#pragma once

#include "CoreMinimal.h"
#include "Components/StaticMeshComponent.h"
#include "VLPartMesh.generated.h"

/**
 * One rigid part of a unit's figure (AVLKing::BuildFigure): a static mesh component whose scene proxy takes the
 * engine's APPROXIMATE occlusion, as every mesh that does not move does.
 *
 * A unit is 14 to 38 such parts. The engine gives every movable primitive that can be occluded its own hardware
 * occlusion query every frame: with the armies in the overview that was 11,000 queries (3.7 ms of GPU at 1080p, and
 * the render thread's time to issue and read them). With approximate occlusion a part that was seen last frame is
 * asked about again only now and then (one frame in ten or so, at random), while one that was hidden is still asked
 * about every frame, in a group with others: so a unit coming out from behind the mountain shows as soon as before,
 * and one going behind it is drawn a few frames longer. Nothing is seen differently.
 * (Never asking at all was tried and measured: the overview gained more, but with the massif in view the units
 * behind it were all drawn, 45 % more triangles and 2.5 ms more of the render thread. vl.Opt.PartOcclusion 2.)
 * Near the camera the parts are not asked about either way: a primitive that writes custom depth, as units do within
 * vl.Opt.UnitDepthFar, cannot be occluded (FStaticMeshSceneProxy::CanBeOccluded).
 */
UCLASS()
class SOVEREIGNREALMS_API UVLPartMeshComponent : public UStaticMeshComponent
{
	GENERATED_BODY()

public:
	virtual FPrimitiveSceneProxy* CreateStaticMeshSceneProxy(Nanite::FMaterialAudit& NaniteMaterials, bool bCreateNanite) override;
};
