<#
.SYNOPSIS
    uninstall.ps1 -- via54Medit Windows 一键完全卸载与清理脚本 (Native PowerShell Uninstaller)

.DESCRIPTION
    完全移除当前 Windows 系统中部署的 via54Medit 所有组件，包括：
    1. 终止所有运行中的 via54Medit / telemetry 后台守护进程与监控进程
    2. 注销并删除所有计划任务 (medit-usage-collector, medit-monday-finalize, MeditTelemetryWeekly, MeditTelemetryMonthly)
    3. 移除开机自启动脚本 (Startup\traework_telemetry_silent.vbs 等)
    4. 彻底删除已部署的主目录 (~/.via54medit 与 ~/.medit)
    5. 清理豆包工作伙伴在 lark-chats 解压的工作空间与用户技能
    6. 清理下载的安装包归档与临时缓存
    7. 支持通过 -CleanRepo 清除本地代码仓库

.PARAMETER CheckOnly
    只检查，不实际删除

.PARAMETER CleanRepo
    同时彻底删除当前或指定的本地代码仓库

.PARAMETER RepoPath
    指定本地代码仓库路径（默认自动检测当前脚本所在仓库）
#>

[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$CleanRepo,
    [string]$RepoPath = ""
)

$ErrorActionPreference = "Continue"

$HOME_DIR     = $env:USERPROFILE
$BIN_DIR      = "$HOME_DIR\.via54medit"
$CFG_DIR      = "$HOME_DIR\.medit"
$STARTUP_DIR  = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$DOUBAO_WS    = "$HOME_DIR\.doubao\lark-chats\2026-10-12\new-chat\via54Medit"
$SKILLS_DIR   = "$env:APPDATA\LarkShell\aha\users\d3cbefc07078f021dab889c87626bd02\doubao\.doubao\agent_mode\workspace\.user_skills"
$PID_FILE     = "$CFG_DIR\daemon.pid"

$Report = [System.Collections.ArrayList]::new()

function Log-Item($name, $status, $detail) {
    $null = $Report.Add([PSCustomObject]@{ Item = $name; Status = $status; Detail = $detail })
    $mark = switch ($status) {
        "OK"      { "[OK]     " }
        "REMOVED" { "[REMOVED]" }
        "KILLED"  { "[KILLED] " }
        "WARN"    { "[WARN]   " }
        "FAIL"    { "[FAIL]   " }
        default   { "[INFO]   " }
    }
    Write-Host ("{0} {1,-38} {2}" -f $mark, $name, $detail)
}

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host " via54Medit Windows 一键完全卸载与清理引擎 (PowerShell Uninstaller)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. 终止运行中进程
Write-Host "`n[1/6] 检查并终止后台运行中的 via54Medit / Telemetry 进程..." -ForegroundColor Yellow
$procKilled = 0

# 读取 daemon.pid
if (Test-Path $PID_FILE) {
    try {
        $p = [int]((Get-Content $PID_FILE -Raw).Trim())
        if ($p -gt 0) {
            $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
            if ($proc) {
                if ($CheckOnly) {
                    Log-Item "守护进程 (daemon.pid)" "WARN" "进程正在运行 PID: $p"
                } else {
                    Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
                    Log-Item "守护进程 (daemon.pid)" "KILLED" "已终止 PID: $p"
                    $procKilled++
                }
            }
        }
    } catch {}
}

# 检索 CommandLine 中包含 telemetry.cli / usage_collector / monday_finalize / via54medit 的进程（过滤 Intel 驱动守护）
$targets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "telemetry\.cli|usage_collector|monday_finalize|\.via54medit" -and
    $_.ExecutablePath -notmatch "Intel\\TelemetryAgent"
}
foreach ($t in $targets) {
    if ($t.ProcessId -ne $PID) {
        if ($CheckOnly) {
            Log-Item "活跃进程 ($($t.ProcessName))" "WARN" "PID: $($t.ProcessId) - $($t.CommandLine.Substring(0, [Math]::Min(50, $t.CommandLine.Length)))"
        } else {
            Stop-Process -Id $t.ProcessId -Force -ErrorAction SilentlyContinue
            Log-Item "活跃进程 ($($t.ProcessName))" "KILLED" "已终止 PID: $($t.ProcessId)"
            $procKilled++
        }
    }
}
if ($procKilled -eq 0 -and -not $CheckOnly) {
    Log-Item "后台进程检查" "OK" "无活跃的 via54Medit 进程"
}

