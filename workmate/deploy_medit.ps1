# =====================================================================
# deploy_medit.ps1 — via54Medit 豆包伙伴 一键依赖部署/自愈脚本
# 用途：伙伴部署后自动探测并补全全部依赖（FFmpeg / PaddleOCR / Office COM /
#       Go 工具链与模块依赖 / Python 依赖 / 技能同步 / 配置初始化 / CDP）
# 特性：幂等（已满足跳过）、模块化、可重跑、输出状态报告
# 用法：
#   powershell -ExecutionPolicy Bypass -File deploy_medit.ps1 -CheckOnly     # 只体检
#   powershell -ExecutionPolicy Bypass -File deploy_medit.ps1                # 全量修复
#   powershell -ExecutionPolicy Bypass -File deploy_medit.ps1 -SkipPaddle    # 跳过 PaddleOCR
#   powershell -ExecutionPolicy Bypass -File deploy_medit.ps1                # 全量部署（缺 DeepSeek key 时交互提示）
# =====================================================================
param(
  [switch]$CheckOnly,        # 只检查，不安装
  [switch]$SkipPaddle,       # 跳过 PaddleOCR（大，~1GB）
  [switch]$SkipGoBuild,      # 跳过 Go 重编译
  [switch]$SkipSkillsSync,   # 跳过技能同步
  [switch]$StartCDP          # （已弃用，antfu 源已剥离）保留兼容
)

$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

# ---------- 路径常量 ----------
$HOME_DIR       = $env:USERPROFILE
$BIN_DIR        = "$HOME_DIR\.via54medit\bin"
$CFG_DIR        = "$HOME_DIR\.medit"
$CFG_FILE       = "$CFG_DIR\config.yaml"
$GO_TOOLCHAIN   = "$HOME_DIR\go-toolchain\go\bin\go.exe"
$REPO_DIR       = "$HOME_DIR\.doubao\lark-chats\2026-10-12\new-chat\via54Medit"
$SKILL_DEST     = "$HOME_DIR\AppData\Roaming\LarkShell\aha\users\d3cbefc07078f021dab889c87626bd02\doubao\.doubao\agent_mode\workspace\.user_skills"
$LOG            = "$BIN_DIR\deploy_medit.log"
$ts             = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$report         = [System.Collections.ArrayList]::new()

function Log($msg) { $line = "[$ts] $msg"; Add-Content -Path $LOG -Value $line -Encoding utf8 -ErrorAction SilentlyContinue }
function Add-Report($name, $status, $detail) {
  $null = $report.Add([PSCustomObject]@{ Item = $name; Status = $status; Detail = $detail })
  $mark = switch ($status) { "OK" { "✅" } "FIXED" { "🔧" } "SKIP" { "➖" } "FAIL" { "❌" } "WARN" { "⚠️" } default { "·" } }
  Write-Host ("{0} {1,-34} {2}" -f $mark, $name, $detail)
  Log "$mark $name : $detail"
}

# ---------- 工具探测 ----------
function Get-Tool($name) { return (Get-Command $name -ErrorAction SilentlyContinue) }

function Test-PyPkg($mod, $import) {
  $code = "import $import; print('ok')"
  $r = & python -c $code 2>$null
  return ($LASTEXITCODE -eq 0)
}

function Test-COM($progId) {
  try { $o = New-Object -ComObject $progId -ErrorAction Stop; if ($o) { [void]$o.Quit(); return $true } } catch {}
  return $false
}

Write-Host "`n=== via54Medit 伙伴依赖部署脚本  $ts ===" -ForegroundColor Cyan
if (-not (Test-Path $BIN_DIR)) { New-Item -ItemType Directory -Force -Path $BIN_DIR | Out-Null }

