#include "VLPlayerController.h"

bool AVLPlayerController::InputGesture(const FInputDeviceId DeviceId, EGestureEvent GestureType, EGesturePhase GesturePhase,
	const FVector2D& GestureDelta, bool bIsDirectionInvertedFromDevice, const uint64 Timestamp)
{
	switch (GestureType)
	{
	case EGestureEvent::Scroll:
		Scroll += GestureDelta;       // handled here: Slate then does not turn it into mouse wheel steps as well
		return true;
	case EGestureEvent::Magnify:
		Pinch += GestureDelta.X;
		return true;
	case EGestureEvent::Rotate:
		Rotate += GestureDelta.X;
		return true;
	default:
		return Super::InputGesture(DeviceId, GestureType, GesturePhase, GestureDelta, bIsDirectionInvertedFromDevice, Timestamp);
	}
}

void AVLPlayerController::TakeGestures(FVector2D& OutScroll, float& OutPinch, float& OutRotate)
{
	OutScroll = Scroll;
	OutPinch = Pinch;
	OutRotate = Rotate;
	Scroll = FVector2D::ZeroVector;
	Pinch = Rotate = 0.f;
}
