import json
import re
from typing import TypedDict, Sequence, List, Literal, Optional
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, HumanMessage
from .mcp_client import mcp_executor
from asgiref.sync import async_to_sync

OPENAI_HARDCODED_KEY = "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"

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
    """Determines the next tool call or produces the final answer."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_HARDCODED_KEY)
    
    tools_summary = "\n".join([
        f"- Name: {t.get('name')}, Description: {t.get('description')}"
        for t in state['available_tools']
    ])

    system_msg = SystemMessage(
        "You are an autonomous Onshape CAD orchestration agent.\n"
        "You have local developer tools available: 'Create', 'Read', 'ListDir', and 'Bash'.\n\n"
        "--- STRICT ACTION PROTOCOL ---\n"
        "1. Do NOT output conversational status updates (e.g., 'I will proceed now', 'Let us create a sketch').\n"
        "2. If an action or tool call is needed, you MUST output ONLY the JSON tool block. No introductory text.\n"
        "3. Every tool execution proposal MUST be formatted exactly as a markdown JSON block:\n"
        "```json\n"
        "{\"action\": \"CALL_TOOL\", \"name\": \"tool_name\", \"arguments\": {...}}\n"
        "```\n"
        "4. Keep a local session log of every action taken using 'Create' at `/tmp/aishape_logs/log.txt`.\n\n"
        "--- LIVE ACTIVE CONTEXT IDs ---\n"
        f"- documentId: \"{state.get('doc_id')}\"\n"
        f"- workspaceId: \"{state.get('work_id')}\"\n"
        f"- elementId: \"{state.get('elem_id')}\"\n\n"
        f"--- AVAILABLE MCP TOOLS ---\n{tools_summary}"
    )

    response = llm.invoke([system_msg] + list(state['messages']))
    content = response.content.strip()
    
    # 🔍 DEBUG PRINT 1: Print raw LLM string to Render logs
    print("\n==================== [RAW LLM OUTPUT] ====================")
    print(content)
    print("==========================================================\n")

    # Match JSON tool call blocks cleanly
    match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL | re.IGNORECASE) or re.search(r'(\{.*?"action"\s*:\s*"CALL_TOOL".*?\})', content, re.DOTALL)
    if match:
        try:
            action_data = json.loads(match.group(1).strip())
            if action_data.get("action") == "CALL_TOOL" or "name" in action_data:
                print(f"✅ [PARSED ACTION]: {json.dumps(action_data, indent=2)}")
                return {"next_action": action_data, "messages": [response], "final_reply": None}
        except Exception as e:
            print(f"❌ [PARSER EXCEPTION]: {e}")
            
    print("⚠️ [PARSER WARNING]: No tool call block matched! Returning text reply.")
    return {"final_reply": content, "messages": [response], "next_action": None}


def should_continue(state: AgentState) -> Literal["continue", "exit"]:
    """Determines whether a tool runs autonomously in the background or pauses for UI approval."""
    action = state.get("next_action")
    if not action:
        print("🚪 [ROUTING DECISION]: Exit (No action present)")
        return "exit"
        
    BACKGROUND_SAFE_TOOLS = [
        "Create", "Read", "ListDir", "Bash",
        "get_features", "get_variables", "get_parts", 
        "eval_featurescript", "get_elements", "get_document_summary",
        "onshape_read_resource", "onshape_api_search", "onshape_api_explain"
    ]
    
    tool_name = action.get("name")
    if tool_name in BACKGROUND_SAFE_TOOLS:
        print(f"🔄 [ROUTING DECISION]: Continue autonomously (Background tool: {tool_name})")
        return "continue"
        
    print(f"🛑 [ROUTING DECISION]: Exit for Human Approval (Write tool: {tool_name})")
    return "exit"


def execute_background_tool(state: AgentState):
    """Executes safe diagnostic and system tools autonomously without breaking the request stream."""
    action = state["next_action"]
    print(f"⚙️ [AUTONOMY ENGINE] Auto-running background tool: {action['name']}")
    
    tool_output_raw = async_to_sync(mcp_executor.run_with_session)(
        action_type="CALL_TOOL",
        tool_name=action['name'],
        arguments=action['arguments']
    )
    
    clean_output_list = [
        block.text if hasattr(block, 'text') else str(block) 
        for block in (tool_output_raw or [])
    ]
    final_tool_string = "\n".join(clean_output_list)
    
    print(f"📥 [TOOL OUTPUT OUTPUT]:\n{final_tool_string[:300]}...\n")
    
    return {
        "messages": [AIMessage(content=f"System Notification: Tool '{action['name']}' returned output: {final_tool_string}")],
        "next_action": None
    }


def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", core_agent_node)
    workflow.add_node("background_tools", execute_background_tool)
    
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