# core/rewrite_service.py
from core.ai_services import generate_code
from core.prompts import SYSTEM_PROMPT_REWRITE_ELEMENT, SYSTEM_PROMPT_REWRITE_SINGULAR_ELEMENT
from core.utils import extract_first_html_element, is_singular_element

async def rewrite_html_element(prompt: str, selected_element_html: str, model: str) -> str:
    """
    Analyzes the selected element and uses the best AI prompt to rewrite it.
    """
    
    # Detect if the element is singular (like <h1>) or complex (like <section>).
    is_simple = is_singular_element(selected_element_html)
    
    # Choose the best prompt based on the element's complexity.
    system_prompt = SYSTEM_PROMPT_REWRITE_SINGULAR_ELEMENT if is_simple else SYSTEM_PROMPT_REWRITE_ELEMENT
    
    print(f"Element detected as {'SINGULAR' if is_simple else 'COMPLEX'}. Using appropriate prompt.")

    # Construct the user prompt for the AI.
    user_prompt_for_ai = (
        f"**Original HTML Element:**\n```html\n{selected_element_html}\n```\n\n"
        f"**User's Instruction to change it:**\n'{prompt}'\n\n"
        "Rewrite the HTML element above to ONLY fulfill the user's instruction. "
        "Your response MUST BE the new HTML element's code and nothing else."
    )

    # Generate the rewritten code.
    ai_response_text = await generate_code(
        system_prompt,
        user_prompt_for_ai,
        model
    )
    
    # Clean and extract the final HTML.
    rewritten_element_html = extract_first_html_element(ai_response_text)
    
    if not rewritten_element_html.strip():
        raise Exception("AI returned an empty or invalid element after cleaning.")
        
    return rewritten_element_html
