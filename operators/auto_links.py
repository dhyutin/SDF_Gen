"""
Automated Link Generation using Azure OpenAI

This module analyzes a Blender scene and automatically generates link collections
based on object hierarchy, naming conventions, transforms, and relationships.
Uses Azure OpenAI to intelligently group objects into links.
"""

import bpy
import json
from datetime import datetime
from mathutils import Vector
from .connect_azure import get_azure_client, get_deployment_name
from .general_functions import show_message_box


# Blender Text Logger Class
class BlenderTextLogger:
    """Logger that writes to a Blender text datablock"""

    def __init__(self, text_name="Auto-Link Log"):
        self.text_name = text_name
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs = []

        # Create or get text datablock
        if text_name in bpy.data.texts:
            self.text_block = bpy.data.texts[text_name]
            self.text_block.clear()
        else:
            self.text_block = bpy.data.texts.new(text_name)

        # Write header
        self.info("=" * 80)
        self.info(f"AUTO-LINK GENERATION LOG - {self.timestamp}")
        self.info("=" * 80)
        self.info("")

    def _write(self, level, message):
        """Write a log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {level}: {message}"
        self.logs.append(log_line)
        self.text_block.write(log_line + "\n")

    def info(self, message):
        """Log info message"""
        self._write("INFO", message)

    def warning(self, message):
        """Log warning message"""
        self._write("WARN", message)

    def error(self, message):
        """Log error message"""
        self._write("ERROR", message)

    def debug(self, message):
        """Log debug message"""
        self._write("DEBUG", message)

    def separator(self, char="=", length=60):
        """Add a separator line"""
        self.text_block.write(char * length + "\n")

    def section(self, title):
        """Start a new section"""
        self.info("")
        self.separator("=", 60)
        self.info(title)
        self.separator("=", 60)

    def show_in_editor(self):
        """Open the log in Blender's text editor"""
        # Find or create a text editor area
        text_editor_found = False

        for area in bpy.context.screen.areas:
            if area.type == 'TEXT_EDITOR':
                area.spaces[0].text = self.text_block
                text_editor_found = True
                break

        if not text_editor_found:
            # Try to split the current area to show text editor
            try:
                # Get the current area
                for area in bpy.context.screen.areas:
                    if area.type == 'VIEW_3D':
                        # Store original area type
                        original_type = area.type
                        # Change to text editor temporarily
                        area.type = 'TEXT_EDITOR'
                        area.spaces[0].text = self.text_block
                        break
            except:
                pass

# Initialize logger
logger = None


def update_viewport_to_camera():
    """
    Update the 3D viewport to show the current camera view.
    This provides visual feedback to the user about what angle is being captured.
    """
    import time

    try:
        # Find the 3D viewport area
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    # Set to camera view
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.region_3d.view_perspective = 'CAMERA'

                    # Force viewport update/redraw
                    area.tag_redraw()

                    # Process events to show the update immediately
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

                    # Brief pause so user can see the angle (0.3 seconds)
                    time.sleep(0.3)
                    return
    except Exception as e:
        # Non-critical - if viewport update fails, continue anyway
        pass


def get_optimal_viewing_angles(initial_image_path, scene_bounds):
    """
    Use AI to determine optimal viewing angles based on initial image.

    Args:
        initial_image_path (str): Path to first captured image
        scene_bounds (dict): Scene bounding box info

    Returns:
        list: List of angle specifications (azimuth, elevation)
    """
    global logger
    import base64
    import os

    try:
        if logger:
            logger.info("Analyzing initial image to determine optimal viewing angles...")

        client = get_azure_client()
        deployment = get_deployment_name()

        if not client or not deployment:
            # Fallback to default angles
            return [(90, 0), (180, 0), (270, 30)]

        # Encode initial image
        with open(initial_image_path, "rb") as img_file:
            encoded_image = base64.b64encode(img_file.read()).decode('utf-8')

        angle_prompt = """You are an expert in 3D visualization and mechanical analysis.

I've captured an initial view of a 3D mechanical model. Based on this image, determine the BEST additional camera angles to fully understand the mechanism's structure.

INITIAL VIEW: Front view (0° azimuth, 0° elevation)

TASK: Suggest 3-4 additional viewing angles that would provide the most information about:
1. Hidden joint connections
2. Rear/back components
3. Underside or top structures
4. Symmetric elements (left/right)
5. Complex geometric features

Respond with JSON containing angle suggestions:
{
  "suggested_angles": [
    {"azimuth": 90, "elevation": 0, "reason": "view right side and side joints"},
    {"azimuth": 180, "elevation": 15, "reason": "view rear components with slight elevation"},
    {"azimuth": 270, "elevation": -15, "reason": "view left side from below"}
  ],
  "analysis": "brief description of what's visible and what's hidden"
}

Azimuth: 0-360° (0=front, 90=right, 180=back, 270=left)
Elevation: -45 to 45° (negative=below, positive=above)
"""

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You are an expert in 3D visualization and camera positioning."},
                {"role": "user", "content": [
                    {"type": "text", "text": angle_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_image}"}}
                ]}
            ],
            max_completion_tokens=2000
        )

        result = response.choices[0].message.content

        # Parse JSON
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()

        angle_data = json.loads(result)
        suggested_angles = [(a["azimuth"], a["elevation"]) for a in angle_data.get("suggested_angles", [])]

        if logger:
            logger.info(f"  AI suggested {len(suggested_angles)} optimal angles")
            logger.info(f"  Analysis: {angle_data.get('analysis', 'N/A')}")
            for i, angle in enumerate(angle_data.get("suggested_angles", [])):
                logger.info(f"    Angle {i+1}: Azimuth {angle['azimuth']}°, Elevation {angle['elevation']}° - {angle['reason']}")

        return suggested_angles if suggested_angles else [(90, 0), (180, 0), (270, 30)]

    except Exception as e:
        if logger:
            logger.warning(f"Failed to get AI angle suggestions: {str(e)}")
            logger.warning("Using default angles")
        # Fallback to default angles
        return [(90, 0), (180, 0), (270, 30)]


def capture_viewport_images():
    """
    Capture viewport images from fixed comprehensive angles around the scene using safe camera-based rendering.
    Uses fixed angles to avoid unnecessary AI API calls and captures orthographic views + diagonals.

    Returns:
        list: List of file paths to the captured images
    """
    global logger
    import tempfile
    import os
    import math

    if logger:
        logger.info("Capturing viewport images from fixed comprehensive angles...")

    image_paths = []
    temp_dir = tempfile.gettempdir()

    # Initialize variables outside try block so they're accessible in finally
    temp_camera = None
    camera_data = None
    original_camera = None
    original_resolution_x = None
    original_resolution_y = None
    original_file_format = None

    try:
        # Get scene bounds
        all_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        if not all_objects:
            if logger:
                logger.warning("No mesh objects found for viewport capture")
            return []

        # Calculate bounding box center and size
        min_corner = Vector((float('inf'), float('inf'), float('inf')))
        max_corner = Vector((float('-inf'), float('-inf'), float('-inf')))

        for obj in all_objects:
            try:
                for corner in obj.bound_box:
                    world_corner = obj.matrix_world @ Vector(corner)
                    min_corner.x = min(min_corner.x, world_corner.x)
                    min_corner.y = min(min_corner.y, world_corner.y)
                    min_corner.z = min(min_corner.z, world_corner.z)
                    max_corner.x = max(max_corner.x, world_corner.x)
                    max_corner.y = max(max_corner.y, world_corner.y)
                    max_corner.z = max(max_corner.z, world_corner.z)
            except Exception as e:
                if logger:
                    logger.warning(f"Skipping object {obj.name}: {str(e)}")
                continue

        center = (min_corner + max_corner) / 2
        size = (max_corner - min_corner).length

        if size == 0:
            if logger:
                logger.warning("Model has zero size, cannot capture images")
            return []

        # Store original camera and render settings
        original_camera = bpy.context.scene.camera
        original_resolution_x = bpy.context.scene.render.resolution_x
        original_resolution_y = bpy.context.scene.render.resolution_y
        original_file_format = bpy.context.scene.render.image_settings.file_format

        # Create temporary camera
        camera_data = bpy.data.cameras.new(name="TempCaptureCam")
        temp_camera = bpy.data.objects.new("TempCaptureCam", camera_data)
        bpy.context.scene.collection.objects.link(temp_camera)
        bpy.context.scene.camera = temp_camera

        # Set render settings for capture - REDUCED RESOLUTION to save tokens
        bpy.context.scene.render.resolution_x = 512  # Reduced from 1024
        bpy.context.scene.render.resolution_y = 512  # Reduced from 1024
        bpy.context.scene.render.image_settings.file_format = 'PNG'

        # Define fixed comprehensive angles
        # Format: (name, azimuth, elevation)
        # Azimuth: 0=front, 90=right, 180=back, 270=left
        # Elevation: 0=level, positive=above, negative=below
        fixed_angles = [
            ("front", 0, 0),           # Front view
            ("right", 90, 0),          # Right side view
            ("back", 180, 0),          # Back view
            ("left", 270, 0),          # Left side view
            ("top", 0, 90),            # Top view (looking down)
            ("bottom", 0, -90),        # Bottom view (looking up)
            ("front_top", 45, 30),     # Diagonal: front-top
            ("right_top", 135, 30),    # Diagonal: right-top
            ("back_top", 225, 30),     # Diagonal: back-top
            ("left_top", 315, 30),     # Diagonal: left-top
        ]

        if logger:
            logger.info(f"  Capturing {len(fixed_angles)} comprehensive views...")

        cam_distance = size * 2.0

        for i, (view_name, azimuth, elevation) in enumerate(fixed_angles):
            try:
                # Convert angles to radians
                azimuth_rad = math.radians(azimuth)
                elevation_rad = math.radians(elevation)

                # Position camera
                if abs(elevation) == 90:
                    # Top/bottom views: position directly above/below
                    cam_x = center.x
                    cam_y = center.y
                    cam_z = center.z + (cam_distance if elevation > 0 else -cam_distance)
                else:
                    horizontal_dist = cam_distance * math.cos(elevation_rad)
                    cam_x = center.x + horizontal_dist * math.sin(azimuth_rad)
                    cam_y = center.y + horizontal_dist * math.cos(azimuth_rad)
                    cam_z = center.z + cam_distance * math.sin(elevation_rad)

                temp_camera.location = Vector((cam_x, cam_y, cam_z))

                # Point camera at center
                direction = center - temp_camera.location
                rot_quat = direction.to_track_quat('-Z', 'Y')
                temp_camera.rotation_euler = rot_quat.to_euler()

                # Update viewport to show the angle (visual feedback for user)
                update_viewport_to_camera()

                # Render image
                image_path = os.path.join(temp_dir, f"blender_view_{view_name}.png")
                bpy.context.scene.render.filepath = image_path
                bpy.ops.render.opengl(write_still=True)

                if os.path.exists(image_path):
                    image_paths.append(image_path)
                    if logger:
                        logger.info(f"    ✓ {view_name.replace('_', ' ').title()}: Azimuth {azimuth}°, Elevation {elevation}°")
                else:
                    if logger:
                        logger.warning(f"    ✗ Failed to create {view_name} view")

            except Exception as e:
                if logger:
                    logger.warning(f"    ✗ Error capturing {view_name} view: {str(e)}")
                continue

        if logger:
            logger.info(f"Successfully captured {len(image_paths)} images at 512x512 resolution")

        return image_paths

    except Exception as e:
        if logger:
            logger.error(f"Error during image capture: {str(e)}")
        return []

    finally:
        # Always cleanup temporary camera and restore settings
        try:
            # Restore original settings if they were saved
            if original_camera is not None:
                bpy.context.scene.camera = original_camera
            if original_resolution_x is not None:
                bpy.context.scene.render.resolution_x = original_resolution_x
            if original_resolution_y is not None:
                bpy.context.scene.render.resolution_y = original_resolution_y
            if original_file_format is not None:
                bpy.context.scene.render.image_settings.file_format = original_file_format

            # Clean up temporary camera objects
            if temp_camera is not None and temp_camera.name in bpy.data.objects:
                bpy.data.objects.remove(temp_camera, do_unlink=True)
            if camera_data is not None and camera_data.name in bpy.data.cameras:
                bpy.data.cameras.remove(camera_data, do_unlink=True)
        except Exception as cleanup_error:
            if logger:
                logger.warning(f"Cleanup warning: {str(cleanup_error)}")


