// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "SRCameraPawn.generated.h"

class UCameraComponent;
class UExponentialHeightFogComponent;

/**
 * RTS camera rig. The pawn sits on the ground at the focus point; the camera hangs
 * back along the view direction. All smoothing is exponential (time-constant based),
 * so it behaves identically at any frame rate.
 *
 * Input arrives from ASRPlayerController; tuning lives in USRFeelSettings (Camera).
 */
UCLASS()
class SOVEREIGNREALMS_API ASRCameraPawn : public APawn
{
	GENERATED_BODY()

public:
	ASRCameraPawn();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** X = screen right, Y = screen up, each -1..1. Set every frame by the controller. */
	void SetPanInput(const FVector2D& Input) { PanInput = Input; }

	/** Positive notches zoom in. CursorGround (optional) pulls the focus toward the cursor when zooming in. */
	void AddZoomInput(float Notches, const FVector* CursorGround);

	/** Middle-mouse "grab the ground and drag". */
	void BeginDragPan();
	void EndDragPan();

	void FocusOn(const FVector2D& WorldXY, bool bSnap);
	/** Moves the view by a ground offset at once (a trackpad's two-finger scroll); clamped to the map like any pan. */
	void AddPanOffset(const FVector2D& WorldDelta);
	/** Ground distance (cm) across one screen pixel at the focus, roughly: for pans that should feel 1:1. */
	float GetGroundPerPixel(float ViewportWidthPixels) const;
	void SetZoom(float Zoom01, bool bSnap);
	void AddTrauma(float Amount);

	/** The film (sr.Film): the view is placed outright each frame, with its own pitch (degrees, negative = down), and
	 * the pawn's own panning, zoom easing and map clamp stand aside. bCut: a new shot (nothing eases across it). */
	void FilmView(const FVector2D& WorldXY, float Zoom01, float Pitch, bool bCut, float DeltaSeconds);
	/** Back to the player's camera. */
	void EndFilm() { bFilm = false; }

	FVector GetFocusPoint() const { return FVector(Focus.X, Focus.Y, FocusZ); }
	/** Rotation the view is rendered with this frame. Sprite cards copy it (see USRBattleSubsystem::UpdateSpriteView). */
	FRotator GetViewRotation() const;
	float GetZoomDistance() const;

private:
	bool CursorOnFocusPlane(FVector& OutPoint) const;
	/** Places the camera for this frame. DeltaSeconds 0 (a snap: FocusOn, SetZoom, the first frame) takes the terrain
	 * clearance at once instead of easing toward it. */
	void ApplyView(float DeltaSeconds);
	/** Terrain clearance: how much steeper than BasePitch (degrees, 0 or negative) the view must tilt so that the line
	 * from the focus point back to the camera clears the ground (USRFeelSettings::CameraGroundClearance). */
	float ClearancePitch(const FVector& FocusPoint, float BasePitch, float Distance) const;

	UPROPERTY(VisibleAnywhere, Category = "Camera") TObjectPtr<UCameraComponent> Camera;

	/** The level's height fog, if it has one: its start distance follows the focus distance (Sovereign Feel > Visuals > Haze). */
	TWeakObjectPtr<UExponentialHeightFogComponent> Haze;

	FVector2D Focus = FVector2D::ZeroVector;
	float FocusZ = 0.f;
	FVector2D PanVelocity = FVector2D::ZeroVector;
	FVector2D PanInput = FVector2D::ZeroVector;

	float Zoom = 0.5f;        // 0 = fully in, 1 = fully out (smoothed)
	float ZoomTarget = 0.5f;

	bool bRecentering = false;
	FVector2D RecenterGoal = FVector2D::ZeroVector;

	bool bDragging = false;
	FVector DragAnchor = FVector::ZeroVector;

	/** The extra tilt the terrain asks for right now (degrees, 0 or negative), eased: see ClearancePitch. */
	float PitchLift = 0.f;

	/** The film has the view (FilmView): Tick leaves it alone; FilmPitch replaces the camera-angle setting's pitch. */
	bool bFilm = false;
	float FilmPitch = -40.f;

	float Trauma = 0.f;
	float ShakeClock = 0.f;
};
