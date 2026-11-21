// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SRLeaves.generated.h"

class UProceduralMeshComponent;

/**
 * Leaves falling from the trees the camera is looking at: thick in a wood, a few from a lone tree, none over open
 * ground. Each leaf is one quad in a procedural mesh rebuilt each frame (like ASRBirds): it lets go of a crown,
 * side-slips and tumbles down on the wind, lies on the ground for a few seconds and is gone. The trees are read once
 * from the level's instanced foliage (actors tagged SRTrees: Tools/build_battlefield_visuals.py); the leaf's colour
 * follows the tree (oak greens and yellows, maple reds, birch gold, a fir's brown needles). Lit, masked, two-sided
 * (M_Leaves), so depth of field and the sun treat a leaf like everything else. Tuned in Sovereign Feel > World > Leaves.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRLeaves : public AActor
{
	GENERATED_BODY()

public:
	ASRLeaves();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	int32 NumTrees() const { return TreeCount; }
	int32 NumNear() const { return Near.Num(); }
	int32 NumFalling() const;

private:
	struct FTree { FVector Base; float Height, Radius, Weight; uint8 Kind; };
	struct FLeaf
	{
		FVector Pos = FVector::ZeroVector;
		float GroundZ = 0.f;
		float Fall = 70.f;            // cm/s
		float Phase = 0.f, Rate = 1.f, Swing = 40.f, Heading = 0.f;
		float Spin = 0.f, SpinRate = 2.f, Roll = 0.f;
		FVector2D Drift = FVector2D::ZeroVector;   // cm/s, its own way out from the tree on top of the wind
		float Tumble = 0.f, Flip = 0.f;   // rad/s it turns over and over about its own length (0: it only rocks), and how far it has
		float Size = 14.f;
		float Rest = -1.f;            // > 0: lying on the ground, seconds left
		bool bAlive = false;
		FLinearColor Color;
	};

	void ReadTrees();
	void Gather(const FVector2D& Focus, float Radius);
	void Spawn(FLeaf& L, bool bMidAir);
	void BuildMesh(bool bCreate);

	UPROPERTY(VisibleAnywhere) TObjectPtr<UProceduralMeshComponent> Mesh;

	TMap<FIntPoint, TArray<FTree>> Cells;
	int32 TreeCount = 0;
	TArray<FTree> Near;               // the trees round the camera's focus now
	TArray<float> NearCum;            // their running weights (to pick one)
	float NearWeight = 0.f;
	FVector2D GatheredAt = FVector2D(1.e9f, 1.e9f);
	float GatherTimer = 0.f;
	float SpawnDebt = 0.f;
	TArray<FLeaf> Leaves;
	TArray<FVector> Verts;
	TArray<FVector> Normals;
	TArray<FVector2D> UVs;
	TArray<FLinearColor> Colors;
	float Clock = 0.f;
	bool bRead = false;
	FRandomStream Rng;
};
