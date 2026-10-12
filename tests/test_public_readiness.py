"""General-purpose behavior regressions. All jobs are fictional; no network."""
import contextlib
import copy
import io
from pathlib import Path
import tempfile
import unittest

from test_job_report import module as report, job, run_record
from test_run_state import state
from test_report_target import module as target


class PublicReadiness(unittest.TestCase):
    def generic(self):
        value = job()
        value.update(title='Financial analyst', location='Toronto', games='unknown')
        run = run_record(value)
        run['profile'] = report.profile_format.defaults(['Financial analyst'])
        return run

    def result(self, run):
        result = report.check(run)
        self.assertEqual(result['errors'], [])
        return result

    def test_new_init_has_no_implicit_platform_policy(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            p, r = Path(directory) / 'profile.json', Path(directory) / 'run.json'
            profile = report.profile_format.defaults(['Unity developer'])
            report.save(p, profile)
            self.assertEqual(report.main(['init', '--profile', str(p), '--as-of', '2026-09-21', '--run', str(r)]), 0)
            run = report.load(r)
            self.assertEqual(run['profile'], profile)
            self.assertNotIn('platform_policy', run)
            self.assertFalse(run['profile']['exclude_games'])
            self.assertEqual(report.search_budget.summary(run)['total']['limit'], 60)

    def salary(self, period='year', basis='base', lower=60000, upper=84000):
        run = self.generic()
        run['profile']['salary'].update(currency='CAD', requirement={
            'period': period, 'basis': basis, 'min_lower': lower,
            'min_upper': upper, 'original_text': 'Fictional user salary requirement'})
        run['jobs'][0]['salary'].update(currency='CAD', period=period,
                                        min=lower, max=upper, basis=basis)
        return run

    def test_annual_intent_does_not_change_with_installments(self):
        for basis in ('base', 'total'):
            for months in (None, 12, 13):
                run = self.salary(basis=basis)
                run['jobs'][0]['salary']['months'] = months
                self.assertEqual(len(self.result(run)['kept']), 1)

    def test_pay_period_basis_and_conversion(self):
        for period in ('hour', 'day', 'month', 'year'):
            run = self.salary(period=period)
            self.assertEqual(len(self.result(run)['kept']), 1)
            run['jobs'][0]['salary']['min'] -= 1
            self.assertEqual(len(self.result(run)['excluded']), 1)
        for change in ({'currency': 'USD'}, {'period': 'unknown'}, {'basis': 'total'}, {'period': 'hour'}):
            run = self.salary()
            run['jobs'][0]['salary'].update(change)
            self.assertEqual(len(self.result(run)['pending']), 1)
        run = self.salary(lower=78000, upper=104000)
        run['jobs'][0]['salary'].update(period='month', min=6000, max=8000, months=13)
        self.assertEqual(len(self.result(run)['kept']), 1)
        run['jobs'][0]['salary']['months'] = None
        self.assertEqual(len(self.result(run)['pending']), 1)

    def test_salary_requirement_markdown_roundtrip_and_invalid_mix(self):
        p = self.salary()['profile']
        self.assertEqual(report.profile_format.parse(report.profile_format.render(p)), p)
        partial = '\n'.join(line for line in report.profile_format.render(p).splitlines() if not line.startswith('| 薪资原始需求 |'))
        with self.assertRaises(ValueError):
            report.profile_format.parse(partial)
        p['salary']['min_lower_monthly'] = 100
        with self.assertRaises(ValueError):
            report.validate_profile(p)
        old = self.generic()['profile']
        self.assertNotIn('requirement', report.profile_format.parse(report.profile_format.render(old))['salary'])

    def test_same_job_conflicting_salary_basis_stays_pending(self):
        run = self.salary()
        original = run['jobs'][0]
        original['identity_key'] = 'same-confirmed-job'
        second = copy.deepcopy(original)
        second.update(id='other', job_url='https://example.org/other')
        second['salary']['basis'] = 'total'
        run['jobs'].append(second)
        self.assertEqual(len(self.result(run)['pending']), 1)

    def test_event_collision_is_atomic_and_cross_kind_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            run = self.generic()
            run['reserved_queries'] = 5
            report.save(path, run)
            event = {'event_id': 'q1', 'query': 'accountant Shanghai', 'source': 'synthetic', 'outcome': 'success'}
            self.assertTrue(state.record(path, event)['recorded'])
            before = path.read_bytes()
            self.assertFalse(state.record(path, {**event, 'phase': 'discovery', 'note': '', 'budget_bucket': 'general'})['recorded'])
            for page, changed in ((False, {**event, 'query': 'accountant Beijing'}),
                                  (True, {'event_id': 'q1', 'url': 'https://example.org/job', 'outcome': 'success'})):
                with self.assertRaises(ValueError):
                    state.record(path, changed, page)
                self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(ValueError):
                state.batch(path, {'searches': [{**event, 'event_id': 'q2'}, {**event, 'query': 'new'}]})
            self.assertEqual(path.read_bytes(), before)

    def test_publish_rechecks_manually_edited_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.md'
            run = self.generic()
            source.write_text(report.render(run, self.result(run)), encoding='utf-8')
            prepared = target.prepare(directory, 'refresh', '2026-09-21', report=str(source), queries=0)
            task = report.load(prepared['task'])
            task['searches'] = [{'query': 'synthetic', 'source': 'fixture', 'outcome': 'success'}]
            report.save(prepared['task'], task)
            with self.assertRaises(ValueError):
                target.publish(prepared['task'], 'Synthetic only')
            self.assertEqual(report.load(prepared['task'])['status'], 'draft')
            self.assertEqual(list(Path(directory).glob('*_*.md')), [])

    def test_refresh_labels_historical_counts_and_rejects_wrong_totals(self):
        run = self.generic()
        closed = copy.deepcopy(run['jobs'][0])
        closed.update(id='closed', job_url='https://example.org/closed', status='closed')
        run['jobs'].append(closed)
        source = report.render(run, self.result(run))
        updated, summary = report.report_format.apply(source, {'jobs': [{
            'number': '01', 'state': 'pending', 'reason': 'Synthetic access blocked',
            'sources': ['https://example.org/jobs/1'], 'checked_at': '2026-09-21'}]})
        self.assertEqual(summary['remaining'], 0)
        self.assertIn('搜索时的未纳入与去重（历史记录）', updated)
        self.assertEqual(report.report_format.check(updated)['errors'], [])
        self.assertTrue(report.report_format.check(updated.replace('剔除 1 条', '剔除 7 条'))['errors'])

    def test_extra_budget_and_unknown_dates_are_independent(self):
        run = self.generic()
        run.update(relative_date_mode='profile', platform_policy={
            'version': 2, 'extra_queries': {'yupao': 5, 'linkedin': 0},
            'linkedin_age_months': 0, 'linkedin_allow_unknown': False})
        value = run['jobs'][0]
        value.update(job_url='https://linkedin.com/jobs/view/1', dates=[])
        self.assertEqual(len(self.result(run)['pending']), 1)
        self.assertEqual(report.search_budget.summary(run)['total']['limit'], 65)
        run['platform_policy']['linkedin_age_months'] = 3
        self.assertEqual(len(self.result(run)['pending']), 1)
        run['platform_policy']['linkedin_allow_unknown'] = True
        self.assertEqual(len(self.result(run)['kept']), 1)

    def test_legacy_disabled_age_policy_remains_disabled_in_report(self):
        run = self.generic()
        run['platform_policy'] = report.search_budget.default_policy()
        run['platform_policy']['linkedin_allow_unknown'] = False
        value = run['jobs'][0]
        value.update(job_url='https://linkedin.com/jobs/view/1', dates=[])
        self.assertEqual(len(self.result(run)['pending']), 1)
        self.assertIn('LinkedIn日期例外未启用', report.render(run, self.result(run)))

    def test_shareable_source_label_does_not_expose_absolute_path(self):
        run = self.generic()
        run['coverage'] = report.lead_tracking.initial()
        run['leads'] = []
        run['coverage']['sources'] = [{'path': r'C:\Users\PrivateName\PrivateProject\previous.md', 'note': '历史线索'}]
        content = report.render(run, self.result(run))
        self.assertIn('previous.md', content)
        self.assertNotIn('PrivateName', content)
        self.assertNotIn('PrivateProject', content)

    def test_new_report_omits_unrequested_empty_company_fields(self):
        run = self.generic()
        run['report_options'] = {'company_details': False}
        content = report.render(run, self.result(run))
        self.assertNotIn('**法律风险**', content)
        run['jobs'][0]['details']['legal_risk'] = {'text': '仅合成资料', 'sources': ['https://example.org/legal']}
        self.assertIn('仅合成资料', report.render(run, self.result(run)))

    def test_relative_dates_follow_profile_without_exception(self):
        for host in ('linkedin.com', 'example.org'):
            run = self.generic()
            run['relative_date_mode'] = 'profile'
            value = run['jobs'][0]
            value.update(job_url='https://' + host + '/jobs/1', dates=[])
            value['relative_dates'] = [{'text': '3 days ago', 'url': value['job_url'],
                'note': 'job body time', 'observed_at': '2026-09-21', 'kind': 'published'}]
            self.assertEqual(len(self.result(run)['kept']), 1)
            run['profile']['freshness']['published_months'] = 0
            self.assertEqual(len(self.result(run)['excluded']), 1)
            run['profile']['freshness'].update(published_months=2, mode='all')
            self.assertEqual(len(self.result(run)['pending']), 1)
            value['relative_dates'][0]['observed_at'] = '2026-01-21'
            self.assertEqual(len(self.result(run)['excluded']), 1)

    def test_generic_roles_and_core_conditions(self):
        for role in ('Accountant', 'Game developer', 'Designer', 'Operations intern'):
            run = self.generic()
            run['profile']['target_roles'] = [role]
            run['jobs'][0].update(title=role, games='yes', relevance='adjacent')
            self.assertEqual(len(self.result(run)['kept']), 1)
            run['profile']['include_adjacent'] = False
            self.assertEqual(len(self.result(run)['excluded']), 1)
            run['profile']['include_adjacent'] = True
            run['jobs'][0]['profile_match'] = 'no'
            self.assertEqual(len(self.result(run)['excluded']), 1)

    def test_relative_and_absolute_types_can_jointly_satisfy_all(self):
        run = self.generic()
        run['relative_date_mode'] = 'profile'
        run['profile']['freshness'].update(published_months=1, refreshed_months=0, mode='all')
        j = run['jobs'][0]
        j['dates'][0]['value'] = run['as_of']
        j['relative_dates'] = [{'kind': 'published', 'text': '3 days ago', 'observed_at': run['as_of'],
                                'url': j['job_url'], 'note': 'job body time'}]
        self.assertEqual(len(self.result(run)['kept']), 1)
        j['dates'].append({'kind': 'published', 'value': '2026-01-01', 'url': j['job_url'], 'note': 'Synthetic publication'})
        self.assertEqual(len(self.result(run)['pending']), 1)


if __name__ == '__main__':
    unittest.main()
