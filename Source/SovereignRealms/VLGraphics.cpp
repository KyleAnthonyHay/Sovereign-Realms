// The Graphics settings: see VLGraphics.h.

#include "VLGraphics.h"
#include "VLNet.h"
#include "SovereignRealms.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Engine/Engine.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/GameUserSettings.h"
#include "Widgets/SWindow.h"
#include "Engine/PointLight.h"
#include "Engine/DirectionalLight.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/LightComponent.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Kismet/KismetSystemLibrary.h"
#include "LegacyScreenPercentageDriver.h"
#include "Misc/ConfigCacheIni.h"
#include "UnrealClient.h"
#if PLATFORM_MAC
#import <Foundation/NSProcessInfo.h>
#endif

int32 UVLGraphics::Quality = UVLGraphics::High;
int32 UVLGraphics::RenderScale = 100;
int32 UVLGraphics::DynamicRes = UVLGraphics::DynOff;
int32 UVLGraphics::UserFrameCap = 60;
bool UVLGraphics::bMenuThrottle = false;
bool UVLGraphics::bLoaded = false;
bool UVLGraphics::bFarFog = false;

namespace
{
	// What each preset asks of the engine. High has no column: it is whatever the variable was when the game started
	// (the project's ini files and the engine's defaults), remembered the first time a preset is applied.
	struct FPresetVar
	{
		const TCHAR* Name;
		const TCHAR* Medium;      // (nullptr: as High)
		const TCHAR* Low;
		const TCHAR* Far = nullptr;      // on every preset while the camera is far above the ground (UpdateFarFog)
		IConsoleVariable* Var = nullptr;
		FString Start;
	};
	FPresetVar PresetVars[] = {
		// Lumen off on Low: the movable sky light lights the shade, with distance-field ambient occlusion (the project
		// generates mesh distance fields) and the screen-space one
		{ TEXT("r.DynamicGlobalIlluminationMethod"), nullptr, TEXT("0") },
		{ TEXT("r.ReflectionMethod"), nullptr, TEXT("0") },
		// the fog's froxel grid: 8 px / 128 slices as the game starts (the engine's Epic shadow quality)
		{ TEXT("r.VolumetricFog"), nullptr, TEXT("0") },
		{ TEXT("r.VolumetricFog.GridPixelSize"), TEXT("16"), TEXT("16"), TEXT("32") },
		{ TEXT("r.VolumetricFog.GridSizeZ"), TEXT("64"), TEXT("64"), TEXT("32") },
		// The sun's shadows stay virtual shadow maps on every preset (cascades would have to span the realm's 1,100 m
		// shadow distance); the lower presets draw them at a lower resolution with fewer filter rays.
		{ TEXT("r.Shadow.Virtual.ResolutionLodBiasDirectional"), TEXT("-0.5"), TEXT("0.5") },
		{ TEXT("r.Shadow.Virtual.ResolutionLodBiasDirectionalMoving"), TEXT("-0.5"), TEXT("0.5") },
		{ TEXT("r.Shadow.Virtual.SMRT.RayCountDirectional"), nullptr, TEXT("4") },
		{ TEXT("r.Shadow.Virtual.SMRT.SamplesPerRayDirectional"), nullptr, TEXT("2") },
		// half-res Lumen reflections and smaller VSM page pool on Medium/Low (High keeps startup values untouched)
		{ TEXT("r.Lumen.Reflections.DownsampleFactor"), TEXT("2"), TEXT("2") },
		{ TEXT("r.Shadow.Virtual.MaxPhysicalPages"), TEXT("1024"), TEXT("1024") },
		// the lamps' point lights fade out at MaxDrawDistance (Tools/ue/build_level.py lamps()): sooner on the lower presets
		{ TEXT("r.LightMaxDrawDistanceScale"), TEXT("0.75"), TEXT("0.5") },
	};
	bool bVarsCaptured = false;
	IConsoleVariable* ScreenPercentageVar = nullptr;
	IConsoleVariable* MaxFpsVar = nullptr;
	IConsoleVariable* DynOpModeVar = nullptr;
	IConsoleVariable* DynBudgetVar = nullptr;
	IConsoleVariable* DynMinVar = nullptr;
	IConsoleVariable* DynMaxVar = nullptr;
	FString ScreenPercentageStart;
	FString MaxFpsStart;
	FString DynOpModeStart;
	FString DynBudgetStart;
	FString DynMinStart;
	FString DynMaxStart;

	TAutoConsoleVariable<int32> CVarThermalGuard(TEXT("vl.Opt.ThermalGuard"), 1,
		TEXT("1: on macOS, cap frame rate (and engage dynamic resolution under Critical heat) when Low Power Mode or Serious/Critical thermal state is reported. 0: off."));
	TAutoConsoleVariable<int32> CVarIdleThrottle(TEXT("vl.Opt.IdleThrottle"), 1,
		TEXT("1: lower the frame-rate cap in menus (30 fps) and while unfocused (15 fps) to cut laptop heat and battery draw. 0: off."));

	const int32 Scales[] = { 100, 85, 75, 67, 60, 50 };
	const int32 PresetScale[UVLGraphics::NumQualities] = { 70, 85, 100 };

	TAutoConsoleVariable<int32> CVarFarFog(TEXT("vl.Opt.FarFog"), 1,
		TEXT("1: the volumetric fog's grid is coarse (32 px, 32 slices) while the camera is so far above the ground that nothing but air is inside the fog volume. 0: never."));

	void CaptureVars()
	{
		if (bVarsCaptured)
		{
			return;
		}
		bVarsCaptured = true;
		for (FPresetVar& V : PresetVars)
		{
			V.Var = IConsoleManager::Get().FindConsoleVariable(V.Name);
			if (V.Var)
			{
				V.Start = V.Var->GetString();
			}
			else
			{
				UE_LOG(LogSovereignRealms, Warning, TEXT("graphics: no console variable %s"), V.Name);
			}
		}
		auto Capture = [](const TCHAR* Name, IConsoleVariable*& OutVar, FString& OutStart)
		{
			OutVar = IConsoleManager::Get().FindConsoleVariable(Name);
			if (OutVar)
			{
				OutStart = OutVar->GetString();
			}
		};
		Capture(TEXT("r.ScreenPercentage"), ScreenPercentageVar, ScreenPercentageStart);
		Capture(TEXT("t.MaxFPS"), MaxFpsVar, MaxFpsStart);
		Capture(TEXT("r.DynamicRes.OperationMode"), DynOpModeVar, DynOpModeStart);
		Capture(TEXT("r.DynamicRes.FrameTimeBudget"), DynBudgetVar, DynBudgetStart);
		Capture(TEXT("r.DynamicRes.MinScreenPercentage"), DynMinVar, DynMinStart);
		Capture(TEXT("r.DynamicRes.MaxScreenPercentage"), DynMaxVar, DynMaxStart);
	}

