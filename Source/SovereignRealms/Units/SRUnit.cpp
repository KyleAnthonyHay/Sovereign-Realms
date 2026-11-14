// Copyright Sovereign Realms.

#include "Units/SRUnit.h"
#include "FX/SRFXSprite.h"
#include "Units/SRProjectile.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRAISubsystem.h"
#include "Common/SRAudioSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"

namespace
{
	FVector2D DirFromYaw(float YawDeg)
	{
		const float R = FMath::DegreesToRadians(YawDeg);
		return FVector2D(FMath::Cos(R), FMath::Sin(R));
	}

	float YawFromDir(const FVector2D& Dir)
	{
		return FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
	}
}

ASRUnit::ASRUnit()
{
	// Stepped by USRBattleSubsystem so all units see a consistent frame.
	PrimaryActorTick.bCanEverTick = false;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	VisualRoot = CreateDefaultSubobject<USceneComponent>(TEXT("VisualRoot"));
	VisualRoot->SetupAttachment(Root);
}

void ASRUnit::InitUnit(ESRUnitType InType, ESRTeam InTeam, float InSpawnDelay, const FString& InLabel)
{
	UnitType = InType;
	Team = InTeam;
	SpawnDelay = InSpawnDelay;
	Label = InLabel;
	Battle = USRBattleSubsystem::Get(this);

	Health = Stats().MaxHealth;
	SimPos = GetActorLocation();
	FacingYaw = GetActorRotation().Yaw;
	Home = GetPos2D();
	// Desynchronise the idle cycle and retargeting between units.
	AnimTime = FMath::FRandRange(0.f, 10.f);
	RetargetTimer = FMath::FRandRange(0.f, 0.3f);
	SnortClock = FMath::FRandRange(3.f, 16.f);

	BuildVisuals();
	StepVisual(0.f);
}

const FSRUnitStats& ASRUnit::Stats() const
{
	return USRFeelSettings::Get().StatsFor(UnitType);
}

FVector2D ASRUnit::GetFacingDir() const
{
	return DirFromYaw(FacingYaw);
}

float ASRUnit::GetHealthFrac() const
{
	return FMath::Clamp(Health / FMath::Max(Stats().MaxHealth, 1.f), 0.f, 1.f);
}

float ASRUnit::GetPushMass() const
{
	// Units that are planted (idle or mid-swing) resist shoving more than ones on the move.
	return Stats().Mass * (IsPlanted() ? 2.f : 1.f);
}

bool ASRUnit::IsPlanted() const
{
	return AttackPhase != ESRAttackPhase::Ready || bWorking || ((Order == ESROrder::Idle || Order == ESROrder::Hold) && !Target.IsValid() && !TargetBuilding.IsValid());
}

// ------------------------------------------------------------------ orders

void ASRUnit::OrderMove(const FVector2D& Dest)
{
	if (!IsAlive()) { return; }
	Order = ESROrder::Move;
	Destination = Dest;
	Waypoints.Reset();
	Target = nullptr;
	TargetBuilding = nullptr;
	bReturnHomeWhenDone = false;
	CancelAttack();
	ResetProgress();
}

void ASRUnit::OrderAttackMove(const FVector2D& Dest)
{
	if (!IsAlive()) { return; }
	Order = ESROrder::AttackMove;
	Destination = Dest;
	Waypoints.Reset();
	RetargetTimer = 0.f; // look for something to fight right away
	ResetProgress();
}

void ASRUnit::OrderMovePath(const TArray<FVector2D>& Points, bool bAttackMove)
{
	if (Points.Num() == 0) { return; }
	if (bAttackMove) { OrderAttackMove(Points[0]); }
	else { OrderMove(Points[0]); }
	for (int32 i = 1; i < Points.Num(); ++i) { Waypoints.Add(Points[i]); }
}

void ASRUnit::OrderAttack(ASRUnit* InTarget)
{
	if (!IsAlive() || !InTarget || !InTarget->IsAlive() || InTarget == this) { return; }
	if (Target.Get() != InTarget) { CancelAttack(); }
	Order = ESROrder::AttackTarget;
	Waypoints.Reset();
	Target = InTarget;
	TargetBuilding = nullptr;
	bReturnHomeWhenDone = false;
}

void ASRUnit::OrderAttackBuilding(ASRBuilding* InTarget)
{
	if (!IsAlive() || !InTarget || !InTarget->IsAlive() || InTarget->Team == Team) { return; }
	if (TargetBuilding.Get() != InTarget) { CancelAttack(); }
	Order = ESROrder::AttackTarget;
	Waypoints.Reset();
	Target = nullptr;
	TargetBuilding = InTarget;
	bReturnHomeWhenDone = false;
}

