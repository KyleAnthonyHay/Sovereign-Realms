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
#include "Battle/SRMapInfo.h"
#include "Misc/PackageName.h"
#include "PlatformFeatures.h"
#include "SaveGameSystem.h"

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
	if (bTravelling) { return; }   // this level is on its way out
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
	ForgetSaves();
	// Open over the player's kingdom; the controller then drifts the camera slowly (ASRPlayerController::ComputePanInput).
	if (ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
	{
		// the citadel sits right of centre, clear of the title and the menu on the left
		FVector2D Focus = USRFeelSettings::Get().PlayerStart;
		const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
		if (const ASRBuilding* Castle = Economy ? Economy->GetCastle(ESRTeam::Player) : nullptr) { Focus = Castle->GetFootprintCentre() + FVector2D(500.f, -900.f); }
		Camera->FocusOn(Focus, true);
		Camera->SetZoom(USRFeelSettings::Get().ZoomMainMenu, true);
	}
	SetState(ESRGameState::MainMenu);
}

// ------------------------------------------------------------------ maps

FName USRGameFlowSubsystem::GetCurrentMapId() const
{
	if (CurrentMapId.IsNone())
	{
		const ASRMapInfo* Info = ASRMapInfo::Get(this);
		CurrentMapId = (Info && !Info->MapId.IsNone()) ? Info->MapId : DefaultMapId();
	}
	return CurrentMapId;
}

bool USRGameFlowSubsystem::IsMapAvailable(FName Map) const
{
	if (Map == GetCurrentMapId()) { return true; }
	if (const bool* Known = MapAvailable.Find(Map)) { return *Known; }
	const FSRMapEntry* Entry = USRFeelSettings::Get().FindMap(Map);
	return MapAvailable.Add(Map, Entry && FPackageName::DoesPackageExist(Entry->Level));
}

FString USRGameFlowSubsystem::MapTitle(FName Map)
{
	const FSRMapEntry* Entry = USRFeelSettings::Get().FindMap(Map);
	if (!Entry || Entry->Name.IsEmpty()) { return Map.ToString(); }
	// the list's names are written for the menu's capitals ("THE RIVERLANDS"): in a sentence, "The Riverlands"
	FString Title = Entry->Name.ToLower();
	bool bStart = true;
	for (TCHAR& Ch : Title)
	{
		if (bStart) { Ch = FChar::ToUpper(Ch); }
		bStart = FChar::IsWhitespace(Ch);
	}
	return Title;
}

bool USRGameFlowSubsystem::TravelTo(const FSRMapEntry& Entry, const FString& Options)
{
	if (!FPackageName::DoesPackageExist(Entry.Level))
	{
		SaveMessage = FString::Printf(TEXT("%s is not in this game yet."), *MapTitle(Entry.Id));
		SaveMessageTime = FPlatformTime::Seconds();
		UE_LOG(LogSovereign, Warning, TEXT("MAP %s: no level %s (build it with the level builder)"), *Entry.Id.ToString(), *Entry.Level);
		return false;
	}
	UE_LOG(LogSovereign, Log, TEXT("MAP travel: %s -> %s (%s?%s)"), *GetCurrentMapId().ToString(), *Entry.Id.ToString(), *Entry.Level, *Options);
	bTravelling = true;
	UGameplayStatics::OpenLevel(this, FName(*Entry.Level), true, Options);
	return true;
}

