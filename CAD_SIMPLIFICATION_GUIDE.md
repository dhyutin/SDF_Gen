# CAD Model Auto-Simplification Guide

## Overview

This guide explains the new **CAD Auto-Simplification** feature added to the Capstone Blender plugin. This automation eliminates the need to manually perform repetitive cleanup steps when importing CAD models into Blender.

### What Does It Do?

The CAD Auto-Simplification feature automates all the manual steps that are typically required **before** material assignment (Step 1 in the original manual process). This includes:

1. ✅ Deleting unnecessary objects (cameras, lights, empties)
2. ✅ Joining all mesh objects into a single mesh
3. ✅ Applying all transforms (location, rotation, scale)
4. ✅ Removing duplicate vertices (merge by distance)
5. ✅ Recalculating normals to face outward
6. ✅ Deleting loose geometry (unconnected vertices/edges)
7. ✅ Filling holes in the mesh
8. ✅ Cleaning up the final mesh

After running this automation, your CAD model will be ready for **Step 1: Assign and Consolidate Materials**.

---

## Location in Blender

The CAD Simplification tools are located in the **Capstone** panel in the 3D Viewport sidebar.

### How to Access:

1. Open Blender
2. In the 3D Viewport, press `N` to open the sidebar (if not already visible)
3. Click on the **"Capstone"** tab
4. Navigate to the **"Utilities"** section (click the wrench icon at the top)
5. Scroll down to find the **"CAD Simplification"** section

---

## How to Use

### Method 1: One-Click Auto-Simplification (Recommended)

This is the **easiest and fastest** method. It runs all simplification steps automatically in one click.

#### Step-by-Step Instructions:

1. **Import your CAD model** into Blender:
   - Go to the **Utilities** tab in the Capstone panel
   - Under "Import", click **"Import STEP"** (requires STEPper addon)
   - OR use Blender's standard import: `File > Import > STL/OBJ/FBX` etc.

2. **After import**, you should see your CAD model in the viewport along with any cameras, lights, or empty objects that came with the import

3. **Click the "Auto-Simplify CAD Model" button**:
   - Located in the **CAD Simplification** section of the Utilities tab
   - This button has a "MOD_BUILD" icon next to it

4. **Wait for the process to complete**:
   - Blender will process your model (this may take a few seconds to minutes depending on model complexity)
   - You'll see status messages in the Info editor at the bottom of Blender
   - Messages will show progress like:
     - "Step 1/8: Deleting unnecessary objects..."
     - "Step 2/8: Selecting all mesh objects..."
     - etc.

5. **Done!** Your model is now simplified and ready for material assignment:
   - All meshes are joined into one object
   - Transforms are applied
   - Duplicate vertices removed
   - Normals recalculated
   - Holes filled
   - Ready for the next step in your workflow

#### Expected Result:
- You should now have a **single mesh object** in your scene
- All cameras, lights, and empty objects have been removed
- The mesh is clean and optimized
- You can proceed to **Step 1: Assign and Consolidate Materials** from the original manual workflow

---

### Method 2: Advanced Step-by-Step Control

If you want more control over the simplification process or need to run only specific steps, use the **Advanced Step-by-Step** mode.

#### Step-by-Step Instructions:

1. **Import your CAD model** (same as Method 1)

2. **Expand the Advanced options**:
   - In the **CAD Simplification** section, you'll see a collapsed section labeled **"Advanced Step-by-Step"**
   - Click the **triangle icon** (▶) next to it to expand

3. **Run individual steps** in order:
   - You'll see 7 numbered buttons, one for each simplification step
   - Click each button **in order** to perform that specific step:

#### Individual Steps Explained:

**Step 1: Delete Unnecessary Objects**
- Removes all cameras, lights, and empty objects from the scene
- Useful for cleaning up after CAD import
- *When to use*: If your import brought in unwanted objects

**Step 2: Join All Meshes**
- Combines all separate mesh objects into one single mesh
- Makes editing and processing much easier
- *When to use*: After you've verified all meshes are correct and want to merge them

