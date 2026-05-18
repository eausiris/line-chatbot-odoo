from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    line_channel_secret: str
    line_channel_access_token: str
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-20250514"
    odoo_url: str
    odoo_db: str
    odoo_username: str
    odoo_password: str
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: int = 3600
    business_name: str = "ร้านของฉัน"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()