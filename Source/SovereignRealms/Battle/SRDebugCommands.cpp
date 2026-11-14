// Copyright Sovereign Realms.
//
// Console commands for exercising the slice without a mouse (automated checks, quick tuning).
// Type them in the PIE console (~), or write them one per line to <Project>/Saved/SRCommands.txt
// and the running game executes them (see USRBattleSubsystem::PollCommandInbox).

#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Player/SRPlayerController.h"
#include "Player/SRCameraPawn.h"
#include "Units/SRUnit.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "UnrealClient.h"
#include "InputKeyEventArgs.h"
#include "TimerManager.h"
#include "Misc/Paths.h"

namespace
{
	ASRPlayerController* GetSRController(UWorld* World)
	{
		return World ? Cast<ASRPlayerController>(World->GetFirstPlayerController()) : nullptr;
	}

	bool ParseXY(const TArray<FString>& Args, FVector2D& Out)
	{
		if (Args.Num() < 2) { return false; }
		Out = FVector2D(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]));
		return true;
	}

	FVector GroundAt(UWorld* World, const FVector2D& XY)
	{
		float Z = 0.f;
		if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World)) { Battle->SampleGround(XY, 20000.f, Z); }
		return FVector(XY.X, XY.Y, Z);
	}

	ASRUnit* NearestOfTeam(UWorld* World, ESRTeam Team, const FVector2D& To)
	{
		ASRUnit* Best = nullptr;
		float BestDist = TNumericLimits<float>::Max();
		if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World))
		{
			for (ASRUnit* Unit : Battle->GetUnits())
			{
				if (!Unit || !Unit->IsActive() || Unit->GetTeam() != Team) { continue; }
				const float Dist = FVector2D::DistSquared(Unit->GetPos2D(), To);
				if (Dist < BestDist) { BestDist = Dist; Best = Unit; }
			}
		}
		return Best;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdSelectAll(TEXT("sr.SelectAll"), TEXT("Select every player unit."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (ASRPlayerController* PC = GetSRController(World))
			{
				PC->SelectAllPlayerUnits();
				UE_LOG(LogSovereign, Log, TEXT("sr.SelectAll: %d selected"), PC->GetSelection().Num());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSelectType(TEXT("sr.SelectType"), TEXT("sr.SelectType <0=Shieldbearer|1=Archer>: select all player units of a type."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!PC || !Battle || Args.Num() < 1) { return; }
			const ESRUnitType Type = FCString::Atoi(*Args[0]) == 1 ? ESRUnitType::Archer : ESRUnitType::Shieldbearer;
			TArray<ASRUnit*> Units;
			for (ASRUnit* Unit : Battle->GetUnits())
			{
				if (Unit && Unit->IsActive() && Unit->GetTeam() == ESRTeam::Player && Unit->GetUnitType() == Type) { Units.Add(Unit); }
			}
			PC->SelectUnits(Units, false);
			UE_LOG(LogSovereign, Log, TEXT("sr.SelectType: %d selected"), PC->GetSelection().Num());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOrderMove(TEXT("sr.OrderMove"), TEXT("sr.OrderMove X Y: move the selection (formation) to a world position."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			if (PC && ParseXY(Args, XY)) { PC->IssueMove(GroundAt(World, XY), false); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOrderAttackMove(TEXT("sr.OrderAttackMove"), TEXT("sr.OrderAttackMove X Y: attack-move the selection to a world position."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			if (PC && ParseXY(Args, XY)) { PC->IssueMove(GroundAt(World, XY), true); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOrderAttackNearest(TEXT("sr.OrderAttackNearest"), TEXT("Selection attacks the enemy nearest to the selection (like right-clicking it)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!PC || !Battle) { return; }
			if (ASRUnit* Target = NearestOfTeam(World, ESRTeam::Enemy, Battle->TeamCentroid(ESRTeam::Player)))
			{
				UE_LOG(LogSovereign, Log, TEXT("sr.OrderAttackNearest: target %s"), *Target->GetLabel());
				PC->IssueAttack(Target);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOrderStop(TEXT("sr.OrderStop"), TEXT("Selection stops."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (ASRPlayerController* PC = GetSRController(World)) { PC->IssueStop(); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdReset(TEXT("sr.ResetBattle"), TEXT("Respawn the scenario."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (ASRPlayerController* PC = GetSRController(World)) { PC->ClearSelection(); }
			if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World)) { Battle->ResetBattle(); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAutoBattle(TEXT("sr.AutoBattle"), TEXT("sr.AutoBattle [0|1]: both sides attack-move at each other and fight to the end."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World))
			{
				Battle->SetAutoBattle(Args.Num() == 0 || FCString::Atoi(*Args[0]) != 0);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdStatus(TEXT("sr.Status"), TEXT("Log every unit's position, health, order and target."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World)) { Battle->LogStatus(); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdCamera(TEXT("sr.Camera"), TEXT("sr.Camera X Y [Zoom01]: snap the game camera to a world position (0 = zoomed in, 1 = zoomed out)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			const ASRPlayerController* PC = GetSRController(World);
			ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr;
			if (Camera && ParseXY(Args, XY))
			{
				if (Args.Num() >= 3) { Camera->SetZoom(FCString::Atof(*Args[2]), true); }
				Camera->FocusOn(XY, true);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdTrauma(TEXT("sr.Shake"), TEXT("sr.Shake [amount 0..1]: add camera trauma to preview the shake."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const ASRPlayerController* PC = GetSRController(World);
			if (ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
			{
				Camera->AddTrauma(Args.Num() > 0 ? FCString::Atof(*Args[0]) : 0.5f);
			}
		}));

	// --- scripted input: drives the real Enhanced Input bindings, for automated end-to-end checks ---

	FAutoConsoleCommandWithWorldAndArgs CmdCursor(TEXT("sr.Cursor"), TEXT("sr.Cursor X Y | off: pretend the mouse is at a viewport position (0..1, 0..1). 'off' returns to the real mouse."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			if (ASRPlayerController* PC = GetSRController(World))
			{
				PC->SetCursorOverride(ParseXY(Args, XY), XY);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdCursorWorld(TEXT("sr.CursorWorld"), TEXT("sr.CursorWorld X Y [Z]: pretend the mouse is over a world position."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY, Screen;
			int32 SizeX = 0, SizeY = 0;
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || !ParseXY(Args, XY)) { return; }
			FVector Point = GroundAt(World, XY);
			if (Args.Num() >= 3) { Point.Z += FCString::Atof(*Args[2]); }
			PC->GetViewportSize(SizeX, SizeY);
			if (SizeX > 0 && PC->ProjectWorldLocationToScreen(Point, Screen))
			{
				PC->SetCursorOverride(true, FVector2D(Screen.X / SizeX, Screen.Y / SizeY));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdKey(TEXT("sr.Key"), TEXT("sr.Key <KeyName> <down|up|tap>: inject a key / mouse-button event (e.g. LeftMouseButton, A, LeftShift, SpaceBar)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || Args.Num() < 2) { return; }
			const FKey Key(*Args[0]);
			if (!Key.IsValid())
			{
				UE_LOG(LogSovereign, Warning, TEXT("sr.Key: unknown key '%s'"), *Args[0]);
				return;
			}
			if (Args[1].Equals(TEXT("tap"), ESearchCase::IgnoreCase))
			{
				// Press now, release on the next frame: a real quick tap.
				PC->InputKey(FInputKeyEventArgs::CreateSimulated(Key, IE_Pressed, 1.f));
				World->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(PC, [PC, Key]()
				{
					PC->InputKey(FInputKeyEventArgs::CreateSimulated(Key, IE_Released, 0.f));
				}));
				return;
			}
			const bool bDown = Args[1].Equals(TEXT("down"), ESearchCase::IgnoreCase);
			PC->InputKey(FInputKeyEventArgs::CreateSimulated(Key, bDown ? IE_Pressed : IE_Released, bDown ? 1.f : 0.f));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdZoom(TEXT("sr.Zoom"), TEXT("sr.Zoom <notches>: zoom as if the wheel was turned (positive = in)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const ASRPlayerController* PC = GetSRController(World);
			if (ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
			{
				Camera->AddZoomInput(Args.Num() > 0 ? FCString::Atof(*Args[0]) : 1.f, nullptr);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdShotOn(TEXT("sr.ShotOn"),
		TEXT("sr.ShotOn <strike|hit|death> <name> [type 0=Shieldbearer 1=Archer -1=any] [team 0=player 1=enemy -1=any]: the next time it happens, freeze the battle on that frame, centre the camera on the unit and save Saved/Screenshots/SR/<name>.png."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!Battle || Args.Num() < 2) { return; }
			const ESRShotEvent Event = Args[0].Equals(TEXT("strike"), ESearchCase::IgnoreCase) ? ESRShotEvent::Strike
				: Args[0].Equals(TEXT("hit"), ESearchCase::IgnoreCase) ? ESRShotEvent::Hit
				: Args[0].Equals(TEXT("death"), ESearchCase::IgnoreCase) ? ESRShotEvent::Death : ESRShotEvent::None;
			Battle->ArmShot(Event, Args[1], Args.Num() > 2 ? FCString::Atoi(*Args[2]) : -1, Args.Num() > 3 ? FCString::Atoi(*Args[3]) : -1);
			UE_LOG(LogSovereign, Log, TEXT("sr.ShotOn armed: %s -> %s"), *Args[0], *Args[1]);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdFan(TEXT("sr.Fan"), TEXT("sr.Fan [distance]: every player unit runs outward in its own direction (unit i heads i * 45 degrees), to check all eight sprite facings at once."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!Battle) { return; }
			const float Distance = Args.Num() > 0 ? FCString::Atof(*Args[0]) : 700.f;
			int32 Index = 0;
			for (ASRUnit* Unit : Battle->GetUnits())
			{
				if (!Unit || !Unit->IsActive() || Unit->GetTeam() != ESRTeam::Player) { continue; }
				const float Yaw = FMath::DegreesToRadians(45.f * Index++);
				Unit->OrderMove(Unit->GetPos2D() + FVector2D(FMath::Cos(Yaw), FMath::Sin(Yaw)) * Distance);
			}
			UE_LOG(LogSovereign, Log, TEXT("sr.Fan: %d units"), Index);
		}));

	// --- kingdoms: economy, recruitment, rally point ---

	FAutoConsoleCommandWithWorldAndArgs CmdGive(TEXT("sr.Give"), TEXT("sr.Give <gold|food> <amount>: add to (or with a negative amount take from) the player's stock."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USREconomySubsystem* Economy = USREconomySubsystem::Get(World);
			if (!Economy || Args.Num() < 2) { return; }
			const ESRResource Resource = Args[0].StartsWith(TEXT("f"), ESearchCase::IgnoreCase) ? ESRResource::Food : ESRResource::Gold;
			Economy->AddResource(ESRTeam::Player, Resource, FCString::Atoi(*Args[1]));
			UE_LOG(LogSovereign, Log, TEXT("sr.Give: player gold=%d food=%d"), Economy->GetResource(ESRTeam::Player, ESRResource::Gold), Economy->GetResource(ESRTeam::Player, ESRResource::Food));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRecruit(TEXT("sr.Recruit"), TEXT("sr.Recruit <shield|archer>: queue a recruit at the player's castle (pays the cost; refused if it cannot be afforded)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || Args.Num() < 1) { return; }
			const ESRUnitType Type = Args[0].StartsWith(TEXT("a"), ESearchCase::IgnoreCase) ? ESRUnitType::Archer : ESRUnitType::Shieldbearer;
			const bool bOk = PC->RecruitAtCastle(Type);
			UE_LOG(LogSovereign, Log, TEXT("sr.Recruit %s: %s"), *Args[0], bOk ? TEXT("queued") : TEXT("REFUSED"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSelectCastle(TEXT("sr.SelectCastle"), TEXT("sr.SelectCastle [farm|mine|enemy|none]: select the player's castle (or another building; none deselects)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			const USREconomySubsystem* Economy = USREconomySubsystem::Get(World);
			if (!PC || !Economy) { return; }
			const FString What = Args.Num() > 0 ? Args[0].ToLower() : TEXT("castle");
			ASRBuilding* Building = nullptr;
			if (What == TEXT("farm")) { Building = Economy->FindBuilding(ESRBuildingType::Farm, ESRTeam::Player); }
			else if (What == TEXT("mine")) { Building = Economy->FindBuilding(ESRBuildingType::Mine, ESRTeam::Player); }
			else if (What == TEXT("enemy")) { Building = Economy->FindBuilding(ESRBuildingType::Castle, ESRTeam::Enemy); }
			else if (What != TEXT("none")) { Building = Economy->FindBuilding(ESRBuildingType::Castle, ESRTeam::Player); }
			PC->SelectBuilding(Building);
			UE_LOG(LogSovereign, Log, TEXT("sr.SelectCastle: %s"), Building ? *Building->GetActorNameOrLabel() : TEXT("none"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRally(TEXT("sr.Rally"), TEXT("sr.Rally X Y: set the player castle's rally point."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			if (PC && ParseXY(Args, XY)) { PC->SetCastleRally(GroundAt(World, XY)); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdEconomy(TEXT("sr.Economy"), TEXT("Log both teams' gold and food, income, and every building's timers, queue and rally point."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (const USREconomySubsystem* Economy = USREconomySubsystem::Get(World)) { Economy->LogStatus(); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdShot(TEXT("sr.Shot"), TEXT("sr.Shot <name>: save a screenshot of the game view (with HUD) to Saved/Screenshots/SR/<name>.png."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld*)
		{
			const FString Name = Args.Num() > 0 ? Args[0] : TEXT("shot");
			const FString Path = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots/SR") / (Name + TEXT(".png")));
			FScreenshotRequest::RequestScreenshot(Path, true, false);
			UE_LOG(LogSovereign, Log, TEXT("sr.Shot -> %s"), *Path);
		}));
}
