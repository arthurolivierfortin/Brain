"""Memory entry model with confidence decay and TF-IDF search.

Each memory has a type, confidence score, and decay rate. Confidence
decreases over time based on the entry type:
- architecture: never decays
- strategy: 90-day half-life
- bug: 60-day half-life
- context: 14-day half-life

Search uses TF-IDF similarity weighted by confidence for ranking.
"""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    ARCHITECTURE = "architecture"  # Never decays
    STRATEGY = "strategy"          # 90-day half-life
    BUG = "bug"                    # 60-day half-life
    CONTEXT = "context"            # 14-day half-life
    DECISION = "decision"          # 30-day half-life


# Half-life in days per type (0 = never decays)
DECAY_HALF_LIFE: dict[MemoryType, float] = {
    MemoryType.ARCHITECTURE: 0,
    MemoryType.STRATEGY: 90,
    MemoryType.BUG: 60,
    MemoryType.CONTEXT: 14,
    MemoryType.DECISION: 30,
}

ARCHIVE_THRESHOLD = 0.1
REVIEW_THRESHOLD = 0.5

# ---------- TF-IDF helpers ----------

_TOKENIZE_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset([
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "and", "or", "but",
    "not", "no", "nor", "so", "yet", "both", "either", "neither", "each",
    "every", "all", "any", "few", "more", "most", "other", "some", "such",
    "that", "this", "these", "those", "it", "its", "he", "she", "they",
    "them", "their", "we", "our", "you", "your", "i", "my", "me",
])


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenization with stop-word removal."""
    return [w for w in _TOKENIZE_RE.findall(text.lower()) if w not in _STOP_WORDS]


def _build_tfidf_index(
    docs: list[list[str]],
) -> tuple[list[dict[str, float]], dict[str, float]]:
    """Build TF-IDF vectors for a list of tokenized documents.

    Returns:
        (tf_vectors, idf) where tf_vectors[i] maps term -> tf-idf weight
        and idf maps term -> inverse document frequency.
    """
    n = len(docs)
    if n == 0:
        return [], {}

    # Document frequency
    df: Counter[str] = Counter()
    for tokens in docs:
        df.update(set(tokens))

    # IDF: log(N / df) — add 1 to avoid division by zero
    idf = {term: math.log((n + 1) / (count + 1)) + 1 for term, count in df.items()}

    # TF-IDF vectors
    tf_vectors: list[dict[str, float]] = []
    for tokens in docs:
        tf = Counter(tokens)
        total = len(tokens) or 1
        vec = {t: (c / total) * idf.get(t, 1.0) for t, c in tf.items()}
        tf_vectors.append(vec)

    return tf_vectors, idf


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class MemoryEntry:
    """A single memory entry with decay-based confidence and reinforcement."""

    id: str
    content: str
    memory_type: str  # MemoryType value
    agent: str        # Which agent created this
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # Wikilink targets
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0       # How many times this was returned by search
    last_accessed: str = ""     # ISO timestamp of last search hit
    source: str = ""            # "docs" for read-only doc index entries

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def reinforce(self) -> None:
        """Bump confidence on search hit — frequently accessed memories resist decay."""
        self.access_count += 1
        self.last_accessed = datetime.now(UTC).isoformat()
        # Bump base confidence by 0.1, capped at 1.0
        self.confidence = min(1.0, self.confidence + 0.1)

    def compute_confidence(self) -> float:
        """Compute current confidence based on age, decay, and reinforcement.

        Reinforcement bonus: frequently accessed memories decay slower.
        Formula: base_confidence * decay_factor * reinforcement_bonus
        where reinforcement_bonus = min(1.5, 1.0 + 0.05 * access_count)
        """
        mem_type = MemoryType(self.memory_type)
        half_life = DECAY_HALF_LIFE.get(mem_type, 30)

        if half_life == 0:
            return self.confidence  # Never decays

        try:
            created = datetime.fromisoformat(self.created_at)
            age_days = (datetime.now(UTC) - created).total_seconds() / 86400
        except (ValueError, AttributeError):
            return self.confidence

        # Exponential decay: confidence * 0.5^(age/half_life)
        decay_factor = math.pow(0.5, age_days / half_life)

        # Reinforcement: accessed memories resist decay
        # 0 accesses = neutral (1.0), each access adds 0.05, capped at 1.5
        reinforcement = min(1.5, 1.0 + 0.05 * self.access_count)

        return round(self.confidence * decay_factor * reinforcement, 4)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MemoryEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class MemoryStore:
    """Persistent memory store for an agent. Backed by a JSON file."""

    def __init__(self, agent: str, base_dir: Path | None = None) -> None:
        self._agent = agent
        self._base = base_dir or Path("memory/agents") / agent
        self._base.mkdir(parents=True, exist_ok=True)
        self._path = self._base / "memories.json"
        self._entries: list[MemoryEntry] = self._load()

    def store(
        self,
        content: str,
        memory_type: MemoryType,
        tags: list[str] | None = None,
        links: list[str] | None = None,
    ) -> MemoryEntry:
        """Store a new memory entry."""
        entry = MemoryEntry(
            id="",
            content=content,
            memory_type=memory_type.value,
            agent=self._agent,
            tags=tags or [],
            links=links or [],
        )
        self._entries.append(entry)
        self._save()
        logger.info("Memory stored [%s/%s]: %s", self._agent, entry.id, content[:80])
        return entry

    def search(self, query: str, top_k: int = 5, reinforce: bool = True) -> list[MemoryEntry]:
        """TF-IDF semantic search weighted by confidence decay.

        Combines content + tag text into a document per entry, builds a
        TF-IDF index, and ranks by cosine similarity * confidence.
        Falls back to substring match for single-token queries.

        When reinforce=True, matched entries get a confidence bump
        (like the human brain strengthening frequently-used connections).
        """
        if not self._entries:
            return []

        query_tokens = _tokenize(query)

        # Fallback for very short / stop-word-only queries: substring match
        if not query_tokens:
            query_lower = query.lower()
            scored = []
            for entry in self._entries:
                if query_lower in entry.content.lower() or any(
                    query_lower in t.lower() for t in entry.tags
                ):
                    scored.append((entry.compute_confidence(), entry))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = [entry for _, entry in scored[:top_k]]
            if reinforce and results:
                for entry in results:
                    entry.reinforce()
                self._save()
            return results

        # Build document corpus: content + tags per entry
        docs = [
            _tokenize(entry.content + " " + " ".join(entry.tags))
            for entry in self._entries
        ]

        tf_vectors, idf = _build_tfidf_index(docs)

        # Query vector using the same IDF
        qtf = Counter(query_tokens)
        q_total = len(query_tokens)
        query_vec = {t: (c / q_total) * idf.get(t, 1.0) for t, c in qtf.items()}

        scored = []
        for i, entry in enumerate(self._entries):
            sim = _cosine_similarity(query_vec, tf_vectors[i])
            if sim > 0:
                score = sim * entry.compute_confidence()
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [entry for _, entry in scored[:top_k]]

        # Reinforce matched entries — frequently accessed memories survive longer
        if reinforce and results:
            for entry in results:
                entry.reinforce()
            self._save()

        return results

    def get_by_type(self, memory_type: MemoryType) -> list[MemoryEntry]:
        """Get all entries of a specific type."""
        return [e for e in self._entries if e.memory_type == memory_type.value]

    def get_active(self) -> list[MemoryEntry]:
        """Get all entries above archive threshold."""
        return [e for e in self._entries if e.compute_confidence() >= ARCHIVE_THRESHOLD]

    def consolidate(self) -> dict[str, int]:
        """Run decay consolidation. Returns stats."""
        archived = 0
        flagged = 0
        active = []

        for entry in self._entries:
            conf = entry.compute_confidence()
            if conf < ARCHIVE_THRESHOLD:
                archived += 1
                self._archive(entry)
            else:
                if conf < REVIEW_THRESHOLD:
                    flagged += 1
                active.append(entry)

        self._entries = active
        self._save()
        logger.info(
            "Memory consolidation [%s]: %d active, %d archived, %d flagged for review",
            self._agent, len(active), archived, flagged,
        )
        return {"active": len(active), "archived": archived, "flagged": flagged}

    @property
    def count(self) -> int:
        return len(self._entries)

    def _archive(self, entry: MemoryEntry) -> None:
        """Move an entry to the archive."""
        archive_dir = self._base / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / "archived.jsonl"
        with archive_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def _load(self) -> list[MemoryEntry]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text())
            return [MemoryEntry.from_dict(d) for d in data]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load memories for %s: %s", self._agent, e)
            return []

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(
                [e.to_dict() for e in self._entries], indent=2,
            ))
        except OSError as e:
            logger.error("Failed to save memories for %s: %s", self._agent, e)
