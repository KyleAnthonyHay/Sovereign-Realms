// Copyright Sovereign Realms.

#include "Buildings/SRWorker.h"
#include "Buildings/SRBuilding.h"
#include "Battle/SRBattleSubsystem.h"
#include "Common/SRAudioSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Units/SRSprite.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"

namespace
{
	// Sheet blocks (same layout as the troops; SRSprite.cpp): idle (8, 0), walk (16, 0), attack = work (0, 8).
	constexpr int32 IdleCol = 8, WalkCol = 16, WorkCol = 0, WorkRow = 8;
	constexpr float WalkSpeed = 150.f;
	constexpr float WorkFps = 7.f;
	constexpr int32 WorkStrikeFrame = 4;

	// Places in the building's local space (front = -X), from the Blender models (Tools/blender/bld_mine.py, bld_farm.py).
	const FVector2D MineAdit(-30.f, 0.f);         // the dark mouth: miners vanish here
	const FVector2D MineOutside(-140.f, 0.f);     // a few steps out of it
	const FVector2D MineCart(-214.f, 92.f);       // beside the ore cart
	const FVector2D FarmDrop(70.f, -175.f);       // the cottage door
	const float FieldX0 = -360.f, FieldX1 = 220.f, FieldY0 = -70.f, FieldY1 = 420.f;

	UStaticMeshComponent* MakeCard(AActor* Owner, UStaticMesh* Mesh, UMaterialInterface* Material, bool bShadowOnly)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(Owner);
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(Mesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		C->SetCanEverAffectNavigation(false);
		C->bReceivesDecals = false;
		C->bAffectDynamicIndirectLighting = false;
		C->bAffectDistanceFieldLighting = false;
		C->bVisibleInRayTracing = false;
		C->SetUsingAbsoluteRotation(true);
		C->SetUsingAbsoluteScale(true);
		if (bShadowOnly)
		{
			C->SetCastShadow(true);
			C->bCastHiddenShadow = true;
			C->SetHiddenInGame(true);
			C->ShadowCacheInvalidationBehavior = EShadowCacheInvalidationBehavior::Always;
		}
		else
		{
			C->SetCastShadow(false);
			C->SetBoundsScale(2.f);
		}
		C->SetupAttachment(Owner->GetRootComponent());
		C->RegisterComponent();
		C->SetMaterial(0, Material);
		return C;
	}
}

ASRWorker::ASRWorker()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;   // after the battle subsystem has set this frame's sprite view
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

ASRWorker* ASRWorker::SpawnWorker(ASRBuilding* InHome, int32 InIndex)
{
	UWorld* World = InHome ? InHome->GetWorld() : nullptr;
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
	if (!World || !Battle || !Battle->UnitCardMesh) { return nullptr; }

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ASRWorker* W = World->SpawnActor<ASRWorker>(InHome->GetActorLocation(), FRotator::ZeroRotator, Params);
	if (!W) { return nullptr; }
	W->Home = InHome;
	W->bMiner = InHome->BuildingType == ESRBuildingType::Mine;
	W->Index = InIndex;
	const int32 M = W->bMiner ? 0 : 1;
	W->Card = MakeCard(W, Battle->UnitCardMesh, Battle->WorkerMaterials[M], false);
	W->ShadowCard = MakeCard(W, Battle->UnitCardMesh, Battle->WorkerShadowMaterials[M], true);
	const FLinearColor TeamCol = Battle->TeamColor(InHome->Team);
	W->Card->SetCustomPrimitiveDataVector4(SRSprite::DataTeamColor, FVector4(TeamCol.R, TeamCol.G, TeamCol.B, 1.f));

	// Stagger the workers so deliveries alternate.
	if (W->bMiner)
	{
		W->Pos = W->LocalToWorld(MineAdit);
		W->Begin(EState::Inside);
		W->StateDuration *= (0.35f + 0.65f * InIndex);
	}
	else
	{
		W->Pos = W->LocalToWorld(FarmDrop + FVector2D(-60.f * InIndex, 40.f));
		W->Fade = 1.f;
		W->Begin(EState::ToWork);
	}
	W->Z = InHome->GetActorLocation().Z;
	return W;
}

FVector2D ASRWorker::LocalToWorld(const FVector2D& Local) const
{
	return Home.IsValid() ? Home->ToWorld2D(Local) : Local;
}

float ASRWorker::CycleTime() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const float Interval = bMiner ? F.MinePayoutInterval : F.FarmPayoutInterval;
	return FMath::Max(Interval * FMath::Max(F.WorkersPerBuilding, 1), 3.f);
}

void ASRWorker::Begin(EState NewState)
{
	State = NewState;
	StateTime = 0.f;
	const float Cycle = CycleTime();
	switch (NewState)
	{
	case EState::Inside:
		// out of sight in the mine: the rest of the cycle after the walks and the tip into the cart
		StateDuration = FMath::Max(Cycle - 2.f * FVector2D::Distance(MineAdit, MineCart) / WalkSpeed - 0.9f, 1.f) * FMath::FRandRange(0.9f, 1.1f);
		break;
	case EState::ToWork:
		if (bMiner)
		{
			Goal = LocalToWorld(MineAdit);
		}
		else
		{
			Goal = LocalToWorld(FVector2D(FMath::FRandRange(FieldX0, FieldX1), FMath::FRandRange(FieldY0, FieldY1)));
		}
		break;
	case EState::Working:
	{
		const float Walks = 2.f * FVector2D::Distance(Pos, LocalToWorld(FarmDrop)) / WalkSpeed;
		StateDuration = FMath::Max(Cycle - Walks - 0.9f, 1.5f) * FMath::FRandRange(0.9f, 1.1f);
		Yaw = FMath::FRandRange(-180.f, 180.f);
		break;
	}
	case EState::ToDrop:
		Goal = LocalToWorld(bMiner ? MineCart + FVector2D(0.f, 40.f * Index) : FarmDrop + FVector2D(-30.f * Index, 0.f));
		break;
	case EState::Dropping:
		StateDuration = 0.9f;
		break;
	}
}

