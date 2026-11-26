#include "VLTroopShip.h"
#include "VLNet.h"

#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLCommand.h"
#include "VLGameMode.h"
#include "VLGrid.h"
#include "VLKing.h"
#include "VLTroopShipDeck.inl"

#include "Async/ParallelFor.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInterface.h"
#include "TimerManager.h"

namespace
{
	namespace Deck = VLTroopShipDeck;

	constexpr float PlankWalk = 340.f;          // cm a second on the gangplank and the deck (a walk)
	constexpr float PlankDropSeconds = 0.3f;    // the gangplank dropping out as it docks
	constexpr float BoardNear = 380.f;          // a unit this near the gangplank's foot goes up it
	constexpr float BoardEvery = 0.3f;          // seconds between two units setting foot on it
	constexpr float ChartMargin = 3000.f;       // the chart reaches this far beyond the ground's bounds
	constexpr float SideGap = 55.f;             // the water kept between the hull and a quay it lies alongside
	constexpr float MaxSlide = 900.f;           // the furthest it comes sideways to lie alongside
	constexpr float LandDown = 190.f, LandUp = 120.f;   // ground this far under / over the entry port's sill takes the gangplank

	FVector2D Dir2D(float YawDeg)
	{
		const float R = FMath::DegreesToRadians(YawDeg);
		return FVector2D(FMath::Cos(R), FMath::Sin(R));
	}

	void Alert(const UObject* Context, const FString& Text, const FVector& At)
	{
		if (UVLBattle* Battle = UVLBattle::Get(Context))
		{
			Battle->PushAlert(Text, EVLAlert::Info, &At);
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s"), *Text);
	}

	/** Does a vertical ray through the water at P meet nothing down to a ship's draught? */
	bool ClearWater(const UWorld* World, const FVector2D& P, float SeaZ, const FCollisionQueryParams& Params)
	{
		return !World->LineTraceTestByChannel(FVector(P.X, P.Y, SeaZ + 2200.f), FVector(P.X, P.Y, SeaZ - Deck::Draught - 40.f), ECC_Visibility, Params);
	}

	FCollisionQueryParams ChartParams(const UWorld* World)
	{
		FCollisionQueryParams Params(SCENE_QUERY_STAT(VLFleet), true);
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			if (It->IsA<APawn>() || It->IsA<AVLTroopShip>() || UVLGrid::IsUnseen(*It) || It->ActorHasTag(TEXT("Moored")))
			{
				Params.AddIgnoredActor(*It);
			}
		}
		return Params;
	}
}

// ================================================================================================ the ship

AVLTroopShip::AVLTroopShip()
{
	PrimaryActorTick.bCanEverTick = true;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	SetRootComponent(Root);
	Hull = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Hull"));
	Hull->SetupAttachment(Root);
	Hull->SetMobility(EComponentMobility::Movable);
	Hull->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
	Hull->SetCanEverAffectNavigation(false);
	Plank = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Gangplank"));
	Plank->SetupAttachment(Root);
	Plank->SetMobility(EComponentMobility::Movable);
	Plank->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
	Plank->SetCanEverAffectNavigation(false);
	Plank->SetVisibility(false);
	for (const FVector& P : Deck::Main) { Places.Add({ P, 0 }); }
	for (const FVector& P : Deck::Fore) { Places.Add({ P, 1 }); }
	for (const FVector& P : Deck::Stern) { Places.Add({ P, 2 }); }
}

void AVLTroopShip::BeginPlay()
{
	Super::BeginPlay();
	if (UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Voxel/Meshes/SM_TroopShip.SM_TroopShip"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Hull->SetStaticMesh(M);
	}
	else
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("ship: /Game/Voxel/Meshes/SM_TroopShip is not imported"));
	}
	if (UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Voxel/Meshes/SM_TroopShip_Gangplank.SM_TroopShip_Gangplank"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Plank->SetStaticMesh(M);
	}
	SeaZ = GetActorLocation().Z;
	BobClock = FMath::Fmod(float(GetUniqueID() % 97) * 0.37f, 6.f);
	SetTeam(Team);
}

void AVLTroopShip::SetTeam(int32 InTeam)
{
	Team = InTeam;
	// (its name for the panel and vl.Select; it is no building: nothing with a Team or a Selectable tag)
	Tags.RemoveAll([](const FName& T) { return T.ToString().StartsWith(TEXT("Name:")); });
	Tags.Add(Team == UVLBattle::Enemy ? TEXT("Name:Enemy Troop Ship") : TEXT("Name:Troop Ship"));
	UStaticMesh* M = Hull ? Hull->GetStaticMesh() : nullptr;
	if (!M)
	{
		return;
	}
	// the enemy's cloth is red (MI_Vox_cloth_Enemy, as the level builder gives its buildings and its moored ship)
	UMaterialInterface* Red = Team == UVLBattle::Enemy ? LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Voxel/Materials/MI_Vox_cloth_Enemy.MI_Vox_cloth_Enemy"), nullptr, LOAD_NoWarn | LOAD_Quiet) : nullptr;
	const TArray<FName> Slots = Hull->GetMaterialSlotNames();
	for (int32 i = 0; i < Slots.Num(); ++i)
	{
		const bool bCloth = Slots[i].ToString().Contains(TEXT("cloth"));
		Hull->SetMaterial(i, bCloth && Red ? Red : M->GetMaterial(i));
	}
}

int32 AVLTroopShip::Capacity()
{
	return UE_ARRAY_COUNT(Deck::Main) + UE_ARRAY_COUNT(Deck::Fore);
}

AVLTroopShip* AVLTroopShip::Of(const AVLKing* Unit)
{
	return Unit ? Cast<AVLTroopShip>(Unit->GarrisonIn.Get()) : nullptr;
}

bool AVLTroopShip::IsHero(const AVLKing* Unit) const
{
	return Unit && (!Unit->IsTroop() || Unit->IsJonathan());
}

int32 AVLTroopShip::PlaceOf(const AVLKing* Unit) const
{
	return Places.IndexOfByPredicate([Unit](const FPlace& P) { return P.Unit.Get() == Unit; });
}

int32 AVLTroopShip::FreePlace(const AVLKing* Unit) const
{
	// the heroes on the stern castle; archers on the forecastle first, soldiers on the main deck first
	const bool bHero = IsHero(Unit);
	const uint8 Order[2] = { uint8(Unit->IsRanged() ? 1 : 0), uint8(Unit->IsRanged() ? 0 : 1) };
	for (int32 Pass = 0; Pass < (bHero ? 1 : 2); ++Pass)
	{
		const uint8 Kind = bHero ? 2 : Order[Pass];
		for (int32 i = 0; i < Places.Num(); ++i)
		{
			if (Places[i].Kind == Kind && !Places[i].Unit.IsValid())
			{
				return i;
			}
		}
	}
	return INDEX_NONE;
}

FVector AVLTroopShip::PlaceWorld(int32 Place) const
{
	return Hull->GetComponentTransform().TransformPosition(Places[Place].Local);
}

FVector AVLTroopShip::GateWorld(int32 Side) const
{
	return GetActorTransform().TransformPosition(FVector(Deck::GateX, Side * Deck::GateY, Deck::GateZ));
}

void AVLTroopShip::GetAboard(TArray<AVLKing*>& Out) const
{
	Out.Reset();
	for (const FPlace& P : Places)
	{
		if (P.bAboard && P.Unit.IsValid())
		{
			Out.Add(P.Unit.Get());
		}
	}
}

int32 AVLTroopShip::NumAboard() const
{
	int32 N = 0;
	for (const FPlace& P : Places)
	{
		N += (P.bAboard && P.Unit.IsValid()) ? 1 : 0;
	}
	return N;
}

int32 AVLTroopShip::NumComing() const
{
	int32 N = 0;
	for (const FPlace& P : Places)
	{
		N += (!P.bAboard && P.Unit.IsValid()) ? 1 : 0;
	}
	return N;
}

