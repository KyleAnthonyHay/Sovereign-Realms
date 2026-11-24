#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLFog.generated.h"

class AVLKing;
class UTexture2D;
class UMaterialInstanceDynamic;
class APostProcessVolume;

/**
 * Fog of war for the player (team 0): the classic three states on a grid of Cell cm over the map (the path grid's
 * ground, made square as the minimap is):
 *   unexplored            never seen: dense fog
 *   explored              seen before, not now: lighter fog, the ground and the buildings as they were, no enemy units
 *   visible               seen now by one of the player's units, buildings or ships: clear
 *
 * VISION (the owner's rule). Each eye stands EyeHeight (vl.Fog.EyeHeight, 20 m) over its feet and looks down at
 * Angle (vl.Fog.Angle, 30 degrees) below the horizontal all the way round; where that cone meets the ground is how far
 * it sees. On flat ground that is 20 / tan 30 = 34.6 m. Here it is worked out per direction (48 of them): a ray at -30
 * degrees is marched from the eye over the terrain's heightfield (the level's Ground meshes and the water, sampled once
 * on the fog's cells) until it meets the ground. From a plateau, a ridge or a tower's lookout the ground is further
 * below the eye and the ray goes further (a lookout at 10.5 m: 52.8 m over flat ground); a slope rising in front, a
 * ridge or a cliff stops it sooner. The circle each eye reveals is that outline, filled. Units: times their kind's
 * sight over a swordsman's (VLRules::FTroop::Sight: archers and Jonathan 1.15, the Spy 2.0), scaled by vl.Fog.KindScale.
 * Buildings: the same from the middle of their footprint, pushed out to their walls. WATCH TOWERS see TowerView
 * (vl.Fog.TowerView, 1.8; was 1.35) times their shooting range from their walls (24 / 27 / 30 m: 43.2 / 48.6 / 54 m) on flat
 * ground, combined with the height rule: the eye's height is chosen so the -30 degree cone lands there on flat ground
 * (24.9 / 28.1 / 31.2 m, over the tower's top), and the same per-direction ray then sees further from a plateau
 * and less against a slope. A tower's own archers are part of it (not eyes of their own); archers the player sends up
 * to the lookout are eyes from the lookout's floor.
 *
 * HIDDEN: enemy units (and ships) not on a visible cell are hidden in the world (SetActorHiddenInGame; only those the
 * fog hid are shown again), and left out of the HUD's frame list (bars, diamonds, the minimap), of picking and hover.
 * The enemy's Spy shows only within 45 % (its Notice) of a player eye's reach. Enemy buildings raised in the match are
 * hidden until first seen; the map's own stand (their tips poke out of the fog). The minimap draws enemy buildings
 * only once seen.
 *
 * RENDERING: a post-process material (/Game/Voxel/Fog/M_FogOfWar, made by Tools/ue/build_fog_material.py) on an
 * unbound post-process volume of the fog's own. It marches the view ray through a layer whose top is Layer
 * (vl.Fog.Layer, 17.5 m: just under a watch tower's 20.6 m tip) over the terrain smoothed (a height texture), its
 * density from the fog texture (R visible, G explored), with drifting wisps on its top: towers' roofs, castle flags and
 * the mountain's peaks stand out of it. The fog texture's alpha is the minimap's veil.
 *
 * Off on the Test World (vl.Fog.TestWorld 1 for it there), on sandboxes and the title screen. The enemy commander
 * keeps its own perception (VLEnemyAI: sightings within 26 m), untouched.
 * Console: vl.Fog 0|1, vl.Fog.Reveal [0|1], vl.Fog.Info, vl.Fog.Eyes; cvars vl.Fog.*.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLFog : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLFog* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UVLFog, STATGROUP_Tickables); }

	/** The fog is on in this match (a battle, playing, not switched off). */
	bool IsActive() const { return bActive; }
	/** Is this unit hidden from the player by the fog (an enemy unit not seen now)? False whenever the fog is off. */
	static bool HidesUnit(const AVLKing* Unit);
	/** The same for any actor: a unit, an enemy building not seen yet, an enemy ship not seen now. */
	static bool HidesActor(const AActor* Actor);
	/** A building in sight now (a cell of its footprint visible), or the player's own, or the fog off: the HUD draws
	 *  the bars over it (training, a site's progress, health) only then. */
	static bool InSight(const AActor* Building);
	/** 0 unexplored, 1 explored, 2 visible (2 everywhere while the fog is off). */
	int32 StateAt(const FVector2D& World) const;
	/** Has the player seen this enemy building (the minimap draws it only then)? True while the fog is off. */
	bool WasSeen(const AActor* Building) const;
	/** What an eye (a unit, a building, a ship) sees: the outline on the ground (world points, Z on the ground + 15 cm).
	 *  False: it is no eye of the player's, or the fog is off. */
	bool Outline(const AActor* Eye, TArray<FVector>& Out);
	/** Its mean view radius (cm), the eye's height over its feet and the ground under the eye; 0 if it is no eye. */
	float ViewRadius(const AActor* Eye, float* OutMin = nullptr, float* OutMax = nullptr, float* OutEyeHeight = nullptr);

	/** The minimap's veil: the fog texture (alpha: how dark) and the world square it covers. */
	UTexture2D* GetMaskTexture() const { return MaskTex; }
	FBox2D GetBounds() const { return FBox2D(Origin, Origin + FVector2D(Dim * Cell, Dim * Cell)); }

	/** For saved games: the explored cells (one byte each, Dim x Dim) and the grid they are on. */
	void GetExplored(TArray<uint8>& Out, int32& OutDim, float& OutCell, FVector2D& OutOrigin) const;
	/** Puts them back (only when the grid is the same; returns false otherwise). */
	bool SetExplored(const TArray<uint8>& In, int32 InDim);
	/** For saved games: the enemy buildings seen at least once. */
	void GetSeen(TArray<const AActor*>& Out) const;
	/** For saved games (UVLSaves, as the match starts): the explored cells and the buildings seen, put back on the
	 *  fog's first update of this match (after its new-match reset), when the grid is the same (InDim). */
	void RestoreLater(const TArray<uint8>& InExplored, int32 InDim, const TArray<const AActor*>& InSeen);

	void LogInfo(const AActor* Focus);
	void LogEyes();
	void SetRevealAll(bool bOn) { bRevealAll = bOn; NextUpdate = 0.0; }

