#!/usr/bin/env python3
"""
ColdStart Agent

Bootstraps and incrementally updates a user's academic profile from:
- natural language self-description
- uploaded PDFs
- future scholar links
"""

import copy
import hashlib
import importlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
create_profile = db_ops.create_profile
update_profile = db_ops.update_profile
get_profile = db_ops.get_profile

pdf_parser = importlib.import_module("skills.pdf-parser.scripts.parse_pdf")
parse_paper_for_coldstart = pdf_parser.parse_paper_for_coldstart

feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")


DIRECTION_KEYWORDS = {
    "gui-agent": ["gui agent", "gui", "interface agent", "computer use", "screen agent", "action agent"],
    "multimodal-reasoning": ["multimodal", "vision-language", "vision and language", "cross-modal"],
    "vision": ["vision", "visual", "image", "video", "cv", "computer vision"],
    "language": ["language", "llm", "nlp", "text", "transformer"],
    "machine-learning": ["machine learning", "ml", "classification", "regression"],
    "deep-learning": ["deep learning", "neural", "cnn", "transformer"],
    "reinforcement-learning": ["reinforcement", "rl", "reward", "policy", "actor", "critic"],
    "reasoning": ["reasoning", "chain of thought", "cot", "thought"],
    "agent": ["agent", "agents", "autonomous"],
    "optimization": ["optimization", "optimize", "efficient", "optimizer"],
    "retrieval": ["retrieval", "retrieve", "search", "rag"],
    "generation": ["generation", "generate", "diffusion", "generative"],
    "data-native": ["data-native", "data native", "data-centric", "data centric", "infrastructure"],
    "bio-molecular": ["bio", "protein", "molecular", "drug", "compound", "molecule"],
    "science-discovery": ["scientific", "science", "discovery", "hypothesis"],
}

METHODOLOGY_KEYWORDS = {
    "data_driven": [
        "data-driven",
        "empirical",
        "experimental",
        "large-scale",
        "data-native",
        "data native",
        "dataset",
        "infrastructure",
    ],
    "theory": ["theoretical", "theory", "analysis", "proof"],
    "systematic": ["systematic", "comprehensive", "benchmark", "framework", "infrastructure", "platform", "map", "graph"],
    "incremental": ["improvement", "enhancement", "better", "incremental"],
    "open_source": ["open source", "opensource", "code available", "github"],
    "application": ["application", "applied", "real-world", "case study"],
}

BASELINE_PDF_ENV_VAR = "SCITASTE_BASELINE_PDF"
PDF_DIRECTION_WEIGHT_CAP = 0.70
PDF_INCREMENT_BLEND = 0.25
PDF_NEW_DIRECTION_CAP = 0.55
PDF_NEW_DIRECTION_SCALE = 0.85
TEXT_INCREMENT_BLEND = 0.35
TEXT_NEW_DIRECTION_CAP = 0.65
COLD_START_COMMAND_HINTS = {"冷启动", "重新冷启动", "cold start", "cold-start"}


def build_empty_profile(user_id: str) -> Dict[str, Any]:
    """Create an empty profile payload with the full schema."""
    now = datetime.now().isoformat()
    return {
        "user_id": user_id,
        "version": "0.1",
        "created_at": now,
        "updated_at": now,
        "core_directions": {},
        "methodology_preferences": {},
        "must_read": {
            "authors": [],
            "institutions": [],
            "keywords": [],
        },
        "topic_weights": {},
        "author_heat": {},
        "institution_heat": {},
        "interest_vector": [],
        "taste_profile": {},
        "reading_history": [],
        "behavior_logs": [],
    }


def ensure_profile_shape(profile: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
    """Normalize a stored profile into the current schema."""
    normalized = copy.deepcopy(profile) if profile else build_empty_profile(user_id)
    normalized["user_id"] = user_id
    normalized.setdefault("version", "0.1")
    normalized.setdefault("created_at", normalized.get("updated_at", datetime.now().isoformat()))
    normalized["updated_at"] = datetime.now().isoformat()

    for key in ("core_directions", "methodology_preferences", "topic_weights", "author_heat", "institution_heat", "taste_profile"):
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, dict) else {}

    must_read = normalized.get("must_read")
    normalized["must_read"] = must_read if isinstance(must_read, dict) else {}
    for key in ("authors", "institutions", "keywords"):
        value = normalized["must_read"].get(key)
        normalized["must_read"][key] = value if isinstance(value, list) else []

    for key in ("interest_vector", "reading_history", "behavior_logs"):
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, list) else []

    return normalized