# ================= 1. medit 二进制 =================
# 部署源优先级：① 伙伴安装包自带 bin\medit.exe（上传部署场景）→ ② 仓库预编译 → ③ Go 编译
$medit = "$BIN_DIR\medit.exe"
if (Test-Path $medit) {
  $v = & $medit version 2>$null | Select-Object -First 1
  Add-Report "medit 二进制" "OK" "$v"
} else {
  if ($CheckOnly) { Add-Report "medit 二进制" "FAIL" "缺失: $medit（全量部署时自动从安装包 bin/ 补齐）" }
  else {
    $bundleMedit = Join-Path $PSScriptRoot "bin\medit.exe"
    if (Test-Path $bundleMedit) {
      Copy-Item $bundleMedit $medit -Force
      $bundleMcp = Join-Path $PSScriptRoot "bin\medit-mcp.exe"
      if (Test-Path $bundleMcp) { Copy-Item $bundleMcp "$BIN_DIR\medit-mcp.exe" -Force }
      Add-Report "medit 二进制" "FIXED" "从伙伴安装包 bin/ 复制部署"
    } elseif (Test-Path "$REPO_DIR\bin\medit.exe") {
      Copy-Item "$REPO_DIR\bin\medit.exe" $medit -Force
      Copy-Item "$REPO_DIR\bin\medit-mcp.exe" "$BIN_DIR\medit-mcp.exe" -Force -ErrorAction SilentlyContinue
      Add-Report "medit 二进制" "FIXED" "从仓库复制并部署"
    } else { Add-Report "medit 二进制" "FAIL" "安装包与仓库均无 medit.exe，需 Go 编译" }
  }
}

# ================= 2. Python 运行时 =================
$py = Get-Tool python
if ($py) {
  $pyv = & python --version 2>&1 | Select-Object -First 1
  Add-Report "Python" "OK" "$pyv"
} else { Add-Report "Python" "FAIL" "python 不在 PATH（需安装 Python 3.11+）" }

# ================= 3. Python 依赖 =================
$pyDeps = @(
  @{ Mod = "PyMuPDF";  Import = "fitz";  Pkg = "pymupdf" },
  @{ Mod = "python-pptx"; Import = "pptx"; Pkg = "python-pptx" },
  @{ Mod = "Pillow";   Import = "PIL";   Pkg = "Pillow" },
  @{ Mod = "pywin32";  Import = "win32com"; Pkg = "pywin32" }
)
$pyMissing = @()
foreach ($d in $pyDeps) {
  if (Test-PyPkg $d.Mod $d.Import) { Add-Report "py: $($d.Mod)" "OK" "已安装" }
  else { Add-Report "py: $($d.Mod)" "WARN" "缺失"; $pyMissing += $d.Pkg }
}
if ($pyMissing.Count -gt 0) {
  if ($CheckOnly) { Add-Report "Python 依赖安装" "WARN" "缺失: $($pyMissing -join ', ')" }
  else {
    & python -m pip install --quiet $pyMissing 2>&1 | Out-Null
    if (Test-PyPkg $pyDeps[0].Mod $pyDeps[0].Import) { Add-Report "Python 依赖安装" "FIXED" "已安装 $($pyMissing -join ', ')" }
    else { Add-Report "Python 依赖安装" "FAIL" "pip 安装失败，见 $LOG" }
  }
}

# ================= 4. PaddleOCR（大） =================
if (Test-PyPkg "paddleocr" "paddleocr") {
  Add-Report "PaddleOCR" "OK" "已安装（首次使用自动下载模型）"
} elseif ($SkipPaddle) {
  Add-Report "PaddleOCR" "SKIP" "已跳过（-SkipPaddle）"
} elseif ($CheckOnly) {
  Add-Report "PaddleOCR" "WARN" "缺失（~1GB，首次安装较慢）"
} else {
  Write-Host "  → 安装 paddlepaddle + paddleocr（体积较大，请耐心等待）..." -ForegroundColor Yellow
  & python -m pip install --quiet paddlepaddle paddleocr 2>&1 | Out-Null
  Start-Sleep -Seconds 2
  if (Test-PyPkg "paddleocr" "paddleocr") { Add-Report "PaddleOCR" "FIXED" "安装完成（模型首次调用时下载）" }
  else { Add-Report "PaddleOCR" "FAIL" "安装失败（可加 -SkipPaddle 跳过，不影响主链路）" }
}

