@echo off
setlocal EnableExtensions

cd /d "%~dp0..\.."

set "LLM_PARSER_OPENAI_MODEL=gemini-3-flash-preview"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "OUT_DIR=data\benchmark_full_24users_20260301_20260419_show20_with_reading"

echo ============================================================
echo PaperFlow full benchmark: 24 users x 50 days, Top-20, reading
echo Workspace: %CD%
echo Output:    %OUT_DIR%
echo ============================================================
echo.

echo [1/7] Stop any existing historical simulation process...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*simulate_historical_episodes.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
if errorlevel 1 goto :fail

echo.
echo [2/7] Clean previous benchmark output in this workspace...
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
if errorlevel 1 goto :fail

if exist data\token_usage.jsonl del /q data\token_usage.jsonl
if errorlevel 1 goto :fail

if exist data\embeddings_cache rmdir /s /q data\embeddings_cache
if errorlevel 1 goto :fail
mkdir data\embeddings_cache
if errorlevel 1 goto :fail

echo.
echo [3/7] Reset benchmark state, preserving papers and reseeding profiles...
python scripts\clear_database.py --action benchmark_reset --yes
if errorlevel 1 goto :fail

echo.
echo [4/7] Run full simulation with fixed paper database...
python experiments\simulation\simulate_historical_episodes.py ^
  --start-date 20260301 ^
  --end-date 20260419 ^
  --skip-paper-collection ^
  --show-count 20 ^
  --llm-model "gemini-3-flash-preview" ^
  --embedding-model "Qwen/Qwen3-Embedding-8B" ^
  --output-dir "%OUT_DIR%"
if errorlevel 1 goto :fail

echo.
echo [5/7] Evaluate recommendation metrics...
python experiments\benchmark\evaluate_simulation_metrics.py ^
  --input-dir "%OUT_DIR%" ^
  --ks 5 10 20 ^
  --method-name "Full PaperFlow Pipeline"
if errorlevel 1 goto :fail

echo.
echo [6/7] Export human audit subset...
python experiments\benchmark\export_human_audit_subset.py ^
  --input-dir "%OUT_DIR%" ^
  --shown-only ^
  --sample-size 500 ^
  --seed 42
if errorlevel 1 goto :fail

echo.
echo [7/7] Done. Key outputs:
echo   %OUT_DIR%\simulation_summary.json
echo   %OUT_DIR%\dataset_summary.md
echo   %OUT_DIR%\main_experiment_table_top20.md
echo   %OUT_DIR%\case_metrics_table_top20.md
echo   %OUT_DIR%\evaluation_metrics.json
echo   %OUT_DIR%\human_audit_subset.csv
echo   %OUT_DIR%\reading_reports.jsonl
echo   %OUT_DIR%\reading_reports_md\
echo.
echo Full benchmark completed successfully.
goto :eof

:fail
echo.
echo Benchmark failed. Check the console output above.
exit /b 1
