# Fingjob

适用于 Codex 和 Claude Code 的轻量岗位研究插件。根据求职条件建立画像、搜索岗位、补充资料并复核清单，结果以附来源的 Markdown 文件保存在当前工作空间。

仓库及市场名为 `findjob`，插件名为 `fingjob`。

## 功能与入口

| 入口 | 功能 | Codex 调用 | Claude Code 调用 |
|---|---|---|---|
| `job-profile` | 根据需求、简历或已有画像，生成可编辑的求职画像 | `$job-profile` | `/fingjob:job-profile` |
| `job-search` | 按条件搜索近期岗位，输出简表和逐岗详情 | `$job-search` | `/fingjob:job-search` |
| `job-enrich` | 补充已有清单的职责、福利、工时及企业信息 | `$job-enrich` | `/fingjob:job-enrich` |
| `job-refresh` | 重新核实已有岗位的日期、状态和筛选条件 | `$job-refresh` | `/fingjob:job-refresh` |

Codex 也可从技能选择器选择 `fingjob` 对应入口。搜索可直接描述条件或指定画像文件；补充、复核可指定清单，未指定时优先使用对话最近完成的清单，再从当前工作空间选择。

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
codex plugin add fingjob@findjob
```

### Claude Code

```sh
claude plugin marketplace add tangerinesalt/findjob
claude plugin install fingjob@findjob
```

安装后开启新会话，在需要保存画像或岗位清单的项目中调用入口。例如：

```text
Codex：使用 $job-search 搜索大模型应用开发岗位，地点不限，排除猎头。
Claude Code：/fingjob:job-search 搜索大模型应用开发岗位，地点不限，排除猎头。
```

更新已安装版本：

```sh
# Codex
codex plugin marketplace upgrade findjob
codex plugin add fingjob@findjob

# Claude Code
claude plugin marketplace update findjob
claude plugin update fingjob@findjob
```

更新后开启新会话。若提示不存在 `plugin` 命令，请先更新对应客户端。

## 功能边界

- 搜索基于公开或已授权访问的资料，受搜索索引、登录限制和页面可达性影响，不保证穷尽所有岗位或岗位仍可投递。
- 缺失或冲突信息会保留说明；福利、工时、社保人数及法律风险不作推测，员工规模不等于社保人数。
- 未指定的条件按入口默认值处理；岗位筛选依赖已取得的证据，脚本校验不能替代网页事实核验。
- 不自动投递简历、联系招聘方、购买数据、绕过访问限制或建立定时任务。
- 文件保存在用户工作空间，不自动上传本仓库；处理内容仍遵循所用 Codex / Claude Code 服务的数据政策。
