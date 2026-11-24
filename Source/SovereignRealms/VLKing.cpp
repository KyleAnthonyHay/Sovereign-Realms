#include "VLKing.h"
#include "SovereignRealms.h"
#include "VLCharacterData.h"
#include "VLPartMesh.h"
#include "VLHUD.h"
#include "VLGraphics.h"
#include "Engine/GameViewportClient.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SWindow.h"
#include "VLArcherCombat.h"
#include "VLGameMode.h"
#include "VLGrid.h"
#include "VLFog.h"
#include "VLTroopShip.h"
#include "VLCommand.h"
#include "AIController.h"
#include "VLPlayerController.h"
#include "VLFootDust.h"
#include "VLRocks.h"
#include "VLSwordsmanCombat.h"
#include "VLBattle.h"
#include "VLTroop.h"
#include "VLConstruction.h"
#include "Camera/CameraActor.h"
#include "Components/SkeletalMeshComponent.h"      // (these four: the file also builds on its own, outside the unity blob)
#include "Engine/Engine.h"
#include "Misc/ConfigCacheIni.h"
#include "UObject/Package.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Engine/DamageEvents.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Sound/SoundBase.h"
#include "HAL/IConsoleManager.h"
#include "Misc/PackageName.h"

bool VLRigLodOn();      // (VLKingRig.cpp: vl.Opt.RigLOD, vl.Opt.UnitGI)
bool VLUnitGI();

namespace
{
	const float DrawSeconds = 0.5f;
	const float GuardSeconds = 1.f;    // the battle stance lasts this long after the last swing
	const float SheatheAfter = 4.f;    // drawn but resting this long, he puts it away

	float Smooth(float T)
	{
		T = FMath::Clamp(T, 0.f, 1.f);
		return T * T * (3.f - 2.f * T);
	}
}

AVLKing::AVLKing()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bTickEvenWhenPaused = true;        // (paused, only the menu's input is read: Tick)
	Data = TSoftObjectPtr<UVLCharacterData>(FSoftObjectPath(TEXT("/Game/Voxel/King/DA_King.DA_King")));
	// whoever the player is not controlling walks to orders under an AI controller (troops get one when spawned)
	AIControllerClass = AAIController::StaticClass();
	AutoPossessAI = EAutoPossessAI::Disabled;

	// what the voxel materials (MI_Vox_<slot>) sound like underfoot
	for (const TCHAR* Slot : { TEXT("grass"), TEXT("grass_side"), TEXT("dirt"), TEXT("moss"), TEXT("leaves"), TEXT("hay"), TEXT("wheat"), TEXT("wheat_top"), TEXT("wool"), TEXT("cloth") })
	{
		FootstepSurfaces.Add(Slot, EVLStepSurface::Dirt);
	}
	for (const TCHAR* Slot : { TEXT("stone"), TEXT("stone_mossy"), TEXT("cobble"), TEXT("gravel"), TEXT("brick"), TEXT("plaster"), TEXT("ore"), TEXT("metal"), TEXT("gold"), TEXT("roof") })
	{
		FootstepSurfaces.Add(Slot, EVLStepSurface::Cement);
	}
	for (const TCHAR* Slot : { TEXT("plank"), TEXT("beam"), TEXT("beam_v"), TEXT("bark"), TEXT("log_end") })
	{
		FootstepSurfaces.Add(Slot, EVLStepSurface::Wood);
	}

	GetCapsuleComponent()->InitCapsuleSize(40.f, 85.f);
	bUseControllerRotationYaw = false;

	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->bOrientRotationToMovement = true;
	Move->RotationRate = FRotator(0.f, 620.f, 0.f);
	Move->MaxWalkSpeed = WalkSpeed;
	Move->MaxAcceleration = 2400.f;
	Move->BrakingDecelerationWalking = 2400.f;
	Move->GroundFriction = 8.f;
	Move->MaxStepHeight = 58.f;                 // a 50 cm block is a step, as in any block world
	Move->SetWalkableFloorAngle(50.f);
	Move->JumpZVelocity = 540.f;
	Move->AirControl = 0.9f;                    // steer in the air: turn and change direction mid-jump
	Move->AirControlBoostMultiplier = 2.f;
	Move->FallingLateralFriction = 0.5f;        // a change of direction in the air takes hold quickly
	Move->GravityScale = 1.6f;
	Move->bUseFlatBaseForFloorChecks = true;    // a round capsule bottom slides off block edges
	Move->PerchRadiusThreshold = 0.f;
	// (Windows pass, batch 1) A unit standing still keeps the floor it found instead of sweeping for it again every
	// frame: the engine looks again by itself when the unit moves or is teleported, and when what it stands on is
	// movable, loses its collision or is destroyed (UCharacterMovementComponent::FindFloor).
	Move->bAlwaysCheckFloor = false;
	// nothing in this world simulates physics: no downward force on the floor, no push from overlapping bodies
	Move->bEnablePhysicsInteraction = false;
	// nothing listens to the capsule's overlaps (the game has no triggers): its sweeps need not gather them
	GetCapsuleComponent()->SetGenerateOverlapEvents(false);

	Figure = CreateDefaultSubobject<USceneComponent>(TEXT("Figure"));
	Figure->SetupAttachment(GetCapsuleComponent());

	Dust = CreateDefaultSubobject<UVLFootDust>(TEXT("Dust"));
	Dust->SetupAttachment(GetCapsuleComponent());

	// (the spring arm and the cameras: only on a pawn the player controls, EnsureCameraRig)

	if (USkeletalMeshComponent* Skel = GetMesh())
	{
		Skel->SetVisibility(false);
		Skel->PrimaryComponentTick.bStartWithTickEnabled = false;      // (registering turned a tick switched off here back on)
		Skel->SetUsingAbsoluteLocation(true);       // (and it need not be moved with the capsule: there is nothing of it)
		Skel->SetUsingAbsoluteRotation(true);
		Skel->SetUsingAbsoluteScale(true);
		Skel->SetComponentTickEnabled(false);
	}
}

void AVLKing::BeginPlay()
{
	Super::BeginPlay();
	int32 Saved = 0;
	if (GConfig && GConfig->GetInt(TEXT("SovereignRealms.Camera"), TEXT("CameraAngle"), Saved, GGameUserSettingsIni))
	{
		CameraAngle = FMath::Clamp(Saved, 0, 2);
	}
	int32 SavedInvert = 0;
	if (GConfig && GConfig->GetInt(TEXT("SovereignRealms.Camera"), TEXT("LookInvertV2"), SavedInvert, GGameUserSettingsIni))
	{
		LookInvert = FMath::Clamp(SavedInvert, 0, 3);
	}
	float SavedSpeed = 0.f;
	if (GConfig && GConfig->GetFloat(TEXT("SovereignRealms.Camera"), TEXT("LookSpeed"), SavedSpeed, GGameUserSettingsIni) && SavedSpeed > 0.f)
	{
		LookSpeedSetting = FMath::Clamp(SavedSpeed, 0.1f, 2.f);
	}
	MaxHealth = VLRules::Troop(UnitKind).Health;          // the rules for its kind (UVLBattle)
	BuildFigure();
	Post = GetFeet();
	// look the way the postcard does
	for (TActorIterator<ACameraActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(TEXT("Postcard")))
		{
			CamYaw = It->GetActorRotation().Yaw;
			break;
		}
	}
	HomeYaw = OverviewYaw = CamYaw;
	OverviewFocus = FVector(0.f, 0.f, 0.f);
	if (USkeletalMeshComponent* Skel = GetMesh())
	{
		Skel->SetComponentTickEnabled(false);       // hidden, with no mesh: nothing to animate
	}
	if (!bTroop || IsJonathan())
	{
		// King David's pace (VLRules; a troop's 420 / 760 now, it was 520 / 950). A pace other than the figure's own is
		// half a longer stride and half a quicker step, so the feet stay planted (StrideScale); he gets up to speed,
		// brakes and is trailed by the camera in the same time and distance as before (at a troop's pace: 1, as is).
		// (Jonathan, the second hero, has a pace of his own the same way: 520 / 1000, VLRules::Jonathan*)
		const VLRules::FTroop& Rules = VLRules::Troop(UnitKind);
		if (Rules.WalkSpeed > 0.f)
		{
			const float Was = WalkSpeed, WasRun = RunSpeed;
			WalkSpeed = Rules.WalkSpeed;
			RunSpeed = FMath::Max(Rules.RunSpeed, Rules.WalkSpeed);
			StrideScale = FMath::Sqrt(WalkSpeed / FMath::Max(Was, 1.f));
			const float Quicker = RunSpeed / FMath::Max(WasRun, 1.f);
			GetCharacterMovement()->MaxAcceleration *= Quicker;
			GetCharacterMovement()->BrakingDecelerationWalking *= Quicker;
			BoomLagScale = Quicker;
			if (Boom)
			{
				Boom->CameraLagSpeed = 7.f * BoomLagScale;
			}
		}
	}
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		EnsureCameraRig();
		Camera->SetFieldOfView(CameraFOV);
		PC->SetControlRotation(FRotator(HeroPitch(Zoom), CamYaw, 0.f));
		// the pointer stays visible and is never locked to the window
		FInputModeGameAndUI Mode;
		Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		Mode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(Mode);
		PC->bShowMouseCursor = true;
		PC->PlayerCameraManager->ViewPitchMin = -80.f;
		PC->PlayerCameraManager->ViewPitchMax = 10.f;
	}
	UpdateOverviewCamera(0.f, true);        // (the overview camera itself: EnsureCameraRig, for the player's pawn only)
	RigRegister(true);
}

namespace
{
	/** The enemy's twin of a unit material, or null: "<name>_Enemy" beside it (MI_King_paint_Enemy, MI_King_sway_Enemy:
	 *  TeamMix 1, which turns the green cloth red; Tools/ue/import_king.py makes them). Shared by every enemy unit. */
	UMaterialInterface* VLEnemyTwin(const UMaterialInterface* Base)
	{
		static TMap<FName, TWeakObjectPtr<UMaterialInterface>> Twins;
		static TSet<FName> Missing;
		if (!Base)
		{
			return nullptr;
		}
		const FString Package = Base->GetOutermost()->GetName() + TEXT("_Enemy");
		const FName Key(*Package);
		if (Missing.Contains(Key))
		{
			return nullptr;
		}
		if (const TWeakObjectPtr<UMaterialInterface>* Found = Twins.Find(Key); Found && Found->IsValid())
		{
			return Found->Get();
		}
		UMaterialInterface* Twin = FPackageName::DoesPackageExist(Package)
			? LoadObject<UMaterialInterface>(nullptr, *(Package + TEXT(".") + Base->GetName() + TEXT("_Enemy"))) : nullptr;
		if (Twin)
		{
			Twins.Add(Key, Twin);
		}
		else
		{
			Missing.Add(Key);
		}
		return Twin;
	}

	/** A part's look by its side. Every unit writes custom depth, with its side in the stencil: 1 the player's (which
	 *  M_Silhouette shows through trees and buildings), 2 the enemy's (never shown; but, being in the custom depth, a
	 *  unit standing in front of another does not bring the silhouette out). The enemy's cloth is red. */
	void VLTeamLook(UStaticMeshComponent* Mesh, int32 Team, bool bDepth, bool bAmbient = false, bool bNoOutline = false)
	{
		const bool bEnemy = Team != 0;
		Mesh->SetRenderCustomDepth(bDepth);          // (off behind the title screen and far from the camera: AVLKing::RigLate)
		// (a figure of the scenery: 2, never shown through walls; so too a tower's own archer, who never leaves it)
		Mesh->SetCustomDepthStencilValue(bEnemy || bNoOutline ? 2 : 1);
		const UStaticMesh* Asset = Mesh->GetStaticMesh();
		for (int32 i = 0; Asset && i < Asset->GetStaticMaterials().Num(); ++i)
		{
			Mesh->SetMaterial(i, bEnemy && !bAmbient ? VLEnemyTwin(Asset->GetMaterial(i)) : nullptr);      // (null: the mesh's own)
		}
	}
}

void AVLKing::ApplyPartLook(UStaticMeshComponent* Mesh, int32 InTeam)
{
	if (Mesh)
	{
		VLTeamLook(Mesh, InTeam, false, false, true);
	}
}

void AVLKing::RefreshSilhouette()
{
	for (UStaticMeshComponent* PartMesh : Meshes)
	{
		if (PartMesh)
		{
			VLTeamLook(PartMesh, Team, bDepthOn, bAmbient, bTowerGuard);
		}
	}
}

void AVLKing::BuildFigure()
{
	Loaded = Data.LoadSynchronous();
	if (!Loaded)
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("King: no character data at %s"), *Data.ToString());
		return;
	}
	const float Half = FMath::Max(Loaded->Height * 0.5f, Loaded->Radius);
	GetCapsuleComponent()->SetCapsuleSize(Loaded->Radius, Half);
	Figure->SetRelativeLocation(FVector(0.f, 0.f, -Half));
	// The joints live in character space (X forward, Y right); only the MESHES are turned to face forward. (Turning the
	// whole figure turned the joints with it: the limbs then swung sideways and sat in front of and behind the body.)
	Figure->SetRelativeRotation(FRotator::ZeroRotator);
	if (Boom)
	{
		Boom->SetRelativeLocation(FVector(0.f, 0.f, Half * 0.45f));
	}
	Health = MaxHealth;

	// every part is a joint at its pivot, hung from its parent's joint (or from the figure), with its mesh on it
	TMap<FName, FVector> Pivot;
	for (const FVLPart& P : Loaded->Parts)
	{
		Pivot.Add(P.Name, P.Pivot);
	}
	for (const FVLPart& P : Loaded->Parts)
	{
		const FString Label = P.Name.ToString();
		USceneComponent* Parent = Figure;
		FVector Base = FVector::ZeroVector;
		if (!P.Parent.IsNone())
		{
			if (const TObjectPtr<USceneComponent>* Found = Joints.Find(P.Parent))
			{
				Parent = Found->Get();
				Base = Pivot[P.Parent];
			}
			else
			{
				UE_LOG(LogSovereignRealms, Warning, TEXT("King: part %s is listed before its parent %s"), *Label, *P.Parent.ToString());
			}
		}
		USceneComponent* Joint = NewObject<USceneComponent>(this, *FString::Printf(TEXT("Joint_%s"), *Label));
		Joint->SetupAttachment(Parent);
		Joint->SetRelativeLocation(P.Pivot - Base);
		Joint->RegisterComponent();
		Joints.Add(P.Name, Joint);
		// its node of the pose buffer (a parent is always listed before its children)
		const int32 NodeIndex = RigNodes.AddDefaulted();
		RigNodes[NodeIndex].Joint = Joint;
		RigNodes[NodeIndex].Parent = Parent == Figure ? RigFigure : RigIndex.FindRef(P.Parent);
		RigNodes[NodeIndex].RelLoc = P.Pivot - Base;
		RigIndex.Add(P.Name, NodeIndex);
		if (!P.Mesh)
		{
			continue;
		}
		UStaticMeshComponent* PartMesh = NewObject<UVLPartMeshComponent>(this, *FString::Printf(TEXT("Mesh_%s"), *Label));     // (never occlusion-queried: VLPartMesh.h)
		PartMesh->SetStaticMesh(P.Mesh);
		PartMesh->SetupAttachment(Joint);
		PartMesh->SetRelativeRotation(FRotator(0.f, Loaded->MeshYaw, 0.f));
		PartMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		PartMesh->SetCastShadow(true);
		PartMesh->bCastContactShadow = true;
		PartMesh->bAffectDistanceFieldLighting = false;    // he moves every frame: keep him out of the global distance field
		bUnitGI = VLUnitGI();
		if (!bUnitGI)
		{
			// nor in Lumen's scene (a card capture for every part, every frame it moved) or the indirect lighting cache
			// (the project has no static lighting): a figure this small adds nothing to the bounce that can be seen
			PartMesh->bAffectDynamicIndirectLighting = false;
			PartMesh->IndirectLightingCacheQuality = ILCQ_Off;
		}
		VLTeamLook(PartMesh, Team, bDepthOn, bAmbient, bTowerGuard);    // custom depth + stencil for M_Silhouette; the enemy's red cloth
		PartMesh->RegisterComponent();
		Meshes.Add(PartMesh);
		RigNodes[NodeIndex].Mesh = PartMesh;
		RigNodes[NodeIndex].MeshRot = FRotator(0.f, Loaded->MeshYaw, 0.f).Quaternion();
	}
	auto At = [&Pivot](const TCHAR* Name) { const FVector* V = Pivot.Find(Name); return V ? *V : FVector::ZeroVector; };
	Rig.Body = Part(TEXT("Body"));
	Rig.Chest = Part(TEXT("Chest"));
	Rig.Head = Part(TEXT("Head"));
	Rig.ArmL = Part(TEXT("ArmL"));
	Rig.ForeL = Part(TEXT("ForeL"));
	Rig.ArmR = Part(TEXT("ArmR"));
	Rig.ForeR = Part(TEXT("ForeR"));
	Rig.HandR = Part(TEXT("HandR"));
	Rig.LegL = Part(TEXT("LegL"));
	Rig.ShinL = Part(TEXT("ShinL"));
	Rig.LegR = Part(TEXT("LegR"));
	Rig.ShinR = Part(TEXT("ShinR"));
	SwordJoint = Part(TEXT("Sword"));                  // moved by hand each frame: in the scabbard, or with the fist
	const TCHAR* Weapon = TEXT("Sword");
	if (!SwordJoint && Part(TEXT("Hammer")))
	{
		SwordJoint = Part(TEXT("Hammer"));             // the Builder: its hammer is held and swung as a sword is
		Weapon = TEXT("Hammer");
	}
	Rig.iBody = RigFind(TEXT("Body"));
	Rig.iChest = RigFind(TEXT("Chest"));
	Rig.iHead = RigFind(TEXT("Head"));
	Rig.iArmL = RigFind(TEXT("ArmL"));
	Rig.iForeL = RigFind(TEXT("ForeL"));
	Rig.iArmR = RigFind(TEXT("ArmR"));
	Rig.iForeR = RigFind(TEXT("ForeR"));
	Rig.iHandR = RigFind(TEXT("HandR"));
	Rig.iLegL = RigFind(TEXT("LegL"));
	Rig.iShinL = RigFind(TEXT("ShinL"));
	Rig.iLegR = RigFind(TEXT("LegR"));
	Rig.iShinR = RigFind(TEXT("ShinR"));
	Rig.iSword = RigFind(Weapon);
	Rig.HipL = At(TEXT("LegL"));
	Rig.HipR = At(TEXT("LegR"));
	Rig.HipHeight = FMath::Max(20.f, Rig.HipL.Z);
	Rig.Thigh = FMath::Max(5.f, (At(TEXT("ShinL")) - Rig.HipL).Size());
	Rig.Shin = FMath::Max(5.f, At(TEXT("ShinL")).Z);
	Rig.ShoulderR = At(TEXT("ArmR")) - At(TEXT("Chest"));
	Rig.UpperR = At(TEXT("ForeR")) - At(TEXT("ArmR"));
	Rig.ForeVecR = At(TEXT("HandR")) - At(TEXT("ForeR"));
	Rig.ForeAxis = Rig.ForeVecR.GetSafeNormal(UE_SMALL_NUMBER, FVector(0.f, 0.f, -1.f));
	Rig.Blade = Loaded->SwordBladeDir.GetSafeNormal();
	Rig.GripOff = At(Weapon) - At(TEXT("HandR"));
	// the cape's panels, column by column from the yoke down
	CapeCols = FMath::Clamp(Loaded->CapeCols, 0, CapeMaxCols);
	CapeRows = FMath::Clamp(Loaded->CapeRows, 0, CapeMaxRows);
	for (int32 C = 0; C < CapeCols; ++C)
	{
		for (int32 R = 0; R < CapeRows; ++R)
		{
			FCapePanel& N = Cape[C][R];
			const FName Name(*FString::Printf(TEXT("Cape%d%d"), C, R));
			N.Joint = Part(Name);
			N.Node = RigFind(Name);
			FVector Down = (R + 1 < CapeRows ? At(*FString::Printf(TEXT("Cape%d%d"), C, R + 1)) : FVector::ZeroVector) - Pivot.FindRef(Name);
			if (R + 1 >= CapeRows)
			{
				Down = R > 0 ? (Pivot.FindRef(Name) - At(*FString::Printf(TEXT("Cape%d%d"), C, R - 1))) * 1.15f : FVector(-5.f, 0.f, -28.f);
			}
			N.Length = FMath::Max(5.f, FVector2D(Down.X, Down.Z).Size());
			N.Slope = FMath::RadiansToDegrees(FMath::Atan2(-Down.X, -Down.Z));     // it hangs a little away from him as modelled
		}
	}
	if (bFootDust && Dust && Loaded->DustMaterial)
	{
		Dust->Setup(Loaded->DustMaterial);
	}
	else if (Dust)
	{
		// (troops raise no dust: no pool of 40 cubes and no material of their own for each of them)
		Dust->DestroyComponent();
		Dust = nullptr;
		bFootDust = false;
	}
	if (Loaded->FlashMaterial)
	{
		FlashMID = UMaterialInstanceDynamic::Create(Loaded->FlashMaterial, this);
	}
	FigureRest = Figure->GetRelativeLocation();
	RigBuild();
	UE_LOG(LogSovereignRealms, Log, TEXT("King: %d parts, height %.0f, legs %.0f + %.0f, cape %d x %d, sword %s"), Loaded->Parts.Num(), Loaded->Height, Rig.Thigh, Rig.Shin,
		CapeCols, CapeRows, SwordJoint ? (Loaded->bHasSheath ? TEXT("with scabbard") : TEXT("in hand only")) : TEXT("none"));
}

USceneComponent* AVLKing::Part(FName Name) const
{
	const TObjectPtr<USceneComponent>* Found = Joints.Find(Name);
	return Found ? Found->Get() : nullptr;
}

FString AVLKing::GetSelectedName() const
{
	const AActor* A = Selected.Get();
	if (!A)
	{
		return FString();
	}
	if (const AVLKing* Unit = Cast<AVLKing>(A))
	{
		return Unit->DisplayName;
	}
	for (const FName& Tag : A->Tags)
	{
		const FString S = Tag.ToString();
		if (S.StartsWith(TEXT("Name:")))
		{
			return S.Mid(5);
		}
	}
	return A->GetName();
}

void AVLKing::SelectByName(const FString& Name)
{
	Selected = nullptr;
	UVLCommand* Command = UVLCommand::Get(this);
	if (Command)
	{
		Command->ClearSelection();
	}
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		if (Name.Equals(TEXT("king"), ESearchCase::IgnoreCase) ? !It->IsTroop() : It->DisplayName.Equals(Name, ESearchCase::IgnoreCase))
		{
			Selected = *It;
			if (Command)
			{
				Command->Select({ *It });
			}
			return;
		}
	}
	const FName Tag(*(TEXT("Name:") + Name));
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(Tag))
		{
			Selected = *It;
			return;
		}
	}
}

void AVLKing::WalkTo(const FVector2D& Target, bool bRun)
{
	const FVector Ground(Target.X, Target.Y, GetFeet().Z);
	if (UVLCommand* Command = UVLCommand::Get(this))
	{
		Command->OrderMove({ this }, Ground, bRun, EVLFormation::Line);
	}
	else
	{
		FollowPath({ Ground }, bRun);
	}
}

FVector AVLKing::GetFeet() const
{
	return GetActorLocation() - FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
}

void AVLKing::FollowPath(const TArray<FVector>& Points, bool bRun)
{
	Waypoints = Points;
	bAutoWalk = Waypoints.Num() > 0;
	if (bAutoWalk)
	{
		SetMovementAwake(true);
	}
	bAutoRun = bRun;
	PaceCap = 0.f;              // at its own pace, unless it is a march's (UVLCommand::OrderMove sets that after this)
	MarchId = 0;
	AutoTime = 0.f;
	ProgressTime = 0.f;
	ProgressAt = FVector2D(GetActorLocation());
	StuckCount = 0;
	Replans = 0;
	if (bAutoWalk)
	{
		OrderGoal = Waypoints.Last();
		AutoTarget = FVector2D(OrderGoal);
	}
	// On the march units pass through one another (kept apart by AutoSteer, as the main game's are by its own
	// separation): capsules that block each other jam a gate or the bridge when a whole group arrives at it.
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, (bAutoWalk || bAmbient) ? ECR_Ignore : ECR_Block);
}

void AVLKing::QueueLeg(const FVector& Slot, bool bRun)
{
	QueuedLegs.Add(Slot);
	QueuedRuns.Add(bRun);
}

void AVLKing::ClearQueue()
{
	QueuedLegs.Reset();
	QueuedRuns.Reset();
}

bool AVLKing::StartNextLeg()
{
	if (QueuedLegs.Num() == 0)
	{
		return false;
	}
	const FVector Slot = QueuedLegs[0];
	const bool bRun = QueuedRuns.IsValidIndex(0) ? QueuedRuns[0] : false;
	QueuedLegs.RemoveAt(0);
	if (QueuedRuns.Num() > 0)
	{
		QueuedRuns.RemoveAt(0);
	}
	TArray<FVector> Path;
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!(Grid && Grid->EnsureBuilt() && Grid->FindPath(GetFeet(), Slot, Path) && Path.Num() > 0))
	{
		Path = { Slot };
	}
	else if (FVector::DistSquared2D(Path.Last(), Slot) > 1.f)
	{
		Path.Add(Slot);
	}
	// a leg of its pathway is part of the march it was queued on: it keeps the march's pace
	const float Cap = PaceCap;
	const int32 March = MarchId;
	FollowPath(Path, bRun);
	PaceCap = Cap;
	MarchId = March;
	return true;
}

namespace
{
	TAutoConsoleVariable<int32> CVarMoveSleep(TEXT("vl.Opt.MoveSleep"), 0,
		TEXT("1: a unit standing with nothing to do (settled on a floor that does not move, no order) has its movement component switched off until it is asked to move, is put elsewhere or loses its floor. 0: every unit's ticks every frame"));
	TAutoConsoleVariable<int32> CVarGarrisonSleep(TEXT("vl.Opt.GarrisonSleep"), 1,
		TEXT("1: a unit standing on a tower's lookout has its movement component switched off until it leaves (it never walks there). 0: it ticks as every unit"));
}

void AVLKing::SetMovementAwake(bool bAwake)
{
	UCharacterMovementComponent* Move = GetCharacterMovement();
	if (!Move || bAwake != bMoveAsleep)
	{
		return;             // (as it is already; only what was put to sleep here is woken here)
	}
	bMoveAsleep = !bAwake;
	MoveStill = 0;
	Move->SetComponentTickEnabled(bAwake);
	if (bAwake)
	{
		Move->bForceNextFloorCheck = true;      // (wherever it is now: the floor is looked for afresh)
	}
}

