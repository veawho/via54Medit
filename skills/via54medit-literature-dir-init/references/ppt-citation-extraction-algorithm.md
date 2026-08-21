# PPT 引用提取算法 (语义 + 序号智能切分)

> 解决: PPT 底部参考文献有两种格式 — 多段落 (每条换行) 和单段落挤在一起。
> 旧方法用 `re.split(r'(\d{1,3}\.\s*)')` 会把页码也切开 (如 "66." → 假引用)。
> 新方法用语义判断: 编号后面必须跟大写字母或中文, 否则是页码不是引用。

## 核心算法

```python
import re

def extract_citations_from_text(text, slide_num):
    """从单段文本中提取所有引用: 找所有 "数字. 作者/期刊" 位置, 按位置切分
    
    支持两种格式:
    - 多段落: 每条引用换行 (\\n 自然分隔)
    - 单段落: 多条引用挤在一起, 按 "数字. 作者/期刊" 语义位置切分
    """
    results = []
    seen_pairs = set()  # (slide, num) 去重
    
    for line in [l.strip() for l in text.split('\n') if l.strip()]:
        # 找所有 "数字. [大写字母/中文]" 位置
        # 关键: lookahead (?=[A-Z\u4e00-\u9fff]) 确保编号后是作者/期刊, 不是页码
        matches = list(re.finditer(
            r'(\d{1,3})\.\s*(?=[A-Z\u4e00-\u9fff\u00c0-\u024f])', line
        ))
        
        for i, m in enumerate(matches):
            num = int(m.group(1))
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(line)
            text_part = line[start:end].strip()
            text_part = re.sub(r'\s+', ' ', text_part)[:300].rstrip(' ,.,')
            if len(text_part) < 10:
                continue
            pair = (slide_num, num)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                results.append({'slide': slide_num, 'num': num, 'text': text_part})
    
    return results
```

## 为什么旧方法失败

### 旧方法: 纯序号分割

```python
# ❌ 错: 会把页码切成假引用
refs = re.split(r'(\d{1,3}\.\s*)', text)
# "1. George JN... 654-66. 2. Timmermans..." 
# → 把 "66." 也切成一条引用 (因为 66 后面有 ".")
```

### 问题: 页码格式与引用编号格式冲突

- 引用编号: `1. George JN, et al.`
- 页码: `654-66.` (出现在引用文本中间)
- 旧正则 `(\d{1,3}\.\s*)` 无法区分两者

### 新方法: 语义 lookahead

```python
# ✅ 对: 编号后面必须跟大写字母或中文
r'(\d{1,3})\.\s*(?=[A-Z\u4e00-\u9fff\u00c0-\u024f])'
#                           ^^^^^^^^^^^^^^^^^^^^^^^^^^
#                           lookahead: 下一个字符必须是作者首字母或中文
#                           页码后面是空格或下一条引用的数字 → 不匹配
```

## 去重策略

**同一 (slide, num) 只保留一条**:

不同 shape 可能包含相同编号 (如 slide 21 有两个 shape 都有 "1."), 去重后只保留第一条。

```python
seen_pairs = set()
pair = (slide_num, num)
if pair not in seen_pairs:
    seen_pairs.add(pair)
    results.append(...)
```

## 实测 (TMA PPT, 2026-08-07)

| 版本 | 条数 | 问题 |
|------|------|------|
| 旧方法 (纯序号 split) | 26 | ❌ 错误去重 (跨 slide 同编号 = 不同文献) |
| 旧方法 (不去重) | 108 | ❌ 页码被切成假引用 |
| **新方法 (语义 lookahead)** | **106** | **✅ 正确** |

106 条跨 27 个 slide, 引用编号 1-26, 同编号在不同 slide 是不同文献。

## 集成到 render_ppt_slides.py

`extract_citations()` 函数已集成到统一 PPT 渲染脚本:

```bash
python3 render_ppt_slides.py <pptx> --engine applescript
# → 渲染 33 张 slide + 提取 106 条引用 → citation_table.csv
```

## 特殊情况处理

### 同编号跨 slide = 不同文献

PPT 的引用编号是每页重新编号的 (slide 3 的 ref 1 和 slide 6 的 ref 1 是不同论文)。
所以 **不能跨 slide 去重**, 只能在同 slide 内去重。

### PPT 笔误

Slide 31 末尾有 "2. Jiang A, Liu Y, et al." — 编号 2 是笔误 (前面已有 ref 2)。
实际应为 ref 8 (第 8 条独立文献)。

### 缺失编号

某些 slide 可能跳号 (如 slide 11 只有 [2,3,4,6,7], 缺 1 和 5)。
这是因为 PPT 正文上标引用可能不连续, 但底部参考文献可能完整。
