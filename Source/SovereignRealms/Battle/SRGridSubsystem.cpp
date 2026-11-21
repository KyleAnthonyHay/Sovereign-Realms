// Copyright Sovereign Realms.

#include "Battle/SRGridSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRMapInfo.h"
#include "Buildings/SRBuilding.h"
#include "Units/SRUnit.h"
#include "Battle/SRBattleSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "EngineUtils.h"
#include "DrawDebugHelpers.h"

#define LOCTEXT_NAMESPACE "SRGrid"

namespace
{
	const FIntPoint Neighbours[8] = { {1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}, {1, -1}, {-1, 1}, {-1, -1} };
	constexpr float Diag = 1.41421356f;

	// Deciding whether a cell is cut by ground too steep to walk (USRGridSubsystem::Build, "Edges"). The map
	// generator's own validation (Tools/) mirrors these numbers: change them there too.
	constexpr float EvenGroundRise = 20.f;    // every axis neighbour within this (cm) of the cell: open, no corner probes
	constexpr float SteepGroundRise = 70.f;   // both opposite neighbours more than this (cm) up one way and down the other: steep, no probes
	constexpr float CornerProbe = 0.45f;      // the corner probes stand this fraction of a cell out from its centre

	// With no map info in the level: the range the ground traces always ran over.
	constexpr float DefaultTraceTop = 8000.f;
	constexpr float DefaultTraceBottom = -2000.f;
	// With no water sheet in the level: the one water level the terraced map had (ground under this is water).
	constexpr float OldWaterLine = -30.f;

	struct FOpen
	{
		float F;
		int32 I;
	};
	struct FOpenLess { bool operator()(const FOpen& A, const FOpen& B) const { return A.F < B.F; } };
}

USRGridSubsystem* USRGridSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USRGridSubsystem>() : nullptr;
}

bool USRGridSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void USRGridSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	Build();
}

// ------------------------------------------------------------------- building the grid

