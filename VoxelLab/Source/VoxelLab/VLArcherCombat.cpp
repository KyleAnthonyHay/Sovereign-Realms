#include "VLArcherCombat.h"
#include "VoxelLab.h"
#include "VLArrow.h"
#include "VLCharacterData.h"
#include "VLCommand.h"
#include "VLGrid.h"
#include "VLHUD.h"
#include "VLKing.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"

namespace
{
	bool ArcherLogOn()
	{
		static const IConsoleVariable* Log = IConsoleManager::Get().FindConsoleVariable(TEXT("vl.ArcherLog"));
		return Log && Log->GetInt() != 0;
	}

	float ArcherSmooth(float T)
	{
		T = FMath::Clamp(T, 0.f, 1.f);
		return T * T * (3.f - 2.f * T);
	}

	/** Axes for a bow: Z along it, X towards its string (made square to Z). Two of these give the turn between them. */
	FQuat ArcherFrame(const FVector& Along, const FVector& ToString)
	{
		return FRotationMatrix::MakeFromZX(Along, ToString).ToQuat();
	}

	/** An arm of two rigid pieces from the shoulder: the turns (world) of the upper arm and of the forearm that bring
	 *  the end of the forearm (the fist) to Target, as near as the arm reaches, the elbow out towards Pole.
	 *  Upper / Fore: shoulder -> elbow and elbow -> fist in the rest pose, in the frame the arm hangs from (Base). */
	void ArcherSolveArm(const FVector& Shoulder, const FQuat& Base, const FVector& Upper, const FVector& Fore, const FVector& Target, const FVector& Pole,
		FQuat& OutUpper, FQuat& OutFore)
	{
		const float L1 = FMath::Max(Upper.Size(), 1.f), L2 = FMath::Max(Fore.Size(), 1.f);
		const FVector To = Target - Shoulder;
		const float D = FMath::Clamp(float(To.Size()), FMath::Abs(L1 - L2) + 0.5f, L1 + L2 - 0.5f);
		const FVector Dir = To.GetSafeNormal(UE_SMALL_NUMBER, Base.GetForwardVector());
		const float CosA = FMath::Clamp((L1 * L1 + D * D - L2 * L2) / (2.f * L1 * D), -1.f, 1.f);
		const float SinA = FMath::Sqrt(FMath::Max(0.f, 1.f - CosA * CosA));
		const FVector Side = (Pole - Dir * FVector::DotProduct(Pole, Dir)).GetSafeNormal(UE_SMALL_NUMBER, Base.GetRightVector());
		const FVector Elbow = Shoulder + Dir * (L1 * CosA) + Side * (L1 * SinA);
		const FVector Fist = Shoulder + Dir * D;
		OutUpper = FQuat::FindBetweenNormals(Base.RotateVector(Upper / L1), (Elbow - Shoulder).GetSafeNormal()) * Base;
		OutFore = FQuat::FindBetweenNormals(OutUpper.RotateVector(Fore / L2), (Fist - Elbow).GetSafeNormal()) * OutUpper;
	}

	bool ArcherInHands(const AVLKing* Unit)
	{
		return Unit && Unit->IsHeroMode() && Cast<APlayerController>(Unit->GetController()) != nullptr;
	}

	const TCHAR* ArcherPhaseName(int32 Phase)
	{
		static const TCHAR* Names[6] = { TEXT("rest"), TEXT("reach"), TEXT("nock"), TEXT("draw"), TEXT("hold"), TEXT("loose") };
		return Names[FMath::Clamp(Phase, 0, 5)];
	}
}

UVLArcherCombat::UVLArcherCombat()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

bool UVLArcherCombat::CanFight(const AVLKing* Unit)
{
	return Unit && Unit->IsTroop() && Unit->IsRanged();
}

UVLArcherCombat* UVLArcherCombat::For(AVLKing* Unit, bool bCreate)
{
	if (!Unit)
	{
		return nullptr;
	}
	UVLArcherCombat* Combat = Unit->FindComponentByClass<UVLArcherCombat>();
	if (!Combat && bCreate && CanFight(Unit))
	{
		Combat = NewObject<UVLArcherCombat>(Unit, TEXT("ArcherCombat"));
		Combat->RegisterComponent();
		Combat->AddTickPrerequisiteActor(Unit);     // the figure is posed first (AVLKing::Animate), then the bow arm
	}
	return Combat;
}

int32 UVLArcherCombat::OrderAttack(const TArray<AVLKing*>& Units, AActor* InTarget, bool bRun)
{
	int32 Ordered = 0;
	for (AVLKing* U : Units)
	{
		if (!InTarget || !CanFight(U) || ArcherInHands(U))
		{
			continue;
		}
		if (UVLArcherCombat* Combat = For(U))
		{
			Combat->Begin(InTarget, bRun);
			++Ordered;
		}
	}
	return Ordered;
}

int32 UVLArcherCombat::OrderAttackGround(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun)
{
	int32 Ordered = 0;
	for (AVLKing* U : Units)
	{
		if (!CanFight(U) || ArcherInHands(U))
		{
			continue;
		}
		if (UVLArcherCombat* Combat = For(U))
		{
			Combat->BeginGround(Ground, Combat->GroundShots, bRun);
			++Ordered;
		}
	}
	return Ordered;
}

void UVLArcherCombat::Begin(AActor* InTarget, bool bRun)
{
	Mode = InTarget ? EMode::Actor : EMode::None;
	Target = InTarget;
	ShotsLeft = -1;
	ShotScatter = FVector::ZeroVector;
	bOrderRun = bRun;
	bEngaged = false;
	bApproaching = false;
	Approaches = 0;
}

void UVLArcherCombat::BeginGround(const FVector& Ground, int32 InShots, bool bRun)
{
	Mode = EMode::Ground;
	Target = nullptr;
	GroundTarget = Ground;
	ShotsLeft = FMath::Max(InShots, 1);
	ShotScatter = FVector::ZeroVector;
	bOrderRun = bRun;
	bEngaged = false;
	bApproaching = false;
	Approaches = 0;
}

void UVLArcherCombat::Stop()
{
	if (bInternalOrder || Mode == EMode::None)
	{
		return;
	}
	if (ArcherLogOn())
	{
		const AVLKing* Unit = Cast<AVLKing>(GetOwner());
		UE_LOG(LogVoxelLab, Log, TEXT("%s stops shooting (%d arrows loosed)"), Unit ? *Unit->GetDisplayName() : TEXT("?"), Shots);
	}
	Mode = EMode::None;
	Target = nullptr;
	bEngaged = false;
	bApproaching = false;
}

void UVLArcherCombat::LetDown()
{
	// let the string down: no shot, and the right button does nothing more until it has been let go
	bLocked = false;
	bLetDown = true;
	bWantDraw = false;
	bLooseQueued = false;
}

