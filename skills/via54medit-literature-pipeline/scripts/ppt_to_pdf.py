#!/usr/bin/env python3
"""ppt_to_pdf.py — PPT → PDF 导出 (**版式与文字由 Microsoft PowerPoint 产出**)

为什么单独一个模块
------------------
本文件位于权威工具链 ``scripts/hl_v3_final/``, 会被 ``scripts/sync_skill_bundle.py``
整目录镜像到技能分发包 ``skills/via54medit-literature-pipeline/scripts/``。
技能包必须**自包含** (会被分发到 ``~/.via54medit/skills/``), 不能 import 上层
``scripts/ppt_render_engine.py``, 所以这里放一份可独立运行的最小实现。

规则与判定标准 (2026-08-05 用户硬规则; 2026-09-11 用户澄清)
------------------------------------------------------------
用户 2026-09-11: "我是认为 PowerPoint 渲染出来的图片更符合原版, 如果有其他渲染图片
并不会改变 PowerPoint 排版与文字的方式也可以集成"。

所以标准是**保真**, 不是程序名:
  * **不可替代** —— PPTX→画面这一步 (版式/文字)。Keynote / LibreOffice / WPS /
    python-pptx 会各自重排 OOXML, 字体与布局和原版不一致, 一律不用。
  * **两个引擎可选, 且都由微软提供** —— ``RENDER_ENGINE=powerpoint``(默认, 桌面版) 或
    ``RENDER_ENGINE=graph``(Microsoft Graph 的 ``?format=pdf`` 在线转换)。后者需**显式指定**,
    不是自动降级目标; 与桌面版有已知差异。
  * **可以换** —— 把这里产出的**固定版式 PDF** 再栅格化成图片那一步 (不重排)。
  * 选定的引擎拿不到就**抛错**, 不产出近似渲染的替代品。
完整结论表见仓库 ``docs/ppt-render-fidelity.md``; 规则出处见
``references/v2.12.0-powerpoint-render-mandatory.md``。

用法
----
    python3 ppt_to_pdf.py <in.pptx> <out.pdf>
    from ppt_to_pdf import export_ppt_to_pdf
"""
import os
import subprocess
import sys
import time

#: 同目录兄弟模块(graph_render / Graph 客户端)要能直接 import —— 技能包自包含。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: AppleScript 超时(秒); 可用环境变量 PPT_RENDER_TIMEOUT 覆盖。
_DEFAULT_TIMEOUT = 60.0


def _engine_pref():
    """``RENDER_ENGINE``: ``powerpoint``(默认, 桌面版) 或 ``graph``(微软在线渲染)。"""
    return os.environ.get("RENDER_ENGINE", "powerpoint").strip().lower()


def _graph_module():
    """按需加载 Graph 客户端(与同目录 graph_render.py 同一份实现)。"""
    import graph_render
    return graph_render


#: PowerPoint 自动化被模态对话框挡住时给出的可操作提示。
#: 只讲怎么把 PowerPoint 修好; 另外点明**另一条微软引擎**的路(不是换成会重排的第三方引擎)。
_BLOCKED_HINT = (
    "PowerPoint 多半是弹了模态对话框(登录 / 激活 / 文件访问权限)挡住了 Apple 事件。"
    "请手动打开一次 PowerPoint, 关掉该对话框后再重试。"
    "若仍然卡住, 需排查 PowerPoint 自身状态(是否已激活、是否允许被自动化控制), "
    "而不是换成会重新排版的第三方引擎。"
    "自动化超时可用 PPT_RENDER_TIMEOUT(秒) 调整。"
    "另一条路: 若本机确实用不了桌面版 PowerPoint, 可**显式**设 RENDER_ENGINE=graph "
    "改用微软的在线渲染引擎(Office 在线; 与桌面版有已知差异, 见 docs/ppt-render-fidelity.md)。"
)


class PPTExportError(RuntimeError):
    """PPT → PDF 失败。``hint`` 是可操作建议 —— 由调用方**单独成行**打印, 避免被截断。"""

    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


