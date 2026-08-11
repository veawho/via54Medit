#!/usr/bin/env python3
"""
P4-2 / 全 89 目录 高亮算法 v2.0 (视觉驱动精确标注 + 工作目录承载)
========================================================

输入: PPT 应证内容 (citation_table.csv) + 原 PDF
输出: Pn-x_pageN_citeK_highlight.jpg (DPI=120)

算法 (算法驱动 + 视觉驱动):
1. 解析 citation_table.csv C 列 -> 提取该 Pn-x 在 PPT 中要应证的具体数据
2. PDF 全文搜 keyword + 数字 span -> 只标应证论点对应的 span
3. 截图 DPI=120, 不调 save (避免 #5062 heap corruption)
4. subprocess.run timeout=15s 防卡死, kill orphan
5. 状态持久化到 _literature_citation_index/_state.json (LLM 上下文不爆)

调用: python3 process_pn_x.py [Pn-x|all]
"""

import os, sys, csv, re, json, fitz, subprocess, shutil, time, tempfile
from collections import defaultdict

BASE = '/Users/david/Desktop/雷管方案_文献整理'
CSV = os.path.join(BASE, '_citation_table', 'citation_table.csv')
ARCHIVE = os.path.join(BASE, '_literature_citation_index')
PYTHON = '/Users/david/.hermes/hermes-agent/venv/bin/python3.11'
FALLBACK_MANIFEST = os.path.join(BASE, '_audit_report', '_pn_x_fallback_manifest.json')
FALLBACK_LOG_DIR = os.path.join(BASE, '_audit_report')

# ====== Fallback 触发阈值 (用户在 manifest 中可覆盖) ======
FALLBACK_DEFAULTS = {
    'min_highlights_main': 5,       # Main 标 < 5 处时启用 fallback (单 PDF 难以全面覆盖)
    'min_highlights_total': 8,      # Main+fallback 总标 < 8 时报警
    'check_keywords_in_main': True, # 检查 main 是否命中关键 keyword
    'description': 'Main 标 < min_highlights_main (5) 时启用 fallback, main 越多则越少触发'
}

# ====== 硬规则: _literature_citation_index/ 只能含 Pn-x 目录, 严禁 _state.json / _manifest.json / md5_xxx/ 等杂项 ======
FORBIDDEN_ARCHIVE_FILES = ['_state.json', '_manifest.json', '_state.csv', 'README.md', '.DS_Store']

# ====== 数据过滤规则 (v2.0 视觉驱动精确标注) ======
KEYWORD_BANK = [
    # 流行病学
    'HBV', 'HCV', 'ALD', 'NASH', 'AFP', 'cirrhosis', 'cirrhotic',
    'incidence', 'mortality', 'prevalence', 'cases', 'deaths',
    'globocan', 'iarc', 'who', 'cancer', 'carcinoma',
    # 临床分期
    'BCLC', 'stage A', 'stage B', 'stage C', 'stage D', 'Stage 0',
    'tumor size', 'tumor burden', 'nodules', 'lesion',
    # 治疗
    'sorafenib', 'lenvatinib', 'atezolizumab', 'bevacizumab',
    'tremelimumab', 'durvalumab', 'nivolumab', 'ipilimumab',
    'pembrolizumab', 'cabozantinib', 'regorafenib', 'ramucirumab',
    'TACE', 'TARE', 'RFA', 'PEI', 'resection', 'transplant',
    'chemoembolization', 'ablation', 'systemic',
    # 生存/疗效
    'OS', 'PFS', 'ORR', 'DCR', 'TTP', 'HR', 'median',
    'months', 'year', 'survival', 'follow-up',
    '95% CI', 'confidence',
    # 区域
    'China', 'chinese', 'North America', 'Europe', 'Japan', 'Korea', 'Taiwan',
    'Asia', 'Asian', 'western', 'global', 'worldwide',
    # 队列/研究
    'BRIDGE', 'IMbrave', 'HIMALAYA', 'CheckMate', 'ORIENT',
    'CARES', 'EMERALD', 'LEAP', 'DUBHE', 'TREMENDOUS', 'APOLLO',
    'RATIONALE', 'RESCUE', 'REFLECT', 'SHARP', 'phoenix',
    # GLOBOCAN/数据库特有
    '新发', '死亡', '病例', '肝癌', '中国', '全球', '万',
]

EXCLUDE_SPAN = [
    r'^\s*10\.\d{4,}/',        # DOI
    r'^\s*(?:19|20)\d{2}\s*$',  # 年份
    r'^\s*\d{1,2}\s*$',          # 页码
    r'^\s*[a-z]$',               # 字母
    r'@',                        # email
]


def load_state():
    state_path = os.path.join(BASE, 'scripts', '_state_pn_x.json')
    if os.path.exists(state_path):
        with open(state_path) as f:
            return json.load(f)
    return {'processed': [], 'failed': []}


def save_state(state):
    state_path = os.path.join(BASE, 'scripts', '_state_pn_x.json')
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clean_forbidden_archive_files():
    """清理 ARCHIVE 下的杂项文件 (_state.json / _manifest.json 等)"""
    if not os.path.isdir(ARCHIVE):
        return
    for f in os.listdir(ARCHIVE):
        if f in FORBIDDEN_ARCHIVE_FILES:
            try:
                os.remove(os.path.join(ARCHIVE, f))
            except:
                pass
        # 严禁 md5_xxx/ 嵌套目录
        elif os.path.isdir(os.path.join(ARCHIVE, f)) and (f.startswith('md5_') or f.startswith('_')):
            try:
                shutil.rmtree(os.path.join(ARCHIVE, f))
            except:
                pass


