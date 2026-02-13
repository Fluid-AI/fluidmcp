#!/usr/bin/env python3
"""
Vercel Deploy MCP Server
Generates static websites with AI and deploys them to Vercel
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import zipfile
import requests
import fcntl
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent, Prompt, GetPromptResult, PromptMessage
import mcp.server.stdio

# Try to import Anthropic for dynamic website generation
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logging.warning("Anthropic SDK not installed.")

# Try to import Google Gemini for dynamic website generation (free alternative)
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google Genai SDK not installed. Install with: pip install google-genai")

# Try to import OpenAI for dynamic website generation (paid, high quality)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI SDK not installed. Install with: pip install openai")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vercel-deploy-mcp")

# Initialize MCP server
app = Server("vercel-deploy")

# Base directory for generated sites
SITES_DIR = Path.home() / ".vercel-mcp" / "sites"
SITES_DIR.mkdir(parents=True, exist_ok=True)

# Global deployment tracking and synchronization
_active_deployment_lock = threading.Lock()
_active_deployment = None  # Stores the current active deployment thread and site_name
_deployment_cancelled = threading.Event()  # Event to signal cancellation

# Deployment history file
DEPLOYMENT_HISTORY = SITES_DIR / "deployment_history.json"


def load_deployment_history():
    """Load deployment history from file with file locking and aggressive cache clearing"""
    if DEPLOYMENT_HISTORY.exists():
        try:
            import os
            import time

            logger.info(f"[LOAD] Starting to load deployment history at {datetime.now().isoformat()}")
            print(f"\n{'='*80}", file=sys.stderr, flush=True)
            print(f"[LOAD] Starting to load deployment history at {datetime.now().isoformat()}", file=sys.stderr, flush=True)

            # NUCLEAR cache clearing
            # 1. Sync filesystem FIRST
            try:
                os.sync()
                logger.info("[LOAD] Called os.sync()")
            except (AttributeError, OSError) as e:
                logger.info(f"[LOAD] os.sync() not available: {e}")

            # 2. Small delay to ensure writes complete
            time.sleep(0.1)
            logger.info("[LOAD] Waited 100ms for filesystem")

            # 3. Clear stat cache
            file_size = os.stat(DEPLOYMENT_HISTORY).st_size
            file_mtime = os.stat(DEPLOYMENT_HISTORY).st_mtime
            logger.info(f"[LOAD] File size: {file_size} bytes, modified: {datetime.fromtimestamp(file_mtime).isoformat()}")

            # 4. Read file TWICE to force cache invalidation
            logger.info("[LOAD] Reading file...")
            with open(DEPLOYMENT_HISTORY, 'r') as f:
                # Acquire shared lock for reading
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                except (OSError, AttributeError):
                    pass

                try:
                    data = json.load(f)
                    logger.info(f"[LOAD] Successfully loaded {len(data)} entries")

                    # Log the last 3 entries with FULL details
                    if data:
                        logger.info("[LOAD] Last 3 entries:")
                        print(f"[LOAD] Last 3 entries:", file=sys.stderr, flush=True)
                        for d in data[-3:]:
                            logger.info(f"[LOAD]   - {d.get('site_name')}: {d.get('deployment_status')} @ {d.get('deployed_at', d.get('created_at', 'no time'))[:19]}")
                            logger.info(f"[LOAD]     URL: {d.get('deploy_url', 'no url')[:100]}")
                            print(f"[LOAD]   - {d.get('site_name')}: {d.get('deployment_status')} @ {d.get('deployed_at', d.get('created_at', 'no time'))[:19]}", file=sys.stderr, flush=True)
                            print(f"[LOAD]     URL: {d.get('deploy_url', 'no url')[:100]}", file=sys.stderr, flush=True)

                    return data
                finally:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except (OSError, AttributeError):
                        pass
        except Exception as e:
            logger.error(f"[LOAD] Error loading deployment history: {e}")
            return []
    else:
        logger.warning(f"[LOAD] Deployment history file does not exist: {DEPLOYMENT_HISTORY}")
    return []


def save_deployment_history(deployments):
    """Save deployment history to file with file locking"""
    import os
    try:
        with open(DEPLOYMENT_HISTORY, 'w') as f:
            # Acquire exclusive lock for writing
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except (OSError, AttributeError):
                pass  # File locking not available on all platforms

            try:
                json.dump(deployments, f, indent=2)
                f.flush()  # Flush Python's buffer
                os.fsync(f.fileno())  # Force OS to write to disk immediately
            finally:
                # Release lock
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except (OSError, AttributeError):
                    pass
    except Exception as e:
        logger.error(f"Error saving deployment history: {e}")


def clean_display_url(url: str) -> str:
    """
    Clean Vercel URL for display by removing team name suffixes ONLY.

    This is a fallback - the real production URL should come from Vercel's API.
    This function ONLY removes the team name, it does NOT modify timestamps.

    Converts:
    https://simple-calculator-20260211074502-shivam-swamis-projects.vercel.app/
    To:
    https://simple-calculator-20260211074502.vercel.app/
    (keeping the full timestamp as-is)
    """
    if not url or not isinstance(url, str):
        return url

    import re

    # ONLY remove the "-{team-name}-projects" suffix, don't modify anything else
    # Pattern: Find timestamp digits, capture everything up to that point, then remove team name + "-projects"
    # URL format: {site-name}-{timestamp}-{team-name}-projects.vercel.app
    # Result: {site-name}-{timestamp}.vercel.app (with original timestamp unchanged)
    cleaned_url = re.sub(r'(-\d+)-[a-z0-9-]+-projects\.vercel\.app', r'\1.vercel.app', url)

    return cleaned_url


def detect_site_type_from_prompt(prompt: str) -> tuple[str, str]:
    """
    Detect site type from natural language prompt.
    Returns (site_type, auto_site_name)

    Only uses templates for very basic/generic prompts.
    Any specific description uses AI generation for customization.
    """
    prompt_lower = prompt.lower().strip()

    # Only match templates for VERY simple, generic prompts
    # If the prompt has more specific details, use AI generation instead

    # Todo app - only for basic todo prompts
    if prompt_lower in ['create a todo app', 'make a todo app', 'build a todo app',
                        'create a task manager', 'make a task manager', 'todo app',
                        'create todo', 'make todo']:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return ("todo", f"todo-{timestamp}")

    # Portfolio - only for basic portfolio prompts
    if prompt_lower in ['create a portfolio', 'make a portfolio', 'build a portfolio',
                        'create a portfolio website', 'portfolio website', 'portfolio',
                        'create resume site', 'resume website']:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return ("portfolio", f"portfolio-{timestamp}")

    # Landing page - only for very generic landing page prompts
    if prompt_lower in ['create a landing page', 'make a landing page', 'build a landing page',
                        'landing page', 'create landing', 'make landing']:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return ("landing", f"landing-{timestamp}")

    # Everything else uses AI generation (including specific prompts like "social media landing page")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Generate a meaningful site name from the prompt
    # Extract key words for the site name
    words = prompt_lower.replace('create', '').replace('make', '').replace('build', '').replace('a ', '').strip()
    words = words.replace(' ', '-')[:30]  # Limit length and replace spaces

    return ("custom", f"{words}-{timestamp}" if words else f"site-{timestamp}")


async def generate_custom_website_with_ai(prompt: str, site_name: str) -> Dict[str, str]:
    """
    Use AI API (OpenAI, Anthropic Claude, or Google Gemini) to generate a custom single-page application based on the prompt.
    Returns a dict with 'html', 'css', and 'js' keys.

    Priority:
    1. Try OpenAI GPT-4 if OPENAI_API_KEY is available (BEST QUALITY)
    2. Try Anthropic Claude if ANTHROPIC_API_KEY is available (HIGH QUALITY)
    3. Fall back to Google Gemini if GEMINI_API_KEY is available (FREE)
    """
    # Check which APIs are available
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    use_openai = OPENAI_AVAILABLE and openai_key
    use_anthropic = ANTHROPIC_AVAILABLE and anthropic_key
    use_gemini = GEMINI_AVAILABLE and gemini_key

    if not use_openai and not use_anthropic and not use_gemini:
        raise RuntimeError(
            "No AI API configured. Please set one of:\n"
            "  - OPENAI_API_KEY (ChatGPT, best quality)\n"
            "  - ANTHROPIC_API_KEY (Claude, high quality)\n"
            "  - GEMINI_API_KEY (free at https://aistudio.google.com/apikey)\n"
            "\nInstall SDKs with: pip install openai anthropic google-generativeai"
        )

    logger.info(f"Generating custom website with AI for prompt: {prompt}")

    # Try OpenAI first (if available) - BEST QUALITY
    if use_openai:
        try:
            logger.info("🚀 Using OpenAI GPT-4 API (highest quality)...")
            return await _generate_with_openai(prompt, site_name, openai_key)
        except Exception as e:
            error_msg = str(e).lower()
            # If it's a quota/billing error, try fallbacks
            if "quota" in error_msg or "billing" in error_msg or "insufficient" in error_msg:
                logger.warning(f"OpenAI API failed (quota/billing issue): {e}")
                if use_anthropic:
                    logger.info("Falling back to Anthropic Claude...")
                    return await _generate_with_anthropic(prompt, site_name, anthropic_key)
                elif use_gemini:
                    logger.info("Falling back to Google Gemini (free API)...")
                    return await _generate_with_gemini(prompt, site_name, gemini_key)
            else:
                # Other errors - re-raise
                raise

    # Try Anthropic second (if available)
    if use_anthropic:
        try:
            logger.info("Using Anthropic Claude API...")
            return await _generate_with_anthropic(prompt, site_name, anthropic_key)
        except Exception as e:
            error_msg = str(e).lower()
            # If it's a credit/billing error, try Gemini fallback
            if "credit" in error_msg or "billing" in error_msg or "quota" in error_msg:
                logger.warning(f"Anthropic API failed (likely no credits): {e}")
                if use_gemini:
                    logger.info("Falling back to Google Gemini (free API)...")
                    return await _generate_with_gemini(prompt, site_name, gemini_key)
                else:
                    raise RuntimeError(
                        f"Anthropic API failed: {e}\n"
                        "Get a FREE Gemini API key at https://aistudio.google.com/apikey\n"
                        "Install with: pip install google-generativeai"
                    )
            else:
                # Other errors, re-raise
                raise

    # Use Gemini if it's the only option available
    if use_gemini:
        logger.info("Using Google Gemini API (free)...")
        return await _generate_with_gemini(prompt, site_name, gemini_key)


async def _generate_with_anthropic(prompt: str, site_name: str, api_key: str) -> Dict[str, str]:
    """Generate website using Anthropic Claude API"""
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """You are an expert full-stack web developer who creates PRODUCTION-READY, beautiful, and highly functional single-page applications.

Your code must be:
- **Professional Grade**: Clean, well-structured, maintainable code with best practices
- **Fully Functional**: All features work perfectly with proper event handling and state management
- **Visually Stunning**: Modern design with smooth animations, beautiful gradients, professional color schemes
- **Responsive**: Perfect on all devices (mobile, tablet, desktop) with mobile-first approach
- **Interactive**: Rich user interactions with hover effects, transitions, loading states, success/error feedback
- **Data Persistent**: Use localStorage/sessionStorage intelligently for state persistence
- **Error Handling**: Comprehensive error handling with user-friendly error messages
- **Accessible**: Proper ARIA labels, keyboard navigation, semantic HTML
- **Performance Optimized**: Fast loading, efficient DOM manipulation, debounced events where needed

Design Guidelines:
- Use modern CSS (Grid, Flexbox, CSS Variables, Animations, Transforms)
- Beautiful color schemes (use gradients, shadows, modern palettes)
- Smooth transitions and micro-interactions
- Professional typography with proper hierarchy
- White space and visual breathing room
- Icons using emoji or Unicode symbols (no external dependencies)
- Loading states and skeleton screens where appropriate
- Toast notifications or feedback for user actions

Code Quality:
- Vanilla JavaScript with ES6+ features (classes, arrow functions, destructuring, async/await)
- Modular code structure with clear separation of concerns
- Descriptive variable/function names
- Comment only complex logic, not obvious code
- DRY principle - no code repetition

CRITICAL - NO LOADING SCREENS OR SPLASH SCREENS:
- **ABSOLUTELY NO loading screens, splash screens, or delayed content**
- **DO NOT create elements with id="loading-screen" or class="loading"**
- **DO NOT use setTimeout/setInterval to delay showing content**
- **DO NOT show "Loading...", spinners, progress bars, or "Please wait" messages**
- The app interface MUST be visible IMMEDIATELY on page load (no delays, no animations blocking content)
- All content must appear within 100ms of page load
- All apps must be fully self-contained with inline/hardcoded data (no API calls, no fetch, no external data)
- User should see a fully functional app the instant the page loads
- You can add loading states for USER ACTIONS (button clicks), but NOT for initial page load

Return your response in THREE separate markdown code blocks (NOT as JSON):

```html
<!DOCTYPE html>
... complete HTML code here ...
```

```css
/* complete CSS code here */
```

```javascript
// complete JavaScript code here
```

The HTML must include proper DOCTYPE, meta tags, and link to style.css and script.js.
CSS and JS are separate file contents. Do NOT wrap in JSON - use markdown code blocks."""

    user_prompt = f"""Create a production-ready single-page application: {prompt}

Requirements:
- Make it fully functional with ALL necessary features
- Use stunning modern design with beautiful UI
- Add thoughtful interactions and animations
- Include proper error handling and loading states
- Make it intuitive and user-friendly
- Add any features that make sense for this type of app

