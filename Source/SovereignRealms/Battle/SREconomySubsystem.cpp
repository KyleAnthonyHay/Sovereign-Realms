// Copyright Sovereign Realms.

#include "Battle/SREconomySubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Common/SRAudioSubsystem.h"
#include "Units/SRUnit.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"

USREconomySubsystem* USREconomySubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USREconomySubsystem>() : nullptr;
}

bool USREconomySubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void USREconomySubsystem::RegisterBuilding(ASRBuilding* Building)
{
	if (Building) { Buildings.AddUnique(Building); }
}

void USREconomySubsystem::UnregisterBuilding(ASRBuilding* Building)
{
	Buildings.Remove(Building);
}

ASRBuilding* USREconomySubsystem::FindBuilding(ESRBuildingType Type, ESRTeam Team) const
{
	for (ASRBuilding* Building : Buildings)
	{
		if (Building && Building->BuildingType == Type && Building->Team == Team) { return Building; }
	}
	return nullptr;
}

int32 USREconomySubsystem::CountBuildings(ESRBuildingType Type, ESRTeam Team) const
{
	int32 Count = 0;
	for (const ASRBuilding* Building : Buildings)
	{
		Count += (Building && Building->BuildingType == Type && Building->Team == Team) ? 1 : 0;
	}
	return Count;
}

void USREconomySubsystem::Reset()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	for (int32 Team = 0; Team < 2; ++Team)
	{
		Stock[Team][int32(ESRResource::Gold)] = F.StartingGold;
		Stock[Team][int32(ESRResource::Food)] = F.StartingFood;
	}
	Flash[0] = Flash[1] = Pulse[0] = Pulse[1] = 0.f;
	PopFlash = 0.f;
	Popups.Reset();
	Alerts.Reset();
	LastAttackAlert.Reset();
	LastAttackTime[0] = LastAttackTime[1] = -100.0;
	ScoutCooldownLeft[0] = ScoutCooldownLeft[1] = 0.f;
	// Buildings put up during the last match come down; the level's own stand again.
	const TArray<TObjectPtr<ASRBuilding>> Copy = Buildings;
	for (ASRBuilding* Building : Copy)
	{
		if (Building && Building->IsRuntimeBuilt()) { Building->Destroy(); }
	}
	for (ASRBuilding* Building : Buildings)
	{
		if (Building && !Building->IsRuntimeBuilt()) { Building->ResetRuntime(); }
	}
	bStarted = true;
	UE_LOG(LogSovereign, Log, TEXT("ECONOMY RESET: gold=%d food=%d, buildings=%d (player: %d castle, %d farm, %d mine)"), F.StartingGold, F.StartingFood, Buildings.Num(),
		CountBuildings(ESRBuildingType::Castle, ESRTeam::Player), CountBuildings(ESRBuildingType::Farm, ESRTeam::Player), CountBuildings(ESRBuildingType::Mine, ESRTeam::Player));
}

void USREconomySubsystem::Step(float Dt)
{
	if (!bStarted) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();

	// A building may destroy itself while stepping (rubble cleared): step a copy of the list.
	const TArray<TObjectPtr<ASRBuilding>> Copy = Buildings;
	for (ASRBuilding* Building : Copy)
	{
		if (IsValid(Building)) { Building->StepBuilding(Dt); }
	}
	PopFlash = FMath::Max(0.f, PopFlash - Dt / FMath::Max(F.InsufficientFlashTime, 0.05f));
	for (int32 i = Alerts.Num() - 1; i >= 0; --i)
	{
		Alerts[i].Age += Dt;
		if (Alerts[i].Age > 6.f) { Alerts.RemoveAt(i); }
	}

	for (int32 i = 0; i < 2; ++i)
	{
		ScoutCooldownLeft[i] = FMath::Max(0.f, ScoutCooldownLeft[i] - Dt);
		Flash[i] = FMath::Max(0.f, Flash[i] - Dt / FMath::Max(F.InsufficientFlashTime, 0.05f));
		Pulse[i] = FMath::Max(0.f, Pulse[i] - Dt / 0.45f);
	}
	for (int32 i = Popups.Num() - 1; i >= 0; --i)
	{
		Popups[i].Age += Dt;
		if (Popups[i].Age >= F.PayoutPopupTime) { Popups.RemoveAt(i); }
	}
}

