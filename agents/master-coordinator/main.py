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
get_recent_pushes = db_ops.get_recent_pushes

# 飞书报告器
feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
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

    bootstrap_text = (role_meta.get("natural_language") or role_meta.get("description") or "").strip()
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
    core_directions = profile.get("core_directions", {})
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
        lines.append("（暂无数据，后续会根据你的选择继续学习）")
    lines.append("")

    lines.append("━━━ 必读清单 ━━━")
    must_read = profile.get("must_read", {})
    lines.append(f"作者：{', '.join(must_read.get('authors', [])) or '（空，待你添加）'}")
    lines.append(f"机构：{', '.join(must_read.get('institutions', [])) or '（空，待你添加）'}")
    lines.append(f"关键词：{', '.join(must_read.get('keywords', [])) or '（空，待你添加）'}")

    author_heat = profile.get("author_heat", {})
    filtered_author_heat = {
        author: heat for author, heat in author_heat.items()
        if is_displayable_author_name(author)
    }
    if filtered_author_heat:
        top_authors = sorted(filtered_author_heat.items(), key=lambda item: -item[1])[:3]
        lines.append("")
        lines.append("━━━ 最近学到的作者偏好 ━━━")
        for author, heat in top_authors:
            lines.append(f"{author}（热度：{heat:.2f}）")

    lines.append("")
    lines.append("━━━━━━━━━━━━")
    lines.append("你可以直接说：")
    lines.append('  "加个必读作者：XXX"')
    lines.append('  "降低 GUI Agent 权重"')
    lines.append('  "我最近对 protein language model 更感兴趣了"')

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
        "reading_history": [],
        "behavior_logs": [],
    }


def normalize_topic_token(value: str) -> str:
    """Normalize topic labels for fuzzy matching."""
    return re.sub(r"[\s_\-]+", "", (value or "").strip().lower())


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
    return cleaned.lower()


def clamp_weight(value: float, minimum: float = 0.1, maximum: float = 0.95) -> float:
    """Clamp profile weights into a safe displayable range."""
    return max(minimum, min(maximum, round(float(value), 2)))


def iter_topic_aliases(topic_key: str) -> List[str]:
    """Return user-facing aliases for a topic key."""
    aliases = {
        topic_key,
        format_direction_label(topic_key),
        topic_key.replace("-", " "),
        topic_key.replace("_", " "),
    }
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


BOT_AUTHORED_PREFIXES = (
    "📋 你的学术画像",
    "SciTaste 学术画像确认",
    "📰 今日论文",
    "📊 今日反馈已记录",
    "收到，",
    "抱歉，",
    "已增强你对",
    "已下调你对",
    "已将 ",
)


def first_meaningful_line(text: Any) -> str:
    """Use only the leading content line so bot examples do not get reparsed as user input."""
    for raw_line in str(text or "").splitlines():
        cleaned = raw_line.strip().strip("“”\"'")
        if cleaned:
            return cleaned
    return ""


def detect_explicit_command_intent(text: Any) -> Optional[Dict[str, Any]]:
    """Fast-path obvious commands so they never go through the profile-update LLM."""
    cleaned = first_meaningful_line(text)
    lowered = cleaned.lower().strip()
    if not lowered:
        return None

    if lowered in {"冷启动", "重新冷启动", "cold start", "cold-start"}:
        return {"intent": "cold_start", "confidence": 1.0, "slots": {"text": cleaned}}

    if lowered in {"推送", "daily push", "今日论文", "今天论文", "来一篇", "来几篇"}:
        return {"intent": "daily_push", "confidence": 1.0, "slots": {}}

    if lowered in {"精读", "read this", "deep read"}:
        return {"intent": "reading_report", "confidence": 1.0, "slots": {}}

    if lowered in {"周报", "weekly report"}:
        return {"intent": "weekly_report", "confidence": 1.0, "slots": {}}

    if lowered in {"必读", "必读清单"}:
        return {"intent": "must_read", "confidence": 1.0, "slots": {"command": cleaned}}

    if lowered in {"画像", "我的画像", "显示画像", "profile"}:
        return {"intent": "show_profile", "confidence": 1.0, "slots": {}}

    if lowered in {"all red", "all lock", "none", "全部", "没有"}:
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
    has_target = any(token in cleaned for token in ("作者", "机构", "关键词")) or any(
        token in lowered for token in ("author", "institution", "keyword")
    )
    has_command_shape = (
        ":" in cleaned
        or "：" in cleaned
        or lowered.startswith(("加个", "添加", "增加", "移除", "删除", "删掉", "add ", "remove ", "delete "))
    )
    if has_action and has_target and (("必读" in cleaned or "must read" in lowered) or has_command_shape):
        return True

    return False


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

    if profile and not profile_needs_bootstrap(profile):
        return False

    return any(token in cleaned for token in COLD_START_BOOTSTRAP_HINTS) or any(
        token in lowered for token in COLD_START_BOOTSTRAP_HINTS
    )


