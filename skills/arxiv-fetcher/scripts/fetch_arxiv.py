#!/usr/bin/env python3
"""
ArXiv Paper Fetcher
"""

import os
import re
import requests
import xml.etree.ElementTree as ET
from html import unescape
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
import urllib.parse

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_LIST_URL = "https://arxiv.org/list"
DEFAULT_REQUEST_TIMEOUT = float(os.environ.get("ARXIV_REQUEST_TIMEOUT", "12"))
DEFAULT_RETRY_SLEEP = float(os.environ.get("ARXIV_RETRY_SLEEP", "5"))
DEFAULT_MAX_RETRIES = int(os.environ.get("ARXIV_MAX_RETRIES", "1"))
DEFAULT_RATE_LIMIT_WAIT = float(os.environ.get("ARXIV_RATE_LIMIT_WAIT", "0"))
DEFAULT_REQUEST_HEADERS = {"User-Agent": "PaperFlow/0.1 ArxivFetcher"}

# arXiv 类别映射
CATEGORIES = {
    "cs.AI": "Artificial Intelligence",
    "cs.LG": "Machine Learning",
    "cs.CL": "Computation and Language",
    "cs.CV": "Computer Vision",
    "q-bio.BM": "Biomolecules",
    "q-bio.GN": "Genomics",
    "stat.ML": "Machine Learning",
}


def _fetch_arxiv_query(search_query: str, limit: int, max_retries: int = DEFAULT_MAX_RETRIES) -> List[Dict]:
    encoded_query = urllib.parse.quote(search_query, safe='')
    url = f"{ARXIV_API_URL}?search_query={encoded_query}&start=0&max_results={limit}&sortBy=submittedDate&sortOrder=descending"

    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries}...")
            response = requests.get(url, timeout=DEFAULT_REQUEST_TIMEOUT, headers=DEFAULT_REQUEST_HEADERS)
            if response.status_code == 429:
                wait_time = DEFAULT_RATE_LIMIT_WAIT * (attempt + 1)
                if wait_time <= 0 or attempt >= max_retries - 1:
                    print("Rate limited (429), skipping arXiv fetch for this query.")
                    return []
                print(f"Rate limited (429), waiting {wait_time:g}s before retry...")
                time.sleep(wait_time)
                continue
            response.raise_for_status()
            return parse_arxiv_xml(response.text) or []
        except requests.Timeout:
            if attempt < max_retries - 1:
                print("Request timeout, retrying...")
                time.sleep(DEFAULT_RETRY_SLEEP)
            else:
                print(f"Error fetching from arXiv after {max_retries} attempts: timeout")
                return []
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                print(f"Request failed: {e}, retrying...")
                time.sleep(DEFAULT_RETRY_SLEEP)
            else:
                print(f"Error fetching from arXiv after {max_retries} attempts: {e}")
                return []
    return []


