"""Optional search coverage ledger. Checks recorded work, never proves web facts."""
import copy
import hashlib
import json
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


START = '<!-- findjob:coverage v1 -->'
END = '<!-- /findjob:coverage -->'
STATES = {'queued', 'reviewed', 'merged', 'deferred'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def address(value):
    if not text(value):
        return False
    parts = urlsplit(value)
    return parts.scheme in ('http', 'https') and bool(parts.netloc)


def canonical(value):
    parts = urlsplit(value)
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith('utm_'))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), urlencode(query), ''))


def identity(lead):
    # Shared announcement URLs can contain multiple roles; URL alone is not identity.
    norm = lambda s: ''.join(s.split()).casefold().replace('（', '(').replace('）', ')')
    return (canonical(lead['url']), norm(lead['company']), norm(lead['title']), lead.get('identity_key', ''))


def lead_id(lead):
    return 'lead-' + hashlib.sha256(json.dumps(identity(lead), ensure_ascii=False).encode('utf-8')).hexdigest()[:16]


def unique(items):
    result = []
    for item in items:
        if item not in result:
            result.append(copy.deepcopy(item))
    return result


def initial():
    return {'version': 1, 'sources': [], 'source_note': '', 'stop_reason': ''}


def update(run, leads=(), coverage=None):
    require('coverage' in run, '旧运行未启用覆盖记录；新任务由 init 建立')
    require(run.get('mode', 'search') == 'search', '补充/复核不追加搜索覆盖记录')
    if coverage is not None:
        require(isinstance(coverage, dict), 'coverage 须为对象')
        require(not (set(coverage) - {'sources', 'source_note', 'stop_reason'}), 'coverage 更新字段无效')
        for key, value in coverage.items():
            if key == 'sources':
                require(isinstance(value, list), 'coverage.sources 须为数组')
                run['coverage'][key] = unique(run['coverage'].get(key, []) + value)
            else:
                run['coverage'][key] = copy.deepcopy(value)
    require(isinstance(leads, (list, tuple)), 'leads 须为数组')
    positions = {lead['id']: i for i, lead in enumerate(run.setdefault('leads', []))}
    seen = set()
    for item in leads:
        require(isinstance(item, dict) and text(item.get('id')), '线索缺 id')
        require(item['id'] not in seen, '同一批次线索 id 重复')
        seen.add(item['id'])
        if item['id'] in positions:
            index = positions[item['id']]
            previous = run['leads'][index]
            merged = {**previous, **copy.deepcopy(item)}
            for key in ('origins', 'attempt_ids'):
                if key in item:
                    require(isinstance(item[key], list), f'线索 {key} 须为数组')
                    merged[key] = unique(previous.get(key, []) + item[key])
            require(identity(merged) == identity(previous), '线索身份不能原地更换；另建线索并说明关联')
            run['leads'][index] = merged
        else:
            positions[item['id']] = len(run['leads'])
            run['leads'].append(copy.deepcopy(item))
    validate(run)


def validate(run, final=False):
    if 'coverage' not in run:
        require(not run.get('leads'), 'leads 需要 coverage 版本记录')
        return
    coverage = run['coverage']
    require(run.get('mode', 'search') == 'search', 'coverage 仅用于搜索任务')
    require(isinstance(coverage, dict) and type(coverage.get('version')) is int and coverage['version'] == 1,
            '覆盖记录版本无效')
    require(not (set(coverage) - {'version', 'sources', 'source_note', 'stop_reason'}), 'coverage 有未知字段')
    require(isinstance(coverage.get('sources'), list), 'coverage.sources 须为数组')
    for source in coverage['sources']:
        require(isinstance(source, dict) and text(source.get('path')) and text(source.get('note')),
                '覆盖来源缺 path/note')
    for key in ('source_note', 'stop_reason'):
        require(isinstance(coverage.get(key, ''), str), f'coverage.{key} 须为文本')
    leads = run.get('leads', [])
    require(isinstance(leads, list), 'leads 须为数组')
    jobs = {j['id']: j for j in run.get('jobs', []) if isinstance(j, dict) and 'id' in j}
    events = {e['event_id'] for e in run.get('searches', []) + run.get('accesses', []) if e.get('event_id')}
    ids, identities = set(), set()
    for lead in leads:
        require(isinstance(lead, dict), '线索须为对象')
        for key in ('id', 'company', 'title'):
            require(text(lead.get(key)), f'线索缺 {key}')
        require(address(lead.get('url')), '线索缺有效 HTTP(S) url')
        require(isinstance(lead.get('identity_key', ''), str), '线索 identity_key 须为文本')
        require(lead['id'] not in ids and identity(lead) not in identities, '重复线索；同岗合并 origins 并更新同一 id')
        ids.add(lead['id'])
        identities.add(identity(lead))
        require(lead.get('state') in STATES, '线索 state 无效')
        require(type(lead.get('important', True)) is bool, '线索 important 须为布尔值')
        origins = lead.get('origins')
        require(isinstance(origins, list) and origins, '线索缺 origins 来源')
        for origin in origins:
            require(isinstance(origin, dict) and text(origin.get('source')), '线索来源缺 source')
            require(origin.get('previous_state') in ('kept', 'pending', 'excluded', 'new', 'user', 'unknown'),
                    '线索 previous_state 无效')
            if origin.get('observed_at'):
                date.fromisoformat(origin['observed_at'])
        attempts = lead.get('attempt_ids', [])
        require(isinstance(attempts, list) and all(text(a) and a in events for a in attempts),
                '线索 attempt_ids 必须引用本轮已有调用 event_id')
        for key in ('reason', 'gap', 'next_step', 'match_note'):
            require(isinstance(lead.get(key, ''), str), f'线索 {key} 须为文本')
        if lead['state'] in ('reviewed', 'merged'):
            require(text(lead.get('job_id')) and lead['job_id'] in jobs, '已处理线索缺有效 job_id')
            require(bool(attempts), '已处理线索缺本轮调用关联')
            job = jobs[lead['job_id']]
            job_identity = identity({'url': job.get('job_url', ''), 'company': job.get('company', ''), 'title': job.get('title', '')})
            if lead['state'] == 'merged' or job_identity[:3] != identity(lead)[:3]:
                require(text(lead.get('match_note')), '跨URL或合并线索须说明同岗依据 match_note')
        if lead['state'] == 'deferred':
            require(text(lead.get('reason')), '暂缓线索须记录具体 reason')
        if final:
            require(not (lead.get('important', True) and lead['state'] == 'queued'),
                    f"重要线索尚未处理或说明暂缓：{lead['id']} {lead['company']} / {lead['title']}")
    if final:
        require(coverage['sources'] or text(coverage.get('source_note')), '收尾前须记录相关历史来源或 source_note')
        require(text(coverage.get('stop_reason')), '收尾前须记录全局 stop_reason')


