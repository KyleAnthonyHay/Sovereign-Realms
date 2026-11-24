#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLRocks.generated.h"

class AActor;
class AVLKing;
class UVLFootDust;

/**
 * Clearing rocks (the owner's call, 2026-11-24: "builders should be able to remove rocks; it just takes a little time,
 * maybe 10 seconds"). The loose rocks and boulders the layout scripts scatter (the SM_Rock_A..E meshes, each a static
 * mesh actor of the level, in its Realm/Rocks folder; the mountains, ridges, crags and mesas are terrain meshes and are
 * not rocks here) block placing a building and walking. Builders clear one:
 *
 *   ordering   select Builders and right-click a rock (AVLKing::OrderOn; Shift: on the end of their queues). They
 *              walk to it by the usual routes (UVLBuilderWork, the rock as their job) and hammer at its side
 *   the work   ClearSeconds (10 s) with one Builder; each Builder at it adds as much again (VLBuild::ExtraSpeed), up
 *              to VLBuild::PerBuilding (4: 2.5 s). The rock sinks and shrinks a little as they work, dust at each blow
 *   cleared    the rock's actor goes, with a puff of dust and the rumble of stones;
 *              the path grid is sampled again round it, so the ground can be walked and built on. Free
 *   saved      the cleared rocks (by their actor's name) and the work done on others
 *              (UVLSaveGame::RocksCleared, RockWork; VLSave.*)
 * No map has rocks as instances of one component (the forest's instanced kinds are trees and plants); the first scan
 * counts any, so a map that has them is noticed.
 * Console: vl.Rocks (how many, cleared, at work), vl.Rocks clear | order (the rock nearest the played unit).
 */
UCLASS()
class SOVEREIGNREALMS_API UVLRocks : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLRocks* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Tick(float DeltaSeconds) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UVLRocks, STATGROUP_Tickables); }
	virtual void Deinitialize() override;

	static constexpr float ClearSeconds = 10.f;      // with one Builder at it

	/** A loose rock or boulder that Builders can clear (a static mesh actor of an SM_Rock_ mesh, still standing). */
	static bool IsRock(const AActor* Actor);
	/** The rock at a world point (the pointer's hit on it, or the ground just beside it), or null. */
	AActor* RockAt(const FVector& Point, float Slack = 60.f);
	/** A standing rock by its actor's name (a saved game's queued "clear it"), or null. */
	AActor* FindRock(const FString& Name);
	/** The closest point of the rock's footprint to From, on the ground plane (and the distance to it). */
	static float DistanceTo(const AActor* Rock, const FVector& From, FVector* OutPoint = nullptr);
	/** The Builders among Units go and clear it (bQueue: on the end of their queues). True if any was sent. */
	bool OrderClear(const TArray<AVLKing*>& Units, AActor* Rock, bool bQueue = false);
	/** A Builder at the rock gives it a frame of work (UVLBuilderWork); true when that cleared it. */
	bool AddWork(AActor* Rock, const AVLKing* Builder, float Dt);
	/** Seconds of one Builder's work done on it, of ClearSeconds. */
	float WorkOn(const AActor* Rock) const;
	/** Takes it away now: the dust, the sound, the path grid. */
	void Clear(AActor* Rock, bool bQuiet = false);

	// ---- saved games
	void SaveTo(TArray<FString>& OutCleared, TArray<FString>& OutWorkNames, TArray<float>& OutWork) const;
	/** The saved state on a fresh map: the cleared rocks go (silently; their ground added to OutChanged for the grid). */
	void RestoreFrom(const TArray<FString>& Cleared, const TArray<FString>& WorkNames, const TArray<float>& Work, TArray<FBox2D>& OutChanged);

	void LogStatus() const;

private:
	void Scan();
	FBox RockBox(const AActor* Rock) const;
	bool bScanned = false;
	TArray<TWeakObjectPtr<AActor>> Rocks;
	TArray<FString> Cleared;
	struct FWork
	{
		float Done = 0.f;
		uint64 Frame = 0;           // the frame its Builders last worked it, and how many did then (VLBuild::PerBuilding)
		int32 InFrame = 0;
		FVector BaseScale = FVector::OneVector;
		FVector BaseLocation = FVector::ZeroVector;
		float NextDust = 0.f;
	};
	TMap<TWeakObjectPtr<AActor>, FWork> Work;
	void ShowWork(AActor* Rock, FWork& W);
	void Puff(const FBox& Box, int32 Count, float Scale);

	UPROPERTY(Transient)
	TObjectPtr<AActor> DustActor;
	UPROPERTY(Transient)
	TObjectPtr<UVLFootDust> Dust;
	float DustUntil = 0.f;
};
