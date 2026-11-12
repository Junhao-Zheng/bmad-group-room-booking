---
title: '创建停用并查询完整管理记录'
type: feature
created: '2026-11-12'
status: ready-for-dev
route: dispatch
story_key: 3-2-maintenance-block
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-3-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 3.2 — 创建停用并查询完整管理记录

<frozen-after-approval reason="用户授权完整实施，沿用规划；非额外人工批准">

## Intent

**Problem:** 管理员需要登记维护占用并浏览全部记录，以便维护安排不会静默覆盖成员活动。
**Approach:** 在已完成依赖3.1基础上交付本故事可操作能力。追踪FR-18/20/21/22；NFR-01/02/04；ADR-02/03/06/07；UX-DR8/9/10。

## Boundaries & Constraints

**Always:** 服务端授权、严格输入、单事务业务/槽/审计、精确DTO、统一Clock；实际测试和可追踪证据。
**Never:** 不扩充范围外功能或虚构人类/课堂记录；不提前实施实验A目标；不操作Git/远端。

## I/O & Edge-Case Matrix

|验收编号|Given|When|Then|
|---|---|---|---|
|AC-3.2-1|未来半点时段及1—500字原因|创建停用|允许跨日和超过4h，仍满足30天窗口；201、完整槽和一次审计|
|AC-3.2-2|已有预约或停用重叠|尝试新增停用或并发booking/block|409且原预约不变；20轮最终互斥；相邻时段可用|
|AC-3.2-3|admin按房间日期状态过滤|查询booking与block管理列表|完整白名单DTO，start/id升序；block四态互斥，非法status400|
|AC-3.2-4|member或审计故障|直接调用或提交停用|拒绝越权/完整回滚；UI冲突展示必要详情和保留输入|

</frozen-after-approval>

## Code Map

- 新增独立create_block(admin,payload)：strict room_id JSON int，start/end格式复用纯解析，t<start<end<=t+30d、半小时刻度；允许跨日及>4h。reason strip1—500；user_id=创建者admin，booking分支字段NULL。
- 同一BEGIN IMMEDIATE内重新认证admin、取t、查房间与booking/block重叠；冲突409且不取消原预约。连续完整槽、block.created审计同提交；BlockFull精确revoked五键null，无cancelled外部键。
- 新增admin_bookings/admin_blocks只读服务及GET /api/admin/bookings、/api/admin/blocks；room_id/date/status均可选，非法400；指定不存在room404；date半开相交；start/id升序；四态过滤互斥。完整白名单仅admin，不能复用共享DTO省字段。
- /admin加入停用创建、预约/停用列表与筛选；用户文案区分未查/空/加载/冲突/权限，确认原因与时段。预约列表此时只查看，停用列表只查看；不要放尚不可用取消/撤销按钮。
- 20轮真实HTTP booking/block同槽竞争只有一成功另一409；不同类型共享槽约束、相邻允许、跨日历史、审计失败全部回滚、管理员列表精确字段/状态/顺序、member直接403。
- 严禁实现admin_cancel_booking或revoke_block，以及能传kind直接执行这两个行为的通用终态函数。本故事完成后才固定实验A共同基线；实现者不得查看/开展实验目标。

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
