"""Scoped source-policy integration checks; all records are synthetic."""
import contextlib
import copy
import io
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from test_job_report import module as report, job, run_record, SKILL
from test_report_target import module as target
from test_run_state import state


def policy_run(*jobs):
    data = run_record(*jobs)
    data.update(as_of='2026-10-09', platform_policy=report.search_budget.default_policy(),
                reserved_platform_queries={'yupao': 0, 'linkedin': 0})
    return data


def linkedin_job(text=None, observed_at='2026-10-09'):
    value = job()
    value['job_url'] = 'https://cn.linkedin.com/jobs/view/test-123'
    value['dates'] = []
    for evidence in value['evidence'].values():
        evidence['url'] = value['job_url']
    if text is not None:
        value['relative_dates'] = [{'text': text, 'url': value['job_url'],
                                    'note': '正文岗位时间（合成测试）', 'observed_at': observed_at}]
    return value


class PlatformIntegration(unittest.TestCase):
    def check(self, data):
        result = report.check(data)
        self.assertEqual(result['errors'], [])
        return result

    def test_other_platforms_preserve_original_date_and_hard_filters(self):
        for host in ('m.yupao.com', 'www.zhaopin.com', 'www.liepin.com', 'www.zhipin.com',
                     'www.nowcoder.com', 'www.shixiseng.com', 'www.indeed.com', 'www.glassdoor.com'):
            for day, kind in ((None, None), ('2026-07-10', 'published'), ('2026-08-09', 'published'),
                              ('2026-09-08', 'refreshed'), ('2026-09-09', 'refreshed')):
                for change in ({}, {'games': 'yes'}, {'recruiter': 'headhunter'}, {'status': 'closed'}):
                    with self.subTest(host=host, day=day, change=change):
                        value = job()
                        value['job_url'] = 'https://' + host + '/jobs/123'
                        value.update(change)
                        value['dates'] = [] if day is None else [{'value': day, 'kind': kind,
                            'url': value['job_url'], 'note': 'Synthetic position date'}]
                        legacy = policy_run(value)
                        del legacy['platform_policy']
                        del legacy['reserved_platform_queries']
                        actual = self.check(policy_run(value))
                        expected = self.check(legacy)
                        for key in ('kept', 'pending', 'excluded', 'duplicates'):
                            self.assertEqual(actual[key], expected[key])

    def test_linkedin_unknown_and_relative_dates_render_and_complete(self):
        for text in (None, '3天前', '2 weeks ago', '2个月前'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                data = policy_run(linkedin_job(text))
                result = self.check(data)
                self.assertEqual(len(result['kept']), 1)
                self.assertIsNone(result['kept'][0]['date'])
                content = report.render(data, result)
                self.assertEqual(report.report_format.check(content)['errors'], [])
                self.assertIn(text or '日期未核实', content)
                self.assertNotIn('2026-09-20（刷新）', content)
                ledger, output = Path(directory) / 'run.json', Path(directory) / 'report.md'
                report.save(ledger, data)
                output.write_text(content, encoding='utf-8')
                self.assertTrue(state.complete(ledger, output)['completed'])

    def test_date_exception_cannot_release_other_hard_condition_failures(self):
        for change, expected in (({'status': 'closed'}, 'excluded'), ({'games': 'yes'}, 'excluded'),
                                 ({'recruiter': 'headhunter'}, 'excluded'),
                                 ({'games': 'unknown'}, 'pending'), ({'relevance': 'unknown'}, 'pending')):
            value = linkedin_job('3天前')
            value.update(change)
            self.assertEqual(len(self.check(policy_run(value))[expected]), 1)
        value = linkedin_job()
        value['salary'].update(text='100-120元/月', min=100, max=120)
        self.assertEqual(len(self.check(policy_run(value))['excluded']), 1)

    def test_old_run_and_explicit_opt_out_do_not_receive_exception(self):
        value = linkedin_job('3天前')
        legacy = run_record(value)
        self.assertEqual(len(self.check(legacy)['pending']), 1)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            path = Path(directory) / 'run.json'
            self.assertEqual(report.main(['init', '--profile', str(SKILL / 'references/presets/unity-non-game.json'),
                                         '--as-of', '2026-10-09', '--run', str(path), '--no-platform-policy']), 0)
            self.assertNotIn('platform_policy', report.load(path))

    def test_same_confirmed_vacancy_keeps_known_old_date(self):
        linked = linkedin_job('3天前')
        linked.update(id='linkedin', identity_key='confirmed-requisition')
        original = copy.deepcopy(linked)
        original.update(id='original', job_url='https://employer.example/jobs/123')
        original.pop('relative_dates')
        original['dates'] = [{'value': '2026-07-09', 'kind': 'published',
                             'url': original['job_url'], 'note': 'Synthetic original position date'}]
        result = self.check(policy_run(original, linked))
        self.assertEqual(len(result['excluded']), 1)
        self.assertEqual(len(result['duplicates']), 1)
        reversed_result = self.check(policy_run(linked, original))
        self.assertEqual(result, reversed_result)

    def test_followups_inherit_date_policy_without_extra_query_credit(self):
        content = report.render(policy_run(linkedin_job('3天前')), self.check(policy_run(linkedin_job('3天前'))))
        for mode in ('refresh', 'enrich'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'report.md'
                source.write_text(content, encoding='utf-8')
                prepared = target.prepare(directory, mode, '2026-10-10', report=str(source))
                task = report.load(prepared['task'])
                self.assertEqual(task['platform_policy'], report.search_budget.default_policy())
                usage = report.search_budget.summary(task)
                self.assertEqual(usage['total']['limit'], 60 if mode == 'refresh' else 12)
                for bucket in ('yupao', 'linkedin'):
                    self.assertEqual(usage['pools'][bucket]['limit'], 0)
                    with self.assertRaises(ValueError):
                        state.record(prepared['task'], {'query': 'site:linkedin.com Unity', 'source': 'web',
                                     'outcome': 'success', 'budget_bucket': bucket})

    def test_complete_rejects_removed_or_tampered_policy_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            data = policy_run(linkedin_job())
            ledger, output = Path(directory) / 'run.json', Path(directory) / 'report.md'
            report.save(ledger, data)
            content = report.render(data, self.check(data))
            for altered in (content.replace('"linkedin_age_months":3', '"linkedin_age_months":4'),
                            '\n'.join(line for line in content.splitlines() if not line.startswith('平台例外：')) + '\n'):
                output.write_text(altered, encoding='utf-8')
                with self.assertRaises(ValueError):
                    state.complete(ledger, output)

    def test_followup_publish_cannot_lose_or_change_inherited_policy(self):
        data = policy_run(linkedin_job())
        content = report.render(data, self.check(data))
        for mode in ('refresh', 'enrich'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'report.md'
                source.write_text(content, encoding='utf-8')
                prepared = target.prepare(directory, mode, '2026-10-10', report=str(source))
                working = Path(prepared['working'])
                for altered in (content.replace('"linkedin_age_months":3', '"linkedin_age_months":4'),
                                '\n'.join(line for line in content.splitlines() if not line.startswith('<!-- findjob:platform-policy ')) + '\n',
                                '\n'.join(line for line in content.splitlines() if not line.startswith('平台例外：')) + '\n'):
                    working.write_text(altered, encoding='utf-8')
                    with self.assertRaises(ValueError):
                        target.publish(prepared['task'], 'Synthetic tamper test')
                working.write_text(content, encoding='utf-8')
                self.assertTrue(Path(target.publish(prepared['task'], 'Synthetic valid follow-up')['output']).is_file())

    def test_policy_marker_handles_windows_lines_and_rejects_malformed_marker(self):
        data = policy_run(linkedin_job())
        content = report.render(data, self.check(data))
        self.assertEqual(target.inherited_platform_policy(content.replace('\n', '\r\n')), data['platform_policy'])
        with self.assertRaises(ValueError):
            target.inherited_platform_policy('<!-- findjob:platform-policy broken -->\r\n')

    def test_relative_time_on_other_platform_cannot_activate_linkedin_exception(self):
        value = linkedin_job('3天前')
        value['job_url'] = 'https://www.zhaopin.com/jobs/123'
        value['relative_dates'][0]['url'] = value['job_url']
        self.assertEqual(len(self.check(policy_run(value))['pending']), 1)


if __name__ == '__main__':
    unittest.main()
