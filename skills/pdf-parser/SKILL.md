# PDF Parser Skill

## 职责

PDF 解析：冷启动时分析论文全文，提取标题、作者、摘要、关键词、方法、结果等结构化信息。

## API

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `parse_pdf(pdf_path)` | PDF 路径 | content dict | 解析 PDF 全文 |
| `extract_metadata(pdf_content)` | PDF 内容 | metadata dict | 提取元数据 |
| `extract_sections(pdf_content)` | PDF 内容 | sections dict | 提取章节内容 |
| `parse_paper_for_coldstart(pdf_path)` | PDF 路径 | analysis dict | 冷启动分析 |

## 输出结构

```python
{
    "title": "论文标题",
    "authors": ["作者 1", "作者 2"],
    "abstract": "摘要内容",
    "keywords": ["关键词 1", "关键词 2"],
    "sections": {
        "introduction": "引言内容",
        "method": "方法内容",
        "results": "结果内容",
        "conclusion": "结论内容"
    },
    "references": ["参考文献 1", ...],
    "full_text": "完整文本内容"
}
```

### 冷启动分析输出

```python
{
    "research_directions": [
        {"name": "GUI Agent", "confidence": 0.85},
        {"name": "Protein Folding", "confidence": 0.75}
    ],
    "methodology_preferences": {
        "data_driven": True,
        "systematic_work": True,
        "open_source": False,
        "bio_application": True
    },
    "inferred_topics": ["machine learning", "computational biology"],
    "taste_profile": {
        "preferred_work_type": ["empirical", "systematic"],
        "venue_preference": ["NeurIPS", "ICML"]
    }
}
```

## 技术方案

### 方案 1: PyMuPDF (推荐)

```python
import fitz  # PyMuPDF

def parse_pdf_with_pymupdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text
```

### 方案 2: pdfplumber

```python
import pdfplumber

def parse_pdf_with_pdfplumber(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text
```

### 方案 3: 调用外部 API

```python
# 使用 Claude API 解析 PDF
from anthropic import Anthropic

client = Anthropic()

def parse_pdf_with_claude(pdf_path):
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "data": base64.b64encode(pdf_data).decode()}},
                {"type": "text", "text": "Extract the title, authors, abstract, and key contributions from this paper."}
            ]
        }]
    )
    return response.content
```

## 脚本实现 (scripts/parse_pdf.py)

