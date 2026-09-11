#!/usr/bin/env python3
"""
ppt_render_engine.py — PPT → 图片 渲染 (部署新系统即用)

渲染策略 (2026-08-05 用户硬规则; 2026-09-11 用户两次澄清):

  **版式与文字必须来自微软的引擎**。这一步不可替代: PPTX 只是描述性格式, 第三方引擎会各自
  重排 OOXML, 字体回退 / 断行 / autofit / SmartArt 都与原版分叉。可用的两个引擎:

    * ``powerpoint``(**默认**) —— 桌面版 PowerPoint: Windows 走 COM, macOS 走原生 AppleScript。
      保真上限最高; 能直出位图 (Windows `Slide.Export`) 就不必绕 PDF, 也就绕开了
      "字体未内嵌"的风险。
    * ``graph``(**显式选择**) —— Microsoft Graph 的 ``?format=pdf`` 转换(Office 在线渲染)。
      同样出自微软, 适合"本机没有桌面版 PowerPoint"(Linux/CI)或桌面版故障时的**显式**替代;
      与桌面版有**已知差异**(在线引擎的字体替换 / 符号占位 / 部分对象行为), 见
      ``docs/ppt-render-fidelity.md``。

  **判定标准是"会不会重新排版", 不是"是不是 PowerPoint 这个程序"** —— 用户 2026-09-11:
  "我是认为 PowerPoint 渲染出来的图片更符合原版, 如果有其他渲染图片并不会改变 PowerPoint
   排版与文字的方式也可以集成"。所以把固定版式的 PDF **再栅格化**那一步(只解释绘制指令、
  不重排)换工具**不算换通道**: 由 ``RENDER_RASTERIZER`` 选 ``pymupdf``(默认) / ``pdftoppm``
  (强制 ``-cropbox``)。

  **会重新排版的一律禁止**: LibreOffice / Keynote / WPS / python-pptx / Aspose / Spire /
  GroupDocs / Syncfusion。选定的引擎拿不到就**直接失败**, 不降级。
  (2026-09-11 二次勘误: 本文档上一版写成"禁用任何其它图片生成方式", 那**比规则本身更严**;
   规则的标准是保真, 不是程序名。)

关于引擎偏好 RENDER_ENGINE:
  * 只认 ``powerpoint``(默认) / ``graph``; 其它取值一律报错。
  * WPS / LibreOffice / python-pptx 等**会重新排版**的通道以及 "auto 自动降级" 已整体删除 ——
    所以**没有**"拿不到桌面版就自动切到 graph"这种事, 必须自己显式指定。

用法:
  from ppt_render_engine import render_ppt_slides_auto, detect_engines
  n, engine = render_ppt_slides_auto("D:/x.pptx", "D:/out")
"""
import os, sys, subprocess, time

# 排版引擎: **只用微软的引擎** —— 桌面版 PowerPoint, 或显式选定的 Microsoft Graph。
#   WPS / LibreOffice / python-pptx 等会**重新排版**, 故整体删除 —— 既不做默认, 也不做兜底。
#   注意区分: "换排版引擎"禁止; "把已排好的固定版式栅格化"允许
#   (见下方 RENDER_RASTERIZER 与 docs/ppt-render-fidelity.md)。
COM_ENGINES = [
    ("PowerPoint", "PowerPoint.Application"),
]


def _engine_pref():
    """环境变量 RENDER_ENGINE: ``powerpoint``(默认) 或 ``graph``; 其它取值由 _build_engine_list 报错。"""
    return os.environ.get("RENDER_ENGINE", "powerpoint").strip().lower()


# 偏好引擎 → 引擎标识。
# 两个取值**都是微软的引擎**, 区别只在"桌面版"还是"在线版":
#   * powerpoint —— 桌面版 PowerPoint(Windows COM / macOS 原生)。**默认**, 保真上限最高。
#   * graph      —— Microsoft Graph 的 ``?format=pdf`` 转换(Office 在线渲染)。**必须显式选择**,
#                   它不是自动降级目标; 且与桌面版有已知差异(见 docs/ppt-render-fidelity.md)。
_PREF_MAP = {
    "powerpoint": ("PowerPoint", "com", "PowerPoint.Application"),
    "ppt": ("PowerPoint", "com", "PowerPoint.Application"),
    "graph": ("Microsoft Graph (Office 在线渲染)", "graph", "graph.microsoft.com"),
}

