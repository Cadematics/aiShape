import json
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from .agent import create_graph
from .mcp_client import mcp_executor

# 💥 Ensure StreamingHttpResponse is imported at the top of authentication/views.py:
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import re
from asgiref.sync import async_to_sync
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from .agent import create_graph
from .mcp_client import mcp_executor
import os
import requests







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
        scene_elements = request.session.get("active_elements", {})

        def event_stream_generator():
            """Generates Server-Sent Events (SSE) in real-time as LangGraph steps execute."""
            
            # Helper to format SSE frames
            def sse_format(event_type: str, payload: dict) -> str:
                return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

            yield sse_format("status", {"message": "Initializing autonomous agent loop..."})

            messages = []
            for msg in chat_history_raw:
                if msg.get('isActionPrompt'):
                    continue
                if msg.get('sender') == 'user':
                    messages.append(HumanMessage(content=msg['text']))
                else:
                    messages.append(AIMessage(content=msg['text']))
                    
            if user_prompt and user_prompt not in ["Approved", "Rejected"]:
                messages.append(HumanMessage(content=user_prompt))

            # Handle user approvals for CAD write actions
            if has_approved is True and pending_action:
                yield sse_format("step", {"title": f"Executing CAD action: {pending_action['name']}", "status": "running"})
                
                tool_output_raw = async_to_sync(mcp_executor.run_with_session)(
                    action_type="CALL_TOOL",
                    tool_name=pending_action['name'],
                    arguments=pending_action['arguments']
                )
                
                clean_output_list = [
                    block.text if hasattr(block, 'text') else str(block) 
                    for block in (tool_output_raw or [])
                ]
                final_tool_string = "\n".join(clean_output_list)
                messages.append(HumanMessage(content=f"System Notification: Tool '{pending_action['name']}' returned: {final_tool_string}"))
                
                if "featureId" in final_tool_string or "id" in final_tool_string:
                    match = re.search(r'"(?:featureId|id)"\s*:\s*"([^"]+)"', final_tool_string)
                    if match:
                        scene_elements[pending_action['name']] = match.group(1)
                        request.session["active_elements"] = scene_elements
                        request.session.modified = True

            # Run LangGraph Agent Engine and Stream
            available_tools = async_to_sync(mcp_executor.run_with_session)(action_type="GET_TOOLS")
            graph = create_graph()
            initial_state = {
                "messages": messages,
                "doc_id": doc_id or "",
                "work_id": work_id or "",
                "elem_id": elem_id or "",
                "available_tools": available_tools,
                "next_action": None,
                "approval_granted": has_approved,
                "final_reply": None
            }

            if scene_elements:
                initial_state["messages"] = [SystemMessage(
                    content=f"--- ACTIVE SCENE GEOMETRY IDs ---\n{json.dumps(scene_elements, indent=2)}"
                )] + list(initial_state["messages"])

            final_state = initial_state
            
            # Stream graph updates live
            for event in graph.stream(initial_state, stream_mode="values"):
                final_state = event
                next_act = event.get("next_action")
                
                if next_act:
                    yield sse_format("step", {
                        "title": f"Executing action: {next_act.get('name', 'tool')}",
                        "status": "running"
                    })
                else:
                    yield sse_format("status", {"message": "Agent evaluating next architectural step..."})

            proposed_action = final_state.get("next_action")
            final_reply = final_state.get("final_reply")
            
            if proposed_action:
                yield sse_format("approval_required", {
                    "status": "requires_approval",
                    "message": f"🤖 **Proposal: {proposed_action['name']}**\nI want to run `{proposed_action['name']}` with options: {json.dumps(proposed_action['arguments'])}",
                    "pendingAction": proposed_action
                })
            else:
                yield sse_format("done", {
                    "status": "success",
                    "reply": final_reply or "Task completed."
                })

        return StreamingHttpResponse(event_stream_generator(), content_type="text/event-stream")
        
    except Exception as e:
        print(f"[CRITICAL EXCEPTION]: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)    





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