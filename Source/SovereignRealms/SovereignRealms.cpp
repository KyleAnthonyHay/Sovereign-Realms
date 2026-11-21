// ================================================================================================================
// DEPRECATED: superseded by VoxelLab (VoxelLab/Source/VoxelLab). This module is the first draft of Sovereign Realms and
// is no longer developed. Its game logic was reimplemented there (VLBattle, VLEnemyAI, VLCommand, VLHUD, the combat
// components); the Builder, Scout, Medic, Catapult, Horseman, construction, fog of war and saves remain only here.
// See README.md at the repository root. Kept so the old project still builds; do not delete.
// ================================================================================================================
// Copyright Sovereign Realms.

#include "SovereignRealms.h"
#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY(LogSovereign);

IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, SovereignRealms, "SovereignRealms");
