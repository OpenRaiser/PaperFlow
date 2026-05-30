param(
  [string]$BenchmarkDir = "data\benchmark_full_24users_20260301_20260419_show20_with_reading",
  [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptRoot "..\..")).Path
Set-Location $ProjectRoot

$BenchmarkPath = (Resolve-Path $BenchmarkDir).Path
$CleanInputPath = Join-Path $BenchmarkPath "baseline_clean_input"
$MainExperimentPath = Join-Path $BenchmarkPath "main_experiment"
$LogPath = Join-Path $MainExperimentPath "logs"
New-Item -ItemType Directory -Force -Path $MainExperimentPath, $LogPath | Out-Null

$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$MainLog = Join-Path $LogPath "full_baseline_run_$RunId.log"
$PythonExe = (Get-Command python).Source
$RunFailedPath = Join-Path $MainExperimentPath "RUN_FAILED.txt"
$RunCompletePath = Join-Path $MainExperimentPath "RUN_COMPLETE.txt"

function Write-RunLog {
  param([string]$Message)
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $MainLog -Value $line -Encoding UTF8
  Write-Host $line
}

function Test-NonEmptyFile {
  param([string]$Path)
  return (Test-Path $Path -PathType Leaf) -and ((Get-Item $Path).Length -gt 0)
}

function Invoke-PythonLogged {
  param(
    [string[]]$Arguments,
    [string]$Name
  )

  $stdoutLog = Join-Path $LogPath "$Name`_$RunId.stdout.log"
  $stderrLog = Join-Path $LogPath "$Name`_$RunId.stderr.log"
  Write-RunLog ("START {0}: {1} {2}" -f $Name, $PythonExe, ($Arguments -join " "))

  $process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList $Arguments `
    -WorkingDirectory $ProjectRoot `
    -Wait `
    -PassThru `
    -NoNewWindow `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

  if ($process.ExitCode -ne 0) {
    Write-RunLog ("FAILED {0}: exit code {1}" -f $Name, $process.ExitCode)
    Write-RunLog ("STDOUT: {0}" -f $stdoutLog)
    Write-RunLog ("STDERR: {0}" -f $stderrLog)
    throw "$Name failed with exit code $($process.ExitCode)"
  }

  Write-RunLog ("DONE {0}: stdout={1}; stderr={2}" -f $Name, $stdoutLog, $stderrLog)
}

function Test-BaselineComplete {
  param([string]$OutputDir)
  $required = @(
    "episodes.jsonl",
    "episode_papers.jsonl",
    "evaluation_metrics.json",
    "dataset_summary.json",
    "main_experiment_table_top20.md"
  )
  foreach ($fileName in $required) {
    if (-not (Test-NonEmptyFile (Join-Path $OutputDir $fileName))) {
      return $false
    }
  }
  return $true
}

Write-RunLog "Full main-experiment baseline run started."
Write-RunLog "Project root: $ProjectRoot"
Write-RunLog "Benchmark: $BenchmarkPath"
Write-RunLog "Python: $PythonExe"
Remove-Item -Path $RunFailedPath -ErrorAction SilentlyContinue

$cleanRequired = @("candidate_pools.jsonl", "labels_for_eval.jsonl", "episodes.jsonl", "users.json", "manifest.json")
$cleanReady = $true
foreach ($fileName in $cleanRequired) {
  if (-not (Test-NonEmptyFile (Join-Path $CleanInputPath $fileName))) {
    $cleanReady = $false
    break
  }
}

if (-not $cleanReady) {
  New-Item -ItemType Directory -Force -Path $CleanInputPath | Out-Null
  Invoke-PythonLogged `
    -Name "export_clean_baseline_input" `
    -Arguments @(
      "experiments\benchmark\export_clean_baseline_benchmark.py",
      "--input-dir", $BenchmarkPath,
      "--output-dir", $CleanInputPath
    )
} else {
  Write-RunLog "Clean baseline input exists; reuse it."
}

$runs = @(
  @{ Key = "scholar_inbox"; Name = "scholar_inbox"; Script = "experiments\main_experiment\run_baselines\run_scholar_inbox.py" },
  @{ Key = "citation_enhanced"; Name = "citation_enhanced"; Script = "experiments\main_experiment\run_baselines\run_citation_enhanced.py" },
  @{ Key = "discourse_aware"; Name = "discourse_aware"; Script = "experiments\main_experiment\run_baselines\run_discourse_aware.py" },
  @{ Key = "nl_profile"; Name = "nl_profile"; Script = "experiments\main_experiment\run_baselines\run_nl_profile.py" },
  @{ Key = "knowledge_entity"; Name = "knowledge_entity"; Script = "experiments\main_experiment\run_baselines\run_knowledge_entity.py" }
)

try {
  foreach ($run in $runs) {
    $outputDir = Join-Path $MainExperimentPath $run["Key"]
    if ((-not $Force) -and (Test-BaselineComplete $outputDir)) {
      Write-RunLog ("SKIP {0}: complete output already exists." -f $run["Name"])
      continue
    }

    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    Invoke-PythonLogged `
      -Name $run["Name"] `
      -Arguments @(
        $run["Script"],
        "--input-dir", $CleanInputPath,
        "--output-dir", $outputDir
      )
  }

  Invoke-PythonLogged `
    -Name "combine_tables" `
    -Arguments @(
      "experiments\main_experiment\_combine_baseline_tables.py",
      "--benchmark-dir", $BenchmarkPath,
      "--main-experiment-dir", $MainExperimentPath
    )

  Set-Content -Path $RunCompletePath -Value ("Completed at {0}`nLog: {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $MainLog) -Encoding UTF8
  Write-RunLog "Full main-experiment baseline run completed."
} catch {
  Set-Content -Path $RunFailedPath -Value ("Failed at {0}`nLog: {1}`nError: {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $MainLog, $_.Exception.Message) -Encoding UTF8
  Write-RunLog ("Full run failed: {0}" -f $_.Exception.Message)
  throw
}
