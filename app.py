import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re
import json
from typing import Optional, List, Dict, Any

# --- Pydantic Models for API Request Bodies ---
class BuildRequest(BaseModel):
    prompt: str
    model: str = "glm-4.5-air"  # Default to GLM 4.5 Air
    projectType: str = "single"
    includeSeo: bool = True
    makeResponsive: bool = True
    isPreview: bool = False

class EditRequest(BaseModel):
    html: str
    selector: str
    prompt: str
    model: str = "glm-4.5-air"  # Default to GLM 4.5 Air

class DiffPatchRequest(BaseModel):
    html: str
    selector: str
    prompt: str
    model: str = "glm-4.5-air"  # Default to GLM 4.5 Air

class InteractiveRequest(BaseModel):
    html: str
    type: str
    config: Dict[str, Any]
    model: str = "glm-4.5-air"  # Default to GLM 4.5 Air

class SeoRequest(BaseModel):
    html: str
    seo: Dict[str, str]
    model: str = "glm-4.5-air"  # Default to GLM 4.5 Air

# --- Configuration ---
API_KEY = os.environ.get("GLM_API_KEY") 
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1", 
)

# --- Model Mapping ---
MODEL_MAPPING = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/deepseek-r1"  # Assuming this is the model ID for DeepSeek R1
}

# --- AI Response Sanitization Function ---
def clean_html_response(raw_response: str) -> str:
    """
    Cleans the AI's raw output to ensure it's valid HTML.
    - Strips leading/trailing whitespace.
    - Removes markdown code fences (```html ... ```).
    - Extracts content starting from <!DOCTYPE html>.
    """
    # Remove markdown fences
    cleaned_response = re.sub(r'```html\n?', '', raw_response)
    cleaned_response = re.sub(r'```', '', cleaned_response)
    
    # Find the start of the actual HTML document
    doctype_match = re.search(r'<!DOCTYPE html.*?>', cleaned_response, re.IGNORECASE | re.DOTALL)
    
    if doctype_match:
        # Return everything from the doctype declaration onwards
        return cleaned_response[doctype_match.start():].strip()
    else:
        # If no doctype, return the cleaned text, hoping for the best
        return cleaned_response.strip()

# --- Extract CSS and JavaScript from HTML ---
def extract_css_js(html: str) -> tuple:
    """
    Extracts CSS and JavaScript from HTML and returns them separately.
    Returns a tuple of (cleaned_html, css, js).
    """
    css = ""
    js = ""
    
    # Extract CSS from style tags
    style_tags = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL | re.IGNORECASE)
    for style in style_tags:
        css += style.strip() + "\n"
    
    # Extract JavaScript from script tags
    script_tags = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    for script in script_tags:
        js += script.strip() + "\n"
    
    # Remove style and script tags from HTML
    cleaned_html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    cleaned_html = re.sub(r'<script[^>]*>.*?</script>', '', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
    
    return cleaned_html.strip(), css.strip(), js.strip()

# --- AI Core Functions ---
def generate_website_code_sync(prompt: str, model: str = "glm-4.5-air", project_type: str = "single", 
                              include_seo: bool = True, make_responsive: bool = True, is_preview: bool = False):
    try:
        # Map the model name to the actual model ID
        model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
        
        # Build the system prompt based on parameters
        system_prompt = (
            "You are a silent HTML code generation machine. Your one and only task is to transform a user's description into a complete, valid HTML file using Tailwind CSS. "
        )
        
        if include_seo:
            system_prompt += "Include SEO-friendly meta tags, proper heading structure, and semantic HTML. "
        
        if make_responsive:
            system_prompt += "Ensure the design is fully responsive for all device sizes. "
        
        if project_type == "multi":
            system_prompt += "This is a single page within a multi-page website. Include navigation to other pages. "
        
        if is_preview:
            system_prompt += "This is a preview, so focus on the main structure and layout. "
        
        system_prompt += (
            "Your entire response MUST be ONLY the raw HTML code. Start directly with `<!DOCTYPE html>`. "
            "DO NOT write any other text, explanations, or comments. Your output is fed directly to a browser."
        )
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        )
        
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html)
    except Exception as e:
        print(f"Build API Error: {e}")
        return None

