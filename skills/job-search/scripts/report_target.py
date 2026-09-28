"""Select a local job report and keep follow-up drafts out of completed reports.

No network access, job parsing, or evidence verification is performed here.
"""
import argparse
from datetime import date
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit

_spec = importlib.util.spec_from_file_location('fingjob_report_format', Path(__file__).with_name('report_format.py'))
report_format = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_format)


_store_spec = importlib.util.spec_from_file_location('fingjob_file_store', Path(__file__).resolve().parents[3] / 'scripts/file_store.py')
file_store = importlib.util.module_from_spec(_store_spec)
_store_spec.loader.exec_module(file_store)
write_json = file_store.save

def read(path):
    return Path(path).read_text(encoding="utf-8-sig")


def is_report(path):
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".md":
        return False
    try:
        content = read(path)
    except (OSError, UnicodeError):
        return False
    # Ignore code examples in guides. Recognize older, manually written tables too.
    fenced = False
    fence = ""
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            if not fenced:
                fenced, fence = True, stripped[:3]
            elif stripped.startswith(fence):
                fenced = False
            continue
        if not fenced:
            lines.append(line)
    title = next((line for line in lines if re.match(r"^#\s+", line)), "")
    if not re.search(r"岗位|招聘|职位|\bjobs?\b", title, re.I):
        return False
    # Classify document purpose before any subtitle containing the target role.
    purpose = re.split(r"[:：]", title, maxsplit=1)[0].strip()
    if re.search(r"(?:分析|对比|比较|说明|指南|画像|测试报告)$", purpose):
        return False
    for i, line in enumerate(lines[:-1]):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
        company = any(c in {"公司", "公司/招聘单位", "招聘单位", "企业", "公司名称", "雇主"} for c in cells)
        role = any(c in {"岗位", "职位", "岗位名称", "职位名称"} for c in cells)
        location_salary = any(c in {"地点", "工作地点", "城市", "薪资", "薪资待遇", "薪资范围"} for c in cells)
        separator = all(re.fullmatch(r":?-{3,}:?", c.strip()) for c in lines[i + 1].strip().strip("|").split("|"))
        if company and role and location_salary and separator:
            return True
    return False


def rebase_links(content, source_dir, destination_dir):
    """Rebase local Markdown links; preserve URLs, anchors and code examples."""
    if Path(source_dir).resolve() == Path(destination_dir).resolve():
        return content

    def address(value):
        wrapped = value.startswith('<') and value.endswith('>')
        raw = value[1:-1] if wrapped else value
        parts = urlsplit(raw)
        if parts.scheme or parts.netloc or not parts.path or Path(unquote(parts.path)).is_absolute():
            return value
        target = (Path(source_dir) / unquote(parts.path)).resolve()
        try:
            rebased = Path(os.path.relpath(target, destination_dir)).as_posix()
        except ValueError:  # Different Windows drives: use an absolute Markdown path.
            rebased = target.as_posix()
        result = urlunsplit(('', '', quote(rebased, safe='/:~!$&\'*,;=@-._'), parts.query, parts.fragment))
        return '<' + result + '>' if wrapped else result

    result, fence = [], None
    for line in content.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith(('```', '~~~')):
            if fence is None:
                fence = stripped[:3]
            elif stripped.startswith(fence):
                fence = None
            result.append(line)
            continue
        if fence:
            result.append(line)
            continue
        # Leave inline code intact. Support inline/image links and reference definitions.
        pieces = re.split(r'(`+[^`]*`+)', line)
        for i in range(0, len(pieces), 2):
            pieces[i] = re.sub(r'(\]\()(<[^>\n]+>|(?:[^\s()\\]|\\.|\([^()]*\))+)',
                               lambda m: m[1] + address(m[2]), pieces[i])
            pieces[i] = re.sub(r'^(\s{0,3}\[[^\]]+\]:\s*)(<[^>\n]+>|\S+)',
                               lambda m: m[1] + address(m[2]), pieces[i])
        result.append(''.join(pieces))
    return ''.join(result)