# 2. 注销计划任务
Write-Host "`n[2/6] 清除系统计划任务..." -ForegroundColor Yellow
$tasks = @(
    "medit-usage-collector",
    "medit-monday-finalize",
    "MeditTelemetryWeekly",
    "MeditTelemetryMonthly"
)
foreach ($t in $tasks) {
    $task = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    if ($task) {
        if ($CheckOnly) {
            Log-Item "计划任务: $t" "WARN" "已注册待删除"
        } else {
            Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
            $check = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
            if (-not $check) {
                Log-Item "计划任务: $t" "REMOVED" "已注销并移除"
            } else {
                Log-Item "计划任务: $t" "FAIL" "注销失败"
            }
        }
    } else {
        Log-Item "计划任务: $t" "OK" "未注册或已清理"
    }
}

# 3. 移除开机自启脚本
Write-Host "`n[3/6] 检查并移除开机启动脚本与伴随启动器..." -ForegroundColor Yellow
$vbsTargets = @(
    "$STARTUP_DIR\traework_telemetry_silent.vbs",
    "$STARTUP_DIR\启动 TraeWork (带自动监控).vbs",
    "$HOME_DIR\Desktop\启动 TraeWork (带自动监控).vbs"
)
foreach ($v in $vbsTargets) {
    if (Test-Path $v) {
        if ($CheckOnly) {
            Log-Item "自启项: $(Split-Path $v -Leaf)" "WARN" $v
        } else {
            try {
                Remove-Item $v -Force -ErrorAction Stop
                Log-Item "自启项: $(Split-Path $v -Leaf)" "REMOVED" "已删除: $v"
            } catch {
                Log-Item "自启项: $(Split-Path $v -Leaf)" "FAIL" $_.Exception.Message
            }
        }
    } else {
        Log-Item "自启项: $(Split-Path $v -Leaf)" "OK" "不存在"
    }
}

# 4. 删除已部署主目录与数据
Write-Host "`n[4/6] 清除已部署主目录 (~/.via54medit / ~/.medit)..." -ForegroundColor Yellow
$dirsToRemove = @($BIN_DIR, $CFG_DIR)
foreach ($d in $dirsToRemove) {
    if (Test-Path $d) {
        if ($CheckOnly) {
            Log-Item "部署目录: $(Split-Path $d -Leaf)" "WARN" $d
        } else {
            try {
                Remove-Item -Path $d -Recurse -Force -ErrorAction Stop
                Log-Item "部署目录: $(Split-Path $d -Leaf)" "REMOVED" "已彻底清除: $d"
            } catch {
                Get-ChildItem -Path $d -Recurse -Force | ForEach-Object { $_.Attributes = 'Normal' }
                Remove-Item -Path $d -Recurse -Force -ErrorAction SilentlyContinue
                if (-not (Test-Path $d)) {
                    Log-Item "部署目录: $(Split-Path $d -Leaf)" "REMOVED" "重试后已删除: $d"
                } else {
                    Log-Item "部署目录: $(Split-Path $d -Leaf)" "FAIL" $_.Exception.Message
                }
            }
        }
    } else {
        Log-Item "部署目录: $(Split-Path $d -Leaf)" "OK" "不存在或已清除"
    }
}

# 5. 清理豆包工作伙伴解压缓存、技能与安装临时文件
Write-Host "`n[5/6] 清理工作伙伴解压缓存、用户技能与安装归档..." -ForegroundColor Yellow

