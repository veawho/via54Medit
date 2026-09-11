"""Workspace watcher and output scanner for TraeWork literature projects."""

import csv
import glob
import json
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional

try:
    import pymupdf as fitz  # PyMuPDF 1.24+ 的正式导入名
except ImportError:
    try:
        import fitz  # 仅旧版本才有这个名字
    except ImportError:
        fitz = None

from .db import TelemetryDB
from .models import DownloadItem, HighlightItem, RetrievalItem, TaskRecord, TaskType
from .pdf_utils import get_pdf_page_count

#: 中文项目常用的高亮产物目录名 (RSV 等): <项目>/高亮结果/*.pdf
HL_DIRNAME = "高亮结果"
#: 每 Pn-x 条目附带的高亮元信息 (含 reference_field / doi / pmid)
HL_META_GLOB = os.path.join(HL_DIRNAME, "*_meta.json")
#: 高亮引用清单 (pn_x / reference_field / highlights / status), meta 缺失时回退
HL_LIST_TSV = f"{HL_DIRNAME}清单.tsv"
#: 无法取得标注数时的均摊基准 (沿用既有行为)
DEFAULT_ANNOTS = 5
#: 检索环节的单篇均摊耗时 (基准, 与历史实现一致)
RETRIEVAL_SECONDS_PER_PAPER = 12.0

# --------------------------------------------------------------------------- #
# 路径卫生 —— 只统计"真实产出物", 不统计备份/临时副本
#
# 这条规则是**统计准确性的前提**。实测发现: RSV 项目下的 `_bak_20260906_201108/高亮结果/`
# 与 `_bak2_20260906_205621/高亮结果/` 被当作成果一起扫了进来, 于是同一篇文献(同一个
# paper_id)在库里出现 3 行 —— 高亮篇数与阅读页数因此虚高到 3 倍(150 篇 / 2917 页,
# 实际 50 篇)。而且**时对时错**: 备份目录被删掉, 数字又"自己变回去"。
#
# 判据用**路径片段的前缀**而不是整串子串: 子串匹配会误伤名字里恰好含 bak 的文献
# (例如 `Wang_bak_2020.pdf`), 也会牵连 `_highlight.pdf` 这类正常产物。
# 只看片段前缀时, `_2_pdfs/`、`_highlight_nested/` 这类合法的下划线开头目录不受影响
# (它们的前缀是 `_2` / `_h`), 所以不需要额外的例外清单。
# --------------------------------------------------------------------------- #
IGNORED_SEGMENT_PREFIXES = (
    "_bak",             # _bak / _bak2 / _bakup 等
    "_backup",
    "_old",
    "_archive",
    "_trash",
    "_copy",
    "_moved",
    ".git",             # .git / .github
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
)


def is_ignored_path(path: str) -> bool:
    """该路径是否位于备份/临时目录下(不应计入统计)。"""
    if not path:
        return False
    norm = os.path.normcase(os.path.abspath(path)).replace("\\", "/")
    return any(seg.startswith(pref) for seg in norm.split("/") if seg
               for pref in IGNORED_SEGMENT_PREFIXES)


def filter_paths(paths: List[str]) -> List[str]:
    """滤掉备份/临时目录下的路径, 保持原顺序。"""
    return [p for p in paths if not is_ignored_path(p)]

#: 引用串中的样板噪声 (归一化时剔除), 这些片段不承载文献身份
_REF_BOILERPLATE = (
    r"available\s*at\s*:.*$",
    r"accessed\s*:?.*$",
    r"retrieved\s+from.*$",
    r"\(accessed[^)]*\)",
    r"\[accessed[^]]*\]",
    r"https?://\S+",
    r"\b\d{2}-\d{4}-[A-Z]{2}-[A-Z]{3}-\d{5}\b",  # 文档编号, 如 07-2028-CN-RSM-00086
)

#: 具有独立文献含义的限定词 —— 命中则不得与主文献合并 (如 正文 vs 补充附录)
_REF_QUALIFIER_RE = re.compile(
    r"(supplementary|suppl\.?|appendix|erratum|corrigendum|correction|reply|comment|abstract|poster|protocol)"
)

#: 前缀归并要求的最短公共长度, 防止短串误合
_REF_MIN_PREFIX = 30

#: 允许被忽略的"良性尾巴" (仅数字/日期/文号一类, 无文献含义)
_REF_BENIGN_TAIL_RE = re.compile(r"[\d.\-/a-z]{0,20}")