def output_name(stem, ending):
    # Reserve space for suffix/extension on both UTF-8 and Windows filesystems.
    while len((stem + ending).encode('utf-8')) > 240 or len((stem + ending).encode('utf-16-le')) // 2 > 240:
        stem = stem[:-1]
    return stem.rstrip(' .') + ending


def local_path(value, workspace):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace / path
    if not path.suffix and not path.exists():
        path = path.with_suffix(".md")
    return path.resolve()


def resolve(workspace, report=None, context_report=None):
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError(f"工作空间不存在：{workspace}")
    warnings = []
    if report:
        target = local_path(report, workspace)
        if not is_report(target):
            raise ValueError(f"指定文件不存在或未识别为岗位清单：{target}；不会自动换用其他文件。")
        return {"report": str(target), "selected_by": "explicit", "warnings": []}
    if context_report:
        target = local_path(context_report, workspace)
        if is_report(target):
            return {"report": str(target), "selected_by": "conversation", "warnings": []}
        warnings.append(f"对话清单不可用，改查工作空间：{target}")
    # Root only: internal drafts, fixture directories and unrelated projects stay out.
    candidates = [p.resolve() for p in workspace.iterdir() if is_report(p)]
    candidates.sort(key=lambda p: (-p.stat().st_mtime_ns, p.name.casefold(), str(p)))
    if not candidates:
        raise ValueError("当前工作空间没有可识别的岗位清单；请指定清单或先执行 job-search。")
    return {"report": str(candidates[0]), "selected_by": "modified_time", "warnings": warnings,
            "candidates": [str(p) for p in candidates]}


def prepare(workspace, mode, as_of, report=None, context_report=None, queries=None):
    date.fromisoformat(as_of)
    if queries is not None and (type(queries) is not int or queries < 0):
        raise ValueError('queries 必须为非负整数')
    if mode not in {"enrich", "refresh"}:
        raise ValueError("mode 必须是 enrich 或 refresh")
    workspace = Path(workspace).resolve()
    selected = resolve(workspace, report, context_report)
    source = Path(selected["report"])
    raw = source.read_bytes()
    parent = workspace / ".scratch" / "fingjob"
    parent.mkdir(parents=True, exist_ok=True)
    task_dir = Path(tempfile.mkdtemp(prefix=f"{mode}-{as_of}-", dir=parent))
    (task_dir / "source.md").write_bytes(raw)
    (task_dir / "working.md").write_bytes(raw)
    task = dict(schema_version=1, mode=mode, operation_date=as_of, workspace=str(workspace),
                source=str(source), source_sha256=hashlib.sha256(raw).hexdigest(),
                selected_by=selected["selected_by"], warnings=selected["warnings"],
                status="draft", output=None, searches=[], notes=[],
                budget={"queries": queries if queries is not None else 12 if mode == "enrich" else 60, "per_job_minutes": 3})
    write_json(task_dir / "task.json", task)
    return {**selected, "task": str(task_dir / "task.json"), "working": str(task_dir / "working.md"),
            "snapshot": str(task_dir / "source.md")}


def publish(task_path, summary):
    task_path = Path(task_path).resolve()
    task = json.loads(read(task_path))
    if task["status"] == "complete":
        raise ValueError(f"该任务已交付：{task['output']}；继续编辑应建立新任务。")
    if not summary.strip():
        raise ValueError("需要简短说明本轮补充或复核结果，包括未核实限制。")
    working = task_path.parent / "working.md"
    if not is_report(working):
        raise ValueError("工作稿缺少岗位清单结构，不能交付。")
    findings = report_format.check(read(working))
    if findings['errors']:
        raise ValueError('；'.join(findings['errors']))
    source = Path(task["source"])
    changed = not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != task["source_sha256"]
    label = {"enrich": "补充", "refresh": "复核"}[task["mode"]]
    ending = f"_{label}_{task['operation_date'].replace('-', '')}"
    # Publish to the active workspace, including when an explicit source is elsewhere.
    workspace = Path(task["workspace"])
    content = rebase_links(read(working), source.parent, workspace).rstrip() + f"\n\n## 本轮{label}记录\n\n处理日期：{task['operation_date']}（不是岗位发布日期或刷新日期）。\n\n{summary.strip()}\n"
    if changed:
        content += "\n原清单在处理期间发生变化或已移走；本结果基于任务开始时的快照。\n"
    for index in range(1, 10000):
        suffix = "" if index == 1 else f"_{index}"
        output = workspace / output_name(source.stem, f"{ending}{suffix}.md")
        try:
            with output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            break
        except FileExistsError:
            continue
    else:
        raise ValueError("同名文件过多，无法分配输出名称。")
    task.update(status="complete", output=str(output), summary=summary.strip())
    write_json(task_path, task)
    return {"output": str(output), "source_changed": changed, 'warnings': findings['warnings']}


