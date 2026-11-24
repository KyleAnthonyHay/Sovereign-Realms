#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLBattle.generated.h"

class AVLKing;
class AVLTroop;
class USoundBase;
class USoundAttenuation;
struct FVLCommander;
struct FVLMatchLog;
enum class EVLUnitKind : uint8;         // VLKing.h

/** A list of units on the stack (most queries return a handful; the whole army spills to the heap). */
using FVLUnits = TArray<AVLKing*, TInlineAllocator<64>>;

/** B: how long the paths the optimisation pass changed take (a test aid). `vl.Opt.Timing` starts the clocks; each
 *  further call logs the milliseconds a frame since the last and starts again. Off until first asked: no cost. */
struct SOVEREIGNREALMS_API FVLOptTiming
{
	enum { Steer, BattleTick, AutoCombat, Arrows, HudWorld, Shuffle, Ambience, Minimap, Num };
	static bool bOn;
	static double Seconds[Num];
	static int32 Calls[Num];
	struct FScope
	{
		const int32 Slot;
		const double Start;
		explicit FScope(int32 InSlot) : Slot(InSlot), Start(bOn ? FPlatformTime::Seconds() : 0.0) {}
		~FScope() { if (Start != 0.0) { Seconds[Slot] += FPlatformTime::Seconds() - Start; ++Calls[Slot]; } }
	};
};

/** What a building is for (its tag Name:<kind>). The main game's ESRBuildingType, as far as this game has them. */
UENUM()
enum class EVLBuilding : uint8
{
	None,       // not a building of the game (a bridge, a dock, a banner)
	Castle,     // the kingdom's seat: it falls, the kingdom falls; houses troops; archers on its walls
	Barracks,   // trains swordsmen
	Range,      // the archery range: trains archers
	Farm,       // grain (food) and housing
	Mine,       // the gold mine: gold
	Tower,      // the watch tower: shoots on its own, and archers can man its lookout
	Granary,    // holds food on top of the castle's stores
	Treasury,   // holds gold on top of the castle's stores
	Hall        // the town hall: no work of its own, but it can be burned
};

enum class EVLRes : uint8 { Gold, Food };

struct FVLCost
{
	int32 Gold = 0;
	int32 Food = 0;
};

/**
 * The rules and numbers of the main game (USRFeelSettings defaults, Docs/GAMEPLAY.md), carried over. Per-hit damage
 * is scaled so that damage per second is the main game's: the voxel troops keep their own (approved) rhythm, a swing
 * every 1.25 s and an arrow every 2.4 s on orders, where the main game had 1.15 s and 1.5 s.
 */
namespace VLRules
{
	struct FTroop
	{
		float Health = 100.f;
		float Damage = 10.f;          // per swing (split over its blows) or per arrow
		float BuildingScale = 1.f;    // x damage against buildings
		float Acquire = 1300.f;       // cm: what it notices and goes for
		int32 Pop = 1;                // housing it takes
		FVLCost Cost;
		float TrainSeconds = 9.f;
		float Sight = 1300.f;         // cm: how far it sees (the selection's sight ring; fog of war, when there is one)
		float Notice = 1.f;           // foes notice it at this share of the distance they would notice anyone else (the Spy)
		float WalkSpeed = 0.f;        // cm/s on the march and at a run; 0 = the figure's own (420 / 760)
		float RunSpeed = 0.f;
	};
	/** "Swordsman", "Archer", "Spy", "King". */
	const FTroop& Troop(const FString& Kind);
	/** The same by number (AVLKing::KindId; AVLKing::KindRules has it cached per unit). */
	const FTroop& Troop(EVLUnitKind Kind);
	EVLUnitKind KindOf(const FString& Kind);
	/** A building's hit box (UVLBattle::BuildingOnPath, BuildingAt, the sword's reach): its mesh's box grown this much
	 *  round the sides and the top (cm), so a blade at its walls or an arrow at its eaves counts. */
	constexpr float BuildingHitPad = 80.f;
	/** The king heals when nothing has hurt him for this long (s), this much of his most health a second (both kings). */
	constexpr float KingRestDelay = 8.f;
	constexpr float KingRestRate = 0.04f;

