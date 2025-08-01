# main.py
import os
import uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup, Tag

from core.ai_services import generate_code
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
    isolate_and_clean_html,
    extract_assets
)

load_dotenv()

class BuildRequest(BaseModel):
    prompt: str
    model: str
    html: str | None = None

class UpdateRequest(BaseModel):
    prompt: str
    model: str
    html: str 
    css: str
    js: str
    container_id: str
    selectedElementHtml: str | None = None # This is now optional for the unified endpoint

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/ask-ai")
async def build_or_full_update(request: Request, body: BuildRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        return JSONResponse(status_code=429, content={"ok": False, "openLogin": True, "message": "Rate limit exceeded."})
    if body.model not in MODELS:
        raise HTTPException(status_code=400, detail="Invalid model selected")
    html_context = body.html if body.html and not is_the_same_html(body.html) else None
    user_prompt = f"My request is: {body.prompt}"
    if html_context:
        user_prompt = f"Here is my current HTML code:\n\n```html\n{html_context}\n```\n\nNow, please create a new design based on this HTML and my request: {body.prompt}"
    ai_response_text = await generate_code(INITIAL_SYSTEM_PROMPT, user_prompt, body.model)
    clean_html_doc = isolate_and_clean_html(ai_response_text)
    if not clean_html_doc:
        raise HTTPException(status_code=500, detail="AI failed to generate valid HTML content.")
    container_id = f"neuroarti-container-{uuid.uuid4().hex[:8]}"
    body_html, css, js = extract_assets(clean_html_doc, container_id)
    return JSONResponse(content={"ok": True, "html": body_html, "css": css, "js": js, "container_id": container_id})

@app.put("/api/ask-ai")
async def unified_diff_patch_update(request: Request, body: UpdateRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        return JSONResponse(status_code=429, content={"ok": False, "openLogin": True, "message": "Rate limit exceeded."})
    if not body.html:
        raise HTTPException(status_code=400, detail="HTML content is required.")
    if body.model not in MODELS:
        raise HTTPException(status_code=400, detail="Invalid model selected")

    # --- Inspired by deepsite-v2: Construct a context-rich prompt ---
    user_prompt = f"The current code is:\n```html\n{body.html}\n```\n\n"

    if body.selectedElementHtml:
        # If an element is selected, give the AI forceful, specific instructions
        user_prompt += (
            "CRITICAL INSTRUCTION: The user has selected a specific element to modify. "
            "You MUST confine your changes to ONLY this element and its children. "
            f"Here is the selected element:\n```html\n{body.selectedElementHtml}\n```\n\n"
            f"The user's request for this specific element is: '{body.prompt}'"
        )
    else:
        # If no element is selected, it's a global update request
        user_prompt += f"My request for a global page update is: '{body.prompt}'"

    patch_instructions = await generate_code(FOLLOW_UP_SYSTEM_PROMPT, user_prompt, body.model)
    
    soup = BeautifulSoup(body.html, 'html.parser')
    original_body_content = ''.join(str(c) for c in soup.body.contents) if soup.body else body.html
    
    if not patch_instructions or SEARCH_START not in patch_instructions:
        print("Warning: AI returned an invalid or empty patch. No changes applied.")
        return JSONResponse(content={"ok": True, "html": original_body_content, "css": body.css, "js": body.js, "container_id": body.container_id})
    
    updated_full_html = apply_diff_patch(body.html, patch_instructions)
    updated_body_content, updated_css, updated_js = extract_assets(updated_full_html, body.container_id)
    
    return JSONResponse(content={
        "ok": True, 
        "html": updated_body_content, 
        "css": updated_css, 
        "js": updated_js, 
        "container_id": body.container_id
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
