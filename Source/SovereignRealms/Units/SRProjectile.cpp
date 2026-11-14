// Copyright Sovereign Realms.

#include "Units/SRProjectile.h"
#include "Units/SRUnit.h"
#include "Battle/SRBattleSubsystem.h"
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

	auto AddPart = [&](UStaticMesh* Mesh, const FVector& Loc, const FRotator& Rot, const FVector& Scale, const FLinearColor& Color)
	{
		UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(this);
		Part->SetMobility(EComponentMobility::Movable);
		Part->SetStaticMesh(Mesh);
		Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Part->SetGenerateOverlapEvents(false);
		Part->SetupAttachment(GetRootComponent());
		Part->RegisterComponent();
		Part->SetRelativeLocationAndRotation(Loc, Rot);
		Part->SetRelativeScale3D(Scale);
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(Battle->UnitMaterial, Part);
		MID->SetVectorParameterValue(TEXT("Color"), Color);
		MID->SetVectorParameterValue(TEXT("TeamColor"), Battle->TeamColor(Shooter->GetTeam()));
		Part->SetMaterial(0, MID);
	};

	// Oversized on purpose so the shot reads at tactical zoom. Shaft along +X, head at the front, team-coloured fletching.
	AddPart(Battle->CylinderMesh, FVector::ZeroVector, FRotator(90, 0, 0), FVector(0.035f, 0.035f, 0.78f), FLinearColor(0.75f, 0.62f, 0.42f));
	AddPart(Battle->ConeMesh, FVector(43, 0, 0), FRotator(-90, 0, 0), FVector(0.10f, 0.10f, 0.18f), FLinearColor(0.8f, 0.82f, 0.86f));
	AddPart(Battle->CubeMesh, FVector(-33, 0, 0), FRotator::ZeroRotator, FVector(0.16f, 0.015f, 0.11f), Battle->TeamColor(Shooter->GetTeam()));
	AddPart(Battle->CubeMesh, FVector(-33, 0, 0), FRotator::ZeroRotator, FVector(0.16f, 0.11f, 0.015f), Battle->TeamColor(Shooter->GetTeam()));
}

void ASRProjectile::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (bStuck)
	{
		// Quiver to a stop in the ground, then go.
		StuckTime += DeltaSeconds;
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
	SetActorLocationAndRotation(Pos, (Ahead - Pos).GetSafeNormal().Rotation());

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
