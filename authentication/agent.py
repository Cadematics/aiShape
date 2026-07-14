
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
import re

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
    # 💥 New Plan State Trackers
    plan: List[str]
    current_step_index: int


def core_agent_node(state: AgentState):
    """The planner/executor node. It generates plans or executes the current pending step."""
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
        "Analyze the user's geometric modeling request and choose the next tool action from the available list below.\n\n"
        "--- LIVE ACTIVE CONTEXT IDs ---\n"
        f"- documentId: \"{state.get('doc_id')}\"\n"
        f"- workspaceId: \"{state.get('work_id')}\"\n"
        f"- elementId: \"{state.get('elem_id')}\"\n\n"
        f"{plan_state_desc}"
        "--- AVAILABLE MCP TOOLS ---\n"
        f"{tools_summary}\n\n"
        "--- OPERATIONAL PROTOCOLS ---\n"
        "1. PLAN FIRST: If the user provides a modeling request and there is no active plan yet, you MUST outline the complete list of steps required to fulfill the request. Output this list clearly in text, followed by a JSON tool proposal to save this plan state.\n"
        "2. STEP-BY-STEP WORKFLOW: If a plan already exists, look at the Next Step to run. Propose ONLY the single JSON tool call necessary to execute that specific step. Do not group multiple steps into one action.\n"
        "3. Every tool execution proposal MUST be a valid JSON block enclosed in markdown backticks:\n"
        "```json\n"
        "{\"action\": \"CALL_TOOL\", \"name\": \"tool_name\", \"arguments\": {...}}\n"
        "```"
    )

    response = llm.invoke([system_msg] + list(state['messages']))
    content = response.content.strip()
    
    # Unpack JSON block
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
                # If a tool is called, keep the output structured
                return {"next_action": action_data, "messages": [response], "final_reply": None}
        except Exception:
            pass
            
    return {"final_reply": content, "messages": [response], "next_action": None}


def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", core_agent_node)
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)
    return workflow.compile()