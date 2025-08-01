import os
import uuid
import re
from typing import Dict, List
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from bs4 import BeautifulSoup, NavigableString
import google.generativeai as genai
import random

# --- Pydantic Models (Updated for new endpoint) ---
class BuildRequest(BaseModel):
    prompt: str
    model: str = "glm-4.5-air"

class DiffAndPatchRequest(BaseModel):
    html: str
    prompt: str
    model: str = "glm-4.5-air"

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

# --- Image Engine & Helpers (Unchanged from last working version) ---
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
    return raw_text[doctype_start:] if doctype_start != -1 else raw_text # Return raw text if no doctype

def extract_assets(html_content: str) -> tuple:
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else ''
        return body_content, css.strip(), js.strip()
    except Exception: return html_content, "", ""

# --- System Prompts (Completely Re-architected) ---

# Prompt for the initial, high-quality build
AETHER_INITIAL_BUILD_PROMPT = (
    "You are 'Aether,' an award-winning digital artist and frontend developer. Your mission is to create a single, standalone HTML file that is a piece of art. It must be aesthetically breathtaking, functional, and perfectly tailored to the user's prompt.\n\n"
    "**DESIGN MANIFESTO:**\n"
    "1.  **CSS MASTERY:** Write rich, detailed custom CSS in the `<style>` tag. Define a sophisticated color palette using CSS variables (`:root { --primary: #...; }`) and import two complementary fonts from Google Fonts.\n"
    "2.  **ARTISTIC LAYOUT:** Create unique, interesting layouts for each section using CSS Grid and Flexbox. Use generous whitespace.\n"
    "3.  **INTERACTIVE ELEGANCE:** The page MUST feel alive. Use JavaScript for 'animate on scroll' effects via the `IntersectionObserver` API.\n"
    "4.  **IMAGE INTEGRATION (CRITICAL):** You are strongly encouraged to find and use specific, high-quality image URLs directly from services like `images.unsplash.com` or `images.pexels.com`. If you cannot, leave `src=\"\"` and write a highly descriptive `alt` attribute.\n\n"
    "**TECHNICAL DIRECTIVES:**\n"
    "- Your response is ONE single HTML file. Start immediately with `<!DOCTYPE html>`."
)

# Prompt for generating precise diff patches, inspired by Deepsite
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
    "8. IMPORTANT: The SEARCH block must *exactly* match the current code, including indentation and whitespace.\n\n"
    "**EXAMPLE:**\n"
    "<<<<<<< SEARCH\n"
    "    <h1>Old Title</h1>\n"
    "=======\n"
    "    <h1>A New, Better Title</h1>\n"
    ">>>>>>> REPLACE"
)

# --- AI Core & Patching Logic ---

def generate_code(system_prompt: str, user_prompt: str, model_key: str, temperature: float = 0.3):
    model_id = MODEL_MAPPING_TOGETHER.get(model_key, "zai-org/GLM-4.5-Air-FP8")
    try:
        response = together_client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=temperature,
            max_tokens=8192
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"Error calling AI model {model_key}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

def apply_diff_patch(original_html: str, patch_text: str) -> str:
    """Applies a SEARCH/REPLACE patch to the original HTML."""
    if '<<<<<<< SEARCH' not in patch_text:
        # The AI failed to follow instructions, return original content
        print("Warning: AI did not return a valid patch. Returning original HTML.")
        return original_html
        
    # Split the patch text into individual patch blocks
    patches = re.split(r'<<<<<<< SEARCH', patch_text)
    modified_html = original_html
    
    for patch in patches:
        if '=======' not in patch or '>>>>>>> REPLACE' not in patch:
            continue
        
        parts = re.split(r'=======\n|>>>>>>> REPLACE', patch)
        search_block = parts[0].strip('\n')
        replace_block = parts[1].strip('\n')
        
        # Use count=1 to only replace the first occurrence found
        modified_html = modified_html.replace(search_block, replace_block, 1)
        
    return modified_html

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root(): return "<h1>NeuroArti Pro Builder API is operational with Deepsite-inspired patching.</h1>"

# --- API Endpoints (Re-architected) ---

@app.post("/build")
def create_build(request: BuildRequest):
    """Generates the initial full HTML page."""
    raw_code = generate_code(AETHER_INITIAL_BUILD_PROMPT, request.prompt, request.model, temperature=0.3)
    html_document = isolate_html_document(raw_code)
    
    if html_document:
        # Only fix images with empty src attributes
        fixed_html_document = fix_broken_images_only(html_document)
        body, css, js = extract_assets(fixed_html_document)
        return {"html": body, "css": css, "js": js}
        
    raise HTTPException(status_code=500, detail="AI failed to generate initial build.")

@app.post("/diff-and-patch")
def diff_and_patch(request: DiffAndPatchRequest):
    """Generates a patch and applies it to the current HTML."""
    # Create the user prompt for the patching AI
    user_prompt = f"Apply the following change to the HTML code below: {request.prompt}\n\n```html\n{request.html}\n```"
    
    # Generate the patch text
    patch_text = generate_code(DEEPSITE_FOLLOW_UP_PROMPT, user_prompt, request.model, temperature=0.0) # Low temp for precision
    
    if not patch_text:
        raise HTTPException(status_code=500, detail="AI failed to generate a patch.")

    # Apply the patch to the original HTML
    patched_html = apply_diff_patch(request.html, patch_text)
    
    # Extract assets from the newly patched full HTML document
    # Note: We need a full structure for the asset extractor to work
    full_patched_doc = f"<!DOCTYPE html><html><body>{patched_html}</body></html>"
    fixed_patched_doc = fix_broken_images_only(full_patched_doc) # Fix images that may have been added
    
    body, css, js = extract_assets(fixed_patched_doc)
    return {"html": body, "css": css, "js": js}

# Uvicorn runner
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
