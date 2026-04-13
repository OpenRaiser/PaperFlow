# OpenReview Fetcher Skill

## 职责

OpenReview 论文抓取：调用 OpenReview API 获取 ICLR、NeurIPS、ICML 等会议论文。

## API 端点

### OpenReview API Base URL

```
https://api.openreview.net
```

### 主要接口

| 接口 | 说明 |
|------|------|
| `/notes` | 获取论文列表 |
| `/notes/search` | 搜索论文 |
| `/edges/browse` | 浏览边信息（评分、决定） |

## API

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `fetch_conference_papers(venue_id, year)` | 会议 ID, 年份 | papers list | 抓取会议论文 |
| `fetch_accepted_papers(venue_id, year)` | 会议 ID, 年份 | papers list | 抓取录用论文 |
| `search_papers(query, venue_id)` | 查询，会议 ID | papers list | 搜索论文 |
| `get_paper_detail(note_id)` | note ID | paper dict | 获取论文详情 |

## 会议 ID 映射

```python
CONFERENCE_IDS = {
    "ICLR": "ICLR.cc",
    "NeurIPS": "NeurIPS.cc",
    "ICML": "ICML.cc",
    "ACL": "ACL.org",
    "EMNLP": "EMNLP.org",
    "CVPR": "CVPR.org",
    "ICCV": "ICCV.org",
    "ECCV": "ECCV.org",
}
```

## 脚本实现 (scripts/fetch_openreview.py)

```python
#!/usr/bin/env python3
"""
OpenReview Paper Fetcher
"""

import requests
from typing import List, Dict, Optional
import yaml
from pathlib import Path

OPENREVIEW_API = "https://api.openreview.net"

# 会议配置
CONFERENCES_CONFIG = Path(__file__).parent.parent / "config" / "conferences.yaml"

def load_conferences_config() -> Dict:
    """加载会议配置"""
    if CONFERENCES_CONFIG.exists():
        with open(CONFERENCES_CONFIG, 'r') as f:
            return yaml.safe_load(f)
    return {}

def fetch_conference_papers(venue_id: str, year: int, limit: int = 100) -> List[Dict]:
    """
    抓取会议论文
    
    Args:
        venue_id: 会议 ID (如 "ICLR.cc")
        year: 年份
        limit: 最大数量
    
    Returns:
        论文列表
    """
    # 构建查询
    params = {
        "content.venueid": f"{venue_id}/{year}/Conference",
        "limit": limit
    }
    
    try:
        response = requests.get(
            f"{OPENREVIEW_API}/notes",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        papers = []
        for note in data.get("notes", []):
            paper = parse_openreview_note(note)
            if paper:
                papers.append(paper)
        
        return papers
    except requests.RequestException as e:
        print(f"Error fetching from OpenReview: {e}")
        return []

def fetch_accepted_papers(venue_id: str, year: int) -> List[Dict]:
    """
    抓取录用论文（有决策的）
    
    Args:
        venue_id: 会议 ID
        year: 年份
    
    Returns:
        论文列表
    """
    # 先获取所有论文
    papers = fetch_conference_papers(venue_id, year, limit=1000)
    
    # 过滤录用的（有 decision 字段）
    accepted = []
    for paper in papers:
        if paper.get("decision") in ["Accept", "Poster", "Oral", "Spotlight"]:
            accepted.append(paper)
    
    return accepted

def parse_openreview_note(note: Dict) -> Optional[Dict]:
    """
    解析 OpenReview note
    
    Args:
        note: OpenReview note
    
    Returns:
        论文字典
    """
    content = note.get("content", {})
    
    return {
        "title": content.get("title", {}).get("value", ""),
        "authors": content.get("authors", {}).get("value", []),
        "abstract": content.get("abstract", {}).get("value", ""),
        "keywords": content.get("keywords", {}).get("value", []),
        "venue": content.get("venue", {}).get("value", ""),
        "decision": content.get("decision", {}).get("value", ""),
        "openreview_id": note.get("id"),
        "openreview_url": f"https://openreview.net/forum?id={note.get('id')}",
        "pdf_url": content.get("pdf", {}).get("value", ""),
        "year": content.get("year", {}).get("value", "")
    }

def search_papers(query: str, venue_id: str = None, year: int = None) -> List[Dict]:
    """
    搜索论文
    
    Args:
        query: 搜索查询
        venue_id: 会议 ID（可选）
        year: 年份（可选）
    
    Returns:
        论文列表
    """
    params = {
        "query": query,
        "limit": 100
    }
    
    if venue_id:
        params["content.venueid"] = venue_id
    if year:
        params["content.year"] = year
    
    try:
        response = requests.get(
            f"{OPENREVIEW_API}/notes/search",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        papers = []
        for note in data.get("notes", []):
            paper = parse_openreview_note(note)
            if paper:
                papers.append(paper)
        
        return papers
    except requests.RequestException as e:
        print(f"Error searching OpenReview: {e}")
        return []

def get_paper_detail(note_id: str) -> Optional[Dict]:
    """
    获取论文详情
    
    Args:
        note_id: OpenReview note ID
    
    Returns:
        论文详情
    """
    try:
        response = requests.get(
            f"{OPENREVIEW_API}/notes/{note_id}",
            timeout=30
        )
        response.raise_for_status()
        note = response.json().get("note")
        return parse_openreview_note(note) if note else None
    except requests.RequestException as e:
        print(f"Error fetching paper detail: {e}")
        return None

if __name__ == "__main__":
    # 测试：获取 ICLR 2026 录用论文
    papers = fetch_accepted_papers("ICLR.cc", 2026)
    print(f"Fetched {len(papers)} accepted papers:")
    for paper in papers[:5]:
        print(f"  - {paper['title'][:50]}...")

```

## 注意事项

1. **API 认证**：部分接口可能需要登录
2. **会议 ID**：不同会议 ID 格式可能不同
3. **决策信息**：不是所有会议都公开决策
4. **速率限制**：避免频繁请求
