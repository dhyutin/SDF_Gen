import bpy
from ..operators.general_functions import show_message_box
import bmesh
import math
import os
from ..operators.general_functions import get_armature
from ..operators.general_functions import get_all_collections
from ..operators.general_functions import get_riginstance_objects
from mathutils import Vector
import json


def get_link_items_child(self, context):
    """Generates the list of link items for the enum property."""  # Added docstring
    link_items = []
    
    # Use children_recursive to get all collections
    for obj in context.scene.objects:
        if getattr(obj, "object_type", "") == "LinkInstanceObject" and obj.instance_collection.name != context.active_pose_bone.joint_grp.parent_link:
            link_items.append((obj.instance_collection.name, obj.instance_collection.name, obj.instance_collection.name))
    
    link_items.insert(0, ('None', "None", "No Child"))
    return link_items

class SDFG_OT_CreateJoint(bpy.types.Operator):
    bl_idname = "scene.create_joint"
    bl_label = "Create Joints"
    bl_description = "Creates link collection and nested visual and collider collections."
    bl_options = {'REGISTER', 'UNDO'}

    # Joint type property
    joint_type_selection: bpy.props.EnumProperty(
        name="Joint Type:",
        description="Type of joint to create",
        items=[
            ('Fixed', "Fixed", "No movement - welded connection (0 DOF)"),
            ('Revolute', "Revolute", "Rotational with angle limits (1 DOF)"),
            ('Continuous', "Continuous", "Unlimited 360° rotation like wheels (1 DOF)"),
            ('Prismatic', "Prismatic", "Linear sliding motion (1 DOF)"),
            ('Planar', "Planar", "Sliding + rotation in a plane (3 DOF)"),
            ('Floating', "Floating", "Free motion in all directions (6 DOF)")
        ],
        default="Fixed"
    ) # type: ignore

    # Get's the appropriate links that the user can select
    def get_link_items_child(self, context):
        # Generates the list of link items for the enum property.
        link_items = []
        
        # Use children_recursive to get all collections
        for obj in context.scene.objects:
            if getattr(obj, "object_type", "") == "LinkInstanceObject" and obj.constraints['Child Of'].subtarget == "":
                link_items.append((obj.instance_collection.name, obj.instance_collection.name, obj.instance_collection.name))
        
        # link_items.insert(0, ('None', "None", "No Child"))
        return link_items

    child_link_selection: bpy.props.EnumProperty(
        items=get_link_items_child,
        name="Child Links",
        description="List of currently selectable child links."
    ) # type: ignore

    # joint_location: bpy.props.FloatVectorProperty(
    #     name="joint Location",
    #     description="Set the location of the joint",
    #     default=(0.0, 0.0, 0.0),
    # ) # type: ignore

    # joint_rotation: bpy.props.FloatVectorProperty(
    #     name="Joint Rotation",
    #     description="Set the rotation of the joint",
    #     default=(0.0, 0.0, 0.0),
    #     subtype='EULER'
    # ) # type: ignore

    joint_name: bpy.props.StringProperty(
        name="Joint Name",
        description="Set the joint name",
        default="",
    ) # type: ignore

    show_in_last_operation: bpy.props.BoolProperty(default=False) # type: ignore

    def invoke(self, context, event):
        self.show_in_last_operation = False
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):   
        layout = self.layout
        layout.prop(self, "joint_type_selection", text="Joint Type")
        layout.prop(self, "child_link_selection", text="Child Link")

        if self.show_in_last_operation and bpy.context.active_object:
            split = layout.split()
            split.prop(self, "joint_location")
            split.prop(self, "joint_rotation")

    def create_joint_bone(self, context, joint_name, joint_type, joint_shape):
        # Find armature object and make it active/selected
        
        for obj in bpy.context.scene.objects:
            if obj.object_type == 'ArmatureObject':
                armature_obj = obj
                armature_obj.select_set(True)
                bpy.context.view_layer.objects.active = armature_obj

        # Switch to edit mode
        bpy.ops.object.mode_set(mode='EDIT')

        # Create bone and make it active
        bpy.ops.armature.bone_primitive_add(name=joint_name)
        joint_bone = armature_obj.data.edit_bones.get(joint_name)
        armature_obj.data.edit_bones.active = joint_bone
        joint_bone.select=True
        joint_bone.length = 0.01

        # Switch to pose mode
        bpy.ops.object.mode_set(mode='POSE')
        pose_bone = armature_obj.pose.bones.get(joint_name)
        armature_obj.data.bones.active = pose_bone.bone

        # Set joint type
        context.active_pose_bone.joint_grp.joint_type = joint_type

        # Set bone control shape
        pose_bone.custom_shape = bpy.data.objects[joint_shape]
        pose_bone.use_custom_shape_bone_size = False
        pose_bone.custom_shape_wire_width = 2.0
        pose_bone.color.palette = 'CUSTOM'
        bpy.context.active_pose_bone.color.custom.normal = (0.0, 1.0, 1.0)
        bpy.context.active_pose_bone.color.custom.select = (0.0, 1.0, 1.0)
        bpy.context.active_pose_bone.color.custom.active = (0.0, 1.0, 0.698)

        return pose_bone
    
    def joint_shape(self, context, joint_type):
        file_path = "path_to_your_blend_file.blend"
        bpy.ops.wm.link(filepath=file_path, )

    def execute(self, context):
        
        # Create fixed joint
        if self.joint_type_selection == 'Fixed':
            joint_name = self.child_link_selection + "_joint_fixed"
            joint_type = 'FixedJoint'
            joint_shape = "fixed"
            self.create_joint_bone(context, joint_name, joint_type, joint_shape)

        elif self.joint_type_selection == 'Revolute':
            joint_name = self.child_link_selection + "_joint_revolute"
            joint_type = 'RevoluteJoint'
            joint_shape = "revolute"
            pose_bone = self.create_joint_bone(context, joint_name, joint_type, joint_shape)

            # Add limit rotation constraint and set properties
            bpy.ops.pose.constraint_add(type='LIMIT_ROTATION')
            rotation_constraint = pose_bone.constraints['Limit Rotation']
            rotation_constraint.use_limit_x = True
            rotation_constraint.use_limit_z = True
            rotation_constraint.use_limit_y = True
            rotation_constraint.use_transform_limit = True
            rotation_constraint.owner_space = 'LOCAL'
            rotation_constraint.min_y = math.radians(-45.0)
            rotation_constraint.max_y = math.radians(45.0)

        elif self.joint_type_selection == 'Continuous':
            joint_name = self.child_link_selection + "_joint_continuous"
            joint_type = 'ContinuousJoint'
            joint_shape = "revolute"  # Use revolute shape for continuous
            pose_bone = self.create_joint_bone(context, joint_name, joint_type, joint_shape)

            # Add limit rotation constraint but with no limits (continuous rotation)
            bpy.ops.pose.constraint_add(type='LIMIT_ROTATION')
            rotation_constraint = pose_bone.constraints['Limit Rotation']
            rotation_constraint.use_limit_x = True
            rotation_constraint.use_limit_z = True
            rotation_constraint.use_limit_y = False  # No Y limit for continuous rotation
            rotation_constraint.use_transform_limit = True
            rotation_constraint.owner_space = 'LOCAL'

            # Mark as continuous
            context.active_pose_bone.joint_grp.revolute_continuous = True

        elif self.joint_type_selection == 'Prismatic':
            joint_name = self.child_link_selection + "_joint_prismatic"
            joint_type = 'PrismaticJoint'
            joint_shape = "prismatic"
            pose_bone = self.create_joint_bone(context, joint_name, joint_type, joint_shape)

            # Add limit rotation constraint and set properties
            bpy.ops.pose.constraint_add(type='LIMIT_LOCATION')
            location_constraint = pose_bone.constraints['Limit Location']
            location_constraint.use_min_x = True
            location_constraint.use_min_y = True
            location_constraint.use_min_z = True
            location_constraint.use_max_x = True
            location_constraint.use_max_y = True
            location_constraint.use_max_z = True
            location_constraint.min_y = -0.2
            location_constraint.max_y = 0.2
            location_constraint.use_transform_limit = True
            location_constraint.owner_space = 'LOCAL'

        elif self.joint_type_selection == 'Planar':
            joint_name = self.child_link_selection + "_joint_planar"
            joint_type = 'PlanarJoint'
            joint_shape = "prismatic"  # Use prismatic shape for planar
            pose_bone = self.create_joint_bone(context, joint_name, joint_type, joint_shape)

            # Add location constraint for 2D sliding (X and Y axes)
            bpy.ops.pose.constraint_add(type='LIMIT_LOCATION')
            location_constraint = pose_bone.constraints['Limit Location']
            location_constraint.use_min_x = True
            location_constraint.use_max_x = True
            location_constraint.use_min_y = True
            location_constraint.use_max_y = True
            location_constraint.use_min_z = True
            location_constraint.use_max_z = True
            location_constraint.min_x = -1.0
            location_constraint.max_x = 1.0
            location_constraint.min_y = -1.0
            location_constraint.max_y = 1.0
            location_constraint.min_z = 0.0  # Lock Z axis
            location_constraint.max_z = 0.0
            location_constraint.use_transform_limit = True
            location_constraint.owner_space = 'LOCAL'

            # Add rotation constraint for rotation around Z only
            bpy.ops.pose.constraint_add(type='LIMIT_ROTATION')
            rotation_constraint = pose_bone.constraints['Limit Rotation']
            rotation_constraint.use_limit_x = True
            rotation_constraint.use_limit_y = True
            rotation_constraint.use_limit_z = False  # Allow Z rotation
            rotation_constraint.min_x = 0.0
            rotation_constraint.max_x = 0.0
            rotation_constraint.min_y = 0.0
            rotation_constraint.max_y = 0.0
            rotation_constraint.use_transform_limit = True
            rotation_constraint.owner_space = 'LOCAL'

        elif self.joint_type_selection == 'Floating':
            joint_name = self.child_link_selection + "_joint_floating"
            joint_type = 'FloatingJoint'
            joint_shape = "fixed"  # Use fixed shape for floating (no constraints)
            pose_bone = self.create_joint_bone(context, joint_name, joint_type, joint_shape)

            # No constraints for floating joint - full 6 DOF freedom

        self.show_in_last_operation = True
    
        # bpy.ops.object.collection_instance_add()
        # context.active_object.location = self.joint_location
        # context.active_object.rotation_euler = self.joint_rotation

        # Set child_link
        # child_link = bpy.context.active_pose_bone.joint_grp.child_link
        child_link = self.child_link_selection
        bpy.data.objects[child_link].constraints['Child Of'].subtarget = bpy.context.active_pose_bone.name
        set_inverse(self, context)
        context.active_pose_bone.joint_grp.child_link = child_link

        return {'FINISHED'}

