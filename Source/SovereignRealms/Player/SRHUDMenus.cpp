// Copyright Sovereign Realms.
// Main menu, pause menu, victory / defeat screen, and the screens they share: controls, settings, new game, confirm.

#include "Player/SRHUD.h"
#include "Player/SRHUDStyle.h"
#include "Player/SRPlayerController.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRAISubsystem.h"
#include "Battle/SRFogSubsystem.h"
#include "Common/SRAudioSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Common/SRPowerSubsystem.h"
#include "Common/SRUserSettings.h"
#include "Engine/Canvas.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "Kismet/KismetSystemLibrary.h"

using namespace SRStyle;

namespace
{
	struct FControlRow { const TCHAR* Keys; const TCHAR* What; };   // Keys == nullptr: a section heading

	// Every control (ASRPlayerController's header comment is the source of truth).
	const FControlRow ControlsLeft[] = {
		{ nullptr, TEXT("SELECTION") },
		{ TEXT("LMB"), TEXT("Select a troop or a building") },
		{ TEXT("Shift + LMB"), TEXT("Add to / remove from the selection") },
		{ TEXT("LMB drag"), TEXT("Box-select troops") },
		{ TEXT("Double-click"), TEXT("Select all of that type on screen") },
		{ nullptr, TEXT("ORDERS") },
		{ TEXT("RMB"), TEXT("Move in formation / attack an enemy") },
		{ TEXT("A, then LMB"), TEXT("Attack-move: fight what you meet on the way") },
		{ TEXT("S"), TEXT("Stop") },
		{ TEXT("H"), TEXT("Hold ground: fight only what is in reach") },
		{ TEXT("P, then LMB"), TEXT("Patrol between here and there") },
		{ TEXT("P, Shift + LMB"), TEXT("Patrol round several points (each click adds one)") },
		{ TEXT("Shift + RMB"), TEXT("Pathway: add a point; they walk them in order") },
		{ TEXT("F / G"), TEXT("Formation on / off (RMB its button: shape) / stance") },
		{ nullptr, TEXT("CAMERA") },
		{ TEXT("WASD / Arrows"), TEXT("Pan (hold A or S: a tap is the order)") },
		{ TEXT("Screen edge"), TEXT("Pan") },
		{ TEXT("MMB drag"), TEXT("Grab the ground and drag") },
		{ TEXT("Mouse wheel"), TEXT("Zoom") },
		{ TEXT("Trackpad"), TEXT("Two fingers pan, pinch zooms, Ctrl+click = RMB") },
		{ TEXT("Option + scroll"), TEXT("Zoom (trackpad or Magic Mouse)") },
		{ TEXT("Space / Home"), TEXT("Centre on the selection") },
		{ TEXT("Minimap"), TEXT("LMB look there (drag), RMB send troops") },
	};
	const FControlRow ControlsRight[] = {
		{ nullptr, TEXT("PLATOONS") },
		{ TEXT("Ctrl / Cmd / Alt + 1-6"), TEXT("Form a platoon from the selection") },
		{ TEXT("1-6"), TEXT("Select the platoon (twice: go to it)") },
		{ TEXT("Shift + 1-6"), TEXT("Add the selection to the platoon") },
		{ TEXT("Delete"), TEXT("Disband the selected platoon") },
		{ nullptr, TEXT("BUILDING") },
		{ TEXT("B, then 1-6"), TEXT("Build menu (Tab: next tab), pick a building") },
		{ TEXT("LMB / RMB"), TEXT("Place it (Shift: keep placing) / cancel") },
		{ TEXT("Delete"), TEXT("Cancel construction (75% refund)") },
		{ TEXT("Delete  Delete"), TEXT("Demolish a finished building (30% back; press twice)") },
		{ TEXT("Y"), TEXT("Train a Builder at the Citadel (more per castle level)") },
		{ TEXT("RMB on a site"), TEXT("Builders selected: build / repair it") },
		{ TEXT("X"), TEXT("Builders: repair the nearest damaged building") },
		{ TEXT("K  K"), TEXT("Dismiss the selected troops (press twice)") },
		{ TEXT("V, then click"), TEXT("Guard one of your Builders or buildings (or RMB it)") },
		{ TEXT("O"), TEXT("Scouts: roam on their own (attacked: run home)") },
		{ TEXT("U"), TEXT("Upgrade the selected building, else the Citadel") },
		{ TEXT("M"), TEXT("March together (slowest sets the pace) on / off") },
		{ nullptr, TEXT("TROOPS") },
		{ TEXT("Q / E / R / T"), TEXT("Train Shieldbearer / Archer / Rider / Catapult") },
		{ TEXT("J"), TEXT("Train the Scout (Citadel level 3; one at a time)") },
		{ TEXT("N"), TEXT("Train a Medic at the Barracks (heals; never fights)") },
		{ TEXT("RMB on a troop"), TEXT("Medics selected: look after that troop") },
		{ TEXT("RMB"), TEXT("Rally point (Barracks or Range selected)") },
		{ nullptr, TEXT("GAME") },
		{ TEXT("Esc"), TEXT("Cancel, then deselect, then pause") },
		{ TEXT("F1"), TEXT("Show or hide this list") },
	};

	const TCHAR* DifficultyNames[3] = { TEXT("Easy"), TEXT("Normal"), TEXT("Hard") };
	const TCHAR* DifficultyNotes[3] = {
		TEXT("A gentle enemy: a small economy, late, small attacks."),
		TEXT("A fair fight: it attacks when it thinks it can win."),
		TEXT("The enemy strikes early, raids often, adapts fully.") };
}

void ASRHUD::DimScreen(float Alpha)
{
	Fill(0.f, 0.f, View.X, View.Y, FLinearColor(0.008f, 0.012f, 0.025f, Alpha));
}

void ASRHUD::OpenScreen(EScreen NewScreen)
{
	if (Screen == EScreen::Settings && bSettingsDirty)
	{
		// leaving Settings: keep what was changed
		USRUserSettings::Get()->CaptureAndSave();
		bSettingsDirty = false;
	}
	Screen = NewScreen;
	bActAfterSave = false;
	if (NewScreen == EScreen::Settings) { PendingScale = USRFeelSettings::Get().HUDScale; }
	if (NewScreen == EScreen::NewGame)
	{
		// as things stand: the difficulty last played, the map being looked at
		MenuDifficulty = USRFeelSettings::Get().AIDifficulty;
		if (const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this)) { MenuMap = Flow->GetCurrentMapId(); }
	}
}

