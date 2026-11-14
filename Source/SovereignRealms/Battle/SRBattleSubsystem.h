// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "Units/SRSprite.h"
#include "SRBattleSubsystem.generated.h"

class ASRUnit;
class UStaticMesh;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class ADirectionalLight;

/** Debug: what sr.ShotOn waits for before freezing the battle and saving a screenshot. */
enum class ESRShotEvent : uint8
{
	None,
	Strike,   // a unit's Strike(): melee damage lands / the arrow leaves
	Hit,      // a unit takes damage
	Death
};

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
 * the shared sprite assets and per-frame sprite view, and the victory check.
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
	/** Called from ASRUnit::Strike / ReceiveDamage on the frame it happens (debug capture hook, see ArmShot). */
	void NotifyStrike(ASRUnit* Unit) { OnShotEvent(ESRShotEvent::Strike, Unit); }
	void NotifyHit(ASRUnit* Unit) { OnShotEvent(ESRShotEvent::Hit, Unit); }

	/** Camera axes, sun direction and shadow-card transform shared by every sprite this frame. */
	const FSRSpriteView& GetSpriteView() const { return SpriteView; }
	UMaterialInterface* GetSpriteMaterial(ESRUnitType Type) const;
	UMaterialInterface* GetSpriteShadowMaterial(ESRUnitType Type) const;

	/**
	 * Debug (sr.ShotOn): the next time Event happens to a unit of UnitType (-1 = any) and Team (-1 = any), freeze the battle on that
	 * frame, centre the camera on the unit, let the image settle, save Saved/Screenshots/SR/<Name>.png, then carry on.
	 */
	void ArmShot(ESRShotEvent Event, const FString& Name, int32 UnitType, int32 Team);
	/** True while a debug capture holds the battle still; projectiles pause too. */
	bool IsFrozen() const { return FreezeFramesLeft > 0; }

	/** Adds camera trauma, attenuated by distance from the camera focus. */
	void AddCameraTrauma(const FVector& WorldLocation, float Amount) const;

	FLinearColor TeamColor(ESRTeam Team) const;
	FVector2D TeamCentroid(ESRTeam Team) const;
	int32 CountAlive(ESRTeam Team) const;
	void LogStatus() const;

	ESRBattleResult GetResult() const { return Result; }
	float GetTimeSinceResult() const { return TimeSinceResult; }

	// Shared sprite assets (Docs/VISUAL_CONTRACT.md, "Troop sprites"). Units and arrows hold no material instances
	// of their own: the frame, team colour, flash and fade travel as custom primitive data.
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> UnitCardMesh;
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> ArrowCardMesh;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> SpriteMaterials[2];
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> SpriteShadowMaterials[2];
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> ArrowMaterial;
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> ArrowShadowMaterial;
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> BlobMaterial;
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> RingMaterial;

	// Only for the optional grey test blocks (Sovereign Feel > Scenario > Spawn Greybox Obstacles).
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> CubeMesh;
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> GreyboxMaterial;

private:
	void SpawnScenario();
	void SpawnObstacles();
	void ResolveOverlaps(float DeltaTime);
	void CheckResult();
	void PollCommandInbox(float DeltaTime);
	void UpdateSpriteView();
	void UpdateSpriteLook();
	void OnShotEvent(ESRShotEvent Event, ASRUnit* Unit);
	void IgnoreBuildings(struct FCollisionQueryParams& Params) const;

	UPROPERTY(Transient) TArray<TObjectPtr<ASRUnit>> Units;
	UPROPERTY(Transient) TArray<TObjectPtr<ASRUnit>> Corpses;
	UPROPERTY(Transient) TArray<TObjectPtr<AActor>> Obstacles;

	bool bBattleStarted = false;
	bool bAutoBattle = false;
	ESRBattleResult Result = ESRBattleResult::Ongoing;
	float TimeSinceResult = 0.f;
	float BattleClock = 0.f;
	float InboxTimer = 0.f;

	FSRSpriteView SpriteView;
	TWeakObjectPtr<ADirectionalLight> Sun;
	bool bSunSearched = false;
	FVector4 AppliedSpriteLook = FVector4(-1.f, -1.f, -1.f, -1.f);
	FLinearColor AppliedFlashColor = FLinearColor(-1.f, -1.f, -1.f);

	// debug capture (sr.ShotOn)
	ESRShotEvent ArmedEvent = ESRShotEvent::None;
	FString ArmedShotName;
	int32 ArmedUnitType = -1;
	int32 ArmedTeam = -1;
	TWeakObjectPtr<ASRUnit> ArmedUnit;
	int32 FreezeFramesLeft = 0;
	bool bShotPending = false;
};
