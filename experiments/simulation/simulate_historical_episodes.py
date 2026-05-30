#!/usr/bin/env python3
"""
Simulate Historical Episodes - 支持兴趣漂移

对指定日期范围内的每一天，模拟：
1. 从论文池选择当天发表的论文
2. 为 24 个用户生成推送
3. 模拟用户反馈（选择/跳过）
4. 应用兴趣漂移（根据 checkfile 随机触发）
5. 记录画像快照、Episode、漂移事件

使用方法:
    python scripts/simulate_historical_episodes.py \
      --start-date 20260301 \
      --end-date 20260420 \
      --llm-model gemini-3-flash-preview \
      --drift-probability 0.5 \
      --output-dir data/simulation_output
"""

import argparse
import copy
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(PROJECT_ROOT))

# 导入 drift_engine
from scripts.drift_engine import (
    DriftEngine,
    load_checkfiles,
    create_drift_event,
    to_display_drift_status,
)
from scripts.collect_all_papers import collect_all_papers

# 导入 token 统计工具
from experiments.token_cost.token_usage_tracker import log_token_usage, estimate_tokens
import importlib

DB_PATH = PROJECT_ROOT / "data" / "paperflow.db"
DRIFT_CHECKFILES_DIR = PROJECT_ROOT / "data" / "drift_checkfiles"
direction_lexicon = importlib.import_module("config.direction_lexicon")
daily_push_agent = importlib.import_module("deployments.feishu.daily-push-agent.main")
reading_agent = importlib.import_module("agents.reading-agent.main")
embedding_module = importlib.import_module("skills.embedding.scripts.embed")
llm_parser_module = importlib.import_module("agents.master-coordinator.scripts.llm_parser")
profile_updater_module = importlib.import_module("skills.profile-updater.scripts.update_profile")
is_must_read = profile_updater_module.is_must_read


def _extract_usage_dict(usage: Any) -> Dict[str, int]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


class TokenUsageRecorder:
    def __init__(self) -> None:
        self.current: Dict[str, Any] = {}
        self.rows: List[Dict[str, Any]] = []

    @contextmanager
    def scope(self, **kwargs):
        previous = dict(self.current)
        self.current = {**previous, **kwargs}
        try:
            yield
        finally:
            self.current = previous

    def record(self, *, model: str, usage: Dict[str, int], default_task_type: str) -> None:
        task_type = str(self.current.get("task_type") or default_task_type)
        record = {
            "task_type": task_type,
            "model": model,
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
            "user_id": self.current.get("user_id"),
            "date": self.current.get("date"),
            "extra": self.current.get("extra") or {},
        }
        log_token_usage(**record)
        self.rows.append(
            {
                "task_type": task_type,
                "model": model,
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
                "date": self.current.get("date"),
            }
        )

    def totals_for_date(self, date: str) -> Dict[str, int]:
        embedding = 0
        llm = 0
        for row in self.rows:
            if row.get("date") != date:
                continue
            total = int(row.get("total_tokens") or 0)
            if "embedding" in str(row.get("task_type") or "").lower():
                embedding += total
            else:
                llm += total
        return {"embedding": embedding, "llm": llm}

    def flush_logs(self) -> None:
        """Flush token logs to file"""
        from experiments.token_cost.token_usage_tracker import flush_token_logs
        flush_token_logs()


TOKEN_RECORDER = TokenUsageRecorder()


def _patch_real_usage_logging():
    original_embedding_init = embedding_module.EmbeddingService.__init__
    original_get_openai_client = llm_parser_module._get_openai_client

    def patched_embedding_init(self, *args, **kwargs):
        original_embedding_init(self, *args, **kwargs)
        if getattr(self, "provider", None) == "openai" and getattr(self, "client", None) is not None:
            original_create = self.client.embeddings.create
            if not getattr(original_create, "_paperflow_usage_wrapped", False):
                def wrapped_create(*create_args, **create_kwargs):
                    response = original_create(*create_args, **create_kwargs)
                    usage = _extract_usage_dict(getattr(response, "usage", None))
                    model = str(create_kwargs.get("model") or getattr(self, "model", ""))
                    TOKEN_RECORDER.record(model=model, usage=usage, default_task_type="embedding")
                    return response

                wrapped_create._paperflow_usage_wrapped = True  # type: ignore[attr-defined]
                self.client.embeddings.create = wrapped_create

    def patched_get_openai_client(timeout_override: Optional[float] = None):
        client = original_get_openai_client(timeout_override=timeout_override)
        if client is None:
            return None
        original_chat_create = client.chat.completions.create
        if not getattr(original_chat_create, "_paperflow_usage_wrapped", False):
            def wrapped_chat_create(*create_args, **create_kwargs):
                response = original_chat_create(*create_args, **create_kwargs)
                usage = _extract_usage_dict(getattr(response, "usage", None))
                model = str(create_kwargs.get("model") or "")
                TOKEN_RECORDER.record(model=model, usage=usage, default_task_type="llm_report")
                return response

            wrapped_chat_create._paperflow_usage_wrapped = True  # type: ignore[attr-defined]
            client.chat.completions.create = wrapped_chat_create
        return client

    embedding_module.EmbeddingService.__init__ = patched_embedding_init
    llm_parser_module._get_openai_client = patched_get_openai_client
    return original_embedding_init, original_get_openai_client


def _unpatch_real_usage_logging(original_embedding_init, original_get_openai_client):
    embedding_module.EmbeddingService.__init__ = original_embedding_init
    llm_parser_module._get_openai_client = original_get_openai_client


# ==================== 输出目录管理 ====================

SIMULATION_OUTPUT_FILES = (
    "paper_pools.jsonl",
    "profiles.jsonl",
    "profiles_state.jsonl",
    "episodes.jsonl",
    "episode_papers.jsonl",
    "reading_reports.jsonl",
    "drift_timeline.jsonl",
    "users.json",
    "simulation_summary.json",
)


