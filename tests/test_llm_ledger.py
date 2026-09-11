"""LLM 接入与 Token 用量读取能力 —— 记账链路的"不许悄悄退化"测试。

为什么要专门一组测试
--------------------
记账是**旁路**: 一条调用路径不再记录用量, 调用本身不会报错、不会有异常、不会有
非零退出码, 报表只是安静地少一块数字。实测抓到过两处这类缺口:

  * ``scripts/provider_llm.py``(默认文本 provider)把 ``usage`` 返回给调用方,
    却**没有任何地方把它写进库** —— DeepSeek 的 token 一直是 0;
  * Go 侧 ``internal/foundation/llm.go`` 解析响应时只取 ``choices``, ``usage``
    整个丢弃 —— ``medit ask`` / ``medplan`` / docproc 的 token 一行都没进库。

两者都不会让任何测试变红。所以这里既测"现在是对的", 也**测"探测器本身能发现退化"**
(见 ``TestDetectorCatchesRegression``): 一个只会说"一切正常"的检查比没有检查更糟。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from telemetry import llm_providers, llm_spool           # noqa: E402
from telemetry.db import TelemetryDB                     # noqa: E402

def _read(path):
    """读源码。显式指定 utf-8 并关闭句柄 —— Windows 上默认编码是 cp1252,
    而且未关闭的文件会拦住后续的替换/删除。"""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


GO_USAGE_SRC = os.path.join(REPO, "internal", "foundation", "llm_usage.go")
GO_LLM_SRC = os.path.join(REPO, "internal", "foundation", "llm.go")
GO_GLM_SRC = os.path.join(REPO, "internal", "foundation", "llm_glm.go")


class TestRegistryIntegrity(unittest.TestCase):
    """注册表要么说得准, 要么别写 —— 每条通道的实现文件必须真的存在。"""

    def test_every_channel_module_exists(self):
        missing = []
        for prov in llm_providers.PROVIDERS:
            self.assertTrue(prov.channels, "%s 没有任何通道" % prov.key)
            for ch in prov.channels:
                if not llm_providers.find_module(ch.module):
                    missing.append("%s → %s" % (prov.key, ch.module))
        self.assertEqual(missing, [], "注册表里的实现文件不存在: %s" % missing)

    def test_registry_has_no_declared_recorder_field(self):
        # 这是**方法论**的守卫: "谁在记用量"必须由 scan_recorders 从源码查出来。
        # 一旦有人把"记录者清单"加回注册表, 这个断言会提醒他那是在自我声明。
        self.assertNotIn("recorders", llm_providers.Provider.__dataclass_fields__)
        self.assertNotIn("recorder", llm_providers.Provider.__dataclass_fields__)

    def test_sample_responses_cover_every_provider_with_response_usage(self):
        # 声称"能从响应体读到 usage"的 provider, 就必须有对应形状的样例 ——
        # 否则 verify_ingestion 会静默跳过它, 校验范围就缩水了。
        need = [p.key for p in llm_providers.PROVIDERS
                if any(c.usage == llm_providers.USAGE_RESPONSE for c in p.channels)]
        missing = [k for k in need if k not in llm_providers._SAMPLE_RESPONSES]
        self.assertEqual(missing, [], "缺少真实响应样例: %s" % missing)

    def test_alias_map_normalizes_go_names(self):
        # Go 注册名 glm 与 Python 的 zhipu 是同一份账单, 必须归一
        self.assertEqual(llm_providers.PROVIDER_ALIASES["glm"], "zhipu")
        self.assertEqual(llm_providers.PROVIDER_ALIASES["codex"], "openai")
        self.assertEqual(llm_providers.PROVIDER_ALIASES["deepseek-r1"], "deepseek")


class TestSourceEvidence(unittest.TestCase):
    """记账证据必须来自源码, 且两侧(Python / Go)都要被看见。"""

    def test_scan_finds_python_and_go_callers(self):
        rec = llm_providers.scan_recorders()
        self.assertIn("scripts/provider_llm.py", rec["py"]["files"])
        self.assertIn("internal/foundation/llm.go", rec["go"]["files"])

    def test_go_side_registers_usage_name_per_provider(self):
        go = llm_providers.scan_recorders()["go"]["by_provider"]
        for key in ("hermes", "openai", "deepseek", "zhipu"):
            self.assertIn(key, go, "Go 侧没有 %s 的记账证据(usageName/字面量)" % key)

    def test_go_source_actually_calls_recorder(self):
        src = _read(GO_LLM_SRC)
        self.assertIn("recordLLMUsage(", src, "llm.go 不再调用记账函数")
        glm = _read(GO_GLM_SRC)
        self.assertIn('recordLLMUsage("zhipu"', glm)

    def test_every_integrated_provider_has_a_recorder(self):
        for p in llm_providers.discover():
            if p["per_call_usage"]:
                self.assertTrue(p["has_recorder"],
                                "%s 声称能读单次用量, 却没有任何记账调用点" % p["key"])
                self.assertEqual(p["unrecorded_channels"], [],
                                 "%s 有通道没在记: %s" % (p["key"], p["unrecorded_channels"]))


class mock_scan:
    """临时把源码扫描指向一个假仓库 —— 不动真实仓库就能验"探测器会不会报"。"""

    def __init__(self, root):
        self.root = root

    def __enter__(self):
        self._orig = llm_providers.scan_recorders

        def patched(root=""):
            return self._orig(self.root)

        llm_providers.scan_recorders = patched
        return self

    def __exit__(self, *exc):
        llm_providers.scan_recorders = self._orig
        return False


class TestDetectorCatchesRegression(unittest.TestCase):
    """探测器自身的负向测试 —— 只会在报"一切正常"的检查比没有检查更危险。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, body):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def test_dead_recording_point_is_reported(self):
        # 私有包装函数定义了记账, 但**没有任何地方调用它**: 正则扫描会数到一个
        # record_llm_usage( 调用点, 于是误判"在记录"。可达性分析必须识破。
        self._write("dead_recorder.py",
                    "def _record_usage(result):\n"
                    "    from telemetry.token_tracker import record_llm_usage\n"
                    "    record_llm_usage(response=result, provider='deepseek')\n"
                    "\n"
                    "def real_call(result):\n"
                    "    return result\n")
        rec = llm_providers.scan_recorders(root=self.tmp)
        self.assertEqual(rec["py"]["files"], [],
                         "死记账点被当成了有效调用点 —— 这正是要防的假阳性")
        self.assertEqual(len(rec["py"]["unreachable"]), 1)
        rel, fn, _key = rec["py"]["unreachable"][0]
        self.assertEqual(fn, "_record_usage")

    def test_public_entry_point_is_not_flagged(self):
        # 公开入口(vision_analyze 这类)在同文件内本来就不会被调用, 不能判死
        self._write("entry.py",
                    "def vision_analyze(result):\n"
                    "    from telemetry.token_tracker import record_llm_usage\n"
                    "    record_llm_usage(response=result, provider='sensenova')\n")
        rec = llm_providers.scan_recorders(root=self.tmp)
        self.assertEqual(rec["py"]["unreachable"], [])
        self.assertIn("entry.py", rec["py"]["files"])

    def test_live_private_helper_is_reachable(self):
        self._write("live.py",
                    "def _record_usage(result):\n"
                    "    from telemetry.token_tracker import record_llm_usage\n"
                    "    record_llm_usage(response=result, provider='deepseek')\n"
                    "\n"
                    "def call_it(result):\n"
                    "    _record_usage(result)\n")
        rec = llm_providers.scan_recorders(root=self.tmp)
        self.assertEqual(rec["py"]["unreachable"], [])
        self.assertEqual(rec["py"]["by_provider"].get("deepseek"), ["live.py"])

    def test_audit_reports_dead_recording_point_as_problem(self):
        self._write("dead_recorder.py",
                    "def _record_usage(result):\n"
                    "    from telemetry.token_tracker import record_llm_usage\n"
                    "    record_llm_usage(response=result, provider='deepseek')\n")
        with mock_scan(self.tmp):
            res = llm_providers.audit()
        joined = " | ".join(res["problems"])
        self.assertIn("_record_usage()", joined)


