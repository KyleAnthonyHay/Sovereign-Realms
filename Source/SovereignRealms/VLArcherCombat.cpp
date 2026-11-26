#include "VLArcherCombat.h"
#include "VLBattle.h"
#include "SovereignRealms.h"
#include "VLArrow.h"
#include "VLCharacterData.h"
#include "VLCommand.h"
#include "VLGrid.h"
#include "VLHUD.h"
#include "VLKing.h"
#include "VLSwordsmanCombat.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "HAL/IConsoleManager.h"

namespace
{
	/** Alt / Option, Ctrl or Cmd held: a left click is a command to the selection, not the bow's. */
	bool CommandModifier(const APlayerController* PC)
	{
		return PC->IsInputKeyDown(EKeys::LeftAlt) || PC->IsInputKeyDown(EKeys::RightAlt) || PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl)
			|| PC->IsInputKeyDown(EKeys::LeftCommand) || PC->IsInputKeyDown(EKeys::RightCommand);
	}
}

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
	// (B: the unit remembers its component, and that it has been looked for: no component search per call)
	UVLArcherCombat* Combat = Unit->BowCombat;
	if (!Combat && !(Unit->CompLooked & 2))
	{
		Combat = Unit->FindComponentByClass<UVLArcherCombat>();
		Unit->BowCombat = Combat;
		Unit->CompLooked |= 2;
	}
	if (!Combat && bCreate && CanFight(Unit))
	{
		Combat = NewObject<UVLArcherCombat>(Unit, TEXT("ArcherCombat"));
		Combat->RegisterComponent();
		Combat->AddTickPrerequisiteActor(Unit);     // the figure is posed first (AVLKing::Animate), then the bow arm
		Unit->BowCombat = Combat;
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
			// An attack takes the place of the walk she is on (as a swordsman's does: its route to the foe replaces
			// it). Left walking, TickOrders took the walk for another order and dropped the attack, every quarter of
			// a second: an archer on an attack-move walked on to its end before she shot. (Not one on her way up a
			// tower: that walk is the tower's.)
			if (U->HasOrder() && !U->IsGarrisoned() && !U->PendingGarrison.IsValid())
			{
				U->StopOrder();
			}
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
	SetComponentTickEnabled(true);      // (it rests, unticked, while there is nothing for it to do: TickComponent)
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
	SetComponentTickEnabled(true);
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
		UE_LOG(LogSovereignRealms, Log, TEXT("%s stops shooting (%d arrows loosed)"), Unit ? *Unit->GetDisplayName() : TEXT("?"), Shots);
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
	SetComponentTickEnabled(true);
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
	SetComponentTickEnabled(true);
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
	// a foe in front of her takes the blow
	if (UVLBattle* Battle = UVLBattle::Get(Unit))
	{
		FVLUnits Near;
		Battle->UnitsNear(Me, BashReach, Near);
		for (AVLKing* Other : Near)
		{
			FVector To = Other->GetActorLocation() - Me;
			To.Z = 0.f;
			if (Battle->IsHostile(Other, Unit->Team) && To.Size() <= BashReach && FVector::DotProduct(To.GetSafeNormal(), Ahead) > 0.3f)
			{
				Battle->Damage(Other, BashDamage, Unit, Unit->Team);
				++Struck;
				break;
			}
		}
	}
	if (Struck == 0 && ArcherLogOn())
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("%s swings the bow at nothing"), *Unit->GetDisplayName());
	}
}

void UVLArcherCombat::Shoot()
{
	if (Phase == EPhase::Rest || (Phase == EPhase::Reach && PhaseTime < 0.12f))
	{
		bQuick = true;              // not drawn (a short click): a quick draw-and-shoot
	}
	bLooseQueued = true;
	SetComponentTickEnabled(true);
}

bool UVLArcherCombat::GetDrawState(float& OutDrawn, bool& bOutReady) const
{
	OutDrawn = 0.f;
	bOutReady = false;
	if (!bHands || Phase == EPhase::Rest || Phase == EPhase::Loose)
	{
		return false;
	}
	// (the same lengths TickShot steps the shot by)
	const float Scale = bQuick ? FMath::Max(QuickScale, 0.1f) : 1.f;
	const float Reach = ReachSeconds * Scale, Nock = NockSeconds * Scale, Draw = DrawSeconds * Scale;
	const float Total = FMath::Max(Reach + Nock + Draw, 0.01f);
	float Done = Total;
	switch (Phase)
	{
	case EPhase::Reach: Done = FMath::Min(PhaseTime, Reach); break;
	case EPhase::Nock: Done = Reach + FMath::Min(PhaseTime, Nock); break;      // (it waits here until the bow arm is up)
	case EPhase::Draw: Done = Reach + Nock + FMath::Min(PhaseTime, Draw); break;
	default: break;
	}
	bOutReady = Phase == EPhase::Hold;
	OutDrawn = bOutReady ? 1.f : FMath::Clamp(Done / Total, 0.f, 0.99f);
	return true;
}

