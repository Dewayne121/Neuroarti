# main.py
import os
import uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup

from core.ai_services import generate_code
from core.prompts import (
    MAX_REQUESTS_PER_IP,
    INITIAL_SYSTEM_PROMPT,
    SYSTEM_PROMPT_REWRITE_ELEMENT # New, hyper-focused prompt
)
from core.models import MODELS
from core.utils import (
    ip_limiter,
    is_the_same_html,
    isolate_and_clean_html,
    extract_assets
)

load_dotenv()

# --- Pydantic Models ---
class BuildRequest(BaseModel):
    prompt: str
    model: str
    html: str | None = None

class EditElementRequest(BaseModel):
    prompt: str
    model: str
    html: str
    css: str
    js: str
    container_id: str
    selector: str # The unique CSS selector for the element

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

    return JSONResponse(content={
        "ok": True, "html": body_html, "css": css, "js": js, "container_id": container_id
    })

# NEW, DEDICATED ENDPOINT FOR SURGICAL EDITS
@app.put("/api/edit-element")
async def edit_element(request: Request, body: EditElementRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        return JSONResponse(status_code=429, content={"ok": False, "openLogin": True, "message": "Rate limit exceeded."})

    if not all([body.html, body.selector, body.prompt, body.container_id]):
        raise HTTPException(status_code=400, detail="Missing required fields for element edit.")
    
    # Reconstruct the document to find the element
    full_html_doc = f'<html><body><div id="{body.container_id}">{body.html}</div></body></html>'
    soup = BeautifulSoup(full_html_doc, 'html.parser')
    
    target_element = soup.select_one(body.selector)
    if not target_element:
        raise HTTPException(status_code=404, detail=f"Element with selector '{body.selector}' not found.")
    
    original_element_html = str(target_element)
    user_prompt = f"INSTRUCTION: '{body.prompt}'.\n\nCURRENT HTML ELEMENT:\n{original_element_html}"

    # Ask the AI to rewrite ONLY this element
    new_element_html = await generate_code(SYSTEM_PROMPT_REWRITE_ELEMENT, user_prompt, body.model)

    if not new_element_html or not new_element_html.strip().startswith('<'):
        raise HTTPException(status_code=500, detail="AI returned an invalid response for the element rewrite.")

    # Safely replace the old element with the new one
    new_element_soup = BeautifulSoup(new_element_html, 'html.parser')
    if new_element_soup.contents:
        target_element.replace_with(new_element_soup.contents[0])
    else:
        raise HTTPException(status_code=500, detail="Could not parse the new element from AI.")

    # Extract the full body content from the modified document
    final_container_div = soup.select_one(f"#{body.container_id}")
    updated_body_content = ''.join(str(c) for c in final_container_div.contents) if final_container_div else ""
    
    return JSONResponse(content={
        "ok": True,
        "html": updated_body_content,
        "css": body.css,
        "js": body.js,
        "container_id": body.container_id
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
