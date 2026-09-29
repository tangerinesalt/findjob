# 标准清单的局部更新

仅在补充/复核标准八列表格时读取。旧清单不需要 run.json；外部或大幅改写的格式可直接局部编辑 working.md，保留注释。

`report_target.py patch --task <task.json> --patch <changes.json>` 更新工作稿；`check --task <task.json>` 检查表格、详情、基本信息和数量。publish 也执行此检查。不会联网或判断新证据真假。脚本无法识别的非标准格式只给人工核对提示。

最小补丁示例（结构示例，非真实信息）：

```json
{
  "jobs": [{
    "number": "01",
    "details": {
      "benefits": {"text": "五险一金", "sources": ["https://example.org/jobs/1"], "scope": "本岗", "observed_at": "2026-09-28"},
      "work_time": {"text": "", "sources": [], "status": "blocked"}
    }
  }]
}
```

number 指当前简表编号；也可用 job_url 唯一定位。只写变更字段，未涉及的文字和用户注释保留；补丁不含整篇报告。

详情字段为 duties/requirements/benefits/work_time/overtime/insured/legal_risk。可选 status：verified（有来源事实）、not_disclosed（已查未披露）、unverified（未核实）、blocked（来源受阻）、conflict（来源冲突）。空字段默认未核实。scope 标本岗/公司口径/其他工种参考，entity/year 可标法人及年报年份；这些信息不由脚本猜测。不同来源的矛盾或互补信息可用 observations 数组保留各自 text/sources/scope/status，不嵌套。

未核实/受阻字段允许在 text 写缺口解释而不填来源，例如“未取得对应法人年度数据”；不能把无来源事实写成 verified。已查未披露应尽量附实际查看的页面，不能把未搜索写成已查。

基本信息变更使用 basic，可含 company/title/location/salary/education_experience/date/job_url；值为保留口径的文本（date 如 `2026-09-27（刷新）`）。这些字段会同步更新简表和详情。变更基本信息或筛选结论时同项提供 reason、sources URL 数组及 checked_at，形成变化记录。改变岗位日期还要有 `date_evidence: {"url":"...","note":"岗位自身日期依据"}`。

复核结论用 `state: kept/pending/excluded`；后两者移出主表并保留原详情。脚本不自行推断结论，也不把访问失败当下架。岗位编号保持不变以便追踪，不强制连续重排。已在待核实区的候选转入或大幅变化可由代理局部编辑后 check，无需转换旧报告。

refresh 可在补丁顶层提供 `window: {"as_of":"2026-09-28","published_since":"2026-07-28","refreshed_since":"2026-08-28","mode":"any"}`，日期由原画像及本轮基准日计算。enrich 禁止滚动窗口。脚本更新展示不代表全表已核实：复核范围与未处理项仍由执行代理准确说明。

同一工作稿的相对链接以原清单目录为基准，发布跨目录时脚本统一重定位。自定义格式、带复杂内嵌 HTML 的链接请抽查目标；不需要为此重写整份清单。
