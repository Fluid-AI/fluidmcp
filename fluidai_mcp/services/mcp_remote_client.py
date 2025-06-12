#!/usr/bin/env python3
"""
FluidMCP Remote Client - MCP STDIO to HTTP Bridge
"""
import sys
import json
import asyncio
import aiohttp
import os
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class PackageInfo:
    name: str
    session_id: Optional[str] = None

class FluidMCPRemoteClient:
    def __init__(self):
        self.server_url = os.environ.get("FMCP_SERVER_URL", "http://localhost:8099")
        self.bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
        self.single_package_mode = os.environ.get("FMCP_PACKAGE_NAME")
        self.packages: Dict[str, PackageInfo] = {}
        self.headers = {"Content-Type": "application/json"}
        
        if self.bearer_token:
            self.headers["Authorization"] = f"Bearer {self.bearer_token}"

    async def discover_packages(self) -> bool:
        """Discover packages from OpenAPI spec"""
        if self.single_package_mode:
            self.packages[self.single_package_mode] = PackageInfo(self.single_package_mode)
            return True

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.server_url}/openapi.json", headers=self.headers, timeout=10) as resp:
                    if resp.status == 200:
                        openapi_spec = await resp.json()
                        package_names = self._extract_packages_from_openapi(openapi_spec)
                        
                        for package_name in package_names:
                            self.packages[package_name] = PackageInfo(package_name)
                        
                        print(f"Discovered {len(package_names)} packages: {package_names}", file=sys.stderr)
                        return len(package_names) > 0
        except Exception as e:
            print(f"Failed to discover packages: {e}", file=sys.stderr)
        
        return False

    def _extract_packages_from_openapi(self, openapi_spec: Dict) -> List[str]:
        """Extract package names from OpenAPI paths"""
        packages = set()
        paths = openapi_spec.get("paths", {})
        
        for path in paths.keys():
            # Look for /{package}/mcp/ pattern
            if "/mcp/" in path:
                parts = path.strip("/").split("/")
                if len(parts) >= 2:
                    package_name = parts[0]
                    if package_name and package_name not in ["docs", "openapi.json", "redoc"]:
                        packages.add(package_name)
        
        return list(packages)

    async def get_session_id(self, package_name: str) -> Optional[str]:
        """Get or create SSE session for package"""
        if package_name not in self.packages:
            return None
            
        package_info = self.packages[package_name]
        if package_info.session_id:
            return package_info.session_id

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.server_url}/{package_name}/sse/start",
                    headers=self.headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        session_id = result["session_id"]
                        package_info.session_id = session_id
                        return session_id
        except Exception as e:
            print(f"Session init error for {package_name}: {e}", file=sys.stderr)
        
        return None

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get tools from all packages"""
        all_tools = []
        
        for package_name in self.packages:
            tools = await self._get_package_tools(package_name)
            if tools:
                if not self.single_package_mode:
                    # Add package prefix for multi-package mode
                    for tool in tools:
                        tool["_package"] = package_name
                        tool["_original_name"] = tool["name"]
                        tool["name"] = f"{self._clean_name(package_name)}_{self._clean_name(tool['name'])}"
                
                all_tools.extend(tools)
        
        return all_tools

    async def _get_package_tools(self, package_name: str) -> List[Dict[str, Any]]:
        """Get tools from specific package"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.server_url}/{package_name}/mcp/tools/list",
                    headers=self.headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        tools = result.get("result", {}).get("tools", [])
                        return [self._clean_tool(tool) for tool in tools if tool.get("name")]
        except Exception as e:
            print(f"Failed to get tools from {package_name}: {e}", file=sys.stderr)
        
        return []

    def _clean_tool(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Clean tool schema for Claude compatibility"""
        clean_tool = {
            "name": str(tool["name"]),
            "description": str(tool.get("description", ""))
        }
        
        # Copy package metadata if present
        for field in ["_package", "_original_name"]:
            if field in tool:
                clean_tool[field] = tool[field]
        
        # Clean inputSchema
        if "inputSchema" in tool and isinstance(tool["inputSchema"], dict):
            schema = tool["inputSchema"]
            clean_schema = {
                "type": "object",
                "properties": {},
                "required": schema.get("required", [])
            }
            
            # Copy properties with allowed fields only
            if "properties" in schema:
                for prop_name, prop_def in schema["properties"].items():
                    if isinstance(prop_def, dict):
                        clean_prop = {}
                        for field in ["type", "description", "enum", "default"]:
                            if field in prop_def:
                                clean_prop[field] = prop_def[field]
                        clean_schema["properties"][prop_name] = clean_prop
            
            clean_tool["inputSchema"] = clean_schema
        
        return clean_tool

    def _clean_name(self, name: str) -> str:
        """Clean name for Claude compatibility"""
        cleaned = re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:64].strip('_-')
        return cleaned or "tool"

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], request_id: int) -> Dict[str, Any]:
        """Call tool via SSE endpoint"""
        package_name, actual_tool_name = self._parse_tool_name(tool_name)
        
        if not package_name:
            return self._error_response(request_id, -32601, f"Tool not found: {tool_name}")

        session_id = await self.get_session_id(package_name)
        if not session_id:
            return self._error_response(request_id, -32603, f"Failed to get session for {package_name}")

        tool_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": actual_tool_name, "arguments": arguments}
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.server_url}/{package_name}/sse/tools/call",
                    headers=self.headers,
                    json=tool_request,
                    timeout=30
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return self._extract_response(result, request_id)
                    else:
                        text = await resp.text()
                        return self._error_response(request_id, -32603, f"Tool call failed: {resp.status}")
        except Exception as e:
            return self._error_response(request_id, -32603, f"Tool call error: {e}")

    def _parse_tool_name(self, tool_name: str) -> tuple[Optional[str], str]:
        """Parse tool name to get package and actual tool name"""
        if self.single_package_mode:
            return self.single_package_mode, tool_name
        
        # Multi-package: extract from prefixed name
        if "_" in tool_name:
            package_name, actual_tool_name = tool_name.split("_", 1)
            if package_name in self.packages:
                return package_name, actual_tool_name
        
        return None, tool_name

    def _extract_response(self, sse_result: Dict[str, Any], request_id: int) -> Dict[str, Any]:
        """Extract final response from SSE result"""
        messages = sse_result.get("messages", [])
        if messages:
            last_message = messages[-1]
            if last_message.get("status") == "completed" and "response" in last_message:
                try:
                    return json.loads(last_message["response"])
                except json.JSONDecodeError:
                    pass
        
        return self._error_response(request_id, -32603, "No valid response from tool")

    def _error_response(self, request_id: int, code: int, message: str) -> Dict[str, Any]:
        """Create JSON-RPC error response"""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message}
        }

    async def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle MCP JSON-RPC request"""
        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            success = await self.discover_packages()
            if success:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": f"FluidMCP ({len(self.packages)} packages)",
                            "version": "1.0.0"
                        }
                    }
                }
            else:
                return self._error_response(request_id, -32603, "No packages available")

        elif method == "notifications/initialized":
            return None

        elif method == "tools/list":
            if not self.packages:
                await self.discover_packages()
            
            tools = await self.get_all_tools()
            print(f"Returning {len(tools)} tools from {len(self.packages)} packages", file=sys.stderr)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": tools}
            }

        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if not tool_name:
                return self._error_response(request_id, -32602, "Tool name required")
            
            return await self.call_tool(tool_name, arguments, request_id)

        else:
            return self._error_response(request_id, -32601, f"Unknown method: {method}")

    async def run(self):
        """Main STDIO loop"""
        mode = "single-package" if self.single_package_mode else "multi-package"
        print(f"🔗 Starting FluidMCP remote client", file=sys.stderr)
        print(f"📡 Server: {self.server_url}", file=sys.stderr)
        print(f"📦 Mode: {mode}", file=sys.stderr)
        
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    request = json.loads(line)
                    response = await self.handle_request(request)
                    
                    if response:
                        print(json.dumps(response), flush=True)
                        
                except json.JSONDecodeError:
                    error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
                    print(json.dumps(error), flush=True)
                except Exception as e:
                    error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
                    print(json.dumps(error), flush=True)
                    
        except KeyboardInterrupt:
            print("Remote client stopped", file=sys.stderr)

def main():
    """CLI entry point"""
    client = FluidMCPRemoteClient()
    asyncio.run(client.run())

if __name__ == "__main__":
    main()