<#
.SYNOPSIS
    via54Medit 一键跨平台部署入口 (Windows PowerShell)
.DESCRIPTION
    对标业界成熟方案 (hermes-agent / openclaw):
    - 环境变量防污染 (清空进程级 PYTHONPATH/PYTHONHOME)
    - 智能定位 Python 3.10+ (python.exe / py -3 / 标准安装路径)
    - 统一参数透传至 scripts/bootstrap_device.py (如 -DryRun, --dry-run 等)
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DryRun
#>

[CmdletBinding()]
param (
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ForwardArgs
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 1. 环境变量防污染
$env:PYTHONPATH = ""
$env:PYTHONHOME = ""

# 2. 定位仓库根目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path "$ScriptDir\bootstrap_device.py") {
    $RepoRoot = Split-Path -Parent $ScriptDir
} elseif (Test-Path "$ScriptDir\scripts\bootstrap_device.py") {
    $RepoRoot = $ScriptDir
} else {
    $RepoRoot = (Get-Location).Path
}

$Bootstrap = Join-Path $RepoRoot "scripts\bootstrap_device.py"
if (-not (Test-Path $Bootstrap)) {
    Write-Host "[-] 错误: 未在 $RepoRoot 找到 scripts\bootstrap_device.py" -ForegroundColor Red
    exit 1
}

# 3. 寻找 Python 3.10+ 解释器
$pyCandidates = @(
    "python",
    "py",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "C:\Python312\python.exe",
    "C:\Python311\python.exe",
    "C:\Python310\python.exe"
)

$pyBin = ""
foreach ($cand in $pyCandidates) {
    if ($cand -eq "python" -or $cand -eq "py") {
        if (Get-Command $cand -ErrorAction SilentlyContinue) {
            $checkCmd = if ($cand -eq "py") { "py -3" } else { "python" }
            $verCheck = & ($checkCmd.Split()[0]) ($checkCmd.Split()[1..10]) -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $pyBin = $checkCmd
                break
            }
        }
    } else {
        if (Test-Path $cand) {
            & $cand -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $pyBin = $cand
                break
            }
        }
    }
}

if (-not $pyBin) {
    Write-Host "[-] 错误: 未检测到 Python >= 3.10 解释器，请先安装 Python 3.10+ 并加入 PATH。" -ForegroundColor Red
    exit 1
}

Write-Host "==> 启动 via54Medit 一键就绪初始化 (Windows)..." -ForegroundColor Cyan
Write-Host "    解释器: $pyBin" -ForegroundColor Gray
Write-Host "    仓库目录: $RepoRoot" -ForegroundColor Gray

# 4. 执行 bootstrap_device.py 并透传参数
$pyParts = $pyBin.Split()
$exe = $pyParts[0]
$baseArgs = @()
if ($pyParts.Length -gt 1) {
    $baseArgs += $pyParts[1..($pyParts.Length - 1)]
}
$baseArgs += $Bootstrap
if ($ForwardArgs) {
    $baseArgs += $ForwardArgs
}

& $exe @baseArgs
exit $LASTEXITCODE
