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

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

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
LOCAL_LLM_DISABLED = False
PROJECT_ROOT = Path(__file__).resolve().parents[3]
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


def _get_openai_client() -> Optional[OpenAI]:
    """获取 OpenAI 客户端（如果可用）"""
    global LLM_FALLBACK_DISABLED

    if LLM_FALLBACK_DISABLED:
        return None

    if OpenAI is None:
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if _is_placeholder_openai_key(api_key):
        return None

    return OpenAI(api_key=api_key)


def _get_llm_parser_provider() -> str:
    """Return the configured parser backend provider."""
    provider = os.environ.get("LLM_PARSER_PROVIDER", "auto").strip().lower()
    if provider in {"none", "disabled", "off"}:
        return "disabled"
    if provider in {"local", "openai"}:
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


def _get_local_llm_backend() -> Optional[Dict[str, Any]]:
    """Load a local causal LM backend for parser inference."""
    global LOCAL_LLM_DISABLED

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

    cache_key = str(model_path)
    if cache_key in _LOCAL_LLM_CACHE:
        return _LOCAL_LLM_CACHE[cache_key]

    trust_remote_code = os.environ.get("LOCAL_LLM_TRUST_REMOTE_CODE", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    configured_device = os.environ.get("LOCAL_LLM_DEVICE", "auto").strip().lower()
    if configured_device in {"cuda", "gpu"} and torch.cuda.is_available():
        device = "cuda"
    elif configured_device == "cpu":
        device = "cpu"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_path),
            trust_remote_code=trust_remote_code,
        )
        if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
            tokenizer.pad_token = tokenizer.eos_token

        model_kwargs: Dict[str, Any] = {
            "trust_remote_code": trust_remote_code,
        }
        if device == "cuda":
            model_kwargs["torch_dtype"] = torch.float16

        model = AutoModelForCausalLM.from_pretrained(str(model_path), **model_kwargs)
        if device == "cuda":
            model = model.to(device)
        model.eval()
    except Exception as e:
        print(f"Local LLM initialization error: {e}")
        LOCAL_LLM_DISABLED = True
        return None

    backend = {
        "tokenizer": tokenizer,
        "model": model,
        "device": device,
        "path": str(model_path),
    }
    _LOCAL_LLM_CACHE[cache_key] = backend
    return backend


def _generate_json_with_local_llm(system_prompt: str, user_text: str, max_new_tokens: int = 512) -> Optional[Dict[str, Any]]:
    """Generate a JSON response from a local causal LM."""
    backend = _get_local_llm_backend()
    if backend is None or torch is None:
        return None

    tokenizer = backend["tokenizer"]
    model = backend["model"]
    device = backend["device"]
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

        with torch.no_grad():
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
        print(f"Local LLM parsing error: {e}")
        return None


def _generate_json_with_openai(system_prompt: str, user_text: str, max_tokens: int = 500) -> Optional[Dict[str, Any]]:
    """Generate a JSON response from OpenAI."""
    client = _get_openai_client()
    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model=os.environ.get("LLM_PARSER_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return _extract_json_object(response.choices[0].message.content)
    except Exception as e:
        if any(token in str(e).lower() for token in ["401", "unauthorized", "invalid api key", "incorrect api key"]):
            global LLM_FALLBACK_DISABLED
            LLM_FALLBACK_DISABLED = True
        print(f"LLM parsing error: {e}")
        return None


def _generate_json_with_configured_llm(
    system_prompt: str,
    user_text: str,
    max_tokens: int,
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

    if provider in {"openai", "auto"}:
        return _generate_json_with_openai(system_prompt, user_text, max_tokens=max_tokens)

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
        max_tokens=500,
    )
    if not isinstance(result, dict):
        return None

    if result.get("confidence", 0) < 0.5:
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
    known_directions = list(DIRECTION_CN_MAP.values()) + [
        data.get("name_cn", "") for data in lexicon.values()
    ]

    system_prompt = f"""你是一个研究方向识别助手。从用户输入中识别他们感兴趣的研究方向。

已知研究方向包括：{", ".join(known_directions)}

返回 JSON 格式：
{{
    "directions": [
        {{
            "name": "方向名称（英文，使用连字符格式，如 multimodal-reasoning）",
            "name_cn": "中文名称",
            "confidence": 0.0-1.0,
            "source_text": "原文中提到的部分",
            "is_known": true/false (是否在已知列表中)
        }}
    ]
}}

如果是中文方向名，请翻译成英文。如果方向不在已知列表中，也请提取，用拼音或翻译表示。"""

    result = _generate_json_with_configured_llm(
        system_prompt=system_prompt,
        user_text=text,
        max_tokens=800,
    )
    if not isinstance(result, dict):
        return []

    directions = result.get("directions", [])
    if not isinstance(directions, list):
        return []

    # 标准化方向名称
    new_directions = []
    normalized_directions: List[Dict[str, Any]] = []
    for direction in directions:
        if not isinstance(direction, dict):
            continue
        name = str(direction.get("name", "")).strip().lower().replace(" ", "-").replace("_", "-")
        if not name:
            continue
        direction["name"] = name
        normalized_directions.append(direction)
        if not direction.get("is_known", True):
            new_directions.append(direction)

    # 自动学习新方向
    if auto_learn and new_directions:
        for direction in new_directions:
            _learn_new_direction(direction, text)

    return normalized_directions


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
    preference_summary = json.dumps(
        user_profile.get("methodology_preferences") or {},
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
        },
        ensure_ascii=False,
    )

    system_prompt = (
        "你是科研论文精读助手。请基于提供的论文元数据、摘要、可用章节摘录和用户画像，"
        "生成一份适合飞书文档使用的结构化中文精读内容。"
        "不要编造具体实验数值；如果信息不足，请保持克制并明确指出需要回原文核对。"
        "输出 JSON，字段包括："
        "one_sentence_summary, research_background, core_method, key_results, "
        "main_contributions, limitations, relevance_points, reading_focus, recommendation_label。"
        "其中 recommendation_label 只能是“强烈推荐”“推荐阅读”“值得快速浏览”“按需阅读”之一。"
    )

    result = _generate_json_with_configured_llm(
        system_prompt=system_prompt,
        user_text=user_text,
        max_tokens=900,
    )
    if not isinstance(result, dict):
        return None

    normalized: Dict[str, Any] = {}
    for key in ("one_sentence_summary", "research_background", "core_method", "key_results", "recommendation_label"):
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
