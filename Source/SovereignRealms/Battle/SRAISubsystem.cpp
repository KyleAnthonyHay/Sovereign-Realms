// Copyright Sovereign Realms.

#include "Battle/SRAISubsystem.h"
#include "Common/SRSaveGame.h"
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

namespace
{
	const TCHAR* Side(const FSRCommander& C) { return C.Team == ESRTeam::Enemy ? TEXT("enemy") : TEXT("player"); }
	ESRTeam Foe(ESRTeam T) { return T == ESRTeam::Player ? ESRTeam::Enemy : ESRTeam::Player; }
}

// ------------------------------------------------------------------ attacks

void FSRAttack::Prune()
{
	Units.RemoveAll([](const TWeakObjectPtr<ASRUnit>& U) { return !U.IsValid() || !U->IsAlive(); });
}

void FSRAttack::Gather(TArray<ASRUnit*>& Out, FVector2D& Centre) const
{
	Centre = FVector2D::ZeroVector;
	for (const TWeakObjectPtr<ASRUnit>& U : Units) { if (U.IsValid() && U->IsAlive()) { Out.Add(U.Get()); Centre += U->GetPos2D(); } }
	if (Out.Num() > 0) { Centre /= Out.Num(); }
}

// ------------------------------------------------------------------ setup

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

FSRAIProfile USRAISubsystem::Profile()
{
	// The timing / odds settings are the Normal values; Easy and Hard scale them. See Docs/GAMEPLAY.md.
	const USRFeelSettings& F = USRFeelSettings::Get();
	FSRAIProfile P;
	P.FirstAttack = F.AIFirstWaveTime;
	P.Advantage = F.AIAttackAdvantage;
	P.Regroup = F.AIWaveInterval;
	P.RaidInterval = F.AIRaidInterval;
	P.FirstRaid = F.AIFirstWaveTime * 1.5f;
	if (F.AIDifficulty <= 0)
	{
		P.FirstAttack *= 1.75f;  P.Advantage *= 1.35f;  P.Regroup *= 1.7f;
		P.AttackCap = 5;  P.AttackCapGrowth = 2;  P.AttackCapMax = 14;
		P.bRaids = false;
		P.AdaptWeight = 0.f;  P.IncomeScale = 0.6f;  P.BuildCadence = 8.f;
		P.MaxTowers = 2;  P.MaxFarms = 6;  P.RecruitQueue = 1;  P.Think = 1.5f;
		P.Garrison = 0.35f;  P.RetreatHold = 0.9f;  P.bReinforce = false;  P.bImpatient = false;
		P.Builders = 1;
	}
	else if (F.AIDifficulty >= 2)
	{
		P.FirstAttack *= 0.6f;  P.Advantage *= 0.77f;  P.Regroup *= 0.45f;
		P.AttackCap = 10;  P.AttackCapGrowth = 4;  P.AttackCapMax = F.AIWaveSizeMax;
		P.FirstRaid = P.FirstAttack;  P.RaidInterval *= 0.5f;
		P.AdaptWeight = 1.f;  P.IncomeScale = 1.f;  P.BuildCadence = 2.f;
		P.MaxTowers = 7;  P.MaxFarms = 14;  P.RecruitQueue = 2;  P.Think = 0.6f;
		P.Garrison = 0.2f;  P.RetreatHold = 0.55f;
	}
	return P;
}

float USRAISubsystem::IncomeScale(ESRTeam Team) const
{
	const FSRCommander& C = Commanders[Team == ESRTeam::Player ? 0 : 1];
	return C.bActive ? Profile().IncomeScale : 1.f;
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
		const FSRAIProfile P = Profile();
		C.ThinkClock = FMath::FRandRange(0.f, P.Think);
		C.NextWaveTime = P.FirstAttack;
		C.NextRaidTime = P.bRaids ? P.FirstRaid : 1e9f;
		C.NextBuildTry = 2.f;
		C.ShieldRatio = F.AIShieldRatio;
		// It knows the foe starts as it does.
		const int32 Shields = t == 1 ? F.PlayerShieldbearers : F.EnemyShieldbearers;
		const int32 Bows = t == 1 ? F.PlayerArchers : F.EnemyArchers;
		C.FoeArmyEstimate = Shields * UnitPower(ESRUnitType::Shieldbearer) + Bows * UnitPower(ESRUnitType::Archer);
	}
	UE_LOG(LogSovereign, Log, TEXT("AI reset: enemy commander on (difficulty %d), player commander %s, first attack from %.0fs"),
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
		C.ThinkClock = Profile().Think;
		Think(C);
	}
}

// ------------------------------------------------------------------ strength

float USRAISubsystem::UnitPower(ESRUnitType Type, float HealthFrac)
{
	// sqrt(health x damage per second), Shieldbearer = 1. Archers' reach (they shoot first and from behind the
	// line) is worth half as much again.
	const USRFeelSettings& F = USRFeelSettings::Get();
	auto Raw = [](const FSRUnitStats& S) { return FMath::Sqrt(S.MaxHealth * S.Damage / FMath::Max(S.AttackInterval, 0.1f)) * (S.bRanged ? 1.5f : 1.f); };
	const float Base = FMath::Max(Raw(F.Shieldbearer), 1.f);
	return Raw(F.StatsFor(Type)) / Base * FMath::Clamp(0.35f + 0.65f * HealthFrac, 0.f, 1.f);
}

float USRAISubsystem::UnitPower(const ASRUnit* Unit)
{
	return Unit ? UnitPower(Unit->GetUnitType(), Unit->GetHealthFrac()) : 0.f;
}

