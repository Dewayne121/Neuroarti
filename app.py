import gradio as gr
import os
from openai import OpenAI

# --- Configuration ---
API_KEY = os.environ.get("GLM_API_KEY") 

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1", 
)

# --- AI Core Function ---
def generate_website_code(prompt: str):
    if not API_KEY:
        raise gr.Error("API Key is not configured. Please add your Together AI key as a variable in Railway.")

    try:
        # --- THE BULLETPROOF SYSTEM PROMPT ---
        system_prompt = (
            "You are a world-class web developer who ONLY outputs raw HTML code. "
            "Your ONLY job is to convert a user's description into a single, complete, and valid HTML file using Tailwind CSS for styling. "
            "CRITICAL REQUIREMENTS: "
            "1. The output MUST be a full HTML document starting with `<!DOCTYPE html>` and enclosed in `<html>` tags."
            "2. The `<head>` section MUST contain `<script src=\"https://cdn.tailwindcss.com\"></script>` to enable Tailwind CSS."
            "3. The design must be modern, clean, and aesthetically pleasing, with good use of colors and spacing."
            "4. DO NOT include any explanations, comments, or markdown formatting like ```html. The output must be ONLY the raw HTML code itself, starting with `<!DOCTYPE html>`."
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


# --- GRADIO UI (No changes here) ---
with gr.Blocks(theme=gr.themes.Default(primary_hue="orange")) as demo:
    gr.Markdown("# 🤖 AI Website Builder")
    gr.Markdown("Enter a description of the website you want to create, and the AI will build it on the right.")

    with gr.Row():
        with gr.Column(scale=1):
            prompt_input = gr.Textbox(
                lines=10, 
                placeholder="e.g., A sleek landing page for a SaaS company called 'SynthFlow'. It should have a dark theme, a hero section with a glowing button, a features grid, and a simple footer.", 
                label="Describe your website"
            )
            submit_button = gr.Button("Build Website", variant="primary")

        with gr.Column(scale=3):
            with gr.Tabs():
                with gr.TabItem("Live Preview"):
                    html_output = gr.HTML(
                        label="Live Preview",
                        value="<div style='display:flex; justify-content:center; align-items:center; height:100%; font-family:sans-serif; color: #aaa;'>Your website will appear here.</div>",
                        show_label=False
                    )
                with gr.TabItem("Code"):
                    code_output = gr.Code(
                        label="Generated Code",
                        language="html",
                        interactive=False
                    )

    submit_button.click(
        fn=generate_website_code,
        inputs=[prompt_input],
        outputs=[html_output, code_output]
    )


# --- Launch the App ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 7860)) 
    demo.launch(server_name="0.0.0.0", server_port=port)
