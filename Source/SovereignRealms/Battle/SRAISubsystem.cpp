// Copyright Sovereign Realms.

#include "Battle/SRAISubsystem.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Units/SRUnit.h"
#include "Common/SRAudioSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"

#define LOCTEXT_NAMESPACE "SRAI"

USRAISubsystem* USRAISubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USRAISubsystem>() : nullptr;
}

bool USRAISubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

float USRAISubsystem::DifficultyScale(float Easy, float Normal, float Hard) const
{
	const int32 D = USRFeelSettings::Get().AIDifficulty;
	return D <= 0 ? Easy : (D >= 2 ? Hard : Normal);
}

void USRAISubsystem::Reset()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const bool bPlayerAI = Commanders[0].bActive || F.bAIPlaysPlayer;
	Clock = 0.f;
	for (int32 t = 0; t < 2; ++t)
	{
		FSRCommander& C = Commanders[t];
		C = FSRCommander();
		C.Team = t == 0 ? ESRTeam::Player : ESRTeam::Enemy;
		C.bActive = t == 1 || bPlayerAI;
		C.ThinkClock = FMath::FRandRange(0.f, F.AIThinkInterval);
		C.NextWaveTime = F.AIFirstWaveTime * DifficultyScale(1.45f, 1.f, 0.72f);
		C.NextBuildTry = 4.f;
	}
	UE_LOG(LogSovereign, Log, TEXT("AI reset: enemy commander on (difficulty %d), player commander %s, first wave at %.0fs"),
		F.AIDifficulty, Commanders[0].bActive ? TEXT("ON") : TEXT("off"), Commanders[1].NextWaveTime);
}

void USRAISubsystem::SetPlayerAI(bool bEnabled)
{
	Commanders[0].bActive = bEnabled;
	if (bEnabled && Commanders[0].NextWaveTime <= 0.f)
	{
		Commanders[0].NextWaveTime = Clock + USRFeelSettings::Get().AIFirstWaveTime;
	}
	UE_LOG(LogSovereign, Log, TEXT("AI player commander %s"), bEnabled ? TEXT("ON") : TEXT("OFF"));
}

float USRAISubsystem::GetEnemyNextWaveIn() const
{
	return Commanders[1].NextWaveTime - Clock;
}

void USRAISubsystem::Step(float Dt)
{
	Clock += Dt;
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (Battle && Battle->GetResult() != ESRBattleResult::Ongoing) { return; }
	for (FSRCommander& C : Commanders)
	{
		if (!C.bActive) { continue; }
		C.ThinkClock -= Dt;
		if (C.ThinkClock > 0.f) { continue; }
		C.ThinkClock = F.AIThinkInterval;
		Think(C);
	}
}

FVector2D USRAISubsystem::TowardFoe(const FSRCommander& C) const
{
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	const ASRBuilding* Mine = Eco ? Eco->GetCastle(C.Team) : nullptr;
	const ASRBuilding* Foe = Eco ? Eco->GetCastle(C.Team == ESRTeam::Player ? ESRTeam::Enemy : ESRTeam::Player) : nullptr;
	if (Mine && Foe) { return (Foe->GetFootprintCentre() - Mine->GetFootprintCentre()).GetSafeNormal(); }
	return C.Team == ESRTeam::Enemy ? FVector2D(-0.7f, -0.7f) : FVector2D(0.7f, 0.7f);
}

FVector2D USRAISubsystem::MusterPoint(const FSRCommander& C) const
{
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	const ASRBuilding* Castle = Eco ? Eco->GetCastle(C.Team) : nullptr;
	if (!Castle) { return FVector2D::ZeroVector; }
	FVector2D P = Castle->GetFootprintCentre() + TowardFoe(C) * 1500.f;
	if (const USRGridSubsystem* Grid = USRGridSubsystem::Get(this)) { P = Grid->NearestWalkable(P); }
	return P;
}

ASRBuilding* USRAISubsystem::PickWaveTarget(const FSRCommander& C, const FVector2D& From) const
{
	// The foe's nearest standing building: outlying farms, mines and towers fall first, then the castle.
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Eco) { return nullptr; }
	ASRBuilding* Best = nullptr;
	float BestD = TNumericLimits<float>::Max();
	for (ASRBuilding* B : Eco->GetBuildings())
	{
		if (!B || !B->IsAlive() || B->Team == C.Team) { continue; }
		float D = FVector2D::Distance(B->GetFootprintCentre(), From);
		if (B->BuildingType == ESRBuildingType::Tower) { D *= 1.25f; } // towers bite: go round them if something else is close
		if (D < BestD) { BestD = D; Best = B; }
	}
	return Best;
}

