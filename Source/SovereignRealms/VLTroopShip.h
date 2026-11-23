#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLTroopShip.generated.h"

class AVLKing;
class APlayerController;
class UStaticMeshComponent;

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
 *   SAIL     click the ship (it is the selection), right click the water: it sails there round the land (its own
 *            chart of the water, UVLFleet), never over ground, rocks, a pier or under a bridge. Right click the land,
 *            a quay or a pier: it goes as near as the water lets it, turns its side to the shore and comes alongside.
 *   UNLOAD   where it lies within a gangplank's reach of ground units can walk on (LANDED: the gangplank is out), the
 *            panel's Unload button (or an order to troops aboard: they step ashore and go) sends everyone down the
 *            gangplank; they form up on the shore. At sea nobody leaves it.
 *
 * It is no building and nobody's target: it cannot be attacked or sunk (the units aboard can be shot at).
 *
 * Where ships come from (UVLFleet, when play starts):
 *   - an actor tagged "TroopShip" (the player's), "TroopShip:0" or "TroopShip:1" (that team's): a ship takes its
 *     place (its location is the ship's pivot, on the waterline; its yaw the ship's, bow along +X). If the actor is
 *     a static mesh actor it is hidden: a level places SM_TroopShip itself there, so the ship shows in the editor.
 *   - a level without any, with ships moored at its piers (actors tagged "Moored": Realm v2): a troop ship at a berth
 *     by each of them, alongside the nearest quay, its side to the land. Whose it is: the moored ship's cloth.
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
	/** Sails to that point of the water, or as near that point of the land as the water lets it. False: no way. */
	bool SailTo(const FVector& Point);
	void StopSailing();
	bool IsSailing() const { return Path.Num() > 0 || bAligning || bComingAlongside; }
	/** Within a gangplank's reach of ground the units can walk on (and lying still). */
	bool IsLanded() const { return bLanded; }
	/** The foot of the gangplank, on the ground (valid while landed). */
	FVector GetLandPoint() const { return LandPoint; }
	/** "Moored at the shore", "Sailing", "At sea": for the panel. */
	FString DescribeState() const;
	/** Moves it there at once (a level's mooring, tests). */
	void Moor(const FVector& At, float Yaw);

	// ---- the player's pointer
	/** The ship the ray meets within MaxDist (its hull or its sail), or null. */
	static AVLTroopShip* Pick(const UWorld* World, const FVector& Origin, const FVector& Dir, float MaxDist);
	/** A right click in the world with a ship of his side selected and no units: it sails to the water under the
	 *  pointer (the land there: to its shore). True if the click was the ship's. */
	static bool OrderFromView(AVLKing* Commander, APlayerController* PC, const FVector2D& Point, const FVector& Ground);
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

	/** Degrees a second it turns (under way; lying still to come alongside). */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	float TurnRate = 26.f;

	/** The longest gangplank (cm, from the entry port to the ground). */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	float PlankReach = 620.f;

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
	FVector GateWorld(int32 Side) const;
	/** The way a unit walks between the shore and its place: the shore, the gangplank's foot, the entry port, the place. */
	void WalkPoints(const FWalk& W, FVector Out[4]) const;

	// sailing
	TArray<FVector2D> Path;
	float Speed = 0.f;
	bool bAligning = false;
	bool bComingAlongside = false;
	bool bCastingOff = false;           // from a berth hard by the shore: sideways to open water first, as it lies
	float AlignYaw = 0.f;
	FVector2D ShoreDir = FVector2D::ZeroVector;     // toward the land it comes alongside
	float Slid = 0.f;
	float SeaZ = 0.f;
	float BobClock = 0.f;
	void TickSailing(float Dt);
	void Arrive();
	void FinishSailing();

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
	float GetSeaZ() const { return ChartSeaZ; }

private:
	void SpawnShips();
	bool FindBerth(const AActor* Moored, FVector& OutAt, float& OutYaw, FVector2D& OutShore) const;
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
};
