// The title screen, the pause menu, the victory / defeat screen, and the screens they share: controls, settings, new
// game, confirm. The main game's SRHUDMenus.cpp, ported (no saved games here; this game's own settings and maps).

#include "VLHUD.h"
#include "VLGraphics.h"
#include "VLHUDStyle.h"
#include "SovereignRealms.h"
#include "VLKing.h"
#include "VLGameMode.h"
#include "VLBattle.h"
#include "Engine/Canvas.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"

using namespace VLStyle;

namespace
{
	struct FControlRow { const TCHAR* Keys; const TCHAR* What; };   // Keys == nullptr: a section heading

	// Every control (AVLKing's PollInput and OverviewCommands are the source of truth).
	const FControlRow ControlsLeft[] = {
		{ nullptr, TEXT("SELECTION") },
		{ TEXT("LMB"), TEXT("Select a unit or a building") },
		{ TEXT("Shift + LMB"), TEXT("Add to / remove from the selection") },
		{ TEXT("LMB drag"), TEXT("Box-select units") },
		{ TEXT("Alt / Option + LMB"), TEXT("All of that kind in view") },
		{ TEXT("Enter / double-click"), TEXT("Take control of the unit (the hero view)") },
		{ TEXT("Space"), TEXT("Centre the view on the selection") },
		{ TEXT("Builders / Spy (top bar)"), TEXT("Their list: click one to go to it, hover marks it") },
		{ nullptr, TEXT("ORDERS") },
		{ TEXT("RMB"), TEXT("Move in formation / attack a foe") },
		{ TEXT("RMB twice"), TEXT("The same, at a run") },
		{ TEXT("Shift + RMB"), TEXT("Pathway / queue: points, foes, buildings in turn") },
		{ TEXT("RMB your troop"), TEXT("The others follow it (its platoon's: it leads)") },
		{ TEXT("Shift (Builders)"), TEXT("Queue walks, builds, repairs, claims (Esc clears)") },
		{ TEXT("LMB a dummy"), TEXT("The fighters attack it (Shift: at a run)") },
		{ TEXT("A, then LMB"), TEXT("Attack-move: fight what you meet on the way") },
		{ TEXT("S (tap)"), TEXT("Stop (to hold ground: the Hold stance, G)") },
		{ VL_ALT_KEY TEXT(" (held)"), TEXT("Shows a button's card while the pointer is on it") },
		{ TEXT("P, then LMB"), TEXT("Patrol there and back (Shift: more points)") },
		{ TEXT("V, then LMB"), TEXT("Guard a building or a unit (in a platoon: all of it)") },
		{ TEXT("RMB the tower"), TEXT("Archers man the watch tower's lookout") },
		{ TEXT("F / G / M"), TEXT("Formation / stance / march together") },
		{ TEXT("O / K K"), TEXT("The Spy roams / dismiss (press twice)") },
		{ nullptr, TEXT("CAMERA") },
		{ TEXT("WASD / Arrows"), TEXT("Pan (hold A or S: a tap is the order)") },
		{ TEXT("Mouse wheel"), TEXT("Zoom (trackpad: pinch)") },
		{ TEXT("Q / E, RMB drag"), TEXT("Turn the view right / left (R: back)") },
		{ TEXT("V / C"), TEXT("Camera angle (no troops chosen) / postcard") },
		{ TEXT("Trackpad"), TEXT("Two fingers pan, twist turns, Ctrl+click = RMB") },
		{ TEXT("Minimap"), TEXT("LMB look there (drag), RMB send troops") },
	};
	const FControlRow ControlsRight[] = {
		{ nullptr, TEXT("PLATOONS") },
		{ TEXT("Ctrl / Shift + 1-6"), TEXT("The selection joins platoon N (empty: forms it)") },
		{ TEXT("1-6"), TEXT("Select the platoon (twice: go to it)") },
		{ TEXT("Assign (command card)"), TEXT("The same, picked from the six platoons") },
		{ TEXT("Delete"), TEXT("Disband the selected platoon") },
		{ TEXT("Flag (platoon row)"), TEXT("New recruits join that platoon (again: off)") },
		{ nullptr, TEXT("BUILDINGS") },
		{ TEXT("U"), TEXT("Upgrade the selected building") },
		{ TEXT("T"), TEXT("Turn the selected building a quarter turn") },
		{ TEXT("RMB a free mine"), TEXT("The selected Builders claim it (140 gold)") },
		{ TEXT("Train"), TEXT("One recruit (Shift: 5, Ctrl / Cmd: 10)") },
		{ TEXT("RMB"), TEXT("Rally point (Barracks or Range selected)") },
		{ TEXT("Ctrl + 1-6"), TEXT("Its recruits join that platoon (again: none)") },
		{ nullptr, TEXT("HERO") },
		{ TEXT("Tab"), TEXT("Hero view / overview") },
		{ TEXT("WASD, Shift, Space"), TEXT("Walk, run (or double-tap), jump") },
		{ TEXT("F"), TEXT("Draw or sheathe the sword") },
		{ TEXT("Hold RMB"), TEXT("Archer: draw (let go: shoot). Spy: the spyglass") },
		{ TEXT("LMB"), TEXT("Attack: always your own blow, never a selection") },
		{ VL_ALT_KEY TEXT(" + LMB troop"), TEXT("Select it (Shift: add / remove; twice: play it)") },
		{ TEXT("... with troops selected"), TEXT("They guard it (in a platoon: the whole platoon)") },
		{ VL_ALT_KEY TEXT(" + LMB foe"), TEXT("Attack: the selection, else followers, else platoon") },
		{ VL_ALT_KEY TEXT(" + LMB ground"), TEXT("They go there (twice quickly: at a run)") },
		{ TEXT("Shift + ") VL_ALT_KEY TEXT(" + LMB"), TEXT("Queue: foe 1, then foe 2, a building, a walk") },
		{ TEXT("RMB / Ctrl + LMB"), TEXT("Selection: move / attack at the crosshair") },
		{ TEXT("Esc / ") VL_ALT_KEY TEXT(" + LMB sky"), TEXT("Let the selection go (Esc again: the menu)") },
		{ TEXT("G"), TEXT("Follow me: the selection falls in behind you") },
		{ nullptr, TEXT("GAME") },
		{ TEXT("Esc / P"), TEXT("Cancel, then pause (P: nobody selected)") },
		{ TEXT("M  U  V  L  I  X"), TEXT("In the pause menu: next map, music, camera, look") },
		{ TEXT(""), TEXT("speed, invert look, quit") },
		{ TEXT("F1"), TEXT("Show or hide this list") },
	};

