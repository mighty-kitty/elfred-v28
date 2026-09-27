$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null
$runId = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$sqliteRuntimeDir = Join-Path $env:TEMP "EMOS\runtime"
New-Item -ItemType Directory -Path $sqliteRuntimeDir -Force | Out-Null
$env:MEMORY_SYSTEM_STORAGE_BACKEND = "auto"
$env:MEMORY_SYSTEM_MEMORY_FILE = "data\runtime\pytest_memory_$runId.json"
$env:MEMORY_SYSTEM_SQLITE_FILE = Join-Path $sqliteRuntimeDir "pytest_memory_$runId.sqlite3"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_workflow.py tests/test_recall.py tests/test_abstraction_recall.py tests/test_embedding_backend.py tests/test_official_english_commit.py tests/test_strategy_config.py tests/test_snapshot.py tests/test_retrieval_settings.py tests/test_api.py tests/test_retrieval_trace.py tests/test_benchmark_summary.py tests/test_benchmark_dataset_stats.py tests/test_benchmark_adapters.py tests/test_benchmark_matching.py tests/test_benchmark_error_taxonomy.py tests/test_summary_memory.py tests/test_evidence_memory.py tests/test_evidence_recall.py tests/test_storage_backend.py tests/test_storage_report.py tests/test_storage_backup.py tests/test_user_report.py tests/test_system_report.py tests/test_delivery_pack.py tests/test_temporal_reasoning.py tests/test_temporal_retrieval.py tests/test_inference_features.py -q
