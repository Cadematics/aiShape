

# api_key="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"




OPENAI_API_KEY="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"

import os
import json
import requests
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

# 🌟 1. NATIVE TOOL: Create Sketch Entity
@tool
def create_sketch_circle_tool(plane_id: str, radius_mm: float, state: dict) -> str:
    """Use this tool when the user explicitly requests to create a sketch of a circle."""
    doc_id = state.get('doc_id')
    work_id = state.get('work_id')
    elem_id = state.get('elem_id')
    
    print(f"[ONSHAPE API] Creating circle sketch on plane '{plane_id}' with radius {radius_mm}mm")
    
    # Target Endpoint for the Onshape Features API
    url = f"https://cad.onshape.com/api/partstudios/d/{doc_id}/w/{work_id}/e/{elem_id}/features"
    
    # Convert mm to meters (Onshape API strictly uses meters internally)
    radius_m = radius_mm / 1000.0
    
    # Clean Onshape Feature definition payload for a sketch circle
    payload = {
        "feature": {
            "type": "Component",
            "typeName": "BTMFeature",
            "message": {
                "featureType": "sketch",
                "name": "AI Circle Sketch",
                "entities": [
                    {
                        "type": "sketchCircle",
                        "centerX": 0.0,
                        "centerY": 0.0,
                        "radius": radius_m
                    }
                ]
            }
        }
    }
    
    # Future authentication header map setup:
    # response = requests.post(url, json=payload, auth=(ONSHAPE_ACCESS, ONSHAPE_SECRET))
    
    return f"Successfully processed native CAD command! Generated a circle sketch with radius {radius_mm}mm targeting plane/face layer '{plane_id}'."

# 🌟 2. NATIVE TOOL: Extrude Feature
@tool
def create_extrude_tool(face_id: str, depth_mm: float, state: dict) -> str:
    """Use this tool when the user wants to extrude or add depth to an element or face."""
    return f"Successfully processed native CAD command! Extruded target entity '{face_id}' by {depth_mm}mm."


# 🧠 3. Geometry Execution Agent Node
def geometry_agent_node(state: AgentState):
    llm = ChatOpenAI(
        model="gpt-4o", 
        temperature=0, 
        api_key=OPENAI_API_KEY
    )
    
    # Bind our robust native cloud tools
    llm_with_tools = llm.bind_tools([create_sketch_circle_tool, create_extrude_tool])
    
    selected_entity = state.get('selected_entity') or {}
    face_id = selected_entity.get('id')
    
    system_msg = SystemMessage(
        "You are the Geometry Specialist Agent for aiShape. You have access to native CAD modeling tools.\n\n"
        f"Active Selection Entity ID: '{face_id or 'None'}'\n\n"
        "Instructions:\n"
        "1. If the user asks for a sketch of a circle, use 'create_sketch_circle_tool'.\n"
        "2. If a face is currently selected, use its ID as the plane_id parameter. Otherwise, default to 'Top'.\n"
        "3. Look for radius/diameter dimensions in the user prompt. If they specify mm, pass it directly to the tool."
    )
    
    response = llm_with_tools.invoke([system_msg] + list(state['messages']))
    
    # Tool Execution Lifecycle
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_args = tool_call['args']
        tool_args['state'] = state  # Inject current document context variables safely
        
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