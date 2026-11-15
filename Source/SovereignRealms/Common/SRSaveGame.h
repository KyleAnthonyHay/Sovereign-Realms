// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"
#include "Common/SRTypes.h"
#include "SRSaveGame.generated.h"

USTRUCT()
struct FSRSavedUnit
{
	GENERATED_BODY()
	UPROPERTY() ESRUnitType Type = ESRUnitType::Shieldbearer;
	UPROPERTY() ESRTeam Team = ESRTeam::Player;
	UPROPERTY() FVector2D Pos = FVector2D::ZeroVector;
	UPROPERTY() float Yaw = 0.f;
	UPROPERTY() float Health = 1.f;
	UPROPERTY() ESRStance Stance = ESRStance::Aggressive;
	UPROPERTY() int32 Platoon = INDEX_NONE;
	UPROPERTY() FVector2D Home = FVector2D::ZeroVector;
};

USTRUCT()
struct FSRSavedBuilding
{
	GENERATED_BODY()
	/** A building placed in the level is matched by its actor name; one raised in the match is spawned again. */
	UPROPERTY() FString LevelName;
	UPROPERTY() ESRBuildingType Type = ESRBuildingType::Farm;
	UPROPERTY() ESRTeam Team = ESRTeam::Player;
	UPROPERTY() FVector Location = FVector::ZeroVector;
	UPROPERTY() float Health = 1.f;
	UPROPERTY() float BuildProgress = 1.f;
	UPROPERTY() bool bDestroyed = false;
	UPROPERTY() TArray<ESRUnitType> Queue;
	UPROPERTY() FVector2D Rally = FVector2D::ZeroVector;
	UPROPERTY() int32 Level = 1;
	UPROPERTY() float UpgradeProgress = -1.f;
	UPROPERTY() int32 AssignedPlatoon = INDEX_NONE;
};

USTRUCT()
struct FSRSavedPlatoon
{
	GENERATED_BODY()
	UPROPERTY() int32 Index = 0;
	UPROPERTY() FString Name;
	UPROPERTY() ESRFormationShape Formation = ESRFormationShape::Line;
	UPROPERTY() bool bFormation = true;
	UPROPERTY() ESRStance Stance = ESRStance::Aggressive;
	UPROPERTY() bool bReceivesRecruits = false;
};

USTRUCT()
struct FSRSavedCommander
{
	GENERATED_BODY()
	UPROPERTY() bool bActive = false;
	UPROPERTY() int32 BuildStep = 0;
	UPROPERTY() int32 WavesSent = 0;
	UPROPERTY() int32 RaidsSent = 0;
	UPROPERTY() int32 FoeAttacks = 0;
	UPROPERTY() float ShieldRatio = 0.55f;
};

/** One saved match (USRGameFlowSubsystem::SaveMatch / LoadMatch). */
UCLASS()
class SOVEREIGNREALMS_API USRSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	static constexpr int32 CurrentVersion = 1;

	UPROPERTY() int32 Version = CurrentVersion;
	UPROPERTY() FDateTime SavedAt;
	UPROPERTY() int32 Difficulty = 1;
	UPROPERTY() float BattleClock = 0.f;
	UPROPERTY() int32 Gold[2] = { 0, 0 };
	UPROPERTY() int32 Food[2] = { 0, 0 };
	/** Seconds each kingdom still waits before it may train another Scout (USREconomySubsystem::GetScoutCooldown). */
	UPROPERTY() float ScoutCooldown[2] = { 0.f, 0.f };
	UPROPERTY() TArray<int32> Stats;       // FSRMatchStats, flattened
	UPROPERTY() TArray<FSRSavedUnit> Units;
	UPROPERTY() TArray<FSRSavedBuilding> Buildings;
	UPROPERTY() TArray<FSRSavedPlatoon> Platoons;
	UPROPERTY() FSRSavedCommander Commanders[2];
	UPROPERTY() TArray<uint8> FogExplored;
	UPROPERTY() FVector2D CameraFocus = FVector2D::ZeroVector;
};