void USRGridSubsystem::Build()
{
	UWorld* World = GetWorld();
	if (!World) { return; }
	const double T0 = FPlatformTime::Seconds();
	const USRFeelSettings& F = USRFeelSettings::Get();

	Cell = FMath::Max(F.GridCellSize, 25.f);
	const float Half = FMath::Max(F.MapHalfExtent.X, F.MapHalfExtent.Y);
	Dim = FMath::CeilToInt(2.f * Half / Cell);
	Origin = FVector2D(-Dim * Cell * 0.5f, -Dim * Cell * 0.5f);
	const int32 N = Dim * Dim;
	Heights.SetNumZeroed(N);
	Flags.SetNumZeroed(N);
	Cost.SetNumUninitialized(N);
	Next.SetNumUninitialized(N);
	Seen.SetNumZeroed(N);
	Stamp = 0;
	RouteMark.SetNumZeroed(N);
	RouteStamp = 0;
	Regions.Reset();
	bRegionsDirty = true;
	++Revision;
	Veins.Reset();
	Relics.Reset();

	// The map's own heights: the traces run from above its highest peak to below its deepest lake bed.
	const ASRMapInfo* Map = ASRMapInfo::Get(World);
	const float TraceTop = Map ? Map->GroundTraceTop : DefaultTraceTop;
	const float TraceBottom = Map ? FMath::Min(Map->GroundTraceBottom, TraceTop - 100.f) : DefaultTraceBottom;

	// Ground: one downward trace per cell against the terrain. Buildings and the hidden blocker boxes are left out;
	// they are footprints / obstacles, not ground. Nor are the water sheets (below).
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SRGridGround), false);
	TArray<const AActor*> BlockerActors;
	TArray<UStaticMeshComponent*> WaterSheets;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->IsA<ASRBuilding>() || It->ActorHasTag(TEXT("SRBlocker")) || It->ActorHasTag(TEXT("SRWater"))) { Params.AddIgnoredActor(*It); }
		if (It->ActorHasTag(TEXT("SRBlocker"))) { BlockerActors.Add(*It); }
		if (It->ActorHasTag(TEXT("SRWater")))
		{
			TArray<UStaticMeshComponent*> Comps;
			It->GetComponents(Comps);
			for (UStaticMeshComponent* Comp : Comps) { if (Comp && Comp->GetStaticMesh()) { WaterSheets.Add(Comp); } }
		}
	}
	// Water sheets (the lakes, tarns, rivers and streams: static meshes on actors tagged SRWater, each at its own
	// height, some running downhill). They are placed without collision; here each is made something that can be asked
	// about and that nothing ever runs into: queries only, its own object type, every channel ignored. The ground
	// traces, the cursor, the camera and the troops' wall probes all ask for WorldStatic objects, so none of them can
	// hit a sheet; only the traces below, aimed at one component at a time, do.
	for (UStaticMeshComponent* Sheet : WaterSheets)
	{
		Sheet->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		Sheet->SetCollisionObjectType(ECC_WorldDynamic);
		Sheet->SetCollisionResponseToAllChannels(ECR_Ignore);
		if (!Sheet->IsPhysicsStateCreated()) { Sheet->RecreatePhysicsState(); }   // (it had no body while it had no collision)
	}
	bWaterSheets = WaterSheets.Num() > 0;

	const FCollisionObjectQueryParams Objects(ECC_WorldStatic);
	TBitArray<> Ground(false, N);   // cells with ground under them (the others are holes: off the terrain)
	for (int32 y = 0; y < Dim; ++y)
	{
		for (int32 x = 0; x < Dim; ++x)
		{
			const FVector2D P = CellCentre(FIntPoint(x, y));
			FHitResult Hit;
			const int32 I = y * Dim + x;
			if (World->LineTraceSingleByObjectType(Hit, FVector(P.X, P.Y, TraceTop), FVector(P.X, P.Y, TraceBottom), Objects, Params))
			{
				Heights[I] = Hit.ImpactPoint.Z;
				Ground[I] = true;
				// (the terraced map: one water level for the whole field)
				if (!bWaterSheets && Hit.ImpactPoint.Z < OldWaterLine) { Flags[I] |= FlagWater | FlagBlocked; }
			}
			else
			{
				Flags[I] |= FlagBlocked;
			}
		}
	}

	// Water, by depth and not by height: there is water at many heights (a tarn in the mountains, the river in its
	// valley, a stream coming down a hillside), so a cell is deep water when the sheet over it lies more than WadeDepth
	// above its ground. Shallower is a ford (its bed lies a few cm under the surface): open ground, and troops wade it.
	// Each sheet is asked only about the cells under its bounds, and only where the ground is below its top.
	if (bWaterSheets)
	{
		TArray<float> Surface;
		Surface.Init(-BIG_NUMBER, N);
		FCollisionQueryParams WaterParams(SCENE_QUERY_STAT(SRGridWater), true);
		WaterParams.bTraceComplex = true;   // a sheet is a triangle mesh, its collision the mesh itself
		for (UStaticMeshComponent* Sheet : WaterSheets)
		{
			const FBox Box = Sheet->Bounds.GetBox();
			const FIntPoint Lo = ToCellClamped(FVector2D(Box.Min.X, Box.Min.Y)), Hi = ToCellClamped(FVector2D(Box.Max.X, Box.Max.Y));
			const float Top = FMath::Min(TraceTop, float(Box.Max.Z) + 10.f);
			for (int32 y = Lo.Y; y <= Hi.Y; ++y)
			{
				for (int32 x = Lo.X; x <= Hi.X; ++x)
				{
					const int32 I = y * Dim + x;
					if (!Ground[I] || Heights[I] >= Top) { continue; }
					const FVector2D P = CellCentre(FIntPoint(x, y));
					FHitResult Hit;
					if (Sheet->LineTraceComponent(Hit, FVector(P.X, P.Y, Top), FVector(P.X, P.Y, Heights[I]), WaterParams))
					{
						Surface[I] = FMath::Max(Surface[I], float(Hit.ImpactPoint.Z));
					}
				}
			}
		}
		for (int32 I = 0; I < N; ++I)
		{
			if (Ground[I] && Surface[I] - Heights[I] > F.WadeDepth) { Flags[I] |= FlagWater | FlagBlocked; }
		}
	}

	// Edges: a cell is open ground only if all of it is. A spread of heights across a cell taller than a step means
	// a mountainside, a bank or a crag cuts through it, and a walker sent across it would meet the real thing.
	// (Sampling the centre alone called such cells open, and routes straightened through them ran troops into the
	// cliff beside a ramp.) The spread is measured at the cell's centre and its four corners; but the ground is a
	// smooth heightfield now, nearly every cell has a slope, and probing four corners of each would cost four times
	// the traces of the ground pass on a map of half a million cells. So two shortcuts settle most cells from the
	// centres already sampled, and only the doubtful ones are probed:
	//  (a) every axis neighbour is open and within EvenGroundRise of the cell: gentle ground, open, no probes (a slope
	//      that shallow cannot spread a step across one cell);
	//  (b) along either axis, one neighbour is more than SteepGroundRise above the cell and the opposite one more than
	//      that below it: the cell lies on a slope steeper than 0.7, far past a step across the cell: an edge, no probes;
	//  (c) anything else: the four corners are traced, as before.
	{
		const float StepH = F.StepHeight;
		const float Probe = Cell * CornerProbe;
		const FIntPoint Side[4] = { {1, 0}, {-1, 0}, {0, 1}, {0, -1} };
		const FVector2D Corner[4] = { {Probe, Probe}, {Probe, -Probe}, {-Probe, Probe}, {-Probe, -Probe} };
		TArray<int32> Edge;
		int32 Probed = 0, Steep = 0;
		for (int32 y = 0; y < Dim; ++y)
		{
			for (int32 x = 0; x < Dim; ++x)
			{
				const int32 I = y * Dim + x;
				if (Flags[I] & FlagBlocked) { continue; }
				// (a) (a neighbour off the grid does not count against the cell: the outermost ring is closed anyway)
				bool bUneven = false;
				for (const FIntPoint& D : Side)
				{
					const FIntPoint C(x + D.X, y + D.Y);
					if (InGrid(C) && ((Flags[Idx(C)] & FlagBlocked) || FMath::Abs(Heights[Idx(C)] - Heights[I]) > EvenGroundRise)) { bUneven = true; break; }
				}
				if (!bUneven) { continue; }
				// (b) (the neighbours' heights count whether they are open or under water; a hole has no height)
				bool bSteep = false;
				for (int32 Axis = 0; Axis < 2 && !bSteep; ++Axis)
				{
					const FIntPoint A(x + Side[Axis * 2].X, y + Side[Axis * 2].Y), B(x + Side[Axis * 2 + 1].X, y + Side[Axis * 2 + 1].Y);
					if (!InGrid(A) || !InGrid(B) || !Ground[Idx(A)] || !Ground[Idx(B)]) { continue; }
					const float Up = Heights[Idx(A)] - Heights[I], Down = Heights[I] - Heights[Idx(B)];
					bSteep = (Up > SteepGroundRise && Down > SteepGroundRise) || (Up < -SteepGroundRise && Down < -SteepGroundRise);
				}
				if (bSteep) { ++Steep; Edge.Add(I); continue; }
				// (c)
				++Probed;
				const FVector2D P = CellCentre(FIntPoint(x, y));
				float Lo = Heights[I], Hi = Heights[I];
				bool bHole = false;
				for (const FVector2D& O : Corner)
				{
					FHitResult Hit;
					if (World->LineTraceSingleByObjectType(Hit, FVector(P.X + O.X, P.Y + O.Y, TraceTop), FVector(P.X + O.X, P.Y + O.Y, TraceBottom), Objects, Params))
					{
						Lo = FMath::Min(Lo, float(Hit.ImpactPoint.Z));
						Hi = FMath::Max(Hi, float(Hit.ImpactPoint.Z));
					}
					else { bHole = true; }
				}
				if (bHole || Hi - Lo > StepH) { Edge.Add(I); }
			}
		}
		for (int32 I : Edge) { Flags[I] |= FlagEdge | FlagBlocked; }
		EdgeCells = Edge.Num();
		UE_LOG(LogSovereign, Verbose, TEXT("GRID edges: %d cells plainly steep, %d probed at their corners, %d in all cut by a slope, a bank or a crag"), Steep, Probed, EdgeCells);
	}

	// Obstacles: rasterise every hidden blocker box (one cube instance per rock / trunk / ruin piece), grown by half a
	// cell so a thin trunk still blocks the cell it stands in.
	auto RasterBox = [&](const FTransform& Xf, const FVector& HalfExtent)
	{
		const FVector Ext(HalfExtent.X + Cell * 0.5f, HalfExtent.Y + Cell * 0.5f, HalfExtent.Z);
		const FVector C = Xf.GetLocation();
		const float R = FVector2D(Ext.X, Ext.Y).Size();
		const FIntPoint Lo = ToCellClamped(FVector2D(C.X - R, C.Y - R));
		const FIntPoint Hi = ToCellClamped(FVector2D(C.X + R, C.Y + R));
		const FQuat Q = Xf.GetRotation();
		for (int32 y = Lo.Y; y <= Hi.Y; ++y)
		{
			for (int32 x = Lo.X; x <= Hi.X; ++x)
			{
				const FVector2D P = CellCentre(FIntPoint(x, y));
				const FVector L = Q.UnrotateVector(FVector(P.X, P.Y, C.Z) - C);
				if (FMath::Abs(L.X) <= Ext.X && FMath::Abs(L.Y) <= Ext.Y) { Flags[y * Dim + x] |= FlagBlocked; }
			}
		}
	};
	int32 Boxes = 0;
	for (const AActor* Actor : BlockerActors)
	{
		TArray<UStaticMeshComponent*> Comps;
		Actor->GetComponents(Comps);
		for (UStaticMeshComponent* Comp : Comps)
		{
			const UStaticMesh* Mesh = Comp->GetStaticMesh();
			if (!Mesh) { continue; }
			const FVector MeshHalf = Mesh->GetBounds().BoxExtent;
			if (UInstancedStaticMeshComponent* ISM = Cast<UInstancedStaticMeshComponent>(Comp))
			{
				for (int32 k = 0; k < ISM->GetInstanceCount(); ++k)
				{
					FTransform Xf;
					ISM->GetInstanceTransform(k, Xf, true);
					RasterBox(FTransform(Xf.GetRotation(), Xf.GetLocation()), MeshHalf * Xf.GetScale3D());
					++Boxes;
				}
			}
			else
			{
				const FTransform Xf = Comp->GetComponentTransform();
				RasterBox(FTransform(Xf.GetRotation(), Xf.GetLocation()), MeshHalf * Xf.GetScale3D());
				++Boxes;
			}
		}
	}

	// The outermost ring is off limits (keeps paths and buildings inside the camera's bounds).
	for (int32 k = 0; k < Dim; ++k)
	{
		Flags[k] |= FlagBlocked; Flags[(Dim - 1) * Dim + k] |= FlagBlocked;
		Flags[k * Dim] |= FlagBlocked; Flags[k * Dim + Dim - 1] |= FlagBlocked;
	}

	// Gold veins: the SM_GoldVein outcrops placed by the world generator.
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		const UStaticMeshComponent* Comp = It->GetStaticMeshComponent();
		const UStaticMesh* Mesh = Comp ? Comp->GetStaticMesh() : nullptr;
		if (Mesh && Mesh->GetName().StartsWith(TEXT("SM_GoldVein")))
		{
			FSRVein& V = Veins.AddDefaulted_GetRef();
			V.Pos = FVector2D(It->GetActorLocation());
			V.Z = It->GetActorLocation().Z;
			FIntPoint C;
			if (ToCell(V.Pos, C)) { Flags[Idx(C)] |= FlagVein; }
		}
	}

	// Old ruins a tower can be raised on, as the level builder marked them: a static mesh actor tagged SRRelic is a
	// relic, for the Relic Tower (an ancient ruin, wherever the map puts one: a broken tower, a stone circle's dolmen);
	// one tagged SRRuinTower is an old broken tower, and a Watchtower can be raised on it. What stands round a relic
	// and belongs to it (its standing stones: any actor tagged SRRelicPart close by, and the SM_Menhir stones) is
	// hidden with it.
	TArray<AActor*> Stones, Parts;
	bool bTagged = false;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->ActorHasTag(TEXT("SRRelicPart"))) { Parts.Add(*It); }
		const AStaticMeshActor* Ruin = Cast<AStaticMeshActor>(*It);
		const bool bRelic = Ruin && It->ActorHasTag(TEXT("SRRelic"));
		if (!bRelic && !(Ruin && It->ActorHasTag(TEXT("SRRuinTower")))) { continue; }
		bTagged = true;
		FSRRelic& R = Relics.AddDefaulted_GetRef();
		R.Pos = FVector2D(It->GetActorLocation());
		R.Z = It->GetActorLocation().Z;
		R.bRelic = bRelic;
		R.Ruins.Add(*It);
	}
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		const UStaticMeshComponent* Comp = It->GetStaticMeshComponent();
		const UStaticMesh* Mesh = Comp ? Comp->GetStaticMesh() : nullptr;
		if (!Mesh) { continue; }
		const FString MeshName = Mesh->GetName();
		if (MeshName.StartsWith(TEXT("SM_Menhir"))) { Stones.Add(*It); }
		// A level with no tagged ruin at all (the terraced map): they are known by their meshes, and by height. Any
		// SM_Ruin_Tower, and an SM_Dolmen on high ground; the high ones are the relics, the rest old towers.
		if (bTagged) { continue; }
		const bool bHigh = It->GetActorLocation().Z > 250.f;
		if (MeshName.StartsWith(TEXT("SM_Ruin_Tower")) || (bHigh && MeshName.StartsWith(TEXT("SM_Dolmen"))))
		{
			FSRRelic& R = Relics.AddDefaulted_GetRef();
			R.Pos = FVector2D(It->GetActorLocation());
			R.Z = It->GetActorLocation().Z;
			R.bRelic = bHigh;
			R.Ruins.Add(*It);
		}
	}
	// A relic looks like what it is: the ruin of a Relic Tower (SM_Bld_RelicTower_Ruin), in place of the level's broken
	// tower / stone circle there (those are hidden for good), so it reads apart from the plain old towers.
	UStaticMesh* RelicRuin = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/SR/Buildings/SM_Bld_RelicTower_Ruin.SM_Bld_RelicTower_Ruin"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	for (FSRRelic& R : Relics)
	{
		if (!R.bRelic) { continue; }
		for (AActor* S : Stones) { if (FVector2D::Distance(FVector2D(S->GetActorLocation()), R.Pos) < 600.f) { R.Ruins.AddUnique(S); } }
		for (AActor* S : Parts) { if (FVector2D::Distance(FVector2D(S->GetActorLocation()), R.Pos) < 900.f) { R.Ruins.AddUnique(S); } }
		if (!RelicRuin) { continue; }
		for (const TWeakObjectPtr<AActor>& Old : R.Ruins) { if (Old.IsValid()) { Old->SetActorHiddenInGame(true); } }
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		if (AStaticMeshActor* A = World->SpawnActor<AStaticMeshActor>(FVector(R.Pos, R.Z), FRotator::ZeroRotator, SP))
		{
			A->SetMobility(EComponentMobility::Movable);
			UStaticMeshComponent* C = A->GetStaticMeshComponent();
			C->SetStaticMesh(RelicRuin);
			C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			C->SetCustomPrimitiveDataVector4(0, FVector4(0.42f, 0.40f, 0.36f, 1.f));   // no kingdom's colour
			A->Tags.Add(TEXT("SRRelicRuin"));
			R.Ruins.Reset();
			R.Ruins.Add(A);
		}
	}

	RefreshNearWall(FIntPoint(0, 0), FIntPoint(Dim - 1, Dim - 1));

	int32 Blocked = 0, Water = 0;
	for (uint8 Fl : Flags) { Blocked += (Fl & FlagBlocked) ? 1 : 0; Water += (Fl & FlagWater) ? 1 : 0; }
	WaterCells = Water;
	int32 NumRelics = 0;
	for (const FSRRelic& R : Relics) { NumRelics += R.bRelic ? 1 : 0; }
	UE_LOG(LogSovereign, Log, TEXT("GRID built: %dx%d cells of %.0f cm, blocked %d (water %d under %d water sheet(s), steep edges %d), blocker boxes %d, veins %d, relics %d, old towers %d (%s), ground traced %.0f to %.0f, in %.0f ms"),
		Dim, Dim, Cell, Blocked, Water, WaterSheets.Num(), EdgeCells, Boxes, Veins.Num(), NumRelics, Relics.Num() - NumRelics, bTagged ? TEXT("by tag") : TEXT("by mesh name"),
		TraceTop, TraceBottom, (FPlatformTime::Seconds() - T0) * 1000.0);
}