Be creative and build something impressive that looks and feels professional."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",  # Claude Sonnet 4 - latest model
            max_tokens=16000,  # Increased for complex websites
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            system=system_prompt
        )

        response_text = message.content[0].text
        logger.info("Received AI response, extracting code blocks...")

        # Primary extraction: Look for markdown code blocks (recommended format)
        result = {}

        # Extract HTML
        if "```html" in response_text:
            html_start = response_text.find("```html") + 7
            html_end = response_text.find("```", html_start)
            result["html"] = response_text[html_start:html_end].strip()
            logger.info(f"Extracted HTML ({len(result['html'])} chars)")

        # Extract CSS
        if "```css" in response_text:
            css_start = response_text.find("```css") + 6
            css_end = response_text.find("```", css_start)
            result["css"] = response_text[css_start:css_end].strip()
            logger.info(f"Extracted CSS ({len(result['css'])} chars)")

        # Extract JavaScript
        if "```javascript" in response_text:
            js_start = response_text.find("```javascript") + 13
            js_end = response_text.find("```", js_start)
            result["js"] = response_text[js_start:js_end].strip()
            logger.info(f"Extracted JS ({len(result['js'])} chars)")
        elif "```js" in response_text:
            js_start = response_text.find("```js") + 5
            js_end = response_text.find("```", js_start)
            result["js"] = response_text[js_start:js_end].strip()
            logger.info(f"Extracted JS ({len(result['js'])} chars)")

        # Check if markdown extraction succeeded
        if all(key in result for key in ["html", "css", "js"]):
            logger.info("Successfully extracted code from markdown blocks")

            # Validate: Check for loading screens (common issue)
            html_lower = result["html"].lower()
            problematic_patterns = [
                "loading-screen",
                "id=\"loading\"",
                "class=\"loading\"",
                "please wait",
                "<div class=\"loader\"",
                "<div class=\"spinner\"",
                "loading....",
            ]

            found_patterns = [p for p in problematic_patterns if p in html_lower]
            if found_patterns:
                logger.warning(f"⚠️ Generated HTML contains loading screen patterns: {found_patterns}")
                logger.warning("This may cause the site to appear broken. AI ignored NO LOADING SCREEN instruction.")
                # Don't fail - just warn. The site might still work if JS properly removes it.

            # Validate JavaScript completeness
            js_code = result.get("js", "")
            if js_code:
                # Check for balanced braces
                open_braces = js_code.count('{')
                close_braces = js_code.count('}')
                if abs(open_braces - close_braces) > 2:  # Allow small variance
                    logger.error(f"⚠️ JavaScript has unbalanced braces: {{ {open_braces} vs }} {close_braces}")
                    logger.error("Code may be truncated or incomplete. Site will likely be broken.")

                # Check if code looks truncated (ends mid-statement)
                js_stripped = js_code.strip()
                if len(js_stripped) > 100:  # Only check if there's substantial code
                    last_100 = js_stripped[-100:]
                    if not (js_stripped.endswith('}') or js_stripped.endswith(';') or js_stripped.endswith(')')):
                        logger.warning(f"⚠️ JavaScript may be truncated. Last 100 chars: ...{last_100}")
                        logger.warning("Site functionality may be broken.")

                logger.info(f"JavaScript validation: {len(js_code)} chars, {open_braces} open braces, {close_braces} close braces")

            return result

        # Fallback: Try JSON format (legacy)
        logger.info("Markdown extraction incomplete, trying JSON fallback...")
        json_text = response_text

        if "```json" in json_text:
            json_start = json_text.find("```json") + 7
            json_end = json_text.find("```", json_start)
            json_text = json_text[json_start:json_end].strip()
        elif "```" in json_text and "```html" not in json_text:
            json_start = json_text.find("```") + 3
            json_end = json_text.find("```", json_start)
            json_text = json_text[json_start:json_end].strip()

        try:
            result = json.loads(json_text)
            if all(key in result for key in ["html", "css", "js"]):
                logger.info("Successfully parsed JSON format")
                return result
        except json.JSONDecodeError as je:
            logger.warning(f"JSON parsing also failed: {je}")

        # FALLBACK: Extract inline CSS/JS from HTML block (for complex games like snake)
        logger.info("Trying to extract inline CSS/JS from HTML block...")
        if "html" in result and result["html"]:
            import re

            html_content = result["html"]

            # Extract inline CSS from <style> tags
            if "css" not in result or not result["css"]:
                style_match = re.search(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
                if style_match:
                    result["css"] = style_match.group(1).strip()
                    logger.info(f"✓ Extracted inline CSS from HTML ({len(result['css'])} chars)")
                    # Remove inline style from HTML
                    result["html"] = re.sub(r'<style[^>]*>.*?</style>', '<link rel="stylesheet" href="style.css">', html_content, flags=re.DOTALL | re.IGNORECASE)
                else:
                    result["css"] = ""
                    logger.warning("No CSS found - using empty CSS")

            # Extract inline JS from <script> tags (excluding external scripts)
            if "js" not in result or not result["js"]:
                # Find script tags that have actual code (not external src)
                script_matches = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html_content, re.DOTALL | re.IGNORECASE)
                if script_matches:
                    # Combine all inline scripts
                    result["js"] = "\n\n".join([s.strip() for s in script_matches if s.strip()])
                    logger.info(f"✓ Extracted inline JavaScript from HTML ({len(result['js'])} chars)")
                    # Remove inline scripts from HTML and add external script tag
                    result["html"] = re.sub(r'<script(?![^>]*src=)[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                    # Add script tag before </body>
                    if '</body>' in result["html"]:
                        result["html"] = result["html"].replace('</body>', '<script src="script.js"></script>\n</body>')
                else:
                    result["js"] = ""
                    logger.warning("No JavaScript found - using empty JS")

            # Check if we now have all required parts
            if all(key in result for key in ["html", "css", "js"]):
                logger.info("✓ Successfully extracted inline CSS/JS from HTML!")
                return result

        # If we got here, extraction failed
        missing_keys = [k for k in ["html", "css", "js"] if k not in result]
        raise RuntimeError(f"Failed to extract required code blocks. Missing: {missing_keys}. Response preview: {response_text[:500]}")

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"AI generation failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to generate custom website: {e}")


async def _generate_with_openai(prompt: str, site_name: str, api_key: str) -> Dict[str, str]:
    """Generate website using OpenAI GPT-4 API (BEST QUALITY)"""
    client = OpenAI(api_key=api_key)

    system_prompt = """You are an expert web developer who creates beautiful, professional single-page applications.

When given a prompt, create a COMPLETE, production-ready single-page application with:
- Modern, professional UI design with beautiful colors and spacing
- Fully functional interactivity (all features must work)
- Responsive design that works on mobile and desktop
- Smooth animations and transitions
- Clean, well-organized code
- NO loading screens or placeholders - site must work immediately

CRITICAL: Return THREE separate code blocks in this EXACT format:

```html
<!DOCTYPE html>
... complete HTML code here ...
```

```css
/* complete CSS code here */
```

```javascript
// complete JavaScript code here
```

DO NOT use inline CSS or inline JavaScript. Always use separate blocks.
DO NOT wrap in JSON - use markdown code blocks as shown above."""

    user_prompt = f"""Create a dynamic single-page application: {prompt}

Requirements:
- Single HTML file with external CSS and JS (separate code blocks)
- Make it modern, beautiful, and fully functional
- Include ALL necessary functionality
- NO loading screens or "coming soon" placeholders
- The site must work immediately when opened
- Add thoughtful interactions and animations
- Make it professional and impressive

Remember: Return THREE separate markdown code blocks (html, css, js) - NOT JSON format."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # GPT-4 Turbo - best quality
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=16000
        )

        response_text = response.choices[0].message.content
        logger.info("Received OpenAI response, extracting code blocks...")

        # Extract code blocks (same logic as other generators)
        result = {}

        # Extract HTML
        if "```html" in response_text:
            html_start = response_text.find("```html") + 7
            html_end = response_text.find("```", html_start)
            result["html"] = response_text[html_start:html_end].strip()
            logger.info(f"Extracted HTML ({len(result['html'])} chars)")

        # Extract CSS
        if "```css" in response_text:
            css_start = response_text.find("```css") + 6
            css_end = response_text.find("```", css_start)
            result["css"] = response_text[css_start:css_end].strip()
            logger.info(f"Extracted CSS ({len(result['css'])} chars)")

        # Extract JavaScript
        if "```javascript" in response_text:
            js_start = response_text.find("```javascript") + 13
            js_end = response_text.find("```", js_start)
            result["js"] = response_text[js_start:js_end].strip()
            logger.info(f"Extracted JS ({len(result['js'])} chars)")
        elif "```js" in response_text:
            js_start = response_text.find("```js") + 5
            js_end = response_text.find("```", js_start)
            result["js"] = response_text[js_start:js_end].strip()
            logger.info(f"Extracted JS ({len(result['js'])} chars)")

        # Check if extraction succeeded
        if all(key in result for key in ["html", "css", "js"]):
            logger.info("✓ Successfully extracted all code blocks from OpenAI response")
            return result

        # FALLBACK: Extract inline CSS/JS from HTML block
        logger.info("Trying to extract inline CSS/JS from HTML block...")
        if "html" in result and result["html"]:
            import re

            html_content = result["html"]

            # Extract inline CSS from <style> tags
            if "css" not in result or not result["css"]:
                style_match = re.search(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
                if style_match:
                    result["css"] = style_match.group(1).strip()
                    logger.info(f"✓ Extracted inline CSS from HTML ({len(result['css'])} chars)")
                    result["html"] = re.sub(r'<style[^>]*>.*?</style>', '<link rel="stylesheet" href="style.css">', html_content, flags=re.DOTALL | re.IGNORECASE)
                else:
                    result["css"] = "/* No CSS provided by AI */"

            # Extract inline JS from <script> tags
            if "js" not in result or not result["js"]:
                script_matches = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html_content, re.DOTALL | re.IGNORECASE)
                if script_matches:
                    result["js"] = "\n\n".join([s.strip() for s in script_matches if s.strip()])
                    logger.info(f"✓ Extracted inline JavaScript from HTML ({len(result['js'])} chars)")
                    result["html"] = re.sub(r'<script(?![^>]*src=)[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                    if '</body>' in result["html"]:
                        result["html"] = result["html"].replace('</body>', '<script src="script.js"></script>\n</body>')
                else:
                    result["js"] = "// No JavaScript provided by AI"

            if all(key in result for key in ["html", "css", "js"]):
                logger.info("✓ Successfully extracted inline CSS/JS from HTML!")
                return result

        # If extraction failed
        missing_keys = [k for k in ["html", "css", "js"] if k not in result]
        raise RuntimeError(f"Failed to extract required code blocks. Missing: {missing_keys}. Response preview: {response_text[:500]}")

    except Exception as e:
        logger.error(f"OpenAI generation failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to generate custom website with OpenAI: {e}")


async def _generate_with_gemini(prompt: str, site_name: str, api_key: str) -> Dict[str, str]:
    """Generate website using Google Gemini API (FREE)"""
    from google import genai as genai_new
    client = genai_new.Client(api_key=api_key)

    system_prompt = """You are an expert full-stack web developer who creates PRODUCTION-READY, beautiful, and highly functional single-page applications.

Your code must be:
- **Professional Grade**: Clean, well-structured, maintainable code with best practices
- **Fully Functional**: All features work perfectly with proper event handling and state management
- **Visually Stunning**: Modern design with smooth animations, beautiful gradients, professional color schemes
- **Responsive**: Perfect on all devices (mobile, tablet, desktop) with mobile-first approach
- **Interactive**: Rich user interactions with hover effects, transitions, loading states, success/error feedback
- **Data Persistent**: Use localStorage/sessionStorage intelligently for state persistence
- **Error Handling**: Comprehensive error handling with user-friendly error messages
- **Accessible**: Proper ARIA labels, keyboard navigation, semantic HTML
- **Performance Optimized**: Fast loading, efficient DOM manipulation, debounced events where needed

Design Guidelines:
- Use modern CSS (Grid, Flexbox, CSS Variables, Animations, Transforms)
- Beautiful color schemes (use gradients, shadows, modern palettes)
- Smooth transitions and micro-interactions
- Professional typography with proper hierarchy
- White space and visual breathing room
- Icons using emoji or Unicode symbols (no external dependencies)
- Loading states and skeleton screens where appropriate
- Toast notifications or feedback for user actions

Code Quality:
- Vanilla JavaScript with ES6+ features (classes, arrow functions, destructuring, async/await)
- Modular code structure with clear separation of concerns
- Descriptive variable/function names
- Comment only complex logic, not obvious code
- DRY principle - no code repetition

CRITICAL - NO LOADING SCREENS OR SPLASH SCREENS:
- **ABSOLUTELY NO loading screens, splash screens, or delayed content**
- **DO NOT create elements with id="loading-screen" or class="loading"**
- **DO NOT use setTimeout/setInterval to delay showing content**
- **DO NOT show "Loading...", spinners, progress bars, or "Please wait" messages**
- The app interface MUST be visible IMMEDIATELY on page load (no delays, no animations blocking content)
- All content must appear within 100ms of page load
- All apps must be fully self-contained with inline/hardcoded data (no API calls, no fetch, no external data)
- User should see a fully functional app the instant the page loads
- You can add loading states for USER ACTIONS (button clicks), but NOT for initial page load

Return your response in THREE separate markdown code blocks (NOT as JSON):

```html
<!DOCTYPE html>
... complete HTML code here ...
```

```css
/* complete CSS code here */
```

```javascript
// complete JavaScript code here
```

The HTML must include proper DOCTYPE, meta tags, and link to style.css and script.js.
CSS and JS are separate file contents. Do NOT wrap in JSON - use markdown code blocks."""

    user_prompt = f"""Create a production-ready single-page application: {prompt}

Requirements:
- Make it fully functional with ALL necessary features
- Use stunning modern design with beautiful UI
- Add thoughtful interactions and animations
- Include proper error handling and loading states
- Make it intuitive and user-friendly
- Add any features that make sense for this type of app

Be creative and build something impressive that looks and feels professional.

