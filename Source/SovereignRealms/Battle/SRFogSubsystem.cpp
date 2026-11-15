// Copyright Sovereign Realms.

#include "Battle/SRFogSubsystem.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Units/SRUnit.h"
#include "Player/SRCameraPawn.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Camera/CameraComponent.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "RenderingThread.h"

USRFogSubsystem* USRFogSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USRFogSubsystem>() : nullptr;
}

bool USRFogSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void USRFogSubsystem::Deinitialize()
{
	FlushRenderingCommands();
	Super::Deinitialize();
}

bool USRFogSubsystem::IsEnabled() const
{
	return USRFeelSettings::Get().bFogOfWar && !bForceOff;
}

void USRFogSubsystem::Reset()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	CellSize = FMath::Max(F.FogCellSize, 25.f);
	const float Extent = FMath::Max(F.MapHalfExtent.X, F.MapHalfExtent.Y) + 1500.f;
	N = FMath::Clamp(FMath::CeilToInt(2.f * Extent / CellSize), 16, 512);
	Origin = FVector2D(-Extent, -Extent);
	Explored.Init(0, N * N);
	Visible.Init(0, N * N);
	Shown.Init(0.f, N * N);
	Pixels.Init(0, N * N * 4);
	KnownBuildings.Reset();
	Clock = 0.f;
	bDirty = true;
	if (FogTexture && (FogTexture->GetSizeX() != N)) { FogTexture = nullptr; FogMaterial = nullptr; bHadView = false; }
	Recompute();
	for (int32 i = 0; i < N * N; ++i) { Shown[i] = Visible[i] ? 1.f : 0.f; }   // no fade-in at the start
	PushTexture(0.f);
}

int32 USRFogSubsystem::CellOf(const FVector2D& P) const
{
	if (N == 0) { return INDEX_NONE; }
	const int32 X = FMath::FloorToInt((P.X - Origin.X) / CellSize), Y = FMath::FloorToInt((P.Y - Origin.Y) / CellSize);
	return (X < 0 || Y < 0 || X >= N || Y >= N) ? INDEX_NONE : Y * N + X;
}

bool USRFogSubsystem::IsVisible(const FVector2D& P) const
{
	if (!IsEnabled()) { return true; }
	const int32 C = CellOf(P);
	return C != INDEX_NONE && Visible[C] != 0;
}

bool USRFogSubsystem::IsExplored(const FVector2D& P) const
{
	if (!IsEnabled()) { return true; }
	const int32 C = CellOf(P);
	return C != INDEX_NONE && Explored[C] != 0;
}

bool USRFogSubsystem::IsUnitVisible(const ASRUnit* Unit) const
{
	if (!Unit || Unit->GetTeam() == ESRTeam::Player || !IsEnabled()) { return true; }
	if (!IsVisible(Unit->GetPos2D())) { return false; }
	// Reduced visibility (an enemy Scout): the ground it stands on is in sight, but it only shows once one of the
	// player's troops or buildings is within the same fraction of its own sight that the enemy's would need.
	const float Scale = Unit->GetNoticeScale();
	if (Scale >= 1.f) { return true; }
	const FVector2D P = Unit->GetPos2D();
	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		for (const ASRUnit* U : Battle->GetUnits())
		{
			if (U && U->IsActive() && U->GetTeam() == ESRTeam::Player && FVector2D::DistSquared(U->GetPos2D(), P) <= FMath::Square(U->Stats().Sight() * Scale)) { return true; }
		}
	}
	if (const USREconomySubsystem* Eco = USREconomySubsystem::Get(this))
	{
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (B && B->IsAlive() && B->Team == ESRTeam::Player && FVector2D::DistSquared(B->GetFootprintCentre(), P) <= FMath::Square(BuildingSight(B) * Scale)) { return true; }
		}
	}
	return false;
}

float USRFogSubsystem::BuildingSight(const ASRBuilding* B)
{
	return FMath::Max3(1400.f, B->GetAttackRange() + 300.f, B->Stats().TerritoryRadius * 0.5f);
}

bool USRFogSubsystem::IsBuildingKnown(const ASRBuilding* Building) const
{
	if (!Building || Building->Team == ESRTeam::Player || !IsEnabled()) { return true; }
	return KnownBuildings.Contains(Building);
}

void USRFogSubsystem::SetExplored(const TArray<uint8>& In)
{
	if (In.Num() == Explored.Num()) { Explored = In; bDirty = true; }
}

void USRFogSubsystem::Stamp(const FVector2D& Centre, float Radius)
{
	const int32 R = FMath::CeilToInt(Radius / CellSize);
	const int32 CX = FMath::FloorToInt((Centre.X - Origin.X) / CellSize), CY = FMath::FloorToInt((Centre.Y - Origin.Y) / CellSize);
	const float R2 = FMath::Square(Radius / CellSize);
	for (int32 y = FMath::Max(0, CY - R); y <= FMath::Min(N - 1, CY + R); ++y)
	{
		for (int32 x = FMath::Max(0, CX - R); x <= FMath::Min(N - 1, CX + R); ++x)
		{
			if (FMath::Square(float(x - CX)) + FMath::Square(float(y - CY)) <= R2)
			{
				const int32 i = y * N + x;
				Visible[i] = 1;
				Explored[i] = 1;
			}
		}
	}
}

