access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"



import os
import sys
import json
import asyncio
import subprocess
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class OnshapeMCPManager:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OnshapeMCPManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    async def initialize(self):
        async with self._lock:
            if self.initialized:
                return
            
            print("[MCP CLIENT] Launching background Onshape MCP process stream...")
            
            # Inject working API authentication context strings from variables
            env = os.environ.copy()
            env["ONSHAPE_ACCESS_KEY"] = access_key
            env["ONSHAPE_SECRET_KEY"] = secret_key
            
            # Target the installed python entry point to spawn the server module background process
            self.server_parameters = StdioServerParameters(
                command="python",
                args=["-m", "onshape_mcp"],
                env=env
            )
            
            # Initialize async context manager loops
            self._client_context = stdio_client(self.server_parameters)
            self.read_stream, self.write_stream = await self._client_context.__aenter__()
            
            # Initialize session parameters handshake
            self.session = ClientSession(self.read_stream, self.write_stream)
            await self.session.__aenter__()
            await self.session.initialize()
            
            self.initialized = True
            print("[MCP CLIENT SUCCESS] Handshake with Onshape MCP complete. Available tools indexed.")

    async def get_tools(self):
        if not self.initialized:
            await self.initialize()
        response = await self.session.list_tools()
        # Map tools into a clean schema layout that the LLM models can read
        return response.tools

    async def call_tool(self, name: str, arguments: dict):
        if not self.initialized:
            await self.initialize()
        print(f"[MCP CLIENT EXECUTE] Sending payload to tool '{name}' via stdio...")
        response = await self.session.call_tool(name, arguments)
        return response.content

# Helper instantiation target hook
mcp_manager = OnshapeMCPManager()