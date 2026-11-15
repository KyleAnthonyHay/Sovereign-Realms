// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SRBirds.generated.h"

class UProceduralMeshComponent;

/**
 * The birds: flocks flying wide, wobbly loops round the whole map, rising over hills and mountains on the way. Every
 * bird is a few flat triangles (a body and two jointed wings) in one procedural mesh, rebuilt each frame: each beats
 * its wings and glides in its own rhythm and banks into the turns. Gulls and rooks, unlit (M_Birds shows the vertex
 * colour). Tuned in Sovereign Feel > World > Birds. Spawned by the game mode, so they fly over the title screen too.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRBirds : public AActor
{
	GENERATED_BODY()

public:
	ASRBirds();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	int32 NumBirds() const { return Birds.Num(); }
	/** A flock's centre now (for the debug status line). */
	FVector FlockPosition(int32 Index) const { return Flocks.IsValidIndex(Index) ? Flocks[Index].Pos : FVector::ZeroVector; }
	int32 NumFlocks() const { return Flocks.Num(); }

private:
	struct FFlock
	{
		FVector2D Centre = FVector2D::ZeroVector;
		float Radius = 8000.f, Squash = 0.8f, Spin = 0.f;     // the loop: an ellipse turned by Spin, its radius wobbling
		float Wobble2 = 0.f, Wobble3 = 0.f, Phase2 = 0.f, Phase3 = 0.f;
		float Theta = 0.f, Dir = 1.f, Speed = 1100.f;
		float Height = 2000.f;                                // above the ground
		float GroundZ = 0.f, GroundTimer = 0.f;
		FVector Pos = FVector::ZeroVector;
		FVector Fwd = FVector::ForwardVector;
		float Bank = 0.f;
	};
	struct FBird
	{
		int32 Flock = 0;
		int32 Kind = 0;                         // 0 gull, 1 rook, 2 goose
		FVector Offset = FVector::ZeroVector;   // in the flock's frame: forward, right, up
		FVector Drift = FVector::ZeroVector;    // how far it wanders round that place
		float DriftRate = 0.3f, DriftPhase = 0.f;
		float Span = 70.f;
		float Flap = 0.f, FlapRate = 3.f;       // wing beat: phase (radians) and beats per second
		float Mode = 0.f;                       // 1 flapping, 0 gliding (eased)
		float ModeTimer = 0.f;
		bool bFlapping = true;
		FLinearColor Body, Tip;
	};

	FVector2D LoopPoint(const FFlock& F, float Theta) const;
	float GroundAt(const FVector2D& XY) const;
	void BuildMesh(bool bCreate);

	UPROPERTY(VisibleAnywhere) TObjectPtr<UProceduralMeshComponent> Mesh;

	TArray<FFlock> Flocks;
	TArray<FBird> Birds;
	TArray<FVector> Verts;
	TArray<int32> Tris;
	TArray<FLinearColor> Colors;
	float Clock = 0.f;
	FRandomStream Rng;
};
