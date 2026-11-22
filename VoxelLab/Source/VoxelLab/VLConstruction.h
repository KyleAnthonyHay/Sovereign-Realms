#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLBattle.h"
#include "VLConstruction.generated.h"

class AVLKing;
class AVLHUD;
class APlayerController;
class AStaticMeshActor;
class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;

/**
 * The rules of building (the main game's FSRBuildingStats, SRFeelSettings > Builders, Docs/GAMEPLAY.md "Building"), as
 * far as this game has the buildings: what a Builder can raise, its price and its time, the limits, refunds and rates.
 * Only Builders build: every site rises only while a Builder works at its walls (the main game's castle zone, where a
 * site rose by itself, is not ported: the player builds where he wants).
 */
namespace VLBuild
{
	struct FSpec
	{
		EVLBuilding Kind = EVLBuilding::None;
		const TCHAR* Mesh = nullptr;        // /Game/Voxel/Meshes/<Mesh> (a farm: one of its variants, see UVLConstruction::MeshFor)
		FVLCost Cost;
		float Seconds = 16.f;               // with one Builder at its walls
		int32 Tab = 0;                      // the build menu: 0 Economy, 1 Military, 2 Defence
		const TCHAR* Blurb = TEXT("");
	};
	/** Everything a Builder can raise, in the build menu's order. */
	const TArray<FSpec>& Specs();
	const FSpec* Spec(EVLBuilding Kind);
	/** The build menu's entries of one tab (0 Economy, 1 Military, 2 Defence). */
	void TabEntries(int32 Tab, TArray<const FSpec*>& Out);
	const TCHAR* TabName(int32 Tab);

	constexpr float CancelRefund = 0.75f;           // a site cancelled: this share of its price back
	constexpr float DemolishRefund = 0.3f;          // a finished building pulled down: this share of its price and its levels
	constexpr float StartHealth = 0.15f;            // a site's health when it is laid (it rises with the walls)
	constexpr float ExtraSpeed = 1.0f;              // each Builder beyond the first adds this share of the speed (two Builders: twice as fast)
	constexpr int32 PerBuilding = 4;                // most Builders that count on one building
	constexpr float RepairPerSecond = 28.f;         // health a Builder gives back a second
	constexpr float AutoWorkRadius = 2600.f;        // an idle Builder of the player's goes to work on its own this near (cm)
	constexpr float Reach = 170.f;                  // a Builder works from this near the walls (cm)
	constexpr float LevelTolerance = 30.f;          // a footprint must be level to this (cm)
	constexpr float Gap = 100.f;                    // free ground between two buildings (cm)
	constexpr float TreeMargin = 150.f;             // trees this near a footprint are cleared (AVLForest::ClearTreesAround)
	constexpr float SnapStep = 50.f;                // placements snap to the half-metre ground blocks
	constexpr float VeinSnap = 1800.f;              // a mine snaps onto a vein this near the pointer (cm)
	// how many a kingdom may raise, by its castle's level (sites count; the level's own buildings do not)
	constexpr int32 FarmLimitBase = 3, FarmLimitPerLevel = 1;
	constexpr int32 TowerLimitBase = 2, TowerLimitPerLevel = 1;
	/** Builders a kingdom may have at a castle level (the main game's FSRCastleLevel::Builders: 2, 3, 3, 4, 4, 5, 6). */
	int32 MaxBuilders(int32 CastleLevel);
	constexpr int32 StartBuilders = 1;              // each side, when a match starts on a map with both castles
}

/** Where a building would go, and whether it can (UVLConstruction::CheckPlacement). */
struct FVLPlacement
{
	EVLBuilding Kind = EVLBuilding::None;
	int32 Team = 0;
	FVector Location = FVector::ZeroVector;     // the actor's (its pivot: the footprint's middle on the ground)
	float Yaw = 0.f;                            // multiples of 90 (its front, local +Y, faces Yaw + 90)
	FString Mesh;
	bool bValid = false;
	FString Reason;                             // why not (empty when valid)
	int32 Trees = 0;                            // trees it would clear
	TWeakObjectPtr<AActor> Vein;                // a mine: the vein it takes (a neutral mine, or a fallen one)
	// for the HUD: plates of a metre over the footprint (and a fringe round it), world points on the ground
	TArray<FVector> Cells;
	TArray<uint8> CellState;                    // 0 fine, 1 refused (uneven, water, something there), 2 fringe: open, 3 fringe: blocked
	FVector AxisX = FVector::ForwardVector;      // half a plate along the building's own axes (cm)
	FVector AxisY = FVector::RightVector;
};

