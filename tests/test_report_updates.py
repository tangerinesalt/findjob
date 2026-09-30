import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_job_report import module as report, job, run_record
from test_report_target import module as target

fmt = report.report_format


class Updates(unittest.TestCase):
    def test_renamed_plugin_can_enrich_a_legacy_report(self):
        source = self.source().replace('<!-- findjob:report v2 -->', '<!-- fingjob:report v2 -->')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '旧清单.md'
            path.write_text(source, encoding='utf-8')
            task = target.prepare(directory, 'enrich', '2026-09-30', report=str(path))
            task_dir = Path(task['task']).parent
            self.assertEqual(task_dir.parent.name, 'findjob')
            legacy_dir = Path(directory) / '.scratch' / 'fingjob' / task_dir.name
            legacy_dir.parent.mkdir(parents=True)
            task_dir.rename(legacy_dir)
            legacy_task = legacy_dir / 'task.json'
            self.assertEqual(target.inspect_report(str(legacy_task), '01', ['benefits'])['text'], '- **福利**：未核实。')
            result = target.publish(str(legacy_task), '旧任务更名后续接')
            text = Path(result['output']).read_text(encoding='utf-8')
            self.assertIn('<!-- fingjob:report v2 -->', text)
            self.assertEqual(fmt.check(text)['errors'], [])
            self.assertEqual(path.read_text(encoding='utf-8'), source)

    def source(self):
        run = run_record(job())
        return report.render(run, report.check(run)) + '\n用户注释：保留原文 | C++。\n'

    def test_field_patch_retains_every_untouched_line(self):
        source = self.source()
        detail = {'text': '五险一金', 'sources': ['https://example.org/benefits'], 'scope': '公司口径', 'observed_at': '2026-09-28'}
        updated, _ = fmt.apply(source, {'jobs': [{'number': '01', 'details': {'benefits': detail}}]})
        self.assertIn(fmt.detail_line('benefits', detail), updated)
        self.assertEqual(source.replace('- **福利**：未核实。', fmt.detail_line('benefits', detail)), updated)

    def test_refresh_moves_history_and_updates_counts(self):
        source = self.source()
        updated, summary = fmt.apply(source, {'jobs': [{'number': '01', 'state': 'pending', 'reason': '来源受阻', 'sources': ['https://example.org/jobs/1'], 'checked_at': '2026-09-28'}], 'window': {'as_of': '2026-09-28', 'published_since': '2026-07-28', 'refreshed_since': '2026-08-28'}})
        self.assertEqual(fmt.check(updated)['errors'], [])
        self.assertEqual(summary['remaining'], 0)
        self.assertIn('0 条岗位、0 家单位', updated)
        self.assertIn('#### 历史 01', updated)
        self.assertIn('用户注释：保留原文', updated)
        self.assertIn('2026-07-28', updated)

    def test_basic_salary_is_synchronized(self):
        updated, _ = fmt.apply(self.source(), {'jobs': [{'number': '01', 'basic': {'salary': '7–10K/月'}, 'reason': '本轮正文薪资。', 'sources': ['https://example.org/jobs/1'], 'checked_at': '2026-09-28'}]})
        self.assertEqual(fmt.check(updated)['errors'], [])
        self.assertIn('- **基本信息**：Shanghai；7–10K/月', updated)
        self.assertIn('| Shanghai | 7–10K/月 |', updated)
        self.assertNotIn('。。', updated)

    def test_date_change_requires_own_evidence(self):
        patch = {'jobs': [{'number': '01', 'basic': {'date': '2026-09-27（刷新）'}, 'reason': '更新', 'sources': ['https://example.org/jobs/1'], 'checked_at': '2026-09-28'}]}
        with self.assertRaises(ValueError):
            fmt.apply(self.source(), patch)

    def test_missing_and_blocked_are_not_reported_as_undisclosed(self):
        self.assertIn('未核实', fmt.detail_line('work_time'))
        self.assertIn('来源受阻', fmt.detail_line('work_time', {'text': '', 'sources': [], 'status': 'blocked'}))
        self.assertIn('已查未披露', fmt.detail_line('work_time', {'text': '', 'sources': [], 'status': 'not_disclosed'}))
        self.assertIn('未核实', fmt.detail_line('insured', {'text': '未取得对应法人年度数据', 'sources': [], 'status': 'unverified'}))

    def test_publication_rejects_inconsistent_standard_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / '清单.md'
            source.write_text(self.source(), encoding='utf-8')
            task = target.prepare(directory, 'enrich', '2026-09-28', report=str(source))
            working = Path(task['working'])
            working.write_text(self.source().replace('| Shanghai |', '| 北京 |'), encoding='utf-8')
            with self.assertRaises(ValueError):
                target.publish(task['task'], '应拒绝不同步的基本信息')
            self.assertEqual(json.loads(target.read(task['task']))['status'], 'draft')

    def test_inspection_limits_output_to_requested_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / '清单.md'
            source.write_text(self.source(), encoding='utf-8')
            task = target.prepare(directory, 'enrich', '2026-09-28', report=str(source))
            value = target.inspect_report(task['task'], '01', ['benefits'])
            self.assertEqual(value['text'], '- **福利**：未核实。')
            self.assertLess(len(json.dumps(value)), len(self.source()))

    def test_legacy_bad_separator_is_repaired_without_json_run(self):
        old = self.source().replace('|---|---|---|---|---|---|---|---|', '|---|---|---|---|---|---|---|---|---|')
        updated, _ = fmt.apply(old, {'jobs': []})
        self.assertEqual(fmt.check(updated)['errors'], [])

    def test_merged_observations_keep_individual_sources_and_scope(self):
        a, b = job(), job()
        b.update(id='two', job_url='https://example.org/other')
        a['details']['benefits'] = {'text': '班车', 'sources': [a['job_url']], 'scope': '本岗'}
        b['details']['benefits'] = {'text': '培训', 'sources': [b['job_url']], 'scope': '公司'}
        run = run_record(a, b)
        text = report.render(run, report.check(run))
        self.assertIn('班车。（本岗）[来源](https://example.org/jobs/1)', text)
        self.assertIn('培训。（公司）[来源](https://example.org/other)', text)

    def test_unknown_explanation_survives_search_consolidation_and_render(self):
        record = job()
        record['details']['insured'] = {'text': '未取得对应法人年度数据', 'sources': [], 'status': 'unverified'}
        record['dates'][0]['note'] += '。'
        record['evidence']['relevance']['note'] += '。'
        run = run_record(record)
        result = report.check(run)
        self.assertEqual(result['errors'], [])
        text = report.render(run, result)
        self.assertIn('未取得对应法人年度数据', text)
        self.assertNotIn('。。', text)
