#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "Fonts/SlateFontInfo.h"
#include "VLHUD.generated.h"

class AVLKing;
class UTexture2D;
class UFont;
struct FVLBuildingState;
enum class EVLBuilding : uint8;

/** The menu screens (the main game's USRGameFlowSubsystem states and the sub-screens of its menus). */
UENUM()
enum class EVLScreen : uint8
{
	None,       // playing: the in-game HUD
	Main,       // the title screen: New Game, How to Play, Settings, Quit
	NewGame,    // choose the map and the difficulty (over the title screen or the pause menu)
	Pause,      // Esc: Resume, Restart, New Game, Controls, Settings, Main menu, Quit (the game is paused)
	Settings,
	End,        // victory / defeat, with the match's numbers
	Controls,   // every key (F1)
	SaveGame,   // the slots to save the match to (over the pause menu; VLHUDSaves.cpp)
	LoadGame    // the slots to load (over the pause menu or the title screen)
};

/** Cells of the icon atlas /Game/Voxel/UI/T_UI_Icons (the main game's, Tools/ui/gen_ui_art.py), in its order. */
enum class EVLIcon : uint8
{
	Coin, Food, Pop, Shield, Bow, Farm, Mine, Tower,
	FormLine, FormColumn, FormWedge, FormSquare, StanceAggressive, StanceDefensive, StanceHold, Stop,
	Swords, AlertAttack, AlertLost, AlertDone, AlertWave, AlertPop, AlertInfo, Clock,
	Pause, Help, RecruitFlag, Castle, ChevronDown, ChevronUp, Crown, Cancel,
	PortraitShield, PortraitArcher, Check, Vein, Barracks, Range, Hammer, Patrol,
	Disband, PortraitHorse, PortraitCatapult, Stable, Workshop, PortraitBuilder, Granary, Treasury,
	PortraitScout, PortraitMedic
};

/** Cells of the portrait atlas /Game/Voxel/UI/T_UI_Portraits (Tools/blender/render_portraits.py): head-and-shoulders
 *  renders of the voxel characters, in this order. */
enum class EVLPortrait : uint8 { King, Swordsman, Archer, Spy, Builder, Jonathan };     // (an atlas without his cell: the archer's)

/** A unit's portrait by its kind ("King", "Swordsman", "Archer", "Spy", "Builder"). */
inline EVLPortrait VLPortraitOf(const FString& Kind)
{
	if (Kind == TEXT("Jonathan")) { return EVLPortrait::Jonathan; }
	return Kind == TEXT("Archer") ? EVLPortrait::Archer : (Kind == TEXT("King") ? EVLPortrait::King : (Kind == TEXT("Spy") ? EVLPortrait::Spy
		: (Kind == TEXT("Builder") ? EVLPortrait::Builder : EVLPortrait::Swordsman)));
}

/**
 * The whole interface, drawn immediate-mode on the HUD canvas every frame: the main game's ASRHUD (SRHUD.cpp,
 * SRHUDGame.cpp, SRHUDMenus.cpp, Docs/UI.md) ported one to one onto this project's battle (UVLBattle), orders
 * (UVLCommand) and units (AVLKing):
 *
 *   title screen / new game / pause menu / victory-defeat / settings / controls     VLHUDMenus.cpp
 *   in-game HUD: resource bar, alerts, minimap, selection panel (troops, or a
 *                building with its upgrade and recruit buttons), platoon panel,
 *                the castle's level card, the hero view's crosshair, mode box and help line   VLHUDGame.cpp
 *   world-space feedback (health bars, rings, range circles, routes, the box, payout popups,
 *   training bars, platoon tags) and the drawing / input primitives                  VLHUD.cpp
 *
 * Everything is laid out in design units (pixels at 1080p) times UI: the view height / 1080 (never below 0.8) times
 * the player's Interface scale. Text is the engine's Roboto through the Slate font cache (sharp at every size);
 * icons come from the main game's pixel-art atlas.
 *
 * Input: no widgets. AVLKing hands every mouse press in the overview to OnMousePress first; if the press is over a
 * panel drawn last frame (or a menu is up) it is queued and answered by the Button() that contains it during this
 * frame's draw, and never reaches the world. Scripted input (vl.UIClick) takes the same path.
 */