	const TCHAR* DifficultyNames[3] = { TEXT("Easy"), TEXT("Normal"), TEXT("Hard") };
	const TCHAR* DifficultyNotes[3] = {
		TEXT("A gentle enemy: a small economy, late, small attacks."),
		TEXT("A fair fight: it attacks when it thinks it can win."),
		TEXT("The enemy strikes early, raids often, adapts fully.") };

	// the maps of New Game, in the order shown: the battles first, then the sandboxes
	const int32 MapOrder[AVLHUD::NumMaps] = { 1, 0, 3, 2, 4 };
	const TCHAR* MapTitles[AVLHUD::NumMaps] = { TEXT("Realm v2"), TEXT("The Realm"), TEXT("Flatlands"), TEXT("Highlands"), TEXT("Test World") };
	const TCHAR* MapNotes[AVLHUD::NumMaps] = {
		TEXT("The great battle: a mountain, two rivers, five mines, the ruins."),
		TEXT("The battle: two kingdoms with a river between."),
		TEXT("Sandbox: every building side by side."),
		TEXT("The bigger battle: bluffs, a gorge, the Crown."),
		TEXT("Balance test: both sides start maxed out, on Realm v2.") };

	const int32 MenuFpsCaps[5] = { 30, 40, 60, 120, 0 };

	FString ClockText(float Seconds)
	{
		const int32 S = FMath::Max(0, FMath::FloorToInt(Seconds));
		return FString::Printf(TEXT("%d:%02d"), S / 60, S % 60);
	}
}

void AVLHUD::DimScreen(float Alpha)
{
	Fill(0.f, 0.f, View.X, View.Y, FLinearColor(0.008f, 0.012f, 0.025f, Alpha));
}

// ---------------------------------------------------------------------------- title screen

