// Saved games: a match written to a slot and read back into the same state. See VLSave.h.

#include "VLSave.h"
#include "SovereignRealms.h"
#include "VLArcherCombat.h"
#include "VLBattle.h"
#include "VLCommand.h"
#include "VLConstruction.h"
#include "VLEnemyAI.h"
#include "VLFog.h"
#include "VLGrid.h"
#include "VLHUD.h"
#include "VLKing.h"
#include "VLRocks.h"
#include "VLSwordsmanCombat.h"
#include "VLTroop.h"
#include "VLTroopShip.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "JsonObjectConverter.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "TimerManager.h"

namespace
{
	TAutoConsoleVariable<float> CVarAutosaveMinutes(TEXT("vl.Autosave.Minutes"), 3.f, TEXT("minutes of play between two autosaves (the Auto slot, written over each time); 0: no autosave"));

	TAutoConsoleVariable<int32> CVarLoadPause(TEXT("vl.Load.Pause"), 0, TEXT("1: the game is paused the moment a save has been put back (tests: the state is read before anything moves; the engine's 'pause' goes on)"));
	TAutoConsoleVariable<int32> CVarSaveTestVersion(TEXT("vl.Save.TestVersion"), 0, TEXT("above 0: saves are written as that format version (tests of how a save from another version is refused)"));

	/** The save waiting for a map to open (UVLSaves::Load), put back when the match starts there. */
	struct FPendingLoad
	{
		FString Slot;
		FString MapPath;
	};
	FPendingLoad GPending;

	FString SaveTag(const AActor* A, const TCHAR* Prefix)
	{
		if (A)
		{
			const int32 Len = FCString::Strlen(Prefix);
			for (const FName& Tag : A->Tags)
			{
				const FString S = Tag.ToString();
				if (S.StartsWith(Prefix))
				{
					return S.Mid(Len);
				}
			}
		}
		return FString();
	}

	FString MapPathOf(const UWorld* World)
	{
		return World ? UWorld::RemovePIEPrefix(World->GetOutermost()->GetName()) : FString();
	}

	/** The map's name as the menus have it (AVLHUD::MapName), from its package. */
	FString MapTitleOf(const FString& Path, bool bTestWorld)
	{
		const FString Name = FPackageName::GetShortName(Path);
		const int32 Map = Name.Contains(TEXT("RealmV3")) ? 5 : Name.Contains(TEXT("RealmV2")) ? (bTestWorld ? 4 : 0) : Name.Contains(TEXT("Highlands")) ? 3 : Name.Contains(TEXT("Flatlands")) ? 2
			: (Name.Contains(TEXT("Realm")) ? 1 : INDEX_NONE);
		return Map == INDEX_NONE ? Name : FString(AVLHUD::MapName(Map));
	}

	FString SavePath(const FString& Slot)
	{
		return FPaths::ProjectSavedDir() / TEXT("SaveGames") / (UVLSaves::FileName(Slot) + TEXT(".sav"));
	}

	template <typename T, int32 N>
	TArray<T> ToArray(const T (&In)[N])
	{
		return TArray<T>(In, N);
	}

	template <typename T, int32 N>
	void FromArray(const TArray<T>& In, T (&Out)[N])
	{
		for (int32 i = 0; i < N && i < In.Num(); ++i)
		{
			Out[i] = In[i];
		}
	}
}

/** The match's state read into a UVLSaveGame, and put back from one. A friend of the classes whose state it is. */
struct FVLSaveIO
{
	static void Capture(UWorld* World, UVLSaveGame& Out);
	/** Puts the save in the place of the match that has just started. Returns what could not be put back (a line for
	 *  the player), or empty. */
	static FString Apply(UWorld* World, const UVLSaveGame& In);
};

// ------------------------------------------------------------------------------------------------ capture

