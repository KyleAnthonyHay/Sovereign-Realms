// Copyright Sovereign Realms.
//
// Greybox body construction and procedural animation for ASRUnit.
// Everything here is presentation only: it reads simulation state and never changes it.
// Local axes: +X forward, +Y right, +Z up. Positive pitch tips the top of a part backwards.

#include "Units/SRUnit.h"
#include "Battle/SRBattleSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Common/SRRingComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	const FLinearColor Skin(0.80f, 0.56f, 0.40f);
	const FLinearColor Steel(0.55f, 0.57f, 0.62f);
	const FLinearColor BrightSteel(0.82f, 0.84f, 0.88f);
	const FLinearColor Bronze(0.70f, 0.47f, 0.16f);
	const FLinearColor Leather(0.26f, 0.20f, 0.12f);
	const FLinearColor Wood(0.42f, 0.26f, 0.11f);
	const FLinearColor String(0.85f, 0.82f, 0.72f);

	float EaseOutCubic(float T) { const float U = 1.f - T; return 1.f - U * U * U; }
	float EaseOutBack(float T) { const float C1 = 1.70158f, C3 = C1 + 1.f; const float U = T - 1.f; return 1.f + C3 * U * U * U + C1 * U * U; }
	float Saturate(float T) { return FMath::Clamp(T, 0.f, 1.f); }
}

UStaticMeshComponent* ASRUnit::AddPart(UStaticMesh* Mesh, USceneComponent* Parent, const FVector& Loc, const FRotator& Rot, const FVector& Scale, const FLinearColor& Color)
{
	UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(this);
	Part->SetMobility(EComponentMobility::Movable);
	Part->SetStaticMesh(Mesh);
	Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Part->SetGenerateOverlapEvents(false);
	Part->SetCanEverAffectNavigation(false);
	Part->SetupAttachment(Parent);
	Part->RegisterComponent();
	Part->SetRelativeLocationAndRotation(Loc, Rot);
	Part->SetRelativeScale3D(Scale);

	// Material contract (Docs/VISUAL_CONTRACT.md): Color, TeamColor, HitFlash, Fade.
	UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(Battle->UnitMaterial, Part);
	MID->SetVectorParameterValue(TEXT("Color"), Color);
	MID->SetVectorParameterValue(TEXT("TeamColor"), Battle->TeamColor(Team));
	MID->SetScalarParameterValue(TEXT("HitFlash"), 0.f);
	MID->SetScalarParameterValue(TEXT("Fade"), 1.f);
	Part->SetMaterial(0, MID);
	PartMIDs.Add(MID);
	PartColors.Add(Color);
	return Part;
}

