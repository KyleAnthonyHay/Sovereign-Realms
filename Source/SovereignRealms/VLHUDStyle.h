#pragma once

#include "CoreMinimal.h"

/**
 * The interface's palette, carried over one to one from the main game (SRHUDStyle.h): dark navy / charcoal
 * translucent panels, restrained bronze and gold trim, warm parchment for text and tooltips, team blue / enemy red
 * accents. Every colour here (and every colour written in the HUD code) is sRGB, "as it should look"; the HUD's
 * primitives convert to linear on the way to the canvas.
 */
namespace VLStyle
{
	const FLinearColor PanelFill(0.022f, 0.032f, 0.058f, 0.90f);
	const FLinearColor PanelSheen(0.050f, 0.070f, 0.115f, 0.90f);
	const FLinearColor Inset(0.010f, 0.014f, 0.026f, 0.85f);
	const FLinearColor Bronze(0.36f, 0.25f, 0.10f, 1.f);
	const FLinearColor Gold(0.86f, 0.66f, 0.26f, 1.f);
	const FLinearColor GoldBright(1.f, 0.86f, 0.45f, 1.f);
	const FLinearColor Parchment(0.93f, 0.89f, 0.78f, 1.f);
	const FLinearColor ParchmentFill(0.80f, 0.73f, 0.56f, 0.97f);
	const FLinearColor Ink(0.045f, 0.030f, 0.018f, 1.f);
	const FLinearColor Dim(0.60f, 0.61f, 0.62f, 1.f);
	/** Patrols, everywhere they are drawn (the route lines, the minimap, a ship's course): violet, clear of the moves'
	 *  blue and the attacks' red (the owner, 2026-11-24). */
	const FLinearColor PatrolViolet(0.80f, 0.45f, 1.f, 0.95f);
	const FLinearColor Refuse(1.f, 0.26f, 0.17f, 1.f);
	const FLinearColor Amber(1.f, 0.62f, 0.16f, 1.f);
	const FLinearColor Good(0.35f, 0.85f, 0.32f, 1.f);
	const FLinearColor FoodColor(0.93f, 0.80f, 0.36f, 1.f);
	const FLinearColor ButtonFill(0.060f, 0.085f, 0.145f, 0.96f);
	const FLinearColor ButtonHot(0.115f, 0.160f, 0.270f, 0.98f);
	const FLinearColor ButtonOff(0.040f, 0.046f, 0.060f, 0.92f);
	const FLinearColor TeamBlue(0.22f, 0.48f, 1.f, 1.f);
	const FLinearColor TeamRed(0.95f, 0.22f, 0.15f, 1.f);

	// world-space colours of the main game (USRFeelSettings defaults; these are linear, drawn as lines)
	const FLinearColor SelectionRing(0.25f, 1.f, 0.35f, 1.f);
	const FLinearColor HoverRing(0.9f, 0.9f, 0.8f, 0.8f);
	const FLinearColor EnemyRing(1.f, 0.16f, 0.1f, 1.f);
	const FLinearColor SightCircle(0.55f, 0.85f, 1.f, 0.55f);
	const FLinearColor RangeCircle(1.f, 0.55f, 0.18f, 0.85f);
	const FLinearColor BoxFill(0.3f, 1.f, 0.4f, 0.10f);
	const FLinearColor BoxLine(0.45f, 1.f, 0.5f, 0.9f);
	constexpr float HealthBarLinger = 3.f;          // seconds a unit's bar stays up after its health changed...
	constexpr float HealthBarFade = 0.8f;           // ...then it fades over this
	constexpr float HealthBarRed = 0.34f;           // below this share (in the red) it always shows
	constexpr float HealthBarW = 44.f, HealthBarH = 5.f;
	constexpr float DamagedFraction = 0.5f;         // "badly damaged" below this

	inline FLinearColor A(FLinearColor C, float Alpha) { C.A *= Alpha; return C; }
	/** A count-down as a clock face: 75.2 s -> "1:16" (rounded up, so it reads 0:01 until the moment it is done). */
	inline FString Countdown(float Seconds)
	{
		const int32 S = FMath::Max(FMath::CeilToInt(Seconds), 0);
		return S >= 3600 ? FString::Printf(TEXT("%d:%02d:%02d"), S / 3600, (S / 60) % 60, S % 60) : FString::Printf(TEXT("%d:%02d"), S / 60, S % 60);
	}
	/** Green -> amber -> red as a health fraction drops. */
	inline FLinearColor Health(float Frac)
	{
		return Frac > 0.5f
			? FMath::Lerp(FLinearColor(0.95f, 0.75f, 0.1f), FLinearColor(0.2f, 0.9f, 0.25f), (Frac - 0.5f) * 2.f)
			: FMath::Lerp(FLinearColor(0.9f, 0.12f, 0.08f), FLinearColor(0.95f, 0.75f, 0.1f), Frac * 2.f);
	}
	/** A platoon's own colour (USRPlatoonSubsystem::PlatoonColor): bright, far apart from each other and from the
	 *  team blue / red and the green selection ring. */
	inline FLinearColor PlatoonColor(int32 Index)
	{
		static const FLinearColor Colors[9] = {
			FLinearColor(1.00f, 0.78f, 0.12f), FLinearColor(0.15f, 0.90f, 1.00f), FLinearColor(1.00f, 0.30f, 0.85f),
			FLinearColor(1.00f, 0.48f, 0.10f), FLinearColor(0.96f, 0.96f, 0.96f), FLinearColor(0.62f, 0.45f, 1.00f),
			FLinearColor(1.00f, 0.62f, 0.68f), FLinearColor(0.20f, 0.78f, 0.62f), FLinearColor(0.78f, 1.00f, 0.22f) };
		return Colors[((Index % 9) + 9) % 9];
	}
}

/** Button ids: each Button() drawn in a frame needs its own (hover animation and drags are keyed by it). */
namespace VLId
{
	enum : uint32
	{
		Pause = 1, Help, Minimap, PlatoonHeader, LegendClose, Upgrade, CastleCard, SendOut, FollowMe,
		Command = 20,     // + 0..19
		Recruit = 40,     // + 0 the building's troop
		Slot = 100,       // + platoon * 5 + {0 row, 1 formation, 2 stance, 3 (unused), 4 disband}
		JoinPlatoon = 220,// + 0 none, 1.. platoon (a training building's panel)
		Build = 240,      // + 0 the Build button, 1..3 the menu's tabs, 4..9 its cards (VLHUDBuild.cpp)
		SiteCancel = 252, Demolish, RecruitBuilder, Rotate, ClaimMine,
		TopChip = 260,    // + 0 the hero, 1 the Builders, 2 the Spy (the top bar)
		ChipRow = 264,    // + 0 "all of them", 1.. a Builder / the Spy (the list under the Builders' and the Spy's chip)
		Assign = 292,     // + platoon 0..5 (the command card's Assign picker)
		Menu = 300,       // + entry
		Screen = 340,     // + control on a sub-screen
		Setting = 400,    // + row
		Ship = 500,       // the troop ship's Unload (VLTroopShipHUD.cpp)
		CornerRepair = 510 // the castle panel's Repair of its corners (VLHUDGame.cpp); + 1, 2: the hero box's other heroes
	};
}
