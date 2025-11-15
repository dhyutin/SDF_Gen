bl_info = {
    "name": "SDF_Gen_updated_collider",
    "author": "Cole Biesemeyer",
    "version": (1, 0, 0),
    "blender": (4, 3, 0),
    "location": "3D Viewport > Sidebar > SDF_Gen_updated_collider",
    "description": "Creates SDF files from Blender scenes",
    "category": "View3D",
}

# This is only relevant on first run, on later reloads those modules
# are already in locals() and those statements do not do anything.
import bpy

from . import auto_load

auto_load.init()

# from .ui.utility_panel import SDFG_PT_Utilities  # Import your panel class
# from .operators.utility import SDFG_OT_UtilitiesOperator
# from .ui.links_panel import SNA_UL_display_scenes_list
# import operators.colliders
from .operators.create import update_scene
from .ui.object_properties_panel import LinkCollectionProperties
from .operators.joints import JointBoneProperties
from .operators.auto_colliders import MagicColliderResult


def register():
    auto_load.register()
    bpy.types.WindowManager.my_list_index = bpy.props.IntProperty(update=update_scene)
    """keymaps = bpy.context.window_manager.keyconfigs.addon.keymaps.new(
        name="3D View", space_type="VIEW_3D"
    )
    kmi = keymaps.keymap_items.new("my_panel.add_scene", "PLUS", "PRESS")
    kmi = keymaps.keymap_items.new("my_panel.delete_scene", "MINUS", "PRESS")"""

    bpy.types.Collection.link_grp = bpy.props.PointerProperty(type=LinkCollectionProperties)
    bpy.types.PoseBone.joint_grp = bpy.props.PointerProperty(type=JointBoneProperties)
    bpy.types.Scene.magic_collider_results = bpy.props.CollectionProperty(type=MagicColliderResult)
    # bpy.types.Scene.utilties_advanced = bpy.props.BoolProperty(name="Utilities Advanced", default=False)

    # LLM settings for Magic Collider (Azure OpenAI)
    bpy.types.Scene.use_llm_collider = bpy.props.BoolProperty(
        name="Use LLM",
        description="Use Large Language Model for intelligent collider selection (configure in .env file)",
        default=False
    )

    # Performance settings for Magic Collider
    bpy.types.Scene.max_refinement_iterations = bpy.props.IntProperty(
        name="Max Refinement Iterations",
        description="Maximum number of refinement iterations for complex objects (0=skip, 1=balanced, 3=high quality)",
        default=1,
        min=0,
        max=3
    )

    bpy.types.Scene.simple_object_volume_threshold = bpy.props.FloatProperty(
        name="Simple Object Volume Threshold",
        description="Objects with volume below this threshold skip refinement (smaller = faster)",
        default=0.001,
        min=0.0,
        max=1.0
    )

    bpy.types.Scene.simple_object_size_threshold = bpy.props.FloatProperty(
        name="Simple Object Size Threshold",
        description="Objects with max dimension below this threshold skip refinement (smaller = faster)",
        default=0.05,
        min=0.0,
        max=1.0
    )


def unregister():
    # bpy.utils.unregister_class(JointObjectProperties)
    auto_load.unregister()
    # bpy.utils.unregister_class(MyPanel)
    del bpy.types.WindowManager.my_list_index
    del bpy.types.PoseBone.joint_grp
    del bpy.types.Collection.link_grp
    del bpy.types.Scene.magic_collider_results
    # del bpy.types.Scene.utilties_advanced

    # Delete LLM settings
    del bpy.types.Scene.use_llm_collider
    del bpy.types.Scene.max_refinement_iterations
    del bpy.types.Scene.simple_object_volume_threshold
    del bpy.types.Scene.simple_object_size_threshold


if __name__ == "__main__":
    register()

    