{system_prompt}"""

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_prompt
        )

        # Get response text with proper error handling
        response_text = None
        if hasattr(response, 'text') and response.text:
            response_text = response.text
        elif hasattr(response, 'candidates') and response.candidates:
            # Try to get text from candidates
            if response.candidates[0].content.parts:
                response_text = response.candidates[0].content.parts[0].text

        if not response_text:
            logger.error(f"Gemini returned empty response. Response object: {response}")
            raise RuntimeError("Gemini API returned empty response. The response object had no text content.")

        logger.info("Received Gemini AI response, extracting code blocks...")
        logger.debug(f"Response length: {len(response_text)} characters")
    except Exception as e:
        error_msg = str(e)

        # Check for specific error types
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            logger.error("=" * 80)
            logger.error("GEMINI API QUOTA EXCEEDED!")
            logger.error("=" * 80)
            logger.error("You have exceeded the Gemini free tier quota (20 requests/day).")
            logger.error("Solutions:")
            logger.error("  1. Wait 24 hours for quota to reset")
            logger.error("  2. Use a different Gemini API key")
            logger.error("  3. Upgrade to paid Gemini plan")
            logger.error("=" * 80)
            raise RuntimeError(
                "❌ GEMINI API QUOTA EXCEEDED\n\n"
                "You've used all 20 free Gemini API requests for today.\n\n"
                "Solutions:\n"
                "  1. Wait 24 hours for quota to reset\n"
                "  2. Get a new Gemini API key from https://aistudio.google.com/app/apikey\n"
                "  3. Upgrade to paid plan\n\n"
                f"Original error: {error_msg}"
            )
        elif "rate" in error_msg.lower() or "limit" in error_msg.lower():
            raise RuntimeError(
                f"❌ GEMINI API RATE LIMIT\n\n"
                f"The Gemini API is rate limiting requests. Please wait a few seconds and try again.\n\n"
                f"Original error: {error_msg}"
            )
        else:
            # Re-raise original exception for other errors
            raise

    # Extract code blocks (same logic as Anthropic)
    try:
        result = {}

        # Extract HTML
        if "```html" in response_text:
            html_start = response_text.find("```html") + 7
            html_end = response_text.find("```", html_start)
            result["html"] = response_text[html_start:html_end].strip()
            logger.info(f"Extracted HTML ({len(result['html'])} chars)")

        # Extract CSS
        if "```css" in response_text:
            css_start = response_text.find("```css") + 6
            css_end = response_text.find("```", css_start)
            result["css"] = response_text[css_start:css_end].strip()
            logger.info(f"Extracted CSS ({len(result['css'])} chars)")

        # Extract JavaScript
        if "```javascript" in response_text:
            js_start = response_text.find("```javascript") + 13
            js_end = response_text.find("```", js_start)
            result["js"] = response_text[js_start:js_end].strip()
            logger.info(f"Extracted JS ({len(result['js'])} chars)")
        elif "```js" in response_text:
            js_start = response_text.find("```js") + 5
            js_end = response_text.find("```", js_start)
            result["js"] = response_text[js_start:js_end].strip()
            logger.info(f"Extracted JS ({len(result['js'])} chars)")

        # Check if extraction succeeded
        if all(key in result for key in ["html", "css", "js"]):
            logger.info("✓ Successfully extracted all code blocks from Gemini response")

            # CRITICAL: Validate and fix HTML to ensure CSS/JS are properly linked
            html = result["html"]

            # Check if HTML has correct stylesheet link
            if 'href="style.css"' not in html and "href='style.css'" not in html:
                logger.warning("⚠️ HTML missing proper CSS link - this will break styling!")
                logger.warning("   Looking for: href=\"style.css\"")
                # Try to fix by injecting proper link if <head> exists
                if '<head>' in html:
                    html = html.replace('</head>', '    <link rel="stylesheet" href="style.css">\n</head>')
                    logger.info("   ✓ Automatically added <link rel=\"stylesheet\" href=\"style.css\">")
                    result["html"] = html

            # Check if HTML has correct script link
            if 'src="script.js"' not in html and "src='script.js'" not in html:
                logger.warning("⚠️ HTML missing proper JS link - this will break interactivity!")
                logger.warning("   Looking for: src=\"script.js\"")
                # Try to fix by injecting proper script if </body> exists
                if '</body>' in html:
                    html = html.replace('</body>', '    <script src="script.js"></script>\n</body>')
                    logger.info("   ✓ Automatically added <script src=\"script.js\"></script>")
                    result["html"] = html

            logger.info("✓ HTML validation complete - CSS and JS links verified")
            return result

        # FALLBACK: Extract inline CSS/JS from HTML block (for complex games like snake)
        logger.info("Trying to extract inline CSS/JS from HTML block...")
        if "html" in result and result["html"]:
            import re

            html_content = result["html"]

            # Extract inline CSS from <style> tags
            if "css" not in result or not result["css"]:
                style_match = re.search(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
                if style_match:
                    result["css"] = style_match.group(1).strip()
                    logger.info(f"✓ Extracted inline CSS from HTML ({len(result['css'])} chars)")
                    # Remove inline style from HTML and add link tag
                    result["html"] = re.sub(r'<style[^>]*>.*?</style>', '<link rel="stylesheet" href="style.css">', html_content, flags=re.DOTALL | re.IGNORECASE)
                else:
                    result["css"] = "/* No CSS provided by AI */"
                    logger.warning("No CSS found - using empty CSS")

            # Extract inline JS from <script> tags (excluding external scripts)
            if "js" not in result or not result["js"]:
                # Find script tags that have actual code (not external src)
                script_matches = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html_content, re.DOTALL | re.IGNORECASE)
                if script_matches:
                    # Combine all inline scripts
                    result["js"] = "\n\n".join([s.strip() for s in script_matches if s.strip()])
                    logger.info(f"✓ Extracted inline JavaScript from HTML ({len(result['js'])} chars)")
                    # Remove inline scripts from HTML and add external script tag
                    result["html"] = re.sub(r'<script(?![^>]*src=)[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                    # Add script tag before </body>
                    if '</body>' in result["html"]:
                        result["html"] = result["html"].replace('</body>', '<script src="script.js"></script>\n</body>')
                    logger.info("✓ Added external script.js reference to HTML")
                else:
                    result["js"] = "// No JavaScript provided by AI"
                    logger.warning("No JavaScript found - using empty JS")

            # Check if we now have all required parts
            if all(key in result for key in ["html", "css", "js"]):
                logger.info("✓ Successfully extracted inline CSS/JS from HTML!")
                return result

        # If extraction still failed
        missing_keys = [k for k in ["html", "css", "js"] if k not in result]
        raise RuntimeError(f"Failed to extract required code blocks. Missing: {missing_keys}. Response preview: {response_text[:500]}")

    except Exception as e:
        logger.error(f"Gemini AI generation failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to generate custom website with Gemini: {e}")


async def update_website_with_ai(site_name: str, modification_request: str, original_prompt: str) -> Dict[str, str]:
    """
    Update an existing website based on modification request.
    Uses the original prompt as context and applies the requested changes.
    """
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError("Anthropic SDK not installed. Install with: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is required")

    logger.info(f"Updating website {site_name} with AI - Request: {modification_request}")

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """You are an expert web developer who modifies existing single-page applications based on user requests.

When given a modification request:
- Understand the original application context
- Apply ONLY the requested changes
- Maintain all existing functionality unless explicitly changed
- Keep the same design style and structure unless asked to change it
- Ensure the modified code is still production-ready and professional

Return your response in THREE separate markdown code blocks (NOT as JSON):

```html
<!DOCTYPE html>
... complete updated HTML code here ...
```

```css
/* complete updated CSS code here */
```

```javascript
// complete updated JavaScript code here
```

Do NOT wrap in JSON - use markdown code blocks."""

    user_prompt = f"""Original application: {original_prompt}

Modification request: {modification_request}

Generate the COMPLETE updated code (HTML, CSS, JS) with the requested modifications applied.
Keep everything else the same. Make sure all features still work perfectly."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",  # Claude Sonnet 4 - latest model
            max_tokens=16000,  # Increased for complex websites
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            system=system_prompt
        )

        response_text = message.content[0].text
        logger.info("Received AI response, extracting code blocks...")

        # Primary extraction: Look for markdown code blocks
        result = {}

        # Extract HTML
        if "```html" in response_text:
            html_start = response_text.find("```html") + 7
            html_end = response_text.find("```", html_start)
            result["html"] = response_text[html_start:html_end].strip()
            logger.info(f"Extracted HTML ({len(result['html'])} chars)")

        # Extract CSS
        if "```css" in response_text:
            css_start = response_text.find("```css") + 6
            css_end = response_text.find("```", css_start)
            result["css"] = response_text[css_start:css_end].strip()
            logger.info(f"Extracted CSS ({len(result['css'])} chars)")

        # Extract JavaScript
        if "```javascript" in response_text:
            js_start = response_text.find("```javascript") + 13
            js_end = response_text.find("```", js_start)
            result["js"] = response_text[js_start:js_end].strip()
            logger.info(f"Extracted JS ({len(result['js'])} chars)")
        elif "```js" in response_text:
            js_start = response_text.find("```js") + 5
            js_end = response_text.find("```", js_start)
            result["js"] = response_text[js_start:js_end].strip()
            logger.info(f"Extracted JS ({len(result['js'])} chars)")

        # Check if extraction succeeded
        if all(key in result for key in ["html", "css", "js"]):
            logger.info("Successfully extracted code from markdown blocks")
            return result

        # FALLBACK: Extract inline CSS/JS from HTML block
        logger.info("Trying to extract inline CSS/JS from HTML block...")
        if "html" in result and result["html"]:
            import re

            html_content = result["html"]

            # Extract inline CSS from <style> tags
            if "css" not in result or not result["css"]:
                style_match = re.search(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
                if style_match:
                    result["css"] = style_match.group(1).strip()
                    logger.info(f"✓ Extracted inline CSS from HTML ({len(result['css'])} chars)")
                    result["html"] = re.sub(r'<style[^>]*>.*?</style>', '<link rel="stylesheet" href="style.css">', html_content, flags=re.DOTALL | re.IGNORECASE)
                else:
                    result["css"] = "/* No CSS changes */"

            # Extract inline JS from <script> tags
            if "js" not in result or not result["js"]:
                script_matches = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html_content, re.DOTALL | re.IGNORECASE)
                if script_matches:
                    result["js"] = "\n\n".join([s.strip() for s in script_matches if s.strip()])
                    logger.info(f"✓ Extracted inline JavaScript from HTML ({len(result['js'])} chars)")
                    result["html"] = re.sub(r'<script(?![^>]*src=)[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                    if '</body>' in result["html"]:
                        result["html"] = result["html"].replace('</body>', '<script src="script.js"></script>\n</body>')
                else:
                    result["js"] = "// No JavaScript changes"

            # Check if we now have all required parts
            if all(key in result for key in ["html", "css", "js"]):
                logger.info("✓ Successfully extracted inline CSS/JS from HTML!")
                return result

        # If extraction still failed
        missing_keys = [k for k in ["html", "css", "js"] if k not in result]
        raise RuntimeError(f"Failed to extract required code blocks. Missing: {missing_keys}. Response preview: {response_text[:500]}")

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"AI update failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to update website: {e}")


