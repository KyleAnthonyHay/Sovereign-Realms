#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "Net/Serialization/FastArraySerializer.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "VLNet.generated.h"

class AVLKing;
class AVLGameState;
class AVLPlayerController;
class UVLBattle;
struct FVLBuildingState;

/**
 * MULTIPLAYER (stage one: two players head to head on a LAN; Docs/Multiplayer/DESIGN.md).
 *
 * The conventional Unreal set-up, nothing of our own underneath it: one player's game is a LISTEN SERVER (the map is
 * opened with ?listen), the other's connects to it by address, and the engine's replication carries the match. The
 * host's game is the only one that runs the rules: the battle, the economy, the orders, the fights. The joining game
 * shows what it is sent and asks for what its player wants:
 *
 *   units        AVLKing replicates (its place by the engine's replicated movement, its side, health, death, sword and
 *                bow); a unit the joining player plays is predicted by its CharacterMovementComponent as in any game
 *   buildings    the battle's building list is mirrored through a fast array on the game state (AVLGameState); the
 *                joining game raises, finishes and fells its own copies of them from that list
 *   the kingdom  gold, food, the counts and the match's state: plain replicated properties of the game state
 *   orders       every order function (UVLCommand's, UVLBattle::Train / Upgrade, UVLConstruction::PlaceBuilding ...)
 *                turns itself into a Server RPC on the joining side (AVLPlayerController::ServerOrder and friends);
 *                the host checks that the units and buildings are that player's, then calls the same function
 *   feedback     alerts, sounds, payout numbers and arrows reach the joining player as Client RPCs
 *
 * Everything here is behind the net mode: in a single-player game (NM_Standalone) none of it runs, every unit has
 * authority, and UVLBattle::Mine() is team 0 as it always was.
 *
 * Teams: the host is team 0 (green, the single-player side), the joining player team 1 (red, the commander's side in
 * single player; the commander is off in a multiplayer match).
 */
namespace VLNet
{
	/** Bumped whenever what the two games send each other changes: a game of another number is refused at the door. */
	constexpr int32 Protocol = 1;
	constexpr int32 DefaultPort = 7777;
	/** "<project version>-mp<Protocol>": what a joining game shows the host (?VLVer=), and the host compares. */
	FString Version();
	/** The joining player's game (NM_Client). */
	bool IsClient(const UObject* WorldContext);
	/** The hosting player's game (NM_ListenServer). */
	bool IsHost(const UObject* WorldContext);
	inline bool IsMultiplayer(const UObject* WorldContext) { return IsClient(WorldContext) || IsHost(WorldContext); }
	/** This game's own player controller (the host's own on a listen server, never the remote player's). */
	AVLPlayerController* LocalController(const UObject* WorldContext);
	/** The host's side: the controller of the player who joined (team 1), or null. */
	AVLPlayerController* RemoteController(const UObject* WorldContext);
	/** The side a player controller commands (the host's 0, the joining player's 1). */
	int32 TeamOf(const class APlayerController* PC);
	AVLGameState* State(const UObject* WorldContext);
	/** This machine's addresses on the local network ("192.168.1.20"), for the host's "tell the other player" line. */
	FString LocalAddresses();
}

/** A unit kind by its name and back (training queues travel as numbers). */
namespace VLNetKinds
{
	uint8 ToByte(const FString& Kind);
	FString ToName(uint8 Kind);
}

/**
 * Something an order points at, in a form both games understand: a unit (replicated: its pointer), an actor of the
 * level (the same name in both games: its pointer), or a building raised in the match (each game has its own copy:
 * the battle's number for it).
 */
USTRUCT()
struct FVLNetRef
{
	GENERATED_BODY()

	UPROPERTY()
	TObjectPtr<AActor> Actor = nullptr;

	UPROPERTY()
	int32 Building = 0;
};

