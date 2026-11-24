#include "VLFog.h"
#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLGrid.h"
#include "VLKing.h"
#include "VLTroopShip.h"
#include "Algo/BinarySearch.h"
#include "Async/ParallelFor.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Physics/Experimental/PhysInterface_Chaos.h"
#include "Physics/PhysicsInterfaceCore.h"
#include "RenderingThread.h"
#include "Math/Float16.h"

static TAutoConsoleVariable<int32> CVarFog(TEXT("vl.Fog"), 1, TEXT("Fog of war for the player: 1 on (battles), 0 off."));
static TAutoConsoleVariable<int32> CVarFogTestWorld(TEXT("vl.Fog.TestWorld"), 0, TEXT("1: the fog of war on the Test World too (off there by default)."));
static TAutoConsoleVariable<float> CVarFogEye(TEXT("vl.Fog.EyeHeight"), 2000.f, TEXT("cm: the eye over a unit's (or a building's) feet; with vl.Fog.Angle it gives the view radius (20 m, 30 deg: 34.6 m on flat ground)."));
static TAutoConsoleVariable<float> CVarFogAngle(TEXT("vl.Fog.Angle"), 30.f, TEXT("degrees below the horizontal the eye looks down at; where that cone meets the terrain is how far it sees."));
static TAutoConsoleVariable<float> CVarFogMax(TEXT("vl.Fog.MaxRadius"), 9000.f, TEXT("cm: the longest a view ray is marched (before the kind's scale)."));
static TAutoConsoleVariable<float> CVarFogKind(TEXT("vl.Fog.KindScale"), 1.f, TEXT("0: every kind sees alike; 1: each kind's radius times its sight over a swordsman's (archer 1.15, Spy 2.0)."));
static TAutoConsoleVariable<float> CVarFogTower(TEXT("vl.Fog.TowerView"), 1.0f, TEXT("a watch tower sees this many times its shooting range (1.0: it shoots as far as it sees, 2026-11-24; its range is 43.2 / 48.6 / 54 m) (from its walls, on flat ground; the height rule on top)."));
static TAutoConsoleVariable<float> CVarFogLayer(TEXT("vl.Fog.Layer"), 1750.f, TEXT("cm: the fog's top over the smoothed terrain (a watch tower's tip is at 2060)."));
static TAutoConsoleVariable<float> CVarFogDensity(TEXT("vl.Fog.Density"), 0.0016f, TEXT("1/cm: the unexplored fog's density (the optical depth is this x the path through the layer: dense at a grazing look, thin looking down)."));
static TAutoConsoleVariable<float> CVarFogExplored(TEXT("vl.Fog.ExploredDensity"), 0.00035f, TEXT("1/cm: the explored (not visible) fog's density."));
static TAutoConsoleVariable<float> CVarFogSteep(TEXT("vl.Fog.Steep"), 0.12f, TEXT("the density's share for a steep look (the overview), on top of the shorter path through the layer; 1: the path alone."));
static TAutoConsoleVariable<float> CVarFogGraze(TEXT("vl.Fog.GrazeDeg"), 6.f, TEXT("degrees below the horizontal: a look this low or lower sees the full density (the hero's view)."));
static TAutoConsoleVariable<float> CVarFogSteepDeg(TEXT("vl.Fog.SteepDeg"), 33.f, TEXT("degrees below the horizontal: from this steep on the density is vl.Fog.Steep of itself (smooth between)."));
static TAutoConsoleVariable<float> CVarFogTopFeather(TEXT("vl.Fog.TopFeather"), 800.f, TEXT("cm: the fog's density ramps in over this much below its top."));
static TAutoConsoleVariable<int32> CVarFogFeather(TEXT("vl.Fog.Feather"), 3, TEXT("cells (2 m): the half-width of the box blurs (two each way) that soften the edge of what is seen: 3 gives a bank some 12 m deep."));
static TAutoConsoleVariable<float> CVarFogDim(TEXT("vl.Fog.UnexploredDim"), 0.6f, TEXT("unexplored ground under the fog is darkened to this (and greyed)."));
static TAutoConsoleVariable<float> CVarFogWisps(TEXT("vl.Fog.Wisps"), 350.f, TEXT("cm: how far the fog's top rises and falls in drifting wisps."));
static TAutoConsoleVariable<float> CVarFogBright(TEXT("vl.Fog.Bright"), 0.72f, TEXT("the fog's brightness (x its colour)."));
static TAutoConsoleVariable<float> CVarFogDesat(TEXT("vl.Fog.Desaturate"), 0.45f, TEXT("explored ground out of sight is greyed this much."));
static TAutoConsoleVariable<float> CVarFogInterval(TEXT("vl.Fog.Interval"), 0.1f, TEXT("s between two vision updates."));
static TAutoConsoleVariable<float> CVarFogFade(TEXT("vl.Fog.Fade"), 0.35f, TEXT("s: how long a cell takes to clear or cloud over."));
static TAutoConsoleVariable<float> CVarFogCell(TEXT("vl.Fog.Cell"), 200.f, TEXT("cm: the fog's cells (read when a match starts)."));
static TAutoConsoleVariable<int32> CVarFogLog(TEXT("vl.Fog.Log"), 0, TEXT("1: log the played unit's view radius whenever it changes by over 1 m; 2: and the vision update's timings."));

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdFogReveal(TEXT("vl.Fog.Reveal"), TEXT("vl.Fog.Reveal [1|0]: the whole map seen (and explored) / back to the fog"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLFog* Fog = UVLFog::Get(World))
			{
				const bool bOn = Args.Num() == 0 || FCString::Atoi(*Args[0]) != 0;
				Fog->SetRevealAll(bOn);
				UE_LOG(LogSovereignRealms, Log, TEXT("fog: reveal all %s"), bOn ? TEXT("on") : TEXT("off"));
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdFogInfo(TEXT("vl.Fog.Info"), TEXT("the fog's state, and the view of the unit played and the selection (radius min / mean / max, eye height, ground)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (UVLFog* Fog = UVLFog::Get(World))
			{
				APlayerController* PC = World->GetFirstPlayerController();
				Fog->LogInfo(PC ? PC->GetPawn() : nullptr);
			}
		}));
	FAutoConsoleCommandWithWorldAndArgs CmdFogEyes(TEXT("vl.Fog.Eyes"), TEXT("log every eye of the player's: what, where, eye height, view radius min / mean / max"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (UVLFog* Fog = UVLFog::Get(World)) { Fog->LogEyes(); }
		}));
}

