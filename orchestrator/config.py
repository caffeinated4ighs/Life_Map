"""
config.py — Environment variable loading and startup validation.
Fail fast if any required var is missing.
"""

import os
from dataclasses import dataclass


REQUIRED_VARS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "GROQ_API_KEY",
    "GROQ_MODEL_ID",
    "TIMEZONE",
]

OPTIONAL_VARS = {
    "LOG_LEVEL": "INFO",
    "HEALTH_CHECK_PATH": "/functions/v1/health",
}


@dataclass
class Config:
    supabase_url: str
    supabase_service_key: str
    groq_api_key: str
    groq_model_id: str
    timezone: str
    log_level: str
    health_check_path: str

    @property
    def health_check_url(self) -> str:
        return self.supabase_url.rstrip("/") + self.health_check_path


def load_config() -> Config:
    """Load and validate all environment variables. Raises on missing required vars."""
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        lines = "\n  ".join(missing)
        raise EnvironmentError(
            f"Missing required environment variables:\n  {lines}\n\n"
            "Copy .env.example to .env and fill in all values, then:\n"
            "  export $(cat .env | xargs)   # or use direnv / dotenv"
        )

    return Config(
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_service_key=os.environ["SUPABASE_SERVICE_KEY"],
        groq_api_key=os.environ["GROQ_API_KEY"],
        groq_model_id=os.environ["GROQ_MODEL_ID"],
        timezone=os.environ["TIMEZONE"],
        log_level=os.environ.get("LOG_LEVEL", OPTIONAL_VARS["LOG_LEVEL"]),
        health_check_path=os.environ.get(
            "HEALTH_CHECK_PATH", OPTIONAL_VARS["HEALTH_CHECK_PATH"]
        ),
    )
