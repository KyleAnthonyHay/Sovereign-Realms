#include "VLMatchLog.h"
#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLEnemyAI.h"
#include "VLKing.h"
#include "VLTroop.h"
#include "VLGrid.h"
#include "VLConstruction.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"

namespace
{
	TAutoConsoleVariable<int32> CVarMatchLog(TEXT("vl.MatchLog"), 0,
		TEXT("1: log the match for balance (Saved/Balance/<id>.json, <id>_series.csv, matches.csv): stock, income, troops, buildings, attacks, the result"));
	TAutoConsoleVariable<float> CVarMaxMinutes(TEXT("vl.MatchLog.MaxMinutes"), 0.f,
		TEXT("> 0: a logged match that has gone on this many minutes of its clock ends there as a draw (the files written)"));
	TAutoConsoleVariable<int32> CVarQuit(TEXT("vl.MatchLog.Quit"), 0,
		TEXT("1: once the log is written, quit the game (a -game run, as Tools/aivsai.py starts; never the editor)"));

	FString Esc(const FString& S)
	{
		return S.Replace(TEXT("\\"), TEXT("\\\\")).Replace(TEXT("\""), TEXT("\\\""));
	}

	const TCHAR* KindName(uint8 K)
	{
		return VLRules::Name(EVLBuilding(K));
	}

	// the kinds of building counted per side, in the columns' order
	const EVLBuilding Counted[] = { EVLBuilding::Farm, EVLBuilding::Mine, EVLBuilding::Barracks, EVLBuilding::Range, EVLBuilding::Tower, EVLBuilding::Granary, EVLBuilding::Treasury };
	const TCHAR* CountedCol[] = { TEXT("farms"), TEXT("mines"), TEXT("barracks"), TEXT("ranges"), TEXT("towers"), TEXT("granaries"), TEXT("treasuries") };
}

FString FVLMatchLog::Tag;

bool FVLMatchLog::Wanted()
{
	return CVarMatchLog.GetValueOnGameThread() != 0;
}

void FVLMatchLog::Begin(UVLBattle* B)
{
	bBegun = true;
	MapName = B->GetWorld() ? B->GetWorld()->GetMapName() : FString();
	MapName.RemoveFromStart(B->GetWorld() ? B->GetWorld()->StreamingLevelsPrefix : FString());
	for (int32 t = 0; t < 2; ++t)
	{
		const FVLCommander* C = B->GetCommander(t);
		bAI[t] = C && C->bActive;
		Difficulty[t] = bAI[t] ? C->Difficulty : -1;
	}
	auto D = [](int32 X) { return X < 0 ? FString(TEXT("Human")) : FString(UVLBattle::DifficultyName(X)); };
	Id = FString::Printf(TEXT("%s_%s_%sv%s%s"), *FDateTime::Now().ToString(TEXT("%Y%m%d-%H%M%S")), *MapName, *D(Difficulty[0]), *D(Difficulty[1]),
		Tag.IsEmpty() ? TEXT("") : *(TEXT("_") + Tag));
	UE_LOG(LogSovereignRealms, Log, TEXT("match log: %s (team 0 %s, team 1 %s)"), *Id, *D(Difficulty[0]), *D(Difficulty[1]));
}

void FVLMatchLog::Event(int32 Team, const TCHAR* Type, const FString& What, const FString& Detail)
{
	EventJson.Add(FString::Printf(TEXT("{\"t\":%.1f,\"team\":%d,\"type\":\"%s\",\"what\":\"%s\",\"detail\":\"%s\"}"), Clock, Team, Type, *Esc(What), *Esc(Detail)));
}

