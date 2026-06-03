"""RAG answer generation over the local PaperFlow Wiki."""

from __future__ import annotations

import importlib
import time
from typing import Any, Dict, List

from paperflow.providers import build_llm_provider


wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")


SYSTEM_PROMPT = """You are PaperFlow's private research wiki assistant.

Answer only from the provided wiki snippets. Cite every concrete claim with
[N], where N is the snippet number. If the snippets do not contain enough
evidence, say that the local wiki does not have enough material yet.
Use concise Chinese by default unless the user asks otherwise."""


def _snippet(node: Dict[str, Any], max_chars: int = 700) -> str:
    body = str(node.get("body") or "").strip()
    if len(body) <= max_chars:
        return body
    head = body[: max_chars // 2].rstrip()
    tail = body[-max_chars // 2 :].lstrip()
    return f"{head}\n...\n{tail}"


def _build_prompt(question: str, hits: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for index, hit in enumerate(hits, start=1):
        metadata = hit.get("metadata") or {}
        source = metadata.get("parent_paper_id") or hit.get("node_id")
        blocks.append(
            "\n".join(
                [
                    f"[{index}] {hit.get('title')}",
                    f"node_id: {hit.get('node_id')}",
                    f"type: {hit.get('node_type')}",
                    f"source: {source}",
                    "content:",
                    _snippet(hit),
                ]
            )
        )
    return f"Question: {question}\n\nWiki snippets:\n\n" + "\n\n".join(blocks)


def _extractive_fallback(hits: List[Dict[str, Any]], error: str) -> str:
    lines = [
        "The configured LLM was not available, so PaperFlow returned local wiki snippets instead.",
        f"Provider error: {error}",
        "",
    ]
    for index, hit in enumerate(hits[:5], start=1):
        lines.append(f"[{index}] {hit.get('title')} ({hit.get('node_type')})")
        lines.append(_snippet(hit, max_chars=280))
        lines.append("")
    return "\n".join(lines).strip()


def answer_question(user_id: str, question: str, *, limit: int = 8) -> Dict[str, Any]:
    """Return an LLM answer with local wiki citations."""
    started = time.time()
    embedding_error = None
    try:
        wiki_db.embed_nodes_for_user(user_id, limit=500)
    except Exception as exc:
        embedding_error = str(exc)
    hits = wiki_db.search_nodes(user_id, question, limit=limit)
    if not hits:
        return {
            "text": (
                "The local wiki does not have enough relevant material yet. "
                "Run `paperflow read` for related papers, or run "
                "`paperflow wiki backfill` to import existing runtime history."
            ),
            "citations": [],
            "elapsed_ms": int((time.time() - started) * 1000),
            "token_usage": {},
        }

    prompt = _build_prompt(question, hits)
    llm = build_llm_provider()
    llm_error = None
    response = None
    try:
        response = llm.generate(prompt, system=SYSTEM_PROMPT, temperature=0.0, max_tokens=900)
        answer_text = response.text
    except Exception as exc:
        llm_error = str(exc)
        answer_text = _extractive_fallback(hits, llm_error)
    citations_by_node = wiki_db.get_citations_for_nodes(user_id, [hit["node_id"] for hit in hits])
    citations = []
    for index, hit in enumerate(hits, start=1):
        node_citations = citations_by_node.get(hit["node_id"], [])
        first = node_citations[0] if node_citations else {}
        citations.append(
            {
                "index": index,
                "node_id": hit["node_id"],
                "title": hit["title"],
                "node_type": hit["node_type"],
                "excerpt": first.get("excerpt") or _snippet(hit, max_chars=260),
                "source_type": first.get("source"),
                "source_id": first.get("source_id"),
                "anchor": first.get("anchor"),
                "metadata": hit.get("metadata") or {},
            }
        )
    return {
        "text": answer_text,
        "citations": citations,
        "elapsed_ms": int((time.time() - started) * 1000),
        "token_usage": {
            "provider": getattr(llm, "name", "unknown"),
            "model": getattr(llm, "model", "unknown"),
            "prompt_tokens": response.prompt_tokens if response else 0,
            "completion_tokens": response.completion_tokens if response else 0,
            "embedding_error": embedding_error,
            "llm_error": llm_error,
        },
    }
