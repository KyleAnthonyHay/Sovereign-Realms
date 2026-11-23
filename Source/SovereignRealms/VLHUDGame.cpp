// The in-game HUD: resource bar, hints and alerts, minimap, selection panel (troops, or a building with its upgrade
// and recruit buttons), platoon panel, the castle's level card, and the hero view's bits. The main game's
// SRHUDGame.cpp, ported onto UVLBattle / UVLCommand / AVLKing.

#include "VLHUD.h"
#include "VLHUDStyle.h"
#include "SovereignRealms.h"
#include "VLKing.h"
#include "VLGameMode.h"
#include "VLCommand.h"
#include "VLBattle.h"
#include "VLConstruction.h"
#include "VLEnemyAI.h"
#include "VLGrid.h"
#include "VLArcherCombat.h"
#include "VLSwordsmanCombat.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/Canvas.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"

using namespace VLStyle;

namespace
{
	FString Clock(float Seconds)
	{
		const int32 S = FMath::Max(0, FMath::FloorToInt(Seconds));
		return FString::Printf(TEXT("%d:%02d"), S / 60, S % 60);
	}

	EVLIcon FormationIcon(EVLFormation Shape)
	{
		switch (Shape)
		{
		case EVLFormation::Column: return EVLIcon::FormColumn;
		case EVLFormation::Wedge: return EVLIcon::FormWedge;
		case EVLFormation::Square: return EVLIcon::FormSquare;
		case EVLFormation::Loose: return EVLIcon::Pop;
		default: return EVLIcon::FormLine;
		}
	}

	EVLIcon StanceIcon(EVLStance Stance)
	{
		return Stance == EVLStance::Defensive ? EVLIcon::StanceDefensive : (Stance == EVLStance::Hold ? EVLIcon::StanceHold : EVLIcon::StanceAggressive);
	}

	EVLIcon BuildingIcon(EVLBuilding Kind)
	{
		switch (Kind)
		{
		case EVLBuilding::Farm: return EVLIcon::Farm;
		case EVLBuilding::Mine: return EVLIcon::Mine;
		case EVLBuilding::Tower: return EVLIcon::Tower;
		case EVLBuilding::Barracks: return EVLIcon::Barracks;
		case EVLBuilding::Range: return EVLIcon::Range;
		case EVLBuilding::Granary: return EVLIcon::Granary;
		case EVLBuilding::Treasury: return EVLIcon::Treasury;
		default: return EVLIcon::Castle;
		}
	}

	/** 0 swordsman, 1 archer, 2 the king, 3 the spy, 4 a builder. */
	constexpr int32 NumKinds = 5;
	int32 KindIndex(const AVLKing* U)
	{
		const FString& K = U->GetKind();
		return !U->IsTroop() ? 2 : (U->IsRanged() ? 1 : (K == TEXT("Spy") ? 3 : (K == TEXT("Builder") ? 4 : 0)));
	}

	/** The portrait of a kind (KindIndex). */
	EVLPortrait KindPortrait(int32 Kind)
	{
		static const EVLPortrait P[NumKinds] = { EVLPortrait::Swordsman, EVLPortrait::Archer, EVLPortrait::King, EVLPortrait::Spy, EVLPortrait::Builder };
		return P[FMath::Clamp(Kind, 0, NumKinds - 1)];
	}

	bool IsFighting(AVLKing* U)
	{
		const UVLSwordsmanCombat* S = UVLSwordsmanCombat::For(U, false);
		const UVLArcherCombat* B = UVLArcherCombat::For(U, false);
		return (S && S->IsAttacking()) || (B && B->IsAttacking());
	}

	/** A platoon's (or a selection's) kind, as the main game named them. */
	const TCHAR* KindName(int32 Swords, int32 Archers, int32 Kings, int32 Others = 0)
	{
		return Kings > 0 ? TEXT("King's guard") : (Others > 0 || (Swords > 0 && Archers > 0) ? TEXT("Mixed host") : (Archers == 0 ? TEXT("Swordsmen") : TEXT("Archers")));
	}

	/** Liang-Barsky: clips the segment to the box. False if it lies wholly outside. */
	bool ClipSegment(const FBox2D& Box, FVector2D& P0, FVector2D& P1)
	{
		const FVector2D D = P1 - P0;
		float T0 = 0.f, T1 = 1.f;
		const float P[4] = { float(-D.X), float(D.X), float(-D.Y), float(D.Y) };
		const float Q[4] = { float(P0.X - Box.Min.X), float(Box.Max.X - P0.X), float(P0.Y - Box.Min.Y), float(Box.Max.Y - P0.Y) };
		for (int32 i = 0; i < 4; ++i)
		{
			if (FMath::IsNearlyZero(P[i])) { if (Q[i] < 0.f) { return false; } continue; }
			const float R = Q[i] / P[i];
			if (P[i] < 0.f) { if (R > T1) { return false; } T0 = FMath::Max(T0, R); }
			else { if (R < T0) { return false; } T1 = FMath::Min(T1, R); }
		}
		const FVector2D A0 = P0 + D * T0, A1 = P0 + D * T1;
		P0 = A0; P1 = A1;
		return true;
	}

	bool ShiftDown(const APlayerController* PC) { return PC && (PC->IsInputKeyDown(EKeys::LeftShift) || PC->IsInputKeyDown(EKeys::RightShift)); }
	bool CtrlDown(const APlayerController* PC)
	{
		// (not Alt / Option any more: it is held to read a button's card, and a click with it held must stay a plain click)
		return PC && (PC->IsInputKeyDown(EKeys::LeftControl) || PC->IsInputKeyDown(EKeys::RightControl) || PC->IsInputKeyDown(EKeys::LeftCommand)
			|| PC->IsInputKeyDown(EKeys::RightCommand));
	}
}

AActor* AVLHUD::SelectedBuilding() const
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!King || King->IsHeroMode() || !Battle)
	{
		return nullptr;
	}
	AActor* Sel = King->GetSelected();
	return (Sel && !Cast<AVLKing>(Sel) && (Battle->FindBuilding(Sel) || UVLCommand::IsTower(Sel))) ? Sel : nullptr;
}

void AVLHUD::DrawGameHUD()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!PCtrl || !King || !Battle)
	{
		return;
	}
	DrawTopBar();
	const float Y = DrawHints(U(10.f + 54.f + 8.f));
	DrawAlerts(Y);
	MapRect = PlatoonRect = FBox2D(ForceInit);
	bAssignDrawn = false;
	{
		// bottom row, left to right: minimap, the Build button (its menu over the selection panel), selection panel
		// ... platoons on the right edge. The hero view keeps the minimap and the platoon panel (the owner's call,
		// 2026-11-22): the build menu and the selection panel are the overview's.
		const bool bHero = King->IsHeroMode();
		const float M = U(14.f), MapSize = U(266.f);
		const FBox2D MapBox(FVector2D(M, View.Y - M - MapSize), FVector2D(M + MapSize, View.Y - M));
		DrawMinimap(MapBox);
		if (!bHero)
		{
			DrawBuildMenu(MapBox.Max.X + U(8.f), View.Y - M);
			const float SX = MapBox.Max.X + U(8.f) + U(76.f) + U(10.f);
			// (its room: up to the platoon panel, which DrawPlatoonPanel puts 292 wide on the right edge. On a view
			// narrower than about 16:9 that is less than the panel's design width: it is drawn smaller there)
			DrawSelectionPanel(SX, View.Y - M, View.X - M - U(292.f) - U(8.f) - SX);
		}
		DrawPlatoonPanel();
		if (!bHero)
		{
			DrawPlacement();
		}
	}
	if (!bAssignDrawn)
	{
		bAssignOpen = false;        // (the command card with its Assign button is not up: the picker is put away)
	}
	DrawHeroBits();
	DrawCastleCard();
	DrawChipList();
}

// ---------------------------------------------------------------------------- the Builders' / Spy's list

namespace
{
	/** What a unit is doing, for its row of the list: a Builder's job (building, repairing, claiming a mine, walking
	 *  to it), a walk, a fight, a standing order, or idle. */
	FString UnitDoing(const UObject* Context, AVLKing* Un)
	{
		const UVLBattle* Battle = UVLBattle::Get(Context);
		const UVLCommand* Command = UVLCommand::Get(Context);
		if (Cast<APlayerController>(Un->GetController()) && Un->IsHeroMode())
		{
			return TEXT("Played by you");
		}
		if (UVLBuilderWork::IsBuilder(Un))
		{
			const UVLBuilderWork* W = UVLBuilderWork::For(Un, false);
			FString S = Un->IsOnOrder() ? TEXT("Walking") : TEXT("Idle");
			if (const AActor* Job = W ? W->GetJob() : nullptr)
			{
				const FVLBuildingState* St = Battle ? Battle->FindBuilding(Job) : nullptr;
				const bool bAt = UVLBuilderWork::IsAtWork(Un);
				const FString Name = St ? St->Name : FString(TEXT("building"));
				if (St && St->IsSite())
				{
					const bool bMine = St->Kind == EVLBuilding::Mine;
					S = bAt ? FString::Printf(TEXT("%s the %s (%d%%)"), bMine ? TEXT("Claiming") : TEXT("Building"), *Name, FMath::Clamp(FMath::FloorToInt(St->Build * 100.f), 0, 99))
						: FString::Printf(TEXT("Walking to %s the %s"), bMine ? TEXT("claim") : TEXT("build"), *Name);
				}
				else
				{
					S = bAt ? FString::Printf(TEXT("Repairing the %s"), *Name) : FString::Printf(TEXT("Walking to repair the %s"), *Name);
				}
			}
			if (W && W->HasTasks())
			{
				S += FString::Printf(TEXT("  ·  +%d queued"), W->GetTasks().Num());
			}
			return S;
		}
		if (IsFighting(Un))
		{
			return TEXT("Fighting");
		}
		if (const FString Doing = Command ? Command->DescribeOrders({ Un }) : FString(); !Doing.IsEmpty())
		{
			return Doing;
		}
		if (Un->IsGarrisoned())
		{
			return TEXT("On a watch tower");
		}
		return Un->IsOnOrder() ? TEXT("Walking") : TEXT("Idle");
	}
}

void AVLHUD::DrawChipList()
{
	HoverUnit = nullptr;
	if (ChipList == 0)
	{
		return;
	}
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* C = UVLConstruction::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Battle || !C || !Command || !King || King->IsHeroMode() || !TopBarRect.bIsValid || Base != EVLScreen::None)
	{
		ChipList = 0;
		return;
	}
	const bool bBuilders = ChipList == 1;
	TArray<AVLKing*> Who;
	if (bBuilders)
	{
		C->GetBuilders(UVLBattle::Player, Who);
	}
	else
	{
		for (AVLKing* Un : UnitsThisFrame().Live)
		{
			if (Un->IsAlive() && Un->Team == UVLBattle::Player && Un->GetKind() == TEXT("Spy"))
			{
				Who.Add(Un);
			}
		}
	}
	Who.Sort([](const AVLKing& A0, const AVLKing& B0) { return A0.GetDisplayName() < B0.GetDisplayName(); });
	const bool bAll = Who.Num() > 1;
	const float W = U(400.f), Pad = U(8.f), HeadH = U(30.f), RowH = U(46.f), AllH = U(32.f), Gap = U(4.f);
	const float H = HeadH + (bAll ? AllH + Gap : 0.f) + FMath::Max(Who.Num(), 1) * (RowH + Gap) + Pad;
	const float X = FMath::Clamp(FMath::RoundToFloat(ChipListChip.Min.X), U(8.f), FMath::Max(U(8.f), View.X - W - U(8.f))), Y = TopBarRect.Max.Y + U(6.f);
	const FBox2D Box(FVector2D(X, Y), FVector2D(X + W, Y + H));
	HudPanel(Box);
	Text(bBuilders ? TEXT("BUILDERS") : TEXT("SPY"), X + U(14.f), Y + U(7.f), U(15.f), GoldBright, AlignLeft, Bold, U(2.f));
	Text(TEXT("click: go to and select   ·   hover: mark"), Box.Max.X - U(14.f), Y + U(9.f), U(12.f), Dim, AlignRight);
	float RY = Y + HeadH;
	auto GoTo = [&](const TArray<AVLKing*>& Units)
	{
		FVector Mid = FVector::ZeroVector;
		for (const AVLKing* Un : Units) { Mid += Un->GetFeet() / Units.Num(); }
		King->SelectByName(Units[0]->GetDisplayName());
		Command->Select(Units);
		King->LookAt(Mid, -1.f, 1e31f);
		Click();
		ChipList = 0;
		UE_LOG(LogSovereignRealms, Log, TEXT("hud: %s list: went to %s%s"), bBuilders ? TEXT("Builders'") : TEXT("Spy's"), *Units[0]->GetDisplayName(), Units.Num() > 1 ? *FString::Printf(TEXT(" and %d more"), Units.Num() - 1) : TEXT(""));
	};
	if (bAll)
	{
		const FBox2D Row(FVector2D(X + Pad, RY), FVector2D(Box.Max.X - Pad, RY + AllH));
		const FBtn B = Button(Row, VLId::ChipRow);
		Fill(Row.Min.X, Row.Min.Y, Row.Max.X - Row.Min.X, AllH, FMath::Lerp(Inset, ButtonHot, B.Hot * 0.7f));
		TextIn(FBox2D(Row.Min + FVector2D(U(12.f), 0.f), Row.Max), FString::Printf(TEXT("All %d Builders"), Who.Num()), U(14.f), B.bHover ? GoldBright : Parchment, AlignLeft, Bold);
		RY += AllH + Gap;
		if (B.bClicked) { GoTo(Who); return; }
	}
	if (Who.Num() == 0)
	{
		const bool bLocked = !bBuilders && Battle->GetCastleLevel(UVLBattle::Player) < VLRules::SpyCastleLevel;
		TextIn(FBox2D(FVector2D(X + Pad, RY), FVector2D(Box.Max.X - Pad, RY + RowH)), bBuilders ? FString(TEXT("No Builders: train one at the castle"))
			: (bLocked ? FString::Printf(TEXT("Locked: the castle at level %d trains the Spy"), VLRules::SpyCastleLevel) : FString(TEXT("No Spy in the field: train one at the castle"))), U(14.f), Dim, AlignCentre);
	}
	for (int32 i = 0; i < Who.Num() && i < 24; ++i)
	{
		AVLKing* Un = Who[i];
		const FBox2D Row(FVector2D(X + Pad, RY), FVector2D(Box.Max.X - Pad, RY + RowH));
		RY += RowH + Gap;
		const FBtn B = Button(Row, VLId::ChipRow + 1 + i);
		const bool bSel = Command->IsSelected(Un);
		Fill(Row.Min.X, Row.Min.Y, Row.Max.X - Row.Min.X, RowH, bSel ? FLinearColor(0.20f, 0.155f, 0.05f, 0.95f) : FMath::Lerp(Inset, ButtonHot, B.Hot * 0.7f));
		if (bSel || B.bHover) { Outline(Row, bSel ? Gold : A(GoldBright, 0.8f), FMath::Max(1.f, U(1.f))); }
		const float PS = U(36.f);
		Portrait(Un->IsJonathan() ? EVLPortrait::Archer : VLPortraitOf(Un->GetKind()), Row.Min.X + U(6.f), Row.Min.Y + (RowH - PS) * 0.5f, PS);      // (Jonathan: the archer's face until he has a portrait of his own)
		const float TX = Row.Min.X + U(6.f) + PS + U(10.f);
		const float Frac = Un->GetHealthFrac();
		Text(Un->GetDisplayName(), TX, Row.Min.Y + U(4.f), U(15.f), Parchment, AlignLeft, Bold);
		const FString Doing = UnitDoing(this, Un);
		const bool bIdle = Doing.StartsWith(TEXT("Idle"));
		Text(Doing, TX, Row.Min.Y + U(24.f), U(13.f), bIdle ? Amber : (Doing.StartsWith(TEXT("Fighting")) ? Refuse : Dim));
		Text(FString::Printf(TEXT("%.0f / %.0f"), FMath::CeilToFloat(Un->GetHealth()), Un->MaxHealth), Row.Max.X - U(10.f), Row.Min.Y + U(5.f), U(13.f), Frac < HealthBarRed ? Refuse : Parchment, AlignRight, Bold);
		Meter(Row.Max.X - U(10.f) - U(70.f), Row.Min.Y + U(27.f), U(70.f), U(6.f), Frac, Health(Frac));
		if (B.bHover)
		{
			HoverUnit = Un;         // (marked in the world: DrawUnitHighlight)
		}
		if (B.bClicked) { GoTo({ Un }); return; }
	}
	// a click anywhere else puts the list away (its own chip toggles it)
	if (PCtrl && PCtrl->WasInputKeyJustPressed(EKeys::LeftMouseButton) && bMouse && !Box.IsInside(Mouse) && !ChipListChip.IsInside(Mouse))
	{
		ChipList = 0;
	}
}

// ---------------------------------------------------------------------------- the Assign picker

