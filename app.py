import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Pydantic Model for API Request Body ---
# This defines the expected JSON structure for our API call
class PromptRequest(BaseModel):
    prompt: str

# --- Configuration ---
API_KEY = os.environ.get("GLM_API_KEY") 

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1", 
)

# --- AI Core Function ---
def generate_website_code_sync(prompt: str):
    # This is the synchronous version of the function for our API
    if not API_KEY:
        raise gr.Error("API Key is not configured.")

    try:
        system_prompt = (
            "You are a world-class web developer who ONLY outputs raw HTML code. "
            "Your ONLY job is to convert a user's description into a single, complete, and valid HTML file using Tailwind CSS for styling. "
            "CRITICAL REQUIREMENTS: "
            "1. The output MUST be a full HTML document starting with `<!DOCTYPE html>`."
            "2. The `<head>` section MUST contain `<script src=\"https://cdn.tailwindcss.com\"></script>`."
            "3. The design must be modern, clean, and aesthetically pleasing."
            "4. DO NOT include any explanations, comments, or markdown formatting like ` ```html `."
        )

        response = client.chat.completions.create(
            model="zai-org/GLM-4.5-Air-FP8",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
        )
        
        return response.choices[0].message.content

    except Exception as e:
        # For an API, we should return a proper error, not a Gradio error
        print(f"API Error: {e}")
        return None


# --- FastAPI App Setup ---
app = FastAPI()

# Add CORS middleware to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Create the dedicated API endpoint ---
@app.post("/build")
async def create_build(request: PromptRequest):
    """
    This is our dedicated, robust API endpoint for building websites.
    """
    html_code = generate_website_code_sync(request.prompt)
    if html_code:
        return {"html": html_code}
    else:
        return {"error": "Failed to generate website code."}, 500

# Note: We are no longer mounting the Gradio UI. 
# The backend is now a pure API server.
