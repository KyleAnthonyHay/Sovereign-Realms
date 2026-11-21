#include "VLSwordsmanCombat.h"
#include "VoxelLab.h"
#include "VLCommand.h"
#include "VLGrid.h"
#include "VLKing.h"
#include "VLBattle.h"
#include "Algo/Sort.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"

namespace
{
	TAutoConsoleVariable<float> CVarSwingVolume(TEXT("vl.Sword.SwingVolume"), 0.3f, TEXT("volume of a sword swing's whoosh"));
	TAutoConsoleVariable<float> CVarHitVolume(TEXT("vl.Sword.HitVolume"), 0.42f, TEXT("volume of a blow's thunk on a training dummy"));
	TAutoConsoleVariable<float> CVarTroopVolume(TEXT("vl.Sword.TroopVolume"), 0.65f, TEXT("troops fighting on orders are this much quieter than the unit the player controls (a share of the volumes)"));
	TAutoConsoleVariable<float> CVarSoundGap(TEXT("vl.Sword.SoundGap"), 0.12f, TEXT("seconds at least between two whooshes, and between two thunks (a group's sounds do not pile up)"));
	TAutoConsoleVariable<float> CVarNear(TEXT("vl.Sword.Near"), 900.f, TEXT("full volume within this many cm of where the player is looking"));
	TAutoConsoleVariable<float> CVarRange(TEXT("vl.Sword.Range"), 4500.f, TEXT("silent from this many cm"));
	TAutoConsoleVariable<int32> CVarCombatLog(TEXT("vl.CombatLog"), 0, TEXT("1: log every swing, every blow that lands and every combat sound"));

	bool CombatLog()
	{
		return CVarCombatLog.GetValueOnGameThread() != 0;
	}

	bool IsPlayers(const AVLKing* Unit)
	{
		return Unit && Cast<APlayerController>(Unit->GetController()) != nullptr;
	}

	/** The unit the player is playing (in the overview the player's own unit takes orders like any other). */
	bool InPlayersHands(const AVLKing* Unit)
	{
		return IsPlayers(Unit) && Unit->IsHeroMode();
	}

	void LoadSet(const TCHAR* Base, TArray<TObjectPtr<USoundBase>>& Out)
	{
		for (int32 i = 1; i <= 8; ++i)
		{
			const FString Name = i == 1 ? FString(Base) : FString::Printf(TEXT("%s_%d"), Base, i);
			if (USoundBase* S = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Voxel/Audio/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet))
			{
				Out.Add(S);
			}
		}
		if (Out.Num() == 0)
		{
			UE_LOG(LogVoxelLab, Warning, TEXT("no %s sounds (copy them to SourceArt/Audio and run Tools/ue/import_audio.py)"), Base);
		}
	}
}

// ------------------------------------------------------------------------------------------------ whoosh, thunk, wobble

UVLSwordFx* UVLSwordFx::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLSwordFx>() : nullptr;
}

bool UVLSwordFx::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UVLSwordFx::Load()
{
	if (bLoaded)
	{
		return;
	}
	bLoaded = true;
	LoadSet(TEXT("S_SwordSwing"), SwingSounds);
	LoadSet(TEXT("S_TargetThunk"), ThunkSounds);
	// placed left and right by where it happens; how loud it is, is worked out in Play
	Pan = NewObject<USoundAttenuation>(this);
	Pan->Attenuation.bAttenuate = false;
	Pan->Attenuation.bSpatialize = true;
}