UVLFog* UVLFog::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLFog>() : nullptr;
}

bool UVLFog::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UVLFog::Deinitialize()
{
	Super::Deinitialize();
}

bool UVLFog::HidesUnit(const AVLKing* Unit)
{
	return HidesActor(Unit);
}

bool UVLFog::HidesActor(const AActor* Actor)
{
	const UVLFog* Fog = Actor ? Get(Actor) : nullptr;
	return Fog && Fog->bActive && Fog->HiddenNow.Contains(Actor);
}

bool UVLFog::InSight(const AActor* Building)
{
	const UVLFog* Fog = Building ? Get(Building) : nullptr;
	if (!Fog || !Fog->bActive || Fog->bRevealAll)
	{
		return true;
	}
	const UVLBattle* Battle = UVLBattle::Get(Building);
	const FVLBuildingState* B = Battle ? Battle->FindBuilding(Building) : nullptr;
	return !B || B->Team == UVLBattle::Player || Fog->InSightNow.Contains(Building);
}

bool UVLFog::ToCell(const FVector2D& P, int32& Out) const
{
	const int32 X = FMath::FloorToInt((P.X - Origin.X) / Cell), Y = FMath::FloorToInt((P.Y - Origin.Y) / Cell);
	if (X < 0 || Y < 0 || X >= Dim || Y >= Dim)
	{
		return false;
	}
	Out = Y * Dim + X;
	return true;
}

int32 UVLFog::StateAt(const FVector2D& World) const
{
	int32 C = 0;
	if (!bActive || bRevealAll)
	{
		return 2;
	}
	if (!ToCell(World, C))
	{
		return 0;
	}
	return Visible[C] ? 2 : (Explored[C] ? 1 : 0);
}

bool UVLFog::WasSeen(const AActor* Building) const
{
	return !bActive || bRevealAll || Seen.Contains(Building);
}

float UVLFog::HeightAt(const FVector2D& P) const
{
	// bilinear over the cells' middles; off the map: the edge's
	const float FX = FMath::Clamp((P.X - Origin.X) / Cell - 0.5f, 0.f, Dim - 1.001f), FY = FMath::Clamp((P.Y - Origin.Y) / Cell - 0.5f, 0.f, Dim - 1.001f);
	const int32 X = FMath::FloorToInt(FX), Y = FMath::FloorToInt(FY);
	const float AX = FX - X, AY = FY - Y;
	const int32 I = Y * Dim + X;
	const float H0 = FMath::Lerp(Height[I], Height[I + 1], AX), H1 = FMath::Lerp(Height[I + Dim], Height[I + Dim + 1], AX);
	return FMath::Lerp(H0, H1, AY);
}

// ------------------------------------------------------------------------------------------------ setup

bool UVLFog::Init()
{
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!Grid || !Grid->EnsureBuilt())
	{
		return false;
	}
	const double T0 = FPlatformTime::Seconds();
	// the grid's ground made square round its middle (as the minimap: AVLHUD::DrawMinimap)
	FBox2D Box = Grid->GetBounds();
	const FVector2D C = Box.GetCenter();
	const float Half = FMath::Max(Box.GetExtent().X, Box.GetExtent().Y);
	Cell = FMath::Clamp(CVarFogCell.GetValueOnGameThread(), 100.f, 800.f);
	Dim = FMath::Clamp(FMath::CeilToInt(2.f * Half / Cell), 16, 1024);
	Cell = 2.f * Half / Dim;
	Origin = C - FVector2D(Half, Half);
	const int32 N = Dim * Dim;
	Visible.Init(0, N);
	Explored.Init(0, N);
	ShowVis.Init(0, N);
	ShowExp.Init(0, N);
	MaskPixels.Init(FColor(0, 0, 0, 0), N);
	BuildHeights();
	BuildOffsets(CVarFogMax.GetValueOnGameThread() * 2.2f);

	MaskTex = UTexture2D::CreateTransient(Dim, Dim, PF_B8G8R8A8, TEXT("VLFogMask"));
	MaskTex->SRGB = false;
	MaskTex->Filter = TF_Bilinear;
	MaskTex->AddressX = MaskTex->AddressY = TA_Clamp;
	MaskTex->UpdateResource();

	// the terrain smoothed (two box blurs of 5 cells): the fog's floor, its top Layer over it
	TArray<float> A = Height, B;
	B.SetNumUninitialized(N);
	const int32 K = FMath::Max(1, FMath::RoundToInt(600.f / Cell));
	for (int32 Pass = 0; Pass < 4; ++Pass)
	{
		const bool bX = (Pass & 1) == 0;
		for (int32 y = 0; y < Dim; ++y)
		{
			for (int32 x = 0; x < Dim; ++x)
			{
				float S = 0.f;
				for (int32 k = -K; k <= K; ++k)
				{
					const int32 xx = bX ? FMath::Clamp(x + k, 0, Dim - 1) : x, yy = bX ? y : FMath::Clamp(y + k, 0, Dim - 1);
					S += A[yy * Dim + xx];
				}
				B[y * Dim + x] = S / (2 * K + 1);
			}
		}
		Swap(A, B);
	}
	TArray<FFloat16>* Half16 = new TArray<FFloat16>();
	Half16->SetNumUninitialized(N);
	for (int32 i = 0; i < N; ++i) { (*Half16)[i] = FFloat16(A[i]); }
	HeightTex = UTexture2D::CreateTransient(Dim, Dim, PF_R16F, TEXT("VLFogHeight"));
	HeightTex->SRGB = false;
	HeightTex->Filter = TF_Bilinear;
	HeightTex->AddressX = HeightTex->AddressY = TA_Clamp;
	HeightTex->UpdateResource();
	FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(0, 0, 0, 0, Dim, Dim);
	HeightTex->UpdateTextureRegions(0, 1, Region, Dim * sizeof(FFloat16), sizeof(FFloat16), reinterpret_cast<uint8*>(Half16->GetData()),
		[Half16](uint8*, const FUpdateTextureRegion2D* R) { delete Half16; delete R; });

	bInit = true;
	UE_LOG(LogSovereignRealms, Log, TEXT("fog: %d x %d cells of %.0f cm over %.0f m square from %.0f %.0f (%.0f ms)"), Dim, Dim, Cell, 2.f * Half / 100.f, Origin.X, Origin.Y,
		(FPlatformTime::Seconds() - T0) * 1000.0);
	return true;
}

