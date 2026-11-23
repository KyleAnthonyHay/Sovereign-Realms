#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "VLSky.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UStaticMesh;

/**
 * The sky's life: voxel clouds and birds (Realm v2; the level builder places one and fills in where they are).
 * Ambient only: no collision, no shadows, nothing the game reads.
 *
 * Clouds: each is a handful of flat white boxes on a 2 m grid, drifting slowly to and fro about its place. A cloud is
 * puffed away (its boxes shrink to nothing) when the camera comes near it or rises to its height, so no cloud ever
 * lies between the overview camera and the ground it looks at.
 *
 * Birds: flocks wheeling on wide loops, each bird a body and two wings (three cubes) that beat and glide in its own
 * rhythm and bank into the turn. The flocks' heights are the level's: some at the clouds' height, some under, some over.
 *
 * Every place is a function of the clock alone. Cost: two instanced components, a few hundred cubes.
 */
UCLASS()
class SOVEREIGNREALMS_API AVLSky : public AActor
{
	GENERATED_BODY()

public:
	AVLSky();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Each cloud's middle (world, cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TArray<FVector> CloudCentres;

	/** Each cloud's half size (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TArray<FVector> CloudSizes;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	int32 PuffsPerCloud = 14;

	/** How far a cloud drifts from its place (cm), and how fast (radians a second). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float CloudDrift = 2600.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float CloudDriftRate = 0.02f;

	/** A cloud is gone when the camera is nearer than this (cm), and comes back over CloudFade more. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float CloudHideNear = 7000.f;

	/** A cloud is gone when the camera is higher than this far under its middle (cm), fading over CloudFade below that. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float CloudHideUnder = 1200.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float CloudFade = 2500.f;

	/** Each flock's loop: its middle (world, cm; Z: the height it flies at). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TArray<FVector> FlockCentres;

	/** Each flock's loop: its radius (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TArray<float> FlockRadii;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	int32 BirdsPerFlock = 6;

	/** Wing tip to wing tip (cm): bigger than life, to be seen from the ground. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float BirdSpan = 260.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float BirdSpeed = 1500.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UStaticMesh> Cube;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UMaterialInterface> CloudMaterial;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UMaterialInterface> BirdMaterial;

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<UInstancedStaticMeshComponent> Clouds;

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<UInstancedStaticMeshComponent> Birds;

private:
	float Clock = 0.f;
	TArray<float> CloudShown;       // 0 .. 1, eased
};
