import os
import json
import requests
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from langchain_core.messages import HumanMessage, AIMessage
from .agent import create_graph
from .mcp_client import mcp_executor
import re

LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'agent_chat.log')

# 💥 THE CORE LOOKUP UTILITY: Resolves the AttributeError completely
def log_agent_interaction(title, data):
    """Safely records diagnostic trace strings into the local tracking block."""
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n==================== [{timestamp}] {title} ====================\n")
            if isinstance(data, (dict, list)):
                f.write(json.dumps(data, indent=2))
            else:
                f.write(str(data))
            f.write("\n")
    except Exception as e:
        print(f"[LOGGING ERROR] Failed to write step: {str(e)}")

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


# Replace your api_chat view function in authentication/views.py with this updated stateful version:

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

        # Retrieve structural state parameters from the session
        session_plan = request.session.get("active_plan", [])
        session_step_idx = request.session.get("current_step_index", 0)
        scene_elements = request.session.get("active_elements", {})

        # Clear state if a fresh text prompt is submitted from scratch
        if user_prompt and not has_approved:
            session_plan = []
            session_step_idx = 0
            scene_elements = {}
            request.session["active_plan"] = []
            request.session["current_step_index"] = 0
            request.session["active_elements"] = {}

        log_agent_interaction("INBOUND USER REQUEST CONTEXT", {
            "prompt": user_prompt,
            "documentId": doc_id,
            "approved": has_approved,
            "pendingAction": pending_action,
            "active_plan": session_plan,
            "step_index": session_step_idx,
            "scene_elements": scene_elements
        })
        
        available_tools = async_to_sync(mcp_executor.run_with_session)(action_type="GET_TOOLS")
        
        messages = []
        for msg in chat_history_raw:
            if msg.get('isActionPrompt'):
                continue
            if msg.get('sender') == 'user':
                messages.append(HumanMessage(content=msg['text']))
            else:
                messages.append(AIMessage(content=msg['text']))
                
        if user_prompt:
            messages.append(HumanMessage(content=user_prompt))
            
        # Execute approved step
        if has_approved is True and pending_action:
            print(f"[AGENT CORE] User approved step {session_step_idx + 1} action: {pending_action['name']}")
            tool_output_raw = async_to_sync(mcp_executor.run_with_session)(
                action_type="CALL_TOOL",
                tool_name=pending_action['name'],
                arguments=pending_action['arguments']
            )
            
            clean_output_list = []
            for block in (tool_output_raw or []):
                if hasattr(block, 'text'):
                    clean_output_list.append(block.text)
                else:
                    clean_output_list.append(str(block))
            
            final_tool_string = "\n".join(clean_output_list)
            messages.append(HumanMessage(content=f"System Notification: Step {session_step_idx + 1} execution response data: {final_tool_string}"))
            
            # Extract generated feature IDs from the tool response and update tracking state
            if "featureId" in final_tool_string or "id" in final_tool_string:
                try:
                    # Attempt simple parsing of feature reference tokens
                    match = re.search(r'"(?:featureId|id)"\s*:\s*"([^"]+)"', final_tool_string)
                    if match:
                        feat_id = match.group(1)
                        step_label = session_plan[session_step_idx] if session_step_idx < len(session_plan) else "element"
                        scene_elements[step_label] = feat_id
                        request.session["active_elements"] = scene_elements
                        print(f"[TRACKER ENGINE] Successfully registered feature element: '{step_label}' -> '{feat_id}'")
                except:
                    pass

            session_step_idx += 1
            request.session["current_step_index"] = session_step_idx
            has_approved = None
            pending_action = None
            
        elif has_approved == False:
            # User rejected or canceled the workflow
            messages.append(HumanMessage(content="System Notification: User aborted or rejected the current step. Stop execution."))
            session_plan = []
            session_step_idx = 0
            scene_elements = {}
            request.session["active_plan"] = []
            request.session["current_step_index"] = 0
            request.session["active_elements"] = {}
            return JsonResponse({
                "status": "success",
                "reply": "Workflow canceled. All active plans have been stopped and cleared."
            })

        # Inject tracking state into state engine parameters
        graph = create_graph()
        initial_state = {
            "messages": messages,
            "doc_id": doc_id or "",
            "work_id": work_id or "",
            "elem_id": elem_id or "",
            "available_tools": available_tools,
            "next_action": pending_action,
            "approval_granted": has_approved,
            "final_reply": None,
            "plan": session_plan,
            "current_step_index": session_step_idx
        }
        
        # Inject tracking elements as system metadata
        if scene_elements:
            initial_state["messages"] = [SystemMessage(
                content=f"--- KNOWN ACTIVE GEOMETRY TRACKER STATS ---\n"
                f"The following elements have been created on Onshape in previous steps of this plan:\n"
                f"{json.dumps(scene_elements, indent=2)}\n"
                "Use these active IDs directly as parameters when calling featurescript or extrude tools."
            )] + list(initial_state["messages"])

        output_state = graph.invoke(initial_state)
        
        proposed_action = output_state.get("next_action")
        final_reply = output_state.get("final_reply")
        
        # Extract plan if newly created
        if final_reply and not session_plan:
            found_steps = re.findall(r'^\s*\d+\.\s*(.+)$', final_reply, re.MULTILINE)
            if found_steps:
                session_plan = found_steps
                request.session["active_plan"] = found_steps
                request.session["current_step_index"] = 0
                
                # 💥 FIX: Send plan initialization with 'requires_approval' status so buttons render
                return JsonResponse({
                    "status": "requires_approval",
                    "message": f"{final_reply}\n\n🤖 **Plan Initialized.** I will guide you through this step-by-step. Do you approve initializing this sequence?",
                    "pendingAction": {
                        "action": "INITIALIZE_PLAN",
                        "name": "initialize_plan",
                        "arguments": {"steps": found_steps}
                    }
                })
        
        if proposed_action:
            action = proposed_action
            step_name = session_plan[session_step_idx] if session_step_idx < len(session_plan) else action['name']
            return JsonResponse({
                "status": "requires_approval",
                "message": f"🤖 **Step {session_step_idx + 1} Proposal: {step_name}**\nI want to run `{action['name']}` with options: {json.dumps(action['arguments'])}",
                "pendingAction": action
            })
            
        return JsonResponse({
            "status": "success",
            "reply": output_state.get("final_reply", "Task processed successfully.")
        })
        
    except Exception as e:
        print(f"[CRITICAL CHAT EXCEPTION]: {str(e)}")
        log_agent_interaction("CRITICAL CHAT EXCEPTION ERROR LOG", str(e))
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