void UVLFog::BuildHeights()
{
	UWorld* World = GetWorld();
	const UVLGrid* Grid = UVLGrid::Get(this);
	const int32 N = Dim * Dim;
	Height.Init(-1e6f, N);
	TArray<UStaticMeshComponent*> Ground;
	FBox Bounds(ForceInit);
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		UStaticMeshComponent* Comp = It->GetStaticMeshComponent();
		const UStaticMesh* Mesh = Comp ? Comp->GetStaticMesh() : nullptr;
		if (!Mesh || It->ActorHasTag(TEXT("Water")))
		{
			continue;
		}
		const FString Name = Mesh->GetName();
		if (It->ActorHasTag(TEXT("Ground")) || Name.StartsWith(TEXT("SM_Terrain")) || Name.StartsWith(TEXT("SM_Flat_")))
		{
			Ground.Add(Comp);
			Bounds += Comp->Bounds.GetBox();
		}
	}
	const float Top = Bounds.IsValid ? Bounds.Max.Z + 100.f : 100000.f, Bottom = Bounds.IsValid ? Bounds.Min.Z - 100.f : -100000.f;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(VLFog), true);
	ParallelFor(TEXT("VLFogHeights"), Dim, 1, [&](int32 y)
	{
		FPhysicsCommand::ExecuteRead(World->GetPhysicsScene(), [&]()
		{
			for (int32 x = 0; x < Dim; ++x)
			{
				const FVector2D P = Origin + (FVector2D(x, y) + 0.5f) * Cell;
				float Z = -1e6f;
				for (UStaticMeshComponent* Comp : Ground)
				{
					const FBox CB = Comp->Bounds.GetBox();
					if (P.X < CB.Min.X || P.X > CB.Max.X || P.Y < CB.Min.Y || P.Y > CB.Max.Y)
					{
						continue;
					}
					FHitResult Hit;
					if (Comp->LineTraceComponent(Hit, FVector(P.X, P.Y, Top), FVector(P.X, P.Y, Bottom), Params))
					{
						Z = FMath::Max(Z, float(Hit.ImpactPoint.Z));
					}
				}
				Height[y * Dim + x] = Z;
			}
		});
	});
	float Low = TNumericLimits<float>::Max();
	for (float Z : Height) { if (Z > -1e5f) { Low = FMath::Min(Low, Z); } }
	if (Low == TNumericLimits<float>::Max()) { Low = 0.f; }
	for (int32 i = 0; i < N; ++i)
	{
		const FVector2D P = Origin + (FVector2D(i % Dim, i / Dim) + 0.5f) * Cell;
		float Z = Height[i] > -1e5f ? Height[i] : Low;
		if (Grid)
		{
			Z = FMath::Max(Z, Grid->WaterLevelAt(FVector(P.X, P.Y, Z)));      // (the sea's surface: rays end on it)
		}
		Height[i] = Z;
	}
}

void UVLFog::BuildOffsets(float MaxRadius)
{
	OffsetsRadius = MaxRadius;
	Offsets.Reset();
	const int32 R = FMath::CeilToInt(MaxRadius / Cell);
	for (int32 dy = -R; dy <= R; ++dy)
	{
		for (int32 dx = -R; dx <= R; ++dx)
		{
			const float D = FMath::Sqrt(float(dx * dx + dy * dy)) * Cell;
			if (D <= MaxRadius)
			{
				float Ang = FMath::Atan2(float(dy), float(dx));
				if (Ang < 0.f) { Ang += 2.f * PI; }
				Offsets.Add({ int16(dx), int16(dy), D, Ang / (2.f * PI) * NumDirs });
			}
		}
	}
	Offsets.Sort([](const FOffset& A, const FOffset& B) { return A.Dist < B.Dist; });
}

void UVLFog::Reset()
{
	for (const TWeakObjectPtr<AActor>& W : HiddenByUs)
	{
		if (AActor* A = W.Get())
		{
			const AVLKing* K = Cast<AVLKing>(A);
			const UVLBattle* Battle = UVLBattle::Get(this);
			const FVLBuildingState* B = Battle ? Battle->FindBuilding(A) : nullptr;
			if ((!K || !K->IsDead()) && (!B || B->IsAlive()))
			{
				A->SetActorHiddenInGame(false);
			}
		}
	}
	HiddenByUs.Reset();
	HiddenNow.Reset();
	if (Volume)
	{
		for (FWeightedBlendable& W : Volume->Settings.WeightedBlendables.Array) { W.Weight = 0.f; }
	}
}

// ------------------------------------------------------------------------------------------------ eyes

