// Copyright Sovereign Realms.

#include "Battle/SRGameMode.h"
#include "Battle/SRBattleSubsystem.h"
#include "Player/SRCameraPawn.h"
#include "Player/SRPlayerController.h"
#include "Player/SRHUD.h"
#include "Common/SRFeelSettings.h"
#include "Common/SRUserSettings.h"
#include "Battle/SRGameFlowSubsystem.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

ASRGameMode::ASRGameMode()
{
	DefaultPawnClass = ASRCameraPawn::StaticClass();
	PlayerControllerClass = ASRPlayerController::StaticClass();
	HUDClass = ASRHUD::StaticClass();
}

void ASRGameMode::StartPlay()
{
	Super::StartPlay();

	// The player's saved options (volumes, interface scale, camera habits) override the project's defaults.
	USRUserSettings::Get()->Apply();

	// Open on the title screen over the idle realm (or straight into a match: Sovereign Feel > Debug > Skip Main Menu,
	// or the -SRSkipMenu command-line switch; scripted tests use the sr.StartMatch console command).
	if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this))
	{
		if (USRFeelSettings::Get().bSkipMainMenu || FParse::Param(FCommandLine::Get(), TEXT("SRSkipMenu"))) { Flow->StartMatch(); }
		else { Flow->EnterMainMenu(); }
	}
}
