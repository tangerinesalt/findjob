"""Editable Markdown profiles: one visible table, no hidden copy of the data."""
from __future__ import annotations

import copy
import html
import json
from pathlib import Path
import re


# label, object path, value type, default; defaults also upgrade legacy JSON for export.
FIELDS = [
    ('格式版本', 'schema_version', 'int', 1),
    ('画像名称', 'name', 'text', ''),
    ('岗位名称', 'target_roles', 'list', []),
    ('检索关键词', 'keywords', 'list', []),
    ('包含相邻岗位', 'include_adjacent', 'bool', True),
    ('工作地点', 'locations', 'list', []),
    ('排除地点', 'excluded_locations', 'list', []),
    ('招聘类型', 'employment_types', 'list', []),
    ('工作方式要求', 'work_arrangements', 'list', []),
    ('发布窗口（月）', 'freshness.published_months', 'int', 2),
    ('刷新窗口（月）', 'freshness.refreshed_months', 'int', 1),
    ('时间条件关系', 'freshness.mode', 'mode', 'any'),
    ('薪资币种', 'salary.currency', 'text', 'CNY'),
    ('月薪下限至少（元）', 'salary.min_lower_monthly', 'number', 0),
    ('月薪上限至少（元）', 'salary.min_upper_monthly', 'number', 0),
    ('接受面议或未披露薪资', 'salary.allow_unknown', 'bool', True),
    ('岗位排除关键词', 'excluded_keywords', 'list', []),
    ('剔除游戏岗位', 'exclude_games', 'bool', False),
    ('剔除猎头', 'exclude_headhunters', 'bool', True),
    ('剔除雇主不明确的信息', 'exclude_unclear_employers', 'bool', True),
    ('其他硬性条件', 'hard_requirements', 'list', []),
    ('排序偏好', 'preferences', 'list', []),
    ('学历、经验与技能背景', 'background', 'text', ''),
    ('搜索预算（query）', 'budget.queries', 'int', 60),
    ('补充预算（query）', 'budget.enrichment_queries', 'int', 12),
    ('单岗参考时间（分钟）', 'budget.per_job_minutes', 'number', 3),
]


def put(data, path, value):
    parts = path.split('.')
    for part in parts[:-1]:
        data = data.setdefault(part, {})
    data[parts[-1]] = value


def get(data, path, default):
    for part in path.split('.'):
        if not isinstance(data, dict) or part not in data:
            return copy.deepcopy(default)
        data = data[part]
    return copy.deepcopy(data)


def defaults(roles):
    data = {}
    for _, path, _, value in FIELDS:
        put(data, path, copy.deepcopy(value))
    data.update(name='、'.join(roles), target_roles=list(roles), keywords=list(roles))
    return data


def encode(value):
    # Entities keep Markdown pipes, markup and list separators unambiguous.
    text = ''.join(f'&#{ord(char)};' if char in '&<>|;；\\`*_[]#' else char for char in str(value))
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')


def decode(value):
    return html.unescape(value.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n'))


def render(profile):
    out = ['# 求职画像', '',
           '只修改“值”列；字段名称保持不变。此表是搜索读取的唯一配置来源。', '',
           '多项用中文分号“；”分隔；空白表示未设置。布尔值填“是/否”。时间关系填“或/且”。',
           '薪资门槛以所填币种的元/月计，0表示不设该门槛；时间窗口按自然月计算，0表示当天。',
           '地点、招聘类型、工作方式及排除项为筛选条件；排序偏好与个人背景不自动成为硬条件。', '',
           '| 属性 | 值 |', '|---|---|']
    for label, path, kind, default in FIELDS:
        fallback = profile.get('keywords', []) if path == 'target_roles' else default
        value = get(profile, path, fallback)
        if kind == 'list':
            display = '；'.join(encode(item) for item in value)
        elif kind == 'bool':
            display = '是' if value else '否'
        elif kind == 'mode':
            display = '或' if value == 'any' else '且'
        else:
            display = encode(value)
        out.append(f'| {label} | {display} |')
    return '\n'.join(out) + '\n'


def parse(text):
    fields = {label: (path, kind) for label, path, kind, _ in FIELDS}
    rows = {}
    for line in text.splitlines():
        if not line.strip().startswith('|'):
            continue
        cells = re.split(r'(?<!\\)\|', line.strip())
        if len(cells) != 4 or cells[0] or cells[-1]:
            raise ValueError('画像表格应为两列；值中的竖线请写为 &#124; 或 \\|')
        label, value = (cell.strip() for cell in cells[1:3])
        if label == '属性' or re.fullmatch(r':?-+:?', label):
            continue
        if label not in fields:
            raise ValueError(f'未知画像属性：{label}；请保留固定字段名称')
        if label in rows:
            raise ValueError(f'画像属性重复：{label}')
        rows[label] = value.replace('\\|', '&#124;')
    missing = set(fields) - rows.keys()
    if missing:
        raise ValueError('画像缺少属性：' + '、'.join(sorted(missing)))
    result = {}
    for label, (path, kind) in fields.items():
        raw = rows[label]
        value = decode(raw)
        if kind == 'list':
            value = [decode(x.strip()) for x in raw.split('；') if x.strip()]
        elif kind == 'bool':
            if value not in ('是', '否'):
                raise ValueError(f'{label}应填是或否')
            value = value == '是'
        elif kind == 'mode':
            if value not in ('或', '且'):
                raise ValueError('时间条件关系应填或/且')
            value = 'any' if value == '或' else 'all'
        elif kind == 'int':
            if not re.fullmatch(r'\d+', value):
                raise ValueError(f'{label}应填非负整数')
            value = int(value)
        elif kind == 'number':
            try:
                value = float(value)
            except ValueError:
                raise ValueError(f'{label}应填数值，不带K或元等单位') from None
        put(result, path, value)
    return result


def load(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig')
    return parse(text) if path.suffix.lower() == '.md' else json.loads(text)


def save_new(profile, workspace):
    folder = Path(workspace).resolve()
    if not folder.is_dir():
        raise ValueError('工作空间不存在或不是目录')
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', profile['name']).strip(' .')[:80].rstrip(' .')
    if not stem:
        stem = '求职画像'
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', stem, re.I):
        stem = '_' + stem
    content = render(profile)
    number = 1
    while True:
        suffix = '' if number == 1 else f'_{number}'
        path = folder / f'{stem}{suffix}.md'
        try:
            with path.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
            return path
        except FileExistsError:
            number += 1
