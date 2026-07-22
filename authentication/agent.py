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
        "--- WORKFLOW MANDATE ---\n"
        "1. For complex geometries (like wine glasses or enclosures), write a local helper Python script using 'Create' "
        "to calculate points, execute it with 'Bash', read the output JSON payload with 'Read', and send it to Onshape.\n"
        "2. Do NOT output preliminary text like 'I will write a script now...' unless you also include the tool execution JSON block in the SAME response.\n"
        "3. Every tool call MUST be outputted as a JSON block in markdown backticks:\n"
        "```json\n"
        "{\"action\": \"CALL_TOOL\", \"name\": \"tool_name\", \"arguments\": {...}}\n"
        "```\n\n"
        "--- LIVE ACTIVE CONTEXT IDs ---\n"
        f"- documentId: \"{state.get('doc_id')}\"\n"
        f"- workspaceId: \"{state.get('work_id')}\"\n"
        f"- elementId: \"{state.get('elem_id')}\"\n\n"
        f"--- AVAILABLE MCP TOOLS ---\n{tools_summary}"
    )

    response = llm.invoke([system_msg] + list(state['messages']))
    content = response.content.strip()
    
    # Robust Regex Extraction for Tool Calls
    match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL | re.IGNORECASE) or re.search(r'(\{.*action.*?\})', content, re.DOTALL)
    if match:
        try:
            action_data = json.loads(match.group(1).strip())
            if action_data.get("action") == "CALL_TOOL" or "name" in action_data:
                return {"next_action": action_data, "messages": [response], "final_reply": None}
        except Exception as e:
            print(f"[PARSER WARNING] Failed to parse tool call JSON: {e}")
            
    return {"final_reply": content, "messages": [response], "next_action": None}



def should_continue(state: AgentState) -> Literal["continue", "exit"]:
    """Determines whether a tool runs autonomously or pauses for human approval."""
    action = state.get("next_action")
    if not action:
        return "exit"
        
    # Safe diagnostic tools run automatically in the background
    BACKGROUND_SAFE_TOOLS = [
        "Create", "Read", "ListDir", "Bash",
        "get_features", "get_variables", "get_parts", 
        "eval_featurescript", "get_elements", "get_document_summary"
    ]
    
    if action.get("name") in BACKGROUND_SAFE_TOOLS:
        return "continue"
        
    return "exit"


def execute_background_tool(state: AgentState):
    """Executes background diagnostic tools automatically without breaking the request loop."""
    action = state["next_action"]
    print(f"[AUTONOMY ENGINE] Auto-running background tool: {action['name']}")
    
    tool_output_raw = async_to_sync(mcp_executor.run_with_session)(
        action_type="CALL_TOOL",
        tool_name=action['name'],
        arguments=action['arguments']
    )
    
    clean_output_list = []
    for block in (tool_output_raw or []):
        if hasattr(block, 'text'):
            clean_output_list.append(block.text)
        else:
            clean_output_list.append(str(block))
            
    final_tool_string = "\n".join(clean_output_list)
    
    return {
        "messages": [AIMessage(content=f"System Notification: Background tool '{action['name']}' returned: {final_tool_string}")],
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