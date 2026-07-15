from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Any

class Settings(BaseSettings):
    # Supabase configurations
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., validation_alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(..., validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    
    # Vector DB / SQL connection
    database_url: str = Field(..., validation_alias="DATABASE_URL")
    
    # AI API keys
    cohere_api_key: str = Field(..., validation_alias="COHERE_API_KEY")
    groq_api_key: str = Field(..., validation_alias="GROQ_API_KEY")
    
    # Queue connection
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    
    @field_validator("*", mode="before")
    @classmethod
    def strip_quotes(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().strip("'\"").strip()
        return v
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
