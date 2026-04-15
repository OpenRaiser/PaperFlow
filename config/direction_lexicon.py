#!/usr/bin/env python3
"""
Shared canonical direction registry for SciTaste.

This module centralizes:
- canonical direction metadata
- alias / paper-term expansion
- runtime lexicon persistence
- pending new-direction candidates awaiting confirmation
"""

from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_runtime_path(env_name: str, relative_path: str) -> Path:
    configured = str(os.environ.get(env_name, "")).strip()
    if configured:
        return Path(configured).expanduser()
    return PROJECT_ROOT / relative_path


LEXICON_PATH = _resolve_runtime_path("SCITASTE_DIRECTION_LEXICON_PATH", "config/direction_lexicon.json")
PENDING_PATH = _resolve_runtime_path("SCITASTE_DIRECTION_PENDING_PATH", "data/direction_pending.json")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _normalize_lookup_key(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return ""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def normalize_direction_key(value: Any) -> str:
    raw = str(value or "").strip().casefold()
    if not raw:
        return ""
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", raw, flags=re.UNICODE)
    slug = slug.strip("-_")
    slug = re.sub(r"[_\s]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug


def _dedupe_strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        marker = cleaned.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(cleaned)
    return result


def _default_entry(
    canonical_name: str,
    *,
    name: Optional[str] = None,
    name_cn: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    paper_terms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    canonical_name = normalize_direction_key(canonical_name)
    display_name = str(name or canonical_name.replace("-", " ").title()).strip()
    display_name_cn = str(name_cn or display_name).strip()
    alias_values = _dedupe_strings(
        [
            canonical_name,
            canonical_name.replace("-", " "),
            display_name,
            display_name_cn,
            *(aliases or []),
        ]
    )
    paper_values = _dedupe_strings([*(paper_terms or []), canonical_name.replace("-", " "), display_name])
    return {
        "canonical_name": canonical_name,
        "name": display_name,
        "name_cn": display_name_cn,
        "aliases": alias_values,
        "paper_terms": paper_values,
        "keywords": paper_values[:],
    }


BUILTIN_DIRECTION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "gui-agent": _default_entry(
        "gui-agent",
        name="GUI Agent",
        name_cn="GUI Agent",
        aliases=[
            "computer use",
            "computer use agent",
            "computer-use agent",
            "screen agent",
            "interface agent",
            "ui agent",
            "agentic ui automation",
            "computer use agents",
        ],
        paper_terms=[
            "gui agent",
            "computer use",
            "interface automation",
            "desktop automation",
            "ui automation",
        ],
    ),
    "multimodal-reasoning": _default_entry(
        "multimodal-reasoning",
        name="Multimodal Reasoning",
        name_cn="多模态推理",
        aliases=["multi-modal reasoning", "vision-language reasoning"],
        paper_terms=["multimodal reasoning", "multimodal", "vision-language reasoning"],
    ),
    "multimodal-learning": _default_entry(
        "multimodal-learning",
        name="Multimodal Learning",
        name_cn="多模态学习",
        aliases=["multi-modal learning"],
        paper_terms=["multimodal learning", "multimodal"],
    ),
    "vision-language": _default_entry(
        "vision-language",
        name="Vision-Language",
        name_cn="视觉语言",
        aliases=["vision language", "vision and language", "visual language"],
        paper_terms=["vision-language", "vision and language", "visual language"],
    ),
    "vision-language-model": _default_entry(
        "vision-language-model",
        name="Vision-Language Model",
        name_cn="视觉语言模型",
        aliases=["vlm", "vision language model", "multimodal llm"],
        paper_terms=["vision-language model", "visual language model", "vlm"],
    ),
    "cross-modal": _default_entry(
        "cross-modal",
        name="Cross-Modal Learning",
        name_cn="跨模态学习",
        aliases=["cross modal", "cross-modal learning"],
        paper_terms=["cross-modal", "cross modal"],
    ),
    "vision": _default_entry(
        "vision",
        name="Vision",
        name_cn="视觉",
        aliases=["computer vision", "visual understanding", "image understanding"],
        paper_terms=["vision", "visual", "image", "video", "computer vision"],
    ),
    "computer-vision": _default_entry(
        "computer-vision",
        name="Computer Vision",
        name_cn="计算机视觉",
        aliases=["cv"],
        paper_terms=["computer vision", "cv", "visual recognition"],
    ),
    "language": _default_entry(
        "language",
        name="Language",
        name_cn="语言",
        aliases=["natural language", "language modeling"],
        paper_terms=["language", "text", "transformer", "llm", "language model"],
    ),
    "nlp": _default_entry(
        "nlp",
        name="Natural Language Processing",
        name_cn="自然语言处理",
        aliases=["natural language processing"],
        paper_terms=["nlp", "natural language processing"],
    ),
    "machine-learning": _default_entry(
        "machine-learning",
        name="Machine Learning",
        name_cn="机器学习",
        aliases=["ml"],
        paper_terms=["machine learning", "ml", "classification", "regression"],
    ),
    "deep-learning": _default_entry(
        "deep-learning",
        name="Deep Learning",
        name_cn="深度学习",
        aliases=["neural network", "neural networks"],
        paper_terms=["deep learning", "neural", "cnn", "transformer"],
    ),
    "reinforcement-learning": _default_entry(
        "reinforcement-learning",
        name="Reinforcement Learning",
        name_cn="强化学习",
        aliases=["rl"],
        paper_terms=["reinforcement learning", "rl", "reward", "policy"],
    ),
    "reasoning": _default_entry(
        "reasoning",
        name="Reasoning",
        name_cn="推理",
        aliases=["chain of thought", "cot", "reasoning model"],
        paper_terms=["reasoning", "chain of thought", "cot"],
    ),
    "agent": _default_entry(
        "agent",
        name="Agent",
        name_cn="智能体",
        aliases=["agents", "autonomous agent", "agentic system"],
        paper_terms=["agent", "agents", "autonomous", "agentic"],
    ),
    "optimization": _default_entry(
        "optimization",
        name="Optimization",
        name_cn="优化",
        aliases=["optimizer"],
        paper_terms=["optimization", "optimize", "efficient", "optimizer"],
    ),
    "retrieval": _default_entry(
        "retrieval",
        name="Retrieval",
        name_cn="检索",
        aliases=["rag", "retriever"],
        paper_terms=["retrieval", "retrieve", "search", "rag"],
    ),
    "generation": _default_entry(
        "generation",
        name="Generation",
        name_cn="生成",
        aliases=["generative model", "content generation"],
        paper_terms=["generation", "generate", "diffusion", "generative"],
    ),
    "data-native": _default_entry(
        "data-native",
        name="Data-Native",
        name_cn="数据原生",
        aliases=["data native", "data-centric", "data centric"],
        paper_terms=["data-native", "data native", "data-centric", "infrastructure"],
    ),
    "bio-molecular": _default_entry(
        "bio-molecular",
        name="Bio-Molecular",
        name_cn="生物分子",
        aliases=["biomolecular", "molecular biology", "protein science"],
        paper_terms=["protein", "molecular", "dna", "rna", "gene", "cell", "bio", "molecule"],
    ),
    "bioinformatics": _default_entry(
        "bioinformatics",
        name="Bioinformatics",
        name_cn="生物信息学",
        aliases=["computational biology"],
        paper_terms=["bioinformatics", "computational biology", "genome", "genomic", "single-cell", "multiomic"],
    ),
    "protein-folding": _default_entry(
        "protein-folding",
        name="Protein Folding",
        name_cn="蛋白折叠",
        aliases=["protein structure", "protein structure prediction"],
        paper_terms=["protein folding", "protein structure", "structural biology"],
    ),
    "protein-language-model": _default_entry(
        "protein-language-model",
        name="Protein Language Model",
        name_cn="蛋白语言模型",
        aliases=["protein lm", "plm"],
        paper_terms=["protein language model", "protein lm", "plm"],
    ),
    "science-discovery": _default_entry(
        "science-discovery",
        name="Scientific Discovery",
        name_cn="科学发现",
        aliases=["scientific discovery"],
        paper_terms=["scientific", "science", "discovery", "hypothesis", "experiment"],
    ),
    "ai-detection": _default_entry(
        "ai-detection",
        name="AI Detection",
        name_cn="AI Detection",
        aliases=[
            "ai detection",
            "ai 检测",
            "ai检测",
            "ai generated content detection",
            "aigc detection",
            "aigc 检测",
            "aigc检测",
            "生成式内容检测",
            "生成内容检测",
            "llm detection",
            "deepfake detection",
            "synthetic media detection",
        ],
        paper_terms=[
            "ai detection",
            "ai 检测",
            "aigc detection",
            "aigc 检测",
            "deepfake detection",
            "synthetic media detection",
            "machine-generated content detection",
        ],
    ),
    "detection": _default_entry(
        "detection",
        name="Detection",
        name_cn="检测",
        aliases=["detector"],
        paper_terms=["detection", "detect", "detector"],
    ),
    "segmentation": _default_entry(
        "segmentation",
        name="Segmentation",
        name_cn="分割",
        paper_terms=["segmentation", "segment"],
    ),
    "explanation": _default_entry(
        "explanation",
        name="Explanation",
        name_cn="可解释性",
        aliases=["interpretability", "explainability"],
        paper_terms=["explanation", "explainable", "interpretability", "explainability"],
    ),
    "safety": _default_entry(
        "safety",
        name="Safety",
        name_cn="安全",
        paper_terms=["safety", "safe", "robust", "adversarial"],
    ),
    "privacy": _default_entry(
        "privacy",
        name="Privacy",
        name_cn="隐私",
        paper_terms=["privacy", "private"],
    ),
    "comparison": _default_entry(
        "comparison",
        name="Comparison",
        name_cn="Comparison",
        paper_terms=["comparison", "comparative study"],
    ),
}


DEFAULT_LEXICON = copy.deepcopy(BUILTIN_DIRECTION_REGISTRY)


def _normalize_entry(canonical_name: str, payload: Any) -> Dict[str, Any]:
    data = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    canonical_name = normalize_direction_key(data.get("canonical_name") or canonical_name)
    legacy_keywords = data.get("keywords") if isinstance(data.get("keywords"), list) else []
    aliases = data.get("aliases") if isinstance(data.get("aliases"), list) else []
    paper_terms = data.get("paper_terms") if isinstance(data.get("paper_terms"), list) else []

    if legacy_keywords and not aliases:
        aliases = list(legacy_keywords)
    if legacy_keywords and not paper_terms:
        paper_terms = list(legacy_keywords)

    normalized = _default_entry(
        canonical_name,
        name=str(data.get("name") or canonical_name.replace("-", " ").title()),
        name_cn=str(data.get("name_cn") or data.get("name") or canonical_name.replace("-", " ").title()),
        aliases=aliases,
        paper_terms=paper_terms,
    )

    if data.get("source_text"):
        normalized["source_text"] = str(data["source_text"])

    return normalized


def load_lexicon() -> Dict[str, Dict[str, Any]]:
    lexicon = {key: _normalize_entry(key, value) for key, value in BUILTIN_DIRECTION_REGISTRY.items()}
    if LEXICON_PATH.exists():
        try:
            with LEXICON_PATH.open("r", encoding="utf-8") as handle:
                runtime_lexicon = json.load(handle) or {}
        except Exception as exc:
            print(f"Failed to load direction lexicon: {exc}")
            runtime_lexicon = {}

        if isinstance(runtime_lexicon, dict):
            for key, value in runtime_lexicon.items():
                normalized_key = normalize_direction_key(key) or str(key)
                runtime_entry = _normalize_entry(str(key), value)
                builtin_entry = lexicon.get(normalized_key)
                if builtin_entry:
                    merged_entry = _normalize_entry(
                        normalized_key,
                        {
                            "canonical_name": normalized_key,
                            "name": builtin_entry.get("name"),
                            "name_cn": builtin_entry.get("name_cn"),
                            "aliases": _dedupe_strings(
                                [
                                    *(builtin_entry.get("aliases", []) or []),
                                    *(runtime_entry.get("aliases", []) or []),
                                ]
                            ),
                            "paper_terms": _dedupe_strings(
                                [
                                    *(builtin_entry.get("paper_terms", []) or []),
                                    *(runtime_entry.get("paper_terms", []) or []),
                                ]
                            ),
                            "source_text": runtime_entry.get("source_text") or builtin_entry.get("source_text", ""),
                        },
                    )
                    lexicon[normalized_key] = merged_entry
                else:
                    lexicon[normalized_key] = runtime_entry

    return lexicon


def save_lexicon(lexicon: Dict[str, Any]) -> bool:
    try:
        normalized = {
            key: _normalize_entry(key, value)
            for key, value in (lexicon or {}).items()
            if normalize_direction_key(key)
        }
        LEXICON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEXICON_PATH.open("w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2, ensure_ascii=False, sort_keys=True)
        return True
    except Exception as exc:
        print(f"Failed to save direction lexicon: {exc}")
        return False


def get_direction_entry(direction_key: str, lexicon: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    normalized_key = normalize_direction_key(direction_key)
    if not normalized_key:
        return None
    current_lexicon = lexicon or load_lexicon()
    entry = current_lexicon.get(normalized_key)
    return copy.deepcopy(entry) if entry else None


def _iter_match_terms(entry: Dict[str, Any], include_paper_terms: bool = True) -> Iterable[tuple[str, str]]:
    yield ("canonical_name", entry.get("canonical_name", ""))
    yield ("name", entry.get("name", ""))
    yield ("name_cn", entry.get("name_cn", ""))
    for alias in entry.get("aliases", []) or []:
        yield ("alias", alias)
    if include_paper_terms:
        for term in entry.get("paper_terms", []) or []:
            yield ("paper_term", term)


def resolve_canonical_direction(
    value: Any,
    *,
    lexicon: Optional[Dict[str, Any]] = None,
    include_paper_terms: bool = True,
) -> Optional[Dict[str, Any]]:
    normalized_lookup = _normalize_lookup_key(value)
    if not normalized_lookup:
        return None

    current_lexicon = lexicon or load_lexicon()
    for canonical_name, entry in current_lexicon.items():
        for match_field, raw_term in _iter_match_terms(entry, include_paper_terms=include_paper_terms):
            if _normalize_lookup_key(raw_term) == normalized_lookup:
                return {
                    "canonical_name": canonical_name,
                    "match_field": match_field,
                    "matched_text": str(raw_term),
                    "entry": copy.deepcopy(entry),
                }
    return None


def get_lexicon_keywords() -> Dict[str, List[str]]:
    lexicon = load_lexicon()
    return {
        key: _dedupe_strings(
            [
                *(entry.get("aliases", []) or []),
                *(entry.get("paper_terms", []) or []),
                entry.get("name"),
                entry.get("name_cn"),
            ]
        )
        for key, entry in lexicon.items()
    }


def expand_direction_terms(
    canonical_directions: Iterable[Any],
    *,
    lexicon: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    current_lexicon = lexicon or load_lexicon()
    expanded: Dict[str, Dict[str, Any]] = {}
    for direction in canonical_directions:
        resolved = resolve_canonical_direction(direction, lexicon=current_lexicon, include_paper_terms=True)
        canonical_name = resolved["canonical_name"] if resolved else normalize_direction_key(direction)
        if not canonical_name:
            continue
        entry = current_lexicon.get(canonical_name) or _default_entry(canonical_name)
        expanded[canonical_name] = {
            "canonical_name": canonical_name,
            "name": entry.get("name", canonical_name),
            "name_cn": entry.get("name_cn", entry.get("name", canonical_name)),
            "aliases": _dedupe_strings(entry.get("aliases", [])),
            "paper_terms": _dedupe_strings(entry.get("paper_terms", [])),
        }
    return expanded


def canonicalize_direction_terms(
    values: Iterable[Any],
    *,
    lexicon: Optional[Dict[str, Any]] = None,
    include_paper_terms: bool = True,
    keep_unknown: bool = True,
) -> List[str]:
    current_lexicon = lexicon or load_lexicon()
    canonical_terms: List[str] = []
    seen = set()

    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        resolved = resolve_canonical_direction(
            cleaned,
            lexicon=current_lexicon,
            include_paper_terms=include_paper_terms,
        )
        normalized = resolved["canonical_name"] if resolved else normalize_direction_key(cleaned)
        if not normalized:
            continue
        if resolved is None and not keep_unknown:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        canonical_terms.append(normalized)

    return canonical_terms


def canonicalize_weight_mapping(
    mapping: Optional[Dict[str, Any]],
    *,
    lexicon: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    current_lexicon = lexicon or load_lexicon()
    canonicalized: Dict[str, float] = {}
    for key, value in (mapping or {}).items():
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        cleaned = str(key or "").strip()
        if not cleaned:
            continue
        resolved = resolve_canonical_direction(cleaned, lexicon=current_lexicon, include_paper_terms=True)
        canonical_name = resolved["canonical_name"] if resolved else normalize_direction_key(cleaned)
        if not canonical_name:
            continue
        canonicalized[canonical_name] = max(float(canonicalized.get(canonical_name, 0.0)), numeric_value)
    return canonicalized


def add_direction_alias(canonical_name: str, alias: str) -> bool:
    alias_text = str(alias or "").strip()
    if not alias_text:
        return False

    normalized_canonical = normalize_direction_key(canonical_name)
    lexicon = load_lexicon()
    entry = lexicon.get(normalized_canonical)
    if entry is None:
        return False

    aliases = _dedupe_strings([*(entry.get("aliases", []) or []), alias_text])
    paper_terms = entry.get("paper_terms", []) or []
    entry["aliases"] = aliases
    entry["keywords"] = _dedupe_strings(paper_terms)
    lexicon[normalized_canonical] = entry
    return save_lexicon(lexicon)


def add_new_direction(
    direction_key: str,
    name: str,
    name_cn: str,
    keywords: Optional[List[str]] = None,
    *,
    aliases: Optional[List[str]] = None,
    paper_terms: Optional[List[str]] = None,
    source_text: str = "",
) -> bool:
    canonical_name = normalize_direction_key(direction_key)
    if not canonical_name:
        return False

    lexicon = load_lexicon()
    entry = _default_entry(
        canonical_name,
        name=name or canonical_name.replace("-", " ").title(),
        name_cn=name_cn or name or canonical_name.replace("-", " ").title(),
        aliases=_dedupe_strings([*(aliases or []), *(keywords or []), source_text]),
        paper_terms=_dedupe_strings([*(paper_terms or []), *(keywords or []), source_text]),
    )
    if source_text:
        entry["source_text"] = source_text
    lexicon[canonical_name] = entry
    return save_lexicon(lexicon)


def _load_pending_store() -> Dict[str, Dict[str, Any]]:
    if not PENDING_PATH.exists():
        return {}
    try:
        with PENDING_PATH.open("r", encoding="utf-8") as handle:
            raw = json.load(handle) or {}
    except Exception as exc:
        print(f"Failed to load pending direction store: {exc}")
        return {}
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if isinstance(value, dict)}


def _save_pending_store(store: Dict[str, Any]) -> bool:
    try:
        PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PENDING_PATH.open("w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2, ensure_ascii=False, sort_keys=True)
        return True
    except Exception as exc:
        print(f"Failed to save pending direction store: {exc}")
        return False


def load_pending_candidates() -> Dict[str, Dict[str, Any]]:
    return _load_pending_store()


def upsert_pending_direction_candidate(
    source_text: str,
    *,
    proposed_name: Optional[str] = None,
    proposed_name_cn: Optional[str] = None,
    confidence: float = 0.0,
    user_id: Optional[str] = None,
    reason: str = "",
) -> Dict[str, Any]:
    raw_source = str(source_text or "").strip()
    if not raw_source:
        raw_source = str(proposed_name_cn or proposed_name or "").strip()
    candidate_key = normalize_direction_key(proposed_name or raw_source)
    if not candidate_key:
        candidate_key = normalize_direction_key(proposed_name_cn or raw_source)
    if not candidate_key:
        raise ValueError("pending direction candidate requires a non-empty source text")

    store = _load_pending_store()
    existing = copy.deepcopy(store.get(candidate_key, {}))
    created_at = existing.get("created_at") or _now_iso()

    source_texts = _dedupe_strings([*(existing.get("source_texts", []) or []), raw_source])
    user_ids = _dedupe_strings([*(existing.get("user_ids", []) or []), str(user_id or "").strip()])

    candidate = {
        "candidate_key": candidate_key,
        "canonical_name": candidate_key,
        "name": str(proposed_name or existing.get("name") or candidate_key.replace("-", " ").title()).strip(),
        "name_cn": str(proposed_name_cn or existing.get("name_cn") or raw_source or candidate_key.replace("-", " ").title()).strip(),
        "source_texts": source_texts,
        "aliases": source_texts[:],
        "paper_terms": source_texts[:],
        "confidence": round(max(float(existing.get("confidence", 0.0)), float(confidence or 0.0)), 4),
        "reason": str(reason or existing.get("reason") or "").strip(),
        "created_at": created_at,
        "last_seen_at": _now_iso(),
        "seen_count": int(existing.get("seen_count", 0)) + 1,
        "user_ids": user_ids,
        "status": "pending",
    }

    store[candidate_key] = candidate
    _save_pending_store(store)
    return candidate


def find_pending_direction_candidate(query: str, *, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    normalized_query = _normalize_lookup_key(query)
    if not normalized_query:
        return None

    store = _load_pending_store()
    for candidate in store.values():
        user_ids = candidate.get("user_ids", []) or []
        if user_id and user_ids and str(user_id) not in user_ids:
            continue
        candidate_terms = [
            candidate.get("candidate_key"),
            candidate.get("name"),
            candidate.get("name_cn"),
            *(candidate.get("source_texts", []) or []),
        ]
        for term in candidate_terms:
            if _normalize_lookup_key(term) == normalized_query:
                return copy.deepcopy(candidate)
    return None


def confirm_pending_direction_candidate(query: str, *, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    candidate = find_pending_direction_candidate(query, user_id=user_id)
    if not candidate:
        return None

    canonical_name = candidate.get("canonical_name") or candidate.get("candidate_key")
    add_new_direction(
        direction_key=str(canonical_name),
        name=str(candidate.get("name") or canonical_name),
        name_cn=str(candidate.get("name_cn") or candidate.get("name") or canonical_name),
        aliases=list(candidate.get("source_texts", []) or []),
        paper_terms=list(candidate.get("paper_terms", []) or candidate.get("source_texts", []) or []),
        keywords=list(candidate.get("paper_terms", []) or candidate.get("source_texts", []) or []),
        source_text=str((candidate.get("source_texts") or [""])[0]),
    )

    store = _load_pending_store()
    candidate_key = str(candidate.get("candidate_key") or "")
    if candidate_key in store:
        store.pop(candidate_key, None)
        _save_pending_store(store)

    return get_direction_entry(str(canonical_name))


if __name__ == "__main__":
    registry = load_lexicon()
    print(f"Loaded {len(registry)} canonical directions")
