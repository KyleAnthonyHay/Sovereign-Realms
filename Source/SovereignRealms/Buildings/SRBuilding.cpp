// Copyright Sovereign Realms.

#include "Buildings/SRBuilding.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Buildings/SRWorker.h"
#include "Battle/SRPlatoonSubsystem.h"
#include "Units/SRUnit.h"
#include "Units/SRProjectile.h"
#include "Common/SRAudioSubsystem.h"
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
	Root->SetMobility(EComponentMobility::Movable);     // rises while it is built, collapses when destroyed
	SetRootComponent(Root);

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Root);
	Mesh->SetMobility(EComponentMobility::Movable);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));      // contract: only the footprint box blocks
	Mesh->SetGenerateOverlapEvents(false);

	Blocker = CreateDefaultSubobject<UBoxComponent>(TEXT("Blocker"));
	Blocker->SetupAttachment(Root);
	Blocker->SetMobility(EComponentMobility::Movable);
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

	MeshBaseLocation = Mesh->GetRelativeLocation();
	Economy = USREconomySubsystem::Get(this);
	ResetRuntime();
	if (Economy) { Economy->RegisterBuilding(this); }
	if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this)) { Grid->SetFootprint(this, true); }
}

void ASRBuilding::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Economy) { Economy->UnregisterBuilding(this); }
	if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this); Grid && !bDestroyed) { Grid->SetFootprint(this, false); }
	for (ASRWorker* W : Workers) { if (W) { W->Destroy(); } }
	Workers.Reset();
	Super::EndPlay(Reason);
}

// ------------------------------------------------------------------ run time

void ASRBuilding::ResetRuntime()
{
	// a level building that fell in the last battle stands again
	if (bDestroyed)
	{
		bDestroyed = false;
		Blocker->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this)) { Grid->SetFootprint(this, true); }
	}
	CollapseClock = 0.f;
	DefenceCooldown = FMath::FRandRange(0.f, 1.f);
	HitShake = 0.f;
	LastDamagedTime = -100.0;
	if (!bRuntimeBuilt) { BuildProgress = 1.f; }
	Health = Stats().MaxHealth * (BuildProgress >= 1.f ? 1.f : USRFeelSettings::Get().ConstructionStartHealth);
	Mesh->SetRelativeLocation(MeshBaseLocation);
	Mesh->SetRelativeRotation(FRotator::ZeroRotator);
	ApplyBuildVisual();
	if (Mesh) { Mesh->SetVisibility(true); }
	UpdateWorkers();
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
	HitShake = FMath::Max(0.f, HitShake - Dt * 5.f);

	if (bDestroyed) { StepCollapse(Dt); return; }
	if (BuildProgress < 1.f) { StepConstruction(Dt); UpdateFeedback(Dt); return; }

	if (BuildingType == ESRBuildingType::Farm || BuildingType == ESRBuildingType::Mine)
	{
		// With workers on screen the payout lands when one of them delivers (ASRWorker -> Deliver). Without, on a timer.
		if (F.WorkersPerBuilding <= 0 || Workers.Num() == 0)
		{
			const float Interval = FMath::Max(BuildingType == ESRBuildingType::Farm ? F.FarmPayoutInterval : F.MinePayoutInterval, 0.2f);
			PayoutClock += Dt;
			while (PayoutClock >= Interval)
			{
				PayoutClock -= Interval;
				Deliver();
			}
		}
		else
		{
			PayoutClock += Dt; // only drives the HUD's "next payout" meter
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

	StepDefence(Dt);
	UpdateFeedback(Dt);
}

void ASRBuilding::Deliver()
{
	if (!IsFinished() || !Economy) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const bool bFarm = BuildingType == ESRBuildingType::Farm;
	const int32 Amount = bFarm ? F.FarmFoodPerPayout : F.MineGoldPerPayout;
	if (Amount <= 0 || (BuildingType != ESRBuildingType::Farm && BuildingType != ESRBuildingType::Mine)) { return; }
	const ESRResource Resource = bFarm ? ESRResource::Food : ESRResource::Gold;
	Economy->AddResource(Team, Resource, Amount);
	TimeSincePayout = 0.f;
	PayoutClock = 0.f;
	if (Team == ESRTeam::Player)
	{
		Economy->AddPopup(GetPopupPoint(), Amount, Resource);
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(bFarm ? ESRSound::GrainPayout : ESRSound::CoinPayout, GetPopupPoint()); }
	}
	UE_LOG(LogSovereign, Verbose, TEXT("PAYOUT %s +%d %s  (team %s now gold=%d food=%d)"), *GetActorNameOrLabel(), Amount, bFarm ? TEXT("food") : TEXT("gold"),
		Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"), Economy->GetResource(Team, ESRResource::Gold), Economy->GetResource(Team, ESRResource::Food));
}

bool ASRBuilding::QueueRecruit(ESRUnitType Type)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const TCHAR* Name = *F.StatsFor(Type).DisplayName;
	if (!CanRecruit() || !Economy)
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
	const int32 PopNeeded = Economy->GetPopulation(Team) + Economy->GetQueuedPopulation(Team) + F.StatsFor(Type).PopCost;
	if (PopNeeded > Economy->GetPopulationCap(Team))
	{
		UE_LOG(LogSovereign, Log, TEXT("RECRUIT refused: %s, population %d/%d (build farms to house more troops)"), Name, PopNeeded - F.StatsFor(Type).PopCost, Economy->GetPopulationCap(Team));
		Economy->NotifyPopulationCapped(Team);
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
	const FVector2D Clear = Gate2D + Out * (F.BuildingRouteMargin + 10.f);
	Path.Add(Clear);
	if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this))
	{
		TArray<FVector2D> Rest;
		Grid->FindPath(Clear, Goal, Rest);
		Path.Append(Rest);
	}
	else { Path.Add(Goal); }
	Unit->OrderMovePath(Path, false);
	Unit->SetHome(Path.Last());
	if (Team == ESRTeam::Player)
	{
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::RecruitReady); }
		if (USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this)) { Platoons->OnRecruit(Unit); }
	}

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
	return Stats().DisplayName;
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

	// A shudder when struck.
	if (HitShake > 0.f)
	{
		const float A = 4.f * HitShake;
		Mesh->SetRelativeLocation(MeshBaseLocation + FVector(FMath::FRandRange(-A, A), FMath::FRandRange(-A, A), 0.f));
	}
	else if (!Mesh->GetRelativeLocation().Equals(MeshBaseLocation, 0.01f))
	{
		Mesh->SetRelativeLocation(MeshBaseLocation);
	}

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

