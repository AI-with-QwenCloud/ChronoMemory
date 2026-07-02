from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid

VALID_STATUS = {"active", "archived", "superseded"}
VALID_PROVENANCE = {"user_turn", "agent_turn", "tool_output", "stdout", "external_doc"}

TRUST_SCORES = {
    "user_turn": 1.0,
    "agent_turn": 0.7,
    "tool_output": 0.6,
    "stdout": 0.6,
    "external_doc": 0.4,
}

VIGIL_FLAG_THRESHOLD = 0.5
EMBEDDING_DIM = 384


@dataclass
class MemoryEntry:
    text: str
    embedding: list[float]
    provenance: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    importance: float = 0.5
    relevance_score: float = 0.5
    access_count: int = 0
    status: str = "active"
    superseded_by: Optional[str] = None
    trust_score: Optional[float] = None
    contradiction_log_id: Optional[str] = None
    last_accessed: Optional[datetime] = None
    kv_slot_id: Optional[str] = None

    def __post_init__(self):
        if len(self.embedding) != EMBEDDING_DIM:
            raise ValueError(
                f"embedding must be {EMBEDDING_DIM}-dim, got {len(self.embedding)}"
            )
        if self.provenance not in VALID_PROVENANCE:
            raise ValueError(f"invalid provenance: {self.provenance}")
        if self.status not in VALID_STATUS:
            raise ValueError(f"invalid status: {self.status}")
        if self.trust_score is None:
            self.trust_score = TRUST_SCORES[self.provenance]

    def is_flagged(self) -> bool:
        return self.trust_score < VIGIL_FLAG_THRESHOLD
