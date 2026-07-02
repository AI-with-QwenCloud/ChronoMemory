import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"

ROLE_CONFIG = {
    "agent":     {"key_env": "QWEN_KEY_AGENT",      "model": "qwen3.6-plus"},
    "extractor": {"key_env": "QWEN_KEY_BACKGROUND",  "model": "qwen3.6-flash"},
    "scorer":    {"key_env": "QWEN_KEY_BACKGROUND",  "model": "qwen3.6-flash"},
}

# extractor/scorer are high-frequency, low-complexity calls — thinking must
# never be left on by accident here (a forgotten flag turns a 2s call into
# a 30s one). The agent role gets no such override for the same reason it's
# hardcoded elsewhere: forgetting it once shouldn't be possible.
NO_THINKING_OVERRIDE_ROLES = {"extractor", "scorer"}


def chat(role: str, messages: list[dict], enable_thinking: bool = False, **kwargs) -> dict:
    if role not in ROLE_CONFIG:
        raise ValueError(f"unknown role: {role}")

    config = ROLE_CONFIG[role]
    api_key = os.environ[config["key_env"]]

    if role in NO_THINKING_OVERRIDE_ROLES:
        enable_thinking = False

    payload = {
        "model": config["model"],
        "messages": messages,
        "enable_thinking": enable_thinking,
        **kwargs,
    }

    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
