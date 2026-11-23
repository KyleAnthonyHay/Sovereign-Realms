#include "VLGrid.h"
#include "SovereignRealms.h"
#include "Components/StaticMeshComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "Async/ParallelFor.h"
#include "HAL/IConsoleManager.h"
#include "Hash/CityHash.h"
#include "Physics/PhysicsInterfaceCore.h"
#include "Physics/Experimental/PhysInterface_Chaos.h"

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

	// The level is sampled (and joined) on worker threads, row by row; 0: cell after cell on the game thread, as it
	// was. The grid is the same either way (vl.Opt.GridChecksum 1 logs a checksum of it to compare).
	TAutoConsoleVariable<int32> CVarParallelGrid(TEXT("vl.Opt.ParallelGrid"), 1, TEXT("1: the path grid is sampled on worker threads (the same grid, sooner). 0: on the game thread only"));
	TAutoConsoleVariable<int32> CVarFastRegions(TEXT("vl.Opt.FastRegions"), 1, TEXT("1: the grid's regions of connected ground are worked out in one pass over the nodes in order (the same regions, sooner). 0: by the flood"));
	TAutoConsoleVariable<int32> CVarGridChecksum(TEXT("vl.Opt.GridChecksum"), 0, TEXT("1: log a checksum of the path grid whenever it is built or a part of it sampled again"));
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

void UVLGrid::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	ApplyLevelCollision(&InWorld);
}

bool UVLGrid::IsUnseen(const AActor* Actor)
{
	return Actor && (Actor->ActorHasTag(TEXT("Barrier")) || Actor->ActorHasTag(TEXT("Water")) || Actor->ActorHasTag(TEXT("Backdrop"))
		|| (Actor->IsHidden() && Actor->IsA<AStaticMeshActor>()));
}

