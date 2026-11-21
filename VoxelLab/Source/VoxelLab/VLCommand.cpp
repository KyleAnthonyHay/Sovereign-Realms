#include "VLCommand.h"
#include "VoxelLab.h"
#include "VLGrid.h"
#include "VLKing.h"
#include "VLSwordsmanCombat.h"
#include "VLArcherCombat.h"
#include "VLBattle.h"
#include "VLConstruction.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Components/StaticMeshComponent.h"
#include "HAL/IConsoleManager.h"

namespace
{
	constexpr float Spacing = 125.f;        // between units in a formation: two capsule radii and a gap

	bool ParseLookout(const AActor* Tower, float& FloorZ, FBox2D& Free)
	{
		if (!Tower)
		{
			return false;
		}
		for (const FName& Tag : Tower->Tags)
		{
			const FString S = Tag.ToString();
			if (S.StartsWith(TEXT("Lookout:")))
			{
				TArray<FString> V;
				S.Mid(8).ParseIntoArray(V, TEXT(";"));
				if (V.Num() >= 5)
				{
					// metres in the mesh's own space with +Y north (Blender) -> centimetres, Unreal's +Y south
					FloorZ = FCString::Atof(*V[0]) * 100.f;
					const float X0 = FCString::Atof(*V[1]) * 100.f, Y0 = FCString::Atof(*V[2]) * 100.f, X1 = FCString::Atof(*V[3]) * 100.f, Y1 = FCString::Atof(*V[4]) * 100.f;
					Free = FBox2D(FVector2D(FMath::Min(X0, X1), FMath::Min(-Y0, -Y1)), FVector2D(FMath::Max(X0, X1), FMath::Max(-Y0, -Y1)));
					return true;
				}
			}
		}
		return false;
	}

	/** The posts of a lookout, in the order they are manned: the middles of its four sides, then its corners. */
	bool PostLocal(const FBox2D& Free, int32 Post, FVector2D& Out, FVector2D& Outward)
	{
		static const FVector2D Where[8] = { {0, 1}, {1, 0}, {-1, 0}, {0, -1}, {1, 1}, {-1, 1}, {1, -1}, {-1, -1} };
		if (Post < 0 || Post >= 8)
		{
			return false;
		}
		const FVector2D Half = Free.GetSize() * 0.5f - FVector2D(60.f, 60.f);     // a step in from the rail
		Out = Free.GetCenter() + Where[Post] * Half;
		Outward = Where[Post].GetSafeNormal();
		return Half.X > 0.f && Half.Y > 0.f;
	}
}

UVLCommand* UVLCommand::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLCommand>() : nullptr;
}

bool UVLCommand::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

// ------------------------------------------------------------------------------------------------ selection

void UVLCommand::GetSelection(TArray<AVLKing*>& Out) const
{
	Out.Reset();
	for (const TWeakObjectPtr<AVLKing>& U : Selection)
	{
		if (U.IsValid() && U->IsAlive())
		{
			Out.Add(U.Get());
		}
	}
}

int32 UVLCommand::NumSelected() const
{
	int32 N = 0;
	for (const TWeakObjectPtr<AVLKing>& U : Selection)
	{
		N += (U.IsValid() && U->IsAlive()) ? 1 : 0;
	}
	return N;
}

bool UVLCommand::IsSelected(const AVLKing* Unit) const
{
	return Unit && Selection.Contains(Unit);
}

void UVLCommand::Select(const TArray<AVLKing*>& Units, bool bAdd)
{
	if (!bAdd)
	{
		Selection.Reset();
	}
	for (AVLKing* U : Units)
	{
		if (U && U->IsAlive() && U->Team == UVLBattle::Player)        // the player commands only their own
		{
			Selection.AddUnique(U);
		}
	}
}

void UVLCommand::Toggle(AVLKing* Unit)
{
	if (!Unit || Unit->IsDead() || Unit->Team != UVLBattle::Player)
	{
		return;
	}
	if (Selection.Contains(Unit))
	{
		Selection.Remove(Unit);
	}
	else
	{
		Selection.Add(Unit);
	}
}

// ------------------------------------------------------------------------------------------------ formations

void VLFormation::ComputeSlots(const TArray<AVLKing*>& Units, const FVector2D& Destination, TArray<FVector2D>& OutSlots, EVLFormation Shape)
{
	const int32 Num = Units.Num();
	OutSlots.Init(Destination, Num);
	if (Num <= 1)
	{
		return;
	}
	FVector2D Centroid = FVector2D::ZeroVector, AvgFacing = FVector2D::ZeroVector;
	for (const AVLKing* U : Units)
	{
		Centroid += FVector2D(U->GetActorLocation());
		AvgFacing += FVector2D(U->GetActorForwardVector());
	}
	Centroid /= Num;
	// face the direction of travel; for tiny shuffles keep the facing the group already has
	FVector2D Fwd = Destination - Centroid;
	if (Fwd.SizeSquared() < FMath::Square(150.f))
	{
		Fwd = AvgFacing;
	}
	Fwd = Fwd.GetSafeNormal();
	if (Fwd.IsNearlyZero())
	{
		Fwd = FVector2D(1.f, 0.f);
	}
	const FVector2D Right(-Fwd.Y, Fwd.X);
	auto Pos = [&](int32 i) { return FVector2D(Units[i]->GetActorLocation()); };

	if (Shape == EVLFormation::Loose)
	{
		// each keeps its place relative to the group; a group spread wide is drawn in so it does not arrive scattered
		const float MaxR = Spacing * (0.8f * FMath::Sqrt(float(Num)) + 1.f);
		float R = 0.f;
		for (int32 i = 0; i < Num; ++i)
		{
			R = FMath::Max(R, float(FVector2D::Distance(Pos(i), Centroid)));
		}
		const float Squeeze = R > MaxR ? MaxR / R : 1.f;
		for (int32 i = 0; i < Num; ++i)
		{
			OutSlots[i] = Destination + (Pos(i) - Centroid) * Squeeze;
		}
		return;
	}

	int32 Columns = FMath::Clamp(FMath::CeilToInt(FMath::Sqrt(Num * 2.2f)), 1, 12);
	if (Shape == EVLFormation::Column)
	{
		Columns = FMath::Clamp(FMath::CeilToInt(FMath::Sqrt(float(Num)) * 0.5f), 2, 3);
	}
	else if (Shape == EVLFormation::Square)
	{
		Columns = FMath::Max(FMath::CeilToInt(FMath::Sqrt(float(Num))), 1);
	}

	// melee first, so they take the front ranks
	TArray<int32> Melee, Ranged;
	for (int32 i = 0; i < Num; ++i)
	{
		(Units[i]->IsRanged() ? Ranged : Melee).Add(i);
	}
	TArray<TArray<int32>> Ranks;
	auto BuildRanks = [&](TArray<int32>& Group)
	{
		if (Group.Num() == 0)
		{
			return;
		}
		Group.Sort([&](int32 A, int32 B) { return FVector2D::DotProduct(Pos(A), Fwd) > FVector2D::DotProduct(Pos(B), Fwd); });   // front-most to the front rank
		TArray<int32> Counts;
		if (Shape == EVLFormation::Wedge)
		{
			int32 Left = Group.Num();
			int32 W = Ranks.Num() * 2 + 1;
			while (Left > 0)
			{
				Counts.Add(FMath::Min(W, Left));
				Left -= W;
				W += 2;
			}
		}
		else
		{
			const int32 RankCount = FMath::DivideAndRoundUp(Group.Num(), Columns);
			const int32 Base = Group.Num() / RankCount;
			int32 Extra = Group.Num() % RankCount;
			for (int32 r = 0; r < RankCount; ++r)
			{
				Counts.Add(Base + (Extra-- > 0 ? 1 : 0));       // even ranks rather than one full and one stub
			}
		}
		int32 Cursor = 0;
		for (int32 Count : Counts)
		{
			TArray<int32>& Rank = Ranks.AddDefaulted_GetRef();
			for (int32 k = 0; k < Count; ++k)
			{
				Rank.Add(Group[Cursor++]);
			}
			Rank.Sort([&](int32 A, int32 B) { return FVector2D::DotProduct(Pos(A), Right) < FVector2D::DotProduct(Pos(B), Right); });   // left stays left
		}
	};
	BuildRanks(Melee);
	BuildRanks(Ranged);
	const float DepthOffset = (Ranks.Num() - 1) * 0.5f * Spacing;
	for (int32 r = 0; r < Ranks.Num(); ++r)
	{
		for (int32 k = 0; k < Ranks[r].Num(); ++k)
		{
			const float Lateral = (k - (Ranks[r].Num() - 1) * 0.5f) * Spacing;
			OutSlots[Ranks[r][k]] = Destination + Fwd * (DepthOffset - r * Spacing) + Right * Lateral;
		}
	}
}

const TCHAR* UVLCommand::FormationName(EVLFormation Shape)
{
	switch (Shape)
	{
	case EVLFormation::Column: return TEXT("Column");
	case EVLFormation::Wedge: return TEXT("Wedge");
	case EVLFormation::Square: return TEXT("Square");
	case EVLFormation::Loose: return TEXT("Loose");
	default: return TEXT("Line");
	}
}

EVLFormation UVLCommand::SelectionFormation() const
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	const int32 P = PlatoonOf(Units);
	return P != INDEX_NONE ? Platoons[P].Formation : LooseFormation;
}

void UVLCommand::CycleFormation()
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	const int32 P = PlatoonOf(Units);
	EVLFormation& F = P != INDEX_NONE ? Platoons[P].Formation : LooseFormation;
	F = EVLFormation((int32(F) + 1) % 5);
}

bool UVLCommand::SetFormationByName(const FString& Name)
{
	for (int32 i = 0; i < 5; ++i)
	{
		if (Name.Equals(FormationName(EVLFormation(i)), ESearchCase::IgnoreCase))
		{
			TArray<AVLKing*> Units;
			GetSelection(Units);
			const int32 P = PlatoonOf(Units);
			(P != INDEX_NONE ? Platoons[P].Formation : LooseFormation) = EVLFormation(i);
			return true;
		}
	}
	return false;
}

// ------------------------------------------------------------------------------------------------ orders

void UVLCommand::AddMarker(const FVector& At)
{
	const double Now = GetWorld()->GetRealTimeSeconds();
	Markers.RemoveAll([Now](const FMarker& M) { return Now - M.Time > MarkerSeconds; });
	Markers.Add({ At, Now });
}

