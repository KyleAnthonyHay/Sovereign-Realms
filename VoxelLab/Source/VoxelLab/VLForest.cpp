#include "VLForest.h"
#include "VoxelLab.h"
#include "VLFootDust.h"
#include "VLGrid.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInterface.h"

AVLForest::AVLForest()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Static);
	SetRootComponent(Root);
}

UHierarchicalInstancedStaticMeshComponent* AVLForest::AddKind(UStaticMesh* Mesh, const TArray<FTransform>& Instances, EVLForestPart Part, float Reach,
	bool bCollide, bool bCastShadow, float CullDistance)
{
	if (!Mesh || Instances.Num() == 0)
	{
		return nullptr;
	}
	const FName Name = MakeUniqueObjectName(this, UHierarchicalInstancedStaticMeshComponent::StaticClass(), *Mesh->GetName());
	UHierarchicalInstancedStaticMeshComponent* Comp = NewObject<UHierarchicalInstancedStaticMeshComponent>(this, Name, RF_Transactional);
	Comp->SetMobility(EComponentMobility::Static);
	Comp->SetStaticMesh(Mesh);
	Comp->SetupAttachment(GetRootComponent());
	if (bCollide)
	{
		Comp->SetCollisionProfileName(TEXT("BlockAll"));
	}
	else
	{
		Comp->SetCollisionProfileName(TEXT("NoCollision"));
	}
	Comp->SetCanEverAffectNavigation(false);
	Comp->SetCastShadow(bCastShadow);
	if (Part != EVLForestPart::Trunk)
	{
		// crowns shade the ground from the sun but do not shut out the sky (as the level builder's single trees);
		// the undergrowth is too small to matter to either
		Comp->bAffectDistanceFieldLighting = false;
		Comp->bAffectDynamicIndirectLighting = false;
	}
	if (CullDistance > 0.f)
	{
		Comp->SetCullDistances(FMath::RoundToInt32(CullDistance * 0.85f), FMath::RoundToInt32(CullDistance));
	}
	AddInstanceComponent(Comp);
	Comp->RegisterComponent();
	Comp->AddInstances(Instances, false, true);
	FVLForestKind& Kind = Kinds.AddDefaulted_GetRef();
	Kind.Component = Comp;
	Kind.Part = Part;
	Kind.Reach = Reach;
	return Comp;
}

void AVLForest::BeginPlay()
{
	Super::BeginPlay();
	Dust = NewObject<UVLFootDust>(this, TEXT("ClearingDust"));
	Dust->PoolSize = 240;
	Dust->Size = 26.f;
	Dust->Growth = 2.1f;
	Dust->Lifetime = 0.85f;
	Dust->Drift = 260.f;
	Dust->Rise = 150.f;
	Dust->Color = FLinearColor(0.80f, 0.86f, 0.62f);       // leaves and dust
	Dust->Glow = 0.25f;
	Dust->DustMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Voxel/Materials/MI_Vox_smoke.MI_Vox_smoke"));
	Dust->RegisterComponent();
}

void AVLForest::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (Dust)
	{
		Dust->Advance(DeltaSeconds);
	}
	if (!GetWorld() || GetWorld()->GetTimeSeconds() > DustUntil)
	{
		SetActorTickEnabled(false);
	}
}

void AVLForest::Poof(const TArray<FVector4>& At)
{
	if (!Dust || At.Num() == 0 || !GetWorld())
	{
		return;
	}
	// the pool is shared out: a few cubes a tree when a whole wood goes at once
	const int32 Each = FMath::Clamp(Dust->PoolSize / At.Num(), 2, 14);
	for (const FVector4& P : At)
	{
		const float Tall = P.W;
		for (int32 i = 0; i < Each; ++i)
		{
			const float A = (i * 2.399963f) + P.X * 0.01f;             // the golden angle: all round
			const FVector Out(FMath::Cos(A), FMath::Sin(A), 0.f);
			Dust->Emit(FVector(P.X, P.Y, P.Z + Tall * (0.1f + 0.8f * i / float(Each))), Out, 1, 1.f + Tall / 900.f);
		}
	}
	DustUntil = GetWorld()->GetTimeSeconds() + Dust->Lifetime * 1.4f;
	SetActorTickEnabled(true);
}

