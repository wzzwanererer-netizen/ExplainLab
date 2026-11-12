# ExplainLab 首次安装：Python 依赖 + 前端依赖 + 数据库迁移
# 用法：powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Invoke-Checked {
  param([scriptblock]$Block)
  & $Block
  if ($LASTEXITCODE -ne 0) { throw "命令失败（退出码 $LASTEXITCODE）" }
}

Write-Host "[1/3] 安装 Python 依赖（uv workspace -> .venv）..."
Invoke-Checked { uv sync }

Write-Host "[2/3] 安装前端依赖（npm -> frontend/node_modules）..."
Push-Location frontend
Invoke-Checked { npm install }
Pop-Location

Write-Host "[3/3] 初始化数据库（Alembic upgrade head）..."
Push-Location backend
Invoke-Checked { uv run alembic upgrade head }
Pop-Location

Write-Host ""
Write-Host "安装完成。启动开发服务：scripts/dev.ps1"