import gradio as gr
import os
import uuid
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

class UpdateRequest(BaseModel):
    html: str
    css: str
    js: str
    prompt: str
    model: str = "glm-4.5-air"
    container_id: str

class EditSnippetRequest(BaseModel):
    contextual_snippet: str
    prompt: str
    model: str = "glm-4.5-air"

class PatchRequest(BaseModel):
    html: str
    parent_selector: str
    new_parent_snippet: str
    css: str
    js: str

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
def prefix_css_rules(css_content: str, container_id: str) -> str:
    if not container_id: return css_content
    def prefixer(match):
        selectors = [f"#{container_id} {s.strip()}" for s in match.group(1).split(',')]
        return ", ".join(selectors) + match.group(2)
    css_content = re.sub(r'([^\r\n,{}]+(?:,[^\r\n,{}]+)*)(\s*{)', prefixer, css_content)
    css_content = re.sub(r'(@media[^{]*{\s*)(.*?)(\s*})', 
                         lambda m: m.group(1) + re.sub(r'([^\r\n,{}]+(?:,[^\r\n,{}]+)*)(\s*{)', prefixer, m.group(2)) + m.group(3), 
                         css_content, flags=re.DOTALL)
    return css_content

def clean_chatter_and_invalid_tags(soup_or_tag):
    if not hasattr(soup_or_tag, 'children'): return
    nodes_to_remove = [child for child in list(soup_or_tag.children) 
                       if (isinstance(child, NavigableString) and child.string.strip() and soup_or_tag.name in ['body', 'div', 'section', 'header', 'footer', 'main']) 
                       or (hasattr(child, 'name') and child.name in ['think', 'thought', 'explanation'])]
    for node in nodes_to_remove: node.decompose()
    for child in soup_or_tag.children:
        if hasattr(child, 'name'):
            clean_chatter_and_invalid_tags(child)

def isolate_html_document(raw_text: str) -> str:
    doctype_start = raw_text.lower().find('<!doctype html')
    return raw_text[doctype_start:] if doctype_start != -1 else ""

def clean_html_snippet(text: str) -> str:
    soup = BeautifulSoup(text, 'html.parser')
    clean_chatter_and_invalid_tags(soup)
    return str(soup)

def extract_assets(html_content: str, container_id: str) -> tuple:
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css_content = "\n".join(style.string or '' for style in soup.find_all('style'))
        prefixed_css = prefix_css_rules(css_content, container_id)
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        body_tag = soup.find('body')
        if body_tag:
            clean_chatter_and_invalid_tags(body_tag)
            body_content = ''.join(str(c) for c in body_tag.contents)
        else:
            body_content = ''
        return body_content, prefixed_css, js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str):
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1, max_tokens=8192,
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
        "Start your response immediately with <!DOCTYPE html>. No explanations, no comments, no markdown. "
        "Generate a complete single HTML file using Tailwind CSS via CDN. "
        "Place CSS in <style> tags and JS in <script> tags. RESPOND WITH ONLY HTML CODE."
    )
    raw_code = generate_code(system_prompt, request.prompt, model_id)
    html_document = isolate_html_document(raw_code)
    
    if html_document:
        container_id = f"neuroarti-container-{uuid.uuid4().hex[:8]}"
        body_html, css, js = extract_assets(html_document, container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": container_id}
    
    raise HTTPException(status_code=500, detail="AI failed to generate a valid HTML document.")

# --- NEW ENDPOINT FOR GENERAL UPDATES ---
@app.post("/update")
async def update_build(request: UpdateRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING.get("glm-4.5-air"))
    system_prompt = (
        "You are an expert web developer tasked with modifying an existing webpage. "
        "You will receive the complete HTML, CSS, and JS of the current page, along with a user's request for a high-level change. "
        "Intelligently modify the provided code to fulfill the request. Preserve the overall structure and content as much as possible, only making the necessary changes. "
        "Your response MUST be the complete, updated HTML file, starting with <!DOCTYPE html> and including the modified <style> and <script> tags. "
        "No explanations, no markdown. RESPOND WITH ONLY THE FULL HTML CODE."
    )

    # Reconstruct the full HTML document to send to the AI
    full_html_for_ai = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>{request.css}</style>
</head>
<body>
    <div id="{request.container_id}">
        {request.html}
    </div>
</body>
<script>{request.js}</script>
</html>"""

    user_prompt = f"USER REQUEST: '{request.prompt}'\n\nCURRENT WEBSITE CODE:\n{full_html_for_ai}"

    raw_code = generate_code(system_prompt, user_prompt, model_id)
    html_document = isolate_html_document(raw_code)

    if html_document:
        # Re-extract assets, which will also re-prefix the CSS correctly with the original container ID
        body_html, css, js = extract_assets(html_document, request.container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": request.container_id}

    raise HTTPException(status_code=500, detail="AI failed to update the HTML document.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
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
    
    if cleaned_snippet and '<' in cleaned_snippet:
        return {"snippet": cleaned_snippet}
    
    return {"snippet": request.contextual_snippet.replace('<!-- EDIT_TARGET -->', '')}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        parent_element = soup.select_one(request.parent_selector)
        if not parent_element:
            raise HTTPException(status_code=404, detail=f"Parent selector '{request.parent_selector}' not found.")
        if not request.new_parent_snippet or not request.new_parent_snippet.strip():
            raise HTTPException(status_code=400, detail="New parent snippet is empty.")
        new_snippet_soup = BeautifulSoup(request.new_parent_snippet, 'html.parser')
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new parent snippet.")
        parent_element.replace_with(*new_snippet_soup.contents)
        body_html = ''.join(str(c) for c in soup.body.contents)
        return {"html": body_html, "css": request.css, "js": request.js}
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
