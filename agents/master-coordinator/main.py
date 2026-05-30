#!/usr/bin/env python3
"""
Master Coordinator - 主协调器

职责：
1. 接收用户输入（飞书消息/命令行）
2. 识别意图，路由到对应的 Agent
3. 协调多个 Agent 的协作
4. 统一管理用户会话状态

支持的意图：
- 冷启动 → coldstart-agent
- 每日推送 → daily-push-agent
- 反馈选择 → feedback-agent
- 生成精读 → reading-agent
- 查看周报 → profile-report-agent
- 管理必读 → must-read-manager
"""

import sys
import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import logging

logger = logging.getLogger("master-coordinator")


# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 使用 importlib 导入带连字符的模块
import importlib

# 数据库操作
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
get_profile = db_ops.get_profile
create_profile = db_ops.create_profile
update_profile = db_ops.update_profile
get_latest_push = db_ops.get_latest_push
get_latest_selected_papers = getattr(db_ops, "get_latest_selected_papers", lambda user_id: None)
clear_pending_selected_papers = getattr(
    db_ops,
    "clear_pending_selected_papers",
    lambda user_id: {"cleared": False, "cleared_count": 0, "push_id": None, "papers": []},
)
get_recent_pushes = db_ops.get_recent_pushes
get_recent_created_report = getattr(db_ops, "get_recent_created_report", lambda user_id, minutes=180: None)
log_behavior = db_ops.log_behavior
profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")
build_default_drift_state = profile_updater.build_default_drift_state
ensure_profile_schema = profile_updater.ensure_profile_schema
update_profile_with_reading_signal = profile_updater.update_profile_with_reading_signal
direction_lexicon = importlib.import_module("config.direction_lexicon")
canonicalize_direction_terms = direction_lexicon.canonicalize_direction_terms
confirm_pending_direction_candidate = direction_lexicon.confirm_pending_direction_candidate
find_pending_direction_candidate = direction_lexicon.find_pending_direction_candidate
get_direction_entry = direction_lexicon.get_direction_entry
normalize_direction_key = direction_lexicon.normalize_direction_key
resolve_canonical_direction = direction_lexicon.resolve_canonical_direction

# 飞书报告器
feishu_reporter = importlib.import_module("deployments.feishu.feishu-reporter.scripts.feishu_reporter")
send_text = feishu_reporter.send_text


ROLE_META_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "roles.json",
)


DIRECTION_TRANSLATIONS = {
    "gui-agent": "GUI Agent",
    "multimodal-reasoning": "多模态推理",
    "vision": "视觉",
    "language": "语言",
    "nlp": "自然语言处理",
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
    "ai-detection": "AI Detection",
    "comparison": "Comparison",
    "protein-language-model": "蛋白语言模型",
    "vision-language-model": "视觉语言模型",
    "computer-vision": "计算机视觉",
    "bioinformatics": "生物信息学",
}


TOPIC_KEY_ALIASES = {
    "ai-detection": {
        "ai detection",
        "ai-detection",
        "ai 检测",
        "ai检测",
        "aigc detection",
        "aigc-detection",
        "aigc 检测",
        "aigc检测",
        "ai generated content detection",
        "ai-generated content detection",
        "生成内容检测",
        "生成式内容检测",
        "ai生成内容检测",
        "llm detection",
        "llm 检测",
        "llm检测",
        "deepfake detection",
        "deepfake 检测",
        "deepfake检测",
        "synthetic media detection",
    },
}

PUSH_CATEGORY_LABELS = {
    "must_read": "🔒 必读",
    "high_relevant": "🔴 高度相关",
    "maybe_interested": "🟡 可能感兴趣",
    "edge_relevant": "🔵 边缘相关",
}

CATEGORY_PRIORITY = {
    "must_read": 4,
    "high_relevant": 3,
    "maybe_interested": 2,
    "edge_relevant": 1,
}


def get_current_user_id() -> str:
    """
    从 roles.json 获取当前角色的 user_id

    Returns:
        用户 ID，如果 roles.json 不存在则返回 open_id
    """
    import json
    roles_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "roles.json")
    try:
        with open(roles_path, 'r', encoding='utf-8') as f:
            roles_data = json.load(f)
        current_role = roles_data.get("current_role", "")
        if current_role and current_role in roles_data.get("roles", {}):
            return roles_data["roles"][current_role].get("user_id", "user_default")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return "user_default"


def send_message(text: str, chat_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    发送消息的辅助函数

    Args:
        text: 消息内容
        chat_id: 聊天 ID（优先使用）
        user_id: 用户 open_id（备选）
    """
    if chat_id:
        return send_text(chat_id, text, use_chat_id=True)
    elif user_id:
        return send_text(user_id, text)
    else:
        return {"success": False, "error": "No chat_id or user_id"}


def format_direction_label(direction: str) -> str:
    """Format internal topic keys into user-facing labels."""
    formatter = getattr(direction_lexicon, "format_direction_label", None)
    if callable(formatter):
        return str(formatter(direction, prefer_chinese=True) or direction)
    entry = get_direction_entry(direction)
    if entry:
        return str(entry.get("name_cn") or entry.get("name") or direction)
    if direction in DIRECTION_TRANSLATIONS:
        return DIRECTION_TRANSLATIONS[direction]
    if any(separator in direction for separator in ("-", "_")):
        return direction.replace("_", " ").replace("-", " ").title()
    if re.fullmatch(r"[a-z0-9]+", direction):
        return direction.upper() if len(direction) <= 4 else direction.title()
    return direction


def is_displayable_author_name(author_name: str) -> bool:
    """Filter obviously corrupted author keys from profile summaries."""
    if not author_name:
        return False
    stripped = author_name.strip()
    if not stripped:
        return False
    if stripped.startswith("[") or stripped.startswith("{"):
        return False
    if len(stripped) > 80:
        return False
    return True


def load_roles_meta() -> Dict[str, Any]:
    """Load role metadata if available."""
    if os.path.exists(ROLE_META_PATH):
        with open(ROLE_META_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"roles": {}, "current_role": None}


def get_role_meta_for_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Find the role metadata entry that belongs to a given user."""
    roles_meta = load_roles_meta()
    for role_name, role_info in roles_meta.get("roles", {}).items():
        if role_info.get("user_id") == user_id:
            role_copy = dict(role_info)
            role_copy["role_name"] = role_name
            return role_copy
    return None


def resolve_role_chat_id(user_id: str, profile: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Resolve the Feishu chat target for a role user."""
    if profile and profile.get("feishu_chat_id"):
        return profile.get("feishu_chat_id")

    role_meta = get_role_meta_for_user(user_id)
    if role_meta:
        return role_meta.get("feishu_chat_id")

    return None


def profile_needs_bootstrap(profile: Dict[str, Any]) -> bool:
    """Detect profiles that still only contain the role shell but no cold-start result."""
    return not profile.get("core_directions") and not profile.get("topic_weights")


def repair_profile_from_role_description(user_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Backfill missing cold-start fields from role metadata when possible."""
    if not profile or not profile_needs_bootstrap(profile):
        return profile

    role_meta = get_role_meta_for_user(user_id)
    if not role_meta:
        return profile

    bootstrap_text = (
        role_meta.get("natural_language")
        or role_meta.get("bootstrap_summary")
        or role_meta.get("description")
        or ""
    ).strip()
    if not bootstrap_text:
        return profile

    coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
    parsed = coldstart_agent.parse_natural_language(bootstrap_text)

    repaired_profile = dict(profile)
    for field in ("core_directions", "methodology_preferences", "topic_weights", "interest_vector", "taste_profile"):
        value = parsed.get(field)
        if value:
            repaired_profile[field] = value

    repaired_profile["updated_at"] = datetime.now().isoformat()
    update_profile(user_id, repaired_profile)
    return repaired_profile


def format_profile_message(profile: Dict[str, Any]) -> str:
    """Render the profile using the PDF-style section layout."""
    version = profile.get("version", "0.1")
    reading_history = profile.get("reading_history", [])
    stage = "持续学习" if reading_history else "冷启动"

    lines = [f"📋 你的学术画像（v{version} - {stage}）", ""]

    lines.append("━━━ 核心方向 ━━━")
    core_directions = profile.get("core_directions", {}) or {}
    if core_directions:
        for direction, weight in sorted(core_directions.items(), key=lambda item: -item[1]):
            label = format_direction_label(direction)
            normalized_weight = max(0.0, min(float(weight), 1.0))
            bar_length = max(1, int(round(normalized_weight * 10)))
            bar = "█" * bar_length + "░" * (10 - bar_length)
            lines.append(f"{label} [{bar}] 权重：{normalized_weight:.2f}")
    else:
        lines.append("（当前还没有稳定的方向标签，建议补一句研究方向或重新冷启动）")
    lines.append("")

    lines.append("━━━ 方法论偏好 ━━━")
    method_prefs = profile.get("methodology_preferences", {}) or {}
    if method_prefs:
        data_pref = method_prefs.get("preference_data_driven_over_theory")
        if data_pref is True:
            lines.append("├── 偏好数据驱动 > 纯理论")
        elif data_pref is False:
            lines.append("├── 偏好纯理论 > 数据驱动")
        else:
            lines.append("├── 数据驱动 / 纯理论：暂无明确信号")

        systematic_pref = method_prefs.get("preference_systematic_work_over_incremental")
        if systematic_pref is True:
            lines.append("├── 偏好系统性工作 > 单点改进")
        elif systematic_pref is False:
            lines.append("├── 偏好单点改进 > 系统性工作")
        else:
            lines.append("├── 系统性工作 / 单点改进：暂无明确信号")

        lines.append(
            "├── 偏好有开源代码的工作"
            if method_prefs.get("preference_open_source_code")
            else "├── 对开源代码暂无明显偏好"
        )
        lines.append(
            "└── 偏好有生物/科学应用场景的工作"
            if method_prefs.get("preference_bio_science_application")
            else "└── 当前偏向通用研究场景"
        )
    else:
        lines.append("（暂无方法论偏好信号）")
    lines.append("")

    lines.append("━━━ 必读清单 ━━━")
    must_read = profile.get("must_read", {}) or {}
    lines.append(f"作者：{', '.join(must_read.get('authors', [])) or '（空，待你添加）'}")
    lines.append(f"机构：{', '.join(must_read.get('institutions', [])) or '（空，待你添加）'}")
    lines.append(f"关键词：{', '.join(must_read.get('keywords', [])) or '（空，待你添加）'}")
    lines.append(COLD_START_MUST_READ_NOTE)

    author_heat = profile.get("author_heat", {}) or {}
    filtered_author_heat = {
        author: heat for author, heat in author_heat.items() if is_displayable_author_name(author)
    }
    if filtered_author_heat:
        top_authors = sorted(filtered_author_heat.items(), key=lambda item: -item[1])[:3]
        lines.append("")
        lines.append("━━━ 最近学到的作者偏好 ━━━")
        for author, heat in top_authors:
            lines.append(f"{author}（热度：{heat:.2f}）")

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━",
            "你可以直接说：",
            '  "加个必读作者：XXX"',
            CLEAR_READING_LIST_HINT,
            '  "降低 GUI Agent 权重"',
            '  "我最近对 protein language model 更感兴趣了"',
        ]
    )

    return "\n".join(lines)


