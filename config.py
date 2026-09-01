import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""
    
    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"

    # OpenAI / LLM Settings
    openai_api_key: str = "your_openai_api_key_here"
    llm_model: str = "gpt-4o-mini"

    # Supabase Settings
    supabase_url: str = "https://your-project.supabase.co"
    supabase_key: str = "your_supabase_anon_or_service_key"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

