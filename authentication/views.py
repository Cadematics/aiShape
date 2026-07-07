from django.shortcuts import render



import requests
from django.http import JsonResponse

def onshape_callback(request):
    # 1. Catch the unique authorization code sent by Onshape
    auth_code = request.GET.get('code')
    
    if not auth_code:
        return JsonResponse({'status': 'error', 'message': 'No authorization code detected.'}, status=400)
    
    # 2. Exchange this code for a permanent access token
    token_url = "https://oauth.onshape.com/oauth/token"
    payload = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'client_id': 'YOUR_ONSHAPE_CLIENT_ID',       # We will set these up next
        'client_secret': 'YOUR_ONSHAPE_CLIENT_SECRET', 
        'redirect_uri': 'https://your-app-name.onrender.com/oauth/callback/', # Your future live production URL
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(token_url, data=payload, headers=headers)
    
    if response.status_code == 200:
        tokens = response.json()
        access_token = tokens.get('access_token')
        # Success! You can now pass this token to your AI context windows
        return JsonResponse({'status': 'success', 'message': 'Authenticated with Onshape successfully!'})
    else:
        return JsonResponse(response.json(), status=response.status_code)




# Create your views here.