void FVLSaveIO::Capture(UWorld* World, UVLSaveGame& Out)
{
	UVLBattle* Battle = UVLBattle::Get(World);
	UVLCommand* Command = UVLCommand::Get(World);
	UVLConstruction* Construction = UVLConstruction::Get(World);
	UVLFleet* Fleet = UVLFleet::Get(World);
	if (!Battle)
	{
		return;
	}
	Out.Version = UVLSaveGame::CurrentVersion;
	Out.MapPath = MapPathOf(World);
	Out.bTestWorld = Battle->bTestWorld;
	Out.MapTitle = MapTitleOf(Out.MapPath, Out.bTestWorld);
	Out.Difficulty = Battle->Difficulty;
	Out.Clock = Battle->Clock;
	Out.SavedAt = FDateTime::Now();
	Out.PlayerGold = Battle->Kingdoms[0].Gold;
	Out.PlayerFood = Battle->Kingdoms[0].Food;
	Out.PlayerPop = Battle->GetPopulation(UVLBattle::Player);
	Out.bBattle = Battle->bBattle;
	Out.Numbers = Battle->Numbers;

	// ---- who and what there is: a number each (the save's references)
	TArray<AVLKing*> Units;
	TMap<const AActor*, int32> UnitIndex, BuildingIndex, ShipIndex;
	for (AVLKing* U : Battle->AllUnits())
	{
		// (the fallen troops are gone in a moment; a fallen king rises again and is saved; a benched king, AI against
		// AI, is nobody's)
		if (U && !U->bAmbient && (U->Team == 0 || U->Team == 1) && !(U->IsDead() && U->IsTroop()))
		{
			UnitIndex.Add(U, Units.Add(U));
		}
	}
	TArray<const FVLBuildingState*> Buildings;
	for (const FVLBuildingState& B : Battle->Buildings)
	{
		if (B.Actor.IsValid() && B.Kind != EVLBuilding::None && !BuildingIndex.Contains(B.Actor.Get()))
		{
			BuildingIndex.Add(B.Actor.Get(), Buildings.Add(&B));
		}
	}
	TArray<AVLTroopShip*> Ships;
	if (Fleet)
	{
		for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->GetShips())
		{
			if (S.IsValid())
			{
				ShipIndex.Add(S.Get(), Ships.Add(S.Get()));
			}
		}
	}
	auto UnitRef = [&UnitIndex](const AActor* A) { const int32* I = A ? UnitIndex.Find(A) : nullptr; return I ? *I : INDEX_NONE; };
	auto BuildingRef = [&BuildingIndex](const AActor* A) { const int32* I = A ? BuildingIndex.Find(A) : nullptr; return I ? *I : INDEX_NONE; };
	auto Ref = [&](const AActor* A) -> int32
	{
		if (!A)
		{
			return VLSaveRef::None;
		}
		if (const int32* I = UnitIndex.Find(A)) { return *I; }
		if (const int32* I = BuildingIndex.Find(A)) { return VLSaveRef::Building + *I; }
		if (const int32* I = ShipIndex.Find(A)) { return VLSaveRef::Ship + *I; }
		return VLSaveRef::None;
	};
	auto UnitRefs = [&UnitRef](const TArray<TWeakObjectPtr<AVLKing>>& In)
	{
		TArray<int32> Refs;
		for (const TWeakObjectPtr<AVLKing>& U : In)
		{
			if (const int32 I = UnitRef(U.Get()); I != INDEX_NONE)
			{
				Refs.Add(I);
			}
		}
		return Refs;
	};

	// ---- the kingdoms
	for (int32 t = 0; t < 2; ++t)
	{
		const FVLKingdom& K = Battle->Kingdoms[t];
		FVLSavedKingdom& S = Out.Kingdoms.AddDefaulted_GetRef();
		S.Gold = K.Gold;
		S.Food = K.Food;
		S.Recruited = K.Recruited;
		S.Lost = K.Lost;
		S.Killed = K.Killed;
		S.BuildingsLost = K.BuildingsLost;
		S.bHasCastle = K.bHasCastle;
		S.RecruitedKind = ToArray(K.RecruitedKind);
		S.LostKind = ToArray(K.LostKind);
		S.Earned = ToArray(K.Earned);
		S.Wasted = ToArray(K.Wasted);
		S.Spent = ToArray(K.Spent);
		S.DamageBy = ToArray(K.DamageBy);
		S.BuildingDamageBy = ToArray(K.BuildingDamageBy);
		S.KillsBy = ToArray(K.KillsBy);
		S.SpyCooldown = Battle->SpyCooldownLeft[t];
		S.JonathanWait = Battle->JonathanWait[t];
		S.bJonathanCame = Battle->bJonathanCame[t];
		S.bJonathanBought = Battle->bJonathanBought[t];
		S.bJonathanOffered = Battle->bJonathanOffered[t];
		S.FarmVariant = Construction ? Construction->FarmVariant[t] : -1;
	}

	// ---- the buildings
	for (const FVLBuildingState* BP : Buildings)
	{
		const FVLBuildingState& B = *BP;
		const AActor* A = B.Actor.Get();
		FVLSavedBuilding& S = Out.Buildings.AddDefaulted_GetRef();
		S.LevelActor = A->ActorHasTag(TEXT("Built")) ? FString() : A->GetName();
		S.Kind = VLRules::Name(B.Kind);
		S.Name = B.Name;
		S.Mesh = B.Mesh;
		if (S.Mesh.IsEmpty())
		{
			const UStaticMeshComponent* C = A->FindComponentByClass<UStaticMeshComponent>();
			S.Mesh = C && C->GetStaticMesh() ? C->GetStaticMesh()->GetName() : FString();
		}
		S.Team = B.Team;
		S.Location = B.Rest;
		S.Rotation = A->GetActorRotation();
		S.Level = B.Level;
		S.Health = B.Health;
		S.UpgradeLeft = B.UpgradeLeft;
		S.UpgradeTotal = B.UpgradeTotal;
		S.Payout = B.Payout;
		S.Defence = B.Defence;
		S.bDestroyed = B.bDestroyed;
		S.Queue = B.Queue;
		S.TrainClock = B.TrainClock;
		S.Trained = B.Trained;
		S.FeedPlatoon = B.FeedPlatoon;
		S.bHasRally = B.bHasRally;
		S.Rally = B.Rally;
		S.Build = B.Build;
		S.bRuntime = B.bRuntime;
		S.PaidGold = B.Paid.Gold;
		S.PaidFood = B.Paid.Food;
		S.GuardLevel = B.GuardLevel;
		S.GuardRestock = B.GuardRestock;
		if (B.Kind == EVLBuilding::Castle && B.CornerLevel > 0)
		{
			for (int32 c = 0; c < 4; ++c)
			{
				S.CornerHealth.Add(B.CornerHealth[c]);
				S.CornerDown.Add(B.bCornerDown[c]);
				S.CornerRepair.Add(B.bCornerRepair[c]);
			}
			S.CornerLevel = B.CornerLevel;
		}
		S.bClaim = A->ActorHasTag(TEXT("Claim"));
		S.bWasNeutral = A->ActorHasTag(TEXT("WasNeutral"));
		for (const TWeakObjectPtr<AVLKing>& Y : B.Yard)
		{
			S.Yard.Add(UnitRef(Y.Get()));
		}
	}

	// ---- the ships
	for (AVLTroopShip* Ship : Ships)
	{
		FVLSavedShip& S = Out.Ships.AddDefaulted_GetRef();
		S.Team = Ship->Team;
		S.Location = Ship->GetActorLocation();
		S.Location.Z = Ship->SeaZ;
		S.Yaw = Ship->GetActorRotation().Yaw;
		S.Speed = Ship->Speed;
		S.bLanded = Ship->bLanded;
		if (Ship->bDocking)
		{
			// (in the middle of its docking move: it lies docked)
			S.Location = FVector(Ship->DockTo.X, Ship->DockTo.Y, Ship->SeaZ);
			S.Yaw = FRotator::NormalizeAxis(Ship->DockToYaw);
			S.Speed = 0.f;
			S.bLanded = true;
		}
		else if (Ship->bPatrol && Ship->PatrolPts.Num() >= 2)
		{
			S.Course = 2;
			S.Patrol = Ship->PatrolPts;
			S.PatrolNext = Ship->PatrolNext;
		}
		else if (Ship->Path.Num() > 0)
		{
			S.Course = 1;
			S.Target = Ship->LegTarget;
			S.Waypoints = Ship->Waypoints;
		}
	}

	// ---- the units
	for (AVLKing* U : Units)
	{
		FVLSavedUnit& S = Out.Units.AddDefaulted_GetRef();
		S.Kind = U->GetKind();
		S.Name = U->GetDisplayName();
		S.Team = U->Team;
		S.bTroop = U->IsTroop();
		S.Feet = U->GetFeet();
		S.Yaw = U->GetActorRotation().Yaw;
		S.Health = U->Health;
		S.bDead = U->bDead;
		S.DeadTime = U->DeadTime;
		S.Stance = uint8(U->Stance);
		S.bAttackMove = U->bAttackMove;
		S.bSiege = U->bSiege;
		S.bHoldOrder = U->bHoldOrder;
		S.bTowerGuard = U->bTowerGuard;
		S.bArmed = U->bArmed;
		S.Post = U->Post;
		S.bWalking = U->bAutoWalk;
		S.bRun = U->bAutoRun;
		S.Goal = U->OrderGoal;
		S.Legs = U->QueuedLegs;
		S.LegRuns = U->QueuedRuns;
		if (AActor* In = U->GarrisonIn.Get())
		{
			S.Garrison = Ref(In);
			if (const AVLTroopShip* Ship = Cast<AVLTroopShip>(In))
			{
				S.ShipPlace = Ship->PlaceOf(U);
			}
		}
		else if (AActor* To = U->PendingGarrison.Get())
		{
			S.Heading = Ref(To);
		}
		if (S.Garrison == VLSaveRef::None)
		{
			for (AVLTroopShip* Ship : Ships)
			{
				// on the gangplank, or on its way to it with a place kept: aboard (going up) / headed for it; going
				// down the gangplank: ashore, where it was to muster
				const int32 Place = Ship->PlaceOf(U);
				const AVLTroopShip::FWalk* Walk = Ship->Walks.FindByPredicate([U](const AVLTroopShip::FWalk& W) { return W.Unit.Get() == U; });
				if (Walk && Walk->bOff)
				{
					S.Feet = Walk->Muster;
					S.bWalking = false;
				}
				else if (Walk && Place != INDEX_NONE)
				{
					S.Garrison = Ref(Ship);
					S.ShipPlace = Place;
				}
				else if (Place != INDEX_NONE)
				{
					S.Heading = Ref(Ship);
				}
			}
		}
		if (UVLCommand::IsInOrderedFight(U))
		{
			const UVLSwordsmanCombat* Sword = UVLSwordsmanCombat::For(U, false);
			const UVLArcherCombat* Bow = UVLArcherCombat::For(U, false);
			S.Attack = Ref(Sword && Sword->IsAttacking() ? Sword->GetTarget() : (Bow ? Bow->GetTarget() : nullptr));
		}
		if (const UVLBuilderWork* Work = UVLBuilderWork::IsBuilder(U) ? U->FindComponentByClass<UVLBuilderWork>() : nullptr)
		{
			S.Job = BuildingRef(Work->GetJob());
			for (const UVLBuilderWork::FTask& T : Work->GetTasks())
			{
				FVLSavedTask& ST = S.Tasks.AddDefaulted_GetRef();
				ST.bMove = T.bMove;
				ST.Point = T.Point;
				ST.Building = BuildingRef(T.Building.Get());
				ST.bRun = T.bRun;
			}
		}
	}

	// ---- the orders
	if (Command)
	{
		for (int32 i = 0; i < UVLCommand::MaxPlatoons; ++i)
		{
			const UVLCommand::FPlatoon& P = Command->Platoons[i];
			FVLSavedPlatoon& S = Out.Platoons.AddDefaulted_GetRef();
			S.Members = UnitRefs(P.Members);
			S.Formation = uint8(P.Formation);
			S.Stance = uint8(P.Stance);
			S.bMarchTogether = P.bMarchTogether;
			S.Leader = UnitRef(P.Leader.Get());
		}
		Out.RallyPlatoon = Command->RallyPlatoon;
		Out.LooseFormation = uint8(Command->LooseFormation);
		Out.bLooseMarchTogether = Command->bLooseMarchTogether;
		for (const UVLCommand::FRoute& R : Command->Routes)
		{
			FVLSavedRoute S;
			S.Members = UnitRefs(R.Members);
			S.Points = R.Points;
			S.Next = R.Next;
			S.bLoop = R.bLoop;
			S.bRun = R.bRun;
			S.Shape = uint8(R.Shape);
			if (S.Members.Num() > 0 && S.Points.Num() > 0)
			{
				Out.Routes.Add(S);
			}
		}
		for (const UVLCommand::FGuardPost& G : Command->GuardPosts)
		{
			const int32 Unit = UnitRef(G.Unit.Get());
			const int32 Ward = Ref(G.Ward.Get());
			if (Unit == INDEX_NONE || Ward == VLSaveRef::None)
			{
				continue;
			}
			FVLSavedGuard* S = Out.Guards.FindByPredicate([&](const FVLSavedGuard& X) { return X.Ward == Ward && X.Platoon == G.Platoon; });
			if (!S)
			{
				S = &Out.Guards.AddDefaulted_GetRef();
				S->Ward = Ward;
				S->Platoon = G.Platoon;
			}
			S->Units.Add(Unit);
		}
		for (const UVLCommand::FFollower& F : Command->Followers)
		{
			const int32 Unit = UnitRef(F.Unit.Get());
			const int32 Leader = UnitRef(F.Leader.Get());
			if (Unit == INDEX_NONE || Leader == INDEX_NONE)
			{
				continue;
			}
			FVLSavedFollow* S = Out.Follows.FindByPredicate([Leader](const FVLSavedFollow& X) { return X.Leader == Leader; });
			if (!S)
			{
				S = &Out.Follows.AddDefaulted_GetRef();
				S->Leader = Leader;
			}
			S->Units.Add(Unit);
		}
		for (const UVLCommand::FRoamer& R : Command->Roamers)
		{
			if (const int32 Unit = UnitRef(R.Unit.Get()); Unit != INDEX_NONE)
			{
				Out.Roamers.Add(Unit);
			}
		}
		Out.Selection = UnitRefs(Command->Selection);
	}

	// ---- the commanders
	for (int32 t = 0; t < 2; ++t)
	{
		FVLSavedCommander& S = Out.Commanders.AddDefaulted_GetRef();
		const FVLCommander* C = Battle->Commanders[t].Get();
		if (!C)
		{
			continue;
		}
		S.bSaved = true;
		S.Difficulty = C->Difficulty;
		S.bActive = C->bActive;
		S.Clock = C->Clock;
		S.ThinkClock = C->ThinkClock;
		S.StrategyClock = C->StrategyClock;
		S.MicroClock = C->MicroClock;
		S.FoeArmyEstimate = C->FoeArmyEstimate;
		S.FoeArcherShare = C->FoeArcherShare;
		S.FoeAttacks = C->FoeAttacks;
		S.LastFoeAttack = C->LastFoeAttack;
		S.ThreatSince = C->ThreatSince;
		S.LastRaided = C->LastRaided;
		S.RaidedAt = C->RaidedAt;
		S.Posture = uint8(C->Posture);
		S.PostureSince = C->PostureSince;
		S.PostureWhy = C->PostureWhy;
		S.ContestPoint = C->ContestPoint;
		S.NextSquadId = C->NextSquadId;
		S.NextWaveTime = C->NextWaveTime;
		S.NextRaidTime = C->NextRaidTime;
		S.WavesSent = C->WavesSent;
		S.RaidsSent = C->RaidsSent;
		S.LastReinforce = C->LastReinforce;
		S.ShieldRatio = C->ShieldRatio;
		S.NextSpyOrder = C->NextSpyOrder;
		S.NextBuildTry = C->NextBuildTry;
		S.NextGarrison = C->NextGarrison;
		S.BuildStep = C->BuildStep;
		S.Stat = ToArray(C->Stat);
		for (const FVLSquad& Q : C->Squads)
		{
			FVLSavedSquad& SQ = S.Squads.AddDefaulted_GetRef();
			SQ.Id = Q.Id;
			SQ.Role = uint8(Q.Role);
			SQ.Task = uint8(Q.Task);
			SQ.Units = UnitRefs(Q.Units);
			SQ.Target = Ref(Q.Target.Get());
			SQ.Goal = Q.Goal;
			SQ.GoalName = Q.GoalName;
			SQ.StartSize = Q.StartSize;
			SQ.StartPower = Q.StartPower;
			SQ.TaskSince = Q.TaskSince;
			SQ.LastFight = Q.LastFight;
			SQ.Departs = Q.Departs;
			SQ.Via = Q.Via;
			SQ.TargetHealth = Q.TargetHealth;
			SQ.ProgressAt = Q.ProgressAt;
			SQ.ProgressDealt = Q.ProgressDealt;
		}
		for (const FVLSighting& Seen : C->Seen)
		{
			if (const int32 Unit = UnitRef(Seen.Unit.Get()); Unit != INDEX_NONE)
			{
				FVLSavedSighting& SS = S.Seen.AddDefaulted_GetRef();
				SS.Unit = Unit;
				SS.Pos = Seen.Pos;
				SS.bRanged = Seen.bRanged;
				SS.bKing = Seen.bKing;
				SS.HealthFrac = Seen.HealthFrac;
				SS.Time = Seen.Time;
			}
		}
	}

	// ---- the fog of war: the explored cells (run-length coded: long runs of the same), the enemy buildings seen
	if (const UVLFog* Fog = UVLFog::Get(World); Fog && Fog->IsActive())
	{
		TArray<uint8> Explored;
		Fog->GetExplored(Explored, Out.Fog.Dim, Out.Fog.Cell, Out.Fog.Origin);
		for (int32 i = 0; i < Explored.Num();)
		{
			int32 Run = 1;
			while (Run < 255 && i + Run < Explored.Num() && Explored[i + Run] == Explored[i]) { ++Run; }
			Out.Fog.ExploredRle.Add(Explored[i]);
			Out.Fog.ExploredRle.Add(uint8(Run));
			i += Run;
		}
		TArray<const AActor*> Seen;
		Fog->GetSeen(Seen);
		for (const AActor* A : Seen)
		{
			if (const int32 I = BuildingRef(A); I != INDEX_NONE) { Out.Fog.SeenBuildings.Add(I); }
		}
	}

	// ---- the rocks Builders cleared
	if (const UVLRocks* Rocks = UVLRocks::Get(World))
	{
		Rocks->SaveTo(Out.RocksCleared, Out.RockWorkNames, Out.RockWork);
	}

	// ---- the player's view
	const APlayerController* PC = World->GetFirstPlayerController();
	if (const AVLKing* Me = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr)
	{
		Out.Played = UnitRef(Me);
		Out.bHeroMode = Me->bHeroMode;
		Out.CamYaw = Me->CamYaw;
		Out.Zoom = Me->Zoom;
		Out.LookPitch = Me->LookPitch;
		Out.OverviewFocus = Me->OverviewFocus;
		Out.OverviewYaw = Me->OverviewYaw;
		Out.OverviewZoom = Me->OverviewZoom;
	}
}

