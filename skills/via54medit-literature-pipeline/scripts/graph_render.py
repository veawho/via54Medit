#!/usr/bin/env python3
"""graph_render.py — 用 Microsoft Graph 把 PPTX 转成**固定版式 PDF** (Office 在线渲染)

为什么这个模块存在
------------------
`docs/ppt-render-fidelity.md` 的判定标准是: **版式与文字必须由微软的引擎产出**。
桌面版 PowerPoint 是首选。Microsoft Graph 的 `?format=` 转换由**微软服务端(Office 在线)**
完成, 属于同一家的另一个引擎, 因此可以在**显式选择**的前提下使用::

    RENDER_ENGINE=graph

它不是自动降级目标 —— 桌面 PowerPoint 拿不到时**不会**偷偷切到这里(那正是规范禁止的
"静默换引擎")。且它与桌面版有**已知差异**(Office 在线的功能行为), 见下面「保真度说明」。

为什么只做 PDF, 不做 jpg
-------------------------
官方文档里 `format=jpg` 对 pptx **只返回第一张幻灯片**(社区实测; 官方 API 页未明确说明),
整份演示文稿走 jpg 那条路走不通; `format=pdf` 才是整份。
所以本模块只负责 "PPTX → PDF", 之后由 ``ppt_render_engine`` 用本地栅格化器出逐页图片 ——
PDF 是固定版式, 栅格化那一步不重排。

保真度说明 (与桌面版 PowerPoint 的已知差异)
--------------------------------------------
Graph 走的是 Office 在线渲染引擎, **不是**桌面版。微软官方文档记录的 Web 端行为差异包括:
符号在所需字体不可用时显示为占位符; WordArt / 图表在 Web 端不能插入(能显示);
在线导出 PDF 时字体可能被替换、出现字距/字重差异。
因此: 桌面 PowerPoint 可用时**优先用它**; Graph 适合"没有桌面 PowerPoint 的环境"
(如 Linux/CI), 或本机 PowerPoint 自动化故障时作为**显式**替代。

凭据 (任选其一)
---------------
* ``GRAPH_ACCESS_TOKEN`` —— 现成令牌, 委派或应用均可(例如 `az account get-access-token`)
* ``GRAPH_TENANT_ID`` + ``GRAPH_CLIENT_ID`` + ``GRAPH_CLIENT_SECRET`` —— 客户端凭据(app-only)

其它环境变量:
* ``GRAPH_DRIVE_ID`` —— 上传目标驱动器。未给且用委派令牌时自动取 ``GET /me/drive``
* ``GRAPH_UPLOAD_ROOT`` —— 上传到哪个目录, 默认 ``_via54medit_render_tmp``
* ``GRAPH_TIMEOUT`` —— 单次 HTTP 超时(秒), 默认 120
* ``GRAPH_KEEP_UPLOAD=1`` —— 转换后不删掉上传的临时文件(默认会删)

自检
----
    python3 graph_render.py --check     # 验证凭据 / 取 token / drive 是否可达

用法
----
    python3 graph_render.py <in.pptx> <out.pdf>
    from graph_render import export_ppt_to_pdf_via_graph
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

_GRAPH = "https://graph.microsoft.com/v1.0"
_LOGIN = "https://login.microsoftonline.com"
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_ROOT = "_via54medit_render_tmp"
#: 官方: ``PUT .../content`` 单次调用上限 250 MB; 超过必须用 upload session。
_MAX_SIMPLE_UPLOAD = 250 * 1024 * 1024

_SETUP_HINT = (
    "需要下面任一种凭据:\n"
    "  (a) GRAPH_ACCESS_TOKEN = 现成令牌(委派或应用均可); 或\n"
    "  (b) GRAPH_TENANT_ID + GRAPH_CLIENT_ID + GRAPH_CLIENT_SECRET = 客户端凭据(app-only)。\n"
    "  走 (b) 时需在 Microsoft Entra 注册应用、授予**应用权限** Files.ReadWrite.All 并让管理员同意;\n"
    "  个人版 OneDrive 不支持 app-only, 那种情况请用 (a) 的委派令牌。\n"
    "转换只对**已在 OneDrive/SharePoint 里**的文件生效, 所以还需要 GRAPH_DRIVE_ID ——\n"
    "给了委派令牌时可以留空, 会自动取 GET /me/drive。\n"
    "配好后先跑 `python3 graph_render.py --check` 自检。详见 docs/ppt-render-fidelity.md。"
)


class GraphRenderError(RuntimeError):
    """Graph 通道失败。``hint`` 是可操作建议, 由调用方**单独成行**打印(避免被截断)。"""

    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


class _HttpError(Exception):
    """内部用: 带状态码/重试提示的 HTTP 错误。"""

    def __init__(self, status, retry_after=None, body=""):
        super().__init__("HTTP %s" % status)
        self.status = status
        self.retry_after = retry_after
        self.body = body


# ---------------------------------------------------------------- 环境变量

def _env(name, default=""):
    return os.environ.get(name, default).strip()


def _timeout():
    try:
        val = float(_env("GRAPH_TIMEOUT") or _DEFAULT_TIMEOUT)
    except ValueError:
        val = _DEFAULT_TIMEOUT
    return val if val > 0 else _DEFAULT_TIMEOUT


def _has_credentials():
    if _env("GRAPH_ACCESS_TOKEN"):
        return True
    return all(_env(n) for n in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET"))


def credentials_error():
    """凭据是否就绪。就绪返回空串, 否则返回一段可直接打印的可操作说明。"""
    if _has_credentials():
        return ""
    return "未配置 Microsoft Graph 凭据。\n" + _SETUP_HINT


# ---------------------------------------------------------------- HTTP 接缝

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """**不自动跟随 3xx** —— 官方要求由应用自己跟随 ``Location``(预认证 URL 不能带 Authorization)。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(method, url, data=None, headers=None, timeout=None):
    """单次请求, 返回 ``(status, headers_dict, body_bytes)``; 3xx 也当正常响应返回。"""
    req = urllib.request.Request(url, data=data, method=method)
    for key, val in (headers or {}).items():
        req.add_header(key, val)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout or _timeout()) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        if 300 <= e.code < 400:
            return e.code, dict(e.headers or {}), body
        retry_after = None
        try:
            retry_after = float((e.headers or {}).get("Retry-After"))
        except (TypeError, ValueError):
            pass
        raise _HttpError(e.code, retry_after, body[:400].decode("utf-8", "replace")) from None
    except urllib.error.URLError as e:
        raise _HttpError(0, None, str(e.reason)) from None