void FVLMatchLog::Watch(UVLBattle* B)
{
	// buildings: laid, finished, raised, claimed, lost
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		AActor* A = S.Actor.Get();
		if (!A || S.Kind == EVLBuilding::None || S.Kind == EVLBuilding::Hall)
		{
			continue;
		}
		const bool bDead = !S.IsAlive();
		FSeen* Was = Buildings.Find(A);
		if (!Was)
		{
			FSeen N;
			N.Team = S.Team; N.Level = S.Level; N.bSite = S.IsSite(); N.bDead = bDead; N.Name = S.Name; N.Kind = uint8(S.Kind);
			Buildings.Add(A, N);
			if (bBegun && S.IsSite() && (S.Team == 0 || S.Team == 1))
			{
				Event(S.Team, TEXT("site"), KindName(N.Kind), S.Name);
			}
			continue;
		}
		if (Was->Team != S.Team && (S.Team == 0 || S.Team == 1))
		{
			Event(S.Team, S.IsSite() ? TEXT("claim") : TEXT("captured"), KindName(Was->Kind), S.Name);
			Was->Team = S.Team;
		}
		if (Was->bSite && !S.IsSite() && !bDead)
		{
			Event(S.Team, TEXT("built"), KindName(Was->Kind), S.Name);
		}
		if (S.Level > Was->Level && !bDead)
		{
			Event(S.Team, TEXT("level"), KindName(Was->Kind), FString::Printf(TEXT("%s to level %d"), *S.Name, S.Level));
		}
		if (bDead && !Was->bDead)
		{
			Event(Was->Team, Was->bSite ? TEXT("site_lost") : TEXT("lost"), KindName(Was->Kind), S.Name);
		}
		Was->bSite = S.IsSite();
		Was->Level = S.Level;
		Was->bDead = bDead;
		Was->Team = S.Team;
	}
	// attacks and raids: sent, and back
	for (int32 t = 0; t < 2; ++t)
	{
		const FVLCommander* C = B->GetCommander(t);
		if (!C || !C->bActive)
		{
			continue;
		}
		TSet<uint64> Now;
		for (const FVLSquad& S : C->Squads)
		{
			if (!S.IsOut() || (S.Role != EVLSquadRole::Field && S.Role != EVLSquadRole::Flank && S.Role != EVLSquadRole::Raid))
			{
				continue;
			}
			const uint64 Key = (uint64(t) << 32) | uint32(S.Id);
			Now.Add(Key);
			if (!Out.Contains(Key))
			{
				FOut O;
				O.Team = t;
				O.bRaid = S.Role == EVLSquadRole::Raid;
				O.Start = Clock;
				O.Size = FMath::Max(S.StartSize, S.Num());
				O.Target = S.GoalName;
				Out.Add(Key, O);
				if (O.bRaid) { ++Raids[t]; } else { ++Attacks[t]; }
				if (!O.bRaid && FirstAttackAt[t] < 0) { FirstAttackAt[t] = FMath::RoundToInt(Clock); }
				Event(t, O.bRaid ? TEXT("raid") : (S.Role == EVLSquadRole::Flank ? TEXT("flank") : TEXT("attack")), O.Target, FString::Printf(TEXT("%d troops"), O.Size));
			}
		}
		for (auto It = Out.CreateIterator(); It; ++It)
		{
			if (It.Value().Team != t || Now.Contains(It.Key()))
			{
				continue;
			}
			int32 Back = 0;
			const uint32 SquadId = uint32(It.Key() & 0xffffffffu);
			for (const FVLSquad& S : C->Squads)
			{
				if (uint32(S.Id) == SquadId)
				{
					Back = S.Num();
				}
			}
			Event(t, It.Value().bRaid ? TEXT("raid_end") : TEXT("attack_end"), It.Value().Target,
				FString::Printf(TEXT("%d of %d back after %.0f s"), Back, It.Value().Size, Clock - It.Value().Start));
			It.RemoveCurrent();
		}
	}
}

