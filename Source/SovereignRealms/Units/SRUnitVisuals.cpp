// Copyright Sovereign Realms.
//
// Sprite presentation for ASRUnit: which sheet cell to show, and where the cards stand.
// Everything here is presentation only: it reads simulation state and never changes it.
//
// A unit is three things on screen (Docs/VISUAL_CONTRACT.md, SourceArt/Characters/SPRITE_SPEC.md):
//   SpriteCard  the visible frame on a card parallel to the view plane, pivot at the feet. The material
//               gives it the depth of an upright figure, so it does not sink into walls or the ground.
//   ShadowCard  hidden, shadow-only: the same frame as the sun sees it, so the sun throws a true silhouette.
//   Blob        a small stepped decal under the feet, for contact in shade.
// The frame comes from gameplay, not from a free-running clock, wherever the two must agree:
//   walk    distance actually travelled (one cycle per WalkCycleDistance), so feet do not slide
//   attack  the wind-up / recovery phase, so the authored strike frame is on screen when Strike() runs
//   spawn   the spawn clock, ending on the guard frame as the unit becomes active
//   death   the death clock, holding the corpse frame
// Idle and the hit flinch run on time. Feel layers on top: spawn scale pop, acknowledge hop, hit squash,
// strike lunge, hit-stop (which simply holds whatever frame is up).

#include "Units/SRUnit.h"
#include "FX/SRFXSprite.h"
#include "Battle/SRBattleSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Common/SRRingComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/DecalComponent.h"

namespace
{
	float EaseOutCubic(float T) { const float U = 1.f - T; return 1.f - U * U * U; }
	float EaseOutBack(float T) { const float C1 = 1.70158f, C3 = C1 + 1.f; const float U = T - 1.f; return 1.f + C3 * U * U * U + C1 * U * U; }
	float Saturate(float T) { return FMath::Clamp(T, 0.f, 1.f); }

	/** Height of the shadow card's foot above the unit's ground point, so it never z-fights in the shadow map. */
	const float ShadowCardLift = 1.f;

	UStaticMeshComponent* MakeCard(AActor* Owner, USceneComponent* Parent, UStaticMesh* Mesh, UMaterialInterface* Material, bool bShadowOnly)
	{
		UStaticMeshComponent* Card = NewObject<UStaticMeshComponent>(Owner);
		Card->SetMobility(EComponentMobility::Movable);
		Card->SetStaticMesh(Mesh);
		Card->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Card->SetGenerateOverlapEvents(false);
		Card->SetCanEverAffectNavigation(false);
		Card->bReceivesDecals = false;
		// A flat card must not enter Lumen's scene or the distance fields: it would light and occlude like a wall.
		Card->bAffectDynamicIndirectLighting = false;
		Card->bAffectDistanceFieldLighting = false;
		Card->bVisibleInRayTracing = false;
		Card->SetUsingAbsoluteRotation(true);
		Card->SetUsingAbsoluteScale(true);
		if (bShadowOnly)
		{
			Card->SetCastShadow(true);
			Card->bCastHiddenShadow = true;
			Card->SetHiddenInGame(true);
			// The silhouette changes with the frame (custom primitive data), which the shadow cache cannot see.
			Card->ShadowCacheInvalidationBehavior = EShadowCacheInvalidationBehavior::Always;
		}
		else
		{
			Card->SetCastShadow(false);
			// The material slides vertices along the view ray (up to about 1.5 m), which the mesh bounds do not know about.
			Card->SetBoundsScale(2.f);
		}
		Card->SetupAttachment(Parent);
		Card->RegisterComponent();
		Card->SetMaterial(0, Material);
		return Card;
	}
}

void ASRUnit::BuildVisuals()
{
	SpriteCard = MakeCard(this, VisualRoot, Battle->UnitCardMesh, Battle->GetSpriteMaterial(UnitType), false);
	ShadowCard = MakeCard(this, Root, Battle->UnitCardMesh, Battle->GetSpriteShadowMaterial(UnitType), true);

	const FLinearColor TeamCol = Battle->TeamColor(Team);
	SpriteCard->SetCustomPrimitiveDataVector4(SRSprite::DataTeamColor, FVector4(TeamCol.R, TeamCol.G, TeamCol.B, 1.f));
	// custom depth + team stencil: behind a building the troop shows through as a silhouette (M_Occlusion)
	SpriteCard->SetRenderCustomDepth(true);
	SpriteCard->SetCustomDepthStencilValue(Team == ESRTeam::Player ? 1 : 2);

	Blob = NewObject<UDecalComponent>(this);
	Blob->SetUsingAbsoluteRotation(true);
	Blob->SetupAttachment(Root);
	Blob->RegisterComponent();
	Blob->SetDecalMaterial(Battle->BlobMaterial);
	// Projects straight down. Wider across the screen than in depth, like a figure's footprint seen from the camera.
	Blob->SetWorldRotation(FRotator(-90.f, 0.f, 0.f));
	Blob->DecalSize = FVector(40.f, GetRadius() * 1.3f, GetRadius() * 0.95f);
	Blob->SetFadeScreenSize(0.f);
	Blob->SetRelativeLocation(FVector(0.f, 0.f, 10.f));

	Ring = NewObject<USRRingComponent>(this);
	Ring->SetupAttachment(Root);
	Ring->RegisterComponent();
	Ring->SetRelativeLocation(FVector(0, 0, 3));
	Ring->BuildRing(GetRadius() * 1.12f, GetRadius() * 1.42f);
	Ring->SetVisibility(false);

	LastVisualPos = GetPos2D();
	const FSRSpriteView& View = Battle->GetSpriteView();
	FacingIndex = SRSprite::FacingIndex(FacingYaw, View.ViewYaw);
	ShadowFacingIndex = SRSprite::FacingIndex(FacingYaw, View.SunYaw);
}

