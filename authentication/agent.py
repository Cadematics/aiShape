
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
    
    # system_msg = SystemMessage(
    #     "You are an elite autonomous Onshape CAD agent acting as an MCP orchestration manager.\n"
    #     "Analyze the user's geometric modeling request and choose the next tool action from the available list below.\n\n"
    #     "--- LIVE ACTIVE CONTEXT IDs (DO NOT ASK FOR THESE, USE THEM DIRECTLY) ---\n"
    #     f"- documentId: \"{state.get('doc_id')}\"\n"
    #     f"- workspaceId: \"{state.get('work_id')}\"\n"
    #     f"- elementId: \"{state.get('elem_id')}\"\n\n"
    #     "--- AVAILABLE MCP TOOLS ---\n"
    #     f"{tools_summary}\n\n"
    #     "--- RESPONSE MANDATE (CRITICAL) ---\n"
    #     "If you need to execute an action, you MUST output a single valid JSON block specifying the target tool name and parameters.\n"
    #     "Do not include any extra introductory text if choosing a tool. Format it exactly like this:\n"
    #     "```json\n"
    #     "{\"action\": \"CALL_TOOL\", \"name\": \"tool_name\", \"arguments\": {...}}\n"
    #     "```\n"
    #     "If the objective is reached, output a clear text confirmation summary."
    # )

    # 💥 REPLACE YOUR PROMPT BLOCK INSIDE agent.py WITH THIS STRENGTHENED VERSION:
    system_msg = SystemMessage(
        "You are an elite autonomous Onshape CAD agent acting as an MCP orchestration manager.\n"
        "Analyze the user's geometric modeling request and choose the next tool action from the available list below.\n\n"
        "--- LIVE ACTIVE CONTEXT IDs (DO NOT ASK FOR THESE, USE THEM DIRECTLY) ---\n"
        f"- documentId: \"{state.get('doc_id')}\"\n"
        f"- workspaceId: \"{state.get('work_id')}\"\n"
        f"- elementId: \"{state.get('elem_id')}\"\n\n"
        "--- AVAILABLE MCP TOOLS ---\n"
        f"{tools_summary}\n\n"
        "--- RESPONSE MANDATE (STRICT) ---\n"
        "1. If a modification, relocation, deletion, or creation is requested, you MUST generate a tool call action.\n"
        "2. Do NOT write conversational filler descriptions like 'Let's proceed with this adjustment' without a JSON block.\n"
        "3. Every tool execution proposal MUST be encapsulated inside a valid JSON block matching this layout:\n"
        "```json\n"
        "{\"action\": \"CALL_TOOL\", \"name\": \"tool_name\", \"arguments\": {...}}\n"
        "```\n"
        "4. If the model is completely built, modified, and finalized according to the instruction, return a text confirmation summary."
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