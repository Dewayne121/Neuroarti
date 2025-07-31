import gradio as gr
import os
import zhipuai

# --- Configuration ---
# This line securely gets your API key from Railway's "secrets" or "variables".
API_KEY = os.environ.get("GLM_API_KEY") 

# This sets up the connection to the AI service.
client = zhipuai.ZhipuAI(api_key=API_KEY)

# --- AI Core Function ---
def generate_website_code(prompt: str):
    """
    Takes a user prompt, sends it to the GLM API, and returns the generated HTML code.
    """
    if not API_KEY:
        # This is an important check. If the API key isn't set, we show an error.
        raise gr.Error("GLM_API_KEY is not configured. Please add it as a variable in Railway.")

    try:
        # This is the "instruction manual" we give to the AI.
        # It's very important for getting good, clean HTML back.
        system_prompt = (
            "You are an expert web developer specializing in Tailwind CSS. "
            "Your task is to generate a single, complete HTML file based on the user's request. "
            "The HTML file must include a <head> section that links to the Tailwind CSS CDN. "
            "Do not include any explanations, comments, or markdown formatting like ```html. "
            "Only output the raw HTML code."
        )

        # Sending the actual request to the AI model
        response = client.chat.completions.create(
            model="glm-4-air",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
        )
        
        # Extracting the HTML code from the AI's response
        html_code = response.choices[0].message.content
        return html_code

    except Exception as e:
        # If anything goes wrong, show a user-friendly error.
        raise gr.Error(f"An error occurred: {e}")


# --- Gradio UI ---
# This part builds the visual interface using Gradio.
# It's creating the "deepseek"-style layout.
with gr.Blocks(theme=gr.themes.Default(primary_hue="orange")) as demo:
    gr.Markdown("# 🤖 AI Website Builder")
    gr.Markdown("Enter a description of the website you want to create, and the AI will build it on the right.")

    with gr.Row():
        # Left column for user input
        with gr.Column(scale=1):
            prompt_input = gr.Textbox(
                lines=5, 
                placeholder="e.g., A modern landing page for a new AI startup.", 
                label="Describe your website"
            )
            submit_button = gr.Button("Build Website", variant="primary")

        # Right column for the live preview
        with gr.Column(scale=3):
            html_output = gr.HTML(
                label="Live Preview",
                value="<div style='display:flex; justify-content:center; align-items:center; height:100%; font-family:sans-serif; color: #aaa;'>Your website will appear here.</div>",
                show_label=False
            )

    # --- Event Handling ---
    # This connects the button click to our Python function.
    submit_button.click(
        fn=generate_website_code,
        inputs=[prompt_input],
        outputs=[html_output]
    )


# --- Launch the App ---
# This is the special part for Railway.
if __name__ == "__main__":
    # Railway tells our app which port to use through an environment variable called 'PORT'.
    port = int(os.environ.get('PORT', 7860)) 
    
    # We launch the Gradio app, telling it to be accessible from the internet ('0.0.0.0')
    # and to use the port Railway gave us.
    demo.launch(server_name="0.0.0.0", server_port=port)
