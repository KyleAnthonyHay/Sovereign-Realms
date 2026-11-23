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
	if (IsJonathan())
	{
		// JONATHAN, the archer prince (VLRules::Jonathan*): his pace is already his own (AVLKing::BeginPlay took it from
		// his rules, with the stride and the getting up to speed that go with it); here his higher jump and his bow.
		// The bow is the played archer's (UVLArcherCombat: the draw bar, the arrows and their streaks, the same
		// buttons), with a longer draw and a faster arrow. The aim, the arcs and the lead on a moving target are
		// solved from the component's own ArrowSpeed, so they hold at his speed as they do at hers.
		GetCharacterMovement()->JumpZVelocity = VLRules::JonathanJumpZ;
		if (UVLArcherCombat* Bow = UVLArcherCombat::For(this))
		{
			Bow->DrawSeconds = VLRules::JonathanDrawSeconds;
			Bow->ArrowSpeed = VLRules::JonathanArrowSpeed;
			Bow->ArrowDamage = Rules.Damage;
			Bow->ShotInterval = VLRules::JonathanShotInterval;
			// his quiver (SM_Jonathan.json "quiver"): bigger than hers, slung across the back outside the cape
			Bow->QuiverAxis = FVector(0.15643f, 0.49384f, 0.85543f);
			Bow->QuiverMouth = 33.75f;
			Bow->GrabAbove = 26.f;
			// the bow carried a little further out and forward: clear of the fur mantle on his shoulders
			Bow->CarryArmOut = 16.f;
			Bow->CarryArmPitch = 32.f;
		}
	}
	else if (Rules.WalkSpeed > 0.f)
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
