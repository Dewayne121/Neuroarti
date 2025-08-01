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
import google.generativeai as genai

# --- Pydantic Models (Unchanged) ---
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
    container_id: str

# --- Configuration (Unchanged) ---
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not TOGETHER_API_KEY:
    raise ValueError("TOGETHER_API_KEY not found. Please set it in your environment variables.")
if not GOOGLE_API_KEY:
    print("Warning: GOOGLE_API_KEY not found. The Gemini model will not be available.")

# Configure clients
together_client = OpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

MODEL_MAPPING_TOGETHER = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-0528-tput" 
}

# --- Supercharged System Prompts with Image Sourcing ---

# KEY CHANGE: Updated all three build prompts with specific image instructions.
GLM_SUPERCHARGED_PROMPT = (
    "You are an elite AI web developer. Your task is to create a stunning, complete, and modern webpage based on a user's prompt. "
    "Your response MUST BE ONLY the full, valid HTML code. Do not include any explanations, markdown like ```html, or comments. Your response must start immediately with `<!DOCTYPE html>`."
    "\n\n**-- MANDATORY TECHNICAL SPECIFICATIONS --**"
    "\n1.  **Technology Stack:** ..." # (abbreviated)
    "\n2.  **Structural Completeness & Depth:** ..." # (abbreviated)
    "\n3.  **Mandatory Elements:** ..." # (abbreviated)
    "\n4.  **Content & Imagery:**"
    "\n    - Generate rich, relevant, and plausible placeholder content (text, headlines, etc.)."
    "\n    - **Image Sourcing (Crucial):**"
    "\n        - For general scenes, backgrounds, and product photos, you MUST use specific photo URLs from Unsplash (e.g., `https://images.unsplash.com/photo-1543466835-00a7907e9de1`)."
    "\n        - For user avatars, profile pictures, or testimonials, you MUST use the `randomuser.me` portrait API (e.g., `<img src=\"https://randomuser.me/api/portraits/women/44.jpg\">` or `.../men/32.jpg`)."
    "\n5.  **Design, UX, and Responsiveness:** ..." # (abbreviated)
    "\n6.  **Code Quality:** ..." # (abbreviated)
)

DEEPSEEK_SUPERCHARGED_PROMPT = (
    "You are a top-tier frontend architect AI. Your sole function is to write production-ready, single-file HTML documents based on a user request. "
    "Your output must be ONLY the raw HTML code. No preamble, no markdown, no explanation. Your entire response begins with `<!DOCTYPE html>`."
    "\n\n**-- TECHNICAL DIRECTIVES --**"
    "\n1.  **Core Stack:** ..." # (abbreviated)
    "\n2.  **Architectural Blueprint:** ..." # (abbreviated)
    "\n3.  **Component-Level Detail:**"
    "\n    - Generate high-fidelity components..."
    "\n    - **Image Sourcing (Crucial):** For hero sections or galleries, use specific photo URLs from Unsplash (`https://images.unsplash.com/...`). For any user/avatar images (like in testimonials), use the `randomuser.me` portrait API (e.g., `https://randomuser.me/api/portraits/men/75.jpg`)."
    "\n4.  **Responsive Grid & Flexbox:** ..." # (abbreviated)
    "\n5.  **Micro-interactions & UX:** ..." # (abbreviated)
    "\n6.  **Code Standards:** ..." # (abbreviated)
)

GEMINI_2_5_LITE_SUPERCHARGED_PROMPT = (
    "You are a world-class AI developer that specializes in writing clean, modern, and production-ready single-file HTML webpages. "
    "Your response MUST BE ONLY the full, valid HTML code. Do not include any explanations, markdown like ```html, or any text outside of the `<!DOCTYPE html>` document."
    "\n\n**-- CORE REQUIREMENTS --**"
    "\n1.  **Framework:** ..." # (abbreviated)
    "\n2.  **Structure:** ..." # (abbreviated)
    "\n3.  **Responsiveness:** ..." # (abbreviated)
    "\n4.  **Content and Imagery:**"
    "\n    - Populate the page with high-quality, relevant placeholder text."
    "\n    - **Image Sourcing Rule:** For all background or thematic images, use specific URLs from Unsplash (`https://images.unsplash.com/photo-...`). For all people/profile images, use the `randomuser.me` API (`https://randomuser.me/api/portraits/...`)."
    "\n5.  **User Experience:** ..." # (abbreviated)
)


