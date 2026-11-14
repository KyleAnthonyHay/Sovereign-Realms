// Copyright Sovereign Realms.

#include "Buildings/SRPlacementPreview.h"
#include "Battle/SRGridSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"

namespace
{
	const FLinearColor Good(0.25f, 1.f, 0.4f);
	const FLinearColor Bad(1.f, 0.18f, 0.12f);
	const FLinearColor Free(0.9f, 0.95f, 0.85f);
	constexpr int32 Fringe = 4;   // cells shown round the footprint
}

ASRPlacementPreview::ASRPlacementPreview()
{
	PrimaryActorTick.bCanEverTick = false;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));

	Ghost = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Ghost"));
	Ghost->SetupAttachment(GetRootComponent());
	Ghost->SetMobility(EComponentMobility::Movable);
	Ghost->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Ghost->SetCastShadow(false);
	Ghost->bReceivesDecals = false;
	Ghost->bAffectDynamicIndirectLighting = false;
	Ghost->bAffectDistanceFieldLighting = false;
	Ghost->bVisibleInRayTracing = false;

	Cells = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Cells"));
	Cells->SetupAttachment(GetRootComponent());
	Cells->SetMobility(EComponentMobility::Movable);
	Cells->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Cells->SetCastShadow(false);
	Cells->bReceivesDecals = false;
	Cells->bAffectDynamicIndirectLighting = false;
	Cells->bAffectDistanceFieldLighting = false;
	Cells->NumCustomDataFloats = 4;
	Cells->SetUsingAbsoluteLocation(true);
	Cells->SetUsingAbsoluteRotation(true);
	if (UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"))) { Cells->SetStaticMesh(Plane); }
	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SR/Materials/M_GridCell.M_GridCell"))) { Cells->SetMaterial(0, M); }
}

void ASRPlacementPreview::Show(ESRBuildingType Type, const FSRPlacement& P)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!bHasMesh || Type != ShownType)
	{
		ShownType = Type;
		UStaticMesh* Mesh = F.BuildingStatsFor(Type).Mesh.LoadSynchronous();
		Ghost->SetStaticMesh(Mesh);
		if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SR/Materials/M_PlacementGhost.M_PlacementGhost")))
		{
			for (int32 i = 0; i < Ghost->GetNumMaterials(); ++i) { Ghost->SetMaterial(i, M); }
		}
		bHasMesh = true;
		LastCentre = FIntPoint(MIN_int32, MIN_int32);
	}
	SetActorHiddenInGame(false);
	SetActorLocation(P.Location + FVector(0.f, 0.f, 2.f));
	const FLinearColor C = P.bValid ? Good : Bad;
	Ghost->SetCustomPrimitiveDataVector4(0, FVector4(C.R, C.G, C.B, P.bValid ? 0.42f : 0.5f));

	// The cell plates only need rebuilding when the footprint moves to another cell (or its validity flips).
	const USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (!Grid || P.Cells.Num() == 0) { Cells->ClearInstances(); return; }
	const FIntPoint Key = P.Cells[0];
	if (Key == LastCentre && P.bValid == bLastValid) { return; }
	LastCentre = Key;
	bLastValid = P.bValid;

	FIntPoint Lo = P.Cells[0], Hi = P.Cells[0];
	for (const FIntPoint& Cl : P.Cells) { Lo = Lo.ComponentMin(Cl); Hi = Hi.ComponentMax(Cl); }
	Cells->ClearInstances();
	const float Size = Grid->GetCellSize();
	const float Scale = Size / 100.f * 0.97f;   // the engine plane is 100 cm
	TArray<FTransform> Xfs;
	TArray<FLinearColor> Colors;
	for (int32 y = Lo.Y - Fringe; y <= Hi.Y + Fringe; ++y)
	{
		for (int32 x = Lo.X - Fringe; x <= Hi.X + Fringe; ++x)
		{
			const FIntPoint Cl(x, y);
			if (!Grid->InGrid(Cl)) { continue; }
			const int32 K = P.Cells.IndexOfByKey(Cl);
			const bool bFoot = K != INDEX_NONE;
			const bool bBlocked = !Grid->IsWalkable(Cl);
			if (!bFoot && !bBlocked)
			{
				// open ground round the footprint: a faint plate, fading out toward the edge of the fringe
				const int32 Ring = FMath::Max(FMath::Max(Lo.X - x, x - Hi.X), FMath::Max(Lo.Y - y, y - Hi.Y));
				Colors.Add(FLinearColor(Free.R, Free.G, Free.B, 0.22f * (1.f - float(Ring - 1) / Fringe)));
			}
			else if (bFoot)
			{
				const FLinearColor Cc = P.CellOk[K] ? Good : Bad;
				Colors.Add(FLinearColor(Cc.R, Cc.G, Cc.B, P.CellOk[K] ? 0.55f : 0.8f));
			}
			else
			{
				Colors.Add(FLinearColor(Bad.R, Bad.G, Bad.B, Grid->IsBuildingCell(Cl) ? 0.35f : 0.5f));
			}
			const FVector2D Ctr = Grid->CellCentre(Cl);
			Xfs.Add(FTransform(FRotator::ZeroRotator, FVector(Ctr.X, Ctr.Y, Grid->CellHeight(Cl) + 4.f), FVector(Scale, Scale, 1.f)));
		}
	}
	Cells->AddInstances(Xfs, false, false, false);
	for (int32 i = 0; i < Colors.Num(); ++i)
	{
		Cells->SetCustomData(i, { Colors[i].R, Colors[i].G, Colors[i].B, Colors[i].A }, i == Colors.Num() - 1);
	}
}

void ASRPlacementPreview::Hide()
{
	SetActorHiddenInGame(true);
	Cells->ClearInstances();
	LastCentre = FIntPoint(MIN_int32, MIN_int32);
}
