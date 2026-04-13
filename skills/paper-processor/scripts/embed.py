#!/usr/bin/env python3
"""
Paper Processor: Text cleaning, keyword extraction, embedding generation
"""

import re
import hashlib
import json
from typing import List, Dict, Optional
from pathlib import Path

# OpenAI Embedding (optional)
try:
    from openai import OpenAI
    client = OpenAI()
    HAS_OPENAI = True
except ImportError:
    client = None
    HAS_OPENAI = False

# Local Embedding Model (optional)
try:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('BAAI/bge-large-zh')
    HAS_LOCAL_MODEL = True
except ImportError:
    model = None
    HAS_LOCAL_MODEL = False

# Stop words
STOP_WORDS = set([
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "can", "this", "that",
    "these", "those", "it", "its", "as", "we", "you", "they", "our", "their"
])

# Domain keywords
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
    "cs.LG": [
        "machine learning", "deep learning", "neural network", "training",
        "optimization", "gradient", "loss", "accuracy", "prediction"
    ],
    "cs.CV": [
        "computer vision", "image", "visual", "detection", "segmentation",
        "recognition", "classification", "convolutional"
    ],
    "cs.CL": [
        "natural language", "language model", "nlp", "text", "sentence",
        "translation", "generation", "understanding"
    ],
}


def clean_abstract(abstract_text: str) -> str:
    """
    Clean abstract text

    Args:
        abstract_text: Raw abstract

    Returns:
        Cleaned abstract
    """
    text = abstract_text

    # Remove LaTeX formulas
    text = re.sub(r'\$[^$]+\$', '[FORMULA]', text)
    text = re.sub(r'\\\[.*?\\\]', '[FORMULA]', text, flags=re.DOTALL)
    text = re.sub(r'\\begin\{.*?\}.*?\\end\{.*?\}', '[FORMULA]', text, flags=re.DOTALL)

    # Remove citation markers
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\(\d+\)', '', text)

    # Compress whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove special characters
    text = re.sub(r'[^\w\s.,;:!?()\-\']', '', text)

    # Truncate if too long
    if len(text) > 5000:
        text = text[:4997] + "..."

    return text.strip()


def extract_keywords(text: str, top_k: int = 5) -> List[str]:
    """
    Extract keywords

    Args:
        text: Text to extract from
        top_k: Number of keywords to return

    Returns:
        List of keywords
    """
    # Tokenize
    words = re.findall(r'\b\w+\b', text.lower())

    # Remove stop words and short words
    words = [w for w in words if w not in STOP_WORDS and len(w) > 3]

    # Calculate word frequency
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1

    # Match domain keywords
    all_keywords = set()
    for keywords in DOMAIN_KEYWORDS.values():
        all_keywords.update(keywords)

    matched = []
    for keyword in all_keywords:
        if keyword in text.lower():
            matched.append(keyword)

    # Sort by frequency
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

    # Combine results
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
    Generate embedding

    Args:
        text: Text to embed
        model_name: Model name

    Returns:
        Embedding vector
    """
    # Check cache
    cache_dir = Path(__file__).parent.parent.parent / "data" / "embeddings_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    text_hash = hashlib.sha256(text.encode()).hexdigest()
    cache_file = cache_dir / f"{text_hash}.json"

    if cache_file.exists():
        with open(cache_file, 'r') as f:
            cached = json.load(f)
            if cached.get("model") == model_name:
                return cached["embedding"]

    # Use OpenAI
    if model_name.startswith("text-embedding") and HAS_OPENAI and client:
        response = client.embeddings.create(
            input=text,
            model=model_name
        )
        embedding = response.data[0].embedding

        # Cache
        with open(cache_file, 'w') as f:
            json.dump({
                "text_hash": text_hash,
                "embedding": embedding,
                "model": model_name,
                "created_at": str(__import__("datetime").datetime.now())
            }, f)

        return embedding

    # Use local model
    if HAS_LOCAL_MODEL and model and model_name in ["bge-large-zh", "m3e-base"]:
        embedding = model.encode(text).tolist()

        # Cache
        with open(cache_file, 'w') as f:
            json.dump({
                "text_hash": text_hash,
                "embedding": embedding,
                "model": model_name,
                "created_at": str(__import__("datetime").datetime.now())
            }, f)

        return embedding

    # Fallback: return zero vector
    return [0.0] * 768


def process_paper(paper: Dict) -> Dict:
    """
    Process a paper completely

    Args:
        paper: Paper dictionary

    Returns:
        Processed paper dictionary
    """
    # Clean abstract
    paper["cleaned_abstract"] = clean_abstract(paper.get("abstract", ""))

    # Extract keywords
    paper["keywords"] = extract_keywords(paper["cleaned_abstract"], top_k=5)

    # Generate embedding
    paper["embedding"] = generate_embedding(paper["cleaned_abstract"])
    paper["embedding_model"] = "text-embedding-3-small"

    return paper


def deduplicate_papers(papers: List[Dict]) -> List[Dict]:
    """
    Deduplicate papers

    Args:
        papers: List of papers

    Returns:
        Deduplicated list
    """
    seen = set()
    unique = []

    for paper in papers:
        # Priority: arxiv_id > doi > title
        if paper.get("arxiv_id"):
            key = f"arxiv:{paper['arxiv_id']}"
        elif paper.get("doi"):
            key = f"doi:{paper['doi']}"
        else:
            key = f"title:{paper.get('title', '')}"

        if key not in seen:
            seen.add(key)
            unique.append(paper)

    return unique


if __name__ == "__main__":
    # Test
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
