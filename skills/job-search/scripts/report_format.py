"""Shared Markdown fields, targeted edits and structural checks. No web claims."""
import html
import re
from datetime import date
from urllib.parse import quote, unquote, urlsplit

DETAILS = {
    'duties': '工作职责', 'requirements': '具体要求', 'benefits': '福利',
    'work_time': '工作时间（每日起止/每周天数）', 'overtime': '加班情况',
    'insured': '社保人数（法人/年份）', 'legal_risk': '法律风险',
}
STATES = {'verified': '已核实', 'not_disclosed': '已查未披露', 'unverified': '未核实',
          'blocked': '来源受阻，未核实', 'conflict': '来源冲突'}
HEADERS = ['编号', '公司', '岗位', '地点', '薪资', '学历/经验要求', '刷新/招聘时间', '招聘链接']
BASIC = dict(zip(('company', 'title', 'location', 'salary', 'education_experience', 'date', 'job_url'), range(1, 8)))


def esc(value):
    text = html.escape(str(value), quote=False)
    for char in ('\\', '|', '*', '_', '[', ']', '`', '#'):
        text = text.replace(char, '\\' + char)
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')


def link(address, label='来源'):
    return f'[{esc(label)}]({quote(address, safe=":/?&=%#@+;,~!$*-._")})'


def valid_url(value):
    return isinstance(value, str) and not any(c.isspace() for c in value) and urlsplit(value).scheme in ('http', 'https') and bool(urlsplit(value).netloc)


def validate_detail(detail):
    if not isinstance(detail, dict) or not isinstance(detail.get('text'), str):
        raise ValueError('详情需 text 文本')
    if detail.get('status', 'verified' if detail['text'].strip() else 'unverified') not in STATES:
        raise ValueError('详情 status 无效')
    sources = detail.get('sources')
    if not isinstance(sources, list) or not all(valid_url(u) for u in sources):
        raise ValueError('详情 sources 无效')
    if detail['text'].strip() and not sources:
        raise ValueError('非空详情必须保留来源')
    for field in ('scope', 'entity', 'year', 'observed_at'):
        if field in detail and not isinstance(detail[field], str):
            raise ValueError(f'详情 {field} 须为文本')
    if detail.get('observed_at'):
        date.fromisoformat(detail['observed_at'])
    if 'observations' in detail:
        if not isinstance(detail['observations'], list):
            raise ValueError('observations 须为数组')
        for observation in detail['observations']:
            if 'observations' in observation:
                raise ValueError('observations 不嵌套')
            validate_detail(observation)


def detail_line(key, detail=None):
    if detail is None:
        return f'- **{DETAILS[key]}**：未核实。'
    validate_detail(detail)
    values = []
    for observation in detail.get('observations', [detail]):
        status = observation.get('status', 'verified' if observation['text'].strip() else 'unverified')
        metadata = [observation[k] for k in ('scope', 'entity', 'year', 'observed_at') if observation.get(k)]
        text = observation['text'].rstrip().rstrip('。')
        value = (esc(text) + '。') if text else ''
        if status != 'verified' or not text:
            value += STATES[status] + '。'
        if metadata:
            value += '（' + esc('；'.join(metadata)) + '）'
        value += ' '.join(link(u) for u in sorted(set(observation['sources'])))
        values.append(value)
    return f'- **{DETAILS[key]}**：' + '；'.join(values)


def cells(line):
    return [c.strip() for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]


def table_line(values):
    return '| ' + ' | '.join(values) + ' |'


def structure(content):
    lines = content.splitlines()
    headers = [i for i, line in enumerate(lines) if line.lstrip().startswith('|') and cells(line) == HEADERS]
    if len(headers) != 1:
        return None
    start = headers[0]
    end = start + 2
    while end < len(lines) and lines[end].lstrip().startswith('|'):
        end += 1
    rows = {cells(lines[i])[0]: (i, cells(lines[i])) for i in range(start + 2, end)}
    sections = {}
    headings = [i for i, line in enumerate(lines) if line.startswith(('## ', '### '))]
    for i in headings:
        match = re.match(r'^### (\d+)｜', lines[i])
        if match:
            stop = next((j for j in headings if j > i), len(lines))
            if match[1] in sections:
                raise ValueError('岗位详情编号重复')
            sections[match[1]] = (i, stop)
    return lines, start, end, rows, sections


