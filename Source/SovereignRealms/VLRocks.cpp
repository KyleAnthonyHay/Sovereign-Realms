// Clearing rocks: Builders take the loose rocks and boulders of a map away (VLRocks.h).
#include "VLRocks.h"
#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLCommand.h"
#include "VLConstruction.h"
#include "VLFootDust.h"
#include "VLGrid.h"
#include "VLKing.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInterface.h"

namespace
{
	const UStaticMeshComponent* RockMesh(const AActor* Actor)
	{
		const AStaticMeshActor* SMA = Cast<AStaticMeshActor>(Actor);
		const UStaticMeshComponent* C = SMA ? SMA->GetStaticMeshComponent() : nullptr;
		return C && C->GetStaticMesh() ? C : nullptr;
	}

	bool IsRockMesh(const UStaticMesh* Mesh)
	{
		return Mesh && Mesh->GetName().StartsWith(TEXT("SM_Rock_"));
	}
}

UVLRocks* UVLRocks::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLRocks>() : nullptr;
}

bool UVLRocks::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UVLRocks::Deinitialize()
{
	Rocks.Reset();
	Work.Reset();
	Cleared.Reset();
	DustActor = nullptr;
	Dust = nullptr;
	Super::Deinitialize();
}

bool UVLRocks::IsRock(const AActor* Actor)
{
	if (!IsValid(Actor) || Actor->IsActorBeingDestroyed() || Actor->ActorHasTag(TEXT("Selectable")))
	{
		return false;
	}
	const UStaticMeshComponent* C = RockMesh(Actor);
	if (!C || !IsRockMesh(C->GetStaticMesh()))
	{
		return false;
	}
	// (a stone squashed flat under something, as Flatlands' label plinths, is no boulder)
	const FVector S = Actor->GetActorScale3D();
	return S.Z > 0.5f * FMath::Max(S.X, S.Y);
}

void UVLRocks::Scan()
{
	bScanned = true;
	Rocks.Reset();
	int32 Instanced = 0;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (IsRock(*It))
		{
			Rocks.Add(*It);
			continue;
		}
		// (rocks as instances of one component: none of the maps has them today; counted, so a map that does is noticed)
		TInlineComponentArray<UInstancedStaticMeshComponent*> Ism(*It);
		for (const UInstancedStaticMeshComponent* C : Ism)
		{
			Instanced += IsRockMesh(C->GetStaticMesh()) ? C->GetInstanceCount() : 0;
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("rocks: %d loose rocks can be cleared on this map (%d rock instances in instanced components, not clearable)"), Rocks.Num(), Instanced);
}

FBox UVLRocks::RockBox(const AActor* Rock) const
{
	const UStaticMeshComponent* C = RockMesh(Rock);
	return C ? C->Bounds.GetBox() : FBox(ForceInit);
}

AActor* UVLRocks::RockAt(const FVector& Point, float Slack)
{
	if (!bScanned)
	{
		Scan();
	}
	AActor* Best = nullptr;
	float BestD = TNumericLimits<float>::Max();
	for (const TWeakObjectPtr<AActor>& R : Rocks)
	{
		AActor* A = R.Get();
		if (!IsRock(A))
		{
			continue;
		}
		const FBox B = RockBox(A).ExpandBy(FVector(Slack, Slack, Slack));
		if (B.IsInside(Point))
		{
			const float D = FVector::DistSquared2D(B.GetCenter(), Point);
			if (D < BestD)
			{
				BestD = D;
				Best = A;
			}
		}
	}
	return Best;
}

float UVLRocks::DistanceTo(const AActor* Rock, const FVector& From, FVector* OutPoint)
{
	const UStaticMeshComponent* C = RockMesh(Rock);
	if (!C)
	{
		return TNumericLimits<float>::Max();
	}
	// its footprint: the bounds' box on the ground plane, a little inside it (the stone is rounder than its box)
	const FBox B = C->Bounds.GetBox();
	const FVector2D Half = FVector2D(B.GetExtent()) * 0.8f;
	const FVector2D Mid(B.GetCenter());
	const FVector2D P(FMath::Clamp(float(From.X), float(Mid.X - Half.X), float(Mid.X + Half.X)), FMath::Clamp(float(From.Y), float(Mid.Y - Half.Y), float(Mid.Y + Half.Y)));
	if (OutPoint)
	{
		*OutPoint = FVector(P.X, P.Y, B.Min.Z);
	}
	return FVector2D::Distance(P, FVector2D(From));
}