FVector UVLArcherCombat::OrderTarget() const
{
	if (Mode == EMode::Actor && Target.IsValid())
	{
		const UVLBattle* Battle = UVLBattle::Get(this);
		const AActor* Owner = GetOwner();
		if (Battle && Owner && (Cast<AVLKing>(Target.Get()) || Battle->FindBuilding(Target.Get())))
		{
			// a foe's chest (where it will be when the arrow gets there) or a point of a building's wall facing her
			FVector At = Battle->AimPoint(Target.Get(), Owner->GetActorLocation());
			At += Target->GetVelocity() * (FVector::Dist(Owner->GetActorLocation(), At) / FMath::Max(ArrowSpeed, 100.f));
			return At;
		}
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
		iChest = Unit->RigFind(TEXT("Chest"));
		iHead = Unit->RigFind(TEXT("Head"));
		iArmL = Unit->RigFind(TEXT("ArmL"));
		iForeL = Unit->RigFind(TEXT("ForeL"));
		iArmR = Unit->RigFind(TEXT("ArmR"));
		iForeR = Unit->RigFind(TEXT("ForeR"));
		iHandR = Unit->RigFind(TEXT("HandR"));
		iBow = Unit->RigFind(TEXT("Bow"));
		iStringU = Unit->RigFind(TEXT("BowStringU"));
		iStringL = Unit->RigFind(TEXT("BowStringL"));
		iArrow = Unit->RigFind(TEXT("Arrow"));
		iQuiver = Unit->RigFind(TEXT("Quiver"));
		if (!Chest || !ArmL || !ForeL || !ArmR || !ForeR || !Bow)
		{
			bBroken = true;
			UE_LOG(LogSovereignRealms, Warning, TEXT("%s: no bow arm to pose (parts Chest, ArmL, ForeL, ArmR, ForeR, Bow)"), *Unit->GetDisplayName());
			return false;
		}
		bSetup = true;
		// (when the unit is posed outside its Tick, or this component rests, the unit asks for the bow arm's pose)
		Unit->AddRigPoser(this, [this](AVLKing* Posed)
		{
			if (bSetup && !bBroken)
			{
				Pose(Posed, 0.f);
			}
		});
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
				const int32 Joint = Half == 0 ? iStringU : iStringL;
				const FQuat& Fix = Half == 0 ? StringFixU : StringFixL;
				Unit->RigSetMeshRot(Joint, Fix * MeshQ);
				Unit->RigSetRelRot(Joint, Fix.Inverse());
			}
		}
		else
		{
			// an archer imported before the string was its own two parts (SM_Archer.json "bow")
			BowAxis = FVector(0.25882, 0.10097, 0.96063);
			BowString = FVector(-0.13443, -0.98108, 0.13933);
			StringMid = BowString * 26.75f;
			UE_LOG(LogSovereignRealms, Warning, TEXT("%s: no BowStringU / BowStringL parts (re-import SM_Archer): the string will not draw"), *Unit->GetDisplayName());
		}
		ArrowMesh = Unit->RigMesh(iArrow);
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
		Unit->RigSetRelRot(iBow, FQuat(BowAxis, Angle));
		BowRestFrame = ArcherFrame(BowAxis, BowStringCanted).Inverse();
		UE_LOG(LogSovereignRealms, Log, TEXT("%s: bow turned %.0f deg in her fist (string %.0f deg inside the forearm), upper arm %.1f, elbow to grip %.1f, string %.1f cm"),
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
	// THE SPY'S BOW (its weak one, AVLTroop::BeginPlay): its right button is its spyglass (UVLSpy, which owns the right
	// button then), so its bow is the left button: a click is a quick draw and shot at the crosshair
	const bool bSpy = Unit->KindId() == EVLUnitKind::Spy;
	if (!bSpy)
	{
		Unit->bRightMouseAims = true;   // the right button draws the bow: it does not turn the camera
	}
	if (TestLookTime > 0.f)
	{
		// (vl.Bow look) the hero camera turned until the crosshair's ray passes through the point, as the mouse would
		TestLookTime -= Dt;
		FVector O, D;
		if (Unit->IsMouseLooking() && Unit->GetAimRay(PC, O, D))
		{
			const FRotator Have = D.Rotation(), Want = (TestLook - O).Rotation(), Ctrl = PC->GetControlRotation();
			Unit->LookPitch = 0.f;
			Unit->SetOrbit(Ctrl.Yaw + FMath::FindDeltaAngleDegrees(Have.Yaw, Want.Yaw),
				FRotator::NormalizeAxis(Ctrl.Pitch) + FMath::FindDeltaAngleDegrees(Have.Pitch, Want.Pitch), Unit->Boom ? Unit->Boom->TargetArmLength : 1500.f);
		}
	}
	const AVLHUD* HUD = Cast<AVLHUD>(PC->GetHUD());
	const bool bMenu = HUD && HUD->bMenu;
	const bool bCmd = Unit->IsCommandMode();       // (command mode: the right button orders, so no draw; the left click is still hers)
	// The right button (the right trigger): held, it draws; let go, she looses. The left button (the left shoulder)
	// while it is held LOCKS the draw: she stays drawn with the right button let go, and the next right press looses.
	// The left button on a locked draw lets the string down; with no draw at all it is a blow with the bow.
	const bool bRight = bTestDraw || (!bSpy && !bMenu && !bCmd && (PC->IsInputKeyDown(EKeys::RightMouseButton) || PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) > 0.4f));
	const bool bRightPressed = bRight && !bWasRight;
	bWasRight = bRight;
	if (bMenu || (bCmd && bLocked))
	{
		LetDown();                  // the menu (or command mode with a locked draw): the string comes down
	}
	else
	{
		if (bLocked && bRightPressed)
		{
			Shoot();                // the locked draw is loosed; this press draws nothing more
			bLocked = false;
			bLetDown = true;
		}
		else if ((PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) && !CommandModifier(PC) && !Unit->HeroClickTaken()) || PC->WasInputKeyJustPressed(EKeys::Gamepad_LeftShoulder))
		{
			if (!bSpy)
			{
				LeftButton();       // (a click that selected or ordered, AVLKing::HeroCommands, is not the bow's)
			}
			else if (Phase == EPhase::Rest && BashTime < 0.f)
			{
				Shoot();            // (the Spy: a quick shot)
			}
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
	const float Stand = Range * StandAt - FMath::FRandRange(0.f, 200.f);       // (2810-2610 cm with Range 3120)
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
	{
		TGuardValue<bool> Inner(Command->bInnerOrder, true);    // nor a patrol or a guard she is on
		// At a run when it is more than a few steps (UVLSwordsmanCombat::ChargeBeyond, as the swordsmen close with a
		// foe): archers and swordsmen sent at the same foe travel together, and she stops at her range. (She walked
		// unless the order said run, while the swordsmen ran their foe down: the archers fell behind.)
		Command->OrderMove({ Unit }, Dest, bOrderRun || FVector::Dist2D(Me, Dest) > UVLSwordsmanCombat::ChargeBeyond, EVLFormation::Line);
	}
	bInternalOrder = false;
	bApproaching = Unit->HasOrder();
	if (ArcherLogOn())
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("%s walks into range: to %s, %.0f cm from the target%s"), *Unit->GetDisplayName(), *Dest.ToCompactString(), FVector::Dist2D(Dest, At),
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
	if (!World || !World->LineTraceSingleByChannel(Hit, From, From + Dir * Far, ECC_Visibility, Params) || Hit.GetActor() == Target.Get())
	{
		return true;
	}
	// a building aimed at: what the trace met (its props, the mound, its eaves) inside its hit box is the building
	const UVLBattle* Battle = UVLBattle::Get(Unit);
	return Battle && Target.IsValid() && Battle->FindBuilding(Target.Get()) && Battle->BuildingAt(Hit.ImpactPoint, Unit->Team) == Target.Get();
}

