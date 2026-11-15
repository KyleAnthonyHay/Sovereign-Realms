// Copyright Sovereign Realms.
// The in-game HUD: resource bar, hints and alerts, minimap, build menu, selection panel, platoon panel.

#include "Player/SRHUD.h"
#include "Player/SRHUDStyle.h"
#include "Player/SRPlayerController.h"
#include "Player/SRCameraPawn.h"
#include "Units/SRUnit.h"
#include "Buildings/SRBuilding.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRAISubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Battle/SRPlatoonSubsystem.h"
#include "Battle/SRFogSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Common/SRUserSettings.h"
#include "Engine/Canvas.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"

using namespace SRStyle;

namespace
{
	FString Clock(float Seconds)
	{
		const int32 S = FMath::Max(0, FMath::FloorToInt(Seconds));
		return FString::Printf(TEXT("%d:%02d"), S / 60, S % 60);
	}

	ESRIcon FormationIcon(ESRFormationShape Shape)
	{
		switch (Shape)
		{
		case ESRFormationShape::Column: return ESRIcon::FormColumn;
		case ESRFormationShape::Wedge: return ESRIcon::FormWedge;
		case ESRFormationShape::Square: return ESRIcon::FormSquare;
		case ESRFormationShape::Loose: return ESRIcon::Pop;
		default: return ESRIcon::FormLine;
		}
	}

	ESRIcon StanceIcon(ESRStance Stance)
	{
		return Stance == ESRStance::Defensive ? ESRIcon::StanceDefensive : (Stance == ESRStance::HoldGround ? ESRIcon::StanceHold : ESRIcon::StanceAggressive);
	}

	ESRIcon BuildingIcon(ESRBuildingType Type)
	{
		switch (Type)
		{
		case ESRBuildingType::Farm: return ESRIcon::Farm;
		case ESRBuildingType::Mine: return ESRIcon::Mine;
		case ESRBuildingType::Tower: return ESRIcon::Tower;
		case ESRBuildingType::Barracks: return ESRIcon::Barracks;
		case ESRBuildingType::Range: return ESRIcon::Range;
		case ESRBuildingType::Stable: return ESRIcon::Stable;
		case ESRBuildingType::Workshop: return ESRIcon::Workshop;
		case ESRBuildingType::Granary: return ESRIcon::Granary;
		case ESRBuildingType::Treasury: return ESRIcon::Treasury;
		default: return ESRIcon::Castle;
		}
	}

	/** Liang-Barsky: clips the segment to the box. False if it lies wholly outside. */
	bool ClipSegment(const FBox2D& Box, FVector2D& P0, FVector2D& P1)
	{
		const FVector2D D = P1 - P0;
		float T0 = 0.f, T1 = 1.f;
		const float P[4] = { -D.X, D.X, -D.Y, D.Y };
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
}

FBox2D ASRHUD::Pill(const FString& Label, float X, float Y, float Pixels, ESRIcon Which, const FLinearColor& Accent, float Alpha, bool bCentre)
{
	const float IS = FMath::RoundToFloat(Pixels * 1.35f), Pad = FMath::RoundToFloat(Pixels * 0.6f);
	const float H = FMath::RoundToFloat(Pixels * 1.95f);
	const float W = Pad + U(4.f) + IS + Pad * 0.6f + TextSize(Label, Pixels, Bold).X + Pad;
	if (bCentre) { X -= W * 0.5f; }
	X = FMath::RoundToFloat(FMath::Clamp(X, U(6.f), FMath::Max(U(6.f), View.X - W - U(6.f))));
	Y = FMath::RoundToFloat(Y);
	const float B = FMath::Max(1.f, U(1.f));
	Fill(X + B, Y + 2.f * B, W, H, FLinearColor(0.f, 0.f, 0.f, 0.35f * Alpha));
	Fill(X, Y, W, H, A(Accent, 0.75f * Alpha));
	Fill(X + B, Y + B, W - 2.f * B, H - 2.f * B, A(PanelFill, Alpha * 1.05f));
	Fill(X + B, Y + B, U(4.f), H - 2.f * B, A(Accent, Alpha));
	Icon(Which, X + Pad + U(4.f), Y + (H - IS) * 0.5f, IS, FLinearColor(1.f, 1.f, 1.f, Alpha));
	const FBox2D Box(FVector2D(X, Y), FVector2D(X + W, Y + H));
	TextIn(FBox2D(FVector2D(X + Pad + U(4.f) + IS + Pad * 0.6f, Y), Box.Max), Label, Pixels, A(Parchment, Alpha), AlignLeft, Bold);
	return Box;
}

void ASRHUD::DrawGameHUD()
{
	if (!PC) { return; }
	DrawTopBar();
	const float Y = DrawHints(U(10.f + 54.f + 8.f));
	DrawAlerts(Y);

	// bottom row, left to right: minimap, build menu, selection panel ... platoons on the right edge
	const float M = U(14.f), MapSize = U(266.f);
	const FBox2D MapBox(FVector2D(M, View.Y - M - MapSize), FVector2D(M + MapSize, View.Y - M));
	DrawMinimap(MapBox);
	DrawBuildMenu(MapBox.Max.X + U(8.f), View.Y - M);
	const float SX = MapBox.Max.X + U(8.f) + U(76.f) + U(10.f);
	DrawSelectionPanel(FBox2D(FVector2D(SX, View.Y - M - U(152.f)), FVector2D(SX + U(760.f), View.Y - M)));
	DrawPlatoonPanel();
	DrawPlacementCursor();
}

// ---------------------------------------------------------------------------- resource bar

void ASRHUD::DrawTopBar()
{
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Economy || !Battle) { return; }

	const float W = U(940.f), H = U(54.f);
	const float X = FMath::RoundToFloat((View.X - W) * 0.5f), Y = U(10.f);
	const FBox2D Bar(FVector2D(X, Y), FVector2D(X + W, Y + H));
	HudPanel(Bar);
	auto Divider = [&](float AtX) { Fill(AtX, Y + U(11.f), FMath::Max(1.f, U(1.f)), H - U(22.f), A(Bronze, 0.9f)); };
	auto Row = [&](float AtX) { return FBox2D(FVector2D(AtX, Y), FVector2D(AtX + U(400.f), Y + H)); };

	float CX = X + U(18.f);
	for (int32 i = 0; i < 2; ++i)
	{
		const ESRResource Resource = i == 0 ? ESRResource::Gold : ESRResource::Food;
		const float Flash = Economy->GetInsufficientFlash(Resource);
		const float Pulse = Economy->GetIncomePulse(Resource);
		// Refused purchase: the counter that fell short shakes and burns red. Income landing: the icon swells.
		const float Shake = Flash > 0.f ? FMath::RoundToFloat(FMath::Sin(float(Now) * 62.f) * U(5.f) * Flash) : 0.f;
		const float IS = U(30.f) + (Pulse > 0.5f ? U(4.f) : 0.f);
		Icon(i == 0 ? ESRIcon::Coin : ESRIcon::Food, CX + Shake - (IS - U(30.f)) * 0.5f, Y + (H - IS) * 0.5f, IS);
		const FLinearColor Base = i == 0 ? GoldBright : FoodColor;
		// the stores' limit (the castle's level): shown beside the amount, amber when full (income is being lost)
		const int32 Have = Economy->GetResource(ESRTeam::Player, Resource), Store = Economy->GetStorage(ESRTeam::Player, Resource);
		const bool bFull = Have >= Store;
		const FLinearColor Color = FMath::Lerp(FMath::Lerp(bFull ? Amber : Parchment, Base, bFull ? 0.f : 0.35f + 0.65f * Pulse), Refuse, FMath::Clamp(Flash * 1.4f, 0.f, 1.f));
		const float AW = TextIn(Row(CX + Shake + U(38.f)), FString::FromInt(Have), U(25.f), Color, AlignLeft, Bold);
		const float SW = TextIn(Row(CX + U(40.f) + AW), FString::Printf(TEXT("/%d"), Store), U(14.f), bFull ? Amber : Dim, AlignLeft);
		TextIn(Row(CX + U(48.f) + AW + SW), FString::Printf(TEXT("+%.0f/min"), Economy->GetIncomePerMinute(ESRTeam::Player, Resource)), U(14.f), Dim, AlignLeft);
		if (bInputOpen && bMouse && FBox2D(FVector2D(CX - U(8.f), Y), FVector2D(CX + U(200.f), Y + H)).IsInside(Mouse))
		{
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), i == 0 ? TEXT("Gold") : TEXT("Food"),
				{ i == 0 ? TEXT("Pays for buildings. Dug by Gold Mines.") : TEXT("Pays for troops. Grown by Farms."),
				  FString::Printf(TEXT("Your stores hold %d; income beyond that is lost."), Store),
				  i == 0 ? TEXT("Build (and upgrade) a Treasury, or raise the Citadel, to hold more.") : TEXT("Build (and upgrade) a Granary, or raise the Citadel, to hold more.") });
		}
		CX += U(252.f);
		Divider(CX - U(12.f));
	}

	// population: housing taken (troops alive + the ones paid for and still training: their place is held for them)
	// against housing
	{
		const int32 Pop = Economy->GetPopulation(ESRTeam::Player), Queued = Economy->GetQueuedPopulation(ESRTeam::Player), Cap = Economy->GetPopulationCap(ESRTeam::Player);
		const int32 Taken = Pop + Queued;
		const float Flash = Economy->GetPopulationFlash();
		const float Shake = Flash > 0.f ? FMath::RoundToFloat(FMath::Sin(float(Now) * 62.f) * U(5.f) * Flash) : 0.f;
		Icon(ESRIcon::Pop, CX + Shake, Y + (H - U(30.f)) * 0.5f, U(30.f));
		const FLinearColor Color = FMath::Lerp(Taken >= Cap ? Amber : Parchment, Refuse, FMath::Clamp(Flash * 1.4f, 0.f, 1.f));
		TextIn(Row(CX + Shake + U(38.f)), FString::Printf(TEXT("%d/%d"), Taken, Cap), U(23.f), Color, AlignLeft, Bold);
		if (bInputOpen && bMouse && FBox2D(FVector2D(CX - U(8.f), Y), FVector2D(CX + U(160.f), Y + H)).IsInside(Mouse))
		{
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), TEXT("Population"), {
				FString::Printf(TEXT("%d in the field, %d in training, %d free."), Pop, Queued, FMath::Max(0, Cap - Taken)),
				TEXT("A troop takes its place when you pay for it."), TEXT("Farms and the Citadel house troops.") });
		}
		CX += U(176.f);
		Divider(CX - U(12.f));
	}

	// builders: alive (+ in training) against the cap; click to select them
	{
		const USRFeelSettings& F = USRFeelSettings::Get();
		int32 Queued = 0;
		const int32 Alive = Economy->GetBuilderCount(ESRTeam::Player, &Queued);
		const FBox2D Seg(FVector2D(CX - U(8.f), Y), FVector2D(CX + U(130.f), Y + H));
		const FBtn BB = Button(Seg, SRId::Builders);
		if (BB.Hot > 0.f) { Fill(Seg.Min.X, Seg.Min.Y + U(6.f), Seg.Max.X - Seg.Min.X, H - U(12.f), A(ButtonHot, 0.5f * BB.Hot)); }
		Icon(ESRIcon::PortraitBuilder, CX, Y + (H - U(30.f)) * 0.5f, U(30.f));
		const int32 MaxB = Economy->GetMaxBuilders(ESRTeam::Player);
		const FLinearColor Color = Alive == 0 ? Dim : (Alive + Queued >= MaxB ? Amber : Parchment);
		const float BW = TextIn(Row(CX + U(38.f)), FString::Printf(TEXT("%d/%d"), Alive, MaxB), U(23.f), Color, AlignLeft, Bold);
		if (Queued > 0) { TextIn(Row(CX + U(45.f) + BW), FString::Printf(TEXT("+%d"), Queued), U(15.f), Dim, AlignLeft); }
		if (BB.bHover && !bBuilderList)   // (the list itself is open: no tooltip over it)
		{
			const FSRCost& Cost = F.CostFor(ESRUnitType::Builder);
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), TEXT("Builders"),
				{ FString::Printf(TEXT("Builders / most you may have (%d; raising the Citadel allows more)."), MaxB), TEXT("They raise buildings outside the castle's zone and repair damage."),
				  FString::Printf(TEXT("Trained at the Citadel [Y]: %d gold + %d food. They do not count against housing."), Cost.Gold, Cost.Food),
				  TEXT("Click for the list: find one, or select them all.") });
		}
		if (BB.bClicked) { Click(); bBuilderList = !bBuilderList; }   // the list of builders, under the counter
		if (bBuilderList) { DrawBuilderList(Seg); }
		CX += U(142.f);
		Divider(CX - U(12.f));
	}

	// match clock
	Icon(ESRIcon::Clock, CX, Y + (H - U(24.f)) * 0.5f, U(24.f));
	TextIn(Row(CX + U(31.f)), Clock(Battle->GetBattleClock()), U(21.f), Parchment, AlignLeft, Bold);

	// top-right: controls, pause
	const float BS = U(46.f);
	const FBox2D PauseBox(FVector2D(View.X - U(14.f) - BS, Y + U(4.f)), FVector2D(View.X - U(14.f), Y + U(4.f) + BS));
	const FBox2D HelpBox(PauseBox.Min - FVector2D(BS + U(8.f), 0.f), PauseBox.Max - FVector2D(BS + U(8.f), 0.f));
	Block(PauseBox); Block(HelpBox);
	const FBtn Help = IconButton(HelpBox, SRId::Help, ESRIcon::Help, nullptr);
	const FBtn Pause = IconButton(PauseBox, SRId::Pause, ESRIcon::Pause, nullptr);
	if (Help.bHover) { SetTooltip(HelpBox, TEXT("Controls"), { TEXT("Every key and mouse command (F1).") }); }
	if (Pause.bHover) { SetTooltip(PauseBox, TEXT("Pause"), { TEXT("Pause menu: restart, settings, quit (Esc).") }); }
	if (Help.bClicked) { Click(); ToggleLegend(); }
	if (Pause.bClicked)
	{
		Click();
		if (USRGameFlowSubsystem* Flow = USRGameFlowSubsystem::Get(this)) { Flow->SetPaused(true); }
	}
}

