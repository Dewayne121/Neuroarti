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
API_KEY = os.environ.get("TOGETHER_API_KEY")
if not API_KEY:
    raise ValueError("API Key not found. Please set TOGETHER_API_KEY.")

client = OpenAI(api_key=API_KEY, base_url="https://api.together.xyz/v1")

MODEL_MAPPING = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-0528-tput" 
}

# --- Supercharged Prompts (Unchanged) ---
GLM_SUPERCHARGED_PROMPT = (
    "You are an elite AI web developer. Your task is to create a stunning, complete, and modern webpage based on a user's prompt. "
    "Your response MUST BE ONLY the full, valid HTML code. Do not include any explanations, markdown like ```html, or comments. Your response must start immediately with `<!DOCTYPE html>`."
    "\n\n**-- MANDATORY TECHNICAL SPECIFICATIONS --**"
    "\n1.  **Technology Stack:**"
    "\n    - Use HTML5 with Tailwind CSS loaded from the CDN: `<script src=\"https://cdn.tailwindcss.com\"></script>`."
    "\n    - All custom CSS must be placed within a single `<style>` tag in the `<head>`."
    "\n    - All JavaScript must be placed within a single `<script>` tag just before the closing `</body>` tag."
    "\n2.  **Structural Completeness & Depth:**"
    "\n    - Do not generate a simple, short page. Create a comprehensive, multi-section webpage that feels like a real, finished product."
    "\n    - Your generated page MUST include these sections: Navigation Bar, a prominent Hero Section, a Features or Services section, a Testimonials or About Us section, a Call-to-Action (CTA) section, and a detailed Footer."
    "\n3.  **Mandatory Elements:**"
    "\n    - **Logo:** The navigation bar MUST contain a logo. This can be a well-styled text logo (e.g., `<div class='font-bold text-2xl'>Paws & Tails</div>`) or an SVG icon. Be creative."
    "\n    - **Footer:** The footer MUST be comprehensive, containing links, social media icons (use Font Awesome if needed), and a copyright notice (e.g., `© 2024 YourCompanyName. All rights reserved.`)."
    "\n4.  **Content & Imagery:**"
    "\n    - Generate rich, relevant, and plausible placeholder content (text, headlines, etc.)."
    "\n    - Use high-quality, professional placeholder images from `https://images.unsplash.com/`. Use specific, descriptive photo URLs to match the theme (e.g., for a pet store, use a real Unsplash URL of a dog or cat)."
    "\n5.  **Design, UX, and Responsiveness:**"
    "\n    - The design must be modern, clean, and visually appealing with a consistent color scheme and ample whitespace."
    "\n    - Add subtle hover effects and transitions on buttons and links to make the page feel interactive."
    "\n    - The layout MUST be fully responsive and look excellent on all screen sizes. Use Tailwind's responsive prefixes (`sm:`, `md:`, `lg:`) extensively."
    "\n6.  **Code Quality:**"
    "\n    - Produce clean, well-formatted, and semantic HTML5 (use `<header>`, `<main>`, `<section>`, `<footer>`, `<nav>`, etc.)."
)

DEEPSEEK_SUPERCHARGED_PROMPT = (
    "You are a top-tier frontend architect AI. Your sole function is to write production-ready, single-file HTML documents based on a user request. "
    "Your output must be ONLY the raw HTML code. No preamble, no markdown, no explanation. Your entire response begins with `<!DOCTYPE html>`."
    "\n\n**-- TECHNICAL DIRECTIVES --**"
    "\n1.  **Core Stack:** HTML, Tailwind CSS (via CDN: `<script src=\"https://cdn.tailwindcss.com\"></script>`). Place all CSS in a `<style>` block in the `<head>`. Place all JS in a `<script>` block before `</body>`."
    "\n2.  **Architectural Blueprint:** The generated document must be a complete, multi-section landing page, not a simple component. You are required to construct the following semantic structure:"
    "\n    - `<header>` containing a `<nav>` element. This nav MUST feature a logo (text-based, inline SVG, or an icon) and navigation links."
    "\n    - `<main>` containing multiple `<section>` tags for different content blocks (e.g., hero, features, about, testimonials, CTA)."
    "\n    - `<footer>` which must be detailed. It should include navigation links, social media icons (Font Awesome recommended), and a copyright statement."
    "\n3.  **Component-Level Detail:**"
    "\n    - Generate high-fidelity components. For a 'features' section, don't just list items; create cards with icons, headings, and descriptive text."
    "\n    - For a 'hero' section, use a high-impact background image (from `https://images.unsplash.com/`) with a strong headline and a primary call-to-action button."
    "\n4.  **Responsive Grid & Flexbox:**"
    "\n    - Implement a mobile-first responsive strategy using Tailwind's variants (`sm:`, `md:`, `lg:`, `xl:`) as a primary requirement."
    "\n    - The layout must reflow elegantly from a single column on mobile to multi-column layouts on larger screens."
    "\n5.  **Micro-interactions & UX:**"
    "\n    - All interactive elements (buttons, links, cards) must have hover states (`hover:bg-blue-600`, `hover:scale-105`, etc.) and smooth transitions (`transition-all duration-300`)."
    "\n6.  **Code Standards:**"
    "\n    - Write clean, indented, and readable HTML. Adhere strictly to semantic HTML5 standards."
    "\n    - Ensure accessibility basics: `alt` attributes for all `<img>` tags, `aria-label` for icon buttons, etc."
)