void USRGridSubsystem::RefreshNearWall(const FIntPoint& Min, const FIntPoint& Max)
{
	for (int32 y = FMath::Max(Min.Y, 0); y <= FMath::Min(Max.Y, Dim - 1); ++y)
	{
		for (int32 x = FMath::Max(Min.X, 0); x <= FMath::Min(Max.X, Dim - 1); ++x)
		{
			const int32 I = y * Dim + x;
			Flags[I] &= ~FlagNearWall;
			if (Flags[I] & (FlagBlocked | FlagBuilding)) { continue; }
			for (const FIntPoint& D : Neighbours)
			{
				const FIntPoint C(x + D.X, y + D.Y);
				if (!InGrid(C) || (Flags[Idx(C)] & (FlagBlocked | FlagBuilding)) || FMath::Abs(Heights[Idx(C)] - Heights[I]) > USRFeelSettings::Get().StepHeight)
				{
					Flags[I] |= FlagNearWall;
					break;
				}
			}
		}
	}
}

// ---------------------------------------------------------------------------- cells

bool USRGridSubsystem::ToCell(const FVector2D& World, FIntPoint& Out) const
{
	if (Dim <= 0) { return false; }
	Out = FIntPoint(FMath::FloorToInt((World.X - Origin.X) / Cell), FMath::FloorToInt((World.Y - Origin.Y) / Cell));
	return InGrid(Out);
}

FIntPoint USRGridSubsystem::ToCellClamped(const FVector2D& World) const
{
	FIntPoint C(FMath::FloorToInt((World.X - Origin.X) / Cell), FMath::FloorToInt((World.Y - Origin.Y) / Cell));
	C.X = FMath::Clamp(C.X, 0, FMath::Max(Dim - 1, 0));
	C.Y = FMath::Clamp(C.Y, 0, FMath::Max(Dim - 1, 0));
	return C;
}

bool USRGridSubsystem::HeightAt(const FVector2D& World, float& OutZ) const
{
	FIntPoint C;
	if (!ToCell(World, C)) { return false; }
	OutZ = Heights[Idx(C)];
	return true;
}

bool USRGridSubsystem::CanStep(int32 From, int32 To) const
{
	if ((Flags[To] & (FlagBlocked | FlagBuilding)) != 0) { return false; }
	return FMath::Abs(Heights[To] - Heights[From]) <= USRFeelSettings::Get().StepHeight;
}

// ------------------------------------------------------------------------ buildings

void USRGridSubsystem::FootprintCells(const FVector& Location, const FVector2D& Min, const FVector2D& Max, FIntPoint& OutMin, FIntPoint& OutMax) const
{
	// Every cell the footprint reaches into (buildings are axis aligned: yaw 0): a cell with a wall in part of it is
	// not open ground. (A sliver under 5 cm is let go, so a footprint that ends on a cell border takes no extra row.)
	OutMin = ToCellClamped(FVector2D(Location.X + Min.X + 5.f, Location.Y + Min.Y + 5.f));
	OutMax = ToCellClamped(FVector2D(Location.X + Max.X - 5.f, Location.Y + Max.Y - 5.f));
}

void USRGridSubsystem::SetFootprint(const ASRBuilding* Building, bool bOccupy)
{
	if (!Building || Dim <= 0) { return; }
	FIntPoint Lo, Hi;
	FootprintCells(Building->GetActorLocation(), Building->FootprintMin, Building->FootprintMax, Lo, Hi);
	for (int32 y = Lo.Y; y <= Hi.Y; ++y)
	{
		for (int32 x = Lo.X; x <= Hi.X; ++x)
		{
			uint8& Fl = Flags[y * Dim + x];
			Fl = bOccupy ? (Fl | FlagBuilding) : (Fl & ~FlagBuilding);
		}
	}
	RefreshNearWall(Lo - FIntPoint(2, 2), Hi + FIntPoint(2, 2));
	bRegionsDirty = true;   // a building can wall a corner of the field off (and its fall opens it again)
	++Revision;

	// a tower standing on an old ruin (however it got there: placed, loaded, put down by a test) claims it: the ruin hides
	if (bOccupy && (Building->BuildingType == ESRBuildingType::RelicTower || Building->BuildingType == ESRBuildingType::Tower))
	{
		const int32 R = FindFreeRelic(Building->GetFootprintCentre(), 300.f, Building->BuildingType == ESRBuildingType::RelicTower);
		if (R != INDEX_NONE) { ClaimRelic(R, const_cast<ASRBuilding*>(Building)); }
	}

	if (Building->BuildingType == ESRBuildingType::Mine)
	{
		if (bOccupy)
		{
			const int32 V = FindFreeVein(Building->GetFootprintCentre(), 700.f);
			if (V != INDEX_NONE) { Veins[V].Mine = const_cast<ASRBuilding*>(Building); }
		}
		else
		{
			ReleaseVein(Building);
		}
	}
}

