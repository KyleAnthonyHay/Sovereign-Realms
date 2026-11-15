// Copyright Sovereign Realms.
// Main menu, pause menu, victory / defeat screen, and the screens they share: controls, settings, new game, confirm.

#include "Player/SRHUD.h"
#include "Player/SRHUDStyle.h"
#include "Player/SRPlayerController.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRAISubsystem.h"
#include "Common/SRAudioSubsystem.h"
#include "Common/SRFeelSettings.h"
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
		{ TEXT("F / G"), TEXT("Formation on / off (RMB its button: shape) / stance") },
		{ nullptr, TEXT("CAMERA") },
		{ TEXT("WASD / Arrows"), TEXT("Pan (hold A or S: a tap is the order)") },
		{ TEXT("Screen edge"), TEXT("Pan") },
		{ TEXT("MMB drag"), TEXT("Grab the ground and drag") },
		{ TEXT("Mouse wheel"), TEXT("Zoom") },
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
		{ TEXT("Y"), TEXT("Train a Builder at the Citadel (more per castle level)") },
		{ TEXT("RMB on a site"), TEXT("Builders selected: build / repair it") },
		{ TEXT("X"), TEXT("Builders: repair the nearest damaged building") },
		{ TEXT("K  K"), TEXT("Dismiss the selected troops (press twice)") },
		{ TEXT("V, then click"), TEXT("Guard one of your Builders or buildings (or RMB it)") },
		{ TEXT("U"), TEXT("Upgrade the selected building, else the Citadel") },
		{ TEXT("M"), TEXT("March together (slowest sets the pace) on / off") },
		{ nullptr, TEXT("TROOPS") },
		{ TEXT("Q / E / R / T"), TEXT("Train Shieldbearer / Archer / Rider / Catapult") },
		{ TEXT("J"), TEXT("Train the Scout (Citadel level 3; one at a time)") },
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
	if (NewScreen == EScreen::Settings) { PendingScale = USRFeelSettings::Get().HUDScale; }
	if (NewScreen == EScreen::NewGame) { MenuDifficulty = USRFeelSettings::Get().AIDifficulty; }
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
	// The realm stays the picture: only the left third is darkened (in soft steps) to carry the title and the menu.
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
	// a saved game: CONTINUE comes first
	const FString Latest = Flow->LatestSlot();
	if (!Latest.IsEmpty())
	{
		const FBox2D Box(FVector2D(X, Y), FVector2D(X + BW, Y + BH));
		if (MenuButton(Box, SRId::Menu + 8, TEXT("CONTINUE"), true, false)) { Flow->LoadMatch(Latest); }
		Text(Flow->DescribeSave(Latest), X + U(4.f), Y + BH + U(3.f), U(13.f), A(Dim, In));
		Y += BH + Gap + U(16.f);
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
	const float H = U(104.f) + 7.f * (BH + Gap) + U(46.f);
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
		const bool bEnabled = i != 2 || !Latest.IsEmpty();
		if (!MenuButton(Box, SRId::Menu + 10 + i, Labels[i], bEnabled)) { continue; }
		switch (i)
		{
		case 0: Flow->SetPaused(false); break;
		case 1: Flow->SaveMatch(USRGameFlowSubsystem::QuickSlot()); break;
		case 2: Flow->LoadMatch(Latest); break;
		case 3: AskConfirm(EConfirm::Restart); break;
		case 4: OpenScreen(EScreen::Controls); break;
		case 5: OpenScreen(EScreen::Settings); break;
		default: AskConfirm(EConfirm::MainMenu); break;
		}
	}
	// what the save / load buttons did, or what LOAD would bring back
	const bool bFresh = FPlatformTime::Seconds() - Flow->GetSaveMessageTime() < 4.0;
	const FString Note = bFresh ? Flow->GetSaveMessage() : (Latest.IsEmpty() ? FString(TEXT("No saved game yet.")) : FString::Printf(TEXT("Load: %s%s"),
		Latest == USRGameFlowSubsystem::AutoSlot() ? TEXT("autosave, ") : TEXT(""), *Flow->DescribeSave(Latest)));
	Text(Note, X + W * 0.5f, BY + U(4.f), U(14.f), bFresh ? GoldBright : Dim, AlignCentre);
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
	const float H = U(92.f) + 8.f * RowH + U(96.f);
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
	const FSwitch Switches[2] = { { TEXT("Pan at the screen edge"), &F->bEdgePan }, { TEXT("WASD pans the camera"), &F->bWASDPansCamera } };
	for (int32 i = 0; i < 2; ++i, RY += RowH)
	{
		Label(Switches[i].Name);
		if (Toggle(FBox2D(FVector2D(SX, RY + U(7.f)), FVector2D(SX + U(32.f), RY + U(39.f))), SRId::Setting + 6 + i, *Switches[i].Value)) { bSettingsDirty = true; }
		TextIn(FBox2D(FVector2D(SX + U(44.f), RY), FVector2D(VX, RY + RowH)), *Switches[i].Value ? TEXT("On") : TEXT("Off"), U(16.f), *Switches[i].Value ? GoldBright : Dim, AlignLeft, Bold);
	}

	const float BW = U(220.f);
	if (MenuButton(FBox2D(FVector2D(X + (W - BW) * 0.5f, Y + H - U(74.f)), FVector2D(X + (W + BW) * 0.5f, Y + H - U(24.f))), SRId::Screen, TEXT("DONE"))) { OpenScreen(EScreen::None); }
}