# ================= 5. FFmpeg =================
$ff = Get-Tool ffmpeg
if ($ff) {
  $ffv = & ffmpeg -version 2>&1 | Select-Object -First 1
  Add-Report "FFmpeg" "OK" "$($ffv.Substring(0, [Math]::Min(40, $ffv.Length)))"
} else {
  if ($CheckOnly) { Add-Report "FFmpeg" "WARN" "缺失" }
  else {
    Write-Host "  → winget 安装 FFmpeg ..." -ForegroundColor Yellow
    & winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements --disable-interactivity 2>&1 | Out-Null
    Start-Sleep -Seconds 3
    if (Get-Tool ffmpeg) { Add-Report "FFmpeg" "FIXED" "winget 安装完成" }
    else { Add-Report "FFmpeg" "FAIL" "winget 安装失败（重启终端后 PATH 生效）" }
  }
}

# ================= 6. poppler（PDF 渲染备用） =================
$pp = Get-Tool pdftoppm
if ($pp) { Add-Report "poppler" "OK" "pdftoppm 可用" }
elseif ($CheckOnly) { Add-Report "poppler" "WARN" "缺失（可选：PDF→图片渲染备用）" }
else {
  Write-Host "  → winget 安装 Poppler ..." -ForegroundColor Yellow
  & winget install --id oschwartz10612.Poppler -e --accept-package-agreements --accept-source-agreements --disable-interactivity 2>&1 | Out-Null
  Start-Sleep -Seconds 3
  if (Get-Tool pdftoppm) { Add-Report "poppler" "FIXED" "winget 安装完成" }
  else { Add-Report "poppler" "WARN" "winget 安装未生效（重启终端后 PATH 生效；可选项）" }
}

# ================= 7. Go 工具链与模块依赖 =================
if (Test-Path $GO_TOOLCHAIN) {
  $gv = & $GO_TOOLCHAIN version 2>&1 | Select-Object -First 1
  Add-Report "Go 工具链" "OK" "$gv"
  if (-not $CheckOnly -and -not $SkipGoBuild -and (Test-Path "$REPO_DIR\cmd\medit")) {
    Write-Host "  → 增量重编译 medit/medit-mcp（含依赖校验）..." -ForegroundColor Yellow
    $env:PATH = "$HOME_DIR\go-toolchain\go\bin;" + $env:PATH
    $env:GOPATH = "$HOME_DIR\go"; $env:GOCACHE = "$HOME_DIR\go\cache"; $env:CGO_ENABLED = "0"
    Push-Location $REPO_DIR
    & go build -ldflags "-s -w" -o bin\medit.exe .\cmd\medit 2>&1 | Out-Null
    $b1 = $LASTEXITCODE
    & go build -ldflags "-s -w" -o bin\medit-mcp.exe .\cmd\medit-mcp 2>&1 | Out-Null
    $b2 = $LASTEXITCODE
    Pop-Location
    if ($b1 -eq 0 -and $b2 -eq 0) {
      Copy-Item "$REPO_DIR\bin\medit.exe" $BIN_DIR -Force
      Copy-Item "$REPO_DIR\bin\medit-mcp.exe" $BIN_DIR -Force
      Add-Report "Go 编译部署" "FIXED" "重编译完成并部署（medit + medit-mcp）"
    } else { Add-Report "Go 编译部署" "FAIL" "编译失败（b1=$b1 b2=$b2，见日志）" }
  }
  $modCache = Test-Path "$HOME_DIR\go\pkg\mod"
  if (-not $modCache -and -not $CheckOnly) {
    Push-Location $REPO_DIR; & go mod download 2>&1 | Out-Null; Pop-Location
  }
  Add-Report "Go 模块依赖" $(if (Test-Path "$HOME_DIR\go\pkg\mod") { "OK" } else { "WARN" }) "mod 缓存 $HOME_DIR\go\pkg\mod"
} else {
  if ($CheckOnly) { Add-Report "Go 工具链" "WARN" "缺失（编译/升级 medit 时需要；日常运行不需要）" }
  else {
    Write-Host "  → 下载 Go 工具链（约 75MB）..." -ForegroundColor Yellow
    $ver = (curl.exe -s "https://go.dev/VERSION?m=text" | Select-Object -First 1).Trim()
    curl.exe -L -o "$HOME_DIR\go-toolchain\go.zip" "https://go.dev/dl/$ver.windows-amd64.zip" 2>&1 | Out-Null
    Expand-Archive -Path "$HOME_DIR\go-toolchain\go.zip" -DestinationPath "$HOME_DIR\go-toolchain" -Force
    if (Test-Path $GO_TOOLCHAIN) { Add-Report "Go 工具链" "FIXED" "安装完成 $ver" }
    else { Add-Report "Go 工具链" "FAIL" "下载/解压失败" }
  }
}