void FVLMatchLog::Sample(UVLBattle* B)
{
	FString Teams;
	for (int32 t = 0; t < 2; ++t)
	{
		const FVLKingdom& K = B->GetKingdom(t);
		TArray<AVLKing*> Units;
		B->GetUnits(t, Units, true);
		int32 Alive[6] = { 0, 0, 0, 0, 0, 0 };
		for (const AVLKing* U : Units)
		{
			++Alive[FMath::Min(int32(U->KindId()), 5)];
		}
		int32 Count[UE_ARRAY_COUNT(Counted)] = {};
		int32 Sites = 0;
		float Hp = 0.f;
		for (const FVLBuildingState& S : B->GetBuildings())
		{
			if (S.Team != t || !S.IsAlive())
			{
				continue;
			}
			Hp += S.Health;
			if (S.IsSite())
			{
				++Sites;
				continue;
			}
			for (int32 i = 0; i < UE_ARRAY_COUNT(Counted); ++i)
			{
				Count[i] += S.Kind == Counted[i] ? 1 : 0;
			}
		}
		const FVLCommander* C = B->GetCommander(t);
		const bool bCmd = C && C->bActive;
		const FString Posture = bCmd ? FVLCommander::PostureName(C->Posture) : TEXT("-");
		const float Power = bCmd ? C->ArmyPower : 0.f;
		const int32 Sw = int32(EVLUnitKind::Swordsman), Ar = int32(EVLUnitKind::Archer), Bu = int32(EVLUnitKind::Builder), Sp = int32(EVLUnitKind::Spy);
		// the CSV row
		FString Row = FString::Printf(TEXT("%.0f,%d,%d,%d,%d,%d,%.0f,%.0f,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d"),
			Clock, t, K.Gold, K.Food, B->GetStorage(t, EVLRes::Gold), B->GetStorage(t, EVLRes::Food), B->GetIncomePerMinute(t, EVLRes::Gold), B->GetIncomePerMinute(t, EVLRes::Food),
			K.Earned[0], K.Earned[1], K.Wasted[0], K.Wasted[1], K.Spent[0], K.Spent[1],
			B->GetPopulation(t), B->GetQueuedPopulation(t), B->GetPopulationCap(t), B->GetCastleLevel(t),
			Alive[Sw], Alive[Ar], Alive[Bu], Alive[Sp], K.RecruitedKind[Sw], K.RecruitedKind[Ar], K.RecruitedKind[Bu], K.RecruitedKind[Sp],
			K.LostKind[Sw], K.LostKind[Ar], K.LostKind[Bu], K.Killed, K.BuildingsLost);
		for (int32 i = 0; i < UE_ARRAY_COUNT(Counted); ++i)
		{
			Row += FString::Printf(TEXT(",%d"), Count[i]);
		}
		Row += FString::Printf(TEXT(",%d,%.0f,%.2f,%s,%d,%d"), Sites, Hp, Power, *Posture, Attacks[t], Raids[t]);
		SeriesRows.Add(Row);
		// the JSON object
		FString Blds;
		for (int32 i = 0; i < UE_ARRAY_COUNT(Counted); ++i)
		{
			Blds += FString::Printf(TEXT("%s\"%s\":%d"), i ? TEXT(",") : TEXT(""), CountedCol[i], Count[i]);
		}
		Teams += FString::Printf(TEXT("%s{\"team\":%d,\"gold\":%d,\"food\":%d,\"gold_cap\":%d,\"food_cap\":%d,\"gold_min\":%.0f,\"food_min\":%.0f,")
			TEXT("\"earned\":[%d,%d],\"wasted\":[%d,%d],\"spent\":[%d,%d],\"pop\":%d,\"queued\":%d,\"pop_cap\":%d,\"castle\":%d,")
			TEXT("\"alive\":{\"swordsman\":%d,\"archer\":%d,\"builder\":%d,\"spy\":%d},\"trained\":{\"swordsman\":%d,\"archer\":%d,\"builder\":%d,\"spy\":%d},")
			TEXT("\"lost\":{\"swordsman\":%d,\"archer\":%d,\"builder\":%d,\"spy\":%d},\"killed\":%d,\"buildings_lost\":%d,\"buildings\":{%s},\"sites\":%d,\"building_hp\":%.0f,")
			TEXT("\"power\":%.2f,\"posture\":\"%s\",\"attacks\":%d,\"raids\":%d}"),
			t ? TEXT(",") : TEXT(""), t, K.Gold, K.Food, B->GetStorage(t, EVLRes::Gold), B->GetStorage(t, EVLRes::Food), B->GetIncomePerMinute(t, EVLRes::Gold), B->GetIncomePerMinute(t, EVLRes::Food),
			K.Earned[0], K.Earned[1], K.Wasted[0], K.Wasted[1], K.Spent[0], K.Spent[1], B->GetPopulation(t), B->GetQueuedPopulation(t), B->GetPopulationCap(t), B->GetCastleLevel(t),
			Alive[Sw], Alive[Ar], Alive[Bu], Alive[Sp], K.RecruitedKind[Sw], K.RecruitedKind[Ar], K.RecruitedKind[Bu], K.RecruitedKind[Sp],
			K.LostKind[Sw], K.LostKind[Ar], K.LostKind[Bu], K.LostKind[Sp], K.Killed, K.BuildingsLost, *Blds, Sites, Hp, Power, *Posture, Attacks[t], Raids[t]);
	}
	SampleJson.Add(FString::Printf(TEXT("{\"t\":%.0f,\"teams\":[%s]}"), Clock, *Teams));
}

