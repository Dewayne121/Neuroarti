# core/singular_element_service.py
from core.ai_services import generate_code
from core.prompts import SYSTEM_PROMPT_REWRITE_SINGULAR_ELEMENT
from core.utils import extract_first_html_element

async def rewrite_singular_element(prompt: str, selected_element_html: str, model: str) -> str:
    """
    Uses a hyper-focused AI prompt to reliably rewrite simple, single HTML tags.
    """
    print("Using SINGULAR element rewrite service.")

    user_prompt_for_ai = (
        f"**Original HTML Tag:**\n```html\n{selected_element_html}\n```\n\n"
        f"**User's Instruction:**\n'{prompt}'\n\n"
        "Rewrite the HTML tag above to fulfill the user's instruction."
    )

    ai_response_text = await generate_code(
        SYSTEM_PROMPT_REWRITE_SINGULAR_ELEMENT,
        user_prompt_for_ai,
        model
    )
    
    rewritten_element_html = extract_first_html_element(ai_response_text)
    
    if not rewritten_element_html.strip():
        raise Exception("AI returned an empty or invalid element for singular rewrite.")
        
    return rewritten_element_html
