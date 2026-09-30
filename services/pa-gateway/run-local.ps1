# 本地起 PA 网关（前台）。模型配置不用在这里给：服务启动时自己读服务 .env，
# 没有就读仓库根目录的 .env.local / .env 里应用已经配好的 ELFRED_MODEL_*（同一把 key）。
# 用法：powershell -ExecutionPolicy Bypass -File services/pa-gateway/run-local.ps1 [-Port 8790]
param([int]$Port = 8790)

Set-Location $PSScriptRoot
python -m uvicorn app.main:app --port $Port --host 127.0.0.1
