// ================================================================================================================
// DEPRECATED: superseded by VoxelLab (VoxelLab/Source/VoxelLab). This module is the first draft of Sovereign Realms and
// is no longer developed. Its game logic was reimplemented there (VLBattle, VLEnemyAI, VLCommand, VLHUD, the combat
// components); the Builder, Scout, Medic, Catapult, Horseman, construction, fog of war and saves remain only here.
// See README.md at the repository root. Kept so the old project still builds; do not delete.
// ================================================================================================================
// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "SRGameFlowSubsystem.generated.h"

/** One saved game, for the save / load list. */
struct FSRSaveInfo
{
	FString Slot;
	FDateTime SavedAt;
	/** "The Riverlands  ·  14 Nov 22:31  ·  12:05 into the battle  ·  Normal". */
	FString Line;
	bool bAuto = false;
	/** From before the heightfield maps (USRSaveGame::IsFromOldMap): listed, deletable, never loaded. */
	bool bOldMap = false;
};

/** Where the game is. The HUD draws a different interface for each; the controller takes world input only in Playing. */
enum class ESRGameState : uint8
{
	MainMenu,   // title screen over the live (but idle) realm; the camera drifts
	Playing,
	Paused,     // simulation held still, pause menu up
	Ended       // castle fallen: victory / defeat screen (the world keeps moving behind it)
};

/**
 * The game's state machine: main menu -> match -> pause / end -> match or main menu.
 *
 *   EnterMainMenu()   fresh battlefield, simulation paused, camera drift
 *   StartMatch(d, m)  set the difficulty (0 easy, 1 normal, 2 hard; -1 keeps it), reset the battle, focus the castle;
 *                     on another map (m: an id in USRFeelSettings::Maps) it travels to that level first
 *   SetPaused(b)      Playing <-> Paused
 * There is one level per map. A match on another map (a new one, or a saved game from it) opens that level with what
 * to do in the URL (?SRStart=1?SRDifficulty=d, or ?SRLoad=slot); ASRGameMode::StartPlay reads it on arrival and goes
 * straight into the match. This subsystem belongs to the world, so a fresh one runs the new level.
 * "Paused" is USRBattleSubsystem::SetSimPaused, not a world pause: actors, input, sounds, the interface and the
 * debug command inbox (Saved/SRCommands.txt) keep running, so the menus stay responsive and scripted tests can
 * still drive the game. Console: sr.StartMatch [difficulty] [map], sr.Menu <main|play>, sr.Pause 0|1, sr.Map.
 */
