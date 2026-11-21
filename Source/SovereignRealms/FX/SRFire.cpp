// Copyright Sovereign Realms.

#include "FX/SRFire.h"
#include "Battle/SRBattleSubsystem.h"
#include "Units/SRSprite.h"
#include "ProceduralMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/LocalFogVolumeComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "Materials/MaterialInterface.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"

namespace
{
	// quads per mesh (fixed: the sections are made once and only their vertices move)
	constexpr int32 MaxPuffs = 56;
	constexpr int32 MaxClusters = 8;
	constexpr int32 MaxFlames = 72;
	constexpr int32 QuadCount[3] = { MaxPuffs, MaxFlames, MaxClusters };
	const TCHAR* MaterialPath[3] = { TEXT("/Game/SR/Materials/M_FX_Smoke.M_FX_Smoke"), TEXT("/Game/SR/Materials/M_FX_Flame.M_FX_Flame"), TEXT("/Game/SR/Materials/M_FX_Embers.M_FX_Embers") };

	// the look, in one place
	const FVector Wind(55.f, 125.f, 0.f);            // cm/s, the way the mist and the clouds drift
	// A tongue of flame is a fraction of the building's height: FlameShare of it, never under FlameMin nor over FlameMax
	// (cm, before each tongue's own 0.5 .. 1.2, most of them small, and the fire's growth of 0.8 .. 1.15). A storey is
	// about 300, so the tallest lick on a keep is about a third of a storey: many small low flames, and the smoke is
	// what stands tall. (The first tuning, 0.16 / 45 / 85 with taller tongues, read as flames half the height of the
	// keep: the user asked for them realistic and in proportion.)
	constexpr float FlameShare = 0.11f, FlameMin = 32.f, FlameMax = 60.f;
	constexpr float GlowRadius = 1500.f;
	const FLinearColor GlowColor(1.f, 0.46f, 0.14f);
	const FLinearColor HazeEmissive(1.f, 0.32f, 0.055f);

	// live tuning (the defaults are the shipped look)
	TAutoConsoleVariable<float> CVarFlame(TEXT("sr.Fire.Flame"), 1.f, TEXT("Scale of every tongue of flame on a burning building."));
	TAutoConsoleVariable<float> CVarGlow(TEXT("sr.Fire.Glow"), 150.f, TEXT("The fire's light on the walls and ground, candelas at full strength (the level is lit for an 11 lux sun)."));
	TAutoConsoleVariable<float> CVarHaze(TEXT("sr.Fire.Haze"), 0.12f, TEXT("The glow in the haze round a fire (emissive of its local fog volume)."));
	TAutoConsoleVariable<float> CVarSmoke(TEXT("sr.Fire.Smoke"), 1.f, TEXT("How fast a burning building makes smoke."));

	UMaterialInterface* LoadMat(int32 i)
	{
		static TWeakObjectPtr<UMaterialInterface> Cache[3];
		if (!Cache[i].IsValid()) { Cache[i] = LoadObject<UMaterialInterface>(nullptr, MaterialPath[i], nullptr, LOAD_NoWarn | LOAD_Quiet); }
		return Cache[i].Get();
	}
}

bool ASRBuildingFire::CanDraw()
{
	// asked every frame by every building: a miss is remembered for a few seconds (looking for an asset that is not
	// there is not free), a hit until the materials go away
	static bool bLast = false;
	static double NextLook = 0.0;
	const double Now = FPlatformTime::Seconds();
	if (!bLast && Now < NextLook) { return false; }
	bLast = LoadMat(0) != nullptr && LoadMat(1) != nullptr && LoadMat(2) != nullptr;
	NextLook = Now + 5.0;
	return bLast;
}

