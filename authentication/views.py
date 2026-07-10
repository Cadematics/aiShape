access_key ="on_bYfDyZ0QtxjnQOAqlSPTD"
secret_key="aeSrt2XWfSFFTxOwiUMtHKnpaNNQfBrqAnekcX7VgSqeo2xL"
openai_api_key="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"


import os
import requests
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from langchain_core.messages import HumanMessage
from .agent import create_graph  # Clean import without old references


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
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        user_prompt = data.get('prompt', '')
        cad_context = data.get('context', {})
        selected_entity = data.get('selectedEntity')
        
        doc_id = cad_context.get('documentId')
        work_id = cad_context.get('workspaceId')
        elem_id = cad_context.get('elementId')
        
        # 🪵 LOG: Input packet parameters
        log_agent_interaction("INBOUND USER PROMPT & STATE CONTEXT", {
            "prompt": user_prompt,
            "documentId": doc_id,
            "workspaceId": work_id,
            "elementId": elem_id,
            "selectedEntity": selected_entity
        })
        
        graph = create_graph()
        initial_state = {
            "messages": [HumanMessage(content=user_prompt)],
            "doc_id": doc_id or "",
            "work_id": work_id or "",
            "elem_id": elem_id or "",
            "selected_entity": selected_entity or {},
            "active_payloads": []
        }
        
        execution_progress_logs = []
        final_answer_text = ""
        
        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, state_update in event.items():
                
                # 💥 THE FIX: Recursively clean and stringify any HumanMessage/AIMessage objects inside the state dictionary
                serializable_update = {}
                for key, val in state_update.items():
                    if key == "messages":
                        # Convert message list instances to a clean text array
                        serializable_update[key] = [
                            f"{type(msg).__name__}: {msg.content}" if hasattr(msg, 'content') else str(msg)
                            for msg in val
                        ]
                    else:
                        serializable_update[key] = val

                # 🪵 LOG: Now safe to dump cleanly as JSON string tokens
                log_agent_interaction(f"GRAPH NODE STATE UPDATE: {node_name.upper()}", serializable_update)
                
                if "messages" in state_update and state_update["messages"]:
                    latest_msg = state_update["messages"][-1]
                    node_content = latest_msg.content if hasattr(latest_msg, 'content') else str(latest_msg)
                    if node_content:
                        final_answer_text = node_content
                
                log_title = node_name.replace('_', ' ').title()
                execution_progress_logs.append(f"✓ **{log_title}** successfully processed.")

        if not final_answer_text:
            final_answer_text = "CAD processing sequence completed successfully."

        progress_block = "### 🚀 Agent Execution Progress\n" + "\n".join([f"* {log}" for log in execution_progress_logs])
        combined_markdown_reply = f"{progress_block}\n\n---\n\n### 📦 Final Response\n{final_answer_text}"

        return JsonResponse({
            'status': 'success',
            'reply': combined_markdown_reply
        })

    except Exception as e:
        log_agent_interaction("CRITICAL API CHAT RUNTIME EXCEPTION", str(e))
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def view_agent_logs(request):
    """Renders the raw text file logs cleanly in the browser viewport."""
    if not os.path.exists(LOG_FILE_PATH):
        return HttpResponse("<html>bg-slate-900<body><h3>Log file is currently empty or hasn't been created yet.</h3></body></html>")
    
    with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
        log_content = f.read()
        
    # Quick functional HTML wrapper to make the terminal logs readable
    html_layout = f"""
    <html>
    <head>
        <title>aiShape Agent Audit Dashboard</title>
        <style>
            body {{ background-color: #1e1e1e; color: #d4d4d4; font-family: monospace; padding: 20px; }}
            .controls {{ margin-bottom: 20px; padding: 10px; background: #2d2d2d; border-radius: 4px; }}
            a {{ color: #007acc; text-decoration: none; font-weight: bold; margin-right: 20px; }}
            pre {{ background: #252526; padding: 15px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; }}
        </style>
    </head>
    <body>
        <div class="controls">
            <span>🛠️ Operations:</span>
            <a href="/api/logs/clear/" onclick="return confirm('Are you sure you want to clear all logs?');" style="color: #f44336; margin-left: 15px;">⚠️ Delete Logs & Start Fresh</a>
        </div>
        <h3>📄 Active Agent Audit Stream (agent_chat.log)</h3>
        <pre>{log_content}</pre>
    </body>
    </html>
    """
    return HttpResponse(html_layout)

@csrf_exempt
def clear_agent_logs(request):
    """Truncates the log file back to 0 bytes to start completely fresh."""
    try:
        with open(LOG_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write("") # Overwrite clean empty string
        log_agent_interaction("SYSTEM ENGINE INITIALIZED", "Log file cleared manually. Fresh environment tracking ready.")
        return HttpResponse("<html><body><script>alert('Logs cleared successfully!'); window.location.href='/api/logs/';</script></body></html>")
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)