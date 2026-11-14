// Copyright Sovereign Realms.

#include "Player/SRPlayerController.h"
#include "Player/SRCameraPawn.h"
#include "Player/SRHUD.h"
#include "Units/SRUnit.h"
#include "Buildings/SRBuilding.h"
#include "Battle/SREconomySubsystem.h"
#include "SovereignRealms.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRFormation.h"
#include "Battle/SROrderMarker.h"
#include "Battle/SRGridSubsystem.h"
#include "Battle/SRPlatoonSubsystem.h"
#include "Buildings/SRPlacementPreview.h"
#include "Common/SRAudioSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Battle/SRGameFlowSubsystem.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"

ASRPlayerController::ASRPlayerController()
{
	bShowMouseCursor = true;
	bEnableClickEvents = false;
	bEnableMouseOverEvents = false;
	PrimaryActorTick.bCanEverTick = true;
}

void ASRPlayerController::BeginPlay()
{
	Super::BeginPlay();
	Battle = USRBattleSubsystem::Get(this);

	// Cursor stays visible and free; clicks go to the game.
	FInputModeGameAndUI Mode;
	Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	Mode.SetHideCursorDuringCapture(false);
	SetInputMode(Mode);

	if (const ULocalPlayer* LocalPlayer = GetLocalPlayer())
	{
		if (UEnhancedInputLocalPlayerSubsystem* Input = LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
		{
			BuildInput();
			Input->AddMappingContext(bMenuInput ? MenuContext : MappingContext, 0);
		}
	}
}

// -------------------------------------------------------------------- input

void ASRPlayerController::BuildInput()
{
	if (MappingContext) { return; }

	auto MakeAction = [this](const TCHAR* Name, EInputActionValueType Type)
	{
		UInputAction* Action = NewObject<UInputAction>(this, Name);
		Action->ValueType = Type;
		return Action;
	};

	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_SovereignRTS"));
	PanAction = MakeAction(TEXT("IA_Pan"), EInputActionValueType::Axis2D);
	PanWDAction = MakeAction(TEXT("IA_PanWD"), EInputActionValueType::Axis2D);
	ZoomAction = MakeAction(TEXT("IA_Zoom"), EInputActionValueType::Axis1D);
	SelectAction = MakeAction(TEXT("IA_Select"), EInputActionValueType::Boolean);
	CommandAction = MakeAction(TEXT("IA_Command"), EInputActionValueType::Boolean);
	DragPanAction = MakeAction(TEXT("IA_DragPan"), EInputActionValueType::Boolean);
	KeyAAction = MakeAction(TEXT("IA_KeyA"), EInputActionValueType::Boolean);
	KeySAction = MakeAction(TEXT("IA_KeyS"), EInputActionValueType::Boolean);
	RecenterAction = MakeAction(TEXT("IA_Recenter"), EInputActionValueType::Boolean);
	HelpAction = MakeAction(TEXT("IA_Help"), EInputActionValueType::Boolean);
	for (int32 i = 0; i < 6; ++i)
	{
		GroupActions[i] = MakeAction(*FString::Printf(TEXT("IA_Platoon%d"), i + 1), EInputActionValueType::Boolean);
	}
	BuildActions[0] = MakeAction(TEXT("IA_BuildFarm"), EInputActionValueType::Boolean);
	BuildActions[1] = MakeAction(TEXT("IA_BuildMine"), EInputActionValueType::Boolean);
	BuildActions[2] = MakeAction(TEXT("IA_BuildTower"), EInputActionValueType::Boolean);
	HoldAction = MakeAction(TEXT("IA_Hold"), EInputActionValueType::Boolean);
	FormationAction = MakeAction(TEXT("IA_Formation"), EInputActionValueType::Boolean);
	StanceAction = MakeAction(TEXT("IA_Stance"), EInputActionValueType::Boolean);
	CancelAction = MakeAction(TEXT("IA_Cancel"), EInputActionValueType::Boolean);
	DeleteAction = MakeAction(TEXT("IA_Delete"), EInputActionValueType::Boolean);
	RecruitActions[0] = MakeAction(TEXT("IA_RecruitShieldbearer"), EInputActionValueType::Boolean);
	RecruitActions[1] = MakeAction(TEXT("IA_RecruitArcher"), EInputActionValueType::Boolean);

	// A key gives +X. Swizzle moves it onto Y (up/down keys), Negate flips it (left/down keys).
	auto MapAxisKey = [this](UInputAction* Action, FKey Key, bool bVertical, bool bNegative)
	{
		FEnhancedActionKeyMapping& Mapping = MappingContext->MapKey(Action, Key);
		if (bVertical) { Mapping.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(MappingContext)); }
		if (bNegative) { Mapping.Modifiers.Add(NewObject<UInputModifierNegate>(MappingContext)); }
	};
	MapAxisKey(PanAction, EKeys::Up, true, false);
	MapAxisKey(PanAction, EKeys::Down, true, true);
	MapAxisKey(PanAction, EKeys::Right, false, false);
	MapAxisKey(PanAction, EKeys::Left, false, true);
	MapAxisKey(PanWDAction, EKeys::W, true, false);
	MapAxisKey(PanWDAction, EKeys::D, false, false);

	MappingContext->MapKey(ZoomAction, EKeys::MouseWheelAxis);
	MappingContext->MapKey(SelectAction, EKeys::LeftMouseButton);
	MappingContext->MapKey(CommandAction, EKeys::RightMouseButton);
	MappingContext->MapKey(DragPanAction, EKeys::MiddleMouseButton);
	MappingContext->MapKey(KeyAAction, EKeys::A);
	MappingContext->MapKey(KeySAction, EKeys::S);
	MappingContext->MapKey(RecenterAction, EKeys::SpaceBar);
	MappingContext->MapKey(RecenterAction, EKeys::Home);
	MappingContext->MapKey(HelpAction, EKeys::F1);

	// While a menu is up: the mouse, Esc and F1 only.
	MenuContext = NewObject<UInputMappingContext>(this, TEXT("IMC_SovereignMenu"));
	MenuContext->MapKey(SelectAction, EKeys::LeftMouseButton);
	MenuContext->MapKey(CommandAction, EKeys::RightMouseButton);
	MenuContext->MapKey(CancelAction, EKeys::Escape);
	MenuContext->MapKey(HelpAction, EKeys::F1);
	const FKey Digits[6] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six };
	for (int32 i = 0; i < 6; ++i) { MappingContext->MapKey(GroupActions[i], Digits[i]); }
	MappingContext->MapKey(BuildActions[0], EKeys::Z);
	MappingContext->MapKey(BuildActions[1], EKeys::X);
	MappingContext->MapKey(BuildActions[2], EKeys::C);
	MappingContext->MapKey(HoldAction, EKeys::H);
	MappingContext->MapKey(FormationAction, EKeys::F);
	MappingContext->MapKey(StanceAction, EKeys::G);
	MappingContext->MapKey(CancelAction, EKeys::Escape);
	MappingContext->MapKey(DeleteAction, EKeys::Delete);
	MappingContext->MapKey(DeleteAction, EKeys::BackSpace);
	MappingContext->MapKey(RecruitActions[0], EKeys::Q);
	MappingContext->MapKey(RecruitActions[1], EKeys::E);
}

void ASRPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	BuildInput();

	UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(InputComponent);
	if (!ensureMsgf(Input, TEXT("Sovereign Realms needs Enhanced Input as the default input component class.")))
	{
		return;
	}

	Input->BindActionValue(PanAction);
	Input->BindActionValue(PanWDAction);
	Input->BindAction(ZoomAction, ETriggerEvent::Triggered, this, &ASRPlayerController::OnZoom);
	Input->BindAction(SelectAction, ETriggerEvent::Started, this, &ASRPlayerController::OnSelectPressed);
	Input->BindAction(SelectAction, ETriggerEvent::Completed, this, &ASRPlayerController::OnSelectReleased);
	Input->BindAction(CommandAction, ETriggerEvent::Started, this, &ASRPlayerController::OnCommandPressed);
	Input->BindAction(DragPanAction, ETriggerEvent::Started, this, &ASRPlayerController::OnDragPanPressed);
	Input->BindAction(DragPanAction, ETriggerEvent::Completed, this, &ASRPlayerController::OnDragPanReleased);
	Input->BindAction(KeyAAction, ETriggerEvent::Started, this, &ASRPlayerController::OnKeyAPressed);
	Input->BindAction(KeyAAction, ETriggerEvent::Completed, this, &ASRPlayerController::OnKeyAReleased);
	Input->BindAction(KeySAction, ETriggerEvent::Started, this, &ASRPlayerController::OnKeySPressed);
	Input->BindAction(KeySAction, ETriggerEvent::Completed, this, &ASRPlayerController::OnKeySReleased);
	Input->BindAction(RecenterAction, ETriggerEvent::Started, this, &ASRPlayerController::OnRecenter);
	Input->BindAction(HelpAction, ETriggerEvent::Started, this, &ASRPlayerController::OnHelp);
	Input->BindAction(GroupActions[0], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup1);
	Input->BindAction(GroupActions[1], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup2);
	Input->BindAction(GroupActions[2], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup3);
	Input->BindAction(GroupActions[3], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup4);
	Input->BindAction(GroupActions[4], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup5);
	Input->BindAction(GroupActions[5], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup6);
	Input->BindAction(BuildActions[0], ETriggerEvent::Started, this, &ASRPlayerController::OnBuildFarm);
	Input->BindAction(BuildActions[1], ETriggerEvent::Started, this, &ASRPlayerController::OnBuildMine);
	Input->BindAction(BuildActions[2], ETriggerEvent::Started, this, &ASRPlayerController::OnBuildTower);
	Input->BindAction(HoldAction, ETriggerEvent::Started, this, &ASRPlayerController::OnHold);
	Input->BindAction(FormationAction, ETriggerEvent::Started, this, &ASRPlayerController::OnCycleFormation);
	Input->BindAction(StanceAction, ETriggerEvent::Started, this, &ASRPlayerController::OnCycleStance);
	Input->BindAction(CancelAction, ETriggerEvent::Started, this, &ASRPlayerController::OnCancel);
	Input->BindAction(DeleteAction, ETriggerEvent::Started, this, &ASRPlayerController::OnDeleteBuilding);
	Input->BindAction(RecruitActions[0], ETriggerEvent::Started, this, &ASRPlayerController::OnRecruitShieldbearer);
	Input->BindAction(RecruitActions[1], ETriggerEvent::Started, this, &ASRPlayerController::OnRecruitArcher);
}

void ASRPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	if (!Battle) { return; }

	PruneSelection();

	// Box select: becomes a drag once the mouse has travelled past the threshold.
	FVector2D Mouse;
	if (bSelectDown && GetCursorScreenPos(Mouse))
	{
		DragPos = Mouse;
		if (!bBoxSelecting && FVector2D::Distance(PressPos, DragPos) > USRFeelSettings::Get().DragThreshold)
		{
			bBoxSelecting = true;
		}
	}

	UpdateHover();
	if (bPlacing && !bMenuInput) { UpdatePlacement(); }

	if (ASRCameraPawn* Camera = GetCameraPawn())
	{
		Camera->SetPanInput(ComputePanInput());
	}

	CurrentMouseCursor = bAttackMoveArmed ? EMouseCursor::Crosshairs : (bPlacing ? EMouseCursor::Hand : EMouseCursor::Default);
}

FVector2D ASRPlayerController::ComputePanInput()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	FVector2D Pan = FVector2D::ZeroVector;

	if (const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this); Flow && Flow->IsModal())
	{
		// Main menu: a slow drift in a wide circle over the realm. Any other menu: the camera rests.
		if (Flow->GetState() != ESRGameState::MainMenu) { return Pan; }
		const float Angle = float(GetWorld()->GetRealTimeSeconds()) * 0.06f;
		return FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * 0.016f;
	}

	if (const UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(InputComponent))
	{
		Pan += Input->GetBoundActionValue(PanAction).Get<FVector2D>();
		if (F.bWASDPansCamera)
		{
			Pan += Input->GetBoundActionValue(PanWDAction).Get<FVector2D>();
		}
	}

	if (F.bWASDPansCamera)
	{
		// A and S are shared with Attack-move and Stop. With units selected, a quick tap is the command and a
		// hold is a pan; with nothing to command, or when already panning with another key, they pan instantly.
		TArray<ASRUnit*> Commandable;
		GatherCommandable(Commandable);
		const bool bInstant = Commandable.Num() == 0 || !Pan.IsNearlyZero();
		const double Now = GetWorld()->GetRealTimeSeconds();

		if (bKeyADown && (bKeyAPanned || bInstant || bKeySPanned || Now - KeyADownTime >= F.CommandKeyTapTime))
		{
			bKeyAPanned = true;
			Pan.X -= 1.f;
		}
		if (bKeySDown && (bKeySPanned || bInstant || bKeyAPanned || Now - KeySDownTime >= F.CommandKeyTapTime))
		{
			bKeySPanned = true;
			Pan.Y -= 1.f;
		}
	}

	// Screen-edge pan, proportional to how deep into the edge band the cursor is.
	FVector2D Mouse;
	int32 SizeX = 0, SizeY = 0;
	GetViewportSize(SizeX, SizeY);
	if (F.bEdgePan && SizeX > 0 && SizeY > 0 && GetCursorScreenPos(Mouse))
	{
		const float Margin = FMath::Max(F.EdgePanMargin, 1.f);
		if (Mouse.X >= 0.f && Mouse.Y >= 0.f && Mouse.X <= SizeX && Mouse.Y <= SizeY)
		{
			if (Mouse.X < Margin) { Pan.X -= 1.f - Mouse.X / Margin; }
			if (Mouse.X > SizeX - Margin) { Pan.X += 1.f - (SizeX - Mouse.X) / Margin; }
			if (Mouse.Y < Margin) { Pan.Y += 1.f - Mouse.Y / Margin; }
			if (Mouse.Y > SizeY - Margin) { Pan.Y -= 1.f - (SizeY - Mouse.Y) / Margin; }
		}
	}

	return Pan.ClampAxes(-1.f, 1.f);
}

void ASRPlayerController::OnZoom(const FInputActionValue& Value)
{
	if (ASRCameraPawn* Camera = GetCameraPawn())
	{
		// Clamp: trackpads and free-spinning wheels can report large bursts.
		const float Notches = FMath::Clamp(Value.Get<float>(), -3.f, 3.f);
		FVector Origin, Dir;
		if (GetCursorRay(Origin, Dir))
		{
			const FVector Ground = Battle->RayToGround(Origin, Dir);
			Camera->AddZoomInput(Notches, &Ground);
		}
		else
		{
			Camera->AddZoomInput(Notches, nullptr);
		}
	}
}

void ASRPlayerController::OnDragPanPressed()
{
	if (ASRCameraPawn* Camera = GetCameraPawn()) { Camera->BeginDragPan(); }
}

void ASRPlayerController::OnDragPanReleased()
{
	if (ASRCameraPawn* Camera = GetCameraPawn()) { Camera->EndDragPan(); }
}

