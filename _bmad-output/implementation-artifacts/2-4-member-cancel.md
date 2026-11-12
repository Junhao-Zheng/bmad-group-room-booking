---
title: '取消本人尚未开始的预约'
type: feature
created: '2026-11-12'
status: in-progress
route: dispatch
baseline_commit: 791b208ec8075e2c13979eea466d2eda1fbc7faa
story_key: 2-4-member-cancel
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-2-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 2.4 — 取消本人尚未开始的预约

<frozen-after-approval reason="用户授权完整实施，沿用规划；非额外人工批准">

## Intent

**Problem:** 课题组成员需要确认后取消自己的活动，以便及时释放不再使用的时段。
**Approach:** 在已完成依赖2.3基础上交付本故事可操作能力。追踪FR-14/21/22；NFR-01/02/04；ADR-03/06/07；UX-DR6/9/10。

## Boundaries & Constraints

**Always:** 服务端授权、严格输入、单事务业务/槽/审计、精确DTO、统一Clock；实际测试和可追踪证据。
**Never:** 不扩充范围外功能或虚构人类/课堂记录；不提前实施实验A目标；不操作Git/远端。

## I/O & Edge-Case Matrix

|验收编号|Given|When|Then|
|---|---|---|---|
|AC-2.4-1|本人待开始预约|确认取消|200已取消，槽全释放，保留历史且一条member取消审计|
|AC-2.4-2|本人已取消预约或已开始有效预约|重复或首次取消|重复返回原元数据无新审计；首次start边界及以后409|
|AC-2.4-3|他人或不存在记录|请求取消|均404，权限先于幂等；数据不变|
|AC-2.4-4|首次取消审计失败|提交取消|整个取消与槽删除回滚；成功后时段可再次预约|

</frozen-after-approval>

## Code Map

- 新增独立services.member_cancel_booking(actor,id)：BEGIN IMMEDIATE后同一t重新认证，查kind=booking且owner=actor.id；所有权先于重复分支，他人与不存在统一404。管理员在此接口也只能取消自己且遵循成员开始期限。
- 已取消返回原Full，无writer调用、无字段覆盖，即使已过start/end；有效首次仅t<start，t=start及以后409 TRANSITION_CLOSED。成功保存cancelled_at/by，cancel_reason=NULL，删全部所属槽，保留记录/intent，一条booking.cancelled_by_member审计完整before/after同连接。
- /api/bookings/<ID>/cancel POST空对象，Origin/CSRF先检查。不要提前实现或抽成支持admin取消/block撤销的通用终态命令；它们必须留给实验A初次实现。
- /my待开始本人记录提供取消确认（可用明确确认区域或原生confirm）；已开始/结束解释不可取消。重复取消可以确认状态但不能新转换。失败保留状态，成功刷新个人/日程/可用性（当前页面可刷新相关数据；离开再查询应立即可用）。响应未知原记录重试，不自动发请求。
- 测试权限先于幂等、t=start边界、重复过期返回原元数据、槽释放可再次预约、旧成功intent重放cancelled、审计writer故障全回滚。真实HTTP同时重复成员取消只有一次转换；成员/admin竞争待2.5联合验收，不声称已测。
- 新浏览器runner复用已验证的独立进程清理/INCOMPLETE/源码指纹机制；验证实际DOM值和加载/失败后的可编辑性，成功反馈不要抢走已移到其他表单的焦点。
- Sprint1增量故事到此形成成员闭环；证据说明实际压缩迭代时间，不虚构四周或团队会议。

## Tasks & Acceptance

- [ ] 完整实现本故事用户路径。
- [ ] 验收矩阵逐项有执行断言；新测试不能通过继承已有test类重复计数。
- [ ] 实际运行所列验证，保存原始证据。
- [ ] 更新README当前能力和复跑命令、证据入口；使用独立临时库，凭证不进仓库。

## Implementation Notes

遵守上游合同，技术选择为AI实施。

## Spec Change Log

## Review Triage Log

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs`，新增实际处理器关键错误恢复回归。
- 新功能真实浏览器1280x800及390x844正常/拒绝路径、登录退出和既有关键流程；精确DTO与纯文本，无页面横向溢出。
- 矩阵及Code Map中的并发、故障与持久化验证须实际执行；保存原始结果，不以计划替代结果。
