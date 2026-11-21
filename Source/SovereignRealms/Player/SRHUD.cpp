// Copyright Sovereign Realms.

#include "Player/SRHUD.h"
#include "Player/SRHUDStyle.h"
#include "Player/SRPlayerController.h"
#include "Player/SRCameraPawn.h"
#include "Units/SRUnit.h"
#include "Buildings/SRBuilding.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRFogSubsystem.h"
#include "Battle/SRMapInfo.h"
#include "Battle/SRPlatoonSubsystem.h"
#include "Common/SRAudioSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Engine/Canvas.h"
#include "Engine/Texture2D.h"
#include "Engine/Font.h"
#include "Engine/World.h"
#include "CanvasItem.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"
#include "Misc/App.h"
#include "Misc/Paths.h"
#include "MediaPlayer.h"
#include "MediaTexture.h"
#include "FileMediaSource.h"
#include "Engine/GameViewportClient.h"

using namespace SRStyle;

namespace
{
	// The palette (SRHUDStyle.h) and every colour in the HUD code are written as they should LOOK (sRGB); the canvas
	// wants linear values. The primitives below convert on the way in, so no caller has to think about it.
	FLinearColor Lin(const FLinearColor& C) { return FLinearColor(FMath::Pow(C.R, 2.2f), FMath::Pow(C.G, 2.2f), FMath::Pow(C.B, 2.2f), C.A); }
	// ...and a colour that is already linear (the Sovereign Feel settings) is taken back out first.
	FLinearColor FromLinear(const FLinearColor& C) { return FLinearColor(FMath::Pow(C.R, 1.f / 2.2f), FMath::Pow(C.G, 1.f / 2.2f), FMath::Pow(C.B, 1.f / 2.2f), C.A); }
}

void ASRHUD::BeginPlay()
{
	Super::BeginPlay();
	UIFont = LoadObject<UFont>(nullptr, TEXT("/Engine/EngineFonts/Roboto.Roboto"));
	IconAtlas = LoadObject<UTexture2D>(nullptr, TEXT("/Game/SR/UI/T_UI_Icons.T_UI_Icons"));
	TitleArt = LoadObject<UTexture2D>(nullptr, TEXT("/Game/SR/UI/T_UI_Title.T_UI_Title"));
	// the minimap's picture: the map's own (its ASRMapInfo), else the one the first map always had
	const ASRMapInfo* Map = ASRMapInfo::Get(this);
	MinimapBase = (Map && Map->MinimapBase) ? Map->MinimapBase.Get() : LoadObject<UTexture2D>(nullptr, TEXT("/Game/SR/Textures/T_MinimapBase.T_MinimapBase"));
	MenuDifficulty = USRFeelSettings::Get().AIDifficulty;
	if (const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this)) { MenuMap = Flow->GetCurrentMapId(); }
}

// ============================================================================ frame

void ASRHUD::BeginFrame()
{
	PC = Cast<ASRPlayerController>(PlayerOwner);
	View = FVector2D(Canvas->SizeX, Canvas->SizeY);
	DpiScale = Canvas->Canvas ? FMath::Max(Canvas->Canvas->GetDPIScale(), 0.1f) : 1.f;
	int32 ViewX = 0, ViewY = 0;
	if (PC) { PC->GetViewportSize(ViewX, ViewY); }
	ToCanvas = ViewX > 0 ? View.X / ViewX : 1.f;

	// Design units are pixels at 1080p. Never below 0.8 (a 720p window keeps readable text), and never so large that
	// the bottom row (minimap, build menu, selection panel, platoons) no longer fits side by side.
	UI = FMath::Max(View.Y / 1080.f, 0.8f) * FMath::Clamp(USRFeelSettings::Get().HUDScale, 0.8f, 1.4f);
	UI = FMath::Max(FMath::Min(UI, View.X / 1500.f), 0.5f);

	Dt = FMath::Min(float(FApp::GetDeltaTime()), 0.1f);
	Now = GetWorld()->GetRealTimeSeconds();
	FVector2D Cursor;
	bMouse = PC && PC->GetCursorScreenPos(Cursor);
	Mouse = Cursor * ToCanvas;
	bMouseDown = PC && PC->IsInputKeyDown(EKeys::LeftMouseButton);
	Blockers.Reset();
	bTooltip = false;
	bInputOpen = true;
}

void ASRHUD::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// (also from DrawHUD; here as well because a hidden HUD, as in sr.Film, is not drawn and must still let go of the film)
	const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	UpdateMenuFilm(Flow && Flow->GetState() == ESRGameState::MainMenu);
}

void ASRHUD::EndPlay(const EEndPlayReason::Type Reason)
{
	UpdateMenuFilm(false);      // the next level must not inherit a world that is not drawn
	Super::EndPlay(Reason);
}

void ASRHUD::UpdateMenuFilm(bool bMenu)
{
	UGameViewportClient* Viewport = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
	if (!bMenu)
	{
		// a match: stop, let go of the player and its decoder, and give the world its rendering back
		if (MenuFilmPlayer) { MenuFilmPlayer->Close(); }
		if (MenuFilmTexture) { MenuFilmTexture->SetMediaPlayer(nullptr); }
		MenuFilmPlayer = nullptr;
		MenuFilmTexture = nullptr;
		MenuFilmSource = nullptr;
		if (bMenuFilmHidWorld && Viewport) { Viewport->bDisableWorldRendering = false; }
		bMenuFilmHidWorld = false;
		return;
	}
	if (bMenuFilmFailed) { return; }
	const double Clock = FPlatformTime::Seconds();
	if (!MenuFilmPlayer)
	{
		const FString Path = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("Movies/LoadingBattle.mp4"));
		if (!FPaths::FileExists(Path)) { bMenuFilmFailed = true; UE_LOG(LogTemp, Warning, TEXT("Menu film: %s is missing; the live realm is the backdrop"), *Path); return; }
		MenuFilmPlayer = NewObject<UMediaPlayer>(this);
		MenuFilmPlayer->PlayOnOpen = true;
		MenuFilmPlayer->SetLooping(true);
		MenuFilmPlayer->SetNativeVolume(0.f);
		MenuFilmTexture = NewObject<UMediaTexture>(this);
		MenuFilmTexture->AutoClear = true;
		MenuFilmTexture->ClearColor = FLinearColor::Black;
		MenuFilmTexture->SetMediaPlayer(MenuFilmPlayer);
		MenuFilmTexture->UpdateResource();
		MenuFilmSource = NewObject<UFileMediaSource>(this);
		MenuFilmSource->SetFilePath(Path);
		MenuFilmOpened = Clock;
		MenuFilmShown = 0.0;
		if (!MenuFilmPlayer->OpenSource(MenuFilmSource)) { bMenuFilmFailed = true; }
	}
	else if (MenuFilmPlayer->HasError() || (!MenuFilmPlayer->IsPlaying() && !MenuFilmPlayer->IsPreparing() && Clock - MenuFilmOpened > 6.0))
	{
		bMenuFilmFailed = true;
	}
	if (bMenuFilmFailed)
	{
		UE_LOG(LogTemp, Warning, TEXT("Menu film: could not be played; the live realm is the backdrop"));
		UpdateMenuFilm(false);
		return;
	}
	// The film has the whole screen once its first frames are up: the realm behind it need not be drawn.
	const bool bPicture = MenuFilmPlayer->IsPlaying() && MenuFilmTexture && MenuFilmTexture->GetResource() && MenuFilmTexture->GetWidth() > 16
		&& MenuFilmPlayer->GetTime() > FTimespan::FromSeconds(0.1);
	if (bPicture && MenuFilmShown <= 0.0) { MenuFilmShown = Clock; }
	if (Viewport && MenuFilmShown > 0.0 && Clock - MenuFilmShown > 0.6 && !bMenuFilmHidWorld) { Viewport->bDisableWorldRendering = true; bMenuFilmHidWorld = true; }
}