def basic_line(row):
    return f'- **基本信息**：{row[3]}；{row[4]}；{row[5]}；{row[6]}。'


def check(content):
    data = structure(content)
    if data is None:
        return {'errors': [], 'warnings': ['非标准简表：保留原格式，由代理核对主表、详情与统计'], 'managed': False}
    lines, start, end, rows, sections = data
    errors = []
    if len(cells(lines[start + 1])) != 8 or not all(re.fullmatch(r':?-{3,}:?', c) for c in cells(lines[start + 1])):
        errors.append('简表分隔行必须为 8 列')
    if len(rows) != end - start - 2:
        errors.append('主表编号重复')
    if set(rows) != set(sections):
        errors.append('主表与逐岗详情编号不一致')
    for number, (_, row) in rows.items():
        if len(row) != 8:
            errors.append(f'{number} 简表列数不是 8')
            continue
        if number in sections:
            a, b = sections[number]
            block = lines[a:b]
            if basic_line(row) not in block:
                errors.append(f'{number} 简表与详情基本信息不一致')
            urls = re.findall(r'\]\(([^)]+)\)', row[7])
            if len(urls) != 1 or not any(line.startswith('- **招聘链接**：') and urls[0] in line for line in block):
                errors.append(f'{number} 招聘链接不一致')
    total = re.search(r'本轮纳入 \*\*(\d+) 条岗位、(\d+) 家单位\*\*', content)
    if total and (int(total[1]) != len(rows) or int(total[2]) != len({row[1] for _, row in rows.values() if len(row) == 8})):
        errors.append('报告数量与主表不一致')
    return {'errors': errors, 'warnings': [], 'managed': True}


def replace_field(block, label, replacement):
    pattern = re.compile(r'^- \*\*' + re.escape(label) + r'\*\*：.*$', re.M)
    matches = list(pattern.finditer(block))
    if len(matches) > 1:
        raise ValueError(f'字段重复，需局部确认：{label}')
    return pattern.sub(lambda m: replacement, block) if matches else block.rstrip() + '\n' + replacement + '\n'