void AVLHUD::DrawMainMenu()
{
	const float In = FMath::Clamp(float(Now - StateTime) / 0.5f, 0.f, 1.f);
	// The picture is the live realm drifting by (AVLKing turns the overview slowly). The left third is darkened (in
	// soft steps) to carry the title and the menu.
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
	Icon(EVLIcon::Crown, X, Y, U(64.f), FLinearColor(1.f, 1.f, 1.f, In));
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
	const TCHAR* Labels[4] = { TEXT("NEW GAME"), TEXT("HOW TO PLAY"), TEXT("SETTINGS"), TEXT("QUIT") };
	const EVLScreen Opens[4] = { EVLScreen::NewGame, EVLScreen::Controls, EVLScreen::Settings, EVLScreen::None };
	for (int32 i = 0; i < 4; ++i)
	{
		const FBox2D Box(FVector2D(X, Y), FVector2D(X + BW, Y + BH));
		const bool bOpen = i == 3 ? bConfirm : (Sub == Opens[i] && !bConfirm);
		if (MenuButton(Box, VLId::Menu + i, Labels[i], true, bOpen))
		{
			if (bOpen) { bConfirm = false; OpenSub(EVLScreen::None); }
			else if (i == 3) { OpenSub(EVLScreen::None); AskConfirm(EConfirm::Quit); }
			else { OpenSub(Opens[i]); }
		}
		Y += BH + Gap;
	}
	Text(TEXT("F1  controls      Enter  new game      Esc  back"), X, View.Y - U(48.f), U(14.f), A(Dim, 0.9f * In));

	if (Sub != EVLScreen::None || bConfirm) { DrawSub(FMath::Max(View.X * 0.64f, X + BW + U(60.f) + U(330.f))); }
}

// ---------------------------------------------------------------------------- pause menu

void AVLHUD::DrawPauseMenu()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const float In = FMath::Clamp(float(Now - StateTime) / 0.15f, 0.f, 1.f);
	DimScreen(0.5f * In);
	if (Sub != EVLScreen::None || bConfirm)
	{
		DrawSub(View.X * 0.5f);
		return;
	}

	const int32 N = 7;
	const float W = U(420.f), BH = U(54.f), Gap = U(10.f);
	const float H = U(104.f) + N * (BH + Gap) + U(56.f);
	const float X = FMath::RoundToFloat((View.X - W) * 0.5f), Y = FMath::RoundToFloat((View.Y - H) * 0.5f - (1.f - In) * U(12.f));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(TEXT("PAUSED"), X + W * 0.5f, Y + U(26.f), U(32.f), GoldBright, AlignCentre, Bold, U(6.f));
	Rule(X + U(40.f), Y + U(78.f), W - U(80.f));
	const TCHAR* Labels[N] = { TEXT("RESUME"), TEXT("RESTART"), TEXT("NEW GAME"), TEXT("CONTROLS"), TEXT("SETTINGS"), TEXT("QUIT TO MAIN MENU"), TEXT("QUIT GAME") };
	float BY = Y + U(104.f);
	for (int32 i = 0; i < N; ++i, BY += BH + Gap)
	{
		const FBox2D Box(FVector2D(X + U(34.f), BY), FVector2D(X + W - U(34.f), BY + BH));
		if (!MenuButton(Box, VLId::Menu + 10 + i, Labels[i]))
		{
			continue;
		}
		switch (i)
		{
		case 0: SetScreen(EVLScreen::None); break;
		case 1: AskConfirm(EConfirm::Restart); break;
		case 2: OpenSub(EVLScreen::NewGame); break;
		case 3: OpenSub(EVLScreen::Controls); break;
		case 4: OpenSub(EVLScreen::Settings); break;
		case 5: AskConfirm(EConfirm::MainMenu); break;
		default: AskConfirm(EConfirm::Quit); break;
		}
	}
	// where and how this match is played, and the old Esc menu's keys
	const FString Note = Battle && Battle->IsBattle()
		? FString::Printf(TEXT("%s  ·  %s  ·  %s"), MapName(CurrentMap()), UVLBattle::DifficultyName(Battle->GetDifficulty()), *ClockText(Battle->GetClock()))
		: FString::Printf(TEXT("%s  ·  sandbox"), MapName(CurrentMap()));
	Text(Note, X + W * 0.5f, BY - U(4.f), U(14.f), Dim, AlignCentre);
	Text(FString::Printf(TEXT("Enter resume  ·  M %s  ·  X quit"), MapName(OtherMap(0))), X + W * 0.5f, BY + U(14.f), U(13.f), Dim, AlignCentre);
}