# --- Helper Functions (unchanged) ---
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
    if soup.body:
        return ''.join(str(c) for c in soup.body.contents)
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
            container_in_body = body_tag.find(id=container_id)
            if container_in_body and container_in_body.parent == body_tag:
                 body_content = ''.join(str(c) for c in container_in_body.contents)
            else:
                 body_content = ''.join(str(c) for c in body_tag.contents)
        else:
            body_content = ''
        return body_content, prefixed_css, js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Refactored AI Core Functions (unchanged) ---
def generate_with_together(system_prompt: str, user_prompt: str, model_key: str):
    model_id = MODEL_MAPPING_TOGETHER.get(model_key)
    if not model_id:
        raise HTTPException(status_code=400, detail=f"Invalid model key for Together AI: {model_key}")
    
    response = together_client.chat.completions.create(
        model=model_id,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.1, max_tokens=8192,
    )
    return response.choices[0].message.content or ""
def generate_with_google(system_prompt: str, user_prompt: str, model_id_str: str):
    if not GOOGLE_API_KEY:
         raise HTTPException(status_code=503, detail="Google API key not configured. Gemini model is unavailable.")
    
    model = genai.GenerativeModel(model_id_str)
    full_prompt = f"{system_prompt}\n\nUSER PROMPT: {user_prompt}"
    
    safety_settings = {
        'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
        'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
        'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
        'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE',
    }
    
    response = model.generate_content(full_prompt, safety_settings=safety_settings)
    return response.text
def generate_code(system_prompt: str, user_prompt: str, model_key: str):
    try:
        if model_key == "gemini-2.5-flash-lite":
            print(f"Generating code with Google Gemini: {model_key}")
            return generate_with_google(system_prompt, user_prompt, model_key)
        else:
            print(f"Generating code with Together AI: {model_key}")
            return generate_with_together(system_prompt, user_prompt, model_key)
    except Exception as e:
        print(f"Error calling AI model {model_key}: {e}")
        if hasattr(e, 'body') and 'error' in e.body:
             error_detail = e.body['error'].get('message', str(e))
             raise HTTPException(status_code=502, detail=f"AI service error: {error_detail}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")


