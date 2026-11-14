// Copyright Sovereign Realms.

#include "Player/SRHUD.h"
#include "Player/SRPlayerController.h"
#include "Units/SRUnit.h"
#include "Buildings/SRBuilding.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Engine/Canvas.h"
#include "Engine/World.h"

float ASRHUD::UIScale() const
{
	// Authored at 1080p; never shrink below 1 so thin lines stay visible in small PIE windows.
	return FMath::Max(1.f, Canvas ? Canvas->SizeY / 1080.f : 1.f) * USRFeelSettings::Get().HUDScale;
}

void ASRHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas) { return; }
	const FLayout L = ComputeLayout(FVector2D(Canvas->SizeX, Canvas->SizeY));
	DrawHealthBars();
	DrawTrainingBars(L);
	DrawPayoutPopups(L);
	DrawSelectionBox();
	DrawStatusText();
	DrawResourceBar(L);
	DrawBuildingPanel(L);
}

void ASRHUD::DrawSelectionBox()
{
	const ASRPlayerController* PC = Cast<ASRPlayerController>(PlayerOwner);
	if (!PC || !PC->IsBoxSelecting()) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	const FVector2D A = PC->GetBoxStart(), B = PC->GetBoxEnd();
	const float X0 = FMath::Min(A.X, B.X), Y0 = FMath::Min(A.Y, B.Y);
	const float X1 = FMath::Max(A.X, B.X), Y1 = FMath::Max(A.Y, B.Y);

	DrawRect(F.BoxFillColor, X0, Y0, X1 - X0, Y1 - Y0);
	const float Thickness = 1.5f * UIScale();
	DrawLine(X0, Y0, X1, Y0, F.BoxLineColor, Thickness);
	DrawLine(X1, Y0, X1, Y1, F.BoxLineColor, Thickness);
	DrawLine(X1, Y1, X0, Y1, F.BoxLineColor, Thickness);
	DrawLine(X0, Y1, X0, Y0, F.BoxLineColor, Thickness);
}

void ASRHUD::DrawHealthBars()
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	const double Now = GetWorld()->GetTimeSeconds();

	for (const ASRUnit* Unit : Battle->GetUnits())
	{
		if (!Unit || !Unit->IsActive()) { continue; }

		// Only when it matters: selected, or hurt recently. Keeps the battlefield clean.
		const bool bRecentlyHurt = Unit->GetHealthFrac() < 1.f && (Now - Unit->GetLastDamagedTime()) < F.HealthBarLingerTime;
		if (!Unit->IsSelected() && !bRecentlyHurt) { continue; }

		const FVector Screen = Canvas->Project(Unit->GetOverheadPoint());
		if (Screen.Z <= 0.f) { continue; }

		const float UI = UIScale();
		const float W = F.HealthBarSize.X * UI, H = F.HealthBarSize.Y * UI;
		const float X = FMath::RoundToFloat(Screen.X - W * 0.5f), Y = FMath::RoundToFloat(Screen.Y - H);
		const float Frac = Unit->GetHealthFrac();

		// Green -> amber -> red as health drops; enemies get a red-tinted frame so sides read at a glance.
		const FLinearColor Fill = Frac > 0.5f
			? FMath::Lerp(FLinearColor(0.95f, 0.75f, 0.1f), FLinearColor(0.2f, 0.9f, 0.25f), (Frac - 0.5f) * 2.f)
			: FMath::Lerp(FLinearColor(0.9f, 0.12f, 0.08f), FLinearColor(0.95f, 0.75f, 0.1f), Frac * 2.f);
		const FLinearColor Frame = Unit->GetTeam() == ESRTeam::Enemy ? FLinearColor(0.25f, 0.02f, 0.02f, 0.9f) : FLinearColor(0.02f, 0.03f, 0.06f, 0.9f);

		DrawRect(Frame, X - UI, Y - UI, W + 2.f * UI, H + 2.f * UI);
		DrawRect(FLinearColor(0.12f, 0.12f, 0.12f, 0.9f), X, Y, W, H);
		DrawRect(Fill, X, Y, W * Frac, H);
	}
}