// ------------------------------------------------------------------ life, construction, defence

ASRBuilding* ASRBuilding::SpawnBuilding(UWorld* World, ESRBuildingType Type, ESRTeam InTeam, const FVector& Location, bool bUnderConstruction)
{
	if (!World) { return nullptr; }
	const FSRBuildingStats& S = USRFeelSettings::Get().BuildingStatsFor(Type);
	ASRBuilding* B = World->SpawnActorDeferred<ASRBuilding>(ASRBuilding::StaticClass(), FTransform(FRotator::ZeroRotator, Location), nullptr, nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (!B) { return nullptr; }
	B->BuildingType = Type;
	B->Team = InTeam;
	B->BuildingMesh = S.Mesh.LoadSynchronous();
	B->FootprintMin = S.FootprintMin;
	B->FootprintMax = S.FootprintMax;
	B->BlockHeight = S.BlockHeight;
	B->RingRadius = FMath::Max(S.FootprintMax.X - S.FootprintMin.X, S.FootprintMax.Y - S.FootprintMin.Y) * 0.7f;
	B->GateOffset = S.GateOffset;
	B->RallyOffset = S.GateOffset + FVector(-250.f, 0.f, 0.f);
	B->LabelOffset = S.LabelOffset;
	B->PopupOffset = S.PopupOffset;
	B->bRuntimeBuilt = true;
	B->BuildProgress = bUnderConstruction ? 0.f : 1.f;
	B->FinishSpawning(FTransform(FRotator::ZeroRotator, Location));
	if (!B->BuildingMesh)
	{
		UE_LOG(LogSovereign, Warning, TEXT("BUILD %s has no mesh (%s): run the building pipeline (Tools/blender/build_building.py, Tools/import_buildings.py)"),
			*S.DisplayName, *S.Mesh.ToString());
	}

	// Our own troops standing on the foundations step aside.
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World))
	{
		for (ASRUnit* U : Battle->GetUnits())
		{
			if (U && U->IsAlive() && B->ContainsXY(U->GetPos2D(), U->GetRadius()))
			{
				const FVector2D To = B->PushOutside(U->GetPos2D(), U->GetRadius() + 40.f);
				U->OrderMove(To);
			}
		}
	}
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(World); Audio && bUnderConstruction) { Audio->PlayAt(ESRSound::BuildPlace, Location); }
	UE_LOG(LogSovereign, Log, TEXT("BUILD %s %s laid at (%.0f, %.0f)%s"), InTeam == ESRTeam::Player ? TEXT("player") : TEXT("enemy"), *S.DisplayName,
		Location.X, Location.Y, bUnderConstruction ? TEXT(", under construction") : TEXT(""));
	return B;
}