def resize_image_for_ai(image_path, target_size=(384, 384), show_warning=True):
    """
    Resize image to reduce tokens before sending to AI.
    Further reduces already-captured 512x512 images to 384x384 for token efficiency.

    Args:
        image_path (str): Path to image file
        target_size (tuple): Target (width, height) in pixels
        show_warning (bool): Whether to show PIL missing warning (only once)

    Returns:
        str: Path to resized image, or original if resize fails
    """
    global logger

    # Check if PIL is available
    try:
        from PIL import Image
    except ImportError:
        if logger and show_warning:
            logger.warning("PIL/Pillow not available - using original image size (512x512)")
            logger.warning("To reduce token usage, run install_pillow.py from Blender's Scripting workspace")
        return image_path

    try:
        import os

        # Open and resize image
        with Image.open(image_path) as img:
            # Convert RGBA to RGB if needed
            if img.mode == 'RGBA':
                img = img.convert('RGB')

            # Resize maintaining aspect ratio
            img.thumbnail(target_size, Image.Resampling.LANCZOS)

            # Save resized version
            resized_path = image_path.replace('.png', '_resized.png')
            img.save(resized_path, 'PNG', optimize=True)

            return resized_path

    except Exception as e:
        if logger:
            logger.warning(f"Image resize failed: {str(e)} - using original")
        return image_path


def load_images_in_blender(image_paths):
    """
    Load captured images into Blender's image editor for preview.

    Args:
        image_paths (list): List of image file paths
    """
    global logger
    import os

    try:
        if logger:
            logger.info("Loading images in Blender for preview...")

        # Load all images as Blender image datablocks
        loaded_count = 0
        for i, img_path in enumerate(image_paths):
            try:
                # Check if file exists
                if not os.path.exists(img_path):
                    if logger:
                        logger.warning(f"  Image file not found: {img_path}")
                    continue

                # Load image
                img_name = f"Captured_Angle_{i}"
                if img_name in bpy.data.images:
                    bpy.data.images.remove(bpy.data.images[img_name])

                img = bpy.data.images.load(img_path, check_existing=False)
                img.name = img_name
                loaded_count += 1

                if logger:
                    logger.info(f"  Loaded: {img_name}")

            except Exception as e:
                if logger:
                    logger.warning(f"  Failed to load {img_path}: {str(e)}")

        # Try to open in image editor (safely)
        try:
            if bpy.context.screen and bpy.context.screen.areas:
                for area in bpy.context.screen.areas:
                    if area.type == 'IMAGE_EDITOR':
                        if bpy.data.images and "Captured_Angle_0" in bpy.data.images:
                            area.spaces[0].image = bpy.data.images["Captured_Angle_0"]
                            if logger:
                                logger.info("  Opened first image in Image Editor")
                        break
        except Exception as e:
            # Screen access might fail in some contexts - not critical
            if logger:
                logger.info("  (Could not auto-open in Image Editor - manually open if needed)")

        if logger:
            logger.info(f"  {loaded_count}/{len(image_paths)} images loaded successfully")
            logger.info("  Access them via: Image Editor > Image > Browse")

    except Exception as e:
        if logger:
            logger.warning(f"Failed to load images in Blender: {str(e)}")


def analyze_images_with_ai(image_paths, cleanup_images=True, show_preview=True):
    """
    Analyze captured viewport images using Azure OpenAI vision capabilities.

    Args:
        image_paths (list): List of file paths to captured images
        cleanup_images (bool): Whether to delete temporary images after analysis
        show_preview (bool): Whether to load images in Blender for preview

    Returns:
        tuple: (success: bool, analysis: str or error message, tokens_used: int)
    """
    global logger
    import base64
    import os

    try:
        if logger:
            logger.section("VISUAL ANALYSIS WITH AI")
            logger.info(f"Analyzing {len(image_paths)} images...")

        # Load images in Blender for preview
        if show_preview:
            load_images_in_blender(image_paths)

        # Get Azure OpenAI client
        client = get_azure_client()
        deployment = get_deployment_name()

        if not client or not deployment:
            if logger:
                logger.error("Azure OpenAI not configured")
            return False, "Azure OpenAI not configured", 0

        # Resize and encode images to base64 with size limits
        if logger:
            logger.info("Resizing images to reduce token usage...")

        encoded_images = []
        resized_paths = []
        TARGET_SIZE = (384, 384)  # Further reduced to 384x384 to save tokens

        for idx, img_path in enumerate(image_paths):
            try:
                # Check if file exists
                if not os.path.exists(img_path):
                    if logger:
                        logger.warning(f"  Image not found: {img_path}")
                    continue

                original_size_mb = os.path.getsize(img_path) / (1024 * 1024)

                # Resize image to reduce tokens (only show warning for first image)
                resized_path = resize_image_for_ai(img_path, TARGET_SIZE, show_warning=(idx == 0))
                resized_paths.append(resized_path)

                resized_size_mb = os.path.getsize(resized_path) / (1024 * 1024)

                # Encode resized image
                with open(resized_path, "rb") as img_file:
                    image_data = img_file.read()
                    encoded_image = base64.b64encode(image_data).decode('utf-8')
                    encoded_images.append(encoded_image)

                    if logger:
                        logger.info(f"  Resized & encoded: {os.path.basename(img_path)}")
                        logger.info(f"    Original: {original_size_mb:.2f}MB → Resized: {resized_size_mb:.2f}MB ({resized_size_mb/original_size_mb*100:.1f}% of original)")

            except Exception as e:
                if logger:
                    logger.warning(f"  Failed to process {img_path}: {str(e)}")
                continue

        if not encoded_images:
            if logger:
                logger.warning("No images were successfully encoded")
            return False, "No images were successfully encoded", 0

        # Create vision analysis prompt
        vision_prompt = """You are an expert in robotic kinematics, SDF/URDF formats, and simulation-ready robot models for Gazebo/Flowstate.

You are viewing multiple angles (front, back, left, right, top, bottom, and diagonal views) of a 3D mechanical model/robot. Your task is to analyze the kinematic structure for SDF export.

CRITICAL UNDERSTANDING - LINKS ARE RIGID BODIES:
- A "link" is a RIGID BODY in the kinematic chain, NOT an individual CAD part
- Multiple CAD parts that move together = ONE link
- Only parts that move INDEPENDENTLY = separate links
- Links are connected by JOINTS (revolute, prismatic, fixed)

ANALYSIS TASKS:
1. Identify the BASE LINK (fixed/stationary structure):
   - Usually the largest grounded component
   - This is ALWAYS called "base_link" (SDF convention)
   - Mark as static: true

2. Identify MOVING LINKS (independently moving rigid bodies):
   - Each independently moving part/assembly = ONE link
   - Parts rigidly connected (no relative motion) = SAME link
   - Symmetric parts (left/right wheels) = SEPARATE links if they move independently

3. Identify JOINT TYPES for each moving link:
   - REVOLUTE: Rotational/hinge joint (wheels, rotating arms)
   - PRISMATIC: Linear/sliding joint (lifts, telescoping parts)
   - FIXED: Permanently attached (should be in base_link instead)
   - CONTINUOUS: Revolute joint without rotation limits (free-spinning wheels)

4. Determine the KINEMATIC CHAIN:
   - Trace the parent-child relationships from base to end-effector
   - Each link connects to its parent link via a joint

IMPORTANT GUIDELINES:
- Most mechanisms have 2-4 links total (base + 1-3 moving parts)
- Visible gaps, hinges, or sliding mechanisms indicate joints between links
- If components don't move relative to each other, they're the SAME link
- Focus on FUNCTIONAL movement, not CAD assembly structure

SDF NAMING REQUIREMENTS:
- Base link MUST be named "base_link"
- All link names MUST end with "_link" suffix
- Use descriptive names: "chassis_link", "wheel_left_link", "mast_link"

Respond ONLY with valid JSON in this exact format:
{
  "model_description": "One sentence describing the mechanism type and key moving parts",
  "mechanism_type": "wheeled_robot|robotic_arm|gripper|forklift|conveyor|other",
  "total_degrees_of_freedom": <number>,
  "links": [
    {
      "link_name": "base_link",
      "is_base": true,
      "static": true,
      "function": "stationary foundation/chassis",
      "components_description": "all fixed/stationary CAD parts",
      "joint_type": "none",
      "parent_link": null
    },
    {
      "link_name": "descriptive_name_link",
      "is_base": false,
      "static": false,
      "function": "what this link does (e.g., 'rotates left wheel')",
      "components_description": "CAD parts that move together as this rigid body",
      "joint_type": "revolute|prismatic|continuous",
      "parent_link": "base_link",
      "joint_axis": "x|y|z (axis of rotation/translation)",
      "has_limits": true|false
    }
  ]
}

Example for a forklift with 2 independently rotating rear wheels and a vertical lift:
{
  "model_description": "A wheeled forklift robot with two independently rotating rear wheels and a vertical prismatic lift mechanism",
  "mechanism_type": "forklift",
  "total_degrees_of_freedom": 3,
  "links": [
    {
      "link_name": "base_link",
      "is_base": true,
      "static": true,
      "function": "stationary chassis and body",
      "components_description": "main chassis, frame, front casters, all non-moving structural elements",
      "joint_type": "none",
      "parent_link": null
    },
    {
      "link_name": "rear_left_wheel_link",
      "is_base": false,
      "static": false,
      "function": "left rear wheel rotation for driving",
      "components_description": "cylindrical wheel assembly on left rear",
      "joint_type": "continuous",
      "parent_link": "base_link",
      "joint_axis": "y",
      "has_limits": false
    },
    {
      "link_name": "rear_right_wheel_link",
      "is_base": false,
      "static": false,
      "function": "right rear wheel rotation for driving",
      "components_description": "cylindrical wheel assembly on right rear",
      "joint_type": "continuous",
      "parent_link": "base_link",
      "joint_axis": "y",
      "has_limits": false
    },
    {
      "link_name": "mast_lift_link",
      "is_base": false,
      "static": false,
      "function": "vertical lifting carriage",
      "components_description": "lifting carriage, fork assembly, vertical sliding elements",
      "joint_type": "prismatic",
      "parent_link": "base_link",
      "joint_axis": "z",
      "has_limits": true
    }
  ]
}"""

        # Create message content with images
        message_content = [{"type": "text", "text": vision_prompt}]

        for encoded_img in encoded_images:
            message_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{encoded_img}"
                }
            })

        if logger:
            logger.info("Sending images to Azure OpenAI for vision analysis...")
            logger.info(f"  Total images: {len(encoded_images)}")

        # Make API call with vision and error handling
        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in robotics, mechanical engineering, and kinematic analysis."
                    },
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                max_completion_tokens=16000,  # Higher limit for reasoning models (gpt-5-mini uses reasoning tokens)
                timeout=120  # Increased timeout for reasoning models
            )

            if logger:
                logger.info("Received vision analysis response")
                logger.info(f"  Response object type: {type(response)}")

            # Track token usage
            tokens_used = 0
            if hasattr(response, 'usage') and response.usage:
                tokens_used = response.usage.total_tokens
                if logger:
                    logger.info(f"  Tokens used: {tokens_used} (prompt: {response.usage.prompt_tokens}, completion: {response.usage.completion_tokens})")

            if not response or not response.choices:
                if logger:
                    logger.error("Empty response from API")
                    logger.error(f"  Response: {response}")
                return False, "Empty response from vision API", 0

            if logger:
                logger.info(f"  Number of choices: {len(response.choices)}")
                logger.info(f"  Choice[0] message: {response.choices[0].message}")

            analysis = response.choices[0].message.content

            if logger:
                logger.info(f"  Content type: {type(analysis)}")
                logger.info(f"  Content length: {len(analysis) if analysis else 0}")
                if analysis:
                    logger.info(f"  Content preview: {analysis[:200]}...")

            if not analysis or len(analysis.strip()) == 0:
                if logger:
                    logger.error("Vision analysis returned empty content")
                    logger.error(f"  Full response: {response}")
                    logger.error(f"  Message object: {response.choices[0].message}")
                return False, "Vision analysis returned empty content", tokens_used

            if logger:
                logger.info("")
                logger.info("VISION ANALYSIS RESULT:")
                logger.separator("-", 60)

                # Try to parse and display structured JSON
                try:
                    # Extract JSON from markdown code blocks if present
                    analysis_text = analysis
                    if "```json" in analysis_text:
                        analysis_text = analysis_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in analysis_text:
                        analysis_text = analysis_text.split("```")[1].split("```")[0].strip()

                    vision_json = json.loads(analysis_text)

                    # Log structured output
                    logger.info(f"Model: {vision_json.get('model_description', 'N/A')}")
                    logger.info(f"Total Links: {len(vision_json.get('links', []))}")
                    logger.info("")

                    for idx, link in enumerate(vision_json.get('links', []), 1):
                        logger.info(f"Link {idx}: {link.get('link_name', 'unnamed')}")
                        logger.info(f"  Function: {link.get('function', 'N/A')}")
                        logger.info(f"  Components: {link.get('components_description', 'N/A')}")
                        logger.info(f"  Joint Type: {link.get('joint_type', 'N/A')}")
                        logger.info("")

                    # Extract and save joint information for later use
                    joint_data = []
                    for link in vision_json.get('links', []):
                        # Skip base_link (it has no joint)
                        if link.get('is_base', False) or link.get('joint_type') == 'none':
                            continue

                        joint_info = {
                            'link_name': link.get('link_name', ''),
                            'joint_type': link.get('joint_type', ''),
                            'parent_link': link.get('parent_link', 'base_link'),
                            'joint_axis': link.get('joint_axis', 'z'),
                            'has_limits': link.get('has_limits', False),
                            'function': link.get('function', ''),
                            'components': link.get('components_description', '')
                        }
                        joint_data.append(joint_info)

                    # Save joint data to scene for later retrieval
                    if joint_data:
                        bpy.context.scene['auto_link_joint_data'] = json.dumps(joint_data)
                        logger.info(f"Saved {len(joint_data)} joint definitions for later use")
                        logger.info("  Use the 'Create Joints' button to generate joints from this data")
                        logger.info("")

                except (json.JSONDecodeError, KeyError):
                    # Fallback to raw text display
                    for line in analysis.split('\n'):
                        logger.text_block.write(line + "\n")

                logger.separator("-", 60)

            # Cleanup temporary images if requested
            if cleanup_images:
                cleanup_temp_images(image_paths + resized_paths)

            return True, analysis, tokens_used

        except TimeoutError:
            if logger:
                logger.error("Vision analysis timed out after 60 seconds")
            # Cleanup on error
            if cleanup_images:
                cleanup_temp_images(image_paths + resized_paths)
            return False, "Vision analysis timed out - try reducing number of images", 0

        except Exception as api_error:
            if logger:
                logger.error(f"API call failed: {str(api_error)}")
            # Cleanup on error
            if cleanup_images:
                cleanup_temp_images(image_paths + resized_paths)
            return False, f"Vision API call failed: {str(api_error)}", 0

    except Exception as e:
        if logger:
            logger.error(f"Error during vision analysis: {str(e)}")
        # Cleanup on error
        if cleanup_images:
            cleanup_temp_images(image_paths + resized_paths)
        return False, f"Error during vision analysis: {str(e)}", 0