	/** One level of a building (index 0 = level 1). Fields a kind does not use stay 0. */
	struct FLevel
	{
		FVLCost Cost;                 // to raise it to this level (level 1: none)
		float Seconds = 0.f;          // how long the raising takes
		float Health = 1000.f;
		int32 Housing = 0;            // troops it houses
		int32 Ceiling = 0;            // the castle: the most troops the kingdom may field
		int32 Storage = 0;            // the castle: gold and food it holds (each); a granary / treasury: its own resource
		int32 Yield = 0;              // a farm's food / a mine's gold per payout
		int32 Archers = 0;            // defence: shots per volley
		float Damage = 0.f;
		float Interval = 0.f;
		float Range = 0.f;            // cm from its walls
		float TrainSpeed = 1.f;       // barracks / range
		int32 CastleLevel = 0;        // storehouses: the castle level this level needs
	};
	int32 NumLevels(EVLBuilding Kind);
	const FLevel& Level(EVLBuilding Kind, int32 Level);      // Level is 1-based
	const TCHAR* Name(EVLBuilding Kind);
	EVLBuilding KindFromName(const FString& Name);

	// (a side starts with no farm now: the gold for a farm, a barracks and a range with a little over, and food for
	// three troops while the first harvests come in. They were 320 / 200 when the maps placed farms.)
	constexpr int32 StartGold = 400;
	constexpr int32 StartFood = 300;
	constexpr float PayoutInterval = 6.f;       // farms and mines
	constexpr int32 StartSwordsmen = 3;          // each side, when a match starts on a map with both castles
	constexpr int32 StartArchers = 2;
	constexpr int32 RecruitBatch = 5;            // Shift + Train
	constexpr int32 RecruitBatchLarge = 10;      // Ctrl / Cmd / Alt + Train
	/** King David rises again at his castle this long after he falls (s). 100: five times the 20 s it was (the owner's
	 *  call, 2026-11-22: "hero cool down should be 5 times"). His only cooldown: he has no ability on a timer. */
	constexpr float KingRespawnSeconds = 100.f;
	constexpr float CorpseSeconds = 2.4f;
	/** A watch tower's own archers (the owner's call, 2026-11-22): 2 on the lookout at level 1, one more for each
	 *  level it is raised (3, 4); free (no housing, no army count). One that falls is replaced TowerGuardRestock
	 *  seconds later, one at a time. They shoot as far as the tower itself does (its level's reach, from its walls),
	 *  so its reach is as the enemy commander reckons it. */
	inline int32 TowerGuards(int32 Level) { return FMath::Clamp(Level, 1, 3); }
	constexpr float TowerGuardRestock = 40.f;
	/** How far a defensive unit goes from its post after a foe before it turns back (cm). It goes for foes it can
	 *  strike within that: a swordsman 22.4 m from where it stands, an archer her full 42 m. (It was 13 m, or the
	 *  unit's sight of 16.9 / 19.5 m, which then was also how far troops noticed foes.) */
	constexpr float DefensiveLeash = 2000.f;
	/** An aggressive unit lets go of a chase at this many times its reach (unless it is being struck). */
	constexpr float ChaseLetGo = 1.5f;
	/** An aggressive unit on a fight of its own goes no further than this from where it took it up (cm), then walks
	 *  back there, as it does after letting a chase go (one on an attack-move, following, guarding or on a chain of
	 *  orders is brought back by that order instead). With the longer reach a troop would otherwise run down one foe
	 *  after another into the enemy's base. */
	constexpr float AggressiveLeash = 5000.f;
	/** Friends within this of a struck unit come to its help (cm; was 6.5 m). */
	constexpr float HelpRadius = 1200.f;
	/** An idle unit with no foe in its reach goes for the foe of a friend fighting within its reach, if that foe is
	 *  no more than this beyond its reach (cm). */
	constexpr float AssistExtra = 1000.f;
	/** A platoon keeps together (UVLBattle::TickCohesion; the owner's call, 2026-11-22). An aggressive member
	 *  standing idle further than CohesionLeash from the nearest member of its platoon that is in a fight runs there
	 *  and joins in, no further than AggressiveLeash from where it stood; with no fight on, one further than
	 *  RegroupLeash from the platoon's body walks back to it. The body: the member with the most of the others within
	 *  CohesionBody of it. See the README (Standing orders > Platoons keep together) for who is left alone. */
	constexpr float CohesionLeash = 2000.f;
	constexpr float RegroupLeash = 3000.f;
	constexpr float CohesionBody = 1500.f;
	constexpr float EndScreenDelay = 1.6f;
	// the Spy (the main game's Scout: ScoutCastleLevel, MaxScouts, ScoutCooldown)
	constexpr int32 SpyCastleLevel = 3;          // the castle level a kingdom needs before it can train its Spy
	constexpr int32 MaxSpies = 1;                // alive and in training
	constexpr float SpyCooldown = 300.f;         // seconds between two, from the moment the last was queued and paid for
	// JONATHAN, the archer prince: the second hero (unit kind "Jonathan": an AVLTroop with the played archer's bow).
	// He is not there at the start: he comes to the castle when it reaches JonathanCastleLevel (UVLBattle::TickJonathan),
	// free and taking no housing, and comes back there JonathanRespawnSeconds after he falls (while the castle stands
	// at that level). His own numbers, next to the archer troop's bow and King David's legs (the owner's call,
	// 2026-11-23: "his bow should take longer to draw and arrows go faster. his run speed should be faster too and
	// his jump higher"); the archers and the king keep theirs. AVLTroop::BeginPlay puts them on him.
	constexpr int32 JonathanCastleLevel = 3;
	constexpr float JonathanRespawnSeconds = KingRespawnSeconds;
	constexpr float JonathanDrawSeconds = 0.62f;     // the draw itself (the archer: 0.34). Button down to fully drawn: 1.14 s against her 0.86 (+33%)
	constexpr float JonathanArrowSpeed = 11000.f;    // cm/s (the archer: 6210; +77%; was 8280 until 2026-11-23). Aim and arcs are solved with the bow's own speed
	constexpr float JonathanShotInterval = 3.0f;     // on orders, seconds from shot to shot (the archer: 2.4): the longer draw
	constexpr float JonathanWalkSpeed = 520.f;       // cm/s (King David: 420; +24%)
	constexpr float JonathanRunSpeed = 1000.f;       // cm/s (King David: 760; +32%)
	constexpr float JonathanJumpZ = 700.f;           // cm/s off the ground (King David and every troop: 540; +30%, a jump 1.68 times as high)
}