void UVLGrid::ApplyLevelCollision(UWorld* World)
{
	if (!World)
	{
		return;
	}
	int32 Walls = 0, Sheets = 0, Scenery = 0;
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		UStaticMeshComponent* Comp = It->GetStaticMeshComponent();
		if (!Comp)
		{
			continue;
		}
		if (It->ActorHasTag(TEXT("Backdrop")))
		{
			Comp->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);     // (also ends "use default collision")
			++Scenery;
		}
		else if (It->ActorHasTag(TEXT("Water")))
		{
			Comp->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
			Comp->SetCollisionObjectType(ECC_WorldDynamic);
			Comp->SetCollisionResponseToAllChannels(ECR_Ignore);
			Comp->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
			++Sheets;
		}
		else if (It->ActorHasTag(TEXT("Barrier")) || (It->IsHidden() && It->Tags.Num() == 0 && It->GetActorEnableCollision()))
		{
			// (a hidden actor with tags is something else: a razed building, hidden with its collision off)
			Comp->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
			Comp->SetCollisionObjectType(ECC_WorldStatic);
			Comp->SetCollisionResponseToAllChannels(ECR_Ignore);
			Comp->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
			Comp->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			++Walls;
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("level collision: %d hidden wall(s) block pawns only, %d water sheet(s) and %d backdrop(s) stop nothing"), Walls, Sheets, Scenery);
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
	ApplyLevelCollision(World);     // (again: cheap, and the floors below must not be found on a hidden wall's top)
	const double T0 = FPlatformTime::Seconds();
	const bool bParallel = CVarParallelGrid.GetValueOnGameThread() != 0;
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
		UE_LOG(LogSovereignRealms, Warning, TEXT("GRID: no ground in this level (no actor tagged Ground, no SM_Terrain / SM_Flat mesh)"));
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
		// (a row of cells is one task: each writes its own cells of WaterZ only, and only reads the sheet)
		ParallelFor(TEXT("VLGridWater"), Hi.Y - Lo.Y + 1, 1, [&](int32 Row)
		{
			// (the physics scene is locked for reading once for the row: each trace's own lock is then only counted,
			// and the workers do not queue at the scene's lock for every cell)
			FPhysicsCommand::ExecuteRead(World->GetPhysicsScene(), [&]()
			{
				const int32 y = Lo.Y + Row;
				for (int32 x = Lo.X; x <= Hi.X; ++x)
				{
					const FVector2D P = CellCentre(FIntPoint(x, y));
					FHitResult Hit;
					if (Sheet->LineTraceComponent(Hit, FVector(P.X, P.Y, Box.Max.Z + 50.f), FVector(P.X, P.Y, Box.Min.Z - 50.f), WaterParams))
					{
						WaterZ[y * DimX + x] = FMath::Max(WaterZ[y * DimX + x], float(Hit.ImpactPoint.Z));
					}
				}
			});
		}, bParallel ? EParallelForFlags::None : EParallelForFlags::ForceSingleThread);
	}
	const double T1 = FPlatformTime::Seconds();

	// floors
	SampleTop = Top;
	SampleBottom = Bottom;
	int32 Wet = 0, Tight = 0, Inside = 0;
	Nodes.Reserve(N);
	SampleCells(World, FIntPoint(0, 0), FIntPoint(DimX - 1, DimY - 1), TConstArrayView<FIntRect>(), Params, Ground, Wet, Tight, Inside);
	const double T2 = FPlatformTime::Seconds();

	// joins: a step of at most StepHeight to the neighbouring cell's nearest floor; diagonals only between joined sides
	// (each node writes its own joins only, from floors that no longer change: the nodes are shared out to the workers.
	// The diagonals read the sides of other nodes, all written by then, and write the node's own diagonals)
	const EParallelForFlags JoinFlags = bParallel ? EParallelForFlags::None : EParallelForFlags::ForceSingleThread;
	ParallelFor(TEXT("VLGridSides"), Nodes.Num(), 8192, [this](int32 I)
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
	}, JoinFlags);
	ParallelFor(TEXT("VLGridDiagonals"), Nodes.Num(), 8192, [this](int32 I)
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
		bool bWall = false;
		for (int32 n = 0; n < 8; ++n)
		{
			bWall |= Node.Nb[n] < 0;
		}
		Node.bNearWall = bWall;
	}, JoinFlags);
	const double T3 = FPlatformTime::Seconds();

	// regions of connected ground
	int32 MainSize = 0;
	const int32 Regions = LabelRegions(MainSize);
	Cost.Init(0.f, Nodes.Num());
	Next.Init(INDEX_NONE, Nodes.Num());
	Seen.Init(0, Nodes.Num());
	RouteMark.Init(0, Nodes.Num());
	Stamp = RouteStamp = 0;
	++Revision;
	const double T4 = FPlatformTime::Seconds();
	UE_LOG(LogSovereignRealms, Log, TEXT("GRID built: %dx%d cells of %.0f cm, %d nodes in %d regions (the main one %d), rejected: %d under water (%d sheets), %d too tight, %d inside solids; in %.0f ms"),
		DimX, DimY, Cell, Nodes.Num(), Regions, MainSize, Wet, Water.Num(), Tight, Inside, (T4 - T0) * 1000.0);
	UE_LOG(LogSovereignRealms, Log, TEXT("GRID timing (%s): water %.0f ms, floors %.0f ms, joins %.0f ms, regions %.0f ms"), bParallel ? TEXT("worker threads") : TEXT("game thread only"),
		(T1 - T0) * 1000.0, (T2 - T1) * 1000.0, (T3 - T2) * 1000.0, (T4 - T3) * 1000.0);
	if (CVarGridChecksum.GetValueOnGameThread() != 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("GRID checksum %016llx (%d nodes, built %s)"), Checksum(), Nodes.Num(), bParallel ? TEXT("on worker threads") : TEXT("on the game thread"));
	}
}

int32 UVLGrid::SampleFloors(UWorld* World, int32 C, const FCollisionQueryParams& Params, const TSet<const UPrimitiveComponent*>& Ground, float* OutZ, int32& Wet, int32& Tight, int32& Inside) const
{
	const FVector2D P = CellCentre(FIntPoint(C % DimX, C / DimX));
	const float Top = SampleTop, Bottom = SampleBottom;
	const float Lift = StepHeight + 4.f;
	const float HalfHeight = (UnitHeight - Lift) * 0.5f;
	const FCollisionShape Body = FCollisionShape::MakeCapsule(UnitRadius, FMath::Max(HalfHeight, UnitRadius));
	int32 Found = 0;
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
				OutZ[Found++] = FZ;
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
	return Found;
}