void ASRUnit::BuildVisuals()
{
	UStaticMesh* Cube = Battle->CubeMesh;
	UStaticMesh* Sphere = Battle->SphereMesh;
	UStaticMesh* Cylinder = Battle->CylinderMesh;
	UStaticMesh* Cone = Battle->ConeMesh;

	const FLinearColor TeamCol = Battle->TeamColor(Team);
	const FLinearColor TeamLight = FMath::Lerp(TeamCol, FLinearColor::White, 0.28f);

	WeaponPivot = NewObject<USceneComponent>(this);
	WeaponPivot->SetupAttachment(VisualRoot);
	WeaponPivot->RegisterComponent();

	if (UnitType == ESRUnitType::Shieldbearer)
	{
		// Broad, squat silhouette: team-coloured torso, steel helm with a crest that shows facing,
		// a big round shield on the left arm and an upright blade on the right.
		AddPart(Cylinder, VisualRoot, FVector(0, 0, 54), FRotator::ZeroRotator, FVector(0.68f, 0.68f, 0.84f), TeamCol);
		AddPart(Sphere, VisualRoot, FVector(3, 0, 111), FRotator::ZeroRotator, FVector(0.36f), Skin);
		AddPart(Sphere, VisualRoot, FVector(0, 0, 119), FRotator::ZeroRotator, FVector(0.43f, 0.43f, 0.31f), Steel);
		AddPart(Cube, VisualRoot, FVector(-2, 0, 135), FRotator::ZeroRotator, FVector(0.34f, 0.06f, 0.10f), TeamLight);
		AddPart(Cylinder, VisualRoot, FVector(36, -18, 62), FRotator(90, 0, 0), FVector(0.80f, 0.80f, 0.07f), TeamLight);
		AddPart(Sphere, VisualRoot, FVector(41, -18, 62), FRotator::ZeroRotator, FVector(0.17f), Bronze);

		WeaponPivot->SetRelativeLocation(FVector(8, 36, 86));
		AddPart(Cube, WeaponPivot, FVector(0, 0, 36), FRotator::ZeroRotator, FVector(0.05f, 0.11f, 0.68f), BrightSteel);
		AddPart(Cube, WeaponPivot, FVector(0, 0, 4), FRotator::ZeroRotator, FVector(0.07f, 0.26f, 0.05f), Bronze);
	}
	else
	{
		// Slim silhouette: leather body, team-coloured cape disc and pointed hood (readable from above),
		// tall bow in the left hand, quiver on the back.
		AddPart(Cylinder, VisualRoot, FVector(0, 0, 50), FRotator::ZeroRotator, FVector(0.50f, 0.50f, 0.78f), Leather);
		AddPart(Cylinder, VisualRoot, FVector(-2, 0, 91), FRotator::ZeroRotator, FVector(0.62f, 0.62f, 0.07f), TeamCol);
		AddPart(Sphere, VisualRoot, FVector(4, 0, 104), FRotator::ZeroRotator, FVector(0.33f), Skin);
		AddPart(Cone, VisualRoot, FVector(-1, 0, 120), FRotator::ZeroRotator, FVector(0.44f, 0.44f, 0.44f), TeamLight);
		AddPart(Cylinder, VisualRoot, FVector(-25, 13, 80), FRotator(18, 0, 0), FVector(0.13f, 0.13f, 0.50f), Wood);

		WeaponPivot->SetRelativeLocation(FVector(27, -22, 78));
		AddPart(Cube, WeaponPivot, FVector(-4, 0, 25), FRotator(13, 0, 0), FVector(0.045f, 0.055f, 0.52f), Wood);
		AddPart(Cube, WeaponPivot, FVector(-4, 0, -25), FRotator(-13, 0, 0), FVector(0.045f, 0.055f, 0.52f), Wood);
		AddPart(Cylinder, WeaponPivot, FVector(-10, 0, 0), FRotator::ZeroRotator, FVector(0.012f, 0.012f, 0.98f), String);

		// Arrow on the string; only shown while drawing.
		NockedArrow = AddPart(Cylinder, VisualRoot, FVector(20, -22, 92), FRotator(90, 0, 0), FVector(0.025f, 0.025f, 0.62f), Wood);
		NockedArrow->SetVisibility(false);
	}

	Ring = NewObject<USRRingComponent>(this);
	Ring->SetupAttachment(Root);
	Ring->RegisterComponent();
	Ring->SetRelativeLocation(FVector(0, 0, 3));
	Ring->BuildRing(GetRadius() * 1.12f, GetRadius() * 1.42f);
	Ring->SetVisibility(false);
}

FVector ASRUnit::GetMuzzleLocation() const
{
	const FVector2D Fwd = GetFacingDir();
	return SimPos + FVector(Fwd.X * 34.f, Fwd.Y * 34.f, 92.f);
}

void ASRUnit::SetSelected(bool bInSelected)
{
	if (bInSelected && !bSelected) { RingPop = 1.f; }
	bSelected = bInSelected;
}

void ASRUnit::Acknowledge(float Delay)
{
	AckClock = -Delay;
}

bool ASRUnit::IsCorpseExpired() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return bDead && DeathClock > F.DeathToppleTime + F.CorpseLingerTime + F.CorpseSinkTime;
}

