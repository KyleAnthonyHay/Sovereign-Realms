#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "VLForest.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;
class UVLFootDust;

/** What an instanced kind of a forest is, for clearing. */
UENUM(BlueprintType)
enum class EVLForestPart : uint8
{
	/** Bushes, flowers, grass: taken away where a building's footprint covers them. */
	Undergrowth,
	/** A tree's trunk (it collides: the path grid is sampled again where one goes). */
	Trunk,
	/** A tree's crown (same origin, turn and scale as its trunk, so the two always go together). */
	Crown,
};

USTRUCT(BlueprintType)
struct FVLForestKind
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Voxel|Forest")
	TObjectPtr<UHierarchicalInstancedStaticMeshComponent> Component;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Voxel|Forest")
	EVLForestPart Part = EVLForestPart::Undergrowth;

	/** How far one instance reaches from its origin at scale 1, cm: a tree is cleared when a footprint (plus the
	 *  caller's margin) comes within this of its trunk. The same for a tree's trunk and its crown. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Voxel|Forest")
	float Reach = 0.f;
};

/**
 * A level's trees and undergrowth as instanced components: one hierarchical instanced static mesh component per
 * mesh (a tree is two: SM_Tree2_<k>_Trunk, which collides, and SM_Tree2_<k>_Leaves, which does not), instead of an
 * actor each. The level builder (Tools/ue/build_realm.py) fills it with AddKind; the components are saved with the
 * level. Far instances are culled per kind (CullDistance), and the tree meshes carry a second level of detail.
 *
 * Clearing, for buildings: ClearTrees takes away every tree whose trunk stands within its Reach (plus a margin) of a
 * footprint: the trunk, the crown and with them the shadow they cast; and the undergrowth inside the footprint. The
 * path grid is sampled again where trunks stood (UVLGrid::RebuildArea), so units can walk there at once; puffs of
 * dust mark the place. Returns the number of trees taken. Console: vl.ClearTrees.
 */
UCLASS()
class VOXELLAB_API AVLForest : public AActor
{
	GENERATED_BODY()

public:
	AVLForest();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/**
	 * Adds one mesh's instances (world transforms) as a component of this actor. Editor time: the level builder's.
	 * CullDistance: instances further than this from the view are not drawn (cm; 0: always drawn).
	 */
	UFUNCTION(BlueprintCallable, Category = "Voxel|Forest")
	UHierarchicalInstancedStaticMeshComponent* AddKind(UStaticMesh* Mesh, const TArray<FTransform>& Instances, EVLForestPart Part, float Reach,
		bool bCollide, bool bCastShadow, float CullDistance);

	/** Number of instances of a part in every forest of the world (trees: count the trunks). */
	UFUNCTION(BlueprintCallable, Category = "Voxel|Forest", meta = (WorldContext = "WorldContext"))
	static int32 CountInstances(const UObject* WorldContext, EVLForestPart Part);

	/**
	 * Clears the trees that stand in or against a footprint: a rectangle of half extents HalfExtent round Centre,
	 * turned YawDegrees about Z (world cm). A tree goes if its trunk is within Margin + its Reach of the rectangle;
	 * undergrowth goes if it is inside it. bDryRun: only count. Returns the number of trees.
	 */
	UFUNCTION(BlueprintCallable, Category = "Voxel|Forest", meta = (WorldContext = "WorldContext"))
	static int32 ClearTrees(const UObject* WorldContext, FVector2D Centre, FVector2D HalfExtent, float YawDegrees = 0.f, float Margin = 150.f,
		bool bPoof = true, bool bDryRun = false);

	/**
	 * ClearTrees for a caller that samples the path grid again itself (a building being laid: UVLGrid::RebuildAreas does
	 * the trunks' ground and the footprint in one go): OutChanged gets the ground where trunks stood (not valid: none
	 * went) and the grid is left alone.
	 */
	static int32 ClearTreesDeferred(const UObject* WorldContext, FVector2D Centre, FVector2D HalfExtent, float YawDegrees, float Margin, bool bPoof, FBox2D& OutChanged);
	static int32 ClearTreesAroundDeferred(const AActor* Building, float Margin, bool bPoof, FBox2D& OutChanged);

	/**
	 * How many trees ClearTrees would take (the same test, the trunks only): nothing is changed, logged or allocated.
	 * The placement ghost asks this every time it moves (UVLConstruction::CheckPlacement).
	 */
	static int32 CountTrees(const UObject* WorldContext, FVector2D Centre, FVector2D HalfExtent, float YawDegrees = 0.f, float Margin = 150.f);

	/** The same for an axis-aligned footprint. */
	static int32 ClearTreesIn(const UObject* WorldContext, const FBox2D& Footprint, float Margin = 150.f, bool bPoof = true, bool bDryRun = false);

	/** The same for a placed building: its mesh's own bounds, where and as it stands. */
	UFUNCTION(BlueprintCallable, Category = "Voxel|Forest")
	static int32 ClearTreesAround(const AActor* Building, float Margin = 150.f, bool bPoof = true, bool bDryRun = false);

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Voxel|Forest")
	TArray<FVLForestKind> Kinds;

private:
	/** One forest's share of ClearTrees: adds to the counts, to the box whose grid cells changed, to the puffs. */
	void ClearIn(const FVector2D& Centre, const FVector2D& HalfExtent, float YawDegrees, float Margin, bool bDryRun,
		int32& Trees, int32& Crowns, int32& Plants, FBox2D& Changed, TArray<FVector4>* Poofs);
	void Poof(const TArray<FVector4>& At);
	static int32 ClearTreesImpl(const UObject* WorldContext, FVector2D Centre, FVector2D HalfExtent, float YawDegrees, float Margin, bool bPoof, bool bDryRun, FBox2D* OutChanged);
	static bool FootprintOf(const AActor* Building, FVector2D& OutCentre, FVector2D& OutHalf, float& OutYaw);

	/** Where the trunks stand (and how big each is), kind by kind, for CountTrees: read from the components once and
	 *  again whenever instances have gone. */
	struct FTrunk
	{
		double X = 0.0, Y = 0.0;
		float Scale = 1.f;
	};
	struct FTrunkKind
	{
		float Reach = 0.f;
		int32 Instances = 0;        // the component's count when this was read
		TArray<FTrunk> At;
	};
	const TArray<FTrunkKind>& Trunks();
	TArray<FTrunkKind> TrunkCache;
	bool bTrunkCache = false;

	UPROPERTY(Transient)
	TObjectPtr<UVLFootDust> Dust;
	float DustUntil = 0.f;
};