```python
#!/usr/bin/env python3
"""
PDF Parser: Extract structured information from research papers
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

# PyMuPDF
try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# pdfplumber
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# Claude API (可选)
try:
    from anthropic import Anthropic
    import base64
    client = Anthropic()
    HAS_CLAUDE = True
except ImportError:
    HAS_CLAUDE = False

# 常见章节标题模式
SECTION_PATTERNS = {
    "abstract": r"(?:^|\n)\s*(?:abstract|summary)\s*(?:$|\n)",
    "introduction": r"(?:^|\n)\s*(?:introduction|background|related work)\s*(?:$|\n)",
    "method": r"(?:^|\n)\s*(?:method|methodology|approach|our method|model)\s*(?:$|\n)",
    "results": r"(?:^|\n)\s*(?:results|experiments|evaluation|experiments and results)\s*(?:$|\n)",
    "discussion": r"(?:^|\n)\s*(?:discussion|analysis)\s*(?:$|\n)",
    "conclusion": r"(?:^|\n)\s*(?:conclusion|summary|future work)\s*(?:$|\n)",
    "references": r"(?:^|\n)\s*(?:references|bibliography)\s*(?:$|\n)"
}

# 研究领域关键词
RESEARCH_AREA_KEYWORDS = {
    "GUI Agent": ["gui", "interface", "agent", "automation", "ui", "interaction"],
    "Protein Folding": ["protein", "folding", "structure", "alphafold"],
    "Machine Learning": ["machine learning", "deep learning", "neural network"],
    "NLP": ["natural language", "language model", "nlp", "text"],
    "Computer Vision": ["computer vision", "image", "visual", "cv"],
    "Bioinformatics": ["bioinformatics", "genomics", "computational biology"],
}

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    从 PDF 提取文本
    
    Args:
        pdf_path: PDF 文件路径
    
    Returns:
        提取的文本
    """
    if HAS_PYMUPDF:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    
    if HAS_PDFPLUMBER:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        return text
    
    raise ImportError("No PDF library available. Install pymupdf or pdfplumber.")

def extract_metadata(text: str) -> Dict:
    """
    提取元数据（标题、作者等）
    
    Args:
        text: PDF 文本
    
    Returns:
        元数据字典
    """
    metadata = {
        "title": "",
        "authors": [],
        "abstract": ""
    }
    
    lines = text.split("\n")
    
    # 提取标题（通常在第一页顶部）
    for i, line in enumerate(lines[:20]):
        line = line.strip()
        if line and len(line) > 10:
            # 标题通常是第一个非空长行
            metadata["title"] = line
            # 作者通常在标题下方
            if i + 1 < len(lines):
                author_line = lines[i + 1].strip()
                if author_line:
                    # 分割作者
                    authors = re.split(r'[,\s]+and\s+|[,\s]+', author_line)
                    metadata["authors"] = [a.strip() for a in authors if a.strip()]
            break
    
    # 提取摘要
    abstract_match = re.search(r"(?:abstract|summary)[:\s]*(.+?)(?:\n\s*\n|\n\s*(?:introduction|1\.|background))", text, re.IGNORECASE | re.DOTALL)
    if abstract_match:
        metadata["abstract"] = abstract_match.group(1).strip()
    
    return metadata

def extract_sections(text: str) -> Dict[str, str]:
    """
    提取章节内容
    
    Args:
        text: PDF 文本
    
    Returns:
        章节字典
    """
    sections = {}
    
    for section_name, pattern in SECTION_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = match.end()
            # 找到下一节的开始
            next_section = None
            for other_name, other_pattern in SECTION_PATTERNS.items():
                if other_name != section_name:
                    other_match = re.search(other_pattern, text[start:], re.IGNORECASE)
                    if other_match:
                        if next_section is None or other_match.start() < next_section:
                            next_section = other_match.start()
            
            if next_section:
                sections[section_name] = text[start:start + next_section].strip()
            else:
                sections[section_name] = text[start:].strip()
    
    return sections

def infer_research_directions(text: str) -> List[Dict]:
    """
    推断研究方向
    
    Args:
        text: PDF 文本
    
    Returns:
        研究方向列表
    """
    text_lower = text.lower()
    directions = []
    
    for area, keywords in RESEARCH_AREA_KEYWORDS.items():
        match_count = sum(1 for kw in keywords if kw in text_lower)
        if match_count >= 2:  # 至少匹配 2 个关键词
            confidence = min(1.0, match_count / len(keywords))
            directions.append({
                "name": area,
                "confidence": confidence
            })
    
    # 按置信度排序
    directions.sort(key=lambda x: x["confidence"], reverse=True)
    return directions[:5]  # 返回 top 5

def infer_methodology_preferences(sections: Dict) -> Dict:
    """
    推断方法论偏好
    
    Args:
        sections: 章节内容
    
    Returns:
        偏好字典
    """
    method_text = sections.get("method", "").lower()
    results_text = sections.get("results", "").lower()
    
    preferences = {
        "data_driven": "dataset" in method_text or "data" in method_text,
        "systematic_work": "framework" in method_text or "system" in method_text,
        "open_source": "github" in text or "code" in text,
        "bio_application": "bio" in text.lower() or "protein" in text.lower()
    }
    
    return preferences

def parse_pdf(pdf_path: str) -> Dict:
    """
    解析 PDF
    
    Args:
        pdf_path: PDF 路径
    
    Returns:
        解析结果
    """
    # 提取文本
    text = extract_text_from_pdf(pdf_path)
    
    # 提取元数据
    metadata = extract_metadata(text)
    
    # 提取章节
    sections = extract_sections(text)
    
    # 推断研究方向
    directions = infer_research_directions(text)
    
    # 推断方法论偏好
    preferences = infer_methodology_preferences(sections)
    
    return {
        **metadata,
        "sections": sections,
        "inferred_directions": directions,
        "methodology_preferences": preferences,
        "full_text": text
    }

def parse_paper_for_coldstart(pdf_path: str) -> Dict:
    """
    为冷启动解析论文
    
    Args:
        pdf_path: PDF 路径
    
    Returns:
        冷启动分析结果
    """
    result = parse_pdf(pdf_path)
    
    return {
        "research_directions": result["inferred_directions"],
        "methodology_preferences": result["methodology_preferences"],
        "inferred_topics": result.get("keywords", []),
        "title": result["title"],
        "authors": result["authors"],
        "abstract": result["abstract"]
    }

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        result = parse_paper_for_coldstart(pdf_path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Usage: python parse_pdf.py <pdf_path>")

```

## 注意事项

1. **PDF 来源**：支持本地文件和 URL 下载
2. **文本质量**：扫描版 PDF 可能无法提取文本
3. **语言支持**：中英文论文均可处理
4. **错误处理**：解析失败时返回错误信息
