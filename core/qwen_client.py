import os
import random
import time

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

# extractor/scorer are structured-output/classification calls, not open
# conversation — pinning them toward greedy decoding trades away nothing and
# cuts run-to-run variance. The agent role is real conversation and keeps
# its natural sampling.
DETERMINISTIC_ROLES = {"extractor", "scorer"}
DETERMINISTIC_TEMPERATURE = 0.0

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _sleep_backoff(attempt: int) -> None:
    time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt) + random.uniform(0, 0.5))


def _post_with_retry(url: str, headers: dict, payload: dict, timeout: int) -> requests.Response:
    for attempt in range(MAX_ATTEMPTS):
        is_last_attempt = attempt == MAX_ATTEMPTS - 1
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if is_last_attempt:
                raise
            _sleep_backoff(attempt)
            continue

        if response.status_code in RETRIABLE_STATUS_CODES and not is_last_attempt:
            _sleep_backoff(attempt)
            continue

        response.raise_for_status()
        return response


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
    if role in DETERMINISTIC_ROLES:
        payload.setdefault("temperature", DETERMINISTIC_TEMPERATURE)

    response = _post_with_retry(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        payload=payload,
        timeout=30,
    )
    return response.json()
