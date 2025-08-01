# core/utils.py
import re
from bs4 import BeautifulSoup, Comment
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
        print("Warning: Invalid AI response format - no SEARCH blocks found")
        return original_html
        
    modified_html = original_html
    pattern = re.compile(f"{re.escape(SEARCH_START)}(.*?){re.escape(DIVIDER)}(.*?){re.escape(REPLACE_END)}", re.DOTALL)
    matches = list(pattern.finditer(ai_response))
    
    if not matches:
        print("Warning: No valid SEARCH/REPLACE blocks found in AI response")
        return original_html
    
    print(f"Found {len(matches)} SEARCH/REPLACE blocks to process")
    
    # Process matches in reverse order to avoid position shifts
    for i, match in enumerate(reversed(matches)):
        search_block, replace_block = match.group(1), match.group(2)
        
        # Clean up the blocks
        search_block = search_block.strip('\n')
        replace_block = replace_block.strip('\n')
        
        print(f"Processing block {len(matches)-i}: Search for '{search_block[:50]}...'")
        
        if search_block.strip() == "":
            # Insert at the beginning
            modified_html = replace_block + "\n" + modified_html
            print("  -> Inserted at beginning")
        else:
            if search_block in modified_html:
                # Apply the replacement
                old_html = modified_html
                modified_html = modified_html.replace(search_block, replace_block, 1)
                if modified_html != old_html:
                    print("  -> Successfully applied replacement")
                else:
                    print("  -> Replacement had no effect")
            else:
                print(f"  -> Warning: Search block not found in HTML")
                # Try a more flexible search (ignoring some whitespace differences)
                search_normalized = ' '.join(search_block.split())
                html_normalized = ' '.join(modified_html.split())
                if search_normalized in html_normalized:
                    print("  -> Attempting flexible whitespace matching")
                    # This is a more complex case - for now, skip it
                    pass
                else:
                    print(f"  -> Skipping this block entirely")
    
    return modified_html

def isolate_and_clean_html(raw_text: str) -> str:
    """Finds the start of the HTML document and removes any preceding text (AI chatter)."""
    if not raw_text: 
        return ""
        
    # Look for DOCTYPE declaration first
    match = re.search(r'<!DOCTYPE html>', raw_text, re.IGNORECASE)
    if match: 
        return raw_text[match.start():]
        
    # Fall back to html tag
    match = re.search(r'<html', raw_text, re.IGNORECASE)
    if match: 
        return raw_text[match.start():]
        
    # Last resort - look for any opening tag that might start the content
    match = re.search(r'<(?:div|section|header|main|body)', raw_text, re.IGNORECASE)
    if match:
        return raw_text[match.start():]
        
    return ""

def extract_assets(html_content: str, container_id: str) -> tuple:
    """Extracts CSS, JS, and body content from a full HTML document, REMOVING COMMENTS."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract CSS
        css_parts = []
        for style in soup.find_all('style'):
            if style.string:
                css_parts.append(style.string)
        css = "\n".join(css_parts)
        
        # Extract JS (only inline scripts, not external ones)
        js_parts = []
        for script in soup.find_all('script'):
            # Only include scripts with content and no src attribute
            if script.string and not script.get('src'):
                js_parts.append(script.string)
        js = "\n".join(js_parts)
        
        # Extract body content
        body_tag = soup.find('body')
        if body_tag:
            # Remove all comments from the body
            for comment in body_tag.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()
            
            # Remove style and script tags from body (they're extracted separately)
            for tag in body_tag.find_all(['style', 'script']):
                tag.decompose()
            
            body_html = ''.join(str(c) for c in body_tag.contents)
        else:
            # Fallback if no body tag found
            body_html = html_content
        
        return body_html.strip(), css.strip(), js.strip()
        
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""
