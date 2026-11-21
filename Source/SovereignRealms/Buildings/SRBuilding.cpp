// Copyright Sovereign Realms.

#include "Buildings/SRBuilding.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRAISubsystem.h"
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
#include "Misc/PackageName.h"
#include "FX/SRFXSprite.h"
#include "FX/SRFire.h"
#include "Units/SRSprite.h"

namespace { float SRYawOf(const FVector2D& V) { return FMath::RadiansToDegrees(FMath::Atan2(V.Y, V.X)); } }
#include "Components/AudioComponent.h"

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

	BaseLabelOffset = LabelOffset;
	LoadStateMeshes();

	if (IsRecruiter())
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
	StopFireSound(0.1f);
	ClearStateFX(false);
	if (ASRBuildingFire* Fire = FireFX.Get()) { Fire->Finish(); }
	FireFX = nullptr;
	if (Economy) { Economy->UnregisterBuilding(this); }
	if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this); Grid && !bDestroyed) { Grid->SetFootprint(this, false); }
	if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this); Grid && (BuildingType == ESRBuildingType::RelicTower || BuildingType == ESRBuildingType::Tower)) { Grid->ReleaseRelic(this); }   // the ruin stands again
	for (ASRWorker* W : Workers) { if (W) { W->Destroy(); } }
	Workers.Reset();
	Super::EndPlay(Reason);
}

// ------------------------------------------------------------------ run time

void ASRBuilding::ResetRuntime()
{
	Level = 1;
	UpgradeProgress = -1.f;
	// a level building that fell in the last battle stands again
	if (bDestroyed)
	{
		bDestroyed = false;
		Blocker->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this)) { Grid->SetFootprint(this, true); }
	}
	CollapseClock = 0.f;
	if (ASRBuildingFire* Fire = FireFX.Get()) { Fire->Destroy(); }
	FireFX = nullptr;
	FireSeated = 0;
	Soot = 0.f;
	DefenceCooldown = FMath::FRandRange(0.f, 1.f);
	for (FPostArcher& P : Posts) { P.Clock = -1.f; P.bLoosed = true; P.Mark = nullptr; }
	HitShake = 0.f;
	LastDamagedTime = -100.0;
	if (!bRuntimeBuilt) { BuildProgress = 1.f; }
	Health = GetMaxHealth() * (BuildProgress >= 1.f ? 1.f : USRFeelSettings::Get().ConstructionStartHealth);
	Mesh->SetRelativeLocation(MeshBaseLocation);
	Mesh->SetRelativeRotation(FRotator::ZeroRotator);
	SetState(BuildProgress < 1.f ? ESRBuildingState::Site : ESRBuildingState::Complete);
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
	StepFire(Dt);
	StepPosts(Dt);

	if (bDestroyed) { StepCollapse(Dt); return; }
	CountBuilders();
	if (BuildProgress < 1.f) { StepConstruction(Dt); UpdateFeedback(Dt); return; }
	StepRepair(Dt);
	StepUpgrade(Dt);
	StepFireSound(Dt);
	StepLife(Dt);

	// under repair it does not work: no payouts, no training, no shooting (it picks up where it left off)
	if (bRepairing) { UpdateFeedback(Dt); return; }

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
		BuildClock += Dt * GetTrainSpeed();
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
	if (!IsFinished() || !Economy || bRepairing) { return; }   // (a worker's load is lost while it is mended)
	const USRFeelSettings& F = USRFeelSettings::Get();
	const bool bFarm = BuildingType == ESRBuildingType::Farm;
	int32 Amount = GetPayoutAmount();
	// An easier commander gets only a share of its output (USRAISubsystem::Profile).
	if (const USRAISubsystem* AI = USRAISubsystem::Get(this)) { Amount = FMath::RoundToInt(Amount * AI->IncomeScale(Team)); }
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
	if (!CanRecruit() || !Trains(Type) || !Economy)
	{
		UE_LOG(LogSovereign, Log, TEXT("RECRUIT refused: %s cannot recruit"), *GetActorNameOrLabel());
		return false;
	}
	if (F.MaxRecruitQueue > 0 && Queue.Num() >= F.MaxRecruitQueue)
	{
		UE_LOG(LogSovereign, Log, TEXT("RECRUIT refused: %s queue full (%d)"), Name, Queue.Num());
		Economy->NotifyRefused();
		return false;
	}
	if (Type == ESRUnitType::Scout)
	{
		// castle level, one at a time, and a wait between two (USREconomySubsystem::GetScoutRefusal)
		const FText Why = Economy->GetScoutRefusal(Team);
		if (!Why.IsEmpty())
		{
			UE_LOG(LogSovereign, Log, TEXT("RECRUIT refused: Scout (%s): %s"), Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"), *Why.ToString());
			if (Team == ESRTeam::Player) { Economy->PushAlert(ESRAlertKind::Info, Why); }
			Economy->NotifyRefused();
			return false;
		}
	}
	if (Type == ESRUnitType::Builder)
	{
		int32 Queued = 0;
		const int32 Alive = Economy->GetBuilderCount(Team, &Queued);
		const int32 MaxB = Economy->GetMaxBuilders(Team);
		if (Alive + Queued >= MaxB)
		{
			UE_LOG(LogSovereign, Log, TEXT("RECRUIT refused: Builder limit %d reached"), MaxB);
			if (Team == ESRTeam::Player)
			{
				Economy->PushAlert(ESRAlertKind::Info, FText::Format(NSLOCTEXT("SRBuilding", "BuilderCap", "You can have at most {0} Builders (raise the Citadel for more)"), FText::AsNumber(MaxB)));
			}
			Economy->NotifyRefused();
			return false;
		}
	}
	const int32 PopNeeded = Economy->GetPopulation(Team) + Economy->GetQueuedPopulation(Team) + F.StatsFor(Type).PopCost;
	if (F.StatsFor(Type).PopCost > 0 && PopNeeded > Economy->GetPopulationCap(Team))
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
	// the wait before the next Scout runs from now: queued and paid for
	if (Type == ESRUnitType::Scout) { Economy->SetScoutCooldown(Team, F.ScoutCooldown); }
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
	Battle->NoteRecruit(Team);
	if (!Unit) { return; }
	if (Type == ESRUnitType::Horseman)
	{
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::HorseNeigh, FVector(Gate2D, GetActorLocation().Z + 150.f)); }
	}

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
		if (USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this)) { Platoons->OnRecruit(Unit, AssignedPlatoon); }
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
	if (bInSelected && !bSelected) { RingPop = 1.f; if (Team == ESRTeam::Player && !bDestroyed) { PlayVoice(); } }
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
	B->RallyOffset = S.GateOffset + FVector(-450.f, 0.f, 0.f);
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
	return FMath::Clamp(Health / FMath::Max(GetMaxHealth(), 1.f), 0.f, 1.f);
}

int32 ASRBuilding::GetPopProvided() const
{
	if (!IsFinished()) { return 0; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (BuildingType == ESRBuildingType::Farm && F.FarmLevels.Num() > 0) { return F.FarmLevel(Level).Housing; }
	return IsCastle() ? F.CastleLevel(Level).Housing : Stats().PopProvided;
}

float ASRBuilding::GetTrainSpeed() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return IsTrainer() && F.TrainerLevels.Num() > 0 ? FMath::Max(F.TrainerLevel(Level).TrainSpeed, 0.1f) : 1.f;
}

float ASRBuilding::GetTrainTime(ESRUnitType Type) const
{
	return USRFeelSettings::Get().BuildTimeFor(Type) / GetTrainSpeed();
}

int32 ASRBuilding::GetStoreCapacity() const
{
	return IsStore() ? USRFeelSettings::Get().StoreLevel(BuildingType == ESRBuildingType::Granary, Level).Capacity : 0;
}

