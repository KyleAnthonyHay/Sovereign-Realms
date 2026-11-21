// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "SREconomySubsystem.generated.h"

class ASRBuilding;
class ASRUnit;
struct FSRPlacement;

/** Something the player should notice: drawn in the HUD's message line and pinged on the minimap. */
UENUM()
enum class ESRAlertKind : uint8
{
	UnderAttack,      // one of your buildings (or troops, near home) is being hit
	BuildingLost,
	BuildingDone,
	EnemyWave,        // the enemy has marched out
	PopulationCapped,
	Info
};

struct FSRAlert
{
	ESRAlertKind Kind = ESRAlertKind::Info;
	FText Text;
	FVector2D Location = FVector2D::ZeroVector;
	bool bHasLocation = false;
	float Age = 0.f;
};

/** A "+N" floating up from a building when it pays out. Drawn by ASRHUD. */
struct FSRPayoutPopup
{
	FVector Origin = FVector::ZeroVector;
	int32 Amount = 0;
	ESRResource Resource = ESRResource::Gold;
	float Age = 0.f;
};

/**
 * The kingdoms' economy: each team's gold and food, the registry of buildings, and the small services the
 * buildings need (payout popups, "cannot afford" feedback, routes round footprints).
 *
 * Not tickable: USRBattleSubsystem steps it once per frame after the units, so it pauses, freezes and resets
 * with the battle. Tuning lives in Sovereign Feel > Economy.
 */