void AVLForest::ClearIn(const FVector2D& Centre, const FVector2D& HalfExtent, float YawDegrees, float Margin, bool bDryRun,
	int32& Trees, int32& Crowns, int32& Plants, FBox2D& Changed, TArray<FVector4>* Poofs)
{
	const float Yaw = FMath::DegreesToRadians(YawDegrees);
	const float C = FMath::Cos(Yaw), S = FMath::Sin(Yaw);
	TArray<int32> Gone;
	for (FVLForestKind& Kind : Kinds)
	{
		UHierarchicalInstancedStaticMeshComponent* Comp = Kind.Component;
		if (!Comp || !Comp->GetStaticMesh())
		{
			continue;
		}
		const bool bTree = Kind.Part != EVLForestPart::Undergrowth;
		const FBoxSphereBounds MeshBounds = Comp->GetStaticMesh()->GetBounds();
		Gone.Reset();
		for (int32 i = 0, n = Comp->GetInstanceCount(); i < n; ++i)
		{
			FTransform T;
			if (!Comp->GetInstanceTransform(i, T, true))
			{
				continue;
			}
			const FVector P = T.GetLocation();
			const FVector2D D(P.X - Centre.X, P.Y - Centre.Y);
			// in the footprint's own frame; how far outside its rectangle
			const FVector2D L(D.X * C + D.Y * S, -D.X * S + D.Y * C);
			const float Out = FVector2D(FMath::Max(FMath::Abs(L.X) - HalfExtent.X, 0.f), FMath::Max(FMath::Abs(L.Y) - HalfExtent.Y, 0.f)).Size();
			const float Scale = T.GetScale3D().X;
			if (Out > (bTree ? Margin + Kind.Reach * Scale : 0.f))
			{
				continue;
			}
			Gone.Add(i);
			if (Kind.Part == EVLForestPart::Trunk)
			{
				++Trees;
				// the ground its trunk and roots stood on: where the path grid has to look again
				const float R = FMath::Max(MeshBounds.BoxExtent.X, MeshBounds.BoxExtent.Y) * Scale + 80.f;
				Changed += FBox2D(FVector2D(P.X - R, P.Y - R), FVector2D(P.X + R, P.Y + R));
				if (Poofs)
				{
					Poofs->Add(FVector4(P.X, P.Y, P.Z, MeshBounds.BoxExtent.Z * 2.f * Scale));
				}
			}
			else if (Kind.Part == EVLForestPart::Crown)
			{
				++Crowns;
			}
			else
			{
				++Plants;
			}
		}
		if (!bDryRun && Gone.Num() > 0)
		{
			Comp->RemoveInstances(Gone);
			bTrunkCache = false;
		}
	}
}

const TArray<AVLForest::FTrunkKind>& AVLForest::Trunks()
{
	// still what the components hold? (instances only ever go through ClearIn, which says so; the count is a second check)
	if (bTrunkCache)
	{
		int32 k = 0;
		for (const FVLForestKind& Kind : Kinds)
		{
			if (Kind.Part == EVLForestPart::Trunk && Kind.Component && Kind.Component->GetStaticMesh())
			{
				bTrunkCache &= TrunkCache.IsValidIndex(k) && TrunkCache[k].Instances == Kind.Component->GetInstanceCount();
				++k;
			}
		}
		bTrunkCache &= k == TrunkCache.Num();
	}
	if (!bTrunkCache)
	{
		TrunkCache.Reset();
		for (const FVLForestKind& Kind : Kinds)
		{
			const UHierarchicalInstancedStaticMeshComponent* Comp = Kind.Component;
			if (Kind.Part != EVLForestPart::Trunk || !Comp || !Comp->GetStaticMesh())
			{
				continue;
			}
			FTrunkKind& Out = TrunkCache.AddDefaulted_GetRef();
			Out.Reach = Kind.Reach;
			Out.Instances = Comp->GetInstanceCount();
			Out.At.Reserve(Out.Instances);
			for (int32 i = 0; i < Out.Instances; ++i)
			{
				FTransform T;
				if (Comp->GetInstanceTransform(i, T, true))
				{
					const FVector P = T.GetLocation();
					Out.At.Add({ P.X, P.Y, float(T.GetScale3D().X) });
				}
			}
		}
		bTrunkCache = true;
	}
	return TrunkCache;
}

