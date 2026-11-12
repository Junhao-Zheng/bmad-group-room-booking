---
title: '维护房间资料并保护现有容量需求'
type: feature
created: '2026-11-12'
status: ready-for-dev
route: dispatch
story_key: 3-1-room-management
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-3-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 3.1 — 维护房间资料并保护现有容量需求

<frozen-after-approval reason="用户授权完整实施，沿用规划；非额外人工批准">

## Intent

**Problem:** 管理员需要新增修改会议室，以便容量信息准确且不会破坏已有安排。
**Approach:** 在已完成依赖2.4基础上交付本故事可操作能力。追踪FR-16/17/21/22；NFR-01/02/04；ADR-03/06/07；UX-DR7/9/10。

## Boundaries & Constraints

**Always:** 服务端授权、严格输入、单事务业务/槽/审计、精确DTO、统一Clock；实际测试和可追踪证据。
**Never:** 不扩充范围外功能或虚构人类/课堂记录；不提前实施实验A目标；不操作Git/远端。

## I/O & Edge-Case Matrix

|验收编号|Given|When|Then|
|---|---|---|---|
|AC-3.1-1|管理员输入合法名称地点容量|新增或完整修改|稳定id、唯一name/location，1—1000整数；一条真实变更审计，无变化不加审计|
|AC-3.1-2|空/越界/重复组合或member|直接请求管理操作|400/409/403并全部不变，超大id400，不能硬删除|
|AC-3.1-3|未结束有效预约包括进行中人数较多|降低容量|不足则整次409并仅向admin列冲突；等于人数成功；已结束/取消不阻止降低|
|AC-3.1-4|创建预约与降低容量并发|20轮双请求|最终无未结束超员；业务与审计原子，UI失败保留输入|

</frozen-after-approval>

## Code Map

- 新增create_room/update_room：admin角色在写锁内从真实会话重验。name/location strip后1—80/1—120，capacity严格JSON int 1—1000；完整payload，不部分保存；组合唯一冲突409 ROOM_DUPLICATE。路径ID规范验证，未知404。
- 修改保留id；同值无真实变化返回当前Room、零审计。降低容量前同写锁查询kind=booking cancelled_at NULL end_at>t attendees>newcapacity，包含进行中；冲突整次409 CAPACITY_CONFLICT，admin看到精确管理conflicts含id/attendees/reason。等于人数允许；ended/cancelled不阻止。
- 一次真实创建或修改仅一次room.created/room.updated审计，RoomSnapshot精确四键，修改before/after，reason NULL。所有失败/审计异常全部回滚；不增加DELETE/停用永久开关。
- HTML /admin与顶栏管理入口仅admin；页面首次含房间新增/编辑表单，有label/取消编辑/提交确认条件、字段/冲突/未知结果/会话失效，失败不丢输入，安全纯文本。非admin直接HTML/API均403（匿名HTML跳登录，API401）。
- 真实HTTP20轮创建预约与降容量竞争，合法结果为预约成功且降容冲突，或降容成功且预约超容冲突；最终所有未结束有效预约不超容，审计与实际成功一一对应。覆盖认证/CSRF、无变化、上限、组合重复、整体回滚、旧intent在降容后仍重放。
- 不提前实现admin取消或撤销停用，确保实验共同基线没有目标命令。

验证页面等待、恢复及跨表单焦点；取证复用已验证的进程清理、INCOMPLETE和指纹机制。

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
