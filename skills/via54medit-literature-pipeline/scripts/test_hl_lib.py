#!/usr/bin/env python3
"""hl_lib 单元测试: canon / locate / rects / highlight 边界"""
import sys, os, tempfile
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hl_lib
from hl_lib import (canon, canon_keys, locate_sentence, locate_sentence_all,
                    sentence_rects, highlight_sentences, norm,
                    filter_sentences_by_slide_context, add_context_box,
                    add_freetext_badge, annotate_document)
import fitz

PASS = 0
FAIL = 0

def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  ✓ {name}')
    else:
        FAIL += 1
        print(f'  ✗ {name} {detail}')

print('== canon / canon_keys ==')
check('全角字母→半角', canon('ｔ') == 't', repr(canon('ｔ')))
check('全角数字→半角', canon('０') == '0')
check('全角标点→半角', canon('，') == ',' and canon('。') == '.')
check('ligature ﬁ→fi', canon('\ufb01') == 'fi')
check('soft-hyphen 去除', canon('\xad') == '')
check('nbsp 去除', canon('\xa0') == '')
check(r'\x01→≥', canon('\x01') == '≥')
check('€u→ü', canon_keys('€u')[0] == 'ü')
check('中文PDF标点 ꎬ→,', canon('ꎬ') == ',')
nk, ridx = canon_keys('a ﬁ b')
check('canon_keys 索引映射(原始索引含空格)', nk == 'afib' and ridx == [0, 2, 2, 4], repr((nk, ridx)))

print('== locate_sentence ==')
text = 'Hello world. Hello world again.'
l1 = locate_sentence(text, 'Hello world')
check('首次匹配', l1 == (0, 11), repr(l1))
l2 = locate_sentence(text, 'Hello world', occurrence=1)
check('occurrence=1 第二次', l2 == (13, 24), repr(l2))
check('找不到返回 None', locate_sentence(text, 'xyz') is None)
check('多匹配列表', len(locate_sentence_all(text, 'Hello world')) == 2)
# 规范匹配: 全角+连字
check('规范化匹配', locate_sentence('Ｔｈｉｓ ﬁne.', 'This fine') == (0, 8), repr(locate_sentence('Ｔｈｉｓ ﬁne.', 'This fine')))
check('空句子 None', locate_sentence(text, '') is None)

print('== sentence_rects ==')
# 构造假 chars: 3 行
chars = []
chars += [('T', fitz.Rect(100, 100, 105, 113)), ('e', fitz.Rect(105, 100, 110, 113)), ('s', fitz.Rect(110, 100, 115, 113))]
chars += [('t', fitz.Rect(100, 113, 105, 126)), ('x', fitz.Rect(105, 113, 110, 126)), ('t', fitz.Rect(110, 113, 115, 126))]
chars += [('.', fitz.Rect(100, 126, 104, 139))]
rs = sentence_rects(chars, 0, len(chars))
check('3 行分组', len(rs) == 3, repr([(round(r.y0,1)) for r in rs]))
check('行高=行距', round(rs[0].y1 - rs[0].y0, 1) == 12.0, repr(rs[0]))
# 离群: 孤立句号跳位
chars2 = chars + [('.', fitz.Rect(200, 40, 204, 53))]
rs2 = sentence_rects(chars2, 0, len(chars2))
check('离群行过滤', len(rs2) == 3, repr(len(rs2)))
# 同行 bbox 微差 (3.5pt) 合并
chars3 = [('a', fitz.Rect(100, 100, 105, 113)), ('b', fitz.Rect(105, 103.5, 110, 116.5))]
check('微差同行合并', len(sentence_rects(chars3, 0, 2)) == 1)
# 空区间
check('空区间', sentence_rects(chars, 5, 5) == [])

print('== highlight_sentences 边界 ==')
print('== 连字符与标点脱敏匹配 (Hyphenation & Punctuation Resilience) ==')
hyphen_text = 'The trans-missibility of RSV in infants is extremely high.'
l_hyphen = locate_sentence(hyphen_text, 'transmissibility of RSV')
check('跨行断字匹配 (trans-missibility -> transmissibility)', l_hyphen is not None, repr(l_hyphen))
if l_hyphen:
    check('跨行断字提取文本正确', hyphen_text[l_hyphen[0]:l_hyphen[1]] == 'trans-missibility of RSV')

# 标点脱敏与 OCR 错标点测试
punct_text = 'RSV感染属于自限性疾病，绝大多数感染患儿预后良好，不遗留后遗症。'
l_punct = locate_sentence(punct_text, 'RSV 感染属于自限性疾病,绝大多数感染患儿预后良好,不遗留后遗症')
check('标点脱敏匹配 (全角逗号/空格差异自愈)', l_punct is not None, repr(l_punct))

# 双锚点自愈测试 (尾部截断或中间错字)
long_text = '发生重症和危重症的高危人群为早产儿（<=32周）、出生低体重儿、具有支气管肺发育不良、慢性肺疾病等潜在基础疾病。'
l_anchor = locate_sentence(long_text, '发生重症和危重症的高危人群为早产儿（≤32周）、出生低体重儿、具有支气管肺发育不良、慢性肺疾病等潜在基础疾病')
check('双锚点自愈匹配 (符号差异/长句首尾锁定)', l_anchor is not None, repr(l_anchor))

