from experiments.simulation import simulate_historical_episodes as sim


def test_match_paper_to_user_adds_hidden_anchor_exploration_signal():
    profile = {
        "core_directions": {"gui-agent": 0.72, "web-agent": 0.56},
        "drift_state": {
            "status": "observing",
            "drift_enabled": True,
            "hidden_anchor": "multimodal-reasoning",
            "anchor_topic": None,
        },
    }
    paper = {
        "title": "A multimodal reasoning benchmark for autonomous agents",
        "abstract": "This work studies multimodal reasoning with screen understanding.",
    }

    level, score = sim.match_paper_to_user(paper, profile)

    assert level == "maybe_interested"
    assert score >= 0.3


def test_match_paper_to_user_marks_must_read_when_must_read_rule_hits():
    profile = {
        "core_directions": {"gui-agent": 0.72},
        "must_read": {
            "authors": ["Sanja Fidler"],
            "institutions": ["OpenAI"],
            "keywords": ["gui agent"],
        },
        "drift_state": {"status": "stable"},
    }
    paper = {
        "title": "GUI Agent Planning for Desktop Tasks",
        "abstract": "We study computer use and gui agent planning.",
        "authors": ["Sanja Fidler", "Other Author"],
        "institution": "OpenAI",
    }

    level, score = sim.match_paper_to_user(paper, profile)

    assert level == "must_read"
    assert score >= 0.8


def test_match_paper_to_user_marks_must_read_on_institution_match_only():
    profile = {
        "core_directions": {"science-of-science": 0.72},
        "must_read": {
            "authors": [],
            "institutions": ["Microsoft Research"],
            "keywords": [],
        },
        "drift_state": {"status": "stable"},
    }
    paper = {
        "title": "A paper without explicit must-read keywords",
        "abstract": "This study discusses evaluation methodology.",
        "authors": ["Other Author"],
        "institution": "Microsoft Research",
    }

    level, score = sim.match_paper_to_user(paper, profile)

    assert level == "must_read"
    assert score >= 0.8


def test_match_paper_to_user_marks_must_read_on_title_abstract_keyword_match():
    profile = {
        "core_directions": {},
        "must_read": {
            "authors": [],
            "institutions": [],
            "keywords": ["single-cell analysis"],
        },
        "drift_state": {"status": "stable"},
    }
    paper = {
        "title": "GPU-accelerated single-cell analysis at scale",
        "abstract": "The method improves genomics pipelines without explicit keyword metadata.",
        "authors": ["Other Author"],
        "institution": "arxiv",
    }

    level, score = sim.match_paper_to_user(paper, profile)

    assert level == "must_read"
    assert score >= 0.8


def test_simulate_user_feedback_can_choose_observing_anchor_candidate(monkeypatch):
    monkeypatch.setattr(sim.random, "randint", lambda _a, _b: 2)
    monkeypatch.setattr(sim.random, "sample", lambda seq, n: list(seq)[:n])
    monkeypatch.setattr(sim.random, "random", lambda: 0.0)

    profile = {
        "core_directions": {"gui-agent": 0.72},
        "drift_state": {
            "status": "observing",
            "drift_enabled": True,
            "hidden_anchor": "multimodal-reasoning",
            "anchor_topic": None,
        },
    }
    selected_papers = [
        {"paper_id": 1, "title": "Core GUI paper", "abstract": "", "relevance_level": "high_relevant", "relevance_score": 0.8},
        {"paper_id": 2, "title": "Multimodal reasoning for interface agents", "abstract": "", "relevance_level": "maybe_interested", "relevance_score": 0.38},
        {"paper_id": 3, "title": "Unrelated systems paper", "abstract": "", "relevance_level": "maybe_interested", "relevance_score": 0.31},
    ]

    chosen = sim.simulate_user_feedback(selected_papers, profile)
    chosen_ids = [paper["paper_id"] for paper in chosen]

    assert 1 in chosen_ids
    assert 2 in chosen_ids


