# main.py
import os
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from typing import AsyncGenerator
from bs4 import BeautifulSoup
from core.ai_services import generate_code, stream_code
# No longer using element_rewriter, logic is now unified here
from core.prompts import (
    MAX_REQUESTS_PER_IP,
    INITIAL_SYSTEM_PROMPT,
    FOLLOW_UP_SYSTEM_PROMPT,
    SEARCH_START
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
    elementIdToReplace: str | None = None

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def stream_html_generator(ai_stream_coroutine) -> AsyncGenerator[str, None]:
    # ... (no changes to this function)
    ai_stream = await ai_stream_coroutine
    buffer = ""
    html_started = False
    html_ended = False
    async for chunk in ai_stream:
        if html_ended: continue
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
    # ... (no changes to this function)
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP): raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    if body.model not in MODELS: raise HTTPException(status_code=400, detail="Invalid model selected")
    html_context = body.html if body.html and not is_the_same_html(body.html) else None
    user_prompt = f"My request is: {body.prompt}"
    if html_context:
        user_prompt = f"Here is my current HTML code:\n\n```html\n{html_context}\n```\n\nNow, please create a new design based on this HTML and my request: {body.prompt}"
    
    ai_stream_coro = stream_code(INITIAL_SYSTEM_PROMPT, user_prompt, body.model)
    return StreamingResponse(stream_html_generator(ai_stream_coro), media_type="text/plain; charset=utf-8")


@app.put("/api/ask-ai")
async def ask_ai_put(request: Request, body: AskAiPutRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP): raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    if not body.html: raise HTTPException(status_code=400, detail="HTML content is required for an update.")
    if body.model not in MODELS: raise HTTPException(status_code=400, detail="Invalid model selected")
    
    try:
        # --- NEW: Unified Diff-Patch Logic (Inspired by DeepSite) ---
        user_prompt = ""

        if body.elementIdToReplace and body.selectedElementHtml:
            # Case 1: Targeted Element Rewrite
            print(f"INFO: Handling targeted element update for ID: {body.elementIdToReplace}")
            # This prompt structure forces the AI to focus only on the selected element within the full context.
            user_prompt = (
                "You are modifying a single element within an existing HTML file based on the user's request.\n\n"
                f"The FULL current HTML code is: \n```html\n{body.html}\n```\n\n"
                "CRITICAL: You must ONLY update the following specific element, NOTHING ELSE:\n\n"
                f"```html\n{body.selectedElementHtml}\n```\n\n"
                f"The user's instruction for the change is: '{body.prompt}'"
            )
        else:
            # Case 2: Global Page Update
            print("INFO: Handling global page update.")
            user_prompt = (
                f"The current HTML document is:\n```html\n{body.html}\n```\n\n"
                f"My request for a global page update is: '{body.prompt}'"
            )
        
        # Get the patch instructions from the AI
        patch_instructions = await generate_code(FOLLOW_UP_SYSTEM_PROMPT, user_prompt, body.model)
        
        # Clean the AI response to remove any chatter before the patch block
        patch_start_index = patch_instructions.find(SEARCH_START)
        if patch_start_index == -1:
            raise Exception("AI response did not contain a valid SEARCH/REPLACE block. Update failed.")
        
        # Isolate just the patch block(s)
        cleaned_patch = patch_instructions[patch_start_index:]
        
        # Apply the patch to the original HTML
        updated_html = apply_diff_patch(body.html, cleaned_patch)

        # Final cleanup: If the temp ID somehow survived the replacement, remove it.
        # This makes the process resilient.
        if body.elementIdToReplace:
            soup = BeautifulSoup(updated_html, 'lxml')
            target_element = soup.find(id=body.elementIdToReplace)
            if target_element:
                del target_element['id']
            updated_html = str(soup)

        return JSONResponse(content={"ok": True, "html": updated_html})
        
    except Exception as e:
        print(f"ERROR during update: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to apply updates: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
