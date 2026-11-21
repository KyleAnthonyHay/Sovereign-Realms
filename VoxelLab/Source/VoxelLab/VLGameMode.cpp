#include "VLGameMode.h"
#include "VoxelLab.h"
#include "VLKing.h"
#include "VLHUD.h"
#include "VLTroop.h"
#include "VLGrid.h"
#include "VLCommand.h"
#include "VLBattle.h"
#include "DrawDebugHelpers.h"
#include "Engine/AssetManager.h"
#include "Engine/StreamableManager.h"
#include "VLCharacterData.h"
#include "Components/AudioComponent.h"
#include "Sound/SoundBase.h"
#include "Sound/SoundAttenuation.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/CapsuleComponent.h"
#include "EngineUtils.h"
#include "VLPlayerController.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "GameFramework/WorldSettings.h"
#include "GameFramework/GameUserSettings.h"
#include "UnrealClient.h"
#include "RenderTimer.h"
#include "RHI.h"
#include "RHIGlobals.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SViewport.h"
#include "Engine/GameViewportClient.h"
#include "TimerManager.h"

extern ENGINE_API float GAverageFPS;
extern ENGINE_API float GAverageMS;

namespace
{
	// vl.Record: a frame sequence at a fixed time step, with commands timed to its frames (for motion previews)
	struct FRecording
	{
		FString Name;
		int32 Frames = 0;
		int32 Index = 0;
		bool bActive = false;
		TArray<TPair<int32, FString>> At;
		TWeakObjectPtr<AWorldSettings> Settings;      // its frame-time limits are pinned to the step while recording
		float MinFrame = 0.f, MaxFrame = 0.f;
	};
	FRecording GRecording;

	void StopRecording()
	{
		if (GRecording.bActive)
		{
			if (AWorldSettings* WS = GRecording.Settings.Get())
			{
				WS->MinUndilatedFrameTime = GRecording.MinFrame;
				WS->MaxUndilatedFrameTime = GRecording.MaxFrame;
			}
			GRecording.bActive = false;
			GRecording.At.Reset();
			UE_LOG(LogVoxelLab, Log, TEXT("recorded %d frames of %s"), GRecording.Index, *GRecording.Name);
		}
	}

	AVLKing* FindKing(UWorld* World)
	{
		return World ? Cast<AVLKing>(UGameplayStatics::GetPlayerPawn(World, 0)) : nullptr;
	}