class TestIngestionRoundTrip(unittest.TestCase):
    """离线端到端: 真实响应形状 → 落库 → 读回 → 报表层。"""

    def test_all_providers_round_trip(self):
        results = {r["key"]: r for r in llm_providers.verify_ingestion()}
        self.assertEqual(sorted(results), sorted(p.key for p in llm_providers.PROVIDERS))
        bad = {k: v["detail"] for k, v in results.items() if not v["ok"]}
        self.assertEqual(bad, {}, "摄入校验未通过: %s" % bad)

    def test_spool_chain_round_trip_and_idempotent_replay(self):
        res = llm_providers.verify_spool_ingestion()
        self.assertTrue(res["ok"], res["detail"])

    def test_audit_has_no_problems_and_no_live_side_effects(self):
        res = llm_providers.audit(live=False, ingest=False)
        self.assertEqual(res["problems"], [])
        self.assertIsNone(res["mmx_quota"])
        self.assertIsNotNone(res["spool_verify"])
        self.assertTrue(res["spool_verify"]["ok"])

    def test_format_report_mentions_problem_free_state(self):
        text = llm_providers.format_report(llm_providers.audit(live=False), verbose=True)
        self.assertIn("LLM 接入与 Token 用量读取能力审计", text)
        self.assertIn("没有发现问题", text)
        self.assertIn("Go 侧 spool", text)