float ASRBuilding::GetMaxHealth() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (IsTrainer() && F.TrainerLevels.Num() > 0) { return Stats().MaxHealth * F.TrainerLevel(Level).HealthScale; }
	switch (BuildingType)
	{
	case ESRBuildingType::Granary: return F.GranaryLevels.Num() > 0 ? F.StoreLevel(true, Level).Health : Stats().MaxHealth;
	case ESRBuildingType::Treasury: return F.TreasuryLevels.Num() > 0 ? F.StoreLevel(false, Level).Health : Stats().MaxHealth;
	case ESRBuildingType::Castle: return F.CastleLevel(Level).Health;
	case ESRBuildingType::Tower: return F.TowerLevels.Num() > 0 ? F.TowerLevel(Level).Health : Stats().MaxHealth;
	case ESRBuildingType::Mine: return F.MineLevels.Num() > 0 ? F.MineLevel(Level).Health : Stats().MaxHealth;
	case ESRBuildingType::Farm: return F.FarmLevels.Num() > 0 ? F.FarmLevel(Level).Health : Stats().MaxHealth;
	default: return Stats().MaxHealth;
	}
}

int32 ASRBuilding::GetMaxLevel() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	switch (BuildingType)
	{
	case ESRBuildingType::Castle: return F.CastleMaxLevel();
	case ESRBuildingType::Tower: return FMath::Max(1, F.TowerLevels.Num());
	case ESRBuildingType::Mine: return FMath::Max(1, F.MineLevels.Num());
	case ESRBuildingType::Barracks: case ESRBuildingType::Range: case ESRBuildingType::Stable: case ESRBuildingType::Workshop: return FMath::Max(1, F.TrainerLevels.Num());
	case ESRBuildingType::Granary: return FMath::Max(1, F.GranaryLevels.Num());
	case ESRBuildingType::Treasury: return FMath::Max(1, F.TreasuryLevels.Num());
	case ESRBuildingType::Farm: return FMath::Max(1, F.FarmLevels.Num());
	default: return 1;
	}
}

float ASRBuilding::GetAttackRange() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return BuildingType == ESRBuildingType::Tower && F.TowerLevels.Num() > 0 ? F.TowerLevel(Level).Range : Stats().AttackRange;
}

float ASRBuilding::GetAttackDamage() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (BuildingType == ESRBuildingType::Castle && F.CastleLevels.Num() > 0) { return F.CastleLevel(Level).ArrowDamage; }
	return BuildingType == ESRBuildingType::Tower && F.TowerLevels.Num() > 0 ? F.TowerLevel(Level).Damage : Stats().AttackDamage;
}

int32 ASRBuilding::GetArcherCount() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (BuildingType == ESRBuildingType::Castle && F.CastleLevels.Num() > 0) { return FMath::Clamp(F.CastleLevel(Level).Archers, 0, 4); }
	return Stats().Archers;
}

float ASRBuilding::GetAttackInterval() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return BuildingType == ESRBuildingType::Tower && F.TowerLevels.Num() > 0 ? F.TowerLevel(Level).Interval : Stats().AttackInterval;
}

int32 ASRBuilding::GetPayoutAmount() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (BuildingType == ESRBuildingType::Farm) { return F.FarmLevels.Num() > 0 ? F.FarmLevel(Level).FoodPerPayout : F.FarmFoodPerPayout; }
	if (BuildingType == ESRBuildingType::Mine) { return F.MineLevels.Num() > 0 ? F.MineLevel(Level).GoldPerPayout : F.MineGoldPerPayout; }
	return 0;
}

float ASRBuilding::GetUpgradeTime() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	switch (BuildingType)
	{
	case ESRBuildingType::Castle: return F.CastleLevel(Level + 1).UpgradeTime;
	case ESRBuildingType::Tower: return F.TowerLevel(Level + 1).UpgradeTime;
	case ESRBuildingType::Mine: return F.MineLevel(Level + 1).UpgradeTime;
	case ESRBuildingType::Barracks: case ESRBuildingType::Range: case ESRBuildingType::Stable: case ESRBuildingType::Workshop: return F.TrainerLevel(Level + 1).UpgradeTime;
	case ESRBuildingType::Granary: return F.StoreLevel(true, Level + 1).UpgradeTime;
	case ESRBuildingType::Treasury: return F.StoreLevel(false, Level + 1).UpgradeTime;
	case ESRBuildingType::Farm: return F.FarmLevel(Level + 1).UpgradeTime;
	default: return 30.f;
	}
}

float ASRBuilding::GetBuildZoneRadius() const
{
	return IsCastle() ? USRFeelSettings::Get().CastleLevel(Level).BuildZone : Stats().TerritoryRadius;
}

bool ASRBuilding::CanUpgrade() const
{
	if (!IsUpgradable() || !IsFinished() || IsUpgrading() || Level >= GetMaxLevel()) { return false; }
	// some levels wait for the Citadel (a storehouse's)
	const int32 Need = GetUpgradeRequiredCastleLevel();
	return Need <= 0 || !Economy || Economy->GetCastleLevel(Team) >= Need;
}

int32 ASRBuilding::GetUpgradeRequiredCastleLevel() const
{
	if (!IsStore() || Level >= GetMaxLevel()) { return 0; }
	return USRFeelSettings::Get().StoreLevel(BuildingType == ESRBuildingType::Granary, Level + 1).RequiredCastleLevel;
}

FSRCost ASRBuilding::GetUpgradeCost() const
{
	return GetUpgradeCostTo(Level + 1);
}

FSRCost ASRBuilding::GetUpgradeCostTo(int32 ToLevel) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	switch (BuildingType)
	{
	case ESRBuildingType::Castle: return F.CastleLevel(ToLevel).UpgradeCost;
	case ESRBuildingType::Tower: return F.TowerLevel(ToLevel).UpgradeCost;
	case ESRBuildingType::Mine: return F.MineLevel(ToLevel).UpgradeCost;
	case ESRBuildingType::Barracks: case ESRBuildingType::Range: case ESRBuildingType::Stable: case ESRBuildingType::Workshop: return F.TrainerLevel(ToLevel).UpgradeCost;
	case ESRBuildingType::Granary: return F.StoreLevel(true, ToLevel).UpgradeCost;
	case ESRBuildingType::Treasury: return F.StoreLevel(false, ToLevel).UpgradeCost;
	case ESRBuildingType::Farm: return F.FarmLevel(ToLevel).UpgradeCost;
	default: return FSRCost(0, 0);
	}
}

FSRCost ASRBuilding::GetDemolishRefund() const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	// everything paid for it: its price, each level it was raised to, and the level being raised now
	FSRCost Paid = Stats().Cost;
	const int32 Top = IsUpgrading() ? Level + 1 : Level;
	for (int32 L = 2; L <= Top; ++L) { const FSRCost C = GetUpgradeCostTo(L); Paid.Gold += C.Gold; Paid.Food += C.Food; }
	FSRCost Back(FMath::RoundToInt(Paid.Gold * F.DemolishRefund), FMath::RoundToInt(Paid.Food * F.DemolishRefund));
	// recruits paid for and not yet trained: all of it
	for (ESRUnitType T : Queue) { const FSRCost& C = F.CostFor(T); Back.Gold += C.Gold; Back.Food += C.Food; }
	return Back;
}

void ASRBuilding::Demolish()
{
	if (!CanDemolish()) { return; }
	const FSRCost Back = GetDemolishRefund();
	UE_LOG(LogSovereign, Log, TEXT("DEMOLISH %s %s (level %d): %d gold, %d food back"), Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"),
		*GetDisplayName(), Level, Back.Gold, Back.Food);
	Collapse(nullptr, true);
	if (Economy)
	{
		// (after the fall: a storehouse's own capacity is gone by now, so what no longer fits is lost, as when one falls)
		Economy->AddResource(Team, ESRResource::Gold, Back.Gold);
		Economy->AddResource(Team, ESRResource::Food, Back.Food);
		if (Team == ESRTeam::Player)
		{
			const FVector2D At = GetFootprintCentre();
			Economy->PushAlert(ESRAlertKind::Info, FText::Format(NSLOCTEXT("SRBuilding", "Demolished", "{0} demolished: {1} gold and {2} food back"),
				FText::FromString(GetDisplayName()), FText::AsNumber(Back.Gold), FText::AsNumber(Back.Food)), &At);
			if (Back.Gold > 0) { Economy->AddPopup(GetLabelPoint(), Back.Gold, ESRResource::Gold); }
			else if (Back.Food > 0) { Economy->AddPopup(GetLabelPoint(), Back.Food, ESRResource::Food); }
		}
	}
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->SpawnFX(ESRFX::Dust, GetActorLocation() + FVector(0.f, 0.f, 60.f), 3.f); }
}

