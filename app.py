import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import re
import json
from typing import Optional, Dict, Any

# --- Pydantic Models for API Request Bodies ---
class BuildRequest(BaseModel):
    prompt: str
    model: str = "glm-4.5-air"
    projectType: str = "single"
    includeSeo: bool = True
    makeResponsive: bool = True
    isPreview: bool = False

class EditRequest(BaseModel): # Kept for potential future use, but diff-patch is the primary edit endpoint
    html: str
    selector: str
    prompt: str
    model: str = "glm-4.5-air"

class DiffPatchRequest(BaseModel):
    html: str
    selector: str
    prompt: str
    model: str = "glm-4.5-air"

class InteractiveRequest(BaseModel):
    html: str
    type: str
    config: Dict[str, Any]
    model: str = "glm-4.5-air"

class SeoRequest(BaseModel):
    html: str
    seo: Dict[str, str]
    model: str = "glm-4.5-air"

# --- Configuration ---
# IMPORTANT: Make sure GLM_API_KEY is set in your Railway environment variables.
API_KEY = os.environ.get("GLM_API_KEY")
if not API_KEY:
    raise ValueError("API Key not found. Please set the GLM_API_KEY environment variable.")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1",
)

# --- Model Mapping ---
# Updated with valid and powerful models from Together.ai
MODEL_MAPPING = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct" 
}

# --- AI Response Sanitization Function ---
def clean_html_response(raw_response: str) -> str:
    """
    Cleans the AI's raw output to ensure it's valid HTML.
    - Strips leading/trailing whitespace.
    - Removes markdown code fences (```html ... ```).
    - Extracts content starting from <!DOCTYPE html>.
    """
    cleaned_response = re.sub(r'```html\n?', '', raw_response, flags=re.IGNORECASE)
    cleaned_response = re.sub(r'```', '', cleaned_response)
    
    doctype_match = re.search(r'<!DOCTYPE html.*?>', cleaned_response, re.IGNORECASE | re.DOTALL)
    
    if doctype_match:
        return cleaned_response[doctype_match.start():].strip()
    else:
        # If no doctype, it might be a partial snippet, which is invalid for a full page.
        # However, for robustness, we'll return the cleaned text and let the frontend handle it.
        return cleaned_response.strip()

# --- Extract CSS and JavaScript from HTML ---
def extract_assets(html_content: str) -> tuple:
    """
    Extracts CSS from <style> tags and JS from <script> tags within the HTML content.
    It returns the HTML with the tags removed, and the separated CSS and JS content.
    """
    # Use a proper HTML parser to avoid regex issues with complex HTML
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    css_content = []
    js_content = []

    # Extract and remove style tags
    for s in soup.find_all('style'):
        css_content.append(s.string or '')
        s.decompose()

    # Extract and remove script tags (with content, not src)
    for s in soup.find_all('script'):
        if s.string: # Only extract inline scripts
            js_content.append(s.string)
            s.decompose()
    
    # Return the modified HTML (as a string) and the joined assets
    return str(soup), "\n".join(css_content).strip(), "\n".join(js_content).strip()

# --- AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str):
    """Generic function to call the AI and get a cleaned response."""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4096,
        )
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html)
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

def generate_website_code_sync(prompt: str, model: str, project_type: str, include_seo: bool, make_responsive: bool, is_preview: bool):
    model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
    
    system_prompt = (
        "You are an expert frontend developer. Your task is to generate a complete, single HTML file based on the user's description. "
        "The HTML file must use Tailwind CSS for styling, included via a CDN script tag in the `<head>`. "
        "All CSS must be within a single `<style>` tag in the `<head>`, and all JavaScript must be in a single `<script>` tag at the end of the `<body>`. "
        "Your output MUST be only the raw HTML code, starting with `<!DOCTYPE html>`. Do not include any explanations or markdown."
    )
    if include_seo:
        system_prompt += " Include relevant SEO meta tags (title, description, keywords) and use semantic HTML (header, main, section, footer, etc.)."
    if make_responsive:
        system_prompt += " Ensure the layout is fully responsive using Tailwind's mobile-first utility classes."
    
    return generate_code(system_prompt, prompt, model_id)