bool UVLRocks::OrderClear(const TArray<AVLKing*>& Units, AActor* Rock, bool bQueue)
{
	if (!IsRock(Rock))
	{
		return false;
	}
	int32 Sent = 0;
	for (AVLKing* U : Units)
	{
		UVLBuilderWork* W = U && U->IsAlive() && UVLBuilderWork::IsBuilder(U) ? UVLBuilderWork::For(U) : nullptr;
		if (!W)
		{
			continue;
		}
		if (bQueue)
		{
			UVLBuilderWork::FTask T;
			T.Building = Rock;
			W->QueueTask(T);            // Shift: on the end of its queue (as UVLConstruction::OrderWork)
		}
		else
		{
			if (UVLCommand* Command = UVLCommand::Get(this))
			{
				Command->StopAttack(U);
			}
			U->ClearQueue();
			W->Begin(Rock, true);
		}
		++Sent;
	}
	if (Sent > 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("rocks: %d Builder(s) sent to clear %s%s"), Sent, *Rock->GetName(), bQueue ? TEXT(" (queued)") : TEXT(""));
		if (UVLBattle* Battle = UVLBattle::Get(this))
		{
			Battle->Play2D(TEXT("S_UIClick"), 0.35f);
		}
	}
	return Sent > 0;
}

float UVLRocks::WorkOn(const AActor* Rock) const
{
	const FWork* W = Work.Find(const_cast<AActor*>(Rock));
	return W ? W->Done : 0.f;
}

bool UVLRocks::AddWork(AActor* Rock, const AVLKing* Builder, float Dt)
{
	if (!IsRock(Rock))
	{
		return false;
	}
	FWork* W = Work.Find(Rock);
	if (!W)
	{
		W = &Work.Add(Rock);
		W->BaseScale = Rock->GetActorScale3D();
		W->BaseLocation = Rock->GetActorLocation();
		if (USceneComponent* Root = Rock->GetRootComponent())
		{
			Root->SetMobility(EComponentMobility::Movable);        // (it sinks and shrinks as they work)
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("rocks: work starts on %s"), *Rock->GetName());
	}
	// each Builder at it adds a share (VLBuild::ExtraSpeed beyond the first), up to VLBuild::PerBuilding of them
	if (W->Frame != GFrameCounter)
	{
		W->Frame = GFrameCounter;
		W->InFrame = 0;
	}
	if (W->InFrame >= VLBuild::PerBuilding)
	{
		return false;
	}
	W->Done += Dt * (W->InFrame == 0 ? 1.f : VLBuild::ExtraSpeed);
	++W->InFrame;
	W->NextDust -= Dt;
	if (W->NextDust <= 0.f && Dt > 0.f)
	{
		W->NextDust = 0.6f;
		Puff(RockBox(Rock), 3, 0.7f);
	}
	if (W->Done >= ClearSeconds)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("rocks: %s cleared by %s"), *Rock->GetName(), Builder ? *Builder->GetDisplayName() : TEXT("?"));
		Clear(Rock);
		return true;
	}
	ShowWork(Rock, *W);
	return false;
}

void UVLRocks::ShowWork(AActor* Rock, FWork& W)
{
	const float F = FMath::Clamp(W.Done / ClearSeconds, 0.f, 1.f);
	const FBox B = RockBox(Rock);
	Rock->SetActorScale3D(W.BaseScale * (1.f - 0.3f * F));
	Rock->SetActorLocation(W.BaseLocation - FVector(0.f, 0.f, (B.Max.Z - B.Min.Z) * 0.04f * F));
}