**Step 3: Apply Transforms**
- Applies location, rotation, and scale to the mesh data
- Resets the object's transform to zero
- *When to use*: Before any further mesh editing to ensure correct dimensions

**Step 4: Remove Doubles**
- Merges vertices that are very close together (within 0.01mm)
- Reduces vertex count and fixes overlapping geometry
- *When to use*: To clean up duplicate vertices from CAD export

**Step 5: Recalculate Normals**
- Fixes the direction of face normals to point outward
- Ensures proper rendering and shading
- *When to use*: If your model has inverted or inconsistent normals

**Step 6: Delete Loose Geometry**
- Removes vertices and edges that aren't connected to any faces
- Cleans up leftover geometry
- *When to use*: To remove stray vertices from the import

**Step 7: Fill Holes**
- Automatically detects and fills holes in the mesh
- Creates faces to close open boundaries
- *When to use*: If your mesh has holes that need to be closed

#### Tips for Step-by-Step Mode:
- **Run steps in order** (1 through 7) for best results
- You can **skip steps** if they're not needed for your specific model
- After running Step 2 (Join All Meshes), make sure the **mesh is selected** before running subsequent steps
- Use the **Info editor** (bottom of Blender) to see feedback about what each step did

---

## Configuration Options

### Auto-Simplification Settings

When you run the **Auto-Simplify CAD Model** button, it uses the following default settings:

| Setting | Default Value | Description |
|---------|---------------|-------------|
| **Merge Distance** | 0.01 mm | Distance threshold for merging duplicate vertices |
| **Delete Cameras** | ✅ Enabled | Automatically delete camera objects |
| **Delete Lights** | ✅ Enabled | Automatically delete light objects |
| **Delete Empties** | ✅ Enabled | Automatically delete empty objects |
| **Fill Holes** | ✅ Enabled | Automatically fill holes in the mesh |
| **Recalculate Normals** | ✅ Enabled | Fix normal directions to face outward |

*Note: These settings are currently hardcoded. If you need to customize them, use the step-by-step method and skip unwanted steps.*

---

## Troubleshooting

### Common Issues and Solutions

#### Issue: "No mesh objects found in the scene!"
**Solution**: Make sure you've imported a CAD model with mesh objects before running the automation. Check that your import was successful and you can see geometry in the viewport.

#### Issue: "No mesh object selected!" (when using step-by-step mode)
**Solution**: After running "Join All Meshes" or between steps, make sure the mesh object is **selected** (highlighted in orange) in the viewport. Click on it to select it, then run the next step.

#### Issue: The automation seems to freeze or take a long time
**Solution**: This is normal for very complex models with millions of vertices. The process can take several minutes. Check the Info editor (bottom of Blender) for progress updates. Do not interrupt the process.

#### Issue: Some holes weren't filled properly
**Solution**: The automatic hole-filling works for simple holes. For complex holes, you may need to:
1. Switch to Edit Mode (`Tab` key)
2. Select the boundary edges manually
3. Use `F` (Fill) or `Alt+F` (Grid Fill) to fill manually

#### Issue: The model looks wrong after simplification
**Solution**:
1. Press `Ctrl+Z` to undo the simplification
2. Try running the step-by-step method to see which step causes the issue
3. Check if your original import was correct
4. Make sure you're using the correct import format for your CAD file

#### Issue: I accidentally deleted objects I needed
**Solution**:
1. Press `Ctrl+Z` to undo
2. Before running the automation, move any objects you want to keep to a different collection
3. Or use the step-by-step method and skip "Step 1: Delete Unnecessary Objects"

---

## Integration with Original Workflow

The CAD Auto-Simplification feature replaces all the manual steps that came **before** "Step 1: Assign and Consolidate Materials" in the original manual workflow.

