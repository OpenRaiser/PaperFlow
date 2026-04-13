# ArXiv Fetcher Skill

## 职责

arXiv 论文抓取：调用 arXiv API 获取论文元数据，解析 XML 响应。

## API 端点

### arXiv API Base URL

```
https://export.arxiv.org/api/query
```

### 请求参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `search_query` | 搜索查询 | `cat:cs.AI+AND+submittedDate:[20260407000000+TO+20260408000000]` |
| `start` | 起始位置 | `0` |
| `max_results` | 返回数量 | `100` |
| `sortBy` | 排序字段 | `submittedDate` |
| `sortOrder` | 排序顺序 | `descending` |

## API

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `fetch_by_date(start_date, end_date, categories, limit)` | 日期范围，类别，限制 | papers list | 按日期范围抓取 |
| `fetch_by_category(category, start, limit)` | 类别，起始，限制 | papers list | 按类别抓取 |
| `fetch_by_search_query(query, limit)` | 搜索查询，限制 | papers list | 自定义搜索 |
| `parse_arxiv_xml(xml_content)` | XML 内容 | papers list | 解析 XML 响应 |
| `get_paper_detail(arxiv_id)` | arxiv_id | paper dict | 获取单篇论文详情 |

## 论文数据结构

```python
{
    "arxiv_id": "2404.12345",
    "title": "Paper Title",
    "authors": ["Author One", "Author Two"],
    "abstract": "Paper abstract text...",
    "categories": ["cs.AI", "cs.LG"],
    "publish_date": "2026-04-08",
    "updated_date": "2026-04-08",
    "pdf_url": "https://arxiv.org/pdf/2404.12345.pdf",
    "doi": "10.48550/arXiv.2404.12345",
    "comment": "12 pages",
    "journal_ref": "",
    "institution": ""
}
```

## 脚本实现 (scripts/fetch_arxiv.py)

```python
#!/usr/bin/env python3
"""
ArXiv Paper Fetcher
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time

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
    limit: int = 100
) -> List[Dict]:
    """
    按日期范围抓取论文
    
    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        categories: 类别列表，如 ["cs.AI", "cs.LG"]
        limit: 最大返回数量
    
    Returns:
        论文列表
    """
    # 构建搜索查询
    if categories:
        cat_query = "+OR+".join([f"cat:{cat}" for cat in categories])
        search_query = f"({cat_query})+AND+submittedDate:[{start_date}000000+TO+{end_date}235959]"
    else:
        search_query = f"submittedDate:[{start_date}000000+TO+{end_date}235959]"
    
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": limit,
        "sortBy": "submittedDate",
        "sortOrder": "descending"
    }
    
    try:
        response = requests.get(ARXIV_API_URL, params=params, timeout=30)
        response.raise_for_status()
        return parse_arxiv_xml(response.text)
    except requests.RequestException as e:
        print(f"Error fetching from arXiv: {e}")
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
    # 测试：获取今天的论文
    today = datetime.now().strftime("%Y%m%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    
    papers = fetch_by_date(
        start_date=yesterday,
        end_date=today,
        categories=["cs.AI", "cs.LG"],
        limit=10
    )
    
    print(f"Fetched {len(papers)} papers:")
    for paper in papers:
        print(f"  - {paper['arxiv_id']}: {paper['title'][:50]}...")

```

## 注意事项

1. **API 限制**：arXiv API 限制每 5 秒最多 1 次请求，需要添加延迟
2. **日期格式**：submittedDate 使用格式 YYYYMMDDHHMMSS
3. **类别过滤**：支持多类别 OR 查询
4. **超时处理**：设置合理的超时时间（30 秒）
5. **重试机制**：网络错误时重试 3 次