void UVLCommand::OrderMove(const TArray<AVLKing*>& InUnits, const FVector& Ground, bool bRun, EVLFormation Shape, bool bQueue)
{
	TArray<AVLKing*> Units;
	for (AVLKing* U : InUnits)
	{
		if (U && U->IsAlive())
		{
			Units.AddUnique(U);
		}
	}
	if (Units.Num() == 0)
	{
		return;
	}
	if (!bInnerOrder)
	{
		ClearStanding(Units);       // a new order ends a patrol, a guard, a hold, a roam
	}
	// march together: nobody faster than the slowest of them (a single unit: its own pace)
	{
		const bool bTogether = MarchTogether(Units, Shape);
		float Slowest = TNumericLimits<float>::Max();
		for (const AVLKing* U : Units)
		{
			Slowest = FMath::Min(Slowest, bRun ? U->RunSpeed : U->WalkSpeed);
		}
		for (AVLKing* U : Units)
		{
			U->PaceCap = (bTogether && Slowest < (bRun ? U->RunSpeed : U->WalkSpeed) - 1.f) ? Slowest : 0.f;
		}
	}
	for (AVLKing* U : Units)
	{
		U->bAttackMove = false;     // a plain move (UVLBattle::AttackMove sets it again for the commander's)
		if (bQueue && U->IsOnOrder())
		{
			continue;               // it finishes what it is doing first
		}
		Detach(U);                  // a new order ends a march to the tower, and brings down whoever stands on it
		StopAttack(U);              // and an attack
		U->ClearQueue();            // and the rest of its pathway
	}
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!Grid || !Grid->EnsureBuilt())
	{
		for (AVLKing* U : Units)
		{
			const FVector P(Ground.X, Ground.Y, U->GetFeet().Z);
			if (bQueue && U->IsOnOrder())
			{
				U->QueueLeg(P, bRun);
			}
			else
			{
				U->FollowPath({ P }, bRun);       // no grid in this level: straight there
			}
		}
		if (Units[0]->Team == UVLBattle::Player && !bQuietMove)
		{
			AddMarker(Ground);
		}
		return;
	}
	// A click on a roof, a cliff or the water means "go there": beside it, on ground the group can walk to (the
	// group's ground is its first member's; one cut off from the rest is sorted out per walker by the grid).
	int32 Lead = Grid->NodeAt(Units[0]->GetFeet());
	if (Lead == INDEX_NONE)
	{
		Lead = Grid->NearestNode(Units[0]->GetFeet(), 6);
	}
	int32 DestNode = Grid->NearestNode(Ground, 60, Grid->RegionOf(Lead));
	if (DestNode == INDEX_NONE)
	{
		DestNode = Grid->NearestNode(Ground, 60);
	}
	if (DestNode == INDEX_NONE)
	{
		return;
	}
	FVector Dest = Grid->NodePos(DestNode);
	if (FMath::Abs(Ground.X - Dest.X) <= Grid->GetCellSize() * 0.5f && FMath::Abs(Ground.Y - Dest.Y) <= Grid->GetCellSize() * 0.5f)
	{
		Dest.X = Ground.X;          // the very point clicked, when it is open ground
		Dest.Y = Ground.Y;
	}

	if (Units[0]->Team == UVLBattle::Player && !bQuietMove)
	{
		UE_LOG(LogVoxelLab, Log, TEXT("move: ground %s lead %s (node %d region %d, main %d) dest node %d region %d at %s"), *Ground.ToCompactString(), *Units[0]->GetFeet().ToCompactString(),
			Lead, Grid->RegionOf(Lead), Grid->MainRegion(), DestNode, Grid->RegionOf(DestNode), *Dest.ToCompactString());
	}
	TArray<FVector2D> Slots2D;
	VLFormation::ComputeSlots(Units, FVector2D(Dest), Slots2D, Shape);
	TArray<FVector> Slots;
	Grid->FitSlots(Dest, Slots2D, Slots);       // no slot over a cliff's edge, in the water or inside a wall

	TArray<FVector> Starts;
	for (AVLKing* U : Units)
	{
		Starts.Add(U->GetFeet());
	}
	TArray<TArray<FVector>> Paths;
	TArray<FVector> Ends;
	Grid->FindGroupPaths(Starts, Dest, Paths, &Ends);
	for (int32 i = 0; i < Units.Num(); ++i)
	{
		TArray<FVector> Path = Paths.IsValidIndex(i) ? Paths[i] : TArray<FVector>();
		FVector Slot = Slots.IsValidIndex(i) ? Slots[i] : Dest;
		// a walker cut off from the goal goes as near as its own ground comes, not to its slot
		if (Ends.IsValidIndex(i) && FVector::DistSquared2D(Ends[i], Dest) > FMath::Square(Grid->GetCellSize()))
		{
			Slot = Ends[i];
		}
		if (bQueue && Units[i]->IsOnOrder())
		{
			Units[i]->QueueLeg(Slot, bRun);         // its route is planned when it gets there
			continue;
		}
		Path.Add(Slot);
		Units[i]->FollowPath(Path, bRun);
	}
	if (Units[0]->Team == UVLBattle::Player && !bQuietMove)
	{
		AddMarker(Dest);
	}
}

// ------------------------------------------------------------------------------------------------ attacks

void UVLCommand::GetDummies(TArray<AActor*>& Out) const
{
	Out.Reset();
	// (B: from the battle's cached list of the level's dummies, not a walk over every actor)
	if (const UVLBattle* Battle = UVLBattle::Get(this); Battle && UVLBattle::UseRegistry())
	{
		for (const TWeakObjectPtr<AActor>& D : Battle->Dummies())
		{
			if (AActor* A = D.Get())
			{
				Out.Add(A);
			}
		}
	}
	else
	{
		for (TActorIterator<AActor> It(GetWorld()); It; ++It)
		{
			if (It->ActorHasTag(TEXT("Dummy")))
			{
				Out.Add(*It);
			}
		}
	}
	Out.Sort([](const AActor& A, const AActor& B) { return A.GetName() < B.GetName(); });
}

AActor* UVLCommand::DummyAt(const APlayerController* PC, const FVector2D& Point) const
{
	if (!PC)
	{
		return nullptr;
	}
	// by its outline on the screen, as units are picked (the one nearest the camera wins)
	const FVector Eye = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : FVector::ZeroVector;
	TArray<AActor*> Dummies;
	GetDummies(Dummies);
	AActor* Best = nullptr;
	float BestDist = TNumericLimits<float>::Max();
	for (AActor* D : Dummies)
	{
		FVector Origin, Extent;
		D->GetActorBounds(false, Origin, Extent);
		const float Tall = FMath::Clamp(float(Extent.Z), 40.f, 120.f);     // (its bounds grow while it rocks)
		FVector2D Foot, Head;
		if (PC->ProjectWorldLocationToScreen(D->GetActorLocation(), Foot) && PC->ProjectWorldLocationToScreen(D->GetActorLocation() + FVector(0.f, 0.f, 2.f * Tall), Head))
		{
			const float High = FMath::Max(FMath::Abs(Foot.Y - Head.Y), 18.f);
			const float Wide = High * 0.4f + 6.f;
			if (Point.X > Head.X - Wide && Point.X < Head.X + Wide && Point.Y > FMath::Min(Head.Y, Foot.Y) - 8.f && Point.Y < FMath::Max(Head.Y, Foot.Y) + 8.f)
			{
				const float Dist = FVector::DistSquared(Eye, D->GetActorLocation());
				if (Dist < BestDist)
				{
					BestDist = Dist;
					Best = D;
				}
			}
		}
	}
	return Best;
}

bool UVLCommand::CanAttack(const AVLKing* Unit)
{
	return UVLSwordsmanCombat::CanFight(Unit) || UVLArcherCombat::CanFight(Unit);
}

int32 UVLCommand::OrderAttack(const TArray<AVLKing*>& InUnits, AActor* Target, bool bRun, bool bMarker)
{
	if (!Target)
	{
		return 0;
	}
	// never at a friend: only those of Units for whom the target is a foe (a dummy is anybody's)
	const UVLBattle* Battle = UVLBattle::Get(this);
	const bool bDummy = Target->ActorHasTag(TEXT("Dummy"));
	TArray<AVLKing*> Units;
	for (AVLKing* U : InUnits)
	{
		if (U && U->IsAlive() && (bDummy || !Battle || Battle->IsHostile(Target, U->Team)))
		{
			U->bAutoAttack = false;
			U->PaceCap = 0.f;       // a fight is fought at full speed
			Units.Add(U);
		}
	}
	if (!bInnerOrder)
	{
		TArray<AVLKing*> Fighters = Units.FilterByPredicate([](const AVLKing* U) { return CanAttack(U); });
		ClearStanding(Fighters);    // an attack ordered ends a patrol or a guard (a fight of their own on one does not)
	}
	int32 Ordered = 0;
	Ordered += UVLSwordsmanCombat::OrderAttack(Units, Target, bRun);        // the swordsmen among them
	Ordered += UVLArcherCombat::OrderAttack(Units, Target, bRun);           // the archers (those on the tower shoot from it)
	if (Ordered > 0 && bMarker && Units[0]->Team == UVLBattle::Player)
	{
		AddMarker(Target->GetActorLocation());
	}
	return Ordered;
}

void UVLCommand::OnUnitDied(AVLKing* Unit)
{
	if (!Unit)
	{
		return;
	}
	Selection.Remove(Unit);
	for (int32 i = 0; i < MaxPlatoons; ++i)
	{
		FPlatoon& P = Platoons[i];
		const bool bWas = P.Members.Contains(Unit);
		P.Members.Remove(Unit);     // (a platoon whose last troop falls is struck off by itself: its slot is empty)
		P.Members.RemoveAll([](const TWeakObjectPtr<AVLKing>& M) { return !M.IsValid() || M->IsDead(); });
		if (bWas && P.Members.Num() == 0 && Unit->Team == UVLBattle::Player && Unit->GetHealth() <= 0.f)
		{
			if (UVLBattle* Battle = UVLBattle::Get(this))
			{
				const FVector At = Unit->GetActorLocation();
				Battle->PushAlert(FString::Printf(TEXT("Platoon %d has fallen"), i + 1), EVLAlert::Lost, &At);    // (the main game's alert)
			}
		}
	}
	StopAttack(Unit);
	Detach(Unit);
	ClearStanding({ Unit });
}

