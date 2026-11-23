#include "VLWaterLook.h"

#include "SovereignRealms.h"
#include "VLGrid.h"
#include "VLTroopShip.h"

#include "Async/ParallelFor.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "TextureResource.h"
#include "TimerManager.h"

namespace
{
	constexpr float Margin = 8000.f;        // the shore is measured this far beyond the ground's bounds

	TAutoConsoleVariable<int32> CVarWaterDepth(TEXT("vl.Water.Depth"), 1,
		TEXT("1: the water's material draws depth from the distance to the shore (shallows, deep water, foam). 0: the flat water of before"));

	FAutoConsoleVariableSink WaterSink(FConsoleCommandDelegate::CreateLambda([]()
	{
		if (GEngine)
		{
			for (const FWorldContext& Context : GEngine->GetWorldContexts())
			{
				if (UVLWaterLook* Look = Context.World() ? Context.World()->GetSubsystem<UVLWaterLook>() : nullptr)
				{
					Look->SetOn(CVarWaterDepth.GetValueOnGameThread() != 0);
				}
			}
		}
	}));

	FAutoConsoleCommandWithWorldAndArgs CmdWater(TEXT("vl.Water"), TEXT("vl.Water [rebuild | X Y]: log the water's measured shore (rebuild: measure it again; X Y: the distance to the shore there, cm)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLWaterLook* Look = UVLWaterLook::Get(World);
			if (!Look)
			{
				return;
			}
			if (Args.Num() > 0 && Args[0].ToLower() == TEXT("rebuild"))
			{
				Look->Build();
			}
			if (Args.Num() >= 2)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("water: %.0f cm from the shore at %s %s"), Look->ShoreDistance(FVector2D(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]))), *Args[0], *Args[1]);
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("water: %s"), *Look->Describe());
		}));
}

UVLWaterLook* UVLWaterLook::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLWaterLook>() : nullptr;
}

bool UVLWaterLook::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UVLWaterLook::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	FTimerHandle Handle;
	InWorld.GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateUObject(this, &UVLWaterLook::Build), 0.2f, false);
}

FString UVLWaterLook::Describe() const
{
	return DimX > 0 ? FString::Printf(TEXT("%d sheet(s), shore measured on %d x %d cells of %.2f m (%d of water) in %.0f ms, %d material instance(s), depth %s"), Sheets, DimX, DimY, CellSize / 100.f, WaterCells,
		BuildMs, Instances.Num(), CVarWaterDepth.GetValueOnGameThread() != 0 ? TEXT("on") : TEXT("off")) : FString(TEXT("no water measured in this level"));
}

float UVLWaterLook::ShoreDistance(const FVector2D& P) const
{
	if (DimX <= 0)
	{
		return -1.f;
	}
	const int32 X = FMath::Clamp(FMath::FloorToInt((P.X - Origin.X) / CellSize), 0, DimX - 1), Y = FMath::Clamp(FMath::FloorToInt((P.Y - Origin.Y) / CellSize), 0, DimY - 1);
	return Shore[Y * DimX + X] / 255.f * ShoreRange;
}

void UVLWaterLook::SetOn(bool bOn)
{
	for (UMaterialInstanceDynamic* MID : Instances)
	{
		if (MID)
		{
			MID->SetScalarParameterValue(TEXT("ShoreOn"), bOn && ShoreTex ? 1.f : 0.f);
			MID->SetScalarParameterValue(TEXT("DepthOn"), bOn ? 1.f : 0.f);
		}
	}
}

