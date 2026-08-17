"""Deterministic lexical retrieval for active memories with bm25s and multilingual stemming."""

from __future__ import annotations

import re
from collections.abc import Sequence

import bm25s  # type: ignore[import-untyped]
import Stemmer  # type: ignore[import-not-found]

from memory_stale.lifecycle import Memory
from memory_stale.project_paths import evidence_path, is_ignored_project_path

TOKEN = re.compile(r"[\w./:-]+", re.UNICODE)
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
LOCATOR_COMPONENT = re.compile(r"[^\W_]+", re.UNICODE)
BM25_K1 = 1.5
BM25_B = 0.75
CLAIM_WEIGHT = 1.0
DURABILITY_REASON_WEIGHT = 0.5
LOCATOR_WEIGHT = 2.0
RETRIEVAL_TERMS_WEIGHT = 0.75
EXACT_LOCATOR_WEIGHT = 100.0
MINIMUM_LEXICAL_SCORE = 0.25
MINIMUM_RELATIVE_SCORE = 0.5

_STEMMERS: dict[str, Stemmer.Stemmer | None] = {}


def _get_stemmer(language: str) -> Stemmer.Stemmer | None:
    lang = language.strip().casefold()
    if lang in _STEMMERS:
        return _STEMMERS[lang]
    lang_map = {
        "pt": "portuguese",
        "por": "portuguese",
        "portuguese": "portuguese",
        "en": "english",
        "eng": "english",
        "english": "english",
        "es": "spanish",
        "spa": "spanish",
        "spanish": "spanish",
        "fr": "french",
        "fra": "french",
        "french": "french",
        "de": "german",
        "deu": "german",
        "german": "german",
        "it": "italian",
        "ita": "italian",
        "italian": "italian",
        "nl": "dutch",
        "nld": "dutch",
        "dutch": "dutch",
        "ru": "russian",
        "rus": "russian",
        "russian": "russian",
    }
    name = lang_map.get(lang, lang)
    try:
        stemmer = Stemmer.Stemmer(name)
    except Exception:
        stemmer = None
    _STEMMERS[lang] = stemmer
    return stemmer


def _tokenize_natural(text: str, language: str = "en") -> list[str]:
    if not text.strip():
        return []
    stemmer = _get_stemmer(language)
    tokens = bm25s.tokenize([text], stemmer=stemmer, return_ids=False)[0]
    return [str(t) for t in tokens]


def _locator_tokens(locator: str) -> list[str]:
    separated = CAMEL_BOUNDARY.sub(" ", locator)
    return [token.casefold() for token in LOCATOR_COMPONENT.findall(separated)]


def _bm25_scores(documents: Sequence[list[str]], query: Sequence[str]) -> list[float]:
    if not documents or not query:
        return [0.0] * len(documents)
    if not any(documents):
        return [0.0] * len(documents)
    all_tokens = {token for doc in documents for token in doc}
    filtered_query = [token for token in set(query) if token in all_tokens]
    if not filtered_query:
        return [0.0] * len(documents)

    retriever = bm25s.BM25(method="lucene", k1=BM25_K1, b=BM25_B)
    retriever.index(list(documents))
    docs, scores = retriever.retrieve([filtered_query], k=len(documents))
    ordered_scores = [0.0] * len(documents)
    scale = BM25_K1 + 1.0
    for doc_idx, score in zip(docs[0], scores[0], strict=True):
        ordered_scores[int(doc_idx)] = float(score) * scale
    return ordered_scores


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


def retrieve(memories: Sequence[Memory], prompt: str, budget: int = 1500, top_k: int = 5) -> str:
    active = [
        memory
        for memory in memories
        if memory.status == "active"
        and not any(
            is_ignored_project_path(evidence_path(item.type, item.locator))
            for item in memory.evidence
        )
    ]
    if not active or not prompt.strip() or budget <= 0 or top_k <= 0:
        return ""

    active_languages = {memory.language for memory in active} or {"en"}
    natural_query_tokens: set[str] = set()
    for lang in active_languages:
        natural_query_tokens.update(_tokenize_natural(prompt, lang))

    locator_query_tokens = _locator_tokens(prompt)

    if not natural_query_tokens and not locator_query_tokens:
        return ""

    claim_documents = [_tokenize_natural(memory.claim, memory.language) for memory in active]
    durability_reason_documents = [
        _tokenize_natural(memory.durability_reason, memory.language) for memory in active
    ]
    locator_documents = [
        [token for item in memory.evidence for token in _locator_tokens(item.locator)]
        for memory in active
    ]
    retrieval_term_documents = [
        _tokenize_natural(" ".join(memory.retrieval_terms), memory.language) for memory in active
    ]

    claim_scores = _bm25_scores(claim_documents, list(natural_query_tokens))
    durability_reason_scores = _bm25_scores(durability_reason_documents, list(natural_query_tokens))
    locator_scores = _bm25_scores(locator_documents, locator_query_tokens)
    retrieval_term_scores = _bm25_scores(retrieval_term_documents, list(natural_query_tokens))

    scored: list[tuple[float, Memory, bool]] = []
    prompt_folded = prompt.casefold()
    for memory, claim_score, durability_reason_score, locator_score, retrieval_term_score in zip(
        active,
        claim_scores,
        durability_reason_scores,
        locator_scores,
        retrieval_term_scores,
        strict=True,
    ):
        score = (
            claim_score * CLAIM_WEIGHT
            + durability_reason_score * DURABILITY_REASON_WEIGHT
            + locator_score * LOCATOR_WEIGHT
            + retrieval_term_score * RETRIEVAL_TERMS_WEIGHT
        )
        exact = sum(
            1 for item in memory.evidence if _is_exact_locator_match(item.locator, prompt_folded)
        )
        score += exact * EXACT_LOCATOR_WEIGHT
        if exact:
            scored.append((score, memory, True))
            continue
        if retrieval_term_score > 0 and claim_score <= 0 and locator_score <= 0:
            continue
        if score >= MINIMUM_LEXICAL_SCORE:
            scored.append((score, memory, False))
    if not scored:
        return ""
    strongest_score = max(score for score, _memory, _exact in scored)
    scored = [
        item for item in scored if item[2] or item[0] >= strongest_score * MINIMUM_RELATIVE_SCORE
    ]
    scored.sort(key=lambda item: (-item[0], item[1].id))
    scored = scored[:top_k]
    selected: list[str] = []
    used = 0
    for _score, memory, _exact in scored:
        block = (
            f"- {memory.claim}\n  Evidence: {', '.join(item.locator for item in memory.evidence)}"
        )
        cost = max(1, (len(block) + 3) // 4)
        if used + cost > budget:
            continue
        selected.append(block)
        used += cost
    return "Memory Stale active context:\n" + "\n".join(selected) if selected else ""
