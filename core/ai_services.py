# core/ai_services.py
import os
from openai import OpenAI
import google.generativeai as genai
from fastapi import HTTPException
from core.models import MODELS, PROVIDERS
from core.prompts import INITIAL_SYSTEM_PROMPT, FOLLOW_UP_SYSTEM_PROMPT

# --- Environment Setup ---
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

together_client = OpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")
if GOOGLE_API_KEY: genai.configure(api_key=GOOGLE_API_KEY)

# --- Streaming Generation for /build endpoint ---
async def generate_code_stream(prompt: str, model_key: str, provider_key: str, html_context: str | None = None, redesign_markdown: str | None = None):
    selected_model = next((m for m in MODELS if m["value"] == model_key), None)
    if not selected_model:
        raise HTTPException(status_code=400, detail="Invalid model selected.")

    provider_id = PROVIDERS[provider_key]["id"]
    max_tokens = PROVIDERS[provider_key]["max_tokens"]
    
    user_content = ""
    if redesign_markdown:
        user_content = f"Here is my current design as a markdown:\n\n{redesign_markdown}\n\nNow, please create a new design based on this markdown."
    elif html_context:
        user_content = f"Here is my current HTML code:\n\n```html\n{html_context}\n```\n\nNow, please create a new design based on this HTML and my request: {prompt}"
    else:
        user_content = prompt

    messages = [{"role": "system", "content": INITIAL_SYSTEM_PROMPT}, {"role": "user", "content": user_content}]
    
    try:
        stream = await together_client.chat.completions.create(
            model=selected_model["value"],
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens,
            stream=True
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        print(f"Streaming AI Error: {e}")
        yield f'{{"ok": false, "message": "Error from AI provider: {str(e)}"}}'


# --- Non-Streaming Generation for /update (Diff-Patch) endpoint ---
async def generate_diff_patch(prompt: str, model_key: str, provider_key: str, full_html: str, selected_element_html: str | None):
    selected_model = next((m for m in MODELS if m["value"] == model_key), None)
    if not selected_model:
        raise HTTPException(status_code=400, detail="Invalid model selected.")

    provider_id = PROVIDERS[provider_key]["id"]
    max_tokens = PROVIDERS[provider_key]["max_tokens"]

    user_content = f"The current code is:\n```html\n{full_html}\n```\n\nMy request is: '{prompt}'"
    if selected_element_html:
        user_content += f"\n\nI have selected a specific element to modify. Please confine your changes to ONLY this element and its children:\n```html\n{selected_element_html}\n```"

    messages = [{"role": "system", "content": FOLLOW_UP_SYSTEM_PROMPT}, {"role": "user", "content": user_content}]

    try:
        response = await together_client.chat.completions.create(
            model=selected_model["value"],
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"Diff-Patch AI Error: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error during patch generation: {str(e)}")