// ------------------------------------------------------------------------------------------------ apply

FString FVLSaveIO::Apply(UWorld* World, const UVLSaveGame& In)
{
	UVLBattle* Battle = UVLBattle::Get(World);
	UVLCommand* Command = UVLCommand::Get(World);
	UVLConstruction* Construction = UVLConstruction::Get(World);
	UVLFleet* Fleet = UVLFleet::Get(World);
	UVLGrid* Grid = UVLGrid::Get(World);
	if (!Battle || !Command || !Construction)
	{
		return TEXT("The saved game could not be put back");
	}
	const double T0 = FPlatformTime::Seconds();
	int32 MissingBuildings = 0, MissingUnits = 0;

	// ---- the fresh match's army goes (the saved one takes its place); the orders are a clean sheet
	Command->Selection.Reset();
	for (UVLCommand::FPlatoon& P : Command->Platoons)
	{
		P = UVLCommand::FPlatoon();
	}
	Command->RallyPlatoon = INDEX_NONE;
	Command->Routes.Reset();
	Command->GuardPosts.Reset();
	Command->Roamers.Reset();
	Command->Followers.Reset();
	Command->Chains.Reset();
	Command->Towers.Reset();
	Command->Marchers.Reset();
	TMap<int32, AVLKing*> Kings;
	{
		FVLUnits Fresh;
		Battle->GetAllUnits(Fresh);
		for (AVLKing* U : Fresh)
		{
			if (!U)
			{
				continue;
			}
			if (!U->IsTroop())
			{
				Kings.Add(U->Team, U);
				continue;
			}
			if (AController* C = U->GetController(); C && !Cast<APlayerController>(C))
			{
				C->UnPossess();
				C->Destroy();
			}
			U->Destroy();
		}
	}
	for (FVLBuildingState& B : Battle->Buildings)
	{
		B.Guards.Reset();
		B.Yard.Reset();
	}
	Battle->Jonathans[0] = Battle->Jonathans[1] = nullptr;

	// ---- the buildings: the level's own take their saved state, those raised in the match are raised again
	TMap<FString, AActor*> ByName;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (!It->IsA<AVLKing>() && It->Tags.Num() > 0)
		{
			ByName.Add(It->GetName(), *It);
		}
	}
	TArray<AActor*> BuildingActors;
	TSet<const AActor*> Taken;
	TArray<FBox2D> Changed;
	BuildingActors.SetNumZeroed(In.Buildings.Num());
	for (int32 i = 0; i < In.Buildings.Num(); ++i)
	{
		const FVLSavedBuilding& S = In.Buildings[i];
		const EVLBuilding Kind = VLRules::KindFromName(S.Kind);
		if (Kind == EVLBuilding::None)
		{
			++MissingBuildings;
			UE_LOG(LogSovereignRealms, Warning, TEXT("load: no building of kind '%s' in this game (%s): left out"), *S.Kind, *S.Name);
			continue;
		}
		AActor* Actor = nullptr;
		if (!S.LevelActor.IsEmpty())
		{
			// the level's actor by its name; else (the map was built again since) the same kind of building standing
			// where it stood
			if (AActor** Found = ByName.Find(S.LevelActor); Found && !Taken.Contains(*Found) && VLRules::KindFromName(SaveTag(*Found, TEXT("Name:"))) == Kind)
			{
				Actor = *Found;
			}
			if (!Actor)
			{
				float Best = 400.f;
				for (const TPair<FString, AActor*>& Pair : ByName)
				{
					const float D = FVector::Dist(Pair.Value->GetActorLocation(), S.Location);
					if (D < Best && !Taken.Contains(Pair.Value) && !Pair.Value->ActorHasTag(TEXT("Built")) && VLRules::KindFromName(SaveTag(Pair.Value, TEXT("Name:"))) == Kind)
					{
						Best = D;
						Actor = Pair.Value;
					}
				}
				if (Actor)
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("load: %s '%s' is not in the map by that name: taken to be %s, standing there"), *S.Name, *S.LevelActor, *Actor->GetName());
				}
				else
				{
					UE_LOG(LogSovereignRealms, Warning, TEXT("load: the map no longer has %s '%s' at %s: raised again from its mesh"), *S.Name, *S.LevelActor, *S.Location.ToCompactString());
				}
			}
		}
		UVLConstruction::FRestore R;
		R.Actor = Actor;
		R.Kind = Kind;
		R.Team = S.Team;
		R.Mesh = S.Mesh;
		R.Location = S.Location;
		R.Rotation = S.Rotation;
		R.Build = S.Build;
		R.bDestroyed = S.bDestroyed;
		R.bClaim = S.bClaim;
		R.bWasNeutral = S.bWasNeutral;
		AActor* A = Construction->RestoreBuilding(R, Changed);
		FVLBuildingState* St = A ? Battle->FindBuilding(A) : nullptr;
		if (!St)
		{
			++MissingBuildings;
			UE_LOG(LogSovereignRealms, Warning, TEXT("load: %s of team %d could not be put back (mesh '%s'): left out"), *S.Name, S.Team, *S.Mesh);
			continue;
		}
		Taken.Add(A);
		BuildingActors[i] = A;
		St->Kind = Kind;
		St->Team = S.Team;
		if (!S.Name.IsEmpty())
		{
			St->Name = S.Name;
		}
		St->Level = FMath::Clamp(S.Level, 1, FMath::Max(VLRules::NumLevels(Kind), 1));
		St->MaxHealth = VLRules::Level(Kind, St->Level).Health;
		St->Health = S.bDestroyed ? 0.f : FMath::Clamp(S.Health, 1.f, St->MaxHealth);
		St->UpgradeLeft = S.bDestroyed || St->Level >= VLRules::NumLevels(Kind) ? -1.f : S.UpgradeLeft;
		St->UpgradeTotal = S.UpgradeTotal;
		St->Payout = S.Payout;
		St->Defence = S.Defence;
		St->Queue = S.bDestroyed ? TArray<FString>() : S.Queue;
		St->TrainClock = S.TrainClock;
		St->Trained = S.Trained;
		St->FeedPlatoon = S.FeedPlatoon >= 0 && S.FeedPlatoon < UVLCommand::MaxPlatoons ? S.FeedPlatoon : INDEX_NONE;
		St->bHasRally = S.bHasRally;
		St->Rally = S.Rally;
		St->bRuntime = S.bRuntime || Actor == nullptr;
		St->Paid.Gold = S.PaidGold;
		St->Paid.Food = S.PaidFood;
		St->GuardLevel = S.GuardLevel;
		St->GuardRestock = S.GuardRestock;
		// a castle's corners as they stood (else, CornerLevel 0: made whole at its level on the battle's first tick)
		St->CornerLevel = 0;
		if (Kind == EVLBuilding::Castle && S.CornerLevel > 0 && S.CornerHealth.Num() == 4 && S.CornerDown.Num() == 4 && S.CornerRepair.Num() == 4)
		{
			for (int32 c = 0; c < 4; ++c)
			{
				St->CornerHealth[c] = FMath::Max(0.f, S.CornerHealth[c]);
				St->bCornerDown[c] = S.CornerDown[c];
				St->bCornerRepair[c] = S.CornerRepair[c];
				St->CornerYaw[c] = (Battle->CornerPoint(A, c, 0.f) - A->GetActorLocation()).Rotation().Yaw;      // (facing out, as a new level sets it)
			}
			St->CornerLevel = S.CornerLevel;
		}
		St->bRepairing = false;
		St->BuildersAt = 0;
		St->LastHit = -100.0;
		St->LastAlert = -100.0;
	}
	Battle->bBuildingIndexDirty = true;
	Battle->bTagsDirty = true;
	for (int32 t = 0; t < 2 && t < In.Kingdoms.Num(); ++t)
	{
		Construction->FarmVariant[t] = In.Kingdoms[t].FarmVariant;
	}
	if (UVLRocks* Rocks = UVLRocks::Get(World))
	{
		Rocks->RestoreFrom(In.RocksCleared, In.RockWorkNames, In.RockWork, Changed);      // (the rocks Builders cleared go again)
	}
	if (Grid && Grid->EnsureBuilt() && Changed.Num() > 0)
	{
		Grid->RebuildAreas(Changed);
	}

	// ---- the ships (the level's own are put out a moment after play begins: now, so the saved ones can take their places)
	TArray<AVLTroopShip*> Ships;
	if (Fleet)
	{
		World->GetTimerManager().ClearAllTimersForObject(Fleet);
		if (Fleet->Ships.Num() == 0)
		{
			Fleet->SpawnShips();
		}
		TArray<AVLTroopShip*> Have;
		for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->Ships)
		{
			if (S.IsValid())
			{
				Have.Add(S.Get());
			}
		}
		for (int32 i = 0; i < In.Ships.Num(); ++i)
		{
			const FVLSavedShip& S = In.Ships[i];
			// the same ship of the level (by its order, of the same side); else one more
			AVLTroopShip* Ship = Have.IsValidIndex(i) && Have[i]->Team == S.Team && !Ships.Contains(Have[i]) ? Have[i] : nullptr;
			for (int32 k = 0; k < Have.Num() && !Ship; ++k)
			{
				Ship = Have[k]->Team == S.Team && !Ships.Contains(Have[k]) ? Have[k] : nullptr;
			}
			if (!Ship)
			{
				Ship = Fleet->SpawnShip(S.Location, S.Yaw, S.Team);
			}
			Ships.Add(Ship);
			if (!Ship)
			{
				continue;
			}
			Ship->Walks.Reset();
			Ship->Moor(S.Location, S.Yaw);
			if (S.Course == 2 && S.Patrol.Num() >= 2)
			{
				Ship->bPatrol = true;
				Ship->PatrolPts = S.Patrol;
				Ship->PatrolNext = FMath::Clamp(S.PatrolNext, 0, S.Patrol.Num() - 1);
				if (!Ship->StartLeg(Ship->PatrolPts[Ship->PatrolNext], false))
				{
					Ship->ClearCourse();
				}
			}
			else if (S.Course == 1 && Ship->StartLeg(S.Target, S.Waypoints.Num() == 0))
			{
				Ship->Waypoints = S.Waypoints;
			}
			Ship->Speed = Ship->Path.Num() > 0 ? S.Speed : 0.f;
			Ship->SettleClock = 100.f;
			Ship->PlankClock = 100.f;
			Ship->PlacePlank();
		}
	}

	// ---- what a reference of the save stands for now
	TArray<AVLKing*> Units;
	Units.SetNumZeroed(In.Units.Num());
	auto UnitAt = [&Units](int32 I) -> AVLKing* { return Units.IsValidIndex(I) ? Units[I] : nullptr; };
	auto BuildingAt = [&BuildingActors](int32 I) -> AActor* { return BuildingActors.IsValidIndex(I) ? BuildingActors[I] : nullptr; };
	auto Deref = [&](int32 R) -> AActor*
	{
		if (R >= VLSaveRef::Ship)
		{
			return Ships.IsValidIndex(R - VLSaveRef::Ship) ? Ships[R - VLSaveRef::Ship] : nullptr;
		}
		if (R >= VLSaveRef::Building)
		{
			return BuildingAt(R - VLSaveRef::Building);
		}
		return UnitAt(R);
	};
	auto UnitsOf = [&UnitAt](const TArray<int32>& Refs)
	{
		TArray<AVLKing*> Out;
		for (const int32 R : Refs)
		{
			if (AVLKing* U = UnitAt(R); U && U->IsAlive())
			{
				Out.AddUnique(U);
			}
		}
		return Out;
	};

	// ---- the units
	for (int32 i = 0; i < In.Units.Num(); ++i)
	{
		const FVLSavedUnit& S = In.Units[i];
		AVLKing* U = nullptr;
		if (!S.bTroop)
		{
			// the king is the level's own pawn
			AVLKing** King = Kings.Find(S.Team);
			U = King ? *King : nullptr;
			if (U)
			{
				const float Half = U->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
				U->StopOrder();
				U->ClearQueue();
				U->SetActorLocationAndRotation(S.Feet + FVector(0.f, 0.f, Half + 4.f), FRotator(0.f, S.Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
				U->GetCharacterMovement()->StopMovementImmediately();
			}
		}
		else if (S.Team == 0 || S.Team == 1)
		{
			U = Battle->SpawnTroop(S.Kind, S.Team, S.Feet, S.Yaw);
		}
		if (!U)
		{
			++MissingUnits;
			UE_LOG(LogSovereignRealms, Warning, TEXT("load: %s (%s, team %d) could not be put back: left out"), *S.Name, *S.Kind, S.Team);
			continue;
		}
		Units[i] = U;
		if (S.bTroop && !S.Name.IsEmpty())
		{
			U->SetDisplayName(S.Name);
		}
		U->Health = FMath::Clamp(S.Health, 1.f, U->MaxHealth);
		U->Stance = EVLStance(FMath::Min<uint8>(S.Stance, uint8(EVLStance::Hold)));
		U->Post = S.Post;
		U->bSiege = S.bSiege;
		U->LastStruckBy = nullptr;
		U->LastStruckTime = U->LastHurtTime = U->LastAutoFightTime = -100.0;
		if (S.bTowerGuard)
		{
			U->bTowerGuard = true;
			U->RefreshSilhouette();
		}
		if (!S.bTroop)
		{
			U->SetArmed(S.bArmed);
		}
		if (U->IsJonathan())
		{
			Battle->Jonathans[S.Team] = Cast<AVLTroop>(U);
		}
	}
	Battle->Numbers = In.Numbers;       // (the names run on from where they were)
	Battle->bHashDirty = true;

	// ---- who is played (before the orders: taking a unit over stops it)
	APlayerController* PC = World->GetFirstPlayerController();
	if (AVLKing* Me = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr)
	{
		if (AVLKing* Played = UnitAt(In.Played); Played && Played != Me && Played->Team == Me->Team)
		{
			Me->TakeControlOf(Played);
		}
	}
	Command->Followers.Reset();

	// ---- the fallen king lies where he fell, his wait as far on as it was
	for (int32 i = 0; i < In.Units.Num(); ++i)
	{
		if (AVLKing* U = Units[i]; U && In.Units[i].bDead && !In.Units[i].bTroop)
		{
			U->Die();
			U->DeadTime = In.Units[i].DeadTime;
		}
	}

	// ---- the platoons
	for (int32 i = 0; i < UVLCommand::MaxPlatoons && i < In.Platoons.Num(); ++i)
	{
		const FVLSavedPlatoon& S = In.Platoons[i];
		UVLCommand::FPlatoon& P = Command->Platoons[i];
		for (AVLKing* U : UnitsOf(S.Members))
		{
			P.Members.Add(U);
		}
		P.Formation = EVLFormation(FMath::Min<uint8>(S.Formation, uint8(EVLFormation::Loose)));
		P.Stance = EVLStance(FMath::Min<uint8>(S.Stance, uint8(EVLStance::Hold)));
		P.bMarchTogether = S.bMarchTogether;
		P.Leader = P.Members.Contains(UnitAt(S.Leader)) ? UnitAt(S.Leader) : nullptr;
	}
	Command->RallyPlatoon = In.RallyPlatoon >= 0 && In.RallyPlatoon < UVLCommand::MaxPlatoons ? In.RallyPlatoon : INDEX_NONE;
	Command->LooseFormation = EVLFormation(FMath::Min<uint8>(In.LooseFormation, uint8(EVLFormation::Loose)));
	Command->bLooseMarchTogether = In.bLooseMarchTogether;

	// ---- on the lookouts and aboard the ships
	for (int32 i = 0; i < In.Units.Num(); ++i)
	{
		const FVLSavedUnit& S = In.Units[i];
		AVLKing* U = Units[i];
		if (!U || U->IsDead() || S.Garrison == VLSaveRef::None)
		{
			continue;
		}
		AActor* Where = Deref(S.Garrison);
		if (AVLTroopShip* Ship = Cast<AVLTroopShip>(Where))
		{
			if (Ship->Places.IsValidIndex(S.ShipPlace) && !Ship->Places[S.ShipPlace].Unit.IsValid())
			{
				Ship->Seat(U, S.ShipPlace);
			}
			else
			{
				Ship->PutAboard(U);
			}
		}
		else if (Where)
		{
			// the post it stood on (the free one nearest where it stood), so that nobody swaps places
			if (UVLCommand::IsTower(Where))
			{
				UVLCommand::FTower& T = Command->TowerFor(Where);
				int32 Best = INDEX_NONE;
				float BestD = 250.f;
				for (int32 P = 0; P < T.Posts.Num(); ++P)
				{
					FVector Feet;
					FRotator Facing;
					const bool bFree = !T.Posts[P].IsValid() || (T.Posts[P]->GarrisonIn.Get() != Where && T.Posts[P]->PendingGarrison.Get() != Where);
					if (bFree && Command->PostWorld(Where, P, Feet, Facing))
					{
						const float D = FVector::Dist2D(Feet, S.Feet);
						if (D < BestD)
						{
							BestD = D;
							Best = P;
						}
					}
				}
				if (Best != INDEX_NONE)
				{
					T.Posts[Best] = U;
				}
			}
			const bool bUp = Command->PutOnLookout(U, Where);
			if (FVLBuildingState* St = S.bTowerGuard ? Battle->FindBuilding(Where) : nullptr)
			{
				if (bUp)
				{
					St->Guards.Add(U);
				}
			}
			if (!bUp && S.bTowerGuard)
			{
				// (a tower's own archer with no tower to stand on: it goes; the tower fills its lookout again)
				if (AController* C = U->GetController())
				{
					C->UnPossess();
					C->Destroy();
				}
				U->Destroy();
				Units[i] = nullptr;
			}
		}
	}
	for (int32 i = 0; i < In.Units.Num(); ++i)
	{
		// (a tower's own archer whose tower is gone altogether)
		if (AVLKing* U = Units[i]; U && In.Units[i].bTowerGuard && !U->IsGarrisoned())
		{
			if (AController* C = U->GetController())
			{
				C->UnPossess();
				C->Destroy();
			}
			U->Destroy();
			Units[i] = nullptr;
		}
	}

	// ---- the yards
	for (int32 i = 0; i < In.Buildings.Num(); ++i)
	{
		if (FVLBuildingState* St = Battle->FindBuilding(BuildingAt(i)))
		{
			for (const int32 Y : In.Buildings[i].Yard)
			{
				St->Yard.Add(UnitAt(Y));
			}
		}
	}

	// ---- the orders, given again. First each unit's own walk, hold and ordered attack (a plain order ends a standing
	// one), then the standing orders: patrols and attack-moves, guards, followers, roaming Spies
	TSet<int32> Standing;
	for (const FVLSavedRoute& R : In.Routes) { Standing.Append(R.Members); }
	for (const FVLSavedGuard& G : In.Guards) { Standing.Append(G.Units); }
	for (const FVLSavedFollow& F : In.Follows) { Standing.Append(F.Units); }
	Standing.Append(In.Roamers);
	TMap<int32, TArray<AVLKing*>> Attacks, Lookouts, Boardings;
	for (int32 i = 0; i < In.Units.Num(); ++i)
	{
		const FVLSavedUnit& S = In.Units[i];
		AVLKing* U = Units[i];
		if (!U || U->IsDead() || U->IsGarrisoned() || (i == In.Played && In.bHeroMode))
		{
			continue;               // (aboard or on a lookout; or in the player's own hands)
		}
		if (S.Heading >= VLSaveRef::Ship)
		{
			Boardings.FindOrAdd(S.Heading).Add(U);
			continue;
		}
		if (S.Heading >= VLSaveRef::Building)
		{
			Lookouts.FindOrAdd(S.Heading).Add(U);
			continue;
		}
		if (S.bHoldOrder)
		{
			Command->OrderHold({ U });
		}
		if (S.Attack != VLSaveRef::None)
		{
			Attacks.FindOrAdd(S.Attack).Add(U);
			continue;
		}
		if (Standing.Contains(i) || S.Job >= 0)
		{
			continue;
		}
		TArray<FVector> Legs = S.Legs;
		TArray<bool> Runs = S.LegRuns;
		FVector Goal = S.Goal;
		bool bRun = S.bRun;
		bool bWalk = S.bWalking;
		if (!bWalk && Legs.Num() > 0)
		{
			Goal = Legs[0];
			bRun = Runs.IsValidIndex(0) && Runs[0];
			Legs.RemoveAt(0);
			if (Runs.Num() > 0) { Runs.RemoveAt(0); }
			bWalk = true;
		}
		if (bWalk)
		{
			TGuardValue<bool> Quiet(Command->bQuietMove, true);
			Command->OrderMove({ U }, Goal, bRun, EVLFormation::Line);
			for (int32 k = 0; k < Legs.Num(); ++k)
			{
				U->QueueLeg(Legs[k], Runs.IsValidIndex(k) && Runs[k]);
			}
			U->bAttackMove = S.bAttackMove;
		}
	}
	for (const TPair<int32, TArray<AVLKing*>>& A : Attacks)
	{
		if (AActor* Target = Deref(A.Key); Target && Battle->IsAlive(Target))
		{
			Command->OrderAttack(A.Value, Target, false, false);
		}
	}
	for (const TPair<int32, TArray<AVLKing*>>& L : Lookouts)
	{
		if (AActor* Tower = Deref(L.Key); Tower && UVLCommand::IsTower(Tower))
		{
			Command->OrderGarrison(L.Value, Tower, false);
		}
	}
	for (const TPair<int32, TArray<AVLKing*>>& B : Boardings)
	{
		if (AVLTroopShip* Ship = Cast<AVLTroopShip>(Deref(B.Key)); Ship && Ship->IsLanded())
		{
			Ship->OrderBoard(B.Value, false);
		}
	}
	for (const FVLSavedRoute& S : In.Routes)
	{
		UVLCommand::FRoute R;
		for (AVLKing* U : UnitsOf(S.Members))
		{
			if (!U->IsGarrisoned())
			{
				R.Members.Add(U);
			}
		}
		if (R.Members.Num() == 0 || S.Points.Num() == 0)
		{
			continue;
		}
		R.Points = S.Points;
		R.Next = FMath::Clamp(S.Next, 0, S.Points.Num() - 1);
		R.bLoop = S.bLoop;
		R.bRun = S.bRun;
		R.Shape = EVLFormation(FMath::Min<uint8>(S.Shape, uint8(EVLFormation::Loose)));
		R.Id = Command->NextRouteId++;
		R.Settle = 1.f;
		Command->Routes.Add(R);
		Command->IssueLeg(Command->Routes.Last());
	}
	for (const FVLSavedGuard& G : In.Guards)
	{
		if (AActor* Ward = Deref(G.Ward))
		{
			Command->OrderGuard(UnitsOf(G.Units), Ward, true, G.Platoon >= 0 && G.Platoon < UVLCommand::MaxPlatoons ? G.Platoon : INDEX_NONE);
		}
	}
	for (const FVLSavedFollow& F : In.Follows)
	{
		if (AVLKing* Leader = UnitAt(F.Leader))
		{
			Command->OrderFollow(UnitsOf(F.Units), Leader, false);
		}
	}
	if (In.Roamers.Num() > 0)
	{
		Command->OrderRoam(UnitsOf(In.Roamers));
	}
	// the Builders: the job each was on, and its queue
	for (int32 i = 0; i < In.Units.Num(); ++i)
	{
		const FVLSavedUnit& S = In.Units[i];
		AVLKing* U = Units[i];
		if (!U || U->IsDead() || !UVLBuilderWork::IsBuilder(U) || (S.Job < 0 && S.Tasks.Num() == 0))
		{
			continue;
		}
		UVLBuilderWork* Work = UVLBuilderWork::For(U);
		if (!Work)
		{
			continue;
		}
		if (AActor* Job = BuildingAt(S.Job); Job && Battle->IsAlive(Job) && !U->IsGarrisoned())
		{
			Work->Begin(Job, true);
		}
		for (const FVLSavedTask& T : S.Tasks)
		{
			UVLBuilderWork::FTask Task;
			Task.bMove = T.bMove;
			Task.Point = T.Point;
			Task.Building = BuildingAt(T.Building);
			Task.bRun = T.bRun;
			if (Task.bMove || Task.Building.IsValid())
			{
				Work->QueueTask(Task);
			}
		}
	}
	for (AVLKing* U : UnitsOf(In.Selection))
	{
		Command->Selection.Add(U);
	}
	Command->Markers.Reset();
	Command->UpdateMarchPace();

	// ---- the battle's own numbers
	Battle->Clock = In.Clock;
	Battle->bBattle = In.bBattle;
	Battle->bTestWorld = In.bTestWorld;
	Battle->Cohesion.Reset();
	for (int32 t = 0; t < 2 && t < In.Kingdoms.Num(); ++t)
	{
		const FVLSavedKingdom& S = In.Kingdoms[t];
		FVLKingdom K;
		K.Gold = S.Gold;
		K.Food = S.Food;
		K.Recruited = S.Recruited;
		K.Lost = S.Lost;
		K.Killed = S.Killed;
		K.BuildingsLost = S.BuildingsLost;
		K.bHasCastle = Battle->GetCastle(t) != nullptr;
		FromArray(S.RecruitedKind, K.RecruitedKind);
		FromArray(S.LostKind, K.LostKind);
		FromArray(S.Earned, K.Earned);
		FromArray(S.Wasted, K.Wasted);
		FromArray(S.Spent, K.Spent);
		FromArray(S.DamageBy, K.DamageBy);
		FromArray(S.BuildingDamageBy, K.BuildingDamageBy);
		FromArray(S.KillsBy, K.KillsBy);
		Battle->Kingdoms[t] = K;
		Battle->SpyCooldownLeft[t] = FMath::Max(0.f, S.SpyCooldown);
		Battle->JonathanWait[t] = FMath::Max(0.f, S.JonathanWait);
		Battle->bJonathanCame[t] = S.bJonathanCame;
		Battle->bJonathanBought[t] = S.bJonathanBought || S.bJonathanCame;      // (older saves: he had come free)
		Battle->bJonathanOffered[t] = S.bJonathanOffered || Battle->bJonathanBought[t];
	}

	// ---- the commanders: their clocks, posture, squads and what they had seen; the rest they work out again
	for (int32 t = 0; t < 2 && t < In.Commanders.Num(); ++t)
	{
		const FVLSavedCommander& S = In.Commanders[t];
		FVLCommander* C = Battle->Commanders[t].Get();
		if (!C || !S.bSaved)
		{
			continue;
		}
		C->Reset(Battle, t, S.Difficulty);
		C->bActive = S.bActive;
		C->Clock = S.Clock;
		C->ThinkClock = S.ThinkClock;
		C->StrategyClock = S.StrategyClock;
		C->MicroClock = S.MicroClock;
		C->FoeArmyEstimate = S.FoeArmyEstimate;
		C->FoeArcherShare = S.FoeArcherShare;
		C->FoeAttacks = S.FoeAttacks;
		C->LastFoeAttack = S.LastFoeAttack;
		C->ThreatSince = S.ThreatSince;
		C->LastRaided = S.LastRaided;
		C->RaidedAt = S.RaidedAt;
		C->Posture = EVLPosture(FMath::Min<uint8>(S.Posture, uint8(uint8(EVLPosture::Num) - 1)));
		C->PostureSince = S.PostureSince;
		C->PostureWhy = S.PostureWhy;
		C->ContestPoint = S.ContestPoint;
		C->NextSquadId = FMath::Max(S.NextSquadId, 1);
		C->NextWaveTime = S.NextWaveTime;
		C->NextRaidTime = S.NextRaidTime;
		C->WavesSent = S.WavesSent;
		C->RaidsSent = S.RaidsSent;
		C->LastReinforce = S.LastReinforce;
		C->ShieldRatio = S.ShieldRatio;
		C->NextSpyOrder = S.NextSpyOrder;
		C->NextBuildTry = S.NextBuildTry;
		C->NextGarrison = S.NextGarrison;
		C->BuildStep = S.BuildStep;
		FromArray(S.Stat, C->Stat);
		for (const FVLSavedSquad& SQ : S.Squads)
		{
			FVLSquad Q;
			Q.Id = SQ.Id;
			Q.Role = EVLSquadRole(FMath::Min<uint8>(SQ.Role, uint8(EVLSquadRole::Picket)));
			Q.Task = EVLSquadTask(FMath::Min<uint8>(SQ.Task, uint8(EVLSquadTask::Retreat)));
			for (AVLKing* U : UnitsOf(SQ.Units))
			{
				if (U->Team == t)
				{
					Q.Units.Add(U);
				}
			}
			Q.Target = Deref(SQ.Target);
			Q.Goal = SQ.Goal;
			Q.GoalName = SQ.GoalName;
			Q.StartSize = SQ.StartSize;
			Q.StartPower = SQ.StartPower;
			Q.TaskSince = SQ.TaskSince;
			Q.LastFight = SQ.LastFight;
			Q.Departs = SQ.Departs;
			Q.Via = SQ.Via;
			Q.TargetHealth = SQ.TargetHealth;
			Q.ProgressAt = SQ.ProgressAt;
			Q.ProgressDealt = SQ.ProgressDealt;
			// (its order is given again at its next look: OrderedFor 0 matches no body of troops)
			if (Q.Units.Num() > 0)
			{
				C->Squads.Add(Q);
			}
		}
		for (const FVLSavedSighting& SS : S.Seen)
		{
			if (AVLKing* U = UnitAt(SS.Unit))
			{
				FVLSighting Seen;
				Seen.Unit = U;
				Seen.Pos = SS.Pos;
				Seen.bRanged = SS.bRanged;
				Seen.bKing = SS.bKing;
				Seen.HealthFrac = SS.HealthFrac;
				Seen.Time = SS.Time;
				C->Seen.Add(Seen);
			}
		}
		// (what fell before the save is no news to it)
		for (const FVLBuildingState& B : Battle->Buildings)
		{
			if (B.Team == t && B.bDestroyed && B.Actor.IsValid())
			{
				C->KnownLost.Add(B.Actor);
			}
		}
	}

	// ---- the player's view
	if (AVLKing* Me = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr)
	{
		Me->CamYaw = In.CamYaw;
		Me->Zoom = FMath::Clamp(In.Zoom, 0.f, 1.f);
		Me->LookPitch = In.LookPitch;
		PC->SetControlRotation(FRotator(Me->HeroPitch(Me->Zoom), Me->CamYaw, 0.f));
		const bool bHero = In.bHeroMode && Me->IsAlive();
		if (bHero != Me->bHeroMode)
		{
			Me->SetHeroMode(bHero);
		}
		Me->OverviewFocus = FVector(In.OverviewFocus.X, In.OverviewFocus.Y, 0.f);
		Me->OverviewYaw = In.OverviewYaw;
		Me->OverviewZoom = FMath::Clamp(In.OverviewZoom, 0.f, 1.f);
		Me->UpdateOverviewCamera(0.f, true);
	}
	// ---- the fog of war: put back on its first update of the match (after its own new-match reset)
	if (UVLFog* Fog = UVLFog::Get(World); Fog && In.Fog.Dim > 0)
	{
		TArray<uint8> Explored;
		for (int32 i = 0; i + 1 < In.Fog.ExploredRle.Num() && Explored.Num() <= In.Fog.Dim * In.Fog.Dim; i += 2)
		{
			for (int32 k = 0; k < In.Fog.ExploredRle[i + 1]; ++k) { Explored.Add(In.Fog.ExploredRle[i]); }
		}
		TArray<const AActor*> Seen;
		for (const int32 I : In.Fog.SeenBuildings)
		{
			if (BuildingActors.IsValidIndex(I) && BuildingActors[I]) { Seen.Add(BuildingActors[I]); }
		}
		if (Explored.Num() == In.Fog.Dim * In.Fog.Dim)
		{
			Fog->RestoreLater(Explored, In.Fog.Dim, Seen);
		}
		else
		{
			UE_LOG(LogSovereignRealms, Warning, TEXT("load: the fog's explored cells are damaged (%d of %d): not put back"), Explored.Num(), In.Fog.Dim * In.Fog.Dim);
			Fog->RestoreLater(TArray<uint8>(), 0, Seen);
		}
	}

	Battle->Alerts.Reset();
	Battle->Popups.Reset();
	Battle->RefreshUnitHash();

	int32 Put = 0, InPlatoons = 0;
	for (const AVLKing* U : Units)
	{
		Put += U ? 1 : 0;
	}
	for (const UVLCommand::FPlatoon& P : Command->Platoons)
	{
		InPlatoons += P.Members.Num();
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("load: the save of %s (%s, %s, %d:%02d played, version %d) put back in %.0f ms: %d building(s) (%d left out), %d unit(s) (%d left out), %d ship(s), %d platoon member(s), %d route(s)"),
		*In.SavedAt.ToString(), *In.MapTitle, UVLBattle::DifficultyName(In.Difficulty), int32(In.Clock) / 60, int32(In.Clock) % 60, In.Version, (FPlatformTime::Seconds() - T0) * 1000.0,
		In.Buildings.Num() - MissingBuildings, MissingBuildings, Put, MissingUnits, Ships.Num(), InPlatoons, Command->Routes.Num());
	if (MissingBuildings + MissingUnits > 0)
	{
		return FString::Printf(TEXT("Loaded, but %d building(s) and %d unit(s) of the save are not in this version of the game and were left out"), MissingBuildings, MissingUnits);
	}
	return FString();
}

// ------------------------------------------------------------------------------------------------ the slots

UVLSaves* UVLSaves::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLSaves>() : nullptr;
}

