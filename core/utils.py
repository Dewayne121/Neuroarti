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
    """Checks if the provided HTML is the same as the default placeholder, ignoring whitespace and comments."""
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
    
    for i, match in enumerate(reversed(matches)):
        search_block, replace_block = match.group(1), match.group(2)
        search_block = search_block.strip('\n')
        replace_block = replace_block.strip('\n')
        
        if search_block.strip() == "":
            modified_html = replace_block + "\n" + modified_html
        else:
            if search_block in modified_html:
                modified_html = modified_html.replace(search_block, replace_block, 1)
            else:
                print(f"  -> Warning: Search block not found in HTML for block {len(matches)-i}")
    
    return modified_html

def isolate_and_clean_html(raw_text: str) -> str:
    """Finds the start of a FULL HTML document and removes any preceding text."""
    if not raw_text: 
        return ""
    match = re.search(r'<!DOCTYPE html>', raw_text, re.IGNORECASE)
    if match: 
        return raw_text[match.start():]
    match = re.search(r'<html', raw_text, re.IGNORECASE)
    if match: 
        return raw_text[match.start():]
    match = re.search(r'<(?:div|section|header|main|body)', raw_text, re.IGNORECASE)
    if match:
        return raw_text[match.start():]
    return ""

def extract_first_html_element(raw_text: str) -> str:
    """
    Extracts the first complete HTML element from an AI response.
    Improved to handle cases where AI returns extra text or explanations.
    """
    if not raw_text:
        return ""
    
    text_to_parse = raw_text.strip()
    
    # Step 1: Look for markdown code blocks first
    markdown_match = re.search(r'```(?:html)?\n(.*?)\n```', text_to_parse, re.DOTALL)
    if markdown_match:
        text_to_parse = markdown_match.group(1).strip()
    
    # Step 2: Find the first HTML tag
    first_tag_match = re.search(r'<([a-z][a-z0-9]*)', text_to_parse, re.IGNORECASE)
    if not first_tag_match:
        return ""
    
    tag_name = first_tag_match.group(1).lower()
    start_pos = first_tag_match.start()
    
    # Step 3: Extract the complete element
    try:
        # Use BeautifulSoup to parse the HTML
        soup = BeautifulSoup(text_to_parse[start_pos:], 'html.parser')
        
        # Find the first tag that matches our tag name
        first_element = None
        for tag in soup.find_all(lambda tag: isinstance(tag, Tag)):
            if tag.name.lower() == tag_name:
                first_element = tag
                break
        
        if first_element:
            # Return the complete HTML element
            return str(first_element)
    except Exception as e:
        print(f"Error during BeautifulSoup parsing in extract_first_html_element: {e}")
    
    # Fallback: Try to extract using regex
    try:
        # For self-closing tags
        if tag_name in ['img', 'br', 'hr', 'input', 'link', 'meta']:
            pattern = re.compile(rf'<{tag_name}[^>]*?(?:\/>|>)', re.IGNORECASE)
            match = pattern.search(text_to_parse[start_pos:])
            if match:
                return match.group(0)
        
        # For regular tags with content
        pattern = re.compile(rf'<{tag_name}[^>]*>.*?</{tag_name}>', re.DOTALL | re.IGNORECASE)
        match = pattern.search(text_to_parse[start_pos:])
        if match:
            return match.group(0)
    except Exception as e:
        print(f"Error during regex extraction in extract_first_html_element: {e}")
    
    return ""

def extract_assets(html_content: str, container_id: str) -> tuple:
    """Extracts CSS, JS, and body content from a full HTML document, REMOVING COMMENTS."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        css_parts = []
        for style in soup.find_all('style'):
            if style.string:
                css_parts.append(style.string)
        css = "\n".join(css_parts)
        
        js_parts = []
        for script in soup.find_all('script'):
            if script.string and not script.get('src'):
                js_parts.append(script.string)
        js = "\n".join(js_parts)
        
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
