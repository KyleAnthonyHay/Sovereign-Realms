// Copyright Sovereign Realms.
//
// Console commands for exercising the slice without a mouse (automated checks, quick tuning).
// Type them in the PIE console (~), or write them one per line to <Project>/Saved/SRCommands.txt
// and the running game executes them (see USRBattleSubsystem::PollCommandInbox).

#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRAISubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Battle/SRPlatoonSubsystem.h"
#include "Battle/SRGameFlowSubsystem.h"
#include "Kismet/GameplayStatics.h"
#include "Containers/Ticker.h"
#include "RenderCore.h"
#include "RHI.h"
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
#include "Engine/GameViewportClient.h"
#include "Widgets/SWindow.h"

namespace
{
	ASRPlayerController* GetSRController(UWorld* World)
	{
		return World ? Cast<ASRPlayerController>(World->GetFirstPlayerController()) : nullptr;
	}

	ESRBuildingType ParseBuildingType(const FString& Name)
	{
		const FString N = Name.ToLower();
		if (N == TEXT("mine")) { return ESRBuildingType::Mine; }
		if (N == TEXT("tower")) { return ESRBuildingType::Tower; }
		if (N == TEXT("barracks")) { return ESRBuildingType::Barracks; }
		if (N == TEXT("range")) { return ESRBuildingType::Range; }
		if (N == TEXT("castle")) { return ESRBuildingType::Castle; }
		return ESRBuildingType::Farm;
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

	FAutoConsoleCommandWithWorldAndArgs CmdRecruit(TEXT("sr.Recruit"), TEXT("sr.Recruit <shield|archer>: queue a recruit at the player's barracks / range (pays the cost; refused if it cannot be afforded)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || Args.Num() < 1) { return; }
			const ESRUnitType Type = Args[0].StartsWith(TEXT("a"), ESearchCase::IgnoreCase) ? ESRUnitType::Archer : ESRUnitType::Shieldbearer;
			const bool bOk = PC->RecruitTroop(Type);
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
			else if (What == TEXT("barracks")) { Building = Economy->FindBuilding(ESRBuildingType::Barracks, ESRTeam::Player); }
			else if (What == TEXT("range")) { Building = Economy->FindBuilding(ESRBuildingType::Range, ESRTeam::Player); }
			else if (What == TEXT("tower")) { Building = Economy->FindBuilding(ESRBuildingType::Tower, ESRTeam::Player); }
			else if (What != TEXT("none")) { Building = Economy->FindBuilding(ESRBuildingType::Castle, ESRTeam::Player); }
			PC->SelectBuilding(Building);
			UE_LOG(LogSovereign, Log, TEXT("sr.SelectCastle: %s"), Building ? *Building->GetActorNameOrLabel() : TEXT("none"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRally(TEXT("sr.Rally"), TEXT("sr.Rally X Y: set the player castle's rally point."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			if (PC && ParseXY(Args, XY)) { PC->SetRallyFor(GroundAt(World, XY)); }
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

	FAutoConsoleCommandWithWorldAndArgs CmdAIvsAI(TEXT("sr.AIvsAI"), TEXT("sr.AIvsAI [0|1]: a commander plays the player's side too (balance testing)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRAISubsystem* AI = USRAISubsystem::Get(World)) { AI->SetPlayerAI(Args.Num() == 0 || Args[0] != TEXT("0")); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAIStatus(TEXT("sr.AIStatus"), TEXT("Log each commander's economy, army and wave state."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (const USRAISubsystem* AI = USRAISubsystem::Get(World)) { AI->LogStatus(); }
			if (const USRBattleSubsystem* B = USRBattleSubsystem::Get(World))
			{
				UE_LOG(LogSovereign, Log, TEXT("MATCH t=%.0fs troops player=%d enemy=%d result=%d"), B->GetBattleClock(), B->CountAlive(ESRTeam::Player), B->CountAlive(ESRTeam::Enemy), int32(B->GetResult()));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpeed(TEXT("sr.Speed"), TEXT("sr.Speed <x>: run the game x times faster (balance testing; 1 = normal)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const float X = Args.Num() > 0 ? FMath::Clamp(FCString::Atof(*Args[0]), 0.1f, 16.f) : 1.f;
			UGameplayStatics::SetGlobalTimeDilation(World, X);
			UE_LOG(LogSovereign, Log, TEXT("sr.Speed %.1f"), X);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdBuild(TEXT("sr.Build"), TEXT("sr.Build <farm|mine|tower|barracks|range> X Y [enemy]: lay a building (pays gold; refused like the player would be)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USREconomySubsystem* Eco = USREconomySubsystem::Get(World);
			FVector2D XY;
			if (!Eco || Args.Num() < 3) { return; }
			TArray<FString> Rest(Args.GetData() + 1, 2);
			if (!ParseXY(Rest, XY)) { return; }
			const ESRBuildingType Type = ParseBuildingType(Args[0]);
			const ESRTeam Team = Args.Num() > 3 && Args[3] == TEXT("enemy") ? ESRTeam::Enemy : ESRTeam::Player;
			FText Why;
			ASRBuilding* B = Eco->PlaceBuilding(Type, Team, XY, &Why);
			UE_LOG(LogSovereign, Log, TEXT("sr.Build %s at (%.0f, %.0f): %s"), *Args[0], XY.X, XY.Y, B ? TEXT("placed") : *Why.ToString());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPlace(TEXT("sr.Place"), TEXT("sr.Place <farm|mine|tower|barracks|range|off>: enter placement mode as if the build hotkey was pressed."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || Args.Num() == 0) { return; }
			if (Args[0] == TEXT("off")) { PC->CancelPlacement(); return; }
			PC->BeginPlacement(ParseBuildingType(Args[0]));
		}));

	// ---- game flow: the menus, for scripted tests ----
	FAutoConsoleCommandWithWorldAndArgs CmdStartMatch(TEXT("sr.StartMatch"), TEXT("sr.StartMatch [0=easy|1=normal|2=hard]: start a match now, skipping the menus (keeps the difficulty if none is given)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World)) { Flow->StartMatch(Args.Num() > 0 ? FCString::Atoi(*Args[0]) : -1); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMenu(TEXT("sr.Menu"), TEXT("sr.Menu <main|play>: go to the main menu, or start a match."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World);
			if (!Flow) { return; }
			if (Args.Num() > 0 && Args[0].Equals(TEXT("play"), ESearchCase::IgnoreCase)) { Flow->StartMatch(); }
			else { Flow->EnterMainMenu(); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPause(TEXT("sr.Pause"), TEXT("sr.Pause [0|1]: pause (pause menu) or resume the match."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World)) { Flow->SetPaused(Args.Num() == 0 || Args[0] != TEXT("0")); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdKillCastle(TEXT("sr.KillCastle"), TEXT("sr.KillCastle <enemy|player>: bring a castle down (ends the match: victory / defeat screen)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const USREconomySubsystem* Economy = USREconomySubsystem::Get(World);
			const bool bPlayer = Args.Num() > 0 && Args[0].Equals(TEXT("player"), ESearchCase::IgnoreCase);
			if (ASRBuilding* Castle = Economy ? Economy->GetCastle(bPlayer ? ESRTeam::Player : ESRTeam::Enemy) : nullptr) { Castle->ReceiveDamage(1.0e9f, nullptr); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdDamage(TEXT("sr.Damage"), TEXT("sr.Damage <castle|farm|mine|tower|barracks|range> <health fraction left> [enemy]: hurt a building (0 destroys it)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const USREconomySubsystem* Economy = USREconomySubsystem::Get(World);
			if (!Economy || Args.Num() < 2) { return; }
			const ESRTeam Team = Args.Num() > 2 && Args[2].Equals(TEXT("enemy"), ESearchCase::IgnoreCase) ? ESRTeam::Enemy : ESRTeam::Player;
			ASRBuilding* B = Economy->FindBuilding(ParseBuildingType(Args[0]), Team);
			if (!B) { UE_LOG(LogSovereign, Log, TEXT("sr.Damage: no %s"), *Args[0]); return; }
			const float Left = FMath::Clamp(FCString::Atof(*Args[1]), 0.f, 1.f) * B->Stats().MaxHealth;
			B->ReceiveDamage(FMath::Max(B->GetHealth() - Left, 0.f) + (Left <= 0.f ? 1.f : 0.f), nullptr);
			UE_LOG(LogSovereign, Log, TEXT("sr.Damage %s -> %.0f / %.0f (state %d)"), *B->GetDisplayName(), B->GetHealth(), B->Stats().MaxHealth, int32(B->GetState()));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdWindowSize(TEXT("sr.WindowSize"), TEXT("sr.WindowSize W H: resize the game window so the view is W x H pixels (interface scaling tests; r.SetRes does nothing in a PIE window)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UGameViewportClient* Client = World ? World->GetGameViewport() : nullptr;
			const TSharedPtr<SWindow> Window = Client ? Client->GetWindow() : nullptr;
			if (!Window.IsValid() || !Client->Viewport || Args.Num() < 2) { return; }
			// keep the window's own chrome (title bar): grow or shrink by the difference to the current view
			const FVector2D Chrome = Window->GetSizeInScreen() - FVector2D(Client->Viewport->GetSizeXY());
			Window->Resize(FVector2D(FCString::Atof(*Args[0]), FCString::Atof(*Args[1])) + Chrome);
			UE_LOG(LogSovereign, Log, TEXT("sr.WindowSize %s x %s"), *Args[0], *Args[1]);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAlert(TEXT("sr.Alert"), TEXT("sr.Alert <attack|lost|done|wave|pop|info> [X Y]: push a test alert (optionally at a world position, which pings the minimap)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USREconomySubsystem* Economy = USREconomySubsystem::Get(World);
			if (!Economy || Args.Num() == 0) { return; }
			static const TCHAR* Names[] = { TEXT("attack"), TEXT("lost"), TEXT("done"), TEXT("wave"), TEXT("pop"), TEXT("info") };
			static const TCHAR* Texts[] = { TEXT("Your Farm is under attack!"), TEXT("Farm destroyed"), TEXT("Farm completed"), TEXT("The enemy marches on your realm!"), TEXT("Housing is full: build farms"), TEXT("A message") };
			int32 Kind = 5;
			for (int32 i = 0; i < 6; ++i) { if (Args[0].Equals(Names[i], ESearchCase::IgnoreCase)) { Kind = i; } }
			const FVector2D At(Args.Num() > 2 ? FCString::Atof(*Args[1]) : 0.f, Args.Num() > 2 ? FCString::Atof(*Args[2]) : 0.f);
			Economy->PushAlert(ESRAlertKind(Kind), FText::FromString(Texts[Kind]), Args.Num() > 2 ? &At : nullptr);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPlatoon(TEXT("sr.Platoon"), TEXT("sr.Platoon <n> [assign|select|stance|formation]: platoon n (1-based) from / to the selection."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			USRPlatoonSubsystem* P = USRPlatoonSubsystem::Get(World);
			if (!PC || !P || Args.Num() == 0) { return; }
			const int32 I = FCString::Atoi(*Args[0]) - 1;
			const FString Op = Args.Num() > 1 ? Args[1] : TEXT("select");
			if (Op == TEXT("assign"))
			{
				TArray<ASRUnit*> Units;
				for (const TWeakObjectPtr<ASRUnit>& U : PC->GetSelection()) { if (U.IsValid()) { Units.Add(U.Get()); } }
				P->Assign(I, Units);
			}
			else if (Op == TEXT("stance")) { P->CycleStance(I); }
			else if (Op == TEXT("formation")) { P->CycleFormation(I); }
			else { PC->SelectPlatoon(I, true); }
			const FSRPlatoonInfo Info = P->GetInfo(I);
			UE_LOG(LogSovereign, Log, TEXT("sr.Platoon %d '%s': %d shields, %d archers, %s, %s"), I + 1, *Info.Name, Info.Shieldbearers, Info.Archers,
				*USRPlatoonSubsystem::FormationName(Info.Formation).ToString(), *USRPlatoonSubsystem::StanceName(Info.Stance).ToString());
		}));

	// sr.Perf: frame-time sampler. Averages over N seconds of real time, then logs once.
	struct FPerfSampler
	{
		double Left = 0.0, Frames = 0.0, Delta = 0.0, Game = 0.0, Render = 0.0, Gpu = 0.0, Worst = 0.0;
		FTSTicker::FDelegateHandle Handle;
		TWeakObjectPtr<UWorld> World;
	};
	FPerfSampler GPerf;

	FAutoConsoleCommandWithWorldAndArgs CmdPerf(TEXT("sr.Perf"), TEXT("sr.Perf [seconds]: average frame, game-thread, render-thread and GPU times over the next N seconds (default 5) and log them with the unit counts."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (GPerf.Handle.IsValid()) { FTSTicker::GetCoreTicker().RemoveTicker(GPerf.Handle); }
			GPerf = FPerfSampler();
			GPerf.Left = Args.Num() > 0 ? FCString::Atof(*Args[0]) : 5.0;
			GPerf.World = World;
			GPerf.Handle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([](float Dt)
			{
				GPerf.Left -= Dt;
				GPerf.Frames += 1.0;
				GPerf.Delta += Dt;
				GPerf.Worst = FMath::Max(GPerf.Worst, double(Dt));
				GPerf.Game += FPlatformTime::ToMilliseconds(GGameThreadTime);
				GPerf.Render += FPlatformTime::ToMilliseconds(GRenderThreadTime);
				GPerf.Gpu += FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles());
				if (GPerf.Left > 0.0) { return true; }
				const double N = FMath::Max(GPerf.Frames, 1.0);
				int32 Units = 0, Bld = 0;
				if (const USRBattleSubsystem* B = USRBattleSubsystem::Get(GPerf.World.Get())) { Units = B->GetUnits().Num(); }
				if (const USREconomySubsystem* E = USREconomySubsystem::Get(GPerf.World.Get())) { Bld = E->GetBuildings().Num(); }
				UE_LOG(LogSovereign, Log, TEXT("PERF %.1f fps (frame %.2f ms, worst %.1f ms)  game %.2f ms  render %.2f ms  gpu %.2f ms  units %d buildings %d"),
					N / FMath::Max(GPerf.Delta, 1e-6), GPerf.Delta / N * 1000.0, GPerf.Worst * 1000.0, GPerf.Game / N, GPerf.Render / N, GPerf.Gpu / N, Units, Bld);
				GPerf.Handle.Reset();
				return false;
			}));
		}));
}
