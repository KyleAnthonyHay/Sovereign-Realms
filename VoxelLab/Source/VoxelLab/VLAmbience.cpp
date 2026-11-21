#include "VLAmbience.h"
#include "VLBattle.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"

namespace
{
	float Hash(int32 A, int32 B)
	{
		uint32 H = uint32(A) * 73856093u ^ uint32(B) * 19349663u;
		H = (H ^ (H >> 13)) * 1274126177u;
		H ^= H >> 16;
		return float(H & 0xFFFFFF) / float(0xFFFFFF);
	}

	TAutoConsoleVariable<int32> CVarOptAmbience(TEXT("vl.Opt.Ambience"), 1,
		TEXT("1: motes and chimney smoke out of the player's view are not moved (each is a function of the clock alone: it is where it should be the frame it comes into view); 0: all of them, every frame"));

	/** A cone round the player's view, wider than the screen's corners: what is outside it cannot be on screen. */
	struct FViewCone
	{
		bool bValid = false;
		FVector Eye = FVector::ZeroVector;
		FVector Dir = FVector::ForwardVector;
		float Tan = 1.f;        // of the half angle
		float Cos = 0.f, Sin = 1.f;

		explicit FViewCone(const UWorld* World)
		{
			const APlayerController* PC = World && CVarOptAmbience.GetValueOnGameThread() != 0 ? World->GetFirstPlayerController() : nullptr;
			const APlayerCameraManager* Cam = PC ? PC->PlayerCameraManager.Get() : nullptr;
			if (!Cam)
			{
				return;
			}
			Eye = Cam->GetCameraLocation();
			Dir = Cam->GetCameraRotation().Vector();
			// the screen's corner is no further out than the half field of view x sqrt(2) (any shape up to square), and
			// 12 degrees more for good measure; a view that wide or wider: everything is moved
			const float Half = FMath::Atan(FMath::Tan(FMath::DegreesToRadians(FMath::Clamp(Cam->GetFOVAngle(), 5.f, 170.f) * 0.5f)) * 1.4143f) + FMath::DegreesToRadians(12.f);
			if (Half >= 1.5f)
			{
				return;
			}
			Cos = FMath::Cos(Half);
			Sin = FMath::Sin(Half);
			bValid = true;
		}

		/** May a ball be seen? */
		bool Sees(const FVector& Centre, float Radius) const
		{
			if (!bValid)
			{
				return true;
			}
			const FVector To = Centre - Eye;
			const float Along = float(FVector::DotProduct(To, Dir));
			const float Off = FMath::Sqrt(FMath::Max(0.f, float(To.SizeSquared()) - Along * Along));
			// the distance from the centre to the cone's side (negative inside it)
			return Off * Cos - Along * Sin <= Radius;
		}
	};
}