// ------------------------------------------------------------------ resources

void USREconomySubsystem::AddResource(ESRTeam Team, ESRResource Resource, int32 Amount, bool bIgnoreStorage)
{
	int32& Value = Stock[int32(Team)][int32(Resource)];
	// the stores hold only so much (the castle's level, plus granaries / treasuries); what does not fit is lost
	const int32 Cap = bIgnoreStorage ? 999999 : FMath::Max(GetStorage(Team, Resource), Value);
	Value = FMath::Clamp(Value + Amount, 0, Cap);
	if (Team == ESRTeam::Player && Amount > 0) { Pulse[int32(Resource)] = 1.f; }
}

bool USREconomySubsystem::CanAfford(ESRTeam Team, const FSRCost& Cost) const
{
	return GetResource(Team, ESRResource::Gold) >= Cost.Gold && GetResource(Team, ESRResource::Food) >= Cost.Food;
}

bool USREconomySubsystem::TrySpend(ESRTeam Team, const FSRCost& Cost)
{
	if (!CanAfford(Team, Cost))
	{
		if (Team == ESRTeam::Player)
		{
			if (GetResource(Team, ESRResource::Gold) < Cost.Gold) { Flash[int32(ESRResource::Gold)] = 1.f; }
			if (GetResource(Team, ESRResource::Food) < Cost.Food) { Flash[int32(ESRResource::Food)] = 1.f; }
		}
		return false;
	}
	Stock[int32(Team)][int32(ESRResource::Gold)] -= Cost.Gold;
	Stock[int32(Team)][int32(ESRResource::Food)] -= Cost.Food;
	return true;
}

void USREconomySubsystem::NotifyRefused()
{
	Flash[0] = FMath::Max(Flash[0], 0.6f);
	Flash[1] = FMath::Max(Flash[1], 0.6f);
}

float USREconomySubsystem::GetIncomePerMinute(ESRTeam Team, ESRResource Resource) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (Resource == ESRResource::Food)
	{
		return CountFinished(ESRBuildingType::Farm, Team) * F.FarmFoodPerPayout * 60.f / FMath::Max(F.FarmPayoutInterval, 0.2f);
	}
	int32 PerRound = 0;   // each mine at its level
	for (const ASRBuilding* B : Buildings) { if (B && B->Team == Team && B->BuildingType == ESRBuildingType::Mine && B->IsFinished()) { PerRound += B->GetPayoutAmount(); } }
	return PerRound * 60.f / FMath::Max(F.MinePayoutInterval, 0.2f);
}

void USREconomySubsystem::AddPopup(const FVector& Origin, int32 Amount, ESRResource Resource)
{
	FSRPayoutPopup& Popup = Popups.AddDefaulted_GetRef();
	Popup.Origin = Origin;
	Popup.Amount = Amount;
	Popup.Resource = Resource;
}

// ---------------------------------------------------------------------- space

ASRBuilding* USREconomySubsystem::PickBuilding(const FVector& RayOrigin, const FVector& RayDir) const
{
	ASRBuilding* Best = nullptr;
	float BestAlong = TNumericLimits<float>::Max();
	for (ASRBuilding* Building : Buildings)
	{
		float Along = 0.f;
		if (Building && !Building->IsHidden() && Building->RayHit(RayOrigin, RayDir, Along) && Along < BestAlong)
		{
			BestAlong = Along;
			Best = Building;
		}
	}
	return Best;
}

FVector2D USREconomySubsystem::ClearOfBuildings(const FVector2D& Point) const
{
	const float Margin = USRFeelSettings::Get().BuildingRouteMargin;
	FVector2D Out = Point;
	for (int32 Pass = 0; Pass < 2; ++Pass)
	{
		for (const ASRBuilding* Building : Buildings)
		{
			if (Building) { Out = Building->PushOutside(Out, Margin); }
		}
	}
	return Out;
}

