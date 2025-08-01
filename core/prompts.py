# core/prompts.py
SEARCH_START = "<<<<<<< SEARCH"

This method gives the AI the context it desperately needed while putting it in a virtual straitjacket, forcing it to focus
DIVIDER = "======="
REPLACE_END = ">>>>>>> REPLACE"
MAX_REQUESTS_PER_IP = 100
INITIAL_SYSTEM_PROMPT = """You are an expert UI/UX designer and its changes with surgical precision.

Here are all the updated backend files and the single required change to the frontend.

--- frontend developer. Your task is to create a complete, single HTML file based on the user's prompt, using only

### File 1 of 5: `prompts.py` (Updated)

The old, ineffective rewrite prompts have been removed and replaced with the new, powerful "surgical edit" prompt.

```python
# core/prompts. HTML, CSS, and JavaScript.
**Design & Code Mandates:**
1.  **Structure:** Well-structuredpy
SEARCH_START = "<<<<<<< SEARCH"
DIVIDER = "======="
REPLACE_END = with semantic HTML5 tags.
2.  **Styling:** Use Tailwind CSS via CDN. Do not use custom `<style>` blocks.
3.  **Responsiveness:** Must be fully responsive.
4.  **Content ">>>>>>> REPLACE"
MAX_REQUESTS_PER_IP = 100
INITIAL_SYSTEM_PROMPT =:** Create rich, elaborate, and unique content with high-quality placeholders.
5.  **Output Format:** Your entire """You are an expert UI/UX designer and frontend developer. Your task is to create a complete, single HTML file response MUST be a single, complete HTML file. Do not include any explanations, comments, or markdown formatting outside of the HTML code itself based on the user's prompt, using only HTML, CSS, and JavaScript.
**Design & Code Mandates:**
.
"""
FOLLOW_UP_SYSTEM_PROMPT = f"""You are an expert web developer specializing in precise1.  **Structure:** Well-structured with semantic HTML5 tags.
2.  **Styling:** Use, multi-location code modifications on a full HTML page.
You MUST STRICTLY follow the SEARCH/REPLACE block Tailwind CSS via CDN. Do not use custom `<style>` blocks.
3.  **Responsiveness:** Must be fully responsive.
4.  **Accessibility (A11y):** Design with accessibility in mind.
5.  ** format provided below. Do NOT output the entire HTML file.
**CRITICAL FORMATTING RULES:**
1.  StartInteractivity:** Add subtle hover effects and transitions.
6.  **Content:** Create rich, elaborate, and unique each modification block with `{SEARCH_START}`.
2.  Use `{DIVIDER}` to separate the SEARCH block content with high-quality placeholders.
7.  **Output Format:** Your entire response MUST be a single, complete HTML file. Do not include any explanations, comments, or markdown formatting outside of the HTML code itself.
"""
FOLLOW from the REPLACE block.
3.  End each modification block with `{REPLACE_END}`.
"""
# --- NEW, DEFINITIVE PROMPT FOR SURGICAL ELEMENT EDITING ---
SYSTEM_PROMPT_SURG_UP_SYSTEM_PROMPT = f"""You are an expert web developer specializing in precise, multi-location code modificationsICAL_EDIT = (
    "You are a surgical HTML editor. Your task is to modify a single element within a full HTML document based on a user's request. "
    "I have provided the entire HTML document and marked the specific element to on a full HTML page.
You MUST STRICTLY follow the SEARCH/REPLACE block format provided below. Do NOT output be modified with the attribute `data-neuro-edit-target=\"true\"`. "
    "**CRITICAL MAND the entire HTML file.
**CRITICAL FORMATTING RULES:**
1.  Start each modification block with `{SEARCH_START}`ATES:**\n"
    "1.  **SCOPE:** Your ONLY task is to apply the user's changes.
2.  Inside the SEARCH block, provide the EXACT lines from the current code that need to be changed.
3 to the element marked with `data-neuro-edit-target=\"true\"` and its children. You are **STRICTLY FORBIDDEN** from modifying any other part of the document. For example, if the target is an `<h2>`, you.  Use `{DIVIDER}` to separate the SEARCH block from the REPLACE block.
4.  Inside the REPLACE MUST NOT change any other `<h3>` or `<p>` tags elsewhere in the document.\n"
    "2. block, provide the new lines of code.
5.  End each modification block with `{REPLACE_END}`.
"""  **STYLING:** All style changes **MUST** be made using inline Tailwind CSS classes on the target element or
# --- NEW, DEFINITIVE PROMPT FOR SURGICAL ELEMENT EDITING ---
SYSTEM_PROMPT_SURG its children. You are **STRICTLY FORBIDDEN** from adding any global `<style>` blocks or CSS that wouldICAL_EDIT = (
    "You are a surgical HTML editor. Your task is to modify a single element within a affect other elements.\n"
    "3.  **CLEANUP:** After applying the changes, you ** full HTML document based on a user's request. "
    "I have provided the entire HTML document and marked the specificMUST** remove the `data-neuro-edit-target=\"true\"` attribute from the element.\n"
 element to be modified with the attribute `data-neuro-edit-target=\"true\"`. "
    "**    "4.  **OUTPUT:** Your response **MUST** be the complete, full HTML document from `<!DOCTYPE html>`CRITICAL MANDATES:**\n"
    "1.  **SCOPE:** You MUST apply the user's changes to `</html>` with only the surgical modification applied. Do not include explanations, markdown, or any other text."
) **ONLY** to the element marked with `data-neuro-edit-target=\"true\"` and its children. You
DEFAULT_HTML = """<!DOCTYPE html><html><head><title>My app</title><meta name=\" are **STRICTLY FORBIDDEN** from modifying any other part of the document.\n"
    "2.  viewport\" content=\"width=device-width, initial-scale=1.0\" /><meta charset=\"utf-8\**STYLING:** All style changes **MUST** be made using inline Tailwind CSS classes. You are **STRICTLY"><script src=\"https://cdn.tailwindcss.com\"></script></head><body class=\"flex justify-center items- FORBIDDEN** from adding any global `<style>` blocks or CSS that would affect other elements.\n"
    "3center h-screen overflow-hidden bg-white font-sans text-center px-6\"><div class=\"w.  **CLEANUP:** After applying the changes, you **MUST** remove the `data-neuro-edit-full\"><span class=\"text-xs rounded-full mb-2 inline-block px-2 py-1 border-target=\"true\"` attribute from the element.\n"
    "4.  **OUTPUT:** Your response **MUST** be the complete, full HTML document from `<!DOCTYPE html>` to `</html>` with only the surgical border-amber-500/15 bg-amber-500/15 text-amber-5 modification applied. Do not include explanations, markdown, or any other text."
)
DEFAULT_HTML = """<00\">🔥 New version dropped!</span><h1 class=\"text-4xl lg:text-6xl font-bold font-sans\"><span class=\"text-2xl lg:text-4xl text-gray-4!DOCTYPE html><html><head><title>My app</title><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" /><meta charset=\"utf-8\"><script src=\"https://cdn00 block font-medium\">I'm ready to work,</span>Ask me anything.</h1></div><img src.tailwindcss.com\"></script></head><body class=\"flex justify-center items-center h-screen overflow=\"https://enzostvs-deepsite.hf.space/arrow.svg\" class=\"absolute bottom-8 left-hidden bg-white font-sans text-center px-6\"><div class=\"w-full\"><span class=\"text-xs rounded-full mb-2 inline-block px-2 py-1 border border-amber-0 w-[100px] transform rotate-[30deg]\" alt=\"Decorative arrow pointing to the input area-500/15 bg-amber-500/15 text-amber-500\">\" /><script></script></body></html>"""