float USRAISubsystem::BuildingPower(const ASRBuilding* Building)
{
	if (!Building || !Building->IsFinished()) { return 0.f; }
	if (Building->GetAttackRange() <= 0.f || Building->GetAttackDamage() <= 0.f) { return 0.f; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& Ref = F.Shieldbearer;
	const float RefRaw = FMath::Sqrt(Ref.MaxHealth * Ref.Damage / FMath::Max(Ref.AttackInterval, 0.1f));
	// A building cannot be ignored and does not die quickly, but it never advances: count its health at a third.
	const float Raw = FMath::Sqrt(Building->GetMaxHealth() * 0.33f * Building->GetAttackDamage() / FMath::Max(Building->GetAttackInterval(), 0.1f));
	return Raw / FMath::Max(RefRaw, 1.f) * (0.5f + 0.5f * Building->GetHealthFrac());
}

float USRAISubsystem::SumPower(const TArray<ASRUnit*>& Units)
{
	float P = 0.f;
	for (const ASRUnit* U : Units) { P += UnitPower(U); }
	return P;
}

float USRAISubsystem::LocalFoePower(const FSRCommander& C, const FVector2D& At, float Radius) const
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	float P = 0.f;
	if (Battle)
	{
		TArray<ASRUnit*> Near;
		Battle->QueryUnits(At, Radius, Near);
		for (const ASRUnit* U : Near) { if (U && U->IsActive() && U->GetTeam() != C.Team) { P += UnitPower(U); } }
	}
	if (Eco)
	{
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (B && B->Team != C.Team && B->IsFinished() && B->GetAttackRange() > 0.f
				&& FVector2D::Distance(B->GetFootprintCentre(), At) < B->GetAttackRange() + 300.f)
			{
				P += BuildingPower(B);
			}
		}
	}
	return P;
}

float USRAISubsystem::ExpectedDefence(const FSRCommander& C, const FVector2D& At, bool bSeenOnly) const
{
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	float D = 0.f, SeenTotal = 0.f;
	for (const FSRSighting& S : C.Seen)
	{
		const float P = UnitPower(S.Type, S.HealthFrac);
		SeenTotal += P;
		// Troops near the target fight there; troops far off may come back in time, less likely the further.
		const float Dist = FVector2D::Distance(S.Pos, At);
		D += P * (bSeenOnly ? (Dist < 3000.f ? 1.f : 0.f) : FMath::GetMappedRangeValueClamped(FVector2f(2500.f, 9000.f), FVector2f(1.f, 0.15f), Dist));
	}
	// What it has not seen recently is presumably at home: it counts near the foe's castle.
	if (const ASRBuilding* FoeCastle = (Eco && !bSeenOnly) ? Eco->GetCastle(Foe(C.Team)) : nullptr)
	{
		const float Unseen = FMath::Max(0.f, C.FoeArmyEstimate - SeenTotal);
		const float Near = FMath::GetMappedRangeValueClamped(FVector2f(2000.f, 9000.f), FVector2f(0.9f, 0.25f), FVector2D::Distance(FoeCastle->GetFootprintCentre(), At));
		D += Unseen * Near;
	}
	if (Eco)
	{
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (B && B->Team != C.Team && B->IsFinished() && B->GetAttackRange() > 0.f
				&& FVector2D::Distance(B->GetFootprintCentre(), At) < B->GetAttackRange() + 400.f)
			{
				D += BuildingPower(B);
			}
		}
	}
	return D;
}

// ------------------------------------------------------------------ geometry

FVector2D USRAISubsystem::TowardFoe(const FSRCommander& C) const
{
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	const ASRBuilding* Mine = Eco ? Eco->GetCastle(C.Team) : nullptr;
	const ASRBuilding* FoeCastle = Eco ? Eco->GetCastle(Foe(C.Team)) : nullptr;
	if (Mine && FoeCastle) { return (FoeCastle->GetFootprintCentre() - Mine->GetFootprintCentre()).GetSafeNormal(); }
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

ASRBuilding* USRAISubsystem::PickTarget(const FSRCommander& C, const FVector2D& From, float Power, bool bRaid, float* OutDefence) const
{
	// Worth over resistance over distance. Economy hurts most; the castle is worth it once the defence there is beatable.
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Eco) { return nullptr; }
	const int32 FoeMines = Eco->CountBuildings(ESRBuildingType::Mine, Foe(C.Team));
	const int32 OurMines = Eco->CountBuildings(ESRBuildingType::Mine, C.Team);
	ASRBuilding* Best = nullptr;
	float BestScore = -1.f, BestD = 0.f;
	for (ASRBuilding* B : Eco->GetBuildings())
	{
		if (!B || !B->IsAlive() || B->Team == C.Team) { continue; }
		float Value = 1.f;
		switch (B->BuildingType)
		{
		case ESRBuildingType::Mine: Value = FoeMines > OurMines ? 3.6f : 3.f; break;
		case ESRBuildingType::Farm: Value = 2.4f; break;
		case ESRBuildingType::Barracks:
		case ESRBuildingType::Range:
		case ESRBuildingType::Stable:
		case ESRBuildingType::Workshop: Value = 2.6f; break;
		case ESRBuildingType::Tower: Value = 1.f; break;
		case ESRBuildingType::Castle: Value = 4.f; break;
		default: break;
		}
		if (B->IsUnderConstruction()) { Value *= 1.3f; } // half-built: cheap to knock over
		Value *= 1.6f - 0.6f * B->GetHealthFrac();       // already damaged: finish it
		const FVector2D At = B->GetFootprintCentre();
		// A raid goes by what it has seen near the target (and the towers): a gamble on an outlying farm or mine.
		float D = ExpectedDefence(C, At, bRaid);
		if (bRaid)
		{
			if (B->BuildingType != ESRBuildingType::Farm && B->BuildingType != ESRBuildingType::Mine) { continue; }
			if (D > Power * 0.6f) { continue; }
			// and never into the foe's home: the castle's own archers and the army
			if (const ASRBuilding* FoeCastle = Eco->GetCastle(B->Team); FoeCastle && FVector2D::Distance(FoeCastle->GetFootprintCentre(), At) < 3500.f) { continue; }
		}
		else if (B->IsCastle() && D > Power * 0.8f && Eco->GetBuildings().Num() > 0)
		{
			// the castle is the last resort while it is too strong
			bool bOthers = false;
			for (const ASRBuilding* O : Eco->GetBuildings()) { if (O && O != B && O->IsAlive() && O->Team == B->Team) { bOthers = true; break; } }
			if (bOthers) { Value *= 0.3f; }
		}
		const float Dist = FVector2D::Distance(At, From);
		const float Score = Value / (1.f + D) / (1.f + Dist / 9000.f);
		if (Score > BestScore) { BestScore = Score; Best = B; BestD = D; }
	}
	if (OutDefence) { *OutDefence = BestD; }
	return Best;
}