bool UVLFog::EyeParams(const AActor* A, FEye& E) const
{
	const float Eye = FMath::Max(CVarFogEye.GetValueOnGameThread(), 10.f);
	const float Tan = FMath::Tan(FMath::DegreesToRadians(FMath::Clamp(CVarFogAngle.GetValueOnGameThread(), 2.f, 89.f)));
	E.Wall.Init(0.f, NumDirs);
	E.Scale = 1.f;
	E.Notice = 1.f;
	if (const AVLKing* K = Cast<AVLKing>(A))
	{
		if (K->IsDead() || K->Team != UVLBattle::Player || K->bAmbient || K->bTowerGuard)
		{
			return false;
		}
		const FVector Feet = K->GetFeet();
		E.At = FVector2D(Feet);
		E.FeetZ = Feet.Z;
		if (const UVLGrid* Grid = UVLGrid::Get(this))
		{
			E.FeetZ = FMath::Max(E.FeetZ, Grid->WaterLevelAt(Feet));     // (one in the water looks from its surface)
		}
		E.EyeH = Eye;
		const float Base = VLRules::Troop(EVLUnitKind::Swordsman).Sight;
		const float Ratio = Base > 0.f ? K->KindRules().Sight / Base : 1.f;
		E.Scale = FMath::Max(0.1f, 1.f + (Ratio - 1.f) * CVarFogKind.GetValueOnGameThread());
		return true;
	}
	if (const AVLTroopShip* Ship = Cast<AVLTroopShip>(A))
	{
		if (Ship->GetTeam() != UVLBattle::Player)
		{
			return false;
		}
		E.At = FVector2D(Ship->GetActorLocation());
		E.FeetZ = HeightAt(E.At);
		E.EyeH = Eye;
		E.Wall.Init(400.f, NumDirs);
		return true;
	}
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* B = Battle ? Battle->FindBuilding(A) : nullptr;
	if (!B || !B->IsAlive() || B->Team != UVLBattle::Player)
	{
		return false;
	}
	const UStaticMeshComponent* SMC = A->FindComponentByClass<UStaticMeshComponent>();
	E.At = FVector2D(A->GetActorLocation());
	E.FeetZ = HeightAt(E.At);
	E.EyeH = Eye;
	if (SMC && SMC->GetStaticMesh())
	{
		// its walls: for each direction, the support of its box (turned with it) that way, from its middle
		const FTransform T = SMC->GetComponentTransform();
		const FBox Box = SMC->GetStaticMesh()->GetBoundingBox();
		const FVector Mid = T.TransformPosition(Box.GetCenter());
		E.At = FVector2D(Mid);
		E.FeetZ = HeightAt(E.At);
		const FVector Ext = Box.GetExtent() * T.GetScale3D().GetAbs();
		const FVector AX = T.GetUnitAxis(EAxis::X), AY = T.GetUnitAxis(EAxis::Y);
		for (int32 d = 0; d < NumDirs; ++d)
		{
			const float Ang = 2.f * PI * d / NumDirs;
			const FVector Dir(FMath::Cos(Ang), FMath::Sin(Ang), 0.f);
			E.Wall[d] = FMath::Abs(FVector::DotProduct(Dir, AX)) * Ext.X + FMath::Abs(FVector::DotProduct(Dir, AY)) * Ext.Y;
		}
	}
	if (B->Kind == EVLBuilding::Tower && !B->IsSite())
	{
		// a watch tower: TowerView x its shooting range on flat ground, from its walls; the eye put where the cone lands so
		const float Range = VLRules::Level(EVLBuilding::Tower, FMath::Max(1, B->Level)).Range;
		E.EyeH = FMath::Max(100.f, Range * CVarFogTower.GetValueOnGameThread() * Tan);
	}
	return true;
}

void UVLFog::ComputeRays(FEye& E) const
{
	const float Tan = FMath::Tan(FMath::DegreesToRadians(FMath::Clamp(CVarFogAngle.GetValueOnAnyThread(), 2.f, 89.f)));
	const float MaxR = FMath::Max(CVarFogMax.GetValueOnAnyThread(), 500.f);
	const float Step = Cell * 0.5f;
	const float EyeZ = E.FeetZ + E.EyeH;
	E.R.SetNum(NumDirs);
	E.MaxR = 0.f;
	E.MeanR = 0.f;
	for (int32 d = 0; d < NumDirs; ++d)
	{
		const float Ang = 2.f * PI * d / NumDirs;
		const FVector2D Dir(FMath::Cos(Ang), FMath::Sin(Ang));
		const FVector2D From = E.At + Dir * E.Wall[d];
		float Hit = MaxR, PrevGap = E.EyeH;
		for (float S = Step; S <= MaxR; S += Step)
		{
			const float Gap = (EyeZ - S * Tan) - HeightAt(From + Dir * S);
			if (Gap <= 0.f)
			{
				Hit = S - Step * Gap / FMath::Min(Gap - PrevGap, -1e-3f);     // (where the ray crossed the ground, between the samples)
				break;
			}
			PrevGap = Gap;
		}
		E.R[d] = E.Wall[d] + Hit * E.Scale;
		E.MaxR = FMath::Max(E.MaxR, E.R[d]);
		E.MeanR += E.R[d] / NumDirs;
	}
}

UVLFog::FEye* UVLFog::FindOrMakeEye(const AActor* A, bool bDefer)
{
	FEye Want;
	if (!EyeParams(A, Want))
	{
		return nullptr;
	}
	FEye& E = Eyes.FindOrAdd(A);
	const bool bSame = E.R.Num() == NumDirs && FVector2D::DistSquared(E.At, Want.At) < FMath::Square(100.f) && FMath::Abs(E.FeetZ - Want.FeetZ) < 60.f
		&& FMath::IsNearlyEqual(E.EyeH, Want.EyeH, 1.f) && FMath::IsNearlyEqual(E.Scale, Want.Scale, 0.001f) && E.Wall == Want.Wall;
	if (!bSame)
	{
		Want.Actor = A;
		E = MoveTemp(Want);
		E.bDirty = true;
		if (!bDefer)
		{
			ComputeRays(E);
			E.bDirty = false;
		}
	}
	E.Frame = EyeFrame;
	return &E;
}

// ------------------------------------------------------------------------------------------------ the tick

