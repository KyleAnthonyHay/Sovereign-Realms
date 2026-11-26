// Multiplayer, stage one (VLNet.h; Docs/Multiplayer/DESIGN.md).

#include "VLNet.h"
#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLConstruction.h"
#include "VLGameMode.h"
#include "VLHUD.h"
#include "VLKing.h"
#include "VLLoadingScreen.h"
#include "VLPlayerController.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/NetDriver.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "IPAddress.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/Parse.h"
#include "Net/UnrealNetwork.h"
#include "SocketSubsystem.h"
#include "Subsystems/WorldSubsystem.h"
#include "UObject/Package.h"

// ------------------------------------------------------------------------------------------------ helpers

FString VLNet::Version()
{
#if !UE_BUILD_SHIPPING
	// (tests: -VLFakeVersion=<text> makes this game say it is another build, to see the host refuse it)
	FString Fake;
	if (FParse::Value(FCommandLine::Get(), TEXT("VLFakeVersion="), Fake) && !Fake.IsEmpty())
	{
		return Fake;
	}
#endif
	FString Project;
	if (GConfig)
	{
		GConfig->GetString(TEXT("/Script/EngineSettings.GeneralProjectSettings"), TEXT("ProjectVersion"), Project, GGameIni);
	}
	if (Project.IsEmpty())
	{
		Project = TEXT("1.0");
	}
	return FString::Printf(TEXT("%s-mp%d"), *Project, Protocol);
}

bool VLNet::IsClient(const UObject* WorldContext)
{
	// (connected, with the host's world up: a world that is only TRYING to reach a host, the title screen behind
	// "Connecting ...", also says NM_Client, and is no joined game)
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World && World->GetNetMode() == NM_Client && World->GetNetDriver() != nullptr;
}

bool VLNet::IsHost(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World && World->GetNetMode() == NM_ListenServer;
}

AVLPlayerController* VLNet::LocalController(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (World)
	{
		for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
		{
			if (AVLPlayerController* PC = Cast<AVLPlayerController>(It->Get()); PC && PC->IsLocalController())
			{
				return PC;
			}
		}
	}
	return nullptr;
}

AVLPlayerController* VLNet::RemoteController(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (World && World->GetNetMode() == NM_ListenServer)
	{
		for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
		{
			if (AVLPlayerController* PC = Cast<AVLPlayerController>(It->Get()); PC && !PC->IsLocalController())
			{
				return PC;
			}
		}
	}
	return nullptr;
}

int32 VLNet::TeamOf(const APlayerController* PC)
{
	return (PC && (VLNet::IsClient(PC) || !PC->IsLocalController())) ? UVLBattle::Enemy : UVLBattle::Player;
}

AVLGameState* VLNet::State(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetGameState<AVLGameState>() : nullptr;
}

FString VLNet::LocalAddresses()
{
	FString Out;
	if (ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM))
	{
		TArray<TSharedPtr<FInternetAddr>> Found;
		if (Sockets->GetLocalAdapterAddresses(Found))
		{
			for (const TSharedPtr<FInternetAddr>& A : Found)
			{
				const FString Text = A.IsValid() ? A->ToString(false) : FString();
				// (the addresses another machine on the home network can use: IPv4, not this machine's own loopback)
				if (!Text.IsEmpty() && !Text.Contains(TEXT(":")) && !Text.StartsWith(TEXT("127.")) && !Text.StartsWith(TEXT("169.254.")))
				{
					Out += (Out.IsEmpty() ? TEXT("") : TEXT("  or  ")) + Text;
				}
			}
		}
	}
	return Out;
}

uint8 VLNetKinds::ToByte(const FString& Kind)
{
	return uint8(VLRules::KindOf(Kind));
}

