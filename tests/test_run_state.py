import importlib.util
import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_job_report import run_record, job, module as report, ROOT
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

    def test_batch_replay_updates_and_salary_numbers_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            run = run_record()
            run['reserved_queries'] = 2
            state.write(path, run)
            candidate = job()
            candidate['salary'].update(text='8–10K', min=None, max=None, period='unknown')
            payload = {'batch_id': 'one', 'jobs': [candidate],
                       'searches': [{'query': 'Unity 仿真', 'source': 'test', 'outcome': 'success'}],
                       'accesses': [{'url': candidate['job_url'], 'outcome': 'success'}], 'notes': ['下一步核实福利']}
            result = state.batch(path, payload)
            self.assertEqual((result['queries'], result['page_accesses'], result['jobs_recorded']), (1, 1, 1))
            before = path.read_bytes()
            self.assertFalse(state.batch(path, payload)['recorded'])
            self.assertEqual(path.read_bytes(), before)
            changed = copy.deepcopy(payload)
            changed['notes'] = ['不同内容']
            with self.assertRaises(ValueError):
                state.batch(path, changed)
            self.assertEqual(path.read_bytes(), before)
            state.batch(path, {'batch_id': 'two', 'jobs': [{'id': candidate['id'], 'details': {
                'benefits': {'text': '合成福利', 'sources': [candidate['job_url']]}}}], 'notes': ['下一步核实福利']})
            saved = state.read(path)
            self.assertEqual(saved['jobs'][0]['company'], candidate['company'])
            self.assertEqual((saved['jobs'][0]['salary']['min'], saved['jobs'][0]['salary']['max'],
                              saved['jobs'][0]['salary']['period']), (8000, 10000, 'unknown'))
            self.assertEqual(saved['jobs'][0]['details']['benefits']['text'], '合成福利')
            self.assertEqual(len(saved['notes']), 1)
            self.assertEqual(state.status(path, 0)['batches_recorded'], 2)

    def test_batch_budget_failure_does_not_save_part_of_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            state.write(path, {**run_record(), 'reserved_queries': 1})
            before = path.read_bytes()
            payload = {'batch_id': 'over-budget', 'jobs': [job()], 'searches': [
                {'query': query, 'source': 'test', 'outcome': 'success'} for query in ('one', 'two')]}
            with self.assertRaises(ValueError):
                state.batch(path, payload)
            self.assertEqual(path.read_bytes(), before)

    def test_batch_event_ids_share_record_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            state.write(path, {**run_record(), 'reserved_queries': 1})
            event = {'event_id': 'one', 'query': 'test', 'source': 'test', 'outcome': 'success'}
            state.record(path, event)
            result = state.batch(path, {'searches': [event], 'accesses': [
                {'event_id': 'page-one', 'url': 'https://example.org', 'outcome': 'blocked'}]})
            self.assertEqual((result['searches_added'], result['accesses_added']), (0, 1))

    def test_batch_can_save_partial_candidate_before_final_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            state.write(path, run_record())
            state.batch(path, {'jobs': [{'id': 'lead'}], 'notes': ['还需核实岗位详情']})
            self.assertEqual(state.status(path)['jobs_recorded'], 1)
            self.assertTrue(report.check(state.read(path))['errors'])
            candidate = job()
            candidate['id'] = 'lead'
            state.batch(path, {'jobs': [candidate]})
            self.assertEqual(report.check(state.read(path))['errors'], [])

    def test_batch_followup_keeps_markdown_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / '清单.md').write_text(REPORT, encoding='utf-8')
            task = target.prepare(directory, 'enrich', '2026-09-28', queries=2)
            state.batch(task['task'], {'searches': [{'query': '福利', 'source': 'test', 'outcome': 'no_matches'}],
                                        'notes': ['所查岗位页未披露']})
            self.assertEqual(state.read(task['task'])['searches'][0]['phase'], 'enrichment')
            before = Path(task['task']).read_bytes()
            with self.assertRaises(ValueError):
                state.batch(task['task'], {'jobs': [job()]})
            with self.assertRaises(ValueError):
                state.complete(task['task'], Path(directory) / '清单.md')
            self.assertEqual(Path(task['task']).read_bytes(), before)

    def test_complete_checks_current_report_and_is_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            output = Path(directory) / '岗位清单.md'
            run = run_record(job())
            state.write(path, run)
            output.write_text(report.render(run, report.check(run)) + '\n人工补充备注。\n', encoding='utf-8')
            self.assertEqual(state.status(path)['status'], 'in_progress')
            self.assertIsNone(state.status(path)['output'])
            self.assertTrue(state.complete(path, output)['completed'])
            completed = state.status(path)
            self.assertEqual(completed['status'], 'complete')
            self.assertEqual(completed['output'], str(output.resolve()))
            self.assertTrue(completed['completed_at'])
            before = path.read_bytes()
            self.assertFalse(state.complete(path, output)['completed'])
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(ValueError):
                state.batch(path, {'notes': ['交付后追加']})
            with self.assertRaises(ValueError):
                state.record(path, {'query': 'test', 'source': 'test', 'outcome': 'success'})

    def test_complete_rejects_other_report_or_modified_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            output = Path(directory) / '岗位清单.md'
            run = run_record(job())
            state.write(path, run)
            other = copy.deepcopy(run)
            other['jobs'][0]['company'] = 'Other Company'
            output.write_text(report.render(other, report.check(other)), encoding='utf-8')
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                state.complete(path, output)
            self.assertEqual(path.read_bytes(), before)
            output.write_text(report.render(run, report.check(run)), encoding='utf-8')
            state.complete(path, output)
            output.write_text(output.read_text(encoding='utf-8') + '\n已修改\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                state.complete(path, output)

    def test_complete_rejects_missing_and_invalid_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            output = Path(directory) / '岗位清单.md'
            state.write(path, run_record(job()))
            before = path.read_bytes()
            with self.assertRaises(OSError):
                state.complete(path, output)
            output.write_text('# 这不是岗位清单\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                state.complete(path, output)
            self.assertEqual(path.read_bytes(), before)

    def test_complete_rejects_same_rows_with_different_date_or_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            output = Path(directory) / '岗位清单.md'
            run = run_record(job())
            state.write(path, run)
            before = path.read_bytes()
            for change in ('date', 'profile'):
                other = copy.deepcopy(run)
                if change == 'date':
                    other['as_of'] = '2026-09-22'
                else:
                    other['profile']['salary']['min_lower_monthly'] = 5000
                output.write_text(report.render(other, report.check(other)), encoding='utf-8')
                with self.assertRaises(ValueError):
                    state.complete(path, output)
                self.assertEqual(path.read_bytes(), before)
