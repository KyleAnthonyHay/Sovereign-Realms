// The Builder (Tools/blender/assets/troop_builder.py, /Game/Voxel/Troops/Builder/DA_Builder): an AVLTroop of kind
// "Builder". It walks, runs, jumps, is selected, ordered and taken over like any troop; played by hand, a left click
// swings its hammer (the sword's swings: AVLKing::Attack). It is no fighter: VLRules::Troop("Builder") has no acquire
// range, UVLCommand::CanAttack refuses it and the enemy commander counts it as nothing. Trained at the castle
// (UVLBattle::Train(Castle, 1, .., "Builder")); what it builds and repairs, and how: VLConstruction.* (UVLBuilderWork).
#include "VoxelLab.h"
#include "VLBattle.h"
#include "VLGrid.h"
#include "VLTroop.h"
#include "HAL/IConsoleManager.h"

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdSpawnUnit(TEXT("vl.SpawnUnit"),
		TEXT("vl.SpawnUnit <Builder|Swordsman|Archer|...> [count] [enemy]: units of that kind in front of the castle (the player's, or the enemy's), without training"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			if (!Battle || Args.Num() < 1)
			{
				return;
			}
			const int32 Team = Args.Contains(TEXT("enemy")) ? UVLBattle::Enemy : UVLBattle::Player;
			const int32 Count = FMath::Clamp(Args.Num() > 1 && Args[1].IsNumeric() ? FCString::Atoi(*Args[1]) : 1, 1, 40);
			const AActor* Castle = Battle->GetCastle(Team);
			if (!Castle)
			{
				UE_LOG(LogVoxelLab, Warning, TEXT("vl.SpawnUnit: team %d has no castle on this map"), Team);
				return;
			}
			FVector Door, Rally, Front;
			Battle->FrontOf(Castle, Door, Rally, Front);
			const FVector Side(-Front.Y, Front.X, 0.f);
			UVLGrid* Grid = UVLGrid::Get(World);
			const bool bGrid = Grid && Grid->EnsureBuilt();
			int32 Made = 0;
			for (int32 i = 0; i < Count; ++i)
			{
				// rows of five across the front of the castle, a little short of its rally point
				FVector P = Rally - Front * 150.f + Side * (((i % 5) - 2) * 140.f) + Front * ((i / 5) * 140.f);
				if (bGrid)
				{
					const int32 Node = Grid->NearestNode(FVector(P.X, P.Y, P.Z + 300.f), 30, Grid->MainRegion());
					if (Node != INDEX_NONE)
					{
						P = Grid->NodePos(Node);
					}
				}
				if (const AVLTroop* T = Battle->SpawnTroop(Args[0], Team, P, Front.Rotation().Yaw))
				{
					++Made;
					UE_LOG(LogVoxelLab, Log, TEXT("vl.SpawnUnit: %s at %.0f %.0f %.0f"), *T->GetDisplayName(), P.X, P.Y, P.Z);
				}
			}
			UE_LOG(LogVoxelLab, Log, TEXT("vl.SpawnUnit %s: %d of %d spawned for team %d"), *Args[0], Made, Count, Team);
		}));
}