void ASRHUD::AskConfirm(EConfirm What)
{
	Confirm = What;
	OpenScreen(EScreen::Confirm);
}

bool ASRHUD::OnEscape()
{
	const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	const ESRGameState Current = Flow ? Flow->GetState() : ESRGameState::Playing;
	if (bLegend) { bLegend = false; return true; }
	if (Current == ESRGameState::Playing) { return false; }
	if (Screen != EScreen::None) { OpenScreen(EScreen::None); return true; }
	if (Current == ESRGameState::Paused) { USRGameFlowSubsystem::Get(this)->SetPaused(false); }
	return true;
}

void ASRHUD::ToggleLegend()
{
	const USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	const ESRGameState Current = Flow ? Flow->GetState() : ESRGameState::Playing;
	if (Current == ESRGameState::Playing) { bLegend = !bLegend; }
	else if (Current != ESRGameState::Ended) { OpenScreen(Screen == EScreen::Controls ? EScreen::None : EScreen::Controls); }
}

// ---------------------------------------------------------------------------- main menu

void ASRHUD::DrawMainMenu()
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	const float In = FMath::Clamp(Flow->GetStateTime() / 0.5f, 0.f, 1.f);
	// The picture is the film of the battle, looping (DrawMenuFilm), or the live realm while it is not up. A soft
	// vignette (top, bottom, and a light veil over all of it) keeps the lettering readable over fire and bright water,
	// and the left third is darkened (in soft steps) to carry the title and the menu.
	if (DrawMenuFilm(1.f))
	{
		Fill(0.f, 0.f, View.X, View.Y, FLinearColor(0.008f, 0.012f, 0.026f, 0.16f));
		const int32 Rows = 18;
		const float RowH = FMath::CeilToFloat(View.Y * 0.2f / Rows);
		for (int32 i = 0; i < Rows; ++i)
		{
			const float A0 = 0.5f * FMath::Pow(1.f - float(i) / Rows, 1.8f);
			Fill(0.f, i * RowH, View.X, RowH, FLinearColor(0.008f, 0.012f, 0.026f, A0));
			Fill(0.f, View.Y - (i + 1) * RowH, View.X, RowH, FLinearColor(0.008f, 0.012f, 0.026f, A0));
		}
	}
	const int32 Bands = 28;
	const float BandW = FMath::CeilToFloat(View.X * 0.62f / Bands);
	for (int32 i = 0; i < Bands; ++i)
	{
		const float T = 1.f - float(i) / Bands;
		Fill(i * BandW, 0.f, BandW, View.Y, FLinearColor(0.008f, 0.012f, 0.026f, 0.86f * FMath::Pow(T, 1.6f) * In));
	}

	const float X = U(96.f);
	float Y = FMath::RoundToFloat(View.Y * 0.15f);
	// crest, title lettering, rule, tag line
	Icon(ESRIcon::Crown, X, Y, U(64.f), FLinearColor(1.f, 1.f, 1.f, In));
	Y += U(74.f);
	const float TitleW = U(640.f), TitleH = FMath::RoundToFloat(TitleW * 64.f / 508.f);
	if (TitleArt) { DrawTexture(TitleArt, X - U(5.f), Y, TitleW, TitleH, 0.f, 0.f, 1.f, 1.f, FLinearColor(1.f, 1.f, 1.f, In), BLEND_Translucent); }
	else { Text(TEXT("SOVEREIGN REALMS"), X, Y, U(64.f), GoldBright, AlignLeft, Black, U(4.f)); }
	Y += TitleH + U(16.f);
	Rule(X, Y, TitleW - U(10.f), In);
	Y += U(14.f);
	Text(TEXT("RAISE A KINGDOM   ·   HOLD THE LINE"), X, Y, U(17.f), A(Parchment, 0.9f * In), AlignLeft, Bold, U(3.f));
	Y += U(64.f);

	// entries
	const float BW = U(340.f), BH = U(56.f), Gap = U(12.f);
	// a saved game: CONTINUE comes first (the newest that can be loaded; on whichever map it was played)
	const FString Latest = Flow->LatestSlot();
	if (!Latest.IsEmpty())
	{
		const FBox2D Box(FVector2D(X, Y), FVector2D(X + BW, Y + BH));
		if (MenuButton(Box, SRId::Menu + 8, TEXT("CONTINUE"), true, false)) { Flow->LoadMatch(Latest); }
		Text(Flow->DescribeSave(Latest), X + U(4.f), Y + BH + U(3.f), U(13.f), A(Dim, In));
		Y += BH + Gap + U(16.f);
	}
	if (Flow->GetSaves().Num() > 0)
	{
		// every saved game, to pick one (or delete some: the ones from the old map can only be deleted)
		const FBox2D LoadBox(FVector2D(X, Y), FVector2D(X + BW, Y + BH));
		const bool bOpen = Screen == EScreen::Saves;
		if (MenuButton(LoadBox, SRId::Menu + 9, TEXT("LOAD GAME"), true, bOpen)) { if (bOpen) { OpenScreen(EScreen::None); } else { OpenSaves(false); } }
		Y += BH + Gap;
	}
	const TCHAR* Labels[4] = { TEXT("NEW GAME"), TEXT("HOW TO PLAY"), TEXT("SETTINGS"), TEXT("QUIT") };
	const EScreen Opens[4] = { EScreen::NewGame, EScreen::Controls, EScreen::Settings, EScreen::Confirm };
	for (int32 i = 0; i < 4; ++i)
	{
		const FBox2D Box(FVector2D(X, Y), FVector2D(X + BW, Y + BH));
		const bool bOpen = Screen == Opens[i] && Screen != EScreen::None;
		if (MenuButton(Box, SRId::Menu + i, Labels[i], true, bOpen))
		{
			if (bOpen) { OpenScreen(EScreen::None); }
			else if (i == 3) { AskConfirm(EConfirm::Quit); }
			else { OpenScreen(Opens[i]); }
		}
		Y += BH + Gap;
	}
	Text(TEXT("F1  controls      Esc  back"), X, View.Y - U(48.f), U(14.f), A(Dim, 0.9f * In));

	if (Screen != EScreen::None) { DrawScreen(FMath::Max(View.X * 0.64f, X + BW + U(60.f) + U(330.f))); }
}

