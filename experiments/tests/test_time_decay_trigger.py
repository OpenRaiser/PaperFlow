from experiments.simulation import simulate_historical_episodes as sim
import importlib


drift_engine = importlib.import_module("scripts.drift_engine")


def test_inactive_topic_decay_only_adds_staleness_and_reduces_old_topic_scores():
    checkfile = {
        "name": "inactive_topic_decay",
        "drift_method": "direction_remove",
        "params": {"stale_topics_pool": ["gui-agent"]},
        "trigger": {"type": "inactive_topic_decay", "window_episodes": 8, "min_total_selected": 5},
        "_source_file": "06_inactive_topic_decay.json",
    }

    profile = {
        "core_directions": {"gui-agent": 0.72},
        "topic_weights": {"gui-agent": 0.72},
        "drift_plan": {
            "shift_topics": ["multimodal-reasoning"],
            "downweight_topics": ["gui-agent"],
        },
        "reading_history": [
            {"action": "selected", "topics": ["multimodal-reasoning"]},
            {"action": "selected", "topics": ["multimodal-reasoning"]},
            {"action": "selected", "topics": ["computer-using-agent"]},
            {"action": "selected", "topics": ["multimodal-reasoning"]},
            {"action": "selected", "topics": ["computer-using-agent"]},
        ],
        "drift_state": {"status": "stable", "score": 0.0},
    }

    assert drift_engine._trigger_satisfied(checkfile, profile, selected_papers=[]) is False
    assert "gui-agent" in profile["drift_state"]["decayed_topics"]
    assert profile["drift_state"]["topic_staleness"]["gui-agent"] == 1.0

    paper = {"title": "GUI agent benchmark", "abstract": "gui agent evaluation"}
    level, score = sim.match_paper_to_user(paper, profile)

    assert level in {"high_relevant", "maybe_interested", "edge_relevant"}
    assert score < 0.72