void UVLArcherCombat::StartBash()
{
	if (Phase != EPhase::Rest || BashTime >= 0.f || bWantDraw || bLooseQueued)
	{
		return;
	}
	BashTime = 0.f;             // a blow with the bow
	bBashLanded = false;
	if (UVLArrows* Arrows = UVLArrows::Get(this))
	{
		if (const AActor* Owner = GetOwner())
		{
			Arrows->PlaySwish(Owner->GetActorLocation() + Owner->GetActorForwardVector() * 60.f);
		}
	}
}

void UVLArcherCombat::LeftButton()
{
	if (bLocked)
	{
		LetDown();                  // a second click on a locked draw: the string comes down, no shot
	}
	else if (bWasHeld || (bWantDraw && Phase != EPhase::Rest))
	{
		bLocked = true;             // the draw stays, whatever the right button does, until the next right press looses it
	}
	else
	{
		StartBash();
	}
}

void UVLArcherCombat::Bash(AVLKing* Unit)
{
	UVLCommand* Command = UVLCommand::Get(Unit);
	UVLArrows* Arrows = UVLArrows::Get(Unit);
	if (!Command || !Arrows)
	{
		return;
	}
	const FVector Me = Unit->GetActorLocation(), Ahead = Unit->GetActorForwardVector();
	TArray<AActor*> Dummies;
	Command->GetDummies(Dummies);
	int32 Struck = 0;
	for (AActor* Dummy : Dummies)
	{
		FVector To = Dummy->GetActorLocation() - Me;
		To.Z = 0.f;
		if (To.Size() <= BashReach && FVector::DotProduct(To.GetSafeNormal(), Ahead) > 0.3f)
		{
			Arrows->BashDummy(Dummy, To, BashWobble, BashDamage, Unit);
			++Struck;
		}
	}
	if (Struck == 0 && ArcherLogOn())
	{
		UE_LOG(LogVoxelLab, Log, TEXT("%s swings the bow at nothing"), *Unit->GetDisplayName());
	}
}

void UVLArcherCombat::Shoot()
{
	if (Phase == EPhase::Rest || (Phase == EPhase::Reach && PhaseTime < 0.12f))
	{
		bQuick = true;              // not drawn (a short click): a quick draw-and-shoot
	}
	bLooseQueued = true;
}

FVector UVLArcherCombat::OrderTarget() const
{
	if (Mode == EMode::Actor && Target.IsValid())
	{
		return Target->GetActorLocation() + FVector(0.f, 0.f, AimHeight);
	}
	return GroundTarget;
}

void UVLArcherCombat::ShowArrow(bool bShow)
{
	if (bShow != bArrowShown && ArrowMesh)
	{
		ArrowMesh->SetVisibility(bShow);
	}
	bArrowShown = bShow;
}

// ------------------------------------------------------------------------------------------------ the rig

bool UVLArcherCombat::Setup(AVLKing* Unit)
{
	if (bBroken)
	{
		return false;
	}
	if (!bSetup)
	{
		Chest = Unit->GetJoint(TEXT("Chest"));
		Head = Unit->GetJoint(TEXT("Head"));
		ArmL = Unit->GetJoint(TEXT("ArmL"));
		ForeL = Unit->GetJoint(TEXT("ForeL"));
		ArmR = Unit->GetJoint(TEXT("ArmR"));
		ForeR = Unit->GetJoint(TEXT("ForeR"));
		HandR = Unit->GetJoint(TEXT("HandR"));
		Bow = Unit->GetJoint(TEXT("Bow"));
		StringU = Unit->GetJoint(TEXT("BowStringU"));
		StringL = Unit->GetJoint(TEXT("BowStringL"));
		ArrowJoint = Unit->GetJoint(TEXT("Arrow"));
		Quiver = Unit->GetJoint(TEXT("Quiver"));
		if (!Chest || !ArmL || !ForeL || !ArmR || !ForeR || !Bow)
		{
			bBroken = true;
			UE_LOG(LogVoxelLab, Warning, TEXT("%s: no bow arm to pose (parts Chest, ArmL, ForeL, ArmR, ForeR, Bow)"), *Unit->GetDisplayName());
			return false;
		}
		bSetup = true;
		if (const UVLCharacterData* Data = Unit->GetCharacterData())
		{
			MeshYaw = Data->MeshYaw;
		}
		const FQuat MeshQ = FRotator(0.f, MeshYaw, 0.f).Quaternion();
		UpperL = ForeL->GetRelativeLocation();
		GripL = Bow->GetRelativeLocation();
		UpperR = ForeR->GetRelativeLocation();
		GripR = (HandR ? HandR->GetRelativeLocation() : FVector::ZeroVector) + (ArrowJoint ? ArrowJoint->GetRelativeLocation() : FVector(0.f, 0.f, -8.f));
		if (StringU && StringL)
		{
			StringEndU = StringU->GetRelativeLocation();
			StringEndL = StringL->GetRelativeLocation();
			StringMid = (StringEndU + StringEndL) * 0.5f;
			BowAxis = (StringEndU - StringEndL).GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
			BowString = (StringMid - BowAxis * FVector::DotProduct(StringMid, BowAxis)).GetSafeNormal(UE_SMALL_NUMBER, FVector::BackwardVector);
			// each half is laid along its joint's own Z, so that the joint can be stretched along it
			const FVector AlongU = (StringMid - StringEndU).GetSafeNormal(), AlongL = (StringMid - StringEndL).GetSafeNormal();
			StringFixU = FQuat::FindBetweenNormals(AlongU, FVector::UpVector);
			StringFixL = FQuat::FindBetweenNormals(AlongL, FVector::UpVector);
			for (int32 Half = 0; Half < 2; ++Half)
			{
				USceneComponent* Joint = Half == 0 ? StringU : StringL;
				const FQuat& Fix = Half == 0 ? StringFixU : StringFixL;
				if (USceneComponent* MeshComponent = Joint->GetNumChildrenComponents() > 0 ? Joint->GetChildComponent(0) : nullptr)
				{
					MeshComponent->SetRelativeRotation(Fix * MeshQ);
				}
				Joint->SetRelativeRotation(Fix.Inverse());
			}
		}
		else
		{
			// an archer imported before the string was its own two parts (SM_Archer.json "bow")
			BowAxis = FVector(0.25882, 0.10097, 0.96063);
			BowString = FVector(-0.13443, -0.98108, 0.13933);
			StringMid = BowString * 26.75f;
			UE_LOG(LogVoxelLab, Warning, TEXT("%s: no BowStringU / BowStringL parts (re-import SM_Archer): the string will not draw"), *Unit->GetDisplayName());
		}
		ArrowMesh = ArrowJoint && ArrowJoint->GetNumChildrenComponents() > 0 ? Cast<UStaticMeshComponent>(ArrowJoint->GetChildComponent(0)) : nullptr;
		bArrowShown = true;
		ShowArrow(false);           // her right hand is empty until she takes an arrow from the quiver
		BuiltCant = -1000.f;
	}
	if (BuiltCant != BowCant)
	{
		// The bow is turned in the fist, about its own length, until its string lies BowCant degrees inside the
		// forearm (towards her body when the forearm points ahead) instead of out to her left as it was modelled.
		BuiltCant = BowCant;
		const FVector ToElbow = (-GripL - BowAxis * FVector::DotProduct(-GripL, BowAxis)).GetSafeNormal(UE_SMALL_NUMBER, FVector::BackwardVector);
		FVector Inside = FVector::CrossProduct(BowAxis, ToElbow);
		if (Inside.Y < 0.f)
		{
			Inside = -Inside;       // her right
		}
		const float C = FMath::DegreesToRadians(BowCant);
		BowStringCanted = (ToElbow * FMath::Cos(C) + Inside * FMath::Sin(C)).GetSafeNormal();
		float Angle = FMath::Atan2(FVector::DotProduct(FVector::CrossProduct(BowString, BowStringCanted), BowAxis), FVector::DotProduct(BowString, BowStringCanted));
		if ((FQuat(BowAxis, Angle).RotateVector(BowString) - BowStringCanted).Size() > 0.05f)
		{
			Angle = -Angle;
		}
		Bow->SetRelativeRotation(FQuat(BowAxis, Angle));
		BowRestFrame = ArcherFrame(BowAxis, BowStringCanted).Inverse();
		UE_LOG(LogVoxelLab, Log, TEXT("%s: bow turned %.0f deg in her fist (string %.0f deg inside the forearm), upper arm %.1f, elbow to grip %.1f, string %.1f cm"),
			*Unit->GetDisplayName(), FMath::RadiansToDegrees(Angle), BowCant, UpperL.Size(), GripL.Size(), (StringEndU - StringEndL).Size());
	}
	return true;
}