void UVLRocks::Puff(const FBox& Box, int32 Count, float Scale)
{
	UWorld* World = GetWorld();
	if (!World || !Box.IsValid)
	{
		return;
	}
	if (!Dust)
	{
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		P.ObjectFlags |= RF_Transient;
		DustActor = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, P);
		if (!DustActor)
		{
			return;
		}
		Dust = NewObject<UVLFootDust>(DustActor, TEXT("RockDust"));
		Dust->PoolSize = 160;
		Dust->Size = 22.f;
		Dust->Growth = 2.2f;
		Dust->Lifetime = 0.9f;
		Dust->Drift = 200.f;
		Dust->Rise = 130.f;
		Dust->Color = FLinearColor(0.72f, 0.68f, 0.60f);       // stone dust
		Dust->Glow = 0.2f;
		Dust->DustMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Voxel/Materials/MI_Vox_smoke.MI_Vox_smoke"));
		DustActor->SetRootComponent(Dust);
		Dust->RegisterComponent();
	}
	const FVector C = Box.GetCenter();
	const FVector E = Box.GetExtent();
	for (int32 i = 0; i < Count; ++i)
	{
		const float A = i * 2.399963f + FMath::FRand() * 0.6f;
		const FVector Out(FMath::Cos(A), FMath::Sin(A), 0.f);
		Dust->Emit(FVector(C.X + Out.X * E.X * 0.8f, C.Y + Out.Y * E.Y * 0.8f, Box.Min.Z + E.Z * 2.f * FMath::FRandRange(0.1f, 0.7f)), Out, 1, Scale);
	}
	DustUntil = World->GetTimeSeconds() + 1.5f;
}

void UVLRocks::Tick(float DeltaSeconds)
{
	if (Dust && GetWorld() && GetWorld()->GetTimeSeconds() < DustUntil)
	{
		Dust->Advance(DeltaSeconds);
	}
	// rocks nobody works at any more keep the work done on them (as a site does), and their sunk look
	for (auto It = Work.CreateIterator(); It; ++It)
	{
		if (!It->Key.IsValid())
		{
			It.RemoveCurrent();
		}
	}
}

void UVLRocks::Clear(AActor* Rock, bool bQuiet)
{
	if (!IsRock(Rock))
	{
		return;
	}
	FBox B = Work.Contains(Rock) ? FBox(ForceInit) : RockBox(Rock);
	if (const FWork* W = Work.Find(Rock))
	{
		// (its whole size, not the shrunk one)
		Rock->SetActorScale3D(W->BaseScale);
		Rock->SetActorLocation(W->BaseLocation);
		B = RockBox(Rock);
	}
	Cleared.AddUnique(Rock->GetName());
	Work.Remove(Rock);
	Rocks.Remove(Rock);
	if (!bQuiet)
	{
		Puff(B, 24, 1.6f);
		if (UVLBattle* Battle = UVLBattle::Get(this))
		{
			Battle->PlayAt(TEXT("S_BuildingCollapse"), B.GetCenter(), 0.4f, 6000.f, 0.2f);
		}
	}
	Rock->SetActorEnableCollision(false);
	Rock->Destroy();
	// the ground it stood on can be walked and built on again
	if (!bQuiet)
	{
		if (UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->IsBuilt() && B.IsValid)
		{
			const FVector2D Pad(250.f, 250.f);
			Grid->RebuildArea(FBox2D(FVector2D(B.Min) - Pad, FVector2D(B.Max) + Pad));
		}
	}
}

void UVLRocks::SaveTo(TArray<FString>& OutCleared, TArray<FString>& OutWorkNames, TArray<float>& OutWork) const
{
	OutCleared = Cleared;
	OutWorkNames.Reset();
	OutWork.Reset();
	for (const TPair<TWeakObjectPtr<AActor>, FWork>& P : Work)
	{
		if (const AActor* A = P.Key.Get())
		{
			OutWorkNames.Add(A->GetName());
			OutWork.Add(P.Value.Done);
		}
	}
}

AActor* UVLRocks::FindRock(const FString& Name)
{
	if (!bScanned)
	{
		Scan();
	}
	for (const TWeakObjectPtr<AActor>& R : Rocks)
	{
		if (AActor* A = R.Get(); A && IsRock(A) && A->GetName() == Name)
		{
			return A;
		}
	}
	return nullptr;
}

