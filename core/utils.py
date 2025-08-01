# core/utils.py
import re
from bs4 import BeautifulSoup
from core.prompts import DEFAULT_HTML, SEARCH_START, DIVIDER, REPLACE_END

# In-memory store for IP-based rate limiting
ip_address_map = {}

def ip_limiter(ip: str | None, max_requests: int) -> bool:
    """Simple in-memory IP rate limiter."""
    if not ip:
        return True # Allow if IP is not available
    
    count = ip_address_map.get(ip, 0) + 1
    ip_address_map[ip] = count
    return count <= max_requests

def is_the_same_html(current_html: str) -> bool:
    """Checks if the provided HTML is the same as the default placeholder, ignoring whitespace."""
    def normalize(html: str) -> str:
        soup = BeautifulSoup(html, 'html.parser')
        # Remove comments and collapse whitespace
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        return ' '.join(soup.get_text().split())

    return normalize(DEFAULT_HTML) == normalize(current_html)


def apply_diff_patch(original_html: str, ai_response: str) -> str:
    """Parses the AI's diff-patch response and applies it to the original HTML."""
    modified_html = original_html
    
    # Use regex to find all SEARCH/REPLACE blocks
    pattern = re.compile(f"{re.escape(SEARCH_START)}(.*?){re.escape(DIVIDER)}(.*?){re.escape(REPLACE_END)}", re.DOTALL)
    
    for match in pattern.finditer(ai_response):
        search_block = match.group(1)
        replace_block = match.group(2)

        # Handle edge case of newline characters from prompt formatting
        if search_block.startswith('\n'): search_block = search_block[1:]
        if search_block.endswith('\n'): search_block = search_block[:-1]
        if replace_block.startswith('\n'): replace_block = replace_block[1:]
        if replace_block.endswith('\n'): replace_block = replace_block[:-1]

        if search_block.strip() == "": # This is an insertion at the beginning
            modified_html = replace_block + "\n" + modified_html
        else:
             # Use a count of 1 to ensure we only replace the first exact match
            if search_block in modified_html:
                modified_html = modified_html.replace(search_block, replace_block, 1)
            else:
                print(f"Warning: Search block not found in HTML. Skipping patch.")
                print(f"--- SEARCH BLOCK ---\n{search_block}\n--------------------")

    return modified_html