void ASRHUD::DrawStatusText()
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const ASRPlayerController* PC = Cast<ASRPlayerController>(PlayerOwner);
	if (!Battle || !PC) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	const float UI = UIScale();

	if (F.bShowControlsHint)
	{
		const FLinearColor Dim(0.9f, 0.88f, 0.8f, 0.75f);
		DrawText(TEXT("LMB select (shift add, drag box, double-click type)   RMB move / attack   A+LMB attack-move   S stop"), Dim, 14.f * UI, 12.f * UI, nullptr, UI);
		DrawText(TEXT("WASD / arrows / edge / MMB-drag pan   wheel zoom   Space centre   Ctrl+1-3 groups   R reset"), Dim, 14.f * UI, 28.f * UI, nullptr, UI);
		DrawText(TEXT("LMB building: select   Citadel selected: Q Shieldbearer, E Archer, RMB rally point"), Dim, 14.f * UI, 44.f * UI, nullptr, UI);
	}

	if (PC->IsAttackMoveArmed())
	{
		DrawText(TEXT("ATTACK-MOVE: click a destination or an enemy (right-click cancels)"), FLinearColor(1.f, 0.45f, 0.3f), 14.f * UI, 66.f * UI, nullptr, 1.2f * UI);
	}

	if (Battle->GetResult() != ESRBattleResult::Ongoing)
	{
		const bool bWon = Battle->GetResult() == ESRBattleResult::PlayerWon;
		const FString Text = bWon ? TEXT("VICTORY") : TEXT("DEFEAT");
		// Slides in over a third of a second.
		const float In = FMath::Clamp(Battle->GetTimeSinceResult() / 0.35f, 0.f, 1.f);
		const float Scale = 3.f * UI;
		float TextW = 0.f, TextH = 0.f;
		GetTextSize(Text, TextW, TextH, nullptr, Scale);
		const float X = (Canvas->SizeX - TextW) * 0.5f;
		const float Y = Canvas->SizeY * 0.16f - (1.f - In) * 30.f * UI;
		DrawText(Text, FLinearColor(0.f, 0.f, 0.f, 0.6f * In), X + 2.f * UI, Y + 2.f * UI, nullptr, Scale);
		DrawText(Text, (bWon ? FLinearColor(1.f, 0.85f, 0.35f) : FLinearColor(0.9f, 0.25f, 0.2f)).CopyWithNewOpacity(In), X, Y, nullptr, Scale);

		const FString Sub = TEXT("Press R to fight again");
		GetTextSize(Sub, TextW, TextH, nullptr, 1.2f * UI);
		DrawText(Sub, FLinearColor(1.f, 1.f, 1.f, 0.85f * In), (Canvas->SizeX - TextW) * 0.5f, Y + 52.f * UI, nullptr, 1.2f * UI);
	}
}

// ============================================================================ kingdom interface
// Dark blue / charcoal panels with restrained bronze and gold trim (PLAN.md, "Camera and interface"). Everything is
// drawn in whole UI pixels; the icons are small pixel maps, so they stay crisp at any scale.

namespace
{
	const FLinearColor PanelFill(0.030f, 0.043f, 0.075f, 0.93f);
	const FLinearColor PanelInner(0.055f, 0.075f, 0.120f, 0.93f);
	const FLinearColor Bronze(0.36f, 0.25f, 0.10f, 1.f);
	const FLinearColor Gold(0.86f, 0.66f, 0.26f, 1.f);
	const FLinearColor GoldBright(1.f, 0.86f, 0.45f, 1.f);
	const FLinearColor Parchment(0.93f, 0.89f, 0.78f, 1.f);
	const FLinearColor Dim(0.62f, 0.62f, 0.60f, 1.f);
	const FLinearColor Refuse(1.f, 0.24f, 0.16f, 1.f);
	const FLinearColor FoodColor(0.93f, 0.80f, 0.36f, 1.f);