def cleanup_temp_images(image_paths):
    """
    Clean up temporary image files (including resized versions).

    Args:
        image_paths (list): List of image file paths to delete
    """
    global logger
    import os

    if not image_paths:
        return

    cleaned = 0
    for img_path in image_paths:
        try:
            if os.path.exists(img_path):
                os.remove(img_path)
                cleaned += 1
        except Exception as e:
            if logger:
                logger.warning(f"Failed to cleanup {img_path}: {str(e)}")

    if logger and cleaned > 0:
        logger.info(f"Cleaned up {cleaned} temporary image files")


def get_saved_joint_data():
    """
    Retrieve joint data saved from vision analysis.

    Returns:
        list: List of joint definitions with structure:
            [
                {
                    'link_name': str,
                    'joint_type': 'continuous'|'prismatic'|'revolute',
                    'parent_link': str,
                    'joint_axis': 'x'|'y'|'z',
                    'has_limits': bool,
                    'function': str,
                    'components': str
                },
                ...
            ]
        Returns empty list if no data is available.
    """
    global logger

    try:
        joint_data_json = bpy.context.scene.get('auto_link_joint_data')
        if not joint_data_json:
            if logger:
                logger.warning("No saved joint data found")
                logger.warning("  Run 'Auto-Link' first to analyze the model and generate joint definitions")
            return []

        joint_data = json.loads(joint_data_json)
        if logger:
            logger.info(f"Retrieved {len(joint_data)} saved joint definitions")

        return joint_data

    except (json.JSONDecodeError, KeyError) as e:
        if logger:
            logger.error(f"Failed to parse saved joint data: {str(e)}")
        return []


def analyze_spatial_relationships(scene_data):
    """
    Analyze spatial relationships between objects to identify functional groups.
    Uses proximity, geometric features, and symmetry to suggest intelligent groupings.

    Args:
        scene_data (dict): Scene data with object information

    Returns:
        dict: Spatial clusters and geometric feature analysis
    """
    global logger
    import numpy as np
    from mathutils import Vector

    objects = scene_data.get("objects", [])
    if not objects:
        return {"clusters": [], "geometric_features": {}}

    # Get actual Blender objects for geometric analysis
    blender_objects = {}
    for obj_data in objects:
        obj = bpy.data.objects.get(obj_data["name"])
        if obj and obj.type == 'MESH':
            blender_objects[obj_data["name"]] = obj

    if logger:
        logger.info(f"Analyzing spatial relationships for {len(blender_objects)} mesh objects...")

    # 1. Geometric Feature Detection
    geometric_features = {}
    for obj_name, obj in blender_objects.items():
        features = analyze_object_geometry(obj)
        geometric_features[obj_name] = features

    # 2. Spatial Clustering by proximity
    clusters = perform_spatial_clustering(objects, blender_objects)

    # 3. Identify symmetry pairs (left/right assemblies)
    symmetry_pairs = identify_symmetry_pairs(objects, blender_objects)

    if logger:
        logger.info(f"Identified {len(clusters)} spatial clusters")
        logger.info(f"Identified {len(symmetry_pairs)} symmetry pairs")

    return {
        "clusters": clusters,
        "geometric_features": geometric_features,
        "symmetry_pairs": symmetry_pairs
    }


def analyze_object_geometry(obj):
    """
    Analyze geometric features of a mesh object to determine its likely function.

    Args:
        obj: Blender mesh object

    Returns:
        dict: Geometric feature classification
    """
    if not obj or obj.type != 'MESH' or not obj.data.vertices:
        return {"shape": "unknown", "aspect_ratio": 0, "size_category": "unknown"}

    dims = obj.dimensions
    max_dim = max(dims)
    min_dim = min([d for d in dims if d > 0.001]) if any(d > 0.001 for d in dims) else 0.001

    # Calculate aspect ratios
    aspect_ratio = max_dim / min_dim if min_dim > 0 else 1

    # Determine shape category
    shape = "unknown"
    if dims[0] > 0.001 and dims[1] > 0.001 and dims[2] > 0.001:
        # Check for cylindrical (wheel-like) objects
        sorted_dims = sorted(dims)
        if sorted_dims[0] / sorted_dims[1] < 0.3 and abs(sorted_dims[1] - sorted_dims[2]) / sorted_dims[2] < 0.2:
            shape = "cylindrical"  # Likely a wheel or hub
        # Check for elongated (beam/rail-like) objects
        elif aspect_ratio > 5:
            shape = "elongated"  # Likely a rail, beam, or fork tine
        # Check for flat (plate-like) objects
        elif sorted_dims[0] / sorted_dims[2] < 0.2:
            shape = "flat"  # Likely a plate or panel
        # Box-like
        elif aspect_ratio < 3:
            shape = "box"  # Likely chassis or structural component

    # Size categorization
    volume = dims[0] * dims[1] * dims[2]
    if volume > 1.0:
        size_category = "large"
    elif volume > 0.1:
        size_category = "medium"
    else:
        size_category = "small"

    return {
        "shape": shape,
        "aspect_ratio": float(aspect_ratio),
        "size_category": size_category,
        "dimensions": [float(d) for d in dims],
        "volume": float(volume)
    }


def perform_spatial_clustering(objects, blender_objects):
    """
    Group objects by spatial proximity to identify assemblies.

    Args:
        objects (list): Object data from scene
        blender_objects (dict): Actual Blender objects

    Returns:
        list: Spatial clusters with object groups
    """
    from mathutils import Vector
    import numpy as np

    if not objects:
        return []

    # Build position matrix
    positions = []
    obj_names = []

    for obj_data in objects:
        obj = blender_objects.get(obj_data["name"])
        if obj:
            # Use world-space location
            world_loc = obj.matrix_world.translation
            positions.append([world_loc.x, world_loc.y, world_loc.z])
            obj_names.append(obj_data["name"])

    if len(positions) < 2:
        return []

    positions = np.array(positions)

    # Simple clustering based on distance threshold
    clusters = []
    visited = set()
    distance_threshold = 2.0  # Adjust based on model scale

    for i, obj_name in enumerate(obj_names):
        if obj_name in visited:
            continue

        # Start new cluster
        cluster = {"objects": [obj_name], "center": positions[i].tolist()}
        visited.add(obj_name)

        # Find nearby objects
        for j, other_name in enumerate(obj_names):
            if other_name in visited:
                continue

            distance = np.linalg.norm(positions[i] - positions[j])
            if distance < distance_threshold:
                cluster["objects"].append(other_name)
                visited.add(other_name)

        if len(cluster["objects"]) > 1:  # Only include multi-object clusters
            clusters.append(cluster)

    return clusters


def identify_symmetry_pairs(objects, blender_objects):
    """
    Identify symmetric pairs of objects (e.g., left/right wheels).

    Args:
        objects (list): Object data from scene
        blender_objects (dict): Actual Blender objects

    Returns:
        list: Pairs of symmetric objects
    """
    from mathutils import Vector

    pairs = []
    checked = set()

    for obj1_data in objects:
        obj1 = blender_objects.get(obj1_data["name"])
        if not obj1 or obj1.name in checked:
            continue

        pos1 = obj1.matrix_world.translation

        # Look for symmetric counterpart
        for obj2_data in objects:
            obj2 = blender_objects.get(obj2_data["name"])
            if not obj2 or obj2.name in checked or obj1.name == obj2.name:
                continue

            pos2 = obj2.matrix_world.translation

            # Check for symmetry across Y or X axis
            # Objects at similar Z and one axis, but opposite on another axis
            if (abs(pos1.z - pos2.z) < 0.5 and  # Similar height
                abs(pos1.y - pos2.y) < 0.5 and  # Similar depth
                abs(abs(pos1.x) - abs(pos2.x)) < 0.5 and  # Similar distance from center
                pos1.x * pos2.x < 0):  # Opposite sides

                pairs.append({
                    "left": obj1.name if pos1.x < pos2.x else obj2.name,
                    "right": obj2.name if pos1.x < pos2.x else obj1.name
                })
                checked.add(obj1.name)
                checked.add(obj2.name)
                break

    return pairs


def extract_model_data():
    """
    Extract comprehensive model data from the current Blender scene.

    Returns:
        dict: Dictionary containing scene metadata, objects, hierarchy, and relationships
    """
    global logger
    if logger:
        logger.info("Starting model data extraction...")

    scene_data = {
        "scene_name": bpy.context.scene.name,
        "objects": [],
        "hierarchy": [],
        "constraints": [],
        "collections": []
    }

    if logger:
        logger.info(f"Scene name: {bpy.context.scene.name}")

    # Extract object information
    for obj in bpy.context.scene.objects:
        if obj.type in ['MESH', 'EMPTY', 'ARMATURE']:
            # Get world-space location (actual position in 3D space)
            world_location = obj.matrix_world.translation

            # Calculate bounding box center in world space for mesh objects
            bbox_center = None
            if obj.type == 'MESH' and obj.data.vertices:
                try:
                    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
                    bbox_center = sum(bbox_corners, Vector((0,0,0))) / len(bbox_corners)
                except:
                    bbox_center = world_location
            else:
                bbox_center = world_location

            obj_data = {
                "name": obj.name,
                "type": obj.type,
                "location": list(obj.location),  # Local location (for reference)
                "world_location": [world_location.x, world_location.y, world_location.z],  # Actual position
                "bbox_center": [bbox_center.x, bbox_center.y, bbox_center.z] if bbox_center else list(world_location),  # Geometry center
                "rotation": list(obj.rotation_euler),
                "scale": list(obj.scale),
                "parent": obj.parent.name if obj.parent else None,
                "children": [child.name for child in obj.children],
                "dimensions": list(obj.dimensions),
                "object_type": obj.object_type if hasattr(obj, 'object_type') else "StandardObject",
            }

            # Add rigid body information if available
            if obj.rigid_body:
                obj_data["rigid_body"] = {
                    "type": obj.rigid_body.type,
                    "mass": obj.rigid_body.mass,
                    "enabled": obj.rigid_body.enabled
                }

            # Add constraint information
            if obj.constraints:
                obj_data["constraints"] = []
                for constraint in obj.constraints:
                    obj_data["constraints"].append({
                        "type": constraint.type,
                        "target": constraint.target.name if constraint.target else None,
                        "enabled": constraint.enabled if hasattr(constraint, 'enabled') else True
                    })

            # Add collection membership
            obj_data["collections"] = [col.name for col in obj.users_collection]

            scene_data["objects"].append(obj_data)

    # Extract hierarchy relationships
    for obj in bpy.context.scene.objects:
        if obj.type in ['MESH', 'EMPTY', 'ARMATURE']:
            if obj.parent:
                scene_data["hierarchy"].append({
                    "child": obj.name,
                    "parent": obj.parent.name,
                    "parent_type": obj.parent_type
                })

    # Extract collection information
    for collection in bpy.data.collections:
        if collection.name in bpy.context.scene.collection.children.keys() or \
           any(collection.name in col.children.keys() for col in bpy.context.scene.collection.children_recursive):
            col_data = {
                "name": collection.name,
                "collection_type": collection.collection_type if hasattr(collection, 'collection_type') else "StandardCollection",
                "objects": [obj.name for obj in collection.objects],
                "parent": None
            }

            # Find parent collection
            for parent_col in bpy.data.collections:
                if collection.name in parent_col.children.keys():
                    col_data["parent"] = parent_col.name
                    break

            scene_data["collections"].append(col_data)

    # Add spatial clustering and geometric analysis
    spatial_analysis = analyze_spatial_relationships(scene_data)
    scene_data["spatial_clusters"] = spatial_analysis["clusters"]
    scene_data["geometric_features"] = spatial_analysis["geometric_features"]
    scene_data["symmetry_pairs"] = spatial_analysis.get("symmetry_pairs", [])

    if logger:
        logger.info(f"Extracted {len(scene_data['objects'])} objects")
        logger.info(f"Extracted {len(scene_data['hierarchy'])} hierarchy relationships")
        logger.info(f"Extracted {len(scene_data['collections'])} collections")
        logger.info(f"Identified {len(scene_data['spatial_clusters'])} spatial clusters")
        logger.info("")
        logger.info("Full scene data (JSON):")
        logger.separator("-", 60)
        for line in json.dumps(scene_data, indent=2).split('\n'):
            logger.text_block.write(line + "\n")

    return scene_data


