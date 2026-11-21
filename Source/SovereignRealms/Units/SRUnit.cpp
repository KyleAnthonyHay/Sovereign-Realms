// Copyright Sovereign Realms.

#include "Units/SRUnit.h"
#include "FX/SRFXSprite.h"
#include "Units/SRProjectile.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Battle/SRFogSubsystem.h"
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

	// a Medic is dear: it starts Passive (it runs from foes); G makes it Assertive
	if (UnitType == ESRUnitType::Medic) { Stance = ESRStance::Defensive; }

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
	PaceSpeed = 0.f;
	Order = ESROrder::Move;
	Destination = Dest;
	Waypoints.Reset();
	Target = nullptr;
	TargetBuilding = nullptr;
	bReturnHomeWhenDone = false;
	RepathsLeft = 5;
	CancelAttack();
	ResetProgress();
}

void ASRUnit::OrderAttackMove(const FVector2D& Dest)
{
	if (!IsAlive()) { return; }
	PaceSpeed = 0.f;
	Order = ESROrder::AttackMove;
	Destination = Dest;
	Waypoints.Reset();
	RetargetTimer = 0.f; // look for something to fight right away
	RepathsLeft = 5;
	ResetProgress();
}

void ASRUnit::MarchTo(const FVector2D& T, float Pace, bool bAttackMove)
{
	if (!IsAlive()) { return; }
	const ESROrder Want = bAttackMove ? ESROrder::AttackMove : ESROrder::Move;
	if (Order != Want) { Order = Want; RepathsLeft = 5; ResetProgress(); }
	// a target that keeps moving is not "no progress": only a troop standing still is held up
	if (Velocity.SizeSquared() > FMath::Square(60.f)) { ResetProgress(); }
	Destination = T;
	Waypoints.Reset();
	PaceSpeed = Pace;
}

bool ASRUnit::Repath()
{
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (!Grid || RepathsLeft <= 0) { return false; }
	--RepathsLeft;
	// the march's end stays what it was; only the way there is planned again, from where the troop stands now
	const FVector2D Final = Waypoints.Num() > 0 ? Waypoints.Last() : Destination;
	TArray<FVector2D> Path;
	if (!Grid->FindPath(GetPos2D(), Final, Path) || Path.Num() == 0) { return false; }
	Destination = Path[0];
	Waypoints.Reset();
	for (int32 i = 1; i < Path.Num(); ++i) { Waypoints.Add(Path[i]); }
	ResetProgress();
	SlideSide = 0;
	UE_LOG(LogSovereign, Verbose, TEXT("REPATH %s at (%.0f, %.0f): %d corner(s) to (%.0f, %.0f), %d more allowed"), *GetLabel(), SimPos.X, SimPos.Y, Path.Num(), Final.X, Final.Y, RepathsLeft);
	return true;
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
	if (!IsAlive() || !InTarget || !InTarget->IsAlive() || InTarget == this || IsMedic()) { return; }   // a Medic strikes nobody
	if (Target.Get() != InTarget) { CancelAttack(); }
	Order = ESROrder::AttackTarget;
	Waypoints.Reset();
	Target = InTarget;
	TargetBuilding = nullptr;
	bReturnHomeWhenDone = false;
}

