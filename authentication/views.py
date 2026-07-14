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
from .agent import create_graph
from .mcp_client import mcp_executor
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from .agent import create_graph
from .mcp_client import mcp_executor


# Replace the views.py contents with this fully synchronized contextual version:


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
        if user_prompt and not has_approved and not is_state_marker:
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