// ---------------------------------------------------------------------------- victory / defeat

void AVLHUD::DrawEndScreen()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle)
	{
		return;
	}
	const bool bWon = Battle->GetWinner() == UVLBattle::Player;
	const float In = FMath::Clamp(float(Now - StateTime) / 0.35f, 0.f, 1.f);
	DimScreen(0.5f * In);

	const FVLKingdom& Me = Battle->GetKingdom(UVLBattle::Player);
	const FVLKingdom& Foe = Battle->GetKingdom(UVLBattle::Enemy);
	const TPair<const TCHAR*, FString> Rows[] = {
		{ TEXT("Time"), ClockText(Battle->GetClock()) },
		{ TEXT("Map"), MapName(CurrentMap()) },
		{ TEXT("Difficulty"), DifficultyNames[FMath::Clamp(Battle->GetDifficulty(), 0, 2)] },
		{ TEXT("Troops recruited"), FString::FromInt(Me.Recruited) },
		{ TEXT("Troops lost"), FString::FromInt(Me.Lost) },
		{ TEXT("Enemies slain"), FString::FromInt(Me.Killed) },
		{ TEXT("Buildings lost"), FString::FromInt(Me.BuildingsLost) },
		{ TEXT("Enemy buildings razed"), FString::FromInt(Foe.BuildingsLost) },
	};
	const int32 NumRows = UE_ARRAY_COUNT(Rows);
	const float W = U(560.f), RowH = U(30.f);
	const float H = U(170.f) + NumRows * RowH + U(100.f) + U(62.f);
	const float X = FMath::RoundToFloat((View.X - W) * 0.5f), Y = FMath::RoundToFloat((View.Y - H) * 0.5f - (1.f - In) * U(24.f));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true, In);
	const FLinearColor Accent = bWon ? GoldBright : FLinearColor(0.95f, 0.30f, 0.22f, 1.f);
	Icon(bWon ? EVLIcon::Crown : EVLIcon::AlertLost, X + W * 0.5f - U(24.f), Y + U(20.f), U(48.f), FLinearColor(1.f, 1.f, 1.f, In));
	Text(bWon ? TEXT("VICTORY") : TEXT("DEFEAT"), X + W * 0.5f, Y + U(66.f), U(54.f), A(Accent, In), AlignCentre, Black, U(10.f));
	Text(bWon ? TEXT("The enemy's castle has fallen.") : TEXT("Your castle has fallen."), X + W * 0.5f, Y + U(132.f), U(16.f), A(Parchment, In), AlignCentre);
	Rule(X + U(50.f), Y + U(162.f), W - U(100.f), In);
	float RY = Y + U(176.f);
	for (int32 i = 0; i < NumRows; ++i, RY += RowH)
	{
		if (i & 1) { Fill(X + U(40.f), RY, W - U(80.f), RowH, FLinearColor(1.f, 1.f, 1.f, 0.03f * In)); }
		const FBox2D Row(FVector2D(X + U(56.f), RY), FVector2D(X + W - U(56.f), RY + RowH));
		TextIn(Row, Rows[i].Key, U(16.f), A(Dim, In), AlignLeft);
		TextIn(Row, Rows[i].Value, U(17.f), A(Parchment, In), AlignRight, Bold);
	}
	const float BW = (W - U(80.f) - U(14.f)) * 0.5f, BY = Y + H - U(82.f) - U(62.f);
	if (MenuButton(FBox2D(FVector2D(X + U(40.f), BY), FVector2D(X + U(40.f) + BW, BY + U(54.f))), VLId::Menu + 20, TEXT("PLAY AGAIN")))
	{
		OpenMatch(this, CurrentMap(), Battle->GetDifficulty());
	}
	if (MenuButton(FBox2D(FVector2D(X + W - U(40.f) - BW, BY), FVector2D(X + W - U(40.f), BY + U(54.f))), VLId::Menu + 21, TEXT("MAIN MENU")))
	{
		UGameplayStatics::SetGamePaused(this, false);
		UGameplayStatics::OpenLevel(this, FName(*MapPath(CurrentMap())));      // (no match: the title screen comes up)
	}
	// this game's own: the world keeps moving behind the screen, and can be watched
	if (MenuButton(FBox2D(FVector2D(X + U(40.f), BY + U(62.f)), FVector2D(X + W - U(40.f), BY + U(62.f) + U(48.f))), VLId::Menu + 22, TEXT("KEEP WATCHING")))
	{
		SetScreen(EVLScreen::None);
	}
}