def apply(content, patch):
    """Patch standard reports without re-parsing them into complete job records."""
    data = structure(content)
    if data is None:
        raise ValueError('非标准清单请局部编辑；无需重建 JSON')
    lines, start, end, rows, sections = data
    if set(patch) - {'jobs', 'window'} or not isinstance(patch.get('jobs', []), list):
        raise ValueError('patch 只接受 jobs/window')
    edits, removed, changes, touched = [], set(), [], set()
    # Correct the historical separator defect when touching an old generated report.
    edits.append((start + 1, start + 2, ['|' + '---|' * 8]))
    for update in patch.get('jobs', []):
        allowed = {'number', 'job_url', 'details', 'basic', 'state', 'reason', 'sources', 'checked_at', 'date_evidence'}
        if set(update) - allowed:
            raise ValueError('岗位补丁包含未知字段')
        number = update.get('number')
        if not number and update.get('job_url'):
            matches = [n for n, (_, row) in rows.items() if any(unquote(u) == update['job_url'] for u in re.findall(r'\]\(([^)]+)\)', row[7]))]
            if len(matches) != 1:
                raise ValueError('招聘链接未唯一定位主表岗位，请指定 number')
            number = matches[0]
        if number not in rows or number not in sections or number in touched:
            raise ValueError('岗位编号不存在、重复或缺详情')
        touched.add(number)
        row_index, old_row = rows[number]
        row = list(old_row)
        a, b = sections[number]
        block = '\n'.join(lines[a:b]) + '\n'
        for field, value in update.get('details', {}).items():
            if field not in DETAILS:
                raise ValueError(f'未知详情字段：{field}')
            block = replace_field(block, DETAILS[field], detail_line(field, value))
        basic = update.get('basic', {})
        if set(basic) - BASIC.keys() or not all(isinstance(v, str) for v in basic.values()):
            raise ValueError('basic 字段或类型无效')
        for field, value in basic.items():
            if field == 'job_url' and not valid_url(value):
                raise ValueError('新招聘链接无效')
            row[BASIC[field]] = link(value, '岗位') if field == 'job_url' else esc(value)
        state = update.get('state', 'kept')
        if state not in ('kept', 'pending', 'excluded'):
            raise ValueError('state 无效')
        if basic or 'state' in update:
            if not update.get('reason') or not update.get('sources') or not all(valid_url(u) for u in update['sources']):
                raise ValueError('基本信息或筛选变化需 reason 和 sources')
            date.fromisoformat(update['checked_at'])
            block = replace_field(block, '本轮核实', '- **本轮核实**：' + esc(update['checked_at'] + '；' + update['reason']) + '。' + ' '.join(link(u) for u in update['sources']))
        if 'date' in basic:
            proof = update.get('date_evidence', {})
            if not valid_url(proof.get('url')) or not proof.get('note'):
                raise ValueError('岗位日期变更需 date_evidence；访问日期不是岗位日期')
            block = replace_field(block, '日期依据', '- **日期依据**：' + esc(proof['note']) + '。' + link(proof['url']))
        if basic:
            block = replace_field(block, '基本信息', basic_line(row))
            block = re.sub(r'^### .*', lambda m: f'### {number}｜{row[1]} — {row[2].replace("【相关方向】", "")}', block, count=1)
            if 'job_url' in basic:
                block = replace_field(block, '招聘链接', '- **招聘链接**：' + link(basic['job_url'], '职位详情') + '。')
        if state != 'kept':
            removed.add(number)
            block = re.sub(r'^### ', '#### 历史 ', block, count=1)
            edits.extend([(row_index, row_index + 1, []), (a, b, [])])
            changes.append(('history', block))
        else:
            edits.extend([(row_index, row_index + 1, [table_line(row)]), (a, b, block.rstrip('\n').splitlines() + [''])])
        if basic or 'state' in update:
            changes.append(('change', table_line([old_row[1] + ' / ' + old_row[2], '；'.join(old_row[3:7]),
                           state + '；' + '；'.join(row[3:7]), esc(update['reason']), esc(update['checked_at']),
                           ' '.join(link(u) for u in update['sources'])])))
    for a, b, replacement in sorted(edits, reverse=True):
        lines[a:b] = replacement
    result = '\n'.join(lines).rstrip() + '\n'
    remaining = structure(result)[3]
    companies = len({row[1] for _, row in remaining.values()})
    adjacent = sum('【相关方向】' in row[2] for _, row in remaining.values())
    result = re.sub(r'本轮纳入 \*\*\d+ 条岗位、\d+ 家单位\*\*，其中相关方向 \d+ 条',
                    f'本轮纳入 **{len(remaining)} 条岗位、{companies} 家单位**，其中相关方向 {adjacent} 条', result)
    if 'window' in patch:
        w = patch['window']
        for key in ('as_of', 'published_since', 'refreshed_since'):
            date.fromisoformat(w[key])
        if w.get('mode', 'any') not in ('any', 'all'):
            raise ValueError('window.mode 无效')
        result = re.sub(r'检索基准日：\d{4}-\d{2}-\d{2}', '检索基准日：' + w['as_of'], result, count=1)
        result = re.sub(r'^时间：发布自 .*$', lambda m: f"时间：发布自 {w['published_since']} 起，{'且' if w.get('mode') == 'all' else '或'}刷新自 {w['refreshed_since']} 起，均截至 {w['as_of']}。", result, count=1, flags=re.M)
    if changes:
        result += '\n### 本轮变化\n\n| 公司/岗位 | 原值 | 本轮值/结论 | 原因 | 核实日期 | 证据 |\n|---|---|---|---|---|---|\n'
        result += '\n'.join(value for kind, value in changes if kind == 'change') + '\n'
        histories = [value for kind, value in changes if kind == 'history']
        if histories:
            result += '\n### 移出主表的历史详情\n\n' + '\n'.join(histories)
    findings = check(result)
    if findings['errors']:
        raise ValueError('；'.join(findings['errors']))
    return result, {'updated': sorted(touched), 'removed': sorted(removed), 'remaining': len(remaining)}