def generate_and_deploy_in_background(site_type: str, site_name: str, custom_content: Dict, prompt: str):
    """Generate website and deploy to Vercel in the background using a separate thread"""

    # CRITICAL: Write to /tmp FIRST to prove thread started
    # This happens BEFORE any other operations that might fail
    import sys
    emergency_log = f"/tmp/thread_emergency_{site_name}.log"
    try:
        with open(emergency_log, 'w') as f:
            f.write(f"THREAD STARTED at {datetime.now().isoformat()}\n")
            f.write(f"Args: site_type={site_type}, site_name={site_name}, prompt={prompt[:50]}\n")
            f.write(f"SITES_DIR={SITES_DIR}\n")
            f.write(f"Thread ID: {threading.current_thread().ident}\n")
    except Exception as e:
        sys.stderr.write(f"EMERGENCY LOG FAILED: {e}\n")
        sys.stderr.flush()

    # Write to a separate log file for debugging
    thread_log_file = SITES_DIR / f"deployment_thread_{site_name}.log"

    def log_to_file(msg):
        """Log to both logger and file"""
        logger.info(msg)
        try:
            with open(thread_log_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - {msg}\n")
        except Exception as e:
            # Also write to emergency log if normal log fails
            try:
                with open(emergency_log, 'a') as f:
                    f.write(f"LOG ERROR: {e}\n")
                    f.write(f"Message was: {msg}\n")
            except:
                pass

    try:
        log_to_file("=" * 80)
        log_to_file(f"[BACKGROUND DEPLOYMENT STARTED] {site_name}")
        log_to_file(f"[Thread] Prompt: {prompt[:100]}...")
        log_to_file("=" * 80)

        # Check if cancelled before starting
        if _deployment_cancelled.is_set():
            log_to_file(f"[CANCELLED] Deployment cancelled before generation started")
            deployments = load_deployment_history()
            for dep in reversed(deployments):
                if dep.get("site_name") == site_name:
                    dep["deployment_status"] = "cancelled"
                    dep["cancelled_at"] = datetime.now().isoformat()
                    break
            save_deployment_history(deployments)
            return

        # Update status to "generating"
        log_to_file("[Step 1] Loading deployment history...")
        deployments = load_deployment_history()
        log_to_file(f"[Step 1] Found {len(deployments)} existing deployments")

        found = False
        for dep in reversed(deployments):
            if dep.get("site_name") == site_name and dep.get("deployment_status") == "generating":
                dep["deployment_status"] = "generating"
                dep["generation_started_at"] = datetime.now().isoformat()
                found = True
                log_to_file(f"[Step 1] Updated status to 'generating' for {site_name}")
                break

        if not found:
            log_to_file(f"[Step 1] WARNING: Could not find deployment record for {site_name}")

        save_deployment_history(deployments)
        log_to_file("[Step 1] Saved deployment history")

        # Run async generation in a new event loop (thread-safe)
        log_to_file("[Step 2] Creating new event loop...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Generate website files
        log_to_file(f"[Step 2] Generating website files (type={site_type})...")
        project_path = loop.run_until_complete(generate_website(site_type, site_name, custom_content, prompt))
        log_to_file(f"[Step 2] Website generated at: {project_path}")

        # Check if cancelled after generation
        if _deployment_cancelled.is_set():
            log_to_file(f"[CANCELLED] Deployment cancelled after generation")
            loop.close()
            deployments = load_deployment_history()
            for dep in reversed(deployments):
                if dep.get("site_name") == site_name:
                    dep["deployment_status"] = "cancelled"
                    dep["cancelled_at"] = datetime.now().isoformat()
                    break
            save_deployment_history(deployments)
            return

        # Update status to "deploying"
        log_to_file("[Step 3] Updating status to 'deploying'...")
        deployments = load_deployment_history()
        for dep in reversed(deployments):
            if dep.get("site_name") == site_name:
                dep["deployment_status"] = "deploying"
                dep["generation_completed_at"] = datetime.now().isoformat()
                dep["project_path"] = str(project_path)
                log_to_file(f"[Step 3] Updated deployment record")
                break
        save_deployment_history(deployments)
        log_to_file("[Step 3] Saved deployment history")

        # Deploy to Vercel
        log_to_file("[Step 4] Deploying to Vercel...")
        deploy_url = loop.run_until_complete(deploy_to_vercel_internal(str(project_path), site_name, thread_log_file))
        loop.close()
        log_to_file(f"[Step 4] Background deployment successful: {deploy_url}")

        # Update deployment history with successful URL
        log_to_file("[Step 5] Updating deployment history with final URL...")
        deployments = load_deployment_history()
        log_to_file(f"[Step 5] Loaded history, has {len(deployments)} entries")

        updated = False
        for dep in reversed(deployments):
            if dep.get("site_name") == site_name:
                old_status = dep.get("deployment_status")
                dep["deploy_url"] = deploy_url
                dep["deployment_status"] = "deployed"
                dep["deployed_at"] = datetime.now().isoformat()
                log_to_file(f"[Step 5] Updated {site_name}: {old_status} -> deployed, URL={deploy_url}")
                updated = True
                break

        if not updated:
            log_to_file(f"[Step 5] ERROR: Could not find {site_name} in history to update!")

        save_deployment_history(deployments)
        log_to_file(f"[Step 5] Saved deployment history - COMPLETE at {datetime.now().isoformat()}!")

        # Verify the save worked by reading it back
        verify_data = load_deployment_history()
        verify_entry = next((d for d in reversed(verify_data) if d.get("site_name") == site_name), None)
        if verify_entry and verify_entry.get("deployment_status") == "deployed":
            log_to_file(f"[Step 5] ✓ VERIFIED: History file shows {site_name} as 'deployed'")
        else:
            log_to_file(f"[Step 5] ✗ WARNING: Verification failed! Entry not found or wrong status")

        log_to_file(f"[FINAL] Successfully completed deployment for {site_name}")

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        log_to_file(f"[ERROR] Background generation/deployment failed for {site_name}")
        log_to_file(f"[ERROR] Exception: {e}")
        log_to_file(f"[ERROR] Traceback:\n{error_details}")
        logger.error(f"[Thread] Background generation/deployment failed for {site_name}: {e}", exc_info=True)

        # Update deployment history with failure
        log_to_file("[ERROR] Updating deployment history with failure status...")
        deployments = load_deployment_history()
        for dep in reversed(deployments):
            if dep.get("site_name") == site_name:
                dep["deployment_status"] = "failed"
                dep["error"] = str(e)
                dep["failed_at"] = datetime.now().isoformat()
                log_to_file(f"[ERROR] Marked {site_name} as failed in history")
                break
        save_deployment_history(deployments)
        log_to_file("[ERROR] Saved deployment history with failure status")


def deploy_in_background_sync(project_path: str, site_name: str, site_type: str, prompt: str):
    """Deploy to Vercel in the background using a separate thread (for already-generated sites)"""
    try:
        logger.info(f"[Thread] Starting background deployment for {site_name}")

        # Run async deployment in a new event loop (thread-safe)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Note: Can't pass thread_log_file here as it's not available in this scope
        deploy_url = loop.run_until_complete(deploy_to_vercel_internal(project_path, site_name, None))
        loop.close()

        logger.info(f"[Thread] Background deployment successful: {deploy_url}")

        # Update deployment history with successful URL
        deployments = load_deployment_history()
        for dep in reversed(deployments):
            if dep.get("site_name") == site_name and dep.get("deployment_status") == "deploying":
                dep["deploy_url"] = deploy_url
                dep["deployment_status"] = "deployed"
                dep["deployed_at"] = datetime.now().isoformat()
                break
        save_deployment_history(deployments)

        logger.info(f"[Thread] Updated deployment history for {site_name}")

    except Exception as e:
        logger.error(f"[Thread] Background deployment failed for {site_name}: {e}")

        # Update deployment history with failure
        deployments = load_deployment_history()
        for dep in reversed(deployments):
            if dep.get("site_name") == site_name and dep.get("deployment_status") == "deploying":
                dep["deployment_status"] = "failed"
                dep["error"] = str(e)
                dep["deployed_at"] = datetime.now().isoformat()
                break
        save_deployment_history(deployments)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="create_and_deploy_site",
            description="Generate a static website from a natural language prompt using AI (Anthropic Claude or FREE Google Gemini) and automatically deploy it to Vercel. Works for ANY type of single-page application (todo apps, calculators, timers, social media pages, etc). Returns ONLY deployment START confirmation - NOT the final URL. Uses Google Gemini FREE API. CRITICAL RESPONSE RULES: (1) This tool STARTS deployment in background (2) NEVER return a URL immediately after calling this tool (3) Tell user to use list_deployed_sites after 90-120 seconds to get the final URL (4) ONLY mention 'Vercel' platform, NEVER 'Netlify' (5) All URLs end in '.vercel.app' NOT '.netlify.app' (6) DO NOT construct URLs manually - ONLY use URLs from list_deployed_sites tool result (7) If asked about the same deployment again, call list_deployed_sites to check current status before responding",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Natural language description of what website to create. Examples: 'create a todo app', 'build a portfolio website', 'make a landing page'"
                    },
                    "site_name": {
                        "type": "string",
                        "description": "Optional custom name for the site. If not provided, a name will be auto-generated based on site type and timestamp."
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="get_deployment_url",
            description="Get the deployed URL for a website. Use this when user asks: 'show me URL', 'what's the URL', 'give me the link', 'deployed URL', 'show my site', 'where is my site'. ALWAYS call this tool - NEVER make up URLs. Returns the actual production URL from Vercel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_name_or_description": {
                        "type": "string",
                        "description": "Optional: Name or description of the site to find (e.g., 'timer', 'landing page', 'tata motors'). If not provided, shows all recent deployments."
                    }
                }
            }
        ),
        Tool(
            name="list_deployed_sites",
            description="List all deployed websites with their URLs and status. Use when user asks: 'show my sites', 'list deployments', 'what have I deployed'. ALWAYS call this - NEVER answer from memory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Optional search filter to find specific deployments (e.g., 'calculator', 'todo', 'social media'). Matches against site names and prompts."
                    }
                }
            }
        ),
        Tool(
            name="update_and_redeploy_site",
            description="Update an existing deployed website with modifications. Use this when the user wants to change something about their current site (change colors, add features, modify content, etc.). This will regenerate the site with the requested changes and redeploy it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_name": {
                        "type": "string",
                        "description": "Name of the site to update (from list_deployed_sites)"
                    },
                    "modification_request": {
                        "type": "string",
                        "description": "Description of what changes to make. Examples: 'change the background color to blue', 'add a dark mode toggle', 'make the buttons bigger'"
                    }
                },
                "required": ["site_name", "modification_request"]
            }
        )
    ]


@app.list_prompts()
async def list_prompts() -> list[Prompt]:
    """List available prompts"""
    return [
        Prompt(
            name="vercel_deployment_agent",
            description="System instructions for Vercel Deployment Agent - MUST be applied to EVERY conversation"
        )
    ]