/** One order from the joining player (AVLPlayerController::ServerOrder). Which fields count depends on Type. */
UENUM()
enum class EVLNetOrder : uint8
{
	Move,           // Ground, Shape, bRun, bQueue
	Chain,          // Target (or Ground), Shape, bRun, bQueue, Other (rejoin)
	Attack,         // Target (a training dummy), bRun
	AttackGround,   // Ground, bRun
	AttackMove,     // Ground, Shape, bRun, bQueue
	Stop,
	Hold,
	PatrolRoute,    // Points, Shape, bRun
	Guard,          // Target, bFlag (any troop may be the ward)
	Follow,         // Other (the leader)
	Garrison,       // Target (the tower), bRun
	EmptyTower,     // Target
	Dismiss,
	Roam,
	Stance,         // Arg (EVLStance)
	FormUp,         // Shape
	Work,           // Target (a site, a damaged building), bQueue: the Builders among Units
	WorkMove,       // Ground, bRun: a walk on the end of the Builders' queues
	WorkClear,      // the Builders' queues dropped
	Repair,         // the Builders go and mend the nearest damaged building
	ClaimMine,      // Target (the mine), bQueue
	ClearRock,      // Target (a rock of the level), bQueue: the Builders among Units
	PatrolLoop,     // Points, Shape, bRun: from where they stand round the points (UVLCommand::OrderPatrol)
	PatrolExtend    // Ground, Shape: one more point of the patrol they are on
};

USTRUCT()
struct FVLNetOrder
{
	GENERATED_BODY()

	UPROPERTY()
	EVLNetOrder Type = EVLNetOrder::Stop;

	UPROPERTY()
	TArray<TObjectPtr<AVLKing>> Units;

	UPROPERTY()
	FVLNetRef Target;

	UPROPERTY()
	TObjectPtr<AVLKing> Other = nullptr;

	UPROPERTY()
	FVector Ground = FVector::ZeroVector;

	UPROPERTY()
	TArray<FVector> Points;

	UPROPERTY()
	uint8 Shape = 0;

	UPROPERTY()
	int32 Arg = 0;

	UPROPERTY()
	bool bRun = false;

	UPROPERTY()
	bool bQueue = false;

	UPROPERTY()
	bool bFlag = false;
};

/** What the joining player asks of a building (AVLPlayerController::ServerBuilding). */
UENUM()
enum class EVLNetBuildingAsk : uint8
{
	Train,          // Arg: how many, Kind: which troop (empty: its own)
	Upgrade,
	SetRally,       // Ground
	ClearRally,
	Cancel,         // a site
	Demolish,
	Rotate,
	RepairCorners,  // the castle's corners: paid for
	BuyJonathan     // (no building: the kingdom's)
};

/** An arrow loosed on the host, for the joining game to draw (it flies and lands there by the same code, harmless). */
USTRUCT()
struct FVLNetArrow
{
	GENERATED_BODY()

	UPROPERTY()
	FVector_NetQuantize10 Tip;

	UPROPERTY()
	FVector_NetQuantize10 Velocity;

	UPROPERTY()
	float Gravity = 980.f;

	UPROPERTY()
	int8 Team = -1;

	UPROPERTY()
	TObjectPtr<AActor> Ignore = nullptr;
};

namespace VLNet
{
	/** What Actor is to both games (see FVLNetRef). */
	FVLNetRef MakeRef(const UObject* WorldContext, AActor* Actor);
	/**
	 * The joining player's game: the order goes to the host (AVLPlayerController::ServerOrder) and true comes back: the
	 * caller, one of the order functions, does nothing more than show the order was given. Anywhere else (the host, a
	 * single-player game): false, and the caller carries the order out.
	 */
	bool SendOrder(const UObject* WorldContext, EVLNetOrder Type, const TArray<AVLKing*>& Units, AActor* Target = nullptr, const FVector& Ground = FVector::ZeroVector,
		bool bRun = false, bool bQueue = false, uint8 Shape = 0, AVLKing* Other = nullptr, int32 Arg = 0, bool bFlag = false, const TArray<FVector>* Points = nullptr);
	/** The same for what is asked of a building or the kingdom (AVLPlayerController::ServerBuilding). */
	bool SendBuilding(const UObject* WorldContext, EVLNetBuildingAsk Ask, AActor* Building, int32 Arg = 0, const FString& Kind = FString(), const FVector& Ground = FVector::ZeroVector);
}

/** A building of the battle as the joining game is told of it (FVLBuildingState, without what only the host needs). */
USTRUCT()
struct FVLNetBuilding : public FFastArraySerializerItem
{
	GENERATED_BODY()