class SDFG_OT_AutoCreateJoints(bpy.types.Operator):
    """Automatically create all joints from AI vision analysis"""
    bl_idname = "scene.auto_create_joints"
    bl_label = "Auto-Create Joints from AI"
    bl_description = "Automatically creates joints based on AI vision analysis from Auto-Link"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Import the function to get saved joint data
        from . import auto_links

        # Get saved joint data from AI analysis
        joint_data = auto_links.get_saved_joint_data()

        if not joint_data:
            self.report({'ERROR'}, "No AI joint data found. Run Auto-Link first to analyze the model.")
            return {'CANCELLED'}

        # Verify armature exists
        armature_obj = None
        for obj in bpy.context.scene.objects:
            if getattr(obj, 'object_type', '') == 'ArmatureObject':
                armature_obj = obj
                break

        if not armature_obj:
            self.report({'ERROR'}, "No armature found. Create an armature first.")
            return {'CANCELLED'}

        # Set armature as active and switch to pose mode
        armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='POSE')

        # Get all available link instance objects
        available_links = {}
        for obj in bpy.context.scene.objects:
            if getattr(obj, 'object_type', '') == 'LinkInstanceObject':
                available_links[obj.name] = obj

        if not available_links:
            self.report({'ERROR'}, "No link instance objects found. Create armature first.")
            return {'CANCELLED'}

        created_joints = []
        skipped_joints = []

        # Helper function to find best matching link
        def find_best_match(ai_name, available_links):
            """Find the best matching link instance object"""
            # Exact match
            if ai_name in available_links:
                return ai_name, available_links[ai_name]

            # Try variations
            variations = [
                ai_name,
                ai_name.replace('_link', ''),
                ai_name + '_link',
                ai_name.replace('_link_link', '_link'),
            ]

            for var in variations:
                if var in available_links:
                    return var, available_links[var]

            # Fuzzy match: check if key parts match
            ai_parts = set(ai_name.lower().replace('_link', '').split('_'))
            best_match = None
            best_score = 0

            for link_name in available_links.keys():
                link_parts = set(link_name.lower().replace('_link', '').split('_'))
                common = ai_parts & link_parts
                if len(common) >= 2 and len(common) > best_score:
                    best_score = len(common)
                    best_match = link_name

            if best_match:
                return best_match, available_links[best_match]

            return None, None

        # Create each joint from the AI data
        for joint_info in joint_data:
            link_name = joint_info.get('link_name', '')
            joint_type = joint_info.get('joint_type', '').lower()
            parent_link = joint_info.get('parent_link', 'base_link')
            joint_axis = joint_info.get('joint_axis', 'z').lower()
            has_limits = joint_info.get('has_limits', False)

            # Find matching link object
            matched_name, link_obj = find_best_match(link_name, available_links)

            if not link_obj:
                skipped_joints.append(f"{link_name} (no matching link found)")
                continue

            # Check if link already has a joint
            if link_obj.constraints.get('Child Of') and link_obj.constraints['Child Of'].subtarget != "":
                skipped_joints.append(f"{link_name} (already has joint)")
                continue

            # Map AI joint type to Blender joint type
            if joint_type == 'continuous':
                bl_joint_type = 'Continuous'
                joint_shape = "revolute"
                internal_type = 'ContinuousJoint'
                is_continuous = True
            elif joint_type == 'revolute':
                bl_joint_type = 'Revolute'
                joint_shape = "revolute"
                internal_type = 'RevoluteJoint'
                is_continuous = False
            elif joint_type == 'prismatic':
                bl_joint_type = 'Prismatic'
                joint_shape = "prismatic"
                internal_type = 'PrismaticJoint'
                is_continuous = False
            elif joint_type == 'planar':
                bl_joint_type = 'Planar'
                joint_shape = "prismatic"
                internal_type = 'PlanarJoint'
                is_continuous = False
            elif joint_type == 'floating':
                bl_joint_type = 'Floating'
                joint_shape = "fixed"
                internal_type = 'FloatingJoint'
                is_continuous = False
            elif joint_type == 'fixed':
                bl_joint_type = 'Fixed'
                joint_shape = "fixed"
                internal_type = 'FixedJoint'
                is_continuous = False
            else:
                skipped_joints.append(f"{link_name} (unknown joint type: {joint_type})")
                continue

            # Create joint bone
            try:
                joint_name = f"{matched_name}_joint_{joint_type}"

                # Switch to edit mode to create bone
                bpy.ops.object.mode_set(mode='EDIT')

                # Create bone
                bpy.ops.armature.bone_primitive_add(name=joint_name)
                joint_bone = armature_obj.data.edit_bones.get(joint_name)
                armature_obj.data.edit_bones.active = joint_bone
                joint_bone.select = True
                joint_bone.length = 0.01

                # Switch to pose mode to configure
                bpy.ops.object.mode_set(mode='POSE')
                pose_bone = armature_obj.pose.bones.get(joint_name)
                armature_obj.data.bones.active = pose_bone.bone

                # Set joint type
                context.active_pose_bone.joint_grp.joint_type = internal_type

                # Set bone custom shape
                if joint_shape in bpy.data.objects:
                    pose_bone.custom_shape = bpy.data.objects[joint_shape]
                    pose_bone.use_custom_shape_bone_size = False
                    pose_bone.custom_shape_wire_width = 2.0

                # Set bone color
                pose_bone.color.palette = 'CUSTOM'
                context.active_pose_bone.color.custom.normal = (0.0, 1.0, 1.0)
                context.active_pose_bone.color.custom.select = (0.0, 1.0, 1.0)
                context.active_pose_bone.color.custom.active = (0.0, 1.0, 0.698)

                # Configure joint based on type
                if bl_joint_type == 'Revolute':
                    # Add limit rotation constraint
                    bpy.ops.pose.constraint_add(type='LIMIT_ROTATION')
                    rotation_constraint = pose_bone.constraints['Limit Rotation']
                    rotation_constraint.use_limit_x = True
                    rotation_constraint.use_limit_z = True
                    rotation_constraint.use_limit_y = True
                    rotation_constraint.use_transform_limit = True
                    rotation_constraint.owner_space = 'LOCAL'

                    # Set continuous flag
                    context.active_pose_bone.joint_grp.revolute_continuous = is_continuous

                    if has_limits and not is_continuous:
                        # Default limits, user can adjust later
                        rotation_constraint.min_y = math.radians(-45.0)
                        rotation_constraint.max_y = math.radians(45.0)
                    else:
                        # Wide limits for continuous joints
                        rotation_constraint.min_y = math.radians(-360.0)
                        rotation_constraint.max_y = math.radians(360.0)

                elif bl_joint_type == 'Prismatic':
                    # Add limit location constraint
                    bpy.ops.pose.constraint_add(type='LIMIT_LOCATION')
                    location_constraint = pose_bone.constraints['Limit Location']
                    location_constraint.use_min_x = True
                    location_constraint.use_min_y = True
                    location_constraint.use_min_z = True
                    location_constraint.use_max_x = True
                    location_constraint.use_max_y = True
                    location_constraint.use_max_z = True
                    location_constraint.use_transform_limit = True
                    location_constraint.owner_space = 'LOCAL'

                    if has_limits:
                        # Set limits based on axis (default values, user can adjust)
                        if joint_axis == 'z':
                            location_constraint.min_z = -0.5
                            location_constraint.max_z = 0.5
                        elif joint_axis == 'y':
                            location_constraint.min_y = -0.5
                            location_constraint.max_y = 0.5
                        elif joint_axis == 'x':
                            location_constraint.min_x = -0.5
                            location_constraint.max_x = 0.5
                    else:
                        location_constraint.min_y = -0.2
                        location_constraint.max_y = 0.2

                elif bl_joint_type == 'Continuous':
                    # Add limit rotation constraint but with no limits (continuous rotation)
                    bpy.ops.pose.constraint_add(type='LIMIT_ROTATION')
                    rotation_constraint = pose_bone.constraints['Limit Rotation']
                    rotation_constraint.use_limit_x = True
                    rotation_constraint.use_limit_z = True
                    rotation_constraint.use_limit_y = False  # No Y limit for continuous rotation
                    rotation_constraint.use_transform_limit = True
                    rotation_constraint.owner_space = 'LOCAL'

                    # Mark as continuous
                    context.active_pose_bone.joint_grp.revolute_continuous = True

                elif bl_joint_type == 'Planar':
                    # Add location constraint for 2D sliding (X and Y axes)
                    bpy.ops.pose.constraint_add(type='LIMIT_LOCATION')
                    location_constraint = pose_bone.constraints['Limit Location']
                    location_constraint.use_min_x = True
                    location_constraint.use_max_x = True
                    location_constraint.use_min_y = True
                    location_constraint.use_max_y = True
                    location_constraint.use_min_z = True
                    location_constraint.use_max_z = True
                    location_constraint.min_x = -1.0
                    location_constraint.max_x = 1.0
                    location_constraint.min_y = -1.0
                    location_constraint.max_y = 1.0
                    location_constraint.min_z = 0.0  # Lock Z axis
                    location_constraint.max_z = 0.0
                    location_constraint.use_transform_limit = True
                    location_constraint.owner_space = 'LOCAL'

                    # Add rotation constraint for rotation around Z only
                    bpy.ops.pose.constraint_add(type='LIMIT_ROTATION')
                    rotation_constraint = pose_bone.constraints['Limit Rotation']
                    rotation_constraint.use_limit_x = True
                    rotation_constraint.use_limit_y = True
                    rotation_constraint.use_limit_z = False  # Allow Z rotation
                    rotation_constraint.min_x = 0.0
                    rotation_constraint.max_x = 0.0
                    rotation_constraint.min_y = 0.0
                    rotation_constraint.max_y = 0.0
                    rotation_constraint.use_transform_limit = True
                    rotation_constraint.owner_space = 'LOCAL'

                elif bl_joint_type == 'Floating':
                    # No constraints for floating joint - full 6 DOF freedom
                    pass

                elif bl_joint_type == 'Fixed':
                    # No constraints for fixed joint - no movement
                    pass

                # Connect child link to this joint
                link_obj.constraints['Child Of'].subtarget = pose_bone.name
                set_inverse(self, context)
                context.active_pose_bone.joint_grp.child_link = matched_name

                # Show which link was matched if different from AI suggestion
                if matched_name != link_name:
                    created_joints.append(f"{link_name} → {matched_name} ({joint_type})")
                else:
                    created_joints.append(f"{link_name} ({joint_type})")

            except Exception as e:
                skipped_joints.append(f"{link_name} (error: {str(e)})")

        # Report results
        if created_joints:
            self.report({'INFO'}, f"Created {len(created_joints)} joints: {', '.join(created_joints)}")

        if skipped_joints:
            self.report({'WARNING'}, f"Skipped {len(skipped_joints)} joints: {', '.join(skipped_joints)}")
            if not created_joints:
                # Show available links if all joints were skipped
                link_list = ', '.join(available_links.keys())
                self.report({'INFO'}, f"Available link objects: {link_list}")

        if not created_joints and not skipped_joints:
            self.report({'INFO'}, "No joints to create")

        return {'FINISHED'}

