// Copyright Sovereign Realms.

#include "Common/SRUserSettings.h"
#include "Common/SRFeelSettings.h"

void USRUserSettings::Apply() const
{
	if (!bHasSaved) { return; }
	USRFeelSettings* F = GetMutableDefault<USRFeelSettings>();
	F->MasterVolume = FMath::Clamp(MasterVolume, 0.f, 1.f);
	F->EffectsVolume = FMath::Clamp(EffectsVolume, 0.f, 1.f);
	F->UIVolume = FMath::Clamp(UIVolume, 0.f, 1.f);
	F->AmbientVolume = FMath::Clamp(AmbientVolume, 0.f, 1.f);
	F->MusicVolume = FMath::Clamp(MusicVolume, 0.f, 1.f);
	F->HUDScale = FMath::Clamp(HUDScale, 0.8f, 1.4f);
	F->bEdgePan = bEdgePan;
	F->bWASDPansCamera = bWASDPansCamera;
	F->AIDifficulty = FMath::Clamp(AIDifficulty, 0, 2);
	F->FrameRateCap = FMath::Clamp(FrameRateCap, 0, 240);
	F->BatterySaver = FMath::Clamp(BatterySaver, 0, 2);
	F->bFogOfWar = bFogOfWar;
	F->bTrackpadScrollZooms = bTrackpadScrollZooms;
	F->CameraAngle = FMath::Clamp(CameraAngle, 0, 2);
}

void USRUserSettings::CaptureAndSave()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	bHasSaved = true;
	MasterVolume = F.MasterVolume;
	EffectsVolume = F.EffectsVolume;
	UIVolume = F.UIVolume;
	AmbientVolume = F.AmbientVolume;
	MusicVolume = F.MusicVolume;
	HUDScale = F.HUDScale;
	bEdgePan = F.bEdgePan;
	bWASDPansCamera = F.bWASDPansCamera;
	AIDifficulty = F.AIDifficulty;
	FrameRateCap = F.FrameRateCap;
	BatterySaver = F.BatterySaver;
	bFogOfWar = F.bFogOfWar;
	bTrackpadScrollZooms = F.bTrackpadScrollZooms;
	CameraAngle = F.CameraAngle;
	SaveConfig();
}
