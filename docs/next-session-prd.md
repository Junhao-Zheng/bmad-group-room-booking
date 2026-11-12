# PRD 阶段输入

这是下一次独立工作流会话的交接说明，不代表 PRD 已经生成或需求评审已经通过。

项目目录：`/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking`。

在该目录的新会话中执行以下任务：

> 使用项目内已安装的 `bmad-prd` 技能，执行 Create，为软件工程管理课程项目“课题组活动与会议室预约”起草 PRD。
>
> 先读取 README.md、docs/course-scope.md、decision-log.md、_bmad-output/planning-artifacts/product-brief.md，以及 _bmad-output/planning-artifacts/briefs/brief-group-room-booking-2026-11-12/ 下的 addendum.md 和 .memlog.md。根据本地技能文件运行配置解析和必要的工作流步骤。
>
> 用户已经确认选题、服务对象为课题组，并授权其余业务规则由 AI 拟定。不要重复询问组员人数或截止日期；按已标注的假设继续，保留证据边界。没有真实访谈记录，不得编造。
>
> PRD 应为功能需求建立 FR 编号，为非功能需求建立 NFR 编号，覆盖完整使用路径、数据可见性、权限、预约冲突、停用冲突、容量维护、时间边界、重复提交、取消与历史记录。明确每个目标的测试条件、通过标准、错误处理及范围外内容。非功能目标至少包含可测的一致性与权限条件；性能目标需写清负载、样本、统计口径和环境记录方式。
>
> 若假设之间存在矛盾，提出并记录取舍，再同步简述和补充规则。AI 自主修订写入工作流日志，不充作人工否决。PRD 正文采用课程要求的 PRD.md 命名，正文应只有一个权威版本。
>
> 当前阶段完成需求草案及其检查。技术选型、至少 5 条 ADR 和至少 12 个故事在后续架构与拆分阶段处理。实验 B 免做，实验 A 保留；现在不运行实验或填写结果，不把 AI 检查写成教师门禁通过。
>
> 在实际工作节点提交 Git，作者保持 AI 标识。输出需求文档、尚待验证的事项和下一阶段输入，不补造历史提交、会话或团队贡献。

运行 BMAD 脚本前可激活 `.tools/bin/activate`；或使用 `.tools/bin/uv run --python .tools/bin/python ...`。

