"""Render-level checks require markdown-it-py only in the test environment."""
import unittest
import copy
from markdown_it import MarkdownIt
from test_job_report import module, job, run_record


class MarkdownOutput(unittest.TestCase):
    def test_report_is_a_real_eight_column_table(self):
        run = run_record(job())
        tokens = MarkdownIt().enable('table').parse(module.render(run, module.check(run)))
        self.assertEqual(sum(t.type == 'table_open' for t in tokens), 1)
        self.assertEqual(sum(t.type == 'th_open' for t in tokens), 8)
        self.assertEqual(sum(t.type == 'td_open' for t in tokens), 8)

    def test_compact_report_preserves_fields_sources_and_specific_limits(self):
        first = job()
        first['details']['duties'] = {'text': '开发数字孪生系统。', 'sources': [first['job_url']], 'status': 'verified'}
        first['evidence']['relevance']['note'] = first['details']['duties']['text']
        first['evidence']['profile_match']['note'] = '本轮不限城市、学历与经验；职责符合目标方向'
        first['details']['benefits'] = {'text': '所查岗位页未披露。', 'sources': [first['job_url']], 'status': 'not_disclosed'}
        first['notes'] = ['此岗位只接受应届生；独立保留具体限制']
        second = copy.deepcopy(first)
        second.update(id='two', title='Senior Unity developer', job_url='https://example.org/jobs/2')
        for evidence in second['evidence'].values():
            evidence['url'] = second['job_url']
        for detail in second['details'].values():
            detail['sources'] = [second['job_url']]
        second['dates'][0]['url'] = second['job_url']
        second['notes'] = []
        run = run_record(first, second)
        run['reserved_queries'] = 1
        run['searches'] = [dict(query='Unity non-game', source='web', phase='discovery', outcome='success', note='长过程日志 ' * 100)]
        run['notes'] = ['受阻网站不代表不存在岗位；未调查全部公司的法律风险']
        before = copy.deepcopy(run)
        text = module.render(run, module.check(run))
        self.assertEqual(run, before)
        self.assertEqual(text, module.render(run, module.check(run)))
        self.assertEqual(module.report_format.check(text)['errors'], [])
        self.assertEqual(text.count('开发数字孪生系统'), 2)
        self.assertEqual(text.count('本轮不限城市、学历与经验；职责符合目标方向'), 1)
        self.assertEqual(text.count('当前开放状态未独立确认'), 1)
        self.assertNotIn('所查岗位页未披露。已查未披露', text)
        self.assertNotIn('长过程日志', text)
        self.assertIn('实际搜索 1 个 query', text)
        self.assertIn(run['notes'][0], text)
        self.assertIn(first['notes'][0], text)
        self.assertIn('- **福利**：已查未披露。[来源](https://example.org/jobs/1)', text)
        for label in module.DETAILS.values():
            self.assertEqual(text.count('- **' + label + '**：'), 2)
        tokens = MarkdownIt().enable('table').parse(text)
        self.assertEqual(sum(t.type == 'th_open' for t in tokens), 8)
        self.assertEqual(sum(t.type == 'td_open' for t in tokens), 16)
        self.assertIn('https://example.org/jobs/1', text)
        self.assertIn('https://example.org/jobs/2', text)

    def test_direction_basis_stays_when_distinct_or_duties_unverified(self):
        for status, note in (('verified', '职责之外的独立方向证据'), ('unverified', 'Synthetic test evidence')):
            with self.subTest(status=status):
                j = job()
                j['details']['duties'] = {'text': 'Synthetic test evidence', 'sources': [j['job_url']], 'status': status}
                j['evidence']['relevance']['note'] = note
                run = run_record(j)
                text = module.render(run, module.check(run))
                self.assertIn('- **方向依据**：' + note, text)
