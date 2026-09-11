"""接入的 LLM 有哪些、能不能真的读到它们的 token 消耗 —— 一份**可执行**的清单。

为什么需要它
------------
"接入了哪几个 LLM"这个问题, 光看文档或配置都答不出来 —— 它由**代码里的调用路径**决定。
注册表里可以写十个 provider, 但只有真正被 ``record_llm_usage`` 覆盖到的那几个, token 消耗
才进得了库。实测就抓到过这个缺口: ``provider_llm.py``(默认文本 provider) 把 ``usage``
返回给调用方, 却**没有任何地方把它写进库** —— 也就是 DeepSeek 的 token 消耗一直是 0,
而报表还标着"100% 控制台对齐"。

本模块做四件事:

1. **发现**: 哪个 provider 有代码(integrated)、哪个配了凭据(configured)、当前选中哪个(active);
2. **验证**: 凭据能不能通过服务端鉴权(``--live`` 才走网络; 不花钱的探针优先);
3. **证明能读到用量**: 把每个 provider 的**真实响应形状**喂进 ``record_llm_usage``, 再读回来 ——
   全程离线、只写临时库, **不碰生产数据**;
4. **证明 Go 侧链路通**: Go 没有 SQLite 驱动, 用量先落 spool 再由 ``llm_spool`` 摄入,
   这条链路断了不会报任何错, 所以单独验一遍(含别名归一与重放幂等)。

这套校验在**部署与更新后强制跑**: ``medit-telemetry llm`` /
``deploy_scan.py --verify-llm`` / ``bootstrap_device.py`` 第 4 步 /
``auto_sync.py`` 拉取后 / ``medit-telemetry deploy`` 概览 —— 失败一律非零退出。

两种用量口径, 不能混为一谈
--------------------------
* **单次调用用量**: 响应体里的 ``usage`` 字段(prompt/completion/total)。deepseek / openai /
  minimax / sensenova / zhipu 都走这条。
* **账户级用量**: 服务商侧的配额/账单。目前**唯一可程序化读取**的是 mmx-cli ——
  ``mmx quota show --output json`` 返回按模型的配额与已用**次数**(已实测)。注意它是**次数**
  而不是 token, 所以**不会**被折成 token 写进库: 混进去就是造数。

诚实说明读不到的部分
--------------------
* **mmx / MiniMax VLM 的单次 token 读不到**: ``mmx vision describe --output json`` 只返回
  content, CLI 不暴露 token。它的用量只能取到账户级配额。
* **openai 的用量接口需要 Admin key**: organization usage/costs 接口要 ``sk-admin-`` 开头且带
  ``api.usage.read`` 作用域的密钥, 普通 api key 读不到。
* **deepseek 有余额接口没有 token 用量接口**: ``GET /user/balance`` 能查余额; 按 key 的逐条用量
  要走控制台「用量信息」导出 CSV。
* **minimax / sensenova / zhipu 未发现公开用量接口**: 逐次用量只能靠我们自己在调用时记录,
  账户级对账仍需控制台。
"""

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

#: 探针的网络超时(秒)。凭据探测只做一次握手, 不该拖住部署流程。
PROBE_TIMEOUT = 12

#: 单次用量来源的取值
USAGE_RESPONSE = "response"      # 响应体 usage 字段
USAGE_NONE = "none"              # 该通道拿不到 token

#: Go 侧用量 spool 的落盘路径(与 ``internal/foundation/llm_usage.go`` 同名同语义)
SPOOL_ENV = "VIA54_LLM_USAGE_SPOOL"

#: 服务商别名 → 落库时的 provider 名。
#:
#: 这是**唯一权威**: Go 侧管子叫 "glm", Python 侧叫 "zhipu"; 同一次调用如果两边
#: 各写各的, 报表里就会凭空多出一家供应商。摄入 spool 时必须先过这张表。
PROVIDER_ALIASES = {
    "deepseek": "deepseek",
    "deepseek-r1": "deepseek",
    "deepseek-v3": "deepseek",
    "openai": "openai",
    "codex": "openai",
    "glm": "zhipu",
    "zhipu": "zhipu",
    "bigmodel": "zhipu",
    "minimax": "minimax",
    "mmx": "minimax",
    "sensenova": "sensenova",
    "hermes": "hermes",
}


@dataclass(frozen=True)
class Channel:
    """一个 provider 的一条接入通道(同一份账单可能有多种调法)。"""

    name: str
    module: str                  # 实现文件(相对仓库根)
    env_key: str = ""            # 凭据环境变量
    credential_file: str = ""    # 或本地凭据文件
    usage: str = USAGE_RESPONSE  # 单次用量来源
    note: str = ""


@dataclass(frozen=True)
class Provider:
    key: str                     # 落库时的 provider 值
    label: str
    kind: str                    # text / vision / text+vision
    channels: Tuple[Channel, ...] = ()
    #: 选择该 provider 的环境变量(如 LLM_PROVIDER / VISION_PROVIDER)
    selected_by: str = ""
    default_selected: bool = False
    #: 账户级用量怎么读(说明性文字; 能程序化读的在 account_probe 里)
    account_usage: str = ""
    account_probe: str = ""      # "" | "mmx_quota" | "http_balance" | "http_models_admin"
    probe_endpoint: str = ""     # http 探针地址
    note: str = ""
    # 注意: 这里**没有**"记录者清单"字段。谁在记用量必须由 scan_callers() 从源码里查出来,
    # 而不是在这里声明 —— 声明和事实一旦不一致, 缺的正是最该被发现的缺口。