void ASRUnit::OrderBuild(ASRBuilding* InBuilding)
{
	if (!IsAlive() || !Stats().bBuilder || !InBuilding || !InBuilding->IsAlive() || InBuilding->Team != Team) { return; }
	if (BuildTarget.Get() != InBuilding) { bWorking = false; }
	Order = ESROrder::Build;
	BuildTarget = InBuilding;
	Waypoints.Reset();
	Target = nullptr;
	TargetBuilding = nullptr;
	bReturnHomeWhenDone = false;
	CancelAttack();
	ResetProgress();
}

void ASRUnit::OrderHold()
{
	if (!IsAlive()) { return; }
	Order = ESROrder::Hold;
	Waypoints.Reset();
	Target = nullptr;
	TargetBuilding = nullptr;
	Home = GetPos2D();
	bReturnHomeWhenDone = false;
	CancelAttack();
}

void ASRUnit::OrderStop()
{
	if (!IsAlive()) { return; }
	Order = ESROrder::Idle;
	Waypoints.Reset();
	Target = nullptr;
	TargetBuilding = nullptr;
	Home = GetPos2D();
	bReturnHomeWhenDone = false;
	RetargetTimer = 0.6f; // a beat of real stillness before auto-acquire kicks back in
	CancelAttack();
}

void ASRUnit::CancelAttack()
{
	// Orders always win over animation: drop the swing so the unit responds this frame.
	AttackPhase = ESRAttackPhase::Ready;
	PhaseTime = 0.f;
}

void ASRUnit::ResetProgress()
{
	BestDist = TNumericLimits<float>::Max();
	NoProgressTime = 0.f;
}

// --------------------------------------------------------------- simulation