void USREconomySubsystem::RoutePath(const FVector2D& From, const FVector2D& To, TArray<FVector2D>& OutPath) const
{
	RouteLeg(From, ClearOfBuildings(To), nullptr, 0, OutPath);
}

void USREconomySubsystem::RouteLeg(const FVector2D& From, const FVector2D& To, const ASRBuilding* Skip, int32 Depth, TArray<FVector2D>& OutPath) const
{
	const float Margin = USRFeelSettings::Get().BuildingRouteMargin;
	const float Inner = Margin - 6.f;     // what a leg may not cross
	const float Outer = Margin + 4.f;     // where the corner waypoints sit

	// The first footprint this leg runs into.
	const ASRBuilding* Block = nullptr;
	float BlockT = 2.f;
	for (const ASRBuilding* Building : Buildings)
	{
		float T = 0.f;
		if (Building && Building != Skip && Building->SegmentCrosses(From, To, Inner, T) && T < BlockT)
		{
			BlockT = T;
			Block = Building;
		}
	}
	if (!Block || Depth > 3)
	{
		OutPath.Add(To);
		return;
	}

	// Shortest way over the four corners of the grown footprint (nodes: start, corners, goal).
	FVector2D Start = From;
	if (Block->ContainsXY(Start, Inner))
	{
		// Standing against the wall: step straight out first.
		Start = Block->PushOutside(Start, Outer);
		OutPath.Add(Start);
	}
	const FVector2D Min = Block->FootprintMin - FVector2D(Outer, Outer), Max = Block->FootprintMax + FVector2D(Outer, Outer);
	FVector2D Nodes[6];
	Nodes[0] = Start;
	Nodes[1] = Block->ToWorld2D(FVector2D(Min.X, Min.Y));
	Nodes[2] = Block->ToWorld2D(FVector2D(Max.X, Min.Y));
	Nodes[3] = Block->ToWorld2D(FVector2D(Max.X, Max.Y));
	Nodes[4] = Block->ToWorld2D(FVector2D(Min.X, Max.Y));
	Nodes[5] = To;

	float Dist[6];
	int32 Prev[6];
	bool Done[6];
	for (int32 i = 0; i < 6; ++i) { Dist[i] = TNumericLimits<float>::Max(); Prev[i] = -1; Done[i] = false; }
	Dist[0] = 0.f;
	for (int32 Iter = 0; Iter < 6; ++Iter)
	{
		int32 U = -1;
		for (int32 i = 0; i < 6; ++i) { if (!Done[i] && (U < 0 || Dist[i] < Dist[U])) { U = i; } }
		if (U < 0 || Dist[U] == TNumericLimits<float>::Max()) { break; }
		Done[U] = true;
		for (int32 V = 0; V < 6; ++V)
		{
			float T = 0.f;
			if (Done[V] || Block->SegmentCrosses(Nodes[U], Nodes[V], Inner, T)) { continue; }
			const float Alt = Dist[U] + FVector2D::Distance(Nodes[U], Nodes[V]);
			if (Alt < Dist[V]) { Dist[V] = Alt; Prev[V] = U; }
		}
	}
	if (Prev[5] < 0)
	{
		OutPath.Add(To); // no way round found (goal hemmed in): let the unit's own sliding cope
		return;
	}
	TArray<int32, TInlineAllocator<6>> Chain;
	for (int32 Node = 5; Node > 0; Node = Prev[Node]) { Chain.Insert(Node, 0); }
	FVector2D Cursor = Start;
	for (int32 Node : Chain)
	{
		// Each stretch of the detour may meet another building.
		RouteLeg(Cursor, Nodes[Node], Block, Depth + 1, OutPath);
		Cursor = Nodes[Node];
	}
}

