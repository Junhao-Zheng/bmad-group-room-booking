# 课程交付核对

依据《BMAD讲义+作业》第29、32—39页及用户补充：实验 B 可免做，后续课堂临时变更不再给出；正式视频与演示本轮暂缓。后两项是用户安排，不冒充教师已免除原录屏要求。原讲义不上传仓库。

## 当前判定

|讲义要求|现有证据|严格核对结果|
|---|---|---|
|产品简述与真实问题|[产品简述](../_bmad-output/planning-artifacts/product-brief.md)、U-07真实描述：林老师安排、微信群通知、常用2号楼407、偶与其他导师撞时间|已记录用户亲述；登记制度及大组实际采用情况未知|
|编号需求与验收|[PRD v2](../_bmad-output/planning-artifacts/PRD.md)：FR-01—24、NFR-01—04|文本齐备；新增规则对应Epic4代码和验证|
|架构与至少5项ADR|[架构](../_bmad-output/planning-artifacts/architecture.md)含8项ADR|数量满足；新流程在原分层单体内扩展|
|至少3史诗、12故事|[史诗](../_bmad-output/planning-artifacts/epics.md)、[状态](../_bmad-output/implementation-artifacts/sprint-status.yaml)|原3史诗12故事及新增Epic4五故事均有规格、实现和测试|
|至少8条实现规则|[project-context](../project-context.md)16条|数量满足；原规则中的旧30天描述应按PRD v2和决策D-007理解|
|两冲刺、版本化过程|[Sprint 1](sprints/sprint-1-review.md)、[Sprint 2](sprints/sprint-2-review.md)、故事事件与Git|有压缩完成的两次增量及版本记录；不声称真实四周课堂经历|
|源码、测试和NFR|[应用](../booking_app/)、[验证索引](verification.md)|当前260项Python、414项JS全通过；Epic4真实Chrome双视口及新版重启通过；当前7天窗口的NFR03测得200样本P95 16.893ms、0错误|
|至少15条决策、5次人工否决/实质修改|[决策日志](../decision-log.md)23条；D-005/006/007/010/012/015/017为7项实质修改|已记录用户原话及可核对改动；D-021/022/023无另述个人理由，是否逐条计入完整决策由教师判定|
|复盘五指标、实验A|[复盘](../retrospective.md)、[实验A结果](experiment-a-results.md)|有原始协议、两个分支、实测与局限；实验操作者是AI，不能冒充同一学生或核验不可见模型版本；B按用户转述免做|
|README、贡献、AI声明、约10分钟演示|[运行说明与AI声明](../README.md)、[AI及贡献](ai-use-and-contributions.md)、[三人分工](team-contribution-plan.md)、[演示准备](demonstration-plan.md)|README已如实披露AI工具和不可核验的精确模型版本；三人姓名及全项目责任范围已分配，实际贡献记录及正式录屏/演示未完成|

## 本轮新增规则闭环

|用户决定|实现与证据|
|---|---|
|D-006/007/012/013/018：导师归属、学生申请审批、7天窗口、共享导师、详情权限|[4.1身份](evidence/human-review/identity-verification.md)、[4.2审批](evidence/human-review/booking-verification.md)|
|D-010：学生取消需本人导师开始前确认|[4.3取消](evidence/human-review/cancellation-verification.md)|
|D-017/022/023：每周最多8周、整组审批、导师直订|[4.4周期](evidence/human-review/weekly-verification.md)|
|D-015/016：一次原因批量取消并停用、撤销不恢复|[4.5维护](evidence/human-review/maintenance-verification.md)|

Python回归覆盖20个竞争申请及20组审批与停用确认竞争、写入途中故障回滚、v4/v5备份升级。真实Chrome在1280px和390px完成8周申请、导师批准、单场取消、批量维护预览与确认、响应丢失后同凭据重试、撤销不恢复。新版真实Waitress重启检查还核对了8周申请/审批、取消申请/确认、批量停用确认、撤销和持久重放。结果只证明合成数据、本机环境和列出的路径，不证明真实课题组已经采用。

## 仍需本人或教师提供

1. 讲义第38页把M1/M2列为第1、2周的课堂里程碑，要求实施前通过；它们不在第33页的十份Git必交产物中。现无当时课堂通过记录，不能在项目完成后补写为事前通过；如任课老师调整了实际执行安排，应按其真实通知记录。项目完成后的课堂评审是M4终期演示。
2. 三人姓名与全项目责任分配已记录；刘茜雅、黄欣的既有参与和三人后续实际复核尚待核实。四周课堂时间线没有真实资料，不编造。
3. 正式约10分钟录屏和演示按用户要求暂缓；准备材料不是已完成视频。
4. 大组其他导师是否愿意共同使用、现行登记方式和实际试用反馈未核实。当前软件只保证已录入预约的互斥。
5. 课程结束后的操作记录留存期限、真实部署和维护责任尚未确定；本次范围明确为本机课程原型。

因此，**技术原型与可由AI完成的过程材料已完成；严格意义上的全部课程要求仍不能宣称完成**。实验B和未下发的临时变更不列缺项。早期口径、原始会话摘录及局限仍保存在[决策日志](../decision-log.md)和[证据目录](evidence/)。
