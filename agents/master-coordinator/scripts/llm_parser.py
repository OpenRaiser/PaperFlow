#!/usr/bin/env python3
"""
LLM Parser - 使用大语言模型解析用户意图

作为规则解析的兜底方案，处理：
1. 未注册的新研究方向
2. 未覆盖的自然语言句型
3. 复杂的语义理解
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from huggingface_hub import InferenceClient, get_token
except ImportError:
    InferenceClient = None
    get_token = None

try:
    import torch
except ImportError:
    torch = None

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError:
    AutoModelForCausalLM = None
    AutoTokenizer = None

LLM_FALLBACK_DISABLED = False
HF_LLM_DISABLED = False
LOCAL_LLM_DISABLED = False
LOCAL_LLM_DEVICE_OVERRIDE: Optional[str] = None
_LOCAL_LLM_CACHE: Dict[str, Dict[str, Any]] = {}


# 已知方向列表（用于 LLM 标准化）
KNOWN_DIRECTIONS = [
    "gui-agent", "multimodal-reasoning", "vision", "language",
    "machine-learning", "deep-learning", "reinforcement-learning",
    "reasoning", "agent", "optimization", "retrieval", "generation",
    "data-native", "bio-molecular", "science-discovery"
]

# 方向中文映射
DIRECTION_CN_MAP = {
    "gui-agent": "GUI Agent",
    "multimodal-reasoning": "多模态推理",
    "vision": "视觉",
    "language": "语言",
    "machine-learning": "机器学习",
    "deep-learning": "深度学习",
    "reinforcement-learning": "强化学习",
    "reasoning": "推理",
    "agent": "智能体",
    "optimization": "优化",
    "retrieval": "检索",
    "generation": "生成",
    "data-native": "数据原生",
    "bio-molecular": "生物分子",
    "science-discovery": "科学发现",
}


def _is_placeholder_openai_key(api_key: Optional[str]) -> bool:
    """Detect missing or obviously placeholder API keys."""
    normalized = (api_key or "").strip()
    if not normalized:
        return True

    placeholder_markers = [
        "your_openai_api_key",
        "your-key",
        "sk-xxxxxxxx",
        "sk-your",
        "replace_me",
        "placeholder",
    ]
    lowered = normalized.lower()
    if any(marker in lowered for marker in placeholder_markers):
        return True

    return not normalized.startswith("sk-")


def _get_first_env_value(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _should_prefer_dashscope_credentials(provider_hint: Optional[str] = None) -> bool:
    hint = str(provider_hint or "").strip().lower()
    if hint in {"dashscope", "aliyun", "bailian"}:
        return True

    base_url = _get_first_env_value("OPENAI_BASE_URL", "DASHSCOPE_BASE_URL").lower()
    return "dashscope.aliyuncs.com" in base_url


def _get_openai_client(timeout_override: Optional[float] = None) -> Optional[OpenAI]:
    """获取 OpenAI 客户端（如果可用）"""
    global LLM_FALLBACK_DISABLED

    if LLM_FALLBACK_DISABLED:
        return None

    if OpenAI is None:
        return None

    if _should_prefer_dashscope_credentials():
        api_key = _get_first_env_value("DASHSCOPE_API_KEY", "OPENAI_API_KEY")
        base_url = _get_first_env_value("DASHSCOPE_BASE_URL", "OPENAI_BASE_URL") or None
        raw_timeout = _get_first_env_value("DASHSCOPE_API_TIMEOUT", "OPENAI_API_TIMEOUT") or "60"
    else:
        api_key = _get_first_env_value("OPENAI_API_KEY", "DASHSCOPE_API_KEY")
        base_url = _get_first_env_value("OPENAI_BASE_URL", "DASHSCOPE_BASE_URL") or None
        raw_timeout = _get_first_env_value("OPENAI_API_TIMEOUT", "DASHSCOPE_API_TIMEOUT") or "60"
    if _is_placeholder_openai_key(api_key):
        return None
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = 60.0
    if timeout_override is not None:
        timeout = float(timeout_override)

    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)


def _is_placeholder_hf_token(api_key: Optional[str]) -> bool:
    normalized = str(api_key or "").strip().lower()
    if not normalized:
        return True

    return (
        "your_hf_token" in normalized
        or normalized.endswith("-here")
        or normalized == "hf_xxxxxxxxxxxxxxxxxxxx"
    )


def _looks_like_hf_user_token(api_key: Optional[str]) -> bool:
    return str(api_key or "").strip().lower().startswith("hf_")


def _looks_like_auth_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return any(
        token in message
        for token in (
            "401",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "invalid token",
            "authentication",
            "permission denied",
            "forbidden",
        )
    )


def _get_hf_llm_model() -> str:
    return os.environ.get("HF_LLM_MODEL", "Qwen/Qwen3-8B").strip() or "Qwen/Qwen3-8B"


def _get_reading_report_timeout() -> float:
    raw_timeout = os.environ.get("READING_REPORT_LLM_TIMEOUT", "").strip()
    if not raw_timeout:
        raw_timeout = _get_first_env_value("OPENAI_API_TIMEOUT", "HF_LLM_TIMEOUT", "HF_API_TIMEOUT") or "60"
    try:
        return max(30.0, float(raw_timeout))
    except ValueError:
        return 60.0


def _resolve_hf_provider(primary_env_name: str, fallback_env_name: str = "HF_INFERENCE_PROVIDER") -> str:
    primary = os.environ.get(primary_env_name, "").strip()
    if primary:
        return primary
    fallback = os.environ.get(fallback_env_name, "").strip()
    return fallback or "auto"


def _get_hf_llm_client() -> Optional[Any]:
    global HF_LLM_DISABLED

    if HF_LLM_DISABLED or InferenceClient is None:
        return None

    api_key = os.environ.get("HF_TOKEN") or os.environ.get("HF_API_KEY") or ""
    if _is_placeholder_hf_token(api_key):
        api_key = ""

    if not api_key and get_token is not None:
        try:
            api_key = get_token() or ""
        except Exception:
            api_key = ""

    if _is_placeholder_hf_token(api_key):
        return None

    provider_name = _resolve_hf_provider("HF_LLM_PROVIDER")
    if provider_name == "auto" and not _looks_like_hf_user_token(api_key):
        print(
            "HF LLM parser disabled: HF_LLM_PROVIDER/HF_INFERENCE_PROVIDER is set to auto, "
            "but the configured key is not a Hugging Face hf_ token. "
            "Set HF_LLM_PROVIDER to your actual provider name, for example nscale."
        )
        return None

    try:
        timeout = float(os.environ.get("HF_LLM_TIMEOUT", os.environ.get("HF_API_TIMEOUT", "60")))
    except ValueError:
        timeout = 60.0

    return InferenceClient(
        model=_get_hf_llm_model(),
        provider=provider_name,
        api_key=api_key,
        timeout=timeout,
    )


def _get_llm_parser_provider() -> str:
    """Return the configured parser backend provider."""
    provider = os.environ.get("LLM_PARSER_PROVIDER", "auto").strip().lower()
    if provider in {"none", "disabled", "off"}:
        return "disabled"
    if provider in {"dashscope", "aliyun", "bailian"}:
        return "openai"
    if provider in {"local", "openai", "hf_api", "huggingface", "huggingface_api", "hf-inference"}:
        if provider in {"huggingface", "huggingface_api", "hf-inference"}:
            return "hf_api"
        return provider
    return "auto"


def _get_local_llm_model_path() -> Optional[Path]:
    """Resolve the configured local generative model path."""
    raw_path = os.environ.get("LOCAL_LLM_MODEL_PATH", "").strip()
    if not raw_path:
        return None

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate if candidate.exists() else None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _should_fallback_local_llm_to_cpu_on_oom() -> bool:
    return _env_flag("LOCAL_LLM_FALLBACK_TO_CPU_ON_OOM", True)


def _is_cuda_oom_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        "cuda out of memory" in message
        or ("out of memory" in message and "cuda" in message)
        or "cudnn_status_not_supported" in message
    )


def _clear_cuda_cache() -> None:
    if torch is None or not hasattr(torch, "cuda"):
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _resolve_local_llm_device(force_device: Optional[str] = None) -> str:
    preferred = (force_device or LOCAL_LLM_DEVICE_OVERRIDE or os.environ.get("LOCAL_LLM_DEVICE", "auto")).strip().lower()
    if preferred in {"cuda", "gpu"} and torch is not None and torch.cuda.is_available():
        return "cuda"
    if preferred == "cpu":
        return "cpu"
    if torch is not None and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _local_llm_cache_key(model_path: Path, device: str) -> str:
    return f"{model_path}::{device}"


def _evict_local_llm_backend(cache_key: Optional[str]) -> None:
    if not cache_key:
        return

    backend = _LOCAL_LLM_CACHE.pop(cache_key, None)
    if not backend:
        return

    model = backend.get("model")
    device = str(backend.get("device") or "")
    if model is not None and device == "cuda":
        try:
            model.to("cpu")
        except Exception:
            pass

    _clear_cuda_cache()


def _is_embedding_style_checkpoint(model_path: Path) -> bool:
    """Detect sentence-transformer / embedding checkpoints that should not be used for generation."""
    if re.search(r"(embedding|reranker)", model_path.name, flags=re.IGNORECASE):
        return True

    modules_path = model_path / "modules.json"
    if not modules_path.exists():
        return False

    try:
        modules = json.loads(modules_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    if not isinstance(modules, list):
        return False

    module_types = {str(item.get("type", "")) for item in modules if isinstance(item, dict)}
    return any(
        marker in module_type
        for module_type in module_types
        for marker in ("sentence_transformers.models.Pooling", "sentence_transformers.models.Normalize")
    )


def _has_minimum_local_llm_files(model_path: Path) -> bool:
    """Check whether a local model directory looks complete enough for generation loading."""
    required_any = [
        model_path / "config.json",
        model_path / "tokenizer_config.json",
    ]
    if not all(path.exists() for path in required_any):
        return False

    weight_candidates = [
        model_path / "model.safetensors",
        model_path / "pytorch_model.bin",
    ]
    if any(path.exists() for path in weight_candidates):
        return True

    if list(model_path.glob("model-*.safetensors")):
        return True
    if list(model_path.glob("pytorch_model-*.bin")):
        return True

    return False


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from a model response."""
    normalized = str(text or "").strip()
    if not normalized:
        return None

    normalized = re.sub(r"<think>.*?</think>", "", normalized, flags=re.IGNORECASE | re.DOTALL).strip()
    normalized = re.sub(r"^```(?:json)?\s*", "", normalized, flags=re.IGNORECASE).strip()
    normalized = re.sub(r"\s*```$", "", normalized).strip()

    try:
        parsed = json.loads(normalized)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    start = normalized.find("{")
    end = normalized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(normalized[start:end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


_DIRECTION_DISPLAY_MAP = {
    "gui-agent": "GUI Agent",
    "multimodal-reasoning": "Multimodal Reasoning",
    "vision": "Vision",
    "language": "Language",
    "machine-learning": "Machine Learning",
    "deep-learning": "Deep Learning",
    "reinforcement-learning": "Reinforcement Learning",
    "reasoning": "Reasoning",
    "agent": "Agent",
    "optimization": "Optimization",
    "retrieval": "Retrieval",
    "generation": "Generation",
    "data-native": "Data Native",
    "bio-molecular": "Bio Molecular",
    "science-discovery": "Science Discovery",
}

_DIRECTION_GENERIC_TERMS = {
    "direction",
    "directions",
    "topic",
    "topics",
    "area",
    "areas",
    "field",
    "fields",
    "interest",
    "interests",
    "research",
    "方向",
    "研究方向",
    "主题",
    "领域",
    "兴趣",
}


def _normalize_direction_key(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    normalized = normalized.replace("&", " and ")
    normalized = normalized.replace("/", " ")
    normalized = re.sub(r"[_\s]+", "-", normalized)
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff\-]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def _get_direction_parser_timeout() -> float:
    raw_timeout = (
        _get_first_env_value("LLM_PARSER_DIRECTION_TIMEOUT", "SCITASTE_DIRECTION_LLM_TIMEOUT")
        or "18"
    )
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = 18.0
    return min(60.0, max(5.0, timeout))


def _looks_like_explicit_direction_description(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "direction:",
        "directions:",
        "topic:",
        "topics:",
        "研究方向",
        "方向：",
        "方向:",
        "感兴趣",
        "interested in",
        "focus on",
        "working on",
        "关注",
        "聚焦",
        "方向是",
        "领域是",
    )
    return any(marker in lowered for marker in markers) or any(
        delimiter in lowered for delimiter in (",", "，", ";", "；", "、", "/", "\n")
    )


def _build_direction_alias_map(lexicon: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    alias_map: Dict[str, Dict[str, Any]] = {}

    def register(alias: Any, payload: Dict[str, Any]) -> None:
        alias_key = _normalize_direction_key(alias)
        if alias_key:
            alias_map.setdefault(alias_key, payload)

    for direction_key in KNOWN_DIRECTIONS:
        payload = {
            "name": direction_key,
            "name_cn": _DIRECTION_DISPLAY_MAP.get(direction_key, direction_key.replace("-", " ").title()),
            "is_known": True,
            "_auto_learn": False,
        }
        register(direction_key, payload)
        register(direction_key.replace("-", " "), payload)
        register(_DIRECTION_DISPLAY_MAP.get(direction_key, ""), payload)

    for direction_key, data in (lexicon or {}).items():
        payload = {
            "name": _normalize_direction_key(data.get("canonical_name") or direction_key) or str(direction_key),
            "name_cn": str(data.get("name_cn") or data.get("name") or direction_key),
            "is_known": True,
            "_auto_learn": False,
        }
        register(direction_key, payload)
        register(data.get("name"), payload)
        register(data.get("name_cn"), payload)
        register(data.get("canonical_name"), payload)
        for alias in data.get("aliases", []) or []:
            register(alias, payload)
        for keyword in data.get("paper_terms", []) or []:
            register(keyword, payload)
        for keyword in data.get("keywords", []) or []:
            register(keyword, payload)

    return alias_map


def _clean_direction_candidate(candidate: Any) -> str:
    value = str(candidate or "").strip()
    if not value:
        return ""

    value = re.sub(r"^[`'\"“”‘’]+|[`'\"“”‘’]+$", "", value)
    value = re.sub(
        r"^(?:direction|directions|topic|topics|area|areas|field|fields|研究方向|方向|主题|领域)\s*[:：]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"^(?:我最近|最近|目前|现在|主要|比较|更|想|正在|在|做|研究|关注|聚焦|偏向|对)\s*",
        "",
        value,
    )
    value = re.sub(
        r"(?:更?感兴趣了?|感兴趣|有兴趣|比较关注|方向上|方向|领域|主题|相关研究|相关方向)$",
        "",
        value,
    )
    value = re.sub(r"\s+", " ", value).strip(" ,.;:，；、/\\-")
    lowered = value.lower()
    if not value or lowered in _DIRECTION_GENERIC_TERMS:
        return ""
    if len(value) < 2 or len(value) > 80:
        return ""
    return value


def _extract_direction_candidates_fast(text: str, alias_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return []

    candidate_sources: List[str] = []
    explicit_patterns = [
        r"(?:direction|directions|topic|topics|area|areas|field|fields|研究方向|方向|主题|领域)\s*[:：]\s*(.+)",
        r"(?:我最近|最近|目前|现在|我)?(?:对|关注|聚焦)\s*(.+?)\s*(?:更?感兴趣了?|感兴趣|有兴趣|比较关注|$)",
        r"(?:working on|focus on|interested in)\s+(.+)$",
    ]
    for pattern in explicit_patterns:
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            captured = str(match.group(1) or "").strip()
            if captured:
                candidate_sources.append(captured)

    if not candidate_sources:
        candidate_sources.append(normalized_text)

    split_pattern = r"(?:,|，|;|；|、|\band\b|\bor\b|以及|和|与|\+|/|\n)+"
    seen: set[str] = set()
    directions: List[Dict[str, Any]] = []

    for source in candidate_sources:
        for fragment in re.split(split_pattern, source, flags=re.IGNORECASE):
            candidate = _clean_direction_candidate(fragment)
            if not candidate:
                continue

            normalized_candidate = _normalize_direction_key(candidate)
            if not normalized_candidate or normalized_candidate in seen:
                continue
            seen.add(normalized_candidate)

            matched = alias_map.get(normalized_candidate)
            if matched is not None:
                directions.append(
                    {
                        "name": matched["name"],
                        "name_cn": matched["name_cn"],
                        "confidence": 0.82,
                        "source_text": candidate,
                        "is_known": True,
                        "_auto_learn": False,
                    }
                )
                continue

            directions.append(
                {
                    "name": normalized_candidate,
                    "name_cn": candidate if re.search(r"[\u4e00-\u9fff]", candidate) else candidate.title(),
                    "confidence": 0.58,
                    "source_text": candidate,
                    "is_known": False,
                    "_auto_learn": False,
                }
            )

    return directions[:3]


def _normalize_direction_results(
    directions: List[Dict[str, Any]],
    alias_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    normalized_directions: List[Dict[str, Any]] = []
    seen_names: set[str] = set()

    for direction in directions:
        if not isinstance(direction, dict):
            continue

        raw_name = direction.get("name") or direction.get("name_cn") or direction.get("source_text")
        normalized_name = _normalize_direction_key(raw_name)
        if not normalized_name or normalized_name in seen_names:
            continue

        matched = alias_map.get(normalized_name)
        try:
            confidence = float(direction.get("confidence", 0.6))
        except (TypeError, ValueError):
            confidence = 0.6
        confidence = max(0.0, min(1.0, confidence))

        normalized_direction = {
            "name": matched["name"] if matched else normalized_name,
            "name_cn": str(
                direction.get("name_cn")
                or (matched["name_cn"] if matched else raw_name or normalized_name)
            ).strip(),
            "confidence": confidence,
            "source_text": str(direction.get("source_text") or raw_name or "").strip(),
            "is_known": bool(direction.get("is_known", matched is not None)),
            "_auto_learn": bool(direction.get("_auto_learn", matched is None)),
        }

        seen_names.add(normalized_direction["name"])
        normalized_directions.append(normalized_direction)

    return normalized_directions[:3]


def normalize_research_directions(
    text: str,
    *,
    auto_persist_known_aliases: bool = True,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Normalize free-form user direction text into canonical directions.

    Returns:
        {
            "canonical_directions": [...],
            "temporary_matches": [...],
            "pending_candidates": [...],
            "explanations": [...],
        }
    """
    from config.direction_lexicon import (
        add_direction_alias,
        get_direction_entry,
        load_lexicon,
        resolve_canonical_direction,
        upsert_pending_direction_candidate,
    )

    lexicon = load_lexicon()
    alias_map = _build_direction_alias_map(lexicon)
    heuristic_candidates = _normalize_direction_results(
        _extract_direction_candidates_fast(text, alias_map),
        alias_map,
    )

    if heuristic_candidates and (
        _looks_like_explicit_direction_description(text) or len(heuristic_candidates) >= 2
    ):
        final_directions = heuristic_candidates
    else:
        known_directions = [
            _DIRECTION_DISPLAY_MAP.get(direction_key, direction_key.replace("-", " ").title())
            for direction_key in KNOWN_DIRECTIONS
        ] + [
            str(data.get("name_cn") or data.get("name") or "").strip()
            for data in lexicon.values()
            if str(data.get("name_cn") or data.get("name") or "").strip()
        ]

        candidate_hint = ""
        if heuristic_candidates:
            candidate_hint = "Fast candidate phrases: " + ", ".join(
                direction.get("source_text") or direction.get("name_cn") or direction.get("name")
                for direction in heuristic_candidates
            )

        system_prompt = (
            "You extract up to 3 research directions from a user's self-description.\n"
            "Keep multi-word phrases intact and prefer specific topics over broad umbrellas.\n"
            "Do not split phrases like 'protein language model' or 'world model for epidemiology'.\n"
            f"Known directions include: {', '.join(known_directions[:40])}.\n"
            f"{candidate_hint}\n"
            "Return JSON only in this format:\n"
            "{\n"
            '  "directions": [\n'
            "    {\n"
            '      "name": "english-kebab-case-or-best-normalized-name",\n'
            '      "name_cn": "Chinese display name",\n'
            '      "confidence": 0.0,\n'
            '      "source_text": "matched phrase from the user text",\n'
            '      "is_known": true\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "If the user names a new direction, still extract it.\n"
            "Return at most 3 directions."
        )

        result = _generate_json_with_configured_llm(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=160,
            timeout_override=_get_direction_parser_timeout(),
        )
        llm_directions = (
            _normalize_direction_results(result.get("directions", []), alias_map)
            if isinstance(result, dict)
            else []
        )

        final_directions = []
        seen_names: set[str] = set()
        for bucket in (llm_directions, heuristic_candidates):
            for direction in bucket:
                name = str(direction.get("name") or "").strip()
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                final_directions.append(direction)
                if len(final_directions) >= 3:
                    break
            if len(final_directions) >= 3:
                break

    normalized_input = re.sub(r"\s+", " ", str(text or "").strip())
    token_count = len(re.findall(r"[\w\u4e00-\u9fff]+", normalized_input, flags=re.UNICODE))
    if not final_directions and normalized_input and token_count <= 10 and len(normalized_input) <= 80:
        pending = upsert_pending_direction_candidate(
            normalized_input,
            proposed_name=normalized_input,
            proposed_name_cn=normalized_input,
            confidence=0.0,
            user_id=user_id,
            reason="parser_fallback_pending",
        )
        return {
            "canonical_directions": [],
            "temporary_matches": [],
            "pending_candidates": [pending],
            "explanations": [
                f"发现候选新方向：{pending['name_cn']}，回复“确认方向：{pending['name_cn']}”后纳入统一方向库。"
            ],
        }

    canonical_directions: List[Dict[str, Any]] = []
    temporary_matches: List[Dict[str, Any]] = []
    pending_candidates: List[Dict[str, Any]] = []
    explanations: List[str] = []
    seen_canonical: set[str] = set()
    seen_pending: set[str] = set()

    for direction in final_directions:
        raw_name = str(direction.get("name") or "").strip()
        source_text = str(direction.get("source_text") or direction.get("name_cn") or raw_name).strip()
        try:
            confidence = max(0.0, min(1.0, float(direction.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0

        source_resolution = resolve_canonical_direction(
            source_text,
            lexicon=lexicon,
            include_paper_terms=True,
        )
        target_resolution = resolve_canonical_direction(
            raw_name,
            lexicon=lexicon,
            include_paper_terms=True,
        ) or source_resolution

        if target_resolution:
            canonical_name = target_resolution["canonical_name"]
            known_by_source = bool(
                source_resolution and source_resolution["canonical_name"] == canonical_name
            )

            if known_by_source or confidence >= 0.60:
                entry = get_direction_entry(canonical_name, lexicon=lexicon) or target_resolution["entry"]
                if canonical_name not in seen_canonical:
                    seen_canonical.add(canonical_name)
                    canonical_directions.append(
                        {
                            "name": canonical_name,
                            "name_cn": str(entry.get("name_cn") or entry.get("name") or canonical_name),
                            "confidence": round(confidence, 4),
                            "source_text": source_text,
                            "is_known": True,
                        }
                    )

            if not known_by_source and source_text:
                display_name = str(
                    (get_direction_entry(canonical_name, lexicon=lexicon) or {}).get("name_cn")
                    or canonical_name
                )
                if confidence >= 0.85:
                    if auto_persist_known_aliases and add_direction_alias(canonical_name, source_text):
                        lexicon = load_lexicon()
                    explanations.append(f"已将“{source_text}”归一为“{display_name}”。")
                elif confidence >= 0.60:
                    temporary_matches.append(
                        {
                            "source_text": source_text,
                            "canonical_name": canonical_name,
                            "canonical_display_name": display_name,
                            "confidence": round(confidence, 4),
                        }
                    )
                    explanations.append(f"本轮已将“{source_text}”临时归一为“{display_name}”。")
                else:
                    pending = upsert_pending_direction_candidate(
                        source_text,
                        proposed_name=raw_name or source_text,
                        proposed_name_cn=direction.get("name_cn") or source_text,
                        confidence=confidence,
                        user_id=user_id,
                        reason="low_confidence_alias_mapping",
                    )
                    if pending["candidate_key"] not in seen_pending:
                        seen_pending.add(pending["candidate_key"])
                        pending_candidates.append(pending)
                        explanations.append(
                            f"发现候选新方向：{pending['name_cn']}，回复“确认方向：{pending['name_cn']}”后纳入统一方向库。"
                        )
            continue

        pending = upsert_pending_direction_candidate(
            source_text or raw_name,
            proposed_name=raw_name or source_text,
            proposed_name_cn=direction.get("name_cn") or source_text or raw_name,
            confidence=confidence,
            user_id=user_id,
            reason="novel_direction_candidate",
        )
        if pending["candidate_key"] not in seen_pending:
            seen_pending.add(pending["candidate_key"])
            pending_candidates.append(pending)
            explanations.append(
                f"发现候选新方向：{pending['name_cn']}，回复“确认方向：{pending['name_cn']}”后纳入统一方向库。"
            )

    return {
        "canonical_directions": canonical_directions[:3],
        "temporary_matches": temporary_matches[:3],
        "pending_candidates": pending_candidates[:3],
        "explanations": explanations[:6],
    }


def _get_local_llm_backend(force_device: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load a local causal LM backend for parser inference."""
    global LOCAL_LLM_DISABLED, LOCAL_LLM_DEVICE_OVERRIDE

    if LOCAL_LLM_DISABLED:
        return None

    if torch is None or AutoTokenizer is None or AutoModelForCausalLM is None:
        return None

    model_path = _get_local_llm_model_path()
    if model_path is None:
        return None

    if not _has_minimum_local_llm_files(model_path):
        return None

    if _is_embedding_style_checkpoint(model_path):
        print(
            "Local LLM parser disabled: LOCAL_LLM_MODEL_PATH points to an embedding/reranker checkpoint, "
            "not a generative instruct model."
        )
        LOCAL_LLM_DISABLED = True
        return None

    device = _resolve_local_llm_device(force_device)
    cache_key = _local_llm_cache_key(model_path, device)
    if cache_key in _LOCAL_LLM_CACHE:
        return _LOCAL_LLM_CACHE[cache_key]

    trust_remote_code = os.environ.get("LOCAL_LLM_TRUST_REMOTE_CODE", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_path),
            trust_remote_code=trust_remote_code,
        )
        if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
            tokenizer.pad_token = tokenizer.eos_token

        model_kwargs: Dict[str, Any] = {
            "trust_remote_code": trust_remote_code,
            "low_cpu_mem_usage": True,
        }
        if device == "cuda":
            model_kwargs["torch_dtype"] = torch.float16

        model = AutoModelForCausalLM.from_pretrained(str(model_path), **model_kwargs)
        if device == "cuda":
            model = model.to(device)
        model.eval()
    except Exception as e:
        if device == "cuda" and _is_cuda_oom_error(e) and _should_fallback_local_llm_to_cpu_on_oom():
            print("Local LLM initialization hit CUDA OOM; retrying on CPU.")
            LOCAL_LLM_DEVICE_OVERRIDE = "cpu"
            _clear_cuda_cache()
            return _get_local_llm_backend(force_device="cpu")
        print(f"Local LLM initialization error: {e}")
        LOCAL_LLM_DISABLED = True
        return None

    backend = {
        "tokenizer": tokenizer,
        "model": model,
        "device": device,
        "path": str(model_path),
        "cache_key": cache_key,
    }
    _LOCAL_LLM_CACHE[cache_key] = backend
    return backend


def _generate_json_with_local_llm(
    system_prompt: str,
    user_text: str,
    max_new_tokens: int = 512,
    *,
    allow_cpu_retry: bool = True,
) -> Optional[Dict[str, Any]]:
    """Generate a JSON response from a local causal LM."""
    global LOCAL_LLM_DEVICE_OVERRIDE

    backend = _get_local_llm_backend()
    if backend is None or torch is None:
        return None

    tokenizer = backend["tokenizer"]
    model = backend["model"]
    device = backend["device"]
    cache_key = backend.get("cache_key")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    try:
        if hasattr(tokenizer, "apply_chat_template"):
            prompt_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = tokenizer(prompt_text, return_tensors="pt")
        else:
            prompt_text = f"System: {system_prompt}\nUser: {user_text}\nAssistant:"
            inputs = tokenizer(prompt_text, return_tensors="pt")

        if device == "cuda":
            inputs = {key: value.to(device) for key, value in inputs.items()}

        with torch.inference_mode():
            outputs = model.generate(
                **inputs,
                max_new_tokens=int(max_new_tokens),
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )

        prompt_length = inputs["input_ids"].shape[-1]
        generated_ids = outputs[0][prompt_length:]
        generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        return _extract_json_object(generated_text)
    except Exception as e:
        if device == "cuda" and _is_cuda_oom_error(e):
            _clear_cuda_cache()
            if allow_cpu_retry and _should_fallback_local_llm_to_cpu_on_oom():
                print("Local LLM parsing hit CUDA OOM; switching to CPU fallback.")
                LOCAL_LLM_DEVICE_OVERRIDE = "cpu"
                _evict_local_llm_backend(cache_key)
                return _generate_json_with_local_llm(
                    system_prompt,
                    user_text,
                    max_new_tokens=max_new_tokens,
                    allow_cpu_retry=False,
                )
            _evict_local_llm_backend(cache_key)
            LOCAL_LLM_DEVICE_OVERRIDE = "cpu"
            print("Local LLM parsing skipped after CUDA OOM; using heuristic fallback.")
            return None
        print(f"Local LLM parsing error: {e}")
        return None
    finally:
        if device == "cuda":
            _clear_cuda_cache()


def _coerce_hf_message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        fragments: List[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    fragments.append(item.strip())
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("value")
                if text:
                    fragments.append(str(text).strip())
                continue
            text = getattr(item, "text", None) or getattr(item, "content", None)
            if text:
                fragments.append(str(text).strip())
        return "\n".join(fragment for fragment in fragments if fragment).strip()

    return str(content or "").strip()


def _extract_hf_generation_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()

    generated_text = getattr(response, "generated_text", None)
    if generated_text:
        return str(generated_text).strip()

    return str(response or "").strip()


def _build_hf_generation_prompt(system_prompt: str, user_text: str) -> str:
    return (
        f"{system_prompt}\n\n"
        "请直接返回一个 JSON 对象，不要输出解释、思考过程、Markdown 代码块或额外文本。\n"
        "如果你是 Qwen 系列模型，请使用 no-think 模式。\n\n"
        f"用户输入：\n{user_text}\n\n"
        "/no_think\n"
        "JSON:\n"
    )


def _generate_json_with_hf_api(system_prompt: str, user_text: str, max_tokens: int = 500) -> Optional[Dict[str, Any]]:
    """Generate a JSON response from Hugging Face Inference API."""
    global HF_LLM_DISABLED

    client = _get_hf_llm_client()
    if client is None:
        return None

    model = _get_hf_llm_model()
    messages = [
        {
            "role": "system",
            "content": (
                f"{system_prompt}\n\n"
                "你必须只返回一个 JSON 对象，不要输出解释、代码块或额外文本。"
            ),
        },
        {
            "role": "user",
            "content": f"/no_think\n{user_text}",
        },
    ]

    try:
        response = client.chat_completion(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        text = _coerce_hf_message_content_to_text(response.choices[0].message.content)
        parsed = _extract_json_object(text)
        if parsed is not None:
            return parsed
    except Exception as exc:
        if _looks_like_auth_error(exc):
            HF_LLM_DISABLED = True
            print(f"HF LLM auth error: {exc}")
            return None
        print(f"HF chat completion error: {exc}")

    try:
        response = client.text_generation(
            _build_hf_generation_prompt(system_prompt, user_text),
            model=model,
            max_new_tokens=int(max_tokens),
            do_sample=False,
            return_full_text=False,
        )
        return _extract_json_object(_extract_hf_generation_text(response))
    except Exception as exc:
        if _looks_like_auth_error(exc):
            HF_LLM_DISABLED = True
            print(f"HF LLM auth error: {exc}")
            return None
        print(f"HF text generation error: {exc}")
        return None


def _generate_json_with_openai(
    system_prompt: str,
    user_text: str,
    max_tokens: int = 500,
    timeout_override: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Generate a JSON response from OpenAI."""
    client = (
        _get_openai_client(timeout_override=timeout_override)
        if timeout_override is not None
        else _get_openai_client()
    )
    if client is None:
        return None

    model = _get_first_env_value("LLM_PARSER_OPENAI_MODEL", "DASHSCOPE_LLM_MODEL") or "gpt-4o-mini"
    messages = [
        {
            "role": "system",
            "content": (
                f"{system_prompt}\n\n"
                "你必须只返回一个 JSON 对象，不要输出解释、代码块、思考过程或额外文本。"
            ),
        },
        {"role": "user", "content": user_text},
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=max_tokens,
        )
        return _extract_json_object(response.choices[0].message.content)
    except Exception as e:
        if any(token in str(e).lower() for token in ["response_format", "json_object", "unsupported", "not support"]):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0,
                    max_tokens=max_tokens,
                )
                return _extract_json_object(response.choices[0].message.content)
            except Exception as retry_exc:
                e = retry_exc
        if any(token in str(e).lower() for token in ["401", "unauthorized", "invalid api key", "incorrect api key"]):
            global LLM_FALLBACK_DISABLED
            LLM_FALLBACK_DISABLED = True
        print(f"LLM parsing error: {e}")
        return None


def _generate_json_with_configured_llm(
    system_prompt: str,
    user_text: str,
    max_tokens: int,
    timeout_override: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Generate a JSON response using the configured parser backend."""
    provider = _get_llm_parser_provider()
    if provider == "disabled":
        return None

    if provider in {"local", "auto"}:
        local_result = _generate_json_with_local_llm(
            system_prompt,
            user_text,
            max_new_tokens=max_tokens,
        )
        if local_result is not None or provider == "local":
            return local_result

    if provider in {"hf_api", "auto"}:
        hf_result = _generate_json_with_hf_api(system_prompt, user_text, max_tokens=max_tokens)
        if hf_result is not None or provider == "hf_api":
            return hf_result

    if provider in {"openai", "auto"}:
        return _generate_json_with_openai(
            system_prompt,
            user_text,
            max_tokens=max_tokens,
            timeout_override=timeout_override,
        )

    return None


def parse_intent_with_llm(text: str, known_topics: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """
    使用 LLM 解析用户意图

    Args:
        text: 用户输入文本

    Returns:
        解析结果字典，如果失败则返回 None
    """
    known_topics = [str(topic).strip() for topic in (known_topics or []) if str(topic).strip()]
    known_topics_block = ""
    if known_topics:
        known_topics_block = (
            "\n当前用户画像里已经存在的方向/主题有："
            + "，".join(known_topics[:20])
            + "。\n如果用户明显是在修正这些已有方向之一，请优先返回那个具体方向，不要泛化成更宽的概念。"
        )

    system_prompt = """你是一个学术画像解析助手。你的任务是解析用户对学术兴趣方向的描述，提取结构化信息。
请特别注意否定、纠正、转折和语气词。
只要用户表达“不感兴趣 / 不需要 / 去掉 / 移除 / 降低 / 别推 / 不想看”，就优先理解为负向调整，而不是正向兴趣。
不要因为用户提到了一个主题，就默认他对这个主题感兴趣。
像“GUI Agent”“Cold Start”“protein language model”这种短语必须保持为完整主题，不要拆成多个词。

示例：
- “我对 GUI Agent 不感兴趣” -> action=adjust_interest, direction=decrease, topics=["GUI Agent"]
- “不是不喜欢，只是最近没时间” -> action=unknown
- “我最近对 protein language model 更感兴趣了” -> action=adjust_interest, direction=increase, topics=["protein language model"]
""" + known_topics_block + """

请分析用户输入，返回以下 JSON 格式：
{
    "action": "adjust_interest" | "adjust_weight" | "add_must_read" | "remove_must_read" | "unknown",
    "direction": "increase" | "decrease" | null,
    "topics": ["识别出的研究方向或主题列表"],
    "confidence": 0.0-1.0,
    "reasoning": "简短的推理说明"
}

已知研究方向包括：""" + ", ".join(DIRECTION_CN_MAP.values()) + """

如果用户提到新的研究方向（不在已知列表中），也请提取出来，后续系统会自动学习。
如果用户只是表达时间安排、阅读节奏或临时没空，而不是在修正画像，请返回 unknown。

只返回 JSON，不要其他内容。"""

    result = _generate_json_with_configured_llm(
        system_prompt=system_prompt,
        user_text=text,
        max_tokens=200,
    )
    if not isinstance(result, dict):
        return None

    if result.get("confidence", 0) < 0.5:
        return None

    valid_actions = {"adjust_interest", "adjust_weight", "add_must_read", "remove_must_read", "unknown"}
    if result.get("action") not in valid_actions:
        return None

    if isinstance(result.get("topics"), list):
        result["topics"] = [str(topic).strip() for topic in result["topics"] if str(topic).strip()]

    return result


def parse_research_directions(text: str, auto_learn: bool = True) -> List[Dict[str, Any]]:
    """
    使用 LLM 从文本中识别研究方向

    Args:
        text: 用户输入文本
        auto_learn: 是否自动学习新方向到词典

    Returns:
        研究方向列表 [{"name": "...", "confidence": 0.x}, ...]
    """
    # 加载已知方向列表
    from config.direction_lexicon import load_lexicon

    lexicon = load_lexicon()
    alias_map = _build_direction_alias_map(lexicon)
    heuristic_candidates = _normalize_direction_results(
        _extract_direction_candidates_fast(text, alias_map),
        alias_map,
    )

    if heuristic_candidates and (
        _looks_like_explicit_direction_description(text) or len(heuristic_candidates) >= 2
    ):
        return [
            {key: value for key, value in direction.items() if not key.startswith("_")}
            for direction in heuristic_candidates
        ]

    known_directions = [
        _DIRECTION_DISPLAY_MAP.get(direction_key, direction_key.replace("-", " ").title())
        for direction_key in KNOWN_DIRECTIONS
    ] + [
        str(data.get("name_cn") or data.get("name") or "").strip()
        for data in lexicon.values()
        if str(data.get("name_cn") or data.get("name") or "").strip()
    ]

    candidate_hint = ""
    if heuristic_candidates:
        candidate_hint = "Fast candidate phrases: " + ", ".join(
            direction.get("source_text") or direction.get("name_cn") or direction.get("name")
            for direction in heuristic_candidates
        )

    system_prompt = (
        "You extract up to 3 research directions from a user's self-description.\n"
        "Keep multi-word phrases intact and prefer specific topics over broad umbrellas.\n"
        "Do not split phrases like 'protein language model' or 'world model for epidemiology'.\n"
        f"Known directions include: {', '.join(known_directions[:40])}.\n"
        f"{candidate_hint}\n"
        "Return JSON only in this format:\n"
        "{\n"
        '  "directions": [\n'
        "    {\n"
        '      "name": "english-kebab-case-or-best-normalized-name",\n'
        '      "name_cn": "Chinese display name",\n'
        '      "confidence": 0.0,\n'
        '      "source_text": "matched phrase from the user text",\n'
        '      "is_known": true\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "If the user names a new direction, still extract it.\n"
        "Return at most 3 directions."
    )

    result = _generate_json_with_configured_llm(
        system_prompt=system_prompt,
        user_text=text,
        max_tokens=160,
        timeout_override=_get_direction_parser_timeout(),
    )
    llm_directions = _normalize_direction_results(result.get("directions", []), alias_map) if isinstance(result, dict) else []

    final_directions: List[Dict[str, Any]] = []
    seen_names: set[str] = set()
    for bucket in (llm_directions, heuristic_candidates):
        for direction in bucket:
            name = str(direction.get("name") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            final_directions.append(direction)
            if len(final_directions) >= 3:
                break
        if len(final_directions) >= 3:
            break

    if not final_directions:
        return []

    # 自动学习新方向
    if auto_learn:
        new_directions = [direction for direction in final_directions if direction.get("_auto_learn")]
        for direction in new_directions:
            _learn_new_direction(direction, text)

    return [
        {key: value for key, value in direction.items() if not key.startswith("_")}
        for direction in final_directions
    ]


def parse_research_directions(text: str, auto_learn: bool = True) -> List[Dict[str, Any]]:
    """
    Return canonical directions only.

    Unknown directions are kept in the pending store until the user confirms them.
    """
    normalized = normalize_research_directions(
        text,
        auto_persist_known_aliases=auto_learn,
    )
    return [
        {
            "name": direction.get("name"),
            "name_cn": direction.get("name_cn"),
            "confidence": direction.get("confidence", 0.0),
            "source_text": direction.get("source_text", ""),
            "is_known": direction.get("is_known", True),
        }
        for direction in normalized.get("canonical_directions", [])
    ]


def _truncate_prompt_text(text: Any, max_chars: int) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    clipped = normalized[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:") or normalized[: max_chars - 1]
    return f"{clipped}…"


def _clean_generated_list(value: Any, limit: int = 4) -> List[str]:
    if isinstance(value, str):
        candidates = re.split(r"\n+|[;；]+", value)
    elif isinstance(value, list):
        candidates = [str(item) for item in value]
    else:
        return []

    cleaned: List[str] = []
    for candidate in candidates:
        item = re.sub(r"^\s*[-*•\d\.\)\(]+\s*", "", str(candidate)).strip()
        if len(item) >= 4:
            cleaned.append(_truncate_prompt_text(item, 180))
    return cleaned[:limit]


def _summarize_retrieved_evidence_for_prompt(
    heuristic_payload: Optional[Dict[str, Any]],
    *,
    items_per_bucket: int = 2,
    max_chars: int = 240,
) -> Dict[str, Any]:
    heuristic_payload = heuristic_payload or {}
    retrieved_evidence = heuristic_payload.get("retrieved_evidence") or {}
    if not isinstance(retrieved_evidence, dict):
        return {}

    matches = retrieved_evidence.get("matches") or {}
    if not isinstance(matches, dict):
        return {}

    summary: Dict[str, Any] = {}
    descriptor = str(retrieved_evidence.get("descriptor") or "").strip()
    chunk_count = retrieved_evidence.get("chunk_count")
    if descriptor:
        summary["descriptor"] = descriptor
    if isinstance(chunk_count, int) and chunk_count > 0:
        summary["chunk_count"] = chunk_count

    buckets: Dict[str, List[str]] = {}
    for bucket in ("background", "method", "results", "limitations", "relevance"):
        bucket_matches = matches.get(bucket) or []
        if not isinstance(bucket_matches, list):
            continue

        items: List[str] = []
        for match in bucket_matches[:items_per_bucket]:
            if not isinstance(match, dict):
                continue
            section = str(match.get("section") or "").strip() or "pdf"
            score = match.get("score")
            score_text = ""
            if isinstance(score, (int, float)):
                score_text = f" score={float(score):.3f}"
            text = _truncate_prompt_text(match.get("text"), max_chars)
            if not text:
                continue
            items.append(f"[{section}{score_text}] {text}")

        if items:
            buckets[bucket] = items

    if buckets:
        summary["matches"] = buckets
    return summary


def _summarize_field_evidence_map_for_prompt(
    heuristic_payload: Optional[Dict[str, Any]],
    *,
    items_per_field: int = 2,
    max_chars: int = 220,
) -> Dict[str, List[str]]:
    heuristic_payload = heuristic_payload or {}
    field_evidence_map = heuristic_payload.get("field_evidence_map") or {}
    if not isinstance(field_evidence_map, dict):
        return {}

    summary: Dict[str, List[str]] = {}
    for field in (
        "one_sentence_summary",
        "research_background",
        "core_method",
        "key_results",
        "main_contributions",
        "limitations",
        "relevance_points",
        "reading_focus",
    ):
        values = field_evidence_map.get(field) or []
        if not isinstance(values, list):
            continue
        items = [_truncate_prompt_text(value, max_chars) for value in values[:items_per_field] if str(value).strip()]
        if items:
            summary[field] = items
    return summary


def synthesize_reading_report_with_llm(
    paper: Dict[str, Any],
    user_profile: Optional[Dict[str, Any]] = None,
    parsed_pdf: Optional[Dict[str, Any]] = None,
    heuristic_payload: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Generate structured reading-report content using the configured LLM backend."""
    user_profile = user_profile or {}
    heuristic_payload = heuristic_payload or {}
    sections = dict((parsed_pdf or {}).get("sections") or {})

    profile_directions = sorted(
        (user_profile.get("core_directions") or {}).items(),
        key=lambda item: float(item[1]),
        reverse=True,
    )[:3]
    retrieved_evidence = _summarize_retrieved_evidence_for_prompt(heuristic_payload)
    field_evidence_map = _summarize_field_evidence_map_for_prompt(heuristic_payload)
    preference_summary = json.dumps(
        user_profile.get("methodology_preferences") or {},
        ensure_ascii=False,
        sort_keys=True,
    )
    report_preference_summary = json.dumps(
        user_profile.get("report_preferences") or {},
        ensure_ascii=False,
        sort_keys=True,
    )

    user_text = json.dumps(
        {
            "paper": {
                "title": paper.get("title"),
                "authors": paper.get("authors"),
                "abstract": _truncate_prompt_text(paper.get("abstract"), 2000),
                "venue": paper.get("venue"),
                "publish_date": paper.get("publish_date"),
                "arxiv_id": paper.get("arxiv_id"),
                "doi": paper.get("doi"),
            },
            "sections": {
                "introduction": _truncate_prompt_text(sections.get("introduction"), 1600),
                "method": _truncate_prompt_text(sections.get("method"), 1600),
                "results": _truncate_prompt_text(sections.get("results"), 1600),
                "discussion": _truncate_prompt_text(sections.get("discussion"), 1200),
                "conclusion": _truncate_prompt_text(sections.get("conclusion"), 1200),
            },
            "user_profile": {
                "top_directions": profile_directions,
                "methodology_preferences": preference_summary,
                "report_preferences": report_preference_summary,
            },
            "heuristic_draft": {
                "one_sentence_summary": heuristic_payload.get("one_sentence_summary"),
                "research_background": heuristic_payload.get("research_background"),
                "core_method": heuristic_payload.get("core_method"),
                "key_results": heuristic_payload.get("key_results"),
                "main_contributions": heuristic_payload.get("main_contributions"),
                "limitations": heuristic_payload.get("limitations"),
                "relevance_points": heuristic_payload.get("relevance_points"),
                "reading_focus": heuristic_payload.get("reading_focus"),
            },
            "retrieved_evidence": retrieved_evidence,
            "field_evidence_map": field_evidence_map,
        },
        ensure_ascii=False,
    )

    system_prompt = (
        "你是科研论文精读助手。请基于提供的论文元数据、摘要、可用章节摘录和用户画像，"
        "生成一份适合飞书文档使用的结构化中文精读内容。"
        "如果提供了 retrieved_evidence，请优先参考这些 PDF 语义检索命中的证据片段，"
        "再结合 heuristic_draft 做润色和补全；当二者冲突时，优先采用 retrieved_evidence。"
        "如果提供了 field_evidence_map，请让每个输出字段优先参考它对应的证据锚点，"
        "不要把 results 证据写到 research_background，也不要把 background 证据误写成方法贡献。"
        "如果 user_profile.report_preferences 显示 prefer_more_evidence=true 或 preferred_style=evidence_first，"
        "请优先写出更具体的证据锚点和方法/结果依据，不要只给空泛总结。"
        "不要编造具体实验数值；如果信息不足，请保持克制并明确指出需要回原文核对。"
        "可以改写证据，不要大段逐字复制。"
        "输出 JSON，字段包括："
        "one_sentence_summary, research_background, core_method, key_results, "
        "main_contributions, limitations, relevance_points, reading_focus, recommendation_label, analysis_note。"
        "analysis_note 用一句话说明本次生成是否参考了 PDF 检索证据。"
        "其中 recommendation_label 只能是“强烈推荐”“推荐阅读”“值得快速浏览”“按需阅读”之一。"
    )

    result = _generate_json_with_configured_llm(
        system_prompt=system_prompt,
        user_text=user_text,
        max_tokens=900,
        timeout_override=_get_reading_report_timeout(),
    )
    if not isinstance(result, dict):
        return None

    normalized: Dict[str, Any] = {}
    for key in ("one_sentence_summary", "research_background", "core_method", "key_results", "recommendation_label", "analysis_note"):
        value = str(result.get(key, "")).strip()
        if value:
            normalized[key] = value

    for key in ("main_contributions", "limitations", "relevance_points", "reading_focus"):
        values = _clean_generated_list(result.get(key))
        if values:
            normalized[key] = values

    return normalized or None


def _learn_new_direction(direction: Dict[str, Any], source_text: str) -> bool:
    """
    学习新方向到词典

    Args:
        direction: 方向信息
        source_text: 原文

    Returns:
        是否成功
    """
    try:
        from config.direction_lexicon import add_new_direction

        direction_key = direction.get("name", "")
        name_cn = direction.get("name_cn", "")
        source = direction.get("source_text", source_text)

        # 从原文和方向名推断关键词
        keywords = [
            direction.get("name", "").replace("-", " "),
            name_cn,
            source.split()[:5] if source else []
        ]
        keywords = [kw for kw in keywords if kw and isinstance(kw, str)]

        if direction_key and len(direction_key) > 2:
            return add_new_direction(
                direction_key=direction_key,
                name=direction.get("name", ""),
                name_cn=name_cn,
                keywords=keywords,
                source_text=source_text
            )

        return False

    except Exception as e:
        print(f"Failed to learn new direction: {e}")
        return False


def update_direction_lexicon(new_direction: str, keywords: List[str]) -> bool:
    """
    将新发现的方向添加到 lexicon（未来可持久化）

    Args:
        new_direction: 新方向名称
        keywords: 相关关键词列表

    Returns:
        是否成功
    """
    # TODO: 持久化到配置文件
    # 目前仅打印日志
    print(f"[Lexicon Update] New direction: {new_direction} -> keywords: {keywords}")
    return True


if __name__ == "__main__":
    # 测试
    test_cases = [
        "我最近对量子计算很感兴趣",
        "我想多做点神经符号 AI 方向",
        "降低 GUI Agent 权重",
        "我最近在搞具身智能",
    ]

    for text in test_cases:
        print(f"\nInput: {text}")
        result = parse_intent_with_llm(text)
        print(f"Result: {result}")

        directions = parse_research_directions(text)
        print(f"Directions: {directions}")