void ASRUnit::OrderAttackBuilding(ASRBuilding* InTarget)
{
	if (!IsAlive() || !InTarget || !InTarget->IsAlive() || InTarget->Team == Team || IsMedic()) { return; }
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

void ASRUnit::OrderGuard(ASRUnit* Ward, ASRBuilding* WardBuilding, const FVector2D& Offset)
{
	if (!IsAlive() || IsBuilder() || Ward == this) { return; }
	if (Ward && (!CanBeGuarded(Ward) || Ward->GetTeam() != Team || !Ward->IsAlive())) { return; }
	if (!Ward && (!WardBuilding || WardBuilding->Team != Team || !WardBuilding->IsAlive())) { return; }
	PaceSpeed = 0.f;
	Order = ESROrder::Guard;
	GuardUnit = Ward;
	GuardBuilding = Ward ? nullptr : WardBuilding;
	GuardOffset = Offset;
	Waypoints.Reset();
	Target = nullptr;
	TargetBuilding = nullptr;
	bReturnHomeWhenDone = false;
	CancelAttack();
	ResetProgress();
	FVector2D W;
	if (GuardWardPos(W)) { GuardLastWard = W; Home = W + GuardOffset; }
}

void ASRUnit::OrderHeal(ASRUnit* Ward)
{
	if (!IsAlive() || !IsMedic() || !Ward || Ward == this || !Ward->IsAlive() || Ward->GetTeam() != Team) { return; }
	PaceSpeed = 0.f;
	Order = ESROrder::Heal;
	HealWard = Ward;
	Waypoints.Reset();
	Target = nullptr;
	TargetBuilding = nullptr;
	bReturnHomeWhenDone = false;
	ResetProgress();
	UE_LOG(LogSovereign, Log, TEXT("HEAL %s follows %s"), *GetLabel(), *Ward->GetLabel());
}

float ASRUnit::Heal(float Amount)
{
	if (!IsAlive() || Amount <= 0.f) { return 0.f; }
	const float Before = Health;
	Health = FMath::Min(Stats().MaxHealth, Health + Amount);
	return Health - Before;
}

bool ASRUnit::InContact(const ASRUnit* Other) const
{
	return Other && FVector2D::Distance(GetPos2D(), Other->GetPos2D()) - GetRadius() - Other->GetRadius() <= USRFeelSettings::Get().MedicContactReach;
}

ASRUnit* ASRUnit::FindWounded(const FVector2D& Centre, float Radius, bool bAvoidFoes) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	TArray<ASRUnit*> Near;
	Battle->QueryUnits(Centre, Radius, Near);
	ASRUnit* Best = nullptr;
	float BestScore = TNumericLimits<float>::Max();
	for (ASRUnit* U : Near)
	{
		if (!U || U == this || !U->IsActive() || U->GetTeam() != Team) { continue; }
		if (U->Stats().MaxHealth - U->GetHealth() < 0.5f) { continue; }
		if (FVector2D::Distance(U->GetPos2D(), Centre) > Radius) { continue; }
		if (bAvoidFoes)
		{
			const ASRUnit* Foe = Battle->FindNearestEnemy(U, F.MedicFleeRange);
			if (Foe && Foe->Stats().AcquireRange > 0.f) { continue; }
		}
		// the worst hurt first; of two alike, the nearer
		const float Score = U->GetHealthFrac() * 1000.f + FVector2D::Distance(U->GetPos2D(), GetPos2D()) * 0.15f;
		if (Score < BestScore) { BestScore = Score; Best = U; }
	}
	return Best;
}

void ASRUnit::HealPulse()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	ASRUnit* P = Patient.Get();
	if (!P || !P->IsAlive() || FVector2D::Distance(GetPos2D(), P->GetPos2D()) - GetRadius() - P->GetRadius() > F.MedicContactReach + 40.f) { return; }
	const float Got = P->Heal(F.MedicHealAmount);
	if (Got >= 0.5f && (Team == ESRTeam::Player || Battle->IsVisibleToPlayer(P)))
	{
		Battle->AddHealPopup(P->GetSimPos() + FVector(0.f, 0.f, P->GetBodyHeight() + 20.f), FMath::RoundToInt(Got));
	}
	UE_LOG(LogSovereign, Verbose, TEXT("HEAL %s bandaged %s (+%.0f)"), *GetLabel(), *P->GetLabel(), Got);
}