void ASRUnit::StepVisual(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& S = Stats();

	UpdateFlash(Dt);

	if (bDead)
	{
		StepDeathVisual(Dt);
		return;
	}

	SetActorLocationAndRotation(SimPos, FRotator(0.f, FacingYaw, 0.f));
	UpdateRing(Dt);

	const bool bFrozen = HitStopLeft > 0.f; // hold the impact pose
	if (!bFrozen)
	{
		AnimTime += Dt;
		AckClock += Dt;
		Squash = FMath::Max(0.f, Squash - Dt / 0.2f);
	}

	FVector Offset = FVector::ZeroVector;
	float Pitch = 0.f, Roll = 0.f;
	FVector Scale = FVector::OneVector;

	// --- locomotion: bob, forward lean, waddle, bank into turns ---
	const float Speed = Velocity.Size();
	const float SpeedFrac = Saturate(Speed / FMath::Max(S.MaxSpeed, 1.f));
	SmoothedSpeedFrac = FMath::FInterpTo(SmoothedSpeedFrac, SpeedFrac, Dt, 12.f);
	if (!bFrozen) { WalkPhase += Speed * Dt / FMath::Max(F.StrideLength, 1.f) * PI; }
	if (SmoothedSpeedFrac < 0.02f) { WalkPhase = 0.f; }

	Offset.Z += FMath::Abs(FMath::Sin(WalkPhase)) * F.WalkBobHeight * FMath::Sqrt(SmoothedSpeedFrac);
	Pitch -= F.WalkLeanDeg * SmoothedSpeedFrac;
	Roll += FMath::Sin(WalkPhase) * F.WalkWaddleDeg * SmoothedSpeedFrac;
	SmoothedTurnLean = FMath::FInterpTo(SmoothedTurnLean, FMath::Clamp(YawRate / 360.f, -1.f, 1.f) * 7.f * SmoothedSpeedFrac, Dt, 10.f);
	Roll += SmoothedTurnLean;

	// --- idle breathing (fades out while moving) ---
	const float Breath = FMath::Sin(AnimTime * F.BreathRate) * F.BreathAmount * (1.f - SmoothedSpeedFrac);
	Scale.Z *= 1.f + Breath;
	Scale.X *= 1.f - Breath * 0.5f;
	Scale.Y *= 1.f - Breath * 0.5f;

	// --- attack ---
	// Windup:   0..0.7 raise / draw (telegraph), 0.7..1 swing down so contact lands exactly on the strike frame.
	// Recovery: ease back to the rest pose.
	FRotator WeaponRot = S.bRanged ? FRotator(-8.f, 0.f, 28.f) : FRotator(-10.f, 0.f, 0.f);
	FVector WeaponOffset = FVector::ZeroVector;
	bool bShowArrow = false;
	float ArrowPull = 0.f;

	if (AttackPhase == ESRAttackPhase::Windup)
	{
		const float W = Saturate(PhaseTime / FMath::Max(S.WindupTime, 0.01f));
		if (S.bRanged)
		{
			const float Draw = EaseOutCubic(W);
			WeaponRot = FMath::Lerp(WeaponRot, FRotator(0.f, 0.f, 0.f), Saturate(W * 3.f));
			WeaponOffset = FVector(6.f, 0.f, 14.f) * Saturate(W * 3.f);
			Pitch += 7.f * Draw;
			Offset.X -= 5.f * Draw;
			bShowArrow = true;
			ArrowPull = 20.f * Draw;
		}
		else if (W < 0.7f)
		{
			const float Raise = EaseOutCubic(W / 0.7f);
			WeaponRot.Pitch = FMath::Lerp(-10.f, 62.f, Raise);
			Pitch += 11.f * Raise;
			Offset.X -= 9.f * Raise;
		}
		else
		{
			const float Swing = (W - 0.7f) / 0.3f;
			const float SwingE = Swing * Swing;
			WeaponRot.Pitch = FMath::Lerp(62.f, -100.f, SwingE);
			Pitch += FMath::Lerp(11.f, -17.f, SwingE);
			Offset.X += FMath::Lerp(-9.f, F.MeleeLungeDistance, SwingE);
		}
	}
	else if (AttackPhase == ESRAttackPhase::Recovery)
	{
		const float R = EaseOutCubic(Saturate(PhaseTime / FMath::Max(S.RecoveryTime, 0.01f)));
		if (S.bRanged)
		{
			// Release kick: bow jolts forward, body rocks back, then settle.
			WeaponRot = FMath::Lerp(FRotator(-14.f, 0.f, 0.f), WeaponRot, R);
			WeaponOffset = FVector(6.f, 0.f, 14.f) * (1.f - R);
			Pitch += 7.f * (1.f - R);
			Offset.X -= 8.f * (1.f - R);
		}
		else
		{
			WeaponRot.Pitch = FMath::Lerp(-100.f, -10.f, R);
			Pitch += -17.f * (1.f - R);
			Offset.X += F.MeleeLungeDistance * (1.f - R);
		}
	}

	// --- hit reaction: quick squash, no pose interruption ---
	const float Sq = Squash * Squash * F.HitSquash;
	Scale.Z *= 1.f - Sq;
	Scale.X *= 1.f + Sq * 0.6f;
	Scale.Y *= 1.f + Sq * 0.6f;

	// --- order acknowledged: hop with a little stretch ---
	if (AckClock >= 0.f && AckClock < F.AckHopTime)
	{
		const float H = AckClock / F.AckHopTime;
		const float Arc = 4.f * H * (1.f - H);
		Offset.Z += F.AckHopHeight * Arc;
		Scale.Z *= 1.f + 0.10f * Arc;
		Scale.X *= 1.f - 0.05f * Arc;
		Scale.Y *= 1.f - 0.05f * Arc;
	}

	// --- spawn pop-in (overshoots, then settles). Unit becomes active exactly when it finishes. ---
	if (!bActive)
	{
		const float P = Saturate((SpawnClock - SpawnDelay) / FMath::Max(F.SpawnPopTime, 0.01f));
		Scale *= FMath::Max(P <= 0.f ? 0.001f : EaseOutBack(P), 0.001f);
	}

	VisualRoot->SetRelativeLocationAndRotation(Offset, FRotator(Pitch, 0.f, Roll));
	VisualRoot->SetRelativeScale3D(Scale);

	const FVector PivotBase = S.bRanged ? FVector(27, -22, 78) : FVector(8, 36, 86);
	WeaponPivot->SetRelativeLocationAndRotation(PivotBase + WeaponOffset, WeaponRot);

	if (NockedArrow)
	{
		if (NockedArrow->IsVisible() != bShowArrow) { NockedArrow->SetVisibility(bShowArrow); }
		if (bShowArrow) { NockedArrow->SetRelativeLocation(FVector(26.f - ArrowPull, -22.f, 92.f)); }
	}
}