void ASRUnit::StepSim(float Dt)
{
	if (bDead) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& S = Stats();

	if (!bActive)
	{
		SpawnClock += Dt;
		if (SpawnClock >= SpawnDelay + F.SpawnPopTime) { bActive = true; }
		FollowGround(Dt);
		return;
	}

	if (HitStopLeft > 0.f)
	{
		HitStopLeft -= Dt; // frozen on the impact frame
		return;
	}

	Cooldown = FMath::Max(0.f, Cooldown - Dt);
	UpdateTargeting(Dt);
	if (S.bBuilder) { LookForWork(Dt); }
	if (Order != ESROrder::Build) { bWorking = false; }

	const FVector2D Pos = GetPos2D();
	ASRUnit* T = Target.Get();
	ASRBuilding* TB = T ? nullptr : TargetBuilding.Get();
	if (TB && !TB->IsAlive()) { TB = nullptr; TargetBuilding = nullptr; }
	const bool bHolding = Order == ESROrder::Hold || (Stance == ESRStance::HoldGround && Order != ESROrder::Move && Order != ESROrder::AttackTarget);
	FVector2D Desired = FVector2D::ZeroVector;
	FVector2D FaceDir = FVector2D::ZeroVector; // zero = face the direction of travel

	if (Order == ESROrder::Build && AttackPhase == ESRAttackPhase::Ready)
	{
		StepBuild(Dt, Desired, FaceDir);
	}
	else if (AttackPhase != ESRAttackPhase::Ready)
	{
		// Planted for the swing; keep tracking the target.
		if (T) { FaceDir = (T->GetPos2D() - Pos).GetSafeNormal(); }
		else if (TB) { FaceDir = (TB->ClosestPointOnFootprint(Pos, 0.f) - Pos).GetSafeNormal(); }
		TickAttack(Dt, T);
	}
	else if (TB)
	{
		// A building: walk to its nearest wall, strike it there.
		const FVector2D Wall = TB->ClosestPointOnFootprint(Pos, 0.f);
		const float Dist = TB->DistanceToFootprint(Pos);
		const float Reach = S.AttackRange + GetRadius();
		const FVector2D ToDir = (Wall - Pos).GetSafeNormal();
		ResetProgress();
		if (Dist > Reach)
		{
			if (!bHolding)
			{
				const float Remaining = FMath::Max(Dist - Reach * 0.85f, 0.f);
				Desired = ChaseDir(TB->ClosestPointOnFootprint(Pos, GetRadius() + 10.f), Dt) * FMath::Min(S.MaxSpeed, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Remaining) + 40.f);
			}
		}
		else
		{
			FaceDir = ToDir;
			const float AimError = FMath::Abs(FMath::FindDeltaAngleDegrees(FacingYaw, YawFromDir(ToDir)));
			if (Cooldown <= 0.f && AimError < 30.f)
			{
				BeginSwing();
			}
		}
	}
	else if (T)
	{
		const FVector2D To = T->GetPos2D() - Pos;
		const float Dist = To.Size();
		const float Reach = S.AttackRange + GetRadius() + T->GetRadius();
		const FVector2D ToDir = Dist > 1.f ? To / Dist : GetFacingDir();
		ResetProgress();

		if (Dist > Reach)
		{
			// Chase, easing off so we stop just inside reach instead of ramming the target (unless told to hold).
			if (!bHolding)
			{
				const float Remaining = FMath::Max(Dist - Reach * 0.9f, 0.f);
				Desired = ChaseDir(T->GetPos2D(), Dt) * FMath::Min(S.MaxSpeed, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Remaining) + 40.f);
			}
		}
		else
		{
			FaceDir = ToDir;
			const float AimError = FMath::Abs(FMath::FindDeltaAngleDegrees(FacingYaw, YawFromDir(ToDir)));
			if (Cooldown <= 0.f && AimError < 25.f)
			{
				BeginSwing();
			}
			else if (S.bRanged && S.KeepDistance > 0.f && Cooldown > 0.2f)
			{
				// Between shots, give ground to melee attackers that get too close (classic kiting).
				const ASRUnit* Threat = Battle->FindNearestEnemy(this, S.KeepDistance + GetRadius());
				if (Threat && !Threat->Stats().bRanged)
				{
					Desired = (Pos - Threat->GetPos2D()).GetSafeNormal() * S.MaxSpeed;
					FaceDir = FVector2D::ZeroVector;
				}
			}
		}
	}
	else if (Order == ESROrder::Move || Order == ESROrder::AttackMove)
	{
		const FVector2D To = Destination - Pos;
		const float Dist = To.Size();

		if (Dist < BestDist - 4.f) { BestDist = Dist; NoProgressTime = 0.f; }
		else { NoProgressTime += Dt; }

		// Arrived, or someone is parked on our slot and shoving would only cause jitter: settle.
		const bool bGiveUp = NoProgressTime > (Dist < 260.f ? F.GiveUpTimeNear : F.GiveUpTimeFar);
		if (Waypoints.Num() > 0)
		{
			// A corner on the way round a building: cut it at a run, no braking, and head for the next point.
			if (Dist <= FMath::Max(F.ArriveTolerance, 55.f) || bGiveUp)
			{
				Destination = Waypoints[0];
				Waypoints.RemoveAt(0);
				ResetProgress();
			}
			Desired = (Destination - Pos).GetSafeNormal() * S.MaxSpeed;
		}
		else if (Dist <= F.ArriveTolerance || bGiveUp)
		{
			Order = ESROrder::Idle;
		}
		else
		{
			// Arrive: speed limit falls with sqrt(distance) so braking is smooth and never overshoots.
			Desired = (To / Dist) * FMath::Min(S.MaxSpeed, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Dist));
		}
	}

	// --- steering -> velocity ---
	FVector2D Want = Desired + ComputeAvoidance(Desired);
	const float WantSpeed = Want.Size();
	if (WantSpeed > S.MaxSpeed) { Want *= S.MaxSpeed / WantSpeed; }

	if (!Desired.IsNearlyZero())
	{
		// Start moving immediately, but hold some speed back until the body has turned: gives weight without lag.
		const float Align = FVector2D::DotProduct(Want.GetSafeNormal(), GetFacingDir());
		Want *= FMath::Lerp(F.TurnSpeedFloor, 1.f, FMath::Clamp((Align + 0.3f) / 1.3f, 0.f, 1.f));
	}

	const bool bSpeedingUp = Want.SizeSquared() > Velocity.SizeSquared();
	Velocity = FMath::Vector2DInterpConstantTo(Velocity, Want, Dt, bSpeedingUp ? S.Acceleration : S.Deceleration);

	KnockVel *= FMath::Exp(-Dt / FMath::Max(F.KnockbackDecayTime, 0.001f));
	if (KnockVel.SizeSquared() < 1.f) { KnockVel = FVector2D::ZeroVector; }

	const FVector2D Step = (Velocity + KnockVel) * Dt;
	if (Step.SizeSquared() > 1e-6f) { TryMove(Step, Dt); }
	FollowGround(Dt);

	// --- facing ---
	float TargetYaw = FacingYaw;
	if (!FaceDir.IsNearlyZero()) { TargetYaw = YawFromDir(FaceDir); }
	else if (Velocity.SizeSquared() > FMath::Square(25.f)) { TargetYaw = YawFromDir(Velocity); }

	const float Delta = FMath::FindDeltaAngleDegrees(FacingYaw, TargetYaw);
	// Full rate for big turns, easing out for the last few degrees so the turn lands softly.
	const float Rate = S.TurnRateDeg * FMath::Clamp(FMath::Abs(Delta) / 40.f, 0.15f, 1.f);
	const float NewYaw = FMath::FixedTurn(FacingYaw, TargetYaw, Rate * Dt);
	YawRate = Dt > KINDA_SMALL_NUMBER ? FMath::FindDeltaAngleDegrees(FacingYaw, NewYaw) / Dt : 0.f;
	FacingYaw = NewYaw;
}