@app.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> GetPromptResult:
    """Get a specific prompt"""
    if name == "vercel_deployment_agent":
        return GetPromptResult(
            description="Critical system instructions for Vercel Deployment Agent behavior",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="""🤖 VERCEL DEPLOYMENT AGENT - MANDATORY BEHAVIOR RULES

You are an AI assistant helping users deploy websites to Vercel.

═══════════════════════════════════════════════════════════════════
🚨🚨🚨 CRITICAL: TOOL CALLING POLICY - NO EXCEPTIONS 🚨🚨🚨
═══════════════════════════════════════════════════════════════════

RULE 1: ALWAYS CALL TOOLS - EVERY SINGLE TIME
When a user asks about deployments, URLs, or site status:
✅ ALWAYS call get_deployment_url or list_deployed_sites
✅ Call these tools EVERY SINGLE TIME user asks, even if:
   - You just called it 1 second ago
   - It's the 2nd, 3rd, 10th, 15th, or 50th time in this conversation
   - You think you remember the answer
   - You have the information in your context
   - The deployment was "generating" last time you checked
   - You already told the user "it's not ready yet"

❌ NEVER EVER answer from memory or context
❌ NEVER EVER skip tool calls because you "already know"
❌ NEVER EVER say "when I last checked" or "I don't have updates"
❌ NEVER EVER assume information is still current
❌ NEVER EVER use phrases like:
   - "The deployment was still in progress when I last checked"
   - "I don't have the deployed URL"
   - "I don't have any further updates"
   - "It wasn't ready last time"

🚨 IF USER ASKS FOR URL/STATUS → CALL THE TOOL IMMEDIATELY 🚨
No matter how many times they ask. No exceptions. No excuses.

═══════════════════════════════════════════════════════════════════
🎯 DEPLOYMENT NOT READY SCENARIO (MOST IMPORTANT)
═══════════════════════════════════════════════════════════════════

This is the MOST COMMON scenario where you MUST call tools repeatedly:

Turn 1:
User: "show me deployed url"
You: *calls get_deployment_url* → Result: "Status: generating"
You: "Your site is still being generated. It will be ready in 1-2 minutes."

Turn 2 (30 seconds later):
User: "show me deployed url"
You: *calls get_deployment_url AGAIN* → Result: "Status: generating"
You: "Your site is still being generated. Almost ready!"

Turn 3 (1 minute later):
User: "show me deployed url"
You: *calls get_deployment_url AGAIN* → Result: "Status: deployed, URL: https://..."
You: "Your site is now live! Here's your URL: https://..."

🚨 KEY POINT: Call the tool EVERY TIME, even if it was "generating" before!
The status changes from generating → deploying → deployed
You MUST check EVERY TIME to see if it's ready now!

═══════════════════════════════════════════════════════════════════
📋 MORE EXAMPLES
═══════════════════════════════════════════════════════════════════

User: "show me last deployed url"
You: *calls list_deployed_sites* → Shows results

User: "show me deployed url" (asked 10 times in a row)
You: *calls get_deployment_url 10 TIMES* → Shows result each time

User: "give me the link"
You: *calls get_deployment_url* → Shows URL

User: "is my site ready?"
You: *calls list_deployed_sites* → Shows status

═══════════════════════════════════════════════════════════════════
🎯 MANDATORY BEHAVIOR SUMMARY
═══════════════════════════════════════════════════════════════════

1. User asks about URL/deployment → CALL TOOL (no exceptions)
2. User asks again → CALL TOOL AGAIN (no exceptions)
3. User asks 15 times → CALL TOOL 15 TIMES (no exceptions)
4. Deployment was "generating" last time → CALL TOOL AGAIN (status might have changed!)
5. You don't remember the URL → CALL TOOL (never answer from memory)

Platform: This server deploys to VERCEL only (never Netlify)
All URLs end in .vercel.app (never .netlify.app)

🚨 FINAL REMINDER: CALL TOOLS EVERY TIME. NO EXCEPTIONS. 🚨
"""
                    )
                )
            ]
        )

    raise ValueError(f"Unknown prompt: {name}")


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """
    Handle tool calls

    CRITICAL: This MCP server deploys ONLY to VERCEL, never to Netlify.
    The user has migrated from Netlify to Vercel.
    When generating ANY response to the user:
    - ALWAYS say "Vercel" or "Vercel platform"
    - NEVER mention "Netlify" or "Netlify platform"
    - NEVER use "netlify.app" URLs - only "vercel.app"
    - This is a Vercel deployment server, not a Netlify deployment server

    AGENT BEHAVIOR FOR DEPLOYMENTS:
    When create_and_deploy_site is called:
    1. Tell user: "I'll check the status for you automatically in 2 minutes"
    2. WAIT 120 seconds (do not respond during this time)
    3. AUTOMATICALLY call list_deployed_sites with the site name as filter
    4. Show the deployed URL to the user WITHOUT them having to ask
    5. If status is "generating", wait 60 more seconds and check again
    6. Do NOT make the user ask "show me deployed url" multiple times
    """
    import sys  # Ensure sys is available in function scope
    try:
        if arguments is None:
            arguments = {}

        if name == "create_and_deploy_site":
            # CRITICAL DEBUG: Write to file to verify tool is called
            with open("/tmp/vercel_tool_called.log", "a") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"Tool called at: {datetime.now().isoformat()}\n")
                f.write(f"Arguments: {arguments}\n")
                f.write(f"{'='*80}\n")

            prompt = arguments.get("prompt", "")
            site_name = arguments.get("site_name")

            logger.info("=" * 80)
            logger.info(f"[TOOL CALL] create_and_deploy_site")
            logger.info(f"[TOOL CALL] Prompt: {prompt}")
            logger.info(f"[TOOL CALL] Custom site_name: {site_name}")
            logger.info("=" * 80)

            # Detect site type from prompt
            site_type, auto_site_name = detect_site_type_from_prompt(prompt)

            # Use provided site_name or auto-generated one
            # ALWAYS append timestamp to ensure uniqueness on Vercel
            if site_name:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                # Convert to lowercase and replace spaces/invalid chars for Vercel compatibility
                # Vercel requires: lowercase, no spaces, only letters/digits/.-_
                sanitized_name = site_name.lower()
                sanitized_name = sanitized_name.replace(" ", "-")  # Replace spaces with hyphens
                sanitized_name = sanitized_name.replace("_", "-")  # Normalize underscores to hyphens
                # Remove any other invalid characters (keep only alphanumeric, dots, hyphens)
                import re
                sanitized_name = re.sub(r'[^a-z0-9.-]', '', sanitized_name)
                final_site_name = f"{sanitized_name}-{timestamp}"
            else:
                final_site_name = auto_site_name

            logger.info(f"[TOOL CALL] Detected site type: {site_type}")
            logger.info(f"[TOOL CALL] Final site name: {final_site_name}")

            # Save to history as "generating" (not "deploying" yet)
            logger.info(f"[TOOL CALL] Loading deployment history...")
            deployments = load_deployment_history()
            logger.info(f"[TOOL CALL] Current history has {len(deployments)} entries")

            deployment_record = {
                "site_name": final_site_name,
                "site_type": site_type,
                "prompt": prompt,
                "deploy_url": "generating",
                "project_path": "",
                "created_at": datetime.now().isoformat(),
                "deployment_status": "generating"
            }
            deployments.append(deployment_record)
            logger.info(f"[TOOL CALL] Added deployment record for {final_site_name}")

            save_deployment_history(deployments)
            logger.info(f"[TOOL CALL] Saved deployment history (now has {len(deployments)} entries)")

            # CRITICAL: Cancel any existing deployment before starting new one
            global _active_deployment, _deployment_cancelled
            with _active_deployment_lock:
                if _active_deployment is not None:
                    old_thread, old_site_name = _active_deployment
                    if old_thread.is_alive():
                        logger.info(f"[TOOL CALL] Cancelling previous deployment: {old_site_name}")
                        _deployment_cancelled.set()  # Signal cancellation

                        # Wait for thread to finish (with timeout)
                        old_thread.join(timeout=2.0)
                        if old_thread.is_alive():
                            logger.warning(f"[TOOL CALL] Previous deployment didn't stop in time, continuing anyway")

                # Reset cancellation flag for new deployment
                _deployment_cancelled.clear()

            # Start generation AND deployment in background thread
            # This ensures we return immediately (no timeout)
            logger.info(f"[TOOL CALL] Creating background thread for {final_site_name}...")
            thread = threading.Thread(
                target=generate_and_deploy_in_background,
                args=(site_type, final_site_name, {}, prompt),
                daemon=True
            )
            thread.start()

            # Track the new active deployment
            with _active_deployment_lock:
                _active_deployment = (thread, final_site_name)

            logger.info(f"[TOOL CALL] Thread started! Thread ID: {thread.ident}, Is Alive: {thread.is_alive()}")
            logger.info(f"[TOOL CALL] Returning response to agent...")

            # Return immediately
            site_type_name = {
                "todo": "Todo App",
                "portfolio": "Portfolio Website",
                "landing": "Landing Page"
            }.get(site_type, "AI-Generated Website")

            # Check if we cancelled a previous deployment
            cancelled_msg = ""
            if _deployment_cancelled.is_set() or (_active_deployment and _active_deployment[1] != final_site_name):
                cancelled_msg = "\n⚠️  Previous deployment was cancelled to start this new one.\n"

            result_text = f"""Website Creation Started!

Site Type: {site_type_name}
Site Name: {final_site_name}
{cancelled_msg}
Your website is being generated and deployed in the background.
⏱️  Generation: 90-120 seconds (AI-powered)
⏱️  Deployment: 30-60 seconds (Vercel)
⏱️  Total Time: ~2-3 minutes

AGENT INSTRUCTIONS:
1. Tell the user: "I'll automatically check the deployment status for you in 2 minutes."
2. WAIT for 2 minutes (120 seconds) - do NOT respond to the user during this time
3. After 2 minutes, AUTOMATICALLY call 'list_deployed_sites' with filter='{final_site_name}'
4. Show the user the deployed URL immediately - do NOT make them ask for it
5. If status is still "generating", wait another 60 seconds and check again
6. CRITICAL: If user asks about URL/deployments at ANY time, call 'list_deployed_sites' immediately"""

            return [TextContent(type="text", text=result_text)]

        elif name == "get_deployment_url":
            # This tool is a simpler, more focused version specifically for getting URLs
            # It just calls list_deployed_sites with the provided filter
            try:
                current_time = datetime.now()
                filter_query = arguments.get("site_name_or_description", "").strip().lower()

                logger.info(f"[GET_URL TOOL] Getting deployment URL (filter: '{filter_query}') at {current_time.isoformat()}")

                # Use the same logic as list_deployed_sites
                deployments = load_deployment_history()

                active_deployments = [
                    d for d in deployments
                    if (d.get("deployment_status") in ["generating", "deploying"]
                        or (d.get("deployment_status") == "deployed" and "vercel.app" in d.get("deploy_url", "")))
                    and d.get("deployment_status") not in ["cancelled", "failed"]
                ]

                if not active_deployments:
                    result_text = "No deployed sites found. Deploy a site first using create_and_deploy_site."
                    return [TextContent(type="text", text=result_text)]

                # If filter provided, search for matching deployment
                if filter_query:
                    normalized_filter = filter_query.replace("_", " ").replace("-", " ").strip()

                    filtered_deployments = []
                    for d in active_deployments:
                        site_name_norm = d.get("site_name", "").lower().replace("_", " ").replace("-", " ")
                        prompt_norm = d.get("prompt", "").lower().replace("_", " ").replace("-", " ")

                        if normalized_filter in site_name_norm or normalized_filter in prompt_norm:
                            filtered_deployments.append(d)

                    active_deployments = filtered_deployments

                if not active_deployments:
                    result_text = f"No deployed sites found matching '{filter_query}'."
                    return [TextContent(type="text", text=result_text)]

                # PRIORITIZE: Show deployments that are in progress (generating/deploying) FIRST
                # This ensures we show the NEW deployment being created, not an old completed one
                generating_deployments = [d for d in active_deployments if d.get("deployment_status") in ["generating", "deploying"]]

                if generating_deployments:
                    # Show the most recent in-progress deployment
                    latest = generating_deployments[-1]
                else:
                    # No in-progress deployments, show most recent completed one
                    latest = active_deployments[-1]
                site_name = latest.get("site_name", "")
                deploy_url = latest.get("deploy_url", "")
                status = latest.get("deployment_status", "")

                if status == "deployed":
                    clean_url = clean_display_url(deploy_url)
                    result_text = f"""DEPLOYED_URL={clean_url}

🚨 AGENT: Your answer MUST contain this URL: {clean_url}

Example answer: "Your site is deployed! Here's the URL: {clean_url}"

DO NOT say: "I need to call a tool"
DO NOT say: "I've used all tool calls"
JUST give the user the URL above.

Status: Deployed and Live (queried at {current_time.strftime('%H:%M:%S')})
Site: {site_name}"""
                elif status == "generating":
                    result_text = f"""════════════════════════════════════════════════════════════════════
🚨 AGENT: NO URL AVAILABLE YET - SITE IS STILL BEING GENERATED
════════════════════════════════════════════════════════════════════

❌ DO NOT create URL: https://{site_name}.vercel.app
❌ DO NOT tell user the site is deployed
✅ Tell user: "Your site is being generated, check back in 1-2 minutes"

════════════════════════════════════════════════════════════════════

⚙️ Site '{site_name}' is currently being generated by AI. Check back in 30 seconds.

🚨🚨🚨 CRITICAL AGENT INSTRUCTION 🚨🚨🚨
IF USER ASKS AGAIN IN THE FUTURE (even 10 seconds from now):
→ DO NOT answer from memory
→ DO NOT repeat "being generated" without checking
→ YOU MUST CALL THIS TOOL AGAIN to get updated status
→ Status may have changed to "deployed" by then
→ ALWAYS call tools on every request about deployments"""
                elif status == "deploying":
                    result_text = f"""════════════════════════════════════════════════════════════════════
🚨 AGENT: NO URL AVAILABLE YET - SITE IS BEING DEPLOYED
════════════════════════════════════════════════════════════════════

❌ DO NOT create URL: https://{site_name}.vercel.app
❌ DO NOT tell user the site is deployed
✅ Tell user: "Your site is being deployed to Vercel, check back in 30 seconds"

════════════════════════════════════════════════════════════════════

🔄 Site '{site_name}' is being deployed to Vercel. Check back in 60 seconds.

🚨🚨🚨 CRITICAL AGENT INSTRUCTION 🚨🚨🚨
IF USER ASKS AGAIN IN THE FUTURE (even 10 seconds from now):
→ DO NOT answer from memory
→ DO NOT repeat "being deployed" without checking
→ YOU MUST CALL THIS TOOL AGAIN to get updated status
→ Status may have changed to "deployed" by then
→ ALWAYS call tools on every request about deployments"""
                else:
                    result_text = f"Site '{site_name}' status: {status}"

                return [TextContent(type="text", text=result_text)]

            except Exception as e:
                import traceback
                error_msg = f"ERROR in get_deployment_url:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
                logger.error(error_msg)
                return [TextContent(type="text", text=error_msg)]

        elif name == "list_deployed_sites":
            try:
                current_time = datetime.now()
                filter_query = arguments.get("filter", "").strip().lower()
                logger.info(f"[LIST TOOL] Listing deployed sites (filter: '{filter_query}') at {current_time.isoformat()}")

                deployments = load_deployment_history()
                logger.info(f"[LIST TOOL] Loaded {len(deployments)} total deployments from history")

                # Log the last 3 entries for debugging
                if deployments:
                    logger.info(f"[LIST TOOL] Last 3 entries:")
                    for d in deployments[-3:]:
                        logger.info(f"[LIST TOOL]   - {d.get('site_name')}: {d.get('deployment_status')} @ {d.get('deployed_at', d.get('created_at', 'no time'))[:19]}")

                # Filter to show:
                # - All "generating" and "deploying" sites (new Vercel sites)
                # - Only "deployed" sites with vercel.app URLs (exclude old Netlify sites)
                # - EXCLUDE "cancelled" and "failed" sites
                active_deployments = [
                    d for d in deployments
                    if (d.get("deployment_status") in ["generating", "deploying"]
                        or (d.get("deployment_status") == "deployed" and "vercel.app" in d.get("deploy_url", "")))
                    and d.get("deployment_status") not in ["cancelled", "failed"]
                ]

                logger.info(f"[LIST TOOL] Filtered to {len(active_deployments)} active Vercel deployments (excluded cancelled/failed)")

                if not active_deployments:
                    result_text = "No sites have been successfully deployed yet. Use create_and_deploy_site to deploy your first website!"
                    return [TextContent(type="text", text=result_text)]

                # If filter is provided, search through ALL deployments for matches
                if filter_query:
                    # Normalize filter query: replace ALL separators with spaces for flexible matching
                    # "timer", "countdown-timer", "countdown_timer" all match "countdown timer"
                    normalized_filter = filter_query.replace("_", " ").replace("-", " ").strip()

                    logger.info(f"Searching with normalized filter: '{normalized_filter}'")
                    logger.info(f"Total active deployments to search: {len(active_deployments)}")

                    filtered_deployments = []

                    # Pre-scan to find deployed sites and their URLs for top-level summary
                    deployed_urls = []
                    for d in active_deployments:
                        # Normalize ALL searchable fields consistently
                        site_name_raw = d.get("site_name", "")
                        prompt_raw = d.get("prompt", "")
                        site_type_raw = d.get("site_type", "")

                        site_name_norm = site_name_raw.lower().replace("_", " ").replace("-", " ")
                        prompt_norm = prompt_raw.lower().replace("_", " ").replace("-", " ")
                        site_type_norm = site_type_raw.lower().replace("_", " ").replace("-", " ")

                        # Match filter against ALL normalized fields
                        match_site = normalized_filter in site_name_norm
                        match_prompt = normalized_filter in prompt_norm
                        match_type = normalized_filter in site_type_norm

                        if match_site or match_prompt or match_type:
                            filtered_deployments.append(d)
                            logger.info(f"✓ Matched: {site_name_raw} (site={match_site}, prompt={match_prompt}, type={match_type})")

                    active_deployments = filtered_deployments
                    logger.info(f"Filter results: {len(active_deployments)} matches found")

                    if not active_deployments:
                        result_text = f"No deployed sites found matching '{arguments.get('filter', '')}'. Try a different search term or check if the site is still deploying."
                        return [TextContent(type="text", text=result_text)]

                    # PRIORITIZE: Show deployments that are in progress (generating/deploying) FIRST
                    # This ensures we show the NEW deployment being created, not an old completed one
                    generating_deployments = [d for d in active_deployments if d.get("deployment_status") in ["generating", "deploying"]]

                    if generating_deployments:
                        # In-progress deployments exist - show the most recent one at the top
                        latest_deployment = generating_deployments[-1]
                        # Move it to the front for display
                        active_deployments = [latest_deployment] + [d for d in active_deployments if d != latest_deployment]
                        logger.info(f"⚠️ Prioritizing in-progress deployment: {latest_deployment.get('site_name')}")

                    # For filtered results (usually single site), show URL prominently at top
                    if len(active_deployments) == 1:
                        single_dep = active_deployments[0]
                        single_status = single_dep.get("deployment_status")
                        single_name = single_dep.get("site_name", "")

                        if single_status == "deployed":
                            production_url = clean_display_url(single_dep.get("deploy_url", ""))
                            result_lines = [
                                f"DEPLOYED_URL={production_url}",
                                f"",
                                f"🚨 AGENT: Your answer MUST contain this URL: {production_url}",
                                f"",
                                f"Example answer: \"Your site is deployed! Here's the URL: {production_url}\"",
                                f"",
                                f"DO NOT say: \"I need to call a tool\"",
                                f"DO NOT say: \"I've used all tool calls\"",
                                f"JUST give the user the URL above.",
                                f"",
                                f"Status: Deployed and Live (queried at {current_time.strftime('%H:%M:%S')})",
                                f"Site: {single_name}"
                            ]
                        elif single_status == "generating":
                            result_lines = [
                                f"════════════════════════════════════════════════════════════════════",
                                f"🚨 AGENT: NO URL AVAILABLE YET - SITE IS STILL BEING GENERATED",
                                f"════════════════════════════════════════════════════════════════════",
                                f"",
                                f"❌ DO NOT create URL: https://{single_name}.vercel.app",
                                f"❌ DO NOT tell user the site is deployed",
                                f"✅ Tell user: \"Your site is being generated, check back in 1-2 minutes\"",
                                f"",
                                f"════════════════════════════════════════════════════════════════════",
                                f"",
                                f"⚙️ DEPLOYMENT IN PROGRESS (checked at {current_time.strftime('%H:%M:%S')})",
                                f"",
                                f"🔄 Status: AI is generating your website",
                                f"📦 Site: {single_name}",
                                f"",
                                f"⏱️ This typically takes 90-120 seconds.",
                                f"✅ Your site will be automatically deployed to Vercel when generation completes.",
                                f"",
                                f"💡 Check again in 30-60 seconds for the live URL.",
                                f"",
                                f"🚨🚨🚨 CRITICAL AGENT INSTRUCTION 🚨🚨🚨",
                                f"IF USER ASKS AGAIN (even 10 seconds from now):",
                                f"→ DO NOT answer from memory",
                                f"→ DO NOT repeat 'being generated' without checking",
                                f"→ YOU MUST CALL THIS TOOL AGAIN to get updated status",
                                f"→ Status may have changed to 'deployed' by then",
                                f"",
                                f"Details:"
                            ]
                        elif single_status == "deploying":
                            result_lines = [
                                f"════════════════════════════════════════════════════════════════════",
                                f"🚨 AGENT: NO URL AVAILABLE YET - SITE IS BEING DEPLOYED",
                                f"════════════════════════════════════════════════════════════════════",
                                f"",
                                f"❌ DO NOT create URL: https://{single_name}.vercel.app",
                                f"❌ DO NOT tell user the site is deployed",
                                f"✅ Tell user: \"Your site is being deployed to Vercel, check back in 30 seconds\"",
                                f"",
                                f"════════════════════════════════════════════════════════════════════",
                                f"",
                                f"🔄 DEPLOYMENT IN PROGRESS (checked at {current_time.strftime('%H:%M:%S')})",
                                f"",
                                f"📤 Status: Deploying to Vercel",
                                f"📦 Site: {single_name}",
                                f"",
                                f"⏱️ This typically takes 30-60 seconds.",
                                f"✅ Your site will be live soon!",
                                f"",
                                f"💡 Check again in 30 seconds for the live URL.",
                                f"",
                                f"🚨🚨🚨 CRITICAL AGENT INSTRUCTION 🚨🚨🚨",
                                f"IF USER ASKS AGAIN (even 10 seconds from now):",
                                f"→ DO NOT answer from memory",
                                f"→ DO NOT repeat 'being deployed' without checking",
                                f"→ YOU MUST CALL THIS TOOL AGAIN to get updated status",
                                f"→ Status may have changed to 'deployed' by then",
                                f"",
                                f"Details:"
                            ]
                        else:
                            result_lines = [
                                f"🔴 LIVE DATA FROM VERCEL (queried at {current_time.strftime('%H:%M:%S')})",
                                f"",
                                f"Site Status: {single_status}",
                                f"📦 Site: {single_name}",
                                f"",
                                f"Details:"
                            ]
                    else:
                        result_lines = [
                            f"🔴 LIVE DATA FROM VERCEL (queried at {current_time.strftime('%H:%M:%S')})",
                            f"",
                            f"Deployed Sites Matching '{arguments.get('filter', '')}':"
                        ]
                else:
                    # No filter: Show recent 5 deployments (or less if fewer exist)
                    active_deployments = active_deployments[-5:]  # Last 5 deployments
                    if len(active_deployments) == 1:
                        result_lines = [
                            f"🔴 LIVE DATA FROM VERCEL (queried at {current_time.strftime('%H:%M:%S')})",
                            f"",
                            f"Your Recently Deployed Site:"
                        ]
                    else:
                        result_lines = [
                            f"🔴 LIVE DATA FROM VERCEL (queried at {current_time.strftime('%H:%M:%S')})",
                            f"",
                            f"Your {len(active_deployments)} Most Recent Deployments:"
                        ]
                for idx, deployment in enumerate(active_deployments, 1):
                    site_name = deployment.get("site_name", "Unknown")
                    site_type = deployment.get("site_type", "Unknown")
                    deploy_url = deployment.get("deploy_url", "URL not available")
                    deployed_at = deployment.get("deployed_at") or deployment.get("created_at", "Unknown date")
                    deployment_status = deployment.get("deployment_status", "unknown")

                    # CRITICAL DEBUG LOGGING
                    logger.info(f"[LIST TOOL] Formatting deployment #{idx}:")
                    logger.info(f"[LIST TOOL]   Name: {site_name}")
                    logger.info(f"[LIST TOOL]   Status: {deployment_status}")
                    logger.info(f"[LIST TOOL]   URL: {deploy_url}")
                    logger.info(f"[LIST TOOL]   Deployed At: {deployed_at}")

                    print(f"\n[LIST TOOL] Formatting deployment #{idx}:", file=sys.stderr, flush=True)
                    print(f"[LIST TOOL]   Name: {site_name}", file=sys.stderr, flush=True)
                    print(f"[LIST TOOL]   Status: {deployment_status}", file=sys.stderr, flush=True)
                    print(f"[LIST TOOL]   URL: {deploy_url}", file=sys.stderr, flush=True)
                    print(f"[LIST TOOL]   Deployed At: {deployed_at}", file=sys.stderr, flush=True)

                    # Format timestamp
                    try:
                        dt = datetime.fromisoformat(deployed_at)
                        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        time_str = deployed_at

                    site_type_emoji = {
                        "todo": "✅",
                        "portfolio": "💼",
                        "landing": "🚀"
                    }.get(site_type, "🌐")

                    # Status indicator
                    status_emoji = {
                        "deployed": "✅",
                        "deploying": "🔄",
                        "generating": "⚙️"
                    }.get(deployment_status, "❓")

                    result_lines.append(f"{idx}. {site_type_emoji} {site_name} {status_emoji}")
                    result_lines.append(f"   Type: {site_type.capitalize()}")

                    if deployment_status == "deployed":
                        # Clean URL for display (removes team name suffix)
                        display_url = clean_display_url(deploy_url)
                        result_lines.append(f"   🔗 PRODUCTION URL: {display_url}")
                        result_lines.append(f"   Deployed: {time_str}")
                        result_lines.append(f"   ✅ Site is live! Use the URL above (PRODUCTION URL line).")
                    elif deployment_status == "deploying":
                        result_lines.append(f"   Status: Deploying to Vercel... Check back in 60 seconds")
                        result_lines.append(f"   Started: {time_str}")
                    elif deployment_status == "generating":
                        result_lines.append(f"   Status: AI is generating your website... Check back in 30 seconds")
                        result_lines.append(f"   Started: {time_str}")

                    result_lines.append("")

                # Add helpful note for users
                if len(active_deployments) == 1:
                    # Single result - show specific status message
                    if deployment_status == "deployed":
                        result_lines.append("✨ Your site has been deployed to Vercel!")
                        result_lines.append(f"🔗 IMPORTANT: The production URL is: {display_url}")
                        result_lines.append("⚠️  AGENT: When showing this to the user, use ONLY the URL from 'PRODUCTION URL' above.")
                        result_lines.append("⚠️  DO NOT construct a URL from the site_name. Use the actual production URL provided.")
                        result_lines.append("💡 If you get 'Site not found', wait 1 minute and refresh the page.")
                    elif deployment_status == "deploying":
                        result_lines.append("⏳ Your site is being deployed to Vercel. Check back in 60 seconds for the live URL.")
                    elif deployment_status == "generating":
                        result_lines.append("⚙️ AI is generating your website code. Check back in 30 seconds for deployment status.")
                else:
                    # Multiple results - show summary
                    deployed_count = sum(1 for d in active_deployments if d.get("deployment_status") == "deployed")
                    deploying_count = sum(1 for d in active_deployments if d.get("deployment_status") == "deploying")
                    generating_count = sum(1 for d in active_deployments if d.get("deployment_status") == "generating")

                    summary_parts = []
                    if deployed_count > 0:
                        summary_parts.append(f"✅ {deployed_count} live")
                    if deploying_count > 0:
                        summary_parts.append(f"🔄 {deploying_count} deploying")
                    if generating_count > 0:
                        summary_parts.append(f"⚙️ {generating_count} generating")

                    result_lines.append(f"Summary: {' | '.join(summary_parts)}")

                result_text = "\n".join(result_lines)

                # CRITICAL: Add prominent warning for the agent
                agent_warning = f"\n\n{'='*70}\n"
                agent_warning += "⚠️⚠️⚠️ AGENT INSTRUCTIONS ⚠️⚠️⚠️\n"
                agent_warning += f"{'='*70}\n"
                agent_warning += "The URLs shown above are the ONLY correct URLs.\n"
                agent_warning += "DO NOT construct URLs from site_name.\n"
                agent_warning += "DO NOT modify or shorten the URLs.\n"
                agent_warning += "COPY the exact URL from 'PRODUCTION URL' line above.\n"
                agent_warning += f"{'='*70}\n"

                result_text += agent_warning

                # Add debug info to response so user can see what we loaded
                debug_info = f"\n\n---DEBUG INFO (loaded at {datetime.now().isoformat()})---\n"
                debug_info += f"Total deployments in file: {len(deployments)}\n"
                debug_info += f"Active deployments shown: {len(active_deployments)}\n"
                if active_deployments:
                    debug_info += "\nActual data from file:\n"
                    for d in active_deployments[-3:]:
                        debug_info += f"  - {d.get('site_name')}: status='{d.get('deployment_status')}', url='{d.get('deploy_url', 'none')[:60]}...'\n"
                result_text += debug_info

                return [TextContent(type="text", text=result_text)]

            except Exception as e:
                import traceback
                error_msg = f"ERROR in list_deployed_sites:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
                logger.error(error_msg)
                return [TextContent(type="text", text=error_msg)]

        elif name == "update_and_redeploy_site":
            site_name = arguments.get("site_name")
            modification_request = arguments.get("modification_request")

            logger.info(f"Updating site {site_name}: {modification_request}")

            # Find the original deployment
            deployments = load_deployment_history()
            original_deployment = None
            for dep in reversed(deployments):
                if dep.get("site_name") == site_name and dep.get("deployment_status") == "deployed":
                    original_deployment = dep
                    break

            if not original_deployment:
                return [TextContent(type="text", text=f"Error: Site '{site_name}' not found. Use list_deployed_sites to see available sites.")]

            original_prompt = original_deployment.get("prompt", "website")

            try:
                # Generate updated code with AI
                logger.info(f"Generating updated code for {site_name}...")
                updated_code = await update_website_with_ai(site_name, modification_request, original_prompt)

                # Create new project directory with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_site_name = f"{site_name}-updated"
                project_dir = SITES_DIR / f"{new_site_name}_{timestamp}"
                project_dir.mkdir(parents=True, exist_ok=True)

                # Write updated files
                (project_dir / "index.html").write_text(updated_code["html"])
                (project_dir / "style.css").write_text(updated_code["css"])
                (project_dir / "script.js").write_text(updated_code["js"])

                logger.info(f"Updated website files generated at: {project_dir}")

                # Save to history
                new_deployment_record = {
                    "site_name": new_site_name,
                    "site_type": "custom",
                    "prompt": f"{original_prompt} (Updated: {modification_request})",
                    "deploy_url": "deploying",
                    "project_path": str(project_dir),
                    "deployed_at": datetime.now().isoformat(),
                    "deployment_status": "deploying"
                }
                deployments.append(new_deployment_record)
                save_deployment_history(deployments)

                # Start background deployment
                thread = threading.Thread(
                    target=deploy_in_background_sync,
                    args=(str(project_dir), new_site_name, "custom", f"{original_prompt} (Updated)"),
                    daemon=True
                )
                thread.start()

                result_text = f"""Website Updated - Deploying Now!

Original Site: {site_name}
Updated Site: {new_site_name}
Modifications: {modification_request}

Your updated website is being deployed to Vercel.
This typically takes 60-90 seconds.

Check deployment status with 'list_deployed_sites' tool to get your live URL once ready."""

                return [TextContent(type="text", text=result_text)]

            except Exception as e:
                logger.error(f"Update failed: {e}", exc_info=True)
                return [TextContent(type="text", text=f"Website Update Failed\n\nError: {str(e)}")]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        import sys
        import traceback

        # Log to multiple places to ensure visibility
        error_msg = f"Error executing {name}: {str(e)}"
        error_traceback = traceback.format_exc()

        # 1. Standard logger
        logger.error(error_msg)
        logger.error(error_traceback)

        # 2. Write to stderr directly
        sys.stderr.write(f"\n{'='*80}\n")
        sys.stderr.write(f"MCP TOOL ERROR: {error_msg}\n")
        sys.stderr.write(f"{error_traceback}\n")
        sys.stderr.write(f"{'='*80}\n")
        sys.stderr.flush()

        # 3. Write to debug file
        try:
            with open("/tmp/vercel_mcp_errors.log", "a") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"Time: {datetime.now().isoformat()}\n")
                f.write(f"Tool: {name}\n")
                f.write(f"Arguments: {arguments}\n")
                f.write(f"Error: {error_msg}\n")
                f.write(f"Traceback:\n{error_traceback}\n")
                f.write(f"{'='*80}\n")
        except:
            pass

        error_result = {
            "status": "error",
            "message": str(e),
            "tool": name,
            "traceback": error_traceback
        }
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


