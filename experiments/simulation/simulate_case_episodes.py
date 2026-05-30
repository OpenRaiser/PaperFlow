#!/usr/bin/env python3
"""
Simulate a small historical case for quick dataset inspection.

Default behavior:
- Randomly sample 2~3 users from the existing 24 profiles
- Simulate from 2026-03-01 to 2026-03-10
- Reuse the same day-by-day collection -> simulation -> jsonl writing logic
  as simulate_historical_episodes.py
"""

from __future__ import annotations

import argparse
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.simulation import simulate_historical_episodes as sim


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a small historical case with 2-3 sampled users.")
    parser.add_argument("--start-date", type=str, default="20260301", help="Start date YYYYMMDD")
    parser.add_argument("--end-date", type=str, default="20260310", help="End date YYYYMMDD")
    parser.add_argument("--drift-probability", type=float, default=0.5, help="Drift probability")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--min-users", type=int, default=2, help="Minimum sampled users")
    parser.add_argument("--max-users", type=int, default=3, help="Maximum sampled users")
    parser.add_argument(
        "--llm-model",
        type=str,
        default=os.environ.get("LLM_PARSER_OPENAI_MODEL", "gemini-3-flash-preview"),
        help="LLM model label used in benchmark summaries",
    )
    parser.add_argument("--embedding-model", type=str, default="Qwen/Qwen3-Embedding-8B", help="Embedding model label")
    parser.add_argument("--sources", nargs="*", default=None, help="Paper sources collected each day")
    parser.add_argument("--limit-per-source", type=int, default=None, help="Optional daily max papers per source")
    parser.add_argument("--skip-paper-collection", action="store_true", help="Skip daily paper collection")
    parser.add_argument("--skip-reading-reports", action="store_true", help="Skip reading report generation for recommendation-only case runs")
    parser.add_argument("--show-count", type=int, default=sim.DEFAULT_SIMULATION_SHOW_COUNT, help="Displayed papers per episode after real-ranking fallback fill")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    random.seed(args.seed)
    sim.embedding_module._default_service = None
    if hasattr(sim.reading_agent, "READING_REPORT_EVIDENCE_CACHE_ENABLED"):
        sim.reading_agent.READING_REPORT_EVIDENCE_CACHE_ENABLED = False
    sim._patch_real_usage_logging()

    start_date = datetime.strptime(args.start_date, "%Y%m%d")
    end_date = datetime.strptime(args.end_date, "%Y%m%d")

    conn = sqlite3.connect(sim.DB_PATH)
    users = sim.get_all_users(conn)
    conn.close()

    if not users:
        raise RuntimeError("No user profiles found in database.")

    sample_size = random.randint(args.min_users, args.max_users)
    sampled_users = random.sample(users, min(sample_size, len(users)))
    sampled_user_ids = {user["user_id"] for user in sampled_users}

    print(f"Case simulation from {start_date.date()} to {end_date.date()}")
    print(f"Sampled users: {sorted(sampled_user_ids)}")
    print(f"Drift probability: {args.drift_probability}")
    print()

    checkfiles = sim.load_checkfiles(sim.DRIFT_CHECKFILES_DIR)
    print(f"Loaded {len(checkfiles)} drift checkfiles")
    drift_engine = sim.DriftEngine(checkfiles)

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else PROJECT_ROOT / "data" / f"simulation_case_{args.start_date}_{args.end_date}"
    )
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    resume_state = sim.load_resume_state(output_dir, start_date)
    resumed_user_metadata = resume_state.get("user_metadata") or []
    if resume_state["resume"]:
        resumed_user_ids = [str(item.get("user_id")) for item in resumed_user_metadata if str(item.get("user_id") or "").strip()]
        if not resumed_user_ids:
            resumed_user_ids = sorted(resume_state["profiles_by_user"].keys())
        if resumed_user_ids:
            sampled_users = sim.filter_users_by_ids(users, resumed_user_ids)
        sampled_users = sim.apply_resumed_profiles(sampled_users, resume_state["profiles_by_user"])
        sampled_user_ids = {user["user_id"] for user in sampled_users}
        print(f"Resuming case from {resume_state['previous_day']} with users: {sorted(sampled_user_ids)}")
    else:
        sim.clear_simulation_output_files(output_dir)

    output_manager = sim.OutputManager(str(output_dir))

    roles_meta = sim.load_roles_meta()
    user_metadata = resumed_user_metadata if resume_state["resume"] and resumed_user_metadata else []
    if not user_metadata:
        for user in sampled_users:
            profile = user["profile"]
            role_name = user["user_id"].replace("user_", "")
            role_info = roles_meta.get(role_name, {})
            user_metadata.append(
                {
                    "user_id": user["user_id"],
                    "role_name": role_name,
                    "description": role_info.get("description", profile.get("description", "")),
                    "seed_directions": profile.get("core_directions", {}),
                    "created_at": start_date.strftime("%Y-%m-%d"),
                }
            )
    output_manager.save_user_metadata(user_metadata)

    all_results = []
    current_date = start_date
    generated_report_keys: set[str] = set(resume_state["generated_report_keys"])

    while current_date <= end_date:
        newly_collected = 0
        if not args.skip_paper_collection:
            print(f"[{current_date.date()}] Collecting papers for this day...")
            newly_collected = sim.collect_papers_for_day(
                current_date,
                sources=args.sources,
                limit_per_source=args.limit_per_source,
            )

        conn = sqlite3.connect(sim.DB_PATH)
        day_new_papers = sim.get_papers_by_date(conn, current_date)
        day_papers = sim.get_papers_up_to_date(conn, current_date)
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
        result = sim.simulate_one_day(
            date=current_date,
            papers=day_new_papers,
            new_papers=day_new_papers,
            total_papers_count=len(day_papers),
            users=sampled_users,
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
            f"  Episodes: {result['episodes']}, Drifts: {result['drift_count']}, "
            f"Today's papers: {result['new_papers_collected']}, "
            f"Embedding tokens: {result['tokens']['embedding']}, LLM tokens: {result['tokens']['llm']}"
        )
        current_date += timedelta(days=1)

    output_manager.close()

    previous_summary = resume_state["existing_summary"] or {}
    summary = sim.merge_summary_with_previous(
        previous_summary,
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
            "sampled_users": sorted(sampled_user_ids),
            "user_count": len(sampled_users),
            "skip_reading_reports": bool(args.skip_reading_reports),
            "show_count": int(args.show_count or sim.DEFAULT_SIMULATION_SHOW_COUNT),
            "token_usage": {
                "embedding_model": args.embedding_model,
                "llm_model": args.llm_model,
                "embedding_tokens": int((previous_summary.get("token_usage", {}) or {}).get("embedding_tokens", 0) or 0)
                + sum(r.get("tokens", {}).get("embedding", 0) for r in all_results),
                "llm_tokens": int((previous_summary.get("token_usage", {}) or {}).get("llm_tokens", 0) or 0)
                + sum(r.get("tokens", {}).get("llm", 0) for r in all_results),
                "total_tokens": int((previous_summary.get("token_usage", {}) or {}).get("total_tokens", 0) or 0)
                + sum(
                    r.get("tokens", {}).get("embedding", 0) + r.get("tokens", {}).get("llm", 0)
                    for r in all_results
                ),
            },
        },
    )

    summary_path = output_dir / "simulation_summary.json"
    summary_path.write_text(
        __import__("json").dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 60)
    print("Case Simulation Complete")
    print("=" * 60)
    print(f"Days: {len(all_results)}")
    print(f"Sampled users: {len(sampled_users)}")
    print(f"Total Episodes: {summary['total_episodes']}")
    print(f"Total Drifts: {summary['total_drifts']}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
