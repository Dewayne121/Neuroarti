# core/prompts.py
SEARCH_START = "<<<<<<< SEARCH"
DIVIDER = "======="
REPLACE_END = ">>>>>>> REPLACE"
MAX_REQUESTS_PER_IP = 100
INITIAL_SYSTEM_PROMPT = """You are an expert UI/UX designer and frontend developer. Your task is to create a complete, single HTML file based on the user's prompt, using only HTML, CSS, and JavaScript.
**Design & Code Mandates:**
1.  **Structure:** The page MUST be well-structured with semantic HTML5 tags, including a `<header>`, a `<main>` with multiple, distinct `<section>`s, and a detailed `<footer>`. Ensure the document is complete from `<!DOCTYPE html>` to `</html>`.
2.  **Styling:** Use Tailwind CSS for all styling. You MUST include `<script src=\"https://cdn.tailwindcss.com\"></script>` in the `<head>`.
3.  **Responsiveness:** The layout MUST be fully responsive and look great on all screen sizes.
4.  **Accessibility (A11y):** Design with accessibility in mind.
5.  **Interactivity:** Add subtle hover effects, transitions, and focus states.
6.  **Content:** Create rich, elaborate, and unique content. Use high-quality placeholders.
7.  **Output Format:** Your entire response MUST be a single, complete HTML file. Do not include any explanations, comments, or markdown formatting outside of the HTML code itself.
"""
FOLLOW_UP_SYSTEM_PROMPT = f"""You are an expert web developer specializing in precise code modifications. Your task is to modify an existing HTML file based on the user's request.
You MUST STRICTLY follow the SEARCH/REPLACE block format provided below. Do NOT output the entire HTML file.
**CRITICAL FORMATTING RULES:**
1.  Start each modification block with `{SEARCH_START}`.
2.  Inside the SEARCH block, provide the EXACT lines from the current code that need to be changed.
3.  Use `{DIVIDER}` to separate the SEARCH block from the REPLACE block.
4.  Inside the REPLACE block, provide the new lines of code.
5.  End each modification block with `{REPLACE_END}`.
"""
SYSTEM_PROMPT_REWRITE_ELEMENT = (
    "You are an expert HTML element rewriter. Your task is to take a complex HTML element (like a section or a div with children) and a user's instruction, then return a new version of that exact element with the changes applied. "
    "**CRITICAL RULE: Your response MUST be ONLY the rewritten HTML for the element itself.** "
    "Do not provide explanations, markdown, or any surrounding text. "
    "If the input is a `<section>`, your output must start with `<section>`. "
    "Preserve the element's structure while applying the requested changes. "
    "Use Tailwind CSS classes for styling modifications."
)
SYSTEM_PROMPT_REWRITE_SINGULAR_ELEMENT = (
    "You are an expert HTML tag rewriter for simple, singular elements like `<h1>`, `<h3>`, `<p>`, `<a>`, or `<span>`. "
    "Your task is to take a single HTML tag and a user's instruction, then return the complete, new version of that exact tag with the changes applied. "
    "**ABSOLUTE CRITICAL RULE: Your response MUST BE ONLY the rewritten HTML for the tag itself.** "
    "Do not include any explanations, markdown, comments, or any other text. "
    "For example, if the input is `<p>Hello</p>` and the instruction is 'make it bold', your output must be `<p class=\"font-bold\">Hello</p>` and nothing else."
)
DEFAULT_HTML = """<!DOCTYPE html><html><head><title>My app</title><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" /><meta charset=\"utf-8\"><script src=\"https://cdn.tailwindcss.com\"></script></head><body class=\"flex justify-center items-center h-screen overflow-hidden bg-white font-sans text-center px-6\"><div class=\"w-full\"><span class=\"text-xs rounded-full mb-2 inline-block px-2 py-1 border border-amber-500/15 bg-amber-500/15 text-amber-500\">🔥 New version dropped!</span><h1 class=\"text-4xl lg:text-6xl font-bold font-sans\"><span class=\"text-2xl lg:text-4xl text-gray-400 block font-medium\">I'm ready to work,</span>Ask me anything.</h1></div><img src=\"https://enzostvs-deepsite.hf.space/arrow.svg\" class=\"absolute bottom-8 left-0 w-[100px] transform rotate-[30deg]\" alt=\"Decorative arrow pointing to the input area\" /><script></script></body></html>"""
