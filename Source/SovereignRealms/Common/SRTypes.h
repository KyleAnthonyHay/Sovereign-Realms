// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "SRTypes.generated.h"

UENUM(BlueprintType)
enum class ESRTeam : uint8
{
	Player,
	Enemy
};

/**
 * What a building is for. Castle: the kingdom's seat (it falls, the kingdom falls). Farm: food and housing. Mine: gold
 * (on a vein). Tower: shoots. Barracks: trains Shieldbearers. Range: trains Archers. New types go at the end (the
 * level stores the value).
 */
UENUM(BlueprintType)
enum class ESRBuildingType : uint8
{
	Castle,
	Farm,
	Mine,
	Tower,
	Barracks,
	Range,
	Stable,       // trains Horse Riders
	Workshop,     // builds Catapults
	Granary,      // holds food on top of the castle's stores
	Treasury,     // holds gold on top of the castle's stores
	RelicTower,   // raised on a relic (one of the map's ancient ruins): two archers, a very long reach and sight
	SiegeTower    // a stone-thrower on a squat tower: slow, heavy shots that hurt everyone where they land
};

/** The build menu's tabs. */
UENUM(BlueprintType)
enum class ESRBuildCategory : uint8
{
	Economy,
	Military,
	Defence
};

/** What a building looks like right now: the construction site, standing, battle-damaged, or a ruin. */
UENUM(BlueprintType)
enum class ESRBuildingState : uint8
{
	Site,
	Complete,
	Damaged,
	Ruin
};

/** How a platoon (and every unit in it) reacts to enemies it was not told to fight. */
UENUM(BlueprintType)
enum class ESRStance : uint8
{
	Aggressive,   // chase anything in acquire range, as far as it takes     (a Medic: Assertive, into the fight to heal)
	Defensive,    // engage what comes close, give up a short chase and return to position   (a Medic: Passive, runs from foes)
	HoldGround    // never move to fight; strike / shoot only what is in reach
};

/** The shape a group takes when it is ordered to move. */
UENUM(BlueprintType)
enum class ESRFormationShape : uint8
{
	Line,     // wide ranks, melee in front: the default battle line
	Column,   // narrow and deep: for roads, gaps and long marches
	Wedge,    // a point leading: for breaking a line
	Square,   // a compact block, ranged in the middle: for holding ground
	Loose     // formation off: the group keeps its own rough shape (squeezed in if it is spread wide)
};

enum class ESRResource : uint8
{
	Gold,
	Food
};

/** A price in both resources. */
USTRUCT()
struct FSRCost
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, Config, Category = "Cost", meta = (ClampMin = "0"))
	int32 Gold = 0;

	UPROPERTY(EditAnywhere, Config, Category = "Cost", meta = (ClampMin = "0"))
	int32 Food = 0;

	FSRCost() = default;
	FSRCost(int32 InGold, int32 InFood) : Gold(InGold), Food(InFood) {}
};

/**
 * One level of the castle (Sovereign Feel > Buildings > CastleLevels; index 0 is level 1). Raising the castle is how a
 * kingdom grows: more housing and a higher troop ceiling, more builders, a wider building zone, stronger walls and
 * bigger stores.
 */
USTRUCT()
struct FSRCastleLevel
{
	GENERATED_BODY()

	/** Price of raising the castle to this level (level 1: none). */
	UPROPERTY(EditAnywhere, Config, Category = "Castle")
	FSRCost UpgradeCost = FSRCost(0, 0);

	/** Seconds the raising takes (builders at the walls speed it up). */
	UPROPERTY(EditAnywhere, Config, Category = "Castle", meta = (ClampMin = "1"))
	float UpgradeTime = 40.f;

	/** Troops the castle itself houses. */
	UPROPERTY(EditAnywhere, Config, Category = "Castle", meta = (ClampMin = "0"))
	int32 Housing = 8;

	/** The most troops the kingdom may field, however many farms it builds. */
	UPROPERTY(EditAnywhere, Config, Category = "Castle", meta = (ClampMin = "1"))
	int32 PopulationCeiling = 36;

	/** Builders it may have. */
	UPROPERTY(EditAnywhere, Config, Category = "Castle", meta = (ClampMin = "0"))
	int32 Builders = 2;

	/** Radius (cm) of the building zone round it. */
	UPROPERTY(EditAnywhere, Config, Category = "Castle", meta = (ClampMin = "0"))
	float BuildZone = 4200.f;

