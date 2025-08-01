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

def sanitize_rewritten_element(html_string: str) -> str:
    """
    Acts as a safety net to strip any <style> or <script> tags an AI might
    add to a rewritten element against its instructions.
    """
    if not html_string:
        return ""
    try:
        soup = BeautifulSoup(html_string, 'html.parser')
        # Find and remove all <style> and <script> tags
        for tag in soup.find_all(['style', 'script']):
            tag.decompose()
        return str(soup)
    except Exception as e:
        print(f"Error during element sanitization: {e}")
        return html_string # Return original on failure

def is_singular_element(html_string: str) -> bool:
    """
    Detects if an HTML string represents a single element with no nested tags.
    """
    try:
        soup = BeautifulSoup(f"<div>{html_string}</div>", 'html.parser')
        first_tag = soup.div.find(lambda tag: isinstance(tag, Tag))
        if first_tag:
            return not bool(first_tag.find(lambda tag: isinstance(tag, Tag)))
        return False
    except Exception:
        return False

def is_the_same_html(current_html: str) -> bool:
    def normalize(html_str: str) -> str:
        if not html_str: return ""
        soup = BeautifulSoup(html_str, 'html.parser')
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        return ' '.join(soup.get_text(strip=True).split())
    
    return normalize(DEFAULT_HTML) == normalize(current_html)

def apply_diff_patch(original_html: str, ai_response: str) -> str:
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
    if not raw_text: 
        return ""
    match = re.search(r'<!DOCTYPE html>', raw_text, re.IGNORECASE)
    if match: 
        return raw_text[match.start():]
    match = re.search(r'<html', raw_text, re.IGNORECASE)
    if match: 
        return raw_text[match.start():]
    return raw_text

def extract_first_html_element(raw_text: str) -> str:
    if not raw_text:
        return ""
    text_to_parse = raw_text.strip()
    markdown_match = re.search(r'```(?:html)?\n(.*)\n```', text_to_parse, re.DOTALL)
    if markdown_match:
        text_to_parse = markdown_match.group(1).strip()
    else:
        first_tag_match = re.search(r'<', text_to_parse)
        if first_tag_match:
            text_to_parse = text_to_parse[first_tag_match.start():]
        else:
            return ""
    try:
        soup = BeautifulSoup(text_to_parse, 'html.parser')
        first_element = soup.find(lambda tag: isinstance(tag, Tag))
        if first_element:
            return str(first_element)
        return ""
    except Exception as e:
        print(f"Error during BeautifulSoup parsing in extract_first_html_element: {e}")
        return ""

def extract_assets(html_content: str, container_id: str) -> tuple:
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
            body_html = html_content
        return body_html.strip(), css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""