	/** The share of the window's resolution the engine renders at by itself (r.ScreenPercentage 0), for a view of this size. */
	float AutoResolutionFraction(const FIntPoint& ViewSize)
	{
		static const IConsoleVariable* Default = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage.Default"));
		static const IConsoleVariable* Mode = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage.Default.Desktop.Mode"));
		FStaticResolutionFractionHeuristic Heuristic;
		Heuristic.Settings.Mode = EScreenPercentageMode(FMath::Clamp(Mode ? Mode->GetInt() : 1, 0, 2));
		Heuristic.Settings.GlobalResolutionFraction = FMath::Clamp((Default ? Default->GetFloat() : 100.f) / 100.f, 0.25f, 1.f);
		Heuristic.TotalDisplayedPixelCount = FMath::Max(1, ViewSize.X * ViewSize.Y);
		Heuristic.DPIScale = 1.f;
		return FMath::Clamp(Heuristic.ResolveResolutionFraction(), 0.25f, 1.f);
	}

	FAutoConsoleCommandWithWorldAndArgs CmdQuality(TEXT("vl.Gfx.Quality"), TEXT("0 Low, 1 Medium, 2 High (with the preset's render scale; not saved)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() > 0)
			{
				UVLGraphics::SetQuality(World, FCString::Atoi(*Args[0]));
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("graphics: quality %s, render scale %d%%"), UVLGraphics::QualityName(UVLGraphics::GetQuality()), UVLGraphics::GetRenderScale());
		}));

	// (for tuning Tools/ue/build_level.py's lamp_draw / lamp_fade in a running game; the maps carry the values)
	FAutoConsoleCommandWithWorldAndArgs CmdLamps(TEXT("vl.Gfx.Lamps"), TEXT("<max draw distance cm> <fade range cm>: on every point light actor of the level (0: no limit)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			int32 N = 0;
			float Draw = 0.f, Fade = 0.f;
			for (TActorIterator<APointLight> It(World); It; ++It)
			{
				if (ULightComponent* C = It->GetLightComponent())
				{
					if (Args.Num() > 0)
					{
						C->SetMaxDrawDistance(FCString::Atof(*Args[0]));
						C->SetMaxDistanceFadeRange(Args.Num() > 1 ? FCString::Atof(*Args[1]) : 0.f);
					}
					Draw = C->MaxDrawDistance;
					Fade = C->MaxDistanceFadeRange;
					++N;
				}
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("graphics: %d lamp(s), max draw distance %.0f, fade range %.0f"), N, Draw, Fade);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdScale(TEXT("vl.Gfx.Scale"), TEXT("render scale, per cent of the engine's automatic resolution (50..100; not saved)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() > 0)
			{
				UVLGraphics::SetRenderScale(World, FCString::Atoi(*Args[0]));
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("graphics: quality %s, render scale %d%%"), UVLGraphics::QualityName(UVLGraphics::GetQuality()), UVLGraphics::GetRenderScale());
		}));

	// ---- the sun, for recording the showreel at another hour (capture only: nothing calls it; the level's own sun is
	// the game's, and `vl.Sun reset` puts it back). The sky (SkyAtmosphere) and the sky light (real-time capture) follow it.
	struct FSunStart
	{
		TWeakObjectPtr<UDirectionalLightComponent> Light;
		FRotator Rotation;
		float Intensity = 0.f;
		bool bUseTemperature = false;
		float Temperature = 6500.f;
		EComponentMobility::Type Mobility = EComponentMobility::Movable;
	};
	FSunStart GSunStart;

	UDirectionalLightComponent* FindSun(UWorld* World)
	{
		UDirectionalLightComponent* Best = nullptr;
		for (TActorIterator<ADirectionalLight> It(World); It; ++It)
		{
			UDirectionalLightComponent* C = Cast<UDirectionalLightComponent>(It->GetLightComponent());
			if (C && (!Best || C->IsUsedAsAtmosphereSunLight()))
			{
				Best = C;
			}
		}
		return Best;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdSun(TEXT("vl.Sun"),
		TEXT("vl.Sun [Pitch Yaw [Intensity [Kelvin]]] | reset: turn the level's sun (pitch below 0: above the horizon; -8 a sunset), its strength (lux) and colour temperature, for recording; no arguments: log it; reset: as the level has it"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UDirectionalLightComponent* Sun = World ? FindSun(World) : nullptr;
			if (!Sun)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("vl.Sun: no directional light"));
				return;
			}
			if (GSunStart.Light.Get() != Sun)
			{
				GSunStart.Light = Sun;
				GSunStart.Rotation = Sun->GetComponentRotation();
				GSunStart.Intensity = Sun->Intensity;
				GSunStart.bUseTemperature = Sun->bUseTemperature;
				GSunStart.Temperature = Sun->Temperature;
				GSunStart.Mobility = Sun->Mobility;
			}
			if (Args.Num() >= 1 && Args[0].Equals(TEXT("reset"), ESearchCase::IgnoreCase))
			{
				Sun->SetWorldRotation(GSunStart.Rotation);
				Sun->SetIntensity(GSunStart.Intensity);
				Sun->SetUseTemperature(GSunStart.bUseTemperature);
				Sun->SetTemperature(GSunStart.Temperature);
			}
			else if (Args.Num() >= 2)
			{
				if (Sun->Mobility != EComponentMobility::Movable)
				{
					Sun->SetMobility(EComponentMobility::Movable);
				}
				Sun->SetWorldRotation(FRotator(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]), 0.f));
				if (Args.Num() >= 3)
				{
					Sun->SetIntensity(FCString::Atof(*Args[2]));
				}
				if (Args.Num() >= 4)
				{
					Sun->SetUseTemperature(true);
					Sun->SetTemperature(FCString::Atof(*Args[3]));
				}
			}
			const FRotator R = Sun->GetComponentRotation();
			UE_LOG(LogSovereignRealms, Log, TEXT("vl.Sun: pitch %.1f yaw %.1f, %.2f lux, %s %.0f K (the level's: pitch %.1f yaw %.1f, %.2f lux)"), R.Pitch, R.Yaw, Sun->Intensity,
				Sun->bUseTemperature ? TEXT("temperature") : TEXT("no temperature"), Sun->Temperature, GSunStart.Rotation.Pitch, GSunStart.Rotation.Yaw, GSunStart.Intensity);
		}));

	// ---- the see-through outline (M_Silhouette, a blendable of the level's post-process volume), for recording the
	// showreel without it (capture only; the HUD mutes it behind the title screen the same way). 0: its weight is put
	// to 0 on every volume, each frame (a new match's volume too); 1: the weights it had are given back.
	TAutoConsoleVariable<int32> CVarSilhouette(TEXT("vl.Opt.Silhouette"), 1,
		TEXT("1: the player's units show gold through walls and trees, as always. 0: no outline (capture only: Tools/showreel.py)"));
	struct FMutedOutline
	{
		TWeakObjectPtr<APostProcessVolume> Volume;
		int32 Index = 0;
		float Weight = 1.f;
	};
	TArray<FMutedOutline> GMutedOutlines;

	void UpdateSilhouetteMute(UWorld* World)
	{
		if (CVarSilhouette.GetValueOnGameThread() == 0)
		{
			for (TActorIterator<APostProcessVolume> It(World); It; ++It)
			{
				TArray<FWeightedBlendable>& Blends = It->Settings.WeightedBlendables.Array;
				for (int32 i = 0; i < Blends.Num(); ++i)
				{
					if (Blends[i].Object && Blends[i].Weight > 0.f && Blends[i].Object->GetName().Contains(TEXT("Silhouette")))
					{
						GMutedOutlines.Add({ *It, i, Blends[i].Weight });
						Blends[i].Weight = 0.f;
						UE_LOG(LogSovereignRealms, Log, TEXT("graphics: silhouette muted (vl.Opt.Silhouette 0)"));
					}
				}
			}
		}
		else if (GMutedOutlines.Num() > 0)
		{
			for (const FMutedOutline& M : GMutedOutlines)
			{
				if (APostProcessVolume* V = M.Volume.Get(); V && V->Settings.WeightedBlendables.Array.IsValidIndex(M.Index) && V->Settings.WeightedBlendables.Array[M.Index].Weight == 0.f)
				{
					V->Settings.WeightedBlendables.Array[M.Index].Weight = M.Weight;
				}
			}
			GMutedOutlines.Reset();
		}
	}

	FAutoConsoleCommandWithWorldAndArgs CmdDynRes(TEXT("vl.Gfx.DynRes"), TEXT("0 Off, 1 Target 60 fps, 2 Target 40 fps, 3 Target 30 fps (not saved)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() > 0)
			{
				UVLGraphics::SetDynamicRes(World, FCString::Atoi(*Args[0]));
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("graphics: dynamic resolution %s"), UVLGraphics::DynamicResName(UVLGraphics::GetDynamicRes()));
		}));
}

