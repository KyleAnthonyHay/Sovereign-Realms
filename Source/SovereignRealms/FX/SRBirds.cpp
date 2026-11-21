// Copyright Sovereign Realms.

#include "FX/SRBirds.h"
#include "Common/SRFeelSettings.h"
#include "ProceduralMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "Engine/World.h"
#include "CollisionQueryParams.h"

namespace
{
	constexpr int32 VertsPerBird = 12;   // nose, tail; per wing: shoulder front / back, elbow front / back, tip
	constexpr int32 TrisPerBird = 8;     // the body's two, three per wing

	// the three kinds, by flock: a loose cloud of gulls, a loose cloud of rooks, a skein of geese in a V
	struct FKind { FLinearColor Body, Tip; float SpanScale; FVector2D FlapRate; FVector2D FlapTime, GlideTime; };
	const FKind Kinds[3] = {
		{ FLinearColor(0.62f, 0.60f, 0.54f), FLinearColor(0.16f, 0.16f, 0.17f), 1.0f,  FVector2D(2.4f, 3.2f), FVector2D(1.2f, 2.6f), FVector2D(1.0f, 2.8f) },   // gulls: long glides
		{ FLinearColor(0.07f, 0.07f, 0.08f), FLinearColor(0.04f, 0.04f, 0.05f), 0.85f, FVector2D(3.4f, 4.4f), FVector2D(1.8f, 3.6f), FVector2D(0.5f, 1.2f) },   // rooks: busy wings
		{ FLinearColor(0.40f, 0.37f, 0.31f), FLinearColor(0.12f, 0.11f, 0.10f), 1.25f, FVector2D(2.2f, 2.8f), FVector2D(3.0f, 6.0f), FVector2D(0.6f, 1.4f) },   // geese: steady beats
	};
}

ASRBirds::ASRBirds()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
	Mesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Birds"));
	SetRootComponent(Mesh);
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Mesh->SetCastShadow(false);
	Mesh->bUseAsyncCooking = false;
	Mesh->SetCanEverAffectNavigation(false);
}

void ASRBirds::BeginPlay()
{
	Super::BeginPlay();
	SetActorTransform(FTransform::Identity);   // the mesh's vertices are in world space
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!F.bBirds || F.BirdFlocks <= 0) { SetActorTickEnabled(false); return; }
	Rng.Initialize(4711);

	const float Half = FMath::Min(F.MapHalfExtent.X, F.MapHalfExtent.Y);
	for (int32 f = 0; f < F.BirdFlocks; ++f)
	{
		FFlock Fl;
		// loops of every size, spread from close round the middle to out along the mountains
		const float t = F.BirdFlocks > 1 ? float(f) / float(F.BirdFlocks - 1) : 0.5f;
		Fl.Radius = FMath::Min(FMath::Lerp(F.BirdLoopRadius.X, F.BirdLoopRadius.Y, t) * Rng.FRandRange(0.9f, 1.1f), Half * 0.92f);
		Fl.Squash = Rng.FRandRange(0.55f, 0.95f);
		Fl.Spin = Rng.FRandRange(0.f, PI);
		Fl.Centre = FVector2D(Rng.FRandRange(-1.f, 1.f), Rng.FRandRange(-1.f, 1.f)) * FMath::Max(0.f, Half - Fl.Radius) * 0.5f;
		Fl.Wobble2 = Rng.FRandRange(0.06f, 0.2f);
		Fl.Wobble3 = Rng.FRandRange(0.03f, 0.12f);
		Fl.Phase2 = Rng.FRandRange(0.f, 2.f * PI);
		Fl.Phase3 = Rng.FRandRange(0.f, 2.f * PI);
		Fl.Theta = Rng.FRandRange(0.f, 2.f * PI);
		Fl.Dir = (f % 2 == 0) ? 1.f : -1.f;
		Fl.Speed = F.BirdSpeed * Rng.FRandRange(0.8f, 1.2f);
		Fl.Height = Rng.FRandRange(F.BirdHeight.X, F.BirdHeight.Y);
		const FVector2D P = LoopPoint(Fl, Fl.Theta);
		Fl.GroundZ = GroundAt(P);
		Fl.Pos = FVector(P, Fl.GroundZ + Fl.Height);
		const FVector2D D = (LoopPoint(Fl, Fl.Theta + 0.01f * Fl.Dir) - P).GetSafeNormal();
		Fl.Fwd = FVector(D, 0.f);
		Fl.GroundTimer = Rng.FRandRange(0.f, 0.25f);
		const int32 FlockIndex = Flocks.Add(Fl);

		const int32 Kind = (f % 5 == 3) ? 2 : ((f % 3 == 1) ? 1 : 0);
		const FKind& K = Kinds[Kind];
		const int32 Count = Rng.RandRange(FMath::Max(1, F.BirdsPerFlock.X), FMath::Max(F.BirdsPerFlock.X, F.BirdsPerFlock.Y));
		const float Size = 250.f + 55.f * Count;   // how loose the cloud is (cm)
		for (int32 i = 0; i < Count; ++i)
		{
			FBird B;
			B.Flock = FlockIndex;
			B.Span = F.BirdSpan * K.SpanScale * Rng.FRandRange(0.85f, 1.15f);
			if (Kind == 2)
			{
				// a V: the leader at the point, the rest down two arms
				const int32 Rank = (i + 1) / 2;
				const float Side = (i % 2 == 0) ? 1.f : -1.f;
				B.Offset = FVector(-Rank * B.Span * 2.1f, i == 0 ? 0.f : Side * Rank * B.Span * 1.9f, Rng.FRandRange(-20.f, 20.f));
				B.Drift = FVector(25.f, 25.f, 15.f);
			}
			else
			{
				B.Offset = FVector(Rng.FRandRange(-Size, Size), Rng.FRandRange(-Size, Size) * 0.8f, Rng.FRandRange(-Size, Size) * 0.25f);
				B.Drift = FVector(Size * 0.25f, Size * 0.25f, Size * 0.12f);
			}
			B.DriftRate = Rng.FRandRange(0.15f, 0.45f);
			B.DriftPhase = Rng.FRandRange(0.f, 2.f * PI);
			B.FlapRate = Rng.FRandRange(K.FlapRate.X, K.FlapRate.Y);
			B.Flap = Rng.FRandRange(0.f, 2.f * PI);
			B.bFlapping = Rng.FRand() < 0.6f;
			B.Mode = B.bFlapping ? 1.f : 0.f;
			B.ModeTimer = Rng.FRandRange(0.f, 2.f);
			B.Kind = Kind;
			B.Body = K.Body;
			B.Tip = K.Tip;
			Birds.Add(B);
		}
	}

	if (UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SR/Materials/M_Birds.M_Birds"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Mesh->SetMaterial(0, Mat);
	}
	BuildMesh(true);
}

