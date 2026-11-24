#include "VLSpy.h"
#include "SovereignRealms.h"
#include "VLKing.h"
#include "VLBattle.h"
#include "VLHUD.h"
#include "Camera/CameraComponent.h"
#include "Components/PointLightComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "HAL/IConsoleManager.h"

namespace
{
	/** An arm of two rigid pieces from the shoulder (UVLArcherCombat's solve): the turns (world) of the upper arm and
	 *  of the forearm that bring the end of the forearm to Target, as near as the arm reaches, the elbow out towards
	 *  Pole. Upper / Fore: shoulder -> elbow and elbow -> wrist in the rest pose, in the frame the arm hangs from. */
	void SpySolveArm(const FVector& Shoulder, const FQuat& Base, const FVector& Upper, const FVector& Fore, const FVector& Target, const FVector& Pole,
		FQuat& OutUpper, FQuat& OutFore, FVector& OutElbow)
	{
		const float L1 = FMath::Max(Upper.Size(), 1.f), L2 = FMath::Max(Fore.Size(), 1.f);
		const FVector To = Target - Shoulder;
		const float D = FMath::Clamp(float(To.Size()), FMath::Abs(L1 - L2) + 0.5f, L1 + L2 - 0.5f);
		const FVector Dir = To.GetSafeNormal(UE_SMALL_NUMBER, Base.GetForwardVector());
		const float CosA = FMath::Clamp((L1 * L1 + D * D - L2 * L2) / (2.f * L1 * D), -1.f, 1.f);
		const float SinA = FMath::Sqrt(FMath::Max(0.f, 1.f - CosA * CosA));
		const FVector Side = (Pole - Dir * FVector::DotProduct(Pole, Dir)).GetSafeNormal(UE_SMALL_NUMBER, Base.GetRightVector());
		OutElbow = Shoulder + Dir * (L1 * CosA) + Side * (L1 * SinA);
		const FVector Fist = Shoulder + Dir * D;
		OutUpper = FQuat::FindBetweenNormals(Base.RotateVector(Upper / L1), (OutElbow - Shoulder).GetSafeNormal()) * Base;
		OutFore = FQuat::FindBetweenNormals(OutUpper.RotateVector(Fore / L2), (Fist - OutElbow).GetSafeNormal()) * OutUpper;
	}

