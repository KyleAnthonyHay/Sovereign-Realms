// Copyright Sovereign Realms.

#include "FX/SRLeaves.h"
#include "Battle/SRBattleSubsystem.h"
#include "Units/SRSprite.h"
#include "Common/SRFeelSettings.h"
#include "ProceduralMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "CollisionQueryParams.h"
#include "Kismet/GameplayStatics.h"
#include "Camera/PlayerCameraManager.h"
#include "Algo/BinarySearch.h"

namespace
{
	constexpr float CellCm = 1000.f;
	const FVector Wind(34.f, 76.f, 0.f);       // cm/s, the way the mist drifts (each leaf also has a drift of its own: FLeaf::Drift)

	// leaf colours by the tree they fall from (linear): 0 fir, 1 oak, 2 birch, 3 maple
	const FLinearColor Palette[4][4] = {
		{ FLinearColor(0.20f, 0.12f, 0.04f), FLinearColor(0.26f, 0.17f, 0.06f), FLinearColor(0.10f, 0.15f, 0.04f), FLinearColor(0.31f, 0.22f, 0.08f) },
		{ FLinearColor(0.13f, 0.22f, 0.04f), FLinearColor(0.24f, 0.28f, 0.05f), FLinearColor(0.42f, 0.33f, 0.05f), FLinearColor(0.30f, 0.17f, 0.04f) },
		{ FLinearColor(0.55f, 0.42f, 0.05f), FLinearColor(0.62f, 0.50f, 0.08f), FLinearColor(0.33f, 0.36f, 0.06f), FLinearColor(0.46f, 0.30f, 0.05f) },
		{ FLinearColor(0.52f, 0.13f, 0.03f), FLinearColor(0.60f, 0.24f, 0.03f), FLinearColor(0.38f, 0.07f, 0.03f), FLinearColor(0.62f, 0.38f, 0.04f) },
	};
}

ASRLeaves::ASRLeaves()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
	Mesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Leaves"));
	SetRootComponent(Mesh);
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Mesh->SetCastShadow(false);
	Mesh->bUseAsyncCooking = false;
	Mesh->SetCanEverAffectNavigation(false);
	Mesh->bReceivesDecals = false;
	Mesh->bAffectDynamicIndirectLighting = false;
	Mesh->bAffectDistanceFieldLighting = false;
	Mesh->bVisibleInRayTracing = false;
}

void ASRLeaves::BeginPlay()
{
	Super::BeginPlay();
	SetActorTransform(FTransform::Identity);   // the mesh's vertices are in world space
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!F.bLeaves || F.LeafCount <= 0) { SetActorTickEnabled(false); return; }
	Rng.Initialize(9173);
	Leaves.SetNum(F.LeafCount);
	if (UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SR/Materials/M_Leaves.M_Leaves"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Mesh->SetMaterial(0, Mat);
	}
	else { SetActorTickEnabled(false); return; }      // art not built: no leaves, nothing breaks
	BuildMesh(true);
}

void ASRLeaves::ReadTrees()
{
	bRead = true;
	Cells.Reset();
	TreeCount = 0;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (!It->ActorHasTag(TEXT("SRTrees"))) { continue; }
		TInlineComponentArray<UInstancedStaticMeshComponent*> Comps(*It);
		for (const UInstancedStaticMeshComponent* C : Comps)
		{
			const UStaticMesh* SM = C->GetStaticMesh();
			if (!SM) { continue; }
			const FString Name = SM->GetName();
			const uint8 Kind = Name.Contains(TEXT("Maple")) ? 3 : (Name.Contains(TEXT("Birch")) ? 2 : (Name.Contains(TEXT("Conifer")) ? 0 : 1));
			if (Name.Contains(TEXT("Snag")) || Name.Contains(TEXT("Bush"))) { continue; }
			const FBox Box = SM->GetBoundingBox();
			const float H = Box.Max.Z, R = FMath::Max(Box.Max.X, Box.Max.Y);
			for (int32 i = 0; i < C->GetInstanceCount(); ++i)
			{
				FTransform Xf;
				if (!C->GetInstanceTransform(i, Xf, true)) { continue; }
				FTree T;
				T.Base = Xf.GetLocation();
				const float S = Xf.GetScale3D().Z;
				T.Height = H * S;
				T.Radius = R * S;
				T.Kind = Kind;
				T.Weight = Kind == 0 ? 0.2f : 1.f;
				Cells.FindOrAdd(FIntPoint(FMath::FloorToInt32(T.Base.X / CellCm), FMath::FloorToInt32(T.Base.Y / CellCm))).Add(T);
				++TreeCount;
			}
		}
	}
}

