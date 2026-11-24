// Building: the main game's construction (Source/SovereignRealms/Buildings/SRBuilding.cpp: SpawnBuilding,
// StepConstruction, ApplyBuildVisual, StepRepair, CancelConstruction, Demolish; SRPlacementPreview.cpp; SRWorker's
// builders in SRUnit.cpp: OrderBuild, StepBuild, LookForWork; SREconomySubsystem::PlaceBuilding and the limits), on
// this game's tagged buildings (UVLBattle) and path grid (UVLGrid). See VLConstruction.h.

#include "VLConstruction.h"
#include "VLFarmer.h"
#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLEnemyAI.h"
#include "VLKing.h"
#include "VLCommand.h"
#include "VLGrid.h"
#include "VLForest.h"
#include "VLHUD.h"
#include "VLGameMode.h"
#include "VLSwordsmanCombat.h"
#include "VLArcherCombat.h"
#include "Components/CapsuleComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/PointLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Camera/PlayerCameraManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

namespace
{
	// Placing: the ghost keeps what the ground said under each place it has stood (it does not trace again standing
	// still), trees are counted from a list of the trunks, and a building laid among trees has the path grid sampled
	// again once for the trunks' ground and its own. 0: as it was (every check traces, the dry run of the clearing, two
	// samplings), to compare.
	TAutoConsoleVariable<int32> CVarOptPlacement(TEXT("vl.Opt.Placement"), 1, TEXT("1: the placement ghost reuses its ground samples, trees are counted from a list, one grid sampling per building laid. 0: as before"));
	TAutoConsoleVariable<int32> CVarPlacementLog(TEXT("vl.PlacementLog"), 0, TEXT("1: log how long each check of the placement ghost took"));

	struct FVLPropSpec
	{
		const TCHAR* Owner;
		const TCHAR* Mesh;
		float X, Y, Z, Yaw, Scale;
	};
	struct FVLDoorSpec
	{
		const TCHAR* Owner;
		float X, Y, Z;
	};
#include "VLBuildingProps.inl"

	/** The yard of a training building, where its recruits wait in ranks: a rectangle in the mesh's own space (cm,
	 *  Unreal axes, the front +Y), from the Blender scripts. The barracks (Tools/blender/assets/barracks_yard.py):
	 *  the fenced dirt yard in front of the hall, its west half (the three training dummies stand in the east half).
	 *  The archery range (archery_hall.py): the dirt yard inside the rail fence, in front of the shooting hall. */
	struct FVLYardSpec
	{
		const TCHAR* Mesh;
		float X0, Y0, X1, Y1;
	};
	const FVLYardSpec Yards[] = {
		{ TEXT("SM_BarracksYard"), -800.f, 80.f, 150.f, 740.f },
		{ TEXT("SM_ArcheryHall"), -800.f, -60.f, 800.f, 520.f },
	};
	constexpr float RankSpacing = 125.f;        // across a rank (two capsule radii and a gap, as a formation's)
	constexpr float RankDepth = 130.f;          // from one rank to the next

	/** The lookout of a watch tower raised in the match (SM_WatchTower.json "lookout", the level builder's tag). */
	const TCHAR* TowerLookout = TEXT("Lookout:10.500;-3.000;-3.000;3.000;3.000");

	FString TagValue(const AActor* A, const TCHAR* Prefix)
	{
		if (!A)
		{
			return FString();
		}
		const int32 Len = FCString::Strlen(Prefix);
		for (const FName& Tag : A->Tags)
		{
			const FString S = Tag.ToString();
			if (S.StartsWith(Prefix))
			{
				return S.Mid(Len);
			}
		}
		return FString();
	}

	void SetTeamTag(AActor* A, int32 Team)
	{
		A->Tags.RemoveAll([](const FName& T) { return T.ToString().StartsWith(TEXT("Team:")); });
		A->Tags.Add(*(Team < 0 ? FString(TEXT("Team:Neutral")) : FString::Printf(TEXT("Team:%d"), Team)));
	}

	/** The level's ground (what the path grid stands on): tagged Ground, or the terrain meshes of the older maps. */
	bool IsGround(const AActor* A)
	{
		if (!A)
		{
			return false;
		}
		if (A->ActorHasTag(TEXT("Ground")))
		{
			return true;
		}
		const AStaticMeshActor* SMA = Cast<AStaticMeshActor>(A);
		const UStaticMesh* M = SMA && SMA->GetStaticMeshComponent() ? SMA->GetStaticMeshComponent()->GetStaticMesh() : nullptr;
		const FString Name = M ? M->GetName() : FString();
		return Name.StartsWith(TEXT("SM_Terrain")) || Name.StartsWith(TEXT("SM_Flat_")) || Name.StartsWith(TEXT("SM_TownGround")) || Name.StartsWith(TEXT("SM_RealmGround"));
	}

	UStaticMeshComponent* MeshOf(const AActor* A)
	{
		const AStaticMeshActor* SMA = Cast<AStaticMeshActor>(A);
		return SMA ? SMA->GetStaticMeshComponent() : (A ? A->FindComponentByClass<UStaticMeshComponent>() : nullptr);
	}

	/** A building's box on the ground: its middle, its half size along its own axes, and its yaw. */
	bool BoxOf(const AActor* A, FVector2D& OutCentre, FVector2D& OutHalf, float& OutYaw, float Grow = 0.f)
	{
		const UStaticMeshComponent* C = MeshOf(A);
		if (!C || !C->GetStaticMesh())
		{
			return false;
		}
		const FBox L = C->GetStaticMesh()->GetBoundingBox();
		const FTransform& T = C->GetComponentTransform();
		OutCentre = FVector2D(T.TransformPosition(L.GetCenter()));
		OutHalf = FVector2D(L.GetExtent() * T.GetScale3D().GetAbs()) + FVector2D(Grow, Grow);
		OutYaw = T.Rotator().Yaw;
		return true;
	}

	/** Do two turned rectangles on the ground overlap (separating axes)? */
	bool Overlap(const FVector2D& CA, const FVector2D& HA, float YawA, const FVector2D& CB, const FVector2D& HB, float YawB)
	{
		const float a = FMath::DegreesToRadians(YawA), b = FMath::DegreesToRadians(YawB);
		const FVector2D Ax[4] = { { FMath::Cos(a), FMath::Sin(a) }, { -FMath::Sin(a), FMath::Cos(a) }, { FMath::Cos(b), FMath::Sin(b) }, { -FMath::Sin(b), FMath::Cos(b) } };
		const FVector2D D = CB - CA;
		for (const FVector2D& N : Ax)
		{
			const float RA = HA.X * FMath::Abs(FVector2D::DotProduct(Ax[0], N)) + HA.Y * FMath::Abs(FVector2D::DotProduct(Ax[1], N));
			const float RB = HB.X * FMath::Abs(FVector2D::DotProduct(Ax[2], N)) + HB.Y * FMath::Abs(FVector2D::DotProduct(Ax[3], N));
			if (FMath::Abs(FVector2D::DotProduct(D, N)) > RA + RB)
			{
				return false;
			}
		}
		return true;
	}

	bool Inside(const FVector2D& P, const FVector2D& C, const FVector2D& H, float Yaw)
	{
		const FVector2D L = (P - C).GetRotated(-Yaw);
		return FMath::Abs(L.X) <= H.X && FMath::Abs(L.Y) <= H.Y;
	}

	bool InPlayersHands(const AVLKing* U)
	{
		return U && Cast<APlayerController>(U->GetController()) && U->IsHeroMode();
	}

	bool Fighting(AVLKing* U)
	{
		const UVLSwordsmanCombat* S = UVLSwordsmanCombat::For(U, false);
		const UVLArcherCombat* A = UVLArcherCombat::For(U, false);
		return (S && S->IsAttacking()) || (A && A->IsAttacking());
	}

	/** Does the building need a Builder (a site, or below its full health)? */
	bool NeedsWork(const FVLBuildingState& S)
	{
		return S.IsAlive() && (S.IsSite() || S.Health < S.MaxHealth - 0.5f || S.NeedsCornerWork());     // (a castle's corners, paid to be mended)
	}

	void ApplyTeamLook(UStaticMeshComponent* C, int32 Team)
	{
		// the enemy's cloth is red (MI_Vox_cloth_Enemy, as the level builder gives its buildings)
		UStaticMesh* M = C ? C->GetStaticMesh() : nullptr;
		if (!M)
		{
			return;
		}
		UMaterialInterface* Red = Team == UVLBattle::Enemy ? LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Voxel/Materials/MI_Vox_cloth_Enemy.MI_Vox_cloth_Enemy"), nullptr, LOAD_NoWarn | LOAD_Quiet) : nullptr;
		const TArray<FName> Slots = C->GetMaterialSlotNames();
		for (int32 i = 0; i < Slots.Num(); ++i)
		{
			const bool bCloth = Slots[i].ToString().Contains(TEXT("cloth"));
			C->SetMaterial(i, bCloth && Red ? Red : M->GetMaterial(i));
		}
	}

	FString CostText(const FVLCost& C)
	{
		return C.Food > 0 ? FString::Printf(TEXT("%d gold and %d food"), C.Gold, C.Food) : FString::Printf(TEXT("%d gold"), C.Gold);
	}
}

// ------------------------------------------------------------------------------------------------ the rules

namespace VLBuild
{
	const TArray<FSpec>& Specs()
	{
		// the main game's FSRBuildingStats: price (gold), build time with one Builder (Treasury: TreasuryStats,
		// 140 gold, 16 s; Granary: GranaryStats, 120 gold, 14 s). The town hall was never built in the main game.
		// The times are twice the main game's (the owner's call, 2026-11-22: everything takes twice as long), the watch
		// tower's three times (54 s: "archer towers need a lot longer to build").
		static const TArray<FSpec> S = [] {
			TArray<FSpec> L;
			auto Add = [&L](EVLBuilding K, const TCHAR* Mesh, int32 Gold, float Sec, int32 InTab, const TCHAR* Blurb)
			{
				FSpec X;
				X.Kind = K; X.Mesh = Mesh; X.Cost.Gold = Gold; X.Seconds = Sec; X.Tab = InTab; X.Blurb = Blurb;
				L.Add(X);
			};
			Add(EVLBuilding::Farm, TEXT("SM_Farmstead"), 90, 28.f, 0, TEXT("Grows food for troops and houses them."));
			Add(EVLBuilding::Treasury, TEXT("SM_Treasury"), 140, 32.f, 0, TEXT("Holds gold on top of the castle's stores."));
			Add(EVLBuilding::Granary, TEXT("SM_Granary"), 120, 28.f, 0, TEXT("Holds food on top of the castle's stores, so no harvest is lost."));
			// (not in the menu, Tab -1: a mine is never built. A free one of the map is claimed, at this price and in this
			// time: UVLConstruction::ClaimMine)
			Add(EVLBuilding::Mine, TEXT("SM_MineCliff"), 140, 32.f, -1, TEXT("Digs gold. Claimed, not built: order Builders onto a free mine."));
			Add(EVLBuilding::Barracks, TEXT("SM_BarracksYard"), 110, 32.f, 1, TEXT("Trains swordsmen. They wait in its yard."));
			Add(EVLBuilding::Range, TEXT("SM_ArcheryHall"), 125, 32.f, 1, TEXT("Trains archers. They wait in its yard."));
			Add(EVLBuilding::Tower, TEXT("SM_WatchTower"), 160, 54.f, 2, TEXT("Shoots at foes in reach; archers can man its lookout."));
			return L;
		}();
		return S;
	}

	const FSpec* Spec(EVLBuilding Kind)
	{
		return Specs().FindByPredicate([Kind](const FSpec& S) { return S.Kind == Kind; });
	}

	void TabEntries(int32 InTab, TArray<const FSpec*>& Out)
	{
		Out.Reset();
		for (const FSpec& S : Specs())
		{
			if (S.Tab == InTab)
			{
				Out.Add(&S);
			}
		}
	}

	const TCHAR* TabName(int32 InTab)
	{
		return InTab == 0 ? TEXT("Economy") : (InTab == 1 ? TEXT("Military") : TEXT("Defence"));
	}

	int32 MaxBuilders(int32 CastleLevel)
	{
		static const int32 ByLevel[7] = { 2, 3, 3, 4, 4, 5, 6 };
		return ByLevel[FMath::Clamp(CastleLevel, 1, 7) - 1];
	}
}

// ------------------------------------------------------------------------------------------------ a Builder at work

UVLBuilderWork::UVLBuilderWork()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;
}

bool UVLBuilderWork::IsBuilder(const AVLKing* Unit)
{
	return Unit && Unit->IsTroop() && Unit->GetKind() == TEXT("Builder");
}

UVLBuilderWork* UVLBuilderWork::For(AVLKing* Unit, bool bCreate)
{
	if (!Unit)
	{
		return nullptr;
	}
	if (!IsBuilder(Unit))
	{
		return nullptr;         // (only a Builder ever has one: no search through a fighter's parts)
	}
	UVLBuilderWork* W = Unit->FindComponentByClass<UVLBuilderWork>();
	if (!W && bCreate)
	{
		W = NewObject<UVLBuilderWork>(Unit, TEXT("BuilderWork"));
		W->RegisterComponent();
	}
	return W;
}

bool UVLBuilderWork::IsAtWork(const AVLKing* Unit)
{
	const UVLBuilderWork* W = IsBuilder(Unit) ? Unit->FindComponentByClass<UVLBuilderWork>() : nullptr;
	return W && W->IsWorking();
}

void UVLBuilderWork::Begin(AActor* Building, bool bInOrdered)
{
	AVLKing* Unit = Cast<AVLKing>(GetOwner());
	if (!Unit || !Building)
	{
		return;
	}
	if (Job.Get() != Building)
	{
		bWorking = false;
	}
	Job = Building;
	bOrdered = bInOrdered;
	Walks = 0;
	Stuck = 0.f;
	SetComponentTickEnabled(true);
	if (UVLBattle* Battle = UVLBattle::Get(this); Battle && Battle->DistanceTo(Building, Unit->GetFeet()) > VLBuild::Reach)
	{
		bWorking = false;
		WalkToWork(Unit);
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("%s goes to work on %s%s"), *Unit->GetDisplayName(), *GetNameSafe(Building), bOrdered ? TEXT(" (ordered)") : TEXT(""));
}

void UVLBuilderWork::Stop()
{
	Job = nullptr;
	bWorking = false;
	HammerAt = -1.f;
	SetComponentTickEnabled(Tasks.Num() > 0);      // (a queue: its next order starts in the next tick)
}

void UVLBuilderWork::QueueTask(const FTask& Task)
{
	Tasks.Add(Task);
	SetComponentTickEnabled(true);
}

bool UVLBuilderWork::StartNextTask(AVLKing* Unit)
{
	if (Unit->IsOnOrder())
	{
		return true;                // a walk under way (one of the queue's, or before it): the next once it is over
	}
	UVLBattle* Battle = UVLBattle::Get(this);
	while (Tasks.Num() > 0 && Battle)
	{
		const FTask T = Tasks[0];
		Tasks.RemoveAt(0);
		if (T.bMove)
		{
			TArray<FVector> Path;
			UVLGrid* Grid = UVLGrid::Get(this);
			if (!Grid || !Grid->EnsureBuilt() || !Grid->FindPath(Unit->GetFeet(), T.Point, Path) || Path.Num() == 0)
			{
				Path = { T.Point };
			}
			Unit->FollowPath(Path, T.bRun);
			return true;
		}
		AActor* B = T.Building.Get();
		const FVLBuildingState* S = B ? Battle->FindBuilding(B) : nullptr;
		if (S && S->Team == Unit->Team && NeedsWork(*S))
		{
			Begin(B, true);
			return true;
		}
		// (lapsed: the site was cancelled or fell, the building is whole again, ...)
		UE_LOG(LogSovereignRealms, Log, TEXT("%s passes over a queued order on %s: nothing to do there now"), *Unit->GetDisplayName(), *GetNameSafe(B));
	}
	return false;
}

void UVLBuilderWork::WalkToWork(AVLKing* Unit)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLGrid* Grid = UVLGrid::Get(this);
	AActor* B = Job.Get();
	if (!Battle || !B)
	{
		return;
	}
	// the point of its walls nearest the Builder, a step out from them; a crew spreads along the wall (each its own
	// offset, by its number) so that they stand side by side, not on top of each other
	FVector Wall;
	Battle->DistanceTo(B, Unit->GetFeet(), &Wall);
	FVector Out = (Unit->GetFeet() - Wall).GetSafeNormal2D();
	if (Out.IsNearlyZero())
	{
		Out = (Wall - B->GetActorLocation()).GetSafeNormal2D();
	}
	const FVector Along(-Out.Y, Out.X, 0.f);
	const int32 Slot = int32(GetTypeHash(Unit->GetDisplayName()) % 5) - 2;
	FVector Goal = Wall + Out * 90.f + Along * (Slot * 110.f);
	TArray<FVector> Path;
	if (!Grid || !Grid->EnsureBuilt() || !Grid->FindPath(Unit->GetFeet(), Goal, Path) || Path.Num() == 0)
	{
		Path = { Goal };
	}
	Unit->FollowPath(Path, false);
	++Walks;
}

