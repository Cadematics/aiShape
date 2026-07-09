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
    
    system_prompt = (
        "You are an expert AI CAD co-pilot integrated directly within Onshape. "
        f"You are currently analyzing Document ID: {doc_id}. "
    )
    
    if selected_entity:
        system_prompt += f"The user has highlighted a 3D geometry {selected_entity.get('entityType')} with ID: {selected_entity.get('id')}."
    else:
        system_prompt += "No specific 3D geometry is currently selected."

    full_messages = [SystemMessage(content=system_prompt)] + list(messages)
    
    # 💥 CRITICAL CHECK: Verify API key existence explicitly before calling OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[CRITICAL ERROR] OPENAI_API_KEY environment variable is MISSING on Render!")
        raise ValueError("OPENAI_API_KEY environment variable is missing on the server configuration.")

    print(f"[DEBUG] Attempting live hand-off to OpenAI GPT-4o with key length: {len(api_key)}")
    
    try:
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            api_key=api_key
        )
        response = llm.invoke(full_messages)
        print("[DEBUG] OpenAI responded successfully!")
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
    # Safe try-catch wrapper for graph execution
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
        print(f"[CRITICAL EXCEPTION inside run_cad_agent execution]: {str(e)}")
        return f"Backend AI Execution Engine Error: {str(e)}"
    



    