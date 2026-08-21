# 双轨优化 Safety Pattern (2026-08-04)

## 起源

用户硬性约束:
> "我需要确保所有优化不会影响原来的功能和产出能力"

这个需求来自真实场景: 用户之前质疑过多次"为什么我之前能用的功能现在坏了", 反映出对 agent 优化的信任成本极高. 任何 P0/P1/P2 优化一旦破坏现有功能, 用户立刻 revoke 信任.

## 核心 SOP (5 步)

### Step 1: 新增独立文件, 不改原代码

**原则**: 优化文件全是 `*_v2.py` / `references/` / 新 schema, 原 `*.py` 文件 0 行修改.

```bash
# ❌ 错误: 直接覆盖原文件
edit(project_layout_resolver.py, ...)  # 修改原算法

# ✅ 正确: 新增 v2 包装
new(signatures.py, ...)  # 调用原算法, 返回 typed result
```

**实测验收**: 跑 `git status` 或 `md5sum`, 验证原文件 0 字节修改.

### Step 2: 跑回归测试, 锁现有产出

**关键**: 优化之前必须先**建立**回归测试套件, 锁定现有产出.

```python
# test_regression_today.py
def test_resolve_chose_source_of_truth():
    """主目录必须解析到 literature_citation_index"""
    from project_layout_resolver import resolve_dir
    r = resolve_dir(PROJECT_NAME, role='source_of_truth', intent='cite_for_publication')
    assert r['chosen']['dir_id'] == 'literature_citation_index', ...
```

**为什么先建测试再优化**: 如果先优化后建测试, 测试会"接受"优化后的新行为, 失去锁旧产出的能力.

### Step 3: 验证产出等价 (字段 + 浮点近似)

```python
def test_v2_resolve_equivalent():
    """v2 wrapper 产出 = 原函数 (字段对齐)"""
    raw = resolve_dir(PROJECT_NAME, role='source_of_truth', intent='cite_for_publication')
    v2 = resolve_layout_v2(LayoutResolveSig(project=PROJECT_NAME,
                                            role='source_of_truth',
                                            intent='cite_for_publication'))

    assert v2.chosen.dir_id == raw['chosen']['dir_id']
    assert v2.chosen.path == raw['chosen']['path']
    assert abs(v2.chosen.score - raw['chosen']['score']) < 0.001  # 浮点 EWMA 累加漂移
```

**关键**: 浮点比较必须用 `abs(diff) < 0.001` 或 `pytest.approx(rel=1e-6)`, 严禁 `==`.

**为什么**: EWMA 是累加的, 每次 `resolve_dir()` 调用 score 都在漂移, 严格相等必失败.

### Step 4: 保留老 CLI 路径, 新增 subcommand 才用新算法

```bash
# 老 CLI 12 个 subcommand 全部保留
medit resolve/parse/decide/record/archive/update-citation/h-path
medit mirror/verify-pdf/shortcut/proxy/fallback/truth

# 新 CLI subcommand 才用 v2 算法
medit resolve-v2/parse-v2/decide-v2/...  # 或一个 unified --v2 标志
```

### Step 5: 状态文件版本号, 失败时回退

```bash
# cache/state.json      ← 原状态, 兼容老算法
# cache/state_v2.json   ← 新状态, 用 v2 算法
```

**算法版本切换**:
1. 写 v2 状态到 `state_v2.json`
2. 跑回归测试, 如果失败 → 删 `state_v2.json`, 用老的 `state.json`
3. 跑通 100 次 → 才正式切流量

## 反模式 (禁止)

- ❌ 一次性替换所有算法代码
- ❌ 改原 `*.py` 文件的行
- ❌ 改原 `cache/*.json` state 文件
- ❌ 改 `project_layout.json` schema 不留备份
- ❌ 不写测试就上线
- ❌ 不锁定现有产出就开始优化
- ❌ 严格浮点相等比较 (`assert float_a == float_b`)
- ❌ 删除老 CLI subcommand

## 正模式 (推荐)

- ✅ `signatures.py` 只 import 老函数, 不复制实现
- ✅ 测试断言用 `pytest.approx` 或 `abs(diff) < 0.001`
- ✅ 优化产物放独立文件 (`*_v2.py`, `references/`)
- ✅ 跑通 42 个测试才切流量
- ✅ 跑通后保留老 CLI 至少 1 个版本
- ✅ 状态文件版本号 `state_v2.json`, 失败回退

## 实测验证 (2026-08-04)

| 原算法文件 | 改动 | 备注 |
|-----------|------|------|
| `project_layout_resolver.py` | **0 字节** | v2 wrapper 调用 |
| `medit_apply_correction.py` | **0 字节** | v2 wrapper 调用 |
| `medit_parse_instruction.py` | **0 字节** | v2 wrapper 调用 |
| `publisher_shortcuts.py` | **0 字节** | v2 wrapper 调用 |
| `proxy_resolver.py` | **0 字节** | v2 wrapper 调用 |
| `fallback_chain_engine.py` | **0 字节** | v2 wrapper 调用 |
| `manifest_truth_detector.py` | **0 字节** | v2 wrapper 调用 |
| `mirror_health_resolver.py` | **0 字节** | v2 wrapper 调用 |
| `content_verifier.py` | **0 字节** | v2 wrapper 调用 |
| `medit` (CLI) | **0 字节** | 12 个 subcommand 不动 |
| `project_layout.json` | **0 字节** | validator 只读, 不写 |
| `medit_cache/*.json` | **0 字节** | 优化前快照备份 |