# ================= 8. Go 加入用户 PATH（doctor 识别） =================
if (Test-Path $GO_TOOLCHAIN) {
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $goBinDir = Split-Path $GO_TOOLCHAIN -Parent
  if ($userPath -notlike "*$goBinDir*") {
    if (-not $CheckOnly) {
      [Environment]::SetEnvironmentVariable("Path", "$userPath;$goBinDir", "User")
      Add-Report "Go PATH" "FIXED" "已加入用户 PATH: $goBinDir（新终端生效）"
    } else { Add-Report "Go PATH" "WARN" "未加入用户 PATH" }
  } else { Add-Report "Go PATH" "OK" "已在用户 PATH" }
}

# ================= 9. Office COM 接口 =================
$ppt = Test-COM "PowerPoint.Application"
$word = Test-COM "Word.Application"
if ($ppt -and $word) { Add-Report "Office COM (PPT+Word)" "OK" "COM 可实例化" }
else {
  $detail = "PPT:$ppt Word:$word"
  if ($CheckOnly) { Add-Report "Office COM (PPT+Word)" "WARN" $detail }
  else {
    Add-Report "Office COM (PPT+Word)" "FAIL" "$detail — 需本机安装 Microsoft Office（PPT+Word 版式渲染依赖）"
  }
}

# ================= 8. 蚂蚁阿福（antfu）源已剥离（2026-10-12）：不再需要 Chrome CDP =================
# ================= 9. 配置初始化 =================
if (Test-Path $CFG_FILE) { Add-Report "medit 配置" "OK" "$CFG_FILE" }
else {
  if ($CheckOnly) { Add-Report "medit 配置" "WARN" "缺失: ~/.medit/config.yaml" }
  else {
    New-Item -ItemType Directory -Force -Path $CFG_DIR | Out-Null
    @"
# via54Medit 本机配置（deploy_medit.ps1 自动生成）
version: 1
sources:
  pubmed: { enabled: true, api_key: "", rate_limit: 3, email: "" }
  openalex: { enabled: true, email: "", rate_limit: 10 }
  s2: { enabled: true, api_key: "", rate_limit: 1 }
llm:
  default: deepseek
  providers:
    openai: { api_key: "", model: "deepseek-flash", base_url: "https://api.deepseek.com/v1" }
router:
  concurrency: 4
  timeout_per_source: 30s
  max_retries: 3
  fallback_order: [pubmed, openalex, s2]
  fusion: { weights: { cited_by: 0.3, recency: 0.2, fwci: 0.3, multi_source: 0.2 }, simhash_hamming_threshold: 3 }
  classify: { use_llm: true, enable_pico: true }
storage: { qa_dir: "~/.medit/qa", index_db: "~/.medit/fts5.db", pdf_dir: "~/.medit/pdfs", knowledge_base: "medlit", audit_log: "~/.medit/audit" }
output: { default_format: "json", pretty: true, color: "auto", language: "auto" }
"@ | Set-Content -Path $CFG_FILE -Encoding utf8
    Add-Report "medit 配置" "FIXED" "已生成默认配置"
  }
}