ASRBuildingFire::ASRBuildingFire()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;      // after the camera has moved: the quads face it
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	auto Make = [&](const TCHAR* Name, int32 Sort)
	{
		UProceduralMeshComponent* M = CreateDefaultSubobject<UProceduralMeshComponent>(Name);
		M->SetupAttachment(Root);
		M->SetUsingAbsoluteLocation(true);
		M->SetUsingAbsoluteRotation(true);
		M->SetUsingAbsoluteScale(true);
		M->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		M->SetGenerateOverlapEvents(false);
		M->SetCastShadow(false);
		M->bUseAsyncCooking = false;
		M->SetCanEverAffectNavigation(false);
		M->bReceivesDecals = false;
		M->bAffectDynamicIndirectLighting = false;
		M->bAffectDistanceFieldLighting = false;
		M->bVisibleInRayTracing = false;
		M->TranslucencySortPriority = Sort;
		return M;
	};
	SmokeMesh = Make(TEXT("Smoke"), 6);
	FlameMesh = Make(TEXT("Flames"), 7);
	EmberMesh = Make(TEXT("Embers"), 8);

	Glow = CreateDefaultSubobject<UPointLightComponent>(TEXT("Glow"));
	Glow->SetupAttachment(Root);
	Glow->SetMobility(EComponentMobility::Movable);
	Glow->SetIntensityUnits(ELightUnits::Candelas);
	Glow->SetIntensity(0.f);
	Glow->SetAttenuationRadius(GlowRadius);
	Glow->SetSourceRadius(90.f);
	Glow->SetSoftSourceRadius(160.f);
	Glow->SetLightColor(GlowColor);
	Glow->SetCastShadows(false);
	Glow->bAffectTranslucentLighting = false;
	Glow->SetVisibility(false);

	Haze = CreateDefaultSubobject<ULocalFogVolumeComponent>(TEXT("Haze"));
	Haze->SetupAttachment(Root);
	Haze->SetMobility(EComponentMobility::Movable);
	Haze->RadialFogExtinction = 0.025f;
	Haze->HeightFogExtinction = 0.f;
	Haze->FogAlbedo = FLinearColor(0.2f, 0.17f, 0.15f);
	Haze->FogEmissive = FLinearColor::Black;
	Haze->SetVisibility(false);

	Rng.Initialize(FMath::Rand());
}

