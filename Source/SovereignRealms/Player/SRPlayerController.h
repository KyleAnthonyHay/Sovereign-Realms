// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "Common/SRTypes.h"
#include "SRPlayerController.generated.h"

class ASRUnit;
class ASRBuilding;
class ASRCameraPawn;
class ASRPlacementPreview;
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
 *   Ctrl|Cmd|Alt + 1..6 / 1..6 / Shift + 1..6        make / select (double-tap: centre) / add to platoon N
 *   F / G                                            formation (re-forms on the spot) / stance of the selection
 *   H                                                hold ground (stand fast, fight only what is in reach)
 *   P then LMB                                       patrol between here and there (attack-moving), until re-ordered
 *   B                                                the build menu (tabs Economy / Military / Defence); while it is
 *                                                    open 1..n pick a building, Tab changes tab. LMB places, Shift
 *                                                    keeps placing, RMB or Esc cancels
 *   Delete                                           pull down the selected building while it is still being built;
 *                                                    with a platoon selected, disband the platoon (troops stay)
 *   Esc                                              cancel placement / attack-move / the build menu, clear the
 *                                                    selection, then pause
 *   F1                                               the controls overlay
 *   LMB on a building                                select it (info panel; barracks and range show recruit commands)
 *   Q / E                                            recruit a Shieldbearer (at a barracks) / an Archer (at a range):
 *                                                    the selected one, or the one with the shortest queue
 *   RMB, barracks or range selected                  set where its recruits muster (its rally point)
 *   Minimap: LMB (drag) moves the camera, RMB orders the selection there
 *
 * The interface (ASRHUD) sees every mouse press first (OnSelectPressed / OnCommandPressed ask ASRHUD::OnMousePress),
 * so a click on a panel never reaches the world. While a menu is up (USRGameFlowSubsystem::IsModal) the game mapping
 * context is swapped for a tiny menu one (mouse buttons, Esc, F1): no hotkey, order or camera input gets through.
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

	// ---- Buildings: one at a time, never together with units ----
	void SelectBuilding(ASRBuilding* Building);
	ASRBuilding* GetSelectedBuilding() const { return SelectedBuilding.Get(); }
	ASRBuilding* GetHoveredBuilding() const { return HoveredBuilding.Get(); }
	/** Queue a recruit at the selected barracks / range if it trains that type, else at the player's least busy one. */
	bool RecruitTroop(ESRUnitType Type);
	/** The selected (or else the first) barracks / range the player owns gets this rally point. */
	void SetRallyFor(const FVector& GroundPoint);
	/** The player's finished building that would train Type (least busy first), or null. */
	ASRBuilding* FindTrainer(ESRUnitType Type) const;
	/** HUD feedback: which recruit button was last used, and when (real seconds). */
	int32 GetLastRecruitButton() const { return LastRecruitButton; }
	double GetLastRecruitTime() const { return LastRecruitTime; }
	bool WasLastRecruitAccepted() const { return bLastRecruitAccepted; }

	/** Esc with nothing to cancel: opens the pause menu. */
	virtual void OnEscapeUnhandled();

	// ---- Interface hooks ----
	/** Swaps the game key bindings for the menu's (mouse buttons, Esc, F1) and back; drops any half-made drag. */
	void SetMenuInput(bool bMenu);
	/** Nothing selected, nothing in hand: called when a match starts or the main menu opens. */
	void ResetForNewMatch();
	/** The command buttons of the selection panel (same as the A / F / G / Delete keys). */
	void ArmAttackMoveCommand() { ArmAttackMove(); }
	void CycleFormationCommand() { OnCycleFormation(); }
	void ArmPatrolCommand() { ArmPatrol(); }
	bool IsPatrolArmed() const { return bPatrolArmed; }
	void IssuePatrol(const FVector& GroundPoint);
	/** Disband the selected platoon (its troops stay selected). */
	void DisbandPlatoonCommand();
	/** The formation a selection that is not a platoon takes (F cycles it). */
	ESRFormationShape GetLooseFormation() const { return LooseFormation; }
	/** The formation the current selection would move in. */
	ESRFormationShape GetSelectionFormation() const;

	// ---- build menu ----
	void ToggleBuildMenu();
	void SetBuildMenuOpen(bool bOpen);
	bool IsBuildMenuOpen() const { return bBuildMenuOpen; }
	ESRBuildCategory GetBuildMenuTab() const { return BuildMenuTab; }
	void SetBuildMenuTab(ESRBuildCategory Tab) { BuildMenuTab = Tab; }
	/** The player-buildable types in a tab, in menu order. */
	static void GetBuildMenuEntries(ESRBuildCategory Tab, TArray<ESRBuildingType>& Out);
	void CycleStanceCommand() { OnCycleStance(); }
	void CancelConstructionCommand() { OnDeleteBuilding(); }

	// ---- Building placement ----
	void BeginPlacement(ESRBuildingType Type);
	void CancelPlacement();
	bool IsPlacing() const { return bPlacing; }
	ESRBuildingType GetPlacingType() const { return PlacingType; }
	/** Why the spot under the cursor is refused (empty when it is fine). */
	const FText& GetPlacementReason() const { return PlacementReason; }
	bool IsPlacementValid() const { return bPlacementValid; }
	/** Where the building in hand would stand (its origin), while placing. */
	FVector GetPlacementLocation() const { return PlacementLocation; }

	// ---- Platoons ----
	/** The platoon key: assign (Ctrl/Cmd/Alt), add (Shift) or select (double-tap centres). */
	void PlatoonKey(int32 Index);
	void SelectPlatoon(int32 Index, bool bCentre);
	/** The platoon the whole selection belongs to, or INDEX_NONE. */
	int32 GetSelectedPlatoon() const;
	void IssueHold();

	// ---- Orders to the current selection ----
	void IssueMove(const FVector& GroundPoint, bool bAttackMove);
	void IssueAttack(ASRUnit* Target);
	void IssueAttackBuilding(ASRBuilding* Target);
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
	void OnHelp();
	void OnGroupKey(int32 Index) { PlatoonKey(Index); }
	void OnGroup1() { OnGroupKey(0); }
	void OnGroup2() { OnGroupKey(1); }
	void OnGroup3() { OnGroupKey(2); }
	void OnGroup4() { OnGroupKey(3); }
	void OnGroup5() { OnGroupKey(4); }
	void OnGroup6() { OnGroupKey(5); }
	void OnBuildMenu() { ToggleBuildMenu(); }
	void OnNextBuildTab();
	void OnPatrol() { ArmPatrol(); }
	void ArmPatrol();
	/** Re-form a group in place in a new shape (facing the way it already faces). */
	void ReformInPlace(const TArray<ASRUnit*>& Units, ESRFormationShape Shape);
	void OnHold() { IssueHold(); }
	void OnCycleFormation();
	void OnCycleStance();
	void OnCancel();
	void OnDeleteBuilding();
	void UpdatePlacement();
	void TryPlace();
	void OnRecruitShieldbearer() { RecruitHotkey(ESRUnitType::Shieldbearer); }
	void OnRecruitArcher() { RecruitHotkey(ESRUnitType::Archer); }
	void RecruitHotkey(ESRUnitType Type);
	ASRBuilding* PickBuildingUnderCursor() const;

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
	UPROPERTY(Transient) TObjectPtr<UInputAction> HelpAction;
	UPROPERTY(Transient) TObjectPtr<UInputMappingContext> MenuContext;
	bool bMenuInput = false;
	UPROPERTY(Transient) TObjectPtr<UInputAction> GroupActions[6];
	UPROPERTY(Transient) TObjectPtr<UInputAction> BuildMenuAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> BuildTabAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> PatrolAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> HoldAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> FormationAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> StanceAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> CancelAction;
	UPROPERTY(Transient) TObjectPtr<UInputAction> DeleteAction;
	UPROPERTY(Transient) TObjectPtr<ASRPlacementPreview> Preview;
	UPROPERTY(Transient) TObjectPtr<UInputAction> RecruitActions[2];

	UPROPERTY(Transient) TObjectPtr<USRBattleSubsystem> Battle;

	TArray<TWeakObjectPtr<ASRUnit>> Selection;
	bool bPlacing = false;
	ESRBuildingType PlacingType = ESRBuildingType::Farm;
	FText PlacementReason;
	bool bPlacementValid = false;
	FVector PlacementLocation = FVector::ZeroVector;
	TWeakObjectPtr<ASRUnit> Hovered;
	TWeakObjectPtr<ASRBuilding> SelectedBuilding;
	TWeakObjectPtr<ASRBuilding> HoveredBuilding;
	int32 LastRecruitButton = -1;
	double LastRecruitTime = -10.0;
	bool bLastRecruitAccepted = false;
	TArray<TWeakObjectPtr<ASRUnit>> BoxPreview;

	// left mouse
	bool bSelectDown = false;
	bool bBoxSelecting = false;
	FVector2D PressPos = FVector2D::ZeroVector;
	FVector2D DragPos = FVector2D::ZeroVector;
	double LastClickTime = -10.0;
	ESRUnitType LastClickType = ESRUnitType::Shieldbearer;

	bool bAttackMoveArmed = false;
	bool bPatrolArmed = false;
	bool bBuildMenuOpen = false;
	ESRBuildCategory BuildMenuTab = ESRBuildCategory::Economy;
	ESRFormationShape LooseFormation = ESRFormationShape::Line;

	bool bCursorOverride = false;
	FVector2D CursorOverride = FVector2D(0.5f, 0.5f);

	// A / S tap-or-hold
	bool bKeyADown = false, bKeyAPanned = false;
	bool bKeySDown = false, bKeySPanned = false;
	double KeyADownTime = 0.0, KeySDownTime = 0.0;

	int32 LastGroupRecalled = -1;
	double LastGroupRecallTime = -10.0;
};