void UVLRocks::RestoreFrom(const TArray<FString>& InCleared, const TArray<FString>& WorkNames, const TArray<float>& InWork, TArray<FBox2D>& OutChanged)
{
	if (InCleared.Num() == 0 && WorkNames.Num() == 0)
	{
		return;
	}
	if (!bScanned)
	{
		Scan();
	}
	TMap<FString, AActor*> ByName;
	for (const TWeakObjectPtr<AActor>& R : Rocks)
	{
		if (AActor* A = R.Get())
		{
			ByName.Add(A->GetName(), A);
		}
	}
	int32 Gone = 0;
	for (const FString& Name : InCleared)
	{
		if (AActor** A = ByName.Find(Name))
		{
			const FBox B = RockBox(*A);
			const FVector2D Pad(250.f, 250.f);
			OutChanged.Add(FBox2D(FVector2D(B.Min) - Pad, FVector2D(B.Max) + Pad));
			Clear(*A, true);
			++Gone;
		}
		else
		{
			Cleared.AddUnique(Name);
		}
	}
	for (int32 i = 0; i < WorkNames.Num() && i < InWork.Num(); ++i)
	{
		if (AActor** A = ByName.Find(WorkNames[i]); A && IsRock(*A) && InWork[i] > 0.f)
		{
			// (as far on as it was: AddWork with no time makes its record, then the work is set)
			AddWork(*A, nullptr, 0.f);
			if (FWork* W = Work.Find(*A))
			{
				W->Done = FMath::Min(InWork[i], ClearSeconds - 0.1f);
				ShowWork(*A, *W);
			}
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("load: %d rock(s) cleared, %d with work on them"), Gone, Work.Num());
}

void UVLRocks::LogStatus() const
{
	int32 Standing = 0;
	for (const TWeakObjectPtr<AActor>& R : Rocks)
	{
		Standing += IsRock(R.Get()) ? 1 : 0;
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("vl.Rocks: %d standing, %d cleared, %d with work on them (%.0f s to clear with one Builder)"), Standing, Cleared.Num(), Work.Num(), ClearSeconds);
	for (const TPair<TWeakObjectPtr<AActor>, FWork>& P : Work)
	{
		if (const AActor* A = P.Key.Get())
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("  %s at (%.0f, %.0f): %.1f of %.0f s"), *A->GetName(), A->GetActorLocation().X, A->GetActorLocation().Y, P.Value.Done, ClearSeconds);
		}
	}
}

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdRocks(TEXT("vl.Rocks"),
		TEXT("vl.Rocks [clear | near | order]: the clearable rocks (standing, cleared, at work); clear: the one nearest the played unit goes now; near: log the nearest; order: the player's selected Builders go and clear the nearest to the played unit"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLRocks* R = UVLRocks::Get(World);
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			const AActor* Me = PC ? PC->GetPawn() : nullptr;
			if (!R)
			{
				return;
			}
			R->RockAt(FVector::ZeroVector, 0.f);        // (the first call scans the map)
			const FString Verb = Args.Num() > 0 ? Args[0].ToLower() : FString();
			if (Verb.IsEmpty() || !Me)
			{
				R->LogStatus();
				return;
			}
			// the nearest standing rock to the played unit
			AActor* Best = nullptr;
			float BestD = TNumericLimits<float>::Max();
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				if (UVLRocks::IsRock(*It))
				{
					const float D = FVector::Dist2D(It->GetActorLocation(), Me->GetActorLocation());
					if (D < BestD)
					{
						BestD = D;
						Best = *It;
					}
				}
			}
			if (!Best)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("vl.Rocks: no rock on this map"));
				return;
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("vl.Rocks %s: %s at (%.0f, %.0f, %.0f), %.0f m away"), *Verb, *Best->GetName(), Best->GetActorLocation().X, Best->GetActorLocation().Y, Best->GetActorLocation().Z, BestD / 100.f);
			if (Verb == TEXT("clear"))
			{
				R->Clear(Best);
			}
			else if (Verb == TEXT("order"))
			{
				TArray<AVLKing*> Builders;
				if (UVLConstruction* C = UVLConstruction::Get(World))
				{
					C->GetBuilders(UVLBattle::Player, Builders);
				}
				UE_LOG(LogSovereignRealms, Log, TEXT("vl.Rocks order: %d Builder(s) -> %s"), Builders.Num(), R->OrderClear(Builders, Best) ? TEXT("sent") : TEXT("none sent"));
			}
		}));
}
