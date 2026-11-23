"""The optimization pass's look settings, put on maps and materials that are already built (the builders carry the
same values for the next regeneration: build_level.py lamps() / place(), build_special_materials.py sway()).

  python3 Tools/ue_py.py Tools/ue/patch_optim.py            (editor open, no play session)

- every lamp (PointLight actor): max_draw_distance / max_distance_fade_range (build_level.P lamp_draw / lamp_fade)
- wheat (SM_Wheat* actors): the 60 m world-position-offset disable distance the grass and the flowers have
- MI_Sway_* (the plants' wind material instances): one-sided
Globals: MAPS (names), DRY=True (report only), PARTS (["lamps", "wheat", "sway"]).
"""
import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

MAPS = globals().get("MAPS") or ["L_Realm", "L_Highlands", "L_RealmV2", "L_Flatlands"]
PARTS = globals().get("PARTS") or ["lamps", "wheat", "sway"]
DRY = bool(globals().get("DRY"))
LAMP_DRAW, LAMP_FADE = 30000.0, 8000.0          # cm: as build_level.P lamp_draw / lamp_fade
WPO_OFF = 6000


def sway():
    n = 0
    for slot in ("leaves", "paint", "wheat", "wheat_top", "moss", "dirt", "grass"):
        path = "/Game/Voxel/Materials/MI_Sway_" + slot
        if not eal.does_asset_exist(path):
            continue
        mi = eal.load_asset(path)
        bpo = mi.get_editor_property("base_property_overrides")
        if bpo.get_editor_property("override_two_sided") and not bpo.get_editor_property("two_sided"):
            continue
        n += 1
        if DRY:
            continue
        bpo.set_editor_property("override_two_sided", True)
        bpo.set_editor_property("two_sided", False)
        mi.set_editor_property("base_property_overrides", bpo)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi, False)
    print("sway instances made one-sided:", n)


def level(name):
    if not les.load_level("/Game/Maps/" + name):
        print(name, "did not load")
        return
    lamps = wheat = 0
    nl = nw = 0
    for a in eas.get_all_level_actors():
        if "lamps" in PARTS and isinstance(a, unreal.PointLight):
            nl += 1
            lc = a.get_component_by_class(unreal.PointLightComponent)
            if abs(lc.get_editor_property("max_draw_distance") - LAMP_DRAW) > 1 or abs(lc.get_editor_property("max_distance_fade_range") - LAMP_FADE) > 1:
                lamps += 1
                if not DRY:
                    lc.set_editor_property("max_draw_distance", LAMP_DRAW)
                    lc.set_editor_property("max_distance_fade_range", LAMP_FADE)
        elif "wheat" in PARTS and isinstance(a, unreal.StaticMeshActor):
            c = a.static_mesh_component
            sm = c.static_mesh if c else None
            if sm and sm.get_name().startswith("SM_Wheat"):
                nw += 1
                if c.get_editor_property("world_position_offset_disable_distance") != WPO_OFF:
                    wheat += 1
                    if not DRY:
                        c.set_editor_property("world_position_offset_disable_distance", WPO_OFF)
    if (lamps or wheat) and not DRY:
        les.save_current_level()
    print("%s: %d of %d lamp(s), %d of %d wheat changed%s" % (name, lamps, nl, wheat, nw, " (dry run)" if DRY else ""))


if "sway" in PARTS:
    sway()
if "lamps" in PARTS or "wheat" in PARTS:
    for m in MAPS:
        level(m)
