// Copyright Sovereign Realms.

#include "Player/SRHUD.h"
#include "Player/SRPlayerController.h"
#include "Units/SRUnit.h"
#include "Battle/SRBattleSubsystem.h"
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
	DrawHealthBars();
	DrawSelectionBox();
	DrawStatusText();
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
	}

	if (PC->IsAttackMoveArmed())
	{
		DrawText(TEXT("ATTACK-MOVE: click a destination or an enemy (right-click cancels)"), FLinearColor(1.f, 0.45f, 0.3f), 14.f * UI, 50.f * UI, nullptr, 1.2f * UI);
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
