// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "Units/SRSprite.h"
#include "SRBattleSubsystem.generated.h"

class ASRUnit;
class ASRBuilding;
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

/** What happened in the match so far, per team (index = ESRTeam). Shown on the victory / defeat screen. */
struct FSRMatchStats
{
	int32 Recruited[2] = { 0, 0 };
	int32 TroopsLost[2] = { 0, 0 };
	int32 BuildingsBuilt[2] = { 0, 0 };
	int32 BuildingsLost[2] = { 0, 0 };
};

/**
 * Owns the battle: the unit registry, the per-frame simulation order
 * (think -> move -> push apart -> animate), scenario spawning / reset,
 * the shared sprite assets and per-frame sprite view, and the victory check.
 *
 * Units do not tick themselves; this subsystem steps them so every unit sees
 * a consistent world each frame.
 */
enum class ESRFX : uint8;

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

	/** The nearest active enemy within Range. A hard-to-notice one (the Scout: FSRUnitStats::NoticeScale) only counts
	 * within that fraction of Range. */
	/** MinRange: skip anything closer than this (a catapult cannot lob at what is under it; it takes the next one). */
	ASRUnit* FindNearestEnemy(const ASRUnit* For, float Range, float MinRange = 0.f) const;
	/**
	 * Living units within Radius of Pos, from a bucket grid rebuilt each simulation step (so neighbour searches
	 * cost O(nearby) instead of O(all units): avoidance, overlap resolution, targeting, alerts).
	 */
	void QueryUnits(const FVector2D& Pos, float Radius, TArray<ASRUnit*>& Out) const;
	/** Nearest standing enemy building whose footprint edge is within Range of the unit (finished or not). */
	ASRBuilding* FindNearestEnemyBuilding(const ASRUnit* For, float Range) const;

	// ---- group commands: the one way orders reach troops (player, platoons, the enemy commander) ----
	/**
	 * Move (or attack-move) a group in formation. Slots are laid out at the goal in the given shape; one grid
	 * search finds every member's way round lakes, cliffs, woods and buildings.
	 */
	void CommandMove(const TArray<ASRUnit*>& Group, const FVector2D& Goal, bool bAttackMove, ESRFormationShape Shape = ESRFormationShape::Line,
		bool bAcknowledge = true, const FVector2D* Facing = nullptr, bool bKeepPace = true);
	/** Deep water at a point (a hard wall for everyone without water privileges). */
	bool IsDeepWater(const FVector2D& Point) const;
	/** Ground too steep to walk at a point: a mountainside, a bank, a crag's edge (a grid edge cell). The terrain is a
	 * smooth heightfield, so nothing physical stops a troop there: steering treats it as it treats deep water. */
	bool IsSteep(const FVector2D& Point) const;
	void CommandAttack(const TArray<ASRUnit*>& Group, ASRUnit* Target);
	void CommandAttackBuilding(const TArray<ASRUnit*>& Group, ASRBuilding* Target);

	/**
	 * Routes: a group walks through a list of points in formation, one leg at a time (the next leg starts once
	 * everyone has arrived, or given up, and nobody is fighting), until one of its members is given another order
	 * (ClearPatrol).
	 *  - Patrol: attack-moving from where the group stands to To and back, round and round (CommandPatrol), or through
	 *    several points and back to the start (ExtendPatrol: P, then Option+click each point).
	 *  - Pathway: through the points once and stop at the last (ExtendPath: Option+right-click each point).
	 */
	void CommandPatrol(const TArray<ASRUnit*>& Group, const FVector2D& To, ESRFormationShape Shape);
	/** One more point on the patrol these units are on (they start one from where they stand if they are on none). */
	void ExtendPatrol(const TArray<ASRUnit*>& Group, const FVector2D& Point, ESRFormationShape Shape);
	/** One more point on the pathway these units are walking (a new pathway if they are on none). */
	void ExtendPath(const TArray<ASRUnit*>& Group, const FVector2D& Point, bool bAttackMove, ESRFormationShape Shape);
	/** Takes these units off any patrol or pathway (one left with nobody ends). */
	void ClearPatrol(const TArray<ASRUnit*>& Group);
	/** Fog of war: may the player see this unit right now (USRFogSubsystem)? */
	bool IsVisibleToPlayer(const ASRUnit* Unit) const;
	/** The route a unit is on, if any (the HUD draws it): its points, whether it loops (a patrol), the point it is
	 * heading for now. */
	bool GetRoute(const ASRUnit* Unit, TArray<FVector2D>& OutPoints, bool& bOutLoop, int32& OutNext) const;

	// ---- heals (the Medic) ----
	struct FHealPopup { FVector Origin = FVector::ZeroVector; int32 Amount = 0; float Age = 0.f; };
	/** A green "+N" over a troop that was just healed (drawn by ASRHUD). */
	void AddHealPopup(const FVector& Origin, int32 Amount);
	const TArray<FHealPopup>& GetHealPopups() const { return HealPopups; }

	/** A building fell; if it was a castle the match is decided. */
	void NotifyBuildingDestroyed(ASRBuilding* Building);
	float GetBattleClock() const { return BattleClock; }
	/** Saved games. */
	void SetBattleClock(float InClock) { BattleClock = InClock; }
	void SetStats(const FSRMatchStats& InStats) { MatchStats = InStats; }
	/** Saved games: every troop and corpse goes (the loaded ones are spawned after). */
	void RemoveAllUnits();

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
	/** One-shot or looping battlefield effect (fire, smoke, dust, debris, impact); see ASRFXSprite. */
	class ASRFXSprite* SpawnFX(ESRFX Kind, const FVector& Location, float Scale = 1.f, float Lifetime = 0.f);
	UMaterialInterface* GetSpriteShadowMaterial(ESRUnitType Type) const;

	/**
	 * Debug (sr.ShotOn): the next time Event happens to a unit of UnitType (-1 = any) and Team (-1 = any), freeze the battle on that
	 * frame, centre the camera on the unit, let the image settle, save Saved/Screenshots/SR/<Name>.png, then carry on.
	 */
	void ArmShot(ESRShotEvent Event, const FString& Name, int32 UnitType, int32 Team);
	/** True while a debug capture holds the battle still; projectiles pause too. */
	bool IsFrozen() const { return FreezeFramesLeft > 0 || bSimPaused; }

	/**
	 * The pause the menus use (USRGameFlowSubsystem): the whole simulation holds still (troops, buildings, the
	 * commanders, projectiles, workers, the battle clock) while the world itself keeps ticking, so the camera, the
	 * interface, sounds and the debug command inbox stay live.
	 */
	void SetSimPaused(bool bPaused) { bSimPaused = bPaused; }
	bool IsSimPaused() const { return bSimPaused; }

	// ---- match statistics (read by the end-of-match screen) ----
	const FSRMatchStats& GetStats() const { return MatchStats; }
	void NoteRecruit(ESRTeam Team) { ++MatchStats.Recruited[int32(Team)]; }
	void NoteBuildingBuilt(ESRTeam Team) { ++MatchStats.BuildingsBuilt[int32(Team)]; }

	/** Adds camera trauma, attenuated by distance from the camera focus. */
	void AddCameraTrauma(const FVector& WorldLocation, float Amount) const;

	FLinearColor TeamColor(ESRTeam Team) const;
	FVector2D TeamCentroid(ESRTeam Team) const;
	int32 CountAlive(ESRTeam Team) const;
	/** Living builders of a kingdom. */
	int32 CountBuilders(ESRTeam Team) const;
	void LogStatus() const;

	ESRBattleResult GetResult() const { return Result; }
	float GetTimeSinceResult() const { return TimeSinceResult; }

	// Shared sprite assets (Docs/VISUAL_CONTRACT.md, "Troop sprites"). Units and arrows hold no material instances
	// of their own: the frame, team colour, flash and fade travel as custom primitive data.
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> UnitCardMesh;
	UPROPERTY(Transient) TObjectPtr<UStaticMesh> ArrowCardMesh;
	/** Index = ESRUnitType. A type whose sheet is not imported yet borrows the Shieldbearer's. */
	static constexpr int32 SRSpriteTypes = 7;   // one per ESRUnitType (UHT wants the literal below, not this)
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> SpriteMaterials[7];
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> SpriteShadowMaterials[7];
	/** Catapult stones (an arrow card with the stone sheet). */
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> StoneMaterial;
	/** Workers (cosmetic miners and farmhands): 0 miner, 1 farmhand. */
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> WorkerMaterials[2];
	UPROPERTY(Transient) TObjectPtr<UMaterialInterface> WorkerShadowMaterials[2];
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

	void StepFrame(float Dt);
	void StepPatrols(float Dt);
	/** One marching loop under each body of foot troops on the move (the nearest few), following its middle. */
	void StepMarchSounds(float Dt);
	struct FMarchVoice { TWeakObjectPtr<class UAudioComponent> Comp; FVector Pos = FVector::ZeroVector; FVector Want = FVector::ZeroVector; float Gain = 1.f; bool bSeen = false; };
	TArray<FMarchVoice> MarchVoices;
	/** The roar of a big fight near the camera: louder with more troops engaged, following the fight's middle. */
	void StepBattleRoar(float Dt);
	TWeakObjectPtr<class UAudioComponent> RoarComp;
	FVector RoarPos = FVector::ZeroVector, RoarWant = FVector::ZeroVector;
	float RoarClock = 0.f;
	float MarchClock = 0.f;
	void RebuildBuckets();

	struct FPatrol
	{
		TArray<TWeakObjectPtr<ASRUnit>> Members;
		TArray<FVector2D> Points;   // a patrol's first point is where the group stood when it was given
		int32 Next = 0;             // the point the group is walking to now
		bool bLoop = true;          // patrol: round and round; pathway: stop at the last point
		bool bAttackMove = true;
		ESRFormationShape Shape = ESRFormationShape::Line;
		float Settle = 0.f;
	};
	TArray<FPatrol> Patrols;

	/** A group in formation on the march: the formation's centre walks one route and each member keeps its place in
	 * the shape round it, turned to the way the route goes. A member whose place the ground does not allow (a narrow
	 * ramp, a gap) files along the route instead and takes its place again once there is room. At the end each
	 * member walks to its slot as usual. */
	struct FMarch
	{
		TArray<TWeakObjectPtr<ASRUnit>> Members;
		TArray<FVector2D> Offsets;          // place in the shape: x forward, y right (cm)
		TArray<FVector2D> FinalSlots;
		TArray<float> RouteTimer;           // a member off its place and off the route: its own way back, re-planned now and then
		TArray<FVector2D> Route;            // the centre's route, from where the group stood to the goal
		TArray<float> RouteS;               // distance along it at each point
		float S = 0.f, Pace = 0.f, Stalled = 0.f;
		bool bAttackMove = false;
	};
	TArray<FMarch> Marches;
	void StepMarches(float Dt);
	void EndMarchesOf(const TArray<ASRUnit*>& Group);
	FVector2D RouteAt(const FMarch& M, float S) const;
	/** The route all of Group (and nobody else) is on, or INDEX_NONE. */
	int32 FindRouteOf(const TArray<ASRUnit*>& Group) const;
	TArray<FHealPopup> HealPopups;
	static constexpr float BucketSize = 400.f;
	TMap<FIntPoint, TArray<ASRUnit*>> Buckets;

	UPROPERTY(Transient) TArray<TObjectPtr<ASRUnit>> Units;
	UPROPERTY(Transient) TArray<TObjectPtr<ASRUnit>> Corpses;
	UPROPERTY(Transient) TArray<TObjectPtr<AActor>> Obstacles;

	bool bBattleStarted = false;
	bool bAutoBattle = false;
	bool bSimPaused = false;
	FSRMatchStats MatchStats;
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
