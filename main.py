# main.py
import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

from core.prompts import MAX_REQUESTS_PER_IP
from core.models import MODELS, PROVIDERS
from core.utils import ip_limiter, is_the_same_html, apply_diff_patch
from core.ai_services import generate_code_stream, generate_diff_patch

load_dotenv()

# --- A single, more flexible Pydantic Model ---
class AIRequest(BaseModel):
    prompt: str
    model: str
    provider: str
    html: str | None = None
    redesignMarkdown: str | None = None
    selectedElementHtml: str | None = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/ask-ai")
async def build_or_full_update(request: Request, body: AIRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        return JSONResponse(status_code=429, content={"ok": False, "openLogin": True, "message": "Rate limit exceeded."})
    
    selected_model = next((m for m in MODELS if m["value"] == body.model), None)
    if not selected_model:
        raise HTTPException(status_code=400, detail="Invalid model selected")
    
    provider_key = body.provider if body.provider != "auto" else selected_model.get("autoProvider", "novita")
    if provider_key not in selected_model["providers"]:
        raise HTTPException(status_code=400, detail="Provider not supported for this model.")

    html_context = body.html if body.html and not is_the_same_html(body.html) else None

    # Now that validation is passed, we can safely start the stream
    return StreamingResponse(
        generate_code_stream(body.prompt, body.model, provider_key, html_context, body.redesignMarkdown),
        media_type="text/plain"
    )

@app.put("/api/ask-ai")
async def diff_patch_update(request: Request, body: AIRequest):
    ip = request.client.host
    if not ip_limiter(ip, MAX_REQUESTS_PER_IP):
        return JSONResponse(status_code=429, content={"ok": False, "openLogin": True, "message": "Rate limit exceeded."})

    if not body.html:
        raise HTTPException(status_code=400, detail="HTML content is required for a patch update.")

    selected_model = MODELS[0]
    provider_key = body.provider if body.provider != "auto" else selected_model.get("autoProvider", "novita")

    if provider_key not in selected_model["providers"]:
        raise HTTPException(status_code=400, detail="Provider not supported for this model.")
    
    patch_instructions = await generate_diff_patch(body.prompt, selected_model["value"], provider_key, body.html, body.selectedElementHtml)

    if not patch_instructions:
        print("Warning: AI returned empty patch. No changes will be applied.")
        return {"ok": True, "html": body.html}

    updated_html = apply_diff_patch(body.html, patch_instructions)

    return {"ok": True, "html": updated_html}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
