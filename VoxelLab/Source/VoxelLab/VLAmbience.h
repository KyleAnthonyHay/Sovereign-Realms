#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "VLAmbience.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UStaticMesh;

/**
 * Small moving things, all of them cubes: glowing motes drifting in the evening light, and puffs of smoke climbing
 * from the chimneys. Placed and filled in by Tools/ue/build_level.py.
 */
UCLASS()
class VOXELLAB_API AVLAmbience : public AActor
{
	GENERATED_BODY()

public:
	AVLAmbience();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Chimney tops (world). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TArray<FVector> SmokeSources;

	/** Where motes gather (world): lanterns, flower beds, shafts of light. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TArray<FVector> MoteCentres;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	int32 MotesPerCentre = 7;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float MoteRadius = 260.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float MoteSize = 3.2f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	int32 PuffsPerChimney = 9;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	FVector Wind = FVector(-90.f, 60.f, 0.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UStaticMesh> Cube;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UMaterialInterface> MoteMaterial;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UMaterialInterface> SmokeMaterial;

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<UInstancedStaticMeshComponent> Motes;

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<UInstancedStaticMeshComponent> Smoke;

private:
	float Clock = 0.f;
};