// ------------------------------------------------------------------------------------------------ the settings

void UVLGraphics::LoadOnce()
{
	if (bLoaded)
	{
		return;
	}
	bLoaded = true;
	if (GConfig)
	{
		GConfig->GetInt(TEXT("SovereignRealms.Video"), TEXT("Quality"), Quality, GGameUserSettingsIni);
		Quality = FMath::Clamp(Quality, 0, NumQualities - 1);
		RenderScale = PresetScale[Quality];
		GConfig->GetInt(TEXT("SovereignRealms.Video"), TEXT("RenderScale"), RenderScale, GGameUserSettingsIni);
		RenderScale = FMath::Clamp(RenderScale, 50, 100);
		GConfig->GetInt(TEXT("SovereignRealms.Video"), TEXT("DynamicRes"), DynamicRes, GGameUserSettingsIni);
		DynamicRes = FMath::Clamp(DynamicRes, 0, NumDynRes - 1);
	}
}

void UVLGraphics::Save()
{
	LoadOnce();
	if (GConfig)
	{
		GConfig->SetInt(TEXT("SovereignRealms.Video"), TEXT("Quality"), Quality, GGameUserSettingsIni);
		GConfig->SetInt(TEXT("SovereignRealms.Video"), TEXT("RenderScale"), RenderScale, GGameUserSettingsIni);
		GConfig->SetInt(TEXT("SovereignRealms.Video"), TEXT("DynamicRes"), DynamicRes, GGameUserSettingsIni);
	}
}

const TCHAR* UVLGraphics::QualityName(int32 InQuality)
{
	static const TCHAR* Names[NumQualities] = { TEXT("Low"), TEXT("Medium"), TEXT("High") };
	return Names[FMath::Clamp(InQuality, 0, NumQualities - 1)];
}

void UVLGraphics::SetQuality(UWorld* World, int32 InQuality)
{
	LoadOnce();
	Quality = FMath::Clamp(InQuality, 0, NumQualities - 1);
	RenderScale = PresetScale[Quality];
	Apply(World);
}

void UVLGraphics::SetRenderScale(UWorld* World, int32 Percent)
{
	LoadOnce();
	RenderScale = FMath::Clamp(Percent, 50, 100);
	Apply(World);
}

void UVLGraphics::CycleRenderScale(UWorld* World)
{
	LoadOnce();
	int32 Next = 0;
	for (int32 i = 0; i < UE_ARRAY_COUNT(Scales); ++i)
	{
		if (Scales[i] < RenderScale)
		{
			Next = i;
			break;
		}
	}
	SetRenderScale(World, Scales[Next]);
}

const TCHAR* UVLGraphics::DynamicResName(int32 Mode)
{
	static const TCHAR* Names[NumDynRes] = { TEXT("Off"), TEXT("Target 60 fps"), TEXT("Target 40 fps"), TEXT("Target 30 fps") };
	return Names[FMath::Clamp(Mode, 0, NumDynRes - 1)];
}

void UVLGraphics::SetDynamicRes(UWorld* World, int32 Mode)
{
	LoadOnce();
	DynamicRes = FMath::Clamp(Mode, 0, NumDynRes - 1);
	Apply(World);
}

void UVLGraphics::CycleDynamicRes(UWorld* World)
{
	LoadOnce();
	SetDynamicRes(World, (DynamicRes + 1) % NumDynRes);
}

void UVLGraphics::SetUserFrameCap(int32 InFps)
{
	UserFrameCap = FMath::Max(InFps, 0);
}

void UVLGraphics::SetMenuThrottle(UWorld* World, bool bInMenu)
{
	if (bMenuThrottle != bInMenu)
	{
		bMenuThrottle = bInMenu;
		if (UVLGraphics* Self = World ? World->GetSubsystem<UVLGraphics>() : nullptr)
		{
			Self->UpdateThermalAndFrameCap(false);
		}
	}
}