#: Graph 客户端实现放在权威工具链 ``hl_v3_final/`` 里 —— 与 ``ppt_to_pdf.py`` 同一先例:
#: 那个目录会被 ``sync_skill_bundle.py`` 镜像到技能分发包, 于是技能包也能用上 Graph 通道,
#: 不必在这里再抄一份。
_HL_V3_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hl_v3_final")


def _graph_module():
    """按需加载 Graph 客户端(不在这里重复实现)。"""
    if _HL_V3_DIR not in sys.path:
        sys.path.insert(0, _HL_V3_DIR)
    import graph_render
    return graph_render


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
    **只探测 PowerPoint** —— 其它**排版引擎**(会重新排版的那些)已按规范删除
    (2026-08-05 用户硬规则 / 2026-09-11 澄清判定标准)。注意: 只光栅化的下游工具
    (PyMuPDF / pdftoppm)不在此列, 见 ``_RASTERIZERS`` 与 docs/ppt-render-fidelity.md。
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
#: **只讲怎么把 PowerPoint 修好, 不提任何其它排版引擎** —— 版式必须来自 PowerPoint。
#: (2026-09-11 勘误: 此处原先写着"可改用 libreoffice / python-pptx", 那是**引导改用其它排版引擎**,
#:  已删除。)
_MACOS_BLOCKED_HINT = (
    "PowerPoint 多半是弹了模态对话框(登录 / 激活 / 文件访问权限)挡住了 Apple 事件。"
    "请手动打开一次 PowerPoint, 关掉该对话框后再重试。"
    "若仍然卡住, 需排查 PowerPoint 自身状态(是否已激活、是否允许被自动化控制), "
    "而不是换成会重新排版的第三方引擎。"
    "自动化超时可用 PPT_RENDER_TIMEOUT(秒) 调整。"
    "另一条路: 若本机确实用不了桌面版 PowerPoint, 可**显式**设 RENDER_ENGINE=graph "
    "改用微软的在线渲染引擎(Office 在线; 与桌面版有已知差异, 见 docs/ppt-render-fidelity.md)。"
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


def export_ppt_to_pdf(pptx_path, pdf_path):
    """用**微软的引擎**把整份 PPT 导出为 PDF (桌面版 PowerPoint, 或显式选定的 Microsoft Graph)。

    Windows 走 PowerPoint COM, macOS 走原生 PowerPoint AppleScript; 两者都拿不到时,
    **只有**显式设置 ``RENDER_ENGINE=graph`` 才会改走 Microsoft Graph 的在线转换。

    **不 fallback** 到 Keynote / LibreOffice / WPS / python-pptx —— 那些引擎会各自重排 OOXML,
    字体与布局和原版不一致 (2026-08-05 用户硬规则; 2026-09-11 用户澄清判定标准 = 保真,
    不是程序名 —— 见 docs/ppt-render-fidelity.md)。

    注意: 本函数**只负责定版式**。把产出的 PDF 再栅格化成图片是另一回事, 那一步不重排,
    因此可以换工具 (``_RASTERIZERS``)。

    拿不到可用引擎或导出失败时抛 ``RenderEngineError``(带可操作 hint), 不返回半成品。
    """
    abs_pptx = os.path.abspath(pptx_path)
    abs_pdf = os.path.abspath(pdf_path)
    out_parent = os.path.dirname(abs_pdf)
    if out_parent:
        os.makedirs(out_parent, exist_ok=True)

    # 显式选定在线引擎时才走 Graph(它不是自动降级目标)。
    if _engine_pref() == "graph":
        return _graph_module().export_ppt_to_pdf_via_graph(pptx_path, abs_pdf)

    if os.name == "nt":
        return _export_ppt_to_pdf_com(pptx_path, abs_pdf)

    if sys.platform != "darwin":
        raise RenderEngineError(
            "[render] 本平台没有桌面版 PowerPoint 通道 —— 版式规定必须由微软引擎产出、"
            "不用会重排的第三方引擎, 故不降级。"
            "可显式设 RENDER_ENGINE=graph 走微软的在线渲染引擎。")

    # 清理可能残留的卡死实例(模态对话框会阻塞 Apple 事件, 表现为 -9074/超时)
    subprocess.run(["killall", "Microsoft PowerPoint"], capture_output=True, text=True)
    time.sleep(2.0)

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
        raise RenderEngineError(
            "PowerPoint AppleScript error: %s" % err,
            _MACOS_BLOCKED_HINT if _is_apple_event_timeout(err) else "")
    return abs_pdf


def _export_ppt_to_pdf_com(pptx_path, pdf_path):
    """Windows: 用 PowerPoint COM 导出 PDF (ppSaveAsPDF = 32)。"""
    import win32com.client
    _, _, progid = _build_engine_list()[0]   # 只会有 PowerPoint
    app = win32com.client.DispatchEx(progid)
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
        pres = app.Presentations.Open(pptx_path, ReadOnly=True, Untitled=False, WithWindow=False)
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
        raise RenderEngineError("[render] PowerPoint COM 未产出 PDF: %s" % pdf_path)
    return pdf_path


# ============ 固定版式栅格化 (不重排 —— 不属于"换通道") ============
#: 把 PowerPoint 导出的**固定版式 PDF** 转成图片的实现。这些工具只解释 PDF 的绘制指令,
#: **不含重排/回流机制**, 因此不会改变 PowerPoint 已经定下的版式与文字位置 —— 换它们不算换通道。
#: (历史佐证: 参考文档 v2.12.0 的原始实现就是 PowerPoint 导 PDF + pdftoppm 转 JPG。)
_RASTERIZERS = {
    "pymupdf": "PyMuPDF (fitz) get_pixmap —— 按 CropBox 渲染, 无偏移",
    "pdftoppm": "poppler pdftoppm —— 强制 -cropbox, 否则默认按 MediaBox 渲染会带白边/偏移",
}
_DEFAULT_RASTERIZER = "pymupdf"


def _rasterizer_pref():
    """``RENDER_RASTERIZER`` 选择栅格化器; 未知取值直接报错(不猜、不降级)。"""
    name = os.environ.get("RENDER_RASTERIZER", _DEFAULT_RASTERIZER).strip().lower()
    if name not in _RASTERIZERS:
        raise RenderEngineError(
            "未知 RENDER_RASTERIZER=%r —— 只支持 %s。\n"
            "[render] 可换的只是「把 PowerPoint 已排好的固定版式栅格化」这一步(不重排); "
            "任何会重新排版的渲染器 (LibreOffice / Keynote / WPS / python-pptx / Aspose / "
            "Spire / GroupDocs / Syncfusion) 都不在候选内 —— 见 docs/ppt-render-fidelity.md。"
            % (name, " / ".join(sorted(_RASTERIZERS))))
    return name


def _non_embedded_fonts(pdf_path):
    """列出 PDF 里**字形不随文档走**的字体名 (去重; 空列表 = 全部已内嵌)。

    为什么关心: 字体没内嵌时, 栅格化器只能拿自己的替代字体去画 —— **字形就不再由 PowerPoint
    的产物决定**, 那正是"改变了 PowerPoint 的文字"。文字的位置与字距来自 PDF 本身、不会漂移,
    但字形会变。

    判定依据(实测 PyMuPDF ``page.get_fonts()`` 第 2 项 ``ext``):
      * 已内嵌 -> 真实扩展名, 如 ``ttf`` / ``cff`` / ``cid``;
      * 未内嵌 -> ``''``(有字体引用但没有字体文件);
      * base-14 标准字体(Helvetica/Times/Courier...) -> ``n/a``, 同样**不是**随文档走的字形。
    所以 ``''`` 与 ``n/a`` 都算"字形不随文档走"。

    探测失败时返回空列表(不因为查不出来就打断渲染)。
    """
    import pymupdf as fitz
    names = []
    try:
        doc = fitz.open(pdf_path)
        try:
            for page in doc:
                for f in page.get_fonts(full=False):
                    # 元组形如 (xref, ext, type, basefont, name, encoding, referencer)
                    if len(f) < 4:
                        continue
                    ext, basefont = str(f[1]), str(f[3])
                    if ext in ("", "n/a") and basefont and basefont not in names:
                        names.append(basefont)
        finally:
            doc.close()
    except Exception:
        return []
    return names


def _rasterize_with_pymupdf(pdf_path, out_dir, dpi):
    import pymupdf as fitz
    doc = fitz.open(pdf_path)
    try:
        n = 0
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            pix.save(os.path.join(out_dir, "slide_%03d.png" % i))
            n += 1
        return n
    finally:
        doc.close()


def _rasterize_with_pdftoppm(pdf_path, out_dir, dpi):
    """poppler 版。**必须带 ``-cropbox``** —— 它默认按 MediaBox 渲染, 页面若被裁过就会带出
    白边/偏移, 那就等于改变了版式(本仓库历史上被这个坑咬过一次, 见 render_fitz.py 的说明)。"""
    import shutil as _shutil
    exe = _shutil.which("pdftoppm")
    if not exe:
        raise RenderEngineError(
            "RENDER_RASTERIZER=pdftoppm 但本机没有 pdftoppm (poppler-utils)。"
            "可改用默认的 pymupdf(pymupdf 在本仓库是硬依赖), 或 `brew install poppler`。")
    prefix = os.path.join(out_dir, "slide")
    res = subprocess.run([exe, "-png", "-r", str(int(dpi)), "-cropbox", pdf_path, prefix],
                         capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise RenderEngineError("pdftoppm 失败: %s"
                                % (res.stderr or res.stdout).strip()[-200:])
    # pdftoppm 产出 slide-1.png / slide-01.png, 统一改名成 slide_001.png (与 PyMuPDF 一致)
    n = 0
    for name in sorted(os.listdir(out_dir)):
        if not (name.startswith("slide-") and name.endswith(".png")):
            continue
        idx = name[len("slide-"):-len(".png")]
        if not idx.isdigit():
            continue
        n = max(n, int(idx))
        os.replace(os.path.join(out_dir, name),
                   os.path.join(out_dir, "slide_%03d.png" % int(idx)))
    return n


def _rasterize_pdf(pdf_path, out_dir, dpi):
    """把固定版式 PDF 每页栅格化成 ``slide_NNN.png``, 返回页数。

    这一步**只光栅化、不重排**, 所以用什么工具都不改变 PowerPoint 的版式与文字 —— 正是
    用户 2026-09-11 说的"不会改变 PowerPoint 排版与文字的方式也可以集成"。
    """
    os.makedirs(out_dir, exist_ok=True)
    if _rasterizer_pref() == "pdftoppm":
        return _rasterize_with_pdftoppm(pdf_path, out_dir, dpi)
    return _rasterize_with_pymupdf(pdf_path, out_dir, dpi)


def _pdf_to_slides(tmp_pdf, out_dir, dpi):
    """固定版式 PDF → ``slide_NNN.png``, 含**字体是否内嵌**的保真检查。

    这一步与"是谁排的版"无关: 它只把已经排好的页面光栅化, 不重排。
    """
    missing = _non_embedded_fonts(tmp_pdf)
    if missing:
        print("  [render] ⚠️ 导出的 PDF 里有未内嵌字体: %s" % ", ".join(missing[:6]), flush=True)
        print("  [render]    栅格化时这些字体会被替代品替换, 字形可能和原版不同 —— "
              "建议在源应用里嵌入字体后重导 "
              "(保真度说明见 docs/ppt-render-fidelity.md)", flush=True)
    return _rasterize_pdf(tmp_pdf, out_dir, dpi)


def _export_then_rasterize(pptx_path, out_dir, dpi, tmp_prefix):
    """``export_ppt_to_pdf`` → 字体检查 → 栅格化。桌面版与在线版两条路共用。"""
    import tempfile
    os.makedirs(out_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=tmp_prefix)
    try:
        tmp_pdf = os.path.join(tmp_dir, "slides.pdf")
        export_ppt_to_pdf(pptx_path, tmp_pdf)
        return _pdf_to_slides(tmp_pdf, out_dir, dpi)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def render_via_macos_powerpoint(pptx_path, out_dir, dpi=150):
    """macOS: 用**原生 PowerPoint**(桌面版) 定版式, 再把固定版式的 PDF 栅格化成 PNG。

    两步的职责必须分清 (判定标准见 ``docs/ppt-render-fidelity.md``):

      1. ``export_ppt_to_pdf`` —— 版式与文字由 PowerPoint 产出, **不可替代**。内含快速预检:
         通道不通就**立刻报错**并给出可操作提示, 不再像以前那样在 open 上白等 300 秒。
      2. ``_pdf_to_slides`` —— 只把已排好的页面光栅化, **不重排**, 所以这一步换工具不算换通道
         (默认 PyMuPDF; ``RENDER_RASTERIZER=pdftoppm`` 可选)。
    """
    return _export_then_rasterize(pptx_path, out_dir, dpi, "ppt_mac_")


def render_via_graph(pptx_path, out_dir, dpi=150):
    """用 **Microsoft Graph**(Office 在线渲染) 定版式, 再本地栅格化成 PNG。

    为什么走 PDF 而不是 jpg: 官方对 ``pptx→jpg`` 只给**第一张幻灯片**(见
    docs/ppt-render-fidelity.md), 整份只有 ``format=pdf`` 这条路走得起。
    版式仍由**微软的引擎**产出(符合"版式必须来自微软引擎"), PDF→PNG 那一步不重排。

    与桌面版 PowerPoint 有**已知差异**(在线引擎的字体替换、符号占位、部分对象行为),
    所以它是 ``RENDER_ENGINE=graph`` 的**显式选项**, 既不是默认, 也不是降级目标。
    """
    return _export_then_rasterize(pptx_path, out_dir, dpi, "ppt_graph_")


# ============ COM 真实渲染 ============
def render_via_com(progid, pptx_path, out_dir, width_px=1600):
    """用 PowerPoint COM 把每页 slide 导出为 PNG —— **PowerPoint 自己出位图**, 保真上限最高,
    且绕开"PDF 字体未内嵌 → 栅格化替换字形"的风险 (所以能直出就不必绕 PDF)。"""
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
    """构造待用**排版引擎**列表。**只会有微软的引擎** —— 桌面版 PowerPoint 或 Microsoft Graph。

    它们之间**没有自动降级链**: 选哪个由 ``RENDER_ENGINE`` 决定, 拿不到就抛错。
    (下游只光栅化的工具不走这里 —— 它们是 ``_RASTERIZERS``。)
    """
    pref = _engine_pref()
    spec = _PREF_MAP.get(pref)
    if spec is None:
        raise RuntimeError(
            "未知 RENDER_ENGINE=%r —— 只支持 powerpoint(默认) / graph。"
            "会重新排版的第三方引擎已删除。" % pref)
    name, kind, progid = spec
    if kind == "graph":
        # 显式选择的在线引擎: 只校验凭据, **不会**在失败时退到桌面版或别的引擎。
        err = _graph_module().credentials_error()
        if err:
            raise RuntimeError("[render] RENDER_ENGINE=graph 但凭据不全。\n%s" % err)
        return [(name, kind, progid)]
    if os.name == "nt":
        if not (_progid_available(progid) and _ensure_pywin32(progid) and _com_probe(progid)):
            raise RuntimeError(
                "[render] PowerPoint (COM %s) 在本机不可用 —— 版式规定必须由微软引擎产出、"
                "不用会重排的第三方引擎, 故不降级。请确认 PowerPoint 已安装并激活。" % progid)
        return [(name, kind, progid)]
    if sys.platform == "darwin" and _macos_powerpoint_available():
        return [("PowerPoint (macOS)", "macos_ppt", "com.microsoft.Powerpoint")]
    raise RuntimeError(
        "[render] PowerPoint 在本机不可用 —— 版式规定必须由微软引擎产出、"
        "不用会重排的第三方引擎, 故不降级。请确认 PowerPoint 已安装并激活; "
        "macOS 还需在 系统设置 › 隐私与安全性 › 自动化 里允许其被控制。\n"
        "[render] 若本机确实装不了/用不了桌面版 PowerPoint, 可**显式**设 "
        "RENDER_ENGINE=graph 走微软的在线渲染引擎(Office 在线; 与桌面版有已知差异)。")


def render_ppt_slides_auto(pptx_path, out_dir, width_px=1600):
    """用微软的引擎渲染全部 slide, 返回 (count, engine_name)。

    排版引擎由 ``RENDER_ENGINE`` 决定: 默认桌面版 PowerPoint (Windows COM / macOS 原生),
    或**显式**指定 ``graph`` 走 Microsoft Graph 的在线渲染。**不自动切换**:
    选定的引擎拿不到就返回 ``(0, "none")``, 不会改用会重排的第三方引擎。
    (但把产出的固定版式栅格化那一步可换工具, 见 ``_RASTERIZERS``。)
    """
    os.makedirs(out_dir, exist_ok=True)
    try:
        engines = _build_engine_list()
    except Exception as e:
        print("  [render] %s" % str(e), flush=True)
        print("  [render] 提示: 版式只由微软引擎产出(powerpoint / graph); 不会改用其它引擎",
              flush=True)
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
            elif kind == "graph":
                print("  [render] 引擎=%s — 注意: **在线渲染**, 与桌面版有已知差异"
                      % name, flush=True)
                n = render_via_graph(pptx_path, out_dir)
                if n > 0:
                    return n, name
            else:
                # 排版引擎已被禁用, 正常不会到达
                print("  [render] 未知引擎类型 %r —— 其它排版引擎已按规范删除" % kind, flush=True)
        except Exception as e:
            # 消息截断到 160; **可操作建议单独成行**打印 —— 拼在消息里会被截断切掉。
            tail = "" if is_last else " (尝试下一引擎)"
            print("  [render] %s 失败: %s%s" % (name, str(e)[:160], tail), flush=True)
            hint = getattr(e, "hint", "")
            if hint:
                print("  [render] 处理建议: %s" % hint, flush=True)
    print("  [render] PowerPoint 渲染失败, 返回 0 张幻灯片 (按规范不换排版引擎)", flush=True)
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
