// Copyright Sovereign Realms.

#include "Units/SRSprite.h"

namespace
{
	// Sheet layout shared by both troops: six blocks of 8 columns x 8 rows, three across and two down.
	//   rows 0-7:  spawn (cols 0-7), idle (8-15), walk (16-23)      rows 8-15: attack, hit, death
	FSRSpriteSheet MakeSheet()
	{
		FSRSpriteSheet S;
		S.Anims[int32(ESRSpriteAnim::Spawn)] = { 0, 0, 6 };
		S.Anims[int32(ESRSpriteAnim::Idle)] = { 8, 0, 8 };
		S.Anims[int32(ESRSpriteAnim::Walk)] = { 16, 0, 8 };
		S.Anims[int32(ESRSpriteAnim::Attack)] = { 0, 8, 8 };
		S.Anims[int32(ESRSpriteAnim::Hit)] = { 8, 8, 3 };
		S.Anims[int32(ESRSpriteAnim::Death)] = { 16, 8, 8 };
		return S;
	}

	FSRSpriteSheet MakeShieldbearer()
	{
		// shieldbearer.json: strike_frame 3, windup_phase_map, recovery_phase_map, figure_top_row 38, pivot row 118, 1.75 cm per px.
		FSRSpriteSheet S = MakeSheet();
		S.StrikeFrame = 3;
		S.WindupMap = { 0.f, 0.30f, 0.62f };
		S.RecoveryMap = { 0.f, 0.22f, 0.42f, 0.62f, 0.82f };
		S.TopCm = (118 - 38) * 1.75f;
		return S;
	}

	FSRSpriteSheet MakeArcher()
	{
		// archer.json: strike (release) frame 5, figure_top_row 53, projectile_origin_cm (62, 0, 98).
		FSRSpriteSheet S = MakeSheet();
		S.StrikeFrame = 5;
		S.WindupMap = { 0.f, 0.18f, 0.38f, 0.58f, 0.80f };
		S.RecoveryMap = { 0.f, 0.34f, 0.68f };
		S.TopCm = (118 - 53) * 1.75f;
		S.MuzzleCm = FVector(62.f, 0.f, 98.f);
		return S;
	}

	// horseman.json / catapult.json: 256 px cells (1.6x the troops'), pivot row 184, figure top row 80, 1.75 cm per px.
	FSRSpriteSheet MakeHorseman()
	{
		FSRSpriteSheet S = MakeSheet();
		S.StrikeFrame = 3;
		S.WindupMap = { 0.f, 0.30f, 0.62f };
		S.RecoveryMap = { 0.f, 0.22f, 0.42f, 0.62f, 0.82f };
		S.TopCm = (184 - 80) * 1.75f;
		S.CardScale = 1.6f;
		return S;
	}

	FSRSpriteSheet MakeCatapult()
	{
		FSRSpriteSheet S = MakeSheet();
		S.StrikeFrame = 5;          // the arm's release
		S.WindupMap = { 0.f, 0.20f, 0.42f, 0.64f, 0.84f };
		S.RecoveryMap = { 0.f, 0.30f, 0.62f };
		S.TopCm = (184 - 80) * 1.75f;
		S.MuzzleCm = FVector(5.f, 0.f, 210.f);
		S.CardScale = 1.6f;
		return S;
	}

	// builder.json: the worker body with a mallet; strike frame 4, figure top row 38.
	FSRSpriteSheet MakeBuilder()
	{
		FSRSpriteSheet S = MakeSheet();
		S.StrikeFrame = 4;
		S.WindupMap = { 0.f, 0.25f, 0.5f, 0.75f };
		S.RecoveryMap = { 0.f, 0.25f, 0.5f, 0.75f };
		S.TopCm = (118 - 38) * 1.75f;
		return S;
	}

	int32 LastAtOrBelow(TConstArrayView<float> Map, float Value)
	{
		int32 Index = 0;
		for (int32 i = 1; i < Map.Num(); ++i)
		{
			if (Map[i] <= Value) { Index = i; }
		}
		return Index;
	}
}

const FSRSpriteSheet& FSRSpriteSheet::For(ESRUnitType Type)
{
	static const FSRSpriteSheet Shieldbearer = MakeShieldbearer();
	static const FSRSpriteSheet Archer = MakeArcher();
	static const FSRSpriteSheet Horseman = MakeHorseman();
	static const FSRSpriteSheet Catapult = MakeCatapult();
	static const FSRSpriteSheet Builder = MakeBuilder();
	switch (Type)
	{
	case ESRUnitType::Archer: return Archer;
	case ESRUnitType::Horseman: return Horseman;
	case ESRUnitType::Catapult: return Catapult;
	case ESRUnitType::Builder: return Builder;
	default: return Shieldbearer;
	}
}

int32 FSRSpriteSheet::AttackFrame(ESRAttackPhase Phase, float Phase01) const
{
	const int32 Last = Anim(ESRSpriteAnim::Attack).Frames - 1;
	if (Phase == ESRAttackPhase::Windup)
	{
		return FMath::Min(LastAtOrBelow(WindupMap, Phase01), StrikeFrame - 1);
	}
	return FMath::Min(StrikeFrame + LastAtOrBelow(RecoveryMap, Phase01), Last);
}

int32 SRSprite::FacingIndex(float UnitYaw, float ViewYaw)
{
	// rel 0 (facing away from the viewer) -> N, 90 -> E, 180 -> S, -90 -> W.
	const float Rel = FRotator::ClampAxis(UnitYaw - ViewYaw + 180.f); // 0 .. 360
	return FMath::RoundToInt(Rel / 45.f) % NumFacings;
}

int32 SRSprite::FacingIndexSticky(int32 Current, float UnitYaw, float ViewYaw, float HysteresisDeg)
{
	const float Rel = UnitYaw - ViewYaw + 180.f;
	const float FromCentre = FMath::Abs(FMath::FindDeltaAngleDegrees(Current * 45.f, Rel));
	return FromCentre <= 22.5f + HysteresisDeg ? Current : FacingIndex(UnitYaw, ViewYaw);
}
