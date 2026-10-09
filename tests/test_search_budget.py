"""Independent-pool regressions. All calls and records are synthetic and offline."""
import copy
from pathlib import Path
import tempfile
import unittest

from test_job_report import run_record
from test_run_state import state


budget = state.search_budget


def new_run(*jobs):
    run = run_record(*jobs)
    run['platform_policy'] = budget.default_policy()
    run['reserved_platform_queries'] = {'yupao': 0, 'linkedin': 0}
    return run


def call(bucket='general', **changes):
    domain = {'yupao': 'yupao.com', 'linkedin': 'linkedin.com'}.get(bucket)
    event = {'query': 'Unity 工业' + (' site:' + domain if domain else ''),
             'source': 'web', 'phase': 'discovery', 'outcome': 'success',
             'budget_bucket': bucket}
    event.update(changes)
    return event


class SearchBudget(unittest.TestCase):
    def test_default_policy_is_fresh_and_reservation_does_not_change_profile(self):
        policy = budget.default_policy()
        policy['extra_queries']['yupao'] = 0
        self.assertEqual(budget.default_policy()['extra_queries']['yupao'], 5)
        run = new_run()
        profile = copy.deepcopy(run['profile'])
        budget.reserve(run, 60)
        budget.reserve(run, 5, 'yupao')
        summary = budget.reserve(run, 5, 'linkedin')
        self.assertEqual(run['profile'], profile)
        self.assertEqual(run['reserved_queries'], 60)
        self.assertEqual(run['reserved_platform_queries'], {'yupao': 5, 'linkedin': 5})
        self.assertEqual(summary['total'], {'limit': 70, 'reserved': 70, 'used': 0,
                                          'remaining': 70, 'available': 70})

    def test_full_60_plus_5_plus_5_are_independent_and_enrichment_stays_12(self):
        run = new_run()
        budget.reserve(run, 60)
        budget.reserve(run, 5, 'yupao')
        budget.reserve(run, 5, 'linkedin')
        for _ in range(12):
            state.add_event(run, call(phase='enrichment'))
        with self.assertRaises(ValueError):
            state.add_event(run, call(phase='enrichment'))
        for _ in range(48):
            state.add_event(run, call())
        for bucket in ('yupao', 'linkedin'):
            for _ in range(5):
                state.add_event(run, call(bucket))
        budget.validate(run)
        summary = budget.summary(run)
        self.assertEqual(summary['total']['used'], 70)
        self.assertEqual(summary['total']['remaining'], 0)
        self.assertEqual(summary['pools']['general']['used'], 60)
        for bucket in ('general', 'yupao', 'linkedin'):
            with self.subTest(bucket=bucket), self.assertRaises(ValueError):
                state.add_event(run, call(bucket))
        self.assertEqual(len(run['searches']), 70)

    def test_general_cannot_borrow_idle_platform_capacity(self):
        run = new_run()
        budget.reserve(run, 1)
        budget.reserve(run, 5, 'linkedin')
        state.add_event(run, call())
        with self.assertRaises(ValueError):
            state.add_event(run, call())
        self.assertEqual(budget.summary(run)['pools']['linkedin']['available'], 5)

    def test_extra_pool_cannot_borrow_general_or_other_platform_reservations(self):
        run = new_run()
        budget.reserve(run, 60)
        budget.reserve(run, 1, 'yupao')
        budget.reserve(run, 5, 'linkedin')
        state.add_event(run, call('yupao'))
        with self.assertRaises(ValueError):
            state.add_event(run, call('yupao'))
        self.assertEqual(budget.summary(run)['pools']['general']['used'], 0)

    def test_new_special_pool_needs_its_own_reservation(self):
        run = new_run()
        budget.reserve(run, 60)
        with self.assertRaises(ValueError):
            budget.admit(run, call('yupao'))
        self.assertEqual(run['reserved_platform_queries']['yupao'], 0)

    def test_reservation_errors_leave_run_unchanged(self):
        for count, bucket in ((0, 'general'), (-1, 'yupao'), (True, 'general'),
                              (61, 'general'), (6, 'linkedin'), (1, 'zhaopin')):
            with self.subTest(count=count, bucket=bucket):
                run = new_run()
                before = copy.deepcopy(run)
                with self.assertRaises(ValueError):
                    budget.reserve(run, count, bucket)
                self.assertEqual(run, before)
        run = new_run()
        budget.reserve(run, 5, 'yupao')
        before = copy.deepcopy(run)
        with self.assertRaises(ValueError):
            budget.reserve(run, 1, 'yupao')
        self.assertEqual(run, before)

    def test_scoping_accepts_target_subdomains_paths_and_explicit_domains(self):
        cases = [('yupao', 'site:m.yupao.com/zhaogong/ Unity', None),
                 ('linkedin', 'SITE:cn.linkedin.com/jobs/view Unity', None),
                 ('yupao', 'Unity 工业', ['m.yupao.com', 'www.yupao.com']),
                 ('linkedin', 'Unity 医疗', ['linkedin.com']),
                 ('yupao', 'site:yupao.com Unity -site:zhaopin.com', None)]
        for bucket, query, domains in cases:
            with self.subTest(bucket=bucket, query=query):
                run = new_run()
                budget.reserve(run, 1, bucket)
                event = call(bucket, query=query)
                if domains is not None:
                    event['domains'] = domains
                before = copy.deepcopy((run, event))
                budget.admit(run, event)
                self.assertEqual((run, event), before)
                state.add_event(run, event)
                self.assertEqual(budget.summary(run)['pools'][bucket]['used'], 1)

    def test_special_pool_rejects_other_platform_and_unproven_scope(self):
        invalid = [call('yupao', query='site:zhaopin.com Unity'),
                   call('linkedin', query='site:yupao.com Unity'),
                   call('yupao', query='site:yupao.com.evil.org Unity'),
                   call('yupao', query='site:yupao.com OR site:zhaopin.com Unity'),
                   call('yupao', query='Unity', domains=['yupao.com', 'zhaopin.com']),
                   call('yupao', query='site:zhipin.com Unity', domains=['yupao.com']),
                   call('yupao', query='Unity', source='yupao.com'),
                   call('yupao', query='site.yupao.com Unity'),
                   call('yupao', query='-site:yupao.com Unity'),
                   call('yupao', query='https://example.org/?site:yupao.com'),
                   call('yupao', query='Unity', domains=[]),
                   call('yupao', query='Unity', domains='yupao.com'),
                   call('yupao', query='Unity', domains=['https://yupao.com']),
                   call('yupao', phase='enrichment'),
                   call('zhaopin')]
        for event in invalid:
            with self.subTest(event=event):
                run = new_run()
                budget.reserve(run, 5, 'yupao')
                budget.reserve(run, 5, 'linkedin')
                with self.assertRaises(ValueError):
                    state.add_event(run, event)
                self.assertEqual(run['searches'], [])

    def test_boolean_queries_require_explicit_domains_for_extra_pools(self):
        queries = ('site:linkedin.com Unity OR developer',
                   'site:linkedin.com (Unity OR VR)',
                   'site:linkedin.com Unity | developer',
                   '(site:linkedin.com Unity) OR (site:linkedin.com VR)')
        for query in queries:
            with self.subTest(query=query):
                run = new_run()
                budget.reserve(run, 1, 'linkedin')
                with self.assertRaises(ValueError):
                    budget.admit(run, call('linkedin', query=query))
                budget.admit(run, call('linkedin', query=query, domains=['linkedin.com']))
                self.assertEqual(run['searches'], [])

    def test_quoted_site_text_does_not_establish_source_scope(self):
        queries = ('\"site:linkedin.com\" Unity', '\"foo site:linkedin.com\" Unity',
                   "'foo site:linkedin.com' Unity", '\"foo site:linkedin.com Unity',
                   '\"foo \\\"bar site:linkedin.com\\\"\" Unity')
        for query in queries:
            with self.subTest(query=query):
                run = new_run()
                budget.reserve(run, 1, 'linkedin')
                with self.assertRaises(ValueError):
                    budget.admit(run, call('linkedin', query=query))
                budget.admit(run, call('linkedin', query=query, domains=['linkedin.com']))
        run = new_run()
        budget.reserve(run, 1, 'linkedin')
        budget.admit(run, call('linkedin', query='site:linkedin.com \"Unity OR VR\"'))

    def test_blocked_and_no_matches_calls_cost_queries_pages_do_not(self):
        run = new_run()
        budget.reserve(run, 2, 'yupao')
        for outcome in ('blocked', 'no_matches'):
            state.add_event(run, call('yupao', outcome=outcome))
        state.add_event(run, {'url': 'https://m.yupao.com/zhaogong/1.html', 'outcome': 'blocked'}, page=True)
        summary = budget.summary(run)
        self.assertEqual(summary['total']['used'], 2)
        self.assertEqual(summary['pools']['yupao']['available'], 0)
        self.assertEqual(len(run['accesses']), 1)
        with self.assertRaises(ValueError):
            state.add_event(run, call('yupao'))

    def test_restore_preserves_used_and_reserved_and_event_replay_is_free(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            run = new_run()
            budget.reserve(run, 1, 'linkedin')
            state.write(path, run)
            event = call('linkedin', event_id='actual-1')
            state.record(path, event)
            before = path.read_bytes()
            self.assertFalse(state.record(path, event)['recorded'])
            self.assertEqual(path.read_bytes(), before)
            restored = state.read(path)
            self.assertEqual(restored['reserved_platform_queries']['linkedin'], 1)
            result = state.status(path, limit=0)
            self.assertEqual(result['query_budget']['pools']['linkedin']['used'], 1)
            self.assertEqual(result['remaining_queries'], 69)
            self.assertEqual(result['recent_searches'], [])
            with self.assertRaises(ValueError):
                state.record(path, {**event, 'event_id': 'actual-2'})

    def test_each_actual_repeat_uses_one_legal_pool_and_event_id_cannot_switch_pool(self):
        run = new_run()
        budget.reserve(run, 1)
        budget.reserve(run, 1, 'yupao')
        event = call('general', query='site:yupao.com Unity', event_id='actual-1')
        state.add_event(run, event)
        self.assertFalse(state.add_event(run, {**event, 'budget_bucket': 'yupao'}))
        self.assertTrue(state.add_event(run, {**event, 'event_id': 'actual-2', 'budget_bucket': 'yupao'}))
        summary = budget.summary(run)
        self.assertEqual(summary['total']['used'], 2)
        self.assertEqual(summary['pools']['general']['used'], 1)
        self.assertEqual(summary['pools']['yupao']['used'], 1)

    def test_extra_batch_is_atomic_and_replay_does_not_duplicate_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            run = new_run()
            budget.reserve(run, 1, 'yupao')
            state.write(path, run)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                state.batch(path, {'batch_id': 'too-many', 'searches': [call('yupao'), call('yupao')]})
            self.assertEqual(path.read_bytes(), before)
            payload = {'batch_id': 'one', 'searches': [call('yupao', event_id='actual-1')]}
            state.batch(path, payload)
            before = path.read_bytes()
            self.assertFalse(state.batch(path, payload)['recorded'])
            self.assertEqual(path.read_bytes(), before)

    def test_existing_special_logs_are_validated_not_only_new_calls(self):
        for event in (call('yupao', query='site:linkedin.com Unity'), call('linkedin', phase='enrichment')):
            run = new_run()
            budget.reserve(run, 1, 'yupao')
            budget.reserve(run, 1, 'linkedin')
            run['searches'].append(event)
            with self.assertRaises(ValueError):
                budget.validate(run)
        run = new_run()
        budget.reserve(run, 1, 'yupao')
        run['searches'] = [call('yupao'), call('yupao')]
        with self.assertRaises(ValueError):
            budget.validate(run)

    def test_old_run_remains_single_pool_and_old_metadata_is_not_new_credit(self):
        run = run_record()
        run['reserved_queries'] = 1
        state.add_event(run, call('linkedin', query='site:zhaopin.com Unity'))
        self.assertEqual(budget.summary(run)['pools']['general']['used'], 1)
        self.assertEqual(budget.summary(run)['total']['limit'], 60)
        with self.assertRaises(ValueError):
            state.add_event(run, call('yupao'))
        with self.assertRaises(ValueError):
            budget.reserve(run, 1, 'yupao')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            state.write(path, run)
            self.assertNotIn('query_budget', state.status(path))

    def test_followup_inherits_date_policy_without_extra_credit(self):
        for mode in ('enrich', 'refresh'):
            with self.subTest(mode=mode):
                run = {'mode': mode, 'platform_policy': budget.default_policy(),
                       'budget': {'queries': 1}, 'searches': []}
                budget.validate(run)
                summary = budget.summary(run)
                self.assertEqual(summary['total']['limit'], 1)
                self.assertEqual(summary['pools']['yupao']['limit'], 0)
                with self.assertRaises(ValueError):
                    budget.reserve(run, 1, 'linkedin')
                with self.assertRaises(ValueError):
                    state.add_event(run, call('linkedin'))
                state.add_event(run, {'query': '公司 福利', 'source': 'web', 'outcome': 'success'})
                self.assertEqual(run['searches'][0]['phase'], 'enrichment' if mode == 'enrich' else 'discovery')
                with self.assertRaises(ValueError):
                    state.add_event(run, call())
        policy = budget.default_policy()
        del policy['extra_queries']
        run = {'mode': 'refresh', 'platform_policy': policy, 'budget': {'queries': 0}, 'searches': []}
        budget.validate(run)
        self.assertEqual(budget.summary(run)['total']['limit'], 0)

    def test_invalid_policy_and_followup_extra_reservations_are_rejected(self):
        for patch in ({'version': 2}, {'version': True}, {'linkedin_age_months': True},
                      {'linkedin_allow_unknown': 'yes'}, {'extra_queries': {'yupao': 6, 'linkedin': 5}},
                      {'extra_queries': {'yupao': 5, 'zhaopin': 5}}):
            with self.subTest(patch=patch):
                run = new_run()
                run['platform_policy'].update(patch)
                with self.assertRaises(ValueError):
                    budget.validate(run)
        run = {'mode': 'refresh', 'platform_policy': budget.default_policy(), 'budget': {'queries': 1},
               'searches': [], 'reserved_platform_queries': {'yupao': 1, 'linkedin': 0}}
        with self.assertRaises(ValueError):
            budget.validate(run)

    def test_inherited_policy_rejects_explicit_invalid_extra_configuration(self):
        run = {'mode': 'refresh', 'platform_policy': budget.default_policy(),
               'budget': {'queries': 0}, 'searches': []}
        run['platform_policy']['extra_queries'] = None
        with self.assertRaises(ValueError):
            budget.validate(run)


if __name__ == '__main__':
    unittest.main()