void USREconomySubsystem::LogStatus() const
{
	UE_LOG(LogSovereign, Log, TEXT("ECONOMY player gold=%d food=%d (+%.0f gold/min, +%.0f food/min)  enemy gold=%d food=%d  buildings=%d"),
		GetResource(ESRTeam::Player, ESRResource::Gold), GetResource(ESRTeam::Player, ESRResource::Food),
		GetIncomePerMinute(ESRTeam::Player, ESRResource::Gold), GetIncomePerMinute(ESRTeam::Player, ESRResource::Food),
		GetResource(ESRTeam::Enemy, ESRResource::Gold), GetResource(ESRTeam::Enemy, ESRResource::Food), Buildings.Num());
	for (const ASRBuilding* Building : Buildings)
	{
		if (!Building) { continue; }
		FString Queue;
		for (ESRUnitType Type : Building->GetQueue()) { Queue += TEXT("SAHCBO")[FMath::Clamp(int32(Type), 0, SRNumUnitTypes - 1)]; }   // (O: scOut)
		UE_LOG(LogSovereign, Log, TEXT("  %-16s %-9s team=%d pos=(%6.0f,%6.0f) payout=%.2f queue=[%s] build=%.2f rally=(%.0f,%.0f) sel=%d site=%.2f%s builders=%d hp=%.0f"),
			*Building->GetActorNameOrLabel(), *Building->GetDisplayName(), int32(Building->Team), Building->GetActorLocation().X, Building->GetActorLocation().Y,
			Building->GetPayoutFraction(), *Queue, Building->GetBuildFraction(), Building->GetRallyPoint().X, Building->GetRallyPoint().Y, Building->IsSelected() ? 1 : 0,
			Building->GetBuildProgress(), Building->IsUnderConstruction() && Building->NeedsBuilder() ? TEXT(" (needs builder)") : TEXT(""), Building->GetBuildersWorking(), Building->GetHealth());
	}
}


// ------------------------------------------------------------------ population

int32 USREconomySubsystem::GetPopulation(ESRTeam Team) const
{
	int32 Pop = 0;
	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		for (const ASRUnit* U : Battle->GetUnits())
		{
			if (U && U->IsAlive() && U->GetTeam() == Team) { Pop += U->Stats().PopCost; }
		}
	}
	return Pop;
}

int32 USREconomySubsystem::GetQueuedPopulation(ESRTeam Team) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	int32 Pop = 0;
	for (const ASRBuilding* B : Buildings)
	{
		if (B && B->Team == Team && B->IsAlive())
		{
			for (ESRUnitType T : B->GetQueue()) { Pop += F.StatsFor(T).PopCost; }
		}
	}
	return Pop;
}

int32 USREconomySubsystem::GetPopulationCap(ESRTeam Team) const
{
	int32 Cap = 0;
	for (const ASRBuilding* B : Buildings)
	{
		if (B && B->Team == Team) { Cap += B->GetPopProvided(); }
	}
	return FMath::Min(Cap, GetPopulationCeiling(Team));
}

int32 USREconomySubsystem::GetCastleLevel(ESRTeam Team) const
{
	const ASRBuilding* Castle = GetCastle(Team);
	return Castle ? Castle->GetLevel() : 1;
}

int32 USREconomySubsystem::GetPopulationCeiling(ESRTeam Team) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return GetCastle(Team) ? F.CastleLevel(GetCastleLevel(Team)).PopulationCeiling : F.MaxPopulation;
}

int32 USREconomySubsystem::GetMaxTowers(ESRTeam Team) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return F.TowerLimitBase + F.TowerLimitPerCastleLevel * FMath::Max(0, GetCastleLevel(Team) - 1);
}

int32 USREconomySubsystem::GetMaxBuilders(ESRTeam Team) const
{
	return USRFeelSettings::Get().CastleLevel(GetCastleLevel(Team)).Builders;
}

int32 USREconomySubsystem::GetStorage(ESRTeam Team, ESRResource Resource) const
{
	const FSRCost& S = USRFeelSettings::Get().CastleLevel(GetCastleLevel(Team)).Storage;
	return (Resource == ESRResource::Gold ? S.Gold : S.Food) + GetStoreCapacity(Team, Resource);
}

