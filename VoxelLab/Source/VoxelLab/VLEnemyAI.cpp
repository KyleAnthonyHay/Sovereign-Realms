#include "VLEnemyAI.h"
#include "VoxelLab.h"
#include "VLBattle.h"
#include "VLKing.h"
#include "VLCommand.h"
#include "VLGrid.h"
#include "VLConstruction.h"
#include "VLSwordsmanCombat.h"
#include "VLArcherCombat.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "GameFramework/WorldSettings.h"
#include "HAL/IConsoleManager.h"
#include "DrawDebugHelpers.h"

// The commander: the main game's USRAISubsystem (Source/SovereignRealms/Battle/SRAISubsystem.cpp) grown into three
// layers (perception, strategy, squads) over its economy. This file: the profile, perception, the strategy, the
// economy and building (through UVLConstruction, as the player's), places, the report and the console. The squads and
// their tactics: VLAISquads.cpp. The world model (influence map, the map's points): VLAIWorld.*. Not ported: riders and
// catapults (not in this game yet), granaries and treasuries (no voxel model).


namespace
{
	TAutoConsoleVariable<int32> CVarAIDebug(TEXT("vl.AIDebug"), 0,
		TEXT("the commanders' reasoning: 1 logs each look at the strategy (posture, every utility, the squads and their tasks); 2 also draws the squads, their goals, the map's points and the influence map"));
}

int32 VLAIDebugLevel()
{
	return CVarAIDebug.GetValueOnGameThread();
}

FVLAIProfile FVLAIProfile::For(int32 Difficulty)
{
	FVLAIProfile P;          // Normal
	P.FirstRaid = P.FirstAttack * 1.5f;
	P.PatrolRadius = 13000.f;
	P.PullBack = 0.22f;
	if (Difficulty <= 0)
	{
		// Easy: slow to decide, few squads, no micro, but it patrols, guards its castle, holds its side and defends
		P.FirstAttack *= 1.75f;  P.Advantage *= 1.35f;  P.Regroup *= 1.7f;
		P.AttackCap = 5;  P.AttackCapGrowth = 2;  P.AttackCapMax = 14;
		P.bRaids = false;
		P.AdaptWeight = 0.f;  P.IncomeScale = 0.6f;  P.RecruitQueue = 1;  P.Think = 1.5f;
		P.RetreatHold = 0.9f;  P.bReinforce = false;  P.bImpatient = false;
		P.TowerArchers = 0;  P.bUpgrades = false;
		P.Builders = 1;  P.BuildCadence = 8.f;
		P.StrategyEvery = 6.f;  P.ReactionDelay = 5.f;  P.Commitment = 0.2f;  P.ContestWeight = 0.5f;
		P.PatrolMax = 3;  P.PatrolShare = 0.3f;  P.PatrolRadius = 9000.f;
		P.GuardMax = 1;  P.GuardShare = 0.1f;  P.BuilderGuards = 0;  P.PicketFrom = 12;
		P.MaxRaids = 0;  P.bFlank = false;  P.InterceptOdds = 0.f;
		P.MicroEvery = 0.f;  P.FocusFire = 0;  P.bKite = false;  P.PullBack = 0.f;
		P.PushAfter = 2400.f;
	}
	else if (Difficulty >= 2)
	{
		// Hard: quick to react, harasses, focus fire, flanks by the side bridges
		P.FirstAttack *= 0.6f;  P.Advantage *= 0.77f;  P.Regroup *= 0.45f;
		P.AttackCap = 10;  P.AttackCapGrowth = 4;  P.AttackCapMax = FVLCommander::WaveSizeMax;
		P.FirstRaid = P.FirstAttack;  P.RaidInterval *= 0.5f;
		P.AdaptWeight = 1.f;  P.IncomeScale = 1.f;  P.RecruitQueue = 2;  P.Think = 0.6f;
		P.RetreatHold = 0.55f;  P.TowerArchers = 3;
		P.BuildCadence = 2.f;
		P.StrategyEvery = 2.f;  P.ReactionDelay = 0.6f;  P.Commitment = 0.08f;  P.ContestWeight = 1.2f;  P.ExpandWeight = 1.1f;
		P.PatrolMax = 4;  P.PatrolShare = 0.15f;  P.PatrolRadius = 15000.f;
		P.GuardMax = 4;  P.BuilderGuards = 2;  P.PicketFrom = 9;
		P.MaxRaids = 2;  P.RaidSize = 4;  P.bFlank = true;  P.InterceptOdds = 1.25f;  P.InterceptRange = 9000.f;
		P.MicroEvery = 0.5f;  P.FocusFire = 2;  P.bKite = true;  P.PullBack = 0.3f;
		P.PushAfter = 1200.f;
	}
	return P;
}

// ------------------------------------------------------------------------------------------------ strength

float FVLCommander::KindPower(bool bRanged, float HealthFrac)
{
	// sqrt(health x damage per second), a swordsman = 1; archers' reach is worth half as much again
	const VLRules::FTroop& S = VLRules::Troop(EVLUnitKind::Swordsman);     // (by number: no strings made per call)
	const VLRules::FTroop& A = VLRules::Troop(EVLUnitKind::Archer);
	auto Raw = [](const VLRules::FTroop& T, float Interval, bool bR) { return FMath::Sqrt(T.Health * T.Damage / Interval) * (bR ? 1.5f : 1.f); };
	const float Base = Raw(S, 1.25f, false);
	return (bRanged ? Raw(A, 2.4f, true) : Base) / Base * FMath::Clamp(0.35f + 0.65f * HealthFrac, 0.f, 1.f);
}

float FVLCommander::UnitPower(const AVLKing* U)
{
	if (!U || U->IsDead())
	{
		return 0.f;
	}
	if (!U->IsTroop())
	{
		const VLRules::FTroop& K = VLRules::Troop(EVLUnitKind::King);
		const VLRules::FTroop& S = VLRules::Troop(EVLUnitKind::Swordsman);
		return FMath::Sqrt(K.Health * K.Damage) / FMath::Sqrt(S.Health * S.Damage) * (0.35f + 0.65f * U->GetHealthFrac());
	}
	if (U->KindId() == EVLUnitKind::Builder)
	{
		return 0.f;             // a builder is no fighter: no threat, no strength
	}
	if (U->KindId() == EVLUnitKind::Spy)
	{
		return 0.08f * (0.35f + 0.65f * U->GetHealthFrac());     // 90 health, 8 a blow: no fighter
	}
	return KindPower(U->IsRanged(), U->GetHealthFrac());
}

float FVLCommander::BuildingPower(UVLBattle* B, const AActor* Building)
{
	const FVLBuildingState* S = B ? B->FindBuilding(Building) : nullptr;
	if (!S || !S->IsAlive() || S->IsSite() || (S->Kind != EVLBuilding::Tower && S->Kind != EVLBuilding::Castle))
	{
		return 0.f;
	}
	const VLRules::FLevel& L = VLRules::Level(S->Kind, S->Level);
	const VLRules::FTroop& Ref = VLRules::Troop(EVLUnitKind::Swordsman);
	const float RefRaw = FMath::Sqrt(Ref.Health * Ref.Damage / 1.25f);
	// a building cannot be ignored and does not die quickly, but it never advances: its health counts a third
	const float Raw = FMath::Sqrt(FMath::Min(S->MaxHealth, 3000.f) * 0.33f * L.Damage * L.Archers / FMath::Max(L.Interval, 0.1f));
	return Raw / FMath::Max(RefRaw, 1.f) * (0.5f + 0.5f * S->Health / FMath::Max(S->MaxHealth, 1.f));
}

float FVLCommander::SumPower(const TArray<AVLKing*>& Units)
{
	float P = 0.f;
	for (const AVLKing* U : Units)
	{
		P += UnitPower(U);
	}
	return P;
}

float FVLCommander::LocalFoePower(UVLBattle* B, const FVector& At, float Radius) const
{
	float P = 0.f;
	TArray<AVLKing*> Foes;
	B->GetUnits(Foe(), Foes);
	for (const AVLKing* U : Foes)
	{
		if (FVector::DistSquared2D(U->GetFeet(), At) < FMath::Square(Radius))
		{
			P += UnitPower(U);
		}
	}
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team == Foe() && S.IsAlive() && B->DistanceTo(S.Actor.Get(), At) < VLRules::Level(S.Kind, S.Level).Range + 300.f)
		{
			P += BuildingPower(B, S.Actor.Get());
		}
	}
	return P;
}

float FVLCommander::ExpectedDefence(UVLBattle* B, const FVector& At, bool bSeenOnly) const
{
	float D = 0.f, SeenTotal = 0.f;
	for (const FVLSighting& S : Seen)
	{
		const float P = S.Unit.IsValid() ? UnitPower(S.Unit.Get()) : KindPower(S.bRanged, S.HealthFrac);
		SeenTotal += P;
		// troops near the target fight there; troops far off may come back in time, less likely the further
		const float Dist = FVector2D::Distance(S.Pos, FVector2D(At));
		D += P * (bSeenOnly ? (Dist < 3000.f ? 1.f : 0.f) : FMath::GetMappedRangeValueClamped(FVector2f(2500.f, 9000.f), FVector2f(1.f, 0.15f), Dist));
	}
	// what it has not seen lately is presumably at home: it counts near the foe's castle
	if (const AActor* FoeCastle = bSeenOnly ? nullptr : B->GetCastle(Foe()))
	{
		const float Unseen = FMath::Max(0.f, FoeArmyEstimate - SeenTotal);
		D += Unseen * FMath::GetMappedRangeValueClamped(FVector2f(2000.f, 9000.f), FVector2f(0.9f, 0.25f), float(FVector::Dist2D(FoeCastle->GetActorLocation(), At)));
	}
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team == Foe() && S.IsAlive() && B->DistanceTo(S.Actor.Get(), At) < VLRules::Level(S.Kind, S.Level).Range + 400.f)
		{
			D += BuildingPower(B, S.Actor.Get());
		}
	}
	return D;
}

// ------------------------------------------------------------------------------------------------ places

namespace
{
	TAutoConsoleVariable<float> CVarPushAfter(TEXT("vl.AI.PushAfter"), -1.f, TEXT("> = 0: the clock (s) from which the commanders make their final push (tests); < 0: the difficulty's"));
}

bool FVLCommander::IsPushing(const UVLBattle* B) const
{
	const AActor* FoeCastle = B->GetCastle(Foe());
	for (const FVLSquad& S : Squads)
	{
		if (S.Role == EVLSquadRole::Field && S.Task == EVLSquadTask::Attack && FoeCastle && S.Target.Get() == FoeCastle && FinalPush())
		{
			return true;
		}
	}
	return false;
}

bool FVLCommander::FinalPush() const
{
	const float After = CVarPushAfter.GetValueOnGameThread() >= 0.f ? CVarPushAfter.GetValueOnGameThread() : Prof.PushAfter;
	return Clock >= After && ArmyRatio >= 0.9f;
}

int32 FVLCommander::AttackWant(const UVLBattle* B) const
{
	const int32 Cap = FMath::Min3(Prof.AttackCap + Prof.AttackCapGrowth * WavesSent, Prof.AttackCapMax, WaveSizeMax);
	const int32 Housing = FMath::RoundToInt(0.6f * B->GetPopulationCap(Team));
	return FMath::Max(MinAttackSize, FMath::Min(Cap, Housing));
}

FVector2D FVLCommander::TowardFoe(UVLBattle* B) const
{
	const AActor* Mine = B->GetCastle(Team);
	const AActor* Theirs = B->GetCastle(Foe());
	if (Mine && Theirs)
	{
		return FVector2D(Theirs->GetActorLocation() - Mine->GetActorLocation()).GetSafeNormal();
	}
	return Team == 1 ? FVector2D(-0.7f, -0.7f) : FVector2D(0.7f, 0.7f);
}

