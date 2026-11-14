// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Common/SRTypes.h"
#include "SRPlacementPreview.generated.h"

class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
struct FSRPlacement;

/**
 * What the player sees while placing a building: the building itself as glowing glass (green: it fits, red: it
 * does not), and the build grid round it, one plate per cell. Footprint cells are bright green / red; cells in a
 * fringe round the footprint show where the ground is blocked (rocks, trees, water, cliffs, other buildings), so
 * it is obvious why a spot is refused and which way to nudge the cursor.
 */
UCLASS(NotPlaceable)
class SOVEREIGNREALMS_API ASRPlacementPreview : public AActor
{
	GENERATED_BODY()

public:
	ASRPlacementPreview();

	void Show(ESRBuildingType Type, const FSRPlacement& Placement);
	void Hide();

private:
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> Ghost;
	UPROPERTY(Transient) TObjectPtr<UInstancedStaticMeshComponent> Cells;
	ESRBuildingType ShownType = ESRBuildingType::Castle;
	bool bHasMesh = false;
	FIntPoint LastCentre = FIntPoint(MIN_int32, MIN_int32);
	bool bLastValid = false;
};