void ASRUnit::StepDeathVisual(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	DeathClock += Dt;

	if (bRingVisible) { Ring->SetVisibility(false); bRingVisible = false; }
	if (NockedArrow && NockedArrow->IsVisible()) { NockedArrow->SetVisibility(false); }

	// Topple away from the blow, accelerating like a fall, with a small settle bounce at the end.
	const float T = Saturate(DeathClock / FMath::Max(F.DeathToppleTime, 0.01f));
	float Fall = T * T;
	const float After = DeathClock - F.DeathToppleTime;
	if (After > 0.f && After < 0.25f) { Fall -= 0.06f * FMath::Sin(After / 0.25f * PI); }

	const FVector Dir3(DeathDir.X, DeathDir.Y, 0.f);
	const FVector Axis = FVector::CrossProduct(FVector::UpVector, Dir3).GetSafeNormal();
	const FQuat Topple(Axis, FMath::DegreesToRadians(88.f * Fall));

	// Then lie still, then sink into the ground and fade (Fade is honoured by M_UnitGreybox if it supports it).
	const float Sink = Saturate((After - F.CorpseLingerTime) / FMath::Max(F.CorpseSinkTime, 0.01f));
	const float SinkE = Sink * Sink;

	SetActorLocationAndRotation(SimPos, FRotator(0.f, FacingYaw, 0.f));
	VisualRoot->SetWorldRotation(Topple * FQuat(FRotator(0.f, FacingYaw, 0.f)));
	VisualRoot->SetRelativeLocation(FVector(0.f, 0.f, GetRadius() * 0.7f * Fall - 95.f * SinkE));
	VisualRoot->SetRelativeScale3D(FVector(1.f));

	if (Sink > 0.f)
	{
		for (UMaterialInstanceDynamic* MID : PartMIDs)
		{
			MID->SetScalarParameterValue(TEXT("Fade"), 1.f - Sink);
		}
	}
}

void ASRUnit::UpdateFlash(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	HitFlash = FMath::Max(0.f, HitFlash - Dt / FMath::Max(F.HitFlashTime, 0.01f));
	if (FMath::IsNearlyEqual(HitFlash, LastAppliedFlash, 0.001f)) { return; }
	LastAppliedFlash = HitFlash;

	for (int32 i = 0; i < PartMIDs.Num(); ++i)
	{
		PartMIDs[i]->SetScalarParameterValue(TEXT("HitFlash"), HitFlash);
		if (Battle->bUnitMaterialIsFallback)
		{
			// The engine fallback material has no HitFlash input, so fake it by driving Color.
			PartMIDs[i]->SetVectorParameterValue(TEXT("Color"), FMath::Lerp(PartColors[i], F.HitFlashColor, HitFlash));
		}
	}
}

void ASRUnit::UpdateRing(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	TargetFlash = FMath::Max(0.f, TargetFlash - Dt);
	RingPop = FMath::FInterpTo(RingPop, 0.f, Dt, 14.f);

	const bool bShow = bActive && (bSelected || bHovered || TargetFlash > 0.f);
	if (bShow != bRingVisible)
	{
		Ring->SetVisibility(bShow);
		bRingVisible = bShow;
	}
	if (!bShow) { return; }

	FLinearColor Color;
	float RingScale = 1.f;
	if (TargetFlash > 0.f)
	{
		Color = F.AttackMarkerColor;
		RingScale = 1.f + 0.22f * FMath::Abs(FMath::Sin(TargetFlash * 14.f));
	}
	else if (bSelected)
	{
		Color = Team == ESRTeam::Player ? F.SelectionRingColor : F.EnemyRingColor;
		RingScale = 1.f + (F.RingSelectPopScale - 1.f) * RingPop;
	}
	else
	{
		Color = Team == ESRTeam::Player ? F.HoverRingColor : F.EnemyRingColor;
		RingScale = 0.9f;
	}
	Ring->SetRingColor(Color);
	Ring->SetRelativeScale3D(FVector(RingScale, RingScale, 1.f));
}
