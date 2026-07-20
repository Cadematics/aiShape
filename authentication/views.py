import json
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import async_to_sync
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from .agent import create_graph
from .mcp_client import mcp_executor



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

        # Handle explicit tool approval
        if has_approved is True and pending_action:
            print(f"[AGENT CORE] Executing approved write tool: {pending_action['name']}")
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
            messages.append(HumanMessage(content=f"System Notification: Tool '{pending_action['name']}' returned: {final_tool_string}"))
            
            # Store returned feature IDs
            if "featureId" in final_tool_string or "id" in final_tool_string:
                match = re.search(r'"(?:featureId|id)"\s*:\s*"([^"]+)"', final_tool_string)
                if match:
                    scene_elements[pending_action['name']] = match.group(1)
                    request.session["active_elements"] = scene_elements

            has_approved = None
            pending_action = None
            request.session.modified = True

        elif has_approved == False:
            request.session["active_elements"] = {}
            request.session.modified = True
            return JsonResponse({"status": "success", "reply": "Operation rejected and workflow stopped."})

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
            "final_reply": None
        }

        if scene_elements:
            initial_state["messages"] = [SystemMessage(
                content=f"--- ACTIVE SCENE GEOMETRY IDs ---\n{json.dumps(scene_elements, indent=2)}"
            )] + list(initial_state["messages"])

        output_state = graph.invoke(initial_state)
        
        proposed_action = output_state.get("next_action")
        
        if proposed_action:
            action = proposed_action
            return JsonResponse({
                "status": "requires_approval",
                "message": f"🤖 **Proposal: {action['name']}**\nI want to run `{action['name']}` with parameters: {json.dumps(action['arguments'])}",
                "pendingAction": action
            })
            
        return JsonResponse({
            "status": "success",
            "reply": output_state.get("final_reply", "Task completed successfully.")
        })
        
    except Exception as e:
        print(f"[CRITICAL EXCEPTION]: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)