void ASRPlayerController::OnKeyAPressed()
{
	bKeyADown = true;
	bKeyAPanned = false;
	KeyADownTime = GetWorld()->GetRealTimeSeconds();
	if (!USRFeelSettings::Get().bWASDPansCamera) { ArmAttackMove(); }
}

void ASRPlayerController::OnKeyAReleased()
{
	if (bKeyADown && !bKeyAPanned && USRFeelSettings::Get().bWASDPansCamera) { ArmAttackMove(); }
	bKeyADown = false;
}

void ASRPlayerController::OnKeySPressed()
{
	bKeySDown = true;
	bKeySPanned = false;
	KeySDownTime = GetWorld()->GetRealTimeSeconds();
	if (!USRFeelSettings::Get().bWASDPansCamera) { IssueStop(); }
}

void ASRPlayerController::OnKeySReleased()
{
	if (bKeySDown && !bKeySPanned && USRFeelSettings::Get().bWASDPansCamera) { IssueStop(); }
	bKeySDown = false;
}

void ASRPlayerController::ArmAttackMove()
{
	TArray<ASRUnit*> Commandable;
	GatherCommandable(Commandable);
	bAttackMoveArmed = Commandable.Num() > 0;
}

void ASRPlayerController::OnRecenter()
{
	RecenterOnSelection();
}

void ASRPlayerController::OnHelp()
{
	if (ASRHUD* HUD = Cast<ASRHUD>(GetHUD())) { HUD->ToggleLegend(); }
}

void ASRPlayerController::OnEscapeUnhandled()
{
	if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this)) { Flow->SetPaused(true); }
}

void ASRPlayerController::ResetForNewMatch()
{
	ClearSelection();
	SelectBuilding(nullptr);
	CancelPlacement();
	bAttackMoveArmed = false;
	bSelectDown = bBoxSelecting = false;
}

void ASRPlayerController::SetMenuInput(bool bMenu)
{
	if (bMenuInput == bMenu) { return; }
	bMenuInput = bMenu;
	// whatever was half done with the mouse or the tap-or-hold keys ends here
	bSelectDown = bBoxSelecting = false;
	bKeyADown = bKeySDown = false;
	if (ASRCameraPawn* Camera = GetCameraPawn()) { Camera->EndDragPan(); }
	const ULocalPlayer* LocalPlayer = GetLocalPlayer();
	UEnhancedInputLocalPlayerSubsystem* Input = LocalPlayer ? LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr;
	if (!Input || !MappingContext) { return; }
	Input->RemoveMappingContext(bMenu ? MappingContext : MenuContext);
	Input->AddMappingContext(bMenu ? MenuContext : MappingContext, 0);
}

// ---------------------------------------------------------- mouse: selection

void ASRPlayerController::OnSelectPressed()
{
	FVector2D Mouse;
	if (!GetCursorScreenPos(Mouse)) { return; }

	// The interface sits over the world: a press on a panel (or anywhere, while a menu is up) is for it alone.
	if (ASRHUD* HUD = Cast<ASRHUD>(GetHUD()); HUD && HUD->OnMousePress(Mouse, false)) { return; }

	if (bPlacing)
	{
		TryPlace();
		return;
	}

	if (bAttackMoveArmed)
	{
		// A, then click: attack that enemy, or attack-move to that spot.
		FVector Origin, Dir;
		if (GetCursorRay(Origin, Dir))
		{
			ASRUnit* Unit = Battle->PickUnit(Origin, Dir, USRFeelSettings::Get().PickPadding);
			if (Unit && Unit->GetTeam() == ESRTeam::Enemy) { IssueAttack(Unit); }
			else { IssueMove(Battle->RayToGround(Origin, Dir), true); }
		}
		if (!IsShiftDown()) { bAttackMoveArmed = false; }
		return;
	}

	bSelectDown = true;
	bBoxSelecting = false;
	PressPos = DragPos = Mouse;
}

void ASRPlayerController::OnSelectReleased()
{
	if (!bSelectDown) { return; }
	bSelectDown = false;

	const USRFeelSettings& F = USRFeelSettings::Get();
	const bool bShift = IsShiftDown();

	if (bBoxSelecting)
	{
		bBoxSelecting = false;
		TArray<ASRUnit*> InBox;
		GatherUnitsInBox(PressPos, DragPos, InBox);
		if (InBox.Num() > 0 || !bShift) { SelectUnits(InBox, bShift); }
		if (InBox.Num() == 0 && !bShift) { SelectBuilding(nullptr); } // an empty box deselects everything
		return;
	}

	ASRUnit* Clicked = PickUnitUnderCursor();
	const double Now = GetWorld()->GetRealTimeSeconds();

	if (Clicked && Clicked->GetTeam() == ESRTeam::Player)
	{
		const bool bDoubleClick = (Now - LastClickTime) < F.DoubleClickTime && LastClickType == Clicked->GetUnitType();
		LastClickTime = Now;
		LastClickType = Clicked->GetUnitType();

		if (bDoubleClick)
		{
			// Everyone of that troop type currently on screen.
			TArray<ASRUnit*> SameType;
			for (ASRUnit* Unit : Battle->GetUnits())
			{
				if (Unit && Unit->IsActive() && Unit->GetTeam() == ESRTeam::Player
					&& Unit->GetUnitType() == Clicked->GetUnitType() && IsOnScreen(Unit))
				{
					SameType.Add(Unit);
				}
			}
			SelectUnits(SameType, bShift);
			LastClickTime = -10.0; // a third click starts over
		}
		else if (bShift)
		{
			// Toggle membership.
			if (Clicked->IsSelected())
			{
				Clicked->SetSelected(false);
				Selection.Remove(Clicked);
			}
			else
			{
				SelectUnits({ Clicked }, true);
			}
		}
		else
		{
			SelectUnits({ Clicked }, false);
		}
	}
	else if (Clicked)
	{
		// Clicking an enemy just inspects it (ring + health bar).
		if (!bShift) { SelectUnits({ Clicked }, false); }
	}
	else if (!bShift)
	{
		// No troop under the cursor: a building, or empty ground (deselect).
		ASRBuilding* Building = PickBuildingUnderCursor();
		ClearSelection();
		SelectBuilding(Building);
	}
}

