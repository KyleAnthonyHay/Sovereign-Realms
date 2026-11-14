// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"

class ASRUnit;

namespace SRFormation
{
	/**
	 * Destination slot for every unit in a group move, in the same order as Units.
	 *
	 * The group forms ranks facing its direction of travel: melee in front, ranged behind,
	 * wider than deep. Slots are handed out so units keep their relative arrangement
	 * (whoever is on the left stays on the left, whoever is in front stays in front),
	 * which keeps paths from crossing.
	 */
	void ComputeSlots(const TArray<ASRUnit*>& Units, const FVector2D& Destination, TArray<FVector2D>& OutSlots);
}