bool ASRUnit::StepMedic(float Dt, FVector2D& Desired, FVector2D& FaceDir)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& S = Stats();
	const FVector2D Pos = GetPos2D();
	auto Approach = [&](const FVector2D& To, float StopAt)
	{
		const float Dist = FVector2D::Distance(Pos, To);
		const float Remaining = FMath::Max(Dist - StopAt, 0.f);
		return ChaseDir(To, Dt) * FMath::Min(S.MaxSpeed, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Remaining) + 60.f);
	};

	// 1) Passive: a foe close by and it runs, whatever it was doing (it comes back to its work once clear).
	bFleeing = false;
	if (Stance == ESRStance::Defensive && F.MedicFleeRange > 0.f)
	{
		TArray<ASRUnit*> Near;
		Battle->QueryUnits(Pos, F.MedicFleeRange, Near);
		FVector2D Away = FVector2D::ZeroVector;
		for (const ASRUnit* E : Near)
		{
			if (!E || !E->IsActive() || E->GetTeam() == Team || E->Stats().AcquireRange <= 0.f) { continue; }   // (a Scout or a Medic threatens nobody)
			const FVector2D D = Pos - E->GetPos2D();
			const float Dist = D.Size();
			if (Dist > F.MedicFleeRange) { continue; }
			Away += D.GetSafeNormal() * (1.f - Dist / F.MedicFleeRange + 0.2f);
		}
		if (!Away.IsNearlyZero())
		{
			bFleeing = true;
			Patient = nullptr;
			if (AttackPhase != ESRAttackPhase::Ready) { CancelAttack(); }
			FVector2D To = Pos + Away.GetSafeNormal() * 700.f;
			if (const USRGridSubsystem* Grid = USRGridSubsystem::Get(this)) { To = Grid->NearestWalkable(To, 12, &Pos); }
			Desired = ChaseDir(To, Dt) * S.MaxSpeed;
			ResetProgress();
			return true;
		}
	}

	// 2) Mid-bandaging: it stays down beside the patient until it is done (a patient that walks off, or falls, ends it).
	if (AttackPhase != ESRAttackPhase::Ready)
	{
		ASRUnit* P = Patient.Get();
		// (a little slack once it has knelt: the patient being nudged a step does not break off the bandaging)
		if (!P || !P->IsAlive() || FVector2D::Distance(Pos, P->GetPos2D()) - GetRadius() - P->GetRadius() > F.MedicContactReach + 40.f) { CancelAttack(); }
		else
		{
			FaceDir = (P->GetPos2D() - Pos).GetSafeNormal();
			TickAttack(Dt, nullptr);
			return true;
		}
	}

	// 3) On the march it does not stop (a move order is kept).
	const bool bMarching = (Order == ESROrder::Move || Order == ESROrder::AttackMove || Order == ESROrder::Roam) && FVector2D::Distance(Pos, Destination) > 120.f;
	if (bMarching) { Patient = nullptr; return false; }

	// 4) Who to treat: the one in hand while it still needs it, else the most hurt it may go to. Looking after a troop:
	// that troop and the wounded round it. Otherwise: round itself, far into the fight when Assertive, close and only
	// away from foes when Passive, none it would have to walk to when holding ground.
	ASRUnit* Ward = Order == ESROrder::Heal ? HealWard.Get() : nullptr;
	if (Order == ESROrder::Heal && (!Ward || !Ward->IsAlive()))
	{
		Order = ESROrder::Idle;
		HealWard = nullptr;
		Home = Pos;
		Ward = nullptr;
	}
	ASRUnit* P = Patient.Get();
	if (P && (!P->IsAlive() || P->GetHealth() >= P->Stats().MaxHealth - 0.5f)) { P = nullptr; }
	if (!P)
	{
		const bool bPassive = Stance == ESRStance::Defensive;
		if (Ward) { P = FindWounded(Ward->GetPos2D(), F.MedicWardRadius, bPassive); }
		else if (Order == ESROrder::Idle || Order == ESROrder::Guard)
		{
			const float Reach = Stance == ESRStance::Aggressive ? F.MedicSeekRange : (bPassive ? F.MedicSeekRangePassive : 0.f);
			P = Reach > 0.f ? FindWounded(Pos, Reach, bPassive) : nullptr;
		}
		if (!P && (Order == ESROrder::Hold || Stance == ESRStance::HoldGround))
		{
			// holding: only one already within touch
			ASRUnit* Close = FindWounded(Pos, GetRadius() + 120.f + F.MedicContactReach, false);
			P = Close && InContact(Close) ? Close : nullptr;
		}
	}
	Patient = P;

	// 5) Treat it: run to it, and once touching, kneel and bandage (one every Attack Interval).
	if (P)
	{
		if (InContact(P))
		{
			FaceDir = (P->GetPos2D() - Pos).GetSafeNormal();
			if (Cooldown <= 0.f)
			{
				AttackPhase = ESRAttackPhase::Windup;
				PhaseTime = 0.f;
			}
		}
		else
		{
			Desired = Approach(P->GetPos2D(), GetRadius() + P->GetRadius() + F.MedicContactReach * 0.3f);
		}
		Home = Pos;
		return true;
	}

	// 6) Looking after a troop with nobody to treat: keep beside it.
	if (Ward)
	{
		const float Dist = FVector2D::Distance(Pos, Ward->GetPos2D());
		if (Dist > F.MedicFollowDistance) { Desired = Approach(Ward->GetPos2D(), F.MedicFollowDistance * 0.6f); }
		else if (Velocity.SizeSquared() < FMath::Square(30.f)) { FaceDir = (Ward->GetPos2D() - Pos).GetSafeNormal(); }
		Home = Pos;
		return true;
	}
	return false;
}

void ASRUnit::OrderRoam()
{
	if (!IsAlive()) { return; }
	PickRoamPoint();   // (sets the path; the order stays Roam)
	Order = ESROrder::Roam;
	UE_LOG(LogSovereign, Log, TEXT("ROAM %s sets out"), *GetLabel());
}

