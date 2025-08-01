# core/models.py

MODELS = {
    "glm-4.5-air": {
        "label": "GLM 4.5 Air",
        "api_provider": "together",
        "api_id": "zai-org/GLM-4.5-Air-FP8",
    },
    # THE CRITICAL FIX: Using the correct API ID from the documentation
    "gemini-2.5-flash-lite": {
        "label": "Gemini 2.5 Flash-Lite",
        "api_provider": "google",
        "api_id": "gemini-2.5-flash-lite", # Corrected from "gemini-1.5-flash-latest"
    },
    "deepseek-r1": {
        "label": "DeepSeek R1",
        "api_provider": "together",
        "api_id": "deepseek-ai/DeepSeek-R1-0528-tput",
    }
}

PROVIDERS = {
    "together": {"name": "Together AI"},
    "google": {"name": "Google AI"}
}