const TCHAR* UVLCommand::StanceName(EVLStance Stance)
{
	return Stance == EVLStance::Defensive ? TEXT("Defensive") : (Stance == EVLStance::Hold ? TEXT("Hold ground") : TEXT("Aggressive"));
}

EVLStance UVLCommand::SelectionStance() const
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	const int32 P = PlatoonOf(Units);
	return P != INDEX_NONE ? Platoons[P].Stance : (Units.Num() > 0 ? Units[0]->Stance : EVLStance::Aggressive);
}

void UVLCommand::CycleStance()
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	if (Units.Num() == 0)
	{
		return;
	}
	const EVLStance Next = EVLStance((int32(SelectionStance()) + 1) % 3);
	const int32 P = PlatoonOf(Units);
	if (P != INDEX_NONE)
	{
		Platoons[P].Stance = Next;
	}
	for (AVLKing* U : Units)
	{
		U->Stance = Next;
		U->Post = U->GetFeet();
	}
	UE_LOG(LogVoxelLab, Log, TEXT("stance: %d unit(s) %s"), Units.Num(), StanceName(Next));
}

void UVLCommand::StopAttack(AVLKing* Unit)
{
	if (UVLSwordsmanCombat* Sword = UVLSwordsmanCombat::For(Unit, false))
	{
		Sword->Stop();
	}
	if (UVLArcherCombat* Bow = UVLArcherCombat::For(Unit, false))
	{
		Bow->Stop();
	}
	if (UVLBuilderWork* Work = UVLBuilderWork::For(Unit, false))
	{
		Work->Stop();           // a Builder's job (VLConstruction.*): any other order ends it
	}
}

void UVLCommand::ArmAttackGround(bool bArm)
{
	if (bArm)
	{
		Arm(EVLArm::AttackGround);
	}
	else if (Armed == EVLArm::AttackGround)
	{
		Arm(EVLArm::None);
	}
}

bool UVLCommand::IsAttackGroundArmed() const
{
	return GetArmed() == EVLArm::AttackGround;
}

int32 UVLCommand::OrderAttackGround(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun)
{
	for (AVLKing* U : Units)
	{
		if (UVLArcherCombat::CanFight(U))
		{
			StopAttack(U);          // whatever they were shooting at
			ClearStanding({ U });
		}
	}
	const int32 Ordered = UVLArcherCombat::OrderAttackGround(Units, Ground, bRun);
	if (Ordered > 0)
	{
		AddMarker(Ground);
	}
	return Ordered;
}

void UVLCommand::OnOrderEnded(AVLKing* Unit, bool bArrived)
{
	if (!Unit)
	{
		return;
	}
	AActor* Tower = Unit->PendingGarrison.Get();
	if (Tower)
	{
		Unit->PendingGarrison = nullptr;
		if (FVector::Dist2D(Unit->GetFeet(), DoorPoint(Tower)) < 320.f)
		{
			Enter(Unit, Tower);
		}
		else
		{
			Detach(Unit);           // it could not get there: its post is free again
			UE_LOG(LogVoxelLab, Log, TEXT("%s could not reach %s"), *Unit->GetDisplayName(), *Tower->GetName());
		}
	}
}

// ------------------------------------------------------------------------------------------------ platoons

void UVLCommand::AssignPlatoon(int32 Index, const TArray<AVLKing*>& Units)
{
	if (Index < 0 || Index >= MaxPlatoons)
	{
		return;
	}
	Platoons[Index].Members.Reset();
	AddToPlatoon(Index, Units);
}

void UVLCommand::AddToPlatoon(int32 Index, const TArray<AVLKing*>& Units)
{
	if (Index < 0 || Index >= MaxPlatoons)
	{
		return;
	}
	for (AVLKing* U : Units)
	{
		if (!U || U->IsDead() || U->Team != UVLBattle::Player)
		{
			continue;
		}
		for (FPlatoon& P : Platoons)            // a unit belongs to one platoon at most
		{
			P.Members.Remove(U);
		}
		Platoons[Index].Members.Add(U);
		U->Stance = Platoons[Index].Stance;     // the platoon's stance is pushed to its members
	}
}

void UVLCommand::CyclePlatoonFormation(int32 Index)
{
	if (Index >= 0 && Index < MaxPlatoons)
	{
		Platoons[Index].Formation = EVLFormation((int32(Platoons[Index].Formation) + 1) % 5);
	}
}

void UVLCommand::CyclePlatoonStance(int32 Index)
{
	if (Index < 0 || Index >= MaxPlatoons)
	{
		return;
	}
	FPlatoon& P = Platoons[Index];
	P.Stance = EVLStance((int32(P.Stance) + 1) % 3);
	for (const TWeakObjectPtr<AVLKing>& U : P.Members)
	{
		if (U.IsValid() && U->IsAlive())
		{
			U->Stance = P.Stance;
			U->Post = U->GetFeet();
		}
	}
	UE_LOG(LogVoxelLab, Log, TEXT("stance: platoon %d %s"), Index + 1, StanceName(P.Stance));
}

void UVLCommand::DisbandPlatoon(int32 Index)
{
	if (Index >= 0 && Index < MaxPlatoons)
	{
		Platoons[Index].Members.Reset();
		UE_LOG(LogVoxelLab, Log, TEXT("platoon %d disbanded"), Index + 1);
	}
}

void UVLCommand::GetPlatoon(int32 Index, TArray<AVLKing*>& Out) const
{
	Out.Reset();
	if (Index < 0 || Index >= MaxPlatoons)
	{
		return;
	}
	for (const TWeakObjectPtr<AVLKing>& U : Platoons[Index].Members)
	{
		if (U.IsValid() && U->IsAlive())
		{
			Out.Add(U.Get());
		}
	}
}

int32 UVLCommand::PlatoonIndexOf(const AVLKing* Unit) const
{
	// (the first platoon the unit is a living member of, as a search of GetPlatoon(0..) finds it)
	if (Unit && Unit->IsAlive())
	{
		for (int32 i = 0; i < MaxPlatoons; ++i)
		{
			if (Platoons[i].Members.Contains(Unit))
			{
				return i;
			}
		}
	}
	return INDEX_NONE;
}

void UVLCommand::GetPlatoonMap(TMap<const AVLKing*, int32>& Out) const
{
	Out.Reset();
	for (int32 i = 0; i < MaxPlatoons; ++i)
	{
		for (const TWeakObjectPtr<AVLKing>& U : Platoons[i].Members)
		{
			if (const AVLKing* Unit = U.Get(); Unit && Unit->IsAlive() && !Out.Contains(Unit))
			{
				Out.Add(Unit, i);
			}
		}
	}
}

void UVLCommand::GetSelectionSet(TSet<const AVLKing*>& Out) const
{
	// (as IsSelected has it: whoever is in the selection, alive or not)
	Out.Reset();
	for (const TWeakObjectPtr<AVLKing>& U : Selection)
	{
		if (const AVLKing* Unit = U.Get())
		{
			Out.Add(Unit);
		}
	}
}

int32 UVLCommand::PlatoonOf(const TArray<AVLKing*>& Units) const
{
	if (Units.Num() == 0)
	{
		return INDEX_NONE;
	}
	for (int32 i = 0; i < MaxPlatoons; ++i)
	{
		TArray<AVLKing*> Members;
		GetPlatoon(i, Members);
		if (Members.Num() != Units.Num())
		{
			continue;
		}
		bool bAll = true;
		for (AVLKing* U : Units)
		{
			bAll &= Members.Contains(U);
		}
		if (bAll)
		{
			return i;
		}
	}
	return INDEX_NONE;
}

FString UVLCommand::PlatoonName(int32 Index) const
{
	TArray<AVLKing*> Members;
	GetPlatoon(Index, Members);
	int32 Ranged = 0, Melee = 0, Kings = 0;
	for (const AVLKing* U : Members)
	{
		if (!U->IsTroop())
		{
			++Kings;
		}
		else if (U->IsRanged())
		{
			++Ranged;
		}
		else
		{
			++Melee;
		}
	}
	if (Members.Num() == 0)
	{
		return TEXT("-");
	}
	const TCHAR* Kind = Kings > 0 ? TEXT("King's guard") : (Ranged == 0 ? TEXT("Swordsmen") : (Melee == 0 ? TEXT("Archers") : TEXT("Mixed host")));
	return FString::Printf(TEXT("%s x%d"), Kind, Members.Num());
}

FVector UVLCommand::PlatoonCentre(int32 Index) const
{
	TArray<AVLKing*> Members;
	GetPlatoon(Index, Members);
	FVector C = FVector::ZeroVector;
	for (const AVLKing* U : Members)
	{
		C += U->GetActorLocation();
	}
	return Members.Num() > 0 ? C / Members.Num() : C;
}

// ------------------------------------------------------------------------------------------------ the watch tower

bool UVLCommand::IsTower(const AActor* Building)
{
	float Z;
	FBox2D Free;
	return ParseLookout(Building, Z, Free);
}

UVLCommand::FTower& UVLCommand::TowerFor(AActor* Tower)
{
	for (FTower& T : Towers)
	{
		if (T.Actor.Get() == Tower)
		{
			return T;
		}
	}
	FTower& T = Towers.AddDefaulted_GetRef();
	T.Actor = Tower;
	T.Posts.SetNum(8);
	return T;
}

const UVLCommand::FTower* UVLCommand::FindTower(const AActor* Tower) const
{
	for (const FTower& T : Towers)
	{
		if (T.Actor.Get() == Tower)
		{
			return &T;
		}
	}
	return nullptr;
}

int32 UVLCommand::TowerCapacity(const AActor* Tower) const
{
	return IsTower(Tower) ? 8 : 0;
}

int32 UVLCommand::TowerCount(const AActor* Tower) const
{
	TArray<AVLKing*> In;
	GetGarrison(Tower, In);
	return In.Num();
}

void UVLCommand::GetGarrison(const AActor* Tower, TArray<AVLKing*>& Out) const
{
	Out.Reset();
	if (const FTower* T = FindTower(Tower))
	{
		for (const TWeakObjectPtr<AVLKing>& U : T->Posts)
		{
			if (U.IsValid() && U->GarrisonIn.Get() == Tower)
			{
				Out.Add(U.Get());
			}
		}
	}
}