void AVLTroopShip::Seat(AVLKing* Unit, int32 Place)
{
	FPlace& P = Places[Place];
	P.Unit = Unit;
	P.bAboard = true;
	Unit->StopOrder();
	Unit->ClearQueue();
	Unit->PendingGarrison = nullptr;
	Unit->GarrisonIn = this;
	Unit->SetMovementAwake(true);
	UCharacterMovementComponent* Move = Unit->GetCharacterMovement();
	Move->StopMovementImmediately();
	Move->DisableMovement();            // (the deck has no collision: it stands where the ship puts it, and rides with the hull)
	Unit->AttachToComponent(Hull, FAttachmentTransformRules::KeepWorldTransform);
	const float Half = Unit->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	Unit->SetActorLocationAndRotation(PlaceWorld(Place) + FVector(0.f, 0.f, Half + 2.f), FRotator(0.f, GetActorRotation().Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
}

void AVLTroopShip::Release(AVLKing* Unit, const FVector& Feet, float Yaw)
{
	Unit->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
	Unit->GarrisonIn = nullptr;
	const float Half = Unit->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	Unit->SetActorLocationAndRotation(Feet + FVector(0.f, 0.f, Half + 4.f), FRotator(0.f, Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
	Unit->SetActorScale3D(FVector::OneVector);
	UCharacterMovementComponent* Move = Unit->GetCharacterMovement();
	Move->SetMovementMode(MOVE_Walking);
	Move->StopMovementImmediately();
	Move->bForceNextFloorCheck = true;
	Unit->SetMovementAwake(true);
}

bool AVLTroopShip::PutAboard(AVLKing* Unit)
{
	if (!Unit || Unit->IsDead() || PlaceOf(Unit) != INDEX_NONE || Of(Unit))
	{
		return false;
	}
	const int32 Place = FreePlace(Unit);
	if (Place == INDEX_NONE)
	{
		return false;
	}
	if (UVLCommand* Command = UVLCommand::Get(this))
	{
		Command->OrderStop({ Unit });
	}
	Seat(Unit, Place);
	return true;
}

int32 AVLTroopShip::OrderBoard(const TArray<AVLKing*>& Units, bool bRun)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return 0;
	}
	if (!bLanded || IsSailing())
	{
		if (Units.Num() > 0 && Units[0] && Units[0]->Team == UVLBattle::Player)
		{
			Alert(this, IsSailing() ? TEXT("The ship is under way: nobody boards it") : TEXT("The ship lies off the shore: bring it to a quay or a shore to board it"), GetActorLocation());
		}
		return 0;
	}
	TArray<AVLKing*> Going;
	int32 Left = 0;
	for (AVLKing* U : Units)
	{
		if (!U || U->IsDead() || U->Team != Team || U->bTowerGuard || U->bAmbient || Of(U) || PlaceOf(U) != INDEX_NONE)
		{
			continue;
		}
		const int32 Place = FreePlace(U);
		if (Place == INDEX_NONE)
		{
			++Left;
			continue;
		}
		Places[Place].Unit = U;
		Places[Place].bAboard = false;
		Going.Add(U);
	}
	if (Going.Num() > 0)
	{
		Command->OrderMove(Going, LandPoint, bRun, EVLFormation::Column);
		for (AVLKing* U : Going)
		{
			U->PendingGarrison = this;      // (OrderMove ends whatever it was walking to: this is its errand now)
		}
	}
	if (Left > 0 && Team == UVLBattle::Player)
	{
		Alert(this, FString::Printf(TEXT("The ship is full: %d stay ashore"), Left), GetActorLocation());
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("ship: %d unit(s) ordered aboard %s (%d aboard, %d coming, %d left ashore)"), Going.Num(), *GetName(), NumAboard(), NumComing(), Left);
	return Going.Num();
}

int32 AVLTroopShip::Unload()
{
	if (!bLanded || IsSailing())
	{
		if (Team == UVLBattle::Player)
		{
			Alert(this, TEXT("The ship lies off the shore: bring it to a quay or a shore to land"), GetActorLocation());
		}
		return 0;
	}
	TArray<AVLKing*> Units;
	for (const FPlace& P : Places)
	{
		AVLKing* U = P.Unit.Get();
		if (P.bAboard && U && U->IsAlive() && !Walks.ContainsByPredicate([U](const FWalk& W) { return W.Unit.Get() == U; }))
		{
			Units.Add(U);
		}
	}
	if (Units.Num() == 0)
	{
		return 0;
	}
	// where they form up: a few steps inland of the gangplank's foot, in a block
	const FVector Gate = GateWorld(LandSide);
	const FVector Inland = (LandPoint - Gate).GetSafeNormal2D();
	FVector Muster = LandPoint + Inland * 650.f;
	TArray<FVector> Spots;
	UVLGrid* Grid = UVLGrid::Get(this);
	if (Grid && Grid->EnsureBuilt())
	{
		const int32 Node = Grid->NearestNode(Muster, 30, Grid->MainRegion());
		if (Node != INDEX_NONE)
		{
			Muster = Grid->NodePos(Node);
		}
		TArray<FVector2D> Slots;
		VLFormation::ComputeSlots(Units, FVector2D(Muster), Slots, EVLFormation::Square);
		Grid->FitSlots(Muster, Slots, Spots);
	}
	for (int32 i = 0; i < Units.Num(); ++i)
	{
		FWalk W;
		W.Unit = Units[i];
		W.Place = PlaceOf(Units[i]);
		W.bOff = true;
		W.Delay = i * BoardEvery;
		W.Shore = LandPoint;
		W.Muster = Spots.IsValidIndex(i) ? Spots[i] : Muster;
		Walks.Add(W);
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s unloads %d unit(s) at %s, mustering at %s"), *GetName(), Units.Num(), *LandPoint.ToCompactString(), *Muster.ToCompactString());
	return Units.Num();
}

void AVLTroopShip::Disembark(AVLKing* Unit)
{
	const int32 Place = PlaceOf(Unit);
	if (!Unit || Place == INDEX_NONE)
	{
		if (Unit && Unit->GarrisonIn.Get() == this)
		{
			Unit->GarrisonIn = nullptr;
		}
		return;
	}
	if (Unit->IsDead())
	{
		Walks.RemoveAll([Unit](const FWalk& W) { return W.Unit.Get() == Unit; });
		Places[Place].Unit = nullptr;
		Places[Place].bAboard = false;
		Unit->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
		Unit->GarrisonIn = nullptr;
		return;
	}
	if (!Places[Place].bAboard)
	{
		return;                 // on its way to the ship: its place goes when its errand does (TickTroops)
	}
	if (!bLanded || IsSailing())
	{
		return;                 // at sea: it stays aboard (TickTroops drops the order it was given)
	}
	Walks.RemoveAll([Unit](const FWalk& W) { return W.Unit.Get() == Unit; });
	Places[Place].Unit = nullptr;
	Places[Place].bAboard = false;
	// beside whoever stands at the gangplank's foot already
	FVector Spot = LandPoint;
	const FVector Inland = (LandPoint - GateWorld(LandSide)).GetSafeNormal2D();
	if (UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->EnsureBuilt())
	{
		int32 Down = 0;
		if (const UVLBattle* Battle = UVLBattle::Get(this))
		{
			for (const AVLKing* Other : Battle->AllUnits())
			{
				Down += (Other != Unit && !Other->GarrisonIn.IsValid() && FVector::Dist2D(Other->GetFeet(), LandPoint) < 420.f) ? 1 : 0;
			}
		}
		const FVector Side(-Inland.Y, Inland.X, 0.f);
		TArray<FVector2D> Spots;
		TArray<FVector> Fitted;
		for (int32 i = 0; i <= Down; ++i)
		{
			Spots.Add(FVector2D(LandPoint + Inland * (60.f + (i / 3) * 125.f) + Side * (((i % 3) - 1) * 125.f)));
		}
		Grid->FitSlots(LandPoint, Spots, Fitted);
		if (Fitted.Num() > 0)
		{
			Spot = Fitted.Last();
		}
	}
	Release(Unit, Spot, Inland.Rotation().Yaw);
	UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s steps ashore from %s"), *Unit->GetDisplayName(), *GetName());
}

void AVLTroopShip::HoldAboard(TArray<AVLKing*>& Units)
{
	const AVLTroopShip* Held = nullptr;
	bool bPlayers = false;
	Units.RemoveAll([&Held, &bPlayers](const AVLKing* U)
	{
		const AVLTroopShip* Ship = Of(U);
		const int32 Place = Ship ? Ship->PlaceOf(U) : INDEX_NONE;
		const bool bWalking = Ship && Ship->Walks.ContainsByPredicate([U](const FWalk& W) { return W.Unit.Get() == U; });
		if (Ship && Place != INDEX_NONE && Ship->Places[Place].bAboard && (!Ship->bLanded || Ship->IsSailing() || bWalking))
		{
			Held = Ship;
			bPlayers |= U->Team == UVLBattle::Player && !bWalking;
			return true;
		}
		return false;
	});
	if (Held && bPlayers)
	{
		Alert(Held, TEXT("They are aboard the ship at sea: bring it to a quay or a shore to land them"), Held->GetActorLocation());
	}
}

void AVLTroopShip::WalkPoints(const FWalk& W, FVector Out[4]) const
{
	const FVector Gate = Hull->GetComponentTransform().TransformPosition(FVector(Deck::GateX, LandSide * (Deck::GateY - 40.f), Deck::GateZ));
	const FVector Place = Places.IsValidIndex(W.Place) ? PlaceWorld(W.Place) : Gate;
	if (W.bOff)
	{
		Out[0] = Place;
		Out[1] = Gate;
		Out[2] = LandPoint;
		Out[3] = W.Shore;
	}
	else
	{
		Out[0] = W.Shore;
		Out[1] = LandPoint;
		Out[2] = Gate;
		Out[3] = Place;
	}
}

void AVLTroopShip::TickWalks(float Dt)
{
	UVLCommand* Command = UVLCommand::Get(this);
	for (int32 i = 0; i < Walks.Num(); ++i)
	{
		FWalk& W = Walks[i];
		AVLKing* U = W.Unit.Get();
		if (!U || U->IsDead() || U->GarrisonIn.Get() != this || !Places.IsValidIndex(W.Place) || Places[W.Place].Unit.Get() != U)
		{
			Walks.RemoveAt(i--);
			continue;
		}
		W.Delay -= Dt;
		if (W.Delay > 0.f)
		{
			continue;
		}
		FVector P[4];
		WalkPoints(W, P);
		const float L[3] = { float(FVector::Dist(P[0], P[1])), float(FVector::Dist(P[1], P[2])), float(FVector::Dist(P[2], P[3])) };
		W.T += PlankWalk * Dt;
		float S = W.T;
		int32 Leg = 0;
		while (Leg < 2 && S > L[Leg])
		{
			S -= L[Leg++];
		}
		const float Half = U->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
		if (Leg == 2 && S >= L[2])
		{
			// there
			if (W.bOff)
			{
				const FVector Muster = W.Muster;
				Places[W.Place].Unit = nullptr;
				Places[W.Place].bAboard = false;
				Release(U, P[3], (P[3] - P[1]).Rotation().Yaw);
				Walks.RemoveAt(i--);
				if (Command && !Muster.IsZero())
				{
					Command->OrderMove({ U }, Muster, false, EVLFormation::Loose);
				}
			}
			else
			{
				U->SetActorLocationAndRotation(P[3] + FVector(0.f, 0.f, Half + 2.f), FRotator(0.f, GetActorRotation().Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
				U->GetCharacterMovement()->Velocity = FVector::ZeroVector;
				Walks.RemoveAt(i--);
			}
			continue;
		}
		const FVector At = FMath::Lerp(P[Leg], P[Leg + 1], L[Leg] > 1.f ? S / L[Leg] : 1.f);
		const FVector Way = P[Leg + 1] - P[Leg];
		const float Yaw = Way.SizeSquared2D() > 1.f ? Way.Rotation().Yaw : U->GetActorRotation().Yaw;
		U->SetActorLocationAndRotation(At + FVector(0.f, 0.f, Half + 2.f), FRotator(0.f, Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
		// (its movement is off aboard: its velocity is what its walking pose is drawn from, so it walks the gangplank)
		U->GetCharacterMovement()->Velocity = Way.GetSafeNormal() * PlankWalk;
	}
}

void AVLTroopShip::TickTroops(float Dt)
{
	SinceBoard += Dt;
	UVLCommand* Command = UVLCommand::Get(this);
	for (int32 i = 0; i < Places.Num(); ++i)
	{
		FPlace& P = Places[i];
		AVLKing* U = P.Unit.Get();
		if (!U)
		{
			P.Unit = nullptr;
			P.bAboard = false;
			continue;
		}
		if (P.bAboard)
		{
			if (U->IsDead() || U->GarrisonIn.Get() != this)
			{
				// fallen aboard (AVLKing::Die lets go of the ship), or taken off it by something else
				Walks.RemoveAll([U](const FWalk& W) { return W.Unit.Get() == U; });
				if (U->GetAttachParentActor() == this)
				{
					U->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
				}
				P.Unit = nullptr;
				P.bAboard = false;
			}
			else if (U->HasOrder())
			{
				U->StopOrder();         // (an order that reached it at sea: it cannot walk off the deck)
				U->ClearQueue();
			}
			continue;
		}
		// on its way to the gangplank
		if (U->IsDead() || U->PendingGarrison.Get() != this || !bLanded || IsSailing())
		{
			if (U->PendingGarrison.Get() == this)
			{
				U->PendingGarrison = nullptr;
				U->StopOrder();
			}
			P.Unit = nullptr;
			continue;
		}
		const float D = FVector::Dist2D(U->GetFeet(), LandPoint);
		if (D < BoardNear)
		{
			if (SinceBoard >= BoardEvery)
			{
				SinceBoard = 0.f;
				FWalk W;
				W.Unit = U;
				W.Place = i;
				W.Shore = U->GetFeet();
				Seat(U, i);
				// (Seat put it on its place: back to where it stood, to walk up from there)
				U->SetActorLocation(W.Shore + FVector(0.f, 0.f, U->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 2.f), false, nullptr, ETeleportType::TeleportPhysics);
				Walks.Add(W);
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s boards %s (%d of %d aboard)"), *U->GetDisplayName(), *GetName(), NumAboard(), Capacity());
			}
		}
		else if (!U->HasOrder() && Command)
		{
			// it formed up short of the gangplank (a column is long), or was pushed off its way: on to its foot
			Command->OrderMove({ U }, LandPoint, false, EVLFormation::Loose);
			U->PendingGarrison = this;
		}
	}
}

// ------------------------------------------------------------------------------------------------ sailing

FString AVLTroopShip::DescribeState() const
{
	if (bDocking)
	{
		return TEXT("Docking");
	}
	if (Path.Num() > 0)
	{
		return bPatrol ? FString::Printf(TEXT("On patrol (%d points)"), PatrolPts.Num())
			: (Waypoints.Num() > 0 ? FString::Printf(TEXT("Under sail (%d more points)"), Waypoints.Num()) : FString(TEXT("Under sail")));
	}
	return bLanded ? TEXT("Moored: the gangplank is out") : (CanDock() ? TEXT("At sea: a berth is in reach") : TEXT("At sea, off the shore"));
}

void AVLTroopShip::Moor(const FVector& At, float Yaw)
{
	StopSailing();
	SetActorLocationAndRotation(At, FRotator(0.f, Yaw, 0.f));
	SeaZ = At.Z;
	UpdateLanding();
}

void AVLTroopShip::ClearCourse()
{
	Path.Reset();
	Waypoints.Reset();
	PatrolPts.Reset();
	bPatrol = false;
	bCastingOff = false;
	bLegDock = false;
	bLegStop = true;
}

void AVLTroopShip::StopSailing()
{
	ClearCourse();
	bDocking = false;
	Speed = 0.f;
}

void AVLTroopShip::EndWalks()
{
	// those on the gangplank: up it at once, or on down to the shore; one that has not set foot on it stays aboard
	for (FWalk& W : Walks)
	{
		W.Delay = W.bOff && W.T <= 0.f ? 1e9f : 0.f;
		W.T = W.Delay > 0.f ? W.T : 1e7f;
	}
	TickWalks(0.f);
	Walks.Reset();
}

void AVLTroopShip::GetCourse(TArray<FVector>& Out, bool& bOutLoop) const
{
	Out.Reset();
	bOutLoop = bPatrol;
	if (bPatrol)
	{
		Out = PatrolPts;
		return;
	}
	if (Path.Num() == 0)
	{
		return;
	}
	Out.Add(GetActorLocation());
	for (const FVector2D& P : Path)
	{
		Out.Add(FVector(P.X, P.Y, SeaZ));
	}
	for (const FVector& P : Waypoints)
	{
		Out.Add(FVector(P.X, P.Y, SeaZ));
	}
}

bool AVLTroopShip::StartLeg(const FVector& Point, bool bLast)
{
	UVLFleet* Fleet = UVLFleet::Get(this);
	if (!Fleet || !Fleet->EnsureChart(SeaZ))
	{
		return false;
	}
	const FVector2D From(GetActorLocation());
	const FVector2D Target(Point);
	FVector2D Goal;
	TArray<FVector2D> Route;
	if (!Fleet->NearestOpen(From, Target, 15000.f, Goal) || !Fleet->FindRoute(From, Goal, Route))
	{
		return false;
	}
	Path = MoveTemp(Route);
	LegTarget = Point;
	bLegStop = bLast && !bPatrol;
	// the end of its course by land (the land clicked, or land close by where it stops): it docks there
	FVector2D Land;
	bLegDock = bLegStop && (!Fleet->IsWater(Target) || Fleet->NearestLand(Goal, 1400.f, Land));
	bCastingOff = !Fleet->IsOpen(From);     // (hard by a shore: clear of it first)
	bDocking = false;
	bLanded = false;
	Plank->SetVisibility(false);
	return true;
}

bool AVLTroopShip::SailTo(const FVector& Point, bool bQueue)
{
	if (bQueue && Path.Num() > 0 && !bPatrol)
	{
		// one more point of the course it is on: the leg under way no longer ends it
		Waypoints.Add(Point);
		bLegStop = false;
		bLegDock = false;
		UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s: one more point of its course, %.0f %.0f (%d after this leg)"), *GetName(), Point.X, Point.Y, Waypoints.Num());
		return true;
	}
	EndWalks();
	ClearCourse();
	bDocking = false;
	if (!StartLeg(Point, true))
	{
		if (Team == UVLBattle::Player)
		{
			Alert(this, TEXT("The ship cannot sail there"), GetActorLocation());
		}
		return false;
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s sails to %.0f %.0f (%d corner(s), %d aboard%s)"), *GetName(), Path.Last().X, Path.Last().Y, Path.Num(), NumAboard(), bLegDock ? TEXT(", to dock there") : TEXT(""));
	return true;
}

bool AVLTroopShip::OrderPatrol(const FVector& Point, bool bExtend)
{
	UVLFleet* Fleet = UVLFleet::Get(this);
	const FVector2D Here(GetActorLocation());
	FVector2D There, Home;
	// a patrol's points are water a ship can lie in: never the land
	if (!Fleet || !Fleet->EnsureChart(SeaZ) || !Fleet->NearestOpen(Here, FVector2D(Point), 15000.f, There))
	{
		if (Team == UVLBattle::Player)
		{
			Alert(this, TEXT("The ship cannot patrol there"), GetActorLocation());
		}
		return false;
	}
	if (bExtend && bPatrol && PatrolPts.Num() > 0)
	{
		PatrolPts.Add(FVector(There.X, There.Y, SeaZ));
		UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s: one more point of its patrol, %.0f %.0f (%d points)"), *GetName(), There.X, There.Y, PatrolPts.Num());
		return true;
	}
	EndWalks();
	ClearCourse();
	bDocking = false;
	if (!Fleet->NearestOpen(Here, Here, 3000.f, Home))
	{
		Home = Here;
	}
	bPatrol = true;
	PatrolPts = { FVector(Home.X, Home.Y, SeaZ), FVector(There.X, There.Y, SeaZ) };
	PatrolNext = 1;
	if (!StartLeg(PatrolPts[1], false))
	{
		ClearCourse();
		return false;
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s patrols between %.0f %.0f and %.0f %.0f"), *GetName(), Home.X, Home.Y, There.X, There.Y);
	return true;
}

void AVLTroopShip::Arrive()
{
	Path.Reset();
	if (bPatrol && PatrolPts.Num() >= 2)
	{
		// round and round
		PatrolNext = (PatrolNext + 1) % PatrolPts.Num();
		if (StartLeg(PatrolPts[PatrolNext], false))
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s on patrol: on to point %d of %d"), *GetName(), PatrolNext + 1, PatrolPts.Num());
			return;
		}
		ClearCourse();
	}
	while (Waypoints.Num() > 0)
	{
		const FVector Next = Waypoints[0];
		Waypoints.RemoveAt(0);
		if (StartLeg(Next, Waypoints.Num() == 0))
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s: the next point of its course, %.0f %.0f (%d after it%s)"), *GetName(), Next.X, Next.Y, Waypoints.Num(), bLegDock ? TEXT("; it docks there") : TEXT(""));
			return;
		}
	}
	Speed = 0.f;
	if (bLegDock)
	{
		// by the land it was sent to: into the berth there
		const UVLFleet* Fleet = UVLFleet::Get(this);
		FVLBerth Berth;
		if (Fleet && Fleet->FindBerth(FVector2D(GetActorLocation()), DockRange, FVector2D(LegTarget), this, Berth))
		{
			StartDock(Berth);
			return;
		}
	}
	FinishSailing();
}

void AVLTroopShip::FinishSailing()
{
	StopSailing();
	UpdateLanding();
	UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s lies at %s, yaw %.0f: %s"), *GetName(), *GetActorLocation().ToCompactString(), GetActorRotation().Yaw,
		bLanded ? *FString::Printf(TEXT("landed, gangplank to %s"), *LandPoint.ToCompactString()) : TEXT("off the shore"));
}

void AVLTroopShip::TickSailing(float Dt)
{
	UVLFleet* Fleet = UVLFleet::Get(this);
	FVector Loc = GetActorLocation();
	float Yaw = GetActorRotation().Yaw;
	Loc.Z = SeaZ;
	if (Path.Num() == 0 || !Fleet)
	{
		return;
	}
	const FVector2D Pos(Loc);
	FVector2D To = Path[0] - Pos;
	float Dist = To.Size();
	if (bCastingOff)
	{
		// sideways off the quay, as it lies, to the open water its course starts from
		const float Move = FMath::Min(150.f * Dt, Dist);
		Loc.X += To.GetSafeNormal().X * Move;
		Loc.Y += To.GetSafeNormal().Y * Move;
		bCastingOff = Dist - Move > 60.f;
		SetActorLocationAndRotation(Loc, FRotator(0.f, Yaw, 0.f));
		return;
	}
	// (a point it sails on from, a patrol's or a course's: passed at a ship's length, under way)
	const bool bLast = Path.Num() == 1;
	if (Dist < (bLast && bLegStop ? 40.f : (bLast ? 700.f : 500.f)))
	{
		Path.RemoveAt(0);
		if (Path.Num() == 0)
		{
			SetActorLocationAndRotation(Loc, FRotator(0.f, Yaw, 0.f));
			Arrive();
			return;
		}
		To = Path[0] - Pos;
		Dist = To.Size();
	}
	float Left = Dist;
	for (int32 i = 1; i < Path.Num(); ++i)
	{
		Left += FVector2D::Distance(Path[i - 1], Path[i]);
	}
	const float Want = FMath::RadiansToDegrees(FMath::Atan2(To.Y, To.X));
	const float Err = FMath::FindDeltaAngleDegrees(Yaw, Want);
	const bool bCreep = bLegStop && Path.Num() == 1 && Dist < 450.f;        // the last of the way: straight to the spot, whichever way it heads
	// it turns as it goes, quicker the slower it is; off its heading it loses way, so it never circles a corner
	const float Turn = TurnRate * (1.f + 0.8f * (1.f - FMath::Clamp(Speed / Cruise, 0.f, 1.f)));
	if (!bCreep)
	{
		Yaw += FMath::Clamp(Err, -Turn * Dt, Turn * Dt);
	}
	float Target = Cruise * FMath::Clamp(1.f - FMath::Abs(Err) / 55.f, 0.06f, 1.f);
	if (bLegStop)
	{
		Target = FMath::Min(Target, FMath::Sqrt(2.f * Accel * FMath::Max(Left - 30.f, 0.f)) + 50.f);
	}
	if (bCreep)
	{
		Target = FMath::Min(Target, 160.f);
	}
	Speed = Speed < Target ? FMath::Min(Speed + Accel * Dt, Target) : FMath::Max(Speed - Accel * 2.f * Dt, Target);
	const FVector2D Step = (bCreep ? To.GetSafeNormal() : Dir2D(Yaw)) * FMath::Min(Speed * Dt, bCreep ? Dist : 1e9f);
	const FVector2D Next = Pos + Step;
	if (Fleet->IsWater(Next))
	{
		Loc.X = Next.X;
		Loc.Y = Next.Y;
	}
	else
	{
		Speed = 0.f;            // (land ahead: it turns where it lies until its way is clear)
	}
	SetActorLocationAndRotation(Loc, FRotator(0.f, Yaw, 0.f));
}

// ------------------------------------------------------------------------------------------------ docking

bool AVLTroopShip::HullNear(const FVector2D& P, float Margin) const
{
	const FVector L = GetActorTransform().InverseTransformPosition(FVector(P.X, P.Y, GetActorLocation().Z));
	return L.X > Deck::SternX - Margin && L.X < Deck::StemX + Margin && FMath::Abs(L.Y) < Deck::HalfBeam + Margin;
}

bool AVLTroopShip::Dock()
{
	const UVLFleet* Fleet = UVLFleet::Get(this);
	FVLBerth Berth;
	if (bLanded || bDocking || !Fleet || !UVLFleet::Get(this)->EnsureChart(SeaZ) || !Fleet->FindBerth(FVector2D(GetActorLocation()), DockRange, FVector2D(GetActorLocation()), this, Berth))
	{
		return false;
	}
	StartDock(Berth);
	return true;
}

void AVLTroopShip::StartDock(const FVLBerth& Berth)
{
	const UVLFleet* Fleet = UVLFleet::Get(this);
	ClearCourse();
	Speed = 0.f;
	DockFrom = FVector2D(GetActorLocation());
	DockFromYaw = GetActorRotation().Yaw;
	DockTo = Fleet ? Fleet->Snug(Berth) : Berth.At;
	DockToYaw = DockFromYaw + FMath::FindDeltaAngleDegrees(DockFromYaw, Berth.Yaw);       // (the short way round)
	DockShore = Berth.Shore;
	const float Dist = FVector2D::Distance(DockFrom, DockTo);
	const float Swing = FMath::Abs(DockToYaw - DockFromYaw);
	// quick: a second for a berth beside it, a second and a half from the edge of its range or right round
	DockDur = FMath::Clamp(DockSecondsMin + (DockSecondsMax - DockSecondsMin) * FMath::Max(Dist / DockRange, Swing / 180.f), DockSecondsMin, DockSecondsMax);
	// While it swings its ends reach toward the land: it stands off by what the swing needs and comes in as it
	// straightens (so no end passes through a quay's corner)
	const float Off = FVector2D::DotProduct(DockFrom - DockTo, -DockShore);       // how far out it starts
	const float Need = FMath::Abs(FMath::Sin(FMath::DegreesToRadians(Swing))) * Deck::StemX * 0.9f + (Swing > 90.f ? Deck::StemX * 0.9f : 0.f);
	DockBulge = FMath::Clamp(Need - FMath::Max(Off, 0.f), 0.f, 1200.f);
	DockT = 0.f;
	bDocking = true;
	bCanDock = false;
	bLanded = false;
	Plank->SetVisibility(false);
	UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s docks: %.1f m and %.0f degrees to its berth at %.0f %.0f (yaw %.0f), in %.2f s"), *GetName(), Dist / 100.f, Swing, DockTo.X, DockTo.Y, Berth.Yaw, DockDur);
}

void AVLTroopShip::TickDock(float Dt)
{
	DockT += Dt;
	const float T = FMath::Clamp(DockT / FMath::Max(DockDur, 0.1f), 0.f, 1.f);
	// fast in, settling at the end. The turn is done by three quarters of the move; along the shore it goes with the
	// move; toward the shore it comes in last
	auto Out3 = [](float X) { const float I = 1.f - FMath::Clamp(X, 0.f, 1.f); return 1.f - I * I * I; };
	const float Along = Out3(T), Turn = Out3(T / 0.75f), In = FMath::SmoothStep(0.2f, 1.f, T);
	const FVector2D Delta = DockTo - DockFrom;
	const FVector2D Tangent(-DockShore.Y, DockShore.X);
	const float DAlong = FVector2D::DotProduct(Delta, Tangent), DIn = FVector2D::DotProduct(Delta, DockShore);
	FVector2D Pos = DockFrom + Tangent * (DAlong * Along) + DockShore * (DIn * In);
	Pos -= DockShore * (DockBulge * FMath::Sin(PI * FMath::Min(T / 0.8f, 1.f)) * (1.f - In * 0.5f));
	const float Yaw = FMath::Lerp(DockFromYaw, DockToYaw, Turn);
	SetActorLocationAndRotation(FVector(Pos.X, Pos.Y, SeaZ), FRotator(0.f, Yaw, 0.f));
	if (T >= 1.f)
	{
		bDocking = false;
		LastDockSeconds = DockT;
		SettleClock = 0.f;
		SetActorLocationAndRotation(FVector(DockTo.X, DockTo.Y, SeaZ), FRotator(0.f, FRotator::NormalizeAxis(DockToYaw), 0.f));
		UpdateLanding();
		PlankClock = 0.f;           // the gangplank drops now
		PlacePlank();
		UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s docked in %.2f s at %s, yaw %.0f: %s"), *GetName(), LastDockSeconds, *GetActorLocation().ToCompactString(), GetActorRotation().Yaw,
			bLanded ? *FString::Printf(TEXT("landed, its %s side to the land, gangplank to %s"), LandSide > 0 ? TEXT("starboard") : TEXT("port"), *LandPoint.ToCompactString()) : TEXT("off the shore"));
	}
}

void AVLTroopShip::UpdateLanding()
{
	bLanded = false;
	UVLGrid* Grid = UVLGrid::Get(this);
	if (Grid && Grid->EnsureBuilt() && !IsSailing())
	{
		float Best = PlankReach;
		const FTransform Xf = GetActorTransform();
		for (const int32 Side : { 1, -1 })
		{
			const FVector Gate = GateWorld(Side);
			const int32 Node = Grid->NearestNode(Gate, 14, Grid->MainRegion());
			if (Node == INDEX_NONE)
			{
				continue;
			}
			const FVector N = Grid->NodePos(Node);
			const FVector Local = Xf.InverseTransformPosition(N);
			const float D = FVector::Dist2D(N, Gate);
			// ground a gangplank reaches: beside the hull on the port's own side, not far over or under its sill
			if (D < Best && Local.Y * Side > Deck::HalfBeam - 30.f && N.Z - Gate.Z > -LandDown && N.Z - Gate.Z < LandUp)
			{
				Best = D;
				bLanded = true;
				LandPoint = N;
				LandSide = Side;
			}
		}
	}
	PlacePlank();
}

void AVLTroopShip::PlacePlank()
{
	Plank->SetVisibility(bLanded);
	if (!bLanded)
	{
		return;
	}
	// from the entry port's sill to the ground: turned and tilted to it, stretched or shortened to its length. Just
	// docked, it drops from upright (0.3 s)
	const FVector Sill = GetActorTransform().TransformPosition(FVector(Deck::GateX, LandSide * (Deck::GateY - 25.f), Deck::GateZ + 3.f));
	const FVector To = LandPoint + FVector(0.f, 0.f, 4.f) - Sill;
	const float Len = FMath::Max(float(To.Size()), 60.f);
	FRotator Rot = To.Rotation();
	const float Up = 1.f - FMath::Clamp(PlankClock / PlankDropSeconds, 0.f, 1.f);
	Rot.Pitch += 75.f * Up * Up;
	Plank->SetWorldLocationAndRotation(Sill, Rot);
	Plank->SetWorldScale3D(FVector(Len / Deck::PlankLength, 1.f, 1.f));
}

void AVLTroopShip::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);
	BobClock += Dt;
	SettleClock += Dt;
	if (bDocking)
	{
		TickDock(Dt);
	}
	else if (Path.Num() > 0)
	{
		TickSailing(Dt);
	}
	else
	{
		LandCheck += Dt;
		if (LandCheck > 1.5f)
		{
			LandCheck = 0.f;
			if (Walks.Num() == 0)
			{
				UpdateLanding();        // (the ground by it can change: a building laid on the shore)
			}
		}
	}
	if (bLanded && PlankClock < PlankDropSeconds + 0.1f)
	{
		PlankClock += Dt;
		PlacePlank();
	}
	// a berth within reach (the player's ship, not docked): the dock button shows while there is one
	DockCheck += Dt;
	if (bLanded || bDocking || Team != UVLBattle::Player)
	{
		bCanDock = false;
	}
	else if (DockCheck > 0.3f)
	{
		DockCheck = 0.f;
		UVLFleet* Fleet = UVLFleet::Get(this);
		bCanDock = Fleet && Fleet->EnsureChart(SeaZ) && Fleet->FindBerth(FVector2D(GetActorLocation()), DockRange, FVector2D(GetActorLocation()), this, DockBerth);
	}
	// it rides the water: a slow heave and roll (more under way), and a bob as it settles in a berth. The units aboard
	// stand on the hull and ride with it
	const float Way = FMath::Clamp(Speed / FMath::Max(Cruise, 1.f), 0.f, 1.f);
	const float Settle = FMath::Exp(-3.2f * SettleClock);
	const float Heave = 5.f * FMath::Sin(BobClock * 0.9f) + 3.f * Way * FMath::Sin(BobClock * 1.7f) - 9.f * Settle * FMath::Cos(SettleClock * 8.f);
	const float Roll = (0.8f + 0.9f * Way) * FMath::Sin(BobClock * 0.7f + 1.f) + 2.6f * Settle * FMath::Cos(SettleClock * 9.f) * LandSide;
	const float Pitch = (0.35f + 0.5f * Way) * FMath::Sin(BobClock * 0.55f);
	Hull->SetRelativeLocationAndRotation(FVector(0.f, 0.f, Heave), FRotator(Pitch, 0.f, Roll));
	TickTroops(Dt);
	TickWalks(Dt);
}

// ------------------------------------------------------------------------------------------------ the pointer

AVLTroopShip* AVLTroopShip::Pick(const UWorld* World, const FVector& Origin, const FVector& Dir, float MaxDist)
{
	const UVLFleet* Fleet = World ? World->GetSubsystem<UVLFleet>() : nullptr;
	AVLTroopShip* Best = nullptr;
	if (!Fleet)
	{
		return nullptr;
	}
	// the hull with its castles, and the mast with its sail
	const FBox Boxes[2] = { FBox(FVector(Deck::SternX, -Deck::HalfBeam, -Deck::Draught), FVector(Deck::StemX, Deck::HalfBeam, 520.f)),
		FBox(FVector(-60.f, -480.f, 520.f), FVector(260.f, 480.f, Deck::MastZ)) };
	for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->GetShips())
	{
		AVLTroopShip* Ship = S.Get();
		if (!Ship)
		{
			continue;
		}
		const FTransform Xf = Ship->GetActorTransform();
		const FVector O = Xf.InverseTransformPosition(Origin);
		const FVector D = Xf.InverseTransformVectorNoScale(Dir);
		for (const FBox& Box : Boxes)
		{
			float T0 = 0.f, T1 = MaxDist;
			bool bMiss = false;
			for (int32 Axis = 0; Axis < 3 && !bMiss; ++Axis)
			{
				if (FMath::Abs(D[Axis]) < 1e-6f)
				{
					bMiss = O[Axis] < Box.Min[Axis] || O[Axis] > Box.Max[Axis];
					continue;
				}
				float A0 = (Box.Min[Axis] - O[Axis]) / D[Axis], A1 = (Box.Max[Axis] - O[Axis]) / D[Axis];
				if (A0 > A1)
				{
					Swap(A0, A1);
				}
				T0 = FMath::Max(T0, A0);
				T1 = FMath::Min(T1, A1);
				bMiss = T0 > T1;
			}
			if (!bMiss && T0 < MaxDist)
			{
				MaxDist = T0;
				Best = Ship;
			}
		}
	}
	return Best;
}

AVLTroopShip* AVLTroopShip::Selected(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	const AVLKing* Commander = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr;
	AVLTroopShip* Ship = Commander ? Cast<AVLTroopShip>(Commander->GetSelected()) : nullptr;
	const UVLCommand* Command = UVLCommand::Get(World);
	return Ship && Command && Ship->Team == Commander->Team && Command->NumSelected() == 0 ? Ship : nullptr;
}

namespace
{
	/** Where a click of the view is for a ship: the land or the quay under the pointer (Ground, if it is above the
	 *  sea), else where the pointer's ray meets the sea. False: the pointer is on the sky. */
	bool PointerTarget(const APlayerController* PC, const FVector2D& Point, const FVector& Ground, float SeaZ, FVector& Out)
	{
		Out = Ground;
		if (Ground.IsZero() || Ground.Z < SeaZ + 20.f)
		{
			FVector Origin, Dir;
			if (!PC || !PC->DeprojectScreenPositionToWorld(Point.X, Point.Y, Origin, Dir) || Dir.Z > -0.01f)
			{
				return false;
			}
			Out = Origin + Dir * ((SeaZ - Origin.Z) / Dir.Z);
		}
		return true;
	}
}

bool AVLTroopShip::OrderFromView(AVLKing* Commander, APlayerController* PC, const FVector2D& Point, const FVector& Ground, bool bQueue)
{
	AVLTroopShip* Ship = Selected(Commander);
	UVLCommand* Command = UVLCommand::Get(Commander);
	if (!Ship || !PC || !Command)
	{
		return false;
	}
	FVector Target;
	if (PointerTarget(PC, Point, Ground, Ship->SeaZ, Target) && Ship->SailTo(Target, bQueue))
	{
		Command->ShowMarker(FVector(Target.X, Target.Y, FMath::Max(Target.Z, Ship->SeaZ)));
		AVLGameMode::PlayOrderSound(Commander);
	}
	return true;
}

bool AVLTroopShip::OrderFromMap(const UObject* WorldContext, const FVector& At, bool bQueue)
{
	AVLTroopShip* Ship = Selected(WorldContext);
	UVLCommand* Command = UVLCommand::Get(WorldContext);
	if (!Ship || !Command)
	{
		return false;
	}
	// (a point of the map: the land there means its shore, as a click on the land does)
	if (Ship->SailTo(FVector(At.X, At.Y, Ship->SeaZ), bQueue))
	{
		Command->ShowMarker(FVector(At.X, At.Y, Ship->SeaZ));
		AVLGameMode::PlayOrderSound(WorldContext);
		UE_LOG(LogSovereignRealms, Log, TEXT("minimap: the ship sent to %.0f %.0f%s"), At.X, At.Y, bQueue ? TEXT(" (queued)") : TEXT(""));
	}
	return true;
}

bool AVLTroopShip::PatrolClick(AVLKing* Commander, APlayerController* PC, const FVector2D& Point, bool bShift)
{
	AVLTroopShip* Ship = Selected(Commander);
	UVLCommand* Command = UVLCommand::Get(Commander);
	if (!Ship || !PC || !Command)
	{
		return false;
	}
	FVector Target;
	if (PointerTarget(PC, Point, FVector::ZeroVector, Ship->SeaZ, Target) && Ship->OrderPatrol(Target, bShift))
	{
		Command->ShowMarker(FVector(Target.X, Target.Y, Ship->SeaZ));
		AVLGameMode::PlayOrderSound(Commander);
	}
	return true;
}

// ================================================================================================ the fleet

UVLFleet* UVLFleet::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLFleet>() : nullptr;
}

bool UVLFleet::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UVLFleet::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	// (once the level's actors have begun play: the berths are looked for on the path grid)
	FTimerHandle Handle;
	InWorld.GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateUObject(this, &UVLFleet::SpawnShips), 0.25f, false);
}