void USRAISubsystem::Think(FSRCommander& C)
{
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Battle || !Eco || !Eco->GetCastle(C.Team)) { return; }

	// Who is ours, and who is not already marching in the wave.
	for (int32 i = C.Wave.Num() - 1; i >= 0; --i) { if (!C.Wave[i].IsValid() || !C.Wave[i]->IsAlive()) { C.Wave.RemoveAt(i); } }
	TArray<ASRUnit*> Mine, Home;
	for (ASRUnit* U : Battle->GetUnits())
	{
		if (!U || !U->IsActive() || U->GetTeam() != C.Team) { continue; }
		Mine.Add(U);
		if (!C.Wave.Contains(U)) { Home.Add(U); }
	}

	ManageEconomy(C, Mine);
	ManageArmy(C, Home, Mine);
	ManageWave(C);
}

bool USRAISubsystem::TryBuild(FSRCommander& C, ESRBuildingType Type)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	const ASRBuilding* Castle = Eco ? Eco->GetCastle(C.Team) : nullptr;
	if (!Eco || !Grid || !Castle) { return false; }
	if (!Eco->CanAfford(C.Team, F.BuildingStatsFor(Type).Cost)) { return false; }

	const FVector2D Base = Castle->GetFootprintCentre();
	const FVector2D Fwd = TowardFoe(C);
	const FVector2D Side(-Fwd.Y, Fwd.X);
	FVector2D Near = Base;
	float Radius = 3200.f;
	switch (Type)
	{
	case ESRBuildingType::Farm: Near = Base - Fwd * 900.f + Side * FMath::FRandRange(-1800.f, 1800.f); Radius = 3000.f; break; // behind the castle
	case ESRBuildingType::Tower: Near = Base + Fwd * FMath::FRandRange(1600.f, 2600.f) + Side * FMath::FRandRange(-1400.f, 1400.f); Radius = 1600.f; break;
	case ESRBuildingType::Mine: Near = Base; Radius = 16000.f; break; // the nearest free vein, wherever it is
	default: break;
	}
	FSRPlacement P;
	if (Type == ESRBuildingType::Tower)
	{
		// Spread the towers: try a few candidate spots and take the first that is well clear of our other towers.
		bool bFound = false;
		for (int32 Try = 0; Try < 8 && !bFound; ++Try)
		{
			const FVector2D Cand = Base + Fwd * FMath::FRandRange(1400.f, 3000.f) + Side * FMath::FRandRange(-2400.f, 2400.f);
			if (!Grid->FindPlacementNear(Type, C.Team, Cand, 800.f, P)) { continue; }
			bFound = true;
			for (const ASRBuilding* B : Eco->GetBuildings())
			{
				if (B && B->Team == C.Team && B->BuildingType == ESRBuildingType::Tower && FVector2D::Distance(B->GetFootprintCentre(), FVector2D(P.Location)) < 1000.f)
				{
					bFound = false;
					break;
				}
			}
		}
		if (!bFound) { return false; }
	}
	else if (!Grid->FindPlacementNear(Type, C.Team, Near, Radius, P)) { return false; }
	FText Why;
	return Eco->PlaceBuilding(Type, C.Team, FVector2D(P.Location) + (F.BuildingStatsFor(Type).FootprintMin + F.BuildingStatsFor(Type).FootprintMax) * 0.5f, &Why) != nullptr;
}

