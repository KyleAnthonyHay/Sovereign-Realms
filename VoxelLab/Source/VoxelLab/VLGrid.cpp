#include "VLGrid.h"
#include "VoxelLab.h"
#include "Components/StaticMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"

namespace
{
	const FIntPoint Neighbours[8] = { {1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}, {1, -1}, {-1, 1}, {-1, -1} };
	constexpr float Diag = 1.41421356f;
	constexpr float UnitHeight = 170.f;     // what must be clear over a floor
	constexpr float UnitRadius = 38.f;      // (the capsule is 40: a hair under, so a gap it just fits is not lost to rounding)
	constexpr int32 MaxLayers = 5;

	int32 DirIndex(int32 Dx, int32 Dy)
	{
		for (int32 n = 0; n < 8; ++n)
		{
			if (Neighbours[n].X == Dx && Neighbours[n].Y == Dy)
			{
				return n;
			}
		}
		return -1;
	}

	struct FOpen
	{
		float F;
		int32 I;
	};
	struct FOpenLess { bool operator()(const FOpen& A, const FOpen& B) const { return A.F < B.F; } };
}

UVLGrid* UVLGrid::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLGrid>() : nullptr;
}

bool UVLGrid::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

bool UVLGrid::EnsureBuilt()
{
	if (!bTried)
	{
		Build();
	}
	return IsBuilt();
}