void ASRUnit::UpdateTargeting(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& S = Stats();
	const bool bAuto = Battle->IsAutoBattle();
	const FVector2D Pos = GetPos2D();

	ASRUnit* T = Target.Get();
	if (T && !T->IsActive())
	{
		Target = nullptr;
		T = nullptr;
		RetargetTimer = 0.f;
		if (Order == ESROrder::AttackTarget) { Order = ESROrder::Idle; Home = Pos; }
	}
	if (TargetBuilding.IsValid() && !TargetBuilding->IsAlive())
	{
		TargetBuilding = nullptr;
		RetargetTimer = 0.f;
		if (Order == ESROrder::AttackTarget) { Order = ESROrder::Idle; Home = Pos; }
	}

	// Explicit orders are obeyed, not second-guessed. Builders never pick a fight of their own.
	if (Order == ESROrder::Move || Order == ESROrder::AttackTarget || Order == ESROrder::Build) { return; }
	if (S.bBuilder) { Target = nullptr; TargetBuilding = nullptr; return; }

	// Defensive stance: a short chase, then back to the post.
	if (Stance == ESRStance::Defensive && (T || TargetBuilding.IsValid()) && FVector2D::Distance(Pos, Home) > F.DefensiveChaseDistance)
	{
		Target = nullptr;
		TargetBuilding = nullptr;
		const FVector2D Post = Home;
		OrderMove(Post);
		Home = Post;
		return;
	}
	if (Stance == ESRStance::Defensive && !T && !TargetBuilding.IsValid() && bReturnHomeWhenDone && Order == ESROrder::Idle && AttackPhase == ESRAttackPhase::Ready)
	{
		bReturnHomeWhenDone = false;
		if (FVector2D::Distance(Pos, Home) > 150.f) { const FVector2D Post = Home; OrderMove(Post); Home = Post; return; }
	}

	if (Team == ESRTeam::Enemy && F.bEnemyLeash && !bAuto)
	{
		const float HomeDist = FVector2D::Distance(Pos, Home);
		if (T && HomeDist > F.EnemyLeashDistance)
		{
			OrderMove(Home); // chased too far: disengage and walk back
			return;
		}
		if (!T && bReturnHomeWhenDone && Order == ESROrder::Idle && AttackPhase == ESRAttackPhase::Ready)
		{
			bReturnHomeWhenDone = false;
			if (HomeDist > 150.f) { OrderAttackMove(Home); }
		}
	}

	RetargetTimer -= Dt;
	if (RetargetTimer > 0.f) { return; }
	RetargetTimer = FMath::FRandRange(0.18f, 0.3f);

	const bool bHold = Order == ESROrder::Hold || Stance == ESRStance::HoldGround;
	const float Range = bAuto ? 1.e7f : (bHold ? S.AttackRange + GetRadius() * 2.f + 40.f : S.AcquireRange);
	const double Now = GetWorld()->GetTimeSeconds();

	if (T)
	{
		const bool bProvoked = (Now - LastProvokedTime) < 4.0;
		if (!bProvoked && FVector2D::Distance(Pos, T->GetPos2D()) > Range * 1.35f)
		{
			Target = nullptr;
			T = nullptr;
		}
	}

	ASRUnit* Nearest = Battle->FindNearestEnemy(this, Range);
	// A catapult cannot lob at what is right under it.
	if (S.MinRange > 0.f)
	{
		if (Nearest && FVector2D::Distance(Pos, Nearest->GetPos2D()) < S.MinRange) { Nearest = nullptr; }
		if (T && FVector2D::Distance(Pos, T->GetPos2D()) < S.MinRange) { Target = nullptr; T = nullptr; }
	}
	// Siege: a building in sight comes before troops.
	if (S.bPrefersBuildings && !bHold && (Order == ESROrder::AttackMove || Order == ESROrder::Idle))
	{
		if (ASRBuilding* B = Battle->FindNearestEnemyBuilding(this, S.AcquireRange))
		{
			Target = nullptr;
			TargetBuilding = B;
			return;
		}
	}
	if (!T)
	{
		Target = Nearest;
	}
	else if (Nearest && Nearest != T && AttackPhase == ESRAttackPhase::Ready)
	{
		// Only swap for something clearly closer, so units commit instead of dithering between targets.
		if (FVector2D::Distance(Pos, Nearest->GetPos2D()) < FVector2D::Distance(Pos, T->GetPos2D()) * 0.6f)
		{
			Target = Nearest;
		}
	}

	// Nobody to fight in range: an enemy building will do (troops always come first).
	if (!Target.IsValid())
	{
		if (!TargetBuilding.IsValid() && (Order == ESROrder::AttackMove || Order == ESROrder::Idle || Order == ESROrder::Hold))
		{
			// In sight and not told otherwise (idle, attack-moving): go for it, like a troop.
			const bool bSeekBuildings = Stance == ESRStance::Aggressive || Order == ESROrder::AttackMove;
			const float BuildingRange = bHold ? S.AttackRange + GetRadius() + 20.f : (bSeekBuildings ? S.AcquireRange : S.AttackRange + 200.f);
			TargetBuilding = Battle->FindNearestEnemyBuilding(this, BuildingRange);
		}
	}
	else
	{
		TargetBuilding = nullptr;
	}

	if ((Target.IsValid() || TargetBuilding.IsValid()) && (Team == ESRTeam::Enemy || Stance == ESRStance::Defensive)) { bReturnHomeWhenDone = true; }
}

