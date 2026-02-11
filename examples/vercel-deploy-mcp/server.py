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
import threading
import zipfile
import requests
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vercel-deploy-mcp")

# Initialize MCP server
app = Server("vercel-deploy")

# Base directory for generated sites
SITES_DIR = Path.home() / ".vercel-mcp" / "sites"
SITES_DIR.mkdir(parents=True, exist_ok=True)

# Deployment history file
DEPLOYMENT_HISTORY = SITES_DIR / "deployment_history.json"


def load_deployment_history():
    """Load deployment history from file"""
    if DEPLOYMENT_HISTORY.exists():
        try:
            # Clear any OS-level file caching by opening with direct I/O intent
            import os
            # First, get fresh file stats to ensure no stale metadata
            os.stat(DEPLOYMENT_HISTORY)

            with open(DEPLOYMENT_HISTORY, 'r') as f:
                data = json.load(f)
                logger.debug(f"Loaded deployment history: {len(data)} entries")
                return data
        except Exception as e:
            logger.error(f"Error loading deployment history: {e}")
            return []
    return []


def save_deployment_history(deployments):
    """Save deployment history to file"""
    import os
    try:
        with open(DEPLOYMENT_HISTORY, 'w') as f:
            json.dump(deployments, f, indent=2)
            f.flush()  # Flush Python's buffer
            os.fsync(f.fileno())  # Force OS to write to disk immediately
    except Exception as e:
        logger.error(f"Error saving deployment history: {e}")