FVector2D ASRBirds::LoopPoint(const FFlock& Fl, float Theta) const
{
	const float R = Fl.Radius * (1.f + Fl.Wobble2 * FMath::Sin(2.f * Theta + Fl.Phase2) + Fl.Wobble3 * FMath::Sin(3.f * Theta + Fl.Phase3));
	const FVector2D L(R * FMath::Cos(Theta), R * Fl.Squash * FMath::Sin(Theta));
	return Fl.Centre + L.GetRotated(FMath::RadiansToDegrees(Fl.Spin));
}

float ASRBirds::GroundAt(const FVector2D& XY) const
{
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SRBirdsGround), false);
	// (the water sheets are not WorldStatic: over a lake this finds its bed, a little under the surface)
	if (GetWorld() && GetWorld()->LineTraceSingleByObjectType(Hit, FVector(XY, 30000.f), FVector(XY, -5000.f), FCollisionObjectQueryParams(ECC_WorldStatic), Params))
	{
		return Hit.ImpactPoint.Z;
	}
	return 0.f;
}

void ASRBirds::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);
	Clock += Dt;

	for (FFlock& Fl : Flocks)
	{
		// along the loop at the flock's speed (the loop's own stretch per radian varies, so measure it)
		const FVector2D P0 = LoopPoint(Fl, Fl.Theta);
		const float Stretch = FMath::Max((LoopPoint(Fl, Fl.Theta + 0.005f) - LoopPoint(Fl, Fl.Theta - 0.005f)).Size() / 0.01f, 1.f);
		Fl.Theta = FMath::Fmod(Fl.Theta + Fl.Dir * Fl.Speed * Dt / Stretch, 2.f * PI);
		const FVector2D P1 = LoopPoint(Fl, Fl.Theta);
		const FVector NewFwd = FVector((P1 - P0).GetSafeNormal(), 0.f);
		if (!NewFwd.IsNearlyZero())
		{
			// bank into the turn (right wing down turning right)
			const float Turn = FVector::CrossProduct(Fl.Fwd, NewFwd).Z / FMath::Max(Dt, 1e-3f);
			Fl.Bank = FMath::FInterpTo(Fl.Bank, FMath::Clamp(Turn * 1.2f, -0.6f, 0.6f), Dt, 2.f);
			Fl.Fwd = NewFwd;
		}
		// the ground ahead and below: climb early for a hill, sink back slowly after it
		Fl.GroundTimer -= Dt;
		if (Fl.GroundTimer <= 0.f)
		{
			Fl.GroundTimer = 0.25f;
			Fl.GroundZ = FMath::Max(GroundAt(P1), GroundAt(P1 + FVector2D(Fl.Fwd) * Fl.Speed * 2.f));
		}
		const float WantZ = Fl.GroundZ + Fl.Height + FMath::Sin(Clock * 0.21f + Fl.Phase2) * 250.f;
		Fl.Pos = FVector(P1, FMath::FInterpTo(Fl.Pos.Z, WantZ, Dt, WantZ > Fl.Pos.Z ? 1.2f : 0.35f));
	}

	for (FBird& B : Birds)
	{
		const FKind& K = Kinds[B.Kind];
		B.ModeTimer -= Dt;
		if (B.ModeTimer <= 0.f)
		{
			B.bFlapping = !B.bFlapping;
			B.ModeTimer = B.bFlapping ? Rng.FRandRange(K.FlapTime.X, K.FlapTime.Y) : Rng.FRandRange(K.GlideTime.X, K.GlideTime.Y);
		}
		B.Mode = FMath::FInterpTo(B.Mode, B.bFlapping ? 1.f : 0.f, Dt, 4.f);
		// gliding wings settle level with the downstroke's end rather than snapping
		B.Flap = FMath::Fmod(B.Flap + 2.f * PI * B.FlapRate * Dt * FMath::Max(B.Mode, 0.15f), 2.f * PI);
	}
	BuildMesh(false);
}

