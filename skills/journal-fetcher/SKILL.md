# Journal Fetcher Skill

## 职责

期刊论文抓取：根据 `journals.yaml` 配置，抓取 Nature、Science、TPAMI 等期刊的最新论文。

## 支持的期刊源

| 期刊 | 数据源 | 更新频率 |
|------|--------|----------|
| TPAMI | IEEE Xplore API | 每周 |
| IJCV | Springer API | 每周 |
| Nature Machine Intelligence | Nature API / RSS | 每周 |
| Nature Computational Science | Nature API / RSS | 每周 |
| Nature Methods | Nature API / RSS | 每周 |
| Nature | Nature API / RSS | 每周 |
| Science | Science RSS | 每周 |
| Science Advances | Science RSS | 每周 |
| Nature Communications | Nature API / RSS | 每周 |

## API 端点

### Nature API

```
https://www.nature.com/search/search
```

### IEEE Xplore API

```
https://api.ieee.org/xplore/v2/articles
```

### Science RSS

```
https://www.science.org/action/showFeed?ui=0&type=etoc&feed=rss&jc=science
```

## API

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `fetch_nature_papers(journal_name, limit)` | 期刊名，限制 | papers list | 抓取 Nature 系列 |
| `fetch_ieee_papers(journal_name, limit)` | 期刊名，限制 | papers list | 抓取 IEEE 系列 |
| `fetch_science_papers(limit)` | 限制 | papers list | 抓取 Science 系列 |
| `fetch_by_config(config_key)` | 配置键 | papers list | 根据配置抓取 |

## 脚本实现 (scripts/fetch_journals.py)

