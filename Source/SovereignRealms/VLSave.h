#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLSave.generated.h"

class UVLBattle;

/**
 * SAVED GAMES. A match in progress is written to a slot (Saved/SaveGames/VL_<slot>.sav, the engine's own save-game
 * files: UGameplayStatics::SaveGameToSlot of a UVLSaveGame) and read back into the same state.
 *
 *   slots       five the player picks from (Slot1 .. Slot5: the pause menu's Save Game), the quicksave (Quick: F5,
 *               F9 loads it) and the autosave (Auto: every vl.Autosave.Minutes of play, 3 by default; one slot,
 *               written over each time). Load Game (the pause menu, the title screen) lists all seven; Continue (the
 *               title screen) loads whichever was saved last.
 *   saving      FVLSaveIO::Capture reads the battle (UVLBattle: the clock, both kingdoms, every building), the units
 *               (AVLKing / AVLTroop: where, how hurt, what they are on), the orders (UVLCommand: platoons, patrols and
 *               attack-moves, guards, followers, roaming Spies, tower garrisons), the Builders' jobs and queues, the
 *               troop ships (UVLFleet: where, their course, who is aboard), both commanders (FVLCommander: its clocks,
 *               its posture, its squads, what it has seen), the fog of war (UVLFog: the explored cells, run-length
 *               coded, and the enemy buildings seen) and the player's view (who is played, both cameras).
 *   loading     UVLSaves::Load checks the file (its version, its map) and opens the save's map the way New Game does
 *               (so the loading screen shows), with the slot kept aside; when the match starts there
 *               (UVLBattle::StartMatch, before the battle's first tick) FVLSaveIO::Apply puts the saved state in the
 *               place of the fresh match's: the level's buildings take their saved state, the ones raised in the match
 *               are raised again, the starting army gives way to the saved units, and the orders are given again.
 *   versions    UVLSaveGame::Version is written with every save. A save from a newer game, or one older than
 *               MinVersion, is not loaded: the menu says why. Within those, fields added since simply keep their
 *               defaults (the engine's tagged properties), and a building or a unit whose kind or mesh is gone is left
 *               out, counted and reported, never a crash.
 *
 * NOT restored (each comes back by itself within moments): arrows in flight, a swing or a draw half done, a unit's
 * own fight of the moment (it finds its foe again; an ORDERED attack is given again), Shift-queued attack chains, the
 * gait and cape poses, hit flashes, alerts and payout popups, the balance log (vl.MatchLog), the commanders'
 * influence maps and event lists (rebuilt from what they see), a building mid-collapse (it is down), a ship in the
 * middle of its docking move (it lies docked).
 *
 * Console: vl.Save <slot>, vl.Load <slot>, vl.Saves, vl.SaveDump <name> (the live state as JSON, for Tools/save_test.py),
 * vl.Autosave.Minutes.
 */

USTRUCT()
struct FVLSavedKingdom
{
	GENERATED_BODY()

	UPROPERTY() int32 Gold = 0;
	UPROPERTY() int32 Food = 0;
	UPROPERTY() int32 Recruited = 0;
	UPROPERTY() int32 Lost = 0;
	UPROPERTY() int32 Killed = 0;
	UPROPERTY() int32 BuildingsLost = 0;
	UPROPERTY() bool bHasCastle = false;
	UPROPERTY() TArray<int32> RecruitedKind;
	UPROPERTY() TArray<int32> LostKind;
	UPROPERTY() TArray<int32> Earned;
	UPROPERTY() TArray<int32> Wasted;
	UPROPERTY() TArray<int32> Spent;
	UPROPERTY() TArray<float> DamageBy;
	UPROPERTY() TArray<float> BuildingDamageBy;
	UPROPERTY() TArray<int32> KillsBy;
	// the match's side clocks
	UPROPERTY() float SpyCooldown = 0.f;
	UPROPERTY() float JonathanWait = 0.f;
	UPROPERTY() bool bJonathanCame = false;
	UPROPERTY() int32 FarmVariant = -1;
};

USTRUCT()
struct FVLSavedBuilding
{
	GENERATED_BODY()

