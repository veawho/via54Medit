"""CSV 表头迁移 —— 供各推送端共用。

为什么需要它
------------
本模块的统计产物(公司公共统计表、多维表格本地备份)都是"表头 + 数据行"的 CSV。
**新增一个类目就要新增列**, 而列只能追加在末尾:

* **云端表插不了列**: 飞书电子表格的 ``values_append`` 只能往表格尾部追加, 没有插列
  接口。云端插不了而本地按位置插, 两边列语义立刻分叉。
* **本地备份是按表头名回读的** (``dict(zip(header, row))``)。表头没更新就写入更宽的
  行, 回读时会因列数不符被当作脏行**静默丢弃** —— 备份文件看起来还在长, 数据却在丢。
* **中间插列会让历史行整体错位**: 旧行的"总节约工时"会落在新行的"其他任务数"位置上,
  而且表面上完全看不出来。

因此这里的规则只有一条: **新列一律追加在末尾; 表头与当前列定义不一致时, 先按
"旧列名"取值、整表重写为新表头(新列补空), 绝不按位置硬搬** —— 按位置搬正是错位的成因。

对"列数与旧表头不符"的行**原样保留**: 那类行通常属于更早的遗留格式, 各有各的回读
兜底逻辑(见 ``bitable_sync._load_local_csv_records``), 迁移器不该替它们做解释。
"""

import csv
import os
from typing import List, Sequence, Tuple


def migrate_header(csv_path: str, columns: Sequence[str],
                   encoding: str = "utf-8-sig") -> Tuple[bool, str]:
    """把 ``csv_path`` 的表头对齐到 ``columns``。返回 ``(可安全追加, 提示)``。

    * 无需迁移 -> ``(True, "")``
    * 迁移成功 -> ``(True, "本地统计表表头已迁移 (18 -> 21 列), 新增列 [...]")``
    * 无法迁移 -> ``(False, 原因)``。**此时调用方不应再追加数据** ——
      表头没对齐而继续追加, 就是这个文件开始说假话的时刻。

    任何异常都不抛出: 迁移失败不该让上报本身失败, 但要如实回报。
    """
    columns = list(columns)
    try:
        with open(csv_path, "r", encoding=encoding, newline="") as f:
            rows = list(csv.reader(f))
    except OSError as e:
        return False, f"读取失败, 本次不追加: {e}"
    if not rows:
        return True, ""

    old_header = [h.strip() for h in rows[0]]
    if old_header == columns:
        return True, ""

    index = {name: i for i, name in enumerate(old_header)}
    new_rows = [columns]
    for row in rows[1:]:
        if len(row) == len(old_header):
            # 与旧表头等宽 -> 按**列名**取值, 新列补空
            new_rows.append([row[index[name]] if name in index else "" for name in columns])
        else:
            # 列数不符 (遗留格式) -> 原样保留, 交给各自的回读兜底逻辑
            new_rows.append(row)

    tmp_path = csv_path + ".migrating"
    try:
        with open(tmp_path, "w", encoding=encoding, newline="") as f:
            csv.writer(f).writerows(new_rows)
        os.replace(tmp_path, csv_path)
    except OSError as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False, f"表头迁移失败 (原文件未改动), 本次不追加: {e}"

    added = [c for c in columns if c not in index]
    removed = [c for c in old_header if c not in columns]
    note = f"表头已迁移 ({len(old_header)} -> {len(columns)} 列)"
    if added:
        note += f", 新增列 {added}"
    if removed:
        note += f", 已废弃列 {removed}"
    return True, note


def column_letter(idx: int) -> str:
    """0 基列序号 -> 电子表格列名 (0 -> A, 25 -> Z, 26 -> AA)。

    与云端表的 ``Sheet1!A:U`` 区间记法配套, 免得列数一变就要手改字符串。
    """
    letters = ""
    n = idx
    while True:
        letters = chr(ord("A") + n % 26) + letters
        n = n // 26 - 1
        if n < 0:
            break
    return letters


def range_end(columns: Sequence[str]) -> str:
    """列定义 -> 追加区间的右端列名 (21 列 -> ``"U"``)。"""
    return column_letter(len(list(columns)) - 1)


def header_matches(csv_path: str, columns: Sequence[str], encoding: str = "utf-8-sig") -> bool:
    """只判断表头是否已对齐 (不改动文件)。文件不存在视为需迁移。"""
    try:
        with open(csv_path, "r", encoding=encoding, newline="") as f:
            first = next(csv.reader(f), None)
    except OSError:
        return False
    return bool(first) and [h.strip() for h in first] == list(columns)


def dedupe_columns(columns: Sequence[str]) -> List[str]:
    """列名自检: 重复列名会让"按名回读"变成掷硬币。供测试与表头定义处调用。"""
    seen, dupes = set(), []
    for name in columns:
        if name in seen:
            dupes.append(name)
        seen.add(name)
    return dupes
