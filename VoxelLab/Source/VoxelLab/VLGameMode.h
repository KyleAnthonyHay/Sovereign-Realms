#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "VLKing.h"
#include "VLGameMode.generated.h"

/** Puts King David in the scene, and runs console commands dropped into Saved/VLCommands.txt (Tools/pie.py). */
UCLASS()
class VOXELLAB_API AVLGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AVLGameMode();
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void BeginPlay() override;

	// ---- sound: the soundtrack of the main game (S_Music_1..8, one after another) and its ambience
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio")
	float MusicVolume = 0.32f;

	/** The player's music volume (Esc menu / U): 0..100% of MusicVolume, saved. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio")
	float MusicSetting = 1.f;

	void CycleMusicVolume();
	float GetMusicSetting() const { return MusicSetting; }

	UPROPERTY(EditAnywhere, Category = "Voxel|Audio")
	float AmbientVolume = 0.4f;

	// ---- the order click: the player sends units somewhere from the overview (S_OrderMove, not in space)
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio")
	float OrderVolume = 0.6f;

	/** Its pitch is off by up to this share either way. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio")
	float OrderPitchJitter = 0.03f;

	/** Once, for an order the player gave by hand (a right click, Ctrl / Cmd + click, "Send them out"). */
	static void PlayOrderSound(const UObject* WorldContext);

	// ---- the shuffle of marching troops (S_Step_Carpet_<n>): troops on the move are gathered into groups, and each
	// group makes soft steps at its own pace from somewhere among its members: not a sound per foot per troop
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio|Shuffle")
	bool bTroopShuffle = true;

	/** Volume of a shuffle step heard from close by (the hero's walk is 0.32). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio|Shuffle")
	float ShuffleVolume = 0.2f;

	/** Steps a second from one troop walking alone. A group of N makes sqrt(N) times as many, up to ShuffleMaxRate. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio|Shuffle")
	float ShuffleRate = 2.2f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Audio|Shuffle")
	float ShuffleMaxRate = 6.5f;

	/** At a run: this much faster and louder. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio|Shuffle")
	float ShuffleRunBoost = 1.3f;

	/** Full volume within ShuffleNear (cm) of where the player is looking (the hero, or the overview's focus),
	 *  fading to silence at ShuffleRange. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio|Shuffle")
	float ShuffleNear = 900.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Audio|Shuffle")
	float ShuffleRange = 4500.f;

	/** Troops within this distance (cm) of a group's first member march as that group. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio|Shuffle")
	float ShuffleGroupRadius = 700.f;

	// ---- training troops: the barracks trains swordsmen, the archery range archers
	/** "Swordsman", "Archer", or empty if the building trains nothing. */
	static FString TroopFor(const AActor* Building);
	/** Queue one at that building; it walks out of the front after TrainSeconds (one at a time per building). */
	void Train(AActor* Building);
	/** How many are queued there (the one in training included), and how far the current one is (0..1). */
	int32 Queued(const AActor* Building) const;
	float Progress(const AActor* Building) const;

	UPROPERTY(EditAnywhere, Category = "Voxel|Training")
	float TrainSeconds = 3.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Training")
	int32 MaxQueue = 9;

private:
	float PollTimer = 0.f;

	UPROPERTY(Transient)
	TObjectPtr<class UAudioComponent> Music;
	UPROPERTY(Transient)
	TObjectPtr<class UAudioComponent> Ambient;
	UPROPERTY(Transient)
	TArray<TObjectPtr<class USoundBase>> Songs;
	int32 Song = -1;
	void NextSong();

	UPROPERTY(Transient)
	TObjectPtr<class USoundBase> OrderSound;
	UPROPERTY(Transient)
	FVLStepSet ShuffleSteps;
	UPROPERTY(Transient)
	TObjectPtr<class USoundAttenuation> ShufflePan;
	/** Seconds until each marching group's next step, by its first member. */
	TMap<TWeakObjectPtr<AVLKing>, float> ShuffleTimers;
	void TickShuffle(float DeltaSeconds);

	struct FQueue
	{
		TWeakObjectPtr<AActor> Building;
		int32 Count = 0;
		float Time = 0.f;
		int32 Trained = 0;
	};
	TArray<FQueue> Queues;
	TMap<FString, int32> Numbers;      // "Swordsman" -> how many have been trained (for their names)

	/** The windmill's sails (actors tagged Spin), turned a little every frame. */
	TArray<TWeakObjectPtr<AActor>> Spinners;

	FQueue* QueueFor(const AActor* Building);
	const FQueue* QueueFor(const AActor* Building) const;
	void SpawnTroop(FQueue& Q, const FString& Kind);

public:
	/** Puts a troop on the ground at a point, with no training (vl.Spawn: for tests). */
	class AVLTroop* SpawnTroopAt(const FString& Kind, const FVector& Ground, float Yaw = 0.f);
};
