import json
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from .agent import create_graph
from .mcp_client import mcp_executor
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


# Replace the views.py contents with this fully synchronized contextual version:

import json
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from .agent import create_graph
from .mcp_client import mcp_executor

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

        # Load states from Django session cache
        session_plan = request.session.get("active_plan", [])
        session_step_idx = request.session.get("current_step_index", 0)
        scene_elements = request.session.get("active_elements", {})

        # Clear active design loop cache when a brand new user request is submitted
        is_state_marker = user_prompt in ["Approved", "Rejected"]
        
        # If there's no active plan, or if the user is explicitly starting over, clear the state
        if user_prompt and not has_approved and not is_state_marker and not session_plan:
            session_plan = []
            session_step_idx = 0
            scene_elements = {}
            request.session["active_plan"] = []
            request.session["current_step_index"] = 0
            request.session["active_elements"] = {}
            request.session.modified = True

        print(f"[STATE MONITOR] Prompt: '{user_prompt}' | Approved: {has_approved} | Index: {session_step_idx} | Plan Length: {len(session_plan)}")

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
            if pending_action.get("action") == "INITIALIZE_PLAN":
                print("[AGENT CORE] Plan initialization approved.")
                messages.append(HumanMessage(content="System Notification: The plan has been approved. Please propose the first modeling step now."))
            else:
                print(f"[AGENT CORE] Executing step {session_step_idx + 1}: {pending_action['name']}")
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
                messages.append(HumanMessage(content=f"System Notification: Step {session_step_idx + 1} response data: {final_tool_string}"))
                
                # Extract and store generated feature IDs and transient face IDs dynamically
                if "featureId" in final_tool_string or "id" in final_tool_string or "transientId" in final_tool_string:
                    try:
                        # Attempt to parse both feature IDs and transient/deterministic geometric query matches
                        feat_match = re.search(r'"(?:featureId|id)"\s*:\s*"([^"]+)"', final_tool_string)
                        transient_match = re.search(r'"transientId"\s*:\s*"([^"]+)"', final_tool_string)
                        
                        step_label = session_plan[session_step_idx] if session_step_idx < len(session_plan) else "element"
                        step_label_clean = re.sub(r'[*#_]', '', step_label)[:40]
                        
                        if feat_match:
                            scene_elements[f"{step_label_clean}_id"] = feat_match.group(1)
                        if transient_match:
                            scene_elements[f"{step_label_clean}_transient_face_id"] = transient_match.group(1)
                            
                        request.session["active_elements"] = scene_elements
                        print(f"[TRACKER ENGINE] Registered scene element metrics: {scene_elements}")
                    except Exception as parse_err:
                        print(f"[TRACKER WARNING] Could not parse metadata: {str(parse_err)}")

                # Advance index for actual tool steps
                session_step_idx += 1
                request.session["current_step_index"] = session_step_idx

            has_approved = None
            pending_action = None
            request.session.modified = True
            
        elif has_approved == False:
            messages.append(HumanMessage(content="System Notification: User aborted current step. Stop execution."))
            request.session["active_plan"] = []
            request.session["current_step_index"] = 0
            request.session["active_elements"] = {}
            request.session.modified = True
            return JsonResponse({
                "status": "success",
                "reply": "Workflow canceled. Active plans have been cleared."
            })

        # Run LangGraph Engine
        available_tools = async_to_sync(mcp_executor.run_with_session)(action_type="GET_TOOLS")
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
        
        # Inject known active modeling elements as system metadata context
        if scene_elements:
            initial_state["messages"] = [SystemMessage(
                content=f"--- ACTIVE MODEL ELEMENTS & GEOMETRIC ENTITIES IN SCENE ---\n"
                f"{json.dumps(scene_elements, indent=2)}\n"
                "Use these structural element IDs and transient face references exactly as parameters when constructing subsequent features."
            )] + list(initial_state["messages"])


        # 💥 ADD THIS DEBUG LOGGER IN views.py RIGHT BEFORE graph.invoke():
        print("\n==================== [LLM CONTEXT TRANSMISSION AUDIT] ====================")
        print(f"ACTIVE SYSTEM PLAN IN STATE: {session_plan}")
        print(f"ACTIVE STEP INDEX IN STATE: {session_step_idx}")
        print(f"SCENE ELEMENTS CACHE: {json.dumps(scene_elements)}")
        print("-------------------- CONVERSATION HISTORY SENT TO GPT-4o --------------------")
        for i, msg in enumerate(initial_state["messages"]):
            role_tag = "SYSTEM" if isinstance(msg, SystemMessage) else ("USER" if isinstance(msg, HumanMessage) else "ASSISTANT")
            # Slice long responses to keep log readable
            clean_content = msg.content if len(msg.content) < 300 else f"{msg.content[:300]}... [truncated]"
            print(f"[{i}] {role_tag}: {clean_content}")
        print("==========================================================================")

        output_state = graph.invoke(initial_state)
        
        # 💥 ADD THIS POST-INVOKE LOGGER RIGHT AFTER IT:
        print("\n==================== [LLM RESPONSE AUDIT] ====================")
        print(f"AI FINAL REPLY (PROSE): {output_state.get('final_reply')}")
        print(f"AI NEXT ACTION (TOOL): {json.dumps(output_state.get('next_action'), indent=2)}")
        print("================================================================")

        output_state = graph.invoke(initial_state)
        
        proposed_action = output_state.get("next_action")
        final_reply = output_state.get("final_reply")
        
        # Extract plan if newly created
        if final_reply and not session_plan:
            found_steps = re.findall(r'^\s*\d+\.\s*(.+)$', final_reply, re.MULTILINE)
            if found_steps:
                cleaned_steps = [re.sub(r'[*_#]', '', step).strip() for step in found_steps]
                session_plan = cleaned_steps
                request.session["active_plan"] = cleaned_steps
                request.session["current_step_index"] = 0
                request.session.modified = True
                print(f"[SESSION ENGINE] Saved cleaned steps: {cleaned_steps}")
                
                return JsonResponse({
                    "status": "requires_approval",
                    "message": f"{final_reply}\n\n🤖 **Plan Initialized.** Do you approve initializing this sequence?",
                    "pendingAction": {
                        "action": "INITIALIZE_PLAN",
                        "name": "initialize_plan",
                        "arguments": {"steps": cleaned_steps}
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
            "reply": output_state.get("final_reply", "Task completed.")
        })
        
    except Exception as e:
        print(f"[CRITICAL CHAT EXCEPTION]: {str(e)}")
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