FString VLNetKinds::ToName(uint8 Kind)
{
	switch (EVLUnitKind(Kind))
	{
	case EVLUnitKind::King: return TEXT("King");
	case EVLUnitKind::Archer: return TEXT("Archer");
	case EVLUnitKind::Spy: return TEXT("Spy");
	case EVLUnitKind::Builder: return TEXT("Builder");
	case EVLUnitKind::Jonathan: return TEXT("Jonathan");
	default: return TEXT("Swordsman");
	}
}

FVLNetRef VLNet::MakeRef(const UObject* WorldContext, AActor* Actor)
{
	FVLNetRef Ref;
	if (!Actor)
	{
		return Ref;
	}
	// a building raised in the match is each game's own copy: the battle's number says which. Anything else (a unit, an
	// actor of the level) is the same object to both.
	if (Actor->ActorHasTag(TEXT("Built")))
	{
		if (const UVLBattle* Battle = UVLBattle::Get(WorldContext))
		{
			Ref.Building = Battle->NetIdOf(Actor);
		}
	}
	if (Ref.Building == 0)
	{
		Ref.Actor = Actor;
	}
	return Ref;
}

bool VLNet::SendOrder(const UObject* WorldContext, EVLNetOrder Type, const TArray<AVLKing*>& Units, AActor* Target, const FVector& Ground, bool bRun, bool bQueue, uint8 Shape,
	AVLKing* Other, int32 Arg, bool bFlag, const TArray<FVector>* Points)
{
	if (!IsClient(WorldContext))
	{
		return false;
	}
	if (AVLPlayerController* PC = LocalController(WorldContext))
	{
		FVLNetOrder Order;
		Order.Type = Type;
		for (AVLKing* U : Units)
		{
			if (U && U->IsNetCopy())
			{
				Order.Units.Add(U);
			}
		}
		Order.Target = MakeRef(WorldContext, Target);
		Order.Other = Other;
		Order.Ground = Ground;
		if (Points)
		{
			Order.Points = *Points;
		}
		Order.Shape = Shape;
		Order.Arg = Arg;
		Order.bRun = bRun;
		Order.bQueue = bQueue;
		Order.bFlag = bFlag;
		PC->ServerOrder(Order);
	}
	return true;
}

bool VLNet::SendBuilding(const UObject* WorldContext, EVLNetBuildingAsk Ask, AActor* Building, int32 Arg, const FString& Kind, const FVector& Ground)
{
	if (!IsClient(WorldContext))
	{
		return false;
	}
	if (AVLPlayerController* PC = LocalController(WorldContext))
	{
		PC->ServerBuilding(Ask, MakeRef(WorldContext, Building), Arg, Kind, Ground);
	}
	return true;
}

// ------------------------------------------------------------------------------------------------ the building list

bool FVLNetBuilding::SameAs(const FVLNetBuilding& O) const
{
	return Id == O.Id && LevelActor == O.LevelActor && Kind == O.Kind && Team == O.Team && Mesh == O.Mesh && Location.Equals(O.Location, 1.) && Yaw == O.Yaw
		&& Health == O.Health && MaxHealth == O.MaxHealth && Level == O.Level && UpgradeLeft == O.UpgradeLeft && UpgradeTotal == O.UpgradeTotal && Build == O.Build
		&& Flags == O.Flags && BuildersAt == O.BuildersAt && Queue == O.Queue && TrainClock == O.TrainClock && Rally.Equals(O.Rally, 1.) && PaidGold == O.PaidGold
		&& PaidFood == O.PaidFood && CornerHealth[0] == O.CornerHealth[0] && CornerHealth[1] == O.CornerHealth[1] && CornerHealth[2] == O.CornerHealth[2]
		&& CornerHealth[3] == O.CornerHealth[3] && CornerBits == O.CornerBits && CornerLevel == O.CornerLevel;
}

// (the joining game works from the whole list in its tick, AVLGameState::Tick: it only needs to know something came)
void FVLNetBuilding::PreReplicatedRemove(const FVLNetBuildingArray& Array)
{
	if (Array.Owner)
	{
		Array.Owner->bListDirty = true;
	}
}