// ------------------------------------------------------------------------------------------------ the player's hands

void UVLArcherCombat::TickHands(AVLKing* Unit, float Dt)
{
	APlayerController* PC = Cast<APlayerController>(Unit->GetController());
	const bool bNow = PC && Unit->IsHeroMode();
	UCharacterMovementComponent* Move = Unit->GetCharacterMovement();
	if (bNow != bHands)
	{
		bHands = bNow;
		if (bNow)
		{
			Stop();                 // the player's now: no more shooting on orders
			bLetDown = true;        // (a button held as she is taken over is not a draw)
			bWasHeld = false;
			bWasRight = false;
			bLocked = false;
		}
		else
		{
			Unit->bRightMouseAims = false;
			Unit->MoveSpeedCap = 0.f;
			Move->bOrientRotationToMovement = true;
			bWantDraw = false;
			bBattle = false;
			bLooseQueued = false;
			bLocked = false;
			bTestDraw = false;
			bWasHeld = false;
			bWasRight = false;
			BashTime = -1.f;
			TestAimTime = 0.f;
			if (Mode == EMode::None)
			{
				bHasAim = false;
			}
		}
	}
	if (!bNow)
	{
		return;
	}
	Unit->bRightMouseAims = true;       // the right button draws the bow: it does not turn the camera
	const AVLHUD* HUD = Cast<AVLHUD>(PC->GetHUD());
	const bool bMenu = HUD && HUD->bMenu;
	// The right button (the right trigger): held, it draws; let go, she looses. The left button (the left shoulder)
	// while it is held LOCKS the draw: she stays drawn with the right button let go, and the next right press looses.
	// The left button on a locked draw lets the string down; with no draw at all it is a blow with the bow.
	const bool bRight = bTestDraw || (!bMenu && (PC->IsInputKeyDown(EKeys::RightMouseButton) || PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) > 0.4f));
	const bool bRightPressed = bRight && !bWasRight;
	bWasRight = bRight;
	if (bMenu)
	{
		LetDown();                  // the menu: the string comes down, locked or not
	}
	else
	{
		if (bLocked && bRightPressed)
		{
			Shoot();                // the locked draw is loosed; this press draws nothing more
			bLocked = false;
			bLetDown = true;
		}
		else if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) || PC->WasInputKeyJustPressed(EKeys::Gamepad_LeftShoulder))
		{
			LeftButton();
		}
	}
	const bool bHeld = bRight && !bLetDown && BashTime < 0.f;
	if (bWasHeld && !bHeld && !bLetDown && !bLocked)
	{
		Shoot();                    // let go: loose (finishing the draw first, if need be)
	}
	bWantDraw = bHeld || bLocked;
	bWasHeld = bHeld;
	if (!bRight)
	{
		bLetDown = false;
	}

	// Where she aims: where the crosshair's ray meets the world AHEAD of her (AVLKing::GetAimPoint: nothing between
	// the camera and her catches it, nor units, nor the leaves the camera cuts away; nothing ahead: along the
	// crosshair), or with the pointer shown what the pointer is over.
	const FVector Me = Unit->GetActorLocation();
	FVector Point = FVector::ZeroVector;
	bool bFound = false;
	if (TestAimTime > 0.f)
	{
		TestAimTime -= Dt;
		Point = TestAim;
		bFound = true;
	}
	else
	{
		bFound = Unit->GetAimPoint(PC, Point, SkyAimDistance);
	}
	if (bFound)
	{
		FVector Flat(Point.X - Me.X, Point.Y - Me.Y, 0.f);
		const float Dist = Flat.Size();
		if (Dist < 200.f)
		{
			// too near to turn to sensibly: the same way, a little further off
			Flat = Dist > 5.f ? Flat / Dist : Unit->GetActorForwardVector();
			Point = FVector(Me.X + Flat.X * 200.f, Me.Y + Flat.Y * 200.f, Point.Z);
		}
		AimPoint = Point;
		bHasAim = true;
	}
	if (BashTime >= 0.f)
	{
		BashTime += Dt;
		if (!bBashLanded && BashTime >= BashSeconds * 0.45f)
		{
			bBashLanded = true;
			Bash(Unit);
		}
		if (BashTime >= BashSeconds)
		{
			BashTime = -1.f;
		}
	}
	bBattle = bWantDraw || Phase != EPhase::Rest;
	Unit->MoveSpeedCap = bBattle ? Unit->WalkSpeed * DrawMoveScale : 0.f;
	Move->bOrientRotationToMovement = !bBattle;        // she faces her aim, and strafes
}

// ------------------------------------------------------------------------------------------------ orders