void ASRHUD::DrawUpgradeButton(const FBox2D& R, ASRBuilding* Building)
{
	// One button for every building with levels (the castle, watchtowers, gold mines): next level, its price, progress.
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy || !Building) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const int32 L = Building->GetLevel();
	const bool bTop = L >= Building->GetMaxLevel();
	const bool bBusy = Building->IsUpgrading();
	const FSRCost Cost = Building->GetUpgradeCost();
	const bool bGold = Economy->GetResource(ESRTeam::Player, ESRResource::Gold) >= Cost.Gold;
	const bool bFood = Economy->GetResource(ESRTeam::Player, ESRResource::Food) >= Cost.Food;
	const bool bEnabled = Building->CanUpgrade() && bGold && bFood;
	FBtn B = Button(R, SRId::Upgrade);
	if (!bEnabled) { B.Hot *= 0.3f; }
	ButtonFrame(R, B, bEnabled || bBusy);
	Icon(Building->IsCastle() ? ESRIcon::Crown : BuildingIcon(Building->BuildingType), R.Min.X + U(9.f), R.Min.Y + U(12.f), U(44.f),
		bEnabled || bBusy ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
	const float TX = R.Min.X + U(62.f);
	// (a narrow button, the Citadel's three-wide row, gets the short form)
	const bool bNarrow = R.Max.X - R.Min.X < U(185.f);
	const FString Title = bTop ? FString::Printf(TEXT("Level %d (top)"), L) : (bNarrow ? FString::Printf(TEXT("To level %d"), L + 1) : FString::Printf(TEXT("Upgrade to level %d"), L + 1));
	Text(Title, TX, R.Min.Y + U(30.f), U(14.f), bEnabled || bBusy ? Parchment : Dim, AlignLeft, Bold);
	KeyCap(TEXT("U"), R.Max.X - U(6.f), R.Min.Y + U(6.f), bEnabled);
	// what the next level brings, in a few words (and in full in the tooltip)
	FString Gain;
	TArray<FString> Lines;
	switch (Building->BuildingType)
	{
	case ESRBuildingType::Castle:
	{
		const FSRCastleLevel& A = F.CastleLevel(L), &N = F.CastleLevel(L + 1);
		Gain = FString::Printf(TEXT("troops %d > %d"), A.PopulationCeiling, N.PopulationCeiling);
		Lines.Add(FString::Printf(TEXT("Troop ceiling %d > %d   ·   the Citadel houses %d > %d"), A.PopulationCeiling, N.PopulationCeiling, A.Housing, N.Housing));
		Lines.Add(FString::Printf(TEXT("Builders %d > %d   ·   building zone %.0f > %.0f m"), A.Builders, N.Builders, A.BuildZone / 100.f, N.BuildZone / 100.f));
		Lines.Add(FString::Printf(TEXT("Stores %d > %d gold and food   ·   walls %.0f > %.0f"), A.Storage.Gold, N.Storage.Gold, A.Health, N.Health));
		break;
	}
	case ESRBuildingType::Tower:
	{
		const FSRTowerLevel& A = F.TowerLevel(L), &N = F.TowerLevel(L + 1);
		Gain = FString::Printf(TEXT("damage %.0f > %.0f"), A.Damage, N.Damage);
		Lines.Add(FString::Printf(TEXT("Damage %.0f > %.0f   ·   a shot every %.2f > %.2f s"), A.Damage, N.Damage, A.Interval, N.Interval));
		Lines.Add(FString::Printf(TEXT("Reach %.0f > %.0f m   ·   health %.0f > %.0f"), A.Range / 100.f, N.Range / 100.f, A.Health, N.Health));
		break;
	}
	case ESRBuildingType::Barracks: case ESRBuildingType::Range: case ESRBuildingType::Stable: case ESRBuildingType::Workshop:
	{
		const FSRTrainerLevel& A = F.TrainerLevel(L), &N = F.TrainerLevel(L + 1);
		const ESRUnitType Troop = Building->Stats().RecruitType;
		const float T0 = F.BuildTimeFor(Troop) / FMath::Max(A.TrainSpeed, 0.1f), T1 = F.BuildTimeFor(Troop) / FMath::Max(N.TrainSpeed, 0.1f);
		Gain = FString::Printf(TEXT("trains in %.1f > %.1f s"), T0, T1);
		Lines.Add(FString::Printf(TEXT("A %s every %.1f > %.1f s (%d%% > %d%% speed)"), *F.StatsFor(Troop).DisplayName, T0, T1,
			FMath::RoundToInt(A.TrainSpeed * 100.f), FMath::RoundToInt(N.TrainSpeed * 100.f)));
		Lines.Add(FString::Printf(TEXT("Health %.0f > %.0f   ·   it keeps training while it is upgraded"), Building->Stats().MaxHealth * A.HealthScale, Building->Stats().MaxHealth * N.HealthScale));
		break;
	}
	case ESRBuildingType::Mine:
	{
		const FSRMineLevel& A = F.MineLevel(L), &N = F.MineLevel(L + 1);
		Gain = FString::Printf(TEXT("+%d > +%d gold"), A.GoldPerPayout, N.GoldPerPayout);
		Lines.Add(FString::Printf(TEXT("Each delivery %d > %d gold (every %.0f s)   ·   health %.0f > %.0f"), A.GoldPerPayout, N.GoldPerPayout, F.MinePayoutInterval, A.Health, N.Health));
		break;
	}
	case ESRBuildingType::Granary: case ESRBuildingType::Treasury:
	{
		const bool bGranary = Building->BuildingType == ESRBuildingType::Granary;
		const FSRStoreLevel& A = F.StoreLevel(bGranary, L), &N = F.StoreLevel(bGranary, L + 1);
		const TCHAR* What = bGranary ? TEXT("food") : TEXT("gold");
		const int32 Kingdom = Economy->GetStorage(ESRTeam::Player, bGranary ? ESRResource::Food : ESRResource::Gold);
		Gain = FString::Printf(TEXT("holds %d > %d %s"), A.Capacity, N.Capacity, What);
		Lines.Add(FString::Printf(TEXT("Holds %d > %d %s   ·   health %.0f > %.0f"), A.Capacity, N.Capacity, What, A.Health, N.Health));
		Lines.Add(FString::Printf(TEXT("Your kingdom's %s stores: %d > %d"), What, Kingdom, Kingdom + N.Capacity - A.Capacity));
		break;
	}
	default: break;
	}
	if (bBusy)
	{
		Meter(TX, R.Min.Y + U(58.f), R.Max.X - TX - U(12.f), U(8.f), Building->GetUpgradeFraction(), GoldBright);
		Text(FString::Printf(TEXT("Upgrading...  %d%%"), FMath::RoundToInt(Building->GetUpgradeFraction() * 100.f)), R.Min.X + U(10.f), R.Max.Y - U(26.f), U(13.f), Dim);
	}
	else if (!bTop)
	{
		Icon(ESRIcon::Coin, TX, R.Min.Y + U(53.f), U(17.f));
		Text(FString::FromInt(Cost.Gold), TX + U(21.f), R.Min.Y + U(52.f), U(16.f), bGold ? GoldBright : Refuse, AlignLeft, Bold);
		if (Cost.Food > 0)
		{
			const float FX = TX + U(25.f) + TextSize(FString::FromInt(Cost.Gold), U(16.f), Bold).X + U(8.f);
			Icon(ESRIcon::Food, FX, R.Min.Y + U(53.f), U(17.f));
			Text(FString::FromInt(Cost.Food), FX + U(21.f), R.Min.Y + U(52.f), U(16.f), bFood ? FoodColor : Refuse, AlignLeft, Bold);
		}
		Text(Gain, R.Min.X + U(10.f), R.Max.Y - U(26.f), U(13.f), Dim);
	}
	if (B.bHover)
	{
		if (bTop) { Lines.Reset(); Lines.Add(TEXT("At its highest level.")); }
		else
		{
			Lines.Add(Cost.Food > 0 ? FString::Printf(TEXT("Cost %d gold + %d food   ·   %.0f s (Builders at its walls speed it up)."), Cost.Gold, Cost.Food, Building->GetUpgradeTime())
				: FString::Printf(TEXT("Cost %d gold   ·   %.0f s (Builders at its walls speed it up)."), Cost.Gold, Building->GetUpgradeTime()));
		}
		SetTooltip(R, FString::Printf(TEXT("Upgrade the %s   [U]"), *Building->GetDisplayName()), Lines);
	}
	if (B.bClicked) { PC->UpgradeBuildingCommand(Building); if (bEnabled) { Click(); } }
}