### Original Manual Workflow:
1. ~~Import CAD model~~
2. ~~Delete cameras, lights, empties~~
3. ~~Join all meshes~~
4. ~~Apply transforms~~
5. ~~Remove doubles~~
6. ~~Recalculate normals~~
7. ~~Delete loose geometry~~
8. ~~Fill holes~~
9. ~~Clean mesh~~
10. **Step 1: Assign and Consolidate Materials** ← Start here after auto-simplification
11. Step 2: Create colliders
12. Step 3: Set up hierarchy
13. etc.

### New Automated Workflow:
1. **Import CAD model** (using Import STEP or File > Import)
2. **Click "Auto-Simplify CAD Model"** (takes 1 click, ~30 seconds to 5 minutes)
3. **Proceed to Step 1: Assign and Consolidate Materials** (continue with original workflow)

**Time Saved**: Approximately 10-30 minutes per model, depending on complexity!

---

## Technical Details

### What Gets Modified?

The automation modifies the following aspects of your Blender scene:

- **Objects**: Deletes cameras, lights, and empties; joins meshes into one
- **Mesh Data**: Merges duplicate vertices, recalculates normals, fills holes, removes loose geometry
- **Transforms**: Applies location, rotation, and scale to mesh data
- **Materials**: NOT modified (materials are preserved during joining)
- **Collections**: NOT modified (preserved)
- **Scene Settings**: NOT modified

### Performance Considerations

The automation performance depends on:

- **Vertex Count**: More vertices = longer processing time
- **Mesh Complexity**: Complex topology takes longer to process
- **Number of Objects**: More objects to join = slightly longer
- **Hole Count**: More holes to fill = longer processing time

**Typical Processing Times**:
- Simple model (< 10K vertices): 5-15 seconds
- Medium model (10K-100K vertices): 15-60 seconds
- Complex model (100K-1M vertices): 1-5 minutes
- Very complex model (> 1M vertices): 5-15 minutes

### Merge Distance Explained

The **merge distance** (0.01mm default) determines how close two vertices need to be to be considered "duplicates" and merged together.

- **0.01mm** (default): Very precise, good for most CAD models
- **Smaller values** (0.001mm): More precise, keeps more vertices
- **Larger values** (0.1mm): Less precise, may merge vertices that should stay separate

The default of 0.01mm is chosen to match typical CAD export precision and avoid unwanted merging.

---

## Code Location and Files

For developers or advanced users who want to modify the automation:

### New Files Created:
1. **`operators/cad_simplification.py`**
   - Contains `SDFG_OT_SimplifyCAD` operator (main auto-simplification)
   - Contains `SDFG_OT_SimplifyCAD_Advanced` operator (step-by-step mode)
   - Fully commented with explanations of each function

### Modified Files:
1. **`ui/create_panel.py`**
   - Added CAD Simplification section to Utilities tab (lines 244-267)
   - Added UI buttons for both auto and step-by-step modes

2. **`operators/properties.py`**
   - Added `cad_simplify_advanced` BoolProperty for UI state (lines 154-159)

### How It Works (Auto-Load System):
The new operators are automatically registered by Blender's auto-load system:
- `auto_load.py` scans all modules in the `operators/` directory
- Finds all classes that inherit from `bpy.types.Operator`
- Automatically registers them when the addon loads
- No manual registration required!

---

## Examples and Use Cases

### Use Case 1: Simple CAD Import
**Scenario**: You imported a simple mechanical part from STEP format

**Steps**:
1. Import STEP file using "Import STEP" button
2. Click "Auto-Simplify CAD Model"
3. Wait 10-20 seconds
4. Proceed to assign materials

**Expected Result**: Clean, single-mesh model ready for materials

---

### Use Case 2: Complex Assembly
**Scenario**: You imported a complex assembly with 50+ parts

**Steps**:
1. Import your assembly (STEP, OBJ, or FBX)
2. Verify all parts are visible and correct
3. Click "Auto-Simplify CAD Model"
4. Wait 2-5 minutes (complexity dependent)
5. Check the result - should be one merged mesh
6. Proceed to material assignment

**Expected Result**: All parts joined into one optimized mesh

---