void ASRUnit::StepBuild(float Dt, FVector2D& Desired, FVector2D& FaceDir)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& S = Stats();
	const FVector2D Pos = GetPos2D();
	ASRBuilding* B = BuildTarget.Get();
	if (!B || !B->IsAlive() || B->Team != Team || !B->NeedsWork())
	{
		// Done (or gone): stand here and look for the next job straight away.
		BuildTarget = nullptr;
		bWorking = false;
		Order = ESROrder::Idle;
		Home = Pos;
		JobSearchTimer = 0.f;
		return;
	}
	const float Dist = B->DistanceToFootprint(Pos);
	const float Reach = GetRadius() + F.BuilderReach;
	if (Dist > Reach || (!bWorking && Dist > Reach * 0.7f))
	{
		bWorking = false;
		const float Remaining = FMath::Max(Dist - Reach * 0.6f, 0.f);
		Desired = ChaseDir(B->ClosestPointOnFootprint(Pos, GetRadius() + 15.f), Dt) * FMath::Min(S.MaxSpeed, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Remaining) + 40.f);
		return;
	}
	if (!bWorking) { WorkClock = FMath::FRandRange(0.f, 1.f); }
	bWorking = true;
	WorkClock += Dt;
	FaceDir = (B->ClosestPointOnFootprint(Pos, 0.f) - Pos).GetSafeNormal();
}

void ASRUnit::LookForWork(float Dt)
{
	if (Order != ESROrder::Idle || AttackPhase != ESRAttackPhase::Ready || Target.IsValid()) { return; }
	JobSearchTimer -= Dt;
	if (JobSearchTimer > 0.f) { return; }
	JobSearchTimer = FMath::FRandRange(1.0f, 1.6f);

	// The player's builders help out nearby; a commander's go wherever there is work.
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USRAISubsystem* AI = USRAISubsystem::Get(this);
	const bool bCommanded = Team == ESRTeam::Enemy || (AI && AI->IsPlayerAI());
	const float Radius = bCommanded ? 1.e7f : F.BuilderAutoWorkRadius;
	if (Radius <= 0.f) { return; }
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Eco) { return; }
	const FVector2D Pos = GetPos2D();
	ASRBuilding* Best = nullptr;
	float BestScore = TNumericLimits<float>::Max();
	for (ASRBuilding* B : Eco->GetBuildings())
	{
		if (!B || B->Team != Team || !B->IsAlive() || !B->NeedsWork()) { continue; }
		// a damaged building is only worth it once it is properly hurt, or while nothing else is going on
		const bool bSite = B->IsUnderConstruction();
		if (!bSite && B->GetHealthFrac() > 0.9f && !bCommanded) { continue; }
		const float D = B->DistanceToFootprint(Pos);
		if (D > Radius) { continue; }
		// sites nobody can raise without a builder come first, then other sites, then repairs; the nearest of each
		float Score = D;
		if (bSite && B->NeedsBuilder()) { Score *= B->GetBuildersWorking() == 0 ? 0.3f : 0.6f; }
		else if (!bSite) { Score = Score * 1.5f + 600.f; }
		if (Score < BestScore) { BestScore = Score; Best = B; }
	}
	if (Best) { OrderBuild(Best); }
}

void ASRUnit::BeginSwing()
{
	AttackPhase = ESRAttackPhase::Windup;
	PhaseTime = 0.f;
	// a blade (or a rider's sword) cuts the air as the blow comes in
	const FSRUnitStats& S = Stats();
	if (!S.bRanged && !S.bBuilder)
	{
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::SwordSwing, SimPos + FVector(0.f, 0.f, 100.f), 1.f, UnitType == ESRUnitType::Horseman ? 0.85f : 1.f); }
	}
}

