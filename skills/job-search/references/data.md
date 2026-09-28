# 数据和脚本用法

Python 3.10+，仅标准库。以下 `<skill>` 指本 SKILL.md 所在目录，路径含空格时加引号。

```text
python -X utf8 "<skill>/scripts/job_report.py" init --profile "<skill>/references/unity-non-game.json" --as-of 2026-09-21 --run ".scratch/fingjob/20260921-01/run.json"
python -X utf8 "<skill>/scripts/job_report.py" budget --run ".scratch/fingjob/20260921-01/run.json" --count 4
python -X utf8 "<skill>/scripts/job_report.py" check --run ".scratch/fingjob/20260921-01/run.json"
python -X utf8 "<skill>/scripts/job_report.py" render --run ".scratch/fingjob/20260921-01/run.json" --output "岗位报告_20260921.md"
```

日期是示例，执行时替换。init 不覆盖已有运行；继续时读取旧文件。render 默认不覆盖已有报告，要更新同一报告时显式加 `--replace`。画像支持 UTF-8 Markdown 或 JSON，运行仍为 UTF-8 JSON，可通过文件编辑工具更新；仅主代理写 run.json。`budget` 必须在搜索前预留，失败搜索也记入实际日志；并行分支总额度先预留，子代理不用此命令。账本不是对搜索工具的强制拦截器。

## 中文读写

优先用 `apply_patch` 等文件编辑工具保存中文 JSON 或临时 `.py` 文件，再用 `python -X utf8 "脚本路径.py"` 执行。Python 读文件指定 `encoding="utf-8-sig"`（兼容 BOM），写文件指定 `encoding="utf-8"`，JSON 用 `ensure_ascii=False`；现有 `job_report.py` 已采用这些设置。PowerShell 查看文件用 `Get-Content -Encoding UTF8 -LiteralPath "文件路径"`。

避免将含中文的 here-string/脚本通过默认 PowerShell 管道送入 `python -`。`-X utf8` 只设置 Python，不能修复管道发送前已被替换为 `?` 的字符。若发现乱码，从原始证据恢复受影响字段即可，不必重新采集整批岗位；仅将已经损坏的文本另存为 UTF-8 不会还原中文。

## 画像 v1

使用 unity-non-game.json 作为格式示例；字段必须齐全。keywords/locations/preference 是给模型理解的字符串数组；locations 空表示不限。额外硬条件写 `hard_requirements` 字符串数组，模型用 `profile_match` 和证据判断。脚本不靠简单字符串匹配推断学历或行业。所有未知顶层字段会报错，避免拼错字段后静默失效。

init 可用 `--overrides <JSON文件>` 将本次条件递归覆盖选定画像；对象递归合并、数组整体替换。完整合并结果保存进运行，原画像不变。去掉薪资门槛用数值 0，扩大相邻方向用 include_adjacent=true。两个薪资门槛独立设置，允许仅设置其中一个。

`init --profile "画像名称.md"` 直接读取固定表格，格式及示例见 [job-profile 约定](../../job-profile/references/format.md)。手动改值后新运行读取新值；已建立的运行保留原条件快照，继续时不能静默改用新文件。

v1 可选扩展：`target_roles`、`excluded_keywords`、`excluded_locations`、`employment_types`、`work_arrangements` 均为字符串数组；`background` 为背景文本；`exclude_unclear_employers` 为布尔值，旧文件缺省为 true；`freshness.mode` 为 any/all，旧文件缺省为 any。模型读取所有硬条件并以 `profile_match` 和短证据记录匹配判断，脚本不执行词义匹配。背景及 preferences 不作为默认硬条件。

## 运行 v1

init 生成 `schema_version/as_of/profile/reserved_queries/searches/jobs/notes`。

`searches` 每项：`{"query":"实际检索词","source":"web/官网等","phase":"discovery","outcome":"success","note":"简短结果"}`。

- phase 为 discovery 或 enrichment；outcome 为 success、no_matches 或 blocked。
- no_matches 只指该查询未发现候选，不表示市场无岗位；blocked 说明验证码/网络/权限等原因。
- 每个搜索 query 一项，页面打开不计 query。实际日志数不得超过 reserved_queries；总预留不超过预算；enrichment 实际数不得超过补充预算。
- notes 为字符串数组，记录覆盖缺口、预算分配和中断后下一步。事实记录随批落盘；不要将完整网页、个人联系方式或简历复制进来。

## 岗位 v1

以下为**结构示例而非真实岗位**，不要加入真实报告。所有判断必须来自本轮证据。

