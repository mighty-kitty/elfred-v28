$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null

python -m src.memory_system.cli_app --user-id long-horizon-user --session-id long-horizon-session long-horizon-validation --limit 200
