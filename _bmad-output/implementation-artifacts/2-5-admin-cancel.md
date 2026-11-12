---
title: '管理员说明原因干预未结束预约'
type: feature
created: '2026-11-12'
status: in-progress
route: dispatch
baseline_commit: 177dc64e5897a24850dcc79714cfcb87724c09d6
story_key: 2-5-admin-cancel
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-2-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/PRD.md
---

# Story 2.5 — 管理员说明原因干预未结束预约

<frozen-after-approval reason="用户授权完整实施；实验A的X组；不是人类逐项批准">

## Intent

**Problem:** 管理员需处理未结束预约并向预约人说明理由。
**Approach:** 独立管理取消命令，追踪FR-15/21/22、NFR-01/02/04、ADR-03/05/06/07、UX-DR8/9/10。

## Boundaries & Constraints

**Always:** 按上下文合同、单事务业务/槽/审计、新鲜身份与一次锁后时刻。
**Never:** 不实现撤销停用或通用管理转换命令，不读对照Y目录，不操作Git/远端，不冒充人类决策。

## I/O & Edge-Case Matrix

|验收|Given/When|Then|
|---|---|---|
|AC-2.5-1|管理员对待开始/进行中预约提交strip后1—500字原因|200 BookingFull；首次取消保存时刻/人/原因，释放全部槽，一次booking.cancelled_by_admin审计|
|AC-2.5-2|已取消记录含成员先取消；或首次t>=end；重复合法/非法原因|重复原结果/元数据/零审计，即使原end已过；首次结束409 TRANSITION_CLOSED；重复非法原因仍400|
|AC-2.5-3|成员、匿名、过期/退出、旧角色或非法参数|权限优先、拒绝且数据不变；正确kind；正64位ID/格式按合同|
|AC-2.5-4|成员与管理取消20轮真实HTTP竞争；审计失败|一转换保留首成功事实，双方结果一致；失败业务/槽/审计完整回滚|

</frozen-after-approval>

## Code Map

- 基线已有成员取消、房间/停用创建和管理列表，尚无两个实验目标。读取当前代码再接入；保留既有用户路径。
- services独立admin_cancel_booking(actor,id,reason)：BEGIN IMMEDIATE取得锁后一次Clock，重验有效会话及数据库admin；reason用normalized_text，校验对象kind=booking；已取消返回现有Full；首次t<end后更新cancelled_at/by/reason、只删对应槽、写完整before/after快照事件，COMMIT后返回。不得用传入Actor.role代替数据库，不能把校验放幂等分支之后。
- POST /api/admin/bookings/<ID>/cancel接受JSON reason，单层ok/data；所有POST沿用Origin/CSRF。详情取当前房间/显示名，但审计保留事件时操作者快照。不存在或对象kind不对404，普通成员先403，非法字段400。
- 在现有/admin预约列表提供取消确认及原因输入，等待禁用、失败保留、成功刷新；取消结果对预约人可见。textContent/模板转义，1280×800/390×844可用。
- 幂等分支不得调用writer；同事务注入writer前/后失败与COMMIT故障须回滚；复用已取消记录保留原操作者/原因（可能null）。测试权限/期限的精确等号，过期/退出/降权，非法reason含NUL/无效UTF8；不对测试用例继承重复计数。
- 初次实现只做本轮功能及验证，不自行另开代理评审/修复。父流程先封存初版代码和输出，再按实验统一标准评审；负面结果如实报告。

## Tasks & Acceptance

- [ ] 交付独立命令、API、界面和矩阵测试。
- [ ] 实际验证并保留原始输出；报告遗漏或风险，不写未跑成绩。

## Implementation Notes

本次是同基线、同模型配置、同主机的实验A完整上下文组。父流程记录调用时间；不自行修改上游规则。

## Spec Change Log

## Review Triage Log

## Verification

- 全量Python及JS回归，无skip；API精确DTO和安全错误。
- 20轮真实独立HTTP成员/管理员取消竞争，最终DB完整槽、元数据、恰一次转换审计；真实文件库故障回滚。
- 桌面/手机真实浏览器操作管理取消、原因/确认/等待/拒绝/结果和成员详情；保留证据。