AVLTroopShip* UVLFleet::SpawnShip(const FVector& At, float Yaw, int32 Team)
{
	UWorld* World = GetWorld();
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AVLTroopShip* Ship = World ? World->SpawnActor<AVLTroopShip>(AVLTroopShip::StaticClass(), At, FRotator(0.f, Yaw, 0.f), Params) : nullptr;
	if (Ship)
	{
		Ship->SetTeam(Team);
		Ships.Add(Ship);
		Ship->UpdateLanding();
		UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s of team %d at %s, yaw %.0f: %s"), *Ship->GetName(), Team, *At.ToCompactString(), Yaw, Ship->IsLanded() ? TEXT("landed") : TEXT("off the shore"));
	}
	return Ship;
}

void UVLFleet::SpawnShips()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	if (VLNet::IsMultiplayer(World))
	{
		// multiplayer, stage one: no troop ships (a ship and who is aboard it are not replicated yet), in either game
		UE_LOG(LogSovereignRealms, Log, TEXT("fleet: no troop ships in a multiplayer match (not replicated yet)"));
		return;
	}
	TArray<TPair<AActor*, int32>> Marks;
	TArray<AActor*> Moored;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		for (const FName& Tag : It->Tags)
		{
			const FString S = Tag.ToString();
			if (S == TEXT("TroopShip") || S.StartsWith(TEXT("TroopShip:")))
			{
				Marks.Add({ *It, S.Len() > 10 ? FMath::Clamp(FCString::Atoi(*S.Mid(10)), 0, 1) : 0 });
			}
			else if (S == TEXT("Moored"))
			{
				Moored.Add(*It);
			}
		}
	}
	for (const TPair<AActor*, int32>& M : Marks)
	{
		SpawnShip(M.Key->GetActorLocation(), M.Key->GetActorRotation().Yaw, M.Value);
		if (M.Key->IsA<AStaticMeshActor>())
		{
			M.Key->SetActorHiddenInGame(true);          // (the level's own SM_TroopShip, there to be seen in the editor)
			M.Key->SetActorEnableCollision(false);
		}
	}
	if (Marks.Num() == 0)
	{
		for (AActor* M : Moored)
		{
			// by the mooring; and if the units cannot walk to any shore there (the quay is cut off from the land), the
			// nearest shore of the whole coast they can walk to
			const FVector Home = M->GetActorLocation();
			FVLBerth Berth;
			UVLGrid* Grid = UVLGrid::Get(this);
			if (!Grid || !Grid->EnsureBuilt() || !EnsureChart(Home.Z)
				|| !(FindBerth(FVector2D(Home), 4500.f, FVector2D(Home), nullptr, Berth) || FindBerth(FVector2D(Home), 1e7f, FVector2D(Home), nullptr, Berth)))
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: no berth by %s"), *M->GetName());
				continue;
			}
			// whose port: the moored ship's cloth (red: the enemy's)
			int32 Team = UVLBattle::Player;
			if (const UStaticMeshComponent* C = M->FindComponentByClass<UStaticMeshComponent>())
			{
				for (int32 i = 0; i < C->GetNumMaterials(); ++i)
				{
					const UMaterialInterface* Mat = C->GetMaterial(i);
					Team = Mat && Mat->GetName().Contains(TEXT("Enemy")) ? UVLBattle::Enemy : Team;
				}
			}
			const FVector2D Lie = Snug(Berth);
			const FVector At(Lie.X, Lie.Y, Home.Z);
			if (SpawnShip(At, Berth.Yaw, Team))
			{
				// the troop ship is the port's ship now: the one the level moored there makes room for it (not if the
				// berth is another shore altogether)
				if (FVector::Dist2D(At, M->GetActorLocation()) < 6000.f)
				{
					M->SetActorHiddenInGame(true);
					M->SetActorEnableCollision(false);
				}
				else
				{
					UE_LOG(LogSovereignRealms, Warning, TEXT("ship: no shore by %s that units can walk to: the troop ship lies %.0f m from it"), *M->GetName(), FVector::Dist2D(At, M->GetActorLocation()) / 100.f);
				}
			}
		}
	}
	if (Ships.Num() > 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("ship: %d troop ship(s) (%d placed by the level, %d moored ship(s) there)"), Ships.Num(), Marks.Num(), Moored.Num());
	}
}

