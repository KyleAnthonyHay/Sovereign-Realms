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

/**
 * A kingdom building: the castle (recruits troops), a farm (food) or a mine (gold).
 *
 * Placed in the level by Tools/build_battlefield_visuals.py from SourceArt/World/layout.json, which also fills in
 * the footprint and the sockets the Blender model exports (SourceArt/Buildings/<type>.json). The actor origin is on
 * the ground at the model's origin; the model's front (gate, adit, yard) faces local -X.
 *
 * The mesh has no collision. Movement is blocked by one box over the footprint (WorldStatic, so the units' wall
 * traces see it); ground and cursor traces ignore buildings. Team colour reaches the materials as custom primitive
 * data 0..2 (Docs/VISUAL_CONTRACT.md, "Buildings").
 *
 * USREconomySubsystem steps every building each frame: farms and mines pay out on a timer, the castle works
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

	// ---- run time (USREconomySubsystem) ----
	/** Back to the start of a battle: empty queue, timers at zero, default rally point. */
	void ResetRuntime();
	void StepBuilding(float Dt);

	/** Pays for a recruit and queues it. False (with feedback on the resource counters) if it cannot be afforded or the queue is full. */
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

private:
	void SpawnRecruit(ESRUnitType Type);
	void UpdateFeedback(float Dt);

	UPROPERTY(VisibleAnywhere, Category = "Building") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, Category = "Building") TObjectPtr<UStaticMeshComponent> Mesh;
	/** One convex box over the footprint: what stops troops. */
	UPROPERTY(VisibleAnywhere, Category = "Building") TObjectPtr<UBoxComponent> Blocker;
	/** Selection / hover outline round the footprint. */
	UPROPERTY(Transient) TObjectPtr<USRRingComponent> Ring;
	/** The rally flag (castle only): planted at the rally point while the castle is selected or just after it moves. */
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> RallyFlag;

	UPROPERTY(Transient) TObjectPtr<USREconomySubsystem> Economy;

	TArray<ESRUnitType> Queue;
	float BuildClock = 0.f;
	float PayoutClock = 0.f;
	float TimeSincePayout = 1000.f;
	FVector2D RallyPoint = FVector2D::ZeroVector;
	float RallyShowTime = 0.f;
	float RallyPop = 0.f;
	int32 RecruitCount = 0;

	bool bSelected = false;
	bool bHovered = false;
	bool bRingVisible = false;
	float RingPop = 0.f;
};
