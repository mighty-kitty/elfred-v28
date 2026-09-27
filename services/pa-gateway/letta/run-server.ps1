# Start / stop / inspect the local Letta App Server (WP-01).
#
#   powershell -File services\elfred-pa-gateway\letta\run-server.ps1 start
#   powershell -File services\elfred-pa-gateway\letta\run-server.ps1 status
#   powershell -File services\elfred-pa-gateway\letta\run-server.ps1 restart
#
# This runs Letta NATIVELY (`npm i -g @letta-ai/letta-code`). Docker is not used
# on this machine: Huorong blocks the AF_UNIX socket Docker Desktop needs, which
# is why the containers were abandoned. State lives in %USERPROFILE%\.letta, so
# agents and message history survive restarts; the capability token lives in
# ws-token inside that folder and is never committed.
param([Parameter(Position = 0)][string]$Action = "status")

$ErrorActionPreference = "Continue"
$Port = 4500
$LettaHome = Join-Path $env:USERPROFILE ".letta"
$TokenFile = Join-Path $LettaHome "ws-token"
$LogDir = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "logs"
$LettaCmd = Join-Path $env:APPDATA "npm\letta.cmd"

function Get-Listener {
    return Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Start-Letta {
    if (Get-Listener) { "letta already listening on :$Port"; return }
    if (-not (Test-Path $LettaCmd)) {
        "letta CLI not found at $LettaCmd - run: npm i -g @letta-ai/letta-code"
        return
    }
    if (-not (Test-Path $TokenFile)) {
        "capability token missing at $TokenFile - run letta\provision.sh first"
        return
    }
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
    # No -RedirectStandardOutput here: `letta.cmd` is a batch wrapper, and
    # Start-Process waits for the whole batch to exit when its output is
    # redirected - which never happens for a server. Letta keeps its own logs in
    # $LettaHome instead.
    Start-Process -FilePath $LettaCmd `
        -ArgumentList @("server", "--listen", "ws://0.0.0.0:$Port", "--openai-api",
                        "--ws-auth", "capability-token", "--ws-token-file", $TokenFile) `
        -WorkingDirectory $LettaHome -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if (Get-Listener) { "letta listening on :$Port"; return }
        Start-Sleep -Seconds 2
    }
    "letta did NOT come up on :$Port - see logs\letta.err.log"
}

function Stop-Letta {
    $listener = Get-Listener
    if (-not $listener) { "letta already stopped"; return }
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $listener.OwningProcess)
    if ([string]$process.CommandLine -notmatch "letta") {
        "port :$Port is held by an unrelated process (pid " + $listener.OwningProcess + "); not stopping"
        return
    }
    Stop-Process -Id $listener.OwningProcess -Force
    "letta stopped (pid " + $listener.OwningProcess + ")"
}

function Get-Token {
    if (-not (Test-Path $TokenFile)) { return "" }
    return (Get-Content $TokenFile -Raw).Trim()
}

function Show-Status {
    $listener = Get-Listener
    if (-not $listener) { "letta :$Port DOWN"; return }
    "letta :$Port UP (pid " + $listener.OwningProcess + ")"
    try {
        $token = Get-Token
        $headers = @{}
        if ($token) { $headers = @{ Authorization = "Bearer $token" } }
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/v1/models" -Headers $headers `
            -TimeoutSec 8 -UseBasicParsing
        $body = $response.Content
        if ($body.Length -gt 160) { $body = $body.Substring(0, 160) }
        $body
    } catch {
        "models probe failed: " + $_.Exception.Message.Split([char]10)[0]
    }
}

switch ($Action) {
    "start" { Start-Letta }
    "stop" { Stop-Letta }
    "restart" { Stop-Letta; Start-Sleep -Seconds 2; Start-Letta }
    "status" { Show-Status }
    default { "usage: run-server.ps1 [start|stop|restart|status]" }
}
