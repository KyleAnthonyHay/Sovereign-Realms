// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SROrderMarker.generated.h"

class USRRingComponent;

/** Ground-click feedback: a ring that snaps in, shrinks onto the point and vanishes. */
UCLASS()
class SOVEREIGNREALMS_API ASROrderMarker : public AActor
{
	GENERATED_BODY()

public:
	ASROrderMarker();

	static ASROrderMarker* SpawnMarker(UWorld* World, const FVector& GroundPoint, const FLinearColor& Color);

	virtual void Tick(float DeltaSeconds) override;

private:
	UPROPERTY(Transient) TObjectPtr<USRRingComponent> OuterRing;
	UPROPERTY(Transient) TObjectPtr<USRRingComponent> InnerRing;
	FLinearColor Color = FLinearColor::Green;
	float Age = 0.f;
};