void AVLKing::UpdateMovementSleep()
{
	// On a lookout a unit is put on its post (UVLCommand::Enter) and stays there until UVLCommand::Leave takes it
	// down: it only turns to aim (SetActorRotation, which needs no movement tick). Once it has settled on the floor
	// its movement component stops ticking; anything that ends the stay wakes it (here, and at once in Leave,
	// FollowPath, Die and TakeControlOf).
	// (Batch 4, vl.Opt.MoveSleep) The same for any unit that stands with nothing to do: settled on a floor that does
	// not move, no order, not stepping aside. It wakes the moment anything asks it to move (AddMovementInput,
	// FollowPath), when it is hurt, and here, every tick of its own, if it is no longer where it fell asleep (put
	// somewhere else: a teleport) or what it stands on has moved, gone or lost its collision.
	const bool bGarrison = IsGarrisoned() && CVarGarrisonSleep.GetValueOnGameThread() != 0;
	const bool bIdle = CVarMoveSleep.GetValueOnGameThread() != 0 && !bYielding && !bYieldReturn && YieldWish.IsNearlyZero() && WayIgnored.Num() == 0;
	const bool bStay = (bGarrison || bIdle) && !bAutoWalk && !bDead && !IsPlayerControlled();
	UCharacterMovementComponent* Move = GetCharacterMovement();
	if (bMoveAsleep)
	{
		const UPrimitiveComponent* Base = Move->GetMovementBase();
		const bool bFloorThere = Base && IsValid(Base) && Base == SleepBase.Get() && Base->IsQueryCollisionEnabled()
			&& Base->GetComponentLocation().Equals(SleepBaseAt, 0.01);
		if (!bStay || !bFloorThere || !GetActorLocation().Equals(SleepAt, 0.01))
		{
			SetMovementAwake(true);
		}
		return;
	}
	if (!bStay)
	{
		MoveStill = 0;
		return;
	}
	const UPrimitiveComponent* Base = Move->GetMovementBase();
	const bool bStill = Move->IsMovingOnGround() && Move->Velocity.IsNearlyZero() && Move->GetPendingInputVector().IsNearlyZero() && Move->GetCurrentAcceleration().IsNearlyZero()
		&& Base && Base->Mobility != EComponentMobility::Movable && Move->CurrentFloor.IsWalkableFloor();
	MoveStill = bStill ? MoveStill + 1 : 0;
	if (MoveStill >= 20)
	{
		SleepAt = GetActorLocation();
		SleepBase = const_cast<UPrimitiveComponent*>(Base);
		SleepBaseAt = Base->GetComponentLocation();
		SetMovementAwake(false);
	}
}

void AVLKing::AddMovementInput(FVector WorldDirection, float ScaleValue, bool bForce)
{
	if (bMoveAsleep)
	{
		SetMovementAwake(true);         // (asked to move: UpdateMovementSleep)
	}
	Super::AddMovementInput(WorldDirection, ScaleValue, bForce);
}

void AVLKing::StopOrder()
{
	bAutoWalk = false;
	Waypoints.Reset();
	PaceCap = 0.f;              // (its own pace again: the march is over for it)
	MarchId = 0;
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, bAmbient ? ECR_Ignore : ECR_Block);
}

void AVLKing::FinishOrder(bool bArrived)
{
	const bool bHad = bAutoWalk;
	const float Cap = PaceCap;
	const int32 March = MarchId;
	StopOrder();
	if (bHad)
	{
		static const IConsoleVariable* BattleLog = IConsoleManager::Get().FindConsoleVariable(TEXT("vl.BattleLog"));
		if (!bArrived || (BattleLog && BattleLog->GetInt() != 0))       // (an arrival: one line per unit per order, only when asked for)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("%s %s %.0f cm from its goal after %.1f s (%d fresh routes)"), *DisplayName, bArrived ? TEXT("arrived") : TEXT("GAVE UP"),
				FVector::Dist2D(GetFeet(), OrderGoal), AutoTime, Replans);
		}
		if (UVLCommand* Command = UVLCommand::Get(this))
		{
			Command->OnOrderEnded(this, bArrived);
		}
		// the next point of its pathway (Shift + right click), unless the order's end gave it something else to do
		// (walked with the march it was queued on)
		if (!bAutoWalk)
		{
			PaceCap = Cap;
			MarchId = March;
			if (!StartNextLeg())
			{
				PaceCap = 0.f;
				MarchId = 0;
			}
		}
	}
}

bool AVLKing::AutoSteer(float DeltaSeconds, FVector& OutWish)
{
	if (!bAutoWalk)
	{
		return false;
	}
	FVLOptTiming::FScope Timing(FVLOptTiming::Steer);
	const FVector2D Pos(GetActorLocation());
	// corners reached (or passed close by) fall away; the last point is walked right onto
	while (Waypoints.Num() > 0)
	{
		const float Reach = Waypoints.Num() == 1 ? 28.f : 55.f;
		if (FVector2D::DistSquared(FVector2D(Waypoints[0]), Pos) > FMath::Square(Reach))
		{
			break;
		}
		Waypoints.RemoveAt(0);
	}
	if (Waypoints.Num() == 0)
	{
		FinishOrder(true);
		return false;
	}
	AutoTime += DeltaSeconds;
	ProgressTime += DeltaSeconds;
	if (ProgressTime > 0.6f)
	{
		const float Moved = FVector2D::Distance(Pos, ProgressAt);
		ProgressAt = Pos;
		ProgressTime = 0.f;
		if (Moved > 25.f)
		{
			StuckCount = 0;
		}
		else
		{
			++StuckCount;
			// someone stands on its spot: beside it will do
			if (FVector2D::Distance(Pos, FVector2D(OrderGoal)) < (StuckCount >= 2 ? 230.f : 140.f))
			{
				FinishOrder(true);
				return false;
			}
			if (StuckCount >= 2)
			{
				// stuck: plan the rest of the way again from where it stands (as the main game's units do)
				UVLGrid* Grid = UVLGrid::Get(this);
				TArray<FVector> Fresh;
				if (Replans < 4 && Grid && Grid->EnsureBuilt() && Grid->FindPath(GetFeet(), OrderGoal, Fresh) && Fresh.Num() > 0)
				{
					++Replans;
					StuckCount = 0;
					Waypoints = Fresh;
				}
				else if (StuckCount >= 5)
				{
					FinishOrder(false);
					return false;
				}
			}
		}
	}
	FVector2D Dir = (FVector2D(Waypoints[0]) - Pos).GetSafeNormal();
	// keep a little apart from the others on the way (their capsules would only block each other)
	const float Personal = 115.f;
	// (B: only the units of the cells round it, from the battle's spatial hash, in the registry's order; the rules
	// below are as they were. Without a battle, or with vl.Opt.Registry 0: every unit)
	FVLUnits Near;
	if (const UVLBattle* Battle = UVLBattle::Get(this))
	{
		Battle->UnitsNear(GetActorLocation(), Personal, Near);
	}
	else
	{
		for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
		{
			Near.Add(*It);
		}
	}
	const FVector MyLocation = GetActorLocation();
	for (const AVLKing* Other : Near)
	{
		if (Other == this)
		{
			continue;
		}
		const FVector OtherLocation = Other->GetActorLocation();
		if (FMath::Abs(OtherLocation.Z - MyLocation.Z) > 150.f)
		{
			continue;
		}
		const FVector2D Away = Pos - FVector2D(OtherLocation);
		if (Away.SizeSquared() >= FMath::Square(double(Personal)))
		{
			continue;           // (most of them: no square root)
		}
		const float D = Away.Size();
		if (D < Personal && D > 1.f)
		{
			// sideways rather than back: two walking the same way pass, they do not push each other off the road
			FVector2D Push = Away / D;
			Push -= Dir * FMath::Min(FVector2D::DotProduct(Push, Dir), 0.f) * 0.7f;
			Dir += Push * (1.f - D / Personal) * 0.8f;
		}
	}
	OutWish = FVector(Dir.GetSafeNormal(), 0.f);
	return !OutWish.IsNearlyZero();
}

void AVLKing::UpdateSafety(float DeltaSeconds)
{
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!Grid || !Grid->IsBuilt())
	{
		return;
	}
	const FVector Feet = GetFeet();
	SafeTimer += DeltaSeconds;
	if (SafeTimer > 0.3f)
	{
		SafeTimer = 0.f;
		const int32 Node = GetCharacterMovement()->IsMovingOnGround() ? Grid->NodeAt(Feet, 40.f) : INDEX_NONE;
		if (Node != INDEX_NONE && Grid->RegionOf(Node) == Grid->MainRegion())
		{
			LastSafe = GetActorLocation();
			bHasSafe = true;
		}
	}
	// in the water (off the cliffs, into the river): back onto the land where it last stood
	WetTime = Grid->Submerged(Feet) ? WetTime + DeltaSeconds : 0.f;
	if (WetTime > 0.7f && bHasSafe)
	{
		WetTime = 0.f;
		SetActorLocation(LastSafe + FVector(0.f, 0.f, 20.f), false, nullptr, ETeleportType::TeleportPhysics);
		GetCharacterMovement()->StopMovementImmediately();
		UE_LOG(LogSovereignRealms, Log, TEXT("%s fell in the water: back on land"), *DisplayName);
	}
}

void AVLKing::SetOrbit(float Yaw, float Pitch, float Distance)
{
	CamYaw = Yaw;
	ManualPitch = Pitch;
	ManualArm = Distance;
	TargetArm = Distance;
	if (Boom)
	{
		Boom->TargetArmLength = Distance;
	}
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->SetControlRotation(FRotator(Pitch, Yaw, 0.f));      // at once: a preview starts from a settled view
	}
}

void AVLKing::SetCameraLag(bool bLag)
{
	if (Boom)
	{
		Boom->bEnableCameraLag = bLag;
	}
}

void AVLKing::SetFreeCamera(const FVector& Location, const FRotator& Rotation, float FOV)
{
	if (!FreeCamera)
	{
		FreeCamera = GetWorld()->SpawnActor<ACameraActor>(Location, Rotation);
	}
	if (FreeCamera)
	{
		FreeCamera->SetActorLocationAndRotation(Location, Rotation);
		FreeCamera->GetCameraComponent()->SetFieldOfView(FOV);
		FreeCamera->GetCameraComponent()->SetConstraintAspectRatio(false);
		SetView(2, 0.f);
	}
}

void AVLKing::SetView(int32 Mode, float Blend)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		return;
	}
	AActor* Target = this;
	if (Mode == 1)
	{
		for (TActorIterator<ACameraActor> It(GetWorld()); It; ++It)
		{
			if (It->ActorHasTag(TEXT("Postcard")))
			{
				Target = *It;
				break;
			}
		}
	}
	else if (Mode == 2 && FreeCamera)
	{
		Target = FreeCamera;
	}
	else if (Mode == 3 && OverviewCamera)
	{
		Target = OverviewCamera;
	}
	ViewMode = (Target == this) ? 0 : Mode;
	PC->SetViewTargetWithBlend(Target, Blend, VTBlend_Cubic);
}

void AVLKing::SetHeroMode(bool bHero)
{
	bHeroMode = bHero;
	if (!bHero)
	{
		bCommandMode = bCommandChain = bChainHeldByTest = false;    // (command mode is the hero view's)
	}
	if (bHero)
	{
		Selected = this;
		SetView(0, 0.7f);
	}
	else
	{
		// the overview opens over the king, looking the way the hero camera did
		OverviewFocus = FVector(GetActorLocation().X, GetActorLocation().Y, 0.f);
		OverviewYaw = CamYaw;
		UpdateOverviewCamera(0.f, true);
		SetView(3, 0.7f);
	}
}

void AVLKing::LookAt(const FVector& Point, float InZoom, float InYaw)
{
	if (bHeroMode)
	{
		SetHeroMode(false);
	}
	OverviewFocus = FVector(Point.X, Point.Y, 0.f);
	if (InZoom >= 0.f)
	{
		OverviewZoom = FMath::Clamp(InZoom, 0.f, 1.f);
	}
	if (InYaw < 1e30f)
	{
		OverviewYaw = InYaw;
	}
	UpdateOverviewCamera(0.f, true);
}

void AVLKing::TakeControlOf(AVLKing* Unit)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!Unit || !PC || Unit->Team != Team)
	{
		return;                                 // never one of the enemy's
	}
	if (Unit == this)
	{
		if (!bDead)
		{
			SetHeroMode(true);
		}
		return;
	}
	if (Unit->IsDead() && Unit->IsTroop())
	{
		return;
	}
	// the new one looks the way this one did
	Unit->CamYaw = CamYaw;
	Unit->HomeYaw = HomeYaw;
	Unit->Zoom = Zoom;
	Unit->OverviewYaw = OverviewYaw;
	Unit->OverviewZoom = OverviewZoom;
	Unit->StopOrder();
	Unit->ClearQueue();
	StopOrder();
	TestMoveTime = 0.f;
	if (AController* Old = Unit->GetController())
	{
		Old->UnPossess();
		Old->Destroy();
	}
	MakeWay(0.f, false);                        // (whoever it passed through is solid to it again)
	PC->UnPossess();
	PC->Possess(Unit);
	SpawnDefaultController();                   // this one now stands, or walks to orders, by itself
	PC->SetControlRotation(FRotator(HeroPitch(Zoom), CamYaw, 0.f));
	Unit->SetHeroMode(true);
	// the one the player takes control of leads its platoon, and the platoon's idle members fall in behind it
	if (UVLCommand* Command = UVLCommand::Get(this))
	{
		Command->MakeLeader(Unit, true);
	}
}

void AVLKing::Attack(int32 Kind)
{
	const bool bHammer = UnitKind == TEXT("Builder") && (IsPlayerControlled() || UVLBuilderWork::IsAtWork(this));    // a builder the player plays (or one at its work) swings its hammer
	if (bTroop && !UVLSwordsmanCombat::CanFight(this) && !bHammer)
	{
		return;                                 // of the troops the swordsman fights with a sword, as the king does
	}
	if (!bArmed || Draw < 1.f)
	{
		bArmed = true;                       // out with it first; the swing follows
		bAttackQueued = true;
		if (Loaded && !Loaded->bHasSheath)
		{
			Draw = 1.f;                      // no scabbard: the sword is in his hand already, the swing starts at once
		}
		return;
	}
	if (Kind >= 0)
	{
		if (AttackTime < 0.f)
		{
			StartSwing(Kind);                // asked for by name (vl.Attack 1|2|3)
		}
		return;
	}
	if (AttackTime < 0.f)
	{
		// still in the battle stance: the next cut of the combo (side slash, diagonal cut, rising cut); otherwise the first
		StartSwing(GuardHold > 0.f ? (SwingKind >= 2 ? 0 : SwingKind + 1) : 0);
	}
	else
	{
		bComboQueued = true;                 // clicked during a swing: the next one follows on from it
	}
}

void AVLKing::StartSwing(int32 Kind)
{
	// a swing that follows another starts from wherever the blade is, not from the guard
	bSwingCarry = SwingTime >= 0.f;
	if (bSwingCarry)
	{
		FMemory::Memcpy(SwingCarry, SwingShown, sizeof(SwingCarry));
	}
	SwingKind = FMath::Clamp(Kind, 0, 2);
	if (SwingKind == 2 && UnitKind == TEXT("Builder"))
	{
		SwingKind = 3;                       // a Builder's third is his hammer's up-down-up (Swings[3]), not the sword's rising cut
	}
	AttackTime = 0.f;
	SwingTime = 0.f;
	HitsLanded = 0;
	bComboQueued = false;
	if (UVLSwordFx* Fx = UVLSwordFx::Get(this))
	{
		Fx->Swing(this);                     // the whoosh
	}
}

float AVLKing::SwingDamage() const
{
	return VLRules::Troop(UnitKind).Damage;
}

void AVLKing::HitDummies(float Share)
{
	const FVector Me = GetActorLocation();
	const FVector Fwd = GetActorForwardVector();
	// a foe in front of the blade: the one it is fighting if that is in reach, else the nearest in the arc, else a
	// foe's building whose walls are within reach
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		AActor* Struck = nullptr;
		const UVLSwordsmanCombat* Combat = UVLSwordsmanCombat::For(this, false);
		AActor* Fighting = Combat ? Combat->GetTarget() : nullptr;
		float Best = 240.f;
		// (B: the units within the blade's reach from the battle's spatial hash, in the registry's order)
		FVLUnits Near;
		Battle->UnitsNear(Me, 240.f, Near);
		for (AVLKing* Other : Near)
		{
			FVector To = Other->GetActorLocation() - Me;
			To.Z = 0.f;
			const float D = To.Size();
			if (!Battle->IsHostile(Other, Team) || D > 240.f || FMath::Abs(Other->GetActorLocation().Z - Me.Z) > 150.f || (D > 60.f && FVector::DotProduct(To / D, Fwd) < 0.1f))
			{
				continue;
			}
			if (Other == Fighting)
			{
				Struck = Other;
				break;
			}
			if (D < Best)
			{
				Best = D;
				Struck = Other;
			}
		}
		if (!Struck)
		{
			float BestB = 190.f;
			for (const FVLBuildingState& B : Battle->GetBuildings())
			{
				FVector Wall;
				if (!B.IsAlive() || B.Team == Team || B.Team < 0)
				{
					continue;
				}
				// (to its hit box for blades: its walls grown by VLRules::MeleeBuildingPad, so a blade at the eaves or a prop still lands)
				const float D = FMath::Max(0.f, Battle->DistanceTo(B.Actor.Get(), GetFeet(), &Wall) - VLRules::MeleeBuildingPad);
				const FVector To = (Wall - Me).GetSafeNormal2D();
				if (D < BestB && (D < 40.f || FVector::DotProduct(To, Fwd) > 0.f))
				{
					BestB = D;
					Struck = B.Actor.Get();
				}
			}
		}
		if (Struck && Battle->Damage(Struck, SwingDamage() * Share, this, Team) > 0.f && Cast<AVLKing>(Struck))
		{
			Battle->PlayAt(TEXT("S_SwordHit"), Struck->GetActorLocation(), 0.55f, 3500.f, 0.06f);
		}
	}
	// (B: the level's dummies from the battle's cached list, not a walk over every actor on every blow)
	TArray<AActor*, TInlineAllocator<16>> DummyList;
	if (const UVLBattle* Battle = UVLBattle::Get(this); Battle && UVLBattle::UseRegistry())
	{
		for (const TWeakObjectPtr<AActor>& D : Battle->Dummies())
		{
			if (AActor* A = D.Get())
			{
				DummyList.Add(A);
			}
		}
	}
	else
	{
		for (TActorIterator<AActor> It(GetWorld()); It; ++It)
		{
			if (It->ActorHasTag(TEXT("Dummy")))
			{
				DummyList.Add(*It);
			}
		}
	}
	for (AActor* Dummy : DummyList)
	{
		FVector To = Dummy->GetActorLocation() - Me;
		To.Z = 0.f;
		const float Dist = To.Size();
		if (Dist > 230.f || FVector::DotProduct(To.GetSafeNormal(), Fwd) < 0.2f)
		{
			continue;
		}
		// it rocks and thunks: in one place for every sword (a dummy several fighters hit rocks about its own rest pose)
		if (UVLSwordFx* Fx = UVLSwordFx::Get(this))
		{
			Fx->HitDummy(Dummy, To.GetSafeNormal(), this);
		}
	}
}

void AVLKing::UpdateOverviewCamera(float DeltaSeconds, bool bSnap)
{
	if (!OverviewCamera)
	{
		return;
	}
	// (the title screen's backdrop frames the whole map from its own distance, past the overview's zoom limits)
	const bool bTitle = TitleDistance > 0.f;
	FVector Focus = bTitle ? TitleFocus : OverviewFocus;
	const float Dist = bTitle ? TitleDistance : OverviewDistance(OverviewZoom, Focus);
	const float Pitch = bTitle ? TitlePitch : OverviewPitch(OverviewZoom);
	const FRotator Rot(Pitch, OverviewYaw, 0.f);
	// The camera and the ground (UVLCameraGround; not the title's shot, which is far over everything). The view turns
	// about a point ON the ground: the focus rides the terrain's surface (it was at height 0 everywhere, so over high
	// ground the whole view hung under it), smoothly, a little slower the further out the view is.
	UVLCameraGround* Ground = bTitle ? nullptr : UVLCameraGround::Get(this);
	if (Ground && !Ground->IsActive())
	{
		Ground = nullptr;
	}
	if (Ground)
	{
		if (!bFocusGround || !FocusGroundAt.Equals(FVector2D(Focus), 5.f))      // (asked again only once the focus has moved)
		{
			float Z = 0.f;
			if (Ground->SurfaceAt(FVector2D(Focus), Z))
			{
				FocusGroundAt = FVector2D(Focus);
				FocusGroundWant = Z;
				if (!bFocusGround)
				{
					FocusGroundZ = Z;
					bFocusGround = true;
				}
			}
		}
		if (bFocusGround)
		{
			FocusGroundZ = bSnap ? FocusGroundWant : FMath::FInterpTo(FocusGroundZ, FocusGroundWant, DeltaSeconds, FMath::Lerp(6.f, 2.5f, OverviewZoom));
			Focus.Z = FocusGroundZ;
		}
	}
	else
	{
		bFocusGround = false;
	}
	const FVector Want = Focus - Rot.Vector() * Dist;
	FVector Eye = bSnap ? Want : FMath::VInterpTo(OverviewCamera->GetActorLocation(), Want, DeltaSeconds, 9.f);
	FRotator Look = Rot;
	// and the eye itself never comes nearer the ground under it than its clearance: it is lifted there (a low angle
	// close in, a hill behind the view, a turn about a point on a slope), and looks down at the focus more steeply
	if (Ground && Ground->KeepAbove(Eye, OverviewFloor, DeltaSeconds, bSnap, UVLCameraGround::OverviewClearance(), TEXT("overview")) > 0.f)
	{
		const float Flat = FMath::Max(Dist * FMath::Cos(FMath::DegreesToRadians(Pitch)), 1.f);
		Look.Pitch = FMath::Clamp(-FMath::RadiansToDegrees(FMath::Atan2(float(Eye.Z - Focus.Z), Flat)), -89.f, Pitch);
	}
	else if (!Ground)
	{
		OverviewFloor.bValid = false;
	}
	OverviewCamera->SetActorLocationAndRotation(Eye, bSnap ? Look : FMath::RInterpTo(OverviewCamera->GetActorRotation(), Look, DeltaSeconds, 9.f));
}

AActor* AVLKing::PickUnderCursor(APlayerController* PC, FVector* Ground) const
{
	float MX = 0.f, MY = 0.f;
	if (!PC->GetMousePosition(MX, MY))
	{
		return nullptr;
	}
	return PickAt(PC, FVector2D(MX, MY), Ground);
}

AActor* AVLKing::PickAt(APlayerController* PC, const FVector2D& Point, FVector* Ground, bool bBoxes, const AActor* Skip) const
{
	const float MX = Point.X, MY = Point.Y;
	// What the pointer's ray meets first that can be seen: the hidden walls (the river's and the cliffs' barriers, the
	// map's edge), the water and the backdrop are passed through even if the level has them stopping the trace.
	FHitResult Hit;
	bool bHit = false;
	FVector Origin = FVector::ZeroVector, Dir = FVector::ForwardVector;
	const bool bRay = PC->DeprojectScreenPositionToWorld(Point.X, Point.Y, Origin, Dir);
	if (bRay)
	{
		FCollisionQueryParams Params(TEXT("Pointer"), false);
		for (int32 Try = 0; Try < 8 && !bHit; ++Try)
		{
			if (!GetWorld()->LineTraceSingleByChannel(Hit, Origin, Origin + Dir * 200000.f, ECC_Visibility, Params))
			{
				break;
			}
			const AActor* Struck = Hit.GetActor();
			if (Struck && (UVLGrid::IsUnseen(Struck) || Struck->IsA<APawn>()))
			{
				Params.AddIgnoredActor(Struck);
				continue;
			}
			bHit = true;
		}
	}
	if (bHit && Ground)
	{
		*Ground = Hit.ImpactPoint;
	}
	// the king and the troops: their capsules do not stop a visibility trace, so test their outlines on the screen
	// (the one nearest the camera wins)
	AVLKing* Best = nullptr;
	float BestDist = TNumericLimits<float>::Max();
	const FVector Eye = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : GetActorLocation();
	// (B: the units from the battle's registry; the selectable buildings below from its cached list)
	const UVLBattle* PickBattle = UVLBattle::Get(this);
	TArray<AVLKing*> PickLocal;
	if (!PickBattle)
	{
		for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
		{
			PickLocal.Add(*It);
		}
	}
	for (AVLKing* Unit : PickBattle ? PickBattle->AllUnits() : PickLocal)
	{
		if (Unit->IsDead() || Unit == Skip || UVLFog::HidesUnit(Unit))      // (an enemy in the fog of war cannot be picked)
		{
			continue;
		}
		FVector2D Feet, Head;
		const float Half = Unit->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
		if (PC->ProjectWorldLocationToScreen(Unit->GetActorLocation() - FVector(0.f, 0.f, Half), Feet) && PC->ProjectWorldLocationToScreen(Unit->GetActorLocation() + FVector(0.f, 0.f, Half), Head))
		{
			const float Tall = FMath::Max(FMath::Abs(Feet.Y - Head.Y), 18.f);
			const float Wide = Tall * 0.45f + 6.f;
			if (MX > Head.X - Wide && MX < Head.X + Wide && MY > FMath::Min(Head.Y, Feet.Y) - 8.f && MY < FMath::Max(Head.Y, Feet.Y) + 8.f)
			{
				const float D = FVector::DistSquared(Eye, Unit->GetActorLocation());
				if (D < BestDist)
				{
					BestDist = D;
					Best = Unit;
				}
			}
		}
	}
	if (Best)
	{
		// one of a tower's own archers of this side (never selected or ordered): its tower is what was clicked
		if (Best->bTowerGuard && Best->Team == Team && Best->GarrisonIn.IsValid())
		{
			return Best->GarrisonIn.Get();
		}
		return Best;
	}
	// a troop ship (it has no collision: the pointer's ray against its hull and its sail), nearer than what the ray meets
	if (AVLTroopShip* Ship = bRay ? AVLTroopShip::Pick(GetWorld(), Origin, Dir, bHit ? Hit.Distance : 200000.f) : nullptr)
	{
		return Ship;
	}
	if (bHit && Hit.GetActor() && Hit.GetActor()->ActorHasTag(TEXT("Selectable")))
	{
		return Hit.GetActor();
	}
	// Anywhere on a building counts, not only the faces the trace happens to meet first (its banners, lanterns and
	// props, the gaps in its roof, its yard, a tree in front): the pointer's ray against each selectable building's
	// own box (the mesh's bounds, turned with it); the nearest box the ray enters wins.
	// (not for orders; and never a box that lies behind what the pointer is on: a hill, a cliff, another building)
	if (bBoxes && bRay)
	{
		AActor* BestBuilding = nullptr;
		float BestT = bHit ? Hit.Distance + 1.f : TNumericLimits<float>::Max();
		TArray<AActor*, TInlineAllocator<64>> SelectableList;
		if (PickBattle && UVLBattle::UseRegistry())
		{
			for (const TWeakObjectPtr<AActor>& S : PickBattle->Selectables())
			{
				if (AActor* A = S.Get())
				{
					SelectableList.Add(A);
				}
			}
		}
		else
		{
			for (TActorIterator<AActor> It(GetWorld()); It; ++It)
			{
				if (It->ActorHasTag(TEXT("Selectable")) && !It->IsA<AVLKing>())
				{
					SelectableList.Add(*It);
				}
			}
		}
		for (AActor* A : SelectableList)
		{
			const UStaticMeshComponent* SMC = A->FindComponentByClass<UStaticMeshComponent>();
			if (!SMC || !SMC->GetStaticMesh() || UVLFog::HidesActor(A))
			{
				continue;
			}
			const FBox Local = SMC->GetStaticMesh()->GetBoundingBox();
			const FTransform& T = SMC->GetComponentTransform();
			// the ray in the mesh's own space (scale included), then a slab test against its box
			const FVector O = T.InverseTransformPosition(Origin);
			const FVector D = T.InverseTransformVector(Dir);
			float T0 = 0.f, T1 = 1e9f;
			bool bMiss = false;
			for (int32 Axis = 0; Axis < 3 && !bMiss; ++Axis)
			{
				const float Lo = Local.Min[Axis], Hi = Local.Max[Axis];
				if (FMath::Abs(D[Axis]) < 1e-6f)
				{
					bMiss = O[Axis] < Lo || O[Axis] > Hi;
					continue;
				}
				float A0 = (Lo - O[Axis]) / D[Axis], A1 = (Hi - O[Axis]) / D[Axis];
				if (A0 > A1)
				{
					Swap(A0, A1);
				}
				T0 = FMath::Max(T0, A0);
				T1 = FMath::Min(T1, A1);
				bMiss = T0 > T1;
			}
			if (bMiss)
			{
				continue;
			}
			// distance along the world ray to where it enters the box
			const float WorldT = (T.TransformPosition(O + D * T0) - Origin).Size();
			if (WorldT < BestT)
			{
				BestT = WorldT;
				BestBuilding = A;
			}
		}
		if (BestBuilding)
		{
			return BestBuilding;
		}
	}
	return nullptr;
}