bool UVLSaves::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

FString UVLSaves::ManualSlot(int32 Index)
{
	return FString::Printf(TEXT("Slot%d"), FMath::Clamp(Index, 0, NumManualSlots - 1) + 1);
}

TArray<FString> UVLSaves::AllSlots()
{
	TArray<FString> Out;
	for (int32 i = 0; i < NumManualSlots; ++i)
	{
		Out.Add(ManualSlot(i));
	}
	Out.Add(QuickSlot());
	Out.Add(AutoSlot());
	return Out;
}

FString UVLSaves::SlotTitle(const FString& Slot)
{
	if (Slot == QuickSlot()) { return TEXT("Quicksave"); }
	if (Slot == AutoSlot()) { return TEXT("Autosave"); }
	return FString::Printf(TEXT("Slot %s"), *Slot.RightChop(4));
}

FString UVLSaves::SlotFromArg(const FString& Arg)
{
	const FString A = Arg.ToLower();
	if (A.StartsWith(TEXT("q"))) { return QuickSlot(); }
	if (A.StartsWith(TEXT("a"))) { return AutoSlot(); }
	const FString Digits = A.StartsWith(TEXT("slot")) ? A.RightChop(4) : A;
	const int32 N = Digits.IsNumeric() ? FCString::Atoi(*Digits) : 0;
	return N >= 1 && N <= NumManualSlots ? ManualSlot(N - 1) : FString();
}