bool ASRHUD::DrawMenuFilm(float Alpha)
{
	if (!MenuFilmPlayer || !MenuFilmTexture || MenuFilmShown <= 0.0 || !MenuFilmTexture->GetResource()) { return false; }
	const float W = float(MenuFilmTexture->GetWidth()), H = float(MenuFilmTexture->GetHeight());
	if (W < 16.f || H < 16.f || View.X < 1.f || View.Y < 1.f) { return false; }
	// cover fit: the picture fills the view and the overhang is cropped evenly, never a bar
	float U0 = 0.f, V0 = 0.f, UL = 1.f, VL = 1.f;
	const float ViewAspect = View.X / View.Y, FilmAspect = W / H;
	if (ViewAspect > FilmAspect) { VL = FilmAspect / ViewAspect; V0 = (1.f - VL) * 0.5f; }
	else { UL = ViewAspect / FilmAspect; U0 = (1.f - UL) * 0.5f; }
	const float In = FMath::Clamp(float(FPlatformTime::Seconds() - MenuFilmShown) / 0.6f, 0.f, 1.f) * Alpha;      // eases in over the realm
	DrawTexture(MenuFilmTexture, 0.f, 0.f, View.X, View.Y, U0, V0, UL, VL, FLinearColor(1.f, 1.f, 1.f, In), In >= 1.f ? BLEND_Opaque : BLEND_Translucent);
	return true;
}

void ASRHUD::EndFrame()
{
	DrawTooltip();
	Press.bPending = false;                  // a press nothing answered is simply spent
	if (!bMouseDown) { ActiveId = 0; }
}

void ASRHUD::DrawHUD()
{
	Super::DrawHUD();
	const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	if (!Canvas || !Flow) { return; }
	BeginFrame();

	State = Flow->GetState();
	UpdateMenuFilm(State == ESRGameState::MainMenu);
	if (State != LastState)
	{
		// every state starts on its own first screen
		LastState = State;
		Screen = EScreen::None;
		bLegend = false;
	}

	if (State != ESRGameState::MainMenu)
	{
		// the match's own interface; under a menu it is still drawn but takes no input
		bInputOpen = State == ESRGameState::Playing && !bLegend;
		DrawFarPips();
		DrawHealthBars();
		DrawPlatoonTags();
		DrawTrainingBars();
		DrawBuildZone();
		DrawRangeCircles();
		DrawRouteLines();
		DrawPayoutPopups();
		DrawHealPopups();
		DrawSelectionBox();
		DrawGameHUD();
		bInputOpen = true;
	}

	switch (State)
	{
	case ESRGameState::MainMenu: DrawMainMenu(); break;
	case ESRGameState::Paused: DrawPauseMenu(); break;
	case ESRGameState::Ended: DrawEndScreen(); break;
	default: if (bLegend) { DrawLegendOverlay(); } break;
	}
	EndFrame();
}

// ============================================================================ input

bool ASRHUD::IsOverUI(const FVector2D& ViewportPixels) const
{
	if (State != ESRGameState::Playing || bLegend) { return true; }
	const FVector2D P = ViewportPixels * ToCanvas;
	for (const FBox2D& Box : Blockers)
	{
		if (Box.IsInside(P)) { return true; }
	}
	return false;
}

bool ASRHUD::OnMousePress(const FVector2D& ViewportPixels, bool bRight)
{
	// The state may have changed since the last draw (a console command, the match ending): ask the flow itself.
	const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	if (!(Flow && Flow->IsModal()) && !IsOverUI(ViewportPixels)) { return false; }
	Press.bPending = true;
	Press.bRight = bRight;
	Press.Pos = ViewportPixels * ToCanvas;
	return true;
}

void ASRHUD::Click(bool bError)
{
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(bError ? ESRSound::UIError : ESRSound::UIClick); }
}

ASRHUD::FBtn ASRHUD::Button(const FBox2D& Box, uint32 Id, bool bEnabled)
{
	FBtn B;
	B.bHover = bInputOpen && bMouse && Box.IsInside(Mouse);
	if (bInputOpen && Press.bPending && Box.IsInside(Press.Pos))
	{
		Press.bPending = false;
		if (Press.bRight) { B.bRightClicked = bEnabled; }
		else if (bEnabled) { B.bClicked = true; ActiveId = Id; }
		else { Click(true); }
	}
	B.bHeld = ActiveId == Id && bMouseDown;
	// eased hover: 100 ms in and out
	float& H = Hover.FindOrAdd(Id);
	H = FMath::FInterpConstantTo(H, B.bHover && bEnabled ? 1.f : 0.f, Dt, 10.f);
	B.Hot = H;
	return B;
}

// ============================================================================ primitives

void ASRHUD::Fill(float X, float Y, float W, float H, const FLinearColor& Color)
{
	if (W > 0.f && H > 0.f && Color.A > 0.f) { DrawRect(Lin(Color), X, Y, W, H); }
}

void ASRHUD::Outline(const FBox2D& Box, const FLinearColor& Color, float T)
{
	const float X = Box.Min.X, Y = Box.Min.Y, W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	Fill(X, Y, W, T, Color);
	Fill(X, Y + H - T, W, T, Color);
	Fill(X, Y + T, T, H - 2.f * T, Color);
	Fill(X + W - T, Y + T, T, H - 2.f * T, Color);
}

void ASRHUD::Panel(const FBox2D& Box, bool bOrnate, float Alpha)
{
	const float X = Box.Min.X, Y = Box.Min.Y, W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float B = FMath::Max(1.f, U(2.f)), I = FMath::Max(1.f, U(1.f));
	Fill(X + B, Y + 2.f * B, W, H, A(FLinearColor(0.f, 0.f, 0.f, 0.40f), Alpha));          // drop shadow
	Fill(X, Y, W, H, A(Bronze, Alpha));
	Fill(X + B, Y + B, W - 2.f * B, H - 2.f * B, A(PanelFill, Alpha));
	Fill(X + B, Y + B, W - 2.f * B, FMath::RoundToFloat(FMath::Min(H * 0.4f, U(46.f))), A(PanelSheen, Alpha * 0.55f));   // a lighter top: a slight sheen
	// a thin gold rule inside the bronze
	const float G = B + (bOrnate ? U(4.f) : U(2.f));
	Outline(FBox2D(FVector2D(X + G, Y + G), FVector2D(X + W - G, Y + H - G)), A(Gold, Alpha * (bOrnate ? 0.55f : 0.32f)), I);
	// corner brackets
	const float L = U(bOrnate ? 16.f : 9.f), T = FMath::Max(1.f, U(2.f));
	for (int32 c = 0; c < 4; ++c)
	{
		const bool bR = (c & 1) != 0, bD = (c & 2) != 0;
		const float CX = bR ? X + W - G : X + G, CY = bD ? Y + H - G : Y + G;
		Fill(bR ? CX - L : CX, bD ? CY - T : CY, L, T, A(GoldBright, Alpha));
		Fill(bR ? CX - T : CX, bD ? CY - L : CY, T, L, A(GoldBright, Alpha));
		if (bOrnate)
		{
			const float D = U(4.f);
			Fill((bR ? CX - U(8.f) - D : CX + U(8.f)), (bD ? CY - U(8.f) - D : CY + U(8.f)), D, D, A(Gold, Alpha));
		}
	}
}

