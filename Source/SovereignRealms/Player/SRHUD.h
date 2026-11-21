// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "Common/SRTypes.h"
#include "Fonts/SlateFontInfo.h"
#include "Battle/SRGameFlowSubsystem.h"
#include "SRHUD.generated.h"

class ASRPlayerController;
class ASRBuilding;
class UTexture2D;
class UFont;
class ASRUnit;

/** Cells of the icon atlas /Game/SR/UI/T_UI_Icons, in the order Tools/ui/gen_ui_art.py draws them. */
enum class ESRIcon : uint8
{
	Coin, Food, Pop, Shield, Bow, Farm, Mine, Tower,
	FormLine, FormColumn, FormWedge, FormSquare, StanceAggressive, StanceDefensive, StanceHold, Stop,
	Swords, AlertAttack, AlertLost, AlertDone, AlertWave, AlertPop, AlertInfo, Clock,
	Pause, Help, RecruitFlag, Castle, ChevronDown, ChevronUp, Crown, Cancel,
	PortraitShield, PortraitArcher, Check, Vein, Barracks, Range, Hammer, Patrol,
	Disband, PortraitHorse, PortraitCatapult, Stable, Workshop, PortraitBuilder, Granary, Treasury,
	PortraitScout, PortraitMedic
};

inline ESRIcon SRUnitIcon(ESRUnitType Type)
{
	switch (Type)
	{
	case ESRUnitType::Archer: return ESRIcon::PortraitArcher;
	case ESRUnitType::Horseman: return ESRIcon::PortraitHorse;
	case ESRUnitType::Catapult: return ESRIcon::PortraitCatapult;
	case ESRUnitType::Builder: return ESRIcon::PortraitBuilder;
	case ESRUnitType::Scout: return ESRIcon::PortraitScout;
	case ESRUnitType::Medic: return ESRIcon::PortraitMedic;
	default: return ESRIcon::PortraitShield;
	}
}

/** The recruit hotkey of a troop type (Q / E / R / T, Y for a Builder, J for the Scout, N for a Medic). */
inline const TCHAR* SRUnitKey(ESRUnitType Type)
{
	switch (Type)
	{
	case ESRUnitType::Archer: return TEXT("E");
	case ESRUnitType::Horseman: return TEXT("R");
	case ESRUnitType::Catapult: return TEXT("T");
	case ESRUnitType::Builder: return TEXT("Y");
	case ESRUnitType::Scout: return TEXT("J");
	case ESRUnitType::Medic: return TEXT("N");
	default: return TEXT("Q");
	}
}

/**
 * The whole interface, drawn immediate-mode on the HUD canvas every frame (Docs/UI.md):
 *
 *   main menu / pause menu / victory-defeat screen / settings / controls      SRHUDMenus.cpp
 *   in-game HUD: resource bar, alerts, minimap, build menu, selection panel,
 *                platoon panel                                                 SRHUDGame.cpp
 *   world-space feedback (health bars, box select, payout popups, training
 *   bars) and the drawing / input primitives                                   SRHUD.cpp
 *
 * Which of them is up follows USRGameFlowSubsystem's state. Everything is laid out in "design units" (pixels at
 * 1080p) times UI, the interface scale: the view height / 1080 (never below 0.8, so a 720p window stays readable)
 * times the player's UI Scale option. Text is drawn with the engine's Roboto through the Slate font cache, so it is
 * sharp at every size; icons come from one pixel-art atlas.
 *
 * Input: there are no widgets. ASRPlayerController hands every mouse press to OnMousePress first; if the press is
 * over a panel drawn last frame (or a menu is up) it is queued and answered by the Button() that contains it during
 * this frame's draw, and never reaches the world. This also means scripted input (sr.Cursor + sr.Key) drives the
 * interface exactly like a real mouse.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void DrawHUD() override;

	/** A mouse button went down at a viewport position. True = the interface took it (do nothing in the world). */
	bool OnMousePress(const FVector2D& ViewportPixels, bool bRight);
	/** Is the viewport position over a panel (or is a menu up)? */
	bool IsOverUI(const FVector2D& ViewportPixels) const;
	/** Esc: closes the open overlay / sub-screen / pause menu. False = nothing of the interface's to close. */
	bool OnEscape();
	/** F1: the controls overlay. */
	void ToggleLegend();

