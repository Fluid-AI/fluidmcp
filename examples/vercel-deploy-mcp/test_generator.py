#!/usr/bin/env python3
"""
Test script for the Netlify Deploy MCP Server
Tests file generation without deployment
"""

import asyncio
import sys
from pathlib import Path

# Add the server to the path
sys.path.insert(0, str(Path(__file__).parent))

from server import generate_website, SITES_DIR


async def test_generate_todo():
    """Test todo app generation"""
    print("Testing Todo App generation...")
    try:
        project_path = await generate_website(
            site_type="todo",
            site_name="test-todo",
            custom_content={"title": "Test Todo App"}
        )
        print(f"✓ Todo app generated at: {project_path}")

        # Check if files exist
        assert (project_path / "index.html").exists(), "index.html not found"
        assert (project_path / "style.css").exists(), "style.css not found"
        assert (project_path / "script.js").exists(), "script.js not found"
        assert (project_path / "netlify.toml").exists(), "netlify.toml not found"
        print("✓ All required files exist")

        # Check file sizes
        html_size = (project_path / "index.html").stat().st_size
        css_size = (project_path / "style.css").stat().st_size
        js_size = (project_path / "script.js").stat().st_size
        print(f"  - index.html: {html_size} bytes")
        print(f"  - style.css: {css_size} bytes")
        print(f"  - script.js: {js_size} bytes")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def test_generate_portfolio():
    """Test portfolio generation"""
    print("\nTesting Portfolio generation...")
    try:
        project_path = await generate_website(
            site_type="portfolio",
            site_name="test-portfolio",
            custom_content={
                "title": "Jane Doe",
                "description": "Software Engineer"
            }
        )
        print(f"✓ Portfolio generated at: {project_path}")

        # Check if files exist
        assert (project_path / "index.html").exists(), "index.html not found"
        assert (project_path / "style.css").exists(), "style.css not found"
        assert (project_path / "script.js").exists(), "script.js not found"
        assert (project_path / "netlify.toml").exists(), "netlify.toml not found"
        print("✓ All required files exist")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def test_generate_landing():
    """Test landing page generation"""
    print("\nTesting Landing Page generation...")
    try:
        project_path = await generate_website(
            site_type="landing",
            site_name="test-landing",
            custom_content={
                "title": "Amazing Product",
                "description": "The best solution ever"
            }
        )
        print(f"✓ Landing page generated at: {project_path}")

        # Check if files exist
        assert (project_path / "index.html").exists(), "index.html not found"
        assert (project_path / "style.css").exists(), "style.css not found"
        assert (project_path / "script.js").exists(), "script.js not found"
        assert (project_path / "netlify.toml").exists(), "netlify.toml not found"
        print("✓ All required files exist")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Netlify Deploy MCP Server - Test Suite")
    print("=" * 60)
    print(f"\nSites directory: {SITES_DIR}")

    # Run tests
    results = []
    results.append(await test_generate_todo())
    results.append(await test_generate_portfolio())
    results.append(await test_generate_landing())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