FVector FVLCommander::MusterPoint(UVLBattle* B) const
{
	// the level's gathering point for this side (TeamStart:<team>, else Rally:<team>), else in front of the castle
	if (Map.bBuilt && Map.bHasMuster[Team])
	{
		return Map.Muster[Team];
	}
	// (B: once the map is read it has looked at every actor's tags for exactly these: a level without them is not
	// walked again, twice, on every call. Before the map is read, or with vl.Opt.Registry 0: the walk as it was)
	if (!Map.bBuilt || !UVLBattle::UseRegistry())
	{
		UWorld* World = B->GetWorld();
		for (const FString& Tag : { FString::Printf(TEXT("TeamStart:%d"), Team), FString::Printf(TEXT("Rally:%d"), Team) })
		{
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				if (It->ActorHasTag(*Tag))
				{
					return It->GetActorLocation();
				}
			}
		}
	}
	const AActor* Castle = B->GetCastle(Team);
	if (!Castle)
	{
		return FVector::ZeroVector;
	}
	FVector Door, Rally, Front;
	B->FrontOf(Castle, Door, Rally, Front);
	return VLAI::Snap(B, Rally + FVector(TowardFoe(B), 0.f) * 900.f, 40);
}

bool FVLCommander::InFoeReach(UVLBattle* B, const FVector& P, float Margin, const AActor** OutBy) const
{
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team == Foe() && S.IsWorking() && (S.Kind == EVLBuilding::Tower || S.Kind == EVLBuilding::Castle)
			&& B->DistanceTo(S.Actor.Get(), P) < VLRules::Level(S.Kind, S.Level).Range + Margin)
		{
			if (OutBy)
			{
				*OutBy = S.Actor.Get();
			}
			return true;
		}
	}
	return false;
}

FVector FVLCommander::AttackSpot(UVLBattle* B, const AActor* Target) const
{
	if (!Target)
	{
		return FVector::ZeroVector;
	}
	FVector Door, Rally, Front;
	B->FrontOf(Target, Door, Rally, Front);
	return VLAI::Snap(B, Door + (Rally - Door).GetSafeNormal2D() * 150.f, 20);
}

FVector FVLCommander::OutOfReach(UVLBattle* B, const FVector& In) const
{
	FVector P = In;
	const AActor* Castle = B->GetCastle(Team);
	if (!Prof.bAvoidTowers || !Castle)
	{
		return P;
	}
	for (int32 i = 0; i < 14 && InFoeReach(B, P, 350.f); ++i)
	{
		P += (Castle->GetActorLocation() - P).GetSafeNormal2D() * 700.f;
	}
	return P == In ? P : VLAI::Snap(B, P, 30);
}

FVector FVLCommander::ForwardPoint(UVLBattle* B, FString* OutName) const
{
	const AActor* Castle = B->GetCastle(Team);
	const FVector Home = Castle ? Castle->GetActorLocation() : MusterPoint(B);
	FVector P = FVector::ZeroVector;
	FString Name;
	// its end of the crossing (the json's bridge end; else the crossing nearest the line between the castles)
	if (Map.bHasBridgeEnd[Team])
	{
		P = Map.BridgeEnd[Team];
		Name = TEXT("its end of the crossing");
	}
	else
	{
		const FVLAIPoint* Best = nullptr;
		for (const FVLAIPoint& X : Map.Points)
		{
			if (X.Kind == EVLAIPoint::Crossing && (!Best || X.Off < Best->Off))
			{
				Best = &X;
			}
		}
		if (Best)
		{
			P = Best->End[Team];
			Name = TEXT("its end of the crossing");
		}
	}
	// no crossing, or one deep in the foe's half: a third of the way toward the foe
	if (Name.IsEmpty() || FVector::Dist2D(P, Home) > Map.CastleGap * 0.62f)
	{
		P = VLAI::Snap(B, Home + (Map.Castle[Foe()] - Home) * 0.33f, 40);
		Name = TEXT("its forward ground");
	}
	// a little back from the bridge, so that the line forms on its own bank, on the highest ground near
	P = VLAI::Snap(B, P + (Home - P).GetSafeNormal2D() * 700.f, 20);
	P = VLAI::HighGround(B, P, 900.f);
	if (OutName)
	{
		*OutName = Name;
	}
	return OutOfReach(B, P);
}

FVector FVLCommander::SafePoint(UVLBattle* B) const
{
	// under its tower nearest the gathering point (toward the foe), else the gathering point itself
	const FVector Muster = MusterPoint(B);
	const FVector2D F = TowardFoe(B);
	const FVLBuildingState* Best = nullptr;
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team == Team && S.IsWorking() && S.Kind == EVLBuilding::Tower && FVector::Dist2D(S.Rest, Muster) < 7000.f
			&& (!Best || FVector::Dist2D(S.Rest, Muster) < FVector::Dist2D(Best->Rest, Muster)))
		{
			Best = &S;
		}
	}
	return Best ? VLAI::Snap(B, Best->Rest + FVector(F, 0.f) * 900.f, 30) : Muster;
}

int32 FVLCommander::PickContest(UVLBattle* B, float FieldPower, FVector* OutAt, float* OutScore) const
{
	const AActor* Castle = B->GetCastle(Team);
	if (!Castle)
	{
		return INDEX_NONE;
	}
	const FVector Home = Castle->GetActorLocation();
	int32 Best = INDEX_NONE;
	float BestScore = 0.f;
	FVector BestAt = FVector::ZeroVector;
	for (int32 i = 0; i < Map.Points.Num(); ++i)
	{
		const FVLAIPoint& P = Map.Points[i];
		if (P.Kind == EVLAIPoint::Flank)
		{
			continue;               // (the long way round is for raids and flanks, not for holding)
		}
		float Value = P.Value;
		FVector At = P.Pos;
		switch (P.Kind)
		{
		case EVLAIPoint::Crown:
			At = VLAI::HighGround(B, VLAI::Snap(B, P.Pos + (Home - P.Pos).GetSafeNormal2D() * 800.f, 12), 900.f);
			break;
		case EVLAIPoint::Crossing:
			if (Map.Count(EVLAIPoint::Crown) > 0)
			{
				At = P.End[Team];   // a Crown's bridge: held from its own bank
			}
			break;
		case EVLAIPoint::Vein:
		{
			// held from beside it on the home side (clear of the mine that goes up there); a vein it has claimed is worth
			// keeping; one the foe has claimed is a target, not a place to hold
			At = VLAI::Snap(B, P.Pos + (Home - P.Pos).GetSafeNormal2D() * 1400.f, 20);
			const FVLBuildingState* Mine = B->FindBuilding(P.Actor.Get());
			if (Mine && Mine->IsAlive())
			{
				Value *= Mine->Team == Team ? 1.15f : 0.4f;
			}
			break;
		}
		default:
			break;
		}
		if (Prof.bAvoidTowers && InFoeReach(B, At, 400.f))
		{
			continue;
		}
		// can it hold it: its field army against what the foe has near there
		const float FoeNear = Influence.MaxIn(Influence.Foe, FVector2D(At), 2500.f);
		const float Odds = FieldPower / (FoeNear * 1.2f + 0.5f);
		const float Feasible = FMath::Clamp((Odds - 0.6f) / 0.8f, 0.f, 1.f);
		// its own half first: deep in the foe's half it is a raid, not a hold
		const float Along = Team == 0 ? P.Along : 1.f - P.Along;
		const float Side = Along > 0.66f ? 0.35f : (Along > 0.55f ? 0.75f : 1.f);
		const float Reach = 1.f / (1.f + float(FVector::Dist2D(Home, At)) / 30000.f);
		const float Score = Value * Feasible * Side * Reach;
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = i;
			BestAt = At;
		}
	}
	if (OutAt)
	{
		*OutAt = BestAt;
	}
	if (OutScore)
	{
		*OutScore = BestScore;
	}
	return Best;
}

void FVLCommander::PatrolPoints(UVLBattle* B, TArray<FVector>& Out) const
{
	// a loop round its buildings within PatrolRadius of the castle, by angle round it: in front of each mine, farm,
	// tower and trainer (the mine roads), and the castle's front
	Out.Reset();
	const AActor* Castle = B->GetCastle(Team);
	if (!Castle)
	{
		return;
	}
	const FVector C = Castle->GetActorLocation();
	TArray<TPair<float, FVector>> Pts;
	auto Add = [&](const FVector& P)
	{
		for (const TPair<float, FVector>& X : Pts)
		{
			if (FVector::Dist2D(X.Value, P) < 1500.f)
			{
				return;
			}
		}
		const FVector2D D(P - C);
		Pts.Add({ FMath::Atan2(float(D.Y), float(D.X)), P });
	};
	Add(MusterPoint(B));
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team != Team || !S.IsAlive() || S.Kind == EVLBuilding::Castle || S.Kind == EVLBuilding::None || B->DistanceTo(S.Actor.Get(), C) > Prof.PatrolRadius)
		{
			continue;
		}
		FVector Door, Rally, Front;
		B->FrontOf(S.Actor.Get(), Door, Rally, Front);
		const FVector P = OutOfReach(B, VLAI::Snap(B, Rally, 20));
		if (FVector::Dist2D(P, C) > 1200.f)
		{
			Add(P);
		}
	}
	if (Pts.Num() < 2)
	{
		// a short beat out toward the forward ground
		Add(VLAI::Snap(B, C + (ForwardPoint(B) - C) * 0.45f, 30));
	}
	Pts.Sort([](const TPair<float, FVector>& X, const TPair<float, FVector>& Y) { return X.Key < Y.Key; });
	for (const TPair<float, FVector>& X : Pts)
	{
		Out.Add(X.Value);
	}
	while (Out.Num() > 7)
	{
		Out.RemoveAt(Out.Num() / 2);
	}
}

float FVLCommander::RouteDefence(UVLBattle* B, const FVector& From, const FVector& To) const
{
	TArray<FVector> Route;
	VLAI::RouteLength(B, From, To, &Route);
	float Peak = 0.f;
	Influence.RouteRisk(Route, 800.f, &Peak);
	return Peak;
}

AActor* FVLCommander::PickTarget(UVLBattle* B, const FVector& From, float Power, bool bRaid, float* OutDefence, const TArray<const AActor*>* Skip) const
{
	// worth over resistance over distance. The economy hurts most; the castle is worth it once its defence is beatable
	const int32 FoeMines = B->CountBuildings(EVLBuilding::Mine, Foe());
	const int32 OurMines = B->CountBuildings(EVLBuilding::Mine, Team);
	const AActor* FoeCastle = B->GetCastle(Foe());
	AActor* Best = nullptr;
	float BestScore = -1.f, BestD = 0.f;
	int32 Others = 0;
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		Others += (S.Team == Foe() && S.IsAlive() && S.Kind != EVLBuilding::Castle) ? 1 : 0;
	}
	// the final push (FinalPush): the castle, whatever stands round it
	if (!bRaid && FinalPush() && FoeCastle && !(Skip && Skip->Contains(FoeCastle)))
	{
		if (OutDefence)
		{
			*OutDefence = ExpectedDefence(B, FoeCastle->GetActorLocation(), false);
		}
		return const_cast<AActor*>(FoeCastle);
	}
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team != Foe() || !S.IsAlive() || (Skip && Skip->Contains(S.Actor.Get())))
		{
			continue;
		}
		float Value = 1.f;
		switch (S.Kind)
		{
		case EVLBuilding::Mine: Value = FoeMines > OurMines ? 3.6f : 3.f; break;
		case EVLBuilding::Farm: Value = 2.4f; break;
		case EVLBuilding::Barracks:
		case EVLBuilding::Range: Value = 2.6f; break;
		case EVLBuilding::Tower: Value = 1.f; break;
		case EVLBuilding::Castle: Value = 4.f; break;
		case EVLBuilding::Granary:
		case EVLBuilding::Treasury: Value = 2.f; break;
		default: Value = 0.6f; break;
		}
		Value *= 1.6f - 0.6f * S.Health / FMath::Max(S.MaxHealth, 1.f);       // already damaged: finish it
		if (S.IsSite())
		{
			Value *= 1.3f;          // a site goes down fast and costs the foe its price
		}
		const FVector At = S.Actor->GetActorLocation();
		const float D = ExpectedDefence(B, At, bRaid);
		if (bRaid)
		{
			// a raid gambles on an outlying farm or mine it has seen next to no defence at, never in the foe's home,
			// nor under its towers
			const bool bTowered = Prof.bAvoidTowers && InFoeReach(B, At, 0.f) && S.Kind != EVLBuilding::Tower;
			if ((S.Kind != EVLBuilding::Farm && S.Kind != EVLBuilding::Mine && !S.IsSite()) || D > Power * 0.6f || bTowered
				|| (FoeCastle && FVector::Dist2D(FoeCastle->GetActorLocation(), At) < 3500.f))
			{
				continue;
			}
		}
		else if (S.Kind == EVLBuilding::Castle && ArmyRatio >= 1.5f && Power >= D)
		{
			// its army well ahead of the foe's and the body a match for what stands there: finish it (balance runs,
			// 2026-11-22: attacks went for the outlying mines for 90 minutes and no castle ever fell)
			Value *= 2.f;
		}
		else if (S.Kind == EVLBuilding::Castle && D > Power * 0.8f && Others > 0)
		{
			Value *= 0.3f;      // the castle is the last resort while it is too strong
		}
		const float Dist = FVector::Dist2D(At, From);
		const float Score = Value / (1.f + D) / (1.f + Dist / 9000.f);
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = S.Actor.Get();
			BestD = D;
		}
	}
	if (OutDefence)
	{
		*OutDefence = BestD;
	}
	return Best;
}

