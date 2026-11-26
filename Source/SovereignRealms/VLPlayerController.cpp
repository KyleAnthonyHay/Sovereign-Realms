#include "VLPlayerController.h"
#include "SovereignRealms.h"
#include "VLArrow.h"
#include "VLBattle.h"
#include "VLCommand.h"
#include "VLConstruction.h"
#include "VLKing.h"
#include "VLRocks.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/CharacterMovementComponent.h"

bool AVLPlayerController::InputGesture(const FInputDeviceId DeviceId, EGestureEvent GestureType, EGesturePhase GesturePhase,
	const FVector2D& GestureDelta, bool bIsDirectionInvertedFromDevice, const uint64 Timestamp)
{
	switch (GestureType)
	{
	case EGestureEvent::Scroll:
		Scroll += GestureDelta;       // handled here: Slate then does not turn it into mouse wheel steps as well
		return true;
	case EGestureEvent::Magnify:
		Pinch += GestureDelta.X;
		return true;
	case EGestureEvent::Rotate:
		Rotate += GestureDelta.X;
		return true;
	default:
		return Super::InputGesture(DeviceId, GestureType, GesturePhase, GestureDelta, bIsDirectionInvertedFromDevice, Timestamp);
	}
}

void AVLPlayerController::TakeGestures(FVector2D& OutScroll, float& OutPinch, float& OutRotate)
{
	OutScroll = Scroll;
	OutPinch = Pinch;
	OutRotate = Rotate;
	Scroll = FVector2D::ZeroVector;
	Pinch = Rotate = 0.f;
}

// ------------------------------------------------------------------------------------------------ multiplayer (VLNet.h)

void AVLPlayerController::BeginPlay()
{
	Super::BeginPlay();
	if (VLNet::IsClient(this) && IsLocalController() && PlayerCameraManager)
	{
		// the joining player's game looks through its own cameras (the overview's is an actor of this game alone):
		// the host's idea of the view target is not taken
		PlayerCameraManager->bClientSimulatingViewTarget = true;
	}
}

namespace
{
	/** The unit the joining player plays, if Unit is it. */
	AVLKing* VLNetOwnUnit(const AVLPlayerController* PC, AVLKing* Unit)
	{
		return (Unit && IsValid(Unit) && PC->GetPawn() == Unit) ? Unit : nullptr;
	}
}