const FSRBuildingStats& ASRBuilding::Stats() const
{
	return USRFeelSettings::Get().BuildingStatsFor(BuildingType);
}

float ASRBuilding::GetHealthFrac() const
{
	return FMath::Clamp(Health / FMath::Max(Stats().MaxHealth, 1.f), 0.f, 1.f);
}

void ASRBuilding::StepConstruction(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRBuildingStats& S = Stats();
	const float Before = BuildProgress;
	BuildProgress = FMath::Min(1.f, BuildProgress + Dt / FMath::Max(S.BuildTime, 0.5f));
	Health = FMath::Min(S.MaxHealth, Health + S.MaxHealth * (1.f - F.ConstructionStartHealth) * (BuildProgress - Before));
	ApplyBuildVisual();

	HammerClock -= Dt;
	if (HammerClock <= 0.f)
	{
		HammerClock = FMath::FRandRange(0.45f, 0.8f);
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::BuildHammer, GetLabelPoint() * FVector(1, 1, 0) + FVector(0, 0, GetActorLocation().Z + 150.f)); }
	}

	if (BuildProgress >= 1.f)
	{
		Health = FMath::Max(Health, S.MaxHealth * 0.999f);
		UE_LOG(LogSovereign, Log, TEXT("BUILD %s finished at (%.0f, %.0f)"), *GetDisplayName(), GetActorLocation().X, GetActorLocation().Y);
		if (Team == ESRTeam::Player)
		{
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::BuildComplete); }
		}
		if (Economy) { Economy->NotifyBuildingFinished(this); }
		RallyPoint = ToWorld2D(FVector2D(RallyOffset.X, RallyOffset.Y));
		UpdateWorkers();
	}
}

void ASRBuilding::ApplyBuildVisual()
{
	if (!Mesh || bDestroyed) { return; }
	if (BuildProgress >= 1.f)
	{
		Mesh->SetRelativeScale3D(FVector::OneVector);
		return;
	}
	// The walls rise course by course: stepped, not smooth, so it reads as building work rather than a stretch.
	const float Courses = 14.f;
	const float P = FMath::FloorToFloat(FMath::Pow(BuildProgress, 0.85f) * Courses) / Courses;
	Mesh->SetRelativeScale3D(FVector(1.f, 1.f, FMath::Max(0.06f, P)));
}

void ASRBuilding::StepDefence(float Dt)
{
	const FSRBuildingStats& S = Stats();
	if (S.AttackRange <= 0.f || S.AttackDamage <= 0.f) { return; }
	DefenceCooldown -= Dt;
	if (DefenceCooldown > 0.f) { return; }

	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }
	const FVector2D C = GetFootprintCentre();
	ASRUnit* Best = nullptr;
	float BestD = FMath::Square(S.AttackRange);
	for (ASRUnit* U : Battle->GetUnits())
	{
		if (!U || !U->IsActive() || U->GetTeam() == Team) { continue; }
		const float D = FVector2D::DistSquared(U->GetPos2D(), C);
		if (D < BestD) { BestD = D; Best = U; }
	}
	if (!Best) { DefenceCooldown = 0.25f; return; }

	DefenceCooldown = S.AttackInterval * FMath::FRandRange(0.9f, 1.1f);
	const FVector Muzzle = FVector(C.X, C.Y, GetActorLocation().Z + S.MuzzleHeight) + FVector((Best->GetPos2D() - C).GetSafeNormal() * 120.f, 0.f);
	ASRProjectile::LaunchArrow(GetWorld(), Team, nullptr, Best, nullptr, Muzzle, S.AttackDamage, 60.f, 2200.f, 0.1f);
}

void ASRBuilding::ReceiveDamage(float Amount, ASRUnit* From)
{
	if (bDestroyed || Amount <= 0.f) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	Health = FMath::Max(0.f, Health - Amount);
	LastDamagedTime = GetWorld()->GetTimeSeconds();
	HitShake = 1.f;
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::BuildingHit, GetAimPointFrom(From ? From->GetPos2D() : GetFootprintCentre())); }
	if (Economy) { Economy->NotifyBuildingAttacked(this, From); }

	// Troops of ours nearby come to its defence.
	if (From && From->IsAlive())
	{
		if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
		{
			const FVector2D C = GetFootprintCentre();
			for (ASRUnit* U : Battle->GetUnits())
			{
				if (U && U->GetTeam() == Team && FVector2D::DistSquared(U->GetPos2D(), C) < FMath::Square(F.AlertRadius * 2.f)) { U->AlertTo(From); }
			}
		}
	}

	if (Health <= 0.f) { Collapse(From); }
}

