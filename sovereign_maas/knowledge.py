"""Versioned, tenant-filtered lexical retrieval over trusted local source records."""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from .domain import StrictModel

DEFAULT_KB = Path(__file__).resolve().parent / "maas_knowledge.json"


class Citation(StrictModel):
    source_id: str
    source_version: str
    kb_version: str
    kind: str
    text: str


class KnowledgeHit(Citation):
    score: int = Field(ge=1)


class KnowledgeBase:
    def __init__(self, path: str | Path = DEFAULT_KB):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.version: str = data["version"]
        self.documents: list[dict[str, Any]] = data["documents"]
        ids = [doc["id"] for doc in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate knowledge source ID")
        for doc in self.documents:
            if doc["classification"] not in ("public", "tenant"):
                raise ValueError("unsupported knowledge classification")
            if (doc["classification"] == "tenant") != (doc["tenant_id"] is not None):
                raise ValueError("knowledge tenant classification mismatch")

    def retrieve(self, tenant_id: str, query: str, limit: int = 3) -> tuple[KnowledgeHit, ...]:
        if not query or len(query) > 1000 or not 1 <= limit <= 5:
            raise ValueError("invalid knowledge query")
        tokens = set(re.findall(r"[\w-]{3,}", query.casefold()))
        ranked: list[KnowledgeHit] = []
        for doc in self.documents:
            if doc["classification"] != "public" and doc["tenant_id"] != tenant_id:
                continue
            score = len(tokens & set(re.findall(r"[\w-]{3,}", doc["text"].casefold())))
            if score:
                ranked.append(
                    KnowledgeHit(
                        source_id=doc["id"],
                        source_version=doc["version"],
                        kb_version=self.version,
                        kind=doc["kind"],
                        text=doc["text"],
                        score=score,
                    )
                )
        return tuple(sorted(ranked, key=lambda hit: (-hit.score, hit.source_id))[:limit])
