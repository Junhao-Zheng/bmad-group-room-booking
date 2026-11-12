---
title: '撤销尚未结束的停用'
type: feature
created: '2026-11-12'
status: in-review
route: dispatch
baseline_commit: 39436f328eaf2b85d5bf72629e903db00ccc842b
story_key: 3-3-revoke-block
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-3-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 3.3 — 撤销尚未结束的停用

<frozen-after-approval reason="用户授权完整实施；实验A的Y组；不是人类逐项批准">

## Intent

**Problem:** 管理员需说明原因释放不再需要的维护时段，恢复房间可预约性并保留历史。
**Approach:** 独立停用撤销，追踪FR-19/21/22、NFR-01/02/04、ADR-03/05/06/07、UX-DR8/9/10。

## Boundaries & Constraints

**Always:** 管理权限、合法原因、期限、幂等和原子审计。
**Never:** 不恢复已取消预约、不硬删除历史，不冒充人工判断。

## I/O & Edge-Case Matrix

|验收|Given/When|Then|
|---|---|---|
|AC-3.3-1|管理员对未结束停用提交strip后1—500字原因|200 BlockFull；首次保存撤销时刻/人/原因，全部槽释放，同事务一次block.revoked审计|
|AC-3.3-2|已撤销记录或首次t>=end；重复合法/非法原因|重复保留原结果，即使end已过；首次结束409；重复非法原因仍400|
|AC-3.3-3|成员、失效/退出、降权或非法参数|权限优先、拒绝且数据不变；对象kind、正64位ID及原因格式正确|
|AC-3.3-4|同时重复撤销或审计失败|一次转换与首成功元数据；失败完整回滚，不恢复曾取消预约|

</frozen-after-approval>

## Code Map

- 本卡在首次实现前冻结于主仓库，但不向Y提供；Y只接收预登记口述TASK、共同运行说明及共同基线代码/测试。不得读本卡、规划、主仓库或X。初稿封存、统一首轮评审之后，修复阶段才揭示完整上下文；记录这一区别。
- services独立revoke_block：BEGIN IMMEDIATE后一次Clock、重验数据库有效admin；先验证strip后1—500字原因，再查kind=block。已撤销返回原Full且零writer；首次仅t<end，更新存储取消字段、只删目标槽、一次block.revoked审计，完整before/after同连接，提交后返回。
- POST /api/admin/blocks/<ID>/revoke接受JSON reason，单层ok/data；沿用Origin/CSRF、身份优先、严格ID和安全错误。原停用reason保持，输出revoked字段按BlockFull，不能泄露存储cancelled字段。
- /admin停用列表增加原因及明确确认，提交中禁用，失败保留输入，成功刷新。文本安全展示，手机/桌面可用，不影响已有预约/停用查询与创建。
- 两管理员独立HTTP会话20轮同时撤销，每轮两个200且元数据一致、仅一次转换/审计；验证首成功actor/time/reason、全部槽释放、其他记录不变。
- 验证待开始/进行中、首次结束等号、过期重复、重复非法原因、错误kind/严格ID、匿名/member/过期/退出/降权、writer前/后失败与提交失败，真正文件库事务回滚。

## Tasks & Acceptance

- [ ] 首次实现按Y口述输入，封存后统一评审。
- [ ] 修复后独立命令、API、界面与验收全部通过。
- [ ] 实际保存验证，不重复计数测试，不写未跑成绩。

## Implementation Notes

本卡是主流程追踪和首稿之后评审修复的合同，不是Y的首次输入。全部实验差异须据首稿证据记录，不人为制造失败。

## Spec Change Log

## Review Triage Log

## Verification

- 全量Python及JS回归，无skip；精确DTO和安全错误。
- 20轮真实独立HTTP双管理员撤销，最终数据库一次转换/审计、原元数据和槽；文件库故障回滚。
- 1280×800和390×844实际管理撤销、原因/确认/等待/拒绝/结果及既有关键路径，保留证据。