bool ASRUnit::PickRoamPoint()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	const USRFogSubsystem* Fog = USRFogSubsystem::Get(this);
	const FVector2D Pos = GetPos2D();
	const FVector2D Half = F.MapHalfExtent * 0.94f;
	// a few candidates 20-70 m off; ground never seen is worth most, then ground out of sight, then distance
	FVector2D Best = Pos;
	float BestScore = -1.f;
	for (int32 i = 0; i < 12; ++i)
	{
		const float A = FMath::FRandRange(0.f, 2.f * PI), R = FMath::FRandRange(2000.f, 7000.f);
		FVector2D P(FMath::Clamp(Pos.X + FMath::Cos(A) * R, -Half.X, Half.X), FMath::Clamp(Pos.Y + FMath::Sin(A) * R, -Half.Y, Half.Y));
		if (Grid) { P = Grid->NearestWalkable(P); }
		if (Battle && (Battle->IsDeepWater(P) || Battle->IsSteep(P))) { continue; }
		float Score = FVector2D::Distance(P, Pos) * 0.2f + FMath::FRandRange(0.f, 600.f);
		if (Fog && Team == ESRTeam::Player)
		{
			if (!Fog->IsExplored(P)) { Score += 4000.f; }
			else if (!Fog->IsVisible(P)) { Score += 1500.f; }
		}
		if (Score > BestScore) { BestScore = Score; Best = P; }
	}
	if (BestScore < 0.f) { return false; }
	TArray<FVector2D> Path;
	if (!Grid || !Grid->FindPath(Pos, Best, Path) || Path.Num() == 0) { Path.Reset(); Path.Add(Best); }
	OrderMovePath(Path, false);
	Order = ESROrder::Roam;
	RoamLegTime = 0.f;
	return true;
}

void ASRUnit::FleeHome()
{
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	const ASRBuilding* Castle = Eco ? Eco->GetCastle(Team) : nullptr;
	if (!Castle) { OrderStop(); return; }
	const FVector Gate = Castle->GetGatePoint();
	TArray<FVector2D> Path;
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (!Grid || !Grid->FindPath(GetPos2D(), FVector2D(Gate.X, Gate.Y), Path) || Path.Num() == 0) { Path.Reset(); Path.Add(FVector2D(Gate.X, Gate.Y)); }
	OrderMovePath(Path, false);
	SetHome(Path.Last());
	UE_LOG(LogSovereign, Log, TEXT("ROAM %s struck: running home"), *GetLabel());
	if (Team == ESRTeam::Player)
	{
		if (USREconomySubsystem* E = USREconomySubsystem::Get(this))
		{
			const FVector2D At = GetPos2D();
			E->PushAlert(ESRAlertKind::Info, FText::Format(NSLOCTEXT("SRUnit", "ScoutFlees", "Your {0} was attacked: running home"), FText::FromString(Stats().DisplayName)), &At);
		}
	}
}