void ASRBuildingFire::Seat(UStaticMeshComponent* BuildingMesh, const FVector& Centre, const FVector2D& HalfExtent, float Height, bool bLow)
{
	Clusters.Reset();
	Flames.Reset();
	Middle = Centre + FVector(0.f, 0.f, FMath::Min(Height * 0.6f, 420.f));
	const uint32 Hash = GetTypeHash(FIntVector(FMath::RoundToInt32(Centre.X), FMath::RoundToInt32(Centre.Y), bLow ? 1 : 0));
	FRandomStream R;
	R.Initialize(int32(Hash));

	// The mesh's own edges: its vertices dropped into a fine grid, the highest in each cell kept. Roof lines, wall
	// heads, the lips of breaches and the tops of rubble are where vertices are. (Vertex data is kept for the buildings:
	// Tools/import_buildings.py, allow_cpu_access.)
	struct FCell { FVector Top; float H01; float Score; };
	TArray<FCell> Cells;
	float Span = FMath::Max(Height, 200.f);
	const UStaticMesh* SM = BuildingMesh ? BuildingMesh->GetStaticMesh() : nullptr;
	if (SM && SM->GetRenderData() && SM->GetRenderData()->LODResources.Num() > 0)
	{
		const FPositionVertexBuffer& PB = SM->GetRenderData()->LODResources[0].VertexBuffers.PositionVertexBuffer;
		if (PB.GetNumVertices() > 0 && PB.GetVertexData() != nullptr)
		{
			const FTransform Xf = BuildingMesh->GetComponentTransform();
			const float CellCm = 62.f;
			TMap<FIntPoint, FVector> Tops;
			float MaxZ = -1.e9f, MinZ = 1.e9f;
			for (uint32 i = 0; i < PB.GetNumVertices(); ++i)
			{
				const FVector P = Xf.TransformPosition(FVector(PB.VertexPosition(i)));
				if (FMath::Abs(P.X - Centre.X) > HalfExtent.X * 0.94f || FMath::Abs(P.Y - Centre.Y) > HalfExtent.Y * 0.94f) { continue; }
				MaxZ = FMath::Max(MaxZ, float(P.Z));
				MinZ = FMath::Min(MinZ, float(P.Z));
				const FIntPoint K(FMath::FloorToInt32(P.X / CellCm), FMath::FloorToInt32(P.Y / CellCm));
				FVector* T = Tops.Find(K);
				if (!T) { Tops.Add(K, P); }
				else if (P.Z > T->Z) { *T = P; }
			}
			if (MaxZ > MinZ)
			{
				MinZ = FMath::Max(MinZ, float(Centre.Z) - 20.f);
				Span = FMath::Max(MaxZ - MinZ, 100.f);
				for (const TPair<FIntPoint, FVector>& KV : Tops)
				{
					FCell C;
					C.Top = KV.Value;
					C.H01 = (KV.Value.Z - MinZ) / Span;
					if (C.H01 < (bLow ? 0.08f : 0.16f)) { continue; }               // the ground, the yard, the field
					if (!bLow && C.H01 > 0.93f && Span > 700.f) { continue; }        // a standard's pole, a finial
					C.Score = (bLow ? 0.3f : C.H01) + R.FRand() * 0.9f;
					Cells.Add(C);
				}
			}
		}
	}
	// no vertex data (or a mesh with nothing standing): spots over the footprint at roof height
	if (Cells.Num() < 6)
	{
		Cells.Reset();
		for (int32 i = 0; i < 60; ++i)
		{
			FCell C;
			C.H01 = bLow ? 0.3f : 0.8f;
			C.Top = Centre + FVector(R.FRandRange(-0.7f, 0.7f) * HalfExtent.X, R.FRandRange(-0.7f, 0.7f) * HalfExtent.Y, bLow ? 90.f : FMath::Min(Height * 0.8f, 520.f));
			C.Score = R.FRand();
			Cells.Add(C);
		}
	}
	Cells.Sort([](const FCell& A, const FCell& B) { return A.Score > B.Score; });

	// the clusters: spread over the building, the high places first
	const float Size = FMath::Min(HalfExtent.X, HalfExtent.Y);
	const float MinGap = FMath::Clamp(Size * 0.6f, 170.f, 380.f);
	const int32 WantClusters = FMath::Clamp(FMath::RoundToInt32(HalfExtent.X * HalfExtent.Y / 45000.f) + 3, 4, MaxClusters);
	for (const FCell& C : Cells)
	{
		if (Clusters.Num() >= WantClusters) { break; }
		if (!bLow && C.H01 < 0.42f) { continue; }
		bool bFar = true;
		for (const FCluster& S : Clusters) { if (FVector::DistSquared2D(S.Pos, C.Top) < FMath::Square(MinGap)) { bFar = false; break; } }
		if (!bFar) { continue; }
		FCluster S;
		S.Pos = C.Top;
		Clusters.Add(S);
	}
	if (Clusters.Num() == 0 && Cells.Num() > 0) { FCluster S; S.Pos = Cells[0].Top; Clusters.Add(S); }
	// the flames: along the edges near each cluster's heart (down into the breaches under it too), a pace apart
	const float Tongue = FMath::Clamp(Span * FlameShare, FlameMin, FlameMax) * (bLow ? 0.8f : 1.f);
	const float Reach = FMath::Clamp(Size * 0.42f, 130.f, 270.f);
	const int32 PerCluster = FMath::Max(3, MaxFlames / FMath::Max(Clusters.Num(), 1));
	for (int32 c = 0; c < Clusters.Num(); ++c)
	{
		FCluster& S = Clusters[c];
		S.Seed = R.FRand();
		S.Order = Clusters.Num() > 1 ? float(c) / float(Clusters.Num()) : 0.f;
		S.Scale = FMath::Clamp(Size / 420.f, 0.7f, 1.25f) * (bLow ? 0.75f : 1.f);
		const FVector Heart = S.Pos;
		FVector Sum = FVector::ZeroVector;
		int32 Mine = 0;
		for (const FCell& C : Cells)
		{
			if (Mine >= PerCluster || Flames.Num() >= MaxFlames) { break; }
			const float D2 = FVector::DistSquared2D(C.Top, Heart);
			if (D2 > Reach * Reach || C.Top.Z > Heart.Z + 60.f) { continue; }
			bool bFree = true;
			for (const FFlame& F : Flames) { if (FVector::DistSquared(F.Pos, C.Top) < FMath::Square(Tongue * 0.55f)) { bFree = false; break; } }
			if (!bFree) { continue; }
			FFlame F;
			F.Cluster = c;
			F.Pos = C.Top - FVector(0.f, 0.f, Tongue * 0.12f);              // rooted in the edge, not hovering on it
			const float Small = R.FRand();                                   // squared: most tongues are low licks, a few stand up
			const float Big = (0.5f + 0.7f * Small * Small) * (Mine == 0 ? 1.15f : 1.f);
			F.Width = Tongue * Big * R.FRandRange(0.85f, 1.2f);
			F.Height = Tongue * Big * R.FRandRange(1.05f, 1.45f);
			F.Seed = R.FRand();
			F.Delay = Mine == 0 ? 0.f : R.FRandRange(0.05f, 0.6f);
			Flames.Add(F);
			Sum += F.Pos;
			++Mine;
		}
		if (Mine > 0) { S.Pos = Sum / float(Mine); }
	}
	SetActorLocation(Middle);
	Haze->SetWorldScale3D(FVector(FMath::Max(HalfExtent.GetMax() * 2.6f, 900.f) / (2.f * ULocalFogVolumeComponent::GetBaseVolumeSize())));
	Haze->SetWorldLocation(Middle + FVector(0.f, 0.f, 150.f));
}

