"""RAG answer generation over the local PaperFlow Wiki."""

from __future__ import annotations

import importlib
import os
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional

from paperflow.providers import build_llm_provider


wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")


SYSTEM_PROMPT = """You are PaperFlow's private research wiki assistant.

Answer only from the provided wiki snippets. Cite every concrete claim with
[N], where N is the snippet number shown in the context. Keep citation markers
inline immediately after the supported claim, and do not invent references. If
the snippets do not contain enough evidence, say that the local wiki does not
have enough material yet. Do not expose internal section labels such as Q1/Q2
unless the user explicitly asks for report-section structure. Use concise
Chinese by default unless the user asks otherwise."""


def _answer_max_tokens() -> int:
    try:
        value = int(str(os.environ.get("PAPERFLOW_WIKI_ANSWER_MAX_TOKENS", "1800")).strip())
    except (TypeError, ValueError):
        value = 1800
    return max(512, min(4096, value))


def _looks_incomplete_answer(text: str) -> bool:
    content = str(text or "").strip()
    if not content:
        return True
    terminal = "。！？!?.）)]】」』》\"'"
    if content[-1] in terminal:
        return False
    if content.count("[") > content.count("]") or content.count("**") % 2:
        return True
    if len(content) < 320:
        return True
    return False


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
        "当前 LLM 不可用，PaperFlow 先返回本地 Wiki 证据片段（local wiki snippets）。",
        f"Provider error: {error}",
        "",
    ]
    for index, hit in enumerate(hits[:5], start=1):
        lines.append(f"[{index}] {hit.get('title')} ({hit.get('node_type')})")
        lines.append(_snippet(hit, max_chars=280))
        lines.append("")
    return "\n".join(lines).strip()


