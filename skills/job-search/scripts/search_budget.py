"""Query reservations and independent platform pools; no network operations.

Runs without platform_policy keep the legacy single pool. A policy never
grants extra queries to enrich/refresh tasks, even when inherited explicitly.
"""
import re


_PLATFORMS = {'yupao': 'yupao.com', 'linkedin': 'linkedin.com'}
_SITE = re.compile(r'(?<![^\s(])(-?)site:([^\s\"\'()<>|]+)', re.IGNORECASE)


def default_policy():
    """Return a fresh policy for a new search run, without changing its profile."""
    return {'version': 1, 'extra_queries': {'yupao': 5, 'linkedin': 5},
            'linkedin_age_months': 3, 'linkedin_allow_unknown': True}


def _integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(label + '须为非负整数')
    return value


def _policy(run):
    if 'platform_policy' not in run:
        return None
    policy = run['platform_policy']
    required = {'version', 'linkedin_age_months', 'linkedin_allow_unknown'}
    if not isinstance(policy, dict) or not required <= policy.keys() or set(policy) - required - {'extra_queries'}:
        raise ValueError('platform_policy 字段无效')
    if type(policy['version']) is not int or policy['version'] != 1:
        raise ValueError('仅支持 platform_policy version=1')
    _integer(policy['linkedin_age_months'], 'LinkedIn 日期月数')
    if type(policy['linkedin_allow_unknown']) is not bool:
        raise ValueError('LinkedIn 未知日期策略须为布尔值')
    extras = policy.get('extra_queries')
    if 'extra_queries' not in policy and run.get('mode', 'search') != 'search':
        return policy
    if not isinstance(extras, dict) or extras.keys() != _PLATFORMS.keys():
        raise ValueError('extra_queries 须包含 yupao/linkedin 两个池')
    for name, amount in extras.items():
        if _integer(amount, name + ' 额外额度') > 5:
            raise ValueError(name + ' 额外查询上限为5')
    return policy


def _domain(value):
    if not isinstance(value, str):
        raise ValueError('domains 须为域名字符串数组')
    host = value.strip().lower().rstrip('.')
    if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', host):
        raise ValueError('域名无效：' + value)
    return host


def _within(host, target):
    return host == target or host.endswith('.' + target)


def _unquoted(query):
    """Mask quoted phrases so literal site: text cannot establish query scope."""
    visible = []
    quote = None
    escaped = False
    for char in query:
        if quote is not None:
            visible.append(' ')
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
        elif char in ('\"', "'"):
            quote = char
            visible.append(' ')
        else:
            visible.append(char)
    return ''.join(visible), quote is None


def _scope(event, bucket):
    if event.get('phase', 'discovery') != 'discovery':
        raise ValueError('平台额外池仅用于 discovery')
    query = event.get('query')
    if not isinstance(query, str) or not query.strip():
        raise ValueError('平台额外查询缺 query')
    target = _PLATFORMS[bucket]
    domains = event.get('domains')
    explicit = False
    if domains is not None:
        if not isinstance(domains, list) or not domains:
            raise ValueError('domains 须为非空域名数组')
        explicit = all(_within(_domain(value), target) for value in domains)
        if not explicit:
            raise ValueError('平台额外池不能用于其他域名')
    visible, balanced = _unquoted(query)
    if not explicit and (not balanced or re.search(r'\bOR\b|\|', visible, re.IGNORECASE)):
        raise ValueError('平台额外查询含未限定分支或未闭合引号；请用显式 domains 或拆分查询')
    sites = [match.group(2).split('/', 1)[0] for match in _SITE.finditer(visible) if not match.group(1)]
    if any(not _within(_domain(host), target) for host in sites):
        raise ValueError('平台额外池不能混用其他 site: 域名')
    if not explicit and not sites:
        raise ValueError('平台额外查询须用对应 site: 域名或显式 domains')


def _bucket(event, policy):
    # Legacy event metadata was not interpreted as a budget allocation.
    bucket = event.get('budget_bucket', 'general') if policy is not None else 'general'
    if bucket not in ('general', *_PLATFORMS):
        raise ValueError('budget_bucket 无效')
    return bucket