// ---------------------------------------------------------------------------- pause menu

void ASRHUD::DrawPauseMenu()
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	const float In = FMath::Clamp(Flow->GetStateTime() / 0.15f, 0.f, 1.f);
	DimScreen(0.5f * In);
	if (Screen != EScreen::None) { DrawScreen(View.X * 0.5f); return; }

	const float W = U(420.f), BH = U(54.f), Gap = U(10.f);
	const float H = U(104.f) + 7.f * (BH + Gap) + U(56.f);
	const float X = FMath::RoundToFloat((View.X - W) * 0.5f), Y = FMath::RoundToFloat((View.Y - H) * 0.5f - (1.f - In) * U(12.f));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(TEXT("PAUSED"), X + W * 0.5f, Y + U(26.f), U(32.f), GoldBright, AlignCentre, Bold, U(6.f));
	Rule(X + U(40.f), Y + U(78.f), W - U(80.f));
	const FString Latest = Flow->LatestSlot();
	const TCHAR* Labels[7] = { TEXT("RESUME"), TEXT("SAVE GAME"), TEXT("LOAD GAME"), TEXT("RESTART"), TEXT("CONTROLS"), TEXT("SETTINGS"), TEXT("QUIT TO MAIN MENU") };
	float BY = Y + U(104.f);
	for (int32 i = 0; i < 7; ++i, BY += BH + Gap)
	{
		const FBox2D Box(FVector2D(X + U(34.f), BY), FVector2D(X + W - U(34.f), BY + BH));
		const bool bEnabled = i != 2 || Flow->GetSaves().Num() > 0;
		if (!MenuButton(Box, SRId::Menu + 10 + i, Labels[i], bEnabled)) { continue; }
		switch (i)
		{
		case 0: Flow->SetPaused(false); break;
		case 1: OpenSaves(true); break;
		case 2: OpenSaves(false); break;
		case 3: AskConfirm(EConfirm::Restart); break;
		case 4: OpenScreen(EScreen::Controls); break;
		case 5: OpenScreen(EScreen::Settings); break;
		default: AskConfirm(EConfirm::MainMenu); break;
		}
	}
	// what the save / load buttons did, or what LOAD would bring back
	const bool bFresh = FPlatformTime::Seconds() - Flow->GetSaveMessageTime() < 4.0;
	const int32 NumSaves = Flow->GetSaves().Num();
	// (two short lines: one long one ran out past the panel's edges)
	// (Latest is empty when every save is from the old map: nothing LOAD could bring back)
	const FString Note = bFresh ? Flow->GetSaveMessage() : (NumSaves == 0 ? FString(TEXT("No saved game yet.")) : FString::Printf(TEXT("%d saved game%s  ·  %s"),
		NumSaves, NumSaves == 1 ? TEXT("") : TEXT("s"), Latest.IsEmpty() ? TEXT("from the old map") : (Latest == USRGameFlowSubsystem::AutoSlot() ? TEXT("newest: the autosave") : TEXT("newest: your save"))));
	Text(Note, X + W * 0.5f, BY - U(4.f), U(14.f), bFresh ? GoldBright : Dim, AlignCentre);
	if (!bFresh && !Latest.IsEmpty()) { Text(Flow->DescribeSave(Latest), X + W * 0.5f, BY + U(14.f), U(13.f), Dim, AlignCentre); }
}

// ---------------------------------------------------------------------------- victory / defeat

void ASRHUD::DrawEndScreen()
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }
	const bool bWon = Battle->GetResult() == ESRBattleResult::PlayerWon;
	const float In = FMath::Clamp(Flow->GetStateTime() / 0.35f, 0.f, 1.f);
	DimScreen(0.5f * In);

	const FSRMatchStats& S = Battle->GetStats();
	const int32 Me = int32(ESRTeam::Player), Foe = int32(ESRTeam::Enemy);
	const TPair<const TCHAR*, FString> Rows[] = {
		{ TEXT("Time"), FString::Printf(TEXT("%d:%02d"), FMath::FloorToInt(Battle->GetBattleClock()) / 60, FMath::FloorToInt(Battle->GetBattleClock()) % 60) },
		{ TEXT("Difficulty"), DifficultyNames[FMath::Clamp(USRFeelSettings::Get().AIDifficulty, 0, 2)] },
		{ TEXT("Troops recruited"), FString::FromInt(S.Recruited[Me]) },
		{ TEXT("Troops lost"), FString::FromInt(S.TroopsLost[Me]) },
		{ TEXT("Enemies slain"), FString::FromInt(S.TroopsLost[Foe]) },
		{ TEXT("Buildings raised"), FString::FromInt(S.BuildingsBuilt[Me]) },
		{ TEXT("Buildings lost"), FString::FromInt(S.BuildingsLost[Me]) },
		{ TEXT("Enemy buildings razed"), FString::FromInt(S.BuildingsLost[Foe]) },
	};
	const int32 NumRows = UE_ARRAY_COUNT(Rows);
	const float W = U(560.f), RowH = U(30.f);
	const float H = U(170.f) + NumRows * RowH + U(100.f);
	const float X = FMath::RoundToFloat((View.X - W) * 0.5f), Y = FMath::RoundToFloat((View.Y - H) * 0.5f - (1.f - In) * U(24.f));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true, In);
	const FLinearColor Accent = bWon ? GoldBright : FLinearColor(0.95f, 0.30f, 0.22f, 1.f);
	Icon(bWon ? ESRIcon::Crown : ESRIcon::AlertLost, X + W * 0.5f - U(24.f), Y + U(20.f), U(48.f), FLinearColor(1.f, 1.f, 1.f, In));
	Text(bWon ? TEXT("VICTORY") : TEXT("DEFEAT"), X + W * 0.5f, Y + U(66.f), U(54.f), A(Accent, In), AlignCentre, Black, U(10.f));
	Text(bWon ? TEXT("The enemy's citadel has fallen.") : TEXT("Your citadel has fallen."), X + W * 0.5f, Y + U(132.f), U(16.f), A(Parchment, In), AlignCentre);
	Rule(X + U(50.f), Y + U(162.f), W - U(100.f), In);
	float RY = Y + U(176.f);
	for (int32 i = 0; i < NumRows; ++i, RY += RowH)
	{
		if (i & 1) { Fill(X + U(40.f), RY, W - U(80.f), RowH, FLinearColor(1.f, 1.f, 1.f, 0.03f * In)); }
		const FBox2D Row(FVector2D(X + U(56.f), RY), FVector2D(X + W - U(56.f), RY + RowH));
		TextIn(Row, Rows[i].Key, U(16.f), A(Dim, In), AlignLeft);
		TextIn(Row, Rows[i].Value, U(17.f), A(Parchment, In), AlignRight, Bold);
	}
	const float BW = (W - U(80.f) - U(14.f)) * 0.5f, BY = Y + H - U(82.f);
	if (MenuButton(FBox2D(FVector2D(X + U(40.f), BY), FVector2D(X + U(40.f) + BW, BY + U(54.f))), SRId::Menu + 20, TEXT("PLAY AGAIN"))) { Flow->StartMatch(); }
	if (MenuButton(FBox2D(FVector2D(X + W - U(40.f) - BW, BY), FVector2D(X + W - U(40.f), BY + U(54.f))), SRId::Menu + 21, TEXT("MAIN MENU"))) { Flow->EnterMainMenu(); }
}

