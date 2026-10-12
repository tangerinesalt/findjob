# 可选平台策略

默认没有额外平台额度或日期例外，所有来源遵循画像窗口。用户明确选用后，将策略JSON作为 `init --platform-policy "策略.json"` 传入；不因提到平台名称自动启用。用户要求全部来源共用总预算时不开额外池；严格日期要求下 age_months 设0。继续旧运行保留其策略，不迁移加额，不改长期画像。

v2把配置拆开：extra_queries各填0—5独立控制额度；linkedin_age_months=0关闭日期例外，正整数启用对应年龄窗口；linkedin_allow_unknown独立控制启用年龄例外后是否保留日期未知。v1历史语义保留：allow_unknown=false曾同时关闭年龄例外，不静默升级历史策略。

仅需要额外查询时，可用 `{"version":2,"extra_queries":{"yupao":5,"linkedin":5},"linkedin_age_months":0,"linkedin_allow_unknown":false}`。仅要日期例外则两额外额度填0。完整个人策略示例见 [可选平台预设](presets/platform-extra.json)，需明确选择；不叠加到用户规定的全来源总上限。

新任务的正文相对时间解析独立于例外：保存原文、观测日及可靠的kind，不伪造精确日期；按画像窗口比较整个可能日期区间。边界不确定待核实，mode=all仍须发布和刷新两种证据。旧任务没有relative_date_mode标记时保持原解析行为。

## 运行与预算

启用策略的新 run 保存：

```json
{
  "platform_policy": {
    "version": 2,
    "extra_queries": {"yupao": 5, "linkedin": 5},
    "linkedin_age_months": 3,
    "linkedin_allow_unknown": true
  },
  "reserved_platform_queries": {"yupao": 0, "linkedin": 0}
}
```

原 `profile.budget.queries` 默认仍为 60，`reserved_queries` 只计常规预留。下面仅是明确选用两平台各5次的例子，此时默认画像下三池实际合计不得超过 70；常规画像预算为其他值时，总上限为原预算加两平台额外额度，其他平台的常规上限不变。用户明确指定包含所有来源的总上限时，用 `--no-platform-policy` 保持该上限，不静默追加 10 次：

| bucket | 上限 | 可用范围 |
|---|---:|---|
| general（缺省） | 60 | 发现及补充；补充最多 12 且包含其中 |
| yupao | 5 | 仅 `yupao.com` 及其子域的 discovery |
| linkedin | 5 | 仅 `linkedin.com` 及其子域的 discovery |

搜索前用 `budget --bucket general/yupao/linkedin --count N` 预留对应池。两额外池不互相挪用，也不给其他平台、官网、跨来源核实或 enrichment 加额；这些查询使用 general。常规池可以查上述平台，但不能把已经执行的常规查询改记额外池来释放额度。连续低增量、访问受限或没有值得继续的线索时可提前停止，不必用满 5 次。

额外池查询必须由半角 `site:对应域名` 或宿主实际使用的 `domains` 限定到该平台；允许 `www`、`cn`、`m` 等真实子域。所有正向 site 与 domains 必须属于同一对应域，域名相似字符串、仅在关键词/链接中出现平台名或混入另一来源都不合格。domains 限定须把实际列表记入事件，不能事后补写未使用的限制。

没有显式 domains 时，额外池查询不用 OR 或 `|` 拼接，避免某个分支脱离平台限定；拆成单独查询或直接使用对应 domains。引号内的 site 文本不算域名限制。

每个实际 query 独立写 searches 事件的 `budget_bucket`（缺省 general）、phase、outcome 与短增量；失败和无匹配照计。各池实际不得超过预留与上限，记录全部真实调用，不能因超额或受阻省略。页面访问另记 accesses，不计 query；预留不是实际调用。event_id/batch_id 的同一调用重放不重复计数，同词再次调用仍是新事件。

额外额度不是平台总上限。例如鱼泡额外池已用5次且仍有相关机会，就从general预留下一小批鱼泡查询。分支无general额度时交回线索，由主代理决定续配；其他来源按原画像预算和增量继续，不因两个专用池完成而结束全局搜索。

## LinkedIn 岗位日期

以下以显式选择3个月年龄窗口为例；实际采用 platform_policy.linkedin_age_months。未启用年龄例外时，正文相对日期仍可按画像窗口判断，不采用本节的放宽规则。

仅直接 LinkedIn 岗位 URL，或已可靠确认同岗的 LinkedIn 来源记录启用；不能因雇主也有 LinkedIn 页面给其他平台岗位套用。其他平台仍严格按画像的发布/刷新自然月窗口（如 2/1 月），鱼泡没有日期例外。

正文相对时间记录在岗位的 `relative_dates` 数组中：

```json
{"text":"3天前","url":"https://cn.linkedin.com/jobs/view/123","note":"正文时间","observed_at":"2026-10-09"}
```

只记录该岗位正文原文和实际观测日，不用摘要、相关推荐、HR 活跃或工具 Crawled 代替，不编造绝对发布日期。observed_at 表示何日看到该信息，不证明页面实时刷新；缓存和招聘状态限制仍须说明。其他平台的 relative_dates 不提供日期例外。

- 正文相对年龄达到或超过 3 个月排除；不足 3 个月按日期例外保留。例如“3个月前”排除，“3天前”可保留；也可记录英文原文如“3 days ago”。
- 可靠绝对岗位日期按 3 自然月回溯比较，恰好到边界即排除；不能用日期未知或年轻相对值覆盖同岗可靠已知旧日期。未来日期、同次观测矛盾或可靠来源冲突保留待核实，不挑年轻值。
- 天/周等相对值结合 observed_at 与已流逝时间判断，能够确定在 3 自然月边界哪一侧时才作通过/排除，不固定按 90 天代替；边界区间不确定按日期未知处理。
- 只有 linkedin_allow_unknown=true 时日期确实未知才可保留，否则待核实；允许时标“日期未核实（按例外保留）”，招聘状态未知如实记录。这只放宽日期，不放宽 closed、截止、业务、薪资、雇主和其他画像硬条件；已关闭岗位仍排除，其他核心证据未知仍待核实。

## 报告与后续复核

报告保留可见“平台例外：...”说明及机器注释 `<!-- findjob:platform-policy {JSON} -->`，其中 JSON 是本次 platform_policy；每个按例外保留的 LinkedIn 岗位显示正文相对时间或日期未核实，不称已确认绝对发布时间。

`job-refresh` 从已交付报告继承策略，重新读取岗位正文相对时间并保存本轮 observed_at；历史原文与观测日保留。同一 URL 的新可靠观测优先，不能把旧观测日改成今天；无法重读时原相对时间必须加上已流逝时间重新判断，不能无限续期。跨来源或同次观测冲突不靠选择较新值解决；同岗可靠旧日期不能被访问失败改成未知放行。

`job-refresh` 与 `job-enrich` 只继承日期策略，不继承额外发现预算，两特殊池上限均为 0；默认仍各自为 60/12 次常规 query。旧报告没有策略记录时不自动启用。用户要求新发现岗位时另开 job-search，与既有清单复核分开记账。
