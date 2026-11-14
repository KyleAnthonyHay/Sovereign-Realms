// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "SREconomySubsystem.generated.h"

class ASRBuilding;

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
	void AddResource(ESRTeam Team, ESRResource Resource, int32 Amount);
	bool CanAfford(ESRTeam Team, const FSRCost& Cost) const;
	/** Deducts the cost, or refuses and flashes the counters that fall short (player only). */
	bool TrySpend(ESRTeam Team, const FSRCost& Cost);
	/** A command was refused for a reason other than price (queue full): a short shake of both counters. */
	void NotifyRefused();
	/** 1 just after a refused purchase, falling to 0: the HUD flashes and shakes that counter. */
	float GetInsufficientFlash(ESRResource Resource) const { return Flash[int32(Resource)]; }
	/** 1 just after income arrived, falling to 0: the HUD pulses that counter. */
	float GetIncomePulse(ESRResource Resource) const { return Pulse[int32(Resource)]; }
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
	bool bStarted = false;
};