void ASRBuildingFire::SetStrength(float InStrength)
{
	Target = FMath::Clamp(InStrength, 0.f, 1.f);
	if (Target > 0.f) { bFinishing = false; SetActorTickEnabled(true); }
}

void ASRBuildingFire::Finish()
{
	Target = 0.f;
	bFinishing = true;
	SetActorTickEnabled(true);
}

int32 ASRBuildingFire::NumLit() const
{
	int32 N = 0;
	for (const FFlame& F : Flames) { N += F.Lit > 0.05f ? 1 : 0; }
	return N;
}

void ASRBuildingFire::Emit(const FVector& At, float Scale, float Dark, float Heat, float Alpha)
{
	if (Puffs.Num() >= MaxPuffs) { return; }
	FPuff P;
	P.Pos = At + FVector(Rng.FRandRange(-26.f, 26.f), Rng.FRandRange(-26.f, 26.f), Rng.FRandRange(0.f, 30.f)) * Scale;
	P.Vel = FVector(Rng.FRandRange(-22.f, 22.f), Rng.FRandRange(-22.f, 22.f), Rng.FRandRange(210.f, 290.f) * FMath::Sqrt(Scale));
	P.Life = Rng.FRandRange(4.6f, 6.8f) * FMath::Lerp(0.75f, 1.1f, FMath::Clamp(Scale, 0.f, 1.3f));
	P.Size0 = Rng.FRandRange(60.f, 95.f) * Scale;
	P.Size1 = Rng.FRandRange(380.f, 540.f) * Scale;
	P.Seed = Rng.FRand();
	P.Dark = Dark;
	P.Heat = Heat;
	P.Alpha = Alpha;
	P.Drag = 0.5f;
	P.Lift = 85.f;
	Puffs.Add(P);
}

