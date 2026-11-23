#pragma once

#include "CoreMinimal.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "VLFootDust.generated.h"

class UMaterialInterface;

/**
 * Puffs of dust kicked up by running feet: a small fixed pool of instanced cubes (as AVLAmbience's smoke), each one
 * drifting back and up, swelling a little and shrinking away. The owner calls Emit where a foot comes down and Advance
 * once a frame; nothing is allocated after BeginPlay, and they cast no shadow. Only characters that are given this
 * component raise dust (the hero has one; troops have none).
 */
UCLASS(ClassGroup = "Voxel", meta = (BlueprintSpawnableComponent))
class SOVEREIGNREALMS_API UVLFootDust : public UInstancedStaticMeshComponent
{
	GENERATED_BODY()

public:
	UVLFootDust();

	virtual void BeginPlay() override;

	/** Count cubes at a point on the ground (world), thrown along Back; Scale makes a bigger puff (a landing). */
	void Emit(const FVector& At, const FVector& Back, int32 Count, float Scale = 1.f);
	void Advance(float DeltaSeconds);

	/** Cubes per footfall at a run. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	int32 PuffsPerStep = 4;

	/** Edge of a cube when it leaves the ground, cm; it grows to Growth times that before it shrinks away. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	float Size = 8.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	float Growth = 1.7f;

	/** Seconds a cube lasts (each varies by a quarter either way). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	float Lifetime = 0.55f;

	/** Speed backwards and upwards as it leaves the foot, cm/s. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	float Drift = 70.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	float Rise = 55.f;

	/** The colour of the dust (the material's Tint). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	FLinearColor Color = FLinearColor(0.97f, 0.96f, 0.93f);      // white puffs

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	float Glow = 0.45f;

	/** How many cubes there can be at once. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Dust")
	int32 PoolSize = 40;

	/** M_Voxel-style material with a Tint (set by the owner before BeginPlay, or here). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Dust")
	TObjectPtr<UMaterialInterface> DustMaterial;

	void Setup(UMaterialInterface* Material);

private:
	struct FPuff
	{
		FVector Pos = FVector::ZeroVector;
		FVector Vel = FVector::ZeroVector;
		float Age = 0.f;
		float Life = 0.f;      // 0 = free
		float Size = 0.f;
		float Yaw = 0.f;
	};
	TArray<FPuff> Puffs;
	int32 Next = 0;
	int32 Alive = 0;
	FVector ParkAt = FVector::ZeroVector;      // where the unused cubes wait (the last place dust was raised)
	uint32 Seed = 1;
	float Rand();
};