def build_empty_profile(user_id: str) -> Dict[str, Any]:
    """Create the default profile shell used before cold start completes."""
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
        "report_preferences": {
            "positive_feedback_count": 0,
            "negative_feedback_count": 0,
            "preferred_evidence_top_k": 3,
        },
        "reading_history": [],
        "behavior_logs": [],
        "drift_state": build_default_drift_state(now),
    }


def normalize_topic_token(value: str) -> str:
    """Normalize topic labels for fuzzy matching."""
    return re.sub(r"[\s_\-]+", "", (value or "").strip().lower())


def get_canonical_topic_aliases(topic_key: str) -> List[str]:
    """Return canonical aliases for a known topic key."""
    entry = get_direction_entry(topic_key)
    if entry:
        aliases = {
            entry.get("canonical_name", topic_key),
            entry.get("name", ""),
            entry.get("name_cn", ""),
            *(entry.get("aliases", []) or []),
            *(entry.get("paper_terms", []) or []),
        }
        return [alias for alias in aliases if alias]

    aliases = {
        topic_key,
        topic_key.replace("-", " "),
        topic_key.replace("_", " "),
        DIRECTION_TRANSLATIONS.get(topic_key, ""),
    }
    aliases.update(TOPIC_KEY_ALIASES.get(topic_key, set()))
    return [alias for alias in aliases if alias]


def resolve_canonical_topic_key(topic_text: str) -> Optional[str]:
    """Map user-facing topic aliases onto a stable internal key when known."""
    resolved = resolve_canonical_direction(topic_text, include_paper_terms=True)
    if resolved:
        return str(resolved.get("canonical_name"))

    target = normalize_topic_token(topic_text)
    if not target:
        return None

    for topic_key in DIRECTION_TRANSLATIONS.keys():
        alias_tokens = {
            normalize_topic_token(alias)
            for alias in get_canonical_topic_aliases(topic_key)
            if normalize_topic_token(alias)
        }
        if target in alias_tokens:
            return topic_key

    return None


SEMANTIC_TOPIC_FAMILIES = {
    "language_family": {
        "aliases": {
            "language",
            "语言",
            "自然语言处理",
            "nlp",
        },
        "members": {
            "language",
            "nlp",
        },
    },
}


def resolve_semantic_topic_family(topic_text: str) -> Optional[str]:
    """Resolve broad user-facing topic names to a stable semantic family."""
    target = normalize_topic_token(topic_text)
    if not target:
        return None

    for family_name, family in SEMANTIC_TOPIC_FAMILIES.items():
        alias_tokens = {normalize_topic_token(alias) for alias in family.get("aliases", set())}
        if target in alias_tokens:
            return family_name
    return None


def derive_topic_key(topic: str) -> str:
    """Turn free-form topic text into a stable profile key."""
    cleaned = re.sub(r"\s+", " ", (topic or "").strip().strip("“”\"'`"))
    canonical_key = resolve_canonical_topic_key(cleaned)
    if canonical_key:
        return canonical_key
    normalized = normalize_direction_key(cleaned)
    return normalized or cleaned.lower()


def clamp_weight(value: float, minimum: float = 0.1, maximum: float = 0.95) -> float:
    """Clamp profile weights into a safe displayable range."""
    return max(minimum, min(maximum, round(float(value), 2)))


def iter_topic_aliases(topic_key: str) -> List[str]:
    """Return user-facing aliases for a topic key."""
    aliases = set(get_canonical_topic_aliases(topic_key))
    aliases.add(format_direction_label(topic_key))
    return [alias for alias in aliases if alias]


def find_related_profile_topic_keys(
    profile: Dict[str, Any],
    topic_text: str,
    *,
    include_semantic_family: bool = False,
) -> List[str]:
    """Resolve one topic phrase to one or more matching stored profile keys."""
    target = normalize_topic_token(topic_text)
    if not target:
        return []

    keys: List[str] = []
    for container_name in ("core_directions", "topic_weights"):
        container = profile.get(container_name, {}) or {}
        for key in container.keys():
            if key not in keys:
                keys.append(key)

    exact_matches: List[str] = []
    partial_matches: List[tuple[int, str]] = []
    for key in keys:
        alias_norms = [
            normalize_topic_token(alias)
            for alias in iter_topic_aliases(key)
            if normalize_topic_token(alias)
        ]
        if target in alias_norms:
            if key not in exact_matches:
                exact_matches.append(key)
            continue

        for alias_norm in alias_norms:
            if target in alias_norm or alias_norm in target:
                partial_matches.append((abs(len(alias_norm) - len(target)), key))
                break

    semantic_matches: List[str] = []
    if include_semantic_family:
        family_name = resolve_semantic_topic_family(topic_text)
        if family_name:
            member_tokens = {
                normalize_topic_token(member)
                for member in SEMANTIC_TOPIC_FAMILIES[family_name].get("members", set())
            }
            for key in keys:
                if normalize_topic_token(key) in member_tokens and key not in semantic_matches:
                    semantic_matches.append(key)

    ordered_matches: List[str] = []
    for key in exact_matches + semantic_matches:
        if key not in ordered_matches:
            ordered_matches.append(key)

    if ordered_matches:
        return ordered_matches

    partial_matches.sort(key=lambda item: item[0])
    for _, key in partial_matches:
        if key not in ordered_matches:
            ordered_matches.append(key)

    return ordered_matches


def get_profile_topic_context(profile: Optional[Dict[str, Any]]) -> List[str]:
    """Build a compact user-facing topic list to ground LLM profile edits."""
    if not profile:
        return []

    topics: List[str] = []
    for container_name in ("core_directions", "topic_weights"):
        container = profile.get(container_name, {}) or {}
        for key in container.keys():
            for alias in iter_topic_aliases(key):
                if alias not in topics:
                    topics.append(alias)
    return topics


def find_profile_topic_key(profile: Dict[str, Any], topic_text: str) -> Optional[str]:
    """Resolve a free-form topic label back to the stored profile key when possible."""
    matches = find_related_profile_topic_keys(profile, topic_text)
    return matches[0] if matches else None