void UVLGrid::SampleCells(UWorld* World, const FIntPoint& Lo, const FIntPoint& Hi, TConstArrayView<FIntRect> Only, const FCollisionQueryParams& Params,
	const TSet<const UPrimitiveComponent*>& Ground, int32& Wet, int32& Tight, int32& Inside)
{
	const int32 Rows = Hi.Y - Lo.Y + 1, Cols = Hi.X - Lo.X + 1;
	if (Rows <= 0 || Cols <= 0)
	{
		return;
	}
	auto Wanted = [&Only](int32 x, int32 y)
	{
		if (Only.Num() == 0)
		{
			return true;
		}
		for (const FIntRect& R : Only)
		{
			if (x >= R.Min.X && x <= R.Max.X && y >= R.Min.Y && y <= R.Max.Y)
			{
				return true;
			}
		}
		return false;
	};
	// a row's floors, in the order of its cells (how many each cell has: Count); the scene queries only read the
	// physics scene (as the engine's own async traces do), and nothing here writes anything two rows share
	struct FRow
	{
		TArray<float> Z;
		int32 Wet = 0, Tight = 0, Inside = 0;
	};
	TArray<FRow> Sampled;
	Sampled.SetNum(Rows);
	const bool bParallel = CVarParallelGrid.GetValueOnGameThread() != 0 && Rows > 1;
	ParallelFor(TEXT("VLGridFloors"), Rows, 1, [&](int32 Row)
	{
		FRow& Out = Sampled[Row];
		Out.Z.Reserve(Cols + Cols / 4);
		// (one read lock of the physics scene for the row, as for the water)
		FPhysicsCommand::ExecuteRead(World->GetPhysicsScene(), [&]()
		{
			const int32 y = Lo.Y + Row;
			float Z[MaxLayers];
			for (int32 x = Lo.X; x <= Hi.X; ++x)
			{
				if (!Wanted(x, y))
				{
					continue;
				}
				const int32 C = y * DimX + x;
				const int32 Found = SampleFloors(World, C, Params, Ground, Z, Out.Wet, Out.Tight, Out.Inside);
				Count[C] = uint8(Found);
				Out.Z.Append(Z, Found);
			}
		});
	}, bParallel ? EParallelForFlags::None : EParallelForFlags::ForceSingleThread);
	// put together cell after cell: the same nodes, in the same order, as sampling them one by one
	for (int32 Row = 0; Row < Rows; ++Row)
	{
		const FRow& In = Sampled[Row];
		const int32 y = Lo.Y + Row;
		int32 At = 0;
		for (int32 x = Lo.X; x <= Hi.X; ++x)
		{
			if (!Wanted(x, y))
			{
				continue;
			}
			const int32 C = y * DimX + x;
			First[C] = Nodes.Num();
			for (int32 k = 0; k < Count[C]; ++k)
			{
				FNode& Node = Nodes.AddDefaulted_GetRef();
				Node.Z = In.Z[At++];
				Node.Cell = C;
			}
		}
		Wet += In.Wet;
		Tight += In.Tight;
		Inside += In.Inside;
	}
}

uint64 UVLGrid::Checksum() const
{
	uint64 H = CityHash64WithSeed(reinterpret_cast<const char*>(First.GetData()), First.Num() * sizeof(int32), uint64(DimX) << 32 | uint32(DimY));
	H = CityHash64WithSeed(reinterpret_cast<const char*>(Count.GetData()), Count.Num(), H);
	H = CityHash64WithSeed(reinterpret_cast<const char*>(WaterZ.GetData()), WaterZ.Num() * sizeof(float), H);
	// (field by field: a node has padding bytes that are not its value)
	struct FPacked
	{
		float Z;
		int32 Cell, Region, Nb[8], Wall;
	};
	TArray<FPacked> Packed;
	Packed.SetNumUninitialized(Nodes.Num());
	for (int32 I = 0; I < Nodes.Num(); ++I)
	{
		const FNode& N = Nodes[I];
		FPacked& P = Packed[I];
		P.Z = N.Z;
		P.Cell = N.Cell;
		P.Region = N.Region;
		FMemory::Memcpy(P.Nb, N.Nb, sizeof(P.Nb));
		P.Wall = N.bNearWall ? 1 : 0;
	}
	H = CityHash64WithSeed(reinterpret_cast<const char*>(Packed.GetData()), Packed.Num() * sizeof(FPacked), H);
	return CityHash64WithSeed(reinterpret_cast<const char*>(&Main), sizeof(Main), H);
}

