# 课题组活动与会议室预约

软件工程管理课程项目。选题及使用对象已由用户确认，当前处于分析阶段，尚未实现应用。

本仓库按实际发生的工作保存 BMAD 产物和过程证据。实验 B 按用户转述的教师要求免做，实验 A 保留。人数和截止日期不作为当前阶段的阻塞条件。

## 当前材料

- [产品简述草案](_bmad-output/planning-artifacts/product-brief.md)：使用对象、问题假设、范围和验证目标。
- [补充规则](_bmad-output/planning-artifacts/briefs/brief-group-room-booking-2026-11-12/addendum.md)：11 项假设、边界案例和实验 A 准备要求。
- [人机决策日志](decision-log.md)：目前 3 条真实人工决定，尚无人工技术否决。
- [课程要求与状态](docs/course-scope.md)：逐项区分已做与待做。
- [下一会话交接](docs/next-session-prd.md)：在独立会话中执行 PRD 工作流的输入说明。
- [初始化证据](docs/evidence/setup-2026-11-12.md)与[用户输入摘录](docs/evidence/user-inputs.md)。

当前只完成分析草案。PRD、架构、故事、冲刺、实验 A 和应用实现尚未完成；M1 尚未评审。

## 环境

- BMAD Core 与 BMad Method：6.12.1，与讲义参考版本一致。
- 项目级技能：`.agents/skills/`，配置和共享脚本：`_bmad/`。
- 本机工具环境：Python 3.12.14、uv 0.13.7，位于未入库的 `.tools/`。
- 应用技术栈尚未决定，由后续架构阶段依据需求选择。

在本目录使用 BMAD 前，激活工具环境：

```bash
source .tools/bin/activate
uv --version
uv run --python .tools/bin/python _bmad/scripts/resolve_config.py --project-root .
```

其他机器需先安装 Python 3.11+，再在本目录重建工具环境：

```bash
python3 -m venv .tools
.tools/bin/python -m pip install uv==0.13.7
source .tools/bin/activate
```

BMAD 已随仓库保存，无需覆盖安装。若需要恢复项目级安装，使用以下固定版本命令：

```bash
npx --yes bmad-method@6.12.1 install --directory . --modules bmm --tools codex --communication-language Chinese --document-output-language Chinese --user-name 课程项目组 --no-shims --yes
```

本机已验证配置与定制解析脚本可运行。应用尚未创建，因此当前没有应用启动步骤或功能测试结果。

## AI 使用声明

当前材料由 Codex 协助整理和起草，用户负责确认选题、使用对象及任务边界。精确模型版本未在当前可核验输出中提供，后续会话应保存界面中的模型信息，不能猜填。

AI 自主提出的业务规则按假设标注，不作为已完成访谈或用户已逐条批准的证据。人工决策与 AI 的编辑、检查记录分开保存。Git 提交以 Codex 标识记录本次 AI 操作，不代表组员贡献。

