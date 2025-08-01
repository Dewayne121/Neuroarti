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

# --- Image Engine (Fast & Reliable - Unchanged) ---
def get_guaranteed_fallback_images() -> List[str]:
    return [
        "https://images.unsplash.com/photo-1557683316-973673baf926?w=1260&q=80",
        "https://images.unsplash.com/photo-1519681393784-d120267933ba?w=1260&q=80",
        "https://images.unsplash.com/photo-1488998427799-e3362cec87c3?w=1260&q=80",
    ]
def extract_image_context(img_tag: BeautifulSoup) -> str:
    return img_tag.get('alt', '').strip() if len(img_tag.get('alt', '')) > 5 else ""
def fix_image_sources_fast(html_content: str) -> str:
    if not html_content: return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        images = soup.find_all('img')
        for img in images:
            context_query = extract_image_context(img)
            image_url = ""
            if context_query:
                keywords = re.sub(r'[^a-zA-Z0-9\s,]', '', context_query).replace(' ', ',')
                image_url = f"https://source.unsplash.com/random/1200x800/?{keywords}"
            else:
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

# --- THE NEW AESTHETIC SUPER-PROMPT ---
SUPERCHARGED_DESIGN_BRIEF = (
    "You are 'Aether,' an award-winning digital artist and frontend developer. Your mission is to create a single, standalone HTML file that is not just a webpage, but a piece of art. It must be aesthetically breathtaking, functional, and perfectly tailored to the user's prompt.\n\n"
    "**AETHER'S DESIGN MANIFESTO (MANDATORY):**\n\n"
    "1.  **THE ART OF CSS:** You are a CSS master. You will write rich, detailed custom CSS inside the `<style>` tag. You are NOT limited to utility classes.\n"
    "    - **Color Palette:** You MUST define a sophisticated color palette using CSS variables (`:root { --primary: #...; --dark: #...; }`) and use these variables throughout the CSS.\n"
    "    - **Typography:** You MUST import two complementary fonts from Google Fonts (e.g., a serif for headings, a sans-serif for body text) and define a clear typographic hierarchy.\n\n"
    "2.  **LAYOUT & COMPOSITION:**\n"
    "    - **No Boring Stacks:** Every section must have a unique, interesting layout. Use CSS Grid and Flexbox to create asymmetrical designs, overlapping elements, and a dynamic visual flow.\n"
    "    - **Breathe with Whitespace:** Use generous padding and margins to create a clean, high-end feel. Avoid clutter at all costs.\n\n"
    "3.  **INTERACTIVE ELEGANCE:** The page must feel alive.\n"
    "    - **JavaScript Animations:** You MUST include JavaScript in the `<script>` tag to create 'animate on scroll' effects, using the `IntersectionObserver` API to fade-in or slide-in elements as they enter the viewport.\n"
    "    - **Subtle Polish:** All interactive elements (links, buttons, cards) MUST have smooth `transition` effects and engaging `hover` states (e.g., transform, box-shadow).\n\n"
    "4.  **COMPONENT MASTERY:** The page must be feature-rich.\n"
    "    - **Hero Section:** Create a stunning, full-height hero section with a compelling headline and a background image with a gradient overlay.\n"
    "    - **Feature/Product Grids:** Design beautiful cards with images, text, and hover effects.\n"
    "    - **Testimonials & Footers:** Include styled testimonial sections (blockquotes) and a detailed, multi-column footer.\n\n"
    "5.  **IMAGE INTEGRATION:**\n"
    "    - **Descriptive `alt` Tags are CRITICAL:** Your only job for images is to write a highly descriptive `alt` attribute. The system will handle finding the image. Example: `<img alt='A sleek, modern desk with a laptop displaying code and a steaming cup of coffee'>`.\n\n"
    "**TECHNICAL DIRECTIVES:**\n"
    "- Your response is ONE single HTML file.\n"
    "- Start immediately with `<!DOCTYPE html>`. No explanations, no markdown.\n"
    "- All CSS goes in `<style>`. All JS goes in `<script>`. No external files."
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

# --- API Endpoints (Using the new Aesthetic Super-Prompt) ---
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