void ASRPlayerController::OnCommandPressed()
{
	FVector2D Mouse;
	if (ASRHUD* HUD = Cast<ASRHUD>(GetHUD()); HUD && GetCursorScreenPos(Mouse) && HUD->OnMousePress(Mouse, true)) { return; }

	if (bPlacing)
	{
		CancelPlacement(); // right-click drops the building you were about to place
		return;
	}
	if (bAttackMoveArmed)
	{
		bAttackMoveArmed = false; // right-click cancels a pending attack-move
		return;
	}

	FVector Origin, Dir;
	if (!GetCursorRay(Origin, Dir)) { return; }

	// With the player's castle selected, right-click plants its rally point.
	if (ASRBuilding* Castle = SelectedBuilding.Get(); Castle && Castle->IsCastle() && Castle->Team == ESRTeam::Player)
	{
		SetCastleRally(Battle->RayToGround(Origin, Dir));
		return;
	}

	ASRUnit* Unit = Battle->PickUnit(Origin, Dir, USRFeelSettings::Get().PickPadding);
	if (Unit && Unit->GetTeam() == ESRTeam::Enemy)
	{
		IssueAttack(Unit);
		return;
	}
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (ASRBuilding* B = Eco ? Eco->PickBuilding(Origin, Dir) : nullptr; B && B->Team == ESRTeam::Enemy && B->IsAlive())
	{
		IssueAttackBuilding(B);
		return;
	}
	IssueMove(Battle->RayToGround(Origin, Dir), false);
}

// ---------------------------------------------------------------- buildings

void ASRPlayerController::SelectBuilding(ASRBuilding* Building)
{
	if (SelectedBuilding.Get() == Building) { return; }
	if (SelectedBuilding.IsValid()) { SelectedBuilding->SetSelected(false); }
	SelectedBuilding = Building;
	if (Building)
	{
		ClearSelection();
		bAttackMoveArmed = false;
		Building->SetSelected(true);
	}
}

ASRBuilding* ASRPlayerController::PickBuildingUnderCursor() const
{
	FVector Origin, Dir;
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	return (Economy && GetCursorRay(Origin, Dir)) ? Economy->PickBuilding(Origin, Dir) : nullptr;
}

bool ASRPlayerController::RecruitAtCastle(ESRUnitType Type)
{
	ASRBuilding* Castle = SelectedBuilding.Get();
	if (!Castle || !Castle->IsCastle() || Castle->Team != ESRTeam::Player)
	{
		const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
		Castle = Economy ? Economy->FindBuilding(ESRBuildingType::Castle, ESRTeam::Player) : nullptr;
	}
	LastRecruitButton = Type == ESRUnitType::Archer ? 1 : 0;
	LastRecruitTime = GetWorld()->GetRealTimeSeconds();
	bLastRecruitAccepted = Castle && Castle->QueueRecruit(Type);
	return bLastRecruitAccepted;
}

void ASRPlayerController::RecruitHotkey(ESRUnitType Type)
{
	// The hotkeys and buttons belong to the castle's panel: they do nothing unless it is selected.
	const ASRBuilding* Castle = SelectedBuilding.Get();
	if (Castle && Castle->IsCastle() && Castle->Team == ESRTeam::Player) { RecruitAtCastle(Type); }
}

void ASRPlayerController::SetCastleRally(const FVector& GroundPoint)
{
	ASRBuilding* Castle = SelectedBuilding.Get();
	if (!Castle || !Castle->IsCastle() || Castle->Team != ESRTeam::Player)
	{
		const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
		Castle = Economy ? Economy->FindBuilding(ESRBuildingType::Castle, ESRTeam::Player) : nullptr;
	}
	if (!Castle) { return; }
	Castle->SetRallyPoint(FVector2D(GroundPoint.X, GroundPoint.Y));
	const FVector2D Rally = Castle->GetRallyPoint();
	ASROrderMarker::SpawnMarker(GetWorld(), FVector(Rally.X, Rally.Y, GroundPoint.Z), USRFeelSettings::Get().MoveMarkerColor);
}

// ------------------------------------------------------------------- orders