void ASRHUD::DrawBuilderList(const FBox2D& Anchor)
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || !PC) { bBuilderList = false; return; }
	TArray<ASRUnit*> Builders;
	for (ASRUnit* U2 : Battle->GetUnits()) { if (U2 && U2->IsActive() && U2->GetTeam() == ESRTeam::Player && U2->IsBuilder()) { Builders.Add(U2); } }
	const float W = U(330.f), RowH = U(40.f), Pad = U(8.f);
	const int32 Rows = Builders.Num() + 1;   // "select all" first
	const FBox2D Panel(FVector2D(Anchor.Min.X, Anchor.Max.Y + U(4.f)), FVector2D(Anchor.Min.X + W, Anchor.Max.Y + U(4.f) + Pad * 2.f + Rows * RowH));
	Block(Panel);
	HudPanel(Panel);
	auto Status = [](const ASRUnit* B) -> FString
	{
		if (const ASRBuilding* T = B->GetBuildTarget())
		{
			const FString Name = T->GetDisplayName();
			const bool bAtWork = B->IsWorkingOn(T);
			if (T->IsUnderConstruction()) { return bAtWork ? FString::Printf(TEXT("Building the %s"), *Name) : FString::Printf(TEXT("Going to build the %s"), *Name); }
			return bAtWork ? FString::Printf(TEXT("Repairing the %s"), *Name) : FString::Printf(TEXT("Going to repair the %s"), *Name);
		}
		if (B->IsEngaged()) { return TEXT("Fighting!"); }
		return B->GetVelocity2D().SizeSquared() > 400.f ? FString(TEXT("Walking")) : FString(TEXT("Idle"));
	};
	float RY = Panel.Min.Y + Pad;
	for (int32 i = 0; i < Rows; ++i, RY += RowH)
	{
		const FBox2D Row(FVector2D(Panel.Min.X + Pad, RY), FVector2D(Panel.Max.X - Pad, RY + RowH - U(3.f)));
		const FBtn RB = Button(Row, SRId::BuilderRow + i);
		Fill(Row.Min.X, Row.Min.Y, Row.Max.X - Row.Min.X, Row.Max.Y - Row.Min.Y, FMath::Lerp(Inset, ButtonHot, RB.Hot * 0.8f));
		if (i == 0)
		{
			TextIn(FBox2D(Row.Min + FVector2D(U(10.f), 0.f), Row.Max), Builders.Num() > 0 ? FString::Printf(TEXT("Select all %d Builders"), Builders.Num())
				: FString(TEXT("No Builders yet: train them at the Citadel [Y]")), U(14.f), Builders.Num() > 0 ? GoldBright : Dim, AlignLeft, Bold);
			if (RB.bClicked && Builders.Num() > 0) { Click(); PC->SelectBuilding(nullptr); PC->SelectUnits(Builders, false); bBuilderList = false; }
			continue;
		}
		ASRUnit* B = Builders[i - 1];
		Icon(ESRIcon::PortraitBuilder, Row.Min.X + U(6.f), Row.Min.Y + (RowH - U(34.f)) * 0.5f, U(30.f));
		const FString St = Status(B);
		Text(FString::Printf(TEXT("Builder %d"), i), Row.Min.X + U(44.f), Row.Min.Y + U(3.f), U(14.f), B->IsSelected() ? GoldBright : Parchment, AlignLeft, Bold);
		Text(St, Row.Min.X + U(44.f), Row.Min.Y + U(19.f), U(12.f), St == TEXT("Idle") ? Amber : (St == TEXT("Fighting!") ? Refuse : Dim));
		Meter(Row.Max.X - U(70.f), Row.Min.Y + U(15.f), U(60.f), U(6.f), B->GetHealthFrac(), Health(B->GetHealthFrac()));
		if (RB.bClicked)
		{
			// select it and fly the camera there
			Click();
			PC->SelectBuilding(nullptr);
			PC->SelectUnits({ B }, false);
			if (ASRCameraPawn* Cam = Cast<ASRCameraPawn>(PC->GetPawn())) { Cam->FocusOn(B->GetPos2D(), false); }
			B->FlashTargeted();
		}
	}
	// a click anywhere else closes it
	if (bMouse && !Panel.IsInside(Mouse) && !Anchor.IsInside(Mouse) && PC->WasInputKeyJustPressed(EKeys::LeftMouseButton)) { bBuilderList = false; }
}

// ---------------------------------------------------------------------------- hints and alerts

float ASRHUD::DrawHints(float Y)
{
	if (PC->IsPlacing())
	{
		const FString Name = USRFeelSettings::Get().BuildingStatsFor(PC->GetPlacingType()).DisplayName;
		const FBox2D Box = Pill(FString::Printf(TEXT("Placing %s    LMB place   ·   Shift+LMB place more   ·   RMB / Esc cancel"), *Name),
			View.X * 0.5f, Y, U(16.f), BuildingIcon(PC->GetPlacingType()), Gold);
		Y = Box.Max.Y + U(6.f);
	}
	if (PC->IsAttackMoveArmed())
	{
		const FBox2D Box = Pill(TEXT("Attack-move    LMB a destination or an enemy   ·   RMB / Esc cancel"), View.X * 0.5f, Y, U(16.f), ESRIcon::Swords, Refuse);
		Y = Box.Max.Y + U(6.f);
	}
	return Y;
}

void ASRHUD::DrawAlerts(float Y)
{
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy) { return; }
	const TArray<FSRAlert>& Alerts = Economy->GetAlerts();
	for (int32 i = Alerts.Num() - 1; i >= 0; --i)                       // newest on top
	{
		const FSRAlert& Alert = Alerts[i];
		// in over 150 ms, out over the last second of its six
		const float Alpha = FMath::Clamp(Alert.Age / 0.15f, 0.f, 1.f) * FMath::Clamp(6.f - Alert.Age, 0.f, 1.f);
		if (Alpha <= 0.f) { continue; }
		ESRIcon Which = ESRIcon::AlertInfo;
		FLinearColor Accent = Gold;
		bool bBig = false;
		switch (Alert.Kind)
		{
		case ESRAlertKind::UnderAttack: Which = ESRIcon::AlertAttack; Accent = Refuse; break;
		case ESRAlertKind::BuildingLost: Which = ESRIcon::AlertLost; Accent = Refuse; break;
		case ESRAlertKind::BuildingDone: Which = ESRIcon::AlertDone; Accent = Good; break;
		case ESRAlertKind::EnemyWave: Which = ESRIcon::AlertWave; Accent = Refuse; bBig = true; break;
		case ESRAlertKind::PopulationCapped: Which = ESRIcon::AlertPop; Accent = Amber; break;
		default: break;
		}
		if (bBig) { Accent = FMath::Lerp(Accent, GoldBright, 0.5f + 0.5f * FMath::Sin(float(Now) * 6.f)); }   // the war horn: it pulses
		const float Slide = (1.f - FMath::Clamp(Alert.Age / 0.15f, 0.f, 1.f)) * U(8.f);
		const FBox2D Box = Pill(Alert.Text.ToString(), View.X * 0.5f, Y - Slide, U(bBig ? 23.f : 17.f), Which, Accent, Alpha);
		Y = Box.Max.Y + Slide + U(6.f);
	}
}

void ASRHUD::DrawPlacementCursor()
{
	if (!PC->IsPlacing() && bMouse && PC->SelectionHasBuilders())
	{
		for (const FBox2D& Box : Blockers) { if (Box.IsInside(Mouse)) { return; } }
		const ASRBuilding* HoverB = PC->PickBuildingUnderCursor();
		if (HoverB && HoverB->Team == ESRTeam::Player && HoverB->NeedsWork())
		{
			Pill(HoverB->IsUnderConstruction() ? TEXT("RMB: build it") : TEXT("RMB: repair it"), Mouse.X + U(22.f), Mouse.Y + U(24.f), U(16.f), ESRIcon::Hammer, GoldBright, 1.f, false);
		}
		return;
	}
	if (!PC->IsPlacing() || !bMouse) { return; }
	for (const FBox2D& Box : Blockers) { if (Box.IsInside(Mouse)) { return; } }
	if (PC->GetPlacementReason().IsEmpty())
	{
		// a good spot outside the castle's zone: say who will build it
		if (PC->IsPlacementValid() && PC->PlacementNeedsBuilder())
		{
			Pill(TEXT("Outside the castle's zone: a Builder will walk here and build it"), Mouse.X + U(22.f), Mouse.Y + U(24.f), U(16.f), ESRIcon::Hammer, GoldBright, 1.f, false);
		}
		return;
	}
	// why the spot is refused, right where the player is looking
	Pill(PC->GetPlacementReason().ToString(), Mouse.X + U(22.f), Mouse.Y + U(24.f), U(16.f), ESRIcon::Cancel, Refuse, 1.f, false);
}

// ---------------------------------------------------------------------------- minimap

