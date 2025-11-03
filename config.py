import os
from typing import Optional


class Config:
    # Groq API Configuration (Fast, free tier available)
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY", "")

    # Ollama Configuration (Free, runs locally)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    # OpenAI API Configuration
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY", "")

    # Email Configuration (IMAP)
    EMAIL_HOST: str = os.getenv("EMAIL_HOST", "imap.gmail.com")
    EMAIL_PORT: int = int(os.getenv("EMAIL_PORT", "993"))
    EMAIL_USER: Optional[str] = os.getenv("EMAIL_USER", "")
    EMAIL_PASSWORD: Optional[str] = os.getenv("EMAIL_PASSWORD", "")

    # Database
    DATABASE_URL: str = "sqlite:///./memberships.db"

    # Upload directories
    UPLOAD_DIR: str = "uploads"
    STATEMENTS_DIR: str = "uploads/statements"
    EMAILS_DIR: str = "uploads/emails"

    # LLM Settings
    GROQ_MODEL_NAME: str = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile")
    OLLAMA_MODEL_NAME: str = os.getenv("OLLAMA_MODEL_NAME", "llama3.2")
    MODEL_NAME: str = "gpt-4-turbo-preview"  # OpenAI model
    TEMPERATURE: float = 0.3

    # Use AI classification (can be slow with Ollama)
    USE_AI_CLASSIFICATION: bool = (
        os.getenv("USE_AI_CLASSIFICATION", "false").lower() == "true"
    )
