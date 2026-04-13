#!/usr/bin/env python3
"""
Manual helper for exercising reading-report document creation.
"""

import importlib
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
reading_agent = importlib.import_module("agents.reading-agent.main")


def main() -> None:
    test_user_id = "user_rolea"
    test_papers = [
        {
            "id": 1,
            "arxiv_id": "2401.00101",
            "title": "Deep Learning for Natural Language Processing: A Survey",
            "authors": ["John Smith", "Jane Doe"],
            "institution": "MIT",
            "abstract": "Deep learning has revolutionized natural language processing.",
            "score": 0.85,
        },
        {
            "id": 2,
            "arxiv_id": "2401.00202",
            "title": "Efficient Training of Large Language Models",
            "authors": ["Alice Johnson", "Bob Williams"],
            "institution": "Stanford University",
            "abstract": "Training large language models requires significant computational resources.",
            "score": 0.72,
        },
    ]

    print("=" * 60)
    print("Reading Agent manual test")
    print("=" * 60)

    print("\n[Test 1] create_doc")
    try:
        result = feishu_reporter.create_doc(
            title="[Test] Reading Agent Document Creation",
            content="# Test Document\n\nThis is a test Feishu document.\n",
        )
        print("[SUCCESS] create_doc")
        print(f"  token={result.get('obj_token', 'N/A')}")
        print(f"  url={result.get('url', 'N/A')}")
    except Exception as exc:
        print(f"[FAILED] create_doc: {exc}")

    print("\n[Test 2] create_reading_report")
    try:
        created_docs = reading_agent.create_reading_report(
            user_id=test_user_id,
            paper_ids=[1, 2],
            papers=test_papers,
            send_to_feishu=True,
        )
        if not created_docs:
            print("[WARNING] No documents created")
            return

        print(f"[SUCCESS] Created {len(created_docs)} reading reports")
        for doc in created_docs:
            print(f"  - {doc['title']}")
            if doc.get("url"):
                print(f"    {doc['url']}")
    except Exception as exc:
        print(f"[FAILED] reading-agent: {exc}")
        raise


if __name__ == "__main__":
    main()
