# 小批保存与续接

新任务使用 `.scratch/findjob/`。旧版 `.scratch/fingjob/` 中的账本、task.json 和工作稿仍按原路径读取，不因插件更名重新采集或搬动已有任务。

优先用 batch 一并保存小批事实与日志，避免为每次任务另写保存脚本；仍可直接编辑现有 run.json/task.json。

```text
python -X utf8 "<search-skill>/scripts/run_state.py" status --file "<run.json或task.json>"
python -X utf8 "<search-skill>/scripts/run_state.py" batch --file "<账本>" --batch "<本批JSON>"
python -X utf8 "<search-skill>/scripts/run_state.py" record --file "<账本>" --event "<单条查询JSON>"
python -X utf8 "<search-skill>/scripts/run_state.py" record --file "<账本>" --event "<单条页面访问JSON>" --page
```

本批 JSON 可包含 `batch_id` 及 `jobs/searches/accesses/notes`；数组沿用现有岗位、调用和短说明格式。jobs 中同 id 的记录更新已提供字段，保留未提供字段，嵌套对象递归合并；显式提供的数组整体替换，不自动追加。相同 batch_id 且内容相同的重试不重复写入；同 ID 不同内容会拒绝，新的实际调用或修正批次使用新 ID。search 的 run.json 可保存 jobs；follow-up 的 task.json 仅保存 searches/accesses/notes，岗位修改仍以 working.md/patch 为准，不重建整份 JSON。

查询事件沿用 query/source/outcome/note；记录 budget_bucket（省略为 general），可选 phase、domains、direction、new_jobs、new_fields、event_id。两平台额外池的事件必须满足 [平台策略](platforms.md) 的域名和 discovery 限制。页面访问用 url/outcome/note，可选 event_id。event_id 用于中断恢复时避免重复补记同一调用；同词再次实际搜索是新调用，失败/无匹配也计数。脚本只记录，不代替联网调用，也不能自动拦截工具。

status 输出预算、方向、最近查询、最近 notes 及结果位置，不打印全部岗位与证据。启用平台策略时分别显示各池与合计的 limit/reserved/used/remaining/available；remaining 是上限减实际，available 是已预留减实际，均不等于新增调用记录。恢复时先读摘要，再读待处理岗位的相关材料；保留原策略与各池计数，旧运行不自动加额。新事实、冲突、下一步及时写入，脚本采用原子替换，避免写入一半损坏账本。

后续清单可用 `report_target.py inspect --task <task.json>` 只读条件与简表；指定 `--number 01 --field benefits --field work_time` 只看对应字段。省略 field 显示该岗位完整段落。出现冲突再扩读相关上下文，不需要每次输出整份清单。

search 在搜索前仍用 budget 按池预留；follow-up 的 prepare 可传 `--queries N` 设置本轮预算，未传沿用 enrich 12 / refresh 60。follow-up 只继承已交付报告的日期策略，两平台额外发现池始终为 0，不给 enrich/refresh 加额。实际调用与预留分别记，不重置原任务；已执行但尚未落盘的调用从可用工具记录恢复。

## 搜索完成

新搜索按 [coverage.md](coverage.md) 续接相关线索。batch另接受leads数组与coverage更新；status显示线索状态和未处理的重要ID。它们不向旧任务自动迁移。全局收尾应审视其他路线和剩余额度，并记录停止理由；分支结束与格式检查通过不代表覆盖已核实。

render 可以多次生成草稿，不自动结束采集。最终报告的筛选、格式及来源抽查通过后记录完成状态与实际交付路径：

```text
python -X utf8 "<search-skill>/scripts/run_state.py" complete --file "<run.json>" --output "<最终报告.md>"
```

complete 检查报告格式及其与当前运行结果的对应关系，成功后 status 显示 complete 和输出路径。完成记录不代替网页事实核实；不要把草稿记成最终交付。job-enrich/job-refresh 仍用 report_target.py publish 完成任务，不用此命令，也不猜测旧报告与 run.json 的关联。

event_id 在同一任务的 searches/accesses 中共享命名空间。同ID同规范化内容可幂等重放；同ID异内容或跨类型复用报错，整批原子拒绝。重复实际查询应使用新ID；不可改写已有事件以释放预算。
