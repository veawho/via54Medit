#!/usr/bin/env python3
"""render_doctor.py — 渲染通道就绪自检: 回答"这台机器现在到底能不能出图"

为什么需要它
------------
"通道通"不等于"能出图"。本机实测:

  * PowerPoint / Word 的 ``launch`` + ``get version`` 都是**秒回**(0.004s);
  * 但真正 ``open`` 文档时会**一直挂住** —— 模态对话框挡住了 AppleEvent, 或自动化权限没放行。

所以只看预检会给出**假 OK**: 一条跑 30 分钟的管线直到渲染那一步才炸。
本脚本默认做**真出图探针** —— 现场生成一份最小文档, 用**生产函数**真的渲染一遍, 数产出的图片。
这样得到的结论才是"能出图", 而不是"看起来像能出图"。

判定与退出码
------------
  * **必须就绪** → PPT 排版通道(按 ``RENDER_ENGINE`` 选定的那个) + 栅格化器。任一不就绪 -> 退出码 1。
  * **按需就绪** → Word 通道。只有源文件是 DOC/DOCX 时才需要, 不就绪只提示、不判失败。
  * **可选** → Microsoft Graph 通道(需凭据)。

用法
----
    python3 scripts/render_doctor.py          # 真出图探针(默认; 较慢但结论可靠)
    python3 scripts/render_doctor.py --quick   # 只查依赖/凭据, 不出图(快, 但可能假 OK)

探针会用较短的超时(可在环境变量里覆盖 PPT_RENDER_TIMEOUT / WORD_RENDER_TIMEOUT),
因为一份最小文档本来只要几秒; 卡住就是卡住, 不必等满默认的 60 秒。
"""
import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_OK = "✓"
_NO = "✗"
_SKIP = "•"


def _make_canary_pptx(path):
    """造一份最小 PPTX(单页 + 一个文本框)当探针。"""
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    box.text_frame.text = "render doctor canary"
    prs.save(path)
    return path


def _make_canary_docx(path):
    """造一份最小 DOCX 当探针。**不依赖 python-docx**(本仓库没有这个依赖)。"""
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document %s><w:body><w:p><w:r><w:t>render doctor canary</w:t></w:r>'
            '</w:p></w:body></w:document>' % ns)
    return path


def check_rasterizer():
    """栅格化器: 只把已排好的固定版式转成图片, 不重排 —— 这一环可以换工具。"""
    pref = os.environ.get("RENDER_RASTERIZER", "pymupdf").strip().lower()
    if pref in ("pymupdf", "fitz"):
        try:
            import pymupdf  # noqa: F401
            return True, "pymupdf(默认), 只光栅化不重排", ""
        except ImportError:
            return False, "RENDER_RASTERIZER=pymupdf 但 pymupdf 导不进来", \
                "pip install 'pymupdf>=1.24'"
    if pref == "pdftoppm":
        found = shutil.which("pdftoppm")
        return (bool(found), found or "PATH 里找不到 pdftoppm",
                "brew install poppler  (会强制带 -cropbox, 保证与 CropBox 一致)")
    return False, "未知 RENDER_RASTERIZER=%r" % pref, "只支持 pymupdf / pdftoppm"


def check_ppt_channel(canary_pptx, quick):
    """PPT 排版通道 —— 按 RENDER_ENGINE 选定的那**一个**, 不做自动降级。"""
    import ppt_render_engine as pre
    pref = pre._engine_pref()

    if pref == "graph":
        try:
            err = pre._graph_module().credentials_error()
        except Exception as e:                      # noqa: BLE001
            return False, "Graph 客户端加载失败: %s" % e, ""
        if err:
            return False, "Microsoft Graph 凭据不全", err
        if quick:
            return True, "凭据已配置(**未验证连通**)", "去掉 --quick 再跑一次可验证真实转换"

    try:
        engines = pre._build_engine_list()
    except RuntimeError as e:
        return False, "选定引擎(RENDER_ENGINE=%s)不可用" % pref, str(e)

    names = ", ".join(n for n, _, _ in engines)
    if quick:
        return True, "探测到 %s(**未出图验证, 可能假 OK**)" % names, \
            "去掉 --quick 可做真出图探针"

    out_dir = tempfile.mkdtemp(prefix="doctor_ppt_")
    print("   (正在真出一张图, 最长等 PPT_RENDER_TIMEOUT 秒 ...)", flush=True)
    count, engine = pre.render_ppt_slides_auto(canary_pptx, out_dir)
    if count > 0:
        return True, "%s 实出 %d 张图" % (engine, count), ""
    return False, "%s 一张都没出" % (engine or "none"), (
        "多为 open 被模态对话框挡住 / 自动化权限未放行。"
        "可人工打开一次应用关掉对话框, 并在 系统设置 › 隐私与安全性 › 自动化 里放行; "
        "或显式改用 RENDER_ENGINE=graph(需凭据)。")


