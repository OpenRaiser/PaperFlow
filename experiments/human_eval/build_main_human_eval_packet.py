#!/usr/bin/env python3
"""Build a blind annotation packet for main-experiment human evaluation.

The packet is intentionally split into:
- a blind CSV for annotators, containing only profile/paper content and blank
  human-score columns;
- an internal key CSV, containing method, rank, oracle, selected, and automatic
  metric fields needed for aggregation and correlation analysis.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_BENCHMARK_DIR = Path("data/benchmark_full_24users_20260301_20260419_show20_with_reading")
USEFUL_LABELS = {"strong_relevant", "relevant", "weak_relevant"}
STRICT_LABELS = {"strong_relevant", "relevant"}
ORACLE_GAIN = {
    "strong_relevant": 2.0,
    "relevant": 1.0,
    "weak_relevant": 0.5,
    "irrelevant": 0.0,
}
METHOD_LABELS = {
    "full_paperflow": "Full PaperFlow Pipeline",
    "paperflow_fixed_profile": "PaperFlow Fixed Profile",
    "paperflow_no_drift": "PaperFlow No Drift Ablation",
    "scholar_inbox": "Scholar Inbox Pipeline",
    "nl_profile": "Natural-Language User Profile Recommendation",
    "citation_enhanced": "Citation-Enhanced Literature Recommendation",
    "knowledge_entity": "Knowledge-Entity Enhanced Recommendation",
    "discourse_aware": "Discourse-Aware Content Recommendation",
}


@dataclass
class EpisodeAccumulator:
    method_key: str
    method_name: str
    episode_id: str
    user_id: str = ""
    role_name: str = ""
    date: str = ""
    pool_size: int = 0
    pool_useful: int = 0
    pool_strict: int = 0
    pool_gains: List[float] = field(default_factory=list)
    shown_rows: List[Dict[str, Any]] = field(default_factory=list)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def truncate(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value or "")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def paper_url_from_record(paper: Dict[str, Any]) -> str:
    for key in ("url", "arxiv_url", "paper_url", "pdf_url", "arxiv_pdf_url"):
        value = str(paper.get(key) or "").strip()
        if value:
            return value
    arxiv_id = str(paper.get("arxiv_id") or "").strip()
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    doi = str(paper.get("doi") or "").strip()
    if doi:
        return doi if doi.startswith("http") else f"https://doi.org/{doi}"
    return ""


def load_paper_url_map(benchmark_dir: Path) -> Dict[str, str]:
    paper_pools_path = benchmark_dir / "paper_pools.jsonl"
    if not paper_pools_path.exists():
        return {}
    urls: Dict[str, str] = {}
    for row in iter_jsonl(paper_pools_path):
        for paper in row.get("papers") or []:
            if not isinstance(paper, dict):
                continue
            paper_id = str(paper.get("paper_id") or "").strip()
            url = paper_url_from_record(paper)
            if paper_id and url and paper_id not in urls:
                urls[paper_id] = url
    return urls


def load_users(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    users = payload.get("users", []) if isinstance(payload, dict) else []
    return {str(item.get("user_id")): item for item in users if isinstance(item, dict)}


def profile_text(user: Optional[Dict[str, Any]]) -> str:
    if not user:
        return ""
    directions = user.get("seed_directions")
    if isinstance(directions, dict) and directions:
        direction_text = ", ".join(str(key).replace("-", " ") for key in directions)
        return f"{user.get('description') or ''}; core directions: {direction_text}".strip("; ")
    return str(user.get("description") or "")


def method_paths(benchmark_dir: Path, requested: Sequence[str]) -> List[Tuple[str, str, Path]]:
    if requested:
        result = []
        for spec in requested:
            parts = spec.split("=", 2)
            if len(parts) not in {2, 3}:
                raise SystemExit("--method must use key=path or key=path=display name")
            key, raw_path = parts[0], parts[1]
            label = parts[2] if len(parts) == 3 else METHOD_LABELS.get(key, key)
            path = Path(raw_path)
            if path.is_dir():
                path = path / "episode_papers.jsonl"
            result.append((key, label, path))
        return result

    result: List[Tuple[str, str, Path]] = []
    root_full = benchmark_dir / "episode_papers.jsonl"
    if root_full.exists():
        result.append(("full_paperflow", METHOD_LABELS["full_paperflow"], root_full))
    main_dir = benchmark_dir / "main_experiment"
    for path in sorted(main_dir.glob("*/episode_papers.jsonl")):
        key = path.parent.name
        result.append((key, METHOD_LABELS.get(key, key), path))
    return result


def dcg(gains: Iterable[float]) -> float:
    return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))


def mrr_from_labels(labels: Sequence[str], limit: int = 20) -> float:
    for index, label in enumerate(labels[:limit], start=1):
        if label in USEFUL_LABELS:
            return 1.0 / index
    return 0.0


def compute_episode_metrics(acc: EpisodeAccumulator, lift_cap: float = 15.0) -> Dict[str, float]:
    shown = sorted(acc.shown_rows, key=lambda item: int(item.get("system_rank") or 10**9))
    labels = [str(row.get("oracle_label") or "irrelevant") for row in shown[:20]]
    gains = [ORACLE_GAIN.get(label, 0.0) for label in labels]
    ideal_gains = sorted(acc.pool_gains, reverse=True)[:20]
    idcg = dcg(ideal_gains)
    gndcg20 = dcg(gains) / idcg if idcg > 0 else 0.0
    useful5 = sum(1 for label in labels[:5] if label in USEFUL_LABELS) / 5.0 if labels else 0.0
    useful20 = sum(1 for label in labels[:20] if label in USEFUL_LABELS) / 20.0 if labels else 0.0
    strict_r20 = 1.0 if acc.pool_strict > 0 and any(label in STRICT_LABELS for label in labels[:20]) else 0.0
    mrr20 = mrr_from_labels(labels, 20)
    pool_useful_rate = acc.pool_useful / acc.pool_size if acc.pool_size else 0.0
    lift20 = useful20 / pool_useful_rate if pool_useful_rate > 0 else 0.0
    recommendation_score = 100.0 * (
        0.25 * gndcg20
        + 0.15 * useful5
        + 0.15 * useful20
        + 0.20 * strict_r20
        + 0.15 * mrr20
        + 0.10 * min(lift20 / lift_cap, 1.0)
    )
    return {
        "RecommendationScore": recommendation_score,
        "gNDCG@20": gndcg20,
        "Useful@5": useful5,
        "Useful@20": useful20,
        "StrictR@20+": strict_r20,
        "MRR@20": mrr20,
        "Lift@20": lift20,
    }


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                yield item


def collect_method_episodes(method_key: str, method_name: str, path: Path) -> List[Dict[str, Any]]:
    episodes: Dict[str, EpisodeAccumulator] = {}
    for row in iter_jsonl(path):
        episode_id = str(row.get("episode_id") or "")
        if not episode_id:
            continue
        acc = episodes.get(episode_id)
        if acc is None:
            acc = EpisodeAccumulator(
                method_key=method_key,
                method_name=method_name,
                episode_id=episode_id,
                user_id=str(row.get("user_id") or ""),
                role_name=str(row.get("role_name") or ""),
                date=str(row.get("date") or ""),
            )
            episodes[episode_id] = acc
        label = str(row.get("oracle_label") or "irrelevant")
        acc.pool_size += 1
        acc.pool_useful += int(label in USEFUL_LABELS)
        acc.pool_strict += int(label in STRICT_LABELS)
        acc.pool_gains.append(ORACLE_GAIN.get(label, 0.0))
        if as_bool(row.get("shown")):
            acc.shown_rows.append(row)

    result = []
    for acc in episodes.values():
        if not acc.shown_rows:
            continue
        metrics = compute_episode_metrics(acc)
        result.append(
            {
                "method_key": acc.method_key,
                "method_name": acc.method_name,
                "episode_id": acc.episode_id,
                "user_id": acc.user_id,
                "role_name": acc.role_name,
                "date": acc.date,
                "shown_rows": sorted(acc.shown_rows, key=lambda item: int(item.get("system_rank") or 10**9)),
                **metrics,
            }
        )
    return result


def score_bucket(score: float) -> str:
    if score < 40:
        return "low"
    if score < 60:
        return "mid"
    return "high"


def sample_episodes(episodes: List[Dict[str, Any]], count: int, seed: int) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        buckets[score_bucket(float(episode["RecommendationScore"]))].append(episode)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    selected: List[Dict[str, Any]] = []
    labels = ["low", "mid", "high"]
    per_bucket = max(1, count // len(labels))
    for label in labels:
        selected.extend(buckets.get(label, [])[:per_bucket])
    leftovers = [item for label in labels for item in buckets.get(label, [])[per_bucket:]]
    rng.shuffle(leftovers)
    selected.extend(leftovers[: max(0, count - len(selected))])
    return selected[:count]


def choose_rows_for_episode(episode: Dict[str, Any], papers_per_episode: int, rng: random.Random) -> List[Dict[str, Any]]:
    shown = list(episode["shown_rows"])
    top = [row for row in shown if int(row.get("system_rank") or 99) <= 5]
    tail = [row for row in shown if int(row.get("system_rank") or 99) > 5]
    chosen: List[Dict[str, Any]] = []
    if top and papers_per_episode >= 1:
        chosen.append(rng.choice(top))
    if tail and papers_per_episode >= 2:
        chosen.append(rng.choice(tail))
    remaining = [row for row in shown if row not in chosen]
    rng.shuffle(remaining)
    chosen.extend(remaining[: max(0, papers_per_episode - len(chosen))])
    return chosen[:papers_per_episode]


def build_rows(
    episodes_by_method: Dict[str, List[Dict[str, Any]]],
    users: Dict[str, Dict[str, Any]],
    *,
    episodes_per_method: int,
    papers_per_episode: int,
    seed: int,
    abstract_chars: int,
    paper_urls: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rng = random.Random(seed)
    paper_urls = paper_urls or {}
    blind_rows: List[Dict[str, Any]] = []
    key_rows: List[Dict[str, Any]] = []
    sample_index = 1
    for method_key in sorted(episodes_by_method):
        episodes = sample_episodes(episodes_by_method[method_key], episodes_per_method, seed + len(method_key))
        for episode in episodes:
            for paper in choose_rows_for_episode(episode, papers_per_episode, rng):
                sample_id = f"HMAIN_{sample_index:05d}"
                sample_index += 1
                user_id = str(episode.get("user_id") or paper.get("user_id") or "")
                paper_id = str(paper.get("paper_id") or "").strip()
                blind_rows.append(
                    {
                        "sample_id": sample_id,
                        "user_profile": profile_text(users.get(user_id)),
                        "paper_title": truncate(paper.get("title"), 500),
                        "paper_abstract": truncate(paper.get("abstract"), abstract_chars),
                        "paper_authors": truncate(paper.get("authors"), 500),
                        "paper_url": truncate(paper_url_from_record(paper) or paper_urls.get(paper_id), 500),
                        "HumanRelevance": "",
                        "HumanUsefulness": "",
                        "DecisionHelpfulness": "",
                        "comments": "",
                    }
                )
                key_rows.append(
                    {
                        "sample_id": sample_id,
                        "method_key": episode["method_key"],
                        "method_name": episode["method_name"],
                        "episode_id": episode["episode_id"],
                        "user_id": user_id,
                        "role_name": episode.get("role_name"),
                        "date": episode.get("date"),
                        "paper_id": paper.get("paper_id"),
                        "system_rank": paper.get("system_rank"),
                        "system_label": paper.get("system_label"),
                        "system_score": paper.get("system_score"),
                        "oracle_label": paper.get("oracle_label"),
                        "oracle_score": paper.get("oracle_score"),
                        "selected": as_bool(paper.get("selected")),
                        "RecommendationScore": f"{float(episode['RecommendationScore']):.6f}",
                        "gNDCG@20": f"{float(episode['gNDCG@20']):.6f}",
                        "Useful@5": f"{float(episode['Useful@5']):.6f}",
                        "Useful@20": f"{float(episode['Useful@20']):.6f}",
                        "StrictR@20+": f"{float(episode['StrictR@20+']):.6f}",
                        "MRR@20": f"{float(episode['MRR@20']):.6f}",
                        "Lift@20": f"{float(episode['Lift@20']):.6f}",
                    }
                )
    return blind_rows, key_rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_guidelines(path: Path) -> None:
    path.write_text(
        """# Main Human Evaluation Annotation Guide

