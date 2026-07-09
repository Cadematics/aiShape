






import os
from openai import OpenAI


def run_cad_agent(prompt: str, doc_id: str, work_id: str, elem_id: str, selected_entity: dict) -> str:
    # api_key = os.environ.get("OPENAI_API_KEY")
    
    api_key="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"
    if not api_key:
        print("[CRITICAL ERROR] OPENAI_API_KEY environment variable is MISSING on Render!")
        return "Backend API configuration error: Key missing."

    print(f"[NATIVE JOKE TEST] Key validation check passed. Prompt received: '{prompt}'")

    try:
        # Build an explicit, isolated connection layer with generous timeout limits
        # to ensure Gunicorn doesn't drop the thread socket prematurely
        client = OpenAI(
            api_key=api_key,
            timeout=60.0  # Force a long timeout cushion
        )
        
        print("[NATIVE JOKE TEST] Deserializing connection pool. Reaching out to OpenAI...")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Using mini for the fastest possible round-trip execution
            temperature=0.7,
            messages=[
                {"role": "system", "content": "You are a funny assistant. Tell a short engineering or coding joke based on the user request."},
                {"role": "user", "content": prompt}
            ]
        )
        
        ai_reply = response.choices[0].message.content
        print("[NATIVE JOKE TEST] Success! Joke response returned.")
        return ai_reply

    except Exception as e:
        print(f"[NATIVE JOKE TEST CRASH]: {str(e)}")
        return f"Isolated Joke API Connection Failure: {str(e)}"