// ------------------------------------------------------------------------------------------------ the loop

void FVLCommander::Reset(UVLBattle* B, int32 InTeam, int32 InDifficulty)
{
	const int32 KeepTeam = InTeam;
	*this = FVLCommander();
	Team = KeepTeam;
	Difficulty = FMath::Clamp(InDifficulty, 0, 2);
	Prof = FVLAIProfile::For(Difficulty);
	ThinkClock = FMath::FRandRange(0.f, Prof.Think);
	StrategyClock = 1.f;
	NextWaveTime = Prof.FirstAttack;
	NextRaidTime = Prof.bRaids ? Prof.FirstRaid : 1e9f;
	ShieldRatio = BaseShieldRatio;
	Squads.Reserve(16);             // (a handful at most: references to them stay good while one is added)
	// it knows the foe starts as it does
	FoeArmyEstimate = VLRules::StartSwordsmen * KindPower(false) + VLRules::StartArchers * KindPower(true);
	UE_LOG(LogVoxelLab, Log, TEXT("commander of team %d: %s, first attack from %.0f s, raids %s, strategy every %.1f s, micro %s"), Team, UVLBattle::DifficultyName(Difficulty), Prof.FirstAttack,
		Prof.bRaids ? *FString::Printf(TEXT("every %.0f s from %.0f s"), Prof.RaidInterval, Prof.FirstRaid) : TEXT("none"), Prof.StrategyEvery,
		Prof.MicroEvery > 0.f ? *FString::Printf(TEXT("every %.1f s"), Prof.MicroEvery) : TEXT("none"));
}

void FVLCommander::Step(UVLBattle* B, float Dt)
{
	Clock += Dt;
	ThinkClock -= Dt;
	if (ThinkClock <= 0.f)
	{
		ThinkClock = Prof.Think;
		Think(B);
	}
	if (Prof.MicroEvery > 0.f)
	{
		MicroClock -= Dt;
		if (MicroClock <= 0.f)
		{
			MicroClock = Prof.MicroEvery;
			Micro(B);
		}
	}
}

void FVLCommander::Think(UVLBattle* B)
{
	if (!B->GetCastle(Team))
	{
		return;
	}
	if (!Map.bBuilt)
	{
		Map.Build(B);
		FBox2D Bounds(ForceInit);
		if (UVLGrid* Grid = UVLGrid::Get(B->GetWorld()); Grid && Grid->EnsureBuilt())
		{
			Bounds = Grid->GetBounds();
		}
		else
		{
			Bounds += FVector2D(Map.Castle[0]);
			Bounds += FVector2D(Map.Castle[1]);
			Bounds = Bounds.ExpandBy(10000.f);
		}
		Influence.Init(Bounds, 1000.f);
	}
	TArray<AVLKing*> Mine, Army, Pool;
	B->GetUnits(Team, Mine, true);
	for (AVLKing* U : Mine)
	{
		if (U->KindId() == EVLUnitKind::Spy || U->KindId() == EVLUnitKind::Builder)
		{
			continue;               // (the Spy is sent out on its own: ManageSpy; Builders build)
		}
		Army.Add(U);
		if (const FVector* At = Stuck.Find(U))
		{
			if (FVector::Dist2D(*At, U->GetFeet()) < 300.f)
			{
				continue;           // (still where it cannot get out of: left out of the squads)
			}
			Stuck.Remove(U);
		}
		if (!U->IsGarrisoned() && !U->PendingGarrison.IsValid())
		{
			Pool.Add(U);
		}
	}
	ArmyPower = SumPower(Army);
	Observe(B);
	TrackEvents(B, Army);
	UpdateInfluence(B, Mine);
	Adapt(B);
	ManageUpgrades(B);
	ManageBuilding(B, Mine);
	Recruit(B, Mine);
	ManageSpy(B, Mine);
	ManageTowers(B, Pool);
	const bool bLook = Clock >= StrategyClock;
	if (bLook)
	{
		StrategyClock = Clock + Prof.StrategyEvery;
		ChooseStrategy(B);
	}
	ManageSquads(B, Pool);
	RunSquads(B);
	// With no attack out and no main body waiting for its flank, the next attack's time is a real one: never the
	// "while it is out" mark, never further off than its longest pause (whichever way an attack came to an end).
	if (NextWaveTime - Clock > MaxWaveWait() && !IsAttacking())
	{
		const FVLSquad* Field = FindSquad(EVLSquadRole::Field);
		if (!Field || Field->Departs <= 0.f)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d: its next attack was %.0f s off with none out: in %.0f s"), Team, NextWaveTime - Clock, Prof.Regroup);
			NextWaveTime = Clock + Prof.Regroup;
		}
	}
	if (bLook && VLAIDebugLevel() >= 1)
	{
		TArray<FString> Parts;
		for (const FVLSquad& S : Squads)
		{
			Parts.Add(FString::Printf(TEXT("%s#%d %d %s%s"), RoleName(S.Role), S.Id, S.Num(), TaskName(S.Task), S.GoalName.IsEmpty() ? TEXT("") : *(TEXT(" ") + S.GoalName)));
		}
		UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s %s] posture %s (expand %.2f defend %.2f contest %.2f harass %.2f attack %.2f regroup %.2f) army %.1f vs ~%.1f (x%.2f) threat %.1f | %s"),
			Team, UVLBattle::DifficultyName(Difficulty), *FString::Printf(TEXT("%d:%02d"), int32(Clock) / 60, int32(Clock) % 60), PostureName(Posture),
			Utility[0], Utility[1], Utility[2], Utility[3], Utility[4], Utility[5], ArmyPower, FoeArmyEstimate, ArmyRatio, HomeThreat, *FString::Join(Parts, TEXT(" | ")));
	}
	if (VLAIDebugLevel() >= 2)
	{
		DebugDraw(B);
	}
}

// ------------------------------------------------------------------------------------------------ perception

void FVLCommander::Observe(UVLBattle* B)
{
	// eyes: its troops (its Spy further), its Builders and its buildings
	TArray<TPair<FVector, float>> Eyes;
	TArray<AVLKing*> Ours, Theirs;
	B->GetUnits(Team, Ours);
	B->GetUnits(Foe(), Theirs);
	for (const AVLKing* U : Ours)
	{
		Eyes.Add({ U->GetFeet(), FMath::Max(SightRadius, U->KindId() == EVLUnitKind::Spy ? VLRules::Troop(EVLUnitKind::Spy).Sight : 0.f) });
	}
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team == Team && S.IsAlive())
		{
			Eyes.Add({ S.Actor->GetActorLocation(), SightRadius });
		}
	}
	for (AVLKing* U : Theirs)
	{
		bool bVisible = false;
		const float Notice = U->KindRules().Notice;      // a Spy is only seen from close by
		for (const TPair<FVector, float>& E : Eyes)
		{
			if (FVector::DistSquared2D(E.Key, U->GetFeet()) < FMath::Square(E.Value * Notice))
			{
				bVisible = true;
				break;
			}
		}
		if (!bVisible)
		{
			continue;
		}
		FVLSighting* S = Seen.FindByPredicate([U](const FVLSighting& X) { return X.Unit.Get() == U; });
		if (!S)
		{
			S = &Seen.AddDefaulted_GetRef();
			S->Unit = U;
		}
		S->Pos = FVector2D(U->GetFeet());
		S->bRanged = U->IsRanged();
		S->bKing = !U->IsTroop();
		S->HealthFrac = U->GetHealthFrac();
		S->Time = Clock;
	}
	// forget the dead and the long unseen
	Seen.RemoveAll([this](const FVLSighting& S) { return !S.Unit.IsValid() || S.Unit->IsDead() || Clock - S.Time > MemoryTime; });
	float SeenNow = 0.f;
	int32 Archers = 0, Total = 0;
	for (const FVLSighting& S : Seen)
	{
		SeenNow += UnitPower(S.Unit.Get());
		Archers += S.bRanged ? 1 : 0;
		Total += S.bKing ? 0 : 1;
	}
	if (Total >= 3)
	{
		FoeArcherShare = FMath::Lerp(FoeArcherShare, float(Archers) / Total, 0.25f);
	}
	// the foe's army as last seen at its largest, slowly forgotten; unseen, it has kept up with ours at least by half
	TArray<AVLKing*> OurTroops;
	B->GetUnits(Team, OurTroops, true);
	FoeArmyEstimate = FMath::Max3(SeenNow, FoeArmyEstimate * FMath::Pow(0.5f, Prof.Think / 240.f), SumPower(OurTroops) * 0.5f);

	// ---- the foe's bodies: what was seen in the last seconds, grouped
	FoeGroups.Reset();
	{
		TArray<const FVLSighting*> Fresh;
		for (const FVLSighting& S : Seen)
		{
			if (Clock - S.Time < 5.f && S.Unit.IsValid() && UnitPower(S.Unit.Get()) > 0.1f)
			{
				Fresh.Add(&S);
			}
		}
		TArray<bool> Taken;
		Taken.Init(false, Fresh.Num());
		const AActor* FoeCastle = B->GetCastle(Foe());
		for (int32 i = 0; i < Fresh.Num(); ++i)
		{
			if (Taken[i])
			{
				continue;
			}
			FVLFoeGroup G;
			FVector2D Sum = FVector2D::ZeroVector;
			TArray<int32> Members = { i };
			Taken[i] = true;
			for (int32 k = 0; k < Members.Num(); ++k)     // (grows as it goes: friends of friends within 18 m)
			{
				for (int32 j = 0; j < Fresh.Num(); ++j)
				{
					if (!Taken[j] && FVector2D::DistSquared(Fresh[Members[k]]->Pos, Fresh[j]->Pos) < FMath::Square(1800.f))
					{
						Taken[j] = true;
						Members.Add(j);
					}
				}
			}
			for (int32 k : Members)
			{
				Sum += Fresh[k]->Pos;
				G.Power += UnitPower(Fresh[k]->Unit.Get());
			}
			G.Count = Members.Num();
			const FVector2D C = Sum / G.Count;
			G.Centre = VLAI::Snap(B, FVector(C.X, C.Y, Fresh[i]->Unit->GetFeet().Z), 10);
			G.bExposed = (!FoeCastle || FVector::Dist2D(FoeCastle->GetActorLocation(), G.Centre) > 4500.f) && !InFoeReach(B, G.Centre, 300.f);
			for (const FVLBuildingState& Bld : B->GetBuildings())
			{
				if (Bld.Team == Team && Bld.IsAlive() && B->DistanceTo(Bld.Actor.Get(), G.Centre) < DefendRadius)
				{
					G.bAtOurHome = true;
					break;
				}
			}
			FoeGroups.Add(G);
		}
	}

	// ---- is the foe at our door? (foes its buildings can see; a Spy only once noticed)
	FVector ThreatSum = FVector::ZeroVector;
	float ThreatPower = 0.f;
	int32 Threats = 0;
	for (AVLKing* U : Theirs)
	{
		for (const FVLBuildingState& S : B->GetBuildings())
		{
			if (S.Team == Team && S.IsAlive() && UVLBattle::IsNoticed(U, B->DistanceTo(S.Actor.Get(), U->GetFeet()), SightRadius))
			{
				ThreatSum += U->GetFeet();
				ThreatPower += UnitPower(U);
				++Threats;
				break;
			}
		}
	}
	HomeThreat = ThreatPower;
	if (Threats > 0)
	{
		HomeThreatAt = VLAI::Snap(B, ThreatSum / Threats, 10);
	}
	const bool bAtHome = ThreatPower > 0.2f;
	if (bAtHome && !bFoeAtHome && Clock - LastFoeAttack > 30.f)
	{
		++FoeAttacks;
		AddEvent(EVLAIEvent::FoeAtHome, HomeThreatAt, ThreatPower, FString::Printf(TEXT("%d foes"), Threats));
	}
	if (bAtHome)
	{
		LastFoeAttack = Clock;
		if (ThreatSince < 0.f)
		{
			ThreatSince = Clock;
		}
	}
	else if (Clock - LastFoeAttack > 4.f)
	{
		ThreatSince = -1.f;
	}
	bFoeAtHome = bAtHome;
}