void ASRUnit::TickAttack(float Dt, ASRUnit* T)
{
	const FSRUnitStats& S = Stats();
	PhaseTime += Dt;

	if (AttackPhase == ESRAttackPhase::Windup)
	{
		ASRBuilding* B = T ? nullptr : TargetBuilding.Get();
		if (!T && !(B && B->IsAlive()))
		{
			CancelAttack(); // target died mid-windup: no wasted swing, no cooldown penalty
		}
		else if (PhaseTime >= S.WindupTime)
		{
			if (T) { Strike(T); }
			else { StrikeBuilding(B); }
			AttackPhase = ESRAttackPhase::Recovery;
			PhaseTime = 0.f;
			Cooldown = FMath::Max(0.f, S.AttackInterval - S.WindupTime) + FMath::FRandRange(0.f, USRFeelSettings::Get().AttackIntervalJitter);
		}
	}
	else if (PhaseTime >= S.RecoveryTime)
	{
		AttackPhase = ESRAttackPhase::Ready;
		PhaseTime = 0.f;
	}
}

void ASRUnit::Strike(ASRUnit* T)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& S = Stats();
	const FVector2D To = T->GetPos2D() - GetPos2D();
	const FVector2D Dir = To.GetSafeNormal();
	Battle->NotifyStrike(this);

	if (S.bRanged)
	{
		// Damage is applied by the arrow when it lands, not here. The sprite shows its release frame from this frame on.
		ASRProjectile::Launch(this, T, GetMuzzleLocation(), S);
		return;
	}

	// Melee connects on this exact frame, which is also the frame the weapon reaches the target visually.
	const float Reach = S.AttackRange + GetRadius() + T->GetRadius();
	if (To.Size() <= Reach * 1.35f)
	{
		// Cavalry: the first blow after a rest is a charge.
		const double Now = GetWorld()->GetTimeSeconds();
		const bool bCharge = S.ChargeMultiplier > 1.f && (Now - LastStrikeTime) > S.ChargeRestTime;
		LastStrikeTime = Now;
		const float Dmg = S.Damage * (bCharge ? S.ChargeMultiplier : 1.f);
		T->ReceiveDamage(Dmg, this, Dir, S.KnockbackImpulse * (bCharge ? 1.6f : 1.f), S.bHeavyHits);
		if (bCharge)
		{
			Battle->AddCameraTrauma(T->GetSimPos(), F.ShakeTraumaHeavyHit * 1.3f);
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this); Audio && FMath::FRand() < 0.6f) { Audio->PlayAt(ESRSound::HorseNeigh, SimPos + FVector(0.f, 0.f, 150.f)); }
		}
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(S.bHeavyHits ? ESRSound::ShieldBash : ESRSound::SwordHit, T->GetSimPos()); }
		if (S.bHeavyHits)
		{
			if (F.bHitStop) { HitStopLeft = F.HitStopTime; }
			Battle->AddCameraTrauma(T->GetSimPos(), F.ShakeTraumaHeavyHit);
		}
	}
}

void ASRUnit::ReceiveDamage(float Amount, ASRUnit* From, const FVector2D& HitDir, float Knockback, bool bHeavy)
{
	if (bDead) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	const double Now = GetWorld()->GetTimeSeconds();

	Health = FMath::Max(0.f, Health - Amount);
	LastDamagedTime = Now;

	// Reaction is purely additive (flash, squash, flinch frames, a small shove). It never cancels the unit's order or attack.
	HitFlash = 1.f;
	Squash = 1.f;
	HitAnimClock = 0.f;
	Battle->NotifyHit(this);
	KnockVel += HitDir * (Knockback / FMath::Max(Stats().Mass, 0.1f));
	if (bHeavy && F.bHitStop) { HitStopLeft = FMath::Max(HitStopLeft, F.HitStopTime); }

	if (F.bLogHits)
	{
		UE_LOG(LogSovereign, Log, TEXT("HIT   %s -> %s  dmg=%.0f  hp=%.0f/%.0f"),
			From ? *From->GetLabel() : TEXT("?"), *Label, Amount, Health, Stats().MaxHealth);
	}

	if (Health <= 0.f)
	{
		Die(From, HitDir);
		return;
	}

	if (From && From->IsAlive() && From->GetTeam() != Team)
	{
		LastProvokedTime = Now;
		if (!Target.IsValid() && (Order == ESROrder::Idle || Order == ESROrder::AttackMove))
		{
			Target = From; // hit back, even if the shooter is outside acquire range
		}
		TArray<ASRUnit*> Near;
		Battle->QueryUnits(GetPos2D(), F.AlertRadius, Near);
		for (ASRUnit* Ally : Near)
		{
			if (Ally && Ally != this && Ally->GetTeam() == Team)
			{
				Ally->AlertTo(From);
			}
		}
	}
}

void ASRUnit::AlertTo(ASRUnit* Threat)
{
	if (IsActive() && Threat && !Target.IsValid() && Order == ESROrder::Idle && !Stats().bBuilder)
	{
		Target = Threat;
		LastProvokedTime = GetWorld()->GetTimeSeconds();
	}
}