// ------------------------------------------------------------------ the loop

void USRAISubsystem::Think(FSRCommander& C)
{
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Battle || !Eco || !Eco->GetCastle(C.Team)) { return; }

	// An attack whose last troop fell this think has ended too (otherwise it would never launch another).
	const bool bMainWas = C.Main.IsActive(), bRaidWas = C.Raid.IsActive();
	C.Main.Prune();
	C.Raid.Prune();
	if (bMainWas && !C.Main.IsActive()) { EndAttack(C, C.Main, TEXT("wiped out")); }
	if (bRaidWas && !C.Raid.IsActive()) { EndAttack(C, C.Raid, TEXT("wiped out")); }
	TArray<ASRUnit*> Mine, Home;
	for (ASRUnit* U : Battle->GetUnits())
	{
		if (!U || !U->IsActive() || U->GetTeam() != C.Team) { continue; }
		Mine.Add(U);
		// builders are not soldiers: they never join the defence or an attack (they find their own work)
		if (!U->IsBuilder() && !C.Main.Units.Contains(U) && !C.Raid.Units.Contains(U)) { Home.Add(U); }
	}

	Observe(C);
	Adapt(C);
	ManageEconomy(C, Mine);
	ManageDefence(C, Home);
	if (!C.bDefending)
	{
		ManageRaid(C, Home);
		ManageAttack(C, Home);
	}
	if (C.Main.IsActive()) { StepAttack(C, C.Main); }
	if (C.Raid.IsActive()) { StepAttack(C, C.Raid); }
}

void USRAISubsystem::Observe(FSRCommander& C)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);

	// Eyes: our troops and our buildings.
	TArray<FVector2D> Eyes;
	for (const ASRUnit* U : Battle->GetUnits()) { if (U && U->IsActive() && U->GetTeam() == C.Team) { Eyes.Add(U->GetPos2D()); } }
	for (const ASRBuilding* B : Eco->GetBuildings()) { if (B && B->IsAlive() && B->Team == C.Team) { Eyes.Add(B->GetFootprintCentre()); } }
	const float R2 = FMath::Square(F.AISightRadius);

	float SeenNow = 0.f;
	int32 Archers = 0, Total = 0;
	for (ASRUnit* U : Battle->GetUnits())
	{
		if (!U || !U->IsActive() || U->GetTeam() == C.Team) { continue; }
		bool bVisible = false;
		for (const FVector2D& E : Eyes) { if (FVector2D::DistSquared(E, U->GetPos2D()) < R2) { bVisible = true; break; } }
		if (!bVisible) { continue; }
		FSRSighting* S = C.Seen.FindByPredicate([U](const FSRSighting& X) { return X.Unit.Get() == U; });
		if (!S) { S = &C.Seen.AddDefaulted_GetRef(); S->Unit = U; }
		S->Pos = U->GetPos2D();
		S->Type = U->GetUnitType();
		S->HealthFrac = U->GetHealthFrac();
		S->Time = Clock;
	}
	// Forget the dead and the long unseen.
	C.Seen.RemoveAll([this, &F](const FSRSighting& S) { return !S.Unit.IsValid() || !S.Unit->IsAlive() || Clock - S.Time > F.AIMemoryTime; });
	for (const FSRSighting& S : C.Seen)
	{
		SeenNow += UnitPower(S.Type, S.HealthFrac);
		Archers += S.Type == ESRUnitType::Archer ? 1 : 0;
		++Total;
	}
	if (Total >= 3) { C.FoeArcherShare = FMath::Lerp(C.FoeArcherShare, float(Archers) / Total, 0.25f); }
	// The foe's army as last seen at its largest, slowly forgotten (it may have lost troops we did not see die).
	// Unseen, it assumes the foe has kept up with it at least by half.
	float OurPower = 0.f;
	for (const ASRUnit* U : Battle->GetUnits()) { if (U && U->IsActive() && U->GetTeam() == C.Team) { OurPower += UnitPower(U); } }
	C.FoeArmyEstimate = FMath::Max3(SeenNow, C.FoeArmyEstimate * FMath::Pow(0.5f, Profile().Think / 240.f), OurPower * 0.5f);

	// Is the foe at our door?
	bool bAtHome = false;
	for (const FSRSighting& S : C.Seen)
	{
		if (Clock - S.Time > 1.5f) { continue; }
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (B && B->IsAlive() && B->Team == C.Team && FVector2D::DistSquared(B->GetFootprintCentre(), S.Pos) < FMath::Square(F.AIDefendRadius)) { bAtHome = true; break; }
		}
		if (bAtHome) { break; }
	}
	if (bAtHome && !C.bFoeAtHome && Clock - C.LastFoeAttack > 30.f) { ++C.FoeAttacks; }
	if (bAtHome) { C.LastFoeAttack = Clock; }
	C.bFoeAtHome = bAtHome;
}

void USRAISubsystem::Adapt(FSRCommander& C)
{
	// Answer what the foe fields. Shieldbearers close on archers and knock down buildings; archers shred a slow wall
	// of shields from behind their own.
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	const float Weight = Profile().AdaptWeight;   // how fully it adapts
	float Want = F.AIShieldRatio;
	if (C.FoeArcherShare > 0.55f) { Want += (C.FoeArcherShare - 0.55f) * 1.2f; }
	if (C.FoeArcherShare < 0.3f) { Want -= (0.3f - C.FoeArcherShare) * 1.1f; }
	const int32 FoeTowers = Eco ? Eco->CountBuildings(ESRBuildingType::Tower, Foe(C.Team)) : 0;
	Want += FMath::Min(FoeTowers, 4) * 0.03f;                 // towers: bring wall-breakers
	Want = FMath::Lerp(F.AIShieldRatio, FMath::Clamp(Want, 0.3f, 0.8f), Weight);
	C.ShieldRatio = FMath::FInterpTo(C.ShieldRatio, Want, Profile().Think, 0.5f);
}

