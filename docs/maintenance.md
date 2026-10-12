# 维护与验收

四个技能入口分别处理画像、发现岗位、补详和复核。共享脚本只负责本地结构、筛选、记账及报告，不执行联网和投递。招聘事实、语义匹配和查询选择由宿主代理负责；验证通过不等于网页内容真实或市场覆盖充分。

## 本地检查

运行时仅需Python标准库；开发验证使用 `requirements-dev.txt` 中的包。

```sh
python -m pip install -r requirements-dev.txt
python -X utf8 -m unittest discover -s tests -q
python -X utf8 scripts/check_release.py
```

测试全部使用虚构岗位，不能当作真实招聘结果。新增行为应验证可观察结果、条件原意、原文件不变及原子拒绝，不只匹配文案。四入口结构另由宿主skill验证器检查。

## 兼容范围

最低Python3.10。前期以Windows为主要发布和宿主验收平台；Linux、macOS保持Python脚本兼容验证。Windows、Linux、macOS上的3.10与3.13六组CI已实际通过，运行链接和宿主测试边界见 [发布验收记录](validation-0.3.0.md)。Codex和Claude Code安装后均需开启新会话，已加载的旧技能不会自动替换。

旧schema_version=1画像和账本继续读取；可选字段缺省维持旧逻辑。旧platform_policy.version=1不自动升级；新配置可用version=2。新任务标记relative_date_mode=profile启用普通窗口相对日期判断；旧任务不迁移。历史报告补详另存，只有核心变化/窗口更新时标注原搜索统计为历史。

## 发布与回退

两端manifest版本必须一致，先执行全部测试、包内链接及画像预设检查，完成独立场景验证，再发布相同版本的Git标签。使用 `git archive <版本标签>` 生成可复现源码包；安装市场仍跟踪main，不把尚未存在的标签写进市场配置。

本项目使用 [GPL-3.0-only](../LICENSE)。对外发布前运行 `python -X utf8 scripts/check_release.py --release`，记录实际通过的Python/系统/宿主版本；不能把尚未完成的验收写成通过。需要回退时检出既有标签或明确提交，并使用对应宿主的本地插件安装方式；保留用户工作空间中的画像与任务，不回滚或覆盖其数据。

贡献请包含问题、修改后的行为及验证；问题反馈使用仓库Issues，只附脱敏最小复现。报告潜在凭证或个人信息泄露时勿公开具体数据。发布包不携带开发者本地画像、抓取结果或历史会话授权。