	// Pixel maps. Letters index IconColor() below; '.' is empty; 'T' takes the team colour.
	const TCHAR* const CoinIcon[] = {
		TEXT("...oooo..."), TEXT(".ooWWYYoo."), TEXT(".oWYYYYdo."), TEXT("oWYYddYYdo"), TEXT("oWYdYYdYdo"),
		TEXT("oYYdYYdYdo"), TEXT("oYYYddYYdo"), TEXT(".oYYYYddo."), TEXT(".ooddddoo."), TEXT("...oooo...") };
	const TCHAR* const WheatIcon[] = {
		TEXT("....gG...."), TEXT("...gGGg..."), TEXT("..GgGGgG.."), TEXT("...GGGG..."), TEXT("..GgGGgG.."),
		TEXT("...GGGG..."), TEXT("..GgGGgG.."), TEXT("....sG...."), TEXT("....s....."), TEXT("....s.....") };
	const TCHAR* const ShieldIcon[] = {
		TEXT("...bbbb..."), TEXT(".bbBBBBbb."), TEXT(".bBBTTBBb."), TEXT("bBBTTTTBBb"), TEXT("bBTTWWTTBb"),
		TEXT("bBTTWWTTBb"), TEXT("bBBTTTTBBb"), TEXT(".bBBTTBBb."), TEXT(".bbBBBBbb."), TEXT("...bbbb...") };
	const TCHAR* const BowIcon[] = {
		TEXT("..wwww...."), TEXT(".w....c..."), TEXT("w......c.."), TEXT("w.......c."), TEXT("wTTccccccB"),
		TEXT("w.......c."), TEXT("w......c.."), TEXT(".w....c..."), TEXT("..wwww...."), TEXT("..........") };

	FLinearColor IconColor(TCHAR C, const FLinearColor& Team)
	{
		switch (C)
		{
		case 'o': return FLinearColor(0.30f, 0.19f, 0.04f);
		case 'd': return FLinearColor(0.62f, 0.42f, 0.09f);
		case 'Y': return FLinearColor(0.95f, 0.72f, 0.20f);
		case 'W': return FLinearColor(1.f, 0.95f, 0.66f);
		case 'G': return FLinearColor(0.95f, 0.80f, 0.36f);
		case 'g': return FLinearColor(0.70f, 0.52f, 0.14f);
		case 's': return FLinearColor(0.40f, 0.30f, 0.10f);
		case 'b': return FLinearColor(0.24f, 0.15f, 0.05f);
		case 'B': return FLinearColor(0.66f, 0.46f, 0.18f);
		case 'w': return FLinearColor(0.50f, 0.33f, 0.18f);
		case 'c': return FLinearColor(0.90f, 0.85f, 0.70f);
		case 'T': return FLinearColor(FMath::Min(Team.R * 1.6f + 0.05f, 1.f), FMath::Min(Team.G * 1.6f + 0.05f, 1.f), FMath::Min(Team.B * 1.6f + 0.05f, 1.f));
		default: return FLinearColor::White;
		}
	}

	float Px(float V) { return FMath::RoundToFloat(V); }
}

FVector2D ASRHUD::ViewSize() const
{
	int32 X = 0, Y = 0;
	if (PlayerOwner) { PlayerOwner->GetViewportSize(X, Y); }
	return FVector2D(X, Y);
}

ASRHUD::FLayout ASRHUD::ComputeLayout(const FVector2D& View) const
{
	FLayout L;
	L.UI = FMath::Max(1.f, View.Y / 1080.f) * USRFeelSettings::Get().HUDScale;
	const float UI = L.UI;

	// resource readout: top centre
	const FVector2D ResSize(332.f * UI, 46.f * UI);
	const FVector2D ResMin(Px((View.X - ResSize.X) * 0.5f), Px(10.f * UI));
	L.Resources = FBox2D(ResMin, ResMin + ResSize);

	// building panel: bottom centre, only with a building selected
	const ASRPlayerController* PC = Cast<ASRPlayerController>(PlayerOwner);
	const ASRBuilding* Building = PC ? PC->GetSelectedBuilding() : nullptr;
	if (Building)
	{
		L.bBuildingPanel = true;
		L.bButtons = Building->IsCastle() && Building->Team == ESRTeam::Player;
		const FVector2D Size((L.bButtons ? 760.f : 440.f) * UI, 112.f * UI);
		const FVector2D Min(Px((View.X - Size.X) * 0.5f), Px(View.Y - Size.Y - 18.f * UI));
		L.Panel = FBox2D(Min, Min + Size);
		if (L.bButtons)
		{
			const FVector2D ButtonSize(176.f * UI, 80.f * UI);
			for (int32 i = 0; i < 2; ++i)
			{
				const FVector2D BMin(Px(L.Panel.Max.X - 16.f * UI - (2 - i) * ButtonSize.X - (1 - i) * 10.f * UI), Px(Min.Y + 16.f * UI));
				L.Buttons[i] = FBox2D(BMin, BMin + ButtonSize);
			}
		}
	}
	return L;
}

