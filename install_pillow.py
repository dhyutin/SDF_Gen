"""
Install Pillow for Blender's Python

Run this script from within Blender:
1. Open Blender
2. Go to Scripting workspace
3. Open this file or paste the code
4. Click "Run Script" or press Alt+P
"""

import subprocess
import sys

def install_pillow():
    """Install Pillow using Blender's Python"""

    print("=" * 60)
    print("Installing Pillow for Blender...")
    print("=" * 60)
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print()

    try:
        # First, ensure pip is available
        print("Step 1: Ensuring pip is installed...")
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--default-pip"])
        print("✓ pip is ready")
        print()

    except subprocess.CalledProcessError:
        print("ℹ️  pip already installed")
        print()

    try:
        # Install Pillow
        print("Step 2: Installing Pillow...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
        print()
        print("=" * 60)
        print("✅ Pillow installed successfully!")
        print("=" * 60)
        print()

        # Verify installation
        print("Step 3: Verifying installation...")
        from PIL import Image
        print(f"✓ Pillow version {Image.__version__} is now available")
        print()
        print("You can now use Auto-Link with optimized image resizing!")
        print("Images will be resized to 384x384 to reduce token usage.")

    except subprocess.CalledProcessError as e:
        print()
        print("=" * 60)
        print("❌ Installation failed!")
        print("=" * 60)
        print(f"Error: {e}")
        print()
        print("Try running Blender with administrator privileges.")

    except ImportError as e:
        print()
        print("=" * 60)
        print("⚠️  Installation completed but import failed")
        print("=" * 60)
        print(f"Error: {e}")
        print()
        print("Try restarting Blender and running Auto-Link again.")

# Run the installation
if __name__ == "__main__":
    install_pillow()
