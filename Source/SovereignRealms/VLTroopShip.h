#pragma once

#include "CoreMinimal.h"
#include "CollisionQueryParams.h"
#include "GameFramework/Actor.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLTroopShip.generated.h"

class AVLKing;
class APlayerController;
class UStaticMeshComponent;

/** A place a troop ship can lie with its side to the land and its gangplank out. */
struct FVLBerth
{
	FVector2D At = FVector2D::ZeroVector;       // the ship's middle (a cell of the chart off the shore: UVLFleet::Snug brings it alongside)
	float Yaw = 0.f;
	FVector2D Shore = FVector2D::ZeroVector;    // toward the land
	FVector Land = FVector::ZeroVector;         // the ground its gangplank goes to
};

/**
 * The troop ship (SM_TroopShip, Tools/blender/assets/troopship.py): a war cog that takes a platoon and the heroes
 * aboard at a quay or a shore, carries them across the water and puts them ashore again.
 *
 *   BOARD    select troops, right click the ship (the hero view: Alt + click it): they walk to the foot of its
 *            gangplank and go up it one after another. Aboard a unit is garrisoned in the ship (AVLKing::GarrisonIn,
 *            as on a watch tower's lookout): it stands at a place of its own on the deck, rides with the ship, takes
 *            no orders and chases nobody; archers aboard shoot from the deck, and nobody with a sword reaches them.
 *            Room: Capacity troops (the main deck and the forecastle) and the heroes (King David, Jonathan) on the
 *            stern castle, who take no soldier's place.
 *   SAIL     click the ship (it is the selection), right click the water (or the minimap): it sails there round the
 *            land (its own chart of the water, UVLFleet), never over ground, rocks, a pier or under a bridge.
 *            Shift + right click: one more point of its course, sailed in order (the troops' Shift pathway).
 *            P, then a click on the water: it patrols between where it lies and there, round and round (Shift +
 *            click: one more point of the loop), until its next order: the troops' Patrol, never onto land.
 *   DOCK     within DockRange of a place it can lie alongside (a quay or a shore with ground a gangplank reaches) a
 *            dock button shows over that place and in its panel: a click and it swings its side to the land and
 *            slides into the berth in one quick eased move, and the gangplank drops. A right click on a shore or a
 *            quay sails there and docks the same way.
 *   UNLOAD   docked (LANDED: the gangplank is out), the panel's Unload button (or an order to troops aboard: they
 *            step ashore and go) sends everyone down the gangplank; they form up on the shore. At sea nobody leaves.
 *
 * It is no building and nobody's target: it cannot be attacked or sunk (the units aboard can be shot at).
 *
 * Where ships come from (UVLFleet, when play starts):
 *   - an actor tagged "TroopShip" (the player's), "TroopShip:0" or "TroopShip:1" (that team's): a ship takes its
 *     place (its location is the ship's pivot, on the waterline; its yaw the ship's, bow along +X). If the actor is
 *     a static mesh actor it is hidden: a level places SM_TroopShip itself there, so the ship shows in the editor.
 *   - a level without any, with ships moored at its piers (actors tagged "Moored": Realm v2, v3): a troop ship at a
 *     berth by each of them, alongside the nearest quay, its side to the land. Whose it is: the moored ship's cloth.
 * Console: vl.Ship (see VLTroopShip.cpp).
 */
UCLASS()
class SOVEREIGNREALMS_API AVLTroopShip : public AActor
{
	GENERATED_BODY()

public:
	AVLTroopShip();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Whose it is (UVLBattle::Player / Enemy): the enemy's has red cloth. */
	void SetTeam(int32 InTeam);
	int32 GetTeam() const { return Team; }