void UVLBuilderWork::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	AVLKing* Unit = Cast<AVLKing>(GetOwner());
	AActor* B = Job.Get();
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!Unit || Unit->IsDead() || !Battle || InPlayersHands(Unit))
	{
		ClearTasks();
		Stop();
		return;
	}
	if (!B)
	{
		// between jobs: the next order of its queue
		if (!StartNextTask(Unit))
		{
			Stop();
		}
		return;
	}
	const FVLBuildingState* S = Battle->FindBuilding(B);
	if (!S || S->Team != Unit->Team || !NeedsWork(*S))
	{
		// done (or gone): it stands where it is and looks for the next job straight away
		if (S && S->IsAlive() && bWorking)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("%s is done with %s"), *Unit->GetDisplayName(), *S->Name);
		}
		Stop();
		JobSearch = 0.f;
		return;
	}
	if (Unit->HasOrder())
	{
		bWorking = false;
		return;                     // on the way
	}
	const float Dist = Battle->DistanceTo(B, Unit->GetFeet());
	if (Dist > VLBuild::Reach)
	{
		bWorking = false;
		if (Walks >= 4)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("%s cannot get to %s (%.0f cm away): gives up"), *Unit->GetDisplayName(), *S->Name, Dist);
			Stop();
			JobSearch = 4.f;
			return;
		}
		WalkToWork(Unit);
		return;
	}
	if (!bWorking)
	{
		bWorking = true;
		NextSwing = FMath::FRandRange(0.1f, 0.9f);          // each on its own beat
	}
	// it faces the wall and swings: the up-down-up blows of the sword's combo are the hammer's
	FVector Wall;
	Battle->DistanceTo(B, Unit->GetFeet(), &Wall);
	FVector To = Dist > 1.f ? Wall - Unit->GetActorLocation() : B->GetActorLocation() - Unit->GetActorLocation();
	To.Z = 0.f;
	const float WantYaw = To.IsNearlyZero() ? Unit->GetActorRotation().Yaw : To.Rotation().Yaw;
	if (!Unit->GetCharacterMovement()->IsFalling())
	{
		Unit->SetActorRotation(FRotator(0.f, FMath::FixedTurn(Unit->GetActorRotation().Yaw, WantYaw, 540.f * DeltaTime), 0.f));
	}
	NextSwing -= DeltaTime;
	if (NextSwing <= 0.f && FMath::Abs(FMath::FindDeltaAngleDegrees(Unit->GetActorRotation().Yaw, WantYaw)) < 25.f)
	{
		NextSwing = 1.15f * (1.f + FMath::FRandRange(-0.12f, 0.12f));
		Unit->Attack(2);
		HammerAt = 0.3f;
	}
	if (HammerAt >= 0.f)
	{
		HammerAt -= DeltaTime;
		if (HammerAt < 0.f)
		{
			// the blow lands: a hammer strike, now and then a saw stroke (the main game's recorded ones)
			const FVector At = Unit->GetActorLocation() + Unit->GetActorForwardVector() * 60.f;
			Battle->PlayAt(FMath::FRand() < 0.15f ? TEXT("S_Woodwork") : TEXT("S_BuildHammer"), At, 0.34f, 4500.f, 0.06f);
		}
	}
}

// ------------------------------------------------------------------------------------------------ the subsystem

UVLConstruction* UVLConstruction::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLConstruction>() : nullptr;
}

bool UVLConstruction::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UVLConstruction::Deinitialize()
{
	Ghost = nullptr;
	Rising.Reset();
	PlaceMemos.Reset();
	YardMemos.Reset();
	AtWorkScratch.Reset();
	Super::Deinitialize();
}

UStaticMesh* UVLConstruction::LoadMesh(const FString& Name)
{
	return Name.IsEmpty() ? nullptr : LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/Voxel/Meshes/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
}

FString UVLConstruction::MeshFor(EVLBuilding Kind, int32 Team, bool bAdvance)
{
	const VLBuild::FSpec* S = VLBuild::Spec(Kind);
	if (!S)
	{
		return FString();
	}
	if (Kind != EVLBuilding::Farm)
	{
		return S->Mesh;
	}
	// the three farmsteads (same footprint and gate), taken in turn so that neighbours differ; the first of a match at random
	TArray<FString> Variants;
	for (const TCHAR* V : { TEXT("SM_Farmstead_A"), TEXT("SM_Farmstead_B"), TEXT("SM_Farmstead_C") })
	{
		if (LoadMesh(V))
		{
			Variants.Add(V);
		}
	}
	if (Variants.Num() == 0)
	{
		return S->Mesh;             // (not imported yet: the one farmstead)
	}
	int32& Next = FarmVariant[FMath::Clamp(Team, 0, 1)];
	if (Next < 0)
	{
		Next = FMath::RandRange(0, Variants.Num() - 1);
	}
	const FString Pick = Variants[Next % Variants.Num()];
	if (bAdvance)
	{
		Next = (Next + 1) % Variants.Num();
	}
	return Pick;
}

int32 UVLConstruction::CountRaised(EVLBuilding Kind, int32 Team) const
{
	int32 N = 0;
	if (const UVLBattle* Battle = UVLBattle::Get(this))
	{
		for (const FVLBuildingState& B : Battle->GetBuildings())
		{
			N += (B.Kind == Kind && B.Team == Team && B.IsAlive() && B.bRuntime) ? 1 : 0;
		}
	}
	return N;
}

int32 UVLConstruction::BuildLimit(EVLBuilding Kind, int32 Team) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const int32 Up = Battle ? FMath::Max(0, Battle->GetCastleLevel(Team) - 1) : 0;
	switch (Kind)
	{
	case EVLBuilding::Farm: return VLBuild::FarmLimitBase + VLBuild::FarmLimitPerLevel * Up;
	case EVLBuilding::Tower: return VLBuild::TowerLimitBase + VLBuild::TowerLimitPerLevel * Up;
	// the storehouses: one of each per kingdom, as in the main game (raise it a level to hold more)
	case EVLBuilding::Granary:
	case EVLBuilding::Treasury: return 1;
	default: return INDEX_NONE;
	}
}

void UVLConstruction::GetBuilders(int32 Team, TArray<AVLKing*>& Out) const
{
	Out.Reset();
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		if (It->IsAlive() && It->Team == Team && UVLBuilderWork::IsBuilder(*It))
		{
			Out.Add(*It);
		}
	}
}

int32 UVLConstruction::CountBuilders(int32 Team, int32* OutQueued) const
{
	TArray<AVLKing*> Builders;
	GetBuilders(Team, Builders);
	if (OutQueued)
	{
		*OutQueued = 0;
		if (const UVLBattle* Battle = UVLBattle::Get(this))
		{
			for (const FVLBuildingState& B : Battle->GetBuildings())
			{
				if (B.Team == Team && B.IsAlive())
				{
					*OutQueued += B.Queue.FilterByPredicate([](const FString& K) { return K == TEXT("Builder"); }).Num();
				}
			}
		}
	}
	return Builders.Num();
}

FString UVLConstruction::BuildRefusal(EVLBuilding Kind, int32 Team) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const VLBuild::FSpec* S = VLBuild::Spec(Kind);
	if (!Battle || !S)
	{
		return TEXT("That cannot be built");
	}
	if (!LoadMesh(S->Mesh))
	{
		return FString::Printf(TEXT("No model for the %s (import %s)"), VLRules::Name(Kind), S->Mesh);
	}
	const int32 Limit = BuildLimit(Kind, Team);
	if (Limit != INDEX_NONE && CountRaised(Kind, Team) >= Limit)
	{
		if (Kind == EVLBuilding::Granary || Kind == EVLBuilding::Treasury)
		{
			return FString::Printf(TEXT("Only one %s per kingdom: raise it a level to hold more"), VLRules::Name(Kind));
		}
		return FString::Printf(TEXT("%s limit %d reached: raise the castle for another"), VLRules::Name(Kind), Limit);
	}
	int32 Queued = 0;
	if (CountBuilders(Team, &Queued) + Queued == 0)
	{
		return TEXT("Only Builders build: train one at the castle");
	}
	if (!Battle->CanAfford(Team, S->Cost))
	{
		return FString::Printf(TEXT("Not enough gold (%d needed)"), S->Cost.Gold);
	}
	return FString();
}

// ------------------------------------------------------------------------------------------------ placing

bool UVLConstruction::CheckPlacement(EVLBuilding Kind, int32 Team, const FVector& Want, float InYaw, FVLPlacement& Out, bool bCells) const
{
	return CheckPlacementImpl(Kind, Team, Want, InYaw, Out, bCells, nullptr);
}

uint32 UVLConstruction::BuildingsStamp() const
{
	// the buildings as they stand: which, where, alive, a site or done, shown (one laid, finished, fallen or sinking
	// changes it)
	uint32 H = 0;
	if (const UVLBattle* Battle = UVLBattle::Get(this))
	{
		for (const FVLBuildingState& B : Battle->GetBuildings())
		{
			const AActor* A = B.Actor.Get();
			H = HashCombine(H, GetTypeHash(A));
			H = HashCombine(H, uint32(B.IsAlive()) | uint32(B.IsSite()) << 1 | uint32(A && A->IsHidden()) << 2 | uint32(A && A->GetActorEnableCollision()) << 3);
			H = HashCombine(H, A ? GetTypeHash(A->GetActorLocation()) : 0);
		}
	}
	return H;
}

bool UVLConstruction::CheckPlacementForGhost(EVLBuilding Kind, int32 Team, const FVector& Want, float InYaw, FVLPlacement& Out)
{
	const UVLGrid* Grid = UVLGrid::Get(this);
	if (CVarOptPlacement.GetValueOnGameThread() == 0 || Kind == EVLBuilding::Mine || !Grid || !Grid->IsBuilt() || !GetWorld())
	{
		return CheckPlacementImpl(Kind, Team, Want, InYaw, Out, true, nullptr);
	}
	// the memo of this very check (CheckPlacement's own snapping), if what it saw still stands and it is fresh: the
	// ground samples are trusted for a second at most, whatever else may have come to stand there
	const float Yaw = FRotator::NormalizeAxis(FMath::GridSnap(InYaw, 90.f));
	const FVector2D P(FMath::GridSnap(Want.X, VLBuild::SnapStep), FMath::GridSnap(Want.Y, VLBuild::SnapStep));
	const uint32 Revision = Grid->GetRevision(), Stamp = BuildingsStamp();
	const double Now = GetWorld()->GetRealTimeSeconds();
	FPlaceMemo* Memo = nullptr;
	for (FPlaceMemo& M : PlaceMemos)
	{
		if (M.Kind == Kind && M.Team == Team && M.Snapped == P && M.Yaw == Yaw && M.WantZ == Want.Z)
		{
			Memo = &M;
			break;
		}
	}
	if (!Memo)
	{
		if (PlaceMemos.Num() >= 96)
		{
			PlaceMemos.RemoveAt(0, 32, EAllowShrinking::No);      // (the oldest places)
		}
		Memo = &PlaceMemos.AddDefaulted_GetRef();
		Memo->Kind = Kind;
		Memo->Team = Team;
		Memo->Snapped = P;
		Memo->Yaw = Yaw;
		Memo->WantZ = Want.Z;
		Memo->GridRevision = 0;
	}
	Memo->bReplay = Memo->Samples.Num() > 0 && Memo->GridRevision == Revision && Memo->Buildings == Stamp && Now - Memo->SampledAt < 1.0;
	Memo->At = 0;
	if (!Memo->bReplay)
	{
		Memo->Samples.Reset();
		Memo->Trees = INDEX_NONE;
		Memo->GridRevision = Revision;
		Memo->Buildings = Stamp;
		Memo->SampledAt = Now;
	}
	return CheckPlacementImpl(Kind, Team, Want, InYaw, Out, true, Memo);
}

bool UVLConstruction::CheckPlacementImpl(EVLBuilding Kind, int32 Team, const FVector& Want, float InYaw, FVLPlacement& Out, bool bCells, FPlaceMemo* Memo, const AActor* Self) const
{
	Out = FVLPlacement();
	Out.Kind = Kind;
	Out.Team = Team;
	UWorld* World = GetWorld();
	const UVLBattle* Battle = UVLBattle::Get(this);
	UVLGrid* Grid = UVLGrid::Get(this);
	const VLBuild::FSpec* Spec = VLBuild::Spec(Kind);
	if (!World || !Battle || !Spec || !Grid || !Grid->EnsureBuilt())
	{
		Out.Reason = TEXT("That cannot be built here");
		return false;
	}
	Out.Mesh = const_cast<UVLConstruction*>(this)->MeshFor(Kind, Team, false);
	if (Self)
	{
		// a building being turned: the mesh it stands with (a farm keeps its variant)
		const UStaticMeshComponent* Own = MeshOf(Self);
		if (Own && Own->GetStaticMesh())
		{
			Out.Mesh = Own->GetStaticMesh()->GetName();
		}
	}
	const UStaticMesh* Mesh = LoadMesh(Out.Mesh);
	if (!Mesh)
	{
		Out.Reason = FString::Printf(TEXT("No model for the %s"), VLRules::Name(Kind));
		return false;
	}

	// ---- a mine goes on a gold vein: a neutral mine (which it takes over), or the ruin of a fallen one
	if (Kind == EVLBuilding::Mine)
	{
		const AActor* Best = nullptr;
		FVector BestAt = FVector::ZeroVector;
		float BestRot = 0.f;
		float BestD = VLBuild::VeinSnap;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			if (VLRules::KindFromName(TagValue(*It, TEXT("Name:"))) != EVLBuilding::Mine)
			{
				continue;
			}
			const FVLBuildingState* S = Battle->FindBuilding(*It);
			const bool bFree = S ? ((S->bDestroyed && S->Collapse < 0.f) || S->Team == UVLBattle::Neutral) : TagValue(*It, TEXT("Team:")).Equals(TEXT("Neutral"), ESearchCase::IgnoreCase);
			const FVector At = S ? S->Rest : It->GetActorLocation();
			const float D = FVector::Dist2D(At, Want);
			if (bFree && D < BestD)
			{
				BestD = D;
				Best = *It;
				BestAt = At;
				BestRot = It->GetActorRotation().Yaw;
			}
		}
		if (!Best)
		{
			Out.Reason = TEXT("A mine is not built: claim a free one (a neutral mine, or an abandoned one)");
			Out.Location = FVector(Want.X, Want.Y, Want.Z);
			Out.Yaw = FMath::GridSnap(InYaw, 90.f);
			return false;
		}
		Out.Vein = const_cast<AActor*>(Best);
		Out.Location = BestAt;
		Out.Yaw = BestRot;
		for (TActorIterator<AVLKing> It(World); It; ++It)
		{
			if (It->IsAlive() && It->Team != Team && It->Team >= 0 && FVector::Dist2D(It->GetFeet(), BestAt) < 800.f)
			{
				Out.Reason = TEXT("Enemy troops stand at the mine");
				return false;
			}
		}
		Out.bValid = true;
		return true;
	}

	// ---- anywhere else: snapped to the half-metre blocks, its front to Yaw + 90, on level, dry, open ground
	const float Yaw = FRotator::NormalizeAxis(FMath::GridSnap(InYaw, 90.f));
	const FVector2D P(FMath::GridSnap(Want.X, VLBuild::SnapStep), FMath::GridSnap(Want.Y, VLBuild::SnapStep));
	Out.Yaw = Yaw;
	const FBox L = Mesh->GetBoundingBox();
	const FRotator Rot(0.f, Yaw, 0.f);
	const FVector AX = Rot.RotateVector(FVector::ForwardVector), AY = Rot.RotateVector(FVector::RightVector);
	const FVector2D LC(L.GetCenter());
	const FVector2D Half(L.GetExtent());
	const FVector2D Centre = P + FVector2D(AX) * LC.X + FVector2D(AY) * LC.Y;

	// what lies on the ground at a point: 0 open ground (OutZ its height), 1 something stands there, 2 water, 3 nothing
	FCollisionQueryParams Q(SCENE_QUERY_STAT(VLPlacement), false);
	if (Ghost)
	{
		Q.AddIgnoredActor(Ghost);
	}
	for (TActorIterator<AVLForest> It(World); It; ++It)
	{
		Q.AddIgnoredActor(*It);         // (trees are cleared where it goes)
	}
	if (Self)
	{
		// (a building being turned: the ground is looked at through it and its props, which turn with it)
		Q.AddIgnoredActor(Self);
		if (const TArray<TWeakObjectPtr<AActor>>* Mine = Props.Find(const_cast<AActor*>(Self)))
		{
			for (const TWeakObjectPtr<AActor>& Prop : *Mine)
			{
				if (Prop.IsValid())
				{
					Q.AddIgnoredActor(Prop.Get());
				}
			}
		}
	}
	const float Top = Want.Z + 6000.f, Bottom = Want.Z - 6000.f;
	auto Trace = [&](const FVector2D& XY, float& OutZ) -> int32
	{
		// (the query's own list of what to look through is copied only when something has to be added to it)
		const FCollisionQueryParams* QQ = &Q;
		TOptional<FCollisionQueryParams> Own;
		for (int32 Try = 0; Try < 6; ++Try)
		{
			FHitResult H;
			if (!World->LineTraceSingleByChannel(H, FVector(XY.X, XY.Y, Top), FVector(XY.X, XY.Y, Bottom), ECC_Visibility, *QQ))
			{
				return 3;
			}
			AActor* A = H.GetActor();
			if (A && (UVLGrid::IsUnseen(A) || A->IsA<APawn>()))
			{
				if (!Own.IsSet())
				{
					Own = Q;
					QQ = &Own.GetValue();
				}
				Own->AddIgnoredActor(A);
				continue;
			}
			OutZ = H.ImpactPoint.Z;
			if (!IsGround(A))
			{
				return 1;
			}
			return Grid->WaterLevelAt(FVector(XY.X, XY.Y, OutZ)) > OutZ + 5.f ? 2 : 0;
		}
		return 3;
	};
	// the ghost's memo: the same samples in the same order (which follows from the samples alone), so they are read
	// back instead of traced; a check that is not the ghost's (Memo null) always traces
	auto Sample = [&](const FVector2D& XY, float& OutZ) -> int32
	{
		if (Memo && Memo->bReplay && Memo->Samples.IsValidIndex(Memo->At))
		{
			const FPlaceMemo::FSample& S = Memo->Samples[Memo->At++];
			if (S.What != 3)
			{
				OutZ = S.Z;
			}
			return S.What;
		}
		const int32 What = Trace(XY, OutZ);
		if (Memo)
		{
			Memo->bReplay = false;          // (past the end of what was kept: the rest is traced and kept)
			FPlaceMemo::FSample& S = Memo->Samples.AddDefaulted_GetRef();
			S.What = int8(What);
			S.Z = OutZ;
			Memo->At = Memo->Samples.Num();
		}
		return What;
	};

	float BaseZ = Want.Z;
	const int32 Mid = Sample(Centre, BaseZ);
	Out.Location = FVector(P.X, P.Y, BaseZ);
	if (Mid != 0)
	{
		Out.Reason = Mid == 2 ? TEXT("Not on the water") : TEXT("Something stands there");
	}
	// plates of about a metre over the footprint (and a fringe of two round it, for the HUD)
	const int32 NX = FMath::Max(1, FMath::CeilToInt(Half.X * 2.f / 100.f)), NY = FMath::Max(1, FMath::CeilToInt(Half.Y * 2.f / 100.f));
	const float SX = Half.X * 2.f / NX, SY = Half.Y * 2.f / NY;
	Out.AxisX = AX * SX * 0.46f;
	Out.AxisY = AY * SY * 0.46f;
	const int32 Fringe = bCells ? 2 : 0;
	int32 Uneven = 0, Wet = 0, Blocked = 0;
	for (int32 j = -Fringe; j < NY + Fringe && (bCells || Out.Reason.IsEmpty()); ++j)
	{
		for (int32 i = -Fringe; i < NX + Fringe && (bCells || Out.Reason.IsEmpty()); ++i)
		{
			const bool bFoot = i >= 0 && j >= 0 && i < NX && j < NY;
			const FVector2D Local(L.Min.X + (i + 0.5f) * SX, L.Min.Y + (j + 0.5f) * SY);
			const FVector2D XY = P + FVector2D(AX) * Local.X + FVector2D(AY) * Local.Y;
			float Z = BaseZ;
			const int32 What = Sample(XY, Z);
			bool bOk = What == 0 && FMath::Abs(Z - BaseZ) <= VLBuild::LevelTolerance;
			if (bFoot && !bOk)
			{
				(What == 2 ? Wet : (What == 0 ? Uneven : Blocked)) += 1;
				if (Out.Reason.IsEmpty())
				{
					Out.Reason = What == 2 ? TEXT("Not on the water") : (What == 0 ? TEXT("The ground is too uneven") : TEXT("Something stands there"));
				}
			}
			if (bCells)
			{
				Out.Cells.Add(FVector(XY.X, XY.Y, (What == 0 || What == 1 ? Z : BaseZ) + 6.f));
				Out.CellState.Add(bFoot ? (bOk ? 0 : 1) : (What == 0 && FMath::Abs(Z - BaseZ) <= 60.f ? 2 : 3));
			}
		}
	}
	// the map's edge
	const FBox2D Bounds = Grid->GetBounds().ExpandBy(-300.f);
	for (const FVector2D& Corner : { FVector2D(-1, -1), FVector2D(1, -1), FVector2D(-1, 1), FVector2D(1, 1) })
	{
		const FVector2D C = Centre + FVector2D(AX) * (Corner.X * Half.X) + FVector2D(AY) * (Corner.Y * Half.Y);
		if (!Bounds.IsInside(C) && Out.Reason.IsEmpty())
		{
			Out.Reason = TEXT("Too near the edge of the map");
		}
	}
	// a free metre round it: no other building (or site) within the gap
	if (Out.Reason.IsEmpty())
	{
		for (const FVLBuildingState& B : Battle->GetBuildings())
		{
			FVector2D BC, BH;
			float BY = 0.f;
			if (B.IsAlive() && B.Actor.Get() != Self && BoxOf(B.Actor.Get(), BC, BH, BY) && Overlap(Centre, Half + FVector2D(VLBuild::Gap, VLBuild::Gap), Yaw, BC, BH, BY))
			{
				Out.Reason = FString::Printf(TEXT("Too close to the %s"), *B.Name);
				break;
			}
		}
	}
	// no foe standing on it (one's own troops step aside when it is laid)
	if (Out.Reason.IsEmpty())
	{
		for (TActorIterator<AVLKing> It(World); It; ++It)
		{
			if (It->IsAlive() && It->Team != Team && It->Team >= 0 && Inside(FVector2D(It->GetFeet()), Centre, Half + FVector2D(100.f, 100.f), Yaw))
			{
				Out.Reason = TEXT("Enemy troops stand there");
				break;
			}
		}
	}
	// its gate can be walked to from the kingdom's ground (the main piece of connected ground)
	if (Out.Reason.IsEmpty())
	{
		const FVector Gate = FVector(Centre.X, Centre.Y, BaseZ) + AY * (Half.Y + 160.f);
		if (Grid->NearestNode(FVector(Gate.X, Gate.Y, BaseZ + 100.f), 10, Grid->MainRegion()) == INDEX_NONE)
		{
			Out.Reason = TEXT("Its gate would open onto ground nobody can walk to");
		}
	}
	Out.bValid = Out.Reason.IsEmpty();
	if (Out.bValid || bCells)
	{
		if (CVarOptPlacement.GetValueOnGameThread() == 0)
		{
			Out.Trees = AVLForest::ClearTrees(this, Centre, Half, Yaw, VLBuild::TreeMargin, false, true);
		}
		else if (Memo && Memo->Trees != INDEX_NONE)
		{
			Out.Trees = Memo->Trees;
		}
		else
		{
			// (the trees ClearTrees would take, counted without the dry run's scan of every plant and its log line)
			Out.Trees = AVLForest::CountTrees(this, Centre, Half, Yaw, VLBuild::TreeMargin);
			if (Memo)
			{
				Memo->Trees = Out.Trees;
			}
		}
	}
	return Out.bValid;
}