void UVLSwordFx::Play(TArray<TObjectPtr<USoundBase>>& Set, int32& Last, double& LastTime, const TCHAR* What, const FVector& At, float Volume, const AVLKing* By)
{
	Load();
	UWorld* World = GetWorld();
	if (!World || Set.Num() == 0)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	if (LastTime >= 0.0 && Now - LastTime < CVarSoundGap.GetValueOnGameThread() && !IsPlayers(By))
	{
		return;                     // one of these only just sounded (the player's own blows are always heard)
	}
	const APlayerController* PC = World->GetFirstPlayerController();
	const AVLKing* Player = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr;
	const float Far = Player ? FVector::Dist2D(At, Player->GetListenFocus()) : 0.f;
	const float Near = CVarNear.GetValueOnGameThread();
	const float Fade = FMath::Square(FMath::GetMappedRangeValueClamped(FVector2D(Near, FMath::Max(CVarRange.GetValueOnGameThread(), Near + 1.f)), FVector2D(1.f, 0.f), Far));
	Volume *= Fade * ((By && !IsPlayers(By)) ? CVarTroopVolume.GetValueOnGameThread() : 1.f) * FMath::FRandRange(0.85f, 1.f);
	if (Volume <= 0.004f)
	{
		return;
	}
	int32 Index = FMath::RandRange(0, Set.Num() - 1);
	if (Index == Last && Set.Num() > 1)
	{
		Index = (Index + FMath::RandRange(1, Set.Num() - 1)) % Set.Num();       // never the same twice running
	}
	Last = Index;
	LastTime = Now;
	const float Pitch = FMath::FRandRange(0.93f, 1.07f);
	UGameplayStatics::PlaySoundAtLocation(World, Set[Index], At, Volume, Pitch, 0.f, Pan);
	if (CombatLog())
	{
		UE_LOG(LogVoxelLab, Log, TEXT("sword sound t=%.3f %s clip %d vol %.3f pitch %.2f by %s, %.0f cm from the focus"), Now, What, Index + 1, Volume, Pitch,
			By ? *By->GetDisplayName() : TEXT("-"), Far);
	}
}

void UVLSwordFx::Swing(const AVLKing* By)
{
	if (By)
	{
		Play(SwingSounds, LastSwing, LastSwingTime, TEXT("swing"), By->GetActorLocation() + By->GetActorForwardVector() * 60.f, CVarSwingVolume.GetValueOnGameThread(), By);
	}
}

void UVLSwordFx::HitDummy(AActor* Dummy, const FVector& Away, const AVLKing* By)
{
	if (!Dummy)
	{
		return;
	}
	FWobble* W = Wobbles.FindByPredicate([Dummy](const FWobble& X) { return X.Actor.Get() == Dummy; });
	if (!W)
	{
		FWobble New;
		New.Actor = Dummy;
		New.Base = Dummy->GetActorRotation();       // (it stood still: this is its rest pose)
		W = &Wobbles.Add_GetRef(New);
	}
	W->Away = FVector(Away.X, Away.Y, 0.f).GetSafeNormal();
	W->Time = 0.f;
	Play(ThunkSounds, LastThunk, LastThunkTime, TEXT("thunk"), Dummy->GetActorLocation() + FVector(0.f, 0.f, 90.f), CVarHitVolume.GetValueOnGameThread(), By);
	if (!By || !By->IsTroop() || CombatLog())
	{
		UE_LOG(LogVoxelLab, Log, TEXT("hit %s%s%s"), *Dummy->GetName(), By ? TEXT(" by ") : TEXT(""), By ? *By->GetDisplayName() : TEXT(""));
	}
}

void UVLSwordFx::Tick(float DeltaSeconds)
{
	for (int32 i = Wobbles.Num() - 1; i >= 0; --i)
	{
		FWobble& W = Wobbles[i];
		AActor* A = W.Actor.Get();
		if (!A)
		{
			Wobbles.RemoveAt(i);
			continue;
		}
		W.Time += DeltaSeconds;
		// knocked back, then rocking on its foot until it settles
		const float Tilt = 24.f * FMath::Exp(-3.2f * W.Time) * FMath::Cos(W.Time * 13.f - 0.6f);
		const FVector Axis = FVector::CrossProduct(FVector::UpVector, W.Away).GetSafeNormal();
		A->SetActorRotation(FQuat(Axis, FMath::DegreesToRadians(Tilt)) * W.Base.Quaternion());
		if (W.Time > 2.5f)
		{
			A->SetActorRotation(W.Base);
			Wobbles.RemoveAt(i);
		}
	}
}

// ------------------------------------------------------------------------------------------------ a swordsman on orders

UVLSwordsmanCombat::UVLSwordsmanCombat()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;
}

bool UVLSwordsmanCombat::CanFight(const AVLKing* Unit)
{
	return Unit && Unit->IsAlive() && (Unit->KindId() == EVLUnitKind::Swordsman || !Unit->IsTroop());
}

