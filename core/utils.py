# core/utils.py
import re
from bs4 import BeautifulSoup, Comment
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
    """Checks if the provided HTML is the same as the default placeholder, ignoring whitespace and comments."""
    def normalize(html_str: str) -> str:
        if not html_str: return ""
        soup = BeautifulSoup(html_str, 'html.parser')
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        # Collapse whitespace
        return ' '.join(soup.get_text(strip=True).split())

    return normalize(DEFAULT_HTML) == normalize(current_html)

def apply_diff_patch(original_html: str, ai_response: str) -> str:
    """Parses the AI's diff-patch response and applies it to the original HTML."""
    modified_html = original_html
    
    pattern = re.compile(f"{re.escape(SEARCH_START)}(.*?){re.escape(DIVIDER)}(.*?){re.escape(REPLACE_END)}", re.DOTALL)
    
    for match in pattern.finditer(ai_response):
        search_block, replace_block = match.group(1), match.group(2)

        if search_block.startswith('\n'): search_block = search_block[1:]
        if search_block.endswith('\n'): search_block = search_block[:-1]
        if replace_block.startswith('\n'): replace_block = replace_block[1:]
        if replace_block.endswith('\n'): replace_block = replace_block[:-1]

        if search_block.strip() == "":
            modified_html = replace_block + "\n" + modified_html
        else:
            if search_block in modified_html:
                modified_html = modified_html.replace(search_block, replace_block, 1)
            else:
                print(f"Warning: Search block not found in HTML. Skipping patch.")
                print(f"--- SEARCH BLOCK ---\n{search_block}\n--------------------")

    return modified_html
    
def isolate_and_clean_html(raw_text: str) -> str:
    """Finds the start of the HTML document and removes any preceding text (AI chatter)."""
    if not raw_text:
        return ""
    match = re.search(r'<!DOCTYPE html>', raw_text, re.IGNORECASE)
    if match:
        return raw_text[match.start():]
    match = re.search(r'<html', raw_text, re.IGNORECASE)
    if match:
        return raw_text[match.start():]
    return ""

def extract_assets(html_content: str, container_id: str) -> tuple:
    """Extracts CSS, JS, and body content from a full HTML document."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string and not script.get('src'))
        body_tag = soup.find('body')
        if body_tag:
            for tag in body_tag.find_all(['style', 'script']):
                tag.decompose()
            body_html = ''.join(str(c) for c in body_tag.contents)
        else:
            body_html = html_content # Fallback
        return body_html, css, js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""
