import os
import requests
from django.http import JsonResponse

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