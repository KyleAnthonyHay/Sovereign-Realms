// The farms' hands (see VLFarmer.h). Spawned and sent away by UVLConstruction::TickFarmhands.
#include "VLFarmer.h"
#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLCharacterData.h"
#include "VLGrid.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "HAL/IConsoleManager.h"

bool AVLFarmer::bEnabled = true;

namespace
{
	float FarmSmooth(float X)
	{
		X = FMath::Clamp(X, 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}

	FAutoConsoleCommandWithWorldAndArgs CmdFarmhands(TEXT("vl.Farmhands"),
		TEXT("vl.Farmhands: log every farm's hands (where, what they are doing); vl.Farmhands 0|1: none / one woman and one man at every finished farm"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (Args.Num() > 0)
			{
				AVLFarmer::bEnabled = FCString::Atoi(*Args[0]) != 0;
				UE_LOG(LogSovereignRealms, Log, TEXT("FARMHANDS %s"), AVLFarmer::bEnabled ? TEXT("on") : TEXT("off"));
				return;
			}
			int32 N = 0;
			for (TActorIterator<AVLFarmer> It(World); It; ++It)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("FARMHAND %s"), *It->Describe());
				++N;
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("FARMHANDS: %d"), N);
		}));
}

AVLFarmer::AVLFarmer()
{
	bAmbient = true;                    // (set before it is spawned: the battle's registry leaves it out)
	bReplicates = false;                // (scenery: each game of a multiplayer match has its own farm hands)
	Team = UVLBattle::Neutral;
	DisplayName = TEXT("Farmer");
	UnitKind = TEXT("FarmerWoman");
}

AVLFarmer* AVLFarmer::Spawn(UWorld* World, const FString& Kind, AActor* InFarm, const FVLFarmSpots& InSpots, const FVector& At)
{
	const TSoftObjectPtr<UVLCharacterData> Data = AVLTroop::DataFor(Kind);
	if (!World || !Data.LoadSynchronous())
	{
		static bool bWarned = false;
		if (!bWarned)
		{
			bWarned = true;
			UE_LOG(LogSovereignRealms, Warning, TEXT("FARMHANDS: no character data for %s (%s)"), *Kind, *Data.ToString());
		}
		return nullptr;
	}
	const float Yaw = (-InSpots.Front).Rotation().Yaw;
	const FTransform T(FRotator(0.f, Yaw, 0.f), At + FVector(0.f, 0.f, 95.f));
	AVLFarmer* F = World->SpawnActorDeferred<AVLFarmer>(AVLFarmer::StaticClass(), T, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
	if (!F)
	{
		return nullptr;
	}
	static int32 Number = 0;
	F->SetCharacterData(Data);
	F->SetKind(Kind);
	F->Team = UVLBattle::Neutral;
	F->bMan = Kind == TEXT("FarmerMan");
	F->SetDisplayName(FString::Printf(TEXT("%s %d"), F->bMan ? TEXT("Farmer Man") : TEXT("Farmer Woman"), ++Number));
	F->Farm = InFarm;
	F->Spots = InSpots;
	F->FinishSpawning(T);
	F->RefreshSilhouette();
	return F;
}

void AVLFarmer::BeginPlay()
{
	Super::BeginPlay();
	WalkSpeed = FarmWalkSpeed;
	RunSpeed = FarmWalkSpeed * 1.6f;
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);     // others pass through it, it through them
	iBody = RigFind(TEXT("Body"));
	iChest = RigFind(TEXT("Chest"));
	iArmL = RigFind(TEXT("ArmL"));
	iForeL = RigFind(TEXT("ForeL"));
	iArmR = RigFind(TEXT("ArmR"));
	iTool = bMan ? RigFind(TEXT("Pitchfork")) : -1;
	// the work, over the gait's pose whenever the figure is posed (the capsule never ticks: the poser is always called)
	AddRigPoser(GetCapsuleComponent(), [this](AVLKing*) { PoseWork(); });
	ThinkClock = FMath::FRandRange(0.f, 0.6f);
}

const TCHAR* AVLFarmer::SpotName(ESpot Spot)
{
	switch (Spot)
	{
	case ESpot::Field: return TEXT("the field");
	case ESpot::Store: return TEXT("the store");
	default: return TEXT("the door");
	}
}

