"""
Tests for journal RSS date handling.
"""

import importlib
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


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


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 4, 15, tzinfo=tz)


@pytest.fixture(autouse=True)
def fixed_fetch_window(monkeypatch):
    monkeypatch.setattr(journal_fetcher, "datetime", FixedDateTime)


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


def test_fetch_journal_papers_filters_non_research_entries(monkeypatch):
    correction_entry = FakeEntry(
        title="Author Correction: Something Important",
        summary="Correction summary",
        link="https://www.nature.com/articles/example-correction",
        updated_parsed=time.strptime("2026-04-12", "%Y-%m-%d"),
    )
    research_entry = FakeEntry(
        title="A real research article",
        summary="Research summary",
        link="https://www.nature.com/articles/s41586-026-00001-1",
        updated_parsed=time.strptime("2026-04-12", "%Y-%m-%d"),
    )

    fake_feed = SimpleNamespace(entries=[correction_entry, research_entry])
    monkeypatch.setattr(journal_fetcher.feedparser, "parse", lambda url: fake_feed)
    monkeypatch.setattr(journal_fetcher, "_fetch_article_detail", lambda url: {})

    papers = journal_fetcher.fetch_journal_papers(journal="nature", limit=5, days=7)

    assert [paper["title"] for paper in papers] == ["A real research article"]


def test_fetch_journal_papers_enriches_sparse_rss_from_detail_page(monkeypatch):
    sparse_entry = FakeEntry(
        title="Sparse Nature Entry",
        summary="",
        link="https://www.nature.com/articles/s41586-026-00001-1",
        updated_parsed=time.strptime("2026-04-12", "%Y-%m-%d"),
    )

    fake_feed = SimpleNamespace(entries=[sparse_entry])
    monkeypatch.setattr(journal_fetcher.feedparser, "parse", lambda url: fake_feed)
    monkeypatch.setattr(
        journal_fetcher,
        "_fetch_article_detail",
        lambda url: {
            "abstract": "A richer abstract from the article detail page.",
            "authors": ["Alice", "Bob"],
            "doi": "10.1038/example",
            "pdf_url": "https://www.nature.com/articles/example.pdf",
        },
    )

    papers = journal_fetcher.fetch_journal_papers(journal="nature", limit=5, days=7)

    assert len(papers) == 1
    assert papers[0]["abstract"] == "A richer abstract from the article detail page."
    assert papers[0]["authors"] == ["Alice", "Bob"]
    assert papers[0]["doi"] == "10.1038/example"
    assert papers[0]["pdf_url"] == "https://www.nature.com/articles/example.pdf"


def test_fetch_journal_papers_prefers_detail_abstract_over_feed_metadata_prefix(monkeypatch):
    entry = FakeEntry(
        title="Nature Entry With RSS Shell",
        summary=(
            '<p>Nature, Published online: 12 April 2026; '
            '<a href="https://www.nature.com/articles/s41586-026-00001-1">doi:10.1038/s41586-026-00001-1</a>'
            "</p><p>The RSS teaser is shorter than the real abstract.</p>"
        ),
        link="https://www.nature.com/articles/s41586-026-00001-1",
        updated_parsed=time.strptime("2026-04-12", "%Y-%m-%d"),
    )

    fake_feed = SimpleNamespace(entries=[entry])
    monkeypatch.setattr(journal_fetcher.feedparser, "parse", lambda url: fake_feed)
    monkeypatch.setattr(
        journal_fetcher,
        "_fetch_article_detail",
        lambda url: {
            "abstract": "A fuller abstract recovered from the Nature detail page.",
            "authors": ["Alice"],
        },
    )

    papers = journal_fetcher.fetch_journal_papers(journal="nature", limit=5, days=7)

    assert len(papers) == 1
    assert papers[0]["abstract"] == "A fuller abstract recovered from the Nature detail page."


