# 固定画像格式与命令

一份 Markdown 使用一张“属性 / 值”表，完整示例见 [example.md](example.md)。只保留这一份可编辑配置，不要求用户维护JSON或YAML。程序按字段名读取，行顺序可调整；标题和表外说明不参与筛选。保留全部字段，不设置的列表和背景值留空。用户删除/拼错字段时给出具体提示，不静默放宽条件。

多值使用中文分号“；”分隔，例如 `上海；苏州`；布尔值用“是/否”；时间关系用“或/且”。数值字段不带K、元等单位。特殊字符可用HTML实体，例如值中的竖线 `&#124;`、条目内分号 `&#65307;`；脚本生成时自动转义，用户正常中文编辑无需额外处理。

岗位名称与检索关键词分别保存；地点、排除地点、招聘类型、工作方式、排除关键词和其他硬性条件交由搜索代理结合证据判断并写入 `profile_match`，不做全文字符串误杀。学历、经验与技能背景只用于理解适配性。排序偏好不用于自动剔除。

发布时间、刷新时间保存自然月窗口，搜索运行时按检索日计算；0个月表示当天。默认“或”满足任一窗口；“且”需要分别核实明确发布日期和刷新日期，类型不明的岗位时间不能证明两者都满足。薪资保存统一月薪门槛；用户给年薪时明确说明等额换算口径后再存，不推测发薪月数。最低工资不小于指招聘区间下限，最高工资不小于指招聘区间上限，均包含边界。

剔除猎头、剔除雇主不明确是独立选项。允许主体不明确时保留相应说明；若仍排除猎头且招聘者类型无法判断，则只能记为待核实，不能认定为企业直招。

## 命令

`<profile-skill>` 为本job-profile目录，`<search-skill>` 为同插件job-search目录。路径均加引号；日期换成实际检索日。脚本不会解析简历或代替对话判断，这些由宿主代理完成。

```text
python -X utf8 "<profile-skill>/scripts/job_profile.py" draft --role "Unity开发" --role "VR开发" --name "上海Unity非游戏开发" --output ".scratch/fingjob/profile-draft.json"
```

草稿使用现有搜索画像JSON结构及可选扩展字段；生成后根据对话修改实际条件，不能只改名称。内部草稿同名时不覆盖，可另起临时文件名。用户确认属性（或已授权推荐默认值）后：

```text
python -X utf8 "<profile-skill>/scripts/job_profile.py" create --input ".scratch/fingjob/profile-draft.json" --workspace "<当前工作空间绝对路径>"
python -X utf8 "<profile-skill>/scripts/job_profile.py" check --input "<工作空间>/上海Unity非游戏开发.md"
python -X utf8 "<search-skill>/scripts/job_report.py" init --profile "<工作空间>/上海Unity非游戏开发.md" --as-of 2026-09-23 --run ".scratch/fingjob/<运行编号>/run.json"
```

create输出实际文件路径；同名时自动编号，不根据文件标题判断是否覆盖。未传workspace时用进程当前目录，因此宿主应显式传用户工作空间。读取兼容UTF-8 BOM，写入UTF-8。

现有JSON画像继续可用，新增字段为可选：`target_roles`、`excluded_keywords`、`excluded_locations`、`employment_types`、`work_arrangements`均为字符串数组；`background`为文本；`exclude_unclear_employers`为布尔值；`freshness.mode`为`any/all`。旧画像缺少这些字段时保持原先行为：排除匿名主体，时间任一条件满足。查询预算延用现有设置，不引入新搜索阶段。
