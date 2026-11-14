// Copyright Sovereign Realms.

#include "Battle/SRFormation.h"
#include "Units/SRUnit.h"
#include "Common/SRFeelSettings.h"
#include "Battle/SRBattleSubsystem.h"

void SRFormation::ComputeSlots(const TArray<ASRUnit*>& Units, const FVector2D& Destination, TArray<FVector2D>& OutSlots)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const int32 Num = Units.Num();
	OutSlots.Init(Destination, Num);
	if (Num <= 1) { return; }

	FVector2D Centroid = FVector2D::ZeroVector;
	FVector2D AvgFacing = FVector2D::ZeroVector;
	float MaxRadius = 0.f;
	for (const ASRUnit* Unit : Units)
	{
		Centroid += Unit->GetPos2D();
		AvgFacing += Unit->GetFacingDir();
		MaxRadius = FMath::Max(MaxRadius, Unit->GetRadius());
	}
	Centroid /= Num;

	// Face the direction of travel; for tiny shuffles keep the facing the group already has.
	FVector2D Fwd = Destination - Centroid;
	if (Fwd.SizeSquared() < FMath::Square(150.f)) { Fwd = AvgFacing; }
	Fwd = Fwd.GetSafeNormal();
	if (Fwd.IsNearlyZero()) { Fwd = FVector2D(1.f, 0.f); }
	const FVector2D Right(-Fwd.Y, Fwd.X);

	const float Spacing = MaxRadius * 2.f + F.FormationGap;
	const int32 Columns = FMath::Clamp(FMath::CeilToInt(FMath::Sqrt(Num * F.FormationWidthBias)), 1, FMath::Max(F.FormationMaxColumns, 1));

	// Melee first so they take the front ranks.
	TArray<int32> Melee, Ranged;
	for (int32 i = 0; i < Num; ++i)
	{
		(Units[i]->Stats().bRanged ? Ranged : Melee).Add(i);
	}

	struct FRank { TArray<int32> Members; };
	TArray<FRank> Ranks;

	auto BuildRanks = [&](TArray<int32>& Group)
	{
		if (Group.Num() == 0) { return; }
		// Front-most units go to the front rank.
		Group.Sort([&](int32 A, int32 B)
		{
			return FVector2D::DotProduct(Units[A]->GetPos2D(), Fwd) > FVector2D::DotProduct(Units[B]->GetPos2D(), Fwd);
		});
		const int32 RankCount = FMath::DivideAndRoundUp(Group.Num(), Columns);
		const int32 Base = Group.Num() / RankCount;
		int32 Extra = Group.Num() % RankCount;
		int32 Cursor = 0;
		for (int32 r = 0; r < RankCount; ++r)
		{
			const int32 Count = Base + (Extra-- > 0 ? 1 : 0); // even ranks rather than one full and one stub
			FRank& Rank = Ranks.AddDefaulted_GetRef();
			for (int32 k = 0; k < Count; ++k) { Rank.Members.Add(Group[Cursor++]); }
			// Within a rank keep left-to-right order.
			Rank.Members.Sort([&](int32 A, int32 B)
			{
				return FVector2D::DotProduct(Units[A]->GetPos2D(), Right) < FVector2D::DotProduct(Units[B]->GetPos2D(), Right);
			});
		}
	};
	BuildRanks(Melee);
	BuildRanks(Ranged);

	// Centre the block on the clicked point.
	const float DepthOffset = (Ranks.Num() - 1) * 0.5f * Spacing;
	for (int32 r = 0; r < Ranks.Num(); ++r)
	{
		const TArray<int32>& Members = Ranks[r].Members;
		for (int32 k = 0; k < Members.Num(); ++k)
		{
			const float Lateral = (k - (Members.Num() - 1) * 0.5f) * Spacing;
			FVector2D Slot = Destination + Fwd * (DepthOffset - r * Spacing) + Right * Lateral;
			Slot.X = FMath::Clamp(Slot.X, -F.MapHalfExtent.X, F.MapHalfExtent.X);
			Slot.Y = FMath::Clamp(Slot.Y, -F.MapHalfExtent.Y, F.MapHalfExtent.Y);
			// A slot behind / inside a rock is unreachable: tuck it in front of the obstacle instead.
			if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(Units[0]))
			{
				Slot = Battle->ClipToReachable(FVector(Destination.X, Destination.Y, Units[Members[k]]->GetSimPos().Z), Slot, Units[Members[k]]->GetRadius() + 15.f);
			}
			OutSlots[Members[k]] = Slot;
		}
	}
}
