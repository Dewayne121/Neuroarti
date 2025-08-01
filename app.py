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

# --- Configuration (Simplified: No Pexels Key Needed) ---
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

# --- The NEW Lightning-Fast Image Engine ---

def get_guaranteed_fallback_images() -> List[str]:
    """A list of high-quality, proven image URLs to use as a fallback."""
    return [
        "https://images.unsplash.com/photo-1557683316-973673baf926?w=1260&q=80",
        "https://images.unsplash.com/photo-1519681393784-d120267933ba?w=1260&q=80",
        "https://images.unsplash.com/photo-1488998427799-e3362cec87c3?w=1260&q=80",
        "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=1260&q=80",
        "https://images.unsplash.com/photo-1501630834273-4b5604d2ee31?w=1260&q=80"
    ]

def extract_image_context(img_tag: BeautifulSoup) -> str:
    """Extracts a search query from the alt text."""
    alt_text = img_tag.get('alt', '').strip()
    return alt_text if len(alt_text) > 5 else ""

def fix_image_sources_fast(html_content: str) -> str:
    """Instantly replaces image placeholders with dynamic Unsplash URLs or high-quality fallbacks."""
    if not html_content: return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        images = soup.find_all('img')
        
        for img in images:
            context_query = extract_image_context(img)
            image_url = ""
            
            if context_query:
                # Instantly create a dynamic URL. No network call needed on the server.
                keywords = re.sub(r'[^a-zA-Z0-9\s,]', '', context_query).replace(' ', ',')
                image_url = f"https://source.unsplash.com/random/1200x800/?{keywords}"
            else:
                # If no context, use one of the guaranteed beautiful images.
                image_url = random.choice(get_guaranteed_fallback_images())
            
            img['src'] = image_url
            if not img.get('alt'): img['alt'] = "High-quality decorative image"
            img['loading'] = 'lazy'
            
            img_classes = img.get('class', [])
            if 'object-cover' not in img_classes: img_classes.append('object-cover')
            if 'w-full' not in img_classes: img_classes.append('w-full')
            if 'h-full' not in img_classes: img_classes.append('h-full')
            img['class'] = img_classes

        return str(soup)
    except Exception as e:
        print(f"Error in fix_image_sources_fast: {e}")
        return html_content

# --- High-Quality Creative Brief (Unchanged) ---
SUPERCHARGED_DESIGN_BRIEF = (
    "You are 'Vortex,' an elite AI frontend architect renowned for creating visually stunning, modern, and award-winning websites. You will generate a single, complete HTML file using Tailwind CSS via a CDN link.\n\n"
    "**VORTEX'S CORE DESIGN PHILOSOPHY (You MUST adhere to this):**\n\n"
    "1.  **Layout & Spacing:**\n"
    "    - **Embrace Whitespace:** Use generous padding (`p-8`, `py-16`, `px-12`) to let content breathe. Avoid cramped layouts.\n"
    "    - **Modern Grid & Flexbox:** Use CSS Grid (`grid`, `grid-cols-2`, `lg:grid-cols-3`) for feature sections and Flexbox (`flex`, `justify-between`, `items-center`) for headers, footers, and component alignment.\n"
    "    - **Varied Layouts:** Each `<section>` must have a different and interesting layout. Use alternating image-and-text sections, centered content, and multi-column grids.\n\n"
    "2.  **Color & Typography:**\n"
    "    - **Sophisticated Palette:** Use a harmonious color scheme. Typically a dark background (e.g., `bg-slate-900` or `bg-gray-950`), a lighter content background (e.g., `bg-slate-800`), a strong primary/accent color (e.g., `blue-500`, `indigo-600`), and light text (`text-slate-200`, `text-gray-400`).\n"
    "    - **Typographic Hierarchy:** Use a clear hierarchy. Large, bold headings (`text-4xl`, `font-bold`), smaller subheadings, and legible body text (`text-lg`, `text-slate-300`).\n"
    "    - **High Contrast is NON-NEGOTIABLE:** All text must be easily readable against its background.\n\n"
    "3.  **Components & Interactivity:**\n"
    "    - **Rich Component Library:** Your page MUST include several of these: a compelling hero section with a clear call-to-action button, a multi-item feature grid with inline SVG icons, a customer testimonial section, a pricing table, and a contact form.\n"
    "    - **Subtle Polish:** Use smooth transitions on interactive elements (`transition-all`, `duration-300`) and subtle hover effects (`hover:-translate-y-1`, `hover:scale-105`, `hover:shadow-lg`).\n\n"
    "4.  **Content & Images:**\n"
    "    - **Image Integration:** Use `<img>` tags liberally. **Your only task is to write a highly descriptive `alt` attribute.** For example: `<img alt=\"A minimalist workspace with a laptop and a cup of coffee\">`. The system will handle finding the perfect image. The quality of your `alt` text is critical for a good result.\n\n"
    "**TECHNICAL DIRECTIVES:**\n"
    "- Your entire response is ONLY the raw HTML code. Start immediately with `<!DOCTYPE html>`."
)

# --- AI Core Functions (Unchanged) ---
def generate_with_together(system_prompt: str, user_prompt: str, model_key: str):
    model_id = MODEL_MAPPING_TOGETHER.get(model_key)
    if not model_id: raise HTTPException(status_code=400, detail=f"Invalid model key: {model_key}")
    response = together_client.chat.completions.create(model=model_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.3, max_tokens=8192)
    return response.choices[0].message.content or ""