bool UVLConstruction::FindPlacementNear(EVLBuilding Kind, int32 Team, const FVector& Near, float Radius, float Yaw, FVLPlacement& Out, int32 MaxTries) const
{
	// rings outward from Near, every 6 m along each ring, from a random start: the first spot that will do
	const float Step = 600.f;
	int32 Tries = 0;
	for (float R = 0.f; R <= Radius && Tries < MaxTries; R += Step)
	{
		const int32 N = R <= 0.f ? 1 : FMath::Max(6, FMath::FloorToInt(2.f * PI * R / Step));
		const float Start = FMath::FRandRange(0.f, 2.f * PI);
		for (int32 k = 0; k < N && Tries < MaxTries; ++k, ++Tries)
		{
			const float A = Start + 2.f * PI * k / N;
			const FVector P = Near + FVector(FMath::Cos(A), FMath::Sin(A), 0.f) * R;
			// the ground's height there: the path grid's floor
			FVector At = P;
			if (const UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->IsBuilt())
			{
				const int32 Node = Grid->NearestNode(FVector(P.X, P.Y, P.Z + 2000.f), 3);
				if (Node == INDEX_NONE)
				{
					continue;
				}
				At.Z = Grid->NodePos(Node).Z;
			}
			if (CheckPlacement(Kind, Team, At, Yaw, Out, false))
			{
				return true;
			}
		}
	}
	return false;
}

AActor* UVLConstruction::PlaceBuilding(const FVLPlacement& Where, const TArray<AVLKing*>& InBuilders, FString* OutWhy, bool bQuiet, bool bQueue)
{
	UWorld* World = GetWorld();
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLGrid* Grid = UVLGrid::Get(this);
	auto Refuse = [&](const FString& Why) -> AActor*
	{
		if (OutWhy)
		{
			*OutWhy = Why;
		}
		if (Battle && Where.Team == UVLBattle::Player && !bQuiet)
		{
			Battle->PushAlert(Why);
			Battle->Play2D(TEXT("S_UIError"), 0.5f);
		}
		return nullptr;
	};
	const VLBuild::FSpec* Spec = VLBuild::Spec(Where.Kind);
	if (!World || !Battle || !Spec)
	{
		return Refuse(TEXT("That cannot be built"));
	}
	// checked again as it is laid (things move)
	FVLPlacement W;
	if (!CheckPlacement(Where.Kind, Where.Team, Where.Location, Where.Yaw, W, false))
	{
		return Refuse(W.Reason);
	}
	const FString Why = BuildRefusal(Where.Kind, Where.Team);
	if (!Why.IsEmpty())
	{
		if (Why.StartsWith(TEXT("Not enough")) && !bQuiet)
		{
			Battle->TrySpend(Where.Team, Spec->Cost);          // (refused: the gold counter flashes, an alert says why)
			return nullptr;
		}
		return Refuse(Why);
	}
	Battle->TrySpend(Where.Team, Spec->Cost, true);
	const FString MeshName = MeshFor(Where.Kind, Where.Team, true);
	UStaticMesh* Mesh = LoadMesh(MeshName);

	AActor* A = nullptr;
	if (AActor* Vein = W.Vein.Get())
	{
		// a mine on a vein: the neutral mine there (or the fallen one's ruin) is taken over and raised again
		A = Vein;
		if (!Battle->FindBuilding(Vein))
		{
			Vein->Tags.AddUnique(TEXT("WasNeutral"));      // (a cancelled site gives it back)
		}
		if (FVLBuildingState* Old = Battle->FindBuilding(Vein))
		{
			Vein->SetActorLocation(Old->Rest, false, nullptr, ETeleportType::TeleportPhysics);
			Vein->SetActorHiddenInGame(false);
			Vein->SetActorEnableCollision(true);
			Old->bDestroyed = false;
			Old->Collapse = -1.f;
			Old->Level = 1;
			Old->Queue.Reset();
			Old->UpgradeLeft = -1.f;
		}
		SetTeamTag(Vein, Where.Team);
		// a claim: the map's mine stays exactly as it stands (no rising walls; its new side's look when it is done)
		Vein->Tags.Remove(TEXT("Abandoned"));
		Vein->Tags.AddUnique(TEXT("Claim"));
	}
	else
	{
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AStaticMeshActor* New = World->SpawnActor<AStaticMeshActor>(W.Location, FRotator(0.f, W.Yaw, 0.f), SP);
		if (!New || !Mesh)
		{
			Battle->AddStock(Where.Team, EVLRes::Gold, Spec->Cost.Gold, true);
			return Refuse(TEXT("It could not be laid"));
		}
		New->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
		New->GetStaticMeshComponent()->SetStaticMesh(Mesh);
		New->Tags = { TEXT("Selectable"), *(TEXT("Name:") + FString(VLRules::Name(Where.Kind))), TEXT("Built") };
		SetTeamTag(New, Where.Team);
		A = New;
	}
	const bool bClaim = A->ActorHasTag(TEXT("Claim"));
	if (!bClaim)
	{
		ApplyTeamLook(MeshOf(A), Where.Team);
	}
	Battle->RegisterBuilding(A);
	FVLBuildingState* St = Battle->FindBuilding(A);
	if (!St)
	{
		return Refuse(TEXT("It could not be laid"));
	}
	St->Build = 0.f;
	St->Health = St->MaxHealth * VLBuild::StartHealth;
	St->bRuntime = true;
	St->Paid = Spec->Cost;
	St->Mesh = MeshName;
	St->Rest = A->GetActorLocation();
	St->bHasRally = false;
	St->Yard.Reset();
	// its own mesh stands hidden (its collision already up: troops walk round the site, the path grid sees it) while
	// a squashed copy rises course by course
	if (UStaticMeshComponent* C = MeshOf(A))
	{
		C->SetVisibility(bClaim);
	}
	ShowRising(*St, 0.f);
	// the trees in its footprint and a margin round it go (and the path grid is sampled again there); then the whole
	// footprint is sampled again with the site standing
	// (one sampling for both: the ground where trunks stood and the footprint, each cell once)
	const bool bOnce = CVarOptPlacement.GetValueOnGameThread() != 0;
	FBox2D Cleared(ForceInit);
	const int32 Trees = bOnce ? AVLForest::ClearTreesAroundDeferred(A, VLBuild::TreeMargin, true, Cleared) : AVLForest::ClearTreesAround(A, VLBuild::TreeMargin, true, false);
	FVector2D BC, BH;
	float BY = 0.f;
	TArray<FBox2D, TInlineAllocator<2>> Resample;
	if (Cleared.bIsValid)
	{
		Resample.Add(Cleared);
	}
	if (BoxOf(A, BC, BH, BY) && Grid)
	{
		const float R = BH.Size() + 300.f;
		Resample.Add(FBox2D(BC - FVector2D(R, R), BC + FVector2D(R, R)));
	}
	if (Grid && Resample.Num() > 0)
	{
		Grid->RebuildAreas(Resample);
	}
	PlaceMemos.Reset();         // (the ground has changed under the ghost's memos)
	// one's own troops standing on it step aside
	if (UVLCommand* Command = UVLCommand::Get(this))
	{
		for (TActorIterator<AVLKing> It(World); It; ++It)
		{
			if (It->IsAlive() && It->Team == Where.Team && !It->IsGarrisoned() && Inside(FVector2D(It->GetFeet()), BC, BH + FVector2D(60.f, 60.f), BY) && !InPlayersHands(*It))
			{
				// (a Builder with a queue keeps it: the job it was on goes back on its front, after the step aside)
				UVLBuilderWork* Queued = UVLBuilderWork::For(*It, false);
				TArray<UVLBuilderWork::FTask> Keep;
				if (Queued && Queued->HasTasks())
				{
					if (AActor* OnJob = Queued->GetJob())
					{
						UVLBuilderWork::FTask T;
						T.Building = OnJob;
						Keep.Add(T);
					}
					Keep.Append(Queued->GetTasks());
				}
				const FVector2D L = (FVector2D(It->GetFeet()) - BC).GetRotated(-BY);
				const FVector2D Push = FMath::Abs(L.X) / BH.X > FMath::Abs(L.Y) / BH.Y ? FVector2D(FMath::Sign(L.X) * (BH.X + 150.f), L.Y) : FVector2D(L.X, FMath::Sign(L.Y) * (BH.Y + 150.f));
				const FVector2D To = BC + Push.GetRotated(BY);
				Command->OrderMove({ *It }, FVector(To.X, To.Y, It->GetFeet().Z), false, EVLFormation::Line);
				for (const UVLBuilderWork::FTask& T : Keep)
				{
					Queued->QueueTask(T);
				}
			}
		}
	}
	Battle->PlayAt(TEXT("S_BuildPlace"), A->GetActorLocation(), 0.55f, 6000.f, 0.1f);
	// who builds it: the Builders given (the player's selected ones), else the nearest free one of its side
	TArray<AVLKing*> Crew;
	for (AVLKing* U : InBuilders)
	{
		if (UVLBuilderWork::IsBuilder(U) && U->IsAlive() && U->Team == Where.Team)
		{
			Crew.Add(U);
		}
	}
	const bool bQueueCrew = bQueue && Crew.Num() > 0;      // (Shift: on the end of the given Builders' queues)
	if (Crew.Num() == 0)
	{
		TArray<AVLKing*> All;
		GetBuilders(Where.Team, All);
		AVLKing* Best = nullptr;
		float BestScore = TNumericLimits<float>::Max();
		for (AVLKing* U : All)
		{
			const UVLBuilderWork* Work = UVLBuilderWork::For(U, false);
			const AActor* OnJob = Work ? Work->GetJob() : nullptr;
			const FVLBuildingState* JobState = OnJob ? Battle->FindBuilding(OnJob) : nullptr;
			if (InPlayersHands(U) || (JobState && JobState->IsSite()) || (Work && Work->HasTasks()))
			{
				continue;           // (busy raising another, or with orders of its own queued)
			}
			const float Score = FVector::Dist2D(U->GetFeet(), A->GetActorLocation()) + (OnJob ? 5000.f : 0.f) + (U->HasOrder() ? 1500.f : 0.f);
			if (Score < BestScore)
			{
				BestScore = Score;
				Best = U;
			}
		}
		if (Best)
		{
			Crew.Add(Best);
		}
	}
	for (AVLKing* U : Crew)
	{
		if (UVLBuilderWork* Work = UVLBuilderWork::For(U))
		{
			if (bQueueCrew)
			{
				UVLBuilderWork::FTask T;
				T.Building = A;
				Work->QueueTask(T);         // built in its turn
			}
			else
			{
				Work->ClearTasks();         // a plain order: the queue goes
				Work->Begin(A, true);
			}
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("BUILD team %d lays a %s (%s) at %.0f %.0f %.0f yaw %.0f for %s: %d tree(s) cleared, %d builder(s) sent"), Where.Team, VLRules::Name(Where.Kind), *MeshName,
		W.Location.X, W.Location.Y, W.Location.Z, W.Yaw, *CostText(Spec->Cost), Trees, Crew.Num());
	if (Where.Team == UVLBattle::Player && Crew.Num() == 0 && !bQuiet)
	{
		const FVector At = A->GetActorLocation();
		Battle->PushAlert(FString::Printf(TEXT("The %s waits for a Builder"), VLRules::Name(Where.Kind)), EVLAlert::Info, &At);
	}
	return A;
}

void UVLConstruction::ShowRising(FVLBuildingState& B, float Progress)
{
	AActor* A = B.Actor.Get();
	UStaticMeshComponent* Own = MeshOf(A);
	if (!A || !Own || !Own->GetStaticMesh() || A->ActorHasTag(TEXT("Claim")))
	{
		return;                     // (a mine being claimed stands as it is: nothing rises)
	}
	TObjectPtr<AStaticMeshActor>& R = Rising.FindOrAdd(A);
	if (!R)
	{
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		R = GetWorld()->SpawnActor<AStaticMeshActor>(A->GetActorLocation(), A->GetActorRotation(), SP);
		if (!R)
		{
			return;
		}
		UStaticMeshComponent* C = R->GetStaticMeshComponent();
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(Own->GetStaticMesh());
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		for (int32 i = 0; i < Own->GetNumMaterials(); ++i)
		{
			C->SetMaterial(i, Own->GetMaterial(i));
		}
	}
	// the walls rise course by course (stepped, not smooth: it reads as building work, not a stretch), from footings
	const float Courses = 14.f;
	const float P = FMath::FloorToFloat(FMath::Pow(FMath::Clamp(Progress, 0.f, 1.f), 0.85f) * Courses) / Courses;
	const FVector S = A->GetActorScale3D();
	R->SetActorLocationAndRotation(A->GetActorLocation(), A->GetActorRotation());
	R->SetActorScale3D(FVector(S.X, S.Y, S.Z * FMath::Max(0.06f, P)));
}

static TAutoConsoleVariable<int32> CVarPropInstances(TEXT("vl.Opt.PropInstances"), 1, TEXT("1: a building's wheat tufts are the instances of one component a mesh. 0: an actor each, as before (for buildings raised after it is set)"));

void UVLConstruction::SpawnProps(FVLBuildingState& B)
{
	AActor* A = B.Actor.Get();
	if (!A || B.Mesh.IsEmpty())
	{
		return;
	}
	const FTransform T = A->GetActorTransform();
	int32 N = 0;
	// (Windows pass, batch 2) A farm's wheat is 84 tufts: an actor each, they were 1,700 actors and as many primitives
	// with a few farms standing. They have no collision, cast no shadow and nothing ever looks one up, so a building's
	// tufts of one mesh are the instances of one component (on one actor among the building's props, which goes and
	// is raised again with them): the same places, turns and sizes. vl.Opt.PropInstances 0: an actor each, as before.
	static const IConsoleVariable* PropInstances = IConsoleManager::Get().FindConsoleVariable(TEXT("vl.Opt.PropInstances"));
	const bool bInstanced = !PropInstances || PropInstances->GetInt() != 0;
	TMap<UStaticMesh*, TArray<FTransform>> Crops;
	for (const FVLPropSpec* P = GBuildingProps; P->Owner; ++P)
	{
		if (B.Mesh != P->Owner)
		{
			continue;
		}
		UStaticMesh* M = LoadMesh(P->Mesh);
		if (!M)
		{
			continue;
		}
		if (bInstanced && FString(P->Mesh).StartsWith(TEXT("SM_Wheat")))
		{
			Crops.FindOrAdd(M).Add(FTransform(FRotator(0.f, A->GetActorRotation().Yaw + P->Yaw, 0.f), T.TransformPosition(FVector(P->X, P->Y, P->Z)), FVector(P->Scale)));
			++N;
			continue;
		}
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AStaticMeshActor* Prop = GetWorld()->SpawnActor<AStaticMeshActor>(T.TransformPosition(FVector(P->X, P->Y, P->Z)), FRotator(0.f, A->GetActorRotation().Yaw + P->Yaw, 0.f), SP);
		if (!Prop)
		{
			continue;
		}
		UStaticMeshComponent* C = Prop->GetStaticMeshComponent();
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(M);
		Prop->SetActorScale3D(FVector(P->Scale));
		const FString PM(P->Mesh);
		if (PM == TEXT("SM_TrainingDummy"))
		{
			Prop->Tags.Add(TEXT("Dummy"));          // the swords knock them about (AVLKing::HitDummies, UVLSwordFx)
			C->bAffectDistanceFieldLighting = false;
		}
		else if (PM.StartsWith(TEXT("SM_Wheat")))
		{
			C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			C->SetCastShadow(false);
			C->WorldPositionOffsetDisableDistance = 6000;
		}
		Props.FindOrAdd(A).Add(Prop);
		++N;
	}
	for (const TPair<UStaticMesh*, TArray<FTransform>>& Crop : Crops)
	{
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AActor* Holder = GetWorld()->SpawnActor<AActor>(AActor::StaticClass(), FTransform(A->GetActorRotation(), A->GetActorLocation()), SP);
		if (!Holder)
		{
			continue;
		}
		UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(Holder, TEXT("Crop"));
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(Crop.Key);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->WorldPositionOffsetDisableDistance = 6000;
		Holder->SetRootComponent(C);
		C->SetWorldLocationAndRotation(A->GetActorLocation(), A->GetActorRotation());
		C->RegisterComponent();
		C->AddInstances(Crop.Value, false, true);
		Props.FindOrAdd(A).Add(Holder);
	}
	if (N > 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("BUILD %s: %d prop(s)"), *B.Name, N);
	}
}

