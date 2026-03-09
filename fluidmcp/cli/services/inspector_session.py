import time

class InspectorSession:
    """
    Wrapper around an MCP client connection used by the inspector to manage 
    the session state and provide utility methods.
    """

    def __init__(self, client, url: str, transport: str):
        self.client = client
        self.url = url
        self.transport = transport
        self.created_at = time.time()
        self.last_used = time.time()

    async def list_tools(self):
        """
        Fetch the tools available in the MCP server.
        """
        self.last_used = time.time()
        return await self.client.list_tools()
    
    async def call_tool(self, name:str, params: dict):
        """
        Execute a tool on the MCP server with the given name and parameters.
        """
        self.last_used = time.time()
        return await self.client.call_tool(name, params)
    
    async def close(self):
        """
        Close the MCP client connection.
        """
        if hasattr(self.client, 'close'):
            await self.client.close()