bool ASRUnit::GuardWardPos(FVector2D& Out) const
{
	if (const ASRUnit* U = GuardUnit.Get(); U && U->IsAlive()) { Out = U->GetPos2D(); return true; }
	if (const ASRBuilding* B = GuardBuilding.Get(); B && B->IsAlive()) { Out = B->GetFootprintCentre(); return true; }
	return false;
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
	if (Order == ESROrder::Guard)
	{
		// the post moves with what it guards; gone, and the guard stands where it is
		FVector2D Ward;
		if (!GuardWardPos(Ward)) { Order = ESROrder::Idle; Home = Pos; GuardUnit = nullptr; GuardBuilding = nullptr; }
		else
		{
			if (FVector2D::DistSquared(Ward, GuardLastWard) > FMath::Square(60.f)) { GuardLastWard = Ward; ResetProgress(); }
			Home = Ward + GuardOffset;
		}
	}
	ASRUnit* T = Target.Get();
	ASRBuilding* TB = T ? nullptr : TargetBuilding.Get();
	if (TB && !TB->IsAlive()) { TB = nullptr; TargetBuilding = nullptr; }
	const bool bHolding = Order == ESROrder::Hold || (Stance == ESRStance::HoldGround && Order != ESROrder::Move && Order != ESROrder::AttackTarget);
	FVector2D Desired = FVector2D::ZeroVector;
	FVector2D FaceDir = FVector2D::ZeroVector; // zero = face the direction of travel

	if (IsMedic() && StepMedic(Dt, Desired, FaceDir))
	{
		// (the Medic's own: running from foes, healing, following its ward, going to the wounded)
	}
	else if (Order == ESROrder::Build && AttackPhase == ESRAttackPhase::Ready)
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
	else if (!T && !TB && S.MinRange > 0.f && !bHolding && Order != ESROrder::Move && TooCloseThreat(Pos))
	{
		// A catapult with a foe right under it and nothing farther off to throw at: it cannot lob that close, so it
		// rolls back out to where it can, then takes up the fight again (rather than standing there doing nothing).
		// (with anything in reach beyond its minimum range it stays and shoots that instead)
		const ASRUnit* Threat = TooCloseThreat(Pos);
		Desired = ChaseDir(Pos + (Pos - Threat->GetPos2D()).GetSafeNormal() * (S.MinRange + 200.f), Dt) * S.MaxSpeed;
		ResetProgress();
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
				Desired = ChaseDir(TB->ClosestPointOnFootprint(Pos, GetRadius() + 10.f), Dt, TB) * FMath::Min(S.MaxSpeed, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Remaining) + 40.f);
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
			else if (S.bRanged && S.KeepDistance > 0.f && Cooldown > 0.2f && !bHolding)
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
	else if (Order == ESROrder::Guard)
	{
		// keep to the post beside the ward; one that cannot get closer (a wall, a crowd) settles where it is
		const FVector2D To = Home - Pos;
		const float Dist = To.Size();
		if (Dist < BestDist - 4.f) { BestDist = Dist; NoProgressTime = 0.f; }
		else { NoProgressTime += Dt; }
		const bool bSettle = Dist <= 70.f || (NoProgressTime > 1.2f && Dist < 450.f);
		if (!bSettle)
		{
			Desired = ChaseDir(Home, Dt) * FMath::Min(S.MaxSpeed, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Dist) + 30.f);
		}
		else if (Velocity.SizeSquared() < FMath::Square(30.f))
		{
			FVector2D Ward;
			if (GuardWardPos(Ward) && FVector2D::DistSquared(Pos, Ward) > 1.f) { FaceDir = (Pos - Ward).GetSafeNormal(); }   // facing out, watching
		}
	}
	else if (Order == ESROrder::Move || Order == ESROrder::AttackMove || Order == ESROrder::Roam)
	{
		if (Order == ESROrder::Roam) { RoamLegTime += Dt; }
		const float Top = PaceSpeed > 0.f ? FMath::Min(PaceSpeed, S.MaxSpeed) : S.MaxSpeed;   // a group keeps its slowest pace
		const FVector2D To = Destination - Pos;
		const float Dist = To.Size();

		if (Dist < BestDist - 4.f) { BestDist = Dist; NoProgressTime = 0.f; }
		else { NoProgressTime += Dt; }

		// Arrived, or someone is parked on our slot and shoving would only cause jitter: settle.
		const bool bGiveUp = NoProgressTime > (Dist < 260.f ? F.GiveUpTimeNear : F.GiveUpTimeFar);
		if (Waypoints.Num() > 0)
		{
			// A corner on the way round something: cut it at a run, no braking, and head for the next point.
			// Held up on the way to one (a wall the route clipped, a new building, a crowd): plan the rest again from
			// here. Only when that has been tried too often is the corner skipped, as a last resort.
			if (Dist <= FMath::Max(F.ArriveTolerance, 55.f))
			{
				Destination = Waypoints[0];
				Waypoints.RemoveAt(0);
				ResetProgress();
			}
			else if (NoProgressTime > 0.9f && !Repath())
			{
				if (bGiveUp)
				{
					Destination = Waypoints[0];
					Waypoints.RemoveAt(0);
					ResetProgress();
				}
			}
			Desired = (Destination - Pos).GetSafeNormal() * Top;
		}
		else if (bGiveUp && Dist > 260.f && Repath())
		{
			// stopped well short of where it was sent: another way round, rather than standing at the obstacle
			Desired = (Destination - Pos).GetSafeNormal() * Top;
		}
		else if (Dist <= F.ArriveTolerance || bGiveUp || (Order == ESROrder::Roam && RoamLegTime > 40.f))
		{
			// roaming: on to the next spot (a leg that drags on, stuck somewhere, is given up)
			if (Order != ESROrder::Roam || !PickRoamPoint()) { Order = ESROrder::Idle; }
		}
		else
		{
			// Arrive: speed limit falls with sqrt(distance) so braking is smooth and never overshoots.
			Desired = (To / Dist) * FMath::Min(Top, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Dist));
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

	// A Medic fights nobody, ever.
	if (IsMedic()) { Target = nullptr; TargetBuilding = nullptr; return; }
	// Explicit orders are obeyed, not second-guessed. Builders never pick a fight of their own.
	if (Order == ESROrder::Move || Order == ESROrder::AttackTarget || Order == ESROrder::Build || Order == ESROrder::Roam) { return; }
	if (S.bBuilder) { Target = nullptr; TargetBuilding = nullptr; return; }

	// Defensive stance: chase out to the edge of its sight from its post, then back to the post.
	const float DefensiveLeash = FMath::Max(F.DefensiveChaseDistance, S.Sight());
	if (Stance == ESRStance::Defensive && Order != ESROrder::Guard && (T || TargetBuilding.IsValid()) && FVector2D::Distance(Pos, Home) > DefensiveLeash)
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

	FVector2D GuardWard;
	const bool bGuarding = Order == ESROrder::Guard && GuardWardPos(GuardWard);
	if (bGuarding)
	{
		// a guard lets go of a foe that has left the ward behind, or a chase that has taken it too far
		// (one that struck the ward or us, an archer say, is run down a little further)
		const bool bStruck = (GetWorld()->GetTimeSeconds() - LastProvokedTime) < 4.0;
		const float Leash = F.GuardLeash * (bStruck ? 1.8f : 1.f);
		if (T && (FVector2D::Distance(T->GetPos2D(), GuardWard) > Leash || FVector2D::Distance(Pos, GuardWard) > Leash * 1.3f))
		{
			Target = nullptr;
			T = nullptr;
			RetargetTimer = 0.6f;
			return;
		}
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
	// what it notices: everything in its line of sight (Hold Ground: only what is in reach; a unit with no acquire
	// range of its own, the Scout, picks no fights)
	const float SightReach = S.AcquireRange > 0.f ? FMath::Max(S.AcquireRange, S.Sight()) : 0.f;
	const float Range = bAuto ? 1.e7f : (bHold ? S.AttackRange + GetRadius() * 2.f + 40.f : SightReach);
	const double Now = GetWorld()->GetTimeSeconds();

	if (T)
	{
		// (a hard-to-notice target, the Scout, slips away at a shorter distance; a unit told to hold or with no
		// acquire range of its own lets go as soon as it is no longer being hit)
		const bool bProvoked = (Now - LastProvokedTime) < 4.0;
		// (Aggressive runs a foe down well past its sight; Defensive's leash above brings it home anyway)
		const float Keep = Stance == ESRStance::Aggressive && !bHold ? 2.f : 1.35f;
		if (!bProvoked && FVector2D::Distance(Pos, T->GetPos2D()) > Range * Keep * (bAuto ? 1.f : T->GetNoticeScale()))
		{
			Target = nullptr;
			T = nullptr;
		}
	}

	ASRUnit* Nearest = Battle->FindNearestEnemy(this, Range, S.MinRange);
	if (bGuarding && Nearest && FVector2D::Distance(Nearest->GetPos2D(), GuardWard) > F.GuardLeash * 0.85f) { Nearest = nullptr; }   // not near the ward: not our business
	// A catapult cannot lob at what is right under it.
	if (S.MinRange > 0.f)
	{
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
			// In sight and not told otherwise (idle, attack-moving): go for it, like a troop. Defensive goes too (its leash
			// brings it back); Hold Ground only strikes a wall in reach.
			const float BuildingRange = bHold ? S.AttackRange + GetRadius() + 20.f : SightReach;
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
		Desired = ChaseDir(B->ClosestPointOnFootprint(Pos, GetRadius() + 15.f), Dt, B) * FMath::Min(S.MaxSpeed, FMath::Sqrt(2.f * S.Deceleration * 0.6f * Remaining) + 40.f);
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
		// a building under repair is out of action, so nobody starts mending one of their own accord mid-fight
		if (!bSite && GetWorld()->GetTimeSeconds() - B->GetLastDamagedTime() < 10.0) { continue; }
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
	if (S.bStoneProjectile)
	{
		// the arm is winched back: timber groans
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::Creak, SimPos + FVector(0.f, 0.f, 120.f), 1.3f, 0.6f); }
	}
	else if (!S.bRanged && !S.bBuilder)
	{
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::SwordSwing, SimPos + FVector(0.f, 0.f, 100.f), 1.f, UnitType == ESRUnitType::Horseman ? 0.85f : 1.f); }
	}
}

