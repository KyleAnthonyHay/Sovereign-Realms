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
	Shieldbearer.MaxSpeed = 450.f;
	Shieldbearer.Acceleration = 2400.f;
	Shieldbearer.Deceleration = 3000.f;
	Shieldbearer.TurnRateDeg = 520.f;
	Shieldbearer.bRanged = false;
	Shieldbearer.AttackRange = 34.f;
	Shieldbearer.AcquireRange = 1300.f;   // line of sight: what it notices and goes for
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
	Archer.MaxSpeed = 505.f;
	Archer.Acceleration = 2800.f;
	Archer.Deceleration = 3200.f;
	Archer.TurnRateDeg = 640.f;
	Archer.bRanged = true;
	Archer.AttackRange = 880.f;
	Archer.AcquireRange = 1500.f;
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

	// Horse Rider: fast light cavalry. Hits and runs; the first blow of a charge lands double.
	Horseman.DisplayName = TEXT("Horse Rider");
	Horseman.MaxHealth = 230.f;
	Horseman.Radius = 70.f;
	Horseman.Mass = 2.4f;
	Horseman.MaxSpeed = 735.f;
	Horseman.Acceleration = 2600.f;
	Horseman.Deceleration = 3200.f;
	Horseman.TurnRateDeg = 420.f;
	Horseman.bRanged = false;
	Horseman.AttackRange = 55.f;
	Horseman.AcquireRange = 1500.f;
	Horseman.Damage = 24.f;
	Horseman.AttackInterval = 1.3f;
	Horseman.WindupTime = 0.30f;
	Horseman.RecoveryTime = 0.40f;
	Horseman.KnockbackImpulse = 320.f;
	Horseman.bHeavyHits = true;
	Horseman.BuildingDamageScale = 0.5f;
	Horseman.PopCost = 2;
	Horseman.ChargeMultiplier = 2.2f;
	Horseman.ChargeRestTime = 4.f;

	// Catapult: slow, fragile up close, deadly at range; wrecks buildings and scatters packed troops.
	Catapult.DisplayName = TEXT("Catapult");
	Catapult.MaxHealth = 500.f;   // sturdy timbers: it must live long enough to reach the walls
	Catapult.Radius = 110.f;
	Catapult.Mass = 4.f;
	Catapult.MaxSpeed = 360.f;
	Catapult.Acceleration = 1300.f;
	Catapult.Deceleration = 1900.f;
	Catapult.TurnRateDeg = 170.f;
	Catapult.bRanged = true;
	Catapult.AttackRange = 1700.f;
	Catapult.AcquireRange = 1800.f;
	Catapult.MinRange = 450.f;
	Catapult.Damage = 70.f;
	Catapult.AttackInterval = 4.5f;
	Catapult.WindupTime = 1.6f;
	Catapult.RecoveryTime = 0.6f;
	Catapult.KnockbackImpulse = 260.f;
	Catapult.bHeavyHits = true;
	Catapult.ProjectileSpeed = 1300.f;
	Catapult.ProjectileArc = 0.33f;
	Catapult.SplashRadius = 230.f;
	Catapult.bStoneProjectile = true;
	Catapult.bPrefersBuildings = true;
	Catapult.BuildingDamageScale = 3.f;
	Catapult.PopCost = 3;

	// Builder: a lightly armed craftsman. Raises buildings outside the castle's zone and repairs; never starts a fight.
	Builder.DisplayName = TEXT("Builder");
	Builder.MaxHealth = 110.f;
	Builder.Radius = 34.f;
	Builder.Mass = 0.9f;
	Builder.MaxSpeed = 435.f;
	Builder.Acceleration = 2600.f;
	Builder.Deceleration = 3000.f;
	Builder.TurnRateDeg = 600.f;
	Builder.bRanged = false;
	Builder.AttackRange = 30.f;
	Builder.AcquireRange = 0.f;
	Builder.SightRange = 1000.f;
	Builder.Damage = 6.f;
	Builder.AttackInterval = 1.3f;
	Builder.WindupTime = 0.45f;
	Builder.RecoveryTime = 0.45f;
	Builder.KnockbackImpulse = 60.f;
	Builder.BuildingDamageScale = 0.5f;
	Builder.PopCost = 0;   // builders have their own limit (the castle's level), not the troops' housing
	Builder.bBuilder = true;

	// Scout: a hooded runner with a light spear. Outruns cavalry, sees a long way, and is only noticed from close by
	// (NoticeScale); a single blow from anything nearly finishes it. It never picks a fight (no acquire range): it
	// strikes only what it is ordered to, or what is hitting it.
	Scout.DisplayName = TEXT("Scout");
	Scout.MaxHealth = 90.f;
	Scout.Radius = 34.f;
	Scout.Mass = 0.7f;
	Scout.MaxSpeed = 875.f;          // the Horse Rider does 735
	Scout.Acceleration = 3600.f;
	Scout.Deceleration = 3800.f;
	Scout.TurnRateDeg = 720.f;
	Scout.bRanged = false;
	Scout.AttackRange = 34.f;
	Scout.AcquireRange = 0.f;
	Scout.SightRange = 2600.f;       // an Archer sees 1500, a Catapult 1800
	Scout.Damage = 8.f;
	Scout.AttackInterval = 1.2f;
	Scout.WindupTime = 0.32f;
	Scout.RecoveryTime = 0.36f;
	Scout.KnockbackImpulse = 60.f;
	Scout.BuildingDamageScale = 0.2f;
	Scout.PopCost = 1;
	Scout.NoticeScale = 0.45f;       // foes notice it at under half their usual distance
	Scout.WalkCycleDistance = 192.f; // a sprinter's stride (Tools/blender/char_worker.py, scout)

	// Medic: a field medic with a bag of bandages. Runs to a wounded troop of its side, kneels and bandages it, then on
	// to the next (Sovereign Feel > Medics); never strikes anyone. Passive (Defensive): runs from foes; Assertive
	// (Aggressive): goes into the fight to heal. Trained at the Barracks.
	Medic.DisplayName = TEXT("Medic");
	Medic.MaxHealth = 120.f;
	Medic.Radius = 34.f;
	Medic.Mass = 0.8f;
	Medic.MaxSpeed = 620.f;          // quick: Shieldbearers do 450, a Horse Rider 735
	Medic.Acceleration = 3200.f;
	Medic.Deceleration = 3400.f;
	Medic.TurnRateDeg = 600.f;
	Medic.bRanged = false;
	Medic.AttackRange = 30.f;
	Medic.AcquireRange = 0.f;        // picks no fights
	Medic.SightRange = 1400.f;
	Medic.Damage = 0.f;
	Medic.AttackInterval = 1.5f;     // a bandaging every 1.5 s
	Medic.WindupTime = 0.45f;        // down on one knee, bandage out (the heal lands as it is pressed on)...
	Medic.RecoveryTime = 0.45f;      // ...and up again
	Medic.KnockbackImpulse = 0.f;
	Medic.BuildingDamageScale = 0.f;
	Medic.PopCost = 1;

	// ---- buildings (shapes from SourceArt/Buildings/<type>.json; the tower is SM_Bld_Tower) ----
	auto Mesh = [](const TCHAR* Name) { return TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(FString::Printf(TEXT("/Game/SR/Buildings/%s.%s"), Name, Name))); };

	CastleStats.DisplayName = TEXT("Citadel");
	CastleStats.MaxHealth = 12000.f;
	CastleStats.Cost = FSRCost(0, 0);
	CastleStats.BuildTime = 60.f;
	CastleStats.PopProvided = 8;
	CastleStats.TerritoryRadius = 4200.f;   // the building zone: beyond it a Builder must go and build
	CastleStats.bPlayerBuildable = false;
	CastleStats.Category = ESRBuildCategory::Defence;
	CastleStats.Blurb = TEXT("The seat of your kingdom: houses troops, has archers on its corner pillars (more as it rises), trains Builders and (from level 3) a Scout. If it falls, you lose.");
	CastleStats.bRecruits = true;
	CastleStats.RecruitType = ESRUnitType::Builder;
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
	TowerStats.Mesh = Mesh(TEXT("SM_Bld_Tower"));
	TowerStats.Category = ESRBuildCategory::Defence;
	TowerStats.Blurb = TEXT("Archers on the top shoot any enemy in range.");
	TowerStats.FootprintMin = FVector2D(-220.f, -220.f);
	TowerStats.FootprintMax = FVector2D(220.f, 220.f);
	TowerStats.BlockHeight = 900.f;
	TowerStats.GateOffset = FVector(-280.f, 0.f, 0.f);
	TowerStats.LabelOffset = FVector(0.f, 0.f, 1050.f);
	TowerStats.PopupOffset = FVector(0.f, 0.f, 700.f);
	TowerStats.AttackRange = 2400.f;   // a long reach: archers on a height
	TowerStats.AttackDamage = 50.f;   // (level 1 of TowerLevels below)
	TowerStats.AttackInterval = 1.2f;
	TowerStats.MuzzleHeight = 860.f;

	// Relic Tower: raised on a relic, one of the map's ancient ruins (a broken tower, a stone circle; the level's
	// actors tagged SRRelic). Built only there (it snaps on, like a mine onto a vein), outside every castle's zone,
	// so a Builder raises it. Two archers, a very long reach (a Watchtower's is 24-30 m) and the sight to match.
	// Its model: Tools/blender/bld_relictower.py.
	RelicTowerStats = TowerStats;
	RelicTowerStats.DisplayName = TEXT("Relic Tower");
	RelicTowerStats.Mesh = Mesh(TEXT("SM_Bld_RelicTower"));
	RelicTowerStats.FootprintMin = FVector2D(-250.f, -250.f);
	RelicTowerStats.FootprintMax = FVector2D(250.f, 250.f);
	RelicTowerStats.BlockHeight = 1190.f;                       // (SourceArt/Buildings/relictower.json)
	RelicTowerStats.GateOffset = FVector(-310.f, 0.f, 0.f);
	RelicTowerStats.LabelOffset = FVector(0.f, 0.f, 1504.f);
	RelicTowerStats.PopupOffset = FVector(0.f, 0.f, 1000.f);
	RelicTowerStats.MuzzleHeight = 1150.f;                      // the fighting top
	RelicTowerStats.SecondMuzzleHeight = 400.f;                 // the gallery round the foot of the shaft
	RelicTowerStats.MaxHealth = 4500.f;
	RelicTowerStats.Cost = FSRCost(900, 300);
	RelicTowerStats.BuildTime = 75.f;
	RelicTowerStats.Blurb = TEXT("An ancient tower raised again from its relic ruin: two archers, a very long reach, and a view far over the field.");
	RelicTowerStats.AttackRange = 4200.f;
	RelicTowerStats.AttackDamage = 85.f;
	RelicTowerStats.AttackInterval = 1.1f;
	RelicTowerStats.Archers = 2;
	RelicTowerStats.bPlayerBuildable = false;   // not in the build menu: Builders repair a relic ruin into one

	// Siege Tower: a squat stone tower with a stone-thrower on top. Slow heavy shots that land on the target's spot and
	// hurt every foe round it; it cannot reach what is right under it. Its model: Tools/blender/bld_siegetower.py.
	SiegeTowerStats = TowerStats;
	SiegeTowerStats.DisplayName = TEXT("Siege Tower");
	SiegeTowerStats.Mesh = Mesh(TEXT("SM_Bld_SiegeTower"));
	SiegeTowerStats.MaxHealth = 2600.f;
	SiegeTowerStats.Cost = FSRCost(380, 120);
	SiegeTowerStats.BuildTime = 40.f;
	SiegeTowerStats.Blurb = TEXT("A stone-thrower on a squat tower: slow, heavy shots that hurt every foe where they land. It cannot hit what is right under it.");
	SiegeTowerStats.FootprintMin = FVector2D(-240.f, -240.f);
	SiegeTowerStats.FootprintMax = FVector2D(240.f, 240.f);
	SiegeTowerStats.BlockHeight = 800.f;
	SiegeTowerStats.GateOffset = FVector(-300.f, 0.f, 0.f);
	SiegeTowerStats.LabelOffset = FVector(0.f, 0.f, 1240.f);   // (SourceArt/Buildings/siegetower.json sockets)
	SiegeTowerStats.PopupOffset = FVector(0.f, 0.f, 640.f);
	SiegeTowerStats.MuzzleHeight = 1110.f;                     // the cup at the end of the arm
	SiegeTowerStats.AttackRange = 3000.f;
	SiegeTowerStats.MinRange = 500.f;
	SiegeTowerStats.AttackDamage = 70.f;
	SiegeTowerStats.AttackInterval = 4.2f;
	SiegeTowerStats.SplashRadius = 260.f;
	SiegeTowerStats.Archers = 1;

	// Barracks and range: shapes from SourceArt/Buildings/barracks.json and range.json (Tools/blender/bld_barracks.py, bld_range.py).
	BarracksStats.DisplayName = TEXT("Barracks");
	BarracksStats.MaxHealth = 1600.f;
	BarracksStats.Cost = FSRCost(110, 0);
	BarracksStats.BuildTime = 16.f;
	BarracksStats.PopProvided = 0;
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

	// Stable and siege workshop: SourceArt/Buildings/stable.json, workshop.json (Tools/blender/bld_stable.py, bld_workshop.py).
	StableStats = BarracksStats;
	StableStats.DisplayName = TEXT("Stable");
	StableStats.MaxHealth = 1500.f;
	StableStats.Cost = FSRCost(150, 0);
	StableStats.BuildTime = 20.f;
	StableStats.Mesh = Mesh(TEXT("SM_Bld_Stable"));
	StableStats.Blurb = TEXT("Trains Horse Riders: fast cavalry whose charge lands double. Right-click with it selected to set their muster.");
	StableStats.RecruitType = ESRUnitType::Horseman;
	StableStats.FootprintMin = FVector2D(-500.f, -450.f);
	StableStats.FootprintMax = FVector2D(500.f, 450.f);
	StableStats.BlockHeight = 320.f;
	StableStats.GateOffset = FVector(-570.f, 0.f, 0.f);
	StableStats.LabelOffset = FVector(200.f, 0.f, 640.f);
	StableStats.PopupOffset = FVector(0.f, 0.f, 420.f);

	WorkshopStats = BarracksStats;
	WorkshopStats.DisplayName = TEXT("Siege Workshop");
	WorkshopStats.MaxHealth = 1600.f;
	WorkshopStats.Cost = FSRCost(200, 0);
	WorkshopStats.BuildTime = 24.f;
	WorkshopStats.Mesh = Mesh(TEXT("SM_Bld_Workshop"));
	WorkshopStats.Blurb = TEXT("Builds Catapults: long range, splash, wreck buildings; slow and weak up close.");
	WorkshopStats.RecruitType = ESRUnitType::Catapult;
	WorkshopStats.FootprintMin = FVector2D(-500.f, -500.f);
	WorkshopStats.FootprintMax = FVector2D(500.f, 500.f);
	WorkshopStats.BlockHeight = 360.f;
	WorkshopStats.GateOffset = FVector(-570.f, 0.f, 0.f);
	WorkshopStats.LabelOffset = FVector(200.f, 0.f, 680.f);
	WorkshopStats.PopupOffset = FVector(0.f, 0.f, 460.f);

	// Granary and treasury: SourceArt/Buildings/granary.json, treasury.json (Tools/blender/bld_granary.py, bld_treasury.py).
	GranaryStats.DisplayName = TEXT("Granary");
	GranaryStats.MaxHealth = 900.f;
	GranaryStats.Cost = FSRCost(120, 0);
	GranaryStats.BuildTime = 14.f;
	GranaryStats.PopProvided = 0;
	GranaryStats.Mesh = Mesh(TEXT("SM_Bld_Granary"));
	GranaryStats.Category = ESRBuildCategory::Economy;
	GranaryStats.Blurb = TEXT("Holds food on top of the Citadel's stores, so the harvest is not lost when they are full.");
	GranaryStats.FootprintMin = FVector2D(-320.f, -320.f);
	GranaryStats.FootprintMax = FVector2D(320.f, 320.f);
	GranaryStats.BlockHeight = 420.f;
	GranaryStats.GateOffset = FVector(-380.f, 0.f, 0.f);
	GranaryStats.LabelOffset = FVector(0.f, 0.f, 608.f);
	GranaryStats.PopupOffset = FVector(-200.f, 0.f, 260.f);

	TreasuryStats = GranaryStats;
	TreasuryStats.DisplayName = TEXT("Treasury");
	TreasuryStats.MaxHealth = 1100.f;
	TreasuryStats.Cost = FSRCost(140, 0);
	TreasuryStats.BuildTime = 16.f;
	TreasuryStats.Mesh = Mesh(TEXT("SM_Bld_Treasury"));
	TreasuryStats.Blurb = TEXT("Holds gold on top of the Citadel's stores: an iron-banded strongroom for what the mines bring in.");
	TreasuryStats.FootprintMin = FVector2D(-300.f, -300.f);
	TreasuryStats.FootprintMax = FVector2D(300.f, 300.f);
	TreasuryStats.BlockHeight = 380.f;
	TreasuryStats.GateOffset = FVector(-360.f, 0.f, 0.f);
	TreasuryStats.LabelOffset = FVector(0.f, 0.f, 602.f);
	TreasuryStats.PopupOffset = FVector(-200.f, 0.f, 240.f);

	// Storehouse levels: price, time, what it holds, health. One at level 3 holds as much again as a level-3 castle;
	// a kingdom may have one of each, plus one for every two castle levels (StoreLimitBase / StoreLimitCastleLevels).
	// (one of each; raising one to level 2 needs the Citadel at level 2, to level 3 the Citadel at level 3)
	auto SL = [](int32 G, int32 Fd, float Time, int32 Cap, float Hp, int32 Castle)
	{
		FSRStoreLevel L; L.UpgradeCost = FSRCost(G, Fd); L.UpgradeTime = Time; L.Capacity = Cap; L.Health = Hp; L.RequiredCastleLevel = Castle;
		return L;
	};
	GranaryLevels = { SL(0, 0, 0.f, 400, 900.f, 0), SL(180, 0, 30.f, 900, 1200.f, 2), SL(320, 80, 40.f, 1600, 1500.f, 3) };
	TreasuryLevels = { SL(0, 0, 0.f, 400, 1100.f, 0), SL(200, 0, 30.f, 900, 1450.f, 2), SL(340, 80, 40.f, 1600, 1800.f, 3) };

	// farms: three to start (one more per Citadel level), each raised for more food and more housing
	auto FL = [](int32 G, int32 Fd, float Time, int32 Food, int32 House, float Hp)
	{
		FSRFarmLevel L; L.UpgradeCost = FSRCost(G, Fd); L.UpgradeTime = Time; L.FoodPerPayout = Food; L.Housing = House; L.Health = Hp;
		return L;
	};
	FarmLevels = { FL(0, 0, 0.f, 14, 4, 1000.f), FL(200, 0, 30.f, 20, 6, 1300.f), FL(340, 60, 40.f, 27, 8, 1600.f) };

	// Castle levels. Level 1 matches CastleStats above. Each level: price, time, castle housing, troop ceiling,
	// builders, building zone (cm), health, storage (gold, food). The stores always hold the next level's price; the
	// troop ceiling stops at 120 a side; the zone stays well short of halfway to the enemy (the castles are ~148 m apart).
	auto Lv = [](int32 G, int32 Fd, float Time, int32 House, int32 Ceil, int32 Bld, float Zone, float Hp, int32 SG, int32 SF)
	{
		FSRCastleLevel L;
		L.UpgradeCost = FSRCost(G, Fd); L.UpgradeTime = Time; L.Housing = House; L.PopulationCeiling = Ceil; L.Builders = Bld;
		L.BuildZone = Zone; L.Health = Hp; L.Storage = FSRCost(SG, SF);
		return L;
	};
	CastleLevels = {
		Lv(0,    0,   0.f,  8,  36,  2, 4200.f, 12000.f,  600,  600),
		Lv(300,  0,   40.f, 16, 48,  3, 4700.f, 15000.f, 1000, 1000),
		Lv(550,  150, 45.f, 24, 60,  3, 5200.f, 18000.f, 1500, 1500),
		Lv(850,  300, 55.f, 32, 75,  4, 5700.f, 21000.f, 2200, 2200),
		Lv(1200, 450, 65.f, 42, 90,  4, 6200.f, 24000.f, 3000, 3000),
		Lv(1650, 650, 75.f, 52, 105, 5, 6700.f, 27000.f, 4000, 4000),
		Lv(2200, 900, 90.f, 64, 120, 6, 7200.f, 30000.f, 5500, 5500),
	};
	// archers on the corner pillars and their arrows' damage, by castle level (1 at level 1 up to all four pillars at 7)
	{
		const int32 Arch[7] = { 1, 2, 2, 3, 3, 4, 4 };
		const float Dmg[7] = { 36.f, 36.f, 40.f, 40.f, 44.f, 44.f, 48.f };
		for (int32 i = 0; i < CastleLevels.Num() && i < 7; ++i) { CastleLevels[i].Archers = Arch[i]; CastleLevels[i].ArrowDamage = Dmg[i]; }
	}

	// Watchtower levels (after Kingdom Rush's archer towers: by level 3 about 3.5x the damage per second and a quarter
	// more reach; each upgrade dearer than the last).
	auto TL = [](int32 G, float Time, float Dmg, float Iv, float Range, float Hp)
	{
		FSRTowerLevel L; L.UpgradeCost = FSRCost(G, 0); L.UpgradeTime = Time; L.Damage = Dmg; L.Interval = Iv; L.Range = Range; L.Health = Hp;
		return L;
	};
	TowerLevels = { TL(0, 0.f, 50.f, 1.2f, 2400.f, 1800.f), TL(250, 30.f, 85.f, 0.95f, 2700.f, 2300.f), TL(370, 40.f, 120.f, 0.8f, 3000.f, 2800.f) };

	// Gold mine levels: each upgrade pays for itself in four or five minutes.
	auto ML = [](int32 G, int32 Fd, float Time, int32 Gold, float Hp)
	{
		FSRMineLevel L; L.UpgradeCost = FSRCost(G, Fd); L.UpgradeTime = Time; L.GoldPerPayout = Gold; L.Health = Hp;
		return L;
	};
	MineLevels = { ML(0, 0, 0.f, 10, 1250.f), ML(220, 0, 30.f, 16, 1600.f), ML(360, 100, 40.f, 23, 2000.f) };

	// training buildings: level 2 trains a third faster, level 3 nearly twice as fast
	auto TrL = [](int32 G, int32 Fd, float Time, float Speed, float Hp)
	{
		FSRTrainerLevel L; L.UpgradeCost = FSRCost(G, Fd); L.UpgradeTime = Time; L.TrainSpeed = Speed; L.HealthScale = Hp;
		return L;
	};
	TrainerLevels = { TrL(0, 0, 0.f, 1.f, 1.f), TrL(200, 100, 30.f, 1.35f, 1.2f), TrL(380, 180, 40.f, 1.8f, 1.4f) };

	// The battle maps. (The four-cornered one is played by two kingdoms for now.)
	{
		FSRMapEntry Two;
		Two.Id = TEXT("two");
		Two.Level = TEXT("/Game/Maps/L_Battlefield");
		Two.Name = TEXT("THE RIVERLANDS");
		Two.Note = TEXT("Two kingdoms across the river. 480 m square.");
		FSRMapEntry Four;
		Four.Id = TEXT("four");
		Four.Level = TEXT("/Game/Maps/L_Battlefield4");
		Four.Name = TEXT("THE FOUR MARCHES");
		Four.Note = TEXT("Four corners round the High Moor (you against one rival for now). 720 m square.");
		Maps = { Two, Four };
	}

	AIBuildOrder = { ESRBuildingType::Barracks, ESRBuildingType::Farm, ESRBuildingType::Range, ESRBuildingType::Mine, ESRBuildingType::Farm,
		ESRBuildingType::Tower, ESRBuildingType::Farm, ESRBuildingType::Mine, ESRBuildingType::Farm };
}