Annotators see only the user profile and paper content. Method name, rank,
oracle label, selected flag, and automatic scores are hidden.

Use a 1-5 Likert scale:

- 1 = very poor
- 2 = poor
- 3 = fair
- 4 = good
- 5 = very good

Dimensions:

- HumanRelevance: whether the paper matches the user's profile and research interests.
- HumanUsefulness: whether the paper is worth reading for this user.
- DecisionHelpfulness: whether seeing this recommendation helps the user decide to read deeply, skim, or skip.

The final paper-level score is:

```text
HumanEval = 20 * mean(HumanRelevance, HumanUsefulness, DecisionHelpfulness)
```
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a blind main-experiment human-evaluation packet.")
    parser.add_argument("--benchmark-dir", default=str(DEFAULT_BENCHMARK_DIR))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--method", action="append", default=[], help="Optional key=path or key=path=display name")
    parser.add_argument("--episodes-per-method", type=int, default=12)
    parser.add_argument("--papers-per-episode", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--abstract-chars", type=int, default=1200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = Path(args.benchmark_dir)
    output_dir = Path(args.output_dir) if args.output_dir else benchmark_dir / "evaluation" / "main_human_eval"
    users = load_users(benchmark_dir / "users.json")
    paper_urls = load_paper_url_map(benchmark_dir)

    episodes_by_method: Dict[str, List[Dict[str, Any]]] = {}
    for key, name, path in method_paths(benchmark_dir, args.method):
        if not path.exists():
            print(f"Skipping missing method file: {path}")
            continue
        print(f"Collecting {key}: {path}")
        episodes_by_method[key] = collect_method_episodes(key, name, path)
        print(f"  episodes: {len(episodes_by_method[key])}")

    blind_rows, key_rows = build_rows(
        episodes_by_method,
        users,
        episodes_per_method=args.episodes_per_method,
        papers_per_episode=args.papers_per_episode,
        seed=args.seed,
        abstract_chars=args.abstract_chars,
        paper_urls=paper_urls,
    )
    write_csv(output_dir / "main_human_eval_blind.csv", blind_rows)
    write_csv(output_dir / "main_human_eval_key.csv", key_rows)
    write_guidelines(output_dir / "main_human_eval_guidelines.md")
    print(f"Blind packet: {output_dir / 'main_human_eval_blind.csv'}")
    print(f"Internal key: {output_dir / 'main_human_eval_key.csv'}")
    print(f"Rows exported: {len(blind_rows)}")


if __name__ == "__main__":
    main()