bool ASRBuilding::StartUpgrade()
{
	if (Economy && IsFinished() && !IsUpgrading() && Level < GetMaxLevel() && GetUpgradeRequiredCastleLevel() > Economy->GetCastleLevel(Team))
	{
		UE_LOG(LogSovereign, Log, TEXT("UPGRADE refused: %s level %d needs the Citadel at level %d"), *GetDisplayName(), Level + 1, GetUpgradeRequiredCastleLevel());
		if (Team == ESRTeam::Player)
		{
			Economy->PushAlert(ESRAlertKind::Info, FText::Format(NSLOCTEXT("SRBuilding", "NeedCastle", "Raise the Citadel to level {0} first"), FText::AsNumber(GetUpgradeRequiredCastleLevel())));
			Economy->NotifyRefused();
		}
		return false;
	}
	if (!CanUpgrade() || !Economy) { return false; }
	if (!Economy->TrySpend(Team, GetUpgradeCost()))
	{
		UE_LOG(LogSovereign, Log, TEXT("UPGRADE refused: %s level %d costs %d gold"), *GetDisplayName(), Level + 1, GetUpgradeCost().Gold);
		return false;
	}
	UpgradeProgress = 0.f;
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this); Audio && Team == ESRTeam::Player) { Audio->PlayAt(ESRSound::BuildPlace, GetLabelPoint()); }
	UE_LOG(LogSovereign, Log, TEXT("UPGRADE %s %s to level %d started"), Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"), *GetDisplayName(), Level + 1);
	return true;
}

void ASRBuilding::StepUpgrade(float Dt)
{
	if (!IsUpgrading()) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	// builders at the walls speed it up, as they do a site
	const float Rate = 1.f + F.BuilderExtraSpeed * BuildersWorking;
	UpgradeProgress += Rate * Dt / FMath::Max(GetUpgradeTime(), 1.f);
	HammerClock -= Dt;
	if (HammerClock <= 0.f && BuildersWorking == 0)
	{
		HammerClock = FMath::FRandRange(0.6f, 1.0f);
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::BuildHammer, GetLabelPoint() * FVector(1, 1, 0) + FVector(0, 0, GetActorLocation().Z + 250.f)); }
	}
	if (UpgradeProgress < 1.f) { return; }
	UpgradeProgress = -1.f;
	const float Before = GetMaxHealth();
	++Level;
	Health += GetMaxHealth() - Before;   // the new walls come up whole
	NeedsBuilderState = -1;
	ApplyLevelLook(true);                // the new look goes up as the level is reached (any team: the enemy's too)
	UE_LOG(LogSovereign, Log, TEXT("UPGRADE %s reached level %d (houses %d, holds %d)"), *GetDisplayName(), Level, GetPopProvided(), GetStoreCapacity());
	if (Team == ESRTeam::Player && Economy)
	{
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::BuildComplete); }
		const FVector2D At = GetFootprintCentre();
		const FText Msg = IsCastle()
			? FText::Format(NSLOCTEXT("SRBuilding", "Upgraded", "{0} raised to level {1}: troops up to {2}"), FText::FromString(GetDisplayName()), FText::AsNumber(Level),
				FText::AsNumber(USRFeelSettings::Get().CastleLevel(Level).PopulationCeiling))
			: FText::Format(NSLOCTEXT("SRBuilding", "UpgradedOther", "{0} upgraded to level {1}"), FText::FromString(GetDisplayName()), FText::AsNumber(Level));
		Economy->PushAlert(ESRAlertKind::BuildingDone, Msg, &At);
	}
}

void ASRBuilding::SetLevelForLoad(int32 InLevel, float InUpgradeProgress)
{
	Level = FMath::Clamp(InLevel, 1, GetMaxLevel());
	UpgradeProgress = InUpgradeProgress;
	ApplyLevelLook(false);
}

void ASRBuilding::SetLevelNow(int32 InLevel)
{
	const float Before = GetMaxHealth();
	Level = FMath::Clamp(InLevel, 1, GetMaxLevel());
	UpgradeProgress = -1.f;
	if (!bDestroyed) { Health = FMath::Clamp(Health + GetMaxHealth() - Before, 1.f, GetMaxHealth()); }
	NeedsBuilderState = -1;
	ApplyLevelLook(true);
	UE_LOG(LogSovereign, Log, TEXT("LEVEL %s %s set to %d (mesh %s, label z %.0f)"), Team == ESRTeam::Player ? TEXT("player") : TEXT("enemy"), *GetDisplayName(), Level,
		Mesh && Mesh->GetStaticMesh() ? *Mesh->GetStaticMesh()->GetName() : TEXT("none"), LabelOffset.Z);
}

bool ASRBuilding::NeedsBuilder() const
{
	if (NeedsBuilderState < 0)
	{
		const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
		const_cast<ASRBuilding*>(this)->NeedsBuilderState = (Eco && !Eco->IsInBuildZone(Team, GetFootprintCentre())) ? 1 : 0;
	}
	return NeedsBuilderState > 0;
}

void ASRBuilding::CountBuilders()
{
	BuildersWorking = 0;
	if (!NeedsWork()) { return; }
	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		for (const ASRUnit* U : Battle->GetUnits())
		{
			if (U && U->GetTeam() == Team && U->IsWorkingOn(this)) { ++BuildersWorking; }
		}
	}
	BuildersWorking = FMath::Min(BuildersWorking, USRFeelSettings::Get().BuildersPerBuilding);
}

void ASRBuilding::PlayVoice()
{
	USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this);
	if (!Audio) { return; }
	ESRSound Voice = ESRSound::Select;
	switch (BuildingType)
	{
	case ESRBuildingType::Castle: Voice = ESRSound::BellCastle; break;
	case ESRBuildingType::Farm: Voice = ESRSound::Sheep; break;
	case ESRBuildingType::Mine: Voice = ESRSound::Mining; break;
	case ESRBuildingType::Tower: Voice = ESRSound::Creak; break;
	case ESRBuildingType::Barracks: Voice = ESRSound::BladeDraw; break;
	case ESRBuildingType::Range: Voice = ESRSound::TargetThunk; break;
	case ESRBuildingType::Stable: Voice = ESRSound::HorseNeigh; break;
	case ESRBuildingType::Workshop: Voice = ESRSound::Woodwork; break;
	case ESRBuildingType::Granary: Voice = ESRSound::GrainPayout; break;      // sacks thump down
	case ESRBuildingType::Treasury: Voice = ESRSound::CoinPayout; break;      // coins counted out
	}
	if (IsUnderConstruction()) { Voice = ESRSound::BuildHammer; }
	Audio->PlayAt(Voice, GetLabelPoint() * FVector(1, 1, 0) + FVector(0, 0, GetActorLocation().Z + 200.f));
}