/** A building of the game, as the battle keeps it. */
struct FVLBuildingState
{
	TWeakObjectPtr<AActor> Actor;
	EVLBuilding Kind = EVLBuilding::None;
	int32 Team = 0;                     // 0 the player, 1 the enemy, -1 neutral (never hurt)
	FString Name;
	float Health = 1000.f;
	float MaxHealth = 1000.f;
	int32 Level = 1;
	float UpgradeLeft = -1.f;           // seconds until the next level is done; < 0 none under way
	float UpgradeTotal = 0.f;
	float Payout = 0.f;                 // a farm's / mine's clock
	float Defence = 0.f;                // a tower's / the castle's clock
	bool bDestroyed = false;
	float Collapse = -1.f;              // seconds into its collapse
	FVector Rest = FVector::ZeroVector;
	double LastHit = -100.0;
	double LastAlert = -100.0;
	// training (barracks, range)
	TArray<FString> Queue;
	float TrainClock = 0.f;
	int32 Trained = 0;
	int32 FeedPlatoon = INDEX_NONE;     // its recruits join this platoon (the main game's "Joins" row)
	bool bHasRally = false;
	FVector Rally = FVector::ZeroVector;
	// construction (UVLConstruction, VLConstruction.*): a site rises only while Builders work at its walls
	float Build = 1.f;                  // 0..1; below 1 it is a site: no work, no housing, no shots, no upgrades
	int32 BuildersAt = 0;               // Builders at its walls now (counted each frame while it needs work)
	bool bRepairing = false;            // Builders are mending it: out of action until they finish
	bool bRuntime = false;              // raised in the match (not the level's own): counts against the build limits
	FVLCost Paid;                       // what it cost to lay (refunds)
	FString Mesh;                       // the mesh it was raised with (a farm's variant)
	TArray<TWeakObjectPtr<AVLKing>> Yard;   // a barracks' / range's yard: who waits at each of its places
	// a watch tower's own archers (UVLBattle::TickTowerGuards): on its lookout, VLRules::TowerGuards(level) of them
	TArray<TWeakObjectPtr<AVLKing>> Guards;
	int32 GuardLevel = 0;               // the level they were last filled up for (0: never)
	float GuardRestock = 0.f;           // seconds until a fallen one is replaced

	bool IsAlive() const { return !bDestroyed && Actor.IsValid(); }
	bool IsSite() const { return Build < 1.f; }
	/** Standing, built, and not under repair: it works (trains, pays, shoots, houses). */
	bool IsWorking() const { return IsAlive() && !IsSite() && !bRepairing; }
	bool Trains() const { return Kind == EVLBuilding::Barracks || Kind == EVLBuilding::Range || Kind == EVLBuilding::Castle; }   // (the castle: the Spy and the Builders)
};