def format_data_for_ai(scene_data):
    """
    Format extracted scene data into a human-readable format for AI analysis.

    Args:
        scene_data (dict): Extracted scene data

    Returns:
        str: Formatted string for AI prompt
    """
    formatted = f"=== Blender Scene Analysis ===\n"
    formatted += f"Scene: {scene_data['scene_name']}\n\n"

    formatted += "=== OBJECTS ===\n"
    for obj in scene_data['objects']:
        formatted += f"\nObject: {obj['name']}\n"
        formatted += f"  Type: {obj['type']}\n"
        formatted += f"  Parent: {obj['parent']}\n"
        formatted += f"  Children: {', '.join(obj['children']) if obj['children'] else 'None'}\n"
        formatted += f"  World Location: ({obj['world_location'][0]:.3f}, {obj['world_location'][1]:.3f}, {obj['world_location'][2]:.3f})\n"
        formatted += f"  Geometry Center: ({obj['bbox_center'][0]:.3f}, {obj['bbox_center'][1]:.3f}, {obj['bbox_center'][2]:.3f})\n"
        formatted += f"  Dimensions: ({obj['dimensions'][0]:.3f}, {obj['dimensions'][1]:.3f}, {obj['dimensions'][2]:.3f})\n"
        formatted += f"  Collections: {', '.join(obj['collections'])}\n"

        if 'rigid_body' in obj:
            formatted += f"  Rigid Body: {obj['rigid_body']['type']} (mass: {obj['rigid_body']['mass']})\n"

        if 'constraints' in obj:
            for constraint in obj['constraints']:
                formatted += f"  Constraint: {constraint['type']} -> {constraint['target']}\n"

    formatted += "\n=== HIERARCHY ===\n"
    for rel in scene_data['hierarchy']:
        formatted += f"  {rel['child']} <- parent of <- {rel['parent']} (type: {rel['parent_type']})\n"

    formatted += "\n=== EXISTING COLLECTIONS ===\n"
    for col in scene_data['collections']:
        formatted += f"\nCollection: {col['name']} (Type: {col['collection_type']})\n"
        formatted += f"  Objects: {', '.join(col['objects']) if col['objects'] else 'Empty'}\n"
        formatted += f"  Parent: {col['parent']}\n"

    # Add spatial clustering information
    formatted += "\n=== SPATIAL CLUSTERS (Objects Grouped by Proximity) ===\n"
    if scene_data.get('spatial_clusters'):
        for idx, cluster in enumerate(scene_data['spatial_clusters']):
            formatted += f"\nCluster {idx + 1} (near {cluster['center']}):\n"
            formatted += f"  Objects: {', '.join(cluster['objects'])}\n"
    else:
        formatted += "No spatial clusters identified\n"

    # Add geometric features
    formatted += "\n=== GEOMETRIC FEATURES (Shape Analysis) ===\n"
    if scene_data.get('geometric_features'):
        shape_groups = {"cylindrical": [], "elongated": [], "flat": [], "box": [], "unknown": []}

        for obj_name, features in scene_data['geometric_features'].items():
            shape = features.get('shape', 'unknown')
            shape_groups[shape].append(obj_name)

        for shape, objects in shape_groups.items():
            if objects:
                formatted += f"\n{shape.upper()} objects (likely {get_shape_hint(shape)}):\n"
                formatted += f"  {', '.join(objects)}\n"
    else:
        formatted += "No geometric analysis available\n"

    # Add symmetry pairs
    formatted += "\n=== SYMMETRY PAIRS (Left/Right Assemblies) ===\n"
    if scene_data.get('symmetry_pairs'):
        for pair in scene_data['symmetry_pairs']:
            formatted += f"  Left: {pair['left']} <-> Right: {pair['right']}\n"
    else:
        formatted += "No symmetry pairs identified\n"

    return formatted


def get_shape_hint(shape):
    """Provide functional hints based on geometric shape."""
    hints = {
        "cylindrical": "wheels, hubs, axles",
        "elongated": "rails, beams, fork tines, mast columns",
        "flat": "plates, panels, chassis bases",
        "box": "chassis, body, structural blocks",
        "unknown": "complex geometry"
    }
    return hints.get(shape, "unknown function")


def create_ai_prompt(formatted_data, vision_analysis):
    """
    Create a detailed prompt for Azure OpenAI to analyze the scene and suggest links.

    Args:
        formatted_data (str): Formatted scene data
        vision_analysis (str): Visual analysis from image inspection (REQUIRED)

    Returns:
        str: Complete prompt for AI
    """
    vision_context = f"""
VISUAL ANALYSIS (from multi-angle inspection):
{'=' * 60}
{vision_analysis}
{'=' * 60}

IMPORTANT: Use the visual analysis above as PRIMARY guidance for link grouping.
The visual analysis provides domain knowledge about the mechanical structure that should
take precedence over naming conventions in the scene data below.
"""

    prompt = f"""You are an expert in robotic kinematics and SDF (Simulation Description Format) file generation.
Your task is to analyze a Blender scene and group objects into "links" for a robot/mechanism model.

LINK DEFINITION:
- A "link" represents a rigid body in the kinematic chain
- Create links ONLY for: (1) the BASE (stationary), and (2) MOVING COMPONENTS
- Objects that move together as one unit belong to the SAME link
- Links are connected by joints (revolute, prismatic, fixed, etc.)

{vision_context}

LINKING STRATEGY:
1. Identify the BASE: Create ONE base_link containing all stationary/fixed components
2. Identify MOVING PARTS: Create ONE link for each independently moving component or assembly
3. Group rigidly: Components that move together (no relative motion) belong to the SAME link
4. Focus on function: Links represent functional moving parts, not individual CAD components

ANALYSIS PRIORITY (in order):
1. Visual Structure & Position: Use the visual analysis to identify what moves independently
2. Spatial Clusters: Objects in the same spatial cluster are physically close and likely part of the same assembly
3. Geometric Features: Use shape analysis to identify functional components:
   - CYLINDRICAL objects → likely wheels, hubs, or axles (separate moving links)
   - ELONGATED objects → likely rails, beams, or fork tines (group by function)
   - FLAT/BOX objects → likely chassis, body, or structural base (typically base_link)
4. Symmetry Pairs: Left/right symmetric objects (e.g., wheels) should be separate links
5. Domain Knowledge: Apply robotics/mechanical engineering principles about kinematic chains
6. Hierarchy & Constraints: Parent-child relationships indicate kinematic connections
7. Object Names: Use as LAST RESORT - do NOT group by sequential numbering!

CRITICAL: DO NOT assign objects to links based on sequential object names (e.g., Forklift_b.001-015).
Instead, use SPATIAL CLUSTERS, GEOMETRIC FEATURES, and SYMMETRY PAIRS to intelligently categorize.

SCENE DATA:
{formatted_data}

TASK:
Create a minimal, functional link structure. Most mechanisms need only 2-4 links total.

HOW TO USE SPATIAL AND GEOMETRIC DATA:
1. Start with SPATIAL CLUSTERS - objects physically near each other likely form assemblies
2. Use GEOMETRIC FEATURES to identify function:
   - Group all CYLINDRICAL objects at similar positions → wheel assembly
   - Group ELONGATED vertical objects → mast assembly
   - Group large BOX/FLAT objects → chassis/base
3. Use SYMMETRY PAIRS to separate left/right moving parts
4. Cross-reference with VISUAL ANALYSIS for confirmation

Example Process for a Forklift:
- See CYLINDRICAL objects in Cluster 1 at left side → rear_left_wheel_link
- See CYLINDRICAL objects in Cluster 2 at right side (symmetry pair) → rear_right_wheel_link
- See ELONGATED vertical objects in Cluster 3 → mast_assembly_link
- See large BOX objects spread across middle → chassis_link (base)
- See small CYLINDRICAL objects in Cluster 4 at front → front_caster_link

General Examples:
- Simple gripper: base_link (stationary body), gripper_link (moving fingers as one unit)
- Robotic arm (2-joint): base_link, upper_arm_link, forearm_link
- Wheeled robot: chassis_link (base), wheel_left_link, wheel_right_link
- Articulated mechanism: base_link, rotating_platform_link, actuator_link

Respond ONLY with valid JSON in this exact format:
{{
  "links": [
    {{
      "name": "link_name",
      "objects": ["object1", "object2", ...],
      "reasoning": "why these objects move together as one functional unit"
    }}
  ],
  "suggestions": "observations about the kinematic structure"
}}

CRITICAL RULES:
- Create ONE link for the base (all stationary parts)
- Create ONE link per independently moving component/assembly
- Components with no relative motion between them = SAME link
- Most mechanisms have 2-4 links total, not 10+
- Every object should be assigned to exactly one link
- Focus on MOVEMENT and FUNCTION, not component boundaries
"""

    return prompt


def analyze_scene_with_ai(scene_data, vision_analysis):
    """
    Send scene data to Azure OpenAI for analysis and link suggestions.

    Args:
        scene_data (dict): Extracted scene data
        vision_analysis (str): Visual analysis from image inspection (REQUIRED)

    Returns:
        tuple: (success: bool, result: dict or error message: str)
    """
    global logger
    try:
        if logger:
            logger.section("SCENE ANALYSIS WITH VISUAL CONTEXT")
            logger.info("Combining visual analysis with scene data...")

        if not vision_analysis:
            if logger:
                logger.error("Vision analysis is required but was not provided")
            return False, "Vision analysis is required for link generation"

        # Get Azure OpenAI client
        client = get_azure_client()
        deployment = get_deployment_name()

        if not client or not deployment:
            if logger:
                logger.error("Azure OpenAI not configured")
            return False, "Azure OpenAI not configured. Please check your .env file."

        if logger:
            logger.info(f"Using deployment: {deployment}")

        # Format data and create prompt
        formatted_data = format_data_for_ai(scene_data)
        prompt = create_ai_prompt(formatted_data, vision_analysis)

        if logger:
            logger.section("AI PROMPT")
            for line in prompt.split('\n'):
                logger.text_block.write(line + "\n")

        # Make API call (without temperature parameter for model compatibility)
        if logger:
            logger.info("Sending request to Azure OpenAI...")

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert in robotics and CAD analysis. Always respond with valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        if logger:
            logger.info("Received response from Azure OpenAI")

        # Track token usage
        tokens_used = 0
        if hasattr(response, 'usage') and response.usage:
            tokens_used = response.usage.total_tokens
            if logger:
                logger.info(f"  Tokens used: {tokens_used} (prompt: {response.usage.prompt_tokens}, completion: {response.usage.completion_tokens})")

        # Parse response
        ai_response = response.choices[0].message.content

        if logger:
            logger.section("AI RESPONSE (RAW)")
            for line in ai_response.split('\n'):
                logger.text_block.write(line + "\n")

        # Try to extract JSON from response
        try:
            # Sometimes AI wraps JSON in markdown code blocks
            if "```json" in ai_response:
                ai_response = ai_response.split("```json")[1].split("```")[0].strip()
            elif "```" in ai_response:
                ai_response = ai_response.split("```")[1].split("```")[0].strip()

            result = json.loads(ai_response)
            result['_tokens_used'] = tokens_used  # Add tokens to result

            if logger:
                logger.section("AI RESPONSE (PARSED JSON)")
                for line in json.dumps(result, indent=2).split('\n'):
                    logger.text_block.write(line + "\n")
                logger.info("")
                logger.info(f"Number of links suggested: {len(result.get('links', []))}")

            return True, result

        except json.JSONDecodeError as e:
            if logger:
                logger.error(f"Failed to parse AI response as JSON: {str(e)}")
                logger.error(f"Response was: {ai_response}")
            return False, f"Failed to parse AI response as JSON: {str(e)}\n\nResponse:\n{ai_response}"

    except Exception as e:
        if logger:
            logger.error(f"Error during AI analysis: {str(e)}")
        return False, f"Error during AI analysis: {str(e)}"