	float Arg(const TArray<FString>& Args, int32 Index, float Default)
	{
		return Args.IsValidIndex(Index) ? FCString::Atof(*Args[Index]) : Default;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdShot(TEXT("vl.Shot"), TEXT("vl.Shot <name>: save the view to Saved/Screenshots/VL/<name>.png"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld*)
		{
			const FString Name = Args.Num() > 0 ? Args[0] : TEXT("shot");
			const FString Path = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots/VL") / (Name + TEXT(".png")));
			IFileManager::Get().Delete(*Path);
			FScreenshotRequest::RequestScreenshot(Path, false, false);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdView(TEXT("vl.View"), TEXT("vl.View follow | postcard | free X Y Z Pitch Yaw [FOV]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AVLKing* King = FindKing(World);
			if (!King || Args.Num() == 0)
			{
				return;
			}
			if (Args[0] == TEXT("postcard"))
			{
				King->SetView(1, 0.f);
			}
			else if (Args[0] == TEXT("free") && Args.Num() >= 6)
			{
				King->SetFreeCamera(FVector(Arg(Args, 1, 0), Arg(Args, 2, 0), Arg(Args, 3, 0)), FRotator(Arg(Args, 4, 0), Arg(Args, 5, 0), 0.f), Arg(Args, 6, 50.f));
			}
			else
			{
				King->SetView(0, 0.f);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdTeleport(TEXT("vl.Teleport"), TEXT("vl.Teleport X Y Z [Yaw]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->SetActorLocationAndRotation(FVector(Arg(Args, 0, 0), Arg(Args, 1, 0), Arg(Args, 2, 300)), FRotator(0.f, Arg(Args, 3, King->GetActorRotation().Yaw), 0.f), false, nullptr, ETeleportType::TeleportPhysics);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdWalk(TEXT("vl.Walk"), TEXT("vl.Walk X Y [run]: the king walks there by himself"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->WalkTo(FVector2D(Arg(Args, 0, 0), Arg(Args, 1, 0)), Args.Num() > 2);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMove(TEXT("vl.Move"), TEXT("vl.Move Forward Right Seconds [run]: as if the walk keys (and Shift) were held"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->TestInput(Arg(Args, 0, 1), Arg(Args, 1, 0), Arg(Args, 2, 2), Args.Num() > 3);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdDraw(TEXT("vl.Draw"), TEXT("vl.Draw 0|1: sheathe / draw the sword"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->SetArmed(Arg(Args, 0, 1) > 0.5f);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAttack(TEXT("vl.Attack"), TEXT("vl.Attack [1|2|3]: a click (draws first if need be; in the battle stance the next swing of the combo), or that swing: 1 side slash, 2 diagonal cut, 3 up-down-up"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->Attack(Args.Num() > 0 ? FMath::Clamp(FCString::Atoi(*Args[0]) - 1, 0, 2) : -1);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdCamLag(TEXT("vl.CamLag"), TEXT("vl.CamLag 0|1: the follow camera keeps him dead centre / trails him as usual"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->SetCameraLag(Arg(Args, 0, 1) > 0.5f);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdJump(TEXT("vl.Jump"), TEXT("as if Space were pressed"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->Jump();
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdHurt(TEXT("vl.Hurt"), TEXT("vl.Hurt [Amount]: the king takes damage (white flash, a held pose)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->ReceiveDamage(Arg(Args, 0, 10.f));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdHitTune(TEXT("vl.HitTune"), TEXT("vl.HitTune PauseSeconds [FlashSeconds [FlashStrength]]"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->HitPauseSeconds = Arg(Args, 0, King->HitPauseSeconds);
				King->HitFlashSeconds = Arg(Args, 1, King->HitFlashSeconds);
				King->HitFlashStrength = Arg(Args, 2, King->HitFlashStrength);
				UE_LOG(LogVoxelLab, Log, TEXT("hit: pause %.3f s, flash %.3f s at %.2f"), King->HitPauseSeconds, King->HitFlashSeconds, King->HitFlashStrength);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRecord(TEXT("vl.Record"), TEXT("vl.Record Name Frames [Fps]: save Frames screenshots Saved/Screenshots/VL/Name_000.png .. at a fixed time step (default 30 a second)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() < 2 || !World || !World->GetWorldSettings())
			{
				return;
			}
			StopRecording();                    // (the commands queued with vl.At stay: they were given for this recording)
			GRecording.Name = Args[0];
			GRecording.Frames = FMath::Clamp(FCString::Atoi(*Args[1]), 1, 2000);
			GRecording.Index = 0;
			GRecording.bActive = true;
			// every frame is one step of game time, however long it really took: the world clamps its frame time to this
			AWorldSettings* WS = World->GetWorldSettings();
			GRecording.Settings = WS;
			GRecording.MinFrame = WS->MinUndilatedFrameTime;
			GRecording.MaxFrame = WS->MaxUndilatedFrameTime;
			WS->MinUndilatedFrameTime = WS->MaxUndilatedFrameTime = 1.f / FMath::Clamp(Arg(Args, 2, 30.f), 5.f, 240.f);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAt(TEXT("vl.At"), TEXT("vl.At Frame <command>: run a command when the recording reaches that frame"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld*)
		{
			if (Args.Num() >= 2)
			{
				TArray<FString> Rest(Args);
				Rest.RemoveAt(0);
				GRecording.At.Emplace(FCString::Atoi(*Args[0]), FString::Join(Rest, TEXT(" ")));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMode(TEXT("vl.Mode"), TEXT("vl.Mode hero|overview"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->SetHeroMode(Args.Num() == 0 || Args[0] != TEXT("overview"));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSelect(TEXT("vl.Select"), TEXT("vl.Select king|<building name>|none"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->SelectByName(Args.Num() ? FString::Join(Args, TEXT(" ")) : FString());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdTrain(TEXT("vl.Train"), TEXT("vl.Train <building name> [count]: queue troops there (Barracks: swordsmen, Archery Range: archers)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AVLGameMode* GM = World ? World->GetAuthGameMode<AVLGameMode>() : nullptr;
			if (!GM || Args.Num() == 0)
			{
				return;
			}
			int32 Count = 1;
			TArray<FString> Words(Args);
			if (Words.Num() > 1 && Words.Last().IsNumeric())
			{
				Count = FCString::Atoi(*Words.Last());
				Words.Pop();
			}
			const FName Tag(*(TEXT("Name:") + FString::Join(Words, TEXT(" "))));
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				if (It->ActorHasTag(Tag))
				{
					for (int32 i = 0; i < Count; ++i)
					{
						GM->Train(*It);
					}
					return;
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdControl(TEXT("vl.Control"), TEXT("vl.Control king|<unit name>: take control of one of the player's units"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AVLKing* Me = FindKing(World);
			if (!Me)
			{
				return;
			}
			const FString Name = (Args.Num() ? FString::Join(Args, TEXT(" ")) : FString(TEXT("king"))).Replace(TEXT("_"), TEXT(" "));
			for (TActorIterator<AVLKing> It(World); It; ++It)
			{
				if (It->Team != UVLBattle::Player || It->IsDead())
				{
					continue;       // never the enemy's
				}
				if (Name.Equals(TEXT("king"), ESearchCase::IgnoreCase) ? !It->IsTroop() : It->GetDisplayName().Equals(Name, ESearchCase::IgnoreCase))
				{
					Me->TakeControlOf(*It);
					return;
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMenu(TEXT("vl.Menu"), TEXT("vl.Menu 0|1|main|new|pause|settings|controls|end: close the menu / the pause menu / that screen"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr)
			{
				if (AVLHUD* HUD = Cast<AVLHUD>(PC->GetHUD()))
				{
					const FString W = Args.Num() ? Args[0].ToLower() : FString(TEXT("1"));
					const EVLScreen Screen = W == TEXT("main") ? EVLScreen::Main : W == TEXT("new") ? EVLScreen::NewGame : W == TEXT("settings") ? EVLScreen::Settings
						: W == TEXT("end") ? EVLScreen::End : W == TEXT("controls") ? EVLScreen::Controls : (W == TEXT("0") ? EVLScreen::None : EVLScreen::Pause);
					HUD->SetScreen(Screen);
					UE_LOG(LogVoxelLab, Log, TEXT("menu: screen %d"), int32(Screen));
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRestart(TEXT("vl.Restart"), TEXT("vl.Restart [0|1|2]: this map again with a new match (difficulty: this one's)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const UVLBattle* Battle = UVLBattle::Get(World);
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			const AVLHUD* HUD = PC ? Cast<AVLHUD>(PC->GetHUD()) : nullptr;
			if (HUD)
			{
				AVLHUD::OpenMatch(World, HUD->CurrentMap(), Args.Num() ? FCString::Atoi(*Args[0]) : (Battle ? Battle->GetDifficulty() : 1));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOrbit(TEXT("vl.Orbit"), TEXT("vl.Orbit Yaw Pitch Distance: aim the follow camera"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->SetOrbit(Arg(Args, 0, 0), Arg(Args, 1, -20), Arg(Args, 2, 520));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPerf(TEXT("vl.Perf"), TEXT("log the smoothed frame rate"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld*)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("perf: %.1f fps, %.2f ms | game %.2f ms, draw %.2f ms, gpu %.2f ms"), GAverageFPS, GAverageMS,
				FPlatformTime::ToMilliseconds(GGameThreadTime), FPlatformTime::ToMilliseconds(GRenderThreadTime), FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles()));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdWhere(TEXT("vl.Where"), TEXT("log the king's position"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				UE_LOG(LogVoxelLab, Log, TEXT("King at %s yaw %.0f speed %.0f"), *King->GetActorLocation().ToString(), King->GetActorRotation().Yaw, King->GetVelocity().Size2D());
			}
		}));

	// ---- orders, platoons, the tower: for tests (Tools/pie.py run "...")
	void FindUnits(UWorld* World, const FString& Who, TArray<AVLKing*>& Out)
	{
		Out.Reset();
		UVLCommand* Command = UVLCommand::Get(World);
		if (Who.Equals(TEXT("selection"), ESearchCase::IgnoreCase) || Who.Equals(TEXT("sel"), ESearchCase::IgnoreCase))
		{
			if (Command)
			{
				Command->GetSelection(Out);
			}
			return;
		}
		const FString Name = Who.Replace(TEXT("_"), TEXT(" "));
		for (TActorIterator<AVLKing> It(World); It; ++It)
		{
			const bool bKing = !It->IsTroop();
			if (It->IsDead())
			{
				continue;
			}
			if (Who.Equals(TEXT("enemy"), ESearchCase::IgnoreCase))
			{
				if (It->Team != UVLBattle::Player)
				{
					Out.Add(*It);
				}
				continue;
			}
			if (It->Team != UVLBattle::Player && !It->GetDisplayName().Equals(Name, ESearchCase::IgnoreCase))
			{
				continue;       // (the group words mean the player's own units)
			}
			if (Who.Equals(TEXT("all"), ESearchCase::IgnoreCase)
				|| (Who.Equals(TEXT("troops"), ESearchCase::IgnoreCase) && !bKing)
				|| (Who.Equals(TEXT("king"), ESearchCase::IgnoreCase) && bKing)
				|| (Who.Equals(TEXT("archers"), ESearchCase::IgnoreCase) && It->GetKind() == TEXT("Archer"))
				|| (Who.Equals(TEXT("swordsmen"), ESearchCase::IgnoreCase) && It->GetKind() == TEXT("Swordsman"))
				|| It->GetDisplayName().Equals(Name, ESearchCase::IgnoreCase))
			{
				Out.Add(*It);
			}
		}
		Out.Sort([](const AVLKing& A, const AVLKing& B) { return A.GetDisplayName() < B.GetDisplayName(); });
	}

	AActor* FindBuilding(UWorld* World, const FString& Name)
	{
		const FName Tag(*(TEXT("Name:") + Name.Replace(TEXT("_"), TEXT(" "))));
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			if (It->ActorHasTag(Tag))
			{
				return *It;
			}
		}
		return nullptr;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdOrder(TEXT("vl.Order"), TEXT("vl.Order <who> X Y [Z] [run]: an order as a right click gives it. who: selection | all | troops | king | archers | swordsmen | a name (Swordsman_2)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* Command = UVLCommand::Get(World);
			if (!Command || Args.Num() < 3)
			{
				return;
			}
			TArray<AVLKing*> Units;
			FindUnits(World, Args[0], Units);
			const bool bRun = Args.Last().Equals(TEXT("run"), ESearchCase::IgnoreCase);
			const bool bHasZ = Args.Num() > 3 && Args[3].IsNumeric();
			FVector Ground(Arg(Args, 1, 0), Arg(Args, 2, 0), bHasZ ? Arg(Args, 3, 0) : 0.f);
			if (!bHasZ)
			{
				// the ground under that point, as the mouse would find it
				FHitResult Hit;
				FCollisionQueryParams Params(TEXT("OrderGround"), false);
				for (TActorIterator<APawn> It(World); It; ++It)
				{
					Params.AddIgnoredActor(*It);
				}
				if (World->LineTraceSingleByChannel(Hit, Ground + FVector(0.f, 0.f, 6000.f), Ground - FVector(0.f, 0.f, 3000.f), ECC_Visibility, Params))
				{
					Ground = Hit.ImpactPoint;
				}
			}
			UE_LOG(LogVoxelLab, Log, TEXT("order: %d unit(s) to %s in %s"), Units.Num(), *Ground.ToCompactString(), UVLCommand::FormationName(Command->SelectionFormation()));
			Command->OrderMove(Units, Ground, bRun, Units.Num() > 1 ? Command->SelectionFormation() : EVLFormation::Line);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSelectUnits(TEXT("vl.SelectUnits"), TEXT("vl.SelectUnits <who> [add]: all | troops | king | archers | swordsmen | a name | none"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* Command = UVLCommand::Get(World);
			if (!Command || Args.Num() == 0)
			{
				return;
			}
			TArray<AVLKing*> Units;
			FindUnits(World, Args[0], Units);
			Command->Select(Units, Args.Num() > 1);
			UE_LOG(LogVoxelLab, Log, TEXT("selected %d unit(s)"), Command->NumSelected());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdFormation(TEXT("vl.Formation"), TEXT("vl.Formation line|column|wedge|square|loose: the formation of the selection (of its platoon, if it is one)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLCommand* Command = UVLCommand::Get(World))
			{
				if (Args.Num() > 0)
				{
					Command->SetFormationByName(Args[0]);
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPlatoon(TEXT("vl.Platoon"), TEXT("vl.Platoon assign|add|select N: platoon N (1..6) from / with the selection"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* Command = UVLCommand::Get(World);
			if (!Command || Args.Num() < 2)
			{
				return;
			}
			const int32 Index = FCString::Atoi(*Args[1]) - 1;
			TArray<AVLKing*> Units;
			Command->GetSelection(Units);
			if (Args[0] == TEXT("assign"))
			{
				Command->AssignPlatoon(Index, Units);
			}
			else if (Args[0] == TEXT("add"))
			{
				Command->AddToPlatoon(Index, Units);
			}
			else
			{
				Command->GetPlatoon(Index, Units);
				Command->Select(Units);
			}
			Command->GetPlatoon(Index, Units);
			UE_LOG(LogVoxelLab, Log, TEXT("platoon %d: %s, %s"), Index + 1, *Command->PlatoonName(Index), UVLCommand::FormationName(Command->PlatoonFormation(Index)));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdGarrison(TEXT("vl.Garrison"), TEXT("vl.Garrison <who> [building name]: order them onto the watch tower (default: Watch Tower)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* Command = UVLCommand::Get(World);
			if (!Command || Args.Num() == 0)
			{
				return;
			}
			TArray<AVLKing*> Units;
			FindUnits(World, Args[0], Units);
			TArray<FString> Rest(Args);
			Rest.RemoveAt(0);
			AActor* Tower = FindBuilding(World, Rest.Num() ? FString::Join(Rest, TEXT(" ")) : TEXT("Watch Tower"));
			if (Tower)
			{
				Command->OrderGarrison(Units, Tower, false);
			}
			UE_LOG(LogVoxelLab, Log, TEXT("garrison: %d unit(s) ordered to %s"), Units.Num(), Tower ? *Tower->GetName() : TEXT("(no such building)"));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdEmptyTower(TEXT("vl.EmptyTower"), TEXT("vl.EmptyTower [building name]: everyone on the lookout comes down"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* Command = UVLCommand::Get(World);
			AActor* Tower = FindBuilding(World, Args.Num() ? FString::Join(Args, TEXT(" ")) : TEXT("Watch Tower"));
			if (Command && Tower)
			{
				Command->EmptyTower(Tower);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpawn(TEXT("vl.Spawn"), TEXT("vl.Spawn Swordsman|Archer X Y [count]: troops on the ground there, without training (rows of five)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			AVLGameMode* GM = World ? World->GetAuthGameMode<AVLGameMode>() : nullptr;
			UVLGrid* Grid = UVLGrid::Get(World);
			if (!GM || Args.Num() < 3)
			{
				return;
			}
			const int32 Count = FMath::Clamp(int32(Arg(Args, 3, 1)), 1, 40);
			for (int32 i = 0; i < Count; ++i)
			{
				FVector P(Arg(Args, 1, 0) + (i % 5) * 130.f, Arg(Args, 2, 0) + (i / 5) * 130.f, 0.f);
				if (Grid && Grid->EnsureBuilt())
				{
					const int32 Node = Grid->NearestNode(FVector(P.X, P.Y, 100000.f), 20, Grid->MainRegion());
					if (Node != INDEX_NONE)
					{
						P = Grid->NodePos(Node);
					}
				}
				GM->SpawnTroopAt(Args[0], P);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdUnits(TEXT("vl.Units"), TEXT("log every unit: where it is, what it is doing, how far from its goal"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			TArray<AVLKing*> Units;
			FindUnits(World, TEXT("all"), Units);
			UVLCommand* Command = UVLCommand::Get(World);
			for (const AVLKing* U : Units)
			{
				const FVector F = U->GetFeet();
				const FString State = U->IsGarrisoned() ? TEXT("on the tower") : (U->HasOrder() ? FString::Printf(TEXT("walking, %d corners left, %.0f cm to go"), U->GetWaypoints().Num(),
					FVector::Dist2D(F, U->GetWaypoints().Last())) : TEXT("idle"));
				UE_LOG(LogVoxelLab, Log, TEXT("unit %-14s at %6.0f %6.0f %5.0f  %s%s"), *U->GetDisplayName(), F.X, F.Y, F.Z, *State, (Command && Command->IsSelected(U)) ? TEXT("  [selected]") : TEXT(""));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPath(TEXT("vl.Path"), TEXT("vl.Path X0 Y0 X1 Y1: log the route between two points of the ground (and draw it for 20 s)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLGrid* Grid = UVLGrid::Get(World);
			if (!Grid || !Grid->EnsureBuilt() || Args.Num() < 4)
			{
				return;
			}
			const int32 A = Grid->NearestNode(FVector(Arg(Args, 0, 0), Arg(Args, 1, 0), 100000.f), 20, Grid->MainRegion());
			const int32 B = Grid->NearestNode(FVector(Arg(Args, 2, 0), Arg(Args, 3, 0), 100000.f), 20, Grid->MainRegion());
			if (A == INDEX_NONE || B == INDEX_NONE)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("path: no walkable ground there"));
				return;
			}
			TArray<FVector> Path;
			const double T0 = FPlatformTime::Seconds();
			const bool bOk = Grid->FindPath(Grid->NodePos(A), Grid->NodePos(B), Path);
			const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
			float Length = 0.f;
			FVector Prev = Grid->NodePos(A);
			FString Corners;
			for (const FVector& P : Path)
			{
				Length += FVector::Dist2D(Prev, P);
				DrawDebugLine(World, Prev + FVector(0.f, 0.f, 40.f), P + FVector(0.f, 0.f, 40.f), FColor::Cyan, false, 20.f, 0, 8.f);
				Prev = P;
				Corners += FString::Printf(TEXT(" (%.0f %.0f %.0f)"), P.X, P.Y, P.Z);
			}
			UE_LOG(LogVoxelLab, Log, TEXT("path: %s, %d corners, %.1f m (straight %.1f m), %.2f ms:%s"), bOk ? TEXT("found") : TEXT("NONE"), Path.Num(), Length / 100.f,
				FVector::Dist2D(Grid->NodePos(A), Grid->NodePos(B)) / 100.f, Ms, *Corners);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdGrid(TEXT("vl.Grid"), TEXT("vl.Grid [X Y [Radius]] | rebuild: draw the path grid round a point (default: the king) for 20 s"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLGrid* Grid = UVLGrid::Get(World);
			AVLKing* King = FindKing(World);
			if (!Grid)
			{
				return;
			}
			if (Args.Num() > 0 && Args[0] == TEXT("rebuild"))
			{
				Grid->Build();
				return;
			}
			Grid->EnsureBuilt();
			const FVector At = Args.Num() >= 2 ? FVector(Arg(Args, 0, 0), Arg(Args, 1, 0), 0.f) : (King ? King->GetActorLocation() : FVector::ZeroVector);
			Grid->DebugDraw(At, Arg(Args, 2, 1500.f), 20.f);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdShowPaths(TEXT("vl.ShowPaths"), TEXT("vl.ShowPaths [Seconds]: draw every unit's route as it is now"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			for (TActorIterator<AVLKing> It(World); It; ++It)
			{
				FVector Prev = It->GetFeet();
				for (const FVector& P : It->GetWaypoints())
				{
					DrawDebugLine(World, Prev + FVector(0.f, 0.f, 40.f), P + FVector(0.f, 0.f, 40.f), FColor::Yellow, false, Arg(Args, 0, 8.f), 0, 7.f);
					Prev = P;
				}
			}
		}));

	// the mouse, at a point of the view given as fractions of its width and height (0 0 = top left)
	bool ViewPoint(UWorld* World, const TArray<FString>& Args, int32 At, FVector2D& Out)
	{
		APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
		int32 SX = 0, SY = 0;
		if (!PC || Args.Num() < At + 2)
		{
			return false;
		}
		PC->GetViewportSize(SX, SY);
		Out = FVector2D(Arg(Args, At, 0.5f) * SX, Arg(Args, At + 1, 0.5f) * SY);
		return true;
	}

	// The real thing, for testing the controls: the event goes in where the operating system's would (Slate, with the
	// pointer over the middle of the game's view, or at U V), so that it passes focus, capture and the input mode.
	FAutoConsoleCommandWithWorldAndArgs CmdInput(TEXT("vl.Input"), TEXT("vl.Input click|rclick|wheel D|pinch D|scroll DX DY|key NAME [U V]: a real mouse / trackpad / key event through Slate"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UGameViewportClient* GVC = World ? World->GetGameViewport() : nullptr;
			TSharedPtr<SViewport> Widget = GVC ? GVC->GetGameViewportWidget() : nullptr;
			if (!Widget.IsValid() || Args.Num() < 1 || !FSlateApplication::IsInitialized())
			{
				return;
			}
			FSlateApplication& Slate = FSlateApplication::Get();
			const FString What = Args[0].ToLower();
			const int32 Extra = (What == TEXT("click") || What == TEXT("rclick")) ? 1 : (What == TEXT("scroll") ? 3 : 2);
			const FGeometry& Geo = Widget->GetTickSpaceGeometry();
			const FVector2D At = Geo.LocalToAbsolute(Geo.GetLocalSize() * FVector2D(Arg(Args, Extra, 0.5f), Arg(Args, Extra + 1, 0.5f)));
			Slate.SetCursorPos(At);
			Slate.OnMouseMove();
			{
				// what the event will reach: the innermost widget under the pointer, and who has the keyboard
				const FWidgetPath Under = Slate.LocateWindowUnderMouse(At, Slate.GetInteractiveTopLevelWindows());
				const TSharedPtr<SWidget> Focus = Slate.GetUserFocusedWidget(0);
				UE_LOG(LogVoxelLab, Log, TEXT("input: under the pointer %s (%s, game view %s); keyboard focus %s; capture %d"),
					Under.IsValid() ? *Under.GetLastWidget()->GetTypeAsString() : TEXT("nothing"), Under.IsValid() ? *Under.GetWindow()->GetTitle().ToString() : TEXT("-"),
					Under.IsValid() && Under.ContainsWidget(Widget.Get()) ? TEXT("yes") : TEXT("NO"), Focus.IsValid() ? *Focus->GetTypeAsString() : TEXT("none"), Slate.HasAnyMouseCaptor() ? 1 : 0);
			}
			const float D = Arg(Args, 1, 1.f);
			if (What == TEXT("click") || What == TEXT("rclick"))
			{
				const EMouseButtons::Type Button = What == TEXT("click") ? EMouseButtons::Left : EMouseButtons::Right;
				Slate.OnMouseDown(nullptr, Button, At);
				FTimerHandle Handle;
				World->GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateLambda([Button, At]() { FSlateApplication::Get().OnMouseUp(Button, At); }), 0.08f, false);
			}
			else if (What == TEXT("wheel"))
			{
				Slate.OnMouseWheel(D, At);
			}
			else if (What == TEXT("pinch"))
			{
				Slate.OnTouchGesture(EGestureEvent::Magnify, FVector2D(D, D), 0.f, false);
			}
			else if (What == TEXT("scroll"))
			{
				Slate.OnTouchGesture(EGestureEvent::Scroll, FVector2D(D, Arg(Args, 2, 0.f)), Arg(Args, 2, 0.f), false);
			}
			else if (What == TEXT("key") && Args.Num() > 1)
			{
				const FKey Key(*Args[1]);
				const uint32* Code = nullptr; const uint32* Char = nullptr;
				FInputKeyManager::Get().GetCodesFromKey(Key, Code, Char);
				const uint32 C = Code ? *Code : 0, Ch = Char ? *Char : 0;
				Slate.OnKeyDown(C, Ch, false);
				FTimerHandle Handle;
				World->GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateLambda([C, Ch]() { FSlateApplication::Get().OnKeyUp(C, Ch, false); }), 0.08f, false);
			}
			UE_LOG(LogVoxelLab, Log, TEXT("input: %s at %.0f %.0f"), *What, At.X, At.Y);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdClick(TEXT("vl.Click"), TEXT("vl.Click U V [shift]: a left click in the overview at that point of the view (fractions 0..1)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D P;
			if (AVLKing* King = FindKing(World); King && ViewPoint(World, Args, 0, P))
			{
				King->ClickAt(P, Args.Num() > 2);
				UE_LOG(LogVoxelLab, Log, TEXT("click: %s selected, %d unit(s)"), King->GetSelected() ? *King->GetSelectedName() : TEXT("nothing"), UVLCommand::Get(World)->NumSelected());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdUIClick(TEXT("vl.UIClick"), TEXT("vl.UIClick U V [right]: a click on the interface at that point of the view (fractions 0..1), as the mouse's would be"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			AVLHUD* HUD = PC ? Cast<AVLHUD>(PC->GetHUD()) : nullptr;
			FVector2D P;
			if (HUD && ViewPoint(World, Args, 0, P))
			{
				const bool bTaken = HUD->OnMousePress(P, Args.Num() > 2);
				UE_LOG(LogVoxelLab, Log, TEXT("uiclick: %.3f %.3f %s"), Arg(Args, 0, 0.5f), Arg(Args, 1, 0.5f), bTaken ? TEXT("taken by the interface") : TEXT("not on the interface"));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdHUD(TEXT("vl.HUD"), TEXT("vl.HUD: log the interface's buttons of the last frame (id, centre as fractions of the view) and its screen"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			if (const AVLHUD* HUD = PC ? Cast<AVLHUD>(PC->GetHUD()) : nullptr)
			{
				HUD->LogButtons();
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdBox(TEXT("vl.Box"), TEXT("vl.Box U0 V0 U1 V1 [shift]: drag a selection box between two points of the view (fractions 0..1)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D A, B;
			if (AVLKing* King = FindKing(World); King && ViewPoint(World, Args, 0, A) && ViewPoint(World, Args, 2, B))
			{
				King->BoxSelect(A, B, Args.Num() > 4);
				UE_LOG(LogVoxelLab, Log, TEXT("box: %d unit(s) selected"), UVLCommand::Get(World)->NumSelected());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRightClick(TEXT("vl.RightClick"), TEXT("vl.RightClick U V [run]: a right click in the overview at that point of the view: an order for the selection"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			FVector2D P;
			if (AVLKing* King = FindKing(World); King && ViewPoint(World, Args, 0, P))
			{
				King->OrderAt(P, Args.Num() > 2);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdScreen(TEXT("vl.Screen"), TEXT("vl.Screen <who | X Y Z>: log where units (or a world point) show in the view, as fractions of it"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			int32 SX = 0, SY = 0;
			if (!PC || Args.Num() == 0)
			{
				return;
			}
			PC->GetViewportSize(SX, SY);
			FVector2D S;
			if (Args.Num() >= 3)
			{
				const bool bOk = PC->ProjectWorldLocationToScreen(FVector(Arg(Args, 0, 0), Arg(Args, 1, 0), Arg(Args, 2, 0)), S);
				UE_LOG(LogVoxelLab, Log, TEXT("screen: point at %.3f %.3f%s"), S.X / SX, S.Y / SY, bOk ? TEXT("") : TEXT(" (off the view)"));
				return;
			}
			TArray<AVLKing*> Units;
			FindUnits(World, Args[0], Units);
			for (const AVLKing* U : Units)
			{
				if (PC->ProjectWorldLocationToScreen(U->GetActorLocation(), S))
				{
					UE_LOG(LogVoxelLab, Log, TEXT("screen: %s at %.3f %.3f"), *U->GetDisplayName(), S.X / SX, S.Y / SY);
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMusic(TEXT("vl.Music"), TEXT("vl.Music [0..1]: the music setting, applied but not saved (0: nothing plays, no song stays loaded); alone: what the music is doing"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLGameMode* GM = World ? World->GetAuthGameMode<AVLGameMode>() : nullptr)
			{
				if (Args.Num() > 0)
				{
					GM->ApplyMusicSetting(FCString::Atof(*Args[0]));
				}
				UE_LOG(LogVoxelLab, Log, TEXT("MUSIC: %s"), *GM->DescribeMusic());
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMap(TEXT("vl.Map"), TEXT("vl.Map town|realm|flatlands|village|highlands: open that map"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() > 0 && World)
			{
				const int32 Map = Args[0].StartsWith(TEXT("h"), ESearchCase::IgnoreCase) ? 4 : Args[0].StartsWith(TEXT("r"), ESearchCase::IgnoreCase) ? 1 : (Args[0].StartsWith(TEXT("f"), ESearchCase::IgnoreCase) ? 2 : (Args[0].StartsWith(TEXT("v"), ESearchCase::IgnoreCase) ? 3 : 0));
				const UVLBattle* Battle = UVLBattle::Get(World);
				AVLHUD::OpenMatch(World, Map, Battle ? Battle->GetDifficulty() : 1);       // a match there at once (no title screen)
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdLook(TEXT("vl.Look"), TEXT("vl.Look X Y [Zoom 0..1] [Yaw]: the overview camera over that point"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (AVLKing* King = FindKing(World))
			{
				King->LookAt(FVector(Arg(Args, 0, 0), Arg(Args, 1, 0), 0.f), Arg(Args, 2, -1.f), Args.Num() > 3 ? Arg(Args, 3, 0.f) : TNumericLimits<float>::Max());
			}
		}));
}

AVLGameMode::AVLGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bTickEvenWhenPaused = true;        // (the command inbox works while the game is paused)
	DefaultPawnClass = AVLKing::StaticClass();
	HUDClass = AVLHUD::StaticClass();
	PlayerControllerClass = AVLPlayerController::StaticClass();     // the trackpad's gestures
}

void AVLGameMode::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	StopRecording();
	StopMusic();
	Super::EndPlay(EndPlayReason);
}

FString AVLGameMode::TroopFor(const AActor* Building)
{
	return UVLBattle::TroopFor(Building);
}

void AVLGameMode::Train(AActor* Building)
{
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		Battle->Train(Building, 1);
	}
}

int32 AVLGameMode::Queued(const AActor* Building) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	return Battle ? Battle->QueueLength(Building) : 0;
}

float AVLGameMode::Progress(const AActor* Building) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	return Battle ? Battle->TrainProgress(Building) : 0.f;
}

AVLTroop* AVLGameMode::SpawnTroopAt(const FString& Kind, const FVector& Ground, float Yaw)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	return Battle ? Battle->SpawnTroop(Kind, UVLBattle::Player, Ground, Yaw) : nullptr;
}

void AVLGameMode::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
	Super::InitGame(MapName, Options, ErrorMessage);
	bMatchOption = UGameplayStatics::HasOption(Options, TEXT("Match"));
	OptionDifficulty = FMath::Clamp(UGameplayStatics::GetIntOption(Options, TEXT("Difficulty"), 1), 0, 2);
}

void AVLGameMode::BeginPlay()
{
	Super::BeginPlay();
	// A window by default, not full screen (full screen grabbed the mouse badly on the Mac, user request 2026-11-21):
	// once per install, a saved full-screen mode is put back to a window (16:9, 85% of the desktop, at most 1600 x 900).
	// F11 / Alt+Enter still toggle full screen, and that choice is kept from then on.
	if (!GIsEditor && GEngine && GConfig)
	{
		bool bDone = false;
		GConfig->GetBool(TEXT("VoxelLab.Video"), TEXT("WindowedByDefault"), bDone, GGameUserSettingsIni);
		if (!bDone)
		{
			if (UGameUserSettings* S = GEngine->GetGameUserSettings())
			{
				const FIntPoint Desk = S->GetDesktopResolution();
				int32 W = FMath::Min(1600, FMath::RoundToInt(Desk.X * 0.85f));
				int32 H = FMath::RoundToInt(W * 9.f / 16.f);
				if (Desk.Y > 0 && H > Desk.Y * 0.85f)
				{
					H = FMath::RoundToInt(Desk.Y * 0.85f);
					W = FMath::RoundToInt(H * 16.f / 9.f);
				}
				S->SetFullscreenMode(EWindowMode::Windowed);
				if (W >= 640 && H >= 360)
				{
					S->SetScreenResolution(FIntPoint(W, H));
				}
				S->ApplyResolutionSettings(false);
				S->ConfirmVideoMode();
				S->SaveSettings();
				UE_LOG(LogVoxelLab, Log, TEXT("window: windowed by default, %d x %d"), W, H);
			}
			GConfig->SetBool(TEXT("VoxelLab.Video"), TEXT("WindowedByDefault"), true, GGameUserSettingsIni);
			GConfig->Flush(false, GGameUserSettingsIni);
		}
	}
	// TEMP: music off by default (user request, 2026-11-21) — restore: read the saved setting again
	//float SavedMusic = 1.f;
	//if (GConfig && GConfig->GetFloat(TEXT("VoxelLab.Audio"), TEXT("Music"), SavedMusic, GGameUserSettingsIni))
	//{
	//	MusicSetting = FMath::Clamp(SavedMusic, 0.f, 1.f);
	//}
	MusicSetting = 0.f;
	auto Load = [](const FString& Name) { return LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Voxel/Audio/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet); };
	if (USoundBase* Loop = Load(TEXT("S_AmbientLoop")))
	{
		Ambient = UGameplayStatics::CreateSound2D(this, Loop, AmbientVolume, 1.f, 0.f, nullptr, true, false);
		if (Ambient)
		{
			Ambient->FadeIn(2.5f, AmbientVolume);
		}
	}
	// the soundtrack starts at a song picked by chance; no song is loaded (and nothing is played) while the music is off
	Song = FMath::RandRange(0, NumSongs - 1) - 1;
	if (MusicSetting > 0.f)
	{
		NextSong();
	}
	OrderSound = Load(TEXT("S_OrderMove"));
	// the shuffle is placed left and right by where the group is; how loud it is, is worked out here (TickShuffle)
	ShufflePan = NewObject<USoundAttenuation>(this);
	ShufflePan->Attenuation.bAttenuate = false;
	ShufflePan->Attenuation.bSpatialize = true;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(TEXT("Spin")))
		{
			Spinners.Add(*It);
		}
	}
	if (UVLGrid* Grid = UVLGrid::Get(this))
	{
		Grid->EnsureBuilt();            // where units can walk (once, at the start of play)
	}
}

void AVLGameMode::CycleMusicVolume()
{
	// 0, 25, 50, 75, 100%
	float Next = FMath::RoundToFloat(MusicSetting * 4.f) / 4.f + 0.25f;
	if (Next > 1.f + KINDA_SMALL_NUMBER)
	{
		Next = 0.f;
	}
	SetMusicSetting(Next);
}

void AVLGameMode::SetMusicSetting(float Setting)
{
	ApplyMusicSetting(Setting);
	if (GConfig)
	{
		GConfig->SetFloat(TEXT("VoxelLab.Audio"), TEXT("Music"), MusicSetting, GGameUserSettingsIni);
		GConfig->Flush(false, GGameUserSettingsIni);
	}
}

FString AVLGameMode::DescribeMusic() const
{
	FString InMemory;
	for (int32 i = 1; i <= NumSongs; ++i)
	{
		const FString Name = FString::Printf(TEXT("S_Music_%d"), i);
		if (FindObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Voxel/Audio/%s.%s"), *Name, *Name)))
		{
			InMemory += FString::Printf(TEXT(" %d"), i);
		}
	}
	return FString::Printf(TEXT("setting %.2f, %s, %s; songs in memory:%s"), MusicSetting, Music ? (Music->IsPlaying() ? TEXT("a component, playing") : TEXT("a component, silent")) : TEXT("no component"),
		bSongLoading ? *FString::Printf(TEXT("loading S_Music_%d"), Song + 1) : (SongPlaying ? *SongPlaying->GetName() : TEXT("no song")), InMemory.IsEmpty() ? TEXT(" none") : *InMemory);
}

void AVLGameMode::ApplyMusicSetting(float Setting)
{
	MusicSetting = FMath::Clamp(Setting, 0.f, 1.f);
	if (MusicSetting <= 0.f)
	{
		StopMusic();                // off: nothing plays, nothing stays loaded
	}
	else if (Music && Music->IsPlaying())
	{
		Music->SetVolumeMultiplier(MusicVolume * MusicSetting);
	}
	else if (!bSongLoading)
	{
		NextSong();                 // turned on: the next song is loaded and fades in
	}
}

void AVLGameMode::StopMusic()
{
	if (Music)
	{
		Music->Stop();
		Music->DestroyComponent();
		Music = nullptr;
	}
	if (SongLoad.IsValid())
	{
		SongLoad->CancelHandle();       // (a load still under way, or the hold on the song loaded)
		SongLoad.Reset();
	}
	SongPlaying = nullptr;
	bSongLoading = false;
}

void AVLGameMode::NextSong()
{
	if (MusicSetting <= 0.f || bSongLoading)
	{
		return;
	}
	Song = (Song + 1) % NumSongs;
	// loaded in the background (a song is streamed from disk as it plays: Tools/ue/import_audio.py), then played
	const FString Name = FString::Printf(TEXT("S_Music_%d"), Song + 1);
	const FSoftObjectPath Path(FString::Printf(TEXT("/Game/Voxel/Audio/%s.%s"), *Name, *Name));
	bSongLoading = true;
	TWeakObjectPtr<AVLGameMode> Weak(this);
	const int32 Wanted = Song;
	TSharedPtr<FStreamableHandle> Load = UAssetManager::GetStreamableManager().RequestAsyncLoad(Path, FStreamableDelegate::CreateLambda([Weak, Path, Wanted]()
	{
		AVLGameMode* GM = Weak.Get();
		if (!GM || !GM->bSongLoading || GM->Song != Wanted)
		{
			return;
		}
		GM->bSongLoading = false;
		USoundBase* Sound = Cast<USoundBase>(Path.ResolveObject());
		if (GM->MusicSetting <= 0.f || !Sound)
		{
			GM->SongLoad.Reset();
			if (!Sound)
			{
				UE_LOG(LogVoxelLab, Warning, TEXT("music: %s could not be loaded"), *Path.ToString());
				GM->SongFailures++;
			}
			return;
		}
		GM->SongFailures = 0;
		GM->SongPlaying = Sound;
		if (!GM->Music)
		{
			GM->Music = UGameplayStatics::CreateSound2D(GM, Sound, GM->MusicVolume * GM->MusicSetting, 1.f, 0.f, nullptr, true, false);
			if (GM->Music)
			{
				GM->Music->bIsUISound = true;       // it plays on through the pause menu
			}
		}
		if (GM->Music)
		{
			GM->Music->SetSound(Sound);
			GM->Music->FadeIn(3.f, GM->MusicVolume * GM->MusicSetting);
		}
	}), FStreamableManager::AsyncLoadHighPriority);
	// (the hold on the song before this one goes with the old handle)
	SongLoad = Load;
	if (!Load.IsValid())
	{
		bSongLoading = false;
		++SongFailures;
	}
}

void AVLGameMode::PlayOrderSound(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	AVLGameMode* GM = World ? World->GetAuthGameMode<AVLGameMode>() : nullptr;
	if (GM && GM->OrderSound && GM->OrderVolume > 0.f)
	{
		const float Pitch = 1.f + FMath::FRandRange(-GM->OrderPitchJitter, GM->OrderPitchJitter);
		UGameplayStatics::PlaySound2D(GM, GM->OrderSound, GM->OrderVolume, Pitch);
		static const IConsoleVariable* Log = IConsoleManager::Get().FindConsoleVariable(TEXT("vl.StepLog"));
		if (Log && Log->GetInt() != 0)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("order sound t=%.3f vol %.2f pitch %.3f"), World->GetTimeSeconds(), GM->OrderVolume, Pitch);
		}
	}
}

void AVLGameMode::TickShuffle(float DeltaSeconds)
{
	// troops on the march, gathered into groups: each joins the first group whose first member is near enough
	struct FGroup
	{
		AVLKing* First = nullptr;
		TArray<AVLKing*, TInlineAllocator<16>> Members;
		int32 Running = 0;
	};
	TArray<FGroup, TInlineAllocator<8>> Groups;
	const float Radius2 = FMath::Square(ShuffleGroupRadius);
	// (B: the units from the battle's registry, in the order they came into the world)
	FVLOptTiming::FScope Timing(FVLOptTiming::Shuffle);
	const UVLBattle* ShuffleBattle = UVLBattle::Get(this);
	if (!ShuffleBattle)
	{
		ShuffleTimers.Reset();
		return;
	}
	for (AVLKing* U : ShuffleBattle->AllUnits())
	{
		if (!U->IsTroop() || U->IsGarrisoned())
		{
			continue;
		}
		const float Speed = U->GetVelocity().Size2D();
		if (Speed < 40.f || U->GetCharacterMovement()->IsFalling())
		{
			continue;
		}
		FGroup* Group = Groups.FindByPredicate([U, Radius2](const FGroup& G) { return FVector::DistSquared2D(G.First->GetActorLocation(), U->GetActorLocation()) < Radius2; });
		if (!Group)
		{
			Group = &Groups.AddDefaulted_GetRef();
			Group->First = U;
		}
		Group->Members.Add(U);
		Group->Running += Speed > (U->WalkSpeed + U->RunSpeed) * 0.5f ? 1 : 0;
	}
	if (Groups.Num() == 0)
	{
		ShuffleTimers.Reset();              // everyone has stopped: silence
		return;
	}
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	const AVLKing* Player = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr;
	TMap<TWeakObjectPtr<AVLKing>, float> Next;
	for (const FGroup& G : Groups)
	{
		const int32 N = G.Members.Num();
		const bool bRun = G.Running * 2 > N;
		const float Rate = FMath::Min(ShuffleRate * FMath::Sqrt(float(N)), ShuffleMaxRate) * (bRun ? ShuffleRunBoost : 1.f);
		const float Gap = 1.f / FMath::Max(Rate, 0.1f);
		const float* Had = ShuffleTimers.Find(G.First);
		float Left = (Had ? FMath::Min(*Had, Gap * 1.3f) : FMath::FRandRange(0.f, Gap * 0.5f)) - DeltaSeconds;
		if (Left <= 0.f)
		{
			Left = Gap * FMath::FRandRange(0.75f, 1.25f);       // (at most one a frame per group)
			const AVLKing* From = G.Members[FMath::RandRange(0, N - 1)];
			const FVector At = From->GetFeet();
			const float Far = Player ? FVector::Dist2D(At, Player->GetListenFocus()) : 0.f;
			const float Fade = FMath::Square(FMath::GetMappedRangeValueClamped(FVector2D(ShuffleNear, FMath::Max(ShuffleRange, ShuffleNear + 1.f)), FVector2D(1.f, 0.f), Far));
			// a few sound thinner than a company
			const float Volume = ShuffleVolume * Fade * FMath::GetMappedRangeValueClamped(FVector2D(1.f, 6.f), FVector2D(0.7f, 1.f), float(N)) * (bRun ? ShuffleRunBoost : 1.f) * FMath::FRandRange(0.8f, 1.f);
			int32 Clip = 0;
			USoundBase* Sound = Volume > 0.004f ? ShuffleSteps.Pick(EVLStepSurface::Carpet, &Clip) : nullptr;
			if (Sound)
			{
				UGameplayStatics::PlaySoundAtLocation(this, Sound, At, Volume, (bRun ? 1.06f : 1.f) * FMath::FRandRange(0.9f, 1.1f), 0.f, ShufflePan);
			}
			static const IConsoleVariable* Log = IConsoleManager::Get().FindConsoleVariable(TEXT("vl.StepLog"));
			if (Log && Log->GetInt() != 0)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("shuffle t=%.3f group of %d (%s, first %s) %s clip %d vol %.3f rate %.1f/s, %.0f cm from the focus"), GetWorld()->GetTimeSeconds(), N,
					bRun ? TEXT("running") : TEXT("walking"), *G.First->GetDisplayName(), Sound ? TEXT("Carpet") : TEXT("(out of range)"), Clip, Volume, Rate, Far);
			}
		}
		Next.Add(G.First, Left);
	}
	ShuffleTimers = MoveTemp(Next);
}

void AVLGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bMatchStarted && bMatchOption)
	{
		// opened from the New Game screen (Restart, vl.Map): the match starts at once
		bMatchStarted = true;
		if (UVLBattle* Battle = UVLBattle::Get(this))
		{
			Battle->StartMatch(OptionDifficulty);
		}
	}
	if (GetWorld()->IsPaused())
	{
		PollTimer = 1.f;            // only the command inbox, below
	}
	else if (bTroopShuffle)
	{
		TickShuffle(DeltaSeconds);
	}
	if (MusicSetting > 0.f && !bSongLoading && SongFailures < NumSongs && (!Music || !Music->IsPlaying()))
	{
		NextSong();                             // one song after another
	}
	for (const TWeakObjectPtr<AActor>& Spinner : Spinners)
	{
		if (Spinner.IsValid())
		{
			Spinner->AddActorLocalRotation(FRotator(22.f * DeltaSeconds, 0.f, 0.f));    // the sails, about their axle
		}
	}
#if !UE_BUILD_SHIPPING
	// (recordings and the command inbox are for tests: neither is in a Shipping build)
	if (GRecording.bActive)
	{
		APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
		for (int32 i = GRecording.At.Num() - 1; i >= 0; --i)
		{
			if (GRecording.At[i].Key <= GRecording.Index)
			{
				const FString Cmd = GRecording.At[i].Value;
				GRecording.At.RemoveAt(i);
				if (PC)
				{
					PC->ConsoleCommand(Cmd, true);
				}
			}
		}
		const FString Path = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots/VL") / FString::Printf(TEXT("%s_%03d.png"), *GRecording.Name, GRecording.Index));
		FScreenshotRequest::RequestScreenshot(Path, false, false);
		if (++GRecording.Index >= GRecording.Frames)
		{
			StopRecording();
		}
	}
	PollTimer += DeltaSeconds;
	if (PollTimer < 0.05f)
	{
		return;
	}
	PollTimer = 0.f;
	const FString Inbox = FPaths::ProjectSavedDir() / TEXT("VLCommands.txt");
	if (!IFileManager::Get().FileExists(*Inbox))
	{
		return;
	}
	TArray<FString> Lines;
	FFileHelper::LoadFileToStringArray(Lines, *Inbox);
	IFileManager::Get().Delete(*Inbox);
	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	for (const FString& Raw : Lines)
	{
		const FString Line = Raw.TrimStartAndEnd();
		if (Line.IsEmpty())
		{
			continue;
		}
		UE_LOG(LogVoxelLab, Log, TEXT("command: %s"), *Line);
		if (PC)
		{
			PC->ConsoleCommand(Line, true);
		}
		else if (GEngine)
		{
			GEngine->Exec(GetWorld(), *Line);
		}
	}
#endif
}
