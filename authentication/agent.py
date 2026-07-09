

# api_key="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"

import os
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    doc_id: str
    work_id: str
    elem_id: str
    selected_entity: dict

def call_model(state: AgentState):
    messages = state['messages']
    doc_id = state['doc_id']
    selected_entity = state['selected_entity']
    
    # 🌟 CRITICAL REWRITE: Force the LLM to use the data injected here
    system_prompt = (
        "You are an expert AI CAD co-pilot integrated directly within an active Onshape modeling window.\n"
        "Your primary job right now is to look at the telemetry data provided below and answer the user's questions about their current workspace or active selections accurately.\n\n"
        "--- ACTIVE CONTEXT GEOMETRY DATABASES ---\n"
        f"Active Onshape Document ID: {doc_id or 'Unknown'}\n"
    )
    
    if selected_entity:
        system_prompt += (
            "The user has actively clicked on a 3D geometric entity in the canvas viewport. Here is the metadata:\n"
            f"- Topological Type: {selected_entity.get('entityType', 'UNKNOWN')}\n"
            f"- Unique Entity ID: {selected_entity.get('id', 'N/A')}\n\n"
            "CRITICAL INSTRUCTION: If the user asks for the ID, type, or information about what they selected, read the data above and repeat it back to them explicitly. Do not apologize or say you cannot access it."
        )
    else:
        system_prompt += "No specific 3D geometry is currently highlighted on the viewport canvas screen."

    full_messages = [SystemMessage(content=system_prompt)] + list(messages)
    
    # Using your validated working connection mechanism
    api_key="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"
    
    print(f"[DEBUG] Invoking GPT-4o with strict context instructions. Has Selection: {bool(selected_entity)}")
    
    try:
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0, # Keeps the model grounded to strict facts rather than creative guessing
            api_key=api_key
        )
        response = llm.invoke(full_messages)
        return {"messages": [response]}
    except Exception as e:
        print(f"[CRITICAL EXCEPTION inside call_model]: {str(e)}")
        raise e

def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
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
        return f"Backend AI Execution Engine Error: {str(e)}"