#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLGrid.generated.h"

class UPrimitiveComponent;
struct FCollisionQueryParams;

/**
 * Where units can walk: the main game's battlefield grid (USRGridSubsystem) reimplemented for the voxel world.
 *
 * The level is sampled once when play starts, on CellSize cells. What is different from the main game is that the
 * voxel world has floors above floors (a bridge over a river bed, ground under an eave or a gate's beam, a tower's
 * platform), so a cell holds a short stack of NODES, one per floor a unit can stand on:
 *  - a floor is found by tracing down through the cell, again and again from under each surface met, until the
 *    terrain (actors tagged Ground) is reached;
 *  - it counts if there is air over it with headroom (a floor inside a solid building has none), if a unit's
 *    capsule fits there clear of everything taller than a step (walls, fences, trunks, the faces of cliffs), and if
 *    it is not under water (the meshes tagged Water are asked where their surface lies);
 *  - nodes of neighbouring cells are joined where the step between them is at most StepHeight (the 50 cm block
 *    of the voxel ground); a diagonal only where both cells beside it are joined too (no cutting corners).
 * Everything else is the main game's: regions of connected ground, one search outward from the goal that serves a
 * whole group, routes kept off walls where there is room and pulled straight to a few corners, clicks on a roof /
 * cliff / water taken to the nearest ground the walker can reach, formation slots moved onto standable ground.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLGrid : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLGrid* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	/**
	 * The level's collision contract, enforced when play starts (and before the grid samples the level), whatever
	 * the level file says. The builders set these on the placed components, but a static mesh component that still
	 * "uses default collision" takes the mesh asset's BlockAll back when the level is loaded again, which made the
	 * hidden walls stop clicks and arrows:
	 *  - tag Barrier, and every other hidden static mesh actor (the walls round the map's edge): block pawns only;
	 *  - tag Water: no collision for anyone (queries on the component itself still work: the grid asks it);
	 *  - tag Backdrop: no collision at all.
	 */
	static void ApplyLevelCollision(UWorld* World);
	/** Is this an actor no click, aim or shot should stop at (a hidden wall, the water, the backdrop)? */
	static bool IsUnseen(const AActor* Actor);

	/** Samples the level (once; Build() again after changing it). False: the level has no ground to sample. */
	bool EnsureBuilt();
	void Build();
	/**
	 * Samples a part of the level again (world XY, cm) after something that stood there has gone (trees cleared for
	 * a building: AVLForest::ClearTrees) or come: the cells' floors, their joins, the regions. Routes planned
	 * afterwards see it; node numbers handed out before stay valid, those of the area itself do not.
	 * Returns the number of cells sampled.
	 */
	int32 RebuildArea(const FBox2D& Area);
	/**
	 * The same for several areas at once (a building laid among trees: where the trunks stood and its own footprint):
	 * every cell of their union is sampled once, and the joins and the regions are worked out once for all of them.
	 */
	int32 RebuildAreas(TConstArrayView<FBox2D> Areas);
	/** Counts up whenever the grid is built or a part of it sampled again (what stands on the ground changed). */
	uint32 GetRevision() const { return Revision; }
	/** A number that is the same for two grids exactly when they are (cells, floors, joins, regions): vl.Opt.GridChecksum. */
	uint64 Checksum() const;
	bool IsBuilt() const { return Nodes.Num() > 0; }

	struct FNode
	{
		float Z = 0.f;
		int32 Cell = 0;
		int32 Region = 0;
		int32 Nb[8] = { -1, -1, -1, -1, -1, -1, -1, -1 };
		bool bNearWall = false;
	};

	int32 NumNodes() const { return Nodes.Num(); }
	FVector NodePos(int32 Node) const;
	int32 RegionOf(int32 Node) const { return Nodes.IsValidIndex(Node) ? Nodes[Node].Region : 0; }
	/** The biggest piece of connected ground: the town itself (not a roof, a ledge or a walled-in corner). */
	int32 MainRegion() const { return Main; }

	/** The node under a unit's feet: in its cell, the floor nearest in height (within MaxDz). INDEX_NONE: none. */
	int32 NodeAt(const FVector& Feet, float MaxDz = 130.f) const;
	/** The node nearest to a point: its own cell's if it has one (of Region, if given), else ring by ring outward. */
	int32 NearestNode(const FVector& Point, int32 MaxRing = 16, int32 Region = 0) const;

	/**
	 * Routes for a group to one goal, as the main game's FindGroupPaths: OutPaths[i] are the corners walker i visits
	 * (the goal itself is not appended: the caller adds each walker's own slot). OutGoals[i] is where its route ends:
	 * the goal, or for a walker cut off from it the nearest point its own ground comes to it.
	 */
	bool FindGroupPaths(const TArray<FVector>& Starts, const FVector& Goal, TArray<TArray<FVector>>& OutPaths, TArray<FVector>* OutGoals = nullptr);
	/** One walker's corners, the goal (or the nearest point it can reach) appended. */
	bool FindPath(const FVector& From, const FVector& Goal, TArray<FVector>& OutPath);
	/** Formation slots made standable: kept if they can be walked to from the goal nearby, else moved to such ground. */
	void FitSlots(const FVector& Goal, const TArray<FVector2D>& Slots, TArray<FVector>& Out) const;
	/** The water's surface over this point of the map (far below everything where there is none, or no grid). */
	float WaterLevelAt(const FVector& Point) const;
	/** Is this point under water (a unit that fell in is put back on land)? */
	bool Submerged(const FVector& Feet) const;

	/** Draws the nodes round a point for a while (green open, yellow beside a wall): vl.Grid. */
	void DebugDraw(const FVector& Around, float Radius, float Seconds) const;
	float GetCellSize() const { return Cell; }
	/** The ground the grid covers (the level's terrain), world XY. */
	FBox2D GetBounds() const { return FBox2D(Origin, Origin + FVector2D(float(DimX), float(DimY)) * Cell); }

	UPROPERTY(EditAnywhere, Category = "Voxel")
	float CellSize = 50.f;

	/** The tallest step a unit takes (AVLKing's MaxStepHeight). */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	float StepHeight = 58.f;

	/** A route pays this much more per cell hard against a wall, so it keeps its distance where there is room. */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	float WallPenalty = 1.5f;