void USRGameFlowSubsystem::StartMatch(int32 Difficulty, FName Map, bool bSandbox)
{
	UWorld* World = GetWorld();
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (bTravelling) { return; }
	if (Difficulty >= 0)
	{
		GetMutableDefault<USRFeelSettings>()->AIDifficulty = FMath::Clamp(Difficulty, 0, 2);
		USRUserSettings::Get()->CaptureAndSave();
	}
	// Another map: open its level; the match starts there (ASRGameMode::StartPlay reads the URL).
	if (!Map.IsNone() && Map != GetCurrentMapId())
	{
		const FSRMapEntry* Entry = F.FindMap(Map);
		if (!Entry) { UE_LOG(LogSovereign, Warning, TEXT("MATCH START: no map '%s' in Sovereign Feel > Maps; nothing started"), *Map.ToString()); return; }
		TravelTo(*Entry, FString::Printf(TEXT("%s=1?%s=%d%s"), StartOption(), DifficultyOption(), F.AIDifficulty, bSandbox ? *FString::Printf(TEXT("?%s=1"), SandboxOption()) : TEXT("")));
		return;
	}
	ASRPlayerController* PC = Cast<ASRPlayerController>(World->GetFirstPlayerController());
	if (PC) { PC->ResetForNewMatch(); }
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		Battle->ResetBattle();
		Battle->SetSimPaused(false);
	}
	ForgetSaves();   // a new match: nothing of it is saved yet
	AutosaveClock = 0.f;
	bSandboxMatch = bSandbox;
	if (bSandbox) { SetupSandbox(); }
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
		Camera->SetZoom(FMath::Max(F.ZoomDefault, F.ZoomMatchStart), true);   // wide enough to take in the castle and the troops
	}
	SetState(ESRGameState::Playing);
	UE_LOG(LogSovereign, Log, TEXT("MATCH START: difficulty %d, map %s"), F.AIDifficulty, *GetCurrentMapId().ToString());
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
	// (a save from the old terraced map stays in the list, but it is nothing to continue from)
	for (const FSRSaveInfo& Info : GetSaves()) { if (!Info.bOldMap) { return Info.Slot; } }
	return FString();
}

const TArray<FSRSaveInfo>& USRGameFlowSubsystem::GetSaves() const
{
	if (bSavesValid) { return SavesCache; }
	SavesCache.Reset();
	// every slot on disk this game made: its own saves (SR_Save, SR_Save_<time>) and the autosave
	TArray<FString> Names;
	if (ISaveGameSystem* System = IPlatformFeaturesModule::Get().GetSaveGameSystem()) { System->GetSaveGameNames(Names, 0); }
	for (const FString& Name : Names)
	{
		if (!Name.StartsWith(SavePrefix()) && Name != AutoSlot()) { continue; }
		const USRSaveGame* S = Cast<USRSaveGame>(UGameplayStatics::LoadGameFromSlot(Name, 0));
		if (!S) { continue; }
		FSRSaveInfo& Info = SavesCache.AddDefaulted_GetRef();
		Info.Slot = Name;
		Info.SavedAt = S->SavedAt;
		Info.bAuto = Name == AutoSlot();
		Info.bOldMap = S->IsFromOldMap();
		Info.Line = DescribeSave(Name);
	}
	SavesCache.Sort([](const FSRSaveInfo& A, const FSRSaveInfo& B) { return A.SavedAt > B.SavedAt; });
	bSavesValid = true;
	return SavesCache;
}

int32 USRGameFlowSubsystem::CountPlayerSaves() const
{
	int32 N = 0;
	for (const FSRSaveInfo& Info : GetSaves()) { N += Info.bAuto ? 0 : 1; }
	return N;
}

FString USRGameFlowSubsystem::SaveCurrentMatch()
{
	if (!ActiveSlot.IsEmpty() && HasSave(ActiveSlot)) { return SaveMatch(ActiveSlot) ? ActiveSlot : FString(); }
	return SaveNewMatch();
}

bool USRGameFlowSubsystem::IsMatchSaved() const
{
	const float Since = GetUnsavedTime();
	return Since >= 0.f && Since < 1.f;
}

float USRGameFlowSubsystem::GetUnsavedTime(bool* bOutAuto) const
{
	if (bOutAuto) { *bOutAuto = LastAutoClock > LastSaveClock; }
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const float Last = FMath::Max(LastSaveClock, LastAutoClock);
	return (Battle && Last >= 0.f) ? FMath::Max(Battle->GetBattleClock() - Last, 0.f) : -1.f;
}