def check_hierarchy_cycles(scene_data):
    """
    Check for cycles in parent-child hierarchy.

    Args:
        scene_data (dict): Scene data with hierarchy information

    Returns:
        list: List of detected cycles
    """
    hierarchy = scene_data.get("hierarchy", [])

    # Build adjacency list
    graph = {}
    for rel in hierarchy:
        parent = rel["parent"]
        child = rel["child"]
        if child not in graph:
            graph[child] = []
        graph[child].append(parent)

    # Detect cycles using DFS
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node, path):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        if node in graph:
            for neighbor in graph[node]:
                if neighbor not in visited:
                    if dfs(neighbor, path.copy()):
                        return True
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])
                    return True

        rec_stack.remove(node)
        return False

    for node in graph:
        if node not in visited:
            dfs(node, [])

    return cycles


def check_pivot_positions(objects):
    """
    Check if object origins/pivots are properly positioned.

    Args:
        objects (list): List of Blender objects

    Returns:
        dict: Issues with pivot positions
    """
    issues = []

    for obj_name in objects:
        obj = bpy.data.objects.get(obj_name)
        if not obj:
            continue

        # Check if origin is at (0,0,0) in local space (common issue)
        if obj.location.length > 0.001:  # Small tolerance
            # Check if origin is far from geometry center
            if obj.type == 'MESH' and obj.data.vertices:
                # Calculate geometry center in world space
                verts_world = [obj.matrix_world @ v.co for v in obj.data.vertices]
                geom_center = sum(verts_world, Vector((0,0,0))) / len(verts_world)
                origin_world = obj.matrix_world.translation

                distance = (geom_center - origin_world).length
                if distance > 0.1:  # 0.1 unit threshold
                    issues.append({
                        "object": obj_name,
                        "issue": "pivot_far_from_geometry",
                        "distance": distance,
                        "suggestion": "Consider centering the origin to geometry"
                    })

    return issues


def validate_link_suggestions(ai_result, scene_data, vision_analysis):
    """
    Validate AI-generated link suggestions using comprehensive domain knowledge.

    Validation stages:
    1. Conceptual Validation (Hierarchy & Structure)
    2. Naming Convention Validation
    3. Parent-Child Relationship Validation
    4. Pivot/Origin Position Validation
    5. AI-Assisted Structural Validation

    Args:
        ai_result (dict): AI-generated link suggestions
        scene_data (dict): Original scene data
        vision_analysis (str): Visual analysis for context (REQUIRED)

    Returns:
        tuple: (is_valid: bool, validation_report: str, corrected_result: dict)
    """
    global logger
    try:
        if logger:
            logger.section("COMPREHENSIVE LINK VALIDATION")
            logger.info("Stage 1: Conceptual Validation (Hierarchy & Structure)")

        if not vision_analysis:
            if logger:
                logger.error("Vision analysis is required for validation")
            return False, "Vision analysis is required for validation", ai_result

        validation_issues = []
        warnings = []

        links = ai_result.get("links", [])
        all_objects = {obj["name"] for obj in scene_data.get("objects", [])}

        # ===== STAGE 1: CONCEPTUAL VALIDATION =====
        if logger:
            logger.info("  Checking hierarchy cycles...")

        # Check 1.1: Hierarchy cycles
        cycles = check_hierarchy_cycles(scene_data)
        if cycles:
            for cycle in cycles:
                cycle_str = " → ".join(cycle)
                validation_issues.append(f"❌ CYCLE DETECTED: {cycle_str}")
                if logger:
                    logger.error(f"    Cycle: {cycle_str}")
        else:
            if logger:
                logger.info("    ✓ No hierarchy cycles detected")

        # Check 1.2: Minimum number of links
        if logger:
            logger.info("  Checking link count...")
        if len(links) < 1:
            validation_issues.append("❌ ERROR: No links were generated")
        elif len(links) == 1:
            warnings.append("⚠️  WARNING: Only 1 link generated - need at least base + moving components")
        elif len(links) > 10:
            warnings.append(f"⚠️  WARNING: {len(links)} links generated - seems like over-segmentation (most mechanisms have 2-4 links)")
        else:
            if logger:
                logger.info(f"    ✓ {len(links)} links generated (reasonable for most mechanisms)")

        # Check 1.3: All objects assigned
        if logger:
            logger.info("  Checking object assignments...")
        assigned_objects = set()
        for link in links:
            for obj_name in link.get("objects", []):
                assigned_objects.add(obj_name)

        unassigned = all_objects - assigned_objects
        if unassigned:
            warnings.append(f"⚠️  {len(unassigned)} objects not assigned: {', '.join(list(unassigned)[:5])}")
            if logger:
                logger.warning(f"    {len(unassigned)} unassigned objects")
        else:
            if logger:
                logger.info(f"    ✓ All {len(all_objects)} objects assigned")

        # Check 1.4: No duplicate assignments
        object_count = {}
        for link in links:
            for obj_name in link.get("objects", []):
                object_count[obj_name] = object_count.get(obj_name, 0) + 1

        duplicates = {obj: count for obj, count in object_count.items() if count > 1}
        if duplicates:
            validation_issues.append(f"❌ Objects assigned to multiple links: {duplicates}")
            if logger:
                logger.error(f"    Duplicate assignments detected")
        else:
            if logger:
                logger.info("    ✓ No duplicate assignments")

        # Check 1.5: Empty links
        empty_links = [link.get("name", "unnamed") for link in links if not link.get("objects", [])]
        if empty_links:
            validation_issues.append(f"❌ Links with no objects: {', '.join(empty_links)}")

        # ===== STAGE 2: NAMING CONVENTION VALIDATION =====
        if logger:
            logger.info("")
            logger.info("Stage 2: Naming Convention Validation")

        naming_issues = 0
        for link in links:
            link_name = link.get("name", "")
            if not link_name:
                validation_issues.append("❌ Link with no name found")
                naming_issues += 1
            elif not link_name.endswith("_link") and not link_name.endswith("Link"):
                warnings.append(f"ℹ️  Link '{link_name}' doesn't follow naming convention (should end with '_link')")
                naming_issues += 1

        if naming_issues == 0 and logger:
            logger.info("  ✓ All links follow naming conventions")

        # ===== STAGE 3: PARENT-CHILD RELATIONSHIP VALIDATION =====
        if logger:
            logger.info("")
            logger.info("Stage 3: Parent-Child Relationship Validation")

        hierarchy = scene_data.get("hierarchy", [])
        relationship_issues = 0
        for rel in hierarchy:
            parent = rel["parent"]
            child = rel["child"]

            # Find which links contain parent and child
            parent_link = None
            child_link = None

            for link in links:
                if parent in link.get("objects", []):
                    parent_link = link.get("name")
                if child in link.get("objects", []):
                    child_link = link.get("name")

            if parent_link and child_link and parent_link == child_link:
                warnings.append(f"ℹ️  Parent '{parent}' and child '{child}' in same link '{parent_link}' - verify rigid connection")
                relationship_issues += 1

        if relationship_issues == 0 and logger:
            logger.info("  ✓ All parent-child relationships valid")

        # ===== STAGE 4: PIVOT/ORIGIN POSITION VALIDATION =====
        if logger:
            logger.info("")
            logger.info("Stage 4: Pivot/Origin Position Validation")

        pivot_issues = check_pivot_positions(assigned_objects)
        if pivot_issues:
            for issue in pivot_issues:
                warnings.append(f"⚠️  {issue['object']}: {issue['suggestion']} (distance: {issue['distance']:.3f})")
                if logger:
                    logger.warning(f"  {issue['object']}: pivot {issue['distance']:.3f} units from geometry center")
        else:
            if logger:
                logger.info("  ✓ All pivot positions acceptable")

        # ===== STAGE 5: AI-ASSISTED STRUCTURAL VALIDATION =====
        # OPTIMIZATION: Only run AI validation if first 4 stages have no critical issues
        # This saves API calls by focusing AI validation on already-decent structures
        if logger:
            logger.info("")
            logger.info("Stage 5: AI-Assisted Structural Validation")

        if validation_issues:
            # Skip AI validation if basic validations failed
            if logger:
                logger.warning(f"  ⚠️  Skipping AI validation - {len(validation_issues)} critical issues in basic validation")
                logger.warning("  Fix basic validation issues first before AI validation")
        else:
            # Only run AI validation if basic validations passed
            if logger:
                logger.info("  ✓ Basic validations passed - requesting comprehensive AI validation...")

            client = get_azure_client()
            deployment = get_deployment_name()

            if client and deployment:
                validation_prompt = f"""You are an expert in robotic kinematics, SDF/URDF formats, and mechanical validation.

Review the generated link structure against best practices for simulation-ready robot models.

VISUAL ANALYSIS (from multi-angle inspection):
{vision_analysis}

GENERATED LINK STRUCTURE:
{json.dumps(ai_result, indent=2)}

HIERARCHY DATA:
{json.dumps(scene_data.get("hierarchy", []), indent=2)}

COMPREHENSIVE VALIDATION CHECKLIST:

1. **Hierarchy & Structure**
   - Is there a clear base_link (fixed/root)?
   - Are parent-child relationships logical?
   - Are there any circular dependencies?
   - Does the kinematic chain make sense?

2. **Link Separation**
   - Are moving parts separated into different links?
   - Are joints (revolute/prismatic) properly identified?
   - Are rigid connections kept in same link?

3. **Naming & Convention**
   - Are links named descriptively (base_link, arm_link, etc.)?
   - Are joint connection points identifiable?
   - Do names follow standard robotics conventions?

4. **Mechanical Validity**
   - Does the structure match common robot patterns (serial arm, parallel gripper, wheeled base)?
   - Are symmetric parts (left/right) handled correctly?
   - Are degrees of freedom properly accounted for?

5. **SDF/URDF Export Readiness**
   - Will this structure export to valid SDF/URDF?
   - Are there any common pitfalls (floating links, missing base, etc.)?
   - Are inertial properties likely to be computable?

6. **Visual-to-Structure Alignment**
   - Does the link grouping match what you saw in the visual analysis?
   - Are any visual joints missed in the link structure?
   - Are there discrepancies between visual and structural interpretation?

Respond with JSON:
{{
  "is_valid": true/false,
  "confidence": 0-100,
  "structural_score": 0-100,
  "critical_issues": ["blocking issues that prevent export"],
  "warnings": ["issues that may cause problems"],
  "suggestions": ["improvements for better structure"],
  "export_readiness": "ready/needs_fixes/major_issues",
  "kinematic_chain_valid": true/false
}}"""

                try:
                    response = client.chat.completions.create(
                        model=deployment,
                        messages=[
                            {"role": "system", "content": "You are an expert in robotics validation, SDF/URDF formats, and mechanical simulation."},
                            {"role": "user", "content": validation_prompt}
                        ],
                        max_completion_tokens=16000
                    )

                    validation_response = response.choices[0].message.content

                    # Try to parse JSON
                    if "```json" in validation_response:
                        validation_response = validation_response.split("```json")[1].split("```")[0].strip()
                    elif "```" in validation_response:
                        validation_response = validation_response.split("```")[1].split("```")[0].strip()

                    ai_validation = json.loads(validation_response)

                    if logger:
                        logger.info("")
                        logger.info("  AI Validation Results:")
                        logger.info(f"    Overall Valid: {ai_validation.get('is_valid', 'unknown')}")
                        logger.info(f"    Confidence: {ai_validation.get('confidence', 'unknown')}%")
                        logger.info(f"    Structural Score: {ai_validation.get('structural_score', 'unknown')}/100")
                        logger.info(f"    Export Readiness: {ai_validation.get('export_readiness', 'unknown')}")
                        logger.info(f"    Kinematic Chain Valid: {ai_validation.get('kinematic_chain_valid', 'unknown')}")

                    # Add critical issues
                    critical = ai_validation.get("critical_issues", [])
                    if critical:
                        if logger:
                            logger.error(f"    Critical Issues: {len(critical)}")
                        for issue in critical:
                            validation_issues.append(f"❌ CRITICAL: {issue}")

                    # Add warnings from AI
                    ai_warnings = ai_validation.get("warnings", [])
                    if ai_warnings:
                        if logger:
                            logger.warning(f"    Warnings: {len(ai_warnings)}")
                        for warning in ai_warnings:
                            warnings.append(f"⚠️  AI: {warning}")

                    # Add suggestions
                    suggestions = ai_validation.get("suggestions", [])
                    if suggestions:
                        if logger:
                            logger.info(f"    Suggestions: {len(suggestions)}")
                        for suggestion in suggestions:
                            warnings.append(f"💡 SUGGESTION: {suggestion}")

                    # Export readiness check
                    export_status = ai_validation.get("export_readiness", "unknown")
                    if export_status == "major_issues":
                        validation_issues.append("❌ EXPORT: Major issues detected - not ready for SDF/URDF export")
                    elif export_status == "needs_fixes":
                        warnings.append("⚠️  EXPORT: Minor fixes needed before export")
                    elif export_status == "ready":
                        if logger:
                            logger.info("    ✓ Ready for SDF/URDF export")

                except Exception as e:
                    if logger:
                        logger.warning(f"  AI validation failed: {str(e)}")
                    warnings.append(f"⚠️  AI validation could not be performed: {str(e)}")

        # ===== GENERATE COMPREHENSIVE VALIDATION REPORT =====
        if logger:
            logger.info("")
            logger.info("=" * 60)
            logger.info("VALIDATION COMPLETE")
            logger.info("=" * 60)

        report = "=" * 80 + "\n"
        report += "         COMPREHENSIVE LINK VALIDATION REPORT         \n"
        report += "=" * 80 + "\n\n"

        # Summary Section
        report += "📊 SUMMARY\n"
        report += "-" * 80 + "\n"
        report += f"Total Links Generated:     {len(links)}\n"
        report += f"Total Objects in Scene:    {len(all_objects)}\n"
        report += f"Objects Assigned:          {len(assigned_objects)}\n"
        report += f"Objects Unassigned:        {len(unassigned)}\n"
        report += f"Hierarchy Cycles Detected: {len(cycles)}\n"
        report += f"Pivot Issues Found:        {len(pivot_issues)}\n"
        report += "\n"

        # Validation Stages Summary
        report += "✅ VALIDATION STAGES COMPLETED\n"
        report += "-" * 80 + "\n"
        report += "1. ✓ Conceptual Validation (Hierarchy & Structure)\n"
        report += "2. ✓ Naming Convention Validation\n"
        report += "3. ✓ Parent-Child Relationship Validation\n"
        report += "4. ✓ Pivot/Origin Position Validation\n"
        report += "5. ✓ AI-Assisted Structural Validation\n"
        report += "\n"

        # Critical Issues Section
        if validation_issues:
            report += "❌ CRITICAL ISSUES (MUST FIX BEFORE EXPORT)\n"
            report += "-" * 80 + "\n"
            for i, issue in enumerate(validation_issues, 1):
                report += f"{i}. {issue}\n"
            report += "\n"

        # Warnings Section
        if warnings:
            report += "⚠️  WARNINGS & SUGGESTIONS\n"
            report += "-" * 80 + "\n"
            for i, warning in enumerate(warnings, 1):
                report += f"{i}. {warning}\n"
            report += "\n"

        # Success or Needs Attention
        if not validation_issues and not warnings:
            report += "🎉 EXCELLENT! All validation checks passed!\n"
            report += "   Your link structure is ready for SDF/URDF export.\n\n"
        elif not validation_issues:
            report += "✅ VALIDATION PASSED\n"
            report += "   No critical issues found. Review warnings for optimization.\n\n"
        else:
            report += "🔴 VALIDATION FAILED\n"
            report += "   Critical issues detected. Fix issues before proceeding.\n\n"

        # Recommendations
        report += "💡 NEXT STEPS\n"
        report += "-" * 80 + "\n"
        if not validation_issues:
            report += "1. Review any warnings above\n"
            report += "2. Verify link structure in Blender outliner\n"
            report += "3. Check joint positions and orientations\n"
            report += "4. Proceed with SDF/URDF export when ready\n"
            report += "5. Test in Gazebo/Isaac Sim for final validation\n"
        else:
            report += "1. Fix all critical issues listed above\n"
            report += "2. Re-run Auto-Link generation\n"
            report += "3. Verify fixes in Blender\n"
            report += "4. Run validation again\n"

        report += "\n" + "=" * 80 + "\n"

        if logger:
            logger.info("")
            for line in report.split('\n'):
                logger.text_block.write(line + "\n")

        is_valid = len(validation_issues) == 0

        if logger:
            if is_valid:
                logger.info("✅ Validation PASSED - Links are valid")
            else:
                logger.error(f"❌ Validation FAILED - {len(validation_issues)} critical issues")

        return is_valid, report, ai_result

    except Exception as e:
        if logger:
            logger.error(f"Validation error: {str(e)}")
        return False, f"Validation failed: {str(e)}", ai_result


