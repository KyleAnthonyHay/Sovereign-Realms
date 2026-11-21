#include "VLFootDust.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

UVLFootDust::UVLFootDust()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SetCastShadow(false);
	SetMobility(EComponentMobility::Movable);
	SetAbsolute(true, true, true);                 // the dust stays where it was raised
	bAffectDistanceFieldLighting = false;
	bAffectDynamicIndirectLighting = false;
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeFinder.Succeeded())
	{
		SetStaticMesh(CubeFinder.Object);
	}
}

void UVLFootDust::BeginPlay()
{
	Super::BeginPlay();
	Setup(DustMaterial);
}

void UVLFootDust::Setup(UMaterialInterface* Material)
{
	if (Material)
	{
		DustMaterial = Material;
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(Material, this);
		MID->SetVectorParameterValue(TEXT("Tint"), Color);
		MID->SetScalarParameterValue(TEXT("Emissive"), Glow);      // a little of its own light: dust stays pale in his shadow
		SetMaterial(0, MID);
	}
	if (Puffs.Num() == 0 && GetStaticMesh())
	{
		PoolSize = FMath::Clamp(PoolSize, 4, 256);
		Puffs.SetNum(PoolSize);
		const FTransform Hidden(FRotator::ZeroRotator, FVector(0.f, 0.f, -100000.f), FVector(0.001f));
		for (int32 i = 0; i < PoolSize; ++i)
		{
			AddInstance(Hidden, true);
		}
	}
}

float UVLFootDust::Rand()
{
	Seed = Seed * 1664525u + 1013904223u;
	return float((Seed >> 8) & 0xFFFF) / 65535.f;
}

void UVLFootDust::Emit(const FVector& At, const FVector& Back, int32 Count, float Scale)
{
	for (int32 i = 0; i < Count && Puffs.Num() > 0; ++i)
	{
		FPuff& P = Puffs[Next];
		Next = (Next + 1) % Puffs.Num();
		if (P.Life <= 0.f)
		{
			++Alive;
		}
		const FVector Side = FVector::CrossProduct(Back, FVector::UpVector);
		P.Pos = At + Side * (Rand() - 0.5f) * 16.f * Scale + Back * Rand() * 8.f + FVector(0.f, 0.f, Size * 0.5f);
		P.Vel = Back * Drift * (0.5f + Rand()) + Side * (Rand() - 0.5f) * Drift * 0.9f * Scale + FVector(0.f, 0.f, Rise * (0.5f + Rand()));
		P.Age = 0.f;
		P.Life = Lifetime * (0.75f + 0.5f * Rand());
		P.Size = Size * (0.7f + 0.6f * Rand()) * Scale;
		P.Yaw = Rand() * 90.f;
	}
}

void UVLFootDust::Advance(float DeltaSeconds)
{
	if (Alive <= 0 || DeltaSeconds <= 0.f)
	{
		return;
	}
	for (int32 i = 0; i < Puffs.Num(); ++i)
	{
		FPuff& P = Puffs[i];
		if (P.Life <= 0.f)
		{
			continue;
		}
		P.Age += DeltaSeconds;
		float Edge = 0.001f;
		if (P.Age >= P.Life)
		{
			P.Life = 0.f;
			--Alive;
			P.Pos = FVector(0.f, 0.f, -100000.f);
		}
		else
		{
			const float T = P.Age / P.Life;
			P.Vel *= FMath::Exp(-DeltaSeconds * 3.5f);         // the air stops it
			P.Pos += P.Vel * DeltaSeconds;
			// swells out of the ground, then thins away
			Edge = P.Size * FMath::Lerp(1.f, Growth, FMath::Sqrt(T)) * FMath::Clamp(T * 10.f, 0.f, 1.f) * FMath::Clamp((1.f - T) * 2.2f, 0.f, 1.f) / 100.f;
		}
		UpdateInstanceTransform(i, FTransform(FRotator(0.f, P.Yaw, 0.f), P.Pos, FVector(FMath::Max(Edge, 0.0005f))), true, false, false);
	}
	MarkRenderStateDirty();
}
