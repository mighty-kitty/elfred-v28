# 第二页 / 第四页 上游启停（PowerShell 版，直白四段式，避免解析器踩坑）
#
#   powershell -ExecutionPolicy Bypass -File tools/page2-checks/upstreams.ps1 start
#   powershell -ExecutionPolicy Bypass -File tools/page2-checks/upstreams.ps1 status
#   powershell -ExecutionPolicy Bypass -File tools/page2-checks/upstreams.ps1 stop
#
# 为什么要有这一版：从 Node 进程里起的子进程会随那个会话被回收；
# 在**你自己的终端窗口**里用 Start-Process 起，进程归系统管，能一直活着。
# node 那版（upstreams.mjs）继续负责 status / deps / preflight / stop。
param([ValidateSet("start", "status", "stop")][string]$Action = "status")

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$dataDir = Join-Path $root ".elfred-data"
$runDir = Join-Path $dataDir "upstreams"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$ftDir = "C:\Users\35057\Desktop\纪念-Elfred历史版本\elfred\FreeTodo-main\FreeTodo-main"
$ftPy = Join-Path $dataDir "freetodo-venv\Scripts\python.exe"
if (-not (Test-Path $ftPy)) { $ftPy = "python" }
$emosToken = ""
$envFile = Join-Path $root ".env.local"
if (Test-Path $envFile) {
  $hit = Select-String -Path $envFile -Pattern "^ELFRED_MEMORY_HUB_TOKEN=" | Select-Object -First 1
  if ($hit) { $emosToken = ($hit.Line -replace "^ELFRED_MEMORY_HUB_TOKEN=", "").Trim() }
}

function Show-Status {
  $ports = @(8001, 8200, 8790, 8765)
  $names = @("FreeTodo", "EMOS 记忆中枢", "PA 网关", "Skill Foundry")
  for ($i = 0; $i -lt 4; $i++) {
    $up = Get-NetTCPConnection -State Listen -LocalPort $ports[$i] -ErrorAction SilentlyContinue
    $state = "断"
    if ($up) { $state = "通" }
    "{0,-16} {1,-6} {2}" -f $names[$i], $ports[$i], $state
  }
}

function Start-One([string]$key, [string]$title, [string]$exe, [string[]]$arguments, [string]$workDir, [hashtable]$extraEnv) {
  $pidPath = Join-Path $runDir "$key.pid"
  foreach ($k in $extraEnv.Keys) { Set-Item -Path "Env:$k" -Value $extraEnv[$k] }
  # 注意：标准输出和错误输出不能指向同一个文件，PowerShell 会直接拒绝
  $proc = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $workDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDir "$key.log") -RedirectStandardError (Join-Path $runDir "$key.err.log")
  Set-Content -Path $pidPath -Value $proc.Id
  "{0,-16} 启动中（pid {1}）" -f $title, $proc.Id
  foreach ($k in $extraEnv.Keys) { Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue }
}

function Stop-One([string]$key, [string]$title) {
  $pidPath = Join-Path $runDir "$key.pid"
  if (-not (Test-Path $pidPath)) { "{0,-16} 没有 pid 记录，不动它" -f $title; return }
  $target = [int](Get-Content $pidPath)
  taskkill /PID $target /T /F | Out-Null
  "{0,-16} 已停（pid {1}）" -f $title, $target
}

if ($Action -eq "status") { Show-Status }

if ($Action -eq "start") {
  Start-One "freetodo" "FreeTodo" $ftPy @("-m", "lifetrace.server") $ftDir @{ PYTHONUTF8 = "1" }
  Start-One "emos" "EMOS 记忆中枢" "python" @("-m", "src.memory_system.api.elfred_bridge") (Join-Path $root "services\emos-memory") @{ ELFRED_MEMORY_HUB_TOKEN = $emosToken; ELFRED_EMOS_PORT = "8200"; ELFRED_EMOS_DATABASE = (Join-Path $dataDir "emos-memory.sqlite") }
  Start-One "gateway" "PA 网关" "python" @("-m", "uvicorn", "app.main:app", "--port", "8790", "--host", "127.0.0.1") (Join-Path $root "services\pa-gateway") @{}
  Start-One "foundry" "Skill Foundry" "uv" @("run", "--frozen", "python", "-m", "adapter") (Join-Path $root "services\skill-foundry") @{ FREETODO_BASE_URL = "http://127.0.0.1:8001"; ELFRED_ADAPTER_PORT = "8765" }
  "`n等 20 秒后跑 status 看结果。"
}

if ($Action -eq "stop") {
  Stop-One "foundry" "Skill Foundry"
  Stop-One "gateway" "PA 网关"
  Stop-One "emos" "EMOS 记忆中枢"
  Stop-One "freetodo" "FreeTodo"
}