void FVLNetBuilding::PostReplicatedAdd(const FVLNetBuildingArray& Array)
{
	if (Array.Owner)
	{
		Array.Owner->bListDirty = true;
	}
}

void FVLNetBuilding::PostReplicatedChange(const FVLNetBuildingArray& Array)
{
	if (Array.Owner)
	{
		Array.Owner->bListDirty = true;
	}
}

// ------------------------------------------------------------------------------------------------ the game state

AVLGameState::AVLGameState()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bTickEvenWhenPaused = true;
	SetNetUpdateFrequency(15.f);
	Buildings.Owner = this;
}

void AVLGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AVLGameState, Buildings);
	DOREPLIFETIME(AVLGameState, Kingdoms);
	DOREPLIFETIME(AVLGameState, Match);
}

void AVLGameState::BeginPlay()
{
	Super::BeginPlay();
	Buildings.Owner = this;
	bListDirty = true;
}

void AVLGameState::OnRep_Kingdoms()
{
}

void AVLGameState::OnRep_Match()
{
}

namespace
{
	float VLNetRound(float Value, float Step)
	{
		return FMath::RoundToFloat(Value / Step) * Step;
	}

	/** A building of the battle as the joining game is told of it. */
	void VLNetFromState(const FVLBuildingState& B, FVLNetBuilding& I)
	{
		const AActor* A = B.Actor.Get();
		const bool bSpawned = A && A->ActorHasTag(TEXT("Built"));
		I.Id = B.NetId;
		I.LevelActor = bSpawned ? nullptr : const_cast<AActor*>(A);
		I.Kind = uint8(B.Kind);
		I.Team = int8(B.Team);
		I.Mesh = B.Mesh;
		// (where it stands: a falling one is sinking into the ground, its place is where it stood)
		I.Location = (B.Collapse >= 0.f || B.bDestroyed || !A) ? B.Rest : A->GetActorLocation();
		I.Yaw = A ? VLNetRound(A->GetActorRotation().Yaw, 0.5f) : 0.f;
		I.Health = FMath::RoundToFloat(B.Health);
		I.MaxHealth = FMath::RoundToFloat(B.MaxHealth);
		I.Level = uint8(FMath::Clamp(B.Level, 0, 255));
		I.UpgradeLeft = B.UpgradeLeft < 0.f ? -1.f : VLNetRound(B.UpgradeLeft, 0.5f);
		I.UpgradeTotal = B.UpgradeTotal;
		I.Build = B.Build >= 1.f ? 1.f : FMath::Min(0.995f, VLNetRound(B.Build, 0.005f));
		I.Flags = (B.bDestroyed ? 1 : 0) | (B.bRepairing ? 2 : 0) | (B.bRuntime ? 4 : 0) | ((A && A->ActorHasTag(TEXT("Claim"))) ? 8 : 0)
			| ((A && A->ActorHasTag(TEXT("WasNeutral"))) ? 16 : 0) | (B.bHasRally ? 32 : 0) | (bSpawned ? 64 : 0);
		I.BuildersAt = uint8(FMath::Clamp(B.BuildersAt, 0, 255));
		I.Queue.Reset(B.Queue.Num());
		for (const FString& Q : B.Queue)
		{
			I.Queue.Add(VLNetKinds::ToByte(Q));
		}
		I.TrainClock = VLNetRound(B.TrainClock, 0.25f);
		I.Rally = B.Rally;
		I.PaidGold = B.Paid.Gold;
		I.PaidFood = B.Paid.Food;
		I.CornerBits = 0;
		for (int32 c = 0; c < 4; ++c)
		{
			I.CornerHealth[c] = FMath::RoundToFloat(B.CornerHealth[c]);
			I.CornerBits |= (B.bCornerDown[c] ? 1 : 0) << c;
			I.CornerBits |= (B.bCornerRepair[c] ? 1 : 0) << (4 + c);
		}
		I.CornerLevel = uint8(FMath::Clamp(B.CornerLevel, 0, 255));
	}
}

