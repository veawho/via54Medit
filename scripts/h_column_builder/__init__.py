"""
via54Medit H 列构建器 (v9.7 模块化拆分)

模块:
- parse: D/C 列解析
- scan: Pn-x 目录扫描 + 应证评分
- detect: main PDF 错位检测
- links: 链接生成 + 永久性判断
- markdown: markdown 生成 + rich_text 转换

公开 API:
- build_h_md_v6
- build_h_rich_text_v6
- parse_d_field, parse_c_field
- scan_pn_x_dir, calculate_main_score
- detect_main_pdf_mismatch, detect_main_pdf_content_mismatch
- identify_publisher, get_publisher_pdf_urls
- markdown_to_rich_text
"""

from .parse import parse_d_field, parse_c_field
from .scan import (
    scan_pn_x_dir, calculate_main_score, calculate_fallback_score,
    run_light_step2, extract_ppt_data_points_from_c
)
from .detect import (
    detect_main_pdf_mismatch, detect_main_pdf_content_mismatch
)
from .links import (
    identify_publisher, get_publisher_pdf_urls,
    _infer_publisher_label, _infer_fallback_search_link,
    _infer_main_pdf_link, identify_link_eternality
)
from .markdown import (
    markdown_to_rich_text, build_h_md, build_h_md_v6,
    build_h_rich_text, build_h_rich_text_v6
)

__all__ = [
    "parse_d_field", "parse_c_field",
    "scan_pn_x_dir", "calculate_main_score", "calculate_fallback_score",
    "run_light_step2", "extract_ppt_data_points_from_c",
    "detect_main_pdf_mismatch", "detect_main_pdf_content_mismatch",
    "identify_publisher", "get_publisher_pdf_urls",
    "_infer_publisher_label", "_infer_fallback_search_link",
    "_infer_main_pdf_link", "identify_link_eternality",
    "markdown_to_rich_text", "build_h_md", "build_h_md_v6",
    "build_h_rich_text", "build_h_rich_text_v6",
]

__version__ = "9.7"