void AVLPlayerController::ServerOrder_Implementation(const FVLNetOrder& Order)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	UVLConstruction* Construction = UVLConstruction::Get(this);
	if (!Battle || !Command || !Construction || !Battle->IsPlaying())
	{
		return;
	}
	// the host checks everything the joining game says: the units are that player's own, alive, and can be ordered
	const int32 Team = VLNet::TeamOf(this);
	TArray<AVLKing*> Units;
	for (AVLKing* U : Order.Units)
	{
		if (U && IsValid(U) && U->IsAlive() && U->Team == Team && !U->bTowerGuard && !U->bAmbient)
		{
			Units.AddUnique(U);
		}
	}
	AActor* Target = Order.Target.Building != 0 ? Battle->NetBuilding(Order.Target.Building) : Order.Target.Actor.Get();
	if (Target && !IsValid(Target))
	{
		Target = nullptr;
	}
	AVLKing* Other = Order.Other.Get();
	if (Other && (!IsValid(Other) || !Other->IsAlive() || Other->Team != Team))
	{
		Other = nullptr;
	}
	const EVLFormation Shape = EVLFormation(FMath::Clamp<int32>(Order.Shape, 0, UVLCommand::NumFormations - 1));
	const bool bOwnTarget = Target && Battle->TeamOf(Target) == Team;
	if (Units.Num() == 0 && Order.Type != EVLNetOrder::EmptyTower)
	{
		return;
	}
	if (Order.Ground.ContainsNaN() || Order.Ground.SizeSquared() > FMath::Square(4.e6))
	{
		return;         // (no point of any map is that far out)
	}
	switch (Order.Type)
	{
	case EVLNetOrder::Move:
		Command->OrderMove(Units, Order.Ground, Order.bRun, Shape, Order.bQueue);
		break;
	case EVLNetOrder::Chain:
		if (!Target || Battle->IsHostile(Target, Team))
		{
			Command->OrderChain(Units, Target, Order.Ground, Order.bRun, Shape, Order.bQueue, Other);
		}
		break;
	case EVLNetOrder::Attack:
		if (Target && (Target->ActorHasTag(TEXT("Dummy")) || Battle->IsHostile(Target, Team)))
		{
			Command->OrderAttack(Units, Target, Order.bRun, false);
		}
		break;
	case EVLNetOrder::AttackGround:
		Command->OrderAttackGround(Units, Order.Ground, Order.bRun);
		break;
	case EVLNetOrder::AttackMove:
		Command->OrderAttackMove(Units, Order.Ground, Order.bRun, Shape, Order.bQueue);
		break;
	case EVLNetOrder::Stop:
		Command->OrderStop(Units);
		break;
	case EVLNetOrder::Hold:
		Command->OrderHold(Units);
		break;
	case EVLNetOrder::PatrolRoute:
		if (Order.Points.Num() > 0 && Order.Points.Num() <= 32)
		{
			Command->OrderPatrolRoute(Units, Order.Points, Order.bRun, Shape);
		}
		break;
	case EVLNetOrder::PatrolLoop:
		if (Order.Points.Num() > 0 && Order.Points.Num() <= 32)
		{
			Command->OrderPatrol(Units, Order.Points, Order.bRun, Shape);
		}
		break;
	case EVLNetOrder::PatrolExtend:
		Command->ExtendPatrol(Units, Order.Ground, Shape);
		break;
	case EVLNetOrder::Guard:
		if (Target && Command->CanBeGuarded(Target, Team, Order.bFlag))
		{
			Command->OrderGuard(Units, Target, Order.bFlag);
		}
		break;
	case EVLNetOrder::Follow:
		if (Other)
		{
			Command->OrderFollow(Units, Other, false);
		}
		break;
	case EVLNetOrder::Garrison:
		if (bOwnTarget && UVLCommand::IsTower(Target))
		{
			Command->OrderGarrison(Units, Target, Order.bRun);
		}
		break;
	case EVLNetOrder::EmptyTower:
		if (bOwnTarget && UVLCommand::IsTower(Target))
		{
			Command->EmptyTower(Target);
		}
		break;
	case EVLNetOrder::Dismiss:
		Command->Dismiss(Units);
		break;
	case EVLNetOrder::Roam:
		Command->OrderRoam(Units);
		break;
	case EVLNetOrder::Stance:
		for (AVLKing* U : Units)
		{
			U->Stance = EVLStance(FMath::Clamp(Order.Arg, 0, 2));
		}
		break;
	case EVLNetOrder::FormUp:
		Command->FormUpNow(Units, Shape);
		break;
	case EVLNetOrder::Work:
		if (bOwnTarget)
		{
			Construction->OrderWork(Units, Target, true, Order.bQueue);
		}
		break;
	case EVLNetOrder::WorkMove:
		Construction->QueueMove(Units, Order.Ground, Order.bRun);
		break;
	case EVLNetOrder::WorkClear:
		Construction->ClearQueues(Units);
		break;
	case EVLNetOrder::Repair:
		Construction->OrderRepair(Units);
		break;
	case EVLNetOrder::ClaimMine:
		if (Target)
		{
			Construction->ClaimMine(Target, Team, Units, nullptr, false, Order.bQueue);
		}
		break;
	case EVLNetOrder::ClearRock:
		if (UVLRocks* Rocks = UVLRocks::Get(this); Rocks && Target)
		{
			Rocks->OrderClear(Units, Target, Order.bQueue);
		}
		break;
	default:
		break;
	}
}

void AVLPlayerController::ServerBuilding_Implementation(EVLNetBuildingAsk Ask, const FVLNetRef& Building, int32 Arg, const FString& Kind, const FVector& Ground)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* Construction = UVLConstruction::Get(this);
	if (!Battle || !Construction || !Battle->IsPlaying() || Ground.ContainsNaN())
	{
		return;
	}
	const int32 Team = VLNet::TeamOf(this);
	if (Ask == EVLNetBuildingAsk::BuyJonathan)
	{
		Battle->BuyJonathan(Team);
		return;
	}
	// (a building of that player's own, nobody else's)
	AActor* A = Building.Building != 0 ? Battle->NetBuilding(Building.Building) : Building.Actor.Get();
	const FVLBuildingState* B = (A && IsValid(A)) ? Battle->FindBuilding(A) : nullptr;
	if (!B || B->Team != Team)
	{
		return;
	}
	switch (Ask)
	{
	case EVLNetBuildingAsk::Train:
		Battle->Train(A, FMath::Clamp(Arg, 1, VLRules::RecruitBatchLarge), false, Kind.Left(16));
		break;
	case EVLNetBuildingAsk::Upgrade:
		Battle->Upgrade(A);
		break;
	case EVLNetBuildingAsk::SetRally:
		Battle->SetRally(A, Ground);
		break;
	case EVLNetBuildingAsk::ClearRally:
		Battle->SetRally(A, FVector::ZeroVector, true);
		break;
	case EVLNetBuildingAsk::Cancel:
		Construction->CancelSite(A);
		break;
	case EVLNetBuildingAsk::Demolish:
		Construction->Demolish(A);
		break;
	case EVLNetBuildingAsk::Rotate:
		Construction->Rotate(A);
		break;
	case EVLNetBuildingAsk::RepairCorners:
		Battle->PayCornerRepair(A);
		break;
	default:
		break;
	}
}

