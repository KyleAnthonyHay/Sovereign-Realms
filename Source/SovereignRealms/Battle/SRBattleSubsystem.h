// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "SRBattleSubsystem.generated.h"

class ASRUnit;
class UStaticMesh;
class UMaterialInterface;

UENUM()
enum class ESRBattleResult : uint8
{
	Ongoing,
	PlayerWon,
	EnemyWon
};

/**
 * Owns the battle: the unit registry, the per-frame simulation order
 * (think -> move -> push apart -> animate), scenario spawning / reset,
 * shared greybox assets, and the victory check.
 *
 * Units do not tick themselves; this subsystem steps them so every unit sees
 * a consistent world each frame.
 */
UCLASS()
class SOVEREIGNREALMS_API USRBattleSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static USRBattleSubsystem* Get(const UObject* WorldContext);

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	/** Destroys every unit / projectile / marker and spawns the scenario again. */
	void ResetBattle();

	ASRUnit* SpawnUnit(ESRUnitType Type, ESRTeam Team, const FVector2D& Location, float Yaw, float SpawnDelay);

	/** Both sides march at each other and fight to the end (debug / verification). */
	void SetAutoBattle(bool bEnabled);
	bool IsAutoBattle() const { return bAutoBattle; }

	/** Living units (may include ones still popping in; check IsActive()). */
	const TArray<TObjectPtr<ASRUnit>>& GetUnits() const { return Units; }

	ASRUnit* FindNearestEnemy(const ASRUnit* For, float Range) const;

	/** Closest unit hit by a ray (cursor picking). Units have no collision; this is pure maths. */
	ASRUnit* PickUnit(const FVector& RayOrigin, const FVector& RayDir, float Padding) const;

	/** Ground height under a point. RefZ is the height we expect to be near (so roofs / canopies above are ignored). */
	bool SampleGround(const FVector2D& XY, float RefZ, float& OutZ) const;

	/** Where a ray meets the ground (falls back to the Z=0 plane). */
	FVector RayToGround(const FVector& RayOrigin, const FVector& RayDir) const;

	/** True if something solid (wall, rock, trunk) lies between two points at knee height. */
	bool IsPathBlocked(const FVector& From, const FVector& To) const;

	/** Pulls To back toward From if a wall lies between them, leaving Clearance before the wall. */
	FVector2D ClipToReachable(const FVector& From, const FVector2D& To, float Clearance) const;

	void NotifyUnitDied(ASRUnit* Unit, const ASRUnit* Killer);

	/** Adds camera trauma, attenuated by distance from the camera focus. */
	void AddCameraTrauma(const FVector& WorldLocation, float Amount) const;

	FLinearColor TeamColor(ESRTeam Team) const;
	FVector2D TeamCentroid(ESRTeam Team) const;
	int32 CountAlive(ESRTeam Team) const;
	void LogStatus() const;

	ESRBattleResult GetResult() const { return Result; }
	float GetTimeSinceResult() const { return TimeSinceResult; }

	// Shared greybox assets (engine basic shapes) and the materials resolved per the visual contract.
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> CubeMesh;
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> CylinderMesh;
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> ConeMesh;
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> UnitMaterial;
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> RingMaterial;
	/** True when /Game/SR/Materials/M_UnitGreybox is missing and the engine basic-shape material is used instead. */
	bool bUnitMaterialIsFallback = true;

private:
	void SpawnScenario();
	void SpawnObstacles();
	void ResolveOverlaps(float DeltaTime);
	void CheckResult();
	void PollCommandInbox(float DeltaTime);

	UPROPERTY(Transient) TArray<TObjectPtr<ASRUnit>> Units;
	UPROPERTY(Transient) TArray<TObjectPtr<ASRUnit>> Corpses;
	UPROPERTY(Transient) TArray<TObjectPtr<AActor>> Obstacles;

	bool bBattleStarted = false;
	bool bAutoBattle = false;
	ESRBattleResult Result = ESRBattleResult::Ongoing;
	float TimeSinceResult = 0.f;
	float BattleClock = 0.f;
	float InboxTimer = 0.f;
};
