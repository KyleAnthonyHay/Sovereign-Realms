// Copyright Sovereign Realms.

#include "Common/SRFeelSettings.h"
#include "Engine/StaticMesh.h"

USRFeelSettings::USRFeelSettings()
{
	// Shieldbearer: sturdy front-liner. Slower, hits land with weight.
	Shieldbearer.DisplayName = TEXT("Shieldbearer");
	Shieldbearer.MaxHealth = 280.f;
	Shieldbearer.Radius = 44.f;
	Shieldbearer.Mass = 1.6f;
	Shieldbearer.MaxSpeed = 390.f;
	Shieldbearer.Acceleration = 2400.f;
	Shieldbearer.Deceleration = 3000.f;
	Shieldbearer.TurnRateDeg = 520.f;
	Shieldbearer.bRanged = false;
	Shieldbearer.AttackRange = 34.f;
	Shieldbearer.AcquireRange = 760.f;
	Shieldbearer.Damage = 27.f;
	Shieldbearer.AttackInterval = 1.15f;
	Shieldbearer.WindupTime = 0.26f;
	Shieldbearer.RecoveryTime = 0.34f;
	Shieldbearer.KnockbackImpulse = 230.f;
	Shieldbearer.bHeavyHits = true;
	Shieldbearer.BuildingDamageScale = 1.f;
	Shieldbearer.PopCost = 1;

	// Archer: fragile, quick on its feet, long reach.
	Archer.DisplayName = TEXT("Archer");
	Archer.MaxHealth = 125.f;
	Archer.Radius = 36.f;
	Archer.Mass = 0.8f;
	Archer.MaxSpeed = 440.f;
	Archer.Acceleration = 2800.f;
	Archer.Deceleration = 3200.f;
	Archer.TurnRateDeg = 640.f;
	Archer.bRanged = true;
	Archer.AttackRange = 880.f;
	Archer.AcquireRange = 1050.f;
	Archer.Damage = 18.f;
	Archer.AttackInterval = 1.5f;
	Archer.WindupTime = 0.42f;
	Archer.RecoveryTime = 0.24f;
	Archer.KnockbackImpulse = 90.f;
	Archer.bHeavyHits = false;
	Archer.KeepDistance = 230.f;
	Archer.ProjectileSpeed = 1900.f;
	Archer.ProjectileArc = 0.16f;
	Archer.BuildingDamageScale = 0.35f;
	Archer.PopCost = 1;

	// ---- buildings (shapes from SourceArt/Buildings/<type>.json; the tower is SM_Bld_Tower) ----
	auto Mesh = [](const TCHAR* Name) { return TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(FString::Printf(TEXT("/Game/SR/Buildings/%s.%s"), Name, Name))); };

	CastleStats.DisplayName = TEXT("Citadel");
	CastleStats.MaxHealth = 12000.f;
	CastleStats.Cost = FSRCost(0, 0);
	CastleStats.BuildTime = 60.f;
	CastleStats.PopProvided = 8;
	CastleStats.TerritoryRadius = 3800.f;
	CastleStats.bPlayerBuildable = false;
	CastleStats.Category = ESRBuildCategory::Defence;
	CastleStats.Blurb = TEXT("The seat of your kingdom: houses troops and shoots from its walls. If it falls, you lose.");
	CastleStats.Mesh = Mesh(TEXT("SM_Bld_Castle"));
	CastleStats.FootprintMin = FVector2D(-560.f, -660.f);
	CastleStats.FootprintMax = FVector2D(560.f, 660.f);
	CastleStats.BlockHeight = 900.f;
	CastleStats.GateOffset = FVector(-600.f, 0.f, 0.f);
	CastleStats.LabelOffset = FVector(0.f, 0.f, 1168.f);
	CastleStats.PopupOffset = FVector(0.f, 0.f, 700.f);
	CastleStats.AttackRange = 1000.f;
	CastleStats.AttackDamage = 36.f;
	CastleStats.AttackInterval = 1.4f;
	CastleStats.MuzzleHeight = 820.f;

	FarmStats.DisplayName = TEXT("Farm");
	FarmStats.MaxHealth = 1000.f;
	FarmStats.Cost = FSRCost(90, 0);
	FarmStats.BuildTime = 14.f;
	FarmStats.PopProvided = 4;
	FarmStats.TerritoryRadius = 2400.f;
	FarmStats.Mesh = Mesh(TEXT("SM_Bld_Farm"));
	FarmStats.Category = ESRBuildCategory::Economy;
	FarmStats.Blurb = TEXT("Grows food (troops are paid in food) and houses troops.");
	FarmStats.FootprintMin = FVector2D(-440.f, -480.f);
	FarmStats.FootprintMax = FVector2D(440.f, 480.f);
	FarmStats.BlockHeight = 300.f;
	FarmStats.GateOffset = FVector(-500.f, 0.f, 0.f);
	FarmStats.LabelOffset = FVector(60.f, 0.f, 470.f);
	FarmStats.PopupOffset = FVector(-80.f, 170.f, 190.f);

	MineStats.DisplayName = TEXT("Gold Mine");
	MineStats.MaxHealth = 1250.f;
	MineStats.Cost = FSRCost(140, 0);
	MineStats.BuildTime = 16.f;
	MineStats.PopProvided = 0;
	MineStats.TerritoryRadius = 2000.f;
	MineStats.Mesh = Mesh(TEXT("SM_Bld_Mine"));
	MineStats.Category = ESRBuildCategory::Economy;
	MineStats.Blurb = TEXT("Digs gold (buildings are paid in gold). Only on a free gold vein.");
	MineStats.FootprintMin = FVector2D(-400.f, -420.f);
	MineStats.FootprintMax = FVector2D(420.f, 420.f);
	MineStats.BlockHeight = 420.f;
	MineStats.GateOffset = FVector(-460.f, 0.f, 0.f);
	MineStats.LabelOffset = FVector(120.f, 0.f, 620.f);
	MineStats.PopupOffset = FVector(-214.f, 0.f, 200.f);

	TowerStats.DisplayName = TEXT("Watchtower");
	TowerStats.MaxHealth = 1800.f;
	TowerStats.Cost = FSRCost(160, 0);
	TowerStats.BuildTime = 18.f;
	TowerStats.PopProvided = 0;
	TowerStats.TerritoryRadius = 1200.f;
	TowerStats.Mesh = Mesh(TEXT("SM_Bld_Tower"));
	TowerStats.Category = ESRBuildCategory::Defence;
	TowerStats.Blurb = TEXT("Archers on the top shoot any enemy in range.");
	TowerStats.FootprintMin = FVector2D(-220.f, -220.f);
	TowerStats.FootprintMax = FVector2D(220.f, 220.f);
	TowerStats.BlockHeight = 900.f;
	TowerStats.GateOffset = FVector(-280.f, 0.f, 0.f);
	TowerStats.LabelOffset = FVector(0.f, 0.f, 1050.f);
	TowerStats.PopupOffset = FVector(0.f, 0.f, 700.f);
	TowerStats.AttackRange = 1400.f;
	TowerStats.AttackDamage = 40.f;
	TowerStats.AttackInterval = 1.2f;
	TowerStats.MuzzleHeight = 860.f;

	// Barracks and range: shapes from SourceArt/Buildings/barracks.json and range.json (Tools/blender/bld_barracks.py, bld_range.py).
	BarracksStats.DisplayName = TEXT("Barracks");
	BarracksStats.MaxHealth = 1600.f;
	BarracksStats.Cost = FSRCost(110, 0);
	BarracksStats.BuildTime = 16.f;
	BarracksStats.PopProvided = 0;
	BarracksStats.TerritoryRadius = 1800.f;
	BarracksStats.Mesh = Mesh(TEXT("SM_Bld_Barracks"));
	BarracksStats.Category = ESRBuildCategory::Military;
	BarracksStats.Blurb = TEXT("Trains Shieldbearers. Right-click with it selected to set where they muster.");
	BarracksStats.bRecruits = true;
	BarracksStats.RecruitType = ESRUnitType::Shieldbearer;
	BarracksStats.FootprintMin = FVector2D(-460.f, -440.f);
	BarracksStats.FootprintMax = FVector2D(460.f, 440.f);
	BarracksStats.BlockHeight = 320.f;
	BarracksStats.GateOffset = FVector(-520.f, 0.f, 0.f);
	BarracksStats.LabelOffset = FVector(180.f, 0.f, 680.f);
	BarracksStats.PopupOffset = FVector(0.f, 0.f, 420.f);

	RangeStats = BarracksStats;
	RangeStats.DisplayName = TEXT("Archery Range");
	RangeStats.MaxHealth = 1400.f;
	RangeStats.Cost = FSRCost(125, 0);
	RangeStats.BuildTime = 16.f;
	RangeStats.Mesh = Mesh(TEXT("SM_Bld_Range"));
	RangeStats.Blurb = TEXT("Trains Archers. Right-click with it selected to set where they muster.");
	RangeStats.RecruitType = ESRUnitType::Archer;
	RangeStats.FootprintMin = FVector2D(-400.f, -400.f);
	RangeStats.FootprintMax = FVector2D(400.f, 400.f);
	RangeStats.BlockHeight = 280.f;
	RangeStats.GateOffset = FVector(-460.f, -190.f, 0.f);
	RangeStats.LabelOffset = FVector(120.f, 0.f, 520.f);
	RangeStats.PopupOffset = FVector(0.f, 0.f, 320.f);

	AIBuildOrder = { ESRBuildingType::Barracks, ESRBuildingType::Farm, ESRBuildingType::Range, ESRBuildingType::Mine, ESRBuildingType::Farm,
		ESRBuildingType::Tower, ESRBuildingType::Farm, ESRBuildingType::Mine, ESRBuildingType::Farm };
}