int32 USREconomySubsystem::GetStoreCapacity(ESRTeam Team, ESRResource Resource) const
{
	const ESRBuildingType Type = Resource == ESRResource::Gold ? ESRBuildingType::Treasury : ESRBuildingType::Granary;
	int32 Cap = 0;
	for (const ASRBuilding* B : Buildings)
	{
		if (B && B->Team == Team && B->BuildingType == Type && B->IsFinished()) { Cap += B->GetStoreCapacity(); }
	}
	return Cap;
}

int32 USREconomySubsystem::GetMaxStores(ESRTeam Team) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return F.StoreLimitBase + FMath::Max(0, GetCastleLevel(Team) - 1) / FMath::Max(1, F.StoreLimitCastleLevels);
}

int32 USREconomySubsystem::CountStanding(ESRBuildingType Type, ESRTeam Team) const
{
	int32 N = 0;
	for (const ASRBuilding* B : Buildings)
	{
		N += (B && B->Team == Team && B->BuildingType == Type && B->IsAlive()) ? 1 : 0;
	}
	return N;
}

int32 USREconomySubsystem::GetScoutCount(ESRTeam Team, int32* OutQueued) const
{
	int32 Alive = 0, Queued = 0;
	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		for (const ASRUnit* U : Battle->GetUnits())
		{
			Alive += (U && U->IsAlive() && U->GetTeam() == Team && U->GetUnitType() == ESRUnitType::Scout) ? 1 : 0;
		}
	}
	for (const ASRBuilding* B : Buildings)
	{
		if (!B || B->Team != Team || !B->IsAlive()) { continue; }
		for (ESRUnitType T : B->GetQueue()) { Queued += T == ESRUnitType::Scout ? 1 : 0; }
	}
	if (OutQueued) { *OutQueued = Queued; }
	return Alive;
}

FText USREconomySubsystem::GetScoutRefusal(ESRTeam Team) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (GetCastleLevel(Team) < F.ScoutCastleLevel)
	{
		return FText::Format(NSLOCTEXT("SREconomy", "ScoutLevel", "A Scout needs the Citadel at level {0}"), FText::AsNumber(F.ScoutCastleLevel));
	}
	int32 Queued = 0;
	if (GetScoutCount(Team, &Queued) + Queued >= F.MaxScouts)
	{
		return F.MaxScouts == 1 ? NSLOCTEXT("SREconomy", "ScoutOne", "You already have a Scout (a kingdom has only one at a time)")
			: FText::Format(NSLOCTEXT("SREconomy", "ScoutMany", "You can have at most {0} Scouts"), FText::AsNumber(F.MaxScouts));
	}
	if (const float Left = GetScoutCooldown(Team); Left > 0.f)
	{
		const int32 Sec = FMath::CeilToInt(Left);
		return FText::Format(NSLOCTEXT("SREconomy", "ScoutWait", "The next Scout can be trained in {0}:{1}"), FText::AsNumber(Sec / 60),
			FText::FromString(FString::Printf(TEXT("%02d"), Sec % 60)));
	}
	return FText::GetEmpty();
}

void USREconomySubsystem::NotifyPopulationCapped(ESRTeam Team)
{
	if (Team != ESRTeam::Player) { return; }
	PopFlash = 1.f;
	PushAlert(ESRAlertKind::PopulationCapped, NSLOCTEXT("SREconomy", "PopCap", "Not enough housing: build more farms"));
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::UIError); }
}

// ------------------------------------------------------------------ buildings

ASRBuilding* USREconomySubsystem::GetCastle(ESRTeam Team) const
{
	for (ASRBuilding* B : Buildings)
	{
		if (B && B->Team == Team && B->IsCastle() && B->IsAlive()) { return B; }
	}
	return nullptr;
}

int32 USREconomySubsystem::CountFinished(ESRBuildingType Type, ESRTeam Team) const
{
	int32 N = 0;
	for (const ASRBuilding* B : Buildings)
	{
		N += (B && B->Team == Team && B->BuildingType == Type && B->IsFinished()) ? 1 : 0;
	}
	return N;
}

