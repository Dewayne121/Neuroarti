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
from bs4 import BeautifulSoup # <-- Ensure this import is present

from core.ai_services import generate_code, stream_code
from core.element_rewriter import rewrite_element # <-- Make sure this new service is imported
from core.prompts import (
    MAX_REQUESTS_PER_IP,
    INITIAL_SYSTEM_PROMPT,
    FOLLOW_UP_SYSTEM_PROMPT,
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
    elementIdToReplace: str | None = None # The unique ID for reliable replacement

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def stream_html_generator(ai_stream_coroutine) -> AsyncGenerator[str, None]:
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
        updated_html = ""
        # --- HYBRID LOGIC ---
        if body.elementIdToReplace and body.selectedElementHtml:
            # --- Case 1: Targeted Element Rewrite (More Robust) ---
            print(f"INFO: Handling targeted element rewrite for ID: {body.elementIdToReplace}")
            new_element_html = await rewrite_element(
                prompt=body.prompt,
                selected_element_html=body.selectedElementHtml,
                model=body.model
            )
            
            # Use BeautifulSoup for reliable replacement
            soup = BeautifulSoup(body.html, 'lxml')
            target_element = soup.find(id=body.elementIdToReplace)
            
            if target_element:
                # The AI returns just the element, so we need to parse it into a tag
                new_element_soup = BeautifulSoup(new_element_html, 'lxml')
                # Find the first actual tag inside the parsed fragment
                new_tag = new_element_soup.find(lambda tag: tag.name != 'html' and tag.name != 'body')
                
                if new_tag:
                    # Remove the temporary ID before inserting
                    if 'id' in new_tag.attrs and new_tag['id'] == body.elementIdToReplace:
                        del new_tag['id']
                    target_element.replace_with(new_tag)
                    updated_html = str(soup)
                else: # AI failed to return a valid tag
                    raise Exception("AI did not return a valid HTML element for replacement.")
            else: # Couldn't find the temp ID
                raise Exception(f"Could not find element with temporary ID: {body.elementIdToReplace}")

        else:
            # --- Case 2: Global Page Update (Using Diff-Patch) ---
            print("INFO: Handling global page update with diff-patch.")
            user_prompt = (f"The current HTML document is:\n```html\n{body.html}\n```\n\nMy request for a global page update is: '{body.prompt}'")
            patch_instructions = await generate_code(FOLLOW_UP_SYSTEM_PROMPT, user_prompt, body.model)
            updated_html = apply_diff_patch(body.html, patch_instructions)

        return JSONResponse(content={"ok": True, "html": updated_html})
        
    except Exception as e:
        print(f"ERROR during update: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to apply updates: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