### Use Case 3: Selective Simplification
**Scenario**: You want to keep some objects separate and only simplify specific parts

**Steps**:
1. Import your model
2. **Before simplification**: Move objects you want to keep to a different collection or scene
3. Use **Advanced Step-by-Step** mode
4. Skip "Step 1: Delete Unnecessary Objects" if you want to keep cameras/lights
5. Manually select which meshes to join (join some, keep others separate)
6. Run the remaining steps on your selected mesh

**Expected Result**: Custom simplified mesh with selective preservation

---

## Best Practices

### ✅ DO:
- **Always save your Blender file before running simplification** (in case you need to undo)
- **Check your model after import** to make sure the import was successful
- **Use the Info editor** to monitor progress and see what's happening
- **Start with the one-click auto-simplification** for most models
- **Use step-by-step mode** only when you need specific control

### ❌ DON'T:
- **Don't interrupt the process** while it's running (wait for completion)
- **Don't run simplification twice** on the same model (unnecessary)
- **Don't forget to save** before running (use Ctrl+S)
- **Don't use this on models that are already simplified** (it's designed for fresh CAD imports)

---

## Frequently Asked Questions (FAQ)

**Q: Can I undo the simplification if something goes wrong?**
A: Yes! Press `Ctrl+Z` to undo. All operators support Blender's undo system.

**Q: Will this work with any CAD format?**
A: Yes! As long as you can import it into Blender as mesh objects, the simplification will work. Supports STEP, STL, OBJ, FBX, and any other mesh format.

**Q: Does this delete my materials?**
A: No! Materials are preserved when meshes are joined. However, you'll typically assign new materials in "Step 1" anyway.

**Q: Can I customize the merge distance?**
A: Currently, the merge distance is hardcoded to 0.01mm. To customize, you would need to modify the `operators/cad_simplification.py` file and change the `default` value in the `merge_distance` property.

**Q: What happened to the "SDF Gen" tab?**
A: The plugin has been renamed to "Capstone". All functionality remains the same - just look for the "Capstone" tab instead of "SDF Gen" in the 3D Viewport sidebar.

**Q: Why does my model still have some loose vertices after simplification?**
A: The "Delete Loose Geometry" step removes most loose vertices, but some may remain if they're connected to edges (even if not to faces). You can manually clean these in Edit Mode.

**Q: Can I run this on multiple models at once?**
A: Not directly. The automation works on all mesh objects in the current scene. If you have multiple models in separate scenes, you'll need to run it once per scene.

**Q: What's the difference between "Auto-Simplify" and "Clean Mesh"?**
A: "Clean Mesh" (in Mesh Tools) is a simpler operation that just cleans up imported mesh data and applies basic transforms. "Auto-Simplify CAD Model" is a complete workflow that includes joining meshes, filling holes, removing duplicates, and much more.

---

## Support and Feedback

If you encounter issues or have suggestions for improving the CAD Auto-Simplification feature:

1. **Check the Troubleshooting section** above
2. **Review the Blender console** for error messages (`Window > Toggle System Console` on Windows)
3. **Report issues** to the plugin maintainers with:
   - Description of the issue
   - Steps to reproduce
   - Model complexity (vertex count)
   - Blender version
   - Any error messages from the console

---

## Version History

### Version 1.0 (Current)
- Initial release of CAD Auto-Simplification
- One-click auto-simplification feature
- Advanced step-by-step mode with 7 individual steps
- Automatic detection and registration
- Integrated into Utilities tab

---

## Credits

**Original Manual Workflow**: Based on "How to manually change CAT to SDF" guide
**Automation Implementation**: Capstone Plugin Development Team
**Plugin Author**: Sree-Arjun
**Testing**: Blender CAD Import Community

---

## Conclusion

The CAD Auto-Simplification feature dramatically reduces the time and effort required to prepare CAD models for use in Blender and SDF export. What used to take 10-30 minutes of repetitive manual work now takes a single click and a short wait.

**Happy modeling!** 🎉