# ================= 10. 豆包技能同步 =================
$skills = @("via54medit", "via54-highlight-strict", "via54-tma-literature-workflow", "via54medit-algorithm-driven-upgrade-v2", "via54medit-anno2ppt-phase7", "via54medit-anno2ppt-pitfalls-2026-08", "via54medit-architecture-honest-status", "via54medit-literature-dir-init", "via54medit-literature-pipeline", "via54medit-ppt-citation-analysis")
$missingSkills = @()
foreach ($s in $skills) { if (-not (Test-Path "$SKILL_DEST\$s\SKILL.md")) { $missingSkills += $s } }
if ($missingSkills.Count -eq 0) { Add-Report "豆包技能同步" "OK" "10 个技能全部就位" }
else {
  if ($CheckOnly) { Add-Report "豆包技能同步" "WARN" "缺失: $($missingSkills -join ', ')" }
  else {
    if (Test-Path "$REPO_DIR\skills") {
      Get-ChildItem "$REPO_DIR\skills" -Directory | ForEach-Object { Copy-Item $_.FullName "$SKILL_DEST\$($_.Name)" -Recurse -Force }
    }
    if (Test-Path "$REPO_DIR\.agents\skills\via54medit") { Copy-Item "$REPO_DIR\.agents\skills\via54medit" "$SKILL_DEST\via54medit" -Recurse -Force }
    Add-Report "豆包技能同步" "FIXED" "已从仓库同步到 $SKILL_DEST"
  }
}

