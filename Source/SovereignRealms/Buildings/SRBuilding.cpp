// Copyright Sovereign Realms.

#include "Buildings/SRBuilding.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRBattleSubsystem.h"
#include "Units/SRUnit.h"
#include "Common/SRRingComponent.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Components/StaticMeshComponent.h"
#include "Components/BoxComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"

ASRBuilding::ASRBuilding()
{
	// Stepped by USREconomySubsystem (through USRBattleSubsystem), like the units.
	PrimaryActorTick.bCanEverTick = false;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Static);
	SetRootComponent(Root);

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Root);
	Mesh->SetMobility(EComponentMobility::Static);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));      // contract: only the footprint box blocks
	Mesh->SetGenerateOverlapEvents(false);

	Blocker = CreateDefaultSubobject<UBoxComponent>(TEXT("Blocker"));
	Blocker->SetupAttachment(Root);
	Blocker->SetMobility(EComponentMobility::Static);
	Blocker->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Blocker->SetCollisionObjectType(ECC_WorldStatic);          // units trace WorldStatic for walls
	Blocker->SetCollisionResponseToAllChannels(ECR_Block);
	Blocker->SetGenerateOverlapEvents(false);
	Blocker->SetCanEverAffectNavigation(false);
	Blocker->SetHiddenInGame(true);
}

void ASRBuilding::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	RefreshBuilding();
}

void ASRBuilding::RefreshBuilding()
{
	if (Mesh->GetStaticMesh() != BuildingMesh) { Mesh->SetStaticMesh(BuildingMesh); }

	const FVector2D Centre = (FootprintMin + FootprintMax) * 0.5f;
	const FVector2D Half = (FootprintMax - FootprintMin) * 0.5f;
	Blocker->SetRelativeLocation(FVector(Centre.X, Centre.Y, BlockHeight * 0.5f));
	Blocker->SetBoxExtent(FVector(FMath::Max(Half.X, 1.f), FMath::Max(Half.Y, 1.f), BlockHeight * 0.5f));

	// Team colour: stored on the component so the level shows it in the editor; BeginPlay re-applies the live setting.
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FLinearColor Color = Team == ESRTeam::Player ? F.PlayerTeamColor : F.EnemyTeamColor;
	Mesh->SetDefaultCustomPrimitiveDataVector4(0, FVector4(Color.R, Color.G, Color.B, 1.f));
}

void ASRBuilding::BeginPlay()
{
	Super::BeginPlay();
	RefreshBuilding();

	const USRFeelSettings& F = USRFeelSettings::Get();
	const FVector2D Centre = (FootprintMin + FootprintMax) * 0.5f;
	const FVector2D Half = (FootprintMax - FootprintMin) * 0.5f + FVector2D(F.BuildingRingGap + F.BuildingRingWidth, F.BuildingRingGap + F.BuildingRingWidth);

	Ring = NewObject<USRRingComponent>(this, TEXT("Ring"));
	Ring->SetupAttachment(Root);
	Ring->SetRelativeLocation(FVector(Centre.X, Centre.Y, 5.f));
	Ring->RegisterComponent();
	Ring->BuildRoundedRect(Half, 70.f, F.BuildingRingWidth);
	Ring->SetVisibility(false);

	if (IsCastle())
	{
		if (UStaticMesh* FlagMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/SR/Buildings/SM_Bld_RallyFlag.SM_Bld_RallyFlag")))
		{
			RallyFlag = NewObject<UStaticMeshComponent>(this, TEXT("RallyFlag"));
			RallyFlag->SetMobility(EComponentMobility::Movable);
			RallyFlag->SetupAttachment(Root);
			RallyFlag->SetUsingAbsoluteLocation(true);
			RallyFlag->SetUsingAbsoluteRotation(true);
			RallyFlag->SetUsingAbsoluteScale(true);
			RallyFlag->SetCollisionProfileName(TEXT("NoCollision"));
			RallyFlag->SetStaticMesh(FlagMesh);
			RallyFlag->RegisterComponent();
			const FLinearColor Color = Team == ESRTeam::Player ? F.PlayerTeamColor : F.EnemyTeamColor;
			RallyFlag->SetCustomPrimitiveDataVector4(0, FVector4(Color.R, Color.G, Color.B, 1.f));
			RallyFlag->SetVisibility(false);
		}
		else
		{
			UE_LOG(LogSovereign, Warning, TEXT("Missing /Game/SR/Buildings/SM_Bld_RallyFlag: run Tools/blender/build_building.py -- rallyflag and Tools/import_buildings.py"));
		}
	}

	ResetRuntime();
	Economy = USREconomySubsystem::Get(this);
	if (Economy) { Economy->RegisterBuilding(this); }
}

void ASRBuilding::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Economy) { Economy->UnregisterBuilding(this); }
	Super::EndPlay(Reason);
}