	UPROPERTY(EditAnywhere, Config, Category = "Castle", meta = (ClampMin = "1"))
	float Health = 12000.f;

	/** The most gold / food the kingdom can hold; income beyond it is lost. */
	UPROPERTY(EditAnywhere, Config, Category = "Castle")
	FSRCost Storage = FSRCost(600, 600);

	/** Archers on the castle's corner pillars, each loosing at a foe in reach every Attack Interval. */
	UPROPERTY(EditAnywhere, Config, Category = "Castle", meta = (ClampMin = "0", ClampMax = "4"))
	int32 Archers = 1;

	/** Damage of each archer's arrow. */
	UPROPERTY(EditAnywhere, Config, Category = "Castle", meta = (ClampMin = "0"))
	float ArrowDamage = 36.f;
};

/** One level of a watchtower (Sovereign Feel > Buildings > TowerLevels; index 0 is level 1). */
USTRUCT()
struct FSRTowerLevel
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, Config, Category = "Tower") FSRCost UpgradeCost = FSRCost(0, 0);
	UPROPERTY(EditAnywhere, Config, Category = "Tower", meta = (ClampMin = "1")) float UpgradeTime = 30.f;
	UPROPERTY(EditAnywhere, Config, Category = "Tower", meta = (ClampMin = "0")) float Damage = 50.f;
	/** Seconds between shots. */
	UPROPERTY(EditAnywhere, Config, Category = "Tower", meta = (ClampMin = "0.1")) float Interval = 1.2f;
	UPROPERTY(EditAnywhere, Config, Category = "Tower", meta = (ClampMin = "0")) float Range = 2400.f;
	UPROPERTY(EditAnywhere, Config, Category = "Tower", meta = (ClampMin = "1")) float Health = 1800.f;
};

/** One level of a gold mine (Sovereign Feel > Buildings > MineLevels; index 0 is level 1). */
USTRUCT()
struct FSRMineLevel
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, Config, Category = "Mine") FSRCost UpgradeCost = FSRCost(0, 0);
	UPROPERTY(EditAnywhere, Config, Category = "Mine", meta = (ClampMin = "1")) float UpgradeTime = 30.f;
	/** Gold each delivery brings (deliveries come every MinePayoutInterval). */
	UPROPERTY(EditAnywhere, Config, Category = "Mine", meta = (ClampMin = "0")) int32 GoldPerPayout = 10;
	UPROPERTY(EditAnywhere, Config, Category = "Mine", meta = (ClampMin = "1")) float Health = 1250.f;
};

/** One level of a training building (barracks, archery range, stable, siege workshop): drill yards and better
 * instructors. Level 1 is how it is built. */
USTRUCT()
struct FSRTrainerLevel
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, Config, Category = "Trainer") FSRCost UpgradeCost = FSRCost(0, 0);
	UPROPERTY(EditAnywhere, Config, Category = "Trainer", meta = (ClampMin = "1")) float UpgradeTime = 30.f;
	/** How much faster troops are trained (1 = the troop's own training time, 2 = in half the time). */
	UPROPERTY(EditAnywhere, Config, Category = "Trainer", meta = (ClampMin = "0.1")) float TrainSpeed = 1.f;
	/** Its health, as a multiple of the building's own (Building Stats > Max Health). */
	UPROPERTY(EditAnywhere, Config, Category = "Trainer", meta = (ClampMin = "0.1")) float HealthScale = 1.f;
};

/** One level of a storehouse (the Granary holds food, the Treasury gold; Sovereign Feel > Buildings > Granary Levels /
 * Treasury Levels; index 0 is level 1). What it holds is added to the castle's own stores (FSRCastleLevel::Storage). */
USTRUCT()
struct FSRStoreLevel
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, Config, Category = "Store") FSRCost UpgradeCost = FSRCost(0, 0);
	UPROPERTY(EditAnywhere, Config, Category = "Store", meta = (ClampMin = "1")) float UpgradeTime = 30.f;
	/** How much of its resource it holds at this level. */
	UPROPERTY(EditAnywhere, Config, Category = "Store", meta = (ClampMin = "0")) int32 Capacity = 400;
	UPROPERTY(EditAnywhere, Config, Category = "Store", meta = (ClampMin = "1")) float Health = 900.f;
	/** The Citadel level needed before a storehouse can be raised to this level (0: none). */
	UPROPERTY(EditAnywhere, Config, Category = "Store", meta = (ClampMin = "0")) int32 RequiredCastleLevel = 0;
};

