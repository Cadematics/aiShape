
access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"
 
import json
import re
from typing import TypedDict, Annotated, Sequence, List, Literal, Optional
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from .mcp_client import mcp_executor
from asgiref.sync import async_to_sync

OPENAI_HARDCODED_KEY = openai_api_key

class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    doc_id: str
    work_id: str
    elem_id: str
    available_tools: List[dict]
    next_action: Optional[dict]
    approval_granted: Optional[bool]
    final_reply: Optional[str]


def core_agent_node(state: AgentState):
    """The model reads the user request and selects the optimal MCP tool action."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_HARDCODED_KEY)
    
    tools_summary = "\n".join([
        f"- Name: {t.get('name')}, Description: {t.get('description')}, Schema: {t.get('inputSchema')}"
        for t in state['available_tools']
    ])
    
    system_msg = SystemMessage(
        "You are an elite autonomous Onshape CAD agent acting as an MCP orchestration manager.\n"
        "Analyze the user's geometric modeling request and choose the next tool action from the available list below.\n\n"
        "--- LIVE ACTIVE CONTEXT IDs (DO NOT ASK FOR THESE, USE THEM DIRECTLY) ---\n"
        f"- documentId: \"{state.get('doc_id')}\"\n"
        f"- workspaceId: \"{state.get('work_id')}\"\n"
        f"- elementId: \"{state.get('elem_id')}\"\n\n"
        "--- AVAILABLE MCP TOOLS ---\n"
        f"{tools_summary}\n\n"
        "--- ADVANCED GEOMETRY TARGETING MANDATE ---\n"
        "1. For extrusions, revolves, or fillets, do NOT guess. First use `get_features` to inspect the geometry.\n"
        "2. If a tool like `create_extrude` fails, evaluate FeatureScript via `eval_featurescript` to find the exact "
        "transient query face ID (e.g., `qSketchRegion(makeId(\"SketchId\"), true)`) and use it to execute the tool.\n"
        "3. You can execute multiple non-mutative tools in a row (like `get_features` then `eval_featurescript`) "
        "without seeking user approval. Seek approval ONLY before committing write modifications to Onshape.\n\n"
        "--- RESPONSE MANDATE (STRICT) ---\n"
        "If you need to execute an action, you MUST output a single valid JSON block specifying the target tool name and parameters.\n"
        "```json\n"
        "{\"action\": \"CALL_TOOL\", \"name\": \"tool_name\", \"arguments\": {...}}\n"
        "```\n"
        "If the objective is reached, output a clear text confirmation summary."
    )

    response = llm.invoke([system_msg] + list(state['messages']))
    content = response.content.strip()
    
    # Extract JSON payloads cleanly
    markdown_json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL | re.IGNORECASE)
    if markdown_json_match:
        json_string_to_parse = markdown_json_match.group(1)
    else:
        fallback_match = re.search(r'(\{.*\})', content, re.DOTALL)
        json_string_to_parse = fallback_match.group(1) if fallback_match else None

    if json_string_to_parse:
        try:
            action_data = json.loads(json_string_to_parse.strip())
            if action_data.get("action") == "CALL_TOOL" or "name" in action_data:
                return {"next_action": action_data, "messages": [response], "final_reply": None}
        except Exception as parse_err:
            pass
            
    return {"final_reply": content, "messages": [response], "next_action": None}


def tool_execution_node(state: AgentState):
    """Executes non-mutative read-only tools automatically, returning outputs directly into the model loop."""
    action = state["next_action"]
    print(f"[LOOP EXECUTOR] Automatically running read-only tool: {action['name']}")
    
    tool_output_raw = async_to_sync(mcp_executor.run_with_session)(
        action_type="CALL_TOOL",
        tool_name=action['name'],
        arguments=action['arguments']
    )
    
    # Safely unpack MCP TextContent
    clean_output_list = []
    for block in (tool_output_raw or []):
        if hasattr(block, 'text'):
            clean_output_list.append(block.text)
        else:
            clean_output_list.append(str(block))
            
    final_tool_string = "\n".join(clean_output_list)
    
    return {
        "messages": [AIMessage(content=f"Executed {action['name']}. Response: {final_tool_string}")],
        "next_action": None
    }


def routing_logic(state: AgentState):
    """Determines if we need to prompt the user, run a tool automatically, or exit."""
    action = state.get("next_action")
    if not action:
        return "end"
        
    # List of non-mutative read tools that do not require human-in-the-loop approvals
    READ_ONLY_TOOLS = ["get_features", "get_variables", "get_parts", "eval_featurescript"]
    
    if action["name"] in READ_ONLY_TOOLS:
        return "execute_tool"
        
    return "ask_user"


def create_graph():
    workflow = StateGraph(AgentState)
    
    # Nodes
    workflow.add_node("agent", core_agent_node)
    workflow.add_node("execute_tool", tool_execution_node)
    
    # Flow Routing
    workflow.add_edge(START, "agent")
    workflow.add_node("ask_user", lambda state: state) # Dummy pass node for human approval
    
    workflow.add_conditional_edges(
        "agent",
        routing_logic,
        {
            "execute_tool": "execute_tool",
            "ask_user": "ask_user",
            "end": END
        }
    )
    
    workflow.add_edge("execute_tool", "agent")  # Loop tool output directly back to agent
    workflow.add_edge("ask_user", END)
    
    return workflow.compile()