void ASRBirds::BuildMesh(bool bCreate)
{
	const int32 N = Birds.Num();
	Verts.SetNumUninitialized(N * VertsPerBird);
	if (bCreate)
	{
		Tris.Reset(N * TrisPerBird * 3);
		Colors.SetNumUninitialized(N * VertsPerBird);
	}
	for (int32 b = 0; b < N; ++b)
	{
		const FBird& B = Birds[b];
		const FFlock& Fl = Flocks[B.Flock];
		const FVector Fwd = Fl.Fwd;
		const FVector Right0 = FVector::CrossProduct(FVector::UpVector, Fwd);
		const float cb = FMath::Cos(Fl.Bank), sb = FMath::Sin(Fl.Bank);
		const FVector Right = Right0 * cb - FVector::UpVector * sb;
		const FVector Up = FVector::UpVector * cb + Right0 * sb;

		const FVector Wander(B.Drift.X * FMath::Sin(Clock * B.DriftRate + B.DriftPhase), B.Drift.Y * FMath::Sin(Clock * B.DriftRate * 1.3f + B.DriftPhase + 1.f),
			B.Drift.Z * FMath::Sin(Clock * B.DriftRate * 0.7f + B.DriftPhase + 2.f));
		const FVector O = B.Offset + Wander;
		const float H = B.Span * 0.5f, L = B.Span * 0.42f;
		const float Beat = FMath::Sin(B.Flap);
		const float TipZ = FMath::Lerp(0.12f * H, Beat * 0.6f * H, B.Mode);
		const float ElbowZ = FMath::Lerp(0.06f * H, FMath::Sin(B.Flap - 0.5f) * 0.25f * H, B.Mode);
		const FVector C = Fl.Pos + Fwd * O.X + Right0 * O.Y + FVector::UpVector * O.Z - Up * (Beat * 0.06f * H * B.Mode);
		auto At = [&](float f, float r, float u) { return C + Fwd * f + Right * r + Up * u; };

		FVector* V = &Verts[b * VertsPerBird];
		V[0] = At(0.5f * L, 0.f, 0.f);
		V[1] = At(-0.5f * L, 0.f, 0.f);
		for (int32 s = 0; s < 2; ++s)
		{
			const float Sg = s == 0 ? -1.f : 1.f;
			FVector* W = V + 2 + s * 5;
			W[0] = At(0.15f * L, Sg * 0.08f * H, 0.f);          // shoulder, front
			W[1] = At(-0.2f * L, Sg * 0.08f * H, 0.f);          // shoulder, back
			W[2] = At(0.1f * L, Sg * 0.5f * H, ElbowZ);         // elbow, front
			W[3] = At(-0.15f * L, Sg * 0.5f * H, ElbowZ);       // elbow, back
			W[4] = At(-0.3f * L, Sg * H, TipZ);                 // tip (swept back)
		}
		if (bCreate)
		{
			const int32 Base = b * VertsPerBird;
			for (int32 k = 0; k < VertsPerBird; ++k) { Colors[Base + k] = B.Body; }
			Colors[Base + 6] = B.Tip;
			Colors[Base + 11] = B.Tip;
			const int32 SFL = Base + 2, SFR = Base + 7;
			Tris.Append({ Base + 0, SFR, Base + 1, Base + 0, Base + 1, SFL });
			for (int32 s = 0; s < 2; ++s)
			{
				const int32 W = Base + 2 + s * 5;   // 0 shoulder front, 1 shoulder back, 2 elbow front, 3 elbow back, 4 tip
				Tris.Append({ W + 0, W + 2, W + 3, W + 0, W + 3, W + 1, W + 2, W + 4, W + 3 });
			}
		}
	}
	if (bCreate)
	{
		Mesh->CreateMeshSection_LinearColor(0, Verts, Tris, TArray<FVector>(), TArray<FVector2D>(), Colors, TArray<FProcMeshTangent>(), false);
	}
	else
	{
		Mesh->UpdateMeshSection_LinearColor(0, Verts, TArray<FVector>(), TArray<FVector2D>(), TArray<FLinearColor>(), TArray<FProcMeshTangent>());
	}
}
