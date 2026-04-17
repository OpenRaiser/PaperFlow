#!/usr/bin/env python3
"""
Daily Push Agent - 每日推送代理

职责：抓取当日论文，基于用户画像进行筛选、排序、分类，生成推送卡片。
"""

import sys
import os
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import defaultdict

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 未安装，使用环境变量

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 使用 importlib 导入带连字符的模块
import importlib

# 导入多个数据源
arxiv_fetcher = importlib.import_module("skills.arxiv-fetcher.scripts.fetch_arxiv")
arxiv_fetch_by_date = arxiv_fetcher.fetch_by_date

openreview_fetcher = importlib.import_module("skills.openreview-fetcher.scripts.fetch_openreview")
openreview_fetch_by_date = openreview_fetcher.fetch_by_date

journal_fetcher = importlib.import_module("skills.journal-fetcher.scripts.fetch_journal")
journal_fetch_recent = journal_fetcher.get_recent_papers

db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
get_profile = db_ops.get_profile

profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")
calculate_paper_score = profile_updater.calculate_paper_score
is_must_read = profile_updater.is_must_read
cosine_similarity = profile_updater.cosine_similarity
get_must_read_matches = profile_updater.get_must_read_matches

embedding_service_module = importlib.import_module("skills.embedding.scripts.embed")
get_embedding_service = embedding_service_module.get_embedding_service
embed_batch = embedding_service_module.embed_batch
build_paper_text = embedding_service_module.build_paper_text
direction_lexicon = __import__("config.direction_lexicon", fromlist=["dummy"])
canonicalize_direction_terms = direction_lexicon.canonicalize_direction_terms
expand_direction_terms_from_registry = direction_lexicon.expand_direction_terms
format_direction_label = direction_lexicon.format_direction_label

# 飞书报告器（可选）
try:
    feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
    send_daily_push = feishu_reporter.send_daily_push
    send_text_to_chat = feishu_reporter.send_text_to_chat
    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    send_daily_push = None
    send_text_to_chat = None

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")
ROLE_META_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "roles.json")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_yaml_config(filename: str) -> Dict:
    """Load a YAML config file from the config directory."""
    import yaml

    config_file = os.path.join(CONFIG_PATH, filename)
    if not os.path.exists(config_file):
        return {}
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_default_arxiv_categories() -> List[str]:
    """Use all arXiv categories currently supported by the fetcher."""
    categories = list(getattr(arxiv_fetcher, "CATEGORIES", {}).keys())
    return categories or ["cs.AI", "cs.LG", "cs.CV"]


def load_default_conferences() -> List[str]:
    """Load enabled and supported conference sources from config."""
    configured = []
    unsupported = []
    for item in load_yaml_config("conferences.yaml").get("conferences", []):
        if not item.get("enabled", True):
            continue
        normalized = openreview_fetcher.normalize_conference_name(item.get("name", ""))
        if normalized:
            configured.append(normalized)
        else:
            unsupported.append(item.get("name", ""))

    if unsupported:
        print(f"Skipping unsupported conference sources for now: {', '.join(unsupported)}")

    configured = dedupe_preserve_order(configured)
    return configured or openreview_fetcher.get_supported_conferences()


def load_default_journals() -> List[str]:
    """Load enabled journal sources from config, plus built-in supported journals not listed there."""
    configured = []
    unsupported = []
    raw_config = load_yaml_config("journals.yaml").get("journals", {})

    for group_items in raw_config.values():
        for item in group_items or []:
            if not item.get("enabled", True):
                continue
            normalized = journal_fetcher.normalize_journal_name(item.get("name", ""))
            if normalized:
                configured.append(normalized)
            else:
                unsupported.append(item.get("name", ""))

    if unsupported:
        print(f"Skipping unsupported journal sources for now: {', '.join(unsupported)}")

    configured = dedupe_preserve_order(configured)
    supported = journal_fetcher.get_supported_journals()
    extras = [name for name in supported if name not in configured]
    return configured + extras


def load_scoring_weights() -> Dict:
    """加载排序权重配置"""
    import yaml
    config_file = os.path.join(CONFIG_PATH, "scoring_weights.yaml")
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    # 默认配置
    return {
        "w1_interest_vector": 0.35,
        "w2_topic_weight": 0.25,
        "w3_author_institution": 0.20,
        "w4_quality_signal": 0.20,
        "bonus_must_read": 0.15,
        "threshold_high_relevant": 0.75,
        "threshold_maybe_interested": 0.50,
        "drift_bonus_shifting": 0.08,
        "drift_bonus_recovered": 0.04,
        "drift_short_topic_bonus": 0.03,
        "reading_signal_short_term_bonus": 0.05,
    }


@dataclass
class PaperWithScore:
    """带分数的论文"""
    paper: Dict
    score: float
    category: str  # must_read, high_relevant, maybe_interested, edge_relevant
    relevance_signal: float = 0.0
    drift_bonus: float = 0.0
    drift_topics: Optional[List[str]] = None
    reading_signal_bonus: float = 0.0
    reading_signal_topics: Optional[List[str]] = None


def _hard_priority_tuple(paper_with_score: PaperWithScore) -> tuple:
    """Sort must-read hits ahead of all other candidates, then by score."""
    return (
        1 if paper_with_score.category == "must_read" else 0,
        float(paper_with_score.score),
        float(paper_with_score.relevance_signal),
    )


def resolve_chat_id_for_user(user_id: str, profile: Dict = None) -> str:
    """Resolve the Feishu chat target for a role user."""
    if profile and profile.get("feishu_chat_id"):
        return profile["feishu_chat_id"]

    if os.path.exists(ROLE_META_PATH):
        import json

        with open(ROLE_META_PATH, "r", encoding="utf-8") as f:
            roles_meta = json.load(f)

        for role_info in roles_meta.get("roles", {}).values():
            if role_info.get("user_id") == user_id and role_info.get("feishu_chat_id"):
                return role_info["feishu_chat_id"]

    return ""