FSRPlacement USRGridSubsystem::CheckPlacement(ESRBuildingType Type, ESRTeam Team, const FVector2D& Want) const
{
	FSRPlacement Out;
	if (Dim <= 0) { Out.Reason = LOCTEXT("NoGrid", "The battlefield is not ready"); return Out; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRBuildingStats& S = F.BuildingStatsFor(Type);
	const FVector2D FootCentre = (S.FootprintMin + S.FootprintMax) * 0.5f;

	// farms, watchtowers and storehouses are limited by the castle's level
	if (const USREconomySubsystem* Eco = USREconomySubsystem::Get(this); Eco && Eco->IsAtBuildLimit(Type, Team))
	{
		Out.Reason = Eco->GetBuildLimitReason(Type, Team);
		return Out;
	}

	// Where the footprint's centre should go: the cursor, the vein a mine snaps onto, or the relic a Relic Tower stands on.
	FVector2D Centre = Want;
	if (Type == ESRBuildingType::RelicTower)
	{
		Out.RelicIndex = FindFreeRelic(Want, F.VeinSnapRadius * 1.5f, true);
		if (Out.RelicIndex == INDEX_NONE) { Out.Reason = LOCTEXT("NeedRelic", "A Relic Tower can only be raised on a relic: one of the ancient ruins"); }
		else { Centre = Relics[Out.RelicIndex].Pos; }
	}
	else if (Type == ESRBuildingType::Tower)
	{
		// near an old ruined tower: it is raised on it instead (snaps on, cheaper)
		Out.RelicIndex = FindFreeRelic(Want, 450.f, false);
		if (Out.RelicIndex != INDEX_NONE) { Centre = Relics[Out.RelicIndex].Pos; }
	}
	if (Type == ESRBuildingType::Mine)
	{
		Out.VeinIndex = FindFreeVein(Want, F.VeinSnapRadius);
		if (Out.VeinIndex == INDEX_NONE)
		{
			Out.Reason = LOCTEXT("NeedVein", "A mine must be built on a free gold vein");
		}
		else
		{
			Centre = Veins[Out.VeinIndex].Pos;
		}
	}

	// Snap: the footprint's min corner sits on a cell corner.
	const FVector2D WantMin = Centre - FootCentre + S.FootprintMin;
	const FVector2D SnappedMin = Origin + FVector2D(FMath::RoundToFloat((WantMin.X - Origin.X) / Cell), FMath::RoundToFloat((WantMin.Y - Origin.Y) / Cell)) * Cell;
	const FVector2D Loc2D = SnappedMin - S.FootprintMin;

	FIntPoint Lo, Hi;
	FootprintCells(FVector(Loc2D, 0.f), S.FootprintMin, S.FootprintMax, Lo, Hi);
	const int32 Gap = F.BuildingGapCells;

	float SumZ = 0.f, MinZ = TNumericLimits<float>::Max(), MaxZ = TNumericLimits<float>::Lowest();
	bool bAllOk = true, bBlocked = false, bWater = false, bTaken = false, bEdge = false, bCliff = false;
	for (int32 y = Lo.Y; y <= Hi.Y; ++y)
	{
		for (int32 x = Lo.X; x <= Hi.X; ++x)
		{
			const FIntPoint C(x, y);
			bool bOk = InGrid(C);
			if (bOk)
			{
				const uint8 Fl = Flags[Idx(C)];
				if (Fl & FlagWater) { bOk = false; bWater = true; }
				else if (Fl & FlagEdge) { bOk = false; bCliff = true; }
				else if ((Fl & FlagBlocked) && Out.RelicIndex == INDEX_NONE) { bOk = false; bBlocked = true; }   // (the ruin's own stones do not stop its tower)
				if (x < 3 || y < 3 || x >= Dim - 3 || y >= Dim - 3) { bOk = false; bEdge = true; }
				// buildings may not touch: keep Gap free cells all round
				for (int32 dy = -Gap; dy <= Gap && bOk; ++dy)
				{
					for (int32 dx = -Gap; dx <= Gap; ++dx)
					{
						const FIntPoint N(x + dx, y + dy);
						if (InGrid(N) && (Flags[Idx(N)] & FlagBuilding)) { bOk = false; bTaken = true; break; }
					}
				}
				const float Z = Heights[Idx(C)];
				SumZ += Z; MinZ = FMath::Min(MinZ, Z); MaxZ = FMath::Max(MaxZ, Z);
			}
			else
			{
				bEdge = true;
			}
			Out.Cells.Add(C);
			Out.CellOk.Add(bOk);
			bAllOk &= bOk;
		}
	}
	const bool bUneven = Out.Cells.Num() > 0 && MaxZ - MinZ > F.BuildFlatTolerance;
	if (bUneven)
	{
		// mark the cells furthest from the median height so the overlay shows where the ground breaks
		const float Mid = (MinZ + MaxZ) * 0.5f;
		for (int32 k = 0; k < Out.Cells.Num(); ++k)
		{
			if (InGrid(Out.Cells[k]) && FMath::Abs(Heights[Idx(Out.Cells[k])] - Mid) > F.BuildFlatTolerance * 0.5f) { Out.CellOk[k] = false; }
		}
	}
	const float Z = Out.Cells.Num() > 0 ? SumZ / Out.Cells.Num() : 0.f;
	Out.Location = FVector(Loc2D.X, Loc2D.Y, Z);

	// The building zone: inside the castle's reach a building raises itself; anywhere else a Builder has to go and
	// build it, so the kingdom must have one.
	bool bInTerritory = false;
	if (const USREconomySubsystem* Eco = USREconomySubsystem::Get(this))
	{
		bInTerritory = Eco->IsInBuildZone(Team, Loc2D + FootCentre);
		if (!bInTerritory)
		{
			const USRBattleSubsystem* B = USRBattleSubsystem::Get(this);
			Out.bNeedsBuilder = true;
			bInTerritory = B && B->CountBuilders(Team) > 0;
		}
	}

	// Enemy troops standing on the spot block it (your own just step aside when the foundations go down).
	bool bEnemyThere = false;
	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		for (const ASRUnit* U : Battle->GetUnits())
		{
			if (U && U->IsAlive() && U->GetTeam() != Team)
			{
				const FVector2D L = U->GetPos2D() - Loc2D;
				if (L.X > S.FootprintMin.X - 60.f && L.X < S.FootprintMax.X + 60.f && L.Y > S.FootprintMin.Y - 60.f && L.Y < S.FootprintMax.Y + 60.f) { bEnemyThere = true; break; }
			}
		}
	}

	if (!Out.Reason.IsEmpty()) {}
	else if (bEdge) { Out.Reason = LOCTEXT("Edge", "Too close to the edge of the realm"); }
	else if (bWater) { Out.Reason = LOCTEXT("Water", "Cannot build on water"); }
	else if (bTaken) { Out.Reason = LOCTEXT("Taken", "Too close to another building"); }
	else if (bBlocked) { Out.Reason = LOCTEXT("Blocked", "Rocks or trees are in the way"); }
	else if (bUneven || bCliff) { Out.Reason = LOCTEXT("Uneven", "The ground is too uneven"); }
	else if (!bInTerritory) { Out.Reason = LOCTEXT("Territory", "Outside the castle's reach: train a Builder at the castle to build out here"); }
	else if (bEnemyThere) { Out.Reason = LOCTEXT("Enemy", "Enemy troops are in the way"); }
	Out.bValid = Out.Reason.IsEmpty() && bAllOk && !bUneven;
	return Out;
}

bool USRGridSubsystem::FindPlacementNear(ESRBuildingType Type, ESRTeam Team, const FVector2D& Near, float MaxRadius, FSRPlacement& Out) const
{
	if (Type == ESRBuildingType::Mine)
	{
		// Mines: try the free veins, nearest first.
		TArray<int32> Order;
		for (int32 i = 0; i < Veins.Num(); ++i) { if (!Veins[i].Mine.IsValid() && FVector2D::Distance(Veins[i].Pos, Near) <= MaxRadius) { Order.Add(i); } }
		Order.Sort([&](int32 A, int32 B) { return FVector2D::DistSquared(Veins[A].Pos, Near) < FVector2D::DistSquared(Veins[B].Pos, Near); });
		for (int32 V : Order)
		{
			Out = CheckPlacement(Type, Team, Veins[V].Pos);
			if (Out.bValid) { return true; }
		}
		return false;
	}
	// Spiral out in rings of a couple of cells.
	const float Step = Cell * 2.f;
	for (float R = 0.f; R <= MaxRadius; R += Step)
	{
		const int32 Samples = R <= 0.f ? 1 : FMath::Max(8, FMath::CeilToInt(2.f * PI * R / Step));
		const float Phase = FMath::FRand() * 2.f * PI;
		for (int32 k = 0; k < Samples; ++k)
		{
			const float A = Phase + 2.f * PI * k / Samples;
			Out = CheckPlacement(Type, Team, Near + FVector2D(FMath::Cos(A), FMath::Sin(A)) * R);
			if (Out.bValid) { return true; }
		}
	}
	return false;
}

