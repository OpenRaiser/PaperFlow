#!/usr/bin/env python3
"""
Cold Start Script - Generate initial user profile
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "storage-helper" / "scripts"))

from db_ops import create_profile, init_db


def generate_profile(user_input: str) -> dict:
    """
    Generate initial profile from user input

    Args:
        user_input: User's research description

    Returns:
        Profile JSON
    """
    now = datetime.now().isoformat()

    # Parse user input and generate profile
    # User said: "多模态推理的方向，关注多模态方向的论文"

    profile = {
        "user_id": "user_001",
        "version": "0.1",
        "created_at": now,
        "updated_at": now,
        "core_directions": {
            "Multimodal Reasoning": 0.85,
            "Multimodal Learning": 0.80,
            "Vision-Language Models": 0.75,
            "Cross-modal Understanding": 0.70
        },
        "methodology_preferences": {
            "preference_data_driven_over_theory": True,
            "preference_systematic_work_over_incremental": True,
            "preference_open_source_code": True,
            "preference_multimodal_application": True
        },
        "must_read": {
            "authors": [],
            "institutions": [],
            "keywords": ["multimodal", "reasoning", "vision-language"]
        },
        "topic_weights": {
            "multimodal-reasoning": 0.85,
            "multimodal-learning": 0.80,
            "vision-language": 0.75,
            "cross-modal": 0.70
        },
        "author_heat": {},
        "institution_heat": {},
        "interest_vector": [0.0] * 768,  # Will be updated from feedback
        "taste_profile": {
            "preferred_work_type": ["empirical", "multimodal", "reasoning"],
            "dispreferred_work_type": ["single_modality", "incremental"]
        },
        "reading_history": [],
        "behavior_logs_summary": {
            "total_pushes": 0,
            "total_selected": 0,
            "total_skipped": 0,
            "selection_rate": 0.0
        }
    }

    return profile


def main():
    # Default input if not provided
    default_input = "多模态推理方向，关注多模态方向的论文"

    user_input = sys.argv[1] if len(sys.argv) > 1 else default_input

    print("=" * 60)
    print("Cold Start - Generating Initial Profile")
    print("=" * 60)
    print(f"\nUser input: {user_input}\n")

    # Generate profile
    profile = generate_profile(user_input)

    # Initialize database (creates tables if not exist)
    init_db()

    # Store profile
    profile_id = create_profile(profile["user_id"], profile)

    if profile_id:
        print(f"\n[OK] Profile created successfully!")
        print(f"\n--- Profile Summary ---")
        print(f"User ID: {profile['user_id']}")
        print(f"Version: {profile['version']}")
        print(f"\nCore Directions:")
        for direction, weight in profile['core_directions'].items():
            print(f"  - {direction}: {weight}")
        print(f"\nMust-read keywords: {profile['must_read']['keywords']}")
    else:
        print(f"\n[WARN] Profile already exists for user_001")
        print("To update, use: /show-profile or modify directly")


if __name__ == "__main__":
    main()