UCLASS()
class SOVEREIGNREALMS_API AVLHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void BeginPlay() override;
	/** (the settings screen left open as the game quits or the map changes: what was changed is saved all the same) */
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void DrawHUD() override;

	/** The building review field, L_Flatlands (every building side by side), rather than the village. */
	bool InFlatlands() const;
	/** The maps of the menu: 0 Realm v2 (the biggest battle map, L_RealmV2), 1 the realm (the battle map, L_Realm), 2 the
	 *  flatlands (the building review field), 3 the highlands (L_Highlands), 4 the Test World (Realm v2 with both sides
	 *  at their most: UVLBattle::SetupTestWorld), 5 Realm v3 (the compact island, L_RealmV3: two plateaus, one pass,
	 *  the basin). The town and the village are gone. */
	static const int32 NumMaps = 6;
	static FString MapPath(int32 Map);
	static const TCHAR* MapName(int32 Map);
	int32 CurrentMap() const;
	/** The two maps that are not this one: Which 0 = the next round, 1 = the one after. */
	int32 OtherMap(int32 Which) const { return (CurrentMap() + 1 + Which) % NumMaps; }
	/** Opens a map with a match started on it at a difficulty (the New Game screen, Restart, M, vl.Map). */
	static void OpenMatch(const UObject* WorldContext, int32 Map, int32 Difficulty);

	/** A menu screen is up: the world's input is not read (kept for the bow and the cursor). */
	bool bMenu = false;
	EVLScreen GetScreen() const;
	void SetScreen(EVLScreen InScreen);
	/** The title screen (or a screen opened from it) is up: the overview drifts behind it. */
	bool IsTitle() const { return Base == EVLScreen::Main; }
	/** Esc (or P): closes the controls overlay / the open sub-screen / the pause menu, or opens the pause menu. */
	void OnEscape();
	/** F1: the controls overlay while playing, the Controls screen in the menus. */
	void ToggleLegend();
	/** A menu screen's keys this frame (Enter, and the old Esc menu's M, U, V, L, I, X) and its clicks. */
	void MenuInput(APlayerController* PC, AVLKing* Me);
	/** A mouse button went down (bRight: a right click let go) at a viewport position. True = the interface took it. */
	bool OnMousePress(const FVector2D& ViewportPixels, bool bRight);
	/** Is the viewport position over a panel (or is a menu or the controls overlay up)? */
	bool IsOverUI(const FVector2D& ViewportPixels) const;
	/** vl.HUD: the buttons drawn last frame, as fractions of the view. */
	void LogButtons() const;

	/** The player's interface scale (Settings), 80..140%. */
	static float InterfaceScale;
	/** F5 (the quicksave written) / F9 (bLoad: the quicksave loaded), and vl.Quick. */
	void QuickSave(bool bLoad);
	/** Is this a screen drawn over the pause menu or the title screen (New Game, Settings, Controls, Save, Load)? */
	static bool IsSubScreen(EVLScreen Screen)
	{
		return Screen == EVLScreen::NewGame || Screen == EVLScreen::Settings || Screen == EVLScreen::Controls || Screen == EVLScreen::SaveGame || Screen == EVLScreen::LoadGame;
	}

