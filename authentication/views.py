import os
import requests
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt




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
    


@csrf_exempt # Exempt from CSRF tokens since we are handling cross-domain security via CORS
def api_chat(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    try:
        # Parse the JSON payload coming from React
        data = json.loads(request.body)
        
        user_prompt = data.get('prompt', '')
        cad_context = data.get('context', {})
        selected_entity = data.get('selectedEntity') # Can be None if nothing clicked
        
        # Extract individual tokens for your future CAD queries
        doc_id = cad_context.get('documentId')
        work_id = cad_context.get('workspaceId')
        elem_id = cad_context.get('elementId')
        
        # 💥 DEBUG PRINT: Watch the telemetry hit your Render logs live!
        print(f"\n[AI CHAT ENDPOINT INGEST]")
        print(f"-> Prompt: {user_prompt}")
        print(f"-> CAD Context: Doc={doc_id[:6]}..., Work={work_id[:6]}..., Elem={elem_id[:6]}...")
        print(f"-> Clicked Entity Topology: {selected_entity}\n")
        
        # TODO: This is where we will invoke the LangGraph Agent Engine:
        # agent_response = run_cad_agent(user_prompt, doc_id, work_id, elem_id, selected_entity)
        
        # Mock Response for testing the front-to-back pipeline connection
        mock_reply = f"Backend received your request for document {doc_id[:6]}. "
        if selected_entity:
            mock_reply += f"I see you targeted a {selected_entity.get('entityType')}."
        else:
            mock_reply += "No viewport selections were highlighted."
            
        return JsonResponse({
            'status': 'success',
            'reply': mock_reply
        })

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