def patch_report(task_path, patch_path):
    task_path = Path(task_path).resolve()
    task = json.loads(read(task_path))
    if task['status'] == 'complete':
        raise ValueError('已交付任务请另建任务')
    patch = json.loads(read(patch_path))
    if task['mode'] == 'enrich' and 'window' in patch:
        raise ValueError('补充任务不滚动原时间窗口')
    working = task_path.parent / 'working.md'
    content, summary = report_format.apply(read(working), patch)
    temporary = working.with_suffix('.tmp')
    temporary.write_text(content, encoding='utf-8')
    os.replace(temporary, working)
    task.setdefault('patches', []).append({'path': str(Path(patch_path).resolve()), **summary})
    write_json(task_path, task)
    return summary


def inspect_report(task_path, number=None, fields=None):
    data = report_format.structure(read(Path(task_path).parent / 'working.md'))
    if data is None:
        return {'managed': False, 'note': '非标准清单请读取工作稿相关段落'}
    lines, start, end, rows, sections = data
    if number is None:
        return {'conditions': '\n'.join(lines[:start]), 'rows': [row for _, row in rows.values()]}
    if number not in sections:
        raise ValueError('找不到该岗位详情编号')
    a, b = sections[number]
    if not fields:
        return {'number': number, 'text': '\n'.join(lines[a:b])}
    if any(field not in report_format.DETAILS for field in fields):
        raise ValueError('field 使用 duties/requirements/benefits/work_time/overtime/insured/legal_risk')
    labels = [report_format.DETAILS[field] for field in fields]
    return {'number': number, 'row': rows[number][1], 'text': '\n'.join(
        line for line in lines[a:b] if any(line.startswith('- **' + label + '**：') for label in labels))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("resolve", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", default=".")
        command.add_argument("--report")
        command.add_argument("--context-report")
        if name == "prepare":
            command.add_argument("--mode", choices=("enrich", "refresh"), required=True)
            command.add_argument("--as-of", required=True)
            command.add_argument('--queries', type=int)
    command = commands.add_parser("publish")
    command.add_argument("--task", required=True)
    command.add_argument("--summary", required=True)
    command = commands.add_parser('patch', help='按岗位/字段局部更新标准报告')
    command.add_argument('--task', required=True)
    command.add_argument('--patch', required=True)
    command = commands.add_parser('check', help='检查工作稿结构和主表/详情一致性')
    command.add_argument('--task', required=True)
    command = commands.add_parser('inspect', help='只读简表或选定岗位/字段')
    command.add_argument('--task', required=True)
    command.add_argument('--number')
    command.add_argument('--field', action='append')
    args = parser.parse_args(argv)
    try:
        if args.command == "resolve":
            result = resolve(args.workspace, args.report, args.context_report)
        elif args.command == "prepare":
            result = prepare(args.workspace, args.mode, args.as_of, args.report, args.context_report, args.queries)
        elif args.command == 'patch':
            result = patch_report(args.task, args.patch)
        elif args.command == 'inspect':
            result = inspect_report(args.task, args.number, args.field)
        elif args.command == 'check':
            result = report_format.check(read(Path(args.task).parent / 'working.md'))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result['errors'] else 0
        else:
            result = publish(args.task, args.summary)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