void UVLConstruction::Finish(FVLBuildingState& B)
{
	AActor* A = B.Actor.Get();
	B.Build = 1.f;
	B.Health = FMath::Max(B.Health, B.MaxHealth * 0.999f);
	if (!A)
	{
		return;
	}
	if (UStaticMeshComponent* C = MeshOf(A))
	{
		C->SetVisibility(true);
	}
	if (TObjectPtr<AStaticMeshActor>* R = Rising.Find(A))
	{
		if (*R)
		{
			(*R)->Destroy();
		}
		Rising.Remove(A);
	}
	if (A->ActorHasTag(TEXT("Claim")))
	{
		// a mine claimed: it is its new side's from now, in that side's look (it has no props of its own to raise:
		// what stands round a map's mine is the map's)
		A->Tags.Remove(TEXT("Claim"));
		ApplyTeamLook(MeshOf(A), B.Team);
	}
	else
	{
		SpawnProps(B);
	}
	if (Props.Contains(A))
	{
		// (its props stand in the way too: the dummies' posts, the troughs; the grid saw the bare site until now)
		FVector2D PC, PH;
		float PY = 0.f;
		if (UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->IsBuilt() && BoxOf(A, PC, PH, PY))
		{
			const float R = PH.Size() + 300.f;
			Grid->RebuildArea(FBox2D(PC - FVector2D(R, R), PC + FVector2D(R, R)));
		}
	}
	if (B.Kind == EVLBuilding::Tower && !UVLCommand::IsTower(A))
	{
		// its lookout, as the level builder tags the level's towers (the same mesh: the same tag)
		FName Tag = TowerLookout;
		for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
		{
			if (*It != A && It->GetStaticMeshComponent()->GetStaticMesh() == MeshOf(A)->GetStaticMesh())
			{
				const FString V = TagValue(*It, TEXT("Lookout:"));
				if (!V.IsEmpty())
				{
					Tag = *(TEXT("Lookout:") + V);
					break;
				}
			}
		}
		A->Tags.Add(Tag);
	}
	UVLBattle* Battle = UVLBattle::Get(this);
	UE_LOG(LogSovereignRealms, Log, TEXT("BUILD %s of team %d finished at %.0f %.0f"), *B.Name, B.Team, A->GetActorLocation().X, A->GetActorLocation().Y);
	if (Battle)
	{
		Battle->PlayAt(TEXT("S_BuildComplete"), A->GetActorLocation(), 0.6f, 9000.f, 0.2f);
		if (B.Team == UVLBattle::Player)
		{
			const FVector At = A->GetActorLocation();
			Battle->PushAlert(FString::Printf(TEXT("%s completed"), *B.Name), EVLAlert::Good, &At);
		}
	}
}

bool UVLConstruction::FinishNow(AActor* Building)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	FVLBuildingState* B = Battle ? Battle->FindBuilding(Building) : nullptr;
	if (!B || !B->IsAlive() || !B->IsSite())
	{
		return false;
	}
	B->Health = B->MaxHealth;
	Finish(*B);
	return true;
}

bool UVLConstruction::CancelSite(AActor* Building)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	if (!St || !St->IsAlive() || !St->IsSite())
	{
		return false;
	}
	const FVLCost Back = RefundFor(Building);
	const int32 Team = St->Team;
	const FString Name = St->Name;
	const bool bLevel = !Building->ActorHasTag(TEXT("Built"));       // a vein's mine: the level's actor, given back
	const bool bWasNeutral = Building->ActorHasTag(TEXT("WasNeutral"));
	FVector2D BC, BH;
	float BY = 0.f;
	const bool bBox = BoxOf(Building, BC, BH, BY);
	if (TObjectPtr<AStaticMeshActor>* R = Rising.Find(Building))
	{
		if (*R)
		{
			(*R)->Destroy();
		}
		Rising.Remove(Building);
	}
	if (bLevel)
	{
		// back to a free vein: neutral again if it was, else the ruin it was
		if (bWasNeutral)
		{
			Building->Tags.Remove(TEXT("WasNeutral"));
			SetTeamTag(Building, UVLBattle::Neutral);
			Battle->Forget(Building);
			ApplyTeamLook(MeshOf(Building), UVLBattle::Neutral);
			if (UStaticMeshComponent* C = MeshOf(Building))
			{
				C->SetVisibility(true);
			}
		}
		else
		{
			// (an abandoned mine again: it stands as it stood)
			St->bDestroyed = true;
			St->Health = 0.f;
			St->Build = 1.f;
		}
		Building->Tags.Remove(TEXT("Claim"));
	}
	else
	{
		Battle->Forget(Building);
		Building->Destroy();
	}
	Battle->AddStock(Team, EVLRes::Gold, Back.Gold);
	Battle->AddStock(Team, EVLRes::Food, Back.Food);
	if (UVLGrid* Grid = UVLGrid::Get(this); Grid && bBox)
	{
		const float R = BH.Size() + 300.f;
		Grid->RebuildArea(FBox2D(BC - FVector2D(R, R), BC + FVector2D(R, R)));
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("BUILD %s of team %d cancelled: %s back"), *Name, Team, *CostText(Back));
	if (Team == UVLBattle::Player)
	{
		const FVector At(BC.X, BC.Y, 0.f);
		Battle->PushAlert(FString::Printf(TEXT("%s cancelled: %s back"), *Name, *CostText(Back)), EVLAlert::Info, &At);
	}
	return true;
}

FVLCost UVLConstruction::RefundFor(const AActor* Building) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	FVLCost Back;
	if (!St)
	{
		return Back;
	}
	const VLBuild::FSpec* Spec = VLBuild::Spec(St->Kind);
	FVLCost Paid = (St->Paid.Gold > 0 || St->Paid.Food > 0 || !Spec) ? St->Paid : Spec->Cost;
	if (St->IsSite())
	{
		Back.Gold = FMath::RoundToInt(Paid.Gold * VLBuild::CancelRefund);
		Back.Food = FMath::RoundToInt(Paid.Food * VLBuild::CancelRefund);
		return Back;
	}
	// everything paid for it: its price, each level it was raised to, and the level being raised now
	const int32 Top = St->UpgradeLeft >= 0.f ? St->Level + 1 : St->Level;
	for (int32 L = 2; L <= Top; ++L)
	{
		const FVLCost& C = VLRules::Level(St->Kind, L).Cost;
		Paid.Gold += C.Gold;
		Paid.Food += C.Food;
	}
	Back.Gold = FMath::RoundToInt(Paid.Gold * VLBuild::DemolishRefund);
	Back.Food = FMath::RoundToInt(Paid.Food * VLBuild::DemolishRefund);
	// recruits paid for and not yet trained: all of it
	for (const FString& K : St->Queue)
	{
		const FVLCost& C = VLRules::Troop(K).Cost;
		Back.Gold += C.Gold;
		Back.Food += C.Food;
	}
	return Back;
}

bool UVLConstruction::Demolish(AActor* Building)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	if (!St || !St->IsAlive())
	{
		return false;
	}
	if (St->IsSite())
	{
		return CancelSite(Building);
	}
	if (St->Kind == EVLBuilding::Castle)
	{
		return false;
	}
	const FVLCost Back = RefundFor(Building);
	const int32 Team = St->Team;
	const FString Name = St->Name;
	St->Queue.Reset();
	Battle->Raze(Building);         // it slumps into the ground as a fallen one does (its props go with it)
	Battle->AddStock(Team, EVLRes::Gold, Back.Gold);
	Battle->AddStock(Team, EVLRes::Food, Back.Food);
	UE_LOG(LogSovereignRealms, Log, TEXT("DEMOLISH %s of team %d: %s back"), *Name, Team, *CostText(Back));
	if (Team == UVLBattle::Player)
	{
		const FVector At = Building->GetActorLocation();
		Battle->PushAlert(FString::Printf(TEXT("%s demolished: %s back"), *Name, *CostText(Back)), EVLAlert::Info, &At);
	}
	return true;
}

bool UVLConstruction::AskDemolish(AActor* Building)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	if (!St || !St->IsAlive())
	{
		return false;
	}
	if (St->IsSite())
	{
		return CancelSite(Building);
	}
	if (St->Kind == EVLBuilding::Castle)
	{
		Battle->PushAlert(TEXT("The castle cannot be pulled down"));
		Battle->Play2D(TEXT("S_UIError"), 0.5f);
		return false;
	}
	const double Now = GetWorld()->GetRealTimeSeconds();
	if (AskedDemolish.Get() == Building && Now - AskedAt < 3.0)
	{
		AskedDemolish = nullptr;
		return Demolish(Building);
	}
	AskedDemolish = Building;
	AskedAt = Now;
	Battle->PushAlert(FString::Printf(TEXT("Demolish the %s? Again to confirm: %s back"), *St->Name, *CostText(RefundFor(Building))));
	return false;
}

bool UVLConstruction::IsDemolishAsked(const AActor* Building) const
{
	return Building && AskedDemolish.Get() == Building && GetWorld()->GetRealTimeSeconds() - AskedAt < 3.0;
}

// ------------------------------------------------------------------------------------------------ claiming a mine

bool UVLConstruction::IsFreeMine(const AActor* Mine) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle || !Mine || VLRules::KindFromName(TagValue(Mine, TEXT("Name:"))) != EVLBuilding::Mine)
	{
		return false;
	}
	// (as CheckPlacement's test of a vein)
	const FVLBuildingState* S = Battle->FindBuilding(Mine);
	return S ? ((S->bDestroyed && S->Collapse < 0.f) || S->Team == UVLBattle::Neutral) : TagValue(Mine, TEXT("Team:")).Equals(TEXT("Neutral"), ESearchCase::IgnoreCase);
}

FString UVLConstruction::ClaimRefusal(const AActor* Mine, int32 Team) const
{
	if (!IsFreeMine(Mine))
	{
		return TEXT("Only a free mine can be claimed");
	}
	const FString Why = BuildRefusal(EVLBuilding::Mine, Team);
	if (!Why.IsEmpty())
	{
		return Why;
	}
	FVLPlacement W;
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* S = Battle->FindBuilding(Mine);
	CheckPlacement(EVLBuilding::Mine, Team, S ? S->Rest : Mine->GetActorLocation(), 0.f, W);
	return W.bValid && W.Vein.Get() == Mine ? FString() : (W.Reason.IsEmpty() ? FString(TEXT("It cannot be claimed now")) : W.Reason);
}

AActor* UVLConstruction::ClaimMine(AActor* Mine, int32 Team, const TArray<AVLKing*>& Builders, FString* OutWhy, bool bQuiet, bool bQueue)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle || !IsFreeMine(Mine))
	{
		if (OutWhy)
		{
			*OutWhy = TEXT("Only a free mine can be claimed");
		}
		return nullptr;
	}
	const FVLBuildingState* S = Battle->FindBuilding(Mine);
	FVLPlacement W;
	if (!CheckPlacement(EVLBuilding::Mine, Team, S ? S->Rest : Mine->GetActorLocation(), 0.f, W) || W.Vein.Get() != Mine)
	{
		const FString Why = W.Reason.IsEmpty() ? FString(TEXT("It cannot be claimed now")) : W.Reason;
		if (OutWhy)
		{
			*OutWhy = Why;
		}
		if (Team == UVLBattle::Player && !bQuiet)
		{
			Battle->PushAlert(Why);
			Battle->Play2D(TEXT("S_UIError"), 0.5f);
		}
		return nullptr;
	}
	// (the price, the Builders and the site are PlaceBuilding's, as for anything a Builder raises)
	AActor* A = PlaceBuilding(W, Builders, OutWhy, bQuiet, bQueue);
	if (A)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("CLAIM team %d claims the %s at %.0f %.0f"), Team, VLRules::Name(EVLBuilding::Mine), A->GetActorLocation().X, A->GetActorLocation().Y);
	}
	return A;
}

int32 UVLConstruction::MoveClear(const FVector2D& Centre, const FVector2D& Half, float Yaw)
{
	UVLGrid* Grid = UVLGrid::Get(this);
	int32 Cleared = 0;
	if (!Grid || !Grid->IsBuilt())
	{
		return 0;
	}
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		AVLKing* U = *It;
		if (!U->IsAlive() || U->IsGarrisoned() || !Inside(FVector2D(U->GetFeet()), Centre, Half, Yaw))
		{
			continue;
		}
		const FVector Feet = U->GetFeet();
		if (Grid->NodeAt(Feet, 200.f) != INDEX_NONE || Grid->NearestNode(FVector(Feet.X, Feet.Y, Feet.Z + 100.f), 1, Grid->MainRegion()) != INDEX_NONE)
		{
			continue;
		}
		const int32 Node = Grid->NearestNode(FVector(Feet.X, Feet.Y, Feet.Z + 100.f), 40, Grid->MainRegion());
		if (Node != INDEX_NONE)
		{
			const float HalfHeight = U->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
			U->StopOrder();
			U->SetActorLocation(Grid->NodePos(Node) + FVector(0.f, 0.f, HalfHeight + 4.f), false, nullptr, ETeleportType::TeleportPhysics);
			U->GetCharacterMovement()->StopMovementImmediately();
			++Cleared;
		}
	}
	return Cleared;
}

// ------------------------------------------------------------------------------------------------ turning a building