# 豆包解压空间
if (Test-Path $DOUBAO_WS) {
    if ($CheckOnly) {
        Log-Item "豆包工作空间" "WARN" $DOUBAO_WS
    } else {
        try {
            Remove-Item -Path $DOUBAO_WS -Recurse -Force -ErrorAction Stop
            Log-Item "豆包工作空间" "REMOVED" "已彻底删除: $DOUBAO_WS"
        } catch {
            Log-Item "豆包工作空间" "FAIL" $_.Exception.Message
        }
    }
} else {
    Log-Item "豆包工作空间" "OK" "无残留"
}

# 豆包用户技能
if (Test-Path $SKILLS_DIR) {
    Get-ChildItem $SKILLS_DIR -Directory | Where-Object { $_.Name -like "via54medit*" } | ForEach-Object {
        if ($CheckOnly) {
            Log-Item "豆包技能: $($_.Name)" "WARN" $_.FullName
        } else {
            try {
                Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction Stop
                Log-Item "豆包技能: $($_.Name)" "REMOVED" "已清除技能: $($_.Name)"
            } catch {
                Log-Item "豆包技能: $($_.Name)" "FAIL" $_.Exception.Message
            }
        }
    }
}

# 临时文件与安装包
$tempArchives = @(
    "$HOME_DIR\Downloads\via54medit-workmate-installer-v5.4.51.zip",
    "$env:LOCALAPPDATA\Temp\rel50",
    "$env:LOCALAPPDATA\Temp\rel51"
)
foreach ($ta in $tempArchives) {
    if (Test-Path $ta) {
        if ($CheckOnly) {
            Log-Item "安装缓存: $(Split-Path $ta -Leaf)" "WARN" $ta
        } else {
            try {
                Remove-Item -Path $ta -Recurse -Force -ErrorAction Stop
                Log-Item "安装缓存: $(Split-Path $ta -Leaf)" "REMOVED" $ta
            } catch {
                Log-Item "安装缓存: $(Split-Path $ta -Leaf)" "FAIL" $_.Exception.Message
            }
        }
    }
}

# 6. 本地代码仓库清理
Write-Host "`n[6/6] 本地代码仓库清理..." -ForegroundColor Yellow
if ($CleanRepo) {
    $target = $RepoPath
    if (-not $target) {
        if (Test-Path (Join-Path $PSScriptRoot ".git")) {
            $target = $PSScriptRoot
        }
    }
    if ($target -and (Test-Path $target)) {
        if ($CheckOnly) {
            Log-Item "本地代码仓库" "WARN" "待删除目录: $target"
        } else {
            try {
                Get-ChildItem -Path $target -Recurse -Force | ForEach-Object { $_.Attributes = 'Normal' }
                Remove-Item -Path $target -Recurse -Force -ErrorAction Stop
                Log-Item "本地代码仓库" "REMOVED" "已彻底删除代码仓库: $target"
            } catch {
                Log-Item "本地代码仓库" "FAIL" $_.Exception.Message
            }
        }
    } else {
        Log-Item "本地代码仓库" "WARN" "未定位到有效仓库目录"
    }
} else {
    Log-Item "本地代码仓库" "SKIP" "未指定 -CleanRepo，保留本地代码"
}

Write-Host "`n========================= 卸载与清理总结 =========================" -ForegroundColor Cyan
$rem = ($Report | Where-Object { $_.Status -in @("REMOVED", "KILLED") }).Count
$ok  = ($Report | Where-Object { $_.Status -eq "OK" }).Count
$wrn = ($Report | Where-Object { $_.Status -eq "WARN" }).Count
$fl  = ($Report | Where-Object { $_.Status -eq "FAIL" }).Count
Write-Host (" 已清理/终止: {0}   已就绪/无残留: {1}   待处理: {2}   失败: {3}`n" -f $rem, $ok, $wrn, $fl)

if ($fl -gt 0) { exit 1 } else { exit 0 }
