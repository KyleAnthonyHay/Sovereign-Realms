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
}
