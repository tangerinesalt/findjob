"""LinkedIn age exceptions preserve raw evidence and leave other rules to the caller.

The 2026-10-09 seven-sample counterfactual is 2 retained by exception,
3 pending for business/body evidence, and 2 closed. These tests do not certify
those samples as recent or open, and do not depend on local scratch files.
"""
import copy
import importlib.util
from datetime import date
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "linkedin_dates", ROOT / "skills" / "job-search" / "scripts" / "linkedin_dates.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

POLICY = {"version": 1, "extra_queries": {"yupao": 5, "linkedin": 5},
          "linkedin_age_months": 3, "linkedin_allow_unknown": True}
URL = "https://cn.linkedin.com/jobs/view/test-123"
TODAY = "2026-10-09"


def job(text=None, observed=TODAY, url=URL):
    value = {"job_url": url, "dates": [], "status": "unknown", "games": "no"}
    if text is not None:
        value["relative_dates"] = [{"text": text, "url": url,
                                    "note": "岗位正文时间", "observed_at": observed}]
    return value


def absolute(value, kind="published", url=URL, note="岗位正文发布日期"):
    return {"value": value, "kind": kind, "url": url, "note": note}


class LinkedInDates(unittest.TestCase):
    def evaluate(self, value, today=TODAY):
        return module.evaluate(value, today, POLICY)

    def test_exception_requires_explicit_versioned_policy(self):
        for policy in (None, {}, {"version": 1}, {**POLICY, "version": 99},
                       {**POLICY, "linkedin_allow_unknown": False},
                       {**POLICY, "linkedin_age_months": 0},
                       {**POLICY, "linkedin_age_months": True}):
            with self.subTest(policy=policy):
                self.assertIsNone(module.evaluate(job(), TODAY, policy))

    def test_domain_check_accepts_real_hosts_not_similar_names(self):
        for host in ("linkedin.com", "www.linkedin.com", "CN.LinkedIn.com"):
            with self.subTest(host=host):
                self.assertTrue(self.evaluate(job(url=f"https://{host}/jobs/view/123"))["exception"])
        for url in ("https://linkedin.com.evil.test/jobs/123", "https://notlinkedin.com/jobs/123",
                    "https://example.test/linkedin.com/jobs/123", "https://linkedin.com@evil.test/123",
                    "https://evil.test@linkedin.com/123", "ftp://linkedin.com/jobs/123"):
            with self.subTest(url=url):
                self.assertIsNone(self.evaluate(job(url=url)))

    def test_confirmed_source_record_applies_when_canonical_url_is_another_platform(self):
        value = job(url="https://employer.test/jobs/123")
        value["source_records"] = [{"id": "linkedin-123", "url": URL}]
        value["relative_dates"] = job("3天前")["relative_dates"]
        self.assertFalse(self.evaluate(value)["rejected"])
        value.pop("source_records")
        self.assertIsNone(self.evaluate(value))

    def test_unconfirmed_other_linkedin_job_cannot_supply_age(self):
        value = job("3个月前")
        value["relative_dates"][0]["url"] = "https://cn.linkedin.com/jobs/view/unrelated-456"
        result = self.evaluate(value)
        self.assertFalse(result["rejected"])
        self.assertIn("日期未核实", result["display"])

    def test_unknown_has_no_fabricated_date_or_evidence_and_leaves_input_intact(self):
        value = job()
        before = copy.deepcopy(value)
        result = self.evaluate(value)
        self.assertIsNone(result["date"])
        self.assertIsNone(result["evidence"])
        self.assertFalse(result["pending"])
        self.assertIn("按 LinkedIn 例外保留", result["display"])
        self.assertEqual(value, before)

    def test_absolute_boundary_is_strict_and_uses_calendar_months(self):
        for day, rejected in (("2026-07-08", True), ("2026-07-09", True),
                              ("2026-07-10", False), (TODAY, False)):
            with self.subTest(day=day):
                value = job()
                value["dates"] = [absolute(day)]
                result = self.evaluate(value)
                self.assertEqual(bool(result["rejected"]), rejected)
                self.assertEqual(result["date"]["value"], day)
        for today, boundary in (("2024-05-31", "2024-02-29"), ("2026-05-31", "2026-02-28")):
            value = job()
            value["dates"] = [absolute(boundary)]
            self.assertTrue(self.evaluate(value, today)["rejected"])

    def test_absolute_old_date_wins_over_unknown_and_younger_relative(self):
        value = job("3天前")
        value["dates"] = [absolute("2026-06-01", url="https://employer.test/jobs/123")]
        result = self.evaluate(value)
        self.assertTrue(result["rejected"])
        self.assertEqual(result["evidence"]["url"], "https://employer.test/jobs/123")

    def test_true_refresh_after_old_publication_is_not_a_conflict(self):
        value = job()
        value["dates"] = [absolute("2026-01-01"), absolute("2026-10-01", "refreshed")]
        result = self.evaluate(value)
        self.assertFalse(result["pending"])
        self.assertFalse(result["rejected"])
        self.assertEqual(result["date"]["kind"], "refreshed")

    def test_absolute_equivalent_source_observations_remain_stable(self):
        value = job()
        first = absolute("2026-10-01")
        second = {**first, "original_text": "2026-10-01"}
        value["dates"] = [first, second]
        result = self.evaluate(value)
        value["dates"].reverse()
        self.assertEqual(self.evaluate(value), result)

    def test_day_inputs_and_tracking_parameters_do_not_change_job_identity(self):
        value = job("3 days ago")
        value["relative_dates"][0]["url"] += "?utm_source=test#body"
        result = self.evaluate(value, date(2026, 10, 9))
        self.assertFalse(result["rejected"])
        self.assertIn("3 days ago", result["display"])

    def test_absolute_conflicting_or_future_evidence_stays_pending(self):
        for dates in ([absolute("2026-10-10")],
                      [absolute("2026-06-01"), absolute("2026-10-01")],
                      [absolute("2026-10-01"), absolute("2026-09-01", "refreshed")],
                      [absolute("2026-09-01", "refreshed"), absolute("2026-10-01", "job_time")]):
            with self.subTest(dates=dates):
                value = job()
                value["dates"] = dates
                result = self.evaluate(value)
                self.assertTrue(result["pending"])
                self.assertIsNone(result["date"])

    def test_crawled_and_recommendation_dates_are_not_job_dates(self):
        for record in (absolute("2026-01-01", "crawled"),
                       absolute("2026-01-01", note="相关推荐日期")):
            value = job()
            value["dates"] = [record]
            result = self.evaluate(value)
            self.assertFalse(result["rejected"])
            self.assertIsNone(result["date"])
        for note, kind in (("抓取时间", None), ("相关推荐正文时间", None),
                           ("Search snippet time", None), ("岗位正文时间", "crawled")):
            value = job("3个月前")
            value["relative_dates"][0].update(note=note, kind=kind)
            self.assertFalse(self.evaluate(value)["rejected"])

    def test_chinese_and_english_relative_month_year_ages(self):
        for text in ("3个月前", "4 months ago", "1year ago", "1 年前"):
            with self.subTest(text=text):
                result = self.evaluate(job(text))
                self.assertTrue(result["rejected"])
                self.assertIsNone(result["date"])
                self.assertEqual(result["evidence"]["text"], text)
        for text in ("2个月前", "3天前", "3 days ago", "4周前", "1 month ago"):
            with self.subTest(text=text):
                result = self.evaluate(job(text))
                self.assertFalse(result["rejected"])
                self.assertFalse(result["pending"])
                self.assertIsNone(result["date"])
                self.assertIn(text, result["display"])

    def test_days_near_calendar_boundary_remain_uncertain(self):
        # Jul 9 is 92 days before Oct 9; the boundary is not a fixed 90-day window.
        for text, rejected, unknown in (("90天前", False, False),
                                        ("91天前", False, True),
                                        ("92天前", True, False),
                                        ("12 weeks ago", False, False),
                                        ("13 weeks ago", False, True),
                                        ("14 weeks ago", True, False)):
            with self.subTest(text=text):
                result = self.evaluate(job(text))
                self.assertEqual(bool(result["rejected"]), rejected)
                self.assertEqual("日期未核实" in result["display"], unknown)

    def test_chinese_adjacent_words_do_not_hide_old_relative_ages(self):
        for text in ("3个月前发布", "发表于3个月前的岗位", "1年前发布",
                     "该岗位发表于4 months ago的记录"):
            with self.subTest(text=text):
                result = self.evaluate(job(text))
                self.assertTrue(result["rejected"])
                self.assertEqual(result["evidence"]["text"], text)
                self.assertIsNone(result["date"])
        result = self.evaluate(job("3天前发布"))
        self.assertFalse(result["rejected"])
        self.assertNotIn("日期未核实", result["display"])

    def test_ascii_word_boundaries_and_ranges_do_not_supply_a_false_age(self):
        for text in ("3 months agox", "3 months ago_", "3 months ago2", "x3 months ago",
                     "2–3个月前", "2 - 3 months ago", "2至3个月前", "2 to 3 months ago",
                     "-3 months ago", "2.5个月前"):
            with self.subTest(text=text):
                result = self.evaluate(job(text))
                self.assertFalse(result["rejected"])
                self.assertIn("日期未核实", result["display"])

    def test_unrepresentable_age_does_not_crash_the_report(self):
        result = self.evaluate(job("9" * 5000 + " months ago"))
        self.assertIn("日期未核实", result["display"])

    def test_explicit_minimum_old_ages_are_not_treated_as_unknown(self):
        for text in ("over 3 months ago", "more than 3 months ago", "at least 3 months ago",
                     "3+ months ago", "3 + months ago", "至少3个月前", "超过3个月前发布",
                     "3+个月前", "不少于3个月前", "≥3个月前", "3 months ago or more",
                     "1+ year ago", "120+ days ago"):
            with self.subTest(text=text):
                result = self.evaluate(job(text))
                self.assertTrue(result["rejected"])
                self.assertFalse(result["pending"])
                self.assertIsNone(result["date"])
                self.assertEqual(result["evidence"]["text"], text)

    def test_minimum_younger_age_is_uncertain_and_still_ages_on_refresh(self):
        for text in ("30+ days ago", "at least 30 days ago", "至少1个月前", "2+ months ago"):
            with self.subTest(text=text):
                result = self.evaluate(job(text))
                self.assertFalse(result["rejected"])
                self.assertIn("日期未核实", result["display"])
                self.assertIsNone(result["date"])
        self.assertTrue(self.evaluate(job("30+ days ago", "2026-08-01"))["rejected"])

    def test_upper_bound_age_does_not_establish_minimum_old_age(self):
        for text in ("less than 3 months ago", "under 3 months ago", "不足3个月前",
                     "不超过3个月前", "没有超过3个月前", "no more than 3 months ago"):
            with self.subTest(text=text):
                result = self.evaluate(job(text))
                self.assertFalse(result["rejected"])
                self.assertIn("日期未核实", result["display"])

    def test_invalid_url_port_is_rejected_by_relative_validation(self):
        value = job("3个月前")
        value["relative_dates"][0]["url"] = "https://linkedin.com:invalid/jobs/view/123"
        with self.assertRaises(ValueError):
            module.validate_relative(value)

    def test_refresh_ages_stale_observation_instead_of_reusing_three_days(self):
        value = job("3天前", "2026-06-01")
        result = self.evaluate(value)
        self.assertTrue(result["rejected"])
        self.assertEqual(result["evidence"]["observed_at"], "2026-06-01")
        self.assertIn("实际流逝", "；".join(result["notes"]))
        self.assertIsNone(result["date"])

    def test_new_observation_of_same_url_supersedes_stale_observation_stably(self):
        value = job("3天前", "2026-06-01")
        value["relative_dates"] += job("3天前")["relative_dates"]
        original = copy.deepcopy(value)
        result = self.evaluate(value)
        self.assertFalse(result["rejected"])
        self.assertEqual(result["evidence"]["observed_at"], TODAY)
        value["relative_dates"].reverse()
        self.assertEqual(self.evaluate(value), result)
        self.assertEqual(list(reversed(value["relative_dates"])), original["relative_dates"])

    def test_different_sources_or_same_observation_day_age_conflicts_stay_pending(self):
        for other_url in (URL, "https://www.linkedin.com/jobs/view/confirmed-456"):
            with self.subTest(other_url=other_url):
                value = job("3天前")
                value["source_records"] = [{"id": "confirmed", "url": other_url}]
                other = job("3个月前", url=other_url)["relative_dates"][0]
                value["relative_dates"].append(other)
                result = self.evaluate(value)
                self.assertTrue(result["pending"])
                self.assertFalse(result["rejected"])
                value["relative_dates"].reverse()
                self.assertEqual(self.evaluate(value), result)

    def test_future_observation_stays_pending(self):
        result = self.evaluate(job("3天前", "2026-10-10"))
        self.assertTrue(result["pending"])
        self.assertIsNone(result["date"])

    def test_validation_is_platform_independent(self):
        value = job("unknown", url="https://example.test/jobs/123")
        module.validate_relative(value)
        self.assertIsNone(self.evaluate(value))
        for relative in ({}, "3天前", [{"text": "3天前"}],
                         [{"text": "3天前", "url": URL, "note": "正文时间", "observed_at": "2026-02-30"}]):
            with self.subTest(relative=relative):
                value["relative_dates"] = relative
                with self.assertRaises(ValueError):
                    module.validate_relative(value)

    def test_seven_sample_exception_preserves_non_date_blockers(self):
        # Full evaluation must give 2 exception-kept / 3 other-evidence pending / 2 closed.
        # The date helper intentionally does not certify games, JD readability or openness.
        samples = (
            ("轩宇", "3周前", "unknown", "no"),
            ("易格通智", "1周前", "closed", "unknown"),
            ("Dreamscape", None, "unknown", "unknown"),
            ("群源", "1个月前", "unknown", "no"),
            ("视比特", "1周前", "unknown", "unknown"),
            ("武汉湾流", "4周前", "unknown", "unknown"),
            ("南京芭林", "3个月前", "closed", "unknown"),
        )
        for name, text, status, games in samples:
            with self.subTest(name=name):
                value = job(text)
                value.update(status=status, games=games)
                before = copy.deepcopy(value)
                result = self.evaluate(value)
                self.assertEqual(value, before)
                self.assertIsNone(result["date"])
                self.assertEqual(bool(result["rejected"]), name == "南京芭林")
                self.assertFalse(result["pending"])


if __name__ == "__main__":
    unittest.main()
