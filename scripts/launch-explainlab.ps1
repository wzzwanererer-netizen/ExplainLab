<#
.SYNOPSIS
  ExplainLab 原生桌面应用启动器（独立 Electron 桌面进程，不依赖 Edge 浏览器）。
#>
$ErrorActionPreference = "Stop"
$ElectronExe = "D:\ExplainLab\desktop\node_modules\electron\dist\electron.exe"
$DesktopApp = "D:\ExplainLab\desktop"

if (-not (Test-Path $ElectronExe)) {
  Write-Error "未找到 Electron 运行时，请先在 D:\ExplainLab\desktop 执行 npm install"
  exit 1
}

Start-Process -FilePath $ElectronExe -ArgumentList "`"$DesktopApp`"" -WorkingDirectory $DesktopApp
