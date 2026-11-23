#pragma once

#include "CoreMinimal.h"
#include "Components/PrimitiveComponent.h"
#include "VLArrowTrail.generated.h"

class UMaterialInterface;

/**
 * The streaks behind every arrow in flight (UVLArrows): ONE component on the arrows' actor, one dynamic mesh for all
 * of them, however many arrows there are (no component, no actor and no particle system per arrow).
 *
 * UVLArrows gives it, once a tick, a handful of points along the stretch each arrow has just flown (SetTrails); the
 * scene proxy turns every such run of points into a ribbon facing the camera, as wide as the arrow's shaft at the
 * arrow and tapering to nothing at its far end, never thinner on screen than a pixel and a half at its head (so the
 * streaks still read from the overview). It is an ordinary translucent mesh in the world: depth tested (a streak
 * behind a wall or a hill is hidden) and drawn in every build, Shipping too (nothing of it is debug drawing).
 */
UCLASS()
class SOVEREIGNREALMS_API UVLArrowTrailComponent : public UPrimitiveComponent
{
	GENERATED_BODY()

public:
	UVLArrowTrailComponent();

	/** A point of a streak: where (relative to the Origin given with it), and how wide the ribbon is there (0..1 of the head's). */
	struct FPoint
	{
		FVector3f At = FVector3f::ZeroVector;
		float Width = 0.f;
	};

	/** This frame's streaks: PerTrail points each, one after the other in Points (from the arrow back), relative to
	 *  Origin; HalfWidth: half the ribbon's width at its head, cm. An empty array: none. */
	void SetTrails(TArray<FPoint>&& Points, int32 PerTrail, const FVector& Origin, const FBox& WorldBox, float HalfWidth);
	void SetTrailMaterial(UMaterialInterface* InMaterial);
	bool HasTrails() const { return bAny; }

	virtual FPrimitiveSceneProxy* CreateSceneProxy() override;
	virtual FBoxSphereBounds CalcBounds(const FTransform& LocalToWorld) const override;
	virtual void GetUsedMaterials(TArray<UMaterialInterface*>& OutMaterials, bool bGetDebugMaterials = false) const override;

private:
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> TrailMaterial;

	FBox Box = FBox(FVector(-100.f), FVector(100.f));
	bool bAny = false;
};