bool AVLKing::OrderAt(const FVector2D& Point, bool bRun, bool bQueue)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	UVLCommand* Command = UVLCommand::Get(this);
	if (!PC || !Command)
	{
		return false;
	}
	TArray<AVLKing*> Units;
	Command->GetSelection(Units);
	FVector Ground = FVector::ZeroVector;
	AActor* Hit = PickAt(PC, Point, &Ground, false);    // a foe or the tower only where the pointer is on the thing itself
	if (AVLTroopShip::OrderFromView(this, PC, Point, Ground, bQueue))
	{
		return true;            // a troop ship is the selection: it sails there (Shift: one more point of its course)
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("order at %.0f %.0f of the view: %d unit(s), ground %s, on %s"), Point.X, Point.Y, Units.Num(), *Ground.ToCompactString(), *GetNameSafe(Hit));
	return OrderOn(Units, Hit, Ground, bRun, bQueue);
}

bool AVLKing::OrderOn(TArray<AVLKing*> Units, AActor* Hit, const FVector& Ground, bool bRun, bool bQueue, AVLKing* Rejoin)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || Units.Num() == 0 || Ground.IsZero())
	{
		return false;
	}
	// a troop ship of their side: they go aboard it (AVLTroopShip::OrderBoard)
	if (AVLTroopShip* Ship = Cast<AVLTroopShip>(Hit); Ship && Ship->GetTeam() == Team)
	{
		Ship->OrderBoard(Units, bRun);
		return true;
	}
	// one of the player's own troops (or anyone of the selection itself, as a platoon's member): the others follow
	// it; members of its platoon following it make it the platoon's leader. (King David and Builders not in the
	// selection are guarded, below.)
	if (AVLKing* Lead = Cast<AVLKing>(Hit); Lead && Lead->Team == Team && Lead->IsAlive())
	{
		const bool bInSelection = Units.Contains(Lead);
		if (bInSelection || (Lead->IsTroop() && !UVLBuilderWork::IsBuilder(Lead)))
		{
			Units.Remove(Lead);
			return Units.Num() > 0 && Command->OrderFollow(Units, Lead) > 0;
		}
	}
	const UVLBattle* Battle = UVLBattle::Get(this);
	// Builders and a site or a damaged building of their side: they go to work on it (VLConstruction.*); the rest of
	// the selection takes the order as usual
	// Builders and a loose rock or boulder (the pointer on it): they go and clear it (VLRocks.*). The rest of the
	// selection takes the order as usual
	if (UVLRocks* Rocks = UVLRocks::Get(this); Rocks && (!Hit || UVLRocks::IsRock(Hit))
		&& Units.ContainsByPredicate([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); }))
	{
		if (AActor* Rock = UVLRocks::IsRock(Hit) ? Hit : Rocks->RockAt(Ground, 15.f); Rock && Rocks->OrderClear(Units, Rock, bQueue))
		{
			Units.RemoveAll([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); });
			if (Units.Num() == 0)
			{
				return true;
			}
		}
	}
	// Builders and a free gold mine (a neutral one, or one fallen and abandoned): they claim it (the mine's price; it
	// is theirs when they have worked it through). The rest of the selection takes the order as usual
	if (UVLConstruction* Construction = UVLConstruction::Get(this); Hit && Construction && Construction->IsFreeMine(Hit)
		&& Units.ContainsByPredicate([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); }))
	{
		Construction->ClaimMine(Hit, Team, Units.FilterByPredicate([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); }), nullptr, false, bQueue);      // (refused: it says why; Shift: queued)
		Units.RemoveAll([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); });
		if (Units.Num() == 0)
		{
			return true;
		}
	}
	if (UVLConstruction* Construction = UVLConstruction::Get(this); Hit && Battle && Battle->TeamOf(Hit) == Team && Construction && Construction->OrderWork(Units, Hit, true, bQueue))
	{
		Units.RemoveAll([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); });
		if (Units.Num() == 0)
		{
			return true;
		}
	}
	// Shift with Builders: a walk on the end of their queues (after their jobs too, not only their walks)
	// (not on a foe: Builders take no part in an attack)
	if (UVLConstruction* Construction = UVLConstruction::Get(this); bQueue && Construction && !(Hit && Battle && Battle->IsHostile(Hit, Team))
		&& Construction->QueueMove(Units, Ground, bRun))
	{
		Units.RemoveAll([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); });
		if (Units.Num() == 0)
		{
			return true;
		}
	}
	if (Hit && Battle && Battle->IsHostile(Hit, Team) && Units.ContainsByPredicate([](const AVLKing* U) { return UVLCommand::CanAttack(U); }))
	{
		// a foe (a unit, a building): attack it; Shift: after what they are doing, on the end of their chain
		Command->OrderChain(Units, Hit, Ground, bRun, Command->SelectionFormation(), bQueue, Rejoin);
	}
	else if (Hit && UVLCommand::IsTower(Hit) && (!Battle || Battle->TeamOf(Hit) == Team || Battle->TeamOf(Hit) == UVLBattle::Neutral)
		&& Units.ContainsByPredicate([](const AVLKing* U) { return U->IsRanged(); }))
	{
		Command->OrderGarrison(Units, Hit, bRun);       // onto the watch tower
	}
	else if (Hit && !bQueue && Command->CanBeGuarded(Hit, Team) && Units.ContainsByPredicate([](const AVLKing* U) { return U->GetKind() != TEXT("Builder"); }))
	{
		// one of the player's own buildings, Builders or King David: the troops guard it (the main game's right
		// click); Builders with them go there
		Command->OrderGuard(Units, Hit);
		TArray<AVLKing*> Builders = Units.FilterByPredicate([](const AVLKing* U) { return U->GetKind() == TEXT("Builder"); });
		if (Builders.Num() > 0)
		{
			Command->OrderMove(Builders, Ground, bRun, Command->SelectionFormation(), bQueue);
		}
	}
	else if (bQueue && Units.ContainsByPredicate([Command](const AVLKing* U) { return Command->HasChain(U) || UVLCommand::IsInOrderedFight(U); }))
	{
		// Shift with a chain of attacks under way (or an attack they were ordered into): the walk is its next order
		Command->OrderChain(Units, nullptr, Ground, bRun, Command->SelectionFormation(), true, Rejoin);
	}
	else
	{
		Command->OrderMove(Units, Ground, bRun, Command->SelectionFormation(), bQueue);
	}
	return true;
}

// ------------------------------------------------------------------------------------------------ the hero view's commands

bool AVLKing::HeroCrossPoint(APlayerController* PC, FVector2D& Out) const
{
	if (!PC)
	{
		return false;
	}
	if (HeroTestAimTime > 0.f)
	{
		return PC->ProjectWorldLocationToScreen(HeroTestAim, Out);     // (vl.HeroAim: as if the crosshair were there)
	}
	if (bMouseLookActive)
	{
		int32 SX = 0, SY = 0;
		PC->GetViewportSize(SX, SY);
		Out = FVector2D(SX * 0.5f, SY * CrosshairHeight);
		return SX > 0;
	}
	float MX = 0.f, MY = 0.f;
	if (!PC->GetMousePosition(MX, MY))
	{
		return false;
	}
	Out = FVector2D(MX, MY);
	return true;
}

bool AVLKing::HeroClickSelects(APlayerController* PC, AVLKing** OutUnit) const
{
	if (OutUnit)
	{
		*OutUnit = nullptr;
	}
	if (!PC || !bHeroMode)
	{
		return false;
	}
	const bool bCtrl = PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl) || PC->IsInputKeyDown(EKeys::LeftCommand)
		|| PC->IsInputKeyDown(EKeys::RightCommand);
	if (bCtrl)
	{
		return false;                       // (Ctrl / Cmd + click: an order, the right click's)
	}
	AVLKing* Hover = HeroHover.Get();
	if (HeroTestAimTime > 0.f || !Hover)
	{
		FVector2D Cross;
		Hover = HeroCrossPoint(PC, Cross) ? Cast<AVLKing>(PickAt(PC, Cross, nullptr, false, this)) : nullptr;
	}
	const bool bOwn = Hover && Hover->Team == Team && Hover->IsAlive() && Hover != this;
	if (OutUnit && bOwn)
	{
		*OutUnit = Hover;
	}
	return IsCommandMode();                 // a click in command mode selects; else it is the unit's own blow
}

bool AVLKing::HeroPick(APlayerController* PC, AActor*& OutHit, FVector& OutGround) const
{
	OutHit = nullptr;
	OutGround = FVector::ZeroVector;
	FVector Origin, Dir;
	FVector2D Cross;
	if (!PC || !HeroCrossPoint(PC, Cross) || !PC->DeprojectScreenPositionToWorld(Cross.X, Cross.Y, Origin, Dir))
	{
		return false;
	}
	// a unit drawn under it (never this one), as a click in the overview finds it
	if (AVLKing* Unit = Cast<AVLKing>(PickAt(PC, Cross, nullptr, false, this)))
	{
		OutHit = Unit;
		OutGround = Unit->GetFeet();
		return true;
	}
	// else what the aim meets ahead of him (as the sword's and the bow's aim: nothing between the camera and him)
	bool bSky = false;
	AActor* Struck = nullptr;
	FVector Point;
	if (!GetAimPointAlong(Origin, Dir, Point, 3000.f, &bSky, &Struck) || bSky)
	{
		return false;
	}
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (Struck && (Cast<AVLKing>(Struck) || Struck->ActorHasTag(TEXT("Selectable")) || (Battle && Battle->FindBuilding(Struck))))
	{
		OutHit = Struck;
	}
	OutGround = Point;
	return true;
}

bool AVLKing::HeroOrder(APlayerController* PC, bool bRun, bool bQueue)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return false;
	}
	TArray<AVLKing*> Units;
	Command->GetSelection(Units);
	Units.Remove(this);             // (the one played is the player's to move)
	if (Units.Num() == 0)
	{
		return false;
	}
	AActor* Hit = nullptr;
	FVector Ground;
	if (!HeroPick(PC, Hit, Ground))
	{
		return false;
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("hero order: %d unit(s), ground %s, on %s%s"), Units.Num(), *Ground.ToCompactString(), *GetNameSafe(Hit), bQueue ? TEXT(" (queued)") : TEXT(""));
	return OrderOn(Units, Hit, Ground, bRun, bQueue);
}

void AVLKing::HeroCommanded(TArray<AVLKing*>& Out, bool* bOutFollowers) const
{
	Out.Reset();
	if (bOutFollowers)
	{
		*bOutFollowers = false;
	}
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return;
	}
	// the selection (never the unit played); else those following him; else his platoon
	Command->GetSelection(Out);
	Out.Remove(const_cast<AVLKing*>(this));
	if (Out.Num() == 0)
	{
		// (and those off on a chain of attacks who fall in behind him again after it: still his to command)
		Command->GetFollowers(this, Out);
		TArray<UVLCommand::FChainView> Chains;
		Command->GetChains(Chains);
		for (const UVLCommand::FChainView& C : Chains)
		{
			if (C.Rejoin == this)
			{
				for (AVLKing* M : C.Members)
				{
					Out.AddUnique(M);
				}
			}
		}
		if (bOutFollowers)
		{
			*bOutFollowers = Out.Num() > 0;
		}
	}
	if (Out.Num() == 0)
	{
		Command->GetPlatoon(Command->PlatoonIndexOf(this), Out);
		Out.Remove(const_cast<AVLKing*>(this));
	}
}

void AVLKing::SetCommandMode(bool bOn)
{
	if (bOn == bCommandMode)
	{
		return;
	}
	bCommandMode = bOn;
	bCommandChain = false;
	bChainHeldByTest = false;
	HeroLastClicked = nullptr;
	UE_LOG(LogSovereignRealms, Log, TEXT("hero: command mode %s"), bOn ? TEXT("on") : TEXT("off"));
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		Battle->Play2D(TEXT("S_UIClick"), 0.5f);
	}
}

void AVLKing::GetCommandArmy(TArray<AVLKing*>& Out) const
{
	// the army: every swordsman and archer of his side that can be ordered. Not King David, not the unit played, not
	// Jonathan (a hero, played with J), not Builders or the Spy, not a watch tower's own archers, not those on a
	// tower's lookout or aboard a ship (garrisoned), not the ambient ones.
	Out.Reset();
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle)
	{
		return;
	}
	for (AVLKing* U : Battle->AllUnits())
	{
		if (!U || U == this || U->Team != Team || !U->IsAlive() || !U->IsTroop() || U->bAmbient || U->bTowerGuard || U->IsGarrisoned())
		{
			continue;
		}
		const EVLUnitKind K = U->KindId();
		if (K == EVLUnitKind::Swordsman || K == EVLUnitKind::Archer || K == EVLUnitKind::Other)
		{
			Out.Add(U);
		}
	}
}

void AVLKing::GetCommandPlanned(TArray<AVLKing*>& Out) const
{
	Out.Reset();
	for (const TWeakObjectPtr<AVLKing>& W : CommandPlanned)
	{
		if (AVLKing* U = W.Get(); U && U->IsAlive())
		{
			Out.Add(U);
		}
	}
}

void AVLKing::EndCommandChain()
{
	bChainHeldByTest = false;
	if (!bCommandChain)
	{
		return;
	}
	bCommandChain = false;
	if (UVLCommand* Command = UVLCommand::Get(this))
	{
		Command->ClearSelection();      // the chain is given: they keep it, and the next selection starts empty
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("hero command: the Shift chain is given; the selection let go"));
}

void AVLKing::CommandSelect(APlayerController* PC, bool bShift)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return;
	}
	AActor* Hit = nullptr;
	FVector Ground;
	HeroPick(PC, Hit, Ground);
	AVLKing* HitUnit = Cast<AVLKing>(Hit);
	if (HitUnit && HitUnit->Team == Team && HitUnit->IsAlive() && HitUnit != this)
	{
		// one of his own: selected alone (Shift: added or taken out); twice quickly: played. (Never a guard order: a
		// friend is guarded with a right click on King David, a Builder or a building.)
		const double Now = GetWorld()->GetRealTimeSeconds();
		if (!bShift && HeroLastClicked.Get() == HitUnit && Now - HeroLastClickTime < 0.4)
		{
			HeroLastClicked = nullptr;
			TakeControlOf(HitUnit);
			return;
		}
		HeroLastClicked = HitUnit;
		HeroLastClickTime = Now;
		if (bShift)
		{
			Command->Toggle(HitUnit);
		}
		else
		{
			Command->Select({ HitUnit });
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("hero command mode: select %s%s (%d selected)"), *HitUnit->GetDisplayName(), bShift ? TEXT(" toggled") : TEXT(""), Command->NumSelected());
		if (UVLBattle* Battle = UVLBattle::Get(this))
		{
			Battle->Play2D(TEXT("S_UIClick"), 0.4f);
		}
		return;
	}
	HeroLastClicked = nullptr;
	if (!bShift && Command->NumSelected() > 0)
	{
		Command->ClearSelection();          // a click off his own: the selection is let go
		UE_LOG(LogSovereignRealms, Log, TEXT("hero command mode: selection let go (clicked %s)"), *GetNameSafe(Hit));
	}
}

bool AVLKing::CommandOrder(APlayerController* PC, bool bQueue)
{
	UVLCommand* Command = UVLCommand::Get(this);
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!Command)
	{
		return false;
	}
	const double Now = GetWorld()->GetRealTimeSeconds();
	const bool bDouble = !bQueue && Now - HeroLastOrderTime < 0.35;
	HeroLastOrderTime = Now;
	TArray<AVLKing*> Units;
	Command->GetSelection(Units);
	Units.Remove(this);
	if (Units.Num() == 0 && bDouble)
	{
		// the second right click of a quick pair: the units just ordered (and let go) go at a run
		for (const TWeakObjectPtr<AVLKing>& W : CommandLastOrdered)
		{
			if (AVLKing* U = W.Get(); U && U->IsAlive())
			{
				Units.Add(U);
			}
		}
	}
	bool bAll = false;
	if (Units.Num() == 0)
	{
		// nobody selected: the whole army takes it (GetCommandArmy)
		GetCommandArmy(Units);
		bAll = true;
	}
	if (Units.Num() == 0)
	{
		if (Battle)
		{
			Battle->PushAlert(TEXT("Command mode: no troops to command (train swordsmen or archers)"));
			Battle->Play2D(TEXT("S_UIError"), 0.4f);
		}
		return false;
	}
	AActor* Hit = nullptr;
	FVector Ground;
	if (!HeroPick(PC, Hit, Ground))
	{
		return false;                       // (the sky)
	}
	if (FVector2D Cross; HeroTestAimTime <= 0.f && HeroCrossPoint(PC, Cross) && PickAt(PC, Cross, nullptr, false) == this)
	{
		Hit = this;                         // the pointer on him: they guard him (OrderOn)
		Ground = GetFeet();
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("hero command mode: order %d unit(s)%s, ground %s, on %s%s%s"), Units.Num(), bAll ? TEXT(" (all the army: nobody selected)") : TEXT(""),
		*Ground.ToCompactString(), *GetNameSafe(Hit), bQueue ? TEXT(" (queued)") : TEXT(""), bDouble ? TEXT(" (at a run)") : TEXT(""));
	if (!OrderOn(Units, Hit, Ground, bDouble, bQueue))
	{
		return false;
	}
	AVLGameMode::PlayOrderSound(this);
	CommandLastOrdered.Reset();
	for (AVLKing* U : Units)
	{
		CommandLastOrdered.Add(U);
		CommandPlanned.AddUnique(U);
	}
	if (bQueue)
	{
		bCommandChain = true;               // let go when Shift is (HeroCommands)
	}
	else
	{
		bCommandChain = false;
		Command->ClearSelection();          // given: they keep it, and the next selection starts empty
	}
	return true;
}

bool AVLKing::HeroCommands(APlayerController* PC, bool bClickSpent)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return false;
	}
	const bool bShift = PC->IsInputKeyDown(EKeys::LeftShift) || PC->IsInputKeyDown(EKeys::RightShift);
	const bool bCtrl = PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl) || PC->IsInputKeyDown(EKeys::LeftCommand)
		|| PC->IsInputKeyDown(EKeys::RightCommand);
	auto Order = [&]()
	{
		// twice quickly: at a run; Shift: on the end of their pathways (Builders: their queues)
		const double Now = GetWorld()->GetRealTimeSeconds();
		const bool bDouble = Now - HeroLastOrderTime < 0.35;
		HeroLastOrderTime = Now;
		if (HeroOrder(PC, bDouble, bShift))
		{
			AVLGameMode::PlayOrderSound(this);
		}
	};
	// what the crosshair is on (a unit), for the HUD's hint and the click below
	HeroTestAimTime = FMath::Max(0.f, HeroTestAimTime - GetWorld()->GetDeltaSeconds());
	{
		FVector2D Cross;
		HeroHover = HeroCrossPoint(PC, Cross) ? Cast<AVLKing>(PickAt(PC, Cross, nullptr, false, this)) : nullptr;
		AVLKing* Own = nullptr;
		HeroClickSelects(PC, &Own);
		bHeroHoverSelect = Own != nullptr;  // (the hint: in command mode a click selects it)
	}
	bool bTook = bClickSpent;
	// R: command mode on / off (IsCommandMode)
	if (PC->WasInputKeyJustPressed(EKeys::R) && !bCtrl)
	{
		SetCommandMode(!bCommandMode);
	}
	// those ordered from command mode stay in its plan while they are on that order
	CommandPlanned.RemoveAll([Command](const TWeakObjectPtr<AVLKing>& W)
		{
			const AVLKing* U = W.Get();
			return !U || !U->IsAlive() || !(U->IsOnOrder() || Command->HasChain(U) || UVLCommand::IsInOrderedFight(U));
		});
	if (bCommandMode)
	{
		// command mode: the mouse commands (the pointer is shown), never a swing
		if (bClickSpent)
		{
			HeroClickFrame = GFrameCounter;  // (the interface's click)
		}
		else if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton))
		{
			HeroClickFrame = GFrameCounter;
			bTook = true;
			if (bCtrl)
			{
				CommandOrder(PC, bShift);   // Ctrl / Cmd + click: the right click's (a trackpad's)
			}
			else
			{
				CommandSelect(PC, bShift);
			}
			if (PC->GetPawn() != this)
			{
				return true;                // (took control of another)
			}
		}
		// the right click orders at the crosshair (the mouse still looks round; with the pointer shown, as C's postcard
		// shows it, a click let go without dragging, as in the overview)
		if (bMouseLookActive ? PC->WasInputKeyJustPressed(EKeys::RightMouseButton) : (PC->WasInputKeyJustReleased(EKeys::RightMouseButton) && RightTravel < 6.f))
		{
			CommandOrder(PC, bShift);
		}
		// the end of a Shift chain: Shift let go (the chain is theirs; the selection goes)
		if (bCommandChain && !bShift && !bChainHeldByTest)
		{
			EndCommandChain();
		}
	}
	else if (bClickSpent)
	{
		HeroClickFrame = GFrameCounter;      // (the interface's click: not a swing, a bash or a lock)
	}
	else if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton))
	{
		if (bCtrl)
		{
			Order();                        // Ctrl / Cmd + click: an order (the archer's and the spy's, a trackpad's)
			bTook = true;
		}
		if (bTook)
		{
			HeroClickFrame = GFrameCounter;  // (not a swing, a bash or a lock)
		}
	}
	// (R was a command at the crosshair, a779f80; since 2026-11-24 it turns command mode on and off, above, and the
	// Option / Alt + click commands are gone: command mode does them. In the hero view Home puts the camera back.)
	if (PC->GetPawn() != this)
	{
		return true;                        // (took control of another)
	}
	// out of command mode the right button orders the selection, unless the unit played uses it (the archer's bow, the
	// spy's glass). With the pointer shown a right drag turns the view, so then the order is on a click let go without
	// dragging, as in the overview.
	if (!bCommandMode && !bRightMouseAims)
	{
		if (bMouseLookActive ? PC->WasInputKeyJustPressed(EKeys::RightMouseButton) : (PC->WasInputKeyJustReleased(EKeys::RightMouseButton) && RightTravel < 6.f))
		{
			Order();
		}
	}
	// 1..6: select platoon N (as in the overview)
	static const FKey Digits[UVLCommand::MaxPlatoons] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six };
	for (int32 i = 0; i < UVLCommand::MaxPlatoons; ++i)
	{
		if (PC->WasInputKeyJustPressed(Digits[i]) && !bCtrl && !bShift)
		{
			TArray<AVLKing*> Members;
			Command->GetPlatoon(i, Members);
			if (Members.Num() > 0)
			{
				Command->Select(Members);
				if (UVLBattle* Battle = UVLBattle::Get(this))
				{
					Battle->Play2D(TEXT("S_UIClick"), 0.4f);
				}
			}
		}
	}
	// G: "follow me": the selection (none selected: his platoon) falls in behind the one played; his own platoon's
	// members following him make him its leader
	if (PC->WasInputKeyJustPressed(EKeys::G))
	{
		TArray<AVLKing*> Units;
		Command->GetSelection(Units);
		Units.Remove(this);
		if (Units.Num() == 0)
		{
			Command->GetPlatoon(Command->PlatoonIndexOf(this), Units);
			Units.Remove(this);
		}
		if (Command->OrderFollow(Units, this) > 0)
		{
			AVLGameMode::PlayOrderSound(this);
		}
		else if (UVLBattle* Battle = UVLBattle::Get(this))
		{
			Battle->PushAlert(TEXT("Follow me: select troops first (1-6, or R: command mode, and click one)"));
			Battle->Play2D(TEXT("S_UIError"), 0.4f);
		}
	}
	return bTook;
}

// ------------------------------------------------------------------------------------------------ making way

