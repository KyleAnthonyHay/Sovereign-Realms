// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "SRAISubsystem.generated.h"

class ASRUnit;
class ASRBuilding;

/** One kingdom's commander. Plain data + logic; owned by USRAISubsystem. */
struct FSRCommander
{
	ESRTeam Team = ESRTeam::Enemy;
	bool bActive = false;
	float ThinkClock = 0.f;
	int32 BuildStep = 0;
	float NextWaveTime = 0.f;
	int32 WavesSent = 0;
	TArray<TWeakObjectPtr<ASRUnit>> Wave;
	int32 WaveStartSize = 0;
	float WaveLaunched = 0.f;
	float WaveLastFight = 0.f;
	TWeakObjectPtr<ASRBuilding> WaveTarget;
	FVector2D WaveGoal = FVector2D::ZeroVector;
	float WaveReorder = 0.f;
	bool bDefending = false;
	float NextBuildTry = 0.f;
	float LastHomeOrder = -100.f;
};

/**
 * The enemy's commander (and, for balance testing, one for the player's side too: Sovereign Feel > AI > AI Plays
 * Player, or sr.AIvsAI 1).
 *
 * What it does, every AIThinkInterval seconds, with the same rules and information the player has (no map hacks;
 * it does not see the player's troops before they are near its own buildings or its wave):
 *   economy   works through AIBuildOrder (farms, mines on free veins, towers toward the front) as gold allows, then
 *             keeps adding farms when housing runs short and mines while veins are free;
 *   army      recruits continuously toward AIShieldRatio within food and housing, gathering at a muster point in
 *             front of its castle;
 *   defence   anything of the player's near its buildings draws the whole home army (and recalls a wave that has
 *             barely left);
 *   waves     from AIFirstWaveTime, every AIWaveInterval, once the muster holds the wave size (growing each time),
 *             all but a garrison march on the player's nearest building and fight on to the castle; a wave that is
 *             down to AIRetreatFraction and outnumbered falls back.
 * Difficulty (Easy / Normal / Hard) scales wave timing and size; it never gives the commander extra resources.
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
	/** Seconds until the enemy's next wave may leave (for the HUD's warning), negative once it is due. */
	float GetEnemyNextWaveIn() const;
	int32 GetEnemyWavesSent() const { return Commanders[1].WavesSent; }
	void LogStatus() const;

private:
	void Think(FSRCommander& C);
	void ManageEconomy(FSRCommander& C, const TArray<ASRUnit*>& Mine);
	void ManageArmy(FSRCommander& C, TArray<ASRUnit*>& Home, const TArray<ASRUnit*>& Mine);
	void ManageWave(FSRCommander& C);
	bool TryBuild(FSRCommander& C, ESRBuildingType Type);
	FVector2D MusterPoint(const FSRCommander& C) const;
	FVector2D TowardFoe(const FSRCommander& C) const;
	ASRBuilding* PickWaveTarget(const FSRCommander& C, const FVector2D& From) const;
	float DifficultyScale(float Easy, float Normal, float Hard) const;

	FSRCommander Commanders[2];
	float Clock = 0.f;
};
