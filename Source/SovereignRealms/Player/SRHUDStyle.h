// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"

/**
 * The interface's palette (PLAN.md, "Camera and interface"): dark navy / charcoal translucent panels, restrained
 * bronze and gold trim, warm parchment for text and tooltips, team blue / enemy red accents. Change a colour here
 * and every panel, menu and world-space bar follows.
 */
namespace SRStyle
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
	const FLinearColor Refuse(1.f, 0.26f, 0.17f, 1.f);
	const FLinearColor Amber(1.f, 0.62f, 0.16f, 1.f);
	const FLinearColor Good(0.35f, 0.85f, 0.32f, 1.f);
	const FLinearColor FoodColor(0.93f, 0.80f, 0.36f, 1.f);
	const FLinearColor ButtonFill(0.060f, 0.085f, 0.145f, 0.96f);
	const FLinearColor ButtonHot(0.115f, 0.160f, 0.270f, 0.98f);
	const FLinearColor ButtonOff(0.040f, 0.046f, 0.060f, 0.92f);
	const FLinearColor TeamBlue(0.22f, 0.48f, 1.f, 1.f);
	const FLinearColor TeamRed(0.95f, 0.22f, 0.15f, 1.f);

	inline FLinearColor A(FLinearColor C, float Alpha) { C.A *= Alpha; return C; }
	/** Green -> amber -> red as a health fraction drops. */
	inline FLinearColor Health(float Frac)
	{
		return Frac > 0.5f
			? FMath::Lerp(FLinearColor(0.95f, 0.75f, 0.1f), FLinearColor(0.2f, 0.9f, 0.25f), (Frac - 0.5f) * 2.f)
			: FMath::Lerp(FLinearColor(0.9f, 0.12f, 0.08f), FLinearColor(0.95f, 0.75f, 0.1f), Frac * 2.f);
	}
}

/** Button ids: each Button() drawn in a frame needs its own (hover animation and drags are keyed by it). */
namespace SRId
{
	enum : uint32
	{
		Pause = 1, Help, Minimap, PlatoonHeader, CancelBuild, LegendClose, Builders, Upgrade,
		Build = 10,       // + 0 toggle, 1..3 tabs, 4..9 entries
		Command = 20,     // + 0..8
		Recruit = 30,     // + 0..1
		Slot = 100,       // + platoon * 5 + {0 row, 1 formation, 2 stance, 3 recruits, 4 disband}
		Menu = 300,       // + entry
		Screen = 340,     // + control on a sub-screen
		Setting = 400,    // + row
		BuilderRow = 200  // + builder in the top bar's list
	};
}
