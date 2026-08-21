# 工具注册表 (via54_skill_tool_registry.py)

每个 skill 的对外函数入口, 任何 agent 加载 skill 后必须用这里列的工具, 不准自己重写。

## 注册表来源

```python
from via54_skill_tool_registry import get_skill_tools, list_skills

# 列出所有 skill
print(list_skills())
# ['via54-citation-resolver-v3', 'via54-glm-official', ...]

# 拿某个 skill 的对外函数
tools = get_skill_tools('via54-citation-resolver-v3')
print(tools)
# ['parse_citation', 'resolve_citations', 'download_via_l0', ...]
```

## via54-citation-resolver-v3 工具

```python
# 解析 citation 字符串 → 拿 DOI/PMID/journal/year
parse_citation('Luzzatto L, et al. Br J Haematol. 2020;191(4):579-586')
# → {'first_author': 'Luzzatto', 'journal': 'Br J Haematol', 'year': '2020'}

# 解析多个 citation
parse_citations(['citation1', 'citation2'])

# NCBI E-utilities 解析
resolve_citations_ncbi(parse_result)
# → fetch_plan_corrected.json

# GLM 反向推理真实 DOI
glm_resolve_correct(citation, wrong_doi)
```

## via54-glm-official 工具

```python
# 9 项智谱官方能力 1:1 复刻
extract_pdf_text(client, pdf_path)  # file-extract API
extract_docx_text(client, docx_path)
extract_pptx_text(client, pptx_path)
extract_image(client, image_path)
official_process_file(client, pdf_path, prompt)
official_batch_process(client, paths, prompt)
apply_prompt_template(template_name, text)  # 6 个 prompt 模板
```

## 文献下载工具 (cdp_scihub_via_chrome.py)

```python
# 单条下载
from cdp_scihub_via_chrome import download_one_scihub
pn, src, path = download_one_scihub(pn, doi, out_dir)
# src ∈ {'cached', 'unpaywall', 'scihub_sci-hub.sg', 'failed', 'no_doi'}

# 批量 (后台)
python3 cdp_scihub_via_chrome.py <plan_json> <out_dir> <start> <end>

# 通过 sandbox_forbidden wrapper (推荐)
from via54_sandbox_forbidden import download_via_chrome_scihub
pn, src, path = download_via_chrome_scihub(pn='P3-2', doi='10.1111/bjh.17147', out_dir='/path/')
```

## GLM 校验工具 (batch_verify_pdfs.py)

```python
from batch_verify_pdfs import verify_one

result = verify_one(
    pdf_path='/path/to/P3-2.pdf',
    pn='P3-2',
    citation='Luzzatto L, et al. Br J Haematol. 2020...',
    doi='10.1111/bjh.17147'
)
# → {'pn': 'P3-2', 'matches': True, 'score': 95, 'reason': '...'}

# 批量
python3 batch_verify_pdfs.py --pdf-dir /path --plan /path/fetch_plan.json
# → _verify_report.json
```

## Europe PMC 解析 (resolve_correct_doi_v2.py)

```python
from resolve_correct_doi_v2 import search_europe_pmc

candidates, status = search_europe_pmc('Jodele Blood 2014')
# → [{'pmid': '...', 'doi': '10.xxxx', 'title': '...', ...}], 'ok'
```

## citation_resolver 工具 (via54-citation-resolver-v3/scripts/)

```python
# parse_citations.py
parse_citations(['Jodele S, et al. Blood. 2014;123(13):2071-2079', ...])
# → [{'pn': 'P25-1', 'citation': '...', 'doi': '10.xxxx', 'pmid': '...'}]

# download_via_l0 (4 级 fallback)
download_via_l0(pn, doi, pmid, citation, out_dir)
# 策略: Unpaywall → Sci-Hub → Crossref → Google
```

## via54-highlight-strict 工具

```python
# glm_literature_processor.py (v2.0)
process_literature(pdf_path, evidence_json)
# → 黄线 highlight PDF

# evidence-driven-bulk-pdf-highlight
batch_highlight(pn_dir)
# → {Pn-x}_highlight.pdf
```

## 经验教训

**用户已暴怒强调 5+ 次**: 不要自己重写这些函数。**每次自己重写都浪费 30+ 分钟 + 全部下错**。

正确流程:
1. `skills_list()` 看有哪些 skill 可用
2. `skill_view('skill-name')` 读 SKILL.md 找入口
3. `get_skill_tools('skill-name')` 拿对外函数
4. 直接 import + 调用
5. 缺什么工具再 patch skill (不是 patch 我的代码)