class SDFG_OT_DeleteJoint(bpy.types.Operator):
    """Deletes the joint."""
    bl_idname = "scene.delete_joint"
    bl_label = "Delete Joint"
    bl_options = {'REGISTER', 'UNDO'}

    # def invoke(self, context, event):
        # return {'FINISHED'}
        # return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):   
        layout = self.layout
        if bpy.context.active_pose_bone:
            layout.label(text="Delete " + context.active_pose_bone.name + "?")
        else:
            layout.label(text="No active joint.")

    def delete_joint(self, context):
        bone_name = bpy.context.active_pose_bone.name

        # Remove link association
        for obj in context.scene.objects:
            for constraint in obj.constraints:
                if constraint.type == 'CHILD_OF' and constraint.subtarget == bone_name:
                    constraint.subtarget = ""
                    set_inverse(self, context)

        
        bpy.ops.object.mode_set(mode='EDIT')
        edit_bone = bpy.context.active_object.data.edit_bones.get(bone_name)
        bpy.context.active_object.data.edit_bones.remove(edit_bone)
        bpy.ops.object.mode_set(mode='POSE')

    def execute(self, context):
        if not context.active_pose_bone:
            show_message_box(message="No active object or selection.", title="Error", icon='INFO')
            return {'CANCELLED'}
        if bpy.context.selected_pose_bones:
            for bone in bpy.context.selected_pose_bones:
                context.object.data.bones.active = bone.bone
                self.delete_joint(context)
        else:
            self.delete_joint(context)

        return {'FINISHED'}

