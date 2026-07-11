access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"


import os
import sys
import json
import asyncio
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
            
            print("[MCP CLIENT] Spawning background Onshape MCP process stream...")
            
            env = os.environ.copy()
            env["ONSHAPE_ACCESS_KEY"] = "on_bYfDyZ0QtxjnQOAqlSPTD"
            env["ONSHAPE_SECRET_KEY"] = "aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
            
            # 💥 THE CORE FIX: Point args directly to the .server sub-module runner target
            self.server_parameters = StdioServerParameters(
                command="python",
                args=["-m", "onshape_mcp.server"],
                env=env
            )
            
            # Setup async I/O connection context pipes
            self._client_context = stdio_client(self.server_parameters)
            self.read_stream, self.write_stream = await self._client_context.__aenter__()
            
            # Perform protocol handshake initialization
            self.session = ClientSession(self.read_stream, self.write_stream)
            await self.session.__aenter__()
            await self.session.initialize()
            
            self.initialized = True
            print("[MCP CLIENT SUCCESS] Communication bridge with Onshape MCP established.")

    async def get_tools(self):
        if not self.initialized:
            await self.initialize()
        response = await self.session.list_tools()
        return response.tools

    async def call_tool(self, name: str, arguments: dict):
        if not self.initialized:
            await self.initialize()
        print(f"[MCP CLIENT EXECUTE] Sending pipeline frame to tool '{name}'...")
        response = await self.session.call_tool(name, arguments)
        return response.content

mcp_manager = OnshapeMCPManager()