void ASRUnit::Die(ASRUnit* Killer, const FVector2D& HitDir)
{
	if (Battle) { Battle->SpawnFX(ESRFX::Dust, SimPos + FVector(0.f, 0.f, 20.f), UnitType == ESRUnitType::Catapult || UnitType == ESRUnitType::Horseman ? 1.6f : 1.f); }
	if (SpriteCard) { SpriteCard->SetRenderCustomDepth(false); }   // the fallen do not show through walls
	const USRFeelSettings& F = USRFeelSettings::Get();

	// Out of combat this instant; the subsystem moves us to the corpse list at the end of the frame.
	bDead = true;
	DeathClock = 0.f;
	DeathDir = HitDir.IsNearlyZero() ? -GetFacingDir() : HitDir.GetSafeNormal();
	Target = nullptr;
	Order = ESROrder::Idle;
	AttackPhase = ESRAttackPhase::Ready;
	Velocity = FVector2D::ZeroVector;
	HitStopLeft = 0.f;
	bSelected = false;
	bHovered = false;
	TargetFlash = 0.f;
	TargetBuilding = nullptr;

	Battle->AddCameraTrauma(SimPos, F.ShakeTraumaDeath);
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this))
	{
		// an engine does not cry out: its timbers burst apart (with a shower of splinters)
		if (UnitType == ESRUnitType::Catapult)
		{
			Audio->PlayAt(ESRSound::CatapultBreak, SimPos + FVector(0.f, 0.f, 80.f));
			if (Battle) { Battle->SpawnFX(ESRFX::Debris, SimPos + FVector(0.f, 0.f, 60.f), 1.3f); }
		}
		else { Audio->PlayAt(ESRSound::Death, SimPos); }
	}
	Battle->NotifyUnitDied(this, Killer);
}

// ----------------------------------------------------------------- movement

FVector2D ASRUnit::ComputeAvoidance(const FVector2D& Desired) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FVector2D Pos = GetPos2D();
	const bool bMoving = !Desired.IsNearlyZero();
	const FVector2D DesiredDir = Desired.GetSafeNormal();
	const FVector2D Perp(-DesiredDir.Y, DesiredDir.X);
	const ASRUnit* MyTarget = Target.Get();

	FVector2D Separation = FVector2D::ZeroVector;
	float Sidestep = 0.f;

	TArray<ASRUnit*> Near;
	Battle->QueryUnits(Pos, GetRadius() + 50.f + 120.f + F.SeparationPadding, Near);
	for (const ASRUnit* Other : Near)
	{
		if (!Other || Other == this || !Other->IsAlive()) { continue; }

		FVector2D Away = Pos - Other->GetPos2D();
		float Dist = Away.Size();
		if (Dist < 0.5f)
		{
			// Exactly stacked: pick a stable arbitrary direction (depends on which of the two we are).
			Away = (GetUniqueID() < Other->GetUniqueID()) ? FVector2D(1.f, 0.f) : FVector2D(-1.f, 0.f);
			Dist = 0.5f;
		}
		const FVector2D AwayDir = Away / Dist;
		const float Touch = GetRadius() + Other->GetRadius();

		// Soft spacing only between friends. Enemies are meant to press into each other; the hard overlap pass stops interpenetration.
		// A unit standing still does not shuffle away from friends walking past; they go round it.
		const bool bIgnoreMover = !bMoving && IsPlanted() && Other->GetVelocity2D().SizeSquared() > FMath::Square(60.f);
		if (Other->GetTeam() == Team && !bIgnoreMover)
		{
			const float Range = Touch + F.SeparationPadding;
			if (Dist < Range)
			{
				Separation += AwayDir * (1.f - Dist / Range) * 3.f * F.SeparationStrength;
			}
		}

		// Flow round slower bodies in our way instead of pushing straight through them.
		if (bMoving && Other != MyTarget)
		{
			const float LookAhead = Touch + 120.f;
			const float Ahead = FVector2D::DotProduct(-AwayDir, DesiredDir); // 1 = dead ahead
			if (Dist < LookAhead && Ahead > 0.45f && Other->GetVelocity2D().SizeSquared() < Velocity.SizeSquared() * 0.5f + 100.f)
			{
				const float Side = FVector2D::DotProduct(AwayDir, Perp) >= 0.f ? 1.f : -1.f; // keep to the side we are already on
				Sidestep += Side * (Ahead - 0.45f) / 0.55f * (1.f - Dist / LookAhead);
			}
		}
	}

	const float Cap = F.SeparationStrength;
	if (Separation.SizeSquared() > Cap * Cap) { Separation = Separation.GetSafeNormal() * Cap; }

	return Separation + Perp * FMath::Clamp(Sidestep, -1.f, 1.f) * F.SidestepStrength * Stats().MaxSpeed;
}