UCLASS()
class SOVEREIGNREALMS_API USRGameFlowSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static USRGameFlowSubsystem* Get(const UObject* WorldContext);

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	ESRGameState GetState() const { return State; }
	/** Anything but Playing: the interface owns the mouse and keyboard. */
	bool IsModal() const { return State != ESRGameState::Playing; }
	/** Real seconds since the state last changed (menu transitions). */
	float GetStateTime() const;

	void EnterMainMenu();
	/** Map: an id in USRFeelSettings::Maps; none, or the map being played, starts the match here. Another one opens
	 * its level, and the match starts there (nothing starts if that map is unknown or its level is missing). */
	void StartMatch(int32 Difficulty = -1, FName Map = NAME_None, bool bSandbox = false);
	/** Sandbox (testing): both kingdoms built up with every building, armies of every kind on both sides, plenty of
	 * gold and food, and an enemy commander that never attacks or builds. */
	bool IsSandbox() const { return bSandboxMatch; }
	void SetupSandbox();
	void SetPaused(bool bPaused);

	// ---- maps ----
	/** The map this level is (its ASRMapInfo's id; DefaultMapId for a level without one). */
	FName GetCurrentMapId() const;
	static FName DefaultMapId() { return TEXT("two"); }
	/** Can a match be started on this map: it is in the list and its level is in the game? */
	bool IsMapAvailable(FName Map) const;
	/** "The Riverlands" for a map id (the list's name in title case; the id itself if it is not in the list). */
	static FString MapTitle(FName Map);
	/** On its way to another level (the travel happens at the end of the frame): nothing more should be started here. */
	bool IsTravelling() const { return bTravelling; }
	/** The URL options that carry a match to another level (read by ASRGameMode::StartPlay). */
	static const TCHAR* StartOption() { return TEXT("SRStart"); }
	static const TCHAR* DifficultyOption() { return TEXT("SRDifficulty"); }
	static const TCHAR* SandboxOption() { return TEXT("SRSandbox"); }
	static const TCHAR* LoadOption() { return TEXT("SRLoad"); }

	// ---- saved games ----
	/** Slots: the player's save (pause menu) and the autosave (every AutosaveInterval while playing). */
	static const TCHAR* QuickSlot() { return TEXT("SR_Save"); }
	static const TCHAR* AutoSlot() { return TEXT("SR_Autosave"); }
	bool SaveMatch(const FString& Slot);
	/** Puts a saved game back on the field. One from another map opens that map's level and is loaded there (true:
	 * it is on its way); bTravel false refuses instead. One from the old terraced map is refused, with a message. */
	bool LoadMatch(const FString& Slot, bool bTravel = true);
	bool HasSave(const FString& Slot) const;
	/** The newest saved game that can be loaded ("" if none). */
	FString LatestSlot() const;
	/** Every saved game (the player's saves and the autosave), newest first. */
	const TArray<FSRSaveInfo>& GetSaves() const;
	/** Saves the match into a new slot of its own; returns the slot ("" if it failed, or every slot is in use). */
	FString SaveNewMatch();
	/** The player keeps at most this many saved games of their own (the autosave is extra): a fourth must go over
	 * one of them. */
	static constexpr int32 MaxPlayerSaves = 3;
	int32 CountPlayerSaves() const;
	bool CanAddSave() const { return CountPlayerSaves() < MaxPlayerSaves; }
	/** The saved game this match belongs to: the one it was last saved into or loaded from ("" if none yet). */
	const FString& GetActiveSlot() const { return ActiveSlot; }
	/** Saves the match where it belongs: over its own saved game, else into a new slot while there is room. ""
	 * when neither can be done (every slot holds another game: the player has to choose one to overwrite). */
	FString SaveCurrentMatch();
	/** Is the match, as it stands, in a saved game (saved, autosaved or loaded, and not played on since)? */
	bool IsMatchSaved() const;
	/** Battle time played since the match was last saved or loaded (-1: it never was). bOutAuto: that save was the
	 * autosave, not one of the player's own. */
	float GetUnsavedTime(bool* bOutAuto = nullptr) const;
	bool DeleteSave(const FString& Slot);
	/** A slot this game made (the player's saves start with this; the autosave is AutoSlot()). */
	static const TCHAR* SavePrefix() { return TEXT("SR_Save"); }
	/** "The Riverlands · 14 Nov 22:31 · 12:05 into the battle · Normal" for the menus ("" if the slot is empty); a save
	 * from the old terraced map says so instead of naming a map. */
	FString DescribeSave(const FString& Slot) const;
	/** Last save / load message and when (real seconds), for the pause menu. */
	const FString& GetSaveMessage() const { return SaveMessage; }
	double GetSaveMessageTime() const { return SaveMessageTime; }

private:
	void SetState(ESRGameState NewState);
	/** Opens a map's level with Options in the URL. False (and a message) if the level is not in the game. */
	bool TravelTo(const struct FSRMapEntry& Entry, const FString& Options);

	bool bTravelling = false;
	mutable FName CurrentMapId;                 // found once (the level's map info does not change)
	mutable TMap<FName, bool> MapAvailable;     // is the map's level in the game (asked every frame by the New Game screen)

	ESRGameState State = ESRGameState::Playing;
	float AutosaveClock = 0.f;
	// what of this match is on disk: the battle clock at the player's last save (or load) and at the last autosave
	FString ActiveSlot;
	float LastSaveClock = -1.f;
	float LastAutoClock = -1.f;
	void ForgetSaves() { ActiveSlot.Reset(); LastSaveClock = LastAutoClock = -1.f; }
	FString SaveMessage;
	double SaveMessageTime = -100.0;
	// caches: the menus ask every frame, the answers only change when a game is saved
	TMap<FString, FString> SaveLines;
	mutable TArray<FSRSaveInfo> SavesCache;
	mutable bool bSavesValid = false;
	double StateChangedAt = 0.0;
	bool bSandboxMatch = false;
};
