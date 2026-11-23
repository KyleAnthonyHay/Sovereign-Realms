#include "VLSky.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"

namespace
{
	float SkyHash(int32 A, int32 B)
	{
		uint32 H = uint32(A) * 73856093u ^ uint32(B) * 19349663u;
		H = (H ^ (H >> 13)) * 1274126177u;
		H ^= H >> 16;
		return float(H & 0xFFFFFF) / float(0xFFFFFF);
	}

	const FTransform SkyHidden(FRotator::ZeroRotator, FVector(0.f, 0.f, -100000.f), FVector(0.001f));
}

AVLSky::AVLSky()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;     // (after the camera has moved: the clouds answer this frame's view)
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Clouds = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Clouds"));
	Clouds->SetupAttachment(Root);
	Birds = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Birds"));
	Birds->SetupAttachment(Root);
	for (UInstancedStaticMeshComponent* C : { Clouds.Get(), Birds.Get() })
	{
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		C->SetAbsolute(true, true, true);
		C->bAffectDistanceFieldLighting = false;
		C->bAffectDynamicIndirectLighting = false;
		C->bHiddenInSceneCapture = true;        // (not on the minimap)
	}
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeFinder.Succeeded())
	{
		Cube = CubeFinder.Object;
	}
}

void AVLSky::BeginPlay()
{
	Super::BeginPlay();
	if (!Cube)
	{
		return;
	}
	Clouds->SetStaticMesh(Cube);
	Birds->SetStaticMesh(Cube);
	if (CloudMaterial)
	{
		Clouds->SetMaterial(0, CloudMaterial);
	}
	if (BirdMaterial)
	{
		Birds->SetMaterial(0, BirdMaterial);
	}
	for (int32 i = 0; i < CloudCentres.Num() * FMath::Max(1, PuffsPerCloud); ++i)
	{
		Clouds->AddInstance(SkyHidden, true);
	}
	for (int32 i = 0; i < FlockCentres.Num() * FMath::Max(1, BirdsPerFlock) * 3; ++i)
	{
		Birds->AddInstance(SkyHidden, true);
	}
	CloudShown.Init(0.f, CloudCentres.Num());
}

