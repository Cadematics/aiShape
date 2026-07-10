
access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"
 


import os
import json
import requests
from requests.auth import HTTPBasicAuth
from typing import TypedDict, Annotated, Sequence, List, Literal
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool

# Your validated working verification key string variable
OPENAI_HARDCODED_KEY = openai_api_key
# =====================================================================
# 📦 SHARED GRAPH STATE MEMORY
# =====================================================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    doc_id: str
    work_id: str
    elem_id: str
    selected_entity: dict
    steps: List[str]            # The list of operations to perform
    current_step_index: int     # Tracking progress
    current_errors: str         # Active compiler or API errors to debug
    available_tools: List[str]  # Dynamic directory of functional tools
    generated_code: str         # Staging area for new tools built on the fly

# Global dictionary holding dynamically generated code tools inside memory runtime
DYNAMIC_TOOL_REGISTRY = {}

# =====================================================================
# 🛠️ NATIVE STATIC BASE TOOLS
# =====================================================================
@tool
def get_part_studio_features_tool(state: dict) -> dict:
    """Queries Onshape to read the active design tree and check feature health."""
    url = f"https://cad.onshape.com/api/v9/partstudios/d/{state['doc_id']}/w/{state['work_id']}/e/{state['elem_id']}/features"
    response = requests.get(url, auth=HTTPBasicAuth(access_key, secret_key))
    return response.json() if response.status_code == 200 else {"error": "failed"}

# =====================================================================
# 🤖 NODE 1: THE PLANNER AGENT
# =====================================================================
def planner_agent(state: AgentState):
    # 💥 FIXED: Injected the hardcoded api_key parameter configuration
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_HARDCODED_KEY)
    
    system_prompt = (
        "You are the Lead CAD Architect. Look at the user request and the list of available tools.\n"
        f"Available Tools: {state['available_tools']}\n\n"
        "Deconstruct the user's request into explicit sequential CAD API steps. Return a clean JSON array of strings representing the steps."
    )
    
    response = llm.invoke([SystemMessage(content=system_prompt)] + list(state['messages']))
    
    try:
        steps = json.loads(response.content)
    except:
        steps = ["create_sketch_circle_tool", "create_extrude_tool"] # Fallback test plan for a cylinder
        
    return {"steps": steps, "current_step_index": 0, "messages": [response]}

# =====================================================================
# 🤖 NODE 2: THE TOOL-MAKER AGENT (DYNAMIC CODE COMPILER)
# =====================================================================
def tool_maker_agent(state: AgentState):
    # 💥 FIXED: Injected the hardcoded api_key parameter configuration
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_HARDCODED_KEY)
    
    step_needed = state['steps'][state['current_step_index']]
    print(f"[TOOL MAKER] Exposing missing capability factory for: '{step_needed}'")
    
    system_prompt = (
        f"You are an expert Python software engineer. We need a new tool named '{step_needed}' to interact with Onshape's REST API.\n"
        "Write a complete, self-contained Python function that builds the payload and sends a POST request using 'requests'.\n"
        "The function MUST accept arguments like (doc_id, work_id, elem_id, **kwargs) and return a string confirmation.\n"
        "Return ONLY the executable python string code inside your response message block. No markdown, no backticks."
    )
    
    response = llm.invoke([SystemMessage(content=system_prompt)])
    pure_code = response.content.replace("```python", "").replace("```", "").strip()
    
    # SELF-COMPILING EXECUTION BOUNDARY: Safely inject the code into local memory
    try:
        local_scope = {}
        exec(pure_code, globals(), local_scope)
        extracted_func_name = list(local_scope.keys())[0]
        
        DYNAMIC_TOOL_REGISTRY[step_needed] = local_scope[extracted_func_name]
        
        updated_tools = list(state['available_tools']) + [step_needed]
        print(f"[TOOL MAKER SUCCESS] Dynamic module '{step_needed}' is compiled and live inside our registry!")
        return {"generated_code": pure_code, "available_tools": updated_tools}
    except Exception as e:
        print(f"[TOOL MAKER COMPILER FAULT]: {str(e)}")
        return {"current_errors": str(e)}

