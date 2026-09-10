import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any

from .db import TelemetryDB
from .models import AggregateReport
from .pdf_utils import get_pdf_page_count


# 人工基准基线 (秒)
MANUAL_RETRIEVAL_SECONDS_PER_PAPER = 7 * 60.0   # 人工平均 7 分钟检索 1 篇
MANUAL_DOWNLOAD_SECONDS_PER_PAPER = 2 * 60.0    # 人工平均 2 分钟下载 1 篇
MANUAL_HIGHLIGHT_SECONDS_PER_PAPER = 4 * 60.0   # 人工平均 4 分钟高亮 1 篇


class TelemetryAggregator:
    def __init__(self, db: Optional[TelemetryDB] = None):
        self.db = db or TelemetryDB()

    def _calc_metrics(self, start_iso: Optional[str], end_iso: Optional[str], 
                      period_type: str, period_name: str) -> AggregateReport:
        # 1. 检索数据 (按独立文献去重: 同一文献计为 1 篇)
        retrieval_rows = self.db.query_retrievals(start_iso, end_iso)
        distinct_retrievals: Dict[str, float] = {}
        for r in retrieval_rows:
            doi = (r["doi"] or "").strip().lower()
            url = (r["url"] or "").strip().lower()
            paper_id = (r["paper_id"] or "").strip().lower()
            key = doi or url or paper_id
            dur = float(r["duration_seconds"] or 0.0)
            if key not in distinct_retrievals:
                distinct_retrievals[key] = dur
            else:
                distinct_retrievals[key] = min(distinct_retrievals[key], dur)

        r_count = len(distinct_retrievals)
        r_duration = sum(distinct_retrievals.values())
        r_avg = (r_duration / r_count) if r_count > 0 else 0.0
        r_saved = max(0.0, (r_count * MANUAL_RETRIEVAL_SECONDS_PER_PAPER) - r_duration)

        # 2. 下载数据 (仅统计成功下载，且按独立 PDF 文献文件去重)
        download_rows = self.db.query_downloads(start_iso, end_iso)
        successful_downloads = [d for d in download_rows if d["success"]]
        distinct_downloads: Dict[str, float] = {}
        for d in successful_downloads:
            path = (d["pdf_path"] or "").strip()
            if path:
                key = os.path.normcase(os.path.abspath(path))
            elif d["doi"]:
                key = d["doi"].strip().lower()
            else:
                key = (d["paper_id"] or "").strip().lower()
            
            dur = float(d["duration_seconds"] or 0.0)
            if key not in distinct_downloads:
                distinct_downloads[key] = dur
            else:
                distinct_downloads[key] = min(distinct_downloads[key], dur)

        d_count = len(distinct_downloads)
        d_duration = sum(distinct_downloads.values())
        d_avg = (d_duration / d_count) if d_count > 0 else 0.0
        d_saved = max(0.0, (d_count * MANUAL_DOWNLOAD_SECONDS_PER_PAPER) - d_duration)

        # 3. 高亮标注与质检数据
        # 严格遵守：
        # • 完成标注多少篇：对应多少个经历过 highlight 操作的独立 PDF 文献文件
        # • 阅读页数多少页：对应所有经历过 highlight 操作的 PDF 文献文件的页数总和
        highlight_rows = self.db.query_highlights(start_iso, end_iso)
        distinct_hl_pdfs: Dict[str, Dict[str, Any]] = {}
        for h in highlight_rows:
            path = (h["pdf_path"] or "").strip()
            if path:
                key = os.path.normcase(os.path.abspath(path))
            else:
                key = (h["paper_id"] or "").strip().lower()

            pages = int(h["page_count"] or 0)
            # 若记录中页数异常或缺失，且本地存在该 PDF 文件，实时提取其真实总页数
            if pages <= 1 and path and os.path.exists(path):
                real_p = get_pdf_page_count(path)
                if real_p > 0:
                    pages = real_p

            hl_dur = float(h["highlight_duration_seconds"] or 0.0)
            corr_dur = float(h["correction_duration_seconds"] or 0.0)

            if key not in distinct_hl_pdfs:
                distinct_hl_pdfs[key] = {
                    "paper_id": h["paper_id"],
                    "pdf_path": path,
                    "page_count": pages,
                    "highlight_duration_seconds": hl_dur,
                    "correction_duration_seconds": corr_dur,
                }
            else:
                # 保留最大真实页数
                if pages > distinct_hl_pdfs[key]["page_count"]:
                    distinct_hl_pdfs[key]["page_count"] = pages
                distinct_hl_pdfs[key]["highlight_duration_seconds"] = max(distinct_hl_pdfs[key]["highlight_duration_seconds"], hl_dur)
                distinct_hl_pdfs[key]["correction_duration_seconds"] = max(distinct_hl_pdfs[key]["correction_duration_seconds"], corr_dur)

        hl_count = len(distinct_hl_pdfs)
        hl_pages = sum(item["page_count"] for item in distinct_hl_pdfs.values())
        hl_duration = sum(item["highlight_duration_seconds"] for item in distinct_hl_pdfs.values())
        hl_avg = (hl_duration / hl_count) if hl_count > 0 else 0.0
        corr_duration = sum(item["correction_duration_seconds"] for item in distinct_hl_pdfs.values())
        corr_avg = (corr_duration / hl_count) if hl_count > 0 else 0.0
        hl_saved = max(0.0, (hl_count * MANUAL_HIGHLIGHT_SECONDS_PER_PAPER) - (hl_duration + corr_duration))

        # 4. Token 资源消耗统计
        # 严格遵守用户指示：默认与服务商控制台实现 100% 绝对一致 (token_mode="exact")
        token_mode = "exact"
        try:
            from .config import load_config
            cfg = load_config()
            token_mode = cfg.get("telemetry", {}).get("token_mode", "exact")
        except Exception:
            pass

        task_rows = self.db.query_tasks(start_iso, end_iso)
        llm_logs = self.db.query_llm_tokens(start_iso, end_iso)
        llm_call_count = len(llm_logs)

        if token_mode == "exact":
            # 100% 真实对齐：仅汇总真实 LLM 网关响应的 Token 日志，排除任何文件扫描时的估算
            prompt_tokens = sum(int(l["prompt_tokens"]) for l in llm_logs)
            completion_tokens = sum(int(l["completion_tokens"]) for l in llm_logs)
            total_tokens = sum(int(l["total_tokens"]) for l in llm_logs)

            # 叠加由 Python 运行时探针 (track_highlight 等) 明确传入真实 usage 的任务
            for t in task_rows:
                if not str(t["task_id"]).startswith("scan_"):
                    prompt_tokens += int(t["prompt_tokens"])
                    completion_tokens += int(t["completion_tokens"])
                    total_tokens += int(t["total_tokens"])
                    if int(t["total_tokens"]) > 0:
                        llm_call_count += 1
        else:
            # 仅在非默认的 estimated 模式下才汇总历史任务估算
            prompt_tokens = sum(int(t["prompt_tokens"]) for t in task_rows)
            completion_tokens = sum(int(t["completion_tokens"]) for t in task_rows)
            total_tokens = sum(int(t["total_tokens"]) for t in task_rows)

        # 5. 总工时收益
        total_saved_sec = r_saved + d_saved + hl_saved
        total_saved_hrs = total_saved_sec / 3600.0

        report = AggregateReport(
            period_type=period_type,
            period_name=period_name,
            start_date=start_iso or "历史至今",
            end_date=end_iso or datetime.now().isoformat(),
            retrieval_count=r_count,
            retrieval_duration_seconds=r_duration,
            retrieval_avg_seconds=r_avg,
            retrieval_saved_seconds=r_saved,
            download_count=d_count,
            download_duration_seconds=d_duration,
            download_avg_seconds=d_avg,
            download_saved_seconds=d_saved,
            highlight_pages=hl_pages,
            highlight_count=hl_count,
            highlight_duration_seconds=hl_duration,
            highlight_avg_seconds=hl_avg,
            correction_duration_seconds=corr_duration,
            correction_avg_seconds=corr_avg,
            highlight_saved_seconds=hl_saved,
            total_saved_seconds=total_saved_sec,
            total_saved_hours=total_saved_hrs,
            total_prompt_tokens=prompt_tokens,
            total_completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            token_mode=token_mode,
            llm_call_count=llm_call_count,
        )
        return report

    def get_weekly_report(self, ref_date: Optional[datetime] = None) -> AggregateReport:
        """获取当前自然周（周一 00:00:00 至 周日 23:59:59）的聚合数据。"""
        dt = ref_date or datetime.now()
        start_of_week = dt - timedelta(days=dt.weekday())
        start_dt = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        iso_year, iso_week, _ = dt.isocalendar()
        period_name = f"{iso_year}年 第{iso_week:02d}周"

        return self._calc_metrics(
            start_iso=start_dt.isoformat(),
            end_iso=end_dt.isoformat(),
            period_type="weekly",
            period_name=period_name,
        )

    def get_monthly_report(self, ref_date: Optional[datetime] = None) -> AggregateReport:
        """获取当前自然月的聚合数据，并附带历史累计数据。"""
        dt = ref_date or datetime.now()
        start_dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # 下个月的第1天减1秒
        if start_dt.month == 12:
            next_month = start_dt.replace(year=start_dt.year + 1, month=1)
        else:
            next_month = start_dt.replace(month=start_dt.month + 1)
        end_dt = next_month - timedelta(seconds=1)

        period_name = f"{dt.year}年{dt.month:02d}月"
        report = self._calc_metrics(
            start_iso=start_dt.isoformat(),
            end_iso=end_dt.isoformat(),
            period_type="monthly",
            period_name=period_name,
        )
        # 附加历史累计
        report.historical_cumulative = self.get_all_time_report()
        return report

    def get_all_time_report(self) -> AggregateReport:
        """获取从系统初始化以来的历史累计成绩。"""
        return self._calc_metrics(
            start_iso=None,
            end_iso=None,
            period_type="all_time",
            period_name="历史累计总战报",
        )
