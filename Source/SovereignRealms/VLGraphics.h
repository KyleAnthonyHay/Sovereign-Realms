#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Engine/EngineBaseTypes.h"
#include "VLGraphics.generated.h"

class APostProcessVolume;
class UExponentialHeightFogComponent;

/**
 * The Graphics settings: a quality preset (Low / Medium / High) and a render scale, applied by code (console variables
 * and a few properties of the level's own look actors), so they work in a Shipping build with no console. Saved in
 * GameUserSettings.ini, [SovereignRealms.Video] Quality / RenderScale.
 *
 * HIGH is the look the maps were built for: every console variable keeps the value the engine started with, the
 * level's post-process volume keeps its Lumen quality (2.0 / 2.0), and the render scale is the engine's own automatic
 * screen percentage (r.ScreenPercentage 0: from the size of the window; the packaged game's 1736 x 977 window renders
 * at 78 % of that, a Retina-sized 3224 x 1660 editor window at 55 %).
 * MEDIUM: Lumen final gather quality and scene detail 1.0, a coarser volumetric fog grid, softer sun shadows, lamps
 * that stop sooner, render scale 85 % of the automatic one.
 * LOW: no Lumen (the sky light with distance-field and screen-space ambient occlusion instead), no volumetric fog
 * (so no lamp shafts either: the plain height fog takes its place), coarser shadows still, render scale 70 %.
 *
 * It also coarsens the volumetric fog's grid (32 px froxels, 32 slices) while the camera is far above the ground (the
 * far overview): the fog volume reaches 120 m from the camera, and with nothing but air inside it the coarse grid
 * gives the same picture for a twentieth of the cost (vl.Opt.FarFog 0: never). Switching the fog off instead would
 * show: the height fog that takes its place scatters the light differently.
 *
 * vl.Gfx.Quality 0|1|2 and vl.Gfx.Scale <percent> set them from the console (not saved).
 */