// ---------------------------------------------------------------------------- shared screens

void ASRHUD::DrawLegendOverlay()
{
	DimScreen(0.5f);
	DrawControlsPanel(View.X * 0.5f, true);
}

void ASRHUD::DrawScreen(float CentreX)
{
	switch (Screen)
	{
	case EScreen::NewGame: DrawNewGamePanel(CentreX); break;
	case EScreen::Controls: DrawControlsPanel(CentreX, true); break;
	case EScreen::Settings: DrawSettingsPanel(CentreX); break;
	case EScreen::Confirm: DrawConfirmPanel(CentreX); break;
	case EScreen::Saves: DrawSavesPanel(CentreX); break;
	default: break;
	}
}

void ASRHUD::DrawControlsPanel(float CentreX, bool bCloseButton)
{
	const int32 NL = UE_ARRAY_COUNT(ControlsLeft), NR = UE_ARRAY_COUNT(ControlsRight);
	const float RowH = U(27.f), ColW = U(470.f), KeyW = U(168.f);
	const float W = 2.f * ColW + U(70.f);
	const float H = U(92.f) + FMath::Max(NL, NR) * RowH + (bCloseButton ? U(84.f) : U(24.f));
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat(FMath::Max((View.Y - H) * 0.5f, U(8.f)));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(TEXT("CONTROLS"), X + W * 0.5f, Y + U(22.f), U(26.f), GoldBright, AlignCentre, Bold, U(5.f));
	Rule(X + U(40.f), Y + U(66.f), W - U(80.f));
	for (int32 Col = 0; Col < 2; ++Col)
	{
		const FControlRow* Rows = Col == 0 ? ControlsLeft : ControlsRight;
		const int32 Num = Col == 0 ? NL : NR;
		const float CX = X + U(30.f) + Col * (ColW + U(10.f));
		float RY = Y + U(84.f);
		for (int32 i = 0; i < Num; ++i, RY += RowH)
		{
			const FBox2D Row(FVector2D(CX, RY), FVector2D(CX + ColW, RY + RowH));
			if (!Rows[i].Keys)
			{
				TextIn(FBox2D(Row.Min + FVector2D(0.f, U(4.f)), Row.Max), Rows[i].What, U(14.f), Gold, AlignLeft, Bold, U(2.f));
				Fill(CX + TextSize(Rows[i].What, U(14.f), Bold, U(2.f)).X + U(10.f), RY + RowH * 0.5f + U(3.f), ColW - TextSize(Rows[i].What, U(14.f), Bold, U(2.f)).X - U(10.f), FMath::Max(1.f, U(1.f)), A(Bronze, 0.8f));
				continue;
			}
			TextIn(FBox2D(Row.Min, FVector2D(CX + KeyW, Row.Max.Y)), Rows[i].Keys, U(15.f), GoldBright, AlignRight, Bold);
			TextIn(FBox2D(FVector2D(CX + KeyW + U(14.f), RY), Row.Max), Rows[i].What, U(15.f), Parchment, AlignLeft);
		}
	}
	if (bCloseButton)
	{
		const float BW = U(220.f);
		if (MenuButton(FBox2D(FVector2D(X + (W - BW) * 0.5f, Y + H - U(72.f)), FVector2D(X + (W + BW) * 0.5f, Y + H - U(22.f))), SRId::LegendClose, TEXT("CLOSE")))
		{
			if (bLegend) { bLegend = false; }
			else { OpenScreen(EScreen::None); }
		}
	}
}