private:
	struct FEye
	{
		TWeakObjectPtr<const AActor> Actor;
		FVector2D At = FVector2D::ZeroVector;
		float FeetZ = 0.f;
		float EyeH = 0.f;
		float Scale = 1.f;
		float Notice = 1.f;
		TArray<float> Wall;     // per direction: the footprint's reach that way (buildings)
		TArray<float> R;        // per direction: how far it sees (cm, the wall included)
		float MaxR = 0.f, MeanR = 0.f;
		uint32 Frame = 0;
		bool bDirty = false;    // its rays to be worked out again
	};
	static constexpr int32 NumDirs = 48;

	bool Init();
	void Reset();
	void BuildHeights();
	void BuildOffsets(float MaxRadius);
	void UpdateVision();
	void UpdateHidden();
	void UploadMask(float Dt);
	void SetupVisual();
	void ApplyVisualParams();
	void SetHiddenByFog(AActor* A, bool bHide);
	/** The eye's parameters for a unit / building / ship of the player's; false: not an eye. */
	bool EyeParams(const AActor* A, FEye& E) const;
	void ComputeRays(FEye& E) const;
	FEye* FindOrMakeEye(const AActor* A, bool bDefer = false);
	float HeightAt(const FVector2D& P) const;
	bool ToCell(const FVector2D& P, int32& Out) const;

	bool bActive = false;
	bool bInit = false;
	bool bRevealAll = false;
	bool bWasPlaying = false;
	// a saved game's fog, waiting for the match's first update (RestoreLater)
	TArray<uint8> PendingExplored;
	int32 PendingDim = 0;
	bool bPendingRestore = false;
	TArray<TWeakObjectPtr<const AActor>> PendingSeen;
	double NextUpdate = 0.0;
	double LastTick = 0.0;
	float Cell = 200.f;
	int32 Dim = 0;
	FVector2D Origin = FVector2D::ZeroVector;
	TArray<float> Height;          // the terrain (and water) per cell
	TArray<uint8> Visible;         // seen now (0/1)
	TArray<uint8> Explored;        // seen ever (0/1)
	TArray<uint8> ShowVis, ShowExp;    // what is drawn: eased toward the above
	TArray<FColor> MaskPixels;
	struct FOffset { int16 DX, DY; float Dist; float Dir; };
	TArray<FOffset> Offsets;       // the cells round an eye, nearest first
	float OffsetsRadius = 0.f;
	TMap<TWeakObjectPtr<const AActor>, FEye> Eyes;
	TSet<const AActor*> HiddenNow;                 // hidden from the player this frame (units, ships, buildings)
	TSet<TWeakObjectPtr<AActor>> HiddenByUs;       // what SetActorHiddenInGame was called on by the fog
	TSet<TWeakObjectPtr<const AActor>> Seen;       // enemy buildings seen at least once
	TSet<const AActor*> InSightNow;                // enemy and neutral buildings in sight at the last update
	TSet<TWeakObjectPtr<const AActor>> MapBuildings;   // the level's own (there when the match began)
	uint32 EyeFrame = 0;
	double UpdateMs = 0.0, UpdateMsMax = 0.0;      // the last vision update and mask upload (CPU), and the most since vl.Fog.Info

	UPROPERTY(Transient) TObjectPtr<UTexture2D> MaskTex;
	UPROPERTY(Transient) TObjectPtr<UTexture2D> HeightTex;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> FogMID;
	UPROPERTY(Transient) TObjectPtr<APostProcessVolume> Volume;
	bool bVisualTried = false;
};