void UVLGrid::Build()
{
	bTried = true;
	Nodes.Reset();
	DimX = DimY = 0;
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	Cell = FMath::Max(CellSize, 10.f);

	// the ground (where the search for floors stops) and the water
	FBox Bounds(ForceInit);
	TSet<const UPrimitiveComponent*> Ground;
	TArray<UStaticMeshComponent*> Water;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(VLGrid), true);
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->IsA<APawn>())
		{
			Params.AddIgnoredActor(*It);
			continue;
		}
		const AStaticMeshActor* SMA = Cast<AStaticMeshActor>(*It);
		UStaticMeshComponent* Comp = SMA ? SMA->GetStaticMeshComponent() : nullptr;
		const UStaticMesh* Mesh = Comp ? Comp->GetStaticMesh() : nullptr;
		if (!Mesh)
		{
			continue;
		}
		if (It->ActorHasTag(TEXT("Water")))
		{
			Water.Add(Comp);
			Params.AddIgnoredActor(*It);
			continue;
		}
		const FString Name = Mesh->GetName();
		if (It->ActorHasTag(TEXT("Ground")) || Name.StartsWith(TEXT("SM_Terrain")) || Name.StartsWith(TEXT("SM_Flat_")))
		{
			Ground.Add(Comp);
			Bounds += Comp->Bounds.GetBox();
		}
	}
	if (!Bounds.IsValid)
	{
		UE_LOG(LogVoxelLab, Warning, TEXT("GRID: no ground in this level (no actor tagged Ground, no SM_Terrain / SM_Flat mesh)"));
		return;
	}
	// cell centres on the middles of the quarter-block columns of the voxel ground, never on their seams
	Origin = FVector2D(FMath::FloorToFloat(Bounds.Min.X / Cell) * Cell + 12.5f, FMath::FloorToFloat(Bounds.Min.Y / Cell) * Cell + 12.5f);
	DimX = FMath::CeilToInt((Bounds.Max.X - Origin.X) / Cell);
	DimY = FMath::CeilToInt((Bounds.Max.Y - Origin.Y) / Cell);
	const int32 N = DimX * DimY;
	First.Init(0, N);
	Count.Init(0, N);
	WaterZ.Init(-BIG_NUMBER, N);
	const float Top = Bounds.Max.Z + 4000.f;
	const float Bottom = Bounds.Min.Z - 20.f;

	// water: each sheet is asked where its surface lies over the cells under its bounds (it has collision for these
	// queries only: the level builder turned every channel off)
	FCollisionQueryParams WaterParams(SCENE_QUERY_STAT(VLGridWater), true);
	for (UStaticMeshComponent* Sheet : Water)
	{
		const FBox Box = Sheet->Bounds.GetBox();
		const FIntPoint Lo = ToCellClamped(FVector2D(Box.Min.X, Box.Min.Y)), Hi = ToCellClamped(FVector2D(Box.Max.X, Box.Max.Y));
		for (int32 y = Lo.Y; y <= Hi.Y; ++y)
		{
			for (int32 x = Lo.X; x <= Hi.X; ++x)
			{
				const FVector2D P = CellCentre(FIntPoint(x, y));
				FHitResult Hit;
				if (Sheet->LineTraceComponent(Hit, FVector(P.X, P.Y, Box.Max.Z + 50.f), FVector(P.X, P.Y, Box.Min.Z - 50.f), WaterParams))
				{
					WaterZ[y * DimX + x] = FMath::Max(WaterZ[y * DimX + x], float(Hit.ImpactPoint.Z));
				}
			}
		}
	}

	// floors
	const float Lift = StepHeight + 4.f;
	const float HalfHeight = (UnitHeight - Lift) * 0.5f;
	const FCollisionShape Body = FCollisionShape::MakeCapsule(UnitRadius, FMath::Max(HalfHeight, UnitRadius));
	int32 Wet = 0, Tight = 0, Inside = 0;
	Nodes.Reserve(N);
	for (int32 y = 0; y < DimY; ++y)
	{
		for (int32 x = 0; x < DimX; ++x)
		{
			const int32 C = y * DimX + x;
			const FVector2D P = CellCentre(FIntPoint(x, y));
			First[C] = Nodes.Num();
			float Z = Top, PrevZ = Top;
			bool bSky = true;
			for (int32 Layer = 0; Layer < MaxLayers; ++Layer)
			{
				FHitResult Hit;
				if (!World->LineTraceSingleByChannel(Hit, FVector(P.X, P.Y, Z), FVector(P.X, P.Y, Bottom), ECC_Visibility, Params) || Hit.bStartPenetrating)
				{
					break;
				}
				const float FZ = Hit.ImpactPoint.Z;
				if (Hit.ImpactNormal.Z > 0.7f)
				{
					// air over it, with headroom? Under the open sky, yes. Under something: only if looking up shows
					// that thing's underside high enough (seeing nothing means this floor lies inside a solid)
					bool bRoom = bSky;
					if (!bSky)
					{
						FHitResult Up;
						bRoom = World->LineTraceSingleByChannel(Up, FVector(P.X, P.Y, FZ + Lift), FVector(P.X, P.Y, PrevZ + 2.f), ECC_Visibility, Params)
							&& !Up.bStartPenetrating && Up.ImpactPoint.Z - FZ >= UnitHeight;
						Inside += bRoom ? 0 : 1;
					}
					if (bRoom && WaterZ[C] > FZ + 15.f)
					{
						bRoom = false;
						++Wet;
					}
					if (bRoom && World->OverlapBlockingTestByChannel(FVector(P.X, P.Y, FZ + Lift + Body.GetCapsuleHalfHeight()), FQuat::Identity, ECC_Pawn, Body, Params))
					{
						bRoom = false;
						++Tight;
					}
					if (bRoom)
					{
						FNode& Node = Nodes.AddDefaulted_GetRef();
						Node.Z = FZ;
						Node.Cell = C;
					}
				}
				if (Ground.Contains(Hit.GetComponent()))
				{
					break;
				}
				bSky = false;
				PrevZ = FZ;
				Z = FZ - 15.f;
			}
			Count[C] = uint8(Nodes.Num() - First[C]);
		}
	}

	// joins: a step of at most StepHeight to the neighbouring cell's nearest floor; diagonals only between joined sides
	for (int32 I = 0; I < Nodes.Num(); ++I)
	{
		FNode& Node = Nodes[I];
		const FIntPoint C = CellOf(I);
		for (int32 n = 0; n < 4; ++n)
		{
			const FIntPoint NC = C + Neighbours[n];
			if (!InGrid(NC))
			{
				continue;
			}
			const int32 NI = CellIdx(NC);
			float Best = StepHeight;
			for (int32 k = 0; k < Count[NI]; ++k)
			{
				const float D = FMath::Abs(Nodes[First[NI] + k].Z - Node.Z);
				if (D <= Best)
				{
					Best = D;
					Node.Nb[n] = First[NI] + k;
				}
			}
		}
	}
	for (int32 I = 0; I < Nodes.Num(); ++I)
	{
		FNode& Node = Nodes[I];
		for (int32 n = 4; n < 8; ++n)
		{
			const int32 A = Node.Nb[DirIndex(Neighbours[n].X, 0)], B = Node.Nb[DirIndex(0, Neighbours[n].Y)];
			if (A < 0 || B < 0)
			{
				continue;
			}
			// the same corner cell reached both ways round, within a step of here
			const int32 ViaA = Nodes[A].Nb[DirIndex(0, Neighbours[n].Y)], ViaB = Nodes[B].Nb[DirIndex(Neighbours[n].X, 0)];
			if (ViaA >= 0 && ViaA == ViaB && FMath::Abs(Nodes[ViaA].Z - Node.Z) <= StepHeight)
			{
				Node.Nb[n] = ViaA;
			}
		}
		for (int32 n = 0; n < 8; ++n)
		{
			Node.bNearWall |= Node.Nb[n] < 0;
		}
	}

	// regions of connected ground
	int32 Regions = 0, MainSize = 0;
	Main = 0;
	TArray<int32> Stack;
	for (int32 Seed = 0; Seed < Nodes.Num(); ++Seed)
	{
		if (Nodes[Seed].Region != 0)
		{
			continue;
		}
		Nodes[Seed].Region = ++Regions;
		int32 Size = 0;
		Stack.Push(Seed);
		while (Stack.Num() > 0)
		{
			const int32 I = Stack.Pop(EAllowShrinking::No);
			++Size;
			for (int32 n = 0; n < 8; ++n)
			{
				const int32 J = Nodes[I].Nb[n];
				if (J >= 0 && Nodes[J].Region == 0)
				{
					Nodes[J].Region = Regions;
					Stack.Push(J);
				}
			}
		}
		if (Size > MainSize)
		{
			MainSize = Size;
			Main = Regions;
		}
	}
	Cost.Init(0.f, Nodes.Num());
	Next.Init(INDEX_NONE, Nodes.Num());
	Seen.Init(0, Nodes.Num());
	RouteMark.Init(0, Nodes.Num());
	Stamp = RouteStamp = 0;
	UE_LOG(LogVoxelLab, Log, TEXT("GRID built: %dx%d cells of %.0f cm, %d nodes in %d regions (the main one %d), rejected: %d under water (%d sheets), %d too tight, %d inside solids; in %.0f ms"),
		DimX, DimY, Cell, Nodes.Num(), Regions, MainSize, Wet, Water.Num(), Tight, Inside, (FPlatformTime::Seconds() - T0) * 1000.0);
}

