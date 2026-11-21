#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "VLHUD.generated.h"

/**
 * What is drawn over the view: the mode (hero / overview), the selection (gold corner brackets round the selected
 * thing, faint ones round what the mouse is over), a line of controls, and the pause menu (Esc: Resume / Flatlands or Village / Quit).
 * AVLKing feeds it the input.
 */
UCLASS()
class VOXELLAB_API AVLHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	/** 0 = Resume, 1 and 2 = the other two maps, 3 = Quit, -1 = none: the button under a point of the viewport. */
	int32 ButtonAt(const FVector2D& Point, const FVector2D& ViewSize) const;

	/** In the overview with a barracks / archery range (Train) or a manned watch tower (Send out) selected: 0 if the
	 *  point is on that button, else -1. */
	int32 TrainButtonAt(const FVector2D& Point, const FVector2D& ViewSize) const;

	/** The building review field, L_Flatlands (every building side by side), rather than the village. */
	bool InFlatlands() const;
	/** The maps of the menu: 0 the town, 1 the flatlands, 2 the village. */
	static const int32 NumMaps = 3;
	static FString MapPath(int32 Map);
	static const TCHAR* MapName(int32 Map);
	int32 CurrentMap() const;
	/** The two maps that are not this one: Which 0 = the next round, 1 = the one after. */
	int32 OtherMap(int32 Which) const { return (CurrentMap() + 1 + Which) % NumMaps; }
	static const int32 NumButtons = 8;      // Resume, the two other maps, music, camera angle, look speed, invert look, Quit

	bool bMenu = false;
	int32 Hover = -1;

private:
	FBox2D ButtonRect(int32 Index, const FVector2D& ViewSize) const;
	FBox2D TrainRect(const FVector2D& ViewSize) const;
	/** The selected building that trains troops, if the overview shows one. */
	AActor* TrainingBuilding() const;
	/** The selected watch tower, if the overview shows one. */
	AActor* SelectedTower() const;
	void Ring(const FVector& Centre, float Radius, const FLinearColor& Colour, float Thickness);
	void Brackets(AActor* Actor, const FLinearColor& Colour, float Thickness);
};
