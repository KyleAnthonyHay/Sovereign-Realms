// The Save Game and Load Game screens (over the pause menu; Load Game over the title screen too), and the quicksave
// keys. The saving and loading themselves: UVLSaves (VLSave.*).

#include "VLHUD.h"
#include "VLHUDStyle.h"
#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLGraphics.h"
#include "VLSave.h"
#include "Engine/Canvas.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"

using namespace VLStyle;

namespace
{
	FString PlayedText(float Seconds)
	{
		const int32 S = FMath::Max(0, FMath::FloorToInt(Seconds));
		return S >= 3600 ? FString::Printf(TEXT("%d:%02d:%02d"), S / 3600, (S / 60) % 60, S % 60) : FString::Printf(TEXT("%d:%02d"), S / 60, S % 60);
	}
}

void AVLHUD::SaveKeys()
{
	if (!PCtrl || UVLGraphics::DisplayConfirmSeconds() > 0.f)
	{
		return;
	}
	if (PCtrl->WasInputKeyJustPressed(EKeys::F5))
	{
		QuickSave(false);
	}
	if (PCtrl->WasInputKeyJustPressed(EKeys::F9))
	{
		QuickSave(true);
	}
}

void AVLHUD::QuickSave(bool bLoad)
{
	// F5: the quicksave, while a match is on (playing, or its pause menu up). F9: the quicksave loaded, from a match or
	// from the title screen. What is refused says why: an alert in a match, the Load Game screen's line otherwise
	UVLSaves* Saves = UVLSaves::Get(this);
	if (!Saves || (!bLoad && Base == EVLScreen::Main))
	{
		return;
	}
	const bool bOk = bLoad ? Saves->Load(UVLSaves::QuickSlot()) : Saves->Save(UVLSaves::QuickSlot());
	UE_LOG(LogSovereignRealms, Log, TEXT("hud: %s: %s"), bLoad ? TEXT("quickload (F9)") : TEXT("quicksave (F5)"), bOk ? TEXT("done") : *Saves->LastMessage);
	Click(!bOk);
}

