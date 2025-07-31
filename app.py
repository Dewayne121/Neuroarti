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
from bs4 import BeautifulSoup

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

# --- Enhanced Helper Functions (Based on your excellent approach) ---
def clean_html_response(raw_response: str, is_snippet=False) -> str:
    """Enhanced HTML cleaning with multiple fallback strategies"""
    if not raw_response:
        return ""
    
    cleaned = raw_response.strip()
    
    if is_snippet:
        return clean_html_snippet(cleaned)
    else:
        return clean_full_html_document(cleaned)

def clean_html_snippet(text: str) -> str:
    """Aggressively clean HTML snippets to remove AI chatter"""
    # Strategy 1: Extract from markdown code blocks (most common)
    code_patterns = [r'```html\s*\n(.*?)\n```', r'```\n(.*?)\n```']
    for pattern in code_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            extracted = match.group(1).strip()
            if extracted and '<' in extracted:
                return extracted

    # Strategy 2: Find the largest HTML block
    html_blocks = re.findall(r'<[^>]+>.*?</[^>]+>', text, re.DOTALL)
    if html_blocks:
        return max(html_blocks, key=len).strip()

    # Strategy 3: Last resort - extract everything between the first '<' and last '>'
    first_tag = text.find('<')
    last_tag = text.rfind('>')
    if first_tag != -1 and last_tag > first_tag:
        return text[first_tag:last_tag + 1].strip()

    # If no HTML is found, return empty to prevent injecting chatter
    return ""

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()

    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,
            max_tokens=4096,
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html, is_snippet=is_snippet)
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n1. Start immediately with <!DOCTYPE html>.\n2. No explanations or text before/after the HTML.\n"
        "3. No markdown formatting.\n4. Generate a complete single HTML file using Tailwind CSS via CDN.\n"
        "5. Place CSS in <style> tags and JS in <script> tags.\nRESPOND WITH ONLY HTML CODE."
    )
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        body_html, css, js = extract_assets(html_code)
        return {"html": body_html, "css": css, "js": js}
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    system_prompt = (
        "You are an HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n1. Your response must be ONLY the modified HTML snippet.\n2. NO explanations or text.\n"
        "3. NO markdown.\n4. If you cannot modify it, return the original snippet unchanged.\n"
        "5. Your response must start with '<' and end with '>'.\nRESPOND WITH ONLY HTML CODE."
    )
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and '<' in modified_snippet:
        return {"snippet": modified_snippet}
    
    print(f"Snippet generation or cleaning failed. AI response was: '{modified_snippet}'. Returning original.")
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
            
        new_tag = new_snippet_soup.contents[0]
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            target_element.replace_with(str(new_tag))

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
