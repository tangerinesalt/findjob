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

查询事件沿用 query/source/outcome/note；可选 phase、direction、new_jobs、new_fields、event_id。页面访问用 url/outcome/note，可选 event_id。event_id 用于中断恢复时避免重复补记同一调用；同词再次实际搜索是新调用，仍要计数。脚本只记录，不代替联网调用，也不能自动拦截工具。

status 输出预算、方向、最近查询、最近 notes 及结果位置，不打印全部岗位与证据。恢复时先读摘要，再读待处理岗位的相关材料；不要反复读完整报告或插件源码。新事实、冲突、下一步及时写入，脚本采用原子替换，避免写入一半损坏账本。

后续清单可用 `report_target.py inspect --task <task.json>` 只读条件与简表；指定 `--number 01 --field benefits --field work_time` 只看对应字段。省略 field 显示该岗位完整段落。出现冲突再扩读相关上下文，不需要每次输出整份清单。

search 在搜索前仍用 budget 预留；follow-up 的 prepare 可传 `--queries N` 设置本轮预算，未传沿用 enrich 12 / refresh 60。实际调用与预留分别记，不重置原任务；已执行但尚未落盘的调用从可用工具记录恢复。

## 搜索完成

render 可以多次生成草稿，不自动结束采集。最终报告的筛选、格式及来源抽查通过后记录完成状态与实际交付路径：

```text
python -X utf8 "<search-skill>/scripts/run_state.py" complete --file "<run.json>" --output "<最终报告.md>"
```

complete 检查报告格式及其与当前运行结果的对应关系，成功后 status 显示 complete 和输出路径。完成记录不代替网页事实核实；不要把草稿记成最终交付。job-enrich/job-refresh 仍用 report_target.py publish 完成任务，不用此命令，也不猜测旧报告与 run.json 的关联。