# ================= 12.5 telemetry 遥测 + 自动定时回报 =================
$telCfg = "$HOME_DIR\.medit\telemetry_config.json"
$telRep = "$BIN_DIR\telemetry_report.ps1"
$dsCli  = "$BIN_DIR\deepseek.ps1"
if (Test-Path "$REPO_DIR\telemetry\deploy.py") {
  if (Test-Path $telCfg) {
    Add-Report "telemetry 配置" "OK" "已部署（$telCfg）"
    $dstat = & python -m telemetry.cli daemon --status 2>&1 | Select-String "正在运行" | Select-Object -First 1
    if ($dstat) { Add-Report "telemetry 守护进程" "OK" "运行中" }
    else { Add-Report "telemetry 守护进程" "WARN" "未运行（python -m telemetry.cli daemon --start 启动）" }
  } elseif (-not $CheckOnly) {
    Write-Host "  → 部署 telemetry 遥测（守护进程+开机自启）..." -ForegroundColor Yellow
    Push-Location $REPO_DIR
    & python telemetry/deploy.py --silent --nickname "魏宇浩" --openid "ou_3e947622a1da2cdbe913bac1f3df56d2" --no-launcher 2>&1 | Out-Null
    Pop-Location
    if (Test-Path $telCfg) { Add-Report "telemetry 部署" "FIXED" "守护进程+配置已部署" }
    else { Add-Report "telemetry 部署" "FAIL" "deploy.py 未完成，见仓库 telemetry 日志" }
  } else { Add-Report "telemetry 部署" "WARN" "未部署（全量修复时自动装）" }

  if (Test-Path $telRep) { Add-Report "遥测回报脚本" "OK" "telemetry_report.ps1 就位" }
  else { Add-Report "遥测回报脚本" "WARN" "缺失（全量修复时自动补齐）" }
  # --- DeepSeek CLI 强制部署（默认模型=DeepSeek，缺失即 FAIL） ---
  if (-not (Test-Path $dsCli)) {
    $dsSrc = Join-Path $PSScriptRoot "bin\deepseek.ps1"
    if (Test-Path $dsSrc) { Copy-Item $dsSrc $dsCli -Force }
  }
  if (Test-Path $dsCli) {
    Add-Report "DeepSeek CLI" "OK" "deepseek.ps1 就位（强制部署）"
    $dk = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY")
    $keyFile = "$HOME_DIR\.deepseek.key"
    $keyFileHas = (Test-Path $keyFile) -and ((Get-Content $keyFile -Raw -ErrorAction SilentlyContinue).Trim().Length -gt 0)
    $cfgKey = ""
    if (Test-Path $CFG_FILE) {
      $m = Select-String -Path $CFG_FILE -Pattern 'api_key:\s*"([^"]+)"' | Select-Object -First 1
      if ($m -and $m.Matches[0].Groups[1].Value) { $cfgKey = $m.Matches[0].Groups[1].Value }
    }
    if (-not $dk -and -not $keyFileHas -and $cfgKey) {
      # 从 config 回填（openai provider 存了 key 的情况）
      [Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", $cfgKey, "User")
      Set-Content $keyFile $cfgKey -NoNewline -Encoding UTF8
      $dk = $cfgKey
      Add-Report "DeepSeek key" "FIXED" "已从 config 回填 ~/.deepseek.key + 用户环境变量"
    }
    if ($dk -and -not $keyFileHas) {
      Set-Content $keyFile $dk -NoNewline -Encoding UTF8
      Add-Report "DeepSeek key" "FIXED" "已从环境变量落盘 ~/.deepseek.key"
    } elseif ($dk -or $keyFileHas) {
      if (-not $dk) { $dk = (Get-Content $keyFile -Raw).Trim() }
      if ($cfgKey -ne $dk) {
        # 回填 config（保证 --llm deepseek 与 openai 兼容通道均可读 key）
        if (Test-Path $CFG_FILE) {
          $c = Get-Content $CFG_FILE -Raw
          $c = $c -replace 'api_key:\s*""', ('api_key: "' + $dk + '"')
          Set-Content $CFG_FILE $c -Encoding utf8
          Add-Report "DeepSeek key" "FIXED" "已回填 config providers.openai.api_key"
        }
      }
      Add-Report "DeepSeek key" "OK" "已配置（env / ~/.deepseek.key / config）"
    } elseif ($CheckOnly) {
      Add-Report "DeepSeek key" "FAIL" "强制要求：需提供 DeepSeek API Key（全量部署时会提示输入）"
    } else {
      Write-Host "" -ForegroundColor Yellow
      Write-Host "⚠ 强制要求：DeepSeek API Key 缺失。" -ForegroundColor Yellow
      Write-Host "  PPT 分析 / 文献分析 / highlight / 视觉 默认均走 DeepSeek（--llm deepseek，模型 deepseek-flash）。" -ForegroundColor Yellow
      $prompt = Read-Host "  请输入 DeepSeek API Key（sk-...，留空则跳过本次写入）"
      if ($prompt -and $prompt.Trim().Length -gt 0) {
        $dk = $prompt.Trim()
        Set-Content $keyFile $dk -NoNewline -Encoding UTF8
        [Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", $dk, "User")
        if (Test-Path $CFG_FILE) {
          $c = Get-Content $CFG_FILE -Raw
          $c = $c -replace 'api_key:\s*""', ('api_key: "' + $dk + '"')
          Set-Content $CFG_FILE $c -Encoding utf8
        }
        Add-Report "DeepSeek key" "FIXED" "已写入 ~/.deepseek.key + 用户环境变量 + config（本终端请重开生效）"
      } else { Add-Report "DeepSeek key" "FAIL" "未提供 key。可稍后重跑 deploy_medit.ps1 或在设置里配置 DEEPSEEK_API_KEY" }
    }
  } else { Add-Report "DeepSeek CLI" "FAIL" "强制要求：deepseek.ps1 缺失（开发包 bin 也缺，请重新获取开发包）" }

  # --- mmx-cli (MiniMax) 自动部署：npm 全局包自愈 ---
  $mmxMod = "$HOME_DIR\.tools\nodejs\node_modules\mmx-cli\dist\mmx.mjs"
  $mmxInPath = (Get-Command mmx-cli -ErrorAction SilentlyContinue) -ne $null
  if ($mmxInPath -or (Test-Path $mmxMod)) {
    Add-Report "mmx-cli (MiniMax)" "OK" "已部署（npm 全局包）"
  } elseif (-not $CheckOnly) {
    Write-Host "  → 安装 mmx-cli (npm install -g mmx-cli)..." -ForegroundColor Yellow
    & npm install -g mmx-cli 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Add-Report "mmx-cli (MiniMax)" "FIXED" "npm 安装完成" }
    else { Add-Report "mmx-cli (MiniMax)" "FAIL" "npm 安装失败（检查 node/npm 与网络）" }
  } else { Add-Report "mmx-cli (MiniMax)" "WARN" "未部署（全量修复时自动装）" }
  $mk = [Environment]::GetEnvironmentVariable("MINIMAX_API_KEY")
  if ($mk) { Add-Report "MiniMax key" "OK" "MINIMAX_API_KEY 已配置" }
  else { Add-Report "MiniMax key" "WARN" "未设置 MINIMAX_API_KEY" }

  if (Test-Path "$BIN_DIR\medit-telemetry.ps1") { Add-Report "medit-telemetry 命令" "OK" "包装脚本就位" }
  else { Add-Report "medit-telemetry 命令" "WARN" "缺失" }

  # 定时任务：周一 10:30 周报 / 每月 1 日 10:30 月报
  $wk = & schtasks /Query /TN "MeditTelemetryWeekly" 2>&1
  $mo = & schtasks /Query /TN "MeditTelemetryMonthly" 2>&1
  $wkOK = ($LASTEXITCODE -eq 0 -and $wk -match "MeditTelemetryWeekly")
  & schtasks /Query /TN "MeditTelemetryMonthly" 2>&1 | Out-Null
  $moOK = ($LASTEXITCODE -eq 0)
  if ($wkOK -and $moOK) { Add-Report "定时回报任务" "OK" "周报(周一10:30)+月报(1日10:30)" }
  elseif (-not $CheckOnly) {
    $tr = 'powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $telRep + '" -Period '
    & schtasks /Create /F /TN "MeditTelemetryWeekly" /TR ($tr + 'week') /SC WEEKLY /D MON /ST 10:30 2>&1 | Out-Null
    & schtasks /Create /F /TN "MeditTelemetryMonthly" /TR ($tr + 'month') /SC MONTHLY /D 1 /ST 10:30 2>&1 | Out-Null
    Add-Report "定时回报任务" "FIXED" "已注册周报+月报"
  } else { Add-Report "定时回报任务" "WARN" "未注册" }
} else { Add-Report "telemetry 遥测" "SKIP" "仓库 telemetry/ 缺失" }

# ================= 12.6 lark-cli + 飞书账号 + 多维表格自动绑定 =================
$larkCmd = Get-Command lark-cli -ErrorAction SilentlyContinue
if ($larkCmd) {
  $me = lark-cli contact +get-user --jq ".data.user.open_id" 2>&1 | Select-Object -First 1
  if ($me -match "ou_") { Add-Report "lark-cli 部署" "OK" "已就绪，本地飞书账号已绑定（openid $($me.Trim())）" }
  else { Add-Report "lark-cli 部署" "WARN" "命令存在但登录态异常（请重新登录 lark-cli）" }
} else { Add-Report "lark-cli 部署" "WARN" "未安装 lark-cli（豆包工作环境自带；缺失时按官方方式安装）" }
$bitUrl = "https://hackhealth.feishu.cn/base/Al8xbS4u9av85esUgjvcWYDankb"
$tbl = lark-cli base +table-list --base-token "Al8xbS4u9av85esUgjvcWYDankb" 2>&1 | Select-String "监控数据周报明细" | Select-Object -First 1
if ($tbl) { Add-Report "多维表格绑定" "OK" "已绑定 $bitUrl（表：监控数据周报明细）" }
else { Add-Report "多维表格绑定" "WARN" "表格不可访问（检查租户权限）" }
if (Test-Path "$BIN_DIR\bitable_sync.ps1") { Add-Report "表格同步脚本" "OK" "bitable_sync.ps1 就位" }
else { Add-Report "表格同步脚本" "WARN" "缺失（全量修复时自动补齐）" }

# ================= 13. medit doctor 复检 =================
if (Test-Path "$REPO_DIR\scripts\deploy_scan.py") {
  Write-Host "  → medit doctor 复检（从仓库目录）..." -ForegroundColor Yellow
  Push-Location $REPO_DIR
  $docOut = & "$BIN_DIR\medit.exe" doctor --skip-heavy 2>&1
  Pop-Location
  $okLine = ($docOut | Select-String "必需缺口")
  if ($okLine -match "必需缺口 0") { Add-Report "medit doctor 复检" "OK" $okLine.ToString().Trim() }
  else { Add-Report "medit doctor 复检" "WARN" $okLine.ToString().Trim() }
} else { Add-Report "medit doctor 复检" "SKIP" "仓库不存在（$REPO_DIR），跳过深度复检" }

# ================= 汇总 =================
# ------------------------------------------------------------------
# 12.7 实时用量采集体系（v2.3：medit + deepseek-cli + mmx-cli 全通道）
# ------------------------------------------------------------------
Write-Host "`n[12.7] 实时用量采集体系 (v2.3)..." -ForegroundColor Cyan
$collScripts = @("usage_collector.py","mmx-cli.medit.ps1","monday_finalize.ps1","query_llm_week.py","create_sched.ps1","bitable_sync.ps1","telemetry_report.ps1","medit-telemetry.ps1","deepseek.ps1")
foreach ($f in $collScripts) {
  $src = Join-Path $PSScriptRoot "bin\$f"
  $dst = Join-Path $BIN_DIR $f
  if (-not (Test-Path $dst) -and (Test-Path $src)) {
    if ($CheckOnly) { Write-Host ("  - " + $f + " 缺失（全量部署时自动补齐）") -ForegroundColor Yellow }
    else { Copy-Item $src $dst -Force; Write-Host ("  - " + $f + " 已从安装包补齐") -ForegroundColor Green }
  } elseif (Test-Path $dst) { Write-Host ("  - " + $f + " 就位") -ForegroundColor Green }
}
$cTask = Get-ScheduledTask -TaskName "medit-usage-collector" -ErrorAction SilentlyContinue
$mTask = Get-ScheduledTask -TaskName "medit-monday-finalize" -ErrorAction SilentlyContinue
if (-not $cTask -or -not $mTask) {
  if ($CheckOnly) {
    Write-Host "  定时任务未注册（全量部署时自动运行 bin\create_sched.ps1 注册）" -ForegroundColor Yellow
  } else {
    Write-Host "  → 注册定时任务（5分钟采集 + 周一10:30校验）..." -ForegroundColor Yellow
    $sched = Join-Path $BIN_DIR "create_sched.ps1"
    if (Test-Path $sched) { & powershell -NoProfile -ExecutionPolicy Bypass -File $sched 2>&1 | Out-Null }
    Start-Sleep -Seconds 2
    $cTask2 = Get-ScheduledTask -TaskName "medit-usage-collector" -ErrorAction SilentlyContinue
    $mTask2 = Get-ScheduledTask -TaskName "medit-monday-finalize" -ErrorAction SilentlyContinue
    if ($cTask2 -and $mTask2) { Write-Host "  采集+周一校验任务 已注册" -ForegroundColor Green }
    else { Write-Host "  定时任务注册失败（可稍后手动运行 bin\create_sched.ps1）" -ForegroundColor Yellow }
  }
} else { Write-Host "  采集任务(每5分钟) + 周一校验任务(10:30) 已注册" -ForegroundColor Green }

Write-Host "`n==================== 部署报告 ====================" -ForegroundColor Cyan
$ok = ($report | Where-Object { $_.Status -in @("OK","FIXED") }).Count
$warn = ($report | Where-Object { $_.Status -eq "WARN" }).Count
$fail = ($report | Where-Object { $_.Status -eq "FAIL" }).Count
Write-Host "✅ 正常/已修复: $ok   ⚠️ 警告: $warn   ❌ 失败: $fail" -ForegroundColor $(if ($fail -gt 0) { "Red" } elseif ($warn -gt 0) { "Yellow" } else { "Green" })
Write-Host "日志: $LOG"
if ($fail -gt 0) {
  Write-Host "`n以下项需要处理（影响对应能力，主检索链路不受阻）：" -ForegroundColor Yellow
  $report | Where-Object { $_.Status -eq "FAIL" } | ForEach-Object { Write-Host "  ❌ $($_.Item): $($_.Detail)" }
}