FString UVLSaves::FileName(const FString& Slot)
{
	return TEXT("VL_") + Slot;
}

FString UVLSaves::DateText(const FDateTime& When)
{
	static const TCHAR* Months[12] = { TEXT("Jan"), TEXT("Feb"), TEXT("Mar"), TEXT("Apr"), TEXT("May"), TEXT("Jun"), TEXT("Jul"), TEXT("Aug"), TEXT("Sep"), TEXT("Oct"), TEXT("Nov"), TEXT("Dec") };
	return FString::Printf(TEXT("%d %s %d, %02d:%02d"), When.GetDay(), Months[FMath::Clamp(When.GetMonth(), 1, 12) - 1], When.GetYear(), When.GetHour(), When.GetMinute());
}

namespace
{
	struct FCachedInfo
	{
		FDateTime Stamp;
		FVLSaveInfo Info;
	};
	TMap<FString, FCachedInfo> GInfoCache;

	/** Why a save that was read cannot be loaded, or empty. */
	FString ProblemOf(const UVLSaveGame* Save)
	{
		if (!Save)
		{
			return TEXT("The file cannot be read");
		}
		if (Save->Version > UVLSaveGame::CurrentVersion)
		{
			return TEXT("Saved by a newer version of the game");
		}
		if (Save->Version < UVLSaveGame::MinVersion)
		{
			return TEXT("Saved by an older version: it can no longer be loaded");
		}
		if (Save->MapPath.IsEmpty() || !FPackageName::DoesPackageExist(Save->MapPath))
		{
			return FString::Printf(TEXT("Its map (%s) is not in this game"), Save->MapTitle.IsEmpty() ? TEXT("unknown") : *Save->MapTitle);
		}
		return FString();
	}