void ASRPlayerController::IssueMove(const FVector& GroundPoint, bool bAttackMove)
{
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	if (Units.Num() == 0) { return; }

	// A platoon moves in its own formation; any other selection forms a battle line.
	ESRFormationShape Shape = ESRFormationShape::Line;
	if (const USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this))
	{
		if (const FSRPlatoon* P = Platoons->Find(Platoons->PlatoonOf(Units))) { Shape = P->Formation; }
	}
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FVector2D Dest(GroundPoint.X, GroundPoint.Y);
	Battle->CommandMove(Units, Dest, bAttackMove, Shape, true);
	ASROrderMarker::SpawnMarker(GetWorld(), GroundPoint, bAttackMove ? F.AttackMarkerColor : F.MoveMarkerColor);
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(bAttackMove ? ESRSound::AttackOrder : ESRSound::Acknowledge); }
}

void ASRPlayerController::IssueAttack(ASRUnit* Target)
{
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	if (Units.Num() == 0 || !Target) { return; }
	Battle->CommandAttack(Units, Target);
	Target->FlashTargeted();
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::AttackOrder); }
}

void ASRPlayerController::IssueAttackBuilding(ASRBuilding* Target)
{
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	if (Units.Num() == 0 || !Target) { return; }
	Battle->CommandAttackBuilding(Units, Target);
	const FVector2D At = Target->GetFootprintCentre();
	ASROrderMarker::SpawnMarker(GetWorld(), FVector(At, Target->GetActorLocation().Z), USRFeelSettings::Get().AttackMarkerColor);
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::AttackOrder); }
}

void ASRPlayerController::IssueHold()
{
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	for (ASRUnit* Unit : Units) { Unit->OrderHold(); Unit->Acknowledge(FMath::FRandRange(0.f, USRFeelSettings::Get().AckMaxDelay)); }
	bAttackMoveArmed = false;
	if (Units.Num() > 0) { if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::Acknowledge); } }
}

void ASRPlayerController::IssueStop()
{
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	for (ASRUnit* Unit : Units) { Unit->OrderStop(); }
	bAttackMoveArmed = false;
}

// ---------------------------------------------------------------- selection

void ASRPlayerController::SelectUnits(const TArray<ASRUnit*>& Units, bool bAdditive)
{
	if (!bAdditive) { ClearSelection(); }
	if (Units.Num() > 0) { SelectBuilding(nullptr); }
	for (ASRUnit* Unit : Units)
	{
		if (Unit && Unit->IsActive() && !Unit->IsSelected())
		{
			Unit->SetSelected(true);
			Selection.Add(Unit);
		}
	}
	// Never mix an inspected enemy into a player selection.
	if (Selection.Num() > 1)
	{
		for (int32 i = Selection.Num() - 1; i >= 0; --i)
		{
			if (Selection[i].IsValid() && Selection[i]->GetTeam() == ESRTeam::Enemy)
			{
				Selection[i]->SetSelected(false);
				Selection.RemoveAt(i);
			}
		}
	}
}

void ASRPlayerController::SelectAllPlayerUnits()
{
	TArray<ASRUnit*> All;
	for (ASRUnit* Unit : Battle->GetUnits())
	{
		if (Unit && Unit->IsActive() && Unit->GetTeam() == ESRTeam::Player) { All.Add(Unit); }
	}
	SelectUnits(All, false);
}

void ASRPlayerController::ClearSelection()
{
	for (const TWeakObjectPtr<ASRUnit>& Unit : Selection)
	{
		if (Unit.IsValid()) { Unit->SetSelected(false); }
	}
	Selection.Reset();
}

void ASRPlayerController::PruneSelection()
{
	Selection.RemoveAll([](const TWeakObjectPtr<ASRUnit>& Unit) { return !Unit.IsValid() || !Unit->IsAlive(); });
}

void ASRPlayerController::UpdateHover()
{
	// Clear last frame's highlights.
	if (Hovered.IsValid()) { Hovered->SetHovered(false); }
	for (const TWeakObjectPtr<ASRUnit>& Unit : BoxPreview)
	{
		if (Unit.IsValid()) { Unit->SetHovered(false); }
	}
	BoxPreview.Reset();
	Hovered = nullptr;
	if (HoveredBuilding.IsValid()) { HoveredBuilding->SetHovered(false); }
	HoveredBuilding = nullptr;

	// Nothing in the world is under the cursor while it is on the interface.
	FVector2D Cursor;
	if (const ASRHUD* HUD = Cast<ASRHUD>(GetHUD()); HUD && !bBoxSelecting && GetCursorScreenPos(Cursor) && HUD->IsOverUI(Cursor)) { return; }

	if (bBoxSelecting)
	{
		// Live preview of what the box will grab.
		TArray<ASRUnit*> InBox;
		GatherUnitsInBox(PressPos, DragPos, InBox);
		for (ASRUnit* Unit : InBox)
		{
			Unit->SetHovered(true);
			BoxPreview.Add(Unit);
		}
		return;
	}

	if (ASRUnit* Unit = PickUnitUnderCursor())
	{
		Unit->SetHovered(true);
		Hovered = Unit;
	}
	else if (ASRBuilding* Building = PickBuildingUnderCursor())
	{
		Building->SetHovered(true);
		HoveredBuilding = Building;
	}
}

