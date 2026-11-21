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

	/** Before any actor begins play: the level's ASRMapInfo is copied over the per-map Sovereign Feel settings. */
	virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
	virtual void StartPlay() override;
};
