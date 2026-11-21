// Copyright Sovereign Realms.

#include "Battle/SRGameMode.h"
#include "Battle/SRBattleSubsystem.h"
#include "Player/SRCameraPawn.h"
#include "Player/SRPlayerController.h"
#include "Player/SRHUD.h"
#include "Common/SRFeelSettings.h"
#include "Common/SRUserSettings.h"
#include "Battle/SRGameFlowSubsystem.h"
#include "Battle/SRMapInfo.h"
#include "Kismet/GameplayStatics.h"
#include "FX/SRBirds.h"
#include "FX/SRLeaves.h"
#include "FX/SRWildlife.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

ASRGameMode::ASRGameMode()
{
	DefaultPawnClass = ASRCameraPawn::StaticClass();
	PlayerControllerClass = ASRPlayerController::StaticClass();
	HUDClass = ASRHUD::StaticClass();
}

void ASRGameMode::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
	Super::InitGame(MapName, Options, ErrorMessage);
	// The map's size, starts and focus ceiling, before anything reads them: this runs ahead of every actor's BeginPlay
	// and of the world subsystems' OnWorldBeginPlay (the grid is built there, from the map's half extent).
	ASRMapInfo::ApplyToSettings(GetWorld());
}

void ASRGameMode::StartPlay()
{
	Super::StartPlay();

	// The player's saved options (volumes, interface scale, camera habits) override the project's defaults.
	USRUserSettings::Get()->Apply();

	// the birds flying round the map (over the title screen too)
	if (USRFeelSettings::Get().bBirds) { GetWorld()->SpawnActor<ASRBirds>(); }
	// the leaves falling from the trees in view
	if (USRFeelSettings::Get().bLeaves) { GetWorld()->SpawnActor<ASRLeaves>(); }
	// the deer (ASRWildlife waits for the walkability grid, then makes its herds)
	if (USRFeelSettings::Get().bWildlife && USRFeelSettings::Get().WildlifeHerds > 0) { GetWorld()->SpawnActor<ASRWildlife>(); }

	// Open on the title screen over the idle realm (or straight into a match: Sovereign Feel > Debug > Skip Main Menu,
	// or the -SRSkipMenu command-line switch; scripted tests use the sr.StartMatch console command).
	if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this))
	{
		// Arriving from another map (USRGameFlowSubsystem::TravelTo): the player chose this one for a new match, or
		// loaded a game saved on it. The URL says which; no title screen in between.
		if (UGameplayStatics::HasOption(OptionsString, USRGameFlowSubsystem::LoadOption()))
		{
			// (false: the save is for this map, or it cannot be loaded at all; never travel again from here)
			if (!Flow->LoadMatch(UGameplayStatics::ParseOption(OptionsString, USRGameFlowSubsystem::LoadOption()), false)) { Flow->EnterMainMenu(); }
		}
		else if (UGameplayStatics::HasOption(OptionsString, USRGameFlowSubsystem::StartOption()))
		{
			const FString Difficulty = UGameplayStatics::ParseOption(OptionsString, USRGameFlowSubsystem::DifficultyOption());
			Flow->StartMatch(Difficulty.IsNumeric() ? FCString::Atoi(*Difficulty) : -1, NAME_None, UGameplayStatics::HasOption(OptionsString, USRGameFlowSubsystem::SandboxOption()));
		}
		else if (USRFeelSettings::Get().bSkipMainMenu || FParse::Param(FCommandLine::Get(), TEXT("SRSkipMenu"))) { Flow->StartMatch(); }
		else { Flow->EnterMainMenu(); }
	}
}