void FVLCommander::AddEvent(EVLAIEvent Kind, const FVector& At, float Power, const FString& What, AActor* Actor)
{
	FVLAIEvent& E = Events.AddDefaulted_GetRef();
	E.Kind = Kind;
	E.At = At;
	E.Time = Clock;
	E.Power = Power;
	E.What = What;
	E.Actor = Actor;
	if (Kind != EVLAIEvent::UnitLost || VLAIDebugLevel() >= 1)
	{
		UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%d:%02d] event: %s, %s at (%.0f, %.0f)"), Team, int32(Clock) / 60, int32(Clock) % 60, VLAI::EventName(Kind), *What, At.X, At.Y);
	}
}

float FVLCommander::RecentLoss(float Window) const
{
	float P = 0.f;
	for (const FVLAIEvent& E : Events)
	{
		P += (E.Kind == EVLAIEvent::UnitLost && Clock - E.Time < Window) ? E.Power : 0.f;
	}
	return P;
}

int32 FVLCommander::CountEvents(EVLAIEvent Kind, float Window) const
{
	int32 N = 0;
	for (const FVLAIEvent& E : Events)
	{
		N += (E.Kind == Kind && Clock - E.Time < Window) ? 1 : 0;
	}
	return N;
}

void FVLCommander::TrackEvents(UVLBattle* B, const TArray<AVLKing*>& Army)
{
	const double Now = B->GetWorld()->GetTimeSeconds();
	const AActor* Castle = B->GetCastle(Team);
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team != Team || !S.Actor.IsValid())
		{
			continue;
		}
		const TWeakObjectPtr<AActor> Key = S.Actor;
		if (S.bDestroyed)
		{
			if (!KnownLost.Contains(Key))
			{
				KnownLost.Add(Key);
				AddEvent(EVLAIEvent::BuildingLost, S.Rest, 0.f, S.Name, S.Actor.Get());
			}
			continue;
		}
		double* Known = KnownHits.Find(Key);
		if (!Known)
		{
			KnownHits.Add(Key, S.LastHit);
			continue;
		}
		if (S.LastHit > *Known + 0.01)
		{
			const bool bNewBout = S.LastHit - *Known > 8.0;
			*Known = S.LastHit;
			if (bNewBout && Now - S.LastHit < 3.0)
			{
				AddEvent(EVLAIEvent::BuildingHit, S.Rest, 0.f, S.Name, S.Actor.Get());
				if ((S.Kind == EVLBuilding::Farm || S.Kind == EVLBuilding::Mine) && (!Castle || B->DistanceTo(Castle, S.Rest) > 3500.f))
				{
					LastRaided = Clock;
					RaidedAt = S.Rest;
					AddEvent(EVLAIEvent::Raided, S.Rest, 0.f, S.Name, S.Actor.Get());
				}
			}
		}
	}
	// troops lost since the last look (where and how strong they were)
	for (auto It = Roll.CreateIterator(); It; ++It)
	{
		if (!It.Key().IsValid() || It.Key()->IsDead())
		{
			AddEvent(EVLAIEvent::UnitLost, FVector(It.Value().X, It.Value().Y, It.Value().Z), It.Value().W, TEXT("a troop"));
			It.RemoveCurrent();
		}
	}
	for (AVLKing* U : Army)
	{
		const FVector F = U->GetFeet();
		Roll.Add(U, FVector4f(float(F.X), float(F.Y), float(F.Z), FMath::Max(UnitPower(U), KindPower(U->IsRanged(), 0.3f))));
	}
	Events.RemoveAll([this](const FVLAIEvent& E) { return Clock - E.Time > 240.f; });
}

void FVLCommander::UpdateInfluence(UVLBattle* B, const TArray<AVLKing*>& Mine)
{
	if (!Influence.IsValid())
	{
		return;
	}
	Influence.Clear();
	for (const AVLKing* U : Mine)
	{
		Influence.Stamp(Influence.Own, FVector2D(U->GetFeet()), UnitPower(U), 2200.f);
	}
	float SeenTotal = 0.f;
	for (const FVLSighting& S : Seen)
	{
		const float P = S.Unit.IsValid() ? UnitPower(S.Unit.Get()) : KindPower(S.bRanged, S.HealthFrac);
		SeenTotal += P;
		Influence.Stamp(Influence.Foe, S.Pos, P * FMath::Clamp(1.f - (Clock - S.Time) / MemoryTime, 0.25f, 1.f), 2200.f);
	}
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.IsWorking() && (S.Team == Team || S.Team == Foe()) && (S.Kind == EVLBuilding::Tower || S.Kind == EVLBuilding::Castle))
		{
			Influence.Stamp(S.Team == Team ? Influence.Own : Influence.Foe, FVector2D(S.Rest), BuildingPower(B, S.Actor.Get()) * 1.6f, VLRules::Level(S.Kind, S.Level).Range + 900.f);
		}
	}
	// what it has not seen is presumably round the foe's castle
	if (const AActor* FoeCastle = B->GetCastle(Foe()))
	{
		Influence.Stamp(Influence.Foe, FVector2D(FoeCastle->GetActorLocation()), FMath::Max(0.f, FoeArmyEstimate - SeenTotal) * 0.6f, 4500.f);
	}
}

// ------------------------------------------------------------------------------------------------ strategy

void FVLCommander::ChooseStrategy(UVLBattle* B)
{
	float U[int32(EVLPosture::Num)] = {};
	TArray<FString> Why;
	ArmyRatio = ArmyPower / FMath::Max(FoeArmyEstimate, 0.5f);
	float FieldPower = 0.f, HomePower = 0.f;
	int32 FieldN = 0;
	FVector FieldCentre = MusterPoint(B);
	for (const FVLSquad& S : Squads)
	{
		TArray<AVLKing*> W;
		FVector C;
		S.Gather(W, C);
		if (S.Role == EVLSquadRole::Field || S.Role == EVLSquadRole::Reserve || S.Role == EVLSquadRole::Picket)
		{
			FieldPower += SumPower(W);
			FieldN += W.Num();
			if (S.Role == EVLSquadRole::Field && W.Num() > 0)
			{
				FieldCentre = C;
			}
		}
		else if (S.Role == EVLSquadRole::Patrol || S.Role == EVLSquadRole::Guard)
		{
			HomePower += SumPower(W);
		}
	}
	const AActor* Castle = B->GetCastle(Team);
	float TowerHelp = 0.f;
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team == Team && S.IsWorking() && B->DistanceTo(S.Actor.Get(), HomeThreatAt) < VLRules::Level(S.Kind, S.Level).Range + 300.f)
		{
			TowerHelp += BuildingPower(B, S.Actor.Get());
		}
	}

	// ---- defend: foes at its buildings, long enough to be sure (its reaction time)
	const bool bThreat = HomeThreat > 0.25f && ThreatSince >= 0.f && Clock - ThreatSince >= Prof.ReactionDelay;
	if (bThreat)
	{
		const float Cover = HomePower + TowerHelp;
		const bool bCastle = Castle && B->DistanceTo(Castle, HomeThreatAt) < 3200.f;
		U[int32(EVLPosture::Defend)] = HomeThreat < Cover * 0.6f ? 0.3f : 0.6f + 0.4f * FMath::Clamp(HomeThreat / FMath::Max(Cover, 0.5f) - 0.6f, 0.f, 1.f) + (bCastle ? 0.25f : 0.f);
		// its final push out at the foe's castle: a raid on an outlying mine or farm is the patrol's and the guard's, not a
		// reason to call the push home (balance runs, 2026-11-22: a push with twice the foe's army was recalled to an
		// outlying mine again and again, and never took the castle)
		if (!bCastle && IsPushing(B))
		{
			U[int32(EVLPosture::Defend)] = FMath::Min(U[int32(EVLPosture::Defend)], 0.3f);
		}
		Why.Add(FString::Printf(TEXT("threat %.1f vs home %.1f%s"), HomeThreat, Cover, bCastle ? TEXT(" at the castle") : TEXT("")));
	}
	else if (Posture == EVLPosture::Defend && Clock - LastFoeAttack < 12.f)
	{
		U[int32(EVLPosture::Defend)] = 0.5f;          // (foes slipping in and out of sight: it stays on guard a while)
		Why.Add(TEXT("foes lately at home"));
	}
	// ---- regroup: heavy losses lately, or clearly outmatched
	const float Lost = RecentLoss(60.f);
	const float LostShare = Lost / FMath::Max(ArmyPower + Lost, 1.f);
	if (LostShare > 0.3f && Lost > 2.f && ArmyRatio < 1.4f)
	{
		U[int32(EVLPosture::Regroup)] = 0.6f + 0.5f * FMath::Clamp(LostShare - 0.3f, 0.f, 0.6f) + 0.3f * FMath::Clamp(1.f - ArmyRatio, 0.f, 1.f);
		Why.Add(FString::Printf(TEXT("lost %.0f%% of its army in a minute"), LostShare * 100.f));
	}
	else if (ArmyRatio < 0.55f && Clock > 300.f)       // (300: twice the 150 s it was, as every build and training time is)
	{
		U[int32(EVLPosture::Regroup)] = 0.42f;
		Why.Add(TEXT("outnumbered"));
	}
	// ---- attack: the odds against what it expects at the best target, the clock, its housing
	if (Clock >= NextWaveTime && FieldN >= MinAttackSize)
	{
		TArray<AVLKing*> Body;
		FVector From;
		float Power = 0.f, Defence = 0.f;
		if (PlanAttack(B, Body, From, Power, Defence) && Body.Num() >= MinAttackSize)
		{
			const float Odds = Power / FMath::Max(Defence, 0.3f);
			const bool bMaxed = B->GetPopulation(Team) >= B->GetPopulationCap(Team) - 1;
			const bool bWaitedLong = Prof.bImpatient && Clock > NextWaveTime + 150.f && Odds >= 0.85f;
			const bool bReady = Body.Num() >= AttackWant(B) || bMaxed || Odds >= 2.f * Prof.Advantage;
			float A = 0.25f + 0.6f * FMath::Clamp((Odds - 1.f) / FMath::Max(Prof.Advantage - 1.f, 0.1f), 0.f, 1.2f);
			if (Odds >= Prof.Advantage) { A = FMath::Max(A, 0.85f); }
			if (bMaxed) { A += 0.3f; }
			if (bWaitedLong) { A = FMath::Max(A, 0.72f); }
			if (Odds < 0.85f && !bMaxed) { A *= 0.3f; }
			if (!bReady) { A *= 0.3f; }            // (not in force yet: it gathers)
			if (bReady && FinalPush() && Body.Num() >= AttackWant(B)) { A = FMath::Max(A, 0.9f); }     // (the final push)
			U[int32(EVLPosture::Attack)] = A;
			Why.Add(FString::Printf(TEXT("attack odds %.2f (wants %.2f)%s"), Odds, Prof.Advantage, bMaxed ? TEXT(", housing full") : TEXT("")));
		}
	}
	// ---- an attack under way (or a flank out) stays the plan until it ends
	for (const FVLSquad& S : Squads)
	{
		if ((S.Role == EVLSquadRole::Field || S.Role == EVLSquadRole::Flank) && S.Task == EVLSquadTask::Attack && S.Num() > 0)
		{
			U[int32(EVLPosture::Attack)] = FMath::Max(U[int32(EVLPosture::Attack)], 0.9f);
		}
	}
	// ---- contest: the best of the map's points it can hold
	{
		FVector At;
		float Score = 0.f;
		ContestPoint = PickContest(B, FieldPower, &At, &Score);
		if (ContestPoint != INDEX_NONE)
		{
			U[int32(EVLPosture::Contest)] = Prof.ContestWeight * FMath::Min(Score * 1.2f, 0.9f) * (Clock < 60.f ? 0.6f : 1.f);
			Why.Add(FString::Printf(TEXT("contest %s %.2f"), *Map.Points[ContestPoint].Name, Score));
		}
	}
	// ---- harass: raids on the foe's outlying economy (a side behind on mines raids more)
	if (Prof.bRaids && Prof.MaxRaids > 0 && Clock >= Prof.FirstRaid * 0.8f && FieldN >= Prof.RaidSize + 2)
	{
		float Defence = 0.f;
		if (PickTarget(B, FieldCentre, KindPower(false) * Prof.RaidSize, true, &Defence))
		{
			const int32 FoeMines = B->CountBuildings(EVLBuilding::Mine, Foe()), OurMines = B->CountBuildings(EVLBuilding::Mine, Team);
			U[int32(EVLPosture::Harass)] = 0.35f + (FoeMines > OurMines ? 0.2f : 0.f) + (ArmyRatio > 0.8f && ArmyRatio < 1.5f ? 0.15f : 0.f);
		}
	}
	// ---- expand: safe at home and veins to claim / farms to raise; the default of a quiet start
	{
		int32 Veins = 0;
		// (B: only the actors named as a gold mine, from the battle's cached list, in the actor walk's order)
		TArray<AActor*> MineList;
		VLAI::MineActors(B, MineList);
		for (AActor* Mine : MineList)
		{
			FVector At;
			if (VLAI::IsFreeVein(B, Mine, &At) && Castle && FVector::Dist2D(At, Castle->GetActorLocation()) < 26000.f && Influence.FoeAt(At) < Influence.OwnAt(At) + 1.f)
			{
				++Veins;
			}
		}
		SafeVeins = Veins;
		const int32 FoeMines = B->CountBuildings(EVLBuilding::Mine, Foe()), OurMines = B->CountBuildings(EVLBuilding::Mine, Team);
		U[int32(EVLPosture::Expand)] = Prof.ExpandWeight * (0.3f + (Veins > 0 ? 0.15f : 0.f) + 0.15f * FMath::Clamp(1.f - Clock / 300.f, 0.f, 1.f) + (OurMines < FoeMines ? 0.12f : 0.f)) * (bThreat ? 0.5f : 1.f);
	}

	// ---- the choice: the best, the present posture kept a little longer (no flip-flopping), defence at once
	int32 Best = int32(Posture);
	float BestU = -1.f;
	for (int32 i = 0; i < int32(EVLPosture::Num); ++i)
	{
		const float V = U[i] + (i == int32(Posture) ? Prof.Commitment : 0.f);
		if (V > BestU)
		{
			BestU = V;
			Best = i;
		}
	}
	FMemory::Memcpy(Utility, U, sizeof(U));
	// (a field army in the middle of a fight keeps the posture it fights under: the odds of what is not fighting say
	// little then)
	int32 FieldFighting = 0, FieldAll = 0;
	for (const FVLSquad& S : Squads)
	{
		if (S.Role == EVLSquadRole::Field || S.Role == EVLSquadRole::Picket)
		{
			for (const TWeakObjectPtr<AVLKing>& Un : S.Units)
			{
				++FieldAll;
				FieldFighting += (Un.IsValid() && VLAI::Engaged(Un.Get())) ? 1 : 0;
			}
		}
	}
	const bool bUrgent = Best == int32(EVLPosture::Defend) && U[Best] >= 0.6f;
	const bool bDwell = (Clock - PostureSince < FMath::Max(Prof.StrategyEvery * 2.f, 8.f) || FieldFighting * 3 >= FMath::Max(FieldAll, 1)) && !bUrgent;
	if (Best != int32(Posture) && !bDwell)
	{
		UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%d:%02d] posture %s -> %s (%.2f vs %.2f; army %.1f vs ~%.1f; %s)"), Team, int32(Clock) / 60, int32(Clock) % 60, PostureName(Posture), PostureName(EVLPosture(Best)),
			U[Best], U[int32(Posture)], ArmyPower, FoeArmyEstimate, Why.Num() ? *FString::Join(Why, TEXT(", ")) : TEXT("quiet"));
		Posture = EVLPosture(Best);
		PostureSince = Clock;
	}
	PostureWhy = FString::Join(Why, TEXT(", "));
}

