# -*- coding: utf-8 -*-
"""M1/M2 冒烟测试 (repo 内): layout 分栏/页眉页脚 + locate_in_ocr 回退链 + 兼容旧 API."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout
import hl_ocr_band as ob

fails = []


def check(name, cond):
    print(('  OK  ' if cond else '  FAIL') + ' ' + name)
    if not cond:
        fails.append(name)


print('== layout.page_zones (单栏 + 页眉页脚) ==')
# 构造: 2 行正文 x 左栏, 顶部页眉, 底部页码
words = []
def w(x, y, t, h=12):
    return dict(x=x, y=y, w=len(t) * 6, h=h, ln=0, t=t)
# 页眉 (居中短) y=30
words.append(w(400, 30, 'JOURNAL OF TEST'))
# 正文两行 y=100, y=130
words += [w(50, 100, 'Hello'), w(80, 100, 'world'), w(50, 130, 'Second'), w(80, 130, 'line')]
# 页码 y=760 (底部 4%, 在 bottom_frac 带内)
words.append(w(500, 760, '12'))
zones = layout.page_zones(words, 792, 'eng')['zones']
print('  zones:', [(z['kind'], len(z['words'])) for z in zones])
check('header/footer excluded -> body words=4', sum(len(z['words']) for z in zones if z['kind'] == 'body') == 4)

print('== layout 双栏词级切分 ==')
two = []
for row in range(3):
    y = 100 + row * 20
    two += [w(50, y, 'Left%d' % row), w(90, y, 'left'), w(400, y, 'Right%d' % row),
            w(440, y, 'right'), w(480, y, 'col')]
# 行内词会按 x 排序: 应切出左右两列 (各 3 词/行 -> 每侧词数达标)
flows, _ = layout.reading_columns(two, 792, 'eng')
print('  nflows:', len(flows), [len(f) for f in flows])
check('two columns produced', len(flows) == 2 and {len(f) for f in flows} == {6, 9})

print('== locate_in_ocr 回退链 ==')
floww = [dict(t=t) for t in 'On August 3, 2023, CDC recommended nirsevimab (Beyfortus)'.split()]
r = ob.locate_in_ocr(floww, 'On August 3, 2023, CDC recommended nirsevimab (Beyfortus)')
check('exact sentence', r == (0, len(floww) - 1))
# 连字符自愈
fw2 = [dict(t='trans-'), dict(t='missibility')]
check('hyphen heal', ob.locate_in_ocr(fw2, 'transmissibility') == (0, 1))
# 标点脱敏: OCR 缺逗号
r2 = ob.locate_in_ocr(floww, 'On August 3 2023 CDC recommended nirsevimab Beyfortus')
check('punct-agnostic', r2 is not None)
# 找不到
check('no match -> None', ob.locate_in_ocr(floww, 'completely different phrase here') is None)

print('== 兼容旧 API ==')
check('split_cols still exists', hasattr(ob, 'split_cols'))
check('band_highlight exists', hasattr(ob, 'band_highlight'))
check('words_tsv exists', hasattr(ob, 'words_tsv'))
print('  _save_out:', hasattr(ob, '_save_out'))

print('\n%s  (fails=%d)' % ('ALL PASS' if not fails else 'FAILED', len(fails)))
sys.exit(1 if fails else 0)