void UVLGraphics::ApplyConsoleVariables()
{
	CaptureVars();
	for (FPresetVar& V : PresetVars)
	{
		if (!V.Var)
		{
			continue;
		}
		const TCHAR* Wanted = Quality == Low ? V.Low : (Quality == Medium ? V.Medium : nullptr);
		if (bFarFog && V.Far)
		{
			Wanted = V.Far;
		}
		const FString Value = Wanted ? FString(Wanted) : V.Start;
		if (V.Var->GetString() != Value)
		{
			// (by code: several of these come from the project's ini files, which outrank a game setting)
			V.Var->Set(*Value, ECVF_SetByCode);
		}
	}
}

void UVLGraphics::RestoreConsoleVariables()
{
	if (!bVarsCaptured)
	{
		return;
	}
	for (FPresetVar& V : PresetVars)
	{
		if (V.Var && V.Var->GetString() != V.Start)
		{
			V.Var->Set(*V.Start, ECVF_SetByCode);
		}
	}
	auto Restore = [](IConsoleVariable* Var, const FString& Start)
	{
		if (Var && Var->GetString() != Start)
		{
			Var->Set(*Start, ECVF_SetByCode);
		}
	};
	Restore(ScreenPercentageVar, ScreenPercentageStart);
	Restore(MaxFpsVar, MaxFpsStart);
	Restore(DynOpModeVar, DynOpModeStart);
	Restore(DynBudgetVar, DynBudgetStart);
	Restore(DynMinVar, DynMinStart);
	Restore(DynMaxVar, DynMaxStart);
}

void UVLGraphics::Apply(UWorld* World)
{
	LoadOnce();
	ApplyConsoleVariables();
	if (UVLGraphics* Self = World ? World->GetSubsystem<UVLGraphics>() : nullptr)
	{
		Self->ApplyToWorld();
	}
}

// ------------------------------------------------------------------------------------------------ the world

void UVLGraphics::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
#if PLATFORM_WINDOWS
	// VSync always on in the game on Windows: no tearing (user request 2026-11-23; there is no settings row for it).
	// Set every match start, so an install saved with it off is put right too.
	if (!GIsEditor && !IsVSync())
	{
		SetVSync(true);
	}
	else if (!GIsEditor)
	{
		if (IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(TEXT("r.VSync")))
		{
			Var->Set(1, ECVF_SetByGameSetting);
		}
	}
#endif
	Apply(&InWorld);
	UE_LOG(LogSovereignRealms, Log, TEXT("graphics: quality %s, render scale %d%%"), QualityName(Quality), RenderScale);
}

void UVLGraphics::Deinitialize()
{
#if WITH_EDITOR
	// a play session in the editor must not leave the editor on the Low preset
	if (GIsEditor)
	{
		RestoreConsoleVariables();
	}
#endif
	bFarFog = false;
	bMenuThrottle = false;
	KeepWindowState();          // (quitting, or another map: the window as it is now is kept)
	Super::Deinitialize();
}

void UVLGraphics::ApplyToWorld()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	if (!bLookFound)
	{
		bLookFound = true;
		for (TActorIterator<APostProcessVolume> It(World); It; ++It)
		{
			if (It->bUnbound && (It->Settings.bOverride_LumenFinalGatherQuality || It->Settings.bOverride_LumenSceneDetail))
			{
				Look = *It;
				bLookFinalGather = It->Settings.bOverride_LumenFinalGatherQuality;
				bLookSceneDetail = It->Settings.bOverride_LumenSceneDetail;
				LookFinalGather = It->Settings.LumenFinalGatherQuality;
				LookSceneDetail = It->Settings.LumenSceneDetail;
				break;
			}
		}
		for (TActorIterator<AExponentialHeightFog> It(World); It; ++It)
		{
			if (UExponentialHeightFogComponent* C = It->GetComponent())
			{
				Fog = C;
				bFogWasVolumetric = C->bEnableVolumetricFog;
				break;
			}
		}
	}
	// The level's post-process volume raises Lumen's final gather quality and scene detail (to 2.0), which no console
	// variable can lower again: the lower presets set them back to the engine's 1.0 on the volume itself.
	if (APostProcessVolume* V = Look.Get())
	{
		if (bLookFinalGather)
		{
			V->Settings.LumenFinalGatherQuality = Quality == High ? LookFinalGather : FMath::Min(LookFinalGather, 1.f);
		}
		if (bLookSceneDetail)
		{
			V->Settings.LumenSceneDetail = Quality == High ? LookSceneDetail : FMath::Min(LookSceneDetail, 1.f);
		}
	}
	UpdateScreenPercentage(true);
	UpdateThermalAndFrameCap(true);
}

