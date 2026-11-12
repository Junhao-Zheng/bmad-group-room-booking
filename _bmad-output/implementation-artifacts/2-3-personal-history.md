---
title: '查看自己的预约及状态'
type: feature
created: '2026-11-12'
status: in-progress
route: dispatch
baseline_commit: 2ded2623c555d1fad3db93341e1c17c58d9ee087
story_key: 2-3-personal-history
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-2-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 2.3 — 查看自己的预约及状态

<frozen-after-approval reason="用户授权完整实施，沿用规划；非额外人工批准">

## Intent

**Problem:** 课题组成员需要筛选个人活动记录并查看详情，以便掌握未开始、进行中和历史安排。
**Approach:** 在已完成依赖2.2基础上交付本故事可操作能力。追踪FR-13/04/22；NFR-02；ADR-02/06；UX-DR3/6/9。

## Boundaries & Constraints

**Always:** 服务端授权、严格输入、单事务业务/槽/审计、精确DTO、统一Clock；实际测试和可追踪证据。
**Never:** 不扩充范围外功能或虚构人类/课堂记录；不提前实施实验A目标；不操作Git/远端。

## I/O & Edge-Case Matrix

|验收编号|Given|When|Then|
|---|---|---|---|
|AC-2.3-1|本人有四态记录|筛选每种状态并查询详情|start/id降序，时间恰好start/end状态正确；完整业务及取消信息可见|
|AC-2.3-2|替换查询身份或他人记录id|访问本人列表/详情|列表始终本人，非本人及不存在详情同404；admin可读全详情|
|AC-2.3-3|空记录或长文本|使用手机/键盘查看|空状态和字段清楚，无页面横向溢出，活动名按纯文本渲染|

</frozen-after-approval>

## Code Map

- 新增services.my_bookings(actor,status=None)及booking_detail(actor,booking_id)：短只读事务内同一t、服务复核真实会话；个人列表始终actor.id，忽略客户端身份选择。四态过滤、start_at/id降序；非法状态400，空200。管理员个人列表仍只本人。
- 详情本人/admin可见BookingFull；成员访问他人和合法不存在同404。管理员角色取最新数据库，不信任旧Actor.role；授权优先于敏感对象参数与存在性。严格资源ID规范。
- web.py新增GET /api/bookings/mine与/api/bookings/<ID>以及HTML /my。静态mine路由不能被ID吞掉；路径ID用文本转换避免框架对超大数字500。HTML匿名跳login，API匿名401JSON。
- 顶栏提供预约/我的预约导航，保留退出键盘流程。/my列表/详情安全显示名称用途、人数、房间、时间、状态、取消操作者原因，所有空值有明确含义，四态筛选和空/加载/错误/失效。取消按钮由下一故事交付，不放假操作。
- 以独立合成夹具覆盖四态、同start逆id排序、精确start/end时间和状态边界、两个成员/管理员隐私。浏览器验证四态筛选和长文本纯文本，桌面/手机无横溢出。

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