void ASRHUD::HudPanel(const FBox2D& Box)
{
	Panel(Box);
	Block(Box);
}

FSlateFontInfo ASRHUD::Font(float Pixels, int32 Weight) const
{
	static const FName Faces[] = { TEXT("Regular"), TEXT("Bold"), TEXT("Black"), TEXT("BoldCondensed") };
	// Slate sizes are points at 96 dpi; snap to half points so the glyph cache holds a handful of sizes, not hundreds.
	return FCoreStyle::GetDefaultFontStyle(Faces[FMath::Clamp(Weight, 0, 3)], FMath::Max(5.f, FMath::RoundToFloat(Pixels * 0.75f * 2.f) * 0.5f));
}

FVector2D ASRHUD::TextSize(const FString& String, float Pixels, int32 Weight, float Spacing) const
{
	if (!FSlateApplication::IsInitialized()) { return FVector2D(String.Len() * Pixels * 0.5f, Pixels * 1.2f); }
	const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
	const FSlateFontInfo F = Font(Pixels, Weight);
	return FVector2D(Measure->Measure(String, F, DpiScale).X / DpiScale + Spacing * String.Len(), Measure->GetMaxCharacterHeight(F, DpiScale) / DpiScale);
}

float ASRHUD::Text(const FString& String, float X, float Y, float Pixels, const FLinearColor& Color, int32 Align, int32 Weight, float Spacing, bool bShadow)
{
	if (String.IsEmpty() || Color.A <= 0.f || !UIFont) { return 0.f; }
	const float W = TextSize(String, Pixels, Weight, Spacing).X;
	if (Align == AlignCentre) { X -= W * 0.5f; }
	else if (Align == AlignRight) { X -= W; }
	FCanvasTextItem Item(FVector2D(FMath::RoundToFloat(X), FMath::RoundToFloat(Y)), FText::FromString(String), Font(Pixels, Weight), Lin(Color));
	Item.Font = UIFont;
	Item.HorizSpacingAdjust = Spacing;
	if (bShadow)
	{
		const float Off = FMath::Max(1.f, FMath::RoundToFloat(Pixels / 14.f));
		Item.EnableShadow(FLinearColor(0.f, 0.f, 0.f, 0.8f * Color.A), FVector2D(Off, Off));
	}
	Canvas->DrawItem(Item);
	return W;
}

float ASRHUD::TextIn(const FBox2D& Box, const FString& String, float Pixels, const FLinearColor& Color, int32 Align, int32 Weight, float Spacing, bool bShadow)
{
	const float H = TextSize(String, Pixels, Weight, Spacing).Y;
	const float X = Align == AlignCentre ? (Box.Min.X + Box.Max.X) * 0.5f : (Align == AlignRight ? Box.Max.X : Box.Min.X);
	return Text(String, X, (Box.Min.Y + Box.Max.Y - H) * 0.5f, Pixels, Color, Align, Weight, Spacing, bShadow);
}

void ASRHUD::Icon(ESRIcon Which, float X, float Y, float Size, const FLinearColor& Tint, bool bEnemy)
{
	if (!IconAtlas) { return; }
	// atlas: 8 columns of 18 px cells (a 16 px icon and a 1 px gutter); the lower half of the rows are the enemy-red
	// copies. The row count is read off the texture (Tools/ui/gen_ui_art.py, ROWS), so the atlas can grow without a
	// change here; an icon the imported atlas does not hold yet is drawn as its nearest older relative.
	const float AtlasH = FMath::Max(float(IconAtlas->GetSizeY()), 36.f);
	const int32 HalfRows = FMath::Max(1, FMath::RoundToInt(AtlasH / 36.f));
	if (HalfRows < 7)
	{
		if (Which == ESRIcon::Granary) { Which = ESRIcon::Food; }
		else if (Which == ESRIcon::Treasury) { Which = ESRIcon::Coin; }
		else if (Which == ESRIcon::PortraitScout) { Which = ESRIcon::PortraitBuilder; }
		else if (Which == ESRIcon::PortraitMedic) { Which = ESRIcon::PortraitBuilder; }
	}
	const int32 N = int32(Which);
	const float Col = float(N % 8), Row = float(N / 8 + (bEnemy ? HalfRows : 0));
	DrawTexture(IconAtlas, FMath::RoundToFloat(X), FMath::RoundToFloat(Y), FMath::RoundToFloat(Size), FMath::RoundToFloat(Size),
		(Col * 18.f + 1.f) / 144.f, (Row * 18.f + 1.f) / AtlasH, 16.f / 144.f, 16.f / AtlasH, Lin(Tint), BLEND_Translucent);
}

void ASRHUD::Meter(float X, float Y, float W, float H, float Frac, const FLinearColor& FillColor)
{
	const float B = FMath::Max(1.f, U(1.f));
	const float FW = FMath::RoundToFloat(W * FMath::Clamp(Frac, 0.f, 1.f));
	Fill(X - B, Y - B, W + 2.f * B, H + 2.f * B, A(Bronze, FillColor.A));
	Fill(X, Y, W, H, A(FLinearColor(0.012f, 0.016f, 0.028f, 1.f), FillColor.A));
	Fill(X, Y, FW, H, FillColor);
	Fill(X, Y, FW, FMath::Max(1.f, FMath::RoundToFloat(H * 0.3f)), FLinearColor(1.f, 1.f, 1.f, 0.22f * FillColor.A));
}

void ASRHUD::KeyCap(const FString& Key, float RightX, float Y, bool bEnabled)
{
	const float P = U(13.f);
	const float W = FMath::Max(U(19.f), TextSize(Key, P, Bold).X + U(9.f)), H = U(19.f);
	const FBox2D Box(FVector2D(RightX - W, Y), FVector2D(RightX, Y + H));
	Fill(Box.Min.X, Box.Min.Y, W, H, bEnabled ? Gold : A(Bronze, 0.9f));
	const float B = FMath::Max(1.f, U(1.f));
	Fill(Box.Min.X + B, Box.Min.Y + B, W - 2.f * B, H - 2.f * B, FLinearColor(0.02f, 0.028f, 0.05f, 1.f));
	TextIn(Box, Key, P, bEnabled ? GoldBright : Dim, AlignCentre, Bold, 0.f, false);
}

void ASRHUD::Rule(float X, float Y, float W, float Alpha)
{
	// a gold hairline with a small diamond at its middle
	const float T = FMath::Max(1.f, U(1.f)), D = U(3.f);
	Fill(X, Y, W, T, A(Gold, 0.55f * Alpha));
	const float CX = FMath::RoundToFloat(X + W * 0.5f);
	Fill(CX - D, Y - T, 2.f * D, 3.f * T, A(GoldBright, Alpha));
	Fill(CX - T, Y - D, 2.f * T, 2.f * D + T, A(GoldBright, Alpha));
}

void ASRHUD::ButtonFrame(const FBox2D& Box, const FBtn& B, bool bEnabled, bool bActive)
{
	const float Down = B.bHeld ? FMath::Max(1.f, U(1.f)) : 0.f;
	const float X = Box.Min.X, Y = Box.Min.Y + Down, W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float E = FMath::Max(1.f, U(2.f));
	const FLinearColor Border = !bEnabled ? A(Bronze, 0.75f) : (bActive ? GoldBright : FMath::Lerp(A(Gold, 0.8f), GoldBright, B.Hot));
	FLinearColor Body = !bEnabled ? ButtonOff : FMath::Lerp(ButtonFill, ButtonHot, B.bHeld ? 0.3f : B.Hot);
	if (bActive) { Body = FMath::Lerp(Body, FLinearColor(0.30f, 0.22f, 0.07f, 0.98f), 0.6f); }
	Fill(X, Y, W, H, Border);
	Fill(X + E, Y + E, W - 2.f * E, H - 2.f * E, Body);
	if (bEnabled) { Fill(X + E, Y + E, W - 2.f * E, FMath::RoundToFloat(H * 0.42f), FLinearColor(1.f, 1.f, 1.f, 0.035f + 0.04f * B.Hot)); }
}