def _merge_hits(
    pinned_nodes: Iterable[Dict[str, Any]],
    retrieved_nodes: Iterable[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for node in [*list(pinned_nodes or []), *list(retrieved_nodes or [])]:
        node_id = str(node.get("node_id") or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        merged.append(node)
        if len(merged) >= max(1, int(limit)):
            break
    return merged


def _prepare_hits(
    user_id: str,
    question: str,
    limit: int,
    pinned_nodes: Optional[List[Dict[str, Any]]],
    allowed_node_ids: Optional[Iterable[str]] = None,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    embedding_error = None
    try:
        wiki_db.embed_nodes_for_user(user_id, limit=500)
    except Exception as exc:
        embedding_error = str(exc)
    retrieved = wiki_db.search_nodes(user_id, question, limit=max(limit, limit + len(pinned_nodes or [])))
    if allowed_node_ids is not None:
        allowed = {str(node_id) for node_id in allowed_node_ids if str(node_id or "").strip()}
        retrieved = [node for node in retrieved or [] if str(node.get("node_id") or "") in allowed]
    return _merge_hits(pinned_nodes or [], retrieved, limit), embedding_error


def _build_citations(user_id: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    citations_by_node = wiki_db.get_citations_for_nodes(user_id, [hit["node_id"] for hit in hits if hit.get("node_id")])
    citations = []
    for index, hit in enumerate(hits, start=1):
        metadata = hit.get("metadata") or {}
        display_node = hit
        section_title = ""
        if str(hit.get("node_type") or "") == "section" and metadata.get("parent_paper_id"):
            parent = wiki_db.get_node(user_id, str(metadata.get("parent_paper_id")))
            if parent:
                display_node = parent
                section_title = str(hit.get("title") or "")
        node_citations = citations_by_node.get(hit["node_id"], [])
        first = node_citations[0] if node_citations else {}
        display_metadata = dict(display_node.get("metadata") or {})
        if metadata.get("parent_paper_id"):
            display_metadata.setdefault("parent_paper_id", metadata.get("parent_paper_id"))
        if section_title:
            display_metadata["section_title"] = section_title
            display_metadata["evidence_node_id"] = hit["node_id"]
        citations.append(
            {
                "index": index,
                "node_id": display_node["node_id"],
                "title": display_node["title"],
                "node_type": display_node["node_type"],
                "excerpt": first.get("excerpt") or _snippet(hit, max_chars=260),
                "source_type": first.get("source"),
                "source_id": first.get("source_id"),
                "anchor": first.get("anchor"),
                "metadata": display_metadata,
            }
        )
    return citations


def _empty_answer(started: float) -> Dict[str, Any]:
    return {
        "text": (
            "本地 Wiki 还没有足够相关的材料。可以先对相关论文生成精读报告，"
            "或运行 `paperflow wiki backfill` 导入已有运行历史。"
        ),
        "citations": [],
        "elapsed_ms": int((time.time() - started) * 1000),
        "token_usage": {},
    }


def _token_usage(llm: Any, response: Any, embedding_error: Optional[str], llm_error: Optional[str]) -> Dict[str, Any]:
    return {
        "provider": getattr(llm, "name", "unknown"),
        "model": getattr(llm, "model", "unknown"),
        "prompt_tokens": response.prompt_tokens if response else 0,
        "completion_tokens": response.completion_tokens if response else 0,
        "embedding_error": embedding_error,
        "llm_error": llm_error,
    }


def answer_question(
    user_id: str,
    question: str,
    *,
    limit: int = 8,
    pinned_nodes: Optional[List[Dict[str, Any]]] = None,
    allowed_node_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Return an LLM answer with local wiki citations."""
    started = time.time()
    hits, embedding_error = _prepare_hits(user_id, question, limit, pinned_nodes, allowed_node_ids=allowed_node_ids)
    if not hits:
        return _empty_answer(started)

    prompt = _build_prompt(question, hits)
    llm = build_llm_provider()
    llm_error = None
    response = None
    try:
        response = llm.generate(prompt, system=SYSTEM_PROMPT, temperature=0.0, max_tokens=_answer_max_tokens())
        answer_text = response.text
    except Exception as exc:
        llm_error = str(exc)
        answer_text = _extractive_fallback(hits, llm_error)
    citations = _build_citations(user_id, hits)
    return {
        "text": answer_text,
        "citations": citations,
        "elapsed_ms": int((time.time() - started) * 1000),
        "token_usage": _token_usage(llm, response, embedding_error, llm_error),
    }


def answer_question_stream(
    user_id: str,
    question: str,
    *,
    limit: int = 8,
    pinned_nodes: Optional[List[Dict[str, Any]]] = None,
    allowed_node_ids: Optional[Iterable[str]] = None,
) -> Iterator[Dict[str, Any]]:
    """Yield answer events with local citations and provider-native chunks."""
    started = time.time()
    hits, embedding_error = _prepare_hits(user_id, question, limit, pinned_nodes, allowed_node_ids=allowed_node_ids)
    if not hits:
        result = _empty_answer(started)
        yield {"event": "meta", "data": {key: value for key, value in result.items() if key != "text"}}
        yield {"event": "chunk", "data": {"text": result["text"]}}
        yield {"event": "done", "data": result}
        return

    citations = _build_citations(user_id, hits)
    llm = build_llm_provider()
    prompt = _build_prompt(question, hits)
    llm_error = None
    text_parts: List[str] = []
    meta = {
        "citations": citations,
        "elapsed_ms": 0,
        "token_usage": _token_usage(llm, None, embedding_error, None),
        "streaming": {"provider": True, "transport": "sse"},
    }
    yield {"event": "meta", "data": meta}
    try:
        for chunk in llm.stream_generate(prompt, system=SYSTEM_PROMPT, temperature=0.0, max_tokens=_answer_max_tokens()):
            if not chunk:
                continue
            text_parts.append(chunk)
            yield {"event": "chunk", "data": {"text": chunk}}
    except Exception as exc:
        llm_error = str(exc)
        fallback = _extractive_fallback(hits, llm_error)
        text_parts = [fallback]
        yield {"event": "chunk", "data": {"text": fallback}}

    answer_text = "".join(text_parts)
    response = None
    if llm_error is None and _looks_incomplete_answer(answer_text):
        try:
            response = llm.generate(prompt, system=SYSTEM_PROMPT, temperature=0.0, max_tokens=_answer_max_tokens())
            if response.text and len(response.text.strip()) > len(answer_text.strip()):
                answer_text = response.text
        except Exception as exc:
            llm_error = f"incomplete stream fallback failed: {exc}"

    result = {
        "text": answer_text,
        "citations": citations,
        "elapsed_ms": int((time.time() - started) * 1000),
        "token_usage": _token_usage(llm, response, embedding_error, llm_error),
    }
    yield {"event": "done", "data": result}