void AVLFarmer::Tick(float DeltaSeconds)
{
	// the turn to its work, before the figure is posed
	if (bTurning && !GetWorld()->IsPaused())
	{
		FRotator R = GetActorRotation();
		const float Left = FMath::FindDeltaAngleDegrees(R.Yaw, WantYaw);
		R.Yaw = FMath::FixedTurn(R.Yaw, WantYaw, 300.f * DeltaSeconds);
		SetActorRotation(FRotator(0.f, R.Yaw, 0.f));
		bTurning = FMath::Abs(Left) > 300.f * DeltaSeconds;
	}
	Super::Tick(DeltaSeconds);
	ThinkClock -= DeltaSeconds;
	if (ThinkClock <= 0.f && !IsDead() && !GetWorld()->IsPaused())
	{
		ThinkClock = 0.2f;
		Think(GetWorld()->GetTimeSeconds());
		UpdateTickRate();
	}
}

void AVLFarmer::UpdateTickRate()
{
	// Out of view, it and its walking tick four times a second; seen far off, ten times; near, every frame. (Its
	// figure is posed only when seen, and less often far off, by AVLKing::RigLate either way.)
	float Interval = 0.f;
	if (!WasRecentlyRendered(0.5f))
	{
		Interval = 0.25f;
	}
	else if (const APlayerController* PC = GetWorld()->GetFirstPlayerController(); PC && PC->PlayerCameraManager
		&& FVector::DistSquared(PC->PlayerCameraManager->GetCameraLocation(), GetActorLocation()) > FMath::Square(FarTickDistance))
	{
		Interval = 0.1f;
	}
	if (Interval != GetActorTickInterval())
	{
		SetActorTickInterval(Interval);
		GetCharacterMovement()->SetComponentTickInterval(Interval);
	}
}

void AVLFarmer::Think(double Now)
{
	switch (Step)
	{
	case EStep::Start:
		GoTo(Spots.Field.Num() > 0 ? ESpot::Field : ESpot::Store);
		break;
	case EStep::Walk:
		if (!HasOrder())
		{
			Arrive(Now);            // (arrived, or gave up on the way: it works where it got to)
		}
		break;
	default:
		if (Now >= StepEnd)
		{
			if (bWorking)
			{
				bWorking = false;
				WorkStop = Now;
			}
			// the next spot: mostly along the rows; the woman now and then to the store with her basket, or to the
			// door; the man between the rows and the store, now and then to the door
			const float R = FMath::FRand();
			ESpot Next = ESpot::Field;
			if (Where == ESpot::Field)
			{
				Next = bMan ? (R < 0.4f ? ESpot::Field : (R < 0.8f ? ESpot::Store : ESpot::Door)) : (R < 0.62f ? ESpot::Field : (R < 0.84f ? ESpot::Store : ESpot::Door));
			}
			else if (Where == ESpot::Store)
			{
				Next = bMan && R > 0.7f ? ESpot::Door : ESpot::Field;
			}
			else
			{
				Next = bMan && R < 0.35f ? ESpot::Store : ESpot::Field;
			}
			if (Next == ESpot::Field && Spots.Field.Num() == 0)
			{
				Next = Where == ESpot::Store ? ESpot::Door : ESpot::Store;
			}
			GoTo(Next);
		}
		break;
	}
}

void AVLFarmer::GoTo(ESpot Spot)
{
	Where = Spot;
	bTurning = false;
	if (Spot == ESpot::Field)
	{
		// along the rows: one of the three spots nearest the last most of the time, anywhere in the field otherwise
		int32 Pick = FMath::RandRange(0, Spots.Field.Num() - 1);
		if (FieldAt != INDEX_NONE && Spots.Field.Num() > 3 && FMath::FRand() < 0.7f)
		{
			TArray<int32> Order;
			for (int32 i = 0; i < Spots.Field.Num(); ++i)
			{
				if (i != FieldAt)
				{
					Order.Add(i);
				}
			}
			const FVector From = Spots.Field[FieldAt];
			Order.Sort([this, &From](int32 A, int32 B) { return FVector::DistSquared2D(Spots.Field[A], From) < FVector::DistSquared2D(Spots.Field[B], From); });
			Pick = Order[FMath::RandRange(0, FMath::Min(2, Order.Num() - 1))];
		}
		else if (Pick == FieldAt && Spots.Field.Num() > 1)
		{
			Pick = (Pick + 1) % Spots.Field.Num();
		}
		FieldAt = Pick;
		Target = Spots.Field[Pick];
	}
	else
	{
		Target = Spot == ESpot::Store ? Spots.Store : Spots.Door;
	}
	TArray<FVector> Path;
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!(Grid && Grid->IsBuilt() && Grid->FindPath(GetFeet(), Target, Path) && Path.Num() > 0))
	{
		Path = { Target };
	}
	else if (FVector::DistSquared2D(Path.Last(), Target) > 1.f)
	{
		Path.Add(Target);
	}
	FollowPath(Path, false);
	Step = EStep::Walk;
	++Walked;
	UE_LOG(LogSovereignRealms, Verbose, TEXT("FARMHAND %s walks to %s (%.0f cm, %d corners)"), *DisplayName, SpotName(Spot), FVector::Dist2D(GetFeet(), Target), Path.Num());
}

