import os
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

# 1. Define the state structure that flows through our graph nodes
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    doc_id: str
    work_id: str
    elem_id: str
    selected_entity: dict

# 2. Initialize the LLM Engine (GPT-4o)
def get_llm():
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0, # Low temperature ensures strict engineering reasoning
        api_key=os.environ.get("OPENAI_API_KEY")
    )

# 3. Define our primary Reasoning Node
def call_model(state: AgentState):
    messages = state['messages']
    doc_id = state['doc_id']
    selected_entity = state['selected_entity']
    
    # Inject active workspace context directly into the system prompt
    system_prompt = (
        "You are an expert AI CAD co-pilot integrated directly within Onshape. "
        f"You are currently analyzing Document ID: {doc_id}. "
    )
    
    if selected_entity:
        system_prompt += f"The user has highlighted a 3D geometry {selected_entity.get('entityType')} with ID: {selected_entity.get('id')}."
    else:
        system_prompt += "No specific 3D geometry is currently selected."

    # Prepend the system instructions to the current conversation history
    full_messages = [SystemMessage(content=system_prompt)] + list(messages)
    
    llm = get_llm()
    response = llm.invoke(full_messages)
    
    return {"messages": [response]}

# 4. Build and Compile the LangGraph State Machine
def create_graph():
    workflow = StateGraph(AgentState)
    
    # Add our nodes
    workflow.add_node("agent", call_model)
    
    # Establish execution paths
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)
    
    return workflow.compile()

# 5. The Execution Entrypoint for your Django Views
def run_cad_agent(prompt: str, doc_id: str, work_id: str, elem_id: str, selected_entity: dict) -> str:
    graph = create_graph()
    
    # Construct the initial state input dictionary
    initial_state = {
        "messages": [HumanMessage(content=prompt)],
        "doc_id": doc_id or "",
        "work_id": work_id or "",
        "elem_id": elem_id or "",
        "selected_entity": selected_entity or {}
    }
    
    # Run the state execution loop
    output_state = graph.invoke(initial_state)
    
    # Extract the final message response from the graph
    final_message = output_state["messages"][-1]
    return final_message.content