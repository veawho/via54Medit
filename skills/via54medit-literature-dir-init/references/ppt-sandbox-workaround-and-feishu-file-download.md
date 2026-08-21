# PowerPoint TCC 沙盒 workaround + 飞书群附件下载 SOP

实战日期: 2026-08-07
场景: 用户从飞书群 (医学AI-2026, oc_ae8f97997f6a4e7ced732d0609808760) @bot 传 PPT 附件
项目: TMA临床路径的诊断与鉴别 (33 页)
PPT 路径: /Users/david/Desktop/TMA_文献整理/TMA临床路径的诊断与鉴别.pptx (13.7 MB)

## 1. 飞书群附件下载 SOP

### 错误路径 (不要踩)

```bash
# ❶ 绝对路径 (报 234001 validation error)
lark-cli im +messages-resources-download --output /Users/david/...

# ❷ 用 lark-cli api GET /im/v1/files/{key} (报 234008 app is not the resource sender)
#    bot 不是上传者, 拿不到 user 上传的文件
```

### 正确路径 (已验证)

```bash
# 1. 找 chat_id (若已知, 跳过)
lark-cli im +chat-search --query "医学AI" --page-size 5

# 2. 拉群消息, 找 msg_type=file 那条
lark-cli im +chat-messages-list --chat-id oc_ae8f97997f6a4e7ced732d0609808760 --page-size 5
# 输出 content: <file key="file_v3_0014b_xxx" name="xxx.pptx"/>
# 输出 message_id: om_xxx
# 输出 file_key: file_v3_0014b_xxx

# 3. cd 到项目目录, 用相对 --output
cd /Users/david/Desktop/TMA_文献整理
lark-cli im +messages-resources-download \
    --message-id om_x100b686d80e710a0c4910428791963b \
    --file-key file_v3_0014b_77413c1e-e695-4abd-bd48-eb20f5f3c35g \
    --type file \
    --output TMA临床路径的诊断与鉴别.pptx \
    --as bot
```

成功输出:
```json
{
  "ok": true,
  "identity": "bot",
  "data": {
    "saved_path": "/Users/david/Desktop/TMA_文献整理/TMA临床路径的诊断与鉴别.pptx",
    "size_bytes": 13708478
  }
}
```

## 2. PowerPoint AppleScript -1728 诊断与修复

### 现象

`export_ppt_to_images.py` 报:
```
PowerPoint 失败: 142:156: execution error: "Microsoft PowerPoint"遇到一个错误：
The object you are trying to access does not exist (-1728)
```

诊断序列:
```bash
ps aux | grep -i powerpoint           # ✅ 进程 alive (PID 99747)
osascript -e 'tell app "Microsoft PowerPoint" to count of documents'  # 0
osascript -e 'tell app "Microsoft PowerPoint" to get name of front document'  # -1728
mcp__cua_driver__list_windows --pid 99747  # ✅ 窗口 6533 标题 "TMA临床路径的诊断与鉴别"
```

### 根因

macOS 13+ Sandbox + TCC 拦了 AppleScript 对 Microsoft Office 的自动化,但 app 级 AX (cua-driver) 不受该拦。文件其实开着,AX 树里能看到缩略图窗格 33 张 slide 的标题。

### 正确 fallback 路径

#### 路径 A: `python-pptx` 100% 可靠抽文字

引用分析 (A/B/C 列) 全部靠文字层, 不依赖 GUI。

```python
from pptx import Presentation
prs = Presentation("xxx.pptx")
for i, slide in enumerate(prs.slides, 1):
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                t = para.text.strip()
                if t:
                    print(f"SLIDE {i}: {t}")
```

输出: 33 页全部文字 + 底部引用, 包含中文正文、英文期刊引用、上标标号 (¹ ² ³) 的上下文。

#### 路径 B: PowerPoint GUI + screencapture 逐页截图