	/** The slot's save, read; null if there is none or it is no save of this game. */
	UVLSaveGame* ReadSlot(const FString& Slot)
	{
		const FString Path = SavePath(Slot);
		// (a file that is no save-game file at all is not handed to the engine's reader)
		TUniquePtr<FArchive> File(IFileManager::Get().CreateFileReader(*Path, FILEREAD_Silent));
		if (!File || File->TotalSize() < 16)
		{
			return nullptr;
		}
		ANSICHAR Tag[4] = {};
		File->Serialize(Tag, 4);
		File.Reset();
		if (Tag[0] != 'G' || Tag[1] != 'V' || Tag[2] != 'A' || Tag[3] != 'S')
		{
			return nullptr;
		}
		return Cast<UVLSaveGame>(UGameplayStatics::LoadGameFromSlot(UVLSaves::FileName(Slot), 0));
	}
}

FVLSaveInfo UVLSaves::GetInfo(const FString& Slot)
{
	FVLSaveInfo Info;
	Info.Slot = Slot;
	const FString Path = SavePath(Slot);
	const FDateTime Stamp = IFileManager::Get().GetTimeStamp(*Path);
	if (Slot.IsEmpty() || Stamp == FDateTime::MinValue())
	{
		GInfoCache.Remove(Slot);
		return Info;
	}
	if (const FCachedInfo* Cached = GInfoCache.Find(Slot); Cached && Cached->Stamp == Stamp)
	{
		return Cached->Info;
	}
	Info.bExists = true;
	const UVLSaveGame* Save = ReadSlot(Slot);
	Info.Problem = ProblemOf(Save);
	if (Save)
	{
		Info.MapTitle = Save->MapTitle;
		Info.MapPath = Save->MapPath;
		Info.bTestWorld = Save->bTestWorld;
		Info.Difficulty = Save->Difficulty;
		Info.Clock = Save->Clock;
		Info.SavedAt = Save->SavedAt;
		Info.Version = Save->Version;
		Info.Gold = Save->PlayerGold;
		Info.Food = Save->PlayerFood;
		Info.Pop = Save->PlayerPop;
	}
	else
	{
		Info.SavedAt = Stamp;
	}
	GInfoCache.Add(Slot, { Stamp, Info });
	return Info;
}

