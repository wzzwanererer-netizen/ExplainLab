<#
.SYNOPSIS
  检测本机已安装的美国 4 家 + 中国 6 家 Agent，并可选一键注册 ExplainLab 本地 MCP Server。
  默认仅 Dry-Run 预览，不修改任何文件；加 -Apply 参数才执行写入（自动生成 .bak-explainlab 备份）。
#>
param(
  [switch]$Apply,
  [switch]$InstallRules
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
Write-Host "=== ExplainLab 自动记忆沉淀全局规则（让 Agent 主动录入对话知识）===" -ForegroundColor Cyan

$RuleTargets = @(
  @{ Name = "Anthropic Claude Code"; Dir = "$env:USERPROFILE\.claude"; File = "$env:USERPROFILE\.claude\CLAUDE.md"; AgentName = "Claude" },
  @{ Name = "OpenAI Codex"; Dir = "$env:USERPROFILE\.codex"; File = "$env:USERPROFILE\.codex\AGENTS.md"; AgentName = "Codex" },
  @{ Name = "Google Antigravity / Gemini"; Dir = "$env:USERPROFILE\.gemini"; File = "$env:USERPROFILE\.gemini\GEMINI.md"; AgentName = "Antigravity" },
  @{ Name = "Cursor"; Dir = "$env:USERPROFILE\.cursor"; File = "$env:USERPROFILE\.cursor\rules\explainlab-memory.mdc"; AgentName = "Cursor" },
  @{ Name = "Qoder"; Dir = "$env:USERPROFILE\.qoder"; File = "$env:USERPROFILE\.qoder\AGENTS.md"; AgentName = "Qoder" }
)

$MarkerStart = "<!-- EXPLAINLAB-AUTO-MEMORY:START -->"
$MarkerEnd = "<!-- EXPLAINLAB-AUTO-MEMORY:END -->"

foreach ($r in $RuleTargets) {
  if (-not (Test-Path $r.Dir)) {
    continue
  }
  $ruleBlock = @"
$MarkerStart
## ExplainLab 个人知识库自动记忆协议（必须遵守）

你已接入本地 `explainlab` MCP Server（用户的跨 Agent 统一长期记忆外脑）。请自动遵守：
1. **先查后答**：当用户提及历史项目决策、个人偏好、既往踩坑或跨工具上下文时，先调用 `explainlab_search_knowledge` 检索已有记忆。
2. **自动沉淀（无需用户每次提醒）**：当本轮对话产出了**有价值的结论、架构规划、关键排错经验、新概念总结或明确的用户长期偏好**时，主动调用 `explainlab_record_knowledge`（务必传入 `agent_name: "$($r.AgentName)"` 和简明标签 `tags`）将其沉淀到 ExplainLab；若与旧知识有关联，顺手调用 `explainlab_link_knowledge` 建立图谱连线。
3. **只记高价值，严守安全**：不要记录寒暄、纯过程日志或一次性临时问答；严禁写入任何 API Key、密码、Token 或敏感凭证。
$MarkerEnd
"@
  $fileExists = Test-Path $r.File
  $alreadyHas = $false
  if ($fileExists) {
    $rawRule = Get-Content -Path $r.File -Raw -Encoding UTF8
    $alreadyHas = $rawRule -match [regex]::Escape($MarkerStart)
  }

  if (-not ($Apply -or $InstallRules)) {
    $rStatus = if ($alreadyHas) { "已存在自动记忆规则" } elseif ($fileExists) { "将追加自动记忆规则" } else { "将新建全局规则文件" }
    Write-Host ("[规则就绪] {0,-26} {1} -> {2}" -f $r.Name, $rStatus, $r.File) -ForegroundColor Green
    continue
  }

  $parentDir = Split-Path -Parent $r.File
  if (-not (Test-Path $parentDir)) {
    New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
  }
  if ($alreadyHas) {
    Write-Host ("[规则已有] {0,-26} {1}" -f $r.Name, $r.File) -ForegroundColor Yellow
  } elseif ($fileExists) {
    Copy-Item -Path $r.File -Destination ($r.File + ".bak-explainlab") -Force
    [System.IO.File]::AppendAllText($r.File, "`n`n$ruleBlock`n", [System.Text.UTF8Encoding]::new($false))
    Write-Host ("[规则已写] {0,-26} {1}" -f $r.Name, $r.File) -ForegroundColor Green
  } else {
    [System.IO.File]::WriteAllText($r.File, "$ruleBlock`n", [System.Text.UTF8Encoding]::new($false))
    Write-Host ("[规则新建] {0,-26} {1}" -f $r.Name, $r.File) -ForegroundColor Green
  }
}

Write-Host ""
Write-Host "提示：ZCode 与 DSH 桌面端建议在其客户端「设置 -> MCP」中直接填入命令：" -ForegroundColor Cyan
Write-Host "  $McpCmd"
Write-Host "并在其「自定义系统提示词 / 角色规则」中粘贴 ExplainLab 自动记忆规则。" -ForegroundColor Cyan
if (-not ($Apply -or $InstallRules)) {
  Write-Host ""
  Write-Host "确认无误后运行以下命令即可一键接入 MCP + 写入自动记忆规则：" -ForegroundColor Yellow
  Write-Host "  powershell -ExecutionPolicy Bypass -File D:\ExplainLab\scripts\connect-agents.ps1 -Apply"
}
