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
#include "Battle/SRAISubsystem.h"
#include "Battle/SRFogSubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Battle/SRPlatoonSubsystem.h"
#include "Common/SRSaveGame.h"
#include "Units/SRUnit.h"
#include "Kismet/GameplayStatics.h"

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
	// Autosave while a match is being played.
	if (State == ESRGameState::Playing && Battle && Battle->GetResult() == ESRBattleResult::Ongoing)
	{
		AutosaveClock += DeltaTime;
		if (USRFeelSettings::Get().AutosaveInterval > 0.f && AutosaveClock >= USRFeelSettings::Get().AutosaveInterval)
		{
			AutosaveClock = 0.f;
			SaveMatch(AutoSlot());
		}
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
		// On the troops, a little out toward the field: the castle sits low-left in frame, not across the lens
		// (close in, its parapet filled the foreground with blur).
		FVector2D Focus = F.PlayerStart;
		const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
		if (const ASRBuilding* Castle = Economy ? Economy->GetCastle(ESRTeam::Player) : nullptr)
		{
			Focus = F.PlayerStart + (F.PlayerStart - Castle->GetFootprintCentre()).GetSafeNormal() * 400.f;
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

// ------------------------------------------------------------------ saved games

bool USRGameFlowSubsystem::HasSave(const FString& Slot) const
{
	return UGameplayStatics::DoesSaveGameExist(Slot, 0);
}

FString USRGameFlowSubsystem::LatestSlot() const
{
	if (bLatestValid) { return LatestCache; }
	FString Best;
	FDateTime BestAt = FDateTime::MinValue();
	for (const TCHAR* Slot : { QuickSlot(), AutoSlot() })
	{
		if (!HasSave(Slot)) { continue; }
		const USRSaveGame* S = Cast<USRSaveGame>(UGameplayStatics::LoadGameFromSlot(Slot, 0));
		if (S && S->SavedAt > BestAt) { BestAt = S->SavedAt; Best = Slot; }
	}
	LatestCache = Best;
	bLatestValid = true;
	return Best;
}

FString USRGameFlowSubsystem::DescribeSave(const FString& Slot) const
{
	if (const FString* Cached = SaveLines.Find(Slot)) { return *Cached; }
	FString Line;
	if (HasSave(Slot))
	{
		if (const USRSaveGame* S = Cast<USRSaveGame>(UGameplayStatics::LoadGameFromSlot(Slot, 0)))
		{
			static const TCHAR* Names[3] = { TEXT("Easy"), TEXT("Normal"), TEXT("Hard") };
			const int32 Sec = FMath::FloorToInt(S->BattleClock);
			Line = FString::Printf(TEXT("%s  ·  %d:%02d into the battle  ·  %s"), *S->SavedAt.ToString(TEXT("%d %b %H:%M")), Sec / 60, Sec % 60,
				Names[FMath::Clamp(S->Difficulty, 0, 2)]);
		}
	}
	const_cast<USRGameFlowSubsystem*>(this)->SaveLines.Add(Slot, Line);
	return Line;
}

bool USRGameFlowSubsystem::SaveMatch(const FString& Slot)
{
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Battle || !Eco || Battle->GetResult() != ESRBattleResult::Ongoing) { return false; }
	USRSaveGame* S = Cast<USRSaveGame>(UGameplayStatics::CreateSaveGameObject(USRSaveGame::StaticClass()));
	S->SavedAt = FDateTime::Now();
	S->Difficulty = USRFeelSettings::Get().AIDifficulty;
	S->BattleClock = Battle->GetBattleClock();
	for (int32 t = 0; t < 2; ++t)
	{
		S->Gold[t] = Eco->GetResource(ESRTeam(t), ESRResource::Gold);
		S->Food[t] = Eco->GetResource(ESRTeam(t), ESRResource::Food);
	}
	const FSRMatchStats& St = Battle->GetStats();
	for (int32 t = 0; t < 2; ++t) { S->Stats.Append({ St.Recruited[t], St.TroopsLost[t], St.BuildingsBuilt[t], St.BuildingsLost[t] }); }

	for (const ASRUnit* U : Battle->GetUnits())
	{
		if (!U || !U->IsAlive()) { continue; }
		FSRSavedUnit& O = S->Units.AddDefaulted_GetRef();
		O.Type = U->GetUnitType();
		O.Team = U->GetTeam();
		O.Pos = U->GetPos2D();
		const FVector2D Face = U->GetFacingDir();
		O.Yaw = FMath::RadiansToDegrees(FMath::Atan2(Face.Y, Face.X));
		O.Health = U->GetHealth();
		O.Stance = U->GetStance();
		O.Platoon = U->GetPlatoon();
		O.Home = U->GetHome();
	}
	for (const ASRBuilding* B : Eco->GetBuildings())
	{
		if (!B) { continue; }
		if (B->IsRuntimeBuilt() && !B->IsAlive()) { continue; }    // a fallen one raised in the match: its ruin is about to go
		FSRSavedBuilding& O = S->Buildings.AddDefaulted_GetRef();
		O.LevelName = B->IsRuntimeBuilt() ? FString() : B->GetName();
		O.Type = B->BuildingType;
		O.Team = B->Team;
		O.Location = B->GetActorLocation();
		O.Health = B->GetHealth();
		O.BuildProgress = B->GetBuildProgress();
		O.bDestroyed = !B->IsAlive();
		O.Queue = B->GetQueue();
		O.Rally = B->GetRallyPoint();
		O.Level = B->GetLevel();
		O.UpgradeProgress = B->IsUpgrading() ? B->GetUpgradeFraction() : -1.f;
	}
	if (const USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this))
	{
		for (int32 i = 0; i < Platoons->Num(); ++i)
		{
			const FSRPlatoon* P = Platoons->Find(i);
			if (!P) { continue; }
			FSRSavedPlatoon& O = S->Platoons.AddDefaulted_GetRef();
			O.Index = i;
			O.Name = P->Name;
			O.Formation = P->Formation;
			O.Stance = P->Stance;
			O.bReceivesRecruits = P->bReceivesRecruits;
		}
	}
	if (const USRAISubsystem* AI = USRAISubsystem::Get(this)) { AI->SaveState(S->Commanders); }
	if (const USRFogSubsystem* Fog = USRFogSubsystem::Get(this)) { Fog->GetExplored(S->FogExplored); }
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (const ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr) { S->CameraFocus = FVector2D(Camera->GetFocusPoint()); }

	const bool bOk = UGameplayStatics::SaveGameToSlot(S, Slot, 0);
	SaveLines.Remove(Slot);
	bLatestValid = false;
	if (Slot != AutoSlot() || !bOk)
	{
		SaveMessage = bOk ? TEXT("Game saved.") : TEXT("Could not save the game.");
		SaveMessageTime = FPlatformTime::Seconds();
	}
	UE_LOG(LogSovereign, Log, TEXT("SAVE %s -> %s: %d troops, %d buildings, %.0fs"), bOk ? TEXT("ok") : TEXT("FAILED"), *Slot, S->Units.Num(), S->Buildings.Num(), S->BattleClock);
	return bOk;
}

