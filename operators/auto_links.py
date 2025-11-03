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


def create_ai_prompt(formatted_data):
    """
    Create a detailed prompt for Azure OpenAI to analyze the scene and suggest links.

    Args:
        formatted_data (str): Formatted scene data

    Returns:
        str: Complete prompt for AI
    """
    prompt = f"""You are an expert in robotic kinematics and SDF (Simulation Description Format) file generation.
Your task is to analyze a Blender scene and group objects into "links" for a robot/mechanism model.

CONTEXT:
- A "link" is a rigid body part of a mechanism (like an arm segment, wheel, chassis, etc.)
- Objects that move together as one rigid unit should be in the same link
- Links are connected by joints (revolute, prismatic, fixed, etc.)
- Each link should have a descriptive name based on its function or position

IMPORTANT RULES:
1. **DO NOT put all objects into a single link** - analyze the structure carefully
2. **Separate moving parts** - Different moving parts should be different links
3. **Look for joints** - Objects separated by joints should be in different links
4. **Parent-child relationships** often indicate separate links connected by joints
5. **Create multiple links** - Most mechanisms have 3+ separate links minimum

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


def analyze_scene_with_ai(scene_data):
    """
    Send scene data to Azure OpenAI for analysis and link suggestions.

    Args:
        scene_data (dict): Extracted scene data

    Returns:
        tuple: (success: bool, result: dict or error message: str)
    """
    global logger
    try:
        if logger:
            logger.info("Starting AI analysis...")

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
        prompt = create_ai_prompt(formatted_data)

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
            logger.info("Starting link creation from AI suggestions...")

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

        # Check Azure OpenAI connection
        client = get_azure_client()
        if not client:
            logger.error("Azure OpenAI not connected")
            logger.show_in_editor()
            self.report({'ERROR'}, "Azure OpenAI not connected. Check UTILITIES tab.")
            return {'CANCELLED'}

        logger.info("Azure OpenAI connection verified")
        self.report({'INFO'}, "Extracting model data...")

        # Extract scene data
        scene_data = extract_model_data()

        if not scene_data["objects"]:
            self.report({'ERROR'}, "No objects found in scene to analyze")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Analyzing {len(scene_data['objects'])} objects with AI...")

        # Analyze with AI
        success, result = analyze_scene_with_ai(scene_data)

        if not success:
            self.report({'ERROR'}, f"AI analysis failed: {result}")
            show_message_box(
                message=f"AI Analysis Failed:\n\n{result}",
                title="Auto-Link Generation Error",
                icon="ERROR"
            )
            return {'CANCELLED'}

        self.report({'INFO'}, "Creating link collections...")

        # Create links based on AI suggestions
        success, message = create_links_from_ai_suggestion(result)

        if success:
            logger.info("")
            logger.info("=" * 80)
            logger.info("Auto-link generation COMPLETED SUCCESSFULLY")
            logger.info("=" * 80)

            # Show log in text editor
            logger.show_in_editor()

            self.report({'INFO'}, "Links created successfully")
            show_message_box(
                message=message + f"\n\nAI Suggestions:\n{result.get('suggestions', 'None')}\n\n📄 Full log available in 'Auto-Link Log' text",
                title="Auto-Link Generation Complete",
                icon="INFO"
            )
        else:
            logger.error("")
            logger.error("=" * 80)
            logger.error("Auto-link generation FAILED")
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
        # Check Azure OpenAI connection
        client = get_azure_client()
        if not client:
            self.report({'ERROR'}, "Azure OpenAI not connected. Check UTILITIES tab.")
            return {'CANCELLED'}

        # Extract scene data
        scene_data = extract_model_data()

        if not scene_data["objects"]:
            self.report({'ERROR'}, "No objects found in scene to analyze")
            return {'CANCELLED'}

        self.report({'INFO'}, "Analyzing scene with AI...")

        # Analyze with AI
        success, result = analyze_scene_with_ai(scene_data)

        if not success:
            self.report({'ERROR'}, f"AI analysis failed: {result}")
            show_message_box(
                message=f"AI Analysis Failed:\n\n{result}",
                title="Scene Analysis Error",
                icon="ERROR"
            )
            return {'CANCELLED'}

        # Format results for display
        links_summary = []
        for link in result.get("links", []):
            links_summary.append(f"• {link['name']}: {len(link['objects'])} objects")

        message = "AI Analysis Results:\n\n"
        message += "Suggested Links:\n" + "\n".join(links_summary)
        message += f"\n\nSuggestions:\n{result.get('suggestions', 'None')}"
        message += "\n\nUse 'Auto-Generate Links' to create these links."

        self.report({'INFO'}, f"Analysis complete: {len(result.get('links', []))} links suggested")
        show_message_box(
            message=message,
            title="Scene Analysis Preview",
            icon="INFO"
        )

        return {'FINISHED'}