void AVLKing::MakeWay(float DeltaSeconds, bool bActive)
{
	UCapsuleComponent* Cap = GetCapsuleComponent();
	const UVLBattle* Battle = UVLBattle::Get(this);
	TArray<AVLKing*, TInlineAllocator<16>> Near;
	if (bActive && Battle && IsAlive() && Cap)
	{
		const FVector Loc = GetActorLocation();
		const FVector2D Vel(GetVelocity());
		const float Speed = Vel.Size();
		const FVector2D Input(GetLastMovementInputVector());
		// the way it goes (or, against someone it has not got moving yet, the way the keys push it)
		const FVector2D Dir = Speed > 30.f ? Vel / Speed : (Input.SizeSquared() > 0.01f ? Input.GetSafeNormal() : FVector2D::ZeroVector);
		const float MyR = Cap->GetScaledCapsuleRadius();
		const float Look = FMath::Clamp(Speed * 0.45f, 0.f, 320.f);   // (a run clears the way further ahead)
		FVLUnits Others;
		Battle->UnitsNear(Loc, 600.f, Others);
		for (AVLKing* O : Others)
		{
			if (O == this || O->IsDead() || O->IsGarrisoned())
			{
				continue;           // (one on the tower's lookout is up there)
			}
			const FVector OL = O->GetActorLocation();
			const FVector2D Rel(OL - Loc);
			if (FMath::Abs(OL.Z - Loc.Z) > 160.f || Rel.SizeSquared() > FMath::Square(600.f))
			{
				continue;
			}
			const UVLSwordsmanCombat* OSw = UVLSwordsmanCombat::For(O, false);
			const UVLArcherCombat* OBw = UVLArcherCombat::For(O, false);
			const bool bFighting = (OSw && OSw->IsAttacking()) || (OBw && OBw->IsAttacking()) || GetWorld()->GetTimeSeconds() - O->LastStruckTime < 3.0;
			const bool bFoe = O->Team != Team;
			if (bFoe && bFighting)
			{
				continue;           // a foe in a fight holds its ground: solid, no yielding
			}
			if (!bFoe)
			{
				Near.Add(O);        // (one's own: walked through while it steps aside; a foe stays solid)
			}
			const float Touch = MyR + O->GetCapsuleComponent()->GetScaledCapsuleRadius() + 30.f;
			FVector2D Push = FVector2D::ZeroVector;
			float Strength = 0.f;
			if (!Dir.IsZero())
			{
				// in its path (or about to be): aside, off the side it is on, and a little ahead
				const float Along = FVector2D::DotProduct(Rel, Dir);
				const float Side = Dir.X * Rel.Y - Dir.Y * Rel.X;
				if (Along > -Touch * 0.5f && Along < Look + Touch && FMath::Abs(Side) < Touch)
				{
					const float Sgn = FMath::Abs(Side) > 4.f ? FMath::Sign(Side) : ((GetTypeHash(O->GetFName()) & 1) ? 1.f : -1.f);
					Push = FVector2D(-Dir.Y, Dir.X) * Sgn + Dir * 0.35f;
					Strength = FMath::Clamp(1.2f - Along / (Look + Touch), 0.35f, 1.f);
				}
			}
			const float D = Rel.Size();
			if (Strength <= 0.f && D < Touch - 10.f && D > 1.f)
			{
				Push = Rel / D;     // standing in it: straight out
				Strength = 0.5f;
			}
			if (Strength > 0.f)
			{
				// one of his own in a fight gives way only half as readily; so does a foe that is not fighting
				if (bFighting || bFoe)
				{
					Strength *= 0.5f;
				}
				O->YieldTo(Push.GetSafeNormal(), Strength, FMath::Max(Speed, O->WalkSpeed), this);
			}
		}
	}
	// its moves pass through those near it, and theirs through it; the rest are solid to it again
	for (AVLKing* O : Near)
	{
		if (!WayIgnored.Contains(O))
		{
			Cap->IgnoreActorWhenMoving(O, true);
			O->GetCapsuleComponent()->IgnoreActorWhenMoving(this, true);
			WayIgnored.Add(O);
		}
	}
	for (int32 i = WayIgnored.Num() - 1; i >= 0; --i)
	{
		AVLKing* O = WayIgnored[i].Get();
		if (O && Near.Contains(O))
		{
			continue;
		}
		if (O)
		{
			Cap->IgnoreActorWhenMoving(O, false);
			O->GetCapsuleComponent()->IgnoreActorWhenMoving(this, false);
		}
		WayIgnored.RemoveAt(i);
	}
}

void AVLKing::YieldTo(const FVector2D& Dir, float Strength, float Speed, AVLKing* From)
{
	YieldFrom = From;
	if (!bYielding)
	{
		bYielding = true;
		YieldHome = GetFeet();
		YieldHomeYaw = GetActorRotation().Yaw;
		bYieldReturn = !bAutoWalk;      // (one walking to an order walks on to it)
		UE_LOG(LogSovereignRealms, Log, TEXT("%s makes way at %.0f %.0f%s"), *DisplayName, YieldHome.X, YieldHome.Y, bYieldReturn ? TEXT("") : TEXT(" (on its order)"));
	}
	YieldWish += Dir * Strength;
	YieldSpeed = FMath::Max(YieldSpeed, Speed);
	YieldClock = 0.f;
}

bool AVLKing::YieldDirection(FVector2D& Dir, bool bTurn) const
{
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!Grid || !Grid->IsBuilt())
	{
		return true;                    // (no grid in this level: as it is)
	}
	const FVector Feet = GetFeet();
	const int32 Here = Grid->NodeAt(Feet, 80.f);
	const int32 Region = Here != INDEX_NONE ? Grid->RegionOf(Here) : 0;
	static const float Turns[7] = { 0.f, 35.f, -35.f, 70.f, -70.f, 110.f, -110.f };
	for (int32 t = 0; t < (bTurn ? 7 : 1); ++t)
	{
		const FVector2D D = Dir.GetRotated(Turns[t]);
		bool bOpen = true;
		for (const float Step : { 45.f, 95.f })
		{
			const int32 N = Grid->NodeAt(Feet + FVector(D * Step, 0.f), 70.f);
			if (N == INDEX_NONE || (Region != 0 && Grid->RegionOf(N) != Region) || Grid->Submerged(Grid->NodePos(N)))
			{
				bOpen = false;          // a wall, a building, a drop, the water, other ground
				break;
			}
		}
		if (bOpen)
		{
			Dir = D;
			return true;
		}
	}
	return false;
}

bool AVLKing::TickYield(float DeltaSeconds, FVector& OutWish)
{
	if (!bYielding)
	{
		return false;
	}
	YieldClock += DeltaSeconds;
	UCharacterMovementComponent* Move = GetCharacterMovement();
	if (!YieldWish.IsNearlyZero())
	{
		// pushed this frame: aside, as quick as the one coming (no quicker than its run)
		FVector2D Dir = YieldWish.GetSafeNormal();
		const float Strength = FMath::Clamp(float(YieldWish.Size()), 0.25f, 1.f);
		YieldWish = FVector2D::ZeroVector;
		const float Speed = YieldSpeed;
		YieldSpeed = 0.f;
		if (!YieldDirection(Dir, true))
		{
			return false;               // nowhere to go: it lets the played unit pass through
		}
		Move->MaxWalkSpeed = FMath::Clamp(Speed * 1.1f, WalkSpeed, RunSpeed);
		OutWish = FVector(Dir * Strength, 0.f);
		return true;
	}
	if (!bYieldReturn || YieldClock > 8.f)
	{
		if (bYieldReturn)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("%s stays where it made way (its spot is still taken)"), *DisplayName);
		}
		bYielding = false;
		return false;
	}
	if (YieldClock < 0.6f)
	{
		return false;                   // a moment, then back to its spot
	}
	if (const AVLKing* From = YieldFrom.Get(); From && FVector::Dist2D(From->GetFeet(), YieldHome) < 125.f)
	{
		return false;                   // the played unit stands on its spot: it waits (up to the 8 s) rather than push back in
	}
	const FVector2D To(YieldHome - GetFeet());
	if (To.Size() < 30.f)
	{
		// back: it turns the way it faced before
		const float Yaw = GetActorRotation().Yaw;
		if (FMath::Abs(FMath::FindDeltaAngleDegrees(Yaw, YieldHomeYaw)) < 4.f || Move->IsFalling())
		{
			bYielding = false;
			UE_LOG(LogSovereignRealms, Log, TEXT("%s is back at its spot"), *DisplayName);
		}
		else
		{
			SetActorRotation(FRotator(0.f, FMath::FixedTurn(Yaw, YieldHomeYaw, 420.f * DeltaSeconds), 0.f));
		}
		return false;
	}
	FVector2D Dir = To.GetSafeNormal();
	if (!YieldDirection(Dir, true))     // (round a step or a post as the push does: the first way that can be walked)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("%s stays where it made way (no open way back)"), *DisplayName);
		bYielding = false;
		return false;
	}
	Move->MaxWalkSpeed = WalkSpeed;
	OutWish = FVector(Dir * FMath::Clamp(float(To.Size()) / 120.f, 0.35f, 1.f), 0.f);
	return true;
}

void AVLKing::BoxSelect(const FVector2D& A, const FVector2D& B, bool bShift)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	UVLCommand* Command = UVLCommand::Get(this);
	if (!PC || !Command)
	{
		return;
	}
	// everything whose feet or chest lies in the box (as the main game gathers them)
	const FVector2D Lo(FMath::Min(A.X, B.X) - 6.f, FMath::Min(A.Y, B.Y) - 6.f);
	const FVector2D Hi(FMath::Max(A.X, B.X) + 6.f, FMath::Max(A.Y, B.Y) + 6.f);
	TArray<AVLKing*> InBox;
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		if (It->IsDead() || It->Team != Team)
		{
			continue;           // the box gathers only the player's own
		}
		const FVector Probe[2] = { It->GetFeet(), It->GetActorLocation() + FVector(0.f, 0.f, 30.f) };
		for (const FVector& P : Probe)
		{
			FVector2D Screen;
			if (PC->ProjectWorldLocationToScreen(P, Screen) && Screen.X >= Lo.X && Screen.X <= Hi.X && Screen.Y >= Lo.Y && Screen.Y <= Hi.Y)
			{
				InBox.Add(*It);
				break;
			}
		}
	}
	if (InBox.Num() > 0 || !bShift)             // (an empty box lets everything go)
	{
		Command->Select(InBox, bShift);
		TArray<AVLKing*> Units;
		Command->GetSelection(Units);
		Selected = Units.Num() > 0 ? Units[0] : nullptr;
	}
}

bool AVLKing::ClickAt(const FVector2D& Point, bool bShift)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	UVLCommand* Command = UVLCommand::Get(this);
	if (!PC || !Command)
	{
		return false;
	}
	AActor* Hit = PickAt(PC, Point);
	AVLKing* HitUnit = Cast<AVLKing>(Hit);
	UVLBattle* Battle = UVLBattle::Get(this);
	// an armed click (P, V, A: the main game's patrol, guard, attack-move)
	if (const EVLArm Armed = Command->GetArmed(); Armed == EVLArm::Patrol || Armed == EVLArm::Guard || Armed == EVLArm::AttackMove)
	{
		TArray<AVLKing*> Sel;
		Command->GetSelection(Sel);
		Command->Arm(EVLArm::None);
		if (Armed == EVLArm::Patrol && AVLTroopShip::PatrolClick(this, PC, Point, bShift))
		{
			if (bShift)
			{
				Command->Arm(EVLArm::Patrol);       // a troop ship's patrol: Shift, one more point, and P stays armed
			}
			return true;
		}
		if (Armed == EVLArm::Guard)
		{
			// (a troop too, since 2026-11-22: its platoon if it is in one and the guards are not all of it)
			if (HitUnit && HitUnit->Team == Team && HitUnit->IsTroop() && Command->CanBeGuarded(Hit, Team, true))
			{
				const int32 P = Command->PlatoonIndexOf(HitUnit);
				const bool bPlatoon = P != INDEX_NONE && Sel.ContainsByPredicate([Command, P](const AVLKing* U) { return Command->PlatoonIndexOf(U) != P; });
				if ((bPlatoon ? Command->OrderGuardPlatoon(Sel, P) : Command->OrderGuard(Sel, Hit, true)) > 0)
				{
					return true;
				}
			}
			else if (Hit && Command->CanBeGuarded(Hit, Team) && Command->OrderGuard(Sel, Hit) > 0)
			{
				return true;
			}
			if (Battle)
			{
				Battle->PushAlert(TEXT("Guard: click one of your buildings or units"));
				Battle->Play2D(TEXT("S_UIError"), 0.4f);
			}
			return false;
		}
		if (Armed == EVLArm::AttackMove && Hit && Battle && Battle->IsHostile(Hit, Team))
		{
			Command->OrderAttack(Sel, Hit, false);     // A, then a click on a foe: attack it
			return true;
		}
		FVector Ground = FVector::ZeroVector;
		PickAt(PC, Point, &Ground, false);
		if (Ground.IsZero())
		{
			return false;
		}
		if (Armed == EVLArm::Patrol)
		{
			// Shift: one more point of the patrol, and P stays armed for the next
			if (bShift)
			{
				Command->ExtendPatrol(Sel, Ground, Command->SelectionFormation());
				Command->Arm(EVLArm::Patrol);
			}
			else
			{
				Command->OrderPatrol(Sel, { Ground }, false, Command->SelectionFormation());
			}
		}
		else
		{
			Command->OrderAttackMove(Sel, Ground, false, Command->SelectionFormation(), bShift);
			if (bShift)
			{
				Command->Arm(EVLArm::AttackMove);  // Shift: one more point of the way
			}
		}
		return true;
	}
	if (Hit && Battle && Battle->IsHostile(Hit, Team))
	{
		// a foe (a unit or a building), with fighters selected: they attack it (Shift: at a run). Without: it is shown
		TArray<AVLKing*> Fighters;
		Command->GetSelection(Fighters);
		if (Command->OrderAttack(Fighters, Hit, bShift) > 0)
		{
			return true;
		}
		if (!bShift)
		{
			Command->ClearSelection();
			Selected = Hit;         // (read only: the player cannot command the enemy's)
			LastClicked = nullptr;
		}
		return false;
	}
	if (HitUnit && HitUnit->Team != Team)
	{
		HitUnit = nullptr;          // (a fallen or neutral one)
		Hit = nullptr;
	}
	if (!HitUnit && Command->IsAttackGroundArmed())
	{
		// A, then a click on the ground: the selection's archers shoot at that spot
		FVector Ground = FVector::ZeroVector;
		PickAt(PC, Point, &Ground);
		TArray<AVLKing*> Shooters;
		Command->GetSelection(Shooters);
		Command->ArmAttackGround(false);
		if (!Ground.IsZero() && Command->OrderAttackGround(Shooters, Ground, bShift) > 0)
		{
			return true;
		}
	}
	if (!HitUnit)
	{
		// a training dummy, with fighters selected: they attack it (Shift: at a run). A unit in front of it is still
		// a unit to select; with nobody selected who can fight, the click is the usual one.
		if (AActor* Dummy = Command->DummyAt(PC, Point))
		{
			TArray<AVLKing*> Fighters;
			Command->GetSelection(Fighters);
			if (Command->OrderAttack(Fighters, Dummy, bShift) > 0)
			{
				return true;
			}
		}
	}
	const double Now = GetWorld()->GetRealTimeSeconds();
	if (HitUnit && Hit == LastClicked.Get() && Now - LastClickTime < 0.4 && !bShift)
	{
		TakeControlOf(HitUnit);     // double click on a unit: take control of it
		return false;
	}
	LastClicked = Hit;
	LastClickTime = Now;
	if (HitUnit)
	{
		if (bShift)
		{
			Command->Toggle(HitUnit);
		}
		else
		{
			Command->Select({ HitUnit });
		}
		TArray<AVLKing*> Units;
		Command->GetSelection(Units);
		Selected = Units.Contains(HitUnit) ? HitUnit : (Units.Num() > 0 ? Units[0] : nullptr);
	}
	else if (!bShift)
	{
		Command->ClearSelection();  // a building, or the ground: the units are let go
		Selected = Hit;
	}
	return false;
}

bool AVLKing::SelectKindAt(const FVector2D& Point, bool bAdd)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	UVLCommand* Command = UVLCommand::Get(this);
	AVLKing* Of = PC ? Cast<AVLKing>(PickAt(PC, Point)) : nullptr;
	if (!Command || !Of || Of->IsDead() || Of->Team != Team)
	{
		return false;
	}
	int32 SizeX = 0, SizeY = 0;
	PC->GetViewportSize(SizeX, SizeY);
	TArray<AVLKing*> Same;
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		FVector2D Screen;
		if (It->IsAlive() && It->Team == Team && It->GetKind() == Of->GetKind() && It->IsTroop() == Of->IsTroop()
			&& PC->ProjectWorldLocationToScreen(It->GetActorLocation(), Screen) && Screen.X >= 0.f && Screen.Y >= 0.f && Screen.X <= SizeX && Screen.Y <= SizeY)
		{
			Same.Add(*It);
		}
	}
	Command->Select(Same, bAdd);
	Selected = Of;
	LastClicked = nullptr;
	UE_LOG(LogSovereignRealms, Log, TEXT("selected every %s in view: %d"), *Of->GetKind(), Same.Num());
	return true;
}

void AVLKing::SelectPlatoon(int32 Index, bool bLook)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return;
	}
	TArray<AVLKing*> Members;
	Command->GetPlatoon(Index, Members);
	if (Members.Num() == 0)
	{
		return;
	}
	Command->Select(Members);
	Selected = Members[0];
	if (bLook)
	{
		const FVector Centre = Command->PlatoonCentre(Index);
		OverviewFocus = FVector(Centre.X, Centre.Y, 0.f);
	}
}

void AVLKing::OverviewCommands(APlayerController* PC, AVLHUD* HUD, bool bRun)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return;
	}
	// building (VLConstruction.*): B the build menu, X repair, Delete a site / building; while a building is being
	// placed it has the mouse
	if (UVLConstruction* Construction = UVLConstruction::Get(this); Construction && Construction->OverviewInput(PC, HUD, this))
	{
		return;
	}
	float MX = 0.f, MY = 0.f;
	const bool bMouse = PC->GetMousePosition(MX, MY);
	const FVector2D Mouse(MX, MY);
	int32 SizeX = 0, SizeY = 0;
	PC->GetViewportSize(SizeX, SizeY);
	const bool bShift = PC->IsInputKeyDown(EKeys::LeftShift) || PC->IsInputKeyDown(EKeys::RightShift);
	const bool bCtrl = PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl) || PC->IsInputKeyDown(EKeys::LeftCommand)
		|| PC->IsInputKeyDown(EKeys::RightCommand);
	const bool bAlt = PC->IsInputKeyDown(EKeys::LeftAlt) || PC->IsInputKeyDown(EKeys::RightAlt);
	TArray<AVLKing*> Units;
	Command->GetSelection(Units);

	if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) && bMouse)
	{
		// the interface first (a press on a panel, the minimap, a button: AVLHUD answers it as it draws), then an
		// order (Ctrl / Cmd + click: for a trackpad), or the start of a click or of a box
		if (HUD && HUD->OnMousePress(Mouse, false))
		{
			// the interface took it: nothing in the world
		}
		else if (bCtrl && Units.Num() > 0)
		{
			if (OrderAt(Mouse, false, bShift))
			{
				AVLGameMode::PlayOrderSound(this);
			}
		}
		else
		{
			// a click off the build menu (on the world) puts it away; the click is then the usual one (the ground lets
			// the selection go)
			if (UVLConstruction* Construction = UVLConstruction::Get(this); Construction && Construction->IsMenuOpen())
			{
				Construction->SetMenu(false);
			}
			bLeftDown = true;
			bBoxing = false;
			PressPos = DragPos = Mouse;
		}
	}
	if (bLeftDown && bMouse)
	{
		DragPos = Mouse;
		bBoxing |= FVector2D::Distance(PressPos, DragPos) > 8.f;
	}
	if (bLeftDown && !PC->IsInputKeyDown(EKeys::LeftMouseButton))
	{
		bLeftDown = false;
		if (bBoxing)
		{
			bBoxing = false;
			BoxSelect(PressPos, DragPos, bShift);
		}
		else
		{
			if (bAlt && Command->GetArmed() == EVLArm::None && SelectKindAt(DragPos, bShift))
			{
				// Alt / Option + click: all of that kind in view (the main game's double click)
			}
			else if (ClickAt(DragPos, bShift))
			{
				AVLGameMode::PlayOrderSound(this);      // an order
			}
			if (PC->GetPawn() != this)
			{
				return;
			}
		}
		Command->GetSelection(Units);
	}
	UVLBattle* Battle = UVLBattle::Get(this);
	AActor* SelBuilding = (Selected.IsValid() && !Cast<AVLKing>(Selected.Get()) && Battle && Battle->FindBuilding(Selected.Get()) && Battle->TeamOf(Selected.Get()) == Team) ? Selected.Get() : nullptr;
	if (PC->WasInputKeyJustReleased(EKeys::RightMouseButton) && RightTravel < 6.f && bMouse && HUD && HUD->OnMousePress(Mouse, true))
	{
		// a right click on the interface (the minimap: the selection goes there, or a barracks' / range's rally point;
		// a platoon's formation button): AVLHUD answers it; nothing in the world
	}
	else if (PC->WasInputKeyJustReleased(EKeys::RightMouseButton) && RightTravel < 6.f && bMouse && Units.Num() == 0 && SelBuilding && !UVLBattle::TroopFor(SelBuilding).IsEmpty())
	{
		// a barracks / range selected and nobody: a right click on the ground is where its recruits muster; on the
		// building itself: no rally point (they wait in its yard again)
		FVector Ground = FVector::ZeroVector;
		AActor* On = PickAt(PC, Mouse, &Ground);
		if (On == SelBuilding)
		{
			Battle->SetRally(SelBuilding, FVector::ZeroVector, true);
			Battle->PushAlert(TEXT("No rally point: its recruits wait in its yard"));
			AVLGameMode::PlayOrderSound(this);
		}
		else if (!Ground.IsZero())
		{
			Battle->SetRally(SelBuilding, Ground);
			AVLGameMode::PlayOrderSound(this);
		}
	}
	else if (PC->WasInputKeyJustReleased(EKeys::RightMouseButton) && RightTravel < 6.f && bMouse)
	{
		// Shift + right click: a point on their pathway (as in the main game). A double right click: there at a run.
		const double Now = GetWorld()->GetRealTimeSeconds();
		const bool bDouble = Now - LastOrderClickTime < 0.35 && FVector2D::Distance(Mouse, LastOrderClickPos) < 30.f;
		LastOrderClickTime = Now;
		LastOrderClickPos = Mouse;
		if (OrderAt(Mouse, bDouble, bShift))
		{
			AVLGameMode::PlayOrderSound(this);      // the player's own orders only: not vl.Order / vl.RightClick
		}
	}

	// platoons: Ctrl / Cmd / Alt / Shift + 1..6 adds the selection to platoon N (forming it if it is empty), N selects it (twice: look at it)
	static const FKey Digits[UVLCommand::MaxPlatoons] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six };
	for (int32 i = 0; i < UVLCommand::MaxPlatoons; ++i)
	{
		if (!PC->WasInputKeyJustPressed(Digits[i]))
		{
			continue;
		}
		if ((bCtrl || bAlt) && Units.Num() == 0 && SelBuilding && !UVLBattle::TroopFor(SelBuilding).IsEmpty())
		{
			// a barracks / range selected: its recruits join platoon N (again: none)
			const FVLBuildingState* B = Battle->FindBuilding(SelBuilding);
			Battle->SetFeedPlatoon(SelBuilding, (B && B->FeedPlatoon == i) ? INDEX_NONE : i);
		}
		else if (bCtrl || bAlt || bShift)
		{
			// Ctrl / Cmd / Alt / Shift + N: the selection JOINS platoon N, which keeps its members (an empty one is
			// formed of them; a troop leaves the platoon it was in). It was: Ctrl re-formed the platoon of the selection only.
			Command->AddToPlatoon(i, Units);
		}
		else
		{
			const double Now = GetWorld()->GetRealTimeSeconds();
			TArray<AVLKing*> Members;
			Command->GetPlatoon(i, Members);
			if (Members.Num() > 0)
			{
				SelectPlatoon(i, LastPlatoonKey == i && Now - LastPlatoonTime < 0.4);
				LastPlatoonKey = i;
				LastPlatoonTime = Now;
			}
		}
	}
	if (PC->WasInputKeyJustPressed(EKeys::Delete))
	{
		const int32 P = Command->PlatoonOf(Units);
		if (P != INDEX_NONE)
		{
			Command->DisbandPlatoon(P);     // Delete: break up the selected platoon (the troops stay selected)
		}
	}
	if (PC->WasInputKeyJustPressed(EKeys::F))
	{
		Command->CycleFormation();
	}
	if (PC->WasInputKeyJustPressed(EKeys::G))
	{
		Command->CycleStance();         // Aggressive > Defensive > Hold ground
	}
	if (PC->WasInputKeyJustPressed(EKeys::U) && SelBuilding && Battle)
	{
		Battle->Upgrade(SelBuilding);   // raise the selected building a level
	}
	else if (PC->WasInputKeyJustPressed(EKeys::U) && !Selected.IsValid() && Units.Num() == 0 && Battle && Battle->GetCastle(Team))
	{
		Battle->Upgrade(Battle->GetCastle(Team));      // nothing selected: the castle (the main game's U)
	}
	// ---- the main game's orders (the command card has them too)
	auto UIClick = [Battle]() { if (Battle) { Battle->Play2D(TEXT("S_UIClick"), 0.4f); } };
	if (PC->WasInputKeyJustReleased(EKeys::A) && !bTapKeyPanned[0] && TapKeyDownAt[0] >= 0.0 && !bCtrl && !bAlt && Units.Num() > 0)
	{
		Command->CycleAttackArm();      // a tap: attack-move
		UIClick();
	}
	if (PC->WasInputKeyJustReleased(EKeys::S) && !bTapKeyPanned[1] && TapKeyDownAt[1] >= 0.0 && !bCtrl && !bAlt && Units.Num() > 0)
	{
		Command->OrderStop(Units);      // a tap: stop (a hold pans)
		AVLGameMode::PlayOrderSound(this);
	}
	// (H, hold ground, is gone: the stance's cycle, G, has Hold ground)
	if (PC->WasInputKeyJustPressed(EKeys::P) && (Units.Num() > 0 || AVLTroopShip::Selected(this)))
	{
		Command->Arm(EVLArm::Patrol);   // then a click (Shift: more points)
		UIClick();
	}
	if (PC->WasInputKeyJustPressed(EKeys::V) && Command->SelectionCanGuard())
	{
		Command->Arm(EVLArm::Guard);    // then a click on a building or a unit of one's own
		UIClick();
		if (Battle)
		{
			Battle->PushAlert(TEXT("Guard: click one of your buildings or units"));
		}
	}
	if (PC->WasInputKeyJustPressed(EKeys::O) && Units.Num() > 0)
	{
		if (Command->OrderRoam(Units) > 0)
		{
			AVLGameMode::PlayOrderSound(this);
		}
		else if (Battle)
		{
			Battle->PushAlert(TEXT("Only the Spy roams"));
		}
	}
	if (PC->WasInputKeyJustPressed(EKeys::M) && Units.Num() > 1)
	{
		Command->ToggleMarchTogether();
		UIClick();
	}
	if (PC->WasInputKeyJustPressed(EKeys::K) && Units.Num() > 0)
	{
		Command->DismissCommand();      // the first press asks, a second does it
		UIClick();
	}
	if (PC->WasInputKeyJustPressed(EKeys::SpaceBar) || PC->WasInputKeyJustPressed(EKeys::Home))
	{
		// centre the view on the selection (or the selected building)
		FVector C = FVector::ZeroVector;
		for (const AVLKing* U : Units)
		{
			C += U->GetActorLocation();
		}
		if (Units.Num() > 0)
		{
			C /= Units.Num();
			OverviewFocus = FVector(C.X, C.Y, 0.f);
		}
		else if (Selected.IsValid())
		{
			OverviewFocus = FVector(Selected->GetActorLocation().X, Selected->GetActorLocation().Y, 0.f);
		}
	}
	if (PC->WasInputKeyJustPressed(EKeys::RightMouseButton))
	{
		Command->Arm(EVLArm::None);     // a right click lets an armed click go
	}
	PC->CurrentMouseCursor = Command->GetArmed() != EVLArm::None ? EMouseCursor::Crosshairs : EMouseCursor::Default;     // (armed: the main game's crosshair)
	if (PC->WasInputKeyJustPressed(EKeys::Enter))
	{
		if (AVLKing* Chosen = Cast<AVLKing>(Selected.Get()); Chosen && Chosen->Team == Team && Chosen->IsAlive())
		{
			TakeControlOf(Chosen);          // any of the player's own: the king, a swordsman, an archer
		}
	}
}