// ------------------------------------------------------------------ economy

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
	case ESRBuildingType::Barracks:
	case ESRBuildingType::Range:
	case ESRBuildingType::Stable:
	case ESRBuildingType::Workshop: Near = Base + Fwd * 300.f + Side * (FMath::RandBool() ? 1.f : -1.f) * FMath::FRandRange(1300.f, 1900.f); Radius = 2400.f; break;
	case ESRBuildingType::Mine: Near = Base; Radius = 16000.f; break; // the nearest free vein, wherever it is
	default: break;
	}
	FSRPlacement P;
	if (Type == ESRBuildingType::Tower)
	{
		// Spread the towers: covering the economy where the foe has hit before, else toward the front.
		bool bFound = false;
		for (int32 Try = 0; Try < 8 && !bFound; ++Try)
		{
			FVector2D Cand = Base + Fwd * FMath::FRandRange(1400.f, 3000.f) + Side * FMath::FRandRange(-2400.f, 2400.f);
			if (Try % 2 == 1 && C.FoeAttacks > 0)
			{
				// guard an outlying mine or farm
				TArray<const ASRBuilding*> Eco2;
				for (const ASRBuilding* B : Eco->GetBuildings())
				{
					if (B && B->Team == C.Team && B->IsAlive() && (B->BuildingType == ESRBuildingType::Mine || B->BuildingType == ESRBuildingType::Farm)) { Eco2.Add(B); }
				}
				if (Eco2.Num() > 0) { Cand = Eco2[FMath::RandRange(0, Eco2.Num() - 1)]->GetFootprintCentre() + Fwd * 700.f; }
			}
			if (!Grid->FindPlacementNear(Type, C.Team, Cand, 800.f, P)) { continue; }
			bFound = true;
			for (const ASRBuilding* B : Eco->GetBuildings())
			{
				if (B && B->Team == C.Team && B->BuildingType == ESRBuildingType::Tower && FVector2D::Distance(B->GetFootprintCentre(), FVector2D(P.Location)) < 1100.f)
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

	if (Clock >= C.NextBuildTry)
	{
		const int32 Barracks = Eco->CountBuildings(ESRBuildingType::Barracks, C.Team);
		const int32 Ranges = Eco->CountBuildings(ESRBuildingType::Range, C.Team);
		const int32 Pop = Eco->GetPopulation(C.Team) + Eco->GetQueuedPopulation(C.Team);
		const int32 Cap = Eco->GetPopulationCap(C.Team);
		const int32 Mines = Eco->CountBuildings(ESRBuildingType::Mine, C.Team);
		const int32 Farms = Eco->CountBuildings(ESRBuildingType::Farm, C.Team);
		const int32 Towers = Eco->CountBuildings(ESRBuildingType::Tower, C.Team);
		const bool bPastOrder = !F.AIBuildOrder.IsValidIndex(C.BuildStep);
		const FSRAIProfile Prof = Profile();

		// Candidates in priority order; the first that can be placed is built. One that finds no room cools down.
		TArray<TPair<ESRBuildingType, bool>, TInlineAllocator<8>> Wants;   // type, from the build order
		auto Want = [&](ESRBuildingType T, bool bOrder = false)
		{
			const float* Until = C.BuildBlockedUntil.Find(T);
			if (!Until || *Until <= Clock) { Wants.Add({ T, bOrder }); }
		};
		const float Food = Eco->GetResource(C.Team, ESRResource::Food);
		const float Gold = Eco->GetResource(C.Team, ESRResource::Gold);
		// No way to train troops comes before anything (a lost barracks or range is rebuilt).
		if (Barracks == 0 && (bPastOrder || C.BuildStep > 0)) { Want(ESRBuildingType::Barracks); }
		if (Ranges == 0 && bPastOrder) { Want(ESRBuildingType::Range); }
		// Attacked early and often: a tower before the rest of the plan.
		if (C.FoeAttacks >= 2 && Towers == 0 && Clock - C.LastFoeAttack < 120.f) { Want(ESRBuildingType::Tower); }
		if (!bPastOrder) { Want(F.AIBuildOrder[C.BuildStep], true); }
		else
		{
			if (Cap < Eco->GetPopulationCeiling(C.Team) && Pop >= Cap - 2 && Farms < Prof.MaxFarms) { Want(ESRBuildingType::Farm); }
			if (Food < 200.f && Gold > 300.f && Farms < Prof.MaxFarms) { Want(ESRBuildingType::Farm); }   // food is what troops cost
			if (Farms > Mines * 2 + 1 || Gold < 150.f) { Want(ESRBuildingType::Mine); }
			if (Towers < FMath::Min(1 + Mines / 2 + FMath::Min(C.FoeAttacks, 2), Prof.MaxTowers)) { Want(ESRBuildingType::Tower); }
			if (Food > 450 && Barracks < 2) { Want(ESRBuildingType::Barracks); }  // food piling up: train faster
			if (Food > 450 && Ranges < 2) { Want(ESRBuildingType::Range); }
			if (Prof.AdaptWeight > 0.f && Eco->CountBuildings(ESRBuildingType::Stable, C.Team) == 0 && Farms >= 3) { Want(ESRBuildingType::Stable); }
			if (Prof.AdaptWeight > 0.f && Eco->CountBuildings(ESRBuildingType::Workshop, C.Team) == 0
				&& (Eco->CountBuildings(ESRBuildingType::Tower, Foe(C.Team)) >= 2 || C.WavesSent >= 2)) { Want(ESRBuildingType::Workshop); }
			if (Farms < FMath::Min(8, Prof.MaxFarms)) { Want(ESRBuildingType::Farm); }
			if (Gold > 600.f) { Want(ESRBuildingType::Mine); if (Towers < Prof.MaxTowers) { Want(ESRBuildingType::Tower); } }  // gold to spare
		}
		for (const TPair<ESRBuildingType, bool>& W : Wants)
		{
			const FSRCost& Cost = F.BuildingStatsFor(W.Key).Cost;
			if (!Eco->CanAfford(C.Team, Cost)) { break; }   // save up for the most wanted, do not spend it on the next
			if (TryBuild(C, W.Key))
			{
				if (W.Value) { ++C.BuildStep; }
				C.NextBuildTry = Clock + Prof.BuildCadence;
				break;
			}
			// no room (or no free vein): skip it in the build order, and do not try it again for a while
			if (W.Value) { ++C.BuildStep; }
			C.BuildBlockedUntil.Add(W.Key, Clock + 25.f);
			UE_LOG(LogSovereign, Verbose, TEXT("AI %s: no room for a %s"), Side(C), *F.BuildingStatsFor(W.Key).DisplayName);
		}
		C.NextBuildTry = FMath::Max(C.NextBuildTry, Clock + 1.f);
	}

	// housing short (or stores filling) and the price to hand: raise the castle a level
	if (ASRBuilding* Castle = Eco->GetCastle(C.Team); Castle && Castle->CanUpgrade())
	{
		const int32 Pop = Eco->GetPopulation(C.Team) + Eco->GetQueuedPopulation(C.Team);
		const FSRCost Cost = Castle->GetUpgradeCost();
		const bool bCrowded = Pop + 3 >= Eco->GetPopulationCap(C.Team);
		const bool bStoresFull = Eco->GetResource(C.Team, ESRResource::Gold) >= Eco->GetStorage(C.Team, ESRResource::Gold) * 0.85f;
		if ((bCrowded || bStoresFull) && Eco->GetResource(C.Team, ESRResource::Gold) >= Cost.Gold + 60 && Eco->GetResource(C.Team, ESRResource::Food) >= Cost.Food) { Castle->StartUpgrade(); }
	}
	// gold piling up (Normal and Hard): a mine first (more gold), then a tower (where the foe has struck before)
	if (Profile().AdaptWeight > 0.f && Eco->GetResource(C.Team, ESRResource::Gold) >= Eco->GetStorage(C.Team, ESRResource::Gold) * 0.7f)
	{
		ASRBuilding* Best = nullptr;
		for (ASRBuilding* B : Eco->GetBuildings())
		{
			if (!B || B->Team != C.Team || !B->CanUpgrade() || B->IsCastle() || !Eco->CanAfford(C.Team, B->GetUpgradeCost())) { continue; }
			if (!Best || (B->BuildingType == ESRBuildingType::Mine && Best->BuildingType != ESRBuildingType::Mine) || (B->BuildingType == Best->BuildingType && B->GetLevel() < Best->GetLevel())) { Best = B; }
		}
		if (Best) { Best->StartUpgrade(); }
	}

	Recruit(C, Mine);
}

void USRAISubsystem::Recruit(FSRCommander& C, const TArray<ASRUnit*>& Mine)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	int32 Count[4] = { 0, 0, 0, 0 }, Total = 0, Builders = 0;
	for (const ASRUnit* U : Mine)
	{
		if (U->IsBuilder()) { ++Builders; continue; }
		++Count[FMath::Clamp(int32(U->GetUnitType()), 0, 3)]; ++Total;
	}
	TArray<ASRBuilding*> Trainers;
	for (ASRBuilding* B : Eco->GetBuildings())
	{
		if (!B || B->Team != C.Team || !B->IsAlive() || !B->IsRecruiter()) { continue; }
		for (ESRUnitType T : B->GetQueue())
		{
			if (T == ESRUnitType::Builder) { ++Builders; continue; }
			++Count[FMath::Clamp(int32(T), 0, 3)]; ++Total;
		}
		if (B->CanRecruit()) { Trainers.Add(B); }
		const FVector2D Muster = MusterPoint(C);
		if (FVector2D::Distance(B->GetRallyPoint(), Muster) > 150.f) { B->SetRallyPoint(Muster); }
	}
	if (Trainers.Num() == 0) { return; }

	// What the army wants next: a catapult or two against towers (and for the castle), a few riders (more against
	// archers), then the shield / archer mix.
	const FSRAIProfile Prof = Profile();
	const int32 FoeTowers = Eco->CountBuildings(ESRBuildingType::Tower, Foe(C.Team));
	const int32 WantCatapults = Prof.AdaptWeight <= 0.f ? 0 : FMath::Min(3, FoeTowers / 2 + (C.WavesSent >= 2 ? 1 : 0));
	const int32 WantRiders = Prof.AdaptWeight <= 0.f ? 0 : FMath::RoundToInt(Total * (0.12f + (C.FoeArcherShare > 0.5f ? 0.12f : 0.f)));
	TArray<ESRUnitType, TInlineAllocator<6>> Order;
	// a builder first if it is short of them (the first one once it has a barracks going, so troops come first)
	if (Builders < FMath::Min(Prof.Builders, Eco->GetMaxBuilders(C.Team)) && (Builders > 0 || Total >= 4 || Eco->CountBuildings(ESRBuildingType::Barracks, C.Team) > 0)) { Order.Add(ESRUnitType::Builder); }
	if (Count[3] < WantCatapults) { Order.Add(ESRUnitType::Catapult); }
	if (Count[2] < WantRiders) { Order.Add(ESRUnitType::Horseman); }
	const int32 Core = Count[0] + Count[1];
	const bool bNeedShields = Core == 0 || float(Count[0]) / Core < C.ShieldRatio;
	Order.Add(bNeedShields ? ESRUnitType::Shieldbearer : ESRUnitType::Archer);
	Order.Add(bNeedShields ? ESRUnitType::Archer : ESRUnitType::Shieldbearer);
	for (ESRUnitType Type : Order)
	{
		ASRBuilding* Best = nullptr;
		for (ASRBuilding* B : Trainers) { if (B->Trains(Type) && B->GetQueue().Num() < Prof.RecruitQueue && (!Best || B->GetQueue().Num() < Best->GetQueue().Num())) { Best = B; } }
		if (!Best) { continue; }   // no trainer for it (yet): the next want
		const bool bRoom = Eco->GetPopulation(C.Team) + Eco->GetQueuedPopulation(C.Team) + F.StatsFor(Type).PopCost <= Eco->GetPopulationCap(C.Team);
		if (bRoom && Eco->CanAfford(C.Team, F.CostFor(Type))) { Best->QueueRecruit(Type); }
		break; // one decision per think: the wanted type waits for its cost rather than another draining it
	}
}

// ------------------------------------------------------------------ defence

void USRAISubsystem::ManageDefence(FSRCommander& C, TArray<ASRUnit*>& Home)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);

	// Foes near our buildings, right now.
	FVector2D ThreatSum = FVector2D::ZeroVector;
	float ThreatPower = 0.f;
	int32 Threats = 0;
	for (ASRUnit* U : Battle->GetUnits())
	{
		if (!U || !U->IsActive() || U->GetTeam() == C.Team) { continue; }
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (B && B->Team == C.Team && B->IsAlive() && FVector2D::DistSquared(B->GetFootprintCentre(), U->GetPos2D()) < FMath::Square(F.AIDefendRadius))
			{
				ThreatSum += U->GetPos2D();
				ThreatPower += UnitPower(U);
				++Threats;
				break;
			}
		}
	}

	if (Threats == 0)
	{
		// Quiet: gather idle troops at the muster point.
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
		return;
	}

	C.bDefending = true;
	const FVector2D ThreatAt = ThreatSum / Threats;
	// Our towers there fight too.
	float TowerHelp = 0.f;
	for (const ASRBuilding* B : Eco->GetBuildings())
	{
		if (B && B->Team == C.Team && B->GetAttackRange() > 0.f && FVector2D::Distance(B->GetFootprintCentre(), ThreatAt) < B->GetAttackRange() + 300.f) { TowerHelp += BuildingPower(B); }
	}
	// Send the nearest troops until we have clearly more than they do (everyone if that is what it takes).
	const float Need = FMath::Max(0.f, ThreatPower * 1.6f - TowerHelp);
	Home.Sort([&ThreatAt](const ASRUnit& A, const ASRUnit& B) { return FVector2D::DistSquared(A.GetPos2D(), ThreatAt) < FVector2D::DistSquared(B.GetPos2D(), ThreatAt); });
	TArray<ASRUnit*> Send;
	float Sent = 0.f;
	for (ASRUnit* U : Home)
	{
		if (Sent >= Need && Send.Num() >= 2) { break; }
		Sent += UnitPower(U);
		if (!U->IsEngaged()) { Send.Add(U); }
	}
	if (Send.Num() > 0 && Clock - C.LastHomeOrder > 2.f)
	{
		Battle->CommandMove(Send, ThreatAt, true, ESRFormationShape::Line, false);
		C.LastHomeOrder = Clock;
	}

	// Outmatched at home: call back what is out, if it can get back in time (the raid always; the main attack
	// unless it is about to win where it is). With the castle itself in danger, from anywhere: losing the castle
	// loses the war, a base race is only worth running when the foe's castle is about to fall.
	const float HomePower = SumPower(Home) + TowerHelp;
	if (ThreatPower > HomePower * 1.1f)
	{
		const ASRBuilding* Castle = Eco->GetCastle(C.Team);
		const bool bCastleThreat = Castle && FVector2D::Distance(ThreatAt, Castle->GetFootprintCentre()) < 3200.f;
		for (FSRAttack* A : { &C.Raid, &C.Main })
		{
			if (!A->IsActive()) { continue; }
			TArray<ASRUnit*> W;
			FVector2D Centre;
			A->Gather(W, Centre);
			const bool bClose = Castle && FVector2D::Distance(Centre, Castle->GetFootprintCentre()) < 7000.f;
			const bool bWinning = A->Target.IsValid() && A->Target->GetHealthFrac() < (A->Target->IsCastle() ? 0.45f : 0.3f)
				&& LocalFoePower(C, Centre, 2000.f) < SumPower(W) * 0.5f;
			if (A->bRaid || ((bClose || bCastleThreat) && !bWinning))
			{
				Battle->CommandMove(W, ThreatAt, true, ESRFormationShape::Line, false);
				UE_LOG(LogSovereign, Log, TEXT("AI %s recalls its %s to defend (threat %.1f vs home %.1f)"), Side(C), A->bRaid ? TEXT("raid") : TEXT("attack"), ThreatPower, HomePower);
				A->Units.Reset();
				if (A->bRaid) { C.NextRaidTime = Profile().bRaids ? Clock + Profile().RaidInterval * 0.5f : 1e9f; }
				else { C.NextWaveTime = Clock + Profile().Regroup * 0.5f; }
			}
		}
	}
}

