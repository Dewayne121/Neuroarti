import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

# --- AI Core Functions ---
def generate_website_code_sync(prompt: str):
    try:
        system_prompt = (
            "You are a silent HTML code generation machine. Your one and only task is to transform a user's description into a complete, valid HTML file using Tailwind CSS. "
            "Your output MUST start with `<!DOCTYPE html>` and nothing else. "
            "DO NOT, under any circumstances, write any conversational text, explanations, or comments before the HTML code. Your response must be ONLY the raw HTML code."
        )
        response = client.chat.completions.create(
            model="zai-org/GLM-4.5-Air-FP8",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Build API Error: {e}")
        return None

def edit_website_code_sync(html: str, selector: str, prompt: str):
    try:
        system_prompt = (
            "You are a surgical HTML code editor. Your task is to modify a specific element within a given HTML document based on a user's request. "
            f"The user wants to modify the element identified by the CSS selector: `{selector}`. "
            "The user's instruction is: `{prompt}`. "
            "You MUST return the ENTIRE, fully modified HTML document. Do not return only the changed part. Do not add any explanations."
        )
        # Note: We send the original HTML as part of the "user" message for the AI to edit.
        user_content = f"Here is the full HTML document to modify:\n\n```html\n{html}\n```"
        
        response = client.chat.completions.create(
            model="zai-org/GLM-4.5-Air-FP8",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        )
        return response.choices[0].message.content
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