FVector ASRUnit::GetMuzzleLocation() const
{
	// Authored in character space (forward, right, up from the feet); the height is scaled so the arrow leaves
	// the bow where the sprite shows it at the current camera pitch.
	const FVector& Muzzle = FSRSpriteSheet::For(UnitType).MuzzleCm;
	const FVector2D Fwd = GetFacingDir();
	const FVector2D Right(-Fwd.Y, Fwd.X);
	const FVector2D Flat = Fwd * Muzzle.X + Right * Muzzle.Y;
	return SimPos + FVector(Flat.X, Flat.Y, Muzzle.Z * Battle->GetSpriteView().HeightScale);
}

FVector ASRUnit::GetAimPoint() const
{
	return SimPos + FVector(0.f, 0.f, GetBodyHeight() * 0.55f * Battle->GetSpriteView().HeightScale);
}

FVector ASRUnit::GetOverheadPoint() const
{
	return SimPos + Battle->GetSpriteView().ViewUp * (FSRSpriteSheet::For(UnitType).TopCm + 14.f);
}

void ASRUnit::GetPickSegment(FVector& OutFeet, FVector& OutHead) const
{
	// The sprite stands on the card through the feet, parallel to the view plane.
	const FVector Up = Battle->GetSpriteView().ViewUp;
	const float Top = FSRSpriteSheet::For(UnitType).TopCm;
	OutFeet = SimPos + Up * (GetRadius() * 0.5f);
	OutHead = SimPos + Up * FMath::Max(Top - GetRadius() * 0.5f, GetRadius());
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
	return bDead && DeathClock > F.DeathAnimTime + F.CorpseLingerTime + F.CorpseFadeTime;
}

void ASRUnit::SetSpriteShown(bool bShown)
{
	if (bShown == bSpriteShown) { return; }
	bSpriteShown = bShown;
	SpriteCard->SetVisibility(bShown && !bCulled);
	Blob->SetVisibility(bShown && !bCulled);
}

void ASRUnit::ApplySprite(ESRSpriteAnim Anim, int32 Frame, float Fade, const FVector& Offset, const FVector2D& CardScale)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRSpriteView& View = Battle->GetSpriteView();
	const FSRSpriteSheet::FAnim& Block = FSRSpriteSheet::For(UnitType).Anim(Anim);
	SpriteAnim = Anim;
	SpriteFrame = FMath::Clamp(Frame, 0, Block.Frames - 1);

	// --- which cell: per-primitive data, so every unit of a type shares one material ---
	const float Col = float(Block.Col + SpriteFrame);
	const FVector4 SpriteData(Col, float(Block.Row + FacingIndex), HitFlash, Fade);
	if (!SpriteData.Equals(AppliedSpriteData, 0.001f))
	{
		AppliedSpriteData = SpriteData;
		SpriteCard->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, SpriteData);
	}
	const FVector4 ShadowData(Col, float(Block.Row + ShadowFacingIndex), 0.f, Fade);
	if (!ShadowData.Equals(AppliedShadowData, 0.001f))
	{
		AppliedShadowData = ShadowData;
		ShadowCard->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, ShadowData);
	}

	// --- where the cards stand ---
	VisualRoot->SetRelativeLocation(Offset);
	SpriteCard->SetWorldRotation(View.CardRotation);
	const float K = FSRSpriteSheet::For(UnitType).CardScale;
	SpriteCard->SetRelativeScale3D(FVector(1.f, CardScale.X * K, CardScale.Y * K));

	const bool bCast = F.bSpriteShadows && bSpriteShown && Fade > 0.02f;
	if (bCast != bShadowCasting)
	{
		bShadowCasting = bCast;
		ShadowCard->SetCastShadow(bCast);
	}
	if (bCast)
	{
		// The shadow follows the lunge but stays on the ground through a hop.
		ShadowCard->SetRelativeLocation(FVector(Offset.X, Offset.Y, ShadowCardLift));
		ShadowCard->SetWorldRotation(View.ShadowRotation);
		ShadowCard->SetRelativeScale3D(View.ShadowScale * FVector(1.f, CardScale.X * K, CardScale.Y * K));
	}

	const float BlobAlpha = F.SpriteBlobStrength * Fade;
	if (!FMath::IsNearlyEqual(BlobAlpha, AppliedBlob, 0.004f))
	{
		AppliedBlob = BlobAlpha;
		Blob->SetDecalColor(FLinearColor(1.f, 1.f, 1.f, BlobAlpha));
	}
}