def suggest_fixes_for_validation_issues(ai_result, validation_issues, warnings, scene_data, vision_analysis, iteration_history=None):
    """
    Use AI to suggest fixes for validation issues, taking previous attempts into account.

    Args:
        ai_result (dict): Current link structure
        validation_issues (list): List of critical validation issues
        warnings (list): List of warnings
        scene_data (dict): Scene data
        vision_analysis (str): Visual analysis
        iteration_history (list): Previous iteration results and fixes attempted

    Returns:
        tuple: (success: bool, fixed_result: dict or error message)
    """
    global logger

    try:
        if logger:
            logger.info("")
            logger.info("=" * 60)
            logger.info("REQUESTING AI FIXES FOR VALIDATION ISSUES")
            logger.info("=" * 60)

        client = get_azure_client()
        deployment = get_deployment_name()

        if not client or not deployment:
            return False, "Azure OpenAI not available for fixes"

        # Build iteration history context
        history_context = ""
        if iteration_history and len(iteration_history) > 0:
            history_context = "\n\nPREVIOUS ITERATION HISTORY:\n"
            history_context += "=" * 60 + "\n"
            for i, hist in enumerate(iteration_history, 1):
                history_context += f"\nIteration {i}:\n"
                history_context += f"  Score: {hist.get('score', 'unknown')}\n"
                history_context += f"  Issues: {hist.get('issues_count', 0)}\n"
                history_context += f"  Warnings: {hist.get('warnings_count', 0)}\n"
                if hist.get('fixes_applied'):
                    history_context += f"  Fixes attempted:\n"
                    for fix in hist['fixes_applied'][:5]:  # Limit to avoid token bloat
                        history_context += f"    - {fix}\n"
                if hist.get('remaining_issues'):
                    history_context += f"  Issues that remained:\n"
                    for issue in hist['remaining_issues'][:3]:
                        history_context += f"    - {issue}\n"

            history_context += "\nIMPORTANT: Learn from previous attempts. Don't repeat fixes that didn't work.\n"
            history_context += "Focus on NEW approaches to solve remaining issues.\n"
            history_context += "=" * 60 + "\n"

        fix_prompt = f"""You are an expert in robotic link structure and SDF/URDF generation.

The current link structure has validation issues that need to be fixed.

VISUAL ANALYSIS:
{vision_analysis}

CURRENT LINK STRUCTURE:
{json.dumps(ai_result, indent=2)}

VALIDATION ISSUES:
{json.dumps(validation_issues, indent=2)}

WARNINGS:
{json.dumps(warnings[:10], indent=2)}

SCENE HIERARCHY:
{json.dumps(scene_data.get("hierarchy", []), indent=2)}
{history_context}

TASK:
Analyze the validation issues and provide a CORRECTED link structure that fixes ALL critical issues.

{"CRITICAL: This is not the first attempt. Review the iteration history above." if history_context else ""}
{"Learn from what didn't work before and try a DIFFERENT approach." if history_context else ""}

LINKING PHILOSOPHY:
- Create ONE base_link for all stationary components
- Create ONE link per independently moving component/assembly
- Components that move together = SAME link
- Most mechanisms need only 2-4 links total
- Focus on FUNCTIONAL movement, not individual component boundaries

FIXES TO APPLY:
1. Fix any circular dependencies
2. Ensure proper object assignments (no duplicates, no orphans)
3. Correct naming conventions
4. Group components that move together into the same link
5. Separate independently moving parts into different links
6. Ensure parent-child relationships are logical
7. Avoid over-segmentation (too many links)

Respond with JSON in the EXACT same format as the input:
{{
  "links": [
    {{
      "name": "link_name",
      "objects": ["object1", "object2", ...],
      "reasoning": "why these objects move together as one functional unit"
    }}
  ],
  "suggestions": "what was fixed and why (explain how this differs from previous attempts)",
  "fixes_applied": ["list of specific fixes applied in this iteration"]
}}

CRITICAL:
- Every object must be assigned to exactly ONE link
- Create minimal, functional links (base + moving components only)
- Most mechanisms should have 2-4 links, not 10+
"""

        if logger:
            logger.info("Sending validation issues to AI for fix suggestions...")

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You are an expert in robotics and fixing link structure issues."},
                {"role": "user", "content": fix_prompt}
            ],
            max_completion_tokens=16000
        )

        fix_response = response.choices[0].message.content

        # Parse JSON
        if "```json" in fix_response:
            fix_response = fix_response.split("```json")[1].split("```")[0].strip()
        elif "```" in fix_response:
            fix_response = fix_response.split("```")[1].split("```")[0].strip()

        fixed_result = json.loads(fix_response)

        if logger:
            logger.info("AI provided fixed link structure")
            logger.info(f"  Fixes applied: {len(fixed_result.get('fixes_applied', []))}")
            for fix in fixed_result.get('fixes_applied', []):
                logger.info(f"    - {fix}")

        return True, fixed_result

    except Exception as e:
        if logger:
            logger.error(f"Failed to get AI fixes: {str(e)}")
        return False, f"Failed to get fixes: {str(e)}"


def iterative_validation_and_fix(initial_result, scene_data, vision_analysis, max_iterations=2):
    """
    Iteratively validate and fix link structure until validation passes or max iterations reached.
    Builds iteration history to help AI learn from previous attempts.

    Links should be minimal and functional: base + independently moving components only.
    Most mechanisms should have 2-4 links total.

    Args:
        initial_result (dict): Initial link structure
        scene_data (dict): Scene data
        vision_analysis (str): Visual analysis
        max_iterations (int): Maximum number of fix iterations

    Returns:
        tuple: (final_result: dict, validation_report: str, iteration_count: int)
    """
    global logger

    if logger:
        logger.info("")
        logger.info("=" * 80)
        logger.info("STARTING ITERATIVE VALIDATION & FIX LOOP")
        logger.info("=" * 80)
        logger.info(f"Maximum iterations: {max_iterations}")
        logger.info("Learning from each iteration to improve fixes")

    current_result = initial_result
    iteration = 0
    best_result = initial_result
    best_score = float('inf')  # Lower is better (fewer issues)
    iteration_history = []  # Track what we've tried

    while iteration < max_iterations:
        iteration += 1

        if logger:
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"ITERATION {iteration}/{max_iterations}")
            logger.info("=" * 60)

        # Validate current structure
        is_valid, validation_report, validated_result = validate_link_suggestions(
            current_result, scene_data, vision_analysis
        )

        # Calculate score (number of issues)
        issues_count = validation_report.count("❌")
        warnings_count = validation_report.count("⚠️")
        current_score = issues_count * 10 + warnings_count  # Weight issues more than warnings

        if logger:
            logger.info(f"Validation Score: {current_score} (Issues: {issues_count}, Warnings: {warnings_count})")

        # Extract current issues for history
        validation_issues = []
        warnings_list = []
        for line in validation_report.split('\n'):
            if "❌" in line:
                validation_issues.append(line.strip())
            elif "⚠️" in line:
                warnings_list.append(line.strip())

        # Check if this is the best so far
        if current_score < best_score:
            best_score = current_score
            best_result = current_result
            if logger:
                logger.info("✓ This is the best result so far - score improved!")

        # If validation passed, we're done!
        if is_valid:
            if logger:
                logger.info("")
                logger.info("=" * 60)
                logger.info(f"✅ VALIDATION PASSED ON ITERATION {iteration}")
                logger.info("=" * 60)
            return current_result, validation_report, iteration

        # If this is the last iteration, return best result
        if iteration >= max_iterations:
            if logger:
                logger.info("")
                logger.info("=" * 60)
                logger.info(f"⚠️  MAX ITERATIONS REACHED - RETURNING BEST RESULT")
                logger.info(f"   Best Score: {best_score} (achieved in earlier iteration)")
                logger.info("=" * 60)
            # Re-validate best result to get its report
            _, final_report, _ = validate_link_suggestions(best_result, scene_data, vision_analysis)
            return best_result, final_report, iteration

        if logger:
            logger.info(f"Found {len(validation_issues)} critical issues to fix")

        # Record this iteration before requesting fixes
        iteration_record = {
            "iteration": iteration,
            "score": current_score,
            "issues_count": issues_count,
            "warnings_count": warnings_count,
            "fixes_applied": current_result.get("fixes_applied", []),
            "remaining_issues": validation_issues[:5]  # Limit to top 5 to save tokens
        }
        iteration_history.append(iteration_record)

        if logger and len(iteration_history) > 1:
            logger.info(f"Learning from {len(iteration_history)} previous iteration(s)")

        # Get AI to suggest fixes, passing iteration history
        fix_success, fix_result = suggest_fixes_for_validation_issues(
            current_result, validation_issues, warnings_list, scene_data, vision_analysis,
            iteration_history=iteration_history
        )

        if not fix_success:
            if logger:
                logger.warning(f"Failed to get fixes: {fix_result}")
                logger.info("Returning best result so far")
            # Re-validate best result
            _, final_report, _ = validate_link_suggestions(best_result, scene_data, vision_analysis)
            return best_result, final_report, iteration

        # Use fixed result for next iteration
        current_result = fix_result

        if logger:
            logger.info(f"Proceeding to iteration {iteration + 1} with AI-suggested fixes")

    # Should not reach here, but return best result just in case
    _, final_report, _ = validate_link_suggestions(best_result, scene_data, vision_analysis)
    return best_result, final_report, iteration