void AVLHUD::DrawSavesPanel(float CentreX, bool bSave)
{
	UVLSaves* Saves = UVLSaves::Get(this);
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Saves)
	{
		return;
	}
	// Save Game: the five slots. Load Game: those, the quicksave and the autosave
	TArray<FString> Slots = UVLSaves::AllSlots();
	if (bSave)
	{
		Slots.SetNum(UVLSaves::NumManualSlots);
	}
	const int32 N = Slots.Num();
	// a match here that loading would leave (asked about first)
	const bool bInMatch = Base == EVLScreen::Pause && Battle && Battle->IsPlaying();

	const float DesignW = 860.f, DesignRow = 66.f, DesignGap = 8.f;
	const FFit Fit(*this, FitScale(DesignW, 92.f + N * (DesignRow + DesignGap) + 40.f + 86.f));
	const float W = U(DesignW), RowH = U(DesignRow), Gap = U(DesignGap);
	const float H = U(92.f) + N * (RowH + Gap) + U(40.f) + U(86.f);
	const float X = PanelX(CentreX, W), Y = FMath::RoundToFloat(FMath::Max((View.Y - H) * 0.5f, U(8.f)));
	Panel(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), true);
	Text(bSave ? TEXT("SAVE GAME") : TEXT("LOAD GAME"), X + W * 0.5f, Y + U(22.f), U(26.f), GoldBright, AlignCentre, Bold, U(5.f));
	Rule(X + U(40.f), Y + U(66.f), W - U(80.f));

	float RY = Y + U(88.f);
	for (int32 i = 0; i < N; ++i, RY += RowH + Gap)
	{
		const FVLSaveInfo Info = UVLSaves::GetInfo(Slots[i]);
		const FBox2D Box(FVector2D(X + U(40.f), RY), FVector2D(X + W - U(40.f), RY + RowH));
		const bool bAsking = SaveAsk == i;
		// a slot can always be saved to; only one with a save that this game reads can be loaded
		const bool bEnabled = bSave || Info.CanLoad();
		const FBtn B = bAsking ? FBtn() : Button(Box, VLId::Screen + 40 + i, bEnabled);
		ButtonFrame(Box, B, bEnabled, bAsking);
		const float Pad = U(18.f), NameW = U(150.f);
		const FLinearColor Name = !bEnabled ? A(Dim, 0.8f) : FMath::Lerp(Parchment, GoldBright, FMath::Max(B.Hot, bAsking ? 1.f : 0.f));
		TextIn(FBox2D(FVector2D(Box.Min.X + Pad, Box.Min.Y), FVector2D(Box.Min.X + Pad + NameW, Box.Max.Y)), UVLSaves::SlotTitle(Slots[i]).ToUpper(), U(17.f), Name, AlignLeft, Bold, U(1.f));
		const float TX = Box.Min.X + Pad + NameW;
		if (bAsking)
		{
			// the question, in the row's own place: written over (Save), or the match in progress left (Load)
			const FString Ask = bSave ? FString(TEXT("Write over this save?")) : FString(TEXT("Load it? What is not saved will be lost."));
			TextIn(FBox2D(FVector2D(TX, Box.Min.Y), FVector2D(Box.Max.X - U(370.f), Box.Max.Y)), Ask, U(16.f), Amber, AlignLeft);
			const float BW = U(170.f), BG = U(10.f), BYy = Box.Min.Y + U(9.f), BHh = RowH - U(18.f);
			const FBox2D No(FVector2D(Box.Max.X - Pad - BW, BYy), FVector2D(Box.Max.X - Pad, BYy + BHh));
			const FBox2D Yes(FVector2D(No.Min.X - BG - BW, BYy), FVector2D(No.Min.X - BG, BYy + BHh));
			if (MenuButton(Yes, VLId::Screen + 47, bSave ? TEXT("OVERWRITE") : TEXT("LOAD"), true, true))
			{
				SaveAsk = INDEX_NONE;
				if (bSave) { Saves->Save(Slots[i], nullptr, true); }
				else { Saves->Load(Slots[i]); }
			}
			else if (MenuButton(No, VLId::Screen + 48, TEXT("CANCEL")))
			{
				SaveAsk = INDEX_NONE;
			}
			continue;
		}
		if (!Info.bExists)
		{
			TextIn(FBox2D(FVector2D(TX, Box.Min.Y), Box.Max - FVector2D(Pad, 0.f)), TEXT("Empty"), U(16.f), A(Dim, 0.85f), AlignLeft);
		}
		else
		{
			// its map and difficulty over the time played and what the kingdom held; when it was saved on the right
			const FString Head = Info.MapTitle.IsEmpty() ? FString(TEXT("Unreadable save")) : FString::Printf(TEXT("%s  ·  %s"), *Info.MapTitle, UVLBattle::DifficultyName(Info.Difficulty));
			Text(Head, TX, Box.Min.Y + U(11.f), U(17.f), bEnabled ? Parchment : A(Parchment, 0.6f), AlignLeft, Bold);
			if (!Info.Problem.IsEmpty())
			{
				Text(Info.Problem, TX, Box.Min.Y + U(37.f), U(14.f), Amber);
			}
			else
			{
				Text(FString::Printf(TEXT("%s played  ·  %d gold  ·  %d food  ·  %d troops"), *PlayedText(Info.Clock), Info.Gold, Info.Food, Info.Pop), TX, Box.Min.Y + U(37.f), U(14.f), Dim);
			}
			TextIn(FBox2D(FVector2D(Box.Max.X - U(260.f), Box.Min.Y), Box.Max - FVector2D(Pad, 0.f)), UVLSaves::DateText(Info.SavedAt), U(15.f), bEnabled ? A(Parchment, 0.9f) : Dim, AlignRight);
		}
		if (!B.bClicked)
		{
			continue;
		}
		Click();
		if (bSave)
		{
			if (Info.bExists) { SaveAsk = i; }                      // a save is there: asked first
			else { Saves->Save(Slots[i], nullptr, true); }
		}
		else if (bInMatch) { SaveAsk = i; }                          // a match is on: asked first
		else { Saves->Load(Slots[i]); }
	}
	// what the last save or load said (for a few seconds), else what the screen does
	const bool bSaid = Now - Saves->LastMessageAt < 6.0 && !Saves->LastMessage.IsEmpty();
	const FString Line = bSaid ? Saves->LastMessage
		: (bSave ? FString(TEXT("F5 saves to the quicksave at any time; the game also saves by itself every few minutes."))
			: FString(TEXT("F9 loads the quicksave. Saves are kept in the game's Saved/SaveGames folder.")));
	Text(Line, X + W * 0.5f, RY + U(6.f), U(14.f), bSaid ? (Saves->bLastFailed ? Amber : GoldBright) : Dim, AlignCentre);
	const float BW = U(220.f);
	if (MenuButton(FBox2D(FVector2D(X + (W - BW) * 0.5f, Y + H - U(74.f)), FVector2D(X + (W + BW) * 0.5f, Y + H - U(24.f))), VLId::Screen + 49, TEXT("BACK")))
	{
		OpenSub(EVLScreen::None);
	}
}
