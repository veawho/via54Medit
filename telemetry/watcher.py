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
    import fitz  # PyMuPDF
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


def _norm_ref(text: str) -> str:
    """文献引用串归一化, 用于去重 (忽略大小写与各类空白)。"""
    return re.sub(r"[\s\u3000]+", "", text or "").casefold()


def _collect_reference_records(project_dir: str):
    """从「高亮引用清单」读取被引文献, 按文献去重。

    指标口径: 检索数 = 去重后的唯一被引文献数 (与"下载"指标同为唯一文献口径,
    重复引用同一篇文献只计一次)。

    数据源优先级:
      1. ``高亮结果/*_meta.json`` —— 每 Pn-x 一条, reference_field 完整, 并可能带 doi/pmid;
      2. ``高亮结果清单.tsv`` —— meta 缺失时回退。注意该 TSV 的 reference_field
         可能被导出截断, 故仅在无 meta 时使用。

    返回 ``(records, source)``; records 为 ``(paper_id, doi, url, citation_text)`` 列表。
    """
    records: Dict[str, tuple] = {}
    source = ""

    for meta_path in sorted(glob.glob(os.path.join(project_dir, HL_META_GLOB))):
        try:
            with open(meta_path, "r", encoding="utf-8") as fp:
                meta = json.load(fp)
        except Exception:
            continue
        reference = (meta.get("reference_field") or "").strip()
        doi = (meta.get("doi") or "").strip()
        pmid = (meta.get("pmid") or "").strip()
        key = _norm_ref(doi) or _norm_ref(reference)
        if not key:
            continue
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        records.setdefault(key, (key, doi, url, reference))

    if records:
        return list(records.values()), f"{HL_DIRNAME}/*_meta.json"

    tsv_path = os.path.join(project_dir, HL_LIST_TSV)
    if os.path.exists(tsv_path):
        try:
            with open(tsv_path, "r", encoding="utf-8") as fp:
                for row in csv.DictReader(fp, delimiter="\t"):
                    reference = (row.get("reference_field") or row.get("reference") or "").strip()
                    key = _norm_ref(reference)
                    if not key:
                        continue
                    records.setdefault(key, (key, "", "", reference))
            source = os.path.basename(tsv_path)
        except Exception:
            pass

    return list(records.values()), source


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
        """扫描并解析一个文献项目的产出物，自动录入 Telemetry 数据库。"""
        if not os.path.exists(project_dir):
            return {"retrieval": 0, "download": 0, "highlight": 0}

        pname = project_name or os.path.basename(os.path.abspath(project_dir))
        stats = {"retrieval": 0, "download": 0, "highlight": 0}

        # 1. 扫描检索产物 (如 _doi_map_full.json, rsv_pdf_inventory.json, rsv_tasks.json)
        doi_map_files = glob.glob(os.path.join(project_dir, "*doi_map*.json")) + \
                        glob.glob(os.path.join(project_dir, "*inventory*.json"))
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
        pdf_files = glob.glob(os.path.join(project_dir, "_2_pdfs", "*.pdf")) + \
                    [p for p in glob.glob(os.path.join(project_dir, "*.pdf")) if not p.endswith("_highlight.pdf")]
        seen_pdfs = set()
        for p in pdf_files:
            bname = os.path.basename(p)
            if bname not in seen_pdfs:
                seen_pdfs.add(bname)
                # 检查是否已存在
                if self.db.has_download_item(pdf_path=p, paper_id=bname.split(".")[0].split("_")[0]):
                    continue

                fsize = os.path.getsize(p)
                paper_id = bname.split(".")[0].split("_")[0]
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
        hl_pdfs = glob.glob(os.path.join(project_dir, "*_highlight.pdf")) + \
                  glob.glob(os.path.join(project_dir, "_highlight_nested", "*", "*_highlight.pdf")) + \
                  glob.glob(os.path.join(project_dir, "rsv_hl", "P*", "*_highlight.pdf")) + \
                  glob.glob(os.path.join(project_dir, HL_DIRNAME, "*.pdf")) + \
                  glob.glob(os.path.join(project_dir, "*", HL_DIRNAME, "*.pdf"))

        seen_hl = set()
        for hp in hl_pdfs:
            base = os.path.basename(hp)
            if base not in seen_hl:
                seen_hl.add(base)
                paper_id = base.replace("_highlight.pdf", "").replace(".pdf", "")

                # 获取 PDF 文件的真实总页数 (pypdf/fitz/二进制解析)
                pages = get_pdf_page_count(hp)

                # 检查数据库是否已收录该 PDF 文件
                if self.db.has_highlight_item(pdf_path=hp):
                    # 若已收录，更新其真实页数确保一致性
                    self.db.update_highlight_page_count(hp, pages)
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
