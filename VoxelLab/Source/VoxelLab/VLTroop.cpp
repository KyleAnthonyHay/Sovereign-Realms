#include "VLTroop.h"
#include "VLCharacterData.h"
#include "VLArcherCombat.h"

AVLTroop::AVLTroop()
{
	bTroop = true;
	bFootDust = false;
	bFootsteps = false;
	DisplayName = TEXT("Troop");
	UnitKind = TEXT("Swordsman");
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
}

void AVLTroop::BeginPlay()
{
	Super::BeginPlay();
	UVLArcherCombat::For(this);         // an archer: her bow (how she carries it, and shooting); nothing for the others
}

TSoftObjectPtr<UVLCharacterData> AVLTroop::DataFor(const FString& Kind)
{
	const FString Path = FString::Printf(TEXT("/Game/Voxel/Troops/%s/DA_%s.DA_%s"), *Kind, *Kind, *Kind);
	return TSoftObjectPtr<UVLCharacterData>(FSoftObjectPath(Path));
}