void ASRHUD::DrawSettingsPanel(float CentreX)
{
	USRFeelSettings* F = GetMutableDefault<USRFeelSettings>();
	const float W = U(600.f), RowH = U(46.f);
	const float H = U(92.f) + 14.f * RowH + U(96.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat(FMath::Max((View.Y - H) * 0.5f, U(8.f)));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(TEXT("SETTINGS"), X + W * 0.5f, Y + U(22.f), U(26.f), GoldBright, AlignCentre, Bold, U(5.f));
	Rule(X + U(40.f), Y + U(66.f), W - U(80.f));

	const float LX = X + U(40.f), SX = X + U(250.f), SW = U(230.f), VX = X + W - U(40.f);
	float RY = Y + U(88.f);
	auto Label = [&](const TCHAR* Name) { TextIn(FBox2D(FVector2D(LX, RY), FVector2D(SX, RY + RowH)), Name, U(17.f), Parchment, AlignLeft); };
	auto Value = [&](const FString& String) { TextIn(FBox2D(FVector2D(SX + SW, RY), FVector2D(VX, RY + RowH)), String, U(16.f), GoldBright, AlignRight, Bold); };

	struct FVolume { const TCHAR* Name; float* Value; };
	const FVolume Volumes[5] = { { TEXT("Master volume"), &F->MasterVolume }, { TEXT("Effects"), &F->EffectsVolume }, { TEXT("Interface"), &F->UIVolume },
		{ TEXT("Ambience"), &F->AmbientVolume }, { TEXT("Music"), &F->MusicVolume } };
	for (int32 i = 0; i < 5; ++i, RY += RowH)
	{
		Label(Volumes[i].Name);
		if (Slider(FBox2D(FVector2D(SX, RY + U(6.f)), FVector2D(SX + SW, RY + RowH - U(6.f))), SRId::Setting + i, *Volumes[i].Value, 0.f, 1.f))
		{
			bSettingsDirty = true;
			if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->RefreshLoopVolumes(); }
		}
		Value(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(*Volumes[i].Value * 100.f)));
	}

	// Interface scale: applied when the slider is let go, so the panel does not resize under the cursor mid-drag.
	Label(TEXT("Interface scale"));
	Slider(FBox2D(FVector2D(SX, RY + U(6.f)), FVector2D(SX + SW, RY + RowH - U(6.f))), SRId::Setting + 5, PendingScale, 0.8f, 1.4f);
	PendingScale = FMath::RoundToFloat(PendingScale * 20.f) / 20.f;
	if (ActiveId != SRId::Setting + 5 && !FMath::IsNearlyEqual(PendingScale, F->HUDScale))
	{
		F->HUDScale = PendingScale;
		bSettingsDirty = true;
	}
	Value(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(PendingScale * 100.f)));
	RY += RowH;

	struct FSwitch { const TCHAR* Name; bool* Value; };
	const FSwitch Switches[3] = { { TEXT("Pan at the screen edge"), &F->bEdgePan }, { TEXT("WASD pans the camera"), &F->bWASDPansCamera },
		{ TEXT("Fog of war"), &F->bFogOfWar } };
	const uint32 SwitchIds[3] = { SRId::Setting + 6, SRId::Setting + 7, SRId::Setting + 10 };
	for (int32 i = 0; i < 3; ++i, RY += RowH)
	{
		Label(Switches[i].Name);
		if (Toggle(FBox2D(FVector2D(SX, RY + U(7.f)), FVector2D(SX + U(32.f), RY + U(39.f))), SwitchIds[i], *Switches[i].Value))
		{
			bSettingsDirty = true;
			// the fog follows at once (whatever an sr.Fog test command last said)
			if (Switches[i].Value == &F->bFogOfWar) { if (USRFogSubsystem* Fog = USRFogSubsystem::Get(this)) { Fog->SetEnabled(true); } }
		}
		TextIn(FBox2D(FVector2D(SX + U(44.f), RY), FVector2D(VX, RY + RowH)), *Switches[i].Value ? TEXT("On") : TEXT("Off"), U(16.f), *Switches[i].Value ? GoldBright : Dim, AlignLeft, Bold);
	}

	// Power (USRPowerSubsystem): each click steps to the next choice.
	auto Choice = [&](uint32 Id, const FString& Current)
	{
		const FBox2D Box(FVector2D(SX, RY + U(6.f)), FVector2D(SX + SW, RY + RowH - U(6.f)));
		const FBtn B = Button(Box, Id);
		ButtonFrame(Box, B, true);
		TextIn(FBox2D(Box.Min + FVector2D(0.f, B.bHeld ? U(1.f) : 0.f), Box.Max), Current, U(16.f), FMath::Lerp(Parchment, GoldBright, B.Hot), AlignCentre, Bold);
		if (B.bClicked) { Click(); bSettingsDirty = true; }
		return B.bClicked;
	};
	const int32 Caps[4] = { 30, 60, 120, 0 };
	int32 CapIndex = 1;
	for (int32 i = 0; i < 4; ++i) { if (Caps[i] == F->FrameRateCap) { CapIndex = i; } }
	Label(TEXT("Frame rate limit"));
	if (Choice(SRId::Setting + 8, Caps[CapIndex] > 0 ? FString::Printf(TEXT("%d fps"), Caps[CapIndex]) : FString(TEXT("Unlimited")))) { F->FrameRateCap = Caps[(CapIndex + 1) % 4]; }
	RY += RowH;

	static const TCHAR* AngleNames[3] = { TEXT("Classic (steep)"), TEXT("Low"), TEXT("Battlefield (shallow)") };
	Label(TEXT("Camera angle"));
	if (Choice(SRId::Setting + 12, AngleNames[FMath::Clamp(F->CameraAngle, 0, 2)])) { F->CameraAngle = (FMath::Clamp(F->CameraAngle, 0, 2) + 1) % 3; }
	RY += RowH;

	Label(TEXT("Trackpad scroll"));
	if (Choice(SRId::Setting + 11, F->bTrackpadScrollZooms ? FString(TEXT("Zooms")) : FString(TEXT("Pans the map")))) { F->bTrackpadScrollZooms = !F->bTrackpadScrollZooms; }
	RY += RowH;

	static const TCHAR* SaverNames[3] = { TEXT("Off"), TEXT("On battery power"), TEXT("Always") };
	Label(TEXT("Battery saver"));
	if (Choice(SRId::Setting + 9, SaverNames[FMath::Clamp(F->BatterySaver, 0, 2)])) { F->BatterySaver = (FMath::Clamp(F->BatterySaver, 0, 2) + 1) % 3; }
	if (const USRPowerSubsystem* Power = USRPowerSubsystem::Get(this); Power && Power->IsSaverActive()) { Value(TEXT("Active")); }
	RY += RowH;

	// Sandbox: a testing ground on the chosen map (both kingdoms built up, armies of every kind, an enemy that never attacks)
	Label(TEXT("Sandbox (testing)"));
	if (Choice(SRId::Setting + 13, FString(TEXT("Start sandbox")))) { USRGameFlowSubsystem::Get(this)->StartMatch(MenuDifficulty, MenuMap, true); }
	RY += RowH;

	const float BW = U(220.f);
	if (MenuButton(FBox2D(FVector2D(X + (W - BW) * 0.5f, Y + H - U(74.f)), FVector2D(X + (W + BW) * 0.5f, Y + H - U(24.f))), SRId::Screen, TEXT("DONE"))) { OpenScreen(EScreen::None); }
}