void ASRBuildingFire::Burst(const FVector& Centre, const FVector2D& HalfExtent, float Height)
{
	SetActorTickEnabled(true);
	Flash = 1.f;
	const float R0 = HalfExtent.GetMax();
	// keep room: the oldest smoke gives way to the pall
	if (Puffs.Num() > MaxPuffs - 26) { Puffs.RemoveAt(0, Puffs.Num() - (MaxPuffs - 26), EAllowShrinking::No); }
	for (int32 i = 0; i < 16; ++i)            // dust rolling out along the ground
	{
		const float A = 2.f * PI * (i + Rng.FRand() * 0.7f) / 16.f;
		const FVector Dir(FMath::Cos(A), FMath::Sin(A), 0.f);
		FPuff P;
		P.Pos = Centre + Dir * R0 * Rng.FRandRange(0.35f, 0.8f) + FVector(0.f, 0.f, Rng.FRandRange(40.f, 110.f));
		P.Vel = Dir * Rng.FRandRange(260.f, 420.f) + FVector(0.f, 0.f, Rng.FRandRange(20.f, 70.f));
		P.Life = Rng.FRandRange(2.6f, 4.2f);
		P.Size0 = Rng.FRandRange(130.f, 190.f);
		P.Size1 = Rng.FRandRange(420.f, 600.f);
		P.Seed = Rng.FRand();
		P.Dark = Rng.FRandRange(0.f, 0.22f);
		P.Heat = 0.f;
		P.Alpha = 0.85f;
		P.Drag = 1.5f;
		P.Lift = 26.f;
		Puffs.Add(P);
	}
	for (int32 i = 0; i < 10; ++i)            // and thrown up out of the middle
	{
		FPuff P;
		P.Pos = Centre + FVector(Rng.FRandRange(-0.5f, 0.5f) * HalfExtent.X, Rng.FRandRange(-0.5f, 0.5f) * HalfExtent.Y, Rng.FRandRange(0.2f, 0.7f) * FMath::Min(Height, 500.f));
		P.Vel = FVector(Rng.FRandRange(-60.f, 60.f), Rng.FRandRange(-60.f, 60.f), Rng.FRandRange(300.f, 520.f));
		P.Life = Rng.FRandRange(3.4f, 5.4f);
		P.Size0 = Rng.FRandRange(140.f, 200.f);
		P.Size1 = Rng.FRandRange(460.f, 640.f);
		P.Seed = Rng.FRand();
		P.Dark = Rng.FRandRange(0.45f, 0.95f);
		P.Heat = Rng.FRandRange(0.2f, 0.7f);
		P.Alpha = 0.95f;
		P.Drag = 1.0f;
		P.Lift = 60.f;
		Puffs.Add(P);
	}
}

void ASRBuildingFire::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);
	Clock += Dt;
	Strength = FMath::FInterpTo(Strength, Target, Dt, Target > Strength ? 1.4f : 0.6f);
	Flash = FMath::Max(0.f, Flash - Dt * 0.8f);

	// ---- clusters catch one after another as the fire grows, and go out the other way
	float LitSum = 0.f;
	FVector LitAt = FVector::ZeroVector;
	for (FCluster& S : Clusters)
	{
		const float Want = FMath::Clamp((Strength * 1.12f - S.Order * 0.95f) * 4.f, 0.f, 1.f) * (bSmoulder ? 0.6f : 1.f);
		S.Lit = FMath::FInterpTo(S.Lit, Want, Dt, 1.2f);
		if (S.Lit <= 0.02f) { continue; }
		LitSum += S.Lit;
		LitAt += S.Pos * S.Lit;
		// smoke: thicker and blacker as it takes hold
		S.Emit += Dt * S.Lit * FMath::Lerp(1.0f, 2.6f, Strength) * (bSmoulder ? 0.6f : 1.f) * CVarSmoke.GetValueOnGameThread();
		if (S.Emit >= 1.f)
		{
			S.Emit -= 1.f;
			const float Big = S.Scale * FMath::Lerp(0.6f, 1.15f, Strength) * FMath::Lerp(0.7f, 1.f, S.Lit);
			Emit(S.Pos + FVector(0.f, 0.f, 60.f), Big, bSmoulder ? Rng.FRandRange(0.35f, 0.6f) : FMath::Lerp(0.6f, 1.f, Strength) * Rng.FRandRange(0.82f, 1.f),
				bSmoulder ? 0.15f : Rng.FRandRange(0.6f, 1.f), FMath::Lerp(0.7f, 1.f, Strength));
		}
	}
	for (FFlame& F : Flames)
	{
		const float C = Clusters.IsValidIndex(F.Cluster) ? Clusters[F.Cluster].Lit : 0.f;
		F.Lit = FMath::FInterpTo(F.Lit, FMath::Clamp((C - F.Delay) / FMath::Max(1.f - F.Delay, 0.2f) * 1.6f, 0.f, 1.f), Dt, 2.2f);
	}

	// ---- smoke: rises fast off the fire, slows, swells and leans away on the wind
	for (int32 i = Puffs.Num() - 1; i >= 0; --i)
	{
		FPuff& P = Puffs[i];
		P.Age += Dt;
		if (P.Age >= P.Life) { Puffs.RemoveAt(i, 1, EAllowShrinking::No); continue; }
		const float T = P.Age / P.Life;
		P.Vel.Z = FMath::FInterpTo(P.Vel.Z, P.Lift, Dt, P.Drag);
		P.Vel.X = FMath::FInterpTo(P.Vel.X, Wind.X * (0.25f + 1.1f * T), Dt, P.Drag * 0.8f);
		P.Vel.Y = FMath::FInterpTo(P.Vel.Y, Wind.Y * (0.25f + 1.1f * T), Dt, P.Drag * 0.8f);
		P.Pos += P.Vel * Dt;
		P.Pos.X += FMath::Sin(Clock * 0.9f + P.Seed * 40.f) * 14.f * Dt;      // the column wavers
	}

	if (LitSum <= 0.f && Puffs.Num() == 0 && Flash <= 0.f && Strength < 0.01f)
	{
		// nothing left to draw
		if (bCreated) { for (UProceduralMeshComponent* M : { SmokeMesh.Get(), FlameMesh.Get(), EmberMesh.Get() }) { M->SetVisibility(false); } }
		Glow->SetVisibility(false);
		Haze->SetVisibility(false);
		if (bFinishing) { Destroy(); return; }
		SetActorTickEnabled(false);
		return;
	}

	// ---- the light it throws on the walls and the ground, and the glow in the haze
	const float Heat = FMath::Clamp(LitSum / 3.f, 0.f, 1.5f) * (bSmoulder ? 0.45f : 1.f) + Flash * 0.8f;
	if (Heat > 0.01f)
	{
		const float Flicker = 0.82f + 0.12f * FMath::Sin(Clock * 11.3f) + 0.09f * FMath::Sin(Clock * 23.7f + 1.3f) + 0.07f * FMath::Sin(Clock * 5.1f + 0.4f);
		Glow->SetWorldLocation((LitSum > 0.f ? LitAt / LitSum : Middle) + FVector(-90.f, 0.f, 130.f));
		Glow->SetIntensity(CVarGlow.GetValueOnGameThread() * Heat * Flicker);
		Glow->SetVisibility(true);
		Haze->SetFogEmissive(HazeEmissive * (CVarHaze.GetValueOnGameThread() * Heat * (0.85f + 0.15f * Flicker)));
		Haze->SetVisibility(true);
	}
	else
	{
		Glow->SetVisibility(false);
		Haze->SetVisibility(false);
	}
	Build();
}