// ---------------------------------------------------------------------------- veins

int32 USRGridSubsystem::FindFreeVein(const FVector2D& Near, float Radius) const
{
	int32 Best = INDEX_NONE;
	float BestD = Radius * Radius;
	for (int32 i = 0; i < Veins.Num(); ++i)
	{
		if (Veins[i].Mine.IsValid()) { continue; }
		const float D = FVector2D::DistSquared(Veins[i].Pos, Near);
		if (D <= BestD) { BestD = D; Best = i; }
	}
	return Best;
}

void USRGridSubsystem::ClaimVein(int32 Index, ASRBuilding* Mine)
{
	if (Veins.IsValidIndex(Index)) { Veins[Index].Mine = Mine; }
}

void USRGridSubsystem::ReleaseVein(const ASRBuilding* Mine)
{
	for (FSRVein& V : Veins) { if (V.Mine.Get() == Mine) { V.Mine = nullptr; } }
}

// ---------------------------------------------------------------------------- relics

int32 USRGridSubsystem::FindFreeRuin(const FVector2D& Near, float Radius) const
{
	const int32 A = FindFreeRelic(Near, Radius, true), B = FindFreeRelic(Near, Radius, false);
	if (A == INDEX_NONE) { return B; }
	if (B == INDEX_NONE) { return A; }
	return FVector2D::DistSquared(Relics[A].Pos, Near) <= FVector2D::DistSquared(Relics[B].Pos, Near) ? A : B;
}

int32 USRGridSubsystem::FindFreeRelic(const FVector2D& Near, float Radius, bool bRelic) const
{
	int32 Best = INDEX_NONE;
	float BestD = Radius * Radius;
	for (int32 i = 0; i < Relics.Num(); ++i)
	{
		if (Relics[i].bRelic != bRelic || (Relics[i].Tower.IsValid() && Relics[i].Tower->IsAlive())) { continue; }
		const float D = FVector2D::DistSquared(Relics[i].Pos, Near);
		if (D <= BestD) { BestD = D; Best = i; }
	}
	return Best;
}

void USRGridSubsystem::ClaimRelic(int32 Index, ASRBuilding* Tower)
{
	if (!Relics.IsValidIndex(Index)) { return; }
	Relics[Index].Tower = Tower;
	for (const TWeakObjectPtr<AActor>& Ruin : Relics[Index].Ruins) { if (Ruin.IsValid()) { Ruin->SetActorHiddenInGame(true); } }
}

void USRGridSubsystem::ReleaseRelic(const ASRBuilding* Tower)
{
	for (FSRRelic& R : Relics)
	{
		if (R.Tower.Get() != Tower) { continue; }
		R.Tower = nullptr;
		for (const TWeakObjectPtr<AActor>& Ruin : R.Ruins) { if (Ruin.IsValid()) { Ruin->SetActorHiddenInGame(false); } }
	}
}


// -------------------------------------------------------------------- connected ground

void USRGridSubsystem::EnsureRegions() const
{
	if (!bRegionsDirty || Dim <= 0) { return; }
	bRegionsDirty = false;
	const int32 N = Dim * Dim;
	Regions.Init(0, N);
	RegionCount = 0;
	TArray<int32> Stack;
	Stack.Reserve(4096);
	// the same moves the search makes: eight ways, a step at most StepHeight tall, no cutting a corner
	for (int32 Seed = 0; Seed < N; ++Seed)
	{
		if (Regions[Seed] != 0 || (Flags[Seed] & (FlagBlocked | FlagBuilding))) { continue; }
		Regions[Seed] = ++RegionCount;
		Stack.Push(Seed);
		while (Stack.Num() > 0)
		{
			const int32 I = Stack.Pop(EAllowShrinking::No);
			const FIntPoint C = FromIdx(I);
			for (int32 n = 0; n < 8; ++n)
			{
				const FIntPoint NC = C + Neighbours[n];
				if (!InGrid(NC)) { continue; }
				const int32 J = Idx(NC);
				if (Regions[J] != 0 || !CanStep(I, J)) { continue; }
				if (n >= 4 && (!CanStep(I, Idx(FIntPoint(NC.X, C.Y))) || !CanStep(I, Idx(FIntPoint(C.X, NC.Y))))) { continue; }
				Regions[J] = RegionCount;
				Stack.Push(J);
			}
		}
	}
}

bool USRGridSubsystem::CanReach(const FVector2D& From, const FVector2D& To) const
{
	if (Dim <= 0) { return true; }
	EnsureRegions();
	FIntPoint A, B;
	bool bSnapped = false;
	if (!StartCell(From, A, bSnapped) || !StartCell(To, B, bSnapped)) { return false; }
	return Regions[Idx(A)] == Regions[Idx(B)];
}

// ---------------------------------------------------------------------------- paths

bool USRGridSubsystem::StartCell(const FVector2D& From, FIntPoint& OutCell, bool& bOutSnapped) const
{
	bOutSnapped = false;
	if (ToCell(From, OutCell) && IsWalkable(OutCell)) { return true; }
	bOutSnapped = true;
	return ToCell(NearestWalkable(From, 6), OutCell) && IsWalkable(OutCell);
}

FVector2D USRGridSubsystem::NearestWalkable(const FVector2D& P, int32 MaxRing, const FVector2D* ReachableFrom) const
{
	if (Dim <= 0) { return P; }
	// Only ground the walker can get to counts, when we are told where it stands.
	int32 Region = 0;
	if (ReachableFrom)
	{
		EnsureRegions();
		FIntPoint F;
		bool bSnapped = false;
		if (StartCell(*ReachableFrom, F, bSnapped)) { Region = Regions[Idx(F)]; }
	}
	auto Fits = [&](const FIntPoint& N) { return IsWalkable(N) && (Region == 0 || Regions[Idx(N)] == Region); };

	FIntPoint C;
	if (ToCell(P, C) && Fits(C)) { return P; }
	C = ToCellClamped(P);
	// Nearest fitting cell, ring by ring; one hard against a wall loses to an open one a little farther off (so the
	// search looks one ring past the first it finds).
	const float WallCost = FMath::Square(Cell * 1.5f);
	float BestScore = TNumericLimits<float>::Max();
	FIntPoint Best(-1, -1);
	int32 Last = MaxRing;
	for (int32 R = 1; R <= Last; ++R)
	{
		for (int32 dy = -R; dy <= R; ++dy)
		{
			for (int32 dx = -R; dx <= R; ++dx)
			{
				if (FMath::Max(FMath::Abs(dx), FMath::Abs(dy)) != R) { continue; }
				const FIntPoint N(C.X + dx, C.Y + dy);
				if (!Fits(N)) { continue; }
				const float Score = FVector2D::DistSquared(CellCentre(N), P) + ((Flags[Idx(N)] & FlagNearWall) ? WallCost : 0.f);
				if (Score < BestScore) { BestScore = Score; Best = N; }
			}
		}
		if (Best.X >= 0 && Last == MaxRing) { Last = FMath::Min(MaxRing, R + 1); }
	}
	return Best.X >= 0 ? CellCentre(Best) : P;
}