# --- Helper Functions (Unchanged) ---
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
def generate_code(system_prompt: str, user_prompt: str, model_id: str):
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1, max_tokens=8192,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App (Unchanged) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root(): return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    if request.model == "deepseek-r1":
        system_prompt = DEEPSEEK_SUPERCHARGED_PROMPT
        print("Using Supercharged Prompt for DeepSeek R1.")
    else: 
        system_prompt = GLM_SUPERCHARGED_PROMPT
        print("Using Supercharged Prompt for GLM-4.5-Air.")

    raw_code = generate_code(system_prompt, request.prompt, model_id)
    html_document = isolate_html_document(raw_code)
    
    if html_document:
        container_id = f"neuroarti-container-{uuid.uuid4().hex[:8]}"
        body_html, css, js = extract_assets(html_document, container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": container_id}
    
    raise HTTPException(status_code=500, detail="AI failed to generate a valid HTML document.")


@app.post("/update")
async def update_build(request: UpdateRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING.get("glm-4.5-air"))
    
    # KEY CHANGE: Enhance the update prompt
    system_prompt = (
        "You are an expert web developer tasked with modifying an existing webpage. "
        "You will receive the complete HTML, CSS, and JS of the current page, along with a user's request for a high-level change. "
        "Intelligently modify the provided code to fulfill the request. Preserve the overall structure, design system, and existing classes as much as possible. "
        "**CRITICAL:** Ensure the updated code remains fully responsive. Use Tailwind CSS's responsive utility variants (`sm:`, `md:`, etc.) as needed to maintain a mobile-first design. "
        "Your response MUST be the complete, updated HTML file, starting with <!DOCTYPE html> and including the modified <style> and <script> tags. "
        "No explanations, no markdown. RESPOND WITH ONLY THE FULL HTML CODE."
    )

    full_html_for_ai = f"""<!DOCTYPE html>
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
</body>
<script>{request.js}</script>
</html>"""

    user_prompt = f"USER REQUEST: '{request.prompt}'\n\nCURRENT WEBSITE CODE:\n{full_html_for_ai}"

    raw_code = generate_code(system_prompt, user_prompt, model_id)
    html_document = isolate_html_document(raw_code)

    if html_document:
        body_html, css, js = extract_assets(html_document, request.container_id)
        return {"html": body_html, "css": css, "js": js, "container_id": request.container_id}

    raise HTTPException(status_code=500, detail="AI failed to update the HTML document.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # KEY CHANGE: Enhance the edit-snippet prompt
    system_prompt = (
        "You are a context-aware HTML modification tool. You will receive an HTML snippet containing a `<!-- EDIT_TARGET -->` comment. "
        "Your task is to modify the single HTML element immediately following this comment based on the user's instruction. "
        "You MUST preserve the surrounding parent and sibling elements. Adhere to the existing Tailwind CSS classes and design patterns. "
        "**IMPORTANT:** Ensure your changes are responsive and do not break the layout on mobile devices. Use responsive prefixes like `sm:` and `md:` if you add new layout-related classes. "
        "Your response MUST be ONLY the modified, larger HTML snippet, with the `<!-- EDIT_TARG"
    )
    user_prompt = f"INSTRUCTION: '{request.prompt}'.\n\nCONTEXTUAL HTML TO MODIFY:\n{request.contextual_snippet}"
    modified_snippet_raw = generate_code(system_prompt, user_prompt, model_id)
    cleaned_snippet = clean_html_snippet(modified_snippet_raw)
    
    if cleaned_snippet and '<' in cleaned_snippet:
        return {"snippet": cleaned_snippet}
    
    return {"snippet": request.contextual_snippet.replace('<!-- EDIT_TARGET -->', '')}

# Unchanged /patch-html endpoint...
@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f'<body><div id="{request.container_id}">{request.html}</div></body>'
        soup = BeautifulSoup(full_html_doc, 'html.parser')

        parent_element = soup.select_one(request.parent_selector)
        if not parent_element:
            if request.parent_selector == f"body > #{request.container_id}":
                 # This means the user is editing a top-level element, and its parent is the container itself.
                 parent_element = soup.select_one(f"#{request.container_id}")
            if not parent_element:
                 raise HTTPException(status_code=404, detail=f"Parent selector '{request.parent_selector}' not found.")
        
        if not request.new_parent_snippet or not request.new_parent_snippet.strip():
            raise HTTPException(status_code=400, detail="New parent snippet is empty.")

        new_snippet_soup = BeautifulSoup(request.new_parent_snippet, 'html.parser')
        
        new_contents = new_snippet_soup.body.contents if new_snippet_soup.body else new_snippet_soup.contents
        if not new_contents:
            raise HTTPException(status_code=500, detail="Failed to parse new parent snippet from AI response.")
        
        # This handles both cases: replacing a child within a parent, or replacing the entire content of the container
        if request.parent_selector == f"body > #{request.container_id}":
             parent_element.clear()
             for content in new_contents:
                 parent_element.append(content)
        else:
             parent_element.replace_with(*new_contents)

        container_div = soup.select_one(f'#{request.container_id}')
        if not container_div:
            raise HTTPException(status_code=500, detail="Container element was lost after patching HTML.")

        body_html = ''.join(str(c) for c in container_div.contents)
        
        return {"html": body_html, "css": request.css, "js": request.js}
    except Exception as e:
        print(f"Patching error: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# --- Uvicorn runner (Unchanged) ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
