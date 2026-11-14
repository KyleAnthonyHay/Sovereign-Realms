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
 *   raids     sends a small party at an undefended farm or mine every AIRaidInterval to keep the foe honest.
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
	bool IsPlayerAI() const { return Commanders[0].bActive; }
	/** Seconds until the enemy's next main attack may leave (for the HUD's warning), negative once it is due. */
	float GetEnemyNextWaveIn() const;
	int32 GetEnemyWavesSent() const { return Commanders[1].WavesSent; }
	/** The enemy's main attack (or a raid) is out right now. */
	bool IsEnemyAttacking() const { return Commanders[1].Main.IsActive() || Commanders[1].Raid.IsActive(); }
	void LogStatus() const;

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
