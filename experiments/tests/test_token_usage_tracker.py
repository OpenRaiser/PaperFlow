import json

from experiments.token_cost import token_usage_tracker as tracker


def test_flush_token_logs_rewrites_as_daily_aggregates(tmp_path, monkeypatch):
    token_log = tmp_path / "token_usage.jsonl"
    token_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-04-21T15:00:00",
                        "task_type": "llm_report",
                        "model": "gemini-3-flash-preview",
                        "input_tokens": 120,
                        "output_tokens": 30,
                        "total_tokens": 150,
                        "date": "2026-03-01",
                    }
                ),
                json.dumps(
                    {
                        "date": "2026-03-02",
                        "embedding_tokens": 10,
                        "llm_tokens": 20,
                        "total_tokens": 30,
                        "call_count": 2,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(tracker, "TOKEN_LOG_PATH", token_log)
    tracker._daily_token_totals.clear()
    tracker.log_token_usage("embedding", "Qwen/Qwen3-Embedding-8B", 7, 0, date="2026-03-01")
    tracker.log_token_usage("llm_report", "gemini-3-flash-preview", 11, 5, date="2026-03-01")

    tracker.flush_token_logs()

    rows = [json.loads(line) for line in token_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows == [
        {
            "date": "2026-03-01",
            "embedding_tokens": 7,
            "llm_tokens": 16,
            "total_tokens": 23,
            "call_count": 2,
        },
        {
            "date": "2026-03-02",
            "embedding_tokens": 10,
            "llm_tokens": 20,
            "total_tokens": 30,
            "call_count": 2,
        },
    ]

    tracker._daily_token_totals.clear()
