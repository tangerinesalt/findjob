"""Offline same-evidence comparison. Token counts are text estimates, not billed usage."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_job_report import job, run_record, module as current
from test_report_target import module as target


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    import tiktoken
    from markdown_it import MarkdownIt
    encoding = tiktoken.get_encoding('o200k_base')
    tokens = lambda value: len(encoding.encode(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)))
    root = ROOT / '.scratch/fingjob/optimization-validation/benchmark'
    baseline = root / 'baseline'
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', 'baseline-20260928'], cwd=ROOT).decode().splitlines()
    for name in paths:
        if not name.startswith(('skills/', '.codex-plugin/', 'tests/')):
            continue
        path = baseline / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(['git', 'show', 'baseline-20260928:' + name], cwd=ROOT))
    old = load_module('baseline_report', baseline / 'skills/job-search/scripts/job_report.py')
    records = []
    for index in range(1, 11):
        a = job()
        a.update(id=f'{index:02d}-a', company=f'合成公司{index}', job_url=f'https://example.org/jobs/{index}')
        a['details']['benefits'] = {'text': '五险一金', 'sources': [a['job_url']]}
        b = copy.deepcopy(a)
        b.update(id=f'{index:02d}-b', job_url=f'https://other.example.org/jobs/{index}')
        b['details'] = {'work_time': {'text': '09:00–18:00；双休', 'sources': [b['job_url']]}}
        records.extend([a, b])
    run = run_record(*records)
    run['reserved_queries'] = 2
    run['searches'] = [dict(query=q, source='synthetic fixed corpus', outcome='success', phase='discovery') for q in ('Unity 仿真', 'Unity 数字孪生')]
    before, after = old.check(run), current.check(run)
    old_output, new_output = old.render(run, before), current.render(run, after)
    reversed_run = copy.deepcopy(run)
    reversed_run['jobs'].reverse()
    old_sources = {j['id']: j for j in run['jobs']}
    known_before = sum(len(old_sources[j['id']]['details']) for j in before['kept'])
    known_after = sum(len(j['details']) for j in after['records'] if j['id'] in {k['id'] for k in after['kept']})
    report_path = root / '合成测试岗位报告.md'
    report_path.write_text(new_output, encoding='utf-8')
    task = target.prepare(root, 'enrich', '2026-09-28', report=str(report_path))
    summary = target.inspect_report(task['task'], '01', ['benefits', 'work_time'])
    patch = {'jobs': [{'number': '01', 'details': {'benefits': {'text': '五险一金、餐补', 'sources': ['https://example.org/jobs/1']}}}]}
    patched, _ = current.report_format.apply(new_output, patch)
    state = load_module('new_state', ROOT / 'skills/job-search/scripts/run_state.py')
    ledger = root / 'run.json'
    ledger.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding='utf-8')
    result = {
        'corpus': '10 synthetic jobs, 2 complementary observations each; identical two query events, no network calls',
        'token_method': 'o200k_base text token counts, excludes reasoning/tool envelopes and is not actual end-to-end billing',
        'same_evidence': {'before_jobs': len(before['kept']), 'after_jobs': len(after['kept']),
                          'before_retained_detail_fields': known_before, 'after_retained_detail_fields': known_after,
                          'before_order_invariant': old_output == old.render(reversed_run, old.check(reversed_run)),
                          'after_order_invariant': new_output == current.render(reversed_run, current.check(reversed_run)),
                          'before_tables': MarkdownIt().enable('table').render(old_output).count('<table>'),
                          'after_tables': MarkdownIt().enable('table').render(new_output).count('<table>')},
        'context_tokens': {'whole_run': tokens(ledger.read_text(encoding='utf-8')), 'resume_status': tokens(state.status(ledger)),
                           'whole_report': tokens(new_output), 'single_job_two_fields': tokens(summary),
                           'rewrite_report': tokens(patched), 'write_patch': tokens(patch),
                           'search_entry_before': tokens((baseline / 'skills/job-search/SKILL.md').read_text(encoding='utf-8-sig')),
                           'search_entry_after': tokens((ROOT / 'skills/job-search/SKILL.md').read_text(encoding='utf-8-sig'))},
        'limitations': ['Synthetic field retention is not a live search recall estimate.',
                        'A fresh run still reads profile/schema/evidence and retrieval guidance; not all reference text shrank.',
                        'Targeted reads are only appropriate when conditions and scope are already known.'],
    }
    (root / 'metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