void UVLArcherCombat::Approach(AVLKing* Unit, const FVector& At)
{
	UVLCommand* Command = UVLCommand::Get(Unit);
	UWorld* World = Unit->GetWorld();
	if (!Command || !World)
	{
		return;
	}
	const FVector Me = Unit->GetFeet();
	const FVector2D Away = (FVector2D(Me) - FVector2D(At)).GetSafeNormal();
	const float Stand = Range * StandAt - FMath::FRandRange(0.f, 150.f);
	// Somewhere at shooting distance, on her side of the target if that will do: ground she can stand on with
	// nothing right in front of the bow. Else round to either side, then nearer.
	UVLGrid* Grid = UVLGrid::Get(Unit);
	if (Grid && !Grid->EnsureBuilt())
	{
		Grid = nullptr;
	}
	static const float Turns[5] = { 0.f, 30.f, -30.f, 60.f, -60.f };
	static const float Nearer[3] = { 1.f, 0.75f, 0.5f };
	const float Top = FMath::Max(Me.Z, At.Z) + 400.f;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(VLArcherStand), false);
	FVector Dest(At.X + Away.X * Stand, At.Y + Away.Y * Stand, Me.Z);
	bool bFound = false;
	for (int32 N = 0; N < 3 && !bFound; ++N)
	{
		for (int32 T = 0; T < 5 && !bFound; ++T)
		{
			const FVector2D Way = Away.GetRotated(Turns[T]) * (Stand * Nearer[N]);
			FVector Spot(At.X + Way.X, At.Y + Way.Y, Me.Z);
			FHitResult Hit;
			// the ground there (from a little above the higher of the two: not a roof)
			if (!World->LineTraceSingleByChannel(Hit, FVector(Spot.X, Spot.Y, Top), FVector(Spot.X, Spot.Y, Top - 4000.f), ECC_Visibility, Params))
			{
				continue;
			}
			Spot.Z = Hit.ImpactPoint.Z;
			if ((Grid && Grid->NodeAt(Spot) == INDEX_NONE) || (Approaches > 0 && FVector::DistSquared2D(Spot, Me) < FMath::Square(150.f)))
			{
				continue;           // not ground to stand on; or where she stands now, which was no good
			}
			if (ClearShot(Unit, Spot + FVector(0.f, 0.f, 150.f), At))
			{
				Dest = Spot;
				bFound = true;
			}
		}
	}
	++Approaches;
	bInternalOrder = true;          // (UVLCommand::OrderMove ends attacks: not this one)
	Command->OrderMove({ Unit }, Dest, bOrderRun, EVLFormation::Line);
	bInternalOrder = false;
	bApproaching = Unit->HasOrder();
	if (ArcherLogOn())
	{
		UE_LOG(LogVoxelLab, Log, TEXT("%s walks into range: to %s, %.0f cm from the target%s"), *Unit->GetDisplayName(), *Dest.ToCompactString(), FVector::Dist2D(Dest, At),
			bFound ? TEXT("") : TEXT(" (no clear place found)"));
	}
}

float UVLArcherCombat::ShotGravity(const FVector& From, const FVector& To) const
{
	return UVLArrows::ArcGravity(float(FVector::Dist2D(From, To)), ArrowSpeed, ArrowGravity, ArcPeak, ArcPeakDistance, ArcGrowth);
}

bool UVLArcherCombat::ClearShot(const AVLKing* Unit, const FVector& From, const FVector& At) const
{
	UWorld* World = Unit->GetWorld();
	FVector Dir;
	UVLArrows::SolveArc(From, At, ArrowSpeed, ShotGravity(From, At), Dir);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(VLArcherClear), true);
	Params.AddIgnoredActor(Unit);
	if (const AActor* Tower = Unit->GarrisonIn.Get())
	{
		Params.AddIgnoredActor(Tower);
	}
	FHitResult Hit;
	const float Far = FMath::Min(700.f, float(FVector::Dist(From, At)) * 0.7f);
	return !World || !World->LineTraceSingleByChannel(Hit, From, From + Dir * Far, ECC_Visibility, Params) || Hit.GetActor() == Target.Get();
}

void UVLArcherCombat::TickOrders(AVLKing* Unit, float Dt)
{
	if (Mode == EMode::None)
	{
		return;
	}
	if (bHands || (Mode == EMode::Actor && !Target.IsValid()))
	{
		Stop();
		return;
	}
	if (Unit->HasOrder())
	{
		if (!bApproaching)
		{
			Stop();                 // sent somewhere else
		}
		return;                     // on her way into range
	}
	bApproaching = false;
	const FVector At = OrderTarget();
	const float Dist = FVector::Dist2D(Unit->GetActorLocation(), At);
	const bool bTower = Unit->IsGarrisoned();
	if (!bEngaged)
	{
		const float Reach = bTower ? TowerRange : Range;
		if (Dist > Reach * 1.06f)
		{
			if (!bTower && Approaches < 2)
			{
				Approach(Unit, At);
				if (bApproaching)
				{
					return;
				}
			}
			// (the furthest she tries from the ground: what the full pull would let an arrow reach, whatever the arc)
			if (bTower || Dist > ArrowSpeed * ArrowSpeed / FMath::Max(ArrowGravity, 1.f) * 0.9f)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("%s cannot shoot that far (%.0f cm%s)"), *Unit->GetDisplayName(), Dist, bTower ? TEXT(", from the tower") : TEXT(""));
				Stop();
				return;
			}
		}
		else if (!bTower && Approaches < 3 && !ClearShot(Unit, Unit->GetActorLocation() + FVector(0.f, 0.f, 55.f), At))
		{
			Approach(Unit, At);     // a wall right in front of her: somewhere with a clear shot
			if (bApproaching)
			{
				return;
			}
		}
		bEngaged = true;
		Cooldown = FMath::FRandRange(0.05f, FMath::Max(FirstShotDelay, 0.06f));
		UE_LOG(LogVoxelLab, Log, TEXT("%s shoots at %s from %.0f cm%s"), *Unit->GetDisplayName(), Mode == EMode::Actor ? *Target->GetName() : *GroundTarget.ToCompactString(), Dist,
			bTower ? TEXT(" (from the tower)") : TEXT(""));
	}
	AimPoint = At + ShotScatter;
	bHasAim = true;
	if (Phase != EPhase::Rest || bLooseQueued)
	{
		return;                     // a shot is on its way
	}
	if (ShotsLeft == 0)
	{
		Stop();                     // an attack-ground order: done
		return;
	}
	Cooldown -= Dt;
	if (Cooldown <= 0.f)
	{
		Cooldown = FMath::Max(ShotInterval, 0.2f) * (1.f + FMath::FRandRange(-ShotJitter, ShotJitter));
		if (ShotsLeft > 0)
		{
			--ShotsLeft;
		}
		if (Mode == EMode::Ground)
		{
			const float Angle = FMath::FRandRange(0.f, 2.f * UE_PI), Far = GroundScatter * FMath::Sqrt(FMath::FRand());
			ShotScatter = FVector(FMath::Cos(Angle) * Far, FMath::Sin(Angle) * Far, 0.f);
			AimPoint = At + ShotScatter;
		}
		bQuick = false;
		bLooseQueued = true;
	}
}

