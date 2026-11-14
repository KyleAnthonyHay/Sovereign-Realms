// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "SRUserSettings.generated.h"

/**
 * The player's own options (the Settings screen): volumes, interface scale, camera habits, last difficulty.
 *
 * The game reads these values from USRFeelSettings like every other tunable; this object is only their per-user
 * store. It lives in the user's GameUserSettings.ini (Saved/Config/...), not in the project's DefaultGame.ini, so
 * it is writable in a packaged build and never dirties the project's tuning. Apply() copies the stored values onto
 * the feel settings at start-up; CaptureAndSave() copies them back and writes the file.
 */
UCLASS(Config = GameUserSettings)
class SOVEREIGNREALMS_API USRUserSettings : public UObject
{
	GENERATED_BODY()

public:
	static USRUserSettings* Get() { return GetMutableDefault<USRUserSettings>(); }

	/** Pushes the stored options onto USRFeelSettings (nothing happens until the player has saved once). */
	void Apply() const;
	/** Reads the current options back from USRFeelSettings and writes them to disk. */
	void CaptureAndSave();

	/** False until the first save: until then the project's defaults stand. */
	UPROPERTY(Config) bool bHasSaved = false;
	UPROPERTY(Config) float MasterVolume = 0.9f;
	UPROPERTY(Config) float EffectsVolume = 0.85f;
	UPROPERTY(Config) float UIVolume = 0.7f;
	UPROPERTY(Config) float AmbientVolume = 0.45f;
	UPROPERTY(Config) float MusicVolume = 0.35f;
	UPROPERTY(Config) float HUDScale = 1.f;
	UPROPERTY(Config) bool bEdgePan = true;
	UPROPERTY(Config) bool bWASDPansCamera = true;
	UPROPERTY(Config) int32 AIDifficulty = 1;
	/** The platoon panel folded away. */
	UPROPERTY(Config) bool bPlatoonsCollapsed = false;
};