void AVLPlayerController::ServerPlace_Implementation(uint8 Kind, const FVector& Location, float Yaw, const TArray<AVLKing*>& Builders, bool bQueue)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* Construction = UVLConstruction::Get(this);
	if (!Battle || !Construction || !Battle->IsPlaying() || !VLBuild::Spec(EVLBuilding(Kind)) || Location.ContainsNaN() || !FMath::IsFinite(Yaw))
	{
		return;
	}
	const int32 Team = VLNet::TeamOf(this);
	TArray<AVLKing*> Crew;
	for (AVLKing* U : Builders)
	{
		if (U && IsValid(U) && U->IsAlive() && U->Team == Team)
		{
			Crew.AddUnique(U);
		}
	}
	// (PlaceBuilding checks the ground, the limits and the price again itself, and says why not to that player)
	FVLPlacement Where;
	Where.Kind = EVLBuilding(Kind);
	Where.Team = Team;
	Where.Location = Location;
	Where.Yaw = Yaw;
	Construction->PlaceBuilding(Where, Crew, nullptr, false, bQueue);
}

void AVLPlayerController::ServerSwing_Implementation(AVLKing* Unit, int32 Kind, bool bFace, float Yaw)
{
	if (AVLKing* Own = VLNetOwnUnit(this, Unit); Own && Own->IsAlive())
	{
		if (bFace && FMath::IsFinite(Yaw))
		{
			Own->SetActorRotation(FRotator(0.f, Yaw, 0.f));     // (the blow lands where that player aimed it)
		}
		Own->Attack(FMath::Clamp(Kind, -1, 2));
	}
}

void AVLPlayerController::ServerSetArmed_Implementation(AVLKing* Unit, bool bArmed)
{
	if (AVLKing* Own = VLNetOwnUnit(this, Unit))
	{
		Own->SetArmed(bArmed);
	}
}

void AVLPlayerController::ServerSetPace_Implementation(AVLKing* Unit, float MaxSpeed)
{
	if (AVLKing* Own = VLNetOwnUnit(this, Unit); Own && FMath::IsFinite(MaxSpeed))
	{
		// never faster than the unit can run
		Own->GetCharacterMovement()->MaxWalkSpeed = FMath::Clamp(MaxSpeed, 0.f, FMath::Max(Own->RunSpeed, Own->WalkSpeed));
	}
}

void AVLPlayerController::ServerSetHero_Implementation(AVLKing* Unit, bool bHero)
{
	if (AVLKing* Own = VLNetOwnUnit(this, Unit))
	{
		Own->NetSetHero(bHero);
	}
}

void AVLPlayerController::ServerOrderDone_Implementation(AVLKing* Unit, bool bArrived, bool bStopped)
{
	if (AVLKing* Own = VLNetOwnUnit(this, Unit))
	{
		Own->NetFinishOrder(bArrived, bStopped);
	}
}

void AVLPlayerController::ServerReady_Implementation()
{
	bNetReady = true;
	UE_LOG(LogSovereignRealms, Log, TEXT("multiplayer: the joining player's game is ready"));
}

void AVLPlayerController::ClientAlert_Implementation(const FString& Text, uint8 Kind, bool bHasAt, const FVector& At)
{
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		Battle->PushAlert(Text, EVLAlert(FMath::Min<uint8>(Kind, uint8(EVLAlert::Good))), bHasAt ? &At : nullptr);
	}
}

void AVLPlayerController::ClientSound_Implementation(FName Base, bool bAt, const FVector& At, float Volume, float Range)
{
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		const FString Name = Base.ToString();
		if (bAt)
		{
			Battle->PlayAt(*Name, At, Volume, Range, 0.03f);
		}
		else
		{
			Battle->Play2D(*Name, Volume);
		}
	}
}

void AVLPlayerController::ClientPopup_Implementation(const FVector& At, int32 Amount, bool bGold)
{
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		Battle->AddPopup(At, Amount, bGold);
	}
}

void AVLPlayerController::ClientArrows_Implementation(const TArray<FVLNetArrow>& Arrows)
{
	if (UVLArrows* Show = UVLArrows::Get(this))
	{
		for (const FVLNetArrow& A : Arrows)
		{
			Show->NetShow(A);
		}
	}
}

void AVLPlayerController::ClientFollowPath_Implementation(AVLKing* Unit, const TArray<FVector>& Points, bool bRun)
{
	if (AVLKing* Own = VLNetOwnUnit(this, Unit))
	{
		Own->FollowPath(Points, bRun);
	}
}

void AVLPlayerController::ClientStopOrder_Implementation(AVLKing* Unit)
{
	if (AVLKing* Own = VLNetOwnUnit(this, Unit))
	{
		Own->NetFinishOrder(false, true);
	}
}

void AVLPlayerController::ClientRockCleared_Implementation(AActor* Rock)
{
	if (UVLRocks* Rocks = UVLRocks::Get(this); Rocks && Rock)
	{
		Rocks->Clear(Rock, false);
	}
}

void AVLPlayerController::ClientMatchClosed_Implementation(const FString& Why)
{
	if (UVLNetSession* Session = UVLNetSession::Get(this))
	{
		Session->Leave(this, Why);
	}
}