/** One level of a farm (index 0 is level 1): richer harvests and more room for troops. */
USTRUCT()
struct FSRFarmLevel
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, Config, Category = "Farm") FSRCost UpgradeCost = FSRCost(0, 0);
	UPROPERTY(EditAnywhere, Config, Category = "Farm", meta = (ClampMin = "1")) float UpgradeTime = 30.f;
	/** Food each harvest brings (harvests come every FarmPayoutInterval). */
	UPROPERTY(EditAnywhere, Config, Category = "Farm", meta = (ClampMin = "0")) int32 FoodPerPayout = 14;
	/** Troops it houses. */
	UPROPERTY(EditAnywhere, Config, Category = "Farm", meta = (ClampMin = "0")) int32 Housing = 4;
	UPROPERTY(EditAnywhere, Config, Category = "Farm", meta = (ClampMin = "1")) float Health = 1000.f;
};

UENUM()
enum class ESRUnitType : uint8
{
	Shieldbearer,
	Archer,
	Horseman,     // fast cavalry: a charge doubles its first blow
	Catapult,     // slow siege engine: long range, splash, wrecks buildings
	Builder,      // trained at the castle: raises buildings outside the castle's reach, repairs; does not fight
	Scout,        // trained at the castle (level 3, one at a time): very fast, sees far, hard to notice, weak in a fight
	Medic         // trained at the barracks, dear: heals its own side's troops round it; never fights
};

/** How many troop types there are (arrays indexed by ESRUnitType). */
constexpr int32 SRNumUnitTypes = 7;

/** Every troop type, in recruit-menu order. */
inline const TArray<ESRUnitType>& SRAllUnitTypes()
{
	static const TArray<ESRUnitType> Types = { ESRUnitType::Shieldbearer, ESRUnitType::Archer, ESRUnitType::Horseman, ESRUnitType::Catapult, ESRUnitType::Builder, ESRUnitType::Scout, ESRUnitType::Medic };
	return Types;
}

class UStaticMesh;

/**
 * Per-building-type tuning and shape. Edited in Project Settings > Game > Sovereign Feel > Buildings.
 * Footprint / sockets are in the building's local space (cm); its front (gate, adit, yard) faces local -X.
 * The values match the Blender models' exported metadata (SourceArt/Buildings/<type>.json).
 */
