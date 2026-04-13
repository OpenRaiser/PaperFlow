"""
Pytest configuration and fixtures for SciTaste tests
"""

import pytest
import sqlite3
import json
from pathlib import Path
from datetime import datetime


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary database for testing"""
    db_path = tmp_path / "test_scitaste.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            profile_json TEXT NOT NULL,
            version TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arxiv_id TEXT UNIQUE,
            doi TEXT,
            title TEXT NOT NULL,
            authors TEXT,
            institution TEXT,
            abstract TEXT,
            venue TEXT,
            publish_date DATE,
            embedding BLOB,
            embedding_model TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pushed BOOLEAN DEFAULT FALSE,
            push_date DATE
        )
    """)

    cursor.execute("""
        CREATE TABLE behavior_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            push_id TEXT NOT NULL,
            paper_id INTEGER,
            action TEXT NOT NULL,
            action_type TEXT NOT NULL,
            category TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)

    conn.commit()
    conn.close()

    return str(db_path)


@pytest.fixture
def sample_profile():
    """Sample user profile for testing"""
    return {
        "user_id": "test_user_001",
        "version": "0.1",
        "core_directions": {
            "GUI Agent": 0.70,
            "Data-native Scientific Discovery": 0.80
        },
        "methodology_preferences": {
            "preference_data_driven_over_theory": True,
            "preference_systematic_work_over_incremental": True
        },
        "must_read": {
            "authors": ["Mohammed AlQuraishi"],
            "institutions": ["Shanghai AI Lab"],
            "keywords": ["phase transition"]
        },
        "topic_weights": {
            "gui-agent": 0.70,
            "data-native": 0.80
        },
        "author_heat": {"Mohammed AlQuraishi": 0.8},
        "institution_heat": {"Shanghai AI Lab": 0.9},
        "interest_vector": [0.5, 0.3, 0.2],
        "taste_profile": {
            "preferred_work_type": ["empirical", "systematic"]
        }
    }


@pytest.fixture
def sample_paper():
    """Sample paper for testing"""
    return {
        "arxiv_id": "2404.00001",
        "doi": "10.48550/arXiv.2404.00001",
        "title": "GUI Agent with Visual Grounding",
        "authors": ["John Smith", "Jane Doe"],
        "institution": "MIT",
        "abstract": "We present a novel approach to GUI agent with visual grounding.",
        "venue": "arXiv",
        "publish_date": "2026-04-08",
        "embedding": [0.4, 0.4, 0.2],
        "embedding_model": "text-embedding-3-small",
        "keywords": ["gui agent", "visual grounding"],
        "quality_score": 0.8
    }


@pytest.fixture
def sample_papers_batch():
    """Batch of sample papers for testing"""
    return [
        {
            "arxiv_id": "2404.00001",
            "title": "GUI Agent with Visual Grounding",
            "authors": ["John Smith"],
            "abstract": "We present a novel approach to GUI agent.",
            "embedding": [0.4, 0.4, 0.2],
            "keywords": ["gui agent", "visual grounding"]
        },
        {
            "arxiv_id": "2404.00002",
            "title": "Protein Folding with Deep Learning",
            "authors": ["Jane Doe"],
            "abstract": "We present a deep learning approach to protein folding.",
            "embedding": [0.3, 0.5, 0.2],
            "keywords": ["protein", "deep learning"]
        },
        {
            "arxiv_id": "2404.00003",
            "title": "Data-Native Scientific Discovery",
            "authors": ["Bob Wilson"],
            "abstract": "We propose a data-native approach to scientific discovery.",
            "embedding": [0.5, 0.3, 0.2],
            "keywords": ["data-native", "scientific discovery"]
        }
    ]