def test_parse_article_detail_html_extracts_meta_fields():
    html = """
    <html>
      <head>
        <meta name="citation_title" content="Detailed Paper Title">
        <meta name="citation_abstract" content="Detailed abstract from meta tags.">
        <meta name="citation_author" content="Alice">
        <meta name="citation_author" content="Bob">
        <meta name="citation_doi" content="10.1126/science.example">
        <meta name="citation_pdf_url" content="/doi/pdf/10.1126/science.example">
      </head>
    </html>
    """

    parsed = journal_fetcher._parse_article_detail_html(
        html,
        "https://www.science.org/doi/full/10.1126/science.example",
    )

    assert parsed["title"] == "Detailed Paper Title"
    assert parsed["abstract"] == "Detailed abstract from meta tags."
    assert parsed["authors"] == ["Alice", "Bob"]
    assert parsed["doi"] == "10.1126/science.example"
    assert parsed["pdf_url"] == "https://www.science.org/doi/pdf/10.1126/science.example"


def test_parse_article_detail_html_prefers_nature_download_pdf_button_over_meta_pdf_url():
    html = """
    <html>
      <head>
        <meta name="citation_pdf_url" content="https://www.nature.com/articles/s41467-026-71877-z.pdf">
      </head>
      <body>
        <a href="/articles/s41467-026-71877-z_reference.pdf" data-test="download-pdf">Download PDF</a>
      </body>
    </html>
    """

    parsed = journal_fetcher._parse_article_detail_html(
        html,
        "https://www.nature.com/articles/s41467-026-71877-z",
    )

    assert parsed["pdf_url"] == "https://www.nature.com/articles/s41467-026-71877-z_reference.pdf"


def test_parse_article_detail_html_falls_back_to_body_paragraphs_when_meta_abstract_missing():
    html = """
    <html>
      <body>
        <article>
          <p>Short intro.</p>
          <p>This study introduces a robust evaluation pipeline for multimodal scientific agents and reports the first large-scale benchmark across domains.</p>
          <p>Across three datasets, the proposed framework improves ranking quality and reduces redundant reading time for expert users.</p>
        </article>
      </body>
    </html>
    """

    parsed = journal_fetcher._parse_article_detail_html(
        html,
        "https://www.nature.com/articles/s41586-026-00001-1",
    )

    assert "robust evaluation pipeline" in parsed["abstract"]
    assert "improves ranking quality" in parsed["abstract"]


