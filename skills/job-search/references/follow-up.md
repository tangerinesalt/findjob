# 既有清单的选择、工作稿与交付

供 job-enrich / job-refresh 共用。轻量处理已有报告，宿主负责联网核实及编辑；脚本只定位文件、保存快照和另存结果。无需先转换整份报告为 JSON，也不以缺少旧 run.json 为阻塞条件。

## 选择目标

优先级：用户明确指定的清单名/路径 > 当前对话最近一次已经完成并交付的岗位清单 > 当前工作空间根目录中岗位清单的最后修改时间。对话中后续完成的补充/复核清单也可以继续使用。不能将只是提及的旧文件、正在生成的工作稿当作最新完成清单。

先从宿主取得当前工作目录。脚本不能读取对话：有上下文时由代理传 `--context-report`，用户指定则传 `--report`。名称可省略 `.md`。上下文文件已失效时回退目录扫描，并告知；明确指定文件失效时不悄悄改用其他文件。

自动扫描只查根目录实际 Markdown 岗位表，排除画像、指南、比较分析及 `.scratch` 工作稿；同修改时间按文件名稳定排序。先简短告知选中的文件及原因，无需再次确认。若用户指定子目录文件，直接使用指定路径。脚本按标题和表头识别新旧清单；非标准格式未识别时，代理可直接阅读确认是岗位清单后手工另存工作稿，不要求用户改格式。无清单且无可用上下文时才请用户指定，不能自动运行全新搜索。

以下 `<search-skill>` 指已安装插件中 `skills/job-search`，不是当前工作目录。日期按用户时区当天替换。

```text
python -X utf8 "<search-skill>/scripts/report_target.py" resolve --workspace "<当前工作目录>"
python -X utf8 "<search-skill>/scripts/report_target.py" prepare --mode enrich --as-of YYYY-MM-DD --workspace "<当前工作目录>" --report "清单名称.md"
python -X utf8 "<search-skill>/scripts/report_target.py" prepare --mode refresh --as-of YYYY-MM-DD --workspace "<当前工作目录>" --context-report "对话刚完成的清单.md"
```

未指定且无上下文时省略两个 report 参数。prepare 返回 `.scratch/fingjob/<任务>/task.json`、`source.md` 快照和 `working.md`。原文完整复制，手工补充不会因重新生成而丢失。后续只编辑 working.md；继续中断任务时读取该 task.json 和工作稿，保持原任务日期和剩余预算，不再 prepare。

## 证据与进度

默认 query 上限：enrich 12 次，refresh 60 次；均为建议的本轮总预算，用户本次要求优先，不必花完。打开已有链接不计 query。执行前在 task.json 的 notes 简记本批计划，执行后逐条加入 searches：`query/source/outcome/note`，区分 success / no_matches / blocked。已有运行的预算不重置冒充原任务继续；这两个入口各自是新的补充/复核任务。单岗约 3 分钟作为软参考，失败后换一次公开渠道仍无结果就标缺口并继续。每批不超过 5 岗保存工作稿和下一步。无网页能力时可整理历史资料，但明确未进行在线补充/复核。

prepare 可传 `--queries N` 直接采用用户本轮预算。页面访问另记 accesses，便于比较实际成本。续接可先用 [进度摘要](progress.md) 的 status 命令，再读相关岗位；不必重读整份历史。

查询直接传给宿主工具。站点限定用半角 `site:域名` 或工具 domains 参数。中文文件用 UTF-8；PowerShell 读取指定 `-Encoding UTF8`，不要通过默认编码管道向 Python 传中文代码。

如上下文已有明确关联的 run.json，可复制到本任务目录作辅助，再按 [data.md](data.md) 和 [evidence.md](evidence.md) 使用 check；不要只凭 run.json 修改时间推断与清单的关联。清单的手工新增字段仍要保留。刷新后使用新 as_of，旧证据只作历史线索；不能将旧 check 的 kept 直接视为本轮已核实。无需强制重建缺失的 run.json，代理也可按同一规则逐岗检查并更新 Markdown。

## 交付

标准八列表格优先使用[局部更新](updates.md)的 patch/check 命令，仅提交本次变更字段；旧报告不需重建 JSON。非标准清单仍可直接编辑工作稿。publish 自动检查标准表格、主表与详情基本信息及数量；不能识别的格式提示人工核对，不强制转换。

保留两部分结构：公司、岗位、地点、薪资、学历/经验、最新可靠岗位日期、招聘链接简表；逐岗详情含职责、要求、福利、工作时间、加班、社保人数、法律风险、讨论及对应来源。未披露项保持未知。补充/复核日期另列，不改写成岗位日期。更新简表与详情时保持一致，保留用户注释；矛盾信息标出来源与时间，不静默覆盖。

完成事实核对、条目数量与来源链接抽查后：

```text
python -X utf8 "<search-skill>/scripts/report_target.py" publish --task "<任务>/task.json" --summary "本轮补充或复核的数量、变化及未核实限制"
```

默认输出当前工作空间的 `<原名>_补充_YYYYMMDD.md` 或 `<原名>_复核_YYYYMMDD.md`，同名追加 `_2` 等，不覆盖原文件。工作稿在交付前不会进入自动选择候选。publish 只检查基本 Markdown 结构，不能证明网络访问成功或事实真实，摘要和正文必须准确披露实际完成程度。用户明确要求原地修改时按授权编辑原文件并留快照，无需额外确认。

最终给出新清单链接、处理/变化数量和缺口。保留 task.json 供续接，不创建常驻代理、定时器或自动投递任务。