print('== filter_sentences_by_slide_context (幻灯上下文相关性过滤) ==')
candidates = [
    'Mechanism of action: Clesrovimab targets the F protein site IV.',
    'Recommended dosage is 105 mg administered as a single intramuscular injection.',
    'Phase 3 CLEOPATRA trial showed 60.4% reduction in RSV-associated MALRI.',
    'Co-administration with routine childhood vaccines demonstrated non-inferiority.'
]
# Case 1: Slide about mechanism
f1 = filter_sentences_by_slide_context(candidates, 'Clesrovimab 作用机制 靶点 F蛋白', top_k=1)
check('过滤命中机制句子', len(f1) == 1 and 'Mechanism' in f1[0], repr(f1))

# Case 2: Slide about dosage
f2 = filter_sentences_by_slide_context(candidates, '剂量 规格 105mg 单次肌肉注射', top_k=1)
check('过滤命中剂量句子', len(f2) == 1 and '105 mg' in f2[0], repr(f2))

# Case 3: Slide about clinical trial efficacy
f3 = filter_sentences_by_slide_context(candidates, 'CLEOPATRA 临床试验 保护率 60.4% MALRI', top_k=1)
check('过滤命中临床试验句子', len(f3) == 1 and 'CLEOPATRA' in f3[0], repr(f3))

# Case 4: Slide about vaccine co-administration
f4 = filter_sentences_by_slide_context(candidates, '联合接种 疫苗 免疫原性', top_k=1)
check('过滤命中疫苗联合接种句子', len(f4) == 1 and 'vaccines' in f4[0], repr(f4))

print('== 三元标注与角标生成 (Tri-Modal Annotation) ==')
# 创建内存测试 PDF
test_doc = fitz.open()
test_page = test_doc.new_page(width=595, height=842)
test_page.insert_text((50, 100), "Figure 1. Efficacy of Clesrovimab against RSV infection across subgroups.", fontsize=12)
test_page.insert_text((50, 150), "Primary endpoint was met with statistical significance p < 0.001.", fontsize=11)
mem_pdf_path = os.path.join(tempfile.mkdtemp(), 'tri_modal_in.pdf')
mem_pdf_out = os.path.join(tempfile.mkdtemp(), 'tri_modal_out.pdf')
test_doc.save(mem_pdf_path)
test_doc.close()

cfg = {
    'highlights': {0: ["Primary endpoint was met with statistical significance"]},
    'boxes': [{'page': 0, 'rect': [45, 90, 500, 120], 'color': (0.8, 0.1, 0.1), 'width': 1.5, 'label': 'A'}],
    'badges': [{'page': 0, 'rect': [50, 150, 400, 165], 'label': 'B', 'placement': 'right'}]
}
annotate_document(mem_pdf_path, mem_pdf_out, cfg, verbose=False)

# 验证生成注解类型与数量
verify_doc = fitz.open(mem_pdf_out)
vp = verify_doc[0]
annots = list(vp.annots() or [])
types = [a.type[1] for a in annots]
check('三元标注包含 Highlight (Rect)', 'Square' in types or 'Highlight' in types or any(a.type[0] in (4, 8, 9) for a in annots), repr(types))
check('三元标注包含 FreeText 角标', 'FreeText' in types or any(a.type[0] == 2 for a in annots), repr(types))
check('总标注数量符合预期 (>=3)', len(annots) >= 3, f'Total annots: {len(annots)}')
verify_doc.close()

if os.path.exists(mem_pdf_path):
    os.remove(mem_pdf_path)
if os.path.exists(mem_pdf_out):
    os.remove(mem_pdf_out)

print('== highlight_sentences 边界 ==')
# 测试 PDF 参数化: TMA_HL_TEST_SRC > TMA_PROJECT/_2_pdfs/P23-8.pdf > Mac 默认
SRC = os.environ.get("TMA_HL_TEST_SRC") or None
if not SRC:
    proj = os.environ.get("TMA_PROJECT") or ""
    cand = os.path.join(proj, "_2_pdfs", "P23-8.pdf")
    SRC = cand if os.path.isfile(cand) else "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-8_main.pdf"
if not os.path.isfile(SRC):
    print("  ⚠️ 无测试 PDF (设 TMA_PROJECT 或 TMA_HL_TEST_SRC), 跳过 highlight_sentences 边界组")
    print(f"\n结果: {PASS} passed, {FAIL} failed (1 组跳过)")
    sys.exit(0)
doc = fitz.open(SRC)
n = len(doc)
# 动态取首页第一句作为 occurrence 测试句 (任何数据可用)
first_sent = (doc[0].get_text().replace('\n', ' ').strip().split('.')[0] or 'TA-TMA')[:80]
doc.close()
out = os.path.join(tempfile.mkdtemp(), 'hl_out.pdf')
# 页越界保护
r = highlight_sentences(SRC, out, {999: ['x']}, verbose=False)
check('页越界保护', r[0][2] == 'BAD PAGE', repr(r))
# occurrence 元组(句子出现多次时)
r = highlight_sentences(SRC, out, {0: [(first_sent, 0)]}, verbose=False)
check('occurrence 元组可用', any('OK' in x[2] for x in r), repr(r))
# 空句子
r = highlight_sentences(SRC, out, {0: ['']}, verbose=False)
check('空句子 NOT FOUND', r[0][2] == 'NOT FOUND', repr(r))
# 找不到句子
r = highlight_sentences(SRC, out, {0: ['this sentence does not exist anywhere']}, verbose=False)
check('找不到 NOT FOUND', r[0][2] == 'NOT FOUND')
if os.path.exists(out):
    os.remove(out)

print(f'\n结果: {PASS} passed, {FAIL} failed')
sys.exit(1 if FAIL else 0)

