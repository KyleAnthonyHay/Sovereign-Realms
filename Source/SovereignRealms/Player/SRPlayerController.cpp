// Copyright Sovereign Realms.

#include "Player/SRPlayerController.h"
#include "Player/SRCameraPawn.h"
#include "Units/SRUnit.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRFormation.h"
#include "Battle/SROrderMarker.h"
#include "Common/SRFeelSettings.h"
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
			Input->AddMappingContext(MappingContext, 0);
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
	ResetAction = MakeAction(TEXT("IA_ResetBattle"), EInputActionValueType::Boolean);
	for (int32 i = 0; i < 3; ++i)
	{
		GroupActions[i] = MakeAction(*FString::Printf(TEXT("IA_Group%d"), i + 1), EInputActionValueType::Boolean);
	}

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
	MappingContext->MapKey(ResetAction, EKeys::R);
	MappingContext->MapKey(GroupActions[0], EKeys::One);
	MappingContext->MapKey(GroupActions[1], EKeys::Two);
	MappingContext->MapKey(GroupActions[2], EKeys::Three);
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
	Input->BindAction(ResetAction, ETriggerEvent::Started, this, &ASRPlayerController::OnResetBattle);
	Input->BindAction(GroupActions[0], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup1);
	Input->BindAction(GroupActions[1], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup2);
	Input->BindAction(GroupActions[2], ETriggerEvent::Started, this, &ASRPlayerController::OnGroup3);
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

	if (ASRCameraPawn* Camera = GetCameraPawn())
	{
		Camera->SetPanInput(ComputePanInput());
	}

	CurrentMouseCursor = bAttackMoveArmed ? EMouseCursor::Crosshairs : EMouseCursor::Default;
}

FVector2D ASRPlayerController::ComputePanInput()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	FVector2D Pan = FVector2D::ZeroVector;

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

void ASRPlayerController::OnResetBattle()
{
	ClearSelection();
	bAttackMoveArmed = false;
	Battle->ResetBattle();
	if (ASRCameraPawn* Camera = GetCameraPawn())
	{
		Camera->FocusOn(USRFeelSettings::Get().PlayerStart, false);
	}
}

void ASRPlayerController::OnGroupKey(int32 Index)
{
	if (IsGroupModifierDown())
	{
		ControlGroups[Index] = Selection;
		return;
	}

	TArray<ASRUnit*> Units;
	for (const TWeakObjectPtr<ASRUnit>& Unit : ControlGroups[Index])
	{
		if (Unit.IsValid() && Unit->IsActive()) { Units.Add(Unit.Get()); }
	}
	if (Units.Num() == 0) { return; }
	SelectUnits(Units, false);

	// Double-tap a group number to jump the camera to it.
	const double Now = GetWorld()->GetRealTimeSeconds();
	if (LastGroupRecalled == Index && Now - LastGroupRecallTime < 0.4) { RecenterOnSelection(); }
	LastGroupRecalled = Index;
	LastGroupRecallTime = Now;
}

// ---------------------------------------------------------- mouse: selection

void ASRPlayerController::OnSelectPressed()
{
	FVector2D Mouse;
	if (!GetCursorScreenPos(Mouse)) { return; }

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
		ClearSelection();
	}
}

void ASRPlayerController::OnCommandPressed()
{
	if (bAttackMoveArmed)
	{
		bAttackMoveArmed = false; // right-click cancels a pending attack-move
		return;
	}

	FVector Origin, Dir;
	if (!GetCursorRay(Origin, Dir)) { return; }

	ASRUnit* Unit = Battle->PickUnit(Origin, Dir, USRFeelSettings::Get().PickPadding);
	if (Unit && Unit->GetTeam() == ESRTeam::Enemy)
	{
		IssueAttack(Unit);
	}
	else
	{
		IssueMove(Battle->RayToGround(Origin, Dir), false);
	}
}

// ------------------------------------------------------------------- orders

void ASRPlayerController::IssueMove(const FVector& GroundPoint, bool bAttackMove)
{
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	if (Units.Num() == 0) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	FVector2D Dest(GroundPoint.X, GroundPoint.Y);
	Dest.X = FMath::Clamp(Dest.X, -F.MapHalfExtent.X, F.MapHalfExtent.X);
	Dest.Y = FMath::Clamp(Dest.Y, -F.MapHalfExtent.Y, F.MapHalfExtent.Y);

	TArray<FVector2D> Slots;
	SRFormation::ComputeSlots(Units, Dest, Slots);

	for (int32 i = 0; i < Units.Num(); ++i)
	{
		if (bAttackMove) { Units[i]->OrderAttackMove(Slots[i]); }
		else { Units[i]->OrderMove(Slots[i]); }
		Units[i]->Acknowledge(FMath::FRandRange(0.f, F.AckMaxDelay));
	}

	ASROrderMarker::SpawnMarker(GetWorld(), FVector(Dest.X, Dest.Y, GroundPoint.Z), bAttackMove ? F.AttackMarkerColor : F.MoveMarkerColor);
}

void ASRPlayerController::IssueAttack(ASRUnit* Target)
{
	TArray<ASRUnit*> Units;
	GatherCommandable(Units);
	if (Units.Num() == 0 || !Target) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	for (ASRUnit* Unit : Units)
	{
		Unit->OrderAttack(Target);
		Unit->Acknowledge(FMath::FRandRange(0.f, F.AckMaxDelay));
	}
	Target->FlashTargeted();
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
