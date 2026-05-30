@echo off
setlocal EnableExtensions

cd /d "%~dp0..\.."

set "MODE=%~1"

if "%MODE%"=="" goto :usage

set "START_DATE=20260301"
set "SHOW_COUNT=20"
set "DRIFT_PROBABILITY=0.5"
if "%LLM_PARSER_OPENAI_MODEL%"=="" (
    set "LLM_MODEL=gemini-3-flash-preview"
) else (
    set "LLM_MODEL=%LLM_PARSER_OPENAI_MODEL%"
)
set "EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B"

if /I "%MODE%"=="case" (
    set "END_DATE=20260315"
    set "OUT_DIR=data\benchmark_case_3users_20260301_20260315_show20_with_reading"
    set "USER_ARGS=--user-ids user_role1 user_role2 user_role3"
) else if /I "%MODE%"=="full" (
    set "END_DATE=20260419"
    set "OUT_DIR=data\benchmark_24users_20260301_20260419_show20_with_reading"
    set "USER_ARGS=--user-count 24"
) else (
    goto :usage
)

if exist "%OUT_DIR%" (
    echo Removing previous output directory only: %OUT_DIR%
    rmdir /s /q "%OUT_DIR%"
)

if exist "data\token_usage.jsonl" (
    echo Removing previous token log only: data\token_usage.jsonl
    del /q "data\token_usage.jsonl"
)

echo Running PaperFlow reading benchmark: %MODE%
echo Output: %OUT_DIR%
echo.
echo Resetting benchmark state: profiles, behavior_logs, task_status.
echo Papers table is preserved.
echo.

python scripts\clear_database.py --action benchmark_reset --yes
if errorlevel 1 exit /b %errorlevel%

echo NOTE: This command intentionally does not pass --skip-reading-reports.
echo NOTE: --skip-paper-collection keeps the fixed paper database untouched.
echo.

python experiments\simulation\simulate_historical_episodes.py ^
    --start-date %START_DATE% ^
    --end-date %END_DATE% ^
    %USER_ARGS% ^
    --skip-paper-collection ^
    --show-count %SHOW_COUNT% ^
    --drift-probability %DRIFT_PROBABILITY% ^
    --llm-model "%LLM_MODEL%" ^
    --embedding-model "%EMBEDDING_MODEL%" ^
    --output-dir "%OUT_DIR%"
if errorlevel 1 exit /b %errorlevel%

python experiments\benchmark\evaluate_simulation_metrics.py ^
    --input-dir "%OUT_DIR%" ^
    --ks 5 10 20 ^
    --method-name "Full PaperFlow Pipeline"
if errorlevel 1 exit /b %errorlevel%

python experiments\benchmark\export_human_audit_subset.py ^
    --input-dir "%OUT_DIR%" ^
    --shown-only ^
    --sample-size 200 ^
    --seed 42
if errorlevel 1 exit /b %errorlevel%

echo.
echo Benchmark complete: %OUT_DIR%
exit /b 0

:usage
echo Usage:
echo   experiments\benchmark\run_reading_benchmark.cmd case
echo   experiments\benchmark\run_reading_benchmark.cmd full
echo.
echo Modes:
echo   case  = 3 users, 2026-03-01 to 2026-03-15, with reading reports
echo   full  = 24 users, 2026-03-01 to 2026-04-19, with reading reports
echo.
echo The script never clears papers from data\paperflow.db.
echo It always resets profiles, behavior logs, task status, output files, and token logs.
exit /b 2
