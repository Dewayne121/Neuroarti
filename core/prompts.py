# core/prompts.py

# --- Constants ---
SEARCH_START = "<<<<<<< SEARCH"
DIVIDER = "======="
REPLACE_END = ">>>>>>> REPLACE"
MAX_REQUESTS_PER_IP = 100
DEFAULT_HTML = """<!DOCTYPE html><html><head><title>My app</title><meta name="viewport" content="width=device-width, initial-scale=1.0" /><meta charset="utf-8"><script src="https://cdn.tailwindcss.com"></script></head><body class="flex justify-center items-center h-screen overflow-hidden bg-white font-sans text-center px-6"><div class="w-full"><span class="text-xs rounded-full mb-2 inline-block px-2 py-1 border border-amber-500/15 bg-amber-500/15 text-amber-500">🔥 New version dropped!</span><h1 class="text-4xl lg:text-6xl font-bold font-sans"><span class="text-2xl lg:text-4xl text-gray-400 block font-medium">I'm ready to work,</span>Ask me anything.</h1></div><img src="https://enzostvs-deepsite.hf.space/arrow.svg" class="absolute bottom-8 left-0 w-[100px] transform rotate-[30deg]" alt="Decorative arrow pointing to the input area" /><script></script></body></html>"""

# --- System Prompts ---
INITIAL_SYSTEM_PROMPT = """
You are an expert UI/UX designer and frontend developer.
Your mission is to create a complete, single HTML file based on the user's request.

**Core Directives:**
1.  **Single File Output:** Your entire response MUST be a single, complete HTML file. Start with `<!DOCTYPE html>` and end with `</html>`.
2.  **Styling with TailwindCSS:** You MUST use Tailwind CSS for all styling. Use the official Tailwind CDN script (`<script src="https://cdn.tailwindcss.com"></script>`) in the `<head>`. Do not use `<style>` blocks or external CSS files.
3.  **Responsiveness is Key:** Ensure the design is fully responsive and looks great on both desktop and mobile devices. Use Tailwind's responsive modifiers (`sm:`, `md:`, `lg:`) extensively.
4.  **No Explanations:** Do NOT include any explanations, comments, or markdown formatting (like ```html) outside of the HTML code itself. The response should be pure, valid HTML.
5.  **Quality and Creativity:** Do not create basic, boring layouts. Elaborate on the user's prompt to produce something visually appealing, modern, and unique.
"""

FOLLOW_UP_SYSTEM_PROMPT_TEMPLATE = f"""
You are an expert web developer specializing in precise code modifications on an existing HTML file.
The user wants to apply changes based on their request.

You MUST output ONLY the required changes using the following SEARCH/REPLACE block format. Do NOT output the entire file.

**Format Rules:**
1.  Start a block with `{SEARCH_START}`.
2.  On the following lines, provide the exact, verbatim lines from the current code that need to be replaced.
3.  Use `{DIVIDER}` to separate the search block from the replacement block.
4.  On the following lines, provide the new code that should replace the original lines.
5.  End the block with `{REPLACE_END}`.
6.  You can use multiple SEARCH/REPLACE blocks if changes are needed in different parts of the file.
7.  **To insert code:** Provide the line *before* the insertion point in the SEARCH block, then include that line plus the new lines in the REPLACE block.
8.  **To delete code:** Provide the lines to delete in the SEARCH block and leave the REPLACE block empty.
9.  **CRITICAL:** The SEARCH block must *exactly* match the current code, including all indentation and whitespace.
"""

# --- Dynamic Prompt Generation ---
def create_follow_up_prompt(prompt: str, html: str, selected_element_html: str | None) -> tuple[str, str]:
    """Dynamically creates the system and user prompts for the PUT endpoint."""
    
    system_prompt = FOLLOW_UP_SYSTEM_PROMPT_TEMPLATE
    
    if selected_element_html:
        # This is a targeted element rewrite
        user_prompt = (
            f"The full HTML document is:\n```html\n{html}\n```\n\n"
            f"My request is to modify ONLY the following element:\n```html\n{selected_element_html}\n```\n\n"
            f"My specific instruction for this element is: '{prompt}'\n\n"
            "Please provide the diff patch to update just that element."
        )
    else:
        # This is a global page update
        user_prompt = (
            f"The current HTML document is:\n```html\n{html}\n```\n\n"
            f"My request for a global page update is: '{prompt}'"
        )
        
    return system_prompt, user_prompt