// ------------------------------------------------------------------------------------------------ a shot

void UVLArcherCombat::Loose(AVLKing* Unit)
{
	UVLArrows* Arrows = UVLArrows::Get(Unit);
	if (!Arrows)
	{
		return;
	}
	const FVector Tip = ArrowTip;
	FVector Dir = ArrowWay;
	bool bReach = true;
	// the pull on this arrow: what gives the shallow arc wanted over this distance (the same for the aim and the flight)
	const float Gravity = bHasAim ? ShotGravity(Tip, AimPoint) : ArrowGravity;
	if (bHasAim)
	{
		bReach = UVLArrows::SolveArc(Tip, AimPoint, ArrowSpeed, Gravity, Dir);
	}
	// not every arrow of a volley flies the same. At a spot of the ground a flatter arrow comes in lower, so the same
	// error up or down would carry it further along the ground: less of it, by as much as the arc is flatter.
	const float PitchSpread = bHands ? HeroSpread : SpreadPitch * (Mode == EMode::Ground ? Gravity / FMath::Max(ArrowGravity, 1.f) : 1.f);
	FRotator Way = Dir.Rotation();
	Way.Yaw += FMath::FRandRange(-1.f, 1.f) * (bHands ? HeroSpread : SpreadYaw);
	Way.Pitch += FMath::FRandRange(-1.f, 1.f) * PitchSpread;
	Dir = Way.Vector();
	Arrows->Fire(Unit, Tip, Dir * ArrowSpeed, Gravity, Unit->GarrisonIn.Get(), ArrowDamage);
	++Shots;
	if (ArcherLogOn())
	{
		UE_LOG(LogVoxelLab, Log, TEXT("%s looses arrow %d from %s at %s (%.0f cm off%s): pitch %.1f yaw %.1f, pull %.0f, she faces %.1f"), *Unit->GetDisplayName(), Shots, *Tip.ToCompactString(),
			*AimPoint.ToCompactString(), FVector::Dist2D(Tip, AimPoint), bReach ? TEXT("") : TEXT(", OUT OF REACH"), Way.Pitch, Way.Yaw, Gravity, Unit->GetActorRotation().Yaw);
	}
}

void UVLArcherCombat::TickShot(AVLKing* Unit, float Dt)
{
	const float Scale = bQuick ? FMath::Max(QuickScale, 0.1f) : 1.f;
	const bool bWanted = bWantDraw || bLooseQueued;
	PhaseTime += Dt;
	auto Go = [this](EPhase Next)
	{
		Phase = Next;
		PhaseTime = 0.f;
	};
	// she turns to what she aims at, and the shot is raised to reach it
	const bool bAiming = bHasAim && (bBattle || bEngaged || Phase != EPhase::Rest);
	bool bFacing = true;
	if (bAiming)
	{
		const FVector Me = Unit->GetActorLocation();
		const FVector Flat(AimPoint.X - Me.X, AimPoint.Y - Me.Y, 0.f);
		if (Flat.SizeSquared() > 25.f)
		{
			const float WantYaw = Flat.Rotation().Yaw;
			FRotator Now = Unit->GetActorRotation();
			Now.Yaw = FMath::FixedTurn(Now.Yaw, WantYaw, TurnRate * Dt);
			Unit->SetActorRotation(Now);
			bFacing = FMath::Abs(FMath::FindDeltaAngleDegrees(Now.Yaw, WantYaw)) <= FaceWithin;
		}
		FVector Dir;
		const FVector BowAt = Me + FVector(0.f, 0.f, 45.f);
		UVLArrows::SolveArc(BowAt, AimPoint, ArrowSpeed, ShotGravity(BowAt, AimPoint), Dir);
		const float Pitch = FMath::Clamp(FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(float(Dir.Z), -1.f, 1.f))), -40.f, 50.f);
		AimPitch = FMath::FInterpTo(AimPitch, Pitch, Dt, 10.f);
	}
	else
	{
		AimPitch = FMath::FInterpTo(AimPitch, 0.f, Dt, 6.f);
	}
	const bool bUp = Phase != EPhase::Rest || bWantDraw || bLooseQueued || (Mode != EMode::None && bEngaged);
	AimW = FMath::FInterpConstantTo(AimW, bUp ? 1.f : 0.f, Dt, 1.f / FMath::Max(RaiseSeconds, 0.02f));

	switch (Phase)
	{
	case EPhase::Rest:
		if (bWanted)
		{
			Go(EPhase::Reach);
		}
		else
		{
			bQuick = false;
		}
		break;
	case EPhase::Reach:
		if (!bWanted)
		{
			Go(EPhase::Rest);
		}
		else if (PhaseTime >= ReachSeconds * Scale)
		{
			ShowArrow(true);        // an arrow in her hand (the quiver keeps its own)
			Go(EPhase::Nock);
		}
		break;
	case EPhase::Nock:
		if (!bWanted)
		{
			ShowArrow(false);
			Go(EPhase::Rest);
		}
		else if (PhaseTime >= NockSeconds * Scale && AimW > 0.9f)
		{
			Go(EPhase::Draw);
		}
		break;
	case EPhase::Draw:
		if (!bWanted)
		{
			ShowArrow(false);
			Go(EPhase::Rest);
		}
		else if (PhaseTime >= DrawSeconds * Scale)
		{
			HoldTime = 0.f;
			Go(EPhase::Hold);
		}
		break;
	case EPhase::Hold:
		HoldTime += Dt;
		if (!bWanted)
		{
			ShowArrow(false);       // let down
			Go(EPhase::Rest);
		}
		else if (bLooseQueued && (bFacing || HoldTime > 0.7f))
		{
			bLooseQueued = false;
			Loose(Unit);
			ShowArrow(false);
			Go(EPhase::Loose);
		}
		break;
	case EPhase::Loose:
		if (PhaseTime >= LooseSeconds)
		{
			bQuick = false;
			Go(bWantDraw || bLooseQueued ? EPhase::Reach : EPhase::Rest);
		}
		break;
	}
	const bool bOnArrow = Phase != EPhase::Rest;
	HandW = FMath::FInterpConstantTo(HandW, bOnArrow ? 1.f : 0.f, Dt, bOnArrow ? 1.f / FMath::Max(ReachSeconds * Scale * 0.8f, 0.02f) : 1.f / 0.28f);
}

