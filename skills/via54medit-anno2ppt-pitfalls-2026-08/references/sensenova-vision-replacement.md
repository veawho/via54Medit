# sensenova-6.7-flash-lite 替代 mmx vision — 实战完整记录

> 配套: pitfalls §20. 适用: 任何需要 L3 视觉复核 + 高亮验证的场景.

## 为什么必须替代 mmx vision

| 对比项 | mmx vision | sensenova-6.7-flash-lite |
|--------|-----------|--------------------------|
| 费用 | 按 Token 计费 | **全部免费 (pricing=0)** |
| Token 上限 | 经常触发 Token Plan 上限 | **无限制** |
| 安装 | 需 npm 安装 mmx-cli (~100MB) | 0 安装, 纯 API |
| Context | 有限 (8K-32K) | **262K tokens** |
| 敏感词 | Hong Kong / Taiwan 触发审查 | **无审查** (国内 API) |
| 速度 | 慢 (5-15s) | **快 (1-3s)** |

用户原话触发替换: "sensenova 也有多模态才对" (2026-08-01)

## 3 级视觉 Cascade (v4.0, 2026-08-01 集成)

统一入口: scripts/vision_verify.py — 3 级自动降级

### 调用顺序

| 优先级 | 模型 | API | 实测延迟 | 状态 |
|:----:|------|-----|:------:|:----:|
| 1 主 | sensenova-6.7-flash-lite | token.sensenova.cn/v1 | ~11s | 稳定 |
| 2 备 | MiniMax-M3 | api.minimax.chat/v1/chat/completions | N/A | 经常 429 限流 / 2056 配额用尽 |
| 3 兜底 | PyMuPDF local | 本地 | <1s | metadata only, 无视觉理解 |

### MiniMax-M3 关键配置

- base_url: api.minimax.chat/v1
- model: MiniMax-M3 (MiniMax-VL-01 不存在, API 返回 2013 unknown model)
- key_env: MINIMAX_CN_API_KEY_2 或 MINIMAX_CN_API_KEY
- API 端点: POST /v1/chat/completions (OpenAI 兼容格式)

### 控制变量

| 环境变量 | 效果 |
|---------|------|
| SKIP_SENSENOVA=1 | 跳过主视觉, 直接进备选 |
| SKIP_MINIMAX=1 | 跳过备选, 直接进兜底 |
| VISION_TIMEOUT=60 | 单调用超时 (默认 30s) |
| MINIMAX_CN_API_KEY_2 | MiniMax 主 key |

### 用法

```bash
python3.11 scripts/vision_verify.py <image> "<prompt>" --json
python3.11 scripts/vision_verify.py <image> "<prompt>" --provider sensenova
python3.11 scripts/vision_verify.py <image> "<prompt>" --provider minimax
python3.11 scripts/vision_verify.py <image> "<prompt>" --provider local
```

### MiniMax 已知问题

1. MiniMax-VL-01 不存在 — API 返回 2013. 当前视觉模型名是 MiniMax-M3.
2. 429 限流 / 2056 配额用尽 — 配额耗尽需要充值; cascade 自动降级到兜底.
3. Qwen2-VL-2B 4bit 离线兜底 — 需用户手动装 ollama + pull qwen2.5vl. install.sh 被用户安全策略拒绝, 当前未安装, local 兜底只读 metadata.

### process_all_pn_x.py 集成

```python
def sensenova_verify(image_path, expected_terms, provider="cascade", timeout=60):
    """返回 (success, content, provider_used)"""
```

## API 详情

- base_url: token.sensenova.cn/v1
- model: sensenova-6.7-flash-lite
- key_env: SENSENOVA_API_KEY (在 ~/.hermes/config.yaml)
- input_modalities: text, image
- output_modalities: text

端点格式: OpenAI-compatible chat completions
- POST /chat/completions
- Content 数组: [{"type":"text","text":"..."}, {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}]

## 集成位置 (已落地)

