$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null
$runId = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$env:MEMORY_SYSTEM_STORAGE_BACKEND = "auto"
$env:MEMORY_SYSTEM_MEMORY_FILE = "data\runtime\benchmark_memory_$runId.json"
$env:MEMORY_SYSTEM_SQLITE_FILE = "data\runtime\benchmark_memory_$runId.sqlite3"
python -m src.memory_system.benchmarks.runner