AVLAmbience::AVLAmbience()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;     // (B: after the camera has moved, so "out of view" is this frame's view)
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
	FVLOptTiming::FScope Timing(FVLOptTiming::Ambience);

	// (B: a swarm or a chimney's smoke the player cannot see is left where it was: each one's place is a function of
	// the clock alone, so it is right again the frame it can be seen; the render data is sent once, after the last
	// one that moved)
	const FViewCone Cone(GetWorld());

	// motes: each wanders on its own slow loop round its centre, rising and sinking, and winks
	const int32 MoteCount = Motes->GetInstanceCount();
	const int32 PerCentre = FMath::Max(1, MotesPerCentre);
	int32 LastMote = INDEX_NONE;
	for (int32 C = 0; C < MoteCentres.Num() && C * PerCentre < MoteCount; ++C)
	{
		// (the loop's radius, the 22 cm wobble, the height it rides at and its bob, and a margin)
		if (Cone.Sees(MoteCentres[C] + FVector(0.f, 0.f, 135.f), MoteRadius + 22.f + 130.f + 60.f))
		{
			LastMote = FMath::Min((C + 1) * PerCentre, MoteCount) - 1;
		}
	}
	bool bCentreSeen = false;
	for (int32 i = 0; i <= LastMote; ++i)
	{
		const int32 C = i / PerCentre;
		if (!MoteCentres.IsValidIndex(C))
		{
			break;
		}
		if (i % PerCentre == 0)
		{
			bCentreSeen = Cone.Sees(MoteCentres[C] + FVector(0.f, 0.f, 135.f), MoteRadius + 22.f + 130.f + 60.f);
		}
		if (!bCentreSeen)
		{
			continue;
		}
		const float A = Hash(i, 1), B = Hash(i, 2), D = Hash(i, 3), E = Hash(i, 4);
		const float R = MoteRadius * (0.25f + 0.75f * A);
		const float Ang = T * (0.12f + 0.25f * B) * (D > 0.5f ? 1.f : -1.f) + A * 6.2832f;
		const FVector P = MoteCentres[C] + FVector(FMath::Cos(Ang) * R + FMath::Sin(T * 0.7f + E * 9.f) * 22.f,
			FMath::Sin(Ang) * R + FMath::Cos(T * 0.6f + D * 7.f) * 22.f,
			60.f + 150.f * E + FMath::Sin(T * (0.35f + 0.4f * D) + B * 6.2832f) * 45.f);
		const float Wink = FMath::Clamp(FMath::Sin(T * (0.8f + 1.3f * E) + D * 6.2832f) * 0.9f + 0.55f, 0.f, 1.f);
		const float S = MoteSize * (0.5f + 0.5f * A) * Wink / 100.f;
		Motes->UpdateInstanceTransform(i, FTransform(FRotator(0.f, T * 20.f * (B - 0.5f), 0.f), P, FVector(FMath::Max(S, 0.0005f))), true, i == LastMote, false);
	}

	// smoke: puffs leave the chimney one after another, swell as they climb, lean with the wind, and shrink away
	const int32 PuffCount = Smoke->GetInstanceCount();
	const int32 PerChimney = FMath::Max(1, PuffsPerChimney);
	// (a column 340 cm tall, leaning with the wind by up to 1.6 of it, its puffs swaying 44 cm and 44 cm across)
	const FVector SmokeMid = FVector(0.f, 0.f, 175.f) + Wind * 0.8f;
	const float SmokeRadius = 175.f + float(Wind.Size()) * 0.8f + 44.f + 60.f + 60.f;
	int32 LastPuff = INDEX_NONE;
	for (int32 S = 0; S < SmokeSources.Num() && S * PerChimney < PuffCount; ++S)
	{
		if (Cone.Sees(SmokeSources[S] + SmokeMid, SmokeRadius))
		{
			LastPuff = FMath::Min((S + 1) * PerChimney, PuffCount) - 1;
		}
	}
	bool bChimneySeen = false;
	for (int32 i = 0; i <= LastPuff; ++i)
	{
		const int32 S = i / PerChimney;
		const int32 K = i % PerChimney;
		if (!SmokeSources.IsValidIndex(S))
		{
			break;
		}
		if (K == 0)
		{
			bChimneySeen = Cone.Sees(SmokeSources[S] + SmokeMid, SmokeRadius);
		}
		if (!bChimneySeen)
		{
			continue;
		}
		const float Life = 6.5f;
		const float Age = FMath::Fmod(T / Life + float(K) / float(PuffsPerChimney) + Hash(S, 9), 1.f);
		const int32 Cycle = FMath::FloorToInt(T / Life + float(K) / float(PuffsPerChimney) + Hash(S, 9));
		const float J = Hash(i, Cycle);
		const FVector P = SmokeSources[S] + FVector(0.f, 0.f, 10.f) + FVector(0.f, 0.f, 1.f) * (Age * 330.f) + Wind * (Age * Age * 1.6f)
			+ FVector(FMath::Sin(Age * 9.f + J * 6.2832f), FMath::Cos(Age * 7.f + J * 4.f), 0.f) * (14.f + 30.f * Age);
		const float Size = FMath::Lerp(13.f, 44.f, FMath::Sqrt(Age)) * FMath::Clamp((1.f - Age) * 3.2f, 0.f, 1.f) * FMath::Clamp(Age * 12.f, 0.f, 1.f) * (0.75f + 0.5f * J);
		Smoke->UpdateInstanceTransform(i, FTransform(FRotator(0.f, J * 90.f, 0.f), P, FVector(FMath::Max(Size / 100.f, 0.0005f))), true, i == LastPuff, false);
	}
}
