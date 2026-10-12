# Findjob

适用于 Codex 和 Claude Code 的轻量岗位研究插件。根据求职条件建立画像、搜索岗位、补充资料并复核清单，结果以附来源的 Markdown 文件保存在当前工作空间。

仓库、市场及插件名统一为 `findjob`。

## 功能与入口

| 入口            | 功能                                           | Codex 调用       | Claude Code 调用         |
| --------------- | ---------------------------------------------- | ---------------- | ------------------------ |
| `job-profile` | 根据需求、简历或已有画像，生成可编辑的求职画像 | `$job-profile` | `/findjob:job-profile` |
| `job-search`  | 按条件搜索近期岗位，输出简表和逐岗详情         | `$job-search`  | `/findjob:job-search`  |
| `job-enrich`  | 补充已有清单的职责、福利、工时及企业信息       | `$job-enrich`  | `/findjob:job-enrich`  |
| `job-refresh` | 重新核实已有岗位的日期、状态和筛选条件         | `$job-refresh` | `/findjob:job-refresh` |

Codex 也可从技能选择器选择 `findjob` 对应入口。搜索可直接描述条件或指定画像文件；补充、复核可指定清单，未指定时优先使用对话最近完成的清单，再从当前工作空间选择。

搜索支持相关历史线索续接、公开同岗反查及去向记录，避免已知岗位在新任务中静默遗漏。可选额外平台额度用完后仍可用常规预算续查。版本变化见 [发布记录](docs/releases.md)，维护与验收见 [维护说明](docs/maintenance.md)。

当前源码为0.3.0候选版，已完成范围与发布待办见 [验收记录](docs/validation-0.3.0.md)。安装命令获取市场已发布版本，不代表安装此候选源码。

## 平台支持

当前发布以 Windows 为主要支持和验收平台。Linux、macOS 提供 Python 脚本 CI 兼容验证；尚不等同于这些系统上的 Codex / Claude Code 完整宿主验收。

## 运行依赖

- **Python 3.10+**：文件生成、画像解析、筛选及报告处理脚本仅依赖 Python 标准库，运行插件不需要安装第三方 Python 包。
- 请自行安装 Python 并配置 `PATH`，确保 Codex / Claude Code 的终端可以运行 `python --version`，且版本不低于 3.10。安装后必要时重启客户端；若系统仅提供 `python3` 或 `py -3`，可让代理使用对应命令。
- 使用支持插件的 Codex 或 Claude Code，并允许其在当前工作空间读写文件、运行 Python。通过 GitHub 安装还需 Git 和可访问该仓库的网络。
- 搜索、补充及复核依赖宿主可用的在线搜索与网页访问能力；插件不自带搜索服务或招聘网站账号。仅建立画像不要求联网。

## 安装

以下命令在终端执行，不是在聊天输入框中执行。

### Codex

```sh
codex plugin marketplace add tangerinesalt/findjob
codex plugin add findjob@findjob
```

### Claude Code

```sh
claude plugin marketplace add tangerinesalt/findjob
claude plugin install findjob@findjob
```

安装后开启新会话，在需要保存画像或岗位清单的项目中调用入口。例如：

```text
Codex：使用 $job-search 搜索大模型应用开发岗位，地点不限，排除猎头。
Claude Code：/findjob:job-search 搜索大模型应用开发岗位，地点不限，排除猎头。
```

更新已安装版本：

```sh
# Codex
codex plugin marketplace upgrade findjob
codex plugin add findjob@findjob

# Claude Code
claude plugin marketplace update findjob
claude plugin update findjob@findjob
```

更新后开启新会话。若提示不存在 `plugin` 命令，请先更新对应客户端。

## 功能边界

- 本插件用于借助代理工具快速搜集、筛选和整理公开岗位信息。对于仅发布于招聘平台的岗位，优先使用现有搜索和网页访问能力获取，不强制覆盖，也不要求通过爬虫抓取。
- 搜索基于公开或已授权访问的资料，受搜索索引、登录限制和页面可达性影响，不保证穷尽所有岗位或岗位仍可投递。
- 缺失或冲突信息会保留说明；福利、工时、社保人数及法律风险不作推测，员工规模不等于社保人数。
- 未指定的条件按入口默认值处理；岗位筛选依赖已取得的证据，脚本校验不能替代网页事实核验。
- 新搜索默认总计最多60次 query（补充最多12次包含其中），可以提前停止；所有来源遵循画像时间窗口。鱼泡/LinkedIn额外预算和LinkedIn日期例外均需明确选择，可独立设置，见 [平台策略](skills/job-search/references/platforms.md)。旧画像、运行和报告沿用其快照，不自动迁移。
- 不自动投递简历、联系招聘方、购买数据、绕过访问限制或建立定时任务。
- 文件保存在用户工作空间，不自动上传本仓库；处理内容仍遵循所用 Codex / Claude Code 服务的数据政策。


## 使用范围与数据

面向使用中文画像/报告的求职研究，支持多种职业、币种及年/月/日/小时薪资原始口径。固定字段仍为中文；不声称支持所有地区的薪酬制度。地点、远程、合同、学历等条件由代理按证据判断，脚本不自动理解JD。排序默认按岗位日期，偏好不自动评分。企业参保、风险信息按地区及用户需要补充。

画像和交付报告保存在当前工作空间根目录；原始证据摘要、任务快照和调用记录在 `.scratch/findjob/`。分享前检查报告正文、来源备注和本地链接；插件仓库忽略规则不保护其他项目中的用户文件，不会替用户修改Git配置。内部账本保存定位路径，报告中的历史对照来源仅显示文件名。

没有联网工具时只能创建画像或整理旧资料；登录墙、验证码和无法读取的正文会记录缺口，可从官网等公开同岗来源补证，不绕过访问限制。反馈问题时提供版本、Python/宿主版本和脱敏复现，勿附简历、凭证或真实个人画像。

## 许可证

Copyright (C) 2026 tangerinesalt

本项目以 [GNU GPL 第3版](LICENSE)（SPDX：`GPL-3.0-only`）发布，仅适用第3版。允许按许可证条款使用、修改及再分发；本项目不提供担保。完整授权条件以 LICENSE 为准。
