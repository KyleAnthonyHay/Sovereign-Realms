#include "VLTroop.h"
#include "VLCharacterData.h"
#include "VLArcherCombat.h"
#include "VLBattle.h"
#include "VLSpy.h"
#include "GameFramework/CharacterMovementComponent.h"

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
	UVLSpy::For(this);                  // a spy: its spyglass, its hood's tail, its lantern
	// a kind with a pace of its own (the Spy: very fast)
	const VLRules::FTroop& Rules = VLRules::Troop(UnitKind);
	if (Rules.WalkSpeed > 0.f)
	{
		WalkSpeed = Rules.WalkSpeed;
		RunSpeed = FMath::Max(Rules.RunSpeed, Rules.WalkSpeed);
		GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
		GetCharacterMovement()->MaxAcceleration = 3600.f;              // (the main game's Scout: quick off the mark)
		GetCharacterMovement()->BrakingDecelerationWalking = 3800.f;
	}
}

TSoftObjectPtr<UVLCharacterData> AVLTroop::DataFor(const FString& Kind)
{
	const FString Path = FString::Printf(TEXT("/Game/Voxel/Troops/%s/DA_%s.DA_%s"), *Kind, *Kind, *Kind);
	return TSoftObjectPtr<UVLCharacterData>(FSoftObjectPath(Path));
}