	// ---- the troops
	/** Soldiers it takes (the heroes stand on the stern castle and take none of these). */
	static int32 Capacity();
	/** Those of Units of its side that it has room for walk to its gangplank and go aboard; the others stay. Returns
	 *  how many set out. Not landed: nobody (an alert says so). */
	int32 OrderBoard(const TArray<AVLKing*>& Units, bool bRun);
	/** Everyone aboard goes down the gangplank and forms up on the shore. Returns how many; 0 if it is not landed. */
	int32 Unload();
	/** One unit off it at once (UVLCommand::Leave: an order to a unit aboard, or its death). Not landed: it stays. */
	void Disembark(AVLKing* Unit);
	/** Puts a unit straight on a place of the deck (tests, vl.Ship put). False: no room. */
	bool PutAboard(AVLKing* Unit);
	void GetAboard(TArray<AVLKing*>& Out) const;
	int32 NumAboard() const;
	/** On their way to it (a place kept for each). */
	int32 NumComing() const;
	/** The ship a unit is aboard, or null. */
	static AVLTroopShip* Of(const AVLKing* Unit);

	// ---- sailing
	/** Sails to that point of the water, or as near that point of the land as the water lets it (and docks there).
	 *  bQueue: after the course it is on (one more point of it). False: no way. */
	bool SailTo(const FVector& Point, bool bQueue = false);
	/** Patrols between where it lies and that point of the water; bExtend: one more point of the patrol it is on. */
	bool OrderPatrol(const FVector& Point, bool bExtend);
	void StopSailing();
	bool IsSailing() const { return Path.Num() > 0 || bDocking; }
	bool IsPatrolling() const { return bPatrol; }
	/** Its course for the interface: where it is, the corners and points still to sail (a patrol: its loop). */
	void GetCourse(TArray<FVector>& Out, bool& bOutLoop) const;
	/** Lying still with ground a gangplank reaches: its gangplank is out. */
	bool IsLanded() const { return bLanded; }
	/** The foot of the gangplank, on the ground (valid while landed). */
	FVector GetLandPoint() const { return LandPoint; }
	/** "Moored", "Under sail", "On patrol", "At sea": for the panel. */
	FString DescribeState() const;
	/** Moves it there at once (a level's mooring, tests). */
	void Moor(const FVector& At, float Yaw);

	// ---- docking
	/** Within DockRange of a berth (and not docked): the dock button shows. */
	bool CanDock() const { return bCanDock && !bLanded && !bDocking; }
	/** The ground the berth's gangplank would go to (while CanDock). */
	FVector GetDockPoint() const { return DockBerth.Land; }
	/** Swings round and slides into the berth in range, its side to the land, in one eased move. False: none. */
	bool Dock();
	bool IsDocking() const { return bDocking; }
	/** Seconds the last docking move took (0: none yet). */
	float GetLastDockSeconds() const { return LastDockSeconds; }
	/** Is that point within Margin of its hull (another ship's berth must stay clear of it)? */
	bool HullNear(const FVector2D& P, float Margin) const;
	/** cm from the ship's middle to a berth's: the dock button's range. */
	static constexpr float DockRange = 3000.f;

	// ---- the player's pointer
	/** The ship the ray meets within MaxDist (its hull or its sail), or null. */
	static AVLTroopShip* Pick(const UWorld* World, const FVector& Origin, const FVector& Dir, float MaxDist);
	/** The player's ship that is the selection (no units selected), or null. */
	static AVLTroopShip* Selected(const UObject* WorldContext);
	/** A right click in the world with a ship of his side selected and no units: it sails to the water under the
	 *  pointer (the land there: to its shore). bQueue (Shift): one more point of its course. True: the click was the ship's. */
	static bool OrderFromView(AVLKing* Commander, APlayerController* PC, const FVector2D& Point, const FVector& Ground, bool bQueue);
	/** The same from the minimap: a point of the world. */
	static bool OrderFromMap(const UObject* WorldContext, const FVector& At, bool bQueue);
	/** A left click with Patrol armed (P) and a ship selected: its patrol's point (bShift: one more). True: the ship's. */
	static bool PatrolClick(AVLKing* Commander, APlayerController* PC, const FVector2D& Point, bool bShift);
	/** Takes out of Units those aboard a ship that is not landed: they cannot leave it (an alert for the player's). */
	static void HoldAboard(TArray<AVLKing*>& Units);

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<UStaticMeshComponent> Hull;

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<UStaticMeshComponent> Plank;