UVLSwordsmanCombat* UVLSwordsmanCombat::For(AVLKing* Unit, bool bCreate)
{
	if (!Unit)
	{
		return nullptr;
	}
	// (B: the unit remembers its component, and that it has been looked for: no component search per call)
	UVLSwordsmanCombat* Combat = Unit->SwordCombat;
	if (!Combat && !(Unit->CompLooked & 1))
	{
		Combat = Unit->FindComponentByClass<UVLSwordsmanCombat>();
		Unit->SwordCombat = Combat;
		Unit->CompLooked |= 1;
	}
	if (!Combat && bCreate && CanFight(Unit))
	{
		Combat = NewObject<UVLSwordsmanCombat>(Unit, TEXT("SwordsmanCombat"));
		Combat->RegisterComponent();
		Unit->SwordCombat = Combat;
	}
	return Combat;
}

int32 UVLSwordsmanCombat::OrderAttack(const TArray<AVLKing*>& InUnits, AActor* Target, bool bRun)
{
	if (!Target)
	{
		return 0;
	}
	FVector Centre = Target->GetActorLocation();
	UVLBattle* Battle = UVLBattle::Get(Target);
	const AVLKing* Foe = Cast<AVLKing>(Target);
	TArray<AVLKing*> Units;
	FVector2D Mid = FVector2D::ZeroVector;
	for (AVLKing* U : InUnits)
	{
		if (CanFight(U) && !InPlayersHands(U) && !U->IsGarrisoned() && !Units.Contains(U))
		{
			Units.Add(U);
			Mid += FVector2D(U->GetActorLocation());
		}
	}
	const int32 N = Units.Num();
	if (N == 0)
	{
		return 0;
	}
	Mid /= float(N);
	if (Foe)
	{
		// a foe that moves: each runs it down by its own route, and fights where they meet
		for (AVLKing* U : Units)
		{
			UVLSwordsmanCombat* Combat = For(U);
			Combat->Begin(Target);
			Combat->Chase(U, Foe);
		}
		UE_LOG(LogVoxelLab, Log, TEXT("attack: %d swordsman(men) on %s"), N, *Foe->GetDisplayName());
		return N;
	}
	if (Battle && Battle->FindBuilding(Target))
	{
		// a building: the rings go round the point of its walls nearest the group, a step out from them
		FVector Wall;
		Battle->DistanceTo(Target, FVector(Mid.X, Mid.Y, Centre.Z), &Wall);
		const FVector Out = (FVector(Mid.X, Mid.Y, Wall.Z) - Wall).GetSafeNormal2D();
		Centre = Wall + Out * 80.f;
	}
	const FVector2D C2(Centre);
	const UVLSwordsmanCombat* Tune = GetDefault<UVLSwordsmanCombat>();
	// Places on rings round the dummy, each ring filled from the side the group comes from (a few stand before it,
	// a company surrounds it). The nearest take the inner ring; along a ring they keep the order they are in round
	// the dummy, so nobody crosses a neighbour's way.
	const FVector2D Toward = Mid - C2;
	const float Base = Toward.SizeSquared() > 1.f ? FMath::Atan2(Toward.Y, Toward.X) : 0.f;
	auto Bearing = [&](const AVLKing* U)
	{
		const FVector2D D = FVector2D(U->GetActorLocation()) - C2;
		return FMath::FindDeltaAngleRadians(Base, FMath::Atan2(D.Y, D.X));
	};
	Units.Sort([&](const AVLKing& A, const AVLKing& B) { return FVector2D::DistSquared(FVector2D(A.GetActorLocation()), C2) < FVector2D::DistSquared(FVector2D(B.GetActorLocation()), C2); });
	TArray<FVector2D> Slots2D;
	float Radius = FMath::Max(Tune->RingRadius, 60.f);
	const float Room = FMath::Max(Tune->RingSpacing, 40.f);
	for (int32 Done = 0; Done < N;)
	{
		const int32 Cap = FMath::Max(1, FMath::FloorToInt(2.f * PI * Radius / Room));
		const int32 K = FMath::Min(N - Done, Cap);
		const float Step = K == Cap ? 2.f * PI / float(K) : Room / Radius;
		Algo::Sort(MakeArrayView(Units.GetData() + Done, K), [&](const AVLKing* A, const AVLKing* B) { return Bearing(A) < Bearing(B); });
		for (int32 j = 0; j < K; ++j)
		{
			const float Angle = Base + (float(j) - 0.5f * float(K - 1)) * Step;
			Slots2D.Add(C2 + FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * Radius);
		}
		Done += K;
		Radius += FMath::Max(Tune->RingStep, 30.f);
	}
	UVLGrid* Grid = UVLGrid::Get(Target);
	const bool bGrid = Grid && Grid->EnsureBuilt();
	TArray<FVector> Slots;
	if (bGrid)
	{
		// the ground beside the dummy that the group can walk to, and the places moved onto standable ground near it
		int32 Lead = Grid->NodeAt(Units[0]->GetFeet());
		if (Lead == INDEX_NONE)
		{
			Lead = Grid->NearestNode(Units[0]->GetFeet(), 6);
		}
		int32 Beside = Grid->NearestNode(Centre, 60, Grid->RegionOf(Lead));
		if (Beside == INDEX_NONE)
		{
			Beside = Grid->NearestNode(Centre, 60);
		}
		if (Beside != INDEX_NONE)
		{
			Grid->FitSlots(Grid->NodePos(Beside), Slots2D, Slots);
		}
	}
	for (int32 i = 0; i < N; ++i)
	{
		AVLKing* U = Units[i];
		const FVector Slot = Slots.IsValidIndex(i) ? Slots[i] : FVector(Slots2D[i].X, Slots2D[i].Y, U->GetFeet().Z);
		TArray<FVector> Path;
		if (!bGrid || !Grid->FindPath(U->GetFeet(), Slot, Path) || Path.Num() == 0)       // each to its own place: the way round the dummy differs
		{
			Path = { Slot };
		}
		UVLSwordsmanCombat* Combat = For(U);
		U->FollowPath(Path, bRun);
		Combat->Begin(Target);
	}
	UE_LOG(LogVoxelLab, Log, TEXT("attack: %d swordsman(men) on %s at %s"), N, *Target->GetName(), *Centre.ToCompactString());
	return N;
}