bool UVLGrid::ToCell(const FVector2D& P, FIntPoint& Out) const
{
	if (DimX <= 0)
	{
		return false;
	}
	Out = FIntPoint(FMath::FloorToInt((P.X - Origin.X) / Cell), FMath::FloorToInt((P.Y - Origin.Y) / Cell));
	return InGrid(Out);
}

FIntPoint UVLGrid::ToCellClamped(const FVector2D& P) const
{
	return FIntPoint(FMath::Clamp(FMath::FloorToInt((P.X - Origin.X) / Cell), 0, FMath::Max(DimX - 1, 0)),
		FMath::Clamp(FMath::FloorToInt((P.Y - Origin.Y) / Cell), 0, FMath::Max(DimY - 1, 0)));
}

FVector UVLGrid::NodePos(int32 Node) const
{
	if (!Nodes.IsValidIndex(Node))
	{
		return FVector::ZeroVector;
	}
	const FVector2D P = CellCentre(CellOf(Node));
	return FVector(P.X, P.Y, Nodes[Node].Z);
}

int32 UVLGrid::NodeAt(const FVector& Feet, float MaxDz) const
{
	FIntPoint C;
	if (!ToCell(FVector2D(Feet), C))
	{
		return INDEX_NONE;
	}
	const int32 CI = CellIdx(C);
	int32 Best = INDEX_NONE;
	float BestD = MaxDz;
	for (int32 k = 0; k < Count[CI]; ++k)
	{
		const float D = FMath::Abs(Nodes[First[CI] + k].Z - Feet.Z);
		if (D <= BestD)
		{
			BestD = D;
			Best = First[CI] + k;
		}
	}
	return Best;
}