void AVLHUD::DrawAssignPicker(const TArray<AVLKing*>& Units, const FBox2D& Anchor, float Bottom)
{
	UVLCommand* Command = UVLCommand::Get(this);
	bAssignDrawn = true;
	if (!bAssignOpen || !Command)
	{
		return;
	}
	// six chips, one per platoon slot, over the Assign button: a formed platoon shows how many it has (the selection
	// joins it, its members stay), an empty slot reads "new" (the selection forms it)
	const int32 Num = UVLCommand::MaxPlatoons;
	const float CW = U(58.f), CH = U(62.f), Gap = U(6.f), Pad = U(10.f), HeadH = U(26.f);
	const float W = 2.f * Pad + Num * CW + (Num - 1) * Gap, H = HeadH + CH + Pad;
	const float X = FMath::Clamp(FMath::RoundToFloat(Anchor.GetCenter().X - W * 0.5f), U(8.f), FMath::Max(U(8.f), View.X - W - U(8.f))), Y = Bottom - H;
	const FBox2D Box(FVector2D(X, Y), FVector2D(X + W, Y + H));
	HudPanel(Box);
	Text(TEXT("ASSIGN TO PLATOON"), X + Pad, Y + U(6.f), U(13.f), GoldBright, AlignLeft, Bold, U(2.f));
	Text(TEXT("or Ctrl + 1-6"), Box.Max.X - Pad, Y + U(7.f), U(12.f), Dim, AlignRight);
	for (int32 i = 0; i < Num; ++i)
	{
		TArray<AVLKing*> Members;
		Command->GetPlatoon(i, Members);
		// the platoon the selection is already in (all of it): lit, and a click takes the selection out of it
		const bool bIn = Command->AllInPlatoon(i, Units);
		const FBox2D Chip(FVector2D(X + Pad + i * (CW + Gap), Y + HeadH), FVector2D(X + Pad + i * (CW + Gap) + CW, Y + HeadH + CH));
		const FBtn B = Button(Chip, VLId::Assign + i);
		const FLinearColor PCol = PlatoonColor(i);
		ButtonFrame(Chip, B, true, bIn);
		TextIn(FBox2D(Chip.Min + FVector2D(0.f, U(4.f)), FVector2D(Chip.Max.X, Chip.Min.Y + U(36.f))), FString::FromInt(i + 1), U(24.f), Members.Num() > 0 ? PCol : A(PCol, 0.55f), AlignCentre, Black);
		TextIn(FBox2D(FVector2D(Chip.Min.X, Chip.Max.Y - U(24.f)), Chip.Max), Members.Num() > 0 ? FString::Printf(TEXT("%d in it"), Members.Num()) : FString(TEXT("new")), U(12.f),
			Members.Num() > 0 ? Parchment : Dim, AlignCentre);
		if (B.bHover)
		{
			if (bIn)
			{
				SetTooltip(Chip, FString::Printf(TEXT("Leave platoon %d"), i + 1),
					{ Members.Num() > Units.Num() ? FString::Printf(TEXT("The selected troops are taken out of it: its other %d stay."), Members.Num() - Units.Num())
						: FString(TEXT("The selected troops are taken out of it: nobody is left, so it is disbanded.")) });
			}
			else
			{
				SetTooltip(Chip, Members.Num() > 0 ? FString::Printf(TEXT("Join platoon %d   [Ctrl+%d]"), i + 1, i + 1) : FString::Printf(TEXT("Form platoon %d   [Ctrl+%d]"), i + 1, i + 1),
					{ Members.Num() > 0 ? FString::Printf(TEXT("The selected troops join its %d: nobody is put out of it."), Members.Num()) : FString(TEXT("The selected troops become this platoon.")),
					  TEXT("A troop already in another platoon leaves that one.") });
			}
		}
		if (B.bClicked)
		{
			Click();
			if (bIn)
			{
				// the platoon it is already assigned to: clicked again, the selection leaves it (user request 2026-11-23)
				Command->RemoveFromPlatoon(i, Units);
				UE_LOG(LogSovereignRealms, Log, TEXT("hud: Assign: %d unit(s) out of platoon %d (it had %d)"), Units.Num(), i + 1, Members.Num());
			}
			else
			{
				Command->AddToPlatoon(i, Units);
				UE_LOG(LogSovereignRealms, Log, TEXT("hud: Assign: %d unit(s) to platoon %d (it had %d)"), Units.Num(), i + 1, Members.Num());
			}
			bAssignOpen = false;
			return;
		}
	}
	// a click anywhere else puts it away (the Assign button toggles it)
	if (PCtrl && PCtrl->WasInputKeyJustPressed(EKeys::LeftMouseButton) && bMouse && !Box.IsInside(Mouse) && !Anchor.IsInside(Mouse))
	{
		bAssignOpen = false;
	}
}

// ---------------------------------------------------------------------------- the castle's level card

void AVLHUD::CastleUnlocks(int32 From, int32 To, TArray<FUnlock>& Out) const
{
	const VLRules::FLevel& A0 = VLRules::Level(EVLBuilding::Castle, From), &N = VLRules::Level(EVLBuilding::Castle, To);
	Out.Add({ EVLIcon::Pop, FString::Printf(TEXT("Troop ceiling %d > %d   ·   the castle houses %d > %d"), A0.Ceiling, N.Ceiling, A0.Housing, N.Housing), false });
	if (N.Archers != A0.Archers || N.Damage != A0.Damage)
	{
		Out.Add({ EVLIcon::Bow, FString::Printf(TEXT("Archers on its walls %d > %d   ·   arrows %.0f > %.0f"), A0.Archers, N.Archers, A0.Damage, N.Damage), false });
	}
	Out.Add({ EVLIcon::Coin, FString::Printf(TEXT("Stores hold %d > %d gold and food"), A0.Storage, N.Storage), false });
	Out.Add({ EVLIcon::Castle, FString::Printf(TEXT("Walls %.0f > %.0f"), A0.Health, N.Health), false });
	// things new at exactly this level: the storehouses' next levels
	for (int32 L = 2; L <= VLRules::NumLevels(EVLBuilding::Granary); ++L)
	{
		const int32 Need = VLRules::Level(EVLBuilding::Granary, L).CastleLevel;
		if (Need > From && Need <= To)
		{
			Out.Add({ EVLIcon::Granary, FString::Printf(TEXT("Granary and Treasury upgrade to level %d"), L), true });
		}
	}
}

void AVLHUD::DrawCastleCard()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle || !Battle->GetCastle(UVLBattle::Player))
	{
		return;
	}
	const int32 Level = Battle->GetCastleLevel(UVLBattle::Player);
	// a level gained one step at a time is a raise (a jump, or the first look, is a new match: no card)
	if (SeenCastleLevel > 0 && Level == SeenCastleLevel + 1)
	{
		CardLevel = Level;
		CardTime = Now;
	}
	SeenCastleLevel = Level;
	const float Age = float(Now - CardTime), Life = 14.f;
	if (CardLevel <= 1 || Age > Life)
	{
		return;
	}
	const float Alpha = FMath::Clamp(Age / 0.25f, 0.f, 1.f) * FMath::Clamp((Life - Age) / 0.8f, 0.f, 1.f);

	TArray<FUnlock> Lines;
	CastleUnlocks(CardLevel - 1, CardLevel, Lines);
	const float W = U(460.f), RowH = U(30.f), Pad = U(18.f), HeadH = U(74.f), FootH = U(52.f);
	const float H = HeadH + Lines.Num() * RowH + FootH;
	const float X = FMath::RoundToFloat((View.X - W) * 0.5f), Y = FMath::RoundToFloat(View.Y * 0.16f + (1.f - FMath::Clamp(Age / 0.25f, 0.f, 1.f)) * U(16.f));
	const FBox2D Box(FVector2D(X, Y), FVector2D(X + W, Y + H));
	// the card is interface: a click on it (its Onward button above all) must reach the HUD, not the battlefield under it
	Block(Box);
	Fill(X + U(4.f), Y + U(6.f), W, H, FLinearColor(0.f, 0.f, 0.f, 0.4f * Alpha));
	Fill(X, Y, W, H, A(GoldBright, 0.85f * Alpha));
	Fill(X + U(2.f), Y + U(2.f), W - U(4.f), H - U(4.f), A(PanelFill, 0.97f * Alpha));
	Icon(EVLIcon::Crown, X + Pad, Y + U(14.f), U(44.f), FLinearColor(1.f, 1.f, 1.f, Alpha));
	Text(FString::Printf(TEXT("Castle level %d"), CardLevel), X + Pad + U(56.f), Y + U(12.f), U(24.f), A(GoldBright, Alpha), AlignLeft, Bold);
	Text(TEXT("Your kingdom grows. Now available:"), X + Pad + U(56.f), Y + U(44.f), U(14.f), A(Parchment, Alpha));
	float RY = Y + HeadH;
	for (const FUnlock& L : Lines)
	{
		Icon(L.Icon, X + Pad, RY + U(3.f), U(24.f), FLinearColor(1.f, 1.f, 1.f, Alpha));
		float TX = X + Pad + U(34.f);
		if (L.bNew)
		{
			const float NW = TextSize(TEXT("NEW"), U(12.f), Bold).X + U(10.f);
			Fill(TX, RY + U(6.f), NW, U(18.f), A(GoldBright, 0.9f * Alpha));
			Text(TEXT("NEW"), TX + NW * 0.5f, RY + U(7.f), U(12.f), FLinearColor(0.08f, 0.06f, 0.03f, Alpha), AlignCentre, Bold, 0.f, false);
			TX += NW + U(8.f);
		}
		Text(L.Text, TX, RY + U(5.f), U(15.f), A(L.bNew ? GoldBright : Parchment, Alpha), AlignLeft, L.bNew ? Bold : Regular);
		RY += RowH;
	}
	// dismiss: the button, or it fades by itself
	const FBox2D Btn(FVector2D(X + W - Pad - U(120.f), Box.Max.Y - FootH + U(8.f)), FVector2D(X + W - Pad, Box.Max.Y - U(12.f)));
	const FBtn B = Button(Btn, VLId::CastleCard);
	ButtonFrame(Btn, B, true);
	TextIn(Btn, TEXT("Onward"), U(15.f), A(Parchment, Alpha), AlignCentre, Bold);
	Meter(X + Pad, Box.Max.Y - U(28.f), W - Pad * 3.f - U(120.f), U(5.f), 1.f - Age / Life, A(GoldBright, 0.7f * Alpha));
	if (B.bClicked) { Click(); CardTime = -100.0; }
}

// ---------------------------------------------------------------------------- resource bar

void AVLHUD::DrawTopBar()
{
	UVLBattle* Battle = UVLBattle::Get(this);
	TopBarRect = FBox2D(ForceInit);
	if (!Battle || Battle->GetState() == EVLMatch::Idle)
	{
		return;
	}
	const FVLKingdom& K = Battle->GetKingdom(UVLBattle::Player);
	FLinearColor EnemyCol = Dim;
	const FString Enemy = Battle->EnemyStatus(&EnemyCol);
	// top-right: controls, pause (drawn last; the bar keeps clear of them)
	const float Y = U(10.f), BS = U(46.f);
	const FBox2D PauseBox(FVector2D(View.X - U(14.f) - BS, Y + U(4.f)), FVector2D(View.X - U(14.f), Y + U(4.f) + BS));
	const FBox2D HelpBox(PauseBox.Min - FVector2D(BS + U(8.f), 0.f), PauseBox.Max - FVector2D(BS + U(8.f), 0.f));
	// The bar sits in the middle of the view. On a narrow one (4:3, 3:2) its right end would run under the two
	// buttons: it moves left as far as it has to, and where even the room between the left edge and the buttons is
	// less than its width, it is drawn smaller (FFit). On a view with room it is where and as it always was.
	auto BarWidth = [&]()
	{
		const float EnemyW = Enemy.IsEmpty() ? 0.f : U(12.f) + U(30.f) + TextSize(Enemy, U(17.f), Bold).X + U(14.f);
		return U(18.f) + 2.f * U(252.f) + U(176.f) + TopChipsWidth() + U(112.f) + EnemyW;
	};
	const float BarLeft = U(14.f), BarRight = HelpBox.Min.X - U(10.f);
	TOptional<FFit> Fit;
	Fit.Emplace(*this, (BarRight - BarLeft) / FMath::Max(BarWidth(), 1.f));
	const float H = U(54.f);
	const float W = FMath::Min(BarWidth(), BarRight - BarLeft);
	const float X = FMath::Max(FMath::Min(FMath::RoundToFloat((View.X - W) * 0.5f), BarRight - W), BarLeft);
	const FBox2D Bar(FVector2D(X, Y), FVector2D(X + W, Y + H));
	TopBarRect = Bar;
	HudPanel(Bar);
	auto Divider = [&](float AtX) { Fill(AtX, Y + U(11.f), FMath::Max(1.f, U(1.f)), H - U(22.f), A(Bronze, 0.9f)); };
	auto Row = [&](float AtX) { return FBox2D(FVector2D(AtX, Y), FVector2D(AtX + U(400.f), Y + H)); };

	float CX = X + U(18.f);
	for (int32 i = 0; i < 2; ++i)
	{
		const EVLRes Res = i == 0 ? EVLRes::Gold : EVLRes::Food;
		const float Flash = K.Flash[i];
		const float Pulse = K.Pulse[i];
		// Refused purchase: the counter that fell short shakes and burns red. Income landing: the icon swells.
		const float Shake = Flash > 0.f ? FMath::RoundToFloat(FMath::Sin(float(Now) * 62.f) * U(5.f) * Flash) : 0.f;
		const float IS = U(30.f) + (Pulse > 0.5f ? U(4.f) : 0.f);
		Icon(i == 0 ? EVLIcon::Coin : EVLIcon::Food, CX + Shake - (IS - U(30.f)) * 0.5f, Y + (H - IS) * 0.5f, IS);
		const FLinearColor BaseCol = i == 0 ? GoldBright : FoodColor;
		// the stores' limit (the castle's level): shown beside the amount, amber when full (income is being lost)
		const int32 Have = Battle->GetStock(UVLBattle::Player, Res), Store = Battle->GetStorage(UVLBattle::Player, Res);
		const bool bFull = Have >= Store;
		const FLinearColor Color = FMath::Lerp(FMath::Lerp(bFull ? Amber : Parchment, BaseCol, bFull ? 0.f : 0.35f + 0.65f * Pulse), Refuse, FMath::Clamp(Flash * 1.4f, 0.f, 1.f));
		const float AW = TextIn(Row(CX + Shake + U(38.f)), FString::FromInt(Have), U(25.f), Color, AlignLeft, Bold);
		const float SW = TextIn(Row(CX + U(40.f) + AW), FString::Printf(TEXT("/%d"), Store), U(14.f), bFull ? Amber : Dim, AlignLeft);
		TextIn(Row(CX + U(48.f) + AW + SW), FString::Printf(TEXT("+%.0f/min"), Battle->GetIncomePerMinute(UVLBattle::Player, Res)), U(14.f), Dim, AlignLeft);
		if (bInputOpen && bMouse && FBox2D(FVector2D(CX - U(8.f), Y), FVector2D(CX + U(200.f), Y + H)).IsInside(Mouse))
		{
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), i == 0 ? TEXT("Gold") : TEXT("Food"),
				{ i == 0 ? TEXT("Pays for raising buildings a level. Dug by Gold Mines.") : TEXT("Pays for troops. Grown by Farms."),
				  FString::Printf(TEXT("Your stores hold %d; income beyond that is lost."), Store),
				  i == 0 ? TEXT("Raise the castle (or a Treasury) to hold more.") : TEXT("Raise the castle (or a Granary) to hold more.") });
		}
		CX += U(252.f);
		Divider(CX - U(12.f));
	}

	// population: housing taken (troops alive + the ones paid for and still training: their place is held for them)
	// against housing
	{
		const int32 Pop = Battle->GetPopulation(UVLBattle::Player), Queued = Battle->GetQueuedPopulation(UVLBattle::Player), Cap = Battle->GetPopulationCap(UVLBattle::Player);
		const int32 Taken = Pop + Queued;
		Icon(EVLIcon::Pop, CX, Y + (H - U(30.f)) * 0.5f, U(30.f));
		const FLinearColor Color = Taken >= Cap ? Amber : Parchment;
		TextIn(Row(CX + U(38.f)), FString::Printf(TEXT("%d/%d"), Taken, Cap), U(23.f), Color, AlignLeft, Bold);
		if (bInputOpen && bMouse && FBox2D(FVector2D(CX - U(8.f), Y), FVector2D(CX + U(160.f), Y + H)).IsInside(Mouse))
		{
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), TEXT("Population"), {
				FString::Printf(TEXT("%d in the field, %d in training, %d free."), Pop, Queued, FMath::Max(0, Cap - Taken)),
				TEXT("A troop takes its place when you pay for it."), TEXT("Farms and the castle house troops.") });
		}
		CX += U(176.f);
		Divider(CX - U(12.f));
	}

	// the hero, the Builders and the Spy (the main game's Builders and Scout counters; VLHUDBuild.cpp)
	DrawTopChips(CX, Y, H);
	CX += TopChipsWidth();

	// match clock
	Icon(EVLIcon::Clock, CX, Y + (H - U(24.f)) * 0.5f, U(24.f));
	TextIn(Row(CX + U(31.f)), Clock(Battle->GetClock()), U(21.f), Parchment, AlignLeft, Bold);
	CX += U(112.f);

	// the enemy: ready in m:ss, watching, attacking (pulsing red)
	if (!Enemy.IsEmpty())
	{
		Divider(CX - U(12.f));
		const bool bAttack = Enemy.StartsWith(TEXT("Enemy attacking"));
		// dim, amber under a minute, pulsing red while an attack is out
		FLinearColor Col = EnemyCol.R > 0.99f ? Amber : Dim;
		if (bAttack) { Col = FMath::Lerp(Refuse, GoldBright, 0.5f + 0.5f * FMath::Sin(float(Now) * 6.f)); }
		Icon(EVLIcon::RecruitFlag, CX, Y + (H - U(24.f)) * 0.5f, U(24.f), FLinearColor::White, true);
		TextIn(Row(CX + U(30.f)), Enemy, U(17.f), Col, AlignLeft, Bold);
		if (bInputOpen && bMouse && FBox2D(FVector2D(CX - U(8.f), Y), FVector2D(Bar.Max.X, Y + H)).IsInside(Mouse))
		{
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), TEXT("The enemy"), {
				FString::Printf(TEXT("Difficulty: %s."), UVLBattle::DifficultyName(Battle->GetDifficulty())),
				TEXT("Ready in m:ss: its first attack may leave when the count runs out."),
				TEXT("Attacking: an attack or a raid is on its way.") });
		}
	}

	Fit.Reset();

	// top-right: controls, pause
	Block(PauseBox);
	Block(HelpBox);
	const FBtn Help = IconButton(HelpBox, VLId::Help, EVLIcon::Help, nullptr);
	const FBtn Pause = IconButton(PauseBox, VLId::Pause, EVLIcon::Pause, nullptr);
	if (Help.bHover) { SetTooltip(HelpBox, TEXT("Controls"), { TEXT("Every key and mouse command (F1).") }); }
	if (Pause.bHover) { SetTooltip(PauseBox, TEXT("Pause"), { TEXT("Pause menu: restart, maps, settings, quit (Esc).") }); }
	if (Help.bClicked) { Click(); ToggleLegend(); }
	if (Pause.bClicked) { Click(); SetScreen(EVLScreen::Pause); }
}

