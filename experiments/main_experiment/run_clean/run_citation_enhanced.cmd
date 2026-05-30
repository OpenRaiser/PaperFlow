@echo off
setlocal

set "BENCHMARK_DIR=%~1"
if "%BENCHMARK_DIR%"=="" set "BENCHMARK_DIR=data\benchmark_full_24users_20260301_20260419_show20_with_reading"

echo ============================================================
echo Citation-Enhanced baseline with clean, contamination-safe input
echo Benchmark: %BENCHMARK_DIR%
echo ============================================================
echo.

if not exist "%BENCHMARK_DIR%\episode_papers.jsonl" (
  echo [ERROR] Missing "%BENCHMARK_DIR%\episode_papers.jsonl"
  echo Run the Full PaperFlow benchmark first, then rerun this command.
  exit /b 1
)

if not exist "%BENCHMARK_DIR%\episodes.jsonl" (
  echo [ERROR] Missing "%BENCHMARK_DIR%\episodes.jsonl"
  echo Run the Full PaperFlow benchmark first, then rerun this command.
  exit /b 1
)

echo [1/2] Export clean baseline input...
python experiments\benchmark\export_clean_baseline_benchmark.py ^
  --input-dir "%BENCHMARK_DIR%" ^
  --output-dir "%BENCHMARK_DIR%\baseline_clean_input"
if errorlevel 1 exit /b 1

echo.
echo [2/2] Run Citation-Enhanced reranking baseline...
python experiments\main_experiment\run_baselines\run_citation_enhanced.py ^
  --input-dir "%BENCHMARK_DIR%\baseline_clean_input" ^
  --output-dir "%BENCHMARK_DIR%\main_experiment\citation_enhanced"
if errorlevel 1 exit /b 1

echo.
echo Done.
echo Output: %BENCHMARK_DIR%\main_experiment\citation_enhanced
