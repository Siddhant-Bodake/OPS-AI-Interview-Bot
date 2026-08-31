from google import genai

from app.core.config import settings


def build_gemini_client() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)
