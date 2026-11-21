#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "VLCharacterData.generated.h"

class UStaticMesh;
class UMaterialInterface;

/** One rigid piece of a voxel character. The mesh's own origin is the joint it swings about. */
USTRUCT(BlueprintType)
struct FVLPart
{
	GENERATED_BODY()

	/** Body (the pelvis), Chest, Head, ArmL/R, ForeL/R, HandR, LegL/R, ShinL/R, Cape and its panels Cape<col><row>,
	 *  Sword: animated. Anything else rides rigidly on its parent. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	FName Name;

	/** The part this one hangs from (listed before it); none = the figure itself. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	FName Parent;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UStaticMesh> Mesh;

	/** Joint position in cm, character space: X forward, Y right, Z up, origin on the ground between the feet. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	FVector Pivot = FVector::ZeroVector;
};

/** A character built from rigid voxel parts, animated in code (Tools/ue/import_king.py fills it in). */
UCLASS(BlueprintType)
class VOXELLAB_API UVLCharacterData : public UDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TArray<FVLPart> Parts;

	/** Standing height in cm (capsule). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float Height = 170.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float Radius = 40.f;

	/** Extra yaw for the whole figure, if the meshes were not authored facing +X. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float MeshYaw = 0.f;

	/** The sword (part "Sword", origin at the middle of its grip): the direction of its blade as modelled in his hand,
	 *  where its grip sits when sheathed, and the direction the blade points then. Character space, cm. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Sword")
	bool bHasSheath = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Sword")
	FVector SwordBladeDir = FVector(0.f, 0.f, -1.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Sword")
	FVector SwordSheathPos = FVector::ZeroVector;

	/** The turn (about the grip) that takes the sword from his fist into the scabbard, as a quaternion (x, y, z, w). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel|Sword")
	FVector4 SwordSheathQuat = FVector4(0.f, 0.f, 0.f, 1.f);

	/** The bend the forearms are modelled with, degrees (the code animates the elbows in absolute angles). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float ElbowRestL = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float ElbowRestR = 0.f;

	/** The cape: parts "Cape<col><row>", each column a chain of panels hanging from the yoke "Cape". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	int32 CapeCols = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	int32 CapeRows = 0;

	/** Drawn over every part for a moment when he is hurt (unlit, scalar "Flash" 0..1 = how white). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UMaterialInterface> FlashMaterial;

	/** The dust his running feet raise (M_Voxel-style, tinted by the dust component). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	TObjectPtr<UMaterialInterface> DustMaterial;

	/** Stride: cm travelled per full walk cycle. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Voxel")
	float StrideLength = 150.f;
};