bool UVLSaves::MostRecent(FVLSaveInfo& Out)
{
	bool bFound = false;
	for (const FString& Slot : AllSlots())
	{
		const FVLSaveInfo Info = GetInfo(Slot);
		if (Info.CanLoad() && (!bFound || Info.SavedAt > Out.SavedAt))
		{
			Out = Info;
			bFound = true;
		}
	}
	return bFound;
}

// ------------------------------------------------------------------------------------------------ saving and loading

void UVLSaves::Say(const FString& Text, bool bFailed)
{
	LastMessage = Text;
	bLastFailed = bFailed;
	LastMessageAt = GetWorld() ? GetWorld()->GetRealTimeSeconds() : 0.0;
}

FString UVLSaves::SaveRefusal() const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle || Battle->GetState() == EVLMatch::Idle)
	{
		return TEXT("There is no match to save");
	}
	if (Battle->GetState() == EVLMatch::Ended)
	{
		return TEXT("The match is over: there is nothing to save");
	}
	return FString();
}

bool UVLSaves::Save(const FString& Slot, FString* OutWhy, bool bQuiet)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	FString Why = Slot.IsEmpty() ? FString(TEXT("No such slot")) : SaveRefusal();
	if (Why.IsEmpty())
	{
		const double T0 = FPlatformTime::Seconds();
		UVLSaveGame* Save = NewObject<UVLSaveGame>(GetTransientPackage());
		FVLSaveIO::Capture(GetWorld(), *Save);
		if (const int32 TestVersion = CVarSaveTestVersion.GetValueOnGameThread(); TestVersion > 0)
		{
			Save->Version = TestVersion;
		}
		if (UGameplayStatics::SaveGameToSlot(Save, FileName(Slot), 0))
		{
			GInfoCache.Remove(Slot);
			if (Slot != AutoSlot())
			{
				SinceAutosave = 0.f;        // (just saved by hand: the autosave waits its full time again)
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("save: %s written to %s in %.0f ms (%s, %s, %d:%02d played; %d buildings, %d units, %d ships)"), *SlotTitle(Slot), *SavePath(Slot),
				(FPlatformTime::Seconds() - T0) * 1000.0, *Save->MapTitle, UVLBattle::DifficultyName(Save->Difficulty), int32(Save->Clock) / 60, int32(Save->Clock) % 60,
				Save->Buildings.Num(), Save->Units.Num(), Save->Ships.Num());
			Say(Slot == AutoSlot() ? FString(TEXT("Autosaved")) : FString::Printf(TEXT("Game saved: %s"), *SlotTitle(Slot)), false);
			if (!bQuiet && Battle)
			{
				Battle->PushAlert(LastMessage, EVLAlert::Good);
			}
			return true;
		}
		Why = TEXT("The save file could not be written");
	}
	UE_LOG(LogSovereignRealms, Warning, TEXT("save: %s not saved: %s"), *Slot, *Why);
	Say(Why, true);
	if (OutWhy)
	{
		*OutWhy = Why;
	}
	if (!bQuiet && Battle)
	{
		Battle->PushAlert(Why);
		Battle->Play2D(TEXT("S_UIError"), 0.5f);
	}
	return false;
}

bool UVLSaves::Load(const FString& Slot, FString* OutWhy)
{
	const FVLSaveInfo Info = Slot.IsEmpty() ? FVLSaveInfo() : GetInfo(Slot);
	const FString Why = Slot.IsEmpty() ? FString(TEXT("No such slot")) : (!Info.bExists ? FString::Printf(TEXT("%s is empty"), *SlotTitle(Slot)) : Info.Problem);
	if (!Why.IsEmpty())
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("load: %s not loaded: %s"), *Slot, *Why);
		Say(Why, true);
		if (OutWhy)
		{
			*OutWhy = Why;
		}
		if (UVLBattle* Battle = UVLBattle::Get(this); Battle && Battle->IsPlaying())
		{
			Battle->PushAlert(Why);
			Battle->Play2D(TEXT("S_UIError"), 0.5f);
		}
		return false;
	}
	// its map is opened as New Game opens one (the loading screen shows); the match that starts there is the saved one
	// (UVLBattle::StartMatch -> OnMatchStarted)
	GPending.Slot = Slot;
	GPending.MapPath = Info.MapPath;
	UE_LOG(LogSovereignRealms, Log, TEXT("load: %s (%s, %s, %d:%02d played, saved %s): opening %s"), *SlotTitle(Slot), *Info.MapTitle, UVLBattle::DifficultyName(Info.Difficulty),
		int32(Info.Clock) / 60, int32(Info.Clock) % 60, *DateText(Info.SavedAt), *Info.MapPath);
	int32 Map = INDEX_NONE;
	for (int32 i = 0; i < AVLHUD::NumMaps && Map == INDEX_NONE; ++i)
	{
		Map = AVLHUD::MapPath(i) == Info.MapPath && (i == 4) == Info.bTestWorld ? i : INDEX_NONE;       // (4: the Test World, Realm v2 with ?TestWorld=1)
	}
	if (Map != INDEX_NONE)
	{
		AVLHUD::OpenMatch(this, Map, Info.Difficulty);      // (one of the menu's maps: opened exactly as New Game opens it)
	}
	else
	{
		UGameplayStatics::SetGamePaused(this, false);
		UGameplayStatics::OpenLevel(this, FName(*Info.MapPath), true, FString::Printf(TEXT("Match=1?Difficulty=%d%s"), FMath::Clamp(Info.Difficulty, 0, 2), Info.bTestWorld ? TEXT("?TestWorld=1") : TEXT("")));
	}
	return true;
}

bool UVLSaves::Delete(const FString& Slot, FString* OutWhy)
{
	FString Why;
	if (Slot.IsEmpty())
	{
		Why = TEXT("No such slot");
	}
	else if (!IFileManager::Get().FileExists(*SavePath(Slot)))
	{
		Why = FString::Printf(TEXT("%s is empty"), *SlotTitle(Slot));
	}
	else if (!UGameplayStatics::DeleteGameInSlot(FileName(Slot), 0) && IFileManager::Get().FileExists(*SavePath(Slot)))
	{
		Why = FString::Printf(TEXT("%s could not be deleted"), *SlotTitle(Slot));
	}
	GInfoCache.Remove(Slot);
	if (!Why.IsEmpty())
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("save: %s not deleted: %s"), *Slot, *Why);
		Say(Why, true);
		if (OutWhy)
		{
			*OutWhy = Why;
		}
		return false;
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("save: %s deleted (%s)"), *SlotTitle(Slot), *SavePath(Slot));
	Say(FString::Printf(TEXT("%s deleted"), *SlotTitle(Slot)), false);
	return true;
}

