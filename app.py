import os
import uuid
import requests
import re
from typing import List
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

class UpdateRequest(BaseModel):
    html: str
    css: str
    js: str
    prompt: str
    model: str = "glm-4.5-air"
    container_id: str

# NEW MODEL for the improved editing endpoint
class EditElementRequest(BaseModel):
    html: str
    css: str
    js: str
    container_id: str
    selector: str # Direct selector for the element to be edited
    prompt: str
    model: str = "glm-4.5-air"


# --- Configuration ---
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

if not TOGETHER_API_KEY:
    raise ValueError("TOGETHER_API_KEY not found in environment variables.")
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

# --- Enhanced System Prompts ---
MANDATORY_RULESET_V2 = (
    "**MANDATORY RULESET (You MUST follow these rules on ALL responses):**\n"
    "1.  **Output Format:** Your response MUST be ONLY the raw HTML code. Do not include any explanations, comments, or markdown formatting like ```html. The response must start with `<!DOCTYPE html>`.\n"
    "2.  **Completeness:** The generated page MUST be a complete HTML document, including a `<header>`, a `<main>` with multiple diverse `<section>`s (e.g., hero, features, testimonials, CTA), and a detailed `<footer>`.\n"
    "3.  **Styling:** Use Tailwind CSS for ALL styling. You MUST include `<script src='https://cdn.tailwindcss.com'></script>` in the `<head>`. Do not use custom `<style>` blocks.\n"
    "4.  **Responsiveness:** Ensure the layout is fully responsive using Tailwind's prefixes (e.g., `md:`, `lg:`). It must look professional on both mobile and desktop screens. Include `<meta name='viewport' content='width=device-width, initial-scale=1.0'>`.\n"
    "5.  **Color & Contrast:** Use a professional, vibrant, and accessible color palette. AVOID bland, monochromatic grey schemes. Ensure high contrast between text and background colors for readability (e.g., dark text on light backgrounds).\n"
    "6.  **Content Richness:** Populate the page with rich, elaborate, and realistic placeholder content. Do not use generic 'Lorem Ipsum'. Create engaging copy and content that fits the user's prompt.\n"
    "7.  **Images:** Use high-quality placeholder images from services like Pexels or Unsplash. For example: `https://images.pexels.com/photos/3184418/pexels-photo-3184418.jpeg`. Every image MUST have a descriptive `alt` attribute.\n"
    "8.  **Interactivity:** Add subtle hover effects and transitions to all interactive elements like buttons and links (e.g., `hover:opacity-80 transition-all`)."
)

SYSTEM_PROMPT_BUILD = (
    "You are an elite UI/UX designer and frontend developer creating a webpage from scratch. "
    "Your task is to interpret the user's prompt and generate a single, complete, visually stunning HTML file.\n\n"
    f"{MANDATORY_RULESET_V2}"
)

SYSTEM_PROMPT_UPDATE = (
    "You are an expert web developer performing a major revision on an existing webpage. "
    "The user has provided their current code and a request for changes. Your task is to return the complete, updated HTML file incorporating their feedback.\n\n"
    f"{MANDATORY_RULESET_V2}"
)

# NEW, highly focused prompt for rewriting a single element.
SYSTEM_PROMPT_REWRITE_ELEMENT = (
    "You are an expert HTML element rewriter. Your task is to take an HTML element and a user's instruction, then return a new version of that exact element with the changes applied. "
    "**CRITICAL RULE: Your response MUST be ONLY the rewritten HTML element's code.** "
    "Do not provide explanations, markdown, or any surrounding text. "
    "If the input is a `<div>`, your output must start with `<div>`. If it's a `<p>`, your output must start with `<p>`."
)

# --- Image Engine & Helpers (Unchanged) ---
def get_hardcoded_fallback_images() -> List[str]:
    return [
        "https://images.pexels.com/photos/3184418/pexels-photo-3184418.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
        "https://images.pexels.com/photos/3183197/pexels-photo-3183197.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
        "https://images.pexels.com/photos/1181244/pexels-photo-1181244.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
        "https://images.pexels.com/photos/577585/pexels-photo-577585.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2",
    ]

