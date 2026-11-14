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
	TArray<int32> Tris;
	TArray<FVector> Normals;
	TArray<FVector2D> UVs;
	Verts.Reserve(Segments * 2);
	Tris.Reserve(Segments * 6);

	for (int32 i = 0; i < Segments; ++i)
	{
		const float Angle = 2.f * PI * i / Segments;
		const FVector Dir(FMath::Cos(Angle), FMath::Sin(Angle), 0.f);
		Verts.Add(Dir * InnerRadius);
		Verts.Add(Dir * OuterRadius);
		Normals.Add(FVector::UpVector);
		Normals.Add(FVector::UpVector);
		const float InnerFrac = InnerRadius / OuterRadius;
		UVs.Add(FVector2D(0.5f + 0.5f * Dir.X * InnerFrac, 0.5f + 0.5f * Dir.Y * InnerFrac));
		UVs.Add(FVector2D(0.5f + 0.5f * Dir.X, 0.5f + 0.5f * Dir.Y));
	}
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
