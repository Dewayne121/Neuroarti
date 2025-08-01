# core/models.py

# This dictionary now defines all models, their display names, the API to use,
# and the exact ID for that API. This is the single source of truth.
MODELS = {
    "glm-4.5-air": {
        "label": "GLM 4.5 Air",
        "api_provider": "together",
        "api_id": "zai-org/GLM-4.5-Air-FP8", # The specific ID for Together.ai
    },
    "gemini-2.5-flash-lite": {
        "label": "Gemini 2.5 Lite",
        "api_provider": "google",
        "api_id": "gemini-1.5-flash-latest", # The specific ID for Google's API
    },
    "deepseek-r1": {
        "label": "DeepSeek R1",
        "api_provider": "together",
        "api_id": "deepseek-ai/DeepSeek-R1-0528-tput", # The specific ID for Together.ai
    }
}

# The providers dictionary is now simpler as the model defines which one to use.
PROVIDERS = {
    "together": {"name": "Together AI"},
    "google": {"name": "Google AI"}
}
