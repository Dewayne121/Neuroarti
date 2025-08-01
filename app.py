import os
import uuid
import requests
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

# --- Configuration (PEXELS_API_KEY is now important) ---
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY") # Add a Pexels API key for best results

if not TOGETHER_API_KEY:
    raise ValueError("TOGETHER_API_KEY not found.")
if not GOOGLE_API_KEY:
    print("Warning: GOOGLE_API_KEY not found. The Gemini model will not be available.")
if not PEXELS_API_KEY:
    print("Warning: PEXELS_API_KEY not found. Image generation will use generic fallbacks.")

together_client = OpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

MODEL_MAPPING_TOGETHER = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-0528-tput" 
}

# --- The NEW Definitive Image Engine ---

def get_hardcoded_fallback_images() -> List[str]:
    """Returns a list of high-quality, guaranteed-to-work Unsplash image URLs."""
    return [
        "https://images.pexels.com/photos/3184418/pexels-photo-3184418.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
        "https://images.pexels.com/photos/3183197/pexels-photo-3183197.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
        "https://images.pexels.com/photos/3184339/pexels-photo-3184339.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
        "https://images.pexels.com/photos/2422294/pexels-photo-2422294.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
        "https://images.pexels.com/photos/1181244/pexels-photo-1181244.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
        "https://images.pexels.com/photos/577585/pexels-photo-577585.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    ]

def find_image_from_pexels(query: str) -> str:
    """Searches Pexels API for an image and returns a URL if found."""
    if not PEXELS_API_KEY:
        return ""
    try:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=7
        )
        if response.status_code == 200:
            photos = response.json().get('photos', [])
            if photos:
                return random.choice(photos)['src']['large2x']
    except Exception as e:
        print(f"Pexels API error for query '{query}': {e}")
    return ""

def extract_image_context(img_tag: BeautifulSoup) -> str:
    """Extracts context from alt text or nearby text to form an image search query."""
    alt_text = img_tag.get('alt', '').strip()
    if alt_text and len(alt_text) > 3:
        return alt_text
    
    parent = img_tag.find_parent()
    if parent:
        text_content = parent.get_text(separator=' ', strip=True)
        if text_content and len(text_content) > 10:
            first_sentence = text_content.split('.')[0]
            words = re.findall(r'\b[a-zA-Z]{4,}\b', first_sentence)
            return ' '.join(words[:4]) # Use first 4 long words
            
    return "technology abstract" # A reasonable default

def fix_image_sources_smart(html_content: str) -> str:
    """Replaces all image placeholders with the best available real images from Pexels or fallbacks."""
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        images = soup.find_all('img')
        
        for img in images:
            context_query = extract_image_context(img)
            
            # First, try to get a specific image from Pexels
            image_url = find_image_from_pexels(context_query)
            
            # If Pexels fails or no key, use a high-quality fallback
            if not image_url:
                image_url = random.choice(get_hardcoded_fallback_images())
            
            img['src'] = image_url
            if not img.get('alt'):
                img['alt'] = context_query
            img['loading'] = 'lazy'
            
            # Add classes to ensure the image displays well
            img_classes = img.get('class', [])
            if 'object-cover' not in img_classes:
                img_classes.append('object-cover')
            if 'w-full' not in img_classes:
                img_classes.append('w-full')
            if 'h-full' not in img_classes:
                img_classes.append('h-full')
            img['class'] = img_classes

        return str(soup)
    except Exception as e:
        print(f"Error in fix_image_sources_smart: {e}")
        return html_content

# --- THE NEW RELAXED RULESET ---
MANDATORY_RULESET = (
    "**MANDATORY RULESET (You MUST follow these rules on ALL responses):**\n"
    "1.  **STRUCTURE & COMPLETENESS:** Every page MUST include a `<header>`, a `<main>` with multiple diverse `<section>`s, and a detailed `<footer>`.\n"
    "2.  **VISIBILITY & CONTRAST (CRITICAL):** Ensure high color contrast. Dark text on light backgrounds, light text on dark backgrounds.\n"
    "3.  **IMAGES:** Use `<img>` tags liberally for visual appeal. **You are NOT responsible for the `src` URL.** Simply provide a highly descriptive `alt` attribute that explains what the image should show. For example: `<img alt=\"A modern web development team collaborating around a large monitor\">`. The system will automatically find and insert the best possible image. **Focus on great `alt` text.**\n"
)

# --- System Prompts (Updated with the new relaxed rules) ---
GLM_SUPERCHARGED_PROMPT = (
    "You are an elite AI web developer. Your response MUST be ONLY the full HTML code, starting with `<!DOCTYPE html>`.\n\n"
    f"{MANDATORY_RULESET}"
)
DEEPSEEK_SUPERCHARGED_PROMPT = (
    "You are a top-tier frontend architect. Your output must be ONLY the raw HTML code, beginning with `<!DOCTYPE html>`.\n\n"
    f"{MANDATORY_RULESET}"
)
GEMINI_2_5_LITE_SUPERCHARGED_PROMPT = (
    "You are a world-class AI developer. Your response MUST BE ONLY the full, valid HTML code, starting with `<!DOCTYPE html>`.\n\n"
    f"{MANDATORY_RULESET}"
)


# --- Helper Functions (Unchanged from last working version) ---
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

# --- AI Core Functions (Unchanged) ---
def generate_with_together(system_prompt: str, user_prompt: str, model_key: str):
    model_id = MODEL_MAPPING_TOGETHER.get(model_key)
    if not model_id:
        raise HTTPException(status_code=400, detail=f"Invalid model key for Together AI: {model_key}")
    response = together_client.chat.completions.create(model=model_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.1, max_tokens=8192)
    return response.choices[0].message.content or ""

