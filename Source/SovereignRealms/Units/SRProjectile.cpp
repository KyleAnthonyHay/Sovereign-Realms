// Copyright Sovereign Realms.

#include "Units/SRProjectile.h"
#include "Units/SRUnit.h"
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
	UWorld* World = Shooter->GetWorld();
	ASRProjectile* Arrow = World->SpawnActor<ASRProjectile>(From, FRotator::ZeroRotator);
	if (!Arrow) { return nullptr; }

	Arrow->ShooterUnit = Shooter;
	Arrow->TargetUnit = Target;
	Arrow->Start = From;
	Arrow->AimPoint = Target->GetAimPoint();
	const float Dist = FVector::Dist(From, Arrow->AimPoint);
	Arrow->Duration = FMath::Max(Dist / FMath::Max(ShooterStats.ProjectileSpeed, 100.f), 0.08f);
	Arrow->ArcHeight = Dist * ShooterStats.ProjectileArc;
	Arrow->Damage = ShooterStats.Damage;
	Arrow->Knockback = ShooterStats.KnockbackImpulse;
	Arrow->BuildVisuals(Shooter);
	Arrow->Tick(0.f);
	return Arrow;
}

void ASRProjectile::BuildVisuals(ASRUnit* Shooter)
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }

	auto MakeCard = [&](UMaterialInterface* Material, bool bShadowOnly)
	{
		UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(this);
		Part->SetMobility(EComponentMobility::Movable);
		Part->SetStaticMesh(Battle->ArrowCardMesh);
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

	Card = MakeCard(Battle->ArrowMaterial, false);
	ShadowCard = MakeCard(Battle->ArrowShadowMaterial, true);
	const FLinearColor TeamCol = Battle->TeamColor(Shooter->GetTeam());
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
	if (Target && Target->IsAlive())
	{
		AimPoint = Target->GetAimPoint(); // gentle homing: the arc bends with a moving target
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

	if (T >= 1.f)
	{
		if (Target && Target->IsAlive())
		{
			const FVector2D Dir = FVector2D(AimPoint.X - Start.X, AimPoint.Y - Start.Y).GetSafeNormal();
			Target->ReceiveDamage(Damage, ShooterUnit.Get(), Dir, Knockback, false);
			Destroy();
		}
		else
		{
			bStuck = true;
		}
	}
}
