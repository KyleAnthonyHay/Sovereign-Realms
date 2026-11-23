#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SpringArmComponent.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLCameraGround.generated.h"

class UStaticMeshComponent;

/** What a camera remembers of the ground under it from one frame to the next (UVLCameraGround::KeepAbove). */
struct FVLCameraFloor
{
	float Soft = 0.f;                       // the smoothed floor: it comes up fast and sinks slowly
	FVector LastEye = FVector::ZeroVector;
	bool bValid = false;
};

/**
 * Keeps the cameras out of the ground.
 *
 * THE RULE: a camera's eye is never lower than Clearance over the ground at its own place on the map. "The ground" is
 * the terrain (the actors the path grid stops at: tagged Ground, or SM_Terrain* / SM_Flat_* meshes) and the water's
 * surface; trees, units, buildings and the hidden walls do not count (a camera has always passed through those, and a
 * roof must not throw the view about). Where the terrain hangs over open air (an arch, an overhang, a cave) and the
 * eye is in that air, the floor is the ground under the eye, not the top of what hangs over it: the camera may go
 * under a mountain, never into it. Beyond the terrain's edge the floor is the edge's.
 *
 * An eye that would be too low is LIFTED straight up, and its owner turns the view down to what it was looking at
 * (AVLKing::UpdateOverviewCamera, UVLHeroBoom), so nothing is pulled in or cut short. The lift is smooth: the eye
 * rides on a smoothed floor Clearance over the ground (rising at RiseRate, sinking at FallRate, and looking
 * LookAheadSeconds along its own way so a hillside is climbed before it is met), which a 50 cm step of the voxel
 * ground moves without a jolt; only at HardShare of the clearance is it held up at once.
 *
 * Cost: nothing for an eye higher than everything on the map; else one short trace against the piece of terrain
 * under the eye, a second while the eye moves, two more only while it is lower than the terrain's top. The overview's pivot
 * (FocusZ) is one trace whenever it has moved.
 *
 * vl.Cam.Ground 0 switches all of it off, vl.Cam.Clearance <cm> is the overview's clearance, vl.Cam.Overhang 0 keeps
 * the eye over the top of the terrain everywhere, vl.Cam.Log 1 logs every half second a camera is being held up.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLCameraGround : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLCameraGround* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	/** Is it on, and does this level have ground? */
	bool IsActive();
	/** The overview's clearance, cm (vl.Cam.Clearance). */
	static float OverviewClearance();

	/** The top of the terrain over this point of the map. False: there is none here. */
	bool TopAt(const FVector2D& At, float& OutZ);
	/** The surface a view's pivot rests on over this point: the terrain's top or the water's, the terrain's edge
	 *  beyond it (OutTerrain, OutWater: each by itself). False: this level has no ground. */
	bool SurfaceAt(const FVector2D& At, float& OutZ, float* OutTerrain = nullptr, float* OutWater = nullptr);
	/** The floor under an eye (see the class comment). False: none. */
	bool FloorAt(const FVector& Eye, float Clearance, float& OutZ);

	/**
	 * Lifts Eye to Clearance over the ground under it if it is lower; returns by how much (0: it was clear). State is
	 * the camera's own, from frame to frame; bSnap: the camera was put somewhere new (nothing to smooth from).
	 */
	float KeepAbove(FVector& Eye, FVLCameraFloor& State, float DeltaSeconds, bool bSnap, float Clearance, const TCHAR* Who);

	/** The floor comes up at this rate and sinks at that one (1 / seconds, as FInterpTo's speed). */
	float RiseRate = 12.f;
	float FallRate = 2.5f;
	/** The eye is held at once at this share of its clearance (the rest of it is the room the smoothing has). */
	float HardShare = 0.45f;
	/** The floor is also read this far along the eye's way over the map (seconds of its speed, at most LookAheadMax cm). */
	float LookAheadSeconds = 0.35f;
	float LookAheadMax = 3000.f;

private:
	struct FPiece
	{
		TWeakObjectPtr<UStaticMeshComponent> Comp;
		FBox Box;
	};
	bool Collect();
	/** The nearest thing of the terrain between two points, one over the other. */
	bool Trace(const FVector2D& At, float FromZ, float ToZ, FHitResult& Out);

	TArray<FPiece> Pieces;
	FBox Bounds = FBox(ForceInit);
	double NextCollect = 0.0;
	double NextLog = 0.0;
};

/**
 * The hero camera's arm (AVLKing::Boom): a spring arm whose far end is kept out of the ground (UVLCameraGround). Its
 * probe against the world stays off (trees and roofs must not yank a diorama camera in); instead an eye that would be
 * in a hillside, or under the ground because the view was turned up, is lifted over it and turned to look at what
 * the arm was looking at, so the unit stays where it was in the picture.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLHeroBoom : public USpringArmComponent
{
	GENERATED_BODY()

public:
	/** cm over the ground. (Less than the overview's: looking up from behind the unit on flat ground, the eye is 80 cm
	 *  over it, and that view is to stay as it was.) */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float GroundClearance = 60.f;

protected:
	virtual void UpdateDesiredArmLocation(bool bDoTrace, bool bDoLocationLag, bool bDoRotationLag, float DeltaTime) override;

private:
	FVLCameraFloor Floor;
};
