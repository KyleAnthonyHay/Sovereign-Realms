// ================================================================================================================
// DEPRECATED: superseded by VoxelLab (VoxelLab/Source/VoxelLab). This module is the first draft of Sovereign Realms and
// is no longer developed. Its game logic was reimplemented there (VLBattle, VLEnemyAI, VLCommand, VLHUD, the combat
// components); the Builder, Scout, Medic, Catapult, Horseman, construction, fog of war and saves remain only here.
// See README.md at the repository root. Kept so the old project still builds; do not delete.
// ================================================================================================================
// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "SRAISubsystem.generated.h"

class ASRUnit;
class ASRBuilding;

/** A foe the commander has seen: where, what, how hurt, and when. */
struct FSRSighting
{
	TWeakObjectPtr<ASRUnit> Unit;
	FVector2D Pos = FVector2D::ZeroVector;
	ESRUnitType Type = ESRUnitType::Shieldbearer;
	float HealthFrac = 1.f;
	float Time = 0.f;
};

/** A body of troops sent out: the main attack, or a raid on an outlying farm or mine. */
struct FSRAttack
{
	TArray<TWeakObjectPtr<ASRUnit>> Units;
	TWeakObjectPtr<ASRBuilding> Target;
	FVector2D Goal = FVector2D::ZeroVector;
	int32 StartSize = 0;
	float Launched = 0.f;
	float LastFight = 0.f;
	float Reorder = 0.f;
	bool bRaid = false;

	bool IsActive() const { return Units.Num() > 0; }
	void Prune();
	void Gather(TArray<ASRUnit*>& Out, FVector2D& Centre) const;
};

/**
 * How hard the commander plays at one difficulty. Easy is a gentle opponent: a slower, smaller economy, late and
 * small attacks that need big odds, no raids, no adapting, no reinforcing. Hard is the full commander.
 */
struct FSRAIProfile
{
	float FirstAttack = 240.f;     // earliest main attack (s)
	float Advantage = 1.5f;        // strength it wants over the expected defence before attacking
	float Regroup = 90.f;          // pause after an attack ends (s)
	int32 AttackCap = 8;           // most troops in the first attack ...
	int32 AttackCapGrowth = 3;     // ... growing by this much per attack ...
	int32 AttackCapMax = 24;       // ... up to this
	bool bRaids = true;
	float FirstRaid = 360.f;
	float RaidInterval = 120.f;
	float AdaptWeight = 0.6f;      // how fully it answers the player's army mix (0 = never)
	float IncomeScale = 0.9f;      // share of its farms' and mines' output it actually gets
	float BuildCadence = 4.f;      // seconds between building decisions
	int32 MaxTowers = 4;
	int32 MaxFarms = 10;
	int32 RecruitQueue = 2;        // recruits it keeps queued per barracks / range
	float Think = 1.f;             // seconds between decisions
	float Garrison = 0.25f;        // share of the army kept home
	float RetreatHold = 0.7f;      // falls back when its local strength drops below this x the foe's
	bool bReinforce = true;
	bool bImpatient = true;        // attacks at even odds after waiting long
	int32 Builders = 2;            // builders it keeps (to build beyond its castle's zone and repair)
};

/** One kingdom's commander. Plain data + logic; owned by USRAISubsystem. */
struct FSRCommander
{
	ESRTeam Team = ESRTeam::Enemy;
	bool bActive = false;
	float ThinkClock = 0.f;
	int32 BuildStep = 0;
	float NextBuildTry = 0.f;
	/** A building that found no room is not tried again until then (so one bad spot never stalls the economy). */
	TMap<ESRBuildingType, float> BuildBlockedUntil;
	float LastHomeOrder = -100.f;
	bool bDefending = false;

	// ---- the main attack and raids ----
	FSRAttack Main;
	FSRAttack Raid;
	float NextWaveTime = 0.f;       // the main attack may leave from then on
	float NextRaidTime = 0.f;
	int32 WavesSent = 0;
	int32 RaidsSent = 0;
	float LastReinforce = -100.f;

	// ---- what it knows of the foe ----
	TArray<FSRSighting> Seen;
	float FoeArmyEstimate = 0.f;    // strength of the foe's army as last seen at its largest, decaying slowly
	float FoeArcherShare = 0.4f;    // of what it has seen
	int32 FoeAttacks = 0;           // times the foe has come at its buildings
	float LastFoeAttack = -1000.f;
	bool bFoeAtHome = false;        // a foe force is near our buildings right now
	float ShieldRatio = 0.55f;      // what it trains now (adapts to the foe)
	float NextScoutOrder = 0.f;     // when its Scout is next sent somewhere to look
};