void ASRHUD::DrawMinimap(const FBox2D& Box)
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	const USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (!Battle || !Economy) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	HudPanel(Box);
	const float In = U(7.f);
	MapRect = FBox2D(Box.Min + FVector2D(In, In), Box.Max - FVector2D(In, In));
	const FVector2D Size = MapRect.GetSize();
	const FVector2D E = F.MapHalfExtent;
	// the camera looks along +X: +X is up the map, +Y is right
	auto ToMap = [&](const FVector2D& World) { return FVector2D(MapRect.Min.X + (World.Y + E.Y) / (2.f * E.Y) * Size.X, MapRect.Min.Y + (E.X - World.X) / (2.f * E.X) * Size.Y); };
	auto ToWorld = [&](const FVector2D& Map) { return FVector2D(E.X - (Map.Y - MapRect.Min.Y) / Size.Y * 2.f * E.X, (Map.X - MapRect.Min.X) / Size.X * 2.f * E.Y - E.Y); };
	auto Dot = [&](const FVector2D& World, float S, const FLinearColor& Color, bool bRim)
	{
		const FVector2D P = ToMap(World);
		if (!MapRect.IsInside(P)) { return; }
		const float X = FMath::RoundToFloat(P.X - S * 0.5f), Y = FMath::RoundToFloat(P.Y - S * 0.5f);
		if (bRim) { Fill(X - 1.f, Y - 1.f, S + 2.f, S + 2.f, FLinearColor(0.f, 0.f, 0.f, 0.85f * Color.A)); }
		Fill(X, Y, S, S, Color);
	};

	if (MinimapBase) { DrawTexture(MinimapBase, MapRect.Min.X, MapRect.Min.Y, Size.X, Size.Y, 0.f, 0.f, 1.f, 1.f, FLinearColor(0.9f, 0.9f, 0.9f, 1.f), BLEND_Opaque); }
	else { Fill(MapRect.Min.X, MapRect.Min.Y, Size.X, Size.Y, FLinearColor(0.10f, 0.14f, 0.07f, 1.f)); }
	// fog of war: unexplored land dark, explored but out of sight dimmed
	if (const USRFogSubsystem* Fog = USRFogSubsystem::Get(this); Fog && Fog->IsEnabled())
	{
		const int32 G = 56;
		const float CW = Size.X / G, CH = Size.Y / G;
		for (int32 r = 0; r < G; ++r)
		{
			for (int32 c = 0; c < G; ++c)
			{
				const FVector2D W = ToWorld(FVector2D(MapRect.Min.X + (c + 0.5f) * CW, MapRect.Min.Y + (r + 0.5f) * CH));
				const float Dark = Fog->IsVisible(W) ? 0.f : (Fog->IsExplored(W) ? 0.42f : 0.82f);
				if (Dark > 0.f) { Fill(FMath::FloorToFloat(MapRect.Min.X + c * CW), FMath::FloorToFloat(MapRect.Min.Y + r * CH), FMath::CeilToFloat(CW) + 1.f, FMath::CeilToFloat(CH) + 1.f, FLinearColor(0.01f, 0.012f, 0.02f, Dark)); }
			}
		}
	}

	if (Grid)
	{
		for (const FSRVein& Vein : Grid->GetVeins())
		{
			if (!Vein.Mine.IsValid()) { Dot(Vein.Pos, FMath::Max(3.f, U(5.f)), GoldBright, true); }
		}
	}
	for (const ASRBuilding* Building : Economy->GetBuildings())
	{
		if (!Building || !Building->IsAlive() || Building->IsHidden()) { continue; }   // hidden: not yet seen (fog of war)
		FLinearColor Color = Building->Team == ESRTeam::Player ? TeamBlue : TeamRed;
		if (Building->IsUnderConstruction()) { Color = FMath::Lerp(Color, FLinearColor(0.1f, 0.1f, 0.1f, 1.f), 0.45f); }
		Dot(Building->GetFootprintCentre(), FMath::Max(4.f, U(Building->IsCastle() ? 13.f : 8.f)), Color, true);
		if (Building->IsCastle()) { Dot(Building->GetFootprintCentre(), FMath::Max(2.f, U(5.f)), GoldBright, false); }
	}
	const float UnitSize = FMath::Max(2.f, U(3.5f));
	for (const ASRUnit* Unit : Battle->GetUnits())
	{
		if (!Unit || !Unit->IsActive() || !Battle->IsVisibleToPlayer(Unit)) { continue; }
		const bool bEnemy = Unit->GetTeam() == ESRTeam::Enemy;
		Dot(Unit->GetPos2D(), UnitSize, Unit->IsSelected() && !bEnemy ? FLinearColor::White : (bEnemy ? FLinearColor(1.f, 0.42f, 0.30f, 1.f) : FLinearColor(0.55f, 0.80f, 1.f, 1.f)), false);
	}

	// alerts with a place ping there: a ring that swells and fades, again and again while the alert lasts
	for (const FSRAlert& Alert : Economy->GetAlerts())
	{
		if (!Alert.bHasLocation) { continue; }
		const bool bBad = Alert.Kind == ESRAlertKind::UnderAttack || Alert.Kind == ESRAlertKind::BuildingLost || Alert.Kind == ESRAlertKind::EnemyWave;
		const FLinearColor Color = bBad ? Refuse : (Alert.Kind == ESRAlertKind::BuildingDone ? Good : GoldBright);
		const float T = FMath::Fmod(float(Now) * 1.1f, 1.f);
		const FVector2D P = ToMap(Alert.Location);
		const float R = U(5.f) + U(20.f) * T;
		FBox2D Ring(P - FVector2D(R, R), P + FVector2D(R, R));
		Ring.Min = FVector2D(FMath::Max(Ring.Min.X, MapRect.Min.X), FMath::Max(Ring.Min.Y, MapRect.Min.Y));
		Ring.Max = FVector2D(FMath::Min(Ring.Max.X, MapRect.Max.X), FMath::Min(Ring.Max.Y, MapRect.Max.Y));
		if (Ring.Max.X > Ring.Min.X && Ring.Max.Y > Ring.Min.Y) { Outline(Ring, A(Color, (1.f - T) * FMath::Clamp(6.f - Alert.Age, 0.f, 1.f)), FMath::Max(1.f, U(2.f))); }
		Dot(Alert.Location, FMath::Max(3.f, U(5.f)), Color, true);
	}

	// the camera's view of the ground: the four screen corners cast down onto the focus plane
	const ASRCameraPawn* CameraPawn = Cast<ASRCameraPawn>(PC->GetPawn());
	int32 VX = 0, VY = 0;
	PC->GetViewportSize(VX, VY);
	if (CameraPawn && VX > 0)
	{
		const float PlaneZ = CameraPawn->GetFocusPoint().Z;
		const FVector2D Corners[4] = { FVector2D(0.f, 0.f), FVector2D(VX, 0.f), FVector2D(VX, VY), FVector2D(0.f, VY) };
		FVector2D Points[4];
		bool bOk = true;
		for (int32 i = 0; i < 4 && bOk; ++i)
		{
			FVector Origin, Dir;
			bOk = PC->DeprojectScreenPositionToWorld(Corners[i].X, Corners[i].Y, Origin, Dir);
			const float Along = Dir.Z < -0.02f ? FMath::Min(float((PlaneZ - Origin.Z) / Dir.Z), 80000.f) : 80000.f;
			Points[i] = ToMap(FVector2D(Origin + Dir * Along));
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

	// LMB (and drag): look there. RMB: send the selection there (or move the castle's rally point).
	const FBtn B = Button(MapRect, SRId::Minimap);
	const USRBattleSubsystem* Ground = Battle;
	auto GroundAt = [&](const FVector2D& MapPoint)
	{
		const FVector2D World = ToWorld(FVector2D(FMath::Clamp(MapPoint.X, MapRect.Min.X, MapRect.Max.X), FMath::Clamp(MapPoint.Y, MapRect.Min.Y, MapRect.Max.Y)));
		float Z = 0.f;
		Ground->SampleGround(World, 20000.f, Z);
		return FVector(World.X, World.Y, Z);
	};
	if (B.bHeld && bMouse)
	{
		if (ASRCameraPawn* Mutable = Cast<ASRCameraPawn>(PC->GetPawn())) { Mutable->FocusOn(FVector2D(GroundAt(Mouse)), false); }
	}
	if (B.bRightClicked)
	{
		const ASRBuilding* Selected = PC->GetSelectedBuilding();
		if (Selected && Selected->IsRecruiter() && Selected->Team == ESRTeam::Player) { PC->SetRallyFor(GroundAt(Press.Pos)); }
		else { PC->IssueMove(GroundAt(Press.Pos), false); }
	}
}

// ---------------------------------------------------------------------------- build menu

void ASRHUD::DrawBuildMenu(float X, float Bottom)
{
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const bool bOpen = PC->IsBuildMenuOpen();

	// ---- the Build button: as tall as the minimap
	const float BW = U(76.f), BH = U(266.f);
	const FBox2D Toggle(FVector2D(X, Bottom - BH), FVector2D(X + BW, Bottom));
	Block(Toggle);
	const FBtn T = Button(Toggle, SRId::Build);
	Fill(Toggle.Min.X + U(2.f), Toggle.Min.Y + U(4.f), BW, BH, FLinearColor(0.f, 0.f, 0.f, 0.35f));
	ButtonFrame(Toggle, T, true, bOpen || PC->IsPlacing());
	const float Lift = T.bHeld ? U(1.f) : 0.f;
	Icon(ESRIcon::Hammer, Toggle.Min.X + (BW - U(46.f)) * 0.5f, Toggle.Min.Y + BH * 0.5f - U(40.f) + Lift, U(46.f));
	Text(TEXT("Build"), Toggle.Min.X + BW * 0.5f, Toggle.Min.Y + BH * 0.5f + U(14.f) + Lift, U(17.f), Parchment, AlignCentre, Bold);
	KeyCap(TEXT("B"), Toggle.Max.X - U(4.f), Toggle.Min.Y + U(4.f), true);
	if (T.bClicked) { Click(); PC->ToggleBuildMenu(); }
	if (T.bHover) { SetTooltip(Toggle, TEXT("Build   [B]"), { TEXT("Farms, mines, barracks, ranges and towers."), TEXT("Buildings are paid for in gold.") }); }
	if (!bOpen) { return; }

	// ---- the menu: tabs along the top, the tab's buildings below
	static const ESRBuildCategory Tabs[3] = { ESRBuildCategory::Economy, ESRBuildCategory::Military, ESRBuildCategory::Defence };
	static const TCHAR* TabNames[3] = { TEXT("Economy"), TEXT("Military"), TEXT("Defence") };
	static const ESRIcon TabIcons[3] = { ESRIcon::Coin, ESRIcon::Swords, ESRIcon::Tower };
	const float Pad = U(12.f), TabH = U(42.f), CardW = U(118.f), CardH = U(132.f), Gap = U(8.f);
	const float PW = Pad * 2.f + 4.f * CardW + 3.f * Gap, PH = Pad * 2.f + TabH + Gap + CardH + U(24.f);   // room for four cards a tab
	const float PX = Toggle.Max.X + U(10.f), PY = Bottom - U(152.f) - U(10.f) - PH;
	const FBox2D Box(FVector2D(PX, PY), FVector2D(PX + PW, PY + PH));
	HudPanel(Box);

	const float TW = (PW - 2.f * Pad - 2.f * Gap) / 3.f;
	for (int32 t = 0; t < 3; ++t)
	{
		const FBox2D TabBox(FVector2D(PX + Pad + t * (TW + Gap), PY + Pad), FVector2D(PX + Pad + t * (TW + Gap) + TW, PY + Pad + TabH));
		const bool bSel = PC->GetBuildMenuTab() == Tabs[t];
		const FBtn B = Button(TabBox, SRId::Build + 1 + t);
		ButtonFrame(TabBox, B, true, bSel);
		Icon(TabIcons[t], TabBox.Min.X + U(10.f), TabBox.Min.Y + (TabH - U(22.f)) * 0.5f, U(22.f), FLinearColor(1.f, 1.f, 1.f, bSel ? 1.f : 0.7f));
		TextIn(FBox2D(TabBox.Min + FVector2D(U(38.f), 0.f), TabBox.Max), TabNames[t], U(16.f), bSel ? GoldBright : Parchment, AlignLeft, Bold);
		if (B.bClicked && !bSel) { Click(); PC->SetBuildMenuTab(Tabs[t]); }
		if (B.bHover && !bSel) { SetTooltip(TabBox, TabNames[t], { TEXT("Tab cycles the tabs.") }); }
	}

	TArray<ESRBuildingType> Entries;
	ASRPlayerController::GetBuildMenuEntries(PC->GetBuildMenuTab(), Entries);
	const float CY = PY + Pad + TabH + Gap;
	for (int32 i = 0; i < Entries.Num() && i < 6; ++i)
	{
		const ESRBuildingType Type = Entries[i];
		const FSRBuildingStats& Stats = F.BuildingStatsFor(Type);
		// towers and storehouses are limited by the Citadel's level
		const bool bStore = Type == ESRBuildingType::Granary || Type == ESRBuildingType::Treasury;
		const int32 LimitHave = bStore ? Economy->CountStanding(Type, ESRTeam::Player) : Economy->CountBuildings(Type, ESRTeam::Player);
		const int32 LimitMax = bStore ? Economy->GetMaxStores(ESRTeam::Player) : Economy->GetMaxTowers(ESRTeam::Player);
		const bool bTowerCapped = (Type == ESRBuildingType::Tower || bStore) && LimitHave >= LimitMax;
		const bool bAfford = Economy->CanAfford(ESRTeam::Player, Stats.Cost) && !bTowerCapped;
		const FBox2D Card(FVector2D(PX + Pad + i * (CardW + Gap), CY), FVector2D(PX + Pad + i * (CardW + Gap) + CardW, CY + CardH));
		// always clickable: one you cannot afford flashes the gold counter (BeginPlacement says why)
		FBtn B = Button(Card, SRId::Build + 4 + i);
		if (!bAfford) { B.Hot *= 0.3f; }
		ButtonFrame(Card, B, bAfford);
		const float L = B.bHeld ? U(1.f) : 0.f;
		Icon(BuildingIcon(Type), Card.Min.X + (CardW - U(48.f)) * 0.5f, Card.Min.Y + U(12.f) + L, U(48.f), bAfford ? FLinearColor::White : FLinearColor(0.42f, 0.42f, 0.46f, 0.85f));
		const FString Key = FString::FromInt(i + 1);
		KeyCap(Key, Card.Max.X - U(4.f), Card.Min.Y + U(4.f), bAfford);
		Text(Stats.DisplayName, Card.Min.X + CardW * 0.5f, Card.Min.Y + U(68.f) + L, U(15.f), bAfford ? Parchment : Dim, AlignCentre, Bold);
		const FString Cost = FString::FromInt(Stats.Cost.Gold);
		const float CW = U(16.f) + U(4.f) + TextSize(Cost, U(16.f), Bold).X;
		const float CX = Card.Min.X + (CardW - CW) * 0.5f, CostY = Card.Max.Y - U(30.f) + L;
		Icon(ESRIcon::Coin, CX, CostY + U(2.f), U(16.f), bAfford ? FLinearColor::White : FLinearColor(0.6f, 0.6f, 0.6f, 0.9f));
		Text(Cost, CX + U(20.f), CostY, U(16.f), bAfford ? GoldBright : Refuse, AlignLeft, Bold);
		if (Type == ESRBuildingType::Tower || bStore)
		{
			// how many of the castle's allowance are used
			Text(FString::Printf(TEXT("%d/%d"), LimitHave, LimitMax), Card.Min.X + U(6.f), Card.Min.Y + U(4.f), U(13.f),
				bTowerCapped ? Refuse : Dim, AlignLeft, Bold);
		}
		if (B.bClicked) { PC->BeginPlacement(Type); }
		if (B.bHover)
		{
			TArray<FString> Lines;
			if (!Stats.Blurb.IsEmpty()) { Lines.Add(Stats.Blurb); }
			if (Type == ESRBuildingType::Farm) { Lines.Add(FString::Printf(TEXT("+%d food every %.0f s."), F.FarmFoodPerPayout, F.FarmPayoutInterval)); }
			else if (Type == ESRBuildingType::Mine) { Lines.Add(FString::Printf(TEXT("+%d gold every %.0f s."), F.MineGoldPerPayout, F.MinePayoutInterval)); }
			else if (bStore)
			{
				const bool bGranary = Type == ESRBuildingType::Granary;
				const int32 TopLevel = FMath::Max(1, bGranary ? F.GranaryLevels.Num() : F.TreasuryLevels.Num());
				Lines.Add(FString::Printf(TEXT("+%d %s storage; upgrade it (%d levels) to hold up to %d."), F.StoreLevel(bGranary, 1).Capacity, bGranary ? TEXT("food") : TEXT("gold"),
					TopLevel, F.StoreLevel(bGranary, TopLevel).Capacity));
				Lines.Add(TEXT("If it is destroyed, what no longer fits in your stores is lost."));
				Lines.Add(FString::Printf(TEXT("%s: %d of %d (one more for every %d Citadel levels)."), bGranary ? TEXT("Granaries") : TEXT("Treasuries"), LimitHave, LimitMax, F.StoreLimitCastleLevels));
			}
			else if (Stats.bRecruits)
			{
				const FSRUnitStats& U2 = F.StatsFor(Stats.RecruitType);
				Lines.Add(FString::Printf(TEXT("%s: %d food, %.0f s each."), *U2.DisplayName, F.CostFor(Stats.RecruitType).Food, F.BuildTimeFor(Stats.RecruitType)));
			}
			else if (Stats.AttackDamage > 0.f) { Lines.Add(FString::Printf(TEXT("%.0f damage every %.1f s, reach %.0f m."), Stats.AttackDamage, Stats.AttackInterval, Stats.AttackRange / 100.f)); }
			if (Stats.PopProvided > 0) { Lines.Add(FString::Printf(TEXT("Houses %d more troops."), Stats.PopProvided)); }
			Lines.Add(FString::Printf(TEXT("Cost %d gold   ·   builds in %.0f s   ·   %.0f health"), Stats.Cost.Gold, Stats.BuildTime, Stats.MaxHealth));
			Lines.Add(Type == ESRBuildingType::Mine ? TEXT("Rule: mines must stand on a gold vein (gold marks on the map).") : TEXT("Rule: flat, free ground near your own buildings."));
			if (Type == ESRBuildingType::Tower)
			{
				Lines.Add(FString::Printf(TEXT("Watchtowers: %d of %d (each Citadel level allows %d more)."), Economy->CountBuildings(Type, ESRTeam::Player),
					Economy->GetMaxTowers(ESRTeam::Player), F.TowerLimitPerCastleLevel));
			}
			if (bTowerCapped) { Lines.Add(TEXT("Limit reached: raise the Citadel for another.")); }
			else if (!bAfford) { Lines.Add(TEXT("Not enough gold.")); }
			SetTooltip(Card, FString::Printf(TEXT("%s   [%s]"), *Stats.DisplayName, *Key), Lines);
		}
	}
	Text(TEXT("1-6 pick  ·  Tab next tab  ·  Esc close"), PX + PW * 0.5f, Box.Max.Y - U(26.f), U(13.f), Dim, AlignCentre);
}

// ---------------------------------------------------------------------------- selection panel

void ASRHUD::DrawSelectionPanel(const FBox2D& Box)
{
	ASRBuilding* Building = PC->GetSelectedBuilding();
	bool bUnits = false;
	for (const TWeakObjectPtr<ASRUnit>& Unit : PC->GetSelection()) { bUnits |= Unit.IsValid() && Unit->IsAlive(); }
	if (!Building && !bUnits) { return; }
	HudPanel(Box);
	if (Building) { DrawBuildingSelection(Box, Building); }
	else { DrawTroopSelection(Box); }
}

void ASRHUD::DrawTroopSelection(const FBox2D& Box)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this);
	int32 Count[SRNumUnitTypes] = { 0 }, Total = 0, Engaged = 0;
	float HealthSum = 0.f;
	bool bEnemy = false;
	const ASRUnit* First = nullptr;
	for (const TWeakObjectPtr<ASRUnit>& Unit : PC->GetSelection())
	{
		if (!Unit.IsValid() || !Unit->IsAlive()) { continue; }
		if (!First) { First = Unit.Get(); }
		bEnemy |= Unit->GetTeam() == ESRTeam::Enemy;
		++Count[FMath::Clamp(int32(Unit->GetUnitType()), 0, SRNumUnitTypes - 1)];
		++Total;
		Engaged += Unit->IsEngaged() ? 1 : 0;
		HealthSum += Unit->GetHealthFrac();
	}
	if (!First) { return; }
	const int32 Platoon = bEnemy ? INDEX_NONE : PC->GetSelectedPlatoon();
	const FSRPlatoonInfo Info = Platoon != INDEX_NONE && Platoons ? Platoons->GetInfo(Platoon) : FSRPlatoonInfo();
	const ESRStance Stance = Info.bExists ? Info.Stance : First->GetStance();

	const float X = Box.Min.X + U(18.f), Y = Box.Min.Y + U(12.f);
	FString Title = Total == 1 ? F.StatsFor(First->GetUnitType()).DisplayName : FString::Printf(TEXT("%d Troops"), Total);
	if (bEnemy) { Title = TEXT("Enemy ") + Title; }
	if (Info.bExists) { Title = Info.Name; }
	Text(Title, X, Y, U(22.f), bEnemy ? FLinearColor(1.f, 0.55f, 0.45f, 1.f) : GoldBright, AlignLeft, Bold);
	FString Sub = bEnemy ? TEXT("Enemy troops: right-click to attack")
		: (Info.bExists ? FString::Printf(TEXT("Platoon %d  ·  %s  ·  %s  ·  %s"), Platoon + 1, *USRPlatoonSubsystem::KindName(Info.Kind).ToString(),
			*USRPlatoonSubsystem::FormationName(Info.Formation).ToString(), *USRPlatoonSubsystem::StanceName(Info.Stance).ToString())
			: (Count[4] > 0 ? FString(TEXT("B: build anywhere   ·   X: repair"))
			: (Count[5] == Total ? FString(TEXT("Sees far, hard to notice: foes spot it only from close by. No fighter."))
			: FString::Printf(TEXT("Stance: %s   ·   Ctrl+1-6 forms a platoon"), *USRPlatoonSubsystem::StanceName(Stance).ToString()))));
	// the command row takes the right of the panel: a hint that would run under it is dropped (its first part stays)
	if (TextSize(Sub, U(14.f)).X > U(268.f))
	{
		const int32 Cut = Sub.Find(TEXT("   ·   "));
		if (Cut > 0) { Sub.LeftInline(Cut); }
	}
	Text(Sub, X, Y + U(29.f), U(14.f), Dim);

	// who is in the selection: a portrait and a count per troop type
	float PX = X;
	for (int32 t = 0; t < SRNumUnitTypes; ++t)
	{
		if (Count[t] == 0) { continue; }
		Icon(SRUnitIcon(ESRUnitType(t)), PX, Y + U(52.f), U(46.f), FLinearColor::White, bEnemy);
		PX += U(52.f);
		PX += Text(FString::Printf(TEXT("×%d"), Count[t]), PX, Y + U(61.f), U(23.f), Parchment, AlignLeft, Bold) + U(22.f);
	}
	const float Avg = HealthSum / Total;
	const float HY = Box.Max.Y - U(27.f);
	Text(TEXT("Health"), X, HY - U(5.f), U(14.f), Dim);
	Meter(X + U(54.f), HY, U(150.f), U(9.f), Avg, Health(Avg));
	const float HW = Text(FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Avg * 100.f)), X + U(212.f), HY - U(6.f), U(15.f), Parchment, AlignLeft, Bold);
	if (Engaged > 0)
	{
		Icon(ESRIcon::Swords, X + U(224.f) + HW, HY - U(5.f), U(18.f));
		Text(FString::Printf(TEXT("%d fighting"), Engaged), X + U(246.f) + HW, HY - U(5.f), U(14.f), Amber);
	}
	if (bEnemy) { return; }

	// key for the ground circles: dashed = line of sight, solid = bow range
	if (F.bShowRangeCircles)
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
		if (Count[1] > 0 || Count[3] > 0) { Key(TEXT("range"), F.RangeCircleColor, false); }
		Key(TEXT("sight"), F.SightCircleColor, true);
	}

	// command buttons, right-aligned
	enum ECmd { CmdAttack, CmdStop, CmdHold, CmdPatrol, CmdStance, CmdForm, CmdMarch, CmdDisband, CmdRepair, CmdDismiss, CmdGuard };
	struct FCommand { ECmd Kind; ESRIcon Which; const TCHAR* Key; const TCHAR* Label; const TCHAR* Title; const TCHAR* Line; bool bActive; };
	const ESRFormationShape Shape = PC->GetSelectionFormationShape();
	const bool bFormOn = PC->GetSelectionFormationOn();
	TArray<FCommand, TInlineAllocator<12>> Commands;
	Commands.Add({ CmdAttack, ESRIcon::Swords, TEXT("A"), TEXT("Attack"), TEXT("Attack-move   [A]"), TEXT("Then click: march there, fighting what you meet."), PC->IsAttackMoveArmed() });
	Commands.Add({ CmdStop, ESRIcon::Stop, TEXT("S"), TEXT("Stop"), TEXT("Stop   [S]"), TEXT("Halt and drop the current order."), false });
	Commands.Add({ CmdHold, ESRIcon::StanceHold, TEXT("H"), TEXT("Hold"), TEXT("Hold ground   [H]"), TEXT("Stand fast: fight only what is in reach."), false });
	Commands.Add({ CmdPatrol, ESRIcon::Patrol, TEXT("P"), TEXT("Patrol"), TEXT("Patrol   [P]"), TEXT("Then click: walk between here and there, fighting what you meet, until given another order."), PC->IsPatrolArmed() });
	if (Total - Count[int32(ESRUnitType::Builder)] > 0)
	{
		Commands.Add({ CmdGuard, ESRIcon::Shield, TEXT("V"), TEXT("Guard"), TEXT("Guard   [V]"),
			TEXT("Then click one of your Builders or buildings: stay by it and fight what comes near. Or right-click it. Troops cannot be guarded."), PC->IsGuardArmed() });
	}
	Commands.Add({ CmdStance, StanceIcon(Stance), TEXT("G"), TEXT("Stance"), TEXT("Stance   [G]"), TEXT("Aggressive > Defensive > Hold Ground."), false });
	Commands.Add({ CmdForm, bFormOn ? FormationIcon(Shape) : ESRIcon::Pop, TEXT("F"), bFormOn ? TEXT("Form") : TEXT("Loose"), TEXT("Formation   [F]"),
		TEXT("Click (or F): formation on / off (off: they move as a loose group). Right-click: next shape, Line > Column > Wedge > Square."), bFormOn });
	const bool bTogether = PC->GetSelectionMarchTogether();
	if (Total > 1) { Commands.Add({ CmdMarch, ESRIcon::Pop, TEXT("M"), bTogether ? TEXT("Together") : TEXT("Free"), TEXT("March together   [M]"),
		bTogether ? TEXT("On: on the march everyone keeps the slowest troop's pace, so they arrive together. Click for each at its own speed.")
			: TEXT("Off: each marches at its own speed. Click to keep them together at the slowest troop's pace."), bTogether }); }
	if (Count[4] > 0) { Commands.Add({ CmdRepair, ESRIcon::Hammer, TEXT("X"), TEXT("Repair"), TEXT("Repair   [X]"), TEXT("The selected Builders go to the nearest damaged building (or unfinished site) and mend it. Or right-click one."), false }); }
	if (Info.bExists) { Commands.Add({ CmdDisband, ESRIcon::Disband, TEXT("Del"), TEXT("Disband"), TEXT("Disband platoon   [Delete]"), TEXT("Break up the platoon. The troops stay selected."), false }); }
	{
		const bool bArmed = PC->IsDismissArmed();
		Commands.Add({ CmdDismiss, ESRIcon::Cancel, TEXT("K"), bArmed ? TEXT("Sure?") : TEXT("Dismiss"), TEXT("Dismiss   [K]"),
			bArmed ? TEXT("Click (or K) again to dismiss the selected troops. They are gone for good: no refund.")
				: TEXT("Send the selected troops away (one that is stuck, say). Asks first. No refund."), bArmed });
	}
	const float BS = Commands.Num() > 9 ? U(46.f) : U(52.f), Gap = Commands.Num() > 9 ? U(5.f) : U(6.f);   // a long row packs tighter
	float BX = Box.Max.X - U(16.f) - Commands.Num() * (BS + Gap) + Gap;
	const float BY = Box.Min.Y + U(44.f);
	for (int32 i = 0; i < Commands.Num(); ++i, BX += BS + Gap)
	{
		const FCommand& C = Commands[i];
		const FBox2D CmdBox(FVector2D(BX, BY), FVector2D(BX + BS, BY + BS));
		const FBtn B = IconButton(CmdBox, SRId::Command + i, C.Which, C.Key, true, C.bActive);
		Text(C.Label, BX + BS * 0.5f, BY + BS + U(4.f), U(13.f), B.bHover ? Parchment : Dim, AlignCentre);
		if (B.bHover)
		{
			FString TitleText = C.Title;
			if (C.Kind == CmdStance) { TitleText = FString::Printf(TEXT("Stance: %s   [G]"), *USRPlatoonSubsystem::StanceName(Stance).ToString()); }
			if (C.Kind == CmdForm) { TitleText = bFormOn ? FString::Printf(TEXT("Formation: %s   [F]"), *USRPlatoonSubsystem::FormationName(Shape).ToString()) : FString(TEXT("Formation: off (loose)   [F]")); }
			SetTooltip(CmdBox, TitleText, { C.Line });
		}
		if (B.bRightClicked && C.Kind == CmdForm) { Click(); PC->CycleFormationCommand(); continue; }
		if (!B.bClicked) { continue; }
		Click();
		switch (C.Kind)
		{
		case CmdAttack: PC->ArmAttackMoveCommand(); break;
		case CmdStop: PC->IssueStop(); break;
		case CmdHold: PC->IssueHold(); break;
		case CmdPatrol: PC->ArmPatrolCommand(); break;
		case CmdStance: PC->CycleStanceCommand(); break;
		case CmdForm: PC->ToggleFormationCommand(); break;
		case CmdDisband: PC->DisbandPlatoonCommand(); break;
		case CmdRepair: PC->RepairCommand(); break;
		case CmdMarch: PC->ToggleMarchCommand(); break;
		case CmdDismiss: PC->DismissCommand(); break;
		case CmdGuard: PC->ArmGuardCommand(); break;
		}
	}
}