def find_image_from_pexels(query: str) -> str:
    if not PEXELS_API_KEY or not query: return ""
    try:
        response = requests.get("https://api.pexels.com/v1/search", params={"query": query, "per_page": 5, "orientation": "landscape"}, headers={"Authorization": PEXELS_API_KEY}, timeout=7)
        if response.status_code == 200 and response.json().get('photos'):
            return random.choice(response.json()['photos'])['src']['large2x']
    except Exception as e:
        print(f"Pexels API error for query '{query}': {e}")
    return ""

def extract_image_context(img_tag: BeautifulSoup) -> str:
    alt_text = img_tag.get('alt', '').strip()
    if alt_text and len(alt_text) > 3: return alt_text
    parent = img_tag.find_parent()
    if parent:
        text_content = re.sub(r'\s+', ' ', parent.get_text(strip=True))
        if len(text_content) > 10: return ' '.join(text_content.split()[:5])
    return "modern technology abstract"

def fix_image_sources_smart(html_content: str) -> str:
    if not html_content: return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        for img in soup.find_all('img'):
            if img.get('src', '').startswith('http'): continue
            context_query = extract_image_context(img)
            image_url = find_image_from_pexels(context_query)
            img['src'] = image_url if image_url else random.choice(get_hardcoded_fallback_images())
            if not img.get('alt'): img['alt'] = context_query
            img['loading'] = 'lazy'
        return str(soup)
    except Exception as e:
        print(f"Error in fix_image_sources_smart: {e}")
        return html_content

def prefix_css_rules(css_content: str, container_id: str) -> str:
    if not container_id or not css_content: return css_content
    def prefixer(match):
        selectors = [f"#{container_id} {s.strip()}" for s in match.group(1).split(',')]
        return ", ".join(selectors) + match.group(2)
    css_content = re.sub(r'([^\r\n,{}]+(?:,[^\r\n,{}]+)*)(\s*{)', prefixer, css_content)
    css_content = re.sub(r'(@media[^{]*{\s*)(.*?)(\s*})', lambda m: m.group(1) + re.sub(r'([^\r\n,{}]+(?:,[^\r\n,{}]+)*)(\s*{)', prefixer, m.group(2)) + m.group(3), css_content, flags=re.DOTALL)
    return css_content

def clean_chatter_and_invalid_tags(soup):
    for tag in soup.find_all(['think', 'thought', 'explanation']):
        tag.decompose()

def isolate_html_document(raw_text: str) -> str:
    match = re.search(r'<!DOCTYPE html>.*</html>', raw_text, re.DOTALL | re.IGNORECASE)
    return match.group(0) if match else ""

def clean_html_snippet(text: str) -> str:
    soup = BeautifulSoup(f"<body>{text}</body>", 'html.parser')
    clean_chatter_and_invalid_tags(soup.body)
    return ''.join(str(c) for c in soup.body.contents)

def extract_assets(html_content: str, container_id: str) -> tuple:
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        prefixed_css = prefix_css_rules(css, container_id)
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string and not script.get('src'))
        body_tag = soup.find('body')
        if body_tag:
            for tag in body_tag.find_all(['style', 'script']):
                tag.decompose()
            clean_chatter_and_invalid_tags(body_tag)
            body_html = ''.join(str(c) for c in body_tag.contents)
        else:
            for tag in soup.find_all(['style', 'script', 'head', 'html', 'title', 'meta']):
                tag.decompose()
            body_html = str(soup)
        return body_html, prefixed_css, js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

