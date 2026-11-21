// Copyright Sovereign Realms.
//
// Console commands for exercising the slice without a mouse (automated checks, quick tuning).
// Type them in the PIE console (~), or write them one per line to <Project>/Saved/SRCommands.txt
// and the running game executes them (see USRBattleSubsystem::PollCommandInbox).

#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRFogSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRAISubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Battle/SRPlatoonSubsystem.h"
#include "Battle/SRGameFlowSubsystem.h"
#include "Battle/SRMapInfo.h"
#include "Kismet/GameplayStatics.h"
#include "Containers/Ticker.h"
#include "RenderCore.h"
#include "RHI.h"
#include "Buildings/SRBuilding.h"
#include "Player/SRPlayerController.h"
#include "Player/SRCameraPawn.h"
#include "Units/SRUnit.h"
#include "FX/SRBirds.h"
#include "FX/SRLeaves.h"
#include "EngineUtils.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"
#include "GenericPlatform/GenericApplication.h"
#include "HAL/IConsoleManager.h"
#include "UnrealClient.h"
#include "InputKeyEventArgs.h"
#include "TimerManager.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "ImageUtils.h"
#include "HAL/FileManager.h"
#include "Engine/Engine.h"
#include "Misc/App.h"
#include "GameFramework/HUD.h"
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
		if (N == TEXT("stable")) { return ESRBuildingType::Stable; }
		if (N == TEXT("workshop")) { return ESRBuildingType::Workshop; }
		if (N == TEXT("castle")) { return ESRBuildingType::Castle; }
		if (N == TEXT("granary")) { return ESRBuildingType::Granary; }
		if (N == TEXT("treasury")) { return ESRBuildingType::Treasury; }
		if (N == TEXT("relic")) { return ESRBuildingType::RelicTower; }
		if (N == TEXT("siege")) { return ESRBuildingType::SiegeTower; }
		return ESRBuildingType::Farm;
	}

	ESRUnitType ParseUnitType(const FString& Name)
	{
		const FString W = Name.ToLower();
		if (W.StartsWith(TEXT("sc"))) { return ESRUnitType::Scout; }
		if (W.StartsWith(TEXT("med"))) { return ESRUnitType::Medic; }
		if (W.StartsWith(TEXT("a"))) { return ESRUnitType::Archer; }
		if (W.StartsWith(TEXT("h")) || W.StartsWith(TEXT("r"))) { return ESRUnitType::Horseman; }
		if (W.StartsWith(TEXT("c"))) { return ESRUnitType::Catapult; }
		if (W.StartsWith(TEXT("b"))) { return ESRUnitType::Builder; }
		return ESRUnitType::Shieldbearer;
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

	FAutoConsoleCommandWithWorldAndArgs CmdSelectType(TEXT("sr.SelectType"), TEXT("sr.SelectType <0=Shieldbearer|1=Archer|2=Rider|3=Catapult|4=Builder|5=Scout|6=Medic>: select all player units of a type."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!PC || !Battle || Args.Num() < 1) { return; }
			const ESRUnitType Type = ESRUnitType(FMath::Clamp(FCString::Atoi(*Args[0]), 0, SRNumUnitTypes - 1));
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
			Economy->AddResource(ESRTeam::Player, Resource, FCString::Atoi(*Args[1]), true);   // (a test: past the stores' limit)
			UE_LOG(LogSovereign, Log, TEXT("sr.Give: player gold=%d food=%d"), Economy->GetResource(ESRTeam::Player, ESRResource::Gold), Economy->GetResource(ESRTeam::Player, ESRResource::Food));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRecruit(TEXT("sr.Recruit"), TEXT("sr.Recruit <shield|archer|horse|catapult|builder|scout>: queue a recruit at the player's building that trains it (pays the cost; refused like the button would be)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || Args.Num() < 1) { return; }
			const ESRUnitType Type = ParseUnitType(Args[0]);
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
			else if (What == TEXT("granary") || What == TEXT("treasury") || What == TEXT("stable") || What == TEXT("workshop")) { Building = Economy->FindBuilding(ParseBuildingType(What), ESRTeam::Player); }
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

	FAutoConsoleCommandWithWorldAndArgs CmdSandbox(TEXT("sr.Sandbox"), TEXT("sr.Sandbox [map]: start a sandbox match (both kingdoms built up, armies of every kind, the enemy never attacks)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World)) { Flow->StartMatch(-1, Args.Num() > 0 ? FName(*Args[0]) : NAME_None, true); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdWatch(TEXT("sr.Watch"), TEXT("sr.Watch <type> [enemy]: log what every troop of that kind is doing."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!Battle || Args.Num() < 1) { return; }
			const ESRUnitType Type = ParseUnitType(Args[0]);
			const ESRTeam Team = Args.Num() > 1 && Args[1] == TEXT("enemy") ? ESRTeam::Enemy : ESRTeam::Player;
			for (ASRUnit* U : Battle->GetUnits())
			{
				if (U && U->IsActive() && U->GetTeam() == Team && U->GetUnitType() == Type) { UE_LOG(LogSovereign, Log, TEXT("WATCH %s"), *U->DescribeState()); }
			}
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

	FAutoConsoleCommandWithWorldAndArgs CmdBirds(TEXT("sr.Birds"), TEXT("Log where each flock of birds is."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			for (TActorIterator<ASRBirds> It(World); It; ++It)
			{
				FString Line;
				for (int32 i = 0; i < It->NumFlocks(); ++i)
				{
					const FVector P = It->FlockPosition(i);
					Line += FString::Printf(TEXT(" [%d](%.0f,%.0f,%.0f)"), i, P.X, P.Y, P.Z);
				}
				UE_LOG(LogSovereign, Log, TEXT("BIRDS %d birds in %d flocks:%s"), It->NumBirds(), It->NumFlocks(), *Line);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpeed(TEXT("sr.Speed"), TEXT("sr.Speed <x>: run the game x times faster (balance testing; 1 = normal)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const float X = Args.Num() > 0 ? FMath::Clamp(FCString::Atof(*Args[0]), 0.1f, 16.f) : 1.f;
			UGameplayStatics::SetGlobalTimeDilation(World, X);
			UE_LOG(LogSovereign, Log, TEXT("sr.Speed %.1f"), X);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdBuild(TEXT("sr.Build"), TEXT("sr.Build <farm|mine|tower|barracks|range|stable|workshop|granary|treasury> X Y [enemy]: lay a building (pays gold; refused like the player would be)."),
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
			if (ASRPlayerController* PC = GetSRController(World); PC && B && Team == ESRTeam::Player) { PC->SendBuildersTo(B); }
			UE_LOG(LogSovereign, Log, TEXT("sr.Build %s at (%.0f, %.0f): %s"), *Args[0], XY.X, XY.Y, B ? TEXT("placed") : *Why.ToString());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdUpgrade(TEXT("sr.Upgrade"), TEXT("sr.Upgrade [enemy | <building type>]: raise a castle a level, or the player's first upgradable building of a type (granary, treasury, mine, tower...); pays, like the U key."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USREconomySubsystem* Eco = USREconomySubsystem::Get(World);
			if (!Eco) { return; }
			ASRBuilding* Castle = Eco->GetCastle(Args.Num() > 0 && Args[0] == TEXT("enemy") ? ESRTeam::Enemy : ESRTeam::Player);
			if (Args.Num() > 0 && Args[0] != TEXT("enemy") && Args[0] != TEXT("castle"))
			{
				Castle = nullptr;
				const ESRBuildingType Type = ParseBuildingType(Args[0]);
				for (ASRBuilding* B : Eco->GetBuildings()) { if (B && B->Team == ESRTeam::Player && B->BuildingType == Type && B->CanUpgrade()) { Castle = B; break; } }
			}
			if (!Castle) { UE_LOG(LogSovereign, Log, TEXT("sr.Upgrade: nothing to upgrade")); return; }
			const bool bOk = Castle->StartUpgrade();
			UE_LOG(LogSovereign, Log, TEXT("sr.Upgrade %s: %s (level %d, houses %d, holds %d; kingdom stores gold %d food %d)"), *Castle->GetDisplayName(), bOk ? TEXT("started") : TEXT("REFUSED"),
				Castle->GetLevel(), Castle->GetPopProvided(), Castle->GetStoreCapacity(), Eco->GetStorage(Castle->Team, ESRResource::Gold), Eco->GetStorage(Castle->Team, ESRResource::Food));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSetLevel(TEXT("sr.SetLevel"), TEXT("sr.SetLevel <castle|farm|mine|tower|barracks|range|stable|workshop|granary|treasury|all> <level> [enemy]: put every such building of a side at a level at once (free; testing the level looks)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USREconomySubsystem* Eco = USREconomySubsystem::Get(World);
			if (!Eco || Args.Num() < 2) { return; }
			const ESRTeam Team = Args.Num() > 2 && Args[2] == TEXT("enemy") ? ESRTeam::Enemy : ESRTeam::Player;
			const bool bAll = Args[0] == TEXT("all");
			const ESRBuildingType Type = ParseBuildingType(Args[0]);
			int32 Count = 0;
			for (ASRBuilding* B : Eco->GetBuildings())
			{
				if (B && B->Team == Team && B->IsAlive() && B->IsUpgradable() && (bAll || B->BuildingType == Type)) { B->SetLevelNow(FCString::Atoi(*Args[1])); ++Count; }
			}
			UE_LOG(LogSovereign, Log, TEXT("sr.SetLevel %s %s: %d buildings"), *Args[0], *Args[1], Count);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPutBuilding(TEXT("sr.PutBuilding"), TEXT("sr.PutBuilding <castle|farm|mine|tower|barracks|range|stable|workshop|granary|treasury> X Y [level] [enemy]: stand a finished building there at once (free, ignores every rule; testing)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			if (Args.Num() < 3) { return; }
			TArray<FString> Rest(Args.GetData() + 1, 2);
			if (!ParseXY(Rest, XY)) { return; }
			const ESRTeam Team = Args.Last() == TEXT("enemy") ? ESRTeam::Enemy : ESRTeam::Player;
			const FVector At = GroundAt(World, XY);
			ASRBuilding* B = ASRBuilding::SpawnBuilding(World, ParseBuildingType(Args[0]), Team, At, false);
			if (B && Args.Num() > 3 && Args[3] != TEXT("enemy")) { B->SetLevelNow(FCString::Atoi(*Args[3])); }
			UE_LOG(LogSovereign, Log, TEXT("sr.PutBuilding %s at (%.0f, %.0f, %.0f): %s"), *Args[0], At.X, At.Y, At.Z, B ? *B->GetActorNameOrLabel() : TEXT("FAILED"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdScoutCooldown(TEXT("sr.ScoutCooldown"), TEXT("sr.ScoutCooldown [seconds] [enemy]: log (or set) the wait before a kingdom may train its next Scout, and why it could not train one now."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USREconomySubsystem* Eco = USREconomySubsystem::Get(World);
			if (!Eco) { return; }
			const ESRTeam Team = Args.Num() > 0 && Args.Last() == TEXT("enemy") ? ESRTeam::Enemy : ESRTeam::Player;
			if (Args.Num() > 0 && Args[0] != TEXT("enemy")) { Eco->SetScoutCooldown(Team, FCString::Atof(*Args[0])); }
			int32 Queued = 0;
			const int32 Alive = Eco->GetScoutCount(Team, &Queued);
			const FText Why = Eco->GetScoutRefusal(Team);
			UE_LOG(LogSovereign, Log, TEXT("sr.ScoutCooldown %s: %.1fs left, scouts alive=%d queued=%d, castle level %d: %s"), Team == ESRTeam::Enemy ? TEXT("enemy") : TEXT("player"),
				Eco->GetScoutCooldown(Team), Alive, Queued, Eco->GetCastleLevel(Team), Why.IsEmpty() ? TEXT("may train one") : *Why.ToString());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpawn(TEXT("sr.Spawn"), TEXT("sr.Spawn <shield|archer|horse|catapult|builder|scout> X Y [enemy]: put a troop on the field (testing; free, ignores every limit)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			FVector2D XY;
			if (!Battle || Args.Num() < 3) { return; }
			TArray<FString> Rest(Args.GetData() + 1, 2);
			if (!ParseXY(Rest, XY)) { return; }
			const ESRTeam Team = Args.Num() > 3 && Args[3] == TEXT("enemy") ? ESRTeam::Enemy : ESRTeam::Player;
			const ASRUnit* U = Battle->SpawnUnit(ParseUnitType(Args[0]), Team, XY, 0.f, 0.f);
			UE_LOG(LogSovereign, Log, TEXT("sr.Spawn: %s at (%.0f, %.0f)"), U ? *U->GetLabel() : TEXT("FAILED"), XY.X, XY.Y);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOrderPath(TEXT("sr.OrderPath"), TEXT("sr.OrderPath X Y: add a point to the selection's pathway (like Option+right-click)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!PC || !Battle || !ParseXY(Args, XY)) { return; }
			TArray<ASRUnit*> Units;
			for (const TWeakObjectPtr<ASRUnit>& U : PC->GetSelection()) { if (U.IsValid() && U->IsActive() && U->GetTeam() == ESRTeam::Player) { Units.Add(U.Get()); } }
			Battle->ExtendPath(Units, XY, false, PC->GetSelectionFormation());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPatrolPoint(TEXT("sr.PatrolPoint"), TEXT("sr.PatrolPoint X Y: add a point to the selection's patrol (like P, then Option+click)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!PC || !Battle || !ParseXY(Args, XY)) { return; }
			TArray<ASRUnit*> Units;
			for (const TWeakObjectPtr<ASRUnit>& U : PC->GetSelection()) { if (U.IsValid() && U->IsActive() && U->GetTeam() == ESRTeam::Player) { Units.Add(U.Get()); } }
			Battle->ExtendPatrol(Units, XY, PC->GetSelectionFormation());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdHealWard(TEXT("sr.Heal"), TEXT("sr.Heal X Y: the selected Medics look after the player's troop nearest that spot (like right-clicking it)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!PC || !Battle || !ParseXY(Args, XY)) { return; }
			ASRUnit* Best = nullptr;
			float BestD = TNumericLimits<float>::Max();
			for (ASRUnit* U : Battle->GetUnits())
			{
				if (!U || !U->IsActive() || U->GetTeam() != ESRTeam::Player || U->IsSelected()) { continue; }
				const float D = FVector2D::DistSquared(U->GetPos2D(), XY);
				if (D < BestD) { BestD = D; Best = U; }
			}
			const bool bOk = PC->IssueHeal(Best);
			UE_LOG(LogSovereign, Log, TEXT("sr.Heal: %s"), bOk ? *Best->GetLabel() : TEXT("no medics selected / no troop"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdHurt(TEXT("sr.Hurt"), TEXT("sr.Hurt <fraction>: set the selected troops' health to this fraction (testing heals)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || Args.Num() < 1) { return; }
			const float Frac = FMath::Clamp(FCString::Atof(*Args[0]), 0.01f, 1.f);
			for (const TWeakObjectPtr<ASRUnit>& U : PC->GetSelection()) { if (U.IsValid() && U->IsAlive()) { U->SetHealthForLoad(U->Stats().MaxHealth * Frac); } }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdHurtBuilding(TEXT("sr.HurtBuilding"), TEXT("sr.HurtBuilding <fraction> [X Y | all]: put a building's health at this fraction (the one nearest X Y; without, every standing building of the player; 'all': both sides). Testing the fire and the damaged looks; 0 brings it down."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const USREconomySubsystem* Eco = USREconomySubsystem::Get(World);
			if (!Eco || Args.Num() < 1) { return; }
			const float Frac = FMath::Clamp(FCString::Atof(*Args[0]), 0.f, 1.f);
			const bool bAll = Args.Num() == 2 && Args[1].Equals(TEXT("all"), ESearchCase::IgnoreCase);
			TArray<ASRBuilding*> Which;
			if (Args.Num() >= 3)
			{
				const FVector2D XY(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]));
				ASRBuilding* Best = nullptr;
				float BestD = TNumericLimits<float>::Max();
				for (ASRBuilding* B : Eco->GetBuildings())
				{
					if (!B || !B->IsFinished()) { continue; }
					const float D = B->DistanceToFootprint(XY);
					if (D < BestD) { BestD = D; Best = B; }
				}
				if (Best) { Which.Add(Best); }
			}
			else
			{
				for (ASRBuilding* B : Eco->GetBuildings()) { if (B && B->IsFinished() && (bAll || B->Team == ESRTeam::Player)) { Which.Add(B); } }
			}
			for (ASRBuilding* B : Which)
			{
				if (Frac <= 0.f) { B->ReceiveDamage(1.0e9f, nullptr); }
				else { B->DebugSetHealthFrac(Frac); }
				UE_LOG(LogSovereign, Log, TEXT("sr.HurtBuilding: %s at (%.0f, %.0f) health %.0f%%, fire %.2f"), *B->GetDisplayName(), B->GetActorLocation().X, B->GetActorLocation().Y,
					B->GetHealthFrac() * 100.f, B->GetFireStrength());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdFires(TEXT("sr.Fires"), TEXT("Log every burning building: its health, the fire's strength and how many seats are alight."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const USREconomySubsystem* Eco = USREconomySubsystem::Get(World);
			if (!Eco) { return; }
			int32 N = 0;
			for (ASRBuilding* B : Eco->GetBuildings())
			{
				if (!B || B->GetFireStrength() <= 0.f) { continue; }
				++N;
				UE_LOG(LogSovereign, Log, TEXT("FIRE %s at (%.0f, %.0f): health %.0f%%, strength %.2f, seats alight %d"), *B->GetDisplayName(), B->GetActorLocation().X, B->GetActorLocation().Y,
					B->GetHealthFrac() * 100.f, B->GetFireStrength(), B->DebugFireSeats());
			}
			UE_LOG(LogSovereign, Log, TEXT("FIRES %d building(s) burning"), N);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdCameraAngle(TEXT("sr.CameraAngle"), TEXT("sr.CameraAngle <0|1|2>: the camera angle setting (Options > Camera angle), for this session (testing)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() < 1) { return; }
			GetMutableDefault<USRFeelSettings>()->CameraAngle = FMath::Clamp(FCString::Atoi(*Args[0]), 0, 2);
			UE_LOG(LogSovereign, Log, TEXT("sr.CameraAngle %d"), USRFeelSettings::Get().CameraAngle);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdLeaves(TEXT("sr.Leaves"), TEXT("Log the falling leaves: trees read from the level, trees round the camera, leaves alive."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			for (TActorIterator<ASRLeaves> It(World); It; ++It)
			{
				UE_LOG(LogSovereign, Log, TEXT("LEAVES trees %d, in view %d, leaves alive %d"), It->NumTrees(), It->NumNear(), It->NumFalling());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSelectBuildingAt(TEXT("sr.SelectBuildingAt"), TEXT("sr.SelectBuildingAt X Y: select the building nearest that spot (like clicking it)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			const USREconomySubsystem* Eco = USREconomySubsystem::Get(World);
			if (!PC || !Eco || !ParseXY(Args, XY)) { return; }
			ASRBuilding* Best = nullptr;
			float BestD = TNumericLimits<float>::Max();
			for (ASRBuilding* B : Eco->GetBuildings())
			{
				if (!B || !B->IsAlive()) { continue; }
				const float D = B->DistanceToFootprint(XY);
				if (D < BestD) { BestD = D; Best = B; }
			}
			PC->ClearSelection();
			PC->SelectBuilding(Best);
			UE_LOG(LogSovereign, Log, TEXT("sr.SelectBuildingAt: %s"), Best ? *Best->GetDisplayName() : TEXT("nothing"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdTrackpad(TEXT("sr.Trackpad"), TEXT("sr.Trackpad scroll DX DY | pinch M: feed the controller a trackpad gesture, as the Mac reports one (testing)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || Args.Num() < 2) { return; }
			const bool bPinch = Args[0] == TEXT("pinch");
			const FVector2D D(FCString::Atof(*Args[1]), Args.Num() > 2 ? FCString::Atof(*Args[2]) : 0.f);
			const bool bHandled = PC->InputGesture(FInputDeviceId::CreateFromInternalId(0), bPinch ? EGestureEvent::Magnify : EGestureEvent::Scroll, EGesturePhase::Update, D, false, 0);
			UE_LOG(LogSovereign, Log, TEXT("sr.Trackpad %s (%.1f, %.1f): %s"), *Args[0], D.X, D.Y, bHandled ? TEXT("handled") : TEXT("ignored"));
		}));

	// ---- the demo battle: a big war for the loading screen's recording ----
	struct FDemoState
	{
		FTSTicker::FDelegateHandle Handle;
		TWeakObjectPtr<UWorld> World;
		FVector2D From = FVector2D::ZeroVector, To = FVector2D::ZeroVector;
		double Elapsed = 0.0, Length = 30.0;
		FVector2D Focus = FVector2D::ZeroVector;
		bool bRecording = false;
	};
	FDemoState GDemo;

	FAutoConsoleCommandWithWorldAndArgs CmdDemo(TEXT("sr.Demo"), TEXT("sr.Demo [record seconds]: a big battle on the plain with no interface and a slow drifting camera (the loading screen's footage). With seconds: every frame is also saved (MovieFrameNNNNN.png under Saved/Screenshots) at a fixed 30 fps."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World);
			ASRPlayerController* PC = GetSRController(World);
			if (!Battle || !Flow || !PC) { return; }
			Flow->StartMatch(1);
			if (USRFogSubsystem* Fog = USRFogSubsystem::Get(World)) { Fog->SetEnabled(false); }
			if (AHUD* HUD = PC->GetHUD()) { HUD->bShowHUD = false; }
			PC->ClearSelection();
			// Two hosts face each other across the open plain in front of the player's Overlook: shields in front,
			// archers and catapults behind, riders on the wings, a few medics.
			const FVector2D A(-6900.f, -4600.f), B(-3700.f, -3000.f);
			const FVector2D Fwd = (B - A).GetSafeNormal(), Side(-Fwd.Y, Fwd.X);
			auto Host = [&](const FVector2D& At, const FVector2D& Face, ESRTeam Team)
			{
				const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(Face.Y, Face.X));
				struct FRank { ESRUnitType Type; int32 N; float Back; float Spread; };
				const FRank Ranks[] = { { ESRUnitType::Shieldbearer, 16, 0.f, 110.f }, { ESRUnitType::Shieldbearer, 14, 130.f, 115.f },
					{ ESRUnitType::Archer, 14, 330.f, 110.f }, { ESRUnitType::Archer, 10, 450.f, 120.f }, { ESRUnitType::Catapult, 3, 700.f, 420.f },
					{ ESRUnitType::Medic, 3, 560.f, 380.f } };
				for (const FRank& R : Ranks)
				{
					for (int32 i = 0; i < R.N; ++i)
					{
						const FVector2D P = At - Face * R.Back + FVector2D(-Face.Y, Face.X) * (i - (R.N - 1) * 0.5f) * R.Spread;
						Battle->SpawnUnit(R.Type, Team, P, Yaw, FMath::FRandRange(0.f, 0.6f));
					}
				}
				for (int32 Wing = -1; Wing <= 1; Wing += 2)
				{
					for (int32 i = 0; i < 5; ++i)
					{
						const FVector2D P = At + FVector2D(-Face.Y, Face.X) * Wing * (1100.f + 150.f * (i % 3)) - Face * (100.f + 160.f * (i / 3));
						Battle->SpawnUnit(ESRUnitType::Horseman, Team, P, Yaw, FMath::FRandRange(0.f, 0.6f));
					}
				}
			};
			Host(A, Fwd, ESRTeam::Player);
			Host(B, -Fwd, ESRTeam::Enemy);
			Battle->SetAutoBattle(true);
			// the camera drifts slowly along the clash, a little out
			const FVector2D Mid = (A + B) * 0.5f;
			GDemo.World = World;
			GDemo.From = Mid - Side * 900.f;
			GDemo.To = Mid + Side * 900.f;
			GDemo.Elapsed = 0.0;
			GDemo.Length = Args.Num() > 0 ? FMath::Max(FCString::Atof(*Args[0]), 1.f) : 40.0;
			GDemo.bRecording = Args.Num() > 0;
			if (ASRCameraPawn* Camera = Cast<ASRCameraPawn>(PC->GetPawn())) { Camera->FocusOn(Mid, true); Camera->SetZoom(0.46f, true); }
			if (GDemo.bRecording)
			{
				FApp::SetUseFixedTimeStep(true);
				FApp::SetFixedDeltaTime(1.0 / 30.0);
				GIsDumpingMovie = FMath::RoundToInt(GDemo.Length * 30.0);
			}
			if (GDemo.Handle.IsValid()) { FTSTicker::GetCoreTicker().RemoveTicker(GDemo.Handle); }
			GDemo.Handle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([](float Dt)
			{
				UWorld* W = GDemo.World.Get();
				ASRPlayerController* P = W ? GetSRController(W) : nullptr;
				ASRCameraPawn* Camera = P ? Cast<ASRCameraPawn>(P->GetPawn()) : nullptr;
				if (!Camera) { return false; }
				const float Step = GDemo.bRecording ? 1.f / 30.f : Dt;
				GDemo.Elapsed += Step;
				// keep the thick of the fighting in frame: the middle of the troops near the clash, those at blows
				// counting most, followed smoothly, with a slow sideways drift across it
				const FVector2D Mid = (GDemo.From + GDemo.To) * 0.5f;
				FVector2D Sum = FVector2D::ZeroVector;
				float Weight = 0.f;
				if (const USRBattleSubsystem* B = USRBattleSubsystem::Get(W))
				{
					for (const ASRUnit* U : B->GetUnits())
					{
						if (!U || !U->IsActive() || FVector2D::Distance(U->GetPos2D(), Mid) > 4500.f) { continue; }
						const float Wt = U->IsEngaged() ? 3.f : 1.f;
						Sum += U->GetPos2D() * Wt;
						Weight += Wt;
					}
				}
				const FVector2D Heart = Weight > 0.f ? Sum / Weight : Mid;
				const FVector2D Drift = (GDemo.To - GDemo.From).GetSafeNormal() * 350.f * FMath::Sin(float(GDemo.Elapsed / GDemo.Length) * PI - PI * 0.5f);
				GDemo.Focus = GDemo.Elapsed <= Step * 1.5 ? Heart : FMath::Lerp(GDemo.Focus, Heart, 1.f - FMath::Exp(-Step / 1.6f));
				Camera->FocusOn(GDemo.Focus + Drift, true);
				if (GDemo.Elapsed < GDemo.Length) { return true; }
				if (GDemo.bRecording)
				{
					GIsDumpingMovie = 0;
					FApp::SetUseFixedTimeStep(false);
					UE_LOG(LogSovereign, Log, TEXT("sr.Demo: recording done (%.0f s)"), GDemo.Length);
				}
				GDemo.Handle.Reset();
				return false;
			}));
			UE_LOG(LogSovereign, Log, TEXT("sr.Demo: %d troops on the field%s"), Battle->GetUnits().Num(), GDemo.bRecording ? TEXT(", recording") : TEXT(""));
		}));

	// ---- the film: staged shots for the loading screen's footage, read from a script so a take can be re-cut without a build ----
	FAutoConsoleCommandWithWorldAndArgs CmdHost(TEXT("sr.Host"), TEXT("sr.Host X Y FaceX FaceY <player|enemy> [size 0.3..2]: draw up a host there facing that way (shields in front, archers and catapults behind, riders on the wings). Testing and the film."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!Battle || Args.Num() < 5) { return; }
			const FVector2D At(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]));
			const FVector2D Face = FVector2D(FCString::Atof(*Args[2]), FCString::Atof(*Args[3])).GetSafeNormal();
			const ESRTeam Team = Args[4].Equals(TEXT("enemy"), ESearchCase::IgnoreCase) ? ESRTeam::Enemy : ESRTeam::Player;
			const float Size = Args.Num() > 5 ? FMath::Clamp(FCString::Atof(*Args[5]), 0.2f, 2.f) : 1.f;
			const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(Face.Y, Face.X));
			const FVector2D Side(-Face.Y, Face.X);
			struct FRank { ESRUnitType Type; int32 N; float Back; float Spread; };
			const FRank Ranks[] = { { ESRUnitType::Shieldbearer, 16, 0.f, 110.f }, { ESRUnitType::Shieldbearer, 14, 130.f, 115.f },
				{ ESRUnitType::Archer, 14, 330.f, 110.f }, { ESRUnitType::Archer, 10, 450.f, 120.f }, { ESRUnitType::Catapult, 3, 700.f, 420.f },
				{ ESRUnitType::Medic, 3, 560.f, 380.f } };
			int32 Count = 0;
			for (const FRank& R : Ranks)
			{
				const int32 N = FMath::Max(1, FMath::RoundToInt32(R.N * Size));
				for (int32 i = 0; i < N; ++i)
				{
					Count += Battle->SpawnUnit(R.Type, Team, At - Face * R.Back + Side * (i - (N - 1) * 0.5f) * R.Spread, Yaw, 0.f) ? 1 : 0;
				}
			}
			const int32 Riders = FMath::Max(2, FMath::RoundToInt32(5 * Size));
			for (int32 Wing = -1; Wing <= 1; Wing += 2)
			{
				for (int32 i = 0; i < Riders; ++i)
				{
					Count += Battle->SpawnUnit(ESRUnitType::Horseman, Team, At + Side * Wing * (16.f * Size * 55.f + 220.f + 150.f * (i % 3)) - Face * (100.f + 160.f * (i / 3)), Yaw, 0.f) ? 1 : 0;
				}
			}
			UE_LOG(LogSovereign, Log, TEXT("sr.Host: %d troops at (%.0f, %.0f)"), Count, At.X, At.Y);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMarch(TEXT("sr.March"), TEXT("sr.March <player|enemy> X Y [radius] [move]: every troop of a side within radius (default 4000) of where its host stands attack-moves (or just moves) by the offset from its host's middle to X Y, keeping its place in the ranks. Testing and the film."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
			if (!Battle || Args.Num() < 3) { return; }
			const ESRTeam Team = Args[0].Equals(TEXT("enemy"), ESearchCase::IgnoreCase) ? ESRTeam::Enemy : ESRTeam::Player;
			const FVector2D To(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]));
			const float Radius = Args.Num() > 3 ? FCString::Atof(*Args[3]) : 4000.f;
			const bool bMove = Args.Num() > 4 && Args[4].Equals(TEXT("move"), ESearchCase::IgnoreCase);
			// the host: the side's troops nearest the goal (the kingdom's own garrison, far off, is left at home)
			TArray<ASRUnit*> Mine;
			FVector2D Sum = FVector2D::ZeroVector;
			for (ASRUnit* U : Battle->GetUnits())
			{
				if (U && U->IsActive() && U->GetTeam() == Team && FVector2D::Distance(U->GetPos2D(), To) < Radius + 6000.f) { Mine.Add(U); Sum += U->GetPos2D(); }
			}
			if (Mine.Num() == 0) { return; }
			const FVector2D Mid = Sum / float(Mine.Num());
			for (ASRUnit* U : Mine)
			{
				const FVector2D Dest = To + (U->GetPos2D() - Mid) * 0.8f;
				if (bMove) { U->OrderMove(Dest); } else { U->OrderAttackMove(Dest); }
			}
			UE_LOG(LogSovereign, Log, TEXT("sr.March: %d troops to (%.0f, %.0f)"), Mine.Num(), To.X, To.Y);
		}));

	struct FFilmShot
	{
		float Length = 5.f;                    // seconds seen, not counting the head and tail
		FVector2D From = FVector2D::ZeroVector, To = FVector2D::ZeroVector;
		float Zoom0 = 0.5f, Zoom1 = 0.5f, Pitch0 = -40.f, Pitch1 = -40.f, Yaw0 = 0.f, Yaw1 = 0.f;
		float Follow = 0.f;                    // 0..1: how far the focus is drawn to the thick of the fighting near the path
	};
	struct FFilmEvent { float Time = 0.f; FString Command; bool bDone = false; };
	struct FFilmState
	{
		FTSTicker::FDelegateHandle Handle;
		TWeakObjectPtr<UWorld> World;
		TArray<FFilmShot> Shots;
		TArray<FFilmEvent> Events;
		double Elapsed = 0.0;
		int32 Shot = -1, Frame = 0;
		float Head = 1.5f, Tail = 0.5f;        // recorded before and after each shot: the view settles, then the cross-fade
		FVector2D Heart = FVector2D::ZeroVector;
		bool bHeart = false, bRecording = false;
		float OldYaw = 0.f;
		// recording: a frame is asked for, and the film (and the game's clock) only moves on once it has been saved, so no
		// frame is ever missed (the engine's own movie dump lost three in ten here: the window is not drawn every tick)
		bool bWaiting = false, bGotFrame = false;
		int32 Saved = 0;
		FString FrameDir;
		FDelegateHandle Captured;
	};
	FFilmState GFilm;

	FAutoConsoleCommandWithWorldAndArgs CmdFilm(TEXT("sr.Film"), TEXT("sr.Film [record]: play the shots in Saved/Film.txt (no interface, fog of war off). Lines: 'shot <seconds> X0 Y0 X1 Y1 zoom0 zoom1 pitch0 pitch1 [yaw0 yaw1 [follow 0..1]]' (the camera moves evenly from the first to the second over the shot), 'at <seconds> <console command>' (from the film's start), 'head <seconds>', 'tail <seconds>'. Each shot is run for head + seconds + tail, moving throughout: the head lets the picture settle after the cut and both are for cross-fading. With record: every frame is saved (Saved/Film/Frames/FNNNNN.png, none missed) at a fixed 30 fps of game time and each shot's frames are logged (FILM shot ...); Tools/film.py cuts them together."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World);
			ASRPlayerController* PC = GetSRController(World);
			if (!Flow || !PC) { return; }
			TArray<FString> Lines;
			if (!FFileHelper::LoadFileToStringArray(Lines, *(FPaths::ProjectSavedDir() / TEXT("Film.txt")))) { UE_LOG(LogSovereign, Warning, TEXT("sr.Film: no Saved/Film.txt")); return; }
			if (GFilm.Handle.IsValid()) { FTSTicker::GetCoreTicker().RemoveTicker(GFilm.Handle); }
			GFilm = FFilmState();
			for (const FString& Raw : Lines)
			{
				const FString Line = Raw.TrimStartAndEnd();
				TArray<FString> T;
				Line.ParseIntoArrayWS(T);
				if (T.Num() == 0 || Line.StartsWith(TEXT("#"))) { continue; }
				if (T[0] == TEXT("shot") && T.Num() >= 10)
				{
					FFilmShot S;
					S.Length = FCString::Atof(*T[1]);
					S.From = FVector2D(FCString::Atof(*T[2]), FCString::Atof(*T[3]));
					S.To = FVector2D(FCString::Atof(*T[4]), FCString::Atof(*T[5]));
					S.Zoom0 = FCString::Atof(*T[6]); S.Zoom1 = FCString::Atof(*T[7]);
					S.Pitch0 = FCString::Atof(*T[8]); S.Pitch1 = FCString::Atof(*T[9]);
					if (T.Num() >= 12) { S.Yaw0 = FCString::Atof(*T[10]); S.Yaw1 = FCString::Atof(*T[11]); }
					if (T.Num() >= 13) { S.Follow = FMath::Clamp(FCString::Atof(*T[12]), 0.f, 1.f); }
					GFilm.Shots.Add(S);
				}
				else if (T[0] == TEXT("at") && T.Num() >= 3)
				{
					FFilmEvent E;
					E.Time = FCString::Atof(*T[1]);
					E.Command = Line.Mid(Line.Find(T[1]) + T[1].Len()).TrimStart();
					GFilm.Events.Add(E);
				}
				else if (T[0] == TEXT("head") && T.Num() >= 2) { GFilm.Head = FMath::Max(FCString::Atof(*T[1]), 0.f); }
				else if (T[0] == TEXT("tail") && T.Num() >= 2) { GFilm.Tail = FMath::Max(FCString::Atof(*T[1]), 0.f); }
			}
			if (GFilm.Shots.Num() == 0) { UE_LOG(LogSovereign, Warning, TEXT("sr.Film: no shots in Saved/Film.txt")); return; }
			Flow->StartMatch(1);
			if (USRFogSubsystem* Fog = USRFogSubsystem::Get(World)) { Fog->SetEnabled(false); }
			if (AHUD* HUD = PC->GetHUD()) { HUD->bShowHUD = false; }
			PC->ClearSelection();
			GFilm.World = World;
			GFilm.bRecording = Args.Num() > 0 && Args[0].Equals(TEXT("record"), ESearchCase::IgnoreCase);
			GFilm.OldYaw = USRFeelSettings::Get().CameraYaw;
			float Total = 0.f;
			for (const FFilmShot& S : GFilm.Shots) { Total += GFilm.Head + S.Length + GFilm.Tail; }
			if (GFilm.bRecording)
			{
				FApp::SetUseFixedTimeStep(true);
				FApp::SetFixedDeltaTime(1.0 / 30.0);
				GFilm.FrameDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Film/Frames"));
				IFileManager::Get().DeleteDirectory(*GFilm.FrameDir, false, true);
				IFileManager::Get().MakeDirectory(*GFilm.FrameDir, true);
				GFilm.Captured = UGameViewportClient::OnScreenshotCaptured().AddLambda([](int32 Width, int32 Height, const TArray<FColor>& Colors)
				{
					if (!GFilm.bWaiting || GFilm.bGotFrame) { return; }
					TArray<FColor> Opaque = Colors;
					for (FColor& C : Opaque) { C.A = 255; }
					TArray64<uint8> Png;
					FImageUtils::PNGCompressImageArray(Width, Height, TArrayView64<const FColor>(Opaque.GetData(), Opaque.Num()), Png);
					FFileHelper::SaveArrayToFile(Png, *(GFilm.FrameDir / FString::Printf(TEXT("F%05d.png"), GFilm.Frame)));
					GFilm.bGotFrame = true;
					++GFilm.Saved;
				});
			}
			UE_LOG(LogSovereign, Log, TEXT("FILM start: %d shots, %d events, %.1f s run%s"), GFilm.Shots.Num(), GFilm.Events.Num(), Total, GFilm.bRecording ? TEXT(", recording") : TEXT(""));
			GFilm.Handle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([](float Dt)
			{
				UWorld* W = GFilm.World.Get();
				ASRPlayerController* P = W ? GetSRController(W) : nullptr;
				ASRCameraPawn* Camera = P ? Cast<ASRCameraPawn>(P->GetPawn()) : nullptr;
				auto End = [&]()
				{
					if (GFilm.bRecording)
					{
						FApp::SetFixedDeltaTime(1.0 / 30.0);
						FApp::SetUseFixedTimeStep(false);
						UGameViewportClient::OnScreenshotCaptured().Remove(GFilm.Captured);
					}
					GetMutableDefault<USRFeelSettings>()->CameraYaw = GFilm.OldYaw;
					if (Camera) { Camera->EndFilm(); }
					UE_LOG(LogSovereign, Log, TEXT("FILM done: %d frames, %d saved to %s"), GFilm.Frame, GFilm.Saved, *GFilm.FrameDir);
					GFilm.Handle.Reset();
					return false;
				};
				if (!Camera) { return End(); }
				const float Step = GFilm.bRecording ? 1.f / 30.f : FMath::Min(Dt, 0.1f);
				if (GFilm.bRecording && GFilm.bWaiting)
				{
					if (!GFilm.bGotFrame)
					{
						// the frame asked for has not been drawn yet: hold the game's clock still and keep asking
						FApp::SetFixedDeltaTime(1.0e-6);
						if (!FScreenshotRequest::IsScreenshotRequested()) { FScreenshotRequest::RequestScreenshot(false); }
						return true;
					}
					GFilm.bWaiting = false;
					GFilm.Elapsed += Step;
					++GFilm.Frame;
				}
				for (FFilmEvent& E : GFilm.Events)
				{
					if (!E.bDone && GFilm.Elapsed >= E.Time)
					{
						E.bDone = true;
						UE_LOG(LogSovereign, Log, TEXT("FILM %.2f > %s"), GFilm.Elapsed, *E.Command);
						if (GEngine) { GEngine->Exec(W, *E.Command); }
					}
				}
				// which shot, and how far through it (head and tail included: the camera never stands still at a cut)
				float T0 = 0.f;
				int32 Index = INDEX_NONE;
				for (int32 i = 0; i < GFilm.Shots.Num(); ++i)
				{
					const float Run = GFilm.Head + GFilm.Shots[i].Length + GFilm.Tail;
					if (GFilm.Elapsed < T0 + Run) { Index = i; break; }
					T0 += Run;
				}
				if (Index == INDEX_NONE) { return End(); }
				const FFilmShot& S = GFilm.Shots[Index];
				const bool bCut = Index != GFilm.Shot;
				if (bCut)
				{
					GFilm.Shot = Index;
					GFilm.bHeart = false;
					const int32 Frames = FMath::RoundToInt((GFilm.Head + S.Length + GFilm.Tail) * 30.f);
					UE_LOG(LogSovereign, Log, TEXT("FILM shot %d frame %d count %d head %d tail %d"), Index, GFilm.Frame, Frames, FMath::RoundToInt(GFilm.Head * 30.f), FMath::RoundToInt(GFilm.Tail * 30.f));
				}
				const float Run = GFilm.Head + S.Length + GFilm.Tail;
				const float U = FMath::Clamp(float(GFilm.Elapsed - T0) / Run, 0.f, 1.f);
				FVector2D Focus = FMath::Lerp(S.From, S.To, U);
				if (S.Follow > 0.f)
				{
					FVector2D Sum = FVector2D::ZeroVector;
					float Weight = 0.f;
					if (const USRBattleSubsystem* B = USRBattleSubsystem::Get(W))
					{
						for (const ASRUnit* Unit : B->GetUnits())
						{
							if (!Unit || !Unit->IsActive() || FVector2D::Distance(Unit->GetPos2D(), Focus) > 3500.f) { continue; }
							const float Wt = Unit->IsEngaged() ? 3.f : 1.f;
							Sum += Unit->GetPos2D() * Wt;
							Weight += Wt;
						}
					}
					if (Weight > 0.f)
					{
						const FVector2D Heart = Sum / Weight - Focus;      // where the fighting is, from the path
						GFilm.Heart = GFilm.bHeart ? FMath::Lerp(GFilm.Heart, Heart, 1.f - FMath::Exp(-Step / 2.2f)) : Heart;
						GFilm.bHeart = true;
						Focus += GFilm.Heart * S.Follow;
					}
				}
				GetMutableDefault<USRFeelSettings>()->CameraYaw = FMath::Lerp(S.Yaw0, S.Yaw1, U);
				Camera->FilmView(Focus, FMath::Lerp(S.Zoom0, S.Zoom1, U), FMath::Lerp(S.Pitch0, S.Pitch1, U), bCut, Step);
				if (GFilm.bRecording)
				{
					// this pose is drawn, with the game one step on, in the next tick: that frame is the one saved
					FApp::SetFixedDeltaTime(1.0 / 30.0);
					GFilm.bWaiting = true;
					GFilm.bGotFrame = false;
					FScreenshotRequest::RequestScreenshot(false);
					return true;
				}
				GFilm.Elapsed += Step;
				++GFilm.Frame;
				return true;
			}));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdGridCheck(TEXT("sr.GridCheck"), TEXT("Log how the field is connected: the separate pieces of walkable ground, how much is deep water and steep ground, and whether each castle gate, gold vein, relic and old tower can be walked to."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (const USRGridSubsystem* Grid = USRGridSubsystem::Get(World)) { Grid->LogSelfCheck(); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPathTest(TEXT("sr.PathTest"), TEXT("sr.PathTest X0 Y0 X1 Y1: plan a route between two points and log its corners and length (no troop moves)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			USRGridSubsystem* Grid = USRGridSubsystem::Get(World);
			if (!Grid || Args.Num() < 4) { return; }
			const FVector2D From(FCString::Atof(*Args[0]), FCString::Atof(*Args[1])), To(FCString::Atof(*Args[2]), FCString::Atof(*Args[3]));
			TArray<FVector2D> Path;
			const double T0 = FPlatformTime::Seconds();
			const bool bOk = Grid->FindPath(From, To, Path);
			const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
			float Length = 0.f;
			FString Corners;
			FVector2D Prev = From;
			for (const FVector2D& P : Path) { Length += FVector2D::Distance(Prev, P); Prev = P; Corners += FString::Printf(TEXT(" (%.0f,%.0f)"), P.X, P.Y); }
			UE_LOG(LogSovereign, Log, TEXT("sr.PathTest (%.0f,%.0f) -> (%.0f,%.0f): %s, %s, %d point(s), %.0f m, %.2f ms:%s"), From.X, From.Y, To.X, To.Y, bOk ? TEXT("route") : TEXT("NO ROUTE"),
				Grid->CanReach(From, To) ? TEXT("same ground") : TEXT("cut off"), Path.Num(), Length / 100.f, Ms, *Corners);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOrderBuild(TEXT("sr.OrderBuild"), TEXT("sr.OrderBuild X Y: the selected Builders go and work on the player's building nearest that spot (like right-clicking it)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D XY;
			ASRPlayerController* PC = GetSRController(World);
			const USREconomySubsystem* Eco = USREconomySubsystem::Get(World);
			if (!PC || !Eco || !ParseXY(Args, XY)) { return; }
			ASRBuilding* Best = nullptr;
			float BestD = TNumericLimits<float>::Max();
			for (ASRBuilding* B : Eco->GetBuildings())
			{
				if (!B || B->Team != ESRTeam::Player || !B->IsAlive()) { continue; }
				const float D = B->DistanceToFootprint(XY);
				if (D < BestD) { BestD = D; Best = B; }
			}
			int32 Sent = 0;
			for (const TWeakObjectPtr<ASRUnit>& U : PC->GetSelection()) { if (U.IsValid() && U->IsBuilder() && Best) { U->OrderBuild(Best); ++Sent; } }
			UE_LOG(LogSovereign, Log, TEXT("sr.OrderBuild: %d builder(s) to %s"), Sent, Best ? *Best->GetDisplayName() : TEXT("nothing"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPlace(TEXT("sr.Place"), TEXT("sr.Place <farm|mine|tower|barracks|range|stable|workshop|granary|treasury|off>: enter placement mode as if the build hotkey was pressed."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ASRPlayerController* PC = GetSRController(World);
			if (!PC || Args.Num() == 0) { return; }
			if (Args[0] == TEXT("off")) { PC->CancelPlacement(); return; }
			PC->BeginPlacement(ParseBuildingType(Args[0]));
		}));

	// ---- game flow: the menus, for scripted tests ----
	FAutoConsoleCommandWithWorldAndArgs CmdStartMatch(TEXT("sr.StartMatch"), TEXT("sr.StartMatch [0=easy|1=normal|2=hard|-1=keep] [map id]: start a match now, skipping the menus (keeps the difficulty if none is given). With a map id (Sovereign Feel > Maps: two, four) other than the map being played, it opens that map's level and starts there."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World)) { Flow->StartMatch(Args.Num() > 0 ? FCString::Atoi(*Args[0]) : -1, Args.Num() > 1 ? FName(*Args[1]) : FName()); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMap(TEXT("sr.Map"), TEXT("Log the map being played (its id, half extent and starts) and the maps in the list."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World);
			if (!Flow) { return; }
			const USRFeelSettings& F = USRFeelSettings::Get();
			const ASRMapInfo* Info = ASRMapInfo::Get(World);
			UE_LOG(LogSovereign, Log, TEXT("sr.Map: %s (%s), half extent (%.0f, %.0f), player start (%.0f, %.0f), enemy start (%.0f, %.0f), focus up to %.0f, %s"),
				*Flow->GetCurrentMapId().ToString(), *USRGameFlowSubsystem::MapTitle(Flow->GetCurrentMapId()), F.MapHalfExtent.X, F.MapHalfExtent.Y, F.PlayerStart.X, F.PlayerStart.Y,
				F.EnemyStart.X, F.EnemyStart.Y, F.FocusHeightMax,
				Info ? *FString::Printf(TEXT("ground traces %.0f to %.0f"), Info->GroundTraceTop, Info->GroundTraceBottom) : TEXT("no ASRMapInfo in the level (the settings' own values)"));
			for (const FSRMapEntry& M : F.Maps)
			{
				UE_LOG(LogSovereign, Log, TEXT("sr.Map:   %-6s %s  %s%s"), *M.Id.ToString(), *M.Level, *M.Name, Flow->IsMapAvailable(M.Id) ? TEXT("") : TEXT("  (LEVEL MISSING)"));
			}
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

	FAutoConsoleCommandWithWorldAndArgs CmdSave(TEXT("sr.Save"), TEXT("sr.Save [slot]: save the match (default: the pause menu's slot)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World)) { Flow->SaveMatch(Args.Num() > 0 ? Args[0] : FString(USRGameFlowSubsystem::QuickSlot())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdLoad(TEXT("sr.Load"), TEXT("sr.Load [slot]: load a saved match (default: the latest). One saved on another map opens that map's level and is loaded there."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(World)) { Flow->LoadMatch(Args.Num() > 0 ? Args[0] : Flow->LatestSlot()); }
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdFog(TEXT("sr.Fog"), TEXT("sr.Fog <0|1>: fog of war off / on (testing)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (USRFogSubsystem* Fog = USRFogSubsystem::Get(World)) { Fog->SetEnabled(Args.Num() == 0 || Args[0] != TEXT("0")); }
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
