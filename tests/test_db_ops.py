"""
Tests for database operations
"""

import pytest
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "storage-helper" / "scripts"))

from db_ops import (
    init_db,
    create_profile,
    get_profile,
    update_profile,
    add_paper,
    get_paper_by_arxiv,
    log_behavior,
    get_behavior_logs,
    get_selection_stats,
    get_latest_selected_papers,
    clear_pending_selected_papers,
)


class TestProfileOperations:
    """Tests for profile CRUD operations"""

    def test_create_profile(self, test_db_path, sample_profile):
        """Test creating a new profile"""
        # Override DB_PATH
        import db_ops
        db_ops.DB_PATH = test_db_path

        result = create_profile(
            sample_profile["user_id"],
            sample_profile
        )
        assert result is not None
        assert result > 0

    def test_create_duplicate_profile(self, test_db_path, sample_profile):
        """Test creating duplicate profile returns None"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        # Create first profile
        create_profile(sample_profile["user_id"], sample_profile)

        # Try to create duplicate
        result = create_profile(sample_profile["user_id"], sample_profile)
        assert result is None

    def test_get_profile(self, test_db_path, sample_profile):
        """Test retrieving a profile"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        # Create profile
        create_profile(sample_profile["user_id"], sample_profile)

        # Retrieve profile
        result = get_profile(sample_profile["user_id"])
        assert result is not None
        assert result["user_id"] == sample_profile["user_id"]
        assert result["version"] == sample_profile["version"]

    def test_get_nonexistent_profile(self, test_db_path):
        """Test retrieving nonexistent profile returns None"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        result = get_profile("nonexistent_user")
        assert result is None

    def test_update_profile(self, test_db_path, sample_profile):
        """Test updating a profile"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        # Create profile
        create_profile(sample_profile["user_id"], sample_profile)

        # Update profile
        updated = sample_profile.copy()
        updated["version"] = "0.2"
        updated["core_directions"]["new_topic"] = 0.5

        result = update_profile(sample_profile["user_id"], updated)
        assert result is True

        # Verify update
        retrieved = get_profile(sample_profile["user_id"])
        assert retrieved["version"] == "0.2"


class TestPaperOperations:
    """Tests for paper CRUD operations"""

    def test_add_paper(self, test_db_path, sample_paper):
        """Test adding a paper"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        result = add_paper(sample_paper)
        assert result is not None
        assert result > 0

    def test_add_duplicate_paper(self, test_db_path, sample_paper):
        """Test adding duplicate paper returns None"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        # Add first paper
        add_paper(sample_paper)

        # Try to add duplicate
        result = add_paper(sample_paper)
        assert result is None

    def test_get_paper_by_arxiv(self, test_db_path, sample_paper):
        """Test retrieving paper by arxiv_id"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        # Add paper
        add_paper(sample_paper)

        # Retrieve by arxiv_id
        result = get_paper_by_arxiv(sample_paper["arxiv_id"])
        assert result is not None
        assert result["arxiv_id"] == sample_paper["arxiv_id"]


class TestBehaviorLogOperations:
    """Tests for behavior log operations"""

    def test_log_behavior(self, test_db_path):
        """Test logging user behavior"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        result = log_behavior(
            user_id="test_user",
            push_id="push_001",
            paper_id=1,
            action="selected",
            action_type="selected",
            category="🔴"
        )
        assert result is not None
        assert result > 0

    def test_get_behavior_logs(self, test_db_path):
        """Test retrieving behavior logs"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        # Log some behaviors
        log_behavior("test_user", "push_001", 1, "selected", "selected", "🔴")
        log_behavior("test_user", "push_001", 2, "skipped", "skipped", "🟡")

        # Retrieve logs
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        logs = get_behavior_logs("test_user", start_date, end_date)
        assert len(logs) == 2


class TestSelectionStats:
    """Tests for selection statistics"""

    def test_get_selection_stats(self, test_db_path):
        """Test getting selection statistics"""
        import db_ops
        db_ops.DB_PATH = test_db_path

        # Log some behaviors
        for i in range(5):
            log_behavior("test_user", f"push_{i:03d}", i, "selected", "selected", "🔴")
        for i in range(5, 10):
            log_behavior("test_user", f"push_{i:03d}", i, "skipped", "skipped", "🟡")

        # Get stats
        stats = get_selection_stats("test_user", days=7)
        assert stats["total"] == 10
        assert stats["selected"] == 5
        assert stats["skipped"] == 5
        assert abs(stats["selection_rate"] - 0.5) < 0.01


class TestReadingQueueOperations:
    """Tests for the pending reading queue helpers."""

    def test_clear_pending_selected_papers_hides_old_queue_until_new_selection(self, test_db_path, sample_paper):
        import db_ops
        db_ops.DB_PATH = test_db_path

        paper_a = dict(sample_paper)
        paper_b = dict(sample_paper)
        paper_b["arxiv_id"] = "2404.00002"
        paper_b["doi"] = "10.48550/arXiv.2404.00002"
        paper_b["title"] = "Follow-up GUI Agent with Grounded Planning"

        paper_a_id = add_paper(paper_a)
        paper_b_id = add_paper(paper_b)

        log_behavior(
            "test_user",
            "push_001",
            paper_a_id,
            "selected",
            "selected",
            "selected",
            metadata={"paper_number": 1},
        )
        latest_before_clear = get_latest_selected_papers("test_user")
        assert latest_before_clear is not None
        assert latest_before_clear["push_id"] == "push_001"

        cleared = clear_pending_selected_papers("test_user")
        assert cleared["cleared"] is True
        assert cleared["cleared_count"] == 1
        assert cleared["push_id"] == "push_001"
        assert get_latest_selected_papers("test_user") is None

        log_behavior(
            "test_user",
            "push_002",
            paper_b_id,
            "selected",
            "selected",
            "selected",
            metadata={"paper_number": 1},
        )
        latest_after_new_selection = get_latest_selected_papers("test_user")
        assert latest_after_new_selection is not None
        assert latest_after_new_selection["push_id"] == "push_002"

    def test_clear_pending_selected_papers_returns_empty_when_queue_is_already_clear(self, test_db_path):
        import db_ops
        db_ops.DB_PATH = test_db_path

        cleared = clear_pending_selected_papers("test_user")

        assert cleared["cleared"] is False
        assert cleared["cleared_count"] == 0
