// Copyright Sovereign Realms.

#include "Units/SRProjectile.h"
#include "FX/SRFXSprite.h"
#include "Battle/SREconomySubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Units/SRUnit.h"
#include "Buildings/SRBuilding.h"
#include "Common/SRAudioSubsystem.h"
#include "Battle/SRBattleSubsystem.h"
#include "Units/SRSprite.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/World.h"

ASRProjectile::ASRProjectile()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

ASRProjectile* ASRProjectile::Launch(ASRUnit* Shooter, ASRUnit* Target, const FVector& From, const FSRUnitStats& ShooterStats)
{
	return LaunchArrow(Shooter->GetWorld(), Shooter->GetTeam(), Shooter, Target, nullptr, From, ShooterStats.Damage, ShooterStats.KnockbackImpulse,
		ShooterStats.ProjectileSpeed, ShooterStats.ProjectileArc, ShooterStats.SplashRadius, ShooterStats.bStoneProjectile, ShooterStats.BuildingDamageScale);
}

ASRProjectile* ASRProjectile::LaunchArrow(UWorld* World, ESRTeam Team, ASRUnit* ShooterUnit, ASRUnit* TargetUnit, ASRBuilding* TargetBuilding,
	const FVector& From, float Damage, float Knockback, float Speed, float Arc, float Splash, bool bStone, float SplashBuildingScale)
{
	if (!World || (!TargetUnit && !TargetBuilding)) { return nullptr; }
	ASRProjectile* Arrow = World->SpawnActor<ASRProjectile>(From, FRotator::ZeroRotator);
	if (!Arrow) { return nullptr; }

	Arrow->ShooterUnit = ShooterUnit;
	Arrow->TargetUnit = TargetUnit;
	Arrow->TargetBuilding = TargetBuilding;
	Arrow->Start = From;
	Arrow->AimPoint = TargetUnit ? TargetUnit->GetAimPoint() : TargetBuilding->GetAimPointFrom(FVector2D(From));
	const float Dist = FVector::Dist(From, Arrow->AimPoint);
	Arrow->Duration = FMath::Max(Dist / FMath::Max(Speed, 100.f), 0.08f);
	Arrow->ArcHeight = Dist * Arc;
	Arrow->Damage = Damage;
	Arrow->Knockback = Knockback;
	Arrow->Splash = Splash;
	Arrow->bStone = bStone;
	Arrow->SplashBuildingScale = SplashBuildingScale;
	Arrow->ShooterTeam = Team;
	Arrow->BuildVisuals(Team);
	Arrow->Tick(0.f);
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(World))
	{
		if (bStone)
		{
			// the throwing arm's heavy whoom, then the stone's low rush through the air with it
			Audio->PlayAt(ESRSound::SwordSwing, From, 1.4f, 0.45f);
			Audio->PlayAttached(ESRSound::ArrowFly, Arrow->GetRootComponent(), 1.3f, 0.55f);
		}
		else
		{
			Audio->PlayAt(ESRSound::BowRelease, From);
			Audio->PlayAttached(ESRSound::ArrowFly, Arrow->GetRootComponent());   // the whistle travels with the arrow
		}
	}
	return Arrow;
}

void ASRProjectile::BuildVisuals(ESRTeam Team)
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }

	auto MakeCard = [&](UMaterialInterface* Material, bool bShadowOnly)
	{
		UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(this);
		Part->SetMobility(EComponentMobility::Movable);
		Part->SetStaticMesh(bStone && Battle->StoneMaterial ? Battle->UnitCardMesh.Get() : Battle->ArrowCardMesh.Get());
		if (bStone && Battle->StoneMaterial) { Part->SetRelativeScale3D(FVector(1.f, 0.16f, 0.16f)); }   // a 20 px stone on a 160 px card, a little enlarged
		Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Part->SetGenerateOverlapEvents(false);
		Part->bReceivesDecals = false;
		Part->bAffectDynamicIndirectLighting = false;
		Part->bAffectDistanceFieldLighting = false;
		Part->bVisibleInRayTracing = false;
		Part->SetUsingAbsoluteRotation(true);
		Part->SetCastShadow(bShadowOnly);
		if (bShadowOnly)
		{
			Part->bCastHiddenShadow = true;
			Part->SetHiddenInGame(true);
		}
		Part->SetupAttachment(GetRootComponent());
		Part->RegisterComponent();
		Part->SetMaterial(0, Material);
		// Same custom primitive data layout as the troops: one frame (0, 0), no flash, fully faded in; then the team colour.
		Part->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, FVector4(0.f, 0.f, 0.f, 1.f));
		return Part;
	};

	Card = MakeCard(bStone && Battle->StoneMaterial ? Battle->StoneMaterial.Get() : Battle->ArrowMaterial.Get(), false);
	ShadowCard = MakeCard(Battle->ArrowShadowMaterial, true);
	const FLinearColor TeamCol = Battle->TeamColor(Team);
	Card->SetCustomPrimitiveDataVector4(SRSprite::DataTeamColor, FVector4(TeamCol.R, TeamCol.G, TeamCol.B, 1.f));
}