void FVLMatchLog::Tick(UVLBattle* B, float Dt)
{
	if (bFinished || !B || !B->IsBattle())
	{
		return;
	}
	Clock = B->GetClock();
	if (!bBegun)
	{
		Begin(B);
		Watch(B);           // (what the map and the start have: not events)
		Sample(B);
		NextSample = Clock + SampleEvery;
		NextWatch = Clock + 1.f;
		return;
	}
	if (B->GetState() == EVLMatch::Ended)
	{
		Watch(B);
		Sample(B);
		Finish(B, TEXT("castle"));
		return;
	}
	if (Clock >= NextWatch)
	{
		NextWatch = Clock + 1.f;
		Watch(B);
	}
	if (Clock >= NextSample)
	{
		NextSample = Clock + SampleEvery;
		Sample(B);
	}
	const float MaxMinutes = CVarMaxMinutes.GetValueOnGameThread();
	if (MaxMinutes > 0.f && Clock >= MaxMinutes * 60.f)
	{
		Watch(B);
		Sample(B);
		Finish(B, TEXT("time"));
	}
}

void FVLMatchLog::Finish(UVLBattle* B, const FString& Reason)
{
	if (bFinished || !bBegun)
	{
		return;
	}
	bFinished = true;
	const int32 Winner = Reason == TEXT("castle") ? B->GetWinner() : -1;
	const FString Dir = FPaths::ProjectSavedDir() / TEXT("Balance");
	IFileManager::Get().MakeDirectory(*Dir, true);
	auto D = [](int32 X) { return X < 0 ? FString(TEXT("Human")) : FString(UVLBattle::DifficultyName(X)); };
	// the result, with each side's end
	FString Final;
	for (int32 t = 0; t < 2; ++t)
	{
		const FVLKingdom& K = B->GetKingdom(t);
		const int32 Sw = int32(EVLUnitKind::Swordsman), Ar = int32(EVLUnitKind::Archer);
		auto Arr = [](const auto* V) { FString O; for (int32 i = 0; i < 8; ++i) { O += FString::Printf(TEXT("%s%.0f"), i ? TEXT(",") : TEXT(""), float(V[i])); } return O; };
		Final += FString::Printf(TEXT("%s{\"team\":%d,\"damage_by\":[%s],\"building_damage_by\":[%s],\"kills_by\":[%s],"), t ? TEXT(",") : TEXT(""), t, *Arr(K.DamageBy), *Arr(K.BuildingDamageBy), *Arr(K.KillsBy));
		Final += FString::Printf(TEXT("%s\"recruited\":%d,\"lost\":%d,\"killed\":%d,\"buildings_lost\":%d,\"trained_swordsmen\":%d,\"trained_archers\":%d,\"lost_swordsmen\":%d,\"lost_archers\":%d,\"attacks\":%d,\"raids\":%d,\"first_attack\":%d}"),
			TEXT(""), K.Recruited, K.Lost, K.Killed, K.BuildingsLost, K.RecruitedKind[Sw], K.RecruitedKind[Ar], K.LostKind[Sw], K.LostKind[Ar], Attacks[t], Raids[t], FirstAttackAt[t]);
	}
	const FString Json = FString::Printf(TEXT("{\"id\":\"%s\",\"map\":\"%s\",\"tag\":\"%s\",\"difficulty\":[\"%s\",\"%s\"],\"winner\":%d,\"reason\":\"%s\",\"duration\":%.0f,")
		TEXT("\"final\":[%s],\n\"events\":[\n%s\n],\n\"samples\":[\n%s\n]}\n"),
		*Id, *MapName, *Esc(Tag), *D(Difficulty[0]), *D(Difficulty[1]), Winner, *Reason, Clock, *Final, *FString::Join(EventJson, TEXT(",\n")), *FString::Join(SampleJson, TEXT(",\n")));
	FFileHelper::SaveStringToFile(Json, *(Dir / (Id + TEXT(".json"))));
	FString Header = TEXT("t,team,gold,food,gold_cap,food_cap,gold_min,food_min,earned_gold,earned_food,wasted_gold,wasted_food,spent_gold,spent_food,pop,queued,pop_cap,castle,")
		TEXT("swordsmen,archers,builders,spies,trained_swordsmen,trained_archers,trained_builders,trained_spies,lost_swordsmen,lost_archers,lost_builders,killed,buildings_lost");
	for (const TCHAR* Col : CountedCol)
	{
		Header += FString(TEXT(",")) + Col;
	}
	Header += TEXT(",sites,building_hp,power,posture,attacks,raids");
	FFileHelper::SaveStringToFile(Header + TEXT("\n") + FString::Join(SeriesRows, TEXT("\n")) + TEXT("\n"), *(Dir / (Id + TEXT("_series.csv"))));
	const FString Summary = Dir / TEXT("matches.csv");
	const bool bNew = !IFileManager::Get().FileExists(*Summary);
	const FVLKingdom& K0 = B->GetKingdom(0);
	const FVLKingdom& K1 = B->GetKingdom(1);
	const FString Line = FString::Printf(TEXT("%s%s,%s,%s,%s,%s,%d,%s,%.0f,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n"),
		bNew ? TEXT("id,map,tag,team0,team1,winner,reason,duration,recruited0,lost0,buildings_lost0,attacks0,first_attack0,recruited1,lost1,buildings_lost1,attacks1,first_attack1\n") : TEXT(""),
		*Id, *MapName, *Tag, *D(Difficulty[0]), *D(Difficulty[1]), Winner, *Reason, Clock, K0.Recruited, K0.Lost, K0.BuildingsLost, Attacks[0], FirstAttackAt[0],
		K1.Recruited, K1.Lost, K1.BuildingsLost, Attacks[1], FirstAttackAt[1]);
	FFileHelper::SaveStringToFile(Line, *Summary, FFileHelper::EEncodingOptions::AutoDetect, &IFileManager::Get(), FILEWRITE_Append);
	UE_LOG(LogSovereignRealms, Log, TEXT("match log written: %s (winner %d, %s, %.0f s)"), *(Dir / (Id + TEXT(".json"))), Winner, *Reason, Clock);
	if (CVarQuit.GetValueOnGameThread() != 0 && !GIsEditor)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("match log: quitting"));
		FPlatformMisc::RequestExit(false);
	}
}

