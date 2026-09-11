#!/usr/bin/env python3
"""
ppt_render_engine.py — PPT → 图片 渲染 (部署新系统即用)

渲染策略 (2026-09-04 用户规范):
  **只使用 PowerPoint 渲染** —— Windows 走 PowerPoint COM, macOS 走原生 PowerPoint (AppleScript)。
  **禁用其它通道**: 默认偏好下偏好引擎不可用就**直接失败**, 不静默降级到别的引擎。
  (2026-09-11 勘误: 本文档原先写"按优先级自动接入系统可用引擎 / macOS-Linux 优先 soffice
   否则 python-pptx 兜底", 与规范不符, 已改写。)

关于引擎偏好 RENDER_ENGINE:
  * 只认 ``powerpoint``(默认); 其它取值一律报错。
  * WPS / LibreOffice / python-pptx 等通道以及 "auto 自动降级" **已整体删除**,
    代码里不再存在(2026-09-11)。缺少 PowerPoint 时直接失败, 不降级、不近似渲染。

CJK 字体: 按平台探测 (Windows 微软雅黑 / macOS 苹方-简 / Linux Noto CJK)。

用法:
  from ppt_render_engine import render_ppt_slides_auto, detect_engines
  n, engine = render_ppt_slides_auto("D:/x.pptx", "D:/out")
"""
import os, sys, subprocess, time

# 渲染引擎: **只使用 PowerPoint**
#   (2026-09-04 用户规范; 2026-09-11 用户重申"只使用 PowerPoint 渲染, 禁用其它通道")
# 据此把 WPS / LibreOffice / python-pptx 三条通道**整体删除** —— 它们既不做默认、也不做兜底,
# 代码里已不存在。缺少 PowerPoint 时直接失败, 不降级。
COM_ENGINES = [
    ("PowerPoint", "PowerPoint.Application"),
]


def _engine_pref():
    """环境变量 RENDER_ENGINE 只认 ``powerpoint``(默认); 其它取值由 _build_engine_list 报错。"""
    return os.environ.get("RENDER_ENGINE", "powerpoint").strip().lower()


# 偏好引擎 → 引擎标识
_PREF_MAP = {
    "powerpoint": ("PowerPoint", "com", "PowerPoint.Application"),
    "ppt": ("PowerPoint", "com", "PowerPoint.Application"),
}


def _progid_available(progid):
    """注册表检查 COM ProgID 是否已注册 (Windows)"""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid):
            return True
    except OSError:
        return False
    except Exception:
        return False


def _ensure_pywin32(progid_hint=""):
    """确保 win32com 可用; 检测到 COM 引擎但缺 pywin32 时自动安装"""
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        pass
    if os.name != "nt":
        return False
    if progid_hint and not _progid_available(progid_hint):
        return False
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "pywin32"],
                       capture_output=True, timeout=300)
        import win32com.client  # noqa: F401
        return True
    except Exception:
        return False


def _com_probe(progid):
    """COM 试连 (会短暂启动应用), 成功返回 True"""
    try:
        import win32com.client
        app = win32com.client.DispatchEx(progid)  # DispatchEx: 强制新实例 (Dispatch 对 PowerPoint 有连接残留问题)
        try:
            app.Quit()
        except Exception:
            pass
        return True
    except Exception:
        return False


