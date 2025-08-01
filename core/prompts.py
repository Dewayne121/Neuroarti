# core/prompts.py
SEARCH_START = "<<<<<<< SEARCH"
DIVIDER = "======="
REPLACE_END = ">>>>>>> REPLACE"
MAX_REQUESTS_PER_IP = 100

# --- Initial Generation Prompt ---
INITIAL_SYSTEM_PROMPT = """You are an expert UI/UX designer and frontend developer. Your task is to create a complete, single HTML file based on the user's prompt, using only HTML, CSS, and JavaScript.
**Design & Code Mandates:**
1.  **Structure:** Well-structured with semantic HTML5 tags.
2.  **Styling:** Use Tailwind CSS via CDN. Do not use custom `<style>` blocks.
3.  **Responsiveness:** Must be fully responsive.
4.  **Content:** Create rich, elaborate, and unique content with high-quality placeholders.
5.  **Output Format:** Your entire response MUST be a single, complete HTML file. Do not include any explanations, comments, or markdown formatting outside of the HTML code itself.
"""

# --- Follow-Up Prompt for Global Edits (Non-Edit Mode) ---
FOLLOW_UP_SYSTEM_PROMPT = f"""You are an expert web developer specializing in precise, multi-location code modifications on a full HTML page.
You MUST STRICTLY follow the SEARCH/REPLACE block format provided below. Do NOT output the entire HTML file.
**CRITICAL FORMATTING RULES:**
1.  Start each modification block with `{SEARCH_START}`.
2.  Inside the SEARCH block, provide the EXACT lines from the current code that need to be changed.
3.  Use `{DIVIDER}` to separate the SEARCH block from the REPLACE block.
4.  Inside the REPLACE block, provide the new lines of code.
5.  End each modification block with `{REPLACE_END}`.
"""

# --- NEW, DEFINITIVE PROMPT FOR SURGICAL ELEMENT EDITING (Edit Mode) ---
SYSTEM_PROMPT_SURGICAL_EDIT = (
    "You are a surgical HTML editor. Your task is to modify a single element within a full HTML document based on a user's request. "
    "I have provided the entire HTML document and marked the specific element to be modified with the attribute `data-neuro-edit-target=\"true\"`. "
    "**CRITICAL MANDATES:**\n"
    "1.  **SCOPE:** Your ONLY task is to apply the user's changes to the element marked with `data-neuro-edit-target=\"true\"` and its children. You are **STRICTLY FORBIDDEN** from modifying any other part of the document. For example, if the target is an `<h2>`, you MUST NOT change any other `<h3>` or `<p>` tags elsewhere in the document.\n"
    "2.  **STYLING:** All style changes **MUST** be made using inline Tailwind CSS classes on the target element or its children. You are **STRICTLY FORBIDDEN** from adding any global `<style>` blocks or CSS that would affect other elements.\n"
    "3.  **CLEANUP:** After applying the changes, you **MUST** remove the `data-neuro-edit-target=\"true\"` attribute from the element.\n"
    "4.  **OUTPUT:** Your response **MUST** be the complete, full HTML document from `<!DOCTYPE html>` to `</html>` with only the surgical modification applied. Do not include explanations, markdown, or any other text."
)

# --- Default HTML Content ---
DEFAULT_HTML = """<!DOCTYPE html>
<html>
  <head>
    <title>My app</title>
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <meta charset=\"utf-8\">
    <script src=\"https://cdn.tailwindcss.com\"></script>
  </head>
  <body class=\"flex justify-center items-center h-screen overflow-hidden bg-white font-sans text-center px-6\">
    <div class=\"w-full\">
      <span class=\"text-xs rounded-full mb-2 inline-block px-2 py-1 border border-amber-500/15 bg-amber-500/15 text-amber-500\">🔥 New version dropped!</span>
      <h1 class=\"text-4xl lg:text-6xl font-bold font-sans\">
        <span class=\"text-2xl lg:text-4xl text-gray-400 block font-medium\">I'm ready to work,</span>
        Ask me anything.
      </h1>
    </div>
      <img src=\"https://enzostvs-deepsite.hf.space/arrow.svg\" class=\"absolute bottom-8 left-0 w-[100px] transform rotate-[30deg]\" alt=\"Decorative arrow pointing to the input area\" />
    <script></script>
  </body>
</html>
"""