namespace
{
	TAutoConsoleVariable<int32> CVarKeyTurn(TEXT("vl.Cam.KeyTurn"), 1, TEXT("1: Q turns the view clockwise (seen from above) and E anticlockwise, in both views. -1: the other way round (as before 2026-11-22)"));
	TAutoConsoleVariable<int32> CVarInputLog(TEXT("vl.InputLog"), 0, TEXT("1: log the clicks, wheel steps and trackpad gestures the player's unit sees, with the zoom and the attack's state"));
}

void AVLKing::PollInput(float DeltaSeconds)
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		// not the player's: it walks to its orders by itself (under its AI controller)
		bCommandMode = bCommandChain = bChainHeldByTest = false;
		FVector Wish;
		if (GetController() && AutoSteer(DeltaSeconds, Wish))
		{
			GetCharacterMovement()->MaxWalkSpeed = bAutoRun ? RunSpeed : WalkSpeed;
			if (PaceCap > 0.f)
			{
				GetCharacterMovement()->MaxWalkSpeed = FMath::Min(PaceCap, FMath::Max(RunSpeed, WalkSpeed));     // marching together (slower ahead of the body, hurrying behind it)
			}
			if (!YieldWish.IsNearlyZero())
			{
				// in the way of the unit the player plays: nudged off its line, it walks on
				FVector2D Off = YieldWish.GetSafeNormal();
				YieldWish = FVector2D::ZeroVector;
				if (YieldDirection(Off, false))
				{
					Wish = (Wish + FVector(Off, 0.f) * 0.9f).GetSafeNormal();
				}
			}
			AddMovementInput(Wish, 1.f);
		}
		else if (GetController() && TickYield(DeltaSeconds, Wish))
		{
			AddMovementInput(Wish, 1.f);    // stepping out of the played unit's way, or back to its spot (MakeWay)
		}
		if (WayIgnored.Num() > 0)
		{
			MakeWay(DeltaSeconds, false);   // (played no more)
		}
		return;
	}
	// the menus: Esc (or P) opens the pause menu (and backs out of a screen); while one is up the world's input is not read
	AVLHUD* HUD = Cast<AVLHUD>(PC->GetHUD());
	UpdateCursorMode(PC, HUD);
	if (HUD)
	{
		// (P: in the overview with units selected it is Patrol, OverviewCommands; the pause menu otherwise)
		const UVLCommand* Cmd = UVLCommand::Get(this);
		const bool bPatrolKey = !bHeroMode && !HUD->bMenu && Cmd && (Cmd->NumSelected() > 0 || AVLTroopShip::Selected(this));       // (a troop ship patrols too)
		if (PC->WasInputKeyJustPressed(EKeys::Escape) || (PC->WasInputKeyJustPressed(EKeys::P) && !bPatrolKey))
		{
			HUD->OnEscape();
		}
		if (PC->WasInputKeyJustPressed(EKeys::F1))
		{
			HUD->ToggleLegend();            // the controls overlay (in the menus: the Controls screen)
		}
		if (HUD->bMenu)
		{
			HUD->MenuInput(PC, this);
			if (HUD->IsTitle())
			{
				// behind the title screen the overview drifts slowly round the realm
				if (bHeroMode)
				{
					SetHeroMode(false);
					OverviewZoom = 0.32f;
				}
				OverviewYaw += 3.f * DeltaSeconds;
				UpdateOverviewCamera(DeltaSeconds);
			}
			return;
		}
	}
	if (bDead)
	{
		// the king fallen, waiting to rise again: the overview only
		if (bHeroMode)
		{
			SetHeroMode(false);
		}
	}

	// J: the other hero. From King David (or any unit, or the overview) the controls go to Jonathan, the archer prince,
	// once he is in the field (he comes to the castle at its third level: UVLBattle::TickJonathan); from Jonathan
	// they go back to King David. Enter / a double click on either in the overview does the same.
	if (PC->WasInputKeyJustPressed(EKeys::J))
	{
		AVLKing* Other = nullptr;
		if (IsJonathan())
		{
			for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
			{
				if (!It->IsTroop() && It->Team == Team)
				{
					Other = *It;
				}
			}
		}
		else if (const UVLBattle* Battle = UVLBattle::Get(this))
		{
			Other = Battle->GetJonathan(Team);
		}
		if (Other && Other != this && Other->IsAlive())
		{
			TakeControlOf(Other);
			return;
		}
	}
	if ((PC->WasInputKeyJustPressed(EKeys::Tab) || PC->WasInputKeyJustPressed(EKeys::Gamepad_FaceButton_Top)) && !bDead)
	{
		SetHeroMode(!bHeroMode);
	}
	if (PC->WasInputKeyJustPressed(EKeys::V))
	{
		// (in the overview with troops selected V is Guard, as in the main game: OverviewCommands)
		const UVLCommand* Cmd = UVLCommand::Get(this);
		if (bHeroMode || !Cmd || !Cmd->SelectionCanGuard())
		{
			CycleCameraAngle();     // Classic (steep) > Low > Battlefield (shallow), as in the main game
		}
	}
	if (PC->WasInputKeyJustPressed(EKeys::C))
	{
		SetView(ViewMode == 1 ? (bHeroMode ? 0 : 3) : 1);
	}

	float Fwd = (PC->IsInputKeyDown(EKeys::W) || PC->IsInputKeyDown(EKeys::Up) ? 1.f : 0.f) - (PC->IsInputKeyDown(EKeys::S) || PC->IsInputKeyDown(EKeys::Down) ? 1.f : 0.f);
	float Side = (PC->IsInputKeyDown(EKeys::D) || PC->IsInputKeyDown(EKeys::Right) ? 1.f : 0.f) - (PC->IsInputKeyDown(EKeys::A) || PC->IsInputKeyDown(EKeys::Left) ? 1.f : 0.f);
	Fwd += PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftY);
	Side += PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftX);
	if (TestMoveTime > 0.f)                     // vl.Move: as if the keys were held
	{
		TestMoveTime -= DeltaSeconds;
		Fwd += TestMove.X;
		Side += TestMove.Y;
	}
	const bool bTestRunNow = TestMoveTime > 0.f && bTestRun;
	// double-tap a direction to run (as in Minecraft): he keeps running until every direction key is let go
	{
		static const FKey MoveKeys[8] = { EKeys::W, EKeys::A, EKeys::S, EKeys::D, EKeys::Up, EKeys::Left, EKeys::Down, EKeys::Right };
		const double Now = GetWorld()->GetRealTimeSeconds();
		bool bAnyHeld = false;
		for (int32 i = 0; i < 8; ++i)
		{
			if (PC->WasInputKeyJustPressed(MoveKeys[i]))
			{
				if (LastTapKey == i && Now - LastTapTime < DoubleTapSeconds)
				{
					bTapRun = true;
				}
				LastTapKey = i;
				LastTapTime = Now;
			}
			bAnyHeld |= PC->IsInputKeyDown(MoveKeys[i]);
		}
		if (!bAnyHeld)
		{
			bTapRun = false;
		}
	}
	bool bRun = bTapRun || bTestRunNow || PC->IsInputKeyDown(EKeys::LeftShift) || PC->IsInputKeyDown(EKeys::RightShift) || PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) > 0.4f;
	const FVector2D Stick(Fwd, Side);
	const bool bStick = Stick.SizeSquared() > 0.04f;

	// turning and zooming the view, whichever camera is in use
	float MouseX = 0.f, MouseY = 0.f;
	PC->GetInputMouseDelta(MouseX, MouseY);
	const float StickX = PC->GetInputAnalogKeyState(EKeys::Gamepad_RightX);
	const float StickY = PC->GetInputAnalogKeyState(EKeys::Gamepad_RightY);
	// Q / E: the owner's call of 2026-11-22 turned them round (Q now turns the view clockwise seen from above, E
	// anticlockwise: each the opposite of what it did), in both views; vl.Cam.KeyTurn -1 is the old way. The stick,
	// the mouse and the trackpad are as they were.
	const float KeyTurn = CVarKeyTurn.GetValueOnGameThread() < 0 ? -1.f : 1.f;
	float Turn = (KeyTurn * ((PC->IsInputKeyDown(EKeys::Q) ? 1.f : 0.f) - (PC->IsInputKeyDown(EKeys::E) ? 1.f : 0.f)) + StickX) * 80.f * DeltaSeconds;
	if (PC->WasInputKeyJustPressed(EKeys::RightMouseButton))
	{
		float MX = 0.f, MY = 0.f;
		PC->GetMousePosition(MX, MY);
		RightDownAt = FVector2D(MX, MY);
		RightTravel = 0.f;
	}
	if (bMouseLookActive)
	{
		// the hero view: the mouse looks round (up is up); the pointer is hidden, a crosshair shows where he aims
		// the setting (100% = MouseLookSpeed), and calmer the further out the view is
		const float Speed = MouseLookSpeed * LookSpeedSetting * FMath::Lerp(1.f, LookSpeedFar, FMath::Clamp(Zoom, 0.f, 1.f));
		// (the user found the first way round inverted on a trackpad: this is the default now; the Esc menu's
		// "Invert look" setting turns either axis back)
		const float SX = (LookInvert & 1) ? -1.f : 1.f;
		const float SY = (LookInvert & 2) ? -1.f : 1.f;
		Turn += SX * MouseX * Speed;
		LookPitch = FMath::Clamp(LookPitch + SY * MouseY * Speed * 0.8f, -40.f, 32.f);
	}
	else if (PC->IsInputKeyDown(EKeys::RightMouseButton) && !(bHeroMode && bRightMouseAims))      // (an archer's right button draws her bow)
	{
		Turn += MouseX * 0.9f;
		RightTravel += FMath::Abs(MouseX) + FMath::Abs(MouseY);
	}
	float Step = 0.f;
	if (PC->WasInputKeyJustPressed(EKeys::MouseScrollUp))
	{
		Step -= ZoomStep;
	}
	if (PC->WasInputKeyJustPressed(EKeys::MouseScrollDown))
	{
		Step += ZoomStep;
	}
	Step += -StickY * 0.43f * DeltaSeconds;
	const bool bReset = PC->WasInputKeyJustPressed(bHeroMode ? EKeys::Home : EKeys::R);     // (the hero view's R commands: HeroCommands)

	// the trackpad: pinch zooms and the two-finger twist turns the view in both modes; a two-finger scroll pans the
	// overview (the ground follows the fingers) and, in hero mode, turns the view (sideways) and zooms (up and down)
	FVector2D Pad = FVector2D::ZeroVector;
	float Pinch = 0.f, Twist = 0.f;
	if (AVLPlayerController* VPC = Cast<AVLPlayerController>(PC))
	{
		VPC->TakeGestures(Pad, Pinch, Twist);
	}
	Step -= Pinch * 0.41f;        // (0.64 before the zoom range grew 1.55 times)
	Turn += Twist * 1.0f;
	if (bHeroMode)
	{
		Turn -= Pad.X * 0.12f;
		Step += Pad.Y * 0.0018f;
	}
	if (Step != 0.f && ViewMode != (bHeroMode ? 0 : 3) && PC->GetPawn() == this)
	{
		// zooming while the postcard (C) or a test camera is up: back to this mode's own camera, which is the one
		// that zooms (otherwise the wheel seems dead)
		SetView(bHeroMode ? 0 : 3, 0.4f);
	}

	if (CVarInputLog.GetValueOnGameThread() != 0 && (Step != 0.f || Pinch != 0.f || !Pad.IsZero() || PC->WasInputKeyJustPressed(EKeys::LeftMouseButton)))
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("input seen: %s step %.3f pinch %.3f pad %.1f %.1f click %d | zoom %.2f overview %.2f arm %.0f armed %d attack %.2f"), bHeroMode ? TEXT("hero") : TEXT("overview"),
			Step, Pinch, Pad.X, Pad.Y, PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) ? 1 : 0, Zoom, OverviewZoom, Boom ? Boom->TargetArmLength : 0.f, bArmed ? 1 : 0, AttackTime);
	}
	if (!bHeroMode)
	{
		// ---- overview: the camera roams, the mouse selects
		OverviewYaw += Turn;
		OverviewZoom = FMath::Clamp(OverviewZoom + Step * OverviewZoomStepScale, 0.f, 1.f);
		if (bReset)
		{
			OverviewYaw = HomeYaw;
		}
		const FRotator Yaw(0.f, OverviewYaw, 0.f);
		const FVector Ahead = FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), Right = FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y);
		// A and S are attack-move and Stop too (OverviewCommands): with units selected a quick tap is the order and a
		// hold pans once it has lasted CommandKeyTapSeconds; with nobody selected, or while another pan key is down,
		// they pan at once (the main game's rule)
		FVector2D PanStick = Stick;
		{
			const UVLCommand* Cmd = UVLCommand::Get(this);
			const bool bOrders = Cmd && Cmd->NumSelected() > 0;
			const double Now = GetWorld()->GetRealTimeSeconds();
			static const FKey TapKeys[2] = { EKeys::A, EKeys::S };
			const FVector2D Own[2] = { FVector2D(0.f, -1.f), FVector2D(-1.f, 0.f) };     // each one's part of the stick
			const bool bOtherKeys = PC->IsInputKeyDown(EKeys::W) || PC->IsInputKeyDown(EKeys::D) || PC->IsInputKeyDown(EKeys::Up) || PC->IsInputKeyDown(EKeys::Down)
				|| PC->IsInputKeyDown(EKeys::Left) || PC->IsInputKeyDown(EKeys::Right);
			for (int32 k = 0; k < 2; ++k)
			{
				if (PC->WasInputKeyJustPressed(TapKeys[k]))
				{
					TapKeyDownAt[k] = Now;
					bTapKeyPanned[k] = false;
				}
				if (!PC->IsInputKeyDown(TapKeys[k]))
				{
					continue;
				}
				if (!bOrders || bOtherKeys || bTapKeyPanned[1 - k] || bTapKeyPanned[k] || Now - TapKeyDownAt[k] >= CommandKeyTapSeconds)
				{
					bTapKeyPanned[k] = true;
				}
				else
				{
					PanStick -= Own[k];     // not yet: it may be a tap
				}
			}
		}
		if (PanStick.SizeSquared() > 0.04f)
		{
			const FVector Dir = (Ahead * PanStick.X + Right * PanStick.Y).GetClampedToMaxSize(1.f);
			const float Speed = FMath::Lerp(1400.f, 11900.f, OverviewZoom) * (bRun ? 1.8f : 1.f);
			OverviewFocus += Dir * Speed * DeltaSeconds;
		}
		if (!Pad.IsZero())
		{
			// the ground moves with the fingers: further out, a point of scroll covers more ground
			const float PerPoint = FMath::Lerp(1.f, 8.7f, OverviewZoom);
			OverviewFocus += (Ahead * Pad.Y - Right * Pad.X) * PerPoint;
		}
		FBox2D Roam(FVector2D(-9000.f, -9000.f), FVector2D(9000.f, 9000.f));
		if (const UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->IsBuilt())
		{
			Roam += Grid->GetBounds();      // (a map bigger than the town: as far as its ground goes)
		}
		OverviewFocus.X = FMath::Clamp(OverviewFocus.X, Roam.Min.X, Roam.Max.X);
		OverviewFocus.Y = FMath::Clamp(OverviewFocus.Y, Roam.Min.Y, Roam.Max.Y);
		if (ViewMode == 3)
		{
			UpdateOverviewCamera(DeltaSeconds);
		}
		OverviewCommands(PC, HUD, bRun);
		if (PC->GetPawn() != this)
		{
			return;                 // took control of another unit
		}
	}
	else
	{
		// ---- hero: the camera holds the diorama angle and follows him
		CamYaw += Turn;
		if (bReset)
		{
			LookPitch = 0.f;
			CamYaw = HomeYaw;
			ManualPitch = ManualArm = 0.f;
		}
		if (Step != 0.f)
		{
			Zoom = FMath::Clamp(Zoom + Step, 0.f, 1.f);
			ManualPitch = ManualArm = 0.f;
		}
		if (PC->WasInputKeyJustPressed(EKeys::SpaceBar) || PC->WasInputKeyJustPressed(EKeys::Gamepad_FaceButton_Bottom))
		{
			Jump();
		}
		if (PC->WasInputKeyJustReleased(EKeys::SpaceBar) || PC->WasInputKeyJustReleased(EKeys::Gamepad_FaceButton_Bottom))
		{
			StopJumping();
		}
		if (!bTroop && (PC->WasInputKeyJustPressed(EKeys::F) || PC->WasInputKeyJustPressed(EKeys::Gamepad_FaceButton_Left)))
		{
			bArmed = !bArmed;
			bAttackQueued = false;
		}
		// commanding from here: R turns command mode on (at the crosshair a left click selects, a right click orders,
		// Shift queues); out of it the right click (Ctrl / Cmd + click) orders the selection; 1..6 the platoons, G follow
		// me (a command's click is not a swing)
		// (the pointer shown in the hero view, C's postcard or mouse look off: the minimap and the platoon panel take
		// their clicks first, as in the overview)
		bool bHudClick = false;
		if (HUD && !bMouseLookActive)
		{
			float HX = 0.f, HY = 0.f;
			if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) && PC->GetMousePosition(HX, HY))
			{
				bHudClick = HUD->OnMousePress(FVector2D(HX, HY), false);
			}
			else if (PC->WasInputKeyJustReleased(EKeys::RightMouseButton) && RightTravel < 6.f && PC->GetMousePosition(HX, HY))
			{
				HUD->OnMousePress(FVector2D(HX, HY), true);
			}
		}
		const bool bCommandClick = HeroCommands(PC, bHudClick);
		if (PC->GetPawn() != this)
		{
			return;                 // took control of another unit
		}
		if (!bCommandClick && (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) || PC->WasInputKeyJustPressed(EKeys::Gamepad_RightShoulder)))
		{
			// a swing turns him towards the pointer for FaceMouseHoldSeconds, then he faces his way of walking again
			float Yaw = 0.f;
			if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) && PointerYaw(PC, Yaw))
			{
				FaceYaw = Yaw;
				FaceMouseLeft = FaceMouseHoldSeconds;
			}
			Attack();
		}
	}
	// the hero camera keeps its angle up to date even while the overview is shown, so switching back is seamless
	{
		const float Curve = Zoom * Zoom;                    // fine steps close in, long ones far out
		TargetArm = ManualArm > 0.f ? ManualArm : FMath::Lerp(ArmNear, ArmFar, Curve);
		const float Pitch = FMath::Clamp((ManualPitch != 0.f ? ManualPitch : HeroPitch(Zoom)) + LookPitch, -80.f, 8.f);
		const FRotator Now = PC->GetControlRotation();
		PC->SetControlRotation(FRotator(FMath::FInterpTo(Now.Pitch > 180.f ? Now.Pitch - 360.f : Now.Pitch, Pitch, DeltaSeconds, 6.f), CamYaw, 0.f));
		if (Boom)
		{
			Boom->TargetArmLength = FMath::FInterpTo(Boom->TargetArmLength, TargetArm, DeltaSeconds, 6.f);
		}
	}

	// ---- moving him: the keys in hero mode, or an order
	FVector Wish = FVector::ZeroVector;
	if (bAutoWalk && bHeroMode && bStick)
	{
		StopOrder();                // the player takes the controls
	}
	if (AutoSteer(DeltaSeconds, Wish))
	{
		bRun = bAutoRun;
	}
	else if (bHeroMode && bStick)
	{
		const FRotator Yaw(0.f, CamYaw, 0.f);
		Wish = (FRotationMatrix(Yaw).GetUnitAxis(EAxis::X) * Stick.X + FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y) * Stick.Y).GetClampedToMaxSize(1.f);
	}
	GetCharacterMovement()->MaxWalkSpeed = bRun ? RunSpeed : WalkSpeed;
	if (PaceCap > 0.f && bAutoWalk && !bHeroMode)
	{
		GetCharacterMovement()->MaxWalkSpeed = FMath::Min(PaceCap, FMath::Max(RunSpeed, WalkSpeed));     // on an order with his troops: the march's speed for him
	}
	if (MoveSpeedCap > 0.f && bHeroMode)
	{
		GetCharacterMovement()->MaxWalkSpeed = FMath::Min(GetCharacterMovement()->MaxWalkSpeed, MoveSpeedCap);     // an archer drawing her bow
	}
	if (!Wish.IsNearlyZero())
	{
		AddMovementInput(Wish, 1.f);
	}
	// his own way: the player's units he walks into step aside (foes do not)
	MakeWay(DeltaSeconds, bHeroMode && !bDead);
	// after a swing he faces where it was aimed (the pointer when clicked) for FaceMouseHoldSeconds, WASD strafing; then
	// he turns back to his way of walking (the movement component's own turn). Archers aim with their own component.
	if (!bTroop || !FindComponentByClass<UVLArcherCombat>())
	{
		FaceMouseLeft = FMath::Max(0.f, FaceMouseLeft - DeltaSeconds);
		const bool bFace = bFaceMouseWhenArmed && bHeroMode && FaceMouseLeft > 0.f && !bAutoWalk;
		GetCharacterMovement()->bOrientRotationToMovement = !bFace;
		if (bFace)
		{
			const FRotator Now = GetActorRotation();
			SetActorRotation(FRotator(0.f, FMath::FixedTurn(Now.Yaw, FaceYaw, FaceMouseTurnRate * DeltaSeconds), 0.f));
		}
	}
}

float AVLKing::HeroPitch(float InZoom) const
{
	// the camera-angle setting, as in the main game: Classic (the tuned pitches), Low, Battlefield (shallow, more of
	// the land ahead). Near and far ends of the zoom each get their own pitch.
	static const float Hero[3][2] = { { 0.f, 0.f }, { -11.f, -36.f }, { -6.f, -23.f } };
	const int32 A = FMath::Clamp(CameraAngle, 0, 2);
	const float Near = A == 0 ? PitchNear : Hero[A][0];
	const float Far = A == 0 ? PitchFar : Hero[A][1];
	return FMath::Lerp(Near, Far, FMath::Clamp(InZoom, 0.f, 1.f));
}

float AVLKing::OverviewDistance(float InZoom, FVector& InOutFocus) const
{
	const float Z = FMath::Clamp(InZoom, 0.f, 1.f);
	float Dist = FMath::Lerp(OverviewNear, OverviewFar, Z * Z);
	FVector2D Centre;
	const float Whole = WholeMapDistance(Centre);
	if (Whole > OverviewFar)
	{
		// the usual zoom untouched up to three quarters; from there out to the whole map, the focus to its middle
		const float E = FMath::SmoothStep(0.75f, 1.f, Z);
		Dist += (Whole - OverviewFar) * E;
		InOutFocus.X = FMath::Lerp(float(InOutFocus.X), float(Centre.X), E);
		InOutFocus.Y = FMath::Lerp(float(InOutFocus.Y), float(Centre.Y), E);
	}
	return Dist;
}

float AVLKing::WholeMapDistance(FVector2D& OutCentre) const
{
	const UVLGrid* Grid = UVLGrid::Get(this);
	if (!Grid || !Grid->IsBuilt())
	{
		return 0.f;
	}
	const FBox2D Ground = Grid->GetBounds();
	float Aspect = 16.f / 9.f;
	if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
	{
		const FIntPoint Size = GEngine->GameViewport->Viewport->GetSizeXY();
		if (Size.X > 0 && Size.Y > 0)
		{
			Aspect = float(Size.X) / float(Size.Y);
		}
	}
	const float Pitch = OverviewPitch(1.f);
	const TArray<float> Key = { float(Ground.Min.X), float(Ground.Min.Y), float(Ground.Max.X), float(Ground.Max.Y), Aspect, OverviewFOV, Pitch };
	if (Key == WholeMapKey)
	{
		OutCentre = WholeMapCentre;
		return WholeMapDist;
	}
	// The map's ground, a square of its larger side round its middle (with a 5% margin), must be inside the view's
	// frustum: every corner in front of the eye and within the half angles, for eight yaws (the furthest of them, so the
	// distance does not change as the view turns). Found by halving between the near limit and far past it.
	const FVector2D C = Ground.GetCenter();
	const float Half = 0.5f * FMath::Max(Ground.GetSize().X, Ground.GetSize().Y) * 1.05f;
	const float TanH = FMath::Tan(FMath::DegreesToRadians(FMath::Clamp(OverviewFOV, 5.f, 170.f) * 0.5f));
	const float TanV = TanH / FMath::Max(Aspect, 0.1f);
	auto Fits = [&](float D, float Yaw)
	{
		const FRotationMatrix M(FRotator(Pitch, Yaw, 0.f));
		const FVector F = M.GetUnitAxis(EAxis::X), R = M.GetUnitAxis(EAxis::Y), U = M.GetUnitAxis(EAxis::Z);
		const FVector Eye = -F * D;     // (the focus at the origin, on the ground)
		for (int32 k = 0; k < 4; ++k)
		{
			const FVector P((k & 1) ? Half : -Half, (k & 2) ? Half : -Half, 0.f);
			const FVector V = P - Eye;
			const float X = float(FVector::DotProduct(V, F));
			if (X <= 1.f || FMath::Abs(float(FVector::DotProduct(V, R))) > X * TanH || FMath::Abs(float(FVector::DotProduct(V, U))) > X * TanV)
			{
				return false;
			}
		}
		return true;
	};
	float Need = 0.f;
	for (int32 y = 0; y <= 8; ++y)
	{
		const float Yaw = y * 11.25f;   // (0 .. 90: a square repeats itself every quarter turn)
		float Lo = OverviewNear, Hi = FMath::Max(OverviewFar, Half * 40.f);
		if (!Fits(Hi, Yaw))
		{
			continue;                   // (never fits: a pitch too shallow for this view; left to the usual far limit)
		}
		for (int32 i = 0; i < 40; ++i)
		{
			const float Mid = 0.5f * (Lo + Hi);
			(Fits(Mid, Yaw) ? Hi : Lo) = Mid;
		}
		Need = FMath::Max(Need, Hi);
	}
	WholeMapKey = Key;
	WholeMapDist = Need;
	WholeMapCentre = C;
	OutCentre = C;
	UE_LOG(LogSovereignRealms, Log, TEXT("overview: the whole map (%.0f x %.0f m) is in view at %.0f m (usual far %.0f m; aspect %.2f, FOV %.0f, pitch %.0f)"),
		Ground.GetSize().X / 100.f, Ground.GetSize().Y / 100.f, Need / 100.f, OverviewFar / 100.f, Aspect, OverviewFOV, Pitch);
	return Need;
}

