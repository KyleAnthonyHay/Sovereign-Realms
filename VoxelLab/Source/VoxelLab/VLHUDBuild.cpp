// Building in the HUD: the main game's Build button and build menu (SRHUDGame.cpp DrawBuildMenu), its placing cursor
// (DrawPlacementCursor) and placement preview's ground plates (SRPlacementPreview), the construction bars over sites,
// a site's panel and the Cancel / Demolish buttons, the castle's Builder button, and the top bar's counters for the
// Builders and the Scout (here: the hero, the Builders and the Spy). Ported onto UVLConstruction (VLConstruction.*).

#include "VLHUD.h"
#include "VLHUDStyle.h"
#include "VoxelLab.h"
#include "VLKing.h"
#include "VLBattle.h"
#include "VLCommand.h"
#include "VLConstruction.h"
#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "GlobalRenderResources.h"

using namespace VLStyle;

namespace
{
	FLinearColor ToLinear(const FLinearColor& C) { return FLinearColor(FMath::Pow(C.R, 2.2f), FMath::Pow(C.G, 2.2f), FMath::Pow(C.B, 2.2f), C.A); }

	EVLIcon BuildIcon(EVLBuilding Kind)
	{
		switch (Kind)
		{
		case EVLBuilding::Farm: return EVLIcon::Farm;
		case EVLBuilding::Mine: return EVLIcon::Mine;
		case EVLBuilding::Tower: return EVLIcon::Tower;
		case EVLBuilding::Barracks: return EVLIcon::Barracks;
		case EVLBuilding::Range: return EVLIcon::Range;
		default: return EVLIcon::Castle;
		}
	}

	FString CostLine(const FVLCost& C)
	{
		return C.Food > 0 ? FString::Printf(TEXT("%d gold + %d food"), C.Gold, C.Food) : FString::Printf(TEXT("%d gold"), C.Gold);
	}

	/** The top of a building's bounds, over its middle (where its bars go). */
	FVector TopOf(const AActor* A)
	{
		FVector Origin, Extent;
		A->GetActorBounds(true, Origin, Extent);
		return FVector(Origin.X, Origin.Y, Origin.Z + Extent.Z + 120.f);
	}

	AVLKing* PlayersKing(const UWorld* World)
	{
		for (TActorIterator<AVLKing> It(World); It; ++It)
		{
			if (!It->IsTroop() && It->Team == UVLBattle::Player)
			{
				return *It;
			}
		}
		return nullptr;
	}
}

// ---------------------------------------------------------------------------- the Build button and menu

