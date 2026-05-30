#!/usr/bin/env bash
# Run Scholar Inbox reranking baseline against clean baseline input.
set -euo pipefail

BENCHMARK_DIR="${1:-data/benchmark_full_24users_20260301_20260419_show20_with_reading}"

echo "============================================================"
echo "Scholar Inbox baseline with clean, contamination-safe input"
echo "Benchmark: ${BENCHMARK_DIR}"
echo "============================================================"
echo

if [[ ! -f "${BENCHMARK_DIR}/episode_papers.jsonl" ]]; then
  echo "[ERROR] Missing ${BENCHMARK_DIR}/episode_papers.jsonl" >&2
  echo "Run the Full PaperFlow benchmark first, then rerun this script." >&2
  exit 1
fi
if [[ ! -f "${BENCHMARK_DIR}/episodes.jsonl" ]]; then
  echo "[ERROR] Missing ${BENCHMARK_DIR}/episodes.jsonl" >&2
  echo "Run the Full PaperFlow benchmark first, then rerun this script." >&2
  exit 1
fi

PYTHON_BIN="${PYTHON:-python}"

echo "[1/2] Export clean baseline input..."
"${PYTHON_BIN}" experiments/benchmark/export_clean_baseline_benchmark.py \
  --input-dir "${BENCHMARK_DIR}" \
  --output-dir "${BENCHMARK_DIR}/baseline_clean_input"

echo
echo "[2/2] Run Scholar Inbox reranking baseline..."
"${PYTHON_BIN}" experiments/main_experiment/run_baselines/run_scholar_inbox.py \
  --input-dir "${BENCHMARK_DIR}/baseline_clean_input" \
  --output-dir "${BENCHMARK_DIR}/main_experiment/scholar_inbox"

echo
echo "Done."
echo "Output: ${BENCHMARK_DIR}/main_experiment/scholar_inbox"