async def generate_website(site_type: str, site_name: str, custom_content: Dict, prompt: str = "") -> Path:
    """Generate website files based on type"""
    # Create project directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_dir = SITES_DIR / f"{site_name}_{timestamp}"
    project_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Creating project in: {project_dir}")

    # Generate files based on site type
    if site_type == "todo":
        await generate_todo_app(project_dir, site_name, custom_content)
    elif site_type == "portfolio":
        await generate_portfolio(project_dir, site_name, custom_content)
    elif site_type == "landing":
        await generate_landing_page(project_dir, site_name, custom_content)
    elif site_type == "custom":
        # Use AI to generate custom website
        if not prompt:
            raise ValueError("Prompt is required for custom website generation")
        logger.info(f"Generating custom website with AI: {prompt}")
        generated_code = await generate_custom_website_with_ai(prompt, site_name)

        # Write the generated files
        (project_dir / "index.html").write_text(generated_code["html"])
        (project_dir / "style.css").write_text(generated_code["css"])
        (project_dir / "script.js").write_text(generated_code["js"])

        logger.info("Custom website generated successfully with AI")
    else:
        raise ValueError(f"Unknown site type: {site_type}")

    logger.info(f"Successfully generated {site_type} website files")
    return project_dir


async def generate_todo_app(project_dir: Path, site_name: str, custom_content: Dict):
    """Generate a todo app with localStorage persistence"""
    title = custom_content.get("title", "My Todo App")

    # HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <h1>✅ {title}</h1>
        <div class="input-section">
            <input type="text" id="todoInput" placeholder="What needs to be done?" />
            <button id="addBtn">Add Task</button>
        </div>
        <div class="filters">
            <button class="filter-btn active" data-filter="all">All</button>
            <button class="filter-btn" data-filter="active">Active</button>
            <button class="filter-btn" data-filter="completed">Completed</button>
        </div>
        <ul id="todoList"></ul>
        <div class="stats">
            <span id="itemsLeft">0 items left</span>
            <button id="clearCompleted">Clear Completed</button>
        </div>
    </div>
    <script src="script.js"></script>
</body>
</html>"""

    # CSS
    css_content = """* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 20px;
}

.container {
    background: white;
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    padding: 40px;
    max-width: 600px;
    width: 100%;
}

h1 {
    color: #667eea;
    text-align: center;
    margin-bottom: 30px;
    font-size: 2.5em;
}

.input-section {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
}

#todoInput {
    flex: 1;
    padding: 15px;
    border: 2px solid #e0e0e0;
    border-radius: 10px;
    font-size: 16px;
    transition: border-color 0.3s;
}

#todoInput:focus {
    outline: none;
    border-color: #667eea;
}

button {
    padding: 15px 30px;
    background: #667eea;
    color: white;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 16px;
    font-weight: 600;
    transition: background 0.3s, transform 0.1s;
}

button:hover {
    background: #764ba2;
}

button:active {
    transform: scale(0.98);
}

.filters {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    justify-content: center;
}

.filter-btn {
    padding: 8px 20px;
    background: #f0f0f0;
    color: #666;
    font-size: 14px;
}

.filter-btn.active {
    background: #667eea;
    color: white;
}

#todoList {
    list-style: none;
    margin-bottom: 20px;
}

.todo-item {
    display: flex;
    align-items: center;
    padding: 15px;
    background: #f9f9f9;
    border-radius: 10px;
    margin-bottom: 10px;
    transition: background 0.3s;
}

.todo-item:hover {
    background: #f0f0f0;
}

.todo-item.completed .todo-text {
    text-decoration: line-through;
    color: #999;
}

.todo-checkbox {
    width: 24px;
    height: 24px;
    margin-right: 15px;
    cursor: pointer;
}

.todo-text {
    flex: 1;
    font-size: 16px;
    color: #333;
}

.delete-btn {
    padding: 8px 15px;
    background: #ff6b6b;
    font-size: 14px;
}

.delete-btn:hover {
    background: #ff5252;
}

.stats {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 20px;
    border-top: 2px solid #e0e0e0;
    color: #666;
}

#clearCompleted {
    padding: 10px 20px;
    background: #ff6b6b;
    font-size: 14px;
}

#clearCompleted:hover {
    background: #ff5252;
}

@media (max-width: 600px) {
    .container {
        padding: 20px;
    }

    h1 {
        font-size: 2em;
    }

    .input-section {
        flex-direction: column;
    }

    .stats {
        flex-direction: column;
        gap: 10px;
    }
}"""

    # JavaScript
    js_content = """// Todo App with localStorage persistence
class TodoApp {
    constructor() {
        this.todos = this.loadTodos();
        this.currentFilter = 'all';
        this.init();
    }