bool USRGridSubsystem::WalkLine(const FVector2D& A, const FVector2D& B, ELineRule Rule) const
{
	FIntPoint C, End;
	if (!ToCell(A, C) || !ToCell(B, End)) { return false; }
	const FIntPoint Start = C;
	const float StepH = USRFeelSettings::Get().StepHeight;
	auto Open = [&](const FIntPoint& P)
	{
		const uint8 Fl = Flags[Idx(P)];
		if (Fl & (FlagBlocked | FlagBuilding)) { return false; }
		if (!(Fl & FlagNearWall) || Rule == ELineRule::Any) { return true; }
		if (Rule == ELineRule::Route) { return RouteMark[Idx(P)] == RouteStamp; }
		// Clear: hard against a wall only where the line starts and ends (a walker beside a building, a goal at its door)
		return FMath::Max(FMath::Abs(P.X - Start.X), FMath::Abs(P.Y - Start.Y)) <= 1 || FMath::Max(FMath::Abs(P.X - End.X), FMath::Abs(P.Y - End.Y)) <= 1;
	};
	auto Steps = [&](const FIntPoint& From, const FIntPoint& To) { return FMath::Abs(Heights[Idx(To)] - Heights[Idx(From)]) <= StepH; };

	// Every cell the segment passes through, in order (a grid walk: at each move the nearer of the next vertical and
	// horizontal cell border). The walker's own cell is forgiven: it may be standing on the edge of something.
	const FVector2D D = B - A;
	const int32 Sx = D.X >= 0.f ? 1 : -1, Sy = D.Y >= 0.f ? 1 : -1;
	const float Far = TNumericLimits<float>::Max();
	const float TDx = FMath::Abs(D.X) > KINDA_SMALL_NUMBER ? Cell / FMath::Abs(float(D.X)) : Far;
	const float TDy = FMath::Abs(D.Y) > KINDA_SMALL_NUMBER ? Cell / FMath::Abs(float(D.Y)) : Far;
	float TX = TDx < Far ? float(((Origin.X + (C.X + (Sx > 0 ? 1 : 0)) * Cell) - A.X) / D.X) : Far;
	float TY = TDy < Far ? float(((Origin.Y + (C.Y + (Sy > 0 ? 1 : 0)) * Cell) - A.Y) / D.Y) : Far;
	for (int32 Guard = Dim * 4; C != End && Guard > 0; --Guard)
	{
		if (FMath::Min(TX, TY) > 1.f + 1e-3f) { break; }   // past B: rounding kept us out of its cell
		const FIntPoint Prev = C;
		if (FMath::Abs(TX - TY) < 1e-4f)
		{
			// exactly through a corner: the two cells beside it must be open as well (no squeezing between two walls)
			const FIntPoint S1(C.X + Sx, C.Y), S2(C.X, C.Y + Sy);
			if (!InGrid(S1) || !InGrid(S2) || !Open(S1) || !Open(S2) || !Steps(Prev, S1) || !Steps(Prev, S2)) { return false; }
			C.X += Sx; C.Y += Sy; TX += TDx; TY += TDy;
		}
		else if (TX < TY) { C.X += Sx; TX += TDx; }
		else { C.Y += Sy; TY += TDy; }
		if (!InGrid(C) || !Open(C) || !Steps(Prev, C)) { return false; }
	}
	return C == End;
}

bool USRGridSubsystem::CanWalkStraight(const FVector2D& A, const FVector2D& B) const
{
	return Dim <= 0 || WalkLine(A, B, ELineRule::Clear);
}

bool USRGridSubsystem::Flood(TConstArrayView<FIntPoint> Goals, const TArray<FIntPoint>& Starts)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	++Stamp;
	if (Stamp == 0) { FMemory::Memzero(Seen.GetData(), Seen.Num() * sizeof(uint32)); Stamp = 1; }

	// A* toward the starts' bounding box (admissible for every start), expanding from the goal cells.
	FIntPoint BMin(MAX_int32, MAX_int32), BMax(MIN_int32, MIN_int32);
	for (const FIntPoint& S : Starts) { BMin = BMin.ComponentMin(S); BMax = BMax.ComponentMax(S); }
	auto H = [&](int32 I)
	{
		const FIntPoint C = FromIdx(I);
		const int32 Dx = FMath::Max3(BMin.X - C.X, 0, C.X - BMax.X);
		const int32 Dy = FMath::Max3(BMin.Y - C.Y, 0, C.Y - BMax.Y);
		return float(FMath::Max(Dx, Dy)) + (Diag - 1.f) * float(FMath::Min(Dx, Dy));
	};

	TSet<int32> Remaining;
	for (const FIntPoint& S : Starts) { Remaining.Add(Idx(S)); }

	TArray<FOpen> Open;
	Open.Reserve(4096);
	for (const FIntPoint& Goal : Goals)
	{
		const int32 G = Idx(Goal);
		Seen[G] = Stamp;
		Cost[G] = 0.f;
		Next[G] = INDEX_NONE;
		Open.HeapPush({ H(G), G }, FOpenLess());
	}
	int32 Settled = 0;
	const int32 Budget = Dim * Dim;

	while (Open.Num() > 0 && Settled < Budget)
	{
		FOpen Top;
		Open.HeapPop(Top, FOpenLess());
		const int32 I = Top.I;
		const float GCost = Cost[I];
		if (Top.F > GCost + H(I) + 1e-3f) { continue; } // stale entry
		++Settled;
		Remaining.Remove(I);
		if (Remaining.Num() == 0) { return true; }

		const FIntPoint C = FromIdx(I);
		const float Here = (Flags[I] & FlagNearWall) ? 1.f + F.PathWallPenalty : 1.f;
		for (int32 n = 0; n < 8; ++n)
		{
			const FIntPoint NC = C + Neighbours[n];
			if (!InGrid(NC)) { continue; }
			const int32 J = Idx(NC);
			if (!CanStep(I, J)) { continue; }
			if (n >= 4)
			{
				// no corner cutting: both orthogonal neighbours must be steppable too
				if (!CanStep(I, Idx(FIntPoint(C.X + Neighbours[n].X, C.Y))) || !CanStep(I, Idx(FIntPoint(C.X, C.Y + Neighbours[n].Y)))) { continue; }
			}
			const float There = (Flags[J] & FlagNearWall) ? 1.f + F.PathWallPenalty : 1.f;
			const float NewCost = GCost + (n >= 4 ? Diag : 1.f) * 0.5f * (Here + There);
			if (Seen[J] != Stamp || NewCost < Cost[J])
			{
				Seen[J] = Stamp;
				Cost[J] = NewCost;
				Next[J] = I;           // toward the goal
				Open.HeapPush({ NewCost + H(J), J }, FOpenLess());
			}
		}
	}
	return Remaining.Num() == 0;
}

void USRGridSubsystem::StringPull(const TArray<FIntPoint>& Cells, TArray<FVector2D>& Out)
{
	// Cells run start -> goal. Keep only the corners: from each anchor, go as far along as a straight walk allows.
	// The straight walk stays out of cells hard against a wall, except the ones the search itself went through (a
	// gap, a doorway, the lip of a ramp): the search paid to keep its distance, and straightening must not give it
	// back. That is what stops a route round a hill from being pulled tight against its cliff.
	if (Cells.Num() == 0) { return; }
	if (++RouteStamp == 0) { FMemory::Memzero(RouteMark.GetData(), RouteMark.Num() * sizeof(uint32)); RouteStamp = 1; }
	for (const FIntPoint& C : Cells) { RouteMark[Idx(C)] = RouteStamp; }
	int32 Anchor = 0;
	FVector2D AnchorPos = CellCentre(Cells[0]);
	while (Anchor < Cells.Num() - 1)
	{
		int32 Far = Anchor + 1;
		for (int32 k = Anchor + 2; k < Cells.Num(); ++k)
		{
			if (WalkLine(AnchorPos, CellCentre(Cells[k]), ELineRule::Route)) { Far = k; }
			else if (k - Far > 6) { break; } // well past the last visible cell: stop looking
		}
		Out.Add(CellCentre(Cells[Far]));
		Anchor = Far;
		AnchorPos = CellCentre(Cells[Far]);
	}
}