bool UVLCommand::PostWorld(const AActor* Tower, int32 Post, FVector& OutFeet, FRotator& OutFacing) const
{
	float FloorZ;
	FBox2D Free;
	FVector2D Local, Outward;
	if (!ParseLookout(Tower, FloorZ, Free) || !PostLocal(Free, Post, Local, Outward))
	{
		return false;
	}
	const FTransform Xf = Tower->GetActorTransform();
	OutFeet = Xf.TransformPosition(FVector(Local.X, Local.Y, FloorZ) / Xf.GetScale3D().X);     // (the tag's numbers are already scaled)
	OutFacing = Xf.TransformVectorNoScale(FVector(Outward.X, Outward.Y, 0.f)).Rotation();
	return true;
}

FVector UVLCommand::DoorPoint(const AActor* Tower) const
{
	// in front of its front (buildings face their local +Y in Unreal: Blender's -Y), just clear of its steps
	FVector Origin, Extent;
	Tower->GetActorBounds(true, Origin, Extent);
	const FVector Front = Tower->GetActorRotation().RotateVector(FVector(0.f, 1.f, 0.f));
	const float Reach = FMath::Abs(Front.X) * Extent.X + FMath::Abs(Front.Y) * Extent.Y;
	FVector P(Origin.X + Front.X * (Reach + 80.f), Origin.Y + Front.Y * (Reach + 80.f), Tower->GetActorLocation().Z);
	if (UVLGrid* Grid = UVLGrid::Get(this))
	{
		if (Grid->EnsureBuilt())
		{
			const int32 Node = Grid->NearestNode(P, 30, Grid->MainRegion());
			if (Node != INDEX_NONE)
			{
				P = Grid->NodePos(Node);
			}
		}
	}
	return P;
}

void UVLCommand::OrderGarrison(const TArray<AVLKing*>& InUnits, AActor* Tower, bool bRun)
{
	if (!IsTower(Tower))
	{
		return;
	}
	FTower& T = TowerFor(Tower);
	TArray<AVLKing*> Going, Others;
	for (AVLKing* U : InUnits)
	{
		if (!U || U->IsDead() || U->GarrisonIn.Get() == Tower)
		{
			continue;
		}
		if (const UVLBattle* Battle = UVLBattle::Get(this); Battle && Battle->TeamOf(Tower) != UVLBattle::Neutral && Battle->TeamOf(Tower) != U->Team)
		{
			continue;           // a lookout of the other side's is no place for it
		}
		if (!U->IsRanged())
		{
			Others.AddUnique(U);
			continue;
		}
		// a post of its own, kept for it while it walks there
		int32 Post = T.Posts.IndexOfByPredicate([U](const TWeakObjectPtr<AVLKing>& P) { return P.Get() == U; });
		if (Post == INDEX_NONE)
		{
			Post = T.Posts.IndexOfByPredicate([Tower](const TWeakObjectPtr<AVLKing>& P) { return !P.IsValid() || (P->GarrisonIn.Get() != Tower && P->PendingGarrison.Get() != Tower); });
		}
		if (Post == INDEX_NONE)
		{
			Others.AddUnique(U);        // the lookout is full: it waits below with the rest
			continue;
		}
		Going.AddUnique(U);
		T.Posts[Post] = U;
	}
	const FVector Door = DoorPoint(Tower);
	if (Going.Num() > 0)
	{
		OrderMove(Going, Door, bRun, EVLFormation::Column);
		FTower& T2 = TowerFor(Tower);       // (OrderMove detached them: give them their posts back)
		for (AVLKing* U : Going)
		{
			if (!T2.Posts.Contains(U))
			{
				const int32 Post = T2.Posts.IndexOfByPredicate([Tower](const TWeakObjectPtr<AVLKing>& P) { return !P.IsValid() || (P->GarrisonIn.Get() != Tower && P->PendingGarrison.Get() != Tower); });
				if (Post != INDEX_NONE)
				{
					T2.Posts[Post] = U;
				}
			}
			U->PendingGarrison = Tower;
			if (!U->HasOrder())
			{
				OnOrderEnded(U, true);  // it stood at the door already
			}
		}
	}
	if (Others.Num() > 0)
	{
		const FVector Front = Tower->GetActorRotation().RotateVector(FVector(0.f, 1.f, 0.f));
		OrderMove(Others, Door + Front * 260.f, bRun, EVLFormation::Line);
	}
}

void UVLCommand::Enter(AVLKing* Unit, AActor* Tower)
{
	FTower& T = TowerFor(Tower);
	int32 Post = T.Posts.IndexOfByPredicate([Unit](const TWeakObjectPtr<AVLKing>& P) { return P.Get() == Unit; });
	if (Post == INDEX_NONE)
	{
		Post = T.Posts.IndexOfByPredicate([Tower](const TWeakObjectPtr<AVLKing>& P) { return !P.IsValid() || (P->GarrisonIn.Get() != Tower && P->PendingGarrison.Get() != Tower); });
	}
	FVector Feet;
	FRotator Facing;
	if (Post == INDEX_NONE || !PostWorld(Tower, Post, Feet, Facing))
	{
		return;
	}
	T.Posts[Post] = Unit;
	Unit->GarrisonIn = Tower;
	Unit->StopOrder();
	// there are no stairs: it is put on the lookout's floor, the way the main game mans its towers
	const float Half = Unit->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	Unit->SetActorLocationAndRotation(Feet + FVector(0.f, 0.f, Half + 4.f), Facing, false, nullptr, ETeleportType::TeleportPhysics);
	Unit->GetCharacterMovement()->StopMovementImmediately();
	UE_LOG(LogVoxelLab, Log, TEXT("%s mans post %d of %s (%d of %d)"), *Unit->GetDisplayName(), Post, *Tower->GetName(), TowerCount(Tower), TowerCapacity(Tower));
}

void UVLCommand::Leave(AVLKing* Unit)
{
	AActor* Tower = Unit ? Unit->GarrisonIn.Get() : nullptr;
	if (!Tower)
	{
		return;
	}
	Unit->GarrisonIn = nullptr;
	FVector Door = DoorPoint(Tower);
	// beside whoever stands there already
	int32 Down = 0;
	if (const UVLBattle* Battle = UVLBattle::Get(this))
	{
		for (const AVLKing* Other : Battle->AllUnits())
		{
			Down += (Other != Unit && !Other->GarrisonIn.IsValid() && FVector::Dist2D(Other->GetFeet(), Door) < 420.f) ? 1 : 0;
		}
	}
	if (UVLGrid* Grid = UVLGrid::Get(this))
	{
		TArray<FVector2D> Spots;
		TArray<FVector> Fitted;
		const FVector Front = Tower->GetActorRotation().RotateVector(FVector(0.f, 1.f, 0.f));
		const FVector Side(-Front.Y, Front.X, 0.f);
		for (int32 i = 0; i <= Down; ++i)
		{
			Spots.Add(FVector2D(Door + Front * (60.f + (i / 3) * Spacing) + Side * (((i % 3) - 1) * Spacing)));
		}
		Grid->FitSlots(Door, Spots, Fitted);
		Door = Fitted.Last();
	}
	const float Half = Unit->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	Unit->SetActorLocation(Door + FVector(0.f, 0.f, Half + 4.f), false, nullptr, ETeleportType::TeleportPhysics);
	Unit->GetCharacterMovement()->StopMovementImmediately();
	UE_LOG(LogVoxelLab, Log, TEXT("%s comes down from %s"), *Unit->GetDisplayName(), *Tower->GetName());
}

void UVLCommand::Detach(AVLKing* Unit)
{
	if (!Unit)
	{
		return;
	}
	Unit->PendingGarrison = nullptr;
	if (Unit->GarrisonIn.IsValid())
	{
		Leave(Unit);
	}
	for (FTower& T : Towers)
	{
		for (TWeakObjectPtr<AVLKing>& P : T.Posts)
		{
			if (P.Get() == Unit)
			{
				P = nullptr;
			}
		}
	}
}

void UVLCommand::EmptyTower(AActor* Tower)
{
	TArray<AVLKing*> In;
	GetGarrison(Tower, In);
	if (In.Num() == 0)
	{
		return;
	}
	const FVector Front = Tower->GetActorRotation().RotateVector(FVector(0.f, 1.f, 0.f));
	OrderMove(In, DoorPoint(Tower) + Front * 300.f, false, EVLFormation::Line);
}

// ------------------------------------------------------------------------------------------------ standing orders
// The main game's Stop, Hold, Patrol, Guard, Roam, attack-move, March together and Dismiss (SRPlayerController,
// USRBattleSubsystem::CommandPatrol / ExtendPatrol / ExtendPath / StepPatrols, ASRUnit::OrderGuard / OrderRoam).

namespace
{
	bool IsFightingNow(const AVLKing* U)
	{
		const UVLSwordsmanCombat* S = UVLSwordsmanCombat::For(const_cast<AVLKing*>(U), false);
		const UVLArcherCombat* B = UVLArcherCombat::For(const_cast<AVLKing*>(U), false);
		return (S && S->IsAttacking()) || (B && B->IsAttacking());
	}

	AActor* FightTarget(const AVLKing* U)
	{
		if (const UVLSwordsmanCombat* S = UVLSwordsmanCombat::For(const_cast<AVLKing*>(U), false); S && S->IsAttacking())
		{
			return S->GetTarget();
		}
		const UVLArcherCombat* B = UVLArcherCombat::For(const_cast<AVLKing*>(U), false);
		return B && B->IsAttacking() ? B->GetTarget() : nullptr;
	}

	/** The player plays it (the hero view): standing orders let go of it. */
	bool PlayedByHand(const AVLKing* U)
	{
		return U && Cast<APlayerController>(U->GetController()) && U->IsHeroMode();
	}

	FVector Centroid(const TArray<AVLKing*>& Units)
	{
		FVector C = FVector::ZeroVector;
		for (const AVLKing* U : Units)
		{
			C += U->GetFeet();
		}
		return Units.Num() > 0 ? C / Units.Num() : C;
	}

	TArray<AVLKing*> Living(const TArray<AVLKing*>& Units)
	{
		TArray<AVLKing*> Out;
		for (AVLKing* U : Units)
		{
			if (U && U->IsAlive())
			{
				Out.AddUnique(U);
			}
		}
		return Out;
	}
}

