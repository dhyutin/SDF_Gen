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


def capture_viewport_images(num_angles=4):
    """
    Capture viewport images from multiple angles around the scene using safe camera-based rendering.

    Args:
        num_angles (int): Number of different angles to capture (2-5 recommended)

    Returns:
        list: List of file paths to the captured images
    """
    global logger
    import tempfile
    import os
    import math

    if logger:
        logger.info(f"Capturing {num_angles} viewport images from different angles...")

    image_paths = []
    temp_dir = tempfile.gettempdir()
    temp_camera = None

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

        # Set render settings for capture
        bpy.context.scene.render.resolution_x = 1024  # Reasonable size
        bpy.context.scene.render.resolution_y = 1024
        bpy.context.scene.render.image_settings.file_format = 'PNG'

        # Capture from different angles
        for i in range(num_angles):
            try:
                angle = (2 * math.pi * i) / num_angles

                # Position camera in a circle around the model
                cam_distance = size * 2.0  # Increased distance for safety
                cam_x = center.x + cam_distance * math.cos(angle)
                cam_y = center.y + cam_distance * math.sin(angle)
                cam_z = center.z + size * 0.5  # Slightly elevated

                # Set camera location
                temp_camera.location = Vector((cam_x, cam_y, cam_z))

                # Point camera at center
                direction = center - temp_camera.location
                rot_quat = direction.to_track_quat('-Z', 'Y')
                temp_camera.rotation_euler = rot_quat.to_euler()

                # Render image
                image_path = os.path.join(temp_dir, f"blender_view_angle_{i}.png")
                bpy.context.scene.render.filepath = image_path

                # Use OpenGL render (faster and safer than full render)
                bpy.ops.render.opengl(write_still=True)

                if os.path.exists(image_path):
                    image_paths.append(image_path)
                    if logger:
                        logger.info(f"  Captured angle {i+1}/{num_angles}: {image_path}")
                else:
                    if logger:
                        logger.warning(f"  Failed to create image for angle {i+1}")

            except Exception as e:
                if logger:
                    logger.warning(f"  Error capturing angle {i+1}: {str(e)}")
                continue

        # Restore original settings
        bpy.context.scene.camera = original_camera
        bpy.context.scene.render.resolution_x = original_resolution_x
        bpy.context.scene.render.resolution_y = original_resolution_y
        bpy.context.scene.render.image_settings.file_format = original_file_format

        # Clean up temporary camera
        if temp_camera:
            bpy.data.objects.remove(temp_camera, do_unlink=True)
            bpy.data.cameras.remove(camera_data, do_unlink=True)

        if logger:
            logger.info(f"Successfully captured {len(image_paths)} images")

        return image_paths

    except Exception as e:
        if logger:
            logger.error(f"Error during image capture: {str(e)}")

        # Cleanup on error
        try:
            if temp_camera and temp_camera.name in bpy.data.objects:
                bpy.context.scene.camera = original_camera
                bpy.data.objects.remove(temp_camera, do_unlink=True)
                if camera_data and camera_data.name in bpy.data.cameras:
                    bpy.data.cameras.remove(camera_data, do_unlink=True)
        except:
            pass

        return []


