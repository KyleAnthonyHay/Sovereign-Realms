#include "VLAmbience.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	float Hash(int32 A, int32 B)
	{
		uint32 H = uint32(A) * 73856093u ^ uint32(B) * 19349663u;
		H = (H ^ (H >> 13)) * 1274126177u;
		H ^= H >> 16;
		return float(H & 0xFFFFFF) / float(0xFFFFFF);
	}
}

AVLAmbience::AVLAmbience()
{
	PrimaryActorTick.bCanEverTick = true;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Motes = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Motes"));
	Motes->SetupAttachment(Root);
	Smoke = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Smoke"));
	Smoke->SetupAttachment(Root);
	for (UInstancedStaticMeshComponent* C : { Motes.Get(), Smoke.Get() })
	{
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		C->SetAbsolute(true, true, true);
		C->bAffectDistanceFieldLighting = false;   // moving every frame: it would force a distance-field update each frame
		C->bAffectDynamicIndirectLighting = false;
	}
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeFinder.Succeeded())
	{
		Cube = CubeFinder.Object;
	}
}

void AVLAmbience::BeginPlay()
{
	Super::BeginPlay();
	if (!Cube)
	{
		return;
	}
	Motes->SetStaticMesh(Cube);
	Smoke->SetStaticMesh(Cube);
	if (MoteMaterial)
	{
		Motes->SetMaterial(0, MoteMaterial);
	}
	if (SmokeMaterial)
	{
		Smoke->SetMaterial(0, SmokeMaterial);
	}
	const FTransform Hidden(FRotator::ZeroRotator, FVector(0.f, 0.f, -100000.f), FVector(0.001f));
	for (int32 i = 0; i < MoteCentres.Num() * MotesPerCentre; ++i)
	{
		Motes->AddInstance(Hidden, true);
	}
	for (int32 i = 0; i < SmokeSources.Num() * PuffsPerChimney; ++i)
	{
		Smoke->AddInstance(Hidden, true);
	}
}

void AVLAmbience::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Clock += DeltaSeconds;
	const float T = Clock;

	// motes: each wanders on its own slow loop round its centre, rising and sinking, and winks
	const int32 MoteCount = Motes->GetInstanceCount();
	for (int32 i = 0; i < MoteCount; ++i)
	{
		const int32 C = i / FMath::Max(1, MotesPerCentre);
		if (!MoteCentres.IsValidIndex(C))
		{
			break;
		}
		const float A = Hash(i, 1), B = Hash(i, 2), D = Hash(i, 3), E = Hash(i, 4);
		const float R = MoteRadius * (0.25f + 0.75f * A);
		const float Ang = T * (0.12f + 0.25f * B) * (D > 0.5f ? 1.f : -1.f) + A * 6.2832f;
		const FVector P = MoteCentres[C] + FVector(FMath::Cos(Ang) * R + FMath::Sin(T * 0.7f + E * 9.f) * 22.f,
			FMath::Sin(Ang) * R + FMath::Cos(T * 0.6f + D * 7.f) * 22.f,
			60.f + 150.f * E + FMath::Sin(T * (0.35f + 0.4f * D) + B * 6.2832f) * 45.f);
		const float Wink = FMath::Clamp(FMath::Sin(T * (0.8f + 1.3f * E) + D * 6.2832f) * 0.9f + 0.55f, 0.f, 1.f);
		const float S = MoteSize * (0.5f + 0.5f * A) * Wink / 100.f;
		Motes->UpdateInstanceTransform(i, FTransform(FRotator(0.f, T * 20.f * (B - 0.5f), 0.f), P, FVector(FMath::Max(S, 0.0005f))), true, i == MoteCount - 1, false);
	}

	// smoke: puffs leave the chimney one after another, swell as they climb, lean with the wind, and shrink away
	const int32 PuffCount = Smoke->GetInstanceCount();
	for (int32 i = 0; i < PuffCount; ++i)
	{
		const int32 S = i / FMath::Max(1, PuffsPerChimney);
		const int32 K = i % FMath::Max(1, PuffsPerChimney);
		if (!SmokeSources.IsValidIndex(S))
		{
			break;
		}
		const float Life = 6.5f;
		const float Age = FMath::Fmod(T / Life + float(K) / float(PuffsPerChimney) + Hash(S, 9), 1.f);
		const int32 Cycle = FMath::FloorToInt(T / Life + float(K) / float(PuffsPerChimney) + Hash(S, 9));
		const float J = Hash(i, Cycle);
		const FVector P = SmokeSources[S] + FVector(0.f, 0.f, 10.f) + FVector(0.f, 0.f, 1.f) * (Age * 330.f) + Wind * (Age * Age * 1.6f)
			+ FVector(FMath::Sin(Age * 9.f + J * 6.2832f), FMath::Cos(Age * 7.f + J * 4.f), 0.f) * (14.f + 30.f * Age);
		const float Size = FMath::Lerp(13.f, 44.f, FMath::Sqrt(Age)) * FMath::Clamp((1.f - Age) * 3.2f, 0.f, 1.f) * FMath::Clamp(Age * 12.f, 0.f, 1.f) * (0.75f + 0.5f * J);
		Smoke->UpdateInstanceTransform(i, FTransform(FRotator(0.f, J * 90.f, 0.f), P, FVector(FMath::Max(Size / 100.f, 0.0005f))), true, i == PuffCount - 1, false);
	}
}