struct FVLKingdom
{
	int32 Gold = 0;
	int32 Food = 0;
	float Flash[2] = { 0.f, 0.f };      // a refused purchase: the counter flashes red (gold, food)
	float Pulse[2] = { 0.f, 0.f };      // income landed
	int32 Recruited = 0;
	int32 Lost = 0;
	int32 Killed = 0;
	int32 BuildingsLost = 0;
	bool bHasCastle = false;
	// the match's books (the balance log, VLMatchLog.*): by EVLUnitKind; by EVLRes
	int32 RecruitedKind[6] = { 0, 0, 0, 0, 0, 0 };
	int32 LostKind[6] = { 0, 0, 0, 0, 0, 0 };
	int32 Earned[2] = { 0, 0 };         // income that came in (farms, mines)
	int32 Wasted[2] = { 0, 0 };         // income lost for want of storage
	int32 Spent[2] = { 0, 0 };          // paid out (buildings, troops, levels; refunds not taken off)
	// what its side dealt, by who dealt it (VLRules::StrikerClass: 0 King, 1 Swordsman, 2 Archer, 3 Spy, 4 Builder,
	// 5 another unit, 6 a tower's own archer, 7 a building's shot): damage to units, to buildings, and kills
	float DamageBy[8] = { 0, 0, 0, 0, 0, 0, 0, 0 };
	float BuildingDamageBy[8] = { 0, 0, 0, 0, 0, 0, 0, 0 };
	int32 KillsBy[8] = { 0, 0, 0, 0, 0, 0, 0, 0 };
};

UENUM()
enum class EVLMatch : uint8
{
	Idle,       // the main menu is up (or nothing has started): no economy, no commander
	Playing,
	Ended
};

UENUM()
enum class EVLAlert : uint8
{
	Info,
	Attack,
	Lost,
	Good
};

struct FVLAlert
{
	FString Text;
	EVLAlert Kind = EVLAlert::Info;
	FVector At = FVector::ZeroVector;
	bool bHasAt = false;
	double Time = 0.0;
};

struct FVLPopup
{
	FVector At = FVector::ZeroVector;
	FString Text;
	int32 Amount = 0;                   // what came in (the HUD draws "+14" and the resource's icon)
	bool bGold = false;
	FLinearColor Colour = FLinearColor::White;
	double Time = 0.0;
};

USTRUCT()
struct FVLSoundSet
{
	GENERATED_BODY()

	UPROPERTY(Transient)
	TArray<TObjectPtr<USoundBase>> Sounds;
	int32 Last = -1;
	double LastTime = -100.0;
};