private:
	/** One cell's floors, found as the class comment says, highest first into OutZ (room for MaxLayers); returns how
	 *  many. Reads the world and this grid only (it runs on worker threads: SampleCells). */
	int32 SampleFloors(UWorld* World, int32 C, const FCollisionQueryParams& Params, const TSet<const UPrimitiveComponent*>& Ground, float* OutZ, int32& Wet, int32& Tight, int32& Inside) const;
	/** The regions of connected ground, numbered from 1 in the order of each one's first node (dead nodes, Region -1,
	 *  stay out), and Main: the biggest. Returns how many; OutMainSize: the main one's nodes. */
	int32 LabelRegions(int32& OutMainSize);
	/** The cells Lo..Hi (those inside one of Only, if given) sampled row by row and their floors appended to Nodes in
	 *  cell order, First and Count set. The rows are sampled side by side on worker threads (vl.Opt.ParallelGrid) and
	 *  put together in order, so the grid is the same as one sampled cell after cell. */
	void SampleCells(UWorld* World, const FIntPoint& Lo, const FIntPoint& Hi, TConstArrayView<FIntRect> Only, const FCollisionQueryParams& Params,
		const TSet<const UPrimitiveComponent*>& Ground, int32& Wet, int32& Tight, int32& Inside);
	float SampleTop = 0.f, SampleBottom = 0.f;      // the heights a cell is traced between (Build's)
	bool ToCell(const FVector2D& P, FIntPoint& Out) const;
	FIntPoint ToCellClamped(const FVector2D& P) const;
	int32 CellIdx(const FIntPoint& C) const { return C.Y * DimX + C.X; }
	FIntPoint CellOf(int32 Node) const { const int32 C = Nodes[Node].Cell; return FIntPoint(C % DimX, C / DimX); }
	FVector2D CellCentre(const FIntPoint& C) const { return Origin + (FVector2D(C) + 0.5f) * Cell; }
	bool InGrid(const FIntPoint& C) const { return C.X >= 0 && C.Y >= 0 && C.X < DimX && C.Y < DimY; }
	bool Flood(TConstArrayView<int32> Goals, const TArray<int32>& Starts);
	bool FloodFast(TConstArrayView<int32> Goals, const TArray<int32>& Starts);
	void SyncSearchArrays();
	// (Windows pass, batch 1) the last one-walker searches: the corners StringPull gave between two nodes
	struct FRouteMemo
	{
		int32 From = INDEX_NONE, To = INDEX_NONE;
		bool bFound = false;
		TArray<FVector> Corners;
		uint64 Used = 0;
	};
	static constexpr int32 MemoSize = 96;
	TArray<FRouteMemo> Memo;
	uint64 MemoClock = 0;
	const FRouteMemo* FindMemo(int32 From, int32 To);
	void AddMemo(int32 From, int32 To, bool bFound, const TArray<FVector>& Corners);
	TArray<uint8> NearWall;     // per node: FNode::bNearWall, for the search's inner loop
	TArray<uint32> StartMark;   // per node: a start the running search has still to reach (== Stamp)
	enum class ELineRule : uint8 { Any, Clear, Route };
	bool WalkLine(int32 FromNode, const FVector2D& A, const FVector2D& B, int32 ToNode, ELineRule Rule) const;
	void StringPull(const TArray<int32>& Chain, TArray<FVector>& Out);

	bool bTried = false;
	int32 DimX = 0, DimY = 0;
	float Cell = 50.f;
	FVector2D Origin = FVector2D::ZeroVector;
	TArray<FNode> Nodes;
	TArray<int32> First;       // per cell: its first node (they are stored highest first)
	TArray<uint8> Count;
	TArray<float> WaterZ;      // per cell: the water's surface, or far below
	int32 Main = 0;
	uint32 Revision = 0;

	TArray<float> Cost;
	TArray<int32> Next;
	TArray<uint32> Seen;
	uint32 Stamp = 0;
	TArray<uint32> RouteMark;
	uint32 RouteStamp = 0;
};