bool UVLFleet::FindBerth(const FVector2D& Around, float Radius, const FVector2D& Prefer, const AVLTroopShip* For, FVLBerth& Out) const
{
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!Grid || !Grid->IsBuilt() || DimX <= 0)
	{
		return false;
	}
	const FIntPoint C0(FMath::Clamp(FMath::FloorToInt((Around.X - Origin.X) / CellSize), 0, DimX - 1), FMath::Clamp(FMath::FloorToInt((Around.Y - Origin.Y) / CellSize), 0, DimY - 1));
	const int32 R = FMath::Min(FMath::CeilToInt(Radius / CellSize), FMath::Max(DimX, DimY));
	const float ForYaw = For ? For->GetActorRotation().Yaw : 0.f;
	float BestScore = TNumericLimits<float>::Max();
	const float Along[] = { VLTroopShipDeck::SternX + 40.f, VLTroopShipDeck::SternX * 0.5f, 0.f, VLTroopShipDeck::StemX * 0.45f, VLTroopShipDeck::StemX - 150.f };
	for (int32 dy = -R; dy <= R; ++dy)
	{
		for (int32 dx = -R; dx <= R; ++dx)
		{
			const FIntPoint C(C0.X + dx, C0.Y + dy);
			if (C.X < 0 || C.Y < 0 || C.X >= DimX || C.Y >= DimY || !Open[Idx(C)])
			{
				continue;
			}
			const FVector2D Mid = CellMid(C);
			FVector2D Land;
			if (FVector2D::DistSquared(Mid, Around) > FMath::Square(Radius) || !NearestLand(Mid, 900.f, Land))
			{
				continue;
			}
			const FVector2D Shore = (Land - Mid).GetSafeNormal();
			for (const float Turn : { 90.f, -90.f })
			{
				// its side to that land: the whole hull in water and clear of other ships, the land lying along it, a
				// gangplank's reach of ground
				const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(Shore.Y, Shore.X)) + Turn;
				const FVector2D Fwd = Dir2D(Yaw);
				const FVector2D Side(-Fwd.Y, Fwd.X);
				const float Port = FVector2D::DotProduct(Side, Shore) > 0.f ? 1.f : -1.f;      // the side toward the land (+Y of the ship)
				bool bFits = true;
				for (const float S : Along)
				{
					for (const float W : { -VLTroopShipDeck::HalfBeam - 20.f, 0.f, VLTroopShipDeck::HalfBeam + 20.f })
					{
						const FVector2D P = Mid + Fwd * S + Side * W;
						bFits = bFits && IsWater(P);
						for (const TWeakObjectPtr<AVLTroopShip>& Other : Ships)
						{
							bFits = bFits && (!Other.IsValid() || Other.Get() == For || !Other->HullNear(P, 250.f));
						}
					}
				}
				// a straight shore: land abeam of it fore and aft as well, about as near as amidships
				const float Gap = FVector2D::Distance(Land, Mid);
				for (const float S : { -800.f, 800.f })
				{
					FVector2D L2;
					const FVector2D P = Mid + Fwd * S;
					bFits = bFits && NearestLand(P, Gap + 300.f, L2) && FVector2D::DotProduct((L2 - P).GetSafeNormal(), Shore) > 0.8f;
				}
				if (!bFits)
				{
					continue;
				}
				const FVector Gate(FVector2D(Mid + Fwd * VLTroopShipDeck::GateX + Side * (Port * VLTroopShipDeck::GateY)), ChartSeaZ + VLTroopShipDeck::GateZ);
				const int32 Node = Grid->NearestNode(Gate, 14, Grid->MainRegion());
				if (Node == INDEX_NONE)
				{
					continue;
				}
				const FVector N = Grid->NodePos(Node);
				const float D = FVector::Dist2D(N, Gate);
				if (D > 850.f || N.Z - Gate.Z < -LandDown || N.Z - Gate.Z > LandUp)       // (it comes alongside from there: nearer)
				{
					continue;
				}
				// the nearest to where it is wanted, a short gangplank, and the heading that turns the ship least
				const float Score = FVector2D::Distance(Mid, Prefer) + 0.5f * D + (For ? FMath::Abs(FMath::FindDeltaAngleDegrees(ForYaw, Yaw)) * 2.f : 0.f);
				if (Score < BestScore)
				{
					BestScore = Score;
					Out.At = Mid;
					Out.Yaw = Yaw;
					Out.Shore = Shore;
					Out.Land = N;
				}
			}
		}
	}
	return BestScore < TNumericLimits<float>::Max();
}

