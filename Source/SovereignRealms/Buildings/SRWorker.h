// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SRWorker.generated.h"

class ASRBuilding;
class UStaticMeshComponent;

/**
 * A worker at a farm or a mine: purely cosmetic (no collision, cannot be selected or hurt), but the building's
 * income is paid when one of them delivers, so what you see is what you earn.
 *
 *   Miner     walks into the adit and vanishes into the dark, works out of sight (you hear the pick), comes out
 *             with a basket of ore, tips it into the cart (payout), and goes back in.
 *   Farmhand  walks to a spot in the field, hoes it for a while, carries the cut sheaves to the cottage (payout),
 *             and picks another spot.
 *
 * Drawn like the troops: a sprite card from SourceArt/Characters/<miner|farmer>_color.png (same sheet layout;
 * the attack block is the work swing) plus a hidden shadow card. The pace is set so each worker delivers once
 * every PayoutInterval x WorkersPerBuilding seconds, which keeps the building's income what the settings say.
 */
UCLASS(NotPlaceable)
class SOVEREIGNREALMS_API ASRWorker : public AActor
{
	GENERATED_BODY()

public:
	ASRWorker();

	static ASRWorker* SpawnWorker(ASRBuilding* Home, int32 Index);

	virtual void Tick(float DeltaSeconds) override;

private:
	enum class EState : uint8 { Inside, ToWork, Working, ToDrop, Dropping };

	void Begin(EState NewState);
	bool WalkTo(const FVector2D& Goal, float Dt);
	void Present(float Dt);
	FVector2D LocalToWorld(const FVector2D& Local) const;
	float CycleTime() const;

	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> Card;
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> ShadowCard;

	TWeakObjectPtr<ASRBuilding> Home;
	bool bMiner = true;
	int32 Index = 0;
	EState State = EState::ToWork;
	FVector2D Pos = FVector2D::ZeroVector;
	FVector2D Goal = FVector2D::ZeroVector;
	float Z = 0.f;
	float Yaw = 0.f;
	float StateTime = 0.f;
	float StateDuration = 1.f;
	float WalkDistance = 0.f;
	float AnimClock = 0.f;
	float Fade = 0.f;
	float SoundClock = 0.f;
	bool bMoving = false;
	int32 Facing = 0;
	int32 ShadowFacing = 0;
	int32 LastWorkFrame = -1;
	FVector4 Applied = FVector4(-1.f, -1.f, -1.f, -1.f);
};
