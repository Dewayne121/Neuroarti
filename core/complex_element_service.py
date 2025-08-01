# core/complex_element_service.py
from core.ai_services import generate_code
from core.prompts import SYSTEM_PROMPT_REWRITE_ELEMENT
from core.utils import extract_first_html_element

async def rewrite_complex_element(prompt: str, selected_element_html: str, model: str) -> str:
    """
    Uses a robust AI prompt to reliably rewrite complex HTML components (e.g., sections, divs).
    """
    print("Using COMPLEX element rewrite service.")
    
    user_prompt_for_ai = (
        f"**Original HTML Element:**\n```html\n{selected_element_html}\n```\n\n"
        f"**User's Instruction to change it:**\n'{prompt}'\n\n"
        "Rewrite the complex HTML element above to ONLY fulfill the user's instruction."
    )

    ai_response_text = await generate_code(
        SYSTEM_PROMPT_REWRITE_ELEMENT,
        user_prompt_for_ai,
        model
    )
    
    rewritten_element_html = extract_first_html_element(ai_response_text)
    
    if not rewritten_element_html.strip():
        raise Exception("AI returned an empty or invalid element for complex rewrite.")
        
    return rewritten_element_html
