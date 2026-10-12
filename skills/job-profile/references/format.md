# 固定画像格式与命令

一份 Markdown 使用一张“属性 / 值”表，完整示例见 [example.md](example.md)。只保留这一份可编辑配置，不要求用户维护JSON或YAML。程序按字段名读取，行顺序可调整；标题和表外说明不参与筛选。保留全部字段，不设置的列表和背景值留空。用户删除/拼错字段时给出具体提示，不静默放宽条件。

多值使用中文分号“；”分隔，例如 `上海；苏州`；布尔值用“是/否”；时间关系用“或/且”。数值字段不带K、元等单位。特殊字符可用HTML实体，例如值中的竖线 `&#124;`、条目内分号 `&#65307;`；脚本生成时自动转义，用户正常中文编辑无需额外处理。

岗位名称与检索关键词分别保存；地点、排除地点、招聘类型、工作方式、排除关键词和其他硬性条件交由搜索代理结合证据判断并写入 `profile_match`，不做全文字符串误杀。学历、经验与技能背景只用于理解适配性。排序偏好不用于自动剔除。

发布时间、刷新时间保存自然月窗口，搜索运行时按检索日计算；0个月表示当天。默认“或”满足任一窗口；“且”需要分别核实明确发布日期和刷新日期，类型不明的岗位时间不能证明两者都满足。新明确薪资需求保留原文和原始计薪周期，使用下述 salary.requirement，不先折算成月薪。旧月薪字段继续兼容。最低工资不小于指招聘区间下限，最高工资不小于指招聘区间上限，均包含边界。

剔除猎头、剔除雇主不明确是独立选项。允许主体不明确时保留相应说明；若仍排除猎头且招聘者类型无法判断，则只能记为待核实，不能认定为企业直招。

## 命令

`<profile-skill>` 为本job-profile目录，`<search-skill>` 为同插件job-search目录。路径均加引号；日期换成实际检索日。脚本不会解析简历或代替对话判断，这些由宿主代理完成。

```text
python -X utf8 "<profile-skill>/scripts/job_profile.py" draft --role "财务分析" --name "上海财务分析" --output ".scratch/findjob/profile-draft.json"
```

草稿使用现有搜索画像JSON结构及可选扩展字段；生成后根据对话修改实际条件，不能只改名称。内部草稿同名时不覆盖，可另起临时文件名。用户确认属性（或已授权推荐默认值）后：

```text
python -X utf8 "<profile-skill>/scripts/job_profile.py" create --input ".scratch/findjob/profile-draft.json" --workspace "<当前工作空间绝对路径>"
python -X utf8 "<profile-skill>/scripts/job_profile.py" check --input "<工作空间>/上海财务分析.md"
python -X utf8 "<search-skill>/scripts/job_report.py" init --profile "<工作空间>/上海财务分析.md" --as-of 2026-09-23 --run ".scratch/findjob/<运行编号>/run.json"
```

create输出实际文件路径；同名时自动编号，不根据文件标题判断是否覆盖。未传workspace时用进程当前目录，因此宿主应显式传用户工作空间。读取兼容UTF-8 BOM，写入UTF-8。

现有JSON画像继续可用，新增字段为可选：`target_roles`、`excluded_keywords`、`excluded_locations`、`employment_types`、`work_arrangements`均为字符串数组；`background`为文本；`exclude_unclear_employers`为布尔值；`freshness.mode`为`any/all`。旧画像缺少这些字段时保持原先行为：排除匿名主体，时间任一条件满足。查询预算延用现有设置，不引入新搜索阶段。

## 薪资原始口径

明确薪资条件时在 salary 中增加 requirement，并把旧 min_lower_monthly/min_upper_monthly 置0，避免两套条件冲突。例如：

```json
{"currency":"CAD","min_lower_monthly":0,"min_upper_monthly":0,"allow_unknown":false,"requirement":{"period":"year","min_lower":60000,"min_upper":84000,"basis":"base","original_text":"固定年薪区间下限至少6万加元，上限至少8.4万加元"}}
```

period 为 month/year/day/hour；basis 为 base（固定薪资）或 total（总包）。金额使用该币种基本单位。生成器会追加“薪资比较周期、薪资下限门槛、薪资上限门槛、薪资比较口径、薪资原始需求”五行；这五行必须一起出现，旧画像可全部缺省。原文不影响数值判定，用于审阅与恢复用户意图。

相同年薪总额不受12/13次发放影响。同口径月薪与年薪之间仅按明确的固定发薪次数换算；年终绩效等不确定奖金不计入固定发薪次数。日薪/时薪仅与相同周期比较，跨币种、总包与固定工资、未知周期均不擅自转换。无法比较且设有门槛时待核实。旧画像的月薪等额比较维持历史行为；新任务需变更时通过本次覆盖明确采用原始口径，不改旧快照。
