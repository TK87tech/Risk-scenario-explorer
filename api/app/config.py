from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://grp:grp@localhost:5434/grp"

    # OIDC: the issuer is what tokens say (the browser-facing URL); the JWKS URL is how the API reaches
    # the provider (inside Docker that's the service name, not localhost).
    oidc_issuer: str = "http://localhost:8081/realms/grp-demo"
    oidc_jwks_url: str = "http://localhost:8081/realms/grp-demo/protocol/openid-connect/certs"
    oidc_audience: str = "grp-api"

    # Bounded LLM explanations. Without an API key the API falls back to deterministic template explanations.
    # llm_provider picks the backend: "anthropic" (Claude) or "openrouter" (any OpenRouter model with tool calling).
    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5"
    openrouter_api_key: str | None = None
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
