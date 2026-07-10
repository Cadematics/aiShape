
access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"
 


import os
import json
import requests
from requests.auth import HTTPBasicAuth
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool

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
    
    
    
    if not access_key or not secret_key:
        return "Error: Onshape API credentials are missing from Render's environment settings."

    url = f"https://cad.onshape.com/api/documents/d/{doc_id}/w/{work_id}/elements"
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, auth=HTTPBasicAuth(access_key, secret_key))
        if response.status_code != 200:
            return f"Failed to retrieve elements. Status: {response.status_code}"
        
        elements_data = response.json()
        summary = [{"name": e.get("name"), "id": e.get("id"), "type": e.get("elementType")} for e in elements_data]
        return f"Found the following elements inside this document workspace:\n{json.dumps(summary, indent=2)}"
    except Exception as e:
        return f"Error connecting to Onshape endpoint: {str(e)}"


# =====================================================================
# 🛠️ TOOL 2: Get Features (Construction Planes, Sketches, etc.)
# =====================================================================
@tool
def get_part_studio_features(state: dict) -> str:
    """Use this tool to fetch the feature list (including construction planes like Top, Front, Right) from the active Part Studio."""
    doc_id = state.get('doc_id')
    work_id = state.get('work_id')
    elem_id = state.get('elem_id')  # Active Part Studio ID
    
    
    
    if not access_key or not secret_key:
        return "Error: Onshape API credentials missing."

    url = f"https://cad.onshape.com/api/v9/partstudios/d/{doc_id}/w/{work_id}/e/{elem_id}/features"
    headers = {"Accept": "application/json;charset=UTF-8"}
    
    try:
        response = requests.get(url, headers=headers, auth=HTTPBasicAuth(access_key, secret_key))
        if response.status_code != 200:
            return f"Failed to get features. Status: {response.status_code}"
            
        features_data = response.json()
        features = features_data.get("features", [])
        
        # Clean down the feature output focusing heavily on construction planes
        summary = []
        for f in features:
            summary.append({
                "name": f.get("name"),
                "id": f.get("id"),
                "featureType": f.get("featureType") # e.g., 'openDefaultCurves' (planes) or 'newSketch'
            })
            
        return f"Active Feature Tree & Construction Planes:\n{json.dumps(summary, indent=2)}"
    except Exception as e:
        return f"Error gathering features: {str(e)}"


# =====================================================================
# 🛠️ TOOL 3: Create Parametric Sketch Circle
# =====================================================================
@tool
def create_sketch_circle_tool(plane_name_or_id: str, radius_mm: float, state: dict) -> str:
    """Use this tool to create a sketch containing a circle. Pass the selected plane name/id (e.g., 'Top', 'Front', or a specific feature ID) and radius."""
    doc_id = state.get('doc_id')
    work_id = state.get('work_id')
    elem_id = state.get('elem_id')
    

    
    radius_m = radius_mm / 1000.0
    url = f"https://cad.onshape.com/api/v9/partstudios/d/{doc_id}/w/{work_id}/e/{elem_id}/features"

    # Clean formatting for planes or custom feature queries
    if plane_name_or_id.lower() in ["top", "front", "right"]:
        formatted_plane = plane_name_or_id.capitalize()
        query_string = f'query=qCreatedBy(makeId("{formatted_plane}"), EntityType.FACE);'
    else:
        query_string = f'query=qCreatedBy(makeId("{plane_name_or_id}"), EntityType.FACE);'

    payload = {
        "feature": {
            "btType": "BTMSketch-151",
            "featureType": "newSketch",
            "name": f"AI Circle ({radius_mm}mm)",
            "parameters": [
                {
                    "btType": "BTMParameterQueryList-148",
                    "parameterId": "sketchPlane",
                    "queries": [
                        {
                            "btType": "BTMIndividualQuery-138",
                            "queryString": query_string
                        }
                    ]
                }
            ],
            "entities": [
                {
                    "btType": "BTMSketchCurve-4",
                    "centerId": "center",
                    "type": "circle",
                    "geometry": {
                        "btType": "BTCircle-115",
                        "radius": radius_m,
                        "x": 0.0,
                        "y": 0.0
                    }
                }
            ]
        }
    }

    headers = {"Accept": "application/json;charset=UTF-8", "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, auth=HTTPBasicAuth(access_key, secret_key))
        if response.status_code in [200, 201]:
            return f"Success! Created sketch containing a {radius_mm}mm radius circle on plane '{plane_name_or_id}'."
        return f"Onshape rejected feature generation: {response.text}"
    except Exception as e:
        return f"Network exception: {str(e)}"


# =====================================================================
# 🧠 Multi-Tool LangGraph Node
# =====================================================================
def geometry_agent_node(state: AgentState):
    llm = ChatOpenAI(
        model="gpt-4o", 
        temperature=0, 
        api_key=openai_api_key
    )
    
    # Register our 3 tool capabilities to the agent's brain layout
    llm_with_tools = llm.bind_tools([get_document_elements, get_part_studio_features, create_sketch_circle_tool])
    
    system_msg = SystemMessage(
        "You are an intelligent CAD assistant with direct access to an Onshape document workspace tree.\n\n"
        "Your guidelines:\n"
        "1. If the user asks for construction planes or current features, call 'get_part_studio_features'.\n"
        "2. If the user asks to draw or sketch a circle on a specific plane, map their chosen target plane name or ID and execute 'create_sketch_circle_tool'.\n"
        "3. Always communicate clearly what actions you are running."
    )
    
    response = llm_with_tools.invoke([system_msg] + list(state['messages']))
    
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_args = tool_call['args']
        
        if tool_call['name'] in ['get_document_elements', 'get_part_studio_features']:
            tool_args = {"state": state}
        else:
            tool_args['state'] = state
            
        # Dynamically execute chosen tracking actions
        if tool_call['name'] == 'get_document_elements':
            return {"messages": [HumanMessage(content=get_document_elements.invoke(tool_args))]}
        elif tool_call['name'] == 'get_part_studio_features':
            return {"messages": [HumanMessage(content=get_part_studio_features.invoke(tool_args))]}
        elif tool_call['name'] == 'create_sketch_circle_tool':
            return {"messages": [HumanMessage(content=create_sketch_circle_tool.invoke(tool_args))]}
            
    return {"messages": [response]}

def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", geometry_agent_node)
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
            "selected_entity": selected_entity or {}
        }
        output_state = graph.invoke(initial_state)
        return output_state["messages"][-1].content
    except Exception as e:
        return f"Agent Runtime Error: {str(e)}"