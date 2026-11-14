// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Common/SRTypes.h"
#include "SRProjectile.generated.h"

class ASRUnit;

/**
 * An arrow. Flies an arc toward its target (tracking it, so arrows aimed at a
 * living unit always land) and applies damage on impact, not on release.
 * If the target dies mid-flight the arrow carries on and sticks in the ground.
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
