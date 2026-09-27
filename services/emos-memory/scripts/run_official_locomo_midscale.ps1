param(
    [int]$MaxSamples = 500
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null
$runId = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$env:MEMORY_SYSTEM_STORAGE_BACKEND = "auto"
$env:MEMORY_SYSTEM_MEMORY_FILE = "data\runtime\official_locomo_midscale_$runId.json"
$env:MEMORY_SYSTEM_SQLITE_FILE = "data\runtime\official_locomo_midscale_$runId.sqlite3"
python -m src.memory_system.benchmarks.runner --benchmark-root data\benchmarks\official --benchmark locomo_official_full --skip-comparison --max-samples $MaxSamples