// ---------------------------------------------------------------------------- shared screens

void AVLHUD::DrawLegendOverlay()
{
	DimScreen(0.5f);
	DrawControlsPanel(View.X * 0.5f, true);
}

void AVLHUD::DrawSub(float CentreX)
{
	if (bConfirm)
	{
		DrawConfirmPanel(CentreX);
		return;
	}
	switch (Sub)
	{
	case EVLScreen::NewGame: DrawNewGamePanel(CentreX); break;
	case EVLScreen::Controls: DrawControlsPanel(CentreX, true); break;
	case EVLScreen::Settings: DrawSettingsPanel(CentreX); break;
	default: break;
	}
}

void AVLHUD::DrawControlsPanel(float CentreX, bool bCloseButton)
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
				const float HW = TextSize(Rows[i].What, U(14.f), Bold, U(2.f)).X;
				Fill(CX + HW + U(10.f), RY + RowH * 0.5f + U(3.f), ColW - HW - U(10.f), FMath::Max(1.f, U(1.f)), A(Bronze, 0.8f));
				continue;
			}
			TextIn(FBox2D(Row.Min, FVector2D(CX + KeyW, Row.Max.Y)), Rows[i].Keys, U(15.f), GoldBright, AlignRight, Bold);
			TextIn(FBox2D(FVector2D(CX + KeyW + U(14.f), RY), Row.Max), Rows[i].What, U(15.f), Parchment, AlignLeft);
		}
	}
	if (bCloseButton)
	{
		const float BW = U(220.f);
		if (MenuButton(FBox2D(FVector2D(X + (W - BW) * 0.5f, Y + H - U(72.f)), FVector2D(X + (W + BW) * 0.5f, Y + H - U(22.f))), VLId::LegendClose, TEXT("CLOSE")))
		{
			if (bLegend) { bLegend = false; }
			else { OpenSub(EVLScreen::None); }
		}
	}
}