	/** The level's own actor (its name in the map), or empty: raised in the match (spawned again from Mesh). */
	UPROPERTY() FString LevelActor;
	UPROPERTY() FString Kind;               // VLRules::Name
	UPROPERTY() FString Name;
	UPROPERTY() FString Mesh;
	UPROPERTY() int32 Team = 0;
	UPROPERTY() FVector Location = FVector::ZeroVector;     // where it stands (its rest: not sunk, not shaking)
	UPROPERTY() FRotator Rotation = FRotator::ZeroRotator;
	UPROPERTY() int32 Level = 1;
	UPROPERTY() float Health = 0.f;
	UPROPERTY() float UpgradeLeft = -1.f;
	UPROPERTY() float UpgradeTotal = 0.f;
	UPROPERTY() float Payout = 0.f;
	UPROPERTY() float Defence = 0.f;
	UPROPERTY() bool bDestroyed = false;
	UPROPERTY() TArray<FString> Queue;
	UPROPERTY() float TrainClock = 0.f;
	UPROPERTY() int32 Trained = 0;
	UPROPERTY() int32 FeedPlatoon = -1;
	UPROPERTY() bool bHasRally = false;
	UPROPERTY() FVector Rally = FVector::ZeroVector;
	UPROPERTY() float Build = 1.f;
	UPROPERTY() bool bRuntime = false;
	UPROPERTY() int32 PaidGold = 0;
	UPROPERTY() int32 PaidFood = 0;
	UPROPERTY() int32 GuardLevel = 0;
	UPROPERTY() float GuardRestock = 0.f;
	UPROPERTY() bool bClaim = false;        // a mine being claimed (tag Claim)
	UPROPERTY() bool bWasNeutral = false;   // ... that was a neutral one (a cancelled claim gives it back)
	/** Who waits at each place of its yard (unit indices, -1 an empty place). */
	UPROPERTY() TArray<int32> Yard;
};

USTRUCT()
struct FVLSavedTask
{
	GENERATED_BODY()

	UPROPERTY() bool bMove = false;
	UPROPERTY() FVector Point = FVector::ZeroVector;
	UPROPERTY() int32 Building = -1;
	UPROPERTY() bool bRun = false;
};

/** A reference to something of the save: -1 nothing, 0.. a unit, 100000.. a building, 200000.. a ship. */
namespace VLSaveRef
{
	constexpr int32 None = -1;
	constexpr int32 Building = 100000;
	constexpr int32 Ship = 200000;
}

USTRUCT()
struct FVLSavedUnit
{
	GENERATED_BODY()

	UPROPERTY() FString Kind;
	UPROPERTY() FString Name;
	UPROPERTY() int32 Team = 0;
	UPROPERTY() bool bTroop = true;
	UPROPERTY() FVector Feet = FVector::ZeroVector;
	UPROPERTY() float Yaw = 0.f;
	UPROPERTY() float Health = 100.f;
	UPROPERTY() bool bDead = false;         // (a king only: fallen troops are not saved)
	UPROPERTY() float DeadTime = 0.f;
	UPROPERTY() uint8 Stance = 0;
	UPROPERTY() bool bAttackMove = false;
	UPROPERTY() bool bSiege = false;
	UPROPERTY() bool bHoldOrder = false;
	UPROPERTY() bool bTowerGuard = false;
	UPROPERTY() bool bArmed = false;
	UPROPERTY() FVector Post = FVector::ZeroVector;
	// the walk it is on, and its pathway after it
	UPROPERTY() bool bWalking = false;
	UPROPERTY() bool bRun = false;
	UPROPERTY() FVector Goal = FVector::ZeroVector;
	UPROPERTY() TArray<FVector> Legs;
	UPROPERTY() TArray<bool> LegRuns;
	// where it stands that is not the ground
	UPROPERTY() int32 Garrison = -1;        // a VLSaveRef: the tower whose lookout it is on, or the ship it is aboard
	UPROPERTY() int32 ShipPlace = -1;
	UPROPERTY() int32 Heading = -1;         // a VLSaveRef: the tower it is walking to, the ship it is walking to board
	// the attack it was ordered to (not one of its own accord)
	UPROPERTY() int32 Attack = -1;          // a VLSaveRef
	// a Builder
	UPROPERTY() int32 Job = -1;             // a building index
	UPROPERTY() TArray<FVLSavedTask> Tasks;
};