def clear_simulation_output_files(output_dir: Path) -> None:
    """Remove managed simulation artifacts before a fresh run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in SIMULATION_OUTPUT_FILES:
        path = output_dir / filename
        if path.exists():
            path.unlink()
    report_dir = output_dir / "reading_reports_md"
    if report_dir.exists():
        shutil.rmtree(report_dir)


def _read_jsonl_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _summarize_interest_vector(vector: Any) -> Dict[str, Any]:
    values = vector if isinstance(vector, list) else []
    numeric_values: List[float] = []
    for value in values:
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            continue

    nonzero_count = sum(1 for value in numeric_values if abs(value) > 1e-12)
    l2_norm = sum(value * value for value in numeric_values) ** 0.5
    return {
        "dim": len(numeric_values),
        "nonzero_count": nonzero_count,
        "l2_norm": round(l2_norm, 6),
    }


def _sanitize_profile_snapshot(profile_record: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = copy.deepcopy(profile_record)
    profile_json = copy.deepcopy(sanitized.get("profile_json") or {})
    if "interest_vector" in profile_json:
        profile_json["interest_vector_summary"] = _summarize_interest_vector(profile_json.get("interest_vector"))
        profile_json.pop("interest_vector", None)
    sanitized["profile_json"] = profile_json
    return sanitized


def _safe_filename_part(value: Any, max_chars: int = 80) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return (text[:max_chars].strip("-._") or "untitled")


def _reading_report_filename(report_record: Dict[str, Any]) -> str:
    date = _safe_filename_part(report_record.get("date"), max_chars=10)
    user_id = _safe_filename_part(report_record.get("user_id"), max_chars=16)
    paper_id = report_record.get("paper_id")
    if paper_id is None:
        paper_part = hashlib.sha1(str(report_record.get("title") or "").encode("utf-8")).hexdigest()[:10]
    else:
        paper_part = _safe_filename_part(paper_id, max_chars=16)
    title_hash = hashlib.sha1(str(report_record.get("title") or "").encode("utf-8")).hexdigest()[:8]
    title_part = _safe_filename_part(report_record.get("title"), max_chars=32)
    return f"{date}_{user_id}_{paper_part}_{title_hash}_{title_part}.md"


def _load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_title_key(title: str) -> str:
    return " ".join(str(title or "").strip().lower().split())


def make_report_key_for_paper(user_id: str, paper: Dict[str, Any]) -> Optional[str]:
    paper_id = paper.get("paper_id")
    if paper_id is not None:
        return f"{user_id}::paper::{paper_id}"

    doi = str(paper.get("doi") or "").strip().lower()
    if doi:
        return f"{user_id}::doi::{doi}"

    arxiv_id = str(paper.get("arxiv_id") or "").strip().lower()
    if arxiv_id:
        return f"{user_id}::arxiv::{arxiv_id}"

    title_key = _normalize_title_key(str(paper.get("title") or ""))
    if title_key:
        return f"{user_id}::title::{title_key}"

    return None


def load_resume_state(output_dir: Path, start_date: datetime) -> Dict[str, Any]:
    """
    Resume only when the output directory contains profile snapshots for the
    immediately previous day. This keeps segmented runs equivalent to one
    continuous run when they share the same output directory.
    """
    start_day = start_date.strftime("%Y-%m-%d")
    previous_day = (start_date - timedelta(days=1)).strftime("%Y-%m-%d")
    profile_state_path = output_dir / "profiles_state.jsonl"
    profile_rows = _read_jsonl_records(profile_state_path if profile_state_path.exists() else output_dir / "profiles.jsonl")

    if not profile_rows:
        return {
            "resume": False,
            "previous_day": previous_day,
            "profiles_by_user": {},
            "generated_report_keys": set(),
            "user_metadata": None,
            "existing_summary": None,
        }

    existing_dates = sorted({str(row.get("date") or "") for row in profile_rows if str(row.get("date") or "").strip()})
    overlapping_dates = [date for date in existing_dates if date >= start_day]
    previous_day_rows = [row for row in profile_rows if row.get("date") == previous_day]

    if previous_day_rows and not overlapping_dates:
        profiles_by_user = {
            str(row.get("user_id")): {
                "profile": copy.deepcopy(row.get("profile_json") or {}),
                "version": row.get("version", "0.1"),
            }
            for row in previous_day_rows
            if str(row.get("user_id") or "").strip()
        }

        generated_report_keys: Set[str] = set()
        for row in _read_jsonl_records(output_dir / "episodes.jsonl"):
            user_id = str(row.get("user_id") or "").strip()
            if not user_id:
                continue
            for paper_id in row.get("selected_paper_ids", []) or []:
                if paper_id is not None:
                    generated_report_keys.add(f"{user_id}::paper::{paper_id}")
            for title in row.get("selected_paper_titles", []) or []:
                title_key = _normalize_title_key(title)
                if title_key:
                    generated_report_keys.add(f"{user_id}::title::{title_key}")

        return {
            "resume": True,
            "previous_day": previous_day,
            "profiles_by_user": profiles_by_user,
            "generated_report_keys": generated_report_keys,
            "user_metadata": (_load_json_file(output_dir / "users.json") or {}).get("users"),
            "existing_summary": _load_json_file(output_dir / "simulation_summary.json"),
        }

    latest_date = existing_dates[-1] if existing_dates else "unknown"
    if overlapping_dates:
        raise RuntimeError(
            f"Output directory already contains data on/after {start_day} "
            f"(latest existing date: {latest_date}). Use a new output dir or clear the old one."
        )

    raise RuntimeError(
        f"Cannot resume from {start_day}: output directory only has data through {latest_date}, "
        f"but segmented runs require the previous day {previous_day}."
    )


def apply_resumed_profiles(users: List[Dict[str, Any]], profiles_by_user: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    updated_users: List[Dict[str, Any]] = []
    for user in users:
        resumed = profiles_by_user.get(user["user_id"])
        if resumed:
            updated_users.append(
                {
                    **user,
                    "profile": copy.deepcopy(resumed.get("profile") or user["profile"]),
                    "version": resumed.get("version", user.get("version", "0.1")),
                }
            )
        else:
            updated_users.append(user)
    return updated_users


def filter_users_by_ids(users: List[Dict[str, Any]], user_ids: List[str]) -> List[Dict[str, Any]]:
    ordered: List[Dict[str, Any]] = []
    users_by_id = {user["user_id"]: user for user in users}
    for user_id in user_ids:
        if user_id in users_by_id:
            ordered.append(users_by_id[user_id])
    return ordered


def merge_summary_with_previous(
    previous_summary: Optional[Dict[str, Any]],
    *,
    current_start: str,
    current_end: str,
    added_days: int,
    added_new_papers: int,
    added_embedding_tokens: int,
    added_llm_tokens: int,
    added_drifts: int,
    added_episodes: int,
    output_dir: Path,
    drift_probability: float,
    sources: Optional[List[str]],
    limit_per_source: Optional[int],
    skip_collection: bool,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    previous_period = (previous_summary or {}).get("period", {}) or {}
    previous_paper_collection = (previous_summary or {}).get("paper_collection", {}) or {}
    previous_tokens = (previous_summary or {}).get("token_usage", {}) or {}

    summary = {
        "period": {
            "start": previous_period.get("start", current_start),
            "end": current_end,
            "days": int(previous_period.get("days", 0) or 0) + added_days,
        },
        "drift_probability": drift_probability,
        "paper_collection": {
            "skip_collection": bool(skip_collection),
            "sources": sources or ["arxiv", "openreview", "journal"],
            "limit_per_source": limit_per_source,
            "total_new_papers_collected": int(previous_paper_collection.get("total_new_papers_collected", 0) or 0) + added_new_papers,
        },
        "token_usage": {
            "embedding_model": previous_tokens.get("embedding_model"),
            "llm_model": previous_tokens.get("llm_model"),
            "embedding_tokens": int(previous_tokens.get("embedding_tokens", 0) or 0) + added_embedding_tokens,
            "llm_tokens": int(previous_tokens.get("llm_tokens", 0) or 0) + added_llm_tokens,
            "total_tokens": int(previous_tokens.get("total_tokens", 0) or 0) + added_embedding_tokens + added_llm_tokens,
        },
        "total_drifts": int((previous_summary or {}).get("total_drifts", 0) or 0) + added_drifts,
        "total_episodes": int((previous_summary or {}).get("total_episodes", 0) or 0) + added_episodes,
        "output_dir": str(output_dir),
    }

    if extra_fields:
        summary.update(extra_fields)

    return summary

class OutputManager:
    """管理所有 JSONL 输出文件（每个层一个大文件）"""

    def __init__(self, output_dir: str, *, reset_existing: bool = False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if reset_existing:
            clear_simulation_output_files(self.output_dir)

        # 所有文件都在根目录，不需要子目录
        self._paper_pool_file: Optional[Any] = None
        self._profile_file: Optional[Any] = None
        self._profile_state_file: Optional[Any] = None
        self._episode_file: Optional[Any] = None
        self._episode_paper_file: Optional[Any] = None
        self._reading_report_file: Optional[Any] = None
        self._drift_file: Optional[Any] = None
        self._users_path: Optional[Path] = None

    @property
    def paper_pool_file(self) -> Any:
        if self._paper_pool_file is None:
            path = self.output_dir / "paper_pools.jsonl"
            self._paper_pool_file = path.open("a", encoding="utf-8")
        return self._paper_pool_file

    @property
    def profile_file(self) -> Any:
        if self._profile_file is None:
            path = self.output_dir / "profiles.jsonl"
            self._profile_file = path.open("a", encoding="utf-8")
        return self._profile_file

    @property
    def profile_state_file(self) -> Any:
        if self._profile_state_file is None:
            path = self.output_dir / "profiles_state.jsonl"
            self._profile_state_file = path.open("a", encoding="utf-8")
        return self._profile_state_file

    @property
    def episode_file(self) -> Any:
        if self._episode_file is None:
            path = self.output_dir / "episodes.jsonl"
            self._episode_file = path.open("a", encoding="utf-8")
        return self._episode_file

    @property
    def episode_paper_file(self) -> Any:
        if self._episode_paper_file is None:
            path = self.output_dir / "episode_papers.jsonl"
            self._episode_paper_file = path.open("a", encoding="utf-8")
        return self._episode_paper_file

    @property
    def reading_report_file(self) -> Any:
        if self._reading_report_file is None:
            path = self.output_dir / "reading_reports.jsonl"
            self._reading_report_file = path.open("a", encoding="utf-8")
        return self._reading_report_file

    @property
    def drift_file(self) -> Any:
        if self._drift_file is None:
            path = self.output_dir / "drift_timeline.jsonl"
            self._drift_file = path.open("a", encoding="utf-8")
        return self._drift_file

    @property
    def users_path(self) -> Path:
        if self._users_path is None:
            self._users_path = self.output_dir / "users.json"
        return self._users_path

    def save_paper_pool(
        self,
        date: str,
        papers: List[Dict],
        new_papers_count: int = 0,
        total_papers: Optional[int] = None,
    ) -> None:
        """保存每日论文池：papers 只放当天论文，total 记录截至当天累计总量。"""
        record = {
            "date": date,
            "total": int(total_papers if total_papers is not None else len(papers)),
            "new_papers_count": new_papers_count,
            "papers": papers,
        }
        self.paper_pool_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.paper_pool_file.flush()

    def save_user_metadata(self, users: List[Dict]) -> None:
        """保存用户元数据"""
        with self.users_path.open("w", encoding="utf-8") as f:
            json.dump({"users": users}, f, ensure_ascii=False, indent=2)

    def write_profile(self, profile_record: Dict) -> None:
        """写入画像快照（所有日期合并到一个文件）"""
        self.profile_state_file.write(json.dumps(profile_record, ensure_ascii=False) + "\n")
        self.profile_state_file.flush()
        self.profile_file.write(json.dumps(_sanitize_profile_snapshot(profile_record), ensure_ascii=False) + "\n")
        self.profile_file.flush()

    def write_episode(self, episode_record: Dict) -> None:
        """写入 Episode 记录（所有日期合并到一个文件）"""
        self.episode_file.write(json.dumps(episode_record, ensure_ascii=False) + "\n")
        self.episode_file.flush()

    def write_episode_paper(self, episode_paper_record: Dict) -> None:
        self.episode_paper_file.write(json.dumps(episode_paper_record, ensure_ascii=False) + "\n")
        self.episode_paper_file.flush()

    def write_reading_report(self, report_record: Dict) -> None:
        self.reading_report_file.write(json.dumps(report_record, ensure_ascii=False) + "\n")
        self.reading_report_file.flush()

        content = str(report_record.get("report_content") or "").strip()
        if not content:
            return
        report_dir = self.output_dir / "reading_reports_md"
        report_dir.mkdir(parents=True, exist_ok=True)
        filename = _reading_report_filename(report_record)
        (report_dir / filename).write_text(content, encoding="utf-8")

    def write_drift_event(self, drift_event: Dict) -> None:
        """写入漂移事件（所有日期合并到一个文件）"""
        self.drift_file.write(json.dumps(drift_event, ensure_ascii=False) + "\n")
        self.drift_file.flush()

    def close(self) -> None:
        """关闭所有文件句柄"""
        if self._paper_pool_file:
            self._paper_pool_file.close()
        if self._profile_file:
            self._profile_file.close()
        if self._profile_state_file:
            self._profile_state_file.close()
        if self._episode_file:
            self._episode_file.close()
        if self._episode_paper_file:
            self._episode_paper_file.close()
        if self._reading_report_file:
            self._reading_report_file.close()
        if self._drift_file:
            self._drift_file.close()
        # users.json is written atomically in save_user_metadata, so no handle needs closing.


# ==================== 数据获取 ====================

def build_paper_links(arxiv_id: str, doi: str, venue: str, title: str = "") -> Dict[str, str]:
    """
    构建论文链接（arXiv + DOI + 会议/期刊官网）

    优先级：期刊官网 > DOI > arXiv
    """
    links = {}
    venue_lower = (venue or "").lower()
    search_query = doi or arxiv_id or title

    # arXiv 链接
    if arxiv_id:
        links["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
        links["arxiv_pdf_url"] = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # DOI 链接（通用）
    if doi:
        links["doi_url"] = f"https://doi.org/{doi}"

    # 会议官网链接
    if "acl" in venue_lower or "emnlp" in venue_lower or "naacl" in venue_lower or "coling" in venue_lower:
        links["venue_url"] = f"https://aclanthology.org/search/?q={search_query}"
        links["venue_name"] = "ACL Anthology"
    elif "iclr" in venue_lower:
        links["venue_url"] = f"https://openreview.net/forum?id={arxiv_id or search_query}"
        links["venue_name"] = "ICLR (OpenReview)"
    elif "neurips" in venue_lower or "nips" in venue_lower:
        links["venue_url"] = f"https://papers.nips.cc/paper_files/search?q={search_query}"
        links["venue_name"] = "NeurIPS Proceedings"
    elif "icml" in venue_lower:
        links["venue_url"] = f"https://proceedings.mlr.press/search?q={search_query}"
        links["venue_name"] = "ICML Proceedings"
    elif "cvpr" in venue_lower:
        links["venue_url"] = f"https://openaccess.thecvf.com/search?q={search_query}"
        links["venue_name"] = "CVF Open Access"
    elif "iccv" in venue_lower:
        links["venue_url"] = f"https://openaccess.thecvf.com/search?q={search_query}"
        links["venue_name"] = "CVF Open Access"
    elif "eccv" in venue_lower:
        links["venue_url"] = f"https://link.springer.com/search?query={search_query}&facet-conference=%22ECCV%22"
        links["venue_name"] = "ECCV (Springer)"
    elif "aaai" in venue_lower:
        links["venue_url"] = f"https://ojs.aaai.org/index.php/AAAI/search/search?query={search_query}"
        links["venue_name"] = "AAAI Proceedings"

    # 期刊官网链接
    elif "nature" in venue_lower:
        links["venue_url"] = f"https://www.nature.com/search?q={doi or search_query}"
        links["venue_name"] = "Nature"
    elif "science" in venue_lower:
        links["venue_url"] = f"https://www.science.org/doi/{doi}" if doi else f"https://www.science.org/search?q={search_query}"
        links["venue_name"] = "Science"
    elif "cell" in venue_lower:
        links["venue_url"] = f"https://www.cell.com/doi/{doi}" if doi else f"https://www.cell.com/search?q={search_query}"
        links["venue_name"] = "Cell"
    elif "pnas" in venue_lower:
        links["venue_url"] = f"https://www.pnas.org/doi/{doi}" if doi else f"https://www.pnas.org/action/doSearch?AllField={search_query}"
        links["venue_name"] = "PNAS"
    elif "acm" in venue_lower:
        links["venue_url"] = f"https://dl.acm.org/action/doSearch?AllField={search_query}"
        links["venue_name"] = "ACM Digital Library"
    elif "ieee" in venue_lower:
        links["venue_url"] = f"https://ieeexplore.ieee.org/search/all?queryText={search_query}"
        links["venue_name"] = "IEEE Xplore"
    elif "springer" in venue_lower:
        links["venue_url"] = f"https://link.springer.com/search?query={search_query}"
        links["venue_name"] = "SpringerLink"
    elif "elsevier" in venue_lower or "sciencedirect" in venue_lower:
        links["venue_url"] = f"https://www.sciencedirect.com/search?qs={search_query}"
        links["venue_name"] = "ScienceDirect"

    return links


def _parse_authors_field(raw_value: Any) -> List[str]:
    """Support both JSON-list authors and legacy plain-text author strings."""
    if raw_value in (None, "", []):
        return []
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        if parsed is not None:
            return [str(parsed).strip()]
        return [item.strip() for item in raw_value.split(",") if item.strip()]
    return [str(raw_value).strip()]


def _direction_match_terms(direction: str) -> List[str]:
    """Expand a direction key into text forms that are likely to appear in papers."""
    cleaned = str(direction or "").strip()
    if not cleaned:
        return []

    terms = {
        cleaned.lower(),
        cleaned.lower().replace("-", " "),
        cleaned.lower().replace("_", " "),
    }

    try:
        resolved = direction_lexicon.resolve_canonical_direction(cleaned, include_paper_terms=True)
    except Exception:
        resolved = None

    entry = (resolved or {}).get("entry") or {}
    for raw_term in (
        [entry.get("name"), entry.get("name_cn")]
        + list(entry.get("aliases", []) or [])
        + list(entry.get("paper_terms", []) or [])
    ):
        if raw_term:
            lowered = str(raw_term).strip().lower()
            if lowered:
                terms.add(lowered)
                terms.add(lowered.replace("-", " "))
                terms.add(lowered.replace("_", " "))

    return [term for term in terms if term]


def _normalize_direction_match_text(value: Any) -> str:
    """Normalize text so short terms like RL only match as standalone tokens."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _text_matches_direction_terms(text: str, terms: List[str]) -> bool:
    normalized_text = f" {_normalize_direction_match_text(text)} "
    if not normalized_text.strip():
        return False
    for term in terms:
        normalized_term = _normalize_direction_match_text(term)
        if normalized_term and f" {normalized_term} " in normalized_text:
            return True
    return False