def resolve_baseline_pdf_path(user_id: str) -> Optional[str]:
    """Return the configured baseline PDF for the given user."""
    candidate_paths: List[Path] = []

    configured = os.environ.get(BASELINE_PDF_ENV_VAR)
    if configured:
        candidate_paths.append(Path(configured).expanduser())

    if user_id == "user_rolea":
        candidate_paths.append(Path.home() / "Desktop" / "Research Infra.pdf")

    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate)

    return None


def _blend_weight(
    existing_weight: float,
    incoming_weight: float,
    blend: float,
    new_direction_cap: float,
    new_direction_scale: float,
) -> float:
    """Blend a new signal into an existing direction without letting one PDF dominate."""
    incoming = min(max(float(incoming_weight or 0.0), 0.0), PDF_DIRECTION_WEIGHT_CAP)
    existing = max(float(existing_weight or 0.0), 0.0)

    if existing > 0:
        blended = existing + blend * (incoming - existing)
        return round(max(existing, min(PDF_DIRECTION_WEIGHT_CAP, blended)), 4)

    seeded = min(PDF_DIRECTION_WEIGHT_CAP, incoming * new_direction_scale, new_direction_cap)
    return round(seeded, 4)


def _apply_full_text_methodology_hints(profile: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Use explicit PDF phrases as extra methodology hints."""
    full_text = (result.get("full_text") or "").lower()

    if any(keyword in full_text for keyword in ("dataset", "data-driven", "empirical", "experiment", "benchmark")):
        profile["methodology_preferences"]["preference_data_driven_over_theory"] = True

    if any(keyword in full_text for keyword in ("framework", "system", "comprehensive", "benchmark", "pipeline", "platform")):
        profile["methodology_preferences"]["preference_systematic_work_over_incremental"] = True

    if any(keyword in full_text for keyword in ("github", "open source", "code available", "code release")):
        profile["methodology_preferences"]["preference_open_source_code"] = True

    if any(keyword in full_text for keyword in ("bio", "protein", "molecular", "drug", "scientific", "computational biology")):
        profile["methodology_preferences"]["preference_bio_science_application"] = True


def merge_parsed_profile_into_profile(
    profile: Dict[str, Any],
    parsed: Dict[str, Any],
    blend: float = TEXT_INCREMENT_BLEND,
    new_direction_cap: float = TEXT_NEW_DIRECTION_CAP,
) -> None:
    """Merge natural-language signals into an existing profile."""
    normalized_profile = ensure_profile_shape(profile, profile.get("user_id", "user_001"))
    profile.clear()
    profile.update(normalized_profile)

    for direction_key, weight in (parsed.get("core_directions") or {}).items():
        merged_weight = _blend_weight(
            existing_weight=profile["core_directions"].get(direction_key, 0.0),
            incoming_weight=weight,
            blend=blend,
            new_direction_cap=new_direction_cap,
            new_direction_scale=1.0,
        )
        if merged_weight > 0:
            profile["core_directions"][direction_key] = merged_weight
            profile["topic_weights"][direction_key] = max(
                merged_weight,
                float(profile["topic_weights"].get(direction_key, 0.0)),
            )

    for key, value in (parsed.get("methodology_preferences") or {}).items():
        if value:
            profile["methodology_preferences"][key] = True

    for topic_key, weight in (parsed.get("topic_weights") or {}).items():
        existing_weight = float(profile["topic_weights"].get(topic_key, 0.0))
        incoming_weight = min(float(weight or 0.0), new_direction_cap)
        profile["topic_weights"][topic_key] = round(max(existing_weight, incoming_weight), 4)

    if not profile["interest_vector"] and parsed.get("interest_vector"):
        profile["interest_vector"] = parsed["interest_vector"]

    parsed_taste_profile = parsed.get("taste_profile") or {}
    for key, values in parsed_taste_profile.items():
        if not isinstance(values, list):
            continue
        current_values = profile["taste_profile"].setdefault(key, [])
        for value in values:
            if value not in current_values:
                current_values.append(value)


def merge_pdf_result_into_profile(profile: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Merge a parsed PDF result into the existing profile conservatively."""
    normalized_profile = ensure_profile_shape(profile, profile.get("user_id", "user_001"))
    profile.clear()
    profile.update(normalized_profile)

    for direction in result.get("research_directions", []):
        name = direction.get("name", "")
        direction_key = name.lower().replace(" ", "-")
        if not direction_key:
            continue

        merged_weight = _blend_weight(
            existing_weight=profile["core_directions"].get(direction_key, 0.0),
            incoming_weight=direction.get("confidence", 0.0),
            blend=PDF_INCREMENT_BLEND,
            new_direction_cap=PDF_NEW_DIRECTION_CAP,
            new_direction_scale=PDF_NEW_DIRECTION_SCALE,
        )
        if merged_weight > 0:
            profile["core_directions"][direction_key] = merged_weight
            profile["topic_weights"][direction_key] = max(
                merged_weight,
                float(profile["topic_weights"].get(direction_key, 0.0)),
            )

    for key, value in (result.get("methodology_preferences") or {}).items():
        if value:
            profile["methodology_preferences"][key] = True

    for topic in result.get("inferred_topics", []):
        topic_key = topic.lower().replace(" ", "-")
        if not topic_key:
            continue

        existing_weight = float(profile["topic_weights"].get(topic_key, 0.0))
        if existing_weight > 0:
            profile["topic_weights"][topic_key] = round(min(0.6, existing_weight + 0.08), 4)
        else:
            profile["topic_weights"][topic_key] = 0.30

    _apply_full_text_methodology_hints(profile, result)


def _seed_profile_from_baseline_pdf(profile: Dict[str, Any], user_id: str) -> Optional[str]:
    """Initialize an empty profile from the configured baseline PDF."""
    if profile.get("core_directions"):
        return None

    baseline_pdf_path = resolve_baseline_pdf_path(user_id)
    if not baseline_pdf_path:
        return None

    result = parse_paper_for_coldstart(baseline_pdf_path)
    for direction in result.get("research_directions", []):
        direction_key = direction.get("name", "").lower().replace(" ", "-")
        confidence = min(float(direction.get("confidence", 0.0)), PDF_DIRECTION_WEIGHT_CAP)
        if direction_key and confidence > 0:
            profile["core_directions"][direction_key] = round(confidence, 4)
            profile["topic_weights"][direction_key] = round(confidence, 4)

    for key, value in (result.get("methodology_preferences") or {}).items():
        if value:
            profile["methodology_preferences"][key] = True

    for topic in result.get("inferred_topics", []):
        topic_key = topic.lower().replace(" ", "-")
        if topic_key and topic_key not in profile["topic_weights"]:
            profile["topic_weights"][topic_key] = 0.35

    _apply_full_text_methodology_hints(profile, result)
    return baseline_pdf_path


def _empty_parsed_profile_fragment() -> Dict[str, Any]:
    """Return an empty parse result for command-only bootstrap text."""
    return {
        "core_directions": {},
        "methodology_preferences": {},
        "topic_weights": {},
        "interest_vector": [],
        "taste_profile": {},
        "inferred_topics": [],
    }


def parse_natural_language(text: str, use_llm: bool = True) -> Dict[str, Any]:
    """Parse a natural-language self-description into a bootstrap profile fragment."""
    normalized_text = re.sub(r"\s+", " ", (text or "").strip()).lower()
    if normalized_text in COLD_START_COMMAND_HINTS:
        return _empty_parsed_profile_fragment()

    text_lower = text.lower()

    # 合并 lexicon 中的关键词到 DIRECTION_KEYWORDS
    from config.direction_lexicon import get_lexicon_keywords
    lexicon_keywords = get_lexicon_keywords()
    merged_directions = dict(DIRECTION_KEYWORDS)
    for key, keywords in lexicon_keywords.items():
        if key in merged_directions:
            # 合并关键词（去重）
            merged_directions[key] = list(set(merged_directions[key] + keywords))
        else:
            # 将关键词转换为英文和中文混合列表
            merged_directions[key] = [kw.lower() for kw in keywords]

    core_directions: Dict[str, float] = {}
    topic_weights: Dict[str, float] = {}
    for direction, keywords in merged_directions.items():
        match_count = sum(1 for keyword in keywords if keyword in text_lower or keyword in text)
        if match_count > 0:
            weight = min(0.5 + match_count * 0.1, 0.95)
            core_directions[direction] = weight
            topic_weights[direction] = weight

    # 先走轻量规则；只有规则没有命中时才回退到 LLM，避免启动时加载本地大模型。
    llm_directions: List[Dict[str, Any]] = []
    if use_llm and not core_directions:
        llm_directions = _parse_directions_with_llm(text)
    for direction in llm_directions:
        name = direction.get("name", "")
        confidence = direction.get("confidence", 0.5)
        direction_key = name.lower().replace(" ", "-")

        # 如果规则已检测到，取较高值；否则添加新方向
        if direction_key in core_directions:
            existing = core_directions[direction_key]
            if confidence > existing:
                core_directions[direction_key] = confidence
                topic_weights[direction_key] = confidence
        else:
            # 新方向，使用较低初始权重
            core_directions[direction_key] = min(confidence * 0.8, 0.5)
            topic_weights[direction_key] = min(confidence * 0.8, 0.5)

    methodology_preferences = {
        "preference_data_driven_over_theory": (
            sum(1 for keyword in METHODOLOGY_KEYWORDS["data_driven"] if keyword in text_lower)
            > sum(1 for keyword in METHODOLOGY_KEYWORDS["theory"] if keyword in text_lower)
        ),
        "preference_systematic_work_over_incremental": (
            sum(1 for keyword in METHODOLOGY_KEYWORDS["systematic"] if keyword in text_lower)
            > sum(1 for keyword in METHODOLOGY_KEYWORDS["incremental"] if keyword in text_lower)
        ),
        "preference_open_source_code": any(keyword in text_lower for keyword in METHODOLOGY_KEYWORDS["open_source"]),
        "preference_bio_science_application": any(
            keyword in text_lower for keyword in ("bio", "science", "scientific", "molecular", "protein")
        ),
    }

    taste_profile = {
        "preferred_work_type": [],
        "dispreferred_work_type": [],
    }
    if methodology_preferences["preference_data_driven_over_theory"]:
        taste_profile["preferred_work_type"].append("empirical")
    else:
        taste_profile["preferred_work_type"].append("theoretical")

    if methodology_preferences["preference_systematic_work_over_incremental"]:
        taste_profile["preferred_work_type"].append("systematic")
        taste_profile["dispreferred_work_type"].append("incremental")
    else:
        taste_profile["dispreferred_work_type"].append("systematic")

    if methodology_preferences["preference_open_source_code"]:
        taste_profile["preferred_work_type"].append("open_source")

    if methodology_preferences["preference_bio_science_application"]:
        taste_profile["preferred_work_type"].append("applied")

    return {
        "core_directions": core_directions,
        "methodology_preferences": methodology_preferences,
        "topic_weights": topic_weights,
        "interest_vector": generate_interest_vector(core_directions),
        "taste_profile": taste_profile,
        "inferred_topics": [d.get("name") for d in llm_directions if d.get("name")],
    }


def _parse_directions_with_llm(text: str) -> List[Dict[str, Any]]:
    """使用 LLM 解析研究方向（规则匹配失败时的兜底）"""
    try:
        llm_parser = importlib.import_module("agents.master-coordinator.scripts.llm_parser")
        directions = llm_parser.parse_research_directions(text, auto_learn=True)

        # 加载动态词典
        lexicon_module = importlib.import_module("config.direction_lexicon")
        lexicon_keywords = lexicon_module.get_lexicon_keywords()

        # 将动态词典合并到 DIRECTION_KEYWORDS 进行检测
        all_directions = dict(DIRECTION_KEYWORDS)
        all_directions.update(lexicon_keywords)

        # 重新检测已知方向（避免重复学习）
        text_lower = text.lower()
        known_keys = set(DIRECTION_KEYWORDS.keys())

        filtered_directions = []
        for d in directions:
            direction_key = d.get("name", "").lower().replace(" ", "-")
            # 检查是否在动态词典中已存在
            if direction_key in lexicon_keywords:
                # 在动态词典中，添加到 all_directions 用于后续匹配
                if direction_key not in all_directions:
                    all_directions[direction_key] = lexicon_keywords.get(direction_key, [])
            filtered_directions.append(d)

        return filtered_directions

    except Exception as e:
        print(f"LLM direction parsing failed: {e}")
        return []


def generate_interest_vector(core_directions: Dict[str, float]) -> List[float]:
    """Generate a deterministic pseudo-vector from the detected directions."""
    try:
        target_dim = max(1, int(str(os.environ.get("EMBEDDING_DIMENSIONS", "768")).strip()))
    except ValueError:
        target_dim = 768

    direction_str = "_".join(sorted(core_directions.keys()))
    hash_bytes = hashlib.sha256(direction_str.encode()).digest()
    vector = []

    for index in range(target_dim):
        byte_index = index % 32
        sign = 1 if (hash_bytes[byte_index] & (1 << (index % 8))) else -1
        value = sign * ((hash_bytes[byte_index] >> (index % 8)) & 1)
        vector.append(float(value))

    norm = sum(value * value for value in vector) ** 0.5
    if norm > 0:
        vector = [value / norm for value in vector]

    return vector


def format_profile_card(profile: Dict[str, Any], user_id: str = "user_001") -> str:
    """Format the cold-start profile confirmation card in the PDF-inspired layout."""
    profile_stage = "持续学习" if profile.get("core_directions") else "冷启动"
    lines = [
        f"📋 你的学术画像（v0.1 - {profile_stage}）",
        "",
        "━━━ 核心方向 ━━━",
    ]

    core_directions = profile.get("core_directions", {})
    if core_directions:
        for direction, weight in sorted(core_directions.items(), key=lambda item: -item[1]):
            direction_cn = translate_direction(direction)
            filled = max(0, min(10, int(round(weight * 10))))
            bar = "█" * filled + "░" * (10 - filled)
            lines.append(f"{direction_cn} [{bar}] 权重：{weight:.2f}")
    else:
        lines.append("（冷启动阶段，暂无稳定方向）")

    lines.extend(
        [
            "",
            "━━━ 方法论偏好 ━━━",
        ]
    )

    method_prefs = profile.get("methodology_preferences", {})
    if method_prefs:
        lines.append(
            "├── 偏好数据驱动 > 纯理论"
            if method_prefs.get("preference_data_driven_over_theory")
            else "├── 偏好纯理论 > 数据驱动"
        )
        lines.append(
            "├── 偏好系统性工作 > 单点改进"
            if method_prefs.get("preference_systematic_work_over_incremental")
            else "├── 偏好单点改进 > 系统性工作"
        )
        lines.append(
            "├── 偏好带开源代码的工作"
            if method_prefs.get("preference_open_source_code")
            else "├── 对开源代码暂无明显偏好"
        )
        lines.append(
            "└── 偏好有生物/科学应用场景的工作"
            if method_prefs.get("preference_bio_science_application")
            else "└── 通用研究场景均可"
        )
    else:
        lines.append("（暂无方法论偏好信号）")

    must_read = profile.get("must_read", {"authors": [], "institutions": [], "keywords": []})
    lines.extend(
        [
            "",
            "━━━ 必读清单 ━━━",
            f"作者：{', '.join(must_read.get('authors', [])) or '（空，待你添加）'}",
            f"机构：{', '.join(must_read.get('institutions', [])) or '（空，待你添加）'}",
            f"关键词：{', '.join(must_read.get('keywords', [])) or '（空，待你添加）'}",
            "",
            "━━━━━━━━━━━━",
            "你可以直接说：",
            '  "加个必读作者：XXX"',
            '  "降低 GUI Agent 权重"',
            '  "我最近对 protein language model 更感兴趣了"',
        ]
    )

    return "\n".join(lines)


def translate_direction(direction: str) -> str:
    """Translate internal direction keys into display labels."""
    translations = {
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
        "protein-folding": "蛋白质折叠",
        "nlp": "自然语言处理",
        "computer-vision": "计算机视觉",
        "bioinformatics": "生物信息学",
    }
    return translations.get(direction, direction)


def cold_start(
    user_id: str = "user_001",
    natural_language: Optional[str] = None,
    pdf_paths: Optional[List[str]] = None,
    scholar_url: Optional[str] = None,
    send_to_feishu: bool = True,
    feishu_user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the cold-start / PDF-update flow."""
    print(f"Starting cold start for user: {user_id}")

    existing_profile = get_profile(user_id)
    if existing_profile:
        profile = ensure_profile_shape(existing_profile, user_id)
        print("Loaded existing profile as merge base.")
    else:
        profile = build_empty_profile(user_id)

    baseline_pdf_path = None
    try:
        baseline_pdf_path = _seed_profile_from_baseline_pdf(profile, user_id)
        if baseline_pdf_path:
            print(f"Seeded profile from baseline PDF: {baseline_pdf_path}")
    except Exception as exc:
        print(f"Failed to seed baseline PDF: {exc}")

    if natural_language:
        print("Parsing natural language...")
        parsed = parse_natural_language(natural_language)
        merge_parsed_profile_into_profile(profile, parsed)

    if pdf_paths:
        print(f"Parsing {len(pdf_paths)} PDF file(s)...")
        applied_sources = set()
        if baseline_pdf_path:
            applied_sources.add(str(Path(baseline_pdf_path).resolve()))

        for pdf_path in pdf_paths:
            if not os.path.exists(pdf_path):
                print(f"  PDF not found: {pdf_path}")
                continue

            resolved_path = str(Path(pdf_path).resolve())
            if resolved_path in applied_sources:
                print(f"  Skipping duplicate source PDF: {pdf_path}")
                continue

            try:
                result = parse_paper_for_coldstart(pdf_path)
                merge_pdf_result_into_profile(profile, result)
                applied_sources.add(resolved_path)
                print(f"  Parsed: {pdf_path}")
            except Exception as exc:
                print(f"  Failed to parse {pdf_path}: {exc}")

    if scholar_url:
        print("Scholar parsing not yet implemented")

    profile["updated_at"] = datetime.now().isoformat()

    print("Saving profile...")
    if existing_profile:
        update_profile(user_id, profile)
        print("Profile updated successfully!")
    else:
        create_profile(user_id, profile)
        print("Profile created successfully!")

    if send_to_feishu:
        target_id = chat_id or feishu_user_id or os.environ.get("FEISHU_USER_ID", "")
        use_chat = chat_id is not None
        print(f"Sending to Feishu - target: {target_id[:20]}..., use_chat_id: {use_chat}")

        card_text = format_profile_card(profile, user_id)
        try:
            if use_chat:
                feishu_reporter.send_text_to_chat(target_id, card_text)
            else:
                feishu_reporter.send_text(target_id, card_text)
            print("Profile sent to Feishu successfully!")
        except Exception as exc:
            print(f"Failed to send to Feishu: {exc}")

    print("\n--- Cold Start Complete ---")
    print(f"Profile version: {profile['version']}")
    print(f"Core directions: {len(profile['core_directions'])}")
    print(f"Topic weights: {list(profile['topic_weights'].keys())}")
    return profile


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ColdStart Agent")
    parser.add_argument("--user-id", type=str, default="user_001", help="User ID")
    parser.add_argument("--role", type=str, default="roleA", help="Role name (roleA, roleB, etc.)")
    parser.add_argument("--natural-language", type=str, help="Natural language description")
    parser.add_argument("--pdf", nargs="+", help="PDF file paths")
    parser.add_argument("--scholar-url", type=str, help="Google Scholar URL")
    parser.add_argument("--send-feishu", action="store_true", help="Send to Feishu")
    parser.add_argument("--feishu-user-id", type=str, help="Feishu user ID")

    args = parser.parse_args()

    role = args.role.lower()
    user_id = f"user_{role}" if role.startswith("role") else args.user_id
    baseline_pdf_path = resolve_baseline_pdf_path(user_id)

    if role == "rolea" and not args.natural_language and not baseline_pdf_path:
        natural_language = (
            "我关注 data-native scientific discovery，"
            "具体做生物分子数据基础设施和方法论图谱，"
            "也关注 auto research 和 GUI agent"
        )
    else:
        natural_language = args.natural_language

    cold_start(
        user_id=user_id,
        natural_language=natural_language,
        pdf_paths=args.pdf,
        scholar_url=args.scholar_url,
        send_to_feishu=args.send_feishu,
        feishu_user_id=args.feishu_user_id,
    )
