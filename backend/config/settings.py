"""Configuration read strictly from environment variables via Pydantic BaseSettings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/postgres",
        alias="DATABASE_URL",
        description="Database connection URL for PostgreSQL or SQLite",
    )
    cors_origins_raw: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins",
    )
    llm_provider: str = Field(
        default="gemini",
        alias="LLM_PROVIDER",
        description="LLM Provider (gemini | openai | groq | ollama | mock)",
    )
    llm_api_key: str | None = Field(
        default=None,
        alias="LLM_API_KEY",
        description="API Key for configured LLM provider",
    )
    llm_model: str = Field(
        default="gemini-2.5-flash",
        alias="LLM_MODEL",
        description="Model identifier (e.g. gemini-2.5-flash, gpt-4o-mini, llama-3.3-70b)",
    )
    llm_timeout_seconds: float = Field(
        default=12.0,
        alias="LLM_TIMEOUT_SECONDS",
        description="HTTP request timeout in seconds for LLM API calls",
    )
    stt_provider: str = Field(
        default="local",
        alias="STT_PROVIDER",
        description="Speech-To-Text Provider (local | whisper | openai | mock)",
    )
    stt_api_key: str | None = Field(
        default=None,
        alias="STT_API_KEY",
        description="API Key for Speech-To-Text provider",
    )
    stt_confidence_threshold: float = Field(
        default=0.6,
        alias="STT_CONFIDENCE_THRESHOLD",
        description="Minimum audio transcription confidence score to proceed",
    )
    whisper_model: str = Field(
        default="base",
        alias="WHISPER_MODEL",
        description="Faster-Whisper model size (tiny, base, small, medium, large-v3)",
    )
    whisper_device: str = Field(
        default="cpu",
        alias="WHISPER_DEVICE",
        description="Faster-Whisper device (cpu | cuda)",
    )
    whisper_compute_type: str = Field(
        default="int8",
        alias="WHISPER_COMPUTE_TYPE",
        description="Faster-Whisper compute type (int8 | float32 | float16)",
    )
    allow_ddl: bool = Field(
        default=False,
        alias="ALLOW_DDL",
        description="Permit DDL operations like DROP/TRUNCATE",
    )
    max_query_rows: int = Field(
        default=500,
        alias="MAX_QUERY_ROWS",
        description="Default LIMIT count for generated SELECT queries",
    )
    max_repair_attempts: int = Field(
        default=3,
        alias="MAX_REPAIR_ATTEMPTS",
        description="Maximum automatic SQL repair retry attempts",
    )
    confirmation_ttl_seconds: int = Field(
        default=300,
        alias="CONFIRMATION_TTL_SECONDS",
        description="TTL expiration in seconds for pending execution tokens (default 5 min)",
    )
    max_mutation_rows: int = Field(
        default=1000,
        alias="MAX_MUTATION_ROWS",
        description="Maximum permitted estimated affected rows for UPDATE/DELETE mutations",
    )

    @property
    def cors_origins(self) -> list[str]:
        if not self.cors_origins_raw:
            return []
        return [x.strip() for x in self.cors_origins_raw.split(",") if x.strip()]
