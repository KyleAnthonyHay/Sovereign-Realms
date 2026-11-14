// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Common/SRTypes.h"

/** The six animation blocks of a troop sprite sheet (SourceArt/Characters/SPRITE_SPEC.md). */
enum class ESRSpriteAnim : uint8
{
	Spawn,
	Idle,
	Walk,
	Attack,
	Hit,
	Death,
	Count
};

/**
 * Layout and timing data of one troop's sprite sheet. Every number is copied from
 * SourceArt/Characters/<name>.json; if the sheets are re-rendered with another layout, update SRSprite.cpp.
 */
struct FSRSpriteSheet
{
	struct FAnim
	{
		int32 Col = 0;      // first column of the block
		int32 Row = 0;      // first row of the block (facing S); add the facing index
		int32 Frames = 1;
	};

	FAnim Anims[int32(ESRSpriteAnim::Count)];

	/** Attack: frames 0 .. StrikeFrame-1 are the wind-up, StrikeFrame .. last are the recovery. */
	int32 StrikeFrame = 3;
	/** Fraction of WindupTime at which each wind-up frame starts. */
	TArray<float, TInlineAllocator<8>> WindupMap;
	/** Fraction of RecoveryTime at which each recovery frame starts. The first is 0: the strike frame is on screen the moment Strike() runs. */
	TArray<float, TInlineAllocator<8>> RecoveryMap;

	/** Top of the standing figure above the pivot, measured on the card (cm in the view plane). For health bars and picking. */
	float TopCm = 140.f;
	/** Where a projectile leaves, in character space: forward, right, up from the feet (cm). */
	FVector MuzzleCm = FVector::ZeroVector;

	const FAnim& Anim(ESRSpriteAnim A) const { return Anims[int32(A)]; }
	int32 AttackFrame(ESRAttackPhase Phase, float Phase01) const;

	static const FSRSpriteSheet& For(ESRUnitType Type);
};

namespace SRSprite
{
	/** Camera elevation the sheets were rendered from, degrees above the horizon. */
	constexpr float RenderElevationDeg = 30.f;
	constexpr int32 NumFacings = 8;

	// Custom primitive data slots read by M_UnitSprite / M_UnitSpriteShadow (Tools/build_visual_materials.py).
	constexpr int32 DataFrame = 0;      // x = column, y = row, z = HitFlash, w = Fade
	constexpr int32 DataTeamColor = 4;  // rgb

	/**
	 * Row offset inside an animation block for a unit facing UnitYaw, seen by a viewer looking along ViewYaw
	 * (the camera, or the sun for the shadow card). Order: S, SW, W, NW, N, NE, E, SE; S faces the viewer.
	 */
	int32 FacingIndex(float UnitYaw, float ViewYaw);

	/** Same, but keeps Current until the yaw is HysteresisDeg past the boundary, so a unit does not flicker between two rows. */
	int32 FacingIndexSticky(int32 Current, float UnitYaw, float ViewYaw, float HysteresisDeg);
}

/** What every sprite needs to know about the camera and the sun this frame. Filled once per frame by USRBattleSubsystem. */
struct FSRSpriteView
{
	/** The camera's rotation. A card with this rotation is parallel to the view plane: X = view forward, Y = screen right, Z = screen up. */
	FQuat CardRotation = FQuat::Identity;

	/**
	 * Significance: sprites further than CullRadius from the camera's focus are off screen. They are hidden (card,
	 * shadow, contact shadow) and skip their per-frame presentation work entirely until they come back into view.
	 */
	FVector2D FocusXY = FVector2D::ZeroVector;
	float CullRadius = 1.e9f;
	FVector ViewForward = FVector::ForwardVector;
	FVector ViewUp = FVector::UpVector;
	float ViewYaw = 0.f;

	/**
	 * The sheets were rendered from 30 degrees; the card shows them unchanged at any camera pitch. A point at authored height H
	 * above the feet therefore appears where a world point at H * HeightScale would. Used for the arrow origin and aim points.
	 */
	float HeightScale = 1.f;

	/** Direction the sunlight travels, and its yaw. */
	FVector SunDir = FVector(0.22f, 0.81f, -0.54f);
	float SunYaw = 75.f;

	/** Rotation and scale of the hidden shadow card: the frame as the sun sees it, laid on a plane leaning away from the sun. */
	FQuat ShadowRotation = FQuat::Identity;
	FVector ShadowScale = FVector::OneVector;
};
