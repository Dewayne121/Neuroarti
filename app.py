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
    "deepseek-r1": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct" 
}

# --- Helper Functions ---
def clean_html_response(raw_response: str, is_snippet=False) -> str:
    cleaned = re.sub(r'```html\n?', '', raw_response, flags=re.IGNORECASE)
    cleaned = re.sub(r'```', '', cleaned)
    
    if is_snippet:
        return cleaned.strip()

    doctype_match = re.search(r'<!DOCTYPE html.*?>', cleaned, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return cleaned[doctype_match.start():].strip()
    return cleaned.strip()

def extract_assets(html_content: str) -> tuple:
    soup = BeautifulSoup(html_content, 'html.parser')
    css = "\n".join(style.string or '' for style in soup.find_all('style'))
    js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
    
    for tag in soup.find_all(['style', 'script']):
        tag.decompose()
        
    body_content = soup.find('body')
    return str(body_content) if body_content else '', css.strip(), js.strip()

# --- AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.7, max_tokens=4096,
        )
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html, is_snippet=is_snippet)
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    system_prompt = (
        "You are an expert frontend developer. Generate a complete, single HTML file using Tailwind CSS via CDN. "
        "Place all CSS in one `<style>` tag in the `<head>` and all JS in one `<script>` tag before `</body>`. "
        "Your output must be ONLY the raw HTML code, starting with `<!DOCTYPE html>`. No explanations."
    )
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code:
        body_html, css, js = extract_assets(html_code)
        return {"html": body_html, "css": css, "js": js}
    raise HTTPException(status_code=500, detail="Failed to generate website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    system_prompt = (
        "You are a precise HTML code editor. You will be given an HTML snippet. "
        "Your task is to modify this snippet based on the user's request. "
        "Return ONLY the new, modified HTML snippet. Do not provide explanations, context, or markdown."
    )
    user_prompt = f"User Request: '{request.prompt}'.\n\nHTML Snippet to Edit:\n```html\n{request.snippet}\n```"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    if modified_snippet:
        return {"snippet": modified_snippet}
    raise HTTPException(status_code=500, detail="Failed to edit snippet.")

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        soup = BeautifulSoup(request.html, 'html.parser')
        target_element = soup.select_one(request.selector)
        
        if not target_element:
            raise HTTPException(status_code=404, detail="Selector did not find any element to patch.")
            
        # The new snippet is also a string, so it needs to be parsed into a tag
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        new_tag = new_snippet_soup.find() # Find the first tag in the snippet
        
        if new_tag:
            target_element.replace_with(new_tag)
        else: # If parsing fails, treat as plain text
            target_element.replace_with(request.new_snippet)

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