// ------------------------------------------------------------------------------------------------ duels

namespace
{
	struct FDuel
	{
		int32 N[2][2] = { { 0, 0 }, { 0, 0 } };     // [side][0 swordsmen, 1 archers]
		float Max = 120.f;
		int32 TowerLevel = 0;                       // > 0: team 1 is a watch tower of this level (and N[1])
	};
	TArray<FDuel> GDuels;
	struct FDuelNow
	{
		bool bOn = false;
		FDuel D;
		float Clock = 0.f;
		float Pause = 0.f;
		TArray<TWeakObjectPtr<AVLKing>> Units[2];
		TWeakObjectPtr<AActor> Tower;
	} GNow;

	FString Body(const int32* N) { return FString::Printf(TEXT("%ds+%da"), N[0], N[1]); }
}

bool FVLDuels::bQuit = false;
FVector FVLDuels::Where = FVector::ZeroVector;

void FVLDuels::Queue(int32 S0, int32 A0, int32 S1, int32 A1, int32 Repeats, float Seconds)
{
	for (int32 r = 0; r < Repeats; ++r)
	{
		FDuel D;
		const bool bSwap = r % 2 == 1;
		D.N[bSwap ? 1 : 0][0] = S0; D.N[bSwap ? 1 : 0][1] = A0;
		D.N[bSwap ? 0 : 1][0] = S1; D.N[bSwap ? 0 : 1][1] = A1;
		D.Max = Seconds;
		GDuels.Add(D);
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("duel: %d queued"), GDuels.Num());
}

