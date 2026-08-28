# backend/app/services/retrieval_ranker.py
"""
RetrievalRanker — Weighted Reranking & Diversity Engine
=========================================================
Problem: Chroma returns top-K chunks by raw cosine similarity, which causes
documentation chunks (especially multilingual translations) to dominate context.

Solution:
  1. apply_weights()  — penalize documentation / translation chunks by type
  2. diversify()      — enforce a balanced selection across chunk categories

Chunk type weight map (lower weight = more penalty to effective distance):
  source_code   1.00   (no penalty — always preferred)
  configuration 0.95
  architecture  0.90
  service       0.90
  route         0.85
  test          0.80
  doc           0.70   (general documentation)
  translation   0.40   (multilingual docs under docs/<lang>/ paths)
"""

import re
from typing import List, Dict, Any, Optional

# ── Weight map ────────────────────────────────────────────────────────────────
# Maps chunk_type → multiplier applied to relevance score (NOT to distance).
# Higher multiplier = chunk is preferred.
CHUNK_TYPE_WEIGHTS: Dict[str, float] = {
    # Source code types
    "class":              1.00,
    "function":           1.00,
    "method":             1.00,
    "code":               1.00,
    # Structural types
    "route":              0.95,
    "service":            0.90,
    "model":              0.90,
    "middleware":         0.88,
    # Config / infra
    "configuration block": 0.88,
    "config":             0.88,
    "schema block":       0.85,
    # Tests
    "test":               0.82,
    "paragraph":          0.72,
    # Docs
    "doc":                0.70,
    "section":            0.68,
    # Translations (detected via path prefix, overrides chunk_type)
    "translation":        0.40,
}

# Budget allocation per category when diversifying.
# Values are *maximums* per category — not guarantees.
DIVERSITY_BUDGET: Dict[str, int] = {
    "source_code":    3,   # class, function, method, code, route, service, model
    "config":         2,   # configuration block, config, schema block
    "test":           1,
    "doc":            1,   # doc, section, paragraph
    "translation":    0,   # translations are last resort only
}

# Regex that matches multilingual doc paths: docs/<lang-code>/...
_TRANSLATION_PATH_RE = re.compile(r"^docs/[a-z]{2,3}(?:-[A-Z]{2})?/", re.IGNORECASE)


def _is_translation(chunk: Dict[str, Any]) -> bool:
    """Returns True if the chunk comes from a translated documentation path."""
    file_path = chunk.get("metadata", {}).get("file_path", "")
    return bool(_TRANSLATION_PATH_RE.match(file_path))


def _effective_type(chunk: Dict[str, Any]) -> str:
    """
    Returns the effective chunk type, promoting multilingual docs to 'translation'.
    """
    if _is_translation(chunk):
        return "translation"
    return chunk.get("metadata", {}).get("chunk_type", "code")


def _category(eff_type: str) -> str:
    """Maps effective type to diversity budget category."""
    source_types = {"class", "function", "method", "code", "route", "service", "model", "middleware"}
    config_types = {"configuration block", "config", "schema block"}
    test_types   = {"test"}
    doc_types    = {"doc", "section", "paragraph"}
    if eff_type in source_types:
        return "source_code"
    if eff_type in config_types:
        return "config"
    if eff_type in test_types:
        return "test"
    if eff_type in doc_types:
        return "doc"
    if eff_type == "translation":
        return "translation"
    return "source_code"  # default


def _weighted_score(chunk: Dict[str, Any]) -> float:
    """
    Computes weighted relevance score:
      base_score = 1 - (distance / 2)
      weighted   = base_score * weight
    Higher is better — used for sorting.
    """
    distance  = float(chunk.get("distance", 1.0))
    base      = max(0.0, min(1.0, 1.0 - (distance / 2.0)))
    eff_type  = _effective_type(chunk)
    weight    = CHUNK_TYPE_WEIGHTS.get(eff_type, 0.70)
    return base * weight


class RetrievalRanker:
    """
    Static utility class for chunk reranking and diversity selection.

    Usage in ContextBuilder:
        ranked    = RetrievalRanker.apply_weights(chunks)
        diverse   = RetrievalRanker.diversify(ranked, budget=7)
    """

    @staticmethod
    def apply_weights(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Reorders chunks by weighted relevance score (descending).
        Injects 'weighted_score' and 'effective_type' keys for downstream use.
        Does NOT modify existing keys.
        """
        annotated = []
        for chunk in chunks:
            eff_type = _effective_type(chunk)
            wscore   = _weighted_score(chunk)
            annotated.append({
                **chunk,
                "_effective_type":  eff_type,
                "_weighted_score":  wscore,
                "_category":        _category(eff_type),
            })
        annotated.sort(key=lambda c: c["_weighted_score"], reverse=True)
        return annotated

    @staticmethod
    def diversify(
        chunks: List[Dict[str, Any]],
        budget: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Selects up to `budget` chunks enforcing category diversity.

        Pass 1: Fill category slots in weighted-score order.
        Pass 2: Fill remaining slots with any remaining chunks.
        Pass 3: Add translations only if budget still not met.
        """
        category_counts: Dict[str, int] = {k: 0 for k in DIVERSITY_BUDGET}
        selected: List[Dict[str, Any]] = []
        overflow: List[Dict[str, Any]] = []

        for chunk in chunks:
            if len(selected) >= budget:
                break
            cat   = chunk.get("_category", "source_code")
            limit = DIVERSITY_BUDGET.get(cat, 1)
            if category_counts.get(cat, 0) < limit:
                selected.append(chunk)
                category_counts[cat] = category_counts.get(cat, 0) + 1
            else:
                overflow.append(chunk)

        # Pass 2: fill remaining slots (non-translation overflow)
        for chunk in overflow:
            if len(selected) >= budget:
                break
            if chunk.get("_category") != "translation":
                selected.append(chunk)

        # Pass 3: translations as last resort
        for chunk in overflow:
            if len(selected) >= budget:
                break
            if chunk.get("_category") == "translation":
                selected.append(chunk)

        return selected

    @staticmethod
    def get_type_summary(chunks: List[Dict[str, Any]]) -> Dict[str, int]:
        """Returns a count of each effective type in the chunk list — useful for debug."""
        counts: Dict[str, int] = {}
        for c in chunks:
            t = c.get("_effective_type", _effective_type(c))
            counts[t] = counts.get(t, 0) + 1
        return counts
