"""Session Q&A memory — the host remembers the last few caller questions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class QA:
    question: str
    answer: str
    files: list[str] = field(default_factory=list)


class SessionMemory:
    def __init__(self, limit: int = 5):
        self._items: deque[QA] = deque(maxlen=limit)

    def add(self, qa: QA) -> None:
        self._items.append(qa)

    def __len__(self) -> int:
        return len(self._items)

    def history_messages(self) -> list[dict]:
        """Past turns as real chat messages — follow-ups ('shorter', 'in one
        sentence') then work naturally instead of confusing the retrieval."""
        messages: list[dict] = []
        for qa in self._items:
            messages.append({"role": "user", "content": qa.question})
            messages.append({"role": "assistant", "content": qa.answer})
        return messages

    def render(self) -> str:
        if not self._items:
            return ""
        lines = [
            f'- Caller asked: "{qa.question}" — you answered: "{qa.answer}"'
            for qa in self._items
        ]
        return "RECENT Q&A THIS SHOW (don't repeat yourself):\n" + "\n".join(lines)