int32 UVLGrid::NearestNode(const FVector& Point, int32 MaxRing, int32 Region) const
{
	if (DimX <= 0)
	{
		return INDEX_NONE;
	}
	const FVector2D P(Point);
	const FIntPoint C = ToCellClamped(P);
	// nearest over the plan, ring by ring; of two floors in one cell the nearer in height; a node hard against a wall
	// loses to an open one a little farther off (so the search looks one ring past the first it finds)
	const float WallCost = FMath::Square(Cell * 1.2f);
	float BestScore = TNumericLimits<float>::Max();
	int32 Best = INDEX_NONE;
	int32 Last = MaxRing;
	for (int32 R = 0; R <= Last; ++R)
	{
		for (int32 dy = -R; dy <= R; ++dy)
		{
			for (int32 dx = -R; dx <= R; ++dx)
			{
				if (FMath::Max(FMath::Abs(dx), FMath::Abs(dy)) != R)
				{
					continue;
				}
				const FIntPoint NC(C.X + dx, C.Y + dy);
				if (!InGrid(NC))
				{
					continue;
				}
				const int32 CI = CellIdx(NC);
				for (int32 k = 0; k < Count[CI]; ++k)
				{
					const FNode& Node = Nodes[First[CI] + k];
					if (Region != 0 && Node.Region != Region)
					{
						continue;
					}
					const float Score = FVector2D::DistSquared(CellCentre(NC), P) + (R > 0 && Node.bNearWall ? WallCost : 0.f)
						+ FMath::Square(FMath::Min(FMath::Abs(Node.Z - float(Point.Z)), 400.f) * 0.25f);
					if (Score < BestScore)
					{
						BestScore = Score;
						Best = First[CI] + k;
					}
				}
			}
		}
		if (Best != INDEX_NONE && Last == MaxRing)
		{
			Last = FMath::Min(MaxRing, R + 1);
		}
	}
	return Best;
}

bool UVLGrid::Submerged(const FVector& Feet) const
{
	FIntPoint C;
	return ToCell(FVector2D(Feet), C) && WaterZ[CellIdx(C)] > Feet.Z + 25.f && NodeAt(Feet, 60.f) == INDEX_NONE;
}