// ------------------------------------------------------------------ attacks

void USRAISubsystem::ManageAttack(FSRCommander& C, TArray<ASRUnit*>& Home)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);

	// Keep a garrison: more against a foe that has come at us lately.
	const FSRAIProfile Prof = Profile();
	const float GarrisonFrac = Prof.Garrison + (Clock - C.LastFoeAttack < 180.f ? 0.15f : 0.f);
	const int32 Keep = FMath::FloorToInt(Home.Num() * GarrisonFrac);
	TArray<ASRUnit*> Free;
	{
		// Shieldbearers lead; the garrison keeps both types.
		TArray<ASRUnit*> Sorted = Home;
		Sorted.Sort([](const ASRUnit& A, const ASRUnit& B) { return A.GetUnitType() < B.GetUnitType(); });
		TSet<int32> Stay;
		for (int32 k = 0; k < Keep; ++k) { Stay.Add((k * Sorted.Num()) / FMath::Max(Keep, 1) + Sorted.Num() / FMath::Max(2 * Keep, 1)); }
		for (int32 i = 0; i < Sorted.Num(); ++i) { if (!Stay.Contains(i) && !Sorted[i]->IsEngaged()) { Free.Add(Sorted[i]); } }
	}
	// How many it will commit grows with each attack it has made (a gentle opponent starts small).
	const int32 Cap = FMath::Min3(Prof.AttackCap + Prof.AttackCapGrowth * C.WavesSent, Prof.AttackCapMax, F.AIWaveSizeMax);
	while (Free.Num() > Cap) { Free.Pop(); }
	const float FreePower = SumPower(Free);

	// Reinforce an attack that is going well.
	if (C.Main.IsActive())
	{
		TArray<ASRUnit*> W;
		FVector2D Centre;
		C.Main.Gather(W, Centre);
		const float Ours = SumPower(W), Theirs = LocalFoePower(C, Centre, 2200.f);
		// Reinforcements go as a body: they gather at the muster point until there are enough to cross the map
		// together (a trickle of three dies to the first tower on the way).
		TArray<ASRUnit*> Mustered;
		const FVector2D Muster = MusterPoint(C);
		for (ASRUnit* U : Free) { if (FVector2D::Distance(U->GetPos2D(), Muster) < 1400.f) { Mustered.Add(U); } }
		Free = Mustered;
		if (Prof.bReinforce && Free.Num() >= 6 && Ours > Theirs * 0.9f && Clock - C.LastReinforce > 20.f)
		{
			C.LastReinforce = Clock;
			Battle->CommandMove(Free, Centre, true, ESRFormationShape::Column, false);
			for (ASRUnit* U : Free) { C.Main.Units.Add(U); U->SetStance(ESRStance::Aggressive); }
			C.Main.StartSize += Free.Num();
			UE_LOG(LogSovereign, Log, TEXT("AI %s reinforces its attack with %d"), Side(C), Free.Num());
		}
		return;
	}

	if (Clock < C.NextWaveTime || Free.Num() < F.AIMinAttackSize) { return; }

	float Defence = 0.f;
	const FVector2D From = MusterPoint(C);
	ASRBuilding* Target = PickTarget(C, From, FreePower, false, &Defence);
	if (!Target) { return; }

	// Go when the odds are good; sooner when the foe's army has been seen away from home; and once the army is at
	// its housing cap, there is nothing to gain by waiting.
	const float Advantage = Prof.Advantage;
	const bool bMaxed = Eco->GetPopulation(C.Team) >= Eco->GetPopulationCap(C.Team) - 1 && Eco->GetPopulationCap(C.Team) >= 20;
	const bool bGood = FreePower >= Defence * Advantage;
	const bool bWaitedLong = Prof.bImpatient && Clock > C.NextWaveTime + 150.f && FreePower >= Defence * 0.85f;
	if (!bGood && !bMaxed && !bWaitedLong) { return; }

	C.Main = FSRAttack();
	for (ASRUnit* U : Free) { C.Main.Units.Add(U); U->SetStance(ESRStance::Aggressive); }
	C.Main.StartSize = Free.Num();
	C.Main.Launched = Clock;
	C.Main.LastFight = Clock;
	C.Main.Target = Target;
	C.Main.Goal = Target->ClosestPointOnFootprint(From, 250.f);
	C.Main.Reorder = 0.f;
	++C.WavesSent;
	C.NextWaveTime = Clock + 1e6f; // set for real when this attack ends
	Battle->CommandMove(Free, C.Main.Goal, true, ESRFormationShape::Line, false);
	UE_LOG(LogSovereign, Log, TEXT("AI %s attacks (#%d): %d troops, power %.1f vs expected %.1f at %s (%.0f, %.0f)%s"), Side(C), C.WavesSent, Free.Num(),
		FreePower, Defence, *Target->GetDisplayName(), C.Main.Goal.X, C.Main.Goal.Y, bGood ? TEXT("") : (bMaxed ? TEXT(" [maxed]") : TEXT(" [impatient]")));
	// (the player is not warned when the enemy sets off: they find out when it arrives, through the under-attack alerts)
}

