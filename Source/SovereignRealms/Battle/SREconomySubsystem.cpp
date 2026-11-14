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

void USREconomySubsystem::AddResource(ESRTeam Team, ESRResource Resource, int32 Amount)
{
	int32& Value = Stock[int32(Team)][int32(Resource)];
	Value = FMath::Clamp(Value + Amount, 0, 999999);
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
	return CountFinished(ESRBuildingType::Mine, Team) * F.MineGoldPerPayout * 60.f / FMath::Max(F.MinePayoutInterval, 0.2f);
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
		if (Building && Building->RayHit(RayOrigin, RayDir, Along) && Along < BestAlong)
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
		for (ESRUnitType Type : Building->GetQueue()) { Queue += Type == ESRUnitType::Archer ? TEXT("A") : TEXT("S"); }
		UE_LOG(LogSovereign, Log, TEXT("  %-16s %-9s team=%d pos=(%6.0f,%6.0f) payout=%.2f queue=[%s] build=%.2f rally=(%.0f,%.0f) sel=%d"),
			*Building->GetActorNameOrLabel(), *Building->GetDisplayName(), int32(Building->Team), Building->GetActorLocation().X, Building->GetActorLocation().Y,
			Building->GetPayoutFraction(), *Queue, Building->GetBuildFraction(), Building->GetRallyPoint().X, Building->GetRallyPoint().Y, Building->IsSelected() ? 1 : 0);
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
	return FMath::Min(Cap, USRFeelSettings::Get().MaxPopulation);
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
	const FSRCost& Cost = F.BuildingStatsFor(Type).Cost;
	if (!TrySpend(Team, Cost))
	{
		if (OutReason) { *OutReason = FText::Format(NSLOCTEXT("SREconomy", "NeedGold", "Not enough gold ({0} needed)"), FText::AsNumber(Cost.Gold)); }
		return nullptr;
	}
	ASRBuilding* B = ASRBuilding::SpawnBuilding(GetWorld(), Type, Team, Placement.Location, true);
	if (B && Type == ESRBuildingType::Mine && Placement.VeinIndex != INDEX_NONE) { Grid->ClaimVein(Placement.VeinIndex, B); }
	return B;
}

void USREconomySubsystem::NotifyBuildingFinished(ASRBuilding* Building)
{
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
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::WarHorn, 0.6f); }
}

void USREconomySubsystem::NotifyBuildingDestroyed(ASRBuilding* Building)
{
	if (!Building) { return; }
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