def _macos_powerpoint_available():
    """检查 macOS 系统中是否安装有 Microsoft PowerPoint"""
    if sys.platform != "darwin":
        return False
    try:
        r = subprocess.run(["osascript", "-e", 'id of app "Microsoft PowerPoint"'],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and "com.microsoft.Powerpoint" in r.stdout
    except Exception:
        return False


def detect_engines():
    """返回本机可用的 **PowerPoint** 引擎列表 [(name, kind, target), ...]。

    kind: ``com`` (Windows COM) | ``macos_ppt`` (macOS 原生 PowerPoint / AppleScript)。
    **只探测 PowerPoint** —— 其它渲染通道已按规范禁用并从本模块删除(2026-09-04 / 2026-09-11)。
    保留本函数是为 ``deps_auto`` 与 ``bootstrap_device`` 的依赖与设备就绪检查。
    """
    out = []
    if os.name == "nt":
        for name, progid in COM_ENGINES:
            if _progid_available(progid):
                if _ensure_pywin32(progid) and _com_probe(progid):
                    out.append((name, "com", progid))
    if sys.platform == "darwin" and _macos_powerpoint_available():
        out.append(("PowerPoint (macOS)", "macos_ppt", "com.microsoft.Powerpoint"))
    return out


# ============ macOS 原生 PowerPoint 真实渲染 ============
#: macOS PowerPoint 自动化的 open/save 超时(秒), 可用 PPT_RENDER_TIMEOUT 覆盖。
#: 默认 60 (原为写死的 300): 实测 open 被模态对话框挡住时会一直挂住, 300s 只是让用户白等 5 分钟。
_DEFAULT_MACOS_TIMEOUT = 60.0
#: 预检超时(秒), 可用 PPT_RENDER_PREFLIGHT_TIMEOUT 覆盖。
#: 只做 launch + get version —— 实测暖机 0.4s 返回, 20s 足够覆盖冷启动。
_DEFAULT_MACOS_PREFLIGHT_TIMEOUT = 20.0

#: PowerPoint 自动化被模态对话框挡住时给出的可操作提示。
#: **只讲怎么把 PowerPoint 修好, 不提任何其它渲染通道** —— 规范是只走 PowerPoint 一条路。
#: (2026-09-11 勘误: 此处原先写着"可改用 libreoffice / python-pptx", 那是**引导改用其它通道**,
#:  违反 2026-09-04 的用户规范, 已删除。)
_MACOS_BLOCKED_HINT = (
    "PowerPoint 多半是弹了模态对话框(登录 / 激活 / 文件访问权限)挡住了 Apple 事件。"
    "请手动打开一次 PowerPoint, 关掉该对话框后再重试。"
    "若仍然卡住, 需排查 PowerPoint 自身状态(是否已激活、是否允许被自动化控制), "
    "而不是绕过它 —— 按规范渲染只走 PowerPoint 这一条通道, 不会自动改用其它引擎。"
    "自动化超时可用 PPT_RENDER_TIMEOUT(秒) 调整。"
)


def _env_seconds(name, default):
    """读环境变量为秒数; 缺失/不可解析/非正数一律回落到 default。"""
    try:
        v = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)
    return v if v > 0 else float(default)


def _macos_render_timeout():
    return _env_seconds("PPT_RENDER_TIMEOUT", _DEFAULT_MACOS_TIMEOUT)


def _macos_preflight_timeout():
    return _env_seconds("PPT_RENDER_PREFLIGHT_TIMEOUT", _DEFAULT_MACOS_PREFLIGHT_TIMEOUT)


def probe_macos_powerpoint(timeout=None):
    """预检 macOS PowerPoint 是否响应 Apple 事件。返回 (ok, 详情)。

    只做 ``launch`` + ``get version`` —— 实测暖机 0.4s 返回。
    存在的意义是**快速失败**: 2026-09-11 实测 ``open`` 这一步会被模态对话框挡住,
    而 PowerPoint 进程本身是活的(``get version`` 紧接着仍 0.1s 应答),
    所以"能不能应答 Apple 事件"无法区分二者, 但至少能在**通道完全不通**时立刻报错,
    不必在 open 上白等几分钟。
    """
    tmo = timeout if timeout is not None else _macos_preflight_timeout()
    script = (
        "with timeout of %d seconds\n"
        'tell application "Microsoft PowerPoint"\n'
        "launch\n"
        "get version\n"
        "end tell\n"
        "end timeout\n" % int(tmo)
    )
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=tmo + 10)
    except subprocess.TimeoutExpired:
        return False, "预检超时(%ds): PowerPoint 未在超时内应答 Apple 事件" % int(tmo)
    except OSError as e:
        return False, "预检无法执行 osascript: %s" % e
    if r.returncode != 0:
        return False, "预检失败: %s" % (r.stderr or r.stdout).strip()[-200:]
    return True, "PowerPoint %s" % (r.stdout or "").strip()