void ASRUnit::StepVisual(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& S = Stats();
	const FSRSpriteSheet& Sheet = FSRSpriteSheet::For(UnitType);
	const FSRSpriteView& View = Battle->GetSpriteView();

	HitFlash = FMath::Max(0.f, HitFlash - Dt / FMath::Max(F.HitFlashTime, 0.01f));

	// Off screen: hide everything and skip the per-frame posing (transforms, sheet cells, shadow cards). The
	// simulation is unaffected; the pose is rebuilt the frame the unit comes back into view.
	// Off screen, or an enemy in the fog of war.
	const bool bOff = (FVector2D::DistSquared(GetPos2D(), View.FocusXY) > FMath::Square(View.CullRadius) && !bSelected)
		|| (Team == ESRTeam::Enemy && !Battle->IsVisibleToPlayer(this));
	if (bOff != bCulled)
	{
		bCulled = bOff;
		SpriteCard->SetVisibility(!bOff && bSpriteShown);
		Blob->SetVisibility(!bOff && bSpriteShown);
		if (bOff) { ShadowCard->SetCastShadow(false); bShadowCasting = false; }
		if (!bOff) { AppliedSpriteData = AppliedShadowData = FVector4(-1.f, -1.f, -1.f, -1.f); }
	}
	if (bCulled)
	{
		AnimTime += Dt;
		LastVisualPos = GetPos2D();
		if (bDead) { DeathClock += Dt; }
		return;
	}

	if (bDead)
	{
		StepDeathVisual(Dt);
		return;
	}

	// Hooves at a gallop and catapult wheels kick up dust.
	if ((UnitType == ESRUnitType::Horseman || UnitType == ESRUnitType::Catapult) && Velocity.SizeSquared() > FMath::Square(S.MaxSpeed * 0.6f))
	{
		DustClock -= Dt;
		if (DustClock <= 0.f)
		{
			DustClock = FMath::FRandRange(0.22f, 0.36f);
			Battle->SpawnFX(ESRFX::Dust, SimPos - FVector(Velocity.GetSafeNormal() * GetRadius(), -10.f), 0.75f);
		}
	}

	SetActorLocationAndRotation(SimPos, FRotator(0.f, FacingYaw, 0.f));
	UpdateRing(Dt);

	const bool bFrozen = HitStopLeft > 0.f; // hold the impact pose
	if (!bFrozen)
	{
		AnimTime += Dt;
		AckClock += Dt;
		HitAnimClock += Dt;
		Squash = FMath::Max(0.f, Squash - Dt / 0.2f);
	}

	// --- facing rows: one for the camera, one for the sun ---
	FacingIndex = SRSprite::FacingIndexSticky(FacingIndex, FacingYaw, View.ViewYaw, F.FacingHysteresisDeg);
	ShadowFacingIndex = SRSprite::FacingIndexSticky(ShadowFacingIndex, FacingYaw, View.SunYaw, F.FacingHysteresisDeg);

	// --- locomotion: the run cycle advances with the ground actually covered ---
	const FVector2D Pos = GetPos2D();
	const float Moved = FVector2D::Distance(Pos, LastVisualPos);
	LastVisualPos = Pos;
	const float Speed = Velocity.Size();
	const bool bWasWalking = bWalking;
	bWalking = bActive && Speed > (bWalking ? F.WalkSpeedThreshold * 0.5f : F.WalkSpeedThreshold);
	if (bWalking && !bWasWalking)
	{
		// Start on a contact frame, alternating the leading foot from one run to the next.
		WalkDistance = bNextStepRight ? F.WalkCycleDistance * 0.5f : 0.f;
		bNextStepRight = !bNextStepRight;
	}
	if (bWalking) { WalkDistance += Moved; }

	// --- state -> sheet cell ---
	ESRSpriteAnim Anim = ESRSpriteAnim::Idle;
	int32 Frame = 0;
	FVector Offset = FVector::ZeroVector;   // VisualRoot space: +X is the unit's facing
	FVector2D Scale(1.f, 1.f);              // card width, height (about the feet)

	if (!bActive)
	{
		// Rises from a crouch with a scale pop; the last frame is the guard stance, reached as the unit becomes active.
		const float P = (SpawnClock - SpawnDelay) / FMath::Max(F.SpawnPopTime, 0.01f);
		SetSpriteShown(P > 0.f);
		const int32 Frames = Sheet.Anim(ESRSpriteAnim::Spawn).Frames;
		Anim = ESRSpriteAnim::Spawn;
		Frame = FMath::Clamp(FMath::FloorToInt(P * Frames), 0, Frames - 1);
		const float Pop = (1.f - F.SpawnPopAmount) + F.SpawnPopAmount * EaseOutBack(Saturate(P / 0.5f));
		Scale *= FMath::Max(Pop, 0.01f);
	}
	else
	{
		SetSpriteShown(true);
		if (AttackPhase == ESRAttackPhase::Windup)
		{
			Anim = ESRSpriteAnim::Attack;
			Frame = Sheet.AttackFrame(AttackPhase, Saturate(PhaseTime / FMath::Max(S.WindupTime, 0.01f)));
		}
		else if (AttackPhase == ESRAttackPhase::Recovery)
		{
			// Strike() ran on the frame this phase began, so its first frame is the authored strike / release frame.
			const float R = Saturate(PhaseTime / FMath::Max(S.RecoveryTime, 0.01f));
			Anim = ESRSpriteAnim::Attack;
			Frame = Sheet.AttackFrame(AttackPhase, R);
			if (!S.bRanged) { Offset.X += F.MeleeLungeDistance * (1.f - EaseOutCubic(R)); }
		}
		else if (HitAnimClock < F.HitAnimTime && !bWalking)
		{
			// Flinch: only while standing and not attacking, so it never hides a strike or makes feet slide.
			const int32 Frames = Sheet.Anim(ESRSpriteAnim::Hit).Frames;
			Anim = ESRSpriteAnim::Hit;
			Frame = FMath::Min(FMath::FloorToInt(HitAnimClock / F.HitAnimTime * Frames), Frames - 1);
		}
		else if (bWalking)
		{
			const int32 Frames = Sheet.Anim(ESRSpriteAnim::Walk).Frames;
			Anim = ESRSpriteAnim::Walk;
			Frame = FMath::FloorToInt(FMath::Frac(WalkDistance / FMath::Max(F.WalkCycleDistance, 1.f)) * Frames) % Frames;
		}
		else
		{
			const int32 Frames = Sheet.Anim(ESRSpriteAnim::Idle).Frames;
			Frame = FMath::FloorToInt(AnimTime * F.IdleFps) % Frames;
		}
	}

	// --- hit reaction: quick squash on top of the frame, no pose interruption ---
	const float Sq = Squash * Squash * F.HitSquash;
	Scale.Y *= 1.f - Sq;
	Scale.X *= 1.f + Sq * 0.6f;

	// --- order acknowledged: hop with a little stretch ---
	if (AckClock >= 0.f && AckClock < F.AckHopTime)
	{
		const float H = AckClock / F.AckHopTime;
		const float Arc = 4.f * H * (1.f - H);
		Offset.Z += F.AckHopHeight * Arc;
		Scale.Y *= 1.f + 0.10f * Arc;
		Scale.X *= 1.f - 0.05f * Arc;
	}

	ApplySprite(Anim, Frame, 1.f, Offset, Scale);
}

