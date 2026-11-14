// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "SRFogSubsystem.generated.h"

class UTexture2D;
class UMaterialInstanceDynamic;
class ASRUnit;
class ASRBuilding;

/**
 * Fog of war, for the player's side.
 *
 * A grid of cells over the map (Sovereign Feel > Fog). Every FogUpdateInterval the player's troops (their line of
 * sight) and buildings light up the cells round them: those are visible now and stay explored. The enemy's troops are
 * drawn, picked, shown on the minimap and given health bars only while they stand in a visible cell; an enemy building
 * is unknown (hidden in the world and on the minimap) until it has been seen once, then remembered.
 *
 * The look: the grid is written to a small transient texture that the post-process material M_FogOfWar
 * (Tools/build_fog_material.py) samples by world position: unexplored ground is near black, explored ground dimmed and
 * greyed, visible ground clear. Edges ease in and out over FogFadeTime.
 *
 * The enemy commander does not use this: it has its own sight memory (USRAISubsystem::Observe).
 */
UCLASS()
class SOVEREIGNREALMS_API USRFogSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static USRFogSubsystem* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Deinitialize() override;

	/** Back to all-unexplored (a new match). */
	void Reset();
	/** Stepped by USRBattleSubsystem every frame (real time; it throttles itself). */
	void Update(float DeltaTime);

	bool IsEnabled() const;
	void SetEnabled(bool bEnabled) { bForceOff = !bEnabled; bDirty = true; }

	bool IsVisible(const FVector2D& WorldXY) const;
	bool IsExplored(const FVector2D& WorldXY) const;
	/** Should the player see this unit right now (own troops always)? */
	bool IsUnitVisible(const ASRUnit* Unit) const;
	/** Has the player ever seen this building (own buildings always)? */
	bool IsBuildingKnown(const ASRBuilding* Building) const;

	/** Saved games: the explored cells. */
	void GetExplored(TArray<uint8>& Out) const { Out = Explored; }
	void SetExplored(const TArray<uint8>& In);

private:
	int32 CellOf(const FVector2D& WorldXY) const;
	void Stamp(const FVector2D& Centre, float Radius);
	void Recompute();
	void PushTexture(float DeltaTime);
	void EnsureView();

	int32 N = 0;
	float CellSize = 125.f;
	FVector2D Origin = FVector2D::ZeroVector;
	TArray<uint8> Explored;
	TArray<uint8> Visible;
	TArray<float> Shown;        // what the texture shows, easing toward the target
	TArray<uint8> Pixels;       // BGRA staging
	float Clock = 0.f;
	bool bDirty = true;
	bool bForceOff = false;
	bool bHadView = false;

	UPROPERTY(Transient) TObjectPtr<UTexture2D> FogTexture;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> FogMaterial;
	TSet<TWeakObjectPtr<ASRBuilding>> KnownBuildings;
};
