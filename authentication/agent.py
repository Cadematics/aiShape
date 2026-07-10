import os
import requests
from requests.auth import HTTPBasicAuth
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool

access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_key="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" 


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    doc_id: str
    work_id: str
    elem_id: str
    selected_entity: dict





# 🌟 1. NATIVE PRODUCTION TOOL: Create Sketch Entity


@tool
def create_sketch_circle_tool(plane_id: str, radius_mm: float, state: dict) -> str:
    """Use this tool when the user explicitly requests to create a sketch of a circle."""
    doc_id = state.get('doc_id')
    work_id = state.get('work_id')
    elem_id = state.get('elem_id')
    
    access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
    secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
    
    if not access_key or not secret_key:
        return "Error: Onshape credentials are missing from the Render environment parameters."

    # Standard Onshape REST API handles geometric coordinate tokens strictly in meters
    radius_m = radius_mm / 1000.0
    url = f"https://cad.onshape.com/api/v9/partstudios/d/{doc_id}/w/{work_id}/e/{elem_id}/features"

    # 💥 THE FIX: Build an absolute evaluation literal for default or custom targets
    # If the plane_id is a standard base reference (top, front, right), escape its naming wrap string
    if plane_id.lower() in ["top", "front", "right"]:
        formatted_plane_name = plane_id.capitalize()
        query_string = f'query=qCreatedBy(makeId("{formatted_plane_name}"), EntityType.FACE);'
    else:
        # Otherwise, treat it as a custom selected face entity topology token from the canvas viewport
        query_string = f'query=qCreatedBy(makeId("{plane_id}"), EntityType.FACE);'

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
                            "queryString": query_string  # <--- Cleanly injected correctly formatted evaluation literal
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
    
    response = requests.post(
        url, 
        json=payload, 
        headers=headers, 
        auth=requests.auth.HTTPBasicAuth(access_key, secret_key)
    )
    
    if response.status_code in [200, 201]:
        return f"Successfully updated your workspace! Drawn a {radius_mm}mm radius circle on plane '{plane_id}'."
    else:
        return f"Onshape API Rejected Request: {response.text}"


# 🌟 2. NATIVE PRODUCTION TOOL: Extrude Feature
@tool
def create_extrude_tool(depth_mm: float, state: dict) -> str:
    """Use this tool when the user wants to extrude or add depth to a sketch element."""
    doc_id = state.get('doc_id')
    work_id = state.get('work_id')
    elem_id = state.get('elem_id')
    
    print(f'inside create_extrude_tool: doc_id={doc_id}, work_id={work_id}, elem_id={elem_id}, depth_mm={depth_mm}')


    access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
    secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"    
    
    url = f"https://cad.onshape.com/api/v9/partstudios/d/{doc_id}/w/{work_id}/e/{elem_id}/features"
    depth_m = depth_mm / 1000.0

    payload = {
        "feature": {
            "btType": "BTMFeature-134",
            "featureType": "extrude",
            "name": f"AI Extrude ({depth_mm}mm)",
            "parameters": [
                {
                    "btType": "BTMParameterEnum-105",
                    "parameterId": "operationType",
                    "value": "NEW"
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "depth",
                    "expression": f"{depth_m}*m"
                },
                {
                    "btType": "BTMParameterQueryList-148",
                    "parameterId": "entities",
                    "queries": [
                        {
                            "btType": "BTMIndividualQuery-138",
                            "queryString": "query=qLastChangedTopology(EntityType.FACE);" # Grabs the last created sketch region
                        }
                    ]
                }
            ]
        }
    }
    
    headers = {"Accept": "application/json;charset=UTF-8", "Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers, auth=HTTPBasicAuth(access_key, secret_key))
    
    if response.status_code in [200, 201]:
        return f"Successfully generated solid geometry! Extruded the cylinder base by {depth_mm}mm."
    return f"Extrude failed: {response.text}"


# 🧠 3. Core Node Wireframe
def geometry_agent_node(state: AgentState):
    llm = ChatOpenAI(
        model="gpt-4o", 
        temperature=0, 
        api_key=openai_key
    )
    llm_with_tools = llm.bind_tools([create_sketch_circle_tool, create_extrude_tool])
    
    selected_entity = state.get('selected_entity') or {}
    face_id = selected_entity.get('id')
    
    system_msg = SystemMessage(
        "You are the Geometry Specialist Agent for aiShape. You command live production Onshape API tools.\n"
        f"Active Selection Target Face: '{face_id or 'None'}'\n"
        "Execute the tools matching the user parameters. If they ask for a circle sketch and an extrude, chain the response calls."
    )
    
    response = llm_with_tools.invoke([system_msg] + list(state['messages']))
    
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_args = tool_call['args']
        tool_args['state'] = state
        
        if tool_call['name'] == 'create_sketch_circle_tool':
            tool_output = create_sketch_circle_tool.invoke(tool_args)
            return {"messages": [HumanMessage(content=tool_output)]}
        elif tool_call['name'] == 'create_extrude_tool':
            tool_output = create_extrude_tool.invoke(tool_args)
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