	/** cm a second under sail, and how fast it gathers and loses way. */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	float Cruise = 900.f;

	UPROPERTY(EditAnywhere, Category = "Voxel")
	float Accel = 260.f;

	/** Degrees a second it turns under way. */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	float TurnRate = 26.f;

	/** The longest gangplank (cm, from the entry port to the ground). */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	float PlankReach = 620.f;

	/** Seconds the docking move takes: the least (a berth right beside it) and the most (from the edge of DockRange, turning right round). */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	float DockSecondsMin = 1.0f;

	UPROPERTY(EditAnywhere, Category = "Voxel")
	float DockSecondsMax = 1.5f;

private:
	struct FPlace
	{
		FVector Local;                      // the ship's own space (cm), the deck under the feet
		uint8 Kind = 0;                     // 0 the main deck, 1 the forecastle (archers first), 2 the stern castle (heroes)
		TWeakObjectPtr<AVLKing> Unit;       // who stands there, or is on the way to it
		bool bAboard = false;
	};
	/** A unit on the gangplank: up it to its place, or down it to the shore. */
	struct FWalk
	{
		TWeakObjectPtr<AVLKing> Unit;
		int32 Place = INDEX_NONE;
		bool bOff = false;
		float Delay = 0.f;                  // seconds before it sets out
		float T = 0.f;                      // cm walked
		FVector Shore = FVector::ZeroVector;    // where it steps on (its own feet) / off (the gangplank's foot)
		FVector Muster = FVector::ZeroVector;   // off: where it goes once ashore
	};
	TArray<FPlace> Places;
	TArray<FWalk> Walks;
	int32 Team = 0;
	float SinceBoard = 0.f;         // seconds since a unit last set foot on the gangplank

	int32 FreePlace(const AVLKing* Unit) const;
	int32 PlaceOf(const AVLKing* Unit) const;
	bool IsHero(const AVLKing* Unit) const;
	FVector PlaceWorld(int32 Place) const;
	void Seat(AVLKing* Unit, int32 Place);          // inert, on its place, riding with the hull
	void Release(AVLKing* Unit, const FVector& Feet, float Yaw);    // a unit of the ground again, standing there
	void TickTroops(float Dt);
	void TickWalks(float Dt);
	void EndWalks();                                // those on the gangplank: aboard at once, or back on the shore
	FVector GateWorld(int32 Side) const;
	/** The way a unit walks between the shore and its place: the shore, the gangplank's foot, the entry port, the place. */
	void WalkPoints(const FWalk& W, FVector Out[4]) const;

	// sailing: the leg under way (Path: its corners), the points after it, or a patrol's loop
	TArray<FVector2D> Path;
	TArray<FVector> Waypoints;
	TArray<FVector> PatrolPts;
	int32 PatrolNext = 0;
	bool bPatrol = false;
	bool bLegStop = true;               // the leg ends its course: it comes to rest at its end
	bool bLegDock = false;              // ... by land: it docks there
	bool bCastingOff = false;           // from a berth hard by the shore: sideways to open water first, as it lies
	FVector LegTarget = FVector::ZeroVector;
	float Speed = 0.f;
	float SeaZ = 0.f;
	float BobClock = 0.f;
	bool StartLeg(const FVector& Point, bool bLast);
	void ClearCourse();
	void TickSailing(float Dt);
	void Arrive();
	void FinishSailing();

	// docking: the berth in range (looked for a few times a second), and the move into it
	bool bCanDock = false;
	FVLBerth DockBerth;
	float DockCheck = 0.f;
	bool bDocking = false;
	float DockT = 0.f, DockDur = 1.f, DockBulge = 0.f;
	FVector2D DockFrom = FVector2D::ZeroVector, DockTo = FVector2D::ZeroVector, DockShore = FVector2D::ZeroVector;
	float DockFromYaw = 0.f, DockToYaw = 0.f;
	float LastDockSeconds = 0.f;
	float SettleClock = 100.f;          // seconds since it came to rest in a berth (the bob as it settles)
	float PlankClock = 100.f;           // seconds since the gangplank began to drop
	void StartDock(const FVLBerth& Berth);
	void TickDock(float Dt);

