import os
import uuid
import re
from typing import Dict
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from bs4 import BeautifulSoup, NavigableString
import google.generativeai as genai
import random

# --- Pydantic Models (Updated for the new architecture) ---
class BuildRequest(BaseModel):
    prompt: str
    model: str = "glm-4.5-air"

# This new model replaces all previous update/edit/patch models
class DiffAndPatchRequest(BaseModel):
    html: str
    css: str
    js: str
    prompt: str
    model: str = "glm-4.5-air"
    container_id: str

# --- Configuration (Unchanged) ---
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not TOGETHER_API_KEY:
    raise ValueError("TOGETHER_API_KEY not found.")
if not GOOGLE_API_KEY:
    print("Warning: GOOGLE_API_KEY not found. The Gemini model will not be available.")

together_client = OpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

MODEL_MAPPING_TOGETHER = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-0528-tput" 
}

# --- Image Engine & Helpers (Unchanged from the last working version) ---
def fix_broken_images_only(html_content: str) -> str:
    if not html_content: return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        images = soup.find_all('img')
        for img in images:
            current_src = img.get('src', '').strip()
            if not current_src:
                context_query = img.get('alt', '').strip()
                keywords = re.sub(r'[^a-zA-Z0-9\s,]', '', context_query).replace(' ', ',')
                img['src'] = f"https://source.unsplash.com/random/1200x800/?{keywords}" if keywords else "https://images.unsplash.com/photo-1557683316-973673baf926?w=1260&q=80"
        return str(soup)
    except Exception: return html_content

def isolate_html_document(raw_text: str) -> str:
    doctype_start = raw_text.lower().find('<!doctype html')
    return raw_text[doctype_start:] if doctype_start != -1 else raw_text

def extract_assets(html_content: str, container_id: str) -> tuple:
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css_content = "\n".join(style.string or '' for style in soup.find_all('style'))
        js_content = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        body_tag = soup.find('body')
        if body_tag:
            container_div = body_tag.find(id=container_id)
            if container_div:
                body_html = ''.join(str(c) for c in container_div.contents)
            else:
                body_html = ''.join(str(c) for c in body_tag.contents)
        else:
            body_html = ''
        return body_html, css_content.strip(), js_content.strip()
    except Exception as e:
        print(f"Asset extraction error: {e}")
        return html_content, "", ""

# --- NEW Deepsite-Inspired System Prompts ---
AETHER_INITIAL_BUILD_PROMPT = (
    "You are 'Aether,' an award-winning digital artist and frontend developer. Your mission is to create a single, standalone HTML file that is a piece of art. It must be aesthetically breathtaking, functional, and perfectly tailored to the user's prompt.\n\n"
    "**DESIGN MANIFESTO (MANDATORY):**\n"
    "1.  **CSS MASTERY:** Write rich, detailed custom CSS in the `<style>` tag. Define a sophisticated color palette using CSS variables (`:root { --primary: #...; }`) and import two complementary fonts from Google Fonts.\n"
    "2.  **ARTISTIC LAYOUT:** Create unique, interesting layouts for each section using CSS Grid and Flexbox. Use generous whitespace.\n"
    "3.  **INTERACTIVE ELEGANCE:** The page MUST feel alive. Use JavaScript for 'animate on scroll' effects via the `IntersectionObserver` API.\n"
    "4.  **IMAGE INTEGRATION (CRITICAL):** You are strongly encouraged to find and use specific, high-quality image URLs directly from services like `images.unsplash.com` or `images.pexels.com`. If you cannot, leave `src=\"\"` and write a highly descriptive `alt` attribute.\n\n"
    "**TECHNICAL DIRECTIVES:**\n"
    "- Your response is ONE single HTML file. Start immediately with `<!DOCTYPE html>`."
)