// ------------------------------------------------------------------ run time

void ASRBuilding::ResetRuntime()
{
	Queue.Reset();
	BuildClock = 0.f;
	PayoutClock = 0.f;
	TimeSincePayout = 1000.f;
	RecruitCount = 0;
	RallyShowTime = 0.f;
	RallyPoint = ToWorld2D(FVector2D(RallyOffset.X, RallyOffset.Y));
	if (RallyFlag)
	{
		float Z = GetActorLocation().Z;
		if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->SampleGround(RallyPoint, Z + 200.f, Z); }
		RallyFlag->SetWorldLocation(FVector(RallyPoint.X, RallyPoint.Y, Z));
	}
}

void ASRBuilding::StepBuilding(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	TimeSincePayout += Dt;

	if (BuildingType == ESRBuildingType::Farm || BuildingType == ESRBuildingType::Mine)
	{
		const bool bFarm = BuildingType == ESRBuildingType::Farm;
		const float Interval = FMath::Max(bFarm ? F.FarmPayoutInterval : F.MinePayoutInterval, 0.2f);
		const int32 Amount = bFarm ? F.FarmFoodPerPayout : F.MineGoldPerPayout;
		PayoutClock += Dt;
		while (PayoutClock >= Interval)
		{
			PayoutClock -= Interval;
			if (Economy && Amount > 0)
			{
				const ESRResource Resource = bFarm ? ESRResource::Food : ESRResource::Gold;
				Economy->AddResource(Team, Resource, Amount);
				TimeSincePayout = 0.f;
				if (Team == ESRTeam::Player) { Economy->AddPopup(GetPopupPoint(), Amount, Resource); }
				UE_LOG(LogSovereign, Log, TEXT("PAYOUT %s +%d %s  (team %s now gold=%d food=%d)"), *GetActorNameOrLabel(), Amount, bFarm ? TEXT("food") : TEXT("gold"),
					Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"), Economy->GetResource(Team, ESRResource::Gold), Economy->GetResource(Team, ESRResource::Food));
			}
		}
	}
	else if (Queue.Num() > 0)
	{
		BuildClock += Dt;
		const float BuildTime = FMath::Max(F.BuildTimeFor(Queue[0]), 0.1f);
		if (BuildClock >= BuildTime)
		{
			const ESRUnitType Type = Queue[0];
			Queue.RemoveAt(0);
			BuildClock = 0.f;
			SpawnRecruit(Type);
		}
	}

	UpdateFeedback(Dt);
}

bool ASRBuilding::QueueRecruit(ESRUnitType Type)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const TCHAR* Name = *F.StatsFor(Type).DisplayName;
	if (!IsCastle() || !Economy)
	{
		UE_LOG(LogSovereign, Log, TEXT("RECRUIT refused: %s cannot recruit"), *GetActorNameOrLabel());
		return false;
	}
	if (Queue.Num() >= F.MaxRecruitQueue)
	{
		UE_LOG(LogSovereign, Log, TEXT("RECRUIT refused: %s queue full (%d)"), Name, Queue.Num());
		Economy->NotifyRefused();
		return false;
	}
	const FSRCost& Cost = F.CostFor(Type);
	if (!Economy->TrySpend(Team, Cost))
	{
		UE_LOG(LogSovereign, Log, TEXT("RECRUIT refused: %s costs gold=%d food=%d, have gold=%d food=%d"), Name, Cost.Gold, Cost.Food,
			Economy->GetResource(Team, ESRResource::Gold), Economy->GetResource(Team, ESRResource::Food));
		return false;
	}
	if (Queue.Num() == 0) { BuildClock = 0.f; }
	Queue.Add(Type);
	UE_LOG(LogSovereign, Log, TEXT("RECRUIT queued: %s at %s for gold=%d food=%d, %.1fs  (queue=%d, left gold=%d food=%d)"), Name, *GetActorNameOrLabel(), Cost.Gold, Cost.Food,
		F.BuildTimeFor(Type), Queue.Num(), Economy->GetResource(Team, ESRResource::Gold), Economy->GetResource(Team, ESRResource::Food));
	return true;
}