int32 ASRHUD::RecruitButtonAt(const FVector2D& Pixels) const
{
	const FLayout L = ComputeLayout(ViewSize());
	if (!L.bButtons) { return -1; }
	for (int32 i = 0; i < 2; ++i)
	{
		if (L.Buttons[i].IsInside(Pixels)) { return i; }
	}
	return -1;
}

bool ASRHUD::IsOverPanel(const FVector2D& Pixels) const
{
	const FLayout L = ComputeLayout(ViewSize());
	return L.Resources.IsInside(Pixels) || (L.bBuildingPanel && L.Panel.IsInside(Pixels));
}

void ASRHUD::Panel(const FBox2D& Box, float UI, float Alpha)
{
	const float X = Box.Min.X, Y = Box.Min.Y, W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float B = Px(2.f * UI), I = Px(1.f * UI);
	auto A = [Alpha](FLinearColor C) { C.A *= Alpha; return C; };
	DrawRect(A(FLinearColor(0.f, 0.f, 0.f, 0.45f)), X + B, Y + B * 2.f, W, H);             // drop shadow
	DrawRect(A(Bronze), X, Y, W, H);
	DrawRect(A(PanelFill), X + B, Y + B, W - 2.f * B, H - 2.f * B);
	DrawRect(A(PanelInner), X + B, Y + B, W - 2.f * B, Px(H * 0.42f));                      // a lighter upper half: a slight sheen
	// one thin gold rule inside the bronze, broken at the corners by studs
	const float G = B + I;
	DrawRect(A(Gold), X + G + 4.f * UI, Y + G, W - 2.f * G - 8.f * UI, I);
	DrawRect(A(Gold.CopyWithNewOpacity(0.55f)), X + G + 4.f * UI, Y + H - G - I, W - 2.f * G - 8.f * UI, I);
	DrawRect(A(Gold.CopyWithNewOpacity(0.55f)), X + G, Y + G + 4.f * UI, I, H - 2.f * G - 8.f * UI);
	DrawRect(A(Gold.CopyWithNewOpacity(0.55f)), X + W - G - I, Y + G + 4.f * UI, I, H - 2.f * G - 8.f * UI);
	const float S = Px(3.f * UI);
	for (int32 c = 0; c < 4; ++c)
	{
		DrawRect(A(GoldBright), (c & 1) ? X + W - B - S : X + B, (c & 2) ? Y + H - B - S : Y + B, S, S);
	}
}

void ASRHUD::Icon(const TCHAR* const* Rows, int32 NumRows, float X, float Y, float Pixel, const FLinearColor& Team, float Alpha, bool bGrey)
{
	Pixel = FMath::Max(1.f, Px(Pixel));
	for (int32 j = 0; j < NumRows; ++j)
	{
		const TCHAR* Row = Rows[j];
		for (int32 i = 0; Row[i]; ++i)
		{
			if (Row[i] == '.') { continue; }
			FLinearColor C = IconColor(Row[i], Team);
			if (bGrey)
			{
				const float Lum = C.R * 0.3f + C.G * 0.59f + C.B * 0.11f;
				C = FLinearColor(Lum * 0.55f, Lum * 0.57f, Lum * 0.62f);
			}
			C.A = Alpha;
			DrawRect(C, X + i * Pixel, Y + j * Pixel, Pixel, Pixel);
		}
	}
}

