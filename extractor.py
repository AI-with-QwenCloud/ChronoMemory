import json

from qwen_client import chat

EXTRACTION_SYSTEM_PROMPT = """You are the memory-extraction stage of an AI coding assistant. Given a \
single conversation turn, extract any durable, standalone facts about the \
user, the project, or their preferences that are worth remembering across \
sessions — not filler, acknowledgements, or content that only makes sense \
in the moment.

Return ONLY a JSON array (no markdown fences, no commentary). Each element \
must have exactly these keys:
- "text": a self-contained sentence stating the fact (must make sense \
without the original conversation).
- "importance": a number from 0.0 to 1.0 rating how significant this fact \
is to remember long-term (0.9+ for explicit decisions/preferences stated \
directly, 0.5-0.7 for incidental but useful details, below 0.3 for minor \
trivia).

If the turn contains no durable facts, return an empty array: []"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        elif text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def extract_facts(turn_text: str) -> list[dict]:
    response = chat(
        "extractor",
        [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": turn_text},
        ],
    )
    content = response["choices"][0]["message"]["content"]
    facts = json.loads(_strip_code_fence(content))

    if not isinstance(facts, list):
        raise ValueError(f"expected a JSON array of facts, got: {facts!r}")

    for fact in facts:
        if not isinstance(fact, dict) or "text" not in fact or "importance" not in fact:
            raise ValueError(f"malformed fact entry: {fact!r}")
        if not isinstance(fact["text"], str) or not fact["text"]:
            raise ValueError(f"fact 'text' must be a non-empty string: {fact!r}")
        if not isinstance(fact["importance"], (int, float)):
            raise ValueError(f"fact 'importance' must be a number: {fact!r}")

    return facts