def edit_website_code_sync(html: str, selector: str, prompt: str, model: str = "glm-4.5-air"):
    try:
        # Map the model name to the actual model ID
        model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
        
        system_prompt = (
            "You are a precise HTML code editor. Your task is to modify a specific element within a given HTML document. "
            f"The user wants to modify the element identified by the CSS selector: `{selector}`. "
            "The user's instruction is: `{prompt}`. "
            "You MUST return the ENTIRE, fully modified HTML document, starting with `<!DOCTYPE html>`. "
            "DO NOT write any explanations or conversational text. Your output must be only the raw, updated HTML code."
        )
        
        user_content = f"Here is the full HTML document to modify:\n\n{html}"
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        )
        
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html)
    except Exception as e:
        print(f"Edit API Error: {e}")
        return None

def diff_patch_website_code_sync(html: str, selector: str, prompt: str, model: str = "glm-4.5-air"):
    """
    Performs a diff-patch operation to modify only the selected element.
    This is more efficient than regenerating the entire page.
    """
    try:
        # Map the model name to the actual model ID
        model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
        
        system_prompt = (
            "You are a precise HTML code editor specializing in targeted edits. Your task is to modify ONLY the specific element "
            f"identified by the CSS selector: `{selector}`. "
            "The user's instruction is: `{prompt}`. "
            "You MUST return ONLY the modified HTML for that specific element, not the entire document. "
            "DO NOT include any explanations or conversational text. Your output must be only the raw HTML for the modified element."
        )
        
        user_content = f"Here is the full HTML document for context:\n\n{html}"
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        )
        
        modified_element = response.choices[0].message.content
        
        # In a real implementation, we would use an HTML parser to find and replace the element
        # For this example, we'll use a simple regex approach (not recommended for production)
        # This is a simplified approach and might not work for all cases
        
        # Try to find the element in the HTML and replace it
        # This is a very basic implementation and would need to be improved for production use
        try:
            # Extract the element tag name from the selector
            tag_match = re.search(r'([a-zA-Z0-9]+)(?=[\s>#.]|$)', selector)
            if not tag_match:
                return html  # Can't determine tag name, return original
            
            tag_name = tag_match.group(1)
            
            # Find the opening and closing tags for the element
            # This is a simplified approach and won't work for nested elements of the same type
            pattern = f'<{tag_name}[^>]*>.*?</{tag_name}>'
            matches = list(re.finditer(pattern, html, re.DOTALL | re.IGNORECASE))
            
            if matches:
                # For simplicity, we'll just replace the first match
                # In a real implementation, we would need to properly identify which match corresponds to the selector
                first_match = matches[0]
                new_html = html[:first_match.start()] + modified_element + html[first_match.end():]
                return new_html
            else:
                return html  # Element not found, return original
        except Exception as e:
            print(f"Diff patch error: {e}")
            return html  # Return original HTML if patching fails
    except Exception as e:
        print(f"Diff Patch API Error: {e}")
        return None

def add_interactive_element_sync(html: str, element_type: str, config: Dict[str, Any], model: str = "glm-4.5-air"):
    try:
        # Map the model name to the actual model ID
        model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
        
        system_prompt = (
            f"You are an expert web developer specializing in interactive elements. Your task is to add a {element_type} "
            "to the provided HTML document. The element should be fully functional and well-styled using Tailwind CSS. "
            "You MUST return the ENTIRE modified HTML document, starting with `<!DOCTYPE html>`. "
            "DO NOT write any explanations or conversational text. Your output must be only the raw, updated HTML code."
        )
        
        config_str = json.dumps(config, indent=2)
        user_content = f"Here is the full HTML document to modify:\n\n{html}\n\nConfiguration for the {element_type}:\n\n{config_str}"
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        )
        
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html)
    except Exception as e:
        print(f"Interactive Element API Error: {e}")
        return None

