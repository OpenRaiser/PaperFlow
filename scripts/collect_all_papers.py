#!/usr/bin/env python3
"""
Collect Papers by Date Range - All Sources

从所有可用来源抓取指定日期范围内的论文：
- arXiv
- OpenReview
- CVF (CVPR/ICCV/ECCV)
- ECVA
- DBLP
- Journals (Nature/Science/Cell/PNAS/etc.)

使用方法:
    python scripts/collect_all_papers.py --start-date 20260301 --end-date 20260301
    python scripts/collect_all_papers.py --start-date 20260301 --end-date 20260420
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "arxiv-fetcher" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "openreview-fetcher" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "journal-fetcher" / "scripts"))

# 导入各个 fetcher
from fetch_arxiv import fetch_by_date as fetch_arxiv
from fetch_openreview import fetch_by_date as fetch_openreview
from fetch_journal import fetch_by_date as fetch_journal
# CVF/ECVA/DBLP 如果没有独立 fetcher，可以后续添加

DB_PATH = PROJECT_ROOT / "data" / "paperflow.db"

# arXiv 主要类别
ARXIV_CATEGORIES = [
    "cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE",
    "q-bio.BM", "q-bio.GN", "stat.ML", "physics.bio-ph", "quant-ph",
]

# OpenReview 主要领域
OPENREVIEW_DOMAINS = [
    "ICLR", "NeurIPS", "ICML", "ACL", "EMNLP", "CVPR", "ICCV", "ECCV"
]

# Journals
JOURNALS = [
    "nature", "nature-machine-intelligence", "nature-communications",
    "science", "cell", "pnas", "ijcv"
]


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def paper_exists(conn: sqlite3.Connection, paper_id: str, source: str) -> bool:
    """检查论文是否已存在"""
    if source == "arxiv":
        cursor = conn.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (paper_id,))
    elif source in ("cvf", "ecva", "dblp"):
        cursor = conn.execute("SELECT 1 FROM papers WHERE doi = ?", (paper_id,))
    else:
        cursor = conn.execute("SELECT 1 FROM papers WHERE doi = ? OR title = ?", (paper_id, paper_id))
    return cursor.fetchone() is not None


def normalize_paper(paper: Dict, source: str) -> Dict:
    """统一不同来源的论文格式"""
    return {
        "arxiv_id": paper.get("arxiv_id", ""),
        "doi": paper.get("doi", ""),
        "title": paper.get("title", "Unknown"),
        "abstract": paper.get("abstract", ""),
        "authors": ",".join(paper.get("authors", [])) if isinstance(paper.get("authors"), list) else str(paper.get("authors", "")),
        "categories": ",".join(paper.get("categories", [])) if isinstance(paper.get("categories"), list) else str(paper.get("categories", "")),
        "venue": paper.get("venue", source),
        "publish_date": paper.get("publish_date", "")[:10] if paper.get("publish_date") else "",
        "pdf_url": paper.get("pdf_url", paper.get("url", "")),
        "source": source,
    }


def save_paper(conn: sqlite3.Connection, paper: Dict) -> None:
    """保存单篇论文到数据库（适配当前表结构）"""
    # 当前表结构：id, arxiv_id, doi, title, authors, institution, abstract, venue, publish_date, embedding, embedding_model, fetched_at, pushed, push_date
    conn.execute("""
        INSERT OR REPLACE INTO papers
        (arxiv_id, doi, title, abstract, authors, institution, venue, publish_date, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paper.get("arxiv_id", ""),
        paper.get("doi", ""),
        paper.get("title", ""),
        paper.get("abstract", ""),
        paper.get("authors", ""),
        paper.get("venue", ""),  # institution 用 venue 填充
        paper.get("venue", ""),
        paper.get("publish_date", ""),
        datetime.now().isoformat(),
    ))
    conn.commit()


def collect_from_source(
    conn: sqlite3.Connection,
    source: str,
    start_date: str,
    end_date: str,
    limit: Optional[int],
    extra_params: Optional[Dict] = None,
) -> int:
    """从单个来源收集论文"""
    # 不限制数量，使用各 fetcher 的默认行为
    params = {"start_date": start_date, "end_date": end_date}

    # 只在用户明确指定 limit 时才传递
    if limit is not None and limit > 0:
        params["limit"] = limit
    # 否则让 fetcher 使用自己的默认值（通常是不限制或 fetcher 内部默认值）

    if extra_params:
        params.update(extra_params)

    print(f"\n  Fetching from {source}...")

    try:
        if source == "arxiv":
            # arXiv 不限制类别，设置较大的上限（arXiv API 单次最多 1000 篇）
            if "limit" not in params:
                params["limit"] = 1000
            papers = fetch_arxiv(categories=ARXIV_CATEGORIES, **params)
        elif source == "openreview":
            # OpenReview 不限制数量
            if "limit" not in params:
                params["limit"] = 1000
            papers = fetch_openreview(conferences=["iclr", "neurips", "icml", "acl", "emnlp", "cvpr"], **params)
        elif source == "journal":
            # Journals 不限制数量
            if "limit" not in params:
                params["limit"] = 500
            papers = fetch_journal(journals=JOURNALS, **params)
        else:
            print(f"    Unknown source: {source}")
            return 0

        if papers is None:
            papers = []

        print(f"    Fetched {len(papers)} papers")

        new_count = 0
        for paper in papers:
            normalized = normalize_paper(paper, source)
            paper_id = normalized.get("arxiv_id") or normalized.get("doi") or normalized.get("title")

            if not paper_exists(conn, paper_id, source):
                save_paper(conn, normalized)
                new_count += 1
                print(f"      + {paper_id}: {normalized['title'][:50]}...")
            else:
                print(f"      ~ {paper_id}: already exists")

        return new_count

    except Exception as e:
        print(f"    Error fetching from {source}: {e}")
        return 0


def collect_all_papers(
    start_date: str,
    end_date: str,
    sources: List[str] = None,
    limit_per_source: int = 200,
) -> int:
    """
    从所有来源收集论文

    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        sources: 来源列表
        limit_per_source: 每个来源的抓取数量限制

    Returns:
        新增论文数量
    """
    conn = init_db()

    before_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    print(f"Before: {before_count} papers in database")

    if sources is None:
        sources = ["arxiv", "openreview", "journal"]

    total_new = 0
    for source in sources:
        new_count = collect_from_source(
            conn=conn,
            source=source,
            start_date=start_date,
            end_date=end_date,
            limit=limit_per_source,
        )
        total_new += new_count
        print(f"  [{source}] Added {new_count} new papers")

    after_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    print(f"\nAfter: {after_count} papers in database")
    print(f"Total new papers added: {total_new}")

    conn.close()
    return total_new


def main():
    parser = argparse.ArgumentParser(description="Collect all papers by date range")
    parser.add_argument("--start-date", type=str, required=True, help="Start date YYYYMMDD")
    parser.add_argument("--end-date", type=str, required=True, help="End date YYYYMMDD")
    parser.add_argument("--sources", nargs="*", default=None, help="Paper sources (arxiv, openreview, journal)")
    parser.add_argument("--limit-per-source", type=int, default=None, help="Max papers per source (None for unlimited)")
    args = parser.parse_args()

    sources = args.sources or ["arxiv", "openreview", "journal"]

    new_count = collect_all_papers(
        start_date=args.start_date,
        end_date=args.end_date,
        sources=sources,
        limit_per_source=args.limit_per_source,
    )

    print(f"\n[OK] Collected {new_count} new papers from {args.start_date} to {args.end_date}")


if __name__ == "__main__":
    main()