UCLASS()
class SOVEREIGNREALMS_API USREconomySubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static USREconomySubsystem* Get(const UObject* WorldContext);

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	void RegisterBuilding(ASRBuilding* Building);
	void UnregisterBuilding(ASRBuilding* Building);
	const TArray<TObjectPtr<ASRBuilding>>& GetBuildings() const { return Buildings; }
	ASRBuilding* FindBuilding(ESRBuildingType Type, ESRTeam Team) const;
	int32 CountBuildings(ESRBuildingType Type, ESRTeam Team) const;

	/** Starting resources, empty queues, default rally points. */
	void Reset();
	void Step(float Dt);

	// ---- resources ----
	int32 GetResource(ESRTeam Team, ESRResource Resource) const { return Stock[int32(Team)][int32(Resource)]; }
	/** Adds (or takes) resources; income beyond the stores' capacity (GetStorage) is lost unless bIgnoreStorage. */
	void AddResource(ESRTeam Team, ESRResource Resource, int32 Amount, bool bIgnoreStorage = false);
	/** The castle's level (1 without one). */
	int32 GetCastleLevel(ESRTeam Team) const;
	/** The most gold / food the kingdom can hold: its castle's level plus its finished Granaries (food) or Treasuries (gold). */
	int32 GetStorage(ESRTeam Team, ESRResource Resource) const;
	/** The share of GetStorage that storehouses add (finished Granaries / Treasuries, each at its level). */
	int32 GetStoreCapacity(ESRTeam Team, ESRResource Resource) const;
	/** Granaries (and, separately, Treasuries) a kingdom may have at its castle's level. */
	int32 GetMaxStores(ESRTeam Team) const;
	/** Standing buildings of a type, finished or going up (ruins not counted). */
	int32 CountStanding(ESRBuildingType Type, ESRTeam Team) const;
	// ---- the Scout: castle level, one at a time, a wait between two ----
	/** Scouts alive, and (OutQueued) in training. */
	int32 GetScoutCount(ESRTeam Team, int32* OutQueued = nullptr) const;
	/** Seconds of game time until the kingdom may train another Scout (0 = now). */
	float GetScoutCooldown(ESRTeam Team) const { return ScoutCooldownLeft[int32(Team)]; }
	/** A Scout was queued and paid for: the wait starts (also: saved games, sr.ScoutCooldown). */
	void SetScoutCooldown(ESRTeam Team, float Seconds) { ScoutCooldownLeft[int32(Team)] = FMath::Max(0.f, Seconds); }
	/** Why the kingdom cannot train a Scout right now (castle level, one already, the wait), or empty if it can.
	 * Price and housing are not looked at here. */
	FText GetScoutRefusal(ESRTeam Team) const;
	/** The most troops it may field at its castle's level, however many farms. */
	int32 GetPopulationCeiling(ESRTeam Team) const;
	/** Builders it may have at its castle's level. */
	int32 GetMaxBuilders(ESRTeam Team) const;
	/** Watchtowers a kingdom may have (standing or going up): TowerLimitBase, +TowerLimitPerCastleLevel per castle level. */
	int32 GetMaxTowers(ESRTeam Team) const;
	/** Farms a kingdom may have (standing or going up): FarmLimitBase, +FarmLimitPerCastleLevel per castle level. */
	int32 GetMaxFarms(ESRTeam Team) const;
	/** How many of a kind of building a kingdom may have at its castle's level (INDEX_NONE: no limit). Counts standing
	 * buildings and sites (CountStanding). */
	int32 GetBuildLimit(ESRBuildingType Type, ESRTeam Team) const;
	bool IsAtBuildLimit(ESRBuildingType Type, ESRTeam Team) const;
	/** "Farm limit 3 reached: raise the Citadel for another" (empty when not at the limit). */
	FText GetBuildLimitReason(ESRBuildingType Type, ESRTeam Team) const;
	/** Saved games. */
	void SetStock(ESRTeam Team, ESRResource Resource, int32 Amount) { Stock[int32(Team)][int32(Resource)] = FMath::Max(0, Amount); }
	bool CanAfford(ESRTeam Team, const FSRCost& Cost) const;
	/** Deducts the cost, or refuses and flashes the counters that fall short (player only). */
	bool TrySpend(ESRTeam Team, const FSRCost& Cost);
	/** A command was refused for a reason other than price (queue full): a short shake of both counters. */
	void NotifyRefused();
	/** 1 just after a refused purchase, falling to 0: the HUD flashes and shakes that counter. */
	float GetInsufficientFlash(ESRResource Resource) const { return Flash[int32(Resource)]; }
	/** 1 just after income arrived, falling to 0: the HUD pulses that counter. */
	float GetIncomePulse(ESRResource Resource) const { return Pulse[int32(Resource)]; }
	// ---- population ----
	/** Troops alive (and spawning). */
	int32 GetPopulation(ESRTeam Team) const;
	/** Troops waiting in recruit queues. */
	int32 GetQueuedPopulation(ESRTeam Team) const;
	/** What the team's finished buildings house, capped at the castle level's troop ceiling. */
	int32 GetPopulationCap(ESRTeam Team) const;
	void NotifyPopulationCapped(ESRTeam Team);
	float GetPopulationFlash() const { return PopFlash; }

	// ---- building ----
	/**
	 * Lays down a building for Team if the spot is valid and the gold is there: the foundations go down and it
	 * rises over BuildTime. Returns it, or null with OutReason set (and the gold counter flashing for the player).
	 */
	ASRBuilding* PlaceBuilding(ESRBuildingType Type, ESRTeam Team, const FVector2D& Want, FText* OutReason = nullptr);
	void NotifyBuildingFinished(ASRBuilding* Building);
	void NotifyBuildingAttacked(ASRBuilding* Building, ASRUnit* Attacker);
	/** One of the player's troops was hit: an alert if it is out of view (throttled). */
	void NotifyUnitAttacked(const ASRUnit* Victim);
	void NotifyBuildingDestroyed(ASRBuilding* Building);
	/** Stock over what the kingdom can now hold is lost (a storehouse pulled down). */
	void ClampToStorage(ESRTeam Team);
	/** The team's castle, if it still stands. */
	ASRBuilding* GetCastle(ESRTeam Team) const;
	/** Inside one of the kingdom's building zones (its castle's TerritoryRadius): buildings there raise themselves. */
	bool IsInBuildZone(ESRTeam Team, const FVector2D& At) const;
	/** Builders alive and builders in training at the castle (the cap is GetMaxBuilders: the castle level). */
	int32 GetBuilderCount(ESRTeam Team, int32* OutQueued = nullptr) const;
	/** Finished, standing buildings of a type. */
	int32 CountFinished(ESRBuildingType Type, ESRTeam Team) const;
	/** The most recent time (game seconds) one of the team's buildings was struck, and where. */
	double GetLastAttackTime(ESRTeam Team) const { return LastAttackTime[int32(Team)]; }
	FVector2D GetLastAttackLocation(ESRTeam Team) const { return LastAttackLocation[int32(Team)]; }

	// ---- alerts (player only) ----
	void PushAlert(ESRAlertKind Kind, const FText& Text, const FVector2D* Location = nullptr);
	const TArray<FSRAlert>& GetAlerts() const { return Alerts; }

	/** What the team's farms / mines bring in per minute at the current settings. */
	float GetIncomePerMinute(ESRTeam Team, ESRResource Resource) const;

	// ---- feedback ----
	void AddPopup(const FVector& Origin, int32 Amount, ESRResource Resource);
	const TArray<FSRPayoutPopup>& GetPopups() const { return Popups; }

	// ---- space ----
	/** Building under the cursor ray (nearest), or null. */
	ASRBuilding* PickBuilding(const FVector& RayOrigin, const FVector& RayDir) const;
	/** The point itself, or the nearest spot a route margin outside any footprint it lies in. */
	FVector2D ClearOfBuildings(const FVector2D& Point) const;
	/**
	 * Appends waypoints that take a walker from From to To round every building footprint in the way (there is no
	 * navmesh; footprints are convex boxes, so the detour is a walk round corners). The last point is To, moved
	 * clear of any footprint it was inside.
	 */
	void RoutePath(const FVector2D& From, const FVector2D& To, TArray<FVector2D>& OutPath) const;

	void LogStatus() const;

private:
	void RouteLeg(const FVector2D& From, const FVector2D& To, const ASRBuilding* Skip, int32 Depth, TArray<FVector2D>& OutPath) const;

	UPROPERTY(Transient) TArray<TObjectPtr<ASRBuilding>> Buildings;

	int32 Stock[2][2] = { { 0, 0 }, { 0, 0 } };
	float Flash[2] = { 0.f, 0.f };
	float Pulse[2] = { 0.f, 0.f };
	TArray<FSRPayoutPopup> Popups;
	TArray<FSRAlert> Alerts;
	float PopFlash = 0.f;
	double LastAttackTime[2] = { -100.0, -100.0 };
	FVector2D LastAttackLocation[2] = { FVector2D::ZeroVector, FVector2D::ZeroVector };
	TMap<TWeakObjectPtr<ASRBuilding>, double> LastAttackAlert;
	double LastUnitAttackAlert = -100.0;
	float ScoutCooldownLeft[2] = { 0.f, 0.f };
	bool bStarted = false;
};
