// ================================================================================================================
// DEPRECATED: superseded by VoxelLab (VoxelLab/Source/VoxelLab). This module is the first draft of Sovereign Realms and
// is no longer developed. Its game logic was reimplemented there (VLBattle, VLEnemyAI, VLCommand, VLHUD, the combat
// components); the Builder, Scout, Medic, Catapult, Horseman, construction, fog of war and saves remain only here.
// See README.md at the repository root. Kept so the old project still builds; do not delete.
// ================================================================================================================
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
	/** How fast the site is rising right now (1 = on its own inside the castle's zone; more with Builders at the
	 * walls; 0 = outside the zone with no Builder on it). */
	float GetConstructionRate() const;
	/** Seconds until the site is finished at the rate it is rising now (0 when it is not a site). bOutWaiting: it
	 * is not rising at all (it waits for a Builder), and the time is the work still to be done by one. */
	float GetBuildSecondsLeft(bool* bOutWaiting = nullptr) const;
	/** Seconds until the level in hand is done, at its present rate (0 when it is not upgrading). */
	float GetUpgradeSecondsLeft() const;
	float GetHealth() const { return Health; }
	float GetHealthFrac() const;
	/** How hard it burns, 0..1: nothing above FireStartFraction of its health, ablaze from end to end near none. */
	float GetFireStrength() const;
	/** Testing (sr.HurtBuilding): put its health at a fraction of the full, with the look that goes with it. */
	void DebugSetHealthFrac(float Frac);
	int32 DebugFireSeats() const;
	double GetLastDamagedTime() const { return LastDamagedTime; }
	/** Arrows and blades. From may be null (another building's arrow). */
	void ReceiveDamage(float Amount, ASRUnit* From);
	/** Pull down a building still under construction and get CancelRefund of its price back. */
	void CancelConstruction();
	/** A finished building of ours that may be pulled down (not the Citadel, not a ruin). */
	bool CanDemolish() const { return !bDestroyed && IsFinished() && !IsCastle(); }
	/** What demolishing it would bring back now: DemolishRefund of its price and its levels, plus its queue in full. */
	FSRCost GetDemolishRefund() const;
	/** Pull it down (it slumps into rubble, as if it had fallen) and give back GetDemolishRefund. */
	void Demolish();
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
	bool Trains(ESRUnitType Type) const
	{
		// one troop type each, and a second at two of them: the Citadel's Scout, the Barracks' Medic
		return Stats().bRecruits && (Stats().RecruitType == Type || (IsCastle() && Type == ESRUnitType::Scout)
			|| (BuildingType == ESRBuildingType::Barracks && Type == ESRUnitType::Medic));
	}
	bool IsRecruiter() const { return Stats().bRecruits; }
	ESRBuildingState GetState() const { return State; }
	bool IsCastle() const { return BuildingType == ESRBuildingType::Castle; }
	/** A barracks, archery range, stable or siege workshop (levelled by FSRTrainerLevel). */
	bool IsTrainer() const { return BuildingType == ESRBuildingType::Barracks || BuildingType == ESRBuildingType::Range || BuildingType == ESRBuildingType::Stable || BuildingType == ESRBuildingType::Workshop; }
	/** A Granary or a Treasury (levelled by FSRStoreLevel): adds to what the kingdom can hold. */
	bool IsStore() const { return BuildingType == ESRBuildingType::Granary || BuildingType == ESRBuildingType::Treasury; }
	/** What a storehouse holds at its level (0 for anything else; the economy counts it once the building is finished). */
	int32 GetStoreCapacity() const;
	/** How much faster than the troop's own time it trains (its level). */
	float GetTrainSpeed() const;
	/** Seconds this building takes to train one of Type, at its level. */
	float GetTrainTime(ESRUnitType Type) const;
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
	/** The castle, watchtowers, gold mines, training buildings and storehouses have levels (Sovereign Feel > Buildings > *Levels); farms have one. */
	int32 GetMaxLevel() const;
	bool IsUpgradable() const { return GetMaxLevel() > 1; }
	/** Finished, below its top level and not already being upgraded. */
	bool CanUpgrade() const;
	/** The price of the next level. */
	FSRCost GetUpgradeCost() const;
	/** The price of raising it to ToLevel (from ToLevel - 1). */
	FSRCost GetUpgradeCostTo(int32 ToLevel) const;
	/** The Citadel level the next level waits for (0: none; a storehouse's levels do). */
	int32 GetUpgradeRequiredCastleLevel() const;
	/** Pays and starts the next level; false (with feedback) if it cannot. */
	bool StartUpgrade();
	/** Health with the building's level counted. */
	float GetMaxHealth() const;
	/** Its shooting at its level (towers; the castle's walls use its stats). 0 range = it does not shoot. */
	float GetAttackRange() const;
	float GetAttackDamage() const;
	float GetAttackInterval() const;
	/** Archers shooting from it (the castle: one per manned corner pillar, by level). */
	int32 GetArcherCount() const;
	/** What one delivery brings (a farm's food, a mine's gold at its level). */
	int32 GetPayoutAmount() const;
	/** Seconds the next level takes to build. */
	float GetUpgradeTime() const;
	/** The building zone round it (the castle's TerritoryRadius, wider with each level). */
	float GetBuildZoneRadius() const;
	/** Saved games. */
	void SetLevelForLoad(int32 InLevel, float InUpgradeProgress);
	/** Testing (sr.SetLevel): jump straight to a level, free and at once, with the new look and its flourish. */
	void SetLevelNow(int32 InLevel);
	/** Builders at its walls working on it right now (counted each frame while it needs work). */
	int32 GetBuildersWorking() const { return BuildersWorking; }
	/** Builders are mending it: until they finish it does not work (no training, payouts or shooting). */
	bool IsUnderRepair() const { return bRepairing; }
	/** The platoon this building's recruits join (and march to), or INDEX_NONE: the platoon panel's recruit platoon. */
	int32 GetAssignedPlatoon() const { return AssignedPlatoon; }
	void SetAssignedPlatoon(int32 Index) { AssignedPlatoon = Index; }

	/** Set by SpawnBuilding: not part of the level, so it is destroyed (not just reset) when the battle resets. */
	bool IsRuntimeBuilt() const { return bRuntimeBuilt; }