float AVLKing::OverviewPitch(float InZoom) const
{
	static const float Over[3][2] = { { 0.f, 0.f }, { -16.f, -43.f }, { -11.f, -30.5f } };
	const int32 A = FMath::Clamp(CameraAngle, 0, 2);
	const float Near = A == 0 ? OverviewPitchNear : Over[A][0];
	const float Far = A == 0 ? OverviewPitchFar : Over[A][1];
	return FMath::Lerp(Near, Far, FMath::Clamp(InZoom, 0.f, 1.f));
}

const TCHAR* AVLKing::CameraAngleName(int32 Angle)
{
	static const TCHAR* Names[3] = { TEXT("Classic (steep)"), TEXT("Low"), TEXT("Battlefield (shallow)") };
	return Names[FMath::Clamp(Angle, 0, 2)];
}

const TCHAR* AVLKing::LookInvertName(int32 Invert)
{
	static const TCHAR* Names[4] = { TEXT("Off"), TEXT("Left / right"), TEXT("Up / down"), TEXT("Both") };
	return Names[FMath::Clamp(Invert, 0, 3)];
}

void AVLKing::CycleLookInvert()
{
	LookInvert = (FMath::Clamp(LookInvert, 0, 3) + 1) % 4;
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		It->LookInvert = LookInvert;
	}
	if (GConfig)
	{
		GConfig->SetInt(TEXT("SovereignRealms.Camera"), TEXT("LookInvertV2"), LookInvert, GGameUserSettingsIni);
		GConfig->Flush(false, GGameUserSettingsIni);
	}
}

void AVLKing::CycleLookSpeed()
{
	// 25% .. 150% in quarters; 75% is the original speed
	float Next = FMath::RoundToFloat(LookSpeedSetting * 4.f) / 4.f + 0.25f;
	if (Next > 1.5f + KINDA_SMALL_NUMBER)
	{
		Next = 0.25f;
	}
	SetLookSpeed(Next, true);
}

void AVLKing::SetLookSpeed(float Speed, bool bSave)
{
	LookSpeedSetting = FMath::Clamp(Speed, 0.1f, 2.f);
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		It->LookSpeedSetting = LookSpeedSetting;
	}
	if (bSave)
	{
		if (GConfig)
		{
			GConfig->SetFloat(TEXT("SovereignRealms.Camera"), TEXT("LookSpeed"), LookSpeedSetting, GGameUserSettingsIni);
			GConfig->Flush(false, GGameUserSettingsIni);
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("look speed: %.0f%%"), LookSpeedSetting * 100.f);
	}
}

void AVLKing::CycleCameraAngle()
{
	CameraAngle = (FMath::Clamp(CameraAngle, 0, 2) + 1) % 3;
	// every unit the player may take over looks the same way, and the choice is kept for the next session
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		It->CameraAngle = CameraAngle;
	}
	if (GConfig)
	{
		GConfig->SetInt(TEXT("SovereignRealms.Camera"), TEXT("CameraAngle"), CameraAngle, GGameUserSettingsIni);
		GConfig->Flush(false, GGameUserSettingsIni);
	}
	UpdateOverviewCamera(0.f, false);
	UE_LOG(LogSovereignRealms, Log, TEXT("camera angle: %s"), CameraAngleName(CameraAngle));
}

bool AVLKing::GetAimRay(APlayerController* PC, FVector& Origin, FVector& Dir) const
{
	if (!PC)
	{
		return false;
	}
	if (bMouseLookActive)
	{
		// through the crosshair (a little above the middle of the view, ahead of him)
		int32 SX = 0, SY = 0;
		PC->GetViewportSize(SX, SY);
		return SX > 0 && PC->DeprojectScreenPositionToWorld(SX * 0.5f, SY * CrosshairHeight, Origin, Dir);
	}
	return PC->DeprojectMousePositionToWorld(Origin, Dir);
}

void AVLKing::UpdateCursorMode(APlayerController* PC, const AVLHUD* HUD)
{
	const bool bWant = bMouseLook && bHeroMode && ViewMode == 0 && !(HUD && HUD->bMenu) && PC->GetPawn() == this;
	// At launch the window can come up without the keyboard and mouse focus (the input mode is applied before the
	// window is in front): until the game viewport really has the mouse, focus it and capture again, twice a second.
	if (bWant && bCursorModeSet)
	{
		UGameViewportClient* GVC = GetWorld()->GetGameViewport();
		const bool bCaptured = GVC && GVC->Viewport && GVC->Viewport->HasMouseCapture();
		CaptureRetry -= GetWorld()->GetDeltaSeconds();
		if (!bCaptured && CaptureRetry <= 0.f && FSlateApplication::IsInitialized())
		{
			CaptureRetry = 0.5f;
			TSharedPtr<SWindow> Window = GVC ? GVC->GetWindow() : nullptr;
			if (Window.IsValid() && Window->IsActive())
			{
				FSlateApplication::Get().SetAllUserFocusToGameViewport();
				FInputModeGameOnly Mode;
				Mode.SetConsumeCaptureMouseDown(false);
				PC->SetInputMode(Mode);
			}
		}
	}
	// (Windows: the pointer stays inside the game while it is full screen, so the lock follows the window mode)
	const EMouseLockMode Lock = UVLGraphics::PointerLock();
	if (bWant == bMouseLookActive && bCursorModeSet && (bWant || Lock == CursorLock))
	{
		return;
	}
	bCursorModeSet = true;
	bMouseLookActive = bWant;
	if (bWant)
	{
		FInputModeGameOnly Mode;
		Mode.SetConsumeCaptureMouseDown(false);
		PC->SetInputMode(Mode);
		PC->bShowMouseCursor = false;
	}
	else
	{
		// the overview, the postcard and the menu: the pointer is back and free to leave the window (a full-screen
		// game on Windows keeps it: UVLGraphics::PointerLock)
		CursorLock = Lock;
		FInputModeGameAndUI Mode;
		Mode.SetLockMouseToViewportBehavior(Lock);
		Mode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(Mode);
		PC->bShowMouseCursor = true;
	}
}

bool AVLKing::GetAimPoint(APlayerController* PC, FVector& OutPoint, float SkyDistance, bool* bOutSky) const
{
	FVector Origin, Dir;
	if (!GetWorld() || !GetAimRay(PC, Origin, Dir))
	{
		return false;
	}
	return GetAimPointAlong(Origin, Dir, OutPoint, SkyDistance, bOutSky);
}

bool AVLKing::GetAimPointAlong(const FVector& Origin, const FVector& Dir, FVector& OutPoint, float SkyDistance, bool* bOutSky, AActor** OutActor) const
{
	UWorld* World = GetWorld();
	if (bOutSky)
	{
		*bOutSky = false;
	}
	if (OutActor)
	{
		*OutActor = nullptr;
	}
	if (!World)
	{
		return false;
	}
	const FVector Me = GetActorLocation();
	const bool bLook = bMouseLookActive;
	// The crosshair's ray starts at the camera, behind him: whatever it meets before it has passed him (a tree, a roof
	// or a fence close to the lens) is drawn under the crosshair but is not what he aims at. Follow it only from
	// the point level with him onwards (and clear of his own body).
	const float Level = bLook ? FMath::Max(0.f, float(FVector::DotProduct(Me - Origin, Dir))) + GetCapsuleComponent()->GetScaledCapsuleRadius() + 40.f : 0.f;
	const float Far = Level + 60000.f;
	// (complex, as an arrow's trace is: what the aim meets is what the arrow meets)
	FCollisionQueryParams Params(TEXT("AimPoint"), true, this);
	bool bFound = false;
	FVector Point = FVector::ZeroVector;
	float Reach = Far;
	for (int32 Try = 0; Try < 12; ++Try)
	{
		FHitResult Hit;
		if (!World->LineTraceSingleByChannel(Hit, Origin + Dir * Level, Origin + Dir * Far, ECC_Visibility, Params))
		{
			break;
		}
		const AActor* Struck = Hit.GetActor();
		if (Struck && (Struck->IsA<APawn>() || Struck->ActorHasTag(TEXT("Canopy"))))
		{
			Params.AddIgnoredActor(Struck);     // units (a foe is found below), and the leaves the camera cuts away: the aim passes through
			continue;
		}
		if (Hit.bStartPenetrating && Hit.GetComponent())
		{
			Params.AddIgnoredComponent(Hit.GetComponent());     // the ray starts inside it (he stands against it): not ahead
			continue;
		}
		Point = Hit.ImpactPoint;
		Reach = float(FVector::DotProduct(Point - Origin, Dir));
		bFound = true;
		if (OutActor)
		{
			*OutActor = Hit.GetActor();
		}
		break;
	}
	// A foe's body the ray passes through before that catches it (units do not stop a visibility trace; an arrow
	// strikes a foe's body, UVLArrows::UnitOnPath): the point on the ray in the middle of the body.
	if (const UVLBattle* Battle = UVLBattle::Get(this))
	{
		const FVector From = Origin + Dir * Level;
		for (TActorIterator<AVLKing> It(World); It; ++It)
		{
			const AVLKing* U = *It;
			if (U == this || !Battle->IsHostile(U, Team))
			{
				continue;
			}
			const UCapsuleComponent* Cap = U->GetCapsuleComponent();
			const float Half = Cap->GetScaledCapsuleHalfHeight(), Rad = Cap->GetScaledCapsuleRadius();
			const FVector C = U->GetActorLocation();
			FVector OnRay, OnBody;
			FMath::SegmentDistToSegmentSafe(From, Origin + Dir * Reach, C - FVector(0.f, 0.f, Half * 0.9f), C + FVector(0.f, 0.f, Half * 0.9f), OnRay, OnBody);
			const float Along = float(FVector::DotProduct(OnRay - Origin, Dir));
			if (FVector::DistSquared(OnRay, OnBody) <= FMath::Square(Rad) && Along < Reach)
			{
				Reach = Along;
				Point = OnRay;
				bFound = true;
				if (OutActor)
				{
					*OutActor = const_cast<AVLKing*>(U);
				}
			}
		}
	}
	if (!bFound)
	{
		if (bLook)
		{
			Point = Origin + Dir * (Level + FMath::Max(SkyDistance, 300.f));        // nothing ahead: along the crosshair
			bFound = true;
			if (bOutSky)
			{
				*bOutSky = true;
			}
		}
		else if (Dir.Z < -0.01f)
		{
			Point = Origin + Dir * ((GetFeet().Z - Origin.Z) / Dir.Z);        // the pointer on the ground at his feet
			bFound = true;
		}
	}
	if (bFound && bLook)
	{
		// never behind him as the camera looks: at least a little ahead, flat, along the crosshair's way
		const FVector Ahead = FVector(Dir.X, Dir.Y, 0.f).GetSafeNormal(UE_SMALL_NUMBER, FRotator(0.f, CamYaw, 0.f).Vector());
		const FVector To(Point.X - Me.X, Point.Y - Me.Y, 0.f);
		const float Along = FVector::DotProduct(To, Ahead);
		if (Along < 60.f)
		{
			Point += Ahead * (60.f - Along);
		}
	}
	OutPoint = Point;
	return bFound;
}

bool AVLKing::PointerYaw(APlayerController* PC, float& OutYaw) const
{
	FVector To;
	if (bMouseLookActive)
	{
		// the crosshair: the way to what it points at ahead of him (never back towards the camera)
		FVector Point;
		if (!GetAimPoint(PC, Point))
		{
			return false;
		}
		To = Point - GetActorLocation();
	}
	else
	{
		FVector Origin, Dir;
		if (!GetAimRay(PC, Origin, Dir) || Dir.Z > -0.05f)
		{
			return false;           // the pointer is on the sky: its ray never comes down to the ground
		}
		// where the pointer's ray meets the ground at his feet
		const float FeetZ = GetActorLocation().Z - GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
		To = Origin + Dir * ((FeetZ - Origin.Z) / Dir.Z) - GetActorLocation();
	}
	if (To.SizeSquared2D() < 30.f * 30.f)
	{
		return false;
	}
	OutYaw = To.Rotation().Yaw;
	return true;
}

void AVLKing::ReceiveDamage(float Amount, AActor* From)
{
	if (Amount <= 0.f || bDead)
	{
		return;
	}
	SetMovementAwake(true);         // (hurt: awake for whatever follows)
	Health = FMath::Max(0.f, Health - Amount);
	LastHurtTime = GetWorld()->GetTimeSeconds();
	HitPauseLeft = FMath::Max(0.f, HitPauseSeconds);
	FlashLeft = FMath::Max(0.f, HitFlashSeconds);
	if (FlashMID && !bFlashOn && FlashLeft > 0.f)
	{
		for (UStaticMeshComponent* PartMesh : Meshes)
		{
			PartMesh->SetOverlayMaterial(FlashMID);
		}
		bFlashOn = true;
	}
	if (!bTroop)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("King hurt: %.0f from %s, health %.0f"), Amount, From ? *From->GetName() : TEXT("nobody"), Health);
	}
	if (Health <= 0.f)
	{
		if (UVLBattle* Battle = UVLBattle::Get(this))
		{
			Battle->OnUnitKilled(this, From);
		}
		else
		{
			Die();
		}
	}
}

void AVLKing::Die()
{
	if (bDead)
	{
		return;
	}
	bDead = true;
	SetMovementAwake(true);         // (asleep on a lookout: awake to fall as any other does)
	DeadTime = 0.f;
	Health = 0.f;
	StopOrder();
	ClearQueue();
	if (UVLSwordsmanCombat* S = UVLSwordsmanCombat::For(this, false))
	{
		S->Stop();
	}
	if (UVLArcherCombat* A = UVLArcherCombat::For(this, false))
	{
		A->Stop();
		A->LetDown();
	}
	GarrisonIn = nullptr;
	PendingGarrison = nullptr;
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GetCharacterMovement()->StopMovementImmediately();
	GetCharacterMovement()->DisableMovement();
	// the player was playing it: a troop hands the controls back to the king; the king himself goes to the overview
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		AVLKing* King = nullptr;
		for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
		{
			if (!It->IsTroop() && It->Team == Team)
			{
				King = *It;
			}
		}
		if (bTroop && King && King != this)
		{
			TakeControlOf(King);
			if (King->IsDead())
			{
				King->SetHeroMode(false);
			}
		}
		else
		{
			SetHeroMode(false);
		}
	}
}

void AVLKing::Revive(const FVector& Feet)
{
	bDead = false;
	DeadTime = 0.f;
	Health = MaxHealth;
	SetActorHiddenInGame(false);
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	SetActorLocation(Feet + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 5.f), false, nullptr, ETeleportType::TeleportPhysics);
	RigSetFigure(FigureLocal.GetLocation(), FQuat::Identity);
	bRigForce = true;
	GetCharacterMovement()->SetMovementMode(MOVE_Walking);
	Post = Feet;
	LastStruckBy = nullptr;
	UE_LOG(LogSovereignRealms, Log, TEXT("%s rises again at %s"), *DisplayName, *Feet.ToCompactString());
}

void AVLKing::TickDeath(float DeltaSeconds)
{
	DeadTime += DeltaSeconds;
	// he topples over sideways (stiffly: a wooden toy), lies a moment, and is gone
	const float Fall = FMath::Clamp(DeadTime / 0.55f, 0.f, 1.f);
	const float Ease = Fall * Fall * (3.f - 2.f * Fall);
	RigSetFigure(FigureRest + FVector(0.f, 0.f, 18.f * Ease - FMath::Max(0.f, DeadTime - VLRules::CorpseSeconds + 0.8f) * 60.f), FRotator(0.f, 0.f, -84.f * Ease).Quaternion());
	if (DeadTime >= VLRules::CorpseSeconds)
	{
		if (bTroop)
		{
			if (AController* C = GetController(); C && !Cast<APlayerController>(C))
			{
				C->UnPossess();
				C->Destroy();
			}
			Destroy();
		}
		else if (!IsHidden())
		{
			SetActorHiddenInGame(true);         // the king: until he rises again at his castle (UVLBattle)
		}
	}
}

float AVLKing::TakeDamage(float DamageAmount, const FDamageEvent& DamageEvent, AController* EventInstigator, AActor* DamageCauser)
{
	const float Taken = Super::TakeDamage(DamageAmount, DamageEvent, EventInstigator, DamageCauser);
	ReceiveDamage(Taken, DamageCauser);
	return Taken;
}

void AVLKing::UpdateFlash(float Dt)
{
	if (!bFlashOn)
	{
		return;
	}
	FlashLeft -= Dt;
	if (FlashLeft <= 0.f || !FlashMID)
	{
		for (UStaticMeshComponent* PartMesh : Meshes)          // his own materials were never touched: just lift the overlay
		{
			PartMesh->SetOverlayMaterial(nullptr);
		}
		bFlashOn = false;
		return;
	}
	const float T = 1.f - FlashLeft / FMath::Max(HitFlashSeconds, 0.001f);
	const float Fade = T < HitFlashHold ? 1.f : 1.f - Smooth((T - HitFlashHold) / FMath::Max(1.f - HitFlashHold, 0.001f));
	static const FName FlashName(TEXT("Flash"));
	FlashMID->SetScalarParameterValue(FlashName, Fade * HitFlashStrength);
}

namespace
{
	// ---- the pose: one number per channel, so poses blend by plain interpolation. Angles in degrees, lengths in cm.
	enum EPose
	{
		P_Drop, P_Shift,                     // the pelvis: down, forward (the feet stay where they are)
		P_PelvLean, P_PelvTwist, P_PelvSide, // lean forward +, twist to his right +, tip to his right +
		P_ChestLean, P_ChestTwist, P_ChestSide,   // the chest, measured against the figure (not against the pelvis)
		P_HeadLean, P_HeadTwist,             // the head, likewise
		P_ArmLP, P_ArmLIn, P_ArmLOut, P_ElbowL,   // shoulder: swing forward +, across the body +, away from the body +; elbow bend
		P_ArmRP, P_ArmRIn, P_ArmROut, P_ElbowR,
		P_FootLX, P_FootLY, P_FootLZ,        // where each sole stands, from its place at rest: forward, to his right, up
		P_FootRX, P_FootRY, P_FootRZ,
		P_AirThighL, P_AirKneeL, P_AirThighR, P_AirKneeR,   // the legs while nothing carries him
		P_Tilt,                              // the whole figure pitched forward about the hips (airborne only)
		P_BladeX, P_BladeY, P_BladeZ,        // where the blade points, chest space
		P_Count
	};
	static_assert(P_Count <= 40, "AVLKing::SwingShown and SwingCarry hold a pose each");

	bool IsLower(int32 C)
	{
		return C == P_Drop || C == P_Shift || (C >= P_FootLX && C <= P_FootRZ);
	}

	// The battle stance (References/king_stance.png): a wide lunge, right foot forward, knees bent, chest turned to
	// the left, the sword hand before his belt and the blade across his body, the free fist low and forward.
	void GuardPose(float* P)
	{
		P[P_Drop] = 8.f;
		P[P_Shift] = 0.f;
		P[P_FootRX] = 26.f;  P[P_FootRY] = 7.f;   P[P_FootRZ] = 0.f;
		P[P_FootLX] = -20.f; P[P_FootLY] = -9.f;  P[P_FootLZ] = 0.f;
		P[P_PelvLean] = 4.f;   P[P_PelvTwist] = -6.f;   P[P_PelvSide] = 0.f;
		P[P_ChestLean] = 10.f; P[P_ChestTwist] = -16.f; P[P_ChestSide] = 0.f;
		P[P_HeadLean] = 4.f;   P[P_HeadTwist] = -5.f;
		P[P_ArmRP] = 10.f; P[P_ArmRIn] = 12.f; P[P_ArmROut] = 8.f;  P[P_ElbowR] = 52.f;
		P[P_ArmLP] = 16.f; P[P_ArmLIn] = 10.f; P[P_ArmLOut] = 14.f; P[P_ElbowL] = 45.f;
		P[P_BladeX] = 0.8f; P[P_BladeY] = -0.56f; P[P_BladeZ] = 0.2f;
	}

	// ---- the swings. Each is a run of key poses over its length; the body is posed whole in every one (feet planted
	// in the lunge and the pelvis shifting over them, hips leading the chest, the chest the arm, the head staying on
	// the target, the free arm thrown the other way). The last four numbers of a pose are for the air: with nothing to
	// stand on the legs scissor instead and the whole figure tilts into the cut.
	enum ESwingPose
	{
		SP_Guard,
		SP_SideWind, SP_SideMid, SP_SideHit, SP_SideFollow,   // (a) the side slash: a broad sweep from his right across his body
		SP_DiagWind, SP_DiagHit, SP_DiagFollow,               // (b) the diagonal cut: from over the right shoulder down to his left
		SP_LowLeft, SP_FrontRise, SP_HighRight                // (c) the rising cut: from low at his left up across his front
	};

	struct FSwing
	{
		float Seconds;
		float ChainAt;        // from here on a queued next swing takes over (share of the swing)
		int32 Keys;
		float At[9];          // when each pose is reached (share of the swing)
		uint8 Pose[9];
		uint8 Ease[9];        // into pose i from the one before: 0 ease in and out, 1 gathering speed, 2 slowing, 3 even
		int32 Hits;
		float HitAt[3];       // when the blows land
	};

	const FSwing Swings[4] =
	{
		{ 0.46f, 0.80f, 6, { 0.f, 0.24f, 0.36f, 0.445f, 0.63f, 1.f }, { SP_Guard, SP_SideWind, SP_SideMid, SP_SideHit, SP_SideFollow, SP_Guard },
		  { 0, 0, 1, 3, 2, 0 }, 1, { 0.445f } },
		{ 0.46f, 0.80f, 5, { 0.f, 0.26f, 0.445f, 0.63f, 1.f }, { SP_Guard, SP_DiagWind, SP_DiagHit, SP_DiagFollow, SP_Guard },
		  { 0, 0, 1, 2, 0 }, 1, { 0.445f } },
		// (c) the rising cut, the combo's last: one wind-up (coiled low at his left, where the diagonal cut left the
		// blade), one blow rising across his front, the follow-through up at his right, back to the guard. It was
		// up-down-up, three blows in a second (the owner, 2026-11-24: "the third swing has two swings in it"): now one
		// blow, the whole swing's damage, landing as the blade passes his front. The way back from up at his right to
		// the guard is slow and eased (0.3 s), so it reads as lowering the sword and not as a second cut; a click
		// queued meanwhile chains from the top of it, where the side slash's wind-up begins anyway.
		{ 0.72f, 0.62f, 5, { 0.f, 0.26f, 0.42f, 0.58f, 1.f }, { SP_Guard, SP_LowLeft, SP_FrontRise, SP_HighRight, SP_Guard },
		  { 0, 0, 1, 2, 0 }, 1, { 0.42f } },
		// (d) the Builder's hammer at his work (and a played Builder's third blow): the old up-down-up, three blows
		// (VLConstruction's work calls for swing 2; StartSwing gives a Builder this one)
		{ 1.0f, 0.86f, 9, { 0.f, 0.10f, 0.19f, 0.29f, 0.43f, 0.53f, 0.64f, 0.75f, 1.f },
		  { SP_Guard, SP_LowLeft, SP_FrontRise, SP_HighRight, SP_DiagHit, SP_LowLeft, SP_FrontRise, SP_HighRight, SP_Guard },
		  { 0, 0, 1, 2, 1, 2, 1, 2, 0 }, 3, { 0.19f, 0.43f, 0.64f } },
	};

