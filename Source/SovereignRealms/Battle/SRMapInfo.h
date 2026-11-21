// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Info.h"
#include "SRMapInfo.generated.h"

class UTexture2D;

/**
 * What the game needs to know about one battle map: its size, where the two kingdoms start, how high its ground goes.
 * One per level, placed by the level builder (Tools/), which fills these in from the map generator's own numbers.
 *
 * When a map starts (ASRGameMode::InitGame, before any actor begins play) ApplyToSettings copies the size, the two
 * starts and the focus ceiling over the Sovereign Feel settings of the same names, so everything that reads
 * USRFeelSettings::MapHalfExtent / PlayerStart / EnemyStart / FocusHeightMax follows the map being played. A level
 * without one keeps the settings as they are.
 */
UCLASS()
class SOVEREIGNREALMS_API ASRMapInfo : public AInfo
{
	GENERATED_BODY()

public:
	/** The map's id in USRFeelSettings::Maps ("two", "four"): saved games remember it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	FName MapId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	FString DisplayName;

	/** The playable area is +/- this (cm) round the world origin: the camera's bounds, move orders, the grid, the fog. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	FVector2D HalfExtent = FVector2D(21000.f, 21000.f);

	/** Centre of the player's starting troops (world XY, cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	FVector2D PlayerStart = FVector2D(-5500.f, -5000.f);

	/** Centre of the enemy's starting troops (world XY, cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	FVector2D EnemyStart = FVector2D(5500.f, 5000.f);

	/** The camera rides the ground under its focus, but never higher than this (cm): the top of the ground troops can stand on. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	float FocusHeightMax = 900.f;

	/** The walkability grid's ground traces run from this height (cm) down to GroundTraceBottom: above the highest peak... */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	float GroundTraceTop = 8000.f;

	/** ...and below the deepest lake bed. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	float GroundTraceBottom = -2000.f;

	/** The minimap's picture of this map (none: /Game/SR/Textures/T_MinimapBase). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	TObjectPtr<UTexture2D> MinimapBase;

	/** The level's map info (null if it has none). */
	static const ASRMapInfo* Get(const UObject* WorldContext);

	/** Copies this level's size, starts and focus ceiling over the Sovereign Feel settings (nothing, if the level has no map info). */
	static void ApplyToSettings(UWorld* World);
};
