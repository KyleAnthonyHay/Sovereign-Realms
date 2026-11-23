#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLWaterLook.generated.h"

class UMaterialInstanceDynamic;
class UTexture2D;

/**
 * The water's depth, as it looks (the owner's call, 2026-11-23: "simulated depth"): the sea beds of the maps are a
 * slab 2 m under the surface and the water is an opaque sheet, so how deep the water reads is drawn by its material,
 * M_VoxWater (Tools/ue/build_special_materials.py), from how far each point of it is from the shore: clear and
 * turquoise with the bed showing through by the land, darkening to deep blue further out, foam along the shore.
 *
 * How far from the shore is not in any level's files: it is measured here when play starts, for whatever level is
 * open. The level is sampled from above on 1.25 m cells (water: a sheet of an actor tagged Water lies there and
 * nothing stands in it: ground, rocks, a quay, a pier); each water cell's distance to the nearest cell that is not
 * water goes into a texture (its alpha: 0 at the shore, 1 at ShoreRange and beyond), and every water sheet's material
 * becomes an instance that reads it (parameters ShoreTex, ShoreRect, ShoreRange, ShoreOn). Rivers, brooks and ponds
 * are narrow, so they come out shallow from bank to bank.
 *
 * Without it (the editor's own viewport, a level with no path grid) the material draws water of one middling depth
 * and no foam: ShoreOn is 0 there.
 *
 * vl.Water.Depth 0 | 1: the old flat look / the depth (compare, measure). vl.Water: log what was measured.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLWaterLook : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLWaterLook* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	/** Measures the shore and gives the water sheets their instance (again: after the level changed). */
	void Build();
	/** The depth look on or off (the instances stay; ShoreOn and DepthOn are set). */
	void SetOn(bool bOn);
	/** cm from that point of the water to the shore (0 on land; ShoreRange at most). -1: not measured. */
	float ShoreDistance(const FVector2D& P) const;
	FString Describe() const;

	/** cm: the texture's alpha of 1 (what is further from the shore than this is as deep as it gets). */
	static constexpr float ShoreRange = 4000.f;
	static constexpr float CellSize = 125.f;

private:
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> ShoreTex;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> Instances;

	TArray<uint8> Shore;        // per cell: the distance, 0..255 over ShoreRange
	FVector2D Origin = FVector2D::ZeroVector;
	int32 DimX = 0, DimY = 0;
	int32 Sheets = 0, WaterCells = 0;
	double BuildMs = 0.0;
};