def test_simulate_user_feedback_prefers_anchor_candidates_after_lock(monkeypatch):
    monkeypatch.setattr(sim.random, "randint", lambda _a, _b: 2)
    monkeypatch.setattr(sim.random, "sample", lambda seq, n: list(seq)[:n])

    profile = {
        "core_directions": {"gui-agent": 0.72},
        "drift_state": {
            "status": "shifting",
            "drift_enabled": True,
            "hidden_anchor": "multimodal-reasoning",
            "anchor_topic": "multimodal-reasoning",
            "anchor_progress": 0.5,
            "commitment_days_remaining": 3,
        },
    }
    selected_papers = [
        {"paper_id": 1, "title": "Core GUI paper", "abstract": "", "relevance_level": "high_relevant", "relevance_score": 0.8},
        {"paper_id": 2, "title": "Multimodal reasoning for interface agents", "abstract": "", "relevance_level": "maybe_interested", "relevance_score": 0.35},
        {"paper_id": 3, "title": "Robust multimodal reasoning benchmark", "abstract": "", "relevance_level": "edge_relevant", "relevance_score": 0.32},
        {"paper_id": 4, "title": "Unrelated systems paper", "abstract": "", "relevance_level": "maybe_interested", "relevance_score": 0.31},
    ]

    chosen = sim.simulate_user_feedback(selected_papers, profile)
    chosen_ids = [paper["paper_id"] for paper in chosen]

    assert 1 in chosen_ids
    assert 2 in chosen_ids
    assert 3 in chosen_ids


def test_simulate_user_feedback_with_oracle_force_selects_observing_anchor_candidate(monkeypatch):
    monkeypatch.setattr(sim.random, "randint", lambda _a, _b: 2)
    monkeypatch.setattr(sim.random, "random", lambda: 0.99)
    monkeypatch.setattr(
        sim,
        "_sample_daily_reading_availability",
        lambda _user_id, _date_str: {"availability_type": "normal", "reading_capacity": 3, "min_reads": 1},
    )

    profile = {
        "core_directions": {"gui-agent": 0.72},
        "secondary_topics": [],
        "must_read": {"authors": [], "institutions": [], "keywords": []},
        "drift_state": {
            "status": "observing",
            "drift_enabled": True,
            "hidden_anchor": "multimodal-reasoning",
            "anchor_topic": None,
        },
    }
    shown_papers = [
        {
            "paper_id": 1,
            "title": "General GUI paper",
            "abstract": "",
            "relevance_level": "high_relevant",
            "relevance_score": 0.8,
            "system_rank": 1,
        },
        {
            "paper_id": 2,
            "title": "Multimodal reasoning for interface agents",
            "abstract": "",
            "relevance_level": "maybe_interested",
            "relevance_score": 0.35,
            "system_rank": 2,
        },
    ]

    chosen = sim.simulate_user_feedback_with_oracle(
        shown_papers,
        profile,
        user_id="user_role1",
        date_str="2026-03-02",
    )
    chosen_ids = [paper["paper_id"] for paper in chosen]

    assert 2 in chosen_ids


def test_simulate_user_feedback_with_oracle_strongly_keeps_must_read(monkeypatch):
    monkeypatch.setattr(sim.random, "random", lambda: 0.89)
    monkeypatch.setattr(sim.random, "randint", lambda _a, _b: 2)
    monkeypatch.setattr(
        sim,
        "_sample_daily_reading_availability",
        lambda _user_id, _date_str: {"availability_type": "normal", "reading_capacity": 3, "min_reads": 1},
    )

    profile = {
        "core_directions": {},
        "must_read": {"authors": [], "institutions": [], "keywords": ["gui agent"]},
        "drift_state": {"status": "stable"},
    }
    shown_papers = [
        {
            "paper_id": "must",
            "title": "A GUI Agent Benchmark",
            "abstract": "This paper studies gui agent evaluation.",
            "authors": [],
            "institution": "",
            "relevance_level": "must_read",
            "relevance_score": 0.8,
            "system_rank": 1,
        },
        {
            "paper_id": "edge",
            "title": "Unrelated Paper",
            "abstract": "An unrelated study.",
            "authors": [],
            "institution": "",
            "relevance_level": "edge_relevant",
            "relevance_score": 0.0,
            "system_rank": 2,
        },
    ]

    chosen = sim.simulate_user_feedback_with_oracle(
        shown_papers,
        profile,
        user_id="user_role1",
        date_str="2026-03-01",
    )

    assert any(paper["paper_id"] == "must" for paper in chosen)


