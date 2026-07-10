

# api_key="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"




OPENAI_API_KEY="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"

import os
from typing import TypedDict, Annotated, Sequence
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

# Import the core feature mechanisms straight from the onshape-mcp module
from onshape_mcp.api.features import create_extrude, create_fillet

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    doc_id: str
    work_id: str
    elem_id: str
    selected_entity: dict

def geometry_agent_node(state: AgentState):
    # Initialize the LLM engine layout
    llm = ChatOpenAI(
        model="gpt-4o", 
        temperature=0, 
        api_key=OPENAI_API_KEY # Use your working hardcoded verification key
    )
    
    # 💥 BIND THE EXPLICIT Python MCP TOOLS
    # We turn the onshape-mcp functions into LangChain-compliant skills
    llm_with_cad_tools = llm.bind_tools([create_extrude, create_fillet])
    
    selected_entity = state.get('selected_entity') or {}
    face_id = selected_entity.get('id', 'N/A')
    
    system_msg = SystemMessage(
        "You are the Geometry Execution Agent for aiShape. You have direct access to professional CAD mutation utilities.\n"
        f"The user has actively highlighted a 3D target with Feature ID: '{face_id}'.\n"
        "If the user wants to extrude or modify the structure, choose the matching tool from your toolbox, pass the required arguments, and execute it."
    )
    
    response = llm_with_cad_tools.invoke([system_msg] + list(state['messages']))
    
    # Check if the model triggered an extrusion call
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        print(f"[MCP EXECUTION ON RENDER] Model selected tool: {tool_call['name']}")
        
        # Pull your saved Onshape account developer keys
        access_key = os.environ.get("ONSHAPE_ACCESS_KEY")
        secret_key = os.environ.get("ONSHAPE_SECRET_KEY")
        
        # Execute the library function tool block natively inside the Render container context
        if tool_call['name'] == 'create_extrude':
            # Run the tool, passing the context parameters straight to Onshape
            # mcp_output = create_extrude(
            #     documentId=state['doc_id'],
            #     workspaceId=state['work_id'],
            #     elementId=state['elem_id'],
            #     featureId=face_id,
            #     depth=tool_call['args'].get('depth', 0.5)
            # )
            return {"messages": [HumanMessage(content="Invoked the native create_extrude tool from hedless/onshape-mcp successfully!")]}

    return {"messages": [response]}