void UVLGraphics::UpdateScreenPercentage(bool bForce)
{
	CaptureVars();
	if (!ScreenPercentageVar)
	{
		return;
	}
	FIntPoint ViewSize = LastViewSize;
	if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
	{
		ViewSize = GEngine->GameViewport->Viewport->GetSizeXY();
	}
	// Engage Dyn30 automatically only under Critical macOS thermal state when ThermalGuard is enabled.
	const bool bThermalDyn = !GIsEditor && CVarThermalGuard.GetValueOnGameThread() != 0 && ThermalLevel >= 3;
	const int32 EffectiveDyn = DynamicRes != DynOff ? DynamicRes : (bThermalDyn ? Dyn30 : DynOff);
	if (EffectiveDyn != DynOff && DynOpModeVar && DynBudgetVar && DynMinVar && DynMaxVar)
	{
		if (ViewSize.X <= 0 || ViewSize.Y <= 0)
		{
			return;
		}
		const float StartVal = FCString::Atof(*ScreenPercentageStart);
		const float Base = StartVal > 0.f ? StartVal / 100.f : AutoResolutionFraction(ViewSize);
		const float MaxPct = FMath::Clamp(FMath::RoundToFloat(Base * RenderScale * 10.f) / 10.f, 50.f, 100.f);
		const float MinPct = FMath::Min(50.f, MaxPct);
		static const float Budgets[NumDynRes] = { 0.f, 16.6f, 25.0f, 33.3f };
		const float Budget = Budgets[FMath::Clamp(EffectiveDyn, 1, NumDynRes - 1)];
		if (bForce || ViewSize != LastViewSize || EffectiveDyn != LastAppliedDynRes || !FMath::IsNearlyEqual(MaxPct, LastScreenPercentage, 0.01f))
		{
			LastViewSize = ViewSize;
			LastAppliedDynRes = EffectiveDyn;
			LastScreenPercentage = MaxPct;
			DynBudgetVar->Set(Budget, ECVF_SetByCode);
			DynMinVar->Set(MinPct, ECVF_SetByCode);
			DynMaxVar->Set(MaxPct, ECVF_SetByCode);
			DynOpModeVar->Set(2, ECVF_SetByCode);
			UE_LOG(LogSovereignRealms, Log, TEXT("graphics: dynamic resolution %s (budget %.1f ms, range %.1f%%..%.1f%%)"), DynamicResName(EffectiveDyn), Budget, MinPct, MaxPct);
		}
		return;
	}
	if (DynOpModeVar && LastAppliedDynRes != DynOff)
	{
		DynOpModeVar->Set(0, ECVF_SetByCode);
		LastAppliedDynRes = DynOff;
		bForce = true;
	}
	// 100 %: the engine's own choice (r.ScreenPercentage as the game started, 0: from the size of the window). Less:
	// that share of what the engine would have chosen, so the scale means the same on every display.
	float Wanted = FCString::Atof(*ScreenPercentageStart);
	if (RenderScale < 100)
	{
		if (ViewSize.X <= 0 || ViewSize.Y <= 0)
		{
			return;
		}
		const float Base = Wanted > 0.f ? Wanted / 100.f : AutoResolutionFraction(ViewSize);
		Wanted = FMath::Clamp(FMath::RoundToFloat(Base * RenderScale * 10.f) / 10.f, 25.f, 100.f);
	}
	if (bForce || ViewSize != LastViewSize || !FMath::IsNearlyEqual(Wanted, LastScreenPercentage, 0.01f))
	{
		LastViewSize = ViewSize;
		if (!FMath::IsNearlyEqual(Wanted, ScreenPercentageVar->GetFloat(), 0.01f))
		{
			ScreenPercentageVar->Set(Wanted, ECVF_SetByCode);
		}
		if (!FMath::IsNearlyEqual(Wanted, LastScreenPercentage, 0.01f))
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("graphics: r.ScreenPercentage %.1f (render scale %d%%, view %d x %d, where the engine's own choice is %.1f%%)"), Wanted, RenderScale,
				ViewSize.X, ViewSize.Y, ViewSize.X > 0 && ViewSize.Y > 0 ? AutoResolutionFraction(ViewSize) * 100.f : 0.f);
		}
		LastScreenPercentage = Wanted;
	}
}

void UVLGraphics::UpdateThermalAndFrameCap(bool bForce)
{
	CaptureVars();
#if PLATFORM_MAC
	if (!GIsEditor && CVarThermalGuard.GetValueOnGameThread() != 0)
	{
		@autoreleasepool
		{
			NSProcessInfo* Info = [NSProcessInfo processInfo];
			const int32 NewThermal = static_cast<int32>([Info thermalState]);
			const bool NewLowPower = [Info isLowPowerModeEnabled] ? true : false;
			if (NewThermal != ThermalLevel || NewLowPower != bLowPowerMode)
			{
				ThermalLevel = NewThermal;
				bLowPowerMode = NewLowPower;
				UE_LOG(LogSovereignRealms, Log, TEXT("graphics: macOS thermal=%d lowPower=%d"), ThermalLevel, bLowPowerMode ? 1 : 0);
				UpdateScreenPercentage(true);
			}
		}
	}
#endif
	if (!MaxFpsVar)
	{
		return;
	}
	int32 Cap = UserFrameCap;
	auto LimitTo = [&Cap](int32 Ceiling)
	{
		if (Ceiling > 0 && (Cap <= 0 || Ceiling < Cap))
		{
			Cap = Ceiling;
		}
	};
	if (!GIsEditor)
	{
		// (not in a multiplayer match: the other player's game depends on this one keeping its pace, focused or not,
		// and its menu does not pause anything)
		const UWorld* ThrottleWorld = GetWorld();
		if (CVarIdleThrottle.GetValueOnGameThread() != 0 && !VLNet::IsMultiplayer(ThrottleWorld))
		{
			if (!FPlatformApplicationMisc::IsThisApplicationForeground())
			{
				LimitTo(15);
			}
			else if (bMenuThrottle)
			{
				LimitTo(30);
			}
		}
		if (CVarThermalGuard.GetValueOnGameThread() != 0)
		{
			if (ThermalLevel >= 3)
			{
				LimitTo(30);
			}
			else if (ThermalLevel >= 2 || bLowPowerMode)
			{
				LimitTo(40);
			}
		}
	}
	if (bForce || Cap != LastEffectiveFrameCap)
	{
		LastEffectiveFrameCap = Cap;
		MaxFpsVar->Set(float(Cap), ECVF_SetByCode);
	}
}

void UVLGraphics::UpdateFarFog()
{
	UExponentialHeightFogComponent* C = Fog.Get();
	UWorld* World = GetWorld();
	if (!C || !bFogWasVolumetric || !World)
	{
		return;
	}
	bool bOff = false;
	const APlayerController* PC = World->GetFirstPlayerController();
	if (CVarFarFog.GetValueOnGameThread() != 0 && PC && PC->PlayerCameraManager)
	{
		// The fog volume is a froxel grid from the camera out to VolumetricFogDistance. Is the camera higher than that
		// (and a margin for the trees and roofs the traces can miss) above all the ground the volume could reach?
		const FVector Cam = PC->PlayerCameraManager->GetCameraLocation();
		const float Reach = C->VolumetricFogDistance;
		const float Margin = bFarFog ? 1500.f : 2500.f;             // (and stays coarse until 10 m lower: no flicker at the edge)
		float Top = -UE_BIG_NUMBER;
		bool bAny = false;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(VLFarFog), true);
		for (int32 i = 0; i < 17; ++i)
		{
			const float R = i == 0 ? 0.f : (i <= 8 ? Reach * 0.5f : Reach);
			const float A = i * (UE_PI / 4.f) + (i > 8 ? UE_PI / 8.f : 0.f);
			const FVector From(Cam.X + R * FMath::Cos(A), Cam.Y + R * FMath::Sin(A), Cam.Z);
			FHitResult Hit;
			if (World->LineTraceSingleByChannel(Hit, From, From - FVector(0.f, 0.f, 200000.f), ECC_Visibility, Params))
			{
				Top = FMath::Max(Top, float(Hit.ImpactPoint.Z));
				bAny = true;
			}
		}
		bOff = bAny && Cam.Z - Top > Reach + Margin;
	}
	if (bOff != bFarFog)
	{
		bFarFog = bOff;
		ApplyConsoleVariables();
		UE_LOG(LogSovereignRealms, Verbose, TEXT("graphics: fog grid %s"), bOff ? TEXT("coarse (far view)") : TEXT("as the preset"));
	}
}

