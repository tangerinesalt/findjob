# 已知线索续接与收尾

新搜索init创建`coverage.version=1`及`leads=[]`，只记录去向，不参与合格筛选。旧账本缺这些字段时沿用原流程，不自动迁移；enrich/refresh不使用搜索线索账本。

## 开始与来源选择

盘点用户点名、当前对话、最近相关正式清单和同一任务的联网验证；有价值的探索线索也可登记。不全盘扫描无关历史，不把旧事实当作今日事实。优先复核已知直达URL，同时保留新机会发现。

有对应旧run时导入已纳入岗位身份和来源，不复制旧薪资、日期、职责、判定或调用，不消耗query：

```text
python -X utf8 "<skill>/scripts/run_state.py" seed --file "<新run.json>" --source-run "<相关旧run.json>"
```

需要该来源待核实线索时加`--include-pending`。同URL同公司同岗位合并来源，共享公告的不同岗位分开；跨URL同岗须凭证据关联。重新seed不重置处理状态。只有Markdown或对话线索时手工登记；seed不自动发现相关来源。

## 小批记录

通过`run_state.py batch`的`leads`数组按id更新，未提供字段保留；origins和attempt_ids追加去重。已登记身份不可原地替换。同岗多来源更新相同id及origins，不因第二份报告另建重复线索。

```json
{
  "batch_id": "leads-first",
  "coverage": {"sources": [{"path": "相关清单.md", "note": "取相关已纳入岗位作复核线索"}]},
  "leads": [{
    "id": "known-job-1", "company": "示例公司", "title": "示例岗位",
    "url": "https://example.org/jobs/1", "important": true, "state": "queued",
    "origins": [{"source": "相关清单.md", "observed_at": "2026-10-09", "previous_state": "kept"}]
  }]
}
```

这是结构示例，不能导入真实结果。previous_state取kept/pending/excluded/new/user/unknown，observed_at如有保留原观测日。identity_key可选，用于区分同URL同标题但明确不同的机会。没有相关历史来源时在coverage.source_note说明盘点范围和情况，不能凭“全查过了”代替来源记录。

| state | 含义与必要字段 |
|---|---|
| queued | 尚未处理，important默认true |
| reviewed | 已处理并保存岗位事实；须有job_id和本轮attempt_ids，岗位仍可待核实或排除 |
| merged | 合并到job_id；须有attempt_ids及match_note说明同岗依据 |
| deferred | 暂缓；须有具体reason，可保留gap、next_step和已有调用 |

attempt_ids引用本轮searches/accesses的event_id。reviewed指向不同URL时也须match_note。reason/gap/next_step保留短说明；预算不足未尝试也如实记录。暂缓不等于不合格。新发现岗位已有jobs记录时无需重复建线索；尚未形成岗位事实的重要URL应登记。

## 全局收尾

检查分支交回线索、其他路线及普通预算。额外池或分支额度用完不代表全局结束，仍有高价值机会时按增量续配general。没有值得继续的路线、公开渠道受限或预算耗尽可结束，不要求用满预算或达到固定岗位数。

在最后一批用coverage.stop_reason记录主要路线、未完成部分和停止理由。新增调用、岗位或线索更新会清空旧停止理由，需重新收尾；可在最后事实同一批填写新理由。coverage.sources追加去重，source_note/stop_reason显式更新。

render输出带搜索基准日的去向表；后续enrich/refresh保留此区块作为搜索历史，当前状态以更新后的岗位主表与复核记录为准。complete检查重要线索是否仍queued、job/event关联、来源与停止理由，并核对报告覆盖区块。暂缓理由完整时允许交付，旧任务不新增必填项。

检查只能验证已登记关系，无法发现从未登记的线索，也不证明人填的匹配、尝试及停止理由真实。仍需对照相关清单抽查，分别报告规则验证、历史线索处理覆盖及联网增量。线索不计合格数量，同批事实判定一致不证明未漏检。