USTRUCT()
struct FSRBuildingStats
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, Config, Category = "Building")
	FString DisplayName = TEXT("Building");

	UPROPERTY(EditAnywhere, Config, Category = "Building", meta = (ClampMin = "1"))
	float MaxHealth = 600.f;

	/** Gold only: troops are bought with food, buildings with gold. */
	UPROPERTY(EditAnywhere, Config, Category = "Building")
	FSRCost Cost = FSRCost(100, 0);

	/** Seconds from laying the foundations to a working building. */
	UPROPERTY(EditAnywhere, Config, Category = "Building", meta = (ClampMin = "0.5"))
	float BuildTime = 12.f;

	/** Troops this building lets its kingdom field (the population cap is the sum over finished buildings). */
	UPROPERTY(EditAnywhere, Config, Category = "Building", meta = (ClampMin = "0"))
	int32 PopProvided = 0;

	/** The building zone round it (cm): new buildings inside it raise themselves; outside every zone a Builder must go
	 * and build them. Only the castle has one by default. 0 = none. */
	UPROPERTY(EditAnywhere, Config, Category = "Building", meta = (ClampMin = "0"))
	float TerritoryRadius = 0.f;

	/** The player can lay this down from the build menu. */
	UPROPERTY(EditAnywhere, Config, Category = "Building")
	bool bPlayerBuildable = true;

	/** Which tab of the build menu it sits in. */
	UPROPERTY(EditAnywhere, Config, Category = "Building")
	ESRBuildCategory Category = ESRBuildCategory::Economy;

	/** One line for the build menu's tooltip. */
	UPROPERTY(EditAnywhere, Config, Category = "Building")
	FString Blurb;

	/** It trains troops (of RecruitType). */
	UPROPERTY(EditAnywhere, Config, Category = "Building|Recruits")
	bool bRecruits = false;

	UPROPERTY(EditAnywhere, Config, Category = "Building|Recruits")
	ESRUnitType RecruitType = ESRUnitType::Shieldbearer;

	UPROPERTY(EditAnywhere, Config, Category = "Building|Shape")
	TSoftObjectPtr<UStaticMesh> Mesh;

	UPROPERTY(EditAnywhere, Config, Category = "Building|Shape")
	FVector2D FootprintMin = FVector2D(-400.f, -400.f);

	UPROPERTY(EditAnywhere, Config, Category = "Building|Shape")
	FVector2D FootprintMax = FVector2D(400.f, 400.f);

	UPROPERTY(EditAnywhere, Config, Category = "Building|Shape", meta = (ClampMin = "50"))
	float BlockHeight = 400.f;

	UPROPERTY(EditAnywhere, Config, Category = "Building|Shape")
	FVector GateOffset = FVector(-500.f, 0.f, 0.f);

	UPROPERTY(EditAnywhere, Config, Category = "Building|Shape")
	FVector LabelOffset = FVector(0.f, 0.f, 520.f);

	UPROPERTY(EditAnywhere, Config, Category = "Building|Shape")
	FVector PopupOffset = FVector(0.f, 0.f, 260.f);

	// ---- towers (and the castle's own archers on the walls) ----
	/** 0 = the building does not shoot. */
	UPROPERTY(EditAnywhere, Config, Category = "Building|Defence", meta = (ClampMin = "0"))
	float AttackRange = 0.f;

	UPROPERTY(EditAnywhere, Config, Category = "Building|Defence", meta = (ClampMin = "0"))
	float AttackDamage = 0.f;

	UPROPERTY(EditAnywhere, Config, Category = "Building|Defence", meta = (ClampMin = "0.1"))
	float AttackInterval = 1.6f;

	/** Height (cm) arrows leave from. */
	UPROPERTY(EditAnywhere, Config, Category = "Building|Defence", meta = (ClampMin = "0"))
	float MuzzleHeight = 700.f;

	/** Stones instead of arrows: each lands on the target's spot and hurts every foe within this radius (cm). 0 = arrows. */
	UPROPERTY(EditAnywhere, Config, Category = "Building|Defence", meta = (ClampMin = "0"))
	float SplashRadius = 0.f;

	/** It cannot hit what is closer than this (cm): a stone-thrower's arc. */
	UPROPERTY(EditAnywhere, Config, Category = "Building|Defence", meta = (ClampMin = "0"))
	float MinRange = 0.f;

	/** Height (cm) the second archer shoots from (a lower gallery); 0 = the same as Muzzle Height. */
	UPROPERTY(EditAnywhere, Config, Category = "Building|Defence", meta = (ClampMin = "0"))
	float SecondMuzzleHeight = 0.f;

	/** Archers on top: each loosing at a target in reach every Attack Interval. */
	UPROPERTY(EditAnywhere, Config, Category = "Building|Defence", meta = (ClampMin = "1", ClampMax = "4"))
	int32 Archers = 1;
};


/** What the unit has been told to do. Auto-acquired targets do not change the order. */
UENUM()
enum class ESROrder : uint8
{
	Idle,         // hold here, engage enemies that come into acquire range
	Move,         // go to destination, ignore enemies
	AttackMove,   // go to destination, engage enemies met on the way
	AttackTarget, // chase and attack one specific unit (or building)
	Hold,         // stand here; strike only what is in reach (Hold Ground stance, or the H key)
	Build,        // builders: walk to a building site (or a damaged building) and work on it
	Guard,        // keep close to a Builder or a building of our own; fight what comes near it, never chase far
	Roam,         // (the Scout) wander from place to place, unexplored ground first; struck, it runs home to the castle
	Heal          // (the Medic) keep beside one troop of our own, following it, and heal everyone in reach
};

enum class ESRAttackPhase : uint8
{
	Ready,
	Windup,    // telegraph; damage lands (or the arrow leaves) when this ends
	Recovery   // follow-through after the strike
};

