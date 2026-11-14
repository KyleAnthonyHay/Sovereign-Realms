// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "SRTypes.generated.h"

UENUM()
enum class ESRTeam : uint8
{
	Player,
	Enemy
};

UENUM()
enum class ESRUnitType : uint8
{
	Shieldbearer,
	Archer
};

/** What the unit has been told to do. Auto-acquired targets do not change the order. */
UENUM()
enum class ESROrder : uint8
{
	Idle,         // hold here, engage enemies that come into acquire range
	Move,         // go to destination, ignore enemies
	AttackMove,   // go to destination, engage enemies met on the way
	AttackTarget  // chase and attack one specific unit
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

	/** Arc apex height as a fraction of the shot distance. */
	UPROPERTY(EditAnywhere, Config, Category = "Combat|Ranged", meta = (ClampMin = "0"))
	float ProjectileArc = 0.16f;
};
