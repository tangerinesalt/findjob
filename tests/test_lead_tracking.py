"""Coverage is a workflow guard, not a new job filter. All fixtures are synthetic."""
import copy
from pathlib import Path
import tempfile
import unittest
from test_job_report import job, run_record, module as report
from test_run_state import state
from test_report_target import module as target


tracking = report.lead_tracking


def current(*jobs):
    run = run_record(*jobs)
    run.update(coverage=tracking.initial(), leads=[])
    run['coverage']['source_note'] = 'Synthetic request without prior reports'
    return run


def lead(candidate=None):
    candidate = candidate or job()
    return {'id': 'known', 'company': candidate['company'], 'title': candidate['title'],
            'url': candidate['job_url'], 'state': 'queued', 'important': True,
            'origins': [{'source': 'previous-report.md', 'observed_at': '2026-09-20', 'previous_state': 'kept'}]}


class Coverage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'run.json'
        self.output = Path(self.temp.name) / 'report.md'

    def render(self):
        run = state.read(self.path)
        result = report.check(run)
        self.assertEqual(result['errors'], [])
        self.output.write_text(report.render(run, result), encoding='utf-8')

    def test_queued_important_blocks_only_completion_not_draft(self):
        run = current(job())
        run['leads'] = [lead()]
        run['coverage']['stop_reason'] = 'Checked available routes'
        state.write(self.path, run)
        self.render()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, '重要线索'):
            state.complete(self.path, self.output)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(state.status(self.path)['coverage']['unresolved_important'], ['known'])

    def test_deferred_with_reason_can_finish_and_is_visible(self):
        state.write(self.path, current())
        state.batch(self.path, {'leads': [{**lead(), 'state': 'deferred', 'reason': 'No usable public alternate route'}],
                               'coverage': {'stop_reason': 'Available routes exhausted; documented unresolved lead'}})
        self.render()
        self.assertIn('No usable public alternate route', self.output.read_text(encoding='utf-8'))
        self.assertTrue(state.complete(self.path, self.output)['completed'])

    def test_invalid_reason_or_event_reference_rolls_back_whole_batch(self):
        state.write(self.path, current())
        before = self.path.read_bytes()
        for item in ({**lead(), 'state': 'deferred'},
                     {**lead(), 'state': 'reviewed', 'job_id': 'one', 'attempt_ids': ['missing']}):
            with self.assertRaises(ValueError):
                state.batch(self.path, {'jobs': [job()], 'leads': [item]})
            self.assertEqual(self.path.read_bytes(), before)

    def test_job_and_event_in_same_batch_link_pending_without_claiming_qualified(self):
        candidate = job()
        candidate['recruiter'] = 'unknown'
        state.write(self.path, current())
        payload = {'batch_id': 'review', 'jobs': [candidate],
                   'accesses': [{'event_id': 'page', 'url': candidate['job_url'], 'outcome': 'success'}],
                   'leads': [{**lead(), 'state': 'reviewed', 'job_id': 'one', 'attempt_ids': ['page']}],
                   'coverage': {'stop_reason': 'Employer unresolved after available public sources'}}
        state.batch(self.path, payload)
        before = self.path.read_bytes()
        self.assertFalse(state.batch(self.path, payload)['recorded'])
        self.assertEqual(self.path.read_bytes(), before)
        self.render()
        self.assertIn('转待核实', self.output.read_text(encoding='utf-8'))
        self.assertTrue(state.complete(self.path, self.output)['completed'])

    def test_cross_url_match_requires_explicit_identity_note(self):
        state.write(self.path, current(job()))
        other = {**lead(), 'url': 'https://example.org/alternate/1', 'state': 'reviewed',
                 'job_id': 'one', 'attempt_ids': ['page']}
        event = {'event_id': 'page', 'url': job()['job_url'], 'outcome': 'success'}
        with self.assertRaisesRegex(ValueError, '同岗依据'):
            state.batch(self.path, {'leads': [other], 'accesses': [event]})
        other['match_note'] = 'Same explicit requisition number and employer'
        state.batch(self.path, {'leads': [other], 'accesses': [event]})

    def test_changed_coverage_report_is_rejected_even_when_rows_match(self):
        run = current(job())
        run['coverage']['stop_reason'] = 'Available routes checked'
        state.write(self.path, run)
        self.render()
        raw = self.output.read_text(encoding='utf-8')
        self.output.write_text(raw.replace('Available routes checked', 'Different unrecorded reason'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '覆盖记录'):
            state.complete(self.path, self.output)
        self.output.write_text(raw.replace(tracking.START, ''), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '覆盖记录'):
            state.complete(self.path, self.output)

    def test_shared_url_does_not_justify_linking_another_role(self):
        state.write(self.path, current(job()))
        item = {**lead(), 'title': 'Another role', 'state': 'reviewed', 'job_id': 'one', 'attempt_ids': ['page']}
        with self.assertRaisesRegex(ValueError, '同岗依据'):
            state.batch(self.path, {'leads': [item], 'accesses': [
                {'event_id': 'page', 'url': job()['job_url'], 'outcome': 'success'}]})

    def test_additional_work_invalidates_old_stop_reason(self):
        run = current()
        run['coverage']['stop_reason'] = 'Earlier stop'
        state.write(self.path, run)
        state.record(self.path, {'event_id': 'later', 'url': job()['job_url'], 'outcome': 'blocked'}, page=True)
        self.assertEqual(state.read(self.path)['coverage']['stop_reason'], '')
        self.render()
        with self.assertRaisesRegex(ValueError, 'stop_reason'):
            state.complete(self.path, self.output)

    def test_sources_required_but_no_history_explanation_is_sufficient(self):
        run = current(job())
        run['coverage'].update(source_note='', stop_reason='Done')
        state.write(self.path, run)
        self.render()
        with self.assertRaisesRegex(ValueError, 'source_note'):
            state.complete(self.path, self.output)
        state.batch(self.path, {'coverage': {'source_note': 'No relevant earlier reports in selected scope'}})
        self.render()
        self.assertTrue(state.complete(self.path, self.output)['completed'])

    def test_seed_deduplicates_provenance_without_copying_facts_or_resetting_state(self):
        state.write(self.path, current())
        for name in ('old-a', 'old-b'):
            source = Path(self.temp.name) / (name + '.json')
            state.write(source, run_record(job()))
            state.seed(self.path, source)
        saved = state.read(self.path)
        self.assertEqual(saved['jobs'], [])
        self.assertEqual(saved['searches'], [])
        self.assertEqual(len(saved['leads']), 1)
        self.assertEqual(len(saved['leads'][0]['origins']), 2)
        self.assertNotIn('salary', saved['leads'][0])
        state.batch(self.path, {'leads': [{'id': saved['leads'][0]['id'], 'state': 'deferred', 'reason': 'Budget exhausted'}]})
        state.seed(self.path, source)
        self.assertEqual(state.read(self.path)['leads'][0]['state'], 'deferred')

    def test_shared_announcement_roles_and_optional_pending_are_not_lost(self):
        one, two = job(), job()
        two.update(id='two', title='Different position', recruiter='unknown')
        source = Path(self.temp.name) / 'old.json'
        state.write(source, run_record(one, two))
        state.write(self.path, current())
        state.seed(self.path, source)
        self.assertEqual(len(state.read(self.path)['leads']), 1)
        state.seed(self.path, source, include_pending=True)
        self.assertEqual(len(state.read(self.path)['leads']), 2)

    def test_legacy_run_is_not_migrated_or_blocked(self):
        legacy = run_record(job())
        state.write(self.path, legacy)
        self.render()
        self.assertNotIn(tracking.START, self.output.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            state.batch(self.path, {'coverage': {'stop_reason': 'attempted migration'}})
        self.assertTrue(state.complete(self.path, self.output)['completed'])

    def test_coverage_does_not_change_job_decisions(self):
        for change in ({}, {'games': 'yes'}, {'recruiter': 'unknown'}, {'status': 'closed'}):
            candidate = {**job(), **change}
            old = report.check(run_record(candidate))
            new = report.check(current(candidate))
            self.assertEqual(old, new)

    def test_new_report_can_be_enriched_and_refreshed_without_rewriting_search_history(self):
        run = current(job())
        run['coverage']['stop_reason'] = 'Synthetic search completed'
        state.write(self.path, run)
        self.render()
        original = self.output.read_text(encoding='utf-8')
        history = original.split(tracking.START)[1].split(tracking.END)[0]
        self.assertIn(run['as_of'], history)
        for mode in ('enrich', 'refresh'):
            task = target.prepare(self.temp.name, mode, '2026-09-28', report=str(self.output))
            task_data = state.read(task['task'])
            self.assertNotIn('coverage', task_data)
            self.assertNotIn('reserved_platform_queries', task_data)
            patch = {'jobs': [{'number': '01', 'details': {'benefits': {
                'text': 'Synthetic benefit', 'sources': ['https://example.org/benefits']}}}]}
            if mode == 'refresh':
                patch = {'jobs': [{'number': '01', 'state': 'pending', 'reason': 'Current source unavailable',
                                  'sources': ['https://example.org/jobs/1'], 'checked_at': '2026-09-28'}]}
            working = Path(task['working'])
            updated, _ = report.report_format.apply(working.read_text(encoding='utf-8'), patch)
            working.write_text(updated, encoding='utf-8')
            delivered = target.publish(task['task'], 'Synthetic follow-up')
            content = Path(delivered['output']).read_text(encoding='utf-8')
            self.assertEqual(report.report_format.check(content)['errors'], [])
            self.assertIn(tracking.START + history + tracking.END, content)
            self.assertEqual(self.output.read_text(encoding='utf-8'), original)

    def test_extra_pool_exhaustion_still_allows_general_on_same_platform(self):
        for platform, domain in (('yupao', 'yupao.com'), ('linkedin', 'linkedin.com')):
            run = current()
            run.update(platform_policy=report.search_budget.default_policy(), reserved_platform_queries={'yupao': 0, 'linkedin': 0})
            report.search_budget.reserve(run, 5, platform)
            for i in range(5):
                state.add_event(run, {'query': f'site:{domain} Unity {i}', 'source': 'test', 'outcome': 'success', 'budget_bucket': platform})
            report.search_budget.reserve(run, 1, 'general')
            state.add_event(run, {'query': f'site:{domain} simulation', 'source': 'test', 'outcome': 'success', 'budget_bucket': 'general'})
            self.assertEqual(report.search_budget.summary(run)['pools']['general']['used'], 1)

    def test_version_observations_preserved_and_explicit_conflicts_still_block(self):
        candidate = job()
        candidate['dates'].append({**candidate['dates'][0], 'value': '2026-09-18', 'note': 'Earlier page version of same refresh field'})
        self.assertEqual(len(report.check(current(candidate))['kept']), 1)
        self.assertEqual(len(report.check(current(candidate))['records'][0]['dates']), 2)
        candidate['merge_conflicts'] = [{'field': 'job_time', 'values': [
            {'value': '2026-07-01', 'url': candidate['job_url']},
            {'value': '2026-09-20', 'url': candidate['job_url']}]}]
        self.assertEqual(len(report.check(current(candidate))['pending']), 1)