def parse_citation_table_for_pn(pn_x):
    """从 citation_table.csv C 列提取该 Pn-x 应证内容

    v3.3: 深度分析 + 多引用扩展
    - 列出该标号的所有位置和内容 (C列清单)
    - 解析多引用模式 (X,Y) 或 (X-Y), 返回所有相关 Pn-x
    """
    page_num, ref_num = pn_x.replace('P', '').split('-')
    page_num, ref_num = int(page_num), int(ref_num)

    with open(CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    for i, r in enumerate(rows):
        if int(r['PPT页']) == page_num and int(r['第几条']) == ref_num:
            cite_c = r['引用语义（上下文）']
            cite_d = r['PPT中的文献引用 完整字段']

            # v3.3: 深度分析 C 列, 列出该标号的所有位置
            position_summary = extract_position_summary(cite_c)

            # v3.3: 多引用扩展 — 找 (X,Y) 或 (X-Y), 列出所有相关标号
            related_cites = extract_multi_cite_refs(cite_c, cite_d, page_num)

            return {
                'row_index': i + 2,
                'ppt_page': page_num,
                'ref_num': ref_num,
                'main_pdf': r['对应PDF文件'],
                'cite_d': cite_d,
                'cite_c': cite_c,
                'cite_e': r['DOI'],
                'position_summary': position_summary,  # v3.3: 位置清单
                'related_cites': related_cites,  # v3.3: 多引用 Pn-x 列表
            }
    return None


def extract_position_summary(c_text):
    """v3.3: 深度分析 C 列, 列出该标号的所有位置和内容

    Returns:
        list of dict: [{'location': 'P3 左半区域主标题', 'content': '中国肝癌...'}, ...]
    """
    positions = []

    # 解析 "位置1: 「...」(P3 左半区主标题文字框)"
    for m in re.finditer(r'位置\s*(\d+)\s*[:：]\s*[「『"]([^」』"]+)[」』"]\s*\(?([^)\n]*)\)?', c_text):
        idx = int(m.group(1))
        content = m.group(2)
        location = m.group(3).strip(' ()')
        positions.append({
            'index': idx,
            'content': content,
            'location': location,
        })

    # 如果没找到位置模式, 用其他方式提取
    if not positions:
        # 找 "出现在 X 个位置" 中的 X
        m = re.search(r'出现在\s*(\d+)\s*个位置', c_text)
        if m:
            positions.append({
                'index': 1,
                'content': c_text[:150],
                'location': f'{m.group(1)} 个位置 (需手动确认)',
            })

    return positions


def extract_multi_cite_refs(c_text, d_text, page_num):
    """v3.3: 解析多引用模式 (X,Y) 或 (X-Y), 返回所有相关 Pn-x

    v3.3 fix: 即使本 row 没写"多引用", 只要同页其他 row 提到本标号在多引用中,
              也应加入 related_cites

    Returns:
        list of str: ['P5-3', 'P5-4'] (此标号的所有引用对应的 Pn-x)
    """
    related = set()
    ref_num = None

    # 0. 看本 row 是否在 cite_d 中提到自己的标号
    # 例如 P3-1 的 cite_c 是 "单标号", 但 P3-2 cite_c 提到 "多引用 1,2",
    # 那么 P3-1 的 related_cites 应包含 P3-2

    # 1. 本 row 自己的多引用模式
    text = c_text + ' ' + d_text

    # 模式 1: "多引用 X-Y 中" 或 "多引用 X,Y"
    for m in re.finditer(r'多引用[^0-9]*(\d+)\s*[,，/\-]\s*(\d+)', text):
        a, b = int(m.group(1)), int(m.group(2))
        if b - a <= 5:  # 防止匹配年份 (2019-2021)
            for i in range(a, b + 1):
                related.add(f'P{page_num}-{i}')

    # 模式 2: "X,Y 多引用" 或 "X-Y 多引用"
    for m in re.finditer(r'(\d+)\s*[,，/-]\s*(\d+)\s*多引用', text):
        a, b = int(m.group(1)), int(m.group(2))
        if b - a <= 5:
            for i in range(a, b + 1):
                related.add(f'P{page_num}-{i}')

    # 模式 3: "(X,Y)" 或 "(X-Y)" (作为多引用标记)
    for m in re.finditer(r'\((\d+)\s*[,，/-]\s*(\d+)\)', text):
        a, b = int(m.group(1)), int(m.group(2))
        if b - a <= 5:
            for i in range(a, b + 1):
                related.add(f'P{page_num}-{i}')

    # v3.3 fix: 扫描同页所有 row, 找 "多引用 X,Y 中 X 部分" 反向匹配
    # 如果其他 row 说 "多引用 1,2 中 1 部分" / "中 2 部分", 那么标号 1 和 2 共享多引用
    all_pn_in_page = find_all_pn_x_in_page(page_num)
    if not ref_num:
        # 提取自己的标号
        m = re.search(r'PPT标号\s*(\d+)', c_text)
        if m:
            ref_num = int(m.group(1))

    if ref_num:
        for other_pn in all_pn_in_page:
            if other_pn == f'P{page_num}-{ref_num}':
                continue  # 跳过自己
            # 直接读 CSV, 避免递归调用 parse_citation_table_for_pn
            other_info = _read_citation_row(other_pn)
            if not other_info:
                continue
            other_text = other_info.get('cite_c', '') + ' ' + other_info.get('cite_d', '')

            # 找 "多引用 ... 中 N 部分" 或 "多引用 ... 中 N"
            m = re.search(r'多引用\s*(\d+)\s*[,，/]\s*(\d+)\s*中\s*' + str(ref_num) + r'\s*部分', other_text)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if b - a <= 5:
                    for i in range(a, b + 1):
                        related.add(f'P{page_num}-{i}')

    # v3.3 fix: 兜底 — 解析同页所有 row 的 cite_c, 找含多引用模式的标号
    # 如果同页其他 row 的 cite_c 提到 "多引用 X,Y" 且 X 或 Y 覆盖本标号,
    # 那么本标号在多引用里
    # 例如: P4-1 cite_c "多引用 1,2 中 1 部分", P4-2 cite_c "多引用 1-3 中 2 部分"
    # 当处理 P4-3 时 (本标号 3), P4-2 提到 "多引用 1-3 中 2 部分" 含标号 3, 所以 P4-3 也在 [1-3] 中
    for pn in all_pn_in_page:
        other_row = _read_citation_row(pn)
        if not other_row:
            continue
        other_c = other_row.get('cite_c', '') + ' ' + other_row.get('cite_d', '')
        # 从其他 row 的 cite_c 中, 找所有多引用范围, 看是否覆盖本标号
        if not ref_num:
            continue
        # 模式: "多引用 X,Y 中 N 部分" / "多引用 X-Y 中 N 部分" / "多引用 X,Y" / "多引用 X-Y"
        # 解析所有多引用范围
        for m in re.finditer(r'多引用\s*(\d+)\s*[,，/]\s*(\d+)', other_c):
            a, b = int(m.group(1)), int(m.group(2))
            if a <= ref_num <= b:
                # 本标号在多引用范围 [a, b] 内
                for i in range(a, b + 1):
                    related.add(f'P{page_num}-{i}')

    return sorted(related)


def _read_citation_row(pn_x):
    """v3.3: 内部辅助函数, 直接读 CSV 行 (不调用 extract_multi_cite_refs, 避免递归)"""
    page_num, ref_num = pn_x.replace('P', '').split('-')
    page_num, ref_num = int(page_num), int(ref_num)
    with open(CSV, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if int(r['PPT页']) == page_num and int(r['第几条']) == ref_num:
                return {
                    'main_pdf': r['对应PDF文件'],
                    'cite_d': r['PPT中的文献引用 完整字段'],
                    'cite_c': r['引用语义（上下文）'],
                }
    return None


def find_all_pn_x_in_page(page_num):
    """v3.3: 找 page_num 这一页的所有 Pn-x"""
    result = []
    with open(CSV, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if int(r['PPT页']) == page_num:
                result.append(f"P{r['PPT页']}-{r['第几条']}")
    return result


def extract_targets_from_c(c_text):
    """从 C 列提取该标号要应证的具体内容 (PDF 里需要被标的数据点)

    支持 3 种 H 列格式:
    1. "X 应证的内容: - xxx"  (Park BRIDGE)
    2. "关联图表与数据: - 图表 N: ... 中国 42.5%"  (GLOBOCAN)
    3. "需印证数据点 (N 项): 1. ... 2. ..."  (其它)

    v3.2: 智能增强 - 检测 C 列的研究名/期刊名, 自动补充 keywords
    """
    targets = []

    # 格式 1: "X 应证的内容:"
    for m in re.finditer(r'(\d+)\s*应证的内容?[：:]?\s*\(', c_text):
        cite_num = m.group(1)
        start = m.end()
        end = len(c_text)
        for stop_kw in ['位置\d', '注:', '推测', '建议', '---']:
            stop_m = re.search(rf'\n\s*{stop_kw}', c_text[start:])
            if stop_m and start + stop_m.start() < end:
                end = start + stop_m.start()
        chunk = c_text[start:end]
        for line_match in re.finditer(r'^\s*[-•]\s*([^\n]+)', chunk, re.MULTILINE):
            line = line_match.group(1)
            if not re.search(r'\d', line):
                continue
            keywords = extract_keywords_from_line(line)
            keywords = enhance_keywords_with_trial_names(keywords, line, c_text)
            if keywords:
                targets.append({
                    'cite_num': cite_num,
                    'context': line[:120],
                    'keywords': keywords,
                })

    # 格式 2: "关联图表与数据" / "需印证数据点" / "关联数据" / "关联图表" / "视觉关联图表"
    if not targets:
        for m in re.finditer(r'(关联图表与数据|需印证数据点|视觉关联数据|关联数据|视觉关联图表|关联图表)[：:]?', c_text):
            start = m.end()
            end = len(c_text)
            for stop_kw in ['注:', '引文:', '推测', '建议']:
                stop_m = re.search(rf'\n\s*{stop_kw}', c_text[start:])
                if stop_m and start + stop_m.start() < end:
                    end = start + stop_m.start()
            chunk = c_text[start:end]
            # v3.10: 也提取不带 - 前缀的数据行 (如 "14.40% (肝癌/Liver)")
            # 模式 1: 带 - 前缀
            for line_match in re.finditer(r'^\s*[-•]\s*([^\n]+)', chunk, re.MULTILINE):
                line = line_match.group(1)
                if not re.search(r'\d', line):
                    continue
                keywords = extract_keywords_from_line(line)
                keywords = enhance_keywords_with_trial_names(keywords, line, c_text)
                if keywords:
                    targets.append({
                        'cite_num': '?',
                        'context': line[:120],
                        'keywords': keywords,
                    })
            # v3.10: 模式 2 - 提取含百分比+括号的数据行 (如 "14.40% (肝癌/Liver) → 27.90%...")
            for line_match in re.finditer(r'^\s*\d+\.?\d*%[^\n]+', chunk, re.MULTILINE):
                line = line_match.group(0).strip()
                keywords = extract_keywords_from_line(line)
                if keywords:
                    targets.append({
                        'cite_num': '?',
                        'context': line[:120],
                        'keywords': keywords,
                    })

    # 格式 3: "1. xxx 2. yyy" 数字列表
    if not targets:
        for m in re.finditer(r'(?:^|\n)\s*\d+\.\s+([^\n]+)', c_text):
            line = m.group(1)
            if not re.search(r'\d', line):
                continue
            keywords = extract_keywords_from_line(line)
            keywords = enhance_keywords_with_trial_names(keywords, line, c_text)
            if keywords:
                targets.append({
                    'cite_num': '?',
                    'context': line[:120],
                    'keywords': keywords,
                })

    return targets


def enhance_keywords_with_trial_names(keywords, line, full_text):
    """v3.2: 给 keywords 添加研究名, 让中文 C 列 targets 也能在英文 PDF 里命中

    逻辑: 如果 line 或 full_text 含 STRIDE/HIMALAYA/IMbrave/CheckMate 等研究名,
          自动加进 keywords, 这样算法扫描 PDF 时能找到对应的英文研究名
    """
    if not keywords:
        return keywords

    KEY_TRIAL_NAMES = [
        'STRIDE', 'HIMALAYA', 'IMbrave', 'IMbrave150',
        'CheckMate', 'CheckMate-9DW', 'ORIENT', 'ORIENT-32',
        'CARES', 'CARES-310', 'EMERALD', 'LEAP', 'LEAP-002',
        'DUBHE', 'TREMENDOUS', 'APOLLO', 'REFLECT', 'SHARP',
        'BRIDGE', 'RATIONALE', 'RESCUE',
    ]

    line_lower = line.lower()
    full_lower = full_text.lower()

    enhanced = list(keywords)
    for kw in KEY_TRIAL_NAMES:
        kw_lower = kw.lower()
        if (kw_lower in line_lower or kw_lower in full_lower) and kw not in enhanced:
            enhanced.append(kw)

    # 也加英文药物名 (tremelimumab, durvalumab 等)
    KEY_DRUGS = [
        'tremelimumab', 'durvalumab', 'atezolizumab', 'bevacizumab',
        'nivolumab', 'pembrolizumab', 'lenvatinib', 'sorafenib',
        'sintilimab', 'camrelizumab', 'tislelizumab', 'toripalimab',
    ]
    for kw in KEY_DRUGS:
        kw_lower = kw.lower()
        if (kw_lower in line_lower or kw_lower in full_lower) and kw not in enhanced:
            enhanced.append(kw)

    return enhanced if enhanced else keywords


def extract_keywords_from_line(line):
    """从一行提取关键词

    v3.4: 提取任意数字/百分比, 不止 KEYWORD_BANK
    v3.5: 提取中文复合词 (5年生存率, 中国, 肝癌) + 时间 (到2030年)
    """
    keywords = []
    for kw in KEYWORD_BANK:
        if kw.lower() in line.lower():
            keywords.append(kw)

    # v3.4: 提取数字关键词 (百分比, 小数, 整数)
    import re
    # 数字 + % (如 46.6%, 26.3%)
    for m in re.finditer(r'\d+\.?\d*%', line):
        kw = m.group(0)
        if kw not in keywords:
            keywords.append(kw)
    # 小数 (如 46.6, 26.3) — 不含 % (避免重复)
    for m in re.finditer(r'(?<![%\d])\d+\.\d+(?!\d)', line):
        kw = m.group(0)
        if kw not in keywords:
            keywords.append(kw)
    # v3.5: 时间关键词 (到YYYY年, YYYY年)
    for m in re.finditer(r'(?:到|至)?\s*\d{4}\s*年', line):
        kw = m.group(0).strip()
        if kw not in keywords and len(kw) >= 3:
            keywords.append(kw)

    # v3.5: 中文复合词 - 高频关键短语 (中英文)
    CHINESE_PHRASES = [
        '5年生存率', '5年OS率', '5年相对生存率', '生存率',
        '总体癌症', '总体癌症5年生存率', '中国肝癌', '中国 HCC',
        '肝癌', '肝细胞癌', '免疫治疗', '靶向治疗', '免疫联合',
        '中位生存', '无进展生存', '总生存期', '无复发生存',
        '客观缓解率', '疾病控制率', '缓解率',
        '全人群', '中国人群', '亚裔人群', '亚太人群',
        '多中心', '随机对照', '开放标签', '双盲',
        '一线治疗', '二线治疗', '联合治疗',
        '安全性', '不良反应', '不良事件', '副作用',
        '生存数据', '疗效数据', '临床数据',
        '病因学', '流行病学', '生存分析',
    ]
    for phrase in CHINESE_PHRASES:
        if phrase in line and phrase not in keywords:
            keywords.append(phrase)

    return keywords


def make_worker_script():
    """生成 worker 脚本 (写到 tmp, 避免 -c escape 问题)"""
    import textwrap
    WORKER_HIGHLIGHT = textwrap.dedent('''\
        import sys, fitz, os, re, json
        from collections import defaultdict

        pdf_path = sys.argv[1]
        out_dir = sys.argv[2]
        pn = sys.argv[3]
        targets_json = sys.argv[4]

        targets = json.loads(targets_json)
        all_keywords = set()
        for t in targets:
            for kw in t["keywords"]:
                all_keywords.add(kw.lower())

        EXCLUDE = [
            r"^\\s*10\\.\\d{4,}/",
            r"^\\s*(?:19|20)\\d{2}\\s*$",
            r"^\\s*\\d{1,2}\\s*$",
            r"^\\s*[a-z]$",
            r"@",
        ]

        SKIP_PAGE_KEYWORDS = [
            "References", "REFERENCES", "Bibliography", "BIBLIOGRAPHY",
            "Acknowledgements", "ACKNOWLEDGEMENTS", "Acknowledgments",
            "Funding", "FUNDING", "Conflict of interest", "Conflicts of interest",
            "Author contributions", "Data availability",
        ]

        AUTHOR_PATTERN = re.compile(r"^[A-Z]\\.[A-Z]?\\.?\\s*[A-Z]?[a-z]+$|^[A-Z][a-z]+,\\s*[A-Z]\\.?$")

        def is_legend_text(text):
            t = text.strip()
            return bool(re.match(r"^\\d+(?:\\.\\d+)?[–\\-~]\\d+(?:\\.\\d+)?$", t))

        def is_in_image_area(rect, page):
            for img in page.get_image_info():
                img_rect = fitz.Rect(img["bbox"])
                if img_rect.contains(rect): return True
                if rect.intersects(img_rect):
                    inter = rect & img_rect
                    if rect.get_area() > 0 and inter.get_area() / rect.get_area() > 0.7:
                        return True
            return False

        def is_references_page(page):
            """检测是否整页都是 References/致谢/资助 (算法驱动)
            
            返回 True 的条件: 整页 95%+ 都是 References 列表 (无 Abstract)
            返回 False 的条件: 有 Abstract/Results 等正文, 或者是多页 PDF 的 References 页
            """
            text = page.get_text("text")
            if not text: return False

            # 模式 1: 找 References 章节标题位置
            blocks = page.get_text("dict")["blocks"]
            ref_section_y0 = None
            for block in blocks:
                if "lines" not in block: continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        t = span["text"].strip()
                        size = span.get("size", 0)
                        if size < 10: continue
                        if t in ("References", "REFERENCES", "Bibliography", "BIBLIOGRAPHY",
                                 "Acknowledgements", "ACKNOWLEDGEMENTS", "Acknowledgments",
                                 "Author contributions", "AUTHOR CONTRIBUTIONS"):
                            ref_section_y0 = line["bbox"][1]
                            break
                    if ref_section_y0 is not None: break
                if ref_section_y0 is not None: break

            # 模式 2: 找到 References 标题 → 检查标题是否在页面顶部 30% (即整页是 References)
            if ref_section_y0 is not None:
                page_rect = page.rect
                if ref_section_y0 < page_rect.height * 0.3:
                    # References 标题在页面顶部, 整页是 References
                    return True
                else:
                    # References 标题在页面中部, 标题前还有正文 (Abstract 等)
                    return False

            # 模式 3: 没找到 References 标题, 检查整页是否都是编号列表
            top_text = page.get_text("text")[:800]
            has_abstract_marker = any(kw in top_text for kw in [
                "Abstract", "ABSTRACT", "Purpose", "Introduction", 
                "Methods", "Results", "Conclusions", "Discussion",
                "Background", "Patients and Methods"
            ])
            if has_abstract_marker:
                return False

            # 整页都是编号列表 (真正的 References 页)
            ref_count = len(re.findall(r"^\s*\d+\.\s+[A-Z]", text, re.MULTILINE))
            return ref_count >= 10

        def draw_underline(page, rect):
            """画下划线 — 不覆盖文字

            v3.9 fix (二次): 单 line (height < 30) 也改为画 line 底部的 1.5px 细线,
            而不是底部 20% 填充 (会盖住文字下半部)
            """
            r = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block: continue
                for line in block["lines"]:
                    line_bbox = line["bbox"]
                    # 检查 line 是否在 rect 内 (允许 2px 容差)
                    line_y0 = line_bbox[1]
                    line_y1 = line_bbox[3]
                    # y 范围检查
                    if line_y0 < r.y0 - 2 or line_y1 > r.y1 + 2: continue
                    line_x0 = max(line_bbox[0], r.x0)
                    line_x1 = min(line_bbox[2], r.x1)
                    if line_x1 <= line_x0: continue
                    # 画 1.5px 细线 (紧贴 line 底部)
                    bar_h = 1.5
                    bar_rect = fitz.Rect(line_x0, line_y1 - bar_h, line_x1, line_y1)
                    page.draw_rect(bar_rect, color=(1, 0.85, 0), fill=(1, 0.92, 0.15),
                                   width=0.1, overlay=True)

        doc = fitz.open(pdf_path)
        highlights_found = []

        def get_ref_section_y0(page):
            """找到 References 章节标题的 y0 位置 (没找到返回 None)"""
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block: continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        t = span["text"].strip()
                        size = span.get("size", 0)
                        if size < 10: continue
                        if t in ("References", "REFERENCES", "Bibliography", "BIBLIOGRAPHY",
                                 "Acknowledgements", "ACKNOWLEDGEMENTS", "Acknowledgments",
                                 "Author contributions", "AUTHOR CONTRIBUTIONS"):
                            return line["bbox"][1]
            return None

        for pi, page in enumerate(doc):
            if pi >= 12: break
            if is_references_page(page):
                continue
            # 找到 References 标题 y0 (可能 None = 没找到)
            ref_y0 = get_ref_section_y0(page)
            try:
                blocks = page.get_text("dict")["blocks"]
            except:
                continue
            # v3.11: 提取 targets 里的具体数字 (严格数字匹配)
                # targets 里的 keywords 形如 "14.40%", "27.90%", "5年生存率" 等
                # 只匹配这些具体数字, 不匹配其他随机统计数字
                target_specific_numbers = set()
                for t in targets:
                    for kw in t["keywords"]:
                        # 提取数字部分 (如 "14.40%" → "14.40")
                        import re as re_mod
                        for nm in re_mod.findall(r'\d+\.\d+|\d+', kw):
                            if len(nm) >= 2:  # 至少 2 位数字
                                target_specific_numbers.add(nm)
                                # v3.11.1: 标准化 — "14.40" 和 "14.4" 应同时匹配
                                # 去掉末尾 0: "14.40" → "14.4"
                                if '.' in nm:
                                    stripped = nm.rstrip('0').rstrip('.')
                                    if len(stripped) >= 2:
                                        target_specific_numbers.add(stripped)

                for block in blocks:
                    if "lines" not in block: continue
                    # v3.6: 按 line 聚合 — 找到含 kw 的 line, 整 line 划线
                    # v3.7: 语义匹配 — P0 主题词 + 数字
                    # v3.8: 段落级匹配 — 跨多 line 整段划线 (合并 y 间隔连续的 line)
                    # v3.9: 跨 block 段落合并 — 解决一个段落被切成多 block 的情况
                    # v3.11: 严格数字匹配 — 只匹配 targets 里的具体数字, 排除通用统计数字
                    lines = block["lines"]
                    if not lines:
                        continue
                    # v3.12: 按 y 坐标合并同一行的所有 line (PyMuPDF 把表格列拆成单独 line)
                # 同一 y 的 line 应视为同一视觉行
                    merged_y_lines = []
                    cur_y_group = []
                    cur_y = None
                    for li, line in enumerate(lines):
                        line_y = (line["bbox"][1] + line["bbox"][3]) / 2
                        if cur_y is None or abs(line_y - cur_y) < 5:  # 同一 y (5 容差)
                            cur_y_group.append(line)
                            cur_y = line_y if cur_y is None else cur_y
                        else:
                            merged_y_lines.append(cur_y_group)
                            cur_y_group = [line]
                            cur_y = line_y
                    if cur_y_group:
                        merged_y_lines.append(cur_y_group)
    
                    # 在 merged_y_lines 上做匹配 (每个 y 组视为一行)
                    matched_line_indices = []
                    for yi, y_group in enumerate(merged_y_lines):
                        # 合并组内所有 line 的文本
                        group_text = " ".join("".join(s["text"] for s in l.get("spans", [])) for l in y_group)
                        group_text_lower = group_text.lower()
                        # 用第一行的 y 作为组的 y
                        group_y = y_group[0]["bbox"][1]
                        # 跳过 References 标题之后的 line
                        if ref_y0 is not None and group_y > ref_y0:
                            continue
                        # v3.7: 语义匹配 (P0 主题词)
                        P0_CHINESE = ['5年生存率', '5年OS率', '5年相对生存率', '总体癌症', '总体癌症5年生存率',
                                      '中国肝癌', '中国 HCC', '肝癌', '肝细胞癌']
                        P0_CHINESE_PARTIAL = ['5年生', '5年OS', '生存率', '肝癌', '肝细胞癌', '总体癌症']
                        P0_ENGLISH = ['5-year survival', 'overall survival', 'progression-free survival',
                                      'PFS', 'median OS', 'hazard ratio', 'objective response',
                                      'disease control', 'overall survival rate', 'survival rate',
                                      'Liver', 'Esophagus', 'Stomach', 'Colon-rectum', 'Breast',
                                      'Pancreas', 'Lung', 'Gallbladder', 'Larynx', 'Nasopharynx',
                                      'Oral', 'Pharynx', 'cancer']
                        p0_zh = sum(1 for p in P0_CHINESE if p in group_text)
                        p0_zh_part = sum(1 for p in P0_CHINESE_PARTIAL if p in group_text)
                        p0_zh_total = p0_zh + (0.5 if p0_zh_part > 0 else 0)
                        p0_en = sum(1 for p in P0_ENGLISH if p.lower() in group_text_lower)
                        p0_count = p0_zh_total + p0_en
                        # v3.11: 数字必须匹配 targets 里的具体数字
                        import re as re_mod
                        group_numbers = set(re_mod.findall(r'\d+\.\d+|\d+', group_text))
                        has_target_num = bool(group_numbers & target_specific_numbers)
                        has_any_num = bool(re.search(r"\d", group_text))
                        # 匹配条件: P0 ≥ 1 AND (含 target 数字 OR 含 P0 中文复合词本身)
                        p0_full = any(p in group_text for p in P0_CHINESE)
                        if not (p0_count >= 1 and (has_target_num or p0_full) and has_any_num):
                            continue
                        # 把组内所有 line index 加入 matched
                        for l in y_group:
                            for li, orig_line in enumerate(lines):
                                if orig_line is l:
                                    matched_line_indices.append(li)
                                    break
                    if not matched_line_indices:
                    continue
                # v3.9: 跨 block 段落合并 — 找 page 内所有 block, y 间隔 < 18 的相邻 block 都合并
                cur_block_y0 = lines[0]["bbox"][1]
                cur_block_y1 = lines[-1]["bbox"][3]
                merged_blocks = [block]
                # 向上找
                prev_bi = blocks.index(block) - 1
                while prev_bi >= 0:
                    prev_block = blocks[prev_bi]
                    if "lines" not in prev_block: break
                    prev_lines = prev_block["lines"]
                    if not prev_lines: break
                    prev_y1 = prev_lines[-1]["bbox"][3]
                    if cur_block_y0 - prev_y1 < 18:
                        merged_blocks.insert(0, prev_block)
                        cur_block_y0 = prev_lines[0]["bbox"][1]
                        prev_bi -= 1
                    else:
                        break
                # 向下找
                next_bi = blocks.index(block) + 1
                while next_bi < len(blocks):
                    next_block = blocks[next_bi]
                    if "lines" not in next_block: break
                    next_lines = next_block["lines"]
                    if not next_lines: break
                    next_y0 = next_lines[0]["bbox"][1]
                    if next_y0 - cur_block_y1 < 18:
                        merged_blocks.append(next_block)
                        cur_block_y1 = next_lines[-1]["bbox"][3]
                        next_bi += 1
                    else:
                        break
                # 计算合并后的整段 bbox
                all_lines = []
                for mb in merged_blocks:
                    for l in mb["lines"]:
                        all_lines.append(l)
                if not all_lines:
                    continue
                para_x0 = min(l["bbox"][0] for l in all_lines)
                para_y0 = min(l["bbox"][1] for l in all_lines)
                para_x1 = max(l["bbox"][2] for l in all_lines)
                para_y1 = max(l["bbox"][3] for l in all_lines)
                paragraph_rect = fitz.Rect(para_x0, para_y0, para_x1, para_y1)
                # 检查是否在图片区域
                if is_in_image_area(paragraph_rect, page):
                    continue
                # 画整段下划线
                draw_underline(page, paragraph_rect)
                para_text = "".join("".join(s["text"] for s in l.get("spans", [])) for l in all_lines)
                highlights_found.append((pi, paragraph_rect, para_text.strip()[:200]))

            # v3.6: 图表标注 — 找页内含数字的表格/图, 整表/整图画线
            try:
                tables = list(page.find_tables())
                for tbl in tables:
                    tbl_bbox = tbl.bbox
                    # 检查表格内容是否含关键字
                    try:
                        df = tbl.to_pandas()
                        # 表格内容 (合并所有 cell)
                        all_cells = ' '.join(str(v) for row in df.values for v in row if v is not None)
                    except Exception:
                        all_cells = page.get_text("text")
                    cells_lower = all_cells.lower()
                    has_kw_in_table = any(kw in cells_lower for kw in all_keywords)
                    has_num_in_table = bool(re.search(r"\d", all_cells))
                    if not (has_kw_in_table and has_num_in_table):
                        continue
                    # 整表画线 (包围框)
                    table_rect = fitz.Rect(tbl_bbox[0], tbl_bbox[1], tbl_bbox[2], tbl_bbox[3])
                    draw_underline(page, table_rect)
                    highlights_found.append((pi, table_rect, f'[Table] {all_cells[:60]}'))
            except Exception:
                pass

        doc.close()

        doc2 = fitz.open(pdf_path)
        for pi, rect, text in highlights_found:
            page2 = doc2[pi]
            draw_underline(page2, rect)

        page_groups = defaultdict(list)
        for pi, rect, text in highlights_found:
            page_groups[pi].append((rect, text))

        n_imgs = 0
        for pi, items in sorted(page_groups.items()):
            page2 = doc2[pi]
            pix = page2.get_pixmap(dpi=120, colorspace=fitz.csRGB)
            out = os.path.join(out_dir, f"{pn}_page{pi+1}_highlight.jpg")
            pix.save(out)
            n_imgs += 1
        doc2.close()
        print(f"OK n={len(highlights_found)} imgs={n_imgs}")
        ''')
    fd, path = tempfile.mkstemp(suffix='.py', dir='/tmp')
    with os.fdopen(fd, 'w') as f:
        f.write(WORKER_HIGHLIGHT)
    return path


def kill_orphan_workers():
    """kill 残留的 phase python 进程 (排除自身)"""
    my_pid = os.getpid()
    try:
        out = subprocess.run(['ps', '-eo', 'pid,command'],
                           capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if 'process_pn_x' in line or 'phase_v4' in line:
                parts = line.split()
                pid = int(parts[0])
                if pid == my_pid:
                    continue
                try:
                    os.kill(pid, 9)
                except:
                    pass
    except:
        pass


def process_one_pn(pn_x):
    """处理单个 Pn-x 目录 (合并到同 md5 共享目录)

    v3.0 新增: 主文档不足时启用 fallback PDF 流程
    v3.3 新增: 多引用扩展 — 同页多引用标号 (X,Y / X-Y) 的 PDF 一并标注
    """
    info = parse_citation_table_for_pn(pn_x)
    if not info:
        return None, 'NO ROW'

    targets = extract_targets_from_c(info['cite_c'])

    # 关键决策: NO TARGETS 时 fallback 用 PPT 引用的核心数字 + 通用关键词
    # (避免某些 row 的 C 列只描述 "1,2 共享文字" 而无具体内容)
    if not targets:
        targets = extract_fallback_targets(info)

    if not targets:
        return None, 'NO TARGETS (skip)'

    pdf_path = os.path.join(BASE, info['main_pdf'])
    if not os.path.exists(pdf_path):
        return None, f'NO PDF {info["main_pdf"]}'

    # ===== v3.0: 调用 process_with_fallback (含 fallback 逻辑) =====
    out_dir, status, log_data = process_with_fallback(pn_x, info, targets)
    print(status)
    if log_data.get('fallback_used'):
        print(f'  ↳ fallback triggered: {log_data.get("fallback_trigger_reason")}')
        for fb in log_data.get('fallback_attempts', []):
            if fb.get('status') == 'NOT_FOUND':
                print(f'    ✗ NOT_FOUND: {fb["path"]}')
            else:
                hits = fb.get('hits', 0)
                print(f'    → {fb.get("type", "?")} (priority={fb.get("priority")}): {hits} hits')

    # v3.3: 多引用扩展 — 同时标 related_cites 中其他 Pn-x 的 PDF
    related_cites = info.get('related_cites', [])
    multi_cite_results = []
    if related_cites and len(related_cites) > 1:
        print(f'  ↳ 多引用扩展 (related={related_cites}):')
        for sib_pn in related_cites:
            if sib_pn == pn_x:
                continue  # 跳过自己
            sib_info = parse_citation_table_for_pn(sib_pn)
            if not sib_info:
                continue
            sib_pdf = os.path.join(BASE, sib_info['main_pdf'])
            if not os.path.exists(sib_pdf):
                print(f'    ✗ {sib_pn}: PDF 缺失 {sib_info["main_pdf"]}')
                continue
            sib_targets = extract_targets_from_c(sib_info['cite_c'])
            if not sib_targets:
                sib_targets = extract_fallback_targets(sib_info)
            if not sib_targets:
                print(f'    ⚠ {sib_pn}: 无 targets')
                continue
            # 跑 兄弟 PDF, 用 sib_pn 前缀命名截图 (保留同 out_dir)
            try:
                sib_out_dir, sib_status, sib_log = process_with_fallback(sib_pn, sib_info, sib_targets, out_dir=out_dir)
                # 提取 n_main
                sib_n = sib_log.get('main_pdf_hits', 0)
                print(f'    → {sib_pn}: {sib_status} (n={sib_n})')
                multi_cite_results.append({'pn': sib_pn, 'status': sib_status, 'n': sib_n})
                # 保存兄弟 Pn-x 到 processed
                save_processed(sib_pn)
            except Exception as e:
                print(f'    ✗ {sib_pn}: 失败 {e}')

    # 复制截图到兄弟 Pn-x 命名 (主文档截图, 不复制 fallback 截图)
    if 'OK' in status:
        replicate_to_sibling_pn_x(pn_x, out_dir)

    # 写多引用扩展结果到日志
    if multi_cite_results:
        log_path = os.path.join(FALLBACK_LOG_DIR, '_pn_x_fallback_log.json')
        try:
            with open(log_path, encoding='utf-8') as f:
                all_logs = json.load(f)
        except (IOError, json.JSONDecodeError):
            all_logs = {}
        if pn_x in all_logs:
            all_logs[pn_x]['multi_cite_results'] = multi_cite_results
            all_logs[pn_x]['related_cites'] = related_cites
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(all_logs, f, indent=2, ensure_ascii=False)

    return out_dir, status


def replicate_to_sibling_pn_x(pn_x, out_dir):
    """把 pn_x 命名的截图复制到其他共享此 PDF 的 Pn-x 命名前缀

    原理: 同一 md5 共用 1 PDF 时, 所有 Pn-x 看到的"应证内容"在视觉上差异不大
    (PPT 应证内容在多 Pn-x 间常相同), 所以复用截图是合理近似
    """
    main_pdf_name = os.path.basename([f for f in os.listdir(out_dir) if f.endswith('.pdf')][0])
    siblings = compute_siblings_for_pdf_by_name(main_pdf_name, exclude=pn_x)
    if not siblings:
        return
    # 把 pn_x_page*_highlight.jpg 复制为 sib_page*_highlight.jpg
    n_replicated = 0
    for jpg in os.listdir(out_dir):
        if jpg.startswith(pn_x + '_') and jpg.endswith('_highlight.jpg'):
            suffix = jpg[len(pn_x):]
            for sib in siblings:
                sib_path = os.path.join(out_dir, sib + suffix)
                if not os.path.exists(sib_path):
                    import shutil
                    shutil.copy2(os.path.join(out_dir, jpg), sib_path)
                    n_replicated += 1
    if n_replicated:
        print(f'    ↳ replicated {n_replicated} jpgs to {len(siblings)} siblings')


def compute_siblings_for_pdf(pdf_path):
    """找同一 PDF (md5) 的所有共享 Pn-x (不含自身调用者, 用 _by_name 排除)"""
    md5_now = md5_of(pdf_path)
    if not md5_now:
        return []
    return compute_siblings_for_md5(md5_now, exclude=None)


def compute_siblings_for_pdf_by_name(main_pdf_name, exclude=None):
    """根据 PDF 文件名找到兄弟 Pn-x (排除 exclude)"""
    # 看 ARCHIVE 里同名文件, 算 md5
    fpath = None
    for dn in os.listdir(ARCHIVE):
        d = os.path.join(ARCHIVE, dn)
        if not os.path.isdir(d): continue
        if main_pdf_name in os.listdir(d):
            fpath = os.path.join(d, main_pdf_name)
            break
    if not fpath:
        return []
    md5_now = md5_of(fpath)
    if not md5_now:
        return []
    return compute_siblings_for_md5(md5_now, exclude=exclude)


def compute_siblings_for_md5(md5_now, exclude=None):
    """给定 md5, 找所有共享 Pn-x"""
    siblings = []
    with open(CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        pf = r['对应PDF文件']
        if not pf: continue
        full_p = os.path.join(BASE, pf)
        if not os.path.exists(full_p): continue
        m = md5_of(full_p)
        if m == md5_now:
            pn = f"P{r['PPT页']}-{r['第几条']}"
            if exclude is None or pn != exclude:
                siblings.append(pn)
    return siblings


def extract_fallback_targets(info):
    """NO TARGETS 时的兜底: 用 PPT 引用 D 字段的核心术语 + 通用关键词 + 主题启发"""
    fallback = []
    d = info.get('cite_d', '')
    c = info.get('cite_c', '')
    full_text = (d + ' ' + c).lower()

    # 试验代号 (大写字母+数字, e.g. IMbrave150, HIMALAYA, CheckMate-9DW)
    for m in re.finditer(r'\b([A-Z][A-Za-z]+-?\d*[A-Z]*\d*)\b', d):
        kw = m.group(1)
        if len(kw) >= 5 and kw not in ['Liver', 'China', 'Asian', 'Global']:
            fallback.append({
                'cite_num': '?',
                'context': f'Fallback from D-field: {kw}',
                'keywords': [kw],
            })

    # 关键研究名 (强制加入, 即使不在 D 字段中 — HIMALAYA/STRIDE 经常只在 C/PDF 中)
    KEY_TRIAL_NAMES = [
        'STRIDE', 'HIMALAYA', 'IMbrave', 'IMbrave150',
        'CheckMate', 'CheckMate-9DW', 'ORIENT', 'ORIENT-32',
        'CARES', 'CARES-310', 'EMERALD', 'LEAP', 'LEAP-002',
        'DUBHE', 'TREMENDOUS', 'APOLLO', 'REFLECT', 'SHARP',
        'BRIDGE', 'RATIONALE', 'RESCUE',
    ]
    for kw in KEY_TRIAL_NAMES:
        # 在 D 或 C 字段含此研究名 → 加入 keywords
        if kw.lower() in full_text:
            fallback.append({
                'cite_num': '?',
                'context': f'Fallback trial name: {kw}',
                'keywords': [kw],
            })

    # 主题启发 (算法驱动): 根据 C 列主题关键词自动加 PPT 应证关键词
    # 肝脏免疫耐受 (Thomson, Crispe, Doherty 等综述)
    liver_immunity_kw = ['DC', 'Treg', 'IL-10', 'B7-H1', 'TGFβ', 'PD-L1',
                          'Kupffer', 'LSEC', 'stellate', 'tolerance', 'tolerogenic',
                          'liver', 'hepatic', 'sinusoidal', 'LSECs', 'PD-1',
                          'TGF', 'PD1']
    # 肝癌流行病学 (Park, Lin, GLOBOCAN)
    epi_kw = ['HBV', 'HCV', 'BCLC', 'China', 'Korean', 'Japan', 'Asia',
              'incidence', 'mortality', 'GLOBOCAN', 'Asian']
    # 临床试验 (IMbrave, HIMALAYA, CheckMate, CARES 等)
    trial_kw = ['IMbrave', 'HIMALAYA', 'CheckMate', 'ORIENT', 'CARES',
                'EMERALD', 'LEAP', 'DUBHE', 'TREMENDOUS', 'APOLLO',
                'REFLECT', 'RESCUE', 'RATIONALE', 'SHARP',
                'sorafenib', 'lenvatinib', 'atezolizumab', 'bevacizumab',
                'nivolumab', 'pembrolizumab', 'durvalumab', 'tremelimumab',
                'cabozantinib', 'regorafenib', 'ramucirumab']
    # OS/PFS 数据
    outcome_kw = ['OS', 'PFS', 'HR', 'ORR', 'DCR', 'median']

    theme_kw = set()
    # 启发: 看 C 列含哪些主题关键词
    if any(kw in full_text for kw in ['immun', 'tolerance', 'tolerogenic', 't cell', 'liver immune']):
        for kw in liver_immunity_kw: theme_kw.add(kw)
    if any(kw in full_text for kw in ['HBV', 'HCV', 'BCLC', 'incidence', 'mortality',
                                       'epidemiol', 'tumor burden', 'tumor size', 'surveillance']):
        for kw in epi_kw: theme_kw.add(kw)
    if any(kw in full_text for kw in ['trial', 'phase', 'randomized', 'RCT', 'first-line',
                                       'advanced', 'unresectable', 'sorafenib', 'lenvatinib',
                                       'atezolizumab', 'bevacizumab', 'nivolumab']):
        for kw in trial_kw: theme_kw.add(kw)
    if any(kw in full_text for kw in ['survival', 'median', 'months', 'efficacy',
                                       'mOS', 'mPFS', 'HR ', '95% CI']):
        for kw in outcome_kw: theme_kw.add(kw)

    if theme_kw:
        fallback.append({
            'cite_num': '?',
            'context': f'Fallback theme keywords ({len(theme_kw)} kw)',
            'keywords': sorted(theme_kw)[:30],  # 上限 30 个避免 worker 太慢
        })

    # 通用关键词兜底 (中英文 + 研究名 + 药物名)
    for kw in ['OS', 'PFS', 'HR', 'ORR', 'mOS', 'mPFS', 'median', 'survival',
               'sorafenib', 'lenvatinib', 'atezolizumab', 'bevacizumab',
               'nivolumab', 'pembrolizumab', 'durvalumab', 'tremelimumab',
               'HBV', 'HCV', 'BCLC', 'tumor', 'China', 'Japan', 'Korea',
               # 研究名 (短的大写单词, 匹配率高)
               'IMbrave', 'HIMALAYA', 'CheckMate', 'ORIENT', 'CARES',
               'EMERALD', 'LEAP', 'DUBHE', 'TREMENDOUS', 'APOLLO', 'REFLECT',
               'STRIDE', 'SHARP', 'BRIDGE', 'RATIONALE', 'RESCUE',
               # 药物 + 亚组
               'Asian', 'Chinese', 'global', 'subgroup',
               # 中文关键词
               '中国', '亚洲', '全球', '肝癌', '新发', '死亡']:
        if kw.lower() in d.lower():
            fallback.append({
                'cite_num': '?',
                'context': f'Fallback keyword: {kw}',
                'keywords': [kw],
            })
            # 不 break - 收集所有匹配的
    return fallback if fallback else []


def compute_group_dir_name(pdf_path):
    """计算该 PDF 所属合并目录名 (按 CSV row order)"""
    md5 = md5_of(pdf_path)
    with open(CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    # 找所有同 md5 的 Pn-x, 按 CSV row order
    same_md5 = []
    for i, r in enumerate(rows):
        if r['对应PDF文件'] and os.path.exists(os.path.join(BASE, r['对应PDF文件'])):
            if md5_of(os.path.join(BASE, r['对应PDF文件'])) == md5:
                pn = f"P{r['PPT页']}-{r['第几条']}"
                same_md5.append((i, pn))

    same_md5.sort()  # 按 CSV row order
    pns = [x[1] for x in same_md5]
    return '_'.join(pns) if pns else os.path.basename(pdf_path).replace('.pdf', '')


# ====== Fallback 文档处理模块 (v3.0) ======

def load_fallback_manifest():
    """加载 fallback manifest, 不存在则返回空 manifest"""
    if not os.path.exists(FALLBACK_MANIFEST):
        return {
            'schema_version': 'v1',
            'description': 'Pn-x fallback 文档清单',
            'format': {},
            'fallback_triggers': FALLBACK_DEFAULTS,
        }
    try:
        with open(FALLBACK_MANIFEST, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f'  ⚠️  manifest 解析失败: {e}')
        return {'format': {}, 'fallback_triggers': FALLBACK_DEFAULTS}


def load_fallback_pdfs(pn_x):
    """返回该 Pn-x 的 fallback PDF 清单 (按 priority 排序)

    Returns:
        list of dict: [{path, type, priority, source, doi_relation, expected_keywords}, ...]
    """
    manifest = load_fallback_manifest()
    entry = manifest.get('format', {}).get(pn_x, {})
    fallback_pdfs = entry.get('fallback_pdfs', [])
    # 按 priority 排序
    fallback_pdfs = sorted(fallback_pdfs, key=lambda x: x.get('priority', 999))
    return fallback_pdfs


def get_fallback_triggers():
    """读取 fallback 触发阈值 (manifest 优先, 默认兜底)"""
    manifest = load_fallback_manifest()
    triggers = manifest.get('fallback_triggers', FALLBACK_DEFAULTS)
    # 合并默认值 (manifest 中没设的用默认值)
    merged = FALLBACK_DEFAULTS.copy()
    merged.update(triggers)
    return merged


def write_fallback_log(pn_x, log_data):
    """写入 fallback log 到 _fallback_log.json

    Args:
        pn_x: Pn-x 标识
        log_data: dict, 含 main_hits, fallback_attempts, fallback_used, etc.
    """
    log_path = os.path.join(FALLBACK_LOG_DIR, '_pn_x_fallback_log.json')
    all_logs = {}
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding='utf-8') as f:
                all_logs = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    all_logs[pn_x] = log_data
    all_logs['_last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')

    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(all_logs, f, indent=2, ensure_ascii=False)


def write_archive_manifest(out_dir, manifest_data):
    """在 ARCHIVE 目录下写 _manifest.json (记录文档来源)

    Args:
        out_dir: ARCHIVE 下的合并目录
        manifest_data: dict, 含 main_pdf, fallback_pdfs, highlight_summary
    """
    mf_path = os.path.join(out_dir, '_manifest.json')
    with open(mf_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)


def should_use_fallback(main_n_highlights, targets, main_text):
    """判断是否需要启用 fallback

    Args:
        main_n_highlights: main PDF 标的高亮数
        targets: 该 Pn-x 的 keywords 列表
        main_text: main PDF 的纯文本 (用于检查 keywords 命中)

    Returns:
        bool: 是否启用 fallback
    """
    triggers = get_fallback_triggers()
    min_main = triggers.get('min_highlights_main', 3)

    # 主标 0 处, 立即 fallback
    if main_n_highlights == 0:
        return True, 'main_n_highlights == 0'

    # 主标 < min_main, fallback
    if main_n_highlights < min_main:
        return True, f'main_n_highlights ({main_n_highlights}) < min_main ({min_main})'

    # 检查 targets 中关键 keyword 是否在 main 命中 (启发式)
    if triggers.get('check_keywords_in_main', True):
        all_keywords = []
        for t in targets:
            all_keywords.extend(t.get('keywords', []))
        # 至少 30% 的 keywords 命中 main, 否则 fallback
        if all_keywords:
            main_lower = main_text.lower()
            hit_count = sum(1 for kw in all_keywords if kw.lower() in main_lower)
            hit_rate = hit_count / len(all_keywords)
            if hit_rate < 0.3:
                return True, f'keyword hit rate {hit_rate:.0%} < 30% in main'

    return False, f'main sufficient (n={main_n_highlights}, >= min={min_main})'


def process_with_fallback(pn_x, info, targets, out_dir=None):
    """主文档不足时, 启用 fallback PDF 流程

    Args:
        pn_x: Pn-x 标识
        info: parse_citation_table_for_pn 返回的 dict
        targets: 提取的 keywords targets
        out_dir: v3.3 多引用扩展 — 强制输出到指定目录 (避免兄弟 Pn-x 自己建目录)

    Returns:
        tuple: (out_dir, status_string, log_data)
    """
    fallback_pdfs = load_fallback_pdfs(pn_x)
    triggers = get_fallback_triggers()
    min_total = triggers.get('min_highlights_total', 5)

    main_pdf_rel = info['main_pdf']
    main_pdf_path = os.path.join(BASE, main_pdf_rel)

    # 1. 计算合并目录 (按 main md5 + CSV row order)
    # v3.3: 如果传入了 out_dir (多引用扩展), 用传入的
    if out_dir is None:
        out_dir_name = compute_group_dir_name(main_pdf_path)
        out_dir = os.path.join(ARCHIVE, out_dir_name)
    os.makedirs(out_dir, exist_ok=True)

    # 2. 复制 main PDF 到 out_dir (如果还没有)
    main_fname = os.path.basename(main_pdf_path)
    main_dst = os.path.join(out_dir, main_fname)
    if not os.path.exists(main_dst):
        shutil.copy2(main_pdf_path, main_dst)

    # 3. 清旧 highlight (保留兄弟 Pn-x 的截图)
    siblings = compute_siblings_for_pdf(main_pdf_path)
    keep_prefixes = siblings + [pn_x] + [f'{pn_x}_fb']  # 保留 fallback 命名的截图
    for f in os.listdir(out_dir):
        if not (f.endswith('_highlight.jpg') or f.endswith('_overview.jpg')):
            continue
        # 检查是否属于兄弟 Pn-x (应该保留)
        is_sibling = any(f.startswith(p + '_') for p in keep_prefixes)
        if not is_sibling:
            os.remove(os.path.join(out_dir, f))

    # 4. 跑 main PDF
    worker_path = make_worker_script()

    # v3.2: 保留历史 _retries (避免被覆盖)
    existing_log = {}
    log_path = os.path.join(FALLBACK_LOG_DIR, '_pn_x_fallback_log.json')
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding='utf-8') as f:
                existing_log = json.load(f)
            if pn_x in existing_log and isinstance(existing_log.get(pn_x), dict):
                prev_retries = existing_log[pn_x].get('_retries', 0)
            else:
                prev_retries = 0
        except (json.JSONDecodeError, IOError):
            prev_retries = 0
    else:
        prev_retries = 0

    log_data = {
        'pn_x': pn_x,
        'main_pdf': main_pdf_rel,
        'fallback_attempts': [],
        'fallback_used': False,
        'fallback_pdf_hits': 0,
        'main_pdf_hits': 0,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        '_retries': prev_retries,  # 保留
    }

    try:
        res = subprocess.run(
            [PYTHON, worker_path, main_pdf_path, out_dir, pn_x, json.dumps(targets, ensure_ascii=False)],
            capture_output=True, text=True, timeout=60
        )
        out = res.stdout.strip()
        main_n = 0
        m = re.search(r'n=(\d+)', out)
        if m:
            main_n = int(m.group(1))
        log_data['main_pdf_hits'] = main_n
        log_data['main_stdout'] = out
        log_data['main_stderr'] = res.stderr[:200] if res.stderr else ''
    except subprocess.TimeoutExpired:
        log_data['main_stdout'] = 'TIMEOUT'
        main_n = 0
    except Exception as e:
        log_data['main_stdout'] = f'ERR: {e}'
        main_n = 0
    finally:
        try:
            os.remove(worker_path)
        except:
            pass

    # 5. 提取 main 全文检查 keywords
    main_text = ''
    try:
        d = fitz.open(main_pdf_path)
        for p in d:
            main_text += p.get_text()
        d.close()
    except:
        pass

    # 6. 决定是否启用 fallback
    need_fallback, reason = should_use_fallback(main_n, targets, main_text)
    log_data['fallback_trigger_reason'] = reason
    log_data['fallback_triggered'] = need_fallback

    # 7. 如启用 fallback, 依次尝试每个 fallback PDF
    if need_fallback and fallback_pdfs:
        log_data['fallback_used'] = True
        for fb in fallback_pdfs:
            fb_path_rel = fb['path']
            fb_path = os.path.join(BASE, fb_path_rel)
            if not os.path.exists(fb_path):
                log_data['fallback_attempts'].append({
                    'path': fb_path_rel, 'status': 'NOT_FOUND'
                })
                continue

            # 复制 fallback PDF 到 out_dir
            fb_fname = os.path.basename(fb_path)
            fb_dst = os.path.join(out_dir, fb_fname)
            if not os.path.exists(fb_dst):
                shutil.copy2(fb_path, fb_dst)

            # fb_short_name: 把 P5-13_supp_methods_s1.pdf 简化为 supp_methods_s1
            # 用于输出命名: P5-13_fb_supp_methods_s1_page1_highlight.jpg
            fb_short = fb_fname.replace(f'{pn_x}_', '').replace('.pdf', '')
            fb_prefix = f'{pn_x}_fb_{fb_short}'
            log_data['fallback_attempts'].append({
                'path': fb_path_rel,
                'type': fb.get('type'),
                'priority': fb.get('priority'),
                'status': 'PROCESSING',
                'fb_prefix': fb_prefix,
            })

            worker_path = make_worker_script()
            try:
                # worker 参数: pdf, out_dir, pn_x, targets_json, fb_prefix
                res = subprocess.run(
                    [PYTHON, worker_path, fb_path, out_dir, fb_prefix, json.dumps(targets, ensure_ascii=False)],
                    capture_output=True, text=True, timeout=60
                )
                fb_out = res.stdout.strip()
                fb_n = 0
                m = re.search(r'n=(\d+)', fb_out)
                if m:
                    fb_n = int(m.group(1))
                log_data['fallback_attempts'][-1]['stdout'] = fb_out
                log_data['fallback_attempts'][-1]['hits'] = fb_n
                log_data['fallback_pdf_hits'] += fb_n
            except subprocess.TimeoutExpired:
                log_data['fallback_attempts'][-1]['stdout'] = 'TIMEOUT'
            except Exception as e:
                log_data['fallback_attempts'][-1]['stdout'] = f'ERR: {e}'
            finally:
                try:
                    os.remove(worker_path)
                except:
                    pass

    # 8. 计算总标
    total = log_data['main_pdf_hits'] + log_data['fallback_pdf_hits']
    log_data['total_hits'] = total

    if total < min_total:
        log_data['warning'] = f'total_hits ({total}) < min_total ({min_total})'
        # v3.2: 累计 _retries, 达到 2 后永久跳过
        log_data['_retries'] = prev_retries + 1
        status = f'OK n_main={main_n} n_fb={log_data["fallback_pdf_hits"]} total={total} WARN'
        # 修正: WARN 也算成功, 但记录 warning
    else:
        status = f'OK n_main={main_n} n_fb={log_data["fallback_pdf_hits"]} total={total}'

    # 9. 写 fallback log
    write_fallback_log(pn_x, log_data)

    # 10. 写 ARCHIVE manifest
    manifest_data = {
        'pn_x': pn_x,
        'main_pdf': main_pdf_rel,
        'fallback_pdfs': [
            {'path': fb['path'], 'type': fb.get('type'), 'priority': fb.get('priority')}
            for fb in fallback_pdfs
        ],
        'highlight_summary': {
            'main_pdf_hits': log_data['main_pdf_hits'],
            'fallback_pdf_hits': log_data['fallback_pdf_hits'],
            'total': total,
        },
        'fallback_triggered': log_data['fallback_triggered'],
        'fallback_trigger_reason': log_data['fallback_trigger_reason'],
        'last_processed': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    write_archive_manifest(out_dir, manifest_data)

    return out_dir, status, log_data


def md5_of(p):
    import hashlib
    try:
        with open(p, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None


def process_all(batch_size=10):
    """批量处理所有 Pn-x"""
    with open(CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    pns = [f"P{r['PPT页']}-{r['第几条']}" for r in rows]
    state = load_state()
    done = set(state.get('processed', []))

    clean_forbidden_archive_files()  # 启动时清理杂项

    todo = [pn for pn in pns if pn not in done]
    print(f'待办: {len(todo)} Pn-x (已完成: {len(done)})', flush=True)

    kill_orphan_workers()

    for i, pn in enumerate(todo):
        out_dir, status = process_one_pn(pn)
        if status and status.startswith('OK'):
            state.setdefault('processed', []).append(pn)
            save_state(state)
            print(f'  [{i+1}/{len(todo)}] {pn}: {status}', flush=True)
        else:
            state.setdefault('failed', []).append({'pn': pn, 'reason': status})
            save_state(state)
            print(f'  [{i+1}/{len(todo)}] {pn}: {status}', flush=True)

        # batch pause 防卡
        if (i + 1) % batch_size == 0:
            print(f'  batch done ({i+1}/{len(todo)}), pause 2s', flush=True)
            time.sleep(2)

    print(f'\n=== 完成 ===')
    print(f'成功: {len(state.get("processed", []))}')
    print(f'失败: {len(state.get("failed", []))}')
    return state


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: process_pn_x.py Pn-x|all')
        sys.exit(1)

    arg = sys.argv[1]
    if arg == 'all':
        process_all()
    else:
        out_dir, status = process_one_pn(arg)
        print(f'{arg}: {status}')
        if status == 'NO TARGETS':
            # 打印 H 段方便 debug
            info = parse_citation_table_for_pn(arg)
            print('---')
            print(info['cite_c'][:300])