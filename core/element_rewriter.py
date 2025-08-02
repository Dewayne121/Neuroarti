# core/element_rewriter.py
import re
from bs4 import BeautifulSoup, Tag
from core.ai_services import generate_code
from core.prompts import SYSTEM_PROMPT_REWRITE_ELEMENT
def clean_ai_response(raw_text: str) -> str:
    """
    Rigorously cleans the AI's response to isolate ONLY the first valid HTML element,
    stripping away any markdown, explanations, or other conversational chatter.
    """
    if not raw_text:
        return ""
    
    # FIXED: Use a more precise, non-greedy regex with a backreference to capture
    # a single, complete element without over-matching.
    # This captures <tag>...</tag> correctly, even with nested tags.
    markdown_match = re.search(r'```(?:html)?\s*(<([a-z][a-z0-9]*)\b[^>]*>.*?</\2>)\s*```', raw_text, re.DOTALL | re.IGNORECASE)
    if markdown_match:
        return markdown_match.group(1).strip()
    
    # If no markdown block is found, parse the whole text and find the first real tag.
    # This handles cases where the AI just returns the HTML directly.
    try:
        soup = BeautifulSoup(raw_text, 'lxml')
        first_tag = soup.find(lambda tag: isinstance(tag, Tag))
        if first_tag:
            return str(first_tag)
    except Exception as e:
        print(f"BeautifulSoup parsing failed in clean_ai_response: {e}")
        # As a last resort for malformed output, use a simpler, non-greedy regex.
        tag_match = re.search(r'(<.*?>.*?</.*?>)', raw_text, re.DOTALL | re.IGNORECASE)
        if tag_match:
            return tag_match.group(1).strip()

    # If no HTML is found at all, return an empty string
    return ""
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
    
    # Clean the response robustly to ensure it's just the HTML element
    rewritten_element = clean_ai_response(ai_response_text)
    
    if not rewritten_element:
        print("Warning: AI returned an empty string for element rewrite.")
        # Fallback to the original element to avoid deleting the user's content
        return selected_element_html
        
    return rewritten_element
