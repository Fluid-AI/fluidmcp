from pathlib import Path
from loguru import logger


def get_latest_version_dir(package_dir: Path) -> Path:
    '''
    Get the latest version directory of a package.
    args:
        package_dir (Path): The path to the package directory.
    returns:
        version_dir (Path): The path to the latest version directory.'''

    logger.debug(f"Looking for latest version in: {package_dir}")

    # Check if the package directory exists
    if not package_dir.exists():
        logger.debug(f"Package directory does not exist: {package_dir}")
        raise FileNotFoundError(f"No installation found for package: {package_dir.name}")

    # Check if version directories exist
    versions = [v for v in package_dir.iterdir() if v.is_dir()]
    logger.debug(f"Found {len(versions)} version(s): {[v.name for v in versions]}")

    # if no version directories exist, raise an error
    if not versions:
        logger.debug(f"No version directories found in {package_dir}")
        raise FileNotFoundError(f"No version folders found in {package_dir}")

    # return the latest version directory collected and sorted
    latest_version = sorted(versions, reverse=True)[0]
    logger.debug(f"Selected latest version: {latest_version.name}")
    return latest_version
