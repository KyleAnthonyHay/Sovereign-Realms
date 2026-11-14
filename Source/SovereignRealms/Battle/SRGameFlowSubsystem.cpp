// Copyright Sovereign Realms.

#include "Battle/SRGameFlowSubsystem.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Player/SRPlayerController.h"
#include "Player/SRCameraPawn.h"
#include "Common/SRFeelSettings.h"
#include "Common/SRUserSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"

USRGameFlowSubsystem* USRGameFlowSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USRGameFlowSubsystem>() : nullptr;
}

bool USRGameFlowSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId USRGameFlowSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(USRGameFlowSubsystem, STATGROUP_Tickables);
}

float USRGameFlowSubsystem::GetStateTime() const
{
	return GetWorld() ? float(GetWorld()->GetRealTimeSeconds() - StateChangedAt) : 0.f;
}

void USRGameFlowSubsystem::SetState(ESRGameState NewState)
{
	State = NewState;
	StateChangedAt = GetWorld()->GetRealTimeSeconds();
	if (ASRPlayerController* PC = Cast<ASRPlayerController>(GetWorld()->GetFirstPlayerController()))
	{
		PC->SetMenuInput(IsModal());
	}
	static const TCHAR* Names[] = { TEXT("MainMenu"), TEXT("Playing"), TEXT("Paused"), TEXT("Ended") };
	UE_LOG(LogSovereign, Log, TEXT("GAME STATE: %s"), Names[int32(NewState)]);
}

void USRGameFlowSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	// The match is decided when a castle falls; give the collapse a moment on screen before the result comes up.
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (State == ESRGameState::Playing && Battle && Battle->GetResult() != ESRBattleResult::Ongoing && Battle->GetTimeSinceResult() > 1.6f)
	{
		SetState(ESRGameState::Ended);
	}
}

void USRGameFlowSubsystem::EnterMainMenu()
{
	UWorld* World = GetWorld();
	ASRPlayerController* PC = Cast<ASRPlayerController>(World->GetFirstPlayerController());
	if (PC) { PC->ResetForNewMatch(); }
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		Battle->ResetBattle();
		Battle->SetSimPaused(true);
	}
	// Open over the player's kingdom; the controller then drifts the camera slowly (ASRPlayerController::ComputePanInput).
	if (ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
	{
		// the citadel sits right of centre, clear of the title and the menu on the left
		FVector2D Focus = USRFeelSettings::Get().PlayerStart;
		const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
		if (const ASRBuilding* Castle = Economy ? Economy->GetCastle(ESRTeam::Player) : nullptr) { Focus = Castle->GetFootprintCentre() + FVector2D(500.f, -900.f); }
		Camera->FocusOn(Focus, true);
		Camera->SetZoom(0.8f, true);
	}
	SetState(ESRGameState::MainMenu);
}

void USRGameFlowSubsystem::StartMatch(int32 Difficulty)
{
	UWorld* World = GetWorld();
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (Difficulty >= 0)
	{
		GetMutableDefault<USRFeelSettings>()->AIDifficulty = FMath::Clamp(Difficulty, 0, 2);
		USRUserSettings::Get()->CaptureAndSave();
	}
	ASRPlayerController* PC = Cast<ASRPlayerController>(World->GetFirstPlayerController());
	if (PC) { PC->ResetForNewMatch(); }
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		Battle->ResetBattle();
		Battle->SetSimPaused(false);
	}
	if (ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
	{
		// Between the castle and the troops drawn up before it.
		FVector2D Focus = F.PlayerStart;
		const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
		if (const ASRBuilding* Castle = Economy ? Economy->GetCastle(ESRTeam::Player) : nullptr)
		{
			Focus = FMath::Lerp(Castle->GetFootprintCentre(), F.PlayerStart, 0.5f);
		}
		Camera->FocusOn(Focus, true);
		Camera->SetZoom(FMath::Max(F.ZoomDefault, 0.5f), true);   // wide enough to take in the castle and the troops
	}
	SetState(ESRGameState::Playing);
	UE_LOG(LogSovereign, Log, TEXT("MATCH START: difficulty %d"), F.AIDifficulty);
}

void USRGameFlowSubsystem::SetPaused(bool bPaused)
{
	if (State != (bPaused ? ESRGameState::Playing : ESRGameState::Paused)) { return; }
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->SetSimPaused(bPaused); }
	SetState(bPaused ? ESRGameState::Paused : ESRGameState::Playing);
}