FString UVLSaves::Describe(const FVLSaveInfo& Info)
{
	const int32 S = FMath::Max(0, FMath::FloorToInt(Info.Clock));
	const FString Played = S >= 3600 ? FString::Printf(TEXT("%d:%02d:%02d"), S / 3600, (S / 60) % 60, S % 60) : FString::Printf(TEXT("%d:%02d"), S / 60, S % 60);
	return Info.MapTitle.IsEmpty() ? FString::Printf(TEXT("%s (unreadable)"), *SlotTitle(Info.Slot))
		: FString::Printf(TEXT("%s: %s · %s, %s played"), *SlotTitle(Info.Slot), *Info.MapTitle, UVLBattle::DifficultyName(Info.Difficulty), *Played);
}

bool UVLSaves::IsLoadPending()
{
	return !GPending.Slot.IsEmpty();
}

bool UVLSaves::WasRestored(const UObject* WorldContext)
{
	const UVLSaves* Saves = Get(WorldContext);
	return Saves && Saves->bRestored;
}

void UVLSaves::OnMatchStarted(UVLBattle* Battle)
{
	if (GPending.Slot.IsEmpty() || !Battle)
	{
		return;
	}
	const FPendingLoad Pending = GPending;
	GPending = FPendingLoad();
	UWorld* World = Battle->GetWorld();
	UVLSaves* Saves = Get(World);
	if (!World || !Saves || MapPathOf(World) != Pending.MapPath)
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("load: %s was waiting for %s, but the match started on %s: not loaded"), *Pending.Slot, *Pending.MapPath, *MapPathOf(World));
		return;
	}
	const UVLSaveGame* Save = ReadSlot(Pending.Slot);
	const FString Why = ProblemOf(Save);
	if (!Why.IsEmpty())
	{
		// (the file went, or changed, while the map was loading: a new match stands here, and says so)
		UE_LOG(LogSovereignRealms, Warning, TEXT("load: %s could not be put back: %s"), *Pending.Slot, *Why);
		Saves->RestoreNote = FString::Printf(TEXT("The saved game could not be loaded (%s): this is a new match"), *Why);
		Saves->RestoreNoteIn = 1.f;
		return;
	}
	Saves->bRestored = true;
	Saves->SinceAutosave = 0.f;
	const FString Note = FVLSaveIO::Apply(World, *Save);
	Saves->RestoreNote = Note.IsEmpty() ? FString::Printf(TEXT("Game loaded: %s"), *SlotTitle(Pending.Slot)) : Note;
	Saves->RestoreNoteIn = 0.5f;
	Saves->Say(Saves->RestoreNote, !Note.IsEmpty());
	if (CVarLoadPause.GetValueOnGameThread() != 0)
	{
		UGameplayStatics::SetGamePaused(World, true);
		UE_LOG(LogSovereignRealms, Log, TEXT("load: paused (vl.Load.Pause)"));
	}
}

float UVLSaves::AutosaveIn() const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const float Minutes = CVarAutosaveMinutes.GetValueOnGameThread();
	return Battle && Battle->IsPlaying() && Minutes > 0.f ? FMath::Max(0.f, Minutes * 60.f - SinceAutosave) : -1.f;
}

void UVLSaves::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle || DeltaSeconds <= 0.f)
	{
		return;
	}
	const float Real = FMath::Min(float(FApp::GetDeltaTime()), 0.5f);
	if (RestoreNoteIn >= 0.f && Battle->GetState() != EVLMatch::Idle)
	{
		RestoreNoteIn -= Real;
		if (RestoreNoteIn < 0.f)
		{
			Battle->PushAlert(RestoreNote, bRestored && RestoreNote.StartsWith(TEXT("Game loaded")) ? EVLAlert::Good : EVLAlert::Info);
		}
	}
	// the autosave: every few minutes of a match being played (not a commander-against-commander balance run)
	const float Minutes = CVarAutosaveMinutes.GetValueOnGameThread();
	const FVLCommander* PlayerAI = Battle->GetCommander(UVLBattle::Player);
	if (!Battle->IsPlaying() || Minutes <= 0.f || (PlayerAI && PlayerAI->bActive))
	{
		return;
	}
	SinceAutosave += Real;
	if (SinceAutosave >= Minutes * 60.f)
	{
		SinceAutosave = 0.f;
		Save(AutoSlot(), nullptr, true);
		if (!bLastFailed)
		{
			Battle->PushAlert(TEXT("Autosaved"));
		}
	}
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdSave(TEXT("vl.Save"), TEXT("vl.Save <1..5|quick|auto>: save the match to that slot (Saved/SaveGames/VL_<slot>.sav)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLSaves* Saves = UVLSaves::Get(World))
			{
				const FString Slot = UVLSaves::SlotFromArg(Args.Num() > 0 ? Args[0] : FString(TEXT("quick")));
				FString Why;
				if (Slot.IsEmpty())
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("save: no such slot '%s' (1..5, quick, auto)"), Args.Num() > 0 ? *Args[0] : TEXT(""));
				}
				else
				{
					Saves->Save(Slot, &Why);
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdLoad(TEXT("vl.Load"), TEXT("vl.Load <1..5|quick|auto|last>: load that slot (last: whichever was saved last, as Continue)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLSaves* Saves = UVLSaves::Get(World))
			{
				const FString Arg = Args.Num() > 0 ? Args[0] : FString(TEXT("quick"));
				FString Slot = UVLSaves::SlotFromArg(Arg);
				if (Arg.StartsWith(TEXT("l"), ESearchCase::IgnoreCase))
				{
					FVLSaveInfo Last;
					Slot = UVLSaves::MostRecent(Last) ? Last.Slot : FString();
				}
				FString Why;
				if (Slot.IsEmpty())
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("load: no such slot '%s' (1..5, quick, auto, last), or nothing saved yet"), *Arg);
				}
				else
				{
					Saves->Load(Slot, &Why);
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdDelete(TEXT("vl.DeleteSave"), TEXT("vl.DeleteSave <1..5|quick|auto>: delete that slot's save"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLSaves* Saves = UVLSaves::Get(World))
			{
				const FString Arg = Args.Num() > 0 ? Args[0] : FString();
				const FString Slot = UVLSaves::SlotFromArg(Arg);
				if (Slot.IsEmpty())
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("save: no such slot '%s' (1..5, quick, auto)"), *Arg);
				}
				else
				{
					Saves->Delete(Slot);
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSaves(TEXT("vl.Saves"), TEXT("vl.Saves: log every slot (what is in it, and whether it can be loaded)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			for (const FString& Slot : UVLSaves::AllSlots())
			{
				const FVLSaveInfo I = UVLSaves::GetInfo(Slot);
				if (!I.bExists)
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("saves: %-9s empty"), *UVLSaves::SlotTitle(Slot));
					continue;
				}
				UE_LOG(LogSovereignRealms, Log, TEXT("saves: %-9s %s, %s, %d:%02d played, saved %s, version %d, %d gold %d food %d troops: %s"), *UVLSaves::SlotTitle(Slot),
					I.MapTitle.IsEmpty() ? TEXT("?") : *I.MapTitle, UVLBattle::DifficultyName(I.Difficulty), int32(I.Clock) / 60, int32(I.Clock) % 60, *UVLSaves::DateText(I.SavedAt), I.Version, I.Gold, I.Food, I.Pop,
					I.Problem.IsEmpty() ? TEXT("can be loaded") : *I.Problem);
			}
			FVLSaveInfo Last;
			const UVLSaves* Saves = UVLSaves::Get(World);
			UE_LOG(LogSovereignRealms, Log, TEXT("saves: in %s; Continue loads %s; this match %s; next autosave in %.0f s"), *FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("SaveGames")),
				UVLSaves::MostRecent(Last) ? *UVLSaves::SlotTitle(Last.Slot) : TEXT("nothing"), UVLSaves::WasRestored(World) ? TEXT("was loaded from a save") : TEXT("was started new"),
				Saves ? Saves->AutosaveIn() : -1.f);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSaveDump(TEXT("vl.SaveDump"), TEXT("vl.SaveDump <name>: the match's state as a save would hold it, written as JSON to Saved/SaveGames/dump_<name>.json (tests)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const UVLBattle* Battle = UVLBattle::Get(World);
			if (!Battle || Battle->GetState() == EVLMatch::Idle)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("savedump: no match"));
				return;
			}
			UVLSaveGame* Save = NewObject<UVLSaveGame>(GetTransientPackage());
			FVLSaveIO::Capture(World, *Save);
			FString Json;
			const FString Path = FPaths::ProjectSavedDir() / TEXT("SaveGames") / FString::Printf(TEXT("dump_%s.json"), Args.Num() > 0 ? *Args[0] : TEXT("state"));
			const bool bOk = FJsonObjectConverter::UStructToJsonObjectString(UVLSaveGame::StaticClass(), Save, Json, 0, 0) && FFileHelper::SaveStringToFile(Json, *Path);
			UE_LOG(LogSovereignRealms, Log, TEXT("savedump: %s %s (%d buildings, %d units, %d ships, clock %.1f)"), bOk ? TEXT("wrote") : TEXT("could not write"), *Path,
				Save->Buildings.Num(), Save->Units.Num(), Save->Ships.Num(), Save->Clock);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdQuick(TEXT("vl.Quick"), TEXT("vl.Quick save|load: as the F5 / F9 keys"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			if (AVLHUD* HUD = PC ? Cast<AVLHUD>(PC->GetHUD()) : nullptr)
			{
				HUD->QuickSave(Args.Num() > 0 && Args[0].StartsWith(TEXT("l"), ESearchCase::IgnoreCase));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSaveMenu(TEXT("vl.SaveMenu"), TEXT("vl.SaveMenu save|load: open the Save Game / Load Game screen (over the pause menu in a match, else the title screen)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			if (AVLHUD* HUD = PC ? Cast<AVLHUD>(PC->GetHUD()) : nullptr)
			{
				HUD->SetScreen(Args.Num() > 0 && Args[0].StartsWith(TEXT("s"), ESearchCase::IgnoreCase) ? EVLScreen::SaveGame : EVLScreen::LoadGame);
			}
		}));
}