int32 UVLGrid::LabelRegions(int32& OutMainSize)
{
	const int32 N = Nodes.Num();
	int32 Regions = 0;
	OutMainSize = 0;
	Main = 0;
	// The quick way: one pass over the nodes in order, joining each to the sets of its neighbours before it (the
	// lowest node of a set is its root), then one more to number the sets in the order of their roots. That is the
	// flood below exactly (a region per piece of ground, numbered by its first node) as long as every join goes both
	// ways, which the pass checks as it goes; the first one that does not, and the flood does it instead.
	// (Next and Seen are borrowed as scratch: both are set up afresh by the caller right after.)
	bool bQuick = CVarFastRegions.GetValueOnGameThread() != 0;
	if (bQuick)
	{
		static const int32 Opposite[8] = { 1, 0, 3, 2, 7, 6, 5, 4 };
		Next.SetNumUninitialized(N, EAllowShrinking::No);
		Seen.SetNumUninitialized(N, EAllowShrinking::No);
		int32* Parent = Next.GetData();
		const FNode* All = Nodes.GetData();
		for (int32 I = 0; I < N && bQuick; ++I)
		{
			const FNode& Node = All[I];
			if (Node.Region < 0)
			{
				Parent[I] = -1;         // (dead: no floor any more)
				continue;
			}
			Parent[I] = I;
			int32 Root = I;
			for (int32 n = 0; n < 8; ++n)
			{
				const int32 J = Node.Nb[n];
				if (J < 0)
				{
					continue;
				}
				if (All[J].Nb[Opposite[n]] != I || All[J].Region < 0)
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("GRID regions: node %d joins %d (side %d) but not the other way round (%d): the flood does the regions"), I, J, n, All[J].Nb[Opposite[n]]);
					bQuick = false;
					break;
				}
				if (J < I)
				{
					int32 R = J;
					while (Parent[R] != R)
					{
						Parent[R] = Parent[Parent[R]];
						R = Parent[R];
					}
					if (R < Root)
					{
						Parent[Root] = R;
						Root = R;
					}
					else if (R > Root)
					{
						Parent[R] = Root;
					}
				}
			}
		}
		if (bQuick)
		{
			uint32* Label = Seen.GetData();
			TArray<int32> Sizes;
			for (int32 I = 0; I < N; ++I)
			{
				if (Parent[I] < 0)
				{
					continue;
				}
				int32 R = I;
				while (Parent[R] != R)
				{
					R = Parent[R];
				}
				Parent[I] = R;
				if (R == I)
				{
					Label[I] = uint32(++Regions);
					Sizes.Add(0);
				}
				else
				{
					Label[I] = Label[R];        // (its root comes before it: numbered already)
				}
				const int32 Region = int32(Label[I]);
				++Sizes[Region - 1];
				FNode& Node = Nodes[I];
				if (Node.Region != Region)
				{
					Node.Region = Region;
				}
			}
			for (int32 k = 0; k < Sizes.Num(); ++k)
			{
				if (Sizes[k] > OutMainSize)
				{
					OutMainSize = Sizes[k];
					Main = k + 1;
				}
			}
			return Regions;
		}
	}
	// the flood: from each node not yet in a region, everything that can be walked to from it
	for (FNode& Node : Nodes)
	{
		Node.Region = Node.Region < 0 ? -1 : 0;
	}
	TArray<int32> Stack;
	for (int32 Seed = 0; Seed < N; ++Seed)
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
		if (Size > OutMainSize)
		{
			OutMainSize = Size;
			Main = Regions;
		}
	}
	return Regions;
}

int32 UVLGrid::RebuildArea(const FBox2D& Area)
{
	return RebuildAreas(MakeArrayView(&Area, 1));
}