private:
	void SpawnRecruit(ESRUnitType Type);
	void UpdateFeedback(float Dt);
	void StepConstruction(float Dt);
	void StepDefence(float Dt);
	/** The archers seen on top (tower, relic tower, the castle's corner pillars): cards of the Archer's sprite sheet
	 * that draw, loose (the arrow leaves on the release frame) and recover with each shot, and stand idle between. */
	struct FPostArcher
	{
		FVector2D Offset = FVector2D::ZeroVector;   // from the footprint centre, in the mesh's own axes
		float FeetZ = 0.f;                          // above the actor
		float Yaw = 0.f;
		int32 Facing = 0;
		float Clock = -1.f;                         // time into the current shot, -1 = idle
		float IdlePhase = 0.f;
		bool bLoosed = true;
		TWeakObjectPtr<ASRUnit> Mark;
		FVector4 Applied = FVector4(-1.f, -1.f, -1.f, -1.f);
	};
	TArray<FPostArcher> Posts;
	UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> PostCards;
	bool HasPostArchers() const;
	void EnsurePosts();
	void StepPosts(float Dt);
	FVector PostFeet(int32 i) const;
	FVector2D PostXY(int32 i) const;
	int32 PostsLevel = -1;
	void StepCollapse(float Dt);
	/** It falls (or, bDemolished, is pulled down by its own side: no alert, no shake, not counted as a loss). */
	void Collapse(ASRUnit* Killer, bool bDemolished = false);
	void ApplyBuildVisual();
	void UpdateWorkers();
	void SetState(ESRBuildingState NewState);
	void LoadStateMeshes();
	/** The finished (or damaged) mesh for the current level: SM_Bld_<Name>_L<n>[_Damaged], else the nearest level below. */
	UStaticMesh* GetLevelMesh(bool bDamaged) const;
	/** Re-applies the current state's mesh for the level and lifts the label (HUD bars) by the level's growth;
	 * bFlourish: dust and debris burst off it, as when an upgrade finishes. */
	void ApplyLevelLook(bool bFlourish);

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
	/** Per-level looks (Tools/blender/build_building.py, LEVELS): index = level - 1; [0] stays empty (BuildingMesh /
	 * DamagedMeshAsset), and so does a level without its own mesh (it keeps the one below). */
	UPROPERTY(Transient) TArray<TObjectPtr<UStaticMesh>> LevelMeshes;
	UPROPERTY(Transient) TArray<TObjectPtr<UStaticMesh>> LevelDamagedMeshes;
	/** LabelOffset as placed (level 1); a higher level's taller mesh raises it. */
	FVector BaseLabelOffset = FVector::ZeroVector;
	ESRBuildingState State = ESRBuildingState::Complete;
	/** The sprite fire and smoke (ASRFXSprite): what burns when the new fire cannot be drawn (UsesNewFire() false). */
	TArray<TWeakObjectPtr<class ASRFXSprite>> StateFX;
	/** The new fire is on (Sovereign Feel > Buildings > Fire) and its materials are in the build. Otherwise the
	 * building burns as it always did: two fire sprites and a smoke sprite while damaged, smoke over the ruin. */
	bool UsesNewFire() const;
	/** The fire on it (ASRBuildingFire): made the first time it burns, fed the fire's strength as its health falls,
	 * throws the pall when it comes down and smoulders over the ruin. */
	TWeakObjectPtr<class ASRBuildingFire> FireFX;
	/** How sooted the mesh is drawn (M_Building / M_BuildingCard, custom primitive data 4): follows the fire, clears as it is repaired. */
	float Soot = 0.f;
	float SootShown = -1.f;
	uint8 FireSeated = 0;            // 0 not seated, 1 on the standing mesh, 2 on the damaged mesh, 3 on the ruin
	void StepFire(float Dt);
	class ASRBuildingFire* NeedFire(uint8 SeatKind);
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
	float CrackleClock = 0.f;
	float LifeClock = 0.f;
	/** Its own voice when the player selects it (a bell for the castle, a baa for the farm, ...). */
	void PlayVoice();
	/** Its life, now and then, heard close by (the farm's sheep and birds, the armourer's anvil, the range's targets...). */
	void StepLife(float Dt);     // -1 = not worked out yet (a saved game): asked of the economy on first need
	int32 BuildersWorking = 0;
	bool bRepairing = false;
	int32 AssignedPlatoon = INDEX_NONE;
	void CountBuilders();
	void StepRepair(float Dt);

	bool bSelected = false;
	bool bHovered = false;
	bool bRingVisible = false;
	float RingPop = 0.f;
};