// ---------------------------------------------------------------------------- hints and alerts

float AVLHUD::DrawHints(float Y)
{
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || !King || King->IsHeroMode())
	{
		return Y;
	}
	FString Hint;
	EVLIcon Which = EVLIcon::Swords;
	FLinearColor Accent = Refuse;
	switch (Command->GetArmed())
	{
	case EVLArm::AttackGround: Hint = TEXT("Attack ground    LMB the ground: the archers shoot there   ·   A: attack-move   ·   RMB / Esc cancel"); break;
	case EVLArm::AttackMove: Hint = TEXT("Attack-move    LMB a destination or a foe   ·   Shift + LMB: more points   ·   RMB / Esc cancel"); break;
	case EVLArm::Patrol: Hint = TEXT("Patrol    LMB: between here and there   ·   Shift + LMB: one more point   ·   RMB / Esc cancel"); Which = EVLIcon::Patrol; Accent = Amber; break;
	case EVLArm::Guard: Hint = TEXT("Guard    LMB one of your buildings or units (a troop in a platoon: the platoon)   ·   RMB / Esc cancel"); Which = EVLIcon::Shield; Accent = Gold; break;
	default: break;
	}
	if (const UVLConstruction* Construction = UVLConstruction::Get(this); Construction && Construction->IsPlacing())
	{
		Hint = FString::Printf(TEXT("Placing: %s    LMB place   ·   Shift + LMB place more   ·   T rotate   ·   RMB / Esc cancel   ·   Q / E: it turns with the view"), VLRules::Name(Construction->GetPlacing()));
		Which = EVLIcon::Hammer;
		Accent = Gold;
	}
	if (!Hint.IsEmpty())
	{
		const FBox2D Box = Pill(Hint, View.X * 0.5f, Y, U(16.f), Which, Accent);
		Y = Box.Max.Y + U(6.f);
	}
	return Y;
}

void AVLHUD::DrawAlerts(float Y)
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle)
	{
		return;
	}
	const TArray<FVLAlert>& Alerts = Battle->GetAlerts();
	for (int32 i = Alerts.Num() - 1; i >= 0; --i)                       // newest on top
	{
		const FVLAlert& Alert = Alerts[i];
		const float Age = float(Now - Alert.Time);
		// in over 150 ms, out over the last second of its six
		const float Alpha = FMath::Clamp(Age / 0.15f, 0.f, 1.f) * FMath::Clamp(6.f - Age, 0.f, 1.f);
		if (Alpha <= 0.f)
		{
			continue;
		}
		EVLIcon Which = EVLIcon::AlertInfo;
		FLinearColor Accent = Gold;
		switch (Alert.Kind)
		{
		case EVLAlert::Attack: Which = EVLIcon::AlertAttack; Accent = Refuse; break;
		case EVLAlert::Lost: Which = EVLIcon::AlertLost; Accent = Refuse; break;
		case EVLAlert::Good: Which = EVLIcon::AlertDone; Accent = Good; break;
		default:
			if (Alert.Text.StartsWith(TEXT("Housing full"))) { Which = EVLIcon::AlertPop; Accent = Amber; }
			break;
		}
		const float Slide = (1.f - FMath::Clamp(Age / 0.15f, 0.f, 1.f)) * U(8.f);
		const FBox2D Box = Pill(Alert.Text, View.X * 0.5f, Y - Slide, U(17.f), Which, Accent, Alpha);
		Y = Box.Max.Y + Slide + U(6.f);
	}
}

// ---------------------------------------------------------------------------- minimap

static TAutoConsoleVariable<int32> CVarMinimapFast(TEXT("vl.Opt.MinimapFast"), 1,
	TEXT("1: the minimap's picture is captured three times with lighting, shadows and Lumen off. 0: as it was (every frame for 1.5 s, everything on). Read when a match starts."));

void AVLHUD::CaptureMinimap(const FBox2D& World)
{
	// The main game's minimap had a picture of its map made by its generator; here every map gets one of its own:
	// the ground seen straight down, captured three times in the first 1.5 s (the last one is kept: by then whatever
	// was still loading or compiling at the first is there), units hidden.
	if (!MinimapCapture)
	{
		MinimapBase = NewObject<UTextureRenderTarget2D>(this);
		MinimapBase->RenderTargetFormat = RTF_RGBA8_SRGB;
		MinimapBase->ClearColor = FLinearColor(0.10f, 0.14f, 0.07f, 1.f);
		MinimapBase->InitAutoFormat(512, 512);
		MinimapBase->UpdateResourceImmediate(true);
		MinimapCapture = NewObject<USceneCaptureComponent2D>(this);
		MinimapCapture->ProjectionType = ECameraProjectionMode::Orthographic;
		// the ground's own colours, unlit: a clean map whatever the light and the exposure (lit, a one-off capture came out
		// blown out)
		MinimapCapture->CaptureSource = ESceneCaptureSource::SCS_BaseColor;
		MinimapCapture->bCaptureOnMovement = false;
		MinimapCapture->bCaptureEveryFrame = false;
		// No view state kept between the captures (nothing temporal is wanted of them), and nothing rendered that the
		// base colour does not need: the capture draws the whole map.
		const bool bFast = CVarMinimapFast.GetValueOnGameThread() != 0;
		MinimapCapture->bAlwaysPersistRenderingState = !bFast;
		if (bFast)
		{
			MinimapCapture->ShowFlags.SetLighting(false);
			MinimapCapture->ShowFlags.SetDynamicShadows(false);
			MinimapCapture->ShowFlags.SetGlobalIllumination(false);
			MinimapCapture->ShowFlags.SetLumenGlobalIllumination(false);
			MinimapCapture->ShowFlags.SetLumenReflections(false);
			MinimapCapture->ShowFlags.SetReflectionEnvironment(false);
			MinimapCapture->ShowFlags.SetScreenSpaceReflections(false);
			MinimapCapture->ShowFlags.SetAmbientOcclusion(false);
			MinimapCapture->ShowFlags.SetDistanceFieldAO(false);
			MinimapCapture->ShowFlags.SetSkyLighting(false);
			MinimapCapture->ShowFlags.SetAtmosphere(false);
			MinimapCapture->ShowFlags.SetAntiAliasing(false);
			MinimapCapture->ShowFlags.SetContactShadows(false);
		}
		MinimapCapture->ShowFlags.SetFog(false);
		MinimapCapture->ShowFlags.SetVolumetricFog(false);
		MinimapCapture->ShowFlags.SetBloom(false);
		MinimapCapture->ShowFlags.SetMotionBlur(false);
		MinimapCapture->ShowFlags.SetDepthOfField(false);
		MinimapCapture->ShowFlags.SetLensFlares(false);
		MinimapCapture->TextureTarget = MinimapBase;
		MinimapCapture->SetupAttachment(GetRootComponent());
		MinimapCapture->RegisterComponent();
	}
	const FVector2D C = World.GetCenter();
	MinimapCapture->OrthoWidth = World.GetSize().X;
	// looking straight down with the default camera's way (MapYaw, a quarter turn) up the picture, as the minimap draws it
	MinimapCapture->SetWorldLocationAndRotation(FVector(C.X, C.Y, 40000.f), FRotator(-90.f, MapYaw, 0.f));
	MinimapCapture->HiddenActors.Reset();
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		MinimapCapture->HiddenActors.Add(*It);
	}
	MinimapCaptureAt = Now;
	MinimapShots = 0;
	bMinimapCaptured = true;
	UE_LOG(LogSovereignRealms, Log, TEXT("minimap: capturing %.0f m round %.0f %.0f, up is yaw %.0f (the default camera's yaw %.0f)"), World.GetSize().X / 100.f, C.X, C.Y, MapYaw, King ? King->GetHomeYaw() : 0.f);
}

void AVLHUD::DrawMinimap(const FBox2D& Box)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	const UVLGrid* Grid = UVLGrid::Get(this);
	if (!Battle || !Command)
	{
		return;
	}
	HudPanel(Box);
	const float In = U(7.f);
	MapRect = FBox2D(Box.Min + FVector2D(In, In), Box.Max - FVector2D(In, In));
	const FVector2D Size = MapRect.GetSize();
	// the ground the grid covers, made square round its middle
	FBox2D WorldBox = (Grid && Grid->IsBuilt()) ? Grid->GetBounds() : FBox2D(FVector2D(-9000.f, -9000.f), FVector2D(9000.f, 9000.f));
	{
		const FVector2D C = WorldBox.GetCenter();
		const float Half = FMath::Max(WorldBox.GetExtent().X, WorldBox.GetExtent().Y);
		WorldBox = FBox2D(C - FVector2D(Half, Half), C + FVector2D(Half, Half));
	}
	MapWorld = WorldBox;
	if (!bMinimapCaptured && King)
	{
		// (the owner's call, 2026-11-22: the map lay a quarter turn off the view; it is now the way the default camera
		// looks, to the nearest quarter turn, and stays so when the view is turned)
		MapYaw = FRotator::NormalizeAxis(FMath::RoundToFloat(King->GetHomeYaw() / 90.f) * 90.f);
	}
	if (!bMinimapCaptured && Grid && Grid->IsBuilt())
	{
		CaptureMinimap(WorldBox);
	}
	if (MinimapCapture)
	{
		// three captures (at once, after 0.5 s and after 1.3 s), not one every frame: the picture is base colour, which
		// has no exposure to settle; then the capture component goes and only the render target is kept
		static const double ShotAt[3] = { 0.0, 0.5, 1.3 };
		const double Age = Now - MinimapCaptureAt;
		if (MinimapCapture->bAlwaysPersistRenderingState)          // (vl.Opt.MinimapFast 0: the old way)
		{
			if (Age < 1.5) { MinimapCapture->CaptureSceneDeferred(); }
		}
		else if (MinimapShots < 3 && Age >= ShotAt[MinimapShots])
		{
			++MinimapShots;
			MinimapCapture->CaptureSceneDeferred();
		}
		else if (MinimapShots >= 3 && Age > 1.5)
		{
			MinimapCapture->DestroyComponent();
			MinimapCapture = nullptr;
		}
	}
	const FVector2D WS = WorldBox.GetSize();
	// up the map is the way the default camera looks (MapYaw), right is to its right; everything drawn on the map and
	// every click on it goes through these two
	const FVector2D MapUp(FMath::Cos(FMath::DegreesToRadians(MapYaw)), FMath::Sin(FMath::DegreesToRadians(MapYaw))), MapRight(-MapUp.Y, MapUp.X);
	const FVector2D WC = WorldBox.GetCenter();
	auto ToMap = [&](const FVector2D& W)
	{
		const FVector2D D = W - WC;
		return FVector2D(MapRect.Min.X + (0.5f + FVector2D::DotProduct(D, MapRight) / WS.X) * Size.X, MapRect.Min.Y + (0.5f - FVector2D::DotProduct(D, MapUp) / WS.X) * Size.Y);
	};
	auto ToWorld = [&](const FVector2D& M)
	{
		return WC + MapRight * (((M.X - MapRect.Min.X) / Size.X - 0.5f) * WS.X) + MapUp * ((0.5f - (M.Y - MapRect.Min.Y) / Size.Y) * WS.X);
	};
	auto Dot = [&](const FVector2D& World, float S, const FLinearColor& Color, bool bRim)
	{
		const FVector2D P = ToMap(World);
		if (!MapRect.IsInside(P))
		{
			return;
		}
		const float X = FMath::RoundToFloat(P.X - S * 0.5f), Y = FMath::RoundToFloat(P.Y - S * 0.5f);
		if (bRim) { Rect(X - 1.f, Y - 1.f, S + 2.f, S + 2.f, FLinearColor(0.f, 0.f, 0.f, 0.85f * Color.A)); }
		Rect(X, Y, S, S, Color);
	};

	if (MinimapBase && Now - MinimapCaptureAt > 1.5)
	{
		DrawTexture(MinimapBase, MapRect.Min.X, MapRect.Min.Y, Size.X, Size.Y, 0.f, 0.f, 1.f, 1.f, FLinearColor(0.9f, 0.9f, 0.9f, 1.f), BLEND_Opaque);
	}
	else
	{
		Fill(MapRect.Min.X, MapRect.Min.Y, Size.X, Size.Y, FLinearColor(0.10f, 0.14f, 0.07f, 1.f));
	}

	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		if (!B.IsAlive())
		{
			continue;
		}
		const FVector2D At(B.Actor->GetActorLocation());
		if (B.Team == UVLBattle::Neutral)
		{
			// a contested mine nobody holds: a gold mark, as the main game's free gold veins
			Dot(At, FMath::Max(3.f, U(5.f)), GoldBright, true);
			continue;
		}
		const FLinearColor Color = B.Team == UVLBattle::Player ? TeamBlue : TeamRed;
		const bool bCastle = B.Kind == EVLBuilding::Castle;
		Dot(At, FMath::Max(4.f, U(bCastle ? 13.f : 8.f)), Color, true);
		if (bCastle) { Dot(At, FMath::Max(2.f, U(5.f)), GoldBright, false); }
	}
	const float UnitSize = FMath::Max(2.f, U(3.5f));
	// (B: the frame's one list of the living and the selection as a set; the dots' squares in one batch)
	FVLOptTiming::FScope Timing(FVLOptTiming::Minimap);
	const FUnitFrame& Frame = UnitsThisFrame();
	BeginRects();
	for (const AVLKing* Unit : Frame.Live)
	{
		if (Unit->IsDead())
		{
			continue;
		}
		const bool bEnemy = Unit->Team == UVLBattle::Enemy;
		const bool bSel = !bEnemy && Frame.Selected.Contains(Unit);
		const FLinearColor Col = bSel ? FLinearColor::White : (bEnemy ? FLinearColor(1.f, 0.42f, 0.30f, 1.f) : FLinearColor(0.55f, 0.80f, 1.f, 1.f));
		// King David: a larger mark with a gold rim
		if (!Unit->IsTroop())
		{
			Dot(FVector2D(Unit->GetActorLocation()), FMath::Max(3.f, U(6.5f)), GoldBright, true);
		}
		Dot(FVector2D(Unit->GetActorLocation()), !Unit->IsTroop() ? FMath::Max(2.f, U(4.f)) : UnitSize, Col, false);
	}
	EndRects();

	// alerts with a place ping there: a ring that swells and fades, again and again while the alert lasts
	for (const FVLAlert& Alert : Battle->GetAlerts())
	{
		if (!Alert.bHasAt)
		{
			continue;
		}
		const float Age = float(Now - Alert.Time);
		const bool bBad = Alert.Kind == EVLAlert::Attack || Alert.Kind == EVLAlert::Lost;
		const FLinearColor Color = bBad ? Refuse : (Alert.Kind == EVLAlert::Good ? Good : GoldBright);
		const float T = FMath::Fmod(float(Now) * 1.1f, 1.f);
		const FVector2D P = ToMap(FVector2D(Alert.At));
		const float R = U(5.f) + U(20.f) * T;
		FBox2D PingBox(P - FVector2D(R, R), P + FVector2D(R, R));
		PingBox.Min = FVector2D(FMath::Max(PingBox.Min.X, MapRect.Min.X), FMath::Max(PingBox.Min.Y, MapRect.Min.Y));
		PingBox.Max = FVector2D(FMath::Min(PingBox.Max.X, MapRect.Max.X), FMath::Min(PingBox.Max.Y, MapRect.Max.Y));
		if (PingBox.Max.X > PingBox.Min.X && PingBox.Max.Y > PingBox.Min.Y && Age < 6.f)
		{
			Outline(PingBox, A(Color, (1.f - T) * FMath::Clamp(6.f - Age, 0.f, 1.f)), FMath::Max(1.f, U(2.f)));
			Dot(FVector2D(Alert.At), FMath::Max(3.f, U(5.f)), Color, true);
		}
	}

	// the camera's view of the ground: the four screen corners cast down onto the ground under the view's middle
	int32 VX = 0, VY = 0;
	PCtrl->GetViewportSize(VX, VY);
	FVector Origin, Dir;
	if (VX > 0 && PCtrl->DeprojectScreenPositionToWorld(VX * 0.5f, VY * 0.5f, Origin, Dir))
	{
		// (Windows pass, batch 1: the ground under the view's middle is looked for again only when the view has moved;
		// the same trace, the same answer while it stands)
		static FVector LastOrigin(FVector::ZeroVector), LastDir(FVector::ZeroVector);
		static TWeakObjectPtr<UWorld> LastWorld;
		static float LastPlaneZ = 0.f;
		static uint32 LastRevision = MAX_uint32;
		const UVLGrid* MapGrid = UVLGrid::Get(this);
		const uint32 GridRevision = MapGrid ? MapGrid->GetRevision() : 0;
		float PlaneZ = 0.f;
		if (LastWorld.Get() == GetWorld() && LastRevision == GridRevision && Origin.Equals(LastOrigin, 0.01) && Dir.Equals(LastDir, 1e-6))
		{
			PlaneZ = LastPlaneZ;
		}
		else
		{
			FHitResult Hit;
			FCollisionQueryParams Params(TEXT("MinimapView"), false);
			if (GetWorld()->LineTraceSingleByChannel(Hit, Origin, Origin + Dir * 100000.f, ECC_Visibility, Params))
			{
				PlaneZ = Hit.ImpactPoint.Z;
			}
			LastWorld = GetWorld();
			LastOrigin = Origin;
			LastDir = Dir;
			LastPlaneZ = PlaneZ;
			LastRevision = GridRevision;
		}
		const FVector2D Corners[4] = { FVector2D(0.f, 0.f), FVector2D(VX, 0.f), FVector2D(VX, VY), FVector2D(0.f, VY) };
		FVector2D Points[4];
		bool bOk = true;
		for (int32 i = 0; i < 4 && bOk; ++i)
		{
			bOk = PCtrl->DeprojectScreenPositionToWorld(Corners[i].X, Corners[i].Y, Origin, Dir);
			const float Along = Dir.Z < -0.02f ? FMath::Min(float((PlaneZ - Origin.Z) / Dir.Z), 80000.f) : 80000.f;
			Points[i] = ToMap(FVector2D(Origin + Dir * Along));
		}
		MapViewMid = bOk ? 0.25f * (Points[0] + Points[1] + Points[2] + Points[3]) : FVector2D::ZeroVector;
		if (const AActor* Castle = Battle->GetCastle(UVLBattle::Player))
		{
			MapCastleAt = ToMap(FVector2D(Castle->GetActorLocation()));
		}
		for (int32 i = 0; i < 4 && bOk; ++i)
		{
			FVector2D P0 = Points[i], P1 = Points[(i + 1) % 4];
			if (ClipSegment(MapRect, P0, P1))
			{
				DrawLine(P0.X + 1.f, P0.Y + 1.f, P1.X + 1.f, P1.Y + 1.f, FLinearColor(0.f, 0.f, 0.f, 0.6f), FMath::Max(1.f, U(1.5f)));
				DrawLine(P0.X, P0.Y, P1.X, P1.Y, FLinearColor(1.f, 0.97f, 0.85f, 0.95f), FMath::Max(1.f, U(1.5f)));
			}
		}
	}
	Outline(MapRect, A(Bronze, 0.9f), FMath::Max(1.f, U(1.f)));

	// LMB (and drag): look there. RMB: send the selection there (or move a barracks' / range's rally point).
	const FBtn B = Button(MapRect, VLId::Minimap);
	auto GroundAt = [&](const FVector2D& MapPoint)
	{
		const FVector2D W = ToWorld(FVector2D(FMath::Clamp(MapPoint.X, MapRect.Min.X, MapRect.Max.X), FMath::Clamp(MapPoint.Y, MapRect.Min.Y, MapRect.Max.Y)));
		FVector Ground(W.X, W.Y, 0.f);
		FHitResult Hit;
		FCollisionQueryParams Params(TEXT("MinimapGround"), false);
		if (GetWorld()->LineTraceSingleByChannel(Hit, Ground + FVector(0.f, 0.f, 20000.f), Ground - FVector(0.f, 0.f, 20000.f), ECC_Visibility, Params))
		{
			Ground = Hit.ImpactPoint;
		}
		return Ground;
	};
	if ((B.bHeld && bMouse) || B.bClicked)
	{
		const FVector At = GroundAt(B.bHeld && bMouse ? Mouse : Press.Pos);
		King->LookAt(At, -1.f, TNumericLimits<float>::Max());
		if (B.bClicked)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("minimap: look at %.0f %.0f"), At.X, At.Y);
		}
	}
	if (B.bRightClicked)
	{
		const FVector At = GroundAt(Press.Pos);
		TArray<AVLKing*> Units;
		Command->GetSelection(Units);
		AActor* Sel = SelectedBuilding();
		const FVLBuildingState* St = Battle->FindBuilding(Sel);
		if (Units.Num() > 0)
		{
			// (Shift: Builders put the walk on the end of their queues, as with a Shift + right click in the world)
			if (UVLConstruction* Construction = UVLConstruction::Get(this); ShiftDown(PCtrl) && Construction && Construction->QueueMove(Units, At, false))
			{
				Units.RemoveAll([](const AVLKing* U) { return UVLBuilderWork::IsBuilder(U); });
			}
			Command->OrderMove(Units, At, false, Command->SelectionFormation(), ShiftDown(PCtrl));
			AVLGameMode::PlayOrderSound(this);
			UE_LOG(LogSovereignRealms, Log, TEXT("minimap: %d unit(s) sent to %.0f %.0f"), Units.Num(), At.X, At.Y);
		}
		else if (St && St->Trains() && St->Team == UVLBattle::Player)
		{
			Battle->SetRally(Sel, At);
			AVLGameMode::PlayOrderSound(this);
			UE_LOG(LogSovereignRealms, Log, TEXT("minimap: rally point of %s at %.0f %.0f"), *St->Name, At.X, At.Y);
		}
	}
}

