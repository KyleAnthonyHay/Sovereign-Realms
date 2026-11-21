// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "SRPowerSubsystem.generated.h"

/**
 * Keeps the game from drawing more than it needs to (Sovereign Feel > Performance).
 *
 * The scene is expensive per frame (Lumen, virtual shadow maps, volumetric fog, depth of field) and nothing in the
 * engine limits how often it is drawn, so this sets the frame-rate cap (t.MaxFPS) to the tightest of:
 *   the player's cap (Settings screen)        FrameRateCap, 60 by default
 *   the battery saver's, while it is on       BatterySaverFrameRateCap, 30
 *   the menus' (main menu, pause, result)     MenuFrameRateCap, 30
 *   the background's (not the front window)   BackgroundFrameRateCap, 10; not inside the editor
 * The battery saver (off / on battery power / always) also takes four quality groups from Epic to High in a
 * standalone game; in the editor it only caps the frame rate, so the look being judged there never changes.
 * Everything it changed is put back when the world ends.
 */
UCLASS()
class SOVEREIGNREALMS_API USRPowerSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static USRPowerSubsystem* Get(const UObject* WorldContext);

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	bool IsOnBattery() const { return bOnBattery; }
	bool IsSaverActive() const { return bSaverActive; }

private:
	void ApplyCap(int32 Cap);
	void ApplySaverQuality(bool bLower);

	bool bOnBattery = false;
	bool bSaverActive = false;
	double NextBatteryCheck = 0.0;

	/** The cap this subsystem last set (-1: none yet) and the engine's values before it set any. */
	int32 AppliedCap = -1;
	float CapBefore = 0.f;
	float LimitBefore = 0.f;

	/** The quality groups the saver lowered, to put back. */
	bool bQualityLowered = false;
	int32 SavedGlobalIllumination = 3;
	int32 SavedReflection = 3;
	int32 SavedShadow = 3;
	int32 SavedAntiAliasing = 3;
};