void AVLHUD::DrawBuildMenu(float X, float Bottom)
{
	UVLConstruction* C = UVLConstruction::Get(this);
	UVLBattle* Battle = UVLBattle::Get(this);
	if (!C || !Battle || !Battle->IsPlaying())
	{
		return;
	}
	const bool bOpen = C->IsMenuOpen();

	// ---- the Build button: as tall as the minimap
	const float BW = U(76.f), BH = U(266.f);
	const FBox2D Toggle(FVector2D(X, Bottom - BH), FVector2D(X + BW, Bottom));
	Block(Toggle);
	const FBtn T = Button(Toggle, VLId::Build);
	Fill(Toggle.Min.X + U(2.f), Toggle.Min.Y + U(4.f), BW, BH, FLinearColor(0.f, 0.f, 0.f, 0.35f));
	ButtonFrame(Toggle, T, true, bOpen || C->IsPlacing());
	const float Lift = T.bHeld ? U(1.f) : 0.f;
	Icon(EVLIcon::Hammer, Toggle.Min.X + (BW - U(46.f)) * 0.5f, Toggle.Min.Y + BH * 0.5f - U(40.f) + Lift, U(46.f));
	Text(TEXT("Build"), Toggle.Min.X + BW * 0.5f, Toggle.Min.Y + BH * 0.5f + U(14.f) + Lift, U(17.f), Parchment, AlignCentre, Bold);
	KeyCap(TEXT("B"), Toggle.Max.X - U(4.f), Toggle.Min.Y + U(4.f), true);
	if (T.bClicked)
	{
		Click();
		if (C->IsPlacing())
		{
			C->CancelPlacement();
		}
		C->ToggleMenu();
	}
	if (T.bHover)
	{
		SetTooltip(Toggle, TEXT("Build   [B]"), { TEXT("Farms, mines, barracks, ranges and towers."), TEXT("Buildings are paid for in gold; only Builders raise them.") });
	}
	if (!bOpen)
	{
		return;
	}

	// ---- the menu: tabs along the top, the tab's buildings below
	const float Pad = U(12.f), TabH = U(42.f), CardW = U(118.f), CardH = U(132.f), Gap = U(8.f);
	const float PW = Pad * 2.f + 4.f * CardW + 3.f * Gap, PH = Pad * 2.f + TabH + Gap + CardH + U(24.f);   // room for four cards a tab
	const float PX = Toggle.Max.X + U(10.f), PY = Bottom - U(152.f) - U(10.f) - PH;
	const FBox2D Box(FVector2D(PX, PY), FVector2D(PX + PW, PY + PH));
	HudPanel(Box);
	static const EVLIcon TabIcons[3] = { EVLIcon::Coin, EVLIcon::Swords, EVLIcon::Tower };
	const float TW = (PW - 2.f * Pad - 2.f * Gap) / 3.f;
	for (int32 t = 0; t < 3; ++t)
	{
		const FBox2D TabBox(FVector2D(PX + Pad + t * (TW + Gap), PY + Pad), FVector2D(PX + Pad + t * (TW + Gap) + TW, PY + Pad + TabH));
		const bool bSel = C->GetTab() == t;
		const FBtn B = Button(TabBox, VLId::Build + 1 + t);
		ButtonFrame(TabBox, B, true, bSel);
		Icon(TabIcons[t], TabBox.Min.X + U(10.f), TabBox.Min.Y + (TabH - U(22.f)) * 0.5f, U(22.f), FLinearColor(1.f, 1.f, 1.f, bSel ? 1.f : 0.7f));
		TextIn(FBox2D(TabBox.Min + FVector2D(U(38.f), 0.f), TabBox.Max), VLBuild::TabName(t), U(16.f), bSel ? GoldBright : Parchment, AlignLeft, Bold);
		if (B.bClicked && !bSel) { Click(); C->SetTab(t); }
	}

	TArray<const VLBuild::FSpec*> Entries;
	VLBuild::TabEntries(C->GetTab(), Entries);
	const float CY = PY + Pad + TabH + Gap;
	for (int32 i = 0; i < Entries.Num() && i < 6; ++i)
	{
		const VLBuild::FSpec& S = *Entries[i];
		const FString Why = C->BuildRefusal(S.Kind, UVLBattle::Player);
		const int32 Limit = C->BuildLimit(S.Kind, UVLBattle::Player);
		const int32 Have = C->CountRaised(S.Kind, UVLBattle::Player);
		const bool bCapped = Limit != INDEX_NONE && Have >= Limit;
		const bool bAfford = Why.IsEmpty();
		const FBox2D Card(FVector2D(PX + Pad + i * (CardW + Gap), CY), FVector2D(PX + Pad + i * (CardW + Gap) + CardW, CY + CardH));
		// always clickable: one that is refused flashes the gold counter or says why (UVLConstruction::BeginPlacement)
		FBtn B = Button(Card, VLId::Build + 4 + i);
		if (!bAfford) { B.Hot *= 0.3f; }
		ButtonFrame(Card, B, bAfford, C->GetPlacing() == S.Kind);
		const float L = B.bHeld ? U(1.f) : 0.f;
		Icon(BuildIcon(S.Kind), Card.Min.X + (CardW - U(48.f)) * 0.5f, Card.Min.Y + U(12.f) + L, U(48.f), bAfford ? FLinearColor::White : FLinearColor(0.42f, 0.42f, 0.46f, 0.85f));
		const FString Key = FString::FromInt(i + 1);
		KeyCap(Key, Card.Max.X - U(4.f), Card.Min.Y + U(4.f), bAfford);
		Text(VLRules::Name(S.Kind), Card.Min.X + CardW * 0.5f, Card.Min.Y + U(68.f) + L, U(15.f), bAfford ? Parchment : Dim, AlignCentre, Bold);
		const FString Cost = FString::FromInt(S.Cost.Gold);
		const float CW = U(16.f) + U(4.f) + TextSize(Cost, U(16.f), Bold).X;
		const float CX = Card.Min.X + (CardW - CW) * 0.5f, CostY = Card.Max.Y - U(30.f) + L;
		const bool bGold = Battle->GetStock(UVLBattle::Player, EVLRes::Gold) >= S.Cost.Gold;
		Icon(EVLIcon::Coin, CX, CostY + U(2.f), U(16.f), bGold ? FLinearColor::White : FLinearColor(0.6f, 0.6f, 0.6f, 0.9f));
		Text(Cost, CX + U(20.f), CostY, U(16.f), bGold ? GoldBright : Refuse, AlignLeft, Bold);
		if (Limit != INDEX_NONE)
		{
			// how much of the castle's allowance is used
			Text(FString::Printf(TEXT("%d/%d"), Have, Limit), Card.Min.X + U(6.f), Card.Min.Y + U(4.f), U(13.f), bCapped ? Refuse : Dim, AlignLeft, Bold);
		}
		if (B.bClicked)
		{
			if (bAfford) { Click(); }
			C->BeginPlacement(S.Kind);
		}
		if (B.bHover)
		{
			TArray<FString> Lines;
			Lines.Add(S.Blurb);
			const VLRules::FLevel& Lv = VLRules::Level(S.Kind, 1);
			switch (S.Kind)
			{
			case EVLBuilding::Farm:
				Lines.Add(FString::Printf(TEXT("+%d food every %.0f s, houses %d; upgrade it for more."), Lv.Yield, VLRules::PayoutInterval, Lv.Housing));
				Lines.Add(FString::Printf(TEXT("Farms raised: %d of %d (each castle level allows %d more)."), Have, Limit, VLBuild::FarmLimitPerLevel));
				break;
			case EVLBuilding::Mine:
				Lines.Add(FString::Printf(TEXT("+%d gold every %.0f s; upgrade it for more."), Lv.Yield, VLRules::PayoutInterval));
				break;
			case EVLBuilding::Barracks:
			case EVLBuilding::Range:
			{
				const FString Troop = S.Kind == EVLBuilding::Barracks ? TEXT("Swordsman") : TEXT("Archer");
				Lines.Add(FString::Printf(TEXT("%s: %d food, %.0f s each. With no rally point set they wait in its yard."), *Troop, VLRules::Troop(Troop).Cost.Food, VLRules::Troop(Troop).TrainSeconds));
				break;
			}
			case EVLBuilding::Tower:
				Lines.Add(FString::Printf(TEXT("%.0f damage every %.1f s, reach %.0f m."), Lv.Damage, Lv.Interval, Lv.Range / 100.f));
				Lines.Add(FString::Printf(TEXT("Towers raised: %d of %d (each castle level allows %d more)."), Have, Limit, VLBuild::TowerLimitPerLevel));
				break;
			default: break;
			}
			Lines.Add(FString::Printf(TEXT("Cost %s   ·   %.0f s with one Builder   ·   %.0f health"), *CostLine(S.Cost), S.Seconds, Lv.Health));
			Lines.Add(S.Kind == EVLBuilding::Mine ? FString(TEXT("Rule: on a gold vein (a neutral mine, or the ruin of a fallen one)."))
				: FString(TEXT("Rule: level, dry, open ground. Trees in the way are cleared.")));
			if (!Why.IsEmpty()) { Lines.Add(Why + TEXT(".")); }
			SetTooltip(Card, FString::Printf(TEXT("%s   [%s]"), VLRules::Name(S.Kind), *Key), Lines);
		}
	}
	Text(TEXT("1-6 pick  ·  Esc close  ·  two Builders build twice as fast"), PX + PW * 0.5f, Box.Max.Y - U(26.f), U(13.f), Dim, AlignCentre);
}