void ASRBuilding::StepLife(float Dt)
{
	LifeClock -= Dt;
	if (LifeClock > 0.f) { return; }
	LifeClock = FMath::FRandRange(6.f, 15.f);
	if (State != ESRBuildingState::Complete || IsHidden()) { return; }   // a burning building has other sounds
	ESRSound Life = ESRSound::Count;
	switch (BuildingType)
	{
	case ESRBuildingType::Farm: Life = FMath::RandBool() ? ESRSound::Sheep : ESRSound::Birds; break;
	case ESRBuildingType::Tower: if (FMath::FRand() < 0.4f) { Life = ESRSound::Creak; } break;
	case ESRBuildingType::Barracks: Life = ESRSound::Anvil; break;
	case ESRBuildingType::Range: Life = ESRSound::TargetThunk; break;
	case ESRBuildingType::Stable: Life = ESRSound::HorseSnort; break;
	case ESRBuildingType::Workshop: Life = ESRSound::Woodwork; break;
	// the granary: sparrows after the spilt grain, a sack set down now and then; the treasury: the clerk at his counting
	case ESRBuildingType::Granary: Life = FMath::FRand() < 0.6f ? ESRSound::Birds : ESRSound::GrainPayout; break;
	case ESRBuildingType::Treasury: if (FMath::FRand() < 0.5f) { Life = ESRSound::CoinPayout; } break;
	default: break;   // the castle and the mine have their own life (archers on the walls, the miners' picks)
	}
	if (Life == ESRSound::Count) { return; }
	const FVector2D Yard = ToWorld2D(FVector2D(GateOffset.X, GateOffset.Y) * 0.6f);
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(Life, FVector(Yard, GetActorLocation().Z + 120.f), FMath::FRandRange(0.5f, 0.85f)); }
}

void ASRBuilding::StepFireSound(float Dt)
{
	USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this);
	if (!Audio) { return; }
	// (the sprite fire burns while the building shows its damaged model; the new one from the first flames' taking hold)
	if (bDestroyed || (UsesNewFire() ? GetFireStrength() < 0.3f : State != ESRBuildingState::Damaged)) { StopFireSound(1.2f); return; }
	const FVector Flames = GetLabelPoint() * FVector(1, 1, 0) + FVector(0, 0, GetActorLocation().Z + FMath::Min(BlockHeight * 0.7f, 450.f));
	UAudioComponent* F = FireSound.Get();
	if (!F)
	{
		// the roar starts (fading in) once the fire is in earshot; until then it is checked now and then
		FireRetry -= Dt;
		if (FireRetry <= 0.f)
		{
			FireRetry = 0.75f;
			FireSound = Audio->PlayAttached(ESRSound::FireLoop, Mesh, 1.f, FMath::FRandRange(0.92f, 1.08f), 1.5f);
			if (UAudioComponent* New = FireSound.Get()) { New->SetWorldLocation(Flames); }
		}
	}
	else if (!Audio->IsInRange(ESRSound::FireLoop, Flames, 1.15f))
	{
		StopFireSound(0.3f);   // well past the range, where it is already silent: give the voice back
	}
	CrackleClock -= Dt;
	if (CrackleClock <= 0.f)
	{
		CrackleClock = FMath::FRandRange(2.5f, 7.f);
		Audio->PlayAt(ESRSound::FireCrackle, Flames, FMath::FRandRange(0.6f, 1.f));
	}
}

void ASRBuilding::StopFireSound(float Fade)
{
	if (UAudioComponent* F = FireSound.Get()) { F->FadeOut(Fade, 0.f); }
	FireSound = nullptr;
}

void ASRBuilding::StepRepair(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const bool bWas = bRepairing;
	bRepairing = BuildersWorking > 0 && Health < GetMaxHealth() - 0.5f;
	if (bRepairing != bWas)
	{
		UE_LOG(LogSovereign, Log, TEXT("REPAIR %s %s"), *GetDisplayName(), bRepairing ? TEXT("started: out of action") : TEXT("ended: back in action"));
	}
	if (!bRepairing) { return; }
	Health = FMath::Min(GetMaxHealth(), Health + BuildersWorking * F.BuilderRepairPerSecond * Dt);
	if (State == ESRBuildingState::Damaged && GetHealthFrac() >= F.DamagedStateFraction) { SetState(ESRBuildingState::Complete); }
	// (the builders' own mallet blows are the sound of the repair)
}

float ASRBuilding::GetConstructionRate() const
{
	// Inside the castle's zone it rises by itself and builders speed it up; outside, only while a builder works on it.
	const USRFeelSettings& F = USRFeelSettings::Get();
	return NeedsBuilder()
		? (BuildersWorking > 0 ? 1.f + F.BuilderExtraSpeed * (BuildersWorking - 1) : 0.f)
		: 1.f + F.BuilderExtraSpeed * BuildersWorking;
}

float ASRBuilding::GetBuildSecondsLeft(bool* bOutWaiting) const
{
	if (bOutWaiting) { *bOutWaiting = false; }
	if (!IsUnderConstruction()) { return 0.f; }
	const float Work = (1.f - BuildProgress) * FMath::Max(Stats().BuildTime, 0.5f);
	const float Rate = GetConstructionRate();
	if (Rate <= 0.f)
	{
		if (bOutWaiting) { *bOutWaiting = true; }
		return Work;
	}
	return Work / Rate;
}

float ASRBuilding::GetUpgradeSecondsLeft() const
{
	if (!IsUpgrading()) { return 0.f; }
	const float Rate = 1.f + USRFeelSettings::Get().BuilderExtraSpeed * BuildersWorking;
	return (1.f - FMath::Clamp(UpgradeProgress, 0.f, 1.f)) * FMath::Max(GetUpgradeTime(), 1.f) / Rate;
}