bool USRGameFlowSubsystem::LoadMatch(const FString& Slot)
{
	USRSaveGame* S = HasSave(Slot) ? Cast<USRSaveGame>(UGameplayStatics::LoadGameFromSlot(Slot, 0)) : nullptr;
	if (!S || S->Version > USRSaveGame::CurrentVersion)
	{
		SaveMessage = TEXT("No saved game to load.");
		SaveMessageTime = FPlatformTime::Seconds();
		return false;
	}
	UWorld* World = GetWorld();
	GetMutableDefault<USRFeelSettings>()->AIDifficulty = FMath::Clamp(S->Difficulty, 0, 2);

	// A fresh battle, then everything put back as it was.
	ASRPlayerController* PC = Cast<ASRPlayerController>(World->GetFirstPlayerController());
	if (PC) { PC->ResetForNewMatch(); }
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Battle || !Eco) { return false; }
	Battle->ResetBattle();
	Battle->RemoveAllUnits();

	// buildings: the level's own by name, the ones raised in the match spawned again
	TMap<FString, ASRBuilding*> LevelBuildings;
	for (ASRBuilding* B : Eco->GetBuildings()) { if (B && !B->IsRuntimeBuilt()) { LevelBuildings.Add(B->GetName(), B); } }
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	for (const FSRSavedBuilding& O : S->Buildings)
	{
		ASRBuilding* B = nullptr;
		if (!O.LevelName.IsEmpty())
		{
			B = LevelBuildings.FindRef(O.LevelName);
		}
		else
		{
			B = ASRBuilding::SpawnBuilding(World, O.Type, O.Team, O.Location, O.BuildProgress < 1.f);
			if (B && O.Type == ESRBuildingType::Mine && Grid)
			{
				const int32 Vein = Grid->FindFreeVein(B->GetFootprintCentre(), 400.f);
				if (Vein != INDEX_NONE) { Grid->ClaimVein(Vein, B); }
			}
		}
		if (B) { B->SetLevelForLoad(O.Level, O.UpgradeProgress); B->ApplySaved(O.Health, O.BuildProgress, O.bDestroyed, O.Queue, O.Rally); }
	}

	// troops
	TArray<TArray<ASRUnit*>> PlatoonMembers;
	PlatoonMembers.SetNum(9);
	for (const FSRSavedUnit& O : S->Units)
	{
		ASRUnit* U = Battle->SpawnUnit(O.Type, O.Team, O.Pos, O.Yaw, 0.f);
		if (!U) { continue; }
		U->SetHealthForLoad(O.Health);
		U->SetStance(O.Stance);
		U->SetHome(O.Home);
		if (O.Platoon >= 0 && O.Platoon < PlatoonMembers.Num() && O.Team == ESRTeam::Player) { PlatoonMembers[O.Platoon].Add(U); }
	}
	if (USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this))
	{
		Platoons->Reset();
		for (const FSRSavedPlatoon& P : S->Platoons)
		{
			if (!PlatoonMembers.IsValidIndex(P.Index) || PlatoonMembers[P.Index].Num() == 0) { continue; }
			Platoons->Assign(P.Index, PlatoonMembers[P.Index]);
			Platoons->RenamePlatoon(P.Index, P.Name);
			Platoons->SetFormation(P.Index, P.Formation);
			Platoons->SetStance(P.Index, P.Stance);
			if (P.bReceivesRecruits) { Platoons->SetRecruitTarget(P.Index); }
		}
	}

	for (int32 t = 0; t < 2; ++t)
	{
		Eco->SetStock(ESRTeam(t), ESRResource::Gold, S->Gold[t]);
		Eco->SetStock(ESRTeam(t), ESRResource::Food, S->Food[t]);
	}
	Battle->SetBattleClock(S->BattleClock);
	if (S->Stats.Num() == 8)
	{
		FSRMatchStats St;
		for (int32 t = 0; t < 2; ++t)
		{
			St.Recruited[t] = S->Stats[t * 4 + 0];
			St.TroopsLost[t] = S->Stats[t * 4 + 1];
			St.BuildingsBuilt[t] = S->Stats[t * 4 + 2];
			St.BuildingsLost[t] = S->Stats[t * 4 + 3];
		}
		Battle->SetStats(St);
	}
	if (USRAISubsystem* AI = USRAISubsystem::Get(this)) { AI->LoadState(S->Commanders, S->BattleClock); }
	if (USRFogSubsystem* Fog = USRFogSubsystem::Get(this)) { Fog->Reset(); Fog->SetExplored(S->FogExplored); }
	if (ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
	{
		Camera->FocusOn(S->CameraFocus, true);
		Camera->SetZoom(FMath::Max(USRFeelSettings::Get().ZoomDefault, 0.5f), true);
	}
	Battle->SetSimPaused(false);
	AutosaveClock = 0.f;
	SetState(ESRGameState::Playing);
	SaveMessage = TEXT("Game loaded.");
	SaveMessageTime = FPlatformTime::Seconds();
	UE_LOG(LogSovereign, Log, TEXT("LOAD %s: %d troops, %d buildings, %.0fs into the battle, difficulty %d"), *Slot, S->Units.Num(), S->Buildings.Num(), S->BattleClock, S->Difficulty);
	return true;
}
