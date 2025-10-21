import bpy
import bmesh
import math
import numpy as np
from mathutils import Vector
from ..operators.utility import get_mesh_volume
from ..operators.colliders import (
    box_collider,
    sphere_collider,
    cylinder_collider,
    plane_collider,
    mesh_collider,
    move_to_collection,
    SetColliderMaterial,
    add_margin_modifier
)


class MagicColliderResult(bpy.types.PropertyGroup):
    """Store results of Magic Collider operation"""
    object_name: bpy.props.StringProperty(name="Object Name")  # type: ignore
    collider_type: bpy.props.StringProperty(name="Collider Type")  # type: ignore
    collider_axis: bpy.props.StringProperty(name="Axis", default="")  # type: ignore


class SDFG_OT_MagicCollider(bpy.types.Operator):
    """Automatically assign the best-fitting collider to each mesh object"""

    bl_idname = "mesh.magic_collider"
    bl_label = "Magic Collider"
    bl_options = {"REGISTER", "UNDO"}

    volume_threshold: bpy.props.FloatProperty(
        name="Volume Tolerance",
        description="Maximum acceptable volume difference ratio for primitive colliders",
        default=0.3,
        min=0.0,
        max=1.0,
    )  # type: ignore

    def execute(self, context):
        # Clear previous results
        context.scene.magic_collider_results.clear()

        # Get mesh objects - prioritize selected objects, otherwise use all
        selected_mesh_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if selected_mesh_objects:
            mesh_objects = selected_mesh_objects
        else:
            # If nothing selected, get all mesh objects in visual collections
            mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']

        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects found in the scene")
            return {'CANCELLED'}

        # Process each mesh object
        processed_count = 0
        skipped_count = 0
        for mesh_obj in mesh_objects:
            # Skip objects that are already colliders
            if "collider" in mesh_obj.name.lower():
                skipped_count += 1
                continue

            # Analyze mesh and assign best collider
            best_collider = self.find_best_collider(mesh_obj)

            if best_collider:
                self.assign_collider(mesh_obj, best_collider)

                # Store result for UI display
                result = context.scene.magic_collider_results.add()
                result.object_name = mesh_obj.name
                result.collider_type = best_collider['type']
                result.collider_axis = best_collider.get('axis', '')

                processed_count += 1

        if processed_count > 0:
            self.report({'INFO'}, f"Assigned colliders to {processed_count} objects")
        else:
            self.report({'WARNING'}, f"No colliders assigned. Skipped {skipped_count} objects (already colliders or invalid)")
        return {'FINISHED'}

    def find_best_collider(self, mesh_obj):
        """Analyze mesh and determine the best-fitting collider type"""

        # Get mesh geometric properties
        bbox_dims = self.get_bounding_box_dimensions(mesh_obj)
        mesh_volume = get_mesh_volume(mesh_obj)

        # Handle zero or very small volume
        if mesh_volume <= 0.0001:
            return {'type': 'Box', 'axis': 'Z', 'score': 0}

        # Compute geometric features
        flatness_ratio = self.compute_flatness_ratio(bbox_dims)
        aspect_ratios = self.compute_aspect_ratios(bbox_dims)
        cylindricality = self.compute_cylindricality(mesh_obj, bbox_dims)

        # Test candidate colliders
        candidates = []

        # 1. Plane collider (for very flat objects)
        if flatness_ratio > 10.0:  # Very flat
            plane_volume = self.estimate_plane_volume(bbox_dims)
            plane_diff = abs(mesh_volume - plane_volume) / mesh_volume if mesh_volume > 0 else float('inf')
            dominant_axis = self.get_smallest_dimension_axis(bbox_dims)
            candidates.append({
                'type': 'Plane',
                'axis': dominant_axis,
                'score': plane_diff,
                'volume_diff': plane_diff
            })

        # 2. Box collider
        box_volume = bbox_dims['x'] * bbox_dims['y'] * bbox_dims['z']
        box_diff = abs(mesh_volume - box_volume) / mesh_volume if mesh_volume > 0 else float('inf')
        candidates.append({
            'type': 'Box',
            'axis': 'Z',
            'score': box_diff,
            'volume_diff': box_diff
        })

        # 3. Sphere collider
        sphere_radius = max(bbox_dims['x'], bbox_dims['y'], bbox_dims['z']) / 2
        sphere_volume = (4/3) * math.pi * (sphere_radius ** 3)
        sphere_diff = abs(mesh_volume - sphere_volume) / mesh_volume if mesh_volume > 0 else float('inf')

        # Favor sphere for objects with similar dimensions in all axes
        sphericity_bonus = 0
        if max(aspect_ratios) < 1.5:  # Nearly cubic/spherical
            sphericity_bonus = -0.1  # Reduce score (better)

        candidates.append({
            'type': 'Sphere',
            'axis': 'Z',
            'score': sphere_diff + sphericity_bonus,
            'volume_diff': sphere_diff
        })

        # 4. Cylinder collider
        for axis in ['X', 'Y', 'Z']:
            cyl_volume, cyl_radius, cyl_height = self.estimate_cylinder_volume(bbox_dims, axis)
            cyl_diff = abs(mesh_volume - cyl_volume) / mesh_volume if mesh_volume > 0 else float('inf')

            # Apply cylindricality bonus
            cyl_score = cyl_diff
            if axis == 'Z' and cylindricality > 0.7:
                cyl_score -= 0.15  # Bonus for cylindrical shape

            candidates.append({
                'type': 'Cylinder',
                'axis': axis,
                'score': cyl_score,
                'volume_diff': cyl_diff
            })

        # Find best candidate
        best = min(candidates, key=lambda x: x['score'])

        # If all primitive fits are poor, fall back to convex hull (mesh collider)
        if best['volume_diff'] > self.volume_threshold:
            return {
                'type': 'Mesh',
                'axis': 'Z',
                'score': 0,
                'volume_diff': 0
            }

        return best

    def assign_collider(self, mesh_obj, collider_info):
        """Assign the chosen collider to the mesh object"""

        # Select only this object
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_obj

        # Create the appropriate collider
        collider_type = collider_info['type']
        axis = collider_info.get('axis', 'Z')

        try:
            if collider_type == 'Box':
                box_collider(mesh_obj)
            elif collider_type == 'Sphere':
                sphere_collider(mesh_obj)
            elif collider_type == 'Cylinder':
                cylinder_collider(axis, mesh_obj)
            elif collider_type == 'Plane':
                plane_collider(axis, mesh_obj)
            elif collider_type == 'Mesh':
                # Use moderate resolution for convex hull
                mesh_collider(mesh_obj, mesh_resolution=0.5, mesh_inflate=0.0)

            collider_obj = bpy.context.active_object

            # Move to appropriate collection
            move_to_collection(mesh_obj, collider_obj)

            # Set material and visibility
            SetColliderMaterial()

            # Rename collider
            bpy.context.active_object.name = (
                f"{mesh_obj.name}_collider_{collider_type}".lower().replace(".", "")
            )

            # Add margin modifier
            add_margin_modifier()

        except Exception as e:
            print(f"Error creating collider for {mesh_obj.name}: {e}")

    def get_bounding_box_dimensions(self, obj):
        """Get the dimensions of the object's bounding box in world space"""
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

        min_x = min(corner.x for corner in bbox_corners)
        max_x = max(corner.x for corner in bbox_corners)
        min_y = min(corner.y for corner in bbox_corners)
        max_y = max(corner.y for corner in bbox_corners)
        min_z = min(corner.z for corner in bbox_corners)
        max_z = max(corner.z for corner in bbox_corners)

        return {
            'x': max_x - min_x,
            'y': max_y - min_y,
            'z': max_z - min_z
        }

    def compute_flatness_ratio(self, bbox_dims):
        """Compute how flat the object is (ratio of largest to smallest dimension)"""
        dims = [bbox_dims['x'], bbox_dims['y'], bbox_dims['z']]
        dims.sort()

        if dims[0] < 0.0001:  # Very thin
            return 1000.0

        return dims[2] / dims[0]

    def compute_aspect_ratios(self, bbox_dims):
        """Compute aspect ratios between dimensions"""
        dims = [bbox_dims['x'], bbox_dims['y'], bbox_dims['z']]
        ratios = []

        for i in range(len(dims)):
            for j in range(i+1, len(dims)):
                if dims[j] > 0.0001:
                    ratios.append(max(dims[i], dims[j]) / min(dims[i], dims[j]))

        return ratios

    def compute_cylindricality(self, obj, bbox_dims):
        """
        Estimate how cylindrical the object is by checking if two dimensions
        are similar and one is different
        """
        dims = sorted([bbox_dims['x'], bbox_dims['y'], bbox_dims['z']])

        # Check if two smallest dimensions are similar (cylinder cross-section)
        if dims[1] > 0.0001:
            cross_section_similarity = min(dims[0], dims[1]) / max(dims[0], dims[1])
        else:
            cross_section_similarity = 0

        # Check if the largest dimension is different (cylinder height)
        if dims[1] > 0.0001:
            height_difference = dims[2] / dims[1]
        else:
            height_difference = 1

        # Cylindrical if cross-section is circular and height is different
        if cross_section_similarity > 0.8 and height_difference > 1.5:
            return 0.9
        elif cross_section_similarity > 0.7 and height_difference > 1.2:
            return 0.7
        else:
            return 0.3

    def get_smallest_dimension_axis(self, bbox_dims):
        """Return the axis with the smallest dimension (for plane colliders)"""
        dims = {
            'X': bbox_dims['x'],
            'Y': bbox_dims['y'],
            'Z': bbox_dims['z']
        }
        return min(dims, key=dims.get)

    def estimate_plane_volume(self, bbox_dims):
        """Estimate volume of a plane (very thin box)"""
        dims = sorted([bbox_dims['x'], bbox_dims['y'], bbox_dims['z']])
        # Use the two largest dimensions and a minimal thickness
        return dims[1] * dims[2] * (dims[0] if dims[0] > 0 else 0.001)

    def estimate_cylinder_volume(self, bbox_dims, axis):
        """Estimate cylinder volume based on bounding box and axis"""
        if axis == 'Z':
            radius = max(bbox_dims['x'], bbox_dims['y']) / 2
            height = bbox_dims['z']
        elif axis == 'Y':
            radius = max(bbox_dims['x'], bbox_dims['z']) / 2
            height = bbox_dims['y']
        else:  # X
            radius = max(bbox_dims['y'], bbox_dims['z']) / 2
            height = bbox_dims['x']

        volume = math.pi * (radius ** 2) * height
        return volume, radius, height
