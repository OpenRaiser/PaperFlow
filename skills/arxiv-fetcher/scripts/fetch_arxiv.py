#!/usr/bin/env python3
"""
ArXiv Paper Fetcher
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
import urllib.parse

ARXIV_API_URL = "https://export.arxiv.org/api/query"

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

def fetch_by_date(
    start_date: str,
    end_date: str,
    categories: List[str] = None,
    limit: int = 100,
    max_retries: int = 3
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

    # 直接构建完整 URL，避免 requests 参数编码问题
    encoded_query = urllib.parse.quote(search_query, safe='')
    url = f"{ARXIV_API_URL}?search_query={encoded_query}&start=0&max_results={limit}&sortBy=submittedDate&sortOrder=descending"

    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries}...")
            response = requests.get(url, timeout=60)
            if response.status_code == 429:
                wait_time = (attempt + 1) * 30  # 30s, 60s, 90s
                print(f"Rate limited (429), waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                continue
            response.raise_for_status()
            return parse_arxiv_xml(response.text)
        except requests.Timeout:
            if attempt < max_retries - 1:
                print(f"Request timeout, retrying...")
                time.sleep(10)
            else:
                print(f"Error fetching from arXiv after {max_retries} attempts: timeout")
                return []
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                print(f"Request failed: {e}, retrying...")
                time.sleep(10)
            else:
                print(f"Error fetching from arXiv after {max_retries} attempts: {e}")
                return []

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

def get_paper_detail(arxiv_id: str) -> Optional[Dict]:
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

    try:
        response = requests.get(ARXIV_API_URL, params=params, timeout=30)
        response.raise_for_status()
        papers = parse_arxiv_xml(response.text)
        return papers[0] if papers else None
    except requests.RequestException as e:
        print(f"Error fetching paper detail: {e}")
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
