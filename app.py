import os
import uuid
import requests
import json
import time
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import re
from typing import Dict, List
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

# --- Configuration (Unchanged) ---
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

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

# --- NEW: High-Quality Hardcoded Fallback Images ---
def get_hardcoded_fallback_images() -> List[str]:
    """
    Returns a list of high-quality, guaranteed-to-work Unsplash image URLs.
    This replaces unreliable placeholders.
    """
    return [
        "https://images.unsplash.com/photo-1557683316-973673baf926?w=800&q=80", # Blue/Purple Gradient
        "https://images.unsplash.com/photo-1528459801416-a9e53bbf4e17?w=800&q=80", # Watercolor texture
        "https://images.unsplash.com/photo-1533134486753-c833f0ed4866?w=800&q=80", # Black/White abstract
        "https://images.unsplash.com/photo-1501630834273-4b5604d2ee31?w=800&q=80", # Clouds
        "https://images.unsplash.com/photo-1488998427799-e3362cec87c3?w=800&q=80", # Desk/Office
        "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=800&q=80", # Team working
        "https://images.unsplash.com/photo-1554629947-334ff61d85dc?w=800&q=80", # Mountains
    ]

# --- REVISED: Image Search Functions ---
def search_api_images(query: str) -> List[str]:
    """Search Pexels and Unsplash using official APIs if keys are available."""
    urls = []
    # Prioritize Pexels if available, it's often faster
    if PEXELS_API_KEY:
        try:
            response = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": 5, "orientation": "landscape"},
                headers={"Authorization": PEXELS_API_KEY},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                urls.extend([photo['src']['large2x'] for photo in data.get('photos', [])])
        except Exception as e:
            print(f"Pexels API error: {e}")
    
    # Try Unsplash API if no Pexels results or no key
    if not urls and UNSPLASH_ACCESS_KEY:
        try:
            response = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 5, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                urls.extend([photo['urls']['regular'] for photo in data.get('results', [])])
        except Exception as e:
            print(f"Unsplash API error: {e}")
            
    return urls

def find_best_image_url(query: str) -> str:
    """Finds the best available image URL, prioritizing APIs and falling back to high-quality images."""
    # Attempt to get a relevant image from APIs
    api_results = search_api_images(query)
    if api_results:
        return random.choice(api_results)
    
    # If APIs fail or don't return results, use a dynamic Unsplash source URL
    # This is less reliable but provides more variety than hardcoded fallbacks
    try:
        clean_query = re.sub(r'[^a-zA-Z0-9,]', '', query.replace(' ', ','))
        if clean_query:
            return f"https://source.unsplash.com/800x600/?{clean_query}"
    except:
        pass # Fall through to hardcoded if this fails

    # As a final, guaranteed step, return a random high-quality hardcoded image
    return random.choice(get_hardcoded_fallback_images())

def extract_image_context(img_tag: BeautifulSoup) -> str:
    """Extracts context from alt text or nearby text to form an image search query."""
    alt_text = img_tag.get('alt', '').strip()
    if alt_text and len(alt_text) > 3:
        return alt_text
    
    parent = img_tag.find_parent()
    if parent:
        # Get text from siblings and parent
        text_content = parent.get_text(separator=' ', strip=True)
        if text_content and len(text_content) > 10:
             # A simple heuristic to find a "subject"
            first_sentence = text_content.split('.')[0]
            words = re.findall(r'\b[a-zA-Z]{4,}\b', first_sentence)
            # Find nouns or capitalized words as potential subjects
            meaningful_words = [w for w in words if not w.islower() or w.lower() not in ['this', 'that', 'with', 'from']]
            if meaningful_words:
                return ' '.join(meaningful_words[:3])

    return "technology abstract" # A better default query

def fix_image_sources_smart(html_content: str) -> str:
    """Replaces image placeholders with the best available real images."""
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        images = soup.find_all('img')
        
        for img in images:
            context_query = extract_image_context(img)
            best_url = find_best_image_url(context_query)
            img['src'] = best_url
            if not img.get('alt'):
                img['alt'] = context_query
            img['loading'] = 'lazy'
            img['class'] = img.get('class', []) + ['object-cover', 'w-full', 'h-full']

        return str(soup)
    except Exception as e:
        print(f"Major error in fix_image_sources_smart: {e}")
        return html_content

