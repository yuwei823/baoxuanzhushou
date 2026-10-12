from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    project_root: Path = Path(__file__).resolve().parents[2]
    dashscope_api_key: SecretStr = SecretStr("")
    bailian_base_url: str = ""
    bailian_text_model: str = "qwen-plus"
    bailian_text_enable_thinking: bool | None = None
    bailian_vision_model: str = "qwen-vl-plus"
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = Field(1024, gt=0)
    retrieval_mode: Literal["bm25", "hybrid"] = "bm25"
    ruleset_id: str = "official-v1-2026-10-11"
    audit_mock: bool = False
    model_timeout_seconds: float = Field(45, gt=0)
    audit_timeout_seconds: float = Field(150, gt=0)
    model_max_retries: int = Field(2, ge=0, le=2)
    model_concurrency: int = Field(2, ge=1, le=2)
    audit_max_model_attempts: int = Field(16, ge=1, le=16)
    batch_rule_count: int = Field(6, ge=1, le=8)
    batch_max_characters: int = Field(90000, ge=1000)
    log_content: bool = False
    # Deployment guards: optional shared access token and in-flight audit cap.
    auth_token: str = ""
    audit_max_concurrency: int = Field(2, ge=1, le=8)

    @property
    def configured(self):
        return self.audit_mock or bool(
            self.dashscope_api_key.get_secret_value() and self.bailian_base_url
        )