class SDFG_OT_ResetJoints(bpy.types.Operator):
    """Resets joint positions to zero."""
    
    bl_idname = "scene.reset_joints"
    bl_label = "Reset Joints"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for bone in bpy.context.active_object.pose.bones:
            bone.rotation_mode = 'XYZ' 
            bone.location = (0, 0, 0)
            bone.rotation_euler = (0, 0, 0)
        
        return {'FINISHED'}

def set_inverse(self, context):
    previous_selection = None
    # Store previous bone selection
    if bpy.context.active_pose_bone:
        previous_selection = bpy.context.active_pose_bone.name
    # Switch to object mode
    bpy.ops.object.mode_set(mode='OBJECT')

    # Iterate through all objects in the scene
    for obj in context.scene.objects:
        # Check if the object has any constraints
        if obj.constraints:
            # Iterate through the object's constraints
            for constraint in obj.constraints:
                # Check if the constraint is a Child Of constraint
                if constraint.type == 'CHILD_OF':
                    bpy.context.view_layer.objects.active = obj
                    # bpy.context.view_layer.objects.active = obj_inverse

                    # Set the inverse
                    bpy.ops.constraint.childof_set_inverse(constraint="Child Of", owner='OBJECT')

    armature_object = get_armature()
    bpy.context.view_layer.objects.active = armature_object
    bpy.ops.object.mode_set(mode='POSE')
    if previous_selection != None:
        pose_bone = armature_object.pose.bones.get(previous_selection)
        pose_bone.bone.select = True
        armature_object.data.bones.active = pose_bone.bone
    