void UVLCommand::ClearStanding(const TArray<AVLKing*>& Units)
{
	for (AVLKing* U : Units)
	{
		if (!U)
		{
			continue;
		}
		U->bHoldOrder = false;
		GuardPosts.RemoveAll([U](const FGuardPost& G) { return G.Unit.Get() == U; });
		Roamers.RemoveAll([U](const FRoamer& R) { return R.Unit.Get() == U; });
	}
	for (int32 i = Routes.Num() - 1; i >= 0; --i)
	{
		Routes[i].Members.RemoveAll([&Units](const TWeakObjectPtr<AVLKing>& M) { return !M.IsValid() || Units.Contains(M.Get()); });
		if (Routes[i].Members.Num() == 0)
		{
			Routes.RemoveAt(i);
		}
	}
}

void UVLCommand::OrderStop(const TArray<AVLKing*>& InUnits)
{
	const TArray<AVLKing*> Units = Living(InUnits);
	ClearStanding(Units);
	for (AVLKing* U : Units)
	{
		StopAttack(U);
		if (U->PendingGarrison.IsValid() && !U->IsGarrisoned())
		{
			Detach(U);              // on its way to the tower: it stays down (one on the lookout stays up there)
		}
		U->StopOrder();
		U->ClearQueue();
		U->bAttackMove = false;
		U->bAutoAttack = false;
		U->PaceCap = 0.f;
		U->Post = U->GetFeet();
	}
	if (Units.Num() > 0)
	{
		UE_LOG(LogVoxelLab, Log, TEXT("stop: %d unit(s)"), Units.Num());
	}
}

void UVLCommand::OrderHold(const TArray<AVLKing*>& InUnits)
{
	const TArray<AVLKing*> Units = Living(InUnits);
	OrderStop(Units);
	for (AVLKing* U : Units)
	{
		U->bHoldOrder = true;
	}
	if (Units.Num() > 0)
	{
		UE_LOG(LogVoxelLab, Log, TEXT("hold: %d unit(s) hold their ground"), Units.Num());
	}
}

int32 UVLCommand::FindRoute(const TArray<AVLKing*>& Units, bool bLoop) const
{
	for (int32 i = 0; i < Routes.Num(); ++i)
	{
		const FRoute& R = Routes[i];
		if (R.bLoop != bLoop)
		{
			continue;
		}
		int32 Live = 0;
		for (const TWeakObjectPtr<AVLKing>& M : R.Members)
		{
			Live += (M.IsValid() && M->IsAlive()) ? 1 : 0;
		}
		if (Live == Units.Num() && !Units.ContainsByPredicate([&R](AVLKing* U) { return !R.Members.Contains(U); }))
		{
			return i;
		}
	}
	return INDEX_NONE;
}

void UVLCommand::IssueLeg(FRoute& R)
{
	TArray<AVLKing*> Live;
	for (const TWeakObjectPtr<AVLKing>& M : R.Members)
	{
		if (M.IsValid() && M->IsAlive())
		{
			Live.Add(M.Get());
		}
	}
	if (Live.Num() == 0 || !R.Points.IsValidIndex(R.Next))
	{
		return;
	}
	{
		TGuardValue<bool> Inner(bInnerOrder, true);
		TGuardValue<bool> Quiet(bQuietMove, true);
		OrderMove(Live, R.Points[R.Next], R.bRun, R.Shape);
	}
	for (AVLKing* U : Live)
	{
		U->bAttackMove = true;      // a patrol and an attack-move fight what they meet
	}
}

void UVLCommand::OrderPatrol(const TArray<AVLKing*>& InUnits, const TArray<FVector>& Points, bool bRun, EVLFormation Shape)
{
	const TArray<AVLKing*> Units = Living(InUnits);
	if (Units.Num() == 0 || Points.Num() == 0)
	{
		return;
	}
	ClearStanding(Units);
	FRoute R;
	for (AVLKing* U : Units)
	{
		R.Members.Add(U);
	}
	R.Points.Add(Centroid(Units));      // from where they stand ...
	R.Points.Append(Points);            // ... through the points, and back
	R.Next = 1;
	R.bLoop = true;
	R.bRun = bRun;
	R.Shape = Shape;
	R.Settle = 1.5f;
	R.Id = NextRouteId++;
	FRoute& Added = Routes.Add_GetRef(R);
	IssueLeg(Added);
	if (Units[0]->Team == UVLBattle::Player)
	{
		AddMarker(Points[0]);
	}
	UE_LOG(LogVoxelLab, Log, TEXT("patrol: %d unit(s), %d point(s) from %s"), Units.Num(), Points.Num(), *R.Points[0].ToCompactString());
}

void UVLCommand::ExtendPatrol(const TArray<AVLKing*>& InUnits, const FVector& Point, EVLFormation Shape)
{
	const TArray<AVLKing*> Units = Living(InUnits);
	const int32 Existing = FindRoute(Units, true);
	if (Existing == INDEX_NONE)
	{
		OrderPatrol(Units, { Point }, false, Shape);
		return;
	}
	Routes[Existing].Points.Add(Point);     // they carry on where they are; the loop now runs through it too
	if (Units.Num() > 0 && Units[0]->Team == UVLBattle::Player)
	{
		AddMarker(Point);
	}
	UE_LOG(LogVoxelLab, Log, TEXT("patrol: point %d at %s"), Routes[Existing].Points.Num(), *Point.ToCompactString());
}

void UVLCommand::OrderAttackMove(const TArray<AVLKing*>& InUnits, const FVector& Ground, bool bRun, EVLFormation Shape, bool bQueue)
{
	const TArray<AVLKing*> Units = Living(InUnits);
	if (Units.Num() == 0)
	{
		return;
	}
	if (bQueue)
	{
		const int32 Existing = FindRoute(Units, false);
		if (Existing != INDEX_NONE)
		{
			Routes[Existing].Points.Add(Ground);
			if (Units[0]->Team == UVLBattle::Player)
			{
				AddMarker(Ground);
			}
			return;
		}
	}
	ClearStanding(Units);
	FRoute R;
	for (AVLKing* U : Units)
	{
		R.Members.Add(U);
	}
	R.Points.Add(Ground);
	R.Next = 0;
	R.bLoop = false;
	R.bRun = bRun;
	R.Shape = Shape;
	R.Settle = 0.8f;
	R.Id = NextRouteId++;
	FRoute& Added = Routes.Add_GetRef(R);
	IssueLeg(Added);
	if (Units[0]->Team == UVLBattle::Player)
	{
		AddMarker(Ground);
	}
	UE_LOG(LogVoxelLab, Log, TEXT("attack-move: %d unit(s) to %s"), Units.Num(), *Ground.ToCompactString());
}

bool UVLCommand::CanBeGuarded(const AActor* Ward, int32 Team) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Ward || !Battle)
	{
		return false;
	}
	if (const AVLKing* U = Cast<AVLKing>(Ward))
	{
		// Builders (as in the main game) and King David; not troops
		return U->IsAlive() && U->Team == Team && (!U->IsTroop() || U->KindId() == EVLUnitKind::Builder);
	}
	const FVLBuildingState* B = Battle->FindBuilding(Ward);
	return B && B->IsAlive() && B->Team == Team;
}

bool UVLCommand::WardPos(const AActor* Ward, FVector& Out) const
{
	if (const AVLKing* U = Cast<AVLKing>(Ward))
	{
		if (!U->IsAlive())
		{
			return false;
		}
		Out = U->GetFeet();
		return true;
	}
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* B = Battle ? Battle->FindBuilding(Ward) : nullptr;
	if (!B || !B->IsAlive())
	{
		return false;
	}
	FVector Origin, Extent;
	Ward->GetActorBounds(true, Origin, Extent);
	Out = FVector(Origin.X, Origin.Y, Ward->GetActorLocation().Z);
	return true;
}

void UVLCommand::GuardPostWorld(const FGuardPost& G, FVector2D& Out) const
{
	FVector W;
	if (Cast<AVLKing>(G.Ward.Get()) && WardPos(G.Ward.Get(), W))
	{
		Out = FVector2D(W) + G.Offset;      // round a unit: the post moves with it
	}
	else
	{
		Out = G.Offset;                     // round a building: a fixed spot just outside its walls
	}
}

