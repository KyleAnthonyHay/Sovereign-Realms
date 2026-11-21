#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "VLSpy.generated.h"

class AVLKing;
class USceneComponent;
class UPointLightComponent;

/**
 * The Spy's own (the main game's Scout; the troop's rules are VLRules::Troop("Spy"), UVLBattle): made on every spy
 * (AVLTroop::BeginPlay), it ticks after the figure is posed (AVLKing::Animate) and
 *
 *   the spyglass   raises the spyglass (part "Spyglass", in the right fist) to the right eye: the arm by a two-bone
 *                  solve, the fist turned so the tube lies along the line of sight, its eyepiece at the eye. While
 *                  the player plays the spy: as long as the RIGHT MOUSE BUTTON (right trigger) is held; the spy then
 *                  faces the way the camera looks, walks slowly, and the camera looks far ahead (LookAhead) through a
 *                  narrower lens (ZoomFOV). A spy standing idle on its own raises it too, now and then: it is looking.
 *   the hood       swings the hood's loose tail (parts "HoodA" > "HoodB", hinged on the head) as cloth: streamed back
 *                  by its speed, thrown by its acceleration, lifted in a fall, with a flutter; never forward into the
 *                  head. (The wind's own flutter is in its material: slot "sway", M_VoxSway by the vertex alpha.)
 *   the lantern    a small warm light at the lantern on its back.
 *
 * Console: vl.Spies (log each), vl.Spyglass 0|1 (hold it up / let it down, as the right button would; every spy).
 */
UCLASS()
class VOXELLAB_API UVLSpy : public UActorComponent
{
	GENERATED_BODY()

public:
	UVLSpy();
	static bool IsSpy(const AVLKing* Unit);
	static UVLSpy* For(AVLKing* Unit, bool bCreate = true);
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	bool IsLooking() const { return Raise > 0.5f; }
	float GetRaise() const { return Raise; }
	void SetTestRaise(bool bOn) { bTestRaise = bOn; }
	FString Describe() const;

	// ---- the spyglass (character space: X forward, Y right, Z up; cm). From SM_Spy.json (Tools/blender/assets/troop_spy.py).
	/** The way the big lens points as modelled in the fist. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	FVector GlassDir = FVector(0.83867f, -0.05693f, 0.54166f);

	/** From the middle of the grip back to the end of the eyepiece. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float EyepieceLength = 13.75f;

	/** The pupil of the right eye, from the head's joint. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	FVector EyeOffset = FVector(16.25f, 7.5f, 20.f);

	/** The gap left between the eyepiece and the eye. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float EyeGap = 2.f;

	/** How fast it comes up and goes down (1 / seconds). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float RaiseSpeed = 4.5f;

	/** While the player holds it up: the camera looks this far ahead of the spy (cm), through this share of its lens
	 *  angle; and the spy walks no faster than this share of its walking speed. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float LookAhead = 2600.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float ZoomFOV = 0.72f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float LookMoveScale = 0.3f;

	/** A spy standing idle on its own looks through it after this long, for IdleLookSeconds at a time. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float IdleLookAfter = 2.5f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float IdleLookSeconds = 6.f;

	// ---- the hood's tail
	/** Degrees it streams back per cm/s of speed, and per cm/s2 of acceleration; how far at most. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy|Hood")
	float HoodTrail = 0.04f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy|Hood")
	float HoodInertia = 0.006f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy|Hood")
	float HoodMax = 62.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy|Hood")
	float HoodStiff = 9.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy|Hood")
	float HoodDamping = 0.45f;

	/** The flutter: degrees standing still, and more at a run. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy|Hood")
	float HoodFlutter = 2.5f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy|Hood")
	float HoodFlutterRun = 6.f;

	// ---- the lantern
	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	FVector LanternOffset = FVector(-38.75f, 53.75f, 7.5f);      // from the chest's joint

	UPROPERTY(EditAnywhere, Category = "Voxel|Spy")
	float LanternIntensity = 900.f;

private:
	bool Setup(AVLKing* Unit);
	void TickGlass(AVLKing* Unit, float Dt);
	void TickHood(AVLKing* Unit, float Dt);
	/** The arm and the hood as the two above have them, written to the unit's pose buffer (AVLKing::Rig...): in this
	 *  component's tick when the unit was posed in its own, else when the unit is posed (seen, later in the frame). */
	void PoseGlass(AVLKing* Unit);
	void PoseHood(AVLKing* Unit);
	int32 iChest = -1, iHead = -1, iArmR = -1, iForeR = -1, iHandR = -1, iGlass = -1, iHoodA = -1, iHoodB = -1;
	float GlassShare = 0.f;     // how far up the spyglass is, eased (0: the arm is left to the gait)

	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> Chest;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> Head;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> ArmR;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> ForeR;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> HandR;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> Glass;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> HoodA;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> HoodB;
	UPROPERTY(Transient)
	TObjectPtr<UPointLightComponent> Lantern;

	bool bSetup = false;
	bool bBroken = false;
	FVector UpperR = FVector::ZeroVector;      // shoulder -> elbow, elbow -> wrist, wrist -> grip (rest pose)
	FVector ForeVec = FVector::ZeroVector;
	FVector GripOff = FVector::ZeroVector;
	float Raise = 0.f;
	bool bHands = false;
	bool bTestRaise = false;
	bool bCamera = false;                      // the camera is looking ahead (to be put back)
	float IdleTime = 0.f;
	float EyeError = 0.f;                      // cm between the eyepiece and the eye, degrees off the line of sight (logged)
	float AimError = 0.f;
	// the tail: two hinges
	float HoodPitch[2] = { 0.f, 0.f };
	float HoodVel[2] = { 0.f, 0.f };
	float HoodRoll = 0.f;
	float HoodRollVel = 0.f;
	FVector LastVel = FVector::ZeroVector;
	FVector Acc = FVector::ZeroVector;
	float LastYaw = 0.f;
	float Time = 0.f;
	bool bStarted = false;
};