void AVLFarmer::Arrive(double Now)
{
	// which way it faces: the crop (the middle of the field, or along the row from the field's middle), the house
	// (the store and the door are against its front wall)
	FVector Face = -Spots.Front;
	if (Where == ESpot::Field)
	{
		Face = Spots.FieldCentre - GetFeet();
		if (Face.SizeSquared2D() < FMath::Square(150.f))
		{
			Face = Spots.Front;
		}
	}
	WantYaw = Face.Rotation().Yaw + (Where == ESpot::Field ? FMath::FRandRange(-35.f, 35.f) : 0.f);
	bTurning = true;
	const bool bWork = Where == ESpot::Field || (bMan && Where == ESpot::Store);
	if (bWork)
	{
		Step = EStep::Work;
		bWorking = true;
		WorkStart = Now + 0.25;      // (once it has half turned to the work)
		WorkRate = FMath::FRandRange(0.9f, 1.1f);
		StepEnd = Now + FMath::FRandRange(WorkSeconds.X, WorkSeconds.Y);
		++Worked;
		UE_LOG(LogSovereignRealms, Verbose, TEXT("FARMHAND %s works at %s (%s; %.0f cm from the spot)"), *DisplayName, SpotName(Where), bMan ? TEXT("raking") : TEXT("cutting with the sickle"),
			FVector::Dist2D(GetFeet(), Target));
	}
	else
	{
		Step = EStep::Rest;
		StepEnd = Now + FMath::FRandRange(RestSeconds.X, RestSeconds.Y);
		UE_LOG(LogSovereignRealms, Verbose, TEXT("FARMHAND %s stops at %s"), *DisplayName, SpotName(Where));
	}
}

