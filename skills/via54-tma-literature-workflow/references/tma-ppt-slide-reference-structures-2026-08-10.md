# TMA PPT 引用编号结构 (vision核对版, 2026-08-10)

**来源**: 用vision_analyze逐页读取`/Users/david/Desktop/TMA_文献整理/_ppt_renders/slide_pp_NNN.jpg`
**用途**: C列（标记）核查参照。python-pptx XML正则提取引用编号不可用。

## 已知真实引用结构

```
Slide 3: [1]中华血液学杂志2024  [2]Luzzatto  [3]West EE
Slide 4: [1]中华血液学杂志2024  [2]Luzzatto  [3]West EE  [4]Skattum  [5]Heesterbeek  [6]Figueroa
Slide 5: [1]Kirschfink  [2]Skattum  [3]Figueroa
Slide 6: [1]Nat Rev Nephrol 2018 (aHUS/补体系统)
Slide 7: [1]Timmermans SAMEG
Slide 8: [1]Laurence J  [2]Palma LM P
Slide 9: [1]George JN  [2]Timmermans  [3]戴艳玲  [4]中华医学会血液学分会  [5]非典型溶血尿毒综合征共识2025
Slide 10: (目录页)
Slide 11: [1]任宏  [2]Azoulay  [4]浙江省医学会  [5]中华医学会  [6]Luzzatto  [7]Yerigeri
         ⚠️ 无引用3！
Slide 12: [1]Azoulay  [2]中华血液学杂志2017  [3]UpToDate
Slide 13: [1]焦扬  [2]Martinez MT
Slide 14: [1]Nguyen TC  [2]Brocklebank V  [3]Thompson GL
Slide 15: [2]Prasad C  ⚠️ 无引用1！
Slide 16: [1]Trojnar E
Slide 17: [1]中华医学会血栓与止血学组+Zheng XL  [4]Issa L
         ⚠️ 引用1包含两篇（指南+Zheng XL）
Slide 18: [1]Zheng XL
Slide 19: [1]Sukumar S  [2]Fox LC
Slide 20: [1]Henrique IM  [2]Liu Y
Slide 21: [1]突变/基因多态性  [2]抗CFH抗体  ⚠️ 中文标题引用
Slide 22: [2]Azoulay  ⚠️ 无引用1！
Slide 23: [2]Schoettler ML  [3]Ho VT  [4]Gavrilaki E  [5]Dvorak CC  [6]Khaled SK  [7]Wanchoo R
         [9]Jodele S  [10]Dandoy CE  [11]Dandoy CE  [12]Jodele S  [13]Jodele S
         [14]Rampogal A  [15]Schoettler M  [16]Schoettler M  [17]Wang Y
         [18]Kraft S  [19]Li A  [20]Postalcioglu M  [21]Liu W  [22]Chen BT
         [23]Sabulski A  [24]Schoettler ML  [25]Dandoy CE  [26]Jodele S
         ⚠️ 无引用8！
Slide 24: [1]Schoettler ML  [2]中华医学会共识  [3]张赵光
Slide 25: [1]Jodele S  [2]非典型溶血尿毒综合征共识2025  [3]Timmermans  [4]Yerigeri
         [5]Trojnar E  [6]Zheng XL  [8]Azoulay
         ⚠️ 无引用7！
Slide 26: (目录页)
Slide 27: [1]Sakari Jokiranta T
Slide 28: [1]Lazana I  [2]Renaud A  [3]Limin H  [4]Mahmoud AA
Slide 29: [2]Sridharan M  ⚠️ 无引用1！
Slide 30: [1]Brocklebank V  [2]非典型溶血尿毒综合征共识  [3]Uriol Rivera MG  [4]Gordon CE
Slide 31: [1]Noris M  [2]Jiang A  [4]Fakhouri F  [5]Licht C  [7]Sami Fam
         ⚠️ 无引用3和6！
```

## 关键发现

1. **跳过编号**: 多个slide引用编号不连续（无3、无8、无1等）
2. **合并引用**: Slide 17的引用1包含两篇不同文献
3. **XML正则失败原因**: 文本跨`<a:t>`块导致分割错误，81条"错误"几乎全是误报
4. **唯一可靠方法**: vision_analyze逐页读取，不能用XML提权

## 飞书表C列核查要点

飞书表C列值应与上表比对。但注意：
- C列可能被之前的不准确流程填充，需与PPT vision结果逐一核对
- 建议用vision_analyze核对关键slides（3/4/5/6/8/9/11/17/23/25/28/30/31）