void ASRBuildingFire::Build()
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }
	const FQuat Q = Battle->GetSpriteView().CardRotation;
	const FVector Fwd = Q.GetAxisX(), Right = Q.GetAxisY(), Up = Q.GetAxisZ();

	if (!bCreated)
	{
		UProceduralMeshComponent* Meshes[3] = { SmokeMesh, FlameMesh, EmberMesh };
		for (int32 m = 0; m < 3; ++m)
		{
			UMaterialInterface* Mat = LoadMat(m);
			if (!Mat) { continue; }
			const int32 N = QuadCount[m];
			V[m].Init(GetActorLocation(), N * 4);
			UV0[m].SetNumZeroed(N * 4);
			UV1[m].SetNumZeroed(N * 4);
			Col[m].Init(FLinearColor::Black, N * 4);
			TArray<int32> Tris;
			Tris.Reserve(N * 6);
			for (int32 q = 0; q < N; ++q)
			{
				const int32 B = q * 4;
				UV0[m][B + 0] = FVector2D(0.f, 1.f); UV0[m][B + 1] = FVector2D(1.f, 1.f); UV0[m][B + 2] = FVector2D(1.f, 0.f); UV0[m][B + 3] = FVector2D(0.f, 0.f);
				Tris.Append({ B, B + 1, B + 2, B, B + 2, B + 3 });
			}
			Meshes[m]->CreateMeshSection_LinearColor(0, V[m], Tris, TArray<FVector>(), UV0[m], UV1[m], TArray<FVector2D>(), TArray<FVector2D>(), Col[m], TArray<FProcMeshTangent>(), false, false);
			Meshes[m]->SetMaterial(0, Mat);
		}
		bCreated = true;
	}
	if (V[0].Num() == 0 || V[1].Num() == 0 || V[2].Num() == 0) { return; }     // the materials are not built

	auto Quad = [&](int32 m, int32 q, const FVector& Base, float W, float H, float Lean, float Seed, float Par, const FLinearColor& C)
	{
		const int32 B = q * 4;
		const FVector L = Right * (W * 0.5f), T = Up * H + Right * Lean;
		V[m][B + 0] = Base - L; V[m][B + 1] = Base + L; V[m][B + 2] = Base + L + T; V[m][B + 3] = Base - L + T;
		for (int32 k = 0; k < 4; ++k) { UV1[m][B + k] = FVector2D(Seed, Par); Col[m][B + k] = C; }
	};
	auto Hide = [&](int32 m, int32 q)
	{
		const int32 B = q * 4;
		for (int32 k = 0; k < 4; ++k) { V[m][B + k] = Middle; Col[m][B + k] = FLinearColor(0.f, 0.f, 0.f, 0.f); }
	};

	// ---- smoke, far to near
	Puffs.Sort([&](const FPuff& A, const FPuff& B) { return FVector::DotProduct(A.Pos, Fwd) > FVector::DotProduct(B.Pos, Fwd); });
	for (int32 q = 0; q < MaxPuffs; ++q)
	{
		if (q >= Puffs.Num()) { Hide(0, q); continue; }
		const FPuff& P = Puffs[q];
		const float T = P.Age / P.Life;
		const float Size = FMath::Lerp(P.Size0, P.Size1, FMath::Pow(T, 0.75f));
		const float A = P.Alpha * FMath::Clamp(P.Age / 0.3f, 0.f, 1.f) * FMath::Clamp((1.f - T) / 0.4f, 0.f, 1.f);
		const float Heat = P.Heat * FMath::Clamp(1.f - P.Age / 1.4f, 0.f, 1.f);
		Quad(0, q, P.Pos - Up * (Size * 0.5f), Size, Size, 0.f, P.Seed, T, FLinearColor(A, Heat, P.Dark, T));
	}
	// ---- the flames: each tongue with its own beat, all leaning with the wind
	const float Grow = FMath::Lerp(0.8f, 1.15f, Strength) * CVarFlame.GetValueOnGameThread();
	const float WindLean = FVector::DotProduct(Wind.GetSafeNormal(), Right);
	for (int32 f = 0; f < MaxFlames; ++f)
	{
		if (f >= Flames.Num() || Flames[f].Lit <= 0.02f) { Hide(1, f); continue; }
		const FFlame& F = Flames[f];
		const float Breath = 1.f + 0.1f * FMath::Sin(Clock * 6.3f + F.Seed * 30.f) + 0.07f * FMath::Sin(Clock * 13.1f + F.Seed * 11.f);
		const float H = F.Height * Grow * FMath::Lerp(0.45f, 1.f, F.Lit) * Breath;
		const float W = F.Width * Grow * FMath::Lerp(0.6f, 1.f, F.Lit) * (2.f - Breath);
		const float Lean = H * (0.2f * WindLean + 0.12f * FMath::Sin(Clock * 1.9f + F.Seed * 9.f));
		Quad(1, f, F.Pos - Fwd * 8.f, W, H, Lean, F.Seed, F.Lit, FLinearColor(F.Lit, F.Seed > 0.5f ? 1.f : 0.f, 0.f, 1.f));
	}
	// ---- sparks climbing over each cluster once it has hold
	for (int32 c = 0; c < MaxClusters; ++c)
	{
		const float Sparks = c < Clusters.Num() ? FMath::Clamp((Strength - 0.2f) * 2.2f, 0.f, 1.f) * Clusters[c].Lit * (bSmoulder ? 0.4f : 1.f) : 0.f;
		if (Sparks <= 0.02f) { Hide(2, c); continue; }
		const FCluster& S = Clusters[c];
		Quad(2, c, S.Pos - Fwd * 20.f, 260.f * S.Scale, 460.f * S.Scale, 110.f * WindLean, S.Seed, Sparks, FLinearColor(Sparks, 0.f, 0.f, 1.f));
	}
	UProceduralMeshComponent* Meshes[3] = { SmokeMesh, FlameMesh, EmberMesh };
	for (int32 m = 0; m < 3; ++m)
	{
		Meshes[m]->SetVisibility(true);
		Meshes[m]->UpdateMeshSection_LinearColor(0, V[m], TArray<FVector>(), UV0[m], UV1[m], TArray<FVector2D>(), TArray<FVector2D>(), Col[m], TArray<FProcMeshTangent>(), false);
	}
}
