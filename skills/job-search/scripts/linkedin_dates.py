"""Opt-in LinkedIn age filtering; never invent an absolute publication date.

This module evaluates dates only. The caller must still apply status, salary,
business and employer rules. ``source_records`` must come from confirmed job
consolidation, not from similarly titled search results.
"""
import calendar
import copy
import json
import re
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


KINDS = {"published": "发布", "refreshed": "刷新", "job_time": "岗位时间"}
NON_JOB_TIME = re.compile(
    r"crawled|crawl(?:ing)?\s*(?:date|time)|相关推荐|相邻(?:职位|岗位)|推荐岗位|页脚|"
    r"抓取|转载收录|招聘者活跃|宣讲|search\s+snippet|footer|similar\s+jobs|"
    r"recommended|recruiter\s+active", re.I)
BODY_TIME = re.compile(r"正文|岗位时间|发布日期|发布时间|刷新|"
                       r"job\s+(?:body|date|time)|(?:body|detail).*?(?:time|date)", re.I)
RELATIVE = re.compile(
    r"(?<![A-Za-z0-9_.])(\d+)\s*(?:\+\s*)?(?:个\s*)?"
    r"(天|日|周|星期|月|年|days?|weeks?|months?|years?)\s*(?:前|ago)(?![A-Za-z0-9_])",
    re.I)


def _iso(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("日期必须为 YYYY-MM-DD")
    return date.fromisoformat(value)


def _url(value):
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
        parts.port  # Reject malformed ports as well as malformed hosts.
        return (parts.scheme in ("http", "https") and bool(parts.hostname)
                and not parts.username and not parts.password)
    except ValueError:
        return False


def _linkedin(value):
    if not _url(value):
        return False
    host = urlsplit(value).hostname.lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def _canonical(value):
    parts = urlsplit(value)
    query = sorted((key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
                   if not key.lower().startswith("utm_"))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"),
                       urlencode(query), ""))


