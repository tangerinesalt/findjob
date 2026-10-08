import copy
import itertools
import unittest
from test_job_report import job, run_record, module


class Facts(unittest.TestCase):
    def copies(self):
        a = job()
        a['identity_key'] = 'confirmed-vacancy-one'
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
        for field in ('requisition_id', 'team', 'identity_key'):
            a, b = self.copies()
            a[field], b[field] = 'A', 'B'
            self.assertEqual(len(module.check(run_record(a, b))['kept']), 2)

    def test_unconfirmed_cross_link_jobs_are_kept_with_possible_relation(self):
        a, b = self.copies()
        for record in (a, b):
            record.pop('identity_key')
        b['salary'].update(min=7000)
        results = [module.check(run_record(*records)) for records in itertools.permutations([a, b])]
        self.assertEqual(results[0], results[1])
        for result in results:
            self.assertEqual(len(result['kept']), 2)
            self.assertFalse(result['pending'])
            self.assertFalse(result['duplicates'])
            for record in result['records']:
                other = b if record['id'] == a['id'] else a
                self.assertTrue(any(other['job_url'] in note and '尚未确认' in note for note in record['notes']))
        outputs = [module.render(run_record(*records), result) for records, result in zip(itertools.permutations([a, b]), results)]
        self.assertEqual(outputs[0], outputs[1])

    def test_one_sided_identity_does_not_merge_cross_link_jobs(self):
        for field in ('requisition_id', 'identity_key'):
            a, b = self.copies()
            for record in (a, b):
                record.pop('identity_key')
            a[field] = 'known-one'
            result = module.check(run_record(a, b))
            self.assertEqual(len(result['kept']), 2)
            self.assertFalse(result['duplicates'])

    def test_unconfirmed_open_and_closed_postings_are_not_a_core_conflict(self):
        a, b = self.copies()
        for record in (a, b):
            record.pop('identity_key')
        a['status'], b['status'] = 'open', 'closed'
        result = module.check(run_record(a, b))
        self.assertEqual(len(result['kept']), 1)
        self.assertEqual(len(result['excluded']), 1)
        self.assertFalse(result['pending'])
        self.assertFalse(result['duplicates'])

    def test_matching_requisition_merges_complementary_sources_without_identity_key(self):
        a, b = self.copies()
        for record in (a, b):
            record.pop('identity_key')
        a['requisition_id'], b['requisition_id'] = ' J123 ', 'j123'
        b['title'] = 'Unity development engineer'
        b['details']['work_time'] = {'text': '09:00–18:00', 'sources': [b['job_url']]}
        result = module.check(run_record(a, b))
        self.assertEqual(len(result['kept']), 1)
        self.assertEqual(len(result['duplicates']), 1)
        self.assertIn('09:00–18:00', module.render(run_record(a, b), result))

    def test_requisition_identity_is_scoped_to_company(self):
        a, b = self.copies()
        a['requisition_id'] = b['requisition_id'] = 'J123'
        b['company'] = 'Another Company'
        result = module.check(run_record(a, b))
        self.assertEqual(len(result['kept']), 2)
        self.assertFalse(result['duplicates'])

    def test_explicit_distinctions_beat_same_canonical_url(self):
        for field in ('requisition_id', 'team', 'identity_key', 'location'):
            a, b = self.copies()
            b['job_url'] = a['job_url'] + '?utm_source=feed'
            a[field], b[field] = 'A', 'B'
            if field == 'location':
                a[field], b[field] = 'Shanghai', 'Beijing'
                run = run_record(a, b)
                run['profile']['locations'] = []
            else:
                run = run_record(a, b)
            result = module.check(run)
            self.assertEqual(len(result['kept']), 2)
            self.assertFalse(result['duplicates'])
            self.assertFalse(any('疑似重复' in note for record in result['records'] for note in record['notes']))

    def test_matching_team_does_not_identify_a_vacancy(self):
        a, b = self.copies()
        for record in (a, b):
            record.pop('identity_key')
            record['team'] = 'Industrial visualization'
        result = module.check(run_record(a, b))
        self.assertEqual(len(result['kept']), 2)
        self.assertFalse(result['duplicates'])

    def test_same_url_with_different_titles_does_not_merge_without_confirmed_identity(self):
        a, b = self.copies()
        for record in (a, b):
            record.pop('identity_key')
        b.update(title='Senior Unity developer', job_url=a['job_url'])
        result = module.check(run_record(a, b))
        self.assertEqual(len(result['kept']), 2)
        self.assertFalse(result['duplicates'])

    def test_tracking_url_merge_does_not_require_a_requisition(self):
        a, b = self.copies()
        for record in (a, b):
            record.pop('identity_key')
        b['job_url'] = a['job_url'] + '/?utm_source=feed#top'
        result = module.check(run_record(a, b))
        self.assertEqual(len(result['kept']), 1)
        self.assertEqual(len(result['duplicates']), 1)

    def test_multi_location_posting_is_not_merged_with_single_location_observation(self):
        a, b = self.copies()
        a['location'], b['location'] = 'Shanghai、Beijing', 'Shanghai'
        result = module.check(run_record(a, b))
        self.assertEqual(len(result['kept']), 2)
        self.assertFalse(result['duplicates'])

    def test_missing_identifier_does_not_bridge_distinct_requisitions(self):
        a, b = self.copies()
        c = copy.deepcopy(a)
        for record in (a, b, c):
            record.pop('identity_key')
        a['requisition_id'], b['requisition_id'] = 'A', 'B'
        c.update(id='three', job_url='https://third.example.org/jobs/1')
        results = [module.check(run_record(*records)) for records in itertools.permutations([a, b, c])]
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(len(results[0]['kept']), 3)
        self.assertFalse(results[0]['duplicates'])

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