```json
{
  "id": "source-job-id",
  "company": "明确雇主全名",
  "title": "岗位名",
  "location": "城市/区域",
  "education": "本科",
  "experience": "3年以上（如冲突写明）",
  "job_url": "https://example.com/jobs/123",
  "status": "unknown",
  "deadline": null,
  "relevance": "core",
  "games": "no",
  "recruiter": "employer",
  "profile_match": "yes",
  "evidence": {
    "relevance": {"url":"https://example.com/jobs/123","note":"职责明确使用Unity开发工业场景"},
    "games": {"url":"https://example.com/jobs/123","note":"工作对象为工业设备仿真"},
    "recruiter": {"url":"https://example.com/jobs/123","note":"企业官网实名职位"},
    "profile_match": {"url":"https://example.com/jobs/123","note":"符合城市和附加硬条件；学历标签与正文差异已记录"},
    "salary": {"url":"https://example.com/jobs/123","note":"该岗位月薪6000至10000元"}
  },
  "salary": {"text":"6–10K/月","currency":"CNY","period":"month","min":6000,"max":10000,"months":null},
  "dates": [{"value":"2026-09-20","kind":"refreshed","url":"https://example.com/jobs/123","note":"职位标题旁显示9月20日更新，本次确认年份"}],
  "details": {
    "duties": {"text":"工业场景与设备交互开发；接口联动。","sources":["https://example.com/jobs/123"]},
    "requirements": {"text":"C#、Unity、性能优化。","sources":["https://example.com/jobs/123"]},
    "benefits": {"text":"公司介绍列五险一金。","sources":["https://example.com/jobs/123"]}
  },
  "discussions": [],
  "notes": ["具体签约或驻场条件未披露"]
}
```

- status：open/unknown/closed；deadline 可省略或 null，日期为 YYYY-MM-DD。
- relevance：core/adjacent/unrelated/unknown；games：yes/no/unknown；recruiter：employer/headhunter/anonymous/unknown；profile_match：yes/no/unknown。
- dates.kind：published/refreshed/job_time/crawled。crawled 永远不证明招聘新鲜度；job_time 用刷新窗口。用来筛选的日期必须有短证据和有效网页 URL。截止日不是发布日期。
- salary.period：month/year/day/hour/unknown；currency 为原始币种。min/max 为元数值或 null，months 为明确的年发薪月数或 null。面议/未披露用 period=unknown，min=max=null，原文写在 text。已知任一数值必须提供 salary 证据。
- evidence 为上述判断依据。缺失不等于通过；筛选输出“待核实”。证据 note 用改写的短描述，不抄整段内容。
- details 允许 duties、requirements、benefits、work_time、overtime、insured、legal_risk；每项为 text 与 sources URL 列表。未取得就省略，脚本标未核实，不能填造假来源。
- 详情可选 status 区分 verified/not_disclosed/unverified/blocked/conflict；未采集默认未核实，不等同已查未披露。scope/entity/year/observed_at 记录适用范围、法人、年报年份及访问日；详细格式及后续更新见 [updates.md](updates.md)，仅需局部更新时读取。
- discussions 每项为 `{"text":"个人反馈摘要，未独立证实","url":"https://...","date":"2025-04-01或未披露","scope":"公司层面，非特定岗位"}`。
- notes 放冲突/局限；主要岗位身份、日期、薪资有冲突未解决时，将相应判断保持 unknown，或不提供未经确认的数值。
- 可选 `requisition_id`、`team` 保存已知招聘编号、团队，防止同公司同名同城不同机会误合并；`identity_key` 仅在已确认跨来源属于同一岗位时填写，不能凭岗位名猜测。
- `check` 先稳定合并重复记录的互补证据，再筛选；不会改写原始 jobs。核心值冲突列待核实，保留各来源，代理按实际证据解决后再更新原记录。输出默认按日期倒序，同日按公司/岗位/地点/链接稳定排序；画像偏好展示但不自动评分。

`check` 返回 kept/excluded/pending/duplicates 和 errors。结构错误返回非零退出码；被正常筛掉不是执行错误。`render` 只将 kept 写入简表和详情，末尾提供未纳入原因与来源访问情况。程序不能验证人写的 evidence 是否真实，仍需原页核实。

默认 check 不打印完整合并记录；需要定位冲突时加 `--full`。常规调用无需读取脚本源码。画像解析/校验与原子存储由插件根目录 scripts 共用，分发时保留完整插件结构，不单拷入口文件。