// ------------------------------------------------------------------------------------------------ the pose

void UVLArcherCombat::Pose(AVLKing* Unit, float Dt)
{
	const FQuat FigQ = Unit->Figure->GetComponentQuat();
	const FVector Up = FigQ.GetUpVector(), Fwd = FigQ.GetForwardVector(), Right = FigQ.GetRightVector();
	const float W = ArcherSmooth(AimW);
	const float Scale = bQuick ? FMath::Max(QuickScale, 0.1f) : 1.f;

	// what the gait gave the bow arm (before it is changed)
	const FRotator Gait = ArmL->GetRelativeRotation();
	const float GaitSwing = FRotator::NormalizeAxis(Gait.Pitch), GaitOut = FRotator::NormalizeAxis(Gait.Roll);

	// ---- a blow with the bow: wound back to her left, swept across her front, and back to the carry
	float BashW = 0.f, BashYaw = 0.f;
	if (BashTime >= 0.f)
	{
		const float U = FMath::Clamp(BashTime / FMath::Max(BashSeconds, 0.05f), 0.f, 1.f);
		BashYaw = U < 0.3f ? FMath::Lerp(0.f, -65.f, ArcherSmooth(U / 0.3f)) : FMath::Lerp(-65.f, 60.f, 1.f - FMath::Square(1.f - FMath::Clamp((U - 0.3f) / 0.3f, 0.f, 1.f)));
		BashW = FMath::Min(ArcherSmooth(U / 0.2f), 1.f - ArcherSmooth((U - 0.7f) / 0.3f));
	}
	// ---- aiming: the chest side on, the head still on the target
	if (W > 0.f || BashW > 0.f)
	{
		Chest->SetWorldRotation(FQuat(Up, FMath::DegreesToRadians(ChestTwist * W + BashYaw * 0.5f * BashW)) * Chest->GetComponentQuat());
	}
	if (W > 0.f)
	{
		if (Head)
		{
			Head->SetWorldRotation(FQuat::Slerp(Head->GetComponentQuat(), FigQ * FRotator(AimPitch * 0.4f, 0.f, 0.f).Quaternion(), W));
		}
	}
	const FQuat ChestQ = Chest->GetComponentQuat();

	// ---- the bow arm. The bow is rigid in the fist, so where the bow is to stand decides the forearm.
	// carried: upright before her left hip, leaning forward a little (more at a run), its string towards her body
	const float Run = FMath::GetMappedRangeValueClamped(FVector2D(Unit->WalkSpeed, FMath::Max(Unit->RunSpeed, Unit->WalkSpeed + 1.f)), FVector2D(0.f, 1.f), float(Unit->GetVelocity().Size2D()));
	const float Lean = FMath::DegreesToRadians(CarryTilt + RunTilt * Run);
	const float In = FMath::DegreesToRadians(CarryStringIn);
	const FQuat ForeCarry = ArcherFrame(Up * FMath::Cos(Lean) + Fwd * FMath::Sin(Lean), -Fwd * FMath::Cos(In) + Right * FMath::Sin(In)) * BowRestFrame;
	const FQuat UpperCarry = ChestQ * FRotator(CarryArmPitch + CarrySwing * GaitSwing, 0.f, CarryArmOut + 0.3f * GaitOut).Quaternion();
	FQuat UpperQ = UpperCarry, ForeQ = ForeCarry;
	const FVector Aim = FigQ.RotateVector(FRotator(AimPitch, 0.f, 0.f).Vector());
	const FVector Cheek = (Head ? Head->GetComponentLocation() : Chest->GetComponentLocation() + Up * 30.f) + FigQ.RotateVector(Anchor);
	if (W > 0.f)
	{
		// aimed: upright in the plane of the shot, the string straight back along it; the grip as far out along the
		// line of the arrow (which passes her cheek) as the upper arm lets the elbow go
		const FVector Along = (Up - Aim * FVector::DotProduct(Up, Aim)).GetSafeNormal(UE_SMALL_NUMBER, Up);
		const FQuat ForeAim = ArcherFrame(Along, -Aim) * BowRestFrame;
		const FVector Shoulder = ArmL->GetComponentLocation();
		const FVector C0 = Cheek - Along * NockAbove - ForeAim.RotateVector(GripL) - Shoulder;
		const float B = FVector::DotProduct(C0, Aim);
		const float Under = B * B - C0.SizeSquared() + UpperL.SizeSquared();
		const float T = -B + (Under > 0.f ? FMath::Sqrt(Under) : 0.f);
		const FVector Elbow = C0 + Aim * T;
		const FQuat UpperAim = FQuat::FindBetweenNormals(ChestQ.RotateVector(UpperL.GetSafeNormal()), Elbow.GetSafeNormal(UE_SMALL_NUMBER, Aim)) * ChestQ;
		UpperQ = FQuat::Slerp(UpperCarry, UpperAim, W);
		ForeQ = FQuat::Slerp(ForeCarry, ForeAim, W);
	}
	if (BashW > 0.f)
	{
		// the bow held out like a staff, level, pointing where the swipe has got to
		const float Yaw = FMath::DegreesToRadians(BashYaw);
		const FVector Out = (Fwd * FMath::Cos(Yaw) + Right * FMath::Sin(Yaw)) * 0.97f + Up * 0.24f;
		UpperQ = FQuat::Slerp(UpperQ, ChestQ * FRotator(58.f, BashYaw * 0.45f, 14.f).Quaternion(), BashW);
		ForeQ = FQuat::Slerp(ForeQ, ArcherFrame(Out, -Up) * BowRestFrame, BashW);
	}
	ArmL->SetWorldRotation(UpperQ);
	ForeL->SetWorldRotation(ForeQ);

	// ---- the bow as it now stands
	const FTransform BowT = Bow->GetComponentTransform();
	const FVector Grip = BowT.GetLocation();
	const FVector Along = BowT.GetRotation().RotateVector(BowAxis);
	const FVector Shot = -BowT.GetRotation().RotateVector(BowString);       // the way an arrow on the string points
	const FVector Brace = BowT.TransformPositionNoScale(StringMid + BowAxis * NockAbove);     // the nocking point, the string at rest
	const FVector Shelf = Grip + Along * NockAbove;                         // where the arrow lies on the bow
	// (drawn no further than the arrow is long: its point stays beyond the bow)
	const float MaxDraw = VLArrowGeom::Length - float(FVector::DotProduct(StringMid, BowString)) - 6.f;
	const float DrawLength = FMath::Clamp(float(FVector::DotProduct(Brace - Cheek, Shot)), 10.f, FMath::Max(MaxDraw, 11.f));
	const FVector Full = Brace - Shot * DrawLength;

	// ---- the string hand
	FVector HandAt = Full;
	bool bStringHeld = false;
	if (HandW > 0.f || Phase != EPhase::Rest)
	{
		const FVector QuiverAt = Quiver ? Quiver->GetComponentTransform().TransformPositionNoScale(QuiverAxis.GetSafeNormal() * (QuiverMouth + GrabAbove))
			: ArmR->GetComponentLocation() - Fwd * 30.f + Up * 8.f;
		const FVector PoleReach = Fwd * 0.3f + Right * 0.8f + Up * 0.6f;
		const FVector PoleDraw = -Fwd * 0.5f + Right * 0.85f + Up * 0.05f;
		FVector Goal = Full, Pole = PoleDraw;
		switch (Phase)
		{
		case EPhase::Reach:
			Goal = QuiverAt;
			Pole = PoleReach;
			break;
		case EPhase::Nock:
		{
			const float U = ArcherSmooth(PhaseTime / FMath::Max(NockSeconds * Scale, 0.01f));
			const FVector Round = (QuiverAt + Brace) * 0.5f + Right * 14.f + Up * 6.f;      // round her head, not through it
			Goal = FMath::Lerp(FMath::Lerp(QuiverAt, Round, U), FMath::Lerp(Round, Brace, U), U);
			Pole = FMath::Lerp(PoleReach, PoleDraw, U);
			break;
		}
		case EPhase::Draw:
			Goal = FMath::Lerp(Brace, Full, ArcherSmooth(PhaseTime / FMath::Max(DrawSeconds * Scale, 0.01f)));
			bStringHeld = true;
			break;
		case EPhase::Hold:
			bStringHeld = true;
			break;
		case EPhase::Loose:
			Goal = Full - Shot * 4.f;       // the hand comes off the string, back past her cheek
			break;
		default:
			break;
		}
		FQuat UpperIK, ForeIK;
		ArcherSolveArm(ArmR->GetComponentLocation(), ChestQ, UpperR, GripR, Goal, Pole, UpperIK, ForeIK);
		const float H = ArcherSmooth(HandW);
		const FQuat UpperNow = ArmR->GetComponentQuat(), ForeNow = ForeR->GetComponentQuat();
		ArmR->SetWorldRotation(FQuat::Slerp(UpperNow, UpperIK, H));
		ForeR->SetWorldRotation(FQuat::Slerp(ForeNow, ForeIK, H));
		HandAt = ForeR->GetComponentTransform().TransformPositionNoScale(GripR);
	}

	// ---- the string: straight between the limbs, or from each limb to the hand that draws it
	if (StringU && StringL && (bStringHeld || bStringDrawn))
	{
		bStringDrawn = bStringHeld;
		const FVector Apex = bStringHeld ? BowT.InverseTransformPositionNoScale(HandAt) : StringMid;
		for (int32 Half = 0; Half < 2; ++Half)
		{
			USceneComponent* Joint = Half == 0 ? StringU : StringL;
			const FVector& End = Half == 0 ? StringEndU : StringEndL;
			const FQuat& Fix = Half == 0 ? StringFixU : StringFixL;
			const FVector Rest = StringMid - End, Now = Apex - End;
			const float RestLength = FMath::Max(float(Rest.Size()), 1.f);
			Joint->SetRelativeRotation(FQuat::FindBetweenNormals(Rest / RestLength, Now.GetSafeNormal(UE_SMALL_NUMBER, Rest / RestLength)) * Fix.Inverse());
			Joint->SetRelativeScale3D(FVector(1.f, 1.f, FMath::Max(float(Now.Size()) / RestLength, 0.05f)));
		}
	}

	// ---- the arrow in her hand: its nock in the fist, turning from the quiver's line to the bow's, then on the string
	if (ArrowJoint && bArrowShown)
	{
		FVector Way = (Shelf - HandAt).GetSafeNormal(UE_SMALL_NUMBER, Shot);
		if (Phase == EPhase::Nock && Quiver)
		{
			const FVector Down = -Quiver->GetComponentQuat().RotateVector(QuiverAxis.GetSafeNormal());
			const float U = ArcherSmooth(PhaseTime / FMath::Max(NockSeconds * Scale * 0.7f, 0.01f));
			Way = FMath::Lerp(Down, Way, U).GetSafeNormal(UE_SMALL_NUMBER, Way);
		}
		ArrowWay = Way;
		ArrowTip = HandAt + Way * VLArrowGeom::Length;
		ArrowJoint->SetWorldLocationAndRotation(HandAt + Way * VLArrowGeom::NockOffset, FQuat::FindBetweenNormals(VLArrowGeom::Dir.GetSafeNormal(), Way));
	}
	else
	{
		ArrowWay = Shot;
		ArrowTip = Brace + Shot * VLArrowGeom::Length;
	}
}