/**
 * A Builder at work (the main game's ASRUnit Build order, StepBuild, LookForWork): sent to a site or a damaged building
 * of its own side, it walks to the nearest point of its walls by the usual routes (UVLGrid), turns to them and swings its
 * hammer (AVLKing::Attack, the up-down-up blows) until the work is done, then stands and looks for the next job. Made
 * the first time a Builder is sent (For); a move order ends the job (UVLCommand::StopAttack).
 */
UCLASS()
class VOXELLAB_API UVLBuilderWork : public UActorComponent
{
	GENERATED_BODY()

public:
	UVLBuilderWork();
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	static bool IsBuilder(const AVLKing* Unit);
	/** The unit's component; made if it has none yet (and it is a Builder). */
	static UVLBuilderWork* For(AVLKing* Unit, bool bCreate = true);
	/** At the walls of its job, hammering (AVLKing::Attack lets a Builder swing then). */
	static bool IsAtWork(const AVLKing* Unit);

	/** Go and work on Building (a site or a damaged building of its side). bOrdered: the player's order (a repair starts
	 *  even on a building hit a moment ago). */
	void Begin(AActor* Building, bool bOrdered);
	/** Ends the job it is on (its queue goes on: the next order of it starts). */
	void Stop();
	AActor* GetJob() const { return Job.Get(); }
	bool IsWorking() const { return bWorking && Job.IsValid(); }
	/** Seconds until it may look for a job of its own again. */
	float JobSearch = 0.f;

	/**
	 * Its queue of the player's Shift orders (UVLConstruction::QueueMove / OrderWork / PlaceBuilding / ClaimMine
	 * with bQueue): walks, and work on a building (a site laid, a claimed mine, a repair), done in turn once the job
	 * and the walk it is on are over. An order that has lapsed by its turn (the site cancelled or fallen, the
	 * building mended) is passed over. A plain order clears it (UVLCommand::StopAttack), so does Esc.
	 */
	struct FTask
	{
		bool bMove = false;
		FVector Point = FVector::ZeroVector;        // a walk: where to
		TWeakObjectPtr<AActor> Building;            // work: on what
		bool bRun = false;
	};
	void QueueTask(const FTask& Task);
	void ClearTasks() { Tasks.Reset(); }
	bool HasTasks() const { return Tasks.Num() > 0; }
	const TArray<FTask>& GetTasks() const { return Tasks; }

private:
	void WalkToWork(AVLKing* Unit);
	/** Between jobs: the next of the queue, once it stands (false: nothing left). */
	bool StartNextTask(AVLKing* Unit);
	TArray<FTask> Tasks;
	TWeakObjectPtr<AActor> Job;
	bool bWorking = false;
	bool bOrdered = false;
	float NextSwing = 0.f;
	float HammerAt = -1.f;
	int32 Walks = 0;
	float Stuck = 0.f;
};