// ------------------------------------------------------------------------------------------------ economy

void FVLCommander::Adapt(UVLBattle* B)
{
	// answer what the foe fields: swordsmen close on archers and knock down buildings; archers shred a slow wall of
	// swords from behind their own
	float Want = BaseShieldRatio;
	if (FoeArcherShare > 0.55f)
	{
		Want += (FoeArcherShare - 0.55f) * 1.2f;
	}
	if (FoeArcherShare < 0.3f)
	{
		Want -= (0.3f - FoeArcherShare) * 1.1f;
	}
	Want += FMath::Min(B->CountBuildings(EVLBuilding::Tower, Foe()), 4) * 0.03f;      // towers: bring wall-breakers
	Want = FMath::Lerp(BaseShieldRatio, FMath::Clamp(Want, 0.3f, 0.8f), Prof.AdaptWeight);
	ShieldRatio = FMath::FInterpTo(ShieldRatio, Want, Prof.Think, 0.5f);
}

void FVLCommander::Recruit(UVLBattle* B, const TArray<AVLKing*>& Mine)
{
	int32 Swords = 0, Bows = 0;
	for (const AVLKing* U : Mine)
	{
		if (U->KindId() == EVLUnitKind::Spy || U->KindId() == EVLUnitKind::Builder)
		{
			continue;               // not part of the army's mix
		}
		(U->IsRanged() ? Bows : Swords) += 1;
	}
	// its Builders first (it keeps Prof.Builders, trained at the castle): the second once its barracks and range are laid
	{
		int32 Builders = 0, BuildersQueued = 0;
		for (const AVLKing* U : Mine)
		{
			Builders += U->KindId() == EVLUnitKind::Builder ? 1 : 0;
		}
		for (const FVLBuildingState& S : B->GetBuildings())
		{
			if (S.Team == Team && S.IsAlive())
			{
				BuildersQueued += S.Queue.FilterByPredicate([](const FString& K) { return K == TEXT("Builder"); }).Num();
			}
		}
		const bool bTrainersLaid = B->CountBuildings(EVLBuilding::Barracks, Team) > 0 && B->CountBuildings(EVLBuilding::Range, Team) > 0;
		AActor* Castle = B->GetCastle(Team);
		if (Castle && Builders + BuildersQueued < FMath::Min(Prof.Builders, VLBuild::MaxBuilders(B->GetCastleLevel(Team))) && (Builders + BuildersQueued == 0 || bTrainersLaid)
			&& B->TrainRefusal(Castle, TEXT("Builder")).IsEmpty())
		{
			if (B->Train(Castle, 1, true, TEXT("Builder")) > 0)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("AI %d: trains a builder (%d alive)"), Team, Builders);
				return;             // one decision a think
			}
		}
	}
	const FVector Muster = MusterPoint(B);
	TArray<FVLBuildingState*> Trainers;
	for (FVLBuildingState& S : B->GetBuildingsMutable())
	{
		if (S.Team != Team || !S.IsAlive() || !S.Trains() || S.IsSite())
		{
			continue;           // (a site trains nobody yet)
		}
		for (const FString& K : S.Queue)
		{
			if (K != TEXT("Spy") && K != TEXT("Builder"))
			{
				(K == TEXT("Archer") ? Bows : Swords) += 1;
			}
		}
		Trainers.Add(&S);
		if (!S.bHasRally || FVector::Dist2D(S.Rally, Muster) > 150.f)
		{
			B->SetRally(S.Actor.Get(), Muster);        // recruits muster at the gathering point (the squads take them from there)
		}
	}
	if (Trainers.Num() == 0)
	{
		return;
	}
	// behind the foe's army: one more in each queue (Normal, Hard)
	const int32 Queue = Prof.RecruitQueue + ((ArmyRatio < 0.8f && Prof.AdaptWeight > 0.f) ? 1 : 0);
	const int32 Core = Swords + Bows;
	const bool bNeedSwords = Core == 0 || float(Swords) / Core < ShieldRatio;
	const FString Order[2] = { bNeedSwords ? TEXT("Swordsman") : TEXT("Archer"), bNeedSwords ? TEXT("Archer") : TEXT("Swordsman") };
	for (const FString& Kind : Order)
	{
		FVLBuildingState* Best = nullptr;
		for (FVLBuildingState* S : Trainers)
		{
			if (UVLBattle::TroopFor(S->Actor.Get()) == Kind && S->Queue.Num() < Queue && (!Best || S->Queue.Num() < Best->Queue.Num()))
			{
				Best = S;
			}
		}
		if (!Best)
		{
			continue;           // no trainer for it with room in its queue: the next want
		}
		if (B->TrainRefusal(Best->Actor.Get()).IsEmpty())
		{
			B->Train(Best->Actor.Get(), 1, true);
		}
		break;                  // one decision a think: the wanted kind waits for its price rather than another draining it
	}
}

void FVLCommander::ManageUpgrades(UVLBattle* B)
{
	// housing short (or the stores filling) and the price to hand: raise the castle a level
	if (AActor* Castle = B->GetCastle(Team))
	{
		FVLCost Cost;
		if (B->UpgradeRefusal(Castle, &Cost).IsEmpty())
		{
			const bool bCrowded = B->GetPopulation(Team) + B->GetQueuedPopulation(Team) + 3 >= B->GetPopulationCap(Team);
			const bool bFull = B->GetStock(Team, EVLRes::Gold) >= B->GetStorage(Team, EVLRes::Gold) * 0.85f;
			if ((bCrowded || bFull) && B->GetStock(Team, EVLRes::Gold) >= Cost.Gold + 60)
			{
				B->Upgrade(Castle, true);
			}
		}
	}
	if (!Prof.bUpgrades)
	{
		return;
	}
	// gold piling up (Normal and Hard): a mine first (more gold), then the barracks and range, then farms and towers;
	// under attack, the tower nearest the trouble first
	const bool bSpare = B->GetStock(Team, EVLRes::Gold) >= B->GetStorage(Team, EVLRes::Gold) * 0.7f;
	if (!bSpare)
	{
		return;
	}
	const bool bPressed = Clock - LastFoeAttack < 60.f || Clock - LastRaided < 90.f;
	auto Rank = [bPressed](EVLBuilding K) { return (bPressed && K == EVLBuilding::Tower) ? -1 : (K == EVLBuilding::Mine ? 0 : (K == EVLBuilding::Barracks || K == EVLBuilding::Range ? 1 : (K == EVLBuilding::Farm ? 2 : 3))); };
	const FVLBuildingState* Best = nullptr;
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team != Team || S.Kind == EVLBuilding::Castle || S.Kind == EVLBuilding::Hall || !B->UpgradeRefusal(S.Actor.Get()).IsEmpty())
		{
			continue;
		}
		if (!Best || Rank(S.Kind) < Rank(Best->Kind) || (Rank(S.Kind) == Rank(Best->Kind) && S.Level < Best->Level))
		{
			Best = &S;
		}
	}
	if (Best)
	{
		B->Upgrade(Best->Actor.Get(), true);
	}
}

