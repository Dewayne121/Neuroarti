# main.py
import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# THE FIX IS HERE: Added CORSMiddleware to the imports
from fastapi.middleware.cors import CORSMiddleware

from core.prompts import MAX_REQUESTS_PER_IP, DEFAULT_HTML
from core.models import MODELS, PROVIDERS
from core.utils import ip_limiter, is_the_same_html, apply_diff_patch
from core.ai_services import generate_code_stream, generate_diff_patch

load_dotenv()

# --- Pydantic Models ---
class BuildRequest(BaseModel):
    prompt: str
    model: str
    provider: str
    html: str | None = None
    redesignMarkdown: str | None = None

class UpdateRequest(BaseModel):
    html: str
    prompt: str
    model: str
    provider: str
    selectedElementHtml: str | None = None
    isFollowUp: bool = True


app = FastAPI()

# --- THIS IS THE CRITICAL CORS CONFIGURATION ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, PUT, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Endpoint for initial generation and full rewrites
@app.post("/api/ask-ai")
async def build_or_full_update(request: Request, body: BuildRequest):
    ip = request.client.host
    # Note: A real app would have a more persistent rate limiter
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
         raise HTTPException(status_code=429, detail={"ok": False, "openLogin": True, "message": "Rate limit exceeded. Please log in."})
    
    selected_model = next((m for m in MODELS if m["value"] == body.model), None)
    if not selected_model:
        raise HTTPException(status_code=400, detail={"ok": False, "error": "Invalid model"})
    
    provider_key = body.provider if body.provider != "auto" else selected_model.get("autoProvider", "novita")
    if provider_key not in selected_model["providers"]:
        raise HTTPException(status_code=400, detail={"ok": False, "openSelectProvider": True, "message": "Provider not supported for this model."})

    html_context = body.html if body.html and not is_the_same_html(body.html) else None

    # This response is streamed to the frontend
    return StreamingResponse(
        generate_code_stream(body.prompt, body.model, provider_key, html_context, body.redesignMarkdown),
        media_type="text/plain"
    )

# Endpoint for surgical "Diff-Patch" updates
@app.put("/api/ask-ai")
async def diff_patch_update(request: Request, body: UpdateRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
         raise HTTPException(status_code=429, detail={"ok": False, "openLogin": True, "message": "Rate limit exceeded."})

    # For diff-patch, we use the base, most reliable model.
    selected_model = MODELS[0]
    provider_key = body.provider if body.provider != "auto" else selected_model.get("autoProvider", "novita")

    if provider_key not in selected_model["providers"]:
        raise HTTPException(status_code=400, detail={"ok": False, "openSelectProvider": True, "message": "Provider not supported for this model."})

    # The full HTML is needed for the AI to have context
    full_html_for_context = body.html
    
    patch_instructions = await generate_diff_patch(body.prompt, selected_model["value"], provider_key, full_html_for_context, body.selectedElementHtml)

    if not patch_instructions:
        # If the AI fails, return the original HTML to prevent data loss
        print("Warning: AI returned empty patch. No changes will be applied.")
        return {"ok": True, "html": body.html, "updatedLines": []}

    updated_html = apply_diff_patch(body.html, patch_instructions)

    # Note: In a real application, you might extract CSS/JS here if the patch could modify them.
    # For simplicity, we assume patches only modify the HTML body.
    return {"ok": True, "html": updated_html, "updatedLines": []} # updatedLines can be implemented later if needed

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