def summary(run):
    if 'coverage' not in run:
        return None
    leads = run.get('leads', [])
    return {'version': run['coverage']['version'], 'sources': run['coverage']['sources'],
            'counts': {s: sum(l['state'] == s for l in leads) for s in sorted(STATES)},
            'unresolved_important': [l['id'] for l in leads if l.get('important', True) and l['state'] == 'queued'],
            'stop_reason': run['coverage'].get('stop_reason', '')}


def render(run, result, esc, link):
    if 'coverage' not in run:
        return []
    outcomes = {i['id']: state for state in ('kept', 'pending', 'excluded') for i in result[state]}
    for duplicate in result['duplicates']:
        outcomes[duplicate['id']] = outcomes.get(duplicate['kept_id'], 'pending')
    labels = {'kept': '纳入', 'pending': '待核实', 'excluded': '证据支持排除'}
    out = [START, f"#### 搜索阶段线索去向（{esc(run['as_of'])}）", '',
           '以下为该次搜索的处置记录；后续补充或复核以更新后的岗位主表及复核记录为准。',
           '线索去向不计入合格岗位数量；本轮调用关联仅供追溯，不自动证明证据真实。', '']
    for source in run['coverage']['sources']:
        out.append(f"- 对照来源：{esc(source['path'])}；{esc(source['note'])}")
    if run['coverage'].get('source_note'):
        out.append('- 来源说明：' + esc(run['coverage']['source_note']))
    out += ['', '| 公司 / 岗位 | 原记录 | 本轮去向 | 说明 |', '|---|---|---|---|']
    for lead in run.get('leads', []):
        previous = sorted({o['previous_state'] for o in lead['origins']})
        outcome = outcomes.get(lead.get('job_id'))
        label = labels.get(outcome, '未复核')
        if lead['state'] == 'merged':
            label = '合并去重；' + label
        elif lead['state'] == 'deferred':
            label = '暂缓／未复核'
        elif lead['state'] == 'queued':
            label = '未复核'
        elif outcome == 'kept':
            label = '继续纳入' if 'kept' in previous else '新增纳入'
        elif outcome == 'pending' and 'kept' in previous:
            label = '转待核实'
        note = '；'.join(lead[k] for k in ('reason', 'gap', 'next_step', 'match_note') if lead.get(k))
        out.append(f"| {esc(lead['company'] + ' / ' + lead['title'])} {link(lead['url'], '线索')} | {esc('、'.join(previous))} | {label} | {esc(note)} |")
    out += ['', '- 全局停止理由：' + esc(run['coverage'].get('stop_reason') or '尚未填写（草稿）'), END]
    return out


def check_rendered(content, expected):
    if not expected:
        return
    lines = content.splitlines()
    require(lines.count(START) == 1 and lines.count(END) == 1, '报告缺少或重复覆盖记录区块，请重新渲染')
    start, end = lines.index(START), lines.index(END)
    require(lines[start:end + 1] == expected, '报告覆盖记录与当前账本不一致，请重新渲染')
