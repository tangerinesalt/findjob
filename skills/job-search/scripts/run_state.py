"""Small append/status helper for search and follow-up ledgers; no network calls."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile


_store_spec = importlib.util.spec_from_file_location('findjob_file_store', Path(__file__).resolve().parents[3] / 'scripts/file_store.py')
file_store = importlib.util.module_from_spec(_store_spec)
_store_spec.loader.exec_module(file_store)
read, write = file_store.load, file_store.save

def record(path, event, page=False):
    data = read(path)
    if data.get('status') == 'complete':
        raise ValueError('已完成任务不能追加调用；新一轮需新任务')
    events = data.setdefault('accesses' if page else 'searches', [])
    event = dict(event)
    if event.get('event_id') and any(e.get('event_id') == event['event_id'] for e in events):
        return {'recorded': False, 'reason': '该 event_id 已记录'}
    if event.get('outcome') not in ('success', 'no_matches', 'blocked'):
        raise ValueError('outcome 无效')
    required = ('url',) if page else ('query', 'source')
    if any(not isinstance(event.get(k), str) or not event[k].strip() for k in required):
        raise ValueError('缺少调用身份字段')
    for key in ('new_jobs', 'new_fields'):
        if key in event and (type(event[key]) is not int or event[key] < 0):
            raise ValueError('增量必须是非负整数')
    if not page:
        budget = data.get('profile', {}).get('budget', data.get('budget', {}))
        limit = min(budget['queries'], data.get('reserved_queries', budget['queries']))
        if len(events) >= limit:
            raise ValueError('查询额度不足；search 任务须先预留，follow-up 使用本轮预算')
        event.setdefault('phase', 'enrichment' if data.get('mode') == 'enrich' else 'discovery')
        if event['phase'] not in ('discovery', 'enrichment'):
            raise ValueError('phase 无效')
        if event['phase'] == 'enrichment' and sum(e.get('phase') == 'enrichment' for e in events) >= budget.get('enrichment_queries', budget['queries']):
            raise ValueError('补充查询额度不足')
    events.append(event)
    write(path, data)
    return {'recorded': True, 'queries': len(data.get('searches', [])), 'page_accesses': len(data.get('accesses', []))}


def status(path, limit=5):
    data = read(path)
    budget = data.get('profile', {}).get('budget', data.get('budget', {}))
    searches = data.get('searches', [])
    return {'file': str(Path(path).resolve()), 'date': data.get('as_of', data.get('operation_date')),
            'mode': data.get('mode', 'search'), 'status': data.get('status', 'in_progress'),
            'source': data.get('source'), 'budget': budget, 'queries': len(searches),
            'reserved_queries': data.get('reserved_queries'), 'remaining_queries': max(0, budget.get('queries', 0) - len(searches)),
            'page_accesses': len(data.get('accesses', [])),
            'directions': sorted({s['direction'] for s in searches if s.get('direction')}),
            'recent_searches': searches[-limit:] if limit else [],
            'jobs_recorded': len(data.get('jobs', [])), 'recent_notes': data.get('notes', [])[-limit:] if limit else [],
            'output': data.get('output')}


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
    args = parser.parse_args(argv)
    try:
        if args.command == 'status' and args.limit < 0:
            raise ValueError('limit 不可为负')
        result = status(args.file, args.limit) if args.command == 'status' else record(args.file, read(args.event), args.page)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
