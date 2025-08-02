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
    create_follow_up_prompt, # New dynamic prompt function
    DEFAULT_HTML
)
from core.models import MODELS
from core.utils import (
    ip_limiter,
    is_the_same_html,
    apply_diff_patch,
    # No longer need extract_assets, as we are working with a single HTML file
)

load_dotenv()

# --- Pydantic Models ---
class AskAiPostRequest(BaseModel):
    prompt: str
    model: str
    html: str | None = None
    # redesignMarkdown: str | None = None # You could add this later

class AskAiPutRequest(BaseModel):
    prompt: str
    model: str
    html: str
    selectedElementHtml: str | None = None # Key for unified updates

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
    """
    Processes an AI stream, filters for valid HTML, and yields clean chunks.
    This is the core of chatter prevention for streaming.
    """
    buffer = ""
    html_started = False
    html_ended = False

    async for chunk in ai_stream:
        if html_ended:
            continue  # Stop processing after </html> is found

        buffer += chunk

        if not html_started:
            # Wait for the HTML to start before yielding anything
            match = re.search(r'<!DOCTYPE html>', buffer, re.IGNORECASE)
            if match:
                html_started = True
                content_to_yield = buffer[match.start():]
                buffer = ""  # Clear buffer after yielding
                yield content_to_yield
        
        if html_started:
            # Once started, check for the end tag
            end_match = re.search(r'</html>', buffer, re.IGNORECASE)
            if end_match:
                html_ended = True
                content_to_yield = buffer[:end_match.end()]
                yield content_to_yield
                break # Terminate the generator
            
            # Yield chunks without the end tag, leaving the tail in the buffer
            last_newline = buffer.rfind('\n')
            if last_newline != -1:
                content_to_yield = buffer[:last_newline + 1]
                buffer = buffer[last_newline + 1:]
                yield content_to_yield
    
    # Yield any remaining part of the buffer if stream ends before </html>
    if html_started and not html_ended and buffer:
        yield buffer


@app.post("/api/ask-ai")
async def ask_ai_post(request: Request, body: AskAiPostRequest):
    """
    Handles initial website generation and full redesigns using a streaming response.
    """
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    if body.model not in MODELS:
        raise HTTPException(status_code=400, detail="Invalid model selected")

    # Determine if we should provide the existing HTML as context
    html_context = body.html if body.html and not is_the_same_html(body.html) else None
    
    if html_context:
        user_prompt = f"Here is my current HTML code:\n\n```html\n{html_context}\n```\n\nNow, please create a new design based on this HTML and my request: {body.prompt}"
    else:
        user_prompt = body.prompt

    ai_stream = stream_code(INITIAL_SYSTEM_PROMPT, user_prompt, body.model)
    
    return StreamingResponse(
        stream_html_generator(ai_stream),
        media_type="text/plain; charset=utf-8"
    )

@app.put("/api/ask-ai")
async def ask_ai_put(request: Request, body: AskAiPutRequest):
    """
    Handles all updates: targeted element rewrites and full-page diff-patch updates.
    This single endpoint replaces the previous PUT and rewrite endpoints.
    """
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    if not body.html:
        raise HTTPException(status_code=400, detail="HTML content is required for an update.")
    
    if body.model not in MODELS:
        raise HTTPException(status_code=400, detail="Invalid model selected")

    # Generate the system and user prompts dynamically based on the request type
    system_prompt, user_prompt = create_follow_up_prompt(
        prompt=body.prompt,
        html=body.html,
        selected_element_html=body.selectedElementHtml
    )

    patch_instructions = await generate_code(system_prompt, user_prompt, body.model)
    
    try:
        updated_html = apply_diff_patch(body.html, patch_instructions)
        # We return the full HTML, letting the frontend manage it.
        return JSONResponse(content={"ok": True, "html": updated_html})
    except Exception as e:
        print(f"Error applying patch: {e}")
        # Fallback: return original HTML on error to avoid breaking the user's page
        raise HTTPException(status_code=500, detail="Failed to apply updates to the HTML.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
