// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "ProceduralMeshComponent.h"
#include "SRRingComponent.generated.h"

class UMaterialInstanceDynamic;

/**
 * Flat ring (annulus) lying on the ground: selection ring, hover ring, order marker.
 * Geometry is generated so no mesh asset is needed. UV0 maps the ring's bounding
 * square to 0..1 (centre = 0.5,0.5) so a replacement material can do radial effects.
 * Material contract: see Docs/VISUAL_CONTRACT.md (M_SelectionRing).
 */
UCLASS()
class SOVEREIGNREALMS_API USRRingComponent : public UProceduralMeshComponent
{
	GENERATED_BODY()

public:
	USRRingComponent(const FObjectInitializer& ObjectInitializer);

	/** Builds the ring mesh and its dynamic material. Call once after registering. */
	void BuildRing(float InnerRadius, float OuterRadius, int32 Segments = 40);

	/** Builds a rounded-rectangle outline instead (a building's footprint). The line is Width thick, inside the given half extents. */
	void BuildRoundedRect(const FVector2D& HalfExtent, float CornerRadius, float Width, int32 CornerSegments = 6);

	void SetRingColor(const FLinearColor& Color, float Opacity = 1.f);

private:
	void FinishMesh(const TArray<FVector>& Verts, const TArray<FVector2D>& UVs, int32 Segments);

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> RingMID;
};
