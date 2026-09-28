"""Profile CLI and Markdown handoff regression tests; all job fixtures are synthetic."""
import contextlib
import copy
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest

from test_job_report import job, run_record, module as report, ROOT

spec = importlib.util.spec_from_file_location('job_profile', ROOT / 'skills/job-profile/scripts/job_profile.py')
profile_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile_cli)
fmt = report.profile_format


class Profiles(unittest.TestCase):
    def invoke(self, module, args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return module.main(args)

    def test_chinese_and_markdown_roundtrip(self):
        profile = fmt.defaults(['Unity开发', 'VR开发'])
        profile.update(name='上海Unity画像', locations=['上海', '苏州'], background='本科 C# & C++\n3年经验 <研发>')
        profile['preferences'] = ['A|B；C;D', '*文本* [链接] `代码` \\test', '&amp; <br> #标签']
        self.assertEqual(fmt.parse(fmt.render(profile)), profile)

    def test_bom_and_reordered_rows(self):
        profile = fmt.defaults(['开发'])
        lines = fmt.render(profile).splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('| 格式版本'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '画像.MD'
            path.write_text('\n'.join(lines[:index] + list(reversed(lines[index:]))), encoding='utf-8-sig')
            self.assertEqual(fmt.load(path), profile)

    def test_collision_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = fmt.defaults(['Unity开发'])
            first = fmt.save_new(profile, directory)
            before = first.read_bytes()
            second = fmt.save_new(profile, directory)
            third = fmt.save_new(profile, directory)
            self.assertEqual([first.name, second.name, third.name], ['Unity开发.md', 'Unity开发_2.md', 'Unity开发_3.md'])
            self.assertEqual(first.read_bytes(), before)

    def test_filename_stays_in_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('../../画像:上海?', 'CON', '...', 'Unity' * 40):
                profile = fmt.defaults(['开发'])
                profile['name'] = name
                path = fmt.save_new(profile, directory)
                self.assertEqual(path.parent, Path(directory).resolve())
                self.assertLessEqual(len(path.stem), 81)
                self.assertNotEqual(path.stem.upper(), 'CON')

    def test_invalid_tables_report_errors(self):
        text = fmt.render(fmt.defaults(['Unity']))
        for changed in (text.replace('| 岗位名称 | Unity |\n', ''), text + '| 岗位名称 | Unity |\n', text.replace('岗位名称', '岗位名错字'), text.replace('| 是 |', '| yes |', 1), text.replace('| 0 |', '| 6K |', 1)):
            with self.subTest(text=changed[-100:]), self.assertRaises(ValueError):
                profile = fmt.parse(changed)
                report.validate_profile(profile)

    def test_independent_salary_thresholds(self):
        for lower, upper in ((6000, 0), (0, 9000), (9000, 6000)):
            profile = fmt.defaults(['Unity'])
            profile['salary'].update(min_lower_monthly=lower, min_upper_monthly=upper)
            report.validate_profile(profile)

    def test_invalid_numbers_and_no_output_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            for value in (-1, float('nan'), float('inf')):
                profile = fmt.defaults(['Unity'])
                profile['salary']['min_lower_monthly'] = value
                report.save(path, profile)
                self.assertEqual(self.invoke(profile_cli, ['create', '--input', str(path), '--workspace', directory]), 1)
            self.assertEqual(list(Path(directory).glob('*.md')), [])

    def test_default_cwd_and_draft_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                args = ['draft', '--role', 'Unity开发', '--output', 'draft.json']
                self.assertEqual(self.invoke(profile_cli, args), 0)
                self.assertEqual(self.invoke(profile_cli, args), 1)
                self.assertEqual(self.invoke(profile_cli, ['create', '--input', 'draft.json']), 0)
                self.assertTrue(Path('Unity开发.md').exists())
            finally:
                os.chdir(previous)

    def test_manual_edit_init_and_filter_handoff(self):
        with tempfile.TemporaryDirectory(prefix='画像测试-') as directory:
            profile = fmt.defaults(['Unity开发'])
            path = fmt.save_new(profile, directory)
            text = path.read_text(encoding='utf-8').replace('| 月薪下限至少（元） | 0 |', '| 月薪下限至少（元） | 7000 |').replace('| 工作地点 |  |', '| 工作地点 | 上海；苏州 |').replace('| 岗位排除关键词 |  |', '| 岗位排除关键词 | 博彩 |')
            path.write_text(text, encoding='utf-8')
            self.assertEqual(self.invoke(profile_cli, ['check', '--input', str(path)]), 0)
            run_path = Path(directory) / 'run.json'
            self.assertEqual(self.invoke(report, ['init', '--profile', str(path), '--as-of', '2026-09-21', '--run', str(run_path)]), 0)
            run = report.load(run_path)
            self.assertEqual(run['profile']['locations'], ['上海', '苏州'])
            self.assertEqual(run['profile']['excluded_keywords'], ['博彩'])
            run['jobs'] = [job()]
            self.assertEqual(len(report.check(run)['excluded']), 1)
            run['jobs'][0]['salary']['min'] = 7000
            self.assertEqual(len(report.check(run)['kept']), 1)
            # Semantic exclusions are assessed by the host, then honored by the checker.
            run['jobs'][0]['profile_match'] = 'no'
            self.assertEqual(len(report.check(run)['excluded']), 1)
            report.save(run_path, run)
            output = Path(directory) / '报告.md'
            self.assertEqual(self.invoke(report, ['render', '--run', str(run_path), '--output', str(output)]), 0)
            self.assertIn('博彩', output.read_text(encoding='utf-8'))

    def test_headhunter_and_unclear_switches(self):
        for recruiter, headhunter, unclear, expected in (
            ('headhunter', True, False, 'excluded'),
            ('headhunter', False, True, 'kept'),
            ('anonymous', False, True, 'excluded'),
            ('anonymous', False, False, 'kept'),
            ('anonymous', True, False, 'pending'),
            ('unknown', True, False, 'pending'),
            ('unknown', False, False, 'kept')):
            with self.subTest(recruiter=recruiter, headhunter=headhunter, unclear=unclear):
                run = run_record(job())
                run['profile'].update(exclude_headhunters=headhunter, exclude_unclear_employers=unclear)
                run['jobs'][0]['recruiter'] = recruiter
                result = report.check(run)
                self.assertEqual(result['errors'], [])
                self.assertEqual(len(result[expected]), 1)

    def test_date_and_mode_requires_both_explicit_dates(self):
        run = run_record(job())
        run['profile']['freshness']['mode'] = 'all'
        self.assertEqual(len(report.check(run)['pending']), 1)
        published = copy.deepcopy(run['jobs'][0]['dates'][0])
        published.update(kind='published', value='2026-07-21')
        run['jobs'][0]['dates'].append(published)
        self.assertEqual(len(report.check(run)['kept']), 1)
        published['value'] = '2026-07-20'
        self.assertEqual(len(report.check(run)['excluded']), 1)
        published.update(kind='job_time', value='2026-09-20')
        self.assertEqual(len(report.check(run)['pending']), 1)

    def test_legacy_export_preserves_filter_results(self):
        run = run_record(job())
        before = report.check(run)
        run['profile'] = fmt.parse(fmt.render(run['profile']))
        report.validate_profile(run['profile'])
        self.assertEqual(report.check(run), before)


if __name__ == '__main__':
    unittest.main()
