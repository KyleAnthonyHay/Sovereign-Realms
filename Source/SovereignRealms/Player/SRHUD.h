// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "SRHUD.generated.h"

/**
 * Immediate-mode overlay for the combat slice: the box-select rectangle, unit
 * health bars, the battle result line and a small controls reminder.
 * Deliberately not UMG: there are no menus in this slice and the real HUD comes later.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	/** Index of the recruit button under a viewport position (0 Shieldbearer, 1 Archer), or -1. Only while the player's castle is selected. */
	int32 RecruitButtonAt(const FVector2D& Pixels) const;
	/** Is the position over a HUD panel (resource bar, building panel)? Clicks there are not for the world. */
	bool IsOverPanel(const FVector2D& Pixels) const;

private:
	/** Where the panels are, in viewport pixels. One function, so drawing and hit-testing can never disagree. */
	struct FLayout
	{
		float UI = 1.f;
		FBox2D Resources = FBox2D(ForceInit);
		bool bBuildingPanel = false;
		FBox2D Panel = FBox2D(ForceInit);
		bool bButtons = false;
		FBox2D Buttons[2] = { FBox2D(ForceInit), FBox2D(ForceInit) };
	};
	FLayout ComputeLayout(const FVector2D& ViewSize) const;
	FVector2D ViewSize() const;

	void DrawSelectionBox();
	void DrawHealthBars();
	void DrawStatusText();
	void DrawResourceBar(const FLayout& L);
	void DrawBuildingPanel(const FLayout& L);
	void DrawPayoutPopups(const FLayout& L);
	void DrawTrainingBars(const FLayout& L);

	// immediate-mode pieces
	void Panel(const FBox2D& Box, float UI, float Alpha = 1.f);
	void Icon(const TCHAR* const* Rows, int32 NumRows, float X, float Y, float Pixel, const FLinearColor& Team, float Alpha = 1.f, bool bGrey = false);
	void Label(const FString& Text, float X, float Y, float Scale, const FLinearColor& Color, bool bShadow = true);
	float LabelWidth(const FString& Text, float Scale);
	void Bar(float X, float Y, float W, float H, float Frac, const FLinearColor& Fill, float UI);

	float UIScale() const;
};