/**
 * The enemy's commander (and, for balance testing, one for the player's side too: Sovereign Feel > AI > AI Plays
 * Player, or sr.AIvsAI 1).
 *
 * It plays by the player's rules and knows only what it has seen: every think it notes the foe's troops within
 * AISightRadius of its own troops and buildings and remembers them for AIMemoryTime (buildings, which do not move,
 * are known). From that it estimates strength (health x damage per troop, towers and the castle count too) and:
 *   economy   works through AIBuildOrder (barracks, farms, range, mines on free veins, towers toward the front),
 *             rebuilds a lost barracks or range, adds farms for housing and mines while veins are free;
 *   army      trains at its barracks and range toward a Shieldbearer share that answers what it has seen (more
 *             Shieldbearers into archers and towers, more Archers into a wall of shields), mustering in front of
 *             its castle;
 *   defence   meets a force near its buildings with enough to beat it (everyone, and the attack recalled, when
 *             it is outmatched at home), and keeps a bigger garrison against a foe that has attacked it;
 *   attack    picks the target worth most for the least resistance (an undefended mine over a towered farm; the
 *             castle once it is weak), and goes when its free army is AIAttackAdvantage times what it expects to
 *             meet there; strikes at once when the foe's army is caught away from home; reinforces an attack that
 *             is winning; falls back to regroup when the fight there turns against it;
 *   raids     sends a small party at an undefended farm or mine every AIRaidInterval to keep the foe honest;
 *   stores    builds a Granary / Treasury (and enlarges them) when its food / gold stores are full;
 *   scouting  (Normal, Hard) trains its one Scout when the rules allow (castle level 3, one at a time, the wait
 *             between two) and keeps it watching the foe's kingdom from a distance.
 * Difficulty (Easy / Normal / Hard) scales timing, the advantage it waits for and how fully it adapts; it never
 * gives the commander extra resources.
 */
UCLASS()
class SOVEREIGNREALMS_API USRAISubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static USRAISubsystem* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	void Reset();
	void Step(float Dt);

	/** Turns the player's-side commander on or off (balance testing). */
	void SetPlayerAI(bool bEnabled);
	/** Turns the enemy commander on or off (the sandbox: an enemy that never builds, recruits or attacks). */
	void SetEnemyCommander(bool bEnabled) { Commanders[1].bActive = bEnabled; }
	bool IsPlayerAI() const { return Commanders[0].bActive; }
	/** Seconds until the enemy's next main attack may leave (for the HUD's warning), negative once it is due. */
	float GetEnemyNextWaveIn() const;
	int32 GetEnemyWavesSent() const { return Commanders[1].WavesSent; }
	/** The enemy's main attack (or a raid) is out right now. */
	bool IsEnemyAttacking() const { return Commanders[1].Main.IsActive() || Commanders[1].Raid.IsActive(); }
	void LogStatus() const;

	/** Saved games: what of each commander's mind is worth keeping (its build order step, attacks made, what it
	 * has learned of the player); on load the clock is the battle's and the next attack waits a regroup. */
	void SaveState(struct FSRSavedCommander Out[2]) const;
	void LoadState(const struct FSRSavedCommander In[2], float BattleClock);

	/** The profile for the current difficulty (Sovereign Feel > AI > AI Difficulty). */
	static FSRAIProfile Profile();
	/** Share of a building's payout its kingdom gets: below 1 for an easier commander, 1 for the player. */
	float IncomeScale(ESRTeam Team) const;

	/** Fighting strength of one troop (health x damage, archers' reach counted), scaled by its health left. */
	static float UnitPower(ESRUnitType Type, float HealthFrac = 1.f);
	static float UnitPower(const ASRUnit* Unit);
	/** Fighting strength a finished building adds to troops defending near it (towers, the castle). */
	static float BuildingPower(const ASRBuilding* Building);

private:
	void Think(FSRCommander& C);
	void Observe(FSRCommander& C);
	void Adapt(FSRCommander& C);
	void ManageEconomy(FSRCommander& C, const TArray<ASRUnit*>& Mine);
	void ManageDefence(FSRCommander& C, TArray<ASRUnit*>& Home);
	void ManageAttack(FSRCommander& C, TArray<ASRUnit*>& Home);
	void ManageRaid(FSRCommander& C, TArray<ASRUnit*>& Home);
	/** Its Scout (if it has one) goes from one look-out to the next round the foe's kingdom, well outside the
	 * distance at which it would be noticed; hurt, it comes home. What it sees feeds Observe like any troop's eyes. */
	void ManageScout(FSRCommander& C, const TArray<ASRUnit*>& Mine);
	void StepAttack(FSRCommander& C, FSRAttack& A);
	void EndAttack(FSRCommander& C, FSRAttack& A, const TCHAR* Why);
	bool TryBuild(FSRCommander& C, ESRBuildingType Type);
	void Recruit(FSRCommander& C, const TArray<ASRUnit*>& Mine);

	FVector2D MusterPoint(const FSRCommander& C) const;
	FVector2D TowardFoe(const FSRCommander& C) const;
	/** What it expects to meet at a point: seen troops (weighted by how far they are), towers in range, and the unseen rest of the foe's army if near the foe's castle. */
	float ExpectedDefence(const FSRCommander& C, const FVector2D& At, bool bSeenOnly = false) const;
	/** Foes it can see right now near a point, plus towers covering it. */
	float LocalFoePower(const FSRCommander& C, const FVector2D& At, float Radius) const;
	ASRBuilding* PickTarget(const FSRCommander& C, const FVector2D& From, float Power, bool bRaid, float* OutDefence = nullptr) const;
	float DifficultyScale(float Easy, float Normal, float Hard) const;
	static float SumPower(const TArray<ASRUnit*>& Units);

	FSRCommander Commanders[2];
	float Clock = 0.f;
};