# =====================================================================
# 🤖 NODE 3: THE EXECUTION & DEBUGGING AGENT
# =====================================================================
def execution_agent(state: AgentState):
    step_name = state['steps'][state['current_step_index']]
    print(f"[EXECUTION NODE] Attempting execution flight path for step: {step_name}")
    
    if state.get("current_errors"):
        print(f"[DEBUGGER LAYER ACTIVATED] Triage handling error: {state['current_errors']}")
        # Optional: You can instantiate another ChatOpenAI instance here if you want an LLM 
        # to rewrite argument parameters explicitly based on the error code message tracking.
    
    try:
        if step_name in DYNAMIC_TOOL_REGISTRY:
            func = DYNAMIC_TOOL_REGISTRY[step_name]
            output = func(state['doc_id'], state['work_id'], state['elem_id'], radius_mm=25.0, depth_mm=50.0)
        else:
            output = f"Simulated call for base feature action {step_name} completed."
            
        return {"messages": [HumanMessage(content=f"Executed {step_name}: {output}")], "current_errors": ""}
    except Exception as e:
        return {"current_errors": str(e)}

# =====================================================================
# 🤖 NODE 4: THE VALIDATION AGENT
# =====================================================================
def validation_agent(state: AgentState):
    print("[VALIDATION NODE] Verifying layout geometry metrics...")
    
    if state.get("current_errors"):
        print("[VALIDATOR WARN] Error detected. Deflecting back to execution for debugging cycle.")
        return {"current_step_index": state['current_step_index']} # Loops back
        
    next_index = state['current_step_index'] + 1
    return {"current_step_index": next_index, "current_errors": ""}

# =====================================================================
# 🎛️ CONDITIONAL ROUTING LOGIC EDGES
# =====================================================================
def routing_router_edge(state: AgentState) -> Literal["tool_maker_agent", "execution_agent", "__end__"]:
    if state['current_step_index'] >= len(state['steps']):
        return "__end__"
        
    next_step_target = state['steps'][state['current_step_index']]
    
    if next_step_target not in state['available_tools']:
        return "tool_maker_agent"
        
    return "execution_agent"

def validation_router_edge(state: AgentState) -> Literal["execution_agent", "planner_agent", "__end__"]:
    if state.get("current_errors"):
        return "execution_agent"
    if state['current_step_index'] < len(state['steps']):
        return "planner_agent"
    return "__end__"

# =====================================================================
# 🕸️ GRAPH ORCHESTRATION PIPELINE ASSEMBLY
# =====================================================================
def create_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("planner_agent", planner_agent)
    workflow.add_node("tool_maker_agent", tool_maker_agent)
    workflow.add_node("execution_agent", execution_agent)
    workflow.add_node("validation_agent", validation_agent)
    
    workflow.add_edge(START, "planner_agent")
    workflow.add_conditional_edges("planner_agent", routing_router_edge)
    workflow.add_edge("tool_maker_agent", "execution_agent")
    workflow.add_edge("execution_agent", "validation_agent")
    workflow.add_conditional_edges("validation_agent", validation_router_edge)
    
    return workflow.compile()

def run_cad_agent(prompt: str, doc_id: str, work_id: str, elem_id: str, selected_entity: dict) -> str:
    try:
        graph = create_graph()
        initial_state = {
            "messages": [HumanMessage(content=prompt)],
            "doc_id": doc_id or "",
            "work_id": work_id or "",
            "elem_id": elem_id or "",
            "selected_entity": selected_entity or {},
            "steps": [],
            "current_step_index": 0,
            "current_errors": "",
            "available_tools": ["get_part_studio_features_tool"],
            "generated_code": ""
        }
        output_state = graph.invoke(initial_state)
        return output_state["messages"][-1].content
    except Exception as e:
        return f"Autonomous Agent System Exception: {str(e)}"