void UVLArcherCombat::TickOrders(AVLKing* Unit, float Dt)
{
	if (Mode == EMode::None)
	{
		return;
	}
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (bHands || Unit->IsDead() || (Mode == EMode::Actor && (!Target.IsValid() || (Battle && !Battle->IsAlive(Target.Get())))))
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
				UE_CLOG(ArcherLogOn(), LogSovereignRealms, Log, TEXT("%s cannot shoot that far (%.0f cm%s)"), *Unit->GetDisplayName(), Dist, bTower ? TEXT(", from the tower") : TEXT(""));
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
		UE_CLOG(ArcherLogOn(), LogSovereignRealms, Log, TEXT("%s shoots at %s from %.0f cm%s"), *Unit->GetDisplayName(), Mode == EMode::Actor ? *Target->GetName() : *GroundTarget.ToCompactString(), Dist,
			bTower ? TEXT(" (from the tower)") : TEXT(""));
	}
	// a foe that has moved out of her reach since: into range again (or, from the tower, let it go)
	if (Mode == EMode::Actor && Dist > (bTower ? TowerRange : Range) * 1.15f && Phase == EPhase::Rest && !bLooseQueued)
	{
		if (bTower)
		{
			Stop();
			return;
		}
		bEngaged = false;
		Approaches = 0;
		return;
	}
	AimPoint = At + ShotScatter;
	bHasAim = true;
	// The wait between two shots runs from one shot's start to the next's, through the draw (reach, nock, draw,
	// loose: 1.1 s) as well: ShotInterval is her rhythm. It used to run only while she stood at rest, so a shot came
	// every 3.5 s, not 2.4, and she dealt 11 damage a second, not the 17 her arrow was set for (balance runs,
	// 2026-11-22: ten swordsmen beat twelve archers without a loss).
	Cooldown -= Dt;
	if (Phase != EPhase::Rest || bLooseQueued)
	{
		return;                     // a shot is on its way
	}
	if (ShotsLeft == 0)
	{
		Stop();                     // an attack-ground order: done
		return;
	}
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
	// In the player's hands the arrow goes to what the crosshair is on, exactly, on its arc. Her spread is put in the
	// aim, not the launch: a point of the same surface (the ground, a wall, a dummy) within distance x tan(HeroSpread)
	// of the crosshair's, or across the shot on a foe's body. (Turning the launch by the spread instead carried these
	// fast, flat arrows, which come down at only 1-3 degrees, far along the ground or over the top of what they were
	// aimed at: 0.3 degrees up landed up to 1.9 m beyond the crosshair at 30 m, 2.7 m at 50 m.) The crosshair on the
	// sky: it flies the way the crosshair points, off by up to HeroSpread.
	FVector At = AimPoint;
	bool bExact = false, bSky = false;
	if (bHands && bHasAim)
	{
		APlayerController* PC = Cast<APlayerController>(Unit->GetController());
		FVector O, D;
		if (TestAimTime > 0.f)
		{
			bExact = true;          // (vl.Bow aim: that point)
		}
		else if (PC && Unit->GetAimRay(PC, O, D))
		{
			FVector P;
			if (Unit->GetAimPointAlong(O, D, P, SkyAimDistance, &bSky))
			{
				At = P;
				bExact = true;
				const float Spread = FMath::DegreesToRadians(FMath::Max(HeroSpread, 0.f));
				const float R = float(FVector::Dist(Tip, P)) * FMath::Tan(Spread);
				if (bSky)
				{
					Dir = Spread > 0.f ? FMath::VRandCone(D, Spread) : D;
				}
				else if (R > 0.5f)
				{
					// a point of the same surface within R (the spread at that distance), or across the shot for a foe's body
					UWorld* World = Unit->GetWorld();
					FCollisionQueryParams Params(SCENE_QUERY_STAT(VLArcherSpread), true, Unit);
					FHitResult Hit;
					const bool bSurface = World->LineTraceSingleByChannel(Hit, P - D * 20.f, P + D * 20.f, ECC_Visibility, Params);
					const FVector N = bSurface ? FVector(Hit.ImpactNormal) : (Tip - P).GetSafeNormal(UE_SMALL_NUMBER, -D);
					FVector A = FVector::CrossProduct(N, FVector::UpVector);
					A = A.SizeSquared() > 0.01f ? A.GetSafeNormal() : FVector::CrossProduct(N, FVector::ForwardVector).GetSafeNormal();
					const FVector B = FVector::CrossProduct(N, A);
					const float Turn = FMath::FRandRange(0.f, 2.f * UE_PI), Far = R * FMath::Sqrt(FMath::FRand());
					FVector Q = P + (A * FMath::Cos(Turn) + B * FMath::Sin(Turn)) * Far;
					if (bSurface)
					{
						FHitResult Onto;
						Q = World->LineTraceSingleByChannel(Onto, Q + N * 30.f, Q - N * 30.f, ECC_Visibility, Params) ? FVector(Onto.ImpactPoint) : P;
					}
					At = Q;
				}
			}
		}
	}
	// the pull on this arrow: what gives the shallow arc wanted over this distance (the same for the aim and the flight)
	const float Gravity = bHasAim ? ShotGravity(Tip, At) : ArrowGravity;
	if (bHasAim && !bSky)
	{
		bReach = UVLArrows::SolveArc(Tip, At, ArrowSpeed, Gravity, Dir);
	}
	FRotator Way = Dir.Rotation();
	if (!bExact)
	{
		// not every arrow of a volley flies the same. At a spot of the ground the same error up or down carries an
		// arrow further along the ground the flatter it comes in (by 1 / the slope it comes down at): less of it, by
		// that slope, so that it lands about as far off along the ground as across. (It was scaled by the pull, which
		// since ArrowSpeed 6210 is always the full one: 0.8 degrees landed up to 5 m off at 28 m.)
		float PitchSpread = bHands ? HeroSpread : SpreadPitch;
		if (Mode == EMode::Ground && !bHands)
		{
			const float Flat = FMath::Max(float(FVector::Dist2D(Tip, At)), 1.f);
			const float Across = FMath::Max(float(FVector2D(Dir.X, Dir.Y).Size()) * ArrowSpeed, 1.f);
			const float Down = Gravity * (Flat / Across) - float(Dir.Z) * ArrowSpeed;      // cm/s down, as it lands
			PitchSpread *= FMath::Clamp(Down / Across, 0.f, 1.f);
		}
		Way.Yaw += FMath::FRandRange(-1.f, 1.f) * (bHands ? HeroSpread : SpreadYaw);
		Way.Pitch += FMath::FRandRange(-1.f, 1.f) * PitchSpread;
		Dir = Way.Vector();
	}
	Arrows->Fire(Unit, Tip, Dir * ArrowSpeed, Gravity, Unit->GarrisonIn.Get(), ArrowDamage);
	if (Unit->GetNetMode() != NM_Standalone)
	{
		Unit->ForceNetUpdate();     // (multiplayer: the joining game's copy lets its string go now, not at its next update)
	}
	++Shots;
	if (ArcherLogOn())
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("%s looses arrow %d from %s at %s (%.0f cm off%s): pitch %.1f yaw %.1f, pull %.0f, she faces %.1f"), *Unit->GetDisplayName(), Shots, *Tip.ToCompactString(),
			*At.ToCompactString(), FVector::Dist2D(Tip, At), bReach ? (bSky ? TEXT(", the sky") : TEXT("")) : TEXT(", OUT OF REACH"), Way.Pitch, Way.Yaw, Gravity, Unit->GetActorRotation().Yaw);
	}
	if (ArcherLogOn() && bHands)
	{
		// (for measuring the aim) what is drawn under the crosshair: the first thing its ray meets from the camera
		APlayerController* PC = Cast<APlayerController>(Unit->GetController());
		FVector O, D;
		if (PC && Unit->GetAimRay(PC, O, D))
		{
			FHitResult Hit;
			FCollisionQueryParams Params(SCENE_QUERY_STAT(VLArcherCrosshair), true, Unit);
			const bool bHit = Unit->GetWorld()->LineTraceSingleByChannel(Hit, O, O + D * 80000.f, ECC_Visibility, Params);
			UE_LOG(LogSovereignRealms, Log, TEXT("aimtest shot %d: eye %s dir %s crosshair %s on %s, aim %s, tip %s"), Shots, *O.ToCompactString(), *D.ToCompactString(),
				bHit ? *Hit.ImpactPoint.ToCompactString() : TEXT("sky"), bHit && Hit.GetActor() ? *Hit.GetActor()->GetName() : TEXT("-"), *At.ToCompactString(), *Tip.ToCompactString());
		}
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
			if (!Unit->IsNetCopy())
			{
				Unit->SetActorRotation(Now);        // (a copy is turned by the host)
			}
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
	const bool bUp = Phase != EPhase::Rest || bWantDraw || bLooseQueued || (Mode != EMode::None && bEngaged) || bNetUp;
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
			if (UVLArrows* Creak = UVLArrows::Get(this); Creak && GetOwner())
			{
				Creak->PlayDraw(GetOwner()->GetActorLocation() + FVector(0.f, 0.f, 60.f));     // the bow creaks as it is drawn
			}
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
	// (every joint is read from and written to the unit's pose buffer, AVLKing::Rig...: the same turns and places as
	// the components had, without moving ~70 of them at every write)
	const FQuat FigQ = Unit->RigWorldRot(AVLKing::RigFigure);
	const FVector Up = FigQ.GetUpVector(), Fwd = FigQ.GetForwardVector(), Right = FigQ.GetRightVector();
	const float W = ArcherSmooth(AimW);
	const float Scale = bQuick ? FMath::Max(QuickScale, 0.1f) : 1.f;

	// what the gait gave the bow arm (before it is changed)
	const FRotator Gait = Unit->RigRelRotator(iArmL);
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
		Unit->RigSetWorldRot(iChest, FQuat(Up, FMath::DegreesToRadians(ChestTwist * W + BashYaw * 0.5f * BashW)) * Unit->RigWorldRot(iChest));
	}
	if (W > 0.f)
	{
		if (Head)
		{
			Unit->RigSetWorldRot(iHead, FQuat::Slerp(Unit->RigWorldRot(iHead), FigQ * FRotator(AimPitch * 0.4f, 0.f, 0.f).Quaternion(), W));
		}
	}
	const FQuat ChestQ = Unit->RigWorldRot(iChest);

	// ---- the bow arm. The bow is rigid in the fist, so where the bow is to stand decides the forearm.
	// carried: upright before her left hip, leaning forward a little (more at a run), its string towards her body
	const float Run = FMath::GetMappedRangeValueClamped(FVector2D(Unit->WalkSpeed, FMath::Max(Unit->RunSpeed, Unit->WalkSpeed + 1.f)), FVector2D(0.f, 1.f), float(Unit->GetVelocity().Size2D()));
	const float Lean = FMath::DegreesToRadians(CarryTilt + RunTilt * Run);
	const float In = FMath::DegreesToRadians(CarryStringIn);
	const FQuat ForeCarry = ArcherFrame(Up * FMath::Cos(Lean) + Fwd * FMath::Sin(Lean), -Fwd * FMath::Cos(In) + Right * FMath::Sin(In)) * BowRestFrame;
	const FQuat UpperCarry = ChestQ * FRotator(CarryArmPitch + CarrySwing * GaitSwing, 0.f, CarryArmOut + 0.3f * GaitOut).Quaternion();
	FQuat UpperQ = UpperCarry, ForeQ = ForeCarry;
	const FVector Aim = FigQ.RotateVector(FRotator(AimPitch, 0.f, 0.f).Vector());
	const FVector Cheek = (Head ? Unit->RigWorldLoc(iHead) : Unit->RigWorldLoc(iChest) + Up * 30.f) + FigQ.RotateVector(Anchor);
	if (W > 0.f)
	{
		// aimed: upright in the plane of the shot, the string straight back along it; the grip as far out along the
		// line of the arrow (which passes her cheek) as the upper arm lets the elbow go
		const FVector Along = (Up - Aim * FVector::DotProduct(Up, Aim)).GetSafeNormal(UE_SMALL_NUMBER, Up);
		const FQuat ForeAim = ArcherFrame(Along, -Aim) * BowRestFrame;
		const FVector Shoulder = Unit->RigWorldLoc(iArmL);
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
	Unit->RigSetWorldRot(iArmL, UpperQ);
	Unit->RigSetWorldRot(iForeL, ForeQ);

	// ---- the bow as it now stands
	const FTransform BowT = Unit->RigWorld(iBow);
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
		const FVector QuiverAt = Quiver ? Unit->RigWorld(iQuiver).TransformPositionNoScale(QuiverAxis.GetSafeNormal() * (QuiverMouth + GrabAbove))
			: Unit->RigWorldLoc(iArmR) - Fwd * 30.f + Up * 8.f;
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
		ArcherSolveArm(Unit->RigWorldLoc(iArmR), ChestQ, UpperR, GripR, Goal, Pole, UpperIK, ForeIK);
		const float H = ArcherSmooth(HandW);
		const FQuat UpperNow = Unit->RigWorldRot(iArmR), ForeNow = Unit->RigWorldRot(iForeR);
		Unit->RigSetWorldRot(iArmR, FQuat::Slerp(UpperNow, UpperIK, H));
		Unit->RigSetWorldRot(iForeR, FQuat::Slerp(ForeNow, ForeIK, H));
		HandAt = Unit->RigWorld(iForeR).TransformPositionNoScale(GripR);
	}

	// ---- the string: straight between the limbs, or from each limb to the hand that draws it
	if (StringU && StringL && (bStringHeld || bStringDrawn))
	{
		bStringDrawn = bStringHeld;
		const FVector Apex = bStringHeld ? BowT.InverseTransformPositionNoScale(HandAt) : StringMid;
		for (int32 Half = 0; Half < 2; ++Half)
		{
			const int32 Joint = Half == 0 ? iStringU : iStringL;
			const FVector& End = Half == 0 ? StringEndU : StringEndL;
			const FQuat& Fix = Half == 0 ? StringFixU : StringFixL;
			const FVector Rest = StringMid - End, Now = Apex - End;
			const float RestLength = FMath::Max(float(Rest.Size()), 1.f);
			Unit->RigSetRelRot(Joint, FQuat::FindBetweenNormals(Rest / RestLength, Now.GetSafeNormal(UE_SMALL_NUMBER, Rest / RestLength)) * Fix.Inverse());
			Unit->RigSetRelScale(Joint, FVector(1.f, 1.f, FMath::Max(float(Now.Size()) / RestLength, 0.05f)));
		}
	}

	// ---- the arrow in her hand: its nock in the fist, turning from the quiver's line to the bow's, then on the string
	if (ArrowJoint && bArrowShown)
	{
		FVector Way = (Shelf - HandAt).GetSafeNormal(UE_SMALL_NUMBER, Shot);
		if (Phase == EPhase::Nock && Quiver)
		{
			const FVector Down = -Unit->RigWorldRot(iQuiver).RotateVector(QuiverAxis.GetSafeNormal());
			const float U = ArcherSmooth(PhaseTime / FMath::Max(NockSeconds * Scale * 0.7f, 0.01f));
			Way = FMath::Lerp(Down, Way, U).GetSafeNormal(UE_SMALL_NUMBER, Way);
		}
		ArrowWay = Way;
		ArrowTip = HandAt + Way * VLArrowGeom::Length;
		Unit->RigSetWorldLocRot(iArrow, HandAt + Way * VLArrowGeom::NockOffset, FQuat::FindBetweenNormals(VLArrowGeom::Dir.GetSafeNormal(), Way));
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
	if (Unit->IsNetCopy())
	{
		NetMirror(Unit, DeltaTime);     // (the joining player's game: the host's shot, shown)
		return;
	}
	TickHands(Unit, DeltaTime);
	TickOrders(Unit, DeltaTime);
	if (Unit->RigPosedAtTick())
	{
		Pose(Unit, DeltaTime);      // (as the shot stands: its arrow leaves from where this puts it)
	}
	TickShot(Unit, DeltaTime);
	if (Unit->KindId() == EVLUnitKind::Spy)
	{
		// the Spy's spyglass is in its drawing hand: put away while it shoots (UVLSpy raises it again)
		if (USceneComponent* Glass = Unit->GetJoint(TEXT("Spyglass")))
		{
			const bool bShow = Phase == EPhase::Rest || Phase == EPhase::Loose;
			if (Glass->IsVisible() != bShow)
			{
				Glass->SetVisibility(bShow, true);
			}
		}
	}
	// While a shot is on its way the figure is posed in every Tick, seen or not: the arrow leaves from where the pose
	// has it (a shot takes several frames to get to the loose, so the pose is there in time). Otherwise the unit poses
	// her, bow arm and all, only when she is seen (AVLKing::RigLate).
	const bool bShot = Phase != EPhase::Rest || bWantDraw || bLooseQueued;
	Unit->RigDemandPose(bShot);
	// nothing at all to do (no order, not the player's, the bow down and at rest): no tick until something wakes it
	// (an order, the player's hands, vl.Bow)
	if (!bShot && !bHands && Mode == EMode::None && BashTime < 0.f && AimW <= 0.f && HandW <= 0.f && AimPitch == 0.f && !bStringDrawn && !bTestDraw
		&& TestAimTime <= 0.f && TestLookTime <= 0.f && !Cast<APlayerController>(Unit->GetController()))
	{
		SetComponentTickEnabled(false);
	}
}

