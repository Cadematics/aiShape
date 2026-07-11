import os
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class OnshapeMCPExecutor:
    """Handles isolated, request-scoped MCP server operations to avoid AnyIO cross-task loop collisions."""
    
    def __init__(self):
        env = os.environ.copy()
        env["ONSHAPE_ACCESS_KEY"] = "on_bYfDyZ0QtxjnQOAqlSPTD"
        env["ONSHAPE_SECRET_KEY"] = "aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
        
        self.server_parameters = StdioServerParameters(
            command="python",
            args=["-m", "onshape_mcp.server"],
            env=env
        )

    async def run_with_session(self, action_type: str, tool_name: str = None, arguments: dict = None):
        """Runs the entire subprocess lifecycle safely inside a single isolated task loop."""
        async with stdio_client(self.server_parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # Perform official protocol handshake initialization
                await session.initialize()
                
                if action_type == "GET_TOOLS":
                    response = await session.list_tools()
                    return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in response.tools]
                
                elif action_type == "CALL_TOOL" and tool_name:
                    print(f"[MCP CLIENT EXECUTE] Dispatching tool call: '{tool_name}'...")
                    response = await session.call_tool(tool_name, arguments or {})
                    return response.content
                
        return None

# Instantiation hook matching views interface signatures
mcp_executor = OnshapeMCPExecutor()