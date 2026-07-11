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
import os
import requests
import json


def onshape_callback(request):
    # 1. Catch the unique authorization code sent by Onshape
    auth_code = request.GET.get('code')
    
    if not auth_code:
        return JsonResponse({'status': 'error', 'message': 'No authorization code detected.'}, status=400)
    
    # 2. Fetch and sanitize environment keys (strip trailing whitespaces/newlines)
    client_id = os.environ.get('ONSHAPE_CLIENT_ID', '').strip()
    client_secret = os.environ.get('ONSHAPE_CLIENT_SECRET', '').strip()
    
    # 💥 DEBUG PRINT: Check Render's log console to ensure these print lengths > 0
    print(f"[DEBUG] Extracted Client ID Length: {len(client_id)}")
    print(f"[DEBUG] Extracted Client Secret Length: {len(client_secret)}")
    
    # 3. Reconstruct the dynamic redirect_uri exactly as requested by the browser
    # This prevents byte-for-byte string mismatches automatically
    actual_redirect_uri = request.build_absolute_uri(request.path)
    print(f"[DEBUG] Matching Redirect URI used: {actual_redirect_uri}")

    # 4. Prepare the explicit exchange payload
    token_url = "https://oauth.onshape.com/oauth/token"
    payload = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': actual_redirect_uri,
    }
    
    # Enforce standard form encoding headers
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    # 5. Outbound request execution
    response = requests.post(token_url, data=payload, headers=headers)
    
    print(f"[DEBUG] Onshape Token Endpoint Response Status: {response.status_code}")
    print(f"[DEBUG] Onshape Token Endpoint Body: {response.text}")
    
    if response.status_code == 200:
        tokens = response.json()
        return JsonResponse({
            'status': 'success', 
            'message': 'Authenticated with Onshape successfully!',
            'access_token_preview': tokens.get('access_token')[:10] + "..."
        })
    else:
        # Return Onshape's error parameters directly to the window for triage
        return JsonResponse({
            'status': 'handshake_failed',
            'onshape_error_payload': response.json(),
            'attempted_payload_meta': {
                'client_id_filled': bool(client_id),
                'client_secret_filled': bool(client_secret),
                'redirect_uri_used': actual_redirect_uri
            }
        }, status=response.status_code)
    


import os
import json
from datetime import datetime
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from langchain_core.messages import HumanMessage
from .agent import create_graph

LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'agent_chat.log')

def log_agent_interaction(title, data):
    """Utility function to append raw execution frames cleanly into the log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
        f.write(f"\n==================== [{timestamp}] {title} ====================\n")
        if isinstance(data, (dict, list)):
            f.write(json.dumps(data, indent=2))
        else:
            f.write(str(data))
        f.write("\n")




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
    

