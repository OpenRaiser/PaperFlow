#!/usr/bin/env python3
"""
Token 花销统计工具

用于统计：
1. Embedding Token 消耗（Qwen-Embedding-8B）
2. LLM Token 消耗（qwen3.5-plus 或其他模型）
3. 按日期/用户/任务类型聚合统计

使用方法:
    python scripts/token_usage_tracker.py --start-date 20260301 --end-date 20260420
    python scripts/token_usage_tracker.py --mode benchmark --llm-model qwen3.5-plus
"""

import argparse
import json
import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict

import requests

DB_PATH = Path("data/paperflow.db")
TOKEN_LOG_PATH = Path("data/token_usage.jsonl")

# 模型价格表 (per 1K tokens)
MODEL_PRICES = {
    # Qwen 系列
    "qwen3.5-plus": {"input": 0.002, "output": 0.006},
    "qwen3-plus": {"input": 0.002, "output": 0.006},
    "qwen-max": {"input": 0.04, "output": 0.12},
    "qwen-plus": {"input": 0.001, "output": 0.003},
    # Gemini 系列
    "gemini-3-flash-preview": {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-flash": {"input": 0.000075, "output": 0.0003},
    # Qwen Embedding
    "Qwen/Qwen3-Embedding-8B": {"input": 0.0007, "output": 0},
    "Qwen/Qwen3-Embedding-0.6B": {"input": 0.0007, "output": 0},
    # 其他
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
}


def estimate_tokens(text: str) -> int:
    """估算文本的 token 数（中文约 1.5 字符/token，英文约 4 字符/token）"""
    if not text:
        return 0
    # 粗略估算：中文字符和英文字符混合
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    english_chars = len(text) - chinese_chars
    # 中文约 1.5 字符/token，英文约 4 字符/token
    return int(chinese_chars / 1.5 + english_chars / 4) + 10


# 内存中的每日 token 累计
_daily_token_totals: Dict[str, Dict[str, Any]] = {}


def _is_daily_aggregate_record(record: Dict[str, Any]) -> bool:
    """Identify compact per-day rows and exclude legacy per-call rows."""
    required_keys = {"date", "embedding_tokens", "llm_tokens", "total_tokens", "call_count"}
    return required_keys.issubset(record.keys()) and "task_type" not in record


def _load_existing_daily_aggregates() -> Dict[str, Dict[str, Any]]:
    """Load existing per-day totals while ignoring legacy per-call detail rows."""
    if not TOKEN_LOG_PATH.exists():
        return {}

    aggregates: Dict[str, Dict[str, Any]] = {}
    with open(TOKEN_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(record, dict) or not _is_daily_aggregate_record(record):
                continue

            date = str(record.get("date") or "").strip()
            if not date:
                continue

            aggregates[date] = {
                "date": date,
                "embedding_tokens": int(record.get("embedding_tokens") or 0),
                "llm_tokens": int(record.get("llm_tokens") or 0),
                "total_tokens": int(record.get("total_tokens") or 0),
                "call_count": int(record.get("call_count") or 0),
            }

    return aggregates


def log_token_usage(
    task_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    user_id: Optional[str] = None,
    date: Optional[str] = None,
    extra: Optional[Dict] = None
) -> None:
    """记录一次 token 使用（累加到每日总计，不实时写入文件）"""
    record_date = date or datetime.now().strftime("%Y-%m-%d")

    if record_date not in _daily_token_totals:
        _daily_token_totals[record_date] = {
            "date": record_date,
            "embedding_input": 0,
            "embedding_output": 0,
            "llm_input": 0,
            "llm_output": 0,
            "call_count": 0,
        }

    total = _daily_token_totals[record_date]
    total["call_count"] += 1

    if "embedding" in task_type.lower():
        total["embedding_input"] += input_tokens
        total["embedding_output"] += output_tokens
    else:
        total["llm_input"] += input_tokens
        total["llm_output"] += output_tokens


def flush_token_logs() -> None:
    """将所有每日 token 总计写入文件（在每天结束时调用）"""
    TOKEN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = _load_existing_daily_aggregates()

    for date, total in sorted(_daily_token_totals.items()):
        embedding_tokens = total["embedding_input"] + total["embedding_output"]
        llm_tokens = total["llm_input"] + total["llm_output"]
        merged[date] = {
            "date": date,
            "embedding_tokens": embedding_tokens,
            "llm_tokens": llm_tokens,
            "total_tokens": embedding_tokens + llm_tokens,
            "call_count": total["call_count"],
        }

    with open(TOKEN_LOG_PATH, "w", encoding="utf-8") as f:
        for date in sorted(merged):
            f.write(json.dumps(merged[date], ensure_ascii=False) + "\n")

    _daily_token_totals.clear()


def calculate_cost(task_type: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """计算单次调用成本"""
    pricing = MODEL_PRICES.get(model, {"input": 0, "output": 0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000


def get_usage_stats(
    start_date: str,
    end_date: str,
    group_by: str = "date"
) -> Dict[str, Any]:
    """获取指定日期范围的 token 使用统计"""
    if not TOKEN_LOG_PATH.exists():
        return {"error": "No token log found"}

    stats = defaultdict(lambda: {
        "embedding_input": 0,
        "embedding_output": 0,
        "llm_input": 0,
        "llm_output": 0,
        "cost": 0,
        "calls": 0,
    })

    with open(TOKEN_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            record_date = record.get("date", "")

            if not (start_date <= record_date <= end_date):
                continue

            if _is_daily_aggregate_record(record):
                key = record.get(group_by, record_date) if group_by == "date" else "aggregate"
                s = stats[key]
                s["embedding_input"] += int(record.get("embedding_tokens", 0))
                s["llm_input"] += int(record.get("llm_tokens", 0))
                s["calls"] += int(record.get("call_count", 0))
                continue

            key = record.get(group_by, "unknown")
            s = stats[key]

            task_type = record.get("task_type", "")
            input_tokens = record.get("input_tokens", 0)
            output_tokens = record.get("output_tokens", 0)
            model = record.get("model", "")

            s["calls"] += 1

            if "embedding" in task_type.lower():
                s["embedding_input"] += input_tokens
                s["embedding_output"] += output_tokens
            else:
                s["llm_input"] += input_tokens
                s["llm_output"] += output_tokens

            s["cost"] += calculate_cost(task_type, model, input_tokens, output_tokens)

    return dict(stats)


def benchmark_one_day(
    date: str,
    llm_model: str,
    papers: List[Dict],
    user_profiles: List[Dict],
) -> Dict[str, Any]:
    """
    基准测试：模拟一天的完整流程，统计 token 消耗

    流程：
    1. Embedding 所有论文
    2. 对每个用户进行排序
    3. 生成推送内容
    4. 模拟用户反馈后生成精读报告
    """
    result = {
        "date": date,
        "llm_model": llm_model,
        "embedding_model": os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B"),
        "paper_count": len(papers),
        "user_count": len(user_profiles),
        "breakdown": {},
        "total": {
            "embedding_tokens": 0,
            "llm_tokens": 0,
            "estimated_cost_usd": 0,
        }
    }

    # 1. Embedding 所有论文
    embedding_tokens = 0
    for paper in papers:
        text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
        tokens = estimate_tokens(text)
        embedding_tokens += tokens

        # 记录
        log_token_usage(
            task_type="embedding",
            model=result["embedding_model"],
            input_tokens=tokens,
            output_tokens=0,
            date=date,
        )

    result["breakdown"]["embedding"] = {
        "papers": len(papers),
        "tokens_per_paper": embedding_tokens // max(1, len(papers)),
        "total_tokens": embedding_tokens,
    }
    result["total"]["embedding_tokens"] = embedding_tokens

    # 2. LLM 排序（对每个用户）
    llm_ranking_tokens = 0
    for profile in user_profiles:
        # 每个用户排序：输入 = 论文摘要 + 用户画像，输出 = 排序结果
        user_text = json.dumps(profile.get("core_directions", {}), ensure_ascii=False)
        paper_text = " ".join([f"{p.get('title')} {p.get('abstract')}" for p in papers[:20]])  # 假设每次推 20 篇

        input_tokens = estimate_tokens(user_text + paper_text)
        output_tokens = estimate_tokens("排序结果约 20 篇论文的编号")

        llm_ranking_tokens += input_tokens + output_tokens

        log_token_usage(
            task_type="llm_ranking",
            model=llm_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            user_id=profile.get("user_id"),
            date=date,
        )

    result["breakdown"]["llm_ranking"] = {
        "users": len(user_profiles),
        "tokens_per_user": llm_ranking_tokens // max(1, len(user_profiles)),
        "total_tokens": llm_ranking_tokens,
    }

    # 3. 精读报告生成（假设 20% 的论文被选中生成报告）
    report_count = max(1, len(papers) // 5)
    report_tokens = 0
    for i in range(report_count):
        # 每篇报告：输入 = 论文全文摘要，输出 = 精读报告
        input_tokens = estimate_tokens(papers[i % len(papers)].get("abstract", "") * 5)  # 假设报告是摘要的 5 倍
        output_tokens = estimate_tokens("精读报告约 2000 字")

        report_tokens += input_tokens + output_tokens

        log_token_usage(
            task_type="llm_report",
            model=llm_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            date=date,
        )

    result["breakdown"]["llm_report"] = {
        "reports": report_count,
        "tokens_per_report": report_tokens // max(1, report_count),
        "total_tokens": report_tokens,
    }

    # 汇总
    result["total"]["llm_tokens"] = llm_ranking_tokens + report_tokens
    result["total"]["total_tokens"] = embedding_tokens + llm_ranking_tokens + report_tokens

    # 计算成本
    embedding_cost = embedding_tokens * MODEL_PRICES.get(result["embedding_model"], {}).get("input", 0) / 1000
    llm_cost_input = llm_ranking_tokens * MODEL_PRICES.get(llm_model, {}).get("input", 0) / 1000
    llm_cost_output = report_tokens * MODEL_PRICES.get(llm_model, {}).get("output", 0) / 1000
    result["total"]["estimated_cost_usd"] = embedding_cost + llm_cost_input + llm_cost_output

    return result


def compare_llm_models(
    date: str,
    papers: List[Dict],
    user_profiles: List[Dict],
    models: List[str] = None,
) -> List[Dict[str, Any]]:
    """对比不同 LLM 模型的 token 消耗"""
    if models is None:
        models = ["qwen3.5-plus", "qwen-plus", "qwen-max"]

    results = []
    for model in models:
        print(f"Benchmarking {model}...")
        result = benchmark_one_day(date, model, papers, user_profiles)
        results.append(result)

        # 清空日志以便下次测试
        if TOKEN_LOG_PATH.exists():
            TOKEN_LOG_PATH.unlink()

    return results


def main():
    parser = argparse.ArgumentParser(description="Token 花销统计工具")
    parser.add_argument("--start-date", type=str, default=None, help="开始日期 YYYYMMDD")
    parser.add_argument("--end-date", type=str, default=None, help="结束日期 YYYYMMDD")
    parser.add_argument("--group-by", type=str, default="date", choices=["date", "task_type", "model", "user_id"])
    parser.add_argument("--mode", type=str, default="stats", choices=["stats", "benchmark", "compare"])
    parser.add_argument("--llm-model", type=str, default="qwen3.5-plus", help="LLM 模型名称")
    parser.add_argument("--days", type=int, default=1, help="基准测试天数")
    args = parser.parse_args()

    # 连接数据库获取论文和用户数据
    conn = sqlite3.connect(DB_PATH)
    papers = conn.execute("SELECT title, abstract FROM papers").fetchall()
    papers = [{"title": p[0], "abstract": p[1] or ""} for p in papers]

    profiles = conn.execute("SELECT user_id, profile_json FROM profiles").fetchall()
    user_profiles = [{"user_id": p[0], **json.loads(p[1])} for p in profiles]
    conn.close()

    print(f"Loaded {len(papers)} papers, {len(user_profiles)} users")

    if args.mode == "stats" and args.start_date and args.end_date:
        # 统计已有日志
        stats = get_usage_stats(args.start_date, args.end_date, args.group_by)
        print(f"\n=== Token Usage Stats ({args.start_date} to {args.end_date}) ===\n")

        for key, s in sorted(stats.items()):
            print(f"[{key}]")
            print(f"  Embedding: {s['embedding_input']:,} tokens")
            print(f"  LLM: {s['llm_input'] + s['llm_output']:,} tokens")
            print(f"  Cost: ${s['cost']:.4f}")
            print(f"  Calls: {s['calls']}")
            print()

    elif args.mode == "benchmark":
        # 基准测试指定天数
        today = datetime.now()
        for i in range(args.days):
            test_date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            print(f"\n{'='*60}")
            print(f"Benchmarking {test_date} with {args.llm_model}...")
            print(f"{'='*60}\n")

            result = benchmark_one_day(test_date, args.llm_model, papers, user_profiles)

            print(f"Date: {result['date']}")
            print(f"LLM Model: {result['llm_model']}")
            print(f"Embedding Model: {result['embedding_model']}")
            print(f"\nBreakdown:")
            for task, data in result["breakdown"].items():
                print(f"  {task}:")
                print(f"    Count: {data.get('papers', data.get('users', data.get('reports', 0)))}")
                print(f"    Tokens: {data['total_tokens']:,} ({data['tokens_per_paper'] if 'tokens_per_paper' in data else data['tokens_per_user'] if 'tokens_per_user' in data else data['tokens_per_report']}/item)")
            print(f"\nTotal:")
            print(f"  Embedding Tokens: {result['total']['embedding_tokens']:,}")
            print(f"  LLM Tokens: {result['total']['llm_tokens']:,}")
            print(f"  Total Tokens: {result['total']['total_tokens']:,}")
            print(f"  Estimated Cost: ${result['total']['estimated_cost_usd']:.4f}")

    elif args.mode == "compare":
        # 对比不同模型
        print(f"\n{'='*60}")
        print(f"Comparing LLM models for {len(papers)} papers × {len(user_profiles)} users")
        print(f"{'='*60}\n")

        results = compare_llm_models(
            datetime.now().strftime("%Y-%m-%d"),
            papers,
            user_profiles,
        )

        print(f"\n{'='*60}")
        print("Model Comparison Summary")
        print(f"{'='*60}\n")

        for r in results:
            print(f"[{r['llm_model']}]")
            print(f"  Total Tokens: {r['total']['total_tokens']:,}")
            print(f"  LLM Tokens: {r['total']['llm_tokens']:,}")
            print(f"  Embedding Tokens: {r['total']['embedding_tokens']:,}")
            print(f"  Estimated Cost: ${r['total']['estimated_cost_usd']:.4f}")
            print()


if __name__ == "__main__":
    main()