int32 UVLGrid::RebuildAreas(TConstArrayView<FBox2D> Areas)
{
	UWorld* World = GetWorld();
	if (!World || !IsBuilt())
	{
		return 0;
	}
	// the areas as cells; all of them inside Lo..Hi
	TArray<FIntRect, TInlineAllocator<4>> Rects;
	for (const FBox2D& Area : Areas)
	{
		if (Area.bIsValid)
		{
			Rects.Add(FIntRect(ToCellClamped(Area.Min), ToCellClamped(Area.Max)));       // (Max: the last cell, itself part of it)
		}
	}
	if (Rects.Num() == 0)
	{
		return 0;
	}
	FIntPoint Lo = Rects[0].Min, Hi = Rects[0].Max;
	for (const FIntRect& R : Rects)
	{
		Lo = FIntPoint(FMath::Min(Lo.X, R.Min.X), FMath::Min(Lo.Y, R.Min.Y));
		Hi = FIntPoint(FMath::Max(Hi.X, R.Max.X), FMath::Max(Hi.Y, R.Max.Y));
	}
	// is this cell in one of the areas, each grown by Grow cells? (one area: every cell of Lo..Hi is)
	auto InAreas = [&Rects](int32 x, int32 y, int32 Grow)
	{
		for (const FIntRect& R : Rects)
		{
			if (x >= R.Min.X - Grow && x <= R.Max.X + Grow && y >= R.Min.Y - Grow && y <= R.Max.Y + Grow)
			{
				return true;
			}
		}
		return false;
	};
	const double T0 = FPlatformTime::Seconds();
	// what Build looks at: the ground (where the search for floors stops); pawns and water are not obstacles
	TSet<const UPrimitiveComponent*> Ground;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(VLGridArea), true);
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->IsA<APawn>() || It->ActorHasTag(TEXT("Water")))
		{
			Params.AddIgnoredActor(*It);
			continue;
		}
		const AStaticMeshActor* SMA = Cast<AStaticMeshActor>(*It);
		UStaticMeshComponent* Comp = SMA ? SMA->GetStaticMeshComponent() : nullptr;
		const UStaticMesh* Mesh = Comp ? Comp->GetStaticMesh() : nullptr;
		if (Mesh && (It->ActorHasTag(TEXT("Ground")) || Mesh->GetName().StartsWith(TEXT("SM_Terrain")) || Mesh->GetName().StartsWith(TEXT("SM_Flat_"))))
		{
			Ground.Add(Comp);
		}
	}
	auto Clamped = [this](const FIntPoint& C) { return FIntPoint(FMath::Clamp(C.X, 0, DimX - 1), FMath::Clamp(C.Y, 0, DimY - 1)); };
	const double T1 = FPlatformTime::Seconds();
	// 1. the cells' old floors go: nothing points at them any more (they stay in the array, dead: Region -1)
	for (int32 y = Lo.Y; y <= Hi.Y; ++y)
	{
		for (int32 x = Lo.X; x <= Hi.X; ++x)
		{
			if (!InAreas(x, y, 0))
			{
				continue;
			}
			const int32 C = y * DimX + x;
			for (int32 k = 0; k < Count[C]; ++k)
			{
				FNode& Old = Nodes[First[C] + k];
				for (int32 n = 0; n < 8; ++n)
				{
					if (Old.Nb[n] >= 0)
					{
						for (int32& Back : Nodes[Old.Nb[n]].Nb)
						{
							Back = Back == First[C] + k ? -1 : Back;
						}
						Old.Nb[n] = -1;
					}
				}
				Old.Region = -1;
			}
			Count[C] = 0;
		}
	}
	// 2. sampled again, as Build does
	int32 Wet = 0, Tight = 0, Inside = 0;
	const int32 Before = Nodes.Num();
	SampleCells(World, Lo, Hi, Rects.Num() > 1 ? TConstArrayView<FIntRect>(Rects) : TConstArrayView<FIntRect>(), Params, Ground, Wet, Tight, Inside);
	const double T2 = FPlatformTime::Seconds();
	// 3. joined again: the sides of these cells and of the ring round them, then the diagonals one ring further
	const FIntPoint Lo1 = Clamped(Lo - FIntPoint(1, 1)), Hi1 = Clamped(Hi + FIntPoint(1, 1));
	const FIntPoint Lo2 = Clamped(Lo - FIntPoint(2, 2)), Hi2 = Clamped(Hi + FIntPoint(2, 2));
	for (int32 y = Lo1.Y; y <= Hi1.Y; ++y)
	{
		for (int32 x = Lo1.X; x <= Hi1.X; ++x)
		{
			if (!InAreas(x, y, 1))
			{
				continue;
			}
			const int32 C = y * DimX + x;
			for (int32 k = 0; k < Count[C]; ++k)
			{
				FNode& Node = Nodes[First[C] + k];
				for (int32 n = 0; n < 4; ++n)
				{
					Node.Nb[n] = -1;
					const FIntPoint NC = FIntPoint(x, y) + Neighbours[n];
					if (!InGrid(NC))
					{
						continue;
					}
					const int32 NI = CellIdx(NC);
					float Best = StepHeight;
					for (int32 j = 0; j < Count[NI]; ++j)
					{
						const float D = FMath::Abs(Nodes[First[NI] + j].Z - Node.Z);
						if (D <= Best)
						{
							Best = D;
							Node.Nb[n] = First[NI] + j;
						}
					}
				}
			}
		}
	}
	for (int32 y = Lo2.Y; y <= Hi2.Y; ++y)
	{
		for (int32 x = Lo2.X; x <= Hi2.X; ++x)
		{
			if (!InAreas(x, y, 2))
			{
				continue;
			}
			const int32 C = y * DimX + x;
			for (int32 k = 0; k < Count[C]; ++k)
			{
				FNode& Node = Nodes[First[C] + k];
				Node.bNearWall = false;
				for (int32 n = 4; n < 8; ++n)
				{
					Node.Nb[n] = -1;
					const int32 A = Node.Nb[DirIndex(Neighbours[n].X, 0)], B = Node.Nb[DirIndex(0, Neighbours[n].Y)];
					if (A < 0 || B < 0)
					{
						continue;
					}
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
		}
	}
	const double T3 = FPlatformTime::Seconds();
	// 4. the regions of connected ground, over again (cleared ground may join two that were apart)
	int32 MainSize = 0;
	const int32 Regions = LabelRegions(MainSize);
	Cost.SetNumZeroed(Nodes.Num());
	Next.Init(INDEX_NONE, Nodes.Num());
	Seen.Init(0, Nodes.Num());
	RouteMark.Init(0, Nodes.Num());
	Stamp = RouteStamp = 0;
	++Revision;
	int32 Cells = 0;
	for (int32 y = Lo.Y; y <= Hi.Y; ++y)
	{
		for (int32 x = Lo.X; x <= Hi.X; ++x)
		{
			Cells += InAreas(x, y, 0) ? 1 : 0;
		}
	}
	const double T4 = FPlatformTime::Seconds();
	UE_LOG(LogSovereignRealms, Log, TEXT("GRID area: %d cells sampled again (%d floors; %d too tight, %d under water), %d regions (the main one %d); in %.1f ms (the level's actors %.1f, floors %.1f, joins %.1f, regions %.1f)"),
		Cells, Nodes.Num() - Before, Tight, Wet, Regions, MainSize, (T4 - T0) * 1000.0, (T1 - T0) * 1000.0, (T2 - T1) * 1000.0, (T3 - T2) * 1000.0, (T4 - T3) * 1000.0);
	if (CVarGridChecksum.GetValueOnGameThread() != 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("GRID checksum %016llx (%d nodes, after an area)"), Checksum(), Nodes.Num());
	}
	return Cells;
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

float UVLGrid::WaterLevelAt(const FVector& Point) const
{
	FIntPoint C;
	return IsBuilt() && ToCell(FVector2D(Point), C) ? WaterZ[CellIdx(C)] : -BIG_NUMBER;
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
	UE_LOG(LogSovereignRealms, Verbose, TEXT("PATH group of %d (%d searched) in %.2f ms"), Starts.Num(), Searched, (FPlatformTime::Seconds() - T0) * 1000.0);
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