void AVLHUD::DrawSettingsPanel(float CentreX)
{
	AVLGameMode* GM = GetWorld()->GetAuthGameMode<AVLGameMode>();
	AVLKing* Me = King;
	const int32 NumRows = 12;
	const float W = U(600.f), RowH = U(46.f), HeadH = U(34.f);
	const float H = U(92.f) + NumRows * RowH + 2.f * HeadH + U(96.f) + U(24.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat(FMath::Max((View.Y - H) * 0.5f, U(8.f)));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(TEXT("SETTINGS"), X + W * 0.5f, Y + U(22.f), U(26.f), GoldBright, AlignCentre, Bold, U(5.f));
	Rule(X + U(40.f), Y + U(66.f), W - U(80.f));

	const float LX = X + U(40.f), SX = X + U(250.f), SW = U(230.f), VX = X + W - U(40.f);
	float RY = Y + U(88.f);
	auto Label = [&](const TCHAR* Name) { TextIn(FBox2D(FVector2D(LX, RY), FVector2D(SX, RY + RowH)), Name, U(17.f), Parchment, AlignLeft); };
	auto Value = [&](const FString& String) { TextIn(FBox2D(FVector2D(SX + SW, RY), FVector2D(VX, RY + RowH)), String, U(16.f), GoldBright, AlignRight, Bold); };
	auto SliderBox = [&]() { return FBox2D(FVector2D(SX, RY + U(6.f)), FVector2D(SX + SW, RY + RowH - U(6.f))); };

	// volumes: the whole game's sound, the effects (UVLBattle's sounds), the music (the game mode's songs)
	Label(TEXT("Master volume"));
	if (Slider(SliderBox(), VLId::Setting + 0, MasterVolume, 0.f, 1.f)) { ApplySettings(); bSettingsDirty = true; }
	Value(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(MasterVolume * 100.f)));
	RY += RowH;
	Label(TEXT("Effects"));
	if (Slider(SliderBox(), VLId::Setting + 1, UVLBattle::EffectsVolume, 0.f, 1.f)) { bSettingsDirty = true; }
	Value(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(UVLBattle::EffectsVolume * 100.f)));
	RY += RowH;
	Label(TEXT("Music"));
	{
		float Music = GM ? GM->GetMusicSetting() : 0.f;
		if (Slider(SliderBox(), VLId::Setting + 2, Music, 0.f, 1.f) && GM)
		{
			GM->SetMusicSetting(FMath::RoundToFloat(Music * 20.f) / 20.f);
		}
		Value(Music > 0.001f ? FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Music * 100.f)) : FString(TEXT("Off")));
	}
	RY += RowH;

	// Interface scale: applied when the slider is let go, so the panel does not resize under the cursor mid-drag.
	Label(TEXT("Interface scale"));
	Slider(SliderBox(), VLId::Setting + 3, PendingScale, 0.8f, 1.4f);
	PendingScale = FMath::RoundToFloat(PendingScale * 20.f) / 20.f;
	if (ActiveId != VLId::Setting + 3 && !FMath::IsNearlyEqual(PendingScale, InterfaceScale))
	{
		InterfaceScale = PendingScale;
		bSettingsDirty = true;
	}
	Value(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(PendingScale * 100.f)));
	RY += RowH;

	// each click steps to the next choice
	auto Choice = [&](uint32 Id, const FString& Current, const TCHAR* Key)
	{
		const FBox2D Box = SliderBox();
		const FBtn B = Button(Box, Id);
		ButtonFrame(Box, B, true);
		TextIn(FBox2D(Box.Min + FVector2D(0.f, B.bHeld ? U(1.f) : 0.f), Box.Max), Current, U(16.f), FMath::Lerp(Parchment, GoldBright, B.Hot), AlignCentre, Bold);
		if (Key) { KeyCap(Key, VX, RY + (RowH - U(19.f)) * 0.5f, true); }
		if (B.bClicked) { Click(); bSettingsDirty = true; }
		return B.bClicked;
	};
	// a section's heading, as on the controls screen
	auto Head = [&](const TCHAR* Name)
	{
		const FBox2D Box(FVector2D(LX, RY), FVector2D(VX, RY + HeadH));
		TextIn(FBox2D(Box.Min + FVector2D(0.f, U(4.f)), Box.Max), Name, U(14.f), Gold, AlignLeft, Bold, U(2.f));
		const float HW = TextSize(Name, U(14.f), Bold, U(2.f)).X;
		Fill(LX + HW + U(10.f), RY + HeadH * 0.5f + U(3.f), VX - LX - HW - U(10.f), FMath::Max(1.f, U(1.f)), A(Bronze, 0.8f));
		RY += HeadH;
	};
	// Graphics (UVLGraphics): the quality preset brings its own render scale, which can then be changed by itself
	Head(TEXT("GRAPHICS"));
	Label(TEXT("Quality"));
	if (Choice(VLId::Setting + 8, UVLGraphics::QualityName(UVLGraphics::GetQuality()), nullptr))
	{
		UVLGraphics::SetQuality(GetWorld(), (UVLGraphics::GetQuality() + UVLGraphics::NumQualities - 1) % UVLGraphics::NumQualities);     // High, Medium, Low
	}
	RY += RowH;
	Label(TEXT("Render scale"));
	if (Choice(VLId::Setting + 9, FString::Printf(TEXT("%d%%"), UVLGraphics::GetRenderScale()), nullptr)) { UVLGraphics::CycleRenderScale(GetWorld()); }
	RY += RowH;
	Label(TEXT("Dynamic resolution"));
	if (Choice(VLId::Setting + 10, UVLGraphics::DynamicResName(UVLGraphics::GetDynamicRes()), nullptr)) { UVLGraphics::CycleDynamicRes(GetWorld()); }
	RY += RowH;
	Label(TEXT("Frame rate limit"));
	if (Choice(VLId::Setting + 4, MenuFpsCaps[FrameCap] > 0 ? FString::Printf(TEXT("%d fps"), MenuFpsCaps[FrameCap]) : FString(TEXT("Unlimited")), nullptr)) { FrameCap = (FrameCap + 1) % 5; ApplySettings(); }
	RY += RowH;
	// the window (saved in GameUserSettings by UVLGraphics, as F11 / Alt+Enter and a dragged edge are; the editor's
	// play window is the editor's own)
	Label(TEXT("Window"));
	if (Choice(VLId::Setting + 11, !UVLGraphics::CanChangeWindow() ? FString(TEXT("Editor window")) : FString(UVLGraphics::IsFullscreen() ? TEXT("Full screen") : TEXT("Windowed")), nullptr))
	{
		UVLGraphics::ToggleFullscreen();
	}
	RY += RowH;
	Head(TEXT("CAMERA"));
	Label(TEXT("Camera angle"));
	if (Choice(VLId::Setting + 5, AVLKing::CameraAngleName(Me ? Me->GetCameraAngle() : 0), TEXT("V")) && Me) { Me->CycleCameraAngle(); }
	RY += RowH;
	Label(TEXT("Look speed"));
	if (Choice(VLId::Setting + 6, FString::Printf(TEXT("%.0f%%"), (Me ? Me->GetLookSpeedSetting() : 0.5f) * 100.f), TEXT("L")) && Me) { Me->CycleLookSpeed(); }
	RY += RowH;
	Label(TEXT("Invert look"));
	if (Choice(VLId::Setting + 7, AVLKing::LookInvertName(Me ? Me->GetLookInvert() : 0), TEXT("I")) && Me) { Me->CycleLookInvert(); }
	RY += RowH;

	Text(TEXT("U music   V camera angle   L look speed   I invert look   Esc back"), X + W * 0.5f, RY + U(8.f), U(14.f), Dim, AlignCentre);
	const float BW = U(220.f);
	if (MenuButton(FBox2D(FVector2D(X + (W - BW) * 0.5f, Y + H - U(74.f)), FVector2D(X + (W + BW) * 0.5f, Y + H - U(24.f))), VLId::Screen, TEXT("DONE")))
	{
		OpenSub(EVLScreen::None);
	}
}