def cleanup_existing_autolinks():
    """
    Remove existing auto-generated link collections to prevent duplicates.

    Returns:
        int: Number of collections removed
    """
    global logger
    removed_count = 0

    if logger:
        logger.info("Checking for existing auto-generated links...")

    # Find all LinkCollection type collections
    collections_to_remove = []
    for collection in bpy.data.collections:
        if hasattr(collection, 'collection_type') and collection.collection_type == "LinkCollection":
            collections_to_remove.append(collection)

    if collections_to_remove:
        if logger:
            logger.info(f"Found {len(collections_to_remove)} existing link collections to clean up")

        for collection in collections_to_remove:
            try:
                # Remove child collections first
                for child in list(collection.children):
                    if logger:
                        logger.info(f"  Removing child collection: {child.name}")
                    bpy.data.collections.remove(child)

                # Remove the link collection itself
                if logger:
                    logger.info(f"  Removing link collection: {collection.name}")
                bpy.data.collections.remove(collection)
                removed_count += 1

            except Exception as e:
                if logger:
                    logger.warning(f"  Failed to remove {collection.name}: {str(e)}")

        if logger:
            logger.info(f"Cleaned up {removed_count} existing link collections")
    else:
        if logger:
            logger.info("No existing link collections found - starting fresh")

    return removed_count


def create_links_from_ai_suggestion(ai_result):
    """
    Automatically create link collections based on AI suggestions.

    Args:
        ai_result (dict): Parsed AI response with link suggestions

    Returns:
        tuple: (success: bool, message: str)
    """
    global logger
    try:
        if logger:
            logger.section("CREATING LINK COLLECTIONS")
            logger.info("Starting link creation from AI suggestions...")

        # Clean up existing auto-generated links first
        cleanup_existing_autolinks()

        links_created = []
        errors = []

        for link_suggestion in ai_result.get("links", []):
            if logger:
                logger.info(f"Processing link: {link_suggestion.get('name', 'unnamed')}")
            link_name = link_suggestion.get("name", "unnamed_link")
            objects = link_suggestion.get("objects", [])

            if not objects:
                errors.append(f"Link '{link_name}' has no objects, skipping")
                if logger:
                    logger.warning(f"Link '{link_name}' has no objects, skipping")
                continue

            if logger:
                logger.info(f"  Objects: {', '.join(objects)}")
                logger.info(f"  Reasoning: {link_suggestion.get('reasoning', 'N/A')}")

            # Create link collection
            try:
                if logger:
                    logger.info(f"  Creating collection structure for '{link_name}'...")
                link_collection = bpy.data.collections.new(f"{link_name}_link")
                bpy.context.scene.collection.children.link(link_collection)
                link_collection.collection_type = "LinkCollection"

                # Create visual collection
                visual_collection = bpy.data.collections.new(f"{link_name}_visual")
                link_collection.children.link(visual_collection)
                visual_collection.collection_type = "VisualCollection"

                # Create collider collection
                collider_collection = bpy.data.collections.new(f"{link_name}_colliders")
                link_collection.children.link(collider_collection)
                collider_collection.collection_type = "ColliderCollection"

                # Move objects to visual collection
                objects_moved = 0
                for obj_name in objects:
                    obj = bpy.data.objects.get(obj_name)
                    if obj:
                        # First, link to new visual collection
                        if obj.name not in visual_collection.objects:
                            visual_collection.objects.link(obj)

                        # Then remove from current collections (except the new one)
                        # Create a list copy to avoid modification during iteration
                        old_collections = [col for col in obj.users_collection if col != visual_collection]
                        for col in old_collections:
                            try:
                                col.objects.unlink(obj)
                            except Exception as e:
                                # Some collections might not allow unlinking, skip them
                                pass

                        objects_moved += 1
                        if logger:
                            logger.info(f"    Moved object '{obj_name}' to visual collection")
                    else:
                        errors.append(f"Object '{obj_name}' not found for link '{link_name}'")
                        if logger:
                            logger.warning(f"    Object '{obj_name}' not found")

                links_created.append(f"{link_name} ({objects_moved} objects)")
                if logger:
                    logger.info(f"  Successfully created link '{link_name}' with {objects_moved} objects")

            except Exception as e:
                errors.append(f"Failed to create link '{link_name}': {str(e)}")
                if logger:
                    logger.error(f"  Failed to create link '{link_name}': {str(e)}")

        # Prepare result message
        if links_created:
            message = f"Created {len(links_created)} links:\n" + "\n".join(f"  • {link}" for link in links_created)
            if errors:
                message += f"\n\nWarnings:\n" + "\n".join(f"  • {err}" for err in errors)

            if logger:
                logger.section("LINK CREATION SUMMARY")
                logger.info(f"Successfully created {len(links_created)} links")
                logger.info("")
                for link in links_created:
                    logger.info(f"  ✓ {link}")
                if errors:
                    logger.info("")
                    logger.info(f"Warnings: {len(errors)}")
                    for err in errors:
                        logger.warning(f"  ! {err}")

            return True, message
        else:
            if logger:
                logger.error("No links created")
                for err in errors:
                    logger.error(f"  {err}")
            return False, "No links created. Errors:\n" + "\n".join(f"  • {err}" for err in errors)

    except Exception as e:
        if logger:
            logger.error(f"Exception creating links: {str(e)}")
        return False, f"Error creating links: {str(e)}"