void AVLGameState::Push(UVLBattle& Battle)
{
	// the match and the two kingdoms: plain properties (the engine sends one only when it differs from what was sent)
	Match.State = uint8(Battle.State);
	Match.bBattle = Battle.bBattle;
	Match.Winner = int8(Battle.Winner);
	Match.Clock = FMath::FloorToInt(Battle.Clock);
	Match.bAbandoned = Battle.bAbandoned;
	for (int32 t = 0; t < 2; ++t)
	{
		const FVLKingdom& K = Battle.Kingdoms[t];
		FVLNetKingdom& N = Kingdoms[t];
		N.Gold = K.Gold;
		N.Food = K.Food;
		N.Recruited = K.Recruited;
		N.Lost = K.Lost;
		N.Killed = K.Killed;
		N.BuildingsLost = K.BuildingsLost;
		N.SpyCooldown = FMath::CeilToInt(Battle.SpyCooldownLeft[t]);
		N.JonathanWait = FMath::CeilToInt(Battle.JonathanWait[t]);
		N.Flags = (K.bHasCastle ? 1 : 0) | (Battle.bJonathanBought[t] ? 2 : 0) | (Battle.bJonathanCame[t] ? 4 : 0);
	}
	// the buildings: the fast array sends only the entries marked here
	TMap<int32, int32> Index;
	Index.Reserve(Buildings.Items.Num());
	for (int32 i = 0; i < Buildings.Items.Num(); ++i)
	{
		Index.Add(Buildings.Items[i].Id, i);
	}
	TSet<int32> Seen;
	FVLNetBuilding Now;
	for (const FVLBuildingState& B : Battle.Buildings)
	{
		if (B.NetId == 0 || !B.Actor.IsValid())
		{
			continue;
		}
		VLNetFromState(B, Now);
		Seen.Add(B.NetId);
		if (const int32* At = Index.Find(B.NetId))
		{
			FVLNetBuilding& Have = Buildings.Items[*At];
			if (!Have.SameAs(Now))
			{
				// (the entry's own replication ids stay as they are: only its fields are written)
				const int32 KeepId = Have.ReplicationID, KeepKey = Have.ReplicationKey, KeepArrayKey = Have.MostRecentArrayReplicationKey;
				Have = Now;
				Have.ReplicationID = KeepId;
				Have.ReplicationKey = KeepKey;
				Have.MostRecentArrayReplicationKey = KeepArrayKey;
				Buildings.MarkItemDirty(Have);
			}
		}
		else
		{
			FVLNetBuilding& Added = Buildings.Items.Add_GetRef(Now);
			Added.ReplicationID = INDEX_NONE;
			Added.ReplicationKey = INDEX_NONE;
			Added.MostRecentArrayReplicationKey = INDEX_NONE;
			Buildings.MarkItemDirty(Added);
		}
	}
	bool bRemoved = false;
	for (int32 i = Buildings.Items.Num() - 1; i >= 0; --i)
	{
		if (!Seen.Contains(Buildings.Items[i].Id))
		{
			Buildings.Items.RemoveAt(i);
			bRemoved = true;
		}
	}
	if (bRemoved)
	{
		Buildings.MarkArrayDirty();
	}
}

