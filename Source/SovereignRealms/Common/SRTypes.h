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
	Workshop      // builds Catapults
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
	Aggressive,   // chase anything in acquire range, as far as it takes
	Defensive,    // engage what comes close, give up a short chase and return to position
	HoldGround    // never move to fight; strike / shoot only what is in reach
};

/** The shape a group takes when it is ordered to move. */
UENUM(BlueprintType)
enum class ESRFormationShape : uint8
{
	Line,     // wide ranks, melee in front: the default battle line
	Column,   // narrow and deep: for roads, gaps and long marches
	Wedge,    // a point leading: for breaking a line
	Square    // a compact block, ranged in the middle: for holding ground
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

UENUM()
enum class ESRUnitType : uint8
{
	Shieldbearer,
	Archer,
	Horseman,     // fast cavalry: a charge doubles its first blow
	Catapult,     // slow siege engine: long range, splash, wrecks buildings
	Builder       // trained at the castle: raises buildings outside the castle's reach, repairs; does not fight
};

/** Every troop type, in recruit-menu order. */
inline const TArray<ESRUnitType>& SRAllUnitTypes()
{
	static const TArray<ESRUnitType> Types = { ESRUnitType::Shieldbearer, ESRUnitType::Archer, ESRUnitType::Horseman, ESRUnitType::Catapult, ESRUnitType::Builder };
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
	Build         // builders: walk to a building site (or a damaged building) and work on it
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

	float Sight() const { return SightRange > 0.f ? SightRange : AcquireRange; }
};