void ASRPlayerController::GatherCommandable(TArray<ASRUnit*>& Out) const
{
	for (const TWeakObjectPtr<ASRUnit>& Unit : Selection)
	{
		if (Unit.IsValid() && Unit->IsActive() && Unit->GetTeam() == ESRTeam::Player) { Out.Add(Unit.Get()); }
	}
}

void ASRPlayerController::GatherUnitsInBox(const FVector2D& A, const FVector2D& B, TArray<ASRUnit*>& Out) const
{
	const FVector2D Min(FMath::Min(A.X, B.X) - 6.f, FMath::Min(A.Y, B.Y) - 6.f);
	const FVector2D Max(FMath::Max(A.X, B.X) + 6.f, FMath::Max(A.Y, B.Y) + 6.f);
	for (ASRUnit* Unit : Battle->GetUnits())
	{
		if (!Unit || !Unit->IsActive() || Unit->GetTeam() != ESRTeam::Player) { continue; }
		// Test feet and chest so a unit is caught whether the box clips its base or its body.
		const FVector Points[] = { Unit->GetSimPos(), Unit->GetAimPoint() };
		for (const FVector& Point : Points)
		{
			FVector2D Screen;
			if (ProjectWorldLocationToScreen(Point, Screen) && Screen.X >= Min.X && Screen.X <= Max.X && Screen.Y >= Min.Y && Screen.Y <= Max.Y)
			{
				Out.Add(Unit);
				break;
			}
		}
	}
}

bool ASRPlayerController::IsOnScreen(const ASRUnit* Unit) const
{
	FVector2D Screen;
	int32 SizeX = 0, SizeY = 0;
	GetViewportSize(SizeX, SizeY);
	return ProjectWorldLocationToScreen(Unit->GetAimPoint(), Screen)
		&& Screen.X >= 0.f && Screen.Y >= 0.f && Screen.X <= SizeX && Screen.Y <= SizeY;
}

void ASRPlayerController::RecenterOnSelection()
{
	ASRCameraPawn* Camera = GetCameraPawn();
	if (!Camera) { return; }

	FVector2D Sum = FVector2D::ZeroVector;
	int32 Count = 0;
	for (const TWeakObjectPtr<ASRUnit>& Unit : Selection)
	{
		if (Unit.IsValid() && Unit->IsAlive()) { Sum += Unit->GetPos2D(); ++Count; }
	}
	// Nothing selected: go to the army.
	Camera->FocusOn(Count > 0 ? Sum / Count : Battle->TeamCentroid(ESRTeam::Player), false);
}

// ------------------------------------------------------------------ helpers

ASRCameraPawn* ASRPlayerController::GetCameraPawn() const
{
	return Cast<ASRCameraPawn>(GetPawn());
}

bool ASRPlayerController::GetCursorScreenPos(FVector2D& OutPixels) const
{
	if (bCursorOverride)
	{
		int32 SizeX = 0, SizeY = 0;
		GetViewportSize(SizeX, SizeY);
		OutPixels = FVector2D(CursorOverride.X * SizeX, CursorOverride.Y * SizeY);
		return SizeX > 0 && SizeY > 0;
	}
	float X = 0.f, Y = 0.f;
	if (!GetMousePosition(X, Y)) { return false; }
	OutPixels = FVector2D(X, Y);
	return true;
}

bool ASRPlayerController::GetCursorRay(FVector& Origin, FVector& Dir) const
{
	FVector2D Screen;
	return GetCursorScreenPos(Screen) && DeprojectScreenPositionToWorld(Screen.X, Screen.Y, Origin, Dir);
}

ASRUnit* ASRPlayerController::PickUnitUnderCursor() const
{
	FVector Origin, Dir;
	return GetCursorRay(Origin, Dir) ? Battle->PickUnit(Origin, Dir, USRFeelSettings::Get().PickPadding) : nullptr;
}

bool ASRPlayerController::IsShiftDown() const
{
	return IsInputKeyDown(EKeys::LeftShift) || IsInputKeyDown(EKeys::RightShift);
}

bool ASRPlayerController::IsGroupModifierDown() const
{
	// Ctrl+digit is often taken by macOS (Mission Control), so Cmd and Alt work too.
	return IsInputKeyDown(EKeys::LeftControl) || IsInputKeyDown(EKeys::RightControl)
		|| IsInputKeyDown(EKeys::LeftCommand) || IsInputKeyDown(EKeys::RightCommand)
		|| IsInputKeyDown(EKeys::LeftAlt) || IsInputKeyDown(EKeys::RightAlt);
}


// ----------------------------------------------------------------- platoons

int32 ASRPlayerController::GetSelectedPlatoon() const
{
	TArray<ASRUnit*> Units;
	for (const TWeakObjectPtr<ASRUnit>& U : Selection) { if (U.IsValid()) { Units.Add(U.Get()); } }
	const USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this);
	return Platoons ? Platoons->PlatoonOf(Units) : INDEX_NONE;
}

