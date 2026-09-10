---
name: medit-telemetry-deploy
description: 在新设备上用一句自然语言单独部署 via54Medit / TraeWork 文献整理与 Highlight 监控统计及飞书同步工具 (medit-telemetry)。当用户说“在新设备上部署监控”、“部署文献监控”、“安装TraeWork监控”、“部署飞书同步”、“部署telemetry”时触发。
---

# medit-telemetry 跨设备一键自然语言部署技能

本技能用于在新设备或协作环境中，通过**单条命令或单句自然语言**全自动完成 `via54Medit` 文献监控统计与飞书同步工具的独立部署。

## 触发场景
当用户提出以下任意指令时立即触发本技能：
* “在新设备上单独部署via54Medit监控与飞书同步工具”
* “在新设备上部署监控”
* “帮我安装 TraeWork 监控并绑定飞书，花名叫xxx”
* “部署文献监控统计工具”
* “部署 telemetry”

## 执行逻辑与标准操作 (SOP)

智能体无需询问用户繁琐的技术细节，直接执行以下自动化流程：

### 1. 执行部署命令 (推荐单行)

#### 方案 A: PowerShell 极速单行 (Windows 首选)
若用户提供了花名或时间要求，直接拼入命令：
```powershell
powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 "在新设备上单独部署监控 [用户补充参数]"
```
或标准静默模式：
```powershell
powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Silent
```

#### 方案 B: 跨平台 Python 自然语言命令 (Windows / macOS / Linux)
```bash
python telemetry/deploy.py "在新设备上单独部署监控，花名<花名>，每周五18:00汇报"
```

#### 方案 C: via54 统一入口
```bash
python scripts/via54.py auto "在新设备上单独部署监控"
```

### 2. 自动化交付保障 (部署引擎自动完成)
1. **Python 环境与标准库自检** (零强制外部依赖)；
2. **`medit-telemetry` 独立包注册** (打通全局 `medit-telemetry` 与 `traework-telemetry` 命令)；
3. **花名与飞书凭据绑定** (自动优先继承本机 TraeWork 飞书连接凭据)；
4. **开机无感自启注册** (macOS 写入 LaunchAgent `com.via54medit.telemetry.plist`，Windows 写入 Startup 目录的 `traework_telemetry_silent.vbs`；重启/登录自动存活)；
5. **桌面伴生启动器生成** (桌面生成 `启动 TraeWork (带自动监控).vbs`，点击 Trae 同启监控)；
6. **后台主动监控守护进程拉起** (30秒主动巡检工作区，大模型 Token 默认 100% 服务商控制台对齐)。

### 3. 部署后状态核验
部署完成后，执行以下命令向用户展示部署状态与已捕获的历史战报：
```bash
medit-telemetry status
medit-telemetry daemon --status
```
向用户汇报：已在当前设备成功部署主动监控守护进程，开机自启已生效，Token 处于 100% 控制台对齐模式，并提供桌面伴随启动器路径。
