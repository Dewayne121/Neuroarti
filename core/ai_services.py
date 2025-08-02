# core/ai_services.py
import os
from openai import AsyncOpenAI
import google.generativeai as genai
from fastapi import HTTPException
from typing import AsyncGenerator
from core.models import MODELS

# --- Environment Setup ---
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

together_client = AsyncOpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# --- Private API Call Functions ---
async def _generate_with_together(system_prompt: str, user_prompt: str, model_api_id: str, stream: bool = False):
    try:
        response_stream = await together_client.chat.completions.create(
            model=model_api_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.2,
            max_tokens=8192,
            stream=stream
        )
        if stream:
            async def stream_generator():
                async for chunk in response_stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
            return stream_generator() # This returns the async generator function
        else:
            # This is not a stream, so we await the single result
            return response_stream.choices[0].message.content or ""
    except Exception as e:
        print(f"Together AI Error: {e}")
        raise HTTPException(status_code=502, detail=f"Together AI service error: {str(e)}")

async def _generate_with_google(system_prompt: str, user_prompt: str, model_api_id: str, stream: bool = False):
    if stream:
        async def stream_placeholder():
            response_text = await _generate_with_google(system_prompt, user_prompt, model_api_id, stream=False)
            yield response_text
        return stream_placeholder()

    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=503, detail="Google API key not configured.")
    try:
        model = genai.GenerativeModel(model_api_id)
        full_prompt = f"{system_prompt}\n\nUSER PROMPT: {user_prompt}"
        safety_settings = { 'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE', 'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'}
        
        response = await model.generate_content_async(full_prompt, safety_settings=safety_settings)
        return response.text
    except Exception as e:
        print(f"Google AI Error: {e}")
        raise HTTPException(status_code=502, detail=f"Google AI service error: {str(e)}")

# --- Public Dispatcher Functions ---
async def generate_code(system_prompt: str, user_prompt: str, model_key: str) -> str:
    model_config = MODELS.get(model_key)
    if not model_config:
        raise HTTPException(status_code=400, detail=f"Invalid model key: {model_key}")
    
    provider_map = {
        "together": _generate_with_together,
        "google": _generate_with_google
    }
    provider_func = provider_map.get(model_config["api_provider"])
    if not provider_func:
        raise HTTPException(status_code=500, detail=f"Unknown provider for model '{model_key}'")

    return await provider_func(system_prompt, user_prompt, model_config["api_id"], stream=False)

# FIX: This is now a REGULAR function, not an async one.
def stream_code(system_prompt: str, user_prompt: str, model_key: str):
    """Returns a coroutine that, when awaited, produces an async generator for streaming."""
    model_config = MODELS.get(model_key)
    if not model_config:
        raise HTTPException(status_code=400, detail=f"Invalid model key: {model_key}")

    provider_map = {
        "together": _generate_with_together,
        "google": _generate_with_google
    }
    provider_func = provider_map.get(model_config["api_provider"])
    if not provider_func:
        raise HTTPException(status_code=500, detail=f"Unknown provider for model '{model_key}'")
    
    # Return the coroutine itself, NOT the awaited result.
    return provider_func(system_prompt, user_prompt, model_config["api_id"], stream=True)
