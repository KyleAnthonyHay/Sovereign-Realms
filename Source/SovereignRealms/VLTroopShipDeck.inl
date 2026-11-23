// Written by Tools/blender/assets/troopship.py from the model's own plan: do not edit by hand.
// Where units stand on SM_TroopShip (cm, the ship's own space: +X the bow, Z up from the waterline), the entry
// ports in its bulwark and the hull's size.
#pragma once
namespace VLTroopShipDeck
{
	// the main deck, aft of the mast: soldiers
	static const FVector Main[] = { FVector(-70.0f, -0.0f, 150.0f), FVector(-70.0f, -100.0f, 150.0f), FVector(-70.0f, 100.0f, 150.0f), FVector(-70.0f, -200.0f, 150.0f), FVector(-70.0f, 200.0f, 150.0f), FVector(-190.0f, -0.0f, 150.0f), FVector(-190.0f, -100.0f, 150.0f), FVector(-190.0f, 100.0f, 150.0f), FVector(-190.0f, -200.0f, 150.0f), FVector(-190.0f, 200.0f, 150.0f), FVector(-310.0f, -0.0f, 150.0f), FVector(-310.0f, -100.0f, 150.0f), FVector(-310.0f, 100.0f, 150.0f), FVector(-310.0f, -200.0f, 150.0f), FVector(-310.0f, 200.0f, 150.0f), FVector(-430.0f, -0.0f, 150.0f), FVector(-430.0f, -100.0f, 150.0f), FVector(-430.0f, 100.0f, 150.0f), FVector(-430.0f, -200.0f, 150.0f), FVector(-430.0f, 200.0f, 150.0f) };
	// the forecastle: archers first
	static const FVector Fore[] = { FVector(795.0f, -105.0f, 312.5f), FVector(795.0f, 105.0f, 312.5f), FVector(910.0f, -65.0f, 312.5f), FVector(910.0f, 65.0f, 312.5f) };
	// the stern castle: the heroes
	static const FVector Stern[] = { FVector(-730.0f, -90.0f, 375.0f), FVector(-730.0f, 90.0f, 375.0f), FVector(-860.0f, -190.0f, 375.0f), FVector(-860.0f, 190.0f, 375.0f) };
	// the entry ports: one each side, at +-GateY (the bulwark's line), their sill on the main deck
	static constexpr float GateX = -187.5f, GateY = 300.0f, GateZ = 150.0f, GateWidth = 162.5f;
	// the hull: from StemX to SternX along it, HalfBeam each side (over the shields), Draught under the water,
	// RailZ the bulwark's top, MastZ the masthead
	static constexpr float SternX = -1150.0f, StemX = 1312.5f, HalfBeam = 343.8f, Draught = 112.5f, RailZ = 237.5f, MastZ = 1737.5f;
	static constexpr float PlankLength = 400.0f;      // SM_TroopShip_Gangplank, from its pivot along +X
}