void ASRBuilding::StepConstruction(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRBuildingStats& S = Stats();
	const float Rate = GetConstructionRate();
	if (Rate <= 0.f) { return; }   // waiting for a builder
	const float Before = BuildProgress;
	BuildProgress = FMath::Min(1.f, BuildProgress + Rate * Dt / FMath::Max(S.BuildTime, 0.5f));
	Health = FMath::Min(GetMaxHealth(), Health + GetMaxHealth() * (1.f - F.ConstructionStartHealth) * (BuildProgress - Before));
	ApplyBuildVisual();

	HammerClock -= Dt;
	if (HammerClock <= 0.f && BuildersWorking == 0)
	{
		HammerClock = FMath::FRandRange(0.45f, 0.8f);
		const bool bSaw = FMath::FRand() < 0.18f;   // a saw stroke now and then among the hammer blows
		if (bSaw) { HammerClock += 0.8f; }
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(bSaw ? ESRSound::Woodwork : ESRSound::BuildHammer, GetLabelPoint() * FVector(1, 1, 0) + FVector(0, 0, GetActorLocation().Z + 150.f)); }
	}

	if (BuildProgress >= 1.f)
	{
		Health = FMath::Max(Health, GetMaxHealth() * 0.999f);
		UE_LOG(LogSovereign, Log, TEXT("BUILD %s finished at (%.0f, %.0f)"), *GetDisplayName(), GetActorLocation().X, GetActorLocation().Y);
		if (Team == ESRTeam::Player)
		{
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::BuildComplete); }
		}
		SetState(ESRBuildingState::Complete);
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
	const int32 Archers = GetArcherCount();
	if (GetAttackRange() <= 0.f || GetAttackDamage() <= 0.f || Archers <= 0) { return; }
	DefenceCooldown -= Dt;
	if (DefenceCooldown > 0.f) { return; }

	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }
	const FVector2D C = GetFootprintCentre();
	ASRUnit* Best = nullptr;
	float BestD = FMath::Square(GetAttackRange());
	for (ASRUnit* U : Battle->GetUnits())
	{
		if (!U || !U->IsActive() || U->GetTeam() == Team) { continue; }
		const float D = FVector2D::DistSquared(U->GetPos2D(), C);
		if (S.MinRange > 0.f && D < FMath::Square(S.MinRange)) { continue; }   // (a stone-thrower cannot reach right under it)
		// the archers on the walls notice a Scout only at a fraction of their reach
		if (D < BestD && U->IsNoticedAt(D, GetAttackRange())) { BestD = D; Best = U; }
	}
	if (!Best) { DefenceCooldown = 0.25f; return; }

	DefenceCooldown = GetAttackInterval() * FMath::FRandRange(0.9f, 1.1f);
	// each archer on top looses one: the first at the nearest foe, the next at the next nearest in reach (or the same)
	TArray<ASRUnit*> Marks = { Best };
	if (Archers > 1)
	{
		TArray<TPair<float, ASRUnit*>> Rest;
		for (ASRUnit* U : Battle->GetUnits())
		{
			if (!U || U == Best || !U->IsActive() || U->GetTeam() == Team) { continue; }
			const float D = FVector2D::DistSquared(U->GetPos2D(), C);
			if (D < FMath::Square(GetAttackRange()) && U->IsNoticedAt(D, GetAttackRange())) { Rest.Add({ D, U }); }
		}
		Rest.Sort([](const TPair<float, ASRUnit*>& A, const TPair<float, ASRUnit*>& B) { return A.Key < B.Key; });
		for (int32 k = 1; k < Archers; ++k) { Marks.Add(Rest.IsValidIndex(k - 1) ? Rest[k - 1].Value : Best); }
	}
	// archers seen on top: each shot goes to a post, which draws and looses on its release frame (StepPosts)
	EnsurePosts();
	if (Posts.Num() > 0)
	{
		const bool bPillars = BuildingType == ESRBuildingType::Castle;
		const int32 Manned = FMath::Min(Archers, Posts.Num());
		TArray<int32> Used;
		for (int32 k = 0; k < Marks.Num(); ++k)
		{
			int32 Pick = -1;
			if (bPillars)
			{
				// the castle: the manned pillar nearest its mark
				float PickD = TNumericLimits<float>::Max();
				for (int32 p = 0; p < Manned; ++p)
				{
					if (Used.Contains(p)) { continue; }
					const float D = FVector2D::DistSquared(PostXY(p), Marks[k]->GetPos2D());
					if (D < PickD) { PickD = D; Pick = p; }
				}
			}
			if (Pick < 0) { Pick = k % Manned; }
			Used.Add(Pick);
			FPostArcher& P = Posts[Pick];
			P.Mark = Marks[k];
			P.Clock = 0.f;
			P.bLoosed = false;
			P.Yaw = SRYawOf(Marks[k]->GetPos2D() - PostXY(Pick));
		}
		return;
	}
	for (int32 k = 0; k < Marks.Num(); ++k)
	{
		const FVector2D Side = FVector2D(-(Marks[k]->GetPos2D() - C).GetSafeNormal().Y, (Marks[k]->GetPos2D() - C).GetSafeNormal().X) * (k == 0 ? -60.f : 60.f) * (Marks.Num() > 1 ? 1.f : 0.f);
		const float MuzzleZ = (k == 1 && S.SecondMuzzleHeight > 0.f) ? S.SecondMuzzleHeight : S.MuzzleHeight;
		const FVector Muzzle = FVector(C.X + Side.X, C.Y + Side.Y, GetActorLocation().Z + MuzzleZ) + FVector((Marks[k]->GetPos2D() - C).GetSafeNormal() * 120.f, 0.f);
		if (S.SplashRadius > 0.f)
		{
			// a stone: high and slow, it lands on the spot and hurts every foe round it
			ASRProjectile::LaunchArrow(GetWorld(), Team, nullptr, Marks[k], nullptr, Muzzle, GetAttackDamage(), 220.f, 1500.f, 0.35f, S.SplashRadius, true, 1.f);
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::Creak, Muzzle, 1.f, 0.6f); }
		}
		else { ASRProjectile::LaunchArrow(GetWorld(), Team, nullptr, Marks[k], nullptr, Muzzle, GetAttackDamage(), 60.f, 2200.f, 0.1f); }
	}
}

void ASRBuilding::ReceiveDamage(float Amount, ASRUnit* From)
{
	if (bDestroyed || Amount <= 0.f) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	Health = FMath::Max(0.f, Health - Amount);
	LastDamagedTime = GetWorld()->GetTimeSeconds();
	HitShake = 1.f;
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::BuildingHit, GetAimPointFrom(From ? From->GetPos2D() : GetFootprintCentre())); }
	// chips fly from the struck wall (not every blow: a crowd hacking at it would bury it in debris)
	if (GetWorld()->GetTimeSeconds() - LastDebrisTime > 0.35)
	{
		LastDebrisTime = GetWorld()->GetTimeSeconds();
		if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->SpawnFX(ESRFX::Debris, GetAimPointFrom(From ? From->GetPos2D() : GetFootprintCentre()), 0.9f); }
	}
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

	if (Health <= 0.f) { Collapse(From); return; }
	if (State == ESRBuildingState::Complete && IsFinished() && GetHealthFrac() < F.DamagedStateFraction) { SetState(ESRBuildingState::Damaged); }
}

void ASRBuilding::Collapse(ASRUnit* Killer, bool bDemolished)
{
	if (bDestroyed) { return; }
	StopFireSound(0.8f);
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

	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->PlayAt(ESRSound::BuildingCollapse, GetLabelPoint(), bDemolished ? 0.7f : 1.f); }
	// the pall: dust rolling out along the ground, smoke and sparks thrown up
	if (ASRBuildingFire* Fire = NeedFire(FireSeated ? FireSeated : 1))
	{
		const FVector2D C2 = GetFootprintCentre();
		Fire->Burst(FVector(C2.X, C2.Y, GetActorLocation().Z), (FootprintMax - FootprintMin) * 0.5f, BlockHeight);
	}
	if (bDemolished)
	{
		// pulled down by its own side: no alarm, no shake, not a loss; a storehouse's stock over the kingdom's
		// remaining capacity goes as when one falls
		if (Economy && IsStore()) { Economy->ClampToStorage(Team); }
		return;
	}
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
	if (State != ESRBuildingState::Ruin)
	{
		Mesh->SetRelativeLocation(MeshBaseLocation + FVector(FMath::FRandRange(-Shake, Shake), FMath::FRandRange(-Shake, Shake), -BlockHeight * 0.18f * E));
		Mesh->SetRelativeRotation(FRotator(0.f, 0.f, 3.5f * E));
		Mesh->SetRelativeScale3D(FVector(1.f + 0.04f * E, 1.f + 0.04f * E, FMath::Lerp(1.f, 0.28f, E)));   // slumps into a heap of rubble
		if (T >= 1.f) { SetState(ESRBuildingState::Ruin); }
	}
	else if (bRuntimeBuilt)
	{
		// a ruin of something raised during the match sinks away in its last few seconds
		const float Left = F.CollapseTime + F.RuinLingerTime - CollapseClock;
		if (Left < 3.f) { Mesh->SetRelativeLocation(MeshBaseLocation - FVector(0.f, 0.f, BlockHeight * 0.25f * (1.f - FMath::Max(Left, 0.f) / 3.f))); }
	}

	if (bRuntimeBuilt && CollapseClock > F.CollapseTime + F.RuinLingerTime)
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

// ------------------------------------------------------------------ states

