#!/usr/bin/env python3.11
"""
csv_feishu_sync.py — Citation table CSV ↔ Feishu sync (Python wrapper)

Why this exists (2026-08-01, user-taught):
  The citation_table.csv MUST have a canonical header row.
  Without a header, every downstream tool (Excel, pandas, lark-cli, the
  Go csv_sync.go gatekeeper) silently misaligns rows. We hit this exact
  bug on 2026-08-01: P3-1 row was missing, then the local CSV had no
  header, causing 1-row offset between local and Feishu.

Iron rule (frozen 2026-08-01):
  - citation_table.csv first row = canonical header (8 columns, frozen)
  - Feishu spreadsheet header = same 8 columns
  - Local row N = Feishu row N+1 (Feishu row 1 is the header)

Usage:
  # One-shot: validate + sync local CSV to Feishu
  python3.11 csv_feishu_sync.py validate <csv_path>
  python3.11 csv_feishu_sync.py sync   <csv_path>

  # Or import the helpers
  from csv_feishu_sync import CANONICAL_HEADER, verify_csv_header, read_csv

Env:
  SENSENOVA_API_KEY    (for visual cascade, not used here)
  LARK_CLI             default: /Users/david/.hermes/node/bin/lark-cli
  FEISHU_SHEET_TOKEN   必填 (飞书表格 token, 勿硬编码提交)
  FEISHU_SHEET_ID      default: b03e59
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

# === Canonical schema — must match Go csv_sync.go CanonicalHeader ===
CANONICAL_HEADER = [
    "PPT页",                              # A: SlidePage
    "第几条",                              # B: CiteIndex
    "引用语义（上下文）",                  # C: Context
    "PPT中的文献引用 完整字段",            # D: Reference
    "DOI",                                 # E: DOI
    "类型",                                # F: DocType
    "对应PDF文件",                          # G: PDFFile
    "来源链接 → 阅读全文",                  # H: SourceURL
]

LARK_CLI = os.environ.get("LARK_CLI", "/Users/david/.hermes/node/bin/lark-cli")
FEISHU_SHEET_TOKEN = os.environ.get("FEISHU_SHEET_TOKEN", "")
FEISHU_SHEET_ID = os.environ.get("FEISHU_SHEET_ID", "b03e59")


def verify_csv_header(csv_path: str) -> tuple[bool, str]:
    """
    Verify citation_table.csv has the canonical header.

    Returns:
        (ok, message)
        ok=True  if header matches CANONICAL_HEADER
        ok=False with diagnostic message if not
    """
    if not Path(csv_path).exists():
        return False, f"file not found: {csv_path}"

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return False, "empty file"

    # Strip BOM
    if header and header[0].startswith("\ufeff"):
        header[0] = header[0][1:]

    if len(header) != len(CANONICAL_HEADER):
        return False, (
            f"column count mismatch: got {len(header)}, want {len(CANONICAL_HEADER)}\n"
            f"  got:  {header}\n"
            f"  want: {CANONICAL_HEADER}"
        )

    for i, (got, want) in enumerate(zip(header, CANONICAL_HEADER)):
        if got.strip() != want:
            return False, (
                f"column {i+1} mismatch: got {got!r}, want {want!r}\n"
                f"  got:  {header}\n"
                f"  want: {CANONICAL_HEADER}"
            )

    return True, "header matches canonical schema"


def read_csv(csv_path: str) -> tuple[list[str], list[list[str]]]:
    """
    Read a citation_table.csv that has the canonical header.

    Returns:
        (header, data_rows)
        header is the verified canonical header
        data_rows is a list of records (each a list of 8 strings)

    Raises:
        ValueError if the header doesn't match.
    """
    ok, msg = verify_csv_header(csv_path)
    if not ok:
        raise ValueError(f"header validation failed: {msg}")

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        rows = [r for r in reader if r and any(c.strip() for c in r)]
    return list(CANONICAL_HEADER), rows


def write_csv(csv_path: str, rows: list[list[str]], header=None):
    """
    Write a citation_table.csv with the canonical header enforced.

    If header is None, CANONICAL_HEADER is used.
    Each row must have exactly len(CANONICAL_HEADER) cells.
    UTF-8 BOM is prepended (Excel + Lark + pandas all read it correctly).
    """
    if header is None:
        header = list(CANONICAL_HEADER)
    if header != CANONICAL_HEADER:
        raise ValueError(f"header must equal CANONICAL_HEADER, got: {header}")

    for i, row in enumerate(rows):
        if len(row) != len(CANONICAL_HEADER):
            raise ValueError(
                f"row {i+1} (data row, +1 for header): "
                f"got {len(row)} cells, want {len(CANONICAL_HEADER)}"
            )

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        for row in rows:
            w.writerow(row)


def feishu_get_range(range_str: str) -> list[list[str]]:
    """
    Read a cell range from Feishu via lark-cli.

    Args:
        range_str: e.g. "A1:H161" (without sheet prefix)

    Returns:
        2D list of cell values (strings). Empty list if no data.
    """
    cmd = [
        LARK_CLI, "sheets", "+cells-get",
        "--spreadsheet-token", FEISHU_SHEET_TOKEN,
        "--sheet-id", FEISHU_SHEET_ID,
        "--range", range_str,
        "--include", "value",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"lark-cli error: {result.stderr}")
    data = json.loads(result.stdout)
    return [
        [c.get("value", "") for c in row]
        for row in data.get("data", {}).get("ranges", [{}])[0].get("cells", [])
    ]


def validate(csv_path: str) -> int:
    """Validate a citation_table.csv. Exit 0 on success, 1 on failure."""
    ok, msg = verify_csv_header(csv_path)
    if ok:
        # Also count data rows
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)
            data_rows = [r for r in reader if r and any(c.strip() for c in r)]
        print(f"✅ {csv_path}")
        print(f"   header: {len(CANONICAL_HEADER)} columns (canonical)")
        print(f"   data rows: {len(data_rows)}")
        return 0
    else:
        print(f"❌ {csv_path}")
        print(f"   {msg}")
        print()
        print("Fix: add the canonical header as the first row:")
        for col in CANONICAL_HEADER:
            print(f"  {col!r}")
        return 1


def pull(csv_path: str) -> int:
    """Pull (overwrite) local CSV with Feishu table contents.

    Strategy:
    1. Detect row count from Feishu (A1:H<auto>)
    2. Validate Feishu header == CANONICAL_HEADER
    3. Backup local CSV to <csv_path>.bak_pre_feishu_pull
    4. Write Feishu data over local CSV (with canonical header)
    """
    # Detect row count first (read just column A from A1:A2000 to find last filled row)
    cmd = [
        LARK_CLI, "sheets", "+cells-get",
        "--spreadsheet-token", FEISHU_SHEET_TOKEN,
        "--sheet-id", FEISHU_SHEET_ID,
        "--range", "A1:A2000",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"❌ lark-cli A column read failed: {result.stderr}")
        return 1
    a_data = json.loads(result.stdout)
    a_cells = a_data.get("data", {}).get("ranges", [{}])[0].get("cells", [])
    # find last non-empty row in column A
    last_row = 0
    for cell in a_cells:
        v = cell.get("value", "")
        if v and v.strip():
            row_n = cell.get("row", 0)
            if row_n > last_row:
                last_row = row_n
    if last_row < 2:
        print(f"❌ Feishu has no data rows (last_row={last_row})")
        return 1
    print(f"✅ Feishu has data through row {last_row}")

    # Now read full range A1:H{last_row}
    feishu = feishu_get_range(f"A1:H{last_row}")
    if not feishu or len(feishu) < 2:
        print(f"❌ Feishu returned insufficient data")
        return 1

    # Validate header
    feishu_header = [c.strip().lstrip("\ufeff") for c in feishu[0]]
    if feishu_header != CANONICAL_HEADER:
        print(f"❌ Feishu header mismatch:")
        print(f"   got:  {feishu_header}")
        print(f"   want: {CANONICAL_HEADER}")
        return 1

    # Backup local CSV
    import shutil
    bak_path = f"{csv_path}.bak_pre_feishu_pull"
    if Path(csv_path).exists():
        shutil.copy2(csv_path, bak_path)
        print(f"✅ backup: {bak_path}")

    # Write Feishu data (skip header row, since write_csv adds it)
    data_rows = feishu[1:]
    # Pad short rows to 8 cells
    padded = []
    for r in data_rows:
        rr = list(r) + [""] * (len(CANONICAL_HEADER) - len(r))
        padded.append(rr[:len(CANONICAL_HEADER)])
    write_csv(csv_path, padded)
    print(f"✅ pulled {len(padded)} rows from Feishu → {csv_path}")
    return 0


def sync(csv_path: str) -> int:
    """Validate local CSV, then compare against Feishu, reporting mismatches."""
    try:
        header, rows = read_csv(csv_path)
    except ValueError as e:
        print(f"❌ local CSV invalid: {e}")
        return 1

    n_rows = len(rows)
    print(f"✅ local CSV: {n_rows} data rows, header OK")

    # Read Feishu header + same row count
    feishu = feishu_get_range(f"A1:H{n_rows + 1}")
    if not feishu:
        print(f"❌ Feishu returned no data for A1:H{n_rows + 1}")
        return 1

    feishu_header = [c.strip().lstrip("\ufeff") for c in feishu[0]]
    if feishu_header != CANONICAL_HEADER:
        print(f"❌ Feishu header mismatch:")
        print(f"   got:  {feishu_header}")
        print(f"   want: {CANONICAL_HEADER}")
        return 1

    print(f"✅ Feishu: header matches canonical")

    # Compare data row by row
    mismatches = []
    for r in range(min(len(rows), len(feishu) - 1)):
        local_row = rows[r]
        feishu_row = feishu[r + 1]
        for c in range(len(CANONICAL_HEADER)):
            lv = local_row[c].strip() if c < len(local_row) else ""
            fv = feishu_row[c].strip() if c < len(feishu_row) else ""
            if lv != fv:
                mismatches.append((r + 2, c, lv[:30], fv[:30]))

    if not mismatches:
        print(f"🎉 all {n_rows} rows × {len(CANONICAL_HEADER)} cells match Feishu")
        return 0

    print(f"⚠️  {len(mismatches)} cell mismatches found:")
    for row_n, col_i, lv, fv in mismatches[:10]:
        col_letter = chr(ord("A") + col_i)
        print(f"   Row {row_n} col {col_letter}: local={lv!r} feishu={fv!r}")
    if len(mismatches) > 10:
        print(f"   ... and {len(mismatches) - 10} more")
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="citation_table.csv ↔ Feishu sync (canonical header enforced)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="validate local CSV header")
    p_val.add_argument("csv_path")

    p_sync = sub.add_parser("sync", help="validate + compare with Feishu")
    p_sync.add_argument("csv_path")
    p_pull = sub.add_parser("pull", help="pull (overwrite) local CSV with Feishu data")
    p_pull.add_argument("csv_path")

    args = parser.parse_args()

    if args.cmd == "validate":
        sys.exit(validate(args.csv_path))
    elif args.cmd == "sync":
        sys.exit(sync(args.csv_path))
    elif args.cmd == "pull":
        sys.exit(pull(args.csv_path))


if __name__ == "__main__":
    main()