def enhance_generated_html(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    if soup.head and not soup.find('meta', attrs={'name': 'viewport'}):
        soup.head.append(soup.new_tag('meta', attrs={'name': 'viewport', 'content': 'width=device-width, initial-scale=1.0'}))
    if soup.head and not soup.find('script', src='https://cdn.tailwindcss.com'):
        soup.head.append(soup.new_tag('script', src='https://cdn.tailwindcss.com'))
    return str(soup)

def generate_code(system_prompt: str, user_prompt: str, model_key: str):
    # ... (This function remains unchanged)
    try:
        if model_key == "gemini-2.5-flash-lite":
            if not GOOGLE_API_KEY: raise HTTPException(status_code=503, detail="Google API key not configured.")
            model = genai.GenerativeModel(model_key)
            full_prompt = f"{system_prompt}\n\nUSER PROMPT: {user_prompt}"
            safety_settings = {'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE', 'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'}
            response = model.generate_content(full_prompt, safety_settings=safety_settings)
            return response.text
        else:
            model_id = MODEL_MAPPING_TOGETHER.get(model_key)
            if not model_id: raise HTTPException(status_code=400, detail=f"Invalid model key for Together AI: {model_key}")
            response = together_client.chat.completions.create(model=model_id, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], temperature=0.2, max_tokens=8192)
            return response.choices[0].message.content or ""
    except Exception as e:
        print(f"Error calling AI model {model_key}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")


# --- FastAPI App ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- API Endpoints ---
@app.post("/build")
def create_build(request: BuildRequest):
    raw_code = generate_code(SYSTEM_PROMPT_BUILD, request.prompt, request.model)
    html_document = isolate_html_document(raw_code)
    if html_document:
        enhanced_html = enhance_generated_html(html_document)
        fixed_images_html = fix_image_sources_smart(enhanced_html)
        container_id = f"neuroarti-container-{uuid.uuid4().hex[:8]}"
        body_html, css, js = extract_assets(fixed_images_html, container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": container_id}
    raise HTTPException(status_code=500, detail="AI failed to generate a valid HTML document.")

@app.post("/update")
def update_build(request: UpdateRequest):
    full_html_for_ai = f"""<!DOCTYPE html><html><head><style>{request.css}</style></head><body><div id="{request.container_id}">{request.html}</div><script>{request.js}</script></html>"""
    user_prompt = f"USER REQUEST: '{request.prompt}'\n\nCURRENT WEBSITE CODE:\n{full_html_for_ai}"
    raw_code = generate_code(SYSTEM_PROMPT_UPDATE, user_prompt, request.model)
    html_document = isolate_html_document(raw_code)
    if html_document:
        enhanced_html = enhance_generated_html(html_document)
        fixed_images_html = fix_image_sources_smart(enhanced_html)
        body_html, css, js = extract_assets(fixed_images_html, request.container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": request.container_id}
    raise HTTPException(status_code=500, detail="AI failed to update the HTML document.")

# NEW /edit-element endpoint replacing the old logic
@app.post("/edit-element")
def edit_element(request: EditElementRequest):
    try:
        # 1. Reconstruct the full document for accurate selection
        full_html_doc = f'<html><head><style>{request.css}</style></head><body><div id="{request.container_id}">{request.html}</div><script>{request.js}</script></body></html>'
        soup = BeautifulSoup(full_html_doc, 'html.parser')

        # 2. Find the target element using its direct selector
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Target element with selector '{request.selector}' not found.")

        # 3. Ask the AI to rewrite just this element
        original_element_html = str(target_element)
        user_prompt = f"INSTRUCTION: '{request.prompt}'.\n\nCURRENT HTML ELEMENT:\n{original_element_html}"
        
        new_element_html_raw = generate_code(SYSTEM_PROMPT_REWRITE_ELEMENT, user_prompt, request.model)
        
        if not new_element_html_raw or not new_element_html_raw.strip().startswith('<'):
            raise HTTPException(status_code=500, detail="AI returned an invalid or empty response for the element edit.")

        # 4. Replace the old element with the new one
        new_element_soup = BeautifulSoup(new_element_html_raw, 'html.parser')
        
        # Make sure we get the actual element from the parsed response
        new_element = new_element_soup.find()
        if not new_element:
            raise HTTPException(status_code=500, detail="Could not parse the new element from AI response.")
            
        target_element.replace_with(new_element)
        
        # 5. Extract assets from the modified full document and return
        body_html, css, js = extract_assets(str(soup), request.container_id)

        return {"html": body_html, "css": css, "js": js, "container_id": request.container_id}

    except Exception as e:
        print(f"EDIT ELEMENT ERROR: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"An internal error occurred during element edit: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