void ASRHUD::Label(const FString& Text, float X, float Y, float Scale, const FLinearColor& Color, bool bShadow)
{
	if (bShadow) { DrawText(Text, FLinearColor(0.f, 0.f, 0.f, 0.7f * Color.A), Px(X) + FMath::Max(1.f, Px(Scale)), Px(Y) + FMath::Max(1.f, Px(Scale)), nullptr, Scale); }
	DrawText(Text, Color, Px(X), Px(Y), nullptr, Scale);
}

float ASRHUD::LabelWidth(const FString& Text, float Scale)
{
	float W = 0.f, H = 0.f;
	GetTextSize(Text, W, H, nullptr, Scale);
	return W;
}

void ASRHUD::Bar(float X, float Y, float W, float H, float Frac, const FLinearColor& Fill, float UI)
{
	const float B = FMath::Max(1.f, Px(UI));
	DrawRect(Bronze, X - B, Y - B, W + 2.f * B, H + 2.f * B);
	DrawRect(FLinearColor(0.02f, 0.025f, 0.04f, 1.f), X, Y, W, H);
	DrawRect(Fill, X, Y, Px(W * FMath::Clamp(Frac, 0.f, 1.f)), H);
	DrawRect(FLinearColor(1.f, 1.f, 1.f, 0.22f), X, Y, Px(W * FMath::Clamp(Frac, 0.f, 1.f)), FMath::Max(1.f, Px(H * 0.3f)));
}

void ASRHUD::DrawResourceBar(const FLayout& L)
{
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const float UI = L.UI;
	Panel(L.Resources, UI);

	const float CellW = (L.Resources.Max.X - L.Resources.Min.X) * 0.5f;
	const double Now = GetWorld()->GetRealTimeSeconds();
	for (int32 i = 0; i < 2; ++i)
	{
		const ESRResource Resource = i == 0 ? ESRResource::Gold : ESRResource::Food;
		const float Flash = Economy->GetInsufficientFlash(Resource);
		const float Pulse = Economy->GetIncomePulse(Resource);
		// Refused purchase: the counter that fell short shakes and burns red.
		const float Shake = Flash > 0.f ? FMath::Sin(float(Now) * 62.f) * 5.f * UI * Flash : 0.f;
		const float X = L.Resources.Min.X + CellW * i + 16.f * UI + Shake;
		const float Y = L.Resources.Min.Y + 9.f * UI;
		if (i == 1) { DrawRect(Bronze, Px(L.Resources.Min.X + CellW), L.Resources.Min.Y + 8.f * UI, FMath::Max(1.f, Px(UI)), 30.f * UI); }

		const float IconPx = Px(2.f * UI) + (Pulse > 0.5f ? 1.f : 0.f);       // a one-pixel swell when income lands
		Icon(i == 0 ? CoinIcon : WheatIcon, 10, Px(X), Px(Y + 4.f * UI - (IconPx - Px(2.f * UI)) * 5.f), IconPx, FLinearColor::White);

		const FLinearColor Base = i == 0 ? GoldBright : FoodColor;
		const FLinearColor Color = FMath::Lerp(FMath::Lerp(Parchment, Base, 0.35f + 0.65f * Pulse), Refuse, FMath::Clamp(Flash * 1.4f, 0.f, 1.f));
		const FString Amount = FString::FromInt(Economy->GetResource(ESRTeam::Player, Resource));
		Label(Amount, X + 30.f * UI, Y - 1.f * UI, 1.75f * UI, Color);
		const float AmountW = LabelWidth(Amount, 1.75f * UI);
		const FString Rate = FString::Printf(TEXT("+%.0f/min"), Economy->GetIncomePerMinute(ESRTeam::Player, Resource));
		Label(Rate, X + 38.f * UI + AmountW, Y + 9.f * UI, 0.95f * UI, Dim.CopyWithNewOpacity(0.9f), false);
	}
}

