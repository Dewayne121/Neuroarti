# core/utils.py
import re
from bs4 import BeautifulSoup, Comment, Tag
from core.prompts import DEFAULT_HTML, SEARCH_START, DIVIDER, REPLACE_END

# In-memory store for IP-based rate limiting
ip_address_map = {}

def ip_limiter(ip: str | None, max_requests: int) -> bool:
    """Simple in-memory IP rate limiter."""
    if not ip: return True
    count = ip_address_map.get(ip, 0) + 1
    ip_address_map[ip] = count
    return count <= max_requests

def is_the_same_html(current_html: str) -> bool:
    """Normalizes and compares HTML content to the default template."""
    def normalize(html_str: str) -> str:
        if not html_str: return ""
        # A more robust normalization by removing comments and collapsing whitespace
        soup = BeautifulSoup(html_str, 'html.parser')
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        return ' '.join(soup.get_text(strip=True).split())
    
    return normalize(DEFAULT_HTML) == normalize(current_html)

def apply_diff_patch(original_html: str, patch_instructions: str) -> str:
    """
    Applies a series of search-and-replace patches to an HTML string.
    """
    if not patch_instructions or SEARCH_START not in patch_instructions:
        # If the AI fails to provide a patch, return the original to avoid breaking the page.
        print("Warning: No valid patch instructions found in AI response. Returning original HTML.")
        return original_html

    modified_html = original_html
    # Use a robust regex to find all patch blocks
    pattern = re.compile(f"{re.escape(SEARCH_START)}(.*?){re.escape(DIVIDER)}(.*?){re.escape(REPLACE_END)}", re.DOTALL)
    
    matches = list(pattern.finditer(patch_instructions))
    if not matches:
        return original_html

    # Iterate backwards to avoid messing up character indices of subsequent matches
    for match in reversed(matches):
        search_block = match.group(1).strip('\r\n')
        replace_block = match.group(2).strip('\r\n')

        # Use a counter to replace only the last occurrence if needed, but 1 is usually safer.
        if search_block in modified_html:
            # A simple replace should be sufficient if the SEARCH block is unique enough
            modified_html = modified_html.replace(search_block, replace_block, 1)
        else:
            # This can happen if the AI hallucinates code that doesn't exist. We just skip it.
            print(f"Warning: Search block not found in HTML. Skipping patch.\nBlock: {search_block}")

    return modified_html