void USRAISubsystem::ManageEconomy(FSRCommander& C, const TArray<ASRUnit*>& Mine)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	ASRBuilding* Castle = Eco->GetCastle(C.Team);

	// ---- buildings: the build order, then housing and veins as needed ----
	if (Clock >= C.NextBuildTry)
	{
		ESRBuildingType Want = ESRBuildingType::Farm;
		bool bHave = false;
		if (F.AIBuildOrder.IsValidIndex(C.BuildStep)) { Want = F.AIBuildOrder[C.BuildStep]; bHave = true; }
		else
		{
			const int32 Pop = Eco->GetPopulation(C.Team) + Eco->GetQueuedPopulation(C.Team);
			const int32 Cap = Eco->GetPopulationCap(C.Team);
			const int32 Mines = Eco->CountBuildings(ESRBuildingType::Mine, C.Team);
			const int32 Farms = Eco->CountBuildings(ESRBuildingType::Farm, C.Team);
			const int32 Towers = Eco->CountBuildings(ESRBuildingType::Tower, C.Team);
			if (Cap < F.MaxPopulation && Pop >= Cap - 3) { Want = ESRBuildingType::Farm; bHave = true; }
			else if (Farms > Mines * 2 + 1) { Want = ESRBuildingType::Mine; bHave = true; }
			else if (Towers < FMath::Min(1 + Mines / 2, 4)) { Want = ESRBuildingType::Tower; bHave = true; }
			else if (Farms < 8) { Want = ESRBuildingType::Farm; bHave = true; }
		}
		if (bHave)
		{
			if (TryBuild(C, Want))
			{
				++C.BuildStep;
				C.NextBuildTry = Clock + 3.f;
			}
			else if (Want == ESRBuildingType::Mine && Eco->CanAfford(C.Team, F.BuildingStatsFor(Want).Cost))
			{
				++C.BuildStep;          // no free vein reachable: skip it rather than stall the whole order
				C.NextBuildTry = Clock + 2.f;
			}
		}
	}

	// ---- troops: keep the castle busy while food and housing last ----
	if (Castle && Castle->CanRecruit() && Castle->GetQueue().Num() < 2)
	{
		int32 Shields = 0, Total = 0;
		for (const ASRUnit* U : Mine) { Shields += U->GetUnitType() == ESRUnitType::Shieldbearer ? 1 : 0; ++Total; }
		for (ESRUnitType T : Castle->GetQueue()) { Shields += T == ESRUnitType::Shieldbearer ? 1 : 0; ++Total; }
		const ESRUnitType Type = (Total == 0 || float(Shields) / Total < F.AIShieldRatio) ? ESRUnitType::Shieldbearer : ESRUnitType::Archer;
		// Hold a little gold back while a building is wanted? No: troops cost food, buildings gold; they never compete.
		const bool bRoom = Eco->GetPopulation(C.Team) + Eco->GetQueuedPopulation(C.Team) + F.StatsFor(Type).PopCost <= Eco->GetPopulationCap(C.Team);
		if (bRoom && Eco->CanAfford(C.Team, F.CostFor(Type))) { Castle->QueueRecruit(Type); }
	}
	if (Castle) { Castle->SetRallyPoint(MusterPoint(C)); }
}

