// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Common/SRTypes.h"
#include "SRBuilding.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UBoxComponent;
class USRRingComponent;
class USREconomySubsystem;
class ASRUnit;
class ASRWorker;

/**
 * A kingdom building: the castle (the kingdom's seat), a farm (food, housing), a mine (gold), a watchtower, the
 * barracks (trains Shieldbearers) or the archery range (trains Archers).
 *
 * States (ESRBuildingState): a construction Site (SM_Bld_<Name>_Site scaffold round the walls, which rise course by
 * course), Complete, Damaged (SM_Bld_<Name>_Damaged below DamagedStateFraction of its health) and Ruin
 * (SM_Bld_<Name>_Ruin after it collapses). A missing state mesh just keeps the finished one.
 *
 * Placed in the level by Tools/build_battlefield_visuals.py from SourceArt/World/layout.json, which also fills in
 * the footprint and the sockets the Blender model exports (SourceArt/Buildings/<type>.json). The actor origin is on
 * the ground at the model's origin; the model's front (gate, adit, yard) faces local -X.
 *
 * The mesh has no collision. Movement is blocked by one box over the footprint (WorldStatic, so the units' wall
 * traces see it); ground and cursor traces ignore buildings. Team colour reaches the materials as custom primitive
 * data 0..2 (Docs/VISUAL_CONTRACT.md, "Buildings").
 *
 * USREconomySubsystem steps every building each frame: farms and mines pay out on a timer, a barracks or range works
 * through its recruit queue and sends each recruit to its rally point.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRBuilding : public AActor
{
	GENERATED_BODY()

public:
	ASRBuilding();

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	/**
	 * A building laid down at run time (the player's build menu, the enemy commander): shape and mesh come from
	 * Sovereign Feel > Buildings. Under construction it rises from its foundations over BuildTime and does nothing
	 * else; a finished one works straight away.
	 */
	static ASRBuilding* SpawnBuilding(UWorld* World, ESRBuildingType Type, ESRTeam Team, const FVector& Location, bool bUnderConstruction);

	/** Applies the properties below to the components (mesh, blocking box, team colour). */
	UFUNCTION(BlueprintCallable, CallInEditor, Category = "Building")
	void RefreshBuilding();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building")
	ESRBuildingType BuildingType = ESRBuildingType::Farm;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building")
	ESRTeam Team = ESRTeam::Player;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building")
	TObjectPtr<UStaticMesh> BuildingMesh;

	/** Blocking footprint in local XY (cm): units walk round it, the selection outline hugs it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building|Footprint")
	FVector2D FootprintMin = FVector2D(-400.f, -400.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building|Footprint")
	FVector2D FootprintMax = FVector2D(400.f, 400.f);

	/** Height of the blocking box, also what cursor picking tests. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building|Footprint", meta = (ClampMin = "50"))
	float BlockHeight = 300.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building|Footprint")
	float RingRadius = 600.f;

	/** Local point where a recruit appears (just outside the gate). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building|Sockets")
	FVector GateOffset = FVector(-600.f, 0.f, 0.f);

	/** Local default rally point. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building|Sockets")
	FVector RallyOffset = FVector(-760.f, 800.f, 0.f);

	/** Local point above the roof line: progress bars sit here. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building|Sockets")
	FVector LabelOffset = FVector(0.f, 0.f, 500.f);

	/** Local point the "+N" payout popups rise from. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Building|Sockets")
	FVector PopupOffset = FVector(0.f, 0.f, 300.f);

	// ---- life ----
	const FSRBuildingStats& Stats() const;
	bool IsAlive() const { return !bDestroyed; }
	/** Standing and fully built (works, counts for territory and population). */
	bool IsFinished() const { return !bDestroyed && BuildProgress >= 1.f; }
	bool IsUnderConstruction() const { return !bDestroyed && BuildProgress < 1.f; }
	float GetBuildProgress() const { return BuildProgress; }
	float GetHealth() const { return Health; }
	float GetHealthFrac() const;
	double GetLastDamagedTime() const { return LastDamagedTime; }
	/** Arrows and blades. From may be null (another building's arrow). */
	void ReceiveDamage(float Amount, ASRUnit* From);
	/** Pull down a building still under construction and get CancelRefund of its price back. */
	void CancelConstruction();
	/** Population this building lets its kingdom field right now. */
	int32 GetPopProvided() const;
	/** Where an arrow shot from From should land on this building (on the near wall, a little up). */
	FVector GetAimPointFrom(const FVector2D& From) const;
	/** Distance from a point to the footprint's edge (0 inside). */
	float DistanceToFootprint(const FVector2D& World) const;
	/** Nearest point on the footprint's edge (grown by Margin) to a point outside it. */
	FVector2D ClosestPointOnFootprint(const FVector2D& World, float Margin) const;

	// ---- run time (USREconomySubsystem) ----
	/** Back to the start of a battle: empty queue, timers at zero, default rally point. */
	void ResetRuntime();
	void StepBuilding(float Dt);

	/** Called by a worker who has just delivered a load (or by the timer when there are no workers): pays out. */
	void Deliver();

	/** Pays for a recruit and queues it. False (with feedback on the resource counters) if it cannot be afforded, the queue is full or the kingdom is at its population cap. */
	bool QueueRecruit(ESRUnitType Type);
	const TArray<ESRUnitType>& GetQueue() const { return Queue; }
	/** 0..1 through the recruit in training. */
	float GetBuildFraction() const;
	/** 0..1 toward the next payout (farm, mine). */
	float GetPayoutFraction() const;
	/** Seconds since this building last paid out (popups, the HUD pulse). */
	float GetTimeSincePayout() const { return TimeSincePayout; }

	void SetRallyPoint(const FVector2D& WorldXY);
	FVector2D GetRallyPoint() const { return RallyPoint; }

	// ---- queries ----
	FString GetDisplayName() const;
	/** Trains troops at all (finished barracks or range). */
	bool CanRecruit() const { return Stats().bRecruits && IsFinished(); }
	/** Is this the kind of building that trains Type (finished or not)? */
	bool Trains(ESRUnitType Type) const { return Stats().bRecruits && Stats().RecruitType == Type; }
	bool IsRecruiter() const { return Stats().bRecruits; }
	ESRBuildingState GetState() const { return State; }
	bool IsCastle() const { return BuildingType == ESRBuildingType::Castle; }
	FVector2D ToLocal2D(const FVector2D& World) const;
	FVector2D ToWorld2D(const FVector2D& Local) const;
	FVector LocalToWorldPoint(const FVector& Local) const;
	FVector GetGatePoint() const { return LocalToWorldPoint(GateOffset); }
	FVector GetLabelPoint() const { return LocalToWorldPoint(LabelOffset); }
	FVector GetPopupPoint() const { return LocalToWorldPoint(PopupOffset); }
	FVector2D GetFootprintCentre() const { return ToWorld2D((FootprintMin + FootprintMax) * 0.5f); }
	/** Is a world point inside the footprint grown by Margin? */
	bool ContainsXY(const FVector2D& World, float Margin) const;
	/** Nearest point outside the footprint grown by Margin (the point itself if it is already outside). */
	FVector2D PushOutside(const FVector2D& World, float Margin) const;
	/** Does the segment pass through the footprint grown by Margin? OutT = where it enters (0..1). */
	bool SegmentCrosses(const FVector2D& From, const FVector2D& To, float Margin, float& OutT) const;
	/** Cursor picking: ray against the footprint box. */
	bool RayHit(const FVector& Origin, const FVector& Dir, float& OutAlong) const;

	// ---- selection feedback ----
	void SetSelected(bool bInSelected);
	bool IsSelected() const { return bSelected; }
	void SetHovered(bool bInHovered) { bHovered = bInHovered; }

	/** Saved games: put the building back as it was (health, construction, ruin, queue, rally point). */
	void ApplySaved(float InHealth, float InProgress, bool bInDestroyed, const TArray<ESRUnitType>& InQueue, const FVector2D& InRally);

	// ---- builders ----
	/** Laid outside the castle's building zone: it only rises while a Builder works on it. */
	void SetNeedsBuilder(bool bNeeds) { NeedsBuilderState = bNeeds ? 1 : 0; }
	bool NeedsBuilder() const;
	/** A builder has something to do here: it is a site, or it stands damaged. */
	bool NeedsWork() const { return !bDestroyed && (BuildProgress < 1.f || Health < GetMaxHealth() - 0.5f); }

	// ---- castle levels ----
	/** The castle is upgraded level by level (Sovereign Feel > Buildings > Castle upgrades): more housing, more walls, a
	 * wider building zone. Other buildings stay at level 1. */
	int32 GetLevel() const { return Level; }
	bool IsUpgrading() const { return UpgradeProgress >= 0.f; }
	float GetUpgradeFraction() const { return FMath::Max(UpgradeProgress, 0.f); }
	/** A finished castle below the top level, not already being upgraded. */
	bool CanUpgrade() const;
	/** The price of the next level. */
	FSRCost GetUpgradeCost() const;
	/** Pays and starts the next level; false (with feedback) if it cannot. */
	bool StartUpgrade();
	/** Health with the castle's levels counted. */
	float GetMaxHealth() const;
	/** The building zone round it (the castle's TerritoryRadius, wider with each level). */
	float GetBuildZoneRadius() const;
	/** Saved games. */
	void SetLevelForLoad(int32 InLevel, float InUpgradeProgress);
	/** Builders at its walls working on it right now (counted each frame while it needs work). */
	int32 GetBuildersWorking() const { return BuildersWorking; }

	/** Set by SpawnBuilding: not part of the level, so it is destroyed (not just reset) when the battle resets. */
	bool IsRuntimeBuilt() const { return bRuntimeBuilt; }