UCLASS()
class SOVEREIGNREALMS_API UVLGraphics : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	enum { Low = 0, Medium = 1, High = 2, NumQualities = 3 };
	enum { DynOff = 0, Dyn60 = 1, Dyn40 = 2, Dyn30 = 3, NumDynRes = 4 };

	// ---- the settings (one set for the whole game; AVLHUD's settings screen shows and changes them)
	static int32 GetQuality() { LoadOnce(); return Quality; }
	static const TCHAR* QualityName(int32 InQuality);
	/** The preset, with its own render scale. */
	static void SetQuality(UWorld* World, int32 InQuality);
	/** Per cent of the engine's automatic resolution: 100 is what the game has always rendered at. */
	static int32 GetRenderScale() { LoadOnce(); return RenderScale; }
	static void SetRenderScale(UWorld* World, int32 Percent);
	/** The next choice of the settings row (100, 85, 75, 67, 60, 50). */
	static void CycleRenderScale(UWorld* World);
	/** Dynamic resolution target (0 Off, 1 Target 60 fps, 2 Target 40 fps, 3 Target 30 fps) using MetalRHI + TSR. */
	static int32 GetDynamicRes() { LoadOnce(); return DynamicRes; }
	static const TCHAR* DynamicResName(int32 Mode);
	static void SetDynamicRes(UWorld* World, int32 Mode);
	static void CycleDynamicRes(UWorld* World);
	/** User frame-rate limit from Settings (0 = Unlimited) and menu-active hint for ProMotion / thermal pacing. */
	static void SetUserFrameCap(int32 InFps);
	static void SetMenuThrottle(UWorld* World, bool bInMenu);
	static void Save();
	/** The window (packaged game only; the editor's play window is the editor's): full screen (borderless, the
	 *  desktop's size; on Windows also exclusive, at one of the display's own modes) or a window. The choice and the
	 *  window's size are kept in GameUserSettings.ini ([/Script/Engine.GameUserSettings] FullscreenMode,
	 *  ResolutionSizeX / Y) however they were changed: the Settings rows, F11 / Alt+Enter, the green button, dragging
	 *  the window's edge (KeepWindowState, once a second and when the world goes).
	 *
	 *  A change asked for here is NOT made at once: it waits for this subsystem's next Tick. The Settings screen asks
	 *  from inside the HUD's draw, and the engine resizes the viewport there and then and draws it again
	 *  (FSceneViewport::ResizeViewport): a second HUD draw inside the first. When the inner one ended the engine took
	 *  the canvas from the HUD, and the outer one's next Text() read a null canvas (the crash of 2026-11-23). */
	enum { DisplayWindowed = 0, DisplayBorderless = 1, DisplayExclusive = 2 };
	static bool IsFullscreen();
	static bool CanChangeWindow() { return !GIsEditor; }
	static void ToggleFullscreen();
	static void KeepWindowState();
	/** The display mode the window has, or is about to get. */
	static int32 GetDisplayMode();
	static const TCHAR* DisplayModeName(int32 Mode);
	/** Windowed -> borderless full screen -> full screen (exclusive; Windows only) -> windowed. */
	static void CycleDisplayMode();
	/** The mode and the size asked for (a size of 0: the window's remembered one, or the desktop's). An exclusive full
	 *  screen mode has to be confirmed (ConfirmDisplay) within DisplayConfirmSeconds, or the display goes back. */
	static void SetDisplay(int32 Mode, FIntPoint Resolution);
	/** The size drawn at: the window's, or the display's in full screen. */
	static FIntPoint GetResolution();
	/** A window and exclusive full screen have a choice of sizes; borderless is the desktop's. */
	static bool CanPickResolution();
	/** The next larger (+1) or smaller (-1) size of the mode's list: the display's own modes in exclusive full screen,
	 *  the usual window sizes up to the desktop in a window. */
	static void StepResolution(int32 Direction);
	/** Seconds left to confirm an exclusive full screen mode (0: nothing to confirm). */
	static float DisplayConfirmSeconds();
	static void ConfirmDisplay();
	static void RevertDisplay();
	static bool IsVSync();
	static void SetVSync(bool bOn);
	/** The pointer's lock for the overview and the menus: never on the Mac (full screen grabbed the mouse badly
	 *  there); on Windows kept inside the game while it is full screen (no slipping onto a second monitor). */
	static EMouseLockMode PointerLock();
	/** Everything, to the engine and to this world's look actors. */
	static void Apply(UWorld* World);

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override { return WorldType == EWorldType::Game || WorldType == EWorldType::PIE; }
	virtual bool IsTickableWhenPaused() const override { return true; }
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UVLGraphics, STATGROUP_Tickables); }

private:
	static void LoadOnce();
	static void ApplyConsoleVariables();
	static void RestoreConsoleVariables();
	void ApplyToWorld();
	void UpdateScreenPercentage(bool bForce);
	void UpdateFarFog();
	void UpdateThermalAndFrameCap(bool bForce);
	static void ApplyPendingDisplay();

	static int32 Quality;
	static int32 RenderScale;
	static int32 DynamicRes;
	static int32 UserFrameCap;
	static bool bMenuThrottle;
	static bool bLoaded;

	// the level's unbound post-process volume and what it asked of Lumen (kept for High)
	TWeakObjectPtr<APostProcessVolume> Look;
	float LookFinalGather = 1.f, LookSceneDetail = 1.f;
	bool bLookFinalGather = false, bLookSceneDetail = false;
	bool bLookFound = false;

	TWeakObjectPtr<UExponentialHeightFogComponent> Fog;
	bool bFogWasVolumetric = false;      // as the level has it
	static bool bFarFog;                 // the camera is far above everything the fog volume could reach: the coarse grid
	float FogCheckIn = 0.f;

	FIntPoint LastViewSize = FIntPoint::ZeroValue;
	float LastScreenPercentage = -1.f;
	int32 LastAppliedDynRes = -1;
	int32 LastEffectiveFrameCap = -1;
	int32 ThermalLevel = 0;              // macOS NSProcessInfoThermalState (0 Nominal .. 3 Critical)
	bool bLowPowerMode = false;          // macOS Low Power Mode
	float ThermalCheckIn = 0.f;
	float WindowCheckIn = 1.f;
};
