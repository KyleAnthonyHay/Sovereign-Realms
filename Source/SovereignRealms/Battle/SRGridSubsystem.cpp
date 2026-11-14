// Copyright Sovereign Realms.

#include "Battle/SRGridSubsystem.h"
#include "Battle/SREconomySubsystem.h"
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
	Veins.Reset();

	// Ground: one downward trace per cell against the terrain. Buildings and the hidden blocker boxes are left out;
	// they are footprints / obstacles, not ground.
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SRGridGround), false);
	TArray<const AActor*> BlockerActors;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->IsA<ASRBuilding>() || It->ActorHasTag(TEXT("SRBlocker"))) { Params.AddIgnoredActor(*It); }
		if (It->ActorHasTag(TEXT("SRBlocker"))) { BlockerActors.Add(*It); }
	}
	const FCollisionObjectQueryParams Objects(ECC_WorldStatic);
	for (int32 y = 0; y < Dim; ++y)
	{
		for (int32 x = 0; x < Dim; ++x)
		{
			const FVector2D P = CellCentre(FIntPoint(x, y));
			FHitResult Hit;
			const int32 I = y * Dim + x;
			if (World->LineTraceSingleByObjectType(Hit, FVector(P.X, P.Y, 8000.f), FVector(P.X, P.Y, -2000.f), Objects, Params))
			{
				Heights[I] = Hit.ImpactPoint.Z;
				if (Hit.ImpactPoint.Z < -30.f) { Flags[I] |= FlagWater | FlagBlocked; }
			}
			else
			{
				Flags[I] |= FlagBlocked;
			}
		}
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

	RefreshNearWall(FIntPoint(0, 0), FIntPoint(Dim - 1, Dim - 1));

	int32 Blocked = 0, Water = 0;
	for (uint8 Fl : Flags) { Blocked += (Fl & FlagBlocked) ? 1 : 0; Water += (Fl & FlagWater) ? 1 : 0; }
	UE_LOG(LogSovereign, Log, TEXT("GRID built: %dx%d cells of %.0f cm, blocked %d (water %d), blocker boxes %d, veins %d, in %.0f ms"),
		Dim, Dim, Cell, Blocked, Water, Boxes, Veins.Num(), (FPlatformTime::Seconds() - T0) * 1000.0);
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
	// Cells whose centres lie inside the footprint (buildings are axis aligned: yaw 0).
	OutMin = ToCellClamped(FVector2D(Location.X + Min.X + Cell * 0.5f, Location.Y + Min.Y + Cell * 0.5f));
	OutMax = ToCellClamped(FVector2D(Location.X + Max.X - Cell * 0.5f, Location.Y + Max.Y - Cell * 0.5f));
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

	// Where the footprint's centre should go: the cursor, or the vein a mine snaps onto.
	FVector2D Centre = Want;
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
	bool bAllOk = true, bBlocked = false, bWater = false, bTaken = false, bEdge = false;
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
				else if (Fl & FlagBlocked) { bOk = false; bBlocked = true; }
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

	// Territory: within reach of one of the kingdom's finished buildings (mines go on any free vein).
	bool bInTerritory = Type == ESRBuildingType::Mine;
	if (!bInTerritory)
	{
		if (const USREconomySubsystem* Eco = USREconomySubsystem::Get(this))
		{
			const FVector2D Mid = Loc2D + FootCentre;
			for (const ASRBuilding* B : Eco->GetBuildings())
			{
				if (B && B->Team == Team && B->IsFinished() && B->IsAlive())
				{
					const float R = F.BuildingStatsFor(B->BuildingType).TerritoryRadius;
					if (R > 0.f && FVector2D::Distance(B->GetFootprintCentre(), Mid) <= R) { bInTerritory = true; break; }
				}
			}
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
	else if (bUneven) { Out.Reason = LOCTEXT("Uneven", "The ground is too uneven"); }
	else if (!bInTerritory) { Out.Reason = LOCTEXT("Territory", "Too far from your kingdom: build near your castle, farms or mines"); }
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

// ---------------------------------------------------------------------------- paths

FVector2D USRGridSubsystem::NearestWalkable(const FVector2D& P, int32 MaxRing) const
{
	FIntPoint C;
	if (Dim <= 0) { return P; }
	if (ToCell(P, C) && IsWalkable(C)) { return P; }
	C = ToCellClamped(P);
	for (int32 R = 1; R <= MaxRing; ++R)
	{
		float BestD = TNumericLimits<float>::Max();
		FIntPoint Best(-1, -1);
		for (int32 dy = -R; dy <= R; ++dy)
		{
			for (int32 dx = -R; dx <= R; ++dx)
			{
				if (FMath::Max(FMath::Abs(dx), FMath::Abs(dy)) != R) { continue; }
				const FIntPoint N(C.X + dx, C.Y + dy);
				if (!IsWalkable(N) || (Flags[Idx(N)] & FlagNearWall)) { continue; }
				const float D = FVector2D::DistSquared(CellCentre(N), P);
				if (D < BestD) { BestD = D; Best = N; }
			}
		}
		if (Best.X >= 0) { return CellCentre(Best); }
	}
	return P;
}

bool USRGridSubsystem::CanWalkStraight(const FVector2D& A, const FVector2D& B) const
{
	if (Dim <= 0) { return true; }
	const float Len = FVector2D::Distance(A, B);
	const int32 Steps = FMath::Max(1, FMath::CeilToInt(Len / (Cell * 0.4f)));
	const float StepH = USRFeelSettings::Get().StepHeight;
	FIntPoint Prev(-1, -1);
	for (int32 k = 0; k <= Steps; ++k)
	{
		FIntPoint C;
		if (!ToCell(FMath::Lerp(A, B, float(k) / Steps), C)) { return false; }
		if (C == Prev) { continue; }
		if (!IsWalkable(C))
		{
			// The walker may be standing on the edge of a blocked cell; only its own first cell is forgiven.
			if (k > 0) { return false; }
		}
		if (Prev.X >= 0 && FMath::Abs(Heights[Idx(C)] - Heights[Idx(Prev)]) > StepH) { return false; }
		Prev = C;
	}
	return true;
}

bool USRGridSubsystem::Flood(const FIntPoint& Goal, const TArray<FIntPoint>& Starts)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	++Stamp;
	if (Stamp == 0) { FMemory::Memzero(Seen.GetData(), Seen.Num() * sizeof(uint32)); Stamp = 1; }

	// A* toward the starts' bounding box (admissible for every start), expanding from the goal.
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
	const int32 G = Idx(Goal);
	Seen[G] = Stamp;
	Cost[G] = 0.f;
	Next[G] = INDEX_NONE;
	Open.HeapPush({ H(G), G }, FOpenLess());
	TArray<uint8> Closed; // lazily: a node is closed when popped with its best cost
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

void USRGridSubsystem::StringPull(const TArray<FIntPoint>& Cells, TArray<FVector2D>& Out) const
{
	// Cells run start -> goal. Keep only the corners: from each anchor, go as far along as a straight walk allows.
	if (Cells.Num() == 0) { return; }
	int32 Anchor = 0;
	FVector2D AnchorPos = CellCentre(Cells[0]);
	while (Anchor < Cells.Num() - 1)
	{
		int32 Far = Anchor + 1;
		for (int32 k = Anchor + 2; k < Cells.Num(); ++k)
		{
			if (CanWalkStraight(AnchorPos, CellCentre(Cells[k]))) { Far = k; }
			else if (k - Far > 6) { break; } // well past the last visible cell: stop looking
		}
		Out.Add(CellCentre(Cells[Far]));
		Anchor = Far;
		AnchorPos = CellCentre(Cells[Far]);
	}
}

bool USRGridSubsystem::FindGroupPaths(const TArray<FVector2D>& Starts, const FVector2D& Goal, TArray<TArray<FVector2D>>& OutPaths)
{
	OutPaths.SetNum(Starts.Num());
	for (TArray<FVector2D>& P : OutPaths) { P.Reset(); }
	if (Dim <= 0 || Starts.Num() == 0) { return true; }
	const double T0 = FPlatformTime::Seconds();

	FIntPoint GoalCell;
	const FVector2D G = NearestWalkable(Goal);
	if (!ToCell(G, GoalCell) || !IsWalkable(GoalCell)) { return false; }

	// Walkers that can see the goal in a straight line need no search.
	TArray<FIntPoint> StartCells;
	TArray<int32> Searching;
	for (int32 i = 0; i < Starts.Num(); ++i)
	{
		if (CanWalkStraight(Starts[i], G)) { continue; }
		FIntPoint C;
		const FVector2D S = NearestWalkable(Starts[i], 4);
		if (!ToCell(S, C) || !IsWalkable(C)) { continue; }
		StartCells.Add(C);
		Searching.Add(i);
	}
	if (Searching.Num() == 0) { return true; }

	const bool bAll = Flood(GoalCell, StartCells);
	bool bAny = false;
	TArray<FIntPoint> Chain;
	for (int32 k = 0; k < Searching.Num(); ++k)
	{
		const int32 I0 = Idx(StartCells[k]);
		if (Seen[I0] != Stamp) { continue; } // unreachable from the goal (cut off by water / cliffs): it keeps a straight order
		Chain.Reset();
		for (int32 I = I0; I != INDEX_NONE && Chain.Num() < Dim * 4; I = Next[I]) { Chain.Add(FromIdx(I)); }
		TArray<FVector2D>& Path = OutPaths[Searching[k]];
		StringPull(Chain, Path);
		if (Path.Num() > 0) { Path.Pop(); } // the goal cell's centre: the caller appends the exact slot instead
		bAny = true;
		if (USRFeelSettings::Get().bDebugDrawPaths)
		{
			TArray<FVector2D> D = Path;
			D.Insert(Starts[Searching[k]], 0);
			D.Add(G);
			DebugPaths.Add(D);
			if (DebugPaths.Num() > 40) { DebugPaths.RemoveAt(0); }
		}
	}
	UE_LOG(LogSovereign, Verbose, TEXT("PATH group of %d (%d searched) in %.2f ms%s"), Starts.Num(), Searching.Num(),
		(FPlatformTime::Seconds() - T0) * 1000.0, bAll ? TEXT("") : TEXT(" (some walkers unreachable)"));
	return bAny || bAll;
}

bool USRGridSubsystem::FindPath(const FVector2D& From, const FVector2D& Goal, TArray<FVector2D>& OutPath)
{
	TArray<TArray<FVector2D>> Paths;
	const bool bOk = FindGroupPaths({ From }, Goal, Paths);
	OutPath = Paths.Num() > 0 ? Paths[0] : TArray<FVector2D>();
	OutPath.Add(Goal);
	return bOk;
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
}

#undef LOCTEXT_NAMESPACE
