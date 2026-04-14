#!/usr/bin/env python3
"""
Test script for PDF reading report generation.

Usage:
    python scripts/test_pdf_reading.py <pdf_path>
"""

import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def test_pdf_reading_report(pdf_path: str):
    """Test reading report generation from a local PDF."""
    from agents.reading_agent.main import create_reading_report

    # Test with a local PDF file
    test_user_id = "user_rolea"
    test_paper = {
        "pdf_path": pdf_path,
        "title": os.path.splitext(os.path.basename(pdf_path))[0]
    }

    print(f"Testing PDF reading report generation...")
    print(f"PDF path: {pdf_path}")
    print(f"User ID: {test_user_id}")

    try:
        created_docs = create_reading_report(
            user_id=test_user_id,
            paper_ids=[],  # Empty - use papers directly
            papers=[test_paper],
            send_to_feishu=False,  # Don't send to Feishu for testing
        )

        if created_docs:
            print("\n=== SUCCESS ===")
            print(f"Created {len(created_docs)} reading report(s)")
            for i, doc in enumerate(created_docs, 1):
                print(f"\n[{i}] Paper: {doc['title']}")
                print(f"    Doc token: {doc.get('doc_token', 'N/A')}")
                print(f"    URL: {doc.get('url', 'N/A')}")
        else:
            print("\n=== WARNING ===")
            print("No documents created, check logs for details")

        return created_docs

    except Exception as e:
        print(f"\n=== ERROR ===")
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_pdf_reading.py <pdf_path>")
        print("\nExample:")
        print("  python test_pdf_reading.py test.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    test_pdf_reading_report(pdf_path)