int32 AVLForest::CountTrees(const UObject* WorldContext, FVector2D Centre, FVector2D InHalfExtent, float YawDegrees, float InMargin)
{
	UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (!World)
	{
		return 0;
	}
	// ClearIn's test, on the trunks (ClearTrees counts those)
	const FVector2D HalfExtent = InHalfExtent.GetAbs();
	const float Margin = FMath::Max(InMargin, 0.f);
	const float Yaw = FMath::DegreesToRadians(YawDegrees);
	const float C = FMath::Cos(Yaw), S = FMath::Sin(Yaw);
	int32 Trees = 0;
	for (TActorIterator<AVLForest> It(World); It; ++It)
	{
		for (const FTrunkKind& Kind : It->Trunks())
		{
			for (const FTrunk& T : Kind.At)
			{
				const FVector2D D(T.X - Centre.X, T.Y - Centre.Y);
				const FVector2D L(D.X * C + D.Y * S, -D.X * S + D.Y * C);
				const float Out = FVector2D(FMath::Max(FMath::Abs(L.X) - HalfExtent.X, 0.f), FMath::Max(FMath::Abs(L.Y) - HalfExtent.Y, 0.f)).Size();
				Trees += Out > Margin + Kind.Reach * T.Scale ? 0 : 1;
			}
		}
	}
	return Trees;
}

int32 AVLForest::ClearTrees(const UObject* WorldContext, FVector2D Centre, FVector2D HalfExtent, float YawDegrees, float Margin, bool bPoof, bool bDryRun)
{
	return ClearTreesImpl(WorldContext, Centre, HalfExtent, YawDegrees, Margin, bPoof, bDryRun, nullptr);
}

int32 AVLForest::ClearTreesDeferred(const UObject* WorldContext, FVector2D Centre, FVector2D HalfExtent, float YawDegrees, float Margin, bool bPoof, FBox2D& OutChanged)
{
	OutChanged = FBox2D(ForceInit);
	return ClearTreesImpl(WorldContext, Centre, HalfExtent, YawDegrees, Margin, bPoof, false, &OutChanged);
}

int32 AVLForest::ClearTreesImpl(const UObject* WorldContext, FVector2D Centre, FVector2D HalfExtent, float YawDegrees, float Margin, bool bPoof, bool bDryRun, FBox2D* OutChanged)
{
	UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (!World)
	{
		return 0;
	}
	const double T0 = FPlatformTime::Seconds();
	int32 Trees = 0, Crowns = 0, Plants = 0, Resampled = 0, Walkable = 0;
	FBox2D Changed(ForceInit);
	TArray<FVector4> Stood;
	for (TActorIterator<AVLForest> It(World); It; ++It)
	{
		TArray<FVector4> Poofs;
		It->ClearIn(Centre, HalfExtent.GetAbs(), YawDegrees, FMath::Max(Margin, 0.f), bDryRun, Trees, Crowns, Plants, Changed, &Poofs);
		if (bPoof && !bDryRun)
		{
			It->Poof(Poofs);
		}
		Stood.Append(Poofs);
	}
	if (OutChanged)
	{
		*OutChanged = Changed;          // (the caller samples the grid again, with what else changed there)
	}
	else if (!bDryRun && Changed.bIsValid)
	{
		if (UVLGrid* Grid = UVLGrid::Get(World); Grid && Grid->IsBuilt())
		{
			Resampled = Grid->RebuildArea(Changed);
			for (const FVector4& P : Stood)
			{
				Walkable += Grid->NodeAt(FVector(P.X, P.Y, P.Z), 150.f) != INDEX_NONE ? 1 : 0;
			}
		}
	}
	if (OutChanged)
	{
		UE_LOG(LogVoxelLab, Log, TEXT("TREES cleared: %d tree(s) (%d crown(s)), %d plant(s) at %.0f %.0f, half %.0f x %.0f, yaw %.0f, margin %.0f; grid: sampled again with the building's ground; %.1f ms"),
			Trees, Crowns, Plants, Centre.X, Centre.Y, HalfExtent.X, HalfExtent.Y, YawDegrees, Margin, (FPlatformTime::Seconds() - T0) * 1000.0);
		return Trees;
	}
	UE_LOG(LogVoxelLab, Log, TEXT("TREES %s: %d tree(s) (%d crown(s)), %d plant(s) at %.0f %.0f, half %.0f x %.0f, yaw %.0f, margin %.0f; grid: %d cell(s) sampled again, walkable where %d trunk(s) stood; %.1f ms"),
		bDryRun ? TEXT("counted") : TEXT("cleared"), Trees, Crowns, Plants, Centre.X, Centre.Y, HalfExtent.X, HalfExtent.Y, YawDegrees, Margin, Resampled, Walkable,
		(FPlatformTime::Seconds() - T0) * 1000.0);
	return Trees;
}

int32 AVLForest::ClearTreesIn(const UObject* WorldContext, const FBox2D& Footprint, float Margin, bool bPoof, bool bDryRun)
{
	return ClearTrees(WorldContext, Footprint.GetCenter(), Footprint.GetExtent(), 0.f, Margin, bPoof, bDryRun);
}