def dedupe_preserve_order(items: List[str]) -> List[str]:
    """Keep the first occurrence of each non-empty string."""
    seen = set()
    result = []
    for item in items:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def estimate_quality_score(paper: Dict) -> float:
    """Estimate a coarse paper quality score from source / venue metadata."""
    source = str(paper.get("source") or "").lower()
    journal = str(paper.get("journal") or "").lower()
    conference_key = infer_conference_key(paper)
    venue = str(paper.get("venue") or "").lower()

    if source == "journal":
        if journal in {"nature", "science", "cell"}:
            return 0.95
        if "nature" in venue or "science" in venue or "cell" in venue:
            return 0.9
        return 0.75

    if source == "openreview":
        if conference_key in {"neurips", "icml", "iclr"}:
            return 0.85
        if conference_key in {"acl", "emnlp", "cvpr", "iccv", "eccv", "acmmm"}:
            return 0.8
        if any(name in venue for name in ("neurips", "icml", "iclr")):
            return 0.85
        if any(name in venue for name in ("acl", "emnlp", "cvpr", "iccv", "eccv", "acm multimedia")):
            return 0.8
        return 0.72

    if source == "arxiv":
        categories = [str(category).lower() for category in paper.get("categories", [])]
        if any(category.startswith("q-bio") for category in categories):
            return 0.62
        return 0.58

    return 0.6