bool UVLGrid::WalkLine(int32 FromNode, const FVector2D& A, const FVector2D& B, int32 ToNode, ELineRule Rule) const
{
	if (!Nodes.IsValidIndex(FromNode) || !Nodes.IsValidIndex(ToNode))
	{
		return false;
	}
	FIntPoint C = CellOf(FromNode);
	const FIntPoint Start = C, End = CellOf(ToNode);
	int32 Cur = FromNode;
	auto Open = [&](int32 I)
	{
		if (!Nodes[I].bNearWall || Rule == ELineRule::Any)
		{
			return true;
		}
		if (Rule == ELineRule::Route)
		{
			return RouteMark[I] == RouteStamp;
		}
		const FIntPoint P = CellOf(I);
		return FMath::Max(FMath::Abs(P.X - Start.X), FMath::Abs(P.Y - Start.Y)) <= 1 || FMath::Max(FMath::Abs(P.X - End.X), FMath::Abs(P.Y - End.Y)) <= 1;
	};
	// every cell the segment passes through, in order, stepping from floor to joined floor
	const FVector2D D = B - A;
	const int32 Sx = D.X >= 0.f ? 1 : -1, Sy = D.Y >= 0.f ? 1 : -1;
	const float Far = TNumericLimits<float>::Max();
	const float TDx = FMath::Abs(D.X) > KINDA_SMALL_NUMBER ? Cell / FMath::Abs(float(D.X)) : Far;
	const float TDy = FMath::Abs(D.Y) > KINDA_SMALL_NUMBER ? Cell / FMath::Abs(float(D.Y)) : Far;
	float TX = TDx < Far ? float(((Origin.X + (C.X + (Sx > 0 ? 1 : 0)) * Cell) - A.X) / D.X) : Far;
	float TY = TDy < Far ? float(((Origin.Y + (C.Y + (Sy > 0 ? 1 : 0)) * Cell) - A.Y) / D.Y) : Far;
	for (int32 Guard = (DimX + DimY) * 2; C != End && Guard > 0; --Guard)
	{
		if (FMath::Min(TX, TY) > 1.f + 1e-3f)
		{
			break;
		}
		int32 Dir;
		if (FMath::Abs(TX - TY) < 1e-4f)
		{
			Dir = DirIndex(Sx, Sy);
			C.X += Sx; C.Y += Sy; TX += TDx; TY += TDy;
		}
		else if (TX < TY)
		{
			Dir = DirIndex(Sx, 0);
			C.X += Sx; TX += TDx;
		}
		else
		{
			Dir = DirIndex(0, Sy);
			C.Y += Sy; TY += TDy;
		}
		Cur = Nodes[Cur].Nb[Dir];
		if (Cur < 0 || !Open(Cur))
		{
			return false;
		}
	}
	return Cur == ToNode;
}

bool UVLGrid::Flood(TConstArrayView<int32> Goals, const TArray<int32>& Starts)
{
	++Stamp;
	if (Stamp == 0)
	{
		FMemory::Memzero(Seen.GetData(), Seen.Num() * sizeof(uint32));
		Stamp = 1;
	}
	// A* toward the starts' bounding box (admissible for every start), expanding from the goal
	FIntPoint BMin(MAX_int32, MAX_int32), BMax(MIN_int32, MIN_int32);
	for (int32 S : Starts)
	{
		BMin = BMin.ComponentMin(CellOf(S));
		BMax = BMax.ComponentMax(CellOf(S));
	}
	auto H = [&](int32 I)
	{
		const FIntPoint C = CellOf(I);
		const int32 Dx = FMath::Max3(BMin.X - C.X, 0, C.X - BMax.X);
		const int32 Dy = FMath::Max3(BMin.Y - C.Y, 0, C.Y - BMax.Y);
		return float(FMath::Max(Dx, Dy)) + (Diag - 1.f) * float(FMath::Min(Dx, Dy));
	};
	TSet<int32> Remaining(Starts);
	TArray<FOpen> Open;
	Open.Reserve(4096);
	for (int32 G : Goals)
	{
		Seen[G] = Stamp;
		Cost[G] = 0.f;
		Next[G] = INDEX_NONE;
		Open.HeapPush({ H(G), G }, FOpenLess());
	}
	while (Open.Num() > 0)
	{
		FOpen Top;
		Open.HeapPop(Top, FOpenLess());
		const int32 I = Top.I;
		const float GCost = Cost[I];
		if (Top.F > GCost + H(I) + 1e-3f)
		{
			continue;
		}
		Remaining.Remove(I);
		if (Remaining.Num() == 0)
		{
			return true;
		}
		const float Here = Nodes[I].bNearWall ? 1.f + WallPenalty : 1.f;
		for (int32 n = 0; n < 8; ++n)
		{
			const int32 J = Nodes[I].Nb[n];
			if (J < 0)
			{
				continue;
			}
			const float There = Nodes[J].bNearWall ? 1.f + WallPenalty : 1.f;
			const float NewCost = GCost + (n >= 4 ? Diag : 1.f) * 0.5f * (Here + There);
			if (Seen[J] != Stamp || NewCost < Cost[J])
			{
				Seen[J] = Stamp;
				Cost[J] = NewCost;
				Next[J] = I;
				Open.HeapPush({ NewCost + H(J), J }, FOpenLess());
			}
		}
	}
	return Remaining.Num() == 0;
}

