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
	const USRAISubsystem* AI = USRAISubsystem::Get(this);
	if (!Economy || !Battle) { return; }

	const float W = U(930.f), H = U(54.f);
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
		const FLinearColor Color = FMath::Lerp(FMath::Lerp(Parchment, Base, 0.35f + 0.65f * Pulse), Refuse, FMath::Clamp(Flash * 1.4f, 0.f, 1.f));
		const float AW = TextIn(Row(CX + Shake + U(38.f)), FString::FromInt(Economy->GetResource(ESRTeam::Player, Resource)), U(25.f), Color, AlignLeft, Bold);
		TextIn(Row(CX + U(46.f) + AW), FString::Printf(TEXT("+%.0f/min"), Economy->GetIncomePerMinute(ESRTeam::Player, Resource)), U(15.f), Dim, AlignLeft);
		if (bInputOpen && bMouse && FBox2D(FVector2D(CX - U(8.f), Y), FVector2D(CX + U(200.f), Y + H)).IsInside(Mouse))
		{
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), i == 0 ? TEXT("Gold") : TEXT("Food"),
				{ i == 0 ? TEXT("Pays for buildings. Dug by Gold Mines.") : TEXT("Pays for troops. Grown by Farms.") });
		}
		CX += U(222.f);
		Divider(CX - U(12.f));
	}

	// population: troops alive (+ in training) against housing
	{
		const int32 Pop = Economy->GetPopulation(ESRTeam::Player), Queued = Economy->GetQueuedPopulation(ESRTeam::Player), Cap = Economy->GetPopulationCap(ESRTeam::Player);
		const float Flash = Economy->GetPopulationFlash();
		const float Shake = Flash > 0.f ? FMath::RoundToFloat(FMath::Sin(float(Now) * 62.f) * U(5.f) * Flash) : 0.f;
		Icon(ESRIcon::Pop, CX + Shake, Y + (H - U(30.f)) * 0.5f, U(30.f));
		const FLinearColor Color = FMath::Lerp(Pop + Queued >= Cap ? Amber : Parchment, Refuse, FMath::Clamp(Flash * 1.4f, 0.f, 1.f));
		const float PW = TextIn(Row(CX + Shake + U(38.f)), FString::Printf(TEXT("%d/%d"), Pop, Cap), U(23.f), Color, AlignLeft, Bold);
		if (Queued > 0) { TextIn(Row(CX + U(45.f) + PW), FString::Printf(TEXT("+%d"), Queued), U(15.f), Dim, AlignLeft); }
		if (bInputOpen && bMouse && FBox2D(FVector2D(CX - U(8.f), Y), FVector2D(CX + U(160.f), Y + H)).IsInside(Mouse))
		{
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), TEXT("Population"), { TEXT("Troops in the field / housing."), TEXT("Farms and the Citadel house troops.") });
		}
		CX += U(176.f);
		Divider(CX - U(12.f));
	}

	// match clock
	Icon(ESRIcon::Clock, CX, Y + (H - U(24.f)) * 0.5f, U(24.f));
	TextIn(Row(CX + U(31.f)), Clock(Battle->GetBattleClock()), U(21.f), Parchment, AlignLeft, Bold);
	CX += U(118.f);
	Divider(CX - U(12.f));

	// the enemy's next wave: quiet until it is close
	if (AI)
	{
		const bool bAttacking = AI->IsEnemyAttacking();
		const float In = bAttacking ? 0.f : AI->GetEnemyNextWaveIn();
		FLinearColor Color = A(Dim, 0.85f);
		if (bAttacking) { Color = A(Refuse, 0.7f + 0.3f * FMath::Sin(float(Now) * 7.f)); }
		else if (In < 20.f) { Color = Amber; }
		Icon(ESRIcon::AlertWave, CX, Y + (H - U(24.f)) * 0.5f, U(24.f), FLinearColor(1.f, 1.f, 1.f, (bAttacking || In < 60.f) ? 1.f : 0.6f));
		const FString Label = bAttacking ? FString(TEXT("Enemy attacking!")) : (In > 0.f ? FString::Printf(TEXT("Enemy ready in %s"), *Clock(In)) : FString(TEXT("Enemy watching")));
		TextIn(Row(CX + U(31.f)), Label, U(17.f), Color, AlignLeft, (bAttacking || In < 20.f) ? Bold : Regular);
		if (bInputOpen && bMouse && FBox2D(FVector2D(CX - U(8.f), Y), FVector2D(Bar.Max.X, Y + H)).IsInside(Mouse))
		{
			SetTooltip(FBox2D(FVector2D(CX, Y), FVector2D(CX, Y + H + U(4.f))), TEXT("The enemy commander"),
				{ TEXT("It attacks when it thinks it can win: keep an army,"), TEXT("towers and watch your outlying farms and mines.") });
		}
	}

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
	if (!PC->IsPlacing() || !bMouse || PC->GetPlacementReason().IsEmpty()) { return; }
	for (const FBox2D& Box : Blockers) { if (Box.IsInside(Mouse)) { return; } }
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

	if (Grid)
	{
		for (const FSRVein& Vein : Grid->GetVeins())
		{
			if (!Vein.Mine.IsValid()) { Dot(Vein.Pos, FMath::Max(3.f, U(5.f)), GoldBright, true); }
		}
	}
	for (const ASRBuilding* Building : Economy->GetBuildings())
	{
		if (!Building || !Building->IsAlive()) { continue; }
		FLinearColor Color = Building->Team == ESRTeam::Player ? TeamBlue : TeamRed;
		if (Building->IsUnderConstruction()) { Color = FMath::Lerp(Color, FLinearColor(0.1f, 0.1f, 0.1f, 1.f), 0.45f); }
		Dot(Building->GetFootprintCentre(), FMath::Max(4.f, U(Building->IsCastle() ? 13.f : 8.f)), Color, true);
		if (Building->IsCastle()) { Dot(Building->GetFootprintCentre(), FMath::Max(2.f, U(5.f)), GoldBright, false); }
	}
	const float UnitSize = FMath::Max(2.f, U(3.5f));
	for (const ASRUnit* Unit : Battle->GetUnits())
	{
		if (!Unit || !Unit->IsActive()) { continue; }
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
	const float PW = Pad * 2.f + 3.f * CardW + 2.f * Gap, PH = Pad * 2.f + TabH + Gap + CardH + U(24.f);
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
		const bool bAfford = Economy->CanAfford(ESRTeam::Player, Stats.Cost);
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
		if (B.bClicked) { PC->BeginPlacement(Type); }
		if (B.bHover)
		{
			TArray<FString> Lines;
			if (!Stats.Blurb.IsEmpty()) { Lines.Add(Stats.Blurb); }
			if (Type == ESRBuildingType::Farm) { Lines.Add(FString::Printf(TEXT("+%d food every %.0f s."), F.FarmFoodPerPayout, F.FarmPayoutInterval)); }
			else if (Type == ESRBuildingType::Mine) { Lines.Add(FString::Printf(TEXT("+%d gold every %.0f s."), F.MineGoldPerPayout, F.MinePayoutInterval)); }
			else if (Stats.bRecruits)
			{
				const FSRUnitStats& U2 = F.StatsFor(Stats.RecruitType);
				Lines.Add(FString::Printf(TEXT("%s: %d food, %.0f s each."), *U2.DisplayName, F.CostFor(Stats.RecruitType).Food, F.BuildTimeFor(Stats.RecruitType)));
			}
			else if (Stats.AttackDamage > 0.f) { Lines.Add(FString::Printf(TEXT("%.0f damage every %.1f s, reach %.0f m."), Stats.AttackDamage, Stats.AttackInterval, Stats.AttackRange / 100.f)); }
			if (Stats.PopProvided > 0) { Lines.Add(FString::Printf(TEXT("Houses %d more troops."), Stats.PopProvided)); }
			Lines.Add(FString::Printf(TEXT("Cost %d gold   ·   builds in %.0f s   ·   %.0f health"), Stats.Cost.Gold, Stats.BuildTime, Stats.MaxHealth));
			Lines.Add(Type == ESRBuildingType::Mine ? TEXT("Rule: mines must stand on a gold vein (gold marks on the map).") : TEXT("Rule: flat, free ground near your own buildings."));
			if (!bAfford) { Lines.Add(TEXT("Not enough gold.")); }
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
	int32 Count[2] = { 0, 0 }, Total = 0, Engaged = 0;
	float HealthSum = 0.f;
	bool bEnemy = false;
	const ASRUnit* First = nullptr;
	for (const TWeakObjectPtr<ASRUnit>& Unit : PC->GetSelection())
	{
		if (!Unit.IsValid() || !Unit->IsAlive()) { continue; }
		if (!First) { First = Unit.Get(); }
		bEnemy |= Unit->GetTeam() == ESRTeam::Enemy;
		++Count[Unit->GetUnitType() == ESRUnitType::Archer ? 1 : 0];
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
	const FString Sub = bEnemy ? TEXT("Enemy troops: right-click to attack")
		: (Info.bExists ? FString::Printf(TEXT("Platoon %d  ·  %s  ·  %s  ·  %s"), Platoon + 1, *USRPlatoonSubsystem::KindName(Info.Kind).ToString(),
			*USRPlatoonSubsystem::FormationName(Info.Formation).ToString(), *USRPlatoonSubsystem::StanceName(Info.Stance).ToString())
			: FString::Printf(TEXT("Stance: %s   ·   Ctrl+1-6 forms a platoon"), *USRPlatoonSubsystem::StanceName(Stance).ToString()));
	Text(Sub, X, Y + U(29.f), U(14.f), Dim);

	// who is in the selection: a portrait and a count per troop type
	float PX = X;
	for (int32 t = 0; t < 2; ++t)
	{
		if (Count[t] == 0) { continue; }
		Icon(t == 1 ? ESRIcon::PortraitArcher : ESRIcon::PortraitShield, PX, Y + U(52.f), U(46.f), FLinearColor::White, bEnemy);
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
		if (Count[1] > 0) { Key(TEXT("bow range"), F.RangeCircleColor, false); }
		Key(TEXT("sight"), F.SightCircleColor, true);
	}

	// command buttons, right-aligned
	enum ECmd { CmdAttack, CmdStop, CmdHold, CmdPatrol, CmdStance, CmdForm, CmdDisband };
	struct FCommand { ECmd Kind; ESRIcon Which; const TCHAR* Key; const TCHAR* Label; const TCHAR* Title; const TCHAR* Line; bool bActive; };
	const ESRFormationShape Shape = PC->GetSelectionFormation();
	TArray<FCommand, TInlineAllocator<8>> Commands;
	Commands.Add({ CmdAttack, ESRIcon::Swords, TEXT("A"), TEXT("Attack"), TEXT("Attack-move   [A]"), TEXT("Then click: march there, fighting what you meet."), PC->IsAttackMoveArmed() });
	Commands.Add({ CmdStop, ESRIcon::Stop, TEXT("S"), TEXT("Stop"), TEXT("Stop   [S]"), TEXT("Halt and drop the current order."), false });
	Commands.Add({ CmdHold, ESRIcon::StanceHold, TEXT("H"), TEXT("Hold"), TEXT("Hold ground   [H]"), TEXT("Stand fast: fight only what is in reach."), false });
	Commands.Add({ CmdPatrol, ESRIcon::Patrol, TEXT("P"), TEXT("Patrol"), TEXT("Patrol   [P]"), TEXT("Then click: walk between here and there, fighting what you meet, until given another order."), PC->IsPatrolArmed() });
	Commands.Add({ CmdStance, StanceIcon(Stance), TEXT("G"), TEXT("Stance"), TEXT("Stance   [G]"), TEXT("Aggressive > Defensive > Hold Ground."), false });
	Commands.Add({ CmdForm, FormationIcon(Shape), TEXT("F"), TEXT("Form"), TEXT("Formation   [F]"), TEXT("Line > Column > Wedge > Square. They re-form where they stand."), false });
	if (Info.bExists) { Commands.Add({ CmdDisband, ESRIcon::Disband, TEXT("Del"), TEXT("Disband"), TEXT("Disband platoon   [Delete]"), TEXT("Break up the platoon. The troops stay selected."), false }); }
	const float BS = U(52.f), Gap = U(6.f);
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
			if (C.Kind == CmdForm) { TitleText = FString::Printf(TEXT("Formation: %s   [F]"), *USRPlatoonSubsystem::FormationName(Shape).ToString()); }
			SetTooltip(CmdBox, TitleText, { C.Line });
		}
		if (!B.bClicked) { continue; }
		Click();
		switch (C.Kind)
		{
		case CmdAttack: PC->ArmAttackMoveCommand(); break;
		case CmdStop: PC->IssueStop(); break;
		case CmdHold: PC->IssueHold(); break;
		case CmdPatrol: PC->ArmPatrolCommand(); break;
		case CmdStance: PC->CycleStanceCommand(); break;
		case CmdForm: PC->CycleFormationCommand(); break;
		case CmdDisband: PC->DisbandPlatoonCommand(); break;
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
	const float MeterW = bRecruits ? U(150.f) : U(260.f);

	Icon(BuildingIcon(Building->BuildingType), X, Y, U(42.f));
	Text(Building->GetDisplayName(), X + U(52.f), Y - U(2.f), U(22.f), bPlayer ? GoldBright : FLinearColor(1.f, 0.55f, 0.45f, 1.f), AlignLeft, Bold);
	{
		FString Sub = bPlayer ? TEXT("Your kingdom") : TEXT("Enemy kingdom");
		if (Building->GetState() == ESRBuildingState::Damaged) { Sub += TEXT("  ·  badly damaged"); }
		Text(Sub, X + U(52.f), Y + U(25.f), U(14.f), bPlayer ? Dim : Refuse);
	}

	const float HY = Y + U(56.f);
	Meter(X, HY, MeterW, U(10.f), Building->GetHealthFrac(), Health(Building->GetHealthFrac()));
	Text(FString::Printf(TEXT("%d / %d"), FMath::CeilToInt(Building->GetHealth()), FMath::RoundToInt(Stats.MaxHealth)), X + MeterW + U(10.f), HY - U(5.f), U(15.f), Parchment, AlignLeft, Bold);
	const float LY = HY + U(24.f);

	if (Building->IsUnderConstruction())
	{
		Text(FString::Printf(TEXT("Under construction   %d%%"), FMath::RoundToInt(Building->GetBuildProgress() * 100.f)), X, LY, U(15.f), Parchment);
		Meter(X, LY + U(26.f), MeterW, U(9.f), Building->GetBuildProgress(), GoldBright);
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

	if (Building->BuildingType == ESRBuildingType::Farm || Building->BuildingType == ESRBuildingType::Mine)
	{
		const bool bFarm = Building->BuildingType == ESRBuildingType::Farm;
		Icon(bFarm ? ESRIcon::Food : ESRIcon::Coin, X, LY, U(20.f));
		Text(FString::Printf(TEXT("+%d %s every %.0f s"), bFarm ? F.FarmFoodPerPayout : F.MineGoldPerPayout, bFarm ? TEXT("food") : TEXT("gold"), bFarm ? F.FarmPayoutInterval : F.MinePayoutInterval),
			X + U(27.f), LY, U(15.f), Parchment);
		Meter(X, LY + U(28.f), MeterW, U(8.f), Building->GetPayoutFraction(), bFarm ? FoodColor : Gold);
		if (Stats.PopProvided > 0) { Text(FString::Printf(TEXT("Houses %d troops"), Stats.PopProvided), X + MeterW + U(14.f), LY + U(22.f), U(14.f), Dim); }
		return;
	}
	if (Building->BuildingType == ESRBuildingType::Tower)
	{
		Text(FString::Printf(TEXT("Shoots enemies in range: %.0f damage every %.1f s"), Stats.AttackDamage, Stats.AttackInterval), X, LY, U(15.f), Parchment);
		Text(FString::Printf(TEXT("Reach %.0f m (the orange circle)"), Stats.AttackRange / 100.f), X, LY + U(22.f), U(14.f), Dim);
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
		Text(TEXT("Recruit troops for food."), X, LY, U(15.f), Parchment);
		Text(TEXT("RMB on the ground: rally point"), X, LY + U(22.f), U(14.f), Dim);
	}
	else
	{
		float QX = X + Text(TEXT("Training"), X, LY + U(3.f), U(14.f), Dim) + U(8.f);
		for (int32 i = 0; i < Queue.Num(); ++i)
		{
			// the one in training is drawn larger and bright, the ones waiting smaller and dimmer
			const float S = U(i == 0 ? 26.f : 20.f);
			Icon(Queue[i] == ESRUnitType::Archer ? ESRIcon::PortraitArcher : ESRIcon::PortraitShield, QX, LY + (i == 0 ? -U(2.f) : U(2.f)), S, FLinearColor(1.f, 1.f, 1.f, i == 0 ? 1.f : 0.7f));
			QX += S + U(3.f);
		}
		Meter(X, LY + U(30.f), U(240.f), U(8.f), Building->GetBuildFraction(), GoldBright);
	}

	const int32 Pop = Economy->GetPopulation(ESRTeam::Player) + Economy->GetQueuedPopulation(ESRTeam::Player), Cap = Economy->GetPopulationCap(ESRTeam::Player);
	const float RW = U(190.f);
	for (int32 i = 0; i < 2; ++i)
	{
		const ESRUnitType Type = i == 1 ? ESRUnitType::Archer : ESRUnitType::Shieldbearer;
		if (!Building->Trains(Type)) { continue; }
		const FSRUnitStats& Unit = F.StatsFor(Type);
		const FSRCost& Cost = F.CostFor(Type);
		const bool bGold = Economy->GetResource(ESRTeam::Player, ESRResource::Gold) >= Cost.Gold;
		const bool bFood = Economy->GetResource(ESRTeam::Player, ESRResource::Food) >= Cost.Food;
		const bool bRoom = Queue.Num() < F.MaxRecruitQueue;
		const bool bHoused = Pop + Unit.PopCost <= Cap;
		const bool bEnabled = bGold && bFood && bRoom && bHoused;
		const float RX = Box.Max.X - U(16.f) - RW;
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
		Icon(i == 1 ? ESRIcon::PortraitArcher : ESRIcon::PortraitShield, R.Min.X + U(9.f), R.Min.Y + U(12.f) + Lift, U(48.f), bEnabled ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
		const float TX = R.Min.X + U(64.f);
		Text(Unit.DisplayName, TX, R.Min.Y + U(30.f) + Lift, U(14.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
		KeyCap(i == 1 ? TEXT("E") : TEXT("Q"), R.Max.X - U(6.f), R.Min.Y + U(6.f), bEnabled);
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
		const FString Status = !bHoused ? TEXT("Housing full") : (!bRoom ? TEXT("Queue full") : FString::Printf(TEXT("Trains in %.0f s"), F.BuildTimeFor(Type)));
		Text(Status, R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), (!bHoused || !bRoom) ? Refuse : Dim);
		if (B.bClicked) { PC->RecruitTroop(Type); if (bEnabled) { Click(); } }
		if (B.bHover)
		{
			TArray<FString> Lines;
			Lines.Add(i == 1 ? TEXT("Light and quick, with a long reach. Weak up close.") : TEXT("Heavy infantry: holds the line and hits hard."));
			Lines.Add(FString::Printf(TEXT("Cost %d food   ·   trains in %.0f s   ·   %d housing"), Cost.Food, F.BuildTimeFor(Type), Unit.PopCost));
			if (!bHoused) { Lines.Add(TEXT("Housing is full: build more farms.")); }
			SetTooltip(R, FString::Printf(TEXT("%s   [%s]"), *Unit.DisplayName, i == 1 ? TEXT("E") : TEXT("Q")), Lines);
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
		// engaged: the left edge burns
		Fill(Row.Min.X, Row.Min.Y, U(3.f), H, Info.Engaged > 0 ? A(Refuse, 0.65f + 0.35f * FMath::Sin(float(Now) * 8.f)) : (bSelected ? GoldBright : TeamBlue));
		TextIn(FBox2D(Badge.Min + FVector2D(U(3.f), 0.f), Badge.Max + FVector2D(U(3.f), 0.f)), FString::FromInt(i + 1), U(20.f), GoldBright, AlignCentre, Black);
		const ESRIcon Kind = Info.Kind == ESRPlatoonKind::ArcherCompany ? ESRIcon::Bow : (Info.Kind == ESRPlatoonKind::MixedHost ? ESRIcon::Pop : ESRIcon::Shield);
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
		Icon(ESRIcon::Shield, CX, CY, U(16.f));
		CX += U(18.f) + Text(FString::FromInt(Info.Shieldbearers), CX + U(18.f), CY - U(1.f), U(14.f), Parchment) + U(8.f);
		Icon(ESRIcon::Bow, CX, CY, U(16.f));
		CX += U(18.f) + Text(FString::FromInt(Info.Archers), CX + U(18.f), CY - U(1.f), U(14.f), Parchment) + U(8.f);
		if (Info.Engaged > 0) { Icon(ESRIcon::Swords, CX, CY, U(16.f), FLinearColor(1.f, 1.f, 1.f, 0.65f + 0.35f * FMath::Sin(float(Now) * 8.f))); }
		Meter(TX, Row.Max.Y - U(9.f), TW - U(4.f), U(4.f), Info.Health, Health(Info.Health));

		const bool bRecruits = RecruitTarget == i;
		ButtonFrame(Small[0], SmallB[0], true);
		Icon(FormationIcon(Info.Formation), Small[0].Min.X + U(5.f), Small[0].Min.Y + U(5.f), SB - U(10.f));
		ButtonFrame(Small[1], SmallB[1], true);
		Icon(StanceIcon(Info.Stance), Small[1].Min.X + U(5.f), Small[1].Min.Y + U(5.f), SB - U(10.f));
		ButtonFrame(Small[2], SmallB[2], true, bRecruits);
		Icon(ESRIcon::RecruitFlag, Small[2].Min.X + U(5.f), Small[2].Min.Y + U(5.f), SB - U(10.f), FLinearColor(1.f, 1.f, 1.f, bRecruits ? 1.f : 0.4f));
		ButtonFrame(Small[3], SmallB[3], true);
		Icon(ESRIcon::Disband, Small[3].Min.X + U(5.f), Small[3].Min.Y + U(5.f), SB - U(10.f));
		if (SmallB[3].bHover) { SetTooltip(Small[3], TEXT("Disband"), { TEXT("Break up the platoon (the troops stay)."), TEXT("A platoon whose troops all fall disbands itself.") }); }
		if (SmallB[3].bClicked) { Click(); Platoons->Disband(i); continue; }
		if (SmallB[0].bHover) { SetTooltip(Small[0], FString::Printf(TEXT("Formation: %s"), *USRPlatoonSubsystem::FormationName(Info.Formation).ToString()), { TEXT("Click (or F) to change.") }); }
		if (SmallB[1].bHover) { SetTooltip(Small[1], FString::Printf(TEXT("Stance: %s"), *USRPlatoonSubsystem::StanceName(Info.Stance).ToString()), { TEXT("Click (or G) to change.") }); }
		if (SmallB[2].bHover) { SetTooltip(Small[2], bRecruits ? TEXT("Recruits join here") : TEXT("Recruits do not join"), { TEXT("New troops from your barracks and ranges march to this platoon.") }); }
		if (SmallB[0].bClicked) { Click(); Platoons->CycleFormation(i); }
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
			SetTooltip(Row, Info.Name, { FString::Printf(TEXT("%s  ·  %d troops  ·  %d%% health"), *USRPlatoonSubsystem::KindName(Info.Kind).ToString(), Info.Shieldbearers + Info.Archers, FMath::RoundToInt(Info.Health * 100.f)),
				FString::Printf(TEXT("Click or press %d to select; twice to go there."), i + 1) });
		}
	}
}
