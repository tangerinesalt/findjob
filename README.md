# Fingjob

轻量岗位研究插件。仓库名为 `findjob`，插件名保留 `fingjob`。

| 入口 | 用途 |
|---|---|
| `job-profile` | 根据需求、简历或已有画像生成可编辑 Markdown 求职画像 |
| `job-search` | 搜索并筛选近期岗位，输出附来源的简表和详情 |
| `job-enrich` | 补充既有清单的职责、福利、工时及企业信息 |
| `job-refresh` | 重新核实既有岗位日期、状态和筛选条件 |

## 当前版本

本轮优化覆盖：文件操作修复、互补证据合并与稳定排序、标准清单局部更新、按信息增量分配查询、简短进度/字段读取及共享画像与存储模块。

- 核心规则及事实来源保持可追溯；未知信息不猜测，单岗缺项不阻塞交付。
- 查询路由是软参考，不要求遍历全部方向或花完预算。
- 标准报告可按岗位/字段更新；非标准 Markdown 可直接局部编辑，不强制转换整份 JSON。
- 运行时仅需 Python 3.10+ 标准库。在线检索由宿主提供，脚本本身不联网。
- `.codex-plugin/`、`skills/`、`scripts/` 应整体分发；画像解析和原子存储位于根目录 `scripts/`。

详细阶段记录、测试结果及量化边界见 [优化记录](docs/optimization-20260928.md)。

## 开发验证

```text
python -m pip install -r requirements-dev.txt
python -B -X utf8 -m unittest discover -s tests -v
python -B -X utf8 tests/benchmark_efficiency.py
```

基准测试从本 Git 仓库的 `baseline-20260928` 导出旧版本，使用相同合成材料对照；输出保存于被忽略的 `.scratch/`。token 按 `o200k_base` 统计文本，不是宿主实际计费或端到端总消耗。真实网络测试产物、个人画像及岗位清单仅保留本地。

## 版本与回退

- `baseline-20260928`：优化前安装版本 `0.1.0+codex.20260924023528`，原始 23 个插件文件按字节保存，38 项原有测试通过；已知渲染、清单选择、链接、长文件名和重复信息问题保留在该标签。
- `optimized-20260929`：六阶段优化完成版本；每个优化阶段分别提交，详见优化记录。

优先在独立工作目录查看基线，保留当前开发现场：

```text
git worktree add --detach ../findjob-baseline baseline-20260928
```

若需要在当前开发分支恢复基线，先提交或另存未提交改动，再执行：

```text
git restore --source baseline-20260928 -- .codex-plugin skills scripts tests
```

这会恢复基线中的文件并移除这些目录内基线不存在的已跟踪文件，不影响本地岗位清单。仓库副本与安装缓存相互独立，Git 回退不会自动切换已安装插件；安装时需同步完整插件到个人市场源目录，再运行缓存版本更新和 `codex plugin add fingjob@personal`。安装新版本后在新对话中加载技能。