class PivotToSelection(bpy.types.Operator):
    bl_idname = "object.pivot_to_selection"
    bl_label = "Pivot to selection"

    def execute(self, context):
        obj = bpy.context.object
        if obj and obj.type == 'MESH' and obj.mode == 'EDIT':
            # Get the bmesh data
            bm = bmesh.from_edit_mesh(obj.data)
            
            # Get the selection mode (vertex, edge, face)
            select_mode = bpy.context.tool_settings.mesh_select_mode[:]
            
            # Get the coordinates of the active selection
            if select_mode[0]:  # Vertex select mode
                selected_coords = [obj.matrix_world @ v.co for v in bm.verts if v.select]
                print("Selected Vertices:", selected_coords)
            elif select_mode[1]:  # Edge select mode
                selected_edges = [(obj.matrix_world @ e.verts[0].co, obj.matrix_world @ e.verts[1].co) 
                                for e in bm.edges if e.select]
                print("Selected Edges (pairs of vertices):", selected_edges)
            elif select_mode[2]:  # Face select mode
                selected_faces = [[obj.matrix_world @ v.co for v in f.verts] for f in bm.faces if f.select]
                print("Selected Faces (list of vertex coordinates):", selected_faces)

        return {'FINISHED'}

class JointParent(bpy.types.Operator):
    bl_idname = "object.set_joint_parent"
    bl_label = "Set the parent link of the joint"

    # Get's the appropriate links that the user can select
    def get_link_items_parent(self, context):
        """Generates the list of link items for the enum property."""  # Added docstring
        link_items = []
        
        # Use children_recursive to get all collections
        for obj in context.scene.objects:
            if getattr(obj, "object_type", "") == "LinkInstanceObject" and obj.instance_collection.name != context.active_pose_bone.joint_grp.parent_link:
                link_items.append((obj.instance_collection.name, obj.instance_collection.name, obj.instance_collection.name))
        
        link_items.insert(0, ('World', "World", "World"))
        return link_items
    
    select_links_parent: bpy.props.EnumProperty(
        items=get_link_items_parent,
        name="Joint Links",
        description="Stores currently selectable links. "
    ) # type: ignore

    def invoke(self, context, event):
        # Refresh the enum property items before drawing
        self.show_in_last_operation = False
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context): 
        # link_items = get_link_items(self, context)  
        layout = self.layout
        layout.prop(self, "select_links_parent")

    def execute(self, context):
        print("SOMETHING")

        armature = bpy.context.object
        parent_bone = armature.data.edit_bones.get(bpy.data.objects[self.select_links_parent].constraints['Child Of'].subtarget)

        bpy.ops.object.mode_set(mode='EDIT')
        armature.data.edit_bones.active.parent = parent_bone
        
        context.active_pose_bone.joint_grp.parent_link = self.select_links_parent
        return {'FINISHED'}