void UVLGrid::StringPull(const TArray<int32>& Chain, TArray<FVector>& Out)
{
	// Chain runs start -> goal. Keep only the corners: from each anchor, as far along as a straight walk allows, and
	// that walk stays out of cells hard against a wall except the ones the search itself went through (a gate, the
	// bridge, the top of a flight of steps): the search paid to keep its distance, straightening must not give it back.
	if (Chain.Num() == 0)
	{
		return;
	}
	if (++RouteStamp == 0)
	{
		FMemory::Memzero(RouteMark.GetData(), RouteMark.Num() * sizeof(uint32));
		RouteStamp = 1;
	}
	for (int32 I : Chain)
	{
		RouteMark[I] = RouteStamp;
	}
	int32 Anchor = 0;
	while (Anchor < Chain.Num() - 1)
	{
		const FVector2D AnchorPos(NodePos(Chain[Anchor]));
		int32 FarI = Anchor + 1;
		for (int32 k = Anchor + 2; k < Chain.Num(); ++k)
		{
			if (WalkLine(Chain[Anchor], AnchorPos, FVector2D(NodePos(Chain[k])), Chain[k], ELineRule::Route))
			{
				FarI = k;
			}
			else if (k - FarI > 8)
			{
				break;
			}
		}
		Out.Add(NodePos(Chain[FarI]));
		Anchor = FarI;
	}
}

