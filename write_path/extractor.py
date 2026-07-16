import json

from core.qwen_client import chat

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


class ExtractionError(Exception):
    """A genuine extraction failure — distinct from the model legitimately
    returning an empty list, which is a normal outcome, not an error.

    `category` lets callers (and the audit log) tell a transient infra
    problem apart from the model returning something the code can't parse,
    instead of collapsing both into one generic failure.
    """

    def __init__(self, category: str, detail: str):
        self.category = category  # "network" | "malformed_response"
        super().__init__(f"{category}: {detail}")


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
    try:
        response = chat(
            "extractor",
            [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": turn_text},
            ],
        )
    except Exception as e:
        raise ExtractionError("network", str(e)) from e

    content = response["choices"][0]["message"]["content"]
    try:
        facts = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as e:
        raise ExtractionError("malformed_response", f"invalid JSON: {e}") from e

    if not isinstance(facts, list):
        raise ExtractionError("malformed_response", f"expected a JSON array of facts, got: {facts!r}")

    for fact in facts:
        if not isinstance(fact, dict) or "text" not in fact or "importance" not in fact:
            raise ExtractionError("malformed_response", f"malformed fact entry: {fact!r}")
        if not isinstance(fact["text"], str) or not fact["text"]:
            raise ExtractionError("malformed_response", f"fact 'text' must be a non-empty string: {fact!r}")
        if not isinstance(fact["importance"], (int, float)):
            raise ExtractionError("malformed_response", f"fact 'importance' must be a number: {fact!r}")

    return facts
