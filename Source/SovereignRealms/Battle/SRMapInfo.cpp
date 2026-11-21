// Copyright Sovereign Realms.

#include "Battle/SRMapInfo.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"
#include "Engine/Texture2D.h"
#include "EngineUtils.h"

const ASRMapInfo* ASRMapInfo::Get(const UObject* WorldContext)
{
	UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (!World) { return nullptr; }
	const TActorIterator<ASRMapInfo> It(World);   // (one per level: the first is the one)
	return It ? *It : nullptr;
}

void ASRMapInfo::ApplyToSettings(UWorld* World)
{
	const ASRMapInfo* Info = Get(World);
	if (!Info)
	{
		UE_LOG(LogSovereign, Log, TEXT("MAP: this level has no ASRMapInfo; the Sovereign Feel settings stand as they are"));
		return;
	}
	// (the settings object is the one every reader already asks, live; the difficulty is set on it the same way)
	USRFeelSettings* F = GetMutableDefault<USRFeelSettings>();
	F->MapHalfExtent = Info->HalfExtent;
	F->PlayerStart = Info->PlayerStart;
	F->EnemyStart = Info->EnemyStart;
	F->FocusHeightMax = Info->FocusHeightMax;
	UE_LOG(LogSovereign, Log, TEXT("MAP %s (%s): half extent (%.0f, %.0f), player start (%.0f, %.0f), enemy start (%.0f, %.0f), focus up to %.0f, ground traces %.0f to %.0f"),
		*Info->MapId.ToString(), *Info->DisplayName, Info->HalfExtent.X, Info->HalfExtent.Y, Info->PlayerStart.X, Info->PlayerStart.Y,
		Info->EnemyStart.X, Info->EnemyStart.Y, Info->FocusHeightMax, Info->GroundTraceTop, Info->GroundTraceBottom);
}