def _is_apple_event_timeout(err):
    return "-1712" in err or "超时" in err or "timed out" in err.lower()


class RenderEngineError(RuntimeError):
    """渲染引擎失败。``hint`` 是可选的**可操作建议**, 空字符串表示没有额外建议。

    为什么不把建议拼进消息里: 调用方打印消息时会截断(``render_ppt_slides_auto`` 用
    ``str(e)[:160]``), 建议拼在**末尾**会被整段切掉 —— 2026-09-11 就踩过这一次;
    拼在**最前面**又把原始错误挤没了, 还留下"｜ 原"这种半截断口。故单独用属性承载。
    """
    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


def render_via_macos_powerpoint(pptx_path, out_dir, dpi=150):
    """macOS 下通过 AppleScript 控制原生 Microsoft PowerPoint 导出 PDF，再由 PyMuPDF 导出高清 PNG

    先做一次快速预检(``probe_macos_powerpoint``), 不通过就**立刻报错**并给出可操作提示,
    不再像以前那样在 open 上白等 300 秒。
    """
    import tempfile
    import pymupdf as fitz
    abs_pptx = os.path.abspath(pptx_path)
    os.makedirs(out_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="ppt_mac_")
    tmp_pdf = os.path.join(tmp_dir, "slides.pdf")
    # 清理可能残留的卡死实例(模态对话框会阻塞 Apple 事件, 表现为 -9074/超时)
    subprocess.run(["killall", "Microsoft PowerPoint"], capture_output=True, text=True)
    time.sleep(2.0)
    try:
        # (a) 快速预检: 先确认 Apple 事件通道通不通, 通了再花时间 open
        ok, detail = probe_macos_powerpoint()
        if not ok:
            raise RenderEngineError(detail, _MACOS_BLOCKED_HINT)

        # (b) 超时可用 PPT_RENDER_TIMEOUT 覆盖 (默认由 300 降到 60)
        tmo = _macos_render_timeout()
        script = f'''
    with timeout of {int(tmo)} seconds
    tell application "Microsoft PowerPoint"
        launch
        delay 3
        open POSIX file "{abs_pptx}"
        set thePres to active presentation
        save thePres in POSIX file "{tmp_pdf}" as save as PDF
        close thePres saving no
    end tell
    end timeout
    '''
        # subprocess 超时比 AppleScript 多 15s, 让 AppleScript 自己的 -1712 先报出来(信息更具体)
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                             timeout=tmo + 15)
        if res.returncode != 0 or not os.path.exists(tmp_pdf):
            err = (res.stderr or res.stdout).strip()[-200:]
            raise RenderEngineError(
                "PowerPoint AppleScript error: %s" % err,
                _MACOS_BLOCKED_HINT if _is_apple_event_timeout(err) else "")
        doc = fitz.open(tmp_pdf)
        n = 0
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            pix.save(os.path.join(out_dir, "slide_%03d.png" % i))
            n += 1
        doc.close()
        return n
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============ COM 真实渲染 ============
def render_via_com(progid, pptx_path, out_dir, width_px=1600):
    """用 PowerPoint/WPS COM 把每页 slide 导出为 PNG"""
    import win32com.client
    app = win32com.client.DispatchEx(progid)
    pres = None
    n = 0
    try:
        try:
            app.Visible = False
        except Exception:
            pass
        try:
            app.DisplayAlerts = False
        except Exception:
            pass
        pres = app.Presentations.Open(pptx_path, ReadOnly=True, Untitled=False, WithWindow=False)
        slides = pres.Slides
        total = slides.Count
        # 按页面比例求高度
        try:
            w = pres.PageSetup.SlideWidth
            h = pres.PageSetup.SlideHeight
        except Exception:
            w, h = 12192000, 6858000  # 16:9 EMU 兜底
        height_px = int(width_px * h / w) if w else int(width_px * 9 / 16)
        for i in range(1, total + 1):
            out_png = os.path.join(out_dir, "slide_%03d.png" % i)
            slides(i).Export(out_png, "PNG", width_px, height_px)
            n += 1
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
    return n