def test_parse_article_detail_html_extracts_nature_json_ld_description():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "mainEntity": {
              "headline": "Nature Research Paper",
              "description": "A JSON-LD abstract for a Nature paper that would otherwise be missed by generic meta parsing."
            }
          }
        </script>
      </head>
    </html>
    """

    parsed = journal_fetcher._parse_article_detail_html(
        html,
        "https://www.nature.com/articles/s41586-026-00002-2",
    )

    assert parsed["title"] == "Nature Research Paper"
    assert "JSON-LD abstract" in parsed["abstract"]


def test_parse_article_detail_html_extracts_nature_special_abstract_block():
    html = """
    <html>
      <head>
        <meta name="citation_title" content="Nature Abstract Section Example">
      </head>
      <body>
        <div class="c-article-body">
          <section aria-labelledby="Abs1" data-title="Abstract" lang="en">
            <div class="c-article-section" id="Abs1-section">
              <h2 class="c-article-section__title" id="Abs1">Abstract</h2>
              <div class="c-article-section__content" id="Abs1-content">
                <p>This abstract section explains how the proposed benchmark evaluates multimodal reasoning systems under realistic scientific reading constraints.</p>
                <p>It also summarizes the main experimental gains and deployment implications for downstream discovery workflows.</p>
              </div>
            </div>
          </section>
          <section data-title="Main">
            <div class="c-article-section__content" id="Sec1-content">
              <p>This main body paragraph should not replace the dedicated abstract when the abstract section is present on Nature article pages.</p>
            </div>
          </section>
        </div>
      </body>
    </html>
    """

    parsed = journal_fetcher._parse_article_detail_html(
        html,
        "https://www.nature.com/articles/s41586-026-00003-3",
    )

    assert parsed["title"] == "Nature Abstract Section Example"
    assert "proposed benchmark evaluates multimodal reasoning systems" in parsed["abstract"]
    assert "main body paragraph should not replace" not in parsed["abstract"]


def test_parse_article_detail_html_returns_source_page_sections_and_full_text():
    html = """
    <html>
      <body>
        <article>
          <section data-title="Abstract">
            <p>This abstract explains how the paper studies multimodal scientific reading with a source-page fallback that preserves structured evidence.</p>
          </section>
          <h2>Introduction</h2>
          <p>The core challenge is that many publisher pages expose enough body text to support structured reading reports even when a direct PDF is unavailable.</p>
          <h2>Method</h2>
          <p>We propose a source-page section extractor that groups paragraphs by headings and then feeds the resulting chunks into the same evidence retrieval pipeline.</p>
          <h2>Results</h2>
          <p>Results show that the fallback report keeps method and result details substantially richer than an abstract-only summary.</p>
        </article>
      </body>
    </html>
    """

    parsed = journal_fetcher._parse_article_detail_html(
        html,
        "https://www.nature.com/articles/s41586-026-00004-4",
    )

    source_page = parsed["metadata"]["source_page"]

    assert source_page["source_kind"] == "source_page"
    assert "source-page fallback" in source_page["abstract"]
    assert "method" in source_page["sections"]
    assert "groups paragraphs by headings" in source_page["sections"]["method"]
    assert "keeps method and result details" in source_page["sections"]["results"]
    assert "direct PDF is unavailable" in source_page["full_text"]


def test_parse_article_detail_html_preserves_long_source_page_abstract():
    long_paragraph = (
        "This abstract paragraph describes a source-page reading workflow with detailed motivation, "
        "method design, implementation choices, and experimental observations for multimodal scientific "
        "reading systems. "
    ) * 6
    second_paragraph = (
        "A second long paragraph explains benchmark setup, evaluation criteria, robustness checks, and "
        "observed improvements across multiple domains without relying on a PDF download step. "
    ) * 5

    html = f"""
    <html>
      <body>
        <article>
          <section data-title="Abstract">
            <p>{long_paragraph}</p>
            <p>{second_paragraph}</p>
          </section>
        </article>
      </body>
    </html>
    """

    parsed = journal_fetcher._parse_article_detail_html(
        html,
        "https://www.nature.com/articles/s41586-026-00004-4",
    )

    abstract = parsed["abstract"]
    assert len(abstract) > 1200
    assert "benchmark setup" in abstract
    assert not abstract.endswith("...")


def test_fetch_journal_papers_skips_nature_news_style_article_ids(monkeypatch):
    news_entry = FakeEntry(
        title="Interesting scientific development",
        summary="News style summary",
        link="https://www.nature.com/articles/d41586-026-00001-1",
        updated_parsed=time.strptime("2026-04-12", "%Y-%m-%d"),
    )

    fake_feed = SimpleNamespace(entries=[news_entry])
    monkeypatch.setattr(journal_fetcher.feedparser, "parse", lambda url: fake_feed)

    papers = journal_fetcher.fetch_journal_papers(journal="nature", limit=5, days=7)

    assert papers == []


def test_parse_article_detail_html_marks_nature_news_article_type_as_non_research():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "@type": "NewsArticle",
            "headline": "A news-style Nature page",
            "articleSection": "News & Views"
          }
        </script>
      </head>
    </html>
    """

    parsed = journal_fetcher._parse_article_detail_html(
        html,
        "https://www.nature.com/articles/s44222-026-00004-4",
    )

    assert parsed["article_type"] == "News & Views"
    assert journal_fetcher._looks_like_non_research_detail_page(
        parsed,
        "https://www.nature.com/articles/s44222-026-00004-4",
    )


def test_fetch_journal_papers_skips_non_research_detail_pages(monkeypatch):
    researchish_entry = FakeEntry(
        title="Interesting article title",
        summary="Summary",
        link="https://www.science.org/doi/full/10.1126/science.example",
        updated_parsed=time.strptime("2026-04-12", "%Y-%m-%d"),
    )

    fake_feed = SimpleNamespace(entries=[researchish_entry])
    monkeypatch.setattr(journal_fetcher.feedparser, "parse", lambda url: fake_feed)
    monkeypatch.setattr(journal_fetcher, "_fetch_article_detail", lambda url: {"_skip": True})

    papers = journal_fetcher.fetch_journal_papers(journal="science", limit=5, days=7)

    assert papers == []