void AVLSky::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Clock += DeltaSeconds;
	const float T = Clock;
	FVector Eye(0.f, 0.f, -1.e9f);
	bool bEye = false;
	if (const APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr)
	{
		if (const APlayerCameraManager* Cam = PC->PlayerCameraManager.Get())
		{
			Eye = Cam->GetCameraLocation();
			bEye = true;
		}
	}

	// ---- clouds: boxes on a 2 m grid round a middle that drifts; puffed away near the camera and under it
	const int32 Per = FMath::Max(1, PuffsPerCloud);
	const int32 NumPuffs = Clouds->GetInstanceCount();
	const float Fade = FMath::Max(CloudFade, 1.f);
	for (int32 c = 0; c < CloudCentres.Num() && (c + 1) * Per <= NumPuffs; ++c)
	{
		const FVector Half = CloudSizes.IsValidIndex(c) ? CloudSizes[c] : FVector(2400.f, 1400.f, 500.f);
		const float P1 = SkyHash(c, 11) * 6.2832f, P2 = SkyHash(c, 12) * 6.2832f;
		const FVector Mid = CloudCentres[c] + FVector(FMath::Sin(T * CloudDriftRate + P1) * CloudDrift, FMath::Cos(T * CloudDriftRate * 0.8f + P2) * CloudDrift * 0.6f,
			FMath::Sin(T * CloudDriftRate * 2.3f + P1) * 120.f);
		float Want = 1.f;
		if (bEye)
		{
			const float Near = FMath::Clamp((float(FVector::Dist(Eye, Mid)) - float(Half.X) - CloudHideNear) / Fade, 0.f, 1.f);
			const float Under = FMath::Clamp((float(Mid.Z) - CloudHideUnder - float(Eye.Z)) / Fade, 0.f, 1.f);
			Want = Near * Under;
		}
		float& Shown = CloudShown[c];
		const bool bWas = Shown > 0.f;
		Shown = Clock < 0.5f ? Want : FMath::FInterpTo(Shown, Want, DeltaSeconds, 2.5f);
		const float S = Shown * Shown * (3.f - 2.f * Shown);
		const bool bLast = c == CloudCentres.Num() - 1;
		if (S <= 0.002f && !bWas)
		{
			continue;       // (still away)
		}
		for (int32 k = 0; k < Per; ++k)
		{
			const int32 i = c * Per + k;
			const float A = SkyHash(i, 1), B = SkyHash(i, 2), D = SkyHash(i, 3), E = SkyHash(i, 4);
			// the first box is the cloud's body; the others lie round it, smaller towards the ends and the top
			FVector Off = k == 0 ? FVector::ZeroVector : FVector((A - 0.5f) * 1.6f * Half.X, (B - 0.5f) * 1.5f * Half.Y, (D - 0.3f) * 1.5f * Half.Z);
			const float Edge = 1.f - 0.55f * FMath::Abs(float(Off.X)) / FMath::Max(float(Half.X), 1.f);
			FVector Size = k == 0 ? FVector(Half.X * 0.8f, Half.Y * 0.85f, Half.Z * 0.9f) : FVector(Half.X * (0.3f + 0.3f * E), Half.Y * (0.35f + 0.35f * A), Half.Z * (0.6f + 0.6f * B)) * Edge;
			Off = FVector(FMath::RoundToFloat(Off.X / 200.f) * 200.f, FMath::RoundToFloat(Off.Y / 200.f) * 200.f, FMath::RoundToFloat(Off.Z / 100.f) * 100.f);
			Size = FVector(FMath::Max(200.f, FMath::RoundToFloat(Size.X / 200.f) * 200.f), FMath::Max(200.f, FMath::RoundToFloat(Size.Y / 200.f) * 200.f),
				FMath::Max(100.f, FMath::RoundToFloat(Size.Z / 100.f) * 100.f));
			const FTransform Tr = S <= 0.002f ? SkyHidden : FTransform(FRotator::ZeroRotator, Mid + Off, Size * (S / 50.f));
			Clouds->UpdateInstanceTransform(i, Tr, true, false, false);      // (no render-state rebuild: the instance data goes to the renderer by itself)
		}
	}

	// ---- birds: each flock on its loop; each bird at its place in the flock, beating and gliding
	const int32 PerFlock = FMath::Max(1, BirdsPerFlock);
	const int32 NumParts = Birds->GetInstanceCount();
	for (int32 f = 0; f < FlockCentres.Num() && (f + 1) * PerFlock * 3 <= NumParts; ++f)
	{
		const float R = FlockRadii.IsValidIndex(f) ? FlockRadii[f] : 9000.f;
		const float Dir = SkyHash(f, 21) > 0.5f ? 1.f : -1.f;
		const float Speed = BirdSpeed * (0.8f + 0.4f * SkyHash(f, 22));
		const float Th = Dir * T * Speed / FMath::Max(R, 100.f) + SkyHash(f, 23) * 6.2832f;
		auto Loop = [&](float A)
		{
			const float Rr = R * (1.f + 0.16f * FMath::Sin(A * 2.f + f) + 0.08f * FMath::Sin(A * 3.f + 2.f * f));
			return FlockCentres[f] + FVector(FMath::Cos(A) * Rr, FMath::Sin(A) * Rr * 0.8f, FMath::Sin(A * 2.f + f * 1.7f) * 600.f + FMath::Sin(T * 0.13f + f) * 300.f);
		};
		const FVector Pos = Loop(Th);
		const FVector Fwd = (Loop(Th + Dir * 0.02f) - Pos).GetSafeNormal();
		const FVector Right = FVector::CrossProduct(FVector::UpVector, Fwd).GetSafeNormal();
		const float Bank = -Dir * 22.f;
		for (int32 b = 0; b < PerFlock; ++b)
		{
			const int32 Id = f * 100 + b;
			const float A = SkyHash(Id, 31), B = SkyHash(Id, 32), D = SkyHash(Id, 33);
			// a loose V: each row further back and out, each bird wandering a little about its place
			const int32 Row = (b + 1) / 2;
			const float Side = (b % 2 == 0) ? 1.f : -1.f;
			const FVector Place = Pos - Fwd * (Row * 420.f + FMath::Sin(T * 0.4f + A * 6.f) * 120.f) + Right * (Side * Row * 360.f + FMath::Sin(T * 0.3f + B * 6.f) * 150.f)
				+ FVector(0.f, 0.f, (D - 0.5f) * 300.f + FMath::Sin(T * 0.5f + D * 6.f) * 80.f);
			// it beats for a while, then glides
			const float Mode = FMath::Clamp(FMath::Sin(T * (0.25f + 0.2f * A) + B * 6.2832f) * 2.f + 0.9f, 0.f, 1.f);
			const float Flap = FMath::Sin(T * (2.6f + 1.2f * D) * 6.2832f / 2.f + A * 6.2832f) * 38.f * Mode + 6.f;
			const FQuat Body = FRotationMatrix::MakeFromXZ(Fwd, FVector::UpVector).ToQuat() * FQuat(FVector::ForwardVector, FMath::DegreesToRadians(Bank));
			const float Span = BirdSpan * (0.8f + 0.4f * B);
			const int32 i = (f * PerFlock + b) * 3;
			Birds->UpdateInstanceTransform(i, FTransform(Body, Place, FVector(Span * 0.42f, Span * 0.12f, Span * 0.09f) / 100.f), true, false, false);
			for (int32 w = 0; w < 2; ++w)
			{
				const float Sg = w == 0 ? 1.f : -1.f;
				// the wing turns about the body's long axis at the shoulder
				const FQuat Wing = Body * FQuat(FVector::ForwardVector, FMath::DegreesToRadians(-Sg * Flap));
				const FVector Mid = Place + Wing.RotateVector(FVector(Span * 0.03f, Sg * Span * 0.27f, Span * 0.02f));
				const bool bLast = f == FlockCentres.Num() - 1 && b == PerFlock - 1 && w == 1;
				Birds->UpdateInstanceTransform(i + 1 + w, FTransform(Wing, Mid, FVector(Span * 0.2f, Span * 0.46f, Span * 0.035f) / 100.f), true, false, false);
			}
		}
	}
}