void UVLWaterLook::Build()
{
	UWorld* World = GetWorld();
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!World)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	TArray<UStaticMeshComponent*> Comps;
	FBox Wet(ForceInit);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(VLWaterLook), true);
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		const AStaticMeshActor* SMA = Cast<AStaticMeshActor>(*It);
		if (SMA && SMA->ActorHasTag(TEXT("Water")) && SMA->GetStaticMeshComponent())
		{
			Comps.Add(SMA->GetStaticMeshComponent());
			Wet += SMA->GetStaticMeshComponent()->Bounds.GetBox();
		}
		if (It->IsA<APawn>() || It->IsA<AVLTroopShip>() || UVLGrid::IsUnseen(*It) || It->ActorHasTag(TEXT("Moored")))
		{
			Params.AddIgnoredActor(*It);
		}
	}
	Sheets = Comps.Num();
	if (Sheets == 0 || !Grid || !Grid->EnsureBuilt())
	{
		return;
	}
	// the ground's bounds and a margin, no further than the water goes
	const FBox2D Ground = Grid->GetBounds().ExpandBy(Margin);
	const FBox2D Area(FVector2D(FMath::Max(Ground.Min.X, Wet.Min.X), FMath::Max(Ground.Min.Y, Wet.Min.Y)), FVector2D(FMath::Min(Ground.Max.X, Wet.Max.X), FMath::Min(Ground.Max.Y, Wet.Max.Y)));
	if (Area.GetSize().X < CellSize * 4.f || Area.GetSize().Y < CellSize * 4.f)
	{
		return;
	}
	Origin = Area.Min;
	DimX = FMath::Min(FMath::CeilToInt(Area.GetSize().X / CellSize), 2048);
	DimY = FMath::Min(FMath::CeilToInt(Area.GetSize().Y / CellSize), 2048);
	const FBox2D Inside = Grid->GetBounds();
	TArray<uint8> IsWater;
	IsWater.Init(0, DimX * DimY);
	const FCollisionQueryParams SheetParams(SCENE_QUERY_STAT(VLWaterSheet), true);
	ParallelFor(DimY, [&](int32 y)
	{
		for (int32 x = 0; x < DimX; ++x)
		{
			const FVector2D P = Origin + FVector2D(x + 0.5f, y + 0.5f) * CellSize;
			// the water's surface there: the path grid knows it over the ground; beyond, the sheets are asked
			float Z = -BIG_NUMBER;
			if (Inside.IsInside(P))
			{
				Z = Grid->WaterLevelAt(FVector(P.X, P.Y, 0.f));
			}
			else
			{
				FHitResult Hit;
				for (UStaticMeshComponent* Sheet : Comps)
				{
					const FBox Box = Sheet->Bounds.GetBox();
					if (Box.IsInsideXY(FVector(P.X, P.Y, 0.f)) && Sheet->LineTraceComponent(Hit, FVector(P.X, P.Y, Box.Max.Z + 50.f), FVector(P.X, P.Y, Box.Min.Z - 50.f), SheetParams))
					{
						Z = FMath::Max(Z, float(Hit.ImpactPoint.Z));
					}
				}
			}
			// water where nothing stands in it or over it (from above: a start inside a cliff would meet nothing)
			IsWater[y * DimX + x] = Z > -BIG_NUMBER * 0.5f && !World->LineTraceTestByChannel(FVector(P.X, P.Y, Z + 3000.f), FVector(P.X, P.Y, Z - 30.f), ECC_Visibility, Params) ? 1 : 0;
		}
	});
	// each water cell's distance to the nearest cell that is not water: two sweeps (3-4 chamfer), in cells
	TArray<float> D;
	D.Init(0.f, DimX * DimY);
	const float Far = ShoreRange / CellSize + 2.f;
	WaterCells = 0;
	for (int32 i = 0; i < D.Num(); ++i)
	{
		D[i] = IsWater[i] ? Far : 0.f;
		WaterCells += IsWater[i];
	}
	auto Relax = [&](int32 x, int32 y, int32 dx, int32 dy, float Cost)
	{
		const int32 nx = x + dx, ny = y + dy;
		if (nx >= 0 && ny >= 0 && nx < DimX && ny < DimY)
		{
			D[y * DimX + x] = FMath::Min(D[y * DimX + x], D[ny * DimX + nx] + Cost);
		}
	};
	for (int32 y = 0; y < DimY; ++y)
	{
		for (int32 x = 0; x < DimX; ++x)
		{
			Relax(x, y, -1, 0, 1.f); Relax(x, y, 0, -1, 1.f); Relax(x, y, -1, -1, 1.4142f); Relax(x, y, 1, -1, 1.4142f);
		}
	}
	for (int32 y = DimY - 1; y >= 0; --y)
	{
		for (int32 x = DimX - 1; x >= 0; --x)
		{
			Relax(x, y, 1, 0, 1.f); Relax(x, y, 0, 1, 1.f); Relax(x, y, 1, 1, 1.4142f); Relax(x, y, -1, 1, 1.4142f);
		}
	}
	Shore.SetNumUninitialized(DimX * DimY);
	for (int32 i = 0; i < D.Num(); ++i)
	{
		// (a water cell's own middle is half a cell from the shore's line)
		Shore[i] = uint8(FMath::Clamp(FMath::RoundToInt(FMath::Max(D[i] - 0.5f, 0.f) * CellSize / ShoreRange * 255.f), 0, 255));
	}
	// the texture: the distance in its alpha (which is never taken for sRGB), white otherwise
	ShoreTex = UTexture2D::CreateTransient(DimX, DimY, PF_B8G8R8A8, TEXT("VLShoreDistance"));
	if (!ShoreTex || !ShoreTex->GetPlatformData() || ShoreTex->GetPlatformData()->Mips.Num() == 0)
	{
		ShoreTex = nullptr;
		return;
	}
	ShoreTex->SRGB = false;
	ShoreTex->Filter = TF_Bilinear;
	ShoreTex->AddressX = TA_Clamp;
	ShoreTex->AddressY = TA_Clamp;
	ShoreTex->NeverStream = true;
	{
		FTexture2DMipMap& Mip = ShoreTex->GetPlatformData()->Mips[0];
		uint8* Data = static_cast<uint8*>(Mip.BulkData.Lock(LOCK_READ_WRITE));
		for (int32 i = 0; i < Shore.Num(); ++i)
		{
			Data[i * 4 + 0] = 255;
			Data[i * 4 + 1] = 255;
			Data[i * 4 + 2] = 255;
			Data[i * 4 + 3] = Shore[i];
		}
		Mip.BulkData.Unlock();
	}
	ShoreTex->UpdateResource();
	// every water sheet's materials: one instance for each material they use
	Instances.Reset();
	TMap<UMaterialInterface*, UMaterialInstanceDynamic*> ByParent;
	const FLinearColor Rect(Origin.X, Origin.Y, 1.f / (DimX * CellSize), 1.f / (DimY * CellSize));
	for (UStaticMeshComponent* Comp : Comps)
	{
		for (int32 i = 0; i < Comp->GetNumMaterials(); ++i)
		{
			UMaterialInterface* Mat = Comp->GetMaterial(i);
			if (UMaterialInstanceDynamic* Old = Cast<UMaterialInstanceDynamic>(Mat))
			{
				Mat = Old->Parent;      // (built again: from the sheet's own material)
			}
			if (!Mat)
			{
				continue;
			}
			UMaterialInstanceDynamic*& MID = ByParent.FindOrAdd(Mat);
			if (!MID)
			{
				MID = UMaterialInstanceDynamic::Create(Mat, this);
				MID->SetTextureParameterValue(TEXT("ShoreTex"), ShoreTex);
				MID->SetVectorParameterValue(TEXT("ShoreRect"), Rect);
				MID->SetScalarParameterValue(TEXT("ShoreRange"), ShoreRange);
				Instances.Add(MID);
			}
			Comp->SetMaterial(i, MID);
		}
	}
	SetOn(CVarWaterDepth.GetValueOnGameThread() != 0);
	BuildMs = (FPlatformTime::Seconds() - T0) * 1000.0;
	UE_LOG(LogSovereignRealms, Log, TEXT("water: %s"), *Describe());
}