void UVLFog::Tick(float DeltaSeconds)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	const bool bPlaying = Battle && Battle->IsBattle() && Battle->GetState() != EVLMatch::Idle;
	const bool bWant = bPlaying && CVarFog.GetValueOnGameThread() != 0 && (!Battle->IsTestWorld() || CVarFogTestWorld.GetValueOnGameThread() != 0);
	if (bPlaying && !bWasPlaying)
	{
		// a new match: nothing explored yet; the level's own buildings are noted
		if (bInit) { FMemory::Memzero(Explored.GetData(), Explored.Num()); FMemory::Memzero(ShowExp.GetData(), ShowExp.Num()); }
		Seen.Reset();
		Eyes.Reset();
		MapBuildings.Reset();
		for (const FVLBuildingState& B : Battle->GetBuildings())
		{
			if (B.Actor.IsValid() && !B.bRuntime) { MapBuildings.Add(B.Actor.Get()); }
		}
		NextUpdate = 0.0;
	}
	bWasPlaying = bPlaying;
	if (!bWant)
	{
		if (bActive)
		{
			bActive = false;
			Reset();
			UE_LOG(LogSovereignRealms, Log, TEXT("fog: off"));
		}
		return;
	}
	if (!bInit && !Init())
	{
		return;
	}
	if (bPendingRestore)
	{
		// a saved game's: what was explored and seen then
		for (const TWeakObjectPtr<const AActor>& A : PendingSeen)
		{
			if (A.IsValid()) { Seen.Add(A); }
		}
		const bool bSet = SetExplored(PendingExplored, PendingDim);
		if (bSet)
		{
			for (int32 i = 0; i < Explored.Num(); ++i) { ShowExp[i] = Explored[i] ? 255 : 0; }
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("fog: a saved game's put back (%s, %d buildings seen)"), bSet ? TEXT("explored cells") : TEXT("its grid differs: not the explored cells"), PendingSeen.Num());
		PendingExplored.Reset();
		PendingSeen.Reset();
		PendingDim = 0;
		bPendingRestore = false;
	}
	if (!bActive)
	{
		bActive = true;
		NextUpdate = 0.0;
		UE_LOG(LogSovereignRealms, Log, TEXT("fog: on"));
	}
	SetupVisual();
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now >= NextUpdate)
	{
		const float Dt = LastTick > 0.0 ? float(FMath::Min(Now - LastTick, 0.5)) : 1.f;
		LastTick = Now;
		NextUpdate = Now + FMath::Max(0.02f, CVarFogInterval.GetValueOnGameThread());
		const double T0 = FPlatformTime::Seconds();
		UpdateVision();
		UploadMask(Dt);
		UpdateMs = (FPlatformTime::Seconds() - T0) * 1000.0;
		UpdateMsMax = FMath::Max(UpdateMsMax, UpdateMs);
		ApplyVisualParams();
	}
	UpdateHidden();
	if (CVarFogLog.GetValueOnGameThread() != 0)
	{
		static float LastLogged = 0.f;
		const APlayerController* PC = GetWorld()->GetFirstPlayerController();
		float Min = 0.f, Max = 0.f, EyeH = 0.f;
		const float R = PC ? ViewRadius(PC->GetPawn(), &Min, &Max, &EyeH) : 0.f;
		if (R > 0.f && FMath::Abs(R - LastLogged) > 100.f)
		{
			LastLogged = R;
			UE_LOG(LogSovereignRealms, Log, TEXT("fog: %s at %s sees %.1f m (min %.1f, max %.1f; eye %.1f m over its feet)"), *GetNameSafe(PC->GetPawn()), *PC->GetPawn()->GetActorLocation().ToCompactString(),
				R / 100.f, Min / 100.f, Max / 100.f, EyeH / 100.f);
		}
	}
}

void UVLFog::UpdateVision()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const double TV0 = FPlatformTime::Seconds();
	++EyeFrame;
	FMemory::Memzero(Visible.GetData(), Visible.Num());
	if (bRevealAll)
	{
		FMemory::Memset(Visible.GetData(), 1, Visible.Num());
		FMemory::Memset(Explored.GetData(), 1, Explored.Num());
		return;
	}
	// the eyes of this update (their rays worked out again only for those that moved, side by side on worker threads;
	// the pointers taken once the map has stopped growing)
	for (AVLKing* U : Battle->AllUnits()) { FindOrMakeEye(U, true); }
	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		if (B.Actor.IsValid()) { FindOrMakeEye(B.Actor.Get(), true); }
	}
	if (const UVLFleet* Fleet = UVLFleet::Get(this))
	{
		for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->GetShips())
		{
			if (S.IsValid()) { FindOrMakeEye(S.Get(), true); }
		}
	}
	TArray<FEye*, TInlineAllocator<256>> Now, Dirty;
	for (auto It = Eyes.CreateIterator(); It; ++It)
	{
		if (It->Value.Frame != EyeFrame) { It.RemoveCurrent(); continue; }
		Now.Add(&It->Value);
		if (It->Value.bDirty) { Dirty.Add(&It->Value); }
	}
	const double TR = FPlatformTime::Seconds();
	ParallelFor(TEXT("VLFogRays"), Dirty.Num(), 2, [this, &Dirty](int32 i) { ComputeRays(*Dirty[i]); Dirty[i]->bDirty = false; });
	const double TS = FPlatformTime::Seconds();
	// each eye's outline filled: the cells round it nearest first, kept while within the radius of their direction
	for (const FEye* E : Now)
	{
		if (E->MaxR > OffsetsRadius)
		{
			BuildOffsets(E->MaxR * 1.2f);
		}
		const int32 CX = FMath::FloorToInt((E->At.X - Origin.X) / Cell), CY = FMath::FloorToInt((E->At.Y - Origin.Y) / Cell);
		// the disc inside its shortest radius in whole rows, then only the ring beyond it cell by cell
		float MinR = E->MaxR;
		for (float R : E->R) { MinR = FMath::Min(MinR, R); }
		const int32 RIn = FMath::Max(0, FMath::FloorToInt(MinR / Cell) - 1);
		for (int32 dy = -RIn; dy <= RIn; ++dy)
		{
			const int32 Y = CY + dy;
			if (Y < 0 || Y >= Dim) { continue; }
			const int32 Half = FMath::FloorToInt(FMath::Sqrt(float(RIn * RIn - dy * dy)));
			const int32 X0 = FMath::Max(0, CX - Half), X1 = FMath::Min(Dim - 1, CX + Half);
			if (X1 >= X0) { FMemory::Memset(&Visible[Y * Dim + X0], 1, X1 - X0 + 1); }
		}
		const float InnerDist = float(RIn) * Cell;
		int32 First = Algo::LowerBoundBy(Offsets, InnerDist, &FOffset::Dist);
		for (int32 oi = First; oi < Offsets.Num(); ++oi)
		{
			const FOffset& O = Offsets[oi];
			if (O.Dist > E->MaxR)
			{
				break;
			}
			const int32 X = CX + O.DX, Y = CY + O.DY;
			if (X < 0 || Y < 0 || X >= Dim || Y >= Dim)
			{
				continue;
			}
			const int32 D0 = FMath::FloorToInt(O.Dir) % NumDirs, D1 = (D0 + 1) % NumDirs;
			const float F = O.Dir - FMath::FloorToFloat(O.Dir);
			if (O.Dist <= FMath::Lerp(E->R[D0], E->R[D1], F) + Cell * 0.5f)
			{
				Visible[Y * Dim + X] = 1;
			}
		}
	}
	for (int32 i = 0; i < Visible.Num(); ++i) { Explored[i] |= Visible[i]; }
	const double TB = FPlatformTime::Seconds();
	// enemy buildings in sight (any corner or the middle of their footprint on a visible cell), and seen ever
	InSightNow.Reset();
	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		const AActor* A = B.Actor.Get();
		if (!A || B.Team == UVLBattle::Player)
		{
			continue;
		}
		FVector O, Ext;
		A->GetActorBounds(true, O, Ext);
		for (int32 k = 0; k < 5; ++k)
		{
			const FVector2D P = FVector2D(O) + (k == 0 ? FVector2D::ZeroVector : FVector2D((k & 1) ? Ext.X : -Ext.X, (k & 2) ? Ext.Y : -Ext.Y) * 0.8f);
			int32 C = 0;
			if (ToCell(P, C) && Visible[C])
			{
				Seen.Add(A);
				InSightNow.Add(A);
				break;
			}
		}
	}
	if (CVarFogLog.GetValueOnGameThread() > 1)
	{
		const double TE = FPlatformTime::Seconds();
		UE_LOG(LogSovereignRealms, Log, TEXT("fog timing: eyes %.2f ms (%d, %d moved), rays %.2f, fill %.2f, buildings %.2f"), (TR - TV0) * 1000.0, Now.Num(), Dirty.Num(), (TS - TR) * 1000.0, (TB - TS) * 1000.0, (TE - TB) * 1000.0);
	}
}