bool UVLConstruction::CanEverRotate(const AActor* Building, FString* OutWhy) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	const UStaticMeshComponent* C = MeshOf(Building);
	const TCHAR* Why = nullptr;
	if (!St || !St->IsAlive() || !C || !C->GetStaticMesh())
	{
		Why = TEXT("That cannot be turned");
	}
	else if (St->Kind == EVLBuilding::Castle)
	{
		Why = TEXT("The castle cannot be turned");
	}
	else if (St->IsSite())
	{
		Why = TEXT("It is still being built: it can be turned once it stands");
	}
	else if (St->Kind == EVLBuilding::Mine)
	{
		Why = TEXT("A mine is part of the land: it cannot be turned");
	}
	else if (!St->bRuntime)
	{
		Why = TEXT("The map's own buildings stay as they were laid: only ones you raised can be turned");
	}
	if (OutWhy)
	{
		*OutWhy = Why ? Why : TEXT("");
	}
	return Why == nullptr;
}

FString UVLConstruction::RotateRefusal(const AActor* Building, FVLPlacement* OutWhere) const
{
	FString Why;
	if (!CanEverRotate(Building, &Why))
	{
		return Why;
	}
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* St = Battle->FindBuilding(Building);
	// about the middle of its footprint, taken on the half-metre blocks: every turn then lands on the blocks, and four
	// turns bring it back to the very place it stood
	const FBox L = MeshOf(Building)->GetStaticMesh()->GetBoundingBox();
	const FVector2D Mid(FMath::GridSnap(L.GetCenter().X, double(VLBuild::SnapStep)), FMath::GridSnap(L.GetCenter().Y, double(VLBuild::SnapStep)));
	const FVector At = Building->GetActorLocation();
	const float Yaw0 = Building->GetActorRotation().Yaw;
	const float Yaw1 = FRotator::NormalizeAxis(FMath::GridSnap(Yaw0 + 90.f, 90.f));
	const FVector2D Pivot = FVector2D(At) + Mid.GetRotated(Yaw0);
	const FVector2D To = Pivot - Mid.GetRotated(Yaw1);
	FVLPlacement W;
	CheckPlacementImpl(St->Kind, St->Team, FVector(To.X, To.Y, At.Z), Yaw1, W, false, nullptr, Building);
	W.Location.Z = At.Z;
	if (W.bValid && W.Trees > 0)
	{
		W.bValid = false;
		W.Reason = FString::Printf(TEXT("%d tree%s in the way"), W.Trees, W.Trees == 1 ? TEXT(" stands") : TEXT("s stand"));
	}
	if (OutWhere)
	{
		*OutWhere = W;
	}
	return W.bValid ? FString() : (W.Reason.IsEmpty() ? FString(TEXT("It cannot be turned here")) : W.Reason);
}

const FString& UVLConstruction::RotateRefusalCached(const AActor* Building) const
{
	const double Now = GetWorld() ? GetWorld()->GetRealTimeSeconds() : 0.0;
	if (RotateAsked.Get() != Building || Now - RotateAskedAt > 0.4)
	{
		RotateAsked = Building;
		RotateAskedAt = Now;
		RotateAskedWhy = RotateRefusal(Building);
	}
	return RotateAskedWhy;
}

bool UVLConstruction::Rotate(AActor* Building, FString* OutWhy, bool bQuiet)
{
	UWorld* World = GetWorld();
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLGrid* Grid = UVLGrid::Get(this);
	FVLPlacement W;
	const FString Why = RotateRefusal(Building, &W);
	FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	FVector2D OC, OH;
	float OY = 0.f;
	if (!Why.IsEmpty() || !World || !St || !BoxOf(Building, OC, OH, OY))
	{
		const FString Said = Why.IsEmpty() ? FString(TEXT("That cannot be turned")) : Why;
		if (OutWhy)
		{
			*OutWhy = Said;
		}
		if (Battle && St && St->Team == UVLBattle::Player && !bQuiet)
		{
			Battle->PushAlert(Said);
			Battle->Play2D(TEXT("S_UIError"), 0.5f);
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("ROTATE %s refused: %s"), St ? *St->Name : *GetNameSafe(Building), *Said);
		return false;
	}
	const int32 Team = St->Team;
	const FTransform OldT = Building->GetActorTransform();
	const float Turn = FRotator::NormalizeAxis(W.Yaw - OldT.Rotator().Yaw);

	// whoever of its side stands in it or on it is carried round with it, each in its own place of the building (the
	// yard's ranks, a lookout's posts, a Builder at its walls): nobody ends up inside a wall
	struct FRider
	{
		AVLKing* Unit = nullptr;
		FVector Local = FVector::ZeroVector;
		bool bOnIt = false;             // on its lookout
		bool bWalking = false;
		bool bGoalInIt = false;         // its goal lies in the building: it turns with it
		FVector Goal = FVector::ZeroVector;
	};
	TArray<FRider> Riders;
	for (TActorIterator<AVLKing> It(World); It; ++It)
	{
		AVLKing* U = *It;
		if (!U->IsAlive() || U->Team != Team)
		{
			continue;
		}
		const bool bOnIt = U->GarrisonIn.Get() == Building;
		if (!bOnIt && (U->IsGarrisoned() || !Inside(FVector2D(U->GetFeet()), OC, OH + FVector2D(60.f, 60.f), OY)))
		{
			continue;
		}
		FRider& R = Riders.AddDefaulted_GetRef();
		R.Unit = U;
		R.Local = OldT.InverseTransformPosition(U->GetActorLocation());
		R.bOnIt = bOnIt;
		R.bWalking = U->HasOrder() && U->GetWaypoints().Num() > 0;
		if (R.bWalking)
		{
			// (a goal inside it turns with it; one outside stays where it is)
			R.Goal = U->GetWaypoints().Last();
			R.bGoalInIt = Inside(FVector2D(R.Goal), OC, OH, OY);
			if (R.bGoalInIt)
			{
				R.Goal = OldT.InverseTransformPosition(R.Goal);
			}
		}
	}

	// (one standing on its floor is carried by its own movement when that floor moves: it is taken off it first, or it
	// would be turned twice)
	for (const FRider& R : Riders)
	{
		R.Unit->SetBase(static_cast<FMovementBaseInterfaceData*>(nullptr));
	}
	// the building itself (its collision with it), then its props, raised again in their new places
	Building->SetActorLocationAndRotation(W.Location, FRotator(0.f, W.Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
	St->Rest = W.Location;
	const FTransform NewT = Building->GetActorTransform();
	int32 NumProps = 0;
	if (TArray<TWeakObjectPtr<AActor>>* Mine = Props.Find(Building))
	{
		for (const TWeakObjectPtr<AActor>& P : *Mine)
		{
			if (AActor* PA = P.Get())
			{
				PA->Destroy();
			}
		}
		Props.Remove(Building);
		SpawnProps(*St);
		if (const TArray<TWeakObjectPtr<AActor>>* Again = Props.Find(Building))
		{
			NumProps = Again->Num();
		}
	}
	for (const FRider& R : Riders)
	{
		// (those on the ground a little above it: the yard's ground may lie a few centimetres higher there)
		const FVector To = NewT.TransformPosition(R.Local) + FVector(0.f, 0.f, R.bOnIt ? 0.f : VLBuild::LevelTolerance + 5.f);
		R.Unit->SetActorLocationAndRotation(To, FRotator(0.f, R.Unit->GetActorRotation().Yaw + Turn, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
		R.Unit->GetCharacterMovement()->StopMovementImmediately();
	}

	// the path grid: the ground it stood on and the ground it stands on now
	FVector2D NC = OC, NH = OH;
	float NY = OY;
	BoxOf(Building, NC, NH, NY);
	if (Grid && Grid->IsBuilt())
	{
		const float R0 = OH.Size() + 300.f, R1 = NH.Size() + 300.f;
		const FBox2D Areas[2] = { FBox2D(OC - FVector2D(R0, R0), OC + FVector2D(R0, R0)), FBox2D(NC - FVector2D(R1, R1), NC + FVector2D(R1, R1)) };
		Grid->RebuildAreas(Areas);
	}
	PlaceMemos.Reset();
	YardMemos.Remove(Building);
	RotateAsked = nullptr;

	// anyone of its side the turned walls came down on (a footprint that is not square sweeps new ground) is put on the
	// nearest ground that can be walked
	const int32 Cleared = MoveClear(NC, NH + FVector2D(60.f, 60.f), NY);
	// those who were walking walk on, by a route through the turned walls
	for (const FRider& R : Riders)
	{
		if (R.bWalking && !R.bOnIt && R.Unit->HasOrder())
		{
			const FVector Goal = R.bGoalInIt ? NewT.TransformPosition(R.Goal) : R.Goal;
			TArray<FVector> Path;
			if (!Grid || !Grid->FindPath(R.Unit->GetFeet(), Goal, Path) || Path.Num() == 0)
			{
				Path = { Goal };
			}
			R.Unit->FollowPath(Path, false);
		}
	}
	// its yard: each of those waiting keeps its place in the ranks, where that place is now
	int32 Ranked = 0;
	TArray<FVector> Slots;
	float YardYaw = 0.f;
	if (St->Yard.Num() > 0 && YardSlots(Building, Slots, YardYaw))
	{
		for (int32 i = 0; i < St->Yard.Num(); ++i)
		{
			AVLKing* U = St->Yard[i].Get();
			if (!U || U->IsDead())
			{
				continue;
			}
			if (!Slots.IsValidIndex(i))
			{
				St->Yard[i] = nullptr;
				continue;
			}
			++Ranked;
			if (U->HasOrder() || FVector::Dist2D(U->GetFeet(), Slots[i]) > 60.f)
			{
				TArray<FVector> Path;
				if (!Grid || !Grid->FindPath(U->GetFeet(), Slots[i], Path) || Path.Num() == 0)
				{
					Path = { Slots[i] };
				}
				U->FollowPath(Path, false);
			}
		}
	}
	// a rally point the walls now stand on is dropped (recruits wait in the yard, or go out by the door, as before one was set)
	if (St->bHasRally && Inside(FVector2D(St->Rally), NC, NH, NY))
	{
		St->bHasRally = false;
	}
	Battle->PlayAt(TEXT("S_BuildPlace"), Building->GetActorLocation(), 0.4f, 6000.f, 0.1f);
	UE_LOG(LogSovereignRealms, Log, TEXT("ROTATE %s of team %d: yaw %.0f -> %.0f, at %.0f %.0f -> %.0f %.0f; %d carried round, %d moved clear, %d in its yard, %d prop(s)"), *St->Name, Team,
		OldT.Rotator().Yaw, W.Yaw, OldT.GetLocation().X, OldT.GetLocation().Y, W.Location.X, W.Location.Y, Riders.Num(), Cleared, Ranked, NumProps);
	return true;
}

bool UVLConstruction::OrderWork(const TArray<AVLKing*>& Units, AActor* Building, bool bOrdered, bool bQueue)
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	// Builders ordered onto the castle with corners to mend: the repair is paid for now (VLCastleCorners.cpp)
	if (St && bOrdered && St->Kind == EVLBuilding::Castle && Battle->CornerRepairCost(*St) > 0
		&& Units.ContainsByPredicate([St](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U) && U->IsAlive() && U->Team == St->Team; }))
	{
		UVLBattle::Get(this)->PayCornerRepair(Building, St->Team != UVLBattle::Player);
	}
	if (!St || !NeedsWork(*St))
	{
		return false;
	}
	int32 N = 0;
	for (AVLKing* U : Units)
	{
		if (UVLBuilderWork::IsBuilder(U) && U->IsAlive() && U->Team == St->Team && bQueue)
		{
			UVLBuilderWork::FTask T;
			T.Building = Building;
			UVLBuilderWork::For(U)->QueueTask(T);      // Shift: on the end of its queue
			++N;
		}
		else if (UVLBuilderWork::IsBuilder(U) && U->IsAlive() && U->Team == St->Team)
		{
			if (UVLCommand* Command = UVLCommand::Get(this))
			{
				Command->StopAttack(U);
			}
			U->ClearQueue();
			UVLBuilderWork::For(U)->Begin(Building, bOrdered);
			++N;
		}
	}
	return N > 0;
}

bool UVLConstruction::QueueMove(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun)
{
	TArray<AVLKing*> Builders = Units.FilterByPredicate([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U) && U->IsAlive(); });
	if (Builders.Num() == 0)
	{
		return false;
	}
	// a point on open ground near the one clicked (as UVLCommand::OrderMove finds it), each its place in a line there
	FVector Dest = Ground;
	TArray<FVector> Slots;
	UVLGrid* Grid = UVLGrid::Get(this);
	if (Grid && Grid->EnsureBuilt())
	{
		const int32 Node = Grid->NearestNode(Ground, 60);
		if (Node != INDEX_NONE)
		{
			const FVector P = Grid->NodePos(Node);
			if (FMath::Abs(Ground.X - P.X) > Grid->GetCellSize() * 0.5f || FMath::Abs(Ground.Y - P.Y) > Grid->GetCellSize() * 0.5f)
			{
				Dest = P;
			}
		}
		TArray<FVector2D> Slots2D;
		VLFormation::ComputeSlots(Builders, FVector2D(Dest), Slots2D, EVLFormation::Line);
		Grid->FitSlots(Dest, Slots2D, Slots);
	}
	for (int32 i = 0; i < Builders.Num(); ++i)
	{
		UVLBuilderWork::FTask T;
		T.bMove = true;
		T.Point = Slots.IsValidIndex(i) ? Slots[i] : Dest;
		T.bRun = bRun;
		UVLBuilderWork::For(Builders[i])->QueueTask(T);
	}
	if (UVLCommand* Command = UVLCommand::Get(this))
	{
		Command->ShowMarker(Dest);
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("queue: %d Builder(s) walk to %s after their orders"), Builders.Num(), *Dest.ToCompactString());
	return true;
}

bool UVLConstruction::ClearQueues(const TArray<AVLKing*>& Units)
{
	bool bAny = false;
	for (AVLKing* U : Units)
	{
		if (UVLBuilderWork* W = UVLBuilderWork::For(U, false); W && W->HasTasks())
		{
			W->ClearTasks();
			bAny = true;
		}
	}
	return bAny;
}

bool UVLConstruction::OrderRepair(const TArray<AVLKing*>& Units)
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	TArray<AVLKing*> Builders = Units.FilterByPredicate([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U) && U->IsAlive(); });
	if (!Battle || Builders.Num() == 0)
	{
		return false;
	}
	// the nearest damaged building of theirs (sites after)
	FVector Mid = FVector::ZeroVector;
	for (const AVLKing* U : Builders)
	{
		Mid += U->GetFeet() / Builders.Num();
	}
	AActor* Best = nullptr;
	float BestD = TNumericLimits<float>::Max();
	for (const FVLBuildingState& S : Battle->GetBuildings())
	{
		if (S.Team != Builders[0]->Team || !NeedsWork(S))
		{
			continue;
		}
		const float D = Battle->DistanceTo(S.Actor.Get(), Mid) + (S.IsSite() ? 100000.f : 0.f);
		if (D < BestD)
		{
			BestD = D;
			Best = S.Actor.Get();
		}
	}
	if (!Best)
	{
		if (Builders[0]->Team == UVLBattle::Player)
		{
			const_cast<UVLBattle*>(Battle)->PushAlert(TEXT("Nothing of yours needs repair"));
		}
		return false;
	}
	return OrderWork(Builders, Best, true);
}

int32 UVLConstruction::BuildersAt(const AActor* Building) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	return St ? St->BuildersAt : 0;
}

AActor* UVLConstruction::FindJob(const AVLKing* Builder) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle || !Builder)
	{
		return nullptr;
	}
	// the player's Builders help out nearby; a commander's go wherever there is work
	const FVLCommander* C = Battle->GetCommander(Builder->Team);
	const bool bCommanded = C && C->bActive;
	const float Radius = bCommanded ? 1e7f : VLBuild::AutoWorkRadius;
	const double Now = GetWorld()->GetTimeSeconds();
	AActor* Best = nullptr;
	float BestScore = TNumericLimits<float>::Max();
	for (const FVLBuildingState& S : Battle->GetBuildings())
	{
		if (S.Team != Builder->Team || !NeedsWork(S) || S.BuildersAt >= VLBuild::PerBuilding)
		{
			continue;
		}
		const bool bSite = S.IsSite();
		// a damaged building is only worth it once it is properly hurt; and nobody starts mending one of their own
		// accord while it is being hit (a building under repair is out of action)
		if (!bSite && ((S.Health / FMath::Max(S.MaxHealth, 1.f) > 0.9f && !bCommanded && !S.NeedsCornerWork()) || Now - S.LastHit < 10.0))
		{
			continue;
		}
		const float D = Battle->DistanceTo(S.Actor.Get(), Builder->GetFeet());
		if (D > Radius)
		{
			continue;
		}
		// sites nobody works on first, then other sites, then repairs; the nearest of each
		const float Score = bSite ? D * (S.BuildersAt == 0 ? 0.3f : 0.6f) : D * 1.5f + 600.f;
		if (Score < BestScore)
		{
			BestScore = Score;
			Best = S.Actor.Get();
		}
	}
	return Best;
}

// ------------------------------------------------------------------------------------------------ every frame

void UVLConstruction::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UWorld* World = GetWorld();
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!World || !Battle || DeltaSeconds <= 0.f)
	{
		return;
	}
	// the build menu and placing belong to the overview of a match being played
	if (IsPlacing() || bMenuOpen)
	{
		const APlayerController* PC = World->GetFirstPlayerController();
		const AVLKing* Me = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr;
		if (!Me || Me->IsHeroMode() || !Battle->IsPlaying())
		{
			CancelPlacement();
			SetMenu(false);
		}
	}
	if (Battle->GetState() != EVLMatch::Idle)
	{
		TickFarmhands(DeltaSeconds);    // (a match, or one ended and watched on)
	}
	if (Battle->GetState() != EVLMatch::Playing)
	{
		return;
	}
	TickSites(DeltaSeconds);
	TickJobs(DeltaSeconds);
	TickYards(DeltaSeconds);
}

