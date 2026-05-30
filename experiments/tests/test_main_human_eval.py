from experiments.human_eval import aggregate_main_human_eval as agg
from experiments.human_eval import build_main_human_eval_packet as packet


def test_compute_episode_metrics_matches_recommendation_formula():
    acc = packet.EpisodeAccumulator("m", "Method", "u::d")
    labels = ["strong_relevant", "relevant", "weak_relevant"] + ["irrelevant"] * 17
    for rank, label in enumerate(labels, start=1):
        row = {"shown": True, "system_rank": rank, "oracle_label": label}
        acc.pool_size += 1
        acc.pool_useful += int(label in packet.USEFUL_LABELS)
        acc.pool_strict += int(label in packet.STRICT_LABELS)
        acc.pool_gains.append(packet.ORACLE_GAIN[label])
        acc.shown_rows.append(row)

    metrics = packet.compute_episode_metrics(acc)

    assert metrics["gNDCG@20"] == 1.0
    assert metrics["Useful@5"] == 0.6
    assert metrics["Useful@20"] == 0.15
    assert metrics["StrictR@20+"] == 1.0
    assert metrics["MRR@20"] == 1.0
    assert metrics["RecommendationScore"] > 0


def test_build_scored_papers_and_aggregate_episode_scores():
    blind_rows = [
        {
            "sample_id": "HMAIN_00001",
            "HumanRelevance": "4",
            "HumanUsefulness": "5",
            "DecisionHelpfulness": "3",
            "comments": "ok",
        },
        {
            "sample_id": "HMAIN_00002",
            "HumanRelevance": "2",
            "HumanUsefulness": "3",
            "DecisionHelpfulness": "4",
            "comments": "",
        },
    ]
    key_rows = [
        {
            "sample_id": "HMAIN_00001",
            "method_key": "m",
            "method_name": "Method",
            "episode_id": "e1",
            "user_id": "u1",
            "date": "2026-03-01",
            "RecommendationScore": "50",
        },
        {
            "sample_id": "HMAIN_00002",
            "method_key": "m",
            "method_name": "Method",
            "episode_id": "e1",
            "user_id": "u1",
            "date": "2026-03-01",
            "RecommendationScore": "50",
        },
    ]

    scored = agg.build_scored_papers(blind_rows, key_rows)
    episodes = agg.aggregate_episode_scores(scored)
    methods = agg.aggregate_method_scores(episodes)

    assert scored[0]["HumanEval"] == "80.0000"
    assert episodes[0]["HumanEval"] == "70.0000"
    assert methods[0]["HumanEval"] == "70.0000"