FVector2D UVLFleet::Snug(const FVLBerth& Berth) const
{
	// sideways toward the land, 10 cm at a time, while the water beside the hull is clear all along it
	const UWorld* World = GetWorld();
	const FVector2D Fwd = Dir2D(Berth.Yaw);
	FVector2D Side(-Fwd.Y, Fwd.X);
	if (FVector2D::DotProduct(Side, Berth.Shore) < 0.f)
	{
		Side = -Side;
	}
	FVector2D At = Berth.At;
	for (int32 Step = 0; World && Step < int32(MaxSlide / 10.f); ++Step)
	{
		bool bClear = true;
		for (const float S : { VLTroopShipDeck::SternX + 60.f, VLTroopShipDeck::SternX * 0.5f, 0.f, VLTroopShipDeck::StemX * 0.4f, VLTroopShipDeck::StemX * 0.72f })
		{
			bClear = bClear && ClearWater(World, At + Fwd * S + Side * (VLTroopShipDeck::HalfBeam + SideGap + 10.f), ChartSeaZ, Probe);
		}
		if (!bClear)
		{
			break;
		}
		At += Side * 10.f;
	}
	return At;
}

// ------------------------------------------------------------------------------------------------ the chart

bool UVLFleet::ToCell(const FVector2D& P, FIntPoint& Out) const
{
	if (DimX <= 0)
	{
		return false;
	}
	Out = FIntPoint(FMath::FloorToInt((P.X - Origin.X) / CellSize), FMath::FloorToInt((P.Y - Origin.Y) / CellSize));
	return Out.X >= 0 && Out.Y >= 0 && Out.X < DimX && Out.Y < DimY;
}