bool USRGridSubsystem::FindGroupPaths(const TArray<FVector2D>& Starts, const FVector2D& Goal, TArray<TArray<FVector2D>>& OutPaths, TArray<FVector2D>* OutGoals)
{
	OutPaths.SetNum(Starts.Num());
	for (TArray<FVector2D>& P : OutPaths) { P.Reset(); }
	if (OutGoals) { OutGoals->Init(Goal, Starts.Num()); }
	if (Dim <= 0 || Starts.Num() == 0) { return true; }
	const double T0 = FPlatformTime::Seconds();
	EnsureRegions();

	FIntPoint GoalCell;
	const FVector2D G = NearestWalkable(Goal);
	if (!ToCell(G, GoalCell) || !IsWalkable(GoalCell)) { return false; }
	const int32 GoalRegion = Regions[Idx(GoalCell)];
	if (OutGoals) { OutGoals->Init(G, Starts.Num()); }

	// Walkers that can see the goal in a straight line need no search. The rest are sorted by the ground they stand
	// on: those on the goal's ground share one search; a walker cut off from it (across the river, down a ledge)
	// is routed to the nearest point its own ground comes to the goal, instead of walking at the cliff.
	struct FWalker { int32 Index; FIntPoint Cell; bool bSnapped; };
	TMap<int32, TArray<FWalker>> ByRegion;
	int32 Searched = 0;
	for (int32 i = 0; i < Starts.Num(); ++i)
	{
		FWalker W{ i, FIntPoint(0, 0), false };
		if (!StartCell(Starts[i], W.Cell, W.bSnapped))
		{
			if (OutGoals) { (*OutGoals)[i] = Starts[i]; }   // walled in: it stays
			continue;
		}
		const int32 Region = Regions[Idx(W.Cell)];
		if (Region == GoalRegion && !W.bSnapped && WalkLine(Starts[i], G, ELineRule::Clear)) { continue; }
		ByRegion.FindOrAdd(Region).Add(W);
		++Searched;
	}

	bool bAny = Searched < Starts.Num(), bAll = true;
	TArray<FIntPoint> StartCells, Chain;
	for (const TPair<int32, TArray<FWalker>>& Pair : ByRegion)
	{
		FIntPoint To = GoalCell;
		FVector2D ToPos = G;
		if (Pair.Key != GoalRegion)
		{
			const FVector2D From = CellCentre(Pair.Value[0].Cell);
			ToPos = NearestWalkable(Goal, 60, &From);
			const bool bFound = ToCell(ToPos, To) && IsWalkable(To) && Regions[Idx(To)] == Pair.Key;
			for (const FWalker& W : Pair.Value) { if (OutGoals) { (*OutGoals)[W.Index] = bFound ? ToPos : Starts[W.Index]; } }
			bAll = false;
			if (!bFound) { continue; }
		}
		StartCells.Reset();
		for (const FWalker& W : Pair.Value) { StartCells.Add(W.Cell); }
		Flood(MakeArrayView(&To, 1), StartCells);
		for (const FWalker& W : Pair.Value)
		{
			const int32 I0 = Idx(W.Cell);
			if (Seen[I0] != Stamp) { bAll = false; continue; }
			Chain.Reset();
			for (int32 I = I0; I != INDEX_NONE && Chain.Num() < Dim * 4; I = Next[I]) { Chain.Add(FromIdx(I)); }
			TArray<FVector2D>& Path = OutPaths[W.Index];
			StringPull(Chain, Path);
			if (Path.Num() > 0) { Path.Pop(); } // the goal cell's centre: the caller appends the exact slot instead
			if (W.bSnapped) { Path.Insert(CellCentre(W.Cell), 0); }   // out of the wall it stands in first
			bAny = true;
			if (USRFeelSettings::Get().bDebugDrawPaths)
			{
				TArray<FVector2D> D = Path;
				D.Insert(Starts[W.Index], 0);
				D.Add(ToPos);
				DebugPaths.Add(D);
				if (DebugPaths.Num() > 40) { DebugPaths.RemoveAt(0); }
			}
		}
	}
	UE_LOG(LogSovereign, Verbose, TEXT("PATH group of %d (%d searched) in %.2f ms%s"), Starts.Num(), Searched,
		(FPlatformTime::Seconds() - T0) * 1000.0, bAll ? TEXT("") : TEXT(" (some walkers cut off from the goal)"));
	return bAny;
}

bool USRGridSubsystem::FindPath(const FVector2D& From, const FVector2D& Goal, TArray<FVector2D>& OutPath)
{
	TArray<TArray<FVector2D>> Paths;
	TArray<FVector2D> Goals;
	const bool bOk = FindGroupPaths({ From }, Goal, Paths, &Goals);
	OutPath = Paths.Num() > 0 ? Paths[0] : TArray<FVector2D>();
	// the exact spot asked for when it is open ground the walker can get to, otherwise the nearest such ground
	OutPath.Add(Goals.Num() > 0 ? Goals[0] : Goal);
	return bOk;
}

bool USRGridSubsystem::FindPathToBuilding(const FVector2D& From, const ASRBuilding* Building, float Standoff, TArray<FVector2D>& OutPath)
{
	OutPath.Reset();
	if (!Building) { return false; }
	const FVector2D Near = Building->ClosestPointOnFootprint(From, Standoff);
	if (Dim <= 0) { OutPath.Add(Near); return true; }
	EnsureRegions();

	FIntPoint Start;
	bool bSnapped = false;
	if (!StartCell(From, Start, bSnapped)) { OutPath.Add(Near); return false; }
	const int32 Region = Regions[Idx(Start)];

	// The free cells round its walls that this walker's ground reaches.
	FIntPoint Lo, Hi;
	FootprintCells(Building->GetActorLocation(), Building->FootprintMin, Building->FootprintMax, Lo, Hi);
	TArray<FIntPoint> Ring;
	for (int32 y = Lo.Y - 1; y <= Hi.Y + 1; ++y)
	{
		for (int32 x = Lo.X - 1; x <= Hi.X + 1; ++x)
		{
			if (x >= Lo.X && x <= Hi.X && y >= Lo.Y && y <= Hi.Y) { continue; }
			const FIntPoint C(x, y);
			if (IsWalkable(C) && Regions[Idx(C)] == Region) { Ring.Add(C); }
		}
	}
	if (Ring.Num() == 0)
	{
		// no side of it can be walked to from here: as near as this ground comes
		FindPath(From, Near, OutPath);
		return false;
	}
	FIntPoint EndCell = Start;
	if (!Ring.Contains(Start))
	{
		Flood(Ring, { Start });
		if (Seen[Idx(Start)] != Stamp) { FindPath(From, Near, OutPath); return false; }
		TArray<FIntPoint> Chain;
		for (int32 I = Idx(Start); I != INDEX_NONE && Chain.Num() < Dim * 4; I = Next[I]) { Chain.Add(FromIdx(I)); }
		StringPull(Chain, OutPath);
		EndCell = Chain.Last();
	}
	if (bSnapped) { OutPath.Insert(CellCentre(Start), 0); }
	// from the cell beside the wall, up to the wall itself
	OutPath.Add(Building->ClosestPointOnFootprint(CellCentre(EndCell), Standoff));
	if (USRFeelSettings::Get().bDebugDrawPaths)
	{
		TArray<FVector2D> D = OutPath;
		D.Insert(From, 0);
		DebugPaths.Add(D);
		if (DebugPaths.Num() > 40) { DebugPaths.RemoveAt(0); }
	}
	return true;
}

void USRGridSubsystem::FitSlots(const FVector2D& Goal, TArray<FVector2D>& Slots) const
{
	FIntPoint GC;
	if (Dim <= 0 || Slots.Num() == 0 || !ToCell(Goal, GC) || !IsWalkable(GC)) { return; }

	// Ground that can be walked to from the goal without leaving the formation's neighbourhood.
	float Reach = 0.f;
	for (const FVector2D& S : Slots) { Reach = FMath::Max(Reach, float(FMath::Max(FMath::Abs(S.X - Goal.X), FMath::Abs(S.Y - Goal.Y)))); }
	const int32 R = FMath::Clamp(FMath::CeilToInt(Reach / Cell) + 4, 6, 48);
	const int32 W = 2 * R + 1;
	TBitArray<> Near(false, W * W);
	auto Local = [&](const FIntPoint& C) { return (C.Y - GC.Y + R) * W + (C.X - GC.X + R); };
	auto Inside = [&](const FIntPoint& C) { return FMath::Abs(C.X - GC.X) <= R && FMath::Abs(C.Y - GC.Y) <= R && InGrid(C); };
	TArray<FIntPoint> Front;
	Front.Add(GC);
	Near[Local(GC)] = true;
	for (int32 Head = 0; Head < Front.Num(); ++Head)
	{
		const FIntPoint C = Front[Head];
		const int32 I = Idx(C);
		for (int32 n = 0; n < 8; ++n)
		{
			const FIntPoint NC = C + Neighbours[n];
			if (!Inside(NC) || Near[Local(NC)] || !CanStep(I, Idx(NC))) { continue; }
			if (n >= 4 && (!CanStep(I, Idx(FIntPoint(NC.X, C.Y))) || !CanStep(I, Idx(FIntPoint(C.X, NC.Y))))) { continue; }
			Near[Local(NC)] = true;
			Front.Add(NC);
		}
	}

	TSet<int32> Taken;   // two displaced slots do not land on one cell while there is room
	for (FVector2D& S : Slots)
	{
		const FIntPoint SC = ToCellClamped(S);
		if (Inside(SC) && Near[Local(SC)]) { Taken.Add(Idx(SC)); continue; }
		float BestScore = TNumericLimits<float>::Max();
		FIntPoint Best(-1, -1);
		for (int32 Ring = 1; Ring <= 10 && Best.X < 0; ++Ring)
		{
			for (int32 dy = -Ring; dy <= Ring; ++dy)
			{
				for (int32 dx = -Ring; dx <= Ring; ++dx)
				{
					if (FMath::Max(FMath::Abs(dx), FMath::Abs(dy)) != Ring) { continue; }
					const FIntPoint N(SC.X + dx, SC.Y + dy);
					if (!Inside(N) || !Near[Local(N)]) { continue; }
					const float Score = FVector2D::DistSquared(CellCentre(N), S) + (Taken.Contains(Idx(N)) ? FMath::Square(Cell * 3.f) : 0.f)
						+ ((Flags[Idx(N)] & FlagNearWall) ? FMath::Square(Cell) : 0.f);
					if (Score < BestScore) { BestScore = Score; Best = N; }
				}
			}
		}
		if (Best.X >= 0) { S = CellCentre(Best); Taken.Add(Idx(Best)); }
		else { S = Goal; }
	}
}