// ---------------------------------------------------------------------------- selection panel

void AVLHUD::DrawSelectionPanel(float X, float Bottom, float Room)
{
	AActor* Building = SelectedBuilding();
	TArray<AVLKing*> Units;
	SelectedUnits(Units);
	if (!Building && Units.Num() == 0)
	{
		return;
	}
	// the player's castle has three buttons (Builder, Spy, upgrade): its panel is wider
	float DesignW = 760.f;
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (const FVLBuildingState* St = Building && Battle ? Battle->FindBuilding(Building) : nullptr; St && St->Kind == EVLBuilding::Castle && St->Team == UVLBattle::Player)
	{
		DesignW += 200.f;
	}
	// Less room than that (a 3:2 or 4:3 view, where the platoon panel stands closer): the whole panel, its cards and
	// its text are drawn smaller, by as much as it takes to end short of the platoon panel. With room: as designed.
	const FFit Fit(*this, Room / FMath::Max(U(DesignW), 1.f));
	const FBox2D Panel(FVector2D(X, Bottom - U(152.f)), FVector2D(X + FMath::Min(U(DesignW), FMath::Max(Room, 1.f)), Bottom));
	HudPanel(Panel);
	if (Building) { DrawBuildingSelection(Panel, Building); }
	else { DrawTroopSelection(Panel, Units); }
}

void AVLHUD::DrawTroopSelection(const FBox2D& Box, const TArray<AVLKing*>& Units)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || Units.Num() == 0)
	{
		return;
	}
	int32 Count[NumKinds] = { 0, 0, 0, 0, 0 }, Total = 0, Engaged = 0;
	float HealthSum = 0.f;
	bool bEnemy = false;
	AVLKing* First = Units[0];
	for (AVLKing* Unit : Units)
	{
		bEnemy |= Unit->Team != UVLBattle::Player;
		++Count[KindIndex(Unit)];
		++Total;
		Engaged += IsFighting(Unit) ? 1 : 0;
		HealthSum += Unit->GetHealthFrac();
	}
	const int32 Platoon = bEnemy ? INDEX_NONE : Command->PlatoonOf(Units);
	const EVLStance Stance = Platoon != INDEX_NONE ? Command->PlatoonStance(Platoon) : First->Stance;
	const EVLFormation Shape = Command->SelectionFormation();

	// command buttons, right-aligned (laid out first: the line under the title must stay clear of them). The main
	// game's card: Attack-move, Stop, Hold, Patrol, Guard, Roam, Stance, Formation, March together, Disband,
	// Dismiss; and this game's Attack ground and Control.
	// (2026-11-22, the owner's call: no Attack-move, Attack ground, Stop or Hold buttons: attacking is a right click,
	// hold is one of the stances; A and S still do attack-move and stop. In their place: Assign, to a platoon.)
	enum ECmd { CmdAssign, CmdPatrol, CmdGuard, CmdRoam, CmdStance, CmdForm, CmdMarch, CmdDisband, CmdDismiss, CmdControl };
	struct FCommand { ECmd Kind; EVLIcon Which; const TCHAR* Key; FString Label; FString Title; FString Line; bool bActive; };
	TArray<FCommand, TInlineAllocator<14>> Commands;
	if (!bEnemy)
	{
		const EVLArm Armed = Command->GetArmed();
		Commands.Add({ CmdAssign, EVLIcon::RecruitFlag, nullptr, TEXT("Assign"), TEXT("Assign to a platoon   [Ctrl + 1-6]"),
			TEXT("Pick a platoon: the selected troops join it and its members stay (an empty slot: they form it). A troop in another platoon leaves that one."), bAssignOpen });
		Commands.Add({ CmdPatrol, EVLIcon::Patrol, TEXT("P"), TEXT("Patrol"), TEXT("Patrol   [P]"),
			TEXT("Then click: walk between here and there, fighting what you meet, until given another order. Hold Shift and click several points: a patrol round all of them."), Armed == EVLArm::Patrol });
		if (Command->SelectionCanGuard())
		{
			Commands.Add({ CmdGuard, EVLIcon::Shield, TEXT("V"), TEXT("Guard"), TEXT("Guard   [V]"),
				TEXT("Then click one of your buildings or units: stay by it and fight what comes near (a troop in a platoon: the whole platoon). Or right-click a building, a Builder or King David."), Armed == EVLArm::Guard || Command->GuardWardOf(First) != nullptr });
		}
		if (Count[3] > 0)
		{
			Commands.Add({ CmdRoam, EVLIcon::Patrol, TEXT("O"), TEXT("Roam"), TEXT("Roam   [O]"),
				TEXT("The Spy wanders on its own, to ground it has not been to lately, clear of foes' towers. If it is attacked it runs home to the castle."), Command->IsRoaming(First) });
		}
		Commands.Add({ CmdStance, StanceIcon(Stance), TEXT("G"), TEXT("Stance"), FString::Printf(TEXT("Stance: %s   [G]"), UVLCommand::StanceName(Stance)), TEXT("Aggressive > Defensive > Hold ground."), false });
		Commands.Add({ CmdForm, FormationIcon(Shape), TEXT("F"), Shape == EVLFormation::Loose ? TEXT("Loose") : TEXT("Form"), FString::Printf(TEXT("Formation: %s   [F]"), UVLCommand::FormationName(Shape)),
			TEXT("Click (or F): the next shape, Line > Column > Wedge > Square > Loose (no formation)."), Shape != EVLFormation::Loose });
		if (Total > 1)
		{
			const bool bTogether = Command->SelectionMarchTogether();
			Commands.Add({ CmdMarch, EVLIcon::Pop, TEXT("M"), bTogether ? TEXT("Together") : TEXT("Free"), TEXT("March together   [M]"),
				Shape != EVLFormation::Loose ? TEXT("In formation they always keep the slowest one's pace (King David's, the Spy's are quicker), so the formation holds. Loose (F) lets each march at its own speed.")
				: (bTogether ? TEXT("On: on the march everyone keeps the slowest one's pace, so they arrive together. Click for each at its own speed.")
					: TEXT("Off: each marches at its own speed. Click to keep them together at the slowest one's pace.")), bTogether });
		}
		if (Platoon != INDEX_NONE)
		{
			Commands.Add({ CmdDisband, EVLIcon::Disband, TEXT("Del"), TEXT("Disband"), TEXT("Disband platoon   [Delete]"), TEXT("Break up the platoon. The troops stay selected."), false });
		}
		if (Units.ContainsByPredicate([](const AVLKing* U) { return U->IsTroop(); }))
		{
			const bool bAsked = Command->IsDismissAsked();
			Commands.Add({ CmdDismiss, EVLIcon::Cancel, TEXT("K"), bAsked ? TEXT("Sure?") : TEXT("Dismiss"), TEXT("Dismiss   [K]"),
				bAsked ? TEXT("Click (or K) again to dismiss the selected troops. They are gone for good: no refund.")
					: TEXT("Send the selected troops away (one that is stuck, say). Asks first. No refund. King David stays."), bAsked });
		}
		if (Total == 1 && First != King)
		{
			Commands.Add({ CmdControl, EVLIcon::Crown, TEXT("Enter"), TEXT("Control"), TEXT("Take control   [Enter]"), TEXT("Play this one yourself (or double-click it). Tab: the overview again."), false });
		}
	}
	// a long row packs tighter (the main game's)
	const float BS = Commands.Num() > 11 ? U(42.f) : (Commands.Num() > 9 ? U(46.f) : U(52.f));
	const float Gap = Commands.Num() > 11 ? U(4.f) : (Commands.Num() > 9 ? U(5.f) : U(6.f));
	const float RowX = Box.Max.X - U(16.f) - Commands.Num() * (BS + Gap) + Gap;

	const float X = Box.Min.X + U(18.f), Y = Box.Min.Y + U(12.f);
	FString Title = Total == 1 ? First->GetDisplayName() : FString::Printf(TEXT("%d Troops"), Total);
	if (bEnemy && !Title.StartsWith(TEXT("Enemy"))) { Title = TEXT("Enemy ") + Title; }
	if (Platoon != INDEX_NONE) { Title = KindName(Count[0], Count[1], Count[2], Count[3] + Count[4]); }
	const float TitleW = Text(Title, X, Y, U(22.f), bEnemy ? FLinearColor(1.f, 0.55f, 0.45f, 1.f) : GoldBright, AlignLeft, Bold);
	// a platoon's leader: a crown after the title of one selected alone, and who leads on the platoon's line
	const int32 OwnPlatoon = bEnemy || Total != 1 ? INDEX_NONE : Command->PlatoonIndexOf(First);
	const bool bLeads = OwnPlatoon != INDEX_NONE && Command->GetPlatoonLeader(OwnPlatoon) == First;
	if (bLeads)
	{
		Icon(EVLIcon::Crown, X + TitleW + U(8.f), Y + U(1.f), U(22.f));
	}
	const AVLKing* PlatoonLeader = Platoon != INDEX_NONE ? Command->GetPlatoonLeader(Platoon) : nullptr;
	const FString LedBy = Platoon == INDEX_NONE ? FString() : (PlatoonLeader ? FString::Printf(TEXT("  ·  led by %s"), PlatoonLeader == King ? TEXT("you") : *PlatoonLeader->GetDisplayName())
		: FString(TEXT("  ·  no leader")));
	FString SubLine = bEnemy ? FString(TEXT("Enemy troops: right-click to attack"))
		: (Platoon != INDEX_NONE ? FString::Printf(TEXT("Platoon %d%s  ·  %s  ·  %s"), Platoon + 1, *LedBy, UVLCommand::FormationName(Shape), UVLCommand::StanceName(Stance))
			: (bLeads ? FString::Printf(TEXT("Leader of platoon %d  ·  Stance: %s"), OwnPlatoon + 1, UVLCommand::StanceName(Stance))
				: FString::Printf(TEXT("Stance: %s   ·   Ctrl+1-6 joins a platoon"), UVLCommand::StanceName(Stance))));
	if (Total == 1 && First->IsGarrisoned()) { SubLine = TEXT("On the watch tower's lookout   ·   ") + SubLine; }
	else if (const FString Doing = bEnemy ? FString() : Command->DescribeOrders(Units); !Doing.IsEmpty()) { SubLine = Doing + TEXT("   ·   ") + SubLine; }
	// the command row takes the right of the panel: a hint that would run under it is dropped (its first part stays)
	const float SubRoom = (Commands.Num() > 0 ? RowX : Box.Max.X) - X - U(12.f);
	while (TextSize(SubLine, U(14.f)).X > SubRoom)
	{
		const int32 Cut = SubLine.Find(TEXT("  ·  "), ESearchCase::CaseSensitive, ESearchDir::FromEnd);     // (either spacing)
		if (Cut <= 0) { break; }
		SubLine.LeftInline(Cut);
		SubLine.TrimEndInline();
	}
	Text(SubLine, X, Y + U(29.f), U(14.f), Dim);

	// who is in the selection: a portrait and a count per troop type
	int32 Kinds = 0;
	for (int32 t = 0; t < NumKinds; ++t) { Kinds += Count[t] > 0 ? 1 : 0; }
	bool bCompact = Kinds >= 3;
	{
		// (a long command row: smaller, so the portraits stay clear of it)
		float Need = 0.f;
		for (int32 t = 0; t < NumKinds; ++t) { Need += Count[t] > 0 ? U(46.f + 4.f + 22.f) + TextSize(FString::Printf(TEXT("×%d"), Count[t]), U(23.f), Bold).X : 0.f; }
		bCompact |= Commands.Num() > 0 && X + Need > RowX - U(8.f);
	}
	const float PS = bCompact ? U(30.f) : U(46.f), PT = bCompact ? U(16.f) : U(23.f);
	float PX = X;
	for (int32 t = 0; t < NumKinds; ++t)
	{
		if (Count[t] == 0) { continue; }
		Portrait(KindPortrait(t), PX, Y + (bCompact ? U(60.f) : U(52.f)), PS, FLinearColor::White, bEnemy);
		if (PlatoonLeader && KindIndex(PlatoonLeader) == t)
		{
			Icon(EVLIcon::Crown, PX + PS - U(14.f), Y + (bCompact ? U(60.f) : U(52.f)) - U(6.f), U(18.f));     // (the leader is one of these)
		}
		PX += PS + U(4.f);
		PX += Text(FString::Printf(TEXT("×%d"), Count[t]), PX, Y + (bCompact ? U(65.f) : U(61.f)), PT, Parchment, AlignLeft, Bold) + (bCompact ? U(9.f) : U(22.f));
	}
	const float Avg = HealthSum / Total;
	const float HY = Box.Max.Y - U(27.f);
	Text(TEXT("Health"), X, HY - U(5.f), U(14.f), Dim);
	Meter(X + U(54.f), HY, U(150.f), U(9.f), Avg, Health(Avg));
	const float HW = Text(Total == 1 ? FString::Printf(TEXT("%.0f / %.0f"), First->GetHealth(), First->MaxHealth) : FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Avg * 100.f)),
		X + U(212.f), HY - U(6.f), U(15.f), Parchment, AlignLeft, Bold);
	if (Engaged > 0)
	{
		Icon(EVLIcon::Swords, X + U(224.f) + HW, HY - U(5.f), U(18.f));
		Text(FString::Printf(TEXT("%d fighting"), Engaged), X + U(246.f) + HW, HY - U(5.f), U(14.f), Amber);
	}
	if (bEnemy)
	{
		return;
	}

	// key for the ground circles: dashed = line of sight, solid = bow range
	{
		const float KY = Box.Max.Y - U(20.f), KS = U(18.f);
		float KX = Box.Max.X - U(16.f);
		auto Key = [&](const TCHAR* Label, const FLinearColor& Color, bool bDashed)
		{
			const float TW = TextSize(Label, U(12.f)).X;
			KX -= TW;
			Text(Label, KX, KY - U(7.f), U(12.f), Dim);
			KX -= U(6.f) + KS;
			for (float d = 0.f; d < KS; d += bDashed ? U(6.f) : KS) { Fill(KX + d, KY, bDashed ? U(4.f) : KS, FMath::Max(1.f, U(2.f)), A(Color, 1.f)); }
			KX -= U(14.f);
		};
		if (Count[1] > 0) { Key(TEXT("range"), RangeCircle, false); }
		Key(TEXT("sight"), SightCircle, true);
	}

	float BX = RowX;
	const float BY = Box.Min.Y + U(44.f);
	// (the Assign picker first: it lies over the panel's top edge, and its chips claim their clicks before the row)
	if (Commands.Num() > 0 && Commands[0].Kind == CmdAssign)
	{
		DrawAssignPicker(Units, FBox2D(FVector2D(RowX, BY), FVector2D(RowX + BS, BY + BS)), Box.Min.Y - U(6.f));
	}
	for (int32 i = 0; i < Commands.Num(); ++i, BX += BS + Gap)
	{
		const FCommand& C = Commands[i];
		const FBox2D CmdBox(FVector2D(BX, BY), FVector2D(BX + BS, BY + BS));
		const FBtn B = IconButton(CmdBox, VLId::Command + i, C.Which, C.Kind == CmdControl ? nullptr : C.Key, true, C.bActive);
		Text(C.Label, BX + BS * 0.5f, BY + BS + U(4.f), BS < U(50.f) ? U(12.f) : U(13.f), B.bHover ? Parchment : Dim, AlignCentre);
		if (B.bHover) { SetTooltip(CmdBox, C.Title, { C.Line }); }
		if (B.bRightClicked && C.Kind == CmdForm) { Click(); Command->CycleFormation(); continue; }
		if (!B.bClicked) { continue; }
		Click();
		switch (C.Kind)
		{
		case CmdAssign:
			bAssignOpen = !bAssignOpen;
			if (UVLConstruction* Construction = UVLConstruction::Get(this); bAssignOpen && Construction)
			{
				Construction->SetMenu(false);       // (the build menu's panel would lie under the picker)
			}
			break;
		case CmdPatrol: Command->Arm(EVLArm::Patrol); break;
		case CmdGuard: Command->Arm(EVLArm::Guard); break;
		case CmdRoam: Command->OrderRoam(Units); AVLGameMode::PlayOrderSound(this); break;
		case CmdMarch: Command->ToggleMarchTogether(); break;
		case CmdDismiss: Command->DismissCommand(); break;
		case CmdStance: Command->CycleStance(); break;
		case CmdForm: Command->CycleFormation(); break;
		case CmdDisband: Command->DisbandPlatoon(Platoon); break;
		case CmdControl: King->TakeControlOf(First); return;
		}
	}
}