FString USRGameFlowSubsystem::SaveNewMatch()
{
	if (!CanAddSave())
	{
		SaveMessage = FString::Printf(TEXT("All %d save slots are in use: overwrite one."), MaxPlayerSaves);
		SaveMessageTime = FPlatformTime::Seconds();
		return FString();
	}
	// a slot of its own, named by the moment (a second save in the same second gets a suffix)
	FString Slot = FString::Printf(TEXT("%s_%s"), SavePrefix(), *FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")));
	for (int32 n = 2; HasSave(Slot); ++n) { Slot = FString::Printf(TEXT("%s_%s_%d"), SavePrefix(), *FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")), n); }
	return SaveMatch(Slot) ? Slot : FString();
}

bool USRGameFlowSubsystem::DeleteSave(const FString& Slot)
{
	if (!Slot.StartsWith(SavePrefix()) && Slot != AutoSlot()) { return false; }
	const bool bOk = UGameplayStatics::DeleteGameInSlot(Slot, 0);
	if (bOk && Slot == ActiveSlot) { ActiveSlot.Reset(); LastSaveClock = -1.f; }   // this match's own save is gone
	if (bOk && Slot == AutoSlot()) { LastAutoClock = -1.f; }
	SaveLines.Remove(Slot);
	bSavesValid = false;
	SaveMessage = bOk ? TEXT("Saved game deleted.") : TEXT("Could not delete that saved game.");
	SaveMessageTime = FPlatformTime::Seconds();
	UE_LOG(LogSovereign, Log, TEXT("SAVE delete %s: %s"), *Slot, bOk ? TEXT("ok") : TEXT("FAILED"));
	return bOk;
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
			// (FDateTime::ToString has no month-name code: "%b" came out as a bare "b")
			static const TCHAR* Months[12] = { TEXT("Jan"), TEXT("Feb"), TEXT("Mar"), TEXT("Apr"), TEXT("May"), TEXT("Jun"), TEXT("Jul"), TEXT("Aug"), TEXT("Sep"), TEXT("Oct"), TEXT("Nov"), TEXT("Dec") };
			const FString When = FString::Printf(TEXT("%d %s %02d:%02d"), S->SavedAt.GetDay(), Months[FMath::Clamp(S->SavedAt.GetMonth() - 1, 0, 11)], S->SavedAt.GetHour(), S->SavedAt.GetMinute());
			// first the map it was played on; a save from the old terraced map cannot be loaded, and says so
			const FString Where = S->IsFromOldMap() ? FString(TEXT("Old map (cannot be loaded)")) : MapTitle(S->Map.IsNone() ? DefaultMapId() : S->Map);
			Line = FString::Printf(TEXT("%s  ·  %s  ·  %d:%02d into the battle  ·  %s"), *Where, *When, Sec / 60, Sec % 60, Names[FMath::Clamp(S->Difficulty, 0, 2)]);
		}
	}
	const_cast<USRGameFlowSubsystem*>(this)->SaveLines.Add(Slot, Line);
	return Line;
}

bool USRGameFlowSubsystem::SaveMatch(const FString& Slot)
{
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Battle || !Eco || Battle->GetResult() != ESRBattleResult::Ongoing || bTravelling) { return false; }
	USRSaveGame* S = Cast<USRSaveGame>(UGameplayStatics::CreateSaveGameObject(USRSaveGame::StaticClass()));
	S->SavedAt = FDateTime::Now();
	S->Map = GetCurrentMapId();
	S->Difficulty = USRFeelSettings::Get().AIDifficulty;
	S->BattleClock = Battle->GetBattleClock();
	for (int32 t = 0; t < 2; ++t)
	{
		S->Gold[t] = Eco->GetResource(ESRTeam(t), ESRResource::Gold);
		S->Food[t] = Eco->GetResource(ESRTeam(t), ESRResource::Food);
		S->ScoutCooldown[t] = Eco->GetScoutCooldown(ESRTeam(t));
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
		O.AssignedPlatoon = B->GetAssignedPlatoon();
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
			O.bFormation = P->bFormation;
			O.Stance = P->Stance;
			O.bReceivesRecruits = P->bReceivesRecruits;
		}
	}
	if (const USRAISubsystem* AI = USRAISubsystem::Get(this)) { AI->SaveState(S->Commanders); }
	if (const USRFogSubsystem* Fog = USRFogSubsystem::Get(this)) { Fog->GetExplored(S->FogExplored); }
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (const ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr) { S->CameraFocus = FVector2D(Camera->GetFocusPoint()); }

	const bool bOk = UGameplayStatics::SaveGameToSlot(S, Slot, 0);
	if (bOk)
	{
		if (Slot == AutoSlot()) { LastAutoClock = S->BattleClock; }
		else { LastSaveClock = S->BattleClock; ActiveSlot = Slot; }
	}
	SaveLines.Remove(Slot);
	bSavesValid = false;
	if (Slot != AutoSlot() || !bOk)
	{
		SaveMessage = bOk ? TEXT("Game saved.") : TEXT("Could not save the game.");
		SaveMessageTime = FPlatformTime::Seconds();
	}
	UE_LOG(LogSovereign, Log, TEXT("SAVE %s -> %s: %d troops, %d buildings, %.0fs"), bOk ? TEXT("ok") : TEXT("FAILED"), *Slot, S->Units.Num(), S->Buildings.Num(), S->BattleClock);
	return bOk;
}