void ASRUnit::TickAttack(float Dt, ASRUnit* T)
{
	const FSRUnitStats& S = Stats();
	PhaseTime += Dt;

	if (IsMedic())
	{
		// the heal gesture: staff up (the heal goes out at its top), staff down
		if (AttackPhase == ESRAttackPhase::Windup && PhaseTime >= S.WindupTime)
		{
			HealPulse();
			AttackPhase = ESRAttackPhase::Recovery;
			PhaseTime = 0.f;
			Cooldown = FMath::Max(0.f, S.AttackInterval - S.WindupTime);
		}
		else if (AttackPhase == ESRAttackPhase::Recovery && PhaseTime >= S.RecoveryTime)
		{
			AttackPhase = ESRAttackPhase::Ready;
			PhaseTime = 0.f;
		}
		return;
	}
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
	if (Order == ESROrder::Roam && Health > 0.f && (!From || From->GetTeam() != Team)) { FleeHome(); }   // (a tower's arrow has no shooter)
	if (Team == ESRTeam::Player && From)
	{
		if (USREconomySubsystem* Eco = USREconomySubsystem::Get(this)) { Eco->NotifyUnitAttacked(this); }
	}

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
		if (!Target.IsValid() && !IsMedic() && (Order == ESROrder::Idle || Order == ESROrder::AttackMove))
		{
			Target = From; // hit back, even if the shooter is outside acquire range (a Medic never does)
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
	// (a troop with no acquire range of its own, the Scout, does not join other people's fights)
	if (IsActive() && Threat && !Target.IsValid() && (Order == ESROrder::Idle || Order == ESROrder::Guard) && !Stats().bBuilder && Stats().AcquireRange > 0.f)
	{
		Target = Threat;
		LastProvokedTime = GetWorld()->GetTimeSeconds();
	}
}

void ASRUnit::Dismiss()
{
	if (!IsAlive()) { return; }
	UE_LOG(LogSovereign, Log, TEXT("DISMISS %s at (%.0f, %.0f)"), *GetName(), SimPos.X, SimPos.Y);
	Die(nullptr, FVector2D::ZeroVector, true);
}

void ASRUnit::Die(ASRUnit* Killer, const FVector2D& HitDir, bool bQuiet)
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

	if (!bQuiet) { Battle->AddCameraTrauma(SimPos, F.ShakeTraumaDeath); }
	if (USRAudioSubsystem* Audio = bQuiet ? nullptr : USRAudioSubsystem::Get(this))
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
	// deep water is a wall (one already in it may always step out). The spot stepped onto is asked as well as the probe
	// ahead of it: along a bank the probe can clear a water cell's corner that the step itself lands in.
	const FVector2D Next = Pos + Step;
	if (!Stats().bWaterWalker && !Battle->IsDeepWater(Pos) && (Battle->IsDeepWater(Probe) || Battle->IsDeepWater(Next))) { return false; }
	// and so is ground too steep to walk. The terrain is a smooth heightfield: a mountainside rises less than a step
	// across this short probe, so nothing below would stop a troop that is shoved, or chasing, from walking straight
	// up a slope the grid routes everyone round. (One already on it may always step off.)
	if (!Battle->IsSteep(Pos) && (Battle->IsSteep(Probe) || Battle->IsSteep(Next))) { return false; }

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
	// a shove never pushes anyone into deep water
	const FVector2D Edge = FVector2D(To) + Delta.GetSafeNormal() * GetRadius() * 0.6f;
	// (the spot shoved onto is asked as well as the edge beyond it: a shove along a bank can clear a water cell's corner)
	if (!Stats().bWaterWalker && !Battle->IsDeepWater(GetPos2D()) && (Battle->IsDeepWater(Edge) || Battle->IsDeepWater(FVector2D(To)))) { return; }
	// nor onto ground too steep to walk (a mountainside is no wall the trace below would find)
	if (!Battle->IsSteep(GetPos2D()) && (Battle->IsSteep(Edge) || Battle->IsSteep(FVector2D(To)))) { return; }
	if (Battle->IsPathBlocked(SimPos, To)) { return; }
	// nor off a cliff or up a ledge: the ground under the shove must be ground this troop could have stepped onto
	// (the heights and the mountains are tall enough that a shove over the edge would drop a troop out of the fight)
	const USRFeelSettings& F = USRFeelSettings::Get();
	float ToZ = SimPos.Z;
	if (!Battle->SampleGround(FVector2D(To), SimPos.Z, ToZ) || ToZ - SimPos.Z > F.StepHeight || SimPos.Z - ToZ > F.MaxDropHeight) { return; }
	SimPos.X = To.X;
	SimPos.Y = To.Y;
}