	/** The battle's number for it (FVLBuildingState::NetId): never 0, never reused in a match. */
	UPROPERTY()
	int32 Id = 0;

	/** The level's own actor (the same in both games), or null for one raised in the match. */
	UPROPERTY()
	TObjectPtr<AActor> LevelActor = nullptr;

	UPROPERTY()
	uint8 Kind = 0;

	UPROPERTY()
	int8 Team = 0;

	UPROPERTY()
	FString Mesh;

	UPROPERTY()
	FVector_NetQuantize10 Location;

	UPROPERTY()
	float Yaw = 0.f;

	UPROPERTY()
	float Health = 0.f;

	UPROPERTY()
	float MaxHealth = 0.f;

	UPROPERTY()
	uint8 Level = 1;

	UPROPERTY()
	float UpgradeLeft = -1.f;

	UPROPERTY()
	float UpgradeTotal = 0.f;

	UPROPERTY()
	float Build = 1.f;

	/** 1 fallen, 2 under repair, 4 raised in the match, 8 a mine being claimed, 16 a mine that was neutral, 32 a rally point */
	UPROPERTY()
	uint8 Flags = 0;

	UPROPERTY()
	uint8 BuildersAt = 0;

	UPROPERTY()
	TArray<uint8> Queue;

	UPROPERTY()
	float TrainClock = 0.f;

	UPROPERTY()
	FVector_NetQuantize10 Rally;

	UPROPERTY()
	int32 PaidGold = 0;

	UPROPERTY()
	int32 PaidFood = 0;

	// the castle's corners
	UPROPERTY()
	float CornerHealth[4] = { 0.f, 0.f, 0.f, 0.f };

	/** bits 0-3: knocked out, bits 4-7: its repair is paid for */
	UPROPERTY()
	uint8 CornerBits = 0;

	UPROPERTY()
	uint8 CornerLevel = 0;

	void PreReplicatedRemove(const struct FVLNetBuildingArray& Array);
	void PostReplicatedAdd(const struct FVLNetBuildingArray& Array);
	void PostReplicatedChange(const struct FVLNetBuildingArray& Array);

	bool SameAs(const FVLNetBuilding& O) const;
};

USTRUCT()
struct FVLNetBuildingArray : public FFastArraySerializer
{
	GENERATED_BODY()

	UPROPERTY()
	TArray<FVLNetBuilding> Items;

	/** (not replicated) the game state that holds it */
	UPROPERTY(NotReplicated)
	TObjectPtr<AVLGameState> Owner = nullptr;

	bool NetDeltaSerialize(FNetDeltaSerializeInfo& DeltaParms)
	{
		return FFastArraySerializer::FastArrayDeltaSerialize<FVLNetBuilding, FVLNetBuildingArray>(Items, DeltaParms, *this);
	}
};

template<>
struct TStructOpsTypeTraits<FVLNetBuildingArray> : public TStructOpsTypeTraitsBase2<FVLNetBuildingArray>
{
	enum { WithNetDeltaSerializer = true };
};

/** A kingdom's numbers (FVLKingdom's, as far as the interface shows them). */
USTRUCT()
struct FVLNetKingdom
{
	GENERATED_BODY()

	UPROPERTY()
	int32 Gold = 0;

	UPROPERTY()
	int32 Food = 0;

	UPROPERTY()
	int32 Recruited = 0;

	UPROPERTY()
	int32 Lost = 0;

	UPROPERTY()
	int32 Killed = 0;

	UPROPERTY()
	int32 BuildingsLost = 0;

	UPROPERTY()
	int32 SpyCooldown = 0;          // whole seconds

	UPROPERTY()
	int32 JonathanWait = 0;         // whole seconds

	/** 1 has a castle, 2 Jonathan bought, 4 Jonathan has come */
	UPROPERTY()
	uint8 Flags = 0;

	bool operator==(const FVLNetKingdom& O) const
	{
		return Gold == O.Gold && Food == O.Food && Recruited == O.Recruited && Lost == O.Lost && Killed == O.Killed && BuildingsLost == O.BuildingsLost
			&& SpyCooldown == O.SpyCooldown && JonathanWait == O.JonathanWait && Flags == O.Flags;
	}
};

