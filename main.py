# main.py
import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# FIX: Import the correct, unified function name
from core.ai_services import generate_code

# These imports are correct
from core.prompts import (
    MAX_REQUESTS_PER_IP,
    INITIAL_SYSTEM_PROMPT,
    FOLLOW_UP_SYSTEM_PROMPT
)
from core.models import MODELS
from core.utils import ip_limiter, is_the_same_html, apply_diff_patch

load_dotenv()

# --- Pydantic Models ---
class BuildRequest(BaseModel):
    prompt: str
    model: str
    html: str | None = None
    redesignMarkdown: str | None = None

class UpdateRequest(BaseModel):
    html: str
    prompt: str
    model: str
    selectedElementHtml: str | None = None

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
    
    user_prompt = ""
    if body.redesignMarkdown:
        user_prompt = f"Here is my current design as a markdown:\n\n{body.redesignMarkdown}\n\nNow, please create a new design based on this markdown."
    elif html_context:
        user_prompt = f"Here is my current HTML code:\n\n```html\n{html_context}\n```\n\nNow, please create a new design based on this HTML and my request: {body.prompt}"
    else:
        user_prompt = body.prompt

    # FIX: Call the unified 'generate_code' function with the correct system prompt for building
    ai_response_text = await generate_code(INITIAL_SYSTEM_PROMPT, user_prompt, body.model)
    
    # We are now sending the full response back as JSON, not streaming for this simplified model
    # A more complex implementation could re-introduce streaming if needed.
    return JSONResponse(content={"ok": True, "html": ai_response_text})


@app.put("/api/ask-ai")
async def diff_patch_update(request: Request, body: UpdateRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        return JSONResponse(status_code=429, content={"ok": False, "openLogin": True, "message": "Rate limit exceeded."})

    if not body.html:
        raise HTTPException(status_code=400, detail="HTML content is required for a patch update.")
    
    # For diff-patch, we can use the user-selected model
    if body.model not in MODELS:
        raise HTTPException(status_code=400, detail="Invalid model selected")

    user_prompt = f"The current code is:\n```html\n{body.html}\n```\n\nMy request is: '{body.prompt}'"
    if body.selectedElementHtml:
        user_prompt += f"\n\nI have selected a specific element to modify. Please confine your changes to ONLY this element and its children:\n```html\n{body.selectedElementHtml}\n```"

    # FIX: Call the unified 'generate_code' function with the correct system prompt for patching
    patch_instructions = await generate_code(FOLLOW_UP_SYSTEM_PROMPT, user_prompt, body.model)

    if not patch_instructions:
        print("Warning: AI returned empty patch. No changes will be applied.")
        return {"ok": True, "html": body.html}

    updated_html = apply_diff_patch(body.html, patch_instructions)

    return {"ok": True, "html": updated_html}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