bool ASRUnit::CanStep(const FVector2D& Step) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FVector2D Dir = Step.GetSafeNormal();
	const FVector2D Pos = GetPos2D();

	// Probe a body-radius ahead: walls / rocks / trunks, then ledges and drops in the ground itself.
	const FVector2D Probe = Pos + Step + Dir * GetRadius() * 0.8f;
	if (Battle->IsPathBlocked(SimPos, FVector(Probe.X, Probe.Y, SimPos.Z))) { return false; }

	float ProbeZ = SimPos.Z;
	if (!Battle->SampleGround(Probe, SimPos.Z, ProbeZ)) { return false; } // off the edge of the world
	if (ProbeZ - SimPos.Z > F.StepHeight) { return false; }
	if (SimPos.Z - ProbeZ > F.MaxDropHeight) { return false; }
	return true;
}

void ASRUnit::TryMove(const FVector2D& Step, float Dt)
{
	if (CanStep(Step))
	{
		SimPos.X += Step.X;
		SimPos.Y += Step.Y;
		UnblockedTime += Dt;
		if (UnblockedTime > 0.35f) { SlideSide = 0; }
		return;
	}

	// Blocked: slide along the obstacle. Stick with one side until clear so we do not dither at a flat face.
	UnblockedTime = 0.f;
	const FVector2D Perp(-Step.Y, Step.X);
	if (SlideSide == 0)
	{
		const FVector2D Goal = Target.IsValid() ? Target->GetPos2D() : Destination;
		SlideSide = FVector2D::DotProduct(Perp, Goal - GetPos2D()) >= 0.f ? 1 : -1;
	}
	for (int32 Attempt = 0; Attempt < 2; ++Attempt)
	{
		const FVector2D Slide = Perp * float(SlideSide);
		if (CanStep(Slide))
		{
			SimPos.X += Slide.X;
			SimPos.Y += Slide.Y;
			Velocity = Slide.GetSafeNormal() * Velocity.Size(); // face the way we are actually going
			return;
		}
		SlideSide = -SlideSide;
	}
	Velocity = FVector2D::ZeroVector;
}

void ASRUnit::Nudge(const FVector2D& Delta)
{
	if (bDead || Delta.SizeSquared() < 1e-6f) { return; }
	const FVector To(SimPos.X + Delta.X, SimPos.Y + Delta.Y, SimPos.Z);
	if (!Battle->IsPathBlocked(SimPos, To))
	{
		SimPos.X = To.X;
		SimPos.Y = To.Y;
	}
}

void ASRUnit::FollowGround(float Dt)
{
	float GroundZ = SimPos.Z;
	if (Battle->SampleGround(GetPos2D(), SimPos.Z, GroundZ))
	{
		SimPos.Z = FMath::FInterpTo(SimPos.Z, GroundZ, Dt, 20.f);
	}
}


void ASRUnit::StrikeBuilding(ASRBuilding* B)
{
	if (!B) { return; }
	const FSRUnitStats& S = Stats();
	Battle->NotifyStrike(this);
	const float Damage = S.Damage * S.BuildingDamageScale;
	if (S.bRanged)
	{
		ASRProjectile::LaunchArrow(GetWorld(), Team, this, nullptr, B, GetMuzzleLocation(), Damage, 0.f, S.ProjectileSpeed, S.ProjectileArc, S.SplashRadius, S.bStoneProjectile, 1.f);
		return;
	}
	if (B->DistanceToFootprint(GetPos2D()) <= (S.AttackRange + GetRadius()) * 1.35f)
	{
		B->ReceiveDamage(Damage, this);
	}
}

FVector2D ASRUnit::ChaseDir(const FVector2D& Goal, float Dt)
{
	const FVector2D Pos = GetPos2D();
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	ChaseRepath -= Dt;
	if (!Grid || FVector2D::DistSquared(Pos, Goal) < FMath::Square(250.f) || Grid->CanWalkStraight(Pos, Goal))
	{
		ChasePath.Reset();
		return (Goal - Pos).GetSafeNormal();
	}
	if (ChasePath.Num() == 0 || ChaseRepath <= 0.f || FVector2D::DistSquared(Goal, ChaseGoal) > FMath::Square(300.f))
	{
		ChasePath.Reset();
		Grid->FindPath(Pos, Goal, ChasePath);
		ChaseGoal = Goal;
		ChaseRepath = FMath::FRandRange(1.0f, 1.6f);
	}
	while (ChasePath.Num() > 1 && FVector2D::DistSquared(Pos, ChasePath[0]) < FMath::Square(70.f)) { ChasePath.RemoveAt(0); }
	return ChasePath.Num() > 0 ? (ChasePath[0] - Pos).GetSafeNormal() : (Goal - Pos).GetSafeNormal();
}