def get_all_papers(conn: sqlite3.Connection) -> List[Dict]:
    """从论文池获取所有论文"""
    papers = conn.execute("""
        SELECT id, arxiv_id, doi, title, authors, institution, abstract, venue, publish_date
        FROM papers
        ORDER BY publish_date DESC
    """).fetchall()

    result = []
    for p in papers:
        paper = {
            "paper_id": p[0],
            "arxiv_id": p[1] or "",
            "doi": p[2] or "",
            "title": p[3] or "",
            "authors": _parse_authors_field(p[4]),
            "institution": p[5] or "",
            "abstract": p[6] or "",
            "venue": p[7] or "",
            "publish_date": p[8] or "",
        }
        paper.update(build_paper_links(paper["arxiv_id"], paper["doi"], paper["venue"]))
        result.append(paper)

    return result


def get_papers_by_date(conn: sqlite3.Connection, date: datetime) -> List[Dict]:
    """获取指定日期的论文"""
    date_str = date.strftime("%Y-%m-%d")
    papers = conn.execute("""
        SELECT id, arxiv_id, doi, title, authors, institution, abstract, venue, publish_date
        FROM papers
        WHERE publish_date >= ? AND publish_date <= ?
        ORDER BY publish_date
    """, (date_str, date_str)).fetchall()

    result = []
    for p in papers:
        paper = {
            "paper_id": p[0],
            "arxiv_id": p[1] or "",
            "doi": p[2] or "",
            "title": p[3] or "",
            "authors": _parse_authors_field(p[4]),
            "institution": p[5] or "",
            "abstract": p[6] or "",
            "venue": p[7] or "",
            "publish_date": p[8] or "",
        }
        paper.update(build_paper_links(paper["arxiv_id"], paper["doi"], paper["venue"]))
        result.append(paper)

    return result


def get_papers_up_to_date(conn: sqlite3.Connection, date: datetime) -> List[Dict]:
    """Get the cumulative paper pool available up to and including the given date."""
    date_str = date.strftime("%Y-%m-%d")
    papers = conn.execute("""
        SELECT id, arxiv_id, doi, title, authors, institution, abstract, venue, publish_date
        FROM papers
        WHERE publish_date <= ?
        ORDER BY publish_date DESC, id DESC
    """, (date_str,)).fetchall()

    result = []
    for p in papers:
        paper = {
            "paper_id": p[0],
            "arxiv_id": p[1] or "",
            "doi": p[2] or "",
            "title": p[3] or "",
            "authors": _parse_authors_field(p[4]),
            "institution": p[5] or "",
            "abstract": p[6] or "",
            "venue": p[7] or "",
            "publish_date": p[8] or "",
        }
        paper.update(build_paper_links(paper["arxiv_id"], paper["doi"], paper["venue"]))
        result.append(paper)

    return result


def get_all_users(conn: sqlite3.Connection) -> List[Dict]:
    """获取所有用户"""
    profiles = conn.execute("SELECT user_id, profile_json, version FROM profiles").fetchall()
    return [{
        "user_id": p[0],
        "profile": json.loads(p[1]),
        "version": p[2],
    } for p in profiles]


def _user_sort_key(user: Dict[str, Any]) -> Tuple[str, int, str]:
    user_id = str(user.get("user_id") or "")
    digits = "".join(ch for ch in user_id if ch.isdigit())
    return (user_id.rstrip("0123456789"), int(digits or 0), user_id)


