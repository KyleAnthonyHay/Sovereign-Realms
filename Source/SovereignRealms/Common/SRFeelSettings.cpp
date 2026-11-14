// Copyright Sovereign Realms.

#include "Common/SRFeelSettings.h"

USRFeelSettings::USRFeelSettings()
{
	// Shieldbearer: sturdy front-liner. Slower, hits land with weight.
	Shieldbearer.DisplayName = TEXT("Shieldbearer");
	Shieldbearer.MaxHealth = 130.f;
	Shieldbearer.Radius = 44.f;
	Shieldbearer.Mass = 1.6f;
	Shieldbearer.MaxSpeed = 390.f;
	Shieldbearer.Acceleration = 2400.f;
	Shieldbearer.Deceleration = 3000.f;
	Shieldbearer.TurnRateDeg = 520.f;
	Shieldbearer.bRanged = false;
	Shieldbearer.AttackRange = 34.f;
	Shieldbearer.AcquireRange = 760.f;
	Shieldbearer.Damage = 14.f;
	Shieldbearer.AttackInterval = 1.15f;
	Shieldbearer.WindupTime = 0.26f;
	Shieldbearer.RecoveryTime = 0.34f;
	Shieldbearer.KnockbackImpulse = 190.f;
	Shieldbearer.bHeavyHits = true;

	// Archer: fragile, quick on its feet, long reach.
	Archer.DisplayName = TEXT("Archer");
	Archer.MaxHealth = 60.f;
	Archer.Radius = 36.f;
	Archer.Mass = 0.8f;
	Archer.MaxSpeed = 440.f;
	Archer.Acceleration = 2800.f;
	Archer.Deceleration = 3200.f;
	Archer.TurnRateDeg = 640.f;
	Archer.bRanged = true;
	Archer.AttackRange = 880.f;
	Archer.AcquireRange = 1050.f;
	Archer.Damage = 9.f;
	Archer.AttackInterval = 1.5f;
	Archer.WindupTime = 0.42f;
	Archer.RecoveryTime = 0.24f;
	Archer.KnockbackImpulse = 90.f;
	Archer.bHeavyHits = false;
	Archer.KeepDistance = 230.f;
	Archer.ProjectileSpeed = 1900.f;
	Archer.ProjectileArc = 0.16f;
}
