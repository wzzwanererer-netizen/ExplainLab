# 在两个独立窗口中分别启动前后端开发服务；关闭对应窗口即停止服务。
# 用法：powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$root\backend'; uv run uvicorn app.main:app --reload --port 8000"
)
Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$root\frontend'; npm run dev"
)

Write-Host "后端: http://127.0.0.1:8000/api/health"
Write-Host "前端: http://localhost:5173"
Write-Host "两个服务分别在独立窗口运行，关闭对应窗口即停止。"