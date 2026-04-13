#!/usr/bin/env python3
"""
Simulate User Feedback for Testing

This script generates synthetic user feedback data for testing the
feedback processing and profile update algorithms.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# Sample paper data for simulation
SAMPLE_PAPERS = [
    {
        "id": 1,
        "arxiv_id": "2404.00001",
        "title": "GUI Agent with Visual Grounding",
        "keywords": ["gui agent", "visual grounding", "multimodal"],
        "category": "🔴"
    },
    {
        "id": 2,
        "arxiv_id": "2404.00002",
        "title": "Protein Folding with Deep Learning",
        "keywords": ["protein", "deep learning", "structure"],
        "category": "🔴"
    },
    {
        "id": 3,
        "arxiv_id": "2404.00003",
        "title": "Data-Native Scientific Discovery",
        "keywords": ["data-native", "scientific discovery"],
        "category": "🔴"
    },
    {
        "id": 4,
        "arxiv_id": "2404.00004",
        "title": "Optimizer Design for Large Models",
        "keywords": ["optimizer", "training", "large models"],
        "category": "🟡"
    },
    {
        "id": 5,
        "arxiv_id": "2404.00005",
        "title": "AutoML for Scientific Experiments",
        "keywords": ["automl", "scientific experiments"],
        "category": "🟡"
    },
    {
        "id": 6,
        "arxiv_id": "2404.00006",
        "title": "Constitutional AI for Research",
        "keywords": ["constitutional ai", "safety", "alignment"],
        "category": "🔵"
    },
]


def simulate_daily_feedback(user_id: str, days: int = 7):
    """
    Simulate feedback for multiple days

    Args:
        user_id: User identifier
        days: Number of days to simulate
    """
    feedback_logs = []
    base_date = datetime.now() - timedelta(days=days)

    for day in range(days):
        current_date = base_date + timedelta(days=day)
        push_id = f"push_{current_date.strftime('%Y%m%d')}"

        # Simulate selection behavior
        # User tends to select 🔴 papers more often
        selected = []
        skipped = []

        for paper in SAMPLE_PAPERS:
            if paper["category"] == "🔴":
                # 80% chance to select 🔴 papers
                if random.random() < 0.8:
                    selected.append(paper["id"])
                else:
                    skipped.append(paper["id"])
            elif paper["category"] == "🟡":
                # 40% chance to select 🟡 papers
                if random.random() < 0.4:
                    selected.append(paper["id"])
                else:
                    skipped.append(paper["id"])
            else:  # 🔵
                # 10% chance to select 🔵 papers
                if random.random() < 0.1:
                    selected.append(paper["id"])
                else:
                    skipped.append(paper["id"])

        # Create feedback log entry
        feedback_log = {
            "user_id": user_id,
            "date": current_date.isoformat(),
            "push_id": push_id,
            "selected": selected,
            "skipped": skipped,
            "selection_rate": len(selected) / len(SAMPLE_PAPERS),
        }
        feedback_logs.append(feedback_log)

    return feedback_logs


def save_feedback_logs(logs: list, output_path: str):
    """Save feedback logs to JSON file"""
    with open(output_path, 'w') as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(logs)} feedback logs to {output_path}")


def simulate_and_save(user_id: str = "test_user_001", days: int = 7):
    """Main function to simulate and save feedback"""
    print(f"Simulating {days} days of feedback for user {user_id}...")

    logs = simulate_daily_feedback(user_id, days)

    # Save to data/logs directory
    output_dir = Path(__file__).parent.parent / "data" / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"simulated_feedback_{user_id}.json"
    save_feedback_logs(logs, str(output_path))

    # Print summary
    total_selected = sum(len(log["selected"]) for log in logs)
    total_papers = len(SAMPLE_PAPERS) * days
    overall_rate = total_selected / total_papers

    print(f"\nSummary:")
    print(f"  Total papers shown: {total_papers}")
    print(f"  Total selected: {total_selected}")
    print(f"  Overall selection rate: {overall_rate:.1%}")


if __name__ == "__main__":
    import sys

    user_id = sys.argv[1] if len(sys.argv) > 1 else "test_user_001"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7

    simulate_and_save(user_id, days)