void UVLGraphics::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	// the window: a change the Settings screen asked for (here, outside any draw), and an exclusive mode nobody confirmed
	ApplyPendingDisplay();
	UpdateScreenPercentage(false);
	if (UWorld* World = GetWorld(); World && World->IsGameWorld())
	{
		UpdateSilhouetteMute(World);
	}
	if (UWorld* World = GetWorld(); World && !World->IsPaused())
	{
		FogCheckIn -= DeltaTime;
		if (FogCheckIn <= 0.f)
		{
			FogCheckIn = 0.2f;
			UpdateFarFog();
		}
	}
	ThermalCheckIn -= DeltaTime;
	if (ThermalCheckIn <= 0.f)
	{
		ThermalCheckIn = 2.f;
		UpdateThermalAndFrameCap(false);
	}
	WindowCheckIn -= DeltaTime;
	if (WindowCheckIn <= 0.f)
	{
		WindowCheckIn = 1.f;
		KeepWindowState();
	}
}

// ------------------------------------------------------------------------------------------------ the window

namespace
{
	/** The game's window and what it shows now (packaged only). */
	bool GameWindow(EWindowMode::Type& OutMode, FIntPoint& OutSize)
	{
		if (GIsEditor || !GEngine || !GEngine->GameViewport || !GEngine->GameViewport->Viewport)
		{
			return false;
		}
		const TSharedPtr<SWindow> Window = GEngine->GameViewport->GetWindow();
		if (!Window.IsValid())
		{
			return false;
		}
		OutMode = Window->GetWindowMode();
		OutSize = GEngine->GameViewport->Viewport->GetSizeXY();
		return OutSize.X > 0 && OutSize.Y > 0;
	}

	// A change of the window waiting for the next Tick (see VLGraphics.h: never from inside the HUD's draw).
	struct FDisplayRequest
	{
		bool bPending = false;
		EWindowMode::Type Mode = EWindowMode::Windowed;
		FIntPoint Size = FIntPoint::ZeroValue;      // (0: none to set, as borderless full screen: the desktop's)
		bool bNeedsConfirm = false;
		bool bMaximize = false;                     // (Windows: a window out of full screen fills the screen, maximized)
	};
	// A maximize waiting for the window to be a window again (the mode change lands a frame or two later).
	bool bMaximizePending = false;
	int32 MaximizeTries = 0;
	FDisplayRequest DisplayRequest;
	// An exclusive full screen mode that the player has not confirmed yet, and what to go back to.
	const float DisplayConfirmTime = 15.f;
	bool bDisplayUnconfirmed = false;
	double DisplayConfirmUntil = 0.0;
	EWindowMode::Type DisplayBackMode = EWindowMode::Windowed;
	FIntPoint DisplayBackSize = FIntPoint::ZeroValue;

	EWindowMode::Type ToWindowMode(int32 Display)
	{
		return Display == UVLGraphics::DisplayExclusive ? EWindowMode::Fullscreen : (Display == UVLGraphics::DisplayBorderless ? EWindowMode::WindowedFullscreen : EWindowMode::Windowed);
	}
	int32 ToDisplay(EWindowMode::Type Mode)
	{
		return Mode == EWindowMode::Fullscreen ? UVLGraphics::DisplayExclusive : (Mode == EWindowMode::WindowedFullscreen ? UVLGraphics::DisplayBorderless : UVLGraphics::DisplayWindowed);
	}

	FIntPoint DesktopSize()
	{
		const UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
		FIntPoint Desk = S ? S->GetDesktopResolution() : FIntPoint::ZeroValue;
#if PLATFORM_WINDOWS
		// In exclusive full screen at a lower mode Windows reports that mode as the desktop: the desktop to go back
		// to (a window's sizes, borderless) is the display's largest mode.
		EWindowMode::Type Mode = EWindowMode::Windowed;
		FIntPoint Size;
		if (GameWindow(Mode, Size) && Mode == EWindowMode::Fullscreen)
		{
			TArray<FIntPoint> Modes;
			UKismetSystemLibrary::GetSupportedFullscreenResolutions(Modes);
			for (const FIntPoint& M : Modes)
			{
				if (M.X * M.Y > Desk.X * Desk.Y)
				{
					Desk = M;
				}
			}
		}
#endif
		return Desk;
	}

	/** The window to come back to from full screen: the one it was ([SovereignRealms.Video] WindowX / WindowY); none:
	 *  16:9, 85% of the desktop (on the Mac at most 1600 x 900, as ever). */
	FIntPoint WindowedSize()
	{
		FIntPoint Res(0, 0);
		if (GConfig)
		{
			GConfig->GetInt(TEXT("SovereignRealms.Video"), TEXT("WindowX"), Res.X, GGameUserSettingsIni);
			GConfig->GetInt(TEXT("SovereignRealms.Video"), TEXT("WindowY"), Res.Y, GGameUserSettingsIni);
		}
		const FIntPoint Desk = DesktopSize();
		if (Res.X < 640 || Res.Y < 360 || (Desk.X > 0 && Res.X >= Desk.X && Res.Y >= Desk.Y))
		{
#if PLATFORM_WINDOWS
			// (real pixels on Windows: 1600 x 900 is a small window on a 4K desktop)
			Res.X = FMath::Max(1280, FMath::RoundToInt(Desk.X * 0.85f));
			Res.Y = FMath::RoundToInt(Res.X * 9.f / 16.f);
			if (Desk.Y > 0 && Res.Y > Desk.Y * 0.85f)
			{
				Res.Y = FMath::RoundToInt(Desk.Y * 0.85f);
				Res.X = FMath::RoundToInt(Res.Y * 16.f / 9.f);
			}
#else
			Res.X = FMath::Min(1600, FMath::RoundToInt(Desk.X * 0.85f));
			Res.Y = FMath::RoundToInt(Res.X * 9.f / 16.f);
#endif
		}
		return Res;
	}

	bool SizeLess(const FIntPoint& A, const FIntPoint& B)
	{
		return A.X != B.X ? A.X < B.X : A.Y < B.Y;
	}