private:
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

	// ---- settings and screens
	void ApplySettings();
	void SaveSettings();
	void OpenSub(EVLScreen NewSub);
	void AskConfirm(EConfirm What);
	void DoConfirmed();

	// ---- frame
	void BeginFrame();
	void EndFrame();
	float U(float Design) const { return FMath::RoundToFloat(Design * UI); }
	/** For its scope, design units are drawn smaller by a factor (never larger): a panel that has less room than its
	 *  design size (the selection panel between the Build button and the platoons on a narrow view, the top bar, a menu
	 *  taller than a small window) is drawn whole at a smaller scale, instead of running under its neighbour or off the
	 *  view. At 1: nothing changes, so a view with room for everything looks as it always did. */
	struct FFit
	{
		FFit(AVLHUD& InHUD, float Scale) : HUD(InHUD), Saved(InHUD.UI) { HUD.UI = Saved * FMath::Clamp(Scale, 0.4f, 1.f); }
		~FFit() { HUD.UI = Saved; }
		AVLHUD& HUD;
		float Saved;
	};
	/** The factor at which a panel of that design size fits the view with a margin round it (1: it fits as it is). */
	float FitScale(float DesignW, float DesignH) const;
	/** The left edge of a menu panel W wide centred on CentreX, kept inside the view and right of PanelLeft. */
	float PanelX(float CentreX, float W) const;
	/** Where the shared menu panels may begin: the view's left edge, or the right of the title screen's entries. */
	float PanelLeft = 0.f;

	// ---- primitives (VLHUD.cpp); every coordinate is in canvas pixels
	void Fill(float X, float Y, float W, float H, const FLinearColor& Color);
	void Outline(const FBox2D& Box, const FLinearColor& Color, float Thickness);
	/** A dark panel with bronze edge, gold hairline and corner brackets. bOrnate adds a heavier frame (menus). */
	void Panel(const FBox2D& Box, bool bOrnate = false, float Alpha = 1.f);
	/** Panel + registers the box so clicks on it do not reach the world. */
	void HudPanel(const FBox2D& Box);
	void Block(const FBox2D& Box) { BlockersNow.Add(Box); }
	FSlateFontInfo Font(float Pixels, int32 Weight) const;
	FVector2D TextSize(const FString& String, float Pixels, int32 Weight = Regular, float Spacing = 0.f) const;
	float Text(const FString& String, float X, float Y, float Pixels, const FLinearColor& Color, int32 Align = AlignLeft, int32 Weight = Regular, float Spacing = 0.f, bool bShadow = true);
	float TextIn(const FBox2D& Box, const FString& String, float Pixels, const FLinearColor& Color, int32 Align = AlignCentre, int32 Weight = Regular, float Spacing = 0.f, bool bShadow = true);
	void Icon(EVLIcon Which, float X, float Y, float Size, const FLinearColor& Tint = FLinearColor::White, bool bEnemy = false);
	/** A unit's portrait (the voxel character's head and shoulders); an enemy's a little reddened. */
	void Portrait(EVLPortrait Which, float X, float Y, float Size, const FLinearColor& Tint = FLinearColor::White, bool bEnemy = false);
	void Meter(float X, float Y, float W, float H, float Frac, const FLinearColor& FillColor);
	void KeyCap(const FString& Key, float RightX, float Y, bool bEnabled);
	void Rule(float X, float Y, float W, float Alpha = 1.f);
	FBox2D Pill(const FString& Label, float X, float Y, float Pixels, EVLIcon Which, const FLinearColor& Accent, float Alpha = 1.f, bool bCentre = true);
	FBtn Button(const FBox2D& Box, uint32 Id, bool bEnabled = true);
	void ButtonFrame(const FBox2D& Box, const FBtn& B, bool bEnabled, bool bActive = false);
	FBtn IconButton(const FBox2D& Box, uint32 Id, EVLIcon Which, const TCHAR* Key, bool bEnabled = true, bool bActive = false);
	bool MenuButton(const FBox2D& Box, uint32 Id, const FString& Label, bool bEnabled = true, bool bSelected = false);
	bool Slider(const FBox2D& Box, uint32 Id, float& Value, float Min, float Max);
	void SetTooltip(const FBox2D& Anchor, const FString& Title, const TArray<FString>& Lines);
	void DrawTooltip();
	void Click(bool bError = false);
	/** A world point on the canvas (Z <= 0: behind the view). */
	FVector Project(const FVector& World) const;

	// ---- world-space feedback (VLHUD.cpp)
	void DrawUnitRings();
	void DrawSelectionBox();
	void DrawHealthBars();
	void DrawPayoutPopups();
	void DrawTrainingBars();
	void DrawRouteLines();
	/** What DrawRouteLines drew last frame (vl.HUD): line segments, the Builders' chains and their numbers, the Shift
	 *  preview to the ghost, and whether the hero view hid them. */
	struct FLineStats { int32 Segments = 0; int32 Chains = 0; int32 Badges = 0; bool bPreview = false; bool bHidden = false; int32 OrderChains = 0; int32 OrderBadges = 0;
		int32 Pathways = 0; int32 Grouped = 0; };       // (pathways drawn; of them, one line standing for a group of more than 7)
	FLineStats LineStats;
	/** The troops' order chains (Shift + click: UVLCommand::OrderChain) of the selection, and in the hero view of those
	 *  he commands: numbered plates over each queued foe and point, in the overview also a dashed line through them
	 *  (red attacks, blue walks). */
	void DrawOrderChains();
	/** Command mode (AVLKing::IsCommandMode): the way from A to B along the ground as the troops will walk it (the path
	 *  grid's route; kept for a while, by where its ends are), B last. */
	void PlanRoute(const FVector& A, const FVector& B, TArray<FVector>& Out);
	TMap<uint32, TArray<FVector>> PlanRoutes;
	/** Command mode: a target mark on an attack's target (a reticle round it on the ground and a crosshair at Over). */
	void DrawTargetMark(const FVector& On, const FVector& Over, float Radius, const FLinearColor& Col, bool bNow);
	/** Who the mode box (top left) showed last frame, for vl.HUD. */
	FString ModeBoxUnit;
	/** The hero chip was double-clicked: his hero view, once this frame's drawing is done. */
	TWeakObjectPtr<AVLKing> PendingHeroView;
	void DrawRangeCircles();
	void DrawFarPips();
	void DrawPlatoonTags();
	/** A shield over every unit the player's troops guard (the hero view's Option + click on a friend, V + click). */
	void DrawGuardMarks();
	/** The unit a row of the Builders' / Spy's list is hovered over: a pulsing ring at its feet and an arrow over it. */
	void DrawUnitHighlight();
	TWeakObjectPtr<AVLKing> HoverUnit;
	void DrawOrderMarkers();
	void Ring(const FVector& Centre, float Radius, const FLinearColor& Colour, float Thickness, int32 Sides = 24);
	/** The ground under a point (a trace down), or Fallback. */
	float GroundZ(const FVector2D& At, float Fallback) const;
	struct FRangeCircle { FVector2D At = FVector2D(1e9, 1e9); TArray<FVector> Sight, Reach; float ReachRadius = 0.f; };
	TMap<TWeakObjectPtr<AVLKing>, FRangeCircle> RangeCircles;
	FRangeCircle BuildingReach;
	TWeakObjectPtr<AActor> BuildingReachOf;

	// ---- in-game HUD (VLHUDGame.cpp)
	void DrawGameHUD();
	void DrawTopBar();
	float DrawHints(float Y);
	void DrawAlerts(float Y);
	void DrawMinimap(const FBox2D& Box);
	/** The panel from X rightwards, Room wide at most (up to the platoon panel), its bottom edge at Bottom. */
	void DrawSelectionPanel(float X, float Bottom, float Room);
	/** The troop ships (VLTroopShipHUD.cpp): a plate over each of the player's that says who is aboard; true if one
	 *  is the selection and its panel was drawn in the selection panel's place. */
	bool DrawShipPanel(float X, float Bottom, float Room);
	void DrawTroopSelection(const FBox2D& Box, const TArray<AVLKing*>& Units);
	void DrawBuildingSelection(const FBox2D& Box, AActor* Building);
	void DrawUpgradeButton(const FBox2D& Box, AActor* Building);
	void DrawLookoutButton(const FBox2D& Box, AActor* Tower);
	void DrawPlatoonPanel();
	void DrawHeroBits();
	// ---- building (VLHUDBuild.cpp): the Build button and its menu, placing (the pointer's pill, the plates on the
	// ground), the sites' bars, a site's panel (progress, Cancel), Demolish, the castle's Builder button, and the top
	// bar's chips for the hero, the Builders and the Spy
	void DrawBuildMenu(float X, float Bottom);
	void DrawPlacement();
	void DrawBuildFeedback();
	bool DrawSitePanel(const FBox2D& Box, AActor* Building);
	/** Returns the tab's left edge (the panel's right margin where it is not drawn): the Rotate tab sits left of it. */
	float DrawDemolishTab(const FBox2D& Box, AActor* Building);
	void DrawRotateTab(const FBox2D& Box, AActor* Building, float RightX);
	/** The panel of a free gold mine (neutral, or abandoned): what it gives, and Claim. */
	void DrawClaimPanel(const FBox2D& Box, AActor* Mine);
	void DrawBuilderButton(const FBox2D& R, AActor* Castle);
	float TopChipsWidth() const;
	void DrawTopChips(float X, float Y, float H);
	/** The list under the Builders' chip (1), the Spy's (2) or the hero's (3: King David and Jonathan, once Jonathan has
	 *  come): a row per unit with what it is doing; a click goes to it and selects it (a hero's: twice, plays him),
	 *  hovering marks it in the world (HoverUnit). 0: closed. */
	void DrawChipList();
	/** The castle panel's row of its corners (VLCastleCorners.cpp): a small bar for each of the four (grey: no archer
	 *  at this level, red: knocked out), and for the player's, Repair (its price in gold) or how the repair stands. */
	void DrawCornerRow(float X, float Y, float Right, AActor* Castle);
	/** The hero's list (ChipList 3): King David and Jonathan, each with his face, health and state (played, in the
	 *  field, or back at the castle in so long); a click goes to him and selects him, a second within 0.35 s plays him. */
	void DrawHeroList();
	int32 HeroListLast = -1;
	double HeroListLastTime = -10.0;
	int32 ChipList = 0;
	FBox2D ChipListChip = FBox2D(ForceInit);
	/** The command card's Assign picker (six platoon chips over the Assign button); drawn by DrawTroopSelection. */
	void DrawAssignPicker(const TArray<AVLKing*>& Units, const FBox2D& Anchor, float Bottom);
	bool bAssignOpen = false;
	bool bAssignDrawn = false;
	/** Is Option / Alt held (the tooltips show only then; Option + click on a platoon's row: guard it)? */
	bool AltHeld() const;
	/** Plates on the ground (world centres, each half-plate axis), filled with a colour each (sRGB): one canvas batch. */
	void GroundPlates(const TArray<FVector>& Centres, const FVector& AxisX, const FVector& AxisY, const TArray<FLinearColor>& Colours);
	int32 LastChip = -1;
	double LastChipTime = -10.0;
	/** What raising the castle from level From to To brings (the card shown when it is raised, and the upgrade
	 *  button's tooltip). */
	struct FUnlock { EVLIcon Icon; FString Text; bool bNew; };
	void CastleUnlocks(int32 From, int32 To, TArray<FUnlock>& Out) const;
	void DrawCastleCard();
	int32 SeenCastleLevel = 0;
	int32 CardLevel = 0;
	double CardTime = -100.0;
	/** The selected building, if the overview shows one. */
	AActor* SelectedBuilding() const;
	void SelectedUnits(TArray<AVLKing*>& Out) const;
	/** The title screen's backdrop: the overview camera frames the whole map (from the level's ground bounds), and the
	 *  silhouettes (M_Silhouette on the level's post-process volumes) are off while it shows. */
	void UpdateTitleBackdrop();
	struct FMutedBlendable { TWeakObjectPtr<class APostProcessVolume> Volume; int32 Index = 0; float Weight = 1.f; };
	TArray<FMutedBlendable> MutedSilhouettes;
	bool bSilhouettesOff = false;
	/** Makes the minimap's picture (a one-off capture of the ground from above). */
	void CaptureMinimap(const FBox2D& World);

	// ---- menus (VLHUDMenus.cpp)
	void DrawMainMenu();
	void DrawPauseMenu();
	void DrawEndScreen();
	void DrawLegendOverlay();
	void DrawSub(float CentreX);
	void DrawControlsPanel(float CentreX, bool bCloseButton);
	void DrawSettingsPanel(float CentreX);
	void DrawNewGamePanel(float CentreX);
	// ---- saved games (VLHUDSaves.cpp; UVLSaves): the Save Game / Load Game screens (a row a slot: its map, the time
	// played, when it was saved), with a question before a slot is written over or a match in progress is left; F5
	// the quicksave, F9 loads it; the title screen's Continue
	void DrawSavesPanel(float CentreX, bool bSave);
	/** F5 / F9, read once a frame while a match is played (or its pause menu is up). */
	void SaveKeys();
	/** The slot (of UVLSaves::AllSlots) waiting for its "write over it?" / "leave this match?", or INDEX_NONE. */
	int32 SaveAsk = INDEX_NONE;
	void DrawConfirmPanel(float CentreX);
	/** "Keep this display mode?" with its countdown, over everything, while UVLGraphics waits for the answer. */
	void DrawDisplayConfirm();
	void DimScreen(float Alpha);

	UPROPERTY(Transient) TObjectPtr<UFont> UIFont;
	UPROPERTY(Transient) TObjectPtr<UTexture2D> IconAtlas;
	UPROPERTY(Transient) TObjectPtr<UTexture2D> TitleArt;
	UPROPERTY(Transient) TObjectPtr<UTexture2D> PortraitAtlas;
	/** Each unit's health as last seen and when it last changed (its bar shows for a while after a hit or a heal). */
	struct FBarSeen { float Health = -1.f; double ChangedAt = -100.0; };
	TMap<TWeakObjectPtr<AVLKing>, FBarSeen> BarSeen;
	// ---- B: the units looked at once a frame (bars, pips, rings, the minimap's dots): the living, each one's platoon,
	// the selection as a set. vl.Opt.Hud 0: the old walks and one canvas tile per rectangle.
	struct FUnitFrame
	{
		TArray<AVLKing*> Live;
		TMap<const AVLKing*, int32> Platoon;
		TSet<const AVLKing*> Selected;
		uint64 Frame = MAX_uint64;
	};
	FUnitFrame UnitFrame;
	const FUnitFrame& UnitsThisFrame();
	/** Rectangles put straight into the canvas's batch, as AHUD::DrawRect's tile would be (the same corners, colour
	 *  and blend: the same pixels), without a canvas item each. Nothing else may be drawn between Begin and End. */
	void BeginRects();
	void EndRects();
	/** Fill(), into the open batch if there is one. Colour as it should look (sRGB), as Fill takes it. */
	void Rect(float X, float Y, float W, float H, const FLinearColor& Color);
	/** The same with a colour already made linear (Lin once for many rectangles). */
	void RectLinear(float X, float Y, float W, float H, const FLinearColor& LinearColor);
	class FBatchedElements* RectBatch = nullptr;
	/** What the pointer is over (the building's hover outline): asked again only when the pointer or the camera has
	 *  moved, or every few frames (units walk). */
	AActor* HoverPick();
	TWeakObjectPtr<AActor> HoverActor;
	FVector2D HoverMouse = FVector2D(-1.0, -1.0);
	FVector HoverEye = FVector::ZeroVector;
	FRotator HoverRot = FRotator::ZeroRotator;
	float HoverFOV = 0.f;
	uint64 HoverFrame = 0;
	bool bHoverKnown = false;
	UPROPERTY(Transient) TObjectPtr<class UTextureRenderTarget2D> MinimapBase;
	UPROPERTY(Transient) TObjectPtr<class USceneCaptureComponent2D> MinimapCapture;
	bool bMinimapCaptured = false;
	double MinimapCaptureAt = -1.0;
	int32 MinimapShots = 0;            // captures asked for so far (three, then the capture component goes)

	// frame state
	APlayerController* PCtrl = nullptr;
	AVLKing* King = nullptr;
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

	// input
	struct FPress { bool bPending = false; bool bRight = false; FVector2D Pos = FVector2D::ZeroVector; };
	FPress Press;
	TArray<FBox2D> Blockers;          // panels drawn in the last frame
	TArray<FBox2D> BlockersNow;
	uint32 ActiveId = 0;
	TMap<uint32, float> Hover;
	TArray<TPair<uint32, FBox2D>> ButtonsNow, ButtonsLast;

	// tooltip of this frame
	bool bTooltip = false;
	FBox2D TooltipAnchor = FBox2D(ForceInit);
	FString TooltipTitle;
	TArray<FString> TooltipLines;

	// screens
	EVLScreen Base = EVLScreen::None;   // None (playing), Main, Pause, End
	EVLScreen Sub = EVLScreen::None;    // NewGame, Controls, Settings, or None; bConfirm over it
	bool bConfirm = false;
	EConfirm Confirm = EConfirm::Restart;
	bool bLegend = false;
	bool bBooted = false;
	bool bEndShown = false;
	double StateTime = 0.0;            // real time the state was entered (fades)
	int32 PickMap = 1;
	int32 PickDifficulty = 1;
	float PendingScale = 1.f;
	bool bSettingsDirty = false;
	bool bLookSpeedDirty = false;      // (the Mouse sensitivity slider moved: saved once it is let go)
	float MasterVolume = 1.f;
	int32 FrameCap = 2;                // 30, 40, 60, 120, unlimited
	bool bPlatoonsCollapsed = false;
	double RecruitFlashTime = -10.0;
	bool bRecruitAccepted = false;
	int32 LastSlotClicked = -1;
	double LastSlotClickTime = -10.0;
	FBox2D MapRect = FBox2D(ForceInit);
	FBox2D PlatoonRect = FBox2D(ForceInit);     // the platoon panel as drawn this frame (the hero view's help line keeps clear of it)
	FBox2D TopBarRect = FBox2D(ForceInit);
	FBox2D MapWorld = FBox2D(ForceInit);
	/** The minimap's "up" as a world yaw: the default camera's (AVLKing::GetHomeYaw) snapped to a quarter turn, so the
	 *  map lies as the world is first seen. Fixed for the match: it does not turn with Q / E (the view box does). */
	float MapYaw = 0.f;
	// (for vl.HUD: where the view box's middle and the player's castle were drawn on the minimap, px)
	FVector2D MapViewMid = FVector2D::ZeroVector, MapCastleAt = FVector2D::ZeroVector;
};