ASRHUD::FBtn ASRHUD::IconButton(const FBox2D& Box, uint32 Id, ESRIcon Which, const TCHAR* Key, bool bEnabled, bool bActive)
{
	const FBtn B = Button(Box, Id, bEnabled);
	ButtonFrame(Box, B, bEnabled, bActive);
	const float W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float S = FMath::RoundToFloat(FMath::Min(W, H) * 0.58f);
	Icon(Which, Box.Min.X + (W - S) * 0.5f, Box.Min.Y + (H - S) * 0.5f + (B.bHeld ? U(1.f) : 0.f) + (Key ? U(3.f) : 0.f), S, bEnabled ? FLinearColor::White : FLinearColor(0.4f, 0.4f, 0.45f, 0.8f));
	if (Key) { KeyCap(Key, Box.Max.X - U(3.f), Box.Min.Y + U(3.f), bEnabled); }
	return B;
}

bool ASRHUD::MenuButton(const FBox2D& Box, uint32 Id, const FString& Label, bool bEnabled, bool bSelected)
{
	const FBtn B = Button(Box, Id, bEnabled);
	const float X = Box.Min.X, Y = Box.Min.Y + (B.bHeld ? U(1.f) : 0.f), W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float Hot = bSelected ? 1.f : B.Hot;
	Fill(X, Y, W, H, FMath::Lerp(A(Bronze, 0.85f), GoldBright, Hot));
	const float E = FMath::Max(1.f, U(2.f));
	Fill(X + E, Y + E, W - 2.f * E, H - 2.f * E, bSelected ? FLinearColor(0.20f, 0.15f, 0.05f, 0.97f) : FMath::Lerp(ButtonFill, ButtonHot, Hot));
	Fill(X + E, Y + E, W - 2.f * E, FMath::RoundToFloat(H * 0.45f), FLinearColor(1.f, 1.f, 1.f, 0.03f + 0.03f * Hot));
	// gold accent on the left, growing with the hover
	Fill(X + E, Y + E, U(4.f) + U(6.f) * Hot, H - 2.f * E, FMath::Lerp(Gold, GoldBright, Hot));
	const FBox2D Inner(FVector2D(X + U(26.f) + U(6.f) * Hot, Y), FVector2D(X + W - U(12.f), Y + H));
	TextIn(Inner, Label, U(21.f), bEnabled ? FMath::Lerp(Parchment, GoldBright, Hot) : Dim, AlignLeft, Bold, U(1.f));
	if (B.bClicked) { Click(); }
	return B.bClicked;
}

bool ASRHUD::Slider(const FBox2D& Box, uint32 Id, float& Value, float Min, float Max)
{
	const FBtn B = Button(Box, Id);
	const float X = Box.Min.X, W = Box.Max.X - Box.Min.X, CY = (Box.Min.Y + Box.Max.Y) * 0.5f;
	const float Knob = U(14.f);
	bool bChanged = false;
	if (B.bHeld && W > Knob)
	{
		const float V = Min + FMath::Clamp((Mouse.X - X - Knob * 0.5f) / (W - Knob), 0.f, 1.f) * (Max - Min);
		bChanged = !FMath::IsNearlyEqual(V, Value, 0.0005f);
		Value = V;
	}
	const float T = FMath::Clamp((Value - Min) / (Max - Min), 0.f, 1.f);
	const float TH = U(8.f);
	Meter(X, FMath::RoundToFloat(CY - TH * 0.5f), W, TH, T, FMath::Lerp(Gold, GoldBright, B.Hot));
	const float KX = FMath::RoundToFloat(X + T * (W - Knob));
	Fill(KX, CY - U(11.f), Knob, U(22.f), B.bHeld || B.bHover ? GoldBright : Gold);
	Fill(KX + U(2.f), CY - U(9.f), Knob - U(4.f), U(18.f), FLinearColor(0.10f, 0.13f, 0.21f, 1.f));
	Fill(KX + U(6.f), CY - U(5.f), U(2.f), U(10.f), GoldBright);
	return bChanged;
}

bool ASRHUD::Toggle(const FBox2D& Box, uint32 Id, bool& bValue)
{
	const FBtn B = Button(Box, Id);
	if (B.bClicked) { bValue = !bValue; Click(); }
	ButtonFrame(Box, B, true, bValue);
	const float S = FMath::RoundToFloat((Box.Max.Y - Box.Min.Y) * 0.6f);
	if (bValue) { Icon(ESRIcon::Check, (Box.Min.X + Box.Max.X - S) * 0.5f, (Box.Min.Y + Box.Max.Y - S) * 0.5f, S); }
	return B.bClicked;
}

void ASRHUD::SetTooltip(const FBox2D& Anchor, const FString& Title, const TArray<FString>& Lines)
{
	bTooltip = true;
	TooltipAnchor = Anchor;
	TooltipTitle = Title;
	TooltipLines = Lines;
}

void ASRHUD::DrawTooltip()
{
	if (!bTooltip) { return; }
	// warm parchment, dark ink: reads as a note laid over the dark panels
	const float Pad = U(12.f), TP = U(18.f), LP = U(15.f), LH = U(21.f);
	float W = TextSize(TooltipTitle, TP, Bold).X;
	for (const FString& L : TooltipLines) { W = FMath::Max(W, TextSize(L, LP, Regular).X); }
	W += 2.f * Pad;
	const float H = 2.f * Pad + U(24.f) + TooltipLines.Num() * LH;
	float X = TooltipAnchor.Max.X + U(10.f), Y = TooltipAnchor.Min.Y;
	if (X + W > View.X - U(8.f)) { X = TooltipAnchor.Min.X - U(10.f) - W; }
	if (X < U(8.f)) { X = FMath::Clamp(TooltipAnchor.Min.X, U(8.f), View.X - W - U(8.f)); Y = TooltipAnchor.Min.Y - H - U(10.f); }
	Y = FMath::Clamp(Y, U(8.f), View.Y - H - U(8.f));
	X = FMath::RoundToFloat(X); Y = FMath::RoundToFloat(Y);
	const float B = FMath::Max(1.f, U(2.f));
	Fill(X + B, Y + 2.f * B, W, H, FLinearColor(0.f, 0.f, 0.f, 0.45f));
	Fill(X, Y, W, H, Bronze);
	Fill(X + B, Y + B, W - 2.f * B, H - 2.f * B, ParchmentFill);
	Fill(X + B, Y + B, W - 2.f * B, U(3.f), FLinearColor(1.f, 1.f, 1.f, 0.25f));
	Text(TooltipTitle, X + Pad, Y + Pad - U(2.f), TP, Ink, AlignLeft, Bold, 0.f, false);
	Fill(X + Pad, Y + Pad + U(23.f), W - 2.f * Pad, FMath::Max(1.f, U(1.f)), A(Bronze, 0.8f));
	for (int32 i = 0; i < TooltipLines.Num(); ++i)
	{
		Text(TooltipLines[i], X + Pad, Y + Pad + U(28.f) + i * LH, LP, A(Ink, 0.92f), AlignLeft, Regular, 0.f, false);
	}
}

// ============================================================================ world-space feedback