void ASRHUD::DrawBuildingPanel(const FLayout& L)
{
	const ASRPlayerController* PC = Cast<ASRPlayerController>(PlayerOwner);
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	const ASRBuilding* Building = PC ? PC->GetSelectedBuilding() : nullptr;
	if (!L.bBuildingPanel || !Building || !Economy) { return; }

	const USRFeelSettings& F = USRFeelSettings::Get();
	const float UI = L.UI;
	const FLinearColor TeamCol = Building->Team == ESRTeam::Player ? F.PlayerTeamColor : F.EnemyTeamColor;
	Panel(L.Panel, UI);

	const float X = L.Panel.Min.X + 20.f * UI, Y = L.Panel.Min.Y + 13.f * UI;
	// team pennon, name, allegiance
	DrawRect(IconColor('T', TeamCol), Px(X), Px(Y + 3.f * UI), Px(6.f * UI), Px(20.f * UI));
	DrawRect(Gold, Px(X), Px(Y + 3.f * UI), Px(6.f * UI), FMath::Max(1.f, Px(2.f * UI)));
	const FString Name = Building->GetDisplayName();
	Label(Name, X + 14.f * UI, Y, 1.7f * UI, GoldBright);
	Label(Building->Team == ESRTeam::Player ? TEXT("your kingdom") : TEXT("enemy"), X + 22.f * UI + LabelWidth(Name, 1.7f * UI), Y + 9.f * UI, 1.f * UI,
		Building->Team == ESRTeam::Player ? Dim : Refuse, false);

	const float Line2 = Y + 36.f * UI, Line3 = Y + 62.f * UI;
	if (Building->BuildingType == ESRBuildingType::Farm || Building->BuildingType == ESRBuildingType::Mine)
	{
		const bool bFarm = Building->BuildingType == ESRBuildingType::Farm;
		Icon(bFarm ? WheatIcon : CoinIcon, 10, Px(X), Px(Line2), 2.f * UI, TeamCol);
		Label(FString::Printf(TEXT("+%d %s every %.0f s"), bFarm ? F.FarmFoodPerPayout : F.MineGoldPerPayout, bFarm ? TEXT("food") : TEXT("gold"),
			bFarm ? F.FarmPayoutInterval : F.MinePayoutInterval), X + 30.f * UI, Line2 + 2.f * UI, 1.15f * UI, Parchment);
		Bar(Px(X), Px(Line3 + 6.f * UI), Px(L.Panel.Max.X - X - 22.f * UI), Px(9.f * UI), Building->GetPayoutFraction(), bFarm ? FoodColor : Gold, UI);
		return;
	}
	if (!L.bButtons)
	{
		Label(TEXT("Enemy stronghold."), X, Line2 + 2.f * UI, 1.15f * UI, Parchment);
		return;
	}

	// ---- the player's castle: queue on the left, recruit buttons on the right
	const TArray<ESRUnitType>& Queue = Building->GetQueue();
	if (Queue.Num() == 0)
	{
		Label(TEXT("Recruit troops for food."), X, Line2 + 2.f * UI, 1.1f * UI, Parchment);
		Label(TEXT("Right-click the ground to set the rally point."), X, Line3, 1.f * UI, Dim, false);
	}
	else
	{
		Label(TEXT("Training"), X, Line2 + 2.f * UI, 1.1f * UI, Parchment);
		float QX = X + LabelWidth(TEXT("Training"), 1.1f * UI) + 12.f * UI;
		for (int32 i = 0; i < Queue.Num(); ++i)
		{
			// the one in training is drawn full size and bright, the ones waiting smaller and dimmer
			const bool bFirst = i == 0;
			Icon(Queue[i] == ESRUnitType::Archer ? BowIcon : ShieldIcon, 10, Px(QX), Px(Line2 + (bFirst ? -1.f : 3.f) * UI), (bFirst ? 2.f : 1.6f) * UI, TeamCol, bFirst ? 1.f : 0.75f);
			QX += (bFirst ? 26.f : 20.f) * UI;
		}
		const float BarW = Px(L.Buttons[0].Min.X - X - 26.f * UI);
		Bar(Px(X), Px(Line3 + 6.f * UI), BarW, Px(9.f * UI), Building->GetBuildFraction(), GoldBright, UI);
	}

	FVector2D Mouse;
	const bool bMouse = PC->GetCursorScreenPos(Mouse);
	const double Now = GetWorld()->GetRealTimeSeconds();
	for (int32 i = 0; i < 2; ++i)
	{
		const ESRUnitType Type = i == 1 ? ESRUnitType::Archer : ESRUnitType::Shieldbearer;
		const FSRCost& Cost = F.CostFor(Type);
		const bool bGold = Economy->GetResource(ESRTeam::Player, ESRResource::Gold) >= Cost.Gold;
		const bool bFood = Economy->GetResource(ESRTeam::Player, ESRResource::Food) >= Cost.Food;
		const bool bRoom = Queue.Num() < F.MaxRecruitQueue;
		const bool bEnabled = bGold && bFood && bRoom;
		const bool bHover = bMouse && L.Buttons[i].IsInside(Mouse);
		const float Since = float(Now - PC->GetLastRecruitTime());
		const float Press = (PC->GetLastRecruitButton() == i && Since < 0.22f) ? 1.f - Since / 0.22f : 0.f;

		const FBox2D& B = L.Buttons[i];
		const float BX = B.Min.X, BY = B.Min.Y + (Press > 0.5f ? Px(UI) : 0.f), BW = B.Max.X - B.Min.X, BH = B.Max.Y - B.Min.Y;
		const float Edge = Px(2.f * UI);
		FLinearColor Border = bEnabled ? (bHover ? GoldBright : Gold) : Bronze.CopyWithNewOpacity(0.8f);
		FLinearColor Fill = bEnabled ? (bHover ? FLinearColor(0.12f, 0.16f, 0.26f, 1.f) : FLinearColor(0.075f, 0.10f, 0.17f, 1.f)) : FLinearColor(0.05f, 0.055f, 0.07f, 1.f);
		if (Press > 0.f)
		{
			const FLinearColor Hit = PC->WasLastRecruitAccepted() ? GoldBright : Refuse;
			Border = FMath::Lerp(Border, Hit, Press);
			Fill = FMath::Lerp(Fill, Hit * 0.35f, Press * 0.8f);
			Fill.A = 1.f;
		}
		DrawRect(Border, BX, BY, BW, BH);
		DrawRect(Fill, BX + Edge, BY + Edge, BW - 2.f * Edge, BH - 2.f * Edge);
		if (bEnabled) { DrawRect(FLinearColor(1.f, 1.f, 1.f, 0.05f), BX + Edge, BY + Edge, BW - 2.f * Edge, Px(BH * 0.4f)); }

		Icon(i == 1 ? BowIcon : ShieldIcon, 10, Px(BX + 12.f * UI), Px(BY + 12.f * UI), 3.f * UI, TeamCol, 1.f, !bEnabled);
		const FLinearColor Text = bEnabled ? Parchment : Dim.CopyWithNewOpacity(0.75f);
		Label(F.StatsFor(Type).DisplayName, BX + 52.f * UI, BY + 9.f * UI, 1.15f * UI, Text, bEnabled);
		// hotkey cap
		const FString Key = i == 1 ? TEXT("E") : TEXT("Q");
		const float KW = Px(17.f * UI);
		DrawRect(bEnabled ? Gold : Bronze, BX + BW - KW - 8.f * UI, BY + 8.f * UI, KW, KW);
		DrawRect(FLinearColor(0.03f, 0.04f, 0.07f, 1.f), BX + BW - KW - 8.f * UI + Px(UI), BY + 8.f * UI + Px(UI), KW - 2.f * Px(UI), KW - 2.f * Px(UI));
		Label(Key, BX + BW - KW - 8.f * UI + (KW - LabelWidth(Key, 1.f * UI)) * 0.5f, BY + 9.f * UI, 1.f * UI, bEnabled ? GoldBright : Dim, false);
		// price: the resource that falls short is red
		float CX = BX + 52.f * UI;
		const float CY = BY + 34.f * UI;
		if (Cost.Gold > 0)
		{
			Icon(CoinIcon, 10, Px(CX), Px(CY + 1.f * UI), 1.6f * UI, TeamCol, 1.f, !bGold && !bEnabled);
			CX += 20.f * UI;
			const FString GoldText = FString::FromInt(Cost.Gold);
			Label(GoldText, CX, CY, 1.15f * UI, bGold ? (bEnabled ? GoldBright : Dim) : Refuse, false);
			CX += LabelWidth(GoldText, 1.15f * UI) + 12.f * UI;
		}
		Icon(WheatIcon, 10, Px(CX), Px(CY + 1.f * UI), 1.6f * UI, TeamCol, 1.f, !bFood && !bEnabled);
		CX += 20.f * UI;
		Label(FString::FromInt(Cost.Food), CX, CY, 1.15f * UI, bFood ? (bEnabled ? FoodColor : Dim) : Refuse, false);
		Label(!bRoom ? TEXT("queue full") : FString::Printf(TEXT("%.0f s"), F.BuildTimeFor(Type)), BX + 52.f * UI, BY + 56.f * UI, 0.95f * UI, !bRoom ? Refuse : Dim.CopyWithNewOpacity(0.85f), false);
	}
}