# --- Ruleset & Prompts (Unchanged) ---
MANDATORY_RULESET = (
    "**MANDATORY RULESET (You MUST follow these rules on ALL responses):**\n"
    "1.  **STRUCTURE & COMPLETENESS:** Every page MUST include a `<header>` with a `<nav>` bar, a logo (text or SVG), navigation links, a `<main>` tag with multiple diverse `<section>`s, and a detailed `<footer>`.\n"
    "2.  **VISIBILITY & CONTRAST (CRITICAL):** You MUST ensure high color contrast. If any element has a light background (e.g., `bg-white`, `bg-slate-100`), all text inside it MUST be a dark color (e.g., `text-gray-900`, `text-slate-800`). NEVER place light text on a light background.\n"
    "3.  **IMAGE USAGE:** Use `<img>` tags freely. You can leave the `src` attribute empty or use a placeholder like `<img src=\"\" alt=\"A team of developers collaborating\">`. The system will automatically find a high-quality, relevant image based on your `alt` text. **Descriptive `alt` text is critical.**\n"
)
GLM_SUPERCHARGED_PROMPT = (
    "You are an elite AI web developer creating a stunning, complete webpage. "
    "Your response MUST BE ONLY the full, valid HTML code, starting with `<!DOCTYPE html>`.\n\n"
    f"{MANDATORY_RULESET}"
)
DEEPSEEK_SUPERCHARGED_PROMPT = (
    "You are a top-tier frontend architect AI writing a production-ready, single-file HTML document. "
    "Your output must be ONLY the raw HTML code, beginning with `<!DOCTYPE html>`.\n\n"
    f"{MANDATORY_RULESET}"
)
GEMINI_2_5_LITE_SUPERCHARGED_PROMPT = (
    "You are a world-class AI developer writing a clean, modern, single-file HTML webpage. "
    "Your response MUST BE ONLY the full, valid HTML code, starting with `<!DOCTYPE html>`.\n\n"
    f"{MANDATORY_RULESET}"
)


# --- Helper Functions (Existing, Unchanged) ---
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
        if hasattr(e, 'body') and 'error' in e.body:
             error_detail = e.body['error'].get('message', str(e))
             raise HTTPException(status_code=502, detail=f"AI service error: {error_detail}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root(): 
    return "<h1>NeuroArti Pro Builder API is operational with Smart Image Search.</h1>"

# --- API Endpoints (Now Synchronous) ---
@app.post("/build")
def create_build(request: BuildRequest):
    if request.model == "gemini-2.5-flash-lite":
        system_prompt = GEMINI_2_5_LITE_SUPERCHARGED_PROMPT
    elif request.model == "deepseek-r1":
        system_prompt = DEEPSEEK_SUPERCHARGED_PROMPT
    else:
        system_prompt = GLM_SUPERCHARGED_PROMPT
        
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
    system_prompt = (
        "You are an expert web developer modifying an existing webpage. Your response MUST be the complete, updated HTML file.\n\n"
        f"{MANDATORY_RULESET}"
    )
    full_html_for_ai = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><script src="https://cdn.tailwindcss.com"></script><style>{request.css}</style></head><body><div id="{request.container_id}">{request.html}</div></body><script>{request.js}</script></html>"""
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
    system_prompt = (
        "You are a context-aware HTML modification tool. Modify the element after the `<!-- EDIT_TARGET -->` comment. "
        "Your response MUST be ONLY the modified HTML snippet.\n\n"
        f"{MANDATORY_RULESET}"
    )
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
        
        container_in_soup = soup.select_one(f"#{request.container_id}")
        if not container_in_soup:
            raise HTTPException(status_code=500, detail="Internal Error: Could not find container.")
        
        if not request.new_parent_snippet or not request.new_parent_snippet.strip():
            raise HTTPException(status_code=400, detail="New parent snippet is empty.")
        
        fixed_snippet = fix_image_sources_smart(request.new_parent_snippet)
        new_snippet_soup = BeautifulSoup(fixed_snippet, 'html.parser')
        
        new_contents = new_snippet_soup.body.contents if new_snippet_soup.body else new_snippet_soup.contents
        if not new_contents:
            raise HTTPException(status_code=500, detail="Failed to parse new parent snippet.")

        if element_to_modify == container_in_soup:
            element_to_modify.clear()
            for node in new_contents: element_to_modify.append(node)
        else:
            element_to_modify.replace_with(*new_contents)
            
        final_container_div = soup.select_one(f'#{request.container_id}')
        if not final_container_div:
            raise HTTPException(status_code=500, detail="Container element was lost after patching.")
        
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
