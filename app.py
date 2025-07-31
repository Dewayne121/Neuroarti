import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import re
from typing import Dict
from bs4 import BeautifulSoup, NavigableString

# --- Pydantic Models ---
class BuildRequest(BaseModel):
    prompt: str
    model: str = "glm-4.5-air"

class EditSnippetRequest(BaseModel):
    contextual_snippet: str
    prompt: str
    model: str = "glm-4.5-air"

class PatchRequest(BaseModel):
    html: str
    parent_selector: str
    new_parent_snippet: str

# --- Configuration ---
API_KEY = os.environ.get("TOGETHER_API_KEY")
if not API_KEY:
    raise ValueError("API Key not found. Please set TOGETHER_API_KEY.")

client = OpenAI(api_key=API_KEY, base_url="https://api.together.xyz/v1")

MODEL_MAPPING = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-0528-tput" 
}

# --- Helper Functions ---
def clean_chatter(soup_tag):
    if not soup_tag: return
    nodes_to_remove = [child for child in soup_tag.children if isinstance(child, NavigableString) and child.string.strip()]
    for node in nodes_to_remove: node.decompose()

def clean_html_snippet(text: str) -> str:
    # Use BeautifulSoup to parse and get only the tag content, which strips outer chatter
    soup = BeautifulSoup(text, 'html.parser')
    # Find the first actual tag
    first_tag = soup.find(lambda tag: tag.name is not None)
    return str(first_tag) if first_tag else ""

def extract_assets(html_content: str) -> tuple:
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        body_tag = soup.find('body')
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
    # --- CONTEXT-AWARE SYSTEM PROMPT ---
    system_prompt = (
        "You are a context-aware HTML modification tool. You will receive an HTML snippet containing a `<!-- EDIT_TARGET -->` comment. "
        "Your task is to modify the single HTML element immediately following this comment based on the user's instruction. "
        "You MUST preserve the surrounding parent and sibling elements. "
        "Your response MUST be ONLY the modified, larger HTML snippet, with the `<!-- EDIT_TARGET -->` comment removed. "
        "NO explanations, NO markdown. Your entire response must be the updated HTML block."
    )
    user_prompt = f"INSTRUCTION: '{request.prompt}'.\n\nCONTEXTUAL HTML TO MODIFY:\n{request.contextual_snippet}"
    
    modified_snippet_raw = generate_code(system_prompt, user_prompt, model_id)
    cleaned_snippet = clean_html_snippet(modified_snippet_raw)
    
    if cleaned_snippet:
        return {"snippet": cleaned_snippet}
    
    print(f"Snippet generation or cleaning failed. Raw: '{modified_snippet_raw}'. Returning original context.")
    # Return original snippet minus the comment
    return {"snippet": request.contextual_snippet.replace('<!-- EDIT_TARGET -->', '')}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        # --- PATCH LOGIC NOW TARGETS THE PARENT ---
        parent_element = soup.select_one(request.parent_selector)
        if not parent_element:
            raise HTTPException(status_code=404, detail=f"Parent selector '{request.parent_selector}' not found.")
            
        if not request.new_parent_snippet or not request.new_parent_snippet.strip():
            raise HTTPException(status_code=400, detail="New parent snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_parent_snippet, 'html.parser')
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new parent snippet.")
            
        # Replace the original parent element with the new, modified parent element
        parent_element.replace_with(new_snippet_soup)

        body_html = ''.join(str(c) for c in soup.body.contents)
        
        return {"html": body_html, "css": "", "js": ""}
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