// ---------------------------------------------------------------------------- placing

void AVLHUD::DrawPlacement()
{
	const UVLConstruction* C = UVLConstruction::Get(this);
	if (!C || !C->IsPlacing() || !bMouse || !C->HasPlacementUnderPointer() || !King || King->IsHeroMode())
	{
		return;
	}
	for (const FBox2D& Box : Blockers)
	{
		if (Box.IsInside(Mouse))
		{
			return;
		}
	}
	const FVLPlacement& P = C->GetPlacement();
	if (!P.bValid)
	{
		// why the spot is refused, right where the player is looking
		Pill(P.Reason.IsEmpty() ? FString(TEXT("It cannot go there")) : P.Reason, Mouse.X + U(22.f), Mouse.Y + U(24.f), U(16.f), EVLIcon::Cancel, Refuse, 1.f, false);
		return;
	}
	FString Say = P.Vein.IsValid() ? FString(TEXT("Takes over the vein: a Builder will raise the mine")) : FString(TEXT("A Builder will walk here and build it"));
	if (P.Trees > 0)
	{
		Say = FString::Printf(TEXT("%d tree%s cleared   ·   "), P.Trees, P.Trees == 1 ? TEXT("") : TEXT("s")) + Say;
	}
	Pill(Say, Mouse.X + U(22.f), Mouse.Y + U(24.f), U(16.f), EVLIcon::Hammer, GoldBright, 1.f, false);
}

void AVLHUD::GroundPlates(const TArray<FVector>& Centres, const FVector& AxisX, const FVector& AxisY, const TArray<FLinearColor>& Colours)
{
	if (!Canvas || Centres.Num() == 0)
	{
		return;
	}
	TArray<FCanvasUVTri> Tris;
	Tris.Reserve(Centres.Num() * 2);
	for (int32 i = 0; i < Centres.Num() && i < Colours.Num(); ++i)
	{
		const FVector& C = Centres[i];
		const FVector Q[4] = { Project(C - AxisX - AxisY), Project(C + AxisX - AxisY), Project(C + AxisX + AxisY), Project(C - AxisX + AxisY) };
		if (Q[0].Z <= 0.f || Q[1].Z <= 0.f || Q[2].Z <= 0.f || Q[3].Z <= 0.f)
		{
			continue;
		}
		const FLinearColor Col = ToLinear(Colours[i]);
		FCanvasUVTri A, B;
		A.V0_Pos = FVector2D(Q[0]); A.V1_Pos = FVector2D(Q[1]); A.V2_Pos = FVector2D(Q[2]);
		B.V0_Pos = FVector2D(Q[0]); B.V1_Pos = FVector2D(Q[2]); B.V2_Pos = FVector2D(Q[3]);
		A.V0_Color = A.V1_Color = A.V2_Color = B.V0_Color = B.V1_Color = B.V2_Color = Col;
		Tris.Add(A);
		Tris.Add(B);
	}
	if (Tris.Num() > 0)
	{
		FCanvasTriangleItem Item(Tris, GWhiteTexture);
		Item.BlendMode = SE_BLEND_Translucent;
		Canvas->DrawItem(Item);
	}
}

void AVLHUD::DrawBuildFeedback()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const UVLConstruction* C = UVLConstruction::Get(this);
	if (!Battle || !C || Battle->GetState() == EVLMatch::Idle)
	{
		return;
	}
	// ---- placing: plates of about a metre over the footprint (green fine, red refused) and a fringe round it (pale
	// open ground, red where something stands): which ground refuses it, and which way to move it
	if (C->IsPlacing() && C->HasPlacementUnderPointer() && King && !King->IsHeroMode())
	{
		const FVLPlacement& P = C->GetPlacement();
		TArray<FLinearColor> Cols;
		Cols.Reserve(P.CellState.Num());
		for (const uint8 S : P.CellState)
		{
			Cols.Add(S == 0 ? FLinearColor(0.35f, 1.f, 0.45f, P.bValid ? 0.32f : 0.24f) : (S == 1 ? FLinearColor(1.f, 0.25f, 0.18f, 0.62f)
				: (S == 2 ? FLinearColor(0.95f, 0.97f, 0.9f, 0.13f) : FLinearColor(1.f, 0.25f, 0.18f, 0.32f))));
		}
		GroundPlates(P.Cells, P.AxisX, P.AxisY, Cols);
	}
	// ---- sites rising and repairs: a bar over each (the main game's construction bar: red "needs a Builder" while
	// nobody works at it)
	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		if (!B.IsAlive() || (!B.IsSite() && !B.bRepairing) || (B.Team != UVLBattle::Player && !B.IsSite()))
		{
			continue;
		}
		const FVector S = Project(TopOf(B.Actor.Get()));
		if (S.Z <= 0.f)
		{
			continue;
		}
		const float W = U(110.f), H = U(9.f), IS = U(24.f);
		const float X = FMath::RoundToFloat(S.X - W * 0.5f + IS * 0.5f), Y = FMath::RoundToFloat(S.Y - (B.Queue.Num() > 0 ? U(26.f) : 0.f));
		const bool bEnemy = B.Team == UVLBattle::Enemy;
		Icon(EVLIcon::Hammer, X - IS - U(5.f), Y + H * 0.5f - IS * 0.5f, IS, FLinearColor::White, bEnemy);
		if (B.IsSite())
		{
			Meter(X, Y, W, H, B.Build, bEnemy ? FLinearColor(0.95f, 0.4f, 0.3f, 1.f) : GoldBright);
			const FString Label = B.BuildersAt > 0 ? FString::Printf(TEXT("%d%%%s"), FMath::FloorToInt(B.Build * 100.f), B.BuildersAt > 1 ? *FString::Printf(TEXT("  x%d"), B.BuildersAt) : TEXT(""))
				: FString(TEXT("needs a Builder"));
			Text(Label, X + W + U(6.f), Y - U(5.f), U(14.f), B.BuildersAt > 0 ? Parchment : Refuse, AlignLeft, Bold);
		}
		else
		{
			Meter(X, Y, W, H, B.Health / FMath::Max(B.MaxHealth, 1.f), Good);
			Text(TEXT("repairing"), X + W + U(6.f), Y - U(5.f), U(14.f), Parchment, AlignLeft, Bold);
		}
	}
}