	/** The sizes the Resolution row steps through, smallest first. */
	void DisplaySizes(int32 Display, TArray<FIntPoint>& Out)
	{
		const FIntPoint Desk = DesktopSize();
		if (Display == UVLGraphics::DisplayExclusive)
		{
			// the display's own modes, as the RHI lists them
			TArray<FIntPoint> Modes;
			UKismetSystemLibrary::GetSupportedFullscreenResolutions(Modes);
			for (const FIntPoint& M : Modes)
			{
				if (M.X >= 1024 && M.Y >= 720)
				{
					Out.AddUnique(M);
				}
			}
			if (Out.Num() == 0 && Desk.X > 0)
			{
				Out.Add(Desk);
			}
		}
		else if (Display == UVLGraphics::DisplayWindowed)
		{
			// the usual sizes that fit on the desktop with the title bar (any other: drag the window's edge)
			static const FIntPoint Usual[] = { FIntPoint(1280, 720), FIntPoint(1600, 900), FIntPoint(1920, 1080), FIntPoint(1920, 1200), FIntPoint(2560, 1080),
				FIntPoint(2560, 1440), FIntPoint(2560, 1600), FIntPoint(3200, 1800), FIntPoint(3440, 1440), FIntPoint(3840, 2160), FIntPoint(5120, 1440), FIntPoint(5120, 2880) };
			for (const FIntPoint& Size : Usual)
			{
				if (Desk.X <= 0 || (Size.X <= Desk.X && Size.Y <= Desk.Y - 100))
				{
					Out.Add(Size);
				}
			}
			if (Out.Num() == 0)
			{
				Out.Add(FIntPoint(1280, 720));
			}
		}
		Out.Sort(&SizeLess);
	}
}

bool UVLGraphics::IsFullscreen()
{
	return GetDisplayMode() != DisplayWindowed;
}

int32 UVLGraphics::GetDisplayMode()
{
	if (DisplayRequest.bPending)
	{
		return ToDisplay(DisplayRequest.Mode);
	}
	EWindowMode::Type Mode = EWindowMode::Windowed;
	FIntPoint Size;
	if (GameWindow(Mode, Size))
	{
		return ToDisplay(Mode);
	}
	const UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
	return S ? ToDisplay(S->GetFullscreenMode()) : int32(DisplayWindowed);
}

const TCHAR* UVLGraphics::DisplayModeName(int32 Mode)
{
	return Mode == DisplayExclusive ? TEXT("Full screen") : (Mode == DisplayBorderless ? TEXT("Borderless") : TEXT("Windowed"));
}

FIntPoint UVLGraphics::GetResolution()
{
	if (DisplayRequest.bPending && DisplayRequest.Size.X > 0)
	{
		return DisplayRequest.Size;
	}
	EWindowMode::Type Mode = EWindowMode::Windowed;
	FIntPoint Size;
	if (!DisplayRequest.bPending && GameWindow(Mode, Size))
	{
		return Size;
	}
	return DesktopSize();
}

bool UVLGraphics::CanPickResolution()
{
	return CanChangeWindow() && GetDisplayMode() != DisplayBorderless;
}

void UVLGraphics::SetDisplay(int32 Mode, FIntPoint Resolution)
{
	if (!CanChangeWindow() || !GEngine || !GEngine->GetGameUserSettings())
	{
		return;
	}
	if (!bDisplayUnconfirmed && !DisplayRequest.bPending)
	{
		KeepWindowState();          // (the window's own size first, to come back to)
		// what an unconfirmed mode goes back to: the display as it is now
		EWindowMode::Type NowMode = EWindowMode::Windowed;
		FIntPoint NowSize = FIntPoint::ZeroValue;
		const bool bWindow = GameWindow(NowMode, NowSize);
		DisplayBackMode = bWindow ? NowMode : EWindowMode::WindowedFullscreen;
		DisplayBackSize = bWindow && NowMode != EWindowMode::WindowedFullscreen ? NowSize : FIntPoint::ZeroValue;
	}
	const bool bWasFullscreen = IsFullscreen();
	DisplayRequest.bPending = true;
	DisplayRequest.Mode = ToWindowMode(Mode);
	DisplayRequest.Size = Resolution;
	DisplayRequest.bMaximize = false;
	if (DisplayRequest.Mode == EWindowMode::WindowedFullscreen)
	{
		DisplayRequest.Size = FIntPoint::ZeroValue;
	}
	else if (Resolution.X <= 0 || Resolution.Y <= 0)
	{
#if PLATFORM_WINDOWS
		// No size asked for: the screen's own. Full screen at the display's native mode; a window out of full screen
		// keeps the screen's resolution (maximized: the whole screen less the title bar and the taskbar), never an old
		// remembered size. A size picked in the Resolution row is taken as it is.
		if (DisplayRequest.Mode == EWindowMode::Windowed && bWasFullscreen)
		{
			DisplayRequest.Size = DesktopSize();
			DisplayRequest.bMaximize = true;
		}
		else
		{
			DisplayRequest.Size = DisplayRequest.Mode == EWindowMode::Windowed ? WindowedSize() : DesktopSize();
		}
#else
		DisplayRequest.Size = DisplayRequest.Mode == EWindowMode::Windowed ? WindowedSize() : DesktopSize();
#endif
	}
	// Applied at once, no "keep this mode?" question (user request 2026-11-23): the exclusive modes offered are the
	// display's own (GetSupportedFullscreenResolutions), so none leaves the screen dark.
	DisplayRequest.bNeedsConfirm = false;
}

void UVLGraphics::ApplyPendingDisplay()
{
	UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
	if (bDisplayUnconfirmed && FPlatformTime::Seconds() >= DisplayConfirmUntil)
	{
		RevertDisplay();            // (nobody confirmed the exclusive mode: the screen may be showing nothing)
	}
	if (bMaximizePending && !DisplayRequest.bPending)
	{
		// once the window is a window again (a few frames at most), maximized: the screen's resolution in a window
		EWindowMode::Type Mode = EWindowMode::Windowed;
		FIntPoint Size;
		const TSharedPtr<SWindow> Window = GameWindow(Mode, Size) && GEngine && GEngine->GameViewport ? GEngine->GameViewport->GetWindow() : nullptr;
		if (Window.IsValid() && Mode == EWindowMode::Windowed)
		{
			Window->Maximize();
			bMaximizePending = false;
			UE_LOG(LogSovereignRealms, Log, TEXT("window: maximized (the screen's resolution in a window)"));
		}
		else if (++MaximizeTries > 120)
		{
			bMaximizePending = false;   // (it never became a window: nothing to maximize)
		}
	}
	if (!DisplayRequest.bPending || !S)
	{
		return;
	}
	const FDisplayRequest R = DisplayRequest;
	DisplayRequest.bPending = false;
	bMaximizePending = R.bMaximize;
	MaximizeTries = 0;
	S->SetFullscreenMode(R.Mode);
	if (R.Size.X > 0 && R.Size.Y > 0)
	{
		S->SetScreenResolution(R.Size);
	}
	S->ApplyResolutionSettings(false);
	bDisplayUnconfirmed = R.bNeedsConfirm;
	if (R.bNeedsConfirm)
	{
		DisplayConfirmUntil = FPlatformTime::Seconds() + DisplayConfirmTime;
	}
	else
	{
		S->ConfirmVideoMode();
		S->SaveSettings();
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("window: %s %d x %d (%s)"), R.Mode == EWindowMode::Windowed ? TEXT("a window") : (R.Mode == EWindowMode::Fullscreen ? TEXT("exclusive full screen") : TEXT("full screen")),
		R.Size.X, R.Size.Y, R.bNeedsConfirm ? TEXT("to be confirmed") : TEXT("saved"));
}

