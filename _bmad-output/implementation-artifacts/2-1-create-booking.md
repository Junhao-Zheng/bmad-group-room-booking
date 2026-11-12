---
title: '提交有效且不冲突的活动预约'
type: feature
created: '2026-11-12'
status: in-progress
route: dispatch
baseline_commit: 85263cf6526ea9dab8c359aa59ae04cccc060a9e
story_key: 2-1-create-booking
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-2-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 2.1 — 提交有效且不冲突的活动预约

<frozen-after-approval reason="用户授权完整实施，依规划推进；非人类逐项批准">

## Intent

**Problem:** 成员在找到可用房间后，需填写活动并获得确定的预约结果。
**Approach:** 创建预约与原子审计。追踪FR-08—11/21/22、NFR-01/02/04、ADR-01/02/03/06/07、UX-DR5/9/10。项目根为本故事文件所在仓库。

## Boundaries & Constraints

**Always:** 遵循架构事务、权限、DTO及安全错误合同。
**Never:** 不实现管理员取消/停用撤销、不删历史、不操作Git/远端。

## I/O & Edge-Case Matrix

|场景|输入/状态|行为|错误/验证|
|---|---|---|---|
|AC-2.1-1|合法room_id,title,purpose,attendees,start,end,intent_key|POST /api/bookings→201单层data={booking:BookingFull,replayed:false}；一组连续槽、一条booking.created审计|全部精确DTO键和null；活动文本纯文本|
|AC-2.1-2|strip空/超长title-purpose、非int/非正人数、JSON数字字符串ID、时间各边界、超容量|复用查询同时间规则；字段400，容量409 CAPACITY_CONFLICT，不存在房间404|不产生记录/槽/审计；超大ID、无法编码文本不能500；权限先于参数|
|AC-2.1-3|同室booking/block重叠；首尾相邻；不同房间|重叠409 OCCUPANCY_CONFLICT；相邻/异室成功；20独立成员同时同槽恰1x201+19x409|最终1条记录、完整槽、一条创建审计；共享conflicts不含ID/人数/用途/账号|
|AC-2.1-4|audit_writer注入异常或提交故障|500安全提示，整个业务和槽回滚；无成功响应|UI保留输入；所有POST有Origin/CSRF；真实失败不占意图key|

</frozen-after-approval>

## Code Map

- 复用auth Actor、db.write_transaction与1.3时间纯规则；JSON ID/人数须type(value) is int，不能用query_attendees截断人数。写锁内重新读真实会话/角色/显示名，统一取一次t。
- schema.sql加入架构audit_events及db必需列检查，初始化保留旧数据/user_version1。独立audit_writer(conn,event)只INSERT，按架构完整事实快照，测试可注入故障，生产无HTTP后门。
- services.create_booking：规范化→房间/窗口/容量/占用检查→业务和完整槽INSERT→一次审计→COMMIT；仅明确槽/意图唯一冲突映射409，其余异常安全500。成功后才响应。DTO/共享与admin冲突白名单严格遵守架构。
- 当前交付新建；2.2交付可靠重放。本次保存成功key与规范化六字段JSON，重复key暂受控409；README明确此增量未交付可靠重试，不提前实现2.2意图编辑/重放逻辑。
- 首页 `/` 从可用房间结果选择资源后填写title/purpose，沿用查询时段和人数。随机32字节新key；等待时禁输入/按钮，成功显示编号/时段，冲突保留输入，未知结果不得声称失败或自动重发。动态文字textContent。保留查询/日程/认证能力。
- 新tests/test_create_booking.py及隔离真实Waitress8线程HTTP验证器；20不同成员/key同槽竞争，检查完整最终DB及审计。可参考外部work/verify_nfr_draft.py的通用HTTP部分，不导入未来未实现调用。

## Tasks & Acceptance

- [ ] 创建服务/schema/审计/DTO及首页表单可用；不得提前实现实验目标。
- [ ] 矩阵全部实际通过，保存原始证据，更新README能力与复跑命令。

## Implementation Notes

无新增人类意图缺口；仅在隔离测试库写入，代码及schema增量可回退；涉及服务、DTO、审计、路由、前端和验证脚本。

## Spec Change Log

## Review Triage Log

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs` 查询/认证与新增表单关键回归。
- 真实HTTP20成员竞争，1成功19冲突，最终存储完整且恰一次审计；故障注入全部回滚。
- 真实浏览器1280x800/390x844创建成功与冲突、普通Unicode/XSS文本及原查询登录退出验证。