```python
#!/usr/bin/env python3
"""
Journal Paper Fetcher
"""

import requests
import feedparser
from typing import List, Dict, Optional
import yaml
from pathlib import Path
from datetime import datetime, timedelta

# 配置文件
JOURNALS_CONFIG = Path(__file__).parent.parent / "config" / "journals.yaml"

def load_journals_config() -> Dict:
    """加载期刊配置"""
    if JOURNALS_CONFIG.exists():
        with open(JOURNALS_CONFIG, 'r') as f:
            return yaml.safe_load(f)
    return {}

def fetch_nature_papers(journal_name: str, limit: int = 50) -> List[Dict]:
    """
    抓取 Nature 系列期刊
    
    Args:
        journal_name: 期刊名（如 "nature", "nature-machine-intelligence"）
        limit: 最大数量
    
    Returns:
        论文列表
    """
    # Nature RSS 源
    rss_url = f"https://www.nature.com/{journal_name}/rss"
    
    try:
        feed = feedparser.parse(rss_url)
        papers = []
        
        for entry in feed.entries[:limit]:
            paper = {
                "title": entry.title,
                "authors": [],  # RSS 中可能没有作者
                "abstract": entry.get("description", ""),
                "journal": journal_name,
                "publish_date": entry.get("published", "")[:10] if entry.get("published") else "",
                "doi": entry.get("prism_doi", ""),
                "url": entry.get("link", ""),
                "source": "Nature RSS"
            }
            papers.append(paper)
        
        return papers
    except Exception as e:
        print(f"Error fetching Nature papers: {e}")
        return []

def fetch_science_papers(journal_name: str = "science", limit: int = 50) -> List[Dict]:
    """
    抓取 Science 系列期刊
    
    Args:
        journal_name: 期刊名
        limit: 最大数量
    
    Returns:
        论文列表
    """
    # Science RSS 源
    rss_url = f"https://www.science.org/action/showFeed?ui=0&type=etoc&feed=rss&jc={journal_name}"
    
    try:
        feed = feedparser.parse(rss_url)
        papers = []
        
        for entry in feed.entries[:limit]:
            paper = {
                "title": entry.title,
                "authors": [],
                "abstract": entry.get("description", ""),
                "journal": journal_name,
                "publish_date": entry.get("published", "")[:10] if entry.get("published") else "",
                "doi": entry.get("prism_doi", ""),
                "url": entry.get("link", ""),
                "source": "Science RSS"
            }
            papers.append(paper)
        
        return papers
    except Exception as e:
        print(f"Error fetching Science papers: {e}")
        return []

def fetch_ieee_papers(journal_name: str, api_key: str, limit: int = 50) -> List[Dict]:
    """
    抓取 IEEE 系列期刊
    
    Args:
        journal_name: 期刊名（如 "TPAMI"）
        api_key: IEEE API Key
        limit: 最大数量
    
    Returns:
        论文列表
    """
    # IEEE Xplore API
    base_url = "https://api.ieee.org/xplore/v2/articles"
    
    params = {
        "apikey": api_key,
        "format": "json",
        "max_records": limit,
        "sort_order": "desc",
        "sort_field": "publication_date"
    }
    
    # 期刊过滤器
    if journal_name == "TPAMI":
        params["publication_title"] = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
    
    try:
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        papers = []
        for article in data.get("articles", []):
            paper = {
                "title": article.get("title", ""),
                "authors": [a.get("full_name", "") for a in article.get("authors", [])],
                "abstract": article.get("abstract", ""),
                "journal": journal_name,
                "publish_date": article.get("publication_date", "")[:10],
                "doi": article.get("doi", ""),
                "url": article.get("pdf_url", ""),
                "source": "IEEE Xplore"
            }
            papers.append(paper)
        
        return papers
    except Exception as e:
        print(f"Error fetching IEEE papers: {e}")
        return []

def fetch_springer_papers(journal_name: str, limit: int = 50) -> List[Dict]:
    """
    抓取 Springer 系列期刊（如 IJCV）
    
    Args:
        journal_name: 期刊名
        limit: 最大数量
    
    Returns:
        论文列表
    """
    # Springer 没有公开 API，使用 RSS 或网站抓取
    # 这里以 IJCV 为例
    rss_url = "https://link.springer.com/feed/11263/articles"  # IJCV feed
    
    try:
        feed = feedparser.parse(rss_url)
        papers = []
        
        for entry in feed.entries[:limit]:
            paper = {
                "title": entry.title,
                "authors": [],
                "abstract": entry.get("summary", ""),
                "journal": journal_name,
                "publish_date": entry.get("published", "")[:10] if entry.get("published") else "",
                "doi": entry.get("prism_doi", ""),
                "url": entry.get("link", ""),
                "source": "Springer"
            }
            papers.append(paper)
        
        return papers
    except Exception as e:
        print(f"Error fetching Springer papers: {e}")
        return []

def fetch_by_config(config_key: str) -> List[Dict]:
    """
    根据配置抓取期刊论文
    
    Args:
        config_key: 配置键（如 "weekly_scan", "weekly_scan_top"）
    
    Returns:
        论文列表
    """
    config = load_journals_config()
    journals = config.get(config_key, [])
    
    all_papers = []
    
    for journal_config in journals:
        journal_name = journal_config.get("name", "")
        source = journal_config.get("source", "").lower()
        
        papers = []
        
        if "nature" in source:
            papers = fetch_nature_papers(journal_name.lower().replace(" ", "-"))
        elif "science" in source:
            papers = fetch_science_papers(journal_name.lower().replace(" ", "-"))
        elif "ieee" in source:
            # 需要 API Key
            api_key = ""  # 从环境变量获取
            papers = fetch_ieee_papers(journal_name, api_key)
        elif "springer" in source:
            papers = fetch_springer_papers(journal_name)
        
        # 应用过滤器
        filter_text = journal_config.get("filter", "")
        if filter_text:
            papers = filter_papers(papers, filter_text)
        
        all_papers.extend(papers)
    
    return all_papers

def filter_papers(papers: List[Dict], filter_text: str) -> List[Dict]:
    """
    根据过滤器筛选论文
    
    Args:
        papers: 论文列表
        filter_text: 过滤关键词
    
    Returns:
        筛选后的论文列表
    """
    if not filter_text:
        return papers
    
    # 简单的关键词过滤
    keywords = [k.strip().lower() for k in filter_text.replace("+", " ").split("|")]
    
    filtered = []
    for paper in papers:
        text = f"{paper['title']} {paper['abstract']}".lower()
        if any(kw in text for kw in keywords):
            filtered.append(paper)
    
    return filtered

if __name__ == "__main__":
    # 测试：抓取 Nature Machine Intelligence
    papers = fetch_nature_papers("nature-machine-intelligence", limit=5)
    print(f"Fetched {len(papers)} papers:")
    for paper in papers:
        print(f"  - {paper['title'][:50]}...")

```

## 注意事项

1. **API 认证**：IEEE Xplore 需要 API Key
2. **RSS 限制**：部分期刊 RSS 可能有访问限制
3. **更新频率**：建议每周抓取一次，避免频繁请求
4. **数据缓存**：抓取的论文应缓存，避免重复
