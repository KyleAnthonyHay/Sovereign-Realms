// The Graphics settings: see VLGraphics.h.

#include "VLGraphics.h"
#include "VoxelLab.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Engine/Engine.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/GameViewportClient.h"
#include "Engine/PointLight.h"
#include "Components/LightComponent.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformApplicationMisc.h"
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
				UE_LOG(LogVoxelLab, Warning, TEXT("graphics: no console variable %s"), V.Name);
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
			UE_LOG(LogVoxelLab, Log, TEXT("graphics: quality %s, render scale %d%%"), UVLGraphics::QualityName(UVLGraphics::GetQuality()), UVLGraphics::GetRenderScale());
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
			UE_LOG(LogVoxelLab, Log, TEXT("graphics: %d lamp(s), max draw distance %.0f, fade range %.0f"), N, Draw, Fade);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdScale(TEXT("vl.Gfx.Scale"), TEXT("render scale, per cent of the engine's automatic resolution (50..100; not saved)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() > 0)
			{
				UVLGraphics::SetRenderScale(World, FCString::Atoi(*Args[0]));
			}
			UE_LOG(LogVoxelLab, Log, TEXT("graphics: quality %s, render scale %d%%"), UVLGraphics::QualityName(UVLGraphics::GetQuality()), UVLGraphics::GetRenderScale());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdDynRes(TEXT("vl.Gfx.DynRes"), TEXT("0 Off, 1 Target 60 fps, 2 Target 40 fps, 3 Target 30 fps (not saved)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() > 0)
			{
				UVLGraphics::SetDynamicRes(World, FCString::Atoi(*Args[0]));
			}
			UE_LOG(LogVoxelLab, Log, TEXT("graphics: dynamic resolution %s"), UVLGraphics::DynamicResName(UVLGraphics::GetDynamicRes()));
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
		GConfig->GetInt(TEXT("VoxelLab.Video"), TEXT("Quality"), Quality, GGameUserSettingsIni);
		Quality = FMath::Clamp(Quality, 0, NumQualities - 1);
		RenderScale = PresetScale[Quality];
		GConfig->GetInt(TEXT("VoxelLab.Video"), TEXT("RenderScale"), RenderScale, GGameUserSettingsIni);
		RenderScale = FMath::Clamp(RenderScale, 50, 100);
		GConfig->GetInt(TEXT("VoxelLab.Video"), TEXT("DynamicRes"), DynamicRes, GGameUserSettingsIni);
		DynamicRes = FMath::Clamp(DynamicRes, 0, NumDynRes - 1);
	}
}

void UVLGraphics::Save()
{
	LoadOnce();
	if (GConfig)
	{
		GConfig->SetInt(TEXT("VoxelLab.Video"), TEXT("Quality"), Quality, GGameUserSettingsIni);
		GConfig->SetInt(TEXT("VoxelLab.Video"), TEXT("RenderScale"), RenderScale, GGameUserSettingsIni);
		GConfig->SetInt(TEXT("VoxelLab.Video"), TEXT("DynamicRes"), DynamicRes, GGameUserSettingsIni);
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
	Apply(&InWorld);
	UE_LOG(LogVoxelLab, Log, TEXT("graphics: quality %s, render scale %d%%"), QualityName(Quality), RenderScale);
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
			UE_LOG(LogVoxelLab, Log, TEXT("graphics: dynamic resolution %s (budget %.1f ms, range %.1f%%..%.1f%%)"), DynamicResName(EffectiveDyn), Budget, MinPct, MaxPct);
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
			UE_LOG(LogVoxelLab, Log, TEXT("graphics: r.ScreenPercentage %.1f (render scale %d%%, view %d x %d, where the engine's own choice is %.1f%%)"), Wanted, RenderScale,
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
				UE_LOG(LogVoxelLab, Log, TEXT("graphics: macOS thermal=%d lowPower=%d"), ThermalLevel, bLowPowerMode ? 1 : 0);
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
		if (CVarIdleThrottle.GetValueOnGameThread() != 0)
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
		UE_LOG(LogVoxelLab, Verbose, TEXT("graphics: fog grid %s"), bOff ? TEXT("coarse (far view)") : TEXT("as the preset"));
	}
}

void UVLGraphics::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	UpdateScreenPercentage(false);
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
}
