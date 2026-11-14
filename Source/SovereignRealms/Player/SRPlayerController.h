// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "Common/SRTypes.h"
#include "SRPlayerController.generated.h"

class ASRUnit;
class ASRCameraPawn;
class USRBattleSubsystem;
class UInputAction;
class UInputMappingContext;
struct FInputActionValue;

/**
 * Mouse-and-keyboard RTS control: selection, orders, and feeding the camera.
 *
 * Input uses Enhanced Input. The actions and mapping context are built in code at
 * runtime (see BuildInput) so the project needs no input assets.
 *
 * Controls
 *   LMB click / shift-click / drag / double-click   select / add-toggle / box / all of type on screen
 *   RMB ground / enemy                               move in formation / attack that unit
 *   A then LMB                                       attack-move      (tap A; holding A pans when WASD panning is on)
 *   S                                                stop             (tap S; holding S pans)
 *   WASD / arrows / screen edge / MMB drag           pan              wheel: zoom
 *   Space / Home                                     centre on selection
 *   Ctrl|Cmd|Alt + 1..3 / 1..3                       set / recall control group (double-tap to centre)
 *   R                                                reset the battle
 */
UCLASS()
class SOVEREIGNREALMS_API ASRPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	ASRPlayerController();

	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	virtual void PlayerTick(float DeltaTime) override;

	// ---- Selection (also used by the sr.* debug commands) ----
	void SelectUnits(const TArray<ASRUnit*>& Units, bool bAdditive);
	void SelectAllPlayerUnits();
	void ClearSelection();
	const TArray<TWeakObjectPtr<ASRUnit>>& GetSelection() const { return Selection; }

	// ---- Orders to the current selection ----
	void IssueMove(const FVector& GroundPoint, bool bAttackMove);
	void IssueAttack(ASRUnit* Target);
	void IssueStop();

	void RecenterOnSelection();

	// ---- State the HUD draws ----
	bool IsBoxSelecting() const { return bBoxSelecting; }
	FVector2D GetBoxStart() const { return PressPos; }
	FVector2D GetBoxEnd() const { return DragPos; }
	bool IsAttackMoveArmed() const { return bAttackMoveArmed; }

	// ---- Cursor (real mouse, or a scripted position for automated input tests: sr.Cursor) ----
	bool GetCursorScreenPos(FVector2D& OutPixels) const;
	bool GetCursorRay(FVector& Origin, FVector& Dir) const;
	void SetCursorOverride(bool bEnabled, const FVector2D& Normalized) { bCursorOverride = bEnabled; CursorOverride = Normalized; }

private:
	void BuildInput();
	ASRCameraPawn* GetCameraPawn() const;
	ASRUnit* PickUnitUnderCursor() const;
	void GatherCommandable(TArray<ASRUnit*>& Out) const;
	void GatherUnitsInBox(const FVector2D& A, const FVector2D& B, TArray<ASRUnit*>& Out) const;
	bool IsOnScreen(const ASRUnit* Unit) const;
	bool IsShiftDown() const;
	bool IsGroupModifierDown() const;
	void PruneSelection();
	void UpdateHover();
	FVector2D ComputePanInput();
	void ArmAttackMove();

	// input handlers
	void OnSelectPressed();
	void OnSelectReleased();
	void OnCommandPressed();
	void OnDragPanPressed();
	void OnDragPanReleased();
	void OnZoom(const FInputActionValue& Value);
	void OnKeyAPressed();
	void OnKeyAReleased();
	void OnKeySPressed();
	void OnKeySReleased();
	void OnRecenter();
	void OnResetBattle();
	void OnGroupKey(int32 Index);
	void OnGroup1() { OnGroupKey(0); }
	void OnGroup2() { OnGroupKey(1); }
	void OnGroup3() { OnGroupKey(2); }

	UPROPERTY(Transient) TObjectPtr<UInputMappingContext> MappingContext;
	UPROPERTY(Transient) TObjectPtr<UInputAction> PanAction;      // arrows
	UPROPERTY(Transient) TObjectPtr<UInputAction> PanWDAction;    // W / D (A and S are tap-or-hold, handled separately)
	UPROPERTY(Transient) TObjectPtr<UInputAction> ZoomAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> SelectAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> CommandAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> DragPanAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> KeyAAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> KeySAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> RecenterAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> ResetAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> GroupActions[3];

	UPROPERTY(Transient) TObjectPtr<USRBattleSubsystem> Battle;

	TArray<TWeakObjectPtr<ASRUnit>> Selection;
	TArray<TWeakObjectPtr<ASRUnit>> ControlGroups[3];
	TWeakObjectPtr<ASRUnit> Hovered;
	TArray<TWeakObjectPtr<ASRUnit>> BoxPreview;

	// left mouse
	bool bSelectDown = false;
	bool bBoxSelecting = false;
	FVector2D PressPos = FVector2D::ZeroVector;
	FVector2D DragPos = FVector2D::ZeroVector;
	double LastClickTime = -10.0;
	ESRUnitType LastClickType = ESRUnitType::Shieldbearer;

	bool bAttackMoveArmed = false;

	bool bCursorOverride = false;
	FVector2D CursorOverride = FVector2D(0.5f, 0.5f);

	// A / S tap-or-hold
	bool bKeyADown = false, bKeyAPanned = false;
	bool bKeySDown = false, bKeySPanned = false;
	double KeyADownTime = 0.0, KeySDownTime = 0.0;

	int32 LastGroupRecalled = -1;
	double LastGroupRecallTime = -10.0;
};
