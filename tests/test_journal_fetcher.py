"""
Tests for journal RSS date handling.
"""

import importlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

journal_fetcher = importlib.import_module("skills.journal-fetcher.scripts.fetch_journal")


class FakeEntry(dict):
    """dict-like RSS entry with attribute access."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


def test_extract_entry_datetime_prefers_updated_when_published_missing():
    entry = FakeEntry(
        updated_parsed=time.strptime("2026-04-10", "%Y-%m-%d"),
    )

    published = journal_fetcher.extract_entry_datetime(entry)

    assert published.isoformat() == "2026-04-10T00:00:00"


def test_fetch_journal_papers_skips_entries_without_any_date(monkeypatch):
    dated_entry = FakeEntry(
        title="Fresh Nature Paper",
        summary="Summary",
        link="https://example.com/paper",
        updated_parsed=time.strptime("2026-04-12", "%Y-%m-%d"),
    )
    undated_entry = FakeEntry(
        title="Undated Nature Paper",
        summary="Summary",
        link="https://example.com/undated",
    )

    fake_feed = SimpleNamespace(entries=[dated_entry, undated_entry])
    monkeypatch.setattr(journal_fetcher.feedparser, "parse", lambda url: fake_feed)

    papers = journal_fetcher.fetch_journal_papers(journal="nature", limit=5, days=7)

    assert [paper["title"] for paper in papers] == ["Fresh Nature Paper"]
    assert papers[0]["publish_date"].startswith("2026-04-12")


def test_normalize_journal_name_handles_config_labels():
    assert journal_fetcher.normalize_journal_name("Nature Machine Intelligence") == "nature-machine-intelligence"
    assert journal_fetcher.normalize_journal_name("Science Advances") == "science-advances"
    assert journal_fetcher.normalize_journal_name("IJCV") == "ijcv"


def test_fetch_journal_papers_normalizes_human_readable_name(monkeypatch):
    dated_entry = FakeEntry(
        title="Fresh NMI Paper",
        summary="Summary",
        link="https://example.com/nmi",
        updated_parsed=time.strptime("2026-04-12", "%Y-%m-%d"),
    )

    fake_feed = SimpleNamespace(entries=[dated_entry])
    monkeypatch.setattr(journal_fetcher.feedparser, "parse", lambda url: fake_feed)

    papers = journal_fetcher.fetch_journal_papers(
        journal="Nature Machine Intelligence",
        limit=5,
        days=7,
    )

    assert [paper["title"] for paper in papers] == ["Fresh NMI Paper"]
    assert papers[0]["journal"] == "nature-machine-intelligence"


def test_fetch_ieee_journal_papers_requires_api_key(monkeypatch):
    monkeypatch.delenv("IEEE_API_KEY", raising=False)

    papers = journal_fetcher.fetch_ieee_journal_papers("tpami", limit=5, days=7)

    assert papers == []