// ---------------------------------------------------------------------------- a site's panel, Cancel and Demolish

bool AVLHUD::DrawSitePanel(const FBox2D& Box, AActor* Building)
{
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* C = UVLConstruction::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	if (!St || !C || !St->IsSite())
	{
		return false;
	}
	const bool bPlayer = St->Team == UVLBattle::Player;
	const float X = Box.Min.X + U(18.f), Y = Box.Min.Y + U(12.f);
	Icon(BuildIcon(St->Kind), X, Y, U(42.f), FLinearColor::White, St->Team == UVLBattle::Enemy);
	Text(St->Name, X + U(52.f), Y - U(2.f), U(22.f), bPlayer ? GoldBright : FLinearColor(1.f, 0.55f, 0.45f, 1.f), AlignLeft, Bold);
	const bool bClaim = Building->ActorHasTag(TEXT("Claim"));
	Text(bClaim ? (bPlayer ? TEXT("Your kingdom  ·  being claimed") : TEXT("Enemy kingdom  ·  being claimed")) : bPlayer ? TEXT("Your kingdom  ·  being built") : TEXT("Enemy kingdom  ·  being built"), X + U(52.f), Y + U(25.f), U(14.f), bPlayer ? Dim : Refuse);
	// how far it has risen, and how long it has to go at the rate it rises now
	const VLBuild::FSpec* Spec = VLBuild::Spec(St->Kind);
	const float Work = (1.f - St->Build) * (Spec ? Spec->Seconds : 16.f);
	const float Rate = St->BuildersAt > 0 ? 1.f + VLBuild::ExtraSpeed * (St->BuildersAt - 1) : 0.f;
	const float MW = U(330.f), HY = Y + U(56.f);
	Meter(X, HY, MW, U(10.f), St->Build, GoldBright);
	Text(Rate > 0.f ? FString::Printf(TEXT("%d%%  ·  %s left"), FMath::FloorToInt(St->Build * 100.f), *Countdown(Work / Rate)) : FString::Printf(TEXT("%d%%  ·  waiting"), FMath::FloorToInt(St->Build * 100.f)),
		X + MW + U(10.f), HY - U(5.f), U(15.f), Parchment, AlignLeft, Bold);
	const float LY = HY + U(24.f);
	if (St->BuildersAt > 0)
	{
		Portrait(EVLPortrait::Builder, X, LY - U(3.f), U(22.f), FLinearColor::White, !bPlayer);
		Text(FString::Printf(TEXT("%d Builder%s at its walls (each beyond the first: +50%%, up to %d)"), St->BuildersAt, St->BuildersAt == 1 ? TEXT("") : TEXT("s"), VLBuild::PerBuilding),
			X + U(27.f), LY, U(14.f), Parchment);
	}
	else
	{
		Text(bPlayer ? TEXT("No Builder at work: select Builders and right-click it") : TEXT("No Builder at work"), X, LY, U(14.f), Refuse);
	}
	Text(FString::Printf(TEXT("Health %d / %d: it rises with the walls"), FMath::CeilToInt(St->Health), FMath::RoundToInt(St->MaxHealth)), X, LY + U(22.f), U(13.f), Dim);
	if (!bPlayer)
	{
		return true;
	}
	// ---- Cancel: three quarters of its price back
	const float RW = U(190.f);
	const FBox2D R(FVector2D(Box.Max.X - U(16.f) - RW, Box.Min.Y + U(16.f)), FVector2D(Box.Max.X - U(16.f), Box.Max.Y - U(16.f)));
	const FVLCost Back = C->RefundFor(Building);
	const FBtn B = Button(R, VLId::SiteCancel);
	ButtonFrame(R, B, true);
	const float Lift = B.bHeld ? U(1.f) : 0.f;
	Icon(EVLIcon::Cancel, R.Min.X + U(9.f), R.Min.Y + U(12.f) + Lift, U(44.f));
	const float TX = R.Min.X + U(62.f);
	Text(TEXT("Cancel"), TX, R.Min.Y + U(30.f) + Lift, U(14.f), Parchment, AlignLeft, Bold);
	KeyCap(TEXT("Del"), R.Max.X - U(6.f), R.Min.Y + U(6.f), true);
	Icon(EVLIcon::Coin, TX, R.Min.Y + U(53.f) + Lift, U(17.f));
	Text(FString::Printf(TEXT("+%d"), Back.Gold), TX + U(21.f), R.Min.Y + U(52.f) + Lift, U(16.f), GoldBright, AlignLeft, Bold);
	Text(FString::Printf(TEXT("%d%% of its price back"), FMath::RoundToInt(VLBuild::CancelRefund * 100.f)), R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), Dim);
	if (B.bHover)
	{
		SetTooltip(R, TEXT("Cancel the site   [Delete]"), { FString::Printf(TEXT("Its walls come down and %s comes back (%d%% of its price)."), *CostLine(Back), FMath::RoundToInt(VLBuild::CancelRefund * 100.f)) });
	}
	if (B.bClicked)
	{
		Click();
		C->CancelSite(Building);
	}
	return true;
}