/**
 * The battle: the main game's USRBattleSubsystem, USREconomySubsystem and USRGameFlowSubsystem, reimplemented on this
 * project's units (AVLKing, AVLTroop) and the level's tagged buildings.
 *
 *   teams      every unit has AVLKing::Team; a building has its tag Team:0 (the player), Team:1 (the enemy) or
 *              Team:Neutral; a game building without one is the player's (the sandboxes)
 *   health     units carry their own (AVLKing); buildings' is kept here (their kind and level). Damage goes through
 *              Damage(): it never hurts a friend, scales a troop's blows against buildings, wakes the victim and
 *              its friends nearby, raises the alerts, and kills / collapses
 *   economy    each kingdom's gold and food: farms and mines pay every 6 s, the castle's stores (and a granary's or
 *              treasury's) cap them; housing from the castle and the farms, capped at the castle's troop ceiling
 *   training   the barracks and the range: each recruit is paid for and housed when queued (no queue limit), trained
 *              in its time (faster at higher levels), and walks to the building's rally point (or joins its platoon)
 *   upgrades   the castle (7 levels), towers, farms, mines, the barracks and range, storehouses (3 levels each)
 *   combat     idle troops go for any foe in their sight (troops before buildings) by their stance; one that is hit
 *              answers; units on an attack-move (the commander's) fight what they meet; towers and the castle shoot
 *   the match  starts from the New Game screen (or vl.StartMatch); the side whose castle falls loses; King David,
 *              if he falls, is carried back to his castle and rises there RespawnSeconds later
 * The enemy commander (VLEnemyAI.*) plays team 1 by the same rules.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLBattle : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLBattle* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UVLBattle, STATGROUP_Tickables); }

	// ---- teams
	static constexpr int32 Player = 0;
	static constexpr int32 Enemy = 1;
	static constexpr int32 Neutral = -1;
	/** A unit's team, a building's, or Neutral. */
	int32 TeamOf(const AActor* Actor) const;
	/** Can Team hurt it (a living unit or standing building of another side)? */
	bool IsHostile(const AActor* Actor, int32 Team) const;
	bool IsAlive(const AActor* Actor) const;
	static FLinearColor TeamColour(int32 Team);
	static const TCHAR* TeamName(int32 Team);

	// ---- the unit registry (vl.Opt.Registry 0: the old TActorIterator walks, for comparing)
	/** Every unit of the world, alive or fallen (as TActorIterator<AVLKing> gave them), in the order they came into
	 *  it. Kept by the world's actor-spawned / actor-destroyed delegates. For loops that only read; one that gives
	 *  orders, deals damage or spawns takes a copy (GetAllUnits). */
	const TArray<AVLKing*>& AllUnits() const;
	void GetAllUnits(FVLUnits& Out) const;
	/** Every unit that may be within Radius cm (on the ground plane) of At: all of those, and some a little further
	 *  (a spatial hash on UnitCell cm cells, rebuilt once a frame; the caller's own test decides). In registry order. */
	void UnitsNear(const FVector& At, float Radius, FVLUnits& Out) const;
	/** The same for a box on the ground plane (an arrow's stretch of flight). */
	void UnitsInBox(const FVector2D& Min, const FVector2D& Max, FVLUnits& Out, int32 NotOfTeam = MIN_int32) const;
	/** Rebuilds the hash now (the subsystems' ticks: every unit has moved since the actors' own). */
	void RefreshUnitHash() const;
	static bool UseRegistry();
	/** The level's actors tagged Selectable (never a unit) / Dummy / named as a gold mine, in the actor iterator's
	 *  order: cached, and read again when an actor is spawned or a building registered (and once a second). */
	const TArray<TWeakObjectPtr<AActor>>& Selectables() const;
	const TArray<TWeakObjectPtr<AActor>>& Dummies() const;
	const TArray<TWeakObjectPtr<AActor>>& MineActors() const;

	// ---- buildings
	FVLBuildingState* FindBuilding(const AActor* Actor);
	const FVLBuildingState* FindBuilding(const AActor* Actor) const;
	const TArray<FVLBuildingState>& GetBuildings() const { return Buildings; }
	TArray<FVLBuildingState>& GetBuildingsMutable() { return Buildings; }
	/** A team's castle while it stands. */
	AActor* GetCastle(int32 Team) const;
	int32 CountBuildings(EVLBuilding Kind, int32 Team) const;
	/** Registers an actor as a building (its tags read again): vl.SetTeam, test bases. */
	void RegisterBuilding(AActor* Actor);
	/** The closest point of a building's box (its mesh's bounds, turned with it) to a point, on the ground plane, and
	 *  how far that is (0 inside). For a unit or a dummy: its feet and the distance to them. */
	float DistanceTo(const AActor* Target, const FVector& From, FVector* OutPoint = nullptr) const;
	/** Where an arrow aimed at it should go (a unit's chest, a point on a building's wall facing From). */
	FVector AimPoint(const AActor* Target, const FVector& From) const;
	/** The first foe's building (not Team's, not neutral, standing) whose hit box (its mesh's box turned with it, grown by
	 *  VLRules::BuildingHitPad; a site's only as high as its walls) the stretch From..To enters, and how far along (0..1). */
	AActor* BuildingOnPath(const FVector& From, const FVector& To, int32 Team, float& OutT) const;
	/** A foe's building (as above) whose hit box holds P (grown by Extra more), else null. */
	AActor* BuildingAt(const FVector& P, int32 Team, float Extra = 0.f) const;
	/** Its front door: where recruits appear (buildings face their local +Y) and its rally point by default. */
	void FrontOf(const AActor* Building, FVector& OutDoor, FVector& OutRally, FVector& OutFront) const;

	// ---- health and damage
	/** Amount from By (a unit, a building, or null) of team ByTeam. Returns the damage done. */
	float Damage(AActor* Target, float Amount, AActor* By, int32 ByTeam);
	/** A unit's health reached 0 (AVLKing::ReceiveDamage). */
	void OnUnitKilled(AVLKing* Unit, AActor* By);

	// ---- economy
	int32 GetStock(int32 Team, EVLRes Res) const;
	void AddStock(int32 Team, EVLRes Res, int32 Amount, bool bIgnoreStorage = false);
	bool CanAfford(int32 Team, const FVLCost& Cost) const;
	/** Pays, or refuses (the player: the short counter flashes, an alert says why). */
	bool TrySpend(int32 Team, const FVLCost& Cost, bool bQuiet = false);
	int32 GetStorage(int32 Team, EVLRes Res) const;
	int32 GetCastleLevel(int32 Team) const;
	/** Jonathan, the archer prince, of a side (alive or just fallen), or null: he is not in the field. */
	AVLTroop* GetJonathan(int32 Team) const;
	/** Jonathan at a point, now (what TickJonathan does at the castle; vl.Jonathan spawn for a sandbox without one). */
	AVLTroop* SpawnJonathan(int32 Team, const FVector& Ground, float Yaw);
	/** Which sides get him: the player's; the enemy's too with vl.Jonathan.Enemy 1. */
	static bool JonathanFor(int32 Team);
	/** Seconds until he may come (back) to the castle; and, for testing (vl.Jonathan castle), the side's castle raised
	 *  straight to the level he comes at. Returns the castle's level. */
	float GetJonathanWait(int32 Team) const { return (Team == 0 || Team == 1) ? JonathanWait[Team] : 0.f; }
	int32 RaiseCastleForJonathan(int32 Team);
	/** Troops alive (not the king), and waiting in training queues. */
	int32 GetPopulation(int32 Team) const;
	int32 GetQueuedPopulation(int32 Team) const;
	/** What its castle and farms house, capped at the castle's troop ceiling. */
	int32 GetPopulationCap(int32 Team) const;
	int32 GetPopulationCeiling(int32 Team) const;
	float GetIncomePerMinute(int32 Team, EVLRes Res) const;
	const FVLKingdom& GetKingdom(int32 Team) const { return Kingdoms[FMath::Clamp(Team, 0, 1)]; }
	/** The share of its farms' and mines' output a kingdom gets (the commander's difficulty; 1 for the player). */
	float IncomeScale(int32 Team) const;

	// ---- training
	/** The troop a building trains ("Swordsman", "Archer"; the castle: "Spy", and "Builder" when asked by name) or empty. */
	static FString TroopFor(const AActor* Building);
	/** Can Kind be trained there (its own troop; the castle: the Spy and Builders)? */
	static bool TrainsKind(const AActor* Building, const FString& Kind);
	/** Why one more (of Kind; empty: its own troop) cannot be queued there (being built, housing, price, the Builders'
	 *  limit), or empty. */
	FString TrainRefusal(const AActor* Building, const FString& Kind = FString()) const;
	/** Queues up to Count of Kind (empty: its own troop), each paid for and housed as it is queued. Returns how many. */
	int32 Train(AActor* Building, int32 Count = 1, bool bQuiet = false, const FString& Kind = FString());
	int32 QueueLength(const AActor* Building) const;
	/** 0..1 through the recruit at the head of its queue. */
	float TrainProgress(const AActor* Building) const;
	/** Seconds it takes to train one of Kind (empty: its own troop) at its level. */
	float TrainSeconds(const AActor* Building, const FString& Kind = FString()) const;
	/** bClear: no rally point (its recruits wait in its yard, or join the recruits' platoon). */
	void SetRally(AActor* Building, const FVector& Ground, bool bClear = false);
	void SetFeedPlatoon(AActor* Building, int32 Platoon);
	// ---- the Spy: castle level 3, one at a time, a wait between two (the main game's Scout rules)
	/** Spies alive, and (OutQueued) in training. */
	int32 GetSpyCount(int32 Team, int32* OutQueued = nullptr) const;
	/** Seconds until the kingdom may train another Spy (0 = now). */
	/** UVLCommand: these units were given an order (not one of their own doing). Those of a platoon ordered without
	 *  the rest of it are apart on purpose, and the platoon's cohesion leaves them alone until they are back with it or
	 *  the whole platoon is ordered again. */
	void NoteOrdered(const TArray<AVLKing*>& Units);
	/** For the log (vl.Cohesion): each platoon's members, who is apart on purpose, who is on its way to a fight. */
	void LogCohesion() const;
	float GetSpyCooldown(int32 Team) const { return SpyCooldownLeft[FMath::Clamp(Team, 0, 1)]; }
	void SetSpyCooldown(int32 Team, float Seconds) { SpyCooldownLeft[FMath::Clamp(Team, 0, 1)] = FMath::Max(0.f, Seconds); }
	/** Why the kingdom cannot train a Spy right now (castle level, one already, the wait), or empty. */
	FString SpyRefusal(int32 Team) const;
	/** Would a foe looking Range far notice Unit at Distance (a Spy: only within its Notice share of it)? */
	static bool IsNoticed(const AVLKing* Unit, float Distance, float Range);
	/** A troop on the ground at a point, of a team, with no training (tests, the starting armies). */
	AVLTroop* SpawnTroop(const FString& Kind, int32 Team, const FVector& Ground, float Yaw = 0.f);

	// ---- upgrades
	/** Why the building cannot be raised a level now (the top level, under way, the castle level a storehouse needs,
	 *  the price), or empty. */
	FString UpgradeRefusal(const AActor* Building, FVLCost* OutCost = nullptr) const;
	bool Upgrade(AActor* Building, bool bQuiet = false);
	/** A line of what it does at its level ("+14 food every 6 s, houses 4"). */
	FString Describe(const FVLBuildingState& B) const;

	// ---- orders the commander gives (the player's are UVLCommand's): a move on which they fight what they meet
	void AttackMove(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun, uint8 Shape);
	/** Every living unit of a team (Troops: not the king). */
	void GetUnits(int32 Team, TArray<AVLKing*>& Out, bool bTroopsOnly = false) const;

	// ---- the match
	/** The New Game screen's start (or vl.StartMatch): kingdoms' stock, starting armies, the commander. */
	void StartMatch(int32 Difficulty);
	/**
	 * The Test World (New Game > Test World: Realm v2 opened with ?TestWorld=1; the owner's call, 2026-11-22): a match
	 * that starts with both sides at their most, for trying the balance. Called once, right after StartMatch. Each
	 * side: its castle at level 7; two barracks, two archery ranges, a Granary, a Treasury, and farms and watch towers
	 * up to their limits, laid round the castle by the construction's own calls (FindPlacementNear, PlaceBuilding)
	 * and finished at once; every building at its top level; its stores full; troops up to the ceiling (three
	 * swordsmen to two archers; the player's in six platoons); every Builder it may have. The commander plays on as usual.
	 */
	void SetupTestWorld();
	bool IsTestWorld() const { return bTestWorld; }
	EVLMatch GetState() const { return State; }
	bool IsPlaying() const { return State == EVLMatch::Playing; }
	/** Both castles stand at the start: a real match (a commander, victory and defeat), not a sandbox. */
	bool IsBattle() const { return bBattle; }
	int32 GetWinner() const { return Winner; }
	/** Seconds since the castle fell (for the end screen's delay), or < 0. */
	float GetEndTime() const;
	float GetClock() const { return Clock; }
	int32 GetDifficulty() const { return Difficulty; }
	static const TCHAR* DifficultyName(int32 Difficulty);
	FVLCommander* GetCommander(int32 Team) const;
	/** A commander for the player's side too (balance tests: vl.AIvsAI), at a difficulty of its own (< 0: the match's). */
	void SetPlayerAI(bool bOn, int32 InDifficulty = -1);
	/** The balance log of this match, if one is kept (vl.MatchLog). */
	FVLMatchLog* GetMatchLog() const { return MatchLog.Get(); }
	/** The player's view of the enemy: "Enemy ready in 3:12", "Enemy watching", "Enemy attacking!". */
	FString EnemyStatus(FLinearColor* OutColour = nullptr) const;

	// ---- feedback
	void PushAlert(const FString& Text, EVLAlert Kind = EVLAlert::Info, const FVector* At = nullptr);
	const TArray<FVLAlert>& GetAlerts() const { return Alerts; }
	const TArray<FVLPopup>& GetPopups() const { return Popups; }
	/** Seconds since the unit was last hurt (health bars). */
	static constexpr float BarSeconds = 4.f;
	/** Plays /Game/Voxel/Audio/<Base>[_n] at a point (fading with the distance from where the player looks), or 2D. */
	void PlayAt(const TCHAR* Base, const FVector& At, float Volume, float Range = 4500.f, float Gap = 0.08f);
	void Play2D(const TCHAR* Base, float Volume = 0.6f);
	/** The player's own sound-effects setting, a share (Esc menu > Effects): applied by PlayAt / Play2D. */
	static float EffectsVolume;

	// ---- tests
	// ---- construction (VLConstruction.*)
	/** Pulls a building down (demolished by its own side: no alert of a loss, not counted as one). */
	void Raze(AActor* Building);
	friend struct FVLDuels;      // (balance duels: a tower raised at a level of its choosing)
	friend struct FVLSaveIO;     // (saved games, VLSave.*: the match's state read and put back)
	/** Takes a building out of the battle without a fall (a site cancelled, a level's barracks at a match's start). */
	void Forget(AActor* Building);

	/** Spawns an enemy base (copies of the level's castle, barracks, range, farm, mine and tower) at an offset, on
	 *  flat ground: a battlefield on any map (vl.TestBase). */
	int32 SpawnTestBase(const FVector& Offset, int32 Team);
	void LogStatus() const;

