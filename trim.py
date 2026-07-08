def _message_len(message: dict) -> int:
    return len(str(message.get("content", "")))


def _total_len(messages: list[dict]) -> int:
    return sum(_message_len(m) for m in messages)


def trim_middle(pinned: list[dict], middle: list[dict], footer: list[dict], char_budget: int) -> list[dict]:
    working_middle = list(middle)

    while working_middle:
        total = _total_len(pinned) + _total_len(working_middle) + _total_len(footer)
        if total <= char_budget:
            break
        working_middle.pop(len(working_middle) // 2)

    return pinned + working_middle + footer
