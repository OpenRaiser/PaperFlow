from experiments.benchmark import export_human_audit_subset as audit


def test_balanced_sample_covers_shown_and_pool_strata():
    rows = [
        {"episode_id": "e1", "paper_id": "s1", "shown": True, "oracle_label": "strong_relevant"},
        {"episode_id": "e1", "paper_id": "s2", "shown": True, "oracle_label": "irrelevant"},
        {"episode_id": "e1", "paper_id": "p1", "shown": False, "oracle_label": "weak_relevant"},
        {"episode_id": "e1", "paper_id": "p2", "shown": False, "oracle_label": "irrelevant"},
    ]

    sampled = audit.balanced_sample(rows, sample_size=4, seed=1)
    strata = {(row["shown"], row["oracle_label"]) for row in sampled}

    assert len(sampled) == 4
    assert (True, "strong_relevant") in strata
    assert (False, "weak_relevant") in strata


def test_normalize_for_audit_leaves_human_fields_blank():
    row = {
        "episode_id": "e1",
        "paper_id": "p1",
        "title": "Title",
        "abstract": "word " * 100,
        "shown": True,
        "selected": False,
    }

    normalized = audit.normalize_for_audit(row, abstract_chars=20)

    assert normalized["shown"] is True
    assert normalized["selected"] is False
    assert normalized["human_label"] == ""
    assert normalized["human_notes"] == ""
    assert normalized["abstract"].endswith("...")
