<#
.SYNOPSIS
    via54Medit 监控统计与飞书同步工具 (medit-telemetry) 一句话部署脚本 (Windows PowerShell)

.DESCRIPTION
    在新设备或现有环境中，自动定位 Python 解释器、注册独立模块、配置花名与飞书凭据、
    安装开机自启、创建桌面 TraeWork 伴随启动器并启动后台主动监控守护进程。

.EXAMPLE
    # 本地一键无交互静默部署
    powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Silent

    # 带花名与指定周报时间部署
    powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Nickname "wtg" -Weekly "Friday 18:00" -Silent

    # 远程单行部署 (下载即跑)
    irm https://raw.githubusercontent.com/veawho/via54Medit/main/telemetry/deploy.ps1 | iex
#>

[CmdletBinding()]
param (
    [Parameter(Position=0, Mandatory=$false)]
    [string]$Instruction = "",

    [Parameter(Mandatory=$false)]
    [string]$Nickname = "",

    [Parameter(Mandatory=$false)]
    [string]$OpenId = "",

    [Parameter(Mandatory=$false)]
    [string]$AppId = "",

    [Parameter(Mandatory=$false)]
    [string]$AppSecret = "",

    [Parameter(Mandatory=$false)]
    [string]$Bitable = "",

    [Parameter(Mandatory=$false)]
    [string]$Weekly = "",

    [Parameter(Mandatory=$false)]
    [string]$Monthly = "",

    [Parameter(Mandatory=$false)]
    [switch]$Silent,

    [Parameter(Mandatory=$false)]
    [switch]$NoStartup,

    [Parameter(Mandatory=$false)]
    [switch]$NoLauncher,

    [Parameter(Mandatory=$false)]
    [switch]$Uninstall
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "🚀 via54Medit medit-telemetry PowerShell 一键部署向导" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. 寻找可用 Python 解释器
$pyCmd = ""
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pyCmd = "python"
} elseif (Test-Path "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe") {
    $pyCmd = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe"
} elseif (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe") {
    $pyCmd = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
} elseif (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe") {
    $pyCmd = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
} elseif (Test-Path "C:\Python311\python.exe") {
    $pyCmd = "C:\Python311\python.exe"
} elseif (Test-Path "C:\Python312\python.exe") {
    $pyCmd = "C:\Python312\python.exe"
} else {
    Write-Host "[!] 未检测到有效的 Python 解释器，请先安装 Python 并加入 PATH。" -ForegroundColor Red
    exit 1
}

Write-Host "[✓] 采用 Python 解释器: $pyCmd" -ForegroundColor Green

# 2. 定位 deploy.py 路径
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) {
    $ScriptDir = (Get-Location).Path
}

$deployPy = Join-Path $ScriptDir "deploy.py"
if (-not (Test-Path $deployPy)) {
    $deployPy = Join-Path $ScriptDir "telemetry\deploy.py"
}

if (-not (Test-Path $deployPy)) {
    Write-Host "[*] 正在拉取最新的部署核心 deploy.py..." -ForegroundColor Yellow
    $deployPy = Join-Path $env:TEMP "medit_deploy.py"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/veawho/via54Medit/main/telemetry/deploy.py" -OutFile $deployPy
}

# 3. 构造参数并调用 Python 部署引擎
$pyArgs = @($deployPy)

if ($Instruction) { $pyArgs += $Instruction }
if ($Silent) { $pyArgs += "--silent" }
if ($Nickname) { $pyArgs += "--nickname"; $pyArgs += $Nickname }
if ($OpenId) { $pyArgs += "--openid"; $pyArgs += $OpenId }
if ($AppId) { $pyArgs += "--app-id"; $pyArgs += $AppId }
if ($AppSecret) { $pyArgs += "--app-secret"; $pyArgs += $AppSecret }
if ($Bitable) { $pyArgs += "--bitable"; $pyArgs += $Bitable }
if ($Weekly) { $pyArgs += "--weekly"; $pyArgs += $Weekly }
if ($Monthly) { $pyArgs += "--monthly"; $pyArgs += $Monthly }
if ($NoStartup) { $pyArgs += "--no-startup" }
if ($NoLauncher) { $pyArgs += "--no-launcher" }
if ($Uninstall) { $pyArgs += "--uninstall" }

& $pyCmd $pyArgs
exit $LASTEXITCODE