DEEPSITE_FOLLOW_UP_PROMPT = (
    "You are an expert web developer modifying an existing HTML file. You MUST output ONLY the changes required using the following SEARCH/REPLACE block format. Do NOT output the entire file. Do NOT include explanations or markdown.\n"
    "**FORMAT RULES:**\n"
    "1. Start each change with `<<<<<<< SEARCH` on its own line.\n"
    "2. Provide the exact lines from the current code that need to be replaced.\n"
    "3. Use `=======` on its own line to separate the search block from the replacement.\n"
    "4. Provide the new lines that should replace the original lines.\n"
    "5. End each change with `>>>>>>> REPLACE` on its own line.\n"
    "6. To insert code, provide the line *before* the insertion point in the SEARCH block and include that line plus the new lines in the REPLACE block.\n"
    "7. To delete code, provide the lines to delete in the SEARCH block and leave the REPLACE block empty.\n"
    "8. IMPORTANT: The SEARCH block must *exactly* match the current code, including indentation and whitespace."
)

# --- AI Core & Patching Logic ---
def generate_code(system_prompt: str, user_prompt: str, model_key: str, temperature: float = 0.3):
    model_id = MODEL_MAPPING_TOGETHER.get(model_key, "zai-org/GLM-4.5-Air-FP8")
    try:
        response = together_client.chat.completions.create(model=model_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=temperature, max_tokens=8192)
        return response.choices[0].message.content or ""
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

def apply_diff_patch(original_html: str, patch_text: str) -> str:
    """Applies a SEARCH/REPLACE patch to the original HTML."""
    if '<<<<<<< SEARCH' not in patch_text:
        print("Warning: AI returned invalid patch format. It may have returned a full HTML file instead.")
        # Check if the AI returned a full HTML doc by mistake
        if '</html>' in patch_text.lower():
            return patch_text
        return original_html
        
    modified_html = original_html
    patches = re.split(r'\s*<<<<<<< SEARCH\s*', patch_text)
    
    for patch in patches:
        if '=======' not in patch: continue
        
        try:
            search_part, replace_part = patch.split('=======', 1)
            search_block = search_part.strip('\n')
            
            replace_block = replace_part.split('>>>>>>> REPLACE')[0].strip('\n')
            
            if search_block:
                modified_html = modified_html.replace(search_block, replace_block, 1)
            else: # Handle insertion at the beginning of the file
                modified_html = replace_block + "\n" + modified_html

        except Exception as e:
            print(f"Could not apply patch block: {e}\nBlock: {patch}")

    return modified_html

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root(): return "<h1>NeuroArti API with Deepsite-inspired patching is operational.</h1>"

# --- API Endpoints ---
@app.post("/build")
def create_build(request: BuildRequest):
    """Generates the initial full HTML page."""
    raw_code = generate_code(AETHER_INITIAL_BUILD_PROMPT, request.prompt, request.model, temperature=0.3)
    html_document = isolate_html_document(raw_code)
    
    if html_document:
        fixed_html_document = fix_broken_images_only(html_document)
        container_id = f"neuroarti-container-{uuid.uuid4().hex[:8]}"
        body, css, js = extract_assets(fixed_html_document, container_id)
        return {"html": body, "css": css, "js": js, "container_id": container_id}
        
    raise HTTPException(status_code=500, detail="AI failed to generate initial build.")

@app.post("/diff-and-patch")
def diff_and_patch(request: DiffAndPatchRequest):
    """Generates a patch and applies it to the current HTML."""
    # Reconstruct the full HTML document for the AI to analyze
    full_html = f"""<!DOCTYPE html>
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
    <script>{request.js}</script>
</body>
</html>"""
    
    user_prompt = f"Apply the following change: '{request.prompt}' to the HTML code below."
    full_prompt_for_ai = f"{user_prompt}\n\n```html\n{full_html}\n```"

    patch_text = generate_code(DEEPSITE_FOLLOW_UP_PROMPT, full_prompt_for_ai, request.model, temperature=0.1)
    
    if not patch_text:
        raise HTTPException(status_code=500, detail="AI failed to generate a patch.")

    patched_html_full = apply_diff_patch(full_html, patch_text)
    fixed_patched_doc = fix_broken_images_only(patched_html_full)
    
    body, css, js = extract_assets(fixed_patched_doc, request.container_id)
    return {"html": body, "css": css, "js": js, "container_id": request.container_id}

# Uvicorn runner
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
