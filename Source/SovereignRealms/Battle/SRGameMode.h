// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "SRGameMode.generated.h"

/**
 * Game mode for the command & combat slice. Wires up the RTS camera pawn, the
 * controller and the HUD, and asks USRBattleSubsystem to spawn the scenario,
 * so the map itself can stay nearly empty.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ASRGameMode();

	virtual void StartPlay() override;
};
