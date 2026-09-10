"""Workspace watcher and output scanner for TraeWork literature projects."""

import glob
import json
import os
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

        # 3. 扫描 Highlight 成果 (*_highlight.pdf, *_verify.json, *_verify_hl.json)
        hl_pdfs = glob.glob(os.path.join(project_dir, "*_highlight.pdf")) + \
                  glob.glob(os.path.join(project_dir, "_highlight_nested", "*", "*_highlight.pdf")) + \
                  glob.glob(os.path.join(project_dir, "rsv_hl", "P*", "*_highlight.pdf"))
        
        seen_hl = set()
        for hp in hl_pdfs:
            base = os.path.basename(hp)
            if base not in seen_hl:
                seen_hl.add(base)
                paper_id = base.replace("_highlight.pdf", "")
                
                # 获取 PDF 文件的真实总页数 (pypdf/fitz/二进制解析)
                pages = get_pdf_page_count(hp)

                # 检查数据库是否已收录该 PDF 文件
                if self.db.has_highlight_item(pdf_path=hp):
                    # 若已收录，更新其真实页数确保一致性
                    self.db.update_highlight_page_count(hp, pages)
                    continue
                
                # 尝试读取同级 verify.json 获取标注数与修正状态
                annots = 0
                verify_json = hp.replace("_highlight.pdf", "_verify.json")
                if not os.path.exists(verify_json):
                    verify_json = hp.replace("_highlight.pdf", "_verify_hl.json")
                if os.path.exists(verify_json):
                    try:
                        with open(verify_json, "r", encoding="utf-8") as vfp:
                            vd = json.load(vfp)
                            annots = vd.get("n_annots", len(vd.get("annotations", [])))
                    except Exception:
                        pass

                item = HighlightItem(
                    paper_id=paper_id,
                    pdf_path=hp,
                    page_count=pages,
                    num_annots=annots or 5,
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