def _normalize_doi(doi: str) -> str:
    """DOI 归一化: 去掉 URL / ``doi:`` 前缀与大小写差异, 便于精确去重。"""
    text = (doi or "").strip()
    text = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.IGNORECASE)
    return text.strip().rstrip(".").casefold()


def _ref_identity(text: str) -> str:
    """引用串 -> 文献身份串 (去空白与样板尾巴, 大小写折叠)。"""
    value = re.sub(r"[\s\u3000]+", "", text or "").casefold()
    for pattern in _REF_BOILERPLATE:
        # 值已 casefold, 故这里统一忽略大小写 (否则 [A-Z] 类模式会失配)
        value = re.sub(pattern, "", value, flags=re.IGNORECASE)
    return value.strip(".,;:()[] ")


def _same_reference(identity_a: str, identity_b: str) -> bool:
    """判断两个身份串是否指向同一文献。

    仅在「其一为另一者的前缀」且「多出的尾巴属良性噪声」时判为同一文献;
    若尾巴含 supplementary / appendix / erratum 等有独立意义的限定词则不合并,
    避免把正文与其补充附录、勘误等误并成一篇。
    """
    if not identity_a or not identity_b:
        return False
    if identity_a == identity_b:
        return True
    longer, shorter = (
        (identity_a, identity_b) if len(identity_a) >= len(identity_b) else (identity_b, identity_a)
    )
    if len(shorter) < _REF_MIN_PREFIX or not longer.startswith(shorter):
        return False
    extra = longer[len(shorter):].strip(".,;:()[] ")
    if _REF_QUALIFIER_RE.search(extra):
        return False
    return bool(_REF_BENIGN_TAIL_RE.fullmatch(extra))


def _collect_reference_candidates(project_dir: str):
    """收集 ``(doi, reference, url)`` 候选, 并返回 (候选列表, 数据源名)。"""
    candidates = []

    for meta_path in sorted(glob.glob(os.path.join(project_dir, HL_META_GLOB))):
        try:
            with open(meta_path, "r", encoding="utf-8") as fp:
                meta = json.load(fp)
        except Exception:
            continue
        reference = (meta.get("reference_field") or "").strip()
        doi = (meta.get("doi") or "").strip()
        pmid = (meta.get("pmid") or "").strip()
        if not reference and not doi:
            continue
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        candidates.append((doi, reference, url))
    if candidates:
        return candidates, f"{HL_DIRNAME}/*_meta.json"

    tsv_path = os.path.join(project_dir, HL_LIST_TSV)
    if os.path.exists(tsv_path):
        try:
            with open(tsv_path, "r", encoding="utf-8") as fp:
                for row in csv.DictReader(fp, delimiter="\t"):
                    reference = (row.get("reference_field") or row.get("reference") or "").strip()
                    if reference:
                        candidates.append(("", reference, ""))
        except Exception:
            return [], ""
        return candidates, os.path.basename(tsv_path)

    return [], ""


def _collect_reference_records(project_dir: str):
    """从「高亮引用清单」读取被引文献并去重。

    指标口径: 检索数 = 去重后的唯一被引文献数 (与"下载/高亮"同为唯一文献口径,
    重复引用同一篇文献只计一次)。

    去重分两层:
      1. **DOI 优先 (精确)**: 有 DOI 时以归一化 DOI 为身份, 跨著录写法稳定;
      2. **引用身份 + 保守前缀归并**: 无 DOI 时按引用串归一化身份去重, 并对
         "同一文献的不同著录写法"做保守归并 (规则见 ``_same_reference``)。

    数据源优先级:
      1. ``高亮结果/*_meta.json`` —— 每 Pn-x 一条, ``reference_field`` 完整, 可能带 doi/pmid;
      2. ``高亮结果清单.tsv`` —— 兜底。注意该 TSV 的 ``reference_field`` 会被导出截断,
         故仅在无 meta 时使用。

    返回 ``(records, source)``; records 为 ``(paper_id, doi, url, citation_text)`` 列表。
    """
    candidates, source = _collect_reference_candidates(project_dir)

    accepted = []   # [(key, identity)] 已采纳的唯一文献
    doi_index = {}  # 归一化 DOI -> key
    records = []

    for doi, reference, url in candidates:
        norm_doi = _normalize_doi(doi)
        identity = _ref_identity(reference)

        # 1) DOI 是否已见过
        if norm_doi and norm_doi in doi_index:
            continue

        # 2) 引用身份是否与已采纳文献为同一篇 (DOI 缺失时的保守归并)
        matched = None
        for exist_key, exist_identity in accepted:
            if _same_reference(identity, exist_identity):
                matched = exist_key
                break
        if matched is not None:
            if norm_doi:
                doi_index[norm_doi] = matched
            continue

        key = norm_doi or identity
        if not key:
            continue
        accepted.append((key, identity))
        if norm_doi:
            doi_index[norm_doi] = key
        records.append((key, doi, url, reference))

    return records, source


