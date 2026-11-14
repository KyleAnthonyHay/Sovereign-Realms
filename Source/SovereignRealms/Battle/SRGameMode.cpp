// Copyright Sovereign Realms.

#include "Battle/SRGameMode.h"
#include "Battle/SRBattleSubsystem.h"
#include "Player/SRCameraPawn.h"
#include "Player/SRPlayerController.h"
#include "Player/SRHUD.h"
#include "Common/SRFeelSettings.h"

ASRGameMode::ASRGameMode()
{
	DefaultPawnClass = ASRCameraPawn::StaticClass();
	PlayerControllerClass = ASRPlayerController::StaticClass();
	HUDClass = ASRHUD::StaticClass();
}

void ASRGameMode::StartPlay()
{
	Super::StartPlay();

	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		Battle->ResetBattle();
	}

	// Open on the player's army.
	if (const APlayerController* PC = GetWorld()->GetFirstPlayerController())
	{
		if (ASRCameraPawn* Camera = Cast<ASRCameraPawn>(PC->GetPawn()))
		{
			Camera->FocusOn(USRFeelSettings::Get().PlayerStart, true);
		}
	}
}
