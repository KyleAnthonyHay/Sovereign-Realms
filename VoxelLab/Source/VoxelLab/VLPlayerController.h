#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "VLPlayerController.generated.h"

/**
 * Collects the Mac trackpad's gestures for AVLKing, which reads and clears them once a frame (TakeGestures):
 * two-finger scroll (it arrives as a gesture, not as mouse wheel clicks), pinch and rotate.
 */
UCLASS()
class VOXELLAB_API AVLPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	virtual bool InputGesture(const FInputDeviceId DeviceId, EGestureEvent GestureType, EGesturePhase GesturePhase, const FVector2D& GestureDelta,
		bool bIsDirectionInvertedFromDevice, const uint64 Timestamp) override;

	/** Since the last call: Scroll in points (x right, y down the screen as the content moves: it follows the OS
	 *  scrolling direction), Pinch (+ spreads the fingers: closer), Rotate (degrees, + anticlockwise). */
	void TakeGestures(FVector2D& OutScroll, float& OutPinch, float& OutRotate);

private:
	FVector2D Scroll = FVector2D::ZeroVector;
	float Pinch = 0.f;
	float Rotate = 0.f;
};
