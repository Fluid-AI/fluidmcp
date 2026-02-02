from setuptools import setup, find_packages
import os

# Read the content of README file
readme_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "README.md")
if os.path.exists(readme_path):
    with open(readme_path, "r", encoding="utf-8") as f:
        long_description = f.read()
else:
    long_description = "FluidAI MCP Installer - A CLI tool for installing and managing Model Context Protocol servers"

setup(
    name="fluidmcp",
    version="0.1.0",
    author="Fluid AI",
    author_email="info@fluid.ai",
    description="A CLI tool for installing and managing Model Context Protocol (MCP) servers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Fluid-AI/fluidmcp",
    packages=['fluidmcp', 'fluidmcp.services', 'fluidmcp.models'],
    package_dir={'fluidmcp': 'fluidmcp/cli'},
    include_package_data=True,
    install_requires=[
        "requests",
        "loguru",
        "pathlib",
        "psutil",
        "boto3",  # Added boto3 for S3 operations
        "fastapi",
        "uvicorn",
        "httpx"  # Required for Replicate client
    ],
    entry_points={
        'console_scripts': [
            'fluidai-mcp=fluidmcp:main',
            'fluidmcp=fluidmcp:main',
            'fmcp=fluidmcp:main',
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.6",
    keywords="mcp, model context protocol, llm, ai, fluidai",
)