void ASRPlayerController::PlatoonKey(int32 Index)
{
	USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this);
	if (!Platoons || Index >= Platoons->Num()) { return; }
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	if (IsGroupModifierDown())
	{
		if (Units.Num() > 0)
		{
			Platoons->Assign(Index, Units);
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::UIClick); }
		}
		return;
	}
	if (IsShiftDown() && Units.Num() > 0)
	{
		Platoons->Add(Index, Units);
		return;
	}
	const double Now = GetWorld()->GetRealTimeSeconds();
	const bool bDouble = LastGroupRecalled == Index && Now - LastGroupRecallTime < 0.4;
	LastGroupRecalled = Index;
	LastGroupRecallTime = Now;
	SelectPlatoon(Index, bDouble);
}

void ASRPlayerController::SelectPlatoon(int32 Index, bool bCentre)
{
	const USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this);
	if (!Platoons) { return; }
	TArray<ASRUnit*> Members;
	Platoons->GetMembers(Index, Members);
	if (Members.Num() == 0) { return; }
	SelectUnits(Members, false);
	if (bCentre) { RecenterOnSelection(); }
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::Select); }
}

void ASRPlayerController::OnCycleFormation()
{
	if (USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this))
	{
		const int32 P = GetSelectedPlatoon();
		if (P != INDEX_NONE) { Platoons->CycleFormation(P); if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::UIClick); } }
	}
}

void ASRPlayerController::OnCycleStance()
{
	USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this);
	const int32 P = GetSelectedPlatoon();
	if (Platoons && P != INDEX_NONE)
	{
		Platoons->CycleStance(P);
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::UIClick); }
		return;
	}
	// Not a platoon: cycle the stance of the selected troops themselves.
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	if (Units.Num() == 0) { return; }
	const ESRStance Next = ESRStance((uint8(Units[0]->GetStance()) + 1) % 3);
	for (ASRUnit* U : Units) { U->SetStance(Next); if (Next == ESRStance::HoldGround && !U->IsEngaged()) { U->OrderHold(); } }
}

// ----------------------------------------------------------------- building placement

void ASRPlayerController::BeginPlacement(ESRBuildingType Type)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!F.BuildingStatsFor(Type).bPlayerBuildable) { return; }
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (Eco && !Eco->CanAfford(ESRTeam::Player, F.BuildingStatsFor(Type).Cost))
	{
		// Say so now rather than after the player has picked a spot.
		const_cast<USREconomySubsystem*>(Eco)->TrySpend(ESRTeam::Player, F.BuildingStatsFor(Type).Cost);
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::UIError); }
		return;
	}
	bPlacing = true;
	PlacingType = Type;
	bAttackMoveArmed = false;
	if (!Preview)
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Preview = GetWorld()->SpawnActor<ASRPlacementPreview>(FVector::ZeroVector, FRotator::ZeroRotator, Params);
	}
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::UIClick); }
	UpdatePlacement();
}

void ASRPlayerController::CancelPlacement()
{
	bPlacing = false;
	PlacementReason = FText::GetEmpty();
	if (Preview) { Preview->Hide(); }
}

void ASRPlayerController::UpdatePlacement()
{
	FVector Origin, Dir;
	const USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (!Grid || !GetCursorRay(Origin, Dir)) { return; }
	const FVector Ground = Battle->RayToGround(Origin, Dir);
	const FSRPlacement P = Grid->CheckPlacement(PlacingType, ESRTeam::Player, FVector2D(Ground));
	bPlacementValid = P.bValid;
	PlacementReason = P.Reason;
	if (Preview) { Preview->Show(PlacingType, P); }
}

void ASRPlayerController::TryPlace()
{
	FVector Origin, Dir;
	USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Eco || !GetCursorRay(Origin, Dir)) { return; }
	const FVector Ground = Battle->RayToGround(Origin, Dir);
	FText Why;
	if (Eco->PlaceBuilding(PlacingType, ESRTeam::Player, FVector2D(Ground), &Why))
	{
		const USRFeelSettings& F = USRFeelSettings::Get();
		// Shift keeps the building in hand for another (if there is gold for it).
		if (!IsShiftDown() || !Eco->CanAfford(ESRTeam::Player, F.BuildingStatsFor(PlacingType).Cost)) { CancelPlacement(); }
	}
	else
	{
		PlacementReason = Why;
		Eco->PushAlert(ESRAlertKind::Info, Why);
		if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(ESRSound::UIError); }
	}
}

void ASRPlayerController::OnCancel()
{
	// An open overlay or menu screen closes first.
	if (ASRHUD* HUD = Cast<ASRHUD>(GetHUD()); HUD && HUD->OnEscape()) { return; }
	if (bPlacing) { CancelPlacement(); return; }
	if (bAttackMoveArmed) { bAttackMoveArmed = false; return; }
	if (Selection.Num() > 0 || SelectedBuilding.IsValid()) { ClearSelection(); SelectBuilding(nullptr); return; }
	OnEscapeUnhandled();
}

void ASRPlayerController::OnDeleteBuilding()
{
	if (ASRBuilding* B = SelectedBuilding.Get(); B && B->Team == ESRTeam::Player && B->IsUnderConstruction())
	{
		SelectBuilding(nullptr);
		B->CancelConstruction();
	}
}
