#!/usr/bin/env python3
"""
Export Daily Data - 导出每日数据

将模拟生成的 JSONL 文件合并为完整的 CSV/JSONL 导出文件，
支持按日期范围过滤，便于后续分析。

使用方法:
    # 导出全部数据
    python scripts/export_daily_data.py --input-dir data/simulation_output

    # 导出指定日期范围
    python scripts/export_daily_data.py \
      --input-dir data/simulation_output \
      --start-date 2026-03-01 \
      --end-date 2026-03-31

    # 导出为 CSV 格式
    python scripts/export_daily_data.py --input-dir data/simulation_output --format csv
"""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_jsonl_file(input_dir: Path, subdir: str, filename: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
    """加载单个 JSONL 文件，支持日期过滤"""
    records = []

    if subdir:
        file_path = input_dir / subdir / filename
    else:
        file_path = input_dir / filename

    if not file_path.exists():
        print(f"  [Warning] File not found: {file_path}")
        return records

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            record = json.loads(line)
            record_date = record.get("date", "")

            # 日期过滤
            if start_date and record_date < start_date:
                continue
            if end_date and record_date > end_date:
                continue

            records.append(record)

    print(f"  Loaded {len(records)} records from {file_path.relative_to(input_dir.parent)}")
    return records


def load_all_jsonl_files(input_dir: Path, subdir: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
    """加载指定子目录下的所有 JSONL 文件（旧版兼容）"""
    records = []
    dir_path = input_dir / subdir

    if not dir_path.exists():
        print(f"  [Warning] Directory not found: {dir_path}")
        return records

    for f in sorted(dir_path.glob("*.jsonl")):
        date_str = f.stem

        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue

        with f.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

    print(f"  Loaded {len(records)} records from {subdir}")
    return records


def flatten_profile(record: Dict) -> Dict:
    """将 profile 记录扁平化"""
    profile_json = record.get("profile_json", {})

    return {
        "date": record.get("date", ""),
        "user_id": record.get("user_id", ""),
        "role_name": record.get("role_name", ""),
        "version": record.get("version", ""),
        "core_directions": json.dumps(profile_json.get("core_directions", {}), ensure_ascii=False),
        "topic_weights": json.dumps(profile_json.get("topic_weights", {}), ensure_ascii=False),
        "must_read_authors": json.dumps(profile_json.get("must_read", {}).get("authors", []), ensure_ascii=False),
        "must_read_institutions": json.dumps(profile_json.get("must_read", {}).get("institutions", []), ensure_ascii=False),
        "must_read_keywords": json.dumps(profile_json.get("must_read", {}).get("keywords", []), ensure_ascii=False),
        "drift_status": profile_json.get("drift_state", {}).get("status", ""),
        "drift_score": profile_json.get("drift_state", {}).get("score", 0),
        "drift_top_topics": json.dumps(profile_json.get("drift_state", {}).get("top_shift_topics", []), ensure_ascii=False),
    }


def flatten_episode(record: Dict) -> Dict:
    """将 episode 记录扁平化"""
    return {
        "date": record.get("date", ""),
        "episode_id": record.get("episode_id", ""),
        "user_id": record.get("user_id", ""),
        "role_name": record.get("role_name", ""),
        "episode_type": record.get("episode_type", ""),
        "candidate_papers": record.get("candidate_papers", 0),
        "candidate_must_read": record.get("candidate_must_read", 0),
        "candidate_high_relevant": record.get("candidate_high_relevant", 0),
        "candidate_maybe_interested": record.get("candidate_maybe_interested", 0),
        "candidate_edge_relevant": record.get("candidate_edge_relevant", 0),
        "selected_papers": record.get("selected_papers", 0),
        "selected_must_read": record.get("selected_must_read", 0),
        "selected_high_relevant": record.get("selected_high_relevant", 0),
        "selected_maybe_interested": record.get("selected_maybe_interested", 0),
        "selected_edge_relevant": record.get("selected_edge_relevant", 0),
        "skipped_papers": record.get("skipped_papers", 0),
        "drift_detected": record.get("drift_detected", False),
        "drift_status": record.get("drift_status", ""),
        "drift_score": record.get("drift_score", 0),
        "selected_paper_ids": json.dumps(record.get("selected_paper_ids", []), ensure_ascii=False),
    }


def flatten_drift(record: Dict) -> Dict:
    """将 drift 记录扁平化"""
    return {
        "timestamp": record.get("timestamp", ""),
        "date": record.get("date", ""),
        "user_id": record.get("user_id", ""),
        "transition": record.get("transition", ""),
        "score_delta": record.get("score_delta", 0),
        "method": record.get("method", ""),
        "checkfile_name": record.get("checkfile_name", ""),
        "emerging_topics": json.dumps(record.get("emerging_topics", []), ensure_ascii=False),
        "directions_added": json.dumps(record.get("directions_added", []), ensure_ascii=False),
        "directions_removed": json.dumps(record.get("directions_removed", []), ensure_ascii=False),
        "explanation": record.get("explanation", ""),
    }


def export_to_csv(records: List[Dict], output_path: Path, flatten_func=None) -> None:
    """导出为 CSV 格式"""
    if not records:
        print("  No records to export")
        return

    # 扁平化
    if flatten_func:
        records = [flatten_func(r) for r in records]

    # 获取所有字段
    all_fields = set()
    for r in records:
        all_fields.update(r.keys())

    # 排序字段（日期和用户 ID 在前）
    priority_fields = ["date", "timestamp", "user_id", "episode_id", "role_name"]
    fields = [f for f in priority_fields if f in all_fields]
    fields.extend(sorted(all_fields - set(fields)))

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print(f"  Exported {len(records)} records to {output_path}")


def export_to_jsonl(records: List[Dict], output_path: Path, flatten_func=None) -> None:
    """导出为 JSONL 格式"""
    if not records:
        print("  No records to export")
        return

    with output_path.open("w", encoding="utf-8") as f:
        for r in records:
            if flatten_func:
                r = flatten_func(r)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"  Exported {len(records)} records to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Export Daily Data")
    parser.add_argument("--input-dir", type=str, required=True, help="模拟输出目录")
    parser.add_argument("--output-dir", type=str, default=None, help="导出输出目录")
    parser.add_argument("--start-date", type=str, default=None, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--format", type=str, choices=["csv", "jsonl"], default="csv", help="输出格式")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_absolute():
        input_dir = PROJECT_ROOT / input_dir

    output_dir = args.output_dir
    if output_dir:
        output_dir = Path(output_dir)
        if not output_dir.is_absolute():
            output_dir = PROJECT_ROOT / output_dir
    else:
        output_dir = input_dir / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Date range: {args.start_date or 'start'} to {args.end_date or 'end'}")
    print()

    export_func = export_to_csv if args.format == "csv" else export_to_jsonl

    # 导出 Profile History
    print("Exporting profile history...")
    profile_records = load_jsonl_file(input_dir, "", "profiles.jsonl", args.start_date, args.end_date)
    export_func(profile_records, output_dir / "profile_history.csv" if args.format == "csv" else output_dir / "profile_history.jsonl", flatten_profile)

    # 导出 Episode History
    print("Exporting episode history...")
    episode_records = load_jsonl_file(input_dir, "", "episodes.jsonl", args.start_date, args.end_date)
    export_func(episode_records, output_dir / "episode_history.csv" if args.format == "csv" else output_dir / "episode_history.jsonl", flatten_episode)

    # 导出 Drift Events
    print("Exporting drift events...")
    drift_records = load_jsonl_file(input_dir, "", "drift_timeline.jsonl", args.start_date, args.end_date)
    export_func(drift_records, output_dir / "drift_events.csv" if args.format == "csv" else output_dir / "drift_events.jsonl", flatten_drift)

    # 导出 Paper Pools
    print("Exporting paper pools...")
    paper_pool_records = load_jsonl_file(input_dir, "", "paper_pools.jsonl", args.start_date, args.end_date)
    if args.format == "csv":
        export_func(paper_pool_records, output_dir / "paper_pools.csv", None)
    else:
        with (output_dir / "paper_pools.jsonl").open("w", encoding="utf-8") as f:
            for r in paper_pool_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  Exported {len(paper_pool_records)} records to paper_pools.jsonl")

    # 导出用户元数据
    print("Exporting user metadata...")
    users_file = input_dir / "users.json"
    if users_file.exists():
        with users_file.open("r", encoding="utf-8") as f:
            users_data = json.load(f)
        users_output = output_dir / "users.json"
        with users_output.open("w", encoding="utf-8") as f:
            json.dump(users_data, f, ensure_ascii=False, indent=2)
        print(f"  Exported {len(users_data.get('users', []))} users to {users_output}")

    # 生成统计报告
    print()
    print("Generating summary...")
    summary = {
        "export_date": datetime.now().isoformat(),
        "date_range": {"start": args.start_date, "end": args.end_date},
        "counts": {
            "profile_records": len(profile_records),
            "episode_records": len(episode_records),
            "drift_records": len(drift_records),
        },
        "format": args.format,
    }

    summary_path = output_dir / "export_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  Summary saved to {summary_path}")

    print()
    print("=" * 60)
    print("Export Complete")
    print("=" * 60)
    print(f"Profile Records: {len(profile_records)}")
    print(f"Episode Records: {len(episode_records)}")
    print(f"Drift Records: {len(drift_records)}")
    print(f"Output Dir: {output_dir}")


if __name__ == "__main__":
    main()