def _back_months(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def validate_relative(job):
    """Validate stored observations on any platform, without enabling an exception."""
    records = job.get("relative_dates", [])
    if not isinstance(records, list):
        raise ValueError("relative_dates 须为数组")
    for record in records:
        if (not isinstance(record, dict)
                or not all(isinstance(record.get(key), str) and record[key].strip()
                           for key in ("text", "note"))
                or not _url(record.get("url"))):
            raise ValueError("relative_dates 每项须有 text/url/note/observed_at")
        try:
            _iso(record.get("observed_at"))
        except (TypeError, ValueError) as exc:
            raise ValueError("relative_dates observed_at 须为有效 YYYY-MM-DD") from exc


def _proof(record, body=False):
    if not isinstance(record, dict) or not _url(record.get("url")):
        return False
    note = record.get("note")
    if not isinstance(note, str) or not note.strip() or NON_JOB_TIME.search(note):
        return False
    if record.get("kind") not in (None, *KINDS):
        return False
    scope = record.get("scope")
    if scope is not None and scope not in ("job", "job_body", "body"):
        return False
    return not body or scope in ("job", "job_body", "body") or bool(BODY_TIME.search(note))


def _result(*, rejected=None, pending=None, notes=None, chosen=None,
            display="日期未核实（按 LinkedIn 例外保留）", evidence=None):
    return {"rejected": rejected or [], "pending": pending or [], "notes": notes or [],
            "date": copy.deepcopy(chosen), "display": display,
            "evidence": copy.deepcopy(evidence), "exception": True}


def _absolute(records, today, cutoff):
    reliable = [item for item in records if item.get("kind") in KINDS and _proof(item)]
    if not reliable:
        return None
    reliable.sort(key=lambda item: (item["kind"], item.get("value", ""), item["url"],
                                   item["note"], _stable(item)))
    try:
        values = [(item, _iso(item.get("value"))) for item in reliable]
    except ValueError:
        return _result(pending=["岗位绝对日期格式未核实"], display="岗位日期待核实",
                       evidence=reliable[0])
    if any(value > today for _, value in values):
        return _result(pending=["岗位证据含未来日期，需解决冲突"], display="岗位日期含未来时间，待核实",
                       evidence=reliable[0])
    by_kind = {kind: [pair for pair in values if pair[0]["kind"] == kind] for kind in KINDS}
    conflict = any(len({value for _, value in group}) > 1 for group in by_kind.values())
    published = by_kind["published"]
    updates = by_kind["refreshed"] + by_kind["job_time"]
    if published and updates and any(value < published[0][1] for _, value in updates):
        conflict = True
    if by_kind["refreshed"] and by_kind["job_time"]:
        conflict |= by_kind["refreshed"][0][1] != by_kind["job_time"][0][1]
    if conflict:
        return _result(pending=["同一岗位的可靠日期证据冲突，不能选择较年轻值"],
                       display="岗位日期冲突，待核实", evidence=reliable[0])
    # A verified refresh can follow an older publication; those are not conflicting dates.
    chosen, value = next(by_kind[kind][0] for kind in ("refreshed", "job_time", "published")
                         if by_kind[kind])
    display = f"{chosen['value']}（{KINDS[chosen['kind']]}；LinkedIn 日期例外）"
    if value <= cutoff:
        return _result(rejected=[f"岗位可靠日期已达 LinkedIn 年龄排除边界（≤{cutoff}）"],
                       chosen=chosen, display=display, evidence=chosen)
    return _result(chosen=chosen, display=display, evidence=chosen,
                   notes=["按 LinkedIn 日期例外保留；未知或相对时间未覆盖可靠绝对日期"])


def _bounds(record):
    matches = list(RELATIVE.finditer(record["text"]))
    if len(matches) != 1:
        return None
    match = matches[0]
    prefix = record["text"][:match.start()]
    if re.search(r"[+\-−]\s*$|\d\s*[-–—~～至]\s*$|\d\s+to\s*$", prefix, re.I):
        return None
    # Upper bounds cannot establish an old age. Explicit lower bounds can:
    # "over 3 months ago" / "3+ months ago" is at least three months old.
    if re.search(r"(?:less\s+than|under|no\s+more\s+than|not\s+more\s+than|"
                 r"不足|不到|(?<!不)少于|至多|最多|不超过|未超过|没有超过|<=|≤|<)\s*$", prefix, re.I):
        return None
    suffix = record["text"][match.end():]
    minimum = ("+" in match[0]
               or bool(re.search(r"(?:over|more\s+than|at\s+least|至少|超过|不少于|不低于|>=|≥|>)\s*$",
                                 prefix, re.I))
               or bool(re.match(r"\s*(?:以上|或以上|or\s+more\b|or\s+older\b)", suffix, re.I)))
    unit = match[2].lower()
    observed = _iso(record["observed_at"])
    try:
        count = int(match[1])
        if unit in ("月", "年") or unit.startswith(("month", "year")):
            factor = 12 if unit == "年" or unit.startswith("year") else 1
            # A displayed "2 months ago" is younger than the 3-month boundary at observation.
            newest = _back_months(observed, count * factor)
            oldest = _back_months(observed, (count + 1) * factor) + timedelta(days=1)
        else:
            factor = 7 if unit in ("周", "星期") or unit.startswith("week") else 1
            newest = observed - timedelta(days=count * factor)
            # Include observation-day uncertainty rather than fabricate a precise date.
            oldest = observed - timedelta(days=(count + 1) * factor)
    except (OverflowError, ValueError):
        return None
    return (date.min if minimum else oldest), newest


def evaluate(job, today, policy):
    """Return date findings for an explicitly enabled, confirmed LinkedIn job, else None.

    Relative observations remain relative. A newer observation of the same URL
    replaces the earlier observation; other URLs must agree on an age interval.
    Ageing uses the original observation day, so refresh cannot perpetually reuse
    a stale "3 days ago". Closed status and other hard conditions belong to the caller.
    """
    if (not isinstance(policy, dict) or type(policy.get("version")) is not int
            or policy["version"] != 1 or type(policy.get("linkedin_age_months")) is not int
            or policy["linkedin_age_months"] <= 0 or policy.get("linkedin_allow_unknown") is not True):
        return None
    urls = {job.get("job_url", "")}
    urls.update(record.get("url", "") for record in job.get("source_records", [])
                if isinstance(record, dict))
    linkedin_urls = {_canonical(value) for value in urls if _linkedin(value)}
    if not linkedin_urls:
        return None
    today = _iso(today) if isinstance(today, str) else today
    if type(today) is not date:
        raise ValueError("today 须为 date 或 YYYY-MM-DD")
    validate_relative(job)
    cutoff = _back_months(today, policy["linkedin_age_months"])
    absolute = _absolute(job.get("dates", []), today, cutoff)
    if absolute is not None:
        return absolute
    observations = [item for item in job.get("relative_dates", [])
                    if _proof(item, body=True) and _linkedin(item["url"])
                    and _canonical(item["url"]) in linkedin_urls]
    latest = {}
    for item in observations:
        key = _canonical(item["url"])
        latest[key] = max(latest.get(key, ""), item["observed_at"])
    observations = [item for item in observations
                    if item["observed_at"] == latest[_canonical(item["url"])]]
    observations.sort(key=lambda item: (item["observed_at"], item["url"], item["text"],
                                       item["note"], _stable(item)))
    if any(_iso(item["observed_at"]) > today for item in observations):
        return _result(pending=["相对时间观测日位于未来，需核实"],
                       display="相对时间观测日异常，待核实", evidence=observations[0])
    bounded = [(item, bounds) for item in observations if (bounds := _bounds(item)) is not None]
    if not bounded:
        return _result(evidence=observations[0] if observations else None,
                       notes=["LinkedIn 岗位日期未核实，按明确例外保留；未认定近期或当前在招"])
    oldest = max(bounds[0] for _, bounds in bounded)
    newest = min(bounds[1] for _, bounds in bounded)
    evidence = bounded[0][0]
    raw = "；".join(dict.fromkeys(f"{item['text']}（{item['observed_at']}观测）"
                               for item, _ in bounded))
    if oldest > newest:
        return _result(pending=["同一岗位相对年龄观测冲突，不能选择较年轻值"],
                       display=f"{raw}；年龄冲突待核实", evidence=evidence)
    notes = ["相对原文与观测日仅用于年龄例外筛选，未伪造绝对发布日期"]
    if any(_iso(item["observed_at"]) < today for item, _ in bounded):
        notes.append(f"已按观测后实际流逝时间复核，截至 {today}，未重新使用旧相对词作为今日年龄")
    if newest <= cutoff:
        return _result(rejected=[f"相对年龄及观测后流逝时间已达到 {policy['linkedin_age_months']} 自然月"],
                       notes=notes, display=f"{raw}；已达年龄排除边界", evidence=evidence)
    if oldest <= cutoff:
        return _result(notes=notes + ["相对年龄区间跨越自然月边界，日期未核实；按例外保留"],
                       display=f"{raw}；日期未核实（按 LinkedIn 例外保留）", evidence=evidence)
    return _result(notes=notes, display=f"{raw}；按 LinkedIn 例外保留", evidence=evidence)