bool UVLFleet::EnsureChart(float SeaZ)
{
	if (bChartTried)
	{
		return DimX > 0 && FMath::Abs(SeaZ - ChartSeaZ) < 60.f;
	}
	bChartTried = true;
	UWorld* World = GetWorld();
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!World || !Grid || !Grid->EnsureBuilt())
	{
		return false;
	}
	const double T0 = FPlatformTime::Seconds();
	TArray<UStaticMeshComponent*> Sheets;
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		if (It->ActorHasTag(TEXT("Water")) && It->GetStaticMeshComponent())
		{
			Sheets.Add(It->GetStaticMeshComponent());
		}
	}
	if (Sheets.Num() == 0)
	{
		return false;
	}
	const FBox2D Bounds = Grid->GetBounds().ExpandBy(ChartMargin);
	Origin = Bounds.Min;
	DimX = FMath::CeilToInt(Bounds.GetSize().X / CellSize);
	DimY = FMath::CeilToInt(Bounds.GetSize().Y / CellSize);
	ChartSeaZ = SeaZ;
	Water.Init(0, DimX * DimY);
	const FCollisionQueryParams Params = ChartParams(World);
	Probe = Params;
	const FCollisionQueryParams SheetParams(SCENE_QUERY_STAT(VLFleetSheet), true);
	ParallelFor(DimY, [&](int32 y)
	{
		for (int32 x = 0; x < DimX; ++x)
		{
			const FVector2D P = CellMid(FIntPoint(x, y));
			bool bSheet = false;
			FHitResult Hit;
			for (UStaticMeshComponent* Sheet : Sheets)
			{
				if (Sheet->Bounds.GetBox().IsInsideXY(FVector(P.X, P.Y, 0.f))
					&& Sheet->LineTraceComponent(Hit, FVector(P.X, P.Y, SeaZ + 300.f), FVector(P.X, P.Y, SeaZ - 300.f), SheetParams) && FMath::Abs(Hit.ImpactPoint.Z - SeaZ) < 60.f)
				{
					bSheet = true;
					break;
				}
			}
			bool bClear = bSheet;
			for (int32 k = 0; k < 5 && bClear; ++k)
			{
				static const FVector2D Off[5] = { FVector2D(0.f, 0.f), FVector2D(70.f, 70.f), FVector2D(-70.f, 70.f), FVector2D(70.f, -70.f), FVector2D(-70.f, -70.f) };
				bClear = ClearWater(World, P + Off[k], SeaZ, Params);
			}
			Water[y * DimX + x] = bClear ? 1 : 0;
		}
	});
	// a ship's middle keeps a cell off everything: its half beam and a little
	Open.Init(0, DimX * DimY);
	int32 NumWater = 0, NumOpen = 0;
	for (int32 y = 1; y < DimY - 1; ++y)
	{
		for (int32 x = 1; x < DimX - 1; ++x)
		{
			bool bAll = true;
			for (int32 dy = -1; dy <= 1 && bAll; ++dy)
			{
				for (int32 dx = -1; dx <= 1 && bAll; ++dx)
				{
					bAll = Water[(y + dy) * DimX + x + dx] != 0;
				}
			}
			Open[y * DimX + x] = bAll ? 1 : 0;
			NumWater += Water[y * DimX + x];
			NumOpen += bAll ? 1 : 0;
		}
	}
	// the waters: each connected piece of open cells
	Sea.Init(0, DimX * DimY);
	int32 Seas = 0;
	TArray<int32> Stack;
	for (int32 i = 0; i < Open.Num(); ++i)
	{
		if (!Open[i] || Sea[i])
		{
			continue;
		}
		Sea[i] = ++Seas;
		Stack.Reset();
		Stack.Add(i);
		while (Stack.Num() > 0)
		{
			const int32 c = Stack.Pop(EAllowShrinking::No);
			const int32 cx = c % DimX, cy = c / DimX;
			for (const FIntPoint& D : { FIntPoint(1, 0), FIntPoint(-1, 0), FIntPoint(0, 1), FIntPoint(0, -1) })
			{
				const int32 nx = cx + D.X, ny = cy + D.Y;
				if (nx >= 0 && ny >= 0 && nx < DimX && ny < DimY && Open[ny * DimX + nx] && !Sea[ny * DimX + nx])
				{
					Sea[ny * DimX + nx] = Seas;
					Stack.Add(ny * DimX + nx);
				}
			}
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("ship: chart %d x %d cells of %.1f m, sea at %.0f: %d of water, %d open to a ship, %d water(s), %.0f ms"), DimX, DimY, CellSize / 100.f, SeaZ, NumWater, NumOpen, Seas,
		(FPlatformTime::Seconds() - T0) * 1000.0);
	return NumOpen > 0;
}