void UVLArcherCombat::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	AVLKing* Unit = Cast<AVLKing>(GetOwner());
	if (!Unit || !Setup(Unit))
	{
		return;
	}
	TickHands(Unit, DeltaTime);
	TickOrders(Unit, DeltaTime);
	Pose(Unit, DeltaTime);          // (as the shot stands: its arrow leaves from where this puts it)
	TickShot(Unit, DeltaTime);
}

FString UVLArcherCombat::Describe() const
{
	const AVLKing* Unit = Cast<AVLKing>(GetOwner());
	if (!Unit || !bSetup)
	{
		return TEXT("(not set up)");
	}
	const FQuat FigQ = Unit->Figure->GetComponentQuat();
	const FTransform BowT = Bow->GetComponentTransform();
	const FVector Along = BowT.GetRotation().RotateVector(BowAxis), StringWay = BowT.GetRotation().RotateVector(BowString);
	const FVector Grip = Unit->GetActorTransform().InverseTransformPositionNoScale(BowT.GetLocation());
	const FVector Hand = ForeR->GetComponentTransform().TransformPositionNoScale(GripR);
	const FVector Brace = BowT.TransformPositionNoScale(StringMid + BowAxis * NockAbove);
	const float Half = Unit->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const FVector At = OrderTarget();
	return FString::Printf(TEXT("%s%s%s, %s%s, aim %.2f hand %.2f pitch %.1f, %d loosed | bow: upright %.2f, string back %.2f right %.2f up %.2f, grip %.0f ahead %.0f right %.0f above her feet, hand to string %.0f cm, string x%.2f"),
		ArcherPhaseName(int32(Phase)), bBattle ? TEXT(" (battle)") : TEXT(""), bHands ? TEXT(" (played)") : TEXT(""),
		Mode == EMode::None ? TEXT("no order") : *FString::Printf(TEXT("%s %.0f cm off, %s"), Mode == EMode::Actor ? TEXT("target") : TEXT("spot"), FVector::Dist2D(Unit->GetActorLocation(), At),
			bEngaged ? TEXT("shooting") : bApproaching ? TEXT("walking in") : TEXT("waiting")),
		Unit->IsGarrisoned() ? TEXT(" on the tower") : TEXT(""), AimW, HandW, AimPitch, Shots,
		FVector::DotProduct(Along, FigQ.GetUpVector()), -FVector::DotProduct(StringWay, FigQ.GetForwardVector()), FVector::DotProduct(StringWay, FigQ.GetRightVector()),
		FVector::DotProduct(StringWay, FigQ.GetUpVector()), Grip.X, Grip.Y, Grip.Z + Half, FVector::Dist(Hand, Brace), StringU ? StringU->GetRelativeScale3D().Z : 1.f);
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	void ArcherFind(UWorld* World, const FString& Who, TArray<AVLKing*>& Out)
	{
		Out.Reset();
		if (!World)
		{
			return;
		}
		if (Who.Equals(TEXT("selection"), ESearchCase::IgnoreCase) || Who.Equals(TEXT("sel"), ESearchCase::IgnoreCase))
		{
			if (UVLCommand* Command = UVLCommand::Get(World))
			{
				Command->GetSelection(Out);
			}
			return;
		}
		const FString Name = Who.Replace(TEXT("_"), TEXT(" "));
		for (TActorIterator<AVLKing> It(World); It; ++It)
		{
			if (Who.Equals(TEXT("all"), ESearchCase::IgnoreCase) || (Who.Equals(TEXT("troops"), ESearchCase::IgnoreCase) && It->IsTroop())
				|| (Who.Equals(TEXT("archers"), ESearchCase::IgnoreCase) && It->IsRanged()) || It->GetDisplayName().Equals(Name, ESearchCase::IgnoreCase))
			{
				Out.Add(*It);
			}
		}
		Out.Sort([](const AVLKing& A, const AVLKing& B) { return A.GetDisplayName() < B.GetDisplayName(); });
	}

	FVector ArcherGround(UWorld* World, float X, float Y)
	{
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(VLArcherGround), false);
		const FVector Top(X, Y, 6000.f);
		return World && World->LineTraceSingleByChannel(Hit, Top, Top - FVector(0.f, 0.f, 9000.f), ECC_Visibility, Params) ? Hit.ImpactPoint : FVector(X, Y, 0.f);
	}

	FAutoConsoleCommandWithWorldAndArgs CmdArchers(TEXT("vl.Archers"), TEXT("log every archer: her shot, her order, and how she holds the bow"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			int32 N = 0;
			for (TActorIterator<AVLKing> It(World); It; ++It)
			{
				if (const UVLArcherCombat* Combat = UVLArcherCombat::For(*It, false))
				{
					UE_LOG(LogVoxelLab, Log, TEXT("archer %s at %s yaw %.0f speed %.0f: %s"), *It->GetDisplayName(), *It->GetActorLocation().ToCompactString(), It->GetActorRotation().Yaw,
						It->GetVelocity().Size2D(), *Combat->Describe());
					++N;
				}
			}
			UE_LOG(LogVoxelLab, Log, TEXT("%d archer(s)"), N);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdBow(TEXT("vl.Bow"),
		TEXT("vl.Bow draw 0|1 | shoot | lock | cancel | bash | aim X Y [Z] | off: the archer the player plays: hold / let go of the right button (letting go looses), a short right click, the left button (locks a held draw, lets a locked one down, else a blow with the bow), let the string down, a blow with the bow, aim at a point instead of the crosshair / pointer (for 60 s), back to it"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			UVLArcherCombat* Combat = PC ? UVLArcherCombat::For(Cast<AVLKing>(PC->GetPawn()), false) : nullptr;
			if (!Combat || Args.Num() < 1)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("vl.Bow: the player is not playing an archer (vl.Control Archer_1)"));
				return;
			}
			if (Args[0].Equals(TEXT("cancel"), ESearchCase::IgnoreCase))
			{
				Combat->LetDown();
				Combat->SetTestDraw(false);
			}
			else if (Args[0].Equals(TEXT("bash"), ESearchCase::IgnoreCase))
			{
				Combat->StartBash();
			}
			else if (Args[0].Equals(TEXT("lock"), ESearchCase::IgnoreCase))
			{
				Combat->LeftButton();
			}
			else if (Args[0].Equals(TEXT("draw"), ESearchCase::IgnoreCase))
			{
				Combat->SetTestDraw(Args.Num() < 2 || FCString::Atoi(*Args[1]) != 0);
			}
			else if (Args[0].Equals(TEXT("shoot"), ESearchCase::IgnoreCase))
			{
				Combat->Shoot();
			}
			else if (Args[0].Equals(TEXT("aim"), ESearchCase::IgnoreCase) && Args.Num() >= 3)
			{
				const float X = FCString::Atof(*Args[1]), Y = FCString::Atof(*Args[2]);
				Combat->SetTestAim(Args.Num() >= 4 ? FVector(X, Y, FCString::Atof(*Args[3])) : ArcherGround(World, X, Y), 60.f);
			}
			else
			{
				Combat->SetTestDraw(false);
				Combat->SetTestAim(FVector::ZeroVector, 0.f);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdArmGround(TEXT("vl.ArmGround"), TEXT("as A in the overview: the next left click on the ground (vl.Click U V) is where the selection's archers shoot"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (UVLCommand* Command = UVLCommand::Get(World))
			{
				Command->ArmAttackGround(true);
				UE_LOG(LogVoxelLab, Log, TEXT("attack ground %s"), Command->IsAttackGroundArmed() ? TEXT("armed") : TEXT("not armed (no archers selected)"));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdShootAt(TEXT("vl.ShootAt"),
		TEXT("vl.ShootAt <who> X Y [Z]: an attack-ground order, as A then a left click on the ground gives it. who: selection | all | troops | archers | a name (Archer_2)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLCommand* Command = UVLCommand::Get(World);
			if (!Command || Args.Num() < 3)
			{
				return;
			}
			TArray<AVLKing*> Units;
			ArcherFind(World, Args[0], Units);
			const float X = FCString::Atof(*Args[1]), Y = FCString::Atof(*Args[2]);
			const FVector Ground = Args.Num() >= 4 ? FVector(X, Y, FCString::Atof(*Args[3])) : ArcherGround(World, X, Y);
			const int32 Ordered = Command->OrderAttackGround(Units, Ground, false);
			UE_LOG(LogVoxelLab, Log, TEXT("attack ground: %d of %d unit(s) shoot at %s"), Ordered, Units.Num(), *Ground.ToCompactString());
		}));
}