void USRAISubsystem::ManageRaid(FSRCommander& C, TArray<ASRUnit*>& Home)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (C.Raid.IsActive() || Clock < C.NextRaidTime) { return; }
	const int32 Size = FMath::Max(1, F.AIRaidSize + (C.RaidsSent >= 2 ? 1 : 0));
	// Only from a surplus: what the main attack does not need right now.
	TArray<ASRUnit*> Free;
	for (ASRUnit* U : Home) { if (!U->IsEngaged() && !C.Main.Units.Contains(U)) { Free.Add(U); } }
	if (Free.Num() < Size + FMath::Max(2, F.AIMinAttackSize / 2)) { return; }
	// Fast first: riders, then Shieldbearers (they hit buildings); never the slow catapults.
	Free.RemoveAll([](const ASRUnit* U) { return U->GetUnitType() == ESRUnitType::Catapult; });
	if (Free.Num() < Size) { return; }
	auto Rank = [](ESRUnitType T) { return T == ESRUnitType::Horseman ? 0 : (T == ESRUnitType::Shieldbearer ? 1 : 2); };
	Free.Sort([&Rank](const ASRUnit& A, const ASRUnit& B) { return Rank(A.GetUnitType()) < Rank(B.GetUnitType()); });
	Free.SetNum(Size);
	const float Power = SumPower(Free);
	float Defence = 0.f;
	ASRBuilding* Target = PickTarget(C, MusterPoint(C), Power, true, &Defence);
	if (!Target) { C.NextRaidTime = Clock + 15.f; return; }

	C.Raid = FSRAttack();
	C.Raid.bRaid = true;
	for (ASRUnit* U : Free) { C.Raid.Units.Add(U); U->SetStance(ESRStance::Aggressive); }
	C.Raid.StartSize = Free.Num();
	C.Raid.Launched = Clock;
	C.Raid.LastFight = Clock;
	C.Raid.Target = Target;
	C.Raid.Goal = Target->ClosestPointOnFootprint(MusterPoint(C), 200.f);
	++C.RaidsSent;
	C.NextRaidTime = Clock + 1e6f;
	Battle->CommandMove(Free, C.Raid.Goal, false, ESRFormationShape::Column, false); // slip past, fight at the target
	UE_LOG(LogSovereign, Log, TEXT("AI %s raids %s with %d (expected defence %.1f)"), Side(C), *Target->GetDisplayName(), Free.Num(), Defence);
}

