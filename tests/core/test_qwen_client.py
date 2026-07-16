from core.qwen_client import chat

for role in ["agent", "extractor", "scorer"]:
    result = chat(role, [{"role": "user", "content": "Say OK."}])
    usage = result.get("usage", {})
    print(f"role={role} status=ok reasoning_tokens={usage.get('reasoning_tokens')} content={result['choices'][0]['message']['content']!r}")
