#!/usr/bin/env python3
"""
Manual helper for exercising pdf-parser functions.
"""

import importlib
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

pdf_parser = importlib.import_module("skills.pdf-parser.scripts.parse_pdf")


def main() -> None:
    print("=" * 60)
    print("PDF Parser manual test")
    print("=" * 60)

    print(f"\nPyMuPDF available: {pdf_parser.HAS_PYMUPDF}")
    print(f"pdfplumber available: {pdf_parser.HAS_PDFPLUMBER}")

    sample_text = """
This paper presents a deep learning approach for natural language processing.
We use neural networks to process text data and build a language model.
Our method achieves state-of-the-art results on NLP tasks.
"""
    print("\n[1] infer_research_directions")
    print(pdf_parser.infer_research_directions(sample_text))

    sample_sections = """
Abstract
This is the abstract of the paper.

Introduction
This is the introduction section.

Method
This is the method section.

Results
This is the results section.

Conclusion
This is the conclusion.
"""
    print("\n[2] extract_sections")
    print(list(pdf_parser.extract_sections(sample_sections).keys()))

    sample_metadata = """
Deep Learning for NLP
John Smith and Jane Doe

Abstract
This paper presents a novel approach to natural language processing.
"""
    print("\n[3] extract_metadata")
    metadata = pdf_parser.extract_metadata(sample_metadata)
    print(f"title={metadata.get('title', 'N/A')}")
    print(f"authors={metadata.get('authors', 'N/A')}")
    print(f"abstract={metadata.get('abstract', 'N/A')[:50]}")


if __name__ == "__main__":
    main()
