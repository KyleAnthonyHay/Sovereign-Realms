#pragma once

#include "CoreMinimal.h"

/**
 * The loading screen: the emblem, an 8-bit King David running along a strip of pixel ground (the owner's run,
 * References/KingRunSprite, as /Game/Voxel/UI/T_UI_KingRun: Tools/blender/assets/king_run_sprite.py) and "LOADING...", in the interface's
 * night-blue. It is up whenever the engine loads a map (the game starting, New Game, Restart, Main Menu, vl.Map: all
 * of them UEngine::LoadMap).
 *
 * It is a little endless runner too, our own: rocks, barrels, stakes and arrows come at him along the ground and are
 * jumped, crows come at his head and are ducked; the ground quickens, a count runs, and running into something makes
 * him stumble (a flash, the count starts again, on he goes). While the map loads he plays by himself: a level load
 * blocks the game thread, which reads no keys then, so the screen is the engine's MoviePlayer loading screen (one
 * Slate widget painted by the movie player's own thread, moved by the clock alone).
 *
 * When the level of a match is ready (its URL has Match: New Game, Restart, a saved game) the screen stays: "PRESS
 * ENTER TO PLAY" (Enter, or A / Start on a gamepad); the title screen's level goes as soon as it is ready. The movie
 * player holds the game thread in its waiting loop meanwhile, still inside LoadMap, so the world behind does not tick
 * (the match's clock starts when the screen goes), and there the keys are live: Space / Up / W jumps and takes him
 * over from then on, Down / S ducks (or drops him faster in the air). The best score is kept in GameUserSettings.ini ([VLRunner] Best).
 * In a run nobody watches (-unattended, as the tools' scripts start the game, or -VLNoEnter) the screen goes by
 * itself once the level is ready, after a second at least.
 *
 * The movie player does not exist in the editor (IsMoviePlayerEnabled()), so Play In Editor shows no loading screen
 * and is otherwise untouched; a standalone game (-game) and the packaged builds show it. (-NoLoadingScreen turns it
 * off, except in Shipping.)
 */
namespace VLLoadingScreen
{
	/** The game module's StartupModule / ShutdownModule. */
	void Startup();
	void Shutdown();
	/**
	 * Opens a map (as UGameplayStatics::OpenLevel) with the loading screen up at once and playable: the runner goes on
	 * the game's viewport (the keys arrive: the game thread is free), the world behind is paused, and the map's package
	 * is loaded in the background (LoadPackageAsync); the old world's assets are kept in memory over the change. Then
	 * the map is opened: the blocking part that is left (the old world torn down, the new one set up and begun) shows
	 * the same runner through the movie player, and "PRESS ENTER TO PLAY" follows as before. Every map change of the
	 * game goes through here (New Game, Restart, Main Menu, a saved game, vl.Map). In the editor (Play In Editor), with
	 * -NoLoadingScreen or -VLNoPreload it is a plain OpenLevel.
	 */
	void Travel(const UObject* WorldContext, const FString& MapPath, const FString& Options);
}
