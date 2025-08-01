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
import random

# --- Pydantic Models (from the more advanced version) ---
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

# --- Configuration (from the more advanced version) ---
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

# --- IMPROVED IMAGE SERVICE STRATEGY ---
def get_reliable_image_url(width: int, height: int, keywords: str = "", image_type: str = "general") -> str:
    """
    Generate reliable image URLs with multiple fallback strategies
    """
    if image_type == "avatar":
        # For avatars, use multiple services with fallbacks
        gender = random.choice(["men", "women"])
        number = random.randint(0, 99)
        avatar_services = [
            f"https://randomuser.me/api/portraits/{gender}/{number}.jpg",
            f"https://i.pravatar.cc/{min(width, height)}?img={random.randint(1, 70)}",
            f"https://avatars.dicebear.com/api/human/{random.randint(1, 1000)}.svg",
        ]
        return random.choice(avatar_services)
    
    # For general images, use multiple reliable services
    if keywords:
        # Clean and format keywords
        clean_keywords = re.sub(r'[^a-zA-Z0-9,\s]', '', keywords).strip()
        keyword_list = [k.strip() for k in clean_keywords.split(',') if k.strip()]
        if keyword_list:
            primary_keyword = keyword_list[0]
            # Use Lorem Picsum with seed for consistency
            seed = abs(hash(primary_keyword)) % 1000
            return f"https://picsum.photos/seed/{seed}/{width}/{height}"
    
    # Fallback options in order of reliability
    general_services = [
        f"https://picsum.photos/{width}/{height}",  # Lorem Picsum - most reliable
        f"https://placehold.co/{width}x{height}/png",  # Placehold.co
        f"https://via.placeholder.com/{width}x{height}/0066CC/FFFFFF?text=Image",  # Via Placeholder
    ]
    
    return random.choice(general_services)

# --- ENHANCED RULESET WITH RELIABLE IMAGES ---
MANDATORY_RULESET = (
    "**MANDATORY RULESET (You MUST follow these rules on ALL responses):**\n"
    "1.  **STRUCTURE & COMPLETENESS:** Every page MUST include a `<header>` with a `<nav>` bar, a logo (text or SVG), navigation links, a `<main>` tag with multiple diverse `<section>`s, and a detailed `<footer>`.\n"
    "2.  **VISIBILITY & CONTRAST (CRITICAL):** You MUST ensure high color contrast. If any element has a light background (e.g., `bg-white`, `bg-slate-100`), all text inside it MUST be a dark color (e.g., `text-gray-900`, `text-slate-800`). NEVER place light text on a light background.\n"
    "3.  **IMAGE RELIABILITY (CRITICAL):** All images MUST work. Use ONLY these reliable services:\n"
    "    - **For general/thematic images:** Use `https://picsum.photos/WIDTHxHEIGHT` or `https://picsum.photos/seed/SEED/WIDTHxHEIGHT` (where SEED is any number 1-1000).\n"
    "    - **For user avatars:** Use `https://i.pravatar.cc/SIZE?img=NUMBER` (where SIZE is pixels and NUMBER is 1-70).\n"
    "    - **For simple placeholders:** Use `https://placehold.co/WIDTHxHEIGHT/png`.\n"
    "    - **Examples:** `<img src=\"https://picsum.photos/800/600\" alt=\"Hero image\">`, `<img src=\"https://i.pravatar.cc/150?img=25\" alt=\"User avatar\">`\n"
    "4.  **IMAGE ATTRIBUTES:** Always include proper `alt` attributes and `loading=\"lazy\"` for performance.\n"
    "5.  **RESPONSIVENESS:** Use responsive image classes like `w-full h-auto object-cover`.\n"
)

# --- Supercharged System Prompts (Using the new, strong ruleset) ---
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

