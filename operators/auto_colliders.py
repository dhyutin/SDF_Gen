import bpy
import bmesh
import math
import numpy as np
import json
import os
import tempfile
import base64
import time
from pathlib import Path
from mathutils import Vector
import mathutils
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


def get_debug_images_dir():
    """Get path to debug images directory"""
    debug_dir = Path.home() / ".blender_llm_collider" / "debug_images"
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def get_env_file_path():
    """Get path to the .env file"""
    # Look for .env file in the addon directory
    addon_dir = Path(__file__).parent.parent
    return addon_dir / ".env"


def load_llm_config():
    """Load LLM configuration from .env file"""
    # Try to load .env file
    env_file = get_env_file_path()
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            print("python-dotenv not installed. Install with: pip install python-dotenv")
        except Exception as e:
            print(f"Error loading .env file: {e}")

    # Load from environment variables
    config = {
        'api_key': os.environ.get('AZURE_OPENAI_API_KEY', ''),
        'azure_endpoint': os.environ.get('AZURE_OPENAI_ENDPOINT', ''),
        'api_version': os.environ.get('AZURE_OPENAI_API_VERSION', '2024-08-01-preview'),
        'deployment_name': os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME', 'gpt-4o'),
    }
    return config


class MagicColliderResult(bpy.types.PropertyGroup):
    """Store results of Magic Collider operation"""
    object_name: bpy.props.StringProperty(name="Object Name")  # type: ignore
    collider_type: bpy.props.StringProperty(name="Collider Type")  # type: ignore
    collider_axis: bpy.props.StringProperty(name="Axis", default="")  # type: ignore
    llm_reasoning: bpy.props.StringProperty(name="LLM Reasoning", default="")  # type: ignore
    used_llm: bpy.props.BoolProperty(name="Used LLM", default=False)  # type: ignore
    llm_error: bpy.props.StringProperty(name="LLM Error", default="")  # type: ignore


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

    collider_margin: bpy.props.FloatProperty(
        name="Collider Margin",
        description="How much bigger colliders should be than the object (1.0 = exact fit, 1.1 = 10% bigger)",
        default=1.05,
        min=1.0,
        max=2.0,
    )  # type: ignore

    def is_simple_object(self, context, mesh_obj):
        """
        Detect if object is simple/small enough to skip refinement loop.
        Simple objects still get primitive colliders (Box/Cylinder), not mesh.

        Args:
            context: Blender context (to access scene properties)
            mesh_obj: The mesh object to check

        Returns:
            bool: True if object is simple and should skip refinement
        """
        try:
            # Get thresholds from scene properties
            volume_threshold = context.scene.simple_object_volume_threshold
            size_threshold = context.scene.simple_object_size_threshold

            # Check volume
            volume = get_mesh_volume(mesh_obj)
            if volume < volume_threshold:
                print(f"  Object '{mesh_obj.name}' is simple (volume={volume:.6f} < {volume_threshold}) - skipping refinement")
                return True

            # Check max dimension
            bbox_dims = self.get_bounding_box_dimensions(mesh_obj)
            max_dim = max(bbox_dims['x'], bbox_dims['y'], bbox_dims['z'])
            if max_dim < size_threshold:
                print(f"  Object '{mesh_obj.name}' is simple (max_dim={max_dim:.4f} < {size_threshold}) - skipping refinement")
                return True

            print(f"  Object '{mesh_obj.name}' is complex (volume={volume:.6f}, max_dim={max_dim:.4f}) - will use refinement")
            return False

        except Exception as e:
            print(f"  Warning: Could not determine if object is simple: {e}")
            return False  # Default to not simple (use refinement)

    def execute(self, context):
        # Start timing
        start_time = time.time()

        print("\n" + "="*80)
        print("MAGIC COLLIDER - STARTING")
        print("="*80)
        print(f"LLM Mode Enabled: {context.scene.use_llm_collider}")

        if context.scene.use_llm_collider:
            debug_dir = get_debug_images_dir()
            print(f"Debug images will be saved to: {debug_dir}")

        # Clear previous results
        context.scene.magic_collider_results.clear()

        # Get mesh objects - prioritize selected objects, otherwise use all
        selected_mesh_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if selected_mesh_objects:
            mesh_objects = selected_mesh_objects
            print(f"Processing {len(mesh_objects)} selected mesh object(s)")
        else:
            # If nothing selected, get all mesh objects in visual collections
            mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
            print(f"No selection - processing all {len(mesh_objects)} mesh object(s)")

        if not mesh_objects:
            elapsed_time = time.time() - start_time
            print("ERROR: No mesh objects found in the scene")
            print(f"\nTotal execution time: {elapsed_time:.2f} seconds")
            self.report({'WARNING'}, "No mesh objects found in the scene")
            return {'CANCELLED'}

        # Capture scene overview ONCE before processing all objects (performance optimization)
        scene_overview_base64 = None
        if context.scene.use_llm_collider and len(mesh_objects) > 0:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_dir = get_debug_images_dir()
            scene_overview_path = debug_dir / f"scene_overview_{timestamp}.png"

            print(f"\n{'='*80}")
            print(f"CAPTURING SHARED SCENE OVERVIEW (used for all {len(mesh_objects)} objects)")
            print(f"{'='*80}")
            print(f"  Saving to: {scene_overview_path}")

            if self.capture_scene_overview_image(context, mesh_objects[0], str(scene_overview_path)):
                scene_overview_base64 = self.encode_image_base64(str(scene_overview_path))
                if scene_overview_base64:
                    print(f"  ✓ Scene overview captured and encoded ({len(scene_overview_base64)} characters)")
                    print(f"  This image will be reused for all {len(mesh_objects)} objects")
                else:
                    print(f"  ✗ Failed to encode scene overview")
            else:
                print(f"  ✗ Failed to capture scene overview")

            print(f"{'='*80}\n")

        # Process each mesh object
        processed_count = 0
        skipped_count = 0
        llm_success_count = 0
        llm_fallback_count = 0

        for mesh_obj in mesh_objects:
            # Skip objects that are already colliders
            if "collider" in mesh_obj.name.lower():
                skipped_count += 1
                continue

            used_llm = False
            llm_reasoning = ""
            llm_error = ""

            # Try LLM-based recommendation if enabled
            if context.scene.use_llm_collider:
                llm_data, error = self.get_collider_recommendation_with_llm(context, mesh_obj, scene_overview_base64)

                if error:
                    # LLM failed, fall back to geometric method
                    print(f"LLM failed for {mesh_obj.name}: {error}")
                    llm_error = error
                    llm_fallback_count += 1
                    best_collider = self.find_best_collider(mesh_obj)
                    if best_collider:
                        self.assign_collider(mesh_obj, best_collider)
                        llm_reasoning = f"LLM failed ({error[:50]}...), using geometric fallback"

                        # Store result for UI display
                        result = context.scene.magic_collider_results.add()
                        result.object_name = mesh_obj.name
                        result.collider_type = best_collider['type']
                        result.collider_axis = best_collider.get('axis', '')
                        result.used_llm = False
                        result.llm_reasoning = llm_reasoning
                        result.llm_error = llm_error

                        processed_count += 1
                else:
                    # LLM succeeded - create compound collider with refinement loop
                    used_llm = True
                    llm_success_count += 1

                    # Check if LLM recommended a single collider - skip refinement entirely
                    colliders_info = llm_data.get('colliders', [])
                    is_single_collider = (
                        len(colliders_info) == 1 and
                        colliders_info[0].get('bounds', {}).get('start', 0.0) == 0.0 and
                        colliders_info[0].get('bounds', {}).get('end', 1.0) == 1.0
                    )

                    # Check if object is simple - skip refinement for performance
                    skip_refinement = is_single_collider or self.is_simple_object(context, mesh_obj)

                    if skip_refinement:
                        # Simple object or single collider - create colliders WITHOUT refinement loop
                        print(f"\n{'='*80}")
                        if is_single_collider:
                            print(f"SKIPPING REFINEMENT - SINGLE COLLIDER RECOMMENDED BY LLM")
                        else:
                            print(f"SKIPPING REFINEMENT FOR SIMPLE OBJECT (performance optimization)")
                        print(f"{'='*80}")

                        collider_objects = self.assign_compound_collider(context, mesh_obj, llm_data, self.collider_margin)

                        refinement_result = {
                            'success': True,
                            'iterations': 0,
                            'final_collider_count': len(collider_objects),
                            'refinement_performed': False,
                            'skipped_refinement': True
                        }
                    else:
                        # Complex object - use refinement loop with configured max iterations
                        max_iters = context.scene.max_refinement_iterations
                        print(f"  Complex object will use max {max_iters} refinement iteration(s)")
                        refinement_result = self.create_colliders_with_refinement(
                            context, mesh_obj, llm_data, self.collider_margin, max_iterations=max_iters
                        )

                    # Build reasoning summary
                    colliders_info = llm_data['colliders']
                    if len(colliders_info) == 1:
                        llm_reasoning = colliders_info[0].get('reasoning', 'No reasoning provided')
                    else:
                        llm_reasoning = f"Compound collider with {len(colliders_info)} parts"

                    # Add refinement info to reasoning
                    if refinement_result.get('success'):
                        iterations = refinement_result.get('iterations', 0)
                        if refinement_result.get('skipped_refinement'):
                            llm_reasoning += " (simple object - skipped refinement)"
                        elif refinement_result.get('refinement_performed'):
                            llm_reasoning += f" (refined over {iterations} iterations)"
                        elif refinement_result.get('rotation_applied'):
                            llm_reasoning += f" (rotation applied: {refinement_result['rotation_applied']:.1f}°)"

                    # Store result for UI display
                    result = context.scene.magic_collider_results.add()
                    result.object_name = mesh_obj.name
                    result.collider_type = f"Compound ({refinement_result.get('final_collider_count', len(colliders_info))})"
                    result.collider_axis = llm_data['decomposition_axis']
                    result.used_llm = True
                    result.llm_reasoning = llm_reasoning
                    result.llm_error = "" if refinement_result.get('success') else refinement_result.get('error', '')

                    processed_count += 1

            else:
                # LLM not enabled, use geometric method
                best_collider = self.find_best_collider(mesh_obj)
                if best_collider:
                    self.assign_collider(mesh_obj, best_collider)

                    # Store result for UI display
                    result = context.scene.magic_collider_results.add()
                    result.object_name = mesh_obj.name
                    result.collider_type = best_collider['type']
                    result.collider_axis = best_collider.get('axis', '')
                    result.used_llm = False
                    result.llm_reasoning = ""
                    result.llm_error = ""

                    processed_count += 1

        # Report results
        print("\n" + "="*80)
        print("MAGIC COLLIDER - SUMMARY")
        print("="*80)
        print(f"Total objects processed: {processed_count}")
        print(f"Objects skipped: {skipped_count}")

        if context.scene.use_llm_collider:
            print(f"LLM successful: {llm_success_count}")
            print(f"LLM fallback to geometric: {llm_fallback_count}")
            info_msg = f"Assigned colliders to {processed_count} objects. "
            if llm_success_count > 0:
                info_msg += f"LLM: {llm_success_count} successful"
            if llm_fallback_count > 0:
                info_msg += f", {llm_fallback_count} fallback to geometric"
            self.report({'INFO'}, info_msg)

            if llm_success_count > 0:
                debug_dir = get_debug_images_dir()
                print(f"\nDebug images saved to: {debug_dir}")
                print("Review these images to see what the LLM analyzed")
        else:
            print("LLM mode was disabled - used geometric calculation")
            if processed_count > 0:
                self.report({'INFO'}, f"Assigned colliders to {processed_count} objects")
            else:
                self.report({'WARNING'}, f"No colliders assigned. Skipped {skipped_count} objects (already colliders or invalid)")

        # Print total execution time
        elapsed_time = time.time() - start_time
        print(f"\n{'='*80}")
        print(f"TOTAL EXECUTION TIME: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
        print("="*80 + "\n")
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

    def calculate_mesh_dimensions_in_bounds(self, mesh_obj, decomp_axis_idx, bounds_start, bounds_end, local_bbox_min, local_bbox_max):
        """
        Calculate the actual bounding box dimensions of mesh vertices within a specific section.

        Args:
            mesh_obj: The mesh object
            decomp_axis_idx: Index of decomposition axis (0=X, 1=Y, 2=Z)
            bounds_start: Normalized start position (0.0 to 1.0)
            bounds_end: Normalized end position (0.0 to 1.0)
            local_bbox_min: Local space bounding box minimum
            local_bbox_max: Local space bounding box maximum

        Returns:
            Tuple of (min_coords, max_coords, center) in local space for the bounded section
        """
        try:
            # Calculate the actual axis range for this section
            axis_range = local_bbox_max[decomp_axis_idx] - local_bbox_min[decomp_axis_idx]
            section_min = local_bbox_min[decomp_axis_idx] + (axis_range * bounds_start)
            section_max = local_bbox_min[decomp_axis_idx] + (axis_range * bounds_end)

            # Get mesh data in LOCAL space
            bm = bmesh.new()
            bm.from_mesh(mesh_obj.data)
            # bm.transform(mesh_obj.matrix_world)  # REMOVED - work in local space

            # Filter vertices that are within the bounded section along decomposition axis
            vertices_in_section = []
            for vert in bm.verts:
                vert_pos = vert.co[decomp_axis_idx]
                if section_min <= vert_pos <= section_max:
                    vertices_in_section.append(vert.co.copy())

            bm.free()

            if not vertices_in_section:
                # No vertices in this section, fall back to full bbox
                print(f"  Warning: No vertices found in section [{bounds_start:.2f}, {bounds_end:.2f}], using full bbox")
                return local_bbox_min.copy(), local_bbox_max.copy(), (local_bbox_min + local_bbox_max) / 2.0

            # Calculate actual bounding box of vertices in this section
            section_min_coords = Vector((
                min(v.x for v in vertices_in_section),
                min(v.y for v in vertices_in_section),
                min(v.z for v in vertices_in_section)
            ))

            section_max_coords = Vector((
                max(v.x for v in vertices_in_section),
                max(v.y for v in vertices_in_section),
                max(v.z for v in vertices_in_section)
            ))

            section_center = (section_min_coords + section_max_coords) / 2.0

            return section_min_coords, section_max_coords, section_center

        except Exception as e:
            print(f"  Error calculating section dimensions: {e}")
            # Fall back to full bbox on error
            return local_bbox_min.copy(), local_bbox_max.copy(), (local_bbox_min + local_bbox_max) / 2.0

    def assign_compound_collider(self, context, mesh_obj, llm_data, margin=1.05):
        """
        Creates a set of primitive colliders based on the
        LLM's decomposition response.

        Args:
            context: Blender context
            mesh_obj: The mesh object to create colliders for
            llm_data: LLM decomposition data with colliders info
            margin: Scale factor for collider size (1.0 = exact fit, 1.05 = 5% bigger)

        Returns:
            list: List of created collider objects
        """
        try:
            print(f"\n{'='*80}")
            print(f"CREATING COMPOUND COLLIDER FOR: {mesh_obj.name}")
            print(f"{'='*80}")
            print(f"Collider Margin: {margin}x ({(margin-1)*100:.1f}% bigger than actual mesh)")

            # # 1. Get Overall Object Bounds (in world space)
            # bbox_corners = [mesh_obj.matrix_world @ Vector(corner) for corner in mesh_obj.bound_box]
            # world_bbox_min = Vector((min(c.x for c in bbox_corners), min(c.y for c in bbox_corners), min(c.z for c in bbox_corners)))
            # world_bbox_max = Vector((max(c.x for c in bbox_corners), max(c.y for c in bbox_corners), max(c.z for c in bbox_corners)))
            # world_bbox_dims = world_bbox_max - world_bbox_min
            # world_bbox_center = (world_bbox_min + world_bbox_max) / 2.0

            # print(f"Object bounding box:")
            # print(f"  Min: {world_bbox_min}")
            # print(f"  Max: {world_bbox_max}")
            # print(f"  Dimensions: {world_bbox_dims}")
            # print(f"  Center: {world_bbox_center}")

            # 1. Get Overall Object Bounds (in LOCAL space)
            local_bbox_corners = [Vector(corner) for corner in mesh_obj.bound_box]
            local_bbox_min = Vector((min(c.x for c in local_bbox_corners), min(c.y for c in local_bbox_corners), min(c.z for c in local_bbox_corners)))
            local_bbox_max = Vector((max(c.x for c in local_bbox_corners), max(c.y for c in local_bbox_corners), max(c.z for c in local_bbox_corners)))
            local_bbox_dims = local_bbox_max - local_bbox_min
            local_bbox_center = (local_bbox_min + local_bbox_max) / 2.0

            print(f"Object LOCAL bounding box:")
            print(f"  Min: {local_bbox_min}")
            print(f"  Max: {local_bbox_max}")
            print(f"  Dimensions: {local_bbox_dims}")
            print(f"  Center: {local_bbox_center}")
            
            # Store world bbox dims for the LLM fix (which uses axis_range)
            world_bbox_dims = local_bbox_dims

            # 2. Get Decomposition Info from LLM
            decomp_axis_str = llm_data['decomposition_axis']
            colliders_info = llm_data['colliders']

            print(f"\nDecomposition axis: {decomp_axis_str}")
            print(f"Number of colliders to create: {len(colliders_info)}")

            # Map 'X', 'Y', 'Z' to 0, 1, 2 for easy vector access
            axis_map = {'X': 0, 'Y': 1, 'Z': 2}
            decomp_axis_idx = axis_map[decomp_axis_str]
            other_axis_indices = [i for i in [0, 1, 2] if i != decomp_axis_idx]

            # 3. Create a Parent Empty
            empty_name = f"{mesh_obj.name}_collider_compound"
            parent_collider_obj = bpy.data.objects.new(empty_name, None)
            parent_collider_obj.location = mesh_obj.matrix_world.translation # Use object's precise world location
            parent_collider_obj.rotation_euler = mesh_obj.rotation_euler.copy()

            parent_collider_obj.empty_display_size = max(world_bbox_dims) / 2.0
            parent_collider_obj.empty_display_type = 'CUBE'
            context.scene.collection.objects.link(parent_collider_obj)  # Add to scene

            print(f"\nCreated parent empty: {parent_collider_obj.name}")
            print(f"  Parent location: {parent_collider_obj.location}")
            print(f"  Parent rotation: X={math.degrees(parent_collider_obj.rotation_euler.x):.2f}°, Y={math.degrees(parent_collider_obj.rotation_euler.y):.2f}°, Z={math.degrees(parent_collider_obj.rotation_euler.z):.2f}°")

            # 4. Loop Through Each Collider Part and Create It
            for i, info in enumerate(colliders_info):
                part_type = info['type'].title()  # Normalize to title case (Box, Capsule, etc.)
                part_axis_str = info.get('axis', decomp_axis_str)
                part_axis_idx = axis_map[part_axis_str]
                bounds = info['bounds']
                reasoning = info.get('reasoning', 'No reasoning provided')

                print(f"\n--- Creating collider part {i+1}/{len(colliders_info)} ---")
                print(f"  Type: {part_type}")
                print(f"  Axis: {part_axis_str}")
                print(f"  Bounds: {bounds['start']:.2f} - {bounds['end']:.2f}")
                print(f"  Reasoning: {reasoning}")

                # --- Calculate Position and Dimensions ---

                # Calculate actual mesh dimensions within this bounded section
                # section_min, section_max, section_center = self.calculate_mesh_dimensions_in_bounds(
                #     mesh_obj,
                #     decomp_axis_idx,
                #     bounds['start'],
                #     bounds['end'],
                #     world_bbox_min,
                #     world_bbox_max
                # )

                section_min, section_max, section_center = self.calculate_mesh_dimensions_in_bounds(
                    mesh_obj,
                    decomp_axis_idx,
                    bounds['start'],
                    bounds['end'],
                    local_bbox_min, # <-- FIX
                    local_bbox_max  # <-- FIX
                )

                # # Calculate actual dimensions of this section
                # section_dims = section_max - section_min

                # # Apply margin to all dimensions
                # part_dims = section_dims * margin

                # # Use the section center as the location
                # part_location = section_center

                # Calculate actual dimensions of this section
                section_dims = section_max - section_min

                # === FIX: START ===
                # The calculated section_dims can be 0.0 on the decomposition axis
                # if all found vertices are planar (e.g., Z-dim was 0.0 for part 2).
                #
                # We will OVERRIDE the dimension and location for the decomposition axis
                # using the LLM's bounds, but KEEP the calculated cross-section (other axes).

                # 1. Get the height/depth/width from LLM's normalized bounds
                axis_range = local_bbox_dims[decomp_axis_idx]
                llm_defined_dimension = axis_range * (bounds['end'] - bounds['start'])

                # 2. Get the center position from LLM's normalized bounds
                llm_defined_center_pos = local_bbox_min[decomp_axis_idx] + (axis_range * (bounds['start'] + bounds['end']) / 2.0)

                # 3. Create the final part dimensions
                # Start with the calculated dimensions (which are correct for the cross-section)
                final_part_dims = section_dims.copy()
                # Override the decomposition axis dimension with the one from the LLM
                final_part_dims[decomp_axis_idx] = llm_defined_dimension
                
                # 4. Create the final part location
                # Start with the calculated center (correct for the cross-section)
                final_part_location = section_center.copy()
                # Override the decomposition axis location with the one from the LLM
                final_part_location[decomp_axis_idx] = llm_defined_center_pos

                # 5. Apply margin
                part_dims = final_part_dims * margin
                
                # # 6. Use the new final location
                # part_location = final_part_location

                # 6. Use the new final location
                local_part_location = final_part_location # Renamed from part_location
                # === FIX: END ===
                # === FIX: END ===


                print(f"  Section actual dimensions (calculated): {section_dims}")
                # Add new logging to see the fix
                print(f"  LLM-defined dimension (axis {decomp_axis_str}): {llm_defined_dimension}")
                print(f"  Final part dimensions (with {margin}x margin): {part_dims}")
                print(f"  Final part location (local space): {local_part_location}")

                # --- Create the Primitive ---
                new_part = None

                if part_type == 'Box':
                    # Box needs no rotation
                    local_rotation = (0, 0, 0)

                    # Create box at origin with no rotation
                    bpy.ops.mesh.primitive_cube_add(
                        size=2.0,  # Default size
                        location=(0,0,0),
                        rotation=(0,0,0)
                    )
                    new_part = context.active_object
                    # Set exact dimensions (not scale)
                    new_part.dimensions = (part_dims.x, part_dims.y, part_dims.z)
                    # Ensure object is selected and apply scale to make it permanent
                    bpy.ops.object.select_all(action='DESELECT')
                    new_part.select_set(True)
                    context.view_layer.objects.active = new_part
                    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                    new_part.object_type = "ColliderObject"
                    new_part.collider_type = "BoxCollider"

                elif part_type == 'Cylinder':
                    # Determine radius and height based on axis
                    other_dims = [part_dims[idx] for idx in other_axis_indices]
                    radius = max(other_dims) / 2.0
                    height = part_dims[part_axis_idx]

                    # Store local rotation for later (after parenting)
                    local_rotation = (0, 0, 0)
                    if part_axis_str == 'X':
                        local_rotation = (0, math.radians(90), 0)
                    elif part_axis_str == 'Y':
                        local_rotation = (math.radians(90), 0, 0)
                    # Z is default, no rotation needed

                    # Create cylinder at origin with NO rotation (will rotate after parenting)
                    bpy.ops.mesh.primitive_cylinder_add(
                        radius=radius,
                        depth=height,
                        location=(0,0,0),
                        rotation=(0,0,0)  # No rotation during creation
                    )
                    new_part = context.active_object
                    new_part.object_type = "ColliderObject"
                    new_part.collider_type = "CylinderCollider"

                elif part_type == 'Sphere':
                    # Sphere needs no rotation (spherically symmetric)
                    local_rotation = (0, 0, 0)

                    # Use average of all dimensions for radius
                    radius = (part_dims.x + part_dims.y + part_dims.z) / 6.0
                    bpy.ops.mesh.primitive_uv_sphere_add(
                        radius=radius,
                        location=(0,0,0),
                    )
                    new_part = context.active_object
                    new_part.object_type = "ColliderObject"
                    new_part.collider_type = "SphereCollider"

                elif part_type == 'Plane':
                    # Store local rotation for later (after parenting)
                    local_rotation = (0, 0, 0)
                    if part_axis_str == 'X':
                        local_rotation = (math.radians(90), 0, 0)
                    elif part_axis_str == 'Y':
                        local_rotation = (0, math.radians(90), 0)
                    # Z is default, no rotation needed

                    # Create plane at origin with NO rotation (will rotate after parenting)
                    bpy.ops.mesh.primitive_plane_add(
                        size=2.0,  # Default size
                        location=(0,0,0),
                        rotation=(0,0,0)  # No rotation during creation
                    )
                    new_part = context.active_object
                    # Set exact dimensions
                    new_part.dimensions = (part_dims.x, part_dims.y, 0)
                    # Ensure object is selected and apply scale to make it permanent
                    bpy.ops.object.select_all(action='DESELECT')
                    new_part.select_set(True)
                    context.view_layer.objects.active = new_part
                    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                    new_part.object_type = "ColliderObject"
                    new_part.collider_type = "PlaneCollider"

                elif part_type == 'Mesh':
                    # For mesh colliders in compound, fall back to a box
                    # Box needs no rotation
                    local_rotation = (0, 0, 0)

                    print(f"  WARNING: Mesh colliders not fully supported in compound mode, using Box instead")
                    bpy.ops.mesh.primitive_cube_add(
                        size=2.0,
                        location=(0,0,0)
                    )
                    new_part = context.active_object
                    # Set exact dimensions
                    new_part.dimensions = (part_dims.x, part_dims.y, part_dims.z)
                    # Ensure object is selected and apply scale to make it permanent
                    bpy.ops.object.select_all(action='DESELECT')
                    new_part.select_set(True)
                    context.view_layer.objects.active = new_part
                    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                    new_part.object_type = "ColliderObject"
                    new_part.collider_type = "BoxCollider"

                if new_part:
                    # 5. Name, parent, and finalize the new part
                    new_part.name = f"{mesh_obj.name}_collider_part_{i}_{part_type}".lower().replace(".", "")

                    # # Parent to the empty while maintaining world transform
                    # # Store world matrix before parenting
                    # world_matrix = new_part.matrix_world.copy()
                    # new_part.parent = parent_collider_obj
                    # # Restore world position (converts to local coordinates relative to parent)
                    # new_part.matrix_world = world_matrix

                    # # Set material and visibility
                    # context.view_layer.objects.active = new_part
                    # SetColliderMaterial()
                    # add_margin_modifier()

                    # Parent to the empty FIRST
                    new_part.parent = parent_collider_obj

                    # NOW set its local location (which we calculated earlier)
                    new_part.location = local_part_location

                    # Set its local rotation (for axis alignment in parent's local space)
                    new_part.rotation_euler = local_rotation

                    print(f"  Applied local rotation: {local_rotation}")

                    # (The dimensions/scale were already set immediately after creation,
                    #  while the object was at (0,0,0) with no parent. This is correct.)

                    # Set material and visibility
                    context.view_layer.objects.active = new_part
                    SetColliderMaterial()
                    add_margin_modifier()

                    print(f"  Created: {new_part.name}")

            # 6. Apply transforms and unparent colliders
            print(f"\n{'='*80}")
            print(f"PROCESSING COLLIDERS")
            print(f"{'='*80}")

            collider_objects = []
            for i, info in enumerate(colliders_info):
                part_type = info['type'].title()  # Normalize to title case (Box, Capsule, etc.)
                part_name = f"{mesh_obj.name}_collider_part_{i}_{part_type}".lower().replace(".", "")

                if part_name in bpy.data.objects:
                    part_obj = bpy.data.objects[part_name]
                    collider_objects.append(part_obj)

                    print(f"\n--- Processing collider {i+1}/{len(colliders_info)}: {part_obj.name} ---")

                    # Select and make active
                    bpy.ops.object.select_all(action='DESELECT')
                    part_obj.select_set(True)
                    context.view_layer.objects.active = part_obj

                    # Apply all transforms (location, rotation, scale) to bake into mesh data
                    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
                    print(f"  Applied transforms to bake into mesh data")

                    # Set origin to center of mass (volume)
                    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME', center='MEDIAN')
                    print(f"  Set origin to center of mass (volume)")

                    # Clear parent but keep transform (now baked into mesh)
                    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

                    # Move to collection
                    move_to_collection(mesh_obj, part_obj)
                    print(f"  Moved to collection")

            # 7. Delete the parent empty (no longer needed)
            bpy.data.objects.remove(parent_collider_obj, do_unlink=True)

            print(f"\n{'='*80}")
            print(f"COMPOUND COLLIDER PARTS CREATED SUCCESSFULLY")
            print(f"  Parts: {len(colliders_info)} standalone colliders")
            print(f"{'='*80}\n")

            # Return the list of created collider objects
            return collider_objects

        except Exception as e:
            import traceback
            print(f"Error creating compound collider for {mesh_obj.name}: {e}")
            print(traceback.format_exc())
            return []

    def create_colliders_with_refinement(self, context, mesh_obj, initial_llm_data, margin=1.05, max_iterations=3):
        """
        Create colliders and iteratively refine them using LLM analysis.

        This method implements a refinement loop that:
        1. Creates initial colliders
        2. Asks orientation analyzer LLM to suggest size/shape improvements
        3. Asks fit analyzer LLM to suggest rotation adjustments
        4. Repeats until both analyzers are satisfied or max iterations reached

        Args:
            context: Blender context
            mesh_obj: The mesh object to create colliders for
            initial_llm_data: Initial LLM decomposition data
            margin: Scale factor for collider size
            max_iterations: Maximum number of refinement iterations

        Returns:
            dict: Summary of the refinement process with final state
        """
        try:
            print(f"\n{'='*80}")
            print(f"STARTING COLLIDER REFINEMENT LOOP")
            print(f"  Max iterations: {max_iterations}")
            print(f"{'='*80}")

            current_llm_data = initial_llm_data
            collider_objects = []
            iteration = 0

            # Track history of LLM decisions for context-aware refinement
            refinement_history = []  # List of orientation analysis results
            rotation_history = []    # List of rotation analysis results

            # Initialize refinement state
            needs_refinement = False
            refined_llm_data = None

            while iteration < max_iterations:
                iteration += 1
                print(f"\n{'='*80}")
                print(f"REFINEMENT ITERATION {iteration}/{max_iterations}")
                print(f"{'='*80}")

                # Only create colliders on first iteration OR if refinement changed the spec
                if iteration == 1 or (iteration > 1 and needs_refinement and refined_llm_data):
                    # Delete old colliders if rebuilding (not first iteration)
                    if collider_objects:
                        print(f"\nDeleting previous colliders for complete rebuild (spec changed)...")
                        try:
                            for collider_obj in collider_objects:
                                if collider_obj.name in bpy.data.objects:
                                    collider_name = collider_obj.name
                                    bpy.data.objects.remove(collider_obj, do_unlink=True)
                                    print(f"  Deleted {collider_name}")
                            collider_objects = []
                        except Exception as e:
                            print(f"\n{'='*80}")
                            print(f"ERROR DELETING OLD COLLIDERS")
                            print(f"{'='*80}")
                            print(f"  Iteration: {iteration}/{max_iterations}")
                            print(f"  Exception: {e}")
                            import traceback
                            print(traceback.format_exc())
                            print(f"{'='*80}\n")
                            collider_objects = []

                    # Create colliders with current specification
                    print(f"\nCreating colliders with current specification...")
                    collider_objects = self.assign_compound_collider(context, mesh_obj, current_llm_data, margin)
                else:
                    print(f"\nKeeping existing colliders, only analyzing fit...")

                if not collider_objects:
                    error_msg = f"Failed to create colliders in iteration {iteration}"
                    print(f"\n{'='*80}")
                    print(f"ERROR IN REFINEMENT LOOP")
                    print(f"{'='*80}")
                    print(f"  Iteration: {iteration}/{max_iterations}")
                    print(f"  Error: {error_msg}")
                    print(f"  Current LLM data:")
                    print(f"    Decomposition axis: {current_llm_data.get('decomposition_axis', 'N/A')}")
                    print(f"    Number of colliders: {len(current_llm_data.get('colliders', []))}")
                    for idx, col_info in enumerate(current_llm_data.get('colliders', [])):
                        print(f"    Collider {idx+1}: type={col_info.get('type', 'N/A')}, bounds={col_info.get('bounds', 'N/A')}")
                    print(f"{'='*80}\n")
                    return {
                        'success': False,
                        'iterations': iteration,
                        'error': error_msg
                    }

                # Analyze orientation/sizing (ask if size/shape should change)
                print(f"\n{'='*80}")
                print(f"LLM COLLIDER ORIENTATION ANALYSIS")
                print(f"{'='*80}")

                try:
                    refined_llm_data, needs_refinement = self.get_llm_collider_refinement(
                        context, mesh_obj, collider_objects, current_llm_data, refinement_history
                    )

                    # Record this refinement attempt in history
                    refinement_history.append({
                        'iteration': iteration,
                        'needs_refinement': needs_refinement,
                        'current_spec': current_llm_data,
                        'refined_spec': refined_llm_data if needs_refinement else None
                    })
                except Exception as e:
                    print(f"\n{'='*80}")
                    print(f"ERROR IN ORIENTATION ANALYSIS")
                    print(f"{'='*80}")
                    print(f"  Iteration: {iteration}/{max_iterations}")
                    print(f"  Exception: {e}")
                    import traceback
                    print(traceback.format_exc())
                    print(f"{'='*80}\n")
                    # Treat as satisfied to avoid infinite loop
                    refined_llm_data, needs_refinement = None, False

                # Analyze fit/rotation (ask if rotation is needed)
                print(f"\n{'='*80}")
                print(f"LLM COLLIDER FIT ANALYSIS")
                print(f"{'='*80}")

                try:
                    rotation_angle = self.get_llm_rotation_suggestion(
                        context, mesh_obj, collider_objects, rotation_history
                    )

                    # Record this rotation attempt in history
                    rotation_history.append({
                        'iteration': iteration,
                        'rotation_needed': rotation_angle is not None,
                        'angle_degrees': rotation_angle if rotation_angle is not None else 0
                    })
                except Exception as e:
                    print(f"\n{'='*80}")
                    print(f"ERROR IN FIT ANALYSIS")
                    print(f"{'='*80}")
                    print(f"  Iteration: {iteration}/{max_iterations}")
                    print(f"  Exception: {e}")
                    import traceback
                    print(traceback.format_exc())
                    print(f"{'='*80}\n")
                    # Treat as satisfied to avoid infinite loop
                    rotation_angle = None

                # Check if both analyzers are satisfied
                orientation_satisfied = not needs_refinement
                fit_satisfied = (rotation_angle is None)

                print(f"\n{'='*80}")
                print(f"ITERATION {iteration} RESULTS")
                print(f"{'='*80}")
                print(f"  Orientation analyzer: {'SATISFIED' if orientation_satisfied else 'NEEDS REFINEMENT'}")
                print(f"  Fit analyzer: {'SATISFIED' if fit_satisfied else f'NEEDS ROTATION ({rotation_angle:.2f}°)'}")

                # Apply rotation if needed
                if rotation_angle is not None:
                    print(f"\nApplying rotation: {rotation_angle:.2f}° around Z-axis...")
                    for collider_obj in collider_objects:
                        collider_obj.rotation_euler.z = math.radians(rotation_angle)
                    print(f"  Rotation applied to all {len(collider_objects)} colliders")

                # Check exit conditions
                if orientation_satisfied and fit_satisfied:
                    print(f"\n{'='*80}")
                    print(f"REFINEMENT COMPLETE - BOTH ANALYZERS SATISFIED")
                    print(f"  Total iterations: {iteration}")
                    print(f"  Final collider count: {len(collider_objects)}")
                    print(f"{'='*80}\n")
                    return {
                        'success': True,
                        'iterations': iteration,
                        'final_collider_count': len(collider_objects),
                        'rotation_applied': rotation_angle if rotation_angle is not None else 0,
                        'refinement_performed': iteration > 1
                    }

                # Prepare for next iteration
                if needs_refinement and refined_llm_data:
                    print(f"\n  → Will refine colliders in next iteration (shape/size changes)")
                    current_llm_data = refined_llm_data
                elif rotation_angle is not None:
                    # Rotation was applied - continue to next iteration to verify it worked
                    print(f"\n  → Rotation applied, continuing to next iteration to verify improvement")
                elif iteration >= max_iterations:
                    print(f"\n  → Max iterations reached, stopping")
                else:
                    # Both analyzers satisfied and no rotation applied - we're truly done
                    print(f"\n  → Both analyzers satisfied, no changes needed")

            # Max iterations reached
            print(f"\n{'='*80}")
            print(f"REFINEMENT STOPPED - MAX ITERATIONS REACHED")
            print(f"  Total iterations: {max_iterations}")
            print(f"  Final collider count: {len(collider_objects)}")
            print(f"{'='*80}\n")
            return {
                'success': True,
                'iterations': max_iterations,
                'final_collider_count': len(collider_objects),
                'max_iterations_reached': True
            }

        except Exception as e:
            import traceback
            print(f"ERROR in refinement loop: {e}")
            print(traceback.format_exc())
            return {
                'success': False,
                'iterations': iteration,
                'error': str(e)
            }

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

    def extract_object_features(self, mesh_obj):
        """
        Extract essential geometric information for LLM-based collider generation.

        Returns a dictionary containing only the features used by the LLM:
        - Dimensions (x, y, z, primary_axis)
        - Volume
        """

        print(f"\n{'='*80}")
        print(f"EXTRACTING FEATURES FOR: {mesh_obj.name}")
        print(f"{'='*80}")

        features = {}

        try:
            # Calculate bounding box dimensions
            bbox_corners = [mesh_obj.matrix_world @ Vector(corner) for corner in mesh_obj.bound_box]

            bbox_min = Vector((
                min(c.x for c in bbox_corners),
                min(c.y for c in bbox_corners),
                min(c.z for c in bbox_corners)
            ))
            bbox_max = Vector((
                max(c.x for c in bbox_corners),
                max(c.y for c in bbox_corners),
                max(c.z for c in bbox_corners)
            ))

            bbox_dims = {
                'x': bbox_max.x - bbox_min.x,
                'y': bbox_max.y - bbox_min.y,
                'z': bbox_max.z - bbox_min.z
            }

            # Determine primary axis (longest dimension)
            dims_dict = {'X': bbox_dims['x'], 'Y': bbox_dims['y'], 'Z': bbox_dims['z']}
            primary_axis = max(dims_dict, key=dims_dict.get)

            features['dimensions'] = {
                'x': bbox_dims['x'],
                'y': bbox_dims['y'],
                'z': bbox_dims['z'],
                'primary_axis': primary_axis
            }

            # Calculate volume (only feature from geometry needed by LLM)
            mesh_volume = get_mesh_volume(mesh_obj)

            features['geometry'] = {
                'volume': mesh_volume
            }

        except Exception as e:
            import traceback
            print(f"Error extracting features: {e}")
            print(traceback.format_exc())
            features['error'] = str(e)

        return features

    def capture_scene_overview_image(self, context, mesh_obj, image_path):
        """
        Capture a rendered image showing the entire scene with all objects visible.
        This provides context about the object's size and role in the overall assembly.

        Args:
            context: Blender context
            mesh_obj: The target mesh object (for camera framing)
            image_path: Path to save the image
        """
        try:
            print(f"  Rendering full scene overview...")
            import bpy_extras
            from bpy_extras.object_utils import world_to_camera_view

            # Store original selection and active object
            original_active = context.view_layer.objects.active
            original_selection = context.selected_objects[:]

            # Store original camera and render settings
            scene = context.scene
            original_camera = scene.camera
            original_resolution_x = scene.render.resolution_x
            original_resolution_y = scene.render.resolution_y
            original_filepath = scene.render.filepath
            original_film_transparent = scene.render.film_transparent

            # Get all mesh objects in the scene to calculate scene bounds
            all_mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH' and not "collider" in obj.name.lower()]

            if not all_mesh_objects:
                print(f"  Warning: No mesh objects found for scene overview")
                return False

            # Calculate scene bounding box
            all_corners = []
            for obj in all_mesh_objects:
                bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
                all_corners.extend(bbox_corners)

            scene_min = Vector((min(c.x for c in all_corners), min(c.y for c in all_corners), min(c.z for c in all_corners)))
            scene_max = Vector((max(c.x for c in all_corners), max(c.y for c in all_corners), max(c.z for c in all_corners)))
            scene_center = (scene_min + scene_max) / 2.0
            scene_size = (scene_max - scene_min).length

            # Create temporary camera
            bpy.ops.object.camera_add()
            camera = context.active_object
            scene.camera = camera

            # Position camera to frame entire scene at 45-degree angle
            camera_distance = scene_size * 1.5
            camera.location = scene_center + Vector((camera_distance * 0.7, -camera_distance * 0.7, camera_distance * 0.5))

            # Point camera at scene center
            direction = scene_center - camera.location
            rot_quat = direction.to_track_quat('-Z', 'Y')
            camera.rotation_euler = rot_quat.to_euler()

            # Create temporary lights
            lights = []

            # Key light
            bpy.ops.object.light_add(type='SUN')
            key_light = context.active_object
            key_light.location = camera.location
            light_direction = scene_center - camera.location
            light_rot_quat = light_direction.to_track_quat('-Z', 'Y')
            key_light.rotation_euler = light_rot_quat.to_euler()
            key_light.data.energy = 5.0
            lights.append(key_light)

            # Fill light
            bpy.ops.object.light_add(type='SUN')
            fill_light = context.active_object
            fill_light.location = camera.location + Vector((scene_size * 0.3, -scene_size * 0.2, scene_size * 0.2))
            fill_direction = scene_center - fill_light.location
            fill_rot_quat = fill_direction.to_track_quat('-Z', 'Y')
            fill_light.rotation_euler = fill_rot_quat.to_euler()
            fill_light.data.energy = 2.5
            lights.append(fill_light)

            # Set render resolution
            scene.render.resolution_x = 480
            scene.render.resolution_y = 480
            scene.render.film_transparent = False
            scene.render.filepath = image_path

            # Render the image (all objects visible)
            bpy.ops.render.render(write_still=True)

            print(f"  Scene overview image saved successfully")

            # Cleanup: restore original settings
            scene.camera = original_camera
            scene.render.resolution_x = original_resolution_x
            scene.render.resolution_y = original_resolution_y
            scene.render.filepath = original_filepath
            scene.render.film_transparent = original_film_transparent

            # Delete temporary camera and lights
            bpy.data.objects.remove(camera, do_unlink=True)
            for light in lights:
                bpy.data.objects.remove(light, do_unlink=True)

            # Restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            context.view_layer.objects.active = original_active

            return True

        except Exception as e:
            print(f"Error capturing scene overview: {e}")

            # Try to cleanup temporary objects even on error
            try:
                if 'camera' in locals() and camera:
                    bpy.data.objects.remove(camera, do_unlink=True)
                if 'lights' in locals():
                    for light in lights:
                        if light:
                            bpy.data.objects.remove(light, do_unlink=True)
            except:
                pass

            return False

    def capture_object_image(self, context, mesh_obj, image_path, rotation_angle=0):
        """
        Capture a clean rendered image of the object (all other objects hidden)

        Args:
            context: Blender context
            mesh_obj: The mesh object to capture
            image_path: Path to save the image
            rotation_angle: Rotation angle in degrees around Z axis (horizontal rotation)
        """
        try:
            print(f"  Rendering object (rotation: {rotation_angle}°)...")
            import bpy_extras
            from bpy_extras.object_utils import world_to_camera_view

            # Store original selection and active object
            original_active = context.view_layer.objects.active
            original_selection = context.selected_objects[:]

            # Store original rotation
            original_rotation = mesh_obj.rotation_euler.copy()

            # Store original camera and render settings
            scene = context.scene
            original_camera = scene.camera
            original_resolution_x = scene.render.resolution_x
            original_resolution_y = scene.render.resolution_y
            original_filepath = scene.render.filepath
            original_film_transparent = scene.render.film_transparent

            # Store original visibility state of all objects and hide them
            original_visibility = {}
            for obj in bpy.data.objects:
                original_visibility[obj.name] = obj.hide_render
                # Hide all objects except the target mesh
                if obj != mesh_obj:
                    obj.hide_render = True
                else:
                    obj.hide_render = False

            # Apply rotation to object (around Z axis for horizontal rotation)
            if rotation_angle != 0:
                mesh_obj.rotation_euler.z = original_rotation.z + math.radians(rotation_angle)

            # Create temporary camera
            bpy.ops.object.camera_add()
            camera = context.active_object
            scene.camera = camera

            # Position camera to frame the object
            # Get object bounds (after rotation)
            bbox_corners = [mesh_obj.matrix_world @ Vector(corner) for corner in mesh_obj.bound_box]
            obj_center = sum(bbox_corners, Vector()) / 8

            # Calculate object size
            bbox_dims = self.get_bounding_box_dimensions(mesh_obj)
            max_dim = max(bbox_dims['x'], bbox_dims['y'], bbox_dims['z'])

            # Position camera at 45-degree angle
            camera_distance = max_dim * 2.5
            camera.location = obj_center + Vector((camera_distance * 0.7, -camera_distance * 0.7, camera_distance * 0.5))

            # Point camera at object
            direction = obj_center - camera.location
            rot_quat = direction.to_track_quat('-Z', 'Y')
            camera.rotation_euler = rot_quat.to_euler()

            # Create temporary lights from camera direction for even illumination
            lights = []

            # Key light - positioned at camera location, pointing at object
            bpy.ops.object.light_add(type='SUN')
            key_light = context.active_object
            key_light.location = camera.location
            # Point the light at the object
            light_direction = obj_center - camera.location
            light_rot_quat = light_direction.to_track_quat('-Z', 'Y')
            key_light.rotation_euler = light_rot_quat.to_euler()
            key_light.data.energy = 5.0
            lights.append(key_light)

            # Fill light - slightly offset from camera for softer shadows
            bpy.ops.object.light_add(type='SUN')
            fill_light = context.active_object
            fill_light.location = camera.location + Vector((max_dim * 0.5, -max_dim * 0.3, max_dim * 0.3))
            fill_direction = obj_center - fill_light.location
            fill_rot_quat = fill_direction.to_track_quat('-Z', 'Y')
            fill_light.rotation_euler = fill_rot_quat.to_euler()
            fill_light.data.energy = 2.5
            lights.append(fill_light)

            # Set render resolution
            scene.render.resolution_x = 480
            scene.render.resolution_y = 480
            scene.render.film_transparent = False
            scene.render.filepath = image_path

            # Render the image
            bpy.ops.render.render(write_still=True)

            print(f"  Image saved successfully")

            # Cleanup: restore original settings
            scene.camera = original_camera
            scene.render.resolution_x = original_resolution_x
            scene.render.resolution_y = original_resolution_y
            scene.render.filepath = original_filepath
            scene.render.film_transparent = original_film_transparent

            # Restore original visibility state of all objects
            for obj_name, visibility in original_visibility.items():
                if obj_name in bpy.data.objects:
                    bpy.data.objects[obj_name].hide_render = visibility

            # Restore original rotation
            mesh_obj.rotation_euler = original_rotation

            # Delete temporary camera and lights
            bpy.data.objects.remove(camera, do_unlink=True)
            for light in lights:
                bpy.data.objects.remove(light, do_unlink=True)

            # Restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            context.view_layer.objects.active = original_active

            return True

        except Exception as e:
            print(f"Error capturing image for {mesh_obj.name}: {e}")

            # Try to restore visibility even on error
            try:
                if 'original_visibility' in locals():
                    for obj_name, visibility in original_visibility.items():
                        if obj_name in bpy.data.objects:
                            bpy.data.objects[obj_name].hide_render = visibility
            except:
                pass

            # Try to restore rotation even on error
            try:
                if 'original_rotation' in locals():
                    mesh_obj.rotation_euler = original_rotation
            except:
                pass

            # Try to cleanup temporary objects even on error
            try:
                if 'camera' in locals() and camera:
                    bpy.data.objects.remove(camera, do_unlink=True)
                if 'lights' in locals():
                    for light in lights:
                        if light:
                            bpy.data.objects.remove(light, do_unlink=True)
            except:
                pass

            return False

    def encode_image_base64(self, image_path):
        """Encode image to base64 for API transmission"""
        try:
            with open(image_path, 'rb') as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error encoding image: {e}")
            return None

    def call_llm_api_classification(self, context, images_base64):
        """
        First LLM call: Classify if object needs single or multiple colliders.

        Args:
            context: Blender context
            images_base64: List of base64-encoded images:
                          [0] = Scene overview (all objects)
                          [1-3] = Selected object views (0°, 120°, 240°)

        Returns:
        - For single collider: {"needs_multiple": false, "collider_type": "Box|Sphere|Cylinder|Plane"}
        - For multiple colliders: {"needs_multiple": true}
        """
        try:
            from openai import AzureOpenAI

            # Load config from .env file
            config = load_llm_config()

            # Validate required fields
            if not config['api_key']:
                error_msg = "No API key provided. Set AZURE_OPENAI_API_KEY in .env file."
                return None, error_msg
            if not config['azure_endpoint']:
                error_msg = "No Azure endpoint provided. Set AZURE_OPENAI_ENDPOINT in .env file."
                return None, error_msg


            print(f"  Sending {len(images_base64)} images (1 scene overview + 3 object views)")

            # Prepare the classification prompt
            prompt_text = """TASK: Determine if this 3D object needs ONE collider or MULTIPLE colliders.

IMAGES PROVIDED:
- Image 1: Full scene showing all objects (provides context - object's size and role)
- Images 2-4: The selected object isolated, rotated at 0°, 120°, 240°

CONTEXT - ROBOTICS APPLICATIONS:
This tool is used for robotics applications including:
- Robot arms and manipulators
- Grippers and end effectors
- Humanoid robots
- Vehicles (cars, forklifts, trucks, AGVs)
- Industrial machinery and equipment

WHAT ARE COLLIDERS?
Collision shapes for physics - they approximate the object's outer boundary for collision detection. They don't need to be perfect, just wrap the object reasonably.

PREFERRED COLLIDER TYPES (in order of preference):
1. Box: For rectangular/cubic parts, gripper bodies, robot links, vehicle chassis
2. Cylinder: For cylindrical shafts, tubes, wheels, joints, robot links

AVOID UNLESS ABSOLUTELY NECESSARY:
- Sphere: Only for truly spherical objects (balls, spherical joints)
- Plane: Only for extremely flat surfaces (rarely needed)

DECISION CRITERIA:
SINGLE collider → Simple, uniform shapes:
  - Box: Rectangular robot links, gripper bodies, vehicle chassis, brackets
  - Cylinder: Cylindrical shafts, wheels, tubes, cylindrical robot links
  - Small components (screws, nuts, bolts, washers, pins, rivets)

MULTIPLE colliders → Complex non-uniform shapes:
  - Robot arms with varying cross-sections
  - Grippers with distinct body and finger sections
  - L-shapes, T-shapes, H-beams
  - Tools, wrenches, complex mechanical parts
  - Objects with distinct sections that vary significantly in cross-section

IMPORTANT GUIDELINES:
- Small fasteners and hardware should ALWAYS use a SINGLE Box or Cylinder collider
- Robot link bodies: prefer Box or Cylinder based on cross-section
- Gripper bodies: prefer Box or Cylinder
- Look at Image 1 to understand the object's relative size and role in the assembly
- Only use MULTIPLE colliders for larger objects with genuinely complex geometry
- Default to Box or Cylinder - avoid Sphere and Plane unless the geometry clearly demands it

OUTPUT (JSON only):
Single collider:
{
  "needs_multiple": false,
  "collider_type": "Box|Cylinder",
  "reasoning": "Brief explanation"
}

Multiple colliders:
{
  "needs_multiple": true,
  "reasoning": "Brief explanation"
}

Return ONLY JSON."""

            # Initialize Azure OpenAI client
            client = AzureOpenAI(
                azure_endpoint=config['azure_endpoint'],
                api_key=config['api_key'],
                api_version=config['api_version'],
            )

            # Build message content with text and all 3 images
            message_content = [
                {
                    "type": "text",
                    "text": prompt_text
                }
            ]

            # Add all images to the message
            for i, img_base64 in enumerate(images_base64):
                message_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}"
                    }
                })

            # Call the API with all images
            response = client.chat.completions.create(
                model=config['deployment_name'],
                messages=[
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                temperature=1,
                max_completion_tokens=500,
            )

            llm_response = response.choices[0].message.content

            # Print token usage
            if hasattr(response, 'usage') and response.usage:
                print(f"\n=== TOKEN USAGE (Classification Call) ===")
                print(f"Prompt tokens: {response.usage.prompt_tokens}")
                print(f"Completion tokens: {response.usage.completion_tokens}")
                print(f"Total tokens: {response.usage.total_tokens}")
                print(f"=========================================\n")

            print(f"Classification Response: {llm_response}")

            # Validate response
            if not llm_response or len(llm_response.strip()) == 0:
                error_msg = "LLM returned empty response for classification"
                return None, error_msg

            return llm_response, None

        except ImportError as e:
            error_msg = f"Import Error: {str(e)}"
            return None, error_msg
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            return None, error_msg

    def call_llm_api_decomposition(self, context, images_base64, features_json):
        """
        Second LLM call: Decompose object into multiple tight-fitting colliders.

        Args:
            context: Blender context
            images_base64: List of base64-encoded images:
                          [0] = Scene overview (all objects)
                          [1-3] = Selected object views (0°, 120°, 240°)
            features_json: Extracted geometric features of the object

        This call receives the images AND the extracted features JSON to provide
        detailed geometric information for creating compound colliders.
        """
        try:
            from openai import AzureOpenAI

            # Load config from .env file
            config = load_llm_config()

            # Validate required fields
            if not config['api_key']:
                error_msg = "No API key provided. Set AZURE_OPENAI_API_KEY in .env file."
                return None, error_msg
            if not config['azure_endpoint']:
                error_msg = "No Azure endpoint provided. Set AZURE_OPENAI_ENDPOINT in .env file."
                return None, error_msg


            print(f"  Sending {len(images_base64)} images (1 scene overview + 3 object views)")

            # Get basic metadata from features
            primary_axis = features_json['dimensions']['primary_axis']
            dimensions = features_json['dimensions']

            # Prepare the decomposition prompt
            prompt_text = f"""TASK: Decompose this 3D object into multiple primitive collision shapes (colliders) for robotics applications.

IMAGES PROVIDED:
- Image 1: Full scene showing all objects (context - object's size and role)
- Images 2-4: The selected object isolated, rotated at 0°, 120°, 240°

CONTEXT - ROBOTICS APPLICATIONS:
This tool is used for robotics applications including:
- Robot arms and manipulators (links, joints, actuators)
- Grippers and end effectors (body, fingers, palm)
- Humanoid robots (torso, limbs, head)
- Vehicles (cars, forklifts, trucks, AGVs)
- Industrial machinery and equipment

WHAT ARE COLLIDERS?
Approximate shapes for physics collision detection. They wrap the object's OUTER BOUNDARY for path planning, collision avoidance, and physics simulation.

CRITICAL REQUIREMENTS:
1. Colliders must COMPLETELY CONTAIN the object - no parts can stick out
2. Colliders should be TIGHT-FITTING - minimize empty space while ensuring full coverage
3. Better to have slightly oversized colliders than ones that don't fully contain the object

OBJECT DATA:
- Dimensions: X={dimensions['x']:.3f}, Y={dimensions['y']:.3f}, Z={dimensions['z']:.3f}
- Primary Axis: {primary_axis} (longest: {dimensions[primary_axis.lower()]:.3f} units)
- Volume: {features_json['geometry']['volume']:.3f}

PREFERRED COLLIDER TYPES (in order of preference):
1. Box: For rectangular/cubic sections - robot links, gripper bodies/fingers, vehicle chassis, brackets
2. Cylinder: For cylindrical sections - shafts, tubes, wheels, joints, cylindrical robot links

AVOID UNLESS ABSOLUTELY NECESSARY:
- Sphere: Only for truly spherical end caps or joints (very rare)
- Plane: Only for extremely flat surfaces (almost never needed)

ROBOTICS-SPECIFIC GUIDELINES:
- Robot link bodies: Use Box for rectangular cross-sections, Cylinder for circular cross-sections
- Gripper bodies: Typically Box or Cylinder
- Gripper fingers: Almost always Box (even if slightly curved)
- Joints/actuators: Box or Cylinder based on shape
- Vehicle chassis/body: Box
- Wheels: Cylinder
- Default to Box or Cylinder - avoid Sphere and Plane unless geometry absolutely requires it

YOUR TASK:
1. Choose decomposition axis (typically {primary_axis} - the longest dimension)
2. Divide object into distinct geometric sections along that axis
3. Assign Box or Cylinder to each section (avoid Sphere/Plane unless critical)
4. Set bounds (0.0-1.0) for each section's position along the axis

EXAMPLES:

Robot arm link:
{{
  "decomposition_axis": "Z",
  "colliders": [
    {{"type": "Cylinder", "axis": "Z", "bounds": {{"start": 0.0, "end": 0.2}}, "reasoning": "Bottom joint housing - cylindrical"}},
    {{"type": "Box", "axis": "Z", "bounds": {{"start": 0.2, "end": 0.8}}, "reasoning": "Main link body - rectangular cross-section"}},
    {{"type": "Cylinder", "axis": "Z", "bounds": {{"start": 0.8, "end": 1.0}}, "reasoning": "Top joint housing - cylindrical"}}
  ]
}}

Gripper:
{{
  "decomposition_axis": "Y",
  "colliders": [
    {{"type": "Box", "axis": "Y", "bounds": {{"start": 0.0, "end": 0.4}}, "reasoning": "Gripper body/palm - rectangular"}},
    {{"type": "Box", "axis": "Y", "bounds": {{"start": 0.4, "end": 1.0}}, "reasoning": "Finger section - rectangular"}}
  ]
}}

L-bracket:
{{
  "decomposition_axis": "Z",
  "colliders": [
    {{"type": "Box", "axis": "Z", "bounds": {{"start": 0.0, "end": 1.0}}, "reasoning": "Vertical part - rectangular"}},
    {{"type": "Box", "axis": "X", "bounds": {{"start": 0.0, "end": 0.3}}, "reasoning": "Horizontal base - rectangular"}}
  ]
}}

OUTPUT (JSON only):
{{
  "decomposition_axis": "X|Y|Z",
  "colliders": [
    {{"type": "Box|Cylinder", "axis": "X|Y|Z", "bounds": {{"start": 0.0, "end": 1.0}}, "reasoning": "Brief description"}},
    ...
  ]
}}

IMPORTANT: Prefer Box and Cylinder. Only use Sphere or Plane if the geometry absolutely requires it.

Return ONLY JSON."""

            # Initialize Azure OpenAI client
            client = AzureOpenAI(
                azure_endpoint=config['azure_endpoint'],
                api_key=config['api_key'],
                api_version=config['api_version'],
            )

            # Build message content with text and all 3 images
            message_content = [
                {
                    "type": "text",
                    "text": prompt_text
                }
            ]

            # Add all images to the message
            for i, img_base64 in enumerate(images_base64):
                message_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}"
                    }
                })

            # Call the API with all images and features
            response = client.chat.completions.create(
                model=config['deployment_name'],
                messages=[
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                temperature=1,
                max_completion_tokens=1500,
            )

            llm_response = response.choices[0].message.content

            # Print token usage
            if hasattr(response, 'usage') and response.usage:
                print(f"\n=== TOKEN USAGE (Decomposition Call) ===")
                print(f"Prompt tokens: {response.usage.prompt_tokens}")
                print(f"Completion tokens: {response.usage.completion_tokens}")
                print(f"Total tokens: {response.usage.total_tokens}")
                print(f"==========================================\n")

            print(f"Decomposition Response: {llm_response}")

            # Validate response
            if not llm_response or len(llm_response.strip()) == 0:
                error_msg = "LLM returned empty response for decomposition"
                return None, error_msg

            return llm_response, None

        except ImportError as e:
            error_msg = f"Import Error: {str(e)}"
            return None, error_msg
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            return None, error_msg

    def parse_classification_response(self, llm_response):
        """Parse and validate classification JSON response"""
        try:
            # Extract JSON from response (LLM might include markdown code blocks)
            response_text = llm_response.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            elif response_text.startswith('```'):
                response_text = response_text[3:]

            if response_text.endswith('```'):
                response_text = response_text[:-3]

            response_text = response_text.strip()

            # Parse JSON
            classification_data = json.loads(response_text)

            # Validate response structure
            if not isinstance(classification_data, dict):
                return None, "Classification response is not a JSON object"

            if 'needs_multiple' not in classification_data:
                return None, "Classification response missing 'needs_multiple' field"

            needs_multiple = classification_data['needs_multiple']

            # If single collider, validate collider_type
            if not needs_multiple:
                if 'collider_type' not in classification_data:
                    return None, "Single collider classification missing 'collider_type' field"

                # Allow all types but prefer Box/Cylinder (validation still permits Sphere/Plane)
                valid_types = {'Box', 'Sphere', 'Cylinder', 'Plane'}
                if classification_data['collider_type'] not in valid_types:
                    return None, f"Invalid collider type: {classification_data['collider_type']}"

            return classification_data, None

        except json.JSONDecodeError as e:
            return None, f"Invalid JSON in classification response: {str(e)}\nOriginal output: {llm_response}"
        except Exception as e:
            return None, f"Error parsing classification response: {str(e)}\nOriginal output: {llm_response}"

    def parse_llm_response(self, llm_response):
        """Parse and validate decomposition LLM JSON response"""
        try:
            # Extract JSON from response (LLM might include markdown code blocks)
            response_text = llm_response.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            elif response_text.startswith('```'):
                response_text = response_text[3:]

            if response_text.endswith('```'):
                response_text = response_text[:-3]

            response_text = response_text.strip()

            # Parse JSON
            llm_data = json.loads(response_text)

            # Validate response structure - should be an object with decomposition_axis and colliders
            if not isinstance(llm_data, dict):
                return None, "LLM response is not a JSON object"

            if 'decomposition_axis' not in llm_data:
                return None, "LLM response missing 'decomposition_axis' field"

            if 'colliders' not in llm_data:
                return None, "LLM response missing 'colliders' field"

            # Validate decomposition_axis
            valid_axes = {'X', 'Y', 'Z'}
            decomp_axis = llm_data['decomposition_axis']
            if decomp_axis not in valid_axes:
                return None, f"Invalid decomposition_axis: {decomp_axis}"

            # Validate colliders array
            colliders = llm_data['colliders']
            if not isinstance(colliders, list):
                return None, "LLM 'colliders' field is not a list"

            if len(colliders) == 0:
                return None, "LLM returned empty collider list"

            # Validate each collider
            valid_types = {'Box', 'Sphere', 'Cylinder', 'Plane', 'Mesh'}

            for collider in colliders:
                if 'type' not in collider:
                    return None, "Collider missing 'type' field"

                if collider['type'] not in valid_types:
                    return None, f"Invalid collider type: {collider['type']}"

                # Validate axis
                if 'axis' not in collider:
                    collider['axis'] = decomp_axis  # Default to decomposition axis
                elif collider['axis'] not in valid_axes:
                    return None, f"Invalid axis: {collider['axis']}"

                # Validate bounds
                if 'bounds' not in collider:
                    return None, "Collider missing 'bounds' field"

                bounds = collider['bounds']
                if not isinstance(bounds, dict):
                    return None, "Collider 'bounds' field is not an object"

                if 'start' not in bounds or 'end' not in bounds:
                    return None, "Collider bounds missing 'start' or 'end' field"

                # Validate bounds values
                try:
                    start = float(bounds['start'])
                    end = float(bounds['end'])
                    if start < 0.0 or start > 1.0:
                        return None, f"Bounds start value {start} is not in range [0.0, 1.0]"
                    if end < 0.0 or end > 1.0:
                        return None, f"Bounds end value {end} is not in range [0.0, 1.0]"
                    if start >= end:
                        return None, f"Bounds start {start} must be less than end {end}"
                except (ValueError, TypeError):
                    return None, "Bounds start/end values must be numbers"

                # Ensure reasoning exists
                if 'reasoning' not in collider:
                    collider['reasoning'] = "No reasoning provided"

            return llm_data, None

        except json.JSONDecodeError as e:
            return None, f"Invalid JSON in LLM response: {str(e)}\nOriginal output: {llm_response}"
        except Exception as e:
            return None, f"Error parsing LLM response: {str(e)}\nOriginal output: {llm_response}"

    def capture_scene_with_colliders(self, context, mesh_obj, collider_objects, camera_angle="SIDE"):
        """
        Capture an image of the mesh object WITH its colliders visible.

        Args:
            context: Blender context
            mesh_obj: The mesh object
            collider_objects: List of collider objects to show
            camera_angle: "SIDE1", "SIDE2", or "TOP"

        Returns:
            str: Path to the captured image, or None if failed
        """
        try:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_dir = get_debug_images_dir()
            safe_obj_name = "".join(c for c in mesh_obj.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            image_path = debug_dir / f"{safe_obj_name}_{timestamp}_{camera_angle}.png"

            print(f"  Capturing {camera_angle} view to: {image_path}")

            # Store original settings
            scene = context.scene
            original_camera = scene.camera
            original_resolution_x = scene.render.resolution_x
            original_resolution_y = scene.render.resolution_y
            original_filepath = scene.render.filepath
            original_film_transparent = scene.render.film_transparent

            # Store original visibility
            original_visibility = {}
            for obj in bpy.data.objects:
                original_visibility[obj.name] = obj.hide_render

            # Make ONLY the mesh object and colliders visible
            for obj in bpy.data.objects:
                if obj == mesh_obj or obj in collider_objects:
                    obj.hide_render = False
                else:
                    obj.hide_render = True

            # Create temporary camera
            bpy.ops.object.camera_add()
            camera = context.active_object
            scene.camera = camera

            # Get object bounds (including colliders)
            all_objects = [mesh_obj] + collider_objects
            bbox_corners = []
            for obj in all_objects:
                bbox_corners.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])

            obj_center = sum(bbox_corners, Vector()) / len(bbox_corners)

            # Calculate bbox dimensions
            bbox_min = Vector((min(c.x for c in bbox_corners), min(c.y for c in bbox_corners), min(c.z for c in bbox_corners)))
            bbox_max = Vector((max(c.x for c in bbox_corners), max(c.y for c in bbox_corners), max(c.z for c in bbox_corners)))
            bbox_dims = bbox_max - bbox_min
            max_dim = max(bbox_dims.x, bbox_dims.y, bbox_dims.z)

            # Set camera position based on angle
            camera_distance = max_dim * 2.5

            if camera_angle == "SIDE1":
                # Side view from +X looking at -X
                camera.location = obj_center + Vector((camera_distance, 0, 0))
                camera.rotation_euler = (math.radians(90), 0, math.radians(90))
            elif camera_angle == "SIDE2":
                # Side view from +Y looking at -Y
                camera.location = obj_center + Vector((0, camera_distance, 0))
                camera.rotation_euler = (math.radians(90), 0, math.radians(180))
            elif camera_angle == "TOP":
                # Top view from +Z looking down
                camera.location = obj_center + Vector((0, 0, camera_distance))
                camera.rotation_euler = (0, 0, 0)

            camera.data.lens = 50

            # Add lights
            lights = []
            for i, angle in enumerate([0, 120, 240]):
                bpy.ops.object.light_add(type='SUN')
                light = context.active_object
                light.data.energy = 2.0
                light.rotation_euler = (math.radians(45), 0, math.radians(angle))
                lights.append(light)

            # Set render settings
            scene.render.resolution_x = 480
            scene.render.resolution_y = 480
            scene.render.filepath = str(image_path)
            scene.render.film_transparent = True

            # Render
            bpy.ops.render.render(write_still=True)

            # Cleanup
            scene.camera = original_camera
            scene.render.resolution_x = original_resolution_x
            scene.render.resolution_y = original_resolution_y
            scene.render.filepath = original_filepath
            scene.render.film_transparent = original_film_transparent

            # Restore visibility
            for obj_name, visibility in original_visibility.items():
                if obj_name in bpy.data.objects:
                    bpy.data.objects[obj_name].hide_render = visibility

            # Delete camera and lights
            bpy.data.objects.remove(camera, do_unlink=True)
            for light in lights:
                bpy.data.objects.remove(light, do_unlink=True)

            print(f"  Image captured successfully")
            return str(image_path)

        except Exception as e:
            print(f"  Error capturing {camera_angle} view: {e}")
            return None

    def get_llm_rotation_suggestion(self, context, mesh_obj, collider_objects, rotation_history):
        """
        Ask LLM to analyze the fit between colliders and object, and suggest a Z-axis rotation angle.

        Args:
            context: Blender context
            mesh_obj: The mesh object
            collider_objects: List of collider objects
            rotation_history: List of previous rotation attempts (for context)

        Returns:
            float: Rotation angle in degrees, or None if no rotation needed
        """
        try:
            from openai import AzureOpenAI

            # Capture 2 views: 1 side view + 1 top view (optimized for rotation analysis)
            print(f"\nCapturing 2 views with colliders (top + side for rotation analysis)...")
            image_paths = []

            # Capture side view
            side_path = self.capture_scene_with_colliders(context, mesh_obj, collider_objects, "SIDE1")
            if side_path:
                image_paths.append(side_path)

            # Capture top view (most important for rotation)
            top_path = self.capture_scene_with_colliders(context, mesh_obj, collider_objects, "TOP")
            if top_path:
                image_paths.append(top_path)

            if len(image_paths) < 2:
                print(f"  ERROR: Could not capture required views")
                return None

            print(f"  Captured 2 views successfully (side + top)")

            # Encode images to base64
            images_base64 = []
            for img_path in image_paths:
                img_b64 = self.encode_image_base64(img_path)
                if img_b64:
                    images_base64.append(img_b64)

            if len(images_base64) < 2:
                print(f"  ERROR: Could not encode all images")
                return None

            # Load config
            config = load_llm_config()

            if not config['api_key'] or not config['azure_endpoint']:
                print(f"  ERROR: Azure OpenAI config missing")
                return None

            # Build history context if available
            history_context = ""
            if rotation_history:
                history_context = "\n\nPREVIOUS ROTATION ATTEMPTS:\n"
                for idx, hist in enumerate(rotation_history):
                    history_context += f"Iteration {hist['iteration']}: "
                    if hist['rotation_needed']:
                        history_context += f"Applied {hist['angle_degrees']:.1f}° rotation\n"
                    else:
                        history_context += "No rotation applied\n"

            # Prepare prompt
            prompt_text = f"""You are analyzing collision detection boxes (purple) for a robotics object.

# YOUR TASK
Determine if the purple colliders need horizontal rotation to better align with the object.

# IMAGES
- Image 1: Side view
- Image 2: Top view (MOST IMPORTANT - check horizontal alignment here)

# ANALYSIS CRITERIA
1. Do colliders completely contain the object? (no parts sticking out)
2. Are colliders aligned with object's orientation? (check top view)
3. Would rotation reduce empty space while maintaining full coverage?{history_context}

# REQUIRED OUTPUT FORMAT
You MUST respond with ONLY a JSON object in one of these two formats:

If rotation is needed:
{{
  "rotation_needed": true,
  "angle_degrees": 30.0,
  "reasoning": "Brief explanation"
}}

If rotation is NOT needed:
{{
  "rotation_needed": false,
  "reasoning": "Brief explanation"
}}

IMPORTANT:
- angle_degrees: -180 to 180 (positive = counter-clockwise in top view)
- Only suggest rotation if it SIGNIFICANTLY improves fit
- Respond with ONLY the JSON object, no other text"""

            # Initialize client
            client = AzureOpenAI(
                azure_endpoint=config['azure_endpoint'],
                api_key=config['api_key'],
                api_version=config['api_version'],
            )

            # Build message content
            message_content = [{"type": "text", "text": prompt_text}]

            for img_b64 in images_base64:
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                })

            # Call LLM
            print(f"\nCalling LLM for rotation analysis...")
            response = client.chat.completions.create(
                model=config['deployment_name'],
                messages=[{"role": "user", "content": message_content}],
                temperature=1,
                max_completion_tokens=500,
            )

            llm_response = response.choices[0].message.content

            # Print token usage
            if hasattr(response, 'usage') and response.usage:
                print(f"\n=== TOKEN USAGE (Rotation Analysis) ===")
                print(f"Prompt tokens: {response.usage.prompt_tokens}")
                print(f"Completion tokens: {response.usage.completion_tokens}")
                print(f"Total tokens: {response.usage.total_tokens}")
                print(f"========================================\n")

            print(f"LLM Response: {llm_response}")

            # Parse response
            import re
            json_match = re.search(r'\{[^{}]*\}', llm_response, re.DOTALL)
            if not json_match:
                print(f"  ERROR: Could not find JSON in response. Original LLM output:")
                print(f"  {llm_response}")
                return None

            result = json.loads(json_match.group(0))

            if result.get('rotation_needed', False):
                angle = result.get('angle_degrees', 0)
                reasoning = result.get('reasoning', 'No reasoning provided')
                print(f"\n  LLM Analysis: Rotation needed")
                print(f"  Suggested angle: {angle:.2f}°")
                print(f"  Reasoning: {reasoning}")
                return float(angle)
            else:
                reasoning = result.get('reasoning', 'Good fit')
                print(f"\n  LLM Analysis: No rotation needed")
                print(f"  Reasoning: {reasoning}")
                return None

        except Exception as e:
            print(f"  ERROR in LLM rotation analysis: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_llm_collider_refinement(self, context, mesh_obj, collider_objects, current_llm_data, refinement_history):
        """
        Ask LLM to analyze the collider fit and suggest size/shape improvements.

        Args:
            context: Blender context
            mesh_obj: The mesh object
            collider_objects: List of current collider objects
            current_llm_data: The current collider specification that was used
            refinement_history: List of previous refinement attempts (for context)

        Returns:
            tuple: (refined_llm_data, needs_refinement)
                   refined_llm_data: New collider specification in same format, or None
                   needs_refinement: Boolean indicating if refinement is needed
        """
        try:
            from openai import AzureOpenAI

            # Capture 3 views: 2 side profiles + 1 top view
            print(f"\nCapturing 3 views with colliders for orientation analysis...")
            image_paths = []

            side1_path = self.capture_scene_with_colliders(context, mesh_obj, collider_objects, "SIDE1")
            if side1_path:
                image_paths.append(side1_path)

            side2_path = self.capture_scene_with_colliders(context, mesh_obj, collider_objects, "SIDE2")
            if side2_path:
                image_paths.append(side2_path)

            top_path = self.capture_scene_with_colliders(context, mesh_obj, collider_objects, "TOP")
            if top_path:
                image_paths.append(top_path)

            if len(image_paths) < 3:
                print(f"  ERROR: Could not capture all 3 views")
                return None, False

            print(f"  Captured 3 views successfully")

            # Encode images to base64
            images_base64 = []
            for img_path in image_paths:
                img_b64 = self.encode_image_base64(img_path)
                if img_b64:
                    images_base64.append(img_b64)

            if len(images_base64) < 3:
                print(f"  ERROR: Could not encode all images")
                return None, False

            # Load config
            config = load_llm_config()

            if not config['api_key'] or not config['azure_endpoint']:
                print(f"  ERROR: Azure OpenAI config missing")
                return None, False

            # Build history context if available
            history_context = ""
            if refinement_history:
                history_context = "\n\nPREVIOUS REFINEMENT ATTEMPTS:\n"
                for idx, hist in enumerate(refinement_history):
                    history_context += f"Iteration {hist['iteration']}: "
                    if hist['needs_refinement']:
                        history_context += f"Refinement requested - {len(hist.get('refined_spec', {}).get('colliders', []))} colliders\n"
                    else:
                        history_context += "No refinement needed\n"

            # Build current specification summary
            current_spec_summary = f"""
CURRENT COLLIDER SPECIFICATION:
Decomposition Axis: {current_llm_data.get('decomposition_axis', 'N/A')}
Number of Colliders: {len(current_llm_data.get('colliders', []))}
"""
            for idx, col in enumerate(current_llm_data.get('colliders', [])):
                current_spec_summary += f"  Part {idx+1}: {col.get('type', 'N/A')} along {col.get('axis', 'N/A')}, bounds {col.get('bounds', {}).get('start', 0):.2f}-{col.get('bounds', {}).get('end', 1):.2f}\n"

            # Prepare prompt
            prompt_text = f"""You are analyzing collision detection boxes (purple) for a robotics object.

# YOUR TASK
Determine if the current collider specification needs refinement. Check if colliders properly contain the object with good fit.

# IMAGES
- Image 1: Side view 1
- Image 2: Side view 2
- Image 3: Top view

{current_spec_summary}{history_context}

# ANALYSIS CRITERIA
1. CRITICAL: Do colliders completely contain the object? (no parts sticking out)
2. Are colliders tight-fitting? (not excessively larger than needed)
3. Would different shapes (Box/Cylinder) or segmentation improve fit?
4. Do bounds (segment positions) need adjustment?

# ROBOTICS GUIDELINES
- Prefer Box for: rectangular robot links, gripper fingers, chassis
- Prefer Cylinder for: cylindrical shafts, joints, wheels
- Avoid Sphere and Plane unless absolutely necessary
- Small gaps are acceptable; parts sticking out are NOT

# REQUIRED OUTPUT FORMAT
You MUST respond with ONLY a JSON object in one of these two formats:

If refinement IS needed:
{{
  "needs_refinement": true,
  "decomposition_axis": "X",
  "colliders": [
    {{
      "type": "Box",
      "axis": "X",
      "bounds": {{"start": 0.0, "end": 0.5}},
      "reasoning": "Why this collider"
    }},
    {{
      "type": "Cylinder",
      "axis": "X",
      "bounds": {{"start": 0.5, "end": 1.0}},
      "reasoning": "Why this collider"
    }}
  ],
  "refinement_reasoning": "What was improved"
}}

If refinement is NOT needed:
{{
  "needs_refinement": false,
  "reasoning": "Why current colliders are acceptable"
}}

IMPORTANT:
- decomposition_axis: X, Y, or Z
- type: Box or Cylinder (avoid Sphere/Plane)
- axis: X, Y, or Z (for Cylinder orientation)
- bounds: start and end values between 0.0 and 1.0
- Only refine if fit is SIGNIFICANTLY poor
- Respond with ONLY the JSON object, no other text"""

            # Initialize client
            client = AzureOpenAI(
                azure_endpoint=config['azure_endpoint'],
                api_key=config['api_key'],
                api_version=config['api_version'],
            )

            # Build message content
            message_content = [{"type": "text", "text": prompt_text}]

            for img_b64 in images_base64:
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                })

            # Call LLM
            print(f"\nCalling LLM for collider orientation analysis...")
            response = client.chat.completions.create(
                model=config['deployment_name'],
                messages=[{"role": "user", "content": message_content}],
                temperature=1,
                max_completion_tokens=1000,
            )

            llm_response = response.choices[0].message.content

            # Print token usage
            if hasattr(response, 'usage') and response.usage:
                print(f"\n=== TOKEN USAGE (Orientation Analysis) ===")
                print(f"Prompt tokens: {response.usage.prompt_tokens}")
                print(f"Completion tokens: {response.usage.completion_tokens}")
                print(f"Total tokens: {response.usage.total_tokens}")
                print(f"===========================================\n")

            print(f"LLM Response: {llm_response}")

            # Parse response
            import re
            json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            if not json_match:
                print(f"  ERROR: Could not find JSON in response. Original LLM output:")
                print(f"  {llm_response}")
                return None, False

            result = json.loads(json_match.group(0))

            if result.get('needs_refinement', False):
                refinement_reasoning = result.get('refinement_reasoning', 'No reasoning provided')
                print(f"\n  LLM Analysis: Refinement needed")
                print(f"  Reasoning: {refinement_reasoning}")
                print(f"  New decomposition axis: {result.get('decomposition_axis')}")
                print(f"  New collider count: {len(result.get('colliders', []))}")

                # Return refined collider data in same format as initial LLM
                refined_data = {
                    'decomposition_axis': result['decomposition_axis'],
                    'colliders': result['colliders']
                }
                return refined_data, True
            else:
                reasoning = result.get('reasoning', 'Colliders fit well')
                print(f"\n  LLM Analysis: No refinement needed")
                print(f"  Reasoning: {reasoning}")
                return None, False

        except Exception as e:
            print(f"  ERROR in LLM orientation analysis: {e}")
            import traceback
            traceback.print_exc()
            return None, False

    def get_collider_recommendation_with_llm(self, context, mesh_obj, scene_overview_base64=None):
        """
        Get collider recommendation using two-stage LLM approach.

        Stage 1: Classification - Determine if single or multiple colliders needed
        Stage 2: Decomposition - If multiple, create tight-fitting compound collider

        Args:
            context: Blender context
            mesh_obj: Mesh object to process
            scene_overview_base64: Optional pre-captured scene overview image (performance optimization)
        """
        debug_image_path = None

        try:
            print("\n" + "="*80)
            print(f"PROCESSING OBJECT: {mesh_obj.name}")
            print("="*80)

            # ===== EXTRACT ALL OBJECT FEATURES =====
            features = self.extract_object_features(mesh_obj)

            # Print features in structured dictionary format
            print("\n" + "="*80)
            print("EXTRACTED OBJECT FEATURES (STRUCTURED DICTIONARY)")
            print("="*80)
            print(json.dumps(features, indent=2))
            print("="*80 + "\n")

            # Capture images:
            # 1. Full scene overview (context - shows all objects) - REUSE if provided
            # 2-4. Selected object at different rotations (0°, 120°, 240°)
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_dir = get_debug_images_dir()
            safe_obj_name = "".join(c for c in mesh_obj.name if c.isalnum() or c in (' ', '-', '_')).rstrip()

            image_paths = []
            images_base64 = []

            # Use provided scene overview or capture new one
            if scene_overview_base64:
                print(f"\n✓ Reusing shared scene overview (performance optimization)")
                images_base64.append(scene_overview_base64)
            else:
                # Capture scene overview (fallback for single object processing)
                print(f"\nCapturing scene overview (provides context about object's role)...")
                scene_overview_path = debug_dir / f"{safe_obj_name}_{timestamp}_scene_overview.png"
                print(f"\n  Scene Overview: Capturing to: {scene_overview_path}")

                if not self.capture_scene_overview_image(context, mesh_obj, str(scene_overview_path)):
                    error_msg = "Failed to capture scene overview image"
                    print(f"  ERROR: {error_msg}")
                    return None, error_msg

                print(f"  Scene overview saved successfully")
                image_paths.append(scene_overview_path)

                # Encode scene overview to base64
                scene_overview_base64 = self.encode_image_base64(str(scene_overview_path))
                if not scene_overview_base64:
                    error_msg = "Failed to encode scene overview image"
                    print(f"  ERROR: {error_msg}")
                    return None, error_msg

                print(f"  Scene overview encoded to base64 ({len(scene_overview_base64)} characters)")
                images_base64.append(scene_overview_base64)

            # Capture 3 object views at different rotations (Images 2-4)
            rotation_angles = [0, 120, 240]
            print(f"\nCapturing {len(rotation_angles)} views of selected object at different rotations...")

            for i, angle in enumerate(rotation_angles):
                debug_image_path = debug_dir / f"{safe_obj_name}_{timestamp}_object_view{i+1}_{angle}deg.png"
                print(f"\n  Object View {i+1}: Capturing at {angle}° rotation to: {debug_image_path}")

                if not self.capture_object_image(context, mesh_obj, str(debug_image_path), rotation_angle=angle):
                    error_msg = f"Failed to capture object image at {angle}° rotation"
                    print(f"  ERROR: {error_msg}")
                    return None, error_msg

                print(f"  Image saved successfully")
                image_paths.append(debug_image_path)

                # Encode image to base64
                image_base64 = self.encode_image_base64(str(debug_image_path))
                if not image_base64:
                    error_msg = f"Failed to encode image at {angle}° rotation"
                    print(f"  ERROR: {error_msg}")
                    return None, error_msg

                print(f"  Image encoded to base64 ({len(image_base64)} characters)")
                images_base64.append(image_base64)

            print(f"\n✓ Successfully captured and encoded {len(images_base64)} images total")
            print(f"  - 1 scene overview + {len(rotation_angles)} object views")
            print(f"  Images saved to: {debug_dir}")

            # ===== STAGE 1: CLASSIFICATION =====
            print("\n" + "="*80)
            print("STAGE 1: CLASSIFICATION")
            print("="*80)

            classification_response, error = self.call_llm_api_classification(context, images_base64)

            if error:
                print(f"Classification LLM API call failed for {mesh_obj.name}")
                return None, error

            # Parse classification response
            classification_data, parse_error = self.parse_classification_response(classification_response)

            if parse_error:
                print(f"ERROR parsing classification response: {parse_error}")
                print(f"Raw classification response: {classification_response}")
                return None, parse_error

            needs_multiple = classification_data['needs_multiple']
            print(f"\nClassification Result:")
            print(f"  Needs Multiple Colliders: {needs_multiple}")
            if not needs_multiple:
                print(f"  Recommended Single Collider: {classification_data['collider_type']}")
            print(f"  Reasoning: {classification_data.get('reasoning', 'N/A')}")

            # ===== HANDLE SINGLE COLLIDER =====
            if not needs_multiple:
                print("\n" + "="*80)
                print("CREATING SINGLE COLLIDER")
                print("="*80)

                collider_type = classification_data['collider_type']

                # Determine axis for cylinder/plane
                primary_axis = features['dimensions']['primary_axis']

                # Create single collider data in compound format for consistency
                single_collider_data = {
                    'decomposition_axis': primary_axis,
                    'colliders': [
                        {
                            'type': collider_type,
                            'axis': primary_axis,
                            'bounds': {'start': 0.0, 'end': 1.0},
                            'reasoning': classification_data.get('reasoning', f'Single {collider_type} collider recommended by LLM')
                        }
                    ]
                }

                print(f"Single collider configuration:")
                print(json.dumps(single_collider_data, indent=2))

                return single_collider_data, None

            # ===== STAGE 2: DECOMPOSITION (Multiple Colliders) =====
            print("\n" + "="*80)
            print("STAGE 2: DECOMPOSITION (Multiple Colliders)")
            print("="*80)

            decomposition_response, error = self.call_llm_api_decomposition(context, images_base64, features)

            if error:
                print(f"Decomposition LLM API call failed for {mesh_obj.name}")
                return None, error

            # Parse decomposition response
            colliders_data, parse_error = self.parse_llm_response(decomposition_response)

            if parse_error:
                print(f"ERROR parsing decomposition response: {parse_error}")
                print(f"Raw decomposition response: {decomposition_response}")
                return None, parse_error

            print(f"\nSuccessfully parsed compound collider with {len(colliders_data['colliders'])} parts")
            print(f"Decomposition axis: {colliders_data['decomposition_axis']}")

            # Print each collider
            for i, collider in enumerate(colliders_data['colliders']):
                print(f"\n  Collider {i+1}:")
                print(f"    Type: {collider['type']}")
                print(f"    Axis: {collider['axis']}")
                print(f"    Bounds: {collider['bounds']['start']:.2f} - {collider['bounds']['end']:.2f}")
                print(f"    Reasoning: {collider.get('reasoning', 'N/A')}")

            return colliders_data, None

        except Exception as e:
            import traceback
            error_msg = f"Error in LLM recommendation: {str(e)}"
            print(f"\nERROR: {error_msg}")
            print(f"Exception Type: {type(e).__name__}")
            print("\nFull Traceback:")
            print(traceback.format_exc())
            print("="*80 + "\n")
            return None, error_msg