# =====================================================================
# 📄 DIAGNOSTIC & TELEMETRY MONITORING CONTROLS
# =====================================================================
def view_agent_logs(request):
    """Renders the logs along with a live sanity check of the MCP Server connection."""
    mcp_status = "🔴 Disconnected / Error"
    discovered_tools = []
    
    try:
        # Fire a quick dynamic session handshake check to see if the subprocess boots
        from .mcp_client import mcp_executor
        discovered_tools = async_to_sync(mcp_executor.run_with_session)(action_type="GET_TOOLS")
        if discovered_tools:
            mcp_status = f"🟢 Connected ({len(discovered_tools)} tools discovered)"
    except Exception as e:
        mcp_status = f"🔴 Connection Failure: {str(e)}"

    if not os.path.exists(LOG_FILE_PATH):
        log_content = "Log file empty."
    else:
        with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
            log_content = f.read()

    # Formulate a diagnostic info card summary array
    tools_list_html = "".join([f"<li><code>{t['name']}</code>: {t['description']}</li>" for t in discovered_tools or []])

    html_layout = f"""
    <html>
    <head><title>aiShape Agent Audit Dashboard</title></head>
    <body style="background:#1e1e1e; color:#d4d4d4; font-family:monospace; padding:20px;">
        <div style="background:#2d2d2d; padding:15px; margin-bottom:20px; border-radius:4px; border-left: 5px solid #007acc;">
            <h3>🔌 MCP Server Live Link Status: <span style="font-weight:bold;">{mcp_status}</span></h3>
            <ul>{tools_list_html}</ul>
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