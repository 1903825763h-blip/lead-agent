import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    data_dir = get_app_dir() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def load_config() -> dict:
    app_dir = get_app_dir()
    env_path = app_dir / ".env"
    load_dotenv(dotenv_path=env_path)

    return {
        "SERPAPI_KEY": os.getenv("SERPAPI_KEY", ""),
        "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
        "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        "LLM_MODEL": os.getenv("LLM_MODEL", "deepseek-chat"),
        "SMTP_HOST": os.getenv("SMTP_HOST", ""),
        "SMTP_PORT": int(os.getenv("SMTP_PORT", "587") or "587"),
        "SMTP_USER": os.getenv("SMTP_USER", ""),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
        "SMTP_FROM": os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")),
    }