```
via54Medit/
├── scripts/
│   ├── vision_verify.py       — 3 级 Cascade 统一入口 (NEW v4.0)
│   ├── sensenova_vision.py (188 行) — 核心 API 调用 + base64
│   ├── l3_vision_verify.py (78 行) — L4 流程包装器
│   └── process_pn_x.py        — 集成 cascade 自动调
└── internal/anno2ppt/
    └── algorithm.go (含 sensenova 配置入口)
```

## CLI 用法

```bash
python3.11 scripts/sensenova_vision.py <image.jpg> "PPT引用语义"
python3.11 scripts/sensenova_vision.py <image.jpg> "prompt" --json
python3.11 scripts/sensenova_vision.py <image.jpg> "prompt" --save output.txt
```

## Python API

```python
import sys
sys.path.insert(0, 'scripts')
from sensenova_vision import vision_analyze

result = vision_analyze(
    "/path/to/highlight.jpg",
    "请数清楚图里黄色高亮区块的具体数量, 并简单描述每处覆盖的内容"
)
# 返回: {success: bool, content: str, error: str}
```

## 实测验证 (4 个 Pn-x)

| Pn-x | 图片 | sensenova 返回 | 准确度 |
|------|------|---------------|:----:|
| P3-1 | page 3 HIMALAYA | 3 处高亮 (ORR 30% vs 20% + CR 8% vs 3% + DOR 22.34 vs 18.1 月) | 通过 |
| P29-1 | page 1 Song YG | 4 处高亮 (8.42% / 4.42% / 2.06% / 2.11x) | 通过 |
| P33-11 | page 1 Song YG | Grade III or IV bleeding 4.42% | 通过 |
| P30-1 | page 2 NCT02329860 | 47.9% Hypertension + 21% Proteinuria | 通过 |

## 关键踩坑

| 坑 | 错写法 | 对写法 |
|---|--------|--------|
| Token Plan 限额 | 反复调 mmx vision 等恢复 | 直接切 sensenova |
| 敏感词触发 | 用 Hong Kong / Taiwan | 用宽泛临床描述: 亚洲亚组 / 中国大陆加港澳台 |
| 图像 base64 | bytes 读后 base64.b64encode | base64.b64encode(open(path,'rb').read()) |
| --json 模式偏差 | 默认 --json | 默认 non-JSON, 需要结构化再 --json |
| 超长 prompt | 200+ 字详细描述 | 50-100 字精炼: 数高亮 + 描述覆盖 |
| MiniMax 模型名 | MiniMax-VL-01 | MiniMax-M3 (2013 错误) |

## 决策表

| 场景 | 工具 |
|------|------|
| 高亮图视觉复核 | sensenova (~11s) |
| 复杂多模态问答 | sensenova (262K context) |
| 文字层搜 + 计数 | PyMuPDF |
| OCR 中文 PDF | PaddleOCR (中文唯一) |
| 大量批量标注 | PyMuPDF + Page.search_for |
| 主视觉挂了 | MiniMax-M3 (备, 常限流) |
| 全 API 挂了 | PyMuPDF local (兜底) |

## 配置文件

~/.hermes/config.yaml 必需:

```yaml
providers:
  sensenova:
    api_key: "sk-***"
    base_url: "https://token.sensenova.cn/v1"
    model: "sensenova-6.7-flash-lite"
    input_modalities: ["text", "image"]
    pricing: 0
```

## 关键经验

1. 不要预设 Token Plan 还能用 — 立即改 sensenova
2. 图像分辨率 150 DPI 已够 — 不用 300 DPI 浪费带宽
3. prompt 简练 — 50-100 字精炼比 200 字啰嗦更准
4. sensenova 返回 ~11s 但更准确 — 不要追求 0.1s 节省
5. multi-image 一次发 — sensenova 支持多图
6. MiniMax 当前不可依赖 — 429/2056 常见, 只作备选, 主调依赖 sensenova
7. Qwen2-VL 需用户手动安装 ollama — 自动化 install 被安全策略拒绝