void UVLSwordsmanCombat::Begin(AActor* InTarget)
{
	Target = InTarget;
	bEngaged = false;
	Closing = 0.f;
	Waiting = 0.f;
	Swings = 0;
	bChasing = false;
	Chases = 0;
	BestDist = 1e9f;
	SetComponentTickEnabled(Target.IsValid());
}

void UVLSwordsmanCombat::Stop()
{
	if (Target.IsValid() && CombatLog())
	{
		UE_LOG(LogVoxelLab, Log, TEXT("%s leaves off %s after %d swing(s)"), *CastChecked<AVLKing>(GetOwner())->GetDisplayName(), *Target->GetName(), Swings);
	}
	Target = nullptr;
	bEngaged = false;
	SetComponentTickEnabled(false);
}

void UVLSwordsmanCombat::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	AVLKing* Unit = Cast<AVLKing>(GetOwner());
	AActor* Dummy = Target.Get();
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Unit || !Dummy || InPlayersHands(Unit) || Unit->IsGarrisoned() || Unit->IsDead() || (Battle && !Battle->IsAlive(Dummy)))
	{
		Stop();                     // the target is gone (fallen, destroyed), or the player has taken this one over
		return;
	}
	const AVLKing* Foe = Cast<AVLKing>(Dummy);
	const float Dist = DistanceTo(Unit, Dummy);
	if (Foe)
	{
		// running it down: a fresh route while it keeps moving; within reach the chase stops and the fight starts
		if (Unit->HasOrder())
		{
			if (!bChasing)
			{
				return;
			}
			if (Dist <= Reach)
			{
				Unit->StopOrder();
				bChasing = false;
			}
			else
			{
				RepathIn -= DeltaTime;
				if (RepathIn <= 0.f && FVector::Dist2D(Foe->GetFeet(), Unit->GetWaypoints().Num() ? Unit->GetWaypoints().Last() : Unit->GetFeet()) > 150.f)
				{
					Chase(Unit, Foe);
				}
				return;
			}
		}
		else if (Dist > Reach * 1.35f)
		{
			// bounded: a chase that has not come any closer for a dozen fresh routes is given up
			if (Dist < BestDist - 50.f)
			{
				BestDist = Dist;
				Chases = 0;
			}
			if (++Chases > 12)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("%s cannot get at %s: gives up the chase"), *Unit->GetDisplayName(), *Foe->GetDisplayName());
				Stop();
				return;
			}
			Chase(Unit, Foe);
			return;
		}
	}
	else if (Unit->HasOrder())
	{
		return;                     // still on the way to its place
	}
	FVector To = Dummy->GetActorLocation() - Unit->GetActorLocation();
	To.Z = 0.f;
	if (Battle && Battle->FindBuilding(Dummy))
	{
		FVector Wall;
		Battle->DistanceTo(Dummy, Unit->GetFeet(), &Wall);
		To = Wall - Unit->GetActorLocation();
		To.Z = 0.f;
	}
	if (!bEngaged)
	{
		bEngaged = true;
		NextSwing = FMath::FRandRange(0.05f, FMath::Max(SwingInterval, 0.1f));      // each on its own beat
		if (Dist > GiveUpBeyond && !Foe)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("%s could not get to %s (%.0f cm away): no attack"), *Unit->GetDisplayName(), *Dummy->GetName(), Dist);
			Stop();
			return;
		}
		if (!Foe || CombatLog())
		{
			UE_LOG(LogVoxelLab, Log, TEXT("%s engages %s from %.0f cm"), *Unit->GetDisplayName(), *Dummy->GetName(), Dist);
		}
	}
	if (To.Size() < 1.f || Unit->GetCharacterMovement()->IsFalling())
	{
		return;
	}
	const FVector Dir = To.GetSafeNormal();
	const FRotator Now = Unit->GetActorRotation();
	const float WantYaw = Dir.Rotation().Yaw;
	Unit->SetActorRotation(FRotator(0.f, FMath::FixedTurn(Now.Yaw, WantYaw, TurnRate * DeltaTime), 0.f));
	if (Dist > Reach)
	{
		if (Closing < CloseInSeconds)
		{
			// out of reach (its place was taken, or moved off bad ground): a few steps closer
			Closing += DeltaTime;
			Unit->GetCharacterMovement()->MaxWalkSpeed = Unit->WalkSpeed;
			Unit->AddMovementInput(Dir, 1.f);
			return;
		}
		if (Dist > BlowReach)
		{
			// crowded out: it stands facing the dummy and tries for a way in again in a while (no cuts at the air)
			Waiting += DeltaTime;
			if (Waiting > RetrySeconds)
			{
				Waiting = 0.f;
				Closing = 0.f;
			}
			return;
		}
	}
	NextSwing -= DeltaTime;
	if (NextSwing <= 0.f && FMath::Abs(FMath::FindDeltaAngleDegrees(Unit->GetActorRotation().Yaw, WantYaw)) <= FaceWithin)
	{
		NextSwing = FMath::Max(SwingInterval, 0.1f) * (1.f + FMath::FRandRange(-SwingJitter, SwingJitter));
		++Swings;
		Unit->Attack();             // the next swing of the combo (the stance holds between them)
		if (CombatLog())
		{
			UE_LOG(LogVoxelLab, Log, TEXT("%s swings at %s (%d), %.0f cm"), *Unit->GetDisplayName(), *Dummy->GetName(), Swings, Dist);
		}
	}
}

