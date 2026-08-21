# 2026-08-01 Session: P3-2 应证推理 + PaddleOCR 集成 + mmx-cli vision

## 核心发现

1. **27 行癌肿图表是图片, 不在文字层**
   - P3-2 main + fallback 两个 PDF 都是纯政策文本（卫健委文件）
   - 文字里只有 "46.6%"（总体癌症5年生存率）
   - 用户说的 "27 种癌症 5 年生存率" 图表是图片, 不在 PyMuPDF 文字提取中
   - 结论: 需要找原图源, 或用 mmx vision 视觉理解

2. **PaddleOCR 3.7.0 安装验证**
   - 安装: `pip install "paddlepaddle>=2.6" "paddleocr>=2.8"`
   - 装在 hermes-agent venv 下
   - 自动下载 4 个模型（~180MB）：PP-LCNet / UVDoc / PP-OCRv6-det / PP-OCRv6-rec
   - 新 API: `ocr.predict(img)` 返回 dict-like OCRResult 对象, 含 rec_texts / rec_scores / rec_polys
   - 旧参数 `use_angle_cls` 已弃用, 改用 `use_textline_orientation`
   - 旧参数 `show_log` 已移除
   - 实测: P3-2 page 3 识别 24 个文本块, 全部得分 ≥0.96

3. **mmx-cli vision 已验证**
   - 安装: `npm install -g mmx-cli` (v1.0.18)
   - 认证: `mmx auth login --api-key sk-xxxxx` (已配置, 文件在 ~/.config/minimax/credentials.json)
   - 命令: `mmx vision describe --image xxx.jpg --prompt "提取表格"`
   - 状态: Token Plan 已超限, 需续费

4. **用户纠正: 设计 != 实现**
   - 用户问"这些是否都配置了"时, 我不能把"设计文档"和"已实现"混着写
   - 必须每层标注真实状态（已用 / 已装 / 已落地 / 已装但未接 / 规划中）

## 应证推理机运行结果

```bash
medit anno2ppt confirm "中国肝癌5年生存率仅14.4%, 远低于其他癌种" /tmp/p3_2_rows.json
```

输出:
```json
{
  "confirm_score": 0.95,
  "mismatch_report": "集合结论: 25 > subject + 1 < subject + 1 例外",
  "decision": {
    "ShouldHighlight": true,
    "Reason": "应证得分 0.95, 集合结论成立",
    "BBoxes": 27,
    "Notes": "应证 中国 肝癌 14.4%, 远低于其他癌种: 25 种癌肿高于 14.4%, 1 种低于 (例外 1 种)"
  }
}
```

## CLI 编译验证

```bash
cd /Users/david/Desktop/developments/via54Medit
go build -o /tmp/medit ./cmd/medit/
go test ./internal/anno2ppt/ -v  # 9/9 PASS
```

## 4 维信息要素抽取示例

输入: "中国肝癌5年生存率仅14.4%, 远低于其他癌种"
输出:
- Elements[0] = {Geography: "中国", Disease: "肝癌"}
- Elements[1] = {Disease: "其他癌种"} (target)
- Elements[2] = {Value: "14.4%", ValueNum: 14.4, Unit: "%"}
- Elements[3] = {Conclusion: "below_all"} (远低于其他)

## 未解决的问题

1. 27 行癌肿图表的原始来源在哪？不在 P3-2 PDF 里
2. mmx-cli vision Token 已超限, 需要续费
3. 错行修复逻辑还没写进 pipeline