void FVLCommander::ManageBuilding(UVLBattle* B, const TArray<AVLKing*>& Mine)
{
	UVLConstruction* C = UVLConstruction::Get(B);
	if (!C || Clock < NextBuildTry)
	{
		return;
	}
	NextBuildTry = Clock + 1.f;
	int32 Builders = 0, Queued = 0, Sites = 0;
	for (const AVLKing* U : Mine)
	{
		Builders += U->KindId() == EVLUnitKind::Builder ? 1 : 0;
	}
	C->CountBuilders(Team, &Queued);
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		Sites += (S.Team == Team && S.IsAlive() && S.IsSite()) ? 1 : 0;
	}
	// only Builders build: none, nothing (Recruit trains one); and one site going up per Builder at a time
	if (Builders + Queued == 0 || Sites >= FMath::Max(1, Builders))
	{
		return;
	}
	const int32 Barracks = B->CountBuildings(EVLBuilding::Barracks, Team);
	const int32 Ranges = B->CountBuildings(EVLBuilding::Range, Team);
	const int32 Farms = B->CountBuildings(EVLBuilding::Farm, Team);
	const int32 Mines = B->CountBuildings(EVLBuilding::Mine, Team);
	const int32 Towers = B->CountBuildings(EVLBuilding::Tower, Team);
	const int32 Pop = B->GetPopulation(Team) + B->GetQueuedPopulation(Team);
	const int32 Cap = B->GetPopulationCap(Team);
	const int32 Food = B->GetStock(Team, EVLRes::Food), Gold = B->GetStock(Team, EVLRes::Gold);
	// the main game's AIBuildOrder (barracks, farm, range, mine, farm, tower, ...). A battle starts with the castle, one
	// mine and its tower, and nothing else: no farm (so no food coming in), no trainers. The farm first, as the player
	// must, then the trainers
	// (no mine in the order: mines are not built. A free mine of the map is claimed, by the wants below, through the
	// same CheckPlacement + PlaceBuilding as UVLConstruction::ClaimMine)
	static const EVLBuilding Order[] = { EVLBuilding::Farm, EVLBuilding::Barracks, EVLBuilding::Range, EVLBuilding::Farm, EVLBuilding::Tower };
	// (a trainer of the order that already stands, or is going up, is a step done)
	while (BuildStep < int32(UE_ARRAY_COUNT(Order)) && ((Order[BuildStep] == EVLBuilding::Barracks && Barracks > 0) || (Order[BuildStep] == EVLBuilding::Range && Ranges > 0)))
	{
		++BuildStep;
	}
	const bool bPastOrder = BuildStep >= int32(UE_ARRAY_COUNT(Order));
	// candidates in priority order: the first that can be placed is built; one that finds no room cools down
	struct FWant
	{
		EVLBuilding Kind;
		bool bInOrder;
		bool bNear;
		FVector Near;
		const TCHAR* Why;
	};
	TArray<FWant, TInlineAllocator<12>> Wants;
	auto Want = [&](EVLBuilding K, const TCHAR* Why, bool bInOrder = false, const FVector* Near = nullptr)
	{
		const int32 Limit = C->BuildLimit(K, Team);
		if (Limit != INDEX_NONE && C->CountRaised(K, Team) >= Limit)
		{
			if (bInOrder) { ++BuildStep; }
			return;                 // the castle's level allows no more (farms, towers)
		}
		const float* Until = BuildBlocked.Find(int32(K));
		if ((!Until || *Until <= Clock) && !Wants.ContainsByPredicate([K](const FWant& W) { return W.Kind == K; }))
		{
			Wants.Add({ K, bInOrder, Near != nullptr, Near ? *Near : FVector::ZeroVector, Why });
		}
	};
	// no food coming in comes before anything (troops are paid in food: the last farm lost is rebuilt first; the first
	// one is the build order's first step), then no way to train troops (a lost barracks or range)
	if (Farms == 0 && BuildStep > 0) { Want(EVLBuilding::Farm, TEXT("no farm")); }
	if (Barracks == 0 && BuildStep > 0) { Want(EVLBuilding::Barracks, TEXT("no barracks")); }
	if (Ranges == 0 && (bPastOrder || BuildStep > 0)) { Want(EVLBuilding::Range, TEXT("no range")); }
	// ---- the strategy's wants
	// raided: a tower by what was struck
	if (Clock - LastRaided < 90.f && Towers < 6)
	{
		bool bCovered = false;
		for (const FVLBuildingState& S : B->GetBuildings())
		{
			bCovered |= S.Team == Team && S.IsAlive() && S.Kind == EVLBuilding::Tower && FVector::Dist2D(S.Rest, RaidedAt) < 2200.f;
		}
		if (!bCovered) { Want(EVLBuilding::Tower, TEXT("raided"), false, &RaidedAt); }
	}
	// attacked early and often: a tower before the rest of the plan
	if (FoeAttacks >= 2 && Towers == 0 && Clock - LastFoeAttack < 120.f) { Want(EVLBuilding::Tower, TEXT("attacked")); }
	// its army behind the foe's: train faster (the kind its mix lacks first)
	if (ArmyRatio < 0.8f && Clock > 300.f && Gold > 250 && Barracks > 0 && Ranges > 0)       // (300: twice the 150 s it was)
	{
		if (Barracks < 2 && ShieldRatio >= 0.5f) { Want(EVLBuilding::Barracks, TEXT("army behind")); }
		if (Ranges < 2) { Want(EVLBuilding::Range, TEXT("army behind")); }
		if (Barracks < 2) { Want(EVLBuilding::Barracks, TEXT("army behind")); }
	}
	// holding a vein (Contest): claim it
	bool bFreeAtContest = false;
	if (Map.Points.IsValidIndex(ContestPoint))
	{
		for (const FVLAIPoint& P : Map.Points)
		{
			bFreeAtContest |= P.Kind == EVLAIPoint::Vein && VLAI::IsFreeVein(B, P.Actor.Get()) && FVector::Dist2D(P.Pos, Map.Points[ContestPoint].Pos) < 4000.f;
		}
	}
	if (Posture == EVLPosture::Contest && bFreeAtContest)
	{
		Want(EVLBuilding::Mine, TEXT("claim the contested vein"), false, &Map.Points[ContestPoint].Pos);
	}
	// quiet and veins free (Expand): a mine before the rest
	if (Posture == EVLPosture::Expand && bPastOrder && Mines < Farms + 1 && SafeVeins > 0) { Want(EVLBuilding::Mine, TEXT("expand")); }
	if (!bPastOrder)
	{
		Want(Order[BuildStep], TEXT("build order"), true);
	}
	else
	{
		if (Cap < B->GetPopulationCeiling(Team) && Pop >= Cap - 2) { Want(EVLBuilding::Farm, TEXT("housing")); }
		if (Food < 200 && Gold > 300) { Want(EVLBuilding::Farm, TEXT("food")); }                   // food is what troops cost
		if (Farms > Mines * 2 + 1 || Gold < 150) { Want(EVLBuilding::Mine, TEXT("gold")); }
		if (Towers < 1 + Mines / 2 + FMath::Min(FoeAttacks, 2)) { Want(EVLBuilding::Tower, TEXT("towers")); }
		if (Food > 450 && Barracks < 2) { Want(EVLBuilding::Barracks, TEXT("food to spare")); }             // food piling up: train faster
		if (Food > 450 && Ranges < 2) { Want(EVLBuilding::Range, TEXT("food to spare")); }
		// the storehouses (one of each): when a stock nears what the kingdom can hold, before it is wasted
		if (B->CountBuildings(EVLBuilding::Granary, Team) == 0 && Food >= B->GetStorage(Team, EVLRes::Food) * 0.8f)
		{
			Want(EVLBuilding::Granary, TEXT("food store nearly full"));
		}
		if (B->CountBuildings(EVLBuilding::Treasury, Team) == 0 && Gold >= B->GetStorage(Team, EVLRes::Gold) * 0.8f)
		{
			Want(EVLBuilding::Treasury, TEXT("gold store nearly full"));
		}
		Want(EVLBuilding::Farm, TEXT("more"));
		if (Gold > 600) { Want(EVLBuilding::Mine, TEXT("gold to spare")); Want(EVLBuilding::Tower, TEXT("gold to spare")); }      // gold to spare
	}
	for (const FWant& W : Wants)
	{
		const VLBuild::FSpec* Spec = VLBuild::Spec(W.Kind);
		if (!Spec || !B->CanAfford(Team, Spec->Cost))
		{
			break;                  // save up for the most wanted, do not spend it on the next
		}
		if (TryBuild(B, W.Kind, W.bNear ? &W.Near : nullptr))
		{
			if (W.bInOrder) { ++BuildStep; }
			NextBuildTry = Clock + Prof.BuildCadence;
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d: (the %s was wanted: %s)"), Team, VLRules::Name(W.Kind), W.Why);
			break;
		}
		// no room (or no free vein): skip it in the build order, and do not try it again for a while
		if (W.bInOrder) { ++BuildStep; }
		BuildBlocked.Add(int32(W.Kind), Clock + 25.f);
		UE_LOG(LogVoxelLab, Log, TEXT("AI %d: no room for a %s (%s)"), Team, VLRules::Name(W.Kind), W.Why);
	}
}

bool FVLCommander::TryBuild(UVLBattle* B, EVLBuilding Kind, const FVector* Near)
{
	UVLConstruction* C = UVLConstruction::Get(B);
	const AActor* Castle = B->GetCastle(Team);
	if (!C || !Castle)
	{
		return false;
	}
	const FVector Base = Castle->GetActorLocation();
	const FVector2D F2 = TowardFoe(B);
	const FVector Fwd(F2.X, F2.Y, 0.f), Side(-F2.Y, F2.X, 0.f);
	FVLPlacement P;
	bool bFound = false;
	// its front (gate, yard) toward the castle: the yaw whose front (+Y) faces back from Near to Base
	auto FacingCastle = [&Base](const FVector& At)
	{
		const FVector D = (Base - At).GetSafeNormal2D();
		return D.IsNearlyZero() ? 0.f : FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)) - 90.f;
	};
	// no site where the foe is clearly stronger (its Builder would die there)
	auto Safe = [&](const FVector& At) { return Influence.FoeAt(At) < Influence.OwnAt(At) + 1.f || Influence.FoeAt(At) < 0.6f; };
	if (Kind == EVLBuilding::Mine)
	{
		// the best free vein: near, safe, rich (the Crown's), the one it is holding first
		TArray<TPair<float, FVector>> Veins;
		TArray<AActor*> MineList;
		VLAI::MineActors(B, MineList);      // (B: the battle's cached list of the actors named as a gold mine)
		for (AActor* It : MineList)
		{
			FVector At;
			if (!VLAI::IsFreeVein(B, It, &At))
			{
				continue;
			}
			const float D = float(FVector::Dist2D(At, Base));
			const bool bHeld = Near && FVector::Dist2D(At, *Near) < 4000.f;
			// (380 m: it was 260, and on Realm v2 the west castle then had no neutral vein it would ever claim: its nearest
			// is 325 m off, while the east castle's is 154 m)
			if (D > 38000.f || (!bHeld && (!Safe(At) || (Prof.bAvoidTowers && InFoeReach(B, At, 300.f)))))
			{
				continue;
			}
			const float Score = (It->ActorHasTag(TEXT("Rich")) ? 1.4f : 1.f) / (1.f + D / 9000.f) + (bHeld ? 2.f : 0.f) + (Influence.OwnAt(At) > Influence.FoeAt(At) ? 0.2f : 0.f);
			Veins.Add({ Score, At });
		}
		Veins.Sort([](const TPair<float, FVector>& X, const TPair<float, FVector>& Y) { return X.Key > Y.Key; });
		for (const TPair<float, FVector>& V : Veins)
		{
			if (C->CheckPlacement(Kind, Team, V.Value, 0.f, P))
			{
				bFound = true;
				break;
			}
		}
	}
	else if (Kind == EVLBuilding::Tower)
	{
		// spread out: toward the foe, by a raided farm or mine (Near), or covering an outlying one once the foe has
		// struck; none within 15 m of another of its towers
		for (int32 Try = 0; Try < 6 && !bFound; ++Try)
		{
			FVector Cand = Base + Fwd * FMath::FRandRange(2000.f, 3600.f) + Side * FMath::FRandRange(-3000.f, 3000.f);
			if (Near && Try < 4)
			{
				Cand = *Near + Fwd * 700.f + Side * FMath::FRandRange(-700.f, 700.f);
			}
			else if (Try % 2 == 1 && FoeAttacks > 0)
			{
				TArray<const FVLBuildingState*> Outlying;
				for (const FVLBuildingState& S : B->GetBuildings())
				{
					if (S.Team == Team && S.IsAlive() && (S.Kind == EVLBuilding::Mine || S.Kind == EVLBuilding::Farm))
					{
						Outlying.Add(&S);
					}
				}
				if (Outlying.Num() > 0)
				{
					Cand = Outlying[FMath::RandRange(0, Outlying.Num() - 1)]->Rest + Fwd * 900.f;
				}
			}
			if (!C->FindPlacementNear(Kind, Team, Cand, 1500.f, FacingCastle(Cand), P, 30) || !Safe(P.Location))
			{
				continue;
			}
			bFound = true;
			for (const FVLBuildingState& S : B->GetBuildings())
			{
				if (S.Team == Team && S.IsAlive() && S.Kind == EVLBuilding::Tower && FVector::Dist2D(S.Rest, P.Location) < 1500.f)
				{
					bFound = false;
					break;
				}
			}
		}
	}
	else
	{
		FVector At = Base;
		float Radius = 4500.f;
		switch (Kind)
		{
		case EVLBuilding::Farm: At = Base - Fwd * 1800.f + Side * FMath::FRandRange(-2500.f, 2500.f); break;                     // behind the castle
		case EVLBuilding::Barracks:
		case EVLBuilding::Range: At = Base + Fwd * 600.f + Side * (FMath::RandBool() ? 1.f : -1.f) * FMath::FRandRange(2400.f, 3200.f); break;   // beside it, toward the foe
		default: break;
		}
		bFound = C->FindPlacementNear(Kind, Team, At, Radius, FacingCastle(At), P, 70) && Safe(P.Location);
		// No room there (a castle with the sea or a cliff behind it: Realm v2's east castle has its port there, and its
		// commander laid one farm in twenty minutes while the west one laid four): either side of the castle, then
		// anywhere round it further out.
		for (int32 Try = 0; Try < 3 && !bFound; ++Try)
		{
			const FVector Alt = Try < 2 ? Base + Side * (Try == 0 ? 3000.f : -3000.f) - Fwd * 600.f : Base;
			const float R = Try < 2 ? 4500.f : 7500.f;
			bFound = C->FindPlacementNear(Kind, Team, Alt, R, FacingCastle(Alt), P, Try < 2 ? 50 : 90) && Safe(P.Location);
		}
	}
	if (!bFound)
	{
		return false;
	}
	FString Why;
	const bool bLaid = C->PlaceBuilding(P, {}, &Why, true) != nullptr;
	UE_LOG(LogVoxelLab, Log, TEXT("AI %d: %s a %s at %.0f %.0f%s"), Team, bLaid ? TEXT("lays") : TEXT("could not lay"), VLRules::Name(Kind), P.Location.X, P.Location.Y, bLaid ? TEXT("") : *(TEXT(" (") + Why + TEXT(")")));
	return bLaid;
}