def analyze_images_with_ai(image_paths, cleanup_images=True):
    """
    Analyze captured viewport images using Azure OpenAI vision capabilities.

    Args:
        image_paths (list): List of file paths to captured images
        cleanup_images (bool): Whether to delete temporary images after analysis

    Returns:
        tuple: (success: bool, analysis: str or error message)
    """
    global logger
    import base64
    import os

    try:
        if logger:
            logger.section("VISUAL ANALYSIS WITH AI")
            logger.info(f"Analyzing {len(image_paths)} images...")

        # Get Azure OpenAI client
        client = get_azure_client()
        deployment = get_deployment_name()

        if not client or not deployment:
            if logger:
                logger.error("Azure OpenAI not configured")
            return False, "Azure OpenAI not configured"

        # Encode images to base64 with size limits
        encoded_images = []
        MAX_IMAGE_SIZE_MB = 5  # Limit to 5MB per image to prevent memory issues

        for img_path in image_paths:
            try:
                # Check if file exists and size is reasonable
                if not os.path.exists(img_path):
                    if logger:
                        logger.warning(f"  Image not found: {img_path}")
                    continue

                file_size_mb = os.path.getsize(img_path) / (1024 * 1024)
                if file_size_mb > MAX_IMAGE_SIZE_MB:
                    if logger:
                        logger.warning(f"  Image too large ({file_size_mb:.2f}MB): {img_path}")
                    continue

                with open(img_path, "rb") as img_file:
                    image_data = img_file.read()
                    encoded_image = base64.b64encode(image_data).decode('utf-8')
                    encoded_images.append(encoded_image)
                    if logger:
                        logger.info(f"  Encoded image ({file_size_mb:.2f}MB): {img_path}")

            except Exception as e:
                if logger:
                    logger.warning(f"  Failed to encode {img_path}: {str(e)}")
                continue

        if not encoded_images:
            if logger:
                logger.warning("No images were successfully encoded")
            return False, "No images were successfully encoded"

        # Create vision analysis prompt
        vision_prompt = """You are an expert in robotic kinematics, mechanical engineering, and CAD analysis.

You are viewing multiple angles of a 3D mechanical model/robot. Your task is to:

1. **Identify the mechanical structure:**
   - What type of mechanism is this? (robotic arm, gripper, wheeled robot, articulated mechanism, etc.)
   - How many distinct rigid bodies (links) do you see?
   - Where are the joints/connection points between moving parts?

2. **Analyze kinematic structure:**
   - Which parts move independently from each other?
   - Which parts are rigidly connected (move together as one link)?
   - What types of joints connect the parts? (revolute/hinge, prismatic/slider, fixed, etc.)

3. **Provide link grouping strategy:**
   - Based on VISUAL INSPECTION ONLY, suggest how objects should be grouped into links
   - Identify the base/fixed link (usually the largest stationary part)
   - Identify moving links and their hierarchy (parent-child relationships)
   - Note any symmetric structures (left/right arms, multiple wheels, etc.)

4. **Domain knowledge validation:**
   - Does this structure follow standard robotic conventions?
   - Are there any unusual configurations that need special attention?
   - What potential issues might arise in link generation?

IMPORTANT GUIDELINES:
- Each RIGID BODY should be a separate link
- Parts connected by joints should be DIFFERENT links
- Parts that move together should be in the SAME link
- Most mechanisms have 3+ separate links minimum
- Look for visual clues: gaps between parts indicate joints, connected/welded parts indicate same link

Provide a detailed visual analysis focusing on the mechanical structure and how it should be divided into links for SDF export."""

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

            if not response or not response.choices:
                if logger:
                    logger.error("Empty response from API")
                    logger.error(f"  Response: {response}")
                return False, "Empty response from vision API"

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
                return False, "Vision analysis returned empty content"

            if logger:
                logger.info("")
                logger.info("VISION ANALYSIS RESULT:")
                logger.separator("-", 60)
                for line in analysis.split('\n'):
                    logger.text_block.write(line + "\n")
                logger.separator("-", 60)

            # Cleanup temporary images if requested
            if cleanup_images:
                cleanup_temp_images(image_paths)

            return True, analysis

        except TimeoutError:
            if logger:
                logger.error("Vision analysis timed out after 60 seconds")
            # Cleanup on error
            if cleanup_images:
                cleanup_temp_images(image_paths)
            return False, "Vision analysis timed out - try reducing number of images"

        except Exception as api_error:
            if logger:
                logger.error(f"API call failed: {str(api_error)}")
            # Cleanup on error
            if cleanup_images:
                cleanup_temp_images(image_paths)
            return False, f"Vision API call failed: {str(api_error)}"

    except Exception as e:
        if logger:
            logger.error(f"Error during vision analysis: {str(e)}")
        # Cleanup on error
        if cleanup_images:
            cleanup_temp_images(image_paths)
        return False, f"Error during vision analysis: {str(e)}"


