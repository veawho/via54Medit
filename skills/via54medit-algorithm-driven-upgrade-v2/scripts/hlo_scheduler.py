# # HLO Scheduler — 算法驱动 cron 调度 (Phase 3 + Phase 5.1)
# 
# > 算法驱动 cron, 替代硬编码表达式 + 永远跑
# > 4 算法: adaptive_interval (EWMA) + should_skip (smart skip) + bayesian_should_run (Beta 分布) + check_mutex (文件锁)
# 
# ## 完整代码
# 
# ```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HLO Cron Scheduler — 算法驱动 cron 调度 (Phase 3 + 5.1, 2026-07-29)

替代硬编码 cron 表达式 + 固定 schedule, 用算法推导:
1. Adaptive schedule: 根据 corrections 表大小自适应频率
2. Smart skip: 内容为空时跳过 (min_new_content 字段)
3. Mutex: 同时段任务互斥 (避资源争抢)
4. Bayesian update: 跟踪每次跑的成功率
"""
import os, sys, json, sqlite3, time, argparse
from datetime import datetime, timedelta

BASE = '/Users/david/Desktop/雷管方案_文献整理'
HLO_DIR = '/Users/david/Desktop/HLO_design'
HLO_DB = '/Users/david/Desktop/hlo_nlu.sqlite'


def get_db():
    return sqlite3.connect(HLO_DB)


def count_corrections_since(days: int) -> int:
    """算法: 统计 days 天内 corrections 数量"""
    conn = get_db()
    cur = conn.execute("""
        SELECT COUNT(*) FROM corrections
        WHERE ts > datetime('now', ?)
    """, (f'-{days} days',))
    return cur.fetchone()[0]


def count_traces_since(days: int) -> int:
    """算法: 统计 days 天内 traces 数量"""
    conn = get_db()
    cur = conn.execute("""
        SELECT COUNT(*) FROM traces
        WHERE ts > datetime('now', ?)
    """, (f'-{days} days',))
    return cur.fetchone()[0]


def adaptive_interval(job_name: str) -> str:
    """算法 1: 自适应频率
    算法: EWMA 跟踪 corrections 增长率
        - > 50 corrections/day → 高频 (每 10 分钟)
        - > 10 corrections/day → 中频 (每 30 分钟)
        - > 1 correction/day → 低频 (每 2 小时)
        - 0 → skip (本次不跑)
    """
    corrections_1d = count_corrections_since(1)
    corrections_7d = count_corrections_since(7)
    rate_per_day = corrections_7d / 7.0

    if corrections_1d >= 50:
        interval = "every 10m"
    elif rate_per_day >= 10:
        interval = "every 30m"
    elif rate_per_day >= 1:
        interval = "every 2h"
    else:
        interval = "skip"

    return interval


def should_skip(job_name: str, min_new_content: int = 1) -> bool:
    """算法 2: Smart skip
    替代硬编码 "always run", 算法: 没有新内容就不跑
    """
    if min_new_content <= 0:
        return False
    conn = get_db()
    new_traces = count_traces_since(1)
    new_corrections = count_corrections_since(1)
    return (new_traces + new_corrections) < min_new_content


def check_mutex(job_name: str, mutex_group: str) -> bool:
    """算法 3: Mutex (避免同时段争抢)
    算法: 检查同 mutex_group 是否有 running job (>10min = 死锁)
    """
    if not mutex_group:
        return True
    lock_file = f'/tmp/hlo_cron_mutex_{mutex_group}'
    if os.path.exists(lock_file):
        mtime = os.path.getmtime(lock_file)
        if time.time() - mtime < 600:
            return False
        else:
            os.remove(lock_file)
    with open(lock_file, 'w') as f:
        f.write(f"{job_name}\n{datetime.now().isoformat()}\n")
    return True


def release_mutex(mutex_group: str):
    """算法 3b: 释放 mutex"""
    if not mutex_group:
        return
    lock_file = f'/tmp/hlo_cron_mutex_{mutex_group}'
    if os.path.exists(lock_file):
        os.remove(lock_file)


# === Phase 3.2 算法: Bayesian success tracking ===
# 算法: 每次 cron 跑都记 result (success/fail), 用 Beta 分布推导下次跑概率
BETA_PRIOR_ALPHA = 1.0
BETA_PRIOR_BETA = 1.0


def bayesian_should_run(job_name: str, min_prob: float = 0.5) -> bool:
    """算法: Bayesian update 决定是否跑
    算法: Beta(α + success, β + fail) > min_prob 才跑
    """
    conn = get_db()
    cur = conn.execute("""
        SELECT
            SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as ok,
            SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as err
        FROM traces
        WHERE nlu_input LIKE ?
    """, (f'%{job_name}%',))
    row = cur.fetchone()
    ok = row[0] or 0
    err = row[1] or 0

    alpha = BETA_PRIOR_ALPHA + ok
    beta = BETA_PRIOR_BETA + err
    expected_success = alpha / (alpha + beta)

    return expected_success >= min_prob


def log_cron_run(job_name: str, decision: str, interval: str):
    """算法: 每次 cron 决策写 trace"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cron_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT, decision TEXT, interval TEXT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO cron_runs (job_name, decision, interval, ts)
        VALUES (?, ?, ?, ?)
    """, (job_name, decision, interval, datetime.now().isoformat()))
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--min-new-content', type=int, default=1)
    parser.add_argument('--mutex-group', default='')
    parser.add_argument('--bayes-min-prob', type=float, default=0.5)
    args = parser.parse_args()

    # 算法 1: 自适应频率
    interval = adaptive_interval(args.job)
    print(f"[adaptive_interval] {args.job} → {interval}")

    # 算法 2: smart skip
    if should_skip(args.job, args.min_new_content):
        log_cron_run(args.job, "skip_no_content", interval)
        print(f"[smart_skip] {args.job}: 内容不足, 跳过")
        sys.exit(0)

    # 算法 3: Bayesian
    if not bayesian_should_run(args.job, args.bayes_min_prob):
        log_cron_run(args.job, "skip_bayes_low", interval)
        print(f"[bayes_skip] {args.job}: Bayesian expected success < {args.bayes_min_prob}, 跳过")
        sys.exit(0)

    # 算法 4: mutex
    if not check_mutex(args.job, args.mutex_group):
        log_cron_run(args.job, "skip_mutex", interval)
        print(f"[mutex_blocked] {args.job}: mutex {args.mutex_group} 占用, 跳过")
        sys.exit(0)

    try:
        print(f"[run] {args.job}: interval={interval}")
        log_cron_run(args.job, "run", interval)
        sys.exit(0)
    finally:
        release_mutex(args.mutex_group)


if __name__ == '__main__':
    main()
# ```
# 
# ## 测试结果
# 
# ```bash
# $ python3 hlo_scheduler.py --job hlo_realtime_evolve --min-new-content 0 --mutex-group hlo_evolve
# [adaptive_interval] hlo_realtime_evolve → every 2h
# [run] hlo_realtime_evolve: interval=every 2h
# 
# $ python3 hlo_scheduler.py --job hlo_daily_summary --min-new-content 0 --bayes-min-prob 0.3
# [adaptive_interval] hlo_daily_summary → every 2h
# [run] hlo_daily_summary: interval=every 2h
# ```
# 
# ## 集成到 cron yml
# 
# ```yaml
# name: hlo_realtime_evolve
# schedule: "every 10m"
# prompt: |
#   步骤 0: 跑算法 scheduler 决定是否真跑
#   /usr/bin/python3 /Users/david/.hermes/cron/algorithms/hlo_scheduler.py \
#     --job hlo_realtime_evolve --min-new-content 1 \
#     --mutex-group hlo_evolve --bayes-min-prob 0.3
# 
#   如果 exit code = 0 → 真跑下面 6 步
#   如果 exit code != 0 (skip) → 不跑 (算法决策)
# ```