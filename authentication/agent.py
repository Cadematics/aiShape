
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
    

    # 💥 REPLACE YOUR SYSTEM MESSAGE BLOCK INSIDE agent.py WITH THIS ROBUST RULES ENGINE:
    system_msg = SystemMessage(
        "You are an elite autonomous Onshape CAD agent acting as an MCP orchestration manager.\n"
        "Analyze the user's geometric modeling request and choose the next tool action from the available list below.\n\n"
        "--- LIVE ACTIVE CONTEXT IDs (DO NOT ASK FOR THESE, USE THEM DIRECTLY) ---\n"
        f"- documentId: \"{state.get('doc_id')}\"\n"
        f"- workspaceId: \"{state.get('work_id')}\"\n"
        f"- elementId: \"{state.get('elem_id')}\"\n\n"
        "--- AVAILABLE MCP TOOLS ---\n"
        f"{tools_summary}\n\n"
        "--- GEOMETRY TARGETING MANDATE ---\n"
        "1. When creating an extrusion (`create_extrude`), if you cannot find a specific `featureId` in the logs history, look for any `BTMSketch-151` type entity or use the name of the sketch created earlier (e.g., \"Sketch 1\").\n"
        "2. If a sketch feature ID is not explicitly named, you are authorized to guess or default the `sketchFeatureId` parameter to the name string \"Sketch 1\" or the most recently generated feature identifier token in the history.\n\n"
        "--- RESPONSE MANDATE (STRICT) ---\n"
        "- If a feature modification, deletion, pattern, or creation (like extrude) is requested, you MUST generate a tool call action block immediately.\n"
        "- Do NOT write conversational conversational filler descriptions like 'Let's try to find the ID' or 'Let me retrieve features'. Just invoke the tool.\n"
        "- Every tool execution proposal MUST be a valid JSON block enclosed in markdown backticks:\n"
        "```json\n"
        "{\"action\": \"CALL_TOOL\", \"name\": \"tool_name\", \"arguments\": {...}}\n"
        "```"
    )

    
    response = llm.invoke([system_msg] + list(state['messages']))
    content = response.content.strip()
    
    # 💥 Strategy 1: Look for clean markdown code block fences first
    markdown_json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL | re.IGNORECASE)
    
    # 💥 Strategy 2: Fall back to pulling from the absolute first '{' to the absolute last '}' 
    if markdown_json_match:
        json_string_to_parse = markdown_json_match.group(1)
    else:
        fallback_match = re.search(r'(\{.*\})', content, re.DOTALL)
        json_string_to_parse = fallback_match.group(1) if fallback_match else None

    if json_string_to_parse:
        try:
            action_data = json.loads(json_string_to_parse.strip())
            if action_data.get("action") == "CALL_TOOL" or "name" in action_data:
                print(f"[AGENT PARSE SUCCESS] Intercepted valid action token payload: {action_data.get('name')}")
                return {"next_action": action_data, "messages": [response]}
        except Exception as parse_err:
            print(f"[AGENT PARSE WARNING] Clean extraction failed to load: {str(parse_err)}")
            
    return {"final_reply": content, "messages": [response]}


def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", core_agent_node)
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)
    return workflow.compile()