def link_joint_shapes(self, context):
    joint_names = ["revolute", "fixed", "prismatic"]
    addon_dir = os.path.dirname(__file__)
    file_path = os.path.join(addon_dir, "assets", "joints.blend")
    with bpy.data.libraries.load(file_path, link=True) as (data_from, data_to):
        data_to.objects = joint_names

    return {'FINISHED'}

class SelectJoint(bpy.types.Operator):
    bl_idname = "object.select_joint"
    bl_label = "Set the parent link of the joint"
    
    bone_name: bpy.props.StringProperty(name="Bone Name") # type: ignore

    def execute(self, context):
        bpy.ops.pose.select_all(action='DESELECT')

        for bone in context.object.pose.bones:
            if bone.name == self.bone_name:
                bone.bone.select = True
                context.object.data.bones.active = bone.bone
                break
    
        return {'FINISHED'}
    
class JointToCursor(bpy.types.Operator):
    bl_idname = "object.joint_to_cursor"
    bl_label = "Move joint to cursor"

    def execute(self, context):
        bpy.ops.view3d.snap_selected_to_cursor(use_offset=False)

        return {'FINISHED'}

class CreateArmature(bpy.types.Operator):
    bl_idname = "object.create_armature"
    bl_label = "Create an armature and associated link instances"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Check if the collection that stores instances exists and if not, create it
        instances_collection_found = False
        for collection in bpy.data.collections:
            if collection.collection_type == "InstancesCollection":
                instances_collection = collection
                instances_collection_found == True
                break

        if instances_collection_found == False:
            bpy.ops.collection.create(name=bpy.context.scene.name + "_instances_collection")
            instances_collection = bpy.data.collections[
                bpy.context.scene.name + "_instances_collection"
            ]
            if (
                instances_collection.name
                not in bpy.context.scene.collection.children.keys()
            ):
                bpy.context.scene.collection.children.link(instances_collection)
            instances_collection.collection_type = "InstancesCollection"
            # instances_collection.empty_display_size

        instances_collection_active = bpy.context.view_layer.layer_collection.children[instances_collection.name]
        context.view_layer.active_layer_collection = instances_collection_active

        # Check if armature exists and if not, create it
        armature_object_exists = False
        for obj in bpy.context.scene.objects:
            if obj.object_type == "ArmatureObject":
                armature_object_exists = True
                break
        if armature_object_exists == False:
            bpy.ops.object.armature_add()
            armature_object = bpy.context.active_object
            armature_object.name = bpy.context.scene.name + "_jointrig"

            # Set object type
            armature_object.object_type = "ArmatureObject"
            
            # Remove default bone
            bpy.ops.object.mode_set(mode='EDIT')
            armature_data = armature_object.data
            bpy.ops.armature.select_all(action='SELECT')
            bpy.ops.armature.delete()
            bpy.ops.object.mode_set(mode='OBJECT')
        
        all_collections = get_all_collections()
        for collection in bpy.context.scene.collection.children:
            # print(context.scene)
            if collection.collection_type == 'LinkCollection':
                # Create a collection instance for the link
                collection_name = collection.name
                instance_name = f"{collection_name}"
                bpy.ops.object.collection_instance_add(
                    collection=instance_name, 
                    name=instance_name,
                    location=(0.0, 0.0, 0.0), 
                    rotation=(0.0, 0.0, 0.0), 
                    scale=(1.0, 1.0, 1.0)
                )
                instance_object = bpy.data.objects[instance_name]
                instance_object.empty_display_size = 0.001

                # Set object type for instance
                instance_object.object_type = "LinkInstanceObject"

                # Add 'Child Of' constraint so the object can be parented
                bpy.ops.object.constraint_add(type="CHILD_OF")
                # Make target the armature
                for obj in context.scene.objects:
                    if obj.object_type == "ArmatureObject":
                        armature_object = obj
                instance_object.constraints["Child Of"].target = armature_object

                
                
        # Switch to POSE mode        
        armature_object = get_armature()
        bpy.context.view_layer.objects.active = armature_object
        bpy.ops.object.mode_set(mode='POSE')
        
        return {'FINISHED'}