def generate_with_google(system_prompt: str, user_prompt: str, model_id_str: str):
    if not GOOGLE_API_KEY:
         raise HTTPException(status_code=503, detail="Google API key not configured. Gemini model is unavailable.")
    model = genai.GenerativeModel(model_id_str)
    full_prompt = f"{system_prompt}\n\nUSER PROMPT: {user_prompt}"
    safety_settings = {'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE', 'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'}
    response = model.generate_content(full_prompt, safety_settings=safety_settings)
    return response.text

def generate_code(system_prompt: str, user_prompt: str, model_key: str):
    try:
        if model_key == "gemini-2.5-flash-lite":
            return generate_with_google(system_prompt, user_prompt, model_key)
        else:
            return generate_with_together(system_prompt, user_prompt, model_key)
    except Exception as e:
        print(f"Error calling AI model {model_key}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root(): 
    return "<h1>NeuroArti Pro Builder API is operational with Smart Image Engine.</h1>"

# --- API Endpoints with Smart Image Replacement ---
@app.post("/build")
def create_build(request: BuildRequest):
    system_prompt = {
        "glm-4.5-air": GLM_SUPERCHARGED_PROMPT,
        "deepseek-r1": DEEPSEEK_SUPERCHARGED_PROMPT,
        "gemini-2.5-flash-lite": GEMINI_2_5_LITE_SUPERCHARGED_PROMPT
    }.get(request.model, GLM_SUPERCHARGED_PROMPT)
        
    raw_code = generate_code(system_prompt, request.prompt, request.model)
    html_document = isolate_html_document(raw_code)
    
    if html_document:
        fixed_html_document = fix_image_sources_smart(html_document)
        container_id = f"neuroarti-container-{uuid.uuid4().hex[:8]}"
        body_html, css, js = extract_assets(fixed_html_document, container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": container_id}
        
    raise HTTPException(status_code=500, detail="AI failed to generate a valid HTML document.")

@app.post("/update")
def update_build(request: UpdateRequest):
    system_prompt = (f"You are an expert web developer modifying an existing webpage. Your response MUST be the complete, updated HTML file.\n\n{MANDATORY_RULESET}")
    full_html_for_ai = f"""<!DOCTYPE html><html><head><style>{request.css}</style></head><body><div id="{request.container_id}">{request.html}</div></body><script>{request.js}</script></html>"""
    user_prompt = f"USER REQUEST: '{request.prompt}'\n\nCURRENT WEBSITE CODE:\n{full_html_for_ai}"
    
    raw_code = generate_code(system_prompt, user_prompt, request.model)
    html_document = isolate_html_document(raw_code)

    if html_document:
        fixed_html_document = fix_image_sources_smart(html_document)
        body_html, css, js = extract_assets(fixed_html_document, request.container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": request.container_id}
        
    raise HTTPException(status_code=500, detail="AI failed to update the HTML document.")

@app.post("/edit-snippet")
def create_edit_snippet(request: EditSnippetRequest):
    system_prompt = (f"You are a context-aware HTML modification tool. Modify the element after the `<!-- EDIT_TARGET -->` comment. Your response MUST be ONLY the modified HTML snippet.\n\n{MANDATORY_RULESET}")
    user_prompt = f"INSTRUCTION: '{request.prompt}'.\n\nCONTEXTUAL HTML TO MODIFY:\n{request.contextual_snippet}"
    
    modified_snippet_raw = generate_code(system_prompt, user_prompt, request.model)
    fixed_snippet = fix_image_sources_smart(modified_snippet_raw)
    cleaned_snippet = clean_html_snippet(fixed_snippet)
    
    if cleaned_snippet and '<' in cleaned_snippet:
        return {"snippet": cleaned_snippet}
    return {"snippet": request.contextual_snippet.replace('<!-- EDIT_TARGET -->', '')}

@app.post("/patch-html")
def patch_html(request: PatchRequest):
    try:
        full_html_doc = f'<body><div id="{request.container_id}">{request.html}</div></body>'
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        element_to_modify = soup.select_one(request.parent_selector)
        if not element_to_modify:
            raise HTTPException(status_code=404, detail=f"Parent selector '{request.parent_selector}' not found.")
        
        if not request.new_parent_snippet or not request.new_parent_snippet.strip():
            raise HTTPException(status_code=400, detail="New parent snippet is empty.")
        
        fixed_snippet = fix_image_sources_smart(request.new_parent_snippet)
        new_snippet_soup = BeautifulSoup(fixed_snippet, 'html.parser')
        
        new_contents = new_snippet_soup.body.contents if new_snippet_soup.body else new_snippet_soup.contents
        if not new_contents:
            raise HTTPException(status_code=500, detail="Failed to parse new parent snippet.")

        parent_element_to_replace = element_to_modify.parent if element_to_modify.parent.name != 'body' else element_to_modify
        parent_element_to_replace.replace_with(*new_contents)
            
        final_container_div = soup.select_one(f'#{request.container_id}')
        if not final_container_div:
            # The patch might have replaced the container itself, find the new top-level element
            body_html = ''.join(str(c) for c in soup.body.contents)
        else:
             body_html = ''.join(str(c) for c in final_container_div.contents)
        return {"html": body_html, "css": request.css, "js": request.js}
    except Exception as e:
        print(f"Patching error: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