def _request(method, url, data=None, headers=None, timeout=None, retries=3):
    """``_open`` + 节流重试(429/503, 尊重 Retry-After)。**测试全部打在这个接缝上。**"""
    attempt = 0
    while True:
        attempt += 1
        try:
            return _open(method, url, data=data, headers=headers, timeout=timeout)
        except _HttpError as e:
            if e.status in (429, 503) and attempt <= retries:
                delay = e.retry_after if e.retry_after else min(2 ** attempt, 30)
                print("  [graph] HTTP %s 被节流, %.0fs 后重试(第 %d 次)" % (e.status, delay, attempt),
                      flush=True)
                time.sleep(delay)
                continue
            raise


def _bearer(token, content_type=None):
    head = {"Authorization": "Bearer %s" % token}
    if content_type:
        head["Content-Type"] = content_type
    return head


def _json_or_error(raw, what):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise GraphRenderError("%s: 返回不是合法 JSON: %s" % (what, raw[:200])) from None


# ---------------------------------------------------------------- 各步

def acquire_token():
    """取访问令牌: 优先 ``GRAPH_ACCESS_TOKEN``, 否则走客户端凭据流。"""
    tok = _env("GRAPH_ACCESS_TOKEN")
    if tok:
        return tok

    url = "%s/%s/oauth2/v2.0/token" % (_LOGIN, _env("GRAPH_TENANT_ID"))
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": _env("GRAPH_CLIENT_ID"),
        "client_secret": _env("GRAPH_CLIENT_SECRET"),
        "scope": "https://graph.microsoft.com/.default",
    }).encode("utf-8")
    try:
        status, _, raw = _request("POST", url, data=body,
                                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    except _HttpError as e:
        raise GraphRenderError("取令牌失败: HTTP %s %s" % (e.status, e.body),
                               _SETUP_HINT) from None
    if status != 200:
        raise GraphRenderError("取令牌失败: HTTP %s %s" % (status, raw[:200]), _SETUP_HINT)
    payload = _json_or_error(raw, "取令牌")
    token = payload.get("access_token")
    if not token:
        raise GraphRenderError("取令牌响应里没有 access_token: %s" % str(payload)[:200], _SETUP_HINT)
    return token


def resolve_drive_id(token):
    """上传目标驱动器 id: 有 ``GRAPH_DRIVE_ID`` 就用; 否则用委派令牌取 ``/me/drive``。"""
    drive = _env("GRAPH_DRIVE_ID")
    if drive:
        return drive
    try:
        status, _, raw = _request("GET", _GRAPH + "/me/drive", headers=_bearer(token))
    except _HttpError as e:
        raise GraphRenderError("解析 drive 失败(GET /me/drive): HTTP %s %s" % (e.status, e.body),
                               _SETUP_HINT) from None
    if status != 200:
        raise GraphRenderError("解析 drive 失败(GET /me/drive): HTTP %s" % status,
                               "若用的是 app-only 令牌, 请显式设置 GRAPH_DRIVE_ID —— "
                               "app-only 没有 /me。")
    return _json_or_error(raw, "GET /me/drive").get("id", "")


def upload_item(token, drive_id, local_path):
    """把本地文件传到 ``GRAPH_UPLOAD_ROOT`` 下, 返回 driveItem id。"""
    root = _env("GRAPH_UPLOAD_ROOT") or _DEFAULT_ROOT
    name = os.path.basename(local_path)
    path = "/".join(urllib.parse.quote(seg, safe="") for seg in (root, name) if seg)
    url = "%s/drives/%s/items/root:/%s:/content" % (_GRAPH, drive_id, path)
    with open(local_path, "rb") as fh:
        blob = fh.read()
    if len(blob) > _MAX_SIMPLE_UPLOAD:
        raise GraphRenderError(
            "文件 %.1f MB 超过单次上传上限 250 MB, 需要 upload session(本模块未实现)。"
            % (len(blob) / 1024.0 / 1024.0),
            "请先在本地把 PPT 拆小, 或直接用桌面版 PowerPoint 渲染。")
    try:
        status, _, raw = _request("PUT", url, data=blob,
                                  headers=_bearer(token, "application/octet-stream"),
                                  timeout=max(_timeout(), 300))
    except _HttpError as e:
        raise GraphRenderError("上传失败: HTTP %s %s" % (e.status, e.body), _SETUP_HINT) from None
    if status not in (200, 201):
        raise GraphRenderError("上传失败: HTTP %s %s" % (status, raw[:200]), _SETUP_HINT)
    item = _json_or_error(raw, "上传").get("id", "")
    if not item:
        raise GraphRenderError("上传响应里没有 id: %s" % raw[:200])
    return item


def download_as_pdf(token, drive_id, item_id, dest_pdf):
    """``?format=pdf`` 转换 + 跟随 302 到预认证 URL 下载整份 PDF。"""
    url = "%s/drives/%s/items/%s/content?format=pdf" % (_GRAPH, drive_id, item_id)
    try:
        status, headers, raw = _request("GET", url, headers=_bearer(token))
    except _HttpError as e:
        raise GraphRenderError("转换请求失败: HTTP %s %s" % (e.status, e.body),
                               "若返回 403, 多为权限不足(应用权限需 Files.ReadWrite.All 且管理员同意)。"
                               ) from None
    if status not in (301, 302, 303, 307, 308):
        raise GraphRenderError("预期 302 重定向, 实际 HTTP %s: %s" % (status, raw[:200]))

    location = headers.get("Location") or headers.get("location") or ""
    if not location:
        raise GraphRenderError("302 响应里没有 Location 头")
    # 预认证 URL 只几分钟有效, 且**不要**带 Authorization(带了反而可能被拒)
    status, _, blob = _request("GET", location, headers={}, timeout=max(_timeout(), 300))
    if status != 200:
        raise GraphRenderError("下载转换结果失败: HTTP %s" % status)
    if not blob[:4] == b"%PDF":
        raise GraphRenderError("转换结果不是 PDF(前 4 字节=%r)" % blob[:4])

    parent = os.path.dirname(os.path.abspath(dest_pdf))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(dest_pdf, "wb") as fh:
        fh.write(blob)
    return os.path.abspath(dest_pdf)


def delete_item(token, drive_id, item_id):
    """删掉上传的临时文件。失败不抛(留日志), 免得盖住真正的渲染结果。"""
    try:
        _request("DELETE", "%s/drives/%s/items/%s" % (_GRAPH, drive_id, item_id),
                 headers=_bearer(token))
        return True
    except Exception as e:
        print("  [graph] 清理临时文件失败(不影响结果): %s" % e, flush=True)
        return False


def export_ppt_to_pdf_via_graph(pptx_path, pdf_path):
    """PPTX →(上传 → ``?format=pdf`` 转换 → 下载)→ 固定版式 PDF。

    版式由**微软服务端引擎**产出; 拿不到就抛 ``GraphRenderError``, **不退回别的排版引擎**。
    """
    err = credentials_error()
    if err:
        raise GraphRenderError("Microsoft Graph 凭据缺失。", err)

    abs_pptx = os.path.abspath(pptx_path)
    if not os.path.isfile(abs_pptx):
        raise GraphRenderError("源文件不存在: %s" % abs_pptx)

    token = acquire_token()
    drive_id = resolve_drive_id(token)

    item_id = ""
    try:
        item_id = upload_item(token, drive_id, abs_pptx)
        print("  [graph] 已上传, 正在用 Office 在线渲染转 PDF ...", flush=True)
        return download_as_pdf(token, drive_id, item_id, pdf_path)
    finally:
        if item_id and not _env("GRAPH_KEEP_UPLOAD"):
            delete_item(token, drive_id, item_id)


# ---------------------------------------------------------------- CLI

def _check():
    """自检: 凭据 / 取令牌 / drive 可达。返回进程退出码。"""
    err = credentials_error()
    if err:
        print("✗ %s" % err, flush=True)
        return 1
    mode = "GRAPH_ACCESS_TOKEN" if _env("GRAPH_ACCESS_TOKEN") else "客户端凭据(app-only)"
    print("✓ 凭据形态: %s" % mode, flush=True)
    try:
        token = acquire_token()
        print("✓ 取令牌成功 (长度 %d)" % len(token), flush=True)
        drive = resolve_drive_id(token)
        print("✓ drive 可达: %s" % drive, flush=True)
        root = _env("GRAPH_UPLOAD_ROOT") or _DEFAULT_ROOT
        print("  上传目录: %s/  (GRAPH_KEEP_UPLOAD=%s)"
              % (root, _env("GRAPH_KEEP_UPLOAD") or "0"), flush=True)
    except GraphRenderError as e:
        print("✗ %s" % e, flush=True)
        if e.hint:
            print(e.hint, flush=True)
        return 1
    print("✓ Graph 通道可用。提示: 它走 Office 在线渲染, 与桌面版 PowerPoint 有已知差异 —— "
          "桌面版可用时优先用它。", flush=True)
    return 0


if __name__ == "__main__":
    import sys
    # Windows 上把输出重定向到文件/管道时默认按 cp936 编码, 本模块打的中文与 ✓ ✗ 有相当
    # 一部分不在 GBK 里, 会直接 UnicodeEncodeError —— 统一改成 utf-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                       # noqa: BLE001
        pass
    if len(sys.argv) >= 2 and sys.argv[1] == "--check":
        sys.exit(_check())
    if len(sys.argv) < 3:
        print("usage: graph_render.py <in.pptx> <out.pdf>  |  graph_render.py --check")
        sys.exit(1)
    try:
        print(export_ppt_to_pdf_via_graph(sys.argv[1], sys.argv[2]))
    except GraphRenderError as e:
        print("导出失败: %s" % e, file=sys.stderr)
        if e.hint:
            print("处理建议: %s" % e.hint, file=sys.stderr)
        sys.exit(1)
