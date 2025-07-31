import gradio as gr
import os
from openai import OpenAI

# --- Configuration ---
# Make sure the value for this variable in Railway is your TOGETHER AI key.
API_KEY = os.environ.get("GLM_API_KEY") 

# This client is already correctly configured for Together AI's server.
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1", 
)

# --- AI Core Function ---
def generate_website_code(prompt: str):
    if not API_KEY:
        raise gr.Error("API Key is not configured. Please add your Together AI key as a variable in Railway.")

    try:
        # The system prompt is still perfect.
        system_prompt = (
            "You are an expert web developer specializing in Tailwind CSS. "
            "Your task is to generate a single, complete HTML file based on the user's request. "
            "The HTML file must include a <head> section that links to the Tailwind CSS CDN. "
            "Do not include any explanations, comments, or markdown formatting like ```html. "
            "Only output the raw HTML code."
        )

        response = client.chat.completions.create(
            # Using the correct model name for Together AI!
            model="zai-org/GLM-4.5-Air-FP8", # <<< THIS IS THE CRITICAL CHANGE
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
        )
        
        html_code = response.choices[0].message.content
        return html_code

    except Exception as e:
        raise gr.Error(f"An API error occurred: {e}")


# --- Gradio UI (No changes needed) ---
with gr.Blocks(theme=gr.themes.Default(primary_hue="orange")) as demo:
    gr.Markdown("# 🤖 AI Website Builder")
    gr.Markdown("Enter a description of the website you want to create, and the AI will build it on the right.")
    with gr.Row():
        with gr.Column(scale=1):
            prompt_input = gr.Textbox(
                lines=5, 
                placeholder="e.g., A modern landing page for a new AI startup.", 
                label="Describe your website"
            )
            submit_button = gr.Button("Build Website", variant="primary")
        with gr.Column(scale=3):
            html_output = gr.HTML(
                label="Live Preview",
                value="<div style='display:flex; justify-content:center; align-items:center; height:100%; font-family:sans-serif; color: #aaa;'>Your website will appear here.</div>",
                show_label=False
            )
    submit_button.click(
        fn=generate_website_code,
        inputs=[prompt_input],
        outputs=[html_output]
    )


# --- Launch the App (No changes needed) ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 7860)) 
    demo.launch(server_name="0.0.0.0", server_port=port)
