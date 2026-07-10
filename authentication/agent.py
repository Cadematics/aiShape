
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

OPENAI_HARDCODED_KEY = openai_api_key

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    doc_id: str
    work_id: str
    elem_id: str
    selected_entity: dict
    active_payloads: List[dict]

# =====================================================================
# 🛠️ TOOL 1: GENERIC ONSHAPE API EXECUTOR (Matches onshape_api_call)
# =====================================================================
@tool
def onshape_api_call(method: str, path: str, body: dict) -> str:
    """
    Executes a generic HTTP request directly against the Onshape REST API.
    Use this to create documents, elements, sketches, or features by providing the exact API path and body.
    """
    # access_key = os.environ.get("ONSHAPE_ACCESS_KEY")
    # secret_key = os.environ.get("ONSHAPE_SECRET_KEY")
    
    url = f"https://cad.onshape.com/api{path}"
    headers = {
        "Accept": "application/json;charset=UTF-8",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            json=body,
            headers=headers,
            auth=HTTPBasicAuth(access_key, secret_key)
        )
        return f"Status {response.status_code} Response:\n{json.dumps(response.json(), indent=2)}"
    except Exception as e:
        return f"HTTP Request Failure: {str(e)}"

# =====================================================================
# 🛠️ TOOL 2: FEATURESCRIPT EVALUATOR (Matches evalFeatureScript)
# =====================================================================
@tool
def evaluate_featurescript(doc_id: str, work_id: str, elem_id: str, script_source: str) -> str:
    """
    Evaluates a FeatureScript expression in the context of a given Part Studio.
    Use this to look up transient IDs, evaluate queries, or locate faces and sketch regions.
    """
    # access_key = os.environ.get("ONSHAPE_ACCESS_KEY")
    # secret_key = os.environ.get("ONSHAPE_SECRET_KEY")
    
    url = f"https://cad.onshape.com/api/v15/partstudios/d/{doc_id}/w/{work_id}/e/{elem_id}/featurescript"
    
    payload = {
        "script": script_source,
        "queries": []
    }
    
    try:
        response = requests.post(url, json=payload, auth=HTTPBasicAuth(access_key, secret_key))
        return f"FeatureScript Output:\n{json.dumps(response.json(), indent=2)}"
    except Exception as e:
        return f"FeatureScript Execution Failure: {str(e)}"

# =====================================================================
# 🤖 DISCOVERY & COORDINATION NODE
# =====================================================================
def core_agent_node(state: AgentState):
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_HARDCODED_KEY)
    
    # Bind the highly flexible generic tools
    llm_with_tools = llm.bind_tools([onshape_api_call, evaluate_featurescript])
    
    system_msg = SystemMessage(
        "You are an elite autonomous Onshape CAD agent modeled after a production MCP architecture.\n"
        "Instead of relying on rigid, pre-built functions, you manipulate geometry by making direct, structured REST API payloads.\n\n"
        "--- CAD STRATEGY GUIDELINES ---\n"
        "1. To create a new Document, use 'onshape_api_call' with POST to '/documents'.\n"
        "2. To add a feature (sketch, extrude, etc.), POST to '/v9/partstudios/d/DOC_ID/w/WORK_ID/e/ELEM_ID/features'.\n"
        "3. When you need to chain an extrusion to a newly created sketch, check for transit IDs or evaluate queries using 'evaluate_featurescript'.\n"
        f"Active Document Scope Context: Doc ID: {state.get('doc_id') or 'Pending New Creation'}\n"
    )
    
    response = llm_with_tools.invoke([system_msg] + list(state['messages']))
    
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        args = tool_call['args']
        
        if tool_call['name'] == 'onshape_api_call':
            output = onshape_api_call.invoke(args)
            return {"messages": [HumanMessage(content=output)]}
        elif tool_call['name'] == 'evaluate_featurescript':
            # Ensure runtime context maps are injected
            args['doc_id'] = args.get('doc_id') or state['doc_id']
            args['work_id'] = args.get('work_id') or state['work_id']
            args['elem_id'] = args.get('elem_id') or state['elem_id']
            output = evaluate_featurescript.invoke(args)
            return {"messages": [HumanMessage(content=output)]}
            
    return {"messages": [response]}

def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", core_agent_node)
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)
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
            "active_payloads": []
        }
        output_state = graph.invoke(initial_state)
        return output_state["messages"][-1].content
    except Exception as e:
        return f"Agent Error: {str(e)}"