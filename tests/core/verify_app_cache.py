import json

from core.prompts import PINNED_PROFILE, SYSTEM_PROMPT
from core.qwen_client import chat


def pinned_message(text: str) -> dict:
    return {
        "role": "system",
        "content": [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
    }


def build_messages() -> list[dict]:
    return [
        pinned_message(SYSTEM_PROMPT),
        pinned_message(PINNED_PROFILE),
        {"role": "user", "content": "Reply with a single word: acknowledged."},
    ]


first = chat("agent", build_messages())
second = chat("agent", build_messages())

print("First call usage:", json.dumps(first.get("usage", {}), indent=2))
print("Second call usage:", json.dumps(second.get("usage", {}), indent=2))

cached_tokens = second.get("usage", {}).get("prompt_tokens_details", {}).get("cached_tokens", 0)
if cached_tokens > 0:
    print(f"\ncache_control: confirmed working on the real app prefix ({cached_tokens} cached tokens)")
else:
    print("\ncache_control: NOT hit — prefix may still be short, or endpoint isn't caching it")