float AVLHUD::DrawDemolishTab(const FBox2D& Box, AActor* Building)
{
	// the main game's Demolish tab on the panel's top edge: a finished building of yours (not the castle); the first
	// press asks and shows what comes back, the second (within 3 s) pulls it down
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* C = UVLConstruction::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	if (!St || !C || !St->IsAlive() || St->IsSite() || St->Team != UVLBattle::Player || St->Kind == EVLBuilding::Castle)
	{
		return Box.Max.X - U(16.f);
	}
	const bool bAsked = C->IsDemolishAsked(Building);
	const FVLCost Back = C->RefundFor(Building);
	const FString Label = bAsked ? FString::Printf(TEXT("Again: +%d gold"), Back.Gold) : FString(TEXT("Demolish"));
	const float W = TextSize(Label, U(13.f), Bold).X + U(46.f), H = U(28.f);
	const FBox2D Tab(FVector2D(Box.Max.X - U(16.f) - W, Box.Min.Y - H + U(2.f)), FVector2D(Box.Max.X - U(16.f), Box.Min.Y + U(2.f)));
	Block(Tab);
	const FBtn B = Button(Tab, VLId::Demolish);
	Fill(Tab.Min.X, Tab.Min.Y, W, H, A(bAsked ? Refuse : Bronze, 0.95f));
	Fill(Tab.Min.X + U(1.f), Tab.Min.Y + U(1.f), W - U(2.f), H - U(1.f), A(B.bHover ? ButtonHot : PanelFill, 0.97f));
	Icon(EVLIcon::Disband, Tab.Min.X + U(8.f), Tab.Min.Y + (H - U(18.f)) * 0.5f, U(18.f));
	TextIn(FBox2D(Tab.Min + FVector2D(U(32.f), 0.f), Tab.Max), Label, U(13.f), bAsked ? GoldBright : Parchment, AlignLeft, Bold);
	if (B.bHover)
	{
		SetTooltip(Tab, TEXT("Demolish   [Delete, twice]"), { FString::Printf(TEXT("Pull it down: %s back (%d%% of its price and its levels; its training queue in full)."),
			*CostLine(Back), FMath::RoundToInt(VLBuild::DemolishRefund * 100.f)), TEXT("Click again within 3 s to confirm.") });
	}
	if (B.bClicked)
	{
		Click();
		C->AskDemolish(Building);
	}
	return Tab.Min.X - U(6.f);
}

