# core/ai_services.py
import os
from openai import AsyncOpenAI # Use the Async version of the client
import google.generativeai as genai
from fastapi import HTTPException
from core.models import MODELS

# --- Environment Setup ---
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# FIX: Initialize the client as an AsyncOpenAI client
together_client = AsyncOpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# --- Private functions for each API ---
async def _generate_with_together(system_prompt: str, user_prompt: str, model_api_id: str):
    try:
        # FIX: Changed from .create to the asynchronous .create
        response = await together_client.chat.completions.create(
            model=model_api_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.2,
            max_tokens=8192
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"Together AI Error: {e}")
        raise HTTPException(status_code=502, detail=f"Together AI service error: {str(e)}")

async def _generate_with_google(system_prompt: str, user_prompt: str, model_api_id: str):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=503, detail="Google API key not configured. Gemini is unavailable.")
    
    try:
        model = genai.GenerativeModel(model_api_id)
        full_prompt = f"{system_prompt}\n\nUSER PROMPT: {user_prompt}"
        safety_settings = {
            'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 
            'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE', 
            'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 
            'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
        }
        
        # FIX: Changed from .generate_content to the asynchronous .generate_content_async
        response = await model.generate_content_async(full_prompt, safety_settings=safety_settings)
        return response.text
    except Exception as e:
        print(f"Google AI Error: {e}")
        raise HTTPException(status_code=502, detail=f"Google AI service error: {str(e)}")

# --- Public dispatcher function ---
async def generate_code(system_prompt: str, user_prompt: str, model_key: str):
    model_config = MODELS.get(model_key)
    if not model_config:
        raise HTTPException(status_code=400, detail=f"Invalid model key provided: {model_key}")
    
    api_provider = model_config["api_provider"]
    model_api_id = model_config["api_id"]
    
    if api_provider == "together":
        return await _generate_with_together(system_prompt, user_prompt, model_api_id)
    elif api_provider == "google":
        return await _generate_with_google(system_prompt, user_prompt, model_api_id)
    else:
        raise HTTPException(status_code=500, detail=f"Unknown API provider configured for model '{model_key}'")
