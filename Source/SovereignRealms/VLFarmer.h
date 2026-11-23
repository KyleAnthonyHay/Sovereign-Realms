#pragma once

#include "CoreMinimal.h"
#include "VLTroop.h"
#include "VLFarmer.generated.h"

/** Where a farm's hands go (world points on walkable ground of the farm's own: UVLConstruction::FarmSpots). */
struct FVLFarmSpots
{
	TArray<FVector> Field;              // among the crop rows
	FVector FieldCentre = FVector::ZeroVector;
	FVector Door = FVector::ZeroVector; // in front of the farmhouse door
	FVector Store = FVector::ZeroVector;// the hay and the barrel beside the house
	FVector Front = FVector::ForwardVector;     // the way the farm faces (its gate)
};

/**
 * A farm's hand (the farmer woman, Tools/blender/assets/troop_farmer_woman.py, and the farmer man, troop_farmer_man.py;
 * /Game/Voxel/Troops/FarmerWoman|FarmerMan/DA_*): the troops' jointed figure, gait and routes (AVLKing, UVLGrid), but a
 * figure of the scenery (AVLKing::bAmbient): no side, not in the battle's registry, never selected, ordered or struck,
 * passing through other units. UVLConstruction::TickFarmhands gives every finished farm one of each and takes them
 * away when it falls, is pulled down or is turned.
 *
 * Its round: it walks (slowly) between spots of its farm and works at each for a while. The woman cuts the crop rows
 * with her sickle, bent over them, and now and then takes her basket to the store or stops at the door; the man rakes
 * with his long-handled tool (the Pitchfork part) at the rows and at the store, and stops at the door: its tines on the
 * ground ahead, a reach forward and three short pulls back toward his feet, leaning into each. The work is a swing of the left arm (the
 * tool's hand) and a bend at the waist and the chest, laid over the gait's pose by a rig poser (AVLKing::AddRigPoser,
 * as the spy's spyglass and the archer's bow arm are), so it costs nothing while the figure is not posed (out of view).
 * Its round is thought over five times a second; nothing scans the world. Out of view it ticks four times a second,
 * seen far off ten times (UpdateTickRate).
 *
 * Console: vl.Farmhands (each, where and what it is doing), vl.Farmhands 0|1 (none / every finished farm's).
 */
UCLASS()
class SOVEREIGNREALMS_API AVLFarmer : public AVLTroop
{
	GENERATED_BODY()

public:
	AVLFarmer();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** A hand of Farm ("FarmerWoman" or "FarmerMan"), standing at At. Null if its character data is missing. */
	static AVLFarmer* Spawn(UWorld* World, const FString& Kind, AActor* Farm, const FVLFarmSpots& Spots, const FVector& At);
	AActor* GetFarm() const { return Farm.Get(); }
	FString Describe() const;
	/** Is the farm's work being done now (its tool swinging)? */
	bool IsWorking() const { return bWorking; }
	int32 GetWorkCount() const { return Worked; }
	int32 GetWalkCount() const { return Walked; }
	/** vl.Farmhands 0|1: farms get their hands (on by default). */
	static bool bEnabled;

	/** Its pace on its rounds (cm/s). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Farm")
	float FarmWalkSpeed = 240.f;

	/** Seconds at a spot: working (min, max) and stopping (at the door; the woman at the store). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Farm")
	FVector2D WorkSeconds = FVector2D(5.f, 9.f);

	UPROPERTY(EditAnywhere, Category = "Voxel|Farm")
	FVector2D RestSeconds = FVector2D(2.f, 4.f);

	/** The man's raking (seconds): one round of it, and of that the lift and reach forward (the rest: three pulls). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Farm")
	float RakeCycle = 3.2f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Farm")
	float RakeReach = 0.6f;

	/** From his grip to the tines' end along the tool's shaft (cm; SM_FarmerMan.json: pitchfork tip - grip). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Farm")
	float ToolReach = 85.6f;

	/** Seen beyond this far from the camera (cm), it ticks ten times a second; out of view, four. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Farm")
	float FarTickDistance = 15000.f;

private:
	enum class ESpot : uint8 { Field, Store, Door };
	enum class EStep : uint8 { Start, Walk, Work, Rest };
	void Think(double Now);
	void GoTo(ESpot Spot);
	void Arrive(double Now);
	void PoseWork();
	void UpdateTickRate();
	static const TCHAR* SpotName(ESpot Spot);

	TWeakObjectPtr<AActor> Farm;
	FVLFarmSpots Spots;
	bool bMan = false;
	EStep Step = EStep::Start;
	ESpot Where = ESpot::Door;
	FVector Target = FVector::ZeroVector;
	int32 FieldAt = INDEX_NONE;
	double StepEnd = 0.0;
	float ThinkClock = 0.f;
	float WantYaw = 0.f;
	bool bTurning = false;
	// the work's pose: eased in from WorkStart, out from WorkStop
	bool bWorking = false;
	double WorkStart = -100.0;
	double WorkStop = -100.0;
	float WorkRate = 1.f;
	int32 Worked = 0;
	int32 Walked = 0;
	int32 iBody = -1, iChest = -1, iArmL = -1, iForeL = -1, iArmR = -1, iTool = -1;
};
