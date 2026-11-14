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
};

/**
 * The battlefield as a grid of GridCellSize cells over the playable area (Sovereign Feel > Grid).
 *
 * Built once when play starts: ground height per cell (downward traces against the terrain), blocked cells (water,
 * the hidden SRBlocker boxes over rocks / trunks / ruins), the gold veins. Buildings mark their footprint while they
 * stand. It answers three things:
 *  - placement: can a building of this type go here for this kingdom (flat, free, gapped, in territory, on a vein)?
 *  - paths: a route for one walker, or a shared search for a whole group (one Dijkstra from the goal; every member
 *    then follows the cheapest way down to it and string-pulls the result to a few corners),
 *  - space queries for the AI (nearest walkable point, free spot near a point for a building).
 * Units still do their own fine steering (separation, sliding along walls); the grid only plans the way round
 * lakes, cliffs, woods and buildings, which plain steering cannot.
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
	bool IsWater(const FIntPoint& C) const { return InGrid(C) && (Flags[Idx(C)] & FlagWater) != 0; }
	bool IsBuildingCell(const FIntPoint& C) const { return InGrid(C) && (Flags[Idx(C)] & FlagBuilding) != 0; }
	bool IsStaticBlocked(const FIntPoint& C) const { return !InGrid(C) || (Flags[Idx(C)] & FlagBlocked) != 0; }
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

	// ---- paths ----
	/**
	 * Routes for a group to one goal: OutPaths[i] are the corners walker i should visit (the goal itself is NOT
	 * appended; the caller adds each walker's own formation slot). False if the goal cannot be reached at all.
	 * One search serves the whole group.
	 */
	bool FindGroupPaths(const TArray<FVector2D>& Starts, const FVector2D& Goal, TArray<TArray<FVector2D>>& OutPaths);
	/** A single walker's corners to Goal (Goal appended). Straight line when nothing is in the way. */
	bool FindPath(const FVector2D& From, const FVector2D& Goal, TArray<FVector2D>& OutPath);
	/** Can one walk in a straight line from A to B (no blocked cell, no ledge taller than a step)? */
	bool CanWalkStraight(const FVector2D& A, const FVector2D& B) const;
	/** The walkable point nearest to P (P itself if it is walkable). */
	FVector2D NearestWalkable(const FVector2D& P, int32 MaxRing = 12) const;

	void DebugDraw() const;

	static constexpr uint8 FlagBlocked = 1;   // rock, trunk, ruin, water, off the world
	static constexpr uint8 FlagWater = 2;
	static constexpr uint8 FlagBuilding = 4;
	static constexpr uint8 FlagVein = 8;
	static constexpr uint8 FlagNearWall = 16; // next to something blocked: walkable, but paths avoid it

private:
	int32 Idx(const FIntPoint& C) const { return C.Y * Dim + C.X; }
	FIntPoint FromIdx(int32 I) const { return FIntPoint(I % Dim, I / Dim); }
	bool CanStep(int32 From, int32 To) const;
	void RefreshNearWall(const FIntPoint& Min, const FIntPoint& Max);
	void FootprintCells(const FVector& Location, const FVector2D& Min, const FVector2D& Max, FIntPoint& OutMin, FIntPoint& OutMax) const;
	/** Dijkstra outward from Goal until every start is settled (or the budget runs out). Fills Cost / Next. */
	bool Flood(const FIntPoint& Goal, const TArray<FIntPoint>& Starts);
	void StringPull(const TArray<FIntPoint>& Cells, TArray<FVector2D>& Out) const;

	int32 Dim = 0;
	float Cell = 100.f;
	FVector2D Origin = FVector2D::ZeroVector;
	TArray<float> Heights;
	TArray<uint8> Flags;
	TArray<FSRVein> Veins;

	// search scratch, reused between searches (Stamp avoids clearing it every time)
	TArray<float> Cost;
	TArray<int32> Next;
	TArray<uint32> Seen;
	uint32 Stamp = 0;

	mutable TArray<TArray<FVector2D>> DebugPaths;
};
