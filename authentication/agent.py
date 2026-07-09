import os
from openai import OpenAI

def run_cad_agent(prompt: str, doc_id: str, work_id: str, elem_id: str, selected_entity: dict) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[CRITICAL ERROR] OPENAI_API_KEY environment variable is MISSING on Render!")
        return "Backend API configuration error: Key missing."

    print(f"[NATIVE OPENAI] Running prompt: '{prompt}'")
    
    # Assemble your engineering context string manually
    system_instruction = (
        "You are an expert AI CAD co-pilot integrated directly within Onshape. "
        f"The active workspace document context is Document ID: {doc_id or 'N/A'}.\n"
    )
    
    if selected_entity:
        system_instruction += (
            f"The user has highlighted a specific 3D topology entity right now:\n"
            f"- Entity Type: {selected_entity.get('entityType')}\n"
            f"- Element/Entity ID: {selected_entity.get('id')}\n"
            "Identify this element to the user when asked."
        )
    else:
        system_instruction += "No specific 3D geometry is currently highlighted in the viewport."

    try:
        # Instantiate your native working client
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o",  # Using full gpt-4o for robust reasoning capabilities
            temperature=0,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ]
        )
        
        ai_reply = response.choices[0].message.content
        print("[NATIVE OPENAI] Success! Response fetched.")
        return ai_reply

    except Exception as e:
        print(f"[NATIVE OPENAI CRASH]: {str(e)}")
        return f"Native Backend Connection Error: {str(e)}"
    