void UVLFog::UpdateHidden()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	HiddenNow.Reset();
	auto Shown = [this](const FVector2D& P)
	{
		int32 C = 0;
		return bRevealAll || (ToCell(P, C) && Visible[C] != 0);
	};
	for (AVLKing* U : Battle->AllUnits())
	{
		if (U->Team == UVLBattle::Player || U->bAmbient)
		{
			continue;
		}
		bool bShow = Shown(FVector2D(U->GetActorLocation()));
		if (bShow && !bRevealAll && U->KindRules().Notice < 1.f)
		{
			// a Spy: only within its Notice share of a player eye's reach
			bShow = false;
			const FVector2D P(U->GetActorLocation());
			for (const TPair<TWeakObjectPtr<const AActor>, FEye>& E : Eyes)
			{
				if (FVector2D::DistSquared(E.Value.At, P) <= FMath::Square(E.Value.MeanR * U->KindRules().Notice)) { bShow = true; break; }
			}
		}
		if (!bShow)
		{
			HiddenNow.Add(U);
		}
		SetHiddenByFog(U, !bShow);
	}
	if (const UVLFleet* Fleet = UVLFleet::Get(this))
	{
		for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->GetShips())
		{
			if (AVLTroopShip* Ship = S.Get(); Ship && Ship->GetTeam() != UVLBattle::Player)
			{
				const bool bShow = Shown(FVector2D(Ship->GetActorLocation()));
				if (!bShow) { HiddenNow.Add(Ship); }
				SetHiddenByFog(Ship, !bShow);
			}
		}
	}
	// enemy buildings raised in the match: hidden until seen (the level's own stand: as last seen)
	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		AActor* A = B.Actor.Get();
		if (!A || B.Team == UVLBattle::Player || B.Team == UVLBattle::Neutral)
		{
			continue;
		}
		const bool bShow = bRevealAll || Seen.Contains(A) || MapBuildings.Contains(A);
		if (!bShow) { HiddenNow.Add(A); }
		if (B.IsAlive()) { SetHiddenByFog(A, !bShow); }
	}
}

void UVLFog::SetHiddenByFog(AActor* A, bool bHide)
{
	if (bHide)
	{
		if (!A->IsHidden())
		{
			A->SetActorHiddenInGame(true);
			HiddenByUs.Add(A);
		}
	}
	else if (HiddenByUs.Remove(A) > 0)
	{
		const AVLKing* K = Cast<AVLKing>(A);
		if (!K || !K->IsDead())
		{
			A->SetActorHiddenInGame(false);
		}
	}
}