void AVLFarmer::PoseWork()
{
	const UWorld* World = GetWorld();
	if (!World || iChest < 0 || iArmL < 0)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	const float H = bWorking ? FarmSmooth(float(Now - WorkStart) / 0.45f) : 1.f - FarmSmooth(float(Now - WorkStop) / 0.35f);
	if (H <= 0.f)
	{
		return;
	}
	const float T = FMath::Max(0.f, float(Now - WorkStart)) * WorkRate;
	float Waist = 0.f, Bend = 0.f, Raise = 0.f, Sweep = 0.f, RaiseR = 0.f, Lift = 0.f;
	if (!bMan)
	{
		// the sickle: bent over the row, a quick cut from out on her left across to her right, the hand brought back
		const float Cycle = FMath::Fmod(T, 1.2f) / 1.2f;
		const float Cut = Cycle < 0.3f ? FarmSmooth(Cycle / 0.3f) : 1.f - FarmSmooth((Cycle - 0.3f) / 0.7f);
		Waist = 14.f;
		Bend = 28.f + 4.f * Cut;
		Raise = 48.f + 14.f * Cut;
		Sweep = -32.f + 66.f * Cut;
	}
	else
	{
		// the rake (his long tool, the "Pitchfork" part): a lift and a reach forward, then three short pulls back
		// toward his feet with the tines along the ground, a little lean into each; and again
		const float Cycle = FMath::Fmod(T, RakeCycle);
		const float ReachFar = 42.f, ReachNear = 6.f;
		float Pull = 0.f;               // how far into a pull (0..1, for the lean)
		if (Cycle < RakeReach)
		{
			const float S = Cycle / RakeReach;
			Raise = FMath::Lerp(ReachNear, ReachFar, FarmSmooth(S));
			Lift = 16.f * FMath::Sin(PI * S);
		}
		else
		{
			const float Stroke = (RakeCycle - RakeReach) / 3.f;
			const float InPulls = Cycle - RakeReach;
			const int32 K = FMath::Min(2, int32(InPulls / Stroke));
			const float S = (InPulls - K * Stroke) / Stroke;
			const float Drag = FarmSmooth(S / 0.6f);        // the pull, then the hands stop a moment
			const float From = FMath::Lerp(ReachFar, ReachNear, K / 3.f), To = FMath::Lerp(ReachFar, ReachNear, (K + 1) / 3.f);
			Raise = FMath::Lerp(From, To, Drag);
			Pull = S < 0.6f ? FMath::Sin(PI * S / 0.6f) : 0.f;
		}
		Waist = 12.f + 4.f * Pull;
		Bend = 10.f + 6.f * Pull + 0.15f * Raise;
		Sweep = 6.f;
		RaiseR = 12.f + 0.6f * Raise;  // (the other hand comes forward too, as if on the shaft)
	}
	// world turns about the figure's own axes (forward X, right Y, up Z): +about the right tips the top forward, so an
	// arm is raised forward by a turn the other way; +about the up swings forward toward the right
	const FQuat A = GetActorQuat();
	const FVector Right = A.GetRightVector(), Up = A.GetUpVector(), Fwd = A.GetForwardVector();
	const FQuat WaistQ(Right, FMath::DegreesToRadians(Waist * H));
	if (iBody >= 0)
	{
		RigSetWorldRot(iBody, WaistQ * RigWorldRot(iBody));
	}
	const FQuat BendQ(Right, FMath::DegreesToRadians(Bend * H));
	RigSetWorldRot(iChest, BendQ * RigWorldRot(iChest));
	const FVector ChestUp = (BendQ * WaistQ).RotateVector(Up);
	const FQuat ArmQ = FQuat(ChestUp, FMath::DegreesToRadians(Sweep * H)) * FQuat(Right, FMath::DegreesToRadians(-Raise * H));
	RigSetWorldRot(iArmL, ArmQ * RigWorldRot(iArmL));
	if (bMan && iArmR >= 0)
	{
		RigSetWorldRot(iArmR, FQuat(Right, FMath::DegreesToRadians(-RaiseR * H)) * RigWorldRot(iArmR));
	}
	if (bMan && iTool >= 0)
	{
		// the tool turned about its grip (where it is held) so that its head, ToolReach along the shaft, rests on the
		// ground ahead (lifted by Lift), a little in toward his middle; the tines stay across the way he faces
		const FVector Grip = RigWorldLoc(iTool);
		const float Ground = GetFeet().Z + 4.f + Lift;
		const float Drop = FMath::Clamp(Grip.Z - Ground, 0.f, ToolReach * 0.98f);
		const float Ahead = FMath::Sqrt(FMath::Square(ToolReach) - FMath::Square(Drop));
		const FVector Want = (Fwd * Ahead + Right * (0.22f * Ahead) - Up * Drop).GetSafeNormal();
		const FQuat FigQ = RigWorldRot(RigFigure);
		const FQuat Aimed = FQuat::FindBetweenNormals(FigQ.RotateVector(FVector::UpVector), Want) * FigQ;     // (modelled upright: +Z)
		RigSetWorldRot(iTool, FQuat::Slerp(RigWorldRot(iTool), Aimed, H));
	}
}

FString AVLFarmer::Describe() const
{
	static const TCHAR* Steps[] = { TEXT("starting"), TEXT("walking"), TEXT("working"), TEXT("stopping") };
	FString Tool;
	if (iTool >= 0)
	{
		// (the tool's head: how far above the ground, and ahead of his feet)
		const FVector Tip = RigWorldLoc(iTool) + RigWorldRot(iTool).RotateVector(FVector::UpVector) * ToolReach;
		Tool = FString::Printf(TEXT("; tool head %.0f cm above the ground, %.0f cm ahead"), Tip.Z - GetFeet().Z, FVector::DotProduct(Tip - GetFeet(), GetActorForwardVector()));
	}
	return FString::Printf(TEXT("%s of %s: %s %s at %s (speed %.0f, %d walks, %d bouts of work, ticks every %.2f s%s)"), *DisplayName, Farm.IsValid() ? *Farm->GetName() : TEXT("-"),
		Steps[int32(Step)], Step == EStep::Walk ? *(FString(TEXT("to ")) + SpotName(Where)) : *(FString(TEXT("at ")) + SpotName(Where)),
		*GetFeet().ToCompactString(), GetVelocity().Size2D(), Walked, Worked, GetActorTickInterval(), *Tool);
}