void ASRHUD::DrawSelectionBox()
{
	if (!PC || !PC->IsBoxSelecting()) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FVector2D P0 = PC->GetBoxStart() * ToCanvas, P1 = PC->GetBoxEnd() * ToCanvas;
	const FBox2D Box(FVector2D(FMath::Min(P0.X, P1.X), FMath::Min(P0.Y, P1.Y)), FVector2D(FMath::Max(P0.X, P1.X), FMath::Max(P0.Y, P1.Y)));
	Fill(Box.Min.X, Box.Min.Y, Box.Max.X - Box.Min.X, Box.Max.Y - Box.Min.Y, FromLinear(F.BoxFillColor));
	Outline(Box, FromLinear(F.BoxLineColor), FMath::Max(1.f, U(2.f)));
}

namespace
{
	/** How many progress rows DrawTrainingBars stacks over a building (training, construction, upgrade, repair), so
	 * the health bar can sit above them. */
	int32 OverheadRows(const ASRBuilding* B)
	{
		int32 Rows = B->GetQueue().Num() > 0 ? 1 : 0;
		if (B->Team == ESRTeam::Player)
		{
			Rows += B->IsUnderConstruction() ? 1 : 0;
			Rows += B->IsUpgrading() ? 1 : 0;
			Rows += (!B->IsUnderConstruction() && B->GetBuildersWorking() > 0 && B->NeedsWork()) ? 1 : 0;
		}
		return Rows;
	}
}

void ASRHUD::DrawHealthBars()
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Battle) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const double WorldNow = GetWorld()->GetTimeSeconds();
	const float B = FMath::Max(1.f, U(1.f));

	auto Bar = [&](const FVector& WorldPoint, float W, float H, float Frac, bool bEnemy, float Lift = 0.f)
	{
		const FVector S = Canvas->Project(WorldPoint);
		if (S.Z <= 0.f) { return; }
		const float X = FMath::RoundToFloat(S.X - W * 0.5f), Y = FMath::RoundToFloat(S.Y - H - Lift);
		// enemies get a red-tinted frame so the sides read at a glance
		Fill(X - B, Y - B, W + 2.f * B, H + 2.f * B, bEnemy ? FLinearColor(0.30f, 0.03f, 0.02f, 0.92f) : FLinearColor(0.02f, 0.03f, 0.07f, 0.92f));
		Fill(X, Y, W, H, FLinearColor(0.10f, 0.10f, 0.11f, 0.9f));
		Fill(X, Y, FMath::RoundToFloat(W * Frac), H, Health(Frac));
		Fill(X, Y, FMath::RoundToFloat(W * Frac), FMath::Max(1.f, FMath::RoundToFloat(H * 0.3f)), FLinearColor(1.f, 1.f, 1.f, 0.25f));
	};

	for (const ASRUnit* Unit : Battle->GetUnits())
	{
		if (!Unit || !Unit->IsActive()) { continue; }
		// Only when it matters: selected, or hurt recently. Keeps the battlefield clean.
		const bool bRecentlyHurt = Unit->GetHealthFrac() < 1.f && (WorldNow - Unit->GetLastDamagedTime()) < F.HealthBarLingerTime;
		if (!Unit->IsSelected() && !bRecentlyHurt) { continue; }
		if (!Battle->IsVisibleToPlayer(Unit)) { continue; }
		Bar(Unit->GetOverheadPoint(), U(F.HealthBarSize.X), FMath::Max(3.f, U(F.HealthBarSize.Y + 1.f)), Unit->GetHealthFrac(), Unit->GetTeam() == ESRTeam::Enemy);
	}
	if (!Economy) { return; }
	for (const ASRBuilding* Building : Economy->GetBuildings())
	{
		if (!Building || !Building->IsAlive() || Building->IsHidden()) { continue; }
		const bool bRecentlyHurt = Building->GetHealthFrac() < 1.f && (WorldNow - Building->GetLastDamagedTime()) < F.HealthBarLingerTime;
		if (!bRecentlyHurt && !(Building->IsSelected() && Building->GetHealthFrac() < 1.f)) { continue; }
		// over the progress rows (training, construction, upgrade, repair) rather than hidden by them
		const int32 Rows = OverheadRows(Building);
		Bar(Building->GetLabelPoint(), U(110.f), U(8.f), Building->GetHealthFrac(), Building->Team == ESRTeam::Enemy, Rows > 0 ? Rows * U(26.f) - U(4.f) : 0.f);
	}
}

void ASRHUD::DrawPlatoonTags()
{
	// A numbered tag in the platoon's colour floats over each platoon, so it can be told apart at a glance.
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this);
	if (!F.bShowPlatoonColors || !Platoons || !PC) { return; }
	for (int32 i = 0; i < Platoons->Num(); ++i)
	{
		const FSRPlatoon* P = Platoons->Find(i);
		if (!P) { continue; }
		// over the member nearest the platoon's middle, a little above the heads
		FVector2D Mid = FVector2D::ZeroVector;
		int32 N = 0;
		for (const TWeakObjectPtr<ASRUnit>& M : P->Members) { if (M.IsValid() && M->IsActive()) { Mid += M->GetPos2D(); ++N; } }
		if (N == 0) { continue; }
		Mid /= N;
		const ASRUnit* Anchor = nullptr;
		float Best = TNumericLimits<float>::Max();
		for (const TWeakObjectPtr<ASRUnit>& M : P->Members)
		{
			if (!M.IsValid() || !M->IsActive()) { continue; }
			const float D = FVector2D::DistSquared(M->GetPos2D(), Mid);
			if (D < Best) { Best = D; Anchor = M.Get(); }
		}
		if (!Anchor) { continue; }
		const FVector S = Canvas->Project(Anchor->GetOverheadPoint() + FVector(0.f, 0.f, 70.f));
		if (S.Z <= 0.f || S.X < -50.f || S.Y < -50.f || S.X > Canvas->ClipX + 50.f || S.Y > Canvas->ClipY + 50.f) { continue; }
		const FLinearColor Col = USRPlatoonSubsystem::PlatoonColor(i);
		const bool bSel = PC->GetSelectedPlatoon() == i;
		const float H = U(bSel ? 24.f : 20.f), W = H * 0.9f;
		const float X = FMath::RoundToFloat(S.X - W * 0.5f), Y = FMath::RoundToFloat(S.Y - H);
		Fill(X - 1.f, Y - 1.f, W + 2.f, H + 2.f, FLinearColor(0.02f, 0.02f, 0.03f, 0.9f));
		Fill(X, Y, W, H, FLinearColor(Col.R * 0.25f, Col.G * 0.25f, Col.B * 0.25f, 0.92f));
		Outline(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), Col, FMath::Max(1.f, U(bSel ? 2.f : 1.5f)));
		// a little pointer down to the troops
		for (float k = 0.f; k < U(5.f); k += 1.f)
		{
			const float w = U(5.f) - k;
			Fill(FMath::RoundToFloat(S.X - w), Y + H + k, FMath::Max(1.f, 2.f * w), 1.f, Col);
		}
		TextIn(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), FString::FromInt(i + 1), H * 0.8f, Col, AlignCentre, Black);
	}
}

