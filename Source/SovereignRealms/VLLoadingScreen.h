#pragma once

#include "CoreMinimal.h"

/**
 * The loading screen: a dark screen in the interface's palette with the emblem, an 8-bit King David running along a
 * strip of pixel ground (the sheet /Game/Voxel/UI/T_UI_KingRun, Tools/blender/assets/king_run_sprite.py) and
 * "LOADING...". It is up whenever the engine loads a map (the game starting, New Game, Restart, Main Menu, vl.Map: all
 * of them UEngine::LoadMap) and stays for at least a second.
 *
 * A level load blocks the game thread, so this is the engine's MoviePlayer loading screen: one Slate widget, painted
 * by the movie player's own thread while the load runs, its animation driven by the clock alone. The movie player
 * does not exist in the editor (IsMoviePlayerEnabled()), so Play In Editor shows no loading screen and is otherwise
 * untouched; a standalone game (-game) and the packaged builds show it. (-NoLoadingScreen turns it off, except in
 * Shipping.)
 */
namespace VLLoadingScreen
{
	/** The game module's StartupModule / ShutdownModule. */
	void Startup();
	void Shutdown();
}