void USRAISubsystem::ManageArmy(FSRCommander& C, TArray<ASRUnit*>& Home, const TArray<ASRUnit*>& Mine)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);

	// ---- threats near our buildings ----
	FVector2D ThreatSum = FVector2D::ZeroVector;
	int32 Threats = 0;
	for (ASRUnit* U : Battle->GetUnits())
	{
		if (!U || !U->IsActive() || U->GetTeam() == C.Team) { continue; }
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (B && B->Team == C.Team && B->IsAlive() && FVector2D::DistSquared(B->GetFootprintCentre(), U->GetPos2D()) < FMath::Square(F.AIDefendRadius))
			{
				ThreatSum += U->GetPos2D();
				++Threats;
				break;
			}
		}
	}

	if (Threats > 0)
	{
		const FVector2D ThreatAt = ThreatSum / Threats;
		C.bDefending = true;
		// Everyone at home who is not already fighting goes to meet them.
		TArray<ASRUnit*> Free;
		for (ASRUnit* U : Home) { if (!U->IsEngaged()) { Free.Add(U); } }
		if (Free.Num() > 0 && Clock - C.LastHomeOrder > 2.f)
		{
			Battle->CommandMove(Free, ThreatAt, true, ESRFormationShape::Line, false);
			C.LastHomeOrder = Clock;
		}
		// A wave that has barely left comes back if home is badly outnumbered.
		if (C.Wave.Num() > 0 && Threats > Home.Num() * 2)
		{
			const ASRBuilding* Castle = Eco->GetCastle(C.Team);
			if (Castle && FVector2D::Distance(C.Wave[0]->GetPos2D(), Castle->GetFootprintCentre()) < 6000.f)
			{
				TArray<ASRUnit*> W;
				for (const TWeakObjectPtr<ASRUnit>& P : C.Wave) { if (P.IsValid()) { W.Add(P.Get()); } }
				Battle->CommandMove(W, ThreatAt, true, ESRFormationShape::Line, false);
				C.Wave.Reset();
				UE_LOG(LogSovereign, Log, TEXT("AI %s recalls its wave to defend (%d threats)"), C.Team == ESRTeam::Enemy ? TEXT("enemy") : TEXT("player"), Threats);
			}
		}
		return;
	}

	// ---- quiet: gather idle troops at the muster point ----
	if (C.bDefending || Clock - C.LastHomeOrder > 6.f)
	{
		C.bDefending = false;
		const FVector2D Muster = MusterPoint(C);
		TArray<ASRUnit*> Stray;
		for (ASRUnit* U : Home)
		{
			if (!U->IsEngaged() && U->GetOrder() == ESROrder::Idle && FVector2D::Distance(U->GetPos2D(), Muster) > 900.f) { Stray.Add(U); }
		}
		if (Stray.Num() > 0) { Battle->CommandMove(Stray, Muster, true, ESRFormationShape::Square, false); }
		C.LastHomeOrder = Clock;
	}

	// ---- launch a wave ----
	int32 WaveSize = FMath::Min(F.AIWaveSizeMax, FMath::RoundToInt((F.AIWaveSizeStart + C.WavesSent * F.AIWaveGrowth) * DifficultyScale(0.75f, 1.f, 1.25f)));
	const int32 Spare = Home.Num() - FMath::FloorToInt(Home.Num() * F.AIGarrisonFraction);
	// With the army at its housing limit there is nothing to gain by waiting: push with everything but the garrison.
	const bool bMaxed = Eco->GetPopulation(C.Team) >= Eco->GetPopulationCap(C.Team) - 2 && Eco->GetPopulationCap(C.Team) >= 30;
	if (bMaxed) { WaveSize = FMath::Max(WaveSize, Spare); }
	const int32 Sendable = FMath::Min(WaveSize, Spare);
	if (C.Wave.Num() == 0 && Clock >= C.NextWaveTime && Sendable >= WaveSize)
	{
		Home.Sort([](const ASRUnit& A, const ASRUnit& B) { return A.GetUnitType() < B.GetUnitType(); }); // shields first
		// Keep a mixed garrison: leave behind every k-th troop so both types stay home.
		const int32 Keep = Home.Num() - Sendable;
		TSet<int32> Stay;
		for (int32 k = 0; k < Keep; ++k) { Stay.Add((k * Home.Num()) / FMath::Max(Keep, 1) + Home.Num() / FMath::Max(2 * Keep, 1)); }
		TArray<ASRUnit*> Send;
		for (int32 i = 0; i < Home.Num(); ++i) { if (!Stay.Contains(i)) { Send.Add(Home[i]); } }
		while (Send.Num() > Sendable) { Send.Pop(); }

		const FVector2D From = MusterPoint(C);
		ASRBuilding* Target = PickWaveTarget(C, From);
		if (!Target) { return; }
		C.Wave.Reset();
		for (ASRUnit* U : Send) { C.Wave.Add(U); U->SetStance(ESRStance::Aggressive); }
		C.WaveStartSize = Send.Num();
		C.WaveLaunched = Clock;
		C.WaveLastFight = Clock;
		C.WaveTarget = Target;
		C.WaveGoal = Target->ClosestPointOnFootprint(From, 250.f);
		C.WaveReorder = 0.f;
		++C.WavesSent;
		C.NextWaveTime = Clock + F.AIWaveInterval * DifficultyScale(1.4f, 1.f, 0.78f);
		Battle->CommandMove(Send, C.WaveGoal, true, ESRFormationShape::Line, false);
		UE_LOG(LogSovereign, Log, TEXT("AI %s sends wave %d: %d troops at %s (%.0f, %.0f)"), C.Team == ESRTeam::Enemy ? TEXT("enemy") : TEXT("player"),
			C.WavesSent, Send.Num(), *Target->GetDisplayName(), C.WaveGoal.X, C.WaveGoal.Y);
		if (C.Team == ESRTeam::Enemy)
		{
			if (USREconomySubsystem* E = USREconomySubsystem::Get(this))
			{
				const FVector2D At = From;
				E->PushAlert(ESRAlertKind::EnemyWave, FText::Format(LOCTEXT("Wave", "The enemy marches on you with {0} troops!"), FText::AsNumber(Send.Num())), &At);
			}
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::WarHorn); }
		}
	}
}