void ASRLeaves::Gather(const FVector2D& Focus, float Radius)
{
	Near.Reset();
	NearCum.Reset();
	NearWeight = 0.f;
	const int32 X0 = FMath::FloorToInt32((Focus.X - Radius) / CellCm), X1 = FMath::FloorToInt32((Focus.X + Radius) / CellCm);
	const int32 Y0 = FMath::FloorToInt32((Focus.Y - Radius) / CellCm), Y1 = FMath::FloorToInt32((Focus.Y + Radius) / CellCm);
	for (int32 x = X0; x <= X1; ++x)
	{
		for (int32 y = Y0; y <= Y1; ++y)
		{
			if (const TArray<FTree>* List = Cells.Find(FIntPoint(x, y)))
			{
				for (const FTree& T : *List)
				{
					if (FVector2D::DistSquared(FVector2D(T.Base), Focus) > Radius * Radius) { continue; }
					Near.Add(T);
					NearWeight += T.Weight;
					NearCum.Add(NearWeight);
				}
			}
		}
	}
	GatheredAt = Focus;
}

void ASRLeaves::Spawn(FLeaf& L, bool bMidAir)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const float Pick = Rng.FRand() * NearWeight;
	const int32 Index = FMath::Clamp(Algo::LowerBound(NearCum, Pick), 0, Near.Num() - 1);
	const FTree& T = Near[Index];
	// Most let go of the outside of the crown (its downwind side more than its upwind), where the camera, which looks
	// down on the canopy, can see them from the first moment: a leaf that starts inside the crown falls hidden under
	// it all the way down. The crown narrows toward its top.
	const bool bOuter = Rng.FRand() < 0.75f;
	float A = Rng.FRandRange(0.f, 2.f * PI);
	if (bOuter && Rng.FRand() < 0.5f) { A = FMath::Atan2(Wind.Y, Wind.X) + Rng.FRandRange(-1.2f, 1.2f); }
	const float Up = bOuter ? Rng.FRandRange(0.6f, 1.02f) : Rng.FRandRange(0.42f, 0.9f);
	const float D = bOuter ? T.Radius * Rng.FRandRange(0.8f, 1.08f) * (1.f - 0.65f * FMath::Clamp((Up - 0.62f) / 0.4f, 0.f, 1.f)) : T.Radius * FMath::Sqrt(Rng.FRand()) * 0.95f;
	const float Top = T.Base.Z + T.Height * Up;
	L.Pos = FVector(T.Base.X + FMath::Cos(A) * D, T.Base.Y + FMath::Sin(A) * D, Top);
	L.GroundZ = T.Base.Z + 4.f;
	// (the ground under where it will land, not under the trunk: one trace a leaf)
	{
		FHitResult Hit;
		const float FallTime = (Top - T.Base.Z) / 55.f;
		const FVector2D Land = FVector2D(L.Pos) + (FVector2D(Wind) * 0.8f + FVector2D(FMath::Cos(A), FMath::Sin(A)) * 45.f) * FallTime;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(SRLeafGround), false);
		if (GetWorld()->LineTraceSingleByObjectType(Hit, FVector(Land, Top + 200.f), FVector(Land, T.Base.Z - 1500.f), FCollisionObjectQueryParams(ECC_WorldStatic), Params))
		{
			L.GroundZ = FMath::Min(float(Hit.ImpactPoint.Z) + 4.f, Top - 50.f);
		}
	}
	L.Fall = Rng.FRandRange(46.f, 84.f);
	// its own way out from the tree, on top of the wind: leaves come off every side of a wood, not only its lee
	L.Drift = FVector2D(FMath::Cos(A), FMath::Sin(A)) * Rng.FRandRange(20.f, 70.f);
	L.Phase = Rng.FRandRange(0.f, 2.f * PI);
	L.Rate = Rng.FRandRange(1.5f, 3.1f);
	L.Swing = Rng.FRandRange(34.f, 78.f);
	L.Tumble = Rng.FRand() < 0.55f ? Rng.FRandRange(2.2f, 5.5f) * (Rng.FRand() < 0.5f ? -1.f : 1.f) : 0.f;      // over and over, or rocking only
	L.Flip = Rng.FRandRange(0.f, 2.f * PI);
	L.Heading = Rng.FRandRange(0.f, 2.f * PI);
	L.Spin = Rng.FRandRange(0.f, 2.f * PI);
	L.SpinRate = Rng.FRandRange(1.4f, 4.2f) * (Rng.FRand() < 0.5f ? -1.f : 1.f);
	L.Roll = Rng.FRandRange(0.f, 2.f * PI);
	L.Size = F.LeafSize * Rng.FRandRange(0.75f, 1.25f) * (T.Kind == 0 ? 0.6f : 1.f);
	L.Rest = -1.f;
	L.bAlive = true;
	const FLinearColor C = Palette[T.Kind][Rng.RandRange(0, 3)];
	const float V = Rng.FRandRange(0.95f, 1.45f);         // a shade brighter than the crown it left, or it is lost against it
	L.Color = FLinearColor(C.R * V, C.G * V, C.B * V, 1.f);
	if (bMidAir) { L.Pos.Z = FMath::Lerp(L.GroundZ, Top, Rng.FRand()); }
}

