
access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"
 
import json
import re
from typing import TypedDict, Annotated, Sequence, List, Literal, Optional
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
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
    plan: List[str]
    current_step_index: int


def core_agent_node(state: AgentState):
    """The model reads active state context and decides on the next design or diagnostic action."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_HARDCODED_KEY)
    
    tools_summary = "\n".join([
        f"- Name: {t.get('name')}, Description: {t.get('description')}, Schema: {t.get('inputSchema')}"
        for t in state['available_tools']
    ])

    plan_state_desc = ""
    current_plan = state.get("plan") or []
    current_idx = state.get("current_step_index", 0)

    if current_plan:
        plan_state_desc = (
            f"--- ACTIVE EXECUTION PLAN ---\n"
            f"Total Steps: {len(current_plan)}\n"
            f"Current Step Index: {current_idx}\n"
            f"Next Step to run: \"{current_plan[current_idx] if current_idx < len(current_plan) else 'None'}\"\n\n"
        )

    system_msg = SystemMessage(
        "You are an elite autonomous Onshape CAD agent acting as an MCP orchestration manager.\n"
        "You have access to a local development sandbox environment. When dealing with complex nested "
        "JSON geometries (such as creating Onshape sketches, geometric constraints, or extrusion features), "
        "do not try to write out massive JSON manually if it risks syntax breakdown. Instead, feel free to "
        "write a local helper Python script to generate clean payloads, execute it via your terminal tools, "
        "and read the clean output file.\n\n"
        "--- LIVE ACTIVE CONTEXT IDs (DO NOT ASK FOR THESE) ---\n"
        f"- documentId: \"{state.get('doc_id')}\"\n"
        f"- workspaceId: \"{state.get('work_id')}\"\n"
        f"- elementId: \"{state.get('elem_id')}\"\n\n"
        f"{plan_state_desc}"
        "--- AVAILABLE MCP TOOLS ---\n"
        f"{tools_summary}\n\n"
        "--- RESPONSE MANDATE (STRICT) ---\n"
        "If you need to execute an action, you MUST output a single valid JSON block specifying the target tool name and parameters.\n"
        "Do not include any extra introductory text if choosing a tool. Format it exactly like this:\n"
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
        except Exception:
            pass
            
    return {"final_reply": content, "messages": [response], "next_action": None}


def should_continue(state: AgentState) -> Literal["continue", "exit"]:
    """Determines whether a tool can be run autonomously in the background, or if we must ask the user."""
    action = state.get("next_action")
    if not action:
        return "exit"
        
    # List of safe, diagnostic, read-only or diagnostic-generation tools
    BACKGROUND_SAFE_TOOLS = [
        "get_features", 
        "get_variables", 
        "get_parts", 
        "eval_featurescript", 
        "get_elements", 
        "get_document_summary",
        "onshape_auth_status",
        "onshape_mcp_get_started",
        "onshape_list_resources",
        "onshape_read_resource",
        "write_to_file",
        "run_command"
    ]
    
    if action.get("name") in BACKGROUND_SAFE_TOOLS:
        return "continue"
        
    return "exit"


def execute_background_tool(state: AgentState):
    """Runs read-only queries and sandbox tools autonomously without breaking the HTTP response loop."""
    action = state["next_action"]
    print(f"[AUTONOMY LOOP] Auto-executing background tool: {action['name']}")
    
    tool_output_raw = async_to_sync(mcp_executor.run_with_session)(
        action_type="CALL_TOOL",
        tool_name=action['name'],
        arguments=action['arguments']
    )
    
    # Extract TextContent structure
    clean_output_list = []
    for block in (tool_output_raw or []):
        if hasattr(block, 'text'):
            clean_output_list.append(block.text)
        else:
            clean_output_list.append(str(block))
            
    final_tool_string = "\n".join(clean_output_list)
    
    # Pack output back into historical state context
    new_message = AIMessage(
        content=f"Executed background tool '{action['name']}' automatically. Response: {final_tool_string}"
    )
    
    return {
        "messages": [new_message],
        "next_action": None
    }


def create_graph():
    workflow = StateGraph(AgentState)
    
    # Nodes
    workflow.add_node("agent", core_agent_node)
    workflow.add_node("background_tools", execute_background_tool)
    
    # Flow Routing
    workflow.add_edge(START, "agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "background_tools",
            "exit": END
        }
    )
    
    workflow.add_edge("background_tools", "agent")
    return workflow.compile()