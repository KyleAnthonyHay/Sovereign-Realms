#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLGraphics.generated.h"

class APostProcessVolume;
class UExponentialHeightFogComponent;

/**
 * The Graphics settings: a quality preset (Low / Medium / High) and a render scale, applied by code (console variables
 * and a few properties of the level's own look actors), so they work in a Shipping build with no console. Saved in
 * GameUserSettings.ini, [VoxelLab.Video] Quality / RenderScale.
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
class VOXELLAB_API UVLGraphics : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	enum { Low = 0, Medium = 1, High = 2, NumQualities = 3 };

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
	static void Save();
	/** Everything, to the engine and to this world's look actors. */
	static void Apply(UWorld* World);

	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override { return WorldType == EWorldType::Game || WorldType == EWorldType::PIE; }
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

	static int32 Quality;
	static int32 RenderScale;
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
};
