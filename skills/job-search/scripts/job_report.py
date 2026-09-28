#!/usr/bin/env python3
"""Local evidence-record checker and Markdown renderer; no network or model calls."""
from __future__ import annotations

import argparse
import calendar
import copy
import html
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import importlib.util
from datetime import date
from urllib.parse import quote, parse_qsl, urlencode, urlsplit, urlunsplit

_profile_spec = importlib.util.spec_from_file_location('fingjob_profile_format', Path(__file__).with_name('profile_format.py'))
profile_format = importlib.util.module_from_spec(_profile_spec)
_profile_spec.loader.exec_module(profile_format)
_facts_spec = importlib.util.spec_from_file_location('fingjob_job_facts', Path(__file__).with_name('job_facts.py'))
job_facts = importlib.util.module_from_spec(_facts_spec)
_facts_spec.loader.exec_module(job_facts)
_format_spec = importlib.util.spec_from_file_location('fingjob_report_format', Path(__file__).with_name('report_format.py'))
report_format = importlib.util.module_from_spec(_format_spec)
_format_spec.loader.exec_module(report_format)


DETAILS = report_format.DETAILS
KINDS = {"published": "发布", "refreshed": "刷新", "job_time": "岗位时间"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value, replace=True):
    """Atomic replacement by the one owning process; init never overwrites."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if not replace:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        return
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def iso(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "日期必须为 YYYY-MM-DD")
    return date.fromisoformat(value)


def back_months(day, months):
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def strings(value):
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        parts = urlsplit(value)
        return parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username and not parts.password
    except ValueError:
        return False


def proof(value):
    return isinstance(value, dict) and url(value.get("url")) and isinstance(value.get("note"), str) and bool(value["note"].strip())


def merge(base, overlay):
    result = copy.deepcopy(base)
    require(isinstance(overlay, dict), "overrides 必须为 JSON 对象")
    for key, value in overlay.items():
        result[key] = merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else copy.deepcopy(value)
    return result


def validate_profile(p):
    require(isinstance(p, dict), "profile 必须为对象")
    required = {"schema_version", "name", "keywords", "locations", "exclude_games", "exclude_headhunters", "include_adjacent", "freshness", "salary", "budget", "preferences"}
    optional = {"hard_requirements", "target_roles", "excluded_keywords", "excluded_locations", "employment_types", "work_arrangements", "background", "exclude_unclear_employers"}
    require(required <= p.keys() and p.keys() <= required | optional, "画像字段缺失或未知")
    require(type(p["schema_version"]) is int and p["schema_version"] == 1, "仅支持画像 schema_version=1")
    require(isinstance(p["name"], str) and p["name"].strip(), "画像缺少 name")
    for key in ("keywords", "locations", "preferences", "hard_requirements", "target_roles", "excluded_keywords", "excluded_locations", "employment_types", "work_arrangements"):
        require(strings(p.get(key, [])), f"画像 {key} 必须为字符串数组")
    require(bool(p["keywords"]), "画像必须给出目标岗位关键词")
    for key in ("exclude_games", "exclude_headhunters", "include_adjacent"):
        require(type(p[key]) is bool, f"画像 {key} 必须为布尔值")
    require(type(p.get('exclude_unclear_employers', True)) is bool, 'exclude_unclear_employers 必须为布尔值')
    require(isinstance(p.get('background', ''), str), 'background 必须为文本')
    f = p["freshness"]
    require(isinstance(f, dict) and {"published_months", "refreshed_months"} <= f.keys() and f.keys() <= {"published_months", "refreshed_months", "mode"}, "freshness 字段无效")
    require(all(type(f[k]) is int and 0 <= f[k] <= 120 for k in ('published_months', 'refreshed_months')), "时间窗口须为 0–120 个自然月")
    require(f.get('mode', 'any') in ('any', 'all'), '时间关系必须为 any/all')
    s = p["salary"]
    require(isinstance(s, dict) and s.keys() == {"currency", "min_lower_monthly", "min_upper_monthly", "allow_unknown"}, "salary 规则字段无效")
    require(isinstance(s["currency"], str) and bool(s["currency"].strip()), "薪资规则缺币种")
    require(number(s["min_lower_monthly"]) and number(s["min_upper_monthly"]), "薪资门槛应为非负有限数")
    require(type(s["allow_unknown"]) is bool, "薪资未知策略无效")
    b = p["budget"]
    require(isinstance(b, dict) and b.keys() == {"queries", "enrichment_queries", "per_job_minutes"}, "budget 字段无效")
    require(type(b["queries"]) is int and b["queries"] >= 0, "queries 预算须为非负整数")
    require(type(b["enrichment_queries"]) is int and 0 <= b["enrichment_queries"] <= b["queries"], "补充预算不能超过总预算")
    require(number(b["per_job_minutes"]) and b["per_job_minutes"] > 0, "单岗时间应大于零")


def validate_run(run):
    require(isinstance(run, dict), "运行文件必须为对象")
    require(run.get("schema_version") == 1, "仅支持运行 schema_version=1")
    iso(run.get("as_of"))
    validate_profile(run.get("profile"))
    reserved = run.get("reserved_queries")
    require(type(reserved) is int and 0 <= reserved <= run["profile"]["budget"]["queries"], "预留额度超过预算或字段无效")
    searches = run.get("searches")
    require(isinstance(searches, list) and len(searches) <= reserved, "实际 query 数超过预留额度或 searches 无效")
    for item in searches:
        require(isinstance(item, dict), "查询日志必须为对象")
        require(all(isinstance(item.get(k), str) and item[k].strip() for k in ("query", "source")), "查询日志缺 query/source")
        require(item.get("phase") in ("discovery", "enrichment"), "查询 phase 无效")
        require(item.get("outcome") in ("success", "no_matches", "blocked"), "查询 outcome 无效")
        require(isinstance(item.get("note", ""), str), "查询 note 须为文本")
    require(sum(x["phase"] == "enrichment" for x in searches) <= run["profile"]["budget"]["enrichment_queries"], "补充搜索超出预算")
    require(isinstance(run.get("jobs"), list) and strings(run.get("notes", [])), "jobs/notes 类型无效")


def validate_job(j):
    require(isinstance(j, dict), "岗位必须为对象")
    for key in ("id", "company", "title", "location"):
        require(isinstance(j.get(key), str) and j[key].strip(), f"岗位缺 {key}")
    for key in ("education", "experience"):
        require(isinstance(j.get(key, ""), str), f"{key} 必须为文本")
    for key in ('identity_key', 'requisition_id', 'team'):
        require(isinstance(j.get(key, ''), str), f'{key} 必须为文本')
    require(url(j.get("job_url")), "岗位缺有效 HTTP(S) 直接链接")
    for key, allowed in {
        "status": {"open", "unknown", "closed"},
        "relevance": {"core", "adjacent", "unrelated", "unknown"},
        "games": {"yes", "no", "unknown"},
        "recruiter": {"employer", "headhunter", "anonymous", "unknown"},
        "profile_match": {"yes", "no", "unknown"},
    }.items():
        require(j.get(key) in allowed, f"岗位 {key} 无效")
    if j.get("deadline") is not None:
        iso(j["deadline"])
    require(isinstance(j.get("evidence", {}), dict), "evidence 须为对象")
    s = j.get("salary")
    require(isinstance(s, dict) and isinstance(s.get("text"), str) and s["text"].strip(), "薪资必须保留原文 text")
    require(isinstance(s.get("currency"), str), "薪资缺 currency")
    require(s.get("period") in ("month", "year", "day", "hour", "unknown"), "薪资周期无效")
    for key in ("min", "max"):
        require(key in s and (s[key] is None or number(s[key])), "薪资数值须为元、非负有限数或 null")
    require(s.get("months") is None or type(s["months"]) is int and 1 <= s["months"] <= 24, "年发薪月数无效")
    require(s["min"] is None or s["max"] is None or s["min"] <= s["max"], "薪资上下限颠倒")
    dates = j.get("dates", [])
    require(isinstance(dates, list), "dates 须为数组")
    for d in dates:
        require(isinstance(d, dict) and d.get("kind") in set(KINDS) | {"crawled"}, "日期类型无效")
        iso(d.get("value"))
    details = j.get("details", {})
    require(isinstance(details, dict) and details.keys() <= DETAILS.keys(), "details 有未知字段")
    for key, detail in details.items():
        report_format.validate_detail(detail)
    require(strings(j.get("notes", [])), "岗位 notes 须为字符串数组")
    require(isinstance(j.get("discussions", []), list), "discussions 须为数组")
    for item in j.get("discussions", []):
        require(isinstance(item, dict) and url(item.get("url")) and all(isinstance(item.get(k), str) and item[k].strip() for k in ("text", "date", "scope")), "讨论缺 text/url/date/scope")


def evaluate(j, p, today):
    rejected, pending, notes = [], [], list(j.get("notes", []))
    e = j.get("evidence", {})
    if j["status"] == "closed" or j.get("deadline") and iso(j["deadline"]) < today:
        rejected.append("已截止或暂停招聘")
    if j["relevance"] == "unrelated" or j["profile_match"] == "no":
        rejected.append("不符合目标岗位或画像硬条件")
    if j["relevance"] == "adjacent" and not p["include_adjacent"]:
        rejected.append("画像不包含相邻方向")
    if p["exclude_games"] and j["games"] == "yes":
        rejected.append("游戏或混合游戏职责")
    unclear = p.get('exclude_unclear_employers', True)
    if unclear and j["recruiter"] == "anonymous" or p["exclude_headhunters"] and j["recruiter"] == "headhunter":
        rejected.append("匿名雇主或猎头招聘")
    for key in ("relevance", "profile_match", "recruiter"):
        if key == 'recruiter' and j[key] in ('anonymous', 'unknown') and not unclear:
            notes.append('招聘主体不明确，按画像保留；未认定为企业直招')
            if p['exclude_headhunters']:
                pending.append('招聘者类型未知，尚不能排除猎头')
            elif not proof(e.get(key)):
                pending.append('缺少 recruiter 的可核实证据')
            continue
        if j[key] == "unknown" or not proof(e.get(key)):
            pending.append(f"缺少 {key} 的可核实证据")
    if p["exclude_games"] and (j["games"] == "unknown" or not proof(e.get("games"))):
        pending.append("非游戏业务未核实")
    dates = [d for d in j.get("dates", []) if d["kind"] in KINDS and proof(d)]
    current = [d for d in dates if back_months(today, p["freshness"]["published_months" if d["kind"] == "published" else "refreshed_months"]) <= iso(d["value"]) <= today]
    if any(iso(d["value"]) > today for d in dates):
        pending.append("岗位证据含未来日期，需解决冲突")
    if not dates:
        pending.append("缺少岗位发布/刷新时间证据")
    elif not current and not pending:
        rejected.append("岗位时间超出窗口")
    elif not current:
        pending.append("未核实窗口内岗位时间")
    if p['freshness'].get('mode', 'any') == 'all':
        for kinds, label in (({'published'}, '发布'), ({'refreshed'}, '刷新')):
            typed = [d for d in dates if d['kind'] in kinds]
            if not typed:
                pending.append(f'时间条件要求同时满足，缺少明确{label}日期')
            elif not any(d in current for d in typed):
                if all(iso(d['value']) <= today for d in typed):
                    rejected.append(f'{label}日期超出窗口')
                else:
                    pending.append(f'{label}日期未核实')
    s, rule = j["salary"], p["salary"]
    values = [s["min"], s["max"]]
    known = any(v is not None for v in values)
    if known and not proof(e.get("salary")):
        pending.append("数值薪资缺来源证据")
    elif not known:
        if not rule["allow_unknown"]:
            rejected.append("画像不接受面议或未披露薪资")
        else:
            notes.append("薪资无可比较数值，未证明达到薪资门槛")
    elif s["currency"].upper() != rule["currency"].upper() or s["period"] not in ("month", "year"):
        if rule["min_lower_monthly"] > 0 or rule["min_upper_monthly"] > 0:
            pending.append("币种或计薪周期不可直接与月薪门槛比较")
    else:
        divisor = (s.get("months") or 12) if s["period"] == "year" else 1
        lower = s["min"] / divisor if s["min"] is not None else None
        upper = s["max"] / divisor if s["max"] is not None else None
        if lower is not None and lower < rule["min_lower_monthly"] or upper is not None and upper < rule["min_upper_monthly"]:
            rejected.append("薪资低于下限或上限门槛")
        if s["period"] == "year":
            notes.append(f"年薪按 {divisor} 个月作等额筛选比较，非固定月薪承诺")
        if None in values:
            notes.append("薪资范围未完整披露，仅检查已知边界")
    if j["status"] == "unknown":
        notes.append("当前开放状态未独立确认")
    chosen = max(current, key=lambda d: (d['value'], d['kind'], d['url'], d['note'])) if current else None
    conflicts = j.get('merge_conflicts', [])
    core_conflicts = [c for c in conflicts if c['field'] not in ('education', 'experience')]
    for conflict in conflicts:
        notes.append('来源冲突 ' + conflict['field'] + '：' + '；'.join(str(v['value']) + ' ' + v['url'] for v in conflict['values']))
    if core_conflicts:
        pending = ['重复来源的核心字段冲突，需按证据解决：' + '、'.join(c['field'] for c in core_conflicts)] + pending
    state = "pending" if core_conflicts else "excluded" if rejected else "pending" if pending else "kept"
    if core_conflicts:
        rejected = []
    return {"id": j["id"], "state": state, "reasons": rejected or pending, "date": chosen, "notes": list(dict.fromkeys(notes))}


def canonical(value):
    return job_facts.canonical(value)


def norm(value):
    return job_facts.norm(value)


def check(run):
    result = {"errors": [], "kept": [], "excluded": [], "pending": [], "duplicates": []}
    try:
        validate_run(run)
    except (ValueError, TypeError) as exc:
        result["errors"].append(str(exc))
        return result
    ids, valid = set(), []
    for index, job in enumerate(run["jobs"]):
        try:
            validate_job(job)
            require(job["id"] not in ids, "id 重复；合并证据或使用不同来源ID")
            ids.add(job["id"])
            valid.append(job)
        except (ValueError, TypeError) as exc:
            result["errors"].append(f"jobs[{index}]: {exc}")
    records, result['duplicates'] = job_facts.consolidate(valid)
    result['records'] = records
    for job in records:
        item = evaluate(job, run['profile'], iso(run['as_of']))
        result[item['state']].append(item)
    identities = {j['id']: tuple(norm(j[k]) for k in ('company', 'title', 'location')) + (canonical(j['job_url']), j['id']) for j in records}
    for state in ('kept', 'excluded', 'pending'):
        result[state].sort(key=lambda i: (-(date.fromisoformat(i['date']['value']).toordinal() if i['date'] else 0), identities[i['id']]))
    return result


def esc(value):
    return report_format.esc(value)


def link(address, label="来源"):
    return report_format.link(address, label)


def render(run, result):
    p, today = run["profile"], iso(run["as_of"])
    jobs = {j["id"]: j for j in run["jobs"]}
    jobs.update({j['id']: j for j in result.get('records', [])})
    kept = result["kept"]
    company_count = len({norm(jobs[x["id"]]["company"]) for x in kept})
    adjacent = sum(jobs[x["id"]]["relevance"] == "adjacent" for x in kept)
    out = [f"# 岗位报告：{esc(p['name'])}", "<!-- fingjob:report v2 -->", "", f"检索基准日：{today}。本轮纳入 **{len(kept)} 条岗位、{company_count} 家单位**，其中相关方向 {adjacent} 条；不代表全网总量。", "",
           "## 第一部分：岗位简表", "",
           f"时间：发布自 {back_months(today, p['freshness']['published_months'])} 起，{'且' if p['freshness'].get('mode', 'any') == 'all' else '或'}刷新自 {back_months(today, p['freshness']['refreshed_months'])} 起，均截至 {today}。",
           f"薪资：{esc(p['salary']['currency'])} 月薪下限 ≥ {p['salary']['min_lower_monthly']:g}，上限 ≥ {p['salary']['min_upper_monthly']:g}；允许未知：{'是' if p['salary']['allow_unknown'] else '否'}。",
           f"地点：{esc('、'.join(p['locations']) or '不限')}；排除游戏：{'是' if p['exclude_games'] else '否'}；排除猎头：{'是' if p['exclude_headhunters'] else '否'}。",
           f"其他硬条件：{esc('；'.join(p.get('hard_requirements', [])) or '无')}。", "",
           f"排除地点：{esc('、'.join(p.get('excluded_locations', [])) or '无')}；招聘类型：{esc('、'.join(p.get('employment_types', [])) or '不限')}；工作方式：{esc('、'.join(p.get('work_arrangements', [])) or '不限')}。",
           f"岗位排除关键词：{esc('、'.join(p.get('excluded_keywords', [])) or '无')}；排除雇主不明确：{'是' if p.get('exclude_unclear_employers', True) else '否'}。",
           f"排序偏好：{esc('；'.join(p.get('preferences', [])) or '无')}。默认按岗位日期倒序，同日按公司/岗位/地点/链接稳定排序；偏好未自动评分。", "",
            report_format.table_line(report_format.HEADERS),
           "|---|---|---|---|---|---|---|---|"]
    for i, item in enumerate(kept, 1):
        j, d = jobs[item["id"]], item["date"]
        title = j["title"] + ("【相关方向】" if j["relevance"] == "adjacent" else "")
        cells = [f"{i:02d}", j["company"], title, j["location"], j["salary"]["text"], f"{j.get('education') or '未披露'} / {j.get('experience') or '未披露'}", f"{d['value']}（{KINDS[d['kind']]}）"]
        out.append("| " + " | ".join(esc(x) for x in cells) + " | " + link(j["job_url"], "岗位") + " |")
    if not kept:
        out += ["", "本轮未采集到符合全部条件且证据足够的岗位。该结果不表示市场没有岗位；来源情况及未纳入原因见下文。"]
    out += ["", "## 第二部分：岗位详情", "", "以下为公开资料归纳。未披露/未核实不等于没有；个人评论不是司法结论。脚本检查不替代网页证据核实。"]
    for i, item in enumerate(kept, 1):
        j, d = jobs[item["id"]], item["date"]
        out += ["", f"### {i:02d}｜{esc(j['company'])} — {esc(j['title'])}", "",
                f"- **基本信息**：{esc(j['location'])}；{esc(j['salary']['text'])}；{esc(j.get('education') or '未披露')} / {esc(j.get('experience') or '未披露')}；{d['value']}（{KINDS[d['kind']]}）。",
                f"- **招聘链接**：{link(j['job_url'], '职位详情')}。",
                f"- **日期依据**：{esc(d['note'])}。{link(d['url'])}"]
        if j.get("deadline"):
            out.append(f"- **截止日期**：{j['deadline']}。")
        for key, label in DETAILS.items():
            detail = j.get("details", {}).get(key)
            out.append(report_format.detail_line(key, detail))
        discussions = j.get("discussions", [])
        out.append("- **岗位讨论及链接**：" + ("未取得可核实的对应讨论。" if not discussions else ""))
        for discussion in discussions:
            out.append(f"  - {esc(discussion['date'])}，{esc(discussion['scope'])}：{esc(discussion['text'])}。{link(discussion['url'], '讨论')}（个人说法，不作已证实事实）。")
        for key, label in (("relevance", "方向依据"), ("games", "业务依据"), ("recruiter", "招聘主体"), ("profile_match", "画像匹配"), ("salary", "薪资依据")):
            evidence = j.get("evidence", {}).get(key)
            if proof(evidence):
                out.append(f"- **{label}**：{esc(evidence['note'])}。{link(evidence['url'])}")
        if item["notes"]:
            out.append("- **缺口/口径**：" + "；".join(esc(x) for x in item["notes"]) + "。")
    out += ["", "### 未纳入与去重", "", f"剔除 {len(result['excluded'])} 条；待核实 {len(result['pending'])} 条；重复 {len(result['duplicates'])} 条。以下不计入主表。"]
    for state, label in (("excluded", "剔除"), ("pending", "待核实"), ("duplicates", "重复")):
        for item in result[state]:
            j = jobs[item["id"]]
            out.append(f"- {label}：{esc(j['company'])} / {esc(j['title'])}：{esc('；'.join(item['reasons']))}。{link(j['job_url'], '职位')}")
            for conflict in j.get('merge_conflicts', []):
                out.append('  - ' + esc(conflict['field']) + ' 来源冲突：' + '；'.join(esc(v['value']) + ' ' + link(v['url']) for v in conflict['values']))
    out += ["", "### 检索覆盖与限制", "", f"实际搜索 {len(run['searches'])} 个 query，预算已预留 {run['reserved_queries']} / {p['budget']['queries']}；打开详情页不计搜索 query。预留额度不等于实际调用量。"]
    sources = {}
    for query in run["searches"]:
        source = sources.setdefault(query["source"], {"success": 0, "no_matches": 0, "blocked": 0, "notes": []})
        source[query["outcome"]] += 1
        if query.get("note"):
            source["notes"].append(query["note"])
    for name, source in sources.items():
        out.append(f"- {esc(name)}：成功采集查询 {source['success']}，无匹配查询 {source['no_matches']}，受阻查询 {source['blocked']}。" + esc("；".join(dict.fromkeys(source["notes"]))))
    if not sources:
        out.append("- 本运行没有实际搜索日志；仅对已输入记录进行了筛选，不能宣称完成新一轮网络搜索。")
    out += ["- " + esc(note) for note in run.get("notes", [])]
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="建立运行，不覆盖原文件")
    init.add_argument("--profile", required=True)
    init.add_argument("--overrides")
    init.add_argument("--as-of", required=True)
    init.add_argument("--run", required=True)
    budget = commands.add_parser("budget", help="单写者预留搜索额度；不执行搜索")
    budget.add_argument("--run", required=True)
    budget.add_argument("--count", type=int, required=True)
    verify = commands.add_parser("check", help="检查及筛选事实记录")
    verify.add_argument("--run", required=True)
    report = commands.add_parser("render", help="生成一份两部分 Markdown 报告")
    report.add_argument("--run", required=True)
    report.add_argument("--output", required=True)
    report.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            profile = profile_format.load(args.profile)
            if args.overrides:
                profile = merge(profile, load(args.overrides))
            validate_profile(profile)
            iso(args.as_of)
            run = dict(schema_version=1, as_of=args.as_of, profile=profile, reserved_queries=0, searches=[], jobs=[], notes=[])
            save(args.run, run, replace=False)
            print(f"Created: {Path(args.run).resolve()}")
            return 0
        run = load(args.run)
        if args.command == "budget":
            validate_run(run)
            require(args.count > 0, "预留 query 数必须大于零")
            total = run["reserved_queries"] + args.count
            require(total <= run["profile"]["budget"]["queries"], "预算不足；未修改运行文件")
            run["reserved_queries"] = total
            save(args.run, run)
            print(json.dumps({"reserved_queries": total, "remaining": run["profile"]["budget"]["queries"] - total}))
            return 0
        result = check(run)
        if args.command == "check" or result["errors"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["errors"]:
            return 1
        if args.command == "render":
            require(Path(args.output).resolve() != Path(args.run).resolve(), "报告不能覆盖运行 JSON")
            save(args.output, render(run, result), replace=args.replace)
            print(f"Report: {Path(args.output).resolve()} ({len(result['kept'])} jobs)")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
