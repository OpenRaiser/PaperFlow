# Paper Processor Skill

## 职责

论文处理：摘要文本清洗、关键词提取、Embedding 向量生成。

## API

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `clean_abstract(abstract_text)` | 摘要文本 | cleaned_text | 清洗摘要 |
| `extract_keywords(text, top_k)` | 文本，数量 | keywords list | 提取关键词 |
| `generate_embedding(text, model)` | 文本，模型名 | embedding vector | 生成 embedding |
| `process_paper(paper_dict)` | 论文字典 | processed_paper | 完整处理论文 |
| `deduplicate_papers(papers_list)` | 论文列表 | unique_papers | 去重处理 |

## 文本清洗规则

### 需要处理的问题

| 问题 | 处理方式 |
|------|----------|
| 多余空白 | 压缩为单空格 |
| LaTeX 公式 | 移除或替换为 `[FORMULA]` |
| 引用标记 | 移除 `[1]`, `[2]` 等 |
| 特殊字符 | 移除或转义 |
| 过长的摘要 | 截断至 5000 字符 |

### 清洗示例

**输入：**
```
We present a novel approach  to   protein folding 
prediction...[formula: E=mc^2]... Our method 
achieves SOTA results [1][2][3].
```

**输出：**
```
We present a novel approach to protein folding prediction. Our method achieves SOTA results.
```

## 关键词提取

### 方法

使用 TF-IDF + 领域词典：

```python
# 领域词典示例
DOMAIN_KEYWORDS = {
    "cs.AI": ["artificial intelligence", "machine learning", "neural network", ...],
    "q-bio.BM": ["protein", "molecular", "structure", "folding", ...],
}
```

### 提取流程

1. 文本分词
2. 移除停用词
3. 计算 TF-IDF
4. 匹配领域词典
5. 返回 top_k 关键词

## Embedding 生成

### 支持的模型

| 模型 | 维度 | 说明 |
|------|------|------|
| `text-embedding-3-small` | 1536 | OpenAI 小型，快速便宜 |
| `text-embedding-3-large` | 3072 | OpenAI 大型，效果更好 |
| `bge-large-zh` | 1024 | 中文友好，本地部署 |
| `m3e-base` | 768 | 中文语义，本地部署 |

### Embedding 缓存

```python
# 缓存结构
{
    "text_hash": "sha256(text)",
    "embedding": [0.1, 0.2, ...],
    "model": "text-embedding-3-small",
    "created_at": "2026-04-08T10:00:00Z"
}
```

## 论文去重

### 去重策略

| 策略 | 说明 |
|------|------|
| arxiv_id 相同 | 同一篇论文 |
| doi 相同 | 同一篇论文 |
| title 相似度 > 0.95 | 可能是同一篇 |
| title + authors 完全相同 | 确定是同一篇 |

## 脚本实现 (scripts/embed.py)

