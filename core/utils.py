# core/utils.py
import re
from bs4 import BeautifulSoup, Comment # Make sure Comment is imported
from core.prompts import DEFAULT_HTML, SEARCH_START, DIVIDER, REPLACE_END

# ... ip_limiter and is_the_same_html functions are unchanged ...

def ip_limiter(ip: str | None, max_requests: int) -> bool:
    # ...
    return True

def is_the_same_html(current_html: str) -> bool:
    # ...
    return True

def apply_diff_patch(original_html: str, ai_response: str) -> str:
    # ...
    return original_html
    
# NEW FUNCTION to strip AI chatter
def isolate_and_clean_html(raw_text: str) -> str:
    """Finds the start of the HTML document and removes any preceding text."""
    if not raw_text:
        return ""
    # Find the start of the doctype, case-insensitive
    match = re.search(r'<!DOCTYPE html>', raw_text, re.IGNORECASE)
    if match:
        # Return everything from the start of the doctype
        return raw_text[match.start():]
    # Fallback if no doctype is found, try to find <html>
    match = re.search(r'<html', raw_text, re.IGNORECASE)
    if match:
        return raw_text[match.start():]
    # If no HTML found, it's likely an error message or all chatter
    return ""