void ASRHUD::DrawPayoutPopups(const FLayout& L)
{
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const float UI = L.UI;
	for (const FSRPayoutPopup& Popup : Economy->GetPopups())
	{
		const float T = FMath::Clamp(Popup.Age / FMath::Max(F.PayoutPopupTime, 0.05f), 0.f, 1.f);
		// rises fast, then drifts; pops in over the first tenth and fades over the last third
		const float Rise = 1.f - FMath::Square(1.f - T);
		const FVector Screen = Canvas->Project(Popup.Origin + FVector(0.f, 0.f, F.PayoutPopupRise * Rise));
		if (Screen.Z <= 0.f) { continue; }
		const float Alpha = T > 0.66f ? 1.f - (T - 0.66f) / 0.34f : 1.f;
		const float Pop = T < 0.12f ? 1.f + 0.5f * (1.f - T / 0.12f) : 1.f;
		const float Scale = 1.9f * UI * Pop;
		const FString Text = FString::Printf(TEXT("+%d"), Popup.Amount);
		const float W = LabelWidth(Text, Scale);
		const float IconPx = FMath::Max(1.f, Px(2.f * UI * Pop));
		const float Total = W + 6.f * UI + IconPx * 10.f;
		const float X = Screen.X - Total * 0.5f, Y = Screen.Y - 12.f * UI * Pop;
		const FLinearColor Color = (Popup.Resource == ESRResource::Gold ? GoldBright : FoodColor).CopyWithNewOpacity(Alpha);
		Label(Text, X, Y, Scale, Color);
		Icon(Popup.Resource == ESRResource::Gold ? CoinIcon : WheatIcon, 10, Px(X + W + 6.f * UI), Px(Y + 5.f * UI * Pop), IconPx, FLinearColor::White, Alpha);
	}
}