bool USREconomySubsystem::IsInBuildZone(ESRTeam Team, const FVector2D& At) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	for (const ASRBuilding* B : Buildings)
	{
		if (!B || B->Team != Team || !B->IsAlive() || !B->IsFinished()) { continue; }
		const float R = B->GetBuildZoneRadius();
		if (R > 0.f && FVector2D::DistSquared(B->GetFootprintCentre(), At) <= R * R) { return true; }
	}
	return false;
}

int32 USREconomySubsystem::GetBuilderCount(ESRTeam Team, int32* OutQueued) const
{
	int32 Alive = 0, Queued = 0;
	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Alive = Battle->CountBuilders(Team); }
	for (const ASRBuilding* B : Buildings)
	{
		if (!B || B->Team != Team || !B->IsAlive()) { continue; }
		for (ESRUnitType T : B->GetQueue()) { Queued += T == ESRUnitType::Builder ? 1 : 0; }
	}
	if (OutQueued) { *OutQueued = Queued; }
	return Alive;
}

ASRBuilding* USREconomySubsystem::PlaceBuilding(ESRBuildingType Type, ESRTeam Team, const FVector2D& Want, FText* OutReason)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (!Grid) { return nullptr; }
	const FSRPlacement Placement = Grid->CheckPlacement(Type, Team, Want);
	if (!Placement.bValid)
	{
		if (OutReason) { *OutReason = Placement.Reason; }
		return nullptr;
	}
	if ((Type == ESRBuildingType::Granary || Type == ESRBuildingType::Treasury) && CountStanding(Type, Team) >= GetMaxStores(Team))
	{
		if (OutReason)
		{
			*OutReason = FText::Format(NSLOCTEXT("SREconomy", "StoreCap", "You can have at most {0} of these (raise the Citadel for more)"), FText::AsNumber(GetMaxStores(Team)));
		}
		return nullptr;
	}
	const FSRCost& Cost = F.BuildingStatsFor(Type).Cost;
	if (!TrySpend(Team, Cost))
	{
		if (OutReason) { *OutReason = FText::Format(NSLOCTEXT("SREconomy", "NeedGold", "Not enough gold ({0} needed)"), FText::AsNumber(Cost.Gold)); }
		return nullptr;
	}
	ASRBuilding* B = ASRBuilding::SpawnBuilding(GetWorld(), Type, Team, Placement.Location, true);
	if (B) { B->SetNeedsBuilder(Placement.bNeedsBuilder); }
	if (B && Type == ESRBuildingType::Mine && Placement.VeinIndex != INDEX_NONE) { Grid->ClaimVein(Placement.VeinIndex, B); }
	return B;
}

void USREconomySubsystem::NotifyBuildingFinished(ASRBuilding* Building)
{
	if (USRBattleSubsystem* Battle = Building ? USRBattleSubsystem::Get(this) : nullptr) { Battle->NoteBuildingBuilt(Building->Team); }
	if (Building && Building->Team == ESRTeam::Player)
	{
		const FVector2D At = Building->GetFootprintCentre();
		PushAlert(ESRAlertKind::BuildingDone, FText::Format(NSLOCTEXT("SREconomy", "Done", "{0} completed"), FText::FromString(Building->GetDisplayName())), &At);
	}
}

void USREconomySubsystem::NotifyBuildingAttacked(ASRBuilding* Building, ASRUnit* Attacker)
{
	if (!Building) { return; }
	const double Now = GetWorld()->GetTimeSeconds();
	const int32 T = int32(Building->Team);
	LastAttackTime[T] = Now;
	LastAttackLocation[T] = Building->GetFootprintCentre();
	if (Building->Team != ESRTeam::Player) { return; }
	double& Last = LastAttackAlert.FindOrAdd(Building);
	if (Now - Last < 10.0) { return; }
	Last = Now;
	const FVector2D At = Building->GetFootprintCentre();
	PushAlert(ESRAlertKind::UnderAttack, FText::Format(NSLOCTEXT("SREconomy", "Attacked", "Your {0} is under attack!"), FText::FromString(Building->GetDisplayName())), &At);
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::AttackAlert); }
}

