# core/utils.py
import re
from bs4 import BeautifulSoup, Comment
from core.prompts import DEFAULT_HTML, SEARCH_START, DIVIDER, REPLACE_END

# REMOVED: ip_address_map dictionary and ip_limiter function

def is_the_same_html(current_html: str) -> bool:
    """Normalizes and compares HTML content to the default template."""
    def normalize(html_str: str) -> str:
        if not html_str: return ""
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
        print("Warning: No valid patch instructions found in AI response. Returning original HTML.")
        return original_html
        
    modified_html = original_html
    pattern = re.compile(f"{re.escape(SEARCH_START)}(.*?){re.escape(DIVIDER)}(.*?){re.escape(REPLACE_END)}", re.DOTALL)
    
    matches = list(pattern.finditer(patch_instructions))
    if not matches:
        return original_html
        
    for match in reversed(matches):
        search_block = match.group(1).strip('\r\n')
        replace_block = match.group(2).strip('\r\n')
        
        if search_block in modified_html:
            modified_html = modified_html.replace(search_block, replace_block, 1)
        else:
            print(f"Warning: Search block not found in HTML. Skipping patch.\nBlock: {search_block}")
            
    return modified_html