void USRAISubsystem::ManageWave(FSRCommander& C)
{
	if (C.Wave.Num() == 0) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);

	TArray<ASRUnit*> W;
	FVector2D Centre = FVector2D::ZeroVector;
	for (const TWeakObjectPtr<ASRUnit>& P : C.Wave) { if (P.IsValid()) { W.Add(P.Get()); Centre += P->GetPos2D(); } }
	if (W.Num() == 0) { C.Wave.Reset(); return; }
	Centre /= W.Num();

	// Losing badly where it fights: fall back home and rebuild.
	int32 Foes = 0;
	for (const ASRUnit* U : Battle->GetUnits())
	{
		if (U && U->IsActive() && U->GetTeam() != C.Team && FVector2D::DistSquared(U->GetPos2D(), Centre) < FMath::Square(1800.f)) { ++Foes; }
	}
	if (W.Num() <= FMath::CeilToInt(C.WaveStartSize * F.AIRetreatFraction) && Foes > W.Num())
	{
		Battle->CommandMove(W, MusterPoint(C), false, ESRFormationShape::Column, false);
		UE_LOG(LogSovereign, Log, TEXT("AI %s wave retreats (%d left of %d, %d foes near)"), C.Team == ESRTeam::Enemy ? TEXT("enemy") : TEXT("player"), W.Num(), C.WaveStartSize, Foes);
		C.Wave.Reset();
		return;
	}

	// A wave that has stopped fighting for a long while (lost its way, target out of reach), or that is down to a
	// handful with nobody near, goes home and rejoins the army instead of blocking the next wave.
	bool bFighting = false;
	for (const ASRUnit* U : W) { if (U->IsEngaged()) { bFighting = true; break; } }
	if (bFighting) { C.WaveLastFight = Clock; }
	if ((Clock - C.WaveLastFight > 150.f) || (W.Num() <= 3 && Foes == 0 && Clock - C.WaveLaunched > 60.f))
	{
		Battle->CommandMove(W, MusterPoint(C), false, ESRFormationShape::Column, false);
		UE_LOG(LogSovereign, Log, TEXT("AI %s wave returns home (%d left, idle %.0fs)"), C.Team == ESRTeam::Enemy ? TEXT("enemy") : TEXT("player"), W.Num(), Clock - C.WaveLastFight);
		C.Wave.Reset();
		return;
	}

	// Target fell (or the wave got there and stands idle): on to the next building, ending at the castle.
	C.WaveReorder -= F.AIThinkInterval;
	bool bIdle = true;
	for (const ASRUnit* U : W) { if (U->IsEngaged() || U->GetOrder() != ESROrder::Idle) { bIdle = false; break; } }
	if (!C.WaveTarget.IsValid() || !C.WaveTarget->IsAlive() || (bIdle && C.WaveReorder <= 0.f))
	{
		ASRBuilding* Next = PickWaveTarget(C, Centre);
		if (!Next) { return; }
		C.WaveTarget = Next;
		C.WaveGoal = Next->ClosestPointOnFootprint(Centre, 250.f);
		C.WaveReorder = 6.f;
		Battle->CommandMove(W, C.WaveGoal, true, ESRFormationShape::Line, false);
	}
	else if (bIdle)
	{
		// at the target with nothing to fight: knock it down
		Battle->CommandAttackBuilding(W, C.WaveTarget.Get());
		C.WaveReorder = 6.f;
	}
}

void USRAISubsystem::LogStatus() const
{
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	for (const FSRCommander& C : Commanders)
	{
		if (!C.bActive || !Eco) { continue; }
		UE_LOG(LogSovereign, Log, TEXT("AI %s: t=%.0fs gold=%d food=%d pop=%d/%d farms=%d mines=%d towers=%d waves=%d (wave now %d) next wave in %.0fs"),
			C.Team == ESRTeam::Enemy ? TEXT("enemy") : TEXT("player"), Clock, Eco->GetResource(C.Team, ESRResource::Gold), Eco->GetResource(C.Team, ESRResource::Food),
			Eco->GetPopulation(C.Team), Eco->GetPopulationCap(C.Team), Eco->CountBuildings(ESRBuildingType::Farm, C.Team), Eco->CountBuildings(ESRBuildingType::Mine, C.Team),
			Eco->CountBuildings(ESRBuildingType::Tower, C.Team), C.WavesSent, C.Wave.Num(), C.NextWaveTime - Clock);
	}
}

#undef LOCTEXT_NAMESPACE
