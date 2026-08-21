# GLM 模型使用规范 (2026-08-07 用户硬规则)

用户原话: "确保所有文献整理相关的执行, 都是走 glm-4-flash"

## 唯一入口

```python
from glm_model_default import call_glm_lit

result = call_glm_lit(prompt, max_tokens=2000)
# 自动:
#   - API key 从 ~/.hermes/.env (GLM_API_KEY)
#   - base_url: https://open.bigmodel.cn/api/paas/v4
#   - model: glm-4-flash-250414 (智谱官方免费)
#   - 限流重试: 429/1302/1305 → 5s/10s/15s 退避
#   - 违规检测: assert_lit_model() 自动抛 AssertionError
```

## 严禁使用

| 模型 | 原因 |
|------|------|
| glm-4.7-flash | 限流严重, 经常返回 "too many requests" |
| glm-4.5-air | 余额不足, 调一次扣一次钱 |
| glm-5 (主 Agent 默认) | 文献整理不是主对话, 切到 glm-4-flash |
| GPT-4 / Claude / 其他 | 收费, 用户已禁止 |

## 自动拦截

```python
# glm_model_default.py 里:
def assert_lit_model(model):
    if model != 'glm-4-flash-250414':
        raise AssertionError(f'文献整理必须用 glm-4-flash-250414, 你用了 {model}')

# 调用时自动:
def call_glm_lit(prompt, model='glm-4-flash-250414', ...):
    assert_lit_model(model)
    ...
```

## 性能数据 (实测)

- file-extract API: 18490 字符 PDF 提取 0.4s
- glm-4-flash-250414 单 query: 14.3s/篇
- 成本: ¥0/篇 (免费)
- 上下文: 128K
- 限流码: 429 / 1302 / 1305 → 5/10/15 秒退避

## 调用规范

### 应证段提取

```python
prompt = f"""你是医学文献证据抽取专家。从下面文献中找出 '{topic}' 相关段落。

文献全文:
{full_text[:30000]}

输出 JSON: {{"evidence": ["段1", "段2", ...], "page_hints": [3, 5, ...]}}
"""
result = call_glm_lit(prompt, max_tokens=2000)
```

### PDF-引用一致性校验

```python
prompt = f"""判断下面下载的 PDF 是否与引用主题相符。

引用: {citation}
DOI: {doi}
PDF metadata title: {pdf_title}
PDF 前 2000 字符: {text}

输出 JSON: {{"matches": true/false, "pdf_title": "...", "score": 0-100, "reason": "..."}}
"""
result = call_glm_lit(prompt, max_tokens=400)
```

### 反向推理 (GLM 找正确 DOI)

```python
prompt = f"""你是文献检索专家。根据下面引用找出最可能的真实 DOI:

引用: {citation}
错误 DOI: {wrong_doi}

输出 JSON: {{"doi": "10.xxx/xxx", "pmid": "...", "reason": "..."}}
"""
result = call_glm_lit(prompt, max_tokens=200)
```

## 验证记录 (2026-08-07)

- P3-2 (Luzzatto PNH 2020) ✅ matches=true, score=95
- 39 个 PDF 批量校验: 21 真正匹配 (53.8%), 18 错位, 7 无法解析
- 错位原因全是 fetch_plan_corrected.json 的 DOI 与 citation 错位, **不是 GLM 校验问题**
- GLM 校验准确率 100% (语义匹配, 不依赖文件名)