void UVLArcherCombat::NetFill(AVLKing* Unit) const
{
	const bool bUp = Phase != EPhase::Rest || bWantDraw || bLooseQueued || (Mode != EMode::None && bEngaged) || bBattle;
	// bit 0 drawing, bit 1 the bow up, bit 2 a quick shot, bits 3..7 the count of shots loosed (each change: one more)
	Unit->NetBow = uint8(((bWantDraw || bLooseQueued) ? 1 : 0) | (bUp ? 2 : 0) | (bQuick ? 4 : 0) | ((Shots & 31) << 3));
	// what she aims at: an actor both games know (a unit, one of the level's), else the point
	AActor* At = (bUp && Mode == EMode::Actor) ? Target.Get() : nullptr;
	if (At && At->ActorHasTag(TEXT("Built")))
	{
		At = nullptr;
	}
	Unit->NetBowTarget = At;
	Unit->NetBowAim = (bUp && !At && bHasAim) ? AimPoint : FVector::ZeroVector;
}

void UVLArcherCombat::NetMirror(AVLKing* Unit, float Dt)
{
	const uint8 Net = Unit->NetBow;
	const int32 TheirShots = Net >> 3;
	bWantDraw = (Net & 1) != 0;
	bNetUp = (Net & 2) != 0;
	bQuick = (Net & 4) != 0;
	bLooseQueued = false;
	if (const AActor* At = Unit->NetBowTarget)
	{
		const UVLBattle* Battle = UVLBattle::Get(this);
		AimPoint = Battle ? Battle->AimPoint(At, Unit->GetActorLocation()) : At->GetActorLocation();
		bHasAim = true;
	}
	else
	{
		AimPoint = Unit->NetBowAim;
		bHasAim = !AimPoint.IsZero();
	}
	bBattle = bNetUp;
	if (NetShotsSeen < 0)
	{
		NetShotsSeen = TheirShots;
	}
	else if (TheirShots != NetShotsSeen)
	{
		// the host loosed: the string is let go here (the arrow itself comes with the host's arrows)
		NetShotsSeen = TheirShots;
		ShowArrow(false);
		Phase = EPhase::Loose;
		PhaseTime = 0.f;
	}
	if (Unit->RigPosedAtTick())
	{
		Pose(Unit, Dt);
	}
	TickShot(Unit, Dt);
	if (Unit->KindId() == EVLUnitKind::Spy)
	{
		if (USceneComponent* Glass = Unit->GetJoint(TEXT("Spyglass")))
		{
			const bool bShow = Phase == EPhase::Rest || Phase == EPhase::Loose;
			if (Glass->IsVisible() != bShow)
			{
				Glass->SetVisibility(bShow, true);
			}
		}
	}
	// at rest with the bow down: no tick until the host's word changes (AVLKing::OnRep_NetBow)
	if (Phase == EPhase::Rest && !bWantDraw && !bNetUp && AimW <= 0.f && HandW <= 0.f && AimPitch == 0.f && !bStringDrawn)
	{
		SetComponentTickEnabled(false);
	}
}