class JointBoneProperties(bpy.types.PropertyGroup):
    bl_label = "Joint Properties"
    bl_idname = "JointObjectProperties"

    def joint_size_update(self, context):
        active_bone = bpy.context.active_pose_bone
        shape_scale = active_bone.custom_shape_scale_xyz
        shape_scale.x = active_bone.joint_grp.joint_size
        shape_scale.y = active_bone.joint_grp.joint_size
        shape_scale.z = active_bone.joint_grp.joint_size

    joint_size: bpy.props.FloatProperty(
        name="Joint Size",
        description="Adjusts the display size of the joint.",
        min=0,
        default=1.0,
        update=joint_size_update
    ) # type: ignore

    joint_type: bpy.props.EnumProperty(
        name="JointType",
        description="Type of joint",
        items=[
            ("NotJoint", "Not a Joint", "Object is not a joint."),
            ("FixedJoint", "Fixed Joint", "Object is a fixed joint."),
            ("RevoluteJoint", "Revolute Joint", "Object is a revolute joint."),
            ("ContinuousJoint", "Continuous Joint", "Object is a continuous joint."),
            ("PrismaticJoint", "Prismatic Joint", "Object is a prismatic joint."),
            ("PlanarJoint", "Planar Joint", "Object is a planar joint."),
            ("FloatingJoint", "Floating Joint", "Object is a floating joint."),
        ],
        default="NotJoint"
    ) # type: ignore

    joint_value: bpy.props.FloatProperty(
        name="Joint Value",
        description="Displays the joint value in the joint controller panel.",
        default=0.0,
        subtype='ANGLE'
    ) # type: ignore

    def update_angle(self, context):
        context.active_pose_bone.constraints['Limit Rotation'].min_y = context.active_pose_bone.joint_grp.revolute_min
        context.active_pose_bone.constraints['Limit Rotation'].max_y = context.active_pose_bone.joint_grp.revolute_max

    revolute_min: bpy.props.FloatProperty(
        name="Revolute Minimum",
        description="Lower limit of revolute joint.",
        default=(math.radians(-45.0)),
        subtype='ANGLE',
        precision=1,
        update=update_angle
    ) # type: ignore

    revolute_max: bpy.props.FloatProperty(
        name="Revolute Maximum",
        description="Upper limit of revolute joint.",
        default=(math.radians(45.0)),
        subtype='ANGLE',
        precision=1,
        update=update_angle
    ) # type: ignore

    def update_position(self, context):
        context.active_pose_bone.constraints['Limit Location'].min_y = context.active_pose_bone.joint_grp.prismatic_min
        context.active_pose_bone.constraints['Limit Location'].max_y = context.active_pose_bone.joint_grp.prismatic_max

    prismatic_min: bpy.props.FloatProperty(
        name="Prismatic Minimum",
        description="Lower limit of prismatic joint.",
        default=-0.2,
        max=0.0,
        subtype='DISTANCE',
        precision=4,
        update=update_position
    ) # type: ignore

    prismatic_max: bpy.props.FloatProperty(
        name="Prismatic Maximum",
        description="Upper limit of prismatic joint.",
        default=0.2,
        min=0.0,
        subtype='DISTANCE',
        precision=4,
        update=update_position
    ) # type: ignore
    
    child_link: bpy.props.StringProperty(
            name="Child Link",
            description="Child link.",
            default='None',
        ) # type: ignore

    def parent_link_update(self, context):
        # Define variables
        armature_object = get_armature()
        joint_selection = context.active_pose_bone
        parent_link = joint_selection.joint_grp.parent_link
        # parent_object = bpy.data.objects[parent_link]

        if parent_link == 'World':
            self.remove_empty_parents(context)
            parent_link = 'World'
        
        bpy.ops.object.mode_set(mode='EDIT')

        edit_bones = bpy.context.object.data.edit_bones

        # Get child bone
        child_bone = edit_bones.get(joint_selection.name)
        # Get parent bone
        edit_bone_name = bpy.data.objects[parent_link].constraints['Child Of'].subtarget
        parent_bone = edit_bones.get(edit_bone_name)

        child_bone.parent = parent_bone

        bpy.ops.object.mode_set(mode='POSE')

        self.sdf_parent_link = context.active_pose_bone.joint_grp.parent_link     

    def get_link_items_parent(self, context):
        link_items = []

        # Use parent_recursive to get all collections
        for obj in context.scene.objects:
            if bpy.context.object.mode == 'POSE':
                if getattr(obj, "object_type", "") == "LinkInstanceObject" and obj.name != context.active_pose_bone.joint_grp.child_link:
                    link_items.append((obj.instance_collection.name, obj.instance_collection.name, obj.instance_collection.name))
        
        link_items.insert(0, ('World', "World", "World"))
            
        return link_items

    parent_link: bpy.props.EnumProperty(
        name="Parent Link",
        description="Parent link.",
        items=get_link_items_parent,
        update=parent_link_update
    ) # type: ignore

    sdf_parent_link: bpy.props.StringProperty(
        name="SDF Parent Link",
        description="Parent link for SDF.",
        default="No Parent Link"
    ) # type: ignore

    revolute_continuous: bpy.props.BoolProperty(
        name="Continuous joint",
        description="Whether the joint is continuous or has limits.",
        default=False
    ) # type: ignore

    def remove_empty_parents(self, context):
        self.update_parent_flag = False
        armature_object = get_armature()
        parent_links = []
        bone_parents = []
        bpy.ops.object.mode_set(mode='EDIT')
        link_instance_objects = get_riginstance_objects()

        for pose_bone in armature_object.pose.bones:
            if pose_bone.joint_grp.parent_link != "" and pose_bone.joint_grp.parent_link != 'World':
                print("POSE BONE: " + pose_bone.joint_grp.parent_link)
                parent_links.append(pose_bone.joint_grp.parent_link)

        for obj in link_instance_objects:
            # print("OBJECT " + obj.name)
            child_of_subtarget = obj.constraints['Child Of'].subtarget
            # print("SUBTARGET " + child_of_subtarget)
            if child_of_subtarget not in parent_links and child_of_subtarget != "":
                print("CHILD OF SUBTARGET: " + child_of_subtarget)
                obj.constraints['Child Of'].subtarget = ""
                print("CHILD OF SUBTARGET DELETED: " + child_of_subtarget)
                bpy.data.armatures[armature_object.name].bones[child_of_subtarget].parent = None
        
        bpy.ops.object.mode_set(mode='POSE')

        set_inverse(self, context)