void FVLCommander::ManageTowers(UVLBattle* B, TArray<AVLKing*>& Pool)
{
	// archers on its watch towers' lookouts (Normal, Hard): they shoot from there at twice an archer's reach. Hurt
	// archers first; never the last few, and none from a body that is out
	if (Prof.TowerArchers <= 0 || Clock < NextGarrison)
	{
		return;
	}
	NextGarrison = Clock + 8.f;
	UVLCommand* Command = UVLCommand::Get(B);
	if (!Command)
	{
		return;
	}
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		AActor* Tower = S.Actor.Get();
		if (S.Team != Team || !S.IsWorking() || !UVLCommand::IsTower(Tower))
		{
			continue;
		}
		int32 Want = Prof.TowerArchers - Command->TowerCount(Tower);
		TArray<AVLKing*> All;
		B->GetUnits(Team, All, true);
		for (const AVLKing* U : All)
		{
			Want -= (U->PendingGarrison.Get() == Tower && !U->IsGarrisoned()) ? 1 : 0;     // (on its way up)
		}
		if (Want <= 0)
		{
			continue;
		}
		TArray<AVLKing*> Can;
		int32 Archers = 0;
		for (AVLKing* U : Pool)
		{
			if (!U->IsRanged())
			{
				continue;
			}
			++Archers;
			bool bOut = false;
			for (const FVLSquad& Sq : Squads)
			{
				bOut |= (Sq.IsOut() || Sq.Task == EVLSquadTask::Defend || Sq.Task == EVLSquadTask::Intercept) && Sq.Has(U);
			}
			if (!bOut && VLAI::Idle(U))
			{
				Can.Add(U);
			}
		}
		Can.Sort([](const AVLKing& X, const AVLKing& Y) { return X.GetHealthFrac() < Y.GetHealthFrac(); });
		TArray<AVLKing*> Send;
		for (AVLKing* U : Can)
		{
			if (Send.Num() < Want && Archers - Send.Num() > 2)
			{
				Send.Add(U);
			}
		}
		if (Send.Num() > 0)
		{
			Command->OrderGarrison(Send, Tower, false);
			Pool.RemoveAll([&Send](const AVLKing* U) { return Send.Contains(U); });
			for (FVLSquad& Sq : Squads)
			{
				Sq.Units.RemoveAll([&Send](const TWeakObjectPtr<AVLKing>& U) { return Send.Contains(U.Get()); });
			}
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d mans %s with %d archer(s)"), Team, *S.Name, Send.Num());
		}
	}
}

// ------------------------------------------------------------------------------------------------ scouting

void FVLCommander::ManageSpy(UVLBattle* B, const TArray<AVLKing*>& Mine)
{
	AVLKing* Spy = nullptr;
	int32 Core = 0;
	for (AVLKing* U : Mine)
	{
		if (U->KindId() == EVLUnitKind::Spy)
		{
			Spy = Spy ? Spy : U;
		}
		else if (U->KindId() != EVLUnitKind::Builder)
		{
			++Core;
		}
	}
	// its one Spy (Normal and Hard), once the army has a core: when the castle's level, the one-at-a-time rule, the
	// wait between two, its housing and its purse all allow it (the player's rules: UVLBattle::TrainRefusal)
	AActor* Castle = B->GetCastle(Team);
	if (!Spy && Prof.AdaptWeight > 0.f && Core >= 6 && Castle && B->TrainRefusal(Castle).IsEmpty())
	{
		if (B->Train(Castle, 1, true) > 0)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d: trains its spy"), Team);
		}
	}
	if (!Spy || Clock < NextSpyOrder || Spy->IsGarrisoned())
	{
		return;
	}
	NextSpyOrder = Clock + FMath::FRandRange(16.f, 28.f);
	UVLCommand* Command = UVLCommand::Get(B);
	if (!Command)
	{
		return;
	}
	// hurt (one more blow would finish it): home, and stay there as a look-out
	FVector Goal = MusterPoint(B);
	if (Spy->GetHealthFrac() >= 0.6f)
	{
		// a look-out point: beside one of the foe's buildings (its castle most often), far enough out that neither
		// its troops nor its towers would notice the Spy, close enough to see the place
		TArray<const FVLBuildingState*> Places;
		for (const FVLBuildingState& S : B->GetBuildings())
		{
			if (S.Team == Foe() && S.IsAlive())
			{
				Places.Add(&S);
			}
		}
		const AActor* FoeCastle = B->GetCastle(Foe());
		const AActor* At = (FoeCastle && (Places.Num() == 0 || FMath::FRand() < 0.4f)) ? FoeCastle : (Places.Num() > 0 ? Places[FMath::RandRange(0, Places.Num() - 1)]->Actor.Get() : nullptr);
		if (At)
		{
			const VLRules::FTroop& R = VLRules::Troop(EVLUnitKind::Spy);
			const FVLBuildingState* S = B->FindBuilding(At);
			const float Reach = S ? VLRules::Level(S->Kind, S->Level).Range : 0.f;
			// (the troops' sight: the archer's, the furthest, plus a little)
			const float Out = FMath::Clamp(FMath::Max(Reach, VLRules::Troop(EVLUnitKind::Archer).Sight + 100.f) * R.Notice + 500.f, 900.f, R.Sight * 0.8f);
			const float Angle = FMath::FRandRange(0.f, 2.f * PI);
			FVector Origin, Extent;
			At->GetActorBounds(true, Origin, Extent);
			Goal = FVector(Origin.X, Origin.Y, At->GetActorLocation().Z) + FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.f) * (Out + FMath::Max(Extent.X, Extent.Y));
		}
	}
	if (FVector::DistSquared2D(Spy->GetFeet(), Goal) < FMath::Square(300.f))
	{
		return;
	}
	// (OrderMove takes the goal to the nearest ground the unit can reach)
	Command->OrderMove({ Spy }, Goal, false, EVLFormation::Line);
	UE_LOG(LogVoxelLab, Verbose, TEXT("AI %d: spy to (%.0f, %.0f)"), Team, Goal.X, Goal.Y);
}

// ------------------------------------------------------------------------------------------------ report

const TCHAR* FVLCommander::PostureName(EVLPosture P)
{
	switch (P)
	{
	case EVLPosture::Expand: return TEXT("EXPAND");
	case EVLPosture::Defend: return TEXT("DEFEND");
	case EVLPosture::Contest: return TEXT("CONTEST");
	case EVLPosture::Harass: return TEXT("HARASS");
	case EVLPosture::Attack: return TEXT("ATTACK");
	case EVLPosture::Regroup: return TEXT("REGROUP");
	default: return TEXT("?");
	}
}

const TCHAR* FVLCommander::RoleName(EVLSquadRole R)
{
	switch (R)
	{
	case EVLSquadRole::Patrol: return TEXT("Patrol");
	case EVLSquadRole::Guard: return TEXT("Guard");
	case EVLSquadRole::Field: return TEXT("Field");
	case EVLSquadRole::Reserve: return TEXT("Reserve");
	case EVLSquadRole::Raid: return TEXT("Raid");
	case EVLSquadRole::Picket: return TEXT("Picket");
	default: return TEXT("Flank");
	}
}

const TCHAR* FVLCommander::TaskName(EVLSquadTask T)
{
	switch (T)
	{
	case EVLSquadTask::Idle: return TEXT("idle");
	case EVLSquadTask::Patrol: return TEXT("patrol");
	case EVLSquadTask::Guard: return TEXT("guard");
	case EVLSquadTask::Hold: return TEXT("hold");
	case EVLSquadTask::Attack: return TEXT("attack");
	case EVLSquadTask::Raid: return TEXT("raid");
	case EVLSquadTask::Defend: return TEXT("defend");
	case EVLSquadTask::Intercept: return TEXT("intercept");
	default: return TEXT("retreat");
	}
}

FString FVLCommander::Describe() const
{
	TArray<FString> Parts;
	for (const FVLSquad& S : Squads)
	{
		Parts.Add(FString::Printf(TEXT("%s %d %s%s"), RoleName(S.Role), S.Num(), TaskName(S.Task), S.GoalName.IsEmpty() ? TEXT("") : *(TEXT(" ") + S.GoalName)));
	}
	return FString::Printf(TEXT("clock %.0f s, %s (%s), army %.1f vs ~%.1f, waves %d (next in %.0f s), raids %d, seen %d foes (archers %.0f%%), wants %.0f%% swordsmen; squads: %s"), Clock,
		PostureName(Posture), PostureWhy.IsEmpty() ? TEXT("quiet") : *PostureWhy, ArmyPower, FoeArmyEstimate, WavesSent, NextWaveIn() < 1e5f ? NextWaveIn() : -1.f, RaidsSent, Seen.Num(),
		FoeArcherShare * 100.f, ShieldRatio * 100.f, Parts.Num() ? *FString::Join(Parts, TEXT("; ")) : TEXT("none"));
}