void USRAISubsystem::EndAttack(FSRCommander& C, FSRAttack& A, const TCHAR* Why)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	TArray<ASRUnit*> W;
	FVector2D Centre;
	A.Gather(W, Centre);
	if (W.Num() > 0) { Battle->CommandMove(W, MusterPoint(C), false, ESRFormationShape::Column, false); }
	UE_LOG(LogSovereign, Log, TEXT("AI %s %s ends (%s): %d of %d back"), Side(C), A.bRaid ? TEXT("raid") : TEXT("attack"), Why, W.Num(), A.StartSize);
	const FSRAIProfile Prof = Profile();
	if (A.bRaid) { C.NextRaidTime = Prof.bRaids ? Clock + Prof.RaidInterval : 1e9f; }
	else { C.NextWaveTime = Clock + Prof.Regroup; }
	A.Units.Reset();
}

void USRAISubsystem::StepAttack(FSRCommander& C, FSRAttack& A)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);

	TArray<ASRUnit*> W;
	FVector2D Centre;
	A.Gather(W, Centre);
	if (W.Num() == 0)
	{
		UE_LOG(LogSovereign, Log, TEXT("AI %s %s wiped out"), Side(C), A.bRaid ? TEXT("raid") : TEXT("attack"));
		EndAttack(C, A, TEXT("wiped out"));
		return;
	}

	// How is the fight where we are going?
	const float Ours = SumPower(W);
	const float Theirs = LocalFoePower(C, Centre, 2200.f);
	bool bFighting = false;
	for (const ASRUnit* U : W) { if (U->IsEngaged()) { bFighting = true; break; } }
	if (bFighting || Theirs > 0.f) { A.LastFight = Clock; }

	// Losing: fall back and regroup rather than feed the foe one troop at a time. A raid gives up sooner.
	const float Hold = A.bRaid ? 0.9f : Profile().RetreatHold;
	if (Theirs > 0.f && Ours < Theirs * Hold && (A.bRaid || W.Num() <= FMath::CeilToInt(A.StartSize * 0.7f)))
	{
		EndAttack(C, A, *FString::Printf(TEXT("outmatched %.1f vs %.1f"), Ours, Theirs));
		return;
	}
	if (W.Num() <= FMath::CeilToInt(A.StartSize * F.AIRetreatFraction) && Theirs > Ours)
	{
		EndAttack(C, A, TEXT("too few left"));
		return;
	}
	// Lost its way, or nothing left worth hitting nearby.
	if (Clock - A.LastFight > (A.bRaid ? 90.f : 150.f))
	{
		EndAttack(C, A, TEXT("no fight"));
		return;
	}

	// Target fell (or we got there and stand idle): on to the next, chosen from here.
	A.Reorder -= Profile().Think;
	bool bIdle = true;
	for (const ASRUnit* U : W) { if (U->IsEngaged() || U->GetOrder() != ESROrder::Idle) { bIdle = false; break; } }
	if (!A.Target.IsValid() || !A.Target->IsAlive() || (bIdle && A.Reorder <= 0.f && !A.Target.IsValid()))
	{
		if (A.bRaid && A.Target.IsValid() && !A.Target->IsAlive())
		{
			// a raid hits one target and goes home with the news
			EndAttack(C, A, TEXT("target burned"));
			return;
		}
		float Defence = 0.f;
		ASRBuilding* Next = PickTarget(C, Centre, Ours, A.bRaid, &Defence);
		if (!Next) { EndAttack(C, A, TEXT("nothing left")); return; }
		// The next target is too strong for what is left: come home and come back bigger.
		if (!A.bRaid && Defence > Ours * 1.25f && !Next->IsCastle())
		{
			EndAttack(C, A, *FString::Printf(TEXT("next target too strong %.1f vs %.1f"), Defence, Ours));
			return;
		}
		A.Target = Next;
		A.Goal = Next->ClosestPointOnFootprint(Centre, 250.f);
		A.Reorder = 6.f;
		Battle->CommandMove(W, A.Goal, true, ESRFormationShape::Line, false);
		UE_LOG(LogSovereign, Log, TEXT("AI %s %s moves on to %s"), Side(C), A.bRaid ? TEXT("raid") : TEXT("attack"), *Next->GetDisplayName());
	}
	else if (bIdle && A.Reorder <= 0.f)
	{
		// at the target with nothing to fight: knock it down
		Battle->CommandAttackBuilding(W, A.Target.Get());
		A.Reorder = 6.f;
	}
}