# --- Helper Functions (Enhanced with image processing) ---
def enhance_html_images(html_content: str) -> str:
    """
    Post-process HTML to ensure all images use reliable services
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for img in soup.find_all('img'):
        src = img.get('src', '')
        alt = img.get('alt', 'Image')
        
        # Skip if already using our recommended services
        if any(service in src for service in ['picsum.photos', 'i.pravatar.cc', 'placehold.co', 'via.placeholder.com']):
            continue
            
        # Extract dimensions if possible
        width = 800
        height = 600
        
        # Try to get dimensions from classes or style
        classes = img.get('class', [])
        if isinstance(classes, str):
            classes = classes.split()
            
        # Look for Tailwind width/height classes
        for cls in classes:
            if cls.startswith('w-') and cls[2:].isdigit():
                width = int(cls[2:]) * 4  # Rough conversion
            elif cls.startswith('h-') and cls[2:].isdigit():
                height = int(cls[2:]) * 4
                
        # Determine image type based on alt text or context
        if any(keyword in alt.lower() for keyword in ['avatar', 'profile', 'user', 'person']):
            new_src = get_reliable_image_url(min(width, height), min(width, height), "", "avatar")
        else:
            # Extract keywords from alt text
            keywords = re.sub(r'[^a-zA-Z0-9\s]', ' ', alt.lower()).strip()
            new_src = get_reliable_image_url(width, height, keywords, "general")
            
        img['src'] = new_src
        
        # Ensure proper attributes
        if not img.get('alt'):
            img['alt'] = 'Image'
        if not img.get('loading'):
            img['loading'] = 'lazy'
            
        # Add responsive classes if not present
        current_classes = img.get('class', [])
        if isinstance(current_classes, str):
            current_classes = current_classes.split()
        
        responsive_classes = ['w-full', 'h-auto', 'object-cover']
        for cls in responsive_classes:
            if cls not in current_classes:
                current_classes.append(cls)
                
        img['class'] = ' '.join(current_classes)
    
    return str(soup)

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
        # First enhance images
        enhanced_html = enhance_html_images(html_content)
        
        soup = BeautifulSoup(enhanced_html, 'html.parser')
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

# --- AI Core Functions ---
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
        if "gemini" in model_key:
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
    return "<h1>NeuroArti Pro Builder API is operational with Enhanced Image Support.</h1>"

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    if "gemini" in request.model:
        system_prompt = GEMINI_2_5_LITE_SUPERCHARGED_PROMPT
    elif request.model == "deepseek-r1":
        system_prompt = DEEPSEEK_SUPERCHARGED_PROMPT
    else:
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
    system_prompt = (
        "You are an expert web developer modifying an existing webpage. Your response MUST be the complete, updated HTML file.\n\n"
        f"{MANDATORY_RULESET}"
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
    system_prompt = (
        "You are a context-aware HTML modification tool. Modify the element after the `<!-- EDIT_TARGET -->` comment. "
        "Your response MUST be ONLY the modified HTML snippet.\n\n"
        f"{MANDATORY_RULESET}"
    )
    user_prompt = f"INSTRUCTION: '{request.prompt}'.\n\nCONTEXTUAL HTML TO MODIFY:\n{request.contextual_snippet}"
    modified_snippet_raw = generate_code(system_prompt, user_prompt, request.model)
    cleaned_snippet = clean_html_snippet(modified_snippet_raw)
    
    # Enhance images in the snippet
    if cleaned_snippet and '<' in cleaned_snippet:
        enhanced_snippet = enhance_html_images(cleaned_snippet)
        return {"snippet": enhanced_snippet}
    return {"snippet": request.contextual_snippet.replace('<!-- EDIT_TARGET -->', '')}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        # Note: The 'container_id' is now sent in the PatchRequest
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
            
        # Enhance images in the new snippet
        enhanced_snippet = enhance_html_images(request.new_parent_snippet)
        new_snippet_soup = BeautifulSoup(enhanced_snippet, 'html.parser')
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
        # We return the css/js so the frontend state remains consistent
        return {"html": body_html, "css": request.css, "js": request.js}
    except Exception as e:
        print(f"Patching error: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# --- New endpoint for testing image services ---
@app.get("/test-images")
async def test_images():
    """Test endpoint to verify image services are working"""
    test_images = {
        "lorem_picsum": "https://picsum.photos/300/200",
        "lorem_picsum_seeded": "https://picsum.photos/seed/123/300/200",
        "pravatar": "https://i.pravatar.cc/150?img=25",
        "placehold": "https://placehold.co/300x200/png",
        "via_placeholder": "https://via.placeholder.com/300x200/0066CC/FFFFFF?text=Test"
    }
    
    return {
        "message": "Image service test endpoints",
        "services": test_images,
        "html_test": f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; padding: 1rem;">
            {' '.join([f'<div><h3>{name}</h3><img src="{url}" alt="{name}" style="width: 100%; height: auto; border: 1px solid #ccc;"></div>' for name, url in test_images.items()])}
        </div>
        """,
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