void ASRHUD::DrawPayoutPopups()
{
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	for (const FSRPayoutPopup& Popup : Economy->GetPopups())
	{
		const float T = FMath::Clamp(Popup.Age / FMath::Max(F.PayoutPopupTime, 0.05f), 0.f, 1.f);
		// rises fast, then drifts; pops in over the first tenth and fades over the last third
		const float Rise = 1.f - FMath::Square(1.f - T);
		const FVector S = Canvas->Project(Popup.Origin + FVector(0.f, 0.f, F.PayoutPopupRise * Rise));
		if (S.Z <= 0.f) { continue; }
		const float Alpha = T > 0.66f ? 1.f - (T - 0.66f) / 0.34f : 1.f;
		const float Pop = T < 0.12f ? 1.f + 0.4f * (1.f - T / 0.12f) : 1.f;
		const float P = U(24.f) * Pop, IS = U(24.f) * Pop;
		const FString Label = FString::Printf(TEXT("+%d"), Popup.Amount);
		const float W = TextSize(Label, P, Bold).X;
		const float X = S.X - (W + U(5.f) + IS) * 0.5f, Y = S.Y - P * 0.6f;
		Text(Label, X, Y, P, A(Popup.Resource == ESRResource::Gold ? GoldBright : FoodColor, Alpha), AlignLeft, Bold);
		Icon(Popup.Resource == ESRResource::Gold ? ESRIcon::Coin : ESRIcon::Food, X + W + U(5.f), Y + P * 0.12f, IS, FLinearColor(1.f, 1.f, 1.f, Alpha));
	}
}

void ASRHUD::DrawHealPopups()
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }
	const FLinearColor Green(0.45f, 1.f, 0.42f, 1.f);
	for (const USRBattleSubsystem::FHealPopup& H : Battle->GetHealPopups())
	{
		const float T = FMath::Clamp(H.Age / 1.1f, 0.f, 1.f);
		const FVector S = Canvas->Project(H.Origin + FVector(0.f, 0.f, 70.f * (1.f - FMath::Square(1.f - T))));
		if (S.Z <= 0.f) { continue; }
		const float Alpha = T > 0.6f ? 1.f - (T - 0.6f) / 0.4f : 1.f;
		const FString Label = FString::Printf(TEXT("+%d"), H.Amount);
		const float P = U(21.f);
		Text(Label, S.X - TextSize(Label, P, Bold).X * 0.5f, S.Y - P, P, A(Green, Alpha), AlignLeft, Bold);
	}
}

void ASRHUD::DrawFarPips()
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr;
	if (!Battle || !Camera) { return; }
	// Fades in from 4.5 m of camera distance... to full at 7 m: by then a troop sprite is only a few pixels tall.
	const float Alpha = FMath::GetMappedRangeValueClamped(FVector2f(4500.f, 7000.f), FVector2f(0.f, 1.f), Camera->GetZoomDistance());
	if (Alpha <= 0.01f) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const float S = FMath::Max(2.f, U(4.f));
	for (const ASRUnit* Unit : Battle->GetUnits())
	{
		if (!Unit || !Unit->IsActive() || !Battle->IsVisibleToPlayer(Unit)) { continue; }
		const FVector P = Canvas->Project(Unit->GetSimPos() + FVector(0.f, 0.f, Unit->GetBodyHeight() + 30.f));
		if (P.Z <= 0.f) { continue; }
		const FLinearColor Team = Unit->GetTeam() == ESRTeam::Player ? F.PlayerTeamColor : F.EnemyTeamColor;
		FLinearColor Col = FLinearColor(FMath::Min(Team.R * 1.6f + 0.15f, 1.f), FMath::Min(Team.G * 1.6f + 0.15f, 1.f), FMath::Min(Team.B * 1.6f + 0.15f, 1.f), Alpha);
		// a platoon's troops show in its colour from afar too
		if (F.bShowPlatoonColors && Unit->GetTeam() == ESRTeam::Player && Unit->GetPlatoon() != INDEX_NONE) { Col = USRPlatoonSubsystem::PlatoonColor(Unit->GetPlatoon()); Col.A = Alpha; }
		// a little diamond with a dark rim
		for (int32 r = 0; r < 2; ++r)
		{
			const float H = S + (r == 0 ? FMath::Max(1.f, U(1.5f)) : 0.f);
			const FLinearColor C = r == 0 ? FLinearColor(0.02f, 0.02f, 0.03f, Alpha * 0.85f) : (Unit->IsSelected() ? FLinearColor(1.f, 0.95f, 0.7f, Alpha) : Col);
			for (float dy = -H; dy <= H; dy += 1.f)
			{
				const float w = H - FMath::Abs(dy);
				Fill(FMath::RoundToFloat(P.X - w), FMath::RoundToFloat(P.Y + dy), FMath::Max(1.f, 2.f * w), 1.f, C);
			}
		}
	}
}

void ASRHUD::DrawBuildZone()
{
	// Where buildings raise themselves: the castle's zone, a gold ring on the ground. Outside it a Builder must go.
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	const ASRBuilding* Castle = Eco ? Eco->GetCastle(ESRTeam::Player) : nullptr;
	const ASRBuilding* Sel = PC ? PC->GetSelectedBuilding() : nullptr;
	const bool bShow = PC && Castle && Battle && Castle->IsAlive() && (PC->IsPlacing() || Sel == Castle);
	if (!bShow) { return; }
	const float R = Castle->GetBuildZoneRadius();
	if (R <= 0.f) { return; }
	const FVector2D Centre = Castle->GetFootprintCentre();
	const bool bRadiusChanged = BuildZone.Sight.Num() > 0 && FMath::Abs(FVector2D::Distance(FVector2D(BuildZone.Sight[0].X, BuildZone.Sight[0].Y), Centre) - R) > 5.f;
	if (FVector2D::DistSquared(Centre, BuildZone.At) > 1.f || BuildZone.Sight.Num() == 0 || bRadiusChanged)
	{
		BuildZone.At = Centre;
		const int32 N = 300;
		BuildZone.Sight.Reset(N);
		const float RefZ = Castle->GetActorLocation().Z;
		for (int32 i = 0; i < N; ++i)
		{
			const float Ang = 2.f * PI * i / N;
			const FVector2D P = Centre + FVector2D(FMath::Cos(Ang), FMath::Sin(Ang)) * R;
			float Z = RefZ;
			Battle->SampleGround(P, RefZ + 1200.f, Z);
			BuildZone.Sight.Add(FVector(P.X, P.Y, Z + 15.f));
		}
	}
	const int32 N = BuildZone.Sight.Num();
	const float W = FMath::Max(1.f, U(3.f));
	const FLinearColor Col(1.f, 0.8f, 0.3f, 0.85f);
	for (int32 i = 0; i < N; ++i)
	{
		if (i % 3 == 2) { continue; }   // dashes
		const FVector S0 = Canvas->Project(BuildZone.Sight[i]);
		const FVector S1 = Canvas->Project(BuildZone.Sight[(i + 1) % N]);
		if (S0.Z > 0.f && S1.Z > 0.f) { DrawLine(S0.X, S0.Y, S1.X, S1.Y, Col, W); }
	}
	// a label on the ring's nearest point to the view centre
	const FVector2D ScreenMid(Canvas->ClipX * 0.5f, Canvas->ClipY * 0.5f);
	float Best = TNumericLimits<float>::Max();
	FVector2D LabelAt;
	for (int32 i = 0; i < N; i += 4)
	{
		const FVector S = Canvas->Project(BuildZone.Sight[i]);
		if (S.Z <= 0.f || S.X < 40.f || S.Y < 80.f || S.X > Canvas->ClipX - 40.f || S.Y > Canvas->ClipY - 200.f) { continue; }
		const float D = FVector2D::DistSquared(FVector2D(S.X, S.Y), ScreenMid);
		if (D < Best) { Best = D; LabelAt = FVector2D(S.X, S.Y); }
	}
	if (Best < TNumericLimits<float>::Max())
	{
		Text(TEXT("CASTLE ZONE: builds itself inside, needs a Builder outside"), LabelAt.X, LabelAt.Y - U(22.f), U(14.f), Col, AlignCentre, Bold);
	}
	(void)F;
}

