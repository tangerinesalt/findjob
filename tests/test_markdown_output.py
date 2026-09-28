"""Render-level checks require markdown-it-py only in the test environment."""
import unittest
from markdown_it import MarkdownIt
from test_job_report import module, job, run_record


class MarkdownOutput(unittest.TestCase):
    def test_report_is_a_real_eight_column_table(self):
        run = run_record(job())
        tokens = MarkdownIt().enable('table').parse(module.render(run, module.check(run)))
        self.assertEqual(sum(t.type == 'table_open' for t in tokens), 1)
        self.assertEqual(sum(t.type == 'th_open' for t in tokens), 8)
        self.assertEqual(sum(t.type == 'td_open' for t in tokens), 8)
