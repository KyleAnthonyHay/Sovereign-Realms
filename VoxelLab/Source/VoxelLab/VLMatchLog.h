#pragma once

#include "CoreMinimal.h"

class UVLBattle;
class AActor;

/**
 * The balance log of a match (vl.MatchLog 1, or ?MatchLog=1 on the map's URL; on by itself with ?AIvsAI): every
 * SampleEvery seconds of the match's clock both sides' gold and food (in stock, earned, lost to full stores, spent),
 * income, troops by kind (alive, trained, lost), buildings by kind, the commander's posture and its attacks; and as
 * they happen (looked at every second) every site laid, building finished, level raised, mine claimed, building lost,
 * attack and raid sent and come back. When the match ends (a castle falls, or vl.MatchLog.MaxMinutes runs out: a
 * draw), it is written to Saved/Balance/: <id>.json (everything), <id>_series.csv (the samples, a row per side) and a
 * line in matches.csv (the result). vl.MatchLog.Quit 1 then quits the game (a -game run only, never the editor).
 * The runner is Tools/aivsai.py.
 */
struct FVLMatchLog
{
	static constexpr float SampleEvery = 10.f;
	/** vl.MatchLog is on. */
	static bool Wanted();
	/** A free tag for the files' names (?Tag=... on the URL). */
	static FString Tag;

	void Tick(UVLBattle* Battle, float Dt);
	/** Writes the files now (the match's end, the time limit, or vl.MatchLog write). bDraw: the time ran out. */
	void Finish(UVLBattle* Battle, const FString& Reason);
	bool IsFinished() const { return bFinished; }

private:
	struct FSeen
	{
		int32 Team = -1;
		int32 Level = 1;
		bool bSite = false;
		bool bDead = false;
		FString Name;
		uint8 Kind = 0;
	};
	struct FOut
	{
		int32 Team = -1;
		bool bRaid = false;
		float Start = 0.f;
		int32 Size = 0;
		FString Target;
	};
	void Begin(UVLBattle* Battle);
	void Sample(UVLBattle* Battle);
	void Watch(UVLBattle* Battle);
	void Event(int32 Team, const TCHAR* Type, const FString& What, const FString& Detail = FString());

	bool bBegun = false;
	bool bFinished = false;
	float NextSample = 0.f;
	float NextWatch = 0.f;
	FString Id, MapName;
	int32 Difficulty[2] = { -1, -1 };
	bool bAI[2] = { false, false };
	TMap<TWeakObjectPtr<AActor>, FSeen> Buildings;
	TMap<uint64, FOut> Out;             // (team << 32 | squad id): bodies out on an attack or a raid
	TArray<FString> SeriesRows;         // CSV rows
	TArray<FString> SampleJson;         // one object per sample
	TArray<FString> EventJson;
	float Clock = 0.f;
	int32 Attacks[2] = { 0, 0 }, Raids[2] = { 0, 0 };
	int32 FirstAttackAt[2] = { -1, -1 };
};

/**
 * Duels for the balance of the troops (vl.Duel; ?Duels=1 runs the standard set and quits): two bodies of troops
 * spawned 36 m apart on open ground of the map (the commanders off), left to fight it out by themselves; the result
 * logged ("duel: ...") and appended to Saved/Balance/duels.csv: who won, in how long, what was left (troops, health).
 * Each duel is fought twice, the sides swapped. Ticked by UVLBattle.
 */
struct FVLDuels
{
	static void Tick(UVLBattle* Battle, float Dt);
	/** Swordsmen and archers of each side; Repeats with the sides swapped each time; Seconds at most. */
	static void Queue(int32 S0, int32 A0, int32 S1, int32 A1, int32 Repeats = 2, float Seconds = 120.f);
	/** The standard set: equal food for each side, pure and mixed bodies (README: The battle > Balance). */
	static void QueueStandard();
	/** Swordsmen and archers of team 0 against a watch tower of team 1 at Level (its own archers on it), Repeats times. */
	static void QueueTower(int32 Level, int32 S0, int32 A0, int32 Repeats = 2, float Seconds = 120.f);
	static void QuitWhenDone() { bQuit = true; }
	static FVector Where;               // the middle of the ground they fight on (0: the map's middle)
private:
	static bool bQuit;
};
