$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null
$runId = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$sqliteRuntimeDir = Join-Path $env:TEMP "EMOS\runtime"
New-Item -ItemType Directory -Path $sqliteRuntimeDir -Force | Out-Null
$env:MEMORY_SYSTEM_STORAGE_BACKEND = "auto"
$env:MEMORY_SYSTEM_MEMORY_FILE = "data\runtime\delivery_memory_$runId.json"
$env:MEMORY_SYSTEM_SQLITE_FILE = Join-Path $sqliteRuntimeDir "delivery_memory_$runId.sqlite3"
python -m src.memory_system.cli_app delivery-pack
