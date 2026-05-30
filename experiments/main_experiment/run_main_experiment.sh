#!/usr/bin/env bash
# Full main-experiment baseline run (bash equivalent of run_main_experiment.ps1).
#
# Usage:
#   experiments/main_experiment/run_main_experiment.sh [BENCHMARK_DIR] [--force]
#
# BENCHMARK_DIR defaults to data/benchmark_full_24users_20260301_20260419_show20_with_reading.

set -euo pipefail

BENCHMARK_DIR="${1:-data/benchmark_full_24users_20260301_20260419_show20_with_reading}"
FORCE=0
shift || true
for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE=1 ;;
    *) ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ ! -d "${BENCHMARK_DIR}" ]]; then
  echo "Benchmark dir not found: ${BENCHMARK_DIR}" >&2
  exit 2
fi
BENCHMARK_DIR="$(cd "${BENCHMARK_DIR}" && pwd)"

CLEAN_INPUT="${BENCHMARK_DIR}/baseline_clean_input"
MAIN_EXPERIMENT="${BENCHMARK_DIR}/main_experiment"
LOG_DIR="${MAIN_EXPERIMENT}/logs"
mkdir -p "${MAIN_EXPERIMENT}" "${LOG_DIR}"

RUN_ID="$(date +%Y%m%d_%H%M%S)"
MAIN_LOG="${LOG_DIR}/full_baseline_run_${RUN_ID}.log"
PYTHON_BIN="${PYTHON:-python}"
RUN_FAILED="${MAIN_EXPERIMENT}/RUN_FAILED.txt"
RUN_COMPLETE="${MAIN_EXPERIMENT}/RUN_COMPLETE.txt"

log() {
  local line
  line="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "${line}" | tee -a "${MAIN_LOG}"
}

run_python() {
  local name="$1"; shift
  local stdout_log="${LOG_DIR}/${name}_${RUN_ID}.stdout.log"
  local stderr_log="${LOG_DIR}/${name}_${RUN_ID}.stderr.log"
  log "START ${name}: ${PYTHON_BIN} $*"
  if "${PYTHON_BIN}" "$@" >"${stdout_log}" 2>"${stderr_log}"; then
    log "DONE ${name}: stdout=${stdout_log}; stderr=${stderr_log}"
  else
    local rc=$?
    log "FAILED ${name}: exit code ${rc}"
    log "STDOUT: ${stdout_log}"
    log "STDERR: ${stderr_log}"
    return ${rc}
  fi
}

baseline_complete() {
  local out_dir="$1"
  for f in episodes.jsonl episode_papers.jsonl evaluation_metrics.json dataset_summary.json main_experiment_table_top20.md; do
    if [[ ! -s "${out_dir}/${f}" ]]; then
      return 1
    fi
  done
  return 0
}

trap 'rc=$?; if [[ ${rc} -ne 0 ]]; then printf "Failed at %s\nLog: %s\n" "$(date)" "${MAIN_LOG}" >"${RUN_FAILED}"; log "Full run failed (exit ${rc})."; fi' EXIT

log "Full main-experiment baseline run started."
log "Project root: ${PROJECT_ROOT}"
log "Benchmark: ${BENCHMARK_DIR}"
log "Python: ${PYTHON_BIN}"
rm -f "${RUN_FAILED}"

clean_ready=1
for f in candidate_pools.jsonl labels_for_eval.jsonl episodes.jsonl users.json manifest.json; do
  if [[ ! -s "${CLEAN_INPUT}/${f}" ]]; then
    clean_ready=0
    break
  fi
done

if [[ ${clean_ready} -eq 0 ]]; then
  mkdir -p "${CLEAN_INPUT}"
  run_python "export_clean_baseline_input" \
    experiments/benchmark/export_clean_baseline_benchmark.py \
    --input-dir "${BENCHMARK_DIR}" \
    --output-dir "${CLEAN_INPUT}"
else
  log "Clean baseline input exists; reuse it."
fi

declare -a RUNS=(
  "scholar_inbox|experiments/main_experiment/run_baselines/run_scholar_inbox.py"
  "citation_enhanced|experiments/main_experiment/run_baselines/run_citation_enhanced.py"
  "discourse_aware|experiments/main_experiment/run_baselines/run_discourse_aware.py"
  "nl_profile|experiments/main_experiment/run_baselines/run_nl_profile.py"
  "knowledge_entity|experiments/main_experiment/run_baselines/run_knowledge_entity.py"
)

for entry in "${RUNS[@]}"; do
  key="${entry%%|*}"
  script="${entry##*|}"
  out_dir="${MAIN_EXPERIMENT}/${key}"
  if [[ ${FORCE} -eq 0 ]] && baseline_complete "${out_dir}"; then
    log "SKIP ${key}: complete output already exists."
    continue
  fi
  mkdir -p "${out_dir}"
  run_python "${key}" "${script}" \
    --input-dir "${CLEAN_INPUT}" \
    --output-dir "${out_dir}"
done

run_python "combine_tables" \
  experiments/main_experiment/_combine_baseline_tables.py \
  --benchmark-dir "${BENCHMARK_DIR}" \
  --main-experiment-dir "${MAIN_EXPERIMENT}"

printf "Completed at %s\nLog: %s\n" "$(date)" "${MAIN_LOG}" >"${RUN_COMPLETE}"
log "Full main-experiment baseline run completed."
