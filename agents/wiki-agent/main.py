#!/usr/bin/env python3
"""PaperFlow Wiki CLI backend."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # pragma: no cover - optional dependency
    pass

wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")
topic_ingest = importlib.import_module("agents.wiki-agent.ingest.from_topic_clustering")
backfill_ingest = importlib.import_module("agents.wiki-agent.ingest.backfill")
answer_module = importlib.import_module("agents.wiki-agent.retrieve.answer")
monthly_export = importlib.import_module("agents.wiki-agent.export.monthly_report")


def _print_nodes(nodes: List[Dict[str, Any]]) -> None:
    if not nodes:
        print("No wiki nodes found.")
        return
    for node in nodes:
        updated = str(node.get("updated_at") or "")[:19]
        keywords = str(node.get("keywords") or "").strip()
        suffix = f" | {keywords}" if keywords else ""
        print(f"{updated}  [{node['node_type']}] {node['node_id']}  {node['title']}{suffix}")


def _cmd_init(_args: argparse.Namespace) -> int:
    wiki_db.init_wiki_schema()
    print("PaperFlow Wiki storage is ready.")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    nodes = wiki_db.list_nodes(args.user_id, node_type=args.type, limit=args.limit)
    if args.json:
        print(json.dumps(nodes, ensure_ascii=False, indent=2))
    else:
        _print_nodes(nodes)
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    nodes = wiki_db.search_nodes(args.user_id, args.query, node_type=args.type, limit=args.limit)
    if args.json:
        print(json.dumps(nodes, ensure_ascii=False, indent=2))
    else:
        _print_nodes(nodes)
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    stats = wiki_db.stats(args.user_id)
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    print(f"Wiki stats for {stats['user_id']}")
    print(f"- Nodes: {stats['nodes']} {stats['nodes_by_type']}")
    print(f"- Edges: {stats['edges']}")
    print(f"- Citations: {stats['citations']}")
    print(f"- Latest update: {stats.get('latest_update') or 'never'}")
    print(f"- Wiki dir: {stats['wiki_dir']}")
    return 0


def _cmd_embed(args: argparse.Namespace) -> int:
    result = wiki_db.embed_nodes_for_user(args.user_id, force=args.force, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Embedded {result['embedded']} nodes with {result.get('model') or 'n/a'}.")
    return 0


def _cmd_topics(args: argparse.Namespace) -> int:
    result = topic_ingest.flush_topics(args.user_id, min_count=args.min_count, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Topics: {result['topics']}; edges: {result['belongs_to_edges']}")
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    result = answer_module.answer_question(args.user_id, args.question, limit=args.limit)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(result["text"])
    if result.get("citations"):
        print("\nSources:")
        for citation in result["citations"]:
            print(f"[{citation['index']}] {citation['title']} ({citation['node_id']})")
    return 0


def _cmd_backfill(args: argparse.Namespace) -> int:
    if args.all:
        result = backfill_ingest.backfill_all(dry_run=args.dry_run)
    else:
        if not args.user_id:
            raise SystemExit("--user-id is required unless --all is set")
        result = backfill_ingest.backfill_user(args.user_id, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0


def _cmd_monthly(args: argparse.Namespace) -> int:
    result = monthly_export.export_monthly_report(
        args.user_id,
        month=args.month,
        output_dir=args.output_dir,
        topic_index_dir=args.topic_index_dir,
        write_topic_index=not args.no_topic_index,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Monthly report: {result['report_path']}")
        if result.get("topic_index_path"):
            print(f"Topic index: {result['topic_index_path']}")
        print(f"Papers: {result['paper_count']}; topics: {result['topic_count']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PaperFlow Wiki")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize wiki tables and folders.")
    init_parser.set_defaults(func=_cmd_init)

    list_parser = subparsers.add_parser("list", help="List wiki nodes.")
    list_parser.add_argument("--user-id", required=True)
    list_parser.add_argument("--type", choices=["paper", "section", "trajectory", "topic"])
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=_cmd_list)

    search_parser = subparsers.add_parser("search", help="Search wiki nodes.")
    search_parser.add_argument("query")
    search_parser.add_argument("--user-id", required=True)
    search_parser.add_argument("--type", choices=["paper", "section", "trajectory", "topic"])
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument("--json", action="store_true")
    search_parser.set_defaults(func=_cmd_search)

    stats_parser = subparsers.add_parser("stats", help="Show wiki storage stats.")
    stats_parser.add_argument("--user-id", required=True)
    stats_parser.add_argument("--json", action="store_true")
    stats_parser.set_defaults(func=_cmd_stats)

    embed_parser = subparsers.add_parser("embed", help="Embed wiki nodes for vector search.")
    embed_parser.add_argument("--user-id", required=True)
    embed_parser.add_argument("--force", action="store_true")
    embed_parser.add_argument("--limit", type=int, default=500)
    embed_parser.add_argument("--json", action="store_true")
    embed_parser.set_defaults(func=_cmd_embed)

    topics_parser = subparsers.add_parser("topics", help="Flush keyword topic nodes.")
    topics_parser.add_argument("--user-id", required=True)
    topics_parser.add_argument("--min-count", type=int, default=2)
    topics_parser.add_argument("--limit", type=int, default=50)
    topics_parser.add_argument("--json", action="store_true")
    topics_parser.set_defaults(func=_cmd_topics)

    ask_parser = subparsers.add_parser("ask", help="Ask a question over the local wiki.")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--user-id", required=True)
    ask_parser.add_argument("--limit", type=int, default=8)
    ask_parser.add_argument("--json", action="store_true")
    ask_parser.set_defaults(func=_cmd_ask)

    backfill_parser = subparsers.add_parser("backfill", help="Backfill existing runtime data into wiki.")
    backfill_parser.add_argument("--user-id")
    backfill_parser.add_argument("--all", action="store_true")
    backfill_parser.add_argument("--dry-run", action="store_true")
    backfill_parser.add_argument("--json", action="store_true")
    backfill_parser.set_defaults(func=_cmd_backfill)

    monthly_parser = subparsers.add_parser("monthly", help="Export an Obsidian-friendly monthly report.")
    monthly_parser.add_argument("--user-id", required=True)
    monthly_parser.add_argument("--month", help="Month to export in YYYY-MM format. Defaults to current month.")
    monthly_parser.add_argument("--output-dir", help="Monthly report output directory.")
    monthly_parser.add_argument("--topic-index-dir", help="Topic Index output directory. Defaults to output dir.")
    monthly_parser.add_argument("--no-topic-index", action="store_true")
    monthly_parser.add_argument("--json", action="store_true")
    monthly_parser.set_defaults(func=_cmd_monthly)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
