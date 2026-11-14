// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Common/SRTypes.h"
#include "SRProjectile.generated.h"

class ASRUnit;
class UStaticMeshComponent;

/**
 * An arrow. Flies an arc toward its target (tracking it, so arrows aimed at a
 * living unit always land) and applies damage on impact, not on release.
 * If the target dies mid-flight the arrow carries on and sticks in the ground.
 *
 * Drawn as a pixel-art sprite (SourceArt/Characters/arrow_color.png) on a card that lies along the
 * flight direction and turns about it to face the camera, so it foreshortens like a real shaft.
 * A second, hidden card turned toward the sun casts its shadow.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRProjectile : public AActor
{
	GENERATED_BODY()

public:
	ASRProjectile();

	static ASRProjectile* Launch(ASRUnit* Shooter, ASRUnit* Target, const FVector& From, const FSRUnitStats& ShooterStats);

	virtual void Tick(float DeltaSeconds) override;

private:
	void BuildVisuals(ASRUnit* Shooter);
	void OrientCards(const FVector& Direction);

	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> Card;
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> ShadowCard;
	float AppliedFade = 1.f;

	TWeakObjectPtr<ASRUnit> ShooterUnit;
	TWeakObjectPtr<ASRUnit> TargetUnit;
	FVector Start = FVector::ZeroVector;
	FVector AimPoint = FVector::ZeroVector;
	float Duration = 0.3f;
	float Elapsed = 0.f;
	float ArcHeight = 0.f;
	float Damage = 0.f;
	float Knockback = 0.f;
	bool bStuck = false;
	bool bTargetLost = false;
	float StuckTime = 0.f;
};
