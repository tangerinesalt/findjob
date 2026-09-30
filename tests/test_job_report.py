"""Behavioral regression tests. Synthetic records never enter user reports."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "job-search"
spec = importlib.util.spec_from_file_location("job_report", SKILL / "scripts" / "job_report.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def job():
    address = "https://example.org/jobs/1"
    return {
        "id": "one", "company": "Test Company", "title": "Unity developer",
        "location": "Shanghai", "education": "Bachelor", "experience": "3 years",
        "job_url": address, "status": "unknown", "relevance": "core", "games": "no",
        "recruiter": "employer", "profile_match": "yes",
        "evidence": {k: {"url": address, "note": "Synthetic test evidence"} for k in ("relevance", "games", "recruiter", "profile_match", "salary")},
        "salary": {"text": "6–9K/month", "currency": "CNY", "period": "month", "min": 6000, "max": 9000, "months": None},
        "dates": [{"value": "2026-09-20", "kind": "refreshed", "url": address, "note": "Synthetic job date"}],
        "details": {}, "discussions": [], "notes": [],
    }


def run_record(*jobs):
    return dict(schema_version=1, as_of="2026-09-21", profile=module.load(SKILL / "references" / "unity-non-game.json"), reserved_queries=0, searches=[], jobs=list(jobs), notes=[])


class Rules(unittest.TestCase):
    def state(self, j, profile=None):
        run = run_record(j)
        if profile:
            run["profile"] = module.merge(run["profile"], profile)
        result = module.check(run)
        self.assertEqual(result["errors"], [])
        return next(name for name in ("kept", "excluded", "pending") if result[name])

    def test_exact_salary_boundaries(self):
        self.assertEqual(self.state(job()), "kept")
        for key, amount in (("min", 5999), ("max", 8999)):
            j = job()
            j["salary"][key] = amount
            self.assertEqual(self.state(j), "excluded")

    def test_publication_and_refresh_use_different_windows(self):
        for kind, day, expected in (("published", "2026-07-21", "kept"), ("published", "2026-07-20", "excluded"), ("refreshed", "2026-08-21", "kept"), ("refreshed", "2026-08-20", "excluded"), ("job_time", "2026-08-20", "excluded"), ("crawled", "2026-09-21", "pending")):
            with self.subTest(kind=kind, day=day):
                j = job()
                j["dates"][0].update(kind=kind, value=day)
                self.assertEqual(self.state(j), expected)

    def test_calendar_month_end_and_leap_year(self):
        self.assertEqual(module.back_months(date(2024, 3, 31), 1), date(2024, 2, 29))
        self.assertEqual(module.back_months(date(2026, 3, 31), 1), date(2026, 2, 28))

    def test_future_and_unproven_dates_stay_pending(self):
        j = job()
        j["dates"][0]["value"] = "2026-09-22"
        self.assertEqual(self.state(j), "pending")
        j["dates"][0].update(value="2026-09-20", note="")
        self.assertEqual(self.state(j), "pending")

    def test_expired_and_closed(self):
        j = job()
        j["deadline"] = "2026-09-20"
        self.assertEqual(self.state(j), "excluded")
        j["deadline"] = "2026-09-21"
        self.assertEqual(self.state(j), "kept")
        j["status"] = "closed"
        self.assertEqual(self.state(j), "excluded")

    def test_game_headhunter_and_adjacent(self):
        for key, value in (("games", "yes"), ("recruiter", "headhunter"), ("recruiter", "anonymous"), ("relevance", "adjacent"), ("profile_match", "no")):
            j = job()
            j[key] = value
            self.assertEqual(self.state(j), "excluded")
        j = job()
        j["relevance"] = "adjacent"
        self.assertEqual(self.state(j, {"include_adjacent": True}), "kept")

    def test_missing_business_evidence_not_accepted(self):
        j = job()
        del j["evidence"]["games"]
        self.assertEqual(self.state(j), "pending")

    def test_unknown_and_partial_salary(self):
        j = job()
        j["salary"].update(text="Negotiable", period="unknown", min=None, max=None)
        self.assertEqual(self.state(j), "kept")
        self.assertEqual(self.state(j, {"salary": {"allow_unknown": False}}), "excluded")
        j = job()
        j["salary"].update(min=5000, max=None)
        self.assertEqual(self.state(j), "excluded")

    def test_foreign_daily_annual_pay(self):
        for update in ({"currency": "USD"}, {"period": "day"}, {"period": "hour"}):
            j = job()
            j["salary"].update(update)
            self.assertEqual(self.state(j), "pending")
        j = job()
        j["salary"].update(period="year", min=72000, max=108000)
        self.assertEqual(self.state(j), "kept")
        j["salary"]["months"] = 13
        self.assertEqual(self.state(j), "excluded")

    def test_dedup_and_distinct_seniority(self):
        first = job()
        duplicate = copy.deepcopy(first)
        duplicate.update(id="two", job_url=first["job_url"] + "?utm_source=feed")
        senior = copy.deepcopy(first)
        senior.update(id="three", title="Senior Unity developer", job_url="https://example.org/jobs/3")
        result = module.check(run_record(first, duplicate, senior))
        self.assertEqual(len(result["kept"]), 2)
        self.assertEqual(len(result["duplicates"]), 1)

    def test_invalid_records_prevent_render(self):
        for change in (lambda j: j["salary"].update(min=10000, max=6000), lambda j: j["details"].update(benefits={"text": "Free meals", "sources": []})):
            j = job()
            change(j)
            self.assertTrue(module.check(run_record(j))["errors"])

    def test_budget_resume_and_report_cli(self):
        with tempfile.TemporaryDirectory(prefix="findjob-test-") as directory, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            path = Path(directory) / "run.json"
            output = Path(directory) / "report.md"
            self.assertEqual(module.main(["init", "--profile", str(SKILL / "references" / "unity-non-game.json"), "--as-of", "2026-09-21", "--run", str(path)]), 0)
            self.assertEqual(module.main(["budget", "--run", str(path), "--count", "60"]), 0)
            before = path.read_bytes()
            self.assertEqual(module.main(["budget", "--run", str(path), "--count", "1"]), 1)
            self.assertEqual(path.read_bytes(), before)
            run = module.load(path)
            run["jobs"] = [job()]
            run["searches"] = [dict(query="Unity non-game", source="test-only", phase="discovery", outcome="success", note="Synthetic")]
            module.save(path, run)
            self.assertEqual(module.main(["render", "--run", str(path), "--output", str(output)]), 0)
            content = output.read_text(encoding="utf-8")
            self.assertIn("Test Company", content)
            self.assertIn("https://example.org/jobs/1", content)
            self.assertEqual(module.main(["render", "--run", str(path), "--output", str(output)]), 1)
            self.assertEqual(module.load(path)["reserved_queries"], 60)
            self.assertEqual(module.main(["render", "--run", str(path), "--output", str(path), "--replace"]), 1)

    def test_blocked_source_is_not_market_absence(self):
        run = run_record()
        run["reserved_queries"] = 1
        run["searches"] = [dict(query="query", source="blocked-source", phase="discovery", outcome="blocked", note="captcha")]
        text = module.render(run, module.check(run))
        self.assertIn("受阻查询 1", text)
        self.assertIn("不表示市场没有岗位", text)

    def test_overrides_preserve_profile(self):
        base = run_record()["profile"]
        saved = copy.deepcopy(base)
        merged = module.merge(base, {"locations": ["Beijing"], "salary": {"min_lower_monthly": 7000}})
        self.assertEqual(base, saved)
        self.assertEqual(merged["salary"]["min_upper_monthly"], 9000)
        self.assertEqual(merged["locations"], ["Beijing"])


if __name__ == "__main__":
    unittest.main()