void ASRBuilding::LoadStateMeshes()
{
	if (!BuildingMesh) { return; }
	const FString Pkg = BuildingMesh->GetOutermost()->GetName();
	const FString Name = BuildingMesh->GetName();
	auto Load = [&](const FString& Suffix) -> UStaticMesh*
	{
		const FString Path = FString::Printf(TEXT("%s_%s.%s_%s"), *Pkg, *Suffix, *Name, *Suffix);
		if (!FPackageName::DoesPackageExist(Pkg + TEXT("_") + Suffix)) { return nullptr; }
		return LoadObject<UStaticMesh>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
	};
	DamagedMeshAsset = Load(TEXT("Damaged"));
	RuinMeshAsset = Load(TEXT("Ruin"));
	// each level above the first has its own finished and damaged meshes (SM_Bld_<Name>_L<n>, _L<n>_Damaged)
	const int32 MaxLevel = GetMaxLevel();
	LevelMeshes.Init(nullptr, MaxLevel);
	LevelDamagedMeshes.Init(nullptr, MaxLevel);
	int32 Found = 0;
	for (int32 L = 2; L <= MaxLevel; ++L)
	{
		const FString Suffix = FString::Printf(TEXT("L%d"), L);
		LevelMeshes[L - 1] = Load(Suffix);
		LevelDamagedMeshes[L - 1] = Load(Suffix + TEXT("_Damaged"));
		Found += LevelMeshes[L - 1] ? 1 : 0;
	}
	if (MaxLevel > 1 && Found < MaxLevel - 1)
	{
		UE_LOG(LogSovereign, Warning, TEXT("%s: %d of %d level meshes found (%s_L2..L%d): the missing levels keep the look below"), *GetActorNameOrLabel(), Found, MaxLevel - 1, *Name, MaxLevel);
	}
	if (UStaticMesh* Site = Load(TEXT("Site")))
	{
		SiteMesh = NewObject<UStaticMeshComponent>(this, TEXT("SiteMesh"));
		SiteMesh->SetupAttachment(Root);
		SiteMesh->SetMobility(EComponentMobility::Movable);
		SiteMesh->SetCollisionProfileName(TEXT("NoCollision"));
		SiteMesh->SetGenerateOverlapEvents(false);
		SiteMesh->SetStaticMesh(Site);
		SiteMesh->SetRelativeLocation(Mesh->GetRelativeLocation());
		SiteMesh->RegisterComponent();
		const USRFeelSettings& F = USRFeelSettings::Get();
		const FLinearColor Color = Team == ESRTeam::Player ? F.PlayerTeamColor : F.EnemyTeamColor;
		SiteMesh->SetCustomPrimitiveDataVector4(0, FVector4(Color.R, Color.G, Color.B, 1.f));
		SiteMesh->SetVisibility(false);
	}
}

void ASRBuilding::SetState(ESRBuildingState NewState)
{
	State = NewState;
	UStaticMesh* Want = BuildingMesh;
	if (NewState == ESRBuildingState::Complete) { Want = GetLevelMesh(false); }
	if (NewState == ESRBuildingState::Damaged) { Want = GetLevelMesh(true); }
	if (NewState == ESRBuildingState::Ruin && RuinMeshAsset)
	{
		Want = RuinMeshAsset;
		// the ruin stands as modelled, not slumped
		Mesh->SetRelativeLocation(MeshBaseLocation);
		Mesh->SetRelativeRotation(FRotator::ZeroRotator);
		Mesh->SetRelativeScale3D(FVector::OneVector);
	}
	if (Want && Mesh->GetStaticMesh() != Want) { Mesh->SetStaticMesh(Want); }
	if (SiteMesh) { SiteMesh->SetVisibility(NewState == ESRBuildingState::Site); }
	// the HUD's bars ride above the roof: a taller level lifts them by as much as it grew
	LabelOffset = BaseLabelOffset;
	// never far over the level-1 model (a level placed before the model was rebuilt smaller keeps an old, higher socket)
	if (BuildingMesh) { LabelOffset.Z = FMath::Min(LabelOffset.Z, float(BuildingMesh->GetBoundingBox().Max.Z) + 120.f); }
	if (BuildingMesh && Want && Want != BuildingMesh && NewState != ESRBuildingState::Ruin)
	{
		LabelOffset.Z += FMath::Max(0.f, float(Want->GetBoundingBox().Max.Z - BuildingMesh->GetBoundingBox().Max.Z));
	}

	// Effects: a damaged building burns in a couple of places and smokes; a ruin smokes for a while.
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || !GetWorld() || !GetWorld()->IsGameWorld()) { return; }
	if (UsesNewFire())
	{
		// the fire itself (flames, smoke, light) follows the building's health: StepFire
		ClearStateFX(false);
		if (NewState == ESRBuildingState::Damaged)
		{
			CrackleClock = 0.f;   // it catches with a flare-up
			FireRetry = 0.f;
		}
		FireSeated = 0;           // the mesh changed: the flames find their places on the new one
		return;
	}
	// The sprite fire (kept for a build without the new fire's materials, or with it switched off): a damaged
	// building burns in a couple of places and smokes; a ruin smokes for a while.
	if (NewState == ESRBuildingState::Damaged)
	{
		ClearStateFX(false);
		CrackleClock = 0.f;   // it catches with a flare-up
		FireRetry = 0.f;
		const FVector2D H = (FootprintMax - FootprintMin) * 0.32f;
		const FVector2D C = GetFootprintCentre();
		const float Top = GetActorLocation().Z + FMath::Min(BlockHeight * 0.8f, 520.f);
		const FVector2D Spots[2] = { C + FVector2D(-H.X, H.Y), C + FVector2D(H.X * 0.6f, -H.Y) };
		for (const FVector2D& P : Spots)
		{
			if (ASRFXSprite* Fire = Battle->SpawnFX(ESRFX::Fire, FVector(P.X, P.Y, Top), 1.f)) { StateFX.Add(Fire); }
		}
		if (ASRFXSprite* Smoke = Battle->SpawnFX(ESRFX::Smoke, FVector(C.X, C.Y, Top + 220.f), 1.2f)) { StateFX.Add(Smoke); }
	}
	else if (NewState == ESRBuildingState::Ruin)
	{
		ClearStateFX(false);
		const FVector2D C = GetFootprintCentre();
		if (ASRFXSprite* Smoke = Battle->SpawnFX(ESRFX::Smoke, FVector(C.X, C.Y, GetActorLocation().Z + 180.f), 1.1f, 25.f)) { StateFX.Add(Smoke); }
	}
	else
	{
		ClearStateFX(false);
	}
}

UStaticMesh* ASRBuilding::GetLevelMesh(bool bDamaged) const
{
	const TArray<TObjectPtr<UStaticMesh>>& Meshes = bDamaged ? LevelDamagedMeshes : LevelMeshes;
	for (int32 L = FMath::Min(Level, Meshes.Num()); L >= 2; --L)
	{
		if (Meshes[L - 1]) { return Meshes[L - 1]; }
		// a level whose damaged mesh is missing still shows its own finished one rather than an older damaged one
		if (bDamaged && L == Level && LevelMeshes.IsValidIndex(L - 1) && LevelMeshes[L - 1]) { return LevelMeshes[L - 1]; }
	}
	return bDamaged && DamagedMeshAsset ? DamagedMeshAsset.Get() : BuildingMesh.Get();
}

void ASRBuilding::ApplyLevelLook(bool bFlourish)
{
	if (bDestroyed || BuildProgress < 1.f) { return; }
	SetState(State == ESRBuildingState::Damaged ? ESRBuildingState::Damaged : ESRBuildingState::Complete);
	if (!bFlourish) { return; }
	// the scaffolding comes down: dust off the corners and the roof, a little debris
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || !GetWorld() || !GetWorld()->IsGameWorld()) { return; }
	const FVector2D C = GetFootprintCentre();
	const FVector2D H = (FootprintMax - FootprintMin) * 0.5f;
	const float Z = GetActorLocation().Z;
	for (int32 i = 0; i < 4; ++i)
	{
		const FVector2D P = ToWorld2D((FootprintMin + FootprintMax) * 0.5f + FVector2D(i & 1 ? H.X : -H.X, i & 2 ? H.Y : -H.Y) * 0.85f);
		Battle->SpawnFX(ESRFX::Dust, FVector(P.X, P.Y, Z + 40.f), 2.2f);
	}
	Battle->SpawnFX(ESRFX::Dust, FVector(C.X, C.Y, GetLabelPoint().Z - 180.f), 2.6f);
	Battle->SpawnFX(ESRFX::Debris, FVector(C.X, C.Y, GetLabelPoint().Z - 260.f), 1.6f);
}

void ASRBuilding::ClearStateFX(bool bKeepSmoke)
{
	for (const TWeakObjectPtr<ASRFXSprite>& FX : StateFX) { if (FX.IsValid()) { FX->Stop(); } }
	StateFX.Reset();
}

