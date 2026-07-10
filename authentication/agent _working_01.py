
access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"
 


import os
import requests
from requests.auth import HTTPBasicAuth
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
import json

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    doc_id: str
    work_id: str
    elem_id: str
    selected_entity: dict

# =====================================================================
# 🛠️ TOOL 1: Get All Elements in Document
# =====================================================================
@tool
def get_document_elements(state: dict) -> str:
    """Use this tool to fetch all elements (tabs, Part Studios, Assemblies) inside the current Onshape document workspace."""
    doc_id = state.get('doc_id')
    work_id = state.get('work_id')
    
    # access_key = os.environ.get("ONSHAPE_ACCESS_KEY")
    # secret_key = os.environ.get("ONSHAPE_SECRET_KEY")
    
    if not access_key or not secret_key:
        return "Error: Onshape API credentials are missing from Render's environment settings."

    # Document Elements Endpoint
    url = f"https://cad.onshape.com/api/documents/d/{doc_id}/w/{work_id}/elements"
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, auth=HTTPBasicAuth(access_key, secret_key))
        if response.status_code != 200:
            return f"Failed to retrieve elements. Onshape API returned status code: {response.status_code}"
        
        elements_data = response.json()
        
        # Clean and simplify the output for the LLM to save token context window space
        summary = []
        for elem in elements_data:
            summary.append({
                "name": elem.get("name"),
                "id": elem.get("id"),
                "type": elem.get("elementType") # e.g., 'PARTSTUDIO' or 'ASSEMBLY'
            })
            
        return f"Found the following elements inside this document workspace:\n{json.dumps(summary, indent=2)}"
    except Exception as e:
        return f"Error connecting to Onshape endpoint: {str(e)}"


# =====================================================================
# 🧠 LangGraph Node Setup
# =====================================================================
def geometry_agent_node(state: AgentState):
    llm = ChatOpenAI(
        model="gpt-4o", 
        temperature=0, 
        api_key=openai_api_key
    )
    
    # Bind our first discovery tool
    llm_with_tools = llm.bind_tools([get_document_elements])
    
    system_msg = SystemMessage(
        "You are the structural coordinator agent for aiShape.\n"
        "If the user asks what elements, tabs, or modeling environments exist in this project document, use the 'get_document_elements' tool to find out."
    )
    
    response = llm_with_tools.invoke([system_msg] + list(state['messages']))
    
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        if tool_call['name'] == 'get_document_elements':
            # Inject the shared state tracking parameters
            tool_output = get_document_elements.invoke({"state": state})
            return {"messages": [HumanMessage(content=tool_output)]}
            
    return {"messages": [response]}

def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", geometry_agent_node)
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)
    return workflow.compile()

def run_cad_agent(prompt: str, doc_id: str, work_id: str, elem_id: str, selected_entity: dict) -> str:
    try:
        import json # Local import block validation
        graph = create_graph()
        initial_state = {
            "messages": [HumanMessage(content=prompt)],
            "doc_id": doc_id or "",
            "work_id": work_id or "",
            "elem_id": elem_id or "",
            "selected_entity": selected_entity or {}
        }
        output_state = graph.invoke(initial_state)
        return output_state["messages"][-1].content
    except Exception as e:
        return f"Agent Runtime Error: {str(e)}"