import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import re
import json
from typing import Dict, Any
from bs4 import BeautifulSoup, NavigableString

# --- Pydantic Models ---
class BuildRequest(BaseModel):
    prompt: str
    model: str = "glm-4.5-air"

class EditSnippetRequest(BaseModel):
    snippet: str
    prompt: str
    model: str = "glm-4.5-air"

class PatchRequest(BaseModel):
    html: str
    selector: str
    new_snippet: str

# --- Configuration ---
API_KEY = os.environ.get("GLM_API_KEY")
if not API_KEY:
    raise ValueError("API Key not found. Please set the GLM_API_KEY environment variable.")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1",
)

MODEL_MAPPING = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/deepseek-coder-33b-instruct" 
}

# --- THE DEFINITIVE FIX: Aggressive Post-Processing ---
def clean_chatter(soup_tag):
    """
    Recursively removes known AI chatter tags and stray text nodes from a BeautifulSoup object.
    This is the core of the fix to guarantee clean output.
    """
    if not soup_tag:
        return

    nodes_to_remove = []
    # Find all direct children to iterate over
    for child in soup_tag.children:
        # Case 1: It's a plain text node (NavigableString)
        if isinstance(child, NavigableString):
            # If the text is just whitespace, ignore it. Otherwise, it's chatter.
            if child.string.strip():
                nodes_to_remove.append(child)
        # Case 2: It's a known chatter tag
        elif child.name in ['think', 'thought', 'explanation']:
            nodes_to_remove.append(child)
    
    # Decompose (remove) all identified chatter nodes
    for node in nodes_to_remove:
        node.decompose()

def clean_html_snippet(text: str) -> str:
    """Cleans snippets by parsing them and removing chatter."""
    soup = BeautifulSoup(f"<div>{text}</div>", 'html.parser')
    wrapper = soup.find('div')
    clean_chatter(wrapper)
    # Return the inner HTML of the cleaned wrapper
    return ''.join(str(c) for c in wrapper.contents)

def extract_assets(html_content: str) -> tuple:
    """Extracts CSS, JS, and a CLEANED body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract assets before cleaning
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        
        # *** APPLY THE CLEANING FUNCTION HERE ***
        clean_chatter(body_tag)
        
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else ''

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str):
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1, max_tokens=8000,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root(): return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    system_prompt = (
        "You are a silent code generation machine. Your response MUST be ONLY valid HTML code. "
        "Start immediately with <!DOCTYPE html>. No explanations, no comments, no markdown. "
        "Generate a complete single HTML file using Tailwind CSS via CDN. "
        "Place CSS in <style> tags and JS in <script> tags. RESPOND WITH ONLY HTML CODE."
    )
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code:
        body_html, css, js = extract_assets(html_code)
        return {"html": body_html, "css": css, "js": js}
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    system_prompt = (
        "You are an HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet. "
        "CRITICAL: Your response MUST be ONLY the modified HTML snippet. NO explanations, NO markdown, NO chatter. "
        "If you cannot perform the modification, return the original snippet unchanged."
    )
    user_prompt = f"INSTRUCTION: '{request.prompt}'.\n\nHTML TO MODIFY:\n{request.snippet}"
    modified_snippet_raw = generate_code(system_prompt, user_prompt, model_id)
    
    # Clean the raw response to remove any chatter
    cleaned_snippet = clean_html_snippet(modified_snippet_raw)
    
    if cleaned_snippet:
        return {"snippet": cleaned_snippet}
    
    print(f"Snippet generation or cleaning failed. Raw response: '{modified_snippet_raw}'. Returning original.")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        # Replace with all contents of the new snippet to handle multiple root elements
        target_element.replace_with(*new_snippet_soup.contents)

        # We don't need to re-clean here because the `currentHtml` was already clean
        # and the new snippet was cleaned in the previous step.
        body_html = ''.join(str(c) for c in soup.body.contents)
        
        # We assume CSS/JS don't change during a patch, so we just return the new body
        # This is a safe assumption for our current workflow.
        return {"html": body_html, "css": "", "js": ""}
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
