"""Small save/status helper for search and follow-up ledgers; no network calls."""
import argparse
import copy
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


_store_spec = importlib.util.spec_from_file_location('findjob_file_store', Path(__file__).resolve().parents[3] / 'scripts/file_store.py')
file_store = importlib.util.module_from_spec(_store_spec)
_store_spec.loader.exec_module(file_store)
read, write = file_store.load, file_store.save

_budget_spec = importlib.util.spec_from_file_location('findjob_search_budget', Path(__file__).with_name('search_budget.py'))
search_budget = importlib.util.module_from_spec(_budget_spec)
_budget_spec.loader.exec_module(search_budget)
_leads_spec = importlib.util.spec_from_file_location('findjob_lead_tracking', Path(__file__).with_name('lead_tracking.py'))
lead_tracking = importlib.util.module_from_spec(_leads_spec)
_leads_spec.loader.exec_module(lead_tracking)


def report_module():
    spec = importlib.util.spec_from_file_location('findjob_job_report', Path(__file__).with_name('job_report.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_active(data):
    if data.get('status') == 'complete':
        raise ValueError('已完成任务不能追加调用；新一轮需新任务')


def add_event(data, event, page=False):
    if not isinstance(event, dict):
        raise ValueError('调用记录必须为对象')
    events = data.setdefault('accesses' if page else 'searches', [])
    event = dict(event)
    if not page:
        event.setdefault('phase', 'enrichment' if data.get('mode') == 'enrich' else 'discovery')
    event_id = event.get('event_id')
    if event_id is not None:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError('event_id 须为非空字符串')
        for name in ('searches', 'accesses'):
            for previous in data.get(name, []):
                if previous.get('event_id') != event_id:
                    continue
                normalized = dict(previous)
                if name == 'searches':
                    normalized.setdefault('phase', 'enrichment' if data.get('mode') == 'enrich' else 'discovery')
                comparable = dict(event)
                for value in (normalized, comparable):
                    value.setdefault('note', '')
                    if name == 'searches':
                        value.setdefault('budget_bucket', 'general')
                if name != ('accesses' if page else 'searches') or normalized != comparable:
                    raise ValueError('event_id 已用于不同调用内容：' + event_id)
                return False
    if event.get('outcome') not in ('success', 'no_matches', 'blocked'):
        raise ValueError('outcome 无效')
    required = ('url',) if page else ('query', 'source')
    if any(not isinstance(event.get(k), str) or not event[k].strip() for k in required):
        raise ValueError('缺少调用身份字段')
    if not isinstance(event.get('note', ''), str):
        raise ValueError('note 须为文本')
    for key in ('new_jobs', 'new_fields'):
        if key in event and (type(event[key]) is not int or event[key] < 0):
            raise ValueError('增量必须是非负整数')
    if not page:
        event.setdefault('phase', 'enrichment' if data.get('mode') == 'enrich' else 'discovery')
        search_budget.admit(data, event)
    elif 'platform_policy' in data:
        search_budget.validate(data)
    events.append(event)
    return True


def counts(data):
    return {'queries': len(data.get('searches', [])), 'page_accesses': len(data.get('accesses', [])),
            'jobs_recorded': len(data.get('jobs', []))}

def record(path, event, page=False):
    data = read(path)
    require_active(data)
    if not add_event(data, event, page):
        return {'recorded': False, 'reason': '该 event_id 已记录'}
    if 'coverage' in data:
        data['coverage']['stop_reason'] = ''
    write(path, data)
    return {'recorded': True, **counts(data)}


def overlay(base, changes):
    """Explicit fields replace values; omitted fields stay, nested objects merge."""
    result = copy.deepcopy(base)
    for key, value in changes.items():
        result[key] = overlay(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else copy.deepcopy(value)
    return result


def batch(path, payload):
    """Commit one small batch atomically; an invalid batch leaves the ledger intact."""
    data = read(path)
    require_active(data)
    if not isinstance(payload, dict) or set(payload) - {'batch_id', 'jobs', 'searches', 'accesses', 'notes', 'leads', 'coverage'}:
        raise ValueError('批次只接受 batch_id/jobs/searches/accesses/notes/leads/coverage')
    for key in ('jobs', 'searches', 'accesses', 'notes'):
        if not isinstance(payload.get(key, []), list):
            raise ValueError(f'{key} 须为数组')
    if any(not isinstance(note, str) or not note.strip() for note in payload.get('notes', [])):
        raise ValueError('notes 须为非空文本数组')
    batch_id = payload.get('batch_id')
    if batch_id is not None and (not isinstance(batch_id, str) or not batch_id.strip()):
        raise ValueError('batch_id 须为非空文本')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    if batch_id and batch_id in data.get('batches', {}):
        if data['batches'][batch_id] != digest:
            raise ValueError('batch_id 已用于不同内容；请使用新批次ID')
        return {'recorded': False, 'reason': '该 batch_id 已记录', **counts(data)}
    incoming = payload.get('jobs', [])
    if incoming and data.get('mode', 'search') != 'search':
        raise ValueError('补充/复核岗位请更新 working.md，批次仅记录调用及说明')
    if incoming:
        module = report_module()
        positions = {item['id']: index for index, item in enumerate(data.setdefault('jobs', []))}
        seen = set()
        for item in incoming:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip():
                raise ValueError('批次岗位须为含非空 id 的对象')
            if item['id'] in seen:
                raise ValueError('同一批次岗位 id 重复')
            seen.add(item['id'])
            if item['id'] in positions:
                index = positions[item['id']]
                data['jobs'][index] = module.normalize_job(overlay(data['jobs'][index], item))
            else:
                positions[item['id']] = len(data['jobs'])
                data['jobs'].append(module.normalize_job(item))
    searches_added = sum(add_event(data, event) for event in payload.get('searches', []))
    accesses_added = sum(add_event(data, event, page=True) for event in payload.get('accesses', []))
    notes = data.setdefault('notes', [])
    notes.extend(note for note in payload.get('notes', []) if note not in notes)
    if 'leads' in payload or 'coverage' in payload:
        lead_tracking.update(data, payload.get('leads', []), payload.get('coverage'))
    if 'coverage' in data:
        if (incoming or payload.get('leads') or searches_added or accesses_added) and 'stop_reason' not in (payload.get('coverage') or {}):
            data['coverage']['stop_reason'] = ''
        lead_tracking.validate(data)
    if batch_id:
        data.setdefault('batches', {})[batch_id] = digest
    write(path, data)
    return {'recorded': True, 'jobs_saved': len(incoming), 'searches_added': searches_added,
            'accesses_added': accesses_added, **counts(data)}


def seed(path, source_path, include_pending=False):
    """Import identities and provenance from a selected prior run, never old job facts."""
    data = read(path)
    require_active(data)
    if 'coverage' not in data or data.get('mode', 'search') != 'search':
        raise ValueError('seed 仅用于 init 新建的覆盖搜索任务')
    source = Path(source_path).resolve()
    if source == Path(path).resolve():
        raise ValueError('不能把本轮账本作为历史来源')
    previous = read(source)
    module = report_module()
    result = module.check(previous)
    if result['errors']:
        raise ValueError('来源账本无效：' + '；'.join(result['errors']))
    if previous['as_of'] > data['as_of']:
        raise ValueError('来源观测日晚于本轮基准日')
    selected = {j['id']: s for s in ('kept', 'pending') if s == 'kept' or include_pending for j in result[s]}
    existing = {l['id'] for l in data.get('leads', [])}
    leads = []
    for job in result['records']:
        if job['id'] not in selected:
            continue
        lead = {'company': job['company'], 'title': job['title'], 'url': job['job_url']}
        identity_key = job.get('identity_key') or job.get('requisition_id')
        if identity_key:
            lead['identity_key'] = identity_key
        key = lead_tracking.lead_id(lead)
        origin = {'source': str(source), 'observed_at': previous['as_of'], 'previous_state': selected[job['id']]}
        if key in existing:
            leads.append({'id': key, 'origins': [origin]})
        else:
            leads.append({**lead, 'id': key, 'state': 'queued', 'important': True, 'origins': [origin]})
    return batch(path, {'leads': leads, 'coverage': {'sources': [
        {'path': str(source), 'note': f"导入已纳入{'及待核实' if include_pending else ''}线索{len(leads)}条；旧事实仅供复核定位"}]}})


def complete(path, output):
    """Mark a checked search report as delivered; render alone remains a draft."""
    data = read(path)
    if data.get('mode', 'search') != 'search':
        raise ValueError('补充/复核任务请使用 report_target.py publish')
    search_budget.validate(data)
    destination = Path(output).resolve()
    if destination == Path(path).resolve():
        raise ValueError('报告不能覆盖运行 JSON')
    raw = destination.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if data.get('status') == 'complete':
        if data.get('output') != str(destination) or data.get('output_sha256') != digest:
            raise ValueError('该任务已交付其他结果或交付文件已变化；新一轮需新任务')
        return {'completed': False, 'output': str(destination), **counts(data)}
    module = report_module()
    result = module.check(data)
    if result['errors']:
        raise ValueError('；'.join(result['errors']))
    lead_tracking.validate(data, final=True)
    content = raw.decode('utf-8-sig')
    findings = module.report_format.check(content)
    if findings['errors'] or not findings['managed']:
        raise ValueError('报告未通过固定格式检查：' + '；'.join(findings['errors'] or findings['warnings']))
    expected = module.report_format.structure(module.render(data, result))
    actual = module.report_format.structure(content)
    if {key: value[1] for key, value in actual[3].items()} != {key: value[1] for key, value in expected[3].items()}:
        raise ValueError('报告主表与当前运行筛选结果不一致，请重新渲染或更新事实')
    prefixes = ('# 岗位报告：', '检索基准日：', '时间：', '薪资：', '地点：', '其他硬条件：',
                '排除地点：', '岗位排除关键词：', '排序偏好：', '平台例外：',
                '<!-- findjob:platform-policy ')
    expected_conditions = [line for line in expected[0][:expected[1]] if line.startswith(prefixes)]
    actual_conditions = [line for line in actual[0][:actual[1]] if line.startswith(prefixes)]
    if actual_conditions != expected_conditions:
        raise ValueError('报告基准日或筛选条件与当前运行不一致，请使用当前结果')
    lead_tracking.check_rendered(content, lead_tracking.render(data, result, module.esc, module.link))
    data.update(status='complete', output=str(destination), output_sha256=digest,
                completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    write(path, data)
    return {'completed': True, 'output': str(destination), 'warnings': findings['warnings'], **counts(data)}


def status(path, limit=5):
    data = read(path)
    budget = data.get('profile', {}).get('budget', data.get('budget', {}))
    searches = data.get('searches', [])
    result = {'file': str(Path(path).resolve()), 'date': data.get('as_of', data.get('operation_date')),
            'mode': data.get('mode', 'search'), 'status': data.get('status', 'in_progress'),
            'source': data.get('source'), 'budget': budget, 'queries': len(searches),
            'reserved_queries': data.get('reserved_queries'), 'remaining_queries': max(0, budget.get('queries', 0) - len(searches)),
            'page_accesses': len(data.get('accesses', [])),
            'directions': sorted({s['direction'] for s in searches if s.get('direction')}),
            'recent_searches': searches[-limit:] if limit else [],
            'jobs_recorded': len(data.get('jobs', [])), 'recent_notes': data.get('notes', [])[-limit:] if limit else [],
            'batches_recorded': len(data.get('batches', {})),
            'output': data.get('output'), 'completed_at': data.get('completed_at')}
    if 'platform_policy' in data:
        result['query_budget'] = search_budget.summary(data)
        result['remaining_queries'] = result['query_budget']['total']['remaining']
    if 'coverage' in data:
        result['coverage'] = lead_tracking.summary(data)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    show = commands.add_parser('status')
    show.add_argument('--file', required=True)
    show.add_argument('--limit', type=int, default=5)
    add = commands.add_parser('record')
    add.add_argument('--file', required=True)
    add.add_argument('--event', required=True, help='JSON file holding one event')
    add.add_argument('--page', action='store_true')
    bulk = commands.add_parser('batch', help='原子保存一批岗位、调用及说明')
    bulk.add_argument('--file', required=True)
    bulk.add_argument('--batch', required=True, help='JSON file holding jobs/searches/accesses/notes/leads/coverage')
    seeds = commands.add_parser('seed', help='从指定旧搜索账本导入已纳入线索，不复制旧事实')
    seeds.add_argument('--file', required=True)
    seeds.add_argument('--source-run', required=True)
    seeds.add_argument('--include-pending', action='store_true')
    finish = commands.add_parser('complete', help='检查搜索报告并登记交付完成')
    finish.add_argument('--file', required=True)
    finish.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'status' and args.limit < 0:
            raise ValueError('limit 不可为负')
        if args.command == 'status':
            result = status(args.file, args.limit)
        elif args.command == 'batch':
            result = batch(args.file, read(args.batch))
        elif args.command == 'complete':
            result = complete(args.file, args.output)
        elif args.command == 'seed':
            result = seed(args.file, args.source_run, args.include_pending)
        else:
            result = record(args.file, read(args.event), args.page)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