	// the landing
	bool bLanded = false;
	FVector LandPoint = FVector::ZeroVector;
	int32 LandSide = 1;
	float LandCheck = 0.f;
	void UpdateLanding();
	void PlacePlank();

	friend class UVLFleet;
};

/**
 * The ships of a level, and the chart they sail by.
 *
 * The chart: the level sampled once on 2.5 m cells from above. A cell is water a ship floats in if a water sheet
 * (an actor tagged Water) lies there at the ships' sea level and nothing stands in it or over it down to a ship's
 * draught: ground, rocks, a pier, a quay, a bridge. A ship's middle keeps to cells whose neighbours are all such
 * water (its half beam and a little), and routes are searched over those (A*, pulled straight).
 *
 * A berth (FindBerth): an open cell with land within 9 m lying straight along the hull, the whole hull in water and
 * clear of other ships, and ground of the path grid's main region within a gangplank's reach of the entry port on
 * that side, no more than 1.9 m under or 1.2 m over its sill.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLFleet : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLFleet* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	const TArray<TWeakObjectPtr<AVLTroopShip>>& GetShips() const { return Ships; }
	AVLTroopShip* SpawnShip(const FVector& At, float Yaw, int32 Team);

	/** The chart, made on first use for water at SeaZ. False: the level has no water there. */
	bool EnsureChart(float SeaZ);
	/** Open water for a ship's middle? */
	bool IsOpen(const FVector2D& P) const;
	/** Water a hull floats in (no clearance kept)? */
	bool IsWater(const FVector2D& P) const;
	/** The open cell nearest a point that a ship at From can sail to. False: none within Reach cm. */
	bool NearestOpen(const FVector2D& From, const FVector2D& Point, float Reach, FVector2D& Out) const;
	/** Corners of a route over open water (the goal the last). False: no way. */
	bool FindRoute(const FVector2D& From, const FVector2D& To, TArray<FVector2D>& Out) const;
	/** The middle of the nearest cell within Reach that is not water (land, a quay), or false. */
	bool NearestLand(const FVector2D& P, float Reach, FVector2D& Out) const;
	/** The berth within Radius of Around that is nearest Prefer (see the class comment). For: the ship it is for
	 *  (the heading that turns it least is preferred; other ships' hulls are kept clear of), or null. */
	bool FindBerth(const FVector2D& Around, float Radius, const FVector2D& Prefer, const AVLTroopShip* For, FVLBerth& Out) const;
	/** Where a ship in that berth lies once it has come sideways to the land: the water beside its hull clear to SideGap. */
	FVector2D Snug(const FVLBerth& Berth) const;
	float GetSeaZ() const { return ChartSeaZ; }

private:
	void SpawnShips();
	bool ToCell(const FVector2D& P, FIntPoint& Out) const;
	FVector2D CellMid(const FIntPoint& C) const { return Origin + (FVector2D(C) + 0.5f) * CellSize; }
	int32 Idx(const FIntPoint& C) const { return C.Y * DimX + C.X; }
	bool LineOpen(const FVector2D& A, const FVector2D& B) const;
	int32 OpenCellNear(const FVector2D& P, int32 Rings, int32 Sea = 0) const;

	UPROPERTY(Transient)
	TArray<TWeakObjectPtr<AVLTroopShip>> Ships;
	bool bChartTried = false;
	float ChartSeaZ = 0.f;
	float CellSize = 250.f;
	int32 DimX = 0, DimY = 0;
	FVector2D Origin = FVector2D::ZeroVector;
	TArray<uint8> Water;        // per cell: 1 a hull floats here
	TArray<uint8> Open;         // per cell: 1 a ship's middle may be here
	TArray<int32> Sea;          // per open cell: which connected water it is part of (0: none)
	FCollisionQueryParams Probe;    // the chart's own trace: what a hull is kept clear of
};