void ASRUnit::StepDeathVisual(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRSpriteSheet& Sheet = FSRSpriteSheet::For(UnitType);
	DeathClock += Dt;

	if (bRingVisible) { Ring->SetVisibility(false); bRingVisible = false; }
	SetSpriteShown(true);

	// The facing rows are frozen from the moment of death (they are simply no longer updated).
	const float AnimTimeTotal = FMath::Max(F.DeathAnimTime, 0.05f);
	const int32 Frames = Sheet.Anim(ESRSpriteAnim::Death).Frames;
	const int32 Frame = FMath::Min(FMath::FloorToInt(DeathClock / AnimTimeTotal * Frames), Frames - 1); // holds the corpse

	// Carried a little way by the blow while falling, then still.
	const float Knock = EaseOutCubic(Saturate(DeathClock / (AnimTimeTotal * 0.6f))) * F.DeathKnockDistance;
	SetActorLocationAndRotation(SimPos + FVector(DeathDir.X, DeathDir.Y, 0.f) * Knock, FRotator(0.f, FacingYaw, 0.f));

	// Lie there, then dissolve (dithered in the sprite, texel by texel in its shadow).
	const float After = DeathClock - AnimTimeTotal - F.CorpseLingerTime;
	const float Fade = 1.f - Saturate(After / FMath::Max(F.CorpseFadeTime, 0.01f));
	ApplySprite(ESRSpriteAnim::Death, Frame, Fade, FVector::ZeroVector, FVector2D(1.f, 1.f));
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
