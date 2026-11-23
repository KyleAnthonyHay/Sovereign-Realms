#pragma once

#include "CoreMinimal.h"
#include "VLKing.h"
#include "VLTroop.generated.h"

/**
 * A troop (the swordsman, the archer, the spy): the same jointed voxel figure and movement as King David, built from its own
 * character data (/Game/Voxel/Troops/<Kind>/DA_<Kind>). Players command troops from the overview (select, right click
 * to send them); for testing a troop can also be taken over like the hero (Enter / double click). Movement and jumping
 * only for now: no attacks, no sword drawing, no footstep dust. Trained at the barracks / archery range (AVLGameMode::Train).
 */
UCLASS()
class SOVEREIGNREALMS_API AVLTroop : public AVLKing
{
	GENERATED_BODY()

public:
	AVLTroop();
	virtual void BeginPlay() override;

	/** "Swordsman", "Archer" or "Spy": its character data. */
	static TSoftObjectPtr<UVLCharacterData> DataFor(const FString& Kind);
};