void AVLHUD::DrawNewGamePanel(float CentreX)
{
	// the maps side by side above the difficulties
	const float W = U(1170.f), RowH = U(76.f), MapH = U(104.f);     // (1170: five maps side by side at the width four had in 960)
	const float H = U(92.f) + MapH + U(16.f) + 3.f * (RowH + U(10.f)) + U(98.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat(FMath::Max((View.Y - H) * 0.5f, U(8.f)));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(TEXT("NEW GAME"), X + W * 0.5f, Y + U(22.f), U(26.f), GoldBright, AlignCentre, Bold, U(5.f));
	Rule(X + U(40.f), Y + U(66.f), W - U(80.f));
	float RY = Y + U(88.f);
	{
		const float Gap = U(12.f), MW = FMath::FloorToFloat((W - U(80.f) - Gap * (NumMaps - 1)) / NumMaps);
		for (int32 k = 0; k < NumMaps; ++k)
		{
			const int32 i = MapOrder[k];
			const float MX = X + U(40.f) + k * (MW + Gap);
			const FBox2D Box(FVector2D(MX, RY), FVector2D(MX + MW, RY + MapH));
			const FBtn B = Button(Box, VLId::Screen + 11 + i);
			const bool bChosen = PickMap == i;
			ButtonFrame(Box, B, true, bChosen);
			const float Pad = U(14.f);
			Text(MapTitles[i], Box.Min.X + Pad, Box.Min.Y + U(11.f), U(18.f), bChosen ? GoldBright : Parchment, AlignLeft, Bold, U(1.f));
			if (bChosen) { Icon(EVLIcon::Check, Box.Max.X - U(34.f), Box.Min.Y + U(9.f), U(24.f)); }
			// the note, wrapped to the button: up to three lines
			TArray<FString> Words;
			FString(MapNotes[i]).ParseIntoArray(Words, TEXT(" "));
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
			if (B.bClicked) { Click(); PickMap = i; }
		}
		RY += MapH + U(16.f);
	}
	for (int32 i = 0; i < 3; ++i, RY += RowH + U(10.f))
	{
		const FBox2D Box(FVector2D(X + U(40.f), RY), FVector2D(X + W - U(40.f), RY + RowH));
		const FBtn B = Button(Box, VLId::Screen + 1 + i);
		const bool bChosen = PickDifficulty == i;
		ButtonFrame(Box, B, true, bChosen);
		static const EVLIcon Icons[3] = { EVLIcon::StanceDefensive, EVLIcon::Swords, EVLIcon::AlertAttack };
		Icon(Icons[i], Box.Min.X + U(18.f), Box.Min.Y + U(18.f), U(40.f));
		Text(DifficultyNames[i], Box.Min.X + U(76.f), Box.Min.Y + U(12.f), U(22.f), bChosen ? GoldBright : Parchment, AlignLeft, Bold);
		Text(DifficultyNotes[i], Box.Min.X + U(76.f), Box.Min.Y + U(43.f), U(15.f), Dim);
		if (bChosen) { Icon(EVLIcon::Check, Box.Max.X - U(46.f), Box.Min.Y + U(24.f), U(28.f)); }
		if (B.bClicked) { Click(); PickDifficulty = i; }
	}
	const float BW = (W - U(80.f) - U(14.f)) * 0.5f, BY = Y + H - U(78.f);
	if (MenuButton(FBox2D(FVector2D(X + U(40.f), BY), FVector2D(X + U(40.f) + BW, BY + U(54.f))), VLId::Screen + 5, TEXT("BACK"))) { OpenSub(EVLScreen::None); }
	if (MenuButton(FBox2D(FVector2D(X + W - U(40.f) - BW, BY), FVector2D(X + W - U(40.f), BY + U(54.f))), VLId::Screen + 6, TEXT("BEGIN"), true, true))
	{
		SaveSettings();
		UE_LOG(LogSovereignRealms, Log, TEXT("hud: new game on %s, %s"), MapName(PickMap), DifficultyNames[PickDifficulty]);
		OpenMatch(this, PickMap, PickDifficulty);
	}
}

void AVLHUD::DrawConfirmPanel(float CentreX)
{
	static const TCHAR* Titles[3] = { TEXT("RESTART THE MATCH?"), TEXT("QUIT TO THE MAIN MENU?"), TEXT("QUIT THE GAME?") };
	static const TCHAR* Yes[3] = { TEXT("RESTART"), TEXT("QUIT"), TEXT("QUIT") };
	const int32 K = int32(Confirm);
	// is there a match that would be lost? (there are no saved games here)
	const UVLBattle* Battle = UVLBattle::Get(this);
	const bool bInMatch = Base == EVLScreen::Pause && Battle && Battle->IsPlaying();
	const FString Note = !bInMatch ? FString(TEXT("Until next time, sovereign."))
		: (Confirm == EConfirm::Restart ? FString(TEXT("The battle starts over.")) : FString(TEXT("This match will be lost.")));

	const float W = U(520.f), H = U(250.f);
	const float X = FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, U(10.f), FMath::Max(U(10.f), View.X - W - U(10.f)))), Y = FMath::RoundToFloat((View.Y - H) * 0.5f);
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(Titles[K], X + W * 0.5f, Y + U(30.f), U(23.f), GoldBright, AlignCentre, Bold, U(3.f));
	Rule(X + U(40.f), Y + U(72.f), W - U(80.f));
	Text(Note, X + W * 0.5f, Y + U(90.f), U(17.f), bInMatch ? Amber : Parchment, AlignCentre);
	Text(TEXT("Enter: yes   ·   Esc: cancel"), X + W * 0.5f, Y + U(116.f), U(14.f), Dim, AlignCentre);

	const float Gap = U(14.f), BW = (W - U(80.f) - Gap) / 2.f, BY = Y + H - U(84.f);
	auto Btn = [&](int32 i) { const float BX = X + U(40.f) + i * (BW + Gap); return FBox2D(FVector2D(BX, BY), FVector2D(BX + BW, BY + U(54.f))); };
	if (MenuButton(Btn(0), VLId::Screen + 8, TEXT("CANCEL"))) { bConfirm = false; return; }
	if (MenuButton(Btn(1), VLId::Screen + 9, Yes[K])) { DoConfirmed(); }
}