/**
 * Building: the main game's construction (ASRBuilding's site, StepConstruction, CancelConstruction, Demolish,
 * USREconomySubsystem::PlaceBuilding, USRGridSubsystem::CheckPlacement, ASRPlacementPreview, the build menu's placing in
 * ASRPlayerController), on this game's buildings (UVLBattle's tagged actors) and path grid.
 *
 *   placing     the build menu (B) picks a building; a ghost of it follows the pointer, snapped to the half-metre blocks,
 *               its front to the view, green where it fits and red where not, with plates on the ground saying which
 *               ground refuses it (uneven, water, something standing there) and the reason; LMB places it (paid
 *               then), Shift + LMB places another, RMB / Esc cancels. A mine snaps onto a gold vein: a neutral mine, or
 *               the ruin of a fallen one, which it takes over
 *   sites       a placed building is a site: the trees in its footprint and a margin round it are cleared (and the path
 *               grid sampled again there), its walls rise course by course while Builders work at them (each beyond the
 *               first adds half the speed, up to four), its health with them; it does nothing else until it is done
 *   repairs     Builders mend a damaged building of their side (28 a second each); while they do it is out of action
 *               (no training, no payouts, no shots)
 *   cancel      a site: 75% of its price back. Demolish: a finished building (not the castle), 30% of its price and its
 *               levels, its training queue in full
 *   Builders    trained at the castle (UVLBattle::Train(Castle, 1, .., "Builder")): 120 gold + 80 food, 14 s, no housing
 *               but a limit of their own by the castle's level; an idle one goes to work by itself on a site or a badly
 *               damaged building nearby (the commander's: anywhere)
 *   yards       a troop trained at a barracks or a range (no rally point set) waits in the building's yard, in ranks
 *   the start   a battle starts without barracks or ranges: the level's are taken away (ClearStartTrainers)
 * The enemy commander builds through the same calls (FVLCommander::TryBuild).
 */