```python
#!/usr/bin/env python3
"""
Paper Processor: Text cleaning, keyword extraction, embedding generation
"""

import re
import hashlib
import json
from typing import List, Dict, Optional
from pathlib import Path

# OpenAI Embedding (可选)
try:
    from openai import OpenAI
    client = OpenAI()
except ImportError:
    client = None

# 本地 Embedding 模型 (可选)
try:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('BAAI/bge-large-zh')
except ImportError:
    model = None

# 停用词表
STOP_WORDS = set([
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "can", "this", "that",
    "these", "those", "it", "its", "as", "we", "you", "they", "our", "their"
])

# 领域词典
DOMAIN_KEYWORDS = {
    "cs.AI": [
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "transformer", "attention", "generative",
        "reinforcement learning", "optimization", "training"
    ],
    "q-bio.BM": [
        "protein", "molecular", "structure", "folding", "binding",
        "enzyme", "sequence", "genome", "biomolecule", "drug"
    ],
}

def clean_abstract(abstract_text: str) -> str:
    """
    清洗摘要文本
    
    Args:
        abstract_text: 原始摘要
    
    Returns:
        清洗后的摘要
    """
    text = abstract_text
    
    # 移除 LaTeX 公式
    text = re.sub(r'\$[^$]+\$', '[FORMULA]', text)
    text = re.sub(r'\\\[.*?\\\]', '[FORMULA]', text, flags=re.DOTALL)
    text = re.sub(r'\\begin\{.*?\}.*?\\end\{.*?\}', '[FORMULA]', text, flags=re.DOTALL)
    
    # 移除引用标记
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\(\d+\)', '', text)
    
    # 压缩空白
    text = re.sub(r'\s+', ' ', text)
    
    # 移除特殊字符
    text = re.sub(r'[^\w\s.,;:!?()\-\']', '', text)
    
    # 截断
    if len(text) > 5000:
        text = text[:4997] + "..."
    
    return text.strip()

def extract_keywords(text: str, top_k: int = 5) -> List[str]:
    """
    提取关键词
    
    Args:
        text: 文本
        top_k: 返回数量
    
    Returns:
        关键词列表
    """
    # 分词
    words = re.findall(r'\b\w+\b', text.lower())
    
    # 移除停用词和短词
    words = [w for w in words if w not in STOP_WORDS and len(w) > 3]
    
    # 计算词频
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    # 匹配领域词典
    domain_keywords = []
    all_keywords = set()
    for category, keywords in DOMAIN_KEYWORDS.items():
        all_keywords.update(keywords)
    
    matched = []
    for keyword in all_keywords:
        if keyword in text.lower():
            matched.append(keyword)
    
    # 按词频排序
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    
    # 合并结果
    result = matched[:top_k]
    if len(result) < top_k:
        for word, _ in sorted_words:
            if word not in result:
                result.append(word)
            if len(result) >= top_k:
                break
    
    return result[:top_k]

def generate_embedding(text: str, model_name: str = "text-embedding-3-small") -> List[float]:
    """
    生成 Embedding
    
    Args:
        text: 文本
        model_name: 模型名称
    
    Returns:
        Embedding 向量
    """
    # 检查缓存
    cache_dir = Path(__file__).parent.parent / "data" / "embeddings_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    cache_file = cache_dir / f"{text_hash}.json"
    
    if cache_file.exists():
        with open(cache_file, 'r') as f:
            cached = json.load(f)
            if cached.get("model") == model_name:
                return cached["embedding"]
    
    # 使用 OpenAI
    if model_name.startswith("text-embedding") and client:
        response = client.embeddings.create(
            input=text,
            model=model_name
        )
        embedding = response.data[0].embedding
        
        # 缓存
        with open(cache_file, 'w') as f:
            json.dump({
                "text_hash": text_hash,
                "embedding": embedding,
                "model": model_name,
                "created_at": str(__import__("datetime").datetime.now())
            }, f)
        
        return embedding
    
    # 使用本地模型
    if model and model_name in ["bge-large-zh", "m3e-base"]:
        embedding = model.encode(text).tolist()
        
        # 缓存
        with open(cache_file, 'w') as f:
            json.dump({
                "text_hash": text_hash,
                "embedding": embedding,
                "model": model_name,
                "created_at": str(__import__("datetime").datetime.now())
            }, f)
        
        return embedding
    
    # 降级：返回空向量
    return [0.0] * 768

def process_paper(paper: Dict) -> Dict:
    """
    完整处理论文
    
    Args:
        paper: 论文字典
    
    Returns:
        处理后的论文字典
    """
    # 清洗摘要
    paper["cleaned_abstract"] = clean_abstract(paper.get("abstract", ""))
    
    # 提取关键词
    paper["keywords"] = extract_keywords(paper["cleaned_abstract"], top_k=5)
    
    # 生成 embedding
    paper["embedding"] = generate_embedding(paper["cleaned_abstract"])
    paper["embedding_model"] = "text-embedding-3-small"
    
    return paper

def deduplicate_papers(papers: List[Dict]) -> List[Dict]:
    """
    去重论文列表
    
    Args:
        papers: 论文列表
    
    Returns:
        去重后的论文列表
    """
    seen = set()
    unique = []
    
    for paper in papers:
        # 优先使用 arxiv_id
        if paper.get("arxiv_id"):
            key = f"arxiv:{paper['arxiv_id']}"
        elif paper.get("doi"):
            key = f"doi:{paper['doi']}"
        else:
            # 使用 title + authors 作为 key
            key = f"title:{paper.get('title', '')}"
        
        if key not in seen:
            seen.add(key)
            unique.append(paper)
    
    return unique

if __name__ == "__main__":
    # 测试
    test_abstract = """
    We present a novel approach to protein folding prediction using 
    deep learning. Our method achieves state-of-the-art results on 
    multiple benchmarks [1][2][3].
    """
    
    cleaned = clean_abstract(test_abstract)
    print(f"Cleaned: {cleaned}")
    
    keywords = extract_keywords(cleaned, top_k=5)
    print(f"Keywords: {keywords}")
    
    embedding = generate_embedding(cleaned)
    print(f"Embedding dimension: {len(embedding)}")

```

## 注意事项

1. **缓存机制**：Embedding 生成后缓存，避免重复调用 API
2. **降级策略**：API 不可用时使用本地模型或返回空向量
3. **批量处理**：支持批量处理论文，提高效率
4. **错误处理**：文本处理失败时返回原始文本