void FVLCommander::LogReport(UVLBattle* B, bool bMap) const
{
	UE_LOG(LogVoxelLab, Log, TEXT("==== AI %d (%s) at %d:%02d: posture %s for %.0f s (%s)"), Team, UVLBattle::DifficultyName(Difficulty), int32(Clock) / 60, int32(Clock) % 60, PostureName(Posture),
		Clock - PostureSince, PostureWhy.IsEmpty() ? TEXT("quiet") : *PostureWhy);
	UE_LOG(LogVoxelLab, Log, TEXT("  utilities: expand %.2f defend %.2f contest %.2f harass %.2f attack %.2f regroup %.2f; army %.1f vs ~%.1f (x%.2f), threat at home %.1f, lost lately %.1f"),
		Utility[0], Utility[1], Utility[2], Utility[3], Utility[4], Utility[5], ArmyPower, FoeArmyEstimate, ArmyRatio, HomeThreat, RecentLoss(45.f));
	UE_LOG(LogVoxelLab, Log, TEXT("  micro so far: %d focus-fire orders, %d steps back, %d pulled back, %d interceptions; waves %d, raids %d; next wave in %.0f s, next raid in %.0f s"),
		Stat[0], Stat[1], Stat[2], Stat[3], WavesSent, RaidsSent, NextWaveIn() < 1e5f ? NextWaveIn() : -1.f, NextRaidTime < 1e5f ? NextRaidTime - Clock : -1.f);
	UVLCommand* Command = UVLCommand::Get(B);
	for (const FVLSquad& S : Squads)
	{
		TArray<AVLKing*> W;
		FVector C;
		S.Gather(W, C);
		TArray<FString> Who;
		for (AVLKing* U : W)
		{
			const FVector F = U->GetFeet();
			Who.Add(FString::Printf(TEXT("%s %.0f%% (%.0f, %.0f)%s%s"), *U->GetDisplayName(), U->GetHealthFrac() * 100.f, F.X, F.Y, U->HasOrder() ? TEXT(" walking") : TEXT(""),
				Command ? *(TEXT(" ") + Command->DescribeOrders({ U })) : TEXT("")));
		}
		UE_LOG(LogVoxelLab, Log, TEXT("  squad %s#%d: %s %s for %.0f s, %d troops power %.1f at (%.0f, %.0f) -> (%.0f, %.0f)%s: %s"), RoleName(S.Role), S.Id, TaskName(S.Task), *S.GoalName, Clock - S.TaskSince,
			W.Num(), SumPower(W), C.X, C.Y, S.Goal.X, S.Goal.Y, S.Target.IsValid() ? *(TEXT(" target ") + S.Target->GetName()) : TEXT(""), *FString::Join(Who, TEXT(", ")));
	}
	for (const FVLFoeGroup& G : FoeGroups)
	{
		UE_LOG(LogVoxelLab, Log, TEXT("  foe body: %d troops power %.1f at (%.0f, %.0f)%s%s"), G.Count, G.Power, G.Centre.X, G.Centre.Y, G.bExposed ? TEXT(", exposed") : TEXT(""), G.bAtOurHome ? TEXT(", AT OUR HOME") : TEXT(""));
	}
	for (const FVLAIEvent& E : Events)
	{
		if (Clock - E.Time < 120.f && E.Kind != EVLAIEvent::UnitLost)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("  event %.0f s ago: %s, %s"), Clock - E.Time, VLAI::EventName(E.Kind), *E.What);
		}
	}
	UE_LOG(LogVoxelLab, Log, TEXT("  troops lost in the last 45 s: %.1f power; map: %s"), RecentLoss(45.f), *Map.Describe());
	if (bMap && Influence.IsValid())
	{
		// the influence map, +X up: o / O its strength, x / X the foe's (as far as it knows), # both; C its castle, K the
		// foe's, letters its squads (P patrol, G guard, F field, R raid / reserve, L flank, W picket), * the map's points
		TMap<FIntPoint, TCHAR> Marks;
		for (const FVLAIPoint& P : Map.Points)
		{
			Marks.Add(Influence.CellOf(P.Pos), TEXT('*'));
		}
		Marks.Add(Influence.CellOf(Map.Castle[Team]), TEXT('C'));
		Marks.Add(Influence.CellOf(Map.Castle[Foe()]), TEXT('K'));
		for (const FVLSquad& S : Squads)
		{
			TArray<AVLKing*> W;
			FVector C;
			S.Gather(W, C);
			if (W.Num() > 0)
			{
				static const TCHAR Letter[] = { TEXT('P'), TEXT('G'), TEXT('F'), TEXT('R'), TEXT('R'), TEXT('L'), TEXT('W') };
				Marks.Add(Influence.CellOf(C), Letter[int32(S.Role)]);
			}
		}
		TArray<FString> Lines;
		Influence.Ascii(Marks).ParseIntoArrayLines(Lines);
		UE_LOG(LogVoxelLab, Log, TEXT("  influence map (10 m cells, +X up, +Y right):"));
		for (const FString& L : Lines)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("%s"), *L);
		}
	}
}

void FVLCommander::DebugDraw(UVLBattle* B) const
{
#if ENABLE_DRAW_DEBUG
	UWorld* World = B->GetWorld();
	const float Life = Prof.Think + 0.05f;
	const FColor Col = Team == 1 ? FColor(255, 70, 50) : FColor(60, 140, 255);
	for (const FVLSquad& S : Squads)
	{
		TArray<AVLKing*> W;
		FVector C;
		S.Gather(W, C);
		if (W.Num() == 0)
		{
			continue;
		}
		DrawDebugSphere(World, C + FVector(0, 0, 250), 120.f, 8, Col, false, Life, 0, 6.f);
		DrawDebugLine(World, C + FVector(0, 0, 250), S.Goal + FVector(0, 0, 100), Col, false, Life, 0, 4.f);
		DrawDebugString(World, C + FVector(0, 0, 420), FString::Printf(TEXT("%s %d: %s %s"), RoleName(S.Role), W.Num(), TaskName(S.Task), *S.GoalName), nullptr, Col, Life, true, 1.2f);
	}
	for (const FVLAIPoint& P : Map.Points)
	{
		DrawDebugCylinder(World, P.Pos, P.Pos + FVector(0, 0, 600), 300.f, 12, FColor::Yellow, false, Life, 0, 3.f);
	}
	if (Influence.IsValid())
	{
		for (int32 X = 0; X < Influence.DimX; ++X)
		{
			for (int32 Y = 0; Y < Influence.DimY; ++Y)
			{
				const float O = Influence.Own[Y * Influence.DimX + X], F = Influence.Foe[Y * Influence.DimX + X];
				if (O + F < 0.3f)
				{
					continue;
				}
				const FVector P(Influence.Origin.X + (X + 0.5f) * Influence.Cell, Influence.Origin.Y + (Y + 0.5f) * Influence.Cell, Map.Castle[Team].Z + 900.f);
				const uint8 R = uint8(FMath::Clamp(F * 60.f, 0.f, 255.f)), G = uint8(FMath::Clamp(O * 60.f, 0.f, 255.f));
				DrawDebugPoint(World, P, 10.f, FColor(R, G, 40), false, Life);
			}
		}
	}
#endif
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdAIReport(TEXT("vl.AI"), TEXT("vl.AI [team 0|1] [nomap]: log the commander's full picture: posture and utilities, squads and their troops, foe bodies, events, the map's points and the influence map"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			const int32 Team = Args.Num() > 0 && Args[0].IsNumeric() ? FMath::Clamp(FCString::Atoi(*Args[0]), 0, 1) : 1;
			const FVLCommander* C = Battle ? Battle->GetCommander(Team) : nullptr;
			if (!C || !C->bActive)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("AI: no active commander for team %d (a battle map with both castles, vl.StartMatch; vl.AIvsAI 1 for team 0)"), Team);
				return;
			}
			C->LogReport(Battle, !Args.Contains(TEXT("nomap")));
		}));

	// Test hooks for the commander's attack clock (Tools/feedback_test.py): an attack forced now, a flank bridge added
	// where a map has none, the flank party struck down, and the clock's state logged.
	FAutoConsoleCommandWithWorldAndArgs CmdAIForce(TEXT("vl.AIForce"), TEXT("vl.AIForce <team> attack | flank X0 Y0 X1 Y1 | killflank | killfield | state | off | on: test hooks for the commander's attacks (attack: its next attack is due now and it has waited; flank: a flank bridge from X0 Y0 (team 0's end) to X1 Y1)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			const int32 Team = Args.Num() > 0 ? FMath::Clamp(FCString::Atoi(*Args[0]), 0, 1) : 1;
			FVLCommander* C = Battle ? Battle->GetCommander(Team) : nullptr;
			const FString What = Args.Num() > 1 ? Args[1].ToLower() : FString(TEXT("state"));
			if (C && (What == TEXT("off") || What == TEXT("on")))
			{
				C->bActive = What == TEXT("on");        // (off: its troops stand as they are, for tests of the player's orders)
				UE_LOG(LogVoxelLab, Log, TEXT("aiforce: team %d's commander %s"), Team, C->bActive ? TEXT("on") : TEXT("off"));
				return;
			}
			if (!C || !C->bActive)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("aiforce: no active commander for team %d"), Team);
				return;
			}
			auto Ground = [World](float X, float Y) -> FVector
			{
				FHitResult Hit;
				FCollisionQueryParams Q;
				if (World->LineTraceSingleByChannel(Hit, FVector(X, Y, 60000.f), FVector(X, Y, -60000.f), ECC_WorldStatic, Q))
				{
					return Hit.ImpactPoint;
				}
				return FVector(X, Y, 0.f);
			};
			if (What == TEXT("attack"))
			{
				C->NextWaveTime = C->Clock - 200.f;      // (due, and it has waited: it goes at near-even odds)
				C->StrategyClock = C->Clock;
			}
			else if (What == TEXT("flank") && Args.Num() >= 6)
			{
				FVLAIPoint P;
				P.Kind = EVLAIPoint::Flank;
				P.Name = TEXT("Test flank");
				P.End[0] = Ground(FCString::Atof(*Args[2]), FCString::Atof(*Args[3]));
				P.End[1] = Ground(FCString::Atof(*Args[4]), FCString::Atof(*Args[5]));
				P.Pos = 0.5f * (P.End[0] + P.End[1]);
				P.Value = 0.3f;
				C->Map.Points.Add(P);
				UE_LOG(LogVoxelLab, Log, TEXT("aiforce: team %d's map has a flank from %s to %s"), Team, *P.End[0].ToCompactString(), *P.End[1].ToCompactString());
			}
			else if (What == TEXT("killflank") || What == TEXT("killfield"))
			{
				const EVLSquadRole Role = What == TEXT("killflank") ? EVLSquadRole::Flank : EVLSquadRole::Field;
				int32 N = 0;
				for (FVLSquad& S : C->Squads)
				{
					if (S.Role != Role)
					{
						continue;
					}
					for (const TWeakObjectPtr<AVLKing>& U : S.Units)
					{
						if (U.IsValid() && U->IsAlive())
						{
							Battle->Damage(U.Get(), 1e6f, nullptr, 1 - Team);
							++N;
						}
					}
				}
				UE_LOG(LogVoxelLab, Log, TEXT("aiforce: team %d's %s struck down (%d)"), Team, FVLCommander::RoleName(Role), N);
			}
			FString Sq;
			for (const FVLSquad& S : C->Squads)
			{
				Sq += FString::Printf(TEXT(" %s#%d %d %s%s"), FVLCommander::RoleName(S.Role), S.Id, S.Num(), FVLCommander::TaskName(S.Task),
					S.Departs > 0.f ? *FString::Printf(TEXT(" (departs in %.0f s)"), S.Departs - C->Clock) : TEXT(""));
			}
			UE_LOG(LogVoxelLab, Log, TEXT("aiforce: team %d clock %.0f next attack in %.0f s (max wait %.0f), attacking %d, waves %d, posture %s, status \"%s\" |%s"), Team, C->Clock, C->NextWaveIn(),
				C->MaxWaveWait(), C->IsAttacking() ? 1 : 0, C->WavesSent, FVLCommander::PostureName(C->Posture), Team == 1 ? *Battle->EnemyStatus() : TEXT("-"), *Sq);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdTimeScale(TEXT("vl.TimeScale"), TEXT("vl.TimeScale N: the game runs N times as fast (tests of whole matches; 1 = normal)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (World && World->GetWorldSettings())
			{
				const float N = Args.Num() ? FMath::Clamp(FCString::Atof(*Args[0]), 0.1f, 8.f) : 1.f;
				World->GetWorldSettings()->SetTimeDilation(N);
				UE_LOG(LogVoxelLab, Log, TEXT("time scale %.2f"), World->GetWorldSettings()->TimeDilation);
			}
		}));
}