USTRUCT()
struct FVLSavedPlatoon
{
	GENERATED_BODY()

	UPROPERTY() TArray<int32> Members;
	UPROPERTY() uint8 Formation = 0;
	UPROPERTY() uint8 Stance = 0;
	UPROPERTY() bool bMarchTogether = true;
	UPROPERTY() int32 Leader = -1;
};

USTRUCT()
struct FVLSavedRoute
{
	GENERATED_BODY()

	UPROPERTY() TArray<int32> Members;
	UPROPERTY() TArray<FVector> Points;
	UPROPERTY() int32 Next = 0;
	UPROPERTY() bool bLoop = true;
	UPROPERTY() bool bRun = false;
	UPROPERTY() uint8 Shape = 0;
};

USTRUCT()
struct FVLSavedGuard
{
	GENERATED_BODY()

	UPROPERTY() TArray<int32> Units;
	UPROPERTY() int32 Ward = -1;            // a VLSaveRef
	UPROPERTY() int32 Platoon = -1;
};

USTRUCT()
struct FVLSavedFollow
{
	GENERATED_BODY()

	UPROPERTY() TArray<int32> Units;
	UPROPERTY() int32 Leader = -1;
};

USTRUCT()
struct FVLSavedShip
{
	GENERATED_BODY()

	UPROPERTY() int32 Team = 0;
	UPROPERTY() FVector Location = FVector::ZeroVector;
	UPROPERTY() float Yaw = 0.f;
	UPROPERTY() float Speed = 0.f;
	/** 0 lying still, 1 under sail to Target (then Waypoints), 2 on patrol round Patrol. */
	UPROPERTY() uint8 Course = 0;
	UPROPERTY() FVector Target = FVector::ZeroVector;
	UPROPERTY() TArray<FVector> Waypoints;
	UPROPERTY() TArray<FVector> Patrol;
	UPROPERTY() int32 PatrolNext = 0;
	UPROPERTY() bool bLanded = false;
};

USTRUCT()
struct FVLSavedSighting
{
	GENERATED_BODY()

	UPROPERTY() int32 Unit = -1;
	UPROPERTY() FVector2D Pos = FVector2D::ZeroVector;
	UPROPERTY() bool bRanged = false;
	UPROPERTY() bool bKing = false;
	UPROPERTY() float HealthFrac = 1.f;
	UPROPERTY() float Time = 0.f;
};

USTRUCT()
struct FVLSavedSquad
{
	GENERATED_BODY()

	UPROPERTY() int32 Id = 0;
	UPROPERTY() uint8 Role = 0;
	UPROPERTY() uint8 Task = 0;
	UPROPERTY() TArray<int32> Units;
	UPROPERTY() int32 Target = -1;          // a VLSaveRef
	UPROPERTY() FVector Goal = FVector::ZeroVector;
	UPROPERTY() FString GoalName;
	UPROPERTY() int32 StartSize = 0;
	UPROPERTY() float StartPower = 0.f;
	UPROPERTY() float TaskSince = 0.f;
	UPROPERTY() float LastFight = 0.f;
	UPROPERTY() float Departs = 0.f;
	UPROPERTY() TArray<FVector> Via;
	UPROPERTY() float TargetHealth = -1.f;
	UPROPERTY() float ProgressAt = 0.f;
	UPROPERTY() float ProgressDealt = -1.f;
};

USTRUCT()
struct FVLSavedCommander
{
	GENERATED_BODY()

