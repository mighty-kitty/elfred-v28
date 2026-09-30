# 重启本地 Elfred（隐藏窗口）并等它起来。日志写到 %TEMP%\elfred-app.log。
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$log = Join-Path $env:TEMP 'elfred-app.log'
$err = Join-Path $env:TEMP 'elfred-app.err.log'

Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -match 'start-local\.mjs|npm-cli\.js" run dev:local' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3

Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', "npm run dev:local > `"$log`" 2> `"$err`"") -WorkingDirectory $root -WindowStyle Hidden

for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 1
  try {
    $r = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3000/api/elfred/health/deps' -TimeoutSec 3
    if ($r.StatusCode -eq 200 -or $r.StatusCode -eq 401) { Write-Host "app up after ${i}s (status $($r.StatusCode))"; exit 0 }
  } catch {
    if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) { Write-Host "app up after ${i}s (401 = 需要登录，正常)"; exit 0 }
  }
}
Write-Host 'app 还没起来'
Get-Content $err -Tail 20 -ErrorAction SilentlyContinue