# --- FastAPI App (Unchanged) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
@app.get("/", response_class=HTMLResponse)
async def root(): return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    if request.model == "gemini-2.5-flash-lite":
        system_prompt = GEMINI_2_5_LITE_SUPERCHARGED_PROMPT
    elif request.model == "deepseek-r1":
        system_prompt = DEEPSEEK_SUPERCHARGED_PROMPT
    else: # Default to GLM
        system_prompt = GLM_SUPERCHARGED_PROMPT

    raw_code = generate_code(system_prompt, request.prompt, request.model)
    html_document = isolate_html_document(raw_code)
    
    if html_document:
        container_id = f"neuroarti-container-{uuid.uuid4().hex[:8]}"
        body_html, css, js = extract_assets(html_document, container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": container_id}
    
    raise HTTPException(status_code=500, detail="AI failed to generate a valid HTML document.")


@app.post("/update")
async def update_build(request: UpdateRequest):
    # KEY CHANGE: Added image sourcing rule to update prompt.
    system_prompt = (
        "You are an expert web developer tasked with modifying an existing webpage. "
        "You will receive the complete HTML, CSS, and JS of the current page, along with a user's request for a high-level change. "
        "Intelligently modify the provided code to fulfill the request. Preserve the overall structure and design system. "
        "**CRITICAL:** Ensure the updated code remains fully responsive. If adding new images, use Unsplash for scenes and `randomuser.me/api/portraits/` for avatars. "
        "Your response MUST be the complete, updated HTML file, starting with <!DOCTYPE html>. No explanations or markdown."
    )
    full_html_for_ai = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><script src="https://cdn.tailwindcss.com"></script><style>{request.css}</style></head><body><div id="{request.container_id}">{request.html}</div></body><script>{request.js}</script></html>"""
    user_prompt = f"USER REQUEST: '{request.prompt}'\n\nCURRENT WEBSITE CODE:\n{full_html_for_ai}"
    raw_code = generate_code(system_prompt, user_prompt, request.model)
    html_document = isolate_html_document(raw_code)
    if html_document:
        body_html, css, js = extract_assets(html_document, request.container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": request.container_id}
    raise HTTPException(status_code=500, detail="AI failed to update the HTML document.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    # KEY CHANGE: Added image sourcing rule to snippet edit prompt.
    system_prompt = (
        "You are a context-aware HTML modification tool. You will receive an HTML snippet containing a `<!-- EDIT_TARGET -->` comment. "
        "Your task is to modify the single HTML element immediately following this comment based on the user's instruction. "
        "You MUST preserve the surrounding parent and sibling elements. Adhere to the existing Tailwind CSS classes and design patterns. "
        "**IMPORTANT:** Ensure your changes are responsive. When changing or adding images, use Unsplash.com for scenes and `randomuser.me/api/portraits/` for profile pictures. "
        "Your response MUST be ONLY the modified, larger HTML snippet, with the `<!-- EDIT_TARGET -->` comment removed. "
        "NO explanations, NO markdown."
    )
    user_prompt = f"INSTRUCTION: '{request.prompt}'.\n\nCONTEXTUAL HTML TO MODIFY:\n{request.contextual_snippet}"
    modified_snippet_raw = generate_code(system_prompt, user_prompt, request.model)
    cleaned_snippet = clean_html_snippet(modified_snippet_raw)
    if cleaned_snippet and '<' in cleaned_snippet:
        return {"snippet": cleaned_snippet}
    return {"snippet": request.contextual_snippet.replace('<!-- EDIT_TARGET -->', '')}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    # This endpoint's logic is correct and unchanged
    try:
        full_html_doc = f'<body><div id="{request.container_id}">{request.html}</div></body>'
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        element_to_modify = soup.select_one(request.parent_selector)
        if not element_to_modify:
            raise HTTPException(status_code=404, detail=f"Parent selector '{request.parent_selector}' not found in document.")
        container_in_soup = soup.select_one(f"#{request.container_id}")
        if not container_in_soup:
            raise HTTPException(status_code=500, detail="Internal Error: Could not find container in parsed soup.")
        if not request.new_parent_snippet or not request.new_parent_snippet.strip():
            raise HTTPException(status_code=400, detail="New parent snippet is empty.")
        new_snippet_soup = BeautifulSoup(request.new_parent_snippet, 'html.parser')
        new_contents = new_snippet_soup.body.contents if new_snippet_soup.body else new_snippet_soup.contents
        if not new_contents:
            raise HTTPException(status_code=500, detail="Failed to parse new parent snippet from AI response.")
        if element_to_modify == container_in_soup:
            print("Performing top-level patch. Clearing and appending content.")
            element_to_modify.clear()
            for node in new_contents:
                element_to_modify.append(node)
        else:
            print(f"Performing nested patch on selector: {request.parent_selector}")
            element_to_modify.replace_with(*new_contents)
        final_container_div = soup.select_one(f'#{request.container_id}')
        if not final_container_div:
            raise HTTPException(status_code=500, detail="Container element was lost after patching HTML.")
        body_html = ''.join(str(c) for c in final_container_div.contents)
        return {"html": body_html, "css": request.css, "js": request.js}
    except Exception as e:
        print(f"Patching error: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# --- Uvicorn runner ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