	UPROPERTY() bool bSaved = false;
	UPROPERTY() int32 Difficulty = 1;
	UPROPERTY() bool bActive = false;
	UPROPERTY() float Clock = 0.f;
	UPROPERTY() float ThinkClock = 0.f;
	UPROPERTY() float StrategyClock = 0.f;
	UPROPERTY() float MicroClock = 0.f;
	UPROPERTY() float FoeArmyEstimate = 0.f;
	UPROPERTY() float FoeArcherShare = 0.4f;
	UPROPERTY() int32 FoeAttacks = 0;
	UPROPERTY() float LastFoeAttack = -1000.f;
	UPROPERTY() float ThreatSince = -1.f;
	UPROPERTY() float LastRaided = -1000.f;
	UPROPERTY() FVector RaidedAt = FVector::ZeroVector;
	UPROPERTY() uint8 Posture = 0;
	UPROPERTY() float PostureSince = 0.f;
	UPROPERTY() FString PostureWhy;
	UPROPERTY() int32 ContestPoint = -1;
	UPROPERTY() int32 NextSquadId = 1;
	UPROPERTY() float NextWaveTime = 0.f;
	UPROPERTY() float NextRaidTime = 0.f;
	UPROPERTY() int32 WavesSent = 0;
	UPROPERTY() int32 RaidsSent = 0;
	UPROPERTY() float LastReinforce = -100.f;
	UPROPERTY() float ShieldRatio = 0.55f;
	UPROPERTY() float NextSpyOrder = 0.f;
	UPROPERTY() float NextBuildTry = 2.f;
	UPROPERTY() float NextGarrison = 0.f;
	UPROPERTY() int32 BuildStep = 0;
	UPROPERTY() TArray<int32> Stat;
	UPROPERTY() TArray<FVLSavedSquad> Squads;
	UPROPERTY() TArray<FVLSavedSighting> Seen;
};

/** The fog of war (UVLFog): what the player has explored, run-length coded (pairs of a byte value and a count of up
 *  to 255), and the enemy buildings seen at least once (building indices). */
USTRUCT()
struct FVLSavedFog
{
	GENERATED_BODY()

	UPROPERTY() int32 Dim = 0;
	UPROPERTY() float Cell = 0.f;
	UPROPERTY() FVector2D Origin = FVector2D::ZeroVector;
	UPROPERTY() TArray<uint8> ExploredRle;
	UPROPERTY() TArray<int32> SeenBuildings;
};

/** A saved match. The head (Version .. PlayerPop) is all the menus read. */
UCLASS()
class SOVEREIGNREALMS_API UVLSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	/** The save format now, and the oldest this game still reads. Raise Version when the saved state changes meaning
	 *  (a field added needs nothing: it keeps its default in an older save); raise MinVersion when an old save can no
	 *  longer be put back sensibly. */
	static constexpr int32 CurrentVersion = 1;
	static constexpr int32 MinVersion = 1;

	UPROPERTY() int32 Version = 0;
	UPROPERTY() FString MapPath;            // "/Game/Maps/L_RealmV3"
	UPROPERTY() FString MapTitle;           // "Realm v3", as the menus name it
	UPROPERTY() bool bTestWorld = false;
	UPROPERTY() int32 Difficulty = 1;
	UPROPERTY() float Clock = 0.f;          // seconds played
	UPROPERTY() FDateTime SavedAt;          // local time
	UPROPERTY() int32 PlayerGold = 0;
	UPROPERTY() int32 PlayerFood = 0;
	UPROPERTY() int32 PlayerPop = 0;

	// ---- the battle
	UPROPERTY() bool bBattle = false;
	UPROPERTY() TArray<FVLSavedKingdom> Kingdoms;
	UPROPERTY() TMap<FString, int32> Numbers;
	UPROPERTY() TArray<FVLSavedBuilding> Buildings;
	UPROPERTY() TArray<FVLSavedUnit> Units;
	UPROPERTY() TArray<FVLSavedShip> Ships;
	UPROPERTY() TArray<FVLSavedCommander> Commanders;
	UPROPERTY() FVLSavedFog Fog;            // (Dim 0: no fog then, or a save from before it)

	// ---- the orders
	UPROPERTY() TArray<FVLSavedPlatoon> Platoons;
	UPROPERTY() int32 RallyPlatoon = -1;
	UPROPERTY() uint8 LooseFormation = 0;
	UPROPERTY() bool bLooseMarchTogether = true;
	UPROPERTY() TArray<FVLSavedRoute> Routes;
	UPROPERTY() TArray<FVLSavedGuard> Guards;
	UPROPERTY() TArray<FVLSavedFollow> Follows;
	UPROPERTY() TArray<int32> Roamers;
	UPROPERTY() TArray<int32> Selection;

	// ---- the player's view
	UPROPERTY() int32 Played = -1;          // the unit the player has the controls of
	UPROPERTY() bool bHeroMode = true;
	UPROPERTY() float CamYaw = 0.f;
	UPROPERTY() float Zoom = 0.19f;
	UPROPERTY() float LookPitch = 0.f;
	UPROPERTY() FVector OverviewFocus = FVector::ZeroVector;
	UPROPERTY() float OverviewYaw = 0.f;
	UPROPERTY() float OverviewZoom = 0.18f;
};