def generate_with_google(system_prompt: str, user_prompt: str, model_id_str: str):
    if not GOOGLE_API_KEY: raise HTTPException(status_code=503, detail="Google API key not configured.")
    model = genai.GenerativeModel(model_id_str)
    full_prompt = f"{system_prompt}\n\nUSER PROMPT: {user_prompt}"
    generation_config = genai.types.GenerationConfig(temperature=0.3)
    safety_settings = {'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE', 'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'}
    response = model.generate_content(full_prompt, generation_config=generation_config, safety_settings=safety_settings)
    return response.text
def generate_code(system_prompt: str, user_prompt: str, model_key: str):
    try:
        if model_key == "gemini-2.5-flash-lite": return generate_with_google(system_prompt, user_prompt, model_key)
        else: return generate_with_together(system_prompt, user_prompt, model_key)
    except Exception as e:
        print(f"Error calling AI model {model_key}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

# --- FastAPI App & Helper Functions (Unchanged) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
def prefix_css_rules(css_content: str, container_id: str) -> str:
    if not container_id: return css_content
    def prefixer(match):
        selectors = [f"#{container_id} {s.strip()}" for s in match.group(1).split(',')]
        return ", ".join(selectors) + match.group(2)
    css_content = re.sub(r'([^\r\n,{}]+(?:,[^\r\n,{}]+)*)(\s*{)', prefixer, css_content)
    css_content = re.sub(r'(@media[^{]*{\s*)(.*?)(\s*})', lambda m: m.group(1) + re.sub(r'([^\r\n,{}]+(?:,[^\r\n,{}]+)*)(\s*{)', prefixer, m.group(2)) + m.group(3), css_content, flags=re.DOTALL)
    return css_content
def clean_chatter_and_invalid_tags(soup_or_tag):
    if not hasattr(soup_or_tag, 'children'): return
    nodes_to_remove = [child for child in list(soup_or_tag.children) if (isinstance(child, NavigableString) and child.string.strip() and soup_or_tag.name in ['body', 'div', 'section', 'header', 'footer', 'main']) or (hasattr(child, 'name') and child.name in ['think', 'thought', 'explanation'])]
    for node in nodes_to_remove: node.decompose()
    for child in soup_or_tag.children:
        if hasattr(child, 'name'): clean_chatter_and_invalid_tags(child)
def isolate_html_document(raw_text: str) -> str:
    doctype_start = raw_text.lower().find('<!doctype html')
    return raw_text[doctype_start:] if doctype_start != -1 else ""
def clean_html_snippet(text: str) -> str:
    soup = BeautifulSoup(text, 'html.parser')
    clean_chatter_and_invalid_tags(soup)
    if soup.body: return ''.join(str(c) for c in soup.body.contents)
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
            else: body_content = ''.join(str(c) for c in body_tag.contents)
        else: body_content = ''
        return body_content, prefixed_css, js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

@app.get("/", response_class=HTMLResponse)
async def root(): return "<h1>NeuroArti Pro Builder API is operational with High-Quality Design Engine.</h1>"

# --- API Endpoints (Now using the fast image fixer) ---
@app.post("/build")
def create_build(request: BuildRequest):
    raw_code = generate_code(SUPERCHARGED_DESIGN_BRIEF, request.prompt, request.model)
    html_document = isolate_html_document(raw_code)
    if html_document:
        fixed_html_document = fix_image_sources_fast(html_document)
        container_id = f"neuroarti-container-{uuid.uuid4().hex[:8]}"
        body_html, css, js = extract_assets(fixed_html_document, container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": container_id}
    raise HTTPException(status_code=500, detail="AI failed to generate a valid HTML document.")

@app.post("/update")
def update_build(request: UpdateRequest):
    full_html_for_ai = f"""<!DOCTYPE html><html><head><style>{request.css}</style></head><body><div id="{request.container_id}">{request.html}</div></body><script>{request.js}</script></html>"""
    user_prompt = f"USER REQUEST: '{request.prompt}'\n\nCURRENT WEBSITE CODE:\n{full_html_for_ai}"
    raw_code = generate_code(SUPERCHARGED_DESIGN_BRIEF, user_prompt, request.model)
    html_document = isolate_html_document(raw_code)
    if html_document:
        fixed_html_document = fix_image_sources_fast(html_document)
        body_html, css, js = extract_assets(fixed_html_document, request.container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": request.container_id}
    raise HTTPException(status_code=500, detail="AI failed to update the HTML document.")

@app.post("/edit-snippet")
def create_edit_snippet(request: EditSnippetRequest):
    user_prompt = f"INSTRUCTION: '{request.prompt}'.\n\nCONTEXTUAL HTML TO MODIFY:\n{request.contextual_snippet}"
    modified_snippet_raw = generate_code(SUPERCHARGED_DESIGN_BRIEF, user_prompt, request.model)
    fixed_snippet = fix_image_sources_fast(modified_snippet_raw)
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
        fixed_snippet = fix_image_sources_fast(request.new_parent_snippet)
        new_snippet_soup = BeautifulSoup(fixed_snippet, 'html.parser')
        new_contents = new_snippet_soup.body.contents if new_snippet_soup.body else new_snippet_soup.contents
        if not new_contents:
            raise HTTPException(status_code=500, detail="Failed to parse new parent snippet.")
        
        element_to_modify.replace_with(*new_contents)
            
        final_container_div = soup.select_one(f'#{request.container_id}')
        body_html = ''.join(str(c) for c in (final_container_div.contents if final_container_div else soup.body.contents))
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