private:
	void SpawnRecruit(ESRUnitType Type);
	void UpdateFeedback(float Dt);
	void StepConstruction(float Dt);
	void StepDefence(float Dt);
	void StepCollapse(float Dt);
	void Collapse(ASRUnit* Killer);
	void ApplyBuildVisual();
	void UpdateWorkers();
	void SetState(ESRBuildingState NewState);
	void LoadStateMeshes();

	UPROPERTY(VisibleAnywhere, Category = "Building") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, Category = "Building") TObjectPtr<UStaticMeshComponent> Mesh;
	/** One convex box over the footprint: what stops troops. */
	UPROPERTY(VisibleAnywhere, Category = "Building") TObjectPtr<UBoxComponent> Blocker;
	/** Selection / hover outline round the footprint. */
	UPROPERTY(Transient) TObjectPtr<USRRingComponent> Ring;
	/** Scaffold round the walls while it is built (SM_Bld_<Name>_Site). */
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> SiteMesh;
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> DamagedMeshAsset;
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> RuinMeshAsset;
	ESRBuildingState State = ESRBuildingState::Complete;
	/** Fire and smoke while it burns (damaged), smoke over the ruin. */
	TArray<TWeakObjectPtr<class ASRFXSprite>> StateFX;
	double LastDebrisTime = -10.0;
	void ClearStateFX(bool bKeepSmoke);
	/** The rally flag (barracks and range): planted at the rally point while the castle is selected or just after it moves. */
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> RallyFlag;

	UPROPERTY(Transient) TObjectPtr<USREconomySubsystem> Economy;

	UPROPERTY(Transient) TArray<TObjectPtr<ASRWorker>> Workers;

	TArray<ESRUnitType> Queue;
	float Health = 1.f;
	float BuildProgress = 1.f;
	bool bDestroyed = false;
	bool bRuntimeBuilt = false;
	float CollapseClock = 0.f;
	float DefenceCooldown = 0.f;
	float HitShake = 0.f;
	float HammerClock = 0.f;
	double LastDamagedTime = -100.0;
	FVector MeshBaseLocation = FVector::ZeroVector;
	float BuildClock = 0.f;
	float PayoutClock = 0.f;
	float TimeSincePayout = 1000.f;
	FVector2D RallyPoint = FVector2D::ZeroVector;
	float RallyShowTime = 0.f;
	float RallyPop = 0.f;
	int32 RecruitCount = 0;
	int8 NeedsBuilderState = -1;
	int32 Level = 1;
	float UpgradeProgress = -1.f;    // 0..1 while the next level is being built, -1 otherwise
	void StepUpgrade(float Dt);
	/** While it burns (damaged): the fire's steady roar (started in earshot, stopped out of it) and the odd flare-up. */
	void StepFireSound(float Dt);
	void StopFireSound(float Fade);
	TWeakObjectPtr<class UAudioComponent> FireSound;
	float FireRetry = 0.f;
	float CrackleClock = 0.f;     // -1 = not worked out yet (a saved game): asked of the economy on first need
	int32 BuildersWorking = 0;
	void CountBuilders();
	void StepRepair(float Dt);

	bool bSelected = false;
	bool bHovered = false;
	bool bRingVisible = false;
	float RingPop = 0.f;
};
