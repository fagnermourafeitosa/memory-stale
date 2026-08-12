"""Deterministic lexical retrieval for active memories."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from memory_stale.lifecycle import Memory

TOKEN = re.compile(r"[\w./:-]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN.findall(text)]


def retrieve(memories: Sequence[Memory], prompt: str, budget: int = 1500) -> str:
    active = [memory for memory in memories if memory.status == "active"]
    query = _tokens(prompt)
    if not active or not query or budget <= 0:
        return ""
    documents = [_tokens(f"{memory.claim} {memory.durability_reason}") for memory in active]
    average_length = sum(map(len, documents)) / len(documents)
    document_frequency = Counter(token for token in set(query) for doc in documents if token in doc)
    scored: list[tuple[float, Memory]] = []
    prompt_folded = prompt.casefold()
    for memory, document in zip(active, documents, strict=True):
        frequencies = Counter(document)
        score = 0.0
        for token in set(query):
            frequency = frequencies[token]
            if not frequency:
                continue
            inverse = math.log(
                1
                + (len(documents) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            score += (
                inverse
                * frequency
                * 2.5
                / (frequency + 1.5 * (0.25 + 0.75 * len(document) / average_length))
            )
        exact = sum(
            1
            for item in memory.evidence
            if item.locator.casefold() in prompt_folded
            or item.locator.rpartition(":")[0].casefold() in prompt_folded
        )
        score += exact * 100.0
        if score > 0:
            scored.append((score, memory))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    selected: list[str] = []
    used = 0
    for _score, memory in scored:
        block = (
            f"- {memory.claim}\n  Evidence: {', '.join(item.locator for item in memory.evidence)}"
        )
        cost = max(1, (len(block) + 3) // 4)
        if used + cost > budget:
            continue
        selected.append(block)
        used += cost
    return "Memory Stale active context:\n" + "\n".join(selected) if selected else ""