void AVLGameState::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	if (World->GetNetMode() == NM_ListenServer)
	{
		// the host: this frame's arrows to the joining player, a packet's worth at a time
		if (AVLPlayerController* Remote = VLNet::RemoteController(this); Remote && Remote->ArrowsOut.Num() > 0)
		{
			const int32 Each = 20;
			for (int32 From = 0; From < Remote->ArrowsOut.Num() && From < 3 * Each; From += Each)
			{
				TArray<FVLNetArrow> Some;
				Some.Append(Remote->ArrowsOut.GetData() + From, FMath::Min(Each, Remote->ArrowsOut.Num() - From));
				Remote->ClientArrows(Some);
			}
			Remote->ArrowsOut.Reset();
		}
		return;
	}
	if (!VLNet::IsClient(this) || !World->HasBegunPlay())
	{
		return;
	}
	// ---- the joining player's game: the battle is filled from what the host sent
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* Construction = UVLConstruction::Get(this);
	if (!Battle || !Construction)
	{
		return;
	}
	// the match
	if (Match.State == uint8(EVLMatch::Playing) && Battle->State == EVLMatch::Idle)
	{
		Battle->State = EVLMatch::Playing;
		Battle->bBattle = Match.bBattle;
		Battle->Winner = -1;
		Battle->EndedAt = -1.0;
		Battle->Clock = float(Match.Clock);
		if (Match.bBattle)
		{
			Construction->ClearStartTrainers();     // (as the host did when the match began: the level's barracks and ranges go)
		}
		bListDirty = true;
		UE_LOG(LogSovereignRealms, Log, TEXT("multiplayer: the match has started (%s)"), Match.bBattle ? TEXT("a battle") : TEXT("a sandbox"));
	}
	if (Battle->State == EVLMatch::Playing)
	{
		if (FMath::Abs(Battle->Clock - float(Match.Clock)) > 1.5f)
		{
			Battle->Clock = float(Match.Clock);
		}
		if (Match.State == uint8(EVLMatch::Ended))
		{
			Battle->State = EVLMatch::Ended;
			Battle->Winner = Match.Winner;
			Battle->bAbandoned = Match.bAbandoned;
			Battle->EndedAt = World->GetRealTimeSeconds();
			UE_LOG(LogSovereignRealms, Log, TEXT("multiplayer: match over, team %d wins%s: %s"), int32(Match.Winner), Match.bAbandoned ? TEXT(" (the other player left)") : TEXT(""),
				Match.Winner == UVLBattle::Mine() ? TEXT("VICTORY") : TEXT("DEFEAT"));
		}
	}
	// the kingdoms
	for (int32 t = 0; t < 2; ++t)
	{
		FVLKingdom& K = Battle->Kingdoms[t];
		const FVLNetKingdom& N = Kingdoms[t];
		if (Battle->State != EVLMatch::Idle)
		{
			if (N.Gold > K.Gold) { K.Pulse[0] = 1.f; }
			if (N.Food > K.Food) { K.Pulse[1] = 1.f; }
		}
		K.Gold = N.Gold;
		K.Food = N.Food;
		K.Recruited = N.Recruited;
		K.Lost = N.Lost;
		K.Killed = N.Killed;
		K.BuildingsLost = N.BuildingsLost;
		K.bHasCastle = (N.Flags & 1) != 0;
		Battle->SpyCooldownLeft[t] = float(N.SpyCooldown);
		Battle->JonathanWait[t] = float(N.JonathanWait);
		Battle->bJonathanBought[t] = (N.Flags & 2) != 0;
		Battle->bJonathanCame[t] = (N.Flags & 4) != 0;
	}
	// the buildings, once the match is on (before that the level's own stand as the level has them)
	PendingClock -= DeltaSeconds;
	if (Battle->State != EVLMatch::Idle && (bListDirty || PendingClock <= 0.f))
	{
		PendingClock = 0.5f;        // (and twice a second anyway: an entry whose level actor was not there yet)
		bListDirty = false;
		TSet<int32> Here;
		for (const FVLNetBuilding& I : Buildings.Items)
		{
			Here.Add(I.Id);
			const FVLNetBuilding* Was = Applied.Find(I.Id);
			if (Was && Was->SameAs(I))
			{
				continue;
			}
			if (Construction->NetApplyBuilding(I))
			{
				Applied.Add(I.Id, I);
			}
		}
		for (auto It = Applied.CreateIterator(); It; ++It)
		{
			if (!Here.Contains(It.Key()))
			{
				Construction->NetRemoveBuilding(It.Key());
				It.RemoveCurrent();
			}
		}
	}
}

