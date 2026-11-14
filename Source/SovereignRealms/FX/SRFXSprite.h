// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SRFXSprite.generated.h"

class UStaticMeshComponent;
class UMaterialInterface;

/** The battlefield's pixel-art effects (SourceArt/FX/fx_<name>.png, Tools/build_fx_materials.py). */
UENUM()
enum class ESRFX : uint8
{
	Fire,      // looping: a burning building
	Smoke,     // looping: smoke rising from a damaged or fallen building
	Dust,      // one-shot: hooves, a fall, a stone landing
	Debris,    // one-shot: chips from a struck building
	Impact     // one-shot: a catapult stone bursting on the ground
};

/**
 * One flipbook on a camera-facing card (like the troops), unlit and masked. One-shots play once and go; loops play
 * until Lifetime runs out (0 = until Stop() or the owner destroys it). The frame index reaches the material as custom
 * primitive data 0 (MI_FX_<Name>: FrameCount / Columns in the instance).
 */
UCLASS()
class SOVEREIGNREALMS_API ASRFXSprite : public AActor
{
	GENERATED_BODY()

public:
	ASRFXSprite();

	static ASRFXSprite* Spawn(UWorld* World, ESRFX Kind, const FVector& Location, float Scale = 1.f, float Lifetime = 0.f);
	/** Fades out over half a second and goes. */
	void Stop();

	virtual void Tick(float DeltaSeconds) override;

	struct FSpec { const TCHAR* Name; int32 Frames; float Fps; float WidthPx; float HeightPx; bool bLoop; float Rise; };
	static const FSpec& SpecFor(ESRFX Kind);

private:
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Card;
	ESRFX Kind = ESRFX::Dust;
	float Age = 0.f;
	float Lifetime = 0.f;
	float StopAt = -1.f;
	float Phase = 0.f;
	int32 ShownFrame = -1;
	float ShownFade = -1.f;
};
