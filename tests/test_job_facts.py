import copy
import itertools
import unittest
from test_job_report import job, run_record, module


class Facts(unittest.TestCase):
    def copies(self):
        a = job()
        b = copy.deepcopy(a)
        b.update(id='two', job_url='https://other.example.org/job/1')
        return a, b

    def test_complementary_details_and_reordered_input_have_same_output(self):
        a, b = self.copies()
        a['details']['benefits'] = {'text': '五险', 'sources': [a['job_url']]}
        b['details']['work_time'] = {'text': '09:00–18:00', 'sources': [b['job_url']]}
        outputs = []
        original = copy.deepcopy([a, b])
        for records in itertools.permutations([a, b]):
            run = run_record(*records)
            result = module.check(run)
            self.assertEqual(result['errors'], [])
            self.assertEqual(len(result['kept']), 1)
            output = module.render(run, result)
            self.assertIn('五险', output)
            self.assertIn('09:00–18:00', output)
            outputs.append(output)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual([a, b], original)

    def test_salary_and_status_conflicts_are_pending_with_both_sources(self):
        for field in ('salary', 'status'):
            a, b = self.copies()
            if field == 'salary':
                b['salary'].update(min=7000)
            else:
                a['status'], b['status'] = 'open', 'closed'
            run = run_record(a, b)
            result = module.check(run)
            self.assertEqual(len(result['pending']), 1)
            text = module.render(run, result)
            self.assertIn(a['job_url'], text)
            self.assertIn(b['job_url'], text)
            self.assertFalse(result['kept'])

    def test_distinct_requisitions_and_teams_are_not_merged(self):
        for field in ('requisition_id', 'team'):
            a, b = self.copies()
            a[field], b[field] = 'A', 'B'
            self.assertEqual(len(module.check(run_record(a, b))['kept']), 2)

    def test_complementary_core_evidence_is_usable(self):
        a, b = self.copies()
        a['profile_match'] = 'unknown'
        a['evidence'].pop('profile_match')
        b['dates'] = []
        result = module.check(run_record(a, b))
        self.assertEqual(len(result['kept']), 1)

    def test_same_day_different_jobs_stably_ordered(self):
        a, b = self.copies()
        b['title'] = 'Senior developer'
        runs = [run_record(a, b), run_record(b, a)]
        self.assertEqual(*(module.render(r, module.check(r)) for r in runs))

    def test_unknown_record_evidence_cannot_prove_other_records_claim(self):
        a, b = self.copies()
        a['profile_match'] = 'unknown'
        b['evidence'].pop('profile_match')
        result = module.check(run_record(a, b))
        self.assertFalse(result['kept'])
        self.assertEqual(len(result['pending']), 1)

    def test_pending_summary_retains_adjacent_label_and_conflict_context(self):
        record = job()
        record.update(relevance='adjacent', dates=[], notes=['摘要日期与正文不一致，未取较新值'])
        run = run_record(record)
        run['profile']['include_adjacent'] = True
        text = module.render(run, module.check(run))
        self.assertIn('【相关方向】', text)
        self.assertIn('摘要日期与正文不一致', text)
