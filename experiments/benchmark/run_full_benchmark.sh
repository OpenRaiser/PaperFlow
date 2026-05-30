#!/usr/bin/env bash
# Full PaperFlow benchmark: 24 users x 50 days, Top-20, reading reports.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

export LLM_PARSER_OPENAI_MODEL="${LLM_PARSER_OPENAI_MODEL:-gemini-3-flash-preview}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

OUT_DIR="data/benchmark_full_24users_20260301_20260419_show20_with_reading"
PYTHON_BIN="${PYTHON:-python}"

cat <<EOF
============================================================
PaperFlow full benchmark: 24 users x 50 days, Top-20, reading
Workspace: ${PROJECT_ROOT}
Output:    ${OUT_DIR}
============================================================

EOF

echo "[1/7] Stop any existing historical simulation process..."
pkill -f "simulate_historical_episodes.py" 2>/dev/null || true

echo
echo "[2/7] Clean previous benchmark output in this workspace..."
rm -rf "${OUT_DIR}"
rm -f data/token_usage.jsonl
rm -rf data/embeddings_cache
mkdir -p data/embeddings_cache

echo
echo "[3/7] Reset benchmark state, preserving papers and reseeding profiles..."
"${PYTHON_BIN}" scripts/clear_database.py --action benchmark_reset --yes

echo
echo "[4/7] Run full simulation with fixed paper database..."
"${PYTHON_BIN}" experiments/simulation/simulate_historical_episodes.py \
  --start-date 20260301 \
  --end-date 20260419 \
  --skip-paper-collection \
  --show-count 20 \
  --llm-model "gemini-3-flash-preview" \
  --embedding-model "Qwen/Qwen3-Embedding-8B" \
  --output-dir "${OUT_DIR}"

echo
echo "[5/7] Evaluate recommendation metrics..."
"${PYTHON_BIN}" experiments/benchmark/evaluate_simulation_metrics.py \
  --input-dir "${OUT_DIR}" \
  --ks 5 10 20 \
  --method-name "Full PaperFlow Pipeline"

echo
echo "[6/7] Export human audit subset..."
"${PYTHON_BIN}" experiments/benchmark/export_human_audit_subset.py \
  --input-dir "${OUT_DIR}" \
  --shown-only \
  --sample-size 500 \
  --seed 42

cat <<EOF

[7/7] Done. Key outputs:
  ${OUT_DIR}/simulation_summary.json
  ${OUT_DIR}/dataset_summary.md
  ${OUT_DIR}/main_experiment_table_top20.md
  ${OUT_DIR}/case_metrics_table_top20.md
  ${OUT_DIR}/evaluation_metrics.json
  ${OUT_DIR}/human_audit_subset.csv
  ${OUT_DIR}/reading_reports.jsonl
  ${OUT_DIR}/reading_reports_md/

Full benchmark completed successfully.
EOF