void ASRHUD::DrawTrainingBars(const FLayout& L)
{
	// A castle at work shows its progress over the gatehouse even when nothing is selected.
	const USREconomySubsystem* Economy = USREconomySubsystem::Get(this);
	if (!Economy) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	const float UI = L.UI;
	for (const ASRBuilding* Building : Economy->GetBuildings())
	{
		if (!Building || Building->GetQueue().Num() == 0) { continue; }
		const FVector Screen = Canvas->Project(Building->GetLabelPoint());
		if (Screen.Z <= 0.f) { continue; }
		const FLinearColor TeamCol = Building->Team == ESRTeam::Player ? F.PlayerTeamColor : F.EnemyTeamColor;
		const float W = Px(96.f * UI), H = Px(8.f * UI);
		const float X = Px(Screen.X - W * 0.5f + 12.f * UI), Y = Px(Screen.Y);
		Icon(Building->GetQueue()[0] == ESRUnitType::Archer ? BowIcon : ShieldIcon, 10, X - 26.f * UI, Y - 6.f * UI, 2.f * UI, TeamCol);
		Bar(X, Y, W, H, Building->GetBuildFraction(), GoldBright, UI);
		if (Building->GetQueue().Num() > 1)
		{
			Label(FString::Printf(TEXT("+%d"), Building->GetQueue().Num() - 1), X + W + 6.f * UI, Y - 5.f * UI, 1.f * UI, Parchment);
		}
	}
}