void ASRHUD::DrawNewGamePanel(float CentreX)
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	const float W = U(560.f), RowH = U(76.f);
	const float H = U(92.f) + 3.f * (RowH + U(10.f)) + U(98.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat(FMath::Max((View.Y - H) * 0.5f, U(8.f)));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(TEXT("NEW GAME"), X + W * 0.5f, Y + U(22.f), U(26.f), GoldBright, AlignCentre, Bold, U(5.f));
	Rule(X + U(40.f), Y + U(66.f), W - U(80.f));
	float RY = Y + U(88.f);
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
	const float BW = (W - U(80.f) - U(14.f)) * 0.5f, BY = Y + H - U(78.f);
	if (MenuButton(FBox2D(FVector2D(X + U(40.f), BY), FVector2D(X + U(40.f) + BW, BY + U(54.f))), SRId::Screen + 5, TEXT("BACK"))) { OpenScreen(EScreen::None); }
	if (MenuButton(FBox2D(FVector2D(X + W - U(40.f) - BW, BY), FVector2D(X + W - U(40.f), BY + U(54.f))), SRId::Screen + 6, TEXT("BEGIN"), true, true)) { Flow->StartMatch(MenuDifficulty); }
}

void ASRHUD::DrawConfirmPanel(float CentreX)
{
	USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this);
	static const TCHAR* Titles[3] = { TEXT("RESTART THE MATCH?"), TEXT("QUIT TO THE MAIN MENU?"), TEXT("QUIT THE GAME?") };
	static const TCHAR* Notes[3] = { TEXT("The battle starts over. This match is lost."), TEXT("This match will be lost."), TEXT("Until next time, sovereign.") };
	static const TCHAR* Yes[3] = { TEXT("RESTART"), TEXT("QUIT"), TEXT("QUIT") };
	const int32 K = int32(Confirm);
	const float W = U(520.f), H = U(236.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat((View.Y - H) * 0.5f);
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(Titles[K], X + W * 0.5f, Y + U(30.f), U(23.f), GoldBright, AlignCentre, Bold, U(3.f));
	Rule(X + U(40.f), Y + U(72.f), W - U(80.f));
	Text(Notes[K], X + W * 0.5f, Y + U(92.f), U(17.f), Parchment, AlignCentre);
	const float BW = (W - U(80.f) - U(14.f)) * 0.5f, BY = Y + H - U(84.f);
	if (MenuButton(FBox2D(FVector2D(X + U(40.f), BY), FVector2D(X + U(40.f) + BW, BY + U(54.f))), SRId::Screen + 8, TEXT("CANCEL"))) { OpenScreen(EScreen::None); }
	if (MenuButton(FBox2D(FVector2D(X + W - U(40.f) - BW, BY), FVector2D(X + W - U(40.f), BY + U(54.f))), SRId::Screen + 9, Yes[K]))
	{
		Screen = EScreen::None;
		switch (Confirm)
		{
		case EConfirm::Restart: Flow->StartMatch(); break;
		case EConfirm::MainMenu: Flow->EnterMainMenu(); break;
		default: UKismetSystemLibrary::QuitGame(this, PlayerOwner, EQuitPreference::Quit, false); break;
		}
	}
}