void UVLConstruction::TickSites(float Dt)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	TMap<const AActor*, int32>& AtWork = AtWorkScratch;
	AtWork.Reset();
	// (the battle's registry, not a walk over the world's actors: every Builder is in it; the farms' hands are not,
	// and are no Builders)
	for (AVLKing* It : Battle->AllUnits())
	{
		// (only a Builder has the component: the others' parts are not searched for it)
		if (const UVLBuilderWork* W = It->IsAlive() && UVLBuilderWork::IsBuilder(It) ? It->FindComponentByClass<UVLBuilderWork>() : nullptr; W && W->IsWorking())
		{
			++AtWork.FindOrAdd(W->GetJob());
		}
	}
	for (FVLBuildingState& B : Battle->GetBuildingsMutable())
	{
		AActor* A = B.Actor.Get();
		if (!B.IsAlive())
		{
			B.BuildersAt = 0;
			B.bRepairing = false;
			if (A)
			{
				// a mine that fell is not taken away (it is part of its map): it stands abandoned, in nobody's look,
				// until it is claimed again
				if (B.Kind == EVLBuilding::Mine && !A->ActorHasTag(TEXT("Abandoned")))
				{
					A->Tags.Add(TEXT("Abandoned"));
					A->Tags.Remove(TEXT("Claim"));
					ApplyTeamLook(MeshOf(A), UVLBattle::Neutral);
					if (UStaticMeshComponent* C = MeshOf(A))
					{
						C->SetVisibility(true);
					}
				}
				// it fell (or was pulled down): its props go with it, and a site's rising walls sink with it
				if (TArray<TWeakObjectPtr<AActor>>* Mine = Props.Find(A))
				{
					for (const TWeakObjectPtr<AActor>& P : *Mine)
					{
						if (AActor* PA = P.Get())
						{
							PA->Destroy();
						}
					}
					Props.Remove(A);
				}
				if (TObjectPtr<AStaticMeshActor>* R = Rising.Find(A); R && *R)
				{
					if (A->IsHidden())
					{
						(*R)->Destroy();
						Rising.Remove(A);
					}
					else
					{
						(*R)->SetActorLocation(A->GetActorLocation());
					}
				}
			}
			continue;
		}
		const int32 N = FMath::Min(AtWork.FindRef(A), VLBuild::PerBuilding);
		B.BuildersAt = N;
		if (B.IsSite())
		{
			// it rises only while a Builder works at its walls; each beyond the first adds half the speed
			const VLBuild::FSpec* Spec = VLBuild::Spec(B.Kind);
			const float Rate = N > 0 ? 1.f + VLBuild::ExtraSpeed * (N - 1) : 0.f;
			if (Rate > 0.f)
			{
				const float Before = B.Build;
				B.Build = FMath::Min(1.f, B.Build + Rate * Dt / FMath::Max(Spec ? Spec->Seconds : 16.f, 0.5f));
				B.Health = FMath::Min(B.MaxHealth, B.Health + B.MaxHealth * (1.f - VLBuild::StartHealth) * (B.Build - Before));
				ShowRising(B, B.Build);
				if (B.Build >= 1.f)
				{
					Finish(B);
				}
			}
			continue;
		}
		const bool bWas = B.bRepairing;
		B.bRepairing = N > 0 && B.Health < B.MaxHealth - 0.5f;
		if (B.bRepairing)
		{
			B.Health = FMath::Min(B.MaxHealth, B.Health + N * VLBuild::RepairPerSecond * Dt);
		}
		if (B.bRepairing != bWas)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("REPAIR %s of team %d %s (%.0f / %.0f)"), *B.Name, B.Team, B.bRepairing ? TEXT("started: out of action") : TEXT("ended: back in action"), B.Health, B.MaxHealth);
		}
	}
}

void UVLConstruction::TickJobs(float Dt)
{
	// an idle Builder looks for work now and then (the main game's LookForWork)
	JobClock -= Dt;
	if (JobClock > 0.f)
	{
		return;
	}
	const float Step = 0.5f;
	JobClock = Step;
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		AVLKing* U = *It;
		if (!U->IsAlive() || !UVLBuilderWork::IsBuilder(U) || InPlayersHands(U) || U->IsOnOrder() || U->Team < 0)
		{
			continue;
		}
		UVLBuilderWork* W = UVLBuilderWork::For(U);
		if (!W || W->GetJob() || W->HasTasks())
		{
			continue;               // (at work, or with the player's orders queued: not taken for work nearby)
		}
		W->JobSearch -= Step;
		if (W->JobSearch > 0.f)
		{
			continue;
		}
		W->JobSearch = FMath::FRandRange(1.f, 1.6f);
		if (AActor* Job = FindJob(U))
		{
			W->Begin(Job, false);
		}
	}
}

bool UVLConstruction::YardSlots(const AActor* Building, TArray<FVector>& Out, float& OutYaw) const
{
	Out.Reset();
	const UStaticMeshComponent* C = MeshOf(Building);
	const UStaticMesh* M = C ? C->GetStaticMesh() : nullptr;
	const FVLYardSpec* Y = nullptr;
	for (const FVLYardSpec& S : Yards)
	{
		if (M && M->GetName() == S.Mesh)
		{
			Y = &S;
		}
	}
	if (!Y)
	{
		return false;
	}
	const FTransform T = Building->GetActorTransform();
	OutYaw = Building->GetActorRotation().Yaw + 90.f;           // facing the yard's front (the gate)
	// ranks across the yard, the first against the hall, each from one side to the other
	const int32 Cols = FMath::Max(1, FMath::FloorToInt((Y->X1 - Y->X0) / RankSpacing) + 1);
	const int32 Rows = FMath::Max(1, FMath::FloorToInt((Y->Y1 - Y->Y0) / RankDepth) + 1);
	const float X0 = (Y->X0 + Y->X1) * 0.5f - (Cols - 1) * RankSpacing * 0.5f;
	TArray<FVector2D> Slots;
	for (int32 r = 0; r < Rows; ++r)
	{
		for (int32 c = 0; c < Cols; ++c)
		{
			Slots.Add(FVector2D(T.TransformPosition(FVector(X0 + c * RankSpacing, Y->Y0 + r * RankDepth, 0.f))));
		}
	}
	UVLGrid* Grid = UVLGrid::Get(this);
	if (Grid && Grid->EnsureBuilt())
	{
		// onto the ground that can be walked (the yard's dirt; round a barrel or a post)
		const FVector Mid = T.TransformPosition(FVector((Y->X0 + Y->X1) * 0.5f, (Y->Y0 + Y->Y1) * 0.5f, 0.f));
		const int32 Node = Grid->NearestNode(FVector(Mid.X, Mid.Y, Mid.Z + 200.f), 20, Grid->MainRegion());
		Grid->FitSlots(Node != INDEX_NONE ? Grid->NodePos(Node) : Mid, Slots, Out);
	}
	if (Out.Num() != Slots.Num())
	{
		Out.Reset();
		for (const FVector2D& S : Slots)
		{
			Out.Add(FVector(S.X, S.Y, Building->GetActorLocation().Z));
		}
	}
	return Out.Num() > 0;
}

namespace
{
	/** Does U hold (stand at, or walk to) this place of a yard? */
	bool Holds(const AVLKing* U, const FVector& Slot)
	{
		if (!U || U->IsDead())
		{
			return false;
		}
		if (U->HasOrder())
		{
			const TArray<FVector>& Way = U->GetWaypoints();
			return Way.Num() > 0 && FVector::Dist2D(Way.Last(), Slot) < 150.f;
		}
		return FVector::Dist2D(U->GetFeet(), Slot) < 200.f;
	}
}

bool UVLConstruction::SendToYard(FVLBuildingState& B, AVLKing* Recruit)
{
	AActor* A = B.Actor.Get();
	TArray<FVector> Slots;
	float Yaw = 0.f;
	if (!A || !Recruit || !YardSlots(A, Slots, Yaw))
	{
		return false;
	}
	B.Yard.SetNum(Slots.Num());
	int32 Free = INDEX_NONE;
	for (int32 i = 0; i < Slots.Num() && Free == INDEX_NONE; ++i)
	{
		if (!Holds(B.Yard[i].Get(), Slots[i]))
		{
			Free = i;
		}
	}
	if (Free == INDEX_NONE)
	{
		return false;               // the yard is full: out to the rally point as before
	}
	B.Yard[Free] = Recruit;
	TArray<FVector> Path;
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!Grid || !Grid->FindPath(Recruit->GetFeet(), Slots[Free], Path) || Path.Num() == 0)
	{
		Path = { Slots[Free] };
	}
	Recruit->FollowPath(Path, false);
	return true;
}

void UVLConstruction::TickYards(float Dt)
{
	// those waiting in a yard stand in their ranks facing its gate; one that has gone off gives its place up
	UVLBattle* Battle = UVLBattle::Get(this);
	for (FVLBuildingState& B : Battle->GetBuildingsMutable())
	{
		if (B.Yard.Num() == 0)
		{
			continue;
		}
		if (!B.IsAlive())
		{
			B.Yard.Reset();
			continue;
		}
		// its ranks: worked out again only when the building or the path grid has changed
		const AActor* Hall = B.Actor.Get();
		const UStaticMeshComponent* HallMesh = MeshOf(Hall);
		const UVLGrid* Grid = UVLGrid::Get(this);
		FYardMemo& Memo = YardMemos.FindOrAdd(Hall);
		const uint32 Revision = Grid && Grid->IsBuilt() ? Grid->GetRevision() : 0;
		const UStaticMesh* HallAsset = HallMesh ? HallMesh->GetStaticMesh() : nullptr;
		if (Revision == 0 || Memo.GridRevision != Revision || Memo.Mesh != HallAsset || !Memo.At.Equals(Hall->GetActorTransform(), 0.f))
		{
			Memo.bOk = YardSlots(Hall, Memo.Slots, Memo.Yaw);
			// (after YardSlots: it builds the grid if it was not)
			Memo.GridRevision = Grid && Grid->IsBuilt() ? Grid->GetRevision() : 0;
			Memo.Mesh = HallAsset;
			Memo.At = Hall->GetActorTransform();
		}
		if (!Memo.bOk)
		{
			continue;
		}
		const TArray<FVector>& Slots = Memo.Slots;
		const float Yaw = Memo.Yaw;
		for (int32 i = 0; i < B.Yard.Num() && i < Slots.Num(); ++i)
		{
			AVLKing* U = B.Yard[i].Get();
			if (!Holds(U, Slots[i]))
			{
				B.Yard[i] = nullptr;
				continue;
			}
			if (!U->HasOrder() && !U->IsOnOrder() && !Fighting(U) && !InPlayersHands(U) && FVector::Dist2D(U->GetFeet(), Slots[i]) < 120.f && !U->GetCharacterMovement()->IsFalling())
			{
				U->SetActorRotation(FRotator(0.f, FMath::FixedTurn(U->GetActorRotation().Yaw, Yaw, 300.f * Dt), 0.f));
			}
		}
	}
}

// ------------------------------------------------------------------------------------------------ the player's placing

void UVLConstruction::SetMenu(bool bOpen)
{
	if (bOpen == bMenuOpen)
	{
		return;
	}
	bMenuOpen = bOpen;
	UE_LOG(LogSovereignRealms, Log, TEXT("build menu %s"), bOpen ? TEXT("open") : TEXT("closed"));
}

void UVLConstruction::BeginPlacement(EVLBuilding Kind)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle)
	{
		return;
	}
	const FString Why = Kind == EVLBuilding::Mine ? FString(TEXT("A mine is claimed, not built: right-click a free mine with Builders selected")) : BuildRefusal(Kind, UVLBattle::Player);
	if (!Why.IsEmpty())
	{
		if (Why.StartsWith(TEXT("Not enough")))
		{
			if (const VLBuild::FSpec* S = VLBuild::Spec(Kind))
			{
				Battle->TrySpend(UVLBattle::Player, S->Cost);        // (refused: flashes the gold counter, says why)
			}
		}
		else
		{
			Battle->PushAlert(Why);
			Battle->Play2D(TEXT("S_UIError"), 0.5f);
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("build: %s refused (%s)"), VLRules::Name(Kind), *Why);
		return;
	}
	if (Kind != PlaceTurnsKind)
	{
		PlaceTurns = 0;             // (another kind: it faces the view again; the same kind keeps the turn it was given)
		PlaceTurnsKind = Kind;
	}
	Placing = Kind;
	Current = FVLPlacement();
	LastSnap = FIntPoint(MAX_int32, MAX_int32);
	bMenuOpen = false;              // (the menu would hide the ground near the bottom of the view: B opens it again)
	UE_LOG(LogSovereignRealms, Log, TEXT("build: placing a %s"), VLRules::Name(Kind));
}

void UVLConstruction::CancelPlacement()
{
	if (Placing != EVLBuilding::None)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("build: placing a %s cancelled"), VLRules::Name(Placing));
	}
	Placing = EVLBuilding::None;
	Current = FVLPlacement();
	PlaceMemos.Reset();
	bPointerOnGround = false;
	bRightDown = false;
	HideGhost();
}

void UVLConstruction::TurnPlacement()
{
	if (!IsPlacing() || Placing == EVLBuilding::Mine)
	{
		return;                     // (a mine is part of its map: never placed, never turned)
	}
	PlaceTurns = (PlaceTurns + 1) % 4;
	LastSnap = FIntPoint(MAX_int32, MAX_int32);     // checked again at once, on the turned footprint
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		Battle->Play2D(TEXT("S_UIClick"), 0.4f);
	}
	bLogTurn = true;                // (the turned footprint is logged once the ghost has been checked on it)
	UE_LOG(LogSovereignRealms, Log, TEXT("build: placing a %s turned to %d quarter turn(s)"), VLRules::Name(Placing), PlaceTurns);
}

bool UVLConstruction::OnEscape()
{
	if (IsPlacing())
	{
		CancelPlacement();
		return true;
	}
	if (bMenuOpen)
	{
		SetMenu(false);
		return true;
	}
	return false;
}

void UVLConstruction::HideGhost()
{
	if (Ghost)
	{
		Ghost->SetActorHiddenInGame(true);
	}
}

void UVLConstruction::UpdateGhost(APlayerController* PC, AVLHUD* HUD, AVLKing* Me)
{
	float MX = 0.f, MY = 0.f;
	if (!PC->GetMousePosition(MX, MY) || (HUD && HUD->IsOverUI(FVector2D(MX, MY))))
	{
		bPointerOnGround = false;
		HideGhost();
		return;
	}
	FVector Ground = FVector::ZeroVector;
	Me->PickAt(PC, FVector2D(MX, MY), &Ground, false);
	if (Ground.IsZero())
	{
		bPointerOnGround = false;
		HideGhost();
		return;
	}
	bPointerOnGround = true;
	// its front (the gate, the yard) to the view: the camera looks along Cam, the front faces back along it
	const float CamYaw = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraRotation().Yaw : 0.f;
	// (T: the player's quarter turns on top of that, clockwise as T turns a finished building)
	const float Yaw = FRotator::NormalizeAxis(FMath::GridSnap(CamYaw + 90.f, 90.f) + 90.f * PlaceTurns);
	const FIntPoint Snap(FMath::RoundToInt(Ground.X / VLBuild::SnapStep), FMath::RoundToInt(Ground.Y / VLBuild::SnapStep));
	const double Now = GetWorld()->GetRealTimeSeconds();
	if (Snap != LastSnap || Yaw != LastYaw || Now - CheckedAt > 0.3)
	{
		LastSnap = Snap;
		LastYaw = Yaw;
		CheckedAt = Now;
		const double T0 = FPlatformTime::Seconds();
		CheckPlacementForGhost(Placing, UVLBattle::Player, Ground, Yaw, Current);
		if (CVarPlacementLog.GetValueOnGameThread() != 0)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("PLACEMENT check: %.3f ms (%d plates, %s)"), (FPlatformTime::Seconds() - T0) * 1000.0, Current.Cells.Num(), Current.bValid ? TEXT("fits") : *Current.Reason);
		}
		if (bLogTurn)
		{
			bLogTurn = false;
			UE_LOG(LogSovereignRealms, Log, TEXT("build: the turned ghost at %.0f %.0f yaw %.0f: footprint axes %s / %s, %d plates, %s"), Current.Location.X, Current.Location.Y, Current.Yaw,
				*Current.AxisX.ToCompactString(), *Current.AxisY.ToCompactString(), Current.Cells.Num(), Current.bValid ? TEXT("fits") : *Current.Reason);
		}
	}
	// the ghost: the building itself as glowing glass, green where it fits, red where it does not
	UStaticMesh* Mesh = LoadMesh(Current.Mesh);
	if (!Mesh)
	{
		HideGhost();
		return;
	}
	if (!Ghost)
	{
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Ghost = GetWorld()->SpawnActor<AStaticMeshActor>(Current.Location, FRotator::ZeroRotator, SP);
		if (!Ghost)
		{
			return;
		}
		UStaticMeshComponent* C = Ghost->GetStaticMeshComponent();
		C->SetMobility(EComponentMobility::Movable);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->bReceivesDecals = false;
		C->bAffectDistanceFieldLighting = false;
		C->bAffectDynamicIndirectLighting = false;
		if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Voxel/Materials/M_PlacementGhost.M_PlacementGhost"), nullptr, LOAD_NoWarn | LOAD_Quiet))
		{
			GhostMaterial = UMaterialInstanceDynamic::Create(M, this);
		}
	}
	UStaticMeshComponent* C = Ghost->GetStaticMeshComponent();
	if (C->GetStaticMesh() != Mesh)
	{
		C->SetStaticMesh(Mesh);
		if (GhostMaterial)
		{
			for (int32 i = 0; i < C->GetNumMaterials(); ++i)
			{
				C->SetMaterial(i, GhostMaterial);
			}
		}
	}
	if (GhostMaterial)
	{
		const FLinearColor Tint = Current.bValid ? FLinearColor(0.25f, 1.f, 0.4f, 0.42f) : FLinearColor(1.f, 0.18f, 0.12f, 0.5f);
		GhostMaterial->SetVectorParameterValue(TEXT("Tint"), Tint);
		GhostMaterial->SetScalarParameterValue(TEXT("Opacity"), Tint.A);
	}
	Ghost->SetActorHiddenInGame(false);
	Ghost->SetActorLocationAndRotation(Current.Location + FVector(0.f, 0.f, 3.f), FRotator(0.f, Current.Yaw, 0.f));
}