/** The match's state. */
USTRUCT()
struct FVLNetMatch
{
	GENERATED_BODY()

	UPROPERTY()
	uint8 State = 0;                // EVLMatch

	UPROPERTY()
	bool bBattle = false;

	UPROPERTY()
	int8 Winner = -1;

	UPROPERTY()
	int32 Clock = 0;                // whole seconds

	/** The other player has gone: the match is over for whoever is left (the note says why). */
	UPROPERTY()
	bool bAbandoned = false;

	bool operator==(const FVLNetMatch& O) const
	{
		return State == O.State && bBattle == O.bBattle && Winner == O.Winner && Clock == O.Clock && bAbandoned == O.bAbandoned;
	}
};

/**
 * The game state of a match: what the joining game is told about the battle (see VLNet above). The host fills it from
 * UVLBattle once a frame (Push); the joining game's UVLBattle is filled from it as it arrives (the OnRep functions and
 * the fast array's callbacks), so the interface there reads UVLBattle exactly as it does in a single-player game.
 */
UCLASS()
class SOVEREIGNREALMS_API AVLGameState : public AGameStateBase
{
	GENERATED_BODY()

public:
	AVLGameState();
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** The host: the battle's state into the replicated copies (only what changed is marked and sent). */
	void Push(UVLBattle& Battle);

	UPROPERTY(Replicated)
	FVLNetBuildingArray Buildings;

	UPROPERTY(ReplicatedUsing = OnRep_Kingdoms)
	FVLNetKingdom Kingdoms[2];

	UPROPERTY(ReplicatedUsing = OnRep_Match)
	FVLNetMatch Match;

	UFUNCTION()
	void OnRep_Kingdoms();

	UFUNCTION()
	void OnRep_Match();

	/** The joining game: something of the building list arrived (the list is gone through in the next tick). */
	bool bListDirty = false;

private:
	/** The joining game: each entry as it was last given to this game's battle (UVLConstruction::NetApplyBuilding), so
	 *  that only what changed is done again; one that could not be applied yet (its level actor not there) is tried
	 *  again twice a second. */
	UPROPERTY(Transient)
	TMap<int32, FVLNetBuilding> Applied;
	float PendingClock = 0.f;
};

/**
 * Hosting and joining (the menu's Multiplayer screen, vl.Host / vl.Join, -VLHost= / -VLJoin=). LAN and direct address
 * for now: Host opens the map as a listen server, Join travels to "address:port". This is the one place that knows how
 * the two games find each other: Epic Online Services (sessions, invites, NAT relay through the engine's online
 * subsystem) goes in behind these same calls later.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLNetSession : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	static UVLNetSession* Get(const UObject* WorldContext);
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** Opens Map (an index of AVLHUD's maps) as a listen server; the match starts when the other player is in. */
	void Host(const UObject* WorldContext, int32 Map);
	/** Connects to a host: "192.168.1.20" or "192.168.1.20:7777". False: no address. */
	bool Join(const UObject* WorldContext, const FString& Address);
	/** Leaves the match (the host: ends it for both) and goes back to the title screen. */
	void Leave(const UObject* WorldContext, const FString& Why = FString());

	/** What the title screen shows after a match that could not be joined or was cut off ("The host runs another
	 *  version", "The connection was lost"); empty when there is nothing to say. Cleared by Host / Join. */
	const FString& GetNote() const { return Note; }
	void SetNote(const FString& InNote) { Note = InNote; }
	/** Trying to reach a host now. */
	bool IsJoining() const { return bJoining; }
	const FString& GetLastAddress() const { return LastAddress; }

private:
	void OnNetworkFailure(UWorld* World, class UNetDriver* Driver, ENetworkFailure::Type Type, const FString& Error);
	void OnTravelFailure(UWorld* World, ETravelFailure::Type Type, const FString& Error);
	void OnPostLoadMap(UWorld* World);
	FString Note;
	FString LastAddress;
	bool bJoining = false;
	bool bLeaving = false;
	FDelegateHandle NetFailHandle, TravelFailHandle, PostLoadHandle;
};