void UVLFog::UploadMask(float Dt)
{
	const double TM0 = FPlatformTime::Seconds();
	// eased toward the cells' states, the visible one softened over a few cells (two box blurs of 2 x Feather + 1 cells each way:
	// the fog's edge is a bank some 8 m deep, not a wall)
	const int32 Step = FMath::Clamp(FMath::RoundToInt(255.f * Dt / FMath::Max(CVarFogFade.GetValueOnGameThread(), 0.01f)), 1, 255);
	TArray<uint16> SoftA, SoftB;
	SoftA.SetNumUninitialized(Visible.Num());
	SoftB.SetNumUninitialized(Visible.Num());
	for (int32 i = 0; i < Visible.Num(); ++i) { SoftA[i] = Visible[i] ? 255 : 0; }
	// (each pass a running sum along its rows or columns, the rows side by side on worker threads)
	for (int32 Pass = 0; Pass < 4; ++Pass)
	{
		const bool bX = (Pass & 1) == 0;
		const int32 Stride = bX ? 1 : Dim, Line = bX ? Dim : 1;
		const uint16* In = SoftA.GetData();
		uint16* Out = SoftB.GetData();
		const int32 N = Dim;
		const int32 K = FMath::Clamp(CVarFogFeather.GetValueOnGameThread(), 0, 12), W = 2 * K + 1;
		ParallelFor(TEXT("VLFogBlur"), Dim, 16, [In, Out, Stride, Line, N, K, W](int32 L)
		{
			const int32 Base = L * Line;
			auto At = [&](int32 k) { return int32(In[Base + FMath::Clamp(k, 0, N - 1) * Stride]); };
			int32 Sum = 0;
			for (int32 k = -K; k <= K; ++k) { Sum += At(k); }
			for (int32 k = 0; k < N; ++k)
			{
				Out[Base + k * Stride] = uint16(Sum / W);
				Sum += At(k + K + 1) - At(k - K);
			}
		});
		Swap(SoftA, SoftB);
	}
	const double TM1 = FPlatformTime::Seconds();
	const uint16* Soft = SoftA.GetData();
	ParallelFor(TEXT("VLFogMask"), Dim, 16, [this, Soft, Step](int32 y)
	{
		for (int32 x = 0; x < Dim; ++x)
		{
			const int32 i = y * Dim + x;
			const int32 S = Soft[i];
			const int32 TV = FMath::Min(255, S * 2 - (Visible[i] ? 0 : S)), TE = Explored[i] ? 255 : 0;
			ShowVis[i] = uint8(TV > ShowVis[i] ? FMath::Min(TV, ShowVis[i] + Step) : FMath::Max(TV, ShowVis[i] - Step));
			ShowExp[i] = uint8(TE > ShowExp[i] ? FMath::Min(TE, ShowExp[i] + Step) : FMath::Max(TE, ShowExp[i] - Step));
			const int32 V = ShowVis[i], E = FMath::Max(int32(ShowExp[i]), V);
			const int32 Veil = (219 * (255 - E) + 115 * (E - V)) / 255;      // (0.86 unexplored, 0.45 explored)
			MaskPixels[i] = FColor(ShowVis[i], ShowExp[i], 0, uint8(FMath::Clamp(Veil, 0, 255)));
		}
	});
	const double TM2 = FPlatformTime::Seconds();
	if (MaskTex)
	{
		TArray<FColor>* Copy = new TArray<FColor>(MaskPixels);
		FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(0, 0, 0, 0, Dim, Dim);
		MaskTex->UpdateTextureRegions(0, 1, Region, Dim * sizeof(FColor), sizeof(FColor), reinterpret_cast<uint8*>(Copy->GetData()),
			[Copy](uint8*, const FUpdateTextureRegion2D* R) { delete Copy; delete R; });
	}
	if (CVarFogLog.GetValueOnGameThread() > 1)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("fog timing: blur %.2f ms, fill %.2f, upload %.2f"), (TM1 - TM0) * 1000.0, (TM2 - TM1) * 1000.0, (FPlatformTime::Seconds() - TM2) * 1000.0);
	}
}

// ------------------------------------------------------------------------------------------------ the look

void UVLFog::SetupVisual()
{
	if (bVisualTried)
	{
		if (Volume) { for (FWeightedBlendable& W : Volume->Settings.WeightedBlendables.Array) { W.Weight = 1.f; } }
		return;
	}
	bVisualTried = true;
	UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Voxel/Fog/M_FogOfWar.M_FogOfWar"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (!Mat)
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("fog: no /Game/Voxel/Fog/M_FogOfWar (run Tools/ue/build_fog_material.py): the fog works but is not drawn in the world"));
		return;
	}
	FogMID = UMaterialInstanceDynamic::Create(Mat, this);
	FogMID->SetTextureParameterValue(TEXT("Mask"), MaskTex);
	FogMID->SetTextureParameterValue(TEXT("Heights"), HeightTex);
	FActorSpawnParameters SP;
	SP.ObjectFlags |= RF_Transient;
	Volume = GetWorld()->SpawnActor<APostProcessVolume>(SP);
	if (Volume)
	{
		Volume->bUnbound = true;
		Volume->Priority = 50.f;
		Volume->BlendWeight = 1.f;
		Volume->Settings.WeightedBlendables.Array.Add(FWeightedBlendable(1.f, FogMID));
	}
	ApplyVisualParams();
}

void UVLFog::ApplyVisualParams()
{
	if (!FogMID)
	{
		return;
	}
	FogMID->SetVectorParameterValue(TEXT("Grid"), FLinearColor(Origin.X, Origin.Y, 1.f / (Dim * Cell), 0.f));
	FogMID->SetScalarParameterValue(TEXT("Layer"), CVarFogLayer.GetValueOnGameThread());
	FogMID->SetScalarParameterValue(TEXT("Density"), CVarFogDensity.GetValueOnGameThread());
	FogMID->SetScalarParameterValue(TEXT("ExploredDensity"), CVarFogExplored.GetValueOnGameThread());
	FogMID->SetScalarParameterValue(TEXT("Wisps"), CVarFogWisps.GetValueOnGameThread());
	FogMID->SetScalarParameterValue(TEXT("Bright"), CVarFogBright.GetValueOnGameThread());
	FogMID->SetScalarParameterValue(TEXT("Desaturate"), CVarFogDesat.GetValueOnGameThread());
	FogMID->SetScalarParameterValue(TEXT("On"), bRevealAll ? 0.f : 1.f);
	FogMID->SetScalarParameterValue(TEXT("Steep"), CVarFogSteep.GetValueOnGameThread());
	FogMID->SetScalarParameterValue(TEXT("TopFeather"), FMath::Max(50.f, CVarFogTopFeather.GetValueOnGameThread()));
	FogMID->SetScalarParameterValue(TEXT("UnexploredDim"), CVarFogDim.GetValueOnGameThread());
	const float Graze = FMath::Clamp(CVarFogGraze.GetValueOnGameThread(), 0.f, 89.f), SteepDeg = FMath::Clamp(CVarFogSteepDeg.GetValueOnGameThread(), Graze + 1.f, 90.f);
	FogMID->SetScalarParameterValue(TEXT("GrazeSin"), FMath::Sin(FMath::DegreesToRadians(Graze)));
	FogMID->SetScalarParameterValue(TEXT("SteepSin"), FMath::Sin(FMath::DegreesToRadians(SteepDeg)));
}