def _parse_profile_update_with_llm(text: str, profile: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """使用 LLM 解析画像更新请求（规则匹配失败时的兜底）"""
    try:
        llm_parser = importlib.import_module("agents.master-coordinator.scripts.llm_parser")
        result = llm_parser.parse_intent_with_llm(
            text,
            known_topics=get_profile_topic_context(profile),
        )

        if not result:
            return None

        action = result.get("action", "unknown")
        if action == "unknown":
            return None

        # 转换为本地格式
        if action in ("adjust_interest", "adjust_weight"):
            topics = result.get("topics", [])
            if not topics:
                return None

            return {
                "action": action,
                "direction": result.get("direction", "increase"),
                "topic": topics[0],  # 取第一个主题
                "topics": topics,  # 保留所有主题供后续使用
                "from_llm": True,
            }

        return result

    except Exception as e:
        logger.warning(f"LLM fallback failed for '{text}': {e}")
        return None


CONFIRM_DIRECTION_RE = re.compile(r"^\s*确认方向\s*[:：]?\s*(?P<topic>.+?)\s*$", flags=re.IGNORECASE)


def parse_confirm_direction_request(text: str) -> Optional[str]:
    """Parse a pending-direction confirmation command."""
    cleaned = first_meaningful_line(text)
    if not cleaned:
        return None
    match = CONFIRM_DIRECTION_RE.match(cleaned)
    if not match:
        return None
    topic = clean_profile_topic_text(match.group("topic"), strip_domain_suffix=True)
    return topic or None


def normalize_profile_update_topics(topic_texts: List[str], user_id: str) -> Dict[str, Any]:
    """Normalize one or more free-form topic texts through the shared direction layer."""
    llm_parser = importlib.import_module("agents.master-coordinator.scripts.llm_parser")

    canonical_directions: List[Dict[str, Any]] = []
    temporary_matches: List[Dict[str, Any]] = []
    pending_candidates: List[Dict[str, Any]] = []
    explanations: List[str] = []
    seen_canonical: set[str] = set()
    seen_temporary: set[tuple[str, str]] = set()
    seen_pending: set[str] = set()
    profile = get_profile(user_id) or {}

    for topic_text in topic_texts:
        cleaned = clean_profile_topic_text(topic_text)
        if not cleaned:
            continue

        profile_key = find_profile_topic_key(profile, cleaned)
        if profile_key and profile_key not in seen_canonical:
            seen_canonical.add(profile_key)
            canonical_directions.append(
                {
                    "name": profile_key,
                    "name_cn": format_direction_label(profile_key),
                    "confidence": 1.0,
                    "source_text": cleaned,
                    "is_known": True,
                }
            )
            continue

        resolved = resolve_canonical_direction(cleaned, include_paper_terms=True)
        if resolved:
            direction_name = str(resolved.get("canonical_name") or "").strip()
            if direction_name and direction_name not in seen_canonical:
                entry = resolved.get("entry") or {}
                seen_canonical.add(direction_name)
                canonical_directions.append(
                    {
                        "name": direction_name,
                        "name_cn": str(entry.get("name_cn") or entry.get("name") or direction_name),
                        "confidence": 1.0,
                        "source_text": cleaned,
                        "is_known": True,
                    }
                )
            continue

        normalized = llm_parser.normalize_research_directions(
            cleaned,
            auto_persist_known_aliases=True,
            user_id=user_id,
        )
        for direction in normalized.get("canonical_directions", []):
            direction_name = str(direction.get("name") or "").strip()
            if not direction_name or direction_name in seen_canonical:
                continue
            seen_canonical.add(direction_name)
            canonical_directions.append(direction)
        for match in normalized.get("temporary_matches", []):
            marker = (
                str(match.get("source_text") or "").strip().casefold(),
                str(match.get("canonical_name") or "").strip(),
            )
            if not marker[0] or marker in seen_temporary:
                continue
            seen_temporary.add(marker)
            temporary_matches.append(match)
        for candidate in normalized.get("pending_candidates", []):
            candidate_key = str(candidate.get("candidate_key") or "").strip()
            if not candidate_key or candidate_key in seen_pending:
                continue
            seen_pending.add(candidate_key)
            pending_candidates.append(candidate)
        for explanation in normalized.get("explanations", []):
            note = str(explanation or "").strip()
            if note and note not in explanations:
                explanations.append(note)

    return {
        "canonical_directions": canonical_directions,
        "temporary_matches": temporary_matches,
        "pending_candidates": pending_candidates,
        "explanations": explanations,
    }


def format_pending_direction_prompt(pending_candidates: List[Dict[str, Any]]) -> str:
    """Format a short confirmation prompt for pending canonical directions."""
    if not pending_candidates:
        return ""
    if len(pending_candidates) == 1:
        candidate = pending_candidates[0]
        label = candidate.get("name_cn") or candidate.get("name") or candidate.get("candidate_key")
        return f"发现候选新方向：{label}，回复“确认方向：{label}”后纳入统一方向库。"

    lines = ["发现候选新方向，请任选其一确认："]
    for candidate in pending_candidates[:3]:
        label = candidate.get("name_cn") or candidate.get("name") or candidate.get("candidate_key")
        lines.append(f"- {label}：回复“确认方向：{label}”")
    return "\n".join(lines)


def merge_unique_message_sections(*sections: Any) -> str:
    """Join message sections once while preserving their original order."""
    merged: List[str] = []
    seen: set[str] = set()

    for section in sections:
        text = str(section or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)

    return "\n".join(merged)


BOT_AUTHORED_PREFIXES = (
    "📋 你的学术画像",
    "PaperFlow 学术画像确认",
    "📰 今日论文",
    "📊 今日反馈已记录",
    "收到，",
    "收到 PDF，",
    "抱歉，",
    "已增强你对",
    "已下调你对",
    "已将 ",
)

COLD_START_MUST_READ_NOTE = "说明：普通“冷启动”会保留这份必读清单；只有“重新冷启动”才会重置。"
CLEAR_READING_LIST_HINT = '  "清空精读列表"'


def first_meaningful_line(text: Any) -> str:
    """Use only the leading content line so bot examples do not get reparsed as user input."""
    for raw_line in str(text or "").splitlines():
        cleaned = raw_line.strip().strip("\"'")
        if cleaned:
            return cleaned
    return ""


def detect_explicit_command_intent(text: Any) -> Optional[Dict[str, Any]]:
    """Fast-path obvious commands so they never go through the profile-update LLM."""
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if not lowered:
        return None

    confirmed_direction = parse_confirm_direction_request(cleaned)
    if confirmed_direction:
        return {
            "intent": "confirm_direction",
            "confidence": 1.0,
            "slots": {"topic": confirmed_direction},
        }

    cold_start_commands = {"cold start", "cold-start", "冷启动", "重新冷启动"}
    daily_push_commands = {"daily push", "推送", "今日论文", "今天论文", "来一篇", "来几篇"}
    reading_commands = {"read this", "deep read", "精读"}
    weekly_report_commands = {"weekly report", "周报"}
    must_read_commands = {"必读", "必读清单"}
    profile_commands = {
        "profile",
        "画像",
        "学术画像",
        "我的画像",
        "我的学术画像",
        "显示画像",
        "显示学术画像",
    }
    feedback_commands = {"all red", "all lock", "none", "全部", "没有"}

    scholar_url = extract_google_scholar_url(cleaned)
    if scholar_url:
        return {
            "intent": "cold_start",
            "confidence": 1.0,
            "slots": {"text": cleaned, "scholar_url": scholar_url},
        }

    pdf_url = extract_pdf_url(text)
    if pdf_url:
        return {
            "intent": "reading_report",
            "confidence": 1.0,
            "slots": {
                "pdf_url": pdf_url,
                "title_hint": normalize_direct_pdf_title_hint(strip_pdf_url(text)),
            },
        }

    homepage_url = extract_homepage_url(cleaned)
    if homepage_url:
        return {
            "intent": "cold_start",
            "confidence": 1.0,
            "slots": {"text": cleaned, "homepage_url": homepage_url},
        }

    if looks_like_clear_reading_list_command(cleaned):
        return {"intent": "clear_reading_list", "confidence": 1.0, "slots": {}}

    if lowered in cold_start_commands:
        return {"intent": "cold_start", "confidence": 1.0, "slots": {"text": cleaned}}
    if lowered in daily_push_commands:
        return {"intent": "daily_push", "confidence": 1.0, "slots": {}}
    if lowered in reading_commands:
        return {"intent": "reading_report", "confidence": 1.0, "slots": {}}
    if lowered in weekly_report_commands:
        return {"intent": "weekly_report", "confidence": 1.0, "slots": {}}
    if lowered in must_read_commands:
        return {"intent": "must_read", "confidence": 1.0, "slots": {"command": cleaned}}
    if lowered in profile_commands:
        return {"intent": "show_profile", "confidence": 1.0, "slots": {}}
    if lowered in feedback_commands:
        return {"intent": "feedback", "confidence": 1.0, "slots": {"reply": cleaned}}
    if re.fullmatch(r"[\d\s,\-，、]+", cleaned) and re.search(r"\d", cleaned):
        return {"intent": "feedback", "confidence": 1.0, "slots": {"reply": cleaned}}

    return None


def looks_like_bot_authored_message(text: Any) -> bool:
    """Detect assistant-authored cards / confirmations that should never be rerouted."""
    normalized = str(text or "").strip()
    if not normalized:
        return False

    if any(normalized.startswith(prefix) for prefix in BOT_AUTHORED_PREFIXES):
        return True

    if "你的学术画像" in normalized and "你可以直接说：" in normalized:
        return True

    if "你的学术画像周度报告" in normalized and "推送论文总数" in normalized:
        return True

    if "今日反馈已记录" in normalized and "画像已更新" in normalized:
        return True

    if "选择方式（任选）" in normalized and "快捷命令" in normalized:
        return True

    if "Reading reports created (" in normalized and "Open the links above to start reading." in normalized:
        return True

    if "Reading reports created (" in normalized and "doc_token:" in normalized:
        return True

    if normalized.startswith("收到 PDF，") and "正在生成精读报告" in normalized:
        return True

    if normalized.startswith("[精读]"):
        return True

    if "必读清单" in normalized and "添加方式：" in normalized and "移除方式：" in normalized:
        return True

    if "学术画像已更新" in normalized and "最后更新" in normalized and "你可以随时回复调整" in normalized:
        return True

    return False


def safe_console_text(text: Any, max_len: int = 120) -> str:
    """Return a console-safe preview that will not crash on Windows GBK terminals."""
    preview = str(text).replace("\r", "").replace("\n", "\\n")[:max_len]
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return preview.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except Exception:
        return preview.encode("ascii", errors="replace").decode("ascii")


PROFILE_WEIGHT_COMMAND_RE = re.compile(
    r"(?P<verb>降低|减少|调低|下调|弱化|提高|增加|调高|上调|强化)\s*(?P<topic>.+?)(?:的?\s*权重)?(?:\s*(?:一点|一些))?$",
    flags=re.IGNORECASE,
)

PROFILE_WEIGHT_TARGET_RE = re.compile(
    r"(?:(?:把|将)\s*)?(?P<topic>.+?)(?:的?\s*权重)?\s*(?P<verb>降低|减少|调低|下调|弱化|提高|增加|调高|上调|强化|设为|设置为|改为|调到|提到|降到)\s*(?:到|为)?\s*(?P<weight>0(?:\.\d+)?|1(?:\.0+)?)$",
    flags=re.IGNORECASE,
)

PROFILE_WEIGHT_TARGET_PREFIX_RE = re.compile(
    r"(?P<verb>降低|减少|调低|下调|弱化|提高|增加|调高|上调|强化)\s*(?P<topic>.+?)(?:的?\s*权重)?\s*(?:到|为)\s*(?P<weight>0(?:\.\d+)?|1(?:\.0+)?)$",
    flags=re.IGNORECASE,
)

PROFILE_NEGATIVE_INTEREST_RE = re.compile(
    r"(?:我(?:最近)?\s*)?(?:对|在)\s*(?P<topic>.+?)\s*(?:不再|不)\s*感兴趣(?:了)?$",
    flags=re.IGNORECASE,
)

PROFILE_SOFT_NEGATIVE_INTEREST_RE = re.compile(
    r"(?:我(?:最近)?\s*)?(?:对|在)\s*(?P<topic>.+?)\s*(?:没那么|不太|不是很)\s*感兴趣(?:了)?$",
    flags=re.IGNORECASE,
)

PROFILE_NEGATIVE_REMOVAL_RE = re.compile(
    r"(?:我\s*)?(?:不需要|不要|去掉|移除|删掉|删除)\s*(?P<topic>.+?)(?:\s*(?:方向|领域|主题))?$",
    flags=re.IGNORECASE,
)

PROFILE_POSITIVE_INTEREST_RE = re.compile(
    r"(?:我(?:最近)?\s*)?(?:对|在)\s*(?P<topic>.+?)\s*(?:更|越来越|重新)?感兴趣(?:了)?$",
    flags=re.IGNORECASE,
)

PROFILE_MORE_ATTENTION_RE = re.compile(
    r"(?:我(?:最近)?|最近)\s*对\s*(?P<topic>.+?)\s*关注更多(?:了)?$",
    flags=re.IGNORECASE,
)

PROFILE_FOCUS_RE = re.compile(
    r"(?:开始|最近|现在|我)\s*(?:更)?关注\s*(?P<topic>.+?)$",
    flags=re.IGNORECASE,
)

MUST_READ_LIST_HINTS = (
    "必读清单",
    "查看必读",
    "显示必读",
    "show must read",
    "show must",
)

MUST_READ_ACTION_HINTS = (
    "加个",
    "添加",
    "增加",
    "去掉",
    "去除",
    "取消",
    "移除",
    "删除",
    "删掉",
    "add",
    "remove",
    "delete",
)

MUST_READ_TARGET_HINTS = (
    "必读作者",
    "必读机构",
    "必读关键词",
    "must read author",
    "must read institution",
    "must read keyword",
)

MUST_READ_TARGET_TOKENS = (
    "作者",
    "机构",
    "关键词",
    "author",
    "institution",
    "keyword",
)

COLD_START_BOOTSTRAP_HINTS = (
    "我是做",
    "我做",
    "我研究",
    "我关注",
    "研究方向",
    "我的方向",
    "方向是",
    "direction:",
    "research direction",
    "i work on",
    "my research",
)

GOOGLE_SCHOLAR_URL_RE = re.compile(
    r"(?P<url>(?:https?://)?(?:scholar\.google\.[^/\s]+)/(?:citations|scholar)\?[^\s]*\buser=[A-Za-z0-9_-]+[^\s]*)",
    re.IGNORECASE,
)

GENERIC_HTTP_URL_RE = re.compile(
    r"(?P<url>(?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?)",
    re.IGNORECASE,
)


def looks_like_must_read_command(text: Any) -> bool:
    """Detect must-read list operations without colliding with profile edits."""
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if not lowered:
        return False

    if looks_like_bot_authored_message(cleaned):
        return False

    if any(hint in lowered for hint in MUST_READ_LIST_HINTS):
        return True

    if any(hint in lowered for hint in MUST_READ_TARGET_HINTS):
        return True

    has_action = any(hint in lowered for hint in MUST_READ_ACTION_HINTS)
    has_target = any(token in cleaned for token in MUST_READ_TARGET_TOKENS) or any(
        token in lowered for token in MUST_READ_TARGET_TOKENS
    )
    if has_action and has_target:
        return True

    return False


def extract_google_scholar_url(text: Any) -> Optional[str]:
    """Extract the first Google Scholar profile URL from arbitrary user text."""
    match = GOOGLE_SCHOLAR_URL_RE.search(str(text or ""))
    if not match:
        return None
    url = str(match.group("url") or "").strip().rstrip(".,);]\u3002\uff0c\uff1b")
    if not url:
        return None
    if "://" not in url:
        url = f"https://{url.lstrip('/')}"
    return url


def looks_like_pdf_http_url(url: Any) -> bool:
    """Heuristic filter for direct PDF-style URLs used for reading reports."""
    candidate = str(url or "").strip()
    if not candidate:
        return False
    if "://" not in candidate:
        candidate = f"https://{candidate.lstrip('/')}"
    lowered = candidate.casefold()
    return (
        lowered.startswith(("http://", "https://"))
        and (
            ".pdf" in lowered
            or "/pdf?" in lowered
            or "/pdf/" in lowered
            or "arxiv.org/pdf/" in lowered
            or "openreview.net/pdf" in lowered
        )
    )


def extract_pdf_url(text: Any) -> Optional[str]:
    """Extract the first PDF-like URL from arbitrary user text."""
    for match in GENERIC_HTTP_URL_RE.finditer(str(text or "")):
        url = str(match.group("url") or "").strip().rstrip(".,);]\u3002\uff0c\uff1b")
        if not url:
            continue
        if "://" not in url:
            url = f"https://{url.lstrip('/')}"
        if looks_like_pdf_http_url(url):
            return url
    return None


def strip_pdf_url(text: Any) -> str:
    """Remove the first PDF URL and lightweight reading command text."""
    raw_text = str(text or "")
    stripped = raw_text
    for match in GENERIC_HTTP_URL_RE.finditer(raw_text):
        raw_url = str(match.group("url") or "").strip().rstrip(".,);]\u3002\uff0c\uff1b")
        if not raw_url:
            continue
        normalized_url = raw_url if "://" in raw_url else f"https://{raw_url.lstrip('/')}"
        if looks_like_pdf_http_url(normalized_url):
            stripped = f"{raw_text[:match.start()]} {raw_text[match.end():]}"
            break
    stripped = re.sub(r"(?i)\b(read this|deep read)\b", " ", stripped)
    stripped = re.sub(r"精读", " ", stripped)
    return first_meaningful_line(re.sub(r"\s+", " ", stripped)).strip(" \t\r\n:：-")


def normalize_direct_pdf_title_hint(text: Any) -> str:
    """Keep only meaningful custom title hints for direct PDF-link reading."""
    candidate = str(text or "").strip()
    if not candidate:
        return ""
    normalized = candidate.casefold()
    generic_hints = {
        "paper",
        "pdf",
        "论文",
        "这篇",
        "这个",
        "这个pdf",
        "这篇论文",
        "帮我看看这个",
        "帮我读一下",
        "读一下",
        "看看这个",
    }
    if normalized in generic_hints or len(candidate) <= 4:
        return ""
    return candidate


def strip_google_scholar_url(text: Any) -> str:
    """Remove the first Google Scholar URL from user text and normalize whitespace."""
    stripped = GOOGLE_SCHOLAR_URL_RE.sub(" ", str(text or ""), count=1)
    return first_meaningful_line(re.sub(r"\s+", " ", stripped)).strip()


def looks_like_homepage_url(url: Any) -> bool:
    """Heuristic filter for personal / lab homepages used in cold start."""
    candidate = str(url or "").strip()
    if not candidate:
        return False
    lowered = candidate.casefold()
    if "scholar.google." in lowered:
        return False
    blocked_markers = (
        "arxiv.org",
        "openreview.net",
        "doi.org",
        "science.org",
        "nature.com",
        "cell.com",
        "pnas.org",
        "pubmed",
        ".pdf",
        "/abs/",
        "/pdf/",
        "/doi/",
        "/article/",
    )
    return not any(marker in lowered for marker in blocked_markers)


def extract_homepage_url(text: Any) -> Optional[str]:
    """Extract the first plausible personal homepage URL from arbitrary user text."""
    for match in GENERIC_HTTP_URL_RE.finditer(str(text or "")):
        url = str(match.group("url") or "").strip().rstrip(".,);]\u3002\uff0c\uff1b")
        if not url:
            continue
        if "://" not in url:
            url = f"https://{url.lstrip('/')}"
        if looks_like_homepage_url(url):
            return url
    return None


def strip_bootstrap_urls(text: Any) -> str:
    """Remove Scholar / homepage URLs from bootstrap text and normalize whitespace."""
    stripped = GOOGLE_SCHOLAR_URL_RE.sub(" ", str(text or ""), count=1)
    stripped = GENERIC_HTTP_URL_RE.sub(" ", stripped, count=1)
    return first_meaningful_line(re.sub(r"\s+", " ", stripped)).strip()


def detect_expand_push_request(text: Any) -> Optional[Dict[str, Any]]:
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if not lowered:
        return None
    if not any(token in cleaned for token in ("展开", "再看看", "遗漏", "补看", "看看")):
        return None

    category = ""
    if any(token in cleaned for token in ("🔒", "必读", "lock")):
        category = "must_read"
    elif any(token in cleaned for token in ("🔴", "红", "高度相关", "red")):
        category = "high_relevant"
    elif any(token in cleaned for token in ("🟡", "黄", "可能感兴趣")):
        category = "maybe_interested"
    elif any(token in cleaned for token in ("🔵", "蓝", "边缘相关")):
        category = "edge_relevant"

    query = ""
    match = re.search(r"展开\s*([^\s，。,；;]+?)\s*(?:分组|方向)?$", cleaned)
    if match:
        query = match.group(1).strip()
    elif "遗漏" in cleaned and not category:
        category = "maybe_interested"

    if not category and not query:
        return None
    return {"category": category, "query": query}


def detect_classification_correction_request(text: Any) -> Optional[Dict[str, Any]]:
    cleaned = first_meaningful_line(text)
    if not cleaned or "应该" not in cleaned:
        return None

    number_match = re.search(r"(\d{1,3})", cleaned)
    if not number_match:
        return None
    paper_number = int(number_match.group(1))

    target_category = ""
    if any(token in cleaned for token in ("🔒", "必读")):
        target_category = "must_read"
    elif any(token in cleaned for token in ("🔴", "红", "高度相关")):
        target_category = "high_relevant"
    elif any(token in cleaned for token in ("🟡", "黄", "可能感兴趣")):
        target_category = "maybe_interested"
    elif any(token in cleaned for token in ("🔵", "蓝", "边缘相关")):
        target_category = "edge_relevant"

    if not target_category:
        return None
    return {"paper_number": paper_number, "target_category": target_category}


def detect_report_feedback_request(text: Any) -> Optional[Dict[str, Any]]:
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if not lowered:
        return None

    positive_markers = ("写得好", "很好", "有用", "抓住重点", "挺好", "不错")
    negative_markers = ("没抓住重点", "不够完整", "太浅", "太空", "不太行", "没用", "一般")
    if "报告" not in cleaned and "精读" not in cleaned and "这篇" not in cleaned:
        return None
    if any(token in cleaned for token in negative_markers):
        return {"sentiment": "negative"}
    if any(token in cleaned for token in positive_markers):
        return {"sentiment": "positive"}
    return None


def detect_reviewer_watch_request(text: Any) -> Optional[Dict[str, Any]]:
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if "reviewer" not in lowered and "审稿" not in cleaned:
        return None
    conference_match = re.search(r"\b(ICLR|NeurIPS|ICML|ACL|EMNLP)\b", cleaned, flags=re.I)
    year_match = re.search(r"\b(20\d{2})\b", cleaned)
    if not conference_match:
        return None
    return {
        "conference": conference_match.group(1).lower(),
        "year": int(year_match.group(1)) if year_match else datetime.now().year,
    }


def looks_like_cold_start_description(text: Any, profile: Optional[Dict[str, Any]] = None) -> bool:
    """Route free-form self-descriptions to cold start only when bootstrap is actually needed."""
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if not lowered:
        return False

    if looks_like_bot_authored_message(cleaned):
        return False

    if lowered in {"冷启动", "重新冷启动", "cold start", "cold-start"}:
        return True

    if any(token in lowered for token in ("初始画像", "设置方向")):
        return True

    if extract_google_scholar_url(cleaned):
        return True
    if extract_homepage_url(cleaned):
        return True

    if profile and not profile_needs_bootstrap(profile):
        return False

    return any(token in cleaned for token in COLD_START_BOOTSTRAP_HINTS) or any(
        token in lowered for token in COLD_START_BOOTSTRAP_HINTS
    )


def should_reset_existing_profile_for_cold_start(text: Any) -> bool:
    """Reset only for explicit rebuild commands, not ordinary cold-start refreshes."""
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if not lowered:
        return False

    return (
        cleaned.startswith("重新冷启动")
        or lowered.startswith("reset cold start")
        or lowered.startswith("re-cold-start")
        or lowered.startswith("re cold start")
    )


def looks_like_clear_reading_list_command(text: Any) -> bool:
    """Detect explicit requests to clear the current pending reading queue."""
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if not lowered:
        return False

    if lowered in {"clear reading list", "clear reading queue"}:
        return True

    return bool(
        re.search(r"(清空|清理|清掉|重置).*(精读列表|精读队列|待精读|已选论文)", cleaned)
    )


def clean_profile_topic_text(topic: str, *, strip_domain_suffix: bool = False) -> str:
    """Trim topic text extracted from profile-update messages."""
    cleaned = re.sub(r"\s+", " ", (topic or "").strip().strip("“”\"'`"))
    cleaned = cleaned.strip("，。！？,.!?；;：:()（）[]【】")
    if strip_domain_suffix:
        cleaned = re.sub(r"\s*(?:方向|领域|主题)$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def parse_weight_target(value: Any) -> Optional[float]:
    """Parse an explicit target weight expressed as a 0-1 decimal."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        return None
    if 0.0 <= parsed <= 1.0:
        return parsed
    return None


def build_profile_update_result(
    action: str,
    direction: str,
    topic: str,
    *,
    strip_domain_suffix: bool = False,
    weight_target: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Build a normalized profile-update payload."""
    cleaned_topic = clean_profile_topic_text(topic, strip_domain_suffix=strip_domain_suffix)
    if not cleaned_topic:
        return None
    result = {
        "action": action,
        "direction": direction,
        "topic": cleaned_topic,
    }
    if weight_target is not None:
        result["weight_target"] = weight_target
    return result


def parse_profile_update_request(text: str, profile: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Safe profile-update parser that prioritizes exact commands and reliable patterns."""
    cleaned = first_meaningful_line(text)
    if not cleaned:
        return None

    if looks_like_bot_authored_message(cleaned):
        return None

    if detect_explicit_command_intent(cleaned):
        return None

    if looks_like_must_read_command(cleaned):
        return None

    if looks_like_cold_start_description(cleaned, profile=profile):
        return None

    for pattern in (PROFILE_WEIGHT_TARGET_RE, PROFILE_WEIGHT_TARGET_PREFIX_RE):
        weight_target_match = pattern.search(cleaned)
        if not weight_target_match:
            continue
        verb = weight_target_match.group("verb")
        target_weight = parse_weight_target(weight_target_match.group("weight"))
        if target_weight is None:
            continue
        return build_profile_update_result(
            "adjust_weight",
            "decrease" if verb in {"降低", "减少", "调低", "下调", "弱化", "降到"} else "increase",
            weight_target_match.group("topic"),
            weight_target=target_weight,
        )

    weight_match = PROFILE_WEIGHT_COMMAND_RE.search(cleaned)
    if weight_match:
        verb = weight_match.group("verb")
        return build_profile_update_result(
            "adjust_weight",
            "decrease" if verb in {"降低", "减少", "调低", "下调", "弱化"} else "increase",
            weight_match.group("topic"),
        )

    negative_interest_match = PROFILE_NEGATIVE_INTEREST_RE.search(cleaned)
    if negative_interest_match:
        return build_profile_update_result(
            "adjust_interest",
            "decrease",
            negative_interest_match.group("topic"),
        )

    soft_negative_interest_match = PROFILE_SOFT_NEGATIVE_INTEREST_RE.search(cleaned)
    if soft_negative_interest_match:
        return build_profile_update_result(
            "adjust_interest",
            "decrease",
            soft_negative_interest_match.group("topic"),
        )

    negative_removal_match = PROFILE_NEGATIVE_REMOVAL_RE.search(cleaned)
    if negative_removal_match:
        return build_profile_update_result(
            "remove_topic",
            "remove",
            negative_removal_match.group("topic"),
            strip_domain_suffix=True,
        )

    positive_interest_match = PROFILE_POSITIVE_INTEREST_RE.search(cleaned)
    if positive_interest_match:
        return build_profile_update_result(
            "adjust_interest",
            "increase",
            positive_interest_match.group("topic"),
        )

    more_attention_match = PROFILE_MORE_ATTENTION_RE.search(cleaned)
    if more_attention_match:
        return build_profile_update_result(
            "adjust_interest",
            "increase",
            more_attention_match.group("topic"),
        )

    focus_match = PROFILE_FOCUS_RE.search(cleaned)
    if focus_match:
        return build_profile_update_result(
            "adjust_interest",
            "increase",
            focus_match.group("topic").removesuffix("更多"),
        )

    llm_result = _parse_profile_update_with_llm(cleaned, profile=profile)
    if llm_result:
        logger.info(f"LLM-first parsed profile update: {cleaned} -> {llm_result}")
        return llm_result

    return None


class MasterCoordinator:
    """主协调器"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        feishu_user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        send_to_feishu: bool = True,
    ):
        """
        初始化协调器

        Args:
            user_id: 用户 ID（可选，如果为空则从 roles.json 获取）
            feishu_user_id: 飞书用户 ID（用于 open_id 发送）
            chat_id: 聊天 ID（用于 chat_id 发送，优先级更高）
            send_to_feishu: 是否允许发送飞书消息；命令行 dry-run/--no-feishu 会关闭
        """
        # 优先使用传入的 user_id，如果没有则从 roles.json 获取
        if user_id:
            self.user_id = user_id
        else:
            roles_user_id = get_current_user_id()
            self.user_id = roles_user_id if roles_user_id != "user_default" else "user_unknown"
        self.send_to_feishu = send_to_feishu
        self.feishu_user_id = (feishu_user_id or os.environ.get("FEISHU_USER_ID", "")) if send_to_feishu else ""
        self.profile = get_profile(self.user_id)
        self.role_meta = get_role_meta_for_user(self.user_id) or {}
        self.role_name = self.role_meta.get("role_name")
        # 优先使用传入 chat_id，否则回退到角色绑定的 chat_id，避免误发到默认个人账号
        self.chat_id = (chat_id or resolve_role_chat_id(self.user_id, self.profile)) if send_to_feishu else None

    def detect_intent(self, text: str) -> Dict[str, Any]:
        """
        检测用户意图

        Args:
            text: 用户输入文本

        Returns:
            意图字典 {"intent": "...", "confidence": 0.0-1.0, "slots": {}}
        """
        cleaned = first_meaningful_line(text)
        text_lower = cleaned.lower().strip()

        if looks_like_bot_authored_message(text):
            return {"intent": "ignore", "confidence": 1.0, "slots": {}}

        explicit_command = detect_explicit_command_intent(text)
        if explicit_command:
            return explicit_command

        # 角色管理
        role_keywords = ["角色", "role", "切换", "create role", "删除角色"]
        if any(kw in text_lower for kw in role_keywords):
            return {"intent": "role_manager", "confidence": 0.85, "slots": {"command": text}}

        if looks_like_must_read_command(text):
            return {"intent": "must_read", "confidence": 0.95, "slots": {"command": cleaned}}

        expand_request = detect_expand_push_request(text)
        if expand_request:
            return {"intent": "expand_push", "confidence": 0.9, "slots": expand_request}

        correction_request = detect_classification_correction_request(text)
        if correction_request:
            return {"intent": "classification_correction", "confidence": 0.92, "slots": correction_request}

        report_feedback = detect_report_feedback_request(text)
        if report_feedback:
            return {"intent": "report_feedback", "confidence": 0.88, "slots": report_feedback}

        reviewer_watch = detect_reviewer_watch_request(text)
        if reviewer_watch:
            return {"intent": "reviewer_watch", "confidence": 0.82, "slots": reviewer_watch}

        if looks_like_clear_reading_list_command(text):
            return {"intent": "clear_reading_list", "confidence": 0.95, "slots": {}}

        profile_update = parse_profile_update_request(text, profile=self.profile)
        if profile_update:
            return {"intent": "profile_update", "confidence": 0.9, "slots": profile_update}

        # 冷启动相关
        if looks_like_cold_start_description(text, profile=self.profile):
            return {"intent": "cold_start", "confidence": 0.9, "slots": {"text": text}}

        # 每日推送
        push_keywords = ["推送", "daily push", "今日论文", "今天有什么", "来一篇"]
        if any(kw in text_lower for kw in push_keywords):
            return {"intent": "daily_push", "confidence": 0.9, "slots": {}}

        # 反馈选择（纯数字或范围格式，或快捷命令）
        # 快捷命令：all red, all lock, none
        if text_lower in ["all red", "all lock", "none", "全部", "没有"]:
            return {"intent": "feedback", "confidence": 0.9, "slots": {"reply": text}}
        # 数字选择
        if re.match(r'^[\d\s\-，,]+$', text_lower):
            # 检查是否包含数字
            if re.search(r'\d', text_lower):
                return {"intent": "feedback", "confidence": 0.85, "slots": {"reply": text}}

        # 精读报告
        reading_keywords = ["精读", "详细读", "生成报告", "read this", "deep read"]
        if any(kw in text_lower for kw in reading_keywords):
            return {"intent": "reading_report", "confidence": 0.85, "slots": {}}

        # 周报
        report_keywords = ["周报", "weekly report", "本周总结", "这一周"]
        if any(kw in text_lower for kw in report_keywords):
            return {"intent": "weekly_report", "confidence": 0.9, "slots": {}}

        # 查看画像
        profile_keywords = ["画像", "profile", "我的方向", "显示画像"]
        if any(kw in text_lower for kw in profile_keywords):
            return {"intent": "show_profile", "confidence": 0.85, "slots": {}}

        # 默认：无法识别
        return {"intent": "unknown", "confidence": 0.5, "slots": {"text": text}}

    def handle_confirm_direction(self, topic: str) -> Dict[str, Any]:
        """Promote a pending direction candidate into the shared canonical registry."""
        print(f"Intent: Confirm Direction - {topic!r}")

        try:
            confirmed = confirm_pending_direction_candidate(topic, user_id=self.user_id)
            if not confirmed:
                msg = f"没有找到待确认的新方向“{topic}”。如果这是一个新词，请先再说一次它的完整方向描述。"
                send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
                return {"success": False, "message": msg}

            profile = get_profile(self.user_id)
            if not profile:
                profile = build_empty_profile(self.user_id)
                create_profile(self.user_id, profile)

            profile = repair_profile_from_role_description(self.user_id, profile)
            updated_profile = dict(profile)
            core_directions = dict(updated_profile.get("core_directions", {}) or {})
            topic_weights = dict(updated_profile.get("topic_weights", {}) or {})
            drift_state = dict(updated_profile.get("drift_state", {}) or {})
            manual_suppressed_topics = [
                str(topic).strip()
                for topic in (drift_state.get("manual_suppressed_topics", []) or [])
                if str(topic).strip()
            ]

            canonical_name = str(confirmed.get("canonical_name") or normalize_direction_key(topic))
            current_weight = max(
                float(core_directions.get(canonical_name, 0.0)),
                float(topic_weights.get(canonical_name, 0.0)),
            )
            seeded_weight = max(current_weight, 0.8)
            core_directions[canonical_name] = seeded_weight
            topic_weights[canonical_name] = seeded_weight

            updated_profile["core_directions"] = core_directions
            updated_profile["topic_weights"] = topic_weights
            updated_profile["interest_vector"] = (
                importlib.import_module("agents.coldstart-agent.main").generate_interest_vector(core_directions)
                if core_directions
                else []
            )
            updated_profile["updated_at"] = datetime.now().isoformat()
            update_profile(self.user_id, updated_profile)
            self.profile = updated_profile

            label = format_direction_label(canonical_name)
            profile_message = format_profile_message(updated_profile)
            summary = f"已确认新方向“{label}”，已纳入统一方向词典，并同步加入你的画像（默认权重 0.80）。"
            send_message(f"{summary}\n\n{profile_message}", chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {
                "success": True,
                "confirmed_direction": canonical_name,
                "updated_topics": [label],
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_cold_start(self, text: str) -> Dict[str, Any]:
        """处理冷启动"""
        print("Intent: Cold Start")

        try:
            coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
            explicit_command = detect_explicit_command_intent(text)
            scholar_url = extract_google_scholar_url(text)
            homepage_url = extract_homepage_url(text)
            natural_language = strip_bootstrap_urls(text) if (scholar_url or homepage_url) else text
            reset_existing = should_reset_existing_profile_for_cold_start(text)

            if explicit_command and explicit_command.get("intent") == "cold_start":
                if not scholar_url and not homepage_url:
                    natural_language = (
                        self.role_meta.get("natural_language")
                        or self.role_meta.get("bootstrap_summary")
                        or self.role_meta.get("description")
                        or ""
                    ).strip()
                elif (scholar_url or homepage_url) and not natural_language:
                    natural_language = None

            coldstart_agent.cold_start(
                user_id=self.user_id,
                natural_language=natural_language or None,
                scholar_url=scholar_url,
                homepage_url=homepage_url,
                reset_existing=reset_existing,
                send_to_feishu=self.send_to_feishu,
                feishu_user_id=self.feishu_user_id,
                chat_id=self.chat_id
            )
            return {"success": True, "message": "冷启动完成"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_daily_push(self) -> Dict[str, Any]:
        """处理每日推送"""
        print("Intent: Daily Push")

        try:
            daily_push_agent = importlib.import_module("deployments.feishu.daily-push-agent.main")
            result = daily_push_agent.daily_push(
                user_id=self.user_id,
                send_to_feishu=self.send_to_feishu,
                feishu_chat_id=self.chat_id
            )
            if isinstance(result, dict):
                return result
            return {"success": True, "message": "推送已发送"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_feedback(self, reply: str) -> Dict[str, Any]:
        """处理反馈"""
        print(f"Intent: Feedback - {reply!r}")

        # 从数据库获取最近的推送记录
        push_info = get_latest_push(self.user_id)

        if not push_info:
            # 如果没有推送记录，使用测试数据
            print("Warning: No recent push found, using test data")
            test_papers = [
                {"id": i+1, "arxiv_id": f"2401.{i:03d}", "title": f"Paper {i+1}"}
                for i in range(20)
            ]
            papers = test_papers
            push_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        else:
            print(f"Using papers from push: {push_info['push_id']}")
            papers = push_info['papers']
            push_id = push_info['push_id']

        try:
            feedback_agent = importlib.import_module("agents.feedback-agent.main")

            result = feedback_agent.process_feedback(
                user_id=self.user_id,
                push_id=push_id,
                reply=reply,
                papers=papers,
                feishu_user_id=self.feishu_user_id,
                chat_id=self.chat_id,
                send_to_feishu=self.send_to_feishu,
            )
            return result
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_reading_report(
        self,
        paper_ids: Optional[List[int]] = None,
        pdf_url: Optional[str] = None,
        title_hint: str = "",
    ) -> Dict[str, Any]:
        """处理精读报告"""
        print(f"Intent: Reading Report - papers: {paper_ids}, pdf_url: {pdf_url}")

        direct_pdf_url = str(pdf_url or "").strip()
        if direct_pdf_url:
            try:
                reading_agent = importlib.import_module("agents.reading-agent.main")
                resolved_title = str(title_hint or "").strip() or "Paper"
                created_docs = reading_agent.create_reading_report(
                    user_id=self.user_id,
                    paper_ids=[],
                    papers=[{"pdf_url": direct_pdf_url, "title": resolved_title, "url": direct_pdf_url}],
                    send_to_feishu=self.send_to_feishu,
                    feishu_user_id=self.feishu_user_id,
                    chat_id=self.chat_id,
                    request_metadata={
                        "report_source_type": "text_pdf_url",
                        "report_source_key": direct_pdf_url,
                        "report_source_name": resolved_title,
                    },
                )
                return {
                    "success": bool(created_docs),
                    "docs": created_docs,
                    "message": "Reading reports created" if created_docs else "No reading reports were created",
                }
            except Exception as e:
                return {"success": False, "message": str(e)}

        selected_info = None
        if paper_ids is None:
            selected_info = get_latest_selected_papers(self.user_id)

        if selected_info and selected_info.get("papers"):
            print(f"Using latest selected papers from push: {selected_info['push_id']}")
            papers = selected_info["papers"]
            paper_ids = list(range(1, len(papers) + 1))
        else:
            # 从数据库获取最近的推送记录
            push_info = get_latest_push(self.user_id)
            if not push_info:
                target_id = self.chat_id or self.feishu_user_id
                if target_id:
                    try:
                        send_text(
                            target_id,
                            "这次没有找到可精读的已选论文。请先“推送”并回复编号，或先完成一次论文选择。",
                            use_chat_id=bool(self.chat_id),
                        )
                    except Exception:
                        pass
                return {"success": False, "message": "No selected papers available for reading report"}

            print(f"Using papers from push: {push_info['push_id']}")
            papers = push_info["papers"]

        try:
            reading_agent = importlib.import_module("agents.reading-agent.main")

            if paper_ids is None:
                return {"success": False, "message": "No selected papers available for reading report"}

            created_docs = reading_agent.create_reading_report(
                user_id=self.user_id,
                paper_ids=paper_ids,
                papers=papers,
                send_to_feishu=self.send_to_feishu,
                feishu_user_id=self.feishu_user_id,
                chat_id=self.chat_id,
                request_metadata={
                    "selection_push_id": selected_info.get("push_id")
                } if selected_info else None,
            )
            return {
                "success": bool(created_docs),
                "docs": created_docs,
                "message": "Reading reports created" if created_docs else "No reading reports were created",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_clear_reading_list(self) -> Dict[str, Any]:
        """Clear the current pending reading queue while preserving learning history."""
        print("Intent: Clear Reading List")

        try:
            result = clear_pending_selected_papers(self.user_id)
        except Exception as e:
            return {"success": False, "message": str(e)}

        if result.get("cleared"):
            cleared_count = int(result.get("cleared_count", 0) or 0)
            paper_titles = [
                str(paper.get("title")).strip()
                for paper in result.get("papers", [])
                if str(paper.get("title")).strip()
            ]
            msg = f"已清空当前精读列表，共移除 {cleared_count} 篇待精读论文。"
            if paper_titles:
                msg += f"\n本次清空：{'; '.join(paper_titles[:3])}"
                if len(paper_titles) > 3:
                    msg += " ..."
            msg += "\n之后重新回复编号，新的论文才会进入精读列表。"
        else:
            msg = "当前没有待清空的精读列表。先推送并回复编号后，系统才会形成精读列表。"

        send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
        return {"success": True, **result, "message": msg}

    def handle_weekly_report(self) -> Dict[str, Any]:
        """处理周报"""
        print("Intent: Weekly Report")

        try:
            profile_report_agent = importlib.import_module("agents.profile-report-agent.main")
            result = profile_report_agent.send_weekly_report(
                user_id=self.user_id,
                send_to_feishu=self.send_to_feishu,
                feishu_chat_id=self.chat_id,
                role_name=self.role_name,
            )
            return result
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_must_read(self, command: str) -> Dict[str, Any]:
        """处理必读清单命令"""
        print(f"Intent: Must Read - {command!r}")

        try:
            must_read_manager = importlib.import_module("agents.must-read-manager.main")
            result = must_read_manager.process_must_read_command(
                user_id=self.user_id,
                command_text=command,
                send_to_feishu=self.send_to_feishu,
                feishu_user_id=self.feishu_user_id,
                chat_id=self.chat_id
            )
            return result
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_expand_push(self, category: str = "", query: str = "") -> Dict[str, Any]:
        """Expand a category bucket or a topic slice from the latest push."""
        push_info = get_latest_push(self.user_id)
        if not push_info:
            msg = "当前没有可展开的最近推送。请先执行一次“推送”。"
            send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": False, "message": msg}

        papers = list(push_info.get("papers") or [])
        filtered = papers
        if category:
            filtered = [paper for paper in filtered if str(paper.get("category") or "") == category]

        normalized_query = normalize_topic_token(query)
        if normalized_query:
            query_filtered = []
            for paper in filtered:
                search_fields = [
                    paper.get("title", ""),
                    paper.get("abstract", ""),
                    paper.get("institution", ""),
                    " ".join(str(author) for author in (paper.get("authors") or [])),
                    " ".join(str(item) for item in (paper.get("topics") or [])),
                    " ".join(str(item) for item in (paper.get("keywords") or [])),
                    " ".join(str(item) for item in (paper.get("categories") or [])),
                ]
                search_blob = normalize_topic_token(" ".join(search_fields))
                if normalized_query and normalized_query in search_blob:
                    query_filtered.append(paper)
            filtered = query_filtered

        if not filtered:
            label = PUSH_CATEGORY_LABELS.get(category, query or "目标分组")
            msg = f"最近一次推送里没有找到可展开的“{label}”候选。"
            send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": False, "message": msg}

        lines = [
            f"📎 补充展开 | {PUSH_CATEGORY_LABELS.get(category, query or '候选分组')} | {len(filtered)} 篇",
            "",
        ]
        for index, paper in enumerate(filtered[:25], start=1):
            position = paper.get("rank") or paper.get("paper_number") or papers.index(paper) + 1
            category_label = PUSH_CATEGORY_LABELS.get(str(paper.get("category") or ""), str(paper.get("category") or "候选"))
            authors = paper.get("authors") or []
            first_author = authors[0].split(",")[0].strip() if authors else "Unknown"
            title = str(paper.get("title") or "Unknown").strip()
            lines.append(f"{int(position):02d}. {category_label} | {first_author} — {title}")
        if len(filtered) > 25:
            lines.append("")
            lines.append(f"其余 {len(filtered) - 25} 篇先省略；如果你还想继续，我可以再往下展开。")

        send_message("\n".join(lines), chat_id=self.chat_id, user_id=self.feishu_user_id)
        return {"success": True, "expanded_count": len(filtered), "category": category, "query": query}

    def handle_classification_correction(self, paper_number: int, target_category: str) -> Dict[str, Any]:
        """Apply a strong explicit signal when the user corrects push categorization."""
        push_info = get_latest_push(self.user_id)
        if not push_info:
            msg = "当前没有可纠正的最近推送。请先执行一次“推送”。"
            send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": False, "message": msg}

        papers = list(push_info.get("papers") or [])
        if not (1 <= int(paper_number) <= len(papers)):
            msg = f"最近一次推送里没有编号 {paper_number}。"
            send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": False, "message": msg}

        paper = dict(papers[int(paper_number) - 1])
        current_category = str(paper.get("category") or "")
        target_priority = CATEGORY_PRIORITY.get(target_category, 0)
        current_priority = CATEGORY_PRIORITY.get(current_category, 0)

        profile = ensure_profile_schema(get_profile(self.user_id) or build_empty_profile(self.user_id))
        updated_profile = profile
        touched_topics: List[str] = []

        paper_topics = canonicalize_direction_terms(
            [
                *(paper.get("topics") or []),
                *(paper.get("keywords") or []),
                *(paper.get("categories") or []),
            ],
            keep_unknown=False,
        )
        touched_topics = list(paper_topics)

        if target_priority >= current_priority:
            updated_profile = update_profile_with_reading_signal(
                profile,
                paper=paper,
                signal_topics=paper_topics,
                signal_strength="strong",
                explicit_text=f"分类纠错：{paper_number} 应该是 {target_category}",
                current_time=datetime.now(),
                source_type="classification_correction",
                source_key=str(paper.get("id") or paper.get("title") or paper_number),
            )
        else:
            updated_profile = ensure_profile_schema(profile)
            for topic in paper_topics:
                if topic in updated_profile.get("topic_weights", {}):
                    updated_profile["topic_weights"][topic] = clamp_weight(
                        float(updated_profile["topic_weights"].get(topic, 0.3)) - 0.08,
                        minimum=0.0,
                        maximum=1.0,
                    )
                if topic in updated_profile.get("core_directions", {}):
                    updated_profile["core_directions"][topic] = clamp_weight(
                        float(updated_profile["core_directions"].get(topic, 0.3)) - 0.05,
                        minimum=0.0,
                        maximum=1.0,
                    )
            updated_profile["updated_at"] = datetime.now().isoformat()

        update_profile(self.user_id, updated_profile)
        self.profile = updated_profile

        log_behavior(
            user_id=self.user_id,
            push_id=str(push_info.get("push_id") or "latest_push"),
            paper_id=paper.get("id"),
            action="classification_correction",
            action_type="manual_override",
            category=target_category,
            metadata={
                "paper_number": int(paper_number),
                "previous_category": current_category,
                "target_category": target_category,
                "topics": touched_topics,
                "paper_title": paper.get("title", ""),
            },
        )

        topic_labels = [format_direction_label(topic) for topic in touched_topics[:3]]
        summary = (
            f"已记录：{paper_number:02d} 我会按 {PUSH_CATEGORY_LABELS.get(target_category, target_category)} 来理解。"
        )
        if topic_labels:
            summary += f"\n同步强化的主题：{', '.join(topic_labels)}。"
        send_message(summary, chat_id=self.chat_id, user_id=self.feishu_user_id)
        return {"success": True, "paper_number": int(paper_number), "target_category": target_category}

    def handle_report_feedback(self, sentiment: str) -> Dict[str, Any]:
        """Store lightweight quality feedback for future reading-report generation."""
        report_record = get_recent_created_report(self.user_id, minutes=720)
        if not report_record:
            msg = "最近没有可关联的精读报告，我先记不下这条反馈。"
            send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": False, "message": msg}

        profile = ensure_profile_schema(get_profile(self.user_id) or build_empty_profile(self.user_id))
        report_preferences = dict(profile.get("report_preferences", {}) or {})
        report_preferences["positive_feedback_count"] = int(report_preferences.get("positive_feedback_count", 0) or 0)
        report_preferences["negative_feedback_count"] = int(report_preferences.get("negative_feedback_count", 0) or 0)
        report_preferences["preferred_evidence_top_k"] = int(report_preferences.get("preferred_evidence_top_k", 3) or 3)

        if sentiment == "positive":
            report_preferences["positive_feedback_count"] += 1
            report_preferences["last_feedback"] = "positive"
        else:
            report_preferences["negative_feedback_count"] += 1
            report_preferences["last_feedback"] = "negative"
            report_preferences["prefer_more_evidence"] = True
            report_preferences["preferred_evidence_top_k"] = min(
                5,
                max(3, int(report_preferences.get("preferred_evidence_top_k", 3) or 3) + 1),
            )
            report_preferences["preferred_style"] = "evidence_first"

        profile["report_preferences"] = report_preferences
        profile["updated_at"] = datetime.now().isoformat()
        update_profile(self.user_id, profile)
        self.profile = profile

        log_behavior(
            user_id=self.user_id,
            push_id="reading_report",
            paper_id=report_record.get("paper_id"),
            action="report_feedback",
            action_type="reading_quality",
            category=sentiment,
            metadata={
                "doc_token": report_record.get("doc_token"),
                "doc_url": report_record.get("doc_url"),
                "paper_title": report_record.get("paper_title"),
            },
        )

        if sentiment == "positive":
            msg = "收到，这条精读报告会记为正反馈；我会保持当前的报告组织方式。"
        else:
            msg = "收到，我会把这条精读记为“没抓住重点”，后续会提高证据密度并优先按 evidence-first 方式组织。"
        send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
        return {"success": True, "sentiment": sentiment}

    def handle_reviewer_watch(self, conference: str, year: int, raw_text: str) -> Dict[str, Any]:
        """Best-effort fetch a reviewer watchlist from public OpenReview groups."""
        try:
            openreview_fetcher = importlib.import_module("skills.openreview-fetcher.scripts.fetch_openreview")
            fetcher = getattr(openreview_fetcher, "get_active_reviewer_candidates", None)
            if not callable(fetcher):
                raise RuntimeError("reviewer candidate fetcher unavailable")
            candidates = list(fetcher(conference, year, limit=8) or [])
        except Exception as e:
            candidates = []
            logger.warning(f"Reviewer watch fetch failed: {e}")

        if not candidates:
            msg = (
                f"当前没法稳定拿到 {conference.upper()} {year} 的公开 reviewer 身份清单。"
                "如果该 venue 没公开 reviewer group，我这边先无法自动追踪。"
            )
            send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": False, "message": msg}

        if "加上" in raw_text or "加入" in raw_text:
            profile = get_profile(self.user_id) or build_empty_profile(self.user_id)
            must_read = dict(profile.get("must_read", {}) or {})
            existing_authors = [str(author).strip() for author in must_read.get("authors", []) if str(author).strip()]
            merged_authors = []
            seen = set()
            for author in existing_authors + candidates[:5]:
                marker = author.casefold()
                if marker in seen:
                    continue
                seen.add(marker)
                merged_authors.append(author)
            must_read["authors"] = merged_authors
            profile["must_read"] = must_read
            profile["updated_at"] = datetime.now().isoformat()
            update_profile(self.user_id, profile)
            self.profile = profile
            msg = (
                f"已把这些公开 reviewer 候选加入必读作者：{', '.join(candidates[:5])}。"
            )
            send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": True, "reviewers": candidates[:5], "added": True}

        msg = (
            f"{conference.upper()} {year} 可见 reviewer / AC 候选（公开数据可得部分）：\n"
            + "\n".join(f"- {name}" for name in candidates[:8])
        )
        send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
        return {"success": True, "reviewers": candidates[:8], "added": False}

    def handle_show_profile(self) -> Dict[str, Any]:
        """处理查看画像"""
        print("Intent: Show Profile")

        try:
            # 刷新画像
            self.profile = get_profile(self.user_id)

            if not self.profile:
                msg = "未找到画像，请先进行冷启动"
                send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
                return {"success": False, "message": msg}

            self.profile = repair_profile_from_role_description(self.user_id, self.profile)
            profile_message = format_profile_message(self.profile)
            send_message(profile_message, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_profile_update(self, text: str, slots: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """处理轻量级画像修正，如提高/降低某方向权重或新增兴趣。"""
        print(f"Intent: Profile Update - {text!r}")

        try:
            profile = get_profile(self.user_id)
            if not profile:
                profile = build_empty_profile(self.user_id)
                create_profile(self.user_id, profile)

            profile = repair_profile_from_role_description(self.user_id, profile)
            slots = slots or parse_profile_update_request(text, profile=profile)
            if not slots:
                msg = "这句画像修正我还没解析清楚，你可以试试“降低 GUI Agent 权重”或“我最近对 protein language model 更感兴趣了”。"
                send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
                return {"success": False, "message": msg}

            action = slots.get("action")
            direction = slots.get("direction", "increase")
            topic_text = (slots.get("topic") or "").strip()
            weight_target = slots.get("weight_target")
            if not topic_text:
                msg = "我没有识别到你想调整的方向或主题。"
                send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
                return {"success": False, "message": msg}

            topic_candidates = [topic_text] + [
                str(item).strip()
                for item in (slots.get("topics") or [])
                if str(item).strip()
            ]
            normalization_result = normalize_profile_update_topics(topic_candidates, self.user_id)
            normalized_candidates = [
                str(item.get("name") or "").strip()
                for item in normalization_result.get("canonical_directions", [])
                if str(item.get("name") or "").strip()
            ]
            normalization_notes = list(normalization_result.get("explanations", []) or [])
            pending_candidates = list(normalization_result.get("pending_candidates", []) or [])
            pending_prompt = format_pending_direction_prompt(pending_candidates)
            if pending_candidates:
                normalization_notes = [
                    note
                    for note in normalization_notes
                    if not str(note or "").strip().startswith("发现候选新方向")
                ]

            updated_profile = dict(profile)
            core_directions = dict(updated_profile.get("core_directions", {}) or {})
            topic_weights = dict(updated_profile.get("topic_weights", {}) or {})
            drift_state = dict(updated_profile.get("drift_state", {}) or {})
            manual_suppressed_topics = [
                str(topic).strip()
                for topic in (drift_state.get("manual_suppressed_topics", []) or [])
                if str(topic).strip()
            ]

            resolved_key = find_profile_topic_key(updated_profile, topic_text)
            resolved_topics: List[str] = []
            use_semantic_expansion = action == "adjust_interest" and direction == "decrease"
            for candidate in topic_candidates + normalized_candidates:
                candidate_keys = find_related_profile_topic_keys(
                    updated_profile,
                    candidate,
                    include_semantic_family=use_semantic_expansion,
                )
                for candidate_key in candidate_keys:
                    if candidate_key not in resolved_topics:
                        resolved_topics.append(candidate_key)
            changed_labels: List[str] = []
            summary = ""

            if action == "remove_topic":
                removal_candidates = [
                    candidate
                    for candidate in resolved_topics
                    if candidate in core_directions or candidate in topic_weights
                ]

                for removal_key in removal_candidates:
                    removed_any = False
                    if removal_key in core_directions:
                        core_directions.pop(removal_key, None)
                        removed_any = True
                    if removal_key in topic_weights:
                        topic_weights.pop(removal_key, None)
                        removed_any = True
                    if removed_any:
                        changed_labels.append(format_direction_label(removal_key))
                        if removal_key not in manual_suppressed_topics:
                            manual_suppressed_topics.append(removal_key)

                if changed_labels:
                    summary = f"已从当前画像中移除：{', '.join(changed_labels)}。"
                else:
                    summary = f"当前画像里没有明显匹配“{topic_text}”的核心方向，我先没有做改动。"
            elif action == "adjust_weight":
                target_key = resolved_key
                if not target_key:
                    for candidate in resolved_topics:
                        if candidate in core_directions or candidate in topic_weights:
                            target_key = candidate
                            break
                if not target_key and direction == "increase" and normalized_candidates:
                    target_key = normalized_candidates[0]

                if not target_key:
                    if direction == "increase" and pending_prompt:
                        summary = pending_prompt
                    else:
                        summary = f"当前画像里没有明显匹配“{topic_text}”的核心方向，我先没有做改动。"
                else:
                    current_weight = float(topic_weights.get(target_key, core_directions.get(target_key, 0.5)))
                    if weight_target is not None:
                        new_weight = clamp_weight(weight_target, minimum=0.0, maximum=1.0)
                    else:
                        delta = 0.15
                        new_weight = clamp_weight(
                            current_weight + delta if direction == "increase" else current_weight - delta,
                            minimum=0.0,
                            maximum=1.0,
                        )
                    topic_weights[target_key] = new_weight
                    if target_key in core_directions or direction == "increase":
                        core_directions[target_key] = new_weight
                    changed_labels.append(format_direction_label(target_key))
                    summary = (
                        f"已将 {format_direction_label(target_key)} 的权重从 "
                        f"{current_weight:.2f} 调整到 {new_weight:.2f}。"
                    )
            else:
                matched_topics = [
                    candidate
                    for candidate in resolved_topics
                    if candidate in core_directions or candidate in topic_weights
                ]

                if direction == "decrease":
                    if matched_topics:
                        for resolved_topic in matched_topics:
                            current_weight = float(
                                topic_weights.get(resolved_topic, core_directions.get(resolved_topic, 0.55))
                            )
                            new_weight = clamp_weight(
                                current_weight - 0.15,
                                minimum=0.0,
                                maximum=1.0,
                            )
                            topic_weights[resolved_topic] = new_weight
                            if resolved_topic in core_directions:
                                core_directions[resolved_topic] = new_weight
                            changed_labels.append(format_direction_label(resolved_topic))
                            if new_weight <= 0.40 and resolved_topic not in manual_suppressed_topics:
                                manual_suppressed_topics.append(resolved_topic)
                        summary = (
                            f"已下调你对“{topic_text}”的兴趣信号。\n"
                            f"同步更新方向：{', '.join(changed_labels)}"
                        )
                    else:
                        summary = f"当前画像里没有明显匹配“{topic_text}”的核心方向，我先没有做改动。"
                else:
                    seed_targets: List[str] = []
                    for candidate in matched_topics + normalized_candidates:
                        if candidate not in seed_targets:
                            seed_targets.append(candidate)

                    if not seed_targets:
                        if pending_prompt:
                            summary = pending_prompt
                        else:
                            summary = f"当前画像里没有明显匹配“{topic_text}”的核心方向，我先没有做改动。"
                    else:
                        for index, target_key in enumerate(seed_targets):
                            current_weight = float(topic_weights.get(target_key, core_directions.get(target_key, 0.0)))
                            if current_weight > 0:
                                new_weight = clamp_weight(
                                    max(current_weight, 0.55) + 0.10,
                                    minimum=0.0,
                                    maximum=1.0,
                                )
                            else:
                                new_weight = clamp_weight(
                                    max(0.55, 0.65 - index * 0.05),
                                    minimum=0.0,
                                    maximum=1.0,
                                )
                            topic_weights[target_key] = new_weight
                            core_directions[target_key] = new_weight
                            changed_labels.append(format_direction_label(target_key))
                        summary = (
                            f"已增强你对“{topic_text}”的兴趣信号。\n"
                            f"同步更新方向：{', '.join(changed_labels)}"
                        )

            if changed_labels:
                updated_profile["core_directions"] = core_directions
                updated_profile["topic_weights"] = topic_weights
                if manual_suppressed_topics:
                    drift_state["manual_suppressed_topics"] = manual_suppressed_topics

                suppressed_set = {
                    str(topic).strip()
                    for topic in manual_suppressed_topics
                    if str(topic).strip()
                }
                current_anchor = str(drift_state.get("anchor_topic") or "").strip()
                current_hidden = str(drift_state.get("hidden_anchor") or "").strip()
                if current_anchor in suppressed_set or current_hidden in suppressed_set:
                    drift_state["status"] = "stable"
                    drift_state["score"] = 0.0
                    drift_state["drift_enabled"] = False
                    drift_state["hidden_anchor"] = None
                    drift_state["hidden_anchor_source"] = None
                    drift_state["intent_score"] = 0.0
                    drift_state["anchor_topic"] = None
                    drift_state["anchor_topics"] = []
                    drift_state["anchor_source"] = None
                    drift_state["anchor_confidence"] = 0.0
                    drift_state["anchor_progress"] = 0.0
                    drift_state["anchor_set_date"] = None
                    drift_state["commitment_days_remaining"] = 0
                    drift_state["signal_window"] = []
                    drift_state["top_shift_topics"] = []
                    drift_state["trigger_source"] = None
                    drift_state["trigger_checkfile"] = None
                    drift_state["trigger_date"] = None
                    drift_state["suppressed_topics"] = []

                updated_profile["drift_state"] = drift_state
                updated_profile["interest_vector"] = (
                    importlib.import_module("agents.coldstart-agent.main").generate_interest_vector(core_directions)
                    if core_directions
                    else []
                )
                updated_profile["updated_at"] = datetime.now().isoformat()
                update_profile(self.user_id, updated_profile)
                self.profile = updated_profile
                profile_message = format_profile_message(updated_profile)
            else:
                self.profile = profile
                profile_message = format_profile_message(profile)

            summary = merge_unique_message_sections(*(normalization_notes or []), summary)

            message_text = f"{summary}\n\n{profile_message}" if summary else profile_message
            send_message(message_text, chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {
                "success": True,
                "updated_topics": changed_labels,
                "pending_candidates": pending_candidates,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_role_manager(self, command: str) -> Dict[str, Any]:
        """处理角色管理命令"""
        print(f"Intent: Role Manager - {command!r}")

        try:
            role_manager = importlib.import_module("agents.role-manager.main")
            result = role_manager.process_role_command(
                command_text=command,
                feishu_user_id=self.feishu_user_id
            )
            return result
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_unknown(self, text: str) -> Dict[str, Any]:
        """处理未知意图"""
        msg = f"抱歉，我还不太理解你的意思。\n\n我可以帮你：\n• 每日推送：说'推送'\n• 反馈选择：回复数字如'1 2 3'\n• 精读报告：说'精读'\n• 清空精读列表：说'清空精读列表'\n• 查看周报：说'周报'\n• 管理必读：说'加个必读作者'\n\n当前输入：{text[:50]}"
        send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
        return {"success": False, "message": "Unknown intent"}

    def process(self, text: str) -> Dict[str, Any]:
        """
        处理用户输入

        Args:
            text: 用户输入文本

        Returns:
            处理结果
        """
        text_clean = safe_console_text(text, 100)
        print(f"\n{'='*60}")
        print(f"Processing: {text_clean}")
        print(f"{'='*60}")

        # 检测意图
        intent = self.detect_intent(text)
        print(f"Detected intent: {intent['intent']} (confidence: {intent['confidence']:.2f})")

        # 路由到对应处理器
        handlers = {
            "ignore": lambda: {"success": True, "ignored": True},
            "confirm_direction": lambda: self.handle_confirm_direction(intent["slots"].get("topic", text)),
            "cold_start": lambda: self.handle_cold_start(text),
            "daily_push": self.handle_daily_push,
            "feedback": lambda: self.handle_feedback(intent["slots"].get("reply", text)),
            "expand_push": lambda: self.handle_expand_push(
                category=intent["slots"].get("category", ""),
                query=intent["slots"].get("query", ""),
            ),
            "classification_correction": lambda: self.handle_classification_correction(
                int(intent["slots"].get("paper_number", 0)),
                intent["slots"].get("target_category", ""),
            ),
            "report_feedback": lambda: self.handle_report_feedback(intent["slots"].get("sentiment", "")),
            "reviewer_watch": lambda: self.handle_reviewer_watch(
                intent["slots"].get("conference", ""),
                int(intent["slots"].get("year", datetime.now().year)),
                text,
            ),
            "reading_report": lambda: self.handle_reading_report(
                paper_ids=intent["slots"].get("paper_ids"),
                pdf_url=intent["slots"].get("pdf_url"),
                title_hint=intent["slots"].get("title_hint", ""),
            ),
            "clear_reading_list": self.handle_clear_reading_list,
            "weekly_report": self.handle_weekly_report,
            "must_read": lambda: self.handle_must_read(intent["slots"].get("command", text)),
            "show_profile": self.handle_show_profile,
            "profile_update": lambda: self.handle_profile_update(text, intent["slots"]),
            "role_manager": lambda: self.handle_role_manager(intent["slots"].get("command", text)),
        }

        handler = handlers.get(intent["intent"], lambda: self.handle_unknown(text))
        result = handler()

        print(f"Result: {safe_console_text(result, 200)}")
        return result


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Master Coordinator - 主协调器")
    parser.add_argument("--user-id", type=str, default="user_001", help="用户 ID")
    parser.add_argument("--message", type=str, required=True, help="用户消息")
    parser.add_argument("--feishu-user-id", type=str, help="飞书用户 ID")
    parser.add_argument("--no-feishu", action="store_true", help="不发送飞书")

    args = parser.parse_args()

    coordinator = MasterCoordinator(
        user_id=args.user_id,
        feishu_user_id=args.feishu_user_id,
        send_to_feishu=not args.no_feishu,
    )

    result = coordinator.process(args.message)
    print(f"\n最终结果：{json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
