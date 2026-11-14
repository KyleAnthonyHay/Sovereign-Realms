// Copyright Sovereign Realms.

#include "Common/SRRingComponent.h"
#include "Battle/SRBattleSubsystem.h"
#include "Materials/MaterialInstanceDynamic.h"

USRRingComponent::USRRingComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryComponentTick.bCanEverTick = false;
	SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SetGenerateOverlapEvents(false);
	SetCastShadow(false);
	bUseAsyncCooking = false;
}

void USRRingComponent::BuildRing(float InnerRadius, float OuterRadius, int32 Segments)
{
	Segments = FMath::Max(Segments, 8);

	TArray<FVector> Verts;
	TArray<FVector2D> UVs;
	Verts.Reserve(Segments * 2);

	for (int32 i = 0; i < Segments; ++i)
	{
		const float Angle = 2.f * PI * i / Segments;
		const FVector Dir(FMath::Cos(Angle), FMath::Sin(Angle), 0.f);
		Verts.Add(Dir * InnerRadius);
		Verts.Add(Dir * OuterRadius);
		const float InnerFrac = InnerRadius / OuterRadius;
		UVs.Add(FVector2D(0.5f + 0.5f * Dir.X * InnerFrac, 0.5f + 0.5f * Dir.Y * InnerFrac));
		UVs.Add(FVector2D(0.5f + 0.5f * Dir.X, 0.5f + 0.5f * Dir.Y));
	}
	FinishMesh(Verts, UVs, Segments);
}

void USRRingComponent::BuildRoundedRect(const FVector2D& HalfExtent, float CornerRadius, float Width, int32 CornerSegments)
{
	CornerSegments = FMath::Max(CornerSegments, 2);
	const float R = FMath::Clamp(CornerRadius, Width, FMath::Min(HalfExtent.X, HalfExtent.Y));
	// The material shades by the distance from the centre of UV space (1 = the outer edge): give every outer vertex
	// a UV on the unit circle along its outward normal, every inner vertex the same direction a little shorter.
	const float InnerFrac = 0.72f;

	TArray<FVector> Verts;
	TArray<FVector2D> UVs;
	const FVector2D Corners[4] = { FVector2D(1.f, 1.f), FVector2D(-1.f, 1.f), FVector2D(-1.f, -1.f), FVector2D(1.f, -1.f) };
	for (int32 c = 0; c < 4; ++c)
	{
		const FVector2D Centre((HalfExtent.X - R) * Corners[c].X, (HalfExtent.Y - R) * Corners[c].Y);
		for (int32 k = 0; k <= CornerSegments; ++k)
		{
			const float Angle = (c + float(k) / CornerSegments) * 0.5f * PI;
			const FVector2D Dir(FMath::Cos(Angle), FMath::Sin(Angle));
			const FVector2D Outer = Centre + Dir * R;
			const FVector2D Inner = Centre + Dir * (R - Width);
			Verts.Add(FVector(Inner.X, Inner.Y, 0.f));
			Verts.Add(FVector(Outer.X, Outer.Y, 0.f));
			UVs.Add(FVector2D(0.5f, 0.5f) + Dir * 0.5f * InnerFrac);
			UVs.Add(FVector2D(0.5f, 0.5f) + Dir * 0.5f);
		}
	}
	FinishMesh(Verts, UVs, Verts.Num() / 2);
}

void USRRingComponent::FinishMesh(const TArray<FVector>& Verts, const TArray<FVector2D>& UVs, int32 Segments)
{
	TArray<int32> Tris;
	TArray<FVector> Normals;
	Tris.Reserve(Segments * 12);
	Normals.Init(FVector::UpVector, Verts.Num());
	for (int32 i = 0; i < Segments; ++i)
	{
		const int32 I0 = i * 2, O0 = i * 2 + 1;
		const int32 I1 = ((i + 1) % Segments) * 2, O1 = I1 + 1;
		// Both windings so the ring is visible whatever the material's culling.
		Tris.Append({ I0, O0, O1,  I0, O1, I1,  I0, O1, O0,  I0, I1, O1 });
	}

	CreateMeshSection_LinearColor(0, Verts, Tris, Normals, UVs, TArray<FLinearColor>(), TArray<FProcMeshTangent>(), false);

	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		RingMID = UMaterialInstanceDynamic::Create(Battle->RingMaterial, this);
		SetMaterial(0, RingMID);
	}
}

void USRRingComponent::SetRingColor(const FLinearColor& Color, float Opacity)
{
	if (RingMID)
	{
		RingMID->SetVectorParameterValue(TEXT("Color"), Color);
		RingMID->SetScalarParameterValue(TEXT("Opacity"), Opacity);
	}
}