bool AVLForest::FootprintOf(const AActor* Building, FVector2D& OutCentre, FVector2D& OutHalf, float& OutYaw)
{
	const UStaticMeshComponent* Comp = Building ? Building->FindComponentByClass<UStaticMeshComponent>() : nullptr;
	if (!Comp || !Comp->GetStaticMesh())
	{
		return false;
	}
	// the mesh's own box, where and as the building stands (not the world box of a turned building, which is bigger)
	const FBox Local = Comp->GetStaticMesh()->GetBoundingBox();
	const FTransform& T = Comp->GetComponentTransform();
	const FVector Centre = T.TransformPosition(Local.GetCenter());
	const FVector Half = Local.GetExtent() * T.GetScale3D().GetAbs();
	OutCentre = FVector2D(Centre.X, Centre.Y);
	OutHalf = FVector2D(Half.X, Half.Y);
	OutYaw = T.Rotator().Yaw;
	return true;
}

int32 AVLForest::ClearTreesAround(const AActor* Building, float Margin, bool bPoof, bool bDryRun)
{
	FVector2D Centre, Half;
	float Yaw = 0.f;
	return FootprintOf(Building, Centre, Half, Yaw) ? ClearTrees(Building, Centre, Half, Yaw, Margin, bPoof, bDryRun) : 0;
}

int32 AVLForest::ClearTreesAroundDeferred(const AActor* Building, float Margin, bool bPoof, FBox2D& OutChanged)
{
	OutChanged = FBox2D(ForceInit);
	FVector2D Centre, Half;
	float Yaw = 0.f;
	return FootprintOf(Building, Centre, Half, Yaw) ? ClearTreesDeferred(Building, Centre, Half, Yaw, Margin, bPoof, OutChanged) : 0;
}

int32 AVLForest::CountInstances(const UObject* WorldContext, EVLForestPart Part)
{
	int32 N = 0;
	if (UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr)
	{
		for (TActorIterator<AVLForest> It(World); It; ++It)
		{
			for (const FVLForestKind& Kind : It->Kinds)
			{
				N += Kind.Part == Part && Kind.Component ? Kind.Component->GetInstanceCount() : 0;
			}
		}
	}
	return N;
}

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdClearTrees(TEXT("vl.ClearTrees"),
		TEXT("vl.ClearTrees X Y [Radius] [count] | <building name> [Margin] [count] | buildings [Margin] [count]: clear the trees round a point (a square of that half side, default 600), "
			"round every building of that name, or round every building; 'count' only counts them. vl.ClearTrees alone: how many trees there are"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& InArgs, UWorld* World)
		{
			if (!World)
			{
				return;
			}
			TArray<FString> Args(InArgs);
			const bool bDry = Args.Num() > 0 && Args.Last().Equals(TEXT("count"), ESearchCase::IgnoreCase);
			if (bDry)
			{
				Args.Pop();
			}
			if (Args.Num() == 0)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("TREES: %d tree(s), %d plant(s) in the level's forest"),
					AVLForest::CountInstances(World, EVLForestPart::Trunk), AVLForest::CountInstances(World, EVLForestPart::Undergrowth));
				return;
			}
			if (Args.Num() >= 2 && Args[0].IsNumeric() && Args[1].IsNumeric())
			{
				const float R = Args.IsValidIndex(2) ? FCString::Atof(*Args[2]) : 600.f;
				AVLForest::ClearTrees(World, FVector2D(FCString::Atof(*Args[0]), FCString::Atof(*Args[1])), FVector2D(R, R), 0.f, 0.f, true, bDry);
				return;
			}
			float Margin = 150.f;
			if (Args.Num() > 1 && Args.Last().IsNumeric())
			{
				Margin = FCString::Atof(*Args.Last());
				Args.Pop();
			}
			const FString Name = FString::Join(Args, TEXT(" "));
			const bool bAll = Name.Equals(TEXT("buildings"), ESearchCase::IgnoreCase);
			const FName Tag(*(TEXT("Name:") + Name));
			int32 Buildings = 0, Trees = 0;
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				if (bAll ? It->ActorHasTag(TEXT("Selectable")) : It->ActorHasTag(Tag))
				{
					++Buildings;
					Trees += AVLForest::ClearTreesAround(*It, Margin, true, bDry);
				}
			}
			UE_LOG(LogVoxelLab, Log, TEXT("TREES %s round %d building(s) '%s' (margin %.0f): %d tree(s)"), bDry ? TEXT("counted") : TEXT("cleared"), Buildings, *Name, Margin, Trees);
		}));
}
