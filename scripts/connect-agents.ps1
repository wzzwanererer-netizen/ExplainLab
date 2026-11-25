<#
.SYNOPSIS
  检测本机已安装的美国 4 家 + 中国 6 家 Agent，并可选一键注册 ExplainLab 本地 MCP Server。
  默认仅 Dry-Run 预览，不修改任何文件；加 -Apply 参数才执行写入（自动生成 .bak-explainlab 备份）。
#>
param(
  [switch]$Apply
)

$ErrorActionPreference = "Stop"
$McpCmd = "D:\ExplainLab\scripts\explainlab-mcp.cmd"
$ApiUrl = "http://127.0.0.1:8000"

if (-not (Test-Path $McpCmd)) {
  Write-Error "未找到 MCP 启动脚本: $McpCmd"
  exit 1
}

$JsonTargets = @(
  @{ Name = "Anthropic Claude Code"; Dir = "$env:USERPROFILE\.claude"; File = "$env:USERPROFILE\.claude.json" },
  @{ Name = "Anthropic Claude Desktop"; Dir = "$env:APPDATA\Claude"; File = "$env:APPDATA\Claude\claude_desktop_config.json" },
  @{ Name = "Google Antigravity / Gemini"; Dir = "$env:USERPROFILE\.gemini\config"; File = "$env:USERPROFILE\.gemini\config\mcp_config.json" },
  @{ Name = "Cursor"; Dir = "$env:USERPROFILE\.cursor"; File = "$env:USERPROFILE\.cursor\mcp.json" },
  @{ Name = "WorkBuddy"; Dir = "$env:USERPROFILE\.workbuddy\connectors\default"; File = "$env:USERPROFILE\.workbuddy\connectors\default\mcp.json" },
  @{ Name = "Trae CN"; Dir = "$env:APPDATA\Trae CN\User"; File = "$env:APPDATA\Trae CN\User\mcp.json" },
  @{ Name = "Qoder"; Dir = "$env:USERPROFILE\.qoder"; File = "$env:USERPROFILE\.qoder\mcp.json" },
  @{ Name = "Kimi Code"; Dir = "$env:USERPROFILE\.kimi-code"; File = "$env:USERPROFILE\.kimi-code\mcp.json" }
)

$CodexToml = "$env:USERPROFILE\.codex\config.toml"

Write-Host "=== ExplainLab MCP 多 Agent 接入检查 ===" -ForegroundColor Cyan
Write-Host ("模式: " + ($(if ($Apply) { "APPLY（写入并自动备份）" } else { "DRY-RUN（仅预览，不修改文件）" })))
Write-Host ""

foreach ($t in $JsonTargets) {
  $installed = Test-Path $t.Dir
  $exists = Test-Path $t.File
  if (-not $installed) {
    Write-Host ("[跳过] {0,-28} 未检测到目录: {1}" -f $t.Name, $t.Dir) -ForegroundColor DarkGray
    continue
  }

  if (-not $Apply) {
    $status = if ($exists) { "将合并 explainlab 到已有 JSON" } else { "将新建 MCP JSON" }
    Write-Host ("[就绪] {0,-28} {1} -> {2}" -f $t.Name, $status, $t.File) -ForegroundColor Green
    continue
  }

  $obj = [PSCustomObject]@{}
  if ($exists) {
    Copy-Item -Path $t.File -Destination ($t.File + ".bak-explainlab") -Force
    $raw = Get-Content -Path $t.File -Raw -Encoding UTF8
    if (-not [string]::IsNullOrWhiteSpace($raw)) {
      $parsed = $raw | ConvertFrom-Json
      if ($null -ne $parsed) { $obj = $parsed }
    }
  }
  if (-not ($obj.PSObject.Properties.Name -contains "mcpServers") -or $null -eq $obj.mcpServers) {
    $obj | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{}) -Force
  }
  $entry = [PSCustomObject]@{
    command = $McpCmd
    env = [PSCustomObject]@{ EXPLAINLAB_API_URL = $ApiUrl }
  }
  $obj.mcpServers | Add-Member -NotePropertyName "explainlab" -NotePropertyValue $entry -Force
  $jsonOut = $obj | ConvertTo-Json -Depth 10
  [System.IO.File]::WriteAllText($t.File, $jsonOut, [System.Text.UTF8Encoding]::new($false))
  Write-Host ("[已接入] {0,-26} {1}" -f $t.Name, $t.File) -ForegroundColor Green
}

# OpenAI Codex (TOML)
if (Test-Path "$env:USERPROFILE\.codex") {
  $hasEntry = $false
  if (Test-Path $CodexToml) {
    $rawToml = Get-Content -Path $CodexToml -Raw -Encoding UTF8
    $hasEntry = $rawToml -match '(?m)^\[mcp_servers\.explainlab\]'
  }
  if (-not $Apply) {
    $msg = if ($hasEntry) { "已存在 [mcp_servers.explainlab]" } else { "将追加 [mcp_servers.explainlab]" }
    Write-Host ("[就绪] {0,-28} {1} -> {2}" -f "OpenAI Codex", $msg, $CodexToml) -ForegroundColor Green
  } elseif (-not $hasEntry) {
    if (Test-Path $CodexToml) {
      Copy-Item -Path $CodexToml -Destination ($CodexToml + ".bak-explainlab") -Force
    }
    $block = "`n[mcp_servers.explainlab]`ncommand = `"D:\\ExplainLab\\scripts\\explainlab-mcp.cmd`"`nenv = { EXPLAINLAB_API_URL = `"$ApiUrl`" }`n"
    [System.IO.File]::AppendAllText($CodexToml, $block, [System.Text.UTF8Encoding]::new($false))
    Write-Host ("[已接入] {0,-26} {1}" -f "OpenAI Codex", $CodexToml) -ForegroundColor Green
  } else {
    Write-Host ("[已存在] {0,-26} {1}" -f "OpenAI Codex", $CodexToml) -ForegroundColor Yellow
  }
}

Write-Host ""
Write-Host "提示：ZCode 与 DSH 桌面端建议在其客户端「设置 -> MCP」中直接填入命令：" -ForegroundColor Cyan
Write-Host "  $McpCmd"
if (-not $Apply) {
  Write-Host ""
  Write-Host "确认无误后运行以下命令即可一键写入：" -ForegroundColor Yellow
  Write-Host "  powershell -ExecutionPolicy Bypass -File D:\ExplainLab\scripts\connect-agents.ps1 -Apply"
}
