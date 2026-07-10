import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Define how to boot up your target open-source MCP server container or process
server_parameters = StdioServerParameters(
    command="npx",
    args=["-y", "@hedless/onshape-mcp"], # Pulls and runs the open-source community cad tool server
    env={
        "ONSHAPE_API_URL": "https://cad.onshape.com",
        "ONSHAPE_ACCESS_KEY": "on_bYfDyZ0QtxjnQOAqlSPTD",
        "ONSHAPE_SECRET_KEY": "aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
    }
)

async def run_mcp_tool(tool_name: str, arguments: dict):
    """Connects to the open-source MCP server and runs a native CAD tool execution."""
    async with stdio_client(server_parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Complete the initial protocol handshake
            await session.initialize()
            
            # Fire the tool command directly to the Onshape engine
            response = await session.call_tool(tool_name, arguments)
            return response.content