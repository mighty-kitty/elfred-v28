$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null

python -m src.memory_system.cli_app long-horizon-summary-report --limit 5