void ASRHUD::DrawRangeCircles()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!F.bShowRangeCircles || !Battle || !PC)
	{
		RangeCircles.Reset();
		return;
	}

	// A tower's (or the castle's) reach: the selected one, or the tower in hand while placing it.
	{
		FVector2D Centre;
		float Reach = 0.f, RefZ = 0.f;
		bool bEnemy = false;
		if (PC->IsPlacing())
		{
			const FSRBuildingStats& S = F.BuildingStatsFor(PC->GetPlacingType());
			const FVector L = PC->GetPlacementLocation();
			Centre = FVector2D(L.X, L.Y) + (S.FootprintMin + S.FootprintMax) * 0.5f;
			Reach = S.AttackRange;
			RefZ = L.Z;
		}
		else if (const ASRBuilding* B = PC->GetSelectedBuilding(); B && B->IsFinished())
		{
			Centre = B->GetFootprintCentre();
			Reach = B->GetAttackRange();
			RefZ = B->GetActorLocation().Z;
			bEnemy = B->Team == ESRTeam::Enemy;
		}
		if (Reach > 0.f)
		{
			if (FVector2D::DistSquared(Centre, BuildingReach.At) > 1.f || BuildingReach.Sight.Num() == 0)
			{
				BuildingReach.At = Centre;
				const int32 N = FMath::Clamp(FMath::RoundToInt(Reach / 22.f), 48, 96);
				BuildingReach.Sight.Reset(N);
				for (int32 i = 0; i < N; ++i)
				{
					const float Ang = 2.f * PI * i / N;
					const FVector2D P = Centre + FVector2D(FMath::Cos(Ang), FMath::Sin(Ang)) * Reach;
					float Z = RefZ;
					Battle->SampleGround(P, RefZ + 600.f, Z);
					BuildingReach.Sight.Add(FVector(P.X, P.Y, Z + 15.f));
				}
			}
			const FLinearColor Color = bEnemy ? FLinearColor(1.f, 0.3f, 0.25f, 0.9f) : F.RangeCircleColor;
			const int32 N = BuildingReach.Sight.Num();
			const float W = FMath::Max(1.f, U(2.5f));
			for (int32 i = 0; i < N; ++i)
			{
				const FVector S0 = Canvas->Project(BuildingReach.Sight[i]);
				const FVector S1 = Canvas->Project(BuildingReach.Sight[(i + 1) % N]);
				if (S0.Z > 0.f && S1.Z > 0.f) { DrawLine(S0.X, S0.Y, S1.X, S1.Y, Color, W); }
			}
		}
		else
		{
			BuildingReach.Sight.Reset();
		}
	}
	// The selected troops nearest the middle of the selection (a big blob of circles reads as nothing).
	TArray<ASRUnit*> Units;
	FVector2D Mid = FVector2D::ZeroVector;
	for (const TWeakObjectPtr<ASRUnit>& U : PC->GetSelection()) { if (U.IsValid() && U->IsActive()) { Units.Add(U.Get()); Mid += U->GetPos2D(); } }
	for (auto It = RangeCircles.CreateIterator(); It; ++It) { if (!It.Key().IsValid() || !Units.Contains(It.Key().Get())) { It.RemoveCurrent(); } }
	if (Units.Num() == 0) { return; }
	Mid /= Units.Num();
	Units.Sort([&Mid](const ASRUnit& A, const ASRUnit& B) { return FVector2D::DistSquared(A.GetPos2D(), Mid) < FVector2D::DistSquared(B.GetPos2D(), Mid); });
	if (Units.Num() > 12) { Units.SetNum(12); }

	// Points hug the ground; they are re-sampled only once the troop has moved a little.
	auto Ring = [Battle](const FVector2D& C, float R, float RefZ, TArray<FVector>& Out)
	{
		const int32 N = FMath::Clamp(FMath::RoundToInt(R / 22.f), 48, 96);
		Out.Reset(N);
		for (int32 i = 0; i < N; ++i)
		{
			const float A = 2.f * PI * i / N;
			const FVector2D P = C + FVector2D(FMath::Cos(A), FMath::Sin(A)) * R;
			float Z = RefZ;
			Battle->SampleGround(P, RefZ + 600.f, Z);
			Out.Add(FVector(P.X, P.Y, Z + 15.f));
		}
	};
	// Several troops' circles merge into one outline: a stretch inside another troop's circle of the same kind is skipped.
	struct FDisc { FVector2D C; float R; };
	TArray<FDisc> SightDiscs, ReachDiscs;
	for (const ASRUnit* Unit : Units)
	{
		SightDiscs.Add({ Unit->GetPos2D(), Unit->Stats().Sight() });
		if (Unit->Stats().bRanged) { ReachDiscs.Add({ Unit->GetPos2D(), Unit->Stats().AttackRange }); }
	}
	auto Covered = [](const TArray<FDisc>& Discs, const FVector2D& P, const FVector2D& Own)
	{
		for (const FDisc& D : Discs)
		{
			if (D.C.Equals(Own, 1.f)) { continue; }
			if (FVector2D::DistSquared(D.C, P) < FMath::Square(D.R - 4.f)) { return true; }
		}
		return false;
	};
	auto Draw = [&](const TArray<FVector>& Pts, const FVector2D& Own, const TArray<FDisc>& Discs, const FLinearColor& Color, bool bDashed, float Width)
	{
		const int32 N = Pts.Num();
		for (int32 i = 0; i < N; ++i)
		{
			if (bDashed && (i & 1)) { continue; }
			const FVector Mid = (Pts[i] + Pts[(i + 1) % N]) * 0.5f;
			if (Covered(Discs, FVector2D(Mid.X, Mid.Y), Own)) { continue; }
			const FVector S0 = Canvas->Project(Pts[i]);
			const FVector S1 = Canvas->Project(Pts[(i + 1) % N]);
			if (S0.Z <= 0.f || S1.Z <= 0.f) { continue; }
			DrawLine(S0.X, S0.Y, S1.X, S1.Y, Color, Width);
		}
	};
	const float W = FMath::Max(1.f, U(2.f));
	for (ASRUnit* Unit : Units)
	{
		FRangeCircle& C = RangeCircles.FindOrAdd(Unit);
		const FVector2D P = Unit->GetPos2D();
		if (FVector2D::DistSquared(P, C.At) > FMath::Square(60.f) || C.Stance != uint8(Unit->GetStance()))   // (a Medic's ring follows its stance)
		{
			C.At = P;
			C.Stance = uint8(Unit->GetStance());
			const FSRUnitStats& S = Unit->Stats();
			Ring(P, S.Sight(), Unit->GetSimPos().Z, C.Sight);
			// the solid ring: a bow's (or a catapult's) reach; a Medic's: how far its heals go
			if (S.bRanged) { Ring(P, S.AttackRange, Unit->GetSimPos().Z, C.Reach); }
			else if (Unit->IsMedic())
			{
				// how far it goes to the wounded on its own (Assertive far, Passive near)
				const float Seek = Unit->GetStance() == ESRStance::Aggressive ? F.MedicSeekRange : (Unit->GetStance() == ESRStance::Defensive ? F.MedicSeekRangePassive : 0.f);
				if (Seek > 0.f) { Ring(P, Seek, Unit->GetSimPos().Z, C.Reach); } else { C.Reach.Reset(); }
			}
			else { C.Reach.Reset(); }
		}
		const bool bEnemy = Unit->GetTeam() == ESRTeam::Enemy;
		Draw(C.Sight, P, SightDiscs, bEnemy ? FLinearColor(1.f, 0.4f, 0.35f, 0.45f) : F.SightCircleColor, true, W);
		if (C.Reach.Num() > 0) { Draw(C.Reach, P, ReachDiscs, F.RangeCircleColor, false, W); }
	}
}

