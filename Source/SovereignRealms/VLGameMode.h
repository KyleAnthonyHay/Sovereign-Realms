#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "VLKing.h"
#include "VLGameMode.generated.h"

/** Puts King David in the scene, and runs console commands dropped into Saved/VLCommands.txt (Tools/pie.py). */
UCLASS()
class SOVEREIGNREALMS_API AVLGameMode : public AGameModeBase
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

	/** The player's music volume (Esc menu / U): 0..100% of MusicVolume, saved ([SovereignRealms.Audio] Music); on (100%)
	 *  until the player turns it down. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Audio")
	float MusicSetting = 0.5f;      // (50% for a new player, the owner's call 2026-11-24; the player's own choice is kept: MusicV2)

	void CycleMusicVolume();
	/** Settings > Music: 0..1, applied at once and saved. */
	void SetMusicSetting(float Setting);
	float GetMusicSetting() const { return MusicSetting; }
	/** The same without saving it (vl.Music, for tests); and what the music is doing now, for the log. */
	void ApplyMusicSetting(float Setting);
	FString DescribeMusic() const;

	UPROPERTY(EditAnywhere, Category = "Voxel|Audio")
	float AmbientVolume = 0.15f;    // TEMP: ambience low (user request, 2026-11-21) — restore to 0.4f

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

	// ---- training troops: the barracks trains swordsmen, the archery range archers (the rules: UVLBattle)
	/** "Swordsman", "Archer", or empty if the building trains nothing. */
	static FString TroopFor(const AActor* Building);
	/** Queue one at that building (paid for and housed: UVLBattle::Train); it walks out of the front when trained. */
	void Train(AActor* Building);
	/** How many are queued there (the one in training included), and how far the current one is (0..1). */
	int32 Queued(const AActor* Building) const;
	float Progress(const AActor* Building) const;

	// ---- the match: the level is opened with ?Match=1?Difficulty=N from the New Game screen (or Restart, vl.Map); without
	// them the title screen comes up over it (AVLHUD)
	virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
	bool HasMatchOption() const { return bMatchOption; }
	/** Opened as the Test World (?TestWorld=1: UVLBattle::SetupTestWorld right after the match starts). */
	bool IsTestWorld() const { return bTestWorldOption; }

private:
	float PollTimer = 0.f;
	bool bMatchOption = false;
	int32 OptionDifficulty = 1;
	bool bTestWorldOption = false;
	int32 OptionAIvsAI = -1;            // ?AIvsAI=<difficulty>: a commander for the player's side too (balance runs)
	float OptionTimeScale = 0.f;        // ?TimeScale=N
	bool bDuelsOption = false;          // ?Duels=1[?DuelAt=X,Y]: the standard duels (FVLDuels), then quit
	bool bMatchStarted = false;

	UPROPERTY(Transient)
	TObjectPtr<class UAudioComponent> Music;
	UPROPERTY(Transient)
	TObjectPtr<class UAudioComponent> Ambient;
	/** The song playing (or fading in). The songs are not loaded while the music setting is 0: the next one is loaded
	 *  when it is wanted (in the background), and let go of when the music is turned off. */
	UPROPERTY(Transient)
	TObjectPtr<class USoundBase> SongPlaying;
	TSharedPtr<struct FStreamableHandle> SongLoad;
	bool bSongLoading = false;
	int32 SongFailures = 0;         // songs in a row that would not load (all of them: the music gives up)
	static constexpr int32 NumSongs = 8;        // S_Music_1..8
	int32 Song = -1;
	/** The next song. bNow (the player has just turned the music on): loaded at once and started with a short fade;
	 *  otherwise loaded in the background and faded in (one song after another). */
	void NextSong(bool bNow = false);
	/** Plays a loaded song on the music's component (made if need be), fading in over FadeSeconds. */
	void StartSong(class USoundBase* Sound, float FadeSeconds);
	void StopMusic();

	UPROPERTY(Transient)
	TObjectPtr<class USoundBase> OrderSound;
	UPROPERTY(Transient)
	FVLStepSet ShuffleSteps;
	UPROPERTY(Transient)
	TObjectPtr<class USoundAttenuation> ShufflePan;
	/** Seconds until each marching group's next step, by its first member. */
	TMap<TWeakObjectPtr<AVLKing>, float> ShuffleTimers;
	void TickShuffle(float DeltaSeconds);


	/** The windmill's sails (actors tagged Spin), turned a little every frame. */
	TArray<TWeakObjectPtr<AActor>> Spinners;


public:
	/** Puts a troop on the ground at a point, with no training (vl.Spawn: for tests). */
	class AVLTroop* SpawnTroopAt(const FString& Kind, const FVector& Ground, float Yaw = 0.f);
};
