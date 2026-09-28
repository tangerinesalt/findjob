"""Deterministic, conservative consolidation of already collected evidence."""
import copy
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical(value):
    parts = urlsplit(value)
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith('utm_'))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), urlencode(query), ''))


def norm(value):
    return re.sub(r'\s+', '', value).casefold().replace('（', '(').replace('）', ')')


def stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def unique(values):
    return [v for _, v in sorted({stable(v): v for v in values}.items())]


def same_job(a, b):
    # An explicit distinction beats a reused URL or matching display title.
    for field in ('requisition_id', 'team', 'identity_key'):
        if a.get(field) and b.get(field) and norm(a[field]) != norm(b[field]):
            return False
    identity = lambda j: tuple(norm(j[k]) for k in ('company', 'title', 'location'))
    if norm(a['company']) != norm(b['company']) or norm(a['location']) != norm(b['location']):
        return False
    return (canonical(a['job_url']) == canonical(b['job_url']) or identity(a) == identity(b)
            or bool(a.get('identity_key') and a.get('identity_key') == b.get('identity_key')))


def consolidate(records):
    groups = []
    for record in sorted(records, key=lambda j: (canonical(j['job_url']), j['id'])):
        group = next((g for g in groups if all(same_job(record, other) for other in g)), None)
        if group is None:
            groups.append([record])
        else:
            group.append(record)
    merged, duplicates = [], []
    for group in groups:
        result = copy.deepcopy(group[0])
        result['merge_conflicts'] = unique(c for j in group for c in j.get('merge_conflicts', []))

        def conflict(field, candidates):
            values = unique({'value': value, 'url': j['job_url']} for j, value in candidates)
            if len({stable(x['value']) for x in values}) > 1:
                result['merge_conflicts'].append({'field': field, 'values': values})

        for field in ('status', 'relevance', 'games', 'recruiter', 'profile_match', 'deadline', 'education', 'experience'):
            candidates = [(j, j[field]) for j in group if j.get(field) not in (None, '', 'unknown')]
            if candidates:
                candidates.sort(key=lambda p: (not bool(p[0].get('evidence', {}).get(field, {}).get('note')), canonical(p[0]['job_url']), p[0]['id']))
                result[field] = candidates[0][1]
                evidence = candidates[0][0].get('evidence', {}).get(field)
                if evidence:
                    result.setdefault('evidence', {})[field] = copy.deepcopy(evidence)
                conflict(field, candidates)
        for field in ('requisition_id', 'team', 'identity_key'):
            values = sorted({j[field] for j in group if j.get(field)})
            if values:
                result[field] = values[0]
        salaries = [(j, j['salary']) for j in group if any(j['salary'].get(k) is not None for k in ('min', 'max'))]
        if salaries:
            # Select a complete observation, never synthesize an interval from two offers.
            salaries.sort(key=lambda p: (-sum(p[1].get(k) is not None for k in ('min', 'max')), canonical(p[0]['job_url']), p[0]['id']))
            result['salary'] = copy.deepcopy(salaries[0][1])
            result.setdefault('evidence', {})['salary'] = copy.deepcopy(salaries[0][0].get('evidence', {}).get('salary', {}))
            comparable = [(j, {k: s.get(k) for k in ('currency', 'period', 'min', 'max', 'months')}) for j, s in salaries]
            conflict('salary', comparable)
        result['dates'] = unique(d for j in group for d in j.get('dates', []))
        result['notes'] = sorted({note for j in group for note in j.get('notes', [])})
        result['discussions'] = unique(d for j in group for d in j.get('discussions', []))
        result['details'] = {}
        for field in sorted({k for j in group for k in j.get('details', {})}):
            observations = unique(o for j in group if field in j.get('details', {})
                                  for o in j['details'][field].get('observations', [j['details'][field]]))
            result['details'][field] = {
                'text': '；'.join(dict.fromkeys(o['text'] for o in observations if o['text'].strip())),
                'sources': sorted({u for o in observations for u in o['sources']}),
                'observations': observations,
            }
        result['merge_conflicts'] = unique(result['merge_conflicts'])
        result['source_records'] = unique({'id': j['id'], 'url': j['job_url']} for j in group)
        result['evidence_sources'] = {field: unique(j['evidence'][field] for j in group if field in j.get('evidence', {}))
                                      for field in sorted({k for j in group for k in j.get('evidence', {})})}
        merged.append(result)
        duplicates.extend({'id': j['id'], 'kept_id': result['id'], 'reasons': ['同一岗位证据已合并；不重复计数']} for j in group[1:])
    return merged, sorted(duplicates, key=lambda d: (d['kept_id'], d['id']))