void AVLHUD::DrawRotateTab(const FBox2D& Box, AActor* Building, float RightX)
{
	// beside the Demolish tab: a finished building of yours (not the castle) turns a quarter turn clockwise where it
	// stands (UVLConstruction::Rotate), if it fits that way; a mine and the map's own buildings say why not
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* C = UVLConstruction::Get(this);
	const FVLBuildingState* St = Battle ? Battle->FindBuilding(Building) : nullptr;
	if (!St || !C || !St->IsAlive() || St->IsSite() || St->Team != UVLBattle::Player || St->Kind == EVLBuilding::Castle)
	{
		return;
	}
	const FString Why = C->RotateRefusalCached(Building);
	const bool bEnabled = Why.IsEmpty();
	const FString Label(TEXT("Rotate"));
	const float KW = U(24.f);
	const float W = TextSize(Label, U(13.f), Bold).X + U(46.f) + KW, H = U(28.f);
	const FBox2D Tab(FVector2D(RightX - W, Box.Min.Y - H + U(2.f)), FVector2D(RightX, Box.Min.Y + U(2.f)));
	Block(Tab);
	const FBtn B = Button(Tab, VLId::Rotate);
	Fill(Tab.Min.X, Tab.Min.Y, W, H, A(Bronze, 0.95f));
	Fill(Tab.Min.X + U(1.f), Tab.Min.Y + U(1.f), W - U(2.f), H - U(1.f), A(B.bHover && bEnabled ? ButtonHot : PanelFill, 0.97f));
	Icon(EVLIcon::Patrol, Tab.Min.X + U(8.f), Tab.Min.Y + (H - U(18.f)) * 0.5f, U(18.f));
	TextIn(FBox2D(Tab.Min + FVector2D(U(32.f), 0.f), Tab.Max), Label, U(13.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
	KeyCap(TEXT("T"), Tab.Max.X - U(5.f), Tab.Min.Y + U(5.f), bEnabled);
	if (B.bHover)
	{
		TArray<FString> Lines;
		Lines.Add(TEXT("Turn it a quarter turn clockwise where it stands: its gate and yard, its props and whoever waits in it turn with it."));
		Lines.Add(TEXT("Free. It must fit the new way round, as when it was placed."));
		if (!bEnabled) { Lines.Add(Why + TEXT(".")); }
		SetTooltip(Tab, TEXT("Rotate   [T]"), Lines);
	}
	if (B.bClicked)
	{
		// (refused: UVLConstruction::Rotate says why and plays the error)
		if (C->Rotate(Building)) { Click(); }
		UE_LOG(LogVoxelLab, Log, TEXT("hud: rotate %s%s"), *St->Name, bEnabled ? TEXT("") : *(TEXT(" (") + Why + TEXT(")")));
	}
}

void AVLHUD::DrawClaimPanel(const FBox2D& Box, AActor* Mine)
{
	// A mine is never built: a free one of the map is claimed. Its panel says what it gives and what the claim costs;
	// Claim sends the selected Builders (none selected: the nearest free one), as a right click on it with Builders does
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* C = UVLConstruction::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	const VLBuild::FSpec* Spec = VLBuild::Spec(EVLBuilding::Mine);
	if (!Battle || !C || !Spec)
	{
		return;
	}
	const FVLBuildingState* St = Battle->FindBuilding(Mine);
	const bool bAbandoned = St && St->bDestroyed;
	const float X = Box.Min.X + U(18.f), Y = Box.Min.Y + U(12.f);
	Icon(EVLIcon::Mine, X, Y, U(42.f));
	Text(VLRules::Name(EVLBuilding::Mine), X + U(52.f), Y - U(2.f), U(22.f), Parchment, AlignLeft, Bold);
	Text(bAbandoned ? TEXT("Abandoned: nobody's") : TEXT("Neutral: nobody's"), X + U(52.f), Y + U(25.f), U(14.f), Dim);
	const VLRules::FLevel& Lv = VLRules::Level(EVLBuilding::Mine, 1);
	const float LY = Y + U(60.f);
	Icon(EVLIcon::Coin, X, LY, U(20.f));
	Text(FString::Printf(TEXT("+%d gold every %.0f s to whoever claims it"), FMath::RoundToInt(Lv.Yield * Battle->IncomeScale(UVLBattle::Player)), VLRules::PayoutInterval), X + U(27.f), LY, U(15.f), Parchment);
	Portrait(EVLPortrait::Builder, X, LY + U(25.f), U(22.f));
	Text(TEXT("Select Builders and right-click it, or press Claim"), X + U(27.f), LY + U(28.f), U(14.f), Dim);
	if (!Battle->IsPlaying())
	{
		return;
	}
	const FString Why = C->ClaimRefusal(Mine, UVLBattle::Player);
	const bool bEnabled = Why.IsEmpty();
	const bool bGold = Battle->GetStock(UVLBattle::Player, EVLRes::Gold) >= Spec->Cost.Gold;
	const float RW = U(190.f);
	const FBox2D R(FVector2D(Box.Max.X - U(16.f) - RW, Box.Min.Y + U(16.f)), FVector2D(Box.Max.X - U(16.f), Box.Max.Y - U(16.f)));
	FBtn B = Button(R, VLId::ClaimMine);
	if (!bEnabled) { B.Hot *= 0.3f; }
	ButtonFrame(R, B, bEnabled);
	const float Lift = B.bHeld ? U(1.f) : 0.f;
	Icon(EVLIcon::Hammer, R.Min.X + U(9.f), R.Min.Y + U(12.f) + Lift, U(44.f), bEnabled ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
	const float TX = R.Min.X + U(62.f);
	Text(TEXT("Claim"), TX, R.Min.Y + U(30.f) + Lift, U(14.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
	Icon(EVLIcon::Coin, TX, R.Min.Y + U(53.f) + Lift, U(17.f));
	Text(FString::FromInt(Spec->Cost.Gold), TX + U(21.f), R.Min.Y + U(52.f) + Lift, U(16.f), bGold ? Gold : Refuse, AlignLeft, Bold);
	Text(FString::Printf(TEXT("Builders work it: %.0f s"), Spec->Seconds), R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), Dim);
	if (B.bHover)
	{
		TArray<FString> Lines;
		Lines.Add(TEXT("Mines are not built: this one is part of the land. Builders claim it for your kingdom."));
		Lines.Add(FString::Printf(TEXT("Cost %s   ·   %.0f s with one Builder at it, faster with more (up to %d)."), *CostLine(Spec->Cost), Spec->Seconds, VLBuild::PerBuilding));
		Lines.Add(TEXT("Or: select Builders and right-click the mine. Until the claim is done it gives nothing."));
		if (!bEnabled) { Lines.Add(Why + TEXT(".")); }
		SetTooltip(R, TEXT("Claim the mine   [Builders: right-click it]"), Lines);
	}
	if (B.bClicked)
	{
		TArray<AVLKing*> Units;
		if (Command) { Command->GetSelection(Units); }
		const bool bOk = C->ClaimMine(Mine, UVLBattle::Player, Units.FilterByPredicate([](const AVLKing* U2) { return UVLBuilderWork::IsBuilder(U2); })) != nullptr;
		if (bOk) { Click(); }
		UE_LOG(LogVoxelLab, Log, TEXT("hud: claim the mine -> %s"), bOk ? TEXT("claimed") : *Why);
	}
}

void AVLHUD::DrawBuilderButton(const FBox2D& R, AActor* Castle)
{
	// the castle trains Builders (the main game's Citadel, Y): 120 gold + 80 food, 14 s, no housing but a limit by the
	// castle's level
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* C = UVLConstruction::Get(this);
	if (!Battle || !C)
	{
		return;
	}
	const VLRules::FTroop& T = VLRules::Troop(TEXT("Builder"));
	int32 Queued = 0;
	const int32 Have = C->CountBuilders(UVLBattle::Player, &Queued);
	const int32 Max = VLBuild::MaxBuilders(Battle->GetCastleLevel(UVLBattle::Player));
	const FString Why = Battle->TrainRefusal(Castle, TEXT("Builder"));
	const bool bEnabled = Why.IsEmpty();
	const bool bGold = Battle->GetStock(UVLBattle::Player, EVLRes::Gold) >= T.Cost.Gold;
	const bool bFood = Battle->GetStock(UVLBattle::Player, EVLRes::Food) >= T.Cost.Food;
	const bool bCapped = Have + Queued >= Max;
	FBtn B = Button(R, VLId::RecruitBuilder);
	if (!bEnabled) { B.Hot *= 0.3f; }
	ButtonFrame(R, B, bEnabled);
	const float Lift = B.bHeld ? U(1.f) : 0.f;
	const float PS = U(48.f);
	Portrait(EVLPortrait::Builder, R.Min.X + U(9.f), R.Min.Y + U(12.f) + Lift, PS, bEnabled ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
	const float TX = R.Min.X + U(16.f) + PS;
	Text(TEXT("Builder"), TX, R.Min.Y + U(30.f) + Lift, U(14.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
	const float CY = R.Min.Y + U(52.f) + Lift;
	Icon(EVLIcon::Coin, TX, CY + U(1.f), U(17.f));
	const float GW = Text(FString::FromInt(T.Cost.Gold), TX + U(21.f), CY, U(16.f), bGold ? Gold : Refuse, AlignLeft, Bold);
	Icon(EVLIcon::Food, TX + U(27.f) + GW, CY + U(1.f), U(17.f));
	Text(FString::FromInt(T.Cost.Food), TX + U(48.f) + GW, CY, U(16.f), bFood ? FoodColor : Refuse, AlignLeft, Bold);
	const FString Status = bCapped ? FString::Printf(TEXT("Builders %d/%d"), Have + Queued, Max) : FString::Printf(TEXT("Trains in %.0f s  ·  %d/%d"), Battle->TrainSeconds(Castle, TEXT("Builder")), Have + Queued, Max);
	Text(Status, R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), bCapped ? Amber : Dim);
	if (B.bClicked)
	{
		const int32 N = Battle->Train(Castle, (PCtrl && (PCtrl->IsInputKeyDown(EKeys::LeftShift) || PCtrl->IsInputKeyDown(EKeys::RightShift))) ? VLRules::RecruitBatch : 1, false, TEXT("Builder"));
		RecruitFlashTime = Now;
		bRecruitAccepted = N > 0;
		if (N > 0) { Click(); }
		UE_LOG(LogVoxelLab, Log, TEXT("hud: train a Builder -> %d queued%s"), N, N > 0 ? TEXT("") : *(TEXT(" (") + Why + TEXT(")")));
	}
	if (B.bHover)
	{
		TArray<FString> Lines;
		Lines.Add(TEXT("Raises buildings (only Builders build) and repairs them. Never picks a fight."));
		Lines.Add(FString::Printf(TEXT("Cost %s   ·   trains in %.0f s   ·   takes no housing"), *CostLine(T.Cost), Battle->TrainSeconds(Castle, TEXT("Builder"))));
		Lines.Add(FString::Printf(TEXT("Builders: %d of %d (raising the castle allows more)."), Have + Queued, Max));
		if (!Why.IsEmpty()) { Lines.Add(Why + TEXT(".")); }
		SetTooltip(R, TEXT("Builder"), Lines);
	}
}

// ---------------------------------------------------------------------------- the top bar's chips

float AVLHUD::TopChipsWidth() const
{
	const bool bCompact = View.X < U(1700.f);
	return bCompact ? U(118.f) + 2.f * U(96.f) : U(156.f) + 2.f * U(120.f);
}

void AVLHUD::DrawTopChips(float X, float Y, float H)
{
	// The main game's Builders and Scout counters, and the hero: a portrait chip each with its count or state. A click
	// selects them, a second within 0.35 s also looks at them.
	UVLBattle* Battle = UVLBattle::Get(this);
	UVLConstruction* C = UVLConstruction::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Battle || !C || !Command || !King)
	{
		return;
	}
	const bool bCompact = View.X < U(1700.f);
	const float Wide[3] = { bCompact ? U(118.f) : U(156.f), bCompact ? U(96.f) : U(120.f), bCompact ? U(96.f) : U(120.f) };
	auto Row = [&](float AtX) { return FBox2D(FVector2D(AtX, Y), FVector2D(AtX + U(300.f), Y + H)); };
	float CX = X;
	for (int32 i = 0; i < 3; ++i)
	{
		const FBox2D Seg(FVector2D(CX - U(8.f), Y), FVector2D(CX + Wide[i] - U(14.f), Y + H));
		TArray<AVLKing*> Who;
		FString Count, SubText;
		FLinearColor Col = Parchment;
		FString Title;
		TArray<FString> Lines;
		EVLPortrait Face = EVLPortrait::King;
		float Bar = -1.f;
		bool bLocked = false;
		if (i == 0)
		{
			// the hero: his health, or how long until he rises again at the castle
			Title = TEXT("King David");
			AVLKing* Hero = PlayersKing(GetWorld());
			if (Hero && Hero->IsAlive())
			{
				Who.Add(Hero);
				Bar = Hero->GetHealthFrac();
				Count = FString::Printf(TEXT("%d"), FMath::CeilToInt(Hero->GetHealth()));
				Col = Bar < 0.34f ? Refuse : Parchment;
				Lines.Add(FString::Printf(TEXT("Your hero: %.0f / %.0f health."), Hero->GetHealth(), Hero->MaxHealth));
			}
			else if (Hero)
			{
				const float Left = FMath::Max(0.f, VLRules::KingRespawnSeconds - Hero->DeadFor());
				Count = Battle->GetCastle(UVLBattle::Player) ? FString::Printf(TEXT("back in %s"), *Countdown(Left)) : FString(TEXT("fallen"));
				Col = Refuse;
				Lines.Add(Battle->GetCastle(UVLBattle::Player) ? FString::Printf(TEXT("Fallen: he rises again at the castle in %s."), *Countdown(Left)) : FString(TEXT("Fallen, and his castle with him.")));
			}
			else
			{
				Count = TEXT("-");
				Col = Dim;
			}
			Lines.Add(TEXT("Click: select him   ·   twice: look at him."));
		}
		else if (i == 1)
		{
			// the Builders: alive (+ in training) against the castle's limit
			Title = TEXT("Builders");
			Face = EVLPortrait::Builder;
			int32 Queued = 0;
			C->GetBuilders(UVLBattle::Player, Who);
			C->CountBuilders(UVLBattle::Player, &Queued);
			const int32 Max = VLBuild::MaxBuilders(Battle->GetCastleLevel(UVLBattle::Player));
			Count = FString::Printf(TEXT("%d/%d"), Who.Num(), Max);
			SubText = Queued > 0 ? FString::Printf(TEXT("+%d"), Queued) : FString();
			Col = Who.Num() == 0 ? Dim : (Who.Num() + Queued >= Max ? Amber : Parchment);
			int32 Busy = 0;
			for (AVLKing* U2 : Who)
			{
				Busy += UVLBuilderWork::IsAtWork(U2) ? 1 : 0;
			}
			Lines.Add(FString::Printf(TEXT("Builders / most you may have (%d; raising the castle allows more). %d at work."), Max, Busy));
			Lines.Add(TEXT("Only Builders build: they raise buildings (B) and repair them (X)."));
			Lines.Add(FString::Printf(TEXT("Trained at the castle: %s. They take no housing."), *CostLine(VLRules::Troop(TEXT("Builder")).Cost)));
			Lines.Add(TEXT("Click: select them   ·   twice: look at them."));
		}
		else
		{
			// the Spy: in the field / in training against the one a kingdom may have, the wait before the next, or locked
			Title = TEXT("Spy");
			Face = EVLPortrait::Spy;
			int32 Queued = 0;
			const int32 Alive = Battle->GetSpyCount(UVLBattle::Player, &Queued);
			bLocked = Battle->GetCastleLevel(UVLBattle::Player) < VLRules::SpyCastleLevel;
			const float Wait = Battle->GetSpyCooldown(UVLBattle::Player);
			for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
			{
				if (It->IsAlive() && It->Team == UVLBattle::Player && It->GetKind() == TEXT("Spy"))
				{
					Who.Add(*It);
				}
			}
			Count = FString::Printf(TEXT("%d/%d"), Alive, VLRules::MaxSpies);
			SubText = Queued > 0 ? FString::Printf(TEXT("+%d"), Queued) : (!bLocked && Wait > 0.f && Alive == 0 ? Countdown(Wait) : FString());
			Col = bLocked || Alive == 0 ? Dim : Parchment;
			if (bLocked) { Lines.Add(FString::Printf(TEXT("Locked: raise the castle to level %d to train one."), VLRules::SpyCastleLevel)); }
			else
			{
				Lines.Add(Alive > 0 ? TEXT("Your Spy is in the field. Click to select it, twice to look at it.") : (Queued > 0 ? TEXT("Your Spy is in training.") : TEXT("No Spy in the field.")));
				if (Wait > 0.f) { Lines.Add(FString::Printf(TEXT("The next can be trained in %s."), *Countdown(Wait))); }
			}
			Lines.Add(TEXT("Trained at the castle: one at a time. Fast, sees far, hard to notice."));
		}
		const FBtn B = Button(Seg, VLId::TopChip + i);
		if (B.Hot > 0.f && Who.Num() > 0) { Fill(Seg.Min.X, Seg.Min.Y + U(6.f), Seg.Max.X - Seg.Min.X, H - U(12.f), A(ButtonHot, 0.5f * B.Hot)); }
		const float PS = U(34.f);
		Portrait(Face, CX, Y + (H - PS) * 0.5f, PS, bLocked ? FLinearColor(0.45f, 0.45f, 0.5f, 0.85f) : (Who.Num() == 0 && i == 0 ? FLinearColor(1.f, 0.55f, 0.5f, 0.85f) : FLinearColor::White));
		const float TX = CX + PS + U(6.f);
		if (Bar >= 0.f)
		{
			// the hero's health: a short bar under his number
			TextIn(FBox2D(FVector2D(TX, Y), FVector2D(TX + U(300.f), Y + H - U(10.f))), Count, U(19.f), Col, AlignLeft, Bold);
			Meter(TX, Y + H - U(17.f), Wide[i] - PS - U(30.f), U(5.f), Bar, Health(Bar));
		}
		else
		{
			const float CW = TextIn(Row(TX), Count, Count.Len() > 5 ? U(15.f) : U(21.f), Col, AlignLeft, Bold);
			if (!SubText.IsEmpty()) { TextIn(Row(TX + CW + U(5.f)), SubText, U(14.f), Dim, AlignLeft); }
		}
		if (B.bHover) { SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), Title, Lines); }
		if (B.bClicked)
		{
			const bool bDouble = LastChip == i && Now - LastChipTime < 0.35;
			LastChip = i;
			LastChipTime = Now;
			Click(Who.Num() == 0);
			if (Who.Num() > 0 && !King->IsHeroMode())
			{
				King->SelectByName(i == 0 ? FString(TEXT("king")) : Who[0]->GetDisplayName());
				Command->Select(Who);
				if (bDouble)
				{
					FVector Mid = FVector::ZeroVector;
					for (const AVLKing* U2 : Who) { Mid += U2->GetFeet() / Who.Num(); }
					King->LookAt(Mid, -1.f, 1e31f);
				}
				UE_LOG(LogVoxelLab, Log, TEXT("hud: top bar %s: %d selected%s"), *Title, Who.Num(), bDouble ? TEXT(", looking at them") : TEXT(""));
			}
		}
		CX += Wide[i];
		Fill(CX - U(12.f), Y + U(11.f), FMath::Max(1.f, U(1.f)), H - U(22.f), A(Bronze, 0.9f));
	}
}