int32 UVLCommand::OrderGuard(const TArray<AVLKing*>& InUnits, AActor* Ward)
{
	TArray<AVLKing*> Guards;
	for (AVLKing* U : Living(InUnits))
	{
		if (U != Ward && U->KindId() != EVLUnitKind::Builder && CanBeGuarded(Ward, U->Team))
		{
			Guards.Add(U);
		}
	}
	FVector Centre;
	if (Guards.Num() == 0 || !WardPos(Ward, Centre))
	{
		return 0;
	}
	ClearStanding(Guards);
	// posts in rings round the ward, the nearest guard first so that paths cross little: close round a unit, just
	// outside the walls of a building (its box grown by the ring's margin, corners rounded)
	const bool bUnitWard = Cast<AVLKing>(Ward) != nullptr;
	const UStaticMeshComponent* SMC = bUnitWard ? nullptr : Ward->FindComponentByClass<UStaticMeshComponent>();
	const bool bBox = SMC && SMC->GetStaticMesh();
	const FTransform T = bBox ? SMC->GetComponentTransform() : FTransform::Identity;
	const FBox Box = bBox ? SMC->GetStaticMesh()->GetBoundingBox() : FBox(FVector::ZeroVector, FVector::ZeroVector);
	const FVector2D C2(Centre);
	Guards.Sort([&C2](const AVLKing& A, const AVLKing& B) { return FVector2D::DistSquared(FVector2D(A.GetFeet()), C2) < FVector2D::DistSquared(FVector2D(B.GetFeet()), C2); });
	auto PostAt = [&](float Angle, float Margin) -> FVector2D
	{
		const FVector Dir(FMath::Cos(Angle), FMath::Sin(Angle), 0.f);
		if (!bBox)
		{
			return C2 + FVector2D(Dir) * Margin;
		}
		// where a ray from the box's middle that way leaves the box, then Margin further out
		const FVector Local = T.InverseTransformVectorNoScale(Dir);
		const FVector Half = Box.GetExtent() * T.GetScale3D().GetAbs();
		const float Out = FMath::Min(FMath::Abs(Local.X) > 1e-3f ? float(Half.X / FMath::Abs(Local.X)) : 1e9f, FMath::Abs(Local.Y) > 1e-3f ? float(Half.Y / FMath::Abs(Local.Y)) : 1e9f);
		return FVector2D(T.TransformPosition(Box.GetCenter())) + FVector2D(Dir) * (Out + Margin);
	};
	float Perimeter0 = 2.f * PI * 230.f;
	if (bBox)
	{
		const FVector S = Box.GetSize() * T.GetScale3D();
		Perimeter0 = 2.f * float(S.X + S.Y);
	}
	int32 Placed = 0, Ring = 0;
	TArray<FVector2D> Posts;
	while (Placed < Guards.Num())
	{
		const float Margin = (bUnitWard ? 230.f : 170.f) + Ring * 120.f;
		const float Perimeter = bUnitWard ? 2.f * PI * Margin : Perimeter0 + 2.f * PI * Margin;
		const int32 Cap = FMath::Max(4, FMath::FloorToInt(Perimeter / 130.f));
		const int32 InRing = FMath::Min(Cap, Guards.Num() - Placed);
		const FVector2D First = FVector2D(Guards[Placed]->GetFeet()) - C2;
		const float Start = FMath::Atan2(First.Y, First.X);
		for (int32 k = 0; k < InRing; ++k)
		{
			Posts.Add(PostAt(Start + 2.f * PI * k / InRing + Ring * 0.4f, Margin));
		}
		Placed += InRing;
		++Ring;
	}
	for (int32 i = 0; i < Guards.Num(); ++i)
	{
		AVLKing* U = Guards[i];
		FGuardPost& G = GuardPosts.AddDefaulted_GetRef();
		G.Unit = U;
		G.Ward = Ward;
		G.Offset = bUnitWard ? Posts[i] - C2 : Posts[i];
		// off it goes (the order is given here so that whatever it was doing ends now; it is a leg of the guard)
		{
			TGuardValue<bool> Inner(bInnerOrder, true);
			TGuardValue<bool> Quiet(bQuietMove, true);
			OrderMove({ U }, FVector(Posts[i].X, Posts[i].Y, Centre.Z), false, EVLFormation::Line);
		}
		G.bSent = true;
		G.SentFor = C2;
	}
	if (Guards[0]->Team == UVLBattle::Player)
	{
		AddMarker(Centre);
	}
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* B = Battle ? Battle->FindBuilding(Ward) : nullptr;
	UE_LOG(LogVoxelLab, Log, TEXT("guard: %d unit(s) guard %s"), Guards.Num(), B ? *B->Name : (bUnitWard ? *Cast<AVLKing>(Ward)->GetDisplayName() : *Ward->GetName()));
	return Guards.Num();
}

AActor* UVLCommand::GuardWardOf(const AVLKing* Unit, float* OutLeash) const
{
	for (const FGuardPost& G : GuardPosts)
	{
		if (G.Unit.Get() == Unit && G.Ward.IsValid())
		{
			if (OutLeash)
			{
				// an archer keeps her reach: she shoots what comes at the ward from as far as she can
				const UVLArcherCombat* Bow = UVLArcherCombat::For(const_cast<AVLKing*>(Unit), false);
				*OutLeash = Bow ? FMath::Max(GuardLeash, Bow->Range) : GuardLeash;
			}
			return G.Ward.Get();
		}
	}
	return nullptr;
}

void UVLCommand::GetGuards(const AActor* Ward, TArray<AVLKing*>& Out) const
{
	Out.Reset();
	for (const FGuardPost& G : GuardPosts)
	{
		if (G.Ward.Get() == Ward && G.Unit.IsValid() && G.Unit->IsAlive())
		{
			Out.Add(G.Unit.Get());
		}
	}
}

int32 UVLCommand::OrderRoam(const TArray<AVLKing*>& InUnits)
{
	TArray<AVLKing*> Spies = Living(InUnits).FilterByPredicate([](const AVLKing* U) { return U->KindId() == EVLUnitKind::Spy; });
	if (Spies.Num() == 0)
	{
		return 0;
	}
	OrderStop(Spies);
	for (AVLKing* U : Spies)
	{
		FRoamer& R = Roamers.AddDefaulted_GetRef();
		R.Unit = U;
		R.Visited.Add(FVector2D(U->GetFeet()));
		PickRoamPoint(R);
		UE_LOG(LogVoxelLab, Log, TEXT("roam: %s sets out"), *U->GetDisplayName());
	}
	return Spies.Num();
}

bool UVLCommand::IsRoaming(const AVLKing* Unit) const
{
	return Roamers.ContainsByPredicate([Unit](const FRoamer& R) { return R.Unit.Get() == Unit; });
}

bool UVLCommand::PickRoamPoint(FRoamer& R)
{
	AVLKing* U = R.Unit.Get();
	UVLGrid* Grid = UVLGrid::Get(this);
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!U || !Grid || !Grid->EnsureBuilt())
	{
		return false;
	}
	// a few spots 20-70 m off; ground it has not been to lately is worth most (there is no fog of war here to
	// explore), then distance; never inside the reach of a foe's tower or castle
	const FVector Me = U->GetFeet();
	const int32 MyNode = Grid->NodeAt(Me) != INDEX_NONE ? Grid->NodeAt(Me) : Grid->NearestNode(Me, 8);
	const int32 Region = MyNode != INDEX_NONE ? Grid->RegionOf(MyNode) : 0;
	FBox2D Bounds = Grid->GetBounds();
	Bounds = Bounds.ExpandBy(-FMath::Min(1500.f, float(Bounds.GetSize().GetMin()) * 0.05f));
	FVector Best = Me;
	float BestScore = -1e9f;
	for (int32 i = 0; i < 12; ++i)
	{
		const float A = FMath::FRandRange(0.f, 2.f * PI), Dist = FMath::FRandRange(2000.f, 7000.f);
		FVector P(FMath::Clamp(Me.X + FMath::Cos(A) * Dist, Bounds.Min.X, Bounds.Max.X), FMath::Clamp(Me.Y + FMath::Sin(A) * Dist, Bounds.Min.Y, Bounds.Max.Y), Me.Z);
		const int32 Node = Grid->NearestNode(P, 20, Region);
		if (Node == INDEX_NONE)
		{
			continue;
		}
		P = Grid->NodePos(Node);
		float Score = FVector::Dist2D(P, Me) * 0.2f + FMath::FRandRange(0.f, 600.f);
		if (!R.Visited.ContainsByPredicate([&P](const FVector2D& V) { return FVector2D::DistSquared(V, FVector2D(P)) < FMath::Square(2500.f); }))
		{
			Score += 4000.f;
		}
		if (Battle)
		{
			for (const FVLBuildingState& B : Battle->GetBuildings())
			{
				if (B.IsAlive() && B.Team >= 0 && B.Team != U->Team && (B.Kind == EVLBuilding::Tower || B.Kind == EVLBuilding::Castle)
					&& Battle->DistanceTo(B.Actor.Get(), P) < VLRules::Level(B.Kind, B.Level).Range + 600.f)
				{
					Score -= 6000.f;
				}
			}
		}
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = P;
		}
	}
	if (BestScore < -1e8f)
	{
		return false;
	}
	{
		TGuardValue<bool> Inner(bInnerOrder, true);
		TGuardValue<bool> Quiet(bQuietMove, true);
		OrderMove({ U }, Best, false, EVLFormation::Line);
	}
	R.LegTime = 0.f;
	R.Visited.Add(FVector2D(Best));
	if (R.Visited.Num() > 24)
	{
		R.Visited.RemoveAt(0);
	}
	return true;
}

void UVLCommand::OnStruck(AVLKing* Victim, AActor* By)
{
	const int32 Index = Roamers.IndexOfByPredicate([Victim](const FRoamer& R) { return R.Unit.Get() == Victim; });
	UVLBattle* Battle = UVLBattle::Get(this);
	if (Index == INDEX_NONE || !Victim || Victim->IsDead() || !Battle || (By && Battle->TeamOf(By) == Victim->Team))
	{
		return;
	}
	// struck while roaming (a tower's arrow too): it drops the roam and runs home to its castle's door
	Roamers.RemoveAt(Index);
	if (AActor* Castle = Battle->GetCastle(Victim->Team))
	{
		FVector Door, Rally, Front;
		Battle->FrontOf(Castle, Door, Rally, Front);
		TGuardValue<bool> Quiet(bQuietMove, true);
		OrderMove({ Victim }, Rally, true, EVLFormation::Line);
	}
	UE_LOG(LogVoxelLab, Log, TEXT("roam: %s struck, runs home"), *Victim->GetDisplayName());
	if (Victim->Team == UVLBattle::Player)
	{
		const FVector At = Victim->GetActorLocation();
		Battle->PushAlert(FString::Printf(TEXT("Your %s was attacked: running home"), *Victim->GetDisplayName()), EVLAlert::Attack, &At);
	}
}

int32 UVLCommand::Dismiss(const TArray<AVLKing*>& InUnits)
{
	int32 N = 0;
	for (AVLKing* U : Living(InUnits))
	{
		if (!U->IsTroop())
		{
			continue;               // King David is not sent away
		}
		ClearStanding({ U });
		OnUnitDied(U);
		UE_LOG(LogVoxelLab, Log, TEXT("dismiss: %s at %s"), *U->GetDisplayName(), *U->GetFeet().ToCompactString());
		U->Die();                   // quietly: no cry, not counted as lost
		++N;
	}
	return N;
}

bool UVLCommand::IsDismissAsked() const
{
	return GetWorld() && GetWorld()->GetRealTimeSeconds() - DismissAskedAt < DismissAskSeconds;
}

void UVLCommand::DismissCommand()
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	const int32 Troops = Units.FilterByPredicate([](const AVLKing* U) { return U->IsTroop(); }).Num();
	UVLBattle* Battle = UVLBattle::Get(this);
	if (Units.Num() == 0 || !Battle)
	{
		return;
	}
	if (Troops == 0)
	{
		Battle->PushAlert(TEXT("King David cannot be dismissed"));
		Battle->Play2D(TEXT("S_UIError"), 0.4f);
		return;
	}
	if (!IsDismissAsked())
	{
		DismissAskedAt = GetWorld()->GetRealTimeSeconds();       // the first press only asks
		Battle->PushAlert(FString::Printf(TEXT("Press K again to dismiss %d %s (no refund)"), Troops, Troops == 1 ? TEXT("troop") : TEXT("troops")));
		return;
	}
	DismissAskedAt = -100.0;
	const int32 N = Dismiss(Units);
	Battle->PushAlert(FString::Printf(TEXT("%d %s dismissed"), N, N == 1 ? TEXT("troop") : TEXT("troops")));
}

