


###############
# authentication/mcp_client.py
import os
import subprocess
import shutil
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class OnshapeMCPExecutor:
    """Handles isolated MCP operations, dynamically routing between Onshape and system tools."""
    
    def __init__(self):
        env = os.environ.copy()
        env["ONSHAPE_ACCESS_KEY"] = "on_bYfDyZ0QtxjnQOAqlSPTD"
        env["ONSHAPE_SECRET_KEY"] = "aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
        
        # 1. Onshape Server Config
        self.onshape_params = StdioServerParameters(
            command="python",
            args=["-m", "onshape_mcp.server"],
            env=env
        )
        
        # 2. Hardcoded Core System Tools (Simulating the CLI's filesystem/bash capabilities)
        self.system_tools = {
            "Create": "Writes text or code content directly to a file path.",
            "Edit": "Modifies lines inside an existing local target file.",
            "Read": "Reads and returns the contents of a local file path.",
            "ListDir": "Lists files and folders inside a given path layout.",
            "Bash": "Executes a safe shell string command inside a workspace."
        }

    def _execute_system_tool(self, tool_name: str, arguments: dict):
        """Autonomously processes OS-level actions exactly like the CLI environment."""
        try:
            from mcp.types import TextContent
            
            if tool_name == "Create" or tool_name == "write_to_file":
                path = arguments.get("TargetFile") or arguments.get("path")
                content = arguments.get("CodeContent") or arguments.get("content", "")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return [TextContent(type="text", text=f"File successfully created at {path}")]

            elif tool_name == "Read" or tool_name == "read_file":
                path = arguments.get("path")
                if not os.path.exists(path):
                    return [TextContent(type="text", text=f"Error: File path {path} does not exist.")]
                with open(path, "r", encoding="utf-8") as f:
                    return [TextContent(type="text", text=f.read())]

            elif tool_name == "ListDir":
                path = arguments.get("path", ".")
                items = os.listdir(path)
                return [TextContent(type="text", text=f"Contents of {path}:\n" + "\n".join(items))]

            elif tool_name == "Bash" or tool_name == "run_command":
                cmd = arguments.get("CommandLine") or arguments.get("command")
                cwd = arguments.get("Cwd", None)
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
                output = f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
                return [TextContent(type="text", text=output)]
                
        except Exception as e:
            from mcp.types import TextContent
            return [TextContent(type="text", text=f"System Tool Error execution failure: {str(e)}")]
            
        return None

    async def run_with_session(self, action_type: str, tool_name: str = None, arguments: dict = None):
        """Routes and handles tool lifecycles between local shell mock nodes and remote server processes."""
        # Route System calls instantly without booting Onshape sub-processes
        if action_type == "CALL_TOOL" and tool_name in self.system_tools:
            return self._execute_system_tool(tool_name, arguments)
            
        async with stdio_client(self.onshape_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                
                if action_type == "GET_TOOLS":
                    response = await session.list_tools()
                    # Map Onshape tools from server
                    mcp_tools = [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in response.tools]
                    
                    # Inject System tools schema blueprints so the LLM explicitly knows it can use them
                    for name, desc in self.system_tools.items():
                        mcp_tools.append({
                            "name": name,
                            "description": desc,
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "content": {"type": "string"},
                                    "command": {"type": "string"},
                                    "CommandLine": {"type": "string"},
                                    "TargetFile": {"type": "string"},
                                    "CodeContent": {"type": "string"},
                                    "Cwd": {"type": "string"}
                                }
                            }
                        })
                    return mcp_tools
                
                elif action_type == "CALL_TOOL" and tool_name:
                    print(f"[MCP CLIENT EXECUTE] Dispatching Onshape tool call: '{tool_name}'...")
                    response = await session.call_tool(tool_name, arguments or {})
                    return response.content
                
        return None

mcp_executor = OnshapeMCPExecutor()