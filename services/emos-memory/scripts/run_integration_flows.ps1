$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null
$runId = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$sqliteRuntimeDir = Join-Path $env:TEMP "EMOS\runtime"
New-Item -ItemType Directory -Path $sqliteRuntimeDir -Force | Out-Null
$env:MEMORY_SYSTEM_STORAGE_BACKEND = "auto"
$env:MEMORY_SYSTEM_MEMORY_FILE = "data\runtime\integration_memory_$runId.json"
$env:MEMORY_SYSTEM_SQLITE_FILE = Join-Path $sqliteRuntimeDir "integration_memory_$runId.sqlite3"
$env:MEMORY_SYSTEM_FEEDBACK_STORE_FILE = "data\runtime\integration_feedback_$runId.json"
$env:MEMORY_SYSTEM_INTERACTION_LOG_FILE = "data\runtime\integration_interactions_$runId.jsonl"
python -m src.memory_system.cli_app --user-id delivery-demo --session-id delivery-session-$runId run-integration-flows --limit 200