def clean_profile_topic_text(topic: str, *, strip_domain_suffix: bool = False) -> str:
    """Trim topic text extracted from profile-update messages."""
    cleaned = re.sub(r"\s+", " ", (topic or "").strip().strip("“”\"'`"))
    cleaned = cleaned.strip("，。！？,.!?；;：:()（）[]【】")
    if strip_domain_suffix:
        cleaned = re.sub(r"\s*(?:方向|领域|主题)$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def build_profile_update_result(action: str, direction: str, topic: str, *, strip_domain_suffix: bool = False) -> Optional[Dict[str, Any]]:
    """Build a normalized profile-update payload."""
    cleaned_topic = clean_profile_topic_text(topic, strip_domain_suffix=strip_domain_suffix)
    if not cleaned_topic:
        return None
    return {
        "action": action,
        "direction": direction,
        "topic": cleaned_topic,
    }


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

    def __init__(self, user_id: Optional[str] = None, feishu_user_id: Optional[str] = None, chat_id: Optional[str] = None):
        """
        初始化协调器

        Args:
            user_id: 用户 ID（可选，如果为空则从 roles.json 获取）
            feishu_user_id: 飞书用户 ID（用于 open_id 发送）
            chat_id: 聊天 ID（用于 chat_id 发送，优先级更高）
        """
        # 优先使用传入的 user_id，如果没有则从 roles.json 获取
        if user_id:
            self.user_id = user_id
        else:
            roles_user_id = get_current_user_id()
            self.user_id = roles_user_id if roles_user_id != "user_default" else "user_unknown"
        self.feishu_user_id = feishu_user_id or os.environ.get("FEISHU_USER_ID", "")
        self.profile = get_profile(self.user_id)
        self.role_meta = get_role_meta_for_user(self.user_id) or {}
        self.role_name = self.role_meta.get("role_name")
        # 优先使用传入 chat_id，否则回退到角色绑定的 chat_id，避免误发到默认个人账号
        self.chat_id = chat_id or resolve_role_chat_id(self.user_id, self.profile)

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

    def handle_cold_start(self, text: str) -> Dict[str, Any]:
        """处理冷启动"""
        print("Intent: Cold Start")

        try:
            coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
            explicit_command = detect_explicit_command_intent(text)
            natural_language = text
            if explicit_command and explicit_command.get("intent") == "cold_start":
                natural_language = (
                    self.role_meta.get("natural_language")
                    or self.role_meta.get("description")
                    or ""
                ).strip()
            coldstart_agent.cold_start(
                user_id=self.user_id,
                natural_language=natural_language or None,
                send_to_feishu=True,
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
            daily_push_agent = importlib.import_module("agents.daily-push-agent.main")
            daily_push_agent.daily_push(
                user_id=self.user_id,
                send_to_feishu=True,
                feishu_chat_id=self.chat_id
            )
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
                chat_id=self.chat_id
            )
            return result
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_reading_report(self, paper_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """处理精读报告"""
        print(f"Intent: Reading Report - papers: {paper_ids}")

        # 从数据库获取最近的推送记录
        push_info = get_latest_push(self.user_id)

        if not push_info:
            # 如果没有推送记录，使用测试数据
            print("Warning: No recent push found, using test data")
            test_papers = [
                {"id": i+1, "arxiv_id": f"2401.{i:03d}", "title": f"Paper {i+1}",
                 "authors": ["Author"], "abstract": "Abstract"}
                for i in range(20)
            ]
            papers = test_papers
        else:
            print(f"Using papers from push: {push_info['push_id']}")
            papers = push_info['papers']

        try:
            reading_agent = importlib.import_module("agents.reading-agent.main")

            # 如果没有指定论文，使用前 3 篇
            if paper_ids is None:
                paper_ids = [p['id'] for p in papers[:3]]

            created_docs = reading_agent.create_reading_report(
                user_id=self.user_id,
                paper_ids=paper_ids,
                papers=papers,
                send_to_feishu=True,
                feishu_user_id=self.feishu_user_id,
                chat_id=self.chat_id
            )
            return {"success": True, "docs": created_docs}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def handle_weekly_report(self) -> Dict[str, Any]:
        """处理周报"""
        print("Intent: Weekly Report")

        try:
            profile_report_agent = importlib.import_module("agents.profile-report-agent.main")
            result = profile_report_agent.send_weekly_report(
                user_id=self.user_id,
                send_to_feishu=True,
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
                send_to_feishu=True,
                feishu_user_id=self.feishu_user_id,
                chat_id=self.chat_id
            )
            return result
        except Exception as e:
            return {"success": False, "message": str(e)}

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
            if not topic_text:
                msg = "我没有识别到你想调整的方向或主题。"
                send_message(msg, chat_id=self.chat_id, user_id=self.feishu_user_id)
                return {"success": False, "message": msg}

            updated_profile = dict(profile)
            core_directions = dict(updated_profile.get("core_directions", {}) or {})
            topic_weights = dict(updated_profile.get("topic_weights", {}) or {})

            resolved_key = find_profile_topic_key(updated_profile, topic_text)
            resolved_topics: List[str] = []
            use_semantic_expansion = action == "adjust_interest"
            for candidate in [topic_text] + [str(item).strip() for item in (slots.get("topics") or []) if str(item).strip()]:
                candidate_keys = find_related_profile_topic_keys(
                    updated_profile,
                    candidate,
                    include_semantic_family=use_semantic_expansion,
                )
                for candidate_key in candidate_keys:
                    if candidate_key not in resolved_topics:
                        resolved_topics.append(candidate_key)
            changed_labels: List[str] = []
            inferred: Optional[Dict[str, Any]] = None

            def get_inferred() -> Dict[str, Any]:
                nonlocal inferred
                if inferred is None:
                    coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
                    inferred = coldstart_agent.parse_natural_language(topic_text)
                return inferred

            if action == "remove_topic":
                removal_candidates: List[str] = []
                for candidate in resolved_topics:
                    if candidate not in removal_candidates:
                        removal_candidates.append(candidate)

                if not removal_candidates:
                    inferred_directions = get_inferred().get("core_directions", {}) or {}
                    for inferred_key in inferred_directions.keys():
                        resolved_inferred_key = find_profile_topic_key(updated_profile, inferred_key)
                        if resolved_inferred_key and resolved_inferred_key not in removal_candidates:
                            removal_candidates.append(resolved_inferred_key)

                if not removal_candidates:
                    derived_key = resolved_key or derive_topic_key(topic_text)
                    if derived_key in core_directions or derived_key in topic_weights:
                        removal_candidates.append(derived_key)

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

                if changed_labels:
                    summary = f"已从当前画像中移除：{', '.join(changed_labels)}。"
                else:
                    summary = f"当前画像里没有明显匹配“{topic_text}”的核心方向，我先没有做改动。"
            elif action == "adjust_weight":
                if not resolved_key:
                    inferred_directions = get_inferred().get("core_directions", {}) or {}
                    for inferred_key in inferred_directions.keys():
                        resolved_inferred_key = find_profile_topic_key(updated_profile, inferred_key)
                        if resolved_inferred_key:
                            resolved_key = resolved_inferred_key
                            break
                    if not resolved_key and direction == "increase":
                        resolved_key = (
                            max(inferred_directions.items(), key=lambda item: item[1])[0]
                            if inferred_directions
                            else derive_topic_key(topic_text)
                        )

                if not resolved_key:
                    summary = f"当前画像里没有明显匹配“{topic_text}”的核心方向，我先没有做改动。"
                else:
                    current_weight = float(topic_weights.get(resolved_key, core_directions.get(resolved_key, 0.5)))
                    delta = 0.15
                    new_weight = clamp_weight(current_weight + delta if direction == "increase" else current_weight - delta)
                    topic_weights[resolved_key] = new_weight
                    if resolved_key in core_directions or direction == "increase":
                        core_directions[resolved_key] = new_weight
                    elif resolved_key in core_directions:
                        core_directions[resolved_key] = new_weight
                    changed_labels.append(format_direction_label(resolved_key))
                    summary = f"已将 {format_direction_label(resolved_key)} 的权重从 {current_weight:.2f} 调整到 {new_weight:.2f}。"
            else:
                matched_topics = list(resolved_topics)
                inferred_directions: Dict[str, Any] = {}
                if not matched_topics and direction == "decrease":
                    inferred_directions = get_inferred().get("core_directions", {}) or {}
                    for inferred_key in inferred_directions.keys():
                        resolved_inferred_key = find_profile_topic_key(updated_profile, inferred_key)
                        if resolved_inferred_key and resolved_inferred_key not in matched_topics:
                            matched_topics.append(resolved_inferred_key)

                if matched_topics:
                    for resolved_topic in matched_topics:
                        current_weight = float(topic_weights.get(resolved_topic, core_directions.get(resolved_topic, 0.55)))
                        base_weight = max(current_weight, 0.55) if direction == "increase" else current_weight
                        new_weight = clamp_weight(base_weight + 0.10 if direction == "increase" else base_weight - 0.15)
                        topic_weights[resolved_topic] = new_weight
                        if resolved_topic in core_directions or direction == "increase":
                            core_directions[resolved_topic] = new_weight
                        changed_labels.append(format_direction_label(resolved_topic))
                else:
                    if direction == "increase":
                        inferred_directions = inferred_directions or (get_inferred().get("core_directions", {}) or {})
                        if inferred_directions:
                            for inferred_key, inferred_weight in inferred_directions.items():
                                current_weight = float(topic_weights.get(inferred_key, core_directions.get(inferred_key, inferred_weight)))
                                base_weight = max(current_weight, float(inferred_weight), 0.55)
                                new_weight = clamp_weight(base_weight + 0.10)
                                topic_weights[inferred_key] = new_weight
                                core_directions[inferred_key] = new_weight
                                changed_labels.append(format_direction_label(inferred_key))
                        else:
                            resolved_key = derive_topic_key(topic_text)
                            current_weight = float(topic_weights.get(resolved_key, core_directions.get(resolved_key, 0.4)))
                            new_weight = clamp_weight(current_weight + 0.15)
                            topic_weights[resolved_key] = new_weight
                            core_directions[resolved_key] = new_weight
                            changed_labels.append(format_direction_label(resolved_key))

                if changed_labels:
                    if direction == "increase":
                        summary = f"已增强你对“{topic_text}”的兴趣信号。\n同步更新方向：{', '.join(changed_labels)}"
                    else:
                        summary = f"已下调你对“{topic_text}”的兴趣信号。\n同步更新方向：{', '.join(changed_labels)}"
                else:
                    summary = f"当前画像里没有明显匹配“{topic_text}”的核心方向，我先没有做改动。"

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

            profile_message = format_profile_message(updated_profile)
            send_message(f"{summary}\n\n{profile_message}", chat_id=self.chat_id, user_id=self.feishu_user_id)
            return {"success": True, "updated_topics": changed_labels}
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
        msg = f"抱歉，我还不太理解你的意思。\n\n我可以帮你：\n• 每日推送：说'推送'\n• 反馈选择：回复数字如'1 2 3'\n• 精读报告：说'精读'\n• 查看周报：说'周报'\n• 管理必读：说'加个必读作者'\n\n当前输入：{text[:50]}"
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
            "cold_start": lambda: self.handle_cold_start(text),
            "daily_push": self.handle_daily_push,
            "feedback": lambda: self.handle_feedback(intent["slots"].get("reply", text)),
            "reading_report": self.handle_reading_report,
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
        feishu_user_id=args.feishu_user_id if not args.no_feishu else None
    )

    result = coordinator.process(args.message)
    print(f"\n最终结果：{json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
