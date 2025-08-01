# Fixed main.py - Only showing the corrected rewrite_element_endpoint function

@app.put("/api/rewrite-element")
async def rewrite_element_endpoint(request: Request, body: RewriteRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        return JSONResponse(status_code=429, content={"ok": False, "message": "Rate limit exceeded."})
    if not body.html or not body.selectedElementHtml:
        raise HTTPException(status_code=400, detail="Full HTML and a selected element are required.")
    
    try:
        # Parse both the full HTML and the selected element
        full_soup = BeautifulSoup(body.html, 'html.parser')
        selected_soup = BeautifulSoup(body.selectedElementHtml, 'html.parser')
        
        # Get the first (and should be only) element from the selected HTML
        selected_element_parsed = selected_soup.find()
        if not selected_element_parsed:
            raise Exception("Could not parse the selected element HTML.")
        
        # Find the target element using a more robust approach
        # We'll look for elements with matching tag, classes, and content
        target_element = None
        
        # Strategy 1: Try exact string match first (fastest)
        for element in full_soup.find_all():
            if str(element) == body.selectedElementHtml:
                target_element = element
                break
        
        # Strategy 2: If exact match fails, try matching by tag, attributes, and text content
        if not target_element:
            tag_name = selected_element_parsed.name
            element_text = selected_element_parsed.get_text(strip=True)
            element_attrs = selected_element_parsed.attrs
            
            candidates = full_soup.find_all(tag_name)
            for candidate in candidates:
                # Check if text content matches
                if candidate.get_text(strip=True) == element_text:
                    # Check if key attributes match (like class, id)
                    attrs_match = True
                    for key, value in element_attrs.items():
                        if candidate.get(key) != value:
                            attrs_match = False
                            break
                    
                    if attrs_match:
                        target_element = candidate
                        break
        
        # Strategy 3: If still not found, try matching just by tag and classes
        if not target_element and selected_element_parsed.get('class'):
            tag_name = selected_element_parsed.name
            element_classes = selected_element_parsed.get('class', [])
            
            candidates = full_soup.find_all(tag_name)
            for candidate in candidates:
                candidate_classes = candidate.get('class', [])
                if set(element_classes) == set(candidate_classes):
                    target_element = candidate
                    break

        if not target_element:
            raise Exception("The selected element could not be found in the full HTML document. This might happen if the page was modified after selection.")

        # Mark the target element for surgical editing
        target_element['data-neuro-edit-target'] = 'true'
        marked_full_html = str(full_soup)

        user_prompt_for_ai = (
            f"**Full HTML Document:**\n```html\n{marked_full_html}\n```\n\n"
            f"**User's Instruction:**\n'{body.prompt}'\n\n"
        )

        ai_response_text = await generate_code(
            SYSTEM_PROMPT_SURGICAL_EDIT,
            user_prompt_for_ai,
            body.model
        )

        updated_full_html = isolate_and_clean_html(ai_response_text)
        if not updated_full_html:
            raise Exception("AI returned an empty or invalid full HTML document.")

        # Extract the container_id from the original body or generate a new one
        container_id = body.container_id if hasattr(body, 'container_id') else f"neuroarti-container-{uuid.uuid4().hex[:8]}"
        updated_body_content, updated_css, updated_js = extract_assets(updated_full_html, container_id)

        return JSONResponse(content={
            "ok": True, 
            "html": updated_body_content, 
            "css": updated_css, 
            "js": updated_js,
            "container_id": container_id
        })

    except Exception as e:
        print(f"Error during surgical element rewrite: {e}")
        raise HTTPException(status_code=500, detail=str(e))
