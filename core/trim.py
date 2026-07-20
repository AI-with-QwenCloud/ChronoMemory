def _message_len(message: dict) -> int:
    return len(str(message.get("content", "")))


def _total_len(messages: list[dict]) -> int:
    return sum(_message_len(m) for m in messages)


def trim_middle(pinned: list[dict], middle: list[dict], footer: list[dict], char_budget: int) -> list[dict]:
    """Drops entries from `middle` nearest its center first, until the total
    fits char_budget. Callers must pre-sort `middle` so the highest-priority
    entries sit at both ends — trimming order is meaningless otherwise.
    """
    working_middle = list(middle)
    reserved = _total_len(pinned) + _total_len(footer)
    middle_len = _total_len(working_middle)

    while working_middle and reserved + middle_len > char_budget:
        dropped = working_middle.pop(len(working_middle) // 2)
        middle_len -= _message_len(dropped)

    return pinned + working_middle + footer
