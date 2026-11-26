// A unit in a multiplayer match (VLNet.h): what of it replicates, and how the joining player's game shows its copy.

#include "VLKing.h"
#include "SovereignRealms.h"
#include "VLArcherCombat.h"
#include "VLBattle.h"
#include "VLCommand.h"
#include "VLConstruction.h"
#include "VLNet.h"
#include "VLPlayerController.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Net/UnrealNetwork.h"

void AVLKing::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AVLKing, Team);
	DOREPLIFETIME_CONDITION(AVLKing, UnitKind, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AVLKing, DisplayName, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AVLKing, bTowerGuard, COND_InitialOnly);
	DOREPLIFETIME(AVLKing, Stance);
	DOREPLIFETIME(AVLKing, Health);
	DOREPLIFETIME(AVLKing, bDead);
	DOREPLIFETIME(AVLKing, NetSwing);
	DOREPLIFETIME(AVLKing, NetBow);
	DOREPLIFETIME(AVLKing, NetBowTarget);
	DOREPLIFETIME(AVLKing, NetBowAim);
	DOREPLIFETIME(AVLKing, NetFlags);
	DOREPLIFETIME(AVLKing, NetGarrison);
	// Hidden is each game's own business: the fog of war hides the OTHER side's units from this game's player
	// (UVLFog::SetHiddenByFog), which must not hide them in the game of the player who owns them.
	DISABLE_REPLICATED_PRIVATE_PROPERTY(AActor, bHidden);
}

void AVLKing::PreReplication(IRepChangedPropertyTracker& ChangedPropertyTracker)
{
	Super::PreReplication(ChangedPropertyTracker);
	// the host: what the joining game shows of this unit, from how it stands now
	uint8 Flags = 0;
	Flags |= bAutoWalk ? 1 : 0;
	Flags |= (bAutoWalk && bAutoRun) ? 2 : 0;
	Flags |= bArmed ? 4 : 0;
	Flags |= bHoldOrder ? 8 : 0;
	Flags |= UVLBuilderWork::IsAtWork(this) ? 16 : 0;
	NetFlags = Flags;
	int32 Tower = 0;
	if (const AActor* In = GarrisonIn.Get())
	{
		if (const UVLBattle* Battle = UVLBattle::Get(this))
		{
			Tower = Battle->NetIdOf(In);
		}
	}
	NetGarrison = Tower;
	if (BowCombat)
	{
		BowCombat->NetFill(this);
	}
}

bool AVLKing::IsRemotelyPlayed() const
{
	const APlayerController* PC = Cast<APlayerController>(GetController());
	return PC && HasAuthority() && !PC->IsLocalController();
}

void AVLKing::PawnClientRestart()
{
	Super::PawnClientRestart();
	// the joining player's game: this is the unit its player plays (BeginPlay's set-up for the player's unit, which
	// had no controller yet when this copy began play)
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC || !PC->IsLocalController())
	{
		return;
	}
	EnsureCameraRig();
	Camera->SetFieldOfView(CameraFOV);
	PC->SetControlRotation(FRotator(HeroPitch(Zoom), CamYaw, 0.f));
	FInputModeGameAndUI Mode;
	Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	Mode.SetHideCursorDuringCapture(false);
	PC->SetInputMode(Mode);
	PC->bShowMouseCursor = true;
	if (PC->PlayerCameraManager)
	{
		PC->PlayerCameraManager->ViewPitchMin = -80.f;
		PC->PlayerCameraManager->ViewPitchMax = 10.f;
	}
	bCursorModeSet = false;
	UpdateOverviewCamera(0.f, true);
	RefreshSilhouette();
	WakeRigPosers();
	if (IsNetCopy())
	{
		bNetHeroSent = true;        // (the host starts it in the hero view, as this game does)
		NetPaceSent = -1.f;
		SetHeroMode(bHeroMode && !bDead);
		if (AVLPlayerController* Mine = Cast<AVLPlayerController>(PC); Mine && !Mine->bNetReady)
		{
			Mine->bNetReady = true;
			Mine->ServerReady();    // the level is up and the unit is in hand: the host may start the match
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("multiplayer: playing %s (team %d)"), *DisplayName, Team);
	}
}

void AVLKing::NetFinishOrder(bool bArrived, bool bStopped)
{
	// the other machine says the walk is over: nothing is sent back
	const TGuardValue<bool> Quiet(bNetQuiet, true);
	if (bStopped)
	{
		StopOrder();
	}
	else if (HasAuthority())
	{
		FinishOrder(bArrived);      // (the host: what follows the order, the next leg of its pathway)
	}
	else
	{
		StopOrder();
	}
}

void AVLKing::OnRep_NetSwing()
{
	if (NetSwing == NetSwingSeen)
	{
		return;
	}
	NetSwingSeen = NetSwing;
	if (Cast<APlayerController>(GetController()) && bHeroMode)
	{
		return;         // (this game's own player swung it: shown already, the host's echo is not shown again)
	}
	bArmed = true;
	bAttackQueued = false;
	Draw = 1.f;
	StartSwing(NetSwing & 3);
}

void AVLKing::OnRep_NetFlags()
{
	const bool bMineInHand = Cast<APlayerController>(GetController()) && bHeroMode;
	if (!bMineInHand)
	{
		bArmed = (NetFlags & 4) != 0;
	}
	bHoldOrder = (NetFlags & 8) != 0;
}

void AVLKing::OnRep_NetBow()
{
	if (UVLArcherCombat* Bow = UVLArcherCombat::For(this, false))
	{
		Bow->SetComponentTickEnabled(true);     // (its copy of the shot follows: UVLArcherCombat::NetMirror)
	}
}

void AVLKing::OnRep_NetGarrison()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	GarrisonIn = (Battle && NetGarrison != 0) ? Battle->NetBuilding(NetGarrison) : nullptr;
}

void AVLKing::OnRep_Team()
{
	RefreshSilhouette();
}

void AVLKing::NetEase(float Dt, FVector& OutShift, FQuat& OutTurn)
{
	OutShift = FVector::ZeroVector;
	OutTurn = FQuat::Identity;
	if (Cast<APlayerController>(GetController()))
	{
		return;         // (this game's own unit: predicted, it is where it is)
	}
	UCharacterMovementComponent* Move = GetCharacterMovement();
	// the capsule is put where each update says; the movement component keeps the offset the engine would give a
	// skeletal mesh to hide that jump (network smoothing). The voxel figure is not that mesh, so it is applied here.
	if (Move && Move->HasPredictionData_Client())
	{
		if (const FNetworkPredictionData_Client_Character* Client = Move->GetPredictionData_Client_Character())
		{
			OutShift = GetActorQuat().UnrotateVector(Client->MeshTranslationOffset);
		}
	}
	// the turn: the host's yaw arrives in steps, the figure follows it smoothly
	const float Yaw = GetActorRotation().Yaw;
	if (!bNetYawSet)
	{
		bNetYawSet = true;
		NetYawShown = Yaw;
	}
	const float Off = FMath::FindDeltaAngleDegrees(NetYawShown, Yaw);
	const float Step = FMath::Clamp(Off, -620.f * Dt, 620.f * Dt);
	NetYawShown = FRotator::NormalizeAxis(NetYawShown + (FMath::Abs(Off) > 120.f ? Off : Step));
	OutTurn = FQuat(FVector::UpVector, FMath::DegreesToRadians(FMath::FindDeltaAngleDegrees(Yaw, NetYawShown)));
}
