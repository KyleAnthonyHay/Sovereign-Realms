// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "SRGridSubsystem.generated.h"

class ASRBuilding;

/** A gold vein: the only kind of place a mine can stand. Found in the level as the SM_GoldVein outcrops. */
struct FSRVein
{
	FVector2D Pos = FVector2D::ZeroVector;
	float Z = 0.f;
	TWeakObjectPtr<ASRBuilding> Mine;   // the mine standing on it (or being built), if any
};

/** An old ruin a tower can be raised on (found in the level by its tag). Two kinds:
 *  - a relic (an actor tagged SRRelic): an ancient ruin, wherever the map sets one (a broken tower, a stone circle;
 *    the actors tagged SRRelicPart round it are its stones): only a Relic Tower goes there, and only there;
 *  - a ruined tower (tagged SRRuinTower): a Watchtower raised on it snaps onto it and costs less (RuinRepairCost).
 * (A level with neither tag falls back to the terraced map's rule: mesh names, and height for which is a relic.) */
struct FSRRelic
{
	FVector2D Pos = FVector2D::ZeroVector;
	float Z = 0.f;
	bool bRelic = true;
	TArray<TWeakObjectPtr<AActor>> Ruins;   // its stones: hidden while a tower stands there
	TWeakObjectPtr<ASRBuilding> Tower;      // the tower raised on it (or going up), if any
};

/** Result of asking "can this building go here?" (also what the placement overlay draws). */
struct FSRPlacement
{
	bool bValid = false;
	/** Where the actor goes (its origin; the footprint is laid out round it in local space, yaw 0). */
	FVector Location = FVector::ZeroVector;
	/** Why not, for the HUD ("Must be built on a gold vein", "Ground is too uneven", ...). Empty when valid. */
	FText Reason;
	/** The footprint's cells and whether each one is fine. */
	TArray<FIntPoint> Cells;
	TArray<bool> CellOk;
	int32 VeinIndex = INDEX_NONE;
	int32 RelicIndex = INDEX_NONE;
	/** Outside the castle's building zone: only a Builder can raise it (it waits for one). */
	bool bNeedsBuilder = false;
};

/**
 * The battlefield as a grid of GridCellSize cells over the playable area (Sovereign Feel > Grid).
 *
 * Built once when play starts: ground height per cell (downward traces against the terrain, over the heights the
 * level's ASRMapInfo gives), blocked cells (deep water: where an SRWater sheet lies more than WadeDepth above the
 * ground, at whatever height that is; the hidden SRBlocker boxes over rocks / trunks / ruins; and every cell a
 * mountainside, a bank or a crag cuts through: a cell is open only if all of it is), the gold veins, the old ruins
 * (tagged SRRelic / SRRuinTower). Buildings mark their footprint while they stand: every cell they
 * touch. The grid is the one truth for where troops can go; it answers three things:
 *  - placement: can a building of this type go here for this kingdom (flat, free, gapped, in territory, on a vein)?
 *  - paths: a route for one walker, or a shared search for a whole group (one Dijkstra from the goal; every member
 *    then follows the cheapest way down to it and string-pulls the result to a few corners),
 *  - space queries for the AI (nearest walkable point, free spot near a point for a building).
 * Routes keep a cell clear of walls wherever there is room (straightened only through open cells), so a walker
 * following one does not rub along a cliff. Units still do their own fine steering (separation, sliding along
 * walls) and ask for a fresh route when they get stuck; the grid plans the way round lakes, cliffs, woods and
 * buildings, which plain steering cannot.
 */