def fetch_latest(
    categories: List[str] = None,
    limit: int = 100,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> List[Dict]:
    """Fetch latest arXiv papers without a submittedDate constraint."""
    if categories:
        search_query = " OR ".join([f"cat:{cat}" for cat in categories])
        if len(categories) > 1:
            search_query = f"({search_query})"
    else:
        search_query = "all:*"
    return _fetch_arxiv_query(search_query, limit, max_retries=max_retries)


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_arxiv_list_page(html: str, category: str, limit: int) -> List[Dict]:
    pairs = re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", html or "", flags=re.DOTALL | re.IGNORECASE)
    papers: List[Dict] = []
    for dt_html, dd_html in pairs:
        id_match = re.search(r"""href\s*=\s*["']/abs/([^"']+)["']""", dt_html, flags=re.IGNORECASE)
        if not id_match:
            continue
        arxiv_id = unescape(id_match.group(1)).strip()
        title_match = re.search(
            r"""<div\s+class=["']list-title[^"']*["']>\s*<span[^>]*>\s*Title:\s*</span>(.*?)</div>""",
            dd_html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        author_block = re.search(
            r"""<div\s+class=["']list-authors[^"']*["']>(.*?)</div>""",
            dd_html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        subjects_block = re.search(
            r"""<div\s+class=["']list-subjects[^"']*["']>(.*?)</div>""",
            dd_html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        authors_html = author_block.group(1) if author_block else ""
        authors = [
            _clean_html_text(match)
            for match in re.findall(r"<a[^>]*>(.*?)</a>", authors_html, flags=re.DOTALL | re.IGNORECASE)
        ]
        title = _clean_html_text(title_match.group(1) if title_match else "")
        if not title:
            continue
        subjects_text = _clean_html_text(subjects_block.group(1) if subjects_block else "")
        categories = re.findall(r"\(([a-z-]+(?:\.[A-Z]{2})?)\)", subjects_text)
        if category and category not in categories:
            categories.insert(0, category)
        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": [author for author in authors if author],
                "abstract": "",
                "categories": categories or [category],
                "publish_date": "",
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "paper_url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            }
        )
        if len(papers) >= limit:
            break
    return papers


def fetch_recent_list_page(category: str, limit: int = 100) -> List[Dict]:
    """Fetch recent papers from arxiv.org/list/<archive>/recent as an API fallback."""
    category = str(category or "").strip()
    if not category:
        return []
    archive = category.split(".", 1)[0]
    url = f"{ARXIV_LIST_URL}/{urllib.parse.quote(archive, safe='-')}/recent?skip=0&show=2000"
    try:
        print(f"Fetching arXiv recent list page for {category}...")
        response = requests.get(url, timeout=DEFAULT_REQUEST_TIMEOUT, headers=DEFAULT_REQUEST_HEADERS)
        response.raise_for_status()
        return _parse_arxiv_list_page(response.text, category, limit)
    except requests.RequestException as exc:
        print(f"Error fetching arXiv recent list page for {category}: {exc}")
        return []


def fetch_by_date(
    start_date: str,
    end_date: str,
    categories: List[str] = None,
    limit: int = 100,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> List[Dict]:
    """
    按日期范围抓取论文

    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        categories: 类别列表，如 ["cs.AI", "cs.LG"]
        limit: 最大返回数量
        max_retries: 最大重试次数

    Returns:
        论文列表
    """
    # 构建搜索查询（使用 URL 编码）
    if categories:
        cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
        # arXiv 日期格式：[YYYYMMDDHHMMSS TO YYYYMMDDHHMMSS]
        search_query = f"({cat_query}) AND submittedDate:[{start_date}000000 TO {end_date}235959]"
    else:
        search_query = f"submittedDate:[{start_date}000000 TO {end_date}235959]"

    return _fetch_arxiv_query(search_query, limit, max_retries=max_retries)

def parse_arxiv_xml(xml_content: str) -> List[Dict]:
    """
    解析 arXiv XML 响应

    Args:
        xml_content: XML 内容

    Returns:
        论文列表
    """
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom"
    }

    root = ET.fromstring(xml_content)
    papers = []

    for entry in root.findall("atom:entry", ns):
        paper = {
            "arxiv_id": extract_arxiv_id(entry, ns),
            "title": extract_text(entry, "atom:title", ns),
            "authors": extract_authors(entry, ns),
            "abstract": extract_text(entry, "atom:summary", ns),
            "categories": extract_categories(entry, ns),
            "publish_date": extract_date(entry, "atom:published", ns),
            "pdf_url": extract_pdf_url(entry, ns),
            "doi": extract_text(entry, "atom:doi", ns),
        }
        papers.append(paper)

    return papers

def extract_text(element: ET.Element, xpath: str, ns: dict) -> str:
    """提取文本内容"""
    elem = element.find(xpath, ns)
    if elem is not None and elem.text:
        return elem.text.strip()
    return ""

def extract_arxiv_id(element: ET.Element, ns: dict) -> str:
    """提取 arXiv ID"""
    id_elem = element.find("atom:id", ns)
    if id_elem is not None and id_elem.text:
        # 从 URL 中提取 arxiv_id
        # 例如：http://arxiv.org/abs/2404.12345
        url = id_elem.text.strip()
        return url.split("/")[-1]
    return ""

def extract_authors(element: ET.Element, ns: dict) -> List[str]:
    """提取作者列表"""
    authors = []
    for author in element.findall("atom:author", ns):
        name_elem = author.find("atom:name", ns)
        if name_elem is not None and name_elem.text:
            authors.append(name_elem.text.strip())
    return authors

def extract_categories(element: ET.Element, ns: dict) -> List[str]:
    """提取类别列表"""
    categories = []
    for category in element.findall("atom:category", ns):
        term = category.get("term")
        if term:
            categories.append(term)
    return categories

def extract_date(element: ET.Element, xpath: str, ns: dict) -> str:
    """提取日期"""
    date_elem = element.find(xpath, ns)
    if date_elem is not None and date_elem.text:
        return date_elem.text[:10]  # YYYY-MM-DD
    return ""

def extract_pdf_url(element: ET.Element, ns: dict) -> str:
    """提取 PDF URL"""
    for link in element.findall("atom:link", ns):
        if link.get("title") == "pdf":
            return link.get("href")
    arxiv_id = extract_arxiv_id(element, ns)
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

def get_paper_detail(
    arxiv_id: str,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    max_retries: int = 1,
) -> Optional[Dict]:
    """
    获取单篇论文详情

    Args:
        arxiv_id: arXiv ID (如 2404.12345)

    Returns:
        论文详情字典
    """
    search_query = f"id:{arxiv_id}"
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": 1
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(
                ARXIV_API_URL,
                params=params,
                timeout=timeout,
                headers=DEFAULT_REQUEST_HEADERS,
            )
            response.raise_for_status()
            papers = parse_arxiv_xml(response.text)
            return papers[0] if papers else None
        except requests.RequestException as e:
            if attempt >= max_retries - 1:
                print(f"Error fetching paper detail: {e}")
                return None
            time.sleep(min(2 * (attempt + 1), 5))

    return None

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch arXiv papers by date range")
    parser.add_argument("categories", nargs="*", default=["cs.AI", "cs.LG"],
                        help="arXiv categories (default: cs.AI,cs.LG)")
    parser.add_argument("--days", type=int, default=1,
                        help="Number of days to fetch (default: 1)")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max results (default: 50)")
    parser.add_argument("--start-date", type=str, default=None,
                        help="Start date YYYYMMDD (default: N days ago)")
    parser.add_argument("--end-date", type=str, default=None,
                        help="End date YYYYMMDD (default: today)")

    args = parser.parse_args()

    today = datetime.now()

    if args.end_date:
        end_date = args.end_date
    else:
        end_date = today.strftime("%Y%m%d")

    if args.start_date:
        start_date = args.start_date
    else:
        start_date = (today - timedelta(days=args.days)).strftime("%Y%m%d")

    print(f"Fetching papers from {start_date} to {end_date}...")
    print(f"Categories: {args.categories}")
    print(f"Max results: {args.limit}")

    papers = fetch_by_date(
        start_date=start_date,
        end_date=end_date,
        categories=args.categories,
        limit=args.limit
    )

    if papers is None:
        papers = []

    print(f"\nFetched {len(papers)} papers:")
    for i, paper in enumerate(papers):
        # 安全打印标题，处理特殊字符
        title = paper['title'].encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        print(f"  {i+1}. {paper['arxiv_id']}: {title[:60]}...")
