#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "VLNet.h"
#include "VLPlayerController.generated.h"

/**
 * Collects the Mac trackpad's gestures for AVLKing, which reads and clears them once a frame (TakeGestures):
 * two-finger scroll (it arrives as a gesture, not as mouse wheel clicks), pinch and rotate.
 */
UCLASS()
class SOVEREIGNREALMS_API AVLPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	virtual bool InputGesture(const FInputDeviceId DeviceId, EGestureEvent GestureType, EGesturePhase GesturePhase, const FVector2D& GestureDelta,
		bool bIsDirectionInvertedFromDevice, const uint64 Timestamp) override;

	/** Since the last call: Scroll in points (x right, y down the screen as the content moves: it follows the OS
	 *  scrolling direction), Pinch (+ spreads the fingers: closer), Rotate (degrees, + anticlockwise). */
	void TakeGestures(FVector2D& OutScroll, float& OutPinch, float& OutRotate);

	// ---- multiplayer (VLNet.h). The joining player's game asks the host for everything its player does through these;
	// the host checks whose the units and buildings are (VLNet::TeamOf(this)) and then calls the same function the
	// single-player game calls. None of this is used in a single-player game.
	/** An order for units (UVLCommand's and UVLConstruction's order functions). */
	UFUNCTION(Server, Reliable)
	void ServerOrder(const FVLNetOrder& Order);

	/** Something asked of a building, or of the kingdom (train, upgrade, rally, cancel, demolish, turn ...). */
	UFUNCTION(Server, Reliable)
	void ServerBuilding(EVLNetBuildingAsk Ask, const FVLNetRef& Building, int32 Arg, const FString& Kind, const FVector& Ground);

	/** A building laid (UVLConstruction::PlaceBuilding): checked and paid for on the host. */
	UFUNCTION(Server, Reliable)
	void ServerPlace(uint8 Kind, const FVector& Location, float Yaw, const TArray<AVLKing*>& Builders, bool bQueue);

	/** The unit the joining player plays: a click of its sword (Kind < 0: the next of the combo), facing Yaw. */
	UFUNCTION(Server, Reliable)
	void ServerSwing(AVLKing* Unit, int32 Kind, bool bFace, float Yaw);

	/** ... its sword drawn or put away (F), and its pace (walking, running, or held to a cap). */
	UFUNCTION(Server, Reliable)
	void ServerSetArmed(AVLKing* Unit, bool bArmed);

	UFUNCTION(Server, Unreliable)
	void ServerSetPace(AVLKing* Unit, float MaxSpeed);

	/** ... and which view it is played in (the hero view: its player's hands; the overview: it takes orders). */
	UFUNCTION(Server, Reliable)
	void ServerSetHero(AVLKing* Unit, bool bHero);

	/** ... and the walk it was sent on (it walks it on its own machine: ClientFollowPath) is over, or dropped. */
	UFUNCTION(Server, Reliable)
	void ServerOrderDone(AVLKing* Unit, bool bArrived, bool bStopped);

	/** The host is told the joining game has the level up and its unit in hand: the match can start. */
	UFUNCTION(Server, Reliable)
	void ServerReady();

	// the host tells the joining player what its own game cannot know
	UFUNCTION(Client, Reliable)
	void ClientAlert(const FString& Text, uint8 Kind, bool bHasAt, const FVector& At);

	UFUNCTION(Client, Unreliable)
	void ClientSound(FName Base, bool bAt, const FVector& At, float Volume, float Range);

	UFUNCTION(Client, Unreliable)
	void ClientPopup(const FVector& At, int32 Amount, bool bGold);

	UFUNCTION(Client, Unreliable)
	void ClientArrows(const TArray<FVLNetArrow>& Arrows);

	/** The unit the joining player plays was given a walk by the host (an order, a fight's approach): it walks it here,
	 *  where its movement is predicted; or the walk is taken back. */
	UFUNCTION(Client, Reliable)
	void ClientFollowPath(AVLKing* Unit, const TArray<FVector>& Points, bool bRun);

	UFUNCTION(Client, Reliable)
	void ClientStopOrder(AVLKing* Unit);

	/** A rock of the level was cleared on the host: it goes here too. */
	UFUNCTION(Client, Reliable)
	void ClientRockCleared(AActor* Rock);

	/** The match is over for this player without a castle falling (the host has left): back to the title, with Why. */
	UFUNCTION(Client, Reliable)
	void ClientMatchClosed(const FString& Why);

	virtual void BeginPlay() override;
	bool bNetReady = false;
	/** The host: arrows loosed this frame, sent to the joining player in one call (AVLGameState::Tick). */
	TArray<FVLNetArrow> ArrowsOut;

private:
	FVector2D Scroll = FVector2D::ZeroVector;
	float Pinch = 0.f;
	float Rotate = 0.f;
};