bool UVLConstruction::OverviewInput(APlayerController* PC, AVLHUD* HUD, AVLKing* Me)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	if (!PC || !Me || !Battle || !Command || !Battle->IsPlaying())
	{
		return false;
	}
	const bool bShift = PC->IsInputKeyDown(EKeys::LeftShift) || PC->IsInputKeyDown(EKeys::RightShift);
	const bool bCtrl = PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl) || PC->IsInputKeyDown(EKeys::LeftCommand) || PC->IsInputKeyDown(EKeys::RightCommand);
	const bool bAlt = PC->IsInputKeyDown(EKeys::LeftAlt) || PC->IsInputKeyDown(EKeys::RightAlt);
	TArray<AVLKing*> Units;
	Command->GetSelection(Units);

	// B: the build menu (as in the main game)
	if (PC->WasInputKeyJustPressed(EKeys::B) && !bCtrl && !bAlt)
	{
		if (IsPlacing())
		{
			CancelPlacement();
		}
		ToggleMenu();
	}
	// X: the selected Builders go and repair the nearest damaged building
	if (PC->WasInputKeyJustPressed(EKeys::X) && !bCtrl && !bAlt && Units.ContainsByPredicate([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); }))
	{
		if (OrderRepair(Units))
		{
			AVLGameMode::PlayOrderSound(Me);
		}
	}
	// Delete / Backspace with a site or a building of one's own selected (and no units): cancel it / demolish it (twice)
	if ((PC->WasInputKeyJustPressed(EKeys::Delete) || PC->WasInputKeyJustPressed(EKeys::BackSpace)) && Units.Num() == 0)
	{
		AActor* Sel = Me->GetSelected();
		const FVLBuildingState* St = Battle->FindBuilding(Sel);
		if (St && St->IsAlive() && St->Team == Me->Team && !Cast<AVLKing>(Sel))
		{
			AskDemolish(Sel);
		}
	}
	// T with a finished building of one's own selected (and no units): it turns a quarter turn clockwise (R is the
	// view's "back to north")
	if (PC->WasInputKeyJustPressed(EKeys::T) && !bCtrl && !bAlt && Units.Num() == 0 && !IsPlacing())
	{
		AActor* Sel = Me->GetSelected();
		const FVLBuildingState* St = Battle->FindBuilding(Sel);
		if (St && St->IsAlive() && St->Team == Me->Team && !Cast<AVLKing>(Sel) && Rotate(Sel))
		{
			AVLGameMode::PlayOrderSound(Me);
		}
	}
	// the menu's 1-6: its entries in the open tab
	if (bMenuOpen && !IsPlacing() && !bCtrl && !bAlt && !bShift)
	{
		static const FKey Digits[6] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six };
		TArray<const VLBuild::FSpec*> Entries;
		VLBuild::TabEntries(Tab, Entries);
		for (int32 i = 0; i < 6; ++i)
		{
			if (PC->WasInputKeyJustPressed(Digits[i]))
			{
				if (Entries.IsValidIndex(i))
				{
					BeginPlacement(Entries[i]->Kind);
				}
				return true;            // (not a platoon key while the menu is open)
			}
		}
	}
	if (!IsPlacing())
	{
		return false;
	}
	// T while placing: the ghost turns a quarter turn clockwise (R stays the view's "back to north")
	if (PC->WasInputKeyJustPressed(EKeys::T) && !bCtrl && !bAlt)
	{
		TurnPlacement();
	}
	UpdateGhost(PC, HUD, Me);
	float MX = 0.f, MY = 0.f;
	const bool bMouse = PC->GetMousePosition(MX, MY);
	const FVector2D Mouse(MX, MY);
	if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) && bMouse)
	{
		if (HUD && HUD->OnMousePress(Mouse, false))
		{
			// the interface's (another card of the menu, a button)
		}
		else if (Current.bValid && bPointerOnGround)
		{
			const TArray<AVLKing*> Builders = Units.FilterByPredicate([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); });
			FString Why;
			if (PlaceBuilding(Current, Builders, &Why, false, bShift))     // (Shift: on the end of their queues)
			{
				AVLGameMode::PlayOrderSound(Me);
				// Shift: another of the same (as long as it can be had)
				if (!bShift || !BuildRefusal(Placing, UVLBattle::Player).IsEmpty())
				{
					CancelPlacement();
				}
				else
				{
					LastSnap = FIntPoint(MAX_int32, MAX_int32);
				}
			}
		}
		else if (bPointerOnGround)
		{
			Battle->PushAlert(Current.Reason.IsEmpty() ? FString(TEXT("It cannot go there")) : Current.Reason);
			Battle->Play2D(TEXT("S_UIError"), 0.5f);
		}
	}
	// RMB (a click, not a drag that turns the view): cancel
	if (PC->WasInputKeyJustPressed(EKeys::RightMouseButton))
	{
		bRightDown = true;
		RightPress = Mouse;
	}
	if (bRightDown && PC->WasInputKeyJustReleased(EKeys::RightMouseButton))
	{
		bRightDown = false;
		if (FVector2D::Distance(Mouse, RightPress) < 6.f && !(HUD && HUD->OnMousePress(Mouse, true)))
		{
			CancelPlacement();
		}
	}
	return true;
}

// ------------------------------------------------------------------------------------------------ the match

int32 UVLConstruction::ClearStartTrainers()
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UWorld* World = GetWorld();
	if (!Battle || !World)
	{
		return 0;
	}
	TArray<AActor*> Gone;
	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		if ((B.Kind == EVLBuilding::Barracks || B.Kind == EVLBuilding::Range) && !B.bRuntime && B.Actor.IsValid() && B.Team >= 0)
		{
			Gone.Add(B.Actor.Get());
		}
	}
	UVLGrid* Grid = UVLGrid::Get(this);
	for (AActor* A : Gone)
	{
		FVector2D BC, BH;
		float BY = 0.f;
		if (BoxOf(A, BC, BH, BY))
		{
			// its training dummies and its lamps go with it
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				if ((It->ActorHasTag(TEXT("Dummy")) || It->IsA<APointLight>()) && Inside(FVector2D(It->GetActorLocation()), BC, BH + FVector2D(150.f, 150.f), BY))
				{
					It->Destroy();
				}
			}
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("match start: the level's %s (team %s) taken away: Builders raise them"), *TagValue(A, TEXT("Name:")), *TagValue(A, TEXT("Team:")));
		Battle->Forget(A);
		A->Destroy();
		if (Grid && Grid->IsBuilt())
		{
			const float R = BH.Size() + 300.f;
			Grid->RebuildArea(FBox2D(BC - FVector2D(R, R), BC + FVector2D(R, R)));
		}
	}
	return Gone.Num();
}

void UVLConstruction::BenchPlacement(EVLBuilding Kind, const FVector& At, int32 N)
{
	N = FMath::Clamp(N, 1, 400);
	PlaceMemos.Reset();
	double Moved = 0.0, Still = 0.0;
	uint32 Digest = 0;
	int32 Fits = 0, Plates = 0, Trees = 0;
	for (int32 i = 0; i < N; ++i)
	{
		const FVector Want = At + FVector(i * VLBuild::SnapStep, (i % 7) * VLBuild::SnapStep, 0.f);
		for (int32 Pass = 0; Pass < 2; ++Pass)
		{
			FVLPlacement Out;
			const double T0 = FPlatformTime::Seconds();
			CheckPlacementForGhost(Kind, UVLBattle::Player, Want, 0.f, Out);
			(Pass == 0 ? Moved : Still) += FPlatformTime::Seconds() - T0;
			Digest = HashCombine(Digest, GetTypeHash(Out.Reason));
			Digest = HashCombine(Digest, uint32(Out.bValid) | uint32(Out.Trees) << 1);
			Digest = HashCombine(Digest, GetTypeHash(Out.Location));
			for (int32 c = 0; c < Out.Cells.Num(); ++c)
			{
				Digest = HashCombine(Digest, HashCombine(GetTypeHash(Out.Cells[c]), uint32(Out.CellState[c])));
			}
			if (Pass == 0)
			{
				Fits += Out.bValid ? 1 : 0;
				Plates += Out.Cells.Num();
				Trees += Out.Trees;
			}
		}
	}
	PlaceMemos.Reset();
	UE_LOG(LogSovereignRealms, Log, TEXT("PLACEMENT bench %s x%d (vl.Opt.Placement %d): moved %.3f ms a check, standing still %.3f ms a check; %d fit, %d plates, %d trees, digest %08x"),
		VLRules::Name(Kind), N, CVarOptPlacement.GetValueOnGameThread(), Moved * 1000.0 / N, Still * 1000.0 / N, Fits, Plates, Trees, Digest);
}

