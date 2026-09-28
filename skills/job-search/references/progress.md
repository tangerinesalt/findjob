# 小批保存与续接

直接编辑现有 run.json/task.json 即可；需要简短追加或恢复摘要时再用辅助脚本，不强制增加文件。

```text
python -X utf8 "<search-skill>/scripts/run_state.py" status --file "<run.json或task.json>"
python -X utf8 "<search-skill>/scripts/run_state.py" record --file "<账本>" --event "<单条查询JSON>"
python -X utf8 "<search-skill>/scripts/run_state.py" record --file "<账本>" --event "<单条页面访问JSON>" --page
```

查询事件沿用 query/source/outcome/note；可选 phase、direction、new_jobs、new_fields、event_id。页面访问用 url/outcome/note，可选 event_id。event_id 用于中断恢复时避免重复补记同一调用；同词再次实际搜索是新调用，仍要计数。脚本只记录，不代替联网调用，也不能自动拦截工具。

status 输出预算、方向、最近查询、最近 notes 及结果位置，不打印全部岗位与证据。恢复时先读摘要，再读待处理岗位的相关材料；不要反复读完整报告或插件源码。新事实、冲突、下一步及时写入，脚本采用原子替换，避免写入一半损坏账本。

search 在搜索前仍用 budget 预留；follow-up 的 prepare 可传 `--queries N` 设置本轮预算，未传沿用 enrich 12 / refresh 60。实际调用与预留分别记，不重置原任务；已执行但尚未落盘的调用从可用工具记录恢复。