UCLASS()
class VOXELLAB_API UVLConstruction : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLConstruction* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Tick(float DeltaSeconds) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UVLConstruction, STATGROUP_Tickables); }
	virtual void Deinitialize() override;

	// ---- the rules
	/** How many of a kind a kingdom may raise now (INDEX_NONE: no limit), and how many it has raised (sites count). */
	int32 BuildLimit(EVLBuilding Kind, int32 Team) const;
	int32 CountRaised(EVLBuilding Kind, int32 Team) const;
	/** Why the kingdom cannot start one more of Kind now (the limit, the price, no Builder), or empty. */
	FString BuildRefusal(EVLBuilding Kind, int32 Team) const;
	/** Builders alive and (OutQueued) in training. */
	int32 CountBuilders(int32 Team, int32* OutQueued = nullptr) const;
	void GetBuilders(int32 Team, TArray<AVLKing*>& Out) const;
	/** The mesh a new building of Kind gets (a farm: the next of its variants, SM_Farmstead_A/B/C, round robin per side
	 *  so that neighbours differ; SM_Farmstead while they are not imported). bAdvance: take it. */
	FString MeshFor(EVLBuilding Kind, int32 Team, bool bAdvance = false);
	static UStaticMesh* LoadMesh(const FString& Name);

	// ---- placing
	/** Would a building of Kind stand at Want (world; snapped), turned Yaw? bCells: also the plates for the HUD. */
	bool CheckPlacement(EVLBuilding Kind, int32 Team, const FVector& Want, float Yaw, FVLPlacement& Out, bool bCells = false) const;
	/** The nearest good spot to Near within Radius (cm), rings outward (the commander's). */
	bool FindPlacementNear(EVLBuilding Kind, int32 Team, const FVector& Near, float Radius, float Yaw, FVLPlacement& Out, int32 MaxTries = 90) const;
	/** Pays and lays the site (trees cleared, the grid sampled again, troops on it step aside). Builders: who goes to
	 *  work on it (none: the nearest free Builder of its side). Returns the building, or null (OutWhy). */
	AActor* PlaceBuilding(const FVLPlacement& Where, const TArray<AVLKing*>& Builders, FString* OutWhy = nullptr, bool bQuiet = false, bool bQueue = false);
	/** A site is finished at once, as if its Builders had worked it through (the Test World's start). False if it is
	 *  no site. */
	bool FinishNow(AActor* Building);
	/** A site's walls are pulled down: CancelRefund of its price back. */
	bool CancelSite(AActor* Building);
	/** A finished building (not the castle) is pulled down: DemolishRefund of everything paid for it back. */
	bool Demolish(AActor* Building);
	/** What demolishing (or cancelling) it would bring back now. */
	FVLCost RefundFor(const AActor* Building) const;
	/** The builders among Units go to work on Building if it is theirs and needs work. True if any were sent.
	 *  bQueue (Shift): it goes on the end of their queue instead (UVLBuilderWork::FTask); PlaceBuilding's and
	 *  ClaimMine's bQueue the same for the site they lay (laid and paid for at once, built in its turn). */
	bool OrderWork(const TArray<AVLKing*>& Units, AActor* Building, bool bOrdered = true, bool bQueue = false);
	/** Shift + right click on the ground: a walk on the end of the Builders' queues (each its place in a line round
	 *  the point). True if any Builder was among Units. */
	bool QueueMove(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun);
	/** Esc: the queued orders of the Builders among Units are dropped (the job they are on goes on). True if any had one. */
	bool ClearQueues(const TArray<AVLKing*>& Units);
	/** X: the builders among Units go and repair the nearest damaged building of theirs. */
	bool OrderRepair(const TArray<AVLKing*>& Units);
	/** Builders at work on it now. */
	int32 BuildersAt(const AActor* Building) const;

	// ---- the player's build menu and placing (the overview)
	bool IsMenuOpen() const { return bMenuOpen; }
	void ToggleMenu() { SetMenu(!bMenuOpen); }
	void SetMenu(bool bOpen);
	int32 GetTab() const { return Tab; }
	void SetTab(int32 InTab) { Tab = FMath::Clamp(InTab, 0, 2); }
	/** The menu's card for Kind was clicked (or its key): placing it starts (or is refused, with why). */
	void BeginPlacement(EVLBuilding Kind);
	void CancelPlacement();
	bool IsPlacing() const { return Placing != EVLBuilding::None; }
	EVLBuilding GetPlacing() const { return Placing; }
	/** T while placing: the ghost turns a quarter turn clockwise (on top of facing the view). The turn is kept for the
	 *  next ghost of a Shift placing and for the next placing of the same kind. Mines are never placed. */
	void TurnPlacement();
	int32 GetPlaceTurns() const { return PlaceTurns; }
	const FVLPlacement& GetPlacement() const { return Current; }
	bool HasPlacementUnderPointer() const { return bPointerOnGround; }
	/** Esc: the placement, then the menu. True if it took the key. */
	bool OnEscape();
	/** AVLKing::OverviewCommands hands the overview's input here first: B (the menu), X (repair), Delete (a selected
	 *  site / building: cancel / demolish, twice), the menu's 1-6, and while placing the mouse. True: it took the frame's
	 *  mouse and keys (nothing else in the overview reads them). */
	bool OverviewInput(APlayerController* PC, AVLHUD* HUD, AVLKing* Me);
	/** Delete / the panel's button: the first press asks (it returns false), a second within 3 s does it. */
	bool AskDemolish(AActor* Building);
	bool IsDemolishAsked(const AActor* Building) const;

	// ---- turning a finished building (T, or the panel's Rotate tab)
	/**
	 * Turns a finished building a quarter turn clockwise (seen from above) where it stands, about the middle of its
	 * footprint: its walls and their collision, its props (spawned again in their new places), its yard and whoever
	 * waits or stands in it, the archers on a tower's lookout (all carried round with it, so nobody ends up inside a
	 * wall), its door and default rally point (UVLBattle::FrontOf reads the actor). The path grid is sampled again
	 * over the old footprint and the new. Free. Refused (OutWhy; the player gets an alert unless bQuiet) for the
	 * castle, a site, a mine (part of its map), the map's own buildings, and where the turned footprint does not
	 * fit: the same checks, and the same reasons, as placing it there (RotateRefusal).
	 */
	bool Rotate(AActor* Building, FString* OutWhy = nullptr, bool bQuiet = false);
	/** Why it cannot be turned a quarter clockwise now, or empty. OutWhere: where it would stand. */
	FString RotateRefusal(const AActor* Building, FVLPlacement* OutWhere = nullptr) const;
	/** The same for the HUD, which asks every frame: worked out again at most every 0.4 s. */
	const FString& RotateRefusalCached(const AActor* Building) const;
	/** Is it a kind of building that is ever turned (a finished one of the match, not the castle, not a mine)? If not,
	 *  OutWhy says why. */
	bool CanEverRotate(const AActor* Building, FString* OutWhy = nullptr) const;

	// ---- claiming a gold mine
	/**
	 * Mines are not built: every one is part of its map, set into a mountain or a hill. A free one (a neutral mine, or
	 * one that has fallen and stands abandoned) is CLAIMED: Builders are ordered onto it (right click, or the Claim
	 * button of its panel), the kingdom pays the mine's price, and it is a site that rises as they work at it, by the
	 * usual rules (each Builder beyond the first adds ExtraSpeed, up to PerBuilding; cancel: CancelRefund back). The
	 * mine's own mesh stays exactly where it is and as it is; when the claim is done it is that side's, in its look.
	 * A mine that falls is not taken away either: it stands abandoned and can be claimed again.
	 * Returns the mine, or null (OutWhy; the player gets an alert unless bQuiet). Builders: who goes (none: the nearest
	 * free Builder of the side). The enemy commander claims by the same call path (CheckPlacement + PlaceBuilding).
	 */
	AActor* ClaimMine(AActor* Mine, int32 Team, const TArray<AVLKing*>& Builders, FString* OutWhy = nullptr, bool bQuiet = false, bool bQueue = false);
	/** A mine nobody holds: neutral, or fallen and abandoned. */
	bool IsFreeMine(const AActor* Mine) const;
	/** Why Team cannot claim it now (not a free mine, the price, no Builder, foes at it), or empty. */
	FString ClaimRefusal(const AActor* Mine, int32 Team) const;

	// ---- the yard: where a trained troop waits (barracks, range)
	/** Sends a fresh recruit to the first free place in the building's yard, in ranks. False: it has no yard / it is full. */
	bool SendToYard(FVLBuildingState& B, AVLKing* Recruit);
	/** Its yard: places of the ranks (world, on the ground), in the order they fill, and the way they face. */
	bool YardSlots(const AActor* Building, TArray<FVector>& Out, float& OutYaw) const;

	// ---- the match
	/** A battle starts with no barracks and no archery range on either side: the level's are taken away. */
	int32 ClearStartTrainers();

	void LogStatus() const;
	/** vl.PlacementBench: the ghost's check at N places in a row from At (each twice: moved there, then standing still),
	 *  timed, with a digest of every answer (to compare vl.Opt.Placement 0 and 1). */
	void BenchPlacement(EVLBuilding Kind, const FVector& At, int32 N);