    init() {
        // DOM elements
        this.todoInput = document.getElementById('todoInput');
        this.addBtn = document.getElementById('addBtn');
        this.todoList = document.getElementById('todoList');
        this.itemsLeft = document.getElementById('itemsLeft');
        this.clearCompleted = document.getElementById('clearCompleted');
        this.filterBtns = document.querySelectorAll('.filter-btn');

        // Event listeners
        this.addBtn.addEventListener('click', () => this.addTodo());
        this.todoInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.addTodo();
        });
        this.clearCompleted.addEventListener('click', () => this.clearCompletedTodos());

        this.filterBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.currentFilter = e.target.dataset.filter;
                this.updateFilterButtons();
                this.render();
            });
        });

        this.render();
    }

    loadTodos() {
        const stored = localStorage.getItem('todos');
        return stored ? JSON.parse(stored) : [];
    }

    saveTodos() {
        localStorage.setItem('todos', JSON.stringify(this.todos));
    }

    addTodo() {
        const text = this.todoInput.value.trim();
        if (!text) return;

        const todo = {
            id: Date.now(),
            text: text,
            completed: false,
            createdAt: new Date().toISOString()
        };

        this.todos.push(todo);
        this.saveTodos();
        this.todoInput.value = '';
        this.render();
    }

    deleteTodo(id) {
        this.todos = this.todos.filter(todo => todo.id !== id);
        this.saveTodos();
        this.render();
    }

    toggleTodo(id) {
        const todo = this.todos.find(t => t.id === id);
        if (todo) {
            todo.completed = !todo.completed;
            this.saveTodos();
            this.render();
        }
    }

    clearCompletedTodos() {
        this.todos = this.todos.filter(todo => !todo.completed);
        this.saveTodos();
        this.render();
    }

    getFilteredTodos() {
        switch(this.currentFilter) {
            case 'active':
                return this.todos.filter(t => !t.completed);
            case 'completed':
                return this.todos.filter(t => t.completed);
            default:
                return this.todos;
        }
    }

    updateFilterButtons() {
        this.filterBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === this.currentFilter);
        });
    }

    render() {
        const filteredTodos = this.getFilteredTodos();

        // Render todos
        this.todoList.innerHTML = filteredTodos.map(todo => `
            <li class="todo-item ${todo.completed ? 'completed' : ''}">
                <input
                    type="checkbox"
                    class="todo-checkbox"
                    ${todo.completed ? 'checked' : ''}
                    onchange="app.toggleTodo(${todo.id})"
                />
                <span class="todo-text">${this.escapeHtml(todo.text)}</span>
                <button class="delete-btn" onclick="app.deleteTodo(${todo.id})">Delete</button>
            </li>
        `).join('');

        // Update stats
        const activeCount = this.todos.filter(t => !t.completed).length;
        this.itemsLeft.textContent = `${activeCount} item${activeCount !== 1 ? 's' : ''} left`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize app
const app = new TodoApp();"""

    # Write files
    (project_dir / "index.html").write_text(html_content)
    (project_dir / "style.css").write_text(css_content)
    (project_dir / "script.js").write_text(js_content)


async def generate_portfolio(project_dir: Path, site_name: str, custom_content: Dict):
    """Generate a portfolio website"""
    name = custom_content.get("title", "John Doe")
    tagline = custom_content.get("description", "Full Stack Developer")

    # HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} - Portfolio</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <nav class="navbar">
        <div class="nav-container">
            <div class="logo">{name}</div>
            <ul class="nav-menu">
                <li><a href="#home">Home</a></li>
                <li><a href="#about">About</a></li>
                <li><a href="#projects">Projects</a></li>
                <li><a href="#contact">Contact</a></li>
            </ul>
            <div class="hamburger">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    </nav>

    <section id="home" class="hero">
        <div class="hero-content">
            <h1>Hi, I'm {name}</h1>
            <p class="tagline">{tagline}</p>
            <a href="#contact" class="cta-button">Get In Touch</a>
        </div>
    </section>

    <section id="about" class="about">
        <div class="container">
            <h2>About Me</h2>
            <div class="about-content">
                <div class="about-text">
                    <p>I'm a passionate developer with expertise in building modern web applications. I love creating elegant solutions to complex problems and turning ideas into reality.</p>
                    <p>With a strong foundation in both frontend and backend technologies, I strive to deliver high-quality, scalable applications that make a difference.</p>
                </div>
                <div class="skills">
                    <h3>Skills</h3>
                    <div class="skill-tags">
                        <span class="skill-tag">JavaScript</span>
                        <span class="skill-tag">React</span>
                        <span class="skill-tag">Node.js</span>
                        <span class="skill-tag">Python</span>
                        <span class="skill-tag">HTML/CSS</span>
                        <span class="skill-tag">Git</span>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section id="projects" class="projects">
        <div class="container">
            <h2>My Projects</h2>
            <div class="projects-grid">
                <div class="project-card">
                    <h3>E-Commerce Platform</h3>
                    <p>A full-stack e-commerce solution with payment integration and real-time inventory management.</p>
                    <div class="project-tags">
                        <span>React</span>
                        <span>Node.js</span>
                        <span>MongoDB</span>
                    </div>
                </div>
                <div class="project-card">
                    <h3>Task Management App</h3>
                    <p>A collaborative task management application with real-time updates and team features.</p>
                    <div class="project-tags">
                        <span>Vue.js</span>
                        <span>Firebase</span>
                        <span>TypeScript</span>
                    </div>
                </div>
                <div class="project-card">
                    <h3>Weather Dashboard</h3>
                    <p>An interactive weather dashboard with forecasts, maps, and historical data visualization.</p>
                    <div class="project-tags">
                        <span>React</span>
                        <span>API Integration</span>
                        <span>Charts.js</span>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section id="contact" class="contact">
        <div class="container">
            <h2>Get In Touch</h2>
            <div class="contact-content">
                <p>I'm always interested in hearing about new projects and opportunities.</p>
                <div class="contact-info">
                    <a href="mailto:contact@example.com" class="contact-link">📧 contact@example.com</a>
                    <a href="https://github.com" class="contact-link">💻 GitHub</a>
                    <a href="https://linkedin.com" class="contact-link">💼 LinkedIn</a>
                </div>
            </div>
        </div>
    </section>

    <footer>
        <p>&copy; 2024 {name}. All rights reserved.</p>
    </footer>

    <script src="script.js"></script>
</body>
</html>"""

    # CSS
    css_content = """* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
    --primary-color: #667eea;
    --secondary-color: #764ba2;
    --text-color: #333;
    --bg-color: #f5f5f5;
    --white: #ffffff;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
}

html {
    scroll-behavior: smooth;
}

.navbar {
    background: var(--white);
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    position: fixed;
    top: 0;
    width: 100%;
    z-index: 1000;
}

.nav-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.logo {
    font-size: 1.5rem;
    font-weight: bold;
    color: var(--primary-color);
}

.nav-menu {
    display: flex;
    list-style: none;
    gap: 2rem;
}

.nav-menu a {
    text-decoration: none;
    color: var(--text-color);
    font-weight: 500;
    transition: color 0.3s;
}

.nav-menu a:hover {
    color: var(--primary-color);
}

.hamburger {
    display: none;
    flex-direction: column;
    cursor: pointer;
}

.hamburger span {
    width: 25px;
    height: 3px;
    background: var(--text-color);
    margin: 3px 0;
    transition: 0.3s;
}

.hero {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    color: var(--white);
    padding: 2rem;
}

.hero-content h1 {
    font-size: 3.5rem;
    margin-bottom: 1rem;
    animation: fadeInUp 1s ease;
}

.tagline {
    font-size: 1.5rem;
    margin-bottom: 2rem;
    animation: fadeInUp 1s ease 0.2s backwards;
}

.cta-button {
    display: inline-block;
    padding: 1rem 2rem;
    background: var(--white);
    color: var(--primary-color);
    text-decoration: none;
    border-radius: 50px;
    font-weight: bold;
    transition: transform 0.3s, box-shadow 0.3s;
    animation: fadeInUp 1s ease 0.4s backwards;
}

.cta-button:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 20px rgba(0,0,0,0.2);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 4rem 2rem;
}

section {
    padding: 4rem 0;
}

h2 {
    font-size: 2.5rem;
    text-align: center;
    margin-bottom: 3rem;
    color: var(--primary-color);
}

.about {
    background: var(--white);
}

.about-content {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 3rem;
    align-items: start;
}

.about-text p {
    margin-bottom: 1rem;
    font-size: 1.1rem;
}

.skills h3 {
    margin-bottom: 1rem;
    color: var(--secondary-color);
}

.skill-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.skill-tag {
    padding: 0.5rem 1rem;
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    color: var(--white);
    border-radius: 20px;
    font-size: 0.9rem;
}

.projects {
    background: var(--bg-color);
}

.projects-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
}

.project-card {
    background: var(--white);
    padding: 2rem;
    border-radius: 10px;
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    transition: transform 0.3s, box-shadow 0.3s;
}

.project-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 10px 25px rgba(0,0,0,0.15);
}

.project-card h3 {
    color: var(--primary-color);
    margin-bottom: 1rem;
}

.project-tags {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
}

.project-tags span {
    padding: 0.25rem 0.75rem;
    background: var(--bg-color);
    border-radius: 15px;
    font-size: 0.85rem;
    color: var(--secondary-color);
}

.contact {
    background: var(--white);
}

.contact-content {
    text-align: center;
}

.contact-content p {
    font-size: 1.2rem;
    margin-bottom: 2rem;
}

.contact-info {
    display: flex;
    justify-content: center;
    gap: 2rem;
    flex-wrap: wrap;
}

.contact-link {
    padding: 1rem 2rem;
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    color: var(--white);
    text-decoration: none;
    border-radius: 10px;
    transition: transform 0.3s;
    font-weight: 500;
}

.contact-link:hover {
    transform: scale(1.05);
}

footer {
    background: var(--text-color);
    color: var(--white);
    text-align: center;
    padding: 2rem;
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@media (max-width: 768px) {
    .hamburger {
        display: flex;
    }

    .nav-menu {
        position: fixed;
        left: -100%;
        top: 70px;
        flex-direction: column;
        background-color: var(--white);
        width: 100%;
        text-align: center;
        transition: 0.3s;
        box-shadow: 0 10px 27px rgba(0,0,0,0.05);
        padding: 2rem 0;
    }

    .nav-menu.active {
        left: 0;
    }

    .hero-content h1 {
        font-size: 2.5rem;
    }

    .tagline {
        font-size: 1.2rem;
    }

    .about-content {
        grid-template-columns: 1fr;
    }

    .projects-grid {
        grid-template-columns: 1fr;
    }

    .contact-info {
        flex-direction: column;
    }
}"""

    # JavaScript
    js_content = """// Mobile menu toggle
const hamburger = document.querySelector('.hamburger');
const navMenu = document.querySelector('.nav-menu');

hamburger.addEventListener('click', () => {
    navMenu.classList.toggle('active');
});

// Close mobile menu when link is clicked
document.querySelectorAll('.nav-menu a').forEach(link => {
    link.addEventListener('click', () => {
        navMenu.classList.remove('active');
    });
});

// Smooth scroll for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Add active class to navbar on scroll
const navbar = document.querySelector('.navbar');
window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
        navbar.style.boxShadow = '0 4px 20px rgba(0,0,0,0.1)';
    } else {
        navbar.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
    }
});"""

    # Write files
    (project_dir / "index.html").write_text(html_content)
    (project_dir / "style.css").write_text(css_content)
    (project_dir / "script.js").write_text(js_content)


async def generate_landing_page(project_dir: Path, site_name: str, custom_content: Dict):
    """Generate a landing page"""
    product_name = custom_content.get("title", "Amazing Product")
    tagline = custom_content.get("description", "The best solution for your needs")

    # HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{product_name} - {tagline}</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <nav class="navbar">
        <div class="nav-container">
            <div class="logo">{product_name}</div>
            <ul class="nav-menu">
                <li><a href="#features">Features</a></li>
                <li><a href="#benefits">Benefits</a></li>
                <li><a href="#cta">Get Started</a></li>
            </ul>
        </div>
    </nav>

    <section class="hero">
        <div class="hero-content">
            <h1>{product_name}</h1>
            <p class="hero-subtitle">{tagline}</p>
            <p class="hero-description">Transform the way you work with our innovative solution. Start your journey today.</p>
            <a href="#cta" class="cta-button">Get Started Free</a>
        </div>
    </section>

    <section id="features" class="features">
        <div class="container">
            <h2>Powerful Features</h2>
            <div class="features-grid">
                <div class="feature-card">
                    <div class="feature-icon">⚡</div>
                    <h3>Lightning Fast</h3>
                    <p>Experience blazing-fast performance that keeps you ahead of the competition.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🔒</div>
                    <h3>Secure & Private</h3>
                    <p>Your data is protected with enterprise-grade security and encryption.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🎨</div>
                    <h3>Beautiful Design</h3>
                    <p>Intuitive interface that makes complex tasks simple and enjoyable.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🚀</div>
                    <h3>Easy Integration</h3>
                    <p>Connect with your favorite tools and platforms in minutes.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">📊</div>
                    <h3>Analytics Dashboard</h3>
                    <p>Get insights with powerful analytics and reporting tools.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🌐</div>
                    <h3>Global Scale</h3>
                    <p>Built to scale from small teams to enterprise organizations.</p>
                </div>
            </div>
        </div>
    </section>

    <section id="benefits" class="benefits">
        <div class="container">
            <h2>Why Choose Us?</h2>
            <div class="benefits-content">
                <div class="benefit-item">
                    <div class="benefit-number">01</div>
                    <h3>Save Time</h3>
                    <p>Automate repetitive tasks and focus on what matters most. Increase productivity by up to 10x.</p>
                </div>
                <div class="benefit-item">
                    <div class="benefit-number">02</div>
                    <h3>Reduce Costs</h3>
                    <p>Cut operational costs with efficient workflows and smart automation. Save thousands every month.</p>
                </div>
                <div class="benefit-item">
                    <div class="benefit-number">03</div>
                    <h3>Scale Effortlessly</h3>
                    <p>Grow your business without worrying about infrastructure. We handle the complexity.</p>
                </div>
            </div>
        </div>
    </section>

    <section id="cta" class="cta-section">
        <div class="container">
            <div class="cta-content">
                <h2>Ready to Get Started?</h2>
                <p>Join thousands of satisfied customers already using {product_name}</p>
                <form class="cta-form" onsubmit="handleSubmit(event)">
                    <input type="email" placeholder="Enter your email" required />
                    <button type="submit">Start Free Trial</button>
                </form>
                <p class="cta-note">No credit card required • 14-day free trial • Cancel anytime</p>
            </div>
        </div>
    </section>

    <footer>
        <div class="footer-content">
            <div class="footer-section">
                <h4>{product_name}</h4>
                <p>The best solution for your needs</p>
            </div>
            <div class="footer-section">
                <h4>Product</h4>
                <a href="#features">Features</a>
                <a href="#benefits">Benefits</a>
                <a href="#cta">Pricing</a>
            </div>
            <div class="footer-section">
                <h4>Company</h4>
                <a href="#">About</a>
                <a href="#">Blog</a>
                <a href="#">Contact</a>
            </div>
            <div class="footer-section">
                <h4>Legal</h4>
                <a href="#">Privacy</a>
                <a href="#">Terms</a>
                <a href="#">Security</a>
            </div>
        </div>
        <div class="footer-bottom">
            <p>&copy; 2024 {product_name}. All rights reserved.</p>
        </div>
    </footer>

    <script src="script.js"></script>
</body>
</html>"""

    # CSS
    css_content = """* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
    --primary-color: #667eea;
    --secondary-color: #764ba2;
    --accent-color: #f093fb;
    --text-color: #333;
    --bg-color: #f5f5f5;
    --white: #ffffff;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
}

