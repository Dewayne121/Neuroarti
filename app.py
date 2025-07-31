import gradio as gr
import os
from openai import OpenAI
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import re
import json
from typing import Dict, Any
from bs4 import BeautifulSoup

# --- Pydantic Models ---
class BuildRequest(BaseModel):
    prompt: str
    model: str = "glm-4.5-air"

class EditSnippetRequest(BaseModel):
    snippet: str
    prompt: str
    model: str = "glm-4.5-air"

class PatchRequest(BaseModel):
    html: str
    selector: str
    new_snippet: str

# --- Configuration ---
API_KEY = os.environ.get("GLM_API_KEY")
if not API_KEY:
    raise ValueError("API Key not found. Please set the GLM_API_KEY environment variable.")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.together.xyz/v1",
)

MODEL_MAPPING = {
    "glm-4.5-air": "zai-org/GLM-4.5-Air-FP8",
    "deepseek-r1": "deepseek-ai/deepseek-coder-33b-instruct" 
}

# --- Enhanced Helper Functions ---
def clean_html_response(raw_response: str, is_snippet=False) -> str:
    """Enhanced HTML cleaning with multiple fallback strategies"""
    if not raw_response:
        return ""
    
    cleaned = raw_response.strip()
    
    if is_snippet:
        return clean_html_snippet(cleaned)
    else:
        return clean_full_html_document(cleaned)

