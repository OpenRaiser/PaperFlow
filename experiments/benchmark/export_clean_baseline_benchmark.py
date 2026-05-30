#!/usr/bin/env python3
"""Export a contamination-safe benchmark package for offline baselines."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


CANDIDATE_FIELDS = (
    "date",
    "episode_id",
    "user_id",
    "role_name",
    "paper_id",
    "title",
    "abstract",
    "authors",
    "source",
    "url",
    "venue",
    "journal",
    "doi",
    "arxiv_id",
    "topics",
    "keywords",
    "institutions",
    "affiliations",
    "cited_by_count",
    "citation_count",
    "citations",
    "influential_citation_count",
    "reference_count",
    "references",
    "reference_ids",
    "cited_references",
    "outbound_citations",
    "citation_ids",
    "cited_by_ids",
    "inbound_citations",
    "openalex_id",
    "semantic_scholar_id",
    "corpus_id",
    "external_ids",
)

LABEL_FIELDS = (
    "date",
    "episode_id",
    "user_id",
    "role_name",
    "paper_id",
    "title",
    "url",
    "doi",
    "arxiv_id",
    "selected",
    "oracle_score",
    "oracle_label",
)

EPISODE_FIELDS = (
    "date",
    "episode_id",
    "user_id",
    "role_name",
    "push_id",
    "episode_type",
    "pool_papers",
    "daily_availability_type",
    "daily_reading_capacity",
    "daily_min_reads",
)

USER_FIELDS = (
    "user_id",
    "role_name",
    "description",
    "seed_directions",
    "initial_topics",
    "created_at",
)

FORBIDDEN_METHOD_FIELDS = (
    "shown",
    "pool_rank",
    "system_rank",
    "system_score",
    "system_label",
    "relevance_signal",
    "drift_bonus",
    "drift_topics",
    "reading_signal_bonus",
    "reading_signal_topics",
    "ranking_source",
    "ranking_fallback",
    "select_probability",
    "show_target_count",
)

FORBIDDEN_USER_FIELDS = (
    "profile",
    "updated_profile",
    "profile_before",
    "profile_after",
    "core_directions",
    "topic_weights",
    "interest_vector",
    "drift_state",
    "report_preferences",
    "version",
    "updated_at",
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_phrase_text(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def paper_identity(row: Dict[str, Any]) -> str:
    for key in ("paper_id", "doi", "arxiv_id", "url"):
        value = str(row.get(key) or "").strip().casefold()
        if value:
            return f"{key}:{value}"
    return "title:" + normalize_phrase_text(row.get("title"))


def project_fields(row: Dict[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
    return {field: row.get(field) for field in fields if field in row}


def export_clean_users(input_dir: Path, output_dir: Path) -> None:
    users_path = input_dir / "users.json"
    if not users_path.exists():
        return
    payload = json.loads(users_path.read_text(encoding="utf-8"))
    users = payload.get("users") if isinstance(payload, dict) else []
    clean_users: List[Dict[str, Any]] = []
    if isinstance(users, list):
        for user in users:
            if isinstance(user, dict):
                clean_users.append(project_fields(user, USER_FIELDS))
    (output_dir / "users.json").write_text(
        json.dumps({"users": clean_users}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_clean_benchmark(input_dir: Path, output_dir: Path) -> Dict[str, Any]:
    episode_papers_path = input_dir / "episode_papers.jsonl"
    episodes_path = input_dir / "episodes.jsonl"
    if not episode_papers_path.exists():
        raise FileNotFoundError(f"Missing episode_papers.jsonl: {episode_papers_path}")
    if not episodes_path.exists():
        raise FileNotFoundError(f"Missing episodes.jsonl: {episodes_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    paper_rows = load_jsonl(episode_papers_path)
    episode_rows = load_jsonl(episodes_path)

    candidates: List[Dict[str, Any]] = []
    labels: List[Dict[str, Any]] = []
    for row in paper_rows:
        candidate = project_fields(row, CANDIDATE_FIELDS)
        candidate["paper_identity"] = paper_identity(row)
        label = project_fields(row, LABEL_FIELDS)
        label["paper_identity"] = candidate["paper_identity"]
        label["selected"] = bool(row.get("selected"))
        label["oracle_score"] = row.get("oracle_score", 0.0)
        label["oracle_label"] = row.get("oracle_label", "irrelevant")
        candidates.append(candidate)
        labels.append(label)

    clean_episodes = [project_fields(row, EPISODE_FIELDS) for row in episode_rows]

    write_jsonl(output_dir / "candidate_pools.jsonl", candidates)
    write_jsonl(output_dir / "labels_for_eval.jsonl", labels)
    write_jsonl(output_dir / "episodes.jsonl", clean_episodes)
    export_clean_users(input_dir, output_dir)

    manifest = {
        "source_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "candidate_file": "candidate_pools.jsonl",
        "label_file": "labels_for_eval.jsonl",
        "episodes_file": "episodes.jsonl",
        "candidate_fields": list(CANDIDATE_FIELDS) + ["paper_identity"],
        "label_fields": list(LABEL_FIELDS) + ["paper_identity"],
        "user_fields": list(USER_FIELDS),
        "forbidden_method_fields_stripped": list(FORBIDDEN_METHOD_FIELDS),
        "forbidden_user_fields_stripped": list(FORBIDDEN_USER_FIELDS),
        "notes": [
            "Baselines must rank using candidate_pools.jsonl only.",
            "labels_for_eval.jsonl is for chronological feedback and post-ranking evaluation only.",
            "oracle_label and oracle_score must never be used for ranking or training.",
            "selected may be used only as historical feedback after a previous day has been ranked.",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "candidate_rows": len(candidates),
        "label_rows": len(labels),
        "episode_rows": len(clean_episodes),
        "output_dir": str(output_dir),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export clean baseline benchmark files.")
    parser.add_argument("--input-dir", required=True, help="Full PaperFlow benchmark output directory.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Clean output directory. Defaults to <input-dir>/baseline_clean_input.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir / "baseline_clean_input"
    result = export_clean_benchmark(input_dir=input_dir, output_dir=output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