void ASRProjectile::OrientCards(const FVector& Direction)
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || !Card || Direction.IsNearlyZero()) { return; }

	// The card's X axis is the shaft. Turn it about the shaft until its face looks as nearly as it can at the viewer.
	auto Facing = [&Direction](const FVector& TowardViewer)
	{
		FVector Normal = TowardViewer - Direction * FVector::DotProduct(TowardViewer, Direction);
		if (!Normal.Normalize())
		{
			// Flying straight at the viewer: any face will do.
			Normal = FVector::CrossProduct(Direction, FVector::UpVector).GetSafeNormal();
			if (Normal.IsNearlyZero()) { Normal = FVector::RightVector; }
		}
		return FMatrix(Direction, FVector::CrossProduct(Normal, Direction), Normal, FVector::ZeroVector).ToQuat();
	};
	const FSRSpriteView& View = Battle->GetSpriteView();
	if (bStone && Battle->StoneMaterial)
	{
		// a stone is round: it just faces the camera like a troop
		Card->SetWorldRotation(View.CardRotation);
		ShadowCard->SetWorldRotation(View.ShadowRotation);
		return;
	}
	Card->SetWorldRotation(Facing(-View.ViewForward));
	ShadowCard->SetWorldRotation(Facing(-View.SunDir));
}

void ASRProjectile::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this); Battle && Battle->IsFrozen())
	{
		return; // a debug capture is holding the battle still
	}

	if (bStuck)
	{
		// Stand in the ground for a moment, then dissolve.
		StuckTime += DeltaSeconds;
		const float Fade = FMath::Clamp((1.6f - StuckTime) / 0.4f, 0.f, 1.f);
		if (Card && !FMath::IsNearlyEqual(Fade, AppliedFade, 0.01f))
		{
			AppliedFade = Fade;
			Card->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, FVector4(0.f, 0.f, 0.f, Fade));
			ShadowCard->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, FVector4(0.f, 0.f, 0.f, Fade));
		}
		if (StuckTime > 1.6f) { Destroy(); }
		return;
	}

	ASRUnit* Target = TargetUnit.Get();
	ASRBuilding* TargetB = TargetBuilding.Get();
	if (bStone)
	{
		// a stone does not home: it comes down where it was aimed
	}
	else if (Target && Target->IsAlive())
	{
		AimPoint = Target->GetAimPoint(); // gentle homing: the arc bends with a moving target
	}
	else if (TargetB && TargetB->IsAlive())
	{
		// buildings do not move: the aim point stays where it was picked
	}
	else if (!bTargetLost)
	{
		// Target died before we landed: fall to the ground where it stood instead.
		bTargetLost = true;
		if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
		{
			float GroundZ = AimPoint.Z;
			if (Battle->SampleGround(FVector2D(AimPoint.X, AimPoint.Y), AimPoint.Z, GroundZ)) { AimPoint.Z = GroundZ + 4.f; }
		}
	}

	Elapsed += DeltaSeconds;
	const float T = FMath::Clamp(Elapsed / Duration, 0.f, 1.f);

	auto ArcAt = [this](float A)
	{
		FVector P = FMath::Lerp(Start, AimPoint, A);
		P.Z += ArcHeight * 4.f * A * (1.f - A);
		return P;
	};

	const FVector Pos = ArcAt(T);
	const FVector Ahead = ArcAt(FMath::Min(T + 0.03f, 1.03f));
	SetActorLocation(Pos);
	OrientCards((Ahead - Pos).GetSafeNormal());

	if (T >= 1.f && bStone)
	{
		Burst();
		Destroy();
		return;
	}
	if (T >= 1.f)
	{
		if (Target && Target->IsAlive())
		{
			const FVector2D Dir = FVector2D(AimPoint.X - Start.X, AimPoint.Y - Start.Y).GetSafeNormal();
			Target->ReceiveDamage(Damage, ShooterUnit.Get(), Dir, Knockback, false);
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::ArrowHitFlesh, AimPoint); }
			Destroy();
		}
		else if (TargetB && TargetB->IsAlive())
		{
			TargetB->ReceiveDamage(Damage, ShooterUnit.Get());
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::ArrowHitWood, AimPoint); }
			bStuck = true; // sticks in the wall for a moment
		}
		else
		{
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::ArrowHitGround, AimPoint); }
			bStuck = true;
		}
	}
}

void ASRProjectile::Burst()
{
	// Everything of the other side round the landing spot is hurt, the full blow at the centre, half at the edge.
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const FVector2D At(AimPoint.X, AimPoint.Y);
	if (Battle && Splash > 0.f)
	{
		TArray<ASRUnit*> Near;
		Battle->QueryUnits(At, Splash + 80.f, Near);
		for (ASRUnit* U : Near)
		{
			if (!U || !U->IsAlive() || U->GetTeam() == ShooterTeam) { continue; }
			const float D = FVector2D::Distance(U->GetPos2D(), At);
			if (D > Splash + U->GetRadius()) { continue; }
			const float Falloff = 1.f - 0.5f * FMath::Clamp(D / Splash, 0.f, 1.f);
			U->ReceiveDamage(Damage * Falloff, ShooterUnit.Get(), (U->GetPos2D() - At).GetSafeNormal(), Knockback * Falloff, true);
		}
	}
	// a building under the stone (the target, or any other in the blast)
	if (const USREconomySubsystem* Eco = USREconomySubsystem::Get(this))
	{
		for (ASRBuilding* B : Eco->GetBuildings())
		{
			if (B && B->IsAlive() && B->Team != ShooterTeam && B->DistanceToFootprint(At) <= FMath::Max(Splash, 60.f))
			{
				// a stone thrown at a building already carries the building multiplier; one thrown at troops gets it here
				B->ReceiveDamage(TargetBuilding.Get() == B ? Damage : Damage * SplashBuildingScale, ShooterUnit.Get());
			}
		}
	}
	if (Battle) { Battle->AddCameraTrauma(AimPoint, 0.25f); }
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::StoneImpact, AimPoint, 1.f); }
	if (Battle) { Battle->SpawnFX(ESRFX::Impact, AimPoint); }
}
