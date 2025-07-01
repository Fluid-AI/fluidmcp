"""
MCP session management utilities
"""
import json
import time
import subprocess
from typing import Dict, Any

def initialize_mcp_server(process: subprocess.Popen) -> bool:
    """Initialize MCP server with proper handshake"""
    try:
        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "fluidmcp-client", "version": "1.0.0"}
            }
        }
        
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        
        # Wait for response
        start_time = time.time()
        while time.time() - start_time < 10:
            if process.poll() is not None:
                return False
            response_line = process.stdout.readline().strip()
            if response_line:
                response = json.loads(response_line)
                if response.get("id") == 0 and "result" in response:
                    # Send initialized notification
                    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                    process.stdin.write(json.dumps(notif) + "\n")
                    process.stdin.flush()
                    return True
            time.sleep(0.1)
        return False
    except Exception as e:
        print(f"Initialization error: {e}")
        return False

# Global session storage
active_sessions: Dict[str, Dict[str, Any]] = {}
persistent_tool_sessions: Dict[str, str] = {}  # Maps package_name to session_id