PROVIDERS: Tuple[Provider, ...] = (
    Provider(
        key="deepseek",
        label="DeepSeek (V3 / R1)",
        kind="text",
        channels=(
            Channel(name="文本 API", module="scripts/provider_llm.py",
                    env_key="DEEPSEEK_API_KEY"),
            Channel(name="Go 端", module="internal/foundation/llm.go",
                    env_key="DEEPSEEK_API_KEY",
                    note="medit ask / medplan / docproc 走 spool 落盘再摄入"),
        ),
        selected_by="LLM_PROVIDER", default_selected=True,
        account_usage="余额可查(GET /user/balance); 按 key 的 token 用量需控制台导出 CSV",
        account_probe="http_balance",
        probe_endpoint="https://api.deepseek.com/user/balance",
        note="LLM_PROVIDER 的默认值",
    ),
    Provider(
        key="openai",
        label="OpenAI / Codex",
        kind="text",
        channels=(
            Channel(name="文本 API", module="scripts/provider_llm.py",
                    env_key="OPENAI_API_KEY"),
            Channel(name="Go 端", module="internal/foundation/llm.go",
                    env_key="OPENAI_API_KEY"),
        ),
        selected_by="LLM_PROVIDER",
        account_usage="用量/成本接口需 Admin key (sk-admin-, api.usage.read); 普通 key 读不到",
        probe_endpoint="https://api.openai.com/v1/models",
        note="",
    ),
    Provider(
        key="minimax",
        label="MiniMax (M3 / VLM / mmx-cli)",
        kind="text+vision",
        channels=(
            Channel(name="文本 API", module="scripts/provider_llm.py",
                    env_key="MINIMAX_API_KEY"),
            Channel(name="M3 视觉", module="scripts/hl_v3_final/vision_check.py",
                    env_key="M3_API_KEY"),
            Channel(name="mmx-cli VLM", module="scripts/mmx_vision.py",
                    credential_file="~/.mmx/config.json", usage=USAGE_NONE,
                    note="CLI 只返回 content, 不暴露 token"),
        ),
        account_usage="mmx-cli 可程序化读取: `mmx quota show` 给出按模型配额与已用次数",
        account_probe="mmx_quota",
        note="账户级用量可读(次数), 单次 token 读不到",
    ),
    Provider(
        key="zhipu",
        label="智谱 GLM (GLM-4V / glm-4.6v-flash)",
        kind="vision",
        channels=(
            Channel(name="视觉 API", module="scripts/glm_vision.py",
                    env_key="GLM_API_KEY"),
            Channel(name="Go 端", module="internal/foundation/llm_glm.go",
                    env_key="GLM_API_KEY",
                    note="Go 侧注册名是 glm, 落库统一归一为 zhipu"),
        ),
        account_usage="未发现公开用量接口; 逐次用量靠调用时记录",
        note="",
    ),
    Provider(
        key="sensenova",
        label="商汤 SenseNova (V6.5 / 6.7-flash-lite)",
        kind="text+vision",
        channels=(
            Channel(name="视觉 API", module="scripts/sensenova_vision.py",
                    env_key="SENSENOVA_API_KEY"),
            Channel(name="文本 API", module="scripts/provider_llm.py",
                    env_key="SENSENOVA_API_KEY"),
        ),
        account_usage="未发现公开用量接口; 逐次用量靠调用时记录",
        note="",
    ),
    Provider(
        key="hermes",
        label="Hermes 本地网关",
        kind="text",
        channels=(
            Channel(name="本地网关", module="scripts/provider_llm.py",
                    env_key="HERMES_API_KEY"),
            Channel(name="Go 端", module="internal/foundation/llm.go",
                    env_key="HERMES_API_KEY"),
        ),
        selected_by="LLM_PROVIDER",
        account_usage="本地网关, 计费取决于其背后的模型",
        note="默认模型 MiniMax-M3",
    ),
)

#: 视觉通道的默认 provider (VISION_PROVIDER 的默认值)
VISION_DEFAULT = "mmx"
#: mmx-cli 的 provider 归口到这个账单身份
_MMX_ACCOUNT_PROVIDER = "minimax"