FString UVLArcherCombat::Describe() const
{
	const AVLKing* Unit = Cast<AVLKing>(GetOwner());
	if (!Unit || !bSetup)
	{
		return TEXT("(not set up)");
	}
	const FQuat FigQ = Unit->RigWorldRot(AVLKing::RigFigure);
	const FTransform BowT = Unit->RigWorld(iBow);
	const FVector Along = BowT.GetRotation().RotateVector(BowAxis), StringWay = BowT.GetRotation().RotateVector(BowString);
	const FVector Grip = Unit->GetActorTransform().InverseTransformPositionNoScale(BowT.GetLocation());
	const FVector Hand = Unit->RigWorld(iForeR).TransformPositionNoScale(GripR);
	const FVector Brace = BowT.TransformPositionNoScale(StringMid + BowAxis * NockAbove);
	const float Half = Unit->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const FVector At = OrderTarget();
	return FString::Printf(TEXT("%s%s%s, %s%s, aim %.2f hand %.2f pitch %.1f, %d loosed | bow: upright %.2f, string back %.2f right %.2f up %.2f, grip %.0f ahead %.0f right %.0f above her feet, hand to string %.0f cm, string x%.2f"),
		ArcherPhaseName(int32(Phase)), bBattle ? TEXT(" (battle)") : TEXT(""), bHands ? TEXT(" (played)") : TEXT(""),
		Mode == EMode::None ? TEXT("no order") : *FString::Printf(TEXT("%s %.0f cm off, %s"), Mode == EMode::Actor ? TEXT("target") : TEXT("spot"), FVector::Dist2D(Unit->GetActorLocation(), At),
			bEngaged ? TEXT("shooting") : bApproaching ? TEXT("walking in") : TEXT("waiting")),
		Unit->IsGarrisoned() ? TEXT(" on the tower") : TEXT(""), AimW, HandW, AimPitch, Shots,
		FVector::DotProduct(Along, FigQ.GetUpVector()), -FVector::DotProduct(StringWay, FigQ.GetForwardVector()), FVector::DotProduct(StringWay, FigQ.GetRightVector()),
		FVector::DotProduct(StringWay, FigQ.GetUpVector()), Grip.X, Grip.Y, Grip.Z + Half, FVector::Dist(Hand, Brace), StringU ? Unit->RigRelScale(iStringU).Z : 1.f);
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
					UE_LOG(LogSovereignRealms, Log, TEXT("archer %s at %s yaw %.0f speed %.0f: %s"), *It->GetDisplayName(), *It->GetActorLocation().ToCompactString(), It->GetActorRotation().Yaw,
						It->GetVelocity().Size2D(), *Combat->Describe());
					++N;
				}
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("%d archer(s)"), N);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdBow(TEXT("vl.Bow"),
		TEXT("vl.Bow draw 0|1 | shoot | lock | cancel | bash | aim X Y [Z] | off: the archer the player plays: hold / let go of the right button (letting go looses), a short right click, the left button (locks a held draw, lets a locked one down, else a blow with the bow), let the string down, a blow with the bow, aim at a point instead of the crosshair / pointer (for 60 s), back to it"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			UVLArcherCombat* Combat = PC ? UVLArcherCombat::For(Cast<AVLKing>(PC->GetPawn()), false) : nullptr;
			if (!Combat || Args.Num() < 1)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("vl.Bow: the player is not playing an archer (vl.Control Archer_1)"));
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
			else if (Args[0].Equals(TEXT("look"), ESearchCase::IgnoreCase) && Args.Num() >= 3)
			{
				// the crosshair put on a point (the ground there without Z) by turning the camera, for 30 s
				const float X = FCString::Atof(*Args[1]), Y = FCString::Atof(*Args[2]);
				Combat->SetTestLook(Args.Num() >= 4 ? FVector(X, Y, FCString::Atof(*Args[3])) : ArcherGround(World, X, Y), 30.f);
			}
			else if (Args[0].Equals(TEXT("spread"), ESearchCase::IgnoreCase) && Args.Num() >= 2)
			{
				Combat->HeroSpread = FCString::Atof(*Args[1]);
				UE_LOG(LogSovereignRealms, Log, TEXT("vl.Bow: hero spread %.2f deg"), Combat->HeroSpread);
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
				UE_LOG(LogSovereignRealms, Log, TEXT("attack ground %s"), Command->IsAttackGroundArmed() ? TEXT("armed") : TEXT("not armed (no archers selected)"));
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
			UE_LOG(LogSovereignRealms, Log, TEXT("attack ground: %d of %d unit(s) shoot at %s"), Ordered, Units.Num(), *Ground.ToCompactString());
		}));
}
