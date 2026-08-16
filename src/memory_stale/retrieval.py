"""Deterministic lexical retrieval for active memories."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from memory_stale.lifecycle import Memory

TOKEN = re.compile(r"[\w./:-]+", re.UNICODE)
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
LOCATOR_COMPONENT = re.compile(r"[^\W_]+", re.UNICODE)
BM25_K1 = 1.5
BM25_B = 0.75
CLAIM_WEIGHT = 1.0
DURABILITY_REASON_WEIGHT = 0.5
LOCATOR_WEIGHT = 2.0
EXACT_LOCATOR_WEIGHT = 100.0


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN.findall(text)]


def _locator_tokens(locator: str) -> list[str]:
    separated = CAMEL_BOUNDARY.sub(" ", locator)
    return [token.casefold() for token in LOCATOR_COMPONENT.findall(separated)]


def _bm25_scores(documents: Sequence[list[str]], query: Sequence[str]) -> list[float]:
    average_length = sum(map(len, documents)) / len(documents)
    document_frequency = Counter(token for token in set(query) for doc in documents if token in doc)
    scores: list[float] = []
    for document in documents:
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
                * (BM25_K1 + 1.0)
                / (frequency + BM25_K1 * (1.0 - BM25_B + BM25_B * len(document) / average_length))
            )
        scores.append(score)
    return scores


def _is_exact_locator_match(locator: str, prompt_folded: str) -> bool:
    locator_folded = locator.casefold()
    if locator_folded in prompt_folded:
        return True
    symbol_path, symbol_separator, symbol = locator.rpartition(":")
    if symbol_separator and (
        (symbol_path and symbol_path.casefold() in prompt_folded)
        or (symbol and symbol.casefold() in prompt_folded)
    ):
        return True
    document_path, pointer_separator, _pointer = locator.partition("#")
    return bool(pointer_separator and document_path and document_path.casefold() in prompt_folded)


def retrieve(memories: Sequence[Memory], prompt: str, budget: int = 1500) -> str:
    active = [memory for memory in memories if memory.status == "active"]
    query = _tokens(prompt)
    if not active or not query or budget <= 0:
        return ""
    claim_documents = [_tokens(memory.claim) for memory in active]
    durability_reason_documents = [_tokens(memory.durability_reason) for memory in active]
    locator_documents = [
        [token for item in memory.evidence for token in _locator_tokens(item.locator)]
        for memory in active
    ]
    claim_scores = _bm25_scores(claim_documents, query)
    durability_reason_scores = _bm25_scores(durability_reason_documents, query)
    locator_scores = _bm25_scores(locator_documents, query)
    scored: list[tuple[float, Memory]] = []
    prompt_folded = prompt.casefold()
    for memory, claim_score, durability_reason_score, locator_score in zip(
        active,
        claim_scores,
        durability_reason_scores,
        locator_scores,
        strict=True,
    ):
        score = (
            claim_score * CLAIM_WEIGHT
            + durability_reason_score * DURABILITY_REASON_WEIGHT
            + locator_score * LOCATOR_WEIGHT
        )
        exact = sum(
            1 for item in memory.evidence if _is_exact_locator_match(item.locator, prompt_folded)
        )
        score += exact * EXACT_LOCATOR_WEIGHT
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