# --------------------------------------------------------------------------- #
# 定位实现文件
# --------------------------------------------------------------------------- #
def repo_root() -> str:
    """仓库根目录(本文件在 ``telemetry/`` 下, 上一层就是根)。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_module(rel: str) -> str:
    """找到实现文件的路径; 找不到返回空串。

    只在**仓库内运行**时才算"有代码"。装在 site-packages 里跑时这些 ``scripts/*.py``
    未必存在 —— 那就如实报"未找到", 而不是假装接入了。
    """
    for base in (repo_root(), os.getcwd()):
        cand = os.path.join(base, rel)
        if os.path.exists(cand):
            return cand
    return ""


def _which(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for cand in (os.path.expanduser("~/.local/bin/" + name),
                 os.path.expanduser("~/.hermes/node/bin/" + name),
                 os.path.expanduser("~/.npm-global/bin/" + name)):
        if os.path.exists(cand):
            return cand
    return ""


# --------------------------------------------------------------------------- #
# 证据: 谁真的在记用量
#
# 这里刻意**不信任任何声明**(注册表说自己被记录不算数), 而是扫源码找真实的
# 调用点: Python 侧是 ``record_llm_usage(...)``, Go 侧是 ``recordLLMUsage(...)``,
# 并把调用点里写的 provider 名取出来。
# 这样"接入了哪些 LLM"就有代码级证据, 而不是一张愿望清单 —— 实测的缺口
# (provider_llm.py 返回 usage 却从不记录, Go 侧整个丢弃 usage) 都是被这个检查抓出来的。
# --------------------------------------------------------------------------- #
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
              "dist", "build", ".idea", ".vscode", "tests"}


def scan_callers(root: str = "") -> Dict[str, List[str]]:
    """``scan_recorders`` 的 Python 侧视图: ``{provider: [文件]}``。

    取不到 ``provider=`` 字面量时记到 ``"(动态)"`` 键下 —— 动态传参没法静态判断,
    如实单独列出而不是猜。
    """
    return scan_recorders(root)["py"]["by_provider"]


#: Go 侧的记账入口(``internal/foundation/llm_usage.go``)。Go 没有 SQLite 驱动,
#: 走 spool 落盘, 所以证据是另一个函数名 —— 但"必须能在源码里找到调用点"这条不变。
GO_CALL_RE_SRC = r"recordLLMUsage\s*\((.*?)\)"
#: Go 端在构造时声明这笔账记到哪个 provider 名下
GO_USAGE_NAME_RE_SRC = r"usageName:\s*\"([A-Za-z0-9_\-]+)\""


def scan_recorders(root: str = "") -> Dict[str, Any]:
    """扫全仓库, 分别给出 Python 与 Go 两侧的**记账证据**。

    返回 ``{"py": {"by_provider": {...}, "files": [...]},
             "go": {"by_provider": {...}, "files": [...]}}``。

    Go 侧的 provider 名有两处来源: 调用点第一个参数的字符串字面量(如 ``"zhipu"``),
    以及构造时的 ``usageName: "deepseek"``。两处都收, 因为
    ``recordLLMUsage(h.usageProvider(), ...)`` 这种写法静态看不出 provider。
    """
    import re

    root = root or repo_root()
    call_re = re.compile(r"record_llm_usage\s*\((.*?)\)", re.S)
    go_call_re = re.compile(GO_CALL_RE_SRC, re.S)
    go_name_re = re.compile(GO_USAGE_NAME_RE_SRC)

    py: Dict[str, List[str]] = {}
    go: Dict[str, List[str]] = {}
    unreachable: List[Any] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS
                       and not d.startswith(".") and not d.startswith("_bak")]
        for fn in filenames:
            is_py = fn.endswith(".py")
            is_go = fn.endswith(".go") and not fn.endswith("_test.go")
            if not (is_py or is_go):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
            except OSError:
                continue

            if is_py:
                if "record_llm_usage" not in src:
                    continue
                # 定义处(telemetry/token_tracker.py)不是调用点
                if rel.endswith("telemetry/token_tracker.py"):
                    continue
                sites, dead = _py_recording_sites(rel, src, call_re)
                for key, n in sites.items():
                    if n:
                        _add(py, key, rel)
                unreachable.extend(dead)
            else:
                if "recordLLMUsage(" not in src:
                    continue
                # 定义处(internal/foundation/llm_usage.go)不是调用点
                if rel.endswith("internal/foundation/llm_usage.go"):
                    continue
                for m in go_call_re.finditer(src):
                    got = re.match(r"\s*\"([A-Za-z0-9_\-]+)\"", m.group(1))
                    key = got.group(1).lower() if got else "(动态)"
                    _add(go, key, rel)
                # 构造时声明的 provider 身份也算证据(动态传参靠它才认得出来)
                for m in go_name_re.finditer(src):
                    _add(go, m.group(1).lower(), rel)

    return {
        "py": {"by_provider": py, "files": sorted({f for fs in py.values() for f in fs}),
               "unreachable": unreachable},
        "go": {"by_provider": go, "files": sorted({f for fs in go.values() for f in fs})},
    }


def _py_recording_sites(rel, src, call_re):
    """AST 分析: 找出**真的会执行到**的 ``record_llm_usage`` 调用点。

    为什么必须做可达性判断, 而不是正则数一下调用点个数 —— 这不是理论洁癖, 是实测:
    ``scripts/provider_llm.py`` 的记账包在私有包装函数 ``_record_usage()`` 里。
    把**所有对它的调用**删掉、只留函数定义, 正则扫描依然数到一个 ``record_llm_usage(``
    调用点, 于是报告写"记录中", 而实际上一个 token 都没进库。这类"死记账点"正是
    本模块存在的理由, 不能被自己的检查放过去。

    规则: 调用点所在的**私有**包装函数(名字以 ``_`` 开头, 且不是定义本身)必须在同文件内
    被调用过。公开入口(如 ``vision_analyze`` —— 由 CLI 拉起)豁免: 它们在文件内本来就
    不会被调用, 按"没有内部调用者"判死会产生大量假阳性。

    解析失败(语法错误)时退回正则, 并把"退回"这件事如实记在 ``unreachable`` 之外 ——
    宁可少判, 也不要因为自己解析不了就诬告某个 provider 没在记账。

    返回 ``(by_provider, unreachable)``; ``unreachable`` 元素是 ``(文件, 函数名, provider)``。
    """
    import ast

    try:
        tree = ast.parse(src)
    except SyntaxError:
        found: Dict[str, int] = {}
        for m in call_re.finditer(src):
            got = re.search(r"provider\s*=\s*[\"']([A-Za-z0-9_\-]+)[\"']", m.group(1))
            key = got.group(1).lower() if got else "(动态)"
            found[key] = found.get(key, 0) + 1
        return found, []

    parents: Dict[Any, Any] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                called.add(f.id)
            elif isinstance(f, ast.Attribute):
                called.add(f.attr)

    by_provider: Dict[str, int] = {}
    unreachable: List[Any] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (
            f.attr if isinstance(f, ast.Attribute) else "")
        if name != "record_llm_usage":
            continue
        key = "(动态)"
        for kw in (node.keywords or []):
            if kw.arg == "provider" and isinstance(kw.value, ast.Constant) \
                    and isinstance(kw.value.value, str):
                key = kw.value.value.lower()
        fn = None
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = cur
                break
        if fn is None:
            # 模块级调用: 导入/执行即发生, 可达
            by_provider[key] = by_provider.get(key, 0) + 1
            continue
        if fn.name == "record_llm_usage":
            continue                      # 定义本身, 不是调用点
        if fn.name.startswith("_") and fn.name not in called:
            unreachable.append((rel, fn.name, key))
            continue
        by_provider[key] = by_provider.get(key, 0) + 1
    return by_provider, unreachable


def _add(bucket: Dict[str, List[str]], key: str, rel: str) -> None:
    bucket.setdefault(key, [])
    if rel not in bucket[key]:
        bucket[key].append(rel)


def caller_summary(root: str = "") -> Dict[str, Any]:
    """给报告用的调用点摘要(区分 Python / Go 两侧, 并统计哪些文件在记)。"""
    rec = scan_recorders(root)
    files = sorted(set(rec["py"]["files"]) | set(rec["go"]["files"]))
    return {"by_provider": rec["py"]["by_provider"],
            "go_by_provider": rec["go"]["by_provider"],
            "files": files,
            "py_files": rec["py"]["files"],
            "go_files": rec["go"]["files"],
            # 定义了记账却没有到达路径的调用点(详见 _py_recording_sites)
            "unreachable": rec["py"].get("unreachable") or []}


# --------------------------------------------------------------------------- #
# 发现
# --------------------------------------------------------------------------- #
def _env_flag(name: str) -> str:
    """环境变量的值(空字符串表示未设置)。"""
    return (os.environ.get(name) or "").strip()


def current_selection() -> Dict[str, str]:
    """当前选中的文本/视觉 provider(来自环境变量与各自的默认值)。"""
    return {
        "text": _env_flag("LLM_PROVIDER").lower() or "deepseek",
        "vision": _env_flag("VISION_PROVIDER").lower() or VISION_DEFAULT,
    }


def discover(root: str = "") -> List[Dict[str, Any]]:
    """逐个 provider 报出: 有没有代码、配没配凭据、是不是当前选中、**谁在真的记用量**。

    全部是**本地可判定**的事实, 不发网络请求(凭据探测要显式 ``--live``)。

    ``has_recorder`` 取自 ``scan_recorders()`` 的**源码证据**, 不是注册表里的声明 ——
    声明的记录者只要不存在, token 就永远进不了库, 而那种缺口恰恰只有扫代码才能发现。
    """
    sel = current_selection()
    rec = scan_recorders(root)
    callers = rec["py"]["by_provider"]
    go_callers = rec["go"]["by_provider"]
    caller_files = set(rec["py"]["files"]) | set(rec["go"]["files"])
    out: List[Dict[str, Any]] = []

    for prov in PROVIDERS:
        channels = []
        for ch in prov.channels:
            module_found = bool(find_module(ch.module))
            cred = ""
            if ch.env_key:
                cred = "已设置" if _env_flag(ch.env_key) else ""
            if not cred and ch.credential_file:
                cred = "存在" if os.path.exists(os.path.expanduser(ch.credential_file)) else ""
            channels.append({
                "name": ch.name,
                "module": ch.module,
                "module_found": module_found,
                "env_key": ch.env_key,
                "credential_file": ch.credential_file,
                "configured": bool(cred),
                "credential": cred,
                "usage": ch.usage,
                # 这条通道的实现文件里**真的**有记账调用吗(Python: record_llm_usage,
                # Go: recordLLMUsage)。只看有没有调用, 不看有没有声明。
                "records_usage": ch.usage == USAGE_RESPONSE and ch.module in caller_files,
                "note": ch.note,
            })

        integrated = any(c["module_found"] for c in channels)
        configured = any(c["configured"] for c in channels)
        active = sel["text"] == prov.key or sel["vision"] == prov.key \
            or (prov.key == _MMX_ACCOUNT_PROVIDER and sel["vision"] == VISION_DEFAULT)
        prov_callers = list(callers.get(prov.key) or [])
        prov_callers += [f for f in (go_callers.get(prov.key) or [])
                         if f not in prov_callers]
        # Go 侧注册名与落库名可能不同(glm → zhipu), 别名也算同一家的证据
        for alias, canon in PROVIDER_ALIASES.items():
            if canon == prov.key and alias != prov.key:
                prov_callers += [f for f in (go_callers.get(alias) or [])
                                 if f not in prov_callers]
        # 动态传参(如 provider=canonical_provider(p))在源码里拿不到字面量, 会被归到
        # "(动态)" 下。只要**该通道的实现文件**确实在记录, 就应当计入这个 provider ——
        # 否则同一件事在通道级判"记"、在 provider 级判"没记", 报告自相矛盾。
        for c in channels:
            if c["records_usage"] and c["module"] not in prov_callers:
                prov_callers.append(c["module"])
        prov_callers.sort()

        out.append({
            "key": prov.key,
            "label": prov.label,
            "kind": prov.kind,
            "integrated": integrated,
            "configured": configured,
            "active": active,
            "has_recorder": bool(prov_callers),
            "callers": prov_callers,
            "channels": channels,
            "account_usage": prov.account_usage,
            "account_probe": prov.account_probe,
            "probe_endpoint": prov.probe_endpoint,
            "note": prov.note,
            "per_call_usage": any(c["usage"] == USAGE_RESPONSE for c in channels),
            # 有 usage 字段、也有通道, 但没有任何通道把调用点写在实现文件里
            "unrecorded_channels": [c["name"] for c in channels
                                    if c["usage"] == USAGE_RESPONSE and not c["records_usage"]],
        })
    return out


# --------------------------------------------------------------------------- #
# 凭据探测(发网络请求; 只在显式 --live 时调用)
# --------------------------------------------------------------------------- #
def _http_status(url: str, api_key: str, timeout: int = PROBE_TIMEOUT) -> Tuple[bool, str]:
    """带 Bearer 的 GET。返回 ``(是否通过鉴权, 说明)``。

    401/403 直接判为凭据不可用 —— 这是"配了 key 但 key 是坏的"最典型的形态;
    网络不通与鉴权失败**分开报**, 因为处置完全不同。
    """
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer %s" % api_key,
        "Accept": "application/json",
        "User-Agent": "via54Medit-telemetry/1.0 (llm-probe)",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, "HTTP %d" % resp.status
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "鉴权被拒 (HTTP %d) — 密钥无效或无该作用域" % e.code
        # 404 之类说明**鉴权过了**但端点不同, 不该判成凭据问题
        return True, "端点返回 HTTP %d (鉴权已通过)" % e.code
    except Exception as e:                                  # noqa: BLE001
        return False, "网络不可达: %s" % str(e)[:120]


def probe_credential(prov: Dict[str, Any]) -> Dict[str, Any]:
    """验证一个 provider 的凭据。返回 ``{"verifiable": bool, "ok": bool|None, "detail": str}``。"""
    key = prov["key"]

    if key == _MMX_ACCOUNT_PROVIDER:
        # mmx-cli 自带的凭据自检 —— 不花钱, 也不会误判
        mmx = _which("mmx")
        if not mmx:
            return {"verifiable": False, "ok": None,
                    "detail": "未安装 mmx-cli, 无法验证该通道凭据"}
        try:
            r = subprocess.run([mmx, "auth", "status"], capture_output=True,
                               text=True, timeout=PROBE_TIMEOUT)
        except Exception as e:                              # noqa: BLE001
            return {"verifiable": False, "ok": None, "detail": "mmx auth status 执行失败: %s" % e}
        if r.returncode != 0:
            return {"verifiable": True, "ok": False,
                    "detail": (r.stdout + r.stderr).strip()[:160] or "未登录"}
        try:
            info = json.loads(r.stdout or "{}")
        except ValueError:
            info = {}
        method = info.get("method") or "unknown"
        source = info.get("source") or "?"
        masked = info.get("key") or ""
        return {"verifiable": True, "ok": True,
                "detail": "已登录 (%s, 来源 %s%s)" % (method, source,
                                                   ", %s" % masked if masked else "")}

    chans = [c for c in prov["channels"] if c.get("env_key")]
    if not chans:
        return {"verifiable": False, "ok": None, "detail": "该 provider 没有可探测的凭据"}
    endpoint = prov.get("probe_endpoint") or ""
    if not endpoint:
        return {"verifiable": False, "ok": None,
                "detail": "未发现公开的鉴权探针 (只能靠调用时报错暴露)"}

    tried = []
    for ch in chans:
        val = _env_flag(ch["env_key"])
        if not val:
            continue
        ok, detail = _http_status(endpoint, val)
        tried.append("%s: %s" % (ch["env_key"], detail))
        if not ok:
            return {"verifiable": True, "ok": False, "detail": "; ".join(tried)}
    if not tried:
        return {"verifiable": True, "ok": None,
                "detail": "未配置凭据 (环境变量 %s 均未设置)"
                          % "/".join(c["env_key"] for c in chans)}
    return {"verifiable": True, "ok": True, "detail": "; ".join(tried)}


# --------------------------------------------------------------------------- #
# 账户级用量(目前只有 mmx-cli 可程序化读取)
# --------------------------------------------------------------------------- #
def read_mmx_quota(timeout: int = PROBE_TIMEOUT) -> Optional[Dict[str, Any]]:
    """读取 mmx-cli 的账户级配额与已用**次数**。

    返回 ``{"models": [{"name", "interval_used", "interval_total", "weekly_used",
    "weekly_total", "interval_remaining_percent", "weekly_remaining_percent"}], "units": "count"}``。

    强调 ``units: "count"``: 它给的是**调用次数**而不是 token, 所以调用方**不要**把它折算成
    token 写进 ``llm_token_logs`` —— 那是造数。它只用来回答"账户侧是不是还有额度"。
    """
    mmx = _which("mmx")
    if not mmx:
        return None
    try:
        r = subprocess.run([mmx, "quota", "show", "--output", "json"],
                           capture_output=True, text=True, timeout=timeout + 10)
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout or "{}")
    except Exception:                                       # noqa: BLE001
        return None

    models = []
    for m in data.get("model_remains") or []:
        if not isinstance(m, dict):
            continue
        models.append({
            "name": m.get("model_name") or "?",
            "interval_used": m.get("current_interval_usage_count"),
            "interval_total": m.get("current_interval_total_count"),
            "weekly_used": m.get("current_weekly_usage_count"),
            "weekly_total": m.get("current_weekly_total_count"),
            "interval_remaining_percent": m.get("current_interval_remaining_percent"),
            "weekly_remaining_percent": m.get("current_weekly_remaining_percent"),
        })
    if not models:
        return None
    return {"models": models, "units": "count",
            "note": "单位是调用次数, 不是 token —— 不要折算成 token 入库"}


# --------------------------------------------------------------------------- #
# 证明"真能读到 token 消耗": 离线端到端摄入校验
# --------------------------------------------------------------------------- #
#: 每个 provider 的**真实响应形状**。用真实报文, 校验才有效 ——
#: 自造一个理想报文再验, 只能证明测试自己写的形状是通的。
_SAMPLE_RESPONSES: Dict[str, Dict[str, Any]] = {
    "deepseek": {"id": "chatcmpl-ds-1", "model": "deepseek-chat",
                 "choices": [{"message": {"content": "ok"}}],
                 "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}},
    "openai": {"id": "chatcmpl-oa-1", "model": "gpt-4o-mini",
               "choices": [{"message": {"content": "ok"}}],
               "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}},
    "minimax": {"id": "mm-1", "model": "MiniMax-M3",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250}},
    "zhipu": {"id": "glm-1", "model": "glm-4.6v-flash",
              "choices": [{"message": {"content": "ok"}}],
              "usage": {"prompt_tokens": 300, "completion_tokens": 40, "total_tokens": 340}},
    "sensenova": {"id": "sn-1", "model": "SenseNova-V6.5",
                  "choices": [{"message": {"content": "ok"}}],
                  "usage": {"prompt_tokens": 150, "completion_tokens": 60, "total_tokens": 210}},
    "hermes": {"id": "hg-1", "model": "MiniMax-M3",
               "choices": [{"message": {"content": "ok"}}],
               "usage": {"prompt_tokens": 60, "completion_tokens": 15, "total_tokens": 75}},
}


def verify_ingestion(db_path: str = "") -> List[Dict[str, Any]]:
    """对每个 provider 做一次**离线**的端到端摄入校验。

    链路: 真实形状的响应 → ``record_llm_usage`` → 临时 SQLite → 读回来核对
    (provider / model / tokens 三项都要对)。**只写临时库**, 绝不碰生产库 ——
    否则这台机器的 token 统计就被人造假数据污染了。

    这是"确保真能读取接入的所有 LLM 的 token 消耗"里**可离线、可重复**的那一半;
    另一半(凭据真的能通)需要 ``--live``, 见 :func:`probe_credential`。
    """
    import tempfile

    from .token_tracker import record_llm_usage

    results: List[Dict[str, Any]] = []
    tmpdir = tempfile.mkdtemp(prefix="llm_verify_")
    try:
        from .db import TelemetryDB

        for prov in PROVIDERS:
            key = prov.key
            sample = _SAMPLE_RESPONSES.get(key)
            if sample is None:
                results.append({"key": key, "ok": None, "detail": "读不到 token(该通道无 usage 字段)"})
                continue
            db_file = db_path or os.path.join(tmpdir, "%s.db" % key)
            try:
                db = TelemetryDB(db_file)
                rec = record_llm_usage(response=dict(sample), provider=key,
                                       project_name="__verify__",
                                       source="llm_providers.verify_ingestion", db=db)
                if rec is None:
                    results.append({"key": key, "ok": False, "detail": "record_llm_usage 未落库"})
                    continue
                rows = db.query_llm_tokens(provider=key)
                if not rows:
                    results.append({"key": key, "ok": False, "detail": "落库后读不回来"})
                    continue
                got = rows[0]
                want = sample["usage"]
                # 一路读到**报表层**: 入库还不够, 统计口径也要真的把它算进去。
                try:
                    from .aggregator import TelemetryAggregator

                    report_total = TelemetryAggregator(db).get_all_time_report().total_tokens
                except Exception as e:                      # noqa: BLE001
                    report_total = -1
                    results.append({"key": key, "ok": False,
                                    "detail": "报表层读取失败: %s" % str(e)[:120]})
                    continue
                checks = {
                    "provider": got["provider"] == key,
                    "model": got["model"] == sample["model"],
                    "prompt": got["prompt_tokens"] == want["prompt_tokens"],
                    "completion": got["completion_tokens"] == want["completion_tokens"],
                    "total": got["total_tokens"] == want["total_tokens"],
                    "report": report_total == want["total_tokens"],
                }
                bad = [k for k, v in checks.items() if not v]
                results.append({
                    "key": key,
                    "ok": not bad,
                    "detail": ("往返一致(含报表层): %s/%s %d+%d=%d" % (
                        got["provider"], got["model"], got["prompt_tokens"],
                        got["completion_tokens"], got["total_tokens"]))
                    if not bad else "字段不一致: %s" % ", ".join(bad),
                })
            except Exception as e:                          # noqa: BLE001
                results.append({"key": key, "ok": False, "detail": "校验异常: %s" % str(e)[:150]})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return results


#: Go 侧 spool 的真实行形状(与 ``internal/foundation/llm_usage.go`` 写出的字段一一对应)。
#: 其中 glm 那条用 Go 的注册名 "glm", 用来证明别名归一真的生效。
_SPOOL_SAMPLE_LINES = (
    '{"ts":"2026-01-05T10:00:00Z","provider":"deepseek","model":"deepseek-chat",'
    '"prompt_tokens":120,"completion_tokens":30,"total_tokens":150,'
    '"req_id":"spool-ds-1","source":"go:medplan/research.go","project_name":""}',
    '{"ts":"2026-01-05T10:01:00Z","provider":"glm","model":"glm-4-flash",'
    '"prompt_tokens":300,"completion_tokens":40,"total_tokens":340,'
    '"req_id":"spool-glm-1","source":"go:docproc/entity","project_name":""}',
)


def verify_spool_ingestion(db_path: str = "") -> Dict[str, Any]:
    """离线证明 **Go 侧链路真的通**: spool 一行 → 摄入 → 读回 → 报表层, 且可重放。

    Go 侧没有 SQLite 驱动, 用量先落 spool 再由本模块摄入 —— 这条链路如果断了,
    ``medit ask`` / ``medplan`` / docproc 的 token 会一行都进不了库, 而调用本身
    一切正常(记账是旁路, 失败不报错)。所以必须单独验证, 不能靠"代码看起来写了"。

    额外验证两件事:
    * **别名归一**: Go 叫 ``glm``, 落库必须是 ``zhipu``, 否则报表里凭空多一家;
    * **幂等重放**: 同样的 spool 再摄入一次, 导入数应为 0、重复数应等于行数。
    """
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix="llm_spool_verify_")
    try:
        from . import llm_spool
        from .db import TelemetryDB

        spool_file = os.path.join(tmpdir, "spool.jsonl")
        db = TelemetryDB(db_path or os.path.join(tmpdir, "spool.db"))

        def write_spool():
            with open(spool_file, "w", encoding="utf-8") as fh:
                for ln in _SPOOL_SAMPLE_LINES:
                    fh.write(ln + "\n")

        write_spool()
        first = llm_spool.ingest(path=spool_file, db=db)
        if first["imported"] != len(_SPOOL_SAMPLE_LINES):
            return {"ok": False, "detail": "首次摄入导入了 %d 行, 期望 %d 行 (invalid=%d)"
                    % (first["imported"], len(_SPOOL_SAMPLE_LINES), first["invalid"])}

        ds = db.query_llm_tokens(provider="deepseek")
        glm_rows = db.query_llm_tokens(provider="zhipu")
        raw_glm = db.query_llm_tokens(provider="glm")
        if not ds or ds[0]["total_tokens"] != 150:
            return {"ok": False, "detail": "deepseek 行读回来不对: %s"
                    % ([dict(r) for r in ds] or "空")}
        if not glm_rows:
            return {"ok": False, "detail": "glm 行没有归一到 zhipu (provider 别名失效)"}
        if raw_glm:
            return {"ok": False, "detail": "库里出现了裸的 glm provider, 未归一"}
        if glm_rows[0]["total_tokens"] != 340:
            return {"ok": False, "detail": "zhipu 行 total_tokens = %s, 期望 340"
                    % glm_rows[0]["total_tokens"]}
        # created_at 必须取 spool 的 ts, 而不是"摄入时刻" —— 否则按周切分会对不上
        if not str(ds[0]["created_at"]).startswith("2026-01-05"):
            return {"ok": False, "detail": "created_at = %s, 应取自 spool 的 ts"
                    % ds[0]["created_at"]}

        # 幂等重放: 同样的内容再喂一次
        write_spool()
        second = llm_spool.ingest(path=spool_file, db=db)
        if second["imported"] != 0 or second["duplicated"] != len(_SPOOL_SAMPLE_LINES):
            return {"ok": False, "detail": "重放未幂等: imported=%d duplicated=%d"
                    % (second["imported"], second["duplicated"])}

        try:
            from .aggregator import TelemetryAggregator

            report_total = TelemetryAggregator(db).get_all_time_report().total_tokens
        except Exception as e:                                  # noqa: BLE001
            return {"ok": False, "detail": "报表层读取失败: %s" % str(e)[:120]}
        if report_total != 490:
            return {"ok": False, "detail": "报表层 total_tokens = %s, 期望 490" % report_total}

        return {"ok": True,
                "detail": "spool→库→报表 往返一致: 150(zhipu 归一等价 340) 合计 490; 重放幂等"}
    except Exception as e:                                      # noqa: BLE001
        return {"ok": False, "detail": "校验异常: %s" % str(e)[:150]}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return results


# --------------------------------------------------------------------------- #
# 总审计
# --------------------------------------------------------------------------- #
def audit(live: bool = False, ingest: bool = False) -> Dict[str, Any]:
    """完整审计: 发现 + (可选)凭据探测 + 离线摄入校验 + 问题清单。

    "问题"只报**能确证**的四类, 不制造噪音:
    1. 通道会返回 ``usage``, 但实现文件里**没有**记账调用点 ——
       token 永远进不了库(这是最该被发现的真实缺口, 且只有扫代码能看出来);
    2. 配了凭据但探测不通过 —— 调用会失败(需 ``live``);
    3. 摄入校验不通过 —— 有 usage 字段却落不了库/读不回来;
    4. spool 链路校验不通过 —— Go 侧写的用量进不了库。

    ``ingest=True`` 时会**真的**把 Go 侧 spool 摄入生产库(部署校验会这么做,
    因为"能读"必须包含"已经把积压的读进来了")。
    """
    from . import llm_spool

    provs = discover()
    ingestion = {r["key"]: r for r in verify_ingestion()}
    spool_check = verify_spool_ingestion()
    ingest_result: Dict[str, Any] = {}
    if ingest:
        ingest_result = llm_spool.ingest()
    spool_state = llm_spool.spool_status()

    probes: Dict[str, Any] = {}
    if live:
        for p in provs:
            probes[p["key"]] = probe_credential(p)

    problems: List[str] = []
    for p in provs:
        ing = ingestion.get(p["key"]) or {}
        p["ingestion"] = ing
        p["probe"] = probes.get(p["key"])
        if not p["integrated"]:
            continue
        if ing.get("ok") is False:
            problems.append("%s: 摄入校验未通过 — %s" % (p["key"], ing.get("detail")))
        if p["per_call_usage"] and not p["has_recorder"]:
            # 整个 provider 没有任何记录点: 报一条就够, 不必再逐通道重复(那是同一条事实)
            problems.append(
                "%s: 没有任何代码路径记录用量 —— 它在报表里永远是 0" % p["key"])
        else:
            for name in p.get("unrecorded_channels") or []:
                problems.append(
                    "%s 的「%s」通道会返回 usage, 但实现文件里没有 record_llm_usage 调用点 "
                    "—— 这部分 token 消耗进不了库" % (p["key"], name))
    if live:
        for key, pr in probes.items():
            if pr.get("verifiable") and pr.get("ok") is False:
                problems.append("%s: 凭据探测未通过 — %s" % (key, pr.get("detail")))
    # "死记账点": 私有包装函数定义了记账却没人调用 —— 比"完全没写"更隐蔽,
    # 因为源码里确实存在 record_llm_usage(, 只有可达性分析能识破。
    for rel, fn_name, key in (caller_summary().get("unreachable") or []):
        problems.append("%s 里的 %s() 定义了记账但同文件没有任何地方调用它 "
                        "—— 这个 provider 的用量不会进库" % (rel, fn_name))
    if spool_check.get("ok") is False:
        problems.append("Go 侧 spool 链路校验未通过 — %s" % spool_check.get("detail"))
    if ingest_result and ingest_result.get("invalid"):
        # 有解析不了的行 = Go 与 Python 两端的字段约定已经漂了, 必须报出来
        problems.append("spool 有 %d 行无法解析, 这部分用量读不到 — %s"
                        % (ingest_result["invalid"],
                           "; ".join(ingest_result.get("problems") or [])[:200]))

    return {
        "selection": current_selection(),
        "providers": provs,
        "live": live,
        "ingestion_verifiable": sum(1 for r in ingestion.values() if r.get("ok") is not None),
        "spool_verify": spool_check,
        "spool": spool_state,
        "ingest": ingest_result,
        "callers": caller_summary(),
        "problems": problems,
        "mmx_quota": read_mmx_quota() if live else None,
    }


def account_usage_map() -> Dict[str, str]:
    """``{provider: 账户级用量怎么读}`` —— 供文档与 CLI 展示。"""
    return {p.key: p.account_usage for p in PROVIDERS}


def format_report(res: Dict[str, Any], verbose: bool = False) -> str:
    """把审计结果渲染成文本。CLI 与部署校验**共用这一份**, 免得两处口径分叉。"""
    lines: List[str] = []
    sel = res.get("selection") or {}
    lines.append("=======================================================")
    lines.append("🤖 LLM 接入与 Token 用量读取能力审计")
    lines.append("=======================================================")
    lines.append("• 当前选中:   文本 %s · 视觉 %s" % (sel.get("text", "?"), sel.get("vision", "?")))
    lines.append("• 校验范围:   %d 个 provider (离线摄入校验: %d 个可验)"
                 % (len(res.get("providers") or []), res.get("ingestion_verifiable") or 0))
    lines.append("")

    head = "%-10s %-6s %-6s %-6s %-9s %s" % ("provider", "代码", "凭据", "记录点", "单次用量", "账户级用量")
    lines.append(head)
    lines.append("-" * len(head))
    for p in res.get("providers") or []:
        mark = lambda b: "✓" if b else "✗"          # noqa: E731
        usage = "可读" if p["per_call_usage"] else "读不到"
        note = p["account_usage"].split(";")[0].strip() or "-"
        lines.append("%-10s %-6s %-6s %-6s %-9s %s" % (
            p["key"], mark(p["integrated"]), mark(p["configured"]),
            mark(p["has_recorder"]), usage, note[:44]))
        if verbose:
            for c in p["channels"]:
                lines.append("            · %-14s %-32s %s" % (
                    c["name"], c["module"],
                    ("记录中" if c["records_usage"] else
                     ("通道不返回 token" if c["usage"] == USAGE_NONE else "未接记录"))))
            ing = p.get("ingestion") or {}
            if ing:
                lines.append("            · 摄入校验: %s %s"
                             % (mark(ing.get("ok")), ing.get("detail", "")))
            if p.get("callers"):
                lines.append("            · 记录者: %s" % ", ".join(p["callers"]))

    quota = res.get("mmx_quota")
    if quota:
        lines.append("")
        lines.append("• mmx 账户级用量(单位: %s, 不是 token):" % quota.get("units"))
        for m in quota["models"]:
            lines.append("    - %-10s 本周期 %s/%s · 本周 %s/%s · 剩余 %s%%" % (
                m["name"], m["interval_used"], m["interval_total"],
                m["weekly_used"], m["weekly_total"], m["weekly_remaining_percent"]))

    # Go 侧走 spool 落盘(没有 SQLite 驱动), 这条链路必须单独报 —— 它断了的话
    # medit ask / medplan / docproc 的 token 一行都进不了库, 而调用看起来完全正常。
    spool = res.get("spool") or {}
    sv = res.get("spool_verify") or {}
    if spool:
        lines.append("")
        lines.append("• Go 侧 spool: %s" % spool.get("path", ""))
        lines.append("    待摄入 %s 行 · %s" % (
            spool.get("pending", 0),
            ("最后写入 %s" % spool["mtime"]) if spool.get("mtime") else "尚无 Go 侧调用"))
        ing = res.get("ingest") or {}
        if ing:
            lines.append("    本次摄入: 导入 %d 行 · 重复跳过 %d 行 · 无效 %d 行"
                         % (ing.get("imported", 0), ing.get("duplicated", 0),
                            ing.get("invalid", 0)))
        if sv:
            lines.append("    链路校验: %s %s" % ("✓" if sv.get("ok") else "✗",
                                            sv.get("detail", "")))

    problems = res.get("problems") or []
    lines.append("")
    if problems:
        lines.append("✗ 发现 %d 个问题:" % len(problems))
        for prob in problems:
            lines.append("    • %s" % prob)
        lines.append("")
        lines.append("  说明: \"单次用量读不到\"的通道(如 mmx-cli)不算问题 —— 那取决于服务商")
        lines.append("        是否暴露 token; 这里只报**能确证是缺陷**的(有 usage 字段却没人记)。")
    else:
        lines.append("✓ 没有发现问题: 所有会返回 usage 的通道都有代码在记录(Python 与 Go 两侧), ")
        lines.append("  每个 provider 的用量都能落库并读回报表, Go 侧 spool 链路也已验证。")
    lines.append("=======================================================")
    return "\n".join(lines)
