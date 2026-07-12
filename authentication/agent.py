
access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"
 

import json
import re
from typing import TypedDict, Annotated, Sequence, List, Literal, Optional
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage

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
        "--- RESPONSE MANDATE (CRITICAL) ---\n"
        "If you need to execute an action, you MUST output a single valid JSON block specifying the target tool name and parameters.\n"
        "Do not include any extra introductory text if choosing a tool. Format it exactly like this:\n"
        "```json\n"
        "{\"action\": \"CALL_TOOL\", \"name\": \"tool_name\", \"arguments\": {...}}\n"
        "```\n"
        "If the objective is reached, output a clear text confirmation summary."
    )
    
    response = llm.invoke([system_msg] + list(state['messages']))
    content = response.content.strip()
    
    # 💥 DEFENSIVE PARSING ENGINE: Captures JSON blocks with or without backtick wrappers
    json_match = re.search(r'(\{.*?\})', content, re.DOTALL)
    if json_match:
        try:
            action_data = json.loads(json_match.group(1))
            if action_data.get("action") == "CALL_TOOL" or "name" in action_data:
                return {"next_action": action_data, "messages": [response]}
        except Exception as parse_err:
            print(f"[AGENT PARSE WARNING] Text block contained pseudo-JSON but failed load: {str(parse_err)}")
            
    return {"final_reply": content, "messages": [response]}

def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", core_agent_node)
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)
    return workflow.compile()