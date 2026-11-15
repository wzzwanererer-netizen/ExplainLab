# 全量质量检查：Python 测试 + lint + 前端测试 + 类型检查与构建
# 用法：powershell -ExecutionPolicy Bypass -File scripts/test.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Invoke-Checked {
  param([scriptblock]$Block)
  & $Block
  if ($LASTEXITCODE -ne 0) { throw "命令失败（退出码 $LASTEXITCODE）" }
}

Write-Host "== Python 测试（backend + knowledge-core）=="
Invoke-Checked { uv run pytest }

Write-Host "== Python lint =="
Invoke-Checked { uv run ruff check backend knowledge-core }

Write-Host "== 前端测试 =="
Push-Location frontend
Invoke-Checked { npm run test }

Write-Host "== 前端类型检查与生产构建 =="
Invoke-Checked { npm run build }
Pop-Location

Write-Host ""
Write-Host "全部通过"