bool UVLGrid::FindGroupPaths(const TArray<FVector>& Starts, const FVector& Goal, TArray<TArray<FVector>>& OutPaths, TArray<FVector>* OutGoals)
{
	OutPaths.SetNum(Starts.Num());
	for (TArray<FVector>& P : OutPaths)
	{
		P.Reset();
	}
	if (OutGoals)
	{
		OutGoals->Init(Goal, Starts.Num());
	}
	if (!EnsureBuilt() || Starts.Num() == 0)
	{
		return true;
	}
	const double T0 = FPlatformTime::Seconds();
	const int32 GoalNode = NearestNode(Goal, 24);
	if (GoalNode == INDEX_NONE)
	{
		return false;
	}
	// the exact point asked for when it lies in an open cell, else that nearest cell's middle
	FIntPoint GC;
	const bool bExact = ToCell(FVector2D(Goal), GC) && CellIdx(GC) == Nodes[GoalNode].Cell;
	const FVector G = bExact ? FVector(Goal.X, Goal.Y, Nodes[GoalNode].Z) : NodePos(GoalNode);
	const int32 GoalRegion = Nodes[GoalNode].Region;
	if (OutGoals)
	{
		OutGoals->Init(G, Starts.Num());
	}

	// Walkers that can walk straight at the goal need no search. The rest are sorted by the ground they stand on:
	// those on the goal's ground share one search; a walker cut off from it (on a ledge, across the gorge) is routed
	// to the nearest point its own ground comes to the goal.
	struct FWalker
	{
		int32 Index;
		int32 Node;
		bool bSnapped;
	};
	TMap<int32, TArray<FWalker>> ByRegion;
	int32 Searched = 0;
	for (int32 i = 0; i < Starts.Num(); ++i)
	{
		FWalker W{ i, NodeAt(Starts[i]), false };
		if (W.Node == INDEX_NONE)
		{
			W.Node = NearestNode(Starts[i], 6);
			W.bSnapped = true;
		}
		if (W.Node == INDEX_NONE)
		{
			if (OutGoals)
			{
				(*OutGoals)[i] = Starts[i];
			}
			continue;
		}
		const int32 Region = Nodes[W.Node].Region;
		if (Region == GoalRegion && !W.bSnapped && WalkLine(W.Node, FVector2D(Starts[i]), FVector2D(G), GoalNode, ELineRule::Clear))
		{
			continue;
		}
		ByRegion.FindOrAdd(Region).Add(W);
		++Searched;
	}

	bool bAny = Searched < Starts.Num();
	TArray<int32> StartNodes, Chain;
	for (const TPair<int32, TArray<FWalker>>& Pair : ByRegion)
	{
		int32 To = GoalNode;
		if (Pair.Key != GoalRegion)
		{
			To = NearestNode(Goal, 80, Pair.Key);
			for (const FWalker& W : Pair.Value)
			{
				if (OutGoals)
				{
					(*OutGoals)[W.Index] = To != INDEX_NONE ? NodePos(To) : Starts[W.Index];
				}
			}
			if (To == INDEX_NONE)
			{
				continue;
			}
		}
		StartNodes.Reset();
		for (const FWalker& W : Pair.Value)
		{
			StartNodes.Add(W.Node);
		}
		Flood(MakeArrayView(&To, 1), StartNodes);
		for (const FWalker& W : Pair.Value)
		{
			if (Seen[W.Node] != Stamp)
			{
				continue;
			}
			Chain.Reset();
			for (int32 I = W.Node; I != INDEX_NONE && Chain.Num() < Nodes.Num(); I = Next[I])
			{
				Chain.Add(I);
			}
			TArray<FVector>& Path = OutPaths[W.Index];
			StringPull(Chain, Path);
			if (Path.Num() > 0)
			{
				Path.Pop();          // the goal cell's middle: the caller appends the exact slot instead
			}
			if (W.bSnapped)
			{
				Path.Insert(NodePos(W.Node), 0);
			}
			bAny = true;
		}
	}
	UE_LOG(LogVoxelLab, Verbose, TEXT("PATH group of %d (%d searched) in %.2f ms"), Starts.Num(), Searched, (FPlatformTime::Seconds() - T0) * 1000.0);
	return bAny;
}

bool UVLGrid::FindPath(const FVector& From, const FVector& Goal, TArray<FVector>& OutPath)
{
	TArray<TArray<FVector>> Paths;
	TArray<FVector> Goals;
	const bool bOk = FindGroupPaths({ From }, Goal, Paths, &Goals);
	OutPath = Paths.Num() > 0 ? Paths[0] : TArray<FVector>();
	OutPath.Add(Goals.Num() > 0 ? Goals[0] : Goal);
	return bOk;
}

