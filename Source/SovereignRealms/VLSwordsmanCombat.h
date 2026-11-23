#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLSwordsmanCombat.generated.h"

class AVLKing;
class USoundBase;
class USoundAttenuation;

/**
 * What a sword blow does to the world, for every sword in it (King David's and the swordsmen's): the whoosh of a
 * swing, the thunk of a blow on a training dummy, and the dummy rocking on its foot. One place, so that a dummy hit
 * by several fighters rocks once (about its own rest pose) and a company swinging together does not pile its sounds
 * up: a whoosh or a thunk that would come within vl.Sword.SoundGap seconds of the last is left out.
 *
 * Volumes fade with the distance from where the player is looking (AVLKing::GetListenFocus), as the troops' shuffle
 * does. Console variables: vl.Sword.SwingVolume, vl.Sword.HitVolume, vl.Sword.TroopVolume, vl.Sword.SoundGap,
 * vl.Sword.Near, vl.Sword.Range; vl.CombatLog 1 logs every swing, hit and sound.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLSwordFx : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLSwordFx* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Tick(float DeltaSeconds) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UVLSwordFx, STATGROUP_Tickables); }

	/** A swing starts: its whoosh. */
	void Swing(const AVLKing* By);
	/** A blow lands on a training dummy: it is knocked Away (a direction on the ground) and rocks until it settles;
	 *  the thunk. By may be null (anything else that hits a dummy can call this too). */
	void HitDummy(AActor* Dummy, const FVector& Away, const AVLKing* By = nullptr);

private:
	struct FWobble
	{
		TWeakObjectPtr<AActor> Actor;
		FRotator Base;
		FVector Away;
		float Time = 0.f;
	};
	TArray<FWobble> Wobbles;

	void Load();
	/** Played unless one of its kind was played a moment ago. Volume: before the fade with distance. */
	void Play(TArray<TObjectPtr<USoundBase>>& Set, int32& Last, double& LastTime, const TCHAR* What, const FVector& At, float Volume, const AVLKing* By);

	UPROPERTY(Transient)
	TArray<TObjectPtr<USoundBase>> SwingSounds;

	UPROPERTY(Transient)
	TArray<TObjectPtr<USoundBase>> ThunkSounds;

	UPROPERTY(Transient)
	TObjectPtr<USoundAttenuation> Pan;

	bool bLoaded = false;
	int32 LastSwing = -1, LastThunk = -1;
	double LastSwingTime = -1.0, LastThunkTime = -1.0;
};

/**
 * A swordsman fighting on orders (not the player's hands: a troop the player controls swings on the left click, as
 * King David does, through AVLKing::Attack).
 *
 * Ordered to attack a training dummy (UVLCommand::OrderAttack: a left click on a dummy in the overview, or
 * vl.AttackDummy) the swordsmen each get a place on a ring round it, walk there by the usual routes (UVLGrid), turn
 * to it and swing at a steady rate, each on its own beat: the King's three swings in turn, in the battle stance, the
 * blows landing through AVLKing::HitDummies. One that ends up out of reach steps closer. They keep at it until given
 * another order (UVLCommand::StopAttack) or taken over by the player.
 *
 * The component is made the first time a swordsman is ordered to attack (For).
 */
UCLASS()
class SOVEREIGNREALMS_API UVLSwordsmanCombat : public UActorComponent
{
	GENERATED_BODY()

public:
	UVLSwordsmanCombat();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Can this unit fight with a sword on orders (a swordsman troop, or King David)? */
	static bool CanFight(const AVLKing* Unit);
	/** The unit's component; made if it has none yet (and it is a swordsman). */
	static UVLSwordsmanCombat* For(AVLKing* Unit, bool bCreate = true);
	/** The swordsmen among Units go and attack Target, spread round it. Returns how many were ordered. */
	static int32 OrderAttack(const TArray<AVLKing*>& Units, AActor* Target, bool bRun);

	/** Attack Target once the order the unit is on (the walk to its place) has ended. */
	void Begin(AActor* InTarget);
	/** No more swings (the one in the air finishes, the stance lapses by itself). */
	void Stop();
	bool IsAttacking() const { return Target.IsValid(); }
	AActor* GetTarget() const { return Target.Get(); }

	/** Seconds from one swing to the next (the three swings take 0.46, 0.46 and 1 s; under about 1.4 the battle
	 *  stance holds between them and the combo goes round). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float SwingInterval = 1.25f;

	/** Each gap is off by up to this share either way; the first swing comes after a random part of the interval. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float SwingJitter = 0.12f;

	/** Where they stand: the first ring's radius round the dummy (cm), the room each takes along a ring, and how much
	 *  further out each further ring is. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float RingRadius = 150.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float RingSpacing = 105.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float RingStep = 65.f;

	/** Further from the dummy than this (cm) it steps closer before swinging, for at most CloseInSeconds (others may
	 *  stand in the way). Still further than BlowReach then (a blow reaches 230: AVLKing::HitDummies), it waits,
	 *  facing the dummy, and tries again every RetrySeconds. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float Reach = 205.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float BlowReach = 228.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float CloseInSeconds = 2.5f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float RetrySeconds = 3.f;

	/** Its walk ended further from the dummy than this (it could not get there): it drops the attack. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float GiveUpBeyond = 600.f;

	/** The charge: further than this (cm) from where it is going, a fighter sent at a foe goes at a run, the first
	 *  walk as well as every fresh route of a chase. The archers' walk into range keeps the same rule
	 *  (UVLArcherCombat::Approach), so a mixed group sent at one foe travels together. */
	static constexpr float ChargeBeyond = 700.f;

	/** Degrees a second it turns to face the dummy; it swings once within FaceWithin degrees of it. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float TurnRate = 540.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float FaceWithin = 20.f;

private:
	TWeakObjectPtr<AActor> Target;
	bool bEngaged = false;      // at its place: turning, closing in, swinging
	float NextSwing = 0.f;
	float Closing = 0.f;        // seconds spent stepping closer
	float Waiting = 0.f;        // seconds stood out of reach since
	int32 Swings = 0;
	// a foe that moves (a unit): it is run down by a fresh route every RepathSeconds while out of reach
	bool bChasing = false;
	float RepathIn = 0.f;
	int32 Chases = 0;
	float BestDist = 1e9f;
	void Chase(AVLKing* Unit, const AVLKing* Foe);
	/** How far it is from the target, as the reach is measured: centre to centre for a unit or a dummy, the walls for a
	 *  building (plus 100, so the same reach numbers serve). */
	float DistanceTo(const AVLKing* Unit, const AActor* To) const;

public:
	UPROPERTY(EditAnywhere, Category = "Voxel|Combat")
	float RepathSeconds = 0.6f;
};
