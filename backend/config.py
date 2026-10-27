"""
Application configuration management.
Safely loads and validates environment variables using Pydantic.
"""

from functools import lru_cache
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration settings."""

    # Application Info
    APP_NAME: str = "AI Receptionist Platform"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_BASE_URL: str = "http://localhost:8000"

    # Tool Execution Mode Policy (Explicit Allowlist: 'mock', 'live', 'unavailable')
    TOOL_EXECUTION_MODE: str = "mock"

    @field_validator("TOOL_EXECUTION_MODE")
    @classmethod
    def validate_tool_execution_mode(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("mock", "live", "unavailable"):
            raise ValueError(
                f"Invalid TOOL_EXECUTION_MODE '{v}'. Must be one of: 'mock', 'live', 'unavailable'."
            )
        return clean

    # Groq API Configuration
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    LLM_TIMEOUT_SECONDS: float = 25.0
    LLM_MAX_RETRIES: int = 2

    # Receptionist Agent & Workflow Execution Limits
    AGENT_MAX_ITERATIONS: int = 5
    AGENT_MAX_TOOL_ROUNDS: int = 5
    AGENT_MAX_EXECUTION_SECONDS: float = 60.0
    CONFIRMATION_EXPIRY_SECONDS: int = 3600
    LOG_LEVEL: str = "INFO"

    # Database Configuration (Supabase PostgreSQL)
    DATABASE_URL: Optional[str] = None
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None

    # Exotel Telephony & WebSocket Configuration
    EXOTEL_ACCOUNT_SID: Optional[str] = None
    EXOTEL_API_KEY: Optional[str] = None
    EXOTEL_API_TOKEN: Optional[str] = None
    EXOTEL_SUBDOMAIN: str = "api.in.exotel.com"
    EXOTEL_WEBHOOK_SECRET: Optional[str] = None
    EXOTEL_STREAM_URL: Optional[str] = None
    EXOTEL_SAMPLE_RATE: int = 8000
    EXOTEL_AUDIO_CODEC: str = "audio/x-raw"
    VOICE_WS_IDLE_TIMEOUT_SECONDS: int = 60
    VOICE_WS_MAX_MESSAGE_BYTES: int = 131072  # 128 KB frame size boundary
    VOICE_MAX_BUFFER_BYTES: int = 1048576      # 1 MB bounded audio buffer

    # Deepgram Speech-to-Text & Text-to-Speech Configuration (Step 9C)
    DEEPGRAM_API_KEY: Optional[str] = None
    DEEPGRAM_STT_MODEL: str = "nova-2"
    DEEPGRAM_STT_LANGUAGE: str = "en"
    DEEPGRAM_STT_ENDPOINTING_MS: int = 300
    DEEPGRAM_STT_SAMPLE_RATE: int = 8000
    DEEPGRAM_STT_ENCODING: str = "linear16"
    DEEPGRAM_TTS_MODEL: str = "aura-asteria-en"
    DEEPGRAM_TTS_VOICE: str = "aura-asteria-en"
    DEEPGRAM_TTS_SAMPLE_RATE: int = 8000
    DEEPGRAM_TTS_ENCODING: str = "linear16"
    VOICE_INTERTURN_TIMEOUT_SECONDS: int = 30

    # Multi-Tenant Integration Adapter & Secret Vault Settings
    CAPABILITY_ENCRYPTION_KEY: Optional[str] = None
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    HUBSPOT_ACCESS_TOKEN: Optional[str] = None
    ZENDESK_SUBDOMAIN: Optional[str] = None
    ZENDESK_EMAIL: Optional[str] = None
    ZENDESK_API_TOKEN: Optional[str] = None

    # Microsoft Graph / Entra ID Settings
    MICROSOFT_CLIENT_ID: Optional[str] = None
    MICROSOFT_CLIENT_SECRET: Optional[str] = None
    MICROSOFT_TENANT_ID: str = "common"
    MICROSOFT_REDIRECT_URI: Optional[str] = None

    @property
    def is_exotel_configured(self) -> bool:
        """Check if minimum production Exotel credentials are configured."""
        return bool(self.EXOTEL_ACCOUNT_SID and self.EXOTEL_API_KEY and self.EXOTEL_API_TOKEN)

    @property
    def is_deepgram_configured(self) -> bool:
        """Check if Deepgram API key is configured."""
        return bool(self.DEEPGRAM_API_KEY and self.DEEPGRAM_API_KEY.strip())

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached application settings instance."""
    return Settings()