void ASRBuilding::ApplySaved(float InHealth, float InProgress, bool bInDestroyed, const TArray<ESRUnitType>& InQueue, const FVector2D& InRally)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (bInDestroyed)
	{
		if (!bDestroyed)
		{
			if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this))
			{
				Grid->SetFootprint(this, false);
				if (BuildingType == ESRBuildingType::Mine) { Grid->ReleaseVein(this); }
			}
			bDestroyed = true;
			Blocker->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			for (ASRWorker* W : Workers) { if (W) { W->Destroy(); } }
			Workers.Reset();
			if (Ring) { Ring->SetVisibility(false); bRingVisible = false; }
			if (RallyFlag) { RallyFlag->SetVisibility(false); }
		}
		Health = 0.f;
		Queue.Reset();
		CollapseClock = F.CollapseTime;
		if (!RuinMeshAsset) { Mesh->SetRelativeScale3D(FVector(1.04f, 1.04f, 0.28f)); }
		SetState(ESRBuildingState::Ruin);
		return;
	}
	BuildProgress = FMath::Clamp(InProgress, 0.f, 1.f);
	NeedsBuilderState = -1;
	Health = FMath::Clamp(InHealth, 1.f, GetMaxHealth());
	Queue = InQueue;
	BuildClock = 0.f;
	RallyPoint = InRally;
	if (RallyFlag)
	{
		float Z = GetActorLocation().Z;
		if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this)) { Battle->SampleGround(RallyPoint, Z + 200.f, Z); }
		RallyFlag->SetWorldLocation(FVector(RallyPoint.X, RallyPoint.Y, Z));
	}
	SetState(BuildProgress < 1.f ? ESRBuildingState::Site : (GetHealthFrac() < F.DamagedStateFraction ? ESRBuildingState::Damaged : ESRBuildingState::Complete));
	ApplyBuildVisual();
	UpdateWorkers();
}

// ---------------------------------------------------------------------------------------------------- fire
float ASRBuilding::GetFireStrength() const
{
	if (bDestroyed || BuildProgress < 1.f) { return 0.f; }
	const float Start = USRFeelSettings::Get().FireStartFraction;
	const float H = GetHealthFrac();
	if (H >= Start) { return 0.f; }
	return FMath::Pow(FMath::Clamp((Start - H) / FMath::Max(Start - 0.1f, 0.05f), 0.f, 1.f), 0.8f);
}

bool ASRBuilding::UsesNewFire() const
{
	return USRFeelSettings::Get().bBuildingFire && ASRBuildingFire::CanDraw();
}

ASRBuildingFire* ASRBuilding::NeedFire(uint8 SeatKind)
{
	UWorld* World = GetWorld();
	if (!World || !World->IsGameWorld() || !UsesNewFire()) { return nullptr; }
	ASRBuildingFire* Fire = FireFX.Get();
	if (!Fire)
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Fire = World->SpawnActor<ASRBuildingFire>(GetActorLocation(), FRotator::ZeroRotator, P);
		FireFX = Fire;
		FireSeated = 0;
	}
	if (Fire && FireSeated != SeatKind)
	{
		const FVector2D C = GetFootprintCentre();
		// (the footprint is in the building's own frame: a turned building's half extent, seen from the world, is the larger one both ways)
		const FVector2D Half = (FootprintMax - FootprintMin) * 0.5f;
		const float Yaw = FMath::Abs(FMath::Fmod(GetActorRotation().Yaw, 180.f));
		const FVector2D HalfW = (Yaw > 1.f && FMath::Abs(Yaw - 180.f) > 1.f) ? FVector2D(Half.GetMax(), Half.GetMax()) : Half;
		Fire->Seat(Mesh, FVector(C.X, C.Y, GetActorLocation().Z), HalfW, BlockHeight, SeatKind == 3);
		FireSeated = SeatKind;
	}
	return Fire;
}

void ASRBuilding::StepFire(float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	// soot on the mesh itself: it blackens as the fire takes hold (quickly), clears as the building is made good (slowly);
	// a ruin stays black
	{
		const float Want = !UsesNewFire() ? 0.f : (bDestroyed ? 0.85f : FMath::Clamp(GetFireStrength() * 1.15f, 0.f, 1.f));
		Soot = FMath::FInterpConstantTo(Soot, Want, Dt, Want > Soot ? 0.35f : 0.12f);
		if (FMath::Abs(Soot - SootShown) > 0.01f)
		{
			SootShown = Soot;
			Mesh->SetCustomPrimitiveDataFloat(4, Soot);
		}
	}
	if (!UsesNewFire())
	{
		// switched off while something burned: put it out (the sprite fire is SetState's)
		if (ASRBuildingFire* Fire = FireFX.Get()) { Fire->Finish(); FireFX = nullptr; FireSeated = 0; }
		return;
	}
	if (bDestroyed)
	{
		// the ruin smoulders for a while, dying down
		if (State != ESRBuildingState::Ruin) { return; }
		const float Left = 1.f - (CollapseClock - F.CollapseTime) / FMath::Max(F.RuinSmoulderTime, 1.f);
		ASRBuildingFire* Fire = FireFX.Get();
		if (Left <= 0.f) { if (Fire) { Fire->Finish(); FireFX = nullptr; } return; }
		if (!Fire && CollapseClock > F.CollapseTime + 1.f) { return; }      // (a ruin loaded from a save: cold)
		if ((Fire = NeedFire(3)) != nullptr)
		{
			Fire->SetSmoulder(true);
			Fire->SetStrength(0.5f * Left);
		}
		return;
	}
	const float S = GetFireStrength();
	if (S <= 0.f)
	{
		if (ASRBuildingFire* Fire = FireFX.Get()) { Fire->SetStrength(0.f); }
		return;
	}
	if (ASRBuildingFire* Fire = NeedFire(State == ESRBuildingState::Damaged ? 2 : 1))
	{
		Fire->SetSmoulder(false);
		Fire->SetStrength(S);
	}
}

void ASRBuilding::DebugSetHealthFrac(float Frac)
{
	if (bDestroyed || BuildProgress < 1.f) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	Health = FMath::Clamp(GetMaxHealth() * Frac, 1.f, GetMaxHealth());
	const ESRBuildingState Want = GetHealthFrac() < F.DamagedStateFraction ? ESRBuildingState::Damaged : ESRBuildingState::Complete;
	if (Want != State) { SetState(Want); }
}

int32 ASRBuilding::DebugFireSeats() const
{
	return FireFX.IsValid() ? FireFX->NumLit() : 0;
}

// --- the archers on top -------------------------------------------------------------------------

bool ASRBuilding::HasPostArchers() const
{
	return BuildingType == ESRBuildingType::Castle || BuildingType == ESRBuildingType::Tower || BuildingType == ESRBuildingType::RelicTower;
}