void AVLHUD::DrawUpgradeButton(const FBox2D& R, AActor* Building)
{
	// One button for every building with levels (the castle, towers, farms, mines, the barracks and range,
	// storehouses): next level, its price, progress.
	UVLBattle* Battle = UVLBattle::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	if (!St)
	{
		return;
	}
	const int32 L = St->Level;
	const bool bTop = L >= VLRules::NumLevels(St->Kind);
	const bool bBusy = St->UpgradeLeft >= 0.f;
	const VLRules::FLevel& Cur = VLRules::Level(St->Kind, L), &Next = VLRules::Level(St->Kind, L + 1);
	const FVLCost Cost = Next.Cost;
	const bool bGold = Battle->GetStock(UVLBattle::Player, EVLRes::Gold) >= Cost.Gold;
	const bool bFood = Battle->GetStock(UVLBattle::Player, EVLRes::Food) >= Cost.Food;
	// a level that waits for the castle (a storehouse's): shown, locked
	const int32 NeedCastle = Next.CastleLevel;
	const bool bLocked = !bTop && !bBusy && NeedCastle > Battle->GetCastleLevel(UVLBattle::Player);
	const bool bEnabled = !bTop && !bBusy && !bLocked && bGold && bFood;
	FBtn B = Button(R, VLId::Upgrade);
	if (!bEnabled) { B.Hot *= 0.3f; }
	ButtonFrame(R, B, bEnabled || bBusy);
	Icon(St->Kind == EVLBuilding::Castle ? EVLIcon::Crown : BuildingIcon(St->Kind), R.Min.X + U(9.f), R.Min.Y + U(12.f), U(44.f),
		bEnabled || bBusy ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
	const float TX = R.Min.X + U(62.f);
	const bool bNarrow = R.Max.X - R.Min.X < U(185.f);
	const FString Title = bTop ? FString::Printf(TEXT("Level %d (top)"), L) : (bNarrow ? FString::Printf(TEXT("To level %d"), L + 1) : FString::Printf(TEXT("Upgrade to level %d"), L + 1));
	Text(Title, TX, R.Min.Y + U(30.f), U(14.f), bEnabled || bBusy ? Parchment : Dim, AlignLeft, Bold);
	KeyCap(TEXT("U"), R.Max.X - U(6.f), R.Min.Y + U(6.f), bEnabled);
	// what the next level brings, in a few words (and in full in the tooltip)
	FString Gain;
	TArray<FString> Lines;
	switch (St->Kind)
	{
	case EVLBuilding::Castle:
	{
		Gain = FString::Printf(TEXT("troops %d > %d"), Cur.Ceiling, Next.Ceiling);
		TArray<FUnlock> More;
		CastleUnlocks(L, L + 1, More);
		for (const FUnlock& M : More) { Lines.Add((M.bNew ? TEXT("NEW: ") : TEXT("")) + M.Text); }
		break;
	}
	case EVLBuilding::Tower:
		Gain = FString::Printf(TEXT("damage %.0f > %.0f"), Cur.Damage, Next.Damage);
		Lines.Add(FString::Printf(TEXT("Damage %.0f > %.0f   ·   a shot every %.2f > %.2f s"), Cur.Damage, Next.Damage, Cur.Interval, Next.Interval));
		Lines.Add(FString::Printf(TEXT("Reach %.0f > %.0f m   ·   health %.0f > %.0f"), Cur.Range / 100.f, Next.Range / 100.f, Cur.Health, Next.Health));
		Lines.Add(FString::Printf(TEXT("Its own archers %d > %d (one more on the lookout at once)"), VLRules::TowerGuards(L), VLRules::TowerGuards(L + 1)));
		break;
	case EVLBuilding::Barracks:
	case EVLBuilding::Range:
	{
		const FString Troop = UVLBattle::TroopFor(Building);
		const float BaseSeconds = VLRules::Troop(Troop).TrainSeconds;
		const float T0 = BaseSeconds / FMath::Max(Cur.TrainSpeed, 0.1f), T1 = BaseSeconds / FMath::Max(Next.TrainSpeed, 0.1f);
		Gain = FString::Printf(TEXT("trains in %.1f > %.1f s"), T0, T1);
		Lines.Add(FString::Printf(TEXT("A %s every %.1f > %.1f s (%d%% > %d%% speed)"), *Troop, T0, T1, FMath::RoundToInt(Cur.TrainSpeed * 100.f), FMath::RoundToInt(Next.TrainSpeed * 100.f)));
		Lines.Add(FString::Printf(TEXT("Health %.0f > %.0f   ·   it keeps training while it is upgraded"), Cur.Health, Next.Health));
		break;
	}
	case EVLBuilding::Mine:
		Gain = FString::Printf(TEXT("+%d > +%d gold"), Cur.Yield, Next.Yield);
		Lines.Add(FString::Printf(TEXT("Each delivery %d > %d gold (every %.0f s)   ·   health %.0f > %.0f"), Cur.Yield, Next.Yield, VLRules::PayoutInterval, Cur.Health, Next.Health));
		break;
	case EVLBuilding::Farm:
		Gain = FString::Printf(TEXT("+%d > +%d food"), Cur.Yield, Next.Yield);
		Lines.Add(FString::Printf(TEXT("Each harvest %d > %d food (every %.0f s)"), Cur.Yield, Next.Yield, VLRules::PayoutInterval));
		Lines.Add(FString::Printf(TEXT("Houses %d > %d troops   ·   health %.0f > %.0f"), Cur.Housing, Next.Housing, Cur.Health, Next.Health));
		break;
	case EVLBuilding::Granary:
	case EVLBuilding::Treasury:
	{
		const bool bGranary = St->Kind == EVLBuilding::Granary;
		const TCHAR* What = bGranary ? TEXT("food") : TEXT("gold");
		const int32 Kingdom = Battle->GetStorage(UVLBattle::Player, bGranary ? EVLRes::Food : EVLRes::Gold);
		Gain = FString::Printf(TEXT("holds %d > %d %s"), Cur.Storage, Next.Storage, What);
		Lines.Add(FString::Printf(TEXT("Holds %d > %d %s   ·   health %.0f > %.0f"), Cur.Storage, Next.Storage, What, Cur.Health, Next.Health));
		Lines.Add(FString::Printf(TEXT("Your kingdom's %s stores: %d > %d"), What, Kingdom, Kingdom + Next.Storage - Cur.Storage));
		break;
	}
	default: break;
	}
	if (bBusy)
	{
		const float Frac = 1.f - St->UpgradeLeft / FMath::Max(St->UpgradeTotal, 0.1f);
		Meter(TX, R.Min.Y + U(58.f), R.Max.X - TX - U(12.f), U(8.f), Frac, GoldBright);
		Text(FString::Printf(TEXT("%d%%  ·  %s left"), FMath::RoundToInt(Frac * 100.f), *Countdown(St->UpgradeLeft)), R.Min.X + U(10.f), R.Max.Y - U(26.f), U(13.f), Dim);
	}
	else if (bLocked)
	{
		Text(FString::Printf(TEXT("Castle level %d"), NeedCastle), TX, R.Min.Y + U(52.f), U(15.f), Refuse, AlignLeft, Bold);
		Text(Gain, R.Min.X + U(10.f), R.Max.Y - U(26.f), U(13.f), Dim);
	}
	else if (!bTop)
	{
		Icon(EVLIcon::Coin, TX, R.Min.Y + U(53.f), U(17.f));
		Text(FString::FromInt(Cost.Gold), TX + U(21.f), R.Min.Y + U(52.f), U(16.f), bGold ? GoldBright : Refuse, AlignLeft, Bold);
		if (Cost.Food > 0)
		{
			const float FX = TX + U(25.f) + TextSize(FString::FromInt(Cost.Gold), U(16.f), Bold).X + U(8.f);
			Icon(EVLIcon::Food, FX, R.Min.Y + U(53.f), U(17.f));
			Text(FString::FromInt(Cost.Food), FX + U(21.f), R.Min.Y + U(52.f), U(16.f), bFood ? FoodColor : Refuse, AlignLeft, Bold);
		}
		Text(Gain, R.Min.X + U(10.f), R.Max.Y - U(26.f), U(13.f), Dim);
	}
	if (B.bHover)
	{
		if (bTop) { Lines.Reset(); Lines.Add(TEXT("At its highest level.")); }
		else if (bBusy) { Lines.Add(FString::Printf(TEXT("Being raised: %s left."), *Countdown(St->UpgradeLeft))); }
		else if (bLocked) { Lines.Add(FString::Printf(TEXT("Needs the castle at level %d first."), NeedCastle)); }
		else
		{
			Lines.Add(Cost.Food > 0 ? FString::Printf(TEXT("Cost %d gold + %d food   ·   %.0f s."), Cost.Gold, Cost.Food, Next.Seconds)
				: FString::Printf(TEXT("Cost %d gold   ·   %.0f s."), Cost.Gold, Next.Seconds));
		}
		SetTooltip(R, FString::Printf(TEXT("Upgrade the %s   [U]"), VLRules::Name(St->Kind)), Lines);
	}
	if (B.bClicked)
	{
		const bool bDone = Battle->Upgrade(Building);
		if (bDone) { Click(); }
		UE_LOG(LogSovereignRealms, Log, TEXT("hud: upgrade %s -> %s"), *St->Name, bDone ? TEXT("started") : *Battle->UpgradeRefusal(Building));
	}
}

void AVLHUD::DrawLookoutButton(const FBox2D& R, AActor* Tower)
{
	// the watch tower's lookout (this game's own): who mans it, and "send them out"
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return;
	}
	// (the tower's own archers count as manning it, but stay up: "send them out" is for the troops sent up)
	TArray<AVLKing*> Up;
	Command->GetGarrison(Tower, Up);
	const int32 Guards = Up.FilterByPredicate([](const AVLKing* U) { return U->bTowerGuard; }).Num();
	const int32 In = Up.Num(), Cap = Command->TowerCapacity(Tower);
	const bool bEnabled = In > Guards;
	FBtn B = Button(R, VLId::SendOut, bEnabled);
	if (!bEnabled) { B.Hot *= 0.3f; }
	ButtonFrame(R, B, bEnabled);
	const float Lift = B.bHeld ? U(1.f) : 0.f;
	Portrait(EVLPortrait::Archer, R.Min.X + U(9.f), R.Min.Y + U(12.f) + Lift, U(44.f), bEnabled ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
	const float TX = R.Min.X + U(62.f);
	Text(TEXT("Lookout"), TX, R.Min.Y + U(30.f) + Lift, U(14.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
	Icon(EVLIcon::Bow, TX, R.Min.Y + U(53.f) + Lift, U(17.f));
	Text(FString::Printf(TEXT("%d / %d"), In, Cap), TX + U(21.f), R.Min.Y + U(52.f) + Lift, U(16.f), bEnabled ? GoldBright : Dim, AlignLeft, Bold);
	Text(bEnabled ? TEXT("Click: send them out") : TEXT("RMB it with archers"), R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), Dim);
	if (B.bHover)
	{
		SetTooltip(R, FString::Printf(TEXT("Lookout   ·   %d of %d posts manned (%d of the tower's own)"), In, Cap, Guards), {
			TEXT("The tower's own archers (2, +1 a level) stay up there: free, and replaced when they fall."),
			TEXT("Archers sent up shoot from it, to 55 m, and see as far."),
			TEXT("Select archers and right-click the tower to man it."),
			TEXT("Click: the archers sent up come down and form up by the door.") });
	}
	if (B.bClicked)
	{
		Click();
		AVLGameMode::PlayOrderSound(this);
		Command->EmptyTower(Tower);
	}
}

void AVLHUD::DrawBuildingSelection(const FBox2D& Box, AActor* Building)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	const float X = Box.Min.X + U(18.f), Y = Box.Min.Y + U(12.f);
	const float RW = U(190.f), RGap = U(10.f);
	auto RightSlot = [&](int32 FromRight) { const float RX = Box.Max.X - U(16.f) - RW - FromRight * (RW + RGap); return FBox2D(FVector2D(RX, Box.Min.Y + U(16.f)), FVector2D(RX + RW, Box.Max.Y - U(16.f))); };
	// a free gold mine (neutral, or fallen and abandoned): what it gives, and Claim (VLHUDBuild.cpp)
	if (const UVLConstruction* Construction = UVLConstruction::Get(this); Construction && Construction->IsFreeMine(Building))
	{
		DrawClaimPanel(Box, Building);
		return;
	}
	if (!St)
	{
		// a lookout that is not one of the game's buildings
		Icon(EVLIcon::Tower, X, Y, U(42.f));
		Text(King->GetSelectedName(), X + U(52.f), Y - U(2.f), U(22.f), GoldBright, AlignLeft, Bold);
		if (UVLCommand::IsTower(Building)) { DrawLookoutButton(RightSlot(0), Building); }
		return;
	}
	// a site: how far it has risen, who works at it, Cancel (VLHUDBuild.cpp); a finished one of yours: Demolish
	if (DrawSitePanel(Box, Building))
	{
		return;
	}
	DrawRotateTab(Box, Building, DrawDemolishTab(Box, Building));
	const bool bPlayer = St->Team == UVLBattle::Player;
	const bool bNeutral = St->Team == UVLBattle::Neutral;
	const bool bRecruits = bPlayer && St->Trains();
	const bool bUpgradable = bPlayer && VLRules::NumLevels(St->Kind) > 1;
	const int32 NumLevels = VLRules::NumLevels(St->Kind);
	const VLRules::FLevel& Lv = VLRules::Level(St->Kind, St->Level);
	const float MeterW = bRecruits ? U(150.f) : U(260.f);
	const float Frac = St->Health / FMath::Max(St->MaxHealth, 1.f);

	Icon(BuildingIcon(St->Kind), X, Y, U(42.f), FLinearColor::White, St->Team == UVLBattle::Enemy);
	Text(St->Name, X + U(52.f), Y - U(2.f), U(22.f), bPlayer ? GoldBright : (bNeutral ? Parchment : FLinearColor(1.f, 0.55f, 0.45f, 1.f)), AlignLeft, Bold);
	{
		FString SubLine = bPlayer ? TEXT("Your kingdom") : (bNeutral ? TEXT("Neutral: nobody's") : TEXT("Enemy kingdom"));
		if (St->Kind == EVLBuilding::Castle) { SubLine += FString::Printf(TEXT("  ·  level %d of %d  ·  houses %d"), St->Level, NumLevels, Lv.Housing); }
		else if (NumLevels > 1) { SubLine += FString::Printf(TEXT("  ·  level %d of %d"), St->Level, NumLevels); }
		if (Frac < DamagedFraction) { SubLine += TEXT("  ·  badly damaged"); }
		Text(SubLine, X + U(52.f), Y + U(25.f), U(14.f), bPlayer || bNeutral ? Dim : Refuse);
	}

	const float HY = Y + U(56.f);
	Meter(X, HY, MeterW, U(10.f), Frac, Health(Frac));
	Text(FString::Printf(TEXT("%d / %d"), FMath::CeilToInt(St->Health), FMath::RoundToInt(St->MaxHealth)), X + MeterW + U(10.f), HY - U(5.f), U(15.f), Parchment, AlignLeft, Bold);
	const float LY = HY + U(24.f);

	switch (St->Kind)
	{
	case EVLBuilding::Farm:
	case EVLBuilding::Mine:
	{
		const bool bFarm = St->Kind == EVLBuilding::Farm;
		const int32 Amount = FMath::RoundToInt(Lv.Yield * Battle->IncomeScale(St->Team));
		Icon(bFarm ? EVLIcon::Food : EVLIcon::Coin, X, LY, U(20.f));
		Text(bNeutral ? FString::Printf(TEXT("+%d %s every %.0f s to whoever holds it"), Amount, bFarm ? TEXT("food") : TEXT("gold"), VLRules::PayoutInterval)
			: FString::Printf(TEXT("+%d %s every %.0f s"), Amount, bFarm ? TEXT("food") : TEXT("gold"), VLRules::PayoutInterval), X + U(27.f), LY, U(15.f), Parchment);
		if (bUpgradable) { DrawUpgradeButton(RightSlot(0), Building); }
		if (!bNeutral) { Meter(X, LY + U(28.f), MeterW, U(8.f), St->Payout / VLRules::PayoutInterval, bFarm ? FoodColor : Gold); }
		if (Lv.Housing > 0) { Text(FString::Printf(TEXT("Houses %d troops"), Lv.Housing), X + MeterW + U(14.f), LY + U(22.f), U(14.f), Dim); }
		return;
	}
	case EVLBuilding::Tower:
	{
		const int32 Manned = Command ? Command->TowerCount(Building) : 0;
		// its own archers on the lookout, and when a fallen one is replaced
		const int32 Own = St->Guards.FilterByPredicate([](const TWeakObjectPtr<AVLKing>& G) { return G.IsValid() && G->IsAlive(); }).Num();
		const int32 OwnWant = VLRules::TowerGuards(St->Level);
		const FString OwnLine = St->IsSite() ? FString() : (Own < OwnWant && St->IsWorking()
			? FString::Printf(TEXT("   ·   archers %d / %d (next in %.0f s)"), Own, OwnWant, FMath::Max(0.f, St->GuardRestock))
			: FString::Printf(TEXT("   ·   archers %d / %d"), Own, OwnWant));
		Text(FString::Printf(TEXT("Level %d: %.0f damage every %.2f s%s"), St->Level, Lv.Damage, Lv.Interval, *OwnLine), X, LY, U(15.f), Parchment);
		Text(FString::Printf(TEXT("Reach %.0f m (the orange circle)%s"), Lv.Range / 100.f, Manned > 0 && !bPlayer ? *FString::Printf(TEXT("   ·   %d archers on its lookout"), Manned) : TEXT("")),
			X, LY + U(22.f), U(14.f), Dim);
		if (bPlayer)
		{
			if (UVLCommand::IsTower(Building)) { DrawLookoutButton(RightSlot(0), Building); }
			if (bUpgradable) { DrawUpgradeButton(RightSlot(UVLCommand::IsTower(Building) ? 1 : 0), Building); }
		}
		return;
	}
	case EVLBuilding::Granary:
	case EVLBuilding::Treasury:
	{
		// a granary / treasury: what it holds, and how full the kingdom's stores of that resource are
		const bool bGranary = St->Kind == EVLBuilding::Granary;
		const EVLRes Res = bGranary ? EVLRes::Food : EVLRes::Gold;
		Icon(bGranary ? EVLIcon::Food : EVLIcon::Coin, X, LY, U(20.f));
		Text(FString::Printf(TEXT("Holds %d %s"), Lv.Storage, bGranary ? TEXT("food") : TEXT("gold")), X + U(27.f), LY, U(15.f), Parchment);
		if (bPlayer)
		{
			const int32 Have = Battle->GetStock(UVLBattle::Player, Res), Store = Battle->GetStorage(UVLBattle::Player, Res);
			Meter(X, LY + U(28.f), MeterW, U(8.f), Store > 0 ? FMath::Clamp(float(Have) / Store, 0.f, 1.f) : 0.f, Have >= Store ? Amber : (bGranary ? FoodColor : Gold));
			Text(FString::Printf(TEXT("Kingdom: %d / %d"), Have, Store), X + MeterW + U(14.f), LY + U(22.f), U(14.f), Have >= Store ? Amber : Dim);
			if (bUpgradable) { DrawUpgradeButton(RightSlot(0), Building); }
		}
		return;
	}
	case EVLBuilding::Castle:
		Text(bPlayer ? TEXT("The seat of your kingdom. If it falls, you lose.") : TEXT("The enemy's seat. Bring it down to win."), X, LY, U(15.f), Parchment);
		Text(FString::Printf(TEXT("%d archer%s on its walls: %.0f every %.1f s, to %.0f m"), Lv.Archers, Lv.Archers == 1 ? TEXT("") : TEXT("s"), Lv.Damage, Lv.Interval, Lv.Range / 100.f),
			X, LY + U(22.f), U(14.f), Dim);
		if (!bRecruits)
		{
			if (bUpgradable) { DrawUpgradeButton(RightSlot(0), Building); }
			return;
		}
		// ---- the player's castle trains Builders (VLHUDBuild.cpp) and the Spy (the main game's Scout button): locked
		// below a castle level, one at a time, and a wait between two (UVLBattle::SpyRefusal). The upgrade button left
		// of them.
		if (bUpgradable) { DrawUpgradeButton(RightSlot(2), Building); }
		DrawBuilderButton(RightSlot(0), Building);
		{
			const VLRules::FTroop& T = VLRules::Troop(TEXT("Spy"));
			const bool bLocked = Battle->GetCastleLevel(UVLBattle::Player) < VLRules::SpyCastleLevel;
			int32 SQueued = 0;
			const int32 SAlive = Battle->GetSpyCount(UVLBattle::Player, &SQueued);
			const bool bSpyOut = !bLocked && SAlive + SQueued >= VLRules::MaxSpies;
			const int32 WaitSec = !bLocked ? FMath::CeilToInt(Battle->GetSpyCooldown(UVLBattle::Player)) : 0;
			const FString WaitText = FString::Printf(TEXT("%d:%02d"), WaitSec / 60, WaitSec % 60);
			const FString Why = Battle->TrainRefusal(Building);
			const bool bGold = Battle->GetStock(UVLBattle::Player, EVLRes::Gold) >= T.Cost.Gold;
			const bool bFood = Battle->GetStock(UVLBattle::Player, EVLRes::Food) >= T.Cost.Food;
			const bool bHoused = !Why.StartsWith(TEXT("Housing"));
			const bool bEnabled = Why.IsEmpty();
			if (SQueued > 0)
			{
				Portrait(EVLPortrait::Spy, X, LY + U(40.f), U(22.f));
				Text(TEXT("Spy in training"), X + U(27.f), LY + U(43.f), U(13.f), Dim);
				Meter(X + U(128.f), LY + U(48.f), U(110.f), U(7.f), Battle->TrainProgress(Building), GoldBright);
			}
			else if (const int32 BQ = St->Queue.FilterByPredicate([](const FString& K) { return K == TEXT("Builder"); }).Num(); BQ > 0)
			{
				Portrait(EVLPortrait::Builder, X, LY + U(40.f), U(22.f));
				Text(BQ > 1 ? FString::Printf(TEXT("Builders in training x%d"), BQ) : FString(TEXT("Builder in training")), X + U(27.f), LY + U(43.f), U(13.f), Dim);
				Meter(X + U(190.f), LY + U(48.f), U(110.f), U(7.f), Battle->TrainProgress(Building), GoldBright);
			}
			const FBox2D R = RightSlot(1);
			FBtn B = Button(R, VLId::Recruit);
			if (!bEnabled) { B.Hot *= 0.3f; }
			ButtonFrame(R, B, bEnabled);
			const float Since = float(Now - RecruitFlashTime);
			if (Since < 0.22f)
			{
				Fill(R.Min.X, R.Min.Y, RW, R.Max.Y - R.Min.Y, A(bRecruitAccepted ? GoldBright : Refuse, 0.45f * (1.f - Since / 0.22f)));
			}
			const float Lift = B.bHeld ? U(1.f) : 0.f;
			const float PortraitSize = U(48.f);
			Portrait(EVLPortrait::Spy, R.Min.X + U(9.f), R.Min.Y + U(12.f) + Lift, PortraitSize, bEnabled ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
			const float TX = R.Min.X + U(16.f) + PortraitSize;
			Text(TEXT("Spy"), TX, R.Min.Y + U(30.f) + Lift, U(14.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
			const float CY = R.Min.Y + U(52.f) + Lift;
			Icon(EVLIcon::Coin, TX, CY + U(1.f), U(17.f));
			const float GW = Text(FString::FromInt(T.Cost.Gold), TX + U(21.f), CY, U(16.f), bGold ? Gold : Refuse, AlignLeft, Bold);
			Icon(EVLIcon::Food, TX + U(27.f) + GW, CY + U(1.f), U(17.f));
			Text(FString::FromInt(T.Cost.Food), TX + U(48.f) + GW, CY, U(16.f), bFood ? FoodColor : Refuse, AlignLeft, Bold);
			FString Status = FString::Printf(TEXT("Trains in %.0f s"), Battle->TrainSeconds(Building));
			if (bLocked) { Status = FString::Printf(TEXT("Castle level %d"), VLRules::SpyCastleLevel); }
			else if (bSpyOut) { Status = SQueued > 0 ? FString(TEXT("In training")) : (WaitSec > 0 ? FString::Printf(TEXT("In the field  ·  %s"), *WaitText) : FString(TEXT("In the field"))); }
			else if (WaitSec > 0) { Status = FString::Printf(TEXT("Ready in %s"), *WaitText); }
			else if (!bHoused) { Status = TEXT("Housing full"); }
			Text(Status, R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), (!bHoused || bLocked || (WaitSec > 0 && !bSpyOut)) ? Refuse : (bSpyOut ? Amber : Dim));
			if (B.bClicked)
			{
				const int32 Queued = Battle->Train(Building, 1);      // (a kingdom has one Spy: no batch)
				RecruitFlashTime = Now;
				bRecruitAccepted = Queued > 0;
				if (Queued > 0) { Click(); }
				UE_LOG(LogSovereignRealms, Log, TEXT("hud: train 1 Spy at %s -> %d queued%s"), *St->Name, Queued, Queued > 0 ? TEXT("") : *(TEXT(" (") + Why + TEXT(")")));
			}
			if (B.bHover)
			{
				TArray<FString> Lines;
				Lines.Add(TEXT("Very fast and far-sighted, hard for foes to notice. Weak in a fight."));
				Lines.Add(FString::Printf(TEXT("Cost %d gold + %d food   ·   trains in %.0f s   ·   %d housing"), T.Cost.Gold, T.Cost.Food, Battle->TrainSeconds(Building), T.Pop));
				Lines.Add(FString::Printf(TEXT("One Spy at a time   ·   needs the castle at level %d"), VLRules::SpyCastleLevel));
				Lines.Add(FString::Printf(TEXT("A new one can be trained every %d:%02d."), FMath::RoundToInt(VLRules::SpyCooldown) / 60, FMath::RoundToInt(VLRules::SpyCooldown) % 60));
				if (bLocked) { Lines.Add(FString::Printf(TEXT("Locked: raise the castle to level %d."), VLRules::SpyCastleLevel)); }
				else if (bSpyOut) { Lines.Add(SQueued > 0 ? TEXT("Your Spy is in training.") : TEXT("Your Spy is in the field.")); }
				else if (!Why.IsEmpty()) { Lines.Add(Why + TEXT(".")); }
				Lines.Add(TEXT("Play it (Enter): hold the right mouse button to look through its spyglass."));
				SetTooltip(R, TEXT("Spy"), Lines);
			}
		}
		return;
	case EVLBuilding::Hall:
		Text(TEXT("No work of its own, but it can be burned."), X, LY, U(15.f), Parchment);
		return;
	default:
		break;
	}
	if (!bRecruits)
	{
		if (St->Trains())
		{
			Text(FString::Printf(TEXT("Trains %ss."), *UVLBattle::TroopFor(Building)), X, LY, U(15.f), Parchment);
			if (St->Queue.Num() > 0) { Text(FString::Printf(TEXT("%d in training"), St->Queue.Num()), X, LY + U(22.f), U(14.f), Dim); }
		}
		return;
	}

	// ---- the player's barracks / range: the queue on the left, the recruit button on the right
	const FString Troop = UVLBattle::TroopFor(Building);
	const bool bArcher = Troop == TEXT("Archer");
	const TArray<FString>& Queue = St->Queue;
	if (Queue.Num() == 0)
	{
		Text(TEXT("Recruit troops for food."), X, LY, U(15.f), Parchment);
		Text(TEXT("RMB on the ground: rally point"), X, LY + U(19.f), U(13.f), Dim);
	}
	else
	{
		float QX = X + Text(TEXT("Training"), X, LY + U(3.f), U(14.f), Dim) + U(8.f);
		// the one in training is drawn larger and bright; the ones waiting are grouped ("x9"), so a queue of any length fits
		Portrait(bArcher ? EVLPortrait::Archer : EVLPortrait::Swordsman, QX, LY - U(2.f), U(26.f));
		QX += U(29.f);
		if (Queue.Num() > 1)
		{
			Portrait(bArcher ? EVLPortrait::Archer : EVLPortrait::Swordsman, QX, LY + U(2.f), U(20.f), FLinearColor(1.f, 1.f, 1.f, 0.7f));
			QX += U(22.f);
			Text(FString::Printf(TEXT("x%d"), Queue.Num() - 1), QX, LY + U(2.f), U(15.f), Parchment, AlignLeft, Bold);
		}
		Meter(X, LY + U(28.f), U(240.f), U(8.f), Battle->TrainProgress(Building), GoldBright);
	}

	// which platoon its recruits join: none, or 1-6 (Ctrl+1-6 with it selected does the same)
	{
		const float CS = U(17.f), CG = U(3.f), CY2 = LY + U(41.f);
		float CX2 = X + Text(TEXT("Joins"), X, CY2 + U(1.f), U(13.f), Dim) + U(7.f);
		const int32 Assigned = St->FeedPlatoon;
		for (int32 p = -1; p < UVLCommand::MaxPlatoons; ++p)
		{
			const FBox2D Chip(FVector2D(CX2, CY2), FVector2D(CX2 + (p < 0 ? CS * 2.f : CS), CY2 + CS));
			const FBtn CB = Button(Chip, VLId::JoinPlatoon + uint32(p + 1));
			const bool bOn = Assigned == p || (p < 0 && Assigned == INDEX_NONE);
			const FLinearColor PCol = p < 0 ? Parchment : PlatoonColor(p);
			Fill(Chip.Min.X, Chip.Min.Y, Chip.Max.X - Chip.Min.X, CS, bOn ? A(PCol, p < 0 ? 0.35f : 0.85f) : A(FLinearColor::Black, CB.bHover ? 0.55f : 0.35f));
			Outline(Chip, A(PCol, bOn || CB.bHover ? 1.f : 0.45f), FMath::Max(1.f, U(1.5f)));
			Text(p < 0 ? FString(TEXT("none")) : FString::FromInt(p + 1), (Chip.Min.X + Chip.Max.X) * 0.5f, CY2 + U(1.f), U(12.f), bOn && p >= 0 ? FLinearColor::Black : Parchment, AlignCentre, Bold, 0.f, !(bOn && p >= 0));
			if (CB.bHover)
			{
				SetTooltip(Chip, p < 0 ? TEXT("Recruits join no platoon") : FString::Printf(TEXT("Recruits join platoon %d"), p + 1),
					{ p < 0 ? FString(TEXT("They join the platoon flagged in the platoon panel, else go to the rally point, else wait in the yard.")) : FString(TEXT("Each new troop from here joins the platoon and marches to it.")),
					  TEXT("Ctrl+1-6 with this building selected sets it too.") });
			}
			if (CB.bClicked && !bOn) { Click(); Battle->SetFeedPlatoon(Building, p); }
			CX2 = Chip.Max.X + CG;
		}
	}

	// drill it to train faster: left of its recruit button
	if (bUpgradable) { DrawUpgradeButton(RightSlot(1), Building); }
	{
		const VLRules::FTroop& T = VLRules::Troop(Troop);
		const FString Why = Battle->TrainRefusal(Building);
		const bool bFood = Battle->GetStock(UVLBattle::Player, EVLRes::Food) >= T.Cost.Food;
		const bool bHoused = !Why.StartsWith(TEXT("Housing"));
		const bool bEnabled = Why.IsEmpty();
		const FBox2D R = RightSlot(0);
		// always clickable: a refused press shakes the counter that fell short (or says the housing is full)
		FBtn B = Button(R, VLId::Recruit);
		if (!bEnabled) { B.Hot *= 0.3f; }
		ButtonFrame(R, B, bEnabled);
		const float Since = float(Now - RecruitFlashTime);
		if (Since < 0.22f)
		{
			// the press answers at once: gold if it was taken, red if refused
			Fill(R.Min.X, R.Min.Y, RW, R.Max.Y - R.Min.Y, A(bRecruitAccepted ? GoldBright : Refuse, 0.45f * (1.f - Since / 0.22f)));
		}
		const float Lift = B.bHeld ? U(1.f) : 0.f;
		const float PortraitSize = U(48.f);
		Portrait(bArcher ? EVLPortrait::Archer : EVLPortrait::Swordsman, R.Min.X + U(9.f), R.Min.Y + U(12.f) + Lift, PortraitSize, bEnabled ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
		const float TX = R.Min.X + U(16.f) + PortraitSize;
		Text(Troop, TX, R.Min.Y + U(30.f) + Lift, U(14.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
		const float CY = R.Min.Y + U(52.f) + Lift;
		Icon(EVLIcon::Food, TX, CY + U(1.f), U(17.f));
		Text(FString::FromInt(T.Cost.Food), TX + U(21.f), CY, U(16.f), bFood ? FoodColor : Refuse, AlignLeft, Bold);
		const FString Status = !bHoused ? FString(TEXT("Housing full")) : FString::Printf(TEXT("Trains in %.0f s"), Battle->TrainSeconds(Building));
		Text(Status, R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), !bHoused ? Refuse : Dim);
		if (B.bClicked)
		{
			const int32 N = CtrlDown(PCtrl) ? VLRules::RecruitBatchLarge : (ShiftDown(PCtrl) ? VLRules::RecruitBatch : 1);
			const int32 Queued = Battle->Train(Building, N);
			RecruitFlashTime = Now;
			bRecruitAccepted = Queued > 0;
			if (Queued > 0) { Click(); }
			UE_LOG(LogSovereignRealms, Log, TEXT("hud: train %d %s at %s -> %d queued"), N, *Troop, *St->Name, Queued);
		}
		if (B.bHover)
		{
			TArray<FString> Lines;
			Lines.Add(bArcher ? TEXT("Light and quick, with a long reach. Weak up close.") : TEXT("Heavy infantry: holds the line and hits hard."));
			Lines.Add(FString::Printf(TEXT("Cost %d food   ·   trains in %.0f s   ·   %d housing"), T.Cost.Food, Battle->TrainSeconds(Building), T.Pop));
			Lines.Add(FString::Printf(TEXT("Shift+click: %d at once   ·   Ctrl / ") VL_ALT_KEY TEXT("+click: %d"), VLRules::RecruitBatch, VLRules::RecruitBatchLarge));
			if (!bHoused) { Lines.Add(Why + TEXT(".")); }
			SetTooltip(R, Troop, Lines);
		}
	}
}

// ---------------------------------------------------------------------------- platoons

void AVLHUD::DrawPlatoonPanel()
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return;
	}
	const int32 Num = UVLCommand::MaxPlatoons;
	const float W = U(292.f), HeaderH = U(34.f), RowH = U(56.f), EmptyH = U(28.f), Gap = U(4.f), Pad = U(8.f);

	struct FInfo { TArray<AVLKing*> Members; int32 Swords = 0, Archers = 0, Kings = 0, Others = 0, Engaged = 0; float Health = 0.f; };
	TArray<FInfo, TInlineAllocator<6>> Infos;
	int32 Formed = 0;
	float Height = HeaderH + (bPlatoonsCollapsed ? 0.f : Pad);
	for (int32 i = 0; i < Num; ++i)
	{
		FInfo& Info = Infos.AddDefaulted_GetRef();
		Command->GetPlatoon(i, Info.Members);
		for (AVLKing* M : Info.Members)
		{
			const int32 K = KindIndex(M);
			Info.Swords += K == 0;
			Info.Archers += K == 1;
			Info.Kings += K == 2;
			Info.Others += K >= 3;
			Info.Engaged += IsFighting(M) ? 1 : 0;
			Info.Health += M->GetHealthFrac();
		}
		Info.Health = Info.Members.Num() > 0 ? Info.Health / Info.Members.Num() : 0.f;
		Formed += Info.Members.Num() > 0 ? 1 : 0;
		if (!bPlatoonsCollapsed) { Height += (Info.Members.Num() > 0 ? RowH : EmptyH) + Gap; }
	}
	const float X = View.X - U(14.f) - W, Y = View.Y - U(14.f) - Height;
	const FBox2D Box(FVector2D(X, Y), FVector2D(X + W, Y + Height));
	PlatoonRect = Box;
	HudPanel(Box);

	// header: click to fold the panel away
	const FBox2D Header(FVector2D(X, Y), FVector2D(X + W, Y + HeaderH));
	const FBtn HB = Button(Header, VLId::PlatoonHeader);
	TextIn(FBox2D(Header.Min + FVector2D(U(14.f), U(2.f)), Header.Max), TEXT("PLATOONS"), U(15.f), FMath::Lerp(Gold, GoldBright, HB.Hot), AlignLeft, Bold, U(2.f));
	TextIn(FBox2D(Header.Min + FVector2D(U(124.f), U(2.f)), Header.Max), FString::Printf(TEXT("%d / %d"), Formed, Num), U(14.f), Dim, AlignLeft);
	Icon(bPlatoonsCollapsed ? EVLIcon::ChevronUp : EVLIcon::ChevronDown, Header.Max.X - U(30.f), Header.Min.Y + U(9.f), U(18.f), FLinearColor(1.f, 1.f, 1.f, 0.7f + 0.3f * HB.Hot));
	if (HB.bClicked)
	{
		Click();
		bPlatoonsCollapsed = !bPlatoonsCollapsed;
		SaveSettings();
	}
	if (bPlatoonsCollapsed)
	{
		return;
	}

	TArray<AVLKing*> Sel;
	Command->GetSelection(Sel);
	const int32 Selected = Command->PlatoonOf(Sel);
	float RY = Y + HeaderH;
	for (int32 i = 0; i < Num; ++i)
	{
		const FInfo& Info = Infos[i];
		const bool bExists = Info.Members.Num() > 0;
		const float H = bExists ? RowH : EmptyH;
		const FBox2D Row(FVector2D(X + Pad, RY), FVector2D(X + W - Pad, RY + H));
		RY += H + Gap;
		const FBox2D Badge(Row.Min, FVector2D(Row.Min.X + U(26.f), Row.Max.Y));
		if (!bExists)
		{
			Fill(Row.Min.X, Row.Min.Y, Row.Max.X - Row.Min.X, H, A(Inset, 0.6f));
			TextIn(Badge, FString::FromInt(i + 1), U(16.f), A(Dim, 0.7f), AlignCentre, Bold);
			TextIn(FBox2D(Row.Min + FVector2D(U(34.f), 0.f), Row.Max), FString::Printf(TEXT("Ctrl+%d to form"), i + 1), U(14.f), A(Dim, 0.75f), AlignLeft);
			continue;
		}

		// the small buttons (formation, stance, the recruits' flag, disband) claim their clicks before the row itself does
		const int32 NSmall = 4;
		const uint32 SmallIds[NSmall] = { 1, 2, 3, 4 };
		const float SB = U(30.f), SG = U(3.f);
		FBox2D Small[NSmall];
		FBtn SmallB[NSmall];
		for (int32 k = 0; k < NSmall; ++k)
		{
			const float SX = Row.Max.X - U(5.f) - (NSmall - k) * SB - (NSmall - 1 - k) * SG;
			Small[k] = FBox2D(FVector2D(SX, Row.Min.Y + (H - SB) * 0.5f), FVector2D(SX + SB, Row.Min.Y + (H - SB) * 0.5f + SB));
			SmallB[k] = Button(Small[k], VLId::Slot + i * 5 + SmallIds[k]);
		}
		const FBtn RB = Button(Row, VLId::Slot + i * 5);
		const bool bSelected = Selected == i;
		Fill(Row.Min.X, Row.Min.Y, Row.Max.X - Row.Min.X, H, bSelected ? FLinearColor(0.20f, 0.155f, 0.05f, 0.95f) : FMath::Lerp(Inset, ButtonHot, RB.Hot * 0.7f));
		if (bSelected) { Outline(Row, Gold, FMath::Max(1.f, U(1.f))); }
		// the platoon's own colour: the badge behind its number (and its tag over the troops); engaged, the edge burns
		const FLinearColor PCol = PlatoonColor(i);
		Fill(Row.Min.X, Row.Min.Y, U(5.f), H, Info.Engaged > 0 ? A(Refuse, 0.65f + 0.35f * FMath::Sin(float(Now) * 8.f)) : PCol);
		Fill(Badge.Min.X + U(6.f), Badge.Min.Y + U(6.f), Badge.Max.X - Badge.Min.X - U(3.f), H - U(12.f), FLinearColor(PCol.R * 0.28f, PCol.G * 0.28f, PCol.B * 0.28f, 0.95f));
		Outline(FBox2D(Badge.Min + FVector2D(U(6.f), U(6.f)), FVector2D(Badge.Max.X + U(3.f), Badge.Max.Y - U(6.f))), PCol, FMath::Max(1.f, U(1.f)));
		TextIn(FBox2D(Badge.Min + FVector2D(U(4.5f), 0.f), Badge.Max + FVector2D(U(4.5f), 0.f)), FString::FromInt(i + 1), U(20.f), PCol, AlignCentre, Black);
		if (Info.Kings > 0 || (Info.Others == 0 && (Info.Swords == 0 || Info.Archers == 0)))
		{
			Portrait(Info.Kings > 0 ? EVLPortrait::King : (Info.Swords == 0 ? EVLPortrait::Archer : EVLPortrait::Swordsman), Row.Min.X + U(31.f), Row.Min.Y + (H - U(32.f)) * 0.5f, U(32.f));
		}
		else
		{
			Icon(EVLIcon::Pop, Row.Min.X + U(32.f), Row.Min.Y + (H - U(30.f)) * 0.5f, U(30.f));
		}
		// led: a small crown over the portrait (a platoon whose leader fell has none)
		const AVLKing* RowLeader = Command->GetPlatoonLeader(i);
		if (RowLeader)
		{
			Icon(EVLIcon::Crown, Row.Min.X + U(50.f), Row.Min.Y + U(2.f), U(16.f));
		}

		const float TX = Row.Min.X + U(68.f), TW = Small[0].Min.X - TX - U(6.f);
		FString Name = KindName(Info.Swords, Info.Archers, Info.Kings, Info.Others);
		if (TextSize(Name, U(14.f), Bold).X > TW)
		{
			while (Name.Len() > 2 && TextSize(Name + TEXT("…"), U(14.f), Bold).X > TW) { Name.LeftChopInline(1); }
			Name = Name.TrimEnd() + TEXT("…");
		}
		Text(Name, TX, Row.Min.Y + U(4.f), U(14.f), Parchment, AlignLeft, Bold);
		float CX = TX;
		const float CY = Row.Min.Y + U(24.f);
		const int32 Counts[3] = { Info.Swords, Info.Archers, Info.Kings };
		const EVLIcon Icons[3] = { EVLIcon::Shield, EVLIcon::Bow, EVLIcon::Crown };
		for (int32 k = 0; k < 3; ++k)
		{
			if (k >= 2 && Counts[k] == 0) { continue; }
			Icon(Icons[k], CX, CY, U(16.f));
			CX += U(18.f) + Text(FString::FromInt(Counts[k]), CX + U(18.f), CY - U(1.f), U(14.f), Parchment) + U(7.f);
		}
		if (Info.Engaged > 0) { Icon(EVLIcon::Swords, CX, CY, U(16.f), FLinearColor(1.f, 1.f, 1.f, 0.65f + 0.35f * FMath::Sin(float(Now) * 8.f))); }
		Meter(TX, Row.Max.Y - U(9.f), TW - U(4.f), U(4.f), Info.Health, Health(Info.Health));

		const EVLFormation Shape = Command->PlatoonFormation(i);
		const EVLStance Stance = Command->PlatoonStance(i);
		ButtonFrame(Small[0], SmallB[0], true);
		Icon(FormationIcon(Shape), Small[0].Min.X + U(5.f), Small[0].Min.Y + U(5.f), SB - U(10.f), FLinearColor(1.f, 1.f, 1.f, Shape != EVLFormation::Loose ? 1.f : 0.55f));
		ButtonFrame(Small[1], SmallB[1], true);
		Icon(StanceIcon(Stance), Small[1].Min.X + U(5.f), Small[1].Min.Y + U(5.f), SB - U(10.f));
		// the recruits' flag: new troops from every barracks and range join this platoon (one platoon at a time)
		const bool bRecruits = Command->GetRallyPlatoon() == i;
		const bool bFull = bRecruits && Info.Members.Num() >= UVLCommand::RallyPlatoonCap;
		ButtonFrame(Small[2], SmallB[2], true, bRecruits);
		Icon(EVLIcon::RecruitFlag, Small[2].Min.X + U(5.f), Small[2].Min.Y + U(5.f), SB - U(10.f), FLinearColor(1.f, 1.f, 1.f, bRecruits ? 1.f : 0.4f));
		if (SmallB[2].bHover)
		{
			SetTooltip(Small[2], bRecruits ? (bFull ? TEXT("Recruits join here (full)") : TEXT("Recruits join here")) : TEXT("Recruits do not join"),
				{ TEXT("New troops from your barracks and ranges join this platoon and march to it."),
				  FString::Printf(TEXT("One platoon at a time; up to %d troops (then they wait in the yard)."), UVLCommand::RallyPlatoonCap),
				  TEXT("A building's own Joins choice comes first. Click again to clear.") });
		}
		if (SmallB[2].bClicked) { Click(); Command->SetRallyPlatoon(bRecruits ? INDEX_NONE : i); }
		ButtonFrame(Small[3], SmallB[3], true);
		Icon(EVLIcon::Disband, Small[3].Min.X + U(5.f), Small[3].Min.Y + U(5.f), SB - U(10.f));
		if (SmallB[3].bHover) { SetTooltip(Small[3], TEXT("Disband"), { TEXT("Break up the platoon (the troops stay)."), TEXT("A platoon whose troops all fall disbands itself.") }); }
		if (SmallB[3].bClicked) { Click(); Command->DisbandPlatoon(i); continue; }
		if (SmallB[0].bHover) { SetTooltip(Small[0], FString::Printf(TEXT("Formation: %s"), UVLCommand::FormationName(Shape)), { TEXT("Click (or F with it selected): the next shape.") }); }
		if (SmallB[1].bHover) { SetTooltip(Small[1], FString::Printf(TEXT("Stance: %s"), UVLCommand::StanceName(Stance)), { TEXT("Click (or G) to change.") }); }
		if (SmallB[0].bClicked || SmallB[0].bRightClicked) { Click(); Command->CyclePlatoonFormation(i); }
		if (SmallB[1].bClicked) { Click(); Command->CyclePlatoonStance(i); }
		if (RB.bClicked && AltHeld() && Sel.Num() > 0 && Selected != i)
		{
			// Option + click on a platoon's row: the selection guards that platoon (keeps by it, fights what comes at it)
			TArray<AVLKing*> Guards = Sel;
			if (King->IsHeroMode()) { Guards.Remove(King); }
			const int32 N = Command->OrderGuardPlatoon(Guards, i);
			Click(N == 0);
			if (UVLBattle* Battle = UVLBattle::Get(this))
			{
				Battle->PushAlert(N > 0 ? FString::Printf(TEXT("%d guard platoon %d"), N, i + 1) : FString(TEXT("Nobody of the selection can guard that platoon")));
			}
			if (N > 0) { AVLGameMode::PlayOrderSound(this); }
		}
		else if (RB.bClicked)
		{
			// click selects; a second click soon after also brings the camera
			const bool bDouble = LastSlotClicked == i && Now - LastSlotClickTime < 0.35;
			LastSlotClicked = i;
			LastSlotClickTime = Now;
			King->SelectPlatoon(i, bDouble);
		}
		if (RB.bHover && !SmallB[0].bHover && !SmallB[1].bHover && !SmallB[2].bHover && !SmallB[3].bHover)
		{
			SetTooltip(Row, KindName(Info.Swords, Info.Archers, Info.Kings, Info.Others), { FString::Printf(TEXT("%d troops  ·  %d%% health  ·  %s  ·  %s"), Info.Members.Num(), FMath::RoundToInt(Info.Health * 100.f),
				UVLCommand::FormationName(Shape), UVLCommand::StanceName(Stance)),
				RowLeader ? FString::Printf(TEXT("Led by %s: the formation forms up on it"), RowLeader == King ? TEXT("you") : *RowLeader->GetDisplayName())
					: FString(TEXT("No leader: take control of a member, or have the others follow one (right-click it)")),
				FString::Printf(TEXT("Click or press %d to select; twice to go there. ") VL_ALT_KEY TEXT(" + click: the selection guards it."), i + 1) });
		}
	}
}

// ---------------------------------------------------------------------------- this game's own: the hero view

void AVLHUD::DrawHeroBits()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const bool bHero = King->IsHeroMode();
	// the crosshair of the mouse-look hero view
	if (King->IsMouseLooking())
	{
		const float CX = View.X * 0.5f, CY = View.Y * King->CrosshairHeight;
		const FLinearColor Cross(1.f, 0.97f, 0.88f, 0.85f);
		const float L = U(7.f), G = U(4.f), T = FMath::Max(1.f, U(2.f));
		Fill(CX - G - L, CY - T * 0.5f, L, T, Cross);
		Fill(CX + G, CY - T * 0.5f, L, T, Cross);
		Fill(CX - T * 0.5f, CY - G - L, T, L, Cross);
		Fill(CX - T * 0.5f, CY + G, T, L, Cross);
		// The bow's draw, just under the crosshair, while the played archer draws (UVLArcherCombat::GetDrawState): a bar
		// that fills from the button going down to the bow fully drawn. Until then letting go only queues the shot (she
		// finishes the draw first): the bar is white as it fills. Once it is full it turns green, with a tick under it: let go, and the
		// arrow leaves at once. A locked draw (a left click while drawing) shows as the full bar with a paler frame.
		float HintDrop = 0.f;
		if (const UVLArcherCombat* Bow = bHero && !King->IsDead() ? UVLArcherCombat::For(King, false) : nullptr)
		{
			float Drawn = 0.f;
			bool bReady = false;
			if (Bow->GetDrawState(Drawn, bReady))
			{
				const float BW = U(64.f), BH = FMath::Max(3.f, U(5.f)), BX = FMath::RoundToFloat(CX - BW * 0.5f), BY = CY + G + L + U(8.f);
				const float Pulse = bReady ? 0.5f + 0.5f * FMath::Sin(float(GetWorld()->GetRealTimeSeconds()) * 9.f) : 0.f;
				const FLinearColor Ready = FMath::Lerp(Good, FLinearColor(0.62f, 1.f, 0.55f, 1.f), Pulse);
				const FLinearColor Frame = bReady ? (Bow->IsDrawLocked() ? Parchment : Good) : FLinearColor(Dim.R, Dim.G, Dim.B, 0.9f);
				Fill(BX - 1.f, BY - 1.f, BW + 2.f, BH + 2.f, FLinearColor(0.f, 0.f, 0.f, 0.55f));
				Fill(BX, BY, FMath::RoundToFloat(BW * Drawn), BH, bReady ? Ready : FLinearColor(1.f, 1.f, 1.f, 0.92f));
				Outline(FBox2D(FVector2D(BX - 1.f, BY - 1.f), FVector2D(BX + BW + 1.f, BY + BH + 1.f)), Frame, 1.f);
				// the mark at the full draw: a notch at the bar's end, dim until the fill reaches it; then a tick under the bar
				Fill(BX + BW - T, BY - U(3.f), T, BH + U(6.f), bReady ? Ready : FLinearColor(1.f, 1.f, 1.f, 0.6f));
				if (bReady)
				{
					const float S = FMath::Max(2.f, U(2.f)), TY = BY + BH + U(5.f);
					for (int32 i = 0; i < 3; ++i)       // the short stroke down ...
					{
						Fill(CX - S * (4.f - i), TY + S * i, S, S, Ready);
					}
					for (int32 i = 0; i < 5; ++i)       // ... and the long one up
					{
						Fill(CX - S * (1.f - i), TY + S * (3.f - i), S, S, Ready);
					}
				}
				HintDrop = BH + U(bReady ? 22.f : 10.f);
			}
		}
		// what a click does where it points (the hero view's commands, AVLKing::HeroCommands): gold over one of his own
		// that a left click selects, red over a foe the selection would be sent at by a right click
		if (const AVLKing* Aimed = King->GetHeroHover(); Aimed && !King->IsDead())
		{
			const UVLCommand* HintCmd = UVLCommand::Get(this);
			TArray<AVLKing*> Sel;
			if (HintCmd) { HintCmd->GetSelection(Sel); }
			Sel.Remove(King);
			FString Hint;
			FLinearColor HintCol = GoldBright;
			TArray<AVLKing*> Commanded;
			King->HeroCommanded(Commanded);
			if (King->IsHeroHoverSelect() && King->HeroGuardsOnClick(Aimed))
			{
				// troops selected and this one is not among them: they guard it (its platoon, if it is in one)
				const int32 GP = HintCmd ? HintCmd->PlatoonIndexOf(Aimed) : INDEX_NONE;
				const bool bWhole = GP != INDEX_NONE && Sel.ContainsByPredicate([HintCmd, GP](const AVLKing* U2) { return HintCmd->PlatoonIndexOf(U2) != GP; });
				Hint = (bWhole ? FString::Printf(VL_ALT_KEY TEXT("+click: guard platoon %d"), GP + 1) : VL_ALT_KEY TEXT("+click: guard ") + Aimed->GetDisplayName())
					+ TEXT("   ·   Shift+") VL_ALT_KEY TEXT(": add it to the selection");
			}
			else if (King->IsHeroHoverSelect())
			{
				Hint = (HintCmd && HintCmd->IsSelected(Aimed) ? VL_ALT_KEY TEXT("+click: ") + Aimed->GetDisplayName() + TEXT(" (selected; Shift+") VL_ALT_KEY TEXT("+click: let go)")
					: VL_ALT_KEY TEXT("+click: select ") + Aimed->GetDisplayName());
			}
			else if (Commanded.Num() > 0 && Battle && Battle->IsHostile(Aimed, King->Team))
			{
				// (the right click orders the selection only)
				Hint = FString::Printf(VL_ALT_KEY TEXT("+click%s: attack %s   ·   Shift: after the last"), Sel.Num() > 0 ? (King->bRightMouseAims ? TEXT(" / Ctrl+click") : TEXT(" / right click")) : TEXT(""),
					*Aimed->GetDisplayName());
				HintCol = Refuse;
			}
			if (!Hint.IsEmpty())
			{
				const float HS = U(13.f);
				const FVector2D TS = TextSize(Hint, HS);
				const FBox2D HB(FVector2D(CX - TS.X * 0.5f - U(8.f), CY + U(16.f) + HintDrop), FVector2D(CX + TS.X * 0.5f + U(8.f), CY + U(20.f) + TS.Y + U(4.f) + HintDrop));
				Panel(HB, false, 0.7f);
				TextIn(HB, Hint, HS, HintCol, AlignCentre);
			}
		}
	}
	// the mode box, top left: which view, the unit in focus (its portrait, name and health) and who is played. The unit
	// in focus is the first of the selection (in the hero view: the first besides the unit played), else a unit
	// looked at (an enemy's), else the unit played: King David when nothing is selected or he is.
	{
		const UVLCommand* Command = UVLCommand::Get(this);
		TArray<AVLKing*> Sel;
		if (Command)
		{
			Command->GetSelection(Sel);
		}
		Sel.RemoveAll([this, bHero](const AVLKing* U2) { return !U2 || U2->IsDead() || (bHero && U2 == King); });
		AVLKing* Focus = Sel.Num() > 0 ? Sel[0] : nullptr;
		if (!Focus && !bHero)
		{
			if (AVLKing* One = Cast<AVLKing>(King->GetSelected()); One && One != King && One->IsAlive())
			{
				Focus = One;
			}
		}
		const bool bFocusSelected = Focus != nullptr;
		if (!Focus)
		{
			Focus = King;
		}
		const bool bFocusEnemy = Battle && Focus->Team != King->Team;
		ModeBoxUnit = Focus->GetDisplayName() + (bFocusSelected ? FString::Printf(TEXT(" (selected, %d in all)"), FMath::Max(1, Sel.Num())) : FString(TEXT(" (played)")));

		FString Info;
		FLinearColor InfoCol = Parchment;
		if (King->IsDead())
		{
			Info = (Battle && !Battle->GetCastle(King->Team) && Battle->IsBattle()) ? FString(TEXT("King David has fallen, and his castle with him"))
				: FString::Printf(TEXT("King David has fallen: he rises again in %.0f s"), FMath::Max(0.f, VLRules::KingRespawnSeconds - King->DeadFor()));
			InfoCol = Refuse;
		}
		else if (bHero)
		{
			// (only King David draws and sheathes a sword: a swordsman always holds his, a builder carries a hammer)
			Info = TEXT("Playing ") + King->GetDisplayName() + ((!King->IsTroop() && King->IsArmed()) ? TEXT("  ·  sword drawn") : TEXT(""));
		}
		else
		{
			Info = FString::Printf(TEXT("Tab: back to %s"), *King->GetDisplayName());
		}
		// the hero view: whom he commands from here (the crosshair picks), and how
		FString Commanding;
		if (bHero && !King->IsDead())
		{
			const int32 P = Command ? Command->PlatoonIndexOf(King) : INDEX_NONE;
			const bool bLeads = P != INDEX_NONE && Command->GetPlatoonLeader(P) == King;
			bool bFollowers = false;
			TArray<AVLKing*> Commanded;
			King->HeroCommanded(Commanded, &bFollowers);
			Commanding = Sel.Num() > 0
				? FString::Printf(TEXT("Commanding %d  ·  ") VL_ALT_KEY TEXT("+click: attack / move (Shift: queue), a friend: guard it  ·  G: follow me  ·  Esc: let go"), Sel.Num())
				: (bFollowers ? FString::Printf(TEXT("%d follow you  ·  ") VL_ALT_KEY TEXT("+click: attack / move (Shift: queue)"), Commanded.Num())
				: (Commanded.Num() > 0 ? FString::Printf(TEXT("Your platoon (%d)  ·  ") VL_ALT_KEY TEXT("+click: attack / move (Shift: queue)  ·  G: follow me"), Commanded.Num())
				: FString(VL_ALT_KEY TEXT("+click a troop under the crosshair (or 1-6) to command it"))));
			if (bLeads)
			{
				Commanding = FString::Printf(TEXT("Leader of platoon %d  ·  "), P + 1) + Commanding;
			}
		}
		const FString Name = Focus->GetDisplayName();
		const FString More = Sel.Num() > 1 ? FString::Printf(TEXT("+%d selected"), Sel.Num() - 1) : FString();
		const float PS = U(38.f), RowY = U(34.f);
		const float RowW = PS + U(10.f) + TextSize(Name, U(15.f), Bold).X + (More.IsEmpty() ? 0.f : U(10.f) + TextSize(More, U(13.f)).X) + U(16.f) + TextSize(TEXT("100 / 100"), U(13.f), Bold).X;
		const float W = FMath::Max(U(300.f), FMath::Max(RowW, FMath::Max(TextSize(Info, U(14.f)).X, TextSize(Commanding, U(13.f)).X)) + U(36.f));
		const float H = U(Commanding.IsEmpty() ? 102.f : 124.f);
		// top left; under the resource bar's row when a narrow window would have them overlap
		const float BY = (TopBarRect.bIsValid && U(14.f) + W > TopBarRect.Min.X - U(8.f)) ? TopBarRect.Max.Y + U(8.f) : U(10.f);
		const FBox2D Box(FVector2D(U(14.f), BY), FVector2D(U(14.f) + W, BY + H));
		HudPanel(Box);
		Text(bHero ? TEXT("HERO") : TEXT("OVERVIEW"), Box.Min.X + U(16.f), Box.Min.Y + U(8.f), U(18.f), GoldBright, AlignLeft, Bold, U(3.f));
		Text(bFocusSelected ? (bFocusEnemy ? TEXT("LOOKED AT") : TEXT("SELECTED")) : TEXT("PLAYED"), Box.Max.X - U(16.f), Box.Min.Y + U(12.f), U(12.f), Dim, AlignRight, Bold, U(2.f));
		// the unit in focus: portrait, name (and how many more are selected), health
		{
			const float PX = Box.Min.X + U(16.f), PY = Box.Min.Y + RowY;
			const bool bDown = Focus->IsDead();
			Portrait(VLPortraitOf(Focus->GetKind()), PX, PY, PS, bDown ? FLinearColor(0.5f, 0.45f, 0.45f, 0.8f) : FLinearColor::White, bFocusEnemy);
			const float TX = PX + PS + U(10.f), MW = Box.Max.X - U(16.f) - TX;
			const float NW = Text(Name, TX, PY - U(1.f), U(15.f), bFocusEnemy ? Refuse : GoldBright, AlignLeft, Bold);
			if (!More.IsEmpty())
			{
				Text(More, TX + NW + U(10.f), PY + U(1.f), U(13.f), Dim);
			}
			const float Frac = bDown ? 0.f : Focus->GetHealthFrac();
			Text(FString::Printf(TEXT("%.0f / %.0f"), FMath::CeilToFloat(bDown ? 0.f : Focus->GetHealth()), Focus->MaxHealth), Box.Max.X - U(16.f), PY + U(1.f), U(13.f), Frac < HealthBarRed ? Refuse : Parchment, AlignRight, Bold);
			const float Hit = FMath::Clamp(1.f - float(GetWorld()->GetTimeSeconds() - Focus->LastHurtTime) / 0.4f, 0.f, 1.f);
			Meter(TX, PY + U(24.f), MW, U(9.f), Frac, FMath::Lerp(Health(Frac), Refuse, Hit * 0.7f));
		}
		Text(Info, Box.Min.X + U(16.f), Box.Min.Y + RowY + PS + U(6.f), U(14.f), InfoCol);
		if (!Commanding.IsEmpty())
		{
			Text(Commanding, Box.Min.X + U(16.f), Box.Min.Y + RowY + PS + U(28.f), U(13.f), Dim);
		}
	}
	// the controls of the hero view along the bottom
	if (bHero)
	{
		const FString Help = King->IsTroop()
			? (King->IsJonathan()
				? TEXT("WASD move   Shift run   Space jump   Hold right mouse: draw (a long draw), let go: shoot   Left click while drawing: lock the draw   Left click: bash with the bow   J: King David   Tab overview   Esc menu")
				: King->IsRanged()
				? TEXT("WASD move   Hold right mouse: draw, let go: shoot   Left click while drawing: lock the draw (right click shoots, left click lets down)   Left click: bash with the bow   Tab overview   Esc menu")
				: (King->GetKind() == TEXT("Spy")
					? TEXT("WASD move   Shift run   Space jump   Hold right mouse: look through the spyglass (far ahead)   Left click: a light blow   Tab overview   Esc menu")
					: (King->GetKind() == TEXT("Builder")
						? TEXT("WASD move   Shift run   Space jump   Left click: swing the hammer   Tab overview (select the king + Enter to go back to him)   Esc menu")
						: TEXT("WASD move   Shift run   Space jump   Left click swing   ") VL_ALT_KEY TEXT("+click select / command   Tab overview (select the king + Enter to go back to him)   Esc menu"))))
			: TEXT("WASD move   Shift run   Space jump   F draw / sheathe   Left click attack   ") VL_ALT_KEY TEXT("+click select / command (Shift: queue)   Tab overview   Esc menu");
		// between the minimap and the platoon panel (both stay up in the hero view): smaller in a narrow window
		const float SpanL = MapRect.bIsValid ? MapRect.Max.X + U(16.f) : U(14.f), SpanR = PlatoonRect.bIsValid ? PlatoonRect.Min.X - U(10.f) : View.X - U(14.f);
		float P = U(15.f);
		while (P > U(10.f) && TextSize(Help, P).X + U(32.f) > SpanR - SpanL) { P -= 1.f; }
		const float W = TextSize(Help, P).X + U(32.f), H = U(32.f);
		const float Mid = W <= SpanR - SpanL ? (SpanL + SpanR) * 0.5f : View.X * 0.5f;
		// (still too wide for the gap: over the panels, on the row above them)
		const float BaseY = W <= SpanR - SpanL ? View.Y - U(14.f) : FMath::Min(MapRect.bIsValid ? MapRect.Min.Y : View.Y, PlatoonRect.bIsValid ? PlatoonRect.Min.Y : View.Y) - U(10.f);
		const FBox2D Box(FVector2D(FMath::RoundToFloat(Mid - W * 0.5f), BaseY - H), FVector2D(FMath::RoundToFloat(Mid + W * 0.5f), BaseY));
		Panel(Box, false, 0.85f);
		TextIn(Box, Help, P, Parchment, AlignCentre);

		// the played unit's health, front and centre over the line of controls: its portrait, name, bar and numbers
		if (!King->IsDead())
		{
			const float Frac = King->GetHealthFrac();
			const float HW = U(440.f), HH = U(58.f);
			const FBox2D HB(FVector2D(FMath::RoundToFloat(Mid - HW * 0.5f), Box.Min.Y - U(10.f) - HH), FVector2D(FMath::RoundToFloat(Mid + HW * 0.5f), Box.Min.Y - U(10.f)));
			Panel(HB, false, 0.9f);
			Portrait(VLPortraitOf(King->GetKind()), HB.Min.X + U(8.f), HB.Min.Y + U(5.f), U(48.f));
			const float TX = HB.Min.X + U(66.f), MW = HB.Max.X - U(16.f) - TX;
			Text(King->GetDisplayName(), TX, HB.Min.Y + U(7.f), U(15.f), GoldBright, AlignLeft, Bold);
			Text(FString::Printf(TEXT("%.0f / %.0f"), FMath::CeilToFloat(King->GetHealth()), King->MaxHealth), HB.Max.X - U(16.f), HB.Min.Y + U(7.f), U(15.f), Frac < HealthBarRed ? Refuse : Parchment, AlignRight, Bold);
			// a hit flashes the bar red for a moment
			const float Hit = FMath::Clamp(1.f - float(GetWorld()->GetTimeSeconds() - King->LastHurtTime) / 0.4f, 0.f, 1.f);
			Meter(TX, HB.Min.Y + U(33.f), MW, U(13.f), Frac, FMath::Lerp(Health(Frac), Refuse, Hit * 0.7f));
		}
	}
}