bool USRGameFlowSubsystem::LoadMatch(const FString& Slot, bool bTravel)
{
	if (bTravelling) { return false; }
	USRSaveGame* S = HasSave(Slot) ? Cast<USRSaveGame>(UGameplayStatics::LoadGameFromSlot(Slot, 0)) : nullptr;
	if (!S || S->Version > USRSaveGame::CurrentVersion)
	{
		SaveMessage = TEXT("No saved game to load.");
		SaveMessageTime = FPlatformTime::Seconds();
		return false;
	}
	// From before the heightfield maps: its troops and buildings stand where there are hills now. It is kept (the
	// player may delete it), never loaded.
	if (S->IsFromOldMap())
	{
		SaveMessage = TEXT("That saved game is from the old map: it cannot be loaded.");
		SaveMessageTime = FPlatformTime::Seconds();
		UE_LOG(LogSovereign, Log, TEXT("LOAD %s refused: version %d, from the old map"), *Slot, S->Version);
		return false;
	}
	// Played on another map: open that map's level; the game is loaded there (ASRGameMode::StartPlay reads the URL).
	const FName SavedMap = S->Map.IsNone() ? DefaultMapId() : S->Map;
	if (SavedMap != GetCurrentMapId())
	{
		const FSRMapEntry* Entry = USRFeelSettings::Get().FindMap(SavedMap);
		if (bTravel && Entry && TravelTo(*Entry, FString::Printf(TEXT("%s=%s"), LoadOption(), *Slot))) { return true; }
		if (!Entry || !bTravel)
		{
			SaveMessage = TEXT("That saved game's map is not in this game.");
			SaveMessageTime = FPlatformTime::Seconds();
		}
		UE_LOG(LogSovereign, Warning, TEXT("LOAD %s refused: it was saved on map '%s', this is '%s'"), *Slot, *SavedMap.ToString(), *GetCurrentMapId().ToString());
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
			if (B && (O.Type == ESRBuildingType::RelicTower || O.Type == ESRBuildingType::Tower) && Grid)
			{
				const int32 Relic = Grid->FindFreeRelic(B->GetFootprintCentre(), 600.f, O.Type == ESRBuildingType::RelicTower);
				if (Relic != INDEX_NONE) { Grid->ClaimRelic(Relic, B); }
			}
		}
		if (B) { B->SetLevelForLoad(O.Level, O.UpgradeProgress); B->ApplySaved(O.Health, O.BuildProgress, O.bDestroyed, O.Queue, O.Rally); B->SetAssignedPlatoon(O.AssignedPlatoon); }
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
			Platoons->SetFormation(P.Index, P.Formation == ESRFormationShape::Loose ? ESRFormationShape::Line : P.Formation);
			Platoons->SetFormationOn(P.Index, P.bFormation);
			Platoons->SetStance(P.Index, P.Stance);
			if (P.bReceivesRecruits) { Platoons->SetRecruitTarget(P.Index); }
		}
	}

	for (int32 t = 0; t < 2; ++t)
	{
		Eco->SetStock(ESRTeam(t), ESRResource::Gold, S->Gold[t]);
		Eco->SetStock(ESRTeam(t), ESRResource::Food, S->Food[t]);
		Eco->SetScoutCooldown(ESRTeam(t), S->ScoutCooldown[t]);   // (0 in a save from before there were Scouts)
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
		Camera->SetZoom(FMath::Max(USRFeelSettings::Get().ZoomDefault, USRFeelSettings::Get().ZoomMatchStart), true);
	}
	Battle->SetSimPaused(false);
	AutosaveClock = 0.f;
	// the match on the field is the one in that saved game: nothing is unsaved until it is played on
	ForgetSaves();
	if (Slot == AutoSlot()) { LastAutoClock = S->BattleClock; }
	else { LastSaveClock = S->BattleClock; ActiveSlot = Slot; }
	SetState(ESRGameState::Playing);
	SaveMessage = TEXT("Game loaded.");
	SaveMessageTime = FPlatformTime::Seconds();
	UE_LOG(LogSovereign, Log, TEXT("LOAD %s: %d troops, %d buildings, %.0fs into the battle, difficulty %d"), *Slot, S->Units.Num(), S->Buildings.Num(), S->BattleClock, S->Difficulty);
	return true;
}