UCLASS()
class SOVEREIGNREALMS_API USRGridSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static USRGridSubsystem* Get(const UObject* WorldContext);

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	/** (Re)samples the whole grid. Called at the start of play; cheap enough to call again after editing the map. */
	void Build();
	bool IsBuilt() const { return Dim > 0; }

	// ---- cells ----
	int32 GetDim() const { return Dim; }
	float GetCellSize() const { return Cell; }
	bool ToCell(const FVector2D& World, FIntPoint& Out) const;
	FIntPoint ToCellClamped(const FVector2D& World) const;
	FVector2D CellCentre(const FIntPoint& C) const { return Origin + (FVector2D(C) + 0.5f) * Cell; }
	bool InGrid(const FIntPoint& C) const { return C.X >= 0 && C.Y >= 0 && C.X < Dim && C.Y < Dim; }
	float CellHeight(const FIntPoint& C) const { return Heights[Idx(C)]; }
	bool IsWalkable(const FIntPoint& C) const { return InGrid(C) && (Flags[Idx(C)] & (FlagBlocked | FlagBuilding)) == 0; }
	/** Deep water (a wall). A ford, water no deeper than WadeDepth, is not: it is open ground. */
	bool IsWater(const FIntPoint& C) const { return InGrid(C) && (Flags[Idx(C)] & FlagWater) != 0; }
	/** Does the level have water sheets (actors tagged SRWater)? Without any, water is the ground under one fixed level. */
	bool UsesWaterSheets() const { return bWaterSheets; }
	bool IsBuildingCell(const FIntPoint& C) const { return InGrid(C) && (Flags[Idx(C)] & FlagBuilding) != 0; }
	bool IsStaticBlocked(const FIntPoint& C) const { return !InGrid(C) || (Flags[Idx(C)] & FlagBlocked) != 0; }
	/** Ground too steep to walk (a mountainside, a bank, a crag's edge) runs through the cell (so it is blocked, though
	 * part of it may be open ground). */
	bool IsEdge(const FIntPoint& C) const { return InGrid(C) && (Flags[Idx(C)] & FlagEdge) != 0; }
	/** Ground height under a point (nearest cell); false outside the grid. */
	bool HeightAt(const FVector2D& World, float& OutZ) const;

	// ---- buildings ----
	/** Marks (or clears) a building's footprint so paths go round it and nothing else is built there. */
	void SetFootprint(const ASRBuilding* Building, bool bOccupy);
	/** Can a building of this type be placed for Team with its origin near Want? Snaps to the grid (and onto a vein for a mine). */
	FSRPlacement CheckPlacement(ESRBuildingType Type, ESRTeam Team, const FVector2D& Want) const;
	/** AI: the nearest valid spot for Type within MaxRadius of Near (spiral search); false if there is none. */
	bool FindPlacementNear(ESRBuildingType Type, ESRTeam Team, const FVector2D& Near, float MaxRadius, FSRPlacement& Out) const;

	// ---- veins ----
	const TArray<FSRVein>& GetVeins() const { return Veins; }
	/** Nearest vein without a mine within Radius of Near, or INDEX_NONE. */
	int32 FindFreeVein(const FVector2D& Near, float Radius) const;
	void ClaimVein(int32 Index, ASRBuilding* Mine);
	void ReleaseVein(const ASRBuilding* Mine);

	// ---- relics ----
	const TArray<FSRRelic>& GetRelics() const { return Relics; }
	/** Nearest relic (bRelic) or ruined tower (!bRelic) with no tower on it within Radius of Near, or INDEX_NONE. */
	int32 FindFreeRelic(const FVector2D& Near, float Radius, bool bRelic = true) const;
	/** A Relic Tower now stands on it: the ruin is hidden. */
	void ClaimRelic(int32 Index, ASRBuilding* Tower);
	/** The Relic Tower is gone (cancelled, or its rubble cleared): the ruin stands again. */
	void ReleaseRelic(const ASRBuilding* Tower);
	/** A ruin with no tower on it near a point (either kind; Radius cm), or INDEX_NONE. */
	int32 FindFreeRuin(const FVector2D& Near, float Radius) const;
	/** What repairing ruin Index raises: a Relic Tower on a relic, a Watchtower on an old tower. */
	ESRBuildingType RuinBuildsInto(int32 Index) const { return Relics.IsValidIndex(Index) && Relics[Index].bRelic ? ESRBuildingType::RelicTower : ESRBuildingType::Tower; }

	// ---- paths ----
	/**
	 * Routes for a group to one goal: OutPaths[i] are the corners walker i should visit (the goal itself is NOT
	 * appended; the caller adds each walker's own formation slot). False if nobody can get anywhere near it.
	 * One search serves the whole group. OutGoals[i] (optional) is where walker i's route really ends: Goal, or, for
	 * a walker whose ground is cut off from it (the far bank, a ledge), the nearest point it can walk to.
	 */
	bool FindGroupPaths(const TArray<FVector2D>& Starts, const FVector2D& Goal, TArray<TArray<FVector2D>>& OutPaths, TArray<FVector2D>* OutGoals = nullptr);
	/** A single walker's corners to Goal (Goal, or the nearest point it can reach, appended). Straight line when nothing is in the way. */
	bool FindPath(const FVector2D& From, const FVector2D& Goal, TArray<FVector2D>& OutPath);
	/**
	 * A walker's corners to a building's walls: the search runs to every free cell round the footprint at once and
	 * takes the nearest by foot, so it ends on a side that can be reached (not the side facing the walker across a
	 * cliff). The last point stands Standoff cm off the wall. False if no side of it can be reached.
	 */
	bool FindPathToBuilding(const FVector2D& From, const ASRBuilding* Building, float Standoff, TArray<FVector2D>& OutPath);
	/**
	 * Can one walk in a straight line from A to B? Every cell the line touches must be open, no ledge taller than a
	 * step, no squeezing between two walls at a corner, and (except right at the two ends) not hard against a wall.
	 */
	bool CanWalkStraight(const FVector2D& A, const FVector2D& B) const;
	/**
	 * The walkable point nearest to P (P itself if it is walkable). With ReachableFrom, only ground that can be walked
	 * to from there counts: a click on a crag or across the river lands on the nearest spot the walker can get to.
	 */
	FVector2D NearestWalkable(const FVector2D& P, int32 MaxRing = 12, const FVector2D* ReachableFrom = nullptr) const;
	/** Is there a way on foot between the two points (same connected ground)? */
	bool CanReach(const FVector2D& From, const FVector2D& To) const;
	/**
	 * Formation slots made standable: each is kept if it can be walked to from Goal without leaving the formation's
	 * neighbourhood, otherwise moved to the nearest such ground (no slot across a cliff edge, in water or in a wall).
	 */
	void FitSlots(const FVector2D& Goal, TArray<FVector2D>& Slots) const;
	/** Bumped whenever a footprint goes down or comes up: routes planned before may be stale. */
	int32 GetRevision() const { return Revision; }

	void DebugDraw() const;
	/** Logs how the field is connected: both castle gates, every vein, every relic and old tower, and whether each can
	 * be walked to; and how much of the grid is deep water and steep ground. */
	void LogSelfCheck() const;

	static constexpr uint8 FlagBlocked = 1;   // rock, trunk, ruin, water, off the world
	static constexpr uint8 FlagWater = 2;
	static constexpr uint8 FlagBuilding = 4;
	static constexpr uint8 FlagVein = 8;
	static constexpr uint8 FlagNearWall = 16; // next to something blocked: walkable, but paths avoid it
	static constexpr uint8 FlagEdge = 32;     // steep ground (a slope, a bank, a crag) cuts through it (FlagBlocked is set too)