def test_fetch_article_detail_uses_http_get(monkeypatch):
    captured = {}

    class FakeResponse:
        url = "https://www.nature.com/articles/s41586-026-00001-1"
        text = """
        <html>
          <head>
            <meta name="citation_title" content="Detailed Nature Paper">
            <meta name="citation_abstract" content="Recovered through the shared HTTP session helper.">
          </head>
        </html>
        """

    def fake_http_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(journal_fetcher, "_http_get", fake_http_get)

    detail = journal_fetcher._fetch_article_detail("https://www.nature.com/articles/s41586-026-00001-1")

    assert captured["url"] == "https://www.nature.com/articles/s41586-026-00001-1"
    assert captured["timeout"] == journal_fetcher.JOURNAL_REQUEST_TIMEOUT
    assert detail["title"] == "Detailed Nature Paper"
    assert "Recovered through the shared HTTP session helper." in detail["abstract"]


def test_reconstruct_openalex_abstract_restores_sentence_order():
    inverted_index = {
        "Self-supervised": [0],
        "methods": [5],
        "pose": [2],
        "3D": [1],
        "hand": [3],
        "help.": [6],
        "estimation": [4],
    }

    abstract = journal_fetcher._reconstruct_openalex_abstract(inverted_index)

    assert abstract == "Self-supervised 3D pose hand estimation methods help."


def test_fetch_article_detail_falls_back_to_scholarly_metadata_when_page_is_blocked(monkeypatch):
    def fail_http_get(url, **kwargs):
        raise RuntimeError("403 forbidden")

    monkeypatch.setattr(journal_fetcher, "_http_get", fail_http_get)
    monkeypatch.setattr(
        journal_fetcher,
        "_fetch_scholarly_metadata_fallback",
        lambda url_or_doi: {
            "title": "Recovered ACM Paper",
            "abstract": "Recovered abstract from OpenAlex/Crossref fallback.",
            "authors": ["Alice", "Bob"],
            "doi": "10.1145/example",
            "pdf_url": "https://dl.acm.org/doi/pdf/10.1145/example",
        },
    )

    detail = journal_fetcher._fetch_article_detail("https://doi.org/10.1145/example")

    assert detail["title"] == "Recovered ACM Paper"
    assert detail["abstract"] == "Recovered abstract from OpenAlex/Crossref fallback."
    assert detail["authors"] == ["Alice", "Bob"]
    assert detail["doi"] == "10.1145/example"
    assert detail["pdf_url"] == "https://dl.acm.org/doi/pdf/10.1145/example"


def test_fetch_article_detail_uses_openalex_landing_page_as_fulltext_fallback(monkeypatch):
    class FakeResponse:
        def __init__(self, url, text, content_type="text/html"):
            self.url = url
            self.text = text
            self.headers = {"Content-Type": content_type}

    def fake_http_get(url, **kwargs):
        if "doi.org" in url:
            raise RuntimeError("403 forbidden")
        if "authors.example.com" in url:
            return FakeResponse(
                "https://authors.example.com/paper",
                """
                <html>
                  <head>
                    <meta name="citation_title" content="Recovered ACM Paper">
                    <meta name="citation_pdf_url" content="https://authors.example.com/paper.pdf">
                  </head>
                  <body>
                    <article>
                      <section data-title="Abstract">
                        <p>Recovered full-text abstract from the author manuscript landing page.</p>
                      </section>
                      <h2>Method</h2>
                      <p>The author manuscript preserves a method section that can be reused as source-page fallback.</p>
                    </article>
                  </body>
                </html>
                """,
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(journal_fetcher, "_http_get", fake_http_get)
    monkeypatch.setattr(
        journal_fetcher,
        "_fetch_openalex_metadata",
        lambda doi: {
            "title": "Recovered ACM Paper",
            "abstract": "",
            "authors": ["Alice", "Bob"],
            "doi": "10.1145/example",
            "pdf_url": "",
            "landing_page_url": "https://authors.example.com/paper",
            "venue": "ACM Multimedia",
            "publish_date": "2026-04-16",
        },
    )
    monkeypatch.setattr(journal_fetcher, "_fetch_crossref_metadata", lambda doi: {})

    detail = journal_fetcher._fetch_article_detail("https://doi.org/10.1145/example")

    assert detail["title"] == "Recovered ACM Paper"
    assert detail["abstract"] == "Recovered full-text abstract from the author manuscript landing page."
    assert detail["pdf_url"] == "https://authors.example.com/paper.pdf"
    assert detail["metadata"]["source_page"]["source_url"] == "https://authors.example.com/paper"
    assert "method" in detail["metadata"]["source_page"]["sections"]
