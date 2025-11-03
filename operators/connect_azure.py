"""
Azure OpenAI Connection Module

This module handles connection to Azure OpenAI services.
It loads API credentials from .env file and provides functions
for other modules to interact with Azure OpenAI.
"""

import bpy
import os
import sys
from pathlib import Path

# Add user site-packages to Python path for Blender
import site
user_site_packages = site.getusersitepackages()
if user_site_packages not in sys.path:
    sys.path.append(user_site_packages)


def load_env_file():
    """
    Load environment variables from .env file.

    Returns:
        bool: True if .env file was loaded successfully, False otherwise
    """
    try:
        # Get the project root directory (parent of operators folder)
        current_dir = Path(__file__).parent
        project_root = current_dir.parent
        env_path = project_root / '.env'

        if not env_path.exists():
            print(f"Warning: .env file not found at {env_path}")
            return False

        # Manual .env parsing (avoiding external dependencies)
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        os.environ[key] = value

        return True
    except Exception as e:
        print(f"Error loading .env file: {e}")
        return False


def get_azure_config():
    """
    Get Azure OpenAI configuration from environment variables.

    Returns:
        dict: Configuration dictionary with API key, endpoint, version, and deployment name
        None: If configuration is incomplete
    """
    # Load environment variables
    load_env_file()

    api_key = os.getenv('AZURE_OPENAI_API_KEY')
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview')
    deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')

    # Check if required fields are present and not placeholder values
    if not api_key or api_key == 'your_api_key_here':
        return None
    if not endpoint or endpoint == 'https://your-resource-name.openai.azure.com/':
        return None
    if not deployment_name or deployment_name == 'your_deployment_name_here':
        return None

    return {
        'api_key': api_key,
        'endpoint': endpoint,
        'api_version': api_version,
        'deployment_name': deployment_name
    }


def test_azure_connection():
    """
    Test the connection to Azure OpenAI.

    Returns:
        tuple: (bool, str) - (Success status, Message)
    """
    try:
        config = get_azure_config()

        if config is None:
            return False, "Azure OpenAI configuration is incomplete. Please check your .env file."

        # Try to import openai package
        try:
            from openai import AzureOpenAI
        except ImportError:
            return False, "OpenAI package not installed. Install with: pip install openai"

        # Create client
        client = AzureOpenAI(
            api_key=config['api_key'],
            api_version=config['api_version'],
            azure_endpoint=config['endpoint']
        )

        # Test with a minimal completion request (without max_tokens for compatibility)
        response = client.chat.completions.create(
            model=config['deployment_name'],
            messages=[
                {"role": "user", "content": "Hi"}
            ]
        )

        if response and response.choices:
            return True, "Connected to Azure OpenAI"
        else:
            return False, "Invalid response from Azure OpenAI"

    except Exception as e:
        error_message = str(e)
        if "401" in error_message or "Unauthorized" in error_message:
            return False, "Authentication failed. Check your API key."
        elif "404" in error_message or "Not Found" in error_message:
            return False, "Endpoint or deployment not found. Check your configuration."
        elif "timeout" in error_message.lower():
            return False, "Connection timeout. Check your network connection."
        else:
            return False, f"Connection error: {error_message}"


def get_azure_client():
    """
    Get an initialized Azure OpenAI client.

    Returns:
        AzureOpenAI: Initialized client instance
        None: If configuration is incomplete or openai package is not installed
    """
    try:
        config = get_azure_config()

        if config is None:
            print("Azure OpenAI configuration is incomplete")
            return None

        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=config['api_key'],
            api_version=config['api_version'],
            azure_endpoint=config['endpoint']
        )

        return client

    except ImportError:
        print("OpenAI package not installed. Install with: pip install openai")
        return None
    except Exception as e:
        print(f"Error creating Azure OpenAI client: {e}")
        return None


def get_deployment_name():
    """
    Get the Azure OpenAI deployment name from configuration.

    Returns:
        str: Deployment name
        None: If configuration is incomplete
    """
    config = get_azure_config()
    if config:
        return config['deployment_name']
    return None


class SDFG_OT_TestAzureConnection(bpy.types.Operator):
    """Test connection to Azure OpenAI"""

    bl_idname = "scene.test_azure_connection"
    bl_label = "Test Azure Connection"
    bl_options = {"REGISTER"}

    def execute(self, context):
        success, message = test_azure_connection()

        # Store the result in the scene for display
        context.scene.azure_connection_status = message
        context.scene.azure_connection_success = success

        if success:
            self.report({'INFO'}, message)
        else:
            self.report({'ERROR'}, message)

        return {'FINISHED'}