def cleanup_temp_images(image_paths):
    """
    Clean up temporary image files.

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
            obj_data = {
                "name": obj.name,
                "type": obj.type,
                "location": list(obj.location),
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

    if logger:
        logger.info(f"Extracted {len(scene_data['objects'])} objects")
        logger.info(f"Extracted {len(scene_data['hierarchy'])} hierarchy relationships")
        logger.info(f"Extracted {len(scene_data['collections'])} collections")
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
        formatted += f"  Location: ({obj['location'][0]:.3f}, {obj['location'][1]:.3f}, {obj['location'][2]:.3f})\n"
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

    return formatted


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

CONTEXT:
- A "link" is a rigid body part of a mechanism (like an arm segment, wheel, chassis, etc.)
- Objects that move together as one rigid unit should be in the same link
- Links are connected by joints (revolute, prismatic, fixed, etc.)
- Each link should have a descriptive name based on its function or position

{vision_context}

IMPORTANT RULES:
1. **DO NOT put all objects into a single link** - analyze the structure carefully
2. **Separate moving parts** - Different moving parts should be different links
3. **Look for joints** - Objects separated by joints should be in different links
4. **Parent-child relationships** often indicate separate links connected by joints
5. **Create multiple links** - Most mechanisms have 3+ separate links minimum
6. **Use visual analysis** - If provided, visual analysis should guide your grouping decisions

ANALYSIS GUIDELINES:
1. **Object Names**: Look for keywords like "base", "arm", "link", "joint", "wheel", "chassis", "gripper"
2. **Hierarchy**: Parent-child relationships usually mean separate links with a joint between them
3. **Constraints**: Objects with CHILD_OF or similar constraints are likely separate links
4. **Naming Patterns**:
   - Objects with numbers (arm_1, arm_2) are usually separate links
   - Objects with position names (left, right, upper, lower) are usually separate links
   - Objects with "joint" in the name are connection points between links

SCENE DATA:
{formatted_data}

TASK:
Analyze this scene and suggest link groupings. Create MULTIPLE separate links based on the structure.
If visual analysis is provided above, use it as the PRIMARY guide for link separation.

Examples of good link separation:
- For a robotic arm: base_link, shoulder_link, upper_arm_link, forearm_link, wrist_link, gripper_link
- For a wheeled robot: chassis_link, wheel_left_link, wheel_right_link
- For a gripper: palm_link, finger_left_link, finger_right_link

Respond ONLY with valid JSON in this exact format:
{{
  "links": [
    {{
      "name": "link_name",
      "objects": ["object1", "object2"],
      "reasoning": "why these specific objects form this link"
    }}
  ],
  "suggestions": "observations about the kinematic structure"
}}

CRITICAL:
- Create SEPARATE links for each movable component
- If you see parent-child relationships, create separate links for parent and child
- DO NOT group the entire model into one "base_link"
- Aim for at least 3-5 links for a typical mechanism
- Every object should be assigned to exactly one link
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


def validate_link_suggestions(ai_result, scene_data, vision_analysis):
    """
    Validate AI-generated link suggestions using domain knowledge.

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
            logger.section("LINK VALIDATION WITH VISUAL CONTEXT")
            logger.info("Validating AI-generated links with domain knowledge...")

        if not vision_analysis:
            if logger:
                logger.error("Vision analysis is required for validation")
            return False, "Vision analysis is required for validation", ai_result

        validation_issues = []
        warnings = []

        links = ai_result.get("links", [])
        all_objects = {obj["name"] for obj in scene_data.get("objects", [])}

        # Check 1: Minimum number of links
        if len(links) < 1:
            validation_issues.append("ERROR: No links were generated")
        elif len(links) == 1:
            warnings.append("WARNING: Only 1 link generated - most mechanisms need multiple links")

        # Check 2: All objects assigned
        assigned_objects = set()
        for link in links:
            for obj_name in link.get("objects", []):
                assigned_objects.add(obj_name)

        unassigned = all_objects - assigned_objects
        if unassigned:
            warnings.append(f"WARNING: {len(unassigned)} objects not assigned to any link: {', '.join(list(unassigned)[:5])}")

        # Check 3: No duplicate assignments
        object_count = {}
        for link in links:
            for obj_name in link.get("objects", []):
                object_count[obj_name] = object_count.get(obj_name, 0) + 1

        duplicates = {obj: count for obj, count in object_count.items() if count > 1}
        if duplicates:
            validation_issues.append(f"ERROR: Objects assigned to multiple links: {duplicates}")

        # Check 4: Empty links
        empty_links = [link.get("name", "unnamed") for link in links if not link.get("objects", [])]
        if empty_links:
            validation_issues.append(f"ERROR: Links with no objects: {', '.join(empty_links)}")

        # Check 5: Parent-child separation check
        hierarchy = scene_data.get("hierarchy", [])
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

            # If both in same link, it might be intentional (rigid connection)
            # but worth flagging for review
            if parent_link and child_link and parent_link == child_link:
                warnings.append(f"INFO: Parent '{parent}' and child '{child}' are in same link '{parent_link}' - verify this is a rigid connection")

        # Check 6: Link naming conventions
        for link in links:
            link_name = link.get("name", "")
            if not link_name:
                validation_issues.append("ERROR: Link with no name found")
            elif not link_name.endswith("_link") and not link_name.endswith("Link"):
                warnings.append(f"INFO: Link '{link_name}' doesn't follow naming convention (should end with '_link')")

        # Check 7: Use AI to validate based on domain knowledge (ALWAYS runs with vision analysis)
        if logger:
            logger.info("Requesting AI domain validation...")

        client = get_azure_client()
        deployment = get_deployment_name()

        if client and deployment:
            validation_prompt = f"""You are an expert in robotic kinematics. Review these generated links and validate them.

VISUAL ANALYSIS:
{vision_analysis}

GENERATED LINKS:
{json.dumps(ai_result, indent=2)}

VALIDATION TASK:
1. Do these links make sense given the visual analysis?
2. Are there any obvious errors in link grouping?
3. Are joints properly separated (different links connected at joints)?
4. Does the link hierarchy follow robotic conventions?

Respond with JSON:
{{
  "is_valid": true/false,
  "confidence": 0-100,
  "issues": ["list of any issues found"],
  "suggestions": ["list of improvements"]
}}"""

            try:
                response = client.chat.completions.create(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": "You are an expert in robotics validation."},
                        {"role": "user", "content": validation_prompt}
                    ]
                )

                validation_response = response.choices[0].message.content

                # Try to parse JSON
                if "```json" in validation_response:
                    validation_response = validation_response.split("```json")[1].split("```")[0].strip()
                elif "```" in validation_response:
                    validation_response = validation_response.split("```")[1].split("```")[0].strip()

                ai_validation = json.loads(validation_response)

                if logger:
                    logger.info("AI Validation Result:")
                    logger.info(f"  Valid: {ai_validation.get('is_valid', 'unknown')}")
                    logger.info(f"  Confidence: {ai_validation.get('confidence', 'unknown')}%")

                if not ai_validation.get("is_valid", True):
                    for issue in ai_validation.get("issues", []):
                        validation_issues.append(f"AI VALIDATION: {issue}")

                for suggestion in ai_validation.get("suggestions", []):
                    warnings.append(f"AI SUGGESTION: {suggestion}")

            except Exception as e:
                if logger:
                    logger.warning(f"AI validation failed: {str(e)}")
                warnings.append(f"AI validation could not be performed: {str(e)}")

        # Generate validation report
        report = "=" * 60 + "\n"
        report += "LINK VALIDATION REPORT\n"
        report += "=" * 60 + "\n\n"
        report += f"Total Links Generated: {len(links)}\n"
        report += f"Total Objects in Scene: {len(all_objects)}\n"
        report += f"Objects Assigned: {len(assigned_objects)}\n"
        report += f"Objects Unassigned: {len(unassigned)}\n\n"

        if validation_issues:
            report += "CRITICAL ISSUES:\n"
            for issue in validation_issues:
                report += f"  ❌ {issue}\n"
            report += "\n"

        if warnings:
            report += "WARNINGS & INFO:\n"
            for warning in warnings:
                report += f"  ⚠️  {warning}\n"
            report += "\n"

        if not validation_issues and not warnings:
            report += "✅ All validation checks passed!\n\n"

        report += "=" * 60 + "\n"

        if logger:
            logger.info("")
            for line in report.split('\n'):
                logger.text_block.write(line + "\n")

        is_valid = len(validation_issues) == 0

        return is_valid, report, ai_result

    except Exception as e:
        if logger:
            logger.error(f"Validation error: {str(e)}")
        return False, f"Validation failed: {str(e)}", ai_result


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

        # Step 1: Capture viewport images (REQUIRED)
        logger.section("STEP 1: VISUAL CAPTURE")
        self.report({'INFO'}, "Capturing viewport images...")

        image_paths = capture_viewport_images(num_angles=3)

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

        vision_success, vision_result = analyze_images_with_ai(image_paths)

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

        logger.info(f"AI generated {len(result.get('links', []))} link suggestions")

        # Step 5: Validate link suggestions
        logger.info("")
        logger.section("STEP 5: VALIDATION")
        self.report({'INFO'}, "Validating generated links...")
        is_valid, validation_report, validated_result = validate_link_suggestions(
            result, scene_data, vision_analysis
        )

        if not is_valid:
            logger.warning("Validation found issues with generated links")
            logger.warning("Proceeding with caution - review the validation report")
        else:
            logger.info("Validation passed - links look good!")

        # Step 6: Create links
        logger.info("")
        logger.section("STEP 6: LINK CREATION")
        self.report({'INFO'}, "Creating link collections...")
        success, message = create_links_from_ai_suggestion(validated_result)

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
            final_message += f"\n\nAI Suggestions:\n{result.get('suggestions', 'None')}"
            final_message += "\n\n📄 Full log with validation details available in 'Auto-Link Log' text"

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

        # Refresh UI
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

        # Capture and analyze images (REQUIRED)
        logger.section("VISUAL CAPTURE & ANALYSIS")
        self.report({'INFO'}, "Capturing viewport images...")

        image_paths = capture_viewport_images(num_angles=3)

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
        vision_success, vision_result = analyze_images_with_ai(image_paths)

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
