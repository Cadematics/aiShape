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
        f"- Name: {t.get('name')}, Description: {t.get('description')}, Input Schema: {t.get('inputSchema', {})}"
        for t in state['available_tools']
    ])

    system_msg = SystemMessage(
        "You are an autonomous Onshape CAD orchestration agent.\n"
        "You have access to MCP CAD tools and local developer tools ('Create', 'Read', 'ListDir', 'Bash').\n\n"
        "--- ABSOLUTE FORMAT RULE ---\n"
        "Do NOT write conversational chatter like 'I will create a sketch now' or 'Let us start by...'.\n"
        "If any action or modeling step is required, your response MUST be ONLY a single Markdown JSON code block containing the tool call.\n"
        "Example:\n"
        "```json\n"
        "{\n"
        '  "action": "CALL_TOOL",\n'
        '  "name": "target_tool_name",\n'
        '  "arguments": { ... }\n'
        "}\n"
        "```\n\n"
        "--- LIVE ACTIVE CONTEXT IDs ---\n"
        f"- documentId: \"{state.get('doc_id')}\"\n"
        f"- workspaceId: \"{state.get('work_id')}\"\n"
        f"- elementId: \"{state.get('elem_id')}\"\n\n"
        f"--- AVAILABLE TOOLS ---\n{tools_summary}"
    )

    response = llm.invoke([system_msg] + list(state['messages']))
    content = response.content.strip()

    print("\n==================== [RAW LLM OUTPUT] ====================")
    print(content)
    print("==========================================================\n")

    # Extract JSON tool call block
    match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL | re.IGNORECASE) or re.search(r'(\{.*?"action"\s*:\s*"CALL_TOOL".*?\})', content, re.DOTALL)
    
    if match:
        try:
            action_data = json.loads(match.group(1).strip())
            if action_data.get("action") == "CALL_TOOL" or "name" in action_data:
                print(f"✅ [PARSED ACTION]: {json.dumps(action_data, indent=2)}")
                return {"next_action": action_data, "messages": [response], "final_reply": None}
        except Exception as e:
            print(f"❌ [PARSER EXCEPTION]: {e}")

    # Fallback: if the LLM output conversational text without JSON, check if it tried to outline a step and force a tool retry
    print("⚠️ [PARSER WARNING]: Model output prose without JSON tool call.")
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
        "onshape_read_resource", "onshape_api_search", "onshape_api_explain",
        "onshape_auth_status", "onshape_mcp_get_started", "onshape_list_resources"
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
    
    print(f"📥 [TOOL OUTPUT]:\n{final_tool_string[:300]}...\n")
    
    return {
        "messages": [AIMessage(content=f"System Notification: Tool '{action['name']}' returned: {final_tool_string}")],
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