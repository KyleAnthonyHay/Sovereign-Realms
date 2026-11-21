#include "VLCommand.h"
#include "VoxelLab.h"
#include "VLGrid.h"
#include "VLKing.h"
#include "VLSwordsmanCombat.h"
#include "VLArcherCombat.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"

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
		if (U.IsValid())
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
		N += U.IsValid() ? 1 : 0;
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
		if (U)
		{
			Selection.AddUnique(U);
		}
	}
}

void UVLCommand::Toggle(AVLKing* Unit)
{
	if (!Unit)
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
		if (U)
		{
			Units.AddUnique(U);
		}
	}
	if (Units.Num() == 0)
	{
		return;
	}
	for (AVLKing* U : Units)
	{
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
		AddMarker(Ground);
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
	AddMarker(Dest);
}

// ------------------------------------------------------------------------------------------------ attacks

void UVLCommand::GetDummies(TArray<AActor*>& Out) const
{
	Out.Reset();
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(TEXT("Dummy")))
		{
			Out.Add(*It);
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

int32 UVLCommand::OrderAttack(const TArray<AVLKing*>& Units, AActor* Target, bool bRun)
{
	if (!Target)
	{
		return 0;
	}
	int32 Ordered = 0;
	Ordered += UVLSwordsmanCombat::OrderAttack(Units, Target, bRun);        // the swordsmen among them
	Ordered += UVLArcherCombat::OrderAttack(Units, Target, bRun);           // the archers (those on the tower shoot from it)
	if (Ordered > 0)
	{
		AddMarker(Target->GetActorLocation());
	}
	return Ordered;
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
}

void UVLCommand::ArmAttackGround(bool bArm)
{
	AttackGroundArmedAt = -1.0;
	if (bArm)
	{
		TArray<AVLKing*> Units;
		GetSelection(Units);
		if (Units.ContainsByPredicate([](const AVLKing* U) { return UVLArcherCombat::CanFight(U); }))
		{
			AttackGroundArmedAt = GetWorld()->GetRealTimeSeconds();
		}
	}
}

bool UVLCommand::IsAttackGroundArmed() const
{
	return AttackGroundArmedAt >= 0.0 && GetWorld() && GetWorld()->GetRealTimeSeconds() - AttackGroundArmedAt < AttackGroundSeconds;
}

int32 UVLCommand::OrderAttackGround(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun)
{
	for (AVLKing* U : Units)
	{
		if (UVLArcherCombat::CanFight(U))
		{
			StopAttack(U);          // whatever they were shooting at
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
		if (!U)
		{
			continue;
		}
		for (FPlatoon& P : Platoons)            // a unit belongs to one platoon at most
		{
			P.Members.Remove(U);
		}
		Platoons[Index].Members.Add(U);
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
		if (U.IsValid())
		{
			Out.Add(U.Get());
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
		if (!U || U->GarrisonIn.Get() == Tower)
		{
			continue;
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
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		Down += (*It != Unit && !It->GarrisonIn.IsValid() && FVector::Dist2D(It->GetFeet(), Door) < 420.f) ? 1 : 0;
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