void ASRBuilding::SpawnRecruit(ESRUnitType Type)
{
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	const FVector Gate = GetGatePoint();
	const FVector2D Gate2D(Gate.X, Gate.Y);
	const FVector2D Out = (Gate2D - GetFootprintCentre()).GetSafeNormal();
	const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(Out.Y, Out.X));

	ASRUnit* Unit = Battle->SpawnUnit(Type, Team, Gate2D, Yaw, 0.f);
	if (!Unit) { return; }

	// Step clear of the gate, then round the buildings to the rally point. Recruits fan out a little so a batch does
	// not pile onto one spot.
	const int32 Slot = RecruitCount++ % 8;
	const FVector2D Side(-Out.Y, Out.X);
	const float Spread = F.StatsFor(Type).Radius * 2.f + F.FormationGap;
	const FVector2D Goal = RallyPoint + Side * ((Slot % 4) - 1.5f) * Spread - Out * (Slot / 4) * Spread;

	TArray<FVector2D> Path;
	const FVector2D Clear = Economy ? Economy->ClearOfBuildings(Gate2D + Out * (F.BuildingRouteMargin + 10.f)) : Gate2D;
	Path.Add(Clear);
	if (Economy) { Economy->RoutePath(Clear, Goal, Path); }
	else { Path.Add(Goal); }
	Unit->OrderMovePath(Path, false);
	Unit->SetHome(Path.Last());

	UE_LOG(LogSovereign, Log, TEXT("RECRUIT ready: %s emerges from %s at (%.0f, %.0f), rally (%.0f, %.0f) via %d waypoint(s)"), *Unit->GetLabel(), *GetActorNameOrLabel(),
		Gate.X, Gate.Y, Path.Last().X, Path.Last().Y, Path.Num());
}

float ASRBuilding::GetBuildFraction() const
{
	if (Queue.Num() == 0) { return 0.f; }
	return FMath::Clamp(BuildClock / FMath::Max(USRFeelSettings::Get().BuildTimeFor(Queue[0]), 0.1f), 0.f, 1.f);
}

float ASRBuilding::GetPayoutFraction() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (BuildingType == ESRBuildingType::Farm) { return FMath::Clamp(PayoutClock / FMath::Max(F.FarmPayoutInterval, 0.2f), 0.f, 1.f); }
	if (BuildingType == ESRBuildingType::Mine) { return FMath::Clamp(PayoutClock / FMath::Max(F.MinePayoutInterval, 0.2f), 0.f, 1.f); }
	return 0.f;
}

void ASRBuilding::SetRallyPoint(const FVector2D& WorldXY)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	FVector2D Point(FMath::Clamp(WorldXY.X, -F.MapHalfExtent.X, F.MapHalfExtent.X), FMath::Clamp(WorldXY.Y, -F.MapHalfExtent.Y, F.MapHalfExtent.Y));
	if (Economy) { Point = Economy->ClearOfBuildings(Point); }
	RallyPoint = Point;
	RallyShowTime = 3.f;
	RallyPop = 1.f;
	if (RallyFlag)
	{
		float Z = GetActorLocation().Z;
		if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->SampleGround(RallyPoint, Z + 200.f, Z); }
		RallyFlag->SetWorldLocation(FVector(RallyPoint.X, RallyPoint.Y, Z));
	}
	UE_LOG(LogSovereign, Log, TEXT("RALLY %s -> (%.0f, %.0f)"), *GetActorNameOrLabel(), RallyPoint.X, RallyPoint.Y);
}

// -------------------------------------------------------------------- queries

FString ASRBuilding::GetDisplayName() const
{
	switch (BuildingType)
	{
	case ESRBuildingType::Castle: return TEXT("Citadel");
	case ESRBuildingType::Farm: return TEXT("Farm");
	default: return TEXT("Gold Mine");
	}
}

FVector2D ASRBuilding::ToLocal2D(const FVector2D& World) const
{
	const FVector Local = GetActorTransform().InverseTransformPosition(FVector(World.X, World.Y, GetActorLocation().Z));
	return FVector2D(Local.X, Local.Y);
}

FVector2D ASRBuilding::ToWorld2D(const FVector2D& Local) const
{
	const FVector World = GetActorTransform().TransformPosition(FVector(Local.X, Local.Y, 0.f));
	return FVector2D(World.X, World.Y);
}

FVector ASRBuilding::LocalToWorldPoint(const FVector& Local) const
{
	return GetActorTransform().TransformPosition(Local);
}

bool ASRBuilding::ContainsXY(const FVector2D& World, float Margin) const
{
	const FVector2D L = ToLocal2D(World);
	return L.X > FootprintMin.X - Margin && L.X < FootprintMax.X + Margin && L.Y > FootprintMin.Y - Margin && L.Y < FootprintMax.Y + Margin;
}

FVector2D ASRBuilding::PushOutside(const FVector2D& World, float Margin) const
{
	FVector2D L = ToLocal2D(World);
	const FVector2D Min = FootprintMin - FVector2D(Margin, Margin), Max = FootprintMax + FVector2D(Margin, Margin);
	if (L.X <= Min.X || L.X >= Max.X || L.Y <= Min.Y || L.Y >= Max.Y) { return World; }
	// Out through the nearest side.
	const float Dists[4] = { L.X - Min.X, Max.X - L.X, L.Y - Min.Y, Max.Y - L.Y };
	int32 Best = 0;
	for (int32 i = 1; i < 4; ++i) { if (Dists[i] < Dists[Best]) { Best = i; } }
	if (Best == 0) { L.X = Min.X - 1.f; }
	else if (Best == 1) { L.X = Max.X + 1.f; }
	else if (Best == 2) { L.Y = Min.Y - 1.f; }
	else { L.Y = Max.Y + 1.f; }
	return ToWorld2D(L);
}