**新文件全是叠加**:
- `signatures.py` (13KB) — OPT-1 typed wrapper
- `config_validator.py` (3.9KB) — OPT-2 validator
- `project_layout.schema.json` (2.4KB) — OPT-2 schema
- `~/.medit/tests/` (3 测试文件, 42 测试) — OPT-3 regression

**测试结果**: 42 passed in 4.88s ✅

## 行业对照

| 项目 | 优化保护机制 |
|------|-------------|
| **DSPy** | 编译后的 `.json` 是 immutable, 失败回退到 heuristic |
| **SGLang** | Radix tree LRU 100K cap, 原子 evict |
| **Aider** | Edit grammar 严格 syntax, 失败 rollback |
| **vLLM** | Continuous batching 原子事务, 不会半完成 |
| **我们 (v1.3.0)** | **双轨 + 回归测试 + 浮点 + 状态版本号** |

## 模板

### Typed Signature Wrapper Template

```python
# signatures.py - v2 typed wrapper
from dataclasses import dataclass, asdict

@dataclass
class MyAlgoSig:
    """DSPy-Style 输入"""
    input_field: str

@dataclass
class MyAlgoResult:
    """DSPy-Style 输出"""
    output_field: str

    def to_dict(self) -> dict:
        return asdict(self)


def my_algo_v2(sig: MyAlgoSig) -> MyAlgoResult:
    """v2 wrapper: 调用原算法, 转为 typed result"""
    from my_algo import original_function  # 老函数

    raw = original_function(sig.input_field)

    return MyAlgoResult(
        output_field=raw['output'],
    )
```

### Regression Test Template

```python
# test_regression_today.py
def test_X_equivalent():
    """v2 wrapper 产出 = 原函数 (字段对齐)"""
    from my_algo import original_function
    from signatures import my_algo_v2, MyAlgoSig

    raw = original_function('input')
    v2 = my_algo_v2(MyAlgoSig(input_field='input'))

    assert v2.output_field == raw['output']
    # 浮点用 approx
    # assert abs(v2.score - raw['score']) < 0.001
```

### JSON Schema Validation Template

```python
# config_validator.py
from pathlib import Path

SCHEMA_PATH = Path.home() / '.medit/config/schema.json'
CONFIG_PATH = Path.home() / '.medit/config/config.json'

def validate_config(config: dict = None) -> dict:
    """校验 config, 不修改"""
    if config is None:
        config = json.loads(CONFIG_PATH.read_text())

    # 三层验证
    if HAS_JSONSCHEMA:
        try:
            schema = json.loads(SCHEMA_PATH.read_text())
            validator = jsonschema.Draft7Validator(schema)
            errors = list(validator.iter_errors(config))
            # 加上 duplicate-id post-check
            errors.extend(_check_duplicate_ids(config))
            return {'valid': len(errors) == 0, 'errors': [str(e) for e in errors]}
        except Exception:
            return _manual_validate(config)
    else:
        return _manual_validate(config)
```

## 切流量步骤

当 P0 优化**全部 42 测试通过**且**>= 1 周内部用户使用没问题**时:

1. **公告**: 通知所有调用 v1 算法的代码, "v1 将在 N 周后 deprecate"
2. **观察**: 监控 v1 vs v2 调用次数, 渐进切换
3. **切换**: v2 调用数 > 80% 时, v1 标 `deprecated`
4. **废弃**: v2 调用数 = 100% 时, v1 标记 `legacy`, 但保留 1 个版本
5. **删除**: v2 稳定 6 个月后, 才能删 v1

**禁止**:
- ❌ 优化当天就删 v1 算法
- ❌ 优化当天就改成 v2 默认
- ❌ 测试一边跑一边改算法

## 验证清单 (切流量前)

- [ ] 42 个回归测试全部通过
- [ ] v2 wrapper 与原函数产出等价 (字段 + 浮点)
- [ ] 原 `*.py` 文件 0 字节修改
- [ ] 原 `project_layout.json` 0 字节修改
- [ ] 原 `cache/*.json` 0 字节修改
- [ ] 老 CLI 12 subcommand 全部保留
- [ ] 状态文件版本号 `state_v2.json` 存在
- [ ] Failure rollback 路径已测 (del state_v2.json, 用 state.json 跑通)
- [ ] 用户确认 OK

## 失败案例 (反例)

- 2026-08-03 早期: 我直接 `edit(project_layout_resolver.py, ...)` 改了原算法, 用户看不到区别但实际 broke 1 个边缘 case
- 2026-08-03 早期: 我新加的 v2 wrapper 没测产出等价, 跑出来 score 字段错位
- 2026-08-03 早期: 我新加 `pytest.approx(rel=1e-6)` 太严格, EWMA 漂移 1e-5 报失败

**教训**: 每次写测试必须先跑, 验证它对老代码 green, 然后再优化. 只有"优化前绿, 优化后绿"才是真正的回归测试.