def edit_element_sync(html: str, selector: str, prompt: str, model: str):
    """
    This is the new, more robust implementation for element editing.
    It asks the AI to return the full, modified document.
    """
    model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
    
    system_prompt = (
        "You are a precise HTML code editor. Your task is to modify a specific part of the given HTML document based on a user's instruction. "
        f"The user wants to change the element identified by the CSS selector: `{selector}`. "
        "Apply the requested change and return the ENTIRE, fully modified HTML document. "
        "Preserve the original structure, styles, and scripts as much as possible, only changing what is necessary. "
        "Your output MUST be only the raw, updated HTML code, starting with `<!DOCTYPE html>`. Do not add any commentary."
    )
    
    user_prompt = f"User's instruction for the change: '{prompt}'.\n\nHere is the full HTML to modify:\n\n{html}"
    
    return generate_code(system_prompt, user_prompt, model_id)

def add_interactive_element_sync(html: str, element_type: str, config: Dict[str, Any], model: str):
    model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
    
    system_prompt = (
        "You are an expert web developer specializing in interactive elements. Your task is to intelligently add a new feature to the provided HTML document. "
        f"The user wants to add a '{element_type}' component. "
        "Find a logical location within the `<body>` of the document to insert this new component. "
        "Ensure the new element is styled with Tailwind CSS to match the existing design. "
        "If the component requires JavaScript for functionality, add it to the `<script>` tag at the end of the body. "
        "Return the ENTIRE, fully modified HTML document. Your output must be ONLY the raw HTML code."
    )
    
    config_str = json.dumps(config, indent=2)
    user_prompt = f"Add a '{element_type}' with the following configuration:\n{config_str}\n\nHere is the HTML document to modify:\n\n{html}"
    
    return generate_code(system_prompt, user_prompt, model_id)

def apply_seo_changes_sync(html: str, seo_data: Dict[str, str], model: str):
    model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
    
    system_prompt = (
        "You are an SEO expert. Your task is to update the `<head>` section of the given HTML document with the provided metadata. "
        "You must also review the `<body>` for SEO best practices, such as ensuring `<img>` tags have `alt` attributes and the heading structure (h1, h2, etc.) is logical. "
        "Update the title, meta description, and meta keywords based on the user's input. "
        "Return the ENTIRE, fully optimized HTML document. Your output must be ONLY the raw HTML code."
    )
    
    seo_str = json.dumps(seo_data, indent=2)
    user_prompt = f"Apply the following SEO data:\n{seo_str}\n\nHere is the HTML document to optimize:\n\n{html}"
    
    return generate_code(system_prompt, user_prompt, model_id)

# --- FastAPI App Setup ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Root endpoint ---
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>NeuroArti Pro Builder API</title></head>
    <body style="font-family: sans-serif; background-color: #0d1117; color: #c9d1d9; text-align: center; padding-top: 5rem;">
        <h1>NeuroArti Pro Builder API</h1>
        <p>This backend is operational. Connect from the frontend application to use the service.</p>
    </body>
    </html>
    """

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    html_code = generate_website_code_sync(
        request.prompt, request.model, request.projectType, 
        request.includeSeo, request.makeResponsive, request.isPreview
    )
    if html_code:
        clean_html, css, js = extract_assets(html_code)
        return {"html": clean_html, "css": css, "js": js}
    raise HTTPException(status_code=500, detail="Failed to generate website code.")

@app.post("/diff-patch")
async def create_diff_patch(request: DiffPatchRequest):
    html_code = edit_element_sync(request.html, request.selector, request.prompt, request.model)
    if html_code:
        clean_html, css, js = extract_assets(html_code)
        return {"html": clean_html, "css": css, "js": js}
    raise HTTPException(status_code=500, detail="Failed to patch website code.")

@app.post("/add-interactive")
async def add_interactive_element(request: InteractiveRequest):
    html_code = add_interactive_element_sync(request.html, request.type, request.config, request.model)
    if html_code:
        clean_html, css, js = extract_assets(html_code)
        return {"html": clean_html, "css": css, "js": js}
    raise HTTPException(status_code=500, detail="Failed to add interactive element.")

@app.post("/apply-seo")
async def apply_seo_changes(request: SeoRequest):
    html_code = apply_seo_changes_sync(request.html, request.seo, request.model)
    if html_code:
        clean_html, css, js = extract_assets(html_code)
        return {"html": clean_html, "css": css, "js": js}
    raise HTTPException(status_code=500, detail="Failed to apply SEO changes.")

# --- Gradio and Uvicorn runner ---
# The Gradio interface is commented out as it's not the primary way to interact with the app.
# def gradio_interface(): ...

if __name__ == "__main__":
    import uvicorn
    # Use the PORT environment variable provided by Railway, default to 8000 for local dev.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