private:
	/**
	 * What the ground said under one placement of the ghost (CheckPlacement's samples, in the order it took them, and
	 * the trees it would clear): kept while a building is being placed, so that the ghost standing still, or coming
	 * back to a place, does not trace the ground again. Used by the ghost only; a building is always checked afresh as
	 * it is laid, and so is everything that moves (other buildings' gaps, troops, the gate's ground) on every check.
	 */
	struct FPlaceMemo
	{
		EVLBuilding Kind = EVLBuilding::None;
		int32 Team = 0;
		FVector2D Snapped = FVector2D::ZeroVector;
		float Yaw = 0.f;
		double WantZ = 0.0;
		bool bCells = false;
		// what it was true of: the path grid's revision (trees, buildings laid or gone), the buildings standing, when
		uint32 GridRevision = 0;
		uint32 Buildings = 0;
		double SampledAt = 0.0;
		struct FSample
		{
			float Z = 0.f;
			int8 What = 3;
		};
		TArray<FSample> Samples;
		int32 Trees = INDEX_NONE;       // (INDEX_NONE: not counted)
		// while a check runs: replaying (At: the next sample), or recording
		bool bReplay = false;
		int32 At = 0;
	};
	/** Self: the building being turned (Rotate): it is looked through, with its props, it is no neighbour of itself,
	 *  and its own mesh (a farm's variant) is the one checked. */
	bool CheckPlacementImpl(EVLBuilding Kind, int32 Team, const FVector& Want, float Yaw, FVLPlacement& Out, bool bCells, FPlaceMemo* Memo, const AActor* Self = nullptr) const;
	/** The ghost's check: CheckPlacement through the memos of this placing. */
	bool CheckPlacementForGhost(EVLBuilding Kind, int32 Team, const FVector& Want, float Yaw, FVLPlacement& Out);
	uint32 BuildingsStamp() const;
	TArray<FPlaceMemo> PlaceMemos;
	/** TickSites' count of Builders at work on each building, and TickYards' ranks: kept between frames. */
	TMap<const AActor*, int32> AtWorkScratch;
	struct FYardMemo
	{
		uint32 GridRevision = 0;
		const UStaticMesh* Mesh = nullptr;
		FTransform At;
		TArray<FVector> Slots;
		float Yaw = 0.f;
		bool bOk = false;
	};
	TMap<TWeakObjectPtr<const AActor>, FYardMemo> YardMemos;

	void TickSites(float Dt);
	void TickJobs(float Dt);
	void TickYards(float Dt);
	/** Units standing in a box of ground that has just been built on (no ground to walk under them any more) are put
	 *  on the nearest that can be walked. Returns how many. */
	int32 MoveClear(const FVector2D& Centre, const FVector2D& Half, float Yaw);
	void Finish(FVLBuildingState& B);
	void ShowRising(FVLBuildingState& B, float Progress);
	void SpawnProps(FVLBuildingState& B);
	void UpdateGhost(APlayerController* PC, AVLHUD* HUD, AVLKing* Me);
	void HideGhost();
	/** The best job for an idle Builder (a site first, the nearest, then a badly damaged building), or null. */
	AActor* FindJob(const AVLKing* Builder) const;

	bool bMenuOpen = false;
	int32 Tab = 0;
	EVLBuilding Placing = EVLBuilding::None;
	FVLPlacement Current;
	bool bPointerOnGround = false;
	FIntPoint LastSnap = FIntPoint(MAX_int32, MAX_int32);
	float LastYaw = -1.f;
	int32 PlaceTurns = 0;                       // quarter turns clockwise the player gave the ghost (T)
	EVLBuilding PlaceTurnsKind = EVLBuilding::None;
	bool bLogTurn = false;
	bool bRightDown = false;
	FVector2D RightPress = FVector2D::ZeroVector;
	TWeakObjectPtr<AActor> AskedDemolish;
	double AskedAt = -10.0;
	mutable TWeakObjectPtr<const AActor> RotateAsked;
	mutable double RotateAskedAt = -10.0;
	mutable FString RotateAskedWhy;
	int32 FarmVariant[2] = { -1, -1 };
	float JobClock = 0.f;
	double CheckedAt = 0.0;
	/** The props each building raised in the match got (its dummies, its wheat and beasts): they go when it falls. */
	TMap<TWeakObjectPtr<AActor>, TArray<TWeakObjectPtr<AActor>>> Props;

	// ---- the farms' hands (AVLFarmer, VLFarmer.*): a farmer woman and a farmer man at every finished farm, the
	// map's and those raised in the match; sent away when it falls, is pulled down (or abandoned) or is turned (they
	// come back to its new ground). Looked over once a second.
	struct FFarmCrew
	{
		TArray<TWeakObjectPtr<AVLKing>> Hands;
		FTransform At;
	};
	TMap<TWeakObjectPtr<AActor>, FFarmCrew> FarmCrews;
	TSet<TWeakObjectPtr<AActor>> FarmNoSpots;     // farms whose ground could not be found (logged once)
	float FarmClock = 0.f;
	void TickFarmhands(float Dt);
	/** Where a farm's hands work: its crop rows (the wheat of its props table), the farmhouse door, the store beside it;
	 *  each on walkable ground of the door's region, inside the farm. False: no grid, or no ground at the door. */
	bool FarmSpots(const FVLBuildingState& B, struct FVLFarmSpots& Out) const;
	void DismissCrew(AActor* Farm, FFarmCrew& Crew, const TCHAR* Why);

	UPROPERTY(Transient)
	TObjectPtr<AStaticMeshActor> Ghost;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> GhostMaterial;

	/** The rising walls of each site: a copy of its mesh, squashed (the building's own mesh is hidden meanwhile, its
	 *  collision already up). */
	UPROPERTY(Transient)
	TMap<TObjectPtr<AActor>, TObjectPtr<AStaticMeshActor>> Rising;
};