def _snapshot(run):
    if not isinstance(run, dict):
        raise ValueError('运行须为对象')
    policy = _policy(run)
    profile = run.get('profile', {})
    if not isinstance(profile, dict):
        raise ValueError('profile 须为对象')
    budget = profile.get('budget', run.get('budget', {}))
    if not isinstance(budget, dict):
        raise ValueError('budget 须为对象')
    general_limit = _integer(budget.get('queries'), '常规查询预算')
    enrichment_limit = _integer(budget.get('enrichment_queries', general_limit), '补充查询预算')
    if enrichment_limit > general_limit:
        raise ValueError('补充预算不能超过常规预算')
    is_search = run.get('mode', 'search') == 'search'
    limits = {'general': general_limit, **{name: policy['extra_queries'][name]
              if policy is not None and is_search else 0 for name in _PLATFORMS}}
    # Follow-ups historically use their whole budget without reservation.
    default_reserved = 0 if policy is not None and is_search else general_limit
    reserved = {'general': _integer(run.get('reserved_queries', default_reserved), '常规预留')}
    platform_reserved = run.get('reserved_platform_queries', {}) if policy is not None else {}
    if not isinstance(platform_reserved, dict) or set(platform_reserved) - _PLATFORMS.keys():
        raise ValueError('reserved_platform_queries 字段无效')
    for name in _PLATFORMS:
        reserved[name] = _integer(platform_reserved.get(name, 0), name + ' 预留')
    for name in limits:
        if reserved[name] > limits[name]:
            raise ValueError(name + ' 预留超过预算')
    searches = run.get('searches', [])
    if not isinstance(searches, list):
        raise ValueError('searches 须为数组')
    used = {name: 0 for name in limits}
    enrichment = 0
    for event in searches:
        if not isinstance(event, dict):
            raise ValueError('查询记录须为对象')
        name = _bucket(event, policy)
        if name != 'general':
            if not is_search:
                raise ValueError('follow-up 不授予平台额外查询额度')
            _scope(event, name)
        used[name] += 1
        enrichment += event.get('phase') == 'enrichment'
    if enrichment > enrichment_limit:
        raise ValueError('补充查询额度不足')
    pools = {}
    for name in limits:
        if used[name] > reserved[name]:
            raise ValueError(name + ' 实际查询超过预留额度')
        pools[name] = {'limit': limits[name], 'reserved': reserved[name], 'used': used[name],
                       'remaining': limits[name] - used[name], 'available': reserved[name] - used[name]}
    return {'pools': pools, 'total': {key: sum(pool[key] for pool in pools.values())
                                    for key in ('limit', 'reserved', 'used', 'remaining', 'available')}}


def validate(run):
    """Validate policy, recorded allocations and caps without changing the run."""
    _snapshot(run)


def summary(run):
    """Return pools and totals; remaining is unused capacity, available reserved capacity."""
    return _snapshot(run)


def reserve(run, count, bucket='general'):
    """Reserve one pool atomically and return its updated summary."""
    if type(count) is not int or count <= 0:
        raise ValueError('预留 query 数必须大于零')
    if bucket not in ('general', *_PLATFORMS):
        raise ValueError('budget_bucket 无效')
    snapshot = _snapshot(run)
    pool = snapshot['pools'][bucket]
    if bucket != 'general' and 'platform_policy' not in run:
        raise ValueError('旧运行未配置平台额外池')
    amount = pool['reserved'] + count
    if amount > pool['limit']:
        raise ValueError(bucket + ' 预算不足；未修改运行')
    if bucket == 'general':
        run['reserved_queries'] = amount
    else:
        reservations = run.setdefault('reserved_platform_queries', {name: 0 for name in _PLATFORMS})
        reservations[bucket] = amount
    return summary(run)


def admit(run, event):
    """Check a prospective actual call; the caller handles event_id replay and append."""
    if not isinstance(event, dict):
        raise ValueError('调用记录必须为对象')
    snapshot = _snapshot(run)
    policy = _policy(run)
    name = _bucket(event, policy)
    phase = event.get('phase', 'enrichment' if run.get('mode') == 'enrich' else 'discovery')
    if phase not in ('discovery', 'enrichment'):
        raise ValueError('phase 无效')
    if name != 'general':
        if run.get('mode', 'search') != 'search':
            raise ValueError('follow-up 不授予平台额外查询额度')
        _scope({**event, 'phase': phase}, name)
    pool = snapshot['pools'][name]
    if pool['used'] >= pool['reserved']:
        raise ValueError(name + ' 查询额度不足；须先预留对应池')
    budget = run.get('profile', {}).get('budget', run.get('budget', {}))
    if phase == 'enrichment' and sum(e.get('phase') == 'enrichment' for e in run.get('searches', [])) >= budget.get('enrichment_queries', budget['queries']):
        raise ValueError('补充查询额度不足')