def _sibling_verify_annots(hl_pdf: str) -> int:
    """同级 ``*_verify.json`` / ``*_verify_hl.json`` 记录的标注数; 无则 0。"""
    for suffix in ("_verify.json", "_verify_hl.json"):
        candidate = hl_pdf.replace("_highlight.pdf", suffix)
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                return int(data.get("n_annots", len(data.get("annotations", []))) or 0)
            except Exception:
                return 0
    return 0


def _count_pdf_annots(pdf_path: str) -> int:
    """用 PyMuPDF 数出 PDF 内真实标注总数; 不可用或异常时返回 0。

    中文目录布局 (``高亮结果/``) 没有伴生 verify.json, 因此以 PDF 内实际
    标注数作为依据, 避免用固定值臆测。
    """
    if fitz is None:
        return 0
    try:
        with fitz.open(pdf_path) as doc:
            return sum(1 for page in doc for _ in (page.annots() or []))
    except Exception:
        return 0


class WorkspaceScanner:
    def __init__(self, db: Optional[TelemetryDB] = None):
        self.db = db or TelemetryDB()

    def scan_project(self, project_dir: str, project_name: Optional[str] = None) -> Dict[str, int]:
        """扫描并解析一个文献项目的产出物，自动录入 Telemetry 数据库。

        两条与"统计要准、要实时"直接相关的规则:

        1. **只看真实产出物**: 备份/临时目录(``_bak_*`` 等)里的副本一律跳过。实测过 RSV 的
           ``_bak_*/高亮结果/`` 被当成成果扫进来, 同一篇文献重复计 3 次(150 篇 vs 实际 50 篇)。
        2. **已收录的条目也刷新**: 原先命中 ``has_*_item`` 就 ``continue``, 于是标注数
           (``num_annots``)与文件大小从此**冻结在首次登记时的值**。现在改为刷新可变字段 ——
           篇数口径不变(刷新≠新增), 但数字会跟着实际产出走。
        """
        if not os.path.exists(project_dir):
            return {"retrieval": 0, "download": 0, "highlight": 0, "refreshed": 0}

        pname = project_name or os.path.basename(os.path.abspath(project_dir))
        stats = {"retrieval": 0, "download": 0, "highlight": 0, "refreshed": 0}

        # 1. 扫描检索产物 (如 _doi_map_full.json, rsv_pdf_inventory.json, rsv_tasks.json)
        doi_map_files = filter_paths(
            glob.glob(os.path.join(project_dir, "*doi_map*.json")) +
            glob.glob(os.path.join(project_dir, "*inventory*.json")))
        seen_retrievals = set()
        for f in doi_map_files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if isinstance(data, dict):
                        for k, v in data.items():
                            if k not in seen_retrievals:
                                seen_retrievals.add(k)
                                url = v if isinstance(v, str) else v.get("url", "")
                                doi = v.get("doi", "") if isinstance(v, dict) else ""
                                
                                # 检查是否已存在
                                if self.db.has_retrieval_item(paper_id=k, doi=doi, url=url):
                                    continue

                                item = RetrievalItem(
                                    paper_id=k,
                                    doi=doi,
                                    url=url,
                                    duration_seconds=12.0,  # 均摊基准
                                    source=os.path.basename(f),
                                )
                                self.db.record_retrieval_item(f"scan_{pname}", item)
                                stats["retrieval"] += 1
            except Exception:
                pass

        # 1b. 扫描「高亮引用清单」折算检索数
        #     口径: 检索数 = 去重后的唯一被引文献数 (与"下载"同为唯一文献口径)
        ref_records, ref_source = _collect_reference_records(project_dir)
        for paper_id, doi, url, reference in ref_records:
            if self.db.has_retrieval_item(paper_id=paper_id, doi=doi, url=url):
                continue
            item = RetrievalItem(
                paper_id=paper_id,
                doi=doi,
                url=url,
                citation_text=reference,
                duration_seconds=RETRIEVAL_SECONDS_PER_PAPER,  # 均摊基准
                source=ref_source or "highlight_ref_list",
            )
            self.db.record_retrieval_item(f"scan_{pname}", item)
            stats["retrieval"] += 1

        # 2. 扫描下载 PDF (如 _2_pdfs/*.pdf 或 根目录下未高亮的 .pdf)
        pdf_files = filter_paths(
            glob.glob(os.path.join(project_dir, "_2_pdfs", "*.pdf")) +
            [p for p in glob.glob(os.path.join(project_dir, "*.pdf"))
             if not p.endswith("_highlight.pdf")])
        seen_pdfs = set()
        for p in pdf_files:
            bname = os.path.basename(p)
            if bname not in seen_pdfs:
                seen_pdfs.add(bname)
                paper_id = bname.split(".")[0].split("_")[0]
                fsize = os.path.getsize(p)

                # 已收录: 刷新文件大小(重新下载后可能变大), 不新增计数
                if self.db.has_download_item(pdf_path=p, paper_id=paper_id):
                    if self.db.refresh_download_item(p, file_size_bytes=fsize):
                        stats["refreshed"] += 1
                    continue

                item = DownloadItem(
                    paper_id=paper_id,
                    pdf_path=p,
                    file_size_bytes=fsize,
                    duration_seconds=8.5,  # 均摊基准
                    success=True,
                    source="scan",
                )
                self.db.record_download_item(f"scan_{pname}", item)
                stats["download"] += 1

        # 3. 扫描 Highlight 成果
        #    命名约定: *_highlight.pdf (TMA) / 高亮结果/*.pdf (RSV 等中文项目)
        hl_pdfs = filter_paths(
            glob.glob(os.path.join(project_dir, "*_highlight.pdf")) +
            glob.glob(os.path.join(project_dir, "_highlight_nested", "*", "*_highlight.pdf")) +
            glob.glob(os.path.join(project_dir, "rsv_hl", "P*", "*_highlight.pdf")) +
            glob.glob(os.path.join(project_dir, HL_DIRNAME, "*.pdf")) +
            glob.glob(os.path.join(project_dir, "*", HL_DIRNAME, "*.pdf")))

        seen_hl = set()
        for hp in hl_pdfs:
            base = os.path.basename(hp)
            if base not in seen_hl:
                seen_hl.add(base)
                paper_id = base.replace("_highlight.pdf", "").replace(".pdf", "")

                # 获取 PDF 文件的真实总页数 (pypdf/fitz/二进制解析)
                pages = get_pdf_page_count(hp)

                # 检查数据库是否已收录该 PDF 文件
                # 同时用 paper_id 兜一层: 文件被移动/改名后, 只按路径匹配会认不出来,
                # 结果是**同一篇文献再加一行**, 篇数虚高。
                if self.db.has_highlight_item(pdf_path=hp, paper_id=paper_id):
                    # 已收录: 刷新页数与标注数(用户在已有 PDF 上继续加标注, 数字要跟上)
                    annots_now = _sibling_verify_annots(hp) or _count_pdf_annots(hp)
                    if self.db.refresh_highlight_item(
                            hp,
                            page_count=pages if pages > 0 else None,
                            num_annots=annots_now if annots_now > 0 else None):
                        stats["refreshed"] += 1
                    continue

                # 标注数: 优先同级 verify.json, 否则数 PDF 内真实标注
                annots = _sibling_verify_annots(hp) or _count_pdf_annots(hp)

                item = HighlightItem(
                    paper_id=paper_id,
                    pdf_path=hp,
                    page_count=pages,
                    num_annots=annots or DEFAULT_ANNOTS,
                    highlight_duration_seconds=25.0,  # 均摊基准
                    correction_duration_seconds=10.0,
                    status="yellow_ok",
                )
                self.db.record_highlight_item(f"scan_{pname}", item)
                stats["highlight"] += 1

        # 仅当扫描到新增项时，登记本次 Scan Task
        if stats["retrieval"] > 0 or stats["download"] > 0 or stats["highlight"] > 0:
            total_time = stats["retrieval"] * 12.0 + stats["download"] * 8.5 + stats["highlight"] * 35.0
            now_iso = datetime.now().isoformat()
            task = TaskRecord(
                task_id=f"scan_{pname}_{int(time.time())}",
                task_type=TaskType.HIGHLIGHT,
                project_name=pname,
                start_time=now_iso,
                end_time=now_iso,
                duration_seconds=total_time,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                status="success",
                extra=stats,
            )
            self.db.record_task(task)

        return stats