// ------------------------------------------------------------------------------------------------ hosting and joining

UVLNetSession* UVLNetSession::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	const UGameInstance* Instance = World ? World->GetGameInstance() : nullptr;
	return Instance ? Instance->GetSubsystem<UVLNetSession>() : nullptr;
}

void UVLNetSession::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	if (GEngine)
	{
		NetFailHandle = GEngine->OnNetworkFailure().AddUObject(this, &UVLNetSession::OnNetworkFailure);
		TravelFailHandle = GEngine->OnTravelFailure().AddUObject(this, &UVLNetSession::OnTravelFailure);
	}
	PostLoadHandle = FCoreUObjectDelegates::PostLoadMapWithWorld.AddUObject(this, &UVLNetSession::OnPostLoadMap);
}

void UVLNetSession::Deinitialize()
{
	if (GEngine)
	{
		GEngine->OnNetworkFailure().Remove(NetFailHandle);
		GEngine->OnTravelFailure().Remove(TravelFailHandle);
	}
	FCoreUObjectDelegates::PostLoadMapWithWorld.Remove(PostLoadHandle);
	Super::Deinitialize();
}

void UVLNetSession::Host(const UObject* WorldContext, int32 Map)
{
	Note.Reset();
	bJoining = false;
	bLeaving = false;
	UGameplayStatics::SetGamePaused(WorldContext, false);
	UE_LOG(LogSovereignRealms, Log, TEXT("multiplayer: hosting %s (version %s; this machine: %s)"), AVLHUD::MapName(Map), *VLNet::Version(), *VLNet::LocalAddresses());
	// ?listen makes this game a listen server; ?MP=1 tells the game mode to wait for the other player before the match
	VLLoadingScreen::Travel(WorldContext, AVLHUD::MapPath(Map), TEXT("Match=1?MP=1?listen"));
}

bool UVLNetSession::Join(const UObject* WorldContext, const FString& Address)
{
	FString Where = Address.TrimStartAndEnd();
	if (Where.IsEmpty())
	{
		return false;
	}
	if (!Where.Contains(TEXT(":")))
	{
		Where += FString::Printf(TEXT(":%d"), VLNet::DefaultPort);
	}
	UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (!PC)
	{
		return false;
	}
	Note.Reset();
	LastAddress = Where;
	bJoining = true;
	bLeaving = false;
	UGameplayStatics::SetGamePaused(WorldContext, false);
	UE_LOG(LogSovereignRealms, Log, TEXT("multiplayer: joining %s (version %s)"), *Where, *VLNet::Version());
	// (the host compares the version and refuses another: AVLGameMode::PreLogin)
	PC->ClientTravel(FString::Printf(TEXT("%s?VLVer=%s"), *Where, *VLNet::Version()), TRAVEL_Absolute);
	return true;
}