def test_simulate_user_feedback_with_oracle_can_skip_must_read(monkeypatch):
    values = iter([0.91, 1.0, 1.0])
    monkeypatch.setattr(sim.random, "random", lambda: next(values))
    monkeypatch.setattr(sim.random, "randint", lambda _a, _b: 2)
    monkeypatch.setattr(
        sim,
        "_sample_daily_reading_availability",
        lambda _user_id, _date_str: {"availability_type": "normal", "reading_capacity": 3, "min_reads": 0},
    )

    profile = {
        "core_directions": {},
        "must_read": {"authors": [], "institutions": [], "keywords": ["gui agent"]},
        "drift_state": {"status": "stable"},
    }
    shown_papers = [
        {
            "paper_id": "must",
            "title": "A GUI Agent Benchmark",
            "abstract": "This paper studies gui agent evaluation.",
            "authors": [],
            "institution": "",
            "relevance_level": "must_read",
            "relevance_score": 0.8,
            "system_rank": 1,
        },
        {
            "paper_id": "edge",
            "title": "Unrelated Paper",
            "abstract": "An unrelated study.",
            "authors": [],
            "institution": "",
            "relevance_level": "edge_relevant",
            "relevance_score": 0.0,
            "system_rank": 2,
        },
    ]

    chosen = sim.simulate_user_feedback_with_oracle(
        shown_papers,
        profile,
        user_id="user_role1",
        date_str="2026-03-01",
    )

    assert not any(paper["paper_id"] == "must" for paper in chosen)


def test_simulate_user_feedback_with_oracle_allows_zero_selection_on_busy_day(monkeypatch):
    monkeypatch.setattr(sim.random, "random", lambda: 0.0)
    monkeypatch.setattr(
        sim,
        "_sample_daily_reading_availability",
        lambda _user_id, _date_str: {"availability_type": "busy", "reading_capacity": 0, "min_reads": 0},
    )

    profile = {"core_directions": {}, "drift_state": {"status": "stable"}}
    shown_papers = [
        {
            "paper_id": "strong",
            "title": "A highly relevant GUI Agent Benchmark",
            "abstract": "This paper studies gui agent evaluation.",
            "relevance_level": "high_relevant",
            "relevance_score": 0.8,
            "system_rank": 1,
            "oracle_label": "strong_relevant",
        }
    ]

    chosen = sim.simulate_user_feedback_with_oracle(
        shown_papers,
        profile,
        user_id="user_role1",
        date_str="2026-03-01",
    )

    assert chosen == []


