#!/usr/bin/env python3
"""
Measure one-day dataset collection token usage with real embedding / LLM calls.

Pipeline for a given date:
1. Collect all papers available on that date from supported sources
2. Prepare paper embeddings once for the shared paper pool
3. For each user profile, run daily-push ranking
4. Simulate user selection:
   - include all must_read
   - include all high_relevant
   - include top 2 maybe_interested
   - include top 1 edge_relevant
5. For selected papers, build heuristic reading payloads and synthesize LLM reports
6. Report embedding / llm token usage tables

The script avoids mutating the main database tables. It only reads profiles and
external sources, and writes measurement artifacts to data/token_measurements/.
"""

from __future__ import annotations

import argparse
import copy
import csv
import importlib
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

daily_push_agent = importlib.import_module("deployments.feishu.daily-push-agent.main")
reading_agent = importlib.import_module("agents.reading-agent.main")
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
embedding_module = importlib.import_module("skills.embedding.scripts.embed")
llm_parser = importlib.import_module("agents.master-coordinator.scripts.llm_parser")
arxiv_fetcher = importlib.import_module("skills.arxiv-fetcher.scripts.fetch_arxiv")
openreview_fetcher = importlib.import_module("skills.openreview-fetcher.scripts.fetch_openreview")
journal_fetcher = importlib.import_module("skills.journal-fetcher.scripts.fetch_journal")


MEASUREMENT_ROOT = PROJECT_ROOT / "data" / "token_measurements"


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