void ASRHUD::DrawRouteLines()
{
	// Dashed ground lines: the patrol route of the selected troops, and a selected barracks' or range's rally point.
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || !PC) { return; }
	auto Ground = [Battle](const FVector2D& P)
	{
		float Z = 0.f;
		Battle->SampleGround(P, 20000.f, Z);
		return FVector(P.X, P.Y, Z + 20.f);
	};
	auto Dashed = [this](const FVector& A, const FVector& B, const FLinearColor& Color)
	{
		const int32 N = 24;
		for (int32 i = 0; i < N; i += 2)
		{
			const FVector S0 = Canvas->Project(FMath::Lerp(A, B, float(i) / N));
			const FVector S1 = Canvas->Project(FMath::Lerp(A, B, float(i + 1) / N));
			if (S0.Z <= 0.f || S1.Z <= 0.f) { continue; }
			DrawLine(S0.X, S0.Y, S1.X, S1.Y, Color, FMath::Max(1.f, U(2.f)));
		}
		for (const FVector& End : { A, B })
		{
			const FVector S = Canvas->Project(End);
			if (S.Z > 0.f) { Fill(S.X - U(4.f), S.Y - U(4.f), U(8.f), U(8.f), Color); }
		}
	};
	// each route once (a group shares one): a patrol's whole loop in orange, a pathway's legs still to walk in blue
	TArray<FVector2D> Drawn;
	for (const TWeakObjectPtr<ASRUnit>& U2 : PC->GetSelection())
	{
		TArray<FVector2D> Points;
		bool bLoop = false;
		int32 Next = 0;
		if (!U2.IsValid() || !Battle->GetRoute(U2.Get(), Points, bLoop, Next) || Points.Num() == 0) { continue; }
		const FVector2D Key(Points.Last().X + Points.Num() * 0.001, Points[0].Y);
		if (Drawn.Contains(Key)) { continue; }
		Drawn.Add(Key);
		if (bLoop)
		{
			const FLinearColor Col(1.f, 0.62f, 0.25f, 0.85f);
			for (int32 k = 0; k < Points.Num(); ++k)
			{
				if (Points.Num() == 2 && k == 1) { break; }   // two points: one line, walked both ways
				Dashed(Ground(Points[k]), Ground(Points[(k + 1) % Points.Num()]), Col);
			}
		}
		else
		{
			const FLinearColor Col(0.55f, 0.8f, 1.f, 0.85f);
			// from the troop to the point it is heading for, then the legs after it
			Dashed(Ground(U2->GetPos2D()), Ground(Points[FMath::Clamp(Next, 0, Points.Num() - 1)]), Col);
			for (int32 k = FMath::Max(Next, 0); k + 1 < Points.Num(); ++k) { Dashed(Ground(Points[k]), Ground(Points[k + 1]), Col); }
		}
	}
	if (const ASRBuilding* Trainer = PC->GetSelectedBuilding(); Trainer && Trainer->IsRecruiter() && Trainer->IsAlive() && Trainer->Team == ESRTeam::Player)
	{
		const FVector Gate = Trainer->GetGatePoint();
		Dashed(Ground(FVector2D(Gate.X, Gate.Y)), Ground(Trainer->GetRallyPoint()), FLinearColor(0.55f, 0.8f, 1.f, 0.85f));
	}
}

void ASRHUD::DrawTrainingBars()
{
	// A building at work shows its progress over the roof even when nothing is selected: training (below), and
	// for your own buildings construction, the castle being raised, and repairs. Several stack upward.
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy) { return; }
	for (const ASRBuilding* Building : Economy->GetBuildings())
	{
		if (!Building || !Building->IsAlive() || Building->Team != ESRTeam::Player || Building->IsHidden()) { continue; }
		struct FRow { ESRIcon Icon; float Frac; FLinearColor Col; FString Label; };
		TArray<FRow, TInlineAllocator<3>> Rows;
		if (Building->IsUnderConstruction())
		{
			const bool bWaiting = Building->NeedsBuilder() && Building->GetBuildersWorking() == 0;
			// the clock: how long until it stands, at the rate it is rising now
			Rows.Add({ ESRIcon::Hammer, Building->GetBuildProgress(), bWaiting ? Refuse : Amber,
				bWaiting ? FString(TEXT("needs a Builder")) : SRStyle::Countdown(Building->GetBuildSecondsLeft()) });
		}
		if (Building->IsUpgrading())
		{
			Rows.Add({ ESRIcon::Crown, Building->GetUpgradeFraction(), GoldBright, FString::Printf(TEXT("level %d  %s"), Building->GetLevel() + 1, *SRStyle::Countdown(Building->GetUpgradeSecondsLeft())) });
		}
		if (!Building->IsUnderConstruction() && Building->GetBuildersWorking() > 0 && Building->NeedsWork())
		{
			Rows.Add({ ESRIcon::Hammer, Building->GetHealthFrac(), Health(Building->GetHealthFrac()), TEXT("repairing") });
		}
		if (Rows.Num() == 0) { continue; }
		const FVector S = Canvas->Project(Building->GetLabelPoint());
		if (S.Z <= 0.f) { continue; }
		const float W = U(110.f), H = U(9.f), IS = U(24.f), Step = U(26.f);
		// above the training bar when the building is also training
		const float Base = S.Y - (Building->GetQueue().Num() > 0 ? Step : 0.f);
		for (int32 r = 0; r < Rows.Num(); ++r)
		{
			const FRow& Row = Rows[r];
			const float X = FMath::RoundToFloat(S.X - W * 0.5f + IS * 0.5f), Y = FMath::RoundToFloat(Base - r * Step);
			Icon(Row.Icon, X - IS - U(5.f), Y + H * 0.5f - IS * 0.5f, IS);
			Meter(X, Y, W, H, Row.Frac, Row.Col);
			Text(Row.Label, X + W + U(6.f), Y - U(5.f), U(14.f), Row.Col == Refuse ? Refuse : Parchment, AlignLeft, Bold);
		}
	}
	for (const ASRBuilding* Building : Economy->GetBuildings())
	{
		if (!Building || Building->GetQueue().Num() == 0) { continue; }
		if (Building->Team == ESRTeam::Enemy)
		{
			// what the enemy trains is only seen up close
			const USRFogSubsystem* Fog = USRFogSubsystem::Get(this);
			if (Building->IsHidden() || (Fog && !Fog->IsVisible(Building->GetFootprintCentre()))) { continue; }
		}
		const FVector S = Canvas->Project(Building->GetLabelPoint());
		if (S.Z <= 0.f) { continue; }
		const bool bEnemy = Building->Team == ESRTeam::Enemy;
		const float W = U(110.f), H = U(9.f), IS = U(26.f);
		const float X = FMath::RoundToFloat(S.X - W * 0.5f + IS * 0.5f), Y = FMath::RoundToFloat(S.Y);
		Icon(SRUnitIcon(Building->GetQueue()[0]), X - IS - U(5.f), Y + H * 0.5f - IS * 0.5f, IS, FLinearColor::White, bEnemy);
		Meter(X, Y, W, H, Building->GetBuildFraction(), GoldBright);
		if (Building->GetQueue().Num() > 1)
		{
			Text(FString::Printf(TEXT("x%d"), Building->GetQueue().Num()), X + W + U(6.f), Y - U(6.f), U(16.f), Parchment, AlignLeft, Bold);
		}
	}
}
