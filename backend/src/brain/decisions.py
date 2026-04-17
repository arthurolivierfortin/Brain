"""Decision log — structured log of agent decisions with reasoning.

Each decision captures what was decided, why, what alternatives were
considered, and (later) what the outcome was.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    """A logged decision with reasoning."""

    id: str
    agent: str
    what: str          # What was decided
    why: str           # Reasoning
    alternatives: list[str] = field(default_factory=list)
    context: str = ""  # What info was available
    outcome: str = ""  # Filled in later
    links: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Decision:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DecisionLog:
    """Append-only decision log for an agent."""

    def __init__(self, agent: str, base_dir: Path | None = None) -> None:
        self._agent = agent
        self._base = base_dir or Path("memory/agents") / agent / "decisions"
        self._base.mkdir(parents=True, exist_ok=True)
        self._path = self._base / "decisions.jsonl"

    def log(
        self,
        decision_id: str,
        what: str,
        why: str,
        alternatives: list[str] | None = None,
        context: str = "",
        links: list[str] | None = None,
    ) -> Decision:
        """Log a new decision."""
        decision = Decision(
            id=decision_id,
            agent=self._agent,
            what=what,
            why=why,
            alternatives=alternatives or [],
            context=context,
            links=links or [],
        )
        self._append(decision)
        logger.info("Decision logged [%s/%s]: %s", self._agent, decision_id, what[:80])
        return decision

    def update_outcome(self, decision_id: str, outcome: str) -> bool:
        """Update the outcome of a previously logged decision."""
        decisions = self._load_all()
        updated = False
        for d in decisions:
            if d.id == decision_id:
                d.outcome = outcome
                updated = True
                break

        if updated:
            self._rewrite(decisions)
            logger.info("Decision outcome updated [%s/%s]: %s", self._agent, decision_id, outcome[:80])
        return updated

    def recent(self, limit: int = 10) -> list[Decision]:
        """Get the most recent decisions."""
        return self._load_all()[-limit:]

    def _append(self, decision: Decision) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(decision.to_dict()) + "\n")
        except OSError as e:
            logger.error("Failed to log decision: %s", e)

    def _load_all(self) -> list[Decision]:
        if not self._path.exists():
            return []
        decisions = []
        try:
            for line in self._path.read_text().splitlines():
                if line.strip():
                    decisions.append(Decision.from_dict(json.loads(line)))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load decisions: %s", e)
        return decisions

    def _rewrite(self, decisions: list[Decision]) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as f:
                for d in decisions:
                    f.write(json.dumps(d.to_dict()) + "\n")
        except OSError as e:
            logger.error("Failed to rewrite decisions: %s", e)
