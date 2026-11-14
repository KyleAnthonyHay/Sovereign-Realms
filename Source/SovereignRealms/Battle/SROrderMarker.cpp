// Copyright Sovereign Realms.

#include "Battle/SROrderMarker.h"
#include "Common/SRRingComponent.h"
#include "Common/SRFeelSettings.h"
#include "Engine/World.h"

ASROrderMarker::ASROrderMarker()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	OuterRing = CreateDefaultSubobject<USRRingComponent>(TEXT("OuterRing"));
	OuterRing->SetupAttachment(GetRootComponent());
	InnerRing = CreateDefaultSubobject<USRRingComponent>(TEXT("InnerRing"));
	InnerRing->SetupAttachment(GetRootComponent());
}

ASROrderMarker* ASROrderMarker::SpawnMarker(UWorld* World, const FVector& GroundPoint, const FLinearColor& InColor)
{
	ASROrderMarker* Marker = World->SpawnActor<ASROrderMarker>(GroundPoint + FVector(0, 0, 4), FRotator::ZeroRotator);
	if (Marker)
	{
		const float R = USRFeelSettings::Get().MarkerRadius;
		Marker->Color = InColor;
		Marker->OuterRing->BuildRing(R * 0.80f, R);
		Marker->InnerRing->BuildRing(R * 0.10f, R * 0.24f);
		Marker->Tick(0.f);
	}
	return Marker;
}

void ASROrderMarker::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	const float Life = FMath::Max(USRFeelSettings::Get().MarkerLifetime, 0.05f);
	Age += DeltaSeconds;
	const float T = FMath::Clamp(Age / Life, 0.f, 1.f);

	// Outer ring: collapses fast then slows (ease-out), and winks out over the last quarter.
	const float U = 1.f - T;
	const float Shrink = 1.f - U * U * U;
	const float Vanish = T > 0.75f ? 1.f - (T - 0.75f) / 0.25f : 1.f;
	const float OuterScale = FMath::Max(FMath::Lerp(1.f, 0.30f, Shrink) * Vanish, 0.001f);
	OuterRing->SetRelativeScale3D(FVector(OuterScale, OuterScale, 1.f));
	OuterRing->SetRingColor(Color, U);

	// Centre dot: pops up with one pulse so the exact destination is unmistakable.
	const float Pulse = FMath::Sin(FMath::Min(T * 1.6f, 1.f) * PI);
	const float InnerScale = FMath::Max((0.6f + 0.9f * Pulse) * Vanish, 0.001f);
	InnerRing->SetRelativeScale3D(FVector(InnerScale, InnerScale, 1.f));
	InnerRing->SetRingColor(Color, U);

	if (T >= 1.f) { Destroy(); }
}