def check_word_channel(canary_docx, quick):
    """Word 通道 —— 只在源文件是 DOC/DOCX 时才需要, 故不就绪不判失败。"""
    if quick:
        return None, "未检查(--quick)", ""
    import unified_render_engine as ure
    if not (os.name == "nt" or sys.platform == "darwin"):
        return False, "本平台没有 Microsoft Word 通道", \
            "在 Windows/macOS 上渲染, 或先用 Word 另存为 PDF 再传入"
    out_dir = tempfile.mkdtemp(prefix="doctor_docx_")
    print("   (正在真出一张图, 最长等 WORD_RENDER_TIMEOUT 秒 ...)", flush=True)
    imgs = ure.render_docx_to_images(canary_docx, out_dir)
    if imgs:
        return True, "Microsoft Word 实出 %d 张图" % len(imgs), ""
    return False, "Microsoft Word 一张都没出", (
        "同 PowerPoint: 多半是 open 被模态对话框挡住或自动化权限未放行。")


def _print_row(label, state, detail, fix):
    mark = _OK if state else (_SKIP if state is None else _NO)
    print("  %s %-14s %s" % (mark, label, detail))
    if state is False and fix:
        for line in fix.splitlines():
            if line.strip():
                print("      → %s" % line.strip())


def main(argv):
    quick = "--quick" in argv
    # 探针只需要几秒; 给个上界, 免得坏掉的通道把 doctor 本身拖死。用户显式设过就尊重。
    os.environ.setdefault("PPT_RENDER_TIMEOUT", "25")
    os.environ.setdefault("PPT_RENDER_PREFLIGHT_TIMEOUT", "8")
    os.environ.setdefault("WORD_RENDER_TIMEOUT", "25")
    os.environ.setdefault("WORD_RENDER_PREFLIGHT_TIMEOUT", "8")

    print("渲染通道就绪自检 %s" % ("(--quick: 只查依赖, 不出图)" if quick else "(真出图探针)"))
    print("=" * 66)

    tmp = tempfile.mkdtemp(prefix="doctor_")
    canary_pptx = None
    canary_docx = None
    try:
        if not quick:
            try:
                canary_pptx = _make_canary_pptx(os.path.join(tmp, "canary.pptx"))
                canary_docx = _make_canary_docx(os.path.join(tmp, "canary.docx"))
            except Exception as e:                  # noqa: BLE001
                print("  %s 造探针文档失败: %s" % (_NO, e))
                return 2

        results = {}
        try:
            results["PPT 排版通道"] = check_ppt_channel(canary_pptx, quick)
        except Exception as e:                      # noqa: BLE001
            results["PPT 排版通道"] = (False, "检查过程异常: %s" % e, "")
        results["栅格化器"] = check_rasterizer()
        try:
            results["Word 通道(按需)"] = check_word_channel(canary_docx, quick)
        except Exception as e:                      # noqa: BLE001
            results["Word 通道(按需)"] = (False, "检查过程异常: %s" % e, "")

        for label, (state, detail, fix) in results.items():
            _print_row(label, state, detail, fix)

        print("-" * 66)
        blockers = [k for k in ("PPT 排版通道", "栅格化器")
                    if results[k][0] is False]
        if blockers:
            print("%s 不可用: %s —— 现在跑管线一定在渲染这步失败, 先解决它。"
                  % (_NO, "、".join(blockers)))
            return 1
        if quick:
            # 这里**不能**说"就绪": --quick 只查了依赖, 而本机实测"探测得到"却"一张也出不来"。
            print("%s 依赖看起来齐全 —— 但**没做真出图探针**, 不能据此认为能渲染。" % _SKIP)
            print("     本机实测过: 预检秒回, 真正 open 却会挂住。要可靠结论请去掉 --quick。")
            return 0
        if results["Word 通道(按需)"][0] is False:
            print("%s PPT 这一侧就绪;**Word 那一侧不可用** —— 只在源文件是 DOC/DOCX 时才会卡住。"
                  % _SKIP)
            return 0
        print("%s 就绪。注意保真规则: 排版只由微软引擎产出, 不会自动切换到会重排的引擎。"
              % _OK)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