private:
	int32 Idx(const FIntPoint& C) const { return C.Y * Dim + C.X; }
	FIntPoint FromIdx(int32 I) const { return FIntPoint(I % Dim, I / Dim); }
	bool CanStep(int32 From, int32 To) const;
	void RefreshNearWall(const FIntPoint& Min, const FIntPoint& Max);
	void FootprintCells(const FVector& Location, const FVector2D& Min, const FVector2D& Max, FIntPoint& OutMin, FIntPoint& OutMax) const;
	/** A* outward from the goal cells (any of them will do) until every start is settled. Fills Cost / Next. */
	bool Flood(TConstArrayView<FIntPoint> Goals, const TArray<FIntPoint>& Starts);
	/** How a straight line may run: through any open cell; clear of walls except at its ends; or hard against a wall
	 * only in cells the searched route itself went through. */
	enum class ELineRule : uint8 { Any, Clear, Route };
	bool WalkLine(const FVector2D& A, const FVector2D& B, ELineRule Rule) const;
	void StringPull(const TArray<FIntPoint>& Cells, TArray<FVector2D>& Out);
	/** The walker's cell, or the nearest open one if it stands in a wall / on an edge. False: nothing near. */
	bool StartCell(const FVector2D& From, FIntPoint& OutCell, bool& bOutSnapped) const;
	/** Connected ground: Regions[cell] is the same number for every cell that can be walked between. */
	void EnsureRegions() const;

	int32 Dim = 0;
	float Cell = 100.f;
	FVector2D Origin = FVector2D::ZeroVector;
	TArray<float> Heights;
	TArray<uint8> Flags;
	TArray<FSRVein> Veins;
	TArray<FSRRelic> Relics;

	// search scratch, reused between searches (Stamp avoids clearing it every time)
	TArray<float> Cost;
	TArray<int32> Next;
	TArray<uint32> Seen;
	uint32 Stamp = 0;

	// which route cells the string-pull may hug a wall in (ELineRule::Route)
	TArray<uint32> RouteMark;
	uint32 RouteStamp = 0;

	mutable TArray<int32> Regions;   // 0 = not walkable
	mutable int32 RegionCount = 0;
	mutable bool bRegionsDirty = true;
	int32 Revision = 0;
	int32 EdgeCells = 0;
	int32 WaterCells = 0;
	bool bWaterSheets = false;

	mutable TArray<TArray<FVector2D>> DebugPaths;
};
