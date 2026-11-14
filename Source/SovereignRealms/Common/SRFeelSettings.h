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

	const FSRUnitStats& StatsFor(ESRUnitType Type) const { return Type == ESRUnitType::Archer ? Archer : Shieldbearer; }

	// ---------------------------------------------------------------- Camera
	/** World yaw the camera looks along. 0 = +X is "up the screen". */
	UPROPERTY(EditAnywhere, Config, Category = "Camera")
	float CameraYaw = 0.f;

	/** Narrow FOV flattens perspective for the miniature / diorama look. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera", meta = (ClampMin = "10", ClampMax = "100"))
	float CameraFOV = 38.f;

	/** Camera distance from the focus point when fully zoomed in. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "200"))
	float ZoomDistanceMin = 1300.f;

	/** Camera distance from the focus point when fully zoomed out. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "200"))
	float ZoomDistanceMax = 4800.f;

	/** 0 = fully in, 1 = fully out. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "0", ClampMax = "1"))
	float ZoomDefault = 0.55f;

	/** Zoom fraction per mouse-wheel notch. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "0.01", ClampMax = "1"))
	float ZoomStep = 0.11f;

	/** Time constant of the zoom ease. Smaller = snappier. */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "0.001"))
	float ZoomSmoothTime = 0.11f;

	/** Pitch when fully zoomed in (lower / more side-on). */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "-89", ClampMax = "-10"))
	float PitchZoomedIn = -43.f;

	/** Pitch when fully zoomed out (steeper / more top-down). */
	UPROPERTY(EditAnywhere, Config, Category = "Camera|Zoom", meta = (ClampMin = "-89", ClampMax = "-10"))
	float PitchZoomedOut = -60.f;

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
	FVector2D MapHalfExtent = FVector2D(3000.f, 3000.f);

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

	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Reaction")
	FLinearColor HitFlashColor = FLinearColor(1.f, 0.92f, 0.85f);

	/** Squash amount on hit (0.2 = 20% shorter, slightly wider). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Hit Reaction", meta = (ClampMin = "0", ClampMax = "0.6"))
	float HitSquash = 0.2f;

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

	UPROPERTY(EditAnywhere, Config, Category = "Combat|AI")
	bool bEnemyLeash = true;

	/** Seconds a health bar stays visible after the unit was last damaged (selected / hovered units always show it). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Health Bars", meta = (ClampMin = "0"))
	float HealthBarLingerTime = 4.f;

	UPROPERTY(EditAnywhere, Config, Category = "Combat|Health Bars")
	FVector2D HealthBarSize = FVector2D(44.f, 5.f);

	/** HUD overlay is authored for a 1080p-tall view and scaled with the viewport (so it stays readable on Retina). Extra multiplier here. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Health Bars", meta = (ClampMin = "0.25"))
	float HUDScale = 1.f;

	/** Seconds for the body to topple over. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Death", meta = (ClampMin = "0.05"))
	float DeathToppleTime = 0.42f;

	/** Seconds the corpse lies there before it starts sinking. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Death", meta = (ClampMin = "0"))
	float CorpseLingerTime = 2.2f;

	/** Seconds the corpse takes to sink / fade before removal. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Death", meta = (ClampMin = "0.05"))
	float CorpseSinkTime = 1.3f;

	// ------------------------------------------------------------- Animation
	/** Seconds of the spawn pop-in. Units are not selectable or active until it ends. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0.01"))
	float SpawnPopTime = 0.38f;

	/** Random extra delay before each unit pops in, so a group ripples into play. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float SpawnStagger = 0.5f;

	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float BreathAmount = 0.022f;

	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float BreathRate = 2.3f;

	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float WalkBobHeight = 8.f;

	/** Ground distance (cm) per step; sets the bob / waddle cadence. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "5"))
	float StrideLength = 62.f;

	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float WalkLeanDeg = 9.f;

	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float WalkWaddleDeg = 5.f;

	/** Forward lunge distance (cm) of a melee strike. */
	UPROPERTY(EditAnywhere, Config, Category = "Animation", meta = (ClampMin = "0"))
	float MeleeLungeDistance = 30.f;

	// ----------------------------------------------------------------- Units
	UPROPERTY(EditAnywhere, Config, Category = "Units")
	FSRUnitStats Shieldbearer;

	UPROPERTY(EditAnywhere, Config, Category = "Units")
	FSRUnitStats Archer;

	// -------------------------------------------------------------- Scenario
	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	FLinearColor PlayerTeamColor = FLinearColor(0.05f, 0.22f, 0.8f);

	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	FLinearColor EnemyTeamColor = FLinearColor(0.72f, 0.07f, 0.05f);

	UPROPERTY(EditAnywhere, Config, Category = "Scenario", meta = (ClampMin = "0"))
	int32 PlayerShieldbearers = 6;

	UPROPERTY(EditAnywhere, Config, Category = "Scenario", meta = (ClampMin = "0"))
	int32 PlayerArchers = 6;

	UPROPERTY(EditAnywhere, Config, Category = "Scenario", meta = (ClampMin = "0"))
	int32 EnemyShieldbearers = 5;

	UPROPERTY(EditAnywhere, Config, Category = "Scenario", meta = (ClampMin = "0"))
	int32 EnemyArchers = 3;

	/** Centre of the player's starting formation (world XY, cm). */
	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	FVector2D PlayerStart = FVector2D(-1300.f, 0.f);

	/** Centre of the hostile group (world XY, cm). */
	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	FVector2D EnemyStart = FVector2D(1500.f, 200.f);

	/** Spawns three grey blocks so obstacle handling can be tested before real props exist. Turn off once the map has its own. */
	UPROPERTY(EditAnywhere, Config, Category = "Scenario")
	bool bSpawnGreyboxObstacles = true;

	// ----------------------------------------------------------------- Debug
	/** Log every hit to LogSovereign (deaths and battle results are always logged). */
	UPROPERTY(EditAnywhere, Config, Category = "Debug")
	bool bLogHits = true;

	/** Show the controls reminder in the top-left corner. */
	UPROPERTY(EditAnywhere, Config, Category = "Debug")
	bool bShowControlsHint = true;
};
