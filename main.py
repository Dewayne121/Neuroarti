# main.py
import os
import uuid
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from typing import AsyncGenerator

from core.ai_services import generate_code, stream_code
from core.prompts import (
    MAX_REQUESTS_PER_IP,
    INITIAL_SYSTEM_PROMPT,
    create_follow_up_prompt,
    DEFAULT_HTML
)
from core.models import MODELS
from core.utils import (
    ip_limiter,
    is_the_same_html,
    apply_diff_patch,
)

load_dotenv()

# --- Pydantic Models ---
class AskAiPostRequest(BaseModel):
    prompt: str
    model: str
    html: str | None = None

class AskAiPutRequest(BaseModel):
    prompt: str
    model: str
    html: str
    selectedElementHtml: str | None = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Streaming Generator for New Builds ---
async def stream_html_generator(ai_stream: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    buffer = ""
    html_started = False
    html_ended = False

    async for chunk in ai_stream: # This loop was causing the error
        if html_ended:
            continue

        buffer += chunk

        if not html_started:
            match = re.search(r'<!DOCTYPE html>', buffer, re.IGNORECASE)
            if match:
                html_started = True
                content_to_yield = buffer[match.start():]
                buffer = ""
                yield content_to_yield
        
        if html_started:
            end_match = re.search(r'</html>', buffer, re.IGNORECASE)
            if end_match:
                html_ended = True
                content_to_yield = buffer[:end_match.end()]
                yield content_to_yield
                break
            
            last_newline = buffer.rfind('\n')
            if last_newline != -1:
                content_to_yield = buffer[:last_newline + 1]
                buffer = buffer[last_newline + 1:]
                yield content_to_yield
    
    if html_started and not html_ended and buffer:
        yield buffer

@app.post("/api/ask-ai")
async def ask_ai_post(request: Request, body: AskAiPostRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    if body.model not in MODELS:
        raise HTTPException(status_code=400, detail="Invalid model selected")

    html_context = body.html if body.html and not is_the_same_html(body.html) else None
    
    if html_context:
        user_prompt = f"Here is my current HTML code:\n\n```html\n{html_context}\n```\n\nNow, please create a new design based on this HTML and my request: {body.prompt}"
    else:
        user_prompt = body.prompt

    # FIX: Do NOT await here. We need the generator object, not its result.
    ai_stream_generator = stream_code(INITIAL_SYSTEM_PROMPT, user_prompt, body.model)
    
    return StreamingResponse(
        stream_html_generator(ai_stream_generator),
        media_type="text/plain; charset=utf-8"
    )

@app.put("/api/ask-ai")
async def ask_ai_put(request: Request, body: AskAiPutRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    if not body.html:
        raise HTTPException(status_code=400, detail="HTML content is required for an update.")
    
    if body.model not in MODELS:
        raise HTTPException(status_code=400, detail="Invalid model selected")

    system_prompt, user_prompt = create_follow_up_prompt(
        prompt=body.prompt,
        html=body.html,
        selected_element_html=body.selectedElementHtml
    )

    patch_instructions = await generate_code(system_prompt, user_prompt, body.model)
    
    try:
        updated_html = apply_diff_patch(body.html, patch_instructions)
        return JSONResponse(content={"ok": True, "html": updated_html})
    except Exception as e:
        print(f"Error applying patch: {e}")
        raise HTTPException(status_code=500, detail="Failed to apply updates to the HTML.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
