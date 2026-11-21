// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SRFire.generated.h"

class UProceduralMeshComponent;
class UPointLightComponent;
class ULocalFogVolumeComponent;
class UStaticMeshComponent;

/**
 * A building on fire. Many small flames, each a fraction of a storey tall, run along the building's own broken edges:
 * its roof lines, wall heads and breaches (the fire reads the mesh's vertices to find them, so it clings to whatever
 * shape the building has). They catch in clusters, one cluster after another as health falls, every tongue with its own
 * size, beat and lean. Over each cluster sparks climb and thick dark smoke rolls up, swells and leans away downwind,
 * lit orange from beneath: the smoke is what is seen from afar, not the flames. A warm flickering light falls on the
 * walls and the ground, the haze round it glows, and ASRBuilding blackens the mesh itself with soot (M_Building's Burn).
 * One actor per burning building; it also throws the pall of dust and smoke when the building comes down and smoulders
 * over the ruin.
 *
 * Everything drawn is camera-facing quads in three procedural meshes (smoke, flames, embers), moved here each frame
 * and animated in their materials (M_FX_Flame, M_FX_Smoke, M_FX_Embers: Tools/build_fx_materials.py). About a hundred
 * quads for a building ablaze, no ticking at all while nothing burns.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRBuildingFire : public AActor
{
	GENERATED_BODY()

public:
	ASRBuildingFire();

	/** The fire's three materials are in the build (M_FX_Smoke, M_FX_Flame, M_FX_Embers). Without them nothing could
	 * be drawn, and ASRBuilding keeps to the old sprite fire. */
	static bool CanDraw();

	/** Seat the fire on a building's mesh (its high places: roofs, towers, wall heads). bLow: on a ruin, anywhere. */
	void Seat(UStaticMeshComponent* BuildingMesh, const FVector& Centre, const FVector2D& HalfExtent, float Height, bool bLow);
	/** 0 = out (the smoke thins away), 1 = ablaze from end to end. */
	void SetStrength(float InStrength);
	float GetStrength() const { return Target; }
	/** A ruin smoulders: thin smoke, a few low flames. */
	void SetSmoulder(bool bIn) { bSmoulder = bIn; }
	/** The building comes down: a ring of dust rolling out along the ground, dark smoke and sparks thrown up. */
	void Burst(const FVector& Centre, const FVector2D& HalfExtent, float Height);
	/** Dies away and removes itself once the last smoke has gone. */
	void Finish();
	int32 NumSeats() const { return Clusters.Num(); }
	int32 NumFlames() const { return Flames.Num(); }
	int32 NumPuffs() const { return Puffs.Num(); }
	/** Flames alight now. */
	int32 NumLit() const;

	virtual void Tick(float DeltaSeconds) override;

private:
	/** A stretch of the building that burns together: a run of roof edge, a wall head, a breach. */
	struct FCluster
	{
		FVector Pos = FVector::ZeroVector;      // the middle of its flames
		float Order = 0.f;                      // 0..1: clusters catch in this order as the fire grows
		float Lit = 0.f;                        // eased 0..1
		float Emit = 0.f;
		float Seed = 0.f;
		float Scale = 1.f;                      // of its smoke: by the building's size
	};
	/** One tongue of flame, rooted on a vertex of the mesh. */
	struct FFlame
	{
		FVector Pos = FVector::ZeroVector;
		int32 Cluster = 0;
		float Width = 60.f, Height = 90.f;
		float Seed = 0.f;
		float Delay = 0.f;                      // how far into its cluster's catching it joins in (0..0.6)
		float Lit = 0.f;
	};
	struct FPuff
	{
		FVector Pos, Vel;
		float Age = 0.f, Life = 1.f;
		float Size0 = 80.f, Size1 = 300.f;
		float Seed = 0.f, Dark = 1.f, Heat = 0.f, Alpha = 1.f;
		float Drag = 0.6f, Lift = 0.f;
	};

	void Build();
	void Emit(const FVector& At, float Scale, float Dark, float Heat, float Alpha);

	UPROPERTY(VisibleAnywhere) TObjectPtr<UProceduralMeshComponent> SmokeMesh;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UProceduralMeshComponent> FlameMesh;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UProceduralMeshComponent> EmberMesh;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UPointLightComponent> Glow;
	UPROPERTY(VisibleAnywhere) TObjectPtr<ULocalFogVolumeComponent> Haze;

	TArray<FCluster> Clusters;
	TArray<FFlame> Flames;
	TArray<FPuff> Puffs;
	TArray<FVector> V[3];
	TArray<FVector2D> UV0[3], UV1[3];
	TArray<FLinearColor> Col[3];
	bool bCreated = false;
	bool bSmoulder = false;
	bool bFinishing = false;
	float Target = 0.f;
	float Strength = 0.f;
	float Clock = 0.f;
	float Flash = 0.f;            // the collapse's flare in the light
	FVector Middle = FVector::ZeroVector;
	FRandomStream Rng;
};