void ASRHUD::DrawNewGamePanel(float CentreX)
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	const TArray<FSRMapEntry>& Maps = USRFeelSettings::Get().Maps;
	// the maps side by side above the difficulties (wide enough that two notes fit in two or three lines each)
	const float W = U(680.f), RowH = U(76.f), MapH = Maps.Num() > 0 ? U(104.f) : 0.f;
	const float H = U(92.f) + (MapH > 0.f ? MapH + U(16.f) : 0.f) + 3.f * (RowH + U(10.f)) + U(52.f) + U(98.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat(FMath::Max((View.Y - H) * 0.5f, U(8.f)));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(TEXT("NEW GAME"), X + W * 0.5f, Y + U(22.f), U(26.f), GoldBright, AlignCentre, Bold, U(5.f));
	Rule(X + U(40.f), Y + U(66.f), W - U(80.f));
	float RY = Y + U(88.f);
	if (MapH > 0.f)
	{
		const float Gap = U(12.f), MW = FMath::FloorToFloat((W - U(80.f) - Gap * (Maps.Num() - 1)) / Maps.Num());
		for (int32 i = 0; i < Maps.Num() && i < 8; ++i)
		{
			const float MX = X + U(40.f) + i * (MW + Gap);
			const FBox2D Box(FVector2D(MX, RY), FVector2D(MX + MW, RY + MapH));
			// (a map whose level has not been built yet is shown, but cannot be chosen)
			const bool bThere = Flow->IsMapAvailable(Maps[i].Id);
			const FBtn B = Button(Box, SRId::Screen + 11 + i, bThere);
			const bool bChosen = MenuMap == Maps[i].Id;
			ButtonFrame(Box, B, bThere, bChosen);
			const float Pad = U(14.f);
			Text(Maps[i].Name, Box.Min.X + Pad, Box.Min.Y + U(11.f), U(18.f), bChosen ? GoldBright : (bThere ? Parchment : Dim), AlignLeft, Bold, U(1.f));
			if (bChosen) { Icon(ESRIcon::Check, Box.Max.X - U(34.f), Box.Min.Y + U(9.f), U(24.f)); }
			// the note, wrapped to the button: up to three lines
			TArray<FString> Words;
			(bThere ? Maps[i].Note : FString(TEXT("Not in this game yet."))).ParseIntoArray(Words, TEXT(" "));
			FString Line;
			float LY = Box.Min.Y + U(39.f);
			int32 LinesLeft = 3;
			for (int32 w = 0; w < Words.Num() && LinesLeft > 0; ++w)
			{
				const FString Longer = Line.IsEmpty() ? Words[w] : Line + TEXT(" ") + Words[w];
				if (!Line.IsEmpty() && TextSize(Longer, U(13.f)).X > MW - 2.f * Pad)
				{
					Text(Line, Box.Min.X + Pad, LY, U(13.f), Dim);
					LY += U(18.f);
					--LinesLeft;
					Line = Words[w];
				}
				else { Line = Longer; }
			}
			if (LinesLeft > 0) { Text(Line, Box.Min.X + Pad, LY, U(13.f), Dim); }
			if (B.bClicked) { Click(); MenuMap = Maps[i].Id; }
		}
		RY += MapH + U(16.f);
	}
	for (int32 i = 0; i < 3; ++i, RY += RowH + U(10.f))
	{
		const FBox2D Box(FVector2D(X + U(40.f), RY), FVector2D(X + W - U(40.f), RY + RowH));
		const FBtn B = Button(Box, SRId::Screen + 1 + i);
		const bool bChosen = MenuDifficulty == i;
		ButtonFrame(Box, B, true, bChosen);
		static const ESRIcon Icons[3] = { ESRIcon::StanceDefensive, ESRIcon::Swords, ESRIcon::AlertAttack };
		Icon(Icons[i], Box.Min.X + U(18.f), Box.Min.Y + U(18.f), U(40.f));
		Text(DifficultyNames[i], Box.Min.X + U(76.f), Box.Min.Y + U(12.f), U(22.f), bChosen ? GoldBright : Parchment, AlignLeft, Bold);
		Text(DifficultyNotes[i], Box.Min.X + U(76.f), Box.Min.Y + U(43.f), U(15.f), Dim);
		if (bChosen) { Icon(ESRIcon::Check, Box.Max.X - U(46.f), Box.Min.Y + U(24.f), U(28.f)); }
		if (B.bClicked) { Click(); MenuDifficulty = i; }
	}
	{
		// Sandbox: a testing ground (both kingdoms built up, armies of every kind, an enemy that never attacks)
		const FBox2D Box(FVector2D(X + U(40.f), RY), FVector2D(X + W - U(40.f), RY + U(42.f)));
		const FBtn B = Button(Box, SRId::Screen + 50);
		ButtonFrame(Box, B, true, bMenuSandbox);
		Text(TEXT("Sandbox"), Box.Min.X + U(18.f), Box.Min.Y + U(10.f), U(18.f), bMenuSandbox ? GoldBright : Parchment, AlignLeft, Bold);
		Text(TEXT("both kingdoms built up, armies of every kind, the enemy never attacks"), Box.Min.X + U(120.f), Box.Min.Y + U(13.f), U(14.f), Dim);
		if (bMenuSandbox) { Icon(ESRIcon::Check, Box.Max.X - U(40.f), Box.Min.Y + U(9.f), U(24.f)); }
		if (B.bClicked) { Click(); bMenuSandbox = !bMenuSandbox; }
	}
	const float BW = (W - U(80.f) - U(14.f)) * 0.5f, BY = Y + H - U(78.f);
	if (MenuButton(FBox2D(FVector2D(X + U(40.f), BY), FVector2D(X + U(40.f) + BW, BY + U(54.f))), SRId::Screen + 5, TEXT("BACK"))) { OpenScreen(EScreen::None); }
	if (MenuButton(FBox2D(FVector2D(X + W - U(40.f) - BW, BY), FVector2D(X + W - U(40.f), BY + U(54.f))), SRId::Screen + 6, TEXT("BEGIN"), true, true)) { Flow->StartMatch(MenuDifficulty, MenuMap, bMenuSandbox); }
}