def apply_seo_changes_sync(html: str, seo_data: Dict[str, str], model: str = "glm-4.5-air"):
    try:
        # Map the model name to the actual model ID
        model_id = MODEL_MAPPING.get(model, MODEL_MAPPING["glm-4.5-air"])
        
        system_prompt = (
            "You are an SEO expert specializing in HTML optimization. Your task is to apply the provided SEO metadata "
            "to the HTML document and optimize it for search engines. This includes adding proper meta tags, "
            "improving heading structure, adding alt attributes to images, and ensuring semantic HTML. "
            "You MUST return the ENTIRE modified HTML document, starting with `<!DOCTYPE html>`. "
            "DO NOT write any explanations or conversational text. Your output must be only the raw, updated HTML code."
        )
        
        seo_str = json.dumps(seo_data, indent=2)
        user_content = f"Here is the full HTML document to modify:\n\n{html}\n\nSEO data to apply:\n\n{seo_str}"
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        )
        
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html)
    except Exception as e:
        print(f"SEO API Error: {e}")
        return None

# --- FastAPI App Setup ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    html_code = generate_website_code_sync(
        request.prompt, 
        request.model, 
        request.projectType, 
        request.includeSeo, 
        request.makeResponsive,
        request.isPreview
    )
    
    if html_code:
        # Extract CSS and JavaScript
        clean_html, css, js = extract_css_js(html_code)
        return {"html": clean_html, "css": css, "js": js}
    
    raise HTTPException(status_code=500, detail="Failed to generate website code.")

@app.post("/edit")
async def create_edit(request: EditRequest):
    html_code = edit_website_code_sync(request.html, request.selector, request.prompt, request.model)
    
    if html_code:
        # Extract CSS and JavaScript
        clean_html, css, js = extract_css_js(html_code)
        return {"html": clean_html, "css": css, "js": js}
    
    raise HTTPException(status_code=500, detail="Failed to edit website code.")

@app.post("/diff-patch")
async def create_diff_patch(request: DiffPatchRequest):
    html_code = diff_patch_website_code_sync(request.html, request.selector, request.prompt, request.model)
    
    if html_code:
        # Extract CSS and JavaScript
        clean_html, css, js = extract_css_js(html_code)
        return {"html": clean_html, "css": css, "js": js}
    
    raise HTTPException(status_code=500, detail="Failed to patch website code.")

@app.post("/add-interactive")
async def add_interactive_element(request: InteractiveRequest):
    html_code = add_interactive_element_sync(request.html, request.type, request.config, request.model)
    
    if html_code:
        # Extract CSS and JavaScript
        clean_html, css, js = extract_css_js(html_code)
        return {"html": clean_html, "css": css, "js": js}
    
    raise HTTPException(status_code=500, detail="Failed to add interactive element.")

@app.post("/apply-seo")
async def apply_seo_changes(request: SeoRequest):
    html_code = apply_seo_changes_sync(request.html, request.seo, request.model)
    
    if html_code:
        # Extract CSS and JavaScript
        clean_html, css, js = extract_css_js(html_code)
        return {"html": clean_html, "css": css, "js": js}
    
    raise HTTPException(status_code=500, detail="Failed to apply SEO changes.")

# --- Gradio Interface (if needed) ---
def gradio_interface():
    with gr.Blocks(title="NeuroArti Pro Builder V2") as demo:
        gr.Markdown("# NeuroArti Pro Builder V2")
        
        with gr.Row():
            with gr.Column():
                prompt = gr.Textbox(label="Describe your website", lines=5)
                model = gr.Dropdown(["glm-4.5-air", "deepseek-r1"], label="AI Model", value="glm-4.5-air")
                build_btn = gr.Button("Generate Website")
            
            with gr.Column():
                html_output = gr.Code(label="Generated HTML", language="html", lines=20)
        
        build_btn.click(
            fn=lambda p, m: generate_website_code_sync(p, m),
            inputs=[prompt, model],
            outputs=html_output
        )
    
    return demo

# Run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