void UVLConstruction::LogStatus() const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle)
	{
		return;
	}
	for (int32 t = 0; t < 2; ++t)
	{
		int32 Queued = 0;
		const int32 N = CountBuilders(t, &Queued);
		UE_LOG(LogSovereignRealms, Log, TEXT("construction team %d: %d builder(s) (+%d in training) of %d; farms raised %d/%d, towers %d/%d"), t, N, Queued, VLBuild::MaxBuilders(Battle->GetCastleLevel(t)),
			CountRaised(EVLBuilding::Farm, t), BuildLimit(EVLBuilding::Farm, t), CountRaised(EVLBuilding::Tower, t), BuildLimit(EVLBuilding::Tower, t));
		TArray<AVLKing*> Builders;
		GetBuilders(t, Builders);
		for (AVLKing* U : Builders)
		{
			const UVLBuilderWork* W = UVLBuilderWork::For(U, false);
			UE_LOG(LogSovereignRealms, Log, TEXT("  %s at %.0f %.0f: %s%s"), *U->GetDisplayName(), U->GetFeet().X, U->GetFeet().Y, W && W->GetJob() ? *W->GetJob()->GetName() : TEXT("idle"),
				W && W->IsWorking() ? TEXT(" (at work, swinging)") : (W && W->GetJob() ? TEXT(" (on the way)") : TEXT("")));
		}
	}
	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		if (B.IsAlive() && (B.IsSite() || B.bRuntime || B.bRepairing || B.Yard.Num() > 0))
		{
			const int32 Waiting = B.Yard.FilterByPredicate([](const TWeakObjectPtr<AVLKing>& U) { return U.IsValid(); }).Num();
			const FVector At = B.Actor->GetActorLocation();
			UE_LOG(LogSovereignRealms, Log, TEXT("  %s (team %d, %s) %s at %.0f %.0f yaw %.0f: %.0f%% built, %d builder(s), health %.0f/%.0f%s, %d waiting in the yard"), *B.Name, B.Team, *B.Mesh, *B.Actor->GetName(),
				At.X, At.Y, B.Actor->GetActorRotation().Yaw, B.Build * 100.f, B.BuildersAt, B.Health, B.MaxHealth, B.bRepairing ? TEXT(" REPAIRING") : TEXT(""), Waiting);
		}
	}
	for (int32 t = 0; t < 2; ++t)
	{
		if (const AActor* Castle = Battle->GetCastle(t))
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("  castle of team %d at %.0f %.0f"), t, Castle->GetActorLocation().X, Castle->GetActorLocation().Y);
		}
	}
	// the gold mines: whose, or free to claim
	for (const TWeakObjectPtr<AActor>& Vein : Battle->MineActors())
	{
		const AActor* V = Vein.Get();
		if (!V)
		{
			continue;
		}
		const FVLBuildingState* S = Battle->FindBuilding(V);
		UE_LOG(LogSovereignRealms, Log, TEXT("  mine %s at %.0f %.0f yaw %.0f: %s%s"), *V->GetName(), V->GetActorLocation().X, V->GetActorLocation().Y, V->GetActorRotation().Yaw,
			!S || S->Team < 0 ? TEXT("free (neutral)") : (S->bDestroyed ? TEXT("free (abandoned)") : (S->IsSite() ? *FString::Printf(TEXT("team %d, being claimed"), S->Team) : *FString::Printf(TEXT("team %d"), S->Team))),
			V->IsHidden() ? TEXT(", HIDDEN") : TEXT(""));
	}
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	EVLBuilding KindArg(const FString& S)
	{
		if (S.StartsWith(TEXT("barr"), ESearchCase::IgnoreCase)) { return EVLBuilding::Barracks; }
		if (S.StartsWith(TEXT("range"), ESearchCase::IgnoreCase) || S.StartsWith(TEXT("arch"), ESearchCase::IgnoreCase)) { return EVLBuilding::Range; }
		if (S.StartsWith(TEXT("farm"), ESearchCase::IgnoreCase)) { return EVLBuilding::Farm; }
		if (S.StartsWith(TEXT("mine"), ESearchCase::IgnoreCase) || S.StartsWith(TEXT("gold"), ESearchCase::IgnoreCase)) { return EVLBuilding::Mine; }
		if (S.StartsWith(TEXT("tower"), ESearchCase::IgnoreCase) || S.StartsWith(TEXT("watch"), ESearchCase::IgnoreCase)) { return EVLBuilding::Tower; }
		return EVLBuilding::None;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdBuild(TEXT("vl.Build"),
		TEXT("vl.Build barracks|range|farm|mine|tower X Y [yaw] [enemy] [near] [queue]: lay a site there (paid; the nearest free Builder goes); near: the nearest good spot within 40 m; queue: on the end of every Builder's queue (Shift)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLConstruction* C = UVLConstruction::Get(World);
			UVLGrid* Grid = UVLGrid::Get(World);
			if (!C || Args.Num() < 3 || !Grid || !Grid->EnsureBuilt())
			{
				return;
			}
			const EVLBuilding Kind = KindArg(Args[0]);
			const int32 Team = Args.Contains(TEXT("enemy")) ? UVLBattle::Enemy : UVLBattle::Player;
			const float Yaw = Args.Num() > 3 && Args[3].IsNumeric() ? FCString::Atof(*Args[3]) : 0.f;
			FVector P(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]), 0.f);
			const int32 Node = Grid->NearestNode(FVector(P.X, P.Y, 100000.f), 6);
			P.Z = Node != INDEX_NONE ? Grid->NodePos(Node).Z : 0.f;
			FVLPlacement Where;
			const bool bOk = Args.Contains(TEXT("near")) ? C->FindPlacementNear(Kind, Team, P, 4000.f, Yaw, Where) : C->CheckPlacement(Kind, Team, P, Yaw, Where);
			FString Why = Where.Reason;
			// queue: on the end of the player's Builders' queues, as a Shift + click of the placing does
			TArray<AVLKing*> Crew;
			if (Args.Contains(TEXT("queue")))
			{
				C->GetBuilders(Team, Crew);
			}
			AActor* A = bOk ? C->PlaceBuilding(Where, Crew, &Why, true, Args.Contains(TEXT("queue"))) : nullptr;
			UE_LOG(LogSovereignRealms, Log, TEXT("vl.Build %s at %.0f %.0f: %s (%d trees)"), VLRules::Name(Kind), Where.Location.X, Where.Location.Y, A ? *A->GetName() : *(TEXT("refused: ") + Why), Where.Trees);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPlacementBench(TEXT("vl.PlacementBench"),
		TEXT("vl.PlacementBench barracks|range|farm|tower X Y [n]: time the placement ghost's check at n places in a row from there (see vl.Opt.Placement)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLConstruction* C = UVLConstruction::Get(World);
			UVLGrid* Grid = UVLGrid::Get(World);
			if (!C || Args.Num() < 3 || !Grid || !Grid->EnsureBuilt())
			{
				return;
			}
			FVector P(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]), 0.f);
			const int32 Node = Grid->NearestNode(FVector(P.X, P.Y, 100000.f), 6);
			P.Z = Node != INDEX_NONE ? Grid->NodePos(Node).Z : 0.f;
			C->BenchPlacement(KindArg(Args[0]), P, Args.Num() > 3 ? FCString::Atoi(*Args[3]) : 40);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdPlace(TEXT("vl.Place"), TEXT("vl.Place barracks|range|farm|mine|tower | off | turn: the player's placing, as a click on the build menu's card (turn: as T while placing)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLConstruction* C = UVLConstruction::Get(World))
			{
				if (Args.Num() == 0 || Args[0] == TEXT("off"))
				{
					C->CancelPlacement();
				}
				else if (Args[0] == TEXT("menu"))
				{
					C->ToggleMenu();
				}
				else if (Args[0] == TEXT("turn"))
				{
					C->TurnPlacement();     // (as T while placing)
				}
				else
				{
					C->BeginPlacement(KindArg(Args[0]));
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdConstruction(TEXT("vl.Construction"), TEXT("log the sites, the Builders and what each does, the yards"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (const UVLConstruction* C = UVLConstruction::Get(World))
			{
				C->LogStatus();
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdDemolish(TEXT("vl.Demolish"), TEXT("vl.Demolish <building name> [enemy]: cancel a site / pull a building down (the refund)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLConstruction* C = UVLConstruction::Get(World);
			UVLBattle* Battle = UVLBattle::Get(World);
			if (!C || !Battle || Args.Num() == 0)
			{
				return;
			}
			TArray<FString> Words(Args);
			const int32 Team = Words.Last() == TEXT("enemy") ? 1 : 0;
			if (Team == 1)
			{
				Words.Pop();
			}
			const FString Name = FString::Join(Words, TEXT(" ")).Replace(TEXT("_"), TEXT(" "));
			// the last one of that name (the newest: a site just laid)
			for (int32 i = Battle->GetBuildings().Num() - 1; i >= 0; --i)
			{
				const FVLBuildingState& B = Battle->GetBuildings()[i];
				if (B.IsAlive() && B.Team == Team && B.Name.Equals(Name, ESearchCase::IgnoreCase))
				{
					AActor* A = B.Actor.Get();
					const bool bOk = C->Demolish(A);
					UE_LOG(LogSovereignRealms, Log, TEXT("vl.Demolish %s: %s"), *Name, bOk ? TEXT("done") : TEXT("refused"));
					return;
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdRotate(TEXT("vl.Rotate"), TEXT("vl.Rotate <building name> [enemy] [times]: turn a finished building a quarter turn clockwise (the newest of that name), as T does; logs where it stands, its door, rally point and yard, and a digest of the walkable ground round it"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLConstruction* C = UVLConstruction::Get(World);
			UVLBattle* Battle = UVLBattle::Get(World);
			UVLGrid* Grid = UVLGrid::Get(World);
			if (!C || !Battle || !Grid || Args.Num() == 0)
			{
				return;
			}
			TArray<FString> Words(Args);
			int32 Times = 1;
			if (Words.Last().IsNumeric())
			{
				Times = FMath::Clamp(FCString::Atoi(*Words.Pop()), 0, 8);
			}
			const int32 Team = Words.Num() > 0 && Words.Last() == TEXT("enemy") ? 1 : 0;
			if (Team == 1)
			{
				Words.Pop();
			}
			const FString Name = FString::Join(Words, TEXT(" ")).Replace(TEXT("_"), TEXT(" "));
			for (int32 i = Battle->GetBuildings().Num() - 1; i >= 0; --i)
			{
				const FVLBuildingState& B = Battle->GetBuildings()[i];
				if (!B.IsAlive() || B.Team != Team || !B.Name.Equals(Name, ESearchCase::IgnoreCase))
				{
					continue;
				}
				AActor* A = B.Actor.Get();
				auto Report = [&](const TCHAR* What)
				{
					// the walkable ground round it, by place (not by node number: a sampled-again area gets new ones)
					const FVector At = A->GetActorLocation();
					uint32 Digest = 0;
					int32 Open = 0;
					for (float Y = At.Y - 2000.f; Y <= At.Y + 2000.f; Y += 50.f)
					{
						for (float X = At.X - 2000.f; X <= At.X + 2000.f; X += 50.f)
						{
							const int32 Node = Grid->NodeAt(FVector(X, Y, At.Z), 300.f);
							const bool bOpen = Node != INDEX_NONE && Grid->RegionOf(Node) == Grid->MainRegion();
							Open += bOpen ? 1 : 0;
							Digest = HashCombine(Digest, bOpen ? GetTypeHash(FIntPoint(FMath::RoundToInt(X), FMath::RoundToInt(Y))) : 7u);
						}
					}
					FVector Door, Rally, Front;
					Battle->FrontOf(A, Door, Rally, Front);
					TArray<FVector> Slots;
					float YardYaw = 0.f;
					const bool bYard = C->YardSlots(A, Slots, YardYaw);
					const FVLBuildingState* S = Battle->FindBuilding(A);
					const int32 Waiting = S ? S->Yard.FilterByPredicate([](const TWeakObjectPtr<AVLKing>& U) { return U.IsValid(); }).Num() : 0;
					UE_LOG(LogSovereignRealms, Log, TEXT("vl.Rotate %s %s: yaw %.0f at %.1f %.1f %.1f; door %.0f %.0f, rally %.0f %.0f, front %.0f %.0f; yard %d place(s)%s, %d waiting; walkable %d, digest %08x"), *Name, What,
						A->GetActorRotation().Yaw, At.X, At.Y, At.Z, Door.X, Door.Y, Rally.X, Rally.Y, Front.X, Front.Y, Slots.Num(),
						bYard ? *FString::Printf(TEXT(" (first %.0f %.0f, facing %.0f)"), Slots[0].X, Slots[0].Y, YardYaw) : TEXT(""), Waiting, Open, Digest);
				};
				Report(TEXT("stands"));
				for (int32 k = 0; k < Times; ++k)
				{
					FString Why;
					const bool bOk = C->Rotate(A, &Why, true);
					Report(bOk ? TEXT("turned") : *(TEXT("refused (") + Why + TEXT(")")));
				}
				return;
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("vl.Rotate %s: no such building of team %d"), *Name, Team);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdWork(TEXT("vl.Work"), TEXT("vl.Work <building name> [enemy]: the side's Builders (all) go to work on it (build / repair)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLConstruction* C = UVLConstruction::Get(World);
			UVLBattle* Battle = UVLBattle::Get(World);
			if (!C || !Battle || Args.Num() == 0)
			{
				return;
			}
			TArray<FString> Words(Args);
			const int32 Team = Words.Last() == TEXT("enemy") ? 1 : 0;
			if (Team == 1)
			{
				Words.Pop();
			}
			const FString Name = FString::Join(Words, TEXT(" ")).Replace(TEXT("_"), TEXT(" "));
			TArray<AVLKing*> Builders;
			C->GetBuilders(Team, Builders);
			for (int32 i = Battle->GetBuildings().Num() - 1; i >= 0; --i)
			{
				const FVLBuildingState& B = Battle->GetBuildings()[i];
				if (B.IsAlive() && B.Team == Team && B.Name.Equals(Name, ESearchCase::IgnoreCase))
				{
					const bool bOk = C->OrderWork(Builders, B.Actor.Get());
					UE_LOG(LogSovereignRealms, Log, TEXT("vl.Work %s: %d builder(s) %s"), *Name, Builders.Num(), bOk ? TEXT("sent") : TEXT("not sent (nothing to do there)"));
					return;
				}
			}
		}));
}

// ------------------------------------------------------------------------------------------------ the farms' hands

bool UVLConstruction::FarmSpots(const FVLBuildingState& B, FVLFarmSpots& Out) const
{
	const AActor* A = B.Actor.Get();
	const UStaticMeshComponent* C = MeshOf(A);
	UVLGrid* Grid = UVLGrid::Get(const_cast<UVLConstruction*>(this));
	if (!A || !C || !C->GetStaticMesh() || !Grid || !Grid->IsBuilt())
	{
		return false;
	}
	// (the map's own farms have no recorded mesh: their mesh's name; SM_Farmstead is SM_Farmstead_A under another name)
	const FString Mesh = B.Mesh.IsEmpty() ? C->GetStaticMesh()->GetName() : B.Mesh;
	const FTransform T = A->GetActorTransform();
	Out = FVLFarmSpots();
	Out.Front = T.GetRotation().RotateVector(FVector(0.f, 1.f, 0.f));      // buildings face their local +Y
	FVector DoorLocal(0.f, -275.f, 50.f);
	for (const FVLDoorSpec* D = GBuildingDoors; D->Owner; ++D)
	{
		if (Mesh == D->Owner)
		{
			DoorLocal = FVector(D->X, D->Y, D->Z);
		}
	}
	// a spot of the ground: the node nearest it (of the door's region), if it is near enough and inside the farm
	int32 Region = 0;
	auto Ground = [&](const FVector& Local, float Within, FVector& OutAt) -> bool
	{
		if (FMath::Abs(Local.X) > 1060.f || FMath::Abs(Local.Y) > 810.f)
		{
			return false;
		}
		const FVector W = T.TransformPosition(Local);
		const int32 N = Grid->NearestNode(W + FVector(0.f, 0.f, 60.f), FMath::CeilToInt32(Within / Grid->GetCellSize()) + 1, Region);
		if (N == INDEX_NONE || FVector::Dist2D(Grid->NodePos(N), W) > Within)
		{
			return false;
		}
		if (Region == 0)
		{
			Region = Grid->RegionOf(N);
		}
		OutAt = Grid->NodePos(N);
		return true;
	};
	// the door: a step out in front of it
	if (!Ground(DoorLocal + FVector(0.f, 110.f, 0.f), 200.f, Out.Door))
	{
		return false;
	}
	// the crop rows: every other tuft of its wheat (none on a mesh without a props table)
	FVector Sum = FVector::ZeroVector;
	int32 Tufts = 0, k = 0;
	for (const FVLPropSpec* P = GBuildingProps; P->Owner; ++P)
	{
		if (Mesh != P->Owner || !FString(P->Mesh).StartsWith(TEXT("SM_Wheat")))
		{
			continue;
		}
		const FVector L(P->X, P->Y, P->Z);
		Sum += L;
		++Tufts;
		FVector At;
		if ((k++ % 3) == 0 && Ground(L, 70.f, At))
		{
			Out.Field.Add(At);
		}
	}
	Out.FieldCentre = Tufts > 0 ? T.TransformPosition(Sum / Tufts) : Out.Door;
	// the store: the hay and the barrel beside the farmhouse door, on the side away from the wheat
	const float Side = (Tufts > 0 && Sum.X / Tufts > DoorLocal.X) ? -1.f : 1.f;
	bool bStore = false;
	for (const float Out_ : { 300.f, 220.f, 380.f, 150.f })
	{
		if (Ground(DoorLocal + FVector(Side * Out_, 130.f, 0.f), 90.f, Out.Store))
		{
			bStore = true;
			break;
		}
	}
	if (!bStore)
	{
		Out.Store = Out.Door;
	}
	return true;
}

void UVLConstruction::DismissCrew(AActor* Farm, FFarmCrew& Crew, const TCHAR* Why)
{
	int32 N = 0;
	for (const TWeakObjectPtr<AVLKing>& H : Crew.Hands)
	{
		if (AVLKing* U = H.Get())
		{
			U->Destroy();
			++N;
		}
	}
	Crew.Hands.Reset();
	UE_LOG(LogSovereignRealms, Log, TEXT("FARMHANDS %s: %d sent away (%s)"), Farm ? *Farm->GetName() : TEXT("a farm"), N, Why);
}

void UVLConstruction::TickFarmhands(float Dt)
{
	FarmClock -= Dt;
	if (FarmClock > 0.f)
	{
		return;
	}
	FarmClock = 1.f;
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle)
	{
		return;
	}
	TSet<const AActor*> Farms;
	for (FVLBuildingState& B : Battle->GetBuildingsMutable())
	{
		AActor* A = B.Actor.Get();
		if (B.Kind != EVLBuilding::Farm || !A)
		{
			continue;
		}
		Farms.Add(A);
		const bool bWant = AVLFarmer::bEnabled && B.IsAlive() && !B.IsSite() && !A->IsHidden() && !A->ActorHasTag(TEXT("Abandoned"));
		if (FFarmCrew* Crew = FarmCrews.Find(A))
		{
			const bool bLost = Crew->Hands.ContainsByPredicate([](const TWeakObjectPtr<AVLKing>& H) { return !H.IsValid(); });
			const bool bMoved = !Crew->At.Equals(A->GetActorTransform(), 1.0);
			if (!bWant || bLost || bMoved)
			{
				DismissCrew(A, *Crew, !bWant ? (B.IsAlive() ? TEXT("the farm is out of work") : TEXT("the farm fell")) : (bMoved ? TEXT("the farm was turned") : TEXT("one went missing")));
				FarmCrews.Remove(A);
			}
		}
		if (!bWant || FarmCrews.Contains(A) || FarmNoSpots.Contains(A))
		{
			continue;
		}
		FVLFarmSpots Spots;
		if (!FarmSpots(B, Spots))
		{
			FarmNoSpots.Add(A);
			UE_LOG(LogSovereignRealms, Warning, TEXT("FARMHANDS %s: no walkable ground at its door: no hands"), *A->GetName());
			continue;
		}
		FFarmCrew& Crew = FarmCrews.Add(A);
		Crew.At = A->GetActorTransform();
		const FVector Side = FVector::CrossProduct(FVector::UpVector, Spots.Front).GetSafeNormal();
		for (int32 i = 0; i < 2; ++i)
		{
			const FVector At = Spots.Door + Side * (i == 0 ? -60.f : 60.f);
			if (AVLFarmer* F = AVLFarmer::Spawn(GetWorld(), i == 0 ? TEXT("FarmerWoman") : TEXT("FarmerMan"), A, Spots, At))
			{
				Crew.Hands.Add(F);
			}
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("FARMHANDS %s (%s of team %d): %d spawned at its door %s; %d spots in the field, the store at %s"), *A->GetName(), *B.Name, B.Team,
			Crew.Hands.Num(), *Spots.Door.ToCompactString(), Spots.Field.Num(), *Spots.Store.ToCompactString());
		if (Crew.Hands.Num() == 0)
		{
			FarmCrews.Remove(A);
			FarmNoSpots.Add(A);     // (no character data: tried once)
		}
	}
	for (auto It = FarmCrews.CreateIterator(); It; ++It)
	{
		AActor* A = It.Key().Get();
		if (!A || !Farms.Contains(A))
		{
			DismissCrew(A, It.Value(), TEXT("the farm is gone"));
			It.RemoveCurrent();
		}
	}
}

// ------------------------------------------------------------------------------------------------ saved games

AActor* UVLConstruction::RestoreBuilding(const FRestore& In, TArray<FBox2D>& OutChanged)
{
	UWorld* World = GetWorld();
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!World || !Battle || In.Kind == EVLBuilding::None)
	{
		return nullptr;
	}
	AActor* A = In.Actor;
	const bool bSpawned = A == nullptr;
	if (bSpawned)
	{
		// raised in the match: the same actor PlaceBuilding makes
		UStaticMesh* Mesh = LoadMesh(In.Mesh);
		if (!Mesh)
		{
			return nullptr;
		}
		FActorSpawnParameters SP;
		SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AStaticMeshActor* New = World->SpawnActor<AStaticMeshActor>(In.Location, In.Rotation, SP);
		if (!New)
		{
			return nullptr;
		}
		New->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
		New->GetStaticMeshComponent()->SetStaticMesh(Mesh);
		New->Tags = { TEXT("Selectable"), *(TEXT("Name:") + FString(VLRules::Name(In.Kind))), TEXT("Built") };
		SetTeamTag(New, In.Team);
		ApplyTeamLook(New->GetStaticMeshComponent(), In.Team);
		A = New;
		// the trees that made way for it are gone again
		FBox2D Cleared(ForceInit);
		AVLForest::ClearTreesAroundDeferred(A, VLBuild::TreeMargin, false, Cleared);
		if (Cleared.bIsValid)
		{
			OutChanged.Add(Cleared);
		}
	}
	else
	{
		// the level's own: its side may have changed in the match (a mine claimed, or fallen and abandoned)
		const FString Tag = TagValue(A, TEXT("Team:"));
		const int32 Had = Tag.IsEmpty() ? UVLBattle::Player : (Tag.IsNumeric() ? FMath::Clamp(FCString::Atoi(*Tag), 0, 1) : UVLBattle::Neutral);
		const bool bMine = In.Kind == EVLBuilding::Mine;
		A->Tags.Remove(TEXT("Claim"));
		A->Tags.Remove(TEXT("WasNeutral"));
		A->Tags.Remove(TEXT("Abandoned"));
		if (Had != In.Team)
		{
			SetTeamTag(A, In.Team);
		}
		if (In.bWasNeutral)
		{
			A->Tags.AddUnique(TEXT("WasNeutral"));
		}
		if (In.bClaim && !In.bDestroyed)
		{
			A->Tags.AddUnique(TEXT("Claim"));           // (it stands as it is until the claim is done)
		}
		else if (bMine && In.bDestroyed)
		{
			A->Tags.AddUnique(TEXT("Abandoned"));
			ApplyTeamLook(MeshOf(A), UVLBattle::Neutral);
		}
		else if (Had != In.Team)
		{
			ApplyTeamLook(MeshOf(A), In.Team);
		}
	}
	Battle->RegisterBuilding(A);
	FVLBuildingState* St = Battle->FindBuilding(A);
	if (!St)
	{
		if (bSpawned)
		{
			A->Destroy();
		}
		return nullptr;
	}
	St->Build = FMath::Clamp(In.Build, 0.f, 1.f);
	St->Rest = A->GetActorLocation();
	St->bDestroyed = In.bDestroyed;
	St->Collapse = -1.f;
	if (!In.Mesh.IsEmpty())
	{
		St->Mesh = In.Mesh;
	}
	UStaticMeshComponent* Own = MeshOf(A);
	const bool bMineRuin = In.bDestroyed && In.Kind == EVLBuilding::Mine;
	if (In.bDestroyed && !bMineRuin)
	{
		// down: out of sight and out of the way (a mine's ruin stands, abandoned)
		A->SetActorHiddenInGame(true);
		A->SetActorEnableCollision(false);
	}
	else if (St->IsSite() && !In.bDestroyed)
	{
		if (Own)
		{
			Own->SetVisibility(A->ActorHasTag(TEXT("Claim")));
		}
		ShowRising(*St, St->Build);
	}
	else if (!In.bDestroyed)
	{
		if (Own)
		{
			Own->SetVisibility(true);
		}
		if (bSpawned)
		{
			SpawnProps(*St);
			if (In.Kind == EVLBuilding::Tower && !UVLCommand::IsTower(A))
			{
				// its lookout (as Finish gives it)
				FName Tag = TowerLookout;
				for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
				{
					if (*It != A && Own && It->GetStaticMeshComponent()->GetStaticMesh() == Own->GetStaticMesh())
					{
						const FString V = TagValue(*It, TEXT("Lookout:"));
						if (!V.IsEmpty())
						{
							Tag = *(TEXT("Lookout:") + V);
							break;
						}
					}
				}
				A->Tags.Add(Tag);
			}
		}
	}
	FVector2D BC, BH;
	float BY = 0.f;
	if (BoxOf(A, BC, BH, BY))
	{
		const float R = BH.Size() + 300.f;
		OutChanged.Add(FBox2D(BC - FVector2D(R, R), BC + FVector2D(R, R)));
	}
	PlaceMemos.Reset();
	return A;
}