void USRFogSubsystem::Recompute()
{
	if (N == 0) { return; }
	FMemory::Memzero(Visible.GetData(), Visible.Num());
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (Battle)
	{
		for (const ASRUnit* U : Battle->GetUnits())
		{
			if (U && U->IsActive() && U->GetTeam() == ESRTeam::Player) { Stamp(U->GetPos2D(), U->Stats().Sight()); }
		}
	}
	if (Eco)
	{
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (!B || !B->IsAlive() || B->Team != ESRTeam::Player) { continue; }
			Stamp(B->GetFootprintCentre(), BuildingSight(B));
		}
		// An enemy building is known once any part of it has been in sight.
		for (ASRBuilding* B : Eco->GetBuildings())
		{
			if (!B || B->Team == ESRTeam::Player || KnownBuildings.Contains(B)) { continue; }
			const FVector2D C = B->GetFootprintCentre();
			const FVector2D H = (B->FootprintMax - B->FootprintMin) * 0.5f;
			const FVector2D Probes[5] = { C, C + H, C - H, C + FVector2D(H.X, -H.Y), C + FVector2D(-H.X, H.Y) };
			for (const FVector2D& P : Probes)
			{
				const int32 Cell = CellOf(P);
				if (Cell != INDEX_NONE && Visible[Cell]) { KnownBuildings.Add(B); break; }
			}
		}
		// Hide the unknown ones in the world.
		for (ASRBuilding* B : Eco->GetBuildings())
		{
			if (!B || B->Team == ESRTeam::Player) { continue; }
			const bool bHide = IsEnabled() && !KnownBuildings.Contains(B);
			if (B->IsHidden() != bHide) { B->SetActorHiddenInGame(bHide); }
		}
	}
}

void USRFogSubsystem::EnsureView()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!FogTexture)
	{
		FogTexture = UTexture2D::CreateTransient(N, N, PF_B8G8R8A8);
		FogTexture->SRGB = true;      // matches the material's Color sampler; the shader undoes the curve
		FogTexture->Filter = TF_Bilinear;
		FogTexture->AddressX = TA_Clamp;
		FogTexture->AddressY = TA_Clamp;
		FogTexture->UpdateResource();
	}
	if (!FogMaterial)
	{
		if (UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SR/Materials/M_FogOfWar.M_FogOfWar")))
		{
			FogMaterial = UMaterialInstanceDynamic::Create(Base, this);
			FogMaterial->SetTextureParameterValue(TEXT("FogTex"), FogTexture);
			FogMaterial->SetVectorParameterValue(TEXT("MapRect"), FLinearColor(Origin.X, Origin.Y, N * CellSize, N * CellSize));
		}
		else
		{
			UE_LOG(LogSovereign, Warning, TEXT("Missing /Game/SR/Materials/M_FogOfWar: run Tools/build_fog_material.py in the editor"));
		}
	}
	if (FogMaterial)
	{
		FogMaterial->SetScalarParameterValue(TEXT("Strength"), IsEnabled() ? F.FogStrength : 0.f);
	}
	if (!bHadView && FogMaterial)
	{
		const APlayerController* PC = GetWorld()->GetFirstPlayerController();
		if (const ASRCameraPawn* Pawn = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
		{
			if (UCameraComponent* Cam = Pawn->FindComponentByClass<UCameraComponent>())
			{
				Cam->PostProcessSettings.WeightedBlendables.Array.Add(FWeightedBlendable(1.f, FogMaterial));
				// and the troops' silhouettes behind buildings (custom depth, team in the stencil)
				if (UMaterialInterface* Occ = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SR/Materials/M_Occlusion.M_Occlusion")))
				{
					Cam->PostProcessSettings.WeightedBlendables.Array.Add(FWeightedBlendable(1.f, Occ));
				}
				bHadView = true;
			}
		}
	}
}

void USRFogSubsystem::PushTexture(float DeltaTime)
{
	if (N == 0) { return; }
	EnsureView();
	if (!FogTexture || !FogTexture->GetResource()) { return; }
	const float Fade = USRFeelSettings::Get().FogFadeTime;
	const float Step = Fade > 0.f && DeltaTime > 0.f ? FMath::Clamp(DeltaTime / Fade, 0.f, 1.f) : 1.f;
	bool bChanged = bDirty;
	for (int32 i = 0; i < N * N; ++i)
	{
		const float Target = Visible[i] ? 1.f : (Explored[i] ? 0.5f : 0.f);
		const float Old = Shown[i];
		const float New = FMath::Abs(Target - Old) <= Step ? Target : Old + FMath::Sign(Target - Old) * Step;
		if (New != Old) { Shown[i] = New; bChanged = true; }
		const uint8 V = uint8(FMath::RoundToInt(New * 255.f));
		Pixels[i * 4 + 0] = V; Pixels[i * 4 + 1] = V; Pixels[i * 4 + 2] = V; Pixels[i * 4 + 3] = 255;
	}
	if (!bChanged) { return; }
	bDirty = false;
	uint8* Copy = static_cast<uint8*>(FMemory::Malloc(Pixels.Num()));
	FMemory::Memcpy(Copy, Pixels.GetData(), Pixels.Num());
	FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(0, 0, 0, 0, N, N);
	FogTexture->UpdateTextureRegions(0, 1, Region, N * 4, 4, Copy, [](uint8* Data, const FUpdateTextureRegion2D* R)
	{
		FMemory::Free(Data);
		delete R;
	});
}

void USRFogSubsystem::Update(float DeltaTime)
{
	if (N == 0) { Reset(); }
	Clock += DeltaTime;
	if (Clock >= USRFeelSettings::Get().FogUpdateInterval)
	{
		Recompute();
		PushTexture(Clock);
		Clock = 0.f;
	}
}