def clean_display_url(url: str) -> str:
    """
    Clean Vercel URL for display by removing team name suffixes.

    Converts:
    https://simple-calculator-20260211074502-shivam-swamis-projects.vercel.app/
    To:
    https://simple-calculator-20260211074502.vercel.app/

    Preserves the actual URL in history for tracking purposes.
    """
    if not url or not isinstance(url, str):
        return url

    # Pattern: Match timestamp (14 digits), capture it, then remove team name suffix
    # Vercel URLs format: {site-name}-{timestamp}-{team-name}-projects.vercel.app
    # We want to keep: {site-name}-{timestamp}.vercel.app
    import re
    cleaned_url = re.sub(r'(-\d{14})-[a-z0-9-]+-projects\.vercel\.app', r'\1.vercel.app', url)

    # If pattern didn't match (e.g., URL without timestamp), return original URL
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
    Use AI API (Anthropic Claude or Google Gemini) to generate a custom single-page application based on the prompt.
    Returns a dict with 'html', 'css', and 'js' keys.

    Priority:
    1. Try Anthropic Claude if ANTHROPIC_API_KEY is available
    2. Fall back to Google Gemini if GEMINI_API_KEY is available (FREE)
    """
    # Check which APIs are available
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    use_anthropic = ANTHROPIC_AVAILABLE and anthropic_key
    use_gemini = GEMINI_AVAILABLE and gemini_key

    if not use_anthropic and not use_gemini:
        raise RuntimeError(
            "No AI API configured. Please set one of:\n"
            "  - ANTHROPIC_API_KEY (requires credits)\n"
            "  - GEMINI_API_KEY (free at https://aistudio.google.com/apikey)\n"
            "\nInstall SDKs with: pip install anthropic google-generativeai"
        )

    logger.info(f"Generating custom website with AI for prompt: {prompt}")

    # Try Anthropic first (if available)
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

        # If we got here, extraction failed
        missing_keys = [k for k in ["html", "css", "js"] if k not in result]
        raise RuntimeError(f"Failed to extract required code blocks. Missing: {missing_keys}. Response preview: {response_text[:500]}")

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"AI generation failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to generate custom website: {e}")


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
        response_text = response.text
        logger.info("Received Gemini AI response, extracting code blocks...")

        # Extract code blocks (same logic as Anthropic)
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

        # If extraction failed
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

        # If we got here, extraction failed
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
        deploy_url = loop.run_until_complete(deploy_to_vercel_internal(str(project_path), site_name))
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
        deploy_url = loop.run_until_complete(deploy_to_vercel_internal(project_path, site_name))
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
            name="list_deployed_sites",
            description="List all websites deployed through this MCP server. Returns site names, types, deployment times, and live Vercel URLs. CRITICAL INSTRUCTIONS: (1) ALWAYS copy the EXACT URLs from the tool result - NEVER make up or modify URLs. (2) ALWAYS include the complete tool result in your answer to the user. (3) URLs will be on vercel.app domain - NEVER mention netlify.app. (4) If status is 'deployed', the site is LIVE NOW at the URL shown. (5) NEVER say generic things like 'check back later' if the URL is already provided. (6) Copy and paste the EXACT URL from the observation.",
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
    """
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
                final_site_name = f"{site_name}-{timestamp}"
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

            # Start generation AND deployment in background thread
            # This ensures we return immediately (no timeout)
            logger.info(f"[TOOL CALL] Creating background thread...")
            thread = threading.Thread(
                target=generate_and_deploy_in_background,
                args=(site_type, final_site_name, {}, prompt),
                daemon=True
            )
            thread.start()
            logger.info(f"[TOOL CALL] Thread started! Thread ID: {thread.ident}, Is Alive: {thread.is_alive()}")
            logger.info(f"[TOOL CALL] Returning response to agent...")

            # Return immediately
            site_type_name = {
                "todo": "Todo App",
                "portfolio": "Portfolio Website",
                "landing": "Landing Page"
            }.get(site_type, "AI-Generated Website")

            result_text = f"""Website Creation Started!

Site Type: {site_type_name}
Site Name: {final_site_name}

Your website is being generated and deployed in the background.
⏱️  Generation: 15-30 seconds (AI-powered)
⏱️  Deployment: 30-60 seconds (Vercel)

Check deployment status with the 'list_deployed_sites' tool to get your live URL once ready."""

            return [TextContent(type="text", text=result_text)]

        elif name == "list_deployed_sites":
            filter_query = arguments.get("filter", "").strip().lower()
            logger.info(f"[LIST TOOL] Listing deployed sites (filter: '{filter_query}') at {datetime.now().isoformat()}")

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
            active_deployments = [
                d for d in deployments
                if d.get("deployment_status") in ["generating", "deploying"]
                or (d.get("deployment_status") == "deployed" and "vercel.app" in d.get("deploy_url", ""))
            ]

            logger.info(f"[LIST TOOL] Filtered to {len(active_deployments)} active Vercel deployments")

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

                result_lines = [f"Deployed Sites Matching '{arguments.get('filter', '')}':\n"]
            else:
                # No filter: Show recent 5 deployments (or less if fewer exist)
                active_deployments = active_deployments[-5:]  # Last 5 deployments
                if len(active_deployments) == 1:
                    result_lines = ["Your Recently Deployed Site:\n"]
                else:
                    result_lines = [f"Your {len(active_deployments)} Most Recent Deployments:\n"]
            for idx, deployment in enumerate(active_deployments, 1):
                site_name = deployment.get("site_name", "Unknown")
                site_type = deployment.get("site_type", "Unknown")
                deploy_url = deployment.get("deploy_url", "URL not available")
                deployed_at = deployment.get("deployed_at") or deployment.get("created_at", "Unknown date")
                deployment_status = deployment.get("deployment_status", "unknown")

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
                    result_lines.append(f"   Live URL: {display_url}")
                    result_lines.append(f"   Deployed: {time_str}")
                    result_lines.append(f"   ✅ Site is live on Vercel! Click the URL above to visit it now.")
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
                    result_lines.append("🔗 URL is ready above, and Vercel deploys instantly - your site should be live now!.")
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
            return [TextContent(type="text", text=result_text)]

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


async def deploy_to_vercel_internal(project_path: str, site_name: str) -> str:
    """Deploy to Vercel using API"""
    project_dir = Path(project_path)

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
        logger.info(f"Vercel API response keys: {list(deploy_data.keys())}")

        # Vercel returns the deployment URL (unique with hash)
        deployment_url = deploy_data.get("url")
        deployment_id = deploy_data.get("id")

        # Look for production/alias URLs in multiple fields
        alias_urls = deploy_data.get("alias", [])
        aliases_field = deploy_data.get("aliases", [])  # Some versions use "aliases"

        logger.info(f"Deployment URL: {deployment_url}")
        logger.info(f"Alias URLs: {alias_urls}")
        logger.info(f"Aliases field: {aliases_field}")

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
        logger.info(f"Production URL: {deploy_url}")

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