void ASRHUD::DrawBuildingSelection(const FBox2D& Box, ASRBuilding* Building)
{
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FSRBuildingStats& Stats = Building->Stats();
	const bool bPlayer = Building->Team == ESRTeam::Player;
	const bool bRecruits = bPlayer && Building->CanRecruit();
	const float X = Box.Min.X + U(18.f), Y = Box.Min.Y + U(12.f);
	// how many troop types it trains (the Citadel: Builders and the Scout): each has its own button on the right
	int32 NumTrained = 0;
	for (const ESRUnitType T : SRAllUnitTypes()) { NumTrained += Building->Trains(T) ? 1 : 0; }
	const bool bWide = bRecruits && NumTrained > 1;
	const float MeterW = bRecruits ? (bWide ? U(96.f) : U(150.f)) : U(260.f);

	Icon(BuildingIcon(Building->BuildingType), X, Y, U(42.f));
	Text(Building->GetDisplayName(), X + U(52.f), Y - U(2.f), U(22.f), bPlayer ? GoldBright : FLinearColor(1.f, 0.55f, 0.45f, 1.f), AlignLeft, Bold);
	{
		FString Sub = bPlayer ? TEXT("Your kingdom") : TEXT("Enemy kingdom");
		// (the player's Citadel has three buttons beside this line: it is kept short)
		if (Building->IsCastle() && bWide) { Sub = FString::Printf(TEXT("Level %d of %d  ·  houses %d"), Building->GetLevel(), F.CastleMaxLevel(), Building->GetPopProvided()); }
		else if (Building->IsCastle()) { Sub += FString::Printf(TEXT("  ·  level %d of %d  ·  houses %d"), Building->GetLevel(), F.CastleMaxLevel(), Building->GetPopProvided()); }
		else if (Building->IsUpgradable()) { Sub += FString::Printf(TEXT("  ·  level %d of %d"), Building->GetLevel(), Building->GetMaxLevel()); }
		if (Building->GetState() == ESRBuildingState::Damaged) { Sub = bWide ? FString::Printf(TEXT("Level %d  ·  badly damaged"), Building->GetLevel()) : Sub + TEXT("  ·  badly damaged"); }
		if (Building->IsUnderRepair()) { Text(bWide ? TEXT("Under repair") : TEXT("Under repair: out of action"), X + U(52.f), Y + U(25.f), U(14.f), Amber, AlignLeft, Bold); }
		else { Text(Sub, X + U(52.f), Y + U(25.f), U(14.f), bPlayer ? Dim : Refuse); }
	}

	const float HY = Y + U(56.f);
	Meter(X, HY, MeterW, U(10.f), Building->GetHealthFrac(), Health(Building->GetHealthFrac()));
	Text(FString::Printf(TEXT("%d / %d"), FMath::CeilToInt(Building->GetHealth()), FMath::RoundToInt(Building->GetMaxHealth())), X + MeterW + U(10.f), HY - U(5.f), U(15.f), Parchment, AlignLeft, Bold);
	const float LY = HY + U(24.f);

	if (Building->IsUnderConstruction())
	{
		Text(FString::Printf(TEXT("Under construction   %d%%"), FMath::RoundToInt(Building->GetBuildProgress() * 100.f)), X, LY, U(15.f), Parchment);
		Meter(X, LY + U(26.f), MeterW, U(9.f), Building->GetBuildProgress(), GoldBright);
		if (bPlayer)
		{
			// outside the castle's zone it only rises while a builder works on it
			const int32 Crew = Building->GetBuildersWorking();
			const bool bWaiting = Building->NeedsBuilder() && Crew == 0;
			const FString Line = bWaiting ? TEXT("Waiting for a Builder (select one, right-click here)")
				: (Crew > 0 ? FString::Printf(TEXT("%d Builder%s at work"), Crew, Crew == 1 ? TEXT("") : TEXT("s")) : FString(TEXT("Inside the castle's zone: raises itself")));
			Text(Line, X, LY + U(42.f), U(13.f), bWaiting ? Refuse : Dim);
		}
		if (bPlayer)
		{
			const FBox2D Cancel(FVector2D(Box.Max.X - U(16.f) - U(200.f), Box.Min.Y + U(48.f)), FVector2D(Box.Max.X - U(16.f), Box.Min.Y + U(104.f)));
			const FBtn B = Button(Cancel, SRId::CancelBuild);
			ButtonFrame(Cancel, B, true);
			Icon(ESRIcon::Cancel, Cancel.Min.X + U(14.f), Cancel.Min.Y + U(15.f), U(26.f));
			TextIn(FBox2D(Cancel.Min + FVector2D(U(50.f), 0.f), Cancel.Max), TEXT("Cancel"), U(18.f), Parchment, AlignLeft, Bold);
			KeyCap(TEXT("Del"), Cancel.Max.X - U(8.f), Cancel.Min.Y + U(18.f), true);
			if (B.bHover) { SetTooltip(Cancel, TEXT("Cancel construction   [Delete]"), { FString::Printf(TEXT("Pull it down and get %d%% of its gold back."), FMath::RoundToInt(F.CancelRefund * 100.f)) }); }
			if (B.bClicked) { Click(); PC->CancelConstructionCommand(); }
		}
		return;
	}

	// damaged: who is mending it (drawn under the health numbers)
	if (bPlayer && Building->NeedsWork())
	{
		const int32 Crew = Building->GetBuildersWorking();
		Text(Crew > 0 ? FString::Printf(TEXT("%d Builder%s repairing"), Crew, Crew == 1 ? TEXT("") : TEXT("s")) : FString(TEXT("Damaged: select Builders and right-click it to repair")),
			X + MeterW + U(100.f), HY - U(4.f), U(13.f), Crew > 0 ? GoldBright : Amber);
	}

	if (Building->BuildingType == ESRBuildingType::Farm || Building->BuildingType == ESRBuildingType::Mine)
	{
		const bool bFarm = Building->BuildingType == ESRBuildingType::Farm;
		Icon(bFarm ? ESRIcon::Food : ESRIcon::Coin, X, LY, U(20.f));
		Text(FString::Printf(TEXT("+%d %s every %.0f s"), Building->GetPayoutAmount(), bFarm ? TEXT("food") : TEXT("gold"), bFarm ? F.FarmPayoutInterval : F.MinePayoutInterval),
			X + U(27.f), LY, U(15.f), Parchment);
		if (bPlayer && Building->IsUpgradable())
		{
			const float RW2 = U(190.f), RX = Box.Max.X - U(16.f) - RW2;
			DrawUpgradeButton(FBox2D(FVector2D(RX, Box.Min.Y + U(16.f)), FVector2D(RX + RW2, Box.Max.Y - U(16.f))), Building);
		}
		Meter(X, LY + U(28.f), MeterW, U(8.f), Building->GetPayoutFraction(), bFarm ? FoodColor : Gold);
		if (Stats.PopProvided > 0) { Text(FString::Printf(TEXT("Houses %d troops"), Stats.PopProvided), X + MeterW + U(14.f), LY + U(22.f), U(14.f), Dim); }
		return;
	}
	if (Building->BuildingType == ESRBuildingType::Tower)
	{
		Text(FString::Printf(TEXT("Level %d: %.0f damage every %.2f s"), Building->GetLevel(), Building->GetAttackDamage(), Building->GetAttackInterval()), X, LY, U(15.f), Parchment);
		Text(FString::Printf(TEXT("Reach %.0f m (the orange circle)"), Building->GetAttackRange() / 100.f), X, LY + U(22.f), U(14.f), Dim);
		if (bPlayer && Building->IsUpgradable())
		{
			const float RW2 = U(190.f), RX = Box.Max.X - U(16.f) - RW2;
			DrawUpgradeButton(FBox2D(FVector2D(RX, Box.Min.Y + U(16.f)), FVector2D(RX + RW2, Box.Max.Y - U(16.f))), Building);
		}
		return;
	}
	if (Building->IsStore())
	{
		// a granary / treasury: what it holds, and how full the kingdom's stores of that resource are
		const bool bGranary = Building->BuildingType == ESRBuildingType::Granary;
		const ESRResource Resource = bGranary ? ESRResource::Food : ESRResource::Gold;
		Icon(bGranary ? ESRIcon::Food : ESRIcon::Coin, X, LY, U(20.f));
		Text(FString::Printf(TEXT("Holds %d %s"), Building->GetStoreCapacity(), bGranary ? TEXT("food") : TEXT("gold")), X + U(27.f), LY, U(15.f), Parchment);
		if (bPlayer)
		{
			const int32 Have = Economy->GetResource(ESRTeam::Player, Resource), Store = Economy->GetStorage(ESRTeam::Player, Resource);
			Meter(X, LY + U(28.f), MeterW, U(8.f), Store > 0 ? FMath::Clamp(float(Have) / Store, 0.f, 1.f) : 0.f, Have >= Store ? Amber : (bGranary ? FoodColor : Gold));
			Text(FString::Printf(TEXT("Kingdom: %d / %d"), Have, Store), X + MeterW + U(14.f), LY + U(22.f), U(14.f), Have >= Store ? Amber : Dim);
			if (Building->IsUpgradable())
			{
				const float RW2 = U(190.f), RX = Box.Max.X - U(16.f) - RW2;
				DrawUpgradeButton(FBox2D(FVector2D(RX, Box.Min.Y + U(16.f)), FVector2D(RX + RW2, Box.Max.Y - U(16.f))), Building);
			}
		}
		return;
	}
	if (!bRecruits)
	{
		if (Building->IsCastle()) { Text(bPlayer ? TEXT("The seat of your kingdom. If it falls, you lose.") : TEXT("The enemy's seat. Bring it down to win."), X, LY, U(15.f), Parchment); }
		else if (Building->IsRecruiter()) { Text(FString::Printf(TEXT("Trains %ss."), *F.StatsFor(Stats.RecruitType).DisplayName), X, LY, U(15.f), Parchment); }
		return;
	}

	// ---- the player's barracks / range: the queue on the left, the recruit button on the right
	const TArray<ESRUnitType>& Queue = Building->GetQueue();
	if (Queue.Num() == 0)
	{
		Text(Building->IsCastle() ? TEXT("Trains Builders and a Scout.") : TEXT("Recruit troops for food."), X, LY, U(15.f), Parchment);
		Text(TEXT("RMB on the ground: rally point"), X, LY + U(19.f), U(13.f), Dim);
	}
	else
	{
		float QX = X + Text(TEXT("Training"), X, LY + U(3.f), U(14.f), Dim) + U(8.f);
		// the one in training is drawn larger and bright; the ones waiting are grouped into runs of the same troop
		// ("x9"), so a queue of any length fits
		Icon(SRUnitIcon(Queue[0]), QX, LY - U(2.f), U(26.f));
		QX += U(29.f);
		int32 Runs = 0;
		for (int32 i = 1; i < Queue.Num();)
		{
			int32 n = 1;
			while (i + n < Queue.Num() && Queue[i + n] == Queue[i]) { ++n; }
			if (++Runs > 4)
			{
				Text(FString::Printf(TEXT("+%d"), Queue.Num() - i), QX + U(2.f), LY, U(15.f), Parchment, AlignLeft, Bold);
				break;
			}
			Icon(SRUnitIcon(Queue[i]), QX, LY + U(2.f), U(20.f), FLinearColor(1.f, 1.f, 1.f, 0.7f));
			QX += U(22.f);
			if (n > 1) { QX += Text(FString::Printf(TEXT("x%d"), n), QX, LY + U(2.f), U(15.f), Parchment, AlignLeft, Bold) + U(3.f); }
			QX += U(4.f);
			i += n;
		}
		Meter(X, LY + U(28.f), bWide ? U(200.f) : U(240.f), U(8.f), Building->GetBuildFraction(), GoldBright);
	}

	// which platoon its recruits join: none, or 1-6 (Ctrl+1-6 with it selected does the same)
	if (!Building->IsCastle())
	{
		USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this);
		const int32 NumP = Platoons ? FMath::Min(Platoons->Num(), 9) : 0;
		const float CS = U(17.f), CG = U(3.f), CY2 = LY + U(41.f);
		float CX2 = X + Text(TEXT("Joins"), X, CY2 + U(1.f), U(13.f), Dim) + U(7.f);
		const int32 Assigned = Building->GetAssignedPlatoon();
		for (int32 p = -1; p < NumP; ++p)
		{
			const FBox2D Chip(FVector2D(CX2, CY2), FVector2D(CX2 + (p < 0 ? CS * 2.f : CS), CY2 + CS));
			const FBtn CB = Button(Chip, SRId::JoinPlatoon + uint32(p + 1));
			const bool bOn = Assigned == p || (p < 0 && Assigned == INDEX_NONE);
			const FLinearColor PCol = p < 0 ? Parchment : USRPlatoonSubsystem::PlatoonColor(p);
			Fill(Chip.Min.X, Chip.Min.Y, Chip.Max.X - Chip.Min.X, CS, bOn ? A(PCol, p < 0 ? 0.35f : 0.85f) : A(FLinearColor::Black, CB.bHover ? 0.55f : 0.35f));
			Outline(Chip, A(PCol, bOn || CB.bHover ? 1.f : 0.45f), FMath::Max(1.f, U(1.5f)));
			Text(p < 0 ? FString(TEXT("none")) : FString::FromInt(p + 1), (Chip.Min.X + Chip.Max.X) * 0.5f, CY2 + U(1.f), U(12.f), bOn && p >= 0 ? FLinearColor::Black : Parchment, AlignCentre, Bold, 0.f, !(bOn && p >= 0));
			if (CB.bHover)
			{
				SetTooltip(Chip, p < 0 ? TEXT("Recruits join no platoon") : FString::Printf(TEXT("Recruits join platoon %d"), p + 1),
					{ p < 0 ? FString(TEXT("They gather at the rally point (or the platoon panel's recruit platoon).")) : FString(TEXT("Each new troop from here joins the platoon and marches to it; made again if it was wiped out.")),
					  TEXT("Ctrl+1-6 with this building selected sets it too.") });
			}
			if (CB.bClicked && !bOn) { PC->AssignBuildingPlatoon(Building, p); }
			CX2 = Chip.Max.X + CG;
		}
	}

	const int32 Pop = Economy->GetPopulation(ESRTeam::Player) + Economy->GetQueuedPopulation(ESRTeam::Player), Cap = Economy->GetPopulationCap(ESRTeam::Player);
	const float RW = bWide ? U(160.f) : U(190.f), RGap = U(10.f);

	// the castle: raise it a level (more housing, stronger walls, a wider building zone), left of the Builder button;
	// a barracks / range / stable / workshop: drill it to train faster, left of its recruit button
	if (Building->IsCastle() || (Building->IsTrainer() && Building->IsUpgradable()))
	{
		const float RX = Box.Max.X - U(16.f) - (RW + RGap) * NumTrained - RW;
		DrawUpgradeButton(FBox2D(FVector2D(RX, Box.Min.Y + U(16.f)), FVector2D(RX + RW, Box.Max.Y - U(16.f))), Building);
	}
	int32 ButtonSlot = 0;   // recruit buttons, left to right in recruit-menu order
	for (const ESRUnitType Type : SRAllUnitTypes())
	{
		const int32 i = int32(Type);
		if (!Building->Trains(Type)) { continue; }
		const FSRUnitStats& Unit = F.StatsFor(Type);
		const FSRCost& Cost = F.CostFor(Type);
		const bool bGold = Economy->GetResource(ESRTeam::Player, ESRResource::Gold) >= Cost.Gold;
		const bool bFood = Economy->GetResource(ESRTeam::Player, ESRResource::Food) >= Cost.Food;
		const bool bRoom = F.MaxRecruitQueue <= 0 || Queue.Num() < F.MaxRecruitQueue;
		const bool bHoused = Unit.PopCost <= 0 || Pop + Unit.PopCost <= Cap;
		int32 BQueued = 0;
		const bool bCapped = Type == ESRUnitType::Builder && Economy->GetBuilderCount(ESRTeam::Player, &BQueued) + BQueued >= Economy->GetMaxBuilders(ESRTeam::Player);
		// the Scout: locked below a castle level, one at a time, and a wait between two (USREconomySubsystem::GetScoutRefusal)
		const bool bScout = Type == ESRUnitType::Scout;
		const bool bLocked = bScout && Economy->GetCastleLevel(ESRTeam::Player) < F.ScoutCastleLevel;
		int32 SQueued = 0;
		const bool bScoutOut = bScout && !bLocked && Economy->GetScoutCount(ESRTeam::Player, &SQueued) + SQueued >= F.MaxScouts;
		const int32 WaitSec = bScout && !bLocked ? FMath::CeilToInt(Economy->GetScoutCooldown(ESRTeam::Player)) : 0;
		const bool bEnabled = bGold && bFood && bRoom && bHoused && !bCapped && !bLocked && !bScoutOut && WaitSec <= 0;
		const float RX = Box.Max.X - U(16.f) - RW * (NumTrained - ButtonSlot) - RGap * (NumTrained - 1 - ButtonSlot);
		++ButtonSlot;
		const FBox2D R(FVector2D(RX, Box.Min.Y + U(16.f)), FVector2D(RX + RW, Box.Max.Y - U(16.f)));
		// always clickable: a refused press shakes the counter that fell short (the castle says why)
		FBtn B = Button(R, SRId::Recruit + i);
		if (!bEnabled) { B.Hot *= 0.3f; }
		ButtonFrame(R, B, bEnabled);
		const float Since = float(Now - PC->GetLastRecruitTime());
		if (PC->GetLastRecruitButton() == i && Since < 0.22f)
		{
			// the press answers at once: gold if it was taken, red if refused
			Fill(R.Min.X, R.Min.Y, RW, R.Max.Y - R.Min.Y, A(PC->WasLastRecruitAccepted() ? GoldBright : Refuse, 0.45f * (1.f - Since / 0.22f)));
		}
		const float Lift = B.bHeld ? U(1.f) : 0.f;
		const float PortraitSize = bWide ? U(40.f) : U(48.f);
		Icon(SRUnitIcon(Type), R.Min.X + U(9.f), R.Min.Y + U(12.f) + Lift, PortraitSize, bEnabled ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
		const float TX = R.Min.X + U(16.f) + PortraitSize;
		Text(Unit.DisplayName, TX, R.Min.Y + U(30.f) + Lift, U(14.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
		KeyCap(SRUnitKey(Type), R.Max.X - U(6.f), R.Min.Y + U(6.f), bEnabled);
		float CX = TX;
		const float CY = R.Min.Y + U(52.f) + Lift;
		if (Cost.Gold > 0)
		{
			Icon(ESRIcon::Coin, CX, CY + U(1.f), U(17.f));
			CX += U(21.f);
			CX += Text(FString::FromInt(Cost.Gold), CX, CY, U(16.f), bGold ? GoldBright : Refuse, AlignLeft, Bold) + U(8.f);
		}
		Icon(ESRIcon::Food, CX, CY + U(1.f), U(17.f));
		Text(FString::FromInt(Cost.Food), CX + U(21.f), CY, U(16.f), bFood ? FoodColor : Refuse, AlignLeft, Bold);
		FString Status = bCapped ? FString::Printf(TEXT("Limit %d reached"), Economy->GetMaxBuilders(ESRTeam::Player)) : (!bHoused ? TEXT("Housing full") : (!bRoom ? TEXT("Queue full") : FString::Printf(TEXT("Trains in %.0f s"), Building->GetTrainTime(Type))));
		const FString WaitText = FString::Printf(TEXT("%d:%02d"), WaitSec / 60, WaitSec % 60);
		if (bLocked) { Status = FString::Printf(TEXT("Citadel level %d"), F.ScoutCastleLevel); }
		else if (bScoutOut) { Status = SQueued > 0 ? FString(TEXT("In training")) : (WaitSec > 0 ? FString::Printf(TEXT("In the field  ·  %s"), *WaitText) : FString(TEXT("In the field"))); }
		else if (WaitSec > 0) { Status = FString::Printf(TEXT("Ready in %s"), *WaitText); }
		Text(Status, R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), (!bHoused || !bRoom || bCapped || bLocked || WaitSec > 0) ? Refuse : (bScoutOut ? Amber : Dim));
		if (B.bClicked) { PC->RecruitTroop(Type, PC->RecruitCountFromModifiers()); if (bEnabled) { Click(); } }
		if (B.bHover)
		{
			TArray<FString> Lines;
			static const TCHAR* Blurbs[SRNumUnitTypes] = { TEXT("Heavy infantry: holds the line and hits hard."), TEXT("Light and quick, with a long reach. Weak up close."),
				TEXT("Fast cavalry: its charge lands double. Raids and runs down archers."), TEXT("Siege: long range, splash, wrecks buildings. Slow, weak up close."),
				TEXT("Raises buildings outside the castle's zone and repairs damaged ones. Does not fight."),
				TEXT("Outruns cavalry and sees far. Foes (and their towers) only notice it from close by. Fragile: no fighter.") };
			Lines.Add(Blurbs[FMath::Clamp(i, 0, SRNumUnitTypes - 1)]);
			Lines.Add(Cost.Gold > 0
				? FString::Printf(TEXT("Cost %d food + %d gold   ·   trains in %.0f s   ·   %d housing"), Cost.Food, Cost.Gold, Building->GetTrainTime(Type), Unit.PopCost)
				: FString::Printf(TEXT("Cost %d food   ·   trains in %.0f s   ·   %d housing"), Cost.Food, Building->GetTrainTime(Type), Unit.PopCost));
			if (bScout)
			{
				const int32 Every = FMath::RoundToInt(F.ScoutCooldown);
				Lines.Add(FString::Printf(TEXT("One Scout at a time   ·   needs the Citadel at level %d"), F.ScoutCastleLevel));
				if (Every > 0) { Lines.Add(FString::Printf(TEXT("A new one can be trained %d:%02d after the last was ordered (even if it is lost or dismissed)."), Every / 60, Every % 60)); }
				if (bLocked) { Lines.Add(FString::Printf(TEXT("Locked: raise the Citadel to level %d."), F.ScoutCastleLevel)); }
				else if (bScoutOut) { Lines.Add(SQueued > 0 ? TEXT("Your Scout is in training.") : TEXT("Your Scout is in the field.")); }
				if (!bLocked && WaitSec > 0) { Lines.Add(FString::Printf(TEXT("The next can be trained in %s."), *WaitText)); }
			}
			else { Lines.Add(FString::Printf(TEXT("Shift+click: %d at once   ·   Ctrl / Option+click: %d"), F.RecruitBatch, F.RecruitBatchLarge)); }
			if (!bHoused) { Lines.Add(TEXT("Housing is full: build more farms.")); }
			SetTooltip(R, FString::Printf(TEXT("%s   [%s]"), *Unit.DisplayName, SRUnitKey(Type)), Lines);
		}
	}
}

// ---------------------------------------------------------------------------- platoons

void ASRHUD::DrawPlatoonPanel()
{
	USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this);
	if (!Platoons) { return; }
	USRUserSettings* User = USRUserSettings::Get();
	const int32 Num = Platoons->Num();
	const float W = U(292.f), HeaderH = U(34.f), RowH = U(56.f), EmptyH = U(28.f), Gap = U(4.f), Pad = U(8.f);

	TArray<FSRPlatoonInfo, TInlineAllocator<9>> Infos;
	int32 Formed = 0;
	float Height = HeaderH + (User->bPlatoonsCollapsed ? 0.f : Pad);
	for (int32 i = 0; i < Num; ++i)
	{
		Infos.Add(Platoons->GetInfo(i));
		Formed += Infos[i].bExists ? 1 : 0;
		if (!User->bPlatoonsCollapsed) { Height += (Infos[i].bExists ? RowH : EmptyH) + Gap; }
	}
	const float X = View.X - U(14.f) - W, Y = View.Y - U(14.f) - Height;
	const FBox2D Box(FVector2D(X, Y), FVector2D(X + W, Y + Height));
	HudPanel(Box);

	// header: click to fold the panel away
	const FBox2D Header(FVector2D(X, Y), FVector2D(X + W, Y + HeaderH));
	const FBtn HB = Button(Header, SRId::PlatoonHeader);
	TextIn(FBox2D(Header.Min + FVector2D(U(14.f), U(2.f)), Header.Max), TEXT("PLATOONS"), U(15.f), FMath::Lerp(Gold, GoldBright, HB.Hot), AlignLeft, Bold, U(2.f));
	TextIn(FBox2D(Header.Min + FVector2D(U(124.f), U(2.f)), Header.Max), FString::Printf(TEXT("%d / %d"), Formed, Num), U(14.f), Dim, AlignLeft);
	Icon(User->bPlatoonsCollapsed ? ESRIcon::ChevronUp : ESRIcon::ChevronDown, Header.Max.X - U(30.f), Header.Min.Y + U(9.f), U(18.f), FLinearColor(1.f, 1.f, 1.f, 0.7f + 0.3f * HB.Hot));
	if (HB.bClicked)
	{
		Click();
		User->bPlatoonsCollapsed = !User->bPlatoonsCollapsed;
		User->SaveConfig();
	}
	if (User->bPlatoonsCollapsed) { return; }

	const int32 Selected = PC->GetSelectedPlatoon();
	const int32 RecruitTarget = Platoons->GetRecruitTarget();
	float RY = Y + HeaderH;
	for (int32 i = 0; i < Num; ++i)
	{
		const FSRPlatoonInfo& Info = Infos[i];
		const float H = Info.bExists ? RowH : EmptyH;
		const FBox2D Row(FVector2D(X + Pad, RY), FVector2D(X + W - Pad, RY + H));
		RY += H + Gap;
		const FBox2D Badge(Row.Min, FVector2D(Row.Min.X + U(26.f), Row.Max.Y));
		if (!Info.bExists)
		{
			Fill(Row.Min.X, Row.Min.Y, Row.Max.X - Row.Min.X, H, A(Inset, 0.6f));
			TextIn(Badge, FString::FromInt(i + 1), U(16.f), A(Dim, 0.7f), AlignCentre, Bold);
			TextIn(FBox2D(Row.Min + FVector2D(U(34.f), 0.f), Row.Max), FString::Printf(TEXT("Ctrl+%d to form"), i + 1), U(14.f), A(Dim, 0.75f), AlignLeft);
			continue;
		}

		// the four small buttons claim their clicks before the row itself does
		const float SB = U(30.f), SG = U(3.f);
		FBox2D Small[4];
		FBtn SmallB[4];
		for (int32 k = 0; k < 4; ++k)
		{
			const float SX = Row.Max.X - U(5.f) - (4 - k) * SB - (3 - k) * SG;
			Small[k] = FBox2D(FVector2D(SX, Row.Min.Y + (H - SB) * 0.5f), FVector2D(SX + SB, Row.Min.Y + (H - SB) * 0.5f + SB));
			SmallB[k] = Button(Small[k], SRId::Slot + i * 5 + 1 + k);
		}
		const FBtn RB = Button(Row, SRId::Slot + i * 5);
		const bool bSelected = Selected == i;
		Fill(Row.Min.X, Row.Min.Y, Row.Max.X - Row.Min.X, H, bSelected ? FLinearColor(0.20f, 0.155f, 0.05f, 0.95f) : FMath::Lerp(Inset, ButtonHot, RB.Hot * 0.7f));
		if (bSelected) { Outline(Row, Gold, FMath::Max(1.f, U(1.f))); }
		// the platoon's own colour: the badge behind its number (and the rings under its troops); engaged, the edge burns
		const FLinearColor PCol = USRPlatoonSubsystem::PlatoonColor(i);
		Fill(Row.Min.X, Row.Min.Y, U(5.f), H, Info.Engaged > 0 ? A(Refuse, 0.65f + 0.35f * FMath::Sin(float(Now) * 8.f)) : PCol);
		Fill(Badge.Min.X + U(6.f), Badge.Min.Y + U(6.f), Badge.Max.X - Badge.Min.X - U(3.f), H - U(12.f), FLinearColor(PCol.R * 0.28f, PCol.G * 0.28f, PCol.B * 0.28f, 0.95f));
		Outline(FBox2D(Badge.Min + FVector2D(U(6.f), U(6.f)), FVector2D(Badge.Max.X + U(3.f), Badge.Max.Y - U(6.f))), PCol, FMath::Max(1.f, U(1.f)));
		TextIn(FBox2D(Badge.Min + FVector2D(U(4.5f), 0.f), Badge.Max + FVector2D(U(4.5f), 0.f)), FString::FromInt(i + 1), U(20.f), PCol, AlignCentre, Black);
		const ESRIcon Kind = Info.Kind == ESRPlatoonKind::ArcherCompany ? ESRIcon::Bow : (Info.Kind == ESRPlatoonKind::MixedHost ? ESRIcon::Pop
			: (Info.Kind == ESRPlatoonKind::Cavalry ? ESRIcon::PortraitHorse : (Info.Kind == ESRPlatoonKind::SiegeTrain ? ESRIcon::PortraitCatapult
			: (Info.Kind == ESRPlatoonKind::WorkCrew ? ESRIcon::Hammer : ESRIcon::Shield))));
		Icon(Kind, Row.Min.X + U(32.f), Row.Min.Y + (H - U(30.f)) * 0.5f, U(30.f));

		const float TX = Row.Min.X + U(68.f), TW = Small[0].Min.X - TX - U(6.f);
		FString Name = Info.Name;
		if (TextSize(Name, U(14.f), Bold).X > TW)
		{
			while (Name.Len() > 2 && TextSize(Name + TEXT("\u2026"), U(14.f), Bold).X > TW) { Name.LeftChopInline(1); }
			Name = Name.TrimEnd() + TEXT("\u2026");
		}
		Text(Name, TX, Row.Min.Y + U(4.f), U(14.f), Parchment, AlignLeft, Bold);
		float CX = TX;
		const float CY = Row.Min.Y + U(24.f);
		const int32 Counts[6] = { Info.Shieldbearers, Info.Archers, Info.Riders, Info.Catapults, Info.Builders, Info.Scouts };
		const ESRIcon Icons[6] = { ESRIcon::Shield, ESRIcon::Bow, ESRIcon::PortraitHorse, ESRIcon::PortraitCatapult, ESRIcon::Hammer, ESRIcon::PortraitScout };
		for (int32 k = 0; k < 6; ++k)
		{
			if (k >= 2 && Counts[k] == 0) { continue; }
			Icon(Icons[k], CX, CY, U(16.f));
			CX += U(18.f) + Text(FString::FromInt(Counts[k]), CX + U(18.f), CY - U(1.f), U(14.f), Parchment) + U(7.f);
		}
		if (Info.Engaged > 0) { Icon(ESRIcon::Swords, CX, CY, U(16.f), FLinearColor(1.f, 1.f, 1.f, 0.65f + 0.35f * FMath::Sin(float(Now) * 8.f))); }
		Meter(TX, Row.Max.Y - U(9.f), TW - U(4.f), U(4.f), Info.Health, Health(Info.Health));

		const bool bRecruits = RecruitTarget == i;
		ButtonFrame(Small[0], SmallB[0], true);
		Icon(Info.bFormation ? FormationIcon(Info.Formation) : ESRIcon::Pop, Small[0].Min.X + U(5.f), Small[0].Min.Y + U(5.f), SB - U(10.f), FLinearColor(1.f, 1.f, 1.f, Info.bFormation ? 1.f : 0.55f));
		ButtonFrame(Small[1], SmallB[1], true);
		Icon(StanceIcon(Info.Stance), Small[1].Min.X + U(5.f), Small[1].Min.Y + U(5.f), SB - U(10.f));
		ButtonFrame(Small[2], SmallB[2], true, bRecruits);
		Icon(ESRIcon::RecruitFlag, Small[2].Min.X + U(5.f), Small[2].Min.Y + U(5.f), SB - U(10.f), FLinearColor(1.f, 1.f, 1.f, bRecruits ? 1.f : 0.4f));
		ButtonFrame(Small[3], SmallB[3], true);
		Icon(ESRIcon::Disband, Small[3].Min.X + U(5.f), Small[3].Min.Y + U(5.f), SB - U(10.f));
		if (SmallB[3].bHover) { SetTooltip(Small[3], TEXT("Disband"), { TEXT("Break up the platoon (the troops stay)."), TEXT("A platoon whose troops all fall disbands itself.") }); }
		if (SmallB[3].bClicked) { Click(); Platoons->Disband(i); continue; }
		if (SmallB[0].bHover)
		{
			SetTooltip(Small[0], Info.bFormation ? FString::Printf(TEXT("Formation: %s"), *USRPlatoonSubsystem::FormationName(Info.Formation).ToString()) : FString(TEXT("Formation: off (loose)")),
				{ TEXT("Click (or F): on / off. Right-click: next shape.") });
		}
		if (SmallB[1].bHover) { SetTooltip(Small[1], FString::Printf(TEXT("Stance: %s"), *USRPlatoonSubsystem::StanceName(Info.Stance).ToString()), { TEXT("Click (or G) to change.") }); }
		if (SmallB[2].bHover) { SetTooltip(Small[2], bRecruits ? TEXT("Recruits join here") : TEXT("Recruits do not join"), { TEXT("New troops from your barracks and ranges march to this platoon.") }); }
		if (SmallB[0].bClicked) { Click(); Platoons->ToggleFormation(i); }
		if (SmallB[0].bRightClicked) { Click(); Platoons->CycleFormation(i); }
		if (SmallB[1].bClicked) { Click(); Platoons->CycleStance(i); }
		if (SmallB[2].bClicked) { Click(); Platoons->SetRecruitTarget(bRecruits ? INDEX_NONE : i); }
		if (RB.bClicked)
		{
			// click selects; a second click soon after also brings the camera
			const bool bDouble = LastSlotClicked == i && Now - LastSlotClickTime < 0.35;
			LastSlotClicked = i;
			LastSlotClickTime = Now;
			PC->SelectPlatoon(i, bDouble);
		}
		if (RB.bHover && !SmallB[0].bHover && !SmallB[1].bHover && !SmallB[2].bHover)
		{
			SetTooltip(Row, Info.Name, { FString::Printf(TEXT("%s  ·  %d troops  ·  %d%% health"), *USRPlatoonSubsystem::KindName(Info.Kind).ToString(), Info.Shieldbearers + Info.Archers + Info.Riders + Info.Catapults + Info.Builders, FMath::RoundToInt(Info.Health * 100.f)),
				FString::Printf(TEXT("Click or press %d to select; twice to go there."), i + 1) });
		}
	}
}