def select_users(
    users: List[Dict[str, Any]],
    *,
    user_ids: Optional[List[str]] = None,
    user_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Select a stable user subset without modifying the database."""
    if user_ids:
        users_by_id = {str(user.get("user_id")): user for user in users}
        missing = [user_id for user_id in user_ids if user_id not in users_by_id]
        if missing:
            raise SystemExit(f"Unknown user id(s): {', '.join(missing)}")
        return [users_by_id[user_id] for user_id in user_ids]

    if user_count and user_count > 0:
        return sorted(users, key=_user_sort_key)[: min(user_count, len(users))]

    return users


def collect_papers_for_day(
    date: datetime,
    *,
    sources: Optional[List[str]] = None,
    limit_per_source: Optional[int] = None,
) -> int:
    """Collect papers for one exact day into the shared database."""
    day_key = date.strftime("%Y%m%d")
    return collect_all_papers(
        start_date=day_key,
        end_date=day_key,
        sources=sources,
        limit_per_source=limit_per_source,
    )


def load_roles_meta() -> Dict[str, Any]:
    roles_path = PROJECT_ROOT / "data" / "roles.json"
    if not roles_path.exists():
        return {}
    with roles_path.open("r", encoding="utf-8") as f:
        return json.load(f).get("roles", {})


# ==================== 论文匹配与选择 ====================

def match_paper_to_user(paper: Dict, user_profile: Dict) -> Tuple[str, float]:
    """根据用户研究方向匹配论文，返回相关度等级和分数"""
    core_directions = user_profile.get("core_directions", {})
    edge_directions = user_profile.get("edge_directions", {})

    if not edge_directions and core_directions:
        edge_directions = {k: v for k, v in core_directions.items() if v < 0.6}

    paper_title = (paper.get("title") or "").lower()
    paper_abstract = (paper.get("abstract") or "").lower()
    paper_text = f"{paper_title} {paper_abstract}"

    max_core_score = 0.0
    for direction, score in core_directions.items():
        if _text_matches_direction_terms(paper_text, _direction_match_terms(direction)):
            max_core_score = max(max_core_score, score)

    max_edge_score = 0.0
    for direction, score in edge_directions.items():
        if _text_matches_direction_terms(paper_text, _direction_match_terms(direction)):
            max_edge_score = max(max_edge_score, score * 0.7)

    anchor_behavior = _get_anchor_behavior(user_profile)
    anchor_score = 0.0
    if anchor_behavior["target_topic"] and _paper_matches_topic(paper, anchor_behavior["target_topic"]):
        anchor_score = anchor_behavior["push_bonus"]

    suppressed_hit = any(_paper_matches_topic(paper, topic) for topic in anchor_behavior["suppressed_topics"])
    if suppressed_hit and not (anchor_behavior["target_topic"] and _paper_matches_topic(paper, anchor_behavior["target_topic"])):
        penalty = anchor_behavior["suppression_penalty"]
        max_core_score = max(0.0, max_core_score - penalty)
        max_edge_score = max(0.0, max_edge_score - penalty)

    decayed_penalty = 0.0
    for topic, stale_score in anchor_behavior["decayed_topics"].items():
        if _paper_matches_topic(paper, topic):
            decayed_penalty = max(decayed_penalty, min(0.18, float(stale_score) * 0.18))
    if decayed_penalty > 0:
        max_core_score = max(0.0, max_core_score - decayed_penalty)
        max_edge_score = max(0.0, max_edge_score - decayed_penalty)

    final_score = max(max_core_score, max_edge_score, anchor_score)

    if is_must_read(paper, user_profile):
        return "must_read", max(final_score, max_core_score, 0.8)
    if max_core_score >= 0.8:
        return "must_read", final_score
    elif max(max_core_score, anchor_score) >= 0.5:
        return "high_relevant", final_score
    elif max(max_edge_score, anchor_score) >= 0.3:
        return "maybe_interested", final_score
    else:
        return "edge_relevant", final_score


def _paper_matches_topic(paper: Dict, topic: Optional[str]) -> bool:
    topic_text = str(topic or "").strip()
    if not topic_text:
        return False
    paper_title = (paper.get("title") or "").lower()
    paper_abstract = (paper.get("abstract") or "").lower()
    paper_text = f"{paper_title} {paper_abstract}"
    return _text_matches_direction_terms(paper_text, _direction_match_terms(topic_text))


def _get_suppressed_topics(user_profile: Dict[str, Any]) -> List[str]:
    drift_state = user_profile.get("drift_state", {}) or {}
    suppressed = [str(topic).strip() for topic in (drift_state.get("suppressed_topics", []) or []) if str(topic).strip()]
    if suppressed:
        return suppressed
    if drift_state.get("drift_enabled") or drift_state.get("anchor_topic"):
        return [
            str(topic).strip()
            for topic in ((user_profile.get("drift_plan", {}) or {}).get("downweight_topics", []) or [])
            if str(topic).strip()
        ]
    return []


def _get_decayed_topics(user_profile: Dict[str, Any]) -> Dict[str, float]:
    drift_state = user_profile.get("drift_state", {}) or {}
    topic_staleness = drift_state.get("topic_staleness", {}) or {}
    return {
        str(topic).strip(): float(score)
        for topic, score in topic_staleness.items()
        if str(topic).strip()
    }


def _get_anchor_behavior(user_profile: Dict[str, Any]) -> Dict[str, Any]:
    drift_state = user_profile.get("drift_state", {}) or {}
    target_topic = None
    push_bonus = 0.0
    exploration_quota = 0
    feedback_anchor_quota = 0
    observing_select_probability = 0.0
    suppression_penalty = 0.0

    if drift_state.get("anchor_topic"):
        target_topic = str(drift_state.get("anchor_topic") or "").strip()
        progress = float(drift_state.get("anchor_progress", 0.0) or 0.0)
        if int(drift_state.get("commitment_days_remaining", 0) or 0) > 0:
            push_bonus = 0.42 + min(0.18, progress * 0.2)
            exploration_quota = 4
            feedback_anchor_quota = 3
            suppression_penalty = 0.28
        else:
            push_bonus = 0.34 + min(0.12, progress * 0.12)
            exploration_quota = 2
            feedback_anchor_quota = 2
            suppression_penalty = 0.18
    elif drift_state.get("drift_enabled") and drift_state.get("hidden_anchor"):
        target_topic = str(drift_state.get("hidden_anchor") or "").strip()
        if drift_state.get("status") == "observing":
            # During observing, keep anchor-matching papers in a trial band
            # and let the simulated user choose them with an 80% probability.
            push_bonus = 0.38
            exploration_quota = 3
            feedback_anchor_quota = 1
            observing_select_probability = 0.8
        else:
            push_bonus = 0.30
            exploration_quota = 2
            feedback_anchor_quota = 1
        suppression_penalty = 0.12

    return {
        "target_topic": target_topic or None,
        "push_bonus": push_bonus,
        "exploration_quota": exploration_quota,
        "feedback_anchor_quota": feedback_anchor_quota,
        "observing_select_probability": observing_select_probability,
        "suppressed_topics": _get_suppressed_topics(user_profile),
        "decayed_topics": _get_decayed_topics(user_profile),
        "suppression_penalty": suppression_penalty,
    }


def _check_recovery(user: Dict, selected_for_reading: List[Dict], date: str) -> Optional[Dict[str, Any]]:
    """
    检查用户是否应该从漂移状态恢复

    当用户选中大量 must_read 或 high_relevant 论文时，
    说明用户重新聚焦原有核心方向，可以降低 drift_score
    """
    profile = user.get("profile", {})
    drift_state = profile.get("drift_state", {})
    strategy_mode = str(drift_state.get("strategy_mode") or "simulation")
    updated_profile, recovery_event = __import__("scripts.drift_engine", fromlist=["dummy"]).advance_anchor_recovery(
        profile,
        selected_for_reading,
        date,
        strategy_mode=strategy_mode,
    )
    if recovery_event is not None:
        user["profile"] = updated_profile
        if updated_profile.get("drift_state", {}).get("status") == "recovered":
            print(f"[Recovery] User {user.get('user_id')} entered recovered")
        elif updated_profile.get("drift_state", {}).get("status") == "stable":
            print(f"[Recovery] User {user.get('user_id')} returned to stable")
        return recovery_event
    return None


SYSTEM_CATEGORY_PRIORITY = {
    "must_read": 0,
    "high_relevant": 1,
    "maybe_interested": 2,
    "edge_relevant": 3,
}


_REAL_DAILY_PUSH_WEIGHTS: Optional[Dict[str, Any]] = None
DEFAULT_SIMULATION_SHOW_COUNT = 30


def _load_real_daily_push_weights() -> Dict[str, Any]:
    """Load the same ranking weights used by the real daily-push agent."""
    global _REAL_DAILY_PUSH_WEIGHTS
    if _REAL_DAILY_PUSH_WEIGHTS is None:
        _REAL_DAILY_PUSH_WEIGHTS = copy.deepcopy(daily_push_agent.load_scoring_weights() or {})
    return copy.deepcopy(_REAL_DAILY_PUSH_WEIGHTS)


def _paper_identity(paper: Dict[str, Any]) -> str:
    paper_id = paper.get("paper_id")
    if paper_id is not None:
        return f"paper::{paper_id}"
    return f"title::{_normalize_title_key(str(paper.get('title') or ''))}"


def _sort_system_candidates(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        papers,
        key=lambda item: (
            SYSTEM_CATEGORY_PRIORITY.get(str(item.get("relevance_level") or "edge_relevant"), 9),
            -float(item.get("relevance_score") or 0.0),
            str(item.get("title") or ""),
        ),
    )


def _paper_text_blob(paper: Dict[str, Any]) -> str:
    categories = " ".join(str(value or "").strip() for value in (paper.get("categories") or []))
    return " ".join(
        part.lower()
        for part in (
            str(paper.get("title") or "").strip(),
            str(paper.get("abstract") or "").strip(),
            str(paper.get("venue") or "").strip(),
            categories,
        )
        if part
    )


def _normalize_string_values(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        parts = [stripped]
        for separator in (";", ",", "|"):
            if separator in stripped:
                parts = [part for chunk in parts for part in chunk.split(separator)]
        return [part.strip() for part in parts if part.strip()]
    return [str(value).strip()]


def _infer_simulation_paper_source(paper: Dict[str, Any]) -> str:
    source = str(paper.get("source") or "").lower().strip()
    if source:
        return source
    venue = str(paper.get("venue") or paper.get("journal") or "").lower()
    if paper.get("arxiv_id") or "arxiv" in venue:
        return "arxiv"
    if any(name in venue for name in ("neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "acl", "emnlp", "openreview")):
        return "openreview"
    if any(name in venue for name in ("nature", "science", "cell", "journal")):
        return "journal"
    return "unknown"


def _collect_profile_match_topics(user_profile: Dict[str, Any]) -> List[str]:
    topics: List[str] = []
    topics.extend((user_profile.get("core_directions", {}) or {}).keys())
    topics.extend((user_profile.get("edge_directions", {}) or {}).keys())
    topics.extend((user_profile.get("topic_weights", {}) or {}).keys())
    topics.extend(user_profile.get("secondary_topics", []) or [])

    drift_plan = user_profile.get("drift_plan", {}) or {}
    topics.extend(drift_plan.get("shift_topics", []) or [])
    topics.extend(drift_plan.get("downweight_topics", []) or [])

    drift_state = user_profile.get("drift_state", {}) or {}
    for key in ("hidden_anchor", "anchor_topic"):
        if drift_state.get(key):
            topics.append(drift_state.get(key))
    topics.extend(drift_state.get("anchor_topics", []) or [])
    topics.extend(drift_state.get("top_shift_topics", []) or [])
    topics.extend((drift_state.get("short_term_topics", {}) or {}).keys())

    return direction_lexicon.canonicalize_direction_terms(topics, keep_unknown=True)


def _prepare_simulation_paper_features(
    papers: List[Dict[str, Any]],
    *,
    date_str: str,
) -> None:
    """
    Attach the feature fields expected by the real daily-push scorer.

    Historical rows loaded from SQLite do not always retain the exact in-memory
    fields produced by daily-push fetching, so simulation rebuilds them before
    delegating ranking to the real scorer.
    """
    if not papers:
        return

    embedding_service = embedding_module.get_embedding_service()
    descriptor = getattr(embedding_service, "descriptor", "")
    for paper in papers:
        if not paper.get("embedding"):
            with TOKEN_RECORDER.scope(
                task_type="embedding",
                date=date_str,
                extra={"paper_id": paper.get("paper_id"), "title": str(paper.get("title") or "")[:120]},
            ):
                paper["embedding"] = embedding_service.embed_text(daily_push_agent.build_paper_text(paper))
        paper["embedding_model"] = paper.get("embedding_model") or descriptor
        paper["institution"] = str(paper.get("institution") or "")
        paper["source"] = _infer_simulation_paper_source(paper)
        paper["quality_score"] = daily_push_agent.estimate_quality_score(paper)

        existing_topics = _normalize_string_values(paper.get("topics"))
        title_topics = daily_push_agent.extract_topics_from_title(str(paper.get("title") or ""))
        semantic_topics = direction_lexicon.canonicalize_direction_terms(
            existing_topics + title_topics,
            keep_unknown=True,
        )

        source_categories = _normalize_string_values(paper.get("categories"))
        if paper.get("source") == "openreview":
            source_categories.append(str(paper.get("venue") or "conference"))
        elif paper.get("source") == "journal":
            source_categories.append(str(paper.get("journal") or paper.get("venue") or "journal"))

        paper["topics"] = list(dict.fromkeys(semantic_topics))
        paper["keywords"] = daily_push_agent.dedupe_preserve_order(
            _normalize_string_values(paper.get("keywords")) + source_categories + paper["topics"]
        )
        paper["direction_terms"] = daily_push_agent.expand_direction_terms(paper["topics"])


def _build_user_ranking_papers(papers: List[Dict[str, Any]], user_profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create per-user paper copies with profile-relevant topic hints."""
    ranking_papers: List[Dict[str, Any]] = []
    profile_topics = _collect_profile_match_topics(user_profile)
    for paper in papers:
        ranking_paper = copy.deepcopy(paper)
        matched_topics = [
            topic for topic in profile_topics
            if _paper_matches_topic(ranking_paper, topic)
        ]
        if matched_topics:
            merged_topics = direction_lexicon.canonicalize_direction_terms(
                list(ranking_paper.get("topics", []) or []) + matched_topics,
                keep_unknown=True,
            )
            ranking_paper["topics"] = list(dict.fromkeys(merged_topics))
            ranking_paper["keywords"] = daily_push_agent.dedupe_preserve_order(
                _normalize_string_values(ranking_paper.get("keywords")) + ranking_paper["topics"]
            )
            ranking_paper["direction_terms"] = daily_push_agent.expand_direction_terms(ranking_paper["topics"])
        ranking_papers.append(ranking_paper)
    return ranking_papers


def _ranking_profile(user_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Use the real scorer with simulation drift-strength settings."""
    profile = copy.deepcopy(user_profile)
    drift_state = profile.setdefault("drift_state", {})
    drift_state.setdefault("strategy_mode", "simulation")
    return profile


def _score_daily_push_candidate_pool(
    papers: List[Dict[str, Any]],
    user_profile: Dict[str, Any],
    weights: Dict[str, Any],
) -> List[Any]:
    scored = []
    for paper in papers:
        score = daily_push_agent.calculate_paper_score(paper, user_profile, weights)
        relevance_signal = daily_push_agent.compute_relevance_signal(paper, user_profile)
        drift_bonus, drift_topics = daily_push_agent.compute_drift_bonus(paper, user_profile, weights)
        reading_signal_bonus, reading_signal_topics = daily_push_agent.compute_reading_signal_bonus(paper, user_profile, weights)
        score = min(1.0, score + drift_bonus + reading_signal_bonus)
        category = daily_push_agent.categorize_paper(score, paper, user_profile, weights)
        scored.append(
            daily_push_agent.PaperWithScore(
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
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def _paper_with_real_score_to_candidate(item: Any, *, ranking_fallback: bool = False) -> Dict[str, Any]:
    candidate = copy.deepcopy(item.paper)
    candidate["relevance_level"] = item.category
    candidate["relevance_score"] = round(float(item.score or 0.0), 4)
    candidate["relevance_signal"] = round(float(getattr(item, "relevance_signal", 0.0) or 0.0), 4)
    candidate["drift_bonus"] = round(float(getattr(item, "drift_bonus", 0.0) or 0.0), 4)
    candidate["drift_topics"] = list(getattr(item, "drift_topics", None) or [])
    candidate["reading_signal_bonus"] = round(float(getattr(item, "reading_signal_bonus", 0.0) or 0.0), 4)
    candidate["reading_signal_topics"] = list(getattr(item, "reading_signal_topics", None) or [])
    candidate["ranking_source"] = "daily_push_agent.sort_and_categorize"
    candidate["ranking_fallback"] = bool(ranking_fallback)
    return candidate


def _extract_paper_author_names(paper: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for author in paper.get("authors") or []:
        if isinstance(author, dict):
            value = author.get("name") or author.get("display_name") or author.get("author")
        else:
            value = author
        text = str(value or "").strip().lower()
        if text:
            names.append(text)
    return names


def _extract_paper_institutions(paper: Dict[str, Any]) -> List[str]:
    institutions: List[str] = []
    for raw in paper.get("institutions") or []:
        text = str(raw or "").strip().lower()
        if text:
            institutions.append(text)
    return institutions


def _deterministic_noise(*parts: Any, scale: float = 0.03) -> float:
    seed_text = "::".join(str(part or "") for part in parts)
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    fraction = int(digest[:8], 16) / 0xFFFFFFFF
    return (fraction * 2.0 - 1.0) * scale


def _deterministic_unit_interval(*parts: Any) -> float:
    seed_text = "::".join(str(part or "") for part in parts)
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _sample_daily_reading_availability(user_id: Optional[str], date_str: Optional[str]) -> Dict[str, Any]:
    """Pseudo-random but reproducible daily reading capacity for a user-day."""
    day_roll = _deterministic_unit_interval(user_id, date_str, "daily_availability")
    capacity_roll = _deterministic_unit_interval(user_id, date_str, "reading_capacity")

    if day_roll < 0.20:
        capacity = 0 if capacity_roll < 0.45 else 1
        return {"availability_type": "busy", "reading_capacity": capacity, "min_reads": 0}
    if day_roll < 0.80:
        capacity = 2 + min(2, int(capacity_roll * 3))
        return {"availability_type": "normal", "reading_capacity": capacity, "min_reads": min(2, capacity)}

    capacity = 5 + min(1, int(capacity_roll * 2))
    return {"availability_type": "light", "reading_capacity": capacity, "min_reads": min(3, capacity)}


def _ensure_simulation_oracle_state(user_profile: Dict[str, Any]) -> Dict[str, Any]:
    state = user_profile.get("simulation_oracle_state")
    if isinstance(state, dict) and state.get("base_core_directions") is not None:
        return state

    state = {
        "base_core_directions": copy.deepcopy(user_profile.get("core_directions", {}) or {}),
        "base_secondary_topics": list(user_profile.get("secondary_topics", []) or []),
        "base_must_read": copy.deepcopy(user_profile.get("must_read", {}) or {}),
    }
    user_profile["simulation_oracle_state"] = state
    return state


def _compute_oracle_signals(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    oracle_state = _ensure_simulation_oracle_state(user_profile)
    paper_text = _paper_text_blob(paper)
    paper_authors = _extract_paper_author_names(paper)
    paper_institutions = _extract_paper_institutions(paper)
    drift_state = user_profile.get("drift_state", {}) or {}
    anchor_behavior = _get_anchor_behavior(user_profile)

    matched_core_topics: List[str] = []
    core_match = 0.0
    for topic, weight in (oracle_state.get("base_core_directions", {}) or {}).items():
        if _paper_matches_topic(paper, topic):
            matched_core_topics.append(str(topic))
            core_match = max(core_match, float(weight or 0.0))

    secondary_match = 0.0
    matched_secondary_topics: List[str] = []
    for topic in oracle_state.get("base_secondary_topics", []) or []:
        if _paper_matches_topic(paper, topic):
            matched_secondary_topics.append(str(topic))
            secondary_match = max(secondary_match, 0.45)

    anchor_topic = str(anchor_behavior.get("target_topic") or "").strip()
    anchor_match = bool(anchor_topic and _paper_matches_topic(paper, anchor_topic))
    anchor_signal = 0.0
    if anchor_match:
        status = str(drift_state.get("status") or "stable")
        if status == "observing":
            anchor_signal = 0.24
        elif status in {"shifting", "recovered"}:
            anchor_signal = 0.36
        elif drift_state.get("drift_enabled"):
            anchor_signal = 0.18

    must_read_cfg = oracle_state.get("base_must_read", {}) or {}
    author_signal = 0.0
    for author in must_read_cfg.get("authors", []) or []:
        lowered = str(author or "").strip().lower()
        if lowered and any(lowered in paper_author for paper_author in paper_authors):
            author_signal = 0.18
            break

    institution_signal = 0.0
    for institution in must_read_cfg.get("institutions", []) or []:
        lowered = str(institution or "").strip().lower()
        if lowered and any(lowered in paper_institution for paper_institution in paper_institutions):
            institution_signal = 0.14
            break

    keyword_signal = 0.0
    for keyword in must_read_cfg.get("keywords", []) or []:
        lowered = str(keyword or "").strip().lower()
        if lowered and lowered in paper_text:
            keyword_signal = 0.12
            break

    suppressed_topics = anchor_behavior.get("suppressed_topics", []) or []
    suppressed_hit = any(_paper_matches_topic(paper, topic) for topic in suppressed_topics)
    suppressed_penalty = 0.0
    if suppressed_hit and not anchor_match:
        suppressed_penalty = 0.18

    decayed_penalty = 0.0
    for topic, stale_score in (anchor_behavior.get("decayed_topics", {}) or {}).items():
        if _paper_matches_topic(paper, topic):
            decayed_penalty = max(decayed_penalty, min(0.14, float(stale_score or 0.0) * 0.14))

    noise = _deterministic_noise(user_id, date_str, _paper_identity(paper), "oracle", scale=0.025)
    oracle_score = (
        0.58 * core_match
        + secondary_match
        + anchor_signal
        + author_signal
        + institution_signal
        + keyword_signal
        - suppressed_penalty
        - decayed_penalty
        + noise
    )
    oracle_score = round(max(0.0, min(1.0, oracle_score)), 4)

    if oracle_score >= 0.72:
        oracle_label = "strong_relevant"
    elif oracle_score >= 0.48:
        oracle_label = "relevant"
    elif oracle_score >= 0.25:
        oracle_label = "weak_relevant"
    else:
        oracle_label = "irrelevant"

    matched_topics = list(dict.fromkeys(matched_core_topics + matched_secondary_topics))
    if anchor_match and anchor_topic and anchor_topic not in matched_topics:
        matched_topics.append(anchor_topic)

    return {
        "oracle_score": oracle_score,
        "oracle_label": oracle_label,
        "oracle_anchor_match": anchor_match,
        "oracle_core_match": round(core_match, 4),
        "oracle_secondary_match": round(secondary_match, 4),
        "oracle_author_signal": round(author_signal, 4),
        "oracle_keyword_signal": round(keyword_signal, 4),
        "oracle_institution_signal": round(institution_signal, 4),
        "oracle_suppressed_hit": suppressed_hit,
        "oracle_suppressed_penalty": round(suppressed_penalty, 4),
        "oracle_decayed_penalty": round(decayed_penalty, 4),
        "oracle_matched_topics": matched_topics,
    }


def _compute_selection_probability(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> float:
    base_probs = {
        "strong_relevant": 0.72,
        "relevant": 0.50,
        "weak_relevant": 0.24,
        "irrelevant": 0.06,
    }
    base_prob = base_probs.get(str(paper.get("oracle_label") or "irrelevant"), 0.06)

    rank = int(paper.get("system_rank") or 999)
    rank_bias = 0.12 if rank <= 3 else 0.06 if rank <= 10 else 0.0

    level = str(paper.get("relevance_level") or "edge_relevant")
    level_bias = {
        "must_read": 0.18,
        "high_relevant": 0.10,
        "maybe_interested": 0.02,
        "edge_relevant": -0.02,
    }.get(level, 0.0)

    drift_state = user_profile.get("drift_state", {}) or {}
    status = str(drift_state.get("status") or "stable")
    anchor_bias = 0.0
    if paper.get("oracle_anchor_match"):
        if status == "observing":
            anchor_bias = 0.20
        elif status in {"shifting", "recovered"}:
            anchor_bias = 0.28
        elif drift_state.get("drift_enabled"):
            anchor_bias = 0.10

    diversity_penalty = 0.0
    recent_topics: List[str] = []
    for item in (user_profile.get("reading_history", []) or [])[-8:]:
        recent_topics.extend(str(topic or "").strip() for topic in (item.get("topics", []) or []))
    matched_topics = [str(topic or "").strip() for topic in (paper.get("oracle_matched_topics", []) or []) if str(topic or "").strip()]
    if recent_topics and matched_topics:
        repeated_hits = sum(1 for topic in matched_topics if topic in recent_topics)
        if repeated_hits >= 2:
            diversity_penalty = 0.08

    suppression_penalty = 0.10 if paper.get("oracle_suppressed_hit") and not paper.get("oracle_anchor_match") else 0.0
    noise = _deterministic_noise(user_id, date_str, _paper_identity(paper), "select", scale=0.02)

    probability = base_prob + rank_bias + level_bias + anchor_bias - diversity_penalty - suppression_penalty + noise
    return round(max(0.02, min(0.98, probability)), 4)


def _annotate_episode_papers(
    papers: List[Dict[str, Any]],
    user_profile: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for paper in papers:
        enriched = copy.deepcopy(paper)
        enriched.update(
            _compute_oracle_signals(
                enriched,
                user_profile,
                user_id=user_id,
                date_str=date_str,
            )
        )
        enriched["select_probability"] = _compute_selection_probability(
            enriched,
            user_profile,
            user_id=user_id,
            date_str=date_str,
        )
        annotated.append(enriched)
    return annotated


def _count_oracle_labels(papers: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        "strong_relevant": 0,
        "relevant": 0,
        "weak_relevant": 0,
        "irrelevant": 0,
    }
    for paper in papers:
        label = str(paper.get("oracle_label") or "irrelevant")
        counts[label] = counts.get(label, 0) + 1
    return counts


def select_papers_for_user(papers: List[Dict], user: Dict) -> List[Dict]:
    """为单个用户选择推送论文"""
    user_profile = user.get("profile", {})
    anchor_behavior = _get_anchor_behavior(user_profile)

    must_read = []
    high_relevant = []
    maybe_interested = []
    edge_relevant = []

    for paper in papers:
        level, score = match_paper_to_user(paper, user_profile)
        paper_with_score = {**paper, "relevance_level": level, "relevance_score": score}

        if level == "must_read":
            must_read.append(paper_with_score)
        elif level == "high_relevant":
            high_relevant.append(paper_with_score)
        elif level == "maybe_interested":
            maybe_interested.append(paper_with_score)
        else:
            edge_relevant.append(paper_with_score)

    for lst in [must_read, high_relevant, maybe_interested, edge_relevant]:
        lst.sort(key=lambda x: x["relevance_score"], reverse=True)

    selected = must_read + high_relevant
    remaining_pool = maybe_interested + edge_relevant
    target_size = random.randint(15, 25)
    need_more = max(0, min(target_size - len(selected), len(remaining_pool)))

    if need_more > 0 and anchor_behavior["target_topic"] and anchor_behavior["exploration_quota"] > 0:
        anchor_candidates = [
            paper for paper in remaining_pool
            if _paper_matches_topic(paper, anchor_behavior["target_topic"])
        ]
        anchor_candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
        anchor_pick_count = min(need_more, anchor_behavior["exploration_quota"], len(anchor_candidates))
        if anchor_pick_count > 0:
            picked_anchor_candidates = anchor_candidates[:anchor_pick_count]
            selected.extend(picked_anchor_candidates)
            picked_keys = {
                paper.get("paper_id") if paper.get("paper_id") is not None else paper.get("title")
                for paper in picked_anchor_candidates
            }
            remaining_pool = [
                paper for paper in remaining_pool
                if (paper.get("paper_id") if paper.get("paper_id") is not None else paper.get("title")) not in picked_keys
            ]
            need_more = max(0, min(target_size - len(selected), len(remaining_pool)))

    if need_more > 0:
        selected.extend(random.sample(remaining_pool, need_more))

    return selected


# ==================== 用户反馈模拟 ====================

def simulate_user_feedback(selected_papers: List[Dict], user_profile: Dict) -> List[Dict]:
    """模拟用户选择行为"""
    selected_for_reading = []
    anchor_behavior = _get_anchor_behavior(user_profile)
    drift_status = str((user_profile.get("drift_state", {}) or {}).get("status") or "stable")

    # 必中和高相关必选
    for paper in selected_papers:
        if paper.get("relevance_level") in ["must_read", "high_relevant"]:
            selected_for_reading.append(paper)

    # 其他随机选 2-3 篇
    maybe_and_edge = [p for p in selected_papers if p.get("relevance_level") in ["maybe_interested", "edge_relevant"]]
    if maybe_and_edge:
        extra_count = random.randint(2, 3)
        anchor_candidates = []
        if anchor_behavior["target_topic"]:
            anchor_candidates = [
                paper for paper in maybe_and_edge
                if _paper_matches_topic(paper, anchor_behavior["target_topic"])
            ]
            anchor_candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        preferred_count = 0
        if anchor_candidates:
            if drift_status == "observing":
                preferred_count = len(anchor_candidates)
            else:
                preferred_count = min(extra_count, anchor_behavior["feedback_anchor_quota"], len(anchor_candidates))
        extra_selected = list(anchor_candidates[:preferred_count])

        remaining_needed = extra_count - len(extra_selected)
        if remaining_needed > 0:
            picked_keys = {
                paper.get("paper_id") if paper.get("paper_id") is not None else paper.get("title")
                for paper in extra_selected
            }
            fallback_pool = [
                paper for paper in maybe_and_edge
                if (paper.get("paper_id") if paper.get("paper_id") is not None else paper.get("title")) not in picked_keys
            ]
            if fallback_pool:
                extra_selected.extend(random.sample(fallback_pool, min(remaining_needed, len(fallback_pool))))
        selected_for_reading.extend(extra_selected)

    return selected_for_reading


def prepare_episode_candidates_with_metrics(
    papers: List[Dict[str, Any]],
    user: Dict[str, Any],
    *,
    show_count: int = DEFAULT_SIMULATION_SHOW_COUNT,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    user_profile = user.get("profile", {})
    ranking_profile = _ranking_profile(user_profile)
    weights = _load_real_daily_push_weights()
    ranking_papers = _build_user_ranking_papers(papers, ranking_profile)
    target_show_count = max(1, int(show_count or DEFAULT_SIMULATION_SHOW_COUNT))
    weights["push_target_count"] = target_show_count
    weights["push_max_count"] = target_show_count

    pool_scored_items = _score_daily_push_candidate_pool(ranking_papers, ranking_profile, weights)
    real_shown_scored_items = daily_push_agent.sort_and_categorize(ranking_papers, ranking_profile, weights)
    shown_scored_items = list(real_shown_scored_items[:target_show_count])
    shown_keys = {_paper_identity(item.paper) for item in shown_scored_items}
    if len(shown_scored_items) < target_show_count:
        for item in pool_scored_items:
            paper_key = _paper_identity(item.paper)
            if paper_key in shown_keys:
                continue
            shown_scored_items.append(item)
            shown_keys.add(paper_key)
            if len(shown_scored_items) >= target_show_count:
                break

    shown_positions = {
        _paper_identity(item.paper): idx
        for idx, item in enumerate(shown_scored_items, start=1)
    }
    shown_items_by_key = {
        _paper_identity(item.paper): item
        for item in shown_scored_items
    }
    real_shown_keys = {_paper_identity(item.paper) for item in real_shown_scored_items}

    all_candidates: List[Dict[str, Any]] = []
    for pool_rank, item in enumerate(pool_scored_items, start=1):
        paper_key = _paper_identity(item.paper)
        source_item = shown_items_by_key.get(paper_key, item)
        candidate = _paper_with_real_score_to_candidate(
            source_item,
            ranking_fallback=paper_key in shown_positions and paper_key not in real_shown_keys,
        )
        candidate["pool_rank"] = pool_rank
        candidate["shown"] = paper_key in shown_positions
        candidate["system_rank"] = shown_positions.get(paper_key)
        candidate["show_target_count"] = target_show_count
        all_candidates.append(candidate)

    shown_candidates = [paper for paper in all_candidates if paper.get("shown")]
    shown_candidates.sort(key=lambda item: int(item.get("system_rank") or 999))
    return shown_candidates, all_candidates


def simulate_user_feedback_with_oracle(
    shown_papers: List[Dict[str, Any]],
    user_profile: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not shown_papers:
        return []

    annotated_shown = _annotate_episode_papers(
        shown_papers,
        user_profile,
        user_id=user_id,
        date_str=date_str,
    )

    ordered = sorted(
        annotated_shown,
        key=lambda paper: (
            -float(paper.get("select_probability") or 0.0),
            -float(paper.get("oracle_score") or 0.0),
            int(paper.get("system_rank") or 999),
        ),
    )

    availability = _sample_daily_reading_availability(user_id, date_str)
    target_max = min(len(ordered), int(availability.get("reading_capacity") or 0))
    min_reads = min(target_max, int(availability.get("min_reads") or 0))
    if target_max <= 0:
        return []

    chosen: List[Dict[str, Any]] = []
    chosen_keys: Set[str] = set()
    must_read_decided_keys: Set[str] = set()
    drift_status = str((user_profile.get("drift_state", {}) or {}).get("status") or "stable")

    for paper in ordered:
        if paper.get("relevance_level") != "must_read":
            continue
        must_read_decided_keys.add(_paper_identity(paper))
        if random.random() >= 0.90:
            continue
        key = _paper_identity(paper)
        if key not in chosen_keys:
            chosen.append(paper)
            chosen_keys.add(key)
            if len(chosen) >= target_max:
                break

    if drift_status == "observing":
        for paper in ordered:
            if paper.get("oracle_anchor_match"):
                key = _paper_identity(paper)
                if key not in chosen_keys:
                    chosen.append(paper)
                    chosen_keys.add(key)
                    if len(chosen) >= target_max:
                        break

    if len(chosen) < target_max:
        for paper in ordered:
            key = _paper_identity(paper)
            if key in chosen_keys:
                continue
            if key in must_read_decided_keys:
                continue
            probability = float(paper.get("select_probability") or 0.0)
            if random.random() < probability:
                chosen.append(paper)
                chosen_keys.add(key)
                if len(chosen) >= target_max:
                    break

    if len(chosen) < min_reads:
        for paper in ordered:
            key = _paper_identity(paper)
            if key in chosen_keys:
                continue
            if key in must_read_decided_keys:
                continue
            chosen.append(paper)
            chosen_keys.add(key)
            if len(chosen) >= min_reads:
                break

    if len(chosen) > target_max:
        must_read_chosen = [paper for paper in chosen if paper.get("relevance_level") == "must_read"]
        must_read_keys = {_paper_identity(paper) for paper in must_read_chosen}
        remainder = [
            paper for paper in chosen
            if _paper_identity(paper) not in must_read_keys
        ]
        target_max = max(target_max, len(must_read_chosen))
        chosen = must_read_chosen + sorted(
            remainder,
            key=lambda paper: (
                -float(paper.get("select_probability") or 0.0),
                -float(paper.get("oracle_score") or 0.0),
                int(paper.get("system_rank") or 999),
            ),
        )[: max(0, target_max - len(must_read_chosen))]

    chosen.sort(key=lambda paper: int(paper.get("system_rank") or 999))
    return chosen


def _infer_simulated_history_topics(paper: Dict[str, Any], user_profile: Dict[str, Any]) -> List[str]:
    candidate_topics = list((user_profile.get("core_directions", {}) or {}).keys())
    candidate_topics.extend(list((user_profile.get("drift_plan", {}) or {}).get("shift_topics", []) or []))
    candidate_topics.extend(list((user_profile.get("drift_plan", {}) or {}).get("downweight_topics", []) or []))
    topics = [
        topic for topic in dict.fromkeys(candidate_topics)
        if _paper_matches_topic(paper, topic)
    ]
    return topics


def _append_simulated_reading_history(user_profile: Dict[str, Any], selected_for_reading: List[Dict[str, Any]], date_str: str) -> None:
    history = list(user_profile.get("reading_history", []) or [])
    for paper in selected_for_reading:
        history.append(
            {
                "paper_id": paper.get("paper_id"),
                "title": paper.get("title"),
                "selected_at": date_str,
                "action": "selected",
                "topics": _infer_simulated_history_topics(paper, user_profile),
            }
        )
    user_profile["reading_history"] = history[-200:]




def _estimate_embedding_tokens_for_paper(paper: Dict[str, Any]) -> int:
    text = " ".join(
        part for part in (
            str(paper.get("title") or "").strip(),
            str(paper.get("abstract") or "").strip(),
            str(paper.get("venue") or "").strip(),
        ) if part
    )
    return estimate_tokens(text)


def _estimate_llm_report_tokens(paper: Dict[str, Any], user_profile: Dict[str, Any]) -> Tuple[int, int]:
    abstract = str(paper.get("abstract") or "").strip()
    profile_text = json.dumps(user_profile.get("core_directions", {}), ensure_ascii=False)
    secondary_topics = " ".join(user_profile.get("secondary_topics", []) or [])
    must_read = user_profile.get("must_read", {}) or {}
    must_read_text = " ".join(
        list(must_read.get("authors", []) or [])
        + list(must_read.get("institutions", []) or [])
        + list(must_read.get("keywords", []) or [])
    )
    llm_input = "\n".join(
        part for part in (
            str(paper.get("title") or "").strip(),
            abstract,
            profile_text,
            secondary_topics,
            must_read_text,
        ) if part
    )
    input_tokens = estimate_tokens(llm_input * 2)
    output_tokens = estimate_tokens("精读报告约 2000 字，包含背景、方法、结果、局限和相关性分析。")
    return input_tokens, output_tokens


# ==================== 单日模拟 ====================

def simulate_one_day(
    date: datetime,
    papers: List[Dict],
    new_papers: List[Dict],
    total_papers_count: Optional[int],
    users: List[Dict],
    drift_engine: DriftEngine,
    drift_probability: float,
    output_manager: OutputManager,
    llm_model: str,
    embedding_model: str,
    generated_report_keys: set,
    skip_reading_reports: bool = False,
    show_count: int = DEFAULT_SIMULATION_SHOW_COUNT,
) -> Dict[str, Any]:
    """模拟一天的完整流程"""
    date_str = date.strftime("%Y-%m-%d")

    result = {
        "date": date_str,
        "papers_available": len(papers),
        "total_papers_available": int(total_papers_count if total_papers_count is not None else len(new_papers)),
        "new_papers_collected": len(new_papers),
        "users": len(users),
        "episodes": 0,
        "drift_count": 0,
        "tokens": {"embedding": 0, "llm": 0},
    }

    # 保存论文池
    output_manager.save_paper_pool(
        date_str,
        new_papers,
        len(new_papers),
        total_papers=total_papers_count,
    )

    _prepare_simulation_paper_features(new_papers, date_str=date_str)

    for user in users:
        user_id = user["user_id"]
        user_profile = user["profile"]
        role_name = user_profile.get("role_name", user_id.replace("user_", ""))

        # 1. 选择论文
        selected_papers, candidate_papers = prepare_episode_candidates_with_metrics(
            papers,
            user,
            show_count=show_count,
        )
        if not selected_papers:
            continue
        candidate_papers = _annotate_episode_papers(
            candidate_papers,
            user_profile,
            user_id=user_id,
            date_str=date_str,
        )
        selected_papers = [paper for paper in candidate_papers if paper.get("shown")]
        selected_papers.sort(key=lambda paper: int(paper.get("system_rank") or 999))

        # 2. 用户反馈
        selected_for_reading = simulate_user_feedback_with_oracle(
            selected_papers,
            user_profile,
            user_id=user_id,
            date_str=date_str,
        )
        reading_availability = _sample_daily_reading_availability(user_id, date_str)
        _append_simulated_reading_history(user_profile, selected_for_reading, date_str)

        if not skip_reading_reports:
            for paper in selected_for_reading:
                report_key = make_report_key_for_paper(user_id, paper)
                if not report_key or report_key in generated_report_keys:
                    continue
                enriched_paper = paper
                heuristic_payload: Dict[str, Any] = {}
                llm_payload: Optional[Dict[str, Any]] = None
                report_payload: Dict[str, Any] = {}
                report_content = ""
                pdf_error: Optional[str] = None

                with TOKEN_RECORDER.scope(
                    task_type="embedding_report_evidence",
                    user_id=user_id,
                    date=date_str,
                    extra={
                        "paper_id": paper.get("paper_id"),
                        "title": str(paper.get("title") or "")[:120],
                        "role_name": role_name,
                    },
                ):
                    enriched_paper, parsed_pdf, pdf_error = reading_agent.enrich_paper_for_reading_report(paper)
                    heuristic_payload = reading_agent.build_heuristic_report_payload(
                        enriched_paper,
                        user_profile,
                        parsed_pdf=parsed_pdf,
                        pdf_error=pdf_error,
                    )
                with TOKEN_RECORDER.scope(
                    task_type="llm_report",
                    user_id=user_id,
                    date=date_str,
                    extra={
                        "paper_id": paper.get("paper_id"),
                        "title": str(paper.get("title") or "")[:120],
                        "role_name": role_name,
                    },
                ):
                    llm_payload = reading_agent._synthesize_report_with_llm(
                        enriched_paper,
                        user_profile,
                        parsed_pdf=parsed_pdf,
                        heuristic_payload=heuristic_payload,
                    )
                report_payload = reading_agent._merge_report_payload(heuristic_payload, llm_payload)
                proposed_label = report_payload.get("recommendation_label")
                report_payload["recommendation_label"] = reading_agent.calibrate_recommendation_label(
                    enriched_paper,
                    proposed_label,
                    report_payload.get("analysis_source"),
                )
                report_payload["recommendation_calibration"] = reading_agent.build_recommendation_calibration_metadata(
                    enriched_paper,
                    proposed_label,
                    report_payload.get("recommendation_label"),
                    report_payload.get("analysis_source"),
                )
                report_content = reading_agent.generate_reading_report(
                    enriched_paper,
                    user_profile,
                    report_payload=report_payload,
                )
                output_manager.write_reading_report(
                    {
                        "date": date_str,
                        "episode_id": f"{user_id}::{date_str}",
                        "user_id": user_id,
                        "role_name": role_name,
                        "paper_id": enriched_paper.get("paper_id"),
                        "report_key": report_key,
                        "title": enriched_paper.get("title"),
                        "url": enriched_paper.get("url") or enriched_paper.get("paper_url"),
                        "arxiv_id": enriched_paper.get("arxiv_id"),
                        "doi": enriched_paper.get("doi"),
                        "analysis_source": report_payload.get("analysis_source"),
                        "pdf_error": pdf_error,
                        "report_payload": report_payload,
                        "report_content": report_content,
                    }
                )
                generated_report_keys.add(report_key)

        # 3. Anchor 驱动漂移：先观察稳定新主题，再锁锚点并承诺推进
        drift_event = None
        recovery_event = None
        profile_before = copy.deepcopy(user_profile)
        profile_after_drift = copy.deepcopy(user_profile)

        drifted_profile, drift_event = drift_engine.advance_profile_drift(
            profile=user_profile,
            selected_papers=selected_for_reading,
            date=date_str,
            drift_probability=drift_probability,
            strategy_mode="simulation",
        )
        user["profile"] = drifted_profile
        profile_after_drift = copy.deepcopy(drifted_profile)

        # 3b. 检查是否应该恢复（用户选中高相关论文，降低 drift_score）
        profile_before_recovery = copy.deepcopy(user["profile"])
        if drift_event and drift_event.get("event_type") == "recovery":
            recovery_event = None
        else:
            recovery_event = _check_recovery(user, selected_for_reading, date_str)
        current_profile = user["profile"]
        internal_drift_status = current_profile.get("drift_state", {}).get("status", "stable")
        display_drift_status = to_display_drift_status(internal_drift_status)
        internal_drift_score = float(current_profile.get("drift_state", {}).get("score", 0.0) or 0.0)
        display_drift_score = 0.0 if display_drift_status == "stable" else internal_drift_score

        # 4. 记录画像快照
        profile_record = {
            "date": date_str,
            "user_id": user_id,
            "role_name": role_name,
            "version": user.get("version", "0.1"),
            "profile_json": current_profile,
        }
        output_manager.write_profile(profile_record)

        # 5. 记录 Episode
        pool_category_counts = {}
        for paper in candidate_papers:
            level = paper.get("relevance_level", "edge_relevant")
            pool_category_counts[level] = pool_category_counts.get(level, 0) + 1

        category_counts = {}
        for paper in selected_papers:
            level = paper.get("relevance_level", "edge_relevant")
            category_counts[level] = category_counts.get(level, 0) + 1

        selected_category_counts = {}
        for paper in selected_for_reading:
            level = paper.get("relevance_level", "edge_relevant")
            selected_category_counts[level] = selected_category_counts.get(level, 0) + 1
        pool_oracle_counts = _count_oracle_labels(candidate_papers)
        shown_oracle_counts = _count_oracle_labels(selected_papers)
        selected_oracle_counts = _count_oracle_labels(selected_for_reading)
        selected_keys = {_paper_identity(paper) for paper in selected_for_reading}

        episode_record = {
            "date": date_str,
            "episode_id": f"{user_id}::{date_str}",
            "user_id": user_id,
            "role_name": role_name,
            "push_id": date_str,
            "episode_type": "daily_push",
            "show_target_count": int(show_count or DEFAULT_SIMULATION_SHOW_COUNT),

            # 候选情况
            "pool_papers": len(candidate_papers),
            "shown_papers": len(selected_papers),
            "candidate_papers": len(selected_papers),  # Backward-compatible alias for shown_papers.
            "pool_must_read": pool_category_counts.get("must_read", 0),
            "pool_high_relevant": pool_category_counts.get("high_relevant", 0),
            "pool_maybe_interested": pool_category_counts.get("maybe_interested", 0),
            "pool_edge_relevant": pool_category_counts.get("edge_relevant", 0),
            "shown_must_read": category_counts.get("must_read", 0),
            "shown_high_relevant": category_counts.get("high_relevant", 0),
            "shown_maybe_interested": category_counts.get("maybe_interested", 0),
            "shown_edge_relevant": category_counts.get("edge_relevant", 0),
            "candidate_must_read": category_counts.get("must_read", 0),
            "candidate_high_relevant": category_counts.get("high_relevant", 0),
            "candidate_maybe_interested": category_counts.get("maybe_interested", 0),
            "candidate_edge_relevant": category_counts.get("edge_relevant", 0),

            # 用户选择
            "selected_papers": len(selected_for_reading),
            "selected_must_read": selected_category_counts.get("must_read", 0),
            "selected_high_relevant": selected_category_counts.get("high_relevant", 0),
            "selected_maybe_interested": selected_category_counts.get("maybe_interested", 0),
            "selected_edge_relevant": selected_category_counts.get("edge_relevant", 0),
            "skipped_papers": len(selected_papers) - len(selected_for_reading),
            "daily_availability_type": reading_availability.get("availability_type"),
            "daily_reading_capacity": reading_availability.get("reading_capacity"),
            "daily_min_reads": reading_availability.get("min_reads"),
            "pool_oracle_strong_relevant": pool_oracle_counts.get("strong_relevant", 0),
            "pool_oracle_relevant": pool_oracle_counts.get("relevant", 0),
            "pool_oracle_weak_relevant": pool_oracle_counts.get("weak_relevant", 0),
            "pool_oracle_irrelevant": pool_oracle_counts.get("irrelevant", 0),
            "shown_oracle_strong_relevant": shown_oracle_counts.get("strong_relevant", 0),
            "shown_oracle_relevant": shown_oracle_counts.get("relevant", 0),
            "shown_oracle_weak_relevant": shown_oracle_counts.get("weak_relevant", 0),
            "shown_oracle_irrelevant": shown_oracle_counts.get("irrelevant", 0),
            "candidate_oracle_strong_relevant": shown_oracle_counts.get("strong_relevant", 0),
            "candidate_oracle_relevant": shown_oracle_counts.get("relevant", 0),
            "candidate_oracle_weak_relevant": shown_oracle_counts.get("weak_relevant", 0),
            "selected_oracle_strong_relevant": selected_oracle_counts.get("strong_relevant", 0),
            "selected_oracle_relevant": selected_oracle_counts.get("relevant", 0),
            "selected_oracle_weak_relevant": selected_oracle_counts.get("weak_relevant", 0),

            # 画像更新
            "drift_detected": drift_event is not None,
            "drift_status": display_drift_status,
            "drift_score": round(display_drift_score, 2),
            "drift_status_internal": internal_drift_status,
            "drift_score_internal": round(internal_drift_score, 2),

            # 选中的论文
            "selected_paper_ids": [p["paper_id"] for p in selected_for_reading],
            "selected_paper_titles": [p["title"] for p in selected_for_reading],
        }
        output_manager.write_episode(episode_record)
        for paper in candidate_papers:
            output_manager.write_episode_paper(
                {
                    "date": date_str,
                    "episode_id": f"{user_id}::{date_str}",
                    "user_id": user_id,
                    "role_name": role_name,
                    "paper_id": paper.get("paper_id"),
                    "title": paper.get("title"),
                    "abstract": paper.get("abstract"),
                    "authors": paper.get("authors"),
                    "source": paper.get("source"),
                    "url": paper.get("url"),
                    "shown": bool(paper.get("shown")),
                    "selected": _paper_identity(paper) in selected_keys,
                    "pool_rank": paper.get("pool_rank"),
                    "system_rank": paper.get("system_rank"),
                    "system_score": paper.get("relevance_score", 0.0),
                    "system_label": paper.get("relevance_level", "edge_relevant"),
                    "relevance_signal": paper.get("relevance_signal", 0.0),
                    "drift_bonus": paper.get("drift_bonus", 0.0),
                    "drift_topics": paper.get("drift_topics", []),
                    "reading_signal_bonus": paper.get("reading_signal_bonus", 0.0),
                    "reading_signal_topics": paper.get("reading_signal_topics", []),
                    "ranking_source": paper.get("ranking_source", "daily_push_agent.sort_and_categorize"),
                    "ranking_fallback": bool(paper.get("ranking_fallback")),
                    "show_target_count": paper.get("show_target_count"),
                    "oracle_score": paper.get("oracle_score", 0.0),
                    "oracle_label": paper.get("oracle_label", "irrelevant"),
                    "select_probability": paper.get("select_probability", 0.0),
                    "oracle_anchor_match": bool(paper.get("oracle_anchor_match")),
                    "oracle_suppressed_hit": bool(paper.get("oracle_suppressed_hit")),
                    "oracle_matched_topics": paper.get("oracle_matched_topics", []),
                }
            )

        # 6. 记录漂移事件
        if drift_event:
            full_drift_event = create_drift_event(
                user_id=user_id,
                date=date_str,
                drift_event=drift_event,
                profile_before=profile_before,
                profile_after=profile_after_drift,
            )
            output_manager.write_drift_event(full_drift_event)
            if drift_event.get("event_type") == "drift":
                result["drift_count"] += 1

        if recovery_event:
            full_recovery_event = create_drift_event(
                user_id=user_id,
                date=date_str,
                drift_event=recovery_event,
                profile_before=profile_before_recovery,
                profile_after=current_profile,
            )
            output_manager.write_drift_event(full_recovery_event)

        result["episodes"] += 1

    result["tokens"] = TOKEN_RECORDER.totals_for_date(date_str)

    #  flush token logs at end of day
    TOKEN_RECORDER.flush_logs()

    return result


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description="Simulate Historical Episodes with Interest Drift")
    parser.add_argument("--start-date", type=str, required=True, help="开始日期 YYYYMMDD")
    parser.add_argument("--end-date", type=str, required=True, help="结束日期 YYYYMMDD")
    parser.add_argument(
        "--llm-model",
        type=str,
        default=os.environ.get("LLM_PARSER_OPENAI_MODEL", "gemini-3-flash-preview"),
        help="LLM model label used in benchmark summaries",
    )
    parser.add_argument("--embedding-model", type=str, default="Qwen/Qwen3-Embedding-8B", help="Embedding 模型")
    parser.add_argument("--drift-probability", type=float, default=0.5, help="漂移触发概率 (0-1)")
    parser.add_argument("--sources", nargs="*", default=None, help="每天收集的论文源 (arxiv, openreview, journal)")
    parser.add_argument("--limit-per-source", type=int, default=None, help="每天每个源的可选上限")
    parser.add_argument("--skip-paper-collection", action="store_true", help="跳过每日论文收集，只使用数据库已有论文池")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--skip-reading-reports", action="store_true", help="Skip reading report generation for recommendation-only simulation")
    parser.add_argument("--show-count", type=int, default=DEFAULT_SIMULATION_SHOW_COUNT, help="Displayed papers per episode after real-ranking fallback fill")
    parser.add_argument("--user-count", type=int, default=None, help="Run only the first N users after stable user-id sorting")
    parser.add_argument("--user-ids", nargs="*", default=None, help="Run only these explicit user ids, e.g. user_role1 user_role9 user_role24")
    args = parser.parse_args()

    random.seed(args.seed)
    embedding_module._default_service = None
    if hasattr(reading_agent, "READING_REPORT_EVIDENCE_CACHE_ENABLED"):
        reading_agent.READING_REPORT_EVIDENCE_CACHE_ENABLED = False
    _patch_real_usage_logging()

    start_date = datetime.strptime(args.start_date, "%Y%m%d")
    end_date = datetime.strptime(args.end_date, "%Y%m%d")

    print(f"Simulating from {start_date.date()} to {end_date.date()}")
    print(f"Drift probability: {args.drift_probability}")
    print()

    # 初始化
    conn = sqlite3.connect(DB_PATH)
    users = get_all_users(conn)
    papers = get_all_papers(conn)
    conn.close()
    users = select_users(users, user_ids=args.user_ids, user_count=args.user_count)

    print(f"Loaded {len(users)} users, {len(papers)} papers")
    print(f"Selected users: {', '.join(str(user.get('user_id')) for user in users)}")

    # 加载漂移 checkfile
    checkfiles = load_checkfiles(DRIFT_CHECKFILES_DIR)
    print(f"Loaded {len(checkfiles)} drift checkfiles")

    drift_engine = DriftEngine(checkfiles)

    # 输出管理器
    output_dir = Path(args.output_dir) if args.output_dir else (PROJECT_ROOT / "data" / "simulation_output")
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    resume_state = load_resume_state(output_dir, start_date)
    if resume_state["resume"]:
        print(f"Resuming from {resume_state['previous_day']} using {output_dir}")
        users = apply_resumed_profiles(users, resume_state["profiles_by_user"])
    else:
        clear_simulation_output_files(output_dir)

    output_manager = OutputManager(str(output_dir))

    roles_meta = load_roles_meta()

    # 保存用户元数据
    user_metadata = resume_state.get("user_metadata") or []
    if not user_metadata:
        user_metadata = []
        for user in users:
            profile = user["profile"]
            role_name = user["user_id"].replace("user_", "")
            role_info = roles_meta.get(role_name, {})
            user_metadata.append({
                "user_id": user["user_id"],
                "role_name": role_name,
                "description": role_info.get("description", profile.get("description", "")),
                "seed_directions": profile.get("core_directions", {}),
                "created_at": start_date.strftime("%Y-%m-%d"),
            })
    output_manager.save_user_metadata(user_metadata)

    # 按天模拟
    all_results = []
    current_date = start_date
    generated_report_keys: set[str] = set(resume_state["generated_report_keys"])

    while current_date <= end_date:
        newly_collected = 0
        if not args.skip_paper_collection:
            print(f"[{current_date.date()}] Collecting papers for this day...")
            newly_collected = collect_papers_for_day(
                current_date,
                sources=args.sources,
                limit_per_source=args.limit_per_source,
            )

        conn = sqlite3.connect(DB_PATH)
        day_new_papers = get_papers_by_date(conn, current_date)
        day_papers = get_papers_up_to_date(conn, current_date)
        conn.close()

        if not day_new_papers:
            print(f"[{current_date.date()}] No new papers collected for this day, skipping...")
            output_manager.save_paper_pool(
                current_date.strftime("%Y-%m-%d"),
                [],
                new_papers_count=0,
                total_papers=len(day_papers),
            )
            all_results.append(
                {
                    "episodes": 0,
                    "drift_count": 0,
                    "new_papers_collected": 0,
                    "tokens": {"embedding": 0, "llm": 0},
                }
            )
            current_date += timedelta(days=1)
            continue

        print(
            f"[{current_date.date()}] Simulating with {len(day_new_papers)} today's papers "
            f"(cumulative total: {len(day_papers)}, new today: {newly_collected})..."
        )

        result = simulate_one_day(
            date=current_date,
            papers=day_new_papers,
            new_papers=day_new_papers,
            total_papers_count=len(day_papers),
            users=users,
            drift_engine=drift_engine,
            drift_probability=args.drift_probability,
            output_manager=output_manager,
            llm_model=args.llm_model,
            embedding_model=args.embedding_model,
            generated_report_keys=generated_report_keys,
            skip_reading_reports=bool(args.skip_reading_reports),
            show_count=args.show_count,
        )
        result["collector_reported_new_papers"] = newly_collected
        result["new_papers_collected"] = len(day_new_papers)
        all_results.append(result)
        print(
            f"  Episodes: {result['episodes']}, Drifts: {result['drift_count']}, Today's papers: {result['new_papers_collected']}, "
            f"Embedding tokens: {result['tokens']['embedding']}, LLM tokens: {result['tokens']['llm']}"
        )

        current_date += timedelta(days=1)

    output_manager.close()

    # 汇总
    summary = merge_summary_with_previous(
        resume_state["existing_summary"],
        current_start=args.start_date,
        current_end=args.end_date,
        added_days=len(all_results),
        added_new_papers=sum(r.get("new_papers_collected", 0) for r in all_results),
        added_embedding_tokens=sum(r.get("tokens", {}).get("embedding", 0) for r in all_results),
        added_llm_tokens=sum(r.get("tokens", {}).get("llm", 0) for r in all_results),
        added_drifts=sum(r["drift_count"] for r in all_results),
        added_episodes=sum(r["episodes"] for r in all_results),
        output_dir=output_dir,
        drift_probability=args.drift_probability,
        sources=args.sources,
        limit_per_source=args.limit_per_source,
        skip_collection=bool(args.skip_paper_collection),
        extra_fields={
            "skip_reading_reports": bool(args.skip_reading_reports),
            "show_count": int(args.show_count or DEFAULT_SIMULATION_SHOW_COUNT),
            "sampled_users": [str(user.get("user_id")) for user in users],
            "user_count": len(users),
            "token_usage": {
                "embedding_model": args.embedding_model,
                "llm_model": args.llm_model,
                "embedding_tokens": int(((resume_state["existing_summary"] or {}).get("token_usage", {}) or {}).get("embedding_tokens", 0) or 0)
                + sum(r.get("tokens", {}).get("embedding", 0) for r in all_results),
                "llm_tokens": int(((resume_state["existing_summary"] or {}).get("token_usage", {}) or {}).get("llm_tokens", 0) or 0)
                + sum(r.get("tokens", {}).get("llm", 0) for r in all_results),
                "total_tokens": int(((resume_state["existing_summary"] or {}).get("token_usage", {}) or {}).get("total_tokens", 0) or 0)
                + sum(r.get("tokens", {}).get("embedding", 0) + r.get("tokens", {}).get("llm", 0) for r in all_results),
            }
        },
    )

    summary_path = Path(output_dir) / "simulation_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print("Simulation Complete")
    print("=" * 60)
    print(f"Days: {len(all_results)}")
    print(f"Total Episodes: {summary['total_episodes']}")
    print(f"Total Drifts: {summary['total_drifts']}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    import copy
    main()