def _timeout():
    """AppleScript 超时(秒)。非法值回落默认, 不抛。"""
    raw = os.environ.get("PPT_RENDER_TIMEOUT", "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT
    return val if val > 0 else _DEFAULT_TIMEOUT


def probe_powerpoint(timeout=20):
    """快速预检: 先确认 Apple 事件通道通不通 (launch + get version)。

    实测 0.4s —— 比直接去 `open` 上白等 300 秒强。返回 ``(ok, detail)``, **不抛异常**。
    """
    script = 'tell application "Microsoft PowerPoint"\nlaunch\nget version\nend tell'
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True,
                             text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, "预检失败: 无法执行 osascript (%s)" % e
    if res.returncode != 0:
        return False, "预检失败: %s" % (res.stderr or res.stdout).strip()[:200]
    return True, "PowerPoint %s" % res.stdout.strip()


def _is_apple_event_timeout(err):
    """判断是否 Apple 事件超时 (-1712)。"""
    return "-1712" in err or "超时" in err or "timed out" in err.lower()


def export_ppt_to_pdf(pptx_path, pdf_path):
    """用 PowerPoint 把整份 PPT 导出为 PDF, 返回 PDF 绝对路径。

    失败抛 ``PPTExportError`` (带可操作 hint), **不**改用会重排的第三方引擎。
    """
    abs_pptx = os.path.abspath(pptx_path)
    abs_pdf = os.path.abspath(pdf_path)
    parent = os.path.dirname(abs_pdf)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # 显式选定在线引擎时才走 Microsoft Graph(它不是自动降级目标)。
    if _engine_pref() == "graph":
        return _graph_module().export_ppt_to_pdf_via_graph(pptx_path, abs_pdf)

    if os.name == "nt":
        return _export_via_com(abs_pptx, abs_pdf)

    if sys.platform != "darwin":
        raise PPTExportError(
            "本平台没有桌面版 PowerPoint 通道 —— 版式规定必须由微软引擎产出、"
            "不用会重排的第三方引擎, 故不降级。"
            "可显式设 RENDER_ENGINE=graph 走微软的在线渲染引擎。")

    # 清掉可能卡死的残留实例(模态对话框会阻塞 Apple 事件, 表现为 -9074 / 超时)
    subprocess.run(["killall", "Microsoft PowerPoint"], capture_output=True, text=True)
    time.sleep(2.0)

    # (a) 快速预检: 通道不通就立刻报错, 不跑到 open 上白等
    ok, detail = probe_powerpoint()
    if not ok:
        raise PPTExportError(detail, _BLOCKED_HINT)

    # (b) 超时可用 PPT_RENDER_TIMEOUT 覆盖
    tmo = _timeout()
    script = f'''
with timeout of {int(tmo)} seconds
tell application "Microsoft PowerPoint"
    launch
    delay 3
    open POSIX file "{abs_pptx}"
    set thePres to active presentation
    save thePres in POSIX file "{abs_pdf}" as save as PDF
    close thePres saving no
end tell
end timeout
'''
    # subprocess 超时比 AppleScript 多 15s, 让 AppleScript 自己的 -1712 先报出来(信息更具体)
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                         timeout=tmo + 15)
    if res.returncode != 0 or not os.path.exists(abs_pdf):
        err = (res.stderr or res.stdout).strip()[-200:]
        raise PPTExportError(
            "PowerPoint AppleScript error: %s" % err,
            _BLOCKED_HINT if _is_apple_event_timeout(err) else "")
    return abs_pdf


def _export_via_com(pptx_path, pdf_path):
    """Windows: 用 PowerPoint COM 导出 PDF (ppSaveAsPDF = 32)。"""
    import win32com.client
    app = win32com.client.DispatchEx("PowerPoint.Application")
    pres = None
    try:
        try:
            app.Visible = False
        except Exception:
            pass
        try:
            app.DisplayAlerts = False
        except Exception:
            pass
        pres = app.Presentations.Open(pptx_path, ReadOnly=True,
                                      Untitled=False, WithWindow=False)
        pres.SaveAs(pdf_path, 32)
    finally:
        try:
            if pres is not None:
                pres.Close()
        except Exception:
            pass
        try:
            app.Quit()
        except Exception:
            pass
    if not os.path.exists(pdf_path):
        raise PPTExportError("PowerPoint COM 未产出 PDF: %s" % pdf_path)
    return pdf_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: ppt_to_pdf.py <in.pptx> <out.pdf>")
        sys.exit(1)
    try:
        out = export_ppt_to_pdf(sys.argv[1], sys.argv[2])
    except PPTExportError as e:
        print("导出失败: %s" % e, file=sys.stderr)
        if e.hint:
            print("处理建议: %s" % e.hint, file=sys.stderr)
        sys.exit(1)
    print(out)