```python
import subprocess, os, time

OUT_DIR = "/Users/david/Desktop/TMA_文献整理/_ppt_renders"
os.makedirs(OUT_DIR, exist_ok=True)

def run_osascript(script):
    subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=15)

# 1. 聚焦 PowerPoint + 全屏
run_osascript('''
tell application "Microsoft PowerPoint" to activate
delay 1
tell application "System Events"
    tell process "Microsoft PowerPoint"
        set frontmost to true
        delay 0.5
        set position of first window to {0, 0}
        set size of first window to {1920, 1080}
    end tell
end tell''')
time.sleep(2)

# 2. 按 F5 进放映
run_osascript('''
tell application "System Events"
    tell process "Microsoft PowerPoint"
        key code 120  -- F5
    end tell
end tell''')
time.sleep(2.5)

# 3. 逐页截图 + → 翻页 (33 张)
for i in range(1, 34):
    run_osascript('''
tell application "System Events"
    tell process "Microsoft PowerPoint"
        set frontmost to true
    end tell''', timeout=5)
    time.sleep(0.4)
    outpath = f"{OUT_DIR}/slide_{i:03d}.jpg"
    subprocess.run(['screencapture', '-x', '-m', '-t', 'jpg', '-q', '92', outpath],
                   capture_output=True, text=True, timeout=8)
    if i < 33:
        run_osascript('''
tell application "System Events"
    tell process "Microsoft PowerPoint"
        key code 124  -- →
    end tell''', timeout=5)
        time.sleep(0.6)

# 4. Esc 退出放映
run_osascript('''
tell application "System Events"
    tell process "Microsoft PowerPoint"
        key code 53  -- Esc
    end tell''', timeout=5)
time.sleep(1.5)
```

**坑**: 如果放映模式失败 (PPT 仍在编辑界面), 截图会带工具栏 + 左边缩略图窗格。先用 `vision_analyze` 抽检 1-2 张确认是否干净; 不干净就用路径 A 替代。

**实测**: 2026-08-07 用 `key code 120 (F5)` 截图 33 张,每张 1-2 MB, 但截图带 PowerPoint 编辑界面 UI (不是放映全屏)。**引用文字层已用 python-pptx 完整替代,视觉图待后续优化**。

## 3. LibreOffice 陷阱

`brew cask install libreoffice` 26.2.5 装完后:
- `soffice` 包装脚本在 `/opt/homebrew/bin/soffice`,但脚本指向 `/Applications/LibreOffice.app/Contents/MacOS/soffice`
- 实际 `/opt/homebrew/Caskroom/libreoffice/26.2.5/LibreOffice.app` 是 symlink, 指向 `/Applications/LibreOffice.app`
- 如果 `/Applications/LibreOffice.app` 不存在,`soffice` 报 `exec: cannot execute`

**验证**: 先用 `ls -la /Applications/LibreOffice.app` + `soffice --version` 确认真可用再调; 否则一律不用。

## 4. 分工 (下次新 PPT 按此执行)

| 步骤 | 工具 | 状态 |
|------|------|------|
| 1. 飞书群附件下载 | `lark-cli +messages-resources-download` (相对路径) | ✅ |
| 2. 建 8 子目录 | `init_literature_dir.py --project` | ✅ |
| 3. 抽 PPT 文字 (含引用) | `python-pptx` (100% 可靠, 不需要 GUI) |
| 4. 渲染 PPT 图片 | 首选: `python-pptx` → 文字层已够; 次选: PowerPoint GUI + screencapture; 兜底: 用户手动导 PDF |
| 5. 4 列分析 | `analyze_ppt_citations.py --no-vision` + vision 抽检 |

## 参考

- `references/ppt-citation-4-column-analysis.md` — 4 列 CSV 分析 SOP
- `lark-cli im +messages-resources-download --help` — 绝对路径禁用的官方说明
- `mcp__cua_driver__list_windows` — 绕过 AppleScript 沙盒看 PowerPoint 真实窗口状态