	float SpySmooth(float X)
	{
		X = FMath::Clamp(X, 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}
}

UVLSpy::UVLSpy()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

bool UVLSpy::IsSpy(const AVLKing* Unit)
{
	return Unit && Unit->IsTroop() && Unit->KindId() == EVLUnitKind::Spy;
}

UVLSpy* UVLSpy::For(AVLKing* Unit, bool bCreate)
{
	if (!Unit)
	{
		return nullptr;
	}
	// (B: the unit remembers its component, and that it has been looked for: no component search per call)
	UVLSpy* Spy = Unit->SpyComp;
	if (!Spy && !(Unit->CompLooked & 4))
	{
		Spy = Unit->FindComponentByClass<UVLSpy>();
		Unit->SpyComp = Spy;
		Unit->CompLooked |= 4;
	}
	if (!Spy && bCreate && IsSpy(Unit))
	{
		Spy = NewObject<UVLSpy>(Unit, TEXT("Spy"));
		Spy->RegisterComponent();
		Spy->AddTickPrerequisiteActor(Unit);        // the figure is posed first (AVLKing::Animate), then the arm and the hood
		Unit->SpyComp = Spy;
	}
	return Spy;
}

bool UVLSpy::Setup(AVLKing* Unit)
{
	if (bBroken)
	{
		return false;
	}
	if (bSetup)
	{
		return true;
	}
	Chest = Unit->GetJoint(TEXT("Chest"));
	Head = Unit->GetJoint(TEXT("Head"));
	ArmR = Unit->GetJoint(TEXT("ArmR"));
	ForeR = Unit->GetJoint(TEXT("ForeR"));
	HandR = Unit->GetJoint(TEXT("HandR"));
	Glass = Unit->GetJoint(TEXT("Spyglass"));
	HoodA = Unit->GetJoint(TEXT("HoodA"));
	HoodB = Unit->GetJoint(TEXT("HoodB"));
	iChest = Unit->RigFind(TEXT("Chest"));
	iHead = Unit->RigFind(TEXT("Head"));
	iArmR = Unit->RigFind(TEXT("ArmR"));
	iForeR = Unit->RigFind(TEXT("ForeR"));
	iHandR = Unit->RigFind(TEXT("HandR"));
	iGlass = Unit->RigFind(TEXT("Spyglass"));
	iHoodA = Unit->RigFind(TEXT("HoodA"));
	iHoodB = Unit->RigFind(TEXT("HoodB"));
	if (!Chest || !Head || !ArmR || !ForeR || !HandR || !Glass)
	{
		bBroken = true;
		UE_LOG(LogSovereignRealms, Warning, TEXT("%s: no spyglass arm to pose (parts Chest, Head, ArmR, ForeR, HandR, Spyglass)"), *Unit->GetDisplayName());
		return false;
	}
	bSetup = true;
	Unit->AddRigPoser(this, [this](AVLKing* Posed)
	{
		if (bSetup && !bBroken)
		{
			PoseGlass(Posed);
			PoseHood(Posed);
		}
	});
	UpperR = ForeR->GetRelativeLocation();
	ForeVec = HandR->GetRelativeLocation();
	GripOff = Glass->GetRelativeLocation();
	GlassDir = GlassDir.GetSafeNormal(UE_SMALL_NUMBER, FVector::ForwardVector);
	if (LanternIntensity > 0.f)
	{
		Lantern = NewObject<UPointLightComponent>(Unit, TEXT("SpyLantern"));
		Lantern->SetupAttachment(Chest);
		Lantern->SetRelativeLocation(LanternOffset);
		Lantern->SetIntensityUnits(ELightUnits::Unitless);
		Lantern->SetIntensity(LanternIntensity);
		Lantern->SetLightColor(FLinearColor(1.f, 0.66f, 0.28f));
		Lantern->SetAttenuationRadius(320.f);
		Lantern->SetSourceRadius(6.f);
		Lantern->SetCastShadows(false);
		Lantern->RegisterComponent();
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("%s: spyglass arm %.0f + %.0f cm, grip %.0f cm from the wrist, hood tail %s"), *Unit->GetDisplayName(), UpperR.Size(), ForeVec.Size(), GripOff.Size(),
		HoodA ? (HoodB ? TEXT("2 hinges") : TEXT("1 hinge")) : TEXT("none"));
	return true;
}

void UVLSpy::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	AVLKing* Unit = Cast<AVLKing>(GetOwner());
	if (!Unit || !Setup(Unit))
	{
		return;
	}
	TickGlass(Unit, DeltaTime);
	TickHood(Unit, DeltaTime);
	if (Unit->RigPosedAtTick())
	{
		PoseGlass(Unit);
		PoseHood(Unit);
	}
}

// ------------------------------------------------------------------------------------------------ the spyglass

