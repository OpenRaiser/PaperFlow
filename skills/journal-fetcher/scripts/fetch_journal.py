#!/usr/bin/env python3
"""
Journal Fetcher - 期刊论文抓取

支持期刊：
- Nature / Nature 子刊
- Science / Science 系列
- Cell
- PNAS
- The Lancet

数据源：使用各期刊的 RSS Feed 和公开 API
"""

import sys
import os
import json
import feedparser
import requests
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

JOURNAL_SOURCES = {
    "nature": {
        "name": "Nature",
        "kind": "rss",
        "rss_url": "https://www.nature.com/nature.rss",
    },
    "nature-biotech": {
        "name": "Nature Biotechnology",
        "kind": "rss",
        "rss_url": "https://www.nature.com/nbt.rss",
    },
    "nature-methods": {
        "name": "Nature Methods",
        "kind": "rss",
        "rss_url": "https://www.nature.com/nmeth.rss",
    },
    "nature-machine-intelligence": {
        "name": "Nature Machine Intelligence",
        "kind": "rss",
        "rss_url": "https://www.nature.com/natmachintell.rss",
    },
    "nature-computational-science": {
        "name": "Nature Computational Science",
        "kind": "rss",
        "rss_url": "https://www.nature.com/natcomputsci.rss",
    },
    "nature-communications": {
        "name": "Nature Communications",
        "kind": "rss",
        "rss_url": "https://www.nature.com/ncomms.rss",
    },
    "science": {
        "name": "Science",
        "kind": "rss",
        "rss_url": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
    },
    "science-advances": {
        "name": "Science Advances",
        "kind": "rss",
        "rss_url": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",
    },
    "cell": {
        "name": "Cell",
        "kind": "rss",
        "rss_url": "https://www.cell.com/cell/rss",
    },
    "pnas": {
        "name": "PNAS",
        "kind": "rss",
        "rss_url": "https://www.pnas.org/action/showFeed?type=header&feed=rss&jc=pnas",
    },
    "ijcv": {
        "name": "IJCV",
        "kind": "rss",
        "rss_url": "https://link.springer.com/search.rss?facet-journal-id=11263&facet-content-type=Article",
    },
    "tpami": {
        "name": "TPAMI",
        "kind": "ieee_api",
        "publication_title": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
    },
}

JOURNAL_ALIASES = {
    "nature": "nature",
    "naturebiotechnology": "nature-biotech",
    "naturebiotech": "nature-biotech",
    "naturemethods": "nature-methods",
    "naturemachineintelligence": "nature-machine-intelligence",
    "naturecomputationalscience": "nature-computational-science",
    "naturecommunications": "nature-communications",
    "science": "science",
    "scienceadvances": "science-advances",
    "cell": "cell",
    "pnas": "pnas",
    "ijcv": "ijcv",
    "tpami": "tpami",
}


def normalize_journal_name(name: str) -> Optional[str]:
    """Normalize human-readable journal names into supported keys."""
    condensed = re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())
    if not condensed:
        return None
    return JOURNAL_ALIASES.get(condensed)


def get_supported_journals() -> List[str]:
    """Return supported journal keys in stable order."""
    return list(JOURNAL_SOURCES.keys())


