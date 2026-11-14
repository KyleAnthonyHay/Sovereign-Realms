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

private:
	void SetState(ESRGameState NewState);

	ESRGameState State = ESRGameState::Playing;
	double StateChangedAt = 0.0;
};
