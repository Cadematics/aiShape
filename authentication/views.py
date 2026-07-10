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
    


import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from langchain_core.messages import HumanMessage
from .agent import create_graph  # <--- Import the graph factory cleanly





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
        
        print(f"[LANGGRAPH INGEST] Processing sync traces for prompt: {user_prompt}")
        
        # Instantiate your agent graph network
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
        
        # Safely stream node steps without pulling the whole dictionary object into pprint logs
        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, state_update in event.items():
                
                # Check for output responses from tools or agent reasoning steps
                if "messages" in state_update and state_update["messages"]:
                    latest_msg = state_update["messages"][-1]
                    # Handle both standard BaseMessage objects and raw string values safely
                    node_content = latest_msg.content if hasattr(latest_msg, 'content') else str(latest_msg)
                    if node_content:
                        final_answer_text = node_content
                
                # Format step markers that drop beautifully inside the markdown chat layout
                log_title = node_name.replace('_', ' ').title()
                execution_progress_logs.append(f"✓ **{log_title}** successfully processed.")

        # If the tool-calls returned data without changing the assistant message, handle fallback text
        if not final_answer_text:
            final_answer_text = "CAD processing sequence completed successfully."

        # Compile progress overview with markdown spacing rules
        progress_block = "### 🚀 Agent Execution Progress\n" + "\n".join([f"* {log}" for log in execution_progress_logs])
        combined_markdown_reply = f"{progress_block}\n\n---\n\n### 📦 Final Response\n{final_answer_text}"

        return JsonResponse({
            'status': 'success',
            'reply': combined_markdown_reply
        })

    except Exception as e:
        print(f"[ERROR IN API CHAT]: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)