void UVLNetSession::Leave(const UObject* WorldContext, const FString& Why)
{
	UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (!World || bLeaving)
	{
		return;
	}
	if (bJoining)
	{
		// still trying to reach a host: give up (the title screen is still up behind it)
		bJoining = false;
		Note = Why;
		if (GEngine)
		{
			GEngine->CancelAllPending();
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("multiplayer: stopped trying to join %s"), *LastAddress);
		return;
	}
	bLeaving = true;
	Note = Why;
	if (World->GetNetMode() == NM_ListenServer)
	{
		// the host leaves: the joining player is told why its match is over, before the connection goes
		if (AVLPlayerController* Remote = VLNet::RemoteController(World))
		{
			Remote->ClientMatchClosed(TEXT("The host left the match"));
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("multiplayer: leaving the match%s%s"), Why.IsEmpty() ? TEXT("") : TEXT(": "), *Why);
	UGameplayStatics::SetGamePaused(World, false);
	// (opening a map on its own, without ?listen or an address, ends the connection: the title screen comes up)
	UGameplayStatics::OpenLevel(World, FName(*AVLHUD::MapPath(1)), true, FString());
}

void UVLNetSession::OnNetworkFailure(UWorld* World, UNetDriver* Driver, ENetworkFailure::Type Type, const FString& Error)
{
	UE_LOG(LogSovereignRealms, Warning, TEXT("multiplayer: network failure %s: %s"), ENetworkFailure::ToString(Type), *Error);
	if (bLeaving || (World && World->GetNetMode() == NM_ListenServer))
	{
		return;         // (the host's side of a player dropping is AVLGameMode::Logout)
	}
	// the joining side: back to the title screen (the engine travels there by itself), with what happened
	switch (Type)
	{
	case ENetworkFailure::FailureReceived:
		Note = Error.IsEmpty() ? FString(TEXT("The host refused the connection")) : Error;      // (PreLogin's message: another version, a full match)
		break;
	case ENetworkFailure::OutdatedClient:
	case ENetworkFailure::OutdatedServer:
		Note = TEXT("The two games are different versions: both need the same build");
		break;
	case ENetworkFailure::PendingConnectionFailure:
		// (with a message: the host's own refusal, another version or a full match; without: nothing answered)
		Note = Error.IsEmpty() ? FString::Printf(TEXT("No game answered at %s"), *LastAddress) : Error;
		break;
	case ENetworkFailure::ConnectionLost:
	case ENetworkFailure::ConnectionTimeout:
		Note = bJoining ? FString::Printf(TEXT("No game answered at %s"), *LastAddress) : FString(TEXT("The connection to the host was lost"));
		break;
	default:
		Note = FString::Printf(TEXT("The connection failed (%s)"), ENetworkFailure::ToString(Type));
		break;
	}
	bJoining = false;
}

void UVLNetSession::OnTravelFailure(UWorld* World, ETravelFailure::Type Type, const FString& Error)
{
	UE_LOG(LogSovereignRealms, Warning, TEXT("multiplayer: travel failure %s: %s"), ETravelFailure::ToString(Type), *Error);
	if (bJoining)
	{
		Note = FString::Printf(TEXT("Could not join %s (%s)"), *LastAddress, ETravelFailure::ToString(Type));
		bJoining = false;
	}
}

void UVLNetSession::OnPostLoadMap(UWorld* World)
{
	bLeaving = false;
	if (VLNet::IsClient(World))
	{
		bJoining = false;       // (in: the host's level is up)
	}
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	// vl.Host <map> / vl.Join <address> / vl.Leave: the menu's Multiplayer screen, for scripts and the ~ console
	FAutoConsoleCommandWithWorldAndArgs CmdVLHost(TEXT("vl.Host"), TEXT("vl.Host [realm|realmv2|realmv3|highlands]: host a multiplayer match on that map (a listen server on port 7777); the match starts when the other player has joined"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLNetSession* Session = UVLNetSession::Get(World))
			{
				Session->Host(World, AVLHUD::MapByName(Args.Num() > 0 ? Args[0] : FString(TEXT("realmv3"))));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdVLJoin(TEXT("vl.Join"), TEXT("vl.Join <address[:port]>: join the multiplayer match hosted at that address (port 7777 unless given)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLNetSession* Session = UVLNetSession::Get(World))
			{
				if (!Session->Join(World, Args.Num() > 0 ? Args[0] : FString(TEXT("127.0.0.1"))))
				{
					UE_LOG(LogSovereignRealms, Warning, TEXT("vl.Join: no address"));
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdVLLeave(TEXT("vl.Leave"), TEXT("vl.Leave: leave the multiplayer match (the host: ends it for both)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (UVLNetSession* Session = UVLNetSession::Get(World))
			{
				Session->Leave(World);
			}
		}));

	// vl.NetDump <name>: what this game holds of the match, one line a unit / building / kingdom, sorted, to
	// Saved/<name>.txt. Run in both games of a multiplayer match and compare the two files (Tools/windows/mp_test.ps1).
	FAutoConsoleCommandWithWorldAndArgs CmdVLNetDump(TEXT("vl.NetDump"), TEXT("vl.NetDump <name>: write this game's view of the match (units, buildings, kingdoms) to Saved/<name>.txt, for comparing the host's with the joining game's"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const UVLBattle* Battle = UVLBattle::Get(World);
			if (!World || !Battle || Args.Num() == 0)
			{
				return;
			}
			TArray<FString> Lines;
			for (const AVLKing* U : Battle->AllUnits())
			{
				if (!U || U->bAmbient)
				{
					continue;
				}
				const FVector F = U->GetFeet();
				Lines.Add(FString::Printf(TEXT("unit team=%d name=%s kind=%s alive=%d health=%.0f x=%.0f y=%.0f z=%.0f"), U->Team, *U->GetDisplayName().Replace(TEXT(" "), TEXT("_")), *U->GetKind(),
					U->IsAlive() ? 1 : 0, U->GetHealth(), F.X, F.Y, F.Z));
			}
			for (const FVLBuildingState& B : Battle->GetBuildings())
			{
				const AActor* A = B.Actor.Get();
				const FVector At = A ? B.Rest : FVector::ZeroVector;
				Lines.Add(FString::Printf(TEXT("building id=%03d team=%d kind=%s level=%d alive=%d health=%.0f build=%.2f queue=%d x=%.0f y=%.0f"), B.NetId, B.Team, VLRules::Name(B.Kind), B.Level,
					B.IsAlive() ? 1 : 0, B.Health, B.Build, B.Queue.Num(), At.X, At.Y));
			}
			for (int32 t = 0; t < 2; ++t)
			{
				const FVLKingdom& K = Battle->GetKingdom(t);
				Lines.Add(FString::Printf(TEXT("kingdom team=%d gold=%d food=%d recruited=%d lost=%d killed=%d buildingslost=%d pop=%d"), t, K.Gold, K.Food, K.Recruited, K.Lost, K.Killed, K.BuildingsLost,
					Battle->GetPopulation(t)));
			}
			Lines.Sort();
			Lines.Insert(FString::Printf(TEXT("match state=%d winner=%d clock=%d mine=%d"), int32(Battle->GetState()), Battle->GetWinner(), FMath::FloorToInt(Battle->GetClock()), UVLBattle::Mine()), 0);
			const FString Path = FPaths::ProjectSavedDir() / (FPaths::GetBaseFilename(Args[0]) + TEXT(".txt"));
			FFileHelper::SaveStringArrayToFile(Lines, *Path);
			UE_LOG(LogSovereignRealms, Log, TEXT("net dump: %d lines to %s"), Lines.Num(), *Path);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdVLNet(TEXT("vl.Net"), TEXT("vl.Net: log the multiplayer state of this game (host or joining, the players, the match, the building list)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			const UVLBattle* Battle = UVLBattle::Get(World);
			const AVLGameState* Net = VLNet::State(World);
			if (!World || !Battle)
			{
				return;
			}
			int32 Players = 0;
			for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
			{
				++Players;
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("net: %s, version %s, my team %d, %d player controller(s), match state %d, clock %.0f, %d buildings here, %d in the list, %d units"),
				World->GetNetMode() == NM_Client ? TEXT("joining game") : (World->GetNetMode() == NM_ListenServer ? TEXT("host") : TEXT("single player")), *VLNet::Version(),
				UVLBattle::Mine(), Players, int32(Battle->GetState()), Battle->GetClock(), Battle->GetBuildings().Num(), Net ? Net->Buildings.Items.Num() : 0, Battle->AllUnits().Num());
		}));
}