def clean_html_snippet(text: str) -> str:
    """Aggressively clean HTML snippets to remove AI chatter"""
    # Strategy 1: Extract from markdown code blocks (most common)
    code_patterns = [
        r'```html\s*\n(.*?)```',
        r'```\s*\n(.*?)```',
        r'`([^`]*)`',
    ]
    
    for pattern in code_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            extracted = match.group(1).strip()
            if extracted and '<' in extracted:
                return clean_section_comments(extracted)
    
    # Strategy 2: Remove section comments first
    text = clean_section_comments(text)
    
    # Strategy 3: Find HTML-like content between tags
    # Look for content that starts with < and ends with >
    html_block_match = re.search(r'(<[^>]*>.*</[^>]*>)', text, re.DOTALL)
    if html_block_match:
        return html_block_match.group(1).strip()
    
    # Strategy 4: Extract everything between first < and last >
    first_tag = text.find('<')
    last_tag = text.rfind('>')
    
    if first_tag != -1 and last_tag != -1 and last_tag > first_tag:
        potential_html = text[first_tag:last_tag + 1].strip()
        # Validate it looks like HTML and fix truncated tags
        if re.search(r'<\w+[^>]*>', potential_html):
            # Fix common truncation issues
            potential_html = fix_truncated_html(potential_html)
            return potential_html
    
    # Strategy 5: Remove common AI response patterns
    # Remove lines that look like explanations
    lines = text.split('\n')
    html_lines = []
    
    for line in lines:
        line = line.strip()
        # Skip empty lines and common AI chatter patterns
        if not line:
            continue
        # Skip section comments
        if re.match(r'^\s*[A-Za-z\s]+Section\s*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. No section comments like ' Header ' or ' Hero Section '\n"
        "5. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "6. Place CSS in <style> tags in <head>\n"
        "7. Place JavaScript in <script> tags before </body>\n"
        "8. Your entire response must be parseable as HTML\n"
        "9. Do not truncate the HTML - provide complete, valid markup\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO section comments like ' Header ' or ' Navigation '\n"
        "5. NO 'Here is...' or 'I've modified...' responses\n"
        "6. If you cannot modify it, return the original snippet unchanged\n"
        "7. Your response must start with < and end with >\n"
        "8. Do not truncate HTML - provide complete valid markup\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port), line) or re.match(r'^\s*[A-Za-z\s]+\s*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port), line):
            continue
        if any(phrase in line.lower() for phrase in [
            'here is', 'here\'s', 'i\'ve created', 'i\'ve modified',
            'this code', 'the code', 'as requested', 'hope this helps',
            'let me know', 'feel free', 'you can', 'this will',
            'explanation:', 'note:', 'important:'
        ]):
            continue
        # If line contains HTML tags, keep it
        if '<' in line and '>' in line:
            html_lines.append(line)
    
    if html_lines:
        result = '\n'.join(html_lines)
        return fix_truncated_html(result)
    
    # Strategy 6: Last resort - if nothing else works, return empty
    # This prevents broken HTML from being injected
    return ""

def clean_section_comments(text: str) -> str:
    """Remove section comments like ' Header ', ' Hero Section ', etc."""
    # Remove lines that are just section labels
    section_patterns = [
        r'^\s*[A-Za-z\s]+Section\s*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port),  # " Hero Section "
        r'^\s*Header\s*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port),              # " Header "
        r'^\s*Footer\s*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port),              # " Footer "
        r'^\s*Navigation\s*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port),          # " Navigation "
        r'^\s*Gallery\s*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port),             # " Gallery "
        r'^\s*[A-Z][a-z\s]*\s*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port),      # Generic single word/phrase lines
    ]
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        is_section_comment = False
        for pattern in section_patterns:
            if re.match(pattern, line):
                is_section_comment = True
                break
        
        if not is_section_comment:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def fix_truncated_html(html: str) -> str:
    """Fix common HTML truncation issues"""
    # Fix truncated tags like "&lt;div class="
    html = html.replace('&lt;', '<').replace('&gt;', '>')
    
    # If HTML ends with an incomplete tag, try to close it
    if html.endswith('<div class="') or html.endswith('<div '):
        # Remove the incomplete opening tag
        html = re.sub(r'<div[^>]*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port), '', html)
    
    # Remove any trailing incomplete tags
    html = re.sub(r'<[^>]*

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port), '', html)
    
    return html.strip()

def clean_full_html_document(text: str) -> str:
    """Clean full HTML documents"""
    # Remove markdown code blocks first
    text = re.sub(r'```html\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    
    # Look for DOCTYPE declaration
    doctype_match = re.search(r'<!DOCTYPE html.*?>', text, re.IGNORECASE | re.DOTALL)
    if doctype_match:
        return text[doctype_match.start():].strip()
    
    # Look for <html> tag
    html_match = re.search(r'<html[^>]*>', text, re.IGNORECASE)
    if html_match:
        return text[html_match.start():].strip()
    
    # Remove common AI response prefixes
    prefixes_to_remove = [
        r'^.*?(?=<!DOCTYPE)',
        r'^.*?(?=<html)',
        r'^Here.*?:\s*',
        r'^I\'ve created.*?:\s*',
        r'^.*?requested.*?:\s*',
    ]
    
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    return text.strip()

def extract_assets(html_content: str) -> tuple:
    """Extract CSS, JS, and body content from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        css = "\n".join(style.string or '' for style in soup.find_all('style'))
        js = "\n".join(script.string or '' for script in soup.find_all('script') if script.string)
        
        body_tag = soup.find('body')
        body_content = ''.join(str(c) for c in body_tag.contents) if body_tag else str(soup)

        return body_content, css.strip(), js.strip()
    except Exception as e:
        print(f"Error extracting assets: {e}")
        return html_content, "", ""

# --- Enhanced AI Core Functions ---
def generate_code(system_prompt: str, user_prompt: str, model_id: str, is_snippet=False):
    """Generate code with enhanced error handling and cleaning"""
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.05,  # Even lower temperature for consistency
            max_tokens=4096,
            # Add stop sequences to prevent common chatter
            stop=["```", "Hope this helps", "Let me know", "Feel free"]
        )
        raw_html = response.choices[0].message.content
        cleaned_html = clean_html_response(raw_html, is_snippet=is_snippet)
        
        # Additional validation
        if is_snippet and not cleaned_html:
            print(f"Warning: Snippet cleaning resulted in empty output. Raw response: {raw_html[:200]}...")
        
        return cleaned_html
    except Exception as e:
        print(f"Error calling AI model {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    return "<h1>NeuroArti Pro Builder API is operational.</h1>"

# --- Enhanced API Endpoints ---
@app.post("/build")
async def create_build(request: BuildRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Enhanced system prompt with explicit format requirements
    system_prompt = (
        "CRITICAL: You are a code generation machine. Your response must be ONLY valid HTML code.\n"
        "RULES:\n"
        "1. Start immediately with <!DOCTYPE html>\n"
        "2. No explanations, comments, or text before/after the HTML\n"
        "3. No markdown formatting (no ```html blocks)\n"
        "4. Generate a complete single HTML file using Tailwind CSS via CDN\n"
        "5. Place CSS in <style> tags in <head>\n"
        "6. Place JavaScript in <script> tags before </body>\n"
        "7. Your entire response must be parseable as HTML\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    html_code = generate_code(system_prompt, request.prompt, model_id)
    if html_code and len(html_code.strip()) > 0:
        try:
            body_html, css, js = extract_assets(html_code)
            return {"html": body_html, "css": css, "js": js}
        except Exception as e:
            print(f"Asset extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse generated HTML.")
    
    raise HTTPException(status_code=500, detail="Failed to generate valid website code.")

@app.post("/edit-snippet")
async def create_edit_snippet(request: EditSnippetRequest):
    model_id = MODEL_MAPPING.get(request.model, MODEL_MAPPING["glm-4.5-air"])
    
    # Ultra-strict system prompt for snippet editing
    system_prompt = (
        "You are a HTML transformation function. Input: HTML snippet + instruction. Output: Modified HTML snippet.\n"
        "CRITICAL RULES:\n"
        "1. Response must be ONLY the modified HTML snippet\n"
        "2. NO explanations, descriptions, or text\n"
        "3. NO markdown code blocks (```html)\n"
        "4. NO 'Here is...' or 'I've modified...' responses\n"
        "5. If you cannot modify it, return the original snippet unchanged\n"
        "6. Your response must start with < and end with >\n"
        "RESPOND WITH ONLY HTML CODE."
    )
    
    user_prompt = f"INSTRUCTION: {request.prompt}\n\nHTML TO MODIFY:\n{request.snippet}"
    
    modified_snippet = generate_code(system_prompt, user_prompt, model_id, is_snippet=True)
    
    if modified_snippet and len(modified_snippet.strip()) > 0:
        # Additional validation - ensure it looks like HTML
        if '<' in modified_snippet and '>' in modified_snippet:
            return {"snippet": modified_snippet}
        else:
            print(f"Generated snippet doesn't look like HTML: {modified_snippet}")
    
    # If cleaning failed, try to return the original snippet as fallback
    print(f"Snippet generation failed, returning original. AI response was: {modified_snippet}")
    return {"snippet": request.snippet}

@app.post("/patch-html")
async def patch_html(request: PatchRequest):
    try:
        full_html_doc = f"<body>{request.html}</body>"
        soup = BeautifulSoup(full_html_doc, 'html.parser')
        
        target_element = soup.select_one(request.selector)
        if not target_element:
            raise HTTPException(status_code=404, detail=f"Selector '{request.selector}' not found.")
            
        # Validate the new snippet before attempting to parse
        if not request.new_snippet or not request.new_snippet.strip():
            raise HTTPException(status_code=400, detail="New snippet is empty.")
            
        new_snippet_soup = BeautifulSoup(request.new_snippet, 'html.parser')
        
        if not new_snippet_soup.contents:
            raise HTTPException(status_code=500, detail="Failed to parse new snippet.")
            
        new_tag = new_snippet_soup.contents[0]
        
        if hasattr(new_tag, 'name'):
            target_element.replace_with(new_tag)
        else:
            # Handle text nodes
            target_element.replace_with(new_tag)

        body_html, css, js = extract_assets(str(soup))
        return {"html": body_html, "css": css, "js": js}
        
    except Exception as e:
        print(f"Patching error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to patch HTML: {str(e)}")

# Uvicorn runner for Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
