import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from test_job_report import run_record, ROOT
from test_report_target import module as target, REPORT

spec = importlib.util.spec_from_file_location('run_state', ROOT / 'skills/job-search/scripts/run_state.py')
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


class Ledger(unittest.TestCase):
    def test_budget_resume_idempotency_and_page_cost_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            run = run_record()
            run['reserved_queries'] = 1
            state.write(path, run)
            event = {'event_id': 'call-1', 'query': 'Unity 仿真', 'source': 'test', 'outcome': 'success', 'direction': '工业仿真', 'new_jobs': 1}
            self.assertTrue(state.record(path, event)['recorded'])
            self.assertFalse(state.record(path, event)['recorded'])
            with self.assertRaises(ValueError):
                state.record(path, {**event, 'event_id': 'call-2'})
            state.record(path, {'url': 'https://example.org/1', 'outcome': 'blocked'}, page=True)
            result = state.status(path)
            self.assertEqual((result['queries'], result['page_accesses']), (1, 1))
            self.assertEqual(result['directions'], ['工业仿真'])

    def test_followup_budget_override_and_small_resume_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / '清单.md').write_text(REPORT, encoding='utf-8')
            task = target.prepare(directory, 'enrich', '2026-09-28', queries=1)
            state.record(task['task'], {'query': '公司 年报', 'source': 'test', 'outcome': 'no_matches'})
            with self.assertRaises(ValueError):
                state.record(task['task'], {'query': '第二次', 'source': 'test', 'outcome': 'success'})
            summary = state.status(task['task'], limit=0)
            self.assertEqual(summary['remaining_queries'], 0)
            self.assertEqual(summary['recent_searches'], [])
