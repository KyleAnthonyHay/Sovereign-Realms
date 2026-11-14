"""Creates /Game/Maps/L_Battlefield if it does not exist: a flat ground slab plus the bare
minimum of lighting so the level is visible. Everything else (units, camera, obstacles) is
spawned from C++ at runtime by ASRGameMode / USRBattleSubsystem.

Run inside the editor:
  UnrealEditor <project>.uproject -ExecutePythonScript="<repo>/Tools/create_battlefield_map.py"
Lighting, fog, post-process, terrain and materials are owned by the visual-design pass.
"""
import unreal

MAP = "/Game/Maps/L_Battlefield"


def main():
    if unreal.EditorAssetLibrary.does_asset_exist(MAP):
        unreal.log("L_Battlefield already exists; leaving it alone.")
        return

    level_sub = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not level_sub.new_level(MAP):
        unreal.log_error("Could not create " + MAP)
        return

    # 80m x 80m slab, top face at Z=0. Gameplay bounds are +/-30m (USRFeelSettings.MapHalfExtent).
    ground = actor_sub.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, -50))
    ground.set_actor_label("Ground")
    ground.set_folder_path("Greybox")
    ground.static_mesh_component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Cube"))
    ground.static_mesh_component.set_material(0, unreal.load_asset("/Engine/EngineMaterials/WorldGridMaterial"))
    ground.set_actor_scale3d(unreal.Vector(80, 80, 1))

    sun = actor_sub.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 800), unreal.Rotator(0, -42, -35))
    sun.set_actor_label("Sun")
    sun.set_folder_path("Lighting")
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property("atmosphere_sun_light", True)

    sky = actor_sub.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 900))
    sky.set_actor_label("SkyLight")
    sky.set_folder_path("Lighting")
    sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property("real_time_capture", True)

    atmo = actor_sub.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
    atmo.set_actor_label("SkyAtmosphere")
    atmo.set_folder_path("Lighting")

    level_sub.save_current_level()
    unreal.log("Created " + MAP)


main()