bool UVLCommand::MarchTogether(const TArray<AVLKing*>& Units, EVLFormation Shape) const
{
	if (Units.Num() < 2)
	{
		return false;
	}
	if (Shape != EVLFormation::Loose)
	{
		return true;                // a formation holds together on the march: the slowest sets the pace
	}
	const int32 P = PlatoonOf(Units);
	return P != INDEX_NONE ? Platoons[P].bMarchTogether : bLooseMarchTogether;
}

bool UVLCommand::SelectionMarchTogether() const
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	const int32 P = PlatoonOf(Units);
	return SelectionFormation() != EVLFormation::Loose || (P != INDEX_NONE ? Platoons[P].bMarchTogether : bLooseMarchTogether);
}

void UVLCommand::ToggleMarchTogether()
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	if (Units.Num() == 0)
	{
		return;
	}
	const int32 P = PlatoonOf(Units);
	bool& bSetting = P != INDEX_NONE ? Platoons[P].bMarchTogether : bLooseMarchTogether;
	bSetting = !bSetting;
	const bool bNow = MarchTogether(Units, SelectionFormation());
	// a march under way follows the change at once
	float Slowest = TNumericLimits<float>::Max();
	for (const AVLKing* U : Units)
	{
		Slowest = FMath::Min(Slowest, U->WalkSpeed);
	}
	for (AVLKing* U : Units)
	{
		U->PaceCap = (bNow && U->HasOrder() && Slowest < U->WalkSpeed - 1.f) ? Slowest : 0.f;
	}
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		Battle->PushAlert(SelectionFormation() != EVLFormation::Loose ? FString(TEXT("In formation they always keep the slowest one's pace (march freely: Loose, F)"))
			: (bSetting ? FString(TEXT("March together: the slowest sets the pace")) : FString(TEXT("March freely: each at its own speed"))));
	}
	UE_LOG(LogVoxelLab, Log, TEXT("march together: %s"), bSetting ? TEXT("on") : TEXT("off"));
}

void UVLCommand::Arm(EVLArm Mode)
{
	Armed = EVLArm::None;
	ArmedAt = -1.0;
	TArray<AVLKing*> Units;
	GetSelection(Units);
	bool bOk = false;
	switch (Mode)
	{
	case EVLArm::AttackGround: bOk = Units.ContainsByPredicate([](const AVLKing* U) { return UVLArcherCombat::CanFight(U); }); break;
	case EVLArm::AttackMove: bOk = Units.ContainsByPredicate([](const AVLKing* U) { return CanAttack(U); }); break;
	case EVLArm::Patrol: bOk = Units.Num() > 0; break;
	case EVLArm::Guard: bOk = SelectionCanGuard(); break;
	default: break;
	}
	if (bOk)
	{
		Armed = Mode;
		ArmedAt = GetWorld()->GetRealTimeSeconds();
	}
}

EVLArm UVLCommand::GetArmed() const
{
	if (Armed == EVLArm::None || !GetWorld())
	{
		return EVLArm::None;
	}
	const float Lapse = Armed == EVLArm::AttackGround ? AttackGroundSeconds : ArmSeconds;
	return GetWorld()->GetRealTimeSeconds() - ArmedAt < Lapse ? Armed : EVLArm::None;
}

void UVLCommand::CycleAttackArm()
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	const bool bArchers = Units.ContainsByPredicate([](const AVLKing* U) { return UVLArcherCombat::CanFight(U); });
	const bool bOthers = Units.ContainsByPredicate([](const AVLKing* U) { return CanAttack(U) && !UVLArcherCombat::CanFight(U); });
	const EVLArm Now = GetArmed();
	if (Now == EVLArm::AttackMove && bArchers)
	{
		Arm(EVLArm::AttackGround);
	}
	else if (Now == EVLArm::AttackGround)
	{
		Arm(EVLArm::AttackMove);
	}
	else
	{
		Arm(bArchers && !bOthers ? EVLArm::AttackGround : EVLArm::AttackMove);
	}
}

bool UVLCommand::SelectionCanGuard() const
{
	TArray<AVLKing*> Units;
	GetSelection(Units);
	return Units.ContainsByPredicate([](const AVLKing* U) { return U->KindId() != EVLUnitKind::Builder; });
}

bool UVLCommand::GetRoute(const AVLKing* Unit, TArray<FVector>& OutPoints, bool& bOutLoop, int32& OutNext, int32* OutId) const
{
	for (const FRoute& R : Routes)
	{
		if (R.Members.Contains(const_cast<AVLKing*>(Unit)))
		{
			OutPoints = R.Points;
			bOutLoop = R.bLoop;
			OutNext = R.Next;
			if (OutId)
			{
				*OutId = R.Id;
			}
			return true;
		}
	}
	return false;
}

FString UVLCommand::DescribeOrders(const TArray<AVLKing*>& Units) const
{
	if (Units.Num() == 0)
	{
		return FString();
	}
	const AVLKing* U = Units[0];
	TArray<FVector> Points;
	bool bLoop = false;
	int32 Next = 0;
	if (GetRoute(U, Points, bLoop, Next))
	{
		return bLoop ? FString::Printf(TEXT("Patrolling (%d points)"), Points.Num()) : FString(TEXT("Attack-move"));
	}
	if (const AActor* Ward = GuardWardOf(U))
	{
		const UVLBattle* Battle = UVLBattle::Get(this);
		const FVLBuildingState* B = Battle ? Battle->FindBuilding(Ward) : nullptr;
		return FString::Printf(TEXT("Guarding %s"), B ? *(TEXT("the ") + B->Name) : (Cast<AVLKing>(Ward) ? *Cast<AVLKing>(Ward)->GetDisplayName() : TEXT("")));
	}
	if (IsRoaming(U))
	{
		return TEXT("Roaming");
	}
	if (U->bHoldOrder)
	{
		return TEXT("Holding its ground");
	}
	return FString();
}

void UVLCommand::TickOrders(float Dt)
{
	// ---- patrols and attack-moves: the next leg once nobody is walking or fighting; a leg cut short by a fight is
	// walked again (the main game's units kept their destination through a fight)
	for (int32 i = Routes.Num() - 1; i >= 0; --i)
	{
		FRoute& R = Routes[i];
		R.Members.RemoveAll([](const TWeakObjectPtr<AVLKing>& M) { return !M.IsValid() || M->IsDead() || PlayedByHand(M.Get()); });
		if (R.Members.Num() == 0 || R.Points.Num() == 0)
		{
			Routes.RemoveAt(i);
			continue;
		}
		R.Settle -= Dt;
		if (R.Settle > 0.f)
		{
			continue;
		}
		TArray<AVLKing*> Live;
		bool bBusy = false;
		for (const TWeakObjectPtr<AVLKing>& M : R.Members)
		{
			Live.Add(M.Get());
			bBusy |= M->IsOnOrder() || IsFightingNow(M.Get());
		}
		if (bBusy)
		{
			continue;
		}
		const float Reach = 280.f + 90.f * FMath::Sqrt(float(Live.Num()));
		const bool bThere = FVector::Dist2D(Centroid(Live), R.Points[R.Next]) < Reach;
		if (!bThere && R.Tries < 3)
		{
			++R.Tries;
			R.Settle = 1.f;
			IssueLeg(R);
			continue;
		}
		if (!R.bLoop && R.Next >= R.Points.Num() - 1)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("attack-move: %d unit(s) at the end of their way"), Live.Num());
			for (AVLKing* U : Live)
			{
				U->bAttackMove = false;
			}
			Routes.RemoveAt(i);
			continue;
		}
		R.Next = (R.Next + 1) % R.Points.Num();
		R.Tries = 0;
		R.Settle = R.bLoop ? 1.5f : 0.6f;
		IssueLeg(R);
	}

	OrdersClock -= Dt;
	if (OrdersClock > 0.f)
	{
		return;
	}
	const float Step = 0.25f - OrdersClock;
	OrdersClock = 0.25f;
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;

	// ---- guards: at their posts (which move with a unit they guard); a chase that takes one too far from its ward
	// is let go (one that struck the ward or the guard is run down further)
	const UVLBattle* Battle = UVLBattle::Get(this);
	for (int32 i = GuardPosts.Num() - 1; i >= 0; --i)
	{
		FGuardPost& G = GuardPosts[i];
		AVLKing* U = G.Unit.Get();
		FVector Ward;
		if (!U || U->IsDead() || PlayedByHand(U) || !WardPos(G.Ward.Get(), Ward))
		{
			if (U && U->IsAlive() && !G.Ward.IsValid())
			{
				U->Post = U->GetFeet();
			}
			GuardPosts.RemoveAt(i);     // the ward fell: the guard stands where it is
			continue;
		}
		float Leash = GuardLeash;
		GuardWardOf(U, &Leash);
		if (AActor* Foe = FightTarget(U))
		{
			G.bSent = false;
			// (one that struck the guard or its ward lately is run down further)
			bool bStruck = Now - U->LastStruckTime < 4.0;
			if (const AVLKing* WardUnit = Cast<AVLKing>(G.Ward.Get()))
			{
				bStruck |= Now - WardUnit->LastStruckTime < 4.0;
			}
			else if (const FVLBuildingState* WB = Battle ? Battle->FindBuilding(G.Ward.Get()) : nullptr)
			{
				bStruck |= Now - WB->LastHit < 4.0;
			}
			const float Far = Leash * (bStruck ? 1.8f : 1.f);
			const float FoeFromWard = Battle ? Battle->DistanceTo(Foe, Ward) : FVector::Dist2D(Foe->GetActorLocation(), Ward);
			if (FoeFromWard > Far || FVector::Dist2D(U->GetFeet(), Ward) > Far * 1.3f)
			{
				StopAttack(U);
				U->bAutoAttack = false;
				UE_LOG(LogVoxelLab, Log, TEXT("guard: %s lets %s go (%.0f cm from its ward)"), *U->GetDisplayName(), *Foe->GetName(), FoeFromWard);
			}
			continue;
		}
		if (IsFightingNow(U))
		{
			continue;                   // (at the ground, or a dummy)
		}
		FVector2D Post;
		GuardPostWorld(G, Post);
		const bool bWardMoved = FVector2D::Distance(FVector2D(Ward), G.SentFor) > 180.f;
		if ((!G.bSent && !U->HasOrder() && FVector2D::Distance(FVector2D(U->GetFeet()), Post) > 120.f) || (bWardMoved && Cast<AVLKing>(G.Ward.Get())))
		{
			TGuardValue<bool> Inner(bInnerOrder, true);
			TGuardValue<bool> Quiet(bQuietMove, true);
			OrderMove({ U }, FVector(Post.X, Post.Y, Ward.Z), FVector2D::Distance(FVector2D(U->GetFeet()), Post) > 900.f, EVLFormation::Line);
			G.bSent = true;
			G.SentFor = FVector2D(Ward);
		}
		U->Post = FVector(Post.X, Post.Y, Ward.Z);  // (a defensive guard comes back here)
	}

	// ---- roamers: on to a new spot when one is reached (or after 40 s on the way to it)
	for (int32 i = Roamers.Num() - 1; i >= 0; --i)
	{
		FRoamer& R = Roamers[i];
		AVLKing* U = R.Unit.Get();
		if (!U || U->IsDead() || PlayedByHand(U))
		{
			Roamers.RemoveAt(i);
			continue;
		}
		R.LegTime += Step;
		if (!U->IsOnOrder() || R.LegTime > 40.f)
		{
			PickRoamPoint(R);
		}
	}
}