def infer_conference_key(paper: Dict) -> str:
    """Infer a normalized conference key from categories or venue text."""
    supported = ("neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "acl", "emnlp", "acmmm")
    categories = [str(category).lower().strip() for category in paper.get("categories", [])]
    for conference in supported:
        if conference in categories:
            return conference

    venue = str(paper.get("venue") or "").lower()
    venue_aliases = {
        "acm multimedia": "acmmm",
    }
    for alias, conference in venue_aliases.items():
        if alias in venue:
            return conference
    for conference in supported:
        if conference in venue:
            return conference
    return ""


def compute_relevance_signal(paper: Dict, profile: Dict) -> float:
    """Estimate user-paper relevance independent of venue prestige."""
    interest_sim = max(
        0.0,
        cosine_similarity(
            paper.get("embedding", []),
            profile.get("interest_vector", []),
        ),
    )

    topic_match = 0.0
    matched_weights = [
        float(profile.get("topic_weights", {}).get(topic, 0.0))
        for topic in paper.get("topics", [])
        if topic in profile.get("topic_weights", {})
    ]
    if matched_weights:
        topic_match = max(matched_weights)

    author_score = 0.0
    paper_authors = paper.get("authors", [])
    if paper_authors:
        author_heat = profile.get("author_heat", {})
        author_hits = [float(author_heat.get(author, 0.0)) for author in paper_authors if author in author_heat]
        if author_hits:
            author_score = sum(author_hits) / len(author_hits)

    institution_score = 0.0
    institution_text = str(paper.get("institution") or "").lower()
    if institution_text:
        for institution, heat in profile.get("institution_heat", {}).items():
            if institution and institution.lower() in institution_text:
                institution_score = max(institution_score, float(heat))

    return max(interest_sim, topic_match, author_score, institution_score)


def compute_drift_bonus(paper: Dict, profile: Dict, weights: Dict) -> tuple[float, List[str]]:
    """Boost papers that align with currently shifting short-term interests."""
    drift_state = (profile or {}).get("drift_state", {}) or {}
    status = str(drift_state.get("status", "stable"))
    if status not in {"shifting", "recovered"}:
        return 0.0, []

    paper_topics = [str(topic).strip() for topic in paper.get("topics", []) if str(topic).strip()]
    if not paper_topics:
        return 0.0, []

    top_shift_topics = [str(topic).strip() for topic in drift_state.get("top_shift_topics", []) or [] if str(topic).strip()]
    short_term_topics = drift_state.get("short_term_topics", {}) or {}

    matched_shift_topics = [topic for topic in paper_topics if topic in top_shift_topics]
    short_term_strength = max(float(short_term_topics.get(topic, 0.0) or 0.0) for topic in paper_topics)

    base_bonus = float(
        weights.get("drift_bonus_shifting", 0.08)
        if status == "shifting"
        else weights.get("drift_bonus_recovered", 0.04)
    )
    short_term_bonus_cap = float(weights.get("drift_short_topic_bonus", 0.03))

    bonus = 0.0
    if matched_shift_topics:
        bonus += base_bonus
    if short_term_strength > 0:
        bonus += min(short_term_bonus_cap, short_term_strength * short_term_bonus_cap)

    return round(min(0.12, bonus), 4), matched_shift_topics[:3]


def compute_reading_signal_bonus(paper: Dict, profile: Dict, weights: Dict) -> tuple[float, List[str]]:
    """Boost papers that align with recent direct-upload reading interests."""
    reading_signal_state = (profile or {}).get("reading_signal_state", {}) or {}
    short_term_topics = reading_signal_state.get("short_term_topics", {}) or {}
    if not short_term_topics:
        return 0.0, []

    paper_topics = [str(topic).strip() for topic in paper.get("topics", []) if str(topic).strip()]
    if not paper_topics:
        return 0.0, []

    matched_topics = [topic for topic in paper_topics if topic in short_term_topics]
    if not matched_topics:
        return 0.0, []

    strongest = max(float(short_term_topics.get(topic, 0.0) or 0.0) for topic in matched_topics)
    bonus_cap = float(weights.get("reading_signal_short_term_bonus", 0.05))
    bonus = min(bonus_cap, strongest * bonus_cap)
    return round(min(0.08, bonus), 4), matched_topics[:3]


def get_source_bucket(paper: Dict) -> str:
    """Map a paper into a source bucket for diversity balancing."""
    source = str(paper.get("source") or "").lower().strip()

    if source == "journal":
        journal = str(paper.get("journal") or "").lower().strip()
        return journal or "journal"

    if source == "openreview":
        return infer_conference_key(paper) or "openreview"

    return source or "unknown"


def apply_source_diversity_quota(
    scored_papers: List[PaperWithScore],
    weights: Dict
) -> List[PaperWithScore]:
    """Soft-cap dominant sources while preserving must-read inclusions."""
    if not scored_papers:
        return scored_papers

    must_read_items = [paper for paper in scored_papers if paper.category == "must_read"]
    remainder = [paper for paper in scored_papers if paper.category != "must_read"]
    if not remainder:
        return scored_papers

    min_total = int(weights.get("source_diversity_min_total", 12))
    min_per_bucket = int(weights.get("source_diversity_min_per_bucket", 3))
    max_share = float(weights.get("source_diversity_max_share", 0.7))

    if len(remainder) < min_total or max_share >= 1.0:
        return scored_papers

    buckets = defaultdict(list)
    for paper in remainder:
        buckets[get_source_bucket(paper.paper)].append(paper)

    if len(buckets) <= 1:
        return scored_papers

    bucket_order = sorted(
        buckets.keys(),
        key=lambda bucket: buckets[bucket][0].score if buckets[bucket] else 0.0,
        reverse=True,
    )
    max_per_bucket = max(min_per_bucket, math.ceil(len(remainder) * max_share))

    selected_ids = set()
    bucket_counts = {bucket: 0 for bucket in buckets}

    for bucket in bucket_order:
        reserve_count = min(len(buckets[bucket]), min_per_bucket, max_per_bucket)
        for paper in buckets[bucket][:reserve_count]:
            selected_ids.add(id(paper))
            bucket_counts[bucket] += 1

    for paper in remainder:
        paper_id = id(paper)
        if paper_id in selected_ids:
            continue

        bucket = get_source_bucket(paper.paper)
        if bucket_counts[bucket] >= max_per_bucket:
            continue

        selected_ids.add(paper_id)
        bucket_counts[bucket] += 1

    selected = must_read_items + [paper for paper in remainder if id(paper) in selected_ids]
    dropped = len(scored_papers) - len(selected)
    if dropped > 0:
        print(
            "Applied source diversity quota: "
            f"kept {len(selected)} of {len(scored_papers)} papers across {len(buckets)} buckets"
        )

    return selected


def format_must_read_config(profile: Dict) -> str:
    """Format current must-read configuration for push cards."""
    must_read = (profile or {}).get("must_read", {})
    authors = ", ".join(must_read.get("authors", [])) or "（空）"
    institutions = ", ".join(must_read.get("institutions", [])) or "（空）"
    keywords = ", ".join(must_read.get("keywords", [])) or "（空）"
    return f"当前配置：作者 {authors} | 机构 {institutions} | 关键词 {keywords}"


def format_must_read_reason(paper: Dict, profile: Dict) -> str:
    """Explain why a paper matched the must-read list."""
    matches = get_must_read_matches(paper, profile or {})
    parts = []
    if matches.get("authors"):
        parts.append(f"作者：{', '.join(matches['authors'])}")
    if matches.get("institutions"):
        parts.append(f"机构：{', '.join(matches['institutions'])}")
    if matches.get("keywords"):
        parts.append(f"关键词：{', '.join(matches['keywords'])}")
    return "；".join(parts)


def expand_direction_terms(canonical_directions: List[str]) -> Dict[str, Dict]:
    """Return canonical directions plus their aliases / paper terms for reuse."""
    return expand_direction_terms_from_registry(canonical_directions)


def prepare_paper_features(papers: List[Dict]) -> List[Dict]:
    """Attach embeddings and normalized ranking features to fetched papers."""
    if not papers:
        return papers

    embedding_texts = [build_paper_text(paper) for paper in papers]
    embeddings = embed_batch(embedding_texts)
    embedding_service = get_embedding_service()
    print(f"Embedding descriptor: {embedding_service.descriptor}")

    for paper, embedding in zip(papers, embeddings):
        paper["embedding"] = embedding
        paper["embedding_model"] = embedding_service.descriptor
        paper["institution"] = str(paper.get("institution") or "")
        paper["quality_score"] = estimate_quality_score(paper)

        semantic_topics = canonicalize_direction_terms(
            extract_topics_from_title(paper.get("title", "")),
            keep_unknown=True,
        )
        source_categories = list(paper.get("categories", []))
        if paper.get("source") == "openreview":
            source_categories.append(paper.get("venue", "conference"))
        elif paper.get("source") == "journal":
            source_categories.append(paper.get("journal", "journal"))

        expanded_terms = expand_direction_terms(semantic_topics)
        paper["keywords"] = dedupe_preserve_order(source_categories + semantic_topics)
        paper["topics"] = semantic_topics
        paper["direction_terms"] = expanded_terms

    return papers


def extract_topics_from_title(title: str) -> List[str]:
    """从标题中提取语义主题关键词"""
    title_lower = title.lower()
    topics = []

    # ===== 用户画像中的主题（优先匹配）=====
    # multimodal-reasoning: 多模态 + 推理
    if ("multimodal" in title_lower or "multi-modal" in title_lower) and "reasoning" in title_lower:
        topics.append("multimodal-reasoning")
    # multimodal-learning: 多模态学习
    if "multimodal" in title_lower or "multi-modal" in title_lower:
        topics.append("multimodal-learning")
    # vision-language: 视觉 - 语言
    if "vision-language" in title_lower or "vision and language" in title_lower or "visual language" in title_lower:
        topics.append("vision-language")
    # cross-modal: 跨模态
    if "cross-modal" in title_lower or "cross modal" in title_lower:
        topics.append("cross-modal")
    if any(token in title_lower for token in ("gui agent", "computer use", "screen agent", "interface agent")):
        topics.append("gui-agent")
    if "protein" in title_lower and any(token in title_lower for token in ("language model", "llm", "transformer")):
        topics.append("protein-language-model")

    # ===== 通用主题（扩展匹配）=====
    # reasoning: 推理
    if "reasoning" in title_lower or "chain of thought" in title_lower or "cot" in title_lower:
        topics.append("reasoning")
    # vision: 视觉
    if "vision" in title_lower or "visual" in title_lower or "image" in title_lower or "video" in title_lower:
        topics.append("vision")
    # language: 语言
    if "language" in title_lower or "llm" in title_lower or "transformer" in title_lower or "text" in title_lower:
        topics.append("language")
    # machine-learning: 机器学习
    if "machine learning" in title_lower or "ml" in title_lower or "classification" in title_lower or "regression" in title_lower:
        topics.append("machine-learning")
    # deep-learning: 深度学习
    if "deep learning" in title_lower or "neural" in title_lower or "cnn" in title_lower or "transformer" in title_lower:
        topics.append("deep-learning")
    # bio-molecular / biology
    if any(
        token in title_lower
        for token in (
            "protein", "molecular", "biological", "bio-", "dna", "rna", "gene",
            "genomic", "genome", "cell", "immune", "microbial", "antigen",
            "single-cell", "single cell", "multi-omic", "multiomic", "maternal",
        )
    ):
        topics.append("bio-molecular")
    # bioinformatics / computational biology
    if any(
        token in title_lower
        for token in (
            "bioinformatics", "computational biology", "genomic", "genome",
            "single-cell", "single cell", "multi-omic", "multiomic",
            "proteomic", "transcriptomic",
        )
    ):
        topics.append("bioinformatics")
    # protein folding / structure
    if "protein" in title_lower and any(token in title_lower for token in ("fold", "structure", "structural", "conformation")):
        topics.append("protein-folding")
    # scientific discovery
    if any(token in title_lower for token in ("scientific", "science", "discovery", "experiment", "hypothesis")):
        topics.append("science-discovery")
    # reinforcement-learning: 强化学习
    if "reinforcement" in title_lower or "rl" in title_lower or "reward" in title_lower or "policy" in title_lower:
        topics.append("reinforcement-learning")
    # retrieval: 检索
    if "retrieval" in title_lower or "retrieve" in title_lower or "search" in title_lower:
        topics.append("retrieval")
    # segmentation: 分割
    if "segmentation" in title_lower or "segment" in title_lower:
        topics.append("segmentation")
    # detection: 检测
    if "detection" in title_lower or "detect" in title_lower or "object detection" in title_lower:
        topics.append("detection")
    if (
        any(token in title_lower for token in ("detection", "detect", "detector"))
        and any(
            token in title_lower
            for token in (
                "ai",
                "aigc",
                "llm",
                "deepfake",
                "synthetic media",
                "synthetic image",
                "synthetic video",
                "ai-generated",
                "generated content",
                "machine-generated",
            )
        )
    ):
        topics.append("ai-detection")
    # generation: 生成
    if "generation" in title_lower or "generate" in title_lower or "diffusion" in title_lower:
        topics.append("generation")
    # explanation: 解释
    if "explanation" in title_lower or "explainable" in title_lower or "interpret" in title_lower:
        topics.append("explanation")
    # agent: 智能体
    if "agent" in title_lower or "agents" in title_lower or "autonomous" in title_lower:
        topics.append("agent")
    # optimization: 优化
    if "optimization" in title_lower or "optimize" in title_lower or "efficient" in title_lower:
        topics.append("optimization")
    # safety: 安全
    if "safety" in title_lower or "safe" in title_lower or "robust" in title_lower or "adversarial" in title_lower:
        topics.append("safety")
    # privacy: 隐私
    if "privacy" in title_lower or "private" in title_lower:
        topics.append("privacy")

    return canonicalize_direction_terms(topics, keep_unknown=True)


def fetch_and_process_papers(
    days: int = 1,
    arxiv_categories: List[str] = None,
    conferences: List[str] = None,
    journals: List[str] = None,
    limit_per_source: int = 30
) -> List[Dict]:
    """
    从多个数据源抓取并处理论文

    Args:
        days: 抓取最近 N 天
        arxiv_categories: arXiv 类别列表
        conferences: 会议列表 (ICLR, NeurIPS, ICML 等)
        journals: 期刊列表 (Nature, Science, Cell 等)
        limit_per_source: 每个数据源的最大论文数

    Returns:
        论文列表
    """
    if arxiv_categories is None:
        arxiv_categories = get_default_arxiv_categories()

    if conferences is None:
        conferences = load_default_conferences()

    if journals is None:
        journals = load_default_journals()

    today = datetime.now()
    end_date = today.strftime("%Y%m%d")

    def fetch_arxiv_papers(fetch_days: int) -> List[Dict]:
        start_date = (today - timedelta(days=fetch_days)).strftime("%Y%m%d")
        print(f"Fetching from arXiv ({start_date} to {end_date})...")
        papers = arxiv_fetch_by_date(
            start_date=start_date,
            end_date=end_date,
            categories=arxiv_categories,
            limit=limit_per_source
        )
        for paper in papers:
            paper["source"] = "arxiv"
        print(f"  Fetched {len(papers)} papers from arXiv")
        return papers

    def fetch_openreview_papers(fetch_days: int) -> List[Dict]:
        start_date = (today - timedelta(days=fetch_days)).strftime("%Y%m%d")
        print(f"Fetching from OpenReview (conferences: {conferences})...")
        papers = openreview_fetch_by_date(
            start_date=start_date,
            end_date=end_date,
            conferences=conferences,
            limit=limit_per_source
        )
        for paper in papers:
            paper["source"] = "openreview"
        print(f"  Fetched {len(papers)} papers from OpenReview")
        return papers

    def fetch_journal_papers(fetch_days: int) -> List[Dict]:
        print(f"Fetching from journals ({journals}) in the last {fetch_days} days...")
        papers = journal_fetch_recent(
            journals=journals,
            days=fetch_days,
            limit_per_journal=limit_per_source
        )
        for paper in papers:
            paper["source"] = "journal"
        print(f"  Fetched {len(papers)} papers from journals")
        return papers

    all_papers = []
    arxiv_papers = []
    openreview_papers = []
    journal_papers = []

    # 1. 从 arXiv 获取论文
    try:
        arxiv_papers = fetch_arxiv_papers(days)
        all_papers.extend(arxiv_papers)
    except Exception as e:
        print(f"  arXiv fetch error: {e}")

    # 2. 从 OpenReview 获取会议论文
    try:
        openreview_papers = fetch_openreview_papers(days)
        all_papers.extend(openreview_papers)
    except Exception as e:
        print(f"  OpenReview fetch error: {e}")

    # 3. 从期刊获取论文
    try:
        journal_papers = fetch_journal_papers(days)
        all_papers.extend(journal_papers)
    except Exception as e:
        print(f"  Journal fetch error: {e}")

    fallback_days = max(days, 7)
    min_candidate_pool = max(10, limit_per_source // 2)
    if days < fallback_days and len(all_papers) < min_candidate_pool:
        print(
            f"Candidate pool too small ({len(all_papers)} papers); "
            f"widening sparse sources to {fallback_days} days..."
        )
        if not arxiv_papers:
            try:
                all_papers.extend(fetch_arxiv_papers(fallback_days))
            except Exception as e:
                print(f"  arXiv fallback fetch error: {e}")
        if not journal_papers:
            try:
                all_papers.extend(fetch_journal_papers(fallback_days))
            except Exception as e:
                print(f"  Journal fallback fetch error: {e}")
        if not openreview_papers:
            try:
                all_papers.extend(fetch_openreview_papers(fallback_days))
            except Exception as e:
                print(f"  OpenReview fallback fetch error: {e}")

    # 去重（基于标题）
    seen_titles = set()
    unique_papers = []
    for paper in all_papers:
        title = paper.get("title", "")
        if title and title not in seen_titles:
            seen_titles.add(title)
            unique_papers.append(paper)

    print(f"Total unique papers after deduplication: {len(unique_papers)}")

    return prepare_paper_features(unique_papers)


def sort_and_categorize(
    papers: List[Dict],
    profile: Dict,
    weights: Dict
) -> List[PaperWithScore]:
    """
    排序并分类论文

    Args:
        papers: 论文列表
        profile: 用户画像
        weights: 权重配置

    Returns:
        带分类的论文列表
    """
    result = []
    for paper in papers:
        score = calculate_paper_score(paper, profile, weights)
        relevance_signal = compute_relevance_signal(paper, profile)
        drift_bonus, drift_topics = compute_drift_bonus(paper, profile, weights)
        reading_signal_bonus, reading_signal_topics = compute_reading_signal_bonus(paper, profile, weights)
        score = min(1.0, score + drift_bonus + reading_signal_bonus)
        category = categorize_paper(score, paper, profile, weights)
        result.append(
            PaperWithScore(
                paper=paper,
                score=score,
                category=category,
                relevance_signal=relevance_signal,
                drift_bonus=drift_bonus,
                drift_topics=drift_topics,
                reading_signal_bonus=reading_signal_bonus,
                reading_signal_topics=reading_signal_topics,
            )
        )

    # 先按分数粗排，再按分类结果做硬优先级重排
    result.sort(key=lambda x: x.score, reverse=True)

    result = categorize_papers_by_rank(result, profile, weights)
    result.sort(key=_hard_priority_tuple, reverse=True)
    result = apply_source_diversity_quota(result, weights)
    result = apply_push_count_limit(result, weights)
    result.sort(key=_hard_priority_tuple, reverse=True)

    return result


def categorize_papers_by_rank(scored_papers: List[PaperWithScore], profile: Dict, weights: Dict) -> List[PaperWithScore]:
    """Categorize papers while treating must-read hits as hard-priority keepers."""
    threshold_high = weights.get("threshold_high_relevant", 0.40)
    threshold_maybe = weights.get("threshold_maybe_interested", 0.25)
    threshold_edge = weights.get("threshold_edge_relevant", 0.15)
    min_relevance_signal = weights.get("min_relevance_signal", 0.08)
    high_rank_fraction = weights.get("rank_high_fraction", 0.1)
    maybe_rank_fraction = weights.get("rank_maybe_fraction", 0.4)

    rank_eligible = [paper for paper in scored_papers if paper.relevance_signal >= min_relevance_signal]
    high_rank_limit = max(1, int(len(rank_eligible) * high_rank_fraction)) if rank_eligible else 0
    maybe_rank_limit = max(high_rank_limit, int(len(rank_eligible) * maybe_rank_fraction)) if rank_eligible else 0
    rank_eligible_positions = {id(paper): idx for idx, paper in enumerate(rank_eligible)}

    filtered: List[PaperWithScore] = []
    for paper_with_score in scored_papers:
        rank_position = rank_eligible_positions.get(id(paper_with_score))
        must_read_hit = is_must_read(paper_with_score.paper, profile)

        if must_read_hit:
            paper_with_score.category = "must_read"
            filtered.append(paper_with_score)
            continue

        if paper_with_score.relevance_signal < min_relevance_signal and not must_read_hit:
            print(
                f"  Filtered out (low relevance={paper_with_score.relevance_signal:.2f}, score={paper_with_score.score:.2f}): "
                f"{str(paper_with_score.paper.get('title', '') or '').strip()}"
            )
            continue

        if paper_with_score.score >= threshold_high or (
            rank_position is not None
            and rank_position < high_rank_limit
            and paper_with_score.score >= threshold_maybe
        ):
            paper_with_score.category = "high_relevant"
            filtered.append(paper_with_score)
            continue

        if paper_with_score.score >= threshold_maybe or (
            rank_position is not None
            and rank_position < maybe_rank_limit
            and paper_with_score.score >= threshold_edge
        ):
            paper_with_score.category = "maybe_interested"
            filtered.append(paper_with_score)
            continue

        if paper_with_score.score >= threshold_edge:
            paper_with_score.category = "edge_relevant"
            filtered.append(paper_with_score)
            continue

        print(
            f"  Filtered out (score={paper_with_score.score:.2f}): "
            f"{str(paper_with_score.paper.get('title', '') or '').strip()}"
        )

    return filtered


def categorize_paper(score: float, paper: Dict, profile: Dict, weights: Dict) -> str:
    """Backward-compatible coarse categorization."""
    threshold_high = weights.get("threshold_high_relevant", 0.75)
    threshold_maybe = weights.get("threshold_maybe_interested", 0.50)
    threshold_edge = weights.get("threshold_edge_relevant", 0.15)

    if is_must_read(paper, profile) and score >= threshold_edge:
        return "must_read"
    if score >= threshold_high:
        return "high_relevant"
    if score >= threshold_maybe:
        return "maybe_interested"
    return "edge_relevant"


def apply_push_count_limit(scored_papers: List[PaperWithScore], weights: Dict) -> List[PaperWithScore]:
    """Keep daily push volume manageable while preserving all must-read hits."""
    if not scored_papers:
        return scored_papers

    target_count = max(1, int(weights.get("push_target_count", 50)))
    max_count = max(target_count, int(weights.get("push_max_count", target_count)))
    must_read_items = [paper for paper in scored_papers if paper.category == "must_read"]
    remainder = [paper for paper in scored_papers if paper.category != "must_read"]

    hard_target_count = max(target_count, len(must_read_items))
    hard_max_count = max(max_count, len(must_read_items))
    non_must_read_capacity = max(0, hard_target_count - len(must_read_items))

    limited_remainder = list(remainder[: max(0, hard_max_count - len(must_read_items))])
    if len(limited_remainder) > non_must_read_capacity:
        limited_remainder = limited_remainder[:non_must_read_capacity]
    limited = must_read_items + limited_remainder

    print(
        f"Applying push count limit: {len(scored_papers)} -> {len(limited)} "
        f"(target={hard_target_count}, max={hard_max_count}, must_read={len(must_read_items)})"
    )
    return limited


def format_drift_hint(profile: Dict) -> str:
    """Render a short ranking explanation based on drift state."""
    drift_state = (profile or {}).get("drift_state", {}) or {}
    status = drift_state.get("status", "stable")
    if status == "shifting":
        topics = [format_direction_label(topic) for topic in (drift_state.get("top_shift_topics", []) or [])[:3]]
        if topics:
            return f"兴趣迁移状态：迁移中，近期偏好权重已提升，当前重点关注 {', '.join(topics)}。"
        return "兴趣迁移状态：迁移中，近期偏好权重已提升。"
    if status == "recovered":
        topics = [format_direction_label(topic) for topic in (drift_state.get("top_shift_topics", []) or [])[:3]]
        if topics:
            return f"兴趣迁移状态：已恢复，系统正在重新平衡短期与长期兴趣，近期变化主要围绕 {', '.join(topics)}。"
        return "兴趣迁移状态：已恢复，系统正在重新平衡短期与长期兴趣。"
    return "兴趣迁移状态：稳定，长期画像权重占优。"


def format_reading_signal_hint(profile: Dict) -> str:
    """Render a short hint for direct-upload reading signals."""
    reading_signal_state = (profile or {}).get("reading_signal_state", {}) or {}
    short_term_topics = reading_signal_state.get("short_term_topics", {}) or {}
    if not short_term_topics:
        return ""

    ranked_topics = sorted(
        short_term_topics.items(),
        key=lambda item: float(item[1] or 0.0),
        reverse=True,
    )
    topic_labels = [format_direction_label(topic) for topic, _ in ranked_topics[:3]]
    if not topic_labels:
        return ""
    return f"近期直传精读信号：{', '.join(topic_labels)}，这些方向会被适度前置。"


def format_push_card(
    scored_papers: List[PaperWithScore],
    profile: Dict = None,
    date: str = None,
    total_fetched: int = None
) -> str:
    """Format the daily push card with explicit must-read status and drift hint."""
    if date is None:
        date = datetime.now().strftime("%m-%d")

    must_read = [p for p in scored_papers if p.category == "must_read"]
    high_relevant = [p for p in scored_papers if p.category == "high_relevant"]
    maybe_interested = [p for p in scored_papers if p.category == "maybe_interested"]
    edge_relevant = [p for p in scored_papers if p.category == "edge_relevant"]

    total = total_fetched or len(scored_papers)
    filtered = len(must_read) + len(high_relevant) + len(maybe_interested) + len(edge_relevant)

    lines = [f"📰 今日论文 | {date} | 抓取 {total} 篇 → 筛后 {filtered} 篇", ""]
    lines.append(f"━━━ 🔒 必读清单命中（{len(must_read)} 篇）━━━")
    lines.append(format_must_read_config(profile or {}))
    lines.append(format_drift_hint(profile or {}))
    reading_signal_hint = format_reading_signal_hint(profile or {})
    if reading_signal_hint:
        lines.append(reading_signal_hint)

    global_count = 0
    if must_read:
        for paper_with_score in must_read:
            global_count += 1
            title = str(paper_with_score.paper.get("title", "Unknown") or "Unknown").strip()
            authors = paper_with_score.paper.get("authors", [])
            categories = paper_with_score.paper.get("categories", [])
            category_str = categories[0] if categories else "unknown"
            first_author = authors[0].split(",")[0].strip() if isinstance(authors, list) and authors else "Unknown"
            lines.append(f"{global_count:02d}. [{category_str}] {first_author} — {title}")
            match_reason = format_must_read_reason(paper_with_score.paper, profile or {})
            if match_reason:
                lines.append(f"    命中：{match_reason}")
    else:
        must_read_config = (profile or {}).get("must_read", {})
        if any(must_read_config.get(key) for key in ("authors", "institutions", "keywords")):
            lines.append("本次推送未命中当前必读清单。")
        else:
            lines.append("当前还没有设置必读作者 / 机构 / 关键词。")
    lines.append("")

    sections = [
        ("🔴", "高度相关", high_relevant),
        ("🟡", "可能感兴趣", maybe_interested),
        ("🔵", "边缘相关", edge_relevant),
    ]
    for marker, section_title, items in sections:
        if not items:
            continue
        lines.append(f"━━━ {marker} {section_title}（{len(items)} 篇）━━━")
        for paper_with_score in items:
            global_count += 1
            title = str(paper_with_score.paper.get("title", "Unknown") or "Unknown").strip()
            authors = paper_with_score.paper.get("authors", [])
            categories = paper_with_score.paper.get("categories", [])
            category_str = categories[0] if categories else "unknown"
            first_author = authors[0].split(",")[0].strip() if isinstance(authors, list) and authors else ""
            lines.append(f"{global_count:02d}. [{category_str}] {first_author} — {title}")
        lines.append("")

    lines.append("━━━━━━━━━━━━")
    lines.append("选择方式（任选）：")
    lines.append("  直接回复编号：1 2 4 6")
    lines.append("  范围选择：1-5 8 10")
    lines.append("  快捷命令：all lock / all red / none")
    return "\n".join(lines)


def daily_push(
    user_id: str = "user_001",
    days: int = 1,
    arxiv_categories: List[str] = None,
    conferences: List[str] = None,
    journals: List[str] = None,
    limit_per_source: int = 30,
    output_file: str = None,
    send_to_feishu: bool = False,
    feishu_chat_id: str = None  # 飞书群 ID（可选，用于多角色）
):
    """
    执行每日推送

    Args:
        user_id: 用户 ID
        days: 抓取最近 N 天
        arxiv_categories: arXiv 类别列表
        conferences: 会议列表
        journals: 期刊列表
        limit_per_source: 每个数据源的最大论文数
        output_file: 输出文件路径（可选）
        send_to_feishu: 是否发送到飞书
        feishu_chat_id: 飞书群 ID（可选，用于多角色）
    """
    print(f"Starting daily push for user: {user_id}")

    # 1. 读取用户画像
    print("Loading user profile...")
    profile = get_profile(user_id)
    if profile is None:
        print(f"Profile missing for user {user_id}, attempting runtime bootstrap...")
        try:
            runtime_bootstrap = importlib.import_module("scripts.runtime_bootstrap")
            runtime_bootstrap.ensure_role_profiles(Path(PROJECT_ROOT))
            profile = get_profile(user_id)
        except Exception as exc:
            print(f"Runtime bootstrap failed while repairing profile: {exc}")

    if profile is None:
        message = f"Profile not found for user {user_id}"
        print(f"Error: {message}")
        return {"success": False, "message": message}
    print(f"Profile loaded: {profile.get('version', 'unknown')}")

    # 2. 加载权重配置
    weights = load_scoring_weights()

    # 3. 从多个数据源抓取论文
    papers = fetch_and_process_papers(
        days=days,
        arxiv_categories=arxiv_categories,
        conferences=conferences,
        journals=journals,
        limit_per_source=limit_per_source
    )
    print(f"Fetched {len(papers)} papers from all sources")

    if not papers:
        print("No papers fetched, skipping push")
        return

    # 4. 排序并分类
    print("Sorting and categorizing papers...")
    scored_papers = sort_and_categorize(papers, profile, weights)

    # 5. 生成推送卡片
    date_str = datetime.now().strftime("%m-%d")
    push_id = f"push_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    push_card = format_push_card(scored_papers, profile, date_str, total_fetched=len(papers))

    # 6. 保存推送记录到数据库
    print(f"Saving push record: {push_id}")
    for i, p in enumerate(scored_papers):
        paper = p.paper
        paper_id = paper.get("id")

        # 如果论文不在数据库，先保存论文
        if not paper_id:
            # 生成新 ID
            try:
                paper_id = db_ops.save_paper(
                    arxiv_id=paper.get("arxiv_id", ""),
                    doi=paper.get("doi", ""),
                    title=paper.get("title", ""),
                    authors=paper.get("authors", []),
                    abstract=paper.get("abstract", ""),
                    categories=paper.get("categories", []),
                    source=paper.get("source", "arxiv"),
                    institution=paper.get("institution"),
                    venue=paper.get("venue") or paper.get("journal"),
                    publish_date=paper.get("publish_date"),
                    embedding=paper.get("embedding"),
                    embedding_model=paper.get("embedding_model"),
                )
                paper["id"] = paper_id
            except Exception as e:
                print(f"  Paper {i+1} save error: {e}")
                # 继续尝试记录行为（可能论文已在数据库中）
                # 尝试通过 arxiv_id 查找现有论文 ID
                try:
                    existing = db_ops.get_paper_by_arxiv_id(paper.get("arxiv_id", ""))
                    if existing:
                        paper_id = existing["id"]
                        paper["id"] = paper_id
                except:
                    pass

        # 记录推送行为（无论论文是否新保存）
        if paper_id:
            try:
                db_ops.log_behavior(
                    user_id=user_id,
                    push_id=push_id,
                    paper_id=paper_id,
                    action="pushed",
                    action_type="push",
                    category=p.category,
                    metadata={
                        "score": p.score,
                        "category": p.category,
                        "relevance_signal": p.relevance_signal,
                        "rank": i + 1,
                        "push_context": "daily_push",
                        # Preserve source links so downstream selected-paper reading
                        # can still resolve the original landing page / PDF after DB reload.
                        "url": paper.get("url"),
                        "paper_url": paper.get("paper_url") or paper.get("url"),
                        "pdf_url": paper.get("pdf_url"),
                        "doi_url": paper.get("doi_url"),
                        "openreview_url": paper.get("openreview_url"),
                        "source": paper.get("source"),
                        "journal": paper.get("journal"),
                        "venue": paper.get("venue") or paper.get("journal"),
                        "publish_date": paper.get("publish_date"),
                        "categories": paper.get("categories", []),
                        "keywords": paper.get("keywords", []),
                        "topics": paper.get("topics", []),
                    }
                )
            except Exception as e:
                print(f"  Paper {i+1} log error: {e}")

    # 6. 输出
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(push_card)
        print(f"Push card written to: {output_file}")

    # 7. 发送到飞书
    if send_to_feishu:
        if FEISHU_AVAILABLE:
            try:
                # 优先使用传入的 chat_id，否则从画像读取，最后使用默认 user_id
                if feishu_chat_id:
                    print(f"Sending to Feishu chat: {feishu_chat_id}")
                    send_text_to_chat(feishu_chat_id, push_card)
                else:
                    # 从画像或 roles.json 读取 chat_id
                    resolved_chat_id = resolve_chat_id_for_user(user_id, profile)
                    if resolved_chat_id:
                        print(f"Sending to Feishu chat (resolved): {resolved_chat_id}")
                        send_text_to_chat(resolved_chat_id, push_card)
                    else:
                        # 使用默认 user_id
                        feishu_user_id = os.environ.get("FEISHU_USER_ID", "").strip()
                        if not feishu_user_id:
                            raise ValueError("Missing Feishu target. Configure feishu_chat_id in roles.json or FEISHU_USER_ID in .env.")
                        print(f"Sending to Feishu user: {feishu_user_id}")
                        send_daily_push(feishu_user_id, push_card)
                print("Push sent to Feishu successfully!")
            except Exception as e:
                print(f"Failed to send to Feishu: {e}")
        else:
            print("Feishu reporter not available, skipping send")
    elif not output_file:
        # 既不发送到飞书也不输出文件，则打印到控制台（移除 emoji 避免编码问题）
        ascii_push_card = push_card.replace("📰", "[PAPER]").replace("🔒", "[LOCK]").replace("🔴", "[RED]").replace("🟡", "[YEL]").replace("🔵", "[BLUE]")
        print("\n" + ascii_push_card)

    # 8. 统计
    must_read_count = sum(1 for p in scored_papers if p.category == "must_read")
    high_relevant_count = sum(1 for p in scored_papers if p.category == "high_relevant")
    maybe_interested_count = sum(1 for p in scored_papers if p.category == "maybe_interested")

    print("\n--- Summary ---")
    # 使用 ASCII 文本避免 Windows 编码问题
    print(f"[MUST READ]    : {must_read_count}")
    print(f"[HIGH RELEVANT]: {high_relevant_count}")
    print(f"[MAYBE INTERESTED]: {maybe_interested_count}")
    edge_count = len(scored_papers) - must_read_count - high_relevant_count - maybe_interested_count
    print(f"[EDGE RELEVANT]: {edge_count}")
    return {
        "success": True,
        "push_id": push_id,
        "paper_count": len(scored_papers),
        "total_fetched": len(papers),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Daily Push Agent - Multi-Source")
    parser.add_argument("--user-id", type=str, default="user_001", help="User ID")
    parser.add_argument("--days", type=int, default=1, help="Fetch papers from last N days")
    parser.add_argument("--arxiv-categories", nargs="+", default=None, help="arXiv categories")
    parser.add_argument("--conferences", nargs="+", default=None, help="Conference names")
    parser.add_argument("--journals", nargs="+", default=None, help="Journal names")
    parser.add_argument("--limit-per-source", type=int, default=30, help="Max papers per source")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--send-feishu", action="store_true", help="Send to Feishu")
    parser.add_argument("--chat-id", type=str, help="Feishu chat ID (for multi-role)")

    args = parser.parse_args()

    daily_push(
        user_id=args.user_id,
        days=args.days,
        arxiv_categories=args.arxiv_categories,
        conferences=args.conferences,
        journals=args.journals,
        limit_per_source=args.limit_per_source,
        output_file=args.output,
        send_to_feishu=args.send_feishu,
        feishu_chat_id=args.chat_id
    )