bool UVLFleet::IsOpen(const FVector2D& P) const
{
	FIntPoint C;
	return ToCell(P, C) && Open[Idx(C)] != 0;
}

bool UVLFleet::IsWater(const FVector2D& P) const
{
	FIntPoint C;
	return ToCell(P, C) && Water[Idx(C)] != 0;
}

int32 UVLFleet::OpenCellNear(const FVector2D& P, int32 Rings, int32 InSea) const
{
	if (DimX <= 0)
	{
		return INDEX_NONE;
	}
	const FIntPoint C(FMath::Clamp(FMath::FloorToInt((P.X - Origin.X) / CellSize), 0, DimX - 1), FMath::Clamp(FMath::FloorToInt((P.Y - Origin.Y) / CellSize), 0, DimY - 1));
	int32 Best = INDEX_NONE;
	float BestD = TNumericLimits<float>::Max();
	for (int32 R = 0; R <= Rings; ++R)
	{
		for (int32 dy = -R; dy <= R; ++dy)
		{
			for (int32 dx = -R; dx <= R; ++dx)
			{
				if (FMath::Max(FMath::Abs(dx), FMath::Abs(dy)) != R)
				{
					continue;
				}
				const FIntPoint N(C.X + dx, C.Y + dy);
				if (N.X < 0 || N.Y < 0 || N.X >= DimX || N.Y >= DimY || !Open[Idx(N)] || (InSea != 0 && Sea[Idx(N)] != InSea))
				{
					continue;
				}
				const float D = FVector2D::DistSquared(CellMid(N), P);
				if (D < BestD)
				{
					BestD = D;
					Best = Idx(N);
				}
			}
		}
		if (Best != INDEX_NONE && R >= 1 && BestD <= FMath::Square((R - 0.5f) * CellSize))
		{
			break;          // (nothing in a further ring is nearer)
		}
	}
	return Best;
}

bool UVLFleet::NearestOpen(const FVector2D& From, const FVector2D& Point, float Reach, FVector2D& Out) const
{
	const int32 Start = OpenCellNear(From, 8);
	if (Start == INDEX_NONE)
	{
		return false;
	}
	const int32 Cell = OpenCellNear(Point, FMath::CeilToInt(Reach / CellSize), Sea[Start]);
	if (Cell == INDEX_NONE)
	{
		return false;
	}
	Out = CellMid(FIntPoint(Cell % DimX, Cell / DimX));
	return true;
}

bool UVLFleet::NearestLand(const FVector2D& P, float Reach, FVector2D& Out) const
{
	FIntPoint C;
	if (!ToCell(P, C))
	{
		return false;
	}
	const int32 Rings = FMath::CeilToInt(Reach / CellSize);
	float BestD = FMath::Square(Reach);
	bool bFound = false;
	for (int32 dy = -Rings; dy <= Rings; ++dy)
	{
		for (int32 dx = -Rings; dx <= Rings; ++dx)
		{
			const FIntPoint N(C.X + dx, C.Y + dy);
			if (N.X < 0 || N.Y < 0 || N.X >= DimX || N.Y >= DimY || Water[Idx(N)])
			{
				continue;
			}
			const float D = FVector2D::DistSquared(CellMid(N), P);
			if (D < BestD)
			{
				BestD = D;
				Out = CellMid(N);
				bFound = true;
			}
		}
	}
	return bFound;
}

bool UVLFleet::LineOpen(const FVector2D& A, const FVector2D& B) const
{
	const float Len = FVector2D::Distance(A, B);
	const int32 Steps = FMath::Max(1, FMath::CeilToInt(Len / (CellSize * 0.4f)));
	for (int32 i = 0; i <= Steps; ++i)
	{
		if (!IsOpen(FMath::Lerp(A, B, float(i) / Steps)))
		{
			return false;
		}
	}
	return true;
}