// ------------------------------------------------------------------------------------------------ console (tests)

namespace
{
	/** selection | all | troops | king | archers | swordsmen | spies | builders | enemy | a name (Swordsman_2). */
	void WhoOf(UWorld* World, const FString& Who, TArray<AVLKing*>& Out)
	{
		Out.Reset();
		if (Who.Equals(TEXT("selection"), ESearchCase::IgnoreCase) || Who.Equals(TEXT("sel"), ESearchCase::IgnoreCase))
		{
			if (UVLCommand* Command = UVLCommand::Get(World))
			{
				Command->GetSelection(Out);
			}
			return;
		}
		const FString Name = Who.Replace(TEXT("_"), TEXT(" "));
		const bool bEnemy = Who.Equals(TEXT("enemy"), ESearchCase::IgnoreCase);
		for (TActorIterator<AVLKing> It(World); It; ++It)
		{
			if (It->IsDead())
			{
				continue;
			}
			if (It->GetDisplayName().Equals(Name, ESearchCase::IgnoreCase) || (bEnemy && It->Team != UVLBattle::Player))
			{
				Out.Add(*It);
				continue;
			}
			if (It->Team != UVLBattle::Player)
			{
				continue;
			}
			const FString& K = It->GetKind();
			if (Who.Equals(TEXT("all"), ESearchCase::IgnoreCase) || (Who.Equals(TEXT("troops"), ESearchCase::IgnoreCase) && It->IsTroop())
				|| (Who.Equals(TEXT("king"), ESearchCase::IgnoreCase) && !It->IsTroop()) || (Who.Equals(TEXT("archers"), ESearchCase::IgnoreCase) && K == TEXT("Archer"))
				|| (Who.Equals(TEXT("swordsmen"), ESearchCase::IgnoreCase) && K == TEXT("Swordsman")) || (Who.Equals(TEXT("spies"), ESearchCase::IgnoreCase) && K == TEXT("Spy"))
				|| (Who.Equals(TEXT("builders"), ESearchCase::IgnoreCase) && K == TEXT("Builder")))
			{
				Out.Add(*It);
			}
		}
		Out.Sort([](const AVLKing& A, const AVLKing& B) { return A.GetDisplayName() < B.GetDisplayName(); });
	}

	FVector GroundAt(UWorld* World, float X, float Y)
	{
		FVector P(X, Y, 0.f);
		FHitResult Hit;
		FCollisionQueryParams Params(TEXT("OrderGround"), false);
		for (TActorIterator<APawn> It(World); It; ++It)
		{
			Params.AddIgnoredActor(*It);
		}
		if (World->LineTraceSingleByChannel(Hit, P + FVector(0.f, 0.f, 6000.f), P - FVector(0.f, 0.f, 3000.f), ECC_Visibility, Params))
		{
			P = Hit.ImpactPoint;
		}
		return P;
	}

	void Simple(const TArray<FString>& Args, UWorld* World, TFunctionRef<void(UVLCommand&, const TArray<AVLKing*>&)> Do)
	{
		UVLCommand* Command = UVLCommand::Get(World);
		if (!Command)
		{
			return;
		}
		TArray<AVLKing*> Units;
		WhoOf(World, Args.Num() > 0 ? Args[0] : TEXT("selection"), Units);
		Do(*Command, Units);
	}

	FAutoConsoleCommandWithWorldAndArgs CmdStop(TEXT("vl.Stop"), TEXT("vl.Stop [who]: drop every order (default: the selection)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			Simple(Args, World, [](UVLCommand& C, const TArray<AVLKing*>& U) { C.OrderStop(U); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdHold(TEXT("vl.Hold"), TEXT("vl.Hold [who]: hold ground until the next order"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			Simple(Args, World, [](UVLCommand& C, const TArray<AVLKing*>& U) { C.OrderHold(U); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRoam(TEXT("vl.Roam"), TEXT("vl.Roam [who]: the Spies among them roam"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			Simple(Args, World, [](UVLCommand& C, const TArray<AVLKing*>& U) { UE_LOG(LogVoxelLab, Log, TEXT("roam: %d"), C.OrderRoam(U)); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdDismiss(TEXT("vl.Dismiss"), TEXT("vl.Dismiss [who]: remove those troops for good"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			Simple(Args, World, [](UVLCommand& C, const TArray<AVLKing*>& U) { UE_LOG(LogVoxelLab, Log, TEXT("dismissed %d"), C.Dismiss(U)); });
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdMarch(TEXT("vl.March"), TEXT("vl.March: march together on / off for the selection (as M)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (UVLCommand* C = UVLCommand::Get(World))
			{
				C->ToggleMarchTogether();
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPatrol(TEXT("vl.Patrol"), TEXT("vl.Patrol <who> X Y [X Y ...] [run]: patrol from where they stand through the points and back"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* C = UVLCommand::Get(World);
			if (!C || Args.Num() < 3)
			{
				return;
			}
			TArray<AVLKing*> Units;
			WhoOf(World, Args[0], Units);
			TArray<FVector> Points;
			for (int32 i = 1; i + 1 < Args.Num() && Args[i].IsNumeric() && Args[i + 1].IsNumeric(); i += 2)
			{
				Points.Add(GroundAt(World, FCString::Atof(*Args[i]), FCString::Atof(*Args[i + 1])));
			}
			C->OrderPatrol(Units, Points, Args.Last().Equals(TEXT("run"), ESearchCase::IgnoreCase), Units.Num() > 1 ? C->SelectionFormation() : EVLFormation::Line);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAttackMove(TEXT("vl.AttackMove"), TEXT("vl.AttackMove <who> X Y [queue] [run]: march there fighting what they meet"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* C = UVLCommand::Get(World);
			if (!C || Args.Num() < 3)
			{
				return;
			}
			TArray<AVLKing*> Units;
			WhoOf(World, Args[0], Units);
			const bool bQueue = Args.ContainsByPredicate([](const FString& A) { return A.Equals(TEXT("queue"), ESearchCase::IgnoreCase); });
			const bool bRun = Args.ContainsByPredicate([](const FString& A) { return A.Equals(TEXT("run"), ESearchCase::IgnoreCase); });
			C->OrderAttackMove(Units, GroundAt(World, FCString::Atof(*Args[1]), FCString::Atof(*Args[2])), bRun, Units.Num() > 1 ? C->SelectionFormation() : EVLFormation::Line, bQueue);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdGuard(TEXT("vl.Guard"), TEXT("vl.Guard <who> <building name | unit name | king>: guard it"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* C = UVLCommand::Get(World);
			if (!C || Args.Num() < 2)
			{
				return;
			}
			TArray<AVLKing*> Units;
			WhoOf(World, Args[0], Units);
			FString Name = Args[1];
			for (int32 i = 2; i < Args.Num(); ++i)
			{
				Name += TEXT(" ") + Args[i];
			}
			Name.ReplaceInline(TEXT("_"), TEXT(" "));
			AActor* Ward = nullptr;
			const FName Tag(*(TEXT("Name:") + Name));
			for (TActorIterator<AActor> It(World); It && !Ward; ++It)
			{
				if (It->ActorHasTag(Tag))
				{
					Ward = *It;
				}
			}
			if (!Ward)
			{
				TArray<AVLKing*> Who;
				WhoOf(World, Name, Who);
				Ward = Who.Num() > 0 ? Who[0] : nullptr;
			}
			UE_LOG(LogVoxelLab, Log, TEXT("guard: %d of %d unit(s) guard %s"), Ward ? C->OrderGuard(Units, Ward) : 0, Units.Num(), *GetNameSafe(Ward));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdOrders(TEXT("vl.Orders"), TEXT("log every unit's standing order (patrol, attack-move, guard, hold, roam) and pace"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			UVLCommand* C = UVLCommand::Get(World);
			if (!C)
			{
				return;
			}
			for (TActorIterator<AVLKing> It(World); It; ++It)
			{
				if (It->IsDead())
				{
					continue;
				}
				TArray<FVector> Points;
				bool bLoop = false;
				int32 Next = 0;
				FString What = C->DescribeOrders({ *It });
				if (C->GetRoute(*It, Points, bLoop, Next))
				{
					What += FString::Printf(TEXT(" -> point %d %s"), Next, *Points[Next].ToCompactString());
				}
				const FVector F = It->GetFeet();
				UE_LOG(LogVoxelLab, Log, TEXT("orders %-14s team %d at %6.0f %6.0f  %s%s  speed %.0f (walk %.0f run %.0f pace %.0f) stance %s%s"), *It->GetDisplayName(), It->Team, F.X, F.Y,
					What.IsEmpty() ? TEXT("-") : *What, It->HasOrder() ? TEXT(" [walking]") : TEXT(""), It->GetVelocity().Size2D(), It->WalkSpeed, It->RunSpeed, It->PaceCap,
					UVLCommand::StanceName(It->Stance), It->bAttackMove ? TEXT(" attack-move") : TEXT(""));
			}
		}));
}
