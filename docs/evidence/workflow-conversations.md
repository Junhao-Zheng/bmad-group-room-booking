# 关键工作流输入与输出索引

这是可复核的关键交互摘录，不是完整聊天导出，也不含模型内部推理。原始人类输入另见user-inputs.md。独立上下文均为AI代理，不能记为组员或教师。

| 阶段 | 输入与执行方式 | 输出/评审证据 |
|---|---|---|
| 分析 | 用户确认课题组预约题目并授权拟定规则；使用bmad-product-brief | planning-artifacts/product-brief.md及briefs工作目录memlog、brief-review-2026-11-12.md |
| PRD | 独立代理读取简述/课程范围，bmad-prd headless；另一个上下文按rubric核验 | planning-artifacts/PRD.md；prds工作目录review-rubric/review-resolution/memlog |
| 架构 | 独立代理读取final PRD/UX，bmad-architecture；三个独立镜头：rubric、技术现实、对抗兼容性 | architecture.md、project-context.md；architecture工作目录reviews与review-resolution |
| 史诗和故事 | 四步执行：完整提取22FR/4NFR/10UX→3史诗→12故事→覆盖/依赖验证 | epics.md、docs/evidence/epics-validation.md |
| 冲刺 | bmad-sprint-planning就绪判断；使用官方sprint_plan.py生成状态，缺失依赖通过uv内联环境解决 | implementation-readiness.md、sprint-status.yaml、docs/sprint-plan.md |
| Build 1.1 | 先独立编译Epic1上下文；在ready-for-dev基线之后开启无历史上下文的实现代理 | 1-1-account-access.md、epic-1-context.md、story-events.jsonl；实现评审待实际完成后补 |

## Build实现标准提示（1.1真实使用）

> Read [本故事spec绝对路径] fully and implement it — the spec is the sole source of truth. Load every file listed in its frontmatter context: before you start.
>
> When done, report what you changed, how you verified it, and anything left incomplete or risky.

提示中的路径指向仓库`_bmad-output/implementation-artifacts/1-1-account-access.md`；spec包含明确矩阵、代码地图、禁止远端操作、验证命令和完整context文件列表。此处用仓库路径替代机器私有前缀以便携带，未声称是逐字完整导出。