int32 ASRLeaves::NumFalling() const
{
	int32 N = 0;
	for (const FLeaf& L : Leaves) { N += L.bAlive ? 1 : 0; }
	return N;
}

void ASRLeaves::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }
	if (!bRead) { ReadTrees(); }
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);
	Clock += Dt;

	// the trees in view: round the camera's focus, as far as the sprites are drawn (no further than leaves can be seen)
	const FSRSpriteView& View = Battle->GetSpriteView();
	// (about what the screen shows: the camera's own distance from its focus; close in, the same leaves fall thick over a
	// few trees, far out they thin over a whole wood, where they are too small to count anyway)
	float Radius = 2500.f;
	if (const APlayerCameraManager* Cam = UGameplayStatics::GetPlayerCameraManager(this, 0))
	{
		// (0.8 of it reaches the corners of the frame at every camera angle; at 1.25, most of the leaves fell on trees the
		// screen never showed, and a close view had two or three in it)
		Radius = FVector::Dist2D(Cam->GetCameraLocation(), FVector(View.FocusXY, 0.f)) * 0.8f;
	}
	Radius = FMath::Clamp(FMath::Min(Radius, View.CullRadius), 800.f, 4500.f);
	GatherTimer -= Dt;
	const bool bJumped = FVector2D::DistSquared(View.FocusXY, GatheredAt) > FMath::Square(Radius * 0.6f);
	if (GatherTimer <= 0.f || bJumped)
	{
		GatherTimer = 0.6f;
		Gather(View.FocusXY, Radius);
	}
	const int32 Want = Near.Num() > 0 ? FMath::Min(Leaves.Num(), FMath::CeilToInt32(NearWeight * F.LeavesPerTree)) : 0;

	int32 Alive = 0;
	const float Gust = 0.8f + 0.4f * FMath::Sin(Clock * 0.31f) + 0.25f * FMath::Sin(Clock * 0.83f + 1.7f);
	for (FLeaf& L : Leaves)
	{
		if (!L.bAlive) { continue; }
		if (L.Rest > 0.f)
		{
			L.Rest -= Dt;
			if (L.Rest <= 0.f) { L.bAlive = false; continue; }
			++Alive;
			continue;
		}
		// gone from view: let it go (its place is wanted where the camera is now)
		if (FVector2D::DistSquared(FVector2D(L.Pos), View.FocusXY) > FMath::Square(Radius * 1.25f)) { L.bAlive = false; continue; }
		++Alive;
		L.Phase += L.Rate * Dt;
		const float Sw = FMath::Sin(L.Phase), Cw = FMath::Cos(L.Phase);
		// side-slip: it swings across, falling fastest through the middle of each swing and hanging at the ends
		const FVector Side(FMath::Cos(L.Heading), FMath::Sin(L.Heading), 0.f);
		L.Heading += 0.35f * Dt;
		L.Pos += Side * (Cw * L.Swing * L.Rate * Dt) + Wind * (Gust * Dt) + FVector(L.Drift, 0.f) * Dt;
		L.Pos.Z -= L.Fall * (0.45f + 0.75f * Cw * Cw) * FMath::Clamp(1.5f - 0.6f * Gust, 0.45f, 1.2f) * Dt;      // a gust holds it up
		L.Spin += L.SpinRate * Dt * (0.4f + FMath::Abs(Cw));
		L.Flip += L.Tumble * Dt * (0.5f + 0.5f * Gust);
		L.Roll = Sw * 1.1f + L.Flip;
		if (L.Pos.Z <= L.GroundZ)
		{
			L.Pos.Z = L.GroundZ;
			L.Rest = Rng.FRandRange(3.f, 6.5f);
		}
	}
	// new leaves let go: a steady fall, never a burst (a camera jump fills the air at once, part-way down)
	if (bJumped && Want > 0)
	{
		for (FLeaf& L : Leaves) { if (Alive >= Want) { break; } if (!L.bAlive) { Spawn(L, true); ++Alive; } }
	}
	else if (Alive < Want)
	{
		SpawnDebt = FMath::Min(SpawnDebt + Dt * FMath::Max(Want / 9.f, 2.f), 12.f);
		for (FLeaf& L : Leaves)
		{
			if (SpawnDebt < 1.f || Alive >= Want) { break; }
			if (!L.bAlive) { Spawn(L, false); ++Alive; SpawnDebt -= 1.f; }
		}
	}
	BuildMesh(false);
}