def test_prepare_episode_candidates_uses_real_daily_push_sort(monkeypatch):
    captured = {}
    papers = [
        {
            "paper_id": 1,
            "title": "General GUI agent paper",
            "abstract": "",
            "embedding": [1.0, 0.0],
            "topics": ["gui-agent"],
            "keywords": ["gui-agent"],
            "quality_score": 0.6,
        },
        {
            "paper_id": 2,
            "title": "Multimodal reasoning for agents",
            "abstract": "",
            "embedding": [0.0, 1.0],
            "topics": ["multimodal-reasoning"],
            "keywords": ["multimodal-reasoning"],
            "quality_score": 0.7,
        },
    ]
    user = {
        "user_id": "user_role1",
        "profile": {
            "core_directions": {"gui-agent": 0.7},
            "topic_weights": {"gui-agent": 0.7, "multimodal-reasoning": 0.5},
            "drift_state": {
                "status": "observing",
                "drift_enabled": True,
                "hidden_anchor": "multimodal-reasoning",
            },
        },
    }

    monkeypatch.setattr(sim, "_load_real_daily_push_weights", lambda: {"push_target_count": 1, "push_max_count": 1})

    def fake_score_pool(ranking_papers, profile, weights):
        return [
            sim.daily_push_agent.PaperWithScore(ranking_papers[0], 0.30, "edge_relevant", relevance_signal=0.2),
            sim.daily_push_agent.PaperWithScore(ranking_papers[1], 0.88, "high_relevant", relevance_signal=0.8, drift_bonus=0.08),
        ]

    def fake_sort_and_categorize(ranking_papers, profile, weights):
        captured["called"] = True
        captured["strategy_mode"] = profile["drift_state"].get("strategy_mode")
        captured["weights"] = weights
        return [
            sim.daily_push_agent.PaperWithScore(ranking_papers[1], 0.88, "high_relevant", relevance_signal=0.8, drift_bonus=0.08)
        ]

    monkeypatch.setattr(sim, "_score_daily_push_candidate_pool", fake_score_pool)
    monkeypatch.setattr(sim.daily_push_agent, "sort_and_categorize", fake_sort_and_categorize)

    shown, all_candidates = sim.prepare_episode_candidates_with_metrics(papers, user, show_count=1)

    assert captured["called"] is True
    assert captured["strategy_mode"] == "simulation"
    assert captured["weights"]["push_target_count"] == 1
    assert [paper["paper_id"] for paper in shown] == [2]
    assert shown[0]["ranking_source"] == "daily_push_agent.sort_and_categorize"
    assert any(paper["paper_id"] == 1 and not paper["shown"] for paper in all_candidates)


def test_prepare_episode_candidates_fills_to_show_count_with_scored_fallback(monkeypatch):
    papers = [
        {"paper_id": 1, "title": "Primary paper", "abstract": "", "topics": ["gui-agent"]},
        {"paper_id": 2, "title": "Fallback paper", "abstract": "", "topics": ["vision"]},
        {"paper_id": 3, "title": "Last paper", "abstract": "", "topics": ["systems"]},
    ]
    user = {
        "user_id": "user_role1",
        "profile": {
            "core_directions": {"gui-agent": 0.7},
            "topic_weights": {"gui-agent": 0.7},
            "drift_state": {"status": "stable"},
        },
    }

    monkeypatch.setattr(sim, "_load_real_daily_push_weights", lambda: {})

    def fake_score_pool(ranking_papers, profile, weights):
        return [
            sim.daily_push_agent.PaperWithScore(ranking_papers[0], 0.90, "high_relevant", relevance_signal=0.8),
            sim.daily_push_agent.PaperWithScore(ranking_papers[1], 0.40, "edge_relevant", relevance_signal=0.05),
            sim.daily_push_agent.PaperWithScore(ranking_papers[2], 0.20, "edge_relevant", relevance_signal=0.02),
        ]

    def fake_sort_and_categorize(ranking_papers, profile, weights):
        return [
            sim.daily_push_agent.PaperWithScore(ranking_papers[0], 0.90, "high_relevant", relevance_signal=0.8)
        ]

    monkeypatch.setattr(sim, "_score_daily_push_candidate_pool", fake_score_pool)
    monkeypatch.setattr(sim.daily_push_agent, "sort_and_categorize", fake_sort_and_categorize)

    shown, all_candidates = sim.prepare_episode_candidates_with_metrics(papers, user, show_count=3)

    assert [paper["paper_id"] for paper in shown] == [1, 2, 3]
    assert [paper["system_rank"] for paper in shown] == [1, 2, 3]
    assert shown[0]["ranking_fallback"] is False
    assert shown[1]["ranking_fallback"] is True
    assert shown[2]["ranking_fallback"] is True
    assert all(paper["show_target_count"] == 3 for paper in all_candidates)
