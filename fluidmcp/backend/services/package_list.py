from pathlib import Path

def get_latest_version_dir(package_dir: Path) -> Path:
    '''
    Get the latest version directory of a package.
    args:
        package_dir (Path): The path to the package directory.
    returns:
        version_dir (Path): The path to the latest version directory.'''
    
    # Check if the package directory exists
    if not package_dir.exists():
        raise FileNotFoundError(f"No installation found for package: {package_dir.name}")
    # Check if version directories exist
    versions = [v for v in package_dir.iterdir() if v.is_dir()]
    # if no version directories exist, raise an error
    if not versions:
        raise FileNotFoundError(f"No version folders found in {package_dir}")
    # return the latest version directory collected and sorted
    return sorted(versions, reverse=True)[0]
