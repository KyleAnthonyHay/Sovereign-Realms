// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "SRGameFlowSubsystem.generated.h"

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
 *   StartMatch(d)     set the difficulty (0 easy, 1 normal, 2 hard; -1 keeps it), reset the battle, focus the castle
 *   SetPaused(b)      Playing <-> Paused
 * "Paused" is USRBattleSubsystem::SetSimPaused, not a world pause: actors, input, sounds, the interface and the
 * debug command inbox (Saved/SRCommands.txt) keep running, so the menus stay responsive and scripted tests can
 * still drive the game. Console: sr.StartMatch [difficulty], sr.Menu <main|play>, sr.Pause 0|1.
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
	void StartMatch(int32 Difficulty = -1);
	void SetPaused(bool bPaused);

	// ---- saved games ----
	/** Slots: the player's save (pause menu) and the autosave (every AutosaveInterval while playing). */
	static const TCHAR* QuickSlot() { return TEXT("SR_Save"); }
	static const TCHAR* AutoSlot() { return TEXT("SR_Autosave"); }
	bool SaveMatch(const FString& Slot);
	bool LoadMatch(const FString& Slot);
	bool HasSave(const FString& Slot) const;
	/** The newer of the two slots that exist ("" if none). */
	FString LatestSlot() const;
	/** "Saved 14:32 · 12:05 into the battle · Normal" for the menus ("" if the slot is empty). */
	FString DescribeSave(const FString& Slot) const;
	/** Last save / load message and when (real seconds), for the pause menu. */
	const FString& GetSaveMessage() const { return SaveMessage; }
	double GetSaveMessageTime() const { return SaveMessageTime; }

private:
	void SetState(ESRGameState NewState);

	ESRGameState State = ESRGameState::Playing;
	float AutosaveClock = 0.f;
	FString SaveMessage;
	double SaveMessageTime = -100.0;
	// caches: the menus ask every frame, the answers only change when a game is saved
	TMap<FString, FString> SaveLines;
	mutable FString LatestCache;
	mutable bool bLatestValid = false;
	double StateChangedAt = 0.0;
};