void ASRUnit::FollowGround(float Dt)
{
	// Standing still on ground it has settled onto: the terrain never changes (buildings are not ground), so the
	// last sample still holds. Most of an army is standing most of the time; this is its only trace per frame.
	const FVector2D Pos = GetPos2D();
	if (bGroundSettled && FVector2D::DistSquared(Pos, GroundSampleXY) < 0.01f) { return; }
	bGroundSettled = false;
	GroundSampleXY = Pos;

	float GroundZ = SimPos.Z;
	if (Battle->SampleGround(Pos, SimPos.Z, GroundZ))
	{
		// No step ever takes a troop down more than MaxDropHeight, so ground far below is a seam between two terrain
		// meshes seen for a frame (a ramp against its cliff), not somewhere to fall: stay at this height.
		if (SimPos.Z - GroundZ > USRFeelSettings::Get().MaxDropHeight + 30.f) { return; }
		SimPos.Z = FMath::FInterpTo(SimPos.Z, GroundZ, Dt, 20.f);
		if (FMath::Abs(SimPos.Z - GroundZ) < 0.05f)
		{
			SimPos.Z = GroundZ;
			bGroundSettled = true;
		}
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

FVector2D ASRUnit::ChaseDir(const FVector2D& Goal, float Dt, const ASRBuilding* Toward)
{
	const FVector2D Pos = GetPos2D();
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	ChaseRepath -= Dt;
	// Right on top of it, or nothing in between: straight there. (The straight walk is checked even at close range:
	// a wall's foot can be a few steps from a troop standing on the cliff above it.)
	if (!Grid || FVector2D::DistSquared(Pos, Goal) < FMath::Square(120.f) || Grid->CanWalkStraight(Pos, Goal))
	{
		ChasePath.Reset();
		return (Goal - Pos).GetSafeNormal();
	}
	// A building does not move: its route is kept until the troop is held up or the timer runs out. A troop being
	// chased does: a fresh route when it has gone 3 m from where the last one led.
	const bool bStale = Toward ? ChaseBuilding.Get() != Toward : FVector2D::DistSquared(Goal, ChaseGoal) > FMath::Square(300.f);
	if (ChasePath.Num() == 0 || ChaseRepath <= 0.f || bStale)
	{
		ChasePath.Reset();
		if (Toward) { Grid->FindPathToBuilding(Pos, Toward, GetRadius() + 10.f, ChasePath); }
		else { Grid->FindPath(Pos, Goal, ChasePath); }
		ChaseGoal = Goal;
		ChaseBuilding = Toward;
		ChaseRepath = Toward ? FMath::FRandRange(2.2f, 3.0f) : FMath::FRandRange(1.0f, 1.6f);
	}
	while (ChasePath.Num() > 1 && FVector2D::DistSquared(Pos, ChasePath[0]) < FMath::Square(70.f)) { ChasePath.RemoveAt(0); }
	return ChasePath.Num() > 0 ? (ChasePath[0] - Pos).GetSafeNormal() : (Goal - Pos).GetSafeNormal();
}

FString ASRUnit::DescribeState() const
{
	const FVector2D Pos = GetPos2D();
	FString Tgt = TEXT("none");
	if (const ASRUnit* T = Target.Get()) { Tgt = FString::Printf(TEXT("unit %s d=%.0f"), *T->GetLabel(), FVector2D::Distance(Pos, T->GetPos2D())); }
	else if (const ASRBuilding* B = TargetBuilding.Get()) { Tgt = FString::Printf(TEXT("bld %s wall=%.0f"), *B->GetDisplayName(), B->DistanceToFootprint(Pos)); }
	return FString::Printf(TEXT("%s (%.0f,%.0f) order=%d dest=(%.0f,%.0f) wp=%d tgt=[%s] phase=%d cd=%.1f v=%.0f stuck=%.1f"),
		*Label, Pos.X, Pos.Y, int32(Order), Destination.X, Destination.Y, Waypoints.Num(), *Tgt, int32(AttackPhase), Cooldown, Velocity.Size(), NoProgressTime);
}

const ASRUnit* ASRUnit::TooCloseThreat(const FVector2D& Pos) const
{
	// (only a foe that can hurt it up close counts: a lone Builder or Scout wandering past is not worth fleeing)
	const FSRUnitStats& S = Stats();
	if (S.MinRange <= 0.f || !Battle) { return nullptr; }
	const ASRUnit* Near = Battle->FindNearestEnemy(this, S.MinRange * 0.85f);
	if (!Near || Near->GetUnitType() == ESRUnitType::Builder || Near->GetUnitType() == ESRUnitType::Scout || Near->GetUnitType() == ESRUnitType::Medic) { return nullptr; }
	return Near;
}