void ASRHUD::DrawSavesPanel(float CentreX)
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	const TArray<FSRSaveInfo>& Saves = Flow->GetSaves();
	const double RealNow = FPlatformTime::Seconds();
	if (RealNow - PendingDeleteTime > 4.0) { PendingDelete.Reset(); }
	if (RealNow - PendingOverwriteTime > 4.0) { PendingOverwrite.Reset(); }
	// the player's three saved games and the autosave fit without paging (older installs may hold more: they page)
	const int32 Rows = USRGameFlowSubsystem::MaxPlayerSaves + 1;
	const int32 MaxScroll = FMath::Max(0, Saves.Num() - Rows);
	SavesScroll = FMath::Clamp(SavesScroll, 0, MaxScroll);
	const int32 Mine = Flow->CountPlayerSaves();
	const bool bRoom = Flow->CanAddSave();

	const float W = U(860.f), RowH = U(58.f), Pad = U(30.f);   // (wide enough for the save's line, which names its map, beside the two buttons)
	const float TopH = U(92.f) + (bSavesToSave ? U(66.f) : 0.f);
	const float H = TopH + Rows * RowH + U(96.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat(FMath::Max((View.Y - H) * 0.5f, U(8.f)));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	static const TCHAR* ThenTitles[3] = { TEXT("SAVE, THEN RESTART"), TEXT("SAVE, THEN QUIT"), TEXT("SAVE, THEN QUIT") };
	Text(!bSavesToSave ? TEXT("LOAD GAME") : (bActAfterSave ? ThenTitles[int32(Confirm)] : TEXT("SAVE GAME")), X + W * 0.5f, Y + U(22.f), U(26.f), GoldBright, AlignCentre, Bold, U(5.f));
	Text(FString::Printf(TEXT("%d of %d slots used"), FMath::Min(Mine, USRGameFlowSubsystem::MaxPlayerSaves), USRGameFlowSubsystem::MaxPlayerSaves), X + W - Pad, Y + U(30.f), U(13.f), Dim, AlignRight);
	Rule(X + U(40.f), Y + U(66.f), W - U(80.f));
	float RY = Y + U(84.f);
	bool bSaved = false;
	if (bSavesToSave)
	{
		// a new save never touches the old ones; with every slot in use the next save goes over one of them
		const FString Label = bRoom ? FString::Printf(TEXT("NEW SAVE   ·   SLOT %d OF %d"), Mine + 1, USRGameFlowSubsystem::MaxPlayerSaves)
			: FString::Printf(TEXT("ALL %d SLOTS IN USE   ·   OVERWRITE ONE BELOW"), USRGameFlowSubsystem::MaxPlayerSaves);
		if (MenuButton(FBox2D(FVector2D(X + Pad, RY), FVector2D(X + W - Pad, RY + U(52.f))), SRId::Screen + 20, Label, bRoom))
		{
			bSaved = !Flow->SaveNewMatch().IsEmpty();
			SavesScroll = 0;
		}
		RY += U(66.f);
	}
	if (Saves.Num() == 0)
	{
		Text(TEXT("No saved games yet."), X + W * 0.5f, RY + U(20.f), U(17.f), Dim, AlignCentre);
	}
	FString ToLoad, ToSaveOver, ToDelete;
	for (int32 r = 0; r < Rows && SavesScroll + r < Saves.Num(); ++r)
	{
		const FSRSaveInfo& Info = Saves[SavesScroll + r];
		const float Y0 = RY + r * RowH;
		const bool bThisMatch = !Info.bAuto && Info.Slot == Flow->GetActiveSlot();
		Fill(X + Pad, Y0 + U(2.f), W - 2.f * Pad, RowH - U(6.f), FLinearColor(0.f, 0.f, 0.f, r % 2 == 0 ? 0.22f : 0.12f));
		Text(Info.bAuto ? TEXT("Autosave") : (bThisMatch ? TEXT("Saved game   ·   this match") : TEXT("Saved game")), X + Pad + U(14.f), Y0 + U(7.f), U(16.f), Info.bAuto ? Gold : GoldBright, AlignLeft, Bold);
		Text(Info.Line, X + Pad + U(14.f), Y0 + U(29.f), U(14.f), Info.bOldMap ? Dim : Parchment);
		// right: load (or save over it), then delete
		const float BW = U(156.f), BH2 = U(40.f), BY = Y0 + (RowH - U(6.f) - BH2) * 0.5f + U(2.f);
		const float DX = X + W - Pad - U(8.f) - BW, AX = DX - U(8.f) - BW;
		const bool bAskDelete = PendingDelete == Info.Slot;
		const bool bAskOver = PendingOverwrite == Info.Slot;
		if (bSavesToSave)
		{
			// over this match's own save at once; over another game's only on a second click (it cannot be undone)
			if (!Info.bAuto && MenuButton(FBox2D(FVector2D(AX, BY), FVector2D(AX + BW, BY + BH2)), SRId::Screen + 24 + r * 2, bAskOver ? TEXT("SURE?") : TEXT("OVERWRITE"), true, bAskOver))
			{
				if (bThisMatch || bAskOver) { ToSaveOver = Info.Slot; }
				else { PendingOverwrite = Info.Slot; PendingOverwriteTime = RealNow; }
			}
		}
		// (a save from the old map is listed, and can be deleted, but not loaded)
		else if (MenuButton(FBox2D(FVector2D(AX, BY), FVector2D(AX + BW, BY + BH2)), SRId::Screen + 24 + r * 2, TEXT("LOAD"), !Info.bOldMap)) { ToLoad = Info.Slot; }
		if (MenuButton(FBox2D(FVector2D(DX, BY), FVector2D(DX + BW, BY + BH2)), SRId::Screen + 25 + r * 2, bAskDelete ? TEXT("SURE?") : TEXT("DELETE"), true, bAskDelete))
		{
			if (bAskDelete) { ToDelete = Info.Slot; }
			else { PendingDelete = Info.Slot; PendingDeleteTime = RealNow; }
		}
	}
	// more than fit: page through them
	const float FY = RY + Rows * RowH + U(14.f);
	if (MaxScroll > 0)
	{
		if (MenuButton(FBox2D(FVector2D(X + Pad, FY), FVector2D(X + Pad + U(110.f), FY + U(48.f))), SRId::Screen + 22, TEXT("UP"), SavesScroll > 0)) { SavesScroll = FMath::Max(0, SavesScroll - Rows); }
		if (MenuButton(FBox2D(FVector2D(X + Pad + U(122.f), FY), FVector2D(X + Pad + U(232.f), FY + U(48.f))), SRId::Screen + 23, TEXT("DOWN"), SavesScroll < MaxScroll)) { SavesScroll = FMath::Min(MaxScroll, SavesScroll + Rows); }
		Text(FString::Printf(TEXT("%d-%d of %d"), SavesScroll + 1, FMath::Min(Saves.Num(), SavesScroll + Rows), Saves.Num()), X + Pad + U(246.f), FY + U(14.f), U(14.f), Dim);
	}
	const bool bFresh = RealNow - Flow->GetSaveMessageTime() < 3.0;
	if (bFresh) { Text(Flow->GetSaveMessage(), X + W * 0.5f, FY + U(14.f), U(15.f), GoldBright, AlignCentre); }
	else if (bActAfterSave) { Text(TEXT("Choose where to save: the match is saved there first."), X + W * 0.5f, FY + U(14.f), U(15.f), Parchment, AlignCentre); }
	if (MenuButton(FBox2D(FVector2D(X + W - Pad - U(180.f), FY), FVector2D(X + W - Pad, FY + U(48.f))), SRId::Screen + 21, bActAfterSave ? TEXT("CANCEL") : TEXT("CLOSE"))) { OpenScreen(EScreen::None); }

	// act after drawing (the list must not change under the loop)
	if (!ToDelete.IsEmpty()) { Flow->DeleteSave(ToDelete); PendingDelete.Reset(); }
	if (!ToSaveOver.IsEmpty()) { bSaved = Flow->SaveMatch(ToSaveOver); PendingOverwrite.Reset(); }
	if (!ToLoad.IsEmpty()) { OpenScreen(EScreen::None); Flow->LoadMatch(ToLoad); }
	// "save, then quit": the save went through, so now the quit
	if (bSaved && bActAfterSave && Screen == EScreen::Saves) { DoConfirmed(); }
}

