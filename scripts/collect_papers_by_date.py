#!/usr/bin/env python3
"""
Collect Papers by Date Range

从 arXiv 抓取指定日期范围内的论文，存入数据库论文池。

使用方法:
    python scripts/collect_papers_by_date.py --start-date 20260301 --end-date 20260301
    python scripts/collect_papers_by_date.py --start-date 20260301 --end-date 20260420
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "arxiv-fetcher" / "scripts"))

from fetch_arxiv import fetch_by_date
import importlib

DB_PATH = PROJECT_ROOT / "data" / "paperflow.db"

# arXiv 主要类别
ARXIV_CATEGORIES = [
    "cs.AI",  # Artificial Intelligence
    "cs.LG",  # Machine Learning
    "cs.CL",  # Computation and Language
    "cs.CV",  # Computer Vision
    "cs.NE",  # Neural and Evolutionary Computing
    "q-bio.BM",  # Biomolecules
    "q-bio.GN",  # Genomics
    "stat.ML",  # Machine Learning
    "physics.bio-ph",  # Biological Physics
    "quant-ph",  # Quantum Physics
]


def init_db() -> sqlite3.Connection:
    """初始化数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def paper_exists(conn: sqlite3.Connection, arxiv_id: str) -> bool:
    """检查论文是否已存在"""
    cursor = conn.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (arxiv_id,))
    return cursor.fetchone() is not None


def save_paper(conn: sqlite3.Connection, paper: Dict) -> None:
    """保存单篇论文到数据库"""
    conn.execute("""
        INSERT OR REPLACE INTO papers
        (arxiv_id, title, abstract, authors, categories, publish_date, pdf_url, doi, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paper.get("arxiv_id", ""),
        paper.get("title", ""),
        paper.get("abstract", ""),
        ",".join(paper.get("authors", [])),
        ",".join(paper.get("categories", [])),
        paper.get("publish_date", ""),
        paper.get("pdf_url", ""),
        paper.get("doi", ""),
        datetime.now().isoformat(),
    ))
    conn.commit()


def collect_papers(
    start_date: str,
    end_date: str,
    categories: List[str] = None,
    limit: int = 500,
) -> int:
    """
    收集指定日期范围内的论文

    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        categories: arXiv 类别列表
        limit: 最大抓取数量

    Returns:
        新增论文数量
    """
    conn = init_db()

    # 获取当前论文数量
    before_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    print(f"Before: {before_count} papers in database")

    # 抓取论文
    print(f"\nFetching papers from {start_date} to {end_date}...")
    print(f"Categories: {categories or 'all'}")
    print(f"Limit: {limit}")

    papers = fetch_by_date(
        start_date=start_date,
        end_date=end_date,
        categories=categories,
        limit=limit,
    )

    if papers is None:
        papers = []

    print(f"\nFetched {len(papers)} papers from arXiv")

    # 保存到数据库（去重）
    new_count = 0
    for paper in papers:
        if not paper_exists(conn, paper["arxiv_id"]):
            save_paper(conn, paper)
            new_count += 1
            print(f"  + {paper['arxiv_id']}: {paper['title'][:50]}...")
        else:
            print(f"  ~ {paper['arxiv_id']}: already exists")

    # 统计结果
    after_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    print(f"\nAfter: {after_count} papers in database")
    print(f"New papers added: {new_count}")

    conn.close()
    return new_count


def main():
    parser = argparse.ArgumentParser(description="Collect papers by date range")
    parser.add_argument("--start-date", type=str, required=True, help="Start date YYYYMMDD")
    parser.add_argument("--end-date", type=str, required=True, help="End date YYYYMMDD")
    parser.add_argument("--categories", nargs="*", default=None, help="arXiv categories")
    parser.add_argument("--limit", type=int, default=500, help="Max results")
    args = parser.parse_args()

    categories = args.categories or ARXIV_CATEGORIES

    new_count = collect_papers(
        start_date=args.start_date,
        end_date=args.end_date,
        categories=categories,
        limit=args.limit,
    )

    print(f"\n[OK] Collected {new_count} new papers from {args.start_date} to {args.end_date}")


if __name__ == "__main__":
    main()
