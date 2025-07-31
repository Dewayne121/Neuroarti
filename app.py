import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re

# --- Pydantic Models for API Request Bodies ---
class BuildRequest(BaseModel):
    prompt: str

class EditRequest(BaseModel):
    html: str
    selector: str
    prompt: str

# --- Configuration ---
API_KEY = os.environ.get("GLM_API_KEY") 

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1", 
)

# --- NEW: AI Response Sanitization Function ---
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

# --- AI Core Functions ---
def generate_website_code_sync(prompt: str):
    try:
        # HYPER-STRICT PROMPT for building
        system_prompt = (
            "You are a silent HTML code generation machine. Your one and only task is to transform a user's description into a complete, valid HTML file using Tailwind CSS. "
            "Your entire response MUST be ONLY the raw HTML code. Start directly with `<!DOCTYPE html>`. "
            "DO NOT write any other text, explanations, or comments. Your output is fed directly to a browser."
        )
        response = client.chat.completions.create(
            model="zai-org/GLM-4.5-Air-FP8",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        )
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html)
    except Exception as e:
        print(f"Build API Error: {e}")
        return None

def edit_website_code_sync(html: str, selector: str, prompt: str):
    try:
        # HYPER-STRICT PROMPT for editing
        system_prompt = (
            "You are a precise HTML code editor. Your task is to modify a specific element within a given HTML document. "
            f"The user wants to modify the element identified by the CSS selector: `{selector}`. "
            "The user's instruction is: `{prompt}`. "
            "You MUST return the ENTIRE, fully modified HTML document, starting with `<!DOCTYPE html>`. "
            "DO NOT write any explanations or conversational text. Your output must be only the raw, updated HTML code."
        )
        user_content = f"Here is the full HTML document to modify:\n\n{html}"
        
        response = client.chat.completions.create(
            model="zai-org/GLM-4.5-Air-FP8",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        )
        raw_html = response.choices[0].message.content
        return clean_html_response(raw_html)
    except Exception as e:
        print(f"Edit API Error: {e}")
        return None

# --- FastAPI App Setup ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    html_code = generate_website_code_sync(request.prompt)
    if html_code:
        return {"html": html_code}
    return {"error": "Failed to generate website code."}, 500

@app.post("/edit")
async def create_edit(request: EditRequest):
    html_code = edit_website_code_sync(request.html, request.selector, request.prompt)
    if html_code:
        return {"html": html_code}
    return {"error": "Failed to edit website code."}, 500