void UVLSpy::TickGlass(AVLKing* Unit, float Dt)
{
	APlayerController* PC = Cast<APlayerController>(Unit->GetController());
	const bool bNow = PC && Unit->IsHeroMode() && Unit->IsAlive();
	UCharacterMovementComponent* Move = Unit->GetCharacterMovement();
	if (bNow != bHands)
	{
		bHands = bNow;
		IdleTime = 0.f;
		if (!bNow)
		{
			Unit->bRightMouseAims = false;
			Unit->MoveSpeedCap = 0.f;
		}
	}
	bool bWant = bTestRaise && Unit->IsAlive();
	if (bNow)
	{
		Unit->bRightMouseAims = true;           // the right button holds the spyglass up: it does not turn the camera
		const AVLHUD* HUD = Cast<AVLHUD>(PC->GetHUD());
		const bool bMenu = (HUD && HUD->bMenu) || Unit->IsCommandMode();     // (command mode: the right button orders)
		bWant |= !bMenu && (PC->IsInputKeyDown(EKeys::RightMouseButton) || PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) > 0.4f);
	}
	else if (Unit->IsAlive())
	{
		// on its own: standing with nothing to do, it looks through the glass for a while, lowers it, looks again
		const bool bStill = Unit->GetVelocity().SizeSquared() < 25.f && !Unit->HasOrder();
		IdleTime = bStill ? IdleTime + Dt : 0.f;
		bWant |= bStill && IdleTime > IdleLookAfter && FMath::Fmod(IdleTime - IdleLookAfter, IdleLookSeconds * 1.6f) < IdleLookSeconds;
	}
	Raise = FMath::Clamp(Raise + (bWant ? Dt : -Dt) * RaiseSpeed, 0.f, 1.f);
	const float H = SpySmooth(Raise);

	// played: it faces the way the camera looks, and creeps; the camera looks far ahead through a narrower lens
	if (bNow)
	{
		Unit->MoveSpeedCap = Raise > 0.f ? Unit->WalkSpeed * LookMoveScale : 0.f;
		if (Raise > 0.f)
		{
			Move->bOrientRotationToMovement = false;
			const float Yaw = PC->GetControlRotation().Yaw;
			Unit->SetActorRotation(FRotator(0.f, FMath::FixedTurn(Unit->GetActorRotation().Yaw, Yaw, 540.f * Dt), 0.f));
		}
	}
	if (Unit->Boom && Unit->Camera && (bCamera || (bNow && H > 0.f)))
	{
		const float Share = bNow ? H : 0.f;
		const FVector Ahead = FRotator(0.f, PC ? PC->GetControlRotation().Yaw : Unit->GetActorRotation().Yaw, 0.f).Vector();
		Unit->Boom->TargetOffset = Ahead * (LookAhead * Share);
		Unit->Camera->SetFieldOfView(FMath::Lerp(Unit->CameraFOV, Unit->CameraFOV * ZoomFOV, Share));
		bCamera = Share > 0.f;
	}
	GlassShare = H;
	if (H <= 0.f)
	{
		EyeError = AimError = 0.f;
	}
}

void UVLSpy::PoseGlass(AVLKing* Unit)
{
	const float H = GlassShare;
	if (H <= 0.f)
	{
		return;
	}
	// the pose: the tube along the head's line of sight, its eyepiece just ahead of the right eye
	const FQuat FigQ = Unit->RigWorldRot(AVLKing::RigFigure);
	const FQuat ChestQ = Unit->RigWorldRot(iChest);
	const FTransform HeadT = Unit->RigWorld(iHead);
	const FVector Aim = HeadT.GetRotation().GetForwardVector();
	const FVector Eye = HeadT.TransformPositionNoScale(EyeOffset);
	const FVector Grip = Eye + Aim * (EyeGap + EyepieceLength);
	const FVector Shoulder = Unit->RigWorldLoc(iArmR);
	const FQuat Level = FQuat::FindBetweenNormals(FigQ.RotateVector(GlassDir), Aim) * FigQ;      // the fist as modelled, the tube turned onto the line
	const FVector ToElbow0 = -ForeVec.GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);           // wrist -> elbow, as modelled
	const FVector Pole = FigQ.RotateVector(FVector(-0.2f, 0.75f, -1.f));                            // the elbow: down and out
	float Roll = PI;                                // (as modelled the fist hangs under the wrist: turned over, the forearm comes up from below)
	FQuat HandQ = Level, UpperQ = ChestQ, ForeQ = ChestQ;
	FVector Elbow = Shoulder, Wrist = Grip;
	for (int32 Pass = 0; Pass < 3; ++Pass)
	{
		HandQ = FQuat(Aim, Roll) * Level;
		Wrist = Grip - HandQ.RotateVector(GripOff);
		SpySolveArm(Shoulder, ChestQ, UpperR, ForeVec, Wrist, Pole, UpperQ, ForeQ, Elbow);
		// turn the fist about the tube until its wrist side faces the elbow
		const FVector Have = FVector::VectorPlaneProject(Level.RotateVector(ToElbow0), Aim).GetSafeNormal();
		const FVector Need = FVector::VectorPlaneProject(Elbow - Wrist, Aim).GetSafeNormal();
		if (Have.IsNearlyZero() || Need.IsNearlyZero())
		{
			break;
		}
		Roll = FMath::Atan2(FVector::DotProduct(FVector::CrossProduct(Have, Need), Aim), FVector::DotProduct(Have, Need));
	}
	const FQuat UpperNow = Unit->RigWorldRot(iArmR), ForeNow = Unit->RigWorldRot(iForeR), HandNow = Unit->RigWorldRot(iHandR);
	Unit->RigSetWorldRot(iArmR, FQuat::Slerp(UpperNow, UpperQ, H));
	Unit->RigSetWorldRot(iForeR, FQuat::Slerp(ForeNow, ForeQ, H));
	Unit->RigSetWorldRot(iHandR, FQuat::Slerp(HandNow, HandQ, H));
	// how well it sits (vl.Spies)
	const FTransform GlassT = Unit->RigWorld(iGlass);
	const FVector Tube = GlassT.GetRotation().RotateVector(GlassDir);
	EyeError = FVector::Dist(GlassT.GetLocation() - Tube * EyepieceLength, Eye + Aim * EyeGap);
	AimError = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FVector::DotProduct(Tube, Aim)), -1.f, 1.f)));
}