void ASRBuilding::EnsurePosts()
{
	if (!HasPostArchers() || (Posts.Num() > 0 && PostsLevel == Level)) { return; }
	PostsLevel = Level;
	// where they stand, in the mesh's own cm (front toward -X; Tools/blender/bld_*.py): roofs and wall walks, by level
	TArray<FVector> Spots;
	if (BuildingType == ESRBuildingType::Tower)
	{
		static const float Floor[3] = { 860.f, 980.f, 1232.f };     // the fighting top (H - 40); level 3: the upper stage's roof
		Spots.Add(Level >= 3 ? FVector(-40.f, -30.f, Floor[2]) : FVector(0.f, 0.f, Floor[FMath::Clamp(Level, 1, 3) - 1]));
	}
	else if (BuildingType == ESRBuildingType::RelicTower)
	{
		Spots.Add(FVector(-92.f, 0.f, 1150.f));     // the fighting top, in front of the beacon pier
		Spots.Add(FVector(-162.f, 0.f, 400.f));     // the gallery walk, in front of the shaft
	}
	else if (BuildingType == ESRBuildingType::Castle)
	{
		// manned in this order as the castle grows (Sovereign Feel > Castle levels > Archers)
		if (Level <= 1) { Spots.Add(FVector(-371.f, -250.f, 190.f)); Spots.Add(FVector(-371.f, 250.f, 190.f)); }     // the yard wall
		else if (Level <= 3) { Spots.Add(FVector(-464.f, -120.f, 392.f)); Spots.Add(FVector(-464.f, 120.f, 392.f)); } // the gatehouse roof
		else
		{
			// the corner towers' roofs (h - 36); from level 5 the great keep stands in for the back-right one
			const int32 L = FMath::Clamp(Level, 4, 7);
			const float FrontH = L >= 7 ? 820.f : (L >= 6 ? 720.f : 596.f), BackH = L >= 7 ? 1040.f : (L >= 6 ? 900.f : 716.f);
			const float KeepH = L >= 7 ? 1660.f : (L >= 6 ? 1480.f : 1300.f);
			Spots.Add(FVector(-366.f, -512.f, FrontH - 36.f));
			Spots.Add(FVector(-366.f, 512.f, FrontH - 36.f));
			Spots.Add(FVector(360.f, -504.f, BackH - 36.f));
			Spots.Add(L >= 5 ? FVector(330.f, 470.f, KeepH - 36.f) : FVector(360.f, 504.f, BackH - 36.f));
		}
	}
	const int32 Old = Posts.Num();
	Posts.SetNum(Spots.Num());
	const FVector2D C = GetFootprintCentre();
	for (int32 i = 0; i < Spots.Num(); ++i)
	{
		FPostArcher& P = Posts[i];
		P.Offset = FVector2D(Spots[i].X, Spots[i].Y);
		P.FeetZ = Spots[i].Z;
		P.Applied = FVector4(-1.f, -1.f, -1.f, -1.f);
		if (i >= Old)
		{
			// at rest they look out over the walls (a centred one, out of the front)
			const FVector2D Out = P.Offset.IsNearlyZero(1.f) ? FVector2D(-100.f, 0.f) : P.Offset;
			P.Yaw = SRYawOf(ToWorld2D((FootprintMin + FootprintMax) * 0.5f + Out) - C);
			P.IdlePhase = FMath::FRandRange(0.f, 3.f);
		}
	}
}

FVector2D ASRBuilding::PostXY(int32 i) const
{
	return ToWorld2D((FootprintMin + FootprintMax) * 0.5f + Posts[i].Offset);
}

FVector ASRBuilding::PostFeet(int32 i) const
{
	const FVector2D P = PostXY(i);
	return FVector(P.X, P.Y, GetActorLocation().Z + Posts[i].FeetZ + USRFeelSettings::Get().PostArcherFeetLift);
}

void ASRBuilding::StepPosts(float Dt)
{
	if (!HasPostArchers()) { return; }
	EnsurePosts();
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || !GetWorld() || !GetWorld()->IsGameWorld()) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRUnitStats& AS = F.StatsFor(ESRUnitType::Archer);
	const FSRSpriteSheet& Sheet = FSRSpriteSheet::For(ESRUnitType::Archer);
	const FSRSpriteView& View = Battle->GetSpriteView();
	const float Windup = FMath::Max(AS.WindupTime, 0.05f), Recovery = FMath::Max(AS.RecoveryTime, 0.05f);
	const bool bWorking = IsFinished() && !bRepairing && State != ESRBuildingState::Ruin;
	const int32 Manned = bWorking ? FMath::Min(GetArcherCount(), Posts.Num()) : 0;
	const bool bOnScreen = FVector2D::DistSquared(GetFootprintCentre(), View.FocusXY) < FMath::Square(View.CullRadius + 1500.f);

	// the cards, made the first time they are needed
	if (F.bPostArchers && Battle->UnitCardMesh && PostCards.Num() < Posts.Num())
	{
		UMaterialInterface* Mat = Battle->GetSpriteMaterial(ESRUnitType::Archer);
		const FLinearColor TeamCol = Battle->TeamColor(Team);
		while (PostCards.Num() < Posts.Num())
		{
			UStaticMeshComponent* Card = NewObject<UStaticMeshComponent>(this);
			Card->SetMobility(EComponentMobility::Movable);
			Card->SetStaticMesh(Battle->UnitCardMesh);
			Card->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Card->SetGenerateOverlapEvents(false);
			Card->SetCanEverAffectNavigation(false);
			Card->bReceivesDecals = false;
			Card->bAffectDynamicIndirectLighting = false;
			Card->bAffectDistanceFieldLighting = false;
			Card->bVisibleInRayTracing = false;
			Card->SetCastShadow(false);
			Card->SetBoundsScale(2.f);
			Card->SetUsingAbsoluteRotation(true);
			Card->SetUsingAbsoluteScale(true);
			Card->SetupAttachment(Root);
			Card->RegisterComponent();
			Card->SetMaterial(0, Mat);
			Card->SetCustomPrimitiveDataVector4(SRSprite::DataTeamColor, FVector4(TeamCol.R, TeamCol.G, TeamCol.B, 1.f));
			Card->SetVisibility(false);
			PostCards.Add(Card);
		}
	}

	for (int32 i = 0; i < Posts.Num(); ++i)
	{
		FPostArcher& P = Posts[i];
		const bool bManned = i < Manned;
		if (!bManned) { P.Clock = -1.f; P.bLoosed = true; P.Mark = nullptr; }
		// the shot: the arrow leaves on the release frame, at the end of the draw
		if (P.Clock >= 0.f)
		{
			P.Clock += Dt;
			ASRUnit* Mark = P.Mark.Get();
			if (Mark && Mark->IsActive()) { P.Yaw = SRYawOf(Mark->GetPos2D() - PostXY(i)); }
			if (!P.bLoosed && P.Clock >= Windup)
			{
				P.bLoosed = true;
				if (Mark && Mark->IsActive())
				{
					const FVector2D Dir = FVector2D(FMath::Cos(FMath::DegreesToRadians(P.Yaw)), FMath::Sin(FMath::DegreesToRadians(P.Yaw)));
					const FVector Muzzle = PostFeet(i) + FVector(Dir * 60.f, 100.f);
					ASRProjectile::LaunchArrow(GetWorld(), Team, nullptr, Mark, nullptr, Muzzle, GetAttackDamage(), 60.f, 2200.f, 0.1f);
				}
			}
			if (P.Clock >= Windup + Recovery) { P.Clock = -1.f; P.Mark = nullptr; }
		}
		P.IdlePhase += Dt;

		if (!PostCards.IsValidIndex(i) || !PostCards[i]) { continue; }
		UStaticMeshComponent* Card = PostCards[i];
		const bool bShow = F.bPostArchers && bManned && bOnScreen && Mesh && Mesh->IsVisible();
		if (Card->IsVisible() != bShow) { Card->SetVisibility(bShow); P.Applied = FVector4(-1.f, -1.f, -1.f, -1.f); }
		if (!bShow) { continue; }

		ESRSpriteAnim Anim = ESRSpriteAnim::Idle;
		int32 Frame = 0;
		if (P.Clock >= 0.f)
		{
			Anim = ESRSpriteAnim::Attack;
			Frame = P.Clock < Windup ? Sheet.AttackFrame(ESRAttackPhase::Windup, P.Clock / Windup)
				: Sheet.AttackFrame(ESRAttackPhase::Recovery, FMath::Clamp((P.Clock - Windup) / Recovery, 0.f, 1.f));
		}
		else { Frame = FMath::FloorToInt(P.IdlePhase * F.IdleFps) % FMath::Max(1, Sheet.Anim(ESRSpriteAnim::Idle).Frames); }
		const FSRSpriteSheet::FAnim& Block = Sheet.Anim(Anim);
		Frame = FMath::Clamp(Frame, 0, Block.Frames - 1);
		P.Facing = SRSprite::FacingIndexSticky(P.Facing, P.Yaw, View.ViewYaw, 8.f);
		const FVector4 Data(float(Block.Col + Frame), float(Block.Row + P.Facing), 0.f, 1.f);
		if (!Data.Equals(P.Applied, 0.001f)) { P.Applied = Data; Card->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, Data); }
		Card->SetWorldLocation(PostFeet(i));
		Card->SetWorldRotation(View.CardRotation);
		const float K = Sheet.CardScale * F.PostArcherScale;
		Card->SetRelativeScale3D(FVector(1.f, K, K));
	}
}
