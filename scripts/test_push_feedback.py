#!/usr/bin/env python3
"""
Manual helper for exercising the daily-push + feedback flow.
"""

import importlib
import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

daily_push_agent = importlib.import_module("agents.daily-push-agent.main")
feedback_agent = importlib.import_module("agents.feedback-agent.main")
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")


def run_feedback_flow(
    user_id: str = "user_001",
    feishu_user_id: str | None = None,
    send_to_feishu: bool = False,
) -> None:
    print("=" * 60)
    print("Test: Daily Push + Feedback flow")
    print("=" * 60)
    print()

    print("[1] Running daily push...")
    daily_push_agent.daily_push(
        user_id=user_id,
        days=1,
        arxiv_categories=["cs.AI", "cs.LG", "cs.CV"],
        limit_per_source=10,
        output_file="test_push_output.txt",
        send_to_feishu=send_to_feishu,
    )

    print()
    print("[2] Simulating feedback replies...")
    test_replies = ["1 2 4 6 8", "1-3 5 7", "1,2,4,6"]

    for index, reply in enumerate(test_replies, start=1):
        test_papers = [
            {"id": paper_index + 1, "arxiv_id": f"2401.{paper_index:03d}", "title": f"Test Paper {paper_index + 1}"}
            for paper_index in range(10)
        ]
        result = feedback_agent.process_feedback(
            user_id=user_id,
            push_id=f"test_push_{index}",
            reply=reply,
            papers=test_papers,
            feishu_user_id=feishu_user_id if send_to_feishu else None,
            send_to_feishu=send_to_feishu,
        )
        print(f"Reply {index}: {reply!r}")
        print(f"  selected={result.get('selected_count', 0)}")
        print(f"  skipped={result.get('skipped_count', 0)}")
        print(f"  reports={result.get('reading_reports_created', 0)}")

    print()
    print("[3] Checking stored profile...")
    profile = db_ops.get_profile(user_id)
    if not profile:
        print("[ERROR] Profile not found")
        return

    print(f"version={profile.get('version', 'unknown')}")
    print(f"reading_history={len(profile.get('reading_history', []))}")
    print(f"author_heat={len(profile.get('author_heat', {}))}")
    print(f"institution_heat={len(profile.get('institution_heat', {}))}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manual Daily Push + Feedback flow helper")
    parser.add_argument("--user-id", type=str, default="user_001", help="User ID")
    parser.add_argument("--feishu-user-id", type=str, help="Feishu user ID")
    parser.add_argument("--send-feishu", action="store_true", help="Send messages to Feishu")
    args = parser.parse_args()

    run_feedback_flow(
        user_id=args.user_id,
        feishu_user_id=args.feishu_user_id,
        send_to_feishu=args.send_feishu,
    )