class SDFG_OT_AutoGenerateLinks(bpy.types.Operator):
    """Automatically generate links using AI analysis"""

    bl_idname = "scene.auto_generate_links"
    bl_label = "Auto-Generate Links (AI)"
    bl_description = "Analyze scene and automatically create link collections using Azure OpenAI"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global logger
        import time

        # Start timing
        start_time = time.time()
        total_tokens = 0

        # Initialize logger
        logger = BlenderTextLogger("Auto-Link Log")
        logger.info("Auto-Generate Links operator started")
        logger.info("")

        # Check Azure OpenAI connection
        client = get_azure_client()
        if not client:
            logger.error("Azure OpenAI not connected")
            logger.show_in_editor()
            self.report({'ERROR'}, "Azure OpenAI not connected. Check UTILITIES tab.")
            return {'CANCELLED'}

        logger.info("Azure OpenAI connection verified")
        logger.info("")

        # Step 1: Capture viewport images from fixed comprehensive angles (REQUIRED)
        logger.section("STEP 1: COMPREHENSIVE VISUAL CAPTURE")
        self.report({'INFO'}, "Capturing viewport images from multiple fixed angles...")

        image_paths = capture_viewport_images()

        if not image_paths or len(image_paths) == 0:
            logger.error("Failed to capture viewport images")
            logger.error("Visual analysis is required for auto-link generation")
            logger.show_in_editor()
            self.report({'ERROR'}, "Image capture failed - check console for details")
            show_message_box(
                message="Failed to capture viewport images.\n\nPossible causes:\n• No mesh objects in scene\n• Viewport rendering error\n\nCheck 'Auto-Link Log' for details.",
                title="Visual Capture Failed",
                icon="ERROR"
            )
            return {'CANCELLED'}

        logger.info(f"Successfully captured {len(image_paths)} viewport images")

        # Step 2: Analyze images with AI (REQUIRED)
        logger.info("")
        logger.section("STEP 2: VISUAL ANALYSIS")
        self.report({'INFO'}, "Analyzing model structure from images...")

        vision_success, vision_result, vision_tokens = analyze_images_with_ai(image_paths)
        total_tokens += vision_tokens

        if not vision_success:
            logger.error(f"Visual analysis failed: {vision_result}")
            logger.error("Visual analysis is required for auto-link generation")
            logger.show_in_editor()
            self.report({'ERROR'}, f"Visual analysis failed: {vision_result}")
            show_message_box(
                message=f"Visual Analysis Failed:\n\n{vision_result}\n\nCheck 'Auto-Link Log' for details.",
                title="Visual Analysis Failed",
                icon="ERROR"
            )
            return {'CANCELLED'}

        vision_analysis = vision_result
        logger.info("Visual analysis completed successfully")
        self.report({'INFO'}, "Visual analysis complete - proceeding with link generation")

        # Step 3: Extract scene data
        logger.info("")
        logger.section("STEP 3: SCENE DATA EXTRACTION")
        self.report({'INFO'}, "Extracting scene data...")
        scene_data = extract_model_data()

        if not scene_data["objects"]:
            logger.error("No objects found in scene")
            logger.show_in_editor()
            self.report({'ERROR'}, "No objects found in scene to analyze")
            return {'CANCELLED'}

        # Step 4: Analyze with AI (combining vision + scene data)
        logger.info("")
        logger.section("STEP 4: AI LINK GENERATION")
        self.report({'INFO'}, f"Generating link suggestions for {len(scene_data['objects'])} objects...")
        success, result = analyze_scene_with_ai(scene_data, vision_analysis)

        if not success:
            logger.error(f"AI analysis failed: {result}")
            logger.show_in_editor()
            self.report({'ERROR'}, f"AI analysis failed: {result}")
            show_message_box(
                message=f"AI Analysis Failed:\n\n{result}",
                title="Auto-Link Generation Error",
                icon="ERROR"
            )
            return {'CANCELLED'}

        # Extract tokens from result
        total_tokens += result.get('_tokens_used', 0)

        logger.info(f"AI generated {len(result.get('links', []))} link suggestions")

        # Step 5: Iterative Validation & Fixing
        logger.info("")
        logger.section("STEP 5: ITERATIVE VALIDATION & FIXING")
        self.report({'INFO'}, "Running iterative validation and fixing...")

        final_result, validation_report, iterations_used = iterative_validation_and_fix(
            result, scene_data, vision_analysis, max_iterations=2
        )

        logger.info("")
        logger.info(f"Iterative process completed after {iterations_used} iteration(s)")

        # Check final validation status
        is_valid = "VALIDATION PASSED" in validation_report or validation_report.count("❌") == 0

        if is_valid:
            logger.info("✅ Final validation PASSED - links are ready")
        else:
            logger.warning("⚠️  Some issues remain - using best result from iterations")

        # Step 6: Create links
        logger.info("")
        logger.section("STEP 6: LINK CREATION")
        self.report({'INFO'}, "Creating link collections...")
        success, message = create_links_from_ai_suggestion(final_result)

        if success:
            logger.info("")
            logger.info("=" * 80)
            logger.info("AUTO-LINK GENERATION COMPLETED SUCCESSFULLY")
            logger.info("=" * 80)
            logger.info("")
            logger.info("VALIDATION SUMMARY:")
            logger.separator("-", 60)
            for line in validation_report.split('\n'):
                logger.text_block.write(line + "\n")

            # Show log in text editor
            logger.show_in_editor()

            self.report({'INFO'}, "Links created successfully")

            final_message = message
            final_message += f"\n\nIterations: {iterations_used}"
            final_message += f"\nFinal Status: {'✅ Validated' if is_valid else '⚠️ Best Effort'}"
            final_message += f"\n\nAI Suggestions:\n{final_result.get('suggestions', 'None')}"
            final_message += "\n\n📄 Full log with iteration details in 'Auto-Link Log' text"

            show_message_box(
                message=final_message,
                title="Auto-Link Generation Complete",
                icon="INFO"
            )
        else:
            logger.error("")
            logger.error("=" * 80)
            logger.error("AUTO-LINK GENERATION FAILED")
            logger.error("=" * 80)

            # Show log in text editor
            logger.show_in_editor()

            self.report({'ERROR'}, message)
            show_message_box(
                message=message + "\n\n📄 Check 'Auto-Link Log' text for full details",
                title="Auto-Link Generation Error",
                icon="ERROR"
            )

        # Calculate and save statistics
        elapsed_time = time.time() - start_time
        context.scene.autolink_time_taken = elapsed_time
        context.scene.autolink_tokens_used = total_tokens
        context.scene.autolink_stats_available = True

        logger.info("")
        logger.info("=" * 80)
        logger.info("STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Total Time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
        logger.info(f"Total Tokens Used: {total_tokens:,}")
        logger.info("")

        # Refresh UI
        if context.area:
            context.area.tag_redraw()

        return {'FINISHED'}


class SDFG_OT_ViewAutoLinkLog(bpy.types.Operator):
    """View the Auto-Link generation log"""

    bl_idname = "scene.view_autolink_log"
    bl_label = "View Auto-Link Log"
    bl_description = "Open the Auto-Link generation log in the text editor"
    bl_options = {"REGISTER"}

    def execute(self, context):
        # Check if log exists
        if "Auto-Link Log" in bpy.data.texts:
            log_text = bpy.data.texts["Auto-Link Log"]

            # Try to find or create text editor area
            text_editor_found = False
            for area in context.screen.areas:
                if area.type == 'TEXT_EDITOR':
                    area.spaces[0].text = log_text
                    text_editor_found = True
                    self.report({'INFO'}, "Log opened in text editor")
                    break

            if not text_editor_found:
                # Change current area to text editor
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.type = 'TEXT_EDITOR'
                        area.spaces[0].text = log_text
                        self.report({'INFO'}, "Log opened in text editor")
                        break

            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No Auto-Link log found. Run Auto-Link first.")
            return {'CANCELLED'}


class SDFG_OT_ViewValidationLog(bpy.types.Operator):
    """View the Link Validation log"""

    bl_idname = "scene.view_validation_log"
    bl_label = "View Validation Log"
    bl_description = "Open the Link Validation log in the text editor"
    bl_options = {"REGISTER"}

    def execute(self, context):
        # Check if log exists
        if "Link Validation Log" in bpy.data.texts:
            log_text = bpy.data.texts["Link Validation Log"]

            # Try to find or create text editor area
            text_editor_found = False
            for area in context.screen.areas:
                if area.type == 'TEXT_EDITOR':
                    area.spaces[0].text = log_text
                    text_editor_found = True
                    self.report({'INFO'}, "Validation log opened in text editor")
                    break

            if not text_editor_found:
                # Change current area to text editor
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.type = 'TEXT_EDITOR'
                        area.spaces[0].text = log_text
                        self.report({'INFO'}, "Validation log opened in text editor")
                        break

            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No validation log found. Run 'Validate Links' first.")
            return {'CANCELLED'}


def extract_existing_link_structure():
    """
    Extract existing link structure from the Blender scene.

    Returns:
        dict: Link structure in AI result format, or None if no links found
    """
    global logger

    if logger:
        logger.info("Extracting existing link structure from scene...")

    links = []

    # Find all LinkCollection type collections
    for collection in bpy.data.collections:
        if hasattr(collection, 'collection_type') and collection.collection_type == "LinkCollection":
            # Find the visual collection child
            visual_collection = None
            for child in collection.children:
                if hasattr(child, 'collection_type') and child.collection_type == "VisualCollection":
                    visual_collection = child
                    break

            if visual_collection:
                # Extract objects from visual collection
                objects = [obj.name for obj in visual_collection.objects]

                # Extract link name (remove _link suffix if present)
                link_name = collection.name
                if link_name.endswith("_link"):
                    link_name = link_name[:-5]  # Remove _link suffix for clean name

                links.append({
                    "name": link_name,
                    "objects": objects,
                    "reasoning": "Existing link structure from scene"
                })

                if logger:
                    logger.info(f"  Found link: {link_name} with {len(objects)} objects")

    if not links:
        if logger:
            logger.warning("No existing link collections found in scene")
        return None

    if logger:
        logger.info(f"Extracted {len(links)} existing links from scene")

    return {
        "links": links,
        "suggestions": "Validation of existing link structure"
    }


class SDFG_OT_ValidateLinksOnly(bpy.types.Operator):
    """Validate existing link structure without regenerating"""

    bl_idname = "scene.validate_links_only"
    bl_label = "Validate Existing Links"
    bl_description = "Run comprehensive validation on existing link structure in the scene"
    bl_options = {"REGISTER"}

    def execute(self, context):
        global logger

        # Initialize logger
        logger = BlenderTextLogger("Link Validation Log")
        logger.info("Link Validation operator started")
        logger.info("")

        # Check if there are existing links
        logger.section("EXTRACTING EXISTING LINK STRUCTURE")
        self.report({'INFO'}, "Extracting existing links...")

        existing_links = extract_existing_link_structure()

        if not existing_links:
            logger.error("No existing link collections found in scene")
            logger.error("Please create links first using 'Auto-Generate Links' or manually")
            logger.show_in_editor()
            self.report({'ERROR'}, "No link collections found in scene")
            show_message_box(
                message="No link collections found in scene.\n\nPlease:\n• Run 'Auto-Generate Links' first, OR\n• Create link collections manually\n\nCheck 'Link Validation Log' for details.",
                title="No Links Found",
                icon="ERROR"
            )
            return {'CANCELLED'}

        logger.info(f"Found {len(existing_links['links'])} existing links to validate")

        # Extract scene data
        logger.info("")
        logger.section("EXTRACTING SCENE DATA")
        self.report({'INFO'}, "Extracting scene data...")
        scene_data = extract_model_data()

        if not scene_data["objects"]:
            logger.error("No objects found in scene")
            logger.show_in_editor()
            self.report({'ERROR'}, "No objects found in scene")
            return {'CANCELLED'}

        # Capture and analyze with vision (optional for validation)
        logger.info("")
        logger.section("VISUAL ANALYSIS (OPTIONAL)")
        self.report({'INFO'}, "Attempting visual analysis...")

        vision_analysis = None
        try:
            # Check Azure OpenAI connection
            client = get_azure_client()
            if client:
                image_paths = capture_viewport_images()

                if image_paths and len(image_paths) > 0:
                    vision_success, vision_result, _ = analyze_images_with_ai(image_paths)
                    if vision_success:
                        vision_analysis = vision_result
                        logger.info("Visual analysis successful - will enhance validation")
                    else:
                        logger.warning("Visual analysis failed - will validate without visual context")
                else:
                    logger.warning("Could not capture images - will validate without visual context")
            else:
                logger.warning("Azure OpenAI not connected - will validate without visual context")
        except Exception as e:
            logger.warning(f"Visual analysis error: {str(e)} - continuing without visual context")

        # If no vision analysis, create a placeholder
        if not vision_analysis:
            vision_analysis = "Visual analysis not available - validation based on structure only"
            logger.info("Proceeding with structure-only validation")

        # Run validation
        logger.info("")
        logger.section("RUNNING COMPREHENSIVE VALIDATION")
        self.report({'INFO'}, "Validating link structure...")

        is_valid, validation_report, validated_result = validate_link_suggestions(
            existing_links, scene_data, vision_analysis
        )

        # Show results
        logger.info("")
        logger.info("=" * 80)
        if is_valid:
            logger.info("VALIDATION COMPLETED - LINKS ARE VALID ✅")
        else:
            logger.info("VALIDATION COMPLETED - ISSUES FOUND ❌")
        logger.info("=" * 80)

        # Show log in text editor
        logger.show_in_editor()

        # Prepare user message
        if is_valid:
            self.report({'INFO'}, "Validation passed - links are valid")
            message = "✅ Validation PASSED!\n\n"
            message += f"Validated {len(existing_links['links'])} links.\n"
            message += "No critical issues found.\n\n"
            message += "📄 Full validation report in 'Link Validation Log' text"
            icon = "INFO"
        else:
            self.report({'WARNING'}, "Validation found issues")
            message = "⚠️ Validation found issues!\n\n"
            message += f"Validated {len(existing_links['links'])} links.\n"
            message += "Critical issues detected.\n\n"
            message += "📄 Check 'Link Validation Log' for details"
            icon = "ERROR"

        show_message_box(
            message=message,
            title="Link Validation Results",
            icon=icon
        )

        # Refresh UI
        if context.area:
            context.area.tag_redraw()

        return {'FINISHED'}


class SDFG_OT_AnalyzeSceneOnly(bpy.types.Operator):
    """Analyze scene with AI without creating links (preview mode)"""

    bl_idname = "scene.analyze_scene_only"
    bl_label = "Preview AI Analysis"
    bl_description = "Analyze scene with AI and show suggestions without creating links"
    bl_options = {"REGISTER"}

    def execute(self, context):
        global logger

        # Initialize logger for preview
        logger = BlenderTextLogger("Auto-Link Preview Log")
        logger.info("Preview AI Analysis started")
        logger.info("")

        # Check Azure OpenAI connection
        client = get_azure_client()
        if not client:
            logger.error("Azure OpenAI not connected")
            self.report({'ERROR'}, "Azure OpenAI not connected. Check UTILITIES tab.")
            return {'CANCELLED'}

        # Capture and analyze images from fixed comprehensive angles (REQUIRED)
        logger.section("COMPREHENSIVE VISUAL CAPTURE & ANALYSIS")
        self.report({'INFO'}, "Capturing viewport images from multiple fixed angles...")

        image_paths = capture_viewport_images()

        if not image_paths or len(image_paths) == 0:
            logger.error("Failed to capture viewport images")
            logger.error("Visual analysis is required for preview")
            logger.show_in_editor()
            self.report({'ERROR'}, "Image capture failed - check console for details")
            show_message_box(
                message="Failed to capture viewport images.\n\nCheck 'Auto-Link Preview Log' for details.",
                title="Visual Capture Failed",
                icon="ERROR"
            )
            return {'CANCELLED'}

        self.report({'INFO'}, "Analyzing images with AI...")
        vision_success, vision_result, _ = analyze_images_with_ai(image_paths)

        if not vision_success:
            logger.error(f"Visual analysis failed: {vision_result}")
            logger.error("Visual analysis is required for preview")
            logger.show_in_editor()
            self.report({'ERROR'}, f"Visual analysis failed: {vision_result}")
            show_message_box(
                message=f"Visual Analysis Failed:\n\n{vision_result}\n\nCheck 'Auto-Link Preview Log' for details.",
                title="Visual Analysis Failed",
                icon="ERROR"
            )
            return {'CANCELLED'}

        vision_analysis = vision_result
        logger.info("Visual analysis successful")

        # Extract scene data
        logger.info("")
        logger.section("SCENE DATA EXTRACTION")
        scene_data = extract_model_data()

        if not scene_data["objects"]:
            logger.error("No objects found in scene")
            self.report({'ERROR'}, "No objects found in scene to analyze")
            return {'CANCELLED'}

        self.report({'INFO'}, "Generating link suggestions...")

        # Analyze with AI
        success, result = analyze_scene_with_ai(scene_data, vision_analysis)

        if not success:
            logger.error(f"AI analysis failed: {result}")
            self.report({'ERROR'}, f"AI analysis failed: {result}")
            show_message_box(
                message=f"AI Analysis Failed:\n\n{result}",
                title="Scene Analysis Error",
                icon="ERROR"
            )
            return {'CANCELLED'}

        # Validate suggestions
        logger.info("")
        logger.section("VALIDATION")
        is_valid, validation_report, validated_result = validate_link_suggestions(
            result, scene_data, vision_analysis
        )

        # Format results for display
        links_summary = []
        for link in result.get("links", []):
            links_summary.append(f"• {link['name']}: {len(link['objects'])} objects")

        message = "AI Analysis Results:\n\n"
        message += "Suggested Links:\n" + "\n".join(links_summary)
        message += f"\n\nSuggestions:\n{result.get('suggestions', 'None')}"
        message += f"\n\nValidation: {'✅ Passed' if is_valid else '⚠️ Issues Found'}"
        message += "\n\nUse 'Auto-Generate Links' to create these links."
        message += "\n\n📄 Full analysis available in 'Auto-Link Preview Log' text"

        logger.info("")
        logger.info("=" * 80)
        logger.info("PREVIEW ANALYSIS COMPLETE")
        logger.info("=" * 80)

        # Show log in editor
        logger.show_in_editor()

        self.report({'INFO'}, f"Analysis complete: {len(result.get('links', []))} links suggested")
        show_message_box(
            message=message,
            title="Scene Analysis Preview",
            icon="INFO"
        )

        return {'FINISHED'}