void ASRHUD::DoConfirmed()
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	OpenScreen(EScreen::None);
	switch (Confirm)
	{
	case EConfirm::Restart: Flow->StartMatch(); break;
	case EConfirm::MainMenu: Flow->EnterMainMenu(); break;
	default: UKismetSystemLibrary::QuitGame(this, PlayerOwner, EQuitPreference::Quit, false); break;
	}
}

void ASRHUD::DrawConfirmPanel(float CentreX)
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	static const TCHAR* Titles[3] = { TEXT("RESTART THE MATCH?"), TEXT("QUIT TO THE MAIN MENU?"), TEXT("QUIT THE GAME?") };
	static const TCHAR* Yes[3] = { TEXT("RESTART"), TEXT("QUIT"), TEXT("QUIT") };
	static const TCHAR* SaveYes[3] = { TEXT("SAVE & RESTART"), TEXT("SAVE & QUIT"), TEXT("SAVE & QUIT") };
	const int32 K = int32(Confirm);

	// Is there a match that would be lost? Only one being played (paused) that has moved on since it was last saved.
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const bool bInMatch = Flow->GetState() == ESRGameState::Paused && Battle && Battle->GetResult() == ESRBattleResult::Ongoing;
	const bool bUnsaved = bInMatch && !Flow->IsMatchSaved();
	FString Note, Detail;
	if (!bInMatch) { Note = TEXT("Until next time, sovereign."); }
	else if (!bUnsaved)
	{
		Note = Confirm == EConfirm::Restart ? TEXT("The battle starts over.") : TEXT("Your game is saved.");
		Detail = Confirm == EConfirm::Restart ? TEXT("This match is saved: you can load it again.") : TEXT("Nothing will be lost.");
	}
	else
	{
		bool bAuto = false;
		const float Since = Flow->GetUnsavedTime(&bAuto);
		Note = Confirm == EConfirm::Restart ? TEXT("The battle starts over: unsaved progress will be lost.") : TEXT("Unsaved progress will be lost.");
		Detail = Since < 0.f ? FString(TEXT("This match has not been saved."))
			: FString::Printf(TEXT("Last %s %s of play ago."), bAuto ? TEXT("autosave") : TEXT("saved"), *SRStyle::Countdown(Since));
	}

	const float W = bUnsaved ? U(700.f) : U(520.f), H = U(250.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat((View.Y - H) * 0.5f);
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(Titles[K], X + W * 0.5f, Y + U(30.f), U(23.f), GoldBright, AlignCentre, Bold, U(3.f));
	Rule(X + U(40.f), Y + U(72.f), W - U(80.f));
	Text(Note, X + W * 0.5f, Y + U(90.f), U(17.f), bUnsaved ? Amber : Parchment, AlignCentre);
	if (!Detail.IsEmpty()) { Text(Detail, X + W * 0.5f, Y + U(116.f), U(14.f), Dim, AlignCentre); }

	const int32 N = bUnsaved ? 3 : 2;
	const float Gap = U(14.f), BW = (W - U(80.f) - Gap * (N - 1)) / N, BY = Y + H - U(84.f);
	auto Btn = [&](int32 i) { const float BX = X + U(40.f) + i * (BW + Gap); return FBox2D(FVector2D(BX, BY), FVector2D(BX + BW, BY + U(54.f))); };
	if (MenuButton(Btn(0), SRId::Screen + 8, TEXT("CANCEL"))) { OpenScreen(EScreen::None); return; }
	if (bUnsaved)
	{
		if (MenuButton(Btn(1), SRId::Screen + 9, TEXT("DON'T SAVE"))) { DoConfirmed(); return; }
		if (MenuButton(Btn(2), SRId::Screen + 10, SaveYes[K], true, true))
		{
			// over this match's own saved game, else a new slot; with every slot in another game's use, the list comes
			// up to choose which one goes, and the quit follows that save
			if (!Flow->SaveCurrentMatch().IsEmpty()) { DoConfirmed(); }
			else if (!Flow->CanAddSave()) { OpenSaves(true, true); }
		}
		return;
	}
	if (MenuButton(Btn(1), SRId::Screen + 9, Yes[K])) { DoConfirmed(); }
}