bool ASRBuilding::SegmentCrosses(const FVector2D& From, const FVector2D& To, float Margin, float& OutT) const
{
	const FVector2D A = ToLocal2D(From), B = ToLocal2D(To);
	const FVector2D Min = FootprintMin - FVector2D(Margin, Margin), Max = FootprintMax + FVector2D(Margin, Margin);
	const FVector2D D = B - A;
	float T0 = 0.f, T1 = 1.f;
	for (int32 Axis = 0; Axis < 2; ++Axis)
	{
		const float P = Axis == 0 ? A.X : A.Y, Dir = Axis == 0 ? D.X : D.Y;
		const float Lo = Axis == 0 ? Min.X : Min.Y, Hi = Axis == 0 ? Max.X : Max.Y;
		if (FMath::Abs(Dir) < KINDA_SMALL_NUMBER)
		{
			if (P <= Lo || P >= Hi) { return false; }
			continue;
		}
		float Ta = (Lo - P) / Dir, Tb = (Hi - P) / Dir;
		if (Ta > Tb) { Swap(Ta, Tb); }
		T0 = FMath::Max(T0, Ta);
		T1 = FMath::Min(T1, Tb);
		if (T0 >= T1) { return false; }
	}
	// Grazing a corner does not count.
	if ((T1 - T0) * D.Size() < 2.f) { return false; }
	OutT = T0;
	return true;
}

bool ASRBuilding::RayHit(const FVector& Origin, const FVector& Dir, float& OutAlong) const
{
	const FTransform& Xf = GetActorTransform();
	const FVector O = Xf.InverseTransformPosition(Origin);
	const FVector D = Xf.InverseTransformVectorNoScale(Dir);
	const FVector Min(FootprintMin.X, FootprintMin.Y, 0.f), Max(FootprintMax.X, FootprintMax.Y, BlockHeight);
	float T0 = 0.f, T1 = 1.e9f;
	for (int32 Axis = 0; Axis < 3; ++Axis)
	{
		if (FMath::Abs(D[Axis]) < KINDA_SMALL_NUMBER)
		{
			if (O[Axis] < Min[Axis] || O[Axis] > Max[Axis]) { return false; }
			continue;
		}
		float Ta = (Min[Axis] - O[Axis]) / D[Axis], Tb = (Max[Axis] - O[Axis]) / D[Axis];
		if (Ta > Tb) { Swap(Ta, Tb); }
		T0 = FMath::Max(T0, Ta);
		T1 = FMath::Min(T1, Tb);
		if (T0 > T1) { return false; }
	}
	OutAlong = T0;
	return true;
}

// ------------------------------------------------------------------- feedback

void ASRBuilding::SetSelected(bool bInSelected)
{
	if (bInSelected && !bSelected) { RingPop = 1.f; }
	bSelected = bInSelected;
}

void ASRBuilding::UpdateFeedback(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	RingPop = FMath::FInterpTo(RingPop, 0.f, Dt, 12.f);

	if (Ring)
	{
		const bool bShow = bSelected || bHovered;
		if (bShow != bRingVisible)
		{
			Ring->SetVisibility(bShow);
			bRingVisible = bShow;
		}
		if (bShow)
		{
			const FLinearColor Color = Team == ESRTeam::Enemy ? F.EnemyRingColor : (bSelected ? F.SelectionRingColor : F.HoverRingColor);
			Ring->SetRingColor(Color, bSelected ? 1.f : 0.7f);
			const float Scale = 1.f + 0.035f * RingPop;
			Ring->SetRelativeScale3D(FVector(Scale, Scale, 1.f));
		}
	}

	if (RallyFlag)
	{
		RallyShowTime = FMath::Max(0.f, RallyShowTime - Dt);
		RallyPop = FMath::FInterpTo(RallyPop, 0.f, Dt, 9.f);
		const bool bShow = Team == ESRTeam::Player && (bSelected || RallyShowTime > 0.f);
		if (bShow != RallyFlag->IsVisible()) { RallyFlag->SetVisibility(bShow); }
		if (bShow)
		{
			// Planted with a little overshoot, like the troops' spawn pop.
			const float Pop = 1.f + 0.35f * RallyPop;
			RallyFlag->SetWorldScale3D(FVector(1.f, 1.f, Pop));
		}
	}
}