html {
    scroll-behavior: smooth;
}

.navbar {
    background: var(--white);
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    position: fixed;
    top: 0;
    width: 100%;
    z-index: 1000;
}

.nav-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.logo {
    font-size: 1.5rem;
    font-weight: bold;
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.nav-menu {
    display: flex;
    list-style: none;
    gap: 2rem;
}

.nav-menu a {
    text-decoration: none;
    color: var(--text-color);
    font-weight: 500;
    transition: color 0.3s;
}

.nav-menu a:hover {
    color: var(--primary-color);
}

.hero {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    color: var(--white);
    padding: 2rem;
    margin-top: 70px;
}

.hero-content {
    max-width: 800px;
}

.hero-content h1 {
    font-size: 4rem;
    margin-bottom: 1rem;
    animation: fadeInUp 0.8s ease;
}

.hero-subtitle {
    font-size: 1.8rem;
    margin-bottom: 1rem;
    animation: fadeInUp 0.8s ease 0.2s backwards;
}

.hero-description {
    font-size: 1.2rem;
    margin-bottom: 2rem;
    opacity: 0.9;
    animation: fadeInUp 0.8s ease 0.4s backwards;
}

.cta-button {
    display: inline-block;
    padding: 1.2rem 3rem;
    background: var(--white);
    color: var(--primary-color);
    text-decoration: none;
    border-radius: 50px;
    font-weight: bold;
    font-size: 1.1rem;
    transition: transform 0.3s, box-shadow 0.3s;
    animation: fadeInUp 0.8s ease 0.6s backwards;
}

.cta-button:hover {
    transform: translateY(-3px);
    box-shadow: 0 15px 30px rgba(0,0,0,0.3);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 5rem 2rem;
}

h2 {
    font-size: 3rem;
    text-align: center;
    margin-bottom: 4rem;
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.features {
    background: var(--white);
}

.features-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
}

.feature-card {
    background: var(--bg-color);
    padding: 2.5rem;
    border-radius: 15px;
    text-align: center;
    transition: transform 0.3s, box-shadow 0.3s;
}

.feature-card:hover {
    transform: translateY(-10px);
    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
}

.feature-icon {
    font-size: 4rem;
    margin-bottom: 1rem;
}

.feature-card h3 {
    color: var(--primary-color);
    margin-bottom: 1rem;
    font-size: 1.5rem;
}

.benefits {
    background: var(--bg-color);
}

.benefits-content {
    display: grid;
    gap: 3rem;
}

.benefit-item {
    display: flex;
    gap: 2rem;
    align-items: start;
}

.benefit-number {
    font-size: 3rem;
    font-weight: bold;
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    min-width: 80px;
}

.benefit-item h3 {
    color: var(--primary-color);
    margin-bottom: 0.5rem;
    font-size: 1.8rem;
}

.benefit-item p {
    font-size: 1.1rem;
    color: #666;
}

.cta-section {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
    color: var(--white);
}

.cta-content {
    text-align: center;
    max-width: 700px;
    margin: 0 auto;
}

.cta-content h2 {
    color: var(--white);
    -webkit-text-fill-color: var(--white);
    margin-bottom: 1rem;
}

.cta-content > p {
    font-size: 1.3rem;
    margin-bottom: 2rem;
}

.cta-form {
    display: flex;
    gap: 1rem;
    max-width: 500px;
    margin: 0 auto 1rem;
}

.cta-form input {
    flex: 1;
    padding: 1rem 1.5rem;
    border: none;
    border-radius: 50px;
    font-size: 1rem;
}

.cta-form button {
    padding: 1rem 2rem;
    background: var(--text-color);
    color: var(--white);
    border: none;
    border-radius: 50px;
    font-weight: bold;
    cursor: pointer;
    transition: background 0.3s, transform 0.3s;
}

.cta-form button:hover {
    background: #222;
    transform: scale(1.05);
}

.cta-note {
    font-size: 0.9rem;
    opacity: 0.9;
}

footer {
    background: #222;
    color: var(--white);
    padding: 3rem 2rem 1rem;
}

.footer-content {
    max-width: 1200px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 2rem;
    margin-bottom: 2rem;
}

.footer-section h4 {
    margin-bottom: 1rem;
    color: var(--accent-color);
}

.footer-section a {
    display: block;
    color: #ccc;
    text-decoration: none;
    margin-bottom: 0.5rem;
    transition: color 0.3s;
}

.footer-section a:hover {
    color: var(--white);
}

.footer-bottom {
    text-align: center;
    padding-top: 2rem;
    border-top: 1px solid #444;
    color: #999;
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@media (max-width: 768px) {
    .hero-content h1 {
        font-size: 2.5rem;
    }

    .hero-subtitle {
        font-size: 1.3rem;
    }

    h2 {
        font-size: 2rem;
    }

    .features-grid {
        grid-template-columns: 1fr;
    }

    .benefit-item {
        flex-direction: column;
        text-align: center;
    }

    .cta-form {
        flex-direction: column;
    }

    .footer-content {
        grid-template-columns: 1fr;
        text-align: center;
    }
}"""

    # JavaScript
    js_content = """// Handle form submission
function handleSubmit(event) {
    event.preventDefault();
    const email = event.target.querySelector('input[type="email"]').value;
    alert(`Thank you! We'll send a confirmation to ${email}`);
    event.target.reset();
}

// Smooth scroll for navigation
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Navbar shadow on scroll
const navbar = document.querySelector('.navbar');
let lastScroll = 0;

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;

    if (currentScroll > 50) {
        navbar.style.boxShadow = '0 4px 20px rgba(0,0,0,0.15)';
    } else {
        navbar.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
    }

    lastScroll = currentScroll;
});

// Animate elements on scroll
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.animation = 'fadeInUp 0.8s ease forwards';
        }
    });
}, observerOptions);

// Observe feature cards and benefit items
document.querySelectorAll('.feature-card, .benefit-item').forEach(el => {
    el.style.opacity = '0';
    observer.observe(el);
});"""

    # Write files
    (project_dir / "index.html").write_text(html_content)
    (project_dir / "style.css").write_text(css_content)
    (project_dir / "script.js").write_text(js_content)


async def deploy_to_vercel_internal(project_path: str, site_name: str, thread_log_file: Path = None) -> str:
    """Deploy to Vercel using API"""
    project_dir = Path(project_path)

    # Helper to log to both logger and thread file
    def log_both(msg):
        logger.info(msg)
        if thread_log_file:
            try:
                with open(thread_log_file, 'a') as f:
                    f.write(f"{datetime.now().isoformat()} - [DEPLOY_VERCEL] {msg}\n")
            except:
                pass

    if not project_dir.exists():
        raise FileNotFoundError(f"Project directory not found: {project_path}")

    # Check for auth token
    vercel_token = os.environ.get("VERCEL_TOKEN")
    if not vercel_token:
        raise RuntimeError("VERCEL_TOKEN environment variable is required")

    logger.info(f"Deploying {project_path} to Vercel via API...")

    try:
        # Step 1: Read all files and prepare them for Vercel
        files = []
        for file_path in project_dir.rglob('*'):
            if file_path.is_file():
                relative_path = str(file_path.relative_to(project_dir))
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                files.append({
                    "file": relative_path,
                    "data": content
                })
                logger.info(f"Added file: {relative_path} ({len(content)} chars)")

        logger.info(f"Prepared {len(files)} files for deployment")

        # Step 2: Create deployment payload
        deployment_payload = {
            "name": site_name,
            "files": files,
            "projectSettings": {
                "framework": None  # Static site, no framework
            },
            "target": "production"
        }

        # Step 3: Deploy to Vercel
        headers = {
            "Authorization": f"Bearer {vercel_token}",
            "Content-Type": "application/json"
        }

        logger.info("Sending deployment request to Vercel...")
        deploy_response = requests.post(
            "https://api.vercel.com/v13/deployments",
            headers=headers,
            json=deployment_payload,
            timeout=120
        )

        if deploy_response.status_code not in [200, 201]:
            error_text = deploy_response.text
            logger.error(f"Vercel deployment failed: {error_text}")

            # Parse error message
            try:
                error_json = deploy_response.json()
                error_msg = error_json.get("error", {}).get("message", error_text)
            except:
                error_msg = error_text

            raise RuntimeError(f"Failed to deploy to Vercel: {error_msg}")

        deploy_data = deploy_response.json()

        # Debug: Log the full response to understand what Vercel returns
        log_both(f"Vercel API response keys: {list(deploy_data.keys())}")
        log_both(f"Vercel project name from API: {deploy_data.get('name')}")
        log_both(f"Vercel projectId from API: {deploy_data.get('projectId')}")

        # Vercel returns the deployment URL (unique with hash)
        deployment_url = deploy_data.get("url")
        deployment_id = deploy_data.get("id")

        # Look for production/alias URLs in multiple fields
        alias_urls = deploy_data.get("alias", [])
        aliases_field = deploy_data.get("aliases", [])  # Some versions use "aliases"

        log_both(f"Deployment URL: {deployment_url}")
        log_both(f"Alias URLs: {alias_urls}")
        log_both(f"Aliases field: {aliases_field}")

        # IMPORTANT: Use the actual URL from Vercel's response
        # Priority: alias > deployment URL (deployment URL includes hash, alias is clean)
        if alias_urls and len(alias_urls) > 0:
            # Use the alias from Vercel (clean production URL)
            deploy_url = alias_urls[0]
            if not deploy_url.startswith("http"):
                deploy_url = f"https://{deploy_url}"
            logger.info(f"✓ Using Vercel alias URL: {deploy_url}")
        elif aliases_field and len(aliases_field) > 0:
            # Try alternate field name
            deploy_url = aliases_field[0]
            if not deploy_url.startswith("http"):
                deploy_url = f"https://{deploy_url}"
            logger.info(f"✓ Using Vercel aliases field URL: {deploy_url}")
        elif deployment_url:
            # Fallback: Use deployment-specific URL (with hash but guaranteed to work)
            deploy_url = deployment_url
            if not deploy_url.startswith("http"):
                deploy_url = f"https://{deploy_url}"
            logger.info(f"⚠ Using deployment-specific URL (has hash): {deploy_url}")
        else:
            # Last resort fallback (shouldn't happen)
            deploy_url = f"https://{site_name}.vercel.app"
            logger.info(f"⚠ WARNING: Using constructed URL (may be incorrect): {deploy_url}")

        logger.info(f"Successfully deployed to Vercel!")
        logger.info(f"Deployment ID: {deployment_id}")
        logger.info(f"Deployment URL from API: {deploy_url}")

        # IMPORTANT: Get the ACTUAL production domain from Vercel
        # Vercel assigns a shorter production domain shown in the dashboard under "Domains"
        try:
            log_both(f"Fetching actual production domain from Vercel...")

            # Get projectId from deployment response (more reliable than project name)
            project_id = deploy_data.get("projectId")
            project_name = deploy_data.get("name")

            log_both(f"Project ID: {project_id}, Project Name: {project_name}")

            if project_id:
                # Query the DOMAINS endpoint - this is where Vercel stores the production domain
                domains_response = requests.get(
                    f"https://api.vercel.com/v9/projects/{project_id}/domains",
                    headers=headers,
                    timeout=30
                )

                log_both(f"Domains API response status: {domains_response.status_code}")

                if domains_response.status_code == 200:
                    domains_data = domains_response.json()
                    domains_list = domains_data.get("domains", [])

                    log_both(f"Found {len(domains_list)} domain(s) for this project")

                    # Log all domains to see what we got
                    for i, domain in enumerate(domains_list):
                        domain_name = domain.get("name")
                        log_both(f"  Domain {i+1}: {domain_name}")

                    # Use the first domain (usually the production domain)
                    if domains_list and len(domains_list) > 0:
                        production_domain = domains_list[0].get("name")
                        if production_domain:
                            deploy_url = f"https://{production_domain}"
                            log_both(f"✓ SUCCESS! Using production domain from Vercel: {deploy_url}")
                        else:
                            log_both(f"⚠ Domain found but no 'name' field, keeping deployment URL")
                    else:
                        log_both(f"⚠ No domains found in response, keeping deployment URL")
                else:
                    log_both(f"⚠ Domains API returned status {domains_response.status_code}")
                    # Try to get error details
                    try:
                        error_data = domains_response.json()
                        log_both(f"   Error: {error_data}")
                    except:
                        pass
            else:
                log_both(f"⚠ No projectId in deployment response, cannot query domains")

        except Exception as e:
            log_both(f"⚠ Exception while fetching domains: {e}")
            import traceback
            log_both(f"   Traceback: {traceback.format_exc()}")

        log_both(f"Final production URL being returned: {deploy_url}")
        return deploy_url

    except requests.exceptions.RequestException as e:
        logger.error(f"Vercel API request failed: {str(e)}")
        raise RuntimeError(f"Vercel API error: {str(e)}")
    except Exception as e:
        logger.error(f"Deployment error: {str(e)}", exc_info=True)
        raise RuntimeError(f"Deployment error: {str(e)}")


async def main():
    """Run the MCP server"""
    import sys

    # CRITICAL: Startup banner to verify code version
    startup_msg = f"""
{'='*80}
VERCEL DEPLOY MCP SERVER - DEBUG VERSION
Started at: {datetime.now().isoformat()}
Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}
Gemini Available: {GEMINI_AVAILABLE}
Anthropic Available: {ANTHROPIC_AVAILABLE}
History File: {DEPLOYMENT_HISTORY}
Debug Logging: ENABLED
{'='*80}
"""
    logger.info(startup_msg)
    sys.stderr.write(startup_msg + "\n")
    sys.stderr.flush()

    # Also write to file
    try:
        with open("/tmp/vercel_mcp_startup.log", "w") as f:
            f.write(startup_msg)
    except:
        pass

    logger.info("Starting Vercel Deploy MCP Server")
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