/** Per-troop-type tuning. Edited in Project Settings > Game > Sovereign Feel. All distances in cm, times in seconds. */
USTRUCT()
struct FSRUnitStats
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, Config, Category = "Unit")
	FString DisplayName = TEXT("Unit");

	UPROPERTY(EditAnywhere, Config, Category = "Unit", meta = (ClampMin = "1"))
	float MaxHealth = 100.f;

	/** Body radius used for spacing, collision between units and click picking. */
	UPROPERTY(EditAnywhere, Config, Category = "Unit", meta = (ClampMin = "5"))
	float Radius = 42.f;

	/** Heavier units get shoved less when bodies overlap. */
	UPROPERTY(EditAnywhere, Config, Category = "Unit", meta = (ClampMin = "0.1"))
	float Mass = 1.f;

	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "0"))
	float MaxSpeed = 400.f;

	/** cm/s^2 when speeding up. Higher = snappier start. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "1"))
	float Acceleration = 2400.f;

	/** cm/s^2 when braking. Also shapes the arrival slow-down distance. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "1"))
	float Deceleration = 2800.f;

	/** Degrees per second at full turn rate (eases out for small corrections). */
	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "1"))
	float TurnRateDeg = 540.f;

	UPROPERTY(EditAnywhere, Config, Category = "Combat")
	bool bRanged = false;

	/** Reach measured edge-to-edge (beyond both body radii). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0"))
	float AttackRange = 35.f;

	/** Idle / attack-moving units engage enemies inside this centre-to-centre distance. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0"))
	float AcquireRange = 750.f;

	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0"))
	float Damage = 12.f;

	/** Minimum seconds between strikes. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0.05"))
	float AttackInterval = 1.2f;

	/** Telegraph before the strike frame. Damage / arrow release happens when it ends. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0.01"))
	float WindupTime = 0.28f;

	/** Follow-through after the strike. A new move order cancels it immediately. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0.01"))
	float RecoveryTime = 0.32f;

	/** Speed (cm/s) of the shove this unit's hits give the victim. Decays within ~0.1s. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0"))
	float KnockbackImpulse = 160.f;

	/** Heavy hits trigger local hit-stop and camera micro-shake (if enabled). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat")
	bool bHeavyHits = false;

	/** Ranged only: between shots, back away from melee enemies closer than this (0 = stand and shoot). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Ranged", meta = (ClampMin = "0"))
	float KeepDistance = 0.f;

	UPROPERTY(EditAnywhere, Config, Category = "Combat|Ranged", meta = (ClampMin = "100"))
	float ProjectileSpeed = 1900.f;

	/** Damage against buildings is Damage x this (arrows barely scratch stone; blades and torches do better). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0"))
	float BuildingDamageScale = 1.f;

	/** Population this troop takes up (see the buildings' PopProvided). */
	UPROPERTY(EditAnywhere, Config, Category = "Unit", meta = (ClampMin = "0"))
	int32 PopCost = 1;

	/** Arc apex height as a fraction of the shot distance. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Ranged", meta = (ClampMin = "0"))
	float ProjectileArc = 0.16f;

	/** Ranged: the shot hurts every foe within this radius (cm) of where it lands, less toward the edge (0 = none). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Ranged", meta = (ClampMin = "0"))
	float SplashRadius = 0.f;

	/** Ranged: cannot shoot at anything closer than this (cm). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Ranged", meta = (ClampMin = "0"))
	float MinRange = 0.f;

	/** Throws stones (the catapult) rather than arrows. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Ranged")
	bool bStoneProjectile = false;

	/** Goes for buildings before troops when both are in sight (siege). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat")
	bool bPrefersBuildings = false;

	/** Melee: the first blow after ChargeRestTime without striking does this x damage (cavalry charge). */
	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "1"))
	float ChargeMultiplier = 1.f;

	UPROPERTY(EditAnywhere, Config, Category = "Combat", meta = (ClampMin = "0"))
	float ChargeRestTime = 4.f;

	/** A builder: raises and repairs its kingdom's buildings, never picks a fight on its own. */
	UPROPERTY(EditAnywhere, Config, Category = "Unit")
	bool bBuilder = false;

	/** How far it sees (fog of war, cm). 0 = its AcquireRange. */
	UPROPERTY(EditAnywhere, Config, Category = "Unit", meta = (ClampMin = "0"))
	float SightRange = 0.f;

	/** May walk into deep water (none do yet). Everyone else meets it as a hard wall, even when shoved. */
	UPROPERTY(EditAnywhere, Config, Category = "Movement")
	bool bWaterWalker = false;

	/** How well it hides: enemies (troops, towers, the enemy's fog of war and its commander) only notice it within this
	 * fraction of the distance they would notice anyone else. 1 = seen like everyone; the Scout is well under 1. */
	UPROPERTY(EditAnywhere, Config, Category = "Unit", meta = (ClampMin = "0.05", ClampMax = "1"))
	float NoticeScale = 1.f;

	/** Ground (cm) one run cycle of its sprite covers. 0 = Animation > Walk Cycle Distance (a sprinter's stride is longer). */
	UPROPERTY(EditAnywhere, Config, Category = "Movement", meta = (ClampMin = "0"))
	float WalkCycleDistance = 0.f;

	float Sight() const { return SightRange > 0.f ? SightRange : AcquireRange; }
};
