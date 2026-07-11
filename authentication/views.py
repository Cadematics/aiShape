access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"


import json
import asyncio
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from langchain_core.messages import HumanMessage, AIMessage
from .agent import create_graph
from .mcp_client import mcp_manager  # Import our subprocess singleton manager

@csrf_exempt
def api_chat(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        user_prompt = data.get('prompt', '')
        cad_context = data.get('context', {})
        
        # Human-in-the-Loop tracking parameters passed from the React component
        has_approved = data.get('approved', None)
        pending_action = data.get('pendingAction', None)
        chat_history_raw = data.get('history', [])
        
        doc_id = cad_context.get('documentId')
        work_id = cad_context.get('workspaceId')
        elem_id = cad_context.get('elementId')
        
        # 1. Initialize background stdio sub-processes dynamically
        async_to_sync(mcp_manager.initialize)()
        available_tools = async_to_sync(mcp_manager.get_tools)()
        
        # 2. Reconstruct session interaction tokens
        messages = []
        for msg in chat_history_raw:
            if msg['sender'] == 'user':
                messages.append(HumanMessage(content=msg['text']))
            else:
                messages.append(AIMessage(content=msg['text']))
                
        if user_prompt:
            messages.append(HumanMessage(content=user_prompt))
            
        # 3. Handle the Human-in-the-Loop response step path
        if has_approved is True and pending_action:
            print(f"[AGENT CORE] User approved execution for tool: {pending_action['name']}")
            
            # Execute approved command directly against the running subprocess stdio channels
            tool_output = async_to_sync(mcp_manager.call_tool)(
                name=pending_action['name'], 
                arguments=pending_action['arguments']
            )
            
            # Append execution details back to history context loops
            messages.append(HumanMessage(content=f"System Notification: Tool execution response data: {json.dumps(tool_output)}"))
            has_approved = None
            pending_action = None
            
        elif has_approved == False:
            # User rejected the proposed action plan
            messages.append(HumanMessage(content="System Notification: The user rejected this operation proposal. Alter strategies."))
            has_approved = None
            pending_action = None

        # 4. Invoke the LangGraph State Engine Instance
        graph = create_graph()
        initial_state = {
            "messages": messages,
            "doc_id": doc_id or "",
            "work_id": work_id or "",
            "elem_id": elem_id or "",
            "available_tools": available_tools,
            "next_action": pending_action,
            "approval_granted": has_approved,
            "final_reply": None
        }
        
        output_state = graph.invoke(initial_state)
        
        # 5. Formulate the response object layout based on state output flags
        if output_state.get("next_action"):
            action = output_state["next_action"]
            return JsonResponse({
                "status": "requires_approval",
                "message": f"🤖 **Plan Proposal:** I want to run the tool `{action['name']}` with options: {json.dumps(action['arguments'])}. Do you approve?",
                "pendingAction": action
            })
            
        return JsonResponse({
            "status": "success",
            "reply": output_state.get("final_reply", "Task processed successfully.")
        })
        
    except Exception as e:
        print(f"[CRITICAL CHAT EXCEPTION]: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)