void ASRBuilding::Collapse(ASRUnit* Killer)
{
	if (bDestroyed) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this)) { Grid->SetFootprint(this, false); }
	bDestroyed = true;
	CollapseClock = 0.f;
	Queue.Reset();
	Blocker->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SetSelected(false);
	for (ASRWorker* W : Workers) { if (W) { W->Destroy(); } }
	Workers.Reset();
	if (Ring) { Ring->SetVisibility(false); bRingVisible = false; }
	if (RallyFlag) { RallyFlag->SetVisibility(false); }

	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::BuildingCollapse, GetLabelPoint(), 1.f); }
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->AddCameraTrauma(GetActorLocation(), F.ShakeTraumaDeath * 1.6f); }
	UE_LOG(LogSovereign, Log, TEXT("DESTROYED %s %s at (%.0f, %.0f) by %s"), Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"), *GetDisplayName(),
		GetActorLocation().X, GetActorLocation().Y, Killer ? *Killer->GetLabel() : TEXT("?"));
	if (Economy) { Economy->NotifyBuildingDestroyed(this); }
}

void ASRBuilding::StepCollapse(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	CollapseClock += Dt;
	const float T = FMath::Clamp(CollapseClock / FMath::Max(F.CollapseTime, 0.1f), 0.f, 1.f);
	const float E = T * T;                                            // falls faster as it goes
	const float Shake = (1.f - T) * 6.f;
	Mesh->SetRelativeLocation(MeshBaseLocation + FVector(FMath::FRandRange(-Shake, Shake), FMath::FRandRange(-Shake, Shake), -BlockHeight * 0.18f * E));
	Mesh->SetRelativeRotation(FRotator(0.f, 0.f, 3.5f * E));
	Mesh->SetRelativeScale3D(FVector(1.f + 0.04f * E, 1.f + 0.04f * E, FMath::Lerp(1.f, 0.28f, E)));   // slumps into a heap of rubble

	if (CollapseClock > F.CollapseTime * 6.f && bRuntimeBuilt)
	{
		Destroy();
	}
}

void ASRBuilding::CancelConstruction()
{
	if (!IsUnderConstruction()) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (Economy)
	{
		const FSRCost& C = Stats().Cost;
		Economy->AddResource(Team, ESRResource::Gold, FMath::RoundToInt(C.Gold * F.CancelRefund));
		Economy->AddResource(Team, ESRResource::Food, FMath::RoundToInt(C.Food * F.CancelRefund));
	}
	UE_LOG(LogSovereign, Log, TEXT("BUILD %s cancelled"), *GetDisplayName());
	if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this)) { Grid->SetFootprint(this, false); }
	bDestroyed = true;
	Destroy();
}

FVector2D ASRBuilding::ClosestPointOnFootprint(const FVector2D& World, float Margin) const
{
	const FVector2D L = ToLocal2D(World);
	const FVector2D Min = FootprintMin - FVector2D(Margin, Margin), Max = FootprintMax + FVector2D(Margin, Margin);
	FVector2D C(FMath::Clamp(L.X, Min.X, Max.X), FMath::Clamp(L.Y, Min.Y, Max.Y));
	if (C == L)
	{
		// inside: out through the nearest side
		return PushOutside(World, Margin);
	}
	return ToWorld2D(C);
}

float ASRBuilding::DistanceToFootprint(const FVector2D& World) const
{
	const FVector2D L = ToLocal2D(World);
	const float Dx = FMath::Max3(float(FootprintMin.X - L.X), 0.f, float(L.X - FootprintMax.X));
	const float Dy = FMath::Max3(float(FootprintMin.Y - L.Y), 0.f, float(L.Y - FootprintMax.Y));
	return FMath::Sqrt(Dx * Dx + Dy * Dy);
}

FVector ASRBuilding::GetAimPointFrom(const FVector2D& From) const
{
	const FVector2D P = ClosestPointOnFootprint(From, -40.f);
	return FVector(P.X, P.Y, GetActorLocation().Z + FMath::Min(BlockHeight * 0.4f, 260.f));
}

void ASRBuilding::UpdateWorkers()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!IsFinished() || (BuildingType != ESRBuildingType::Farm && BuildingType != ESRBuildingType::Mine)) { return; }
	while (Workers.Num() < F.WorkersPerBuilding)
	{
		ASRWorker* W = ASRWorker::SpawnWorker(this, Workers.Num());
		if (!W) { break; }
		Workers.Add(W);
	}
}
