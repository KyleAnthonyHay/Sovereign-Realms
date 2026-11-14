// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "Common/SRTypes.h"
#include "SRFeelSettings.generated.h"

/**
 * Every tuning knob for the command & combat slice.
 * Project Settings > Game > Sovereign Feel. Saved to Config/DefaultGame.ini.
 * Values are read live every frame, so edits made while PIE is running apply immediately.
 * Distances are cm, times are seconds, angles are degrees.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Sovereign Feel"))
class SOVEREIGNREALMS_API USRFeelSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	USRFeelSettings();

	virtual FName GetCategoryName() const override { return TEXT("Game"); }

	static const USRFeelSettings& Get() { return *GetDefault<USRFeelSettings>(); }

	const FSRUnitStats& StatsFor(ESRUnitType Type) const
	{
		switch (Type)
		{
		case ESRUnitType::Archer: return Archer;
		case ESRUnitType::Horseman: return Horseman;
		case ESRUnitType::Catapult: return Catapult;
		case ESRUnitType::Builder: return Builder;
		default: return Shieldbearer;
		}
	}

	// ---------------------------------------------------------------- Camera
	/** World yaw the camera looks along. 0 = +X is "up the screen". */
	UPROPERTY(EditAnywhere, Config, Category = "Camera")
	float CameraYaw = 0.f;

	/** Horizontal FOV. Fairly wide with a close, low camera: terraces show their faces and the hazy distance gets into frame; the tilt-shift supplies the miniature feel. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera", meta = (ClampMin = "10", ClampMax = "100"))
	float CameraFOV = 50.f;

	/** Camera distance from the focus point when fully zoomed in. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "200"))
	float ZoomDistanceMin = 950.f;

	/** Camera distance from the focus point when fully zoomed out. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "200"))
	float ZoomDistanceMax = 11000.f;

	/** 0 = fully in, 1 = fully out. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "0", ClampMax = "1"))
	float ZoomDefault = 0.5f;

	/** Zoom fraction per mouse-wheel notch. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "0.01", ClampMax = "1"))
	float ZoomStep = 0.11f;

	/** Time constant of the zoom ease. Smaller = snappier. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "0.001"))
	float ZoomSmoothTime = 0.11f;

	/** Pitch when fully zoomed in (lower / more side-on). */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "-89", ClampMax = "-10"))
	float PitchZoomedIn = -30.f;

	/** Pitch when fully zoomed out (steeper / more top-down). */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "-89", ClampMax = "-10"))
	float PitchZoomedOut = -58.f;

	/** When zooming in, how far the focus slides toward the cursor per notch (0 = off). */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "0", ClampMax = "1"))
	float ZoomToCursorStrength = 0.18f;

	/** Pan speed (cm/s) at the default zoom; scales with zoom distance. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Pan", meta = (ClampMin = "0"))
	float PanSpeed = 2300.f;

	/** Time constant for reaching pan speed. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Pan", meta = (ClampMin = "0.001"))
	float PanAccelTime = 0.07f;

	/** Time constant for gliding to a stop. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Pan", meta = (ClampMin = "0.001"))
	float PanDecelTime = 0.14f;

	UPROPERTY(EditAnywhere, Config, Category = "Camera|Pan")
	bool bEdgePan = true;

	/** Screen-edge band (pixels) that triggers edge panning. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Pan", meta = (ClampMin = "1"))
	float EdgePanMargin = 12.f;

	/** If true W/A/S/D pan the camera. A and S double as Attack-move / Stop: a quick TAP issues the command, HOLDING pans. If false only arrows / edge / middle-drag pan and A / S act instantly. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Pan")
	bool bWASDPansCamera = true;

	/** A / S held longer than this pan the camera instead of issuing the command (only while units are selected). */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Pan", meta = (ClampMin = "0.05"))
	float CommandKeyTapTime = 0.17f;

	/** Time constant of the glide when re-centering on the selection (Space / Home). */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Pan", meta = (ClampMin = "0.001"))
	float RecenterSmoothTime = 0.16f;

	/** Camera focus is clamped to +/- this (cm) around the world origin. Also clamps move orders. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Bounds")
	FVector2D MapHalfExtent = FVector2D(12000.f, 12000.f);

	/** Motion blur smears units while panning and hides fast attack animation, so the game camera turns it off. Untick to let post-process volumes decide. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera")
	bool bDisableMotionBlur = true;

	UPROPERTY(EditAnywhere, Config, Category = "Camera|Shake")
	bool bCameraShake = true;

	/** Max positional offset (cm) at full trauma, at the default zoom. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Shake", meta = (ClampMin = "0"))
	float ShakeMaxOffset = 7.f;

	/** Trauma lost per second. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Shake", meta = (ClampMin = "0.1"))
	float ShakeDecay = 3.2f;

	UPROPERTY(EditAnywhere, Config, Category = "Camera|Shake", meta = (ClampMin = "1"))
	float ShakeFrequency = 26.f;

	/** Trauma (0..1) added by a heavy melee hit / by a death. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Shake", meta = (ClampMin = "0", ClampMax = "1"))
	float ShakeTraumaHeavyHit = 0.16f;

	UPROPERTY(EditAnywhere, Config, Category = "Camera|Shake", meta = (ClampMin = "0", ClampMax = "1"))
	float ShakeTraumaDeath = 0.34f;

	// ------------------------------------------------------------- Selection
	/** Mouse travel (pixels) before a left-drag becomes a box select. */
	UPROPERTY(EditAnywhere, Config, Category = "Selection", meta = (ClampMin = "1"))
	float DragThreshold = 7.f;

	UPROPERTY(EditAnywhere, Config, Category = "Selection", meta = (ClampMin = "0.05"))
	float DoubleClickTime = 0.32f;

	/** Extra forgiveness (cm) around a unit when clicking it. */
	UPROPERTY(EditAnywhere, Config, Category = "Selection", meta = (ClampMin = "0"))
	float PickPadding = 22.f;

	UPROPERTY(EditAnywhere, Config, Category = "Selection|Look")
	FLinearColor SelectionRingColor = FLinearColor(0.25f, 1.f, 0.35f);

	UPROPERTY(EditAnywhere, Config, Category = "Selection|Look")
	FLinearColor HoverRingColor = FLinearColor(0.9f, 0.9f, 0.8f);

	UPROPERTY(EditAnywhere, Config, Category = "Selection|Look")
	FLinearColor EnemyRingColor = FLinearColor(1.f, 0.16f, 0.1f);

	UPROPERTY(EditAnywhere, Config, Category = "Selection|Look")
	FLinearColor BoxFillColor = FLinearColor(0.3f, 1.f, 0.4f, 0.10f);

	UPROPERTY(EditAnywhere, Config, Category = "Selection|Look")
	FLinearColor BoxLineColor = FLinearColor(0.45f, 1.f, 0.5f, 0.9f);

	/** Ring pops to this scale when a unit becomes selected, then settles to 1. */
	UPROPERTY(EditAnywhere, Config, Category = "Selection|Look", meta = (ClampMin = "1"))
	float RingSelectPopScale = 1.35f;

	// ---------------------------------------------------------------- Orders
	/** Empty space between neighbours in a formation (added to both body radii). */
	UPROPERTY(EditAnywhere, Config, Category = "Orders|Formation", meta = (ClampMin = "0"))
	float FormationGap = 46.f;

	/** Formation width grows with sqrt(count * this). Larger = wider, shallower lines. */
	UPROPERTY(EditAnywhere, Config, Category = "Orders|Formation", meta = (ClampMin = "0.5"))
	float FormationWidthBias = 2.5f;

	UPROPERTY(EditAnywhere, Config, Category = "Orders|Formation", meta = (ClampMin = "1"))
	int32 FormationMaxColumns = 10;

	/** Units acknowledge an order with a hop; each waits a random delay up to this so the group ripples. */
	UPROPERTY(EditAnywhere, Config, Category = "Orders|Feedback", meta = (ClampMin = "0"))
	float AckMaxDelay = 0.09f;

	UPROPERTY(EditAnywhere, Config, Category = "Orders|Feedback", meta = (ClampMin = "0"))
	float AckHopHeight = 16.f;

	UPROPERTY(EditAnywhere, Config, Category = "Orders|Feedback", meta = (ClampMin = "0.05"))
	float AckHopTime = 0.2f;

	UPROPERTY(EditAnywhere, Config, Category = "Orders|Feedback", meta = (ClampMin = "0.05"))
	float MarkerLifetime = 0.55f;

	/** Outer radius (cm) of the ground-click marker when it appears. */
	UPROPERTY(EditAnywhere, Config, Category = "Orders|Feedback", meta = (ClampMin = "10"))
	float MarkerRadius = 85.f;

	UPROPERTY(EditAnywhere, Config, Category = "Orders|Feedback")
	FLinearColor MoveMarkerColor = FLinearColor(0.25f, 1.f, 0.35f);

	UPROPERTY(EditAnywhere, Config, Category = "Orders|Feedback")
	FLinearColor AttackMarkerColor = FLinearColor(1.f, 0.22f, 0.1f);

	// -------------------------------------------------------------- Movement
	/** Units start steering apart inside this gap (cm, edge-to-edge). */
	UPROPERTY(EditAnywhere, Config, Category = "Movement|Avoidance", meta = (ClampMin = "0"))
	float SeparationPadding = 28.f;

	/** Peak steering speed (cm/s) from separation. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement|Avoidance", meta = (ClampMin = "0"))
	float SeparationStrength = 260.f;

	/** How strongly a moving unit side-steps around someone standing in its way (0..1 of max speed). */
	UPROPERTY(EditAnywhere, Config, Category = "Movement|Avoidance", meta = (ClampMin = "0", ClampMax = "2"))
	float SidestepStrength = 0.8f;

	/** Fraction of body overlap removed per second by the hard push-apart pass. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement|Avoidance", meta = (ClampMin = "1"))
	float OverlapResolveRate = 30.f;

	/** Speed fraction a unit keeps while it is still turning to face its travel direction. 1 = no slow-down. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "0", ClampMax = "1"))
	float TurnSpeedFloor = 0.4f;

	/** Within this distance (cm) of its slot a unit counts as arrived. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "1"))
	float ArriveTolerance = 10.f;

	/** A unit that makes no progress for this long near its destination settles where it is (prevents shoving matches). */
	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "0.1"))
	float GiveUpTimeNear = 0.45f;

	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "0.1"))
	float GiveUpTimeFar = 2.5f;

	/** Tallest ledge (cm) a unit can step up; anything steeper blocks it. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement|Terrain", meta = (ClampMin = "1"))
	float StepHeight = 45.f;

	/** Largest drop (cm) a unit will walk off. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement|Terrain", meta = (ClampMin = "1"))
	float MaxDropHeight = 140.f;

	// ---------------------------------------------------------------- Combat
	/** Seconds the hit flash takes to fade. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Reaction", meta = (ClampMin = "0.01"))
	float HitFlashTime = 0.16f;

	/** Colour the whole sprite flashes toward when hit (M_UnitSprite: HitFlashMix and HitFlashGlow set how hard). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Reaction")
	FLinearColor HitFlashColor = FLinearColor(1.f, 0.92f, 0.85f);

	/** Squash of the sprite card on hit (0.1 = 10% shorter, slightly wider), on top of the authored flinch frames. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Reaction", meta = (ClampMin = "0", ClampMax = "0.6"))
	float HitSquash = 0.1f;

	/** Seconds the three flinch frames take. Shown only on a unit that is standing and not mid-attack; it never interrupts anything. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Reaction", meta = (ClampMin = "0.03"))
	float HitAnimTime = 0.17f;

	/** Time constant (s) of knockback decay. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Reaction", meta = (ClampMin = "0.01"))
	float KnockbackDecayTime = 0.07f;

	/** Freeze attacker and victim for a few frames on heavy hits. Local to the two units; the game never stalls. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Stop")
	bool bHitStop = true;

	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Stop", meta = (ClampMin = "0", ClampMax = "0.3"))
	float HitStopTime = 0.045f;

	/** Random extra delay (s) added to each attack cooldown so a group does not swing / loose in perfect unison. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0"))
	float AttackIntervalJitter = 0.14f;

	/** Idle units hit by an enemy call idle allies within this radius to help. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|AI", meta = (ClampMin = "0"))
	float AlertRadius = 650.f;

	/** Hostile units give up the chase and walk home beyond this distance from where they spawned. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|AI", meta = (ClampMin = "0"))
	float EnemyLeashDistance = 2400.f;

	/** Old pre-commander behaviour: enemy troops give up a chase far from home. Off: the commander decides. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|AI")
	bool bEnemyLeash = false;

	/** Selected troops show their line of sight (and archers their bow range) as circles on the ground. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|AI")
	bool bShowRangeCircles = true;

	UPROPERTY(EditAnywhere, Config, Category = "Combat|AI")
	FLinearColor SightCircleColor = FLinearColor(0.55f, 0.85f, 1.f, 0.55f);

	UPROPERTY(EditAnywhere, Config, Category = "Combat|AI")
	FLinearColor RangeCircleColor = FLinearColor(1.f, 0.55f, 0.18f, 0.85f);

	/** Seconds a health bar stays visible after the unit was last damaged (selected / hovered units always show it). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Health Bars", meta = (ClampMin = "0"))
	float HealthBarLingerTime = 4.f;

	UPROPERTY(EditAnywhere, Config, Category = "Combat|Health Bars")
	FVector2D HealthBarSize = FVector2D(44.f, 5.f);

	/** HUD overlay is authored for a 1080p-tall view and scaled with the viewport (so it stays readable on Retina). Extra multiplier here. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Health Bars", meta = (ClampMin = "0.25"))
	float HUDScale = 1.f;

	/** Seconds the eight death frames take (authored for 12 fps = 0.67 s). The last frame is the corpse and is held. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Death", meta = (ClampMin = "0.05"))
	float DeathAnimTime = 0.67f;

	/** The dying body is carried this far (cm) along the direction of the killing blow while it falls. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Death", meta = (ClampMin = "0"))
	float DeathKnockDistance = 16.f;

	/** Seconds the corpse lies there before it starts to fade. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Death", meta = (ClampMin = "0"))
	float CorpseLingerTime = 2.2f;

	/** Seconds the corpse (and its shadow) takes to dissolve before removal. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Death", meta = (ClampMin = "0.05"))
	float CorpseFadeTime = 1.3f;

	// ------------------------------------------------------------- Animation
	// The troops are sprite sheets (SourceArt/Characters/SPRITE_SPEC.md). Frames are chosen from gameplay state:
	// walk by distance travelled, attack by the wind-up / recovery phase, the rest by time.
	/** Seconds of the spawn animation (rise from a crouch, with a scale pop). Units are not selectable or active until it ends, on the guard frame. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0.01"))
	float SpawnPopTime = 0.38f;

	/** Random extra delay before each unit pops in, so a group ripples into play. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float SpawnStagger = 0.5f;

	/** How far the spawn scale pop starts below full size (0 = no pop, 0.5 = starts at half size). It overshoots a little and settles in the first half of the spawn. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0", ClampMax = "0.95"))
	float SpawnPopAmount = 0.45f;

	/** Frames per second of the eight-frame idle (authored for 6). Each unit starts at a random point in it. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0.1"))
	float IdleFps = 6.f;

	/** Ground distance (cm) covered by one eight-frame run cycle (two steps). The frames were authored for 124; any other value makes the feet slide. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "10"))
	float WalkCycleDistance = 124.f;

	/** A unit shows the run cycle above this speed (cm/s) and drops back to idle below half of it. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "1"))
	float WalkSpeedThreshold = 40.f;

	/** The sprite keeps its facing row until the unit has turned this many degrees past the boundary between two of the eight rows. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0", ClampMax = "20"))
	float FacingHysteresisDeg = 8.f;

	/** Extra forward shove (cm) of the whole sprite on the strike frame, easing back during recovery. The frame itself already lunges about 13 cm. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float MeleeLungeDistance = 12.f;

	// ----------------------------------------------------------------- Units
	UPROPERTY(EditAnywhere, Config, Category = "Units")
	FSRUnitStats Shieldbearer;

	UPROPERTY(EditAnywhere, Config, Category = "Units")
	FSRUnitStats Archer;

	UPROPERTY(EditAnywhere, Config, Category = "Units")
	FSRUnitStats Horseman;

	UPROPERTY(EditAnywhere, Config, Category = "Units")
	FSRUnitStats Catapult;

	UPROPERTY(EditAnywhere, Config, Category = "Units")
	FSRUnitStats Builder;

	// -------------------------------------------------------------- Builders
	/** A builder works on a building from within this distance (cm) of its walls. */
	UPROPERTY(EditAnywhere, Config, Category = "Builders", meta = (ClampMin = "10"))
	float BuilderReach = 70.f;

	/** Each builder beyond the first adds this share of the normal build speed (outside the castle's zone the first
	 * builder gives the normal speed; inside it every builder speeds the work up by this much). */
	UPROPERTY(EditAnywhere, Config, Category = "Builders", meta = (ClampMin = "0"))
	float BuilderExtraSpeed = 0.5f;

	// -------------------------------------------------------- Castle upgrades
	/** The castle's top level (it starts at 1). */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings|Castle Upgrades", meta = (ClampMin = "1", ClampMax = "6"))
	int32 CastleMaxLevel = 3;

	/** Price of level 2; each level after costs this times the level it is raised from (level 3 = 2x). */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings|Castle Upgrades")
	FSRCost CastleUpgradeCost = FSRCost(300, 0);

	/** Seconds each level takes (builders at the walls speed it up). */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings|Castle Upgrades", meta = (ClampMin = "1"))
	float CastleUpgradeTime = 40.f;

	/** Housing each level adds. */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings|Castle Upgrades", meta = (ClampMin = "0"))
	int32 CastleUpgradePop = 8;

	/** Health each level adds. */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings|Castle Upgrades", meta = (ClampMin = "0"))
	float CastleUpgradeHealth = 3000.f;

	/** How much wider (cm) the building zone gets with each level. */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings|Castle Upgrades", meta = (ClampMin = "0"))
	float CastleUpgradeZone = 600.f;

	/** Most builders a kingdom may have (alive and in training). */
	UPROPERTY(EditAnywhere, Config, Category = "Builders", meta = (ClampMin = "0", ClampMax = "20"))
	int32 MaxBuilders = 2;

	/** Most builders that count on one building. */
	UPROPERTY(EditAnywhere, Config, Category = "Builders", meta = (ClampMin = "1"))
	int32 BuildersPerBuilding = 4;

	/** Health a builder restores per second on a damaged building. */
	UPROPERTY(EditAnywhere, Config, Category = "Builders", meta = (ClampMin = "0"))
	float BuilderRepairPerSecond = 28.f;

	/** An idle builder of yours goes to work on its own on a site or damaged building within this distance (cm).
	 * The enemy's builders look everywhere. 0 = never on their own. */
	UPROPERTY(EditAnywhere, Config, Category = "Builders", meta = (ClampMin = "0"))
	float BuilderAutoWorkRadius = 2600.f;

	// -------------------------------------------------------------- Scenario
	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	FLinearColor PlayerTeamColor = FLinearColor(0.05f, 0.22f, 0.8f);

	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	FLinearColor EnemyTeamColor = FLinearColor(0.72f, 0.07f, 0.05f);

	UPROPERTY(EditAnywhere, Config, Category = "Scenario", meta = (ClampMin = "0"))
	int32 PlayerShieldbearers = 3;

	UPROPERTY(EditAnywhere, Config, Category = "Scenario", meta = (ClampMin = "0"))
	int32 PlayerArchers = 2;

	UPROPERTY(EditAnywhere, Config, Category = "Scenario", meta = (ClampMin = "0"))
	int32 EnemyShieldbearers = 3;

	UPROPERTY(EditAnywhere, Config, Category = "Scenario", meta = (ClampMin = "0"))
	int32 EnemyArchers = 2;

	/** Centre of the player's starting formation (world XY, cm). */
	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	FVector2D PlayerStart = FVector2D(-5500.f, -5000.f);

	/** Centre of the hostile group (world XY, cm). */
	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	FVector2D EnemyStart = FVector2D(5500.f, 5000.f);

	/** Spawns three grey blocks so obstacle handling can be tested before real props exist. Turn off once the map has its own. */
	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	bool bSpawnGreyboxObstacles = false;

	// --------------------------------------------------------------- Economy
	// Farms make food, mines make gold. The barracks and archery range turn food into troops; gold is for buildings.
	UPROPERTY(EditAnywhere, Config, Category = "Economy", meta = (ClampMin = "0"))
	int32 StartingGold = 320;

	UPROPERTY(EditAnywhere, Config, Category = "Economy", meta = (ClampMin = "0"))
	int32 StartingFood = 200;

	/** Food each farm adds per payout. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Production", meta = (ClampMin = "0"))
	int32 FarmFoodPerPayout = 14;

	/** Seconds between a farm's payouts. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Production", meta = (ClampMin = "0.2"))
	float FarmPayoutInterval = 6.f;

	/** Gold each mine adds per payout. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Production", meta = (ClampMin = "0"))
	int32 MineGoldPerPayout = 10;

	/** Seconds between a mine's payouts. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Production", meta = (ClampMin = "0.2"))
	float MinePayoutInterval = 6.f;

	/** Troops are paid for in food only; gold is kept for buildings. (The cost struct still carries a gold field, left at 0.) */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment")
	FSRCost ShieldbearerCost = FSRCost(0, 100);

	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment")
	FSRCost ArcherCost = FSRCost(0, 85);

	/** Horse Riders and Catapults cost gold as well as food. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment")
	FSRCost HorsemanCost = FSRCost(40, 110);

	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment")
	FSRCost CatapultCost = FSRCost(120, 120);

	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment")
	/** Builders are dear: gold as well as food, and slow to train. */
	FSRCost BuilderCost = FSRCost(120, 80);

	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment", meta = (ClampMin = "0.1"))
	float BuilderBuildTime = 14.f;

	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment", meta = (ClampMin = "0.1"))
	float HorsemanBuildTime = 11.f;

	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment", meta = (ClampMin = "0.1"))
	float CatapultBuildTime = 18.f;

	/** Seconds the barracks takes to train one Shieldbearer. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment", meta = (ClampMin = "0.1"))
	float ShieldbearerBuildTime = 9.f;

	/** Seconds the archery range takes to train one Archer. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment", meta = (ClampMin = "0.1"))
	float ArcherBuildTime = 8.f;

	/** Recruits a barracks or range can have waiting (including the one in training). */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment", meta = (ClampMin = "1", ClampMax = "12"))
	int32 MaxRecruitQueue = 5;

	/** Clearance (cm) recruits and move orders keep from a building's footprint when they are routed round it. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Recruitment", meta = (ClampMin = "20"))
	float BuildingRouteMargin = 85.f;

	/** How long the "+N" over a building lives, and how far it floats up (cm). */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Feedback", meta = (ClampMin = "0.2"))
	float PayoutPopupTime = 1.5f;

	UPROPERTY(EditAnywhere, Config, Category = "Economy|Feedback", meta = (ClampMin = "0"))
	float PayoutPopupRise = 130.f;

	/** How long a resource counter flashes red and shakes when a purchase is refused. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Feedback", meta = (ClampMin = "0.05"))
	float InsufficientFlashTime = 0.55f;

	/** Selection outline round a building: line width (cm) and gap from the footprint. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Feedback", meta = (ClampMin = "2"))
	float BuildingRingWidth = 18.f;

	UPROPERTY(EditAnywhere, Config, Category = "Economy|Feedback", meta = (ClampMin = "0"))
	float BuildingRingGap = 34.f;

	/** Hard ceiling on a kingdom's population, however many buildings it has. */
	UPROPERTY(EditAnywhere, Config, Category = "Economy|Population", meta = (ClampMin = "1"))
	int32 MaxPopulation = 36;

	// ------------------------------------------------------------- Buildings
	UPROPERTY(EditAnywhere, Config, Category = "Buildings")
	FSRBuildingStats CastleStats;

	UPROPERTY(EditAnywhere, Config, Category = "Buildings")
	FSRBuildingStats FarmStats;

	UPROPERTY(EditAnywhere, Config, Category = "Buildings")
	FSRBuildingStats MineStats;

	UPROPERTY(EditAnywhere, Config, Category = "Buildings")
	FSRBuildingStats TowerStats;

	UPROPERTY(EditAnywhere, Config, Category = "Buildings")
	FSRBuildingStats BarracksStats;

	UPROPERTY(EditAnywhere, Config, Category = "Buildings")
	FSRBuildingStats RangeStats;

	UPROPERTY(EditAnywhere, Config, Category = "Buildings")
	FSRBuildingStats StableStats;

	UPROPERTY(EditAnywhere, Config, Category = "Buildings")
	FSRBuildingStats WorkshopStats;

	/** A finished building shows its battle-damaged model below this fraction of its health. */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings", meta = (ClampMin = "0", ClampMax = "1"))
	float DamagedStateFraction = 0.5f;

	/** Seconds the ruin of a building raised during the match lingers before it sinks away (the level's own stay until restart). */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings", meta = (ClampMin = "1"))
	float RuinLingerTime = 40.f;

	/** Gold refunded when a building is cancelled while still under construction (fraction of its cost). */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings", meta = (ClampMin = "0", ClampMax = "1"))
	float CancelRefund = 0.75f;

	/** A building under construction starts with this fraction of its health and gains the rest as it goes up. */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings", meta = (ClampMin = "0.05", ClampMax = "1"))
	float ConstructionStartHealth = 0.15f;

	/** Seconds a destroyed building takes to collapse into rubble (and the rubble lingers twice as long). */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings", meta = (ClampMin = "0.1"))
	float CollapseTime = 1.6f;

	/** Workers (miners at a mine, farmhands at a farm) shown going about their work. Cosmetic; payouts land when they deliver. */
	UPROPERTY(EditAnywhere, Config, Category = "Buildings", meta = (ClampMin = "0", ClampMax = "6"))
	int32 WorkersPerBuilding = 2;

	const FSRBuildingStats& BuildingStatsFor(ESRBuildingType Type) const
	{
		switch (Type)
		{
		case ESRBuildingType::Castle: return CastleStats;
		case ESRBuildingType::Farm: return FarmStats;
		case ESRBuildingType::Mine: return MineStats;
		case ESRBuildingType::Barracks: return BarracksStats;
		case ESRBuildingType::Range: return RangeStats;
		case ESRBuildingType::Stable: return StableStats;
		case ESRBuildingType::Workshop: return WorkshopStats;
		default: return TowerStats;
		}
	}

	/** Every building type, in build-menu order. */
	static const TArray<ESRBuildingType>& AllBuildingTypes()
	{
		static const TArray<ESRBuildingType> Types = { ESRBuildingType::Farm, ESRBuildingType::Mine, ESRBuildingType::Barracks, ESRBuildingType::Range,
			ESRBuildingType::Stable, ESRBuildingType::Workshop, ESRBuildingType::Tower, ESRBuildingType::Castle };
		return Types;
	}

	/** The building that trains a unit type. */
	static ESRBuildingType TrainerOf(ESRUnitType Type)
	{
		switch (Type)
		{
		case ESRUnitType::Archer: return ESRBuildingType::Range;
		case ESRUnitType::Horseman: return ESRBuildingType::Stable;
		case ESRUnitType::Catapult: return ESRBuildingType::Workshop;
		case ESRUnitType::Builder: return ESRBuildingType::Castle;
		default: return ESRBuildingType::Barracks;
		}
	}

	// ------------------------------------------------------------------ Grid
	/** Build grid cell size (cm). Buildings snap to it; the pathfinder walks it. */
	UPROPERTY(EditAnywhere, Config, Category = "Grid", meta = (ClampMin = "50", ClampMax = "400"))
	float GridCellSize = 100.f;

	/** Ground under a building may vary by at most this much (cm) across its footprint. */
	UPROPERTY(EditAnywhere, Config, Category = "Grid", meta = (ClampMin = "0"))
	float BuildFlatTolerance = 30.f;

	/** Free cells kept between two buildings (so troops can always walk between them). */
	UPROPERTY(EditAnywhere, Config, Category = "Grid", meta = (ClampMin = "0", ClampMax = "4"))
	int32 BuildingGapCells = 1;

	/** A mine must be placed with its centre within this distance (cm) of a free gold vein; it snaps onto the vein. */
	UPROPERTY(EditAnywhere, Config, Category = "Grid", meta = (ClampMin = "50"))
	float VeinSnapRadius = 900.f;

	/** Extra path cost for walking next to an obstacle: keeps routes off walls and out of tight gaps. */
	UPROPERTY(EditAnywhere, Config, Category = "Grid", meta = (ClampMin = "0"))
	float PathWallPenalty = 1.5f;

	/** Draw the walkability grid and the last paths (debug). */
	UPROPERTY(EditAnywhere, Config, Category = "Grid")
	bool bDebugDrawPaths = false;

	// -------------------------------------------------------------------- AI
	/** 0 Easy, 1 Normal, 2 Hard: the commander's profile (USRAISubsystem::Profile): its income share (60% / 90% / 100%),
	 * attack timing, size and odds, raids, adapting. No map cheats or bonus resources at any level. */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "0", ClampMax = "2"))
	int32 AIDifficulty = 1;

	/** Seconds between the commander's decisions. */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "0.1"))
	float AIThinkInterval = 0.75f;

	/** The first main attack leaves no earlier than this (seconds into the match), at Normal (Easy x1.75, Hard x0.6). */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "0"))
	float AIFirstWaveTime = 240.f;

	/** Seconds the commander regroups after an attack ends before it may launch the next, at Normal (Easy x1.7, Hard x0.45). */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "10"))
	float AIWaveInterval = 90.f;

	/** Troops in the first wave, growth per wave, and the most a wave will ever wait for. */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "1"))
	int32 AIWaveSizeStart = 7;

	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "0"))
	int32 AIWaveGrowth = 3;

	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "1"))
	int32 AIWaveSizeMax = 30;

	/** Share of the army kept home as a garrison when a wave leaves. */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "0", ClampMax = "0.9"))
	float AIGarrisonFraction = 0.2f;

	/** Enemies within this distance (cm) of any of the commander's buildings make it defend with everything at home. */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "500"))
	float AIDefendRadius = 3200.f;

	/** A wave falls back home when it is down to this fraction of its strength and outnumbered where it fights. */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "0", ClampMax = "1"))
	float AIRetreatFraction = 0.3f;

	/** Share of Shieldbearers the commander aims for (the rest are Archers). */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "0", ClampMax = "1"))
	float AIShieldRatio = 0.55f;

	/** The commander attacks once its free army is this many times stronger than what it expects to meet at the target (Normal; Easy x1.35, Hard x0.77). */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "0.5"))
	float AIAttackAdvantage = 1.5f;

	/** Smallest force (troops) it sends on a main attack, and on a raid of an undefended farm or mine. */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "1"))
	int32 AIMinAttackSize = 4;

	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "1"))
	int32 AIRaidSize = 3;

	/** Seconds between raids (Normal; Hard x0.5; Easy never raids). */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "10"))
	float AIRaidInterval = 120.f;

	/** How far (cm) the commander's troops and buildings see. It only knows what it has seen (and remembers it for AIMemoryTime). */
	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "500"))
	float AISightRadius = 2600.f;

	UPROPERTY(EditAnywhere, Config, Category = "AI", meta = (ClampMin = "5"))
	float AIMemoryTime = 90.f;

	/** What the commander builds, in order, as gold allows (it repeats the list's farms / mines / towers after it ends). */
	UPROPERTY(EditAnywhere, Config, Category = "AI")
	TArray<ESRBuildingType> AIBuildOrder;

	/** Let a commander play the player's side too (balance testing: sr.AIvsAI 1). */
	UPROPERTY(EditAnywhere, Config, Category = "AI")
	bool bAIPlaysPlayer = false;

	/** Seconds between autosaves while a match is played (0 = never). The pause menu also saves by hand. */
	UPROPERTY(EditAnywhere, Config, Category = "Saves", meta = (ClampMin = "0"))
	float AutosaveInterval = 120.f;

	// ------------------------------------------------------------------- Fog
	/** Fog of war for the player: enemy troops show only in sight, enemy buildings once seen (USRFogSubsystem). */
	UPROPERTY(EditAnywhere, Config, Category = "Fog")
	bool bFogOfWar = true;

	/** Fog grid cell (cm). */
	UPROPERTY(EditAnywhere, Config, Category = "Fog", meta = (ClampMin = "25"))
	float FogCellSize = 125.f;

	UPROPERTY(EditAnywhere, Config, Category = "Fog", meta = (ClampMin = "0.03"))
	float FogUpdateInterval = 0.12f;

	/** Seconds a cell takes to clear or fog over (soft edges as troops move). */
	UPROPERTY(EditAnywhere, Config, Category = "Fog", meta = (ClampMin = "0"))
	float FogFadeTime = 0.5f;

	/** How dark the fog is drawn (0 = not drawn, 1 = full). */
	UPROPERTY(EditAnywhere, Config, Category = "Fog", meta = (ClampMin = "0", ClampMax = "1"))
	float FogStrength = 1.f;

	// -------------------------------------------------------------- Platoons
	UPROPERTY(EditAnywhere, Config, Category = "Platoons", meta = (ClampMin = "1", ClampMax = "9"))
	int32 MaxPlatoons = 6;

	/** Each platoon has its own colour: a ring under every member and a numbered tag over the platoon. */
	UPROPERTY(EditAnywhere, Config, Category = "Platoons")
	bool bShowPlatoonColors = true;

	/** Defensive stance: how far (cm) units chase before returning to where they were posted. */
	UPROPERTY(EditAnywhere, Config, Category = "Platoons", meta = (ClampMin = "100"))
	float DefensiveChaseDistance = 900.f;

	// ----------------------------------------------------------------- Audio
	UPROPERTY(EditAnywhere, Config, Category = "Audio", meta = (ClampMin = "0", ClampMax = "1"))
	float MasterVolume = 0.9f;

	UPROPERTY(EditAnywhere, Config, Category = "Audio", meta = (ClampMin = "0", ClampMax = "1"))
	float EffectsVolume = 0.85f;

	UPROPERTY(EditAnywhere, Config, Category = "Audio", meta = (ClampMin = "0", ClampMax = "1"))
	float UIVolume = 0.7f;

	UPROPERTY(EditAnywhere, Config, Category = "Audio", meta = (ClampMin = "0", ClampMax = "1"))
	float AmbientVolume = 0.45f;

	UPROPERTY(EditAnywhere, Config, Category = "Audio", meta = (ClampMin = "0", ClampMax = "1"))
	float MusicVolume = 0.35f;

	/** Every battle sound has its own hearing range (a sword clash carries less far than a collapsing tower); this
	 * scales them all. A sound fades smoothly to silence at the edge of its range, measured from a listener over the
	 * camera's focus that rises as the camera zooms out (so small sounds drop away first). */
	UPROPERTY(EditAnywhere, Config, Category = "Audio", meta = (ClampMin = "0.2", ClampMax = "4"))
	float SoundRangeScale = 1.f;

	/** How high (as a share of the camera's zoom distance) the listener sits over the focus point. */
	UPROPERTY(EditAnywhere, Config, Category = "Audio", meta = (ClampMin = "0", ClampMax = "1"))
	float ListenerZoomHeight = 0.25f;

	const FSRCost& CostFor(ESRUnitType Type) const
	{
		switch (Type)
		{
		case ESRUnitType::Archer: return ArcherCost;
		case ESRUnitType::Horseman: return HorsemanCost;
		case ESRUnitType::Catapult: return CatapultCost;
		case ESRUnitType::Builder: return BuilderCost;
		default: return ShieldbearerCost;
		}
	}
	float BuildTimeFor(ESRUnitType Type) const
	{
		switch (Type)
		{
		case ESRUnitType::Archer: return ArcherBuildTime;
		case ESRUnitType::Horseman: return HorsemanBuildTime;
		case ESRUnitType::Catapult: return CatapultBuildTime;
		case ESRUnitType::Builder: return BuilderBuildTime;
		default: return ShieldbearerBuildTime;
		}
	}

	// --------------------------------------------------------------- Visuals
	// Troop sprites: /Game/SR/Materials/M_UnitSprite on a camera-facing card. The three look values below are pushed
	// into the shared material instances every frame, so they can be tuned while PIE runs.
	/** How much of the sprite the scene lights and shadows (0 = the baked look only, unaffected by sun or shade; 1 = fully lit like the world). */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Sprites", meta = (ClampMin = "0", ClampMax = "1"))
	float SpriteRelight = 0.6f;

	/** Brightness of the baked (emissive) share. Balanced by eye against the sun: too high and troops glow in shade, too low and they go muddy. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Sprites", meta = (ClampMin = "0"))
	float SpriteBakedLight = 3.f;

	/** 1 = the sprite's own per-pixel normals shape the scene light; 0 = one even normal for the whole figure (halfway between up and the camera). */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Sprites", meta = (ClampMin = "0", ClampMax = "1"))
	float SpriteNormalStrength = 0.7f;

	/** Width, in screen pixels, over which each sprite texel edge is anti-aliased. 0 = hard point sampling (crawls a little as units move), 1 = as soft as the world textures. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Sprites", meta = (ClampMin = "0", ClampMax = "2"))
	float SpriteEdgeSoftness = 0.5f;

	/** Each troop casts the silhouette of its current frame from the sun, through a hidden shadow-only card. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Sprites")
	bool bSpriteShadows = true;

	/** How far the shadow card leans away from the sun, degrees from upright. The cast shadow on flat ground is the same at any value; a card lying
	 *  nearly flat (the default) cannot shade the troop's own sprite and keeps the shadow crisp, an upright one also falls across neighbours. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Sprites", meta = (ClampMin = "0", ClampMax = "88"))
	float SpriteShadowLean = 78.f;

	/** Strength of the stepped contact shadow under each troop (0 = off). */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Sprites", meta = (ClampMin = "0", ClampMax = "1"))
	float SpriteBlobStrength = 0.75f;

	/** Miniature / tilt-shift depth of field on the game camera. The focus plane is locked to the camera's focus point, so it follows pan and zoom. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Tilt Shift")
	bool bTiltShift = true;

	/** Blur strength when fully zoomed OUT: the blur-disc diameter, as a percentage of screen width, of something infinitely far behind the focus point. Kept low enough that a troop standing at the top or bottom edge of the view is blurred by no more than about one of its own sprite pixels; the default zoom sits between this and the zoomed-in value. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Tilt Shift", meta = (ClampMin = "0", ClampMax = "20"))
	float TiltShiftBlur = 0.6f;

	/** Blur strength when fully zoomed IN (same unit). The close, low camera sees a deep slice of the field, so this is what sets how soft the foreground props and the hazy distance get in the cinematic view. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Tilt Shift", meta = (ClampMin = "0", ClampMax = "20"))
	float TiltShiftBlurZoomedIn = 0.8f;

	/** Moves the sharp plane (cm) nearer (-) or farther (+) than the camera focus point. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Tilt Shift")
	float TiltShiftFocusOffset = 0.f;

	/** Same, as a fraction of the camera-to-focus distance so it holds at every zoom (-0.05 = 5% nearer). Slightly negative shares the sharp band between the focus point and the troops in the bottom of the frame. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Tilt Shift", meta = (ClampMin = "-0.5", ClampMax = "0.5"))
	float TiltShiftFocusBias = -0.04f;

	/** Aperture used for the bokeh shape only (blur size is set by Tilt Shift Blur). */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Tilt Shift", meta = (ClampMin = "1", ClampMax = "22"))
	float TiltShiftFstop = 1.4f;

	// Distance haze. The level's Exponential Height Fog starts just past the focus point, whatever the zoom,
	// so the troops in the sharp band stay clear while everything up-screen sinks into lit haze (and light shafts).
	/** Camera drives the fog start distance from its focus distance. Untick to leave the fog actor's own values alone. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Haze")
	bool bHazeTracksFocus = true;

	/** Where the haze begins, as a fraction of the camera-to-focus distance (1 = exactly at the focus point). */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Haze", meta = (ClampMin = "0", ClampMax = "4"))
	float HazeStartFraction = 1.05f;

	/** Distance over which the haze fades in past its start, as a fraction of the camera-to-focus distance. */
	UPROPERTY(EditAnywhere, Config, Category = "Visuals|Haze", meta = (ClampMin = "0", ClampMax = "4"))
	float HazeFadeFraction = 0.7f;

	// ----------------------------------------------------------------- Debug
	/** Log every hit to LogSovereign (deaths and battle results are always logged). */
	UPROPERTY(EditAnywhere, Config, Category = "Debug")
	bool bLogHits = true;

	/** Start straight in a match instead of on the title screen (also: the -SRSkipMenu switch, or sr.StartMatch). */
	UPROPERTY(EditAnywhere, Config, Category = "Debug")
	bool bSkipMainMenu = false;
};
