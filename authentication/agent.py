

# api_key="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"

import os
from typing import TypedDict, Annotated, Sequence, Literal
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool


OPENAI_API_KEY="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"

import os
import requests
from typing import TypedDict, Annotated, Sequence, Literal
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool

# 1. Define global shared state across the agent network
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    doc_id: str
    work_id: str
    elem_id: str
    selected_entity: dict
    next_agent: str

# 2. Define a Secure Cloud Tool for the Geometry Agent
@tool
def execute_extrude_operation(face_id: str, depth_mm: float, doc_id: str, work_id: str, elem_id: str) -> str:
    """Invokes an extrude modification operation on a specific topological face ID inside an Onshape document."""
    print(f"[CLOUD TOOL] Executing extrude on face {face_id} by {depth_mm}mm")
    
    # We will use your existing authenticated Onshape tokens here to hit the API
    # For now, we print out the confirmation payload data for tracking
    return f"Successfully sent API instruction to Onshape: Extruded face '{face_id}' by {depth_mm}mm inside element {elem_id[:6]}."


# 3. Define Agent Node: The Router/Triage Supervisor
def triage_agent_node(state: AgentState):
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_API_KEY) # Your working hardcoded token
    
    system_msg = SystemMessage(
        "You are the Lead Triage Agent for aiShape. Review the user's prompt carefully.\n"
        "If the user wants to make a physical structural modification or edit geometry (like an extrude), "
        "set the state variable 'next_agent' to 'geometry_agent'. Do not call the tools yourself.\n"
        "If it is a general question, answer them directly and do not forward the state."
    )
    
    response = llm.invoke([system_msg] + list(state['messages']))
    
    # Simple rule-based intent parsing for routing safety
    next_step = END
    prompt_text = state['messages'][-1].content.lower()
    if "extrude" in prompt_text or "modify" in prompt_text or "id" in prompt_text:
        next_step = "geometry_agent"
        
    return {"messages": [response], "next_agent": next_step}


# 4. Define Agent Node: The Geometry Specialist Agent
def geometry_agent_node(state: AgentState):
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_API_KEY)
    
    selected_entity = state.get('selected_entity') or {}
    face_id = selected_entity.get('id', 'N/A')
    
    system_msg = SystemMessage(
        "You are the Geometry Specialist Agent for aiShape. You have access to the 'execute_extrude_operation' tool.\n"
        f"The user has actively highlighted Face ID: '{face_id}'.\n"
        "Use the tool parameters to process the user's modeling request."
    )
    
    # Bind the structural tool logic directly to the model context engine
    llm_with_tools = llm.bind_tools([execute_extrude_operation])
    response = llm_with_tools.invoke([system_msg] + list(state['messages']))
    
    # If the model decides to use the tool, simulate execution immediately
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        # Run tool function execution locally inside the cloud framework
        tool_output = execute_extrude_operation.invoke({
            "face_id": face_id,
            "depth_mm": tool_call['args'].get('depth_mm', 10.0),
            "doc_id": state['doc_id'],
            "work_id": state['work_id'],
            "elem_id": state['elem_id']
        })
        return {"messages": [HumanMessage(content=tool_output)], "next_agent": END}
        
    return {"messages": [response], "next_agent": END}


# 5. Build Dynamic Conditional Edge Router Link
def router_edge(state: AgentState) -> Literal["geometry_agent", "__end__"]:
    if state.get("next_agent") == "geometry_agent":
        return "geometry_agent"
    return "__end__"


# 6. Build and Compile the Multi-Agent Flow Network
def create_graph():
    workflow = StateGraph(AgentState)
    
    # Establish network node anchors
    workflow.add_node("triage_agent", triage_agent_node)
    workflow.add_node("geometry_agent", geometry_agent_node)
    
    # Set up routing rules
    workflow.add_edge(START, "triage_agent")
    workflow.add_conditional_edges("triage_agent", router_edge)
    workflow.add_edge("geometry_agent", END)
    
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
        return f"Multi-Agent Execution Error: {str(e)}"