private:
	enum class EScreen : uint8 { None, NewGame, Controls, Settings, Confirm, Saves };
	enum class EConfirm : uint8 { Restart, MainMenu, Quit };
	enum { AlignLeft = 0, AlignCentre = 1, AlignRight = 2 };
	enum { Regular = 0, Bold = 1, Black = 2, Condensed = 3 };

	/** What a Button() call reports back. */
	struct FBtn
	{
		bool bClicked = false;      // left press landed on it this frame
		bool bRightClicked = false;
		bool bHover = false;
		bool bHeld = false;         // pressed on it and the button is still down (drags)
		float Hot = 0.f;            // 0..1 eased hover, for the highlight
	};

	// ---- frame ----
	void BeginFrame();
	void EndFrame();
	float U(float Design) const { return FMath::RoundToFloat(Design * UI); }

	// ---- primitives (SRHUD.cpp); every coordinate is in canvas pixels ----
	void Fill(float X, float Y, float W, float H, const FLinearColor& Color);
	void Outline(const FBox2D& Box, const FLinearColor& Color, float Thickness);
	/** A dark panel with bronze edge, gold hairline and corner brackets. bOrnate adds a heavier frame (menus). */
	void Panel(const FBox2D& Box, bool bOrnate = false, float Alpha = 1.f);
	/** Panel + registers the box so clicks on it do not reach the world. */
	void HudPanel(const FBox2D& Box);
	void Block(const FBox2D& Box) { Blockers.Add(Box); }
	FSlateFontInfo Font(float Pixels, int32 Weight) const;
	FVector2D TextSize(const FString& String, float Pixels, int32 Weight = Regular, float Spacing = 0.f) const;
	/** Draws text with its top-left (or top-centre / top-right) at X, Y. Returns its width. */
	float Text(const FString& String, float X, float Y, float Pixels, const FLinearColor& Color, int32 Align = AlignLeft, int32 Weight = Regular, float Spacing = 0.f, bool bShadow = true);
	/** Text centred vertically in a box. */
	float TextIn(const FBox2D& Box, const FString& String, float Pixels, const FLinearColor& Color, int32 Align = AlignCentre, int32 Weight = Regular, float Spacing = 0.f, bool bShadow = true);
	void Icon(ESRIcon Which, float X, float Y, float Size, const FLinearColor& Tint = FLinearColor::White, bool bEnemy = false);
	void Meter(float X, float Y, float W, float H, float Frac, const FLinearColor& FillColor);
	void KeyCap(const FString& Key, float RightX, float Y, bool bEnabled);
	void Rule(float X, float Y, float W, float Alpha = 1.f);
	/** A one-line message plate: icon, text, an accent bar on its left. X is its centre (or its left edge). Returns its box. */
	FBox2D Pill(const FString& Label, float X, float Y, float Pixels, ESRIcon Which, const FLinearColor& Accent, float Alpha = 1.f, bool bCentre = true);

	/** Hit-test + hover animation for a rectangle. Id must be unique among the buttons drawn this frame. */
	FBtn Button(const FBox2D& Box, uint32 Id, bool bEnabled = true);
	void ButtonFrame(const FBox2D& Box, const FBtn& B, bool bEnabled, bool bActive = false);
	/** A square command button: frame, icon, hotkey cap. */
	FBtn IconButton(const FBox2D& Box, uint32 Id, ESRIcon Which, const TCHAR* Key, bool bEnabled = true, bool bActive = false);
	/** A menu entry: label, gold accent that grows on hover. */
	bool MenuButton(const FBox2D& Box, uint32 Id, const FString& Label, bool bEnabled = true, bool bSelected = false);
	bool Slider(const FBox2D& Box, uint32 Id, float& Value, float Min, float Max);
	bool Toggle(const FBox2D& Box, uint32 Id, bool& bValue);
	/** Shown at the end of the frame, next to Anchor. */
	void SetTooltip(const FBox2D& Anchor, const FString& Title, const TArray<FString>& Lines);
	void DrawTooltip();
	void Click(bool bError = false);

	// ---- world-space feedback (SRHUD.cpp) ----
	void DrawSelectionBox();
	void DrawHealthBars();
	void DrawPayoutPopups();
	void DrawTrainingBars();
	void DrawRouteLines();
	/** Ground circles round selected troops: line of sight, and an archer's bow range. */
	void DrawRangeCircles();
	/** Zoomed far out, a team-coloured pip over each troop so armies read at a glance. */
	void DrawFarPips();
	struct FRangeCircle { FVector2D At = FVector2D(1e9, 1e9); TArray<FVector> Sight, Reach; uint8 Stance = 255; };
	TMap<TWeakObjectPtr<ASRUnit>, FRangeCircle> RangeCircles;
	/** A shooting building's reach (selected tower / castle, or a tower being placed), re-sampled when it moves. */
	FRangeCircle BuildingReach;
	/** The castle's building zone (shown while placing a building or with the castle selected). */
	FRangeCircle BuildZone;
	void DrawBuildZone();
	void DrawPlatoonTags();
	/** The top bar's Builders list (open after a click on the counter): each builder and what it is doing. */
	bool bBuilderList = false;
	/** Green "+N" over troops a Medic just healed. */
	void DrawHealPopups();
	void DrawBuilderList(const FBox2D& Anchor);
	/** The Upgrade button of a building with levels (castle, watchtower, gold mine, training buildings, storehouses). */
	void DrawUpgradeButton(const FBox2D& Box, class ASRBuilding* Building);
	/** What raising the Citadel from level From to To brings (the card shown when it is raised, and the upgrade
	 * button's tooltip): more of things, and things new (bNew). */
	struct FUnlock { ESRIcon Icon; FString Text; bool bNew; };
	void CastleUnlocks(int32 From, int32 To, TArray<FUnlock>& Out) const;
	/** The card that says what the Citadel's new level brings (Clash of Clans' town hall unlock popover was the model). */
	void DrawCastleCard();
	int32 SeenCastleLevel = 0;
	int32 CardLevel = 0;
	double CardTime = -100.0;

	// ---- in-game HUD (SRHUDGame.cpp) ----
	void DrawGameHUD();
	void DrawTopBar();
	float DrawHints(float Y);
	void DrawAlerts(float Y);
	void DrawMinimap(const FBox2D& Box);
	void DrawBuildMenu(float X, float Bottom);
	void DrawSelectionPanel(const FBox2D& Box);
	void DrawTroopSelection(const FBox2D& Box);
	void DrawBuildingSelection(const FBox2D& Box, ASRBuilding* Building);
	void DrawPlatoonPanel();
	void DrawPlacementCursor();

	// ---- menus (SRHUDMenus.cpp) ----
	void DrawMainMenu();
	void DrawPauseMenu();
	void DrawEndScreen();
	void DrawLegendOverlay();
	/** The sub-screens (new game, controls, settings, confirm): one panel at a time, centred on CentreX. */
	void DrawScreen(float CentreX);
	void DrawControlsPanel(float CentreX, bool bCloseButton);
	void DrawSettingsPanel(float CentreX);
	void DrawNewGamePanel(float CentreX);
	void DrawConfirmPanel(float CentreX);
	/** The saved games: a list to load from (bSavesToSave false) or to save into (a new save, or over an old one);
	 * every row can be deleted (asks first). */
	void DrawSavesPanel(float CentreX);
	void OpenSaves(bool bToSave, bool bThenAct = false) { bSavesToSave = bToSave; SavesScroll = 0; PendingDelete.Reset(); PendingOverwrite.Reset(); OpenScreen(EScreen::Saves); bActAfterSave = bThenAct; }
	/** Does what the confirm panel was asked about (restart, main menu, quit) and closes the screens. */
	void DoConfirmed();
	void OpenScreen(EScreen NewScreen);
	void AskConfirm(EConfirm What);
	void DimScreen(float Alpha);

	/** The engine's Roboto (a runtime-cached font: FCanvasTextItem needs one to take the Slate font path). */
	UPROPERTY(Transient) TObjectPtr<UFont> UIFont;
	UPROPERTY(Transient) TObjectPtr<UTexture2D> IconAtlas;
	UPROPERTY(Transient) TObjectPtr<UTexture2D> TitleArt;

	// ---- the main menu's backdrop: the film of the battle (Content/Movies/LoadingBattle.mp4), silent, looping, filling
	// the screen. Open only while the main menu is up; if it cannot be opened the live realm stays the backdrop.
	/** Called every frame: opens the film on the main menu, closes and releases it everywhere else. */
	void UpdateMenuFilm(bool bMenu);
	/** Draws the film over the whole view (cover fit). False while there is no picture yet (or none will come). */
	bool DrawMenuFilm(float Alpha);
	UPROPERTY(Transient) TObjectPtr<class UMediaPlayer> MenuFilmPlayer;
	UPROPERTY(Transient) TObjectPtr<class UMediaTexture> MenuFilmTexture;
	UPROPERTY(Transient) TObjectPtr<class UFileMediaSource> MenuFilmSource;
	bool bMenuFilmFailed = false;      // tried and could not: not tried again by this HUD
	bool bMenuFilmHidWorld = false;    // the world's rendering is off behind the film
	double MenuFilmOpened = 0.0, MenuFilmShown = 0.0;
	UPROPERTY(Transient) TObjectPtr<UTexture2D> MinimapBase;

	// frame state
	ASRPlayerController* PC = nullptr;
	FVector2D View = FVector2D::ZeroVector;
	float UI = 1.f;
	float DpiScale = 1.f;
	float ToCanvas = 1.f;             // viewport pixels -> canvas units
	float Dt = 0.f;                   // real seconds
	double Now = 0.0;                 // real seconds
	FVector2D Mouse = FVector2D::ZeroVector;
	bool bMouse = false;
	bool bMouseDown = false;
	bool bInputOpen = true;           // false while drawing a layer that lies under a modal one
	ESRGameState State = ESRGameState::Playing;
	ESRGameState LastState = ESRGameState::Playing;

	// input
	struct FPress { bool bPending = false; bool bRight = false; FVector2D Pos = FVector2D::ZeroVector; };
	FPress Press;
	TArray<FBox2D> Blockers;          // panels drawn in the last frame
	uint32 ActiveId = 0;
	TMap<uint32, float> Hover;

	// tooltip of this frame
	bool bTooltip = false;
	FBox2D TooltipAnchor = FBox2D(ForceInit);
	FString TooltipTitle;
	TArray<FString> TooltipLines;

	// screens
	EScreen Screen = EScreen::None;
	EConfirm Confirm = EConfirm::Restart;
	bool bSavesToSave = false;
	int32 SavesScroll = 0;
	/** A delete asked for once (a second click within a few seconds does it). */
	FString PendingDelete;
	double PendingDeleteTime = -100.0;
	/** The same for saving over another match's saved game. */
	FString PendingOverwrite;
	double PendingOverwriteTime = -100.0;
	/** "Save and quit" with every slot in use: the save list is up to pick one, and the quit follows the save. */
	bool bActAfterSave = false;
	bool bLegend = false;
	int32 MenuDifficulty = 1;
	bool bMenuSandbox = false;
	/** New Game: the map chosen (an id in USRFeelSettings::Maps; the map being played when the screen opens). */
	FName MenuMap;
	float PendingScale = 1.f;
	bool bSettingsDirty = false;
	int32 LastSlotClicked = -1;
	double LastSlotClickTime = -10.0;
	FBox2D MapRect = FBox2D(ForceInit);
};