	void SwingPose(int32 K, float* P)
	{
		GuardPose(P);
		auto Body = [P](float Shift, float Drop, float PelvTwist, float PelvLean, float ChestTwist, float ChestLean, float ChestSide, float HeadTwist, float HeadLean)
		{
			P[P_Shift] = Shift; P[P_Drop] = Drop; P[P_PelvTwist] = PelvTwist; P[P_PelvLean] = PelvLean;
			P[P_ChestTwist] = ChestTwist; P[P_ChestLean] = ChestLean; P[P_ChestSide] = ChestSide; P[P_HeadTwist] = HeadTwist; P[P_HeadLean] = HeadLean;
		};
		auto Sword = [P](float Pitch, float In, float Out, float Elbow, float Bx, float By, float Bz)
		{
			P[P_ArmRP] = Pitch; P[P_ArmRIn] = In; P[P_ArmROut] = Out; P[P_ElbowR] = Elbow; P[P_BladeX] = Bx; P[P_BladeY] = By; P[P_BladeZ] = Bz;
		};
		auto Free = [P](float Pitch, float In, float Out, float Elbow)
		{
			P[P_ArmLP] = Pitch; P[P_ArmLIn] = In; P[P_ArmLOut] = Out; P[P_ElbowL] = Elbow;
		};
		auto InAir = [P](float ThighR, float KneeR, float ThighL, float KneeL, float Tilt)
		{
			P[P_AirThighR] = ThighR; P[P_AirKneeR] = KneeR; P[P_AirThighL] = ThighL; P[P_AirKneeL] = KneeL; P[P_Tilt] = Tilt;
		};
		switch (K)
		{
		// (a) wound up to his right: weight back, hips and chest turned right, the sword arm out to the side with the
		// hand by his ear and the blade cocked up and back, the free arm across his front
		case SP_SideWind:
			Body(-5.f, 7.f, 12.f, 2.f, 42.f, 3.f, -3.f, 10.f, 2.f);
			Sword(76.f, -78.f, 0.f, 62.f, -0.55f, 0.8f, 0.22f);
			Free(40.f, 22.f, 16.f, 60.f);
			InAir(45.f, 80.f, -15.f, 45.f, -6.f);
			break;
		case SP_SideMid:        // the hips have turned, the arm comes round level, the blade flat out to his right
			Body(2.f, 9.f, -2.f, 5.f, 14.f, 8.f, 0.f, 2.f, 5.f);
			Sword(76.f, -32.f, 0.f, 40.f, 0.5f, 0.85f, 0.08f);
			Free(10.f, 10.f, 22.f, 70.f);
			InAir(28.f, 55.f, -22.f, 58.f, 2.f);
			break;
		case SP_SideHit:        // the blow: across the front at chest height, weight on the front foot
			Body(7.f, 9.f, -12.f, 7.f, -22.f, 12.f, 2.f, -8.f, 7.f);
			Sword(78.f, 6.f, 0.f, 14.f, 0.95f, -0.3f, 0.f);
			Free(-20.f, 0.f, 26.f, 80.f);
			InAir(10.f, 30.f, -30.f, 70.f, 10.f);
			break;
		case SP_SideFollow:     // carried through to his left, the chest and the head turned after it
			Body(8.f, 9.f, -18.f, 8.f, -52.f, 14.f, 4.f, -24.f, 8.f);
			Sword(72.f, 58.f, 0.f, 42.f, -0.1f, -0.98f, -0.1f);
			Free(-36.f, 0.f, 30.f, 60.f);
			InAir(5.f, 25.f, -26.f, 60.f, 12.f);
			break;
		// (b) the sword up over the right shoulder (not straight overhead), weight back, the free arm forward
		case SP_DiagWind:
			Body(-6.f, 6.f, 10.f, 0.f, 34.f, -2.f, -4.f, 6.f, 0.f);
			Sword(135.f, -30.f, 15.f, 95.f, -0.45f, 0.4f, 0.8f);
			Free(50.f, 10.f, 22.f, 60.f);
			InAir(55.f, 85.f, -20.f, 50.f, -10.f);
			break;
		case SP_DiagHit:        // the blow: down and across, the arm long, the chest over the front leg
			Body(8.f, 10.f, -12.f, 8.f, -26.f, 20.f, 3.f, -8.f, 10.f);
			Sword(55.f, 12.f, 4.f, 12.f, 0.93f, -0.3f, -0.2f);
			Free(-28.f, 0.f, 28.f, 70.f);
			InAir(15.f, 30.f, -35.f, 75.f, 16.f);
			break;
		case SP_DiagFollow:     // the blade past his left knee
			Body(9.f, 10.f, -16.f, 9.f, -46.f, 24.f, 5.f, -14.f, 12.f);
			Sword(22.f, 42.f, 0.f, 25.f, 0.45f, -0.65f, -0.62f);
			Free(-40.f, 0.f, 30.f, 60.f);
			InAir(5.f, 25.f, -30.f, 60.f, 22.f);
			break;
		// (c) low at his left, coiled over the front leg
		case SP_LowLeft:
			Body(5.f, 10.f, -14.f, 8.f, -42.f, 18.f, 4.f, -12.f, 9.f);
			Sword(30.f, 50.f, 0.f, 45.f, 0.2f, -0.7f, -0.68f);
			Free(-30.f, 0.f, 28.f, 60.f);
			InAir(8.f, 30.f, -30.f, 65.f, 14.f);
			break;
		case SP_FrontRise:      // the rising blow, passing his front
			Body(3.f, 9.f, -2.f, 5.f, -6.f, 8.f, 0.f, -2.f, 5.f);
			Sword(75.f, 10.f, 4.f, 15.f, 0.96f, -0.1f, 0.25f);
			Free(5.f, 5.f, 24.f, 60.f);
			InAir(30.f, 55.f, -22.f, 55.f, 3.f);
			break;
		case SP_HighRight:      // up at his right, the chest opened, weight back: the top of the rise and the start of the next cut
			Body(-4.f, 6.f, 10.f, 0.f, 30.f, -3.f, -4.f, 6.f, 0.f);
			Sword(135.f, -30.f, 15.f, 70.f, -0.3f, 0.45f, 0.84f);
			Free(45.f, 10.f, 20.f, 55.f);
			InAir(50.f, 80.f, -15.f, 45.f, -8.f);
			break;
		default:
			break;
		}
	}

	FVector SlerpDir(const FVector& A, const FVector& B, float T)
	{
		const float Cos = FMath::Clamp(FVector::DotProduct(A, B), -1.f, 1.f);
		const float Angle = FMath::Acos(Cos);
		if (Angle < 0.02f || Angle > 3.1f)
		{
			return FMath::Lerp(A, B, T).GetSafeNormal(UE_SMALL_NUMBER, B);
		}
		return (A * FMath::Sin((1.f - T) * Angle) + B * FMath::Sin(T * Angle)) / FMath::Sin(Angle);
	}

	FQuat Rot(float Pitch, float Yaw, float Roll)
	{
		return FRotator(Pitch, Yaw, Roll).Quaternion();
	}

	/** A leg from hip to sole: where the sole should stand (from the hip, figure space) -> hip roll, thigh pitch (foot
	 *  forward +) and knee bend, all degrees. The foot is one piece with the shin, so a tilted shin digs its toe or heel
	 *  in: the sole is lifted by that much and the leg solved once more. */
	void SolveLeg(const FVector& ToSole, float Thigh, float Shin, float& Roll, float& Pitch, float& Knee)
	{
		FVector V = ToSole;
		for (int32 Pass = 0; Pass < 2; ++Pass)
		{
			const float H = FMath::Sqrt(V.Y * V.Y + V.Z * V.Z);
			Roll = FMath::RadiansToDegrees(FMath::Atan2(-V.Y, -V.Z));
			const float D = FMath::Clamp(FMath::Sqrt(V.X * V.X + H * H), 10.f, Thigh + Shin - 0.05f);
			const float Inner = FMath::Acos(FMath::Clamp((Thigh * Thigh + Shin * Shin - D * D) / (2.f * Thigh * Shin), -1.f, 1.f));
			Knee = 180.f - FMath::RadiansToDegrees(Inner);
			const float Beta = FMath::Atan2(V.X, H);
			const float Alpha = FMath::Acos(FMath::Clamp((Thigh * Thigh + D * D - Shin * Shin) / (2.f * Thigh * D), -1.f, 1.f));
			Pitch = FMath::RadiansToDegrees(Beta + Alpha);
			if (Pass == 0)
			{
				const float ShinTilt = FMath::DegreesToRadians(Pitch - Knee);        // + : the toe is up and the heel is down
				V.Z += ShinTilt > 0.f ? 7.5f * FMath::Sin(ShinTilt) : 17.5f * FMath::Sin(-ShinTilt);
			}
		}
	}
}

bool AVLKing::GetSwingCooldown(float& OutFill, bool& bOutReady) const
{
	OutFill = 1.f;
	bOutReady = true;
	if (IsDead() || !bArmed || (bTroop && !UVLSwordsmanCombat::CanFight(this)))
	{
		return false;
	}
	if (AttackTime >= 0.f)
	{
		const FSwing& Now = Swings[SwingKind];
		const float T = AttackTime / FMath::Max(Now.Seconds, 0.01f);
		OutFill = FMath::Clamp(T / FMath::Max(Now.ChainAt, 0.01f), 0.f, 1.f);
		bOutReady = T >= Now.ChainAt;
		return true;
	}
	// just after the swing: still shown, full and ready, for a moment (the battle stance's clock: GuardHold)
	return GuardHold > 0.f && GuardSeconds - GuardHold < 0.5f;
}

void AVLKing::Animate(float Dt, float AnimDt)
{
	if (!Loaded || !Rig.Body || !Rig.Chest)
	{
		return;
	}
	const UCharacterMovementComponent* Move = GetCharacterMovement();
	const FVector Velocity = GetVelocity();
	const float Speed = Velocity.Size2D();
	const bool bFalling = Move->IsFalling();

	// ---------------------------------------------------------------- the game's side: what happens, on the game's clock
	// (without a scabbard there is nothing to draw: "armed" is only how he carries the sword, and comes and goes quicker)
	const float DrawRate = Loaded->bHasSheath ? 1.f / DrawSeconds : (bArmed ? 1.f / 0.15f : 1.f / 0.4f);
	Draw = FMath::FInterpConstantTo(Draw, bArmed ? 1.f : 0.f, Dt, DrawRate);
	if (bAttackQueued && Draw >= 1.f)
	{
		bAttackQueued = false;
		StartSwing(0);
	}
	// the battle stance: up as a swing starts, held GuardSeconds after the last one, then back to the carry
	if (!bArmed)
	{
		GuardHold = 0.f;
	}
	else if (AttackTime >= 0.f || bAttackQueued)
	{
		GuardHold = GuardSeconds;
	}
	else
	{
		GuardHold = FMath::Max(0.f, GuardHold - Dt);
	}
	const bool bGuard = bArmed && GuardHold > 0.f;
	// drawn, back in the regular stance and left alone: after SheatheAfter seconds the sword goes back in
	if (bArmed && Draw >= 1.f && Guard <= 0.f && AttackTime < 0.f && !bAttackQueued)
	{
		RestingArmed += Dt;
		if (RestingArmed >= SheatheAfter)
		{
			bArmed = false;
		}
	}
	else
	{
		RestingArmed = 0.f;
	}
	if (AttackTime >= 0.f)
	{
		AttackTime += Dt;
		const FSwing& Now = Swings[SwingKind];
		const float T = AttackTime / Now.Seconds;
		while (HitsLanded < Now.Hits && T >= Now.HitAt[HitsLanded])
		{
			++HitsLanded;
			HitDummies(1.f / FMath::Max(Now.Hits, 1));     // every blow of a swing can land (its share of the swing's damage)
		}
		if (bComboQueued && T >= Now.ChainAt)
		{
			StartSwing(SwingKind >= 2 ? 0 : SwingKind + 1);
		}
		else if (T >= 1.f)
		{
			AttackTime = -1.f;
		}
	}
	// leaving the ground and coming back to it
	if (bFalling)
	{
		LastFallSpeed = FMath::Max(0.f, -Velocity.Z);
		if (!bWasFalling && Velocity.Z > 0.f)
		{
			bLeadLeft = FMath::Sin(Phase) > 0.f;        // the knee that was coming forward leads
		}
	}
	else if (bWasFalling)
	{
		CrouchVel += FMath::Min(LandImpulse * LastFallSpeed, 34.f);     // the landing: the knees take it
		if (bFootDust && Dust && LastFallSpeed > 320.f)
		{
			const FVector Feet = GetActorLocation() - FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
			Dust->Emit(Feet, -GetActorForwardVector(), 2 * Dust->PuffsPerStep + 1, 1.6f);     // and the ground gives up a puff
		}
		if (bFootsteps && LastFallSpeed > 150.f)
		{
			PlayFootstep(GetFeet(), 1.f);       // both feet, as one firm step
		}
		LastFallSpeed = 0.f;
	}
	bWasFalling = bFalling;

	// ---------------------------------------------------------------- what is shown, on the pose's clock
	const float WantGait = bFalling ? FMath::Min(Gait, 1.f) : (Speed < 12.f ? 0.f : FMath::GetMappedRangeValueClamped(FVector2D(WalkSpeed, RunSpeed), FVector2D(1.f, 2.f), Speed) * FMath::Clamp(Speed / (WalkSpeed * 0.8f), 0.f, 1.f));
	Gait = FMath::FInterpTo(Gait, WantGait, AnimDt, 9.f);
	const float Stride = FMath::Max(40.f, Loaded->StrideLength) * StrideScale * (1.f + 0.35f * FMath::Clamp(Gait - 1.f, 0.f, 1.f));
	Phase = FMath::Fmod(Phase + (Speed / Stride) * AnimDt * 2.f * PI, 2.f * PI);
	IdleTime += AnimDt;
	Air = FMath::FInterpConstantTo(Air, bFalling ? 1.f : 0.f, AnimDt, bFalling ? 9.f : 14.f);
	Rise = FMath::FInterpTo(Rise, FMath::Clamp(Velocity.Z / FMath::Max(Move->JumpZVelocity, 1.f), -1.f, 1.f), AnimDt, 14.f);
	{
		// the landing spring: sinks at once, comes back up with a little weight
		float Left = AnimDt;
		while (Left > 0.f)
		{
			const float H = FMath::Min(Left, 1.f / 90.f);
			Left -= H;
			CrouchVel += (-LandSpring * LandSpring * Crouch - 2.f * LandDamping * LandSpring * CrouchVel) * H;
			Crouch += CrouchVel * H;
		}
		if (Crouch > 1.f)
		{
			Crouch = 1.f;
			CrouchVel = FMath::Min(CrouchVel, 0.f);
		}
		Crouch = FMath::Max(Crouch, -0.08f);
	}
	DrawVis = FMath::FInterpConstantTo(DrawVis, bArmed ? 1.f : 0.f, AnimDt, DrawRate);
	Guard = FMath::FInterpConstantTo(Guard, bGuard ? 1.f : 0.f, AnimDt, bGuard ? 1.f / 0.14f : 1.f / 0.4f);
	if (SwingTime >= 0.f)
	{
		SwingTime += AnimDt;
		if (SwingTime >= Swings[SwingKind].Seconds)
		{
			SwingTime = -1.f;
		}
	}

	// ---------------------------------------------------------------- the pose
	// Built now for a unit whose pose the game needs this frame (the player's, the King, an archer with a shot on the
	// way) and whenever the old path or "every unit, every frame" is asked for. Otherwise it is left to the late pass
	// (RigLate), which knows where the camera is: a unit out of view is not posed at all, a far one less often. The
	// clocks above have moved on either way, so the pose is right the moment it is built.
	RigPoseDt += AnimDt;
	RigSincePose += Dt;
	if (bRigLegacy || bRigDemand || bFootDust || bFootsteps || !bTroop || IsPlayerControlled() || !VLRigLodOn())
	{
		PoseNow(true);
	}
}

void AVLKing::PoseFigure(float AnimDt)
{
	const FVector Velocity = GetVelocity();
	const float Speed = Velocity.Size2D();
	const bool bFalling = GetCharacterMovement()->IsFalling();

	const float W = FMath::Clamp(Gait, 0.f, 1.f);
	const float R = FMath::Clamp(Gait - 1.f, 0.f, 1.f);
	const float Idle = 1.f - W;
	const float Sw = FMath::Sin(Phase), Cw = FMath::Cos(Phase);
	const float Breath = FMath::Sin(IdleTime * 1.9f);
	const float G = Smooth(Guard) * Smooth(DrawVis);
	const float CarryW = Smooth((DrawVis - 0.6f) / 0.4f);
	const float Up = FMath::Max(Rise, 0.f), Down = FMath::Max(-Rise, 0.f);

	// ---- walking and running. The feet are placed (forward and back along the ground, lifted on the way forward)
	// and the legs solved to reach them; the pelvis rides lowest when the feet are furthest apart.
	float P[P_Count] = {};
	// (a longer stride, StrideScale: the feet reach further, so the pelvis drops further for the legs to reach them;
	// the reach stays Stride / 2 pi, which keeps a planted foot still on the ground)
	P[P_Drop] = W * ((0.5f + 1.5f * R) + (3.4f + 1.6f * R) * StrideScale * StrideScale * StrideScale * Sw * Sw);     // (~ what a 67 cm leg needs at that reach)
	const float LiftCos = FMath::Cos(Phase + 0.3f);
	{
		const float Reach = W * (23.f + 7.f * R) * StrideScale, Lift = W * (6.f + 10.f * R) * FMath::Sqrt(StrideScale);
		P[P_FootLX] = Reach * Sw;
		P[P_FootLZ] = (Lift > 0.f && LiftCos > 0.f) ? Lift * FMath::Pow(LiftCos, 1.2f) : 0.f;
		P[P_FootRX] = -Reach * Sw;
		P[P_FootRZ] = (Lift > 0.f && LiftCos < 0.f) ? Lift * FMath::Pow(-LiftCos, 1.2f) : 0.f;
	}
	P[P_PelvLean] = W * (2.f + 4.f * R);
	P[P_PelvTwist] = Sw * (5.f + 3.f * R) * W;                 // the hip goes forward with its leg ..
	P[P_ChestLean] = W * FMath::Lerp(5.f, RunLean, R) + Breath * 0.8f * Idle;
	P[P_ChestTwist] = -Sw * (6.f + 6.f * R) * W;               // .. and the shoulders against it
	P[P_ChestSide] = Cw * 2.f * W;
	P[P_HeadLean] = P[P_ChestLean] * 0.35f + Breath * 0.5f * Idle;
	P[P_HeadTwist] = FMath::Sin(IdleTime * 0.45f) * 5.f * Idle;
	{
		// the arms swing against the legs; at a run the elbows fold and the fists pump before the chest
		const float Swing = W * (22.f + 14.f * R), Back = W * R * 14.f, Pump = W * (6.f + 10.f * R);
		const float Fold = W * FMath::Lerp(28.f, RunElbow, R);
		P[P_ArmLP] = -Sw * Swing - Back;
		P[P_ArmRP] = Sw * Swing - Back;
		P[P_ArmLOut] = P[P_ArmROut] = 2.f + Breath * 1.2f * Idle + 5.f * W * R;
		P[P_ArmLIn] = P[P_ArmRIn] = 8.f * W * R;
		P[P_ElbowL] = Idle * 16.f + Fold - Pump * Sw;
		P[P_ElbowR] = Idle * 22.f + Fold + Pump * Sw;
		// sword out: carried low at his side, the arm nearly straight, swinging a little with the stride
		P[P_ArmRP] = FMath::Lerp(P[P_ArmRP], -8.f + Sw * Swing * 0.6f - W * R * 10.f, CarryW);
		P[P_ElbowR] = FMath::Lerp(P[P_ElbowR], 10.f + W * (8.f + 40.f * R), CarryW);
		P[P_ArmROut] = FMath::Lerp(P[P_ArmROut], 4.f, CarryW);
		P[P_ArmRIn] = FMath::Lerp(P[P_ArmRIn], 0.f, CarryW);
	}
	P[P_BladeX] = 1.f; P[P_BladeY] = 0.22f; P[P_BladeZ] = -0.42f + 0.27f * W * R;       // the carry: tip forward and down

	// ---- in the air: rising with the leading knee up, opening out over the top, reaching down for the ground
	{
		const float LeadThigh = Rise > 0.f ? FMath::Lerp(40.f, 50.f, Up) : FMath::Lerp(40.f, 18.f, Down);
		const float LeadKnee = Rise > 0.f ? FMath::Lerp(65.f, 75.f, Up) : FMath::Lerp(65.f, 22.f, Down);
		const float TrailThigh = Rise > 0.f ? FMath::Lerp(5.f, -12.f, Up) : FMath::Lerp(5.f, -8.f, Down);
		const float TrailKnee = Rise > 0.f ? FMath::Lerp(55.f, 30.f, Up) : FMath::Lerp(55.f, 28.f, Down);
		P[P_AirThighL] = bLeadLeft ? LeadThigh : TrailThigh;
		P[P_AirKneeL] = bLeadLeft ? LeadKnee : TrailKnee;
		P[P_AirThighR] = bLeadLeft ? TrailThigh : LeadThigh;
		P[P_AirKneeR] = bLeadLeft ? TrailKnee : LeadKnee;
		const float ArmP = Rise > 0.f ? FMath::Lerp(10.f, 32.f, Up) : FMath::Lerp(10.f, -6.f, Down);
		const float ArmOut = Rise > 0.f ? FMath::Lerp(30.f, 18.f, Up) : FMath::Lerp(30.f, 42.f, Down);
		const float Elbow = Rise > 0.f ? FMath::Lerp(45.f, 55.f, Up) : FMath::Lerp(45.f, 35.f, Down);
		const float ArmedAir = Air * (1.f - 0.6f * CarryW);            // the sword arm joins in less
		P[P_ArmLP] = FMath::Lerp(P[P_ArmLP], ArmP + 6.f, Air);
		P[P_ArmLOut] = FMath::Lerp(P[P_ArmLOut], ArmOut, Air);
		P[P_ElbowL] = FMath::Lerp(P[P_ElbowL], Elbow, Air);
		P[P_ArmRP] = FMath::Lerp(P[P_ArmRP], ArmP - 6.f, ArmedAir);
		P[P_ArmROut] = FMath::Lerp(P[P_ArmROut], ArmOut, ArmedAir);
		P[P_ElbowR] = FMath::Lerp(P[P_ElbowR], Elbow, ArmedAir);
		P[P_ChestLean] = FMath::Lerp(P[P_ChestLean], Rise > 0.f ? FMath::Lerp(4.f, -2.f, Up) : FMath::Lerp(4.f, 9.f, Down), Air);
		P[P_ChestTwist] *= 1.f - Air;
		P[P_PelvTwist] *= 1.f - Air;
		P[P_HeadLean] = FMath::Lerp(P[P_HeadLean], 10.f * Down, Air);
	}

	// ---- the battle stance: held fully while standing, the feet less so while he walks
	const float StanceFeet = 1.f - 0.6f * W;
	if (G > 0.f)
	{
		float S[P_Count];
		FMemory::Memcpy(S, P, sizeof(P));
		GuardPose(S);
		for (int32 C = 0; C < P_Count; ++C)
		{
			P[C] = FMath::Lerp(P[C], S[C], IsLower(C) ? G * StanceFeet : G);
		}
	}
	// ---- the swing
	float SwingW = 0.f;
	if (SwingTime >= 0.f)
	{
		const FSwing& Now = Swings[SwingKind];
		const float T = FMath::Clamp(SwingTime / Now.Seconds, 0.f, 1.f);
		int32 K = 0;
		while (K < Now.Keys - 2 && T >= Now.At[K + 1])
		{
			++K;
		}
		float A = FMath::Clamp((T - Now.At[K]) / (Now.At[K + 1] - Now.At[K]), 0.f, 1.f);
		const uint8 Ease = Now.Ease[K + 1];
		A = Ease == 1 ? FMath::Pow(A, 1.8f)                    // a strike gathers speed into the blow ..
			: Ease == 2 ? 1.f - FMath::Pow(1.f - A, 1.8f)      // .. which carries on and slows ..
			: Ease == 3 ? A
			: Smooth(A);                                       // .. the wind-up and the recovery ease in and out
		float From[P_Count], To[P_Count];
		FMemory::Memcpy(From, P, sizeof(P));
		FMemory::Memcpy(To, P, sizeof(P));
		SwingPose(Now.Pose[K], From);
		SwingPose(Now.Pose[K + 1], To);
		for (int32 C = 0; C < P_Count; ++C)
		{
			SwingShown[C] = FMath::Lerp(From[C], To[C], A);
		}
		const FVector Blade = SlerpDir(FVector(From[P_BladeX], From[P_BladeY], From[P_BladeZ]).GetSafeNormal(), FVector(To[P_BladeX], To[P_BladeY], To[P_BladeZ]).GetSafeNormal(), A);
		SwingShown[P_BladeX] = Blade.X; SwingShown[P_BladeY] = Blade.Y; SwingShown[P_BladeZ] = Blade.Z;
		const float In = Smooth(SwingTime / 0.07f);
		if (bSwingCarry)
		{
			// following on from the swing before: out of where that one had got to
			for (int32 C = 0; C < P_Count; ++C)
			{
				SwingShown[C] = FMath::Lerp(SwingCarry[C], SwingShown[C], In);
			}
			SwingW = 1.f;
		}
		else
		{
			SwingW = In;
		}
		for (int32 C = 0; C < P_Count; ++C)
		{
			P[C] = FMath::Lerp(P[C], SwingShown[C], IsLower(C) ? SwingW * StanceFeet : SwingW);
		}
	}
	// ---- the landing: knees, a bow of the chest, the arms down and out
	{
		const float C = Crouch, Free = 1.f - 0.7f * FMath::Max(G, SwingW);
		P[P_Drop] += LandDepth * C;
		P[P_PelvLean] += 6.f * C;
		P[P_ChestLean] += 15.f * C;
		P[P_HeadLean] += 3.f * C;
		P[P_ArmLP] -= 12.f * C * Free;  P[P_ArmLOut] += 10.f * C * Free;  P[P_ElbowL] += 22.f * C * Free;
		P[P_ArmRP] -= 12.f * C * Free;  P[P_ArmROut] += 10.f * C * Free;  P[P_ElbowR] += 22.f * C * Free;
	}
	// ---- drawing and sheathing: the chest turns the sword shoulder towards the hip
	const float DrawTravel = Smooth((DrawVis - 0.42f) / 0.48f);
	const float ReachW = (Loaded->bHasSheath && SwordJoint) ? FMath::Min(Smooth((DrawVis - 0.05f) / 0.33f), 1.f - Smooth((DrawVis - 0.82f) / 0.18f)) : 0.f;
	P[P_ChestTwist] -= 24.f * ReachW * (1.f - DrawTravel);
	P[P_ChestLean] += 5.f * ReachW * (1.f - DrawTravel);

	// ---------------------------------------------------------------- pose the figure
	const float Tilt = P[P_Tilt] * Air;
	const FQuat TiltQ = Rot(-Tilt, 0.f, 0.f);
	const FVector HipMid(0.f, 0.f, Rig.HipHeight);
	const float DropNow = P[P_Drop] * (1.f - Air), ShiftNow = P[P_Shift] * (1.f - Air);
	RigSetFigure(FigureRest + FVector(ShiftNow, 0.f, -DropNow) + HipMid - TiltQ.RotateVector(HipMid), TiltQ);
	const FQuat PelvisQ = Rot(-P[P_PelvLean], P[P_PelvTwist], P[P_PelvSide]);
	const FQuat ChestQ = Rot(-P[P_ChestLean], P[P_ChestTwist], P[P_ChestSide]);
	const FQuat HeadQ = Rot(-P[P_HeadLean], P[P_HeadTwist], 0.f);
	RigSetRelRot(Rig.iBody, PelvisQ);
	RigSetRelRot(Rig.iChest, PelvisQ.Inverse() * ChestQ);
	if (Rig.Head)
	{
		RigSetRelRot(Rig.iHead, ChestQ.Inverse() * HeadQ);
	}
	if (Rig.ArmL && Rig.ForeL)
	{
		RigSetRelRot(Rig.iArmL, Rot(P[P_ArmLP], P[P_ArmLIn], P[P_ArmLOut]));
		RigSetRelRot(Rig.iForeL, Rot(P[P_ElbowL] - Loaded->ElbowRestL, 0.f, 0.f));
	}
	if (Rig.ArmR && Rig.ForeR)
	{
		RigSetRelRot(Rig.iArmR, Rot(P[P_ArmRP], -P[P_ArmRIn], -P[P_ArmROut]));
		RigSetRelRot(Rig.iForeR, Rot(P[P_ElbowR] - Loaded->ElbowRestR, 0.f, 0.f));
	}
	// legs: solved to their footholds on the ground, taken over by the airborne angles as he leaves it
	KneeBack = FVector(1000.f, 0.f, 0.f);
	for (int32 Side = 0; Side < 2; ++Side)
	{
		const int32 Leg = Side == 0 ? Rig.iLegL : Rig.iLegR;
		const int32 Shin = Side == 0 ? Rig.iShinL : Rig.iShinR;
		if (Leg < 0 || Shin < 0)
		{
			continue;
		}
		const FVector& Hip = Side == 0 ? Rig.HipL : Rig.HipR;
		const float* F = &P[Side == 0 ? P_FootLX : P_FootRX];
		float Roll, Pitch, Knee;
		SolveLeg(FVector(F[0] - ShiftNow, F[1], F[2] + DropNow - Hip.Z), Rig.Thigh, Rig.Shin, Roll, Pitch, Knee);
		Pitch = FMath::Lerp(Pitch, P[Side == 0 ? P_AirThighL : P_AirThighR], Air);
		Knee = FMath::Lerp(Knee, P[Side == 0 ? P_AirKneeL : P_AirKneeR], Air);
		Roll = FMath::Lerp(Roll, Side == 0 ? 4.f : -4.f, Air);
		const FQuat ThighQ = Rot(0.f, 0.f, Roll) * Rot(Pitch, 0.f, 0.f);
		RigSetRelRot(Leg, ThighQ);
		RigSetRelRot(Shin, Rot(-Knee, 0.f, 0.f));
		const FVector KneeAt = Hip + ThighQ.RotateVector(FVector(0.f, 0.f, -Rig.Thigh));
		const FVector Heel = KneeAt + (ThighQ * Rot(-Knee, 0.f, 0.f)).RotateVector(FVector(-9.f, 0.f, -Rig.Shin));
		KneeBack.X = FMath::Min3(KneeBack.X, KneeAt.X - 8.f, Heel.X);
	}
	KneeBack.X += ShiftNow;
	// footfalls: a step sound (louder and snappier at a run), and dust where a running foot comes down; dust under both
	// feet while he brakes hard out of a run. A foot is in the air for the half of the gait's cycle in which it is
	// lifted (the cosine below is the one that lifts it, above), and comes down as that half ends: read from the
	// cycle and not from the height of the sole, so that it holds at any speed and frame rate (a slow walk hardly
	// lifts the feet). Two steps a cycle: one every Stride / (2 Speed) seconds.
	if (((bFootDust && Dust) || bFootsteps) && AnimDt > 0.f)
	{
		const FVector Feet = GetActorLocation() - FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
		const FVector Back = Speed > 1.f ? -FVector(Velocity.X, Velocity.Y, 0.f).GetSafeNormal() : -GetActorForwardVector();
		for (int32 Side = 0; Side < 2; ++Side)
		{
			const bool bDown = Side == 0 ? LiftCos <= 0.f : LiftCos >= 0.f;
			if (bDown && !bFootDown[Side] && !bFalling && Speed > 60.f)
			{
				const FVector& Hip = Side == 0 ? Rig.HipL : Rig.HipR;
				const FVector Foot = Feet + GetActorQuat().RotateVector(FVector(P[Side == 0 ? P_FootLX : P_FootRX] - 6.f, Hip.Y, 0.f));
				if (bFootDust && Dust && R > 0.5f)
				{
					Dust->Emit(Foot, Back, Dust->PuffsPerStep);
				}
				if (bFootsteps)
				{
					PlayFootstep(Foot, R);
				}
			}
			bFootDown[Side] = bDown;
		}
		SkidTimer -= AnimDt;
		if (!bFalling && LastSpeed > WalkSpeed && (LastSpeed - Speed) / AnimDt > 1500.f * (RunSpeed / 760.f) && SkidTimer <= 0.f)
		{
			SkidTimer = 0.07f;
			if (Dust)
			{
				Dust->Emit(Feet - Back * 14.f, -Back, 2, 1.2f);        // thrown ahead of him, the way he was going
			}
		}
	}
	LastSpeed = Speed;
	if (Dust)
	{
		Dust->Advance(AnimDt);
	}
	UpdateSword(P, AnimDt);
	UpdateCape(bRigCapeHeld ? 0.f : AnimDt);        // (far off, RigLate: the cloth holds its shape)
}