/** What the menus show of a slot. */
struct FVLSaveInfo
{
	FString Slot;                   // "Slot1" .. "Slot5", "Quick", "Auto"
	bool bExists = false;
	/** Empty: it can be loaded. Else why not ("Made by a newer version of the game", "Its map is missing", ...). */
	FString Problem;
	FString MapTitle;
	FString MapPath;
	bool bTestWorld = false;
	int32 Difficulty = 1;
	float Clock = 0.f;
	FDateTime SavedAt;
	int32 Version = 0;
	int32 Gold = 0, Food = 0, Pop = 0;

	bool CanLoad() const { return bExists && Problem.IsEmpty(); }
};

/** The saved games of this world: saving, loading, the autosave. See the top of this file. */
UCLASS()
class SOVEREIGNREALMS_API UVLSaves : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLSaves* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Tick(float DeltaSeconds) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UVLSaves, STATGROUP_Tickables); }

	// ---- the slots
	static constexpr int32 NumManualSlots = 5;
	static const TCHAR* QuickSlot() { return TEXT("Quick"); }
	static const TCHAR* AutoSlot() { return TEXT("Auto"); }
	/** "Slot1" .. "Slot5". */
	static FString ManualSlot(int32 Index);
	/** Every slot in the menus' order: the five, then Quick, then Auto. */
	static TArray<FString> AllSlots();
	/** "Slot 3", "Quicksave", "Autosave". */
	static FString SlotTitle(const FString& Slot);
	/** A slot by what the console is given: "1".."5", "slot3", "quick", "auto" (any case); empty: no such slot. */
	static FString SlotFromArg(const FString& Arg);
	/** The file's name in Saved/SaveGames (without .sav). */
	static FString FileName(const FString& Slot);
	/** What is in a slot (the file read, and kept until the file changes). */
	static FVLSaveInfo GetInfo(const FString& Slot);
	/** The slot saved last that can be loaded; false: none. */
	static bool MostRecent(FVLSaveInfo& Out);
	static FString DateText(const FDateTime& When);

	// ---- saving and loading
	/** Why the match cannot be saved now (none is on, it has ended), or empty. */
	FString SaveRefusal() const;
	/** Writes the match to the slot. False: OutWhy says why. bQuiet: no alert for the player. */
	bool Save(const FString& Slot, FString* OutWhy = nullptr, bool bQuiet = false);
	/** Checks the slot and opens its map with the save put back as the match starts there. False: OutWhy says why
	 *  (nothing is changed then: the match in progress carries on). */
	bool Load(const FString& Slot, FString* OutWhy = nullptr);
	/** UVLBattle::StartMatch, once its fresh match stands: a save waiting for this map is put in its place. */
	static void OnMatchStarted(UVLBattle* Battle);
	/** This world's match came from a save. */
	static bool WasRestored(const UObject* WorldContext);
	/** A save is waiting for the map being opened (the title screen is not shown over it). */
	static bool IsLoadPending();
	/** Seconds until the next autosave (a match being played), or < 0. */
	float AutosaveIn() const;

	/** What the last save / load here said (the menus' line), and when (real seconds). */
	FString LastMessage;
	bool bLastFailed = false;
	double LastMessageAt = -100.0;

private:
	void Say(const FString& Text, bool bFailed);
	float SinceAutosave = 0.f;
	bool bRestored = false;
	/** What the restore could not put back, said to the player once the match is on screen. */
	FString RestoreNote;
	float RestoreNoteIn = -1.f;
};
