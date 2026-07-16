import json

from core.qwen_client import chat

PINNED_TEXT = (
    "You are an assistant operating under the Governed ChronoMemory-OS "
    "protocol. " + ("This is pinned context filler text used to pad the prefix well past typical minimum cache-block thresholds. " * 300)
)

CACHE_USAGE_KEYS = (
    "prompt_cache_hit_tokens",
    "cached_tokens",
    "cache_read_input_tokens",
    "prompt_cache_miss_tokens",
)


def build_messages() -> list[dict]:
    return [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": PINNED_TEXT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        },
        {"role": "user", "content": "Reply with a single word: acknowledged."},
    ]


def main() -> None:
    first = chat("agent", build_messages())
    second = chat("agent", build_messages())

    print("First call usage:")
    print(json.dumps(first.get("usage", {}), indent=2))
    print("\nSecond call usage:")
    print(json.dumps(second.get("usage", {}), indent=2))

    second_details = second.get("usage", {}).get("prompt_tokens_details", {})
    cached_tokens = second_details.get("cached_tokens", 0)
    if cached_tokens > 0:
        print(f"\ncache_control: confirmed working (second call reused {cached_tokens} cached tokens)")
    else:
        print("\ncache_control: not supported by this endpoint as of 2026-07-08")


if __name__ == "__main__":
    main()
