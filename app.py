import gradio as gr
import os
from openai import OpenAI
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- Configuration ---
API_KEY = os.environ.get("GLM_API_KEY") 

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1", 
)

# --- AI Core Function (No changes here) ---
def generate_website_code(prompt: str):
    if not API_KEY:
        raise gr.Error("API Key is not configured.")

    try:
        system_prompt = (
            "You are a world-class web developer who ONLY outputs raw HTML code. "
            "Your ONLY job is to convert a user's description into a single, complete, and valid HTML file using Tailwind CSS for styling. "
            "CRITICAL REQUIREMENTS: "
            "1. The output MUST be a full HTML document starting with `<!DOCTYPE html>` and enclosed in `<html>` tags."
            "2. The `<head>` section MUST contain `<script src=\"https://cdn.tailwindcss.com\"></script>` to enable Tailwind CSS."
            "3. The design must be modern, clean, and aesthetically pleasing."
            "4. DO NOT include any explanations, comments, or markdown formatting like ```html. The output must be ONLY the raw HTML code itself."
        )

        response = client.chat.completions.create(
            model="zai-org/GLM-4.5-Air-FP8",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
        )
        
        html_code = response.choices[0].message.content
        return html_code, html_code

    except Exception as e:
        raise gr.Error(f"An API error occurred: {e}")


# --- Create Gradio UI (No changes here) ---
with gr.Blocks(theme=gr.themes.Default(primary_hue="orange")) as demo:
    gr.Markdown("# 🤖 AI Website Builder")
    # ... (the rest of your Gradio UI definition is the same)
    with gr.Row():
        with gr.Column(scale=1):
            prompt_input = gr.Textbox(lines=10, placeholder="e.g., A sleek landing page...", label="Describe your website")
            submit_button = gr.Button("Build Website", variant="primary")
        with gr.Column(scale=3):
            with gr.Tabs():
                with gr.TabItem("Live Preview"):
                    html_output = gr.HTML(label="Live Preview", value="<div>...</div>", show_label=False)
                with gr.TabItem("Code"):
                    code_output = gr.Code(label="Generated Code", language="html", interactive=False)
    
    submit_button.click(
        fn=generate_website_code,
        inputs=[prompt_input],
        outputs=[html_output, code_output],
        api_name="build" 
    )

# --- THE FINAL FIX: MOUNT GRADIO ON A FASTAPI APP ---
# 1. Create a FastAPI app
app = FastAPI()

# 2. Add the CORS middleware to the FastAPI app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Mount the Gradio app onto the FastAPI app
app = gr.mount_gradio_app(app, demo, path="/")

# Note: The if __name__ == "__main__" block is no longer needed for Railway,
# as the Procfile now directly uses uvicorn to run the `app` object.