void USREconomySubsystem::NotifyUnitAttacked(const ASRUnit* Victim)
{
	// Troops hit somewhere the player is not looking: one alert (and click to go there), at most every 15 s, and not on
	// top of a building alert from the same fight.
	if (!Victim || Victim->GetTeam() != ESRTeam::Player) { return; }
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || FVector2D::DistSquared(Victim->GetPos2D(), Battle->GetSpriteView().FocusXY) < FMath::Square(2600.f)) { return; }
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastUnitAttackAlert < 15.0) { return; }
	const int32 T = int32(ESRTeam::Player);
	if (Now - LastAttackTime[T] < 6.0 && FVector2D::DistSquared(LastAttackLocation[T], Victim->GetPos2D()) < FMath::Square(3000.f)) { return; }
	LastUnitAttackAlert = Now;
	const FVector2D At = Victim->GetPos2D();
	PushAlert(ESRAlertKind::UnderAttack, NSLOCTEXT("SREconomy", "TroopsAttacked", "Your troops are under attack!"), &At);
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::AttackAlert); }
}

void USREconomySubsystem::NotifyBuildingDestroyed(ASRBuilding* Building)
{
	if (!Building) { return; }
	// A storehouse that falls takes what it held with it: whatever no longer fits in the kingdom's remaining stores
	// is lost (it is already out of GetStorage: the building is down by the time this is called).
	// (Only one that was finished: a site held nothing.)
	if (Building->IsStore() && Building->GetBuildProgress() >= 1.f)
	{
		const ESRResource Resource = Building->BuildingType == ESRBuildingType::Granary ? ESRResource::Food : ESRResource::Gold;
		int32& Value = Stock[int32(Building->Team)][int32(Resource)];
		const int32 Lost = Value - GetStorage(Building->Team, Resource);
		if (Lost > 0)
		{
			Value -= Lost;
			UE_LOG(LogSovereign, Log, TEXT("STORE %s %s fell: %d %s lost (now %d of %d)"), Building->Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"),
				*Building->GetDisplayName(), Lost, Resource == ESRResource::Food ? TEXT("food") : TEXT("gold"), Value, GetStorage(Building->Team, Resource));
			if (Building->Team == ESRTeam::Player)
			{
				const FVector2D At = Building->GetFootprintCentre();
				PushAlert(ESRAlertKind::BuildingLost, FText::Format(NSLOCTEXT("SREconomy", "StoreLost", "{0} destroyed: {1} {2} lost with it"),
					FText::FromString(Building->GetDisplayName()), FText::AsNumber(Lost),
					Resource == ESRResource::Food ? NSLOCTEXT("SREconomy", "FoodWord", "food") : NSLOCTEXT("SREconomy", "GoldWord", "gold")), &At);
				Flash[int32(Resource)] = 1.f;
				if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->NotifyBuildingDestroyed(Building); }
				return;   // (the alert above stands in for the plain "destroyed" one)
			}
		}
	}
	if (Building->Team == ESRTeam::Player)
	{
		const FVector2D At = Building->GetFootprintCentre();
		PushAlert(ESRAlertKind::BuildingLost, FText::Format(NSLOCTEXT("SREconomy", "Lost", "{0} destroyed"), FText::FromString(Building->GetDisplayName())), &At);
	}
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->NotifyBuildingDestroyed(Building); }
}

void USREconomySubsystem::PushAlert(ESRAlertKind Kind, const FText& Text, const FVector2D* Location)
{
	FSRAlert& A = Alerts.AddDefaulted_GetRef();
	A.Kind = Kind;
	A.Text = Text;
	A.bHasLocation = Location != nullptr;
	if (Location) { A.Location = *Location; }
	while (Alerts.Num() > 5) { Alerts.RemoveAt(0); }
	UE_LOG(LogSovereign, Log, TEXT("ALERT %s"), *Text.ToString());
}