void AVLKing::UpdateSword(const float* Pose, float AnimDt)
{
	if (!SwordJoint || !Rig.HandR || !Rig.ForeR || !Rig.ArmR || !Loaded)
	{
		return;
	}
	// The wrist. The sword is one with the fist, so the blade is aimed by the hand: turned about the forearm as far as
	// it takes (nothing shows of that), then bent sideways towards the wanted line, as far as a wrist bends.
	{
		const FVector Want = RigWorldRot(Rig.iForeR).UnrotateVector(RigWorldRot(Rig.iChest).RotateVector(FVector(Pose[P_BladeX], Pose[P_BladeY], Pose[P_BladeZ]).GetSafeNormal()));
		const FVector A = Rig.ForeAxis;
		const FVector B0 = (Rig.Blade - A * FVector::DotProduct(Rig.Blade, A)).GetSafeNormal();
		FVector B1 = Want - A * FVector::DotProduct(Want, A);
		B1 = B1.SizeSquared() < 1e-4f ? B0 : B1.GetSafeNormal();
		const float Turn = FMath::Atan2(FVector::DotProduct(FVector::CrossProduct(B0, B1), A), FVector::DotProduct(B0, B1));
		FQuat TwistQ(A, Turn);
		if (FVector::DotProduct(TwistQ.RotateVector(B0), B1) < FVector::DotProduct(FQuat(A, -Turn).RotateVector(B0), B1))
		{
			TwistQ = FQuat(A, -Turn);
		}
		const float Bend = FMath::Clamp(FMath::Asin(FMath::Clamp(FVector::DotProduct(Want, A), -1.f, 1.f)), FMath::DegreesToRadians(-25.f), FMath::DegreesToRadians(50.f));
		const FQuat BendQ = FQuat::FindBetweenNormals(B1, (B1 * FMath::Cos(Bend) + A * FMath::Sin(Bend)).GetSafeNormal());
		const FQuat WantQ = BendQ * TwistQ;
		WristQ = bRigResume ? WantQ : FQuat::Slerp(WristQ, WantQ, 1.f - FMath::Exp(-AnimDt * 28.f)).GetNormalized();     // (posed again after a gap: where it should be)
		RigSetRelRot(Rig.iHandR, WristQ);
	}
	if (!Loaded->bHasSheath)
	{
		const FTransform Hand = RigWorld(Rig.iHandR);
		RigSetWorldLocRot(Rig.iSword, Hand.TransformPosition(Rig.GripOff), Hand.GetRotation());
		return;
	}
	const FTransform Hip = RigWorld(Rig.iBody);
	const FVector SheathPos = Hip.TransformPosition(Loaded->SwordSheathPos - RigRelLoc(Rig.iBody));
	const FVector4 Q = Loaded->SwordSheathQuat;
	const FQuat Delta(Q.X, Q.Y, Q.Z, Q.W);
	const FQuat SheathRot = Hip.GetRotation() * Delta;
	if (DrawVis <= 0.f)
	{
		RigSetWorldLocRot(Rig.iSword, SheathPos, SheathRot);
		return;
	}
	// Drawing (and, backwards, sheathing): the hand goes to the hilt in the scabbard, closes on it, and from then on
	// the sword is in the fist: it comes straight out along the scabbard, then round in front of him to the carry.
	const float Travel = Smooth((DrawVis - 0.42f) / 0.48f);
	const float ReachW = FMath::Min(Smooth((DrawVis - 0.05f) / 0.33f), 1.f - Smooth((DrawVis - 0.82f) / 0.18f));
	if (ReachW > 0.f)
	{
		const FTransform CarryHand = RigWorld(Rig.iHandR);
		const FQuat CarryRot = CarryHand.GetRotation();
		const FVector CarryPos = CarryHand.TransformPosition(Rig.GripOff);
		const FVector Along = Delta.RotateVector(Rig.Blade);                               // down the scabbard, body space
		FVector GripPos = FMath::Lerp(SheathPos, CarryPos, Travel);
		GripPos += Hip.GetRotation().RotateVector(-Along * 34.f + FVector(46.f, 0.f, 10.f)) * FMath::Sin(Travel * PI);
		const FQuat GripRot = FQuat::Slerp(SheathRot, CarryRot, Travel);
		const FQuat HandRot = FQuat::Slerp(CarryRot, GripRot, ReachW);
		// the arm: shoulder and elbow solved so the wrist is where that hold puts it (chest space)
		const FTransform Chest = RigWorld(Rig.iChest);
		const FVector Target = Chest.InverseTransformPosition(GripPos - GripRot.RotateVector(Rig.GripOff)) - Rig.ShoulderR;
		const float Lu = Rig.UpperR.Size(), Lf = Rig.ForeVecR.Size();
		const float D = FMath::Clamp(Target.Size(), FMath::Abs(Lu - Lf) + 2.f, Lu + Lf - 0.3f);
		const float Bent = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp((D * D - Lu * Lu - Lf * Lf) / (2.f * Lu * Lf), -1.f, 1.f)));
		const float Bent0 = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(Rig.UpperR.GetSafeNormal(), Rig.ForeVecR.GetSafeNormal()), -1.f, 1.f)));
		const float Elbow = Bent - Bent0;                                                  // on top of the bend it is modelled with
		const FVector Reach = Rig.UpperR + Rot(Elbow, 0.f, 0.f).RotateVector(Rig.ForeVecR);
		const FVector Dir = Target.GetSafeNormal();
		FQuat ShoulderQ = FQuat::FindBetweenNormals(Reach.GetSafeNormal(), Dir);
		{
			// the elbow hangs down and out, a little behind
			const FVector Pole(-0.3f, 0.6f, -0.74f);
			const FVector E = ShoulderQ.RotateVector(Rig.UpperR);
			const FVector E1 = (E - Dir * FVector::DotProduct(E, Dir)).GetSafeNormal();
			const FVector P1 = (Pole - Dir * FVector::DotProduct(Pole, Dir)).GetSafeNormal();
			if (!E1.IsNearlyZero() && !P1.IsNearlyZero())
			{
				ShoulderQ = FQuat::FindBetweenNormals(E1, P1) * ShoulderQ;
			}
		}
		const FQuat ShoulderNow = RigRelRot(Rig.iArmR);
		RigSetRelRot(Rig.iArmR, FQuat::Slerp(ShoulderNow, ShoulderQ, ReachW));
		RigSetRelRot(Rig.iForeR, Rot(FMath::Lerp(Pose[P_ElbowR] - Loaded->ElbowRestR, Elbow, ReachW), 0.f, 0.f));
		RigSetWorldRot(Rig.iHandR, HandRot);
	}
	if (Travel <= 0.f)
	{
		RigSetWorldLocRot(Rig.iSword, SheathPos, SheathRot);
		return;
	}
	const FTransform HandNow = RigWorld(Rig.iHandR);
	const FVector InHand = HandNow.TransformPosition(Rig.GripOff);
	const float Taken = Smooth(Travel / 0.12f);         // the moment the hand closes: the last of any gap is taken up
	RigSetWorldLocRot(Rig.iSword, FMath::Lerp(SheathPos, InHand, Taken), FQuat::Slerp(SheathRot, HandNow.GetRotation(), Taken));
}

void AVLKing::UpdateCape(float AnimDt)
{
	if (CapeCols <= 0 || CapeRows <= 0)
	{
		return;
	}
	const FQuat ActorQ = GetActorQuat();
	const FVector Origin = GetActorLocation();
	const FVector Fwd = ActorQ.GetForwardVector(), Right = ActorQ.GetRightVector();
	const float Ground = Origin.Z - GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const float ChestYaw = FRotator::NormalizeAxis((ActorQ.Inverse() * RigWorldRot(Rig.iChest)).Rotator().Yaw);
	const FVector ChestFwd = (ActorQ * FRotator(0.f, ChestYaw, 0.f).Quaternion()).GetForwardVector();
	const float CapeShift = FigureLocal.GetLocation().X - FigureRest.X;
	const bool bStep = AnimDt > 1e-5f && bCapeStarted;
	if (bRigResume)
	{
		// posed again after a gap (it was out of view): the cloth hangs as it did, at rest
		for (int32 C = 0; C < CapeCols; ++C)
		{
			for (int32 Row = 0; Row < CapeRows; ++Row)
			{
				FCapePanel& N = Cape[C][Row];
				N.Vel = N.Acc = FVector::ZeroVector;
				N.PitchVel = N.RollVel = 0.f;
			}
		}
	}
	if (bStep)
	{
		CapeTime += AnimDt;
		// what the cape may not swing into: the back of the hips for the upper rows; for the lower ones the back of
		// the legs too (a heel kicked up pushes it out at once; it comes back in more slowly)
		CapeBackUpper = -17.f;                                   // (both measured from the pelvis)
		const float Lower = FMath::Min(-14.f, KneeBack.X - CapeShift - 5.f);
		CapeBackLower = Lower < CapeBackLower ? Lower : FMath::Min(Lower, CapeBackLower + 90.f * AnimDt);
	}
	const float SpeedShare = FMath::Clamp(GetVelocity().Size() / FMath::Max(RunSpeed, 1.f), 0.f, 1.2f);
	const float InvDt = bStep ? (1.f / AnimDt) : 0.f;
	const float VelAlpha = bStep ? (1.f - FMath::Exp(-AnimDt * 18.f)) : 0.f;
	const float AccAlpha = bStep ? (1.f - FMath::Exp(-AnimDt * 10.f)) : 0.f;
	for (int32 C = 0; C < CapeCols; ++C)
	{
		float YawAbove = ChestYaw;
		for (int32 Row = 0; Row < CapeRows; ++Row)
		{
			FCapePanel& N = Cape[C][Row];
			if (!N.Joint || N.Node < 0)
			{
				break;
			}
			const FVector Hinge = RigWorldLoc(N.Node);       // the panel above has been turned already
			if (bStep)
			{
				const float Deep = float(Row + 1) / float(CapeRows);
				const FVector V = (Hinge - N.Prev) * InvDt;
				const FVector Was = N.Vel;
				N.Vel = FMath::Lerp(N.Vel, V, VelAlpha);
				N.Acc = FMath::Lerp(N.Acc, (N.Vel - Was) * InvDt, AccAlpha);
				const float Vf = FVector::DotProduct(N.Vel, Fwd), Vr = FVector::DotProduct(N.Vel, Right), Vz = N.Vel.Z;
				const float Af = FVector::DotProduct(N.Acc, Fwd), Ar = FVector::DotProduct(N.Acc, Right);
				// where it wants to hang: streamed back by his speed, thrown by his acceleration, lifted by a fall,
				// with a ripple that runs down and across it, and drawn towards its neighbours (it is one cloth)
				float WantPitch = CapeTrail * Vf * (0.55f + 0.45f * Deep) + CapeInertia * FMath::Clamp(Af, -3000.f, 3000.f) * Deep
					+ (Vz < 0.f ? -CapeFall * Vz : -0.012f * Vz) * Deep
					+ CapeFlutter * SpeedShare * FMath::Sin(CapeTime * 9.f - Row * 1.1f + C * 0.9f) * (0.4f + 0.6f * Deep)
					+ 1.2f * FMath::Sin(CapeTime * 1.3f + C * 0.7f - Row * 0.5f) * Deep;
				float WantRoll = (0.035f * Vr + 0.004f * FMath::Clamp(Ar, -3000.f, 3000.f)) * Deep
					+ 0.4f * CapeFlutter * SpeedShare * FMath::Sin(CapeTime * 7.f - Row * 0.9f + C * 1.7f) * Deep;
				WantPitch = 60.f * FMath::Tanh(WantPitch / 60.f);
				WantRoll = FMath::Clamp(WantRoll, -25.f, 25.f);
				const float Near = 0.5f * ((C > 0 ? Cape[C - 1][Row].Pitch : N.Pitch) + (C + 1 < CapeCols ? Cape[C + 1][Row].Pitch : N.Pitch));
				WantPitch += 0.3f * (Near - N.Pitch);
				const float Stiff = FMath::Lerp(CapeStiffTop, CapeStiffHem, Deep);
				float Left = AnimDt;
				while (Left > 0.f)
				{
					const float H = FMath::Min(Left, 1.f / 90.f);
					Left -= H;
					N.PitchVel += (Stiff * Stiff * (WantPitch - N.Pitch) - 2.f * CapeDamping * Stiff * N.PitchVel) * H;
					N.Pitch += N.PitchVel * H;
					N.RollVel += (Stiff * Stiff * (WantRoll - N.Roll) - 2.f * CapeDamping * Stiff * N.RollVel) * H;
					N.Roll += N.RollVel * H;
				}
				N.Yaw += FRotator::NormalizeAxis(YawAbove - N.Yaw) * (1.f - FMath::Exp(-AnimDt * FMath::Lerp(CapeYawLag * 1.6f, CapeYawLag, Deep)));
			}
			else if (!bCapeStarted)
			{
				N.Yaw = YawAbove;
			}
			// kept out of his body and off the ground: the foot of the panel may not pass in front of his back and legs,
			// nor sink into the floor (it lies back along it instead)
			{
				// (measured the way the chest faces: when he twists, the cape's edges come round with his shoulders)
				const float Hx = FVector::DotProduct(Hinge - Origin, ChestFwd) - CapeShift;
				const float Hz = Hinge.Z - Ground - 3.f;
				const float Back = Row * 2 >= CapeRows ? CapeBackLower : CapeBackUpper;
				float Least = FMath::Min(FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp((Hx - Back) / N.Length, -1.f, 1.f))) - N.Slope, 50.f);   // (a heel kicked high lifts it no further than this)
				if (Hz < N.Length)
				{
					Least = FMath::Max(Least, FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(Hz / N.Length, 0.f, 1.f))) - N.Slope);
				}
				Least = FMath::Min(Least, 85.f);
				if (N.Pitch < Least)
				{
					N.Pitch = Least;
					N.PitchVel = FMath::Max(N.PitchVel, 0.f);
				}
				N.Pitch = FMath::Min(N.Pitch, 88.f);
			}
			RigSetWorldRot(N.Node, ActorQ * Rot(0.f, N.Yaw, 0.f) * Rot(0.f, 0.f, N.Roll) * Rot(-N.Pitch, 0.f, 0.f));
			N.Prev = Hinge;
			YawAbove = N.Yaw;
		}
	}
	bCapeStarted = true;
}

namespace
{
	TAutoConsoleVariable<int32> CVarStepLog(TEXT("vl.StepLog"), 0, TEXT("1: log every footstep (surface, material, clip, volume) and every shuffle step of marching troops"));

	const TCHAR* StepSurfaceName(EVLStepSurface S)
	{
		static const TCHAR* Names[] = { TEXT("Dirt"), TEXT("Cement"), TEXT("Wood"), TEXT("Carpet") };
		return Names[FMath::Clamp(int32(S), 0, 3)];
	}
}

USoundBase* FVLStepSet::Pick(EVLStepSurface Surface, int32* OutIndex)
{
	if (!bLoaded)
	{
		bLoaded = true;
		for (int32 i = 1; i <= 12; ++i)
		{
			const FString Name = FString::Printf(TEXT("S_Step_%s_%d"), StepSurfaceName(Surface), i);
			if (USoundBase* S = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Voxel/Audio/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet))
			{
				Sounds.Add(S);
			}
		}
		if (Sounds.Num() == 0)
		{
			UE_LOG(LogSovereignRealms, Warning, TEXT("no step sounds for %s (Tools/ue/import_audio.py)"), StepSurfaceName(Surface));
		}
	}
	if (Sounds.Num() == 0)
	{
		return nullptr;
	}
	int32 Index = FMath::RandRange(0, Sounds.Num() - 1);
	if (Index == Last && Sounds.Num() > 1)
	{
		Index = (Index + FMath::RandRange(1, Sounds.Num() - 1)) % Sounds.Num();
	}
	Last = Index;
	if (OutIndex)
	{
		*OutIndex = Index + 1;
	}
	return Sounds[Index];
}

EVLStepSurface AVLKing::SurfaceUnder(const FVector& Foot, FString* OutMaterial) const
{
	FCollisionQueryParams Params(SCENE_QUERY_STAT(VLStep), true, this);
	Params.bReturnFaceIndex = true;         // the meshes collide with their own triangles: the one hit names its material
	const UWorld* World = GetWorld();
	FHitResult Hit;
	// under the foot; if that is over an edge (a kerb, the side of the bridge), under the body
	const FVector Mid = GetFeet();
	bool bHit = World->LineTraceSingleByChannel(Hit, Foot + FVector(0.f, 0.f, 45.f), Foot - FVector(0.f, 0.f, 60.f), ECC_Visibility, Params) && !Cast<APawn>(Hit.GetActor());
	bHit = bHit || (World->LineTraceSingleByChannel(Hit, Mid + FVector(0.f, 0.f, 45.f), Mid - FVector(0.f, 0.f, 90.f), ECC_Visibility, Params) && !Cast<APawn>(Hit.GetActor()));
	const UPrimitiveComponent* Comp = bHit ? Hit.GetComponent() : nullptr;
	int32 Section = 0;
	const UMaterialInterface* Material = Comp ? Comp->GetMaterialFromCollisionFaceIndex(Hit.FaceIndex, Section) : nullptr;
	if (!Material)
	{
		if (OutMaterial)
		{
			*OutMaterial = Comp ? FString::Printf(TEXT("(none: %s)"), *GetNameSafe(Comp->GetOwner())) : TEXT("(nothing under the foot)");
		}
		return FootstepDefault;
	}
	FString Slot = Material->GetName();
	Slot.RemoveFromStart(TEXT("MI_Vox_")) || Slot.RemoveFromStart(TEXT("MI_Sway_")) || Slot.RemoveFromStart(TEXT("MI_"));
	if (OutMaterial)
	{
		*OutMaterial = Slot;
	}
	if (const EVLStepSurface* Found = FootstepSurfaces.Find(FName(*Slot)))
	{
		return *Found;
	}
	// not listed: the longest entry its name contains (stone_mossy_dark -> stone_mossy)
	const EVLStepSurface* Best = nullptr;
	int32 BestLen = 0;
	for (const TPair<FName, EVLStepSurface>& Entry : FootstepSurfaces)
	{
		const FString Key = Entry.Key.ToString();
		if (Key.Len() > BestLen && Slot.Contains(Key))
		{
			Best = &Entry.Value;
			BestLen = Key.Len();
		}
	}
	return Best ? *Best : FootstepDefault;
}

void AVLKing::PlayFootstep(const FVector& At, float RunBlend)
{
	FString Material;
	const bool bLog = CVarStepLog.GetValueOnGameThread() != 0;
	const EVLStepSurface Surface = SurfaceUnder(At, bLog ? &Material : nullptr);
	const int32 Set = FMath::Clamp(int32(Surface), 0, 2);      // (carpet is not a floor of this world: as dirt)
	int32 Clip = 0;
	USoundBase* Sound = StepSets[Set].Pick(EVLStepSurface(Set), &Clip);
	if (!Sound)
	{
		return;
	}
	const float Run = FMath::Clamp(RunBlend, 0.f, 1.f);
	// As the troops' shuffle (AVLGameMode::TickShuffle): full within ShuffleNear of where the player is looking (the
	// unit played in the hero view, the overview's focus), fading to nothing at ShuffleRange. The unit the player
	// plays in the hero view is always at full volume.
	float Fade = 1.f, Far = 0.f;
	{
		const APlayerController* LPC = GetWorld()->GetFirstPlayerController();
		const AVLKing* Listener = LPC ? Cast<AVLKing>(LPC->GetPawn()) : nullptr;
		const AVLGameMode* GM = GetWorld()->GetAuthGameMode<AVLGameMode>();
		if (Listener && !(Listener == this && bHeroMode))
		{
			const float Near = GM ? GM->ShuffleNear : 900.f, Range = GM ? GM->ShuffleRange : 4500.f;
			Far = FVector::Dist2D(At, Listener->GetListenFocus());
			Fade = FMath::Square(FMath::GetMappedRangeValueClamped(FVector2D(Near, FMath::Max(Range, Near + 1.f)), FVector2D(1.f, 0.f), Far));
		}
	}
	if (Fade <= 0.004f)
	{
		if (bLog)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("step t=%.3f %s (out of range: %.0f cm from the focus)"), GetWorld()->GetTimeSeconds(), *GetDisplayName(), Far);
		}
		return;
	}
	const float Volume = Fade * FMath::Lerp(FootstepWalkVolume, FootstepRunVolume, Run) * (1.f - FMath::FRandRange(0.f, FootstepVolumeJitter));
	const float Pitch = FMath::Lerp(1.f, FootstepRunPitch, Run) * (1.f + FMath::FRandRange(-FootstepPitchJitter, FootstepPitchJitter));
	UGameplayStatics::PlaySoundAtLocation(this, Sound, At, Volume, Pitch);
	if (bLog)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("step t=%.3f %s (%s) clip %d vol %.2f pitch %.2f speed %.0f run %.2f at %.0f %.0f %.0f, %.0f cm from the focus (fade %.2f)"), GetWorld()->GetTimeSeconds(),
			StepSurfaceName(EVLStepSurface(Set)), *Material, Clip, Volume, Pitch, GetVelocity().Size2D(), Run, At.X, At.Y, At.Z, Far, Fade);
	}
}

void AVLKing::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	bRigPosedAtTick = false;
	if (GetWorld()->IsPaused())
	{
		// the pause menu is up: only its input
		if (Cast<APlayerController>(GetController()))
		{
			PollInput(DeltaSeconds);
		}
		return;
	}
	if (bDead)
	{
		if (Cast<APlayerController>(GetController()))
		{
			PollInput(DeltaSeconds);        // (the king in the overview, waiting to rise again)
		}
		TickDeath(DeltaSeconds);
		return;
	}
	PollInput(DeltaSeconds);
	UpdateMovementSleep();
	UpdateSafety(DeltaSeconds);
	// Being hurt holds the POSE for a moment, nothing else: the pose's clock stops while the game's runs on, and
	// afterwards runs a little fast until it has caught up.
	float AnimDt = DeltaSeconds;
	if (HitPauseLeft > 0.f)
	{
		const float Held = FMath::Min(HitPauseLeft, DeltaSeconds);
		HitPauseLeft -= Held;
		AnimLag += Held;
		AnimDt -= Held;
	}
	else if (AnimLag > 0.f)
	{
		const float Catch = FMath::Min(AnimLag, DeltaSeconds * HitCatchUp);
		AnimLag -= Catch;
		AnimDt += Catch;
	}
	Animate(DeltaSeconds, AnimDt);
	UpdateFlash(DeltaSeconds);
}