// ---------------------------------------------------------------------------- checks

void USRGridSubsystem::LogSelfCheck() const
{
	if (Dim <= 0) { return; }
	EnsureRegions();
	TArray<int32> Size;
	Size.Init(0, RegionCount + 1);
	int32 Open = 0;
	for (int32 R : Regions) { if (R > 0) { ++Size[R]; ++Open; } }
	int32 Main = 0;
	for (int32 r = 1; r <= RegionCount; ++r) { if (Size[r] > Size[Main] || Main == 0) { Main = r; } }
	UE_LOG(LogSovereign, Log, TEXT("GRID check: %d open cells in %d separate pieces of ground; the main one holds %.1f%% (%d cells cut off from it)"),
		Open, RegionCount, Open > 0 ? 100.f * Size[Main] / Open : 0.f, Open - (RegionCount > 0 ? Size[Main] : 0));
	UE_LOG(LogSovereign, Log, TEXT("GRID check: %d cells of deep water (%s), %d cells of steep ground, of %d"), WaterCells,
		bWaterSheets ? TEXT("by depth under the water sheets") : TEXT("no water sheets: ground under the old water line"), EdgeCells, Dim * Dim);

	// each castle's gate, and each vein's mine site, against the main ground
	int32 Bad = 0;
	int32 Home = 0;   // the ground the player's castle gate stands on (the relics and old towers are checked against it)
	if (const USREconomySubsystem* Eco = USREconomySubsystem::Get(this))
	{
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (!B || !B->IsCastle()) { continue; }
			const FVector Gate = B->GetGatePoint();
			FIntPoint C;
			bool bSnapped = false;
			const bool bFound = StartCell(FVector2D(Gate.X, Gate.Y), C, bSnapped);
			const bool bOk = bFound && Regions[Idx(C)] == Main;
			if (bFound && B->Team == ESRTeam::Player) { Home = Regions[Idx(C)]; }
			Bad += bOk ? 0 : 1;
			UE_LOG(LogSovereign, Log, TEXT("GRID check: %s castle gate (%.0f, %.0f): %s"), B->Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"), Gate.X, Gate.Y,
				bOk ? TEXT("on the main ground") : TEXT("CUT OFF"));
		}
	}
	const FSRBuildingStats& Mine = USRFeelSettings::Get().BuildingStatsFor(ESRBuildingType::Mine);
	for (int32 v = 0; v < Veins.Num(); ++v)
	{
		// the cells round a mine standing on it: at least one must be on the main ground
		const FVector2D Min = Veins[v].Pos - (Mine.FootprintMin + Mine.FootprintMax) * 0.5f + Mine.FootprintMin;
		const FVector2D Snapped = Origin + FVector2D(FMath::RoundToFloat((Min.X - Origin.X) / Cell), FMath::RoundToFloat((Min.Y - Origin.Y) / Cell)) * Cell;
		FIntPoint Lo, Hi;
		FootprintCells(FVector(Snapped - Mine.FootprintMin, 0.f), Mine.FootprintMin, Mine.FootprintMax, Lo, Hi);
		int32 Ring = 0, Reachable = 0;
		for (int32 y = Lo.Y - 1; y <= Hi.Y + 1; ++y)
		{
			for (int32 x = Lo.X - 1; x <= Hi.X + 1; ++x)
			{
				if (x >= Lo.X && x <= Hi.X && y >= Lo.Y && y <= Hi.Y) { continue; }
				const FIntPoint C(x, y);
				++Ring;
				Reachable += (InGrid(C) && Regions[Idx(C)] == Main) ? 1 : 0;
			}
		}
		Bad += Reachable > 0 ? 0 : 1;
		UE_LOG(LogSovereign, Log, TEXT("GRID check: vein %2d (%6.0f, %6.0f) z %3.0f: %s (%d of the %d cells round a mine there)"), v, Veins[v].Pos.X, Veins[v].Pos.Y, Veins[v].Z,
			Reachable > 0 ? TEXT("reachable") : TEXT("CUT OFF"), Reachable, Ring);
	}
	// each relic and old tower: some open ground within about 6 m of it that the player's troops can walk to from
	// their castle gate (a Builder has to get there to raise the tower)
	if (Home == 0) { Home = Main; }
	const int32 Reach = FMath::CeilToInt(600.f / Cell);
	for (int32 r = 0; r < Relics.Num(); ++r)
	{
		const FIntPoint At = ToCellClamped(Relics[r].Pos);
		int32 Near = 0;
		for (int32 y = At.Y - Reach; y <= At.Y + Reach; ++y)
		{
			for (int32 x = At.X - Reach; x <= At.X + Reach; ++x)
			{
				const FIntPoint C(x, y);
				if (InGrid(C) && Regions[Idx(C)] == Home && FVector2D::DistSquared(CellCentre(C), Relics[r].Pos) <= FMath::Square(600.f)) { ++Near; }
			}
		}
		Bad += Near > 0 ? 0 : 1;
		UE_LOG(LogSovereign, Log, TEXT("GRID check: %s %2d (%6.0f, %6.0f) z %4.0f: %s (%d cells within 6 m on the player's ground)"), Relics[r].bRelic ? TEXT("relic    ") : TEXT("old tower"),
			r, Relics[r].Pos.X, Relics[r].Pos.Y, Relics[r].Z, Near > 0 ? TEXT("reachable") : TEXT("CUT OFF"), Near);
	}
	if (Bad > 0) { UE_LOG(LogSovereign, Warning, TEXT("GRID check: %d place(s) cannot be walked to; troops sent there will stop short"), Bad); }
}

void USRGridSubsystem::DebugDraw() const
{
	const UWorld* World = GetWorld();
	if (!World || Dim <= 0) { return; }
	for (const TArray<FVector2D>& P : DebugPaths)
	{
		for (int32 k = 1; k < P.Num(); ++k)
		{
			float Za = 0.f, Zb = 0.f;
			HeightAt(P[k - 1], Za);
			HeightAt(P[k], Zb);
			DrawDebugLine(World, FVector(P[k - 1], Za + 40.f), FVector(P[k], Zb + 40.f), FColor::Cyan, false, -1.f, 0, 8.f);
		}
	}
	// the cells round the camera: red = a cliff or bank cuts through it, orange = other blocked, yellow = hard against a wall
	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		const FIntPoint Mid = ToCellClamped(Battle->GetSpriteView().FocusXY);
		for (int32 y = FMath::Max(Mid.Y - 34, 0); y <= FMath::Min(Mid.Y + 34, Dim - 1); ++y)
		{
			for (int32 x = FMath::Max(Mid.X - 34, 0); x <= FMath::Min(Mid.X + 34, Dim - 1); ++x)
			{
				const uint8 Fl = Flags[y * Dim + x];
				if (!(Fl & (FlagBlocked | FlagBuilding | FlagNearWall)) || (Fl & FlagWater)) { continue; }
				const FVector2D P = CellCentre(FIntPoint(x, y));
				const FColor Col = (Fl & FlagEdge) ? FColor::Red : ((Fl & (FlagBlocked | FlagBuilding)) ? FColor::Orange : FColor::Yellow);
				DrawDebugPoint(World, FVector(P.X, P.Y, Heights[y * Dim + x] + 30.f), (Fl & FlagNearWall) ? 5.f : 9.f, Col, false, -1.f);
			}
		}
	}
}

#undef LOCTEXT_NAMESPACE
