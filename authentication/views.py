access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"



import os
import json
import requests
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from langchain_core.messages import HumanMessage, AIMessage
from .agent import create_graph
from .mcp_client import mcp_manager  # Import our subprocess singleton manager


LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'agent_chat.log')

# =====================================================================
# 🌐 ONSHAPE OAUTH HANDSHAKE HANDLER
# =====================================================================
def onshape_callback(request):
    auth_code = request.GET.get('code')
    if not auth_code:
        return JsonResponse({'status': 'error', 'message': 'No authorization code detected.'}, status=400)
    
    client_id = os.environ.get('ONSHAPE_CLIENT_ID', '').strip()
    client_secret = os.environ.get('ONSHAPE_CLIENT_SECRET', '').strip()
    actual_redirect_uri = request.build_absolute_uri(request.path)

    token_url = "https://oauth.onshape.com/oauth/token"
    payload = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': actual_redirect_uri,
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    response = requests.post(token_url, data=payload, headers=headers)
    if response.status_code == 200:
        tokens = response.json()
        return JsonResponse({
            'status': 'success', 
            'message': 'Authenticated with Onshape successfully!',
            'access_token_preview': tokens.get('access_token')[:10] + "..."
        })
    else:
        return JsonResponse({
            'status': 'handshake_failed',
            'onshape_error_payload': response.json()
        }, status=response.status_code)

# =====================================================================
# 🤖 ACTIVE AGENT CHAT CONTROL LOOP (WITH HUMAN-IN-THE-LOOP CONTROLS)
# =====================================================================
@csrf_exempt
def api_chat(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        user_prompt = data.get('prompt', '')
        cad_context = data.get('context', {})
        
        has_approved = data.get('approved', None)
        pending_action = data.get('pendingAction', None)
        chat_history_raw = data.get('history', [])
        
        doc_id = cad_context.get('documentId')
        work_id = cad_context.get('workspaceId')
        elem_id = cad_context.get('elementId')
        
        # 1. Initialize background stdio subprocesses dynamically
        async_to_sync(mcp_manager.initialize)()
        available_tools = async_to_sync(mcp_manager.get_tools)()
        
        # 2. Reconstruct session interaction tokens
        messages = []
        for msg in chat_history_raw:
            # Shield out markdown structural prompts from internal chat history memory
            if msg.get('isActionPrompt'):
                continue
            if msg.get('sender') == 'user':
                messages.append(HumanMessage(content=msg['text']))
            else:
                messages.append(AIMessage(content=msg['text']))
                
        if user_prompt:
            messages.append(HumanMessage(content=user_prompt))
            
        # 3. Handle Human-in-the-Loop response decisions
        if has_approved is True and pending_action:
            print(f"[AGENT CORE] User approved execution for tool: {pending_action['name']}")
            tool_output = async_to_sync(mcp_manager.call_tool)(
                name=pending_action['name'], 
                arguments=pending_action['arguments']
            )
            messages.append(HumanMessage(content=f"System Notification: Tool execution response data: {json.dumps(tool_output)}"))
            has_approved = None
            pending_action = None
            
        elif has_approved == False:
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
        
        # 5. Route output state properties back to frontend
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

# =====================================================================
# 📄 DIAGNOSTIC & TELEMETRY MONITORING CONTROLS
# =====================================================================
def view_agent_logs(request):
    if not os.path.exists(LOG_FILE_PATH):
        return HttpResponse("<html><body><h3>Log file is currently empty or hasn't been created yet.</h3></body></html>")
    with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
        log_content = f.read()
    html_layout = f"""
    <html>
    <head><title>aiShape Agent Audit Dashboard</title></head>
    <body style="background:#1e1e1e; color:#d4d4d4; font-family:monospace; padding:20px;">
        <div style="background:#2d2d2d; padding:10px; margin-bottom:20px; border-radius:4px;">
            <a href="/api/logs/clear/" style="color:#f44336; font-weight:bold; text-decoration:none;">⚠️ Delete Logs & Start Fresh</a>
        </div>
        <pre style="white-space:pre-wrap;">{log_content}</pre>
    </body>
    </html>
    """
    return HttpResponse(html_layout)

@csrf_exempt
def clear_agent_logs(request):
    with open(LOG_FILE_PATH, 'w', encoding='utf-8') as f:
        f.write("")
    return HttpResponse("<html><body><script>alert('Logs cleared!'); window.location.href='/api/logs/';</script></body></html>")