float UVLSwordsmanCombat::DistanceTo(const AVLKing* Unit, const AActor* To) const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (Battle && Battle->FindBuilding(To))
	{
		return FMath::Max(0.f, Battle->DistanceTo(To, Unit->GetFeet()) - VLRules::BuildingHitPad) + 100.f;     // to its hit box
	}
	return FVector::Dist2D(To->GetActorLocation(), Unit->GetActorLocation());
}

void UVLSwordsmanCombat::Chase(AVLKing* Unit, const AVLKing* Foe)
{
	// to a point just short of it on the line from here (others come at it from their own sides)
	const FVector Me = Unit->GetFeet(), There = Foe->GetFeet();
	const FVector Goal = There + (Me - There).GetSafeNormal2D() * 110.f;
	TArray<FVector> Path;
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!(Grid && Grid->EnsureBuilt() && Grid->FindPath(Me, Goal, Path) && Path.Num() > 0))
	{
		Path = { Goal };
	}
	Unit->FollowPath(Path, FVector::Dist2D(Me, There) > 700.f);
	bChasing = true;
	bEngaged = false;
	RepathIn = RepathSeconds * FMath::FRandRange(0.8f, 1.2f);
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdDummies(TEXT("vl.Dummies"), TEXT("log every training dummy: its number, where it stands and where it shows in the view (fractions, for vl.Click)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			UVLCommand* Command = UVLCommand::Get(World);
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			if (!Command)
			{
				return;
			}
			TArray<AActor*> Dummies;
			Command->GetDummies(Dummies);
			int32 SX = 1, SY = 1;
			if (PC)
			{
				PC->GetViewportSize(SX, SY);
			}
			for (int32 i = 0; i < Dummies.Num(); ++i)
			{
				FVector2D S = FVector2D::ZeroVector;
				const bool bSeen = PC && PC->ProjectWorldLocationToScreen(Dummies[i]->GetActorLocation() + FVector(0.f, 0.f, 80.f), S);
				UE_LOG(LogVoxelLab, Log, TEXT("dummy %d %s at %s, in the view at %.3f %.3f%s"), i + 1, *Dummies[i]->GetName(), *Dummies[i]->GetActorLocation().ToCompactString(),
					S.X / FMath::Max(SX, 1), S.Y / FMath::Max(SY, 1), bSeen ? TEXT("") : TEXT(" (not in it)"));
			}
			UE_LOG(LogVoxelLab, Log, TEXT("%d training dummy(ies)"), Dummies.Num());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAttackDummy(TEXT("vl.AttackDummy"),
		TEXT("vl.AttackDummy <who> [N] [run]: order them to attack training dummy N of vl.Dummies (default: the one nearest them), as a left click on it does. who: selection | all | troops | swordsmen | archers | a name (Swordsman_2)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* Command = UVLCommand::Get(World);
			if (!Command || Args.Num() < 1)
			{
				return;
			}
			const FString& Who = Args[0];
			TArray<AVLKing*> Units;
			if (Who.Equals(TEXT("selection"), ESearchCase::IgnoreCase) || Who.Equals(TEXT("sel"), ESearchCase::IgnoreCase))
			{
				Command->GetSelection(Units);
			}
			else
			{
				const FString Name = Who.Replace(TEXT("_"), TEXT(" "));
				for (TActorIterator<AVLKing> It(World); It; ++It)
				{
					if (Who.Equals(TEXT("all"), ESearchCase::IgnoreCase)
						|| (Who.Equals(TEXT("troops"), ESearchCase::IgnoreCase) && It->IsTroop())
						|| (Who.Equals(TEXT("archers"), ESearchCase::IgnoreCase) && It->GetKind() == TEXT("Archer"))
						|| (Who.Equals(TEXT("swordsmen"), ESearchCase::IgnoreCase) && It->GetKind() == TEXT("Swordsman"))
						|| It->GetDisplayName().Equals(Name, ESearchCase::IgnoreCase))
					{
						Units.Add(*It);
					}
				}
			}
			TArray<AActor*> Dummies;
			Command->GetDummies(Dummies);
			if (Units.Num() == 0 || Dummies.Num() == 0)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("attack: %d unit(s), %d dummy(ies): nothing to do"), Units.Num(), Dummies.Num());
				return;
			}
			AActor* Dummy = nullptr;
			if (Args.Num() > 1 && Args[1].IsNumeric())
			{
				Dummy = Dummies[FMath::Clamp(FCString::Atoi(*Args[1]) - 1, 0, Dummies.Num() - 1)];
			}
			else
			{
				const FVector From = Units[0]->GetActorLocation();
				Dummy = Dummies[0];
				for (AActor* D : Dummies)
				{
					if (FVector::DistSquared(D->GetActorLocation(), From) < FVector::DistSquared(Dummy->GetActorLocation(), From))
					{
						Dummy = D;
					}
				}
			}
			const int32 Ordered = Command->OrderAttack(Units, Dummy, Args.Last().Equals(TEXT("run"), ESearchCase::IgnoreCase));
			UE_LOG(LogVoxelLab, Log, TEXT("attack order: %d of %d unit(s) on %s"), Ordered, Units.Num(), *Dummy->GetName());
		}));
}