// ------------------------------------------------------------------------------------------------ the hood

void UVLSpy::TickHood(AVLKing* Unit, float Dt)
{
	if (!HoodA)
	{
		return;
	}
	const FQuat ActorQ = Unit->GetActorQuat();
	const FVector Fwd = ActorQ.GetForwardVector(), Right = ActorQ.GetRightVector();
	const FVector Vel = Unit->GetVelocity();
	const float Yaw = Unit->GetActorRotation().Yaw;
	if (!bStarted || Dt <= 1e-5f)
	{
		bStarted = true;
		LastVel = Vel;
		LastYaw = Yaw;
	}
	else
	{
		Time += Dt;
		Acc = FMath::Lerp(Acc, (Vel - LastVel) / Dt, 1.f - FMath::Exp(-Dt * 10.f));
		const float YawRate = FRotator::NormalizeAxis(Yaw - LastYaw) / Dt;          // degrees a second: a turn throws it sideways
		LastVel = Vel;
		LastYaw = Yaw;
		const float Vf = FVector::DotProduct(Vel, Fwd), Vr = FVector::DotProduct(Vel, Right);
		const float Af = FVector::DotProduct(Acc, Fwd);
		const float SpeedShare = FMath::Clamp(Vel.Size() / FMath::Max(Unit->RunSpeed, 1.f), 0.f, 1.2f);
		const float Flutter = HoodFlutter + HoodFlutterRun * SpeedShare;
		for (int32 i = 0; i < 2; ++i)
		{
			// where it wants to hang: streamed back by the speed, thrown by a start or a stop, lifted in a fall; the
			// lower piece trails further and later
			const float Deep = i == 0 ? 0.6f : 1.f;
			float Want = HoodTrail * FMath::Max(Vf, 0.f) * Deep + HoodInertia * FMath::Clamp(Af, -3000.f, 3000.f) * Deep + (Vel.Z < 0.f ? -0.03f * Vel.Z : 0.f) * Deep
				+ Flutter * (0.5f + 0.5f * FMath::Sin(Time * (i == 0 ? 5.3f : 7.1f) - i * 1.3f) * FMath::Sin(Time * 1.7f + i)) * Deep;
			Want = HoodMax * FMath::Tanh(FMath::Max(Want, 0.f) / HoodMax);
			const float Stiff = HoodStiff * (i == 0 ? 1.f : 0.8f);
			float Left = Dt;
			while (Left > 0.f)
			{
				const float Step = FMath::Min(Left, 1.f / 90.f);
				Left -= Step;
				HoodVel[i] += (Stiff * Stiff * (Want - HoodPitch[i]) - 2.f * HoodDamping * Stiff * HoodVel[i]) * Step;
				HoodPitch[i] += HoodVel[i] * Step;
			}
			// never forward into the head (the lower piece may fold a little under the upper)
			const float Least = i == 0 ? 0.f : -6.f;
			if (HoodPitch[i] < Least)
			{
				HoodPitch[i] = Least;
				HoodVel[i] = FMath::Max(HoodVel[i], 0.f);
			}
			HoodPitch[i] = FMath::Min(HoodPitch[i], 80.f);
		}
		const float WantRoll = FMath::Clamp(0.03f * Vr - 0.035f * YawRate + 0.6f * Flutter * FMath::Sin(Time * 4.1f), -22.f, 22.f);
		float Left = Dt;
		while (Left > 0.f)
		{
			const float Step = FMath::Min(Left, 1.f / 90.f);
			Left -= Step;
			HoodRollVel += (HoodStiff * HoodStiff * (WantRoll - HoodRoll) - 2.f * HoodDamping * HoodStiff * HoodRollVel) * Step;
			HoodRoll += HoodRollVel * Step;
		}
		// sideways only as far as it has lifted clear of the head
		HoodRoll = FMath::Clamp(HoodRoll, -22.f, 22.f) * FMath::Clamp(HoodPitch[0] / 12.f + 0.25f, 0.f, 1.f);
	}
}

