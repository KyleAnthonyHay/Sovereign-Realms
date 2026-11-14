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

private:
	void DrawSelectionBox();
	void DrawHealthBars();
	void DrawStatusText();
	float UIScale() const;
};
