#!/usr/bin/env bash
# PaperFlow reading benchmark wrapper. Modes: case | full.
set -euo pipefail

usage() {
  cat <<EOF
Usage:
  experiments/benchmark/run_reading_benchmark.sh case
  experiments/benchmark/run_reading_benchmark.sh full

Modes:
  case  = 3 users, 2026-03-01 to 2026-03-15, with reading reports
  full  = 24 users, 2026-03-01 to 2026-04-19, with reading reports

The script never clears papers from data/paperflow.db.
It always resets profiles, behavior logs, task status, output files, and token logs.
EOF
}

MODE="${1:-}"
if [[ -z "${MODE}" ]]; then
  usage; exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

START_DATE="20260301"
SHOW_COUNT="20"
DRIFT_PROBABILITY="0.5"
LLM_MODEL="${LLM_PARSER_OPENAI_MODEL:-gemini-3-flash-preview}"
EMBEDDING_MODEL="Qwen/Qwen3-Embedding-8B"
PYTHON_BIN="${PYTHON:-python}"

case "${MODE,,}" in
  case)
    END_DATE="20260315"
    OUT_DIR="data/benchmark_case_3users_20260301_20260315_show20_with_reading"
    USER_ARGS=(--user-ids user_role1 user_role2 user_role3)
    ;;
  full)
    END_DATE="20260419"
    OUT_DIR="data/benchmark_24users_20260301_20260419_show20_with_reading"
    USER_ARGS=(--user-count 24)
    ;;
  *)
    usage; exit 2
    ;;
esac

if [[ -d "${OUT_DIR}" ]]; then
  echo "Removing previous output directory only: ${OUT_DIR}"
  rm -rf "${OUT_DIR}"
fi
if [[ -f data/token_usage.jsonl ]]; then
  echo "Removing previous token log only: data/token_usage.jsonl"
  rm -f data/token_usage.jsonl
fi

echo "Running PaperFlow reading benchmark: ${MODE}"
echo "Output: ${OUT_DIR}"
echo
echo "Resetting benchmark state: profiles, behavior_logs, task_status."
echo "Papers table is preserved."
echo

"${PYTHON_BIN}" scripts/clear_database.py --action benchmark_reset --yes

echo "NOTE: This command intentionally does not pass --skip-reading-reports."
echo "NOTE: --skip-paper-collection keeps the fixed paper database untouched."
echo

"${PYTHON_BIN}" experiments/simulation/simulate_historical_episodes.py \
  --start-date "${START_DATE}" \
  --end-date "${END_DATE}" \
  "${USER_ARGS[@]}" \
  --skip-paper-collection \
  --show-count "${SHOW_COUNT}" \
  --drift-probability "${DRIFT_PROBABILITY}" \
  --llm-model "${LLM_MODEL}" \
  --embedding-model "${EMBEDDING_MODEL}" \
  --output-dir "${OUT_DIR}"

"${PYTHON_BIN}" experiments/benchmark/evaluate_simulation_metrics.py \
  --input-dir "${OUT_DIR}" \
  --ks 5 10 20 \
  --method-name "Full PaperFlow Pipeline"

"${PYTHON_BIN}" experiments/benchmark/export_human_audit_subset.py \
  --input-dir "${OUT_DIR}" \
  --shown-only \
  --sample-size 200 \
  --seed 42

echo
echo "Benchmark complete: ${OUT_DIR}"
