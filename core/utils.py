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
    """Checks if the provided HTML is the same as the default placeholder."""
    def normalize(html_str: str) -> str:
        if not html_str: return ""
        soup = BeautifulSoup(html_str, 'html.parser')
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        return ' '.join(soup.get_text(strip=True).split())
    
    return normalize(DEFAULT_HTML) == normalize(current_html)

def apply_diff_patch(original_html: str, ai_response: str) -> str:
    """Parses the AI's diff-patch response and applies it to the original HTML."""
    if not ai_response or SEARCH_START not in ai_response:
        return original_html
    modified_html = original_html
    pattern = re.compile(f"{re.escape(SEARCH_START)}(.*?){re.escape(DIVIDER)}(.*?){re.escape(REPLACE_END)}", re.DOTALL)
    matches = list(pattern.finditer(ai_response))
    if not matches:
        return original_html
    for match in reversed(matches):
        search_block, replace_block = match.group(1), match.group(2)
        search_block = search_block.strip('\n')
        replace_block = replace_block.strip('\n')
        if search_block in modified_html:
            modified_html = modified_html.replace(search_block, replace_block, 1)
    return modified_html

def isolate_and_clean_html(raw_text: str) -> str:
    """
    Finds the start of a FULL HTML document and removes any preceding text or markdown.
    """
    if not raw_text: 
        return ""
    
    # Handle markdown code blocks
    markdown_match = re.search(r'```(?:html)?\n(.*?)\n```', raw_text, re.DOTALL)
    if markdown_match:
        text_to_parse = markdown_match.group(1).strip()
    else:
        text_to_parse = raw_text

    doctype_match = re.search(r'<!DOCTYPE html>', text_to_parse, re.IGNORECASE)
    if doctype_match:
        return text_to_parse[doctype_match.start():]
    
    html_match = re.search(r'<html', text_to_parse, re.IGNORECASE)
    if html_match:
        return text_to_parse[html_match.start():]
        
    return text_to_parse # Fallback to returning whatever is left

def extract_assets(html_content: str, container_id: str) -> tuple:
    """Extracts CSS, JS, and body content from a full HTML document."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join([style.string for style in soup.find_all('style') if style.string])
        js = "\n".join([script.string for script in soup.find_all('script') if script.string and not script.get('src')])
        body_tag = soup.find('body')
        if body_tag:
            for comment in body_tag.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()
            for tag in body_tag.find_all(['style', 'script']):
                tag.decompose()
            body_html = ''.join(str(c) for c in body_tag.contents)
        else:
            # Fallback if no body tag, clean the whole document
            for tag in soup.find_all(['head', 'style', 'script']):
                tag.decompose()
            body_html = str(soup)

        return body_html.strip(), css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""