void UVLSpy::PoseHood(AVLKing* Unit)
{
	if (!HoodA)
	{
		return;
	}
	// (a hanging piece swings backwards on a negative pitch: its foot goes to -X)
	Unit->RigSetRelRot(iHoodA, FRotator(-HoodPitch[0], 0.f, HoodRoll).Quaternion());
	if (HoodB)
	{
		Unit->RigSetRelRot(iHoodB, FRotator(-HoodPitch[1], 0.f, HoodRoll * 0.6f).Quaternion());
	}
}

FString UVLSpy::Describe() const
{
	const AVLKing* Unit = Cast<AVLKing>(GetOwner());
	if (!Unit || !bSetup)
	{
		return TEXT("(not set up)");
	}
	return FString::Printf(TEXT("spyglass %s (raise %.2f%s; eyepiece %.1f cm from the eye, %.1f deg off the line of sight), camera %s, hood tail %.1f / %.1f deg back, %.1f sideways"),
		Raise > 0.5f ? TEXT("UP") : TEXT("down"), Raise, bHands ? TEXT(", played") : TEXT(""), EyeError, AimError, bCamera ? TEXT("looking ahead") : TEXT("as usual"),
		HoodPitch[0], HoodPitch[1], HoodRoll);
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdSpies(TEXT("vl.Spies"), TEXT("log every spy: where, how fast, its spyglass and its hood"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			int32 N = 0;
			for (TActorIterator<AVLKing> It(World); It; ++It)
			{
				if (const UVLSpy* Spy = UVLSpy::For(*It, false))
				{
					const FVector CamOff = It->Boom ? It->Boom->TargetOffset : FVector::ZeroVector;
					UE_LOG(LogSovereignRealms, Log, TEXT("spy %s (team %d) at %s speed %.0f (walk %.0f run %.0f) health %.0f (%.0f%%): %s; camera ahead %.0f cm, lens %.1f"), *It->GetDisplayName(), It->Team,
						*It->GetActorLocation().ToCompactString(), It->GetVelocity().Size2D(), It->WalkSpeed, It->RunSpeed, It->GetHealth(), It->GetHealthFrac() * 100.f, *Spy->Describe(),
						CamOff.Size(), It->Camera ? It->Camera->FieldOfView : 0.f);
					++N;
				}
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("%d spy(ies)"), N);
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpyglass(TEXT("vl.Spyglass"), TEXT("vl.Spyglass 0|1: every spy holds its spyglass up (as the right button does for the one the player plays) / lets it down"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			const bool bOn = Args.Num() == 0 || FCString::Atoi(*Args[0]) != 0;
			int32 N = 0;
			for (TActorIterator<AVLKing> It(World); It; ++It)
			{
				if (UVLSpy* Spy = UVLSpy::For(*It, false))
				{
					Spy->SetTestRaise(bOn);
					++N;
				}
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("vl.Spyglass %d: %d spy(ies)"), bOn ? 1 : 0, N);
		}));
}