void ASRLeaves::BuildMesh(bool bCreate)
{
	const int32 N = Leaves.Num();
	Verts.SetNumUninitialized(N * 4);
	Colors.SetNumUninitialized(N * 4);
	TArray<int32> Tris;
	if (bCreate)
	{
		UVs.SetNumUninitialized(N * 4);
		Normals.Init(FVector::UpVector, N * 4);        // lit like the ground it falls to, from either side
		Tris.Reserve(N * 6);
	}
	for (int32 i = 0; i < N; ++i)
	{
		const FLeaf& L = Leaves[i];
		FVector* V = &Verts[i * 4];
		FLinearColor C = L.Color;
		if (!L.bAlive)
		{
			V[0] = V[1] = V[2] = V[3] = FVector::ZeroVector;
		}
		else
		{
			float Size = L.Size;
			FVector A, B;      // along the leaf, across it
			if (L.Rest > 0.f)
			{
				Size *= FMath::Clamp(L.Rest / 0.8f, 0.f, 1.f);                  // shrinks away at the end
				A = FVector(FMath::Cos(L.Spin), FMath::Sin(L.Spin), 0.f);
				B = FVector(-A.Y, A.X, 0.f);
				C.R *= 0.82f; C.G *= 0.82f; C.B *= 0.82f;
			}
			else
			{
				const float cs = FMath::Cos(L.Spin), sn = FMath::Sin(L.Spin);
				const float cr = FMath::Cos(L.Roll), sr = FMath::Sin(L.Roll);
				A = FVector(cs, sn, 0.22f * sr).GetSafeNormal();
				const FVector Flat(-sn, cs, 0.f);
				B = (Flat * cr + FVector::UpVector * sr).GetSafeNormal();
				// it catches the light as it turns: bright when its face is to the sky, dull edge-on (the material lights
				// every leaf from above, so this flicker is what shows it tumbling)
				const float Catch = 0.62f + 0.6f * FMath::Abs(cr);
				C.R *= Catch; C.G *= Catch; C.B *= Catch;
			}
			A *= Size * 0.5f;
			B *= Size * 0.34f;
			V[0] = L.Pos - A - B; V[1] = L.Pos + A - B; V[2] = L.Pos + A + B; V[3] = L.Pos - A + B;
		}
		for (int32 k = 0; k < 4; ++k) { Colors[i * 4 + k] = C; }
		if (bCreate)
		{
			const int32 Base = i * 4;
			UVs[Base] = FVector2D(0.f, 0.f); UVs[Base + 1] = FVector2D(1.f, 0.f); UVs[Base + 2] = FVector2D(1.f, 1.f); UVs[Base + 3] = FVector2D(0.f, 1.f);
			Tris.Append({ Base, Base + 1, Base + 2, Base, Base + 2, Base + 3 });
		}
	}
	if (bCreate)
	{
		for (FLinearColor& C : Colors) { C = FLinearColor::Black; }
		Mesh->CreateMeshSection_LinearColor(0, Verts, Tris, Normals, UVs, Colors, TArray<FProcMeshTangent>(), false, false);
	}
	else
	{
		Mesh->UpdateMeshSection_LinearColor(0, Verts, TArray<FVector>(), TArray<FVector2D>(), Colors, TArray<FProcMeshTangent>(), false);
	}
}