void UVLGrid::FitSlots(const FVector& Goal, const TArray<FVector2D>& Slots, TArray<FVector>& Out) const
{
	Out.Reset();
	for (const FVector2D& S : Slots)
	{
		Out.Add(FVector(S.X, S.Y, Goal.Z));
	}
	const int32 GoalNode = IsBuilt() ? NodeAt(Goal, 200.f) : INDEX_NONE;
	if (GoalNode == INDEX_NONE || Slots.Num() == 0)
	{
		return;
	}
	const FIntPoint GC = CellOf(GoalNode);
	// ground that can be walked to from the goal without leaving the formation's neighbourhood
	float Reach = 0.f;
	for (const FVector2D& S : Slots)
	{
		Reach = FMath::Max(Reach, float(FMath::Max(FMath::Abs(S.X - Goal.X), FMath::Abs(S.Y - Goal.Y))));
	}
	const int32 R = FMath::Clamp(FMath::CeilToInt(Reach / Cell) + 6, 8, 60);
	const int32 W = 2 * R + 1;
	TArray<int32> Near;          // per cell of the neighbourhood: the node reached there, or -1
	Near.Init(INDEX_NONE, W * W);
	auto Local = [&](const FIntPoint& C) { return (C.Y - GC.Y + R) * W + (C.X - GC.X + R); };
	auto InsideR = [&](const FIntPoint& C) { return FMath::Abs(C.X - GC.X) <= R && FMath::Abs(C.Y - GC.Y) <= R; };
	TArray<int32> Front;
	Front.Add(GoalNode);
	Near[Local(GC)] = GoalNode;
	for (int32 Head = 0; Head < Front.Num(); ++Head)
	{
		for (int32 n = 0; n < 8; ++n)
		{
			const int32 J = Nodes[Front[Head]].Nb[n];
			if (J < 0)
			{
				continue;
			}
			const FIntPoint NC = CellOf(J);
			if (!InsideR(NC) || Near[Local(NC)] != INDEX_NONE)
			{
				continue;
			}
			Near[Local(NC)] = J;
			Front.Add(J);
		}
	}
	TSet<int32> Taken;
	for (int32 i = 0; i < Slots.Num(); ++i)
	{
		const FVector2D S = Slots[i];
		const FIntPoint SC = ToCellClamped(S);
		if (InsideR(SC) && Near[Local(SC)] != INDEX_NONE && !Nodes[Near[Local(SC)]].bNearWall && !Taken.Contains(Near[Local(SC)]))
		{
			Taken.Add(Near[Local(SC)]);
			Out[i].Z = Nodes[Near[Local(SC)]].Z;
			continue;
		}
		float BestScore = TNumericLimits<float>::Max();
		int32 Best = INDEX_NONE;
		for (int32 Ring = 0; Ring <= 12 && Best == INDEX_NONE; ++Ring)
		{
			for (int32 dy = -Ring; dy <= Ring; ++dy)
			{
				for (int32 dx = -Ring; dx <= Ring; ++dx)
				{
					if (FMath::Max(FMath::Abs(dx), FMath::Abs(dy)) != Ring)
					{
						continue;
					}
					const FIntPoint NC(SC.X + dx, SC.Y + dy);
					if (!InsideR(NC) || Near[Local(NC)] == INDEX_NONE)
					{
						continue;
					}
					const int32 J = Near[Local(NC)];
					const float Score = FVector2D::DistSquared(CellCentre(NC), S) + (Taken.Contains(J) ? FMath::Square(Cell * 4.f) : 0.f)
						+ (Nodes[J].bNearWall ? FMath::Square(Cell) : 0.f);
					if (Score < BestScore)
					{
						BestScore = Score;
						Best = J;
					}
				}
			}
		}
		if (Best != INDEX_NONE)
		{
			Out[i] = NodePos(Best);
			Taken.Add(Best);
		}
		else
		{
			Out[i] = FVector(Goal.X, Goal.Y, Nodes[GoalNode].Z);
		}
	}
}

void UVLGrid::DebugDraw(const FVector& Around, float Radius, float Seconds) const
{
	UWorld* World = GetWorld();
	if (!World || !IsBuilt())
	{
		return;
	}
	const FIntPoint Lo = ToCellClamped(FVector2D(Around) - FVector2D(Radius, Radius)), Hi = ToCellClamped(FVector2D(Around) + FVector2D(Radius, Radius));
	for (int32 y = Lo.Y; y <= Hi.Y; ++y)
	{
		for (int32 x = Lo.X; x <= Hi.X; ++x)
		{
			const int32 CI = y * DimX + x;
			for (int32 k = 0; k < Count[CI]; ++k)
			{
				const FNode& Node = Nodes[First[CI] + k];
				const FColor Colour = Node.Region != Main ? FColor(255, 60, 200) : (Node.bNearWall ? FColor(255, 210, 40) : FColor(60, 255, 90));
				DrawDebugPoint(World, NodePos(First[CI] + k) + FVector(0.f, 0.f, 8.f), 5.f, Colour, false, Seconds);
			}
		}
	}
}
