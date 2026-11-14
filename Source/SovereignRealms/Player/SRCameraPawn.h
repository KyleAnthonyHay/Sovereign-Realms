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
	void SetZoom(float Zoom01, bool bSnap);
	void AddTrauma(float Amount);

	FVector GetFocusPoint() const { return FVector(Focus.X, Focus.Y, FocusZ); }
	float GetZoomDistance() const;

private:
	bool CursorOnFocusPlane(FVector& OutPoint) const;
	void ApplyView(float DeltaSeconds);

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

	float Trauma = 0.f;
	float ShakeClock = 0.f;
};
