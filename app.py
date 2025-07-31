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
        # The new, much better system prompt!
        system_prompt = (
            "You are an elite web developer who specializes in creating beautiful, modern, and responsive websites using Tailwind CSS. Your designs are clean, professional, and aesthetically pleasing. "
            "Your task is to generate a single, complete HTML file based on the user's request. "
            "The HTML file MUST include: "
            "1. A complete HTML structure (`<!DOCTYPE html>`, `<html>`, `<head>`, `<body>`)."
            "2. A `<head>` section that links to the official Tailwind CSS CDN: `<script src=\"https://cdn.tailwindcss.com\"></script>`."
            "3. Use modern design principles: good use of whitespace, professional color palettes (e.g., neutral colors with a single accent color), and excellent typography (e.g., `sans-serif` fonts)."
            "4. Make elements visually appealing. Use subtle shadows (`shadow-lg`), rounded corners (`rounded-xl`), and smooth transitions where appropriate."
            "5. The output MUST be only the raw HTML code. Do not include any explanations, comments, or markdown formatting like ```html. Just the code."
        )

        response = client.chat.completions.create(
            model="zai-org/GLM-4.5-Air-FP8",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
        )
        
        html_code = response.choices[0].message.content
        # The function now returns the same code twice to update both UI components
        return html_code, html_code

    except Exception as e:
        raise gr.Error(f"An API error occurred: {e}")


# --- NEW GRADIO UI ---
with gr.Blocks(theme=gr.themes.Default(primary_hue="orange")) as demo:
    gr.Markdown("# 🤖 AI Website Builder")
    gr.Markdown("Enter a description of the website you want to create, and the AI will build it on the right.")

    with gr.Row():
        # --- Left Column for Inputs ---
        with gr.Column(scale=1):
            prompt_input = gr.Textbox(
                lines=10, 
                placeholder="e.g., A sleek landing page for a SaaS company called 'SynthFlow'. It should have a dark theme, a hero section with a glowing button, a features grid, and a simple footer.", 
                label="Describe your website"
            )
            submit_button = gr.Button("Build Website", variant="primary")

        # --- Right Column for Outputs (with Tabs) ---
        with gr.Column(scale=3):
            with gr.Tabs():
                # Tab 1: Live Preview
                with gr.TabItem("Live Preview"):
                    html_output = gr.HTML(
                        label="Live Preview",
                        value="<div style='display:flex; justify-content:center; align-items:center; height:100%; font-family:sans-serif; color: #aaa;'>Your website will appear here.</div>",
                        show_label=False
                    )
                # Tab 2: Code Viewer
                with gr.TabItem("Code"):
                    code_output = gr.Code(
                        label="Generated Code",
                        language="html",
                        interactive=False # User cannot edit this directly
                    )

    # --- Event Handling ---
    # The button click now updates TWO outputs: html_output and code_output
    submit_button.click(
        fn=generate_website_code,
        inputs=[prompt_input],
        outputs=[html_output, code_output]
    )


# --- Launch the App ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 7860)) 
    demo.launch(server_name="0.0.0.0", server_port=port)
