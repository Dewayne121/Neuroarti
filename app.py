import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import re
import json
from typing import Dict, Any
from bs4 import BeautifulSoup

# --- Pydantic Models ---
class BuildRequest(BaseModel):
    prompt: str
    model: str = "glm-4.5-air"

class EditSnippetRequest(BaseModel):
    snippet: str
    prompt: str
    model: str = "glm-4.5-air"

class PatchRequest(BaseModel):
    html: str
    selector: str
    new_snippet: str

# --- Configuration ---
API_KEY = os.environ.get("GLM_API_KEY")
if not API_KEY:
    raise ValueError("API Key not found. Please set the GLM_API_KEY environment variable.")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1",
)

MODEL_MAPPING = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/deepseek-coder-33b-instruct" 
}

# --- Helper Functions ---
def clean_html_response(raw_response: str, is_snippet=False) -> str:
    cleaned = raw_response.strip()
    
    # --- FIX #1: AGGRESSIVE PARSER TO REMOVE AI CHATTER ---
    if is_snippet:
        # First, try to find a markdown code block, which is the most common format for chatter.
        code_block_match = re.search(r'```html\n(.*?)```', cleaned, re.DOTALL)
        if code_block_match:
            # If found, return ONLY the content inside.
            return code_block_match.group(1).strip()

        # If no markdown block, it might be raw code with chatter before/after.
        # Find the first opening tag and the last closing tag.
        first_tag_match = re.search(r'<', cleaned)
        last_tag_match = re.search(r'>', cleaned[::-1]) # Search on a reversed string
        
        if first_tag_match and last_tag_match:
            start_index = first_tag_match.start()
            # Calculate the end index from the reversed string match
            end_index = len(cleaned) - last_tag_match.start()
            # This slices the string from the first '<' to the last '>'
            return cleaned[start_index:end_index].strip()
        
        # If all else fails (e.g., response is just text), return an empty string to avoid breaking the UI.
        return ""

    # For full HTML documents, the old logic is fine.
    doctype_match = re.search(r'<!DOCTYPE html.*?>', cleaned, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return cleaned[doctype_match.start():].strip()
    return cleaned.strip()

def extract_assets(html_content: str) -> tuple:
    soup = BeautifulSoup(html_content, 'html.parser')
    css = "\n".join(style.string or '' for style in soup.find_all('style'))
    js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
    
    body_tag = soup.find('body')
    body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

    return body_content, css.strip(), js.strip()

# --- AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1, # Further lowered temperature for maximum predictability
            max_tokens=4096,
        )
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html, is_snippet=is_snippet)
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    system_prompt = (
        "You are an expert frontend developer. Generate a complete, single HTML file using Tailwind CSS via CDN. "
        "Place all CSS in one `<style>` tag in the `<head>` and all JS in one `<script>` tag before `</body>`. "
        "Your output must be ONLY the raw HTML code, starting with `<!DOCTYPE html>`. No explanations."
    )
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code:
        body_html, css, js = extract_assets(html_code)
        return {"html": body_html, "css": css, "js": js}
    raise HTTPException(status_code=500, detail="Failed to generate website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # --- FIX #2: BRUTALLY STRICT SYSTEM PROMPT ---
    system_prompt = (
        "You are a silent code transformation tool. You will receive an HTML snippet and an instruction. "
        "Your response MUST be ONLY the modified HTML snippet. "
        "DO NOT add any text, explanations, or markdown formatting like ```html. "
        "Your entire response MUST BE valid HTML code and nothing else. "
        "This is not a conversation. You are a parser that outputs code."
    )
    
    user_prompt = f"Instruction: '{request.prompt}'.\n\nHTML Snippet:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    if modified_snippet:
        return {"snippet": modified_snippet}
    # Provide a more specific error if the cleaning process results in an empty string
    raise HTTPException(status_code=500, detail="AI response was unclear or contained no code. Please try again with a more specific prompt.")

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)

        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' did not find any element to patch.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        # Check for contents to handle empty or invalid snippets from the AI
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="AI returned an empty or invalid HTML snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            raise HTTPException(status_code=500, detail="Failed to parse the new snippet from AI.")

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