bool ASRWorker::WalkTo(const FVector2D& Target, float Dt)
{
	const FVector2D To = Target - Pos;
	const float D = To.Size();
	if (D < 6.f) { bMoving = false; return true; }
	const float Step = FMath::Min(D, WalkSpeed * Dt);
	Pos += To / D * Step;
	WalkDistance += Step;
	Yaw = FMath::RadiansToDegrees(FMath::Atan2(To.Y, To.X));
	bMoving = true;
	return false;
}

void ASRWorker::Tick(float Dt)
{
	Super::Tick(Dt);
	ASRBuilding* B = Home.Get();
	if (!B || !B->IsFinished()) { Destroy(); return; }
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (Battle && Battle->IsFrozen()) { return; }

	StateTime += Dt;
	AnimClock += Dt;
	bMoving = false;

	switch (State)
	{
	case EState::Inside:
		Fade = 0.f;
		SoundClock -= Dt;
		if (SoundClock <= 0.f)
		{
			SoundClock = FMath::FRandRange(0.8f, 1.3f);
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::Pickaxe, FVector(LocalToWorld(MineAdit), Z + 80.f), 0.6f); }
		}
		if (StateTime >= StateDuration)
		{
			// out of the dark with a full basket
			Pos = LocalToWorld(MineAdit);
			Begin(EState::ToDrop);
		}
		break;

	case EState::ToWork:
		if (bMiner)
		{
			// walking back into the adit: fade into the dark over the last stretch
			const float D = FVector2D::Distance(Pos, Goal);
			Fade = FMath::Clamp((D - 10.f) / 70.f, 0.f, 1.f);
			if (WalkTo(Goal, Dt)) { Begin(EState::Inside); }
		}
		else
		{
			Fade = FMath::FInterpTo(Fade, 1.f, Dt, 6.f);
			if (WalkTo(Goal, Dt)) { AnimClock = 0.f; LastWorkFrame = -1; Begin(EState::Working); }
		}
		break;

	case EState::Working:
		if (StateTime >= StateDuration) { Begin(EState::ToDrop); }
		break;

	case EState::ToDrop:
		Fade = FMath::FInterpTo(Fade, 1.f, Dt, 5.f);
		if (WalkTo(Goal, Dt))
		{
			Yaw = bMiner ? 90.f : -90.f;
			Begin(EState::Dropping);
		}
		break;

	case EState::Dropping:
		if (StateTime >= StateDuration)
		{
			B->Deliver();
			Begin(EState::ToWork);
		}
		break;
	}

	if (Battle) { Battle->SampleGround(Pos, Z + 60.f, Z); }
	SetActorLocation(FVector(Pos.X, Pos.Y, Z));
	Present(Dt);
}

void ASRWorker::Present(float Dt)
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || !Card) { return; }
	const FSRSpriteView& View = Battle->GetSpriteView();
	const USRFeelSettings& F = USRFeelSettings::Get();
	Facing = SRSprite::FacingIndexSticky(Facing, Yaw, View.ViewYaw, F.FacingHysteresisDeg);
	ShadowFacing = SRSprite::FacingIndexSticky(ShadowFacing, Yaw, View.SunYaw, F.FacingHysteresisDeg);

	int32 Col = IdleCol, Row = 0;
	if (bMoving)
	{
		Col = WalkCol + (FMath::FloorToInt(WalkDistance / FMath::Max(F.WalkCycleDistance, 1.f) * 8.f) % 8);
	}
	else if (State == EState::Working)
	{
		const int32 Frame = FMath::FloorToInt(AnimClock * WorkFps) % 8;
		Col = WorkCol + Frame;
		Row = WorkRow;
		if (Frame == WorkStrikeFrame && LastWorkFrame != WorkStrikeFrame)
		{
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::Hoe, GetActorLocation(), 0.8f); }
		}
		LastWorkFrame = Frame;
	}
	else
	{
		Col = IdleCol + (FMath::FloorToInt(AnimClock * 5.f) % 8);
	}

	const bool bShown = Fade > 0.01f;
	if (Card->IsVisible() != bShown) { Card->SetVisibility(bShown); }
	ShadowCard->SetCastShadow(bShown && F.bSpriteShadows);

	const FVector4 Data(float(Col), float(Row + Facing), 0.f, Fade);
	if (!Data.Equals(Applied, 0.001f))
	{
		Applied = Data;
		Card->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, Data);
		ShadowCard->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, FVector4(float(Col), float(Row + ShadowFacing), 0.f, Fade));
	}
	Card->SetWorldRotation(View.CardRotation);
	if (bShown)
	{
		ShadowCard->SetRelativeLocation(FVector(0.f, 0.f, 1.f));
		ShadowCard->SetWorldRotation(View.ShadowRotation);
		ShadowCard->SetWorldScale3D(View.ShadowScale);
	}
}