float UVLGraphics::DisplayConfirmSeconds()
{
	return bDisplayUnconfirmed ? FMath::Max(float(DisplayConfirmUntil - FPlatformTime::Seconds()), 0.01f) : 0.f;
}

void UVLGraphics::ConfirmDisplay()
{
	UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
	if (bDisplayUnconfirmed && S)
	{
		bDisplayUnconfirmed = false;
		S->ConfirmVideoMode();
		S->SaveSettings();
		UE_LOG(LogSovereignRealms, Log, TEXT("window: the mode is confirmed (saved)"));
	}
}

void UVLGraphics::RevertDisplay()
{
	if (bDisplayUnconfirmed)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("window: the mode is not confirmed: back to the one before"));
		bDisplayUnconfirmed = false;
		DisplayRequest.bPending = true;
		DisplayRequest.Mode = DisplayBackMode;
		DisplayRequest.Size = DisplayBackSize;
		DisplayRequest.bNeedsConfirm = false;
	}
}

void UVLGraphics::ToggleFullscreen()
{
	SetDisplay(IsFullscreen() ? DisplayWindowed : DisplayBorderless, FIntPoint::ZeroValue);
}

void UVLGraphics::CycleDisplayMode()
{
#if PLATFORM_WINDOWS
	const int32 NumModes = 3;
#else
	const int32 NumModes = 2;       // (no exclusive full screen: the Mac's full screen is the borderless one)
#endif
	SetDisplay((FMath::Clamp(GetDisplayMode(), 0, NumModes - 1) + 1) % NumModes, FIntPoint::ZeroValue);
}

void UVLGraphics::StepResolution(int32 Direction)
{
	const int32 Mode = GetDisplayMode();
	TArray<FIntPoint> Sizes;
	DisplaySizes(Mode, Sizes);
	if (!CanPickResolution() || Sizes.Num() == 0)
	{
		return;
	}
	// from where the size now sits in the list (a dragged window is between two of them)
	const FIntPoint Now = GetResolution();
	int32 Pick = INDEX_NONE;
	if (Direction > 0)
	{
		for (int32 i = 0; i < Sizes.Num() && Pick == INDEX_NONE; ++i)
		{
			if (SizeLess(Now, Sizes[i])) { Pick = i; }
		}
		if (Pick == INDEX_NONE) { Pick = 0; }                       // (past the largest: the smallest)
	}
	else
	{
		for (int32 i = Sizes.Num() - 1; i >= 0 && Pick == INDEX_NONE; --i)
		{
			if (SizeLess(Sizes[i], Now)) { Pick = i; }
		}
		if (Pick == INDEX_NONE) { Pick = Sizes.Num() - 1; }
	}
	SetDisplay(Mode, Sizes[Pick]);
}

bool UVLGraphics::IsVSync()
{
	const UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
	return S && S->IsVSyncEnabled();
}

void UVLGraphics::SetVSync(bool bOn)
{
	UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
	if (!S)
	{
		return;
	}
	// (the engine reads bUseVSync into r.VSync when it starts; here the variable itself, and not
	// ApplyNonResolutionSettings, which would put the engine's scalability levels over the game's own presets)
	S->SetVSyncEnabled(bOn);
	if (IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(TEXT("r.VSync")))
	{
		Var->Set(bOn ? 1 : 0, ECVF_SetByGameSetting);
	}
	S->SaveSettings();
	UE_LOG(LogSovereignRealms, Log, TEXT("graphics: vsync %s (saved)"), bOn ? TEXT("on") : TEXT("off"));
}

EMouseLockMode UVLGraphics::PointerLock()
{
#if PLATFORM_WINDOWS
	return !GIsEditor && IsFullscreen() ? EMouseLockMode::LockAlways : EMouseLockMode::DoNotLock;
#else
	return EMouseLockMode::DoNotLock;
#endif
}

void UVLGraphics::KeepWindowState()
{
	UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
	EWindowMode::Type Mode = EWindowMode::Windowed;
	FIntPoint Size;
	// (a change on its way, or an exclusive mode not yet confirmed: nothing of it is saved)
	if (!S || DisplayRequest.bPending || bDisplayUnconfirmed || !GameWindow(Mode, Size))
	{
		return;
	}
	// against what the file holds (the engine puts a dragged window's size in the settings itself, but never saves it)
	int32 SavedX = 0, SavedY = 0, SavedMode = -1;
	if (GConfig)
	{
		const TCHAR* Section = TEXT("/Script/Engine.GameUserSettings");
		GConfig->GetInt(Section, TEXT("ResolutionSizeX"), SavedX, GGameUserSettingsIni);
		GConfig->GetInt(Section, TEXT("ResolutionSizeY"), SavedY, GGameUserSettingsIni);
		GConfig->GetInt(Section, TEXT("FullscreenMode"), SavedMode, GGameUserSettingsIni);
	}
	bool bChanged = SavedMode != int32(Mode);
	S->SetFullscreenMode(Mode);
	// a window's size (a full-screen one is the desktop's: the window's own is kept for coming back to it)
	if (Mode == EWindowMode::Windowed)
	{
		bChanged |= SavedX != Size.X || SavedY != Size.Y;
		S->SetScreenResolution(Size);
	}
	if (bChanged)
	{
		S->ConfirmVideoMode();
		if (Mode == EWindowMode::Windowed && GConfig)
		{
			GConfig->SetInt(TEXT("SovereignRealms.Video"), TEXT("WindowX"), Size.X, GGameUserSettingsIni);
			GConfig->SetInt(TEXT("SovereignRealms.Video"), TEXT("WindowY"), Size.Y, GGameUserSettingsIni);
		}
		S->SaveSettings();
		UE_LOG(LogSovereignRealms, Log, TEXT("window: kept as %s %d x %d"), Mode == EWindowMode::Windowed ? TEXT("a window") : TEXT("full screen"), Size.X, Size.Y);
	}
}