void USRAISubsystem::LogStatus() const
{
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	for (const FSRCommander& C : Commanders)
	{
		if (!C.bActive || !Eco) { continue; }
		UE_LOG(LogSovereign, Log, TEXT("AI %s: t=%.0fs gold=%d food=%d pop=%d/%d farms=%d mines=%d towers=%d barracks=%d ranges=%d | attacks=%d (out %d) raids=%d (out %d) next attack in %.0fs | foe est %.1f, archers %.0f%%, attacks on us %d, shield ratio %.2f"),
			Side(C), Clock, Eco->GetResource(C.Team, ESRResource::Gold), Eco->GetResource(C.Team, ESRResource::Food),
			Eco->GetPopulation(C.Team), Eco->GetPopulationCap(C.Team), Eco->CountBuildings(ESRBuildingType::Farm, C.Team), Eco->CountBuildings(ESRBuildingType::Mine, C.Team),
			Eco->CountBuildings(ESRBuildingType::Tower, C.Team), Eco->CountBuildings(ESRBuildingType::Barracks, C.Team), Eco->CountBuildings(ESRBuildingType::Range, C.Team),
			C.WavesSent, C.Main.Units.Num(), C.RaidsSent, C.Raid.Units.Num(), FMath::Max(0.f, C.NextWaveTime - Clock) > 1e5f ? -1.f : C.NextWaveTime - Clock,
			C.FoeArmyEstimate, C.FoeArcherShare * 100.f, C.FoeAttacks, C.ShieldRatio);
	}
}

#undef LOCTEXT_NAMESPACE

void USRAISubsystem::SaveState(FSRSavedCommander Out[2]) const
{
	for (int32 t = 0; t < 2; ++t)
	{
		const FSRCommander& C = Commanders[t];
		Out[t].bActive = C.bActive;
		Out[t].BuildStep = C.BuildStep;
		Out[t].WavesSent = C.WavesSent;
		Out[t].RaidsSent = C.RaidsSent;
		Out[t].FoeAttacks = C.FoeAttacks;
		Out[t].ShieldRatio = C.ShieldRatio;
	}
}

void USRAISubsystem::LoadState(const FSRSavedCommander In[2], float BattleClock)
{
	const FSRAIProfile P = Profile();
	Clock = BattleClock;
	for (int32 t = 0; t < 2; ++t)
	{
		FSRCommander& C = Commanders[t];
		C.bActive = t == 1 || In[t].bActive;
		C.BuildStep = In[t].BuildStep;
		C.WavesSent = In[t].WavesSent;
		C.RaidsSent = In[t].RaidsSent;
		C.FoeAttacks = In[t].FoeAttacks;
		C.ShieldRatio = In[t].ShieldRatio;
		C.NextWaveTime = FMath::Max(P.FirstAttack, Clock + P.Regroup * 0.5f);
		C.NextRaidTime = P.bRaids ? FMath::Max(P.FirstRaid, Clock + P.RaidInterval * 0.5f) : 1e9f;
		C.NextBuildTry = Clock + 2.f;
	}
}