private:
	void ScanBuildings();
	void ApplyLevel(FVLBuildingState& B, bool bFull);
	void TickEconomy(float Dt);
	/** A king left alone (no blow for VLRules::KingRestDelay s) gets his health back at VLRules::KingRestRate a second. */
	void TickKingRest(float Dt);
	void TickTraining(float Dt);
	void TickUpgrades(float Dt);
	void TickDefence(float Dt);
	/** The watch towers' own archers: filled when a tower is first up (and by one when it is raised a level), a fallen
	 *  one replaced after VLRules::TowerGuardRestock; they go with the tower. */
	void TickTowerGuards(float Dt);
	/** One more archer of the tower's own on its lookout; false if there is no post free. */
	bool SpawnTowerGuard(int32 Slot);
	/** A tower's own archers go (it fell, was pulled down or changed hands). */
	void DismissTowerGuards(FVLBuildingState& B);
	void TickCollapse(float Dt);
	void TickAutoCombat(float Dt);
	/** Platoons keep together: see VLRules::CohesionLeash. */
	void TickCohesion(float Dt);
	struct FVLCohesion
	{
		int32 Platoon = INDEX_NONE;     // the platoon it was last seen in
		bool bApart = false;            // away from its platoon on purpose (an order of its own; joined from afar): left alone
		bool bSent = false;             // on its way to the platoon's fight: its post stays where it stood (Home)
		FVector Home = FVector::ZeroVector;
		double SentAt = -100.0;
	};
	TMap<TWeakObjectPtr<AVLKing>, FVLCohesion> Cohesion;
	float CohesionTimer = 0.f;
	bool bTestWorld = false;
	void TickKings(float Dt);
	/** Jonathan comes to his side's castle once it is at VLRules::JonathanCastleLevel, and again after he has fallen. */
	void TickJonathan(float Dt);
	TWeakObjectPtr<AVLTroop> Jonathans[2];
	float JonathanWait[2] = { 0.f, 0.f };       // seconds until he may come (back) to the castle
	bool bJonathanCame[2] = { false, false };   // he has been in this match before (the alert's wording)
	void SpawnRecruit(FVLBuildingState& B, const FString& Kind);
	void Collapse(FVLBuildingState& B, AActor* By, int32 ByTeam, bool bDemolished = false);
	void CheckEnd();
	/** Sends Unit at Target as if ordered (no marker, no click), remembering it was its own idea. */
	void Engage(AVLKing* Unit, AActor* Target);
	/** The best foe for a unit to go for within Range of it (troops before buildings), or null. */
	AActor* FindFoe(const AVLKing* Unit, float Range, bool bUnitsOnly = false) const;
	AActor* FindFoeIn(const AVLKing* Unit, float Range, bool bUnitsOnly, const TArrayView<AVLKing* const>& Among) const;
	FVLSoundSet* Sounds(const TCHAR* Base);

	TArray<FVLBuildingState> Buildings;
	// buildings by actor (FindBuilding): rebuilt when the array changes (RegisterBuilding, Forget)
	mutable TMap<const AActor*, int32> BuildingIndex;
	mutable bool bBuildingIndexDirty = true;
	// the unit registry and its spatial hash
	static constexpr float UnitCell = 400.f;
	TArray<AVLKing*> Registered;                    // every unit of the world, in the order they came into it
	mutable TArray<AVLKing*> LegacyUnits;           // vl.Opt.Registry 0: this call's TActorIterator walk
	mutable TArray<FIntPoint> HashCells;            // per unit (registry index): its cell
	mutable TArray<int32> HashStart;                // per bucket: where its units start in HashItems
	mutable TArray<int32> HashItems;                // registry indices, bucket after bucket, ascending in each
	mutable uint64 HashFrame = MAX_uint64;
	mutable bool bHashDirty = true;
	mutable FIntPoint HashMin = FIntPoint::ZeroValue, HashMax = FIntPoint::ZeroValue;
	FDelegateHandle SpawnedHandle, DestroyedHandle;
	void OnActorSpawned(AActor* Actor);
	void OnActorDestroyed(AActor* Actor);
	void EnsureUnitHash() const;
	// tagged actors
	mutable TArray<TWeakObjectPtr<AActor>> SelectableActors, DummyActors, MineNamedActors;
	mutable bool bTagsDirty = true;
	mutable double TagsReadAt = -100.0;
	void EnsureTags() const;
	void CheckRegistry();
	FVLKingdom Kingdoms[2];
	EVLMatch State = EVLMatch::Idle;
	bool bBattle = false;
	int32 Winner = -1;
	double EndedAt = -1.0;
	float Clock = 0.f;
	int32 Difficulty = 1;
	float ScanTimer = 0.f;
	float AutoTimer = 0.f;
	double LastTroopAlert = -100.0;
	float SpyCooldownLeft[2] = { 0.f, 0.f };
	TArray<FVLAlert> Alerts;
	TArray<FVLPopup> Popups;
	TMap<FString, int32> Numbers;          // "Swordsman" / "Enemy Swordsman" -> how many there have been (names)
	TSharedPtr<FVLCommander> Commanders[2];
	/** The balance log of this match (vl.MatchLog; VLMatchLog.*), while it is on. */
	TSharedPtr<FVLMatchLog> MatchLog;
	bool bRegrid = false;

	UPROPERTY(Transient)
	TMap<FString, FVLSoundSet> SoundSets;

	UPROPERTY(Transient)
	TObjectPtr<USoundAttenuation> Pan;
};
