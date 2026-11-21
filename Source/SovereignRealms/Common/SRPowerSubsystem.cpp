// Copyright Sovereign Realms.

#include "Common/SRPowerSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Battle/SRGameFlowSubsystem.h"
#include "SovereignRealms.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "Scalability.h"

namespace
{
	/** The lower of two caps, where 0 means "no limit". */
	int32 Tighter(int32 Cap, int32 Limit)
	{
		if (Limit <= 0) { return Cap; }
		return Cap <= 0 ? Limit : FMath::Min(Cap, Limit);
	}

	/** High: what the battery saver takes a group down to (it never raises one). */
	const int32 SaverQuality = 2;
}

USRPowerSubsystem* USRPowerSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USRPowerSubsystem>() : nullptr;
}

bool USRPowerSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId USRPowerSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(USRPowerSubsystem, STATGROUP_Tickables);
}

void USRPowerSubsystem::Deinitialize()
{
	// Leave the engine as it was found: in the editor these outlive the play session.
	ApplySaverQuality(false);
	if (AppliedCap >= 0 && GEngine)
	{
		GEngine->SetMaxFPS(CapBefore);
		if (UGameUserSettings* Settings = GEngine->GetGameUserSettings()) { Settings->SetFrameRateLimit(LimitBefore); }
		AppliedCap = -1;
	}
	Super::Deinitialize();
}

void USRPowerSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	// A benchmark run measures the game uncapped.
	if (!GEngine || FApp::IsBenchmarking()) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();

	// The platform keeps the power source up to date (unplugging mid-game is seen); asking is cheap but not free.
	const double Now = FPlatformTime::Seconds();
	if (Now >= NextBatteryCheck)
	{
		NextBatteryCheck = Now + 2.0;
		bOnBattery = FPlatformMisc::IsRunningOnBattery();
	}
	const bool bSaver = F.BatterySaver >= 2 || (F.BatterySaver == 1 && bOnBattery);
	if (bSaver != bSaverActive)
	{
		bSaverActive = bSaver;
		UE_LOG(LogSovereign, Log, TEXT("POWER: battery saver %s (%s power)"), bSaver ? TEXT("on") : TEXT("off"), bOnBattery ? TEXT("battery") : TEXT("mains"));
	}
	ApplySaverQuality(bSaver && F.bBatterySaverLowersQuality && !GIsEditor);

	int32 Cap = FMath::Max(F.FrameRateCap, 0);
	if (bSaver) { Cap = Tighter(Cap, F.BatterySaverFrameRateCap); }
	if (const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this); Flow && Flow->IsModal()) { Cap = Tighter(Cap, F.MenuFrameRateCap); }
	// The editor throttles itself in the background, and scripted tests drive a play session it does not have in front.
	if (!GIsEditor && !FApp::HasFocus()) { Cap = Tighter(Cap, F.BackgroundFrameRateCap); }
	if (Cap != AppliedCap) { ApplyCap(Cap); }
}

void USRPowerSubsystem::ApplyCap(int32 Cap)
{
	UGameUserSettings* Settings = GEngine->GetGameUserSettings();
	if (AppliedCap < 0)
	{
		CapBefore = GEngine->GetMaxFPS();
		LimitBefore = Settings ? Settings->GetFrameRateLimit() : 0.f;
	}
	AppliedCap = Cap;
	GEngine->SetMaxFPS(float(Cap));
	// The engine's own user settings carry a frame limit too (0 unless set) and would put it back whenever they are
	// re-applied: keep the two in step. Not saved; the player's choice lives in USRUserSettings.
	if (Settings) { Settings->SetFrameRateLimit(float(Cap)); }
	UE_LOG(LogSovereign, Log, TEXT("POWER: frame-rate cap %s"), Cap > 0 ? *FString::FromInt(Cap) : TEXT("off"));
}

void USRPowerSubsystem::ApplySaverQuality(bool bLower)
{
	if (bLower == bQualityLowered) { return; }
	bQualityLowered = bLower;
	Scalability::FQualityLevels Levels = Scalability::GetQualityLevels();
	if (bLower)
	{
		SavedGlobalIllumination = Levels.GlobalIlluminationQuality;
		SavedReflection = Levels.ReflectionQuality;
		SavedShadow = Levels.ShadowQuality;
		SavedAntiAliasing = Levels.AntiAliasingQuality;
		Levels.SetGlobalIlluminationQuality(FMath::Min(SavedGlobalIllumination, SaverQuality));
		Levels.SetReflectionQuality(FMath::Min(SavedReflection, SaverQuality));
		Levels.SetShadowQuality(FMath::Min(SavedShadow, SaverQuality));
		Levels.SetAntiAliasingQuality(FMath::Min(SavedAntiAliasing, SaverQuality));
	}
	else
	{
		Levels.SetGlobalIlluminationQuality(SavedGlobalIllumination);
		Levels.SetReflectionQuality(SavedReflection);
		Levels.SetShadowQuality(SavedShadow);
		Levels.SetAntiAliasingQuality(SavedAntiAliasing);
	}
	Scalability::SetQualityLevels(Levels);
	UE_LOG(LogSovereign, Log, TEXT("POWER: lighting, reflections, shadows and anti-aliasing %s"), bLower ? TEXT("lowered to High") : TEXT("restored"));
}