def fetch_ieee_journal_papers(
    journal_key: str,
    limit: int = 20,
    days: int = 7
) -> List[Dict[str, Any]]:
    """Fetch journal papers from IEEE Xplore when an API key is configured."""
    api_key = os.environ.get("IEEE_API_KEY", "").strip()
    source = JOURNAL_SOURCES[journal_key]
    if not api_key:
        print(f"Skipping {source['name']}: IEEE_API_KEY not configured")
        return []

    cutoff_date = datetime.now() - timedelta(days=days)
    params = {
        "apikey": api_key,
        "format": "json",
        "max_records": limit,
        "sort_order": "desc",
        "sort_field": "article_number",
        "publication_title": source["publication_title"],
    }

    try:
        response = requests.get("https://api.ieee.org/xplore/v2/articles", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching {source['name']} from IEEE Xplore ({type(e).__name__})")
        return []

    papers = []
    for article in data.get("articles", []):
        raw_date = str(article.get("publication_date", "")).strip()
        published = None
        for fmt in ("%d %B %Y", "%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                published = datetime.strptime(raw_date, fmt)
                break
            except ValueError:
                continue

        if published and published < cutoff_date:
            continue

        authors = []
        author_payload = article.get("authors", {})
        for author in author_payload.get("authors", []) if isinstance(author_payload, dict) else []:
            name = author.get("full_name") or author.get("name")
            if name:
                authors.append(name)

        papers.append({
            "title": article.get("title", "Unknown"),
            "abstract": article.get("abstract", ""),
            "authors": authors,
            "venue": source["name"],
            "journal": journal_key,
            "doi": article.get("doi", ""),
            "url": article.get("html_url") or article.get("pdf_url", ""),
            "publish_date": published.isoformat() if published else raw_date,
            "categories": [journal_key],
            "source": "ieee",
        })

    print(f"  Fetched {len(papers)} papers from {source['name']}")
    return papers


def extract_entry_datetime(entry) -> Optional[datetime]:
    """Extract the best available publication timestamp from an RSS entry."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime(*parsed[:6])
    return None


def fetch_journal_papers(
    journal: str = "nature",
    limit: int = 20,
    days: int = 7
) -> List[Dict[str, Any]]:
    """
    抓取指定期刊的论文

    Args:
        journal: 期刊名称 (nature, science, cell, pnas, etc.)
        limit: 返回数量限制
        days: 最近 N 天

    Returns:
        论文列表
    """
    journal_key = normalize_journal_name(journal) or str(journal or "").strip().lower()
    journal_info = JOURNAL_SOURCES.get(journal_key)
    if not journal_info:
        print(f"Unknown journal: {journal}")
        return []

    print(f"Fetching from {journal_info['name']}...")

    if journal_info.get("kind") == "ieee_api":
        return fetch_ieee_journal_papers(journal_key=journal_key, limit=limit, days=days)

    papers = []
    cutoff_date = datetime.now() - timedelta(days=days)

    try:
        # 解析 RSS Feed
        feed = feedparser.parse(journal_info["rss_url"])

        for entry in feed.entries[:limit]:
            # 提取论文信息
            published = extract_entry_datetime(entry)

            if published and published < cutoff_date:
                continue
            if published is None:
                # RSS 没有可靠时间字段时不把旧条目伪装成“今天”
                continue

            paper = {
                "title": entry.get('title', 'Unknown'),
                "abstract": entry.get('summary', entry.get('description', '')),
                "authors": extract_authors_from_rss(entry),
                "venue": journal_info["name"],
                "journal": journal_key,
                "doi": extract_doi(entry),
                "url": entry.get('link', ''),
                "publish_date": published.isoformat(),
                "categories": [journal_key],
                "source": "rss",
            }
            papers.append(paper)

    except Exception as e:
        print(f"Error fetching {journal_info['name']}: {e}")

    print(f"  Fetched {len(papers)} papers from {journal_info['name']}")
    return papers


def extract_authors_from_rss(entry) -> List[str]:
    """从 RSS 条目中提取作者"""
    authors = []

    # 尝试不同格式
    if hasattr(entry, 'author'):
        author_str = entry.author
        if author_str:
            # 分割多个作者
            for author in author_str.split(','):
                author = author.strip()
                if author:
                    authors.append(author)

    if hasattr(entry, 'authors'):
        for author in entry.authors:
            if isinstance(author, dict) and 'name' in author:
                authors.append(author['name'])
            elif isinstance(author, str):
                authors.append(author)

    return authors[:10]  # 限制作者数量


def extract_doi(entry) -> Optional[str]:
    """从 RSS 条目中提取 DOI"""
    # 尝试从链接中提取
    link = entry.get('link', '')
    if 'doi.org' in link:
        parts = link.split('doi.org/')
        if len(parts) > 1:
            return parts[1]

    # 尝试从 DOI 字段提取
    if hasattr(entry, 'doi'):
        return entry.doi

    return None


def fetch_by_date(
    start_date: str,
    end_date: str,
    journals: List[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    按日期范围获取论文（兼容 arxiv-fetcher 接口）

    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        journals: 期刊列表
        limit: 总数量限制

    Returns:
        论文列表
    """
    if journals is None:
        journals = ["nature", "science", "cell"]

    try:
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")
    except ValueError:
        start_dt = None
        end_dt = None

    window_days = 30
    if start_dt and end_dt:
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt
        window_days = max(1, (end_dt - start_dt).days + 1)

    all_papers = []
    limit_per_journal = max(limit // len(journals), 10)

    for journal in journals:
        papers = fetch_journal_papers(
            journal=journal,
            limit=limit_per_journal,
            days=window_days
        )
        all_papers.extend(papers)

    # 去重（基于 DOI 或 title）
    seen = set()
    unique_papers = []
    for paper in all_papers:
        key = paper.get('doi') or paper.get('title')
        if key and key not in seen:
            seen.add(key)
            unique_papers.append(paper)

    # 限制总数
    return unique_papers[:limit]


def get_recent_papers(
    days: int = 7,
    journals: List[str] = None,
    limit_per_journal: int = 20
) -> List[Dict[str, Any]]:
    """
    获取最近 N 天的论文

    Args:
        days: 最近 N 天
        journals: 期刊列表
        limit_per_journal: 每个期刊的数量限制

    Returns:
        论文列表
    """
    if journals is None:
        journals = ["nature", "science", "cell"]

    normalized_journals = []
    for journal in journals:
        normalized = normalize_journal_name(journal)
        if not normalized:
            print(f"Skipping unsupported journal source: {journal}")
            continue
        normalized_journals.append(normalized)

    all_papers = []

    for journal in normalized_journals:
        papers = fetch_journal_papers(
            journal=journal,
            limit=limit_per_journal,
            days=days
        )
        all_papers.extend(papers)

    # 去重
    seen = set()
    unique_papers = []
    for paper in all_papers:
        key = paper.get('doi') or paper.get('title')
        if key and key not in seen:
            seen.add(key)
            unique_papers.append(paper)

    return unique_papers


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Journal Fetcher")
    parser.add_argument("--journal", type=str, default="nature", help="Journal name")
    parser.add_argument("--limit", type=int, default=20, help="Max papers to fetch")
    parser.add_argument("--days", type=int, default=7, help="Recent N days")
    parser.add_argument("--output", type=str, help="Output JSON file path")

    args = parser.parse_args()

    print(f"Fetching papers from {args.journal}...")

    papers = fetch_journal_papers(
        journal=args.journal,
        limit=args.limit,
        days=args.days
    )

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(papers)} papers to {args.output}")
    else:
        print(f"\nFetched {len(papers)} papers:")
        for i, paper in enumerate(papers[:5]):
            print(f"\n{i+1}. {paper.get('title', 'Unknown')[:60]}")
            print(f"   DOI: {paper.get('doi', 'N/A')}")
            print(f"   URL: {paper.get('url', 'N/A')}")

        if len(papers) > 5:
            print(f"\n... and {len(papers) - 5} more")