// ------------------------------------------------------------------------------------------------ queries, the log

float UVLFog::ViewRadius(const AActor* A, float* OutMin, float* OutMax, float* OutEyeHeight)
{
	if (!bActive || !A)
	{
		return 0.f;
	}
	const FEye* E = FindOrMakeEye(A);
	if (!E)
	{
		return 0.f;
	}
	float Min = TNumericLimits<float>::Max();
	for (float R : E->R) { Min = FMath::Min(Min, R); }
	if (OutMin) { *OutMin = Min; }
	if (OutMax) { *OutMax = E->MaxR; }
	if (OutEyeHeight) { *OutEyeHeight = E->EyeH; }
	return E->MeanR;
}

bool UVLFog::Outline(const AActor* A, TArray<FVector>& Out)
{
	const FEye* E = (bActive && A) ? FindOrMakeEye(A) : nullptr;
	if (!E)
	{
		return false;
	}
	Out.Reset(NumDirs * 2);
	for (int32 i = 0; i < NumDirs * 2; ++i)
	{
		const float F = i * 0.5f;
		const int32 D0 = FMath::FloorToInt(F) % NumDirs, D1 = (D0 + 1) % NumDirs;
		const float R = FMath::Lerp(E->R[D0], E->R[D1], F - FMath::FloorToFloat(F));
		const float Ang = 2.f * PI * F / NumDirs;
		const FVector2D P = E->At + FVector2D(FMath::Cos(Ang), FMath::Sin(Ang)) * R;
		Out.Add(FVector(P.X, P.Y, HeightAt(P) + 15.f));
	}
	return true;
}

void UVLFog::GetExplored(TArray<uint8>& Out, int32& OutDim, float& OutCell, FVector2D& OutOrigin) const
{
	Out = Explored;
	OutDim = Dim;
	OutCell = Cell;
	OutOrigin = Origin;
}

bool UVLFog::SetExplored(const TArray<uint8>& In, int32 InDim)
{
	if (!bInit || InDim != Dim || In.Num() != Explored.Num())
	{
		return false;
	}
	Explored = In;
	NextUpdate = 0.0;
	return true;
}

void UVLFog::GetSeen(TArray<const AActor*>& Out) const
{
	Out.Reset();
	for (const TWeakObjectPtr<const AActor>& A : Seen)
	{
		if (A.IsValid()) { Out.Add(A.Get()); }
	}
}

void UVLFog::RestoreLater(const TArray<uint8>& InExplored, int32 InDim, const TArray<const AActor*>& InSeen)
{
	PendingExplored = InExplored;
	PendingDim = InDim;
	bPendingRestore = true;
	PendingSeen.Reset();
	for (const AActor* A : InSeen) { PendingSeen.Add(A); }
}

void UVLFog::LogInfo(const AActor* Focus)
{
	int32 NV = 0, NE = 0;
	for (int32 i = 0; i < Visible.Num(); ++i) { NV += Visible[i]; NE += Explored[i]; }
	const float Tan = FMath::Tan(FMath::DegreesToRadians(CVarFogAngle.GetValueOnGameThread()));
	UE_LOG(LogSovereignRealms, Log, TEXT("fog: %s%s, %d x %d cells of %.0f cm; visible %.1f %%, explored %.1f %%; %d eyes, %d hidden; update %.2f ms (most %.2f) every %.2f s; flat-ground radius %.1f m (eye %.1f m, %.0f deg); material %s"),
		bActive ? TEXT("on") : TEXT("off"), bRevealAll ? TEXT(" (reveal all)") : TEXT(""), Dim, Dim, Cell, Visible.Num() ? 100.f * NV / Visible.Num() : 0.f, Explored.Num() ? 100.f * NE / Explored.Num() : 0.f,
		Eyes.Num(), HiddenNow.Num(), UpdateMs, UpdateMsMax, CVarFogInterval.GetValueOnGameThread(), CVarFogEye.GetValueOnGameThread() / Tan / 100.f, CVarFogEye.GetValueOnGameThread() / 100.f, CVarFogAngle.GetValueOnGameThread(), FogMID ? TEXT("drawn") : TEXT("missing"));
	UpdateMsMax = 0.0;
	if (Focus)
	{
		float Min = 0.f, Max = 0.f, EyeH = 0.f;
		const float R = ViewRadius(Focus, &Min, &Max, &EyeH);
		const FEye* E = Eyes.Find(Focus);
		UE_LOG(LogSovereignRealms, Log, TEXT("fog: played %s at %s (ground %.1f m, feet %.1f m): sees %.1f m mean, %.1f min, %.1f max (eye %.1f m over its feet; state here %d)"), *GetNameSafe(Focus),
			*Focus->GetActorLocation().ToCompactString(), E ? HeightAt(E->At) / 100.f : 0.f, E ? E->FeetZ / 100.f : 0.f, R / 100.f, Min / 100.f, Max / 100.f, EyeH / 100.f, StateAt(FVector2D(Focus->GetActorLocation())));
	}
}

void UVLFog::LogEyes()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	for (const TPair<TWeakObjectPtr<const AActor>, FEye>& P : Eyes)
	{
		const FEye& E = P.Value;
		const FVLBuildingState* B = Battle ? Battle->FindBuilding(E.Actor.Get()) : nullptr;
		float Min = TNumericLimits<float>::Max();
		for (float R : E.R) { Min = FMath::Min(Min, R); }
		UE_LOG(LogSovereignRealms, Log, TEXT("fog eye: %s%s at %.0f %.0f feet %.1f m, eye %.1f m, x%.2f: %.1f / %.1f / %.1f m"), *GetNameSafe(E.Actor.Get()),
			B ? *FString::Printf(TEXT(" (%s level %d)"), VLRules::Name(B->Kind), B->Level) : TEXT(""), E.At.X, E.At.Y, E.FeetZ / 100.f, E.EyeH / 100.f, E.Scale, Min / 100.f, E.MeanR / 100.f, E.MaxR / 100.f);
	}
}
