# core/element_rewriter.py
import re
from core.ai_services import generate_code
from core.prompts import SYSTEM_PROMPT_REWRITE_ELEMENT

def clean_ai_response(raw_text: str) -> str:
    """
    Cleans the AI response to isolate just the HTML element,
    stripping markdown code blocks if they exist.
    """
    if not raw_text:
        return ""
    
    # Check for markdown code block and extract content if present
    match = re.search(r'```(?:html)?\s*(.*?)\s*```', raw_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # If no markdown, return the raw text stripped of whitespace
    return raw_text.strip()


async def rewrite_element(prompt: str, selected_element_html: str, model: str) -> str:
    """
    Uses a hyper-focused AI prompt to reliably rewrite a single HTML element.
    """
    user_prompt_for_ai = (
        f"**Original HTML Element:**\n```html\n{selected_element_html}\n```\n\n"
        f"**User's Instruction for change:**\n'{prompt}'"
    )

    ai_response_text = await generate_code(
        SYSTEM_PROMPT_REWRITE_ELEMENT,
        user_prompt_for_ai,
        model
    )
    
    # Clean the response to ensure it's just the HTML element
    rewritten_element = clean_ai_response(ai_response_text)
    
    if not rewritten_element:
        print("Warning: AI returned an empty string for element rewrite.")
        # Fallback to the original element to avoid deleting content
        return selected_element_html
        
    return rewritten_element