def _build_engine_list():
    """构造待用引擎列表。**只会有 PowerPoint** —— Windows COM 或 macOS 原生。

    其它渲染通道已按规范禁用并删除, 故这里没有降级链: 拿不到 PowerPoint 就抛错。
    """
    pref = _engine_pref()
    spec = _PREF_MAP.get(pref)
    if spec is None:
        raise RuntimeError(
            "未知 RENDER_ENGINE=%r —— 按规范只支持 powerpoint(默认)。"
            "其它渲染通道已禁用并删除。" % pref)
    name, kind, progid = spec
    if os.name == "nt":
        if not (_progid_available(progid) and _ensure_pywin32(progid) and _com_probe(progid)):
            raise RuntimeError(
                "[render] PowerPoint (COM %s) 在本机不可用 —— 规范要求只使用 PowerPoint 渲染、"
                "禁用其它通道, 故不降级。请确认 PowerPoint 已安装并激活。" % progid)
        return [(name, kind, progid)]
    if sys.platform == "darwin" and _macos_powerpoint_available():
        return [("PowerPoint (macOS)", "macos_ppt", "com.microsoft.Powerpoint")]
    raise RuntimeError(
        "[render] PowerPoint 在本机不可用 —— 规范要求只使用 PowerPoint 渲染、"
        "禁用其它通道, 故不降级。请确认 PowerPoint 已安装并激活; "
        "macOS 还需在 系统设置 › 隐私与安全性 › 自动化 里允许其被控制。")


def render_ppt_slides_auto(pptx_path, out_dir, width_px=1600):
    """用 PowerPoint 渲染全部 slide, 返回 (count, engine_name)。

    引擎恒为 PowerPoint (Windows COM / macOS 原生)。按规范**不切换其它通道**:
    拿不到 PowerPoint 就返回 ``(0, "none")``, 不会退化成别的渲染方式。
    """
    os.makedirs(out_dir, exist_ok=True)
    try:
        engines = _build_engine_list()
    except Exception as e:
        print("  [render] %s" % str(e), flush=True)
        print("  [render] 提示: 只使用 PowerPoint 渲染; 其它通道已禁用", flush=True)
        return 0, "none"
    for idx, (name, kind, progid) in enumerate(engines):
        is_last = idx == len(engines) - 1
        try:
            if kind == "com":
                print("  [render] 引擎=%s (COM %s)" % (name, progid), flush=True)
                n = render_via_com(progid, pptx_path, out_dir, width_px)
                if n > 0:
                    return n, name
            elif kind == "macos_ppt":
                print("  [render] 引擎=%s (AppleScript)" % name, flush=True)
                n = render_via_macos_powerpoint(pptx_path, out_dir)
                if n > 0:
                    return n, name
            else:
                # 通道已被禁用, 正常不会到达
                print("  [render] 未知引擎类型 %r —— 其它渲染通道已按规范禁用" % kind, flush=True)
        except Exception as e:
            # 消息截断到 160; **可操作建议单独成行**打印 —— 拼在消息里会被截断切掉。
            tail = "" if is_last else " (尝试下一引擎)"
            print("  [render] %s 失败: %s%s" % (name, str(e)[:160], tail), flush=True)
            hint = getattr(e, "hint", "")
            if hint:
                print("  [render] 处理建议: %s" % hint, flush=True)
    print("  [render] PowerPoint 渲染失败, 返回 0 张幻灯片 (按规范不切换其它通道)", flush=True)
    return 0, "none"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx")
    parser.add_argument("out_dir")
    parser.add_argument("--width", type=int, default=1600)
    ns = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    n, engine = render_ppt_slides_auto(ns.pptx, ns.out_dir, ns.width)
    print("渲染 %d 页, 引擎: %s" % (n, engine))