class TestSpoolIngestion(unittest.TestCase):
    """Go → spool → 库 的字段契约与幂等性。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.spool = os.path.join(self.tmp, "spool.jsonl")
        self.db = TelemetryDB(os.path.join(self.tmp, "t.db"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, lines):
        with open(self.spool, "w", encoding="utf-8") as fh:
            for ln in lines:
                fh.write(ln + "\n")

    def test_go_provider_name_is_normalized(self):
        self._write([json.dumps({
            "ts": "2026-03-01T08:00:00Z", "provider": "glm", "model": "glm-4-flash",
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
            "req_id": "g1", "source": "go:x", "project_name": "",
        })])
        llm_spool.ingest(path=self.spool, db=self.db)
        self.assertEqual(len(self.db.query_llm_tokens(provider="glm")), 0)
        rows = self.db.query_llm_tokens(provider="zhipu")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_tokens"], 15)

    def test_created_at_uses_spool_ts(self):
        self._write([json.dumps({
            "ts": "2026-03-01T08:00:00Z", "provider": "deepseek",
            "model": "deepseek-chat", "prompt_tokens": 1, "completion_tokens": 1,
            "total_tokens": 2, "req_id": "d1", "source": "go:x",
        })])
        llm_spool.ingest(path=self.spool, db=self.db)
        row = self.db.query_llm_tokens()[0]
        # 用 ts 而不是摄入时刻, 否则按周切分的统计会对不上真实调用时间
        self.assertTrue(row["created_at"].startswith("2026-03-01"), row["created_at"])

    def test_replay_is_idempotent(self):
        line = json.dumps({
            "ts": "2026-03-01T08:00:00Z", "provider": "deepseek",
            "model": "deepseek-chat", "prompt_tokens": 7, "completion_tokens": 3,
            "total_tokens": 10, "req_id": "dup-1", "source": "go:x",
        })
        self._write([line])
        first = llm_spool.ingest(path=self.spool, db=self.db)
        self._write([line])
        second = llm_spool.ingest(path=self.spool, db=self.db)
        self.assertEqual((first["imported"], second["imported"]), (1, 0))
        self.assertEqual(second["duplicated"], 1)
        self.assertEqual(len(self.db.query_llm_tokens()), 1)

    def test_line_without_tokens_is_skipped(self):
        # 服务商没返回 usage 时 Go 不写行; 万一写了 0, 也不能入库污染口径
        self._write([json.dumps({
            "ts": "2026-03-01T08:00:00Z", "provider": "deepseek",
            "model": "deepseek-chat", "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "req_id": "zero", "source": "go:x",
        })])
        res = llm_spool.ingest(path=self.spool, db=self.db)
        self.assertEqual(res["imported"], 0)
        self.assertEqual(len(self.db.query_llm_tokens()), 0)

    def test_malformed_line_does_not_abort_the_batch(self):
        good = json.dumps({
            "ts": "2026-03-01T08:00:00Z", "provider": "deepseek",
            "model": "deepseek-chat", "prompt_tokens": 4, "completion_tokens": 4,
            "total_tokens": 8, "req_id": "ok-1", "source": "go:x",
        })
        self._write(["{ this is not json", good])
        res = llm_spool.ingest(path=self.spool, db=self.db)
        self.assertEqual(res["imported"], 1)
        self.assertEqual(res["invalid"], 1)
        self.assertEqual(len(self.db.query_llm_tokens()), 1)

    def test_missing_req_id_still_deduplicates(self):
        line = json.dumps({
            "ts": "2026-03-01T08:00:00Z", "provider": "deepseek",
            "model": "deepseek-chat", "prompt_tokens": 4, "completion_tokens": 4,
            "total_tokens": 8, "source": "go:x",
        })
        self._write([line])
        llm_spool.ingest(path=self.spool, db=self.db)
        self._write([line])
        second = llm_spool.ingest(path=self.spool, db=self.db)
        self.assertEqual(second["imported"], 0, "没有 req_id 时应按内容指纹去重")
        self.assertEqual(len(self.db.query_llm_tokens()), 1)

    def test_truncation_drops_nothing_and_still_makes_progress(self):
        """单批上限生效时: 不丢账, 且必须能往前走。

        两个都会出事的极端:
        * 若按"整文件轮转"推进 —— 没读完的行被直接丢掉, 那是真丢账;
        * 若只截断不推进 —— 已入库的重复行一直占着批额, 后面的行永远读不到。
        """
        from unittest import mock

        lines = [json.dumps({
            "ts": "2026-03-01T08:00:00Z", "provider": "deepseek",
            "model": "deepseek-chat", "prompt_tokens": i + 1,
            "completion_tokens": 1, "total_tokens": i + 2,
            "req_id": "n%d" % i, "source": "go:x",
        }) for i in range(5)]
        self._write(lines)

        with mock.patch.object(llm_spool, "MAX_BATCH", 2):
            first = llm_spool.ingest(path=self.spool, db=self.db)
            self.assertTrue(first["truncated"])
            self.assertEqual(first["imported"], 2)
            # 截断时不得轮转: 其余 3 行必须还在
            self.assertEqual(llm_spool.spool_status(self.spool)["pending"], 3)
            second = llm_spool.ingest(path=self.spool, db=self.db)
            self.assertEqual(second["imported"], 2)
            self.assertEqual(llm_spool.spool_status(self.spool)["pending"], 1)
            third = llm_spool.ingest(path=self.spool, db=self.db)
            self.assertEqual(third["imported"], 1)
            self.assertEqual(llm_spool.spool_status(self.spool)["pending"], 0)

        self.assertEqual(len(self.db.query_llm_tokens()), 5, "5 行必须一行不少地入库")

    def test_bad_lines_do_not_block_forever(self):
        # 坏行必须被清掉, 否则下一轮还会读到同一行, spool 永远清空不了
        self._write(["{ broken", "{ also broken"])
        first = llm_spool.ingest(path=self.spool, db=self.db)
        self.assertEqual(first["invalid"], 2)
        self.assertEqual(llm_spool.spool_status(self.spool)["pending"], 0)

    def test_non_ascii_lines_are_not_split(self):
        # 按字节切片推进: 非 ASCII 内容(中文 source)不能被劈成两半
        self._write([json.dumps({
            "ts": "2026-03-01T08:00:00Z", "provider": "deepseek",
            "model": "深度求索-chat", "prompt_tokens": 9, "completion_tokens": 1,
            "total_tokens": 10, "req_id": "zh-1", "source": "go:medplan/研究",
        }, ensure_ascii=False)])
        first = llm_spool.ingest(path=self.spool, db=self.db)
        self.assertEqual(first["imported"], 1)
        self.assertEqual(llm_spool.spool_status(self.spool)["pending"], 0)
        row = self.db.query_llm_tokens()[0]
        self.assertEqual(row["model"], "深度求索-chat")
        self.assertEqual(row["source"], "go:medplan/研究")

    def test_empty_spool_is_a_no_op(self):
        res = llm_spool.ingest(path=os.path.join(self.tmp, "nope.jsonl"), db=self.db)
        self.assertEqual((res["read"], res["imported"]), (0, 0))

    def test_spool_status_reports_pending(self):
        self._write(["", "{}", ""])
        st = llm_spool.spool_status(self.spool)
        self.assertTrue(st["exists"])
        # 空行不算"待摄入"
        self.assertEqual(st["pending"], 1)
        self.assertEqual(llm_spool.spool_status(
            os.path.join(self.tmp, "nope.jsonl"))["exists"], False)


class TestCrossLanguageContract(unittest.TestCase):
    """Go 写出的字段必须与 Python 摄入端读的字段一致 —— 靠源码对齐, 不靠记忆。"""

    def test_spool_env_name_matches_between_languages(self):
        src = _read(GO_USAGE_SRC)
        self.assertIn('LLMUsageSpoolEnv = "%s"' % llm_providers.SPOOL_ENV, src)

    def test_go_written_keys_are_all_consumed(self):
        import re

        src = _read(GO_USAGE_SRC)
        # 取 json.Marshal 那段 map 的键
        block = src[src.index("json.Marshal(map[string]any{"):]
        block = block[:block.index("})")]
        go_keys = set(re.findall(r'"([a-z_]+)":', block))
        expected = {"ts", "provider", "model", "prompt_tokens", "completion_tokens",
                    "total_tokens", "req_id", "source", "project_name"}
        self.assertEqual(go_keys, expected,
                         "Go 写出的字段变了, Python 摄入端会读不到: %s" % go_keys)

    def test_python_consumes_every_go_key(self):
        # ts 由 _parse_created_at 读(其他键由 _to_record 读), 两者合起来才是摄入端
        import inspect

        body = (inspect.getsource(llm_spool._to_record)
                + inspect.getsource(llm_spool._parse_created_at))
        for key in ("ts", "provider", "model", "prompt_tokens", "completion_tokens",
                    "total_tokens", "req_id", "source", "project_name"):
            self.assertIn('"%s"' % key, body, "摄入端没有读 Go 写的 %s" % key)


class TestEntryPoints(unittest.TestCase):
    """CLI 与部署校验必须真的能跑, 且失败要非零退出。"""

    def test_cli_llm_json(self):
        proc = subprocess.run(
            [sys.executable, "-m", "telemetry.cli", "llm", "--json", "--no-ingest"],
            cwd=REPO, capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["problems"], [])
        self.assertEqual(len(payload["providers"]), len(llm_providers.PROVIDERS))
        self.assertTrue(payload["spool_verify"]["ok"])

    def test_cli_llm_exits_nonzero_on_problems(self):
        from unittest import mock

        from telemetry import cli

        args = type("A", (), {"live": False, "json": False, "verbose": False,
                              "no_ingest": True, "func": None})()
        with mock.patch.object(llm_providers, "audit",
                               return_value={"problems": ["boom"], "providers": [],
                                             "selection": {}, "spool": {},
                                             "spool_verify": {}, "ingest": {}}):
            with self.assertRaises(SystemExit) as ctx:
                cli.cmd_llm(args)
        self.assertEqual(ctx.exception.code, 2)

    def test_deploy_scan_verify_llm_passes(self):
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import deploy_scan

        ok, problems, payload = deploy_scan.verify_llm(live=False, ingest=False)
        self.assertTrue(ok, problems)
        self.assertIsNotNone(payload)

    def test_deploy_scan_verify_llm_cli_exit_code(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO, "scripts", "deploy_scan.py"), "--verify-llm"],
            cwd=REPO, capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",
        )
        self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr)[-800:])
        self.assertIn("LLM 接入校验 OK", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
