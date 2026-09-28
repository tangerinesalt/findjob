"""Selection and non-destructive follow-up behavior, without network fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("report_target", ROOT / "skills/job-search/scripts/report_target.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

REPORT = """# 岗位报告：Unity非游戏开发

## 第一部分：岗位简表

| 公司 | 岗位 | 地点 | 薪资 | 招聘链接 |
|---|---|---|---|---|
| 合成测试公司 | Unity开发 | 上海 | 面议 | [岗位](https://example.org/1) |

## 第二部分：岗位详情

用户手工备注：保留特殊字符 & < > 和中文。
"""


class Targets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "中文 工作空间"
        self.root.mkdir()
        self.old = self.put("旧清单.md", REPORT, 10)
        self.new = self.put("新清单.md", REPORT, 20)

    def put(self, name, content, time=30):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        os.utime(path, (time, time))
        return path

    def test_explicit_beats_context_and_mtime_and_accepts_stem(self):
        result = module.resolve(self.root, "旧清单", "新清单.md")
        self.assertEqual(result["report"], str(self.old.resolve()))
        self.assertEqual(result["selected_by"], "explicit")

    def test_context_beats_newer_file(self):
        result = module.resolve(self.root, context_report="旧清单.md")
        self.assertEqual(result["report"], str(self.old.resolve()))
        self.assertEqual(result["selected_by"], "conversation")

    def test_latest_ignores_profile_guide_comparison_and_internal_draft(self):
        self.put("求职画像.md", "# 求职画像\n| 属性 | 值 |\n|---|---|\n|岗位|Unity|\n")
        self.put("指南.md", "# 岗位指南\n```markdown\n" + REPORT + "```\n")
        self.put("比较分析.md", REPORT.replace("# 岗位报告：Unity非游戏开发", "# 9月21日与9月22日岗位采集对比"))
        self.put(".scratch/fingjob/test/working.md", REPORT)
        result = module.resolve(self.root)
        self.assertEqual(result["report"], str(self.new.resolve()))
        self.assertEqual(len(result["candidates"]), 2)

    def test_missing_explicit_never_falls_back(self):
        with self.assertRaises(ValueError):
            module.resolve(self.root, "没有此文件.md", "新清单.md")

    def test_missing_context_falls_back_with_notice(self):
        result = module.resolve(self.root, context_report="丢失.md")
        self.assertEqual(result["report"], str(self.new.resolve()))
        self.assertTrue(result["warnings"])

    def test_no_reports_and_nonexistent_workspace(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(ValueError):
                module.resolve(empty)
        with self.assertRaises(ValueError):
            module.resolve(self.root / "不存在")

    def test_tie_is_deterministic_and_legacy_headers_supported(self):
        a = self.put("a.md", REPORT.replace("| 公司 |", "| 公司/招聘单位 |"), 50)
        self.put("b.md", REPORT, 50)
        self.assertEqual(module.resolve(self.root)["report"], str(a.resolve()))

    def test_prepare_preserves_original_bytes_and_drafts_are_not_latest(self):
        self.old.write_bytes(b"\xef\xbb\xbf" + REPORT.replace("\n", "\r\n").encode("utf-8"))
        before = self.old.read_bytes()
        result = module.prepare(self.root, "enrich", "2026-09-24", report="旧清单.md")
        self.assertEqual(Path(result["working"]).read_bytes(), before)
        self.assertEqual(Path(result["snapshot"]).read_bytes(), before)
        Path(result["working"]).write_text(REPORT + "新增福利资料。\n", encoding="utf-8")
        self.assertEqual(self.old.read_bytes(), before)
        self.assertNotIn(str(Path(result["working"])), module.resolve(self.root)["candidates"])
        task = json.loads(module.read(result["task"]))
        self.assertEqual(task["budget"]["queries"], 12)
        self.assertEqual(task["status"], "draft")

    def test_publish_retains_notes_adds_suffix_and_refuses_repeat(self):
        original = self.new.read_bytes()
        outputs = []
        for _ in range(2):
            task = module.prepare(self.root, "refresh", "2026-09-24", report="新清单.md")
            working = Path(task["working"])
            working.write_text(REPORT + "\n历史岗位日期：2026-09-20；本轮来源受阻，待核实。\n", encoding="utf-8")
            result = module.publish(task["task"], "合成测试：未取得新的网页证据。")
            outputs.append(result["output"])
            content = module.read(result["output"])
            self.assertIn("用户手工备注：保留特殊字符 & < > 和中文。", content)
            self.assertIn("历史岗位日期：2026-09-20", content)
            self.assertIn("不是岗位发布日期或刷新日期", content)
            with self.assertRaises(ValueError):
                module.publish(task["task"], "重复交付")
        self.assertNotEqual(*outputs)
        self.assertTrue(outputs[1].endswith("_2.md"))
        self.assertEqual(self.new.read_bytes(), original)

    def test_external_explicit_source_outputs_in_workspace_and_notes_source_edit(self):
        external = Path(self.temp.name) / "外部清单.md"
        external.write_text(REPORT, encoding="utf-8")
        task = module.prepare(self.root, "enrich", "2026-09-24", report=str(external))
        external.write_text(REPORT + "外部新注释", encoding="utf-8")
        result = module.publish(task["task"], "历史资料整理。")
        self.assertEqual(Path(result["output"]).parent, self.root)
        self.assertTrue(result["source_changed"])
        self.assertIn("基于任务开始时的快照", module.read(result["output"]))
        self.assertIn("外部新注释", module.read(external))

    def test_incomplete_draft_not_published(self):
        task = module.prepare(self.root, "refresh", "2026-09-24", report="旧清单.md")
        Path(task["working"]).write_text("未完成", encoding="utf-8")
        with self.assertRaises(ValueError):
            module.publish(task["task"], "未完成")
        self.assertEqual(json.loads(module.read(task["task"]))["status"], "draft")

    def test_invalid_date_does_not_create_task(self):
        with self.assertRaises(ValueError):
            module.prepare(self.root, "refresh", "2026-02-30")
        self.assertFalse((self.root / ".scratch").exists())


if __name__ == "__main__":
    unittest.main()
