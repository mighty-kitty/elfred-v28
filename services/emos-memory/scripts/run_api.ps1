$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null
if (-not $env:MEMORY_SYSTEM_STORAGE_BACKEND) { $env:MEMORY_SYSTEM_STORAGE_BACKEND = "sqlite" }
if (-not $env:MEMORY_SYSTEM_MEMORY_FILE) { $env:MEMORY_SYSTEM_MEMORY_FILE = "data\runtime\api_memory.json" }
if (-not $env:MEMORY_SYSTEM_SQLITE_FILE) { $env:MEMORY_SYSTEM_SQLITE_FILE = "data\runtime\api_memory.sqlite3" }
if (-not $env:MEMORY_SYSTEM_API_PORT) { $env:MEMORY_SYSTEM_API_PORT = "8200" }
python -m src.memory_system.api.server