// ------------------------------------------------------------------ sandbox (testing)

void USRGameFlowSubsystem::SetupSandbox()
{
	UWorld* World = GetWorld();
	const USRFeelSettings& F = USRFeelSettings::Get();
	USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (!World || !Economy || !Battle || !Grid) { return; }

	// the enemy holds its ground: no commander building, recruiting or sending attacks (its troops still fight back)
	if (USRAISubsystem* AI = USRAISubsystem::Get(this)) { AI->SetEnemyCommander(false); }
	for (const ESRTeam Team : { ESRTeam::Player, ESRTeam::Enemy })
	{
		Economy->AddResource(Team, ESRResource::Gold, 20000, true);
		Economy->AddResource(Team, ESRResource::Food, 20000, true);
	}

	const ESRBuildingType Kinds[] = { ESRBuildingType::Farm, ESRBuildingType::Farm, ESRBuildingType::Barracks, ESRBuildingType::Range, ESRBuildingType::Stable,
		ESRBuildingType::Workshop, ESRBuildingType::Granary, ESRBuildingType::Treasury, ESRBuildingType::Tower, ESRBuildingType::Tower, ESRBuildingType::SiegeTower };
	int32 Placed = 0, Spawned = 0;
	for (const ESRTeam Team : { ESRTeam::Player, ESRTeam::Enemy })
	{
		ASRBuilding* Castle = Economy->GetCastle(Team);
		if (!Castle) { continue; }
		Castle->SetLevelNow(4);
		const FVector2D C = Castle->GetFootprintCentre();
		const FVector2D ToMiddle = (-C).GetSafeNormal();
		int32 k = 0;
		for (const ESRBuildingType Kind : Kinds)
		{
			// the first free spot on rings round the castle, starting on the side away from the field
			bool bDone = false;
			for (float R = 1700.f; R <= 3800.f && !bDone; R += 300.f)
			{
				for (int32 a = 0; a < 18 && !bDone; ++a)
				{
					const float Ang = FMath::DegreesToRadians(180.f + (k * 47 + a * 20) % 360);
					const FVector2D Want = C + ToMiddle.GetRotated(FMath::RadiansToDegrees(Ang)) * R;
					const FSRPlacement P = Grid->CheckPlacement(Kind, Team, Want);
					if (!P.bValid) { continue; }
					if (ASRBuilding* B = ASRBuilding::SpawnBuilding(World, Kind, Team, P.Location, false))
					{
						if (Kind != ESRBuildingType::SiegeTower) { B->SetLevelNow(1 + (k % 3)); }
						++Placed;
						bDone = true;
					}
				}
			}
			++k;
		}

		// an army of every kind drawn up toward the field: rows of shields, bows, riders, catapults, medics and a scout
		struct FRow { ESRUnitType Type; int32 Count; };
		const FRow Rows[] = { { ESRUnitType::Shieldbearer, 10 }, { ESRUnitType::Archer, 10 }, { ESRUnitType::Horseman, 6 }, { ESRUnitType::Catapult, 4 },
			{ ESRUnitType::Medic, 3 }, { ESRUnitType::Scout, 1 }, { ESRUnitType::Builder, 3 } };
		const FVector2D Front = C + ToMiddle * 3200.f;
		const FVector2D Side(-ToMiddle.Y, ToMiddle.X);
		const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(ToMiddle.Y, ToMiddle.X));
		float Back = 0.f;
		for (const FRow& Row : Rows)
		{
			const float Gap = Row.Type == ESRUnitType::Catapult ? 360.f : (Row.Type == ESRUnitType::Horseman ? 200.f : 130.f);
			for (int32 i = 0; i < Row.Count; ++i)
			{
				const FVector2D Want = Front - ToMiddle * Back + Side * ((i - (Row.Count - 1) * 0.5f) * Gap);
				if (Battle->SpawnUnit(Row.Type, Team, Grid->NearestWalkable(Want, 12, &C), Yaw, 0.f)) { ++Spawned; }
			}
			Back += Row.Type == ESRUnitType::Catapult ? 400.f : 220.f;
		}
	}
	UE_LOG(LogSovereign, Log, TEXT("SANDBOX: %d buildings and %d troops placed; enemy commander off"), Placed, Spawned);
}
