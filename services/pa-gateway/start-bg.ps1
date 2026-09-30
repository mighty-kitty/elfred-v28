# 后台起 PA 网关（隐藏窗口），日志写到 %TEMP%。重复执行会先停掉旧进程。
$port = 8790
$log = Join-Path $env:TEMP 'pa-gateway.log'
$err = Join-Path $env:TEMP 'pa-gateway.err.log'

$old = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
foreach ($c in $old) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }

$runner = Join-Path $PSScriptRoot 'run-local.ps1'
$proc = Start-Process -FilePath 'powershell' -ArgumentList @('-ExecutionPolicy', 'Bypass', '-NoProfile', '-File', $runner) -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $err -PassThru
Write-Host "started pid=$($proc.Id) log=$log"

for ($i = 0; $i -lt 20; $i++) {
  Start-Sleep -Milliseconds 700
  try {
    $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/health" -TimeoutSec 3
    Write-Host "health: $($r.Content)"
    exit 0
  } catch { }
}
Write-Host 'health: 还没起来'
if (Test-Path $err) { Get-Content $err -Tail 15 }
