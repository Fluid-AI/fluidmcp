"""
NPM utility functions for fixing permissions and environment setup
"""
import subprocess
import shutil
from pathlib import Path
from typing import Dict

def fix_npm_permissions() -> bool:
    """Fix npm permissions automatically without requiring sudo"""
    try:
        npm_cache_dir = Path.home() / ".npm"
        npm_global_dir = Path.home() / ".npm-global"
        
        # Check if we have permission issues
        if npm_cache_dir.exists():
            try:
                # Try to create a test file in npm cache
                test_file = npm_cache_dir / "test_permissions"
                test_file.touch()
                test_file.unlink()
            except PermissionError:
                print("🔧 Fixing npm cache permissions...")
                # Clear the problematic cache instead of using sudo
                if npm_cache_dir.exists():
                    try:
                        shutil.rmtree(npm_cache_dir)
                        npm_cache_dir.mkdir(exist_ok=True)
                        print("✅ Cleared npm cache")
                    except Exception as e:
                        print(f"⚠️  Could not clear npm cache: {e}")
        
        # Set up npm global directory
        if not npm_global_dir.exists():
            npm_global_dir.mkdir(exist_ok=True)
            
        # Configure npm to use the new directory
        try:
            subprocess.run(
                ["npm", "config", "set", "prefix", str(npm_global_dir)], 
                check=False, 
                capture_output=True
            )
            subprocess.run(
                ["npm", "config", "set", "cache", str(npm_cache_dir)], 
                check=False, 
                capture_output=True
            )
            print("✅ Configured npm global directory")
        except Exception as e:
            print(f"⚠️  Could not configure npm: {e}")
            
        return True
    except Exception as e:
        print(f"⚠️  Error fixing npm permissions: {e}")
        return False

def create_clean_npm_environment() -> Dict[str, str]:
    """Create a clean npm environment for the current session"""
    try:
        # Create temporary directories
        temp_cache = Path.cwd() / ".temp_npm_cache"
        temp_global = Path.cwd() / ".temp_npm_global"
        
        temp_cache.mkdir(exist_ok=True)
        temp_global.mkdir(exist_ok=True)
        
        # Return environment variables for clean npm
        return {
            "NPM_CONFIG_CACHE": str(temp_cache),
            "NPM_CONFIG_PREFIX": str(temp_global),
            "NPM_CONFIG_USER_CONFIG": "/dev/null",  # Ignore user config
            "NPM_CONFIG_GLOBAL_CONFIG": "/dev/null"  # Ignore global config
        }
    except Exception:
        return {}