bool UVLFleet::FindRoute(const FVector2D& From, const FVector2D& To, TArray<FVector2D>& Out) const
{
	Out.Reset();
	const int32 Start = OpenCellNear(From, 8);
	FIntPoint GoalC;
	if (Start == INDEX_NONE || !ToCell(To, GoalC) || !Open[Idx(GoalC)] || Sea[Idx(GoalC)] != Sea[Start])
	{
		return false;
	}
	const int32 Goal = Idx(GoalC);
	// A* over the open cells (a diagonal only where both cells beside it are open)
	TArray<float> Cost;
	TArray<int32> Parent;
	Cost.Init(TNumericLimits<float>::Max(), Open.Num());
	Parent.Init(INDEX_NONE, Open.Num());
	struct FItem
	{
		float F;
		int32 Cell;
		bool operator<(const FItem& O) const { return F < O.F; }
	};
	TArray<FItem> Heap;
	auto Guess = [this, GoalC](int32 c)
	{
		const int32 dx = FMath::Abs(c % DimX - GoalC.X), dy = FMath::Abs(c / DimX - GoalC.Y);
		return float(FMath::Max(dx, dy)) + 0.4142f * FMath::Min(dx, dy);
	};
	Cost[Start] = 0.f;
	Heap.HeapPush({ Guess(Start), Start });
	bool bFound = false;
	while (Heap.Num() > 0)
	{
		FItem It;
		Heap.HeapPop(It, EAllowShrinking::No);
		if (It.Cell == Goal)
		{
			bFound = true;
			break;
		}
		if (It.F > Cost[It.Cell] + Guess(It.Cell) + 0.001f)
		{
			continue;
		}
		const int32 cx = It.Cell % DimX, cy = It.Cell / DimX;
		for (int32 dy = -1; dy <= 1; ++dy)
		{
			for (int32 dx = -1; dx <= 1; ++dx)
			{
				const int32 nx = cx + dx, ny = cy + dy;
				if ((dx == 0 && dy == 0) || nx < 0 || ny < 0 || nx >= DimX || ny >= DimY || !Open[ny * DimX + nx])
				{
					continue;
				}
				if (dx != 0 && dy != 0 && (!Open[cy * DimX + nx] || !Open[ny * DimX + cx]))
				{
					continue;
				}
				const int32 n = ny * DimX + nx;
				const float G = Cost[It.Cell] + (dx != 0 && dy != 0 ? 1.4142f : 1.f);
				if (G < Cost[n])
				{
					Cost[n] = G;
					Parent[n] = It.Cell;
					Heap.HeapPush({ G + Guess(n), n });
				}
			}
		}
	}
	if (!bFound)
	{
		return false;
	}
	TArray<FVector2D> Cells;
	for (int32 c = Goal; c != INDEX_NONE; c = Parent[c])
	{
		Cells.Insert(CellMid(FIntPoint(c % DimX, c / DimX)), 0);
	}
	// pulled straight: from each corner to the furthest cell of the way it sees over open water
	int32 At = 0;
	Out.Add(Cells[0]);
	while (At < Cells.Num() - 1)
	{
		int32 Far = At + 1;
		for (int32 j = Cells.Num() - 1; j > At + 1; --j)
		{
			if (LineOpen(Cells[At], Cells[j]))
			{
				Far = j;
				break;
			}
		}
		Out.Add(Cells[Far]);
		At = Far;
	}
	return true;
}

// ================================================================================================ console

namespace
{
	AVLTroopShip* PlayersShip(UWorld* World, int32 Index)
	{
		const UVLFleet* Fleet = UVLFleet::Get(World);
		if (!Fleet)
		{
			return nullptr;
		}
		if (Index >= 0)
		{
			return Fleet->GetShips().IsValidIndex(Index) ? Fleet->GetShips()[Index].Get() : nullptr;
		}
		for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->GetShips())
		{
			if (S.IsValid() && S->GetTeam() == UVLBattle::Player)
			{
				return S.Get();
			}
		}
		return nullptr;
	}

	/** "sel" the selection, "all" every troop of the ship's side, "heroes", "platoon N", "near [m]": troops within that of the ship. */
	void ShipUnits(UWorld* World, const AVLTroopShip* Ship, const TArray<FString>& Args, int32 From, TArray<AVLKing*>& Out)
	{
		UVLCommand* Command = UVLCommand::Get(World);
		const UVLBattle* Battle = UVLBattle::Get(World);
		const FString Who = Args.IsValidIndex(From) ? Args[From].ToLower() : TEXT("sel");
		if (!Command || !Battle)
		{
			return;
		}
		if (Who == TEXT("sel"))
		{
			Command->GetSelection(Out);
		}
		else if (Who == TEXT("platoon"))
		{
			Command->GetPlatoon(Args.IsValidIndex(From + 1) ? FCString::Atoi(*Args[From + 1]) - 1 : 0, Out);
		}
		else
		{
			const float Near = Who == TEXT("near") ? (Args.IsValidIndex(From + 1) ? FCString::Atof(*Args[From + 1]) : 80.f) * 100.f : 1e9f;
			for (AVLKing* U : Battle->AllUnits())
			{
				const bool bHero = !U->IsTroop() || U->IsJonathan();
				if (U->IsAlive() && U->Team == Ship->GetTeam() && !U->bTowerGuard && !U->bAmbient && FVector::Dist2D(U->GetFeet(), Ship->GetActorLocation()) < Near
					&& (Who == TEXT("heroes") ? bHero : (U->IsTroop() && U->KindId() != EVLUnitKind::Builder)))
				{
					Out.Add(U);
				}
			}
		}
	}

	FAutoConsoleCommandWithWorldAndArgs CmdShip(TEXT("vl.Ship"),
		TEXT("vl.Ship [#n] state | board <sel|all|heroes|near [m]|platoon N> [run] | put <who> | unload | sail X Y [queue] | patrol X Y [add] | dock | stop | moor X Y Yaw | pos   (#n: which ship, default the player's first; X Y in cm)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& InArgs, UWorld* World)
		{
			TArray<FString> Args(InArgs);
			int32 Index = -1;
			if (Args.Num() > 0 && Args[0].StartsWith(TEXT("#")))
			{
				Index = FCString::Atoi(*Args[0].Mid(1));
				Args.RemoveAt(0);
			}
			UVLFleet* Fleet = UVLFleet::Get(World);
			const FString Verb = Args.Num() > 0 ? Args[0].ToLower() : TEXT("state");
			if (!Fleet)
			{
				return;
			}
			if (Verb == TEXT("state"))
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: %d ship(s)"), Fleet->GetShips().Num());
				int32 i = 0;
				for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->GetShips())
				{
					if (const AVLTroopShip* Ship = S.Get())
					{
						TArray<AVLKing*> In;
						Ship->GetAboard(In);
						float Health = 0.f;
						for (const AVLKing* U : In)
						{
							Health += U->GetHealthFrac();
						}
						UE_LOG(LogSovereignRealms, Log, TEXT("ship #%d %s team %d at %s yaw %.0f: %s; aboard %d of %d, coming %d, landed %d at %s, health of those aboard %.2f; can dock %d at %s, last dock %.2f s"), i, *Ship->GetName(), Ship->GetTeam(),
							*Ship->GetActorLocation().ToCompactString(), Ship->GetActorRotation().Yaw, *Ship->DescribeState(), In.Num(), AVLTroopShip::Capacity(), Ship->NumComing(), Ship->IsLanded() ? 1 : 0,
							*Ship->GetLandPoint().ToCompactString(), In.Num() > 0 ? Health / In.Num() : 0.f, Ship->CanDock() ? 1 : 0, *Ship->GetDockPoint().ToCompactString(), Ship->GetLastDockSeconds());
					}
					++i;
				}
				return;
			}
			AVLTroopShip* Ship = PlayersShip(World, Index);
			if (!Ship)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: no such ship"));
				return;
			}
			if (Verb == TEXT("board") || Verb == TEXT("put"))
			{
				TArray<AVLKing*> Units;
				ShipUnits(World, Ship, Args, 1, Units);
				int32 N = 0;
				if (Verb == TEXT("board"))
				{
					N = Ship->OrderBoard(Units, Args.Last().ToLower() == TEXT("run"));
				}
				else
				{
					for (AVLKing* U : Units)
					{
						N += Ship->PutAboard(U) ? 1 : 0;
					}
				}
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: %s %d of %d unit(s)"), *Verb, N, Units.Num());
			}
			else if (Verb == TEXT("unload"))
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: unload %d"), Ship->Unload());
			}
			else if (Verb == TEXT("sail") && Args.Num() >= 3)
			{
				const bool bOk = Ship->SailTo(FVector(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]), Ship->GetActorLocation().Z), Args.Last().ToLower() == TEXT("queue"));
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: sail %s"), bOk ? TEXT("ordered") : TEXT("refused"));
			}
			else if (Verb == TEXT("patrol") && Args.Num() >= 3)
			{
				const bool bOk = Ship->OrderPatrol(FVector(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]), Ship->GetActorLocation().Z), Args.Last().ToLower() == TEXT("add"));
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: patrol %s"), bOk ? TEXT("ordered") : TEXT("refused"));
			}
			else if (Verb == TEXT("dock"))
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("ship: dock %s"), Ship->Dock() ? TEXT("ordered") : TEXT("refused: no berth in reach"));
			}
			else if (Verb == TEXT("stop"))
			{
				Ship->StopSailing();
			}
			else if (Verb == TEXT("moor") && Args.Num() >= 4)
			{
				Ship->Moor(FVector(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]), Ship->GetActorLocation().Z), FCString::Atof(*Args[3]));
			}
			else if (Verb == TEXT("pos"))
			{
				// where everyone aboard stands, and on what: for the tests
				TArray<AVLKing*> In;
				Ship->GetAboard(In);
				for (const AVLKing* U : In)
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("ship: aboard %s at %s"), *U->GetDisplayName(), *U->GetFeet().ToCompactString());
				}
			}
		}));
}