@dataclass
class TokenTracker:
    current_stage: str = "unscoped"
    embedding_prompt_tokens: int = 0
    embedding_total_tokens: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_total_tokens: int = 0
    embedding_requests: int = 0
    llm_requests: int = 0
    rows: List[Dict[str, Any]] = field(default_factory=list)

    @contextmanager
    def stage(self, name: str):
        previous = self.current_stage
        self.current_stage = name
        try:
            yield
        finally:
            self.current_stage = previous

    def record_embedding(
        self,
        *,
        model: str,
        input_count: int,
        usage: Dict[str, int],
        provider: str,
    ) -> None:
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or prompt_tokens)
        self.embedding_requests += 1
        self.embedding_prompt_tokens += prompt_tokens
        self.embedding_total_tokens += total_tokens
        self.rows.append(
            {
                "kind": "embedding",
                "stage": self.current_stage,
                "provider": provider,
                "model": model,
                "input_count": input_count,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "total_tokens": total_tokens,
            }
        )

    def record_llm(
        self,
        *,
        model: str,
        usage: Dict[str, int],
        provider: str,
    ) -> None:
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        self.llm_requests += 1
        self.llm_prompt_tokens += prompt_tokens
        self.llm_completion_tokens += completion_tokens
        self.llm_total_tokens += total_tokens
        self.rows.append(
            {
                "kind": "llm",
                "stage": self.current_stage,
                "provider": provider,
                "model": model,
                "input_count": 1,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        )


def _patch_token_usage(tracker: TokenTracker):
    original_init = embedding_module.EmbeddingService.__init__
    original_get_openai_client = llm_parser._get_openai_client

    def patched_embedding_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if getattr(self, "provider", None) == "openai" and getattr(self, "client", None) is not None:
            original_create = self.client.embeddings.create
            if not getattr(original_create, "_paperflow_token_wrapped", False):
                def wrapped_create(*create_args, **create_kwargs):
                    response = original_create(*create_args, **create_kwargs)
                    usage = _extract_usage_dict(getattr(response, "usage", None))
                    inputs = create_kwargs.get("input")
                    if isinstance(inputs, list):
                        input_count = len(inputs)
                    else:
                        input_count = 1
                    tracker.record_embedding(
                        model=str(create_kwargs.get("model") or getattr(self, "model", "")),
                        input_count=input_count,
                        usage=usage,
                        provider="openai",
                    )
                    return response

                wrapped_create._paperflow_token_wrapped = True  # type: ignore[attr-defined]
                self.client.embeddings.create = wrapped_create

    def patched_get_openai_client(timeout_override: Optional[float] = None):
        client = original_get_openai_client(timeout_override=timeout_override)
        if client is None:
            return None

        original_chat_create = client.chat.completions.create
        if not getattr(original_chat_create, "_paperflow_token_wrapped", False):
            def wrapped_chat_create(*create_args, **create_kwargs):
                response = original_chat_create(*create_args, **create_kwargs)
                usage = _extract_usage_dict(getattr(response, "usage", None))
                tracker.record_llm(
                    model=str(create_kwargs.get("model") or ""),
                    usage=usage,
                    provider="openai",
                )
                return response

            wrapped_chat_create._paperflow_token_wrapped = True  # type: ignore[attr-defined]
            client.chat.completions.create = wrapped_chat_create
        return client

    embedding_module.EmbeddingService.__init__ = patched_embedding_init
    llm_parser._get_openai_client = patched_get_openai_client

    return original_init, original_get_openai_client


def _unpatch_token_usage(original_init, original_get_openai_client):
    embedding_module.EmbeddingService.__init__ = original_init
    llm_parser._get_openai_client = original_get_openai_client


def _reset_embedding_runtime_cache(measurement_dir: Path) -> None:
    cache_dir = measurement_dir / "embedding_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    embedding_module.DEFAULT_CACHE_DIR = cache_dir
    embedding_module._default_service = None
    reading_agent.READING_REPORT_EVIDENCE_CACHE_ENABLED = False


def _load_profiles() -> Dict[str, Dict[str, Any]]:
    conn = db_ops.get_connection()
    rows = conn.execute("SELECT user_id, profile_json FROM profiles ORDER BY user_id").fetchall()
    conn.close()
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        result[str(row["user_id"])] = json.loads(row["profile_json"])
    return result


def _load_roles() -> Dict[str, Dict[str, Any]]:
    payload = json.loads((PROJECT_ROOT / "data" / "roles.json").read_text(encoding="utf-8"))
    return payload.get("roles", {})


def _build_existing_report_cache() -> Dict[str, Dict[str, Any]]:
    """Build a lightweight in-memory cache to simulate reading report reuse."""
    return {}


def _fetch_papers_for_exact_day(day: str) -> List[Dict[str, Any]]:
    ymd = day.replace("-", "")
    arxiv_categories = daily_push_agent.get_default_arxiv_categories()
    conferences = daily_push_agent.load_default_conferences()
    journals = daily_push_agent.load_default_journals()

    papers: List[Dict[str, Any]] = []

    print(f"[Collect] arXiv for {day}")
    for paper in arxiv_fetcher.fetch_by_date(ymd, ymd, categories=arxiv_categories, limit=5000):
        paper["source"] = "arxiv"
        papers.append(paper)

    print(f"[Collect] OpenReview/CVF/ECVA for {day}")
    for paper in openreview_fetcher.fetch_by_date(ymd, ymd, conferences=conferences, limit=5000):
        papers.append(paper)

    print(f"[Collect] Journals for {day}")
    for paper in journal_fetcher.fetch_by_date(ymd, ymd, journals=journals, limit=5000):
        paper["source"] = paper.get("source", "journal")
        papers.append(paper)

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for paper in papers:
        key = (
            str(paper.get("arxiv_id") or "").strip().lower()
            or str(paper.get("doi") or "").strip().lower()
            or str(paper.get("title") or "").strip().lower()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(paper)
    return deduped


def _simulate_selection(
    scored_papers: List[Any],
    *,
    must_count: int = 1,
    high_count: int = 1,
    maybe_count: int = 2,
    edge_count: int = 1,
) -> List[Any]:
    must_items = [paper for paper in scored_papers if paper.category == "must_read"][:must_count]
    high_items = [paper for paper in scored_papers if paper.category == "high_relevant"][:high_count]
    maybe_items = [paper for paper in scored_papers if paper.category == "maybe_interested"][:maybe_count]
    edge_items = [paper for paper in scored_papers if paper.category == "edge_relevant"][:edge_count]

    selected: List[Any] = []
    seen_titles = set()
    for item in must_items + high_items + maybe_items + edge_items:
        title = str(item.paper.get("title") or "").strip().lower()
        if title in seen_titles:
            continue
        seen_titles.add(title)
        selected.append(item)
    return selected


def _source_counts(papers: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for paper in papers:
        source = str(paper.get("source") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _build_summary_tables(
    *,
    target_date: str,
    all_papers: List[Dict[str, Any]],
    tracker: TokenTracker,
    per_user_rows: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    source_counts = _source_counts(all_papers)
    selected_total = sum(int(row["selected_reports"]) for row in per_user_rows)
    generated_total = sum(int(row["generated_reports"]) for row in per_user_rows)
    reused_total = sum(int(row["reused_reports"]) for row in per_user_rows)
    must_total = sum(int(row["must_read_selected"]) for row in per_user_rows)
    high_total = sum(int(row["high_relevant_selected"]) for row in per_user_rows)
    maybe_total = sum(int(row["maybe_interested_selected"]) for row in per_user_rows)
    edge_total = sum(int(row["edge_relevant_selected"]) for row in per_user_rows)

    overview = [
        {
            "date": target_date,
            "paper_pool_total": len(all_papers),
            "source_breakdown": json.dumps(source_counts, ensure_ascii=False),
            "profiles_tested": len(per_user_rows),
            "selected_reports_total": selected_total,
            "generated_reports_total": generated_total,
            "reused_reports_total": reused_total,
            "must_read_selected_total": must_total,
            "high_relevant_selected_total": high_total,
            "maybe_interested_selected_total": maybe_total,
            "edge_relevant_selected_total": edge_total,
        }
    ]

    token_summary = [
        {
            "kind": "embedding",
            "requests": tracker.embedding_requests,
            "prompt_tokens": tracker.embedding_prompt_tokens,
            "completion_tokens": 0,
            "total_tokens": tracker.embedding_total_tokens,
        },
        {
            "kind": "llm",
            "requests": tracker.llm_requests,
            "prompt_tokens": tracker.llm_prompt_tokens,
            "completion_tokens": tracker.llm_completion_tokens,
            "total_tokens": tracker.llm_total_tokens,
        },
    ]

    stage_rows: Dict[str, Dict[str, Any]] = {}
    for row in tracker.rows:
        stage = str(row["stage"])
        bucket = stage_rows.setdefault(
            stage,
            {
                "stage": stage,
                "kind": row["kind"],
                "requests": 0,
                "input_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )
        bucket["requests"] += int(row["kind"] in {"embedding", "llm"})
        bucket["input_count"] += int(row.get("input_count") or 0)
        bucket["prompt_tokens"] += int(row.get("prompt_tokens") or 0)
        bucket["completion_tokens"] += int(row.get("completion_tokens") or 0)
        bucket["total_tokens"] += int(row.get("total_tokens") or 0)

    stage_summary = list(stage_rows.values())

    return {
        "overview": overview,
        "token_summary": token_summary,
        "stage_summary": stage_summary,
        "per_user": per_user_rows,
        "request_details": tracker.rows,
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _to_markdown(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "(empty)\n"
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure real embedding / LLM token usage for one day's dataset pipeline.")
    parser.add_argument("--date", default="2026-03-01", help="Target day in YYYY-MM-DD.")
    parser.add_argument("--must-count", type=int, default=1, help="How many must_read papers to include per user.")
    parser.add_argument("--high-count", type=int, default=1, help="How many high_relevant papers to include per user.")
    parser.add_argument("--maybe-count", type=int, default=2, help="How many maybe_interested papers to include per user.")
    parser.add_argument("--edge-count", type=int, default=1, help="How many edge_relevant papers to include per user.")
    parser.add_argument("--pdf-mode", default=os.environ.get("READING_REPORT_PDF_MODE", "always"), help="Reading report PDF mode: always / smart / off.")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    measurement_dir = MEASUREMENT_ROOT / f"measure_{args.date.replace('-', '')}_{timestamp}"
    measurement_dir.mkdir(parents=True, exist_ok=True)

    tracker = TokenTracker()
    original_init, original_get_client = _patch_token_usage(tracker)
    _reset_embedding_runtime_cache(measurement_dir)
    os.environ["READING_REPORT_PDF_MODE"] = str(args.pdf_mode).strip()

    try:
        papers = _fetch_papers_for_exact_day(args.date)
        print(f"[Collected] {len(papers)} unique papers for {args.date}")

        with tracker.stage("paper_embedding"):
            prepared_papers = daily_push_agent.prepare_paper_features(copy.deepcopy(papers))

        profiles = _load_profiles()
        roles = _load_roles()
        weights = daily_push_agent.load_scoring_weights()
        report_cache = _build_existing_report_cache()

        per_user_rows: List[Dict[str, Any]] = []

        for role_name, role_data in sorted(roles.items(), key=lambda item: item[0]):
            user_id = str(role_data.get("user_id") or "")
            profile = profiles.get(user_id)
            if not profile:
                continue

            scored = daily_push_agent.sort_and_categorize(copy.deepcopy(prepared_papers), profile, weights)
            selected = _simulate_selection(
                scored,
                must_count=args.must_count,
                high_count=args.high_count,
                maybe_count=args.maybe_count,
                edge_count=args.edge_count,
            )

            if not selected:
                per_user_rows.append(
                    {
                        "role_name": role_name,
                        "user_id": user_id,
                        "paper_pool_count": len(scored),
                        "selected_reports": 0,
                        "generated_reports": 0,
                        "reused_reports": 0,
                        "must_read_selected": 0,
                        "high_relevant_selected": 0,
                        "maybe_interested_selected": 0,
                        "edge_relevant_selected": 0,
                    }
                )
                continue

            must_cnt = sum(1 for item in selected if item.category == "must_read")
            high_cnt = sum(1 for item in selected if item.category == "high_relevant")
            maybe_cnt = sum(1 for item in selected if item.category == "maybe_interested")
            edge_cnt = sum(1 for item in selected if item.category == "edge_relevant")

            reused_reports = 0
            generated_reports = 0

            for item in selected:
                cache_key = f"{user_id}::{str(item.paper.get('doi') or item.paper.get('arxiv_id') or item.paper.get('title') or '').strip().lower()}"
                if cache_key in report_cache:
                    reused_reports += 1
                    continue

                with tracker.stage("report_evidence_embedding"):
                    enriched_paper, parsed_pdf, pdf_error = reading_agent.enrich_paper_for_reading_report(item.paper)
                    heuristic_payload = reading_agent.build_heuristic_report_payload(
                        enriched_paper,
                        profile,
                        parsed_pdf=parsed_pdf,
                        pdf_error=pdf_error,
                    )
                with tracker.stage("reading_report_llm"):
                    llm_payload = reading_agent._synthesize_report_with_llm(
                        enriched_paper,
                        profile,
                        parsed_pdf=parsed_pdf,
                        heuristic_payload=heuristic_payload,
                    )
                report_cache[cache_key] = {
                    "paper_title": enriched_paper.get("title"),
                    "heuristic_payload": heuristic_payload,
                    "llm_payload": llm_payload,
                }
                generated_reports += 1

            per_user_rows.append(
                {
                    "role_name": role_name,
                    "user_id": user_id,
                    "paper_pool_count": len(scored),
                    "selected_reports": len(selected),
                    "generated_reports": generated_reports,
                    "reused_reports": reused_reports,
                    "must_read_selected": must_cnt,
                    "high_relevant_selected": high_cnt,
                    "maybe_interested_selected": maybe_cnt,
                    "edge_relevant_selected": edge_cnt,
                }
            )

        tables = _build_summary_tables(
            target_date=args.date,
            all_papers=prepared_papers,
            tracker=tracker,
            per_user_rows=per_user_rows,
        )

        for name, rows in tables.items():
            _write_csv(measurement_dir / f"{name}.csv", rows)

        markdown_parts = [
            f"# Token Usage Measurement ({args.date})",
            "",
            "## Overview",
            _to_markdown(tables["overview"]),
            "## Token Summary",
            _to_markdown(tables["token_summary"]),
            "## Stage Summary",
            _to_markdown(tables["stage_summary"]),
            "## Per User",
            _to_markdown(tables["per_user"]),
        ]
        (measurement_dir / "summary.md").write_text("\n".join(markdown_parts), encoding="utf-8")

        print("\n=== Overview ===")
        print(_to_markdown(tables["overview"]))
        print("=== Token Summary ===")
        print(_to_markdown(tables["token_summary"]))
        print("=== Stage Summary ===")
        print(_to_markdown(tables["stage_summary"]))
        print("=== Per User ===")
        print(_to_markdown(tables["per_user"]))
        print(f"Saved measurement artifacts to: {measurement_dir}")

    finally:
        _unpatch_token_usage(original_init, original_get_client)


if __name__ == "__main__":
    main()
