from .package_installer import install_package
from .package_installer import parse_package_string
from .env_manager import edit_env_variables
from .alias_support import process_alias

__all__ = ["install_package","edit_env_variables", "parse_package_string", "process_alias"]