void FVLDuels::QueueTower(int32 Level, int32 S0, int32 A0, int32 Repeats, float Seconds)
{
	for (int32 r = 0; r < Repeats; ++r)
	{
		FDuel D;
		D.N[0][0] = S0; D.N[0][1] = A0;
		D.TowerLevel = FMath::Clamp(Level, 1, 3);
		D.Max = Seconds;
		GDuels.Add(D);
	}
}

void FVLDuels::QueueStandard()
{
	// food: a swordsman 100, an archer 85 (VLRules::Troop). Equal food a side, about 1000 / 2000.
	Queue(10, 0, 0, 12, 4);         // 1000 against 1020: swords against bows
	Queue(20, 0, 0, 24, 4);         // 2000 against 2040
	Queue(6, 5, 10, 0, 4);          // 1025 against 1000: a mixed body against swords
	Queue(6, 5, 0, 12, 4);          // 1025 against 1020: a mixed body against bows
	Queue(12, 10, 20, 0, 4);        // 2050 against 2000
	Queue(12, 10, 0, 24, 4);        // 2050 against 2040
	Queue(10, 0, 10, 0, 2);         // the mirror (both sides alike: the ground's own bias)
	Queue(0, 12, 0, 12, 2);
}

void FVLDuels::Tick(UVLBattle* B, float Dt)
{
	if (!B || (!GNow.bOn && GDuels.Num() == 0))
	{
		return;
	}
	if (GNow.Pause > 0.f)
	{
		GNow.Pause -= Dt;
		return;
	}
	UWorld* World = B->GetWorld();
	if (!GNow.bOn)
	{
		if (GDuels.Num() == 0)
		{
			return;
		}
		for (int32 t = 0; t < 2; ++t)
		{
			if (FVLCommander* C = B->GetCommander(t))
			{
				C->bActive = false;         // (nobody's orders: the troops fight by themselves)
			}
		}
		GNow.D = GDuels[0];
		GDuels.RemoveAt(0);
		GNow.bOn = true;
		GNow.Clock = 0.f;
		UVLGrid* Grid = UVLGrid::Get(World);
		const bool bGrid = Grid && Grid->EnsureBuilt();
		GNow.Tower.Reset();
		if (GNow.D.TowerLevel > 0)
		{
			UVLConstruction* Construction = UVLConstruction::Get(B);
			FVLPlacement P;
			B->AddStock(1, EVLRes::Gold, 1000, true);
			// (a Builder of its own on the spot: the side's own may have fallen at an earlier duel's tower)
			AVLTroop* Mason = B->SpawnTroop(TEXT("Builder"), 1, Where + FVector(3000.f, 0.f, 0.f), 0.f);
			FString Why;
			if (Construction && Construction->FindPlacementNear(EVLBuilding::Tower, 1, Where + FVector(1200.f, 0.f, 0.f), 2500.f, 90.f, P, 200))
			{
				TArray<AVLKing*> Crew;
				if (Mason) { Crew.Add(Mason); }
				AActor* T = Construction->PlaceBuilding(P, Crew, &Why, true);
				if (T && Construction->FinishNow(T))
				{
					if (FVLBuildingState* S = B->FindBuilding(T))
					{
						S->Level = GNow.D.TowerLevel;
						B->ApplyLevel(*S, true);
					}
					GNow.Tower = T;
				}
			}
			if (Mason && Mason->IsAlive())
			{
				Mason->Destroy();
			}
			if (!GNow.Tower.IsValid())
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("duel: no room for the tower (%s)"), *Why);
				GNow.bOn = false;
				return;
			}
		}
		for (int32 t = 0; t < 2; ++t)
		{
			GNow.Units[t].Reset();
			const FVector Mid = Where + FVector(t == 0 ? -1800.f : 1800.f, 0.f, 0.f);
			int32 i = 0;
			for (int32 k = 0; k < 2; ++k)
			{
				for (int32 n = 0; n < GNow.D.N[t][k]; ++n, ++i)
				{
					// rows of six across the line between them, archers behind the swords
					const float Back = (t == 0 ? -1.f : 1.f) * (k == 1 ? (GNow.D.N[t][0] > 0 ? 400.f : 0.f) + (n / 6) * 150.f : (n / 6) * 150.f);
					FVector P(Mid.X + Back, Mid.Y + ((n % 6) - 2.5f) * 150.f, Mid.Z + 50000.f);
					if (bGrid)
					{
						const int32 Node = Grid->NearestNode(P, 20, Grid->MainRegion());
						if (Node != INDEX_NONE)
						{
							P = Grid->NodePos(Node);
						}
					}
					if (AVLTroop* T = B->SpawnTroop(k == 0 ? TEXT("Swordsman") : TEXT("Archer"), t, P, t == 0 ? 0.f : 180.f))
					{
						GNow.Units[t].Add(T);
					}
				}
			}
		}
		return;
	}
	GNow.Clock += Dt;
	int32 Alive[2][2] = { { 0, 0 }, { 0, 0 } };
	float Hp[2] = { 0.f, 0.f };
	for (int32 t = 0; t < 2; ++t)
	{
		for (const TWeakObjectPtr<AVLKing>& U : GNow.Units[t])
		{
			if (U.IsValid() && U->IsAlive())
			{
				++Alive[t][U->IsRanged() ? 1 : 0];
				Hp[t] += U->GetHealth();
			}
		}
	}
	const FVLBuildingState* TS = GNow.Tower.IsValid() ? B->FindBuilding(GNow.Tower.Get()) : nullptr;
	const bool bTowerUp = TS && TS->IsAlive();
	if (GNow.D.TowerLevel > 0)
	{
		Hp[1] += bTowerUp ? TS->Health : 0.f;
	}
	const bool bDone0 = Alive[0][0] + Alive[0][1] == 0, bDone1 = Alive[1][0] + Alive[1][1] == 0 && !bTowerUp;
	if (!bDone0 && !bDone1 && GNow.Clock < GNow.D.Max)
	{
		return;
	}
	const int32 Winner = bDone0 && bDone1 ? -1 : (bDone1 ? 0 : (bDone0 ? 1 : (Hp[0] > Hp[1] ? 0 : 1)));
	const FString Side1 = GNow.D.TowerLevel > 0 ? FString::Printf(TEXT("tower%d"), GNow.D.TowerLevel) : Body(GNow.D.N[1]);
	const FString Line = FString::Printf(TEXT("%s,%s,%d,%s,%.1f,%d,%d,%.0f,%d,%d,%.0f"), *Body(GNow.D.N[0]), *Side1, Winner, (bDone0 || bDone1) ? TEXT("wiped") : TEXT("time"), GNow.Clock,
		Alive[0][0], Alive[0][1], Hp[0], Alive[1][0], Alive[1][1], Hp[1]);
	UE_LOG(LogSovereignRealms, Log, TEXT("duel: team 0 %s against team 1 %s: %s in %.0f s; left team 0 %ds+%da (%.0f hp), team 1 %ds+%da (%.0f hp)"), *Body(GNow.D.N[0]), *Side1,
		Winner < 0 ? TEXT("both fall") : (Winner == 0 ? TEXT("team 0 wins") : TEXT("team 1 wins")), GNow.Clock, Alive[0][0], Alive[0][1], Hp[0], Alive[1][0], Alive[1][1], Hp[1]);
	const FString Dir = FPaths::ProjectSavedDir() / TEXT("Balance");
	IFileManager::Get().MakeDirectory(*Dir, true);
	const FString Csv = Dir / TEXT("duels.csv");
	const bool bNew = !IFileManager::Get().FileExists(*Csv);
	FFileHelper::SaveStringToFile((bNew ? FString(TEXT("tag,team0,team1,winner,end,seconds,left0_s,left0_a,hp0,left1_s,left1_a,hp1\n")) : FString()) + FVLMatchLog::Tag + TEXT(",") + Line + TEXT("\n"),
		*Csv, FFileHelper::EEncodingOptions::AutoDetect, &IFileManager::Get(), FILEWRITE_Append);
	for (int32 t = 0; t < 2; ++t)
	{
		for (const TWeakObjectPtr<AVLKing>& U : GNow.Units[t])
		{
			if (U.IsValid() && U->IsAlive())
			{
				B->Damage(U.Get(), 1e6f, nullptr, 1 - t);
			}
		}
		GNow.Units[t].Reset();
	}
	if (bTowerUp)
	{
		B->Raze(GNow.Tower.Get());
	}
	GNow.Tower.Reset();
	GNow.bOn = false;
	GNow.Pause = 4.f;           // (the fallen are gone before the next)
	if (GDuels.Num() == 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("duel: all done"));
		if (bQuit && !GIsEditor)
		{
			FPlatformMisc::RequestExit(false);
		}
	}
}

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdDuel(TEXT("vl.Duel"), TEXT("vl.Duel S0 A0 S1 A1 [repeats] [seconds] | standard | at X Y | quit: troops of each side fight it out by themselves (balance; Saved/Balance/duels.csv)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() >= 1 && Args[0] == TEXT("standard"))
			{
				FVLDuels::QueueStandard();
			}
			else if (Args.Num() >= 3 && Args[0] == TEXT("at"))
			{
				FVLDuels::Where = FVector(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]), 0.f);
			}
			else if (Args.Num() >= 1 && Args[0] == TEXT("quit"))
			{
				FVLDuels::QuitWhenDone();
			}
			else if (Args.Num() >= 4)
			{
				FVLDuels::Queue(FCString::Atoi(*Args[0]), FCString::Atoi(*Args[1]), FCString::Atoi(*Args[2]), FCString::Atoi(*Args[3]),
					Args.Num() > 4 ? FCString::Atoi(*Args[4]) : 2, Args.Num() > 5 ? FCString::Atof(*Args[5]) : 120.f);
			}
		}));
}
