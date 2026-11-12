---
title: '取消本人尚未开始的预约'
type: feature
created: '2026-11-12'
status: done
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

- 实测发现复用history runner的退出竞争：组内只有Z状态时killpg(0)可能PermissionError。直接修补helper，仅在成功枚举且无活成员时视为退出；活组或枚举失败仍报错。保留失败/探针及定向回归；父流程已重开2.3记完成后返工，不增加业务故事。

## Tasks & Acceptance

- [x] 完整实现本故事用户路径。
- [x] 验收矩阵逐项有执行断言；新测试不能通过继承已有test类重复计数。
- [x] 实际运行所列验证，保存原始证据。
- [x] 更新README当前能力和复跑命令、证据入口；使用独立临时库，凭证不进仓库。

## Implementation Notes

遵守上游合同，技术选择为AI实施。

- 2026-11-12：新增独立 `member_cancel_booking` 与空 JSON POST 入口，锁内同一次 Clock 重新认证，所有权先于幂等，首次开始等号拒绝；取消字段/槽/完整 before-after 审计同连接事务，不提前实现管理员干预或停用撤销。
- `/my` 提供显式勾选确认、已开始/结束说明、原记录手动重试、成功列表刷新和失效清空。响应不完整时保留详情；成功反馈不抢走其他表单焦点。
- 新增 8 个独立 Python 验收测试、3 个既有 runner 清理回归和 17 个真实 JS 处理器回归；新增真实 HTTP 与浏览器 runner，复用已有进程清理/INCOMPLETE/源码指纹机制。完整 119 项 Python、71 项 JS 通过，无 skip；20 会话重复取消仅一次转换/一次审计；故障、重启、原意图与槽复用通过；新取消、原历史和原预约/重放 1280/390 浏览器通过。
- 原始证据、AC 映射与运行时间见 [Story 2.4 验证记录](../../docs/evidence/story-2.4-verification.md)。状态为 review，交由父工作流评审；Sprint 1 为当日实际压缩迭代，不代表人工/教师批准或四周团队活动。

## Spec Change Log

## Review Triage Log

|编号|裁决|处置|核对证据与理由|
|---|---|---|---|
|B1|medium|patch|详情响应ID与所选ID未绑定，新增取消会按selectedId操作另条记录；以响应ID等于请求ID的直接校验及测试修补。|
|B2|medium|patch|缺失attendees/capacity先模板格式化成undefined 人，通过字符串检查；原值整数校验须在替换DOM前完成，保留原详情。|
|B3|medium|patch|HTTP200空对象被!body.ok当确定拒绝；仅有效错误信封可标api，其他走未确认分支，保留同记录手动确认。|
|B4|medium|patch|取消POST失效时expired先清空cancelFeedback再聚焦它；改为聚焦已填说明，直接修正目标。|
|B5|medium|patch|POST成功后GET401清空全部成功提示，用户失去已提交确认；仍清受保护数据，保留无记录内容的通用已取消确认和重新登录提示。|
|B6|medium|patch|禁用已聚焦取消按钮会令焦点落到body；恢复时仅在body/本次控件适当聚焦，保留其他表单焦点，真实键盘断言。|
|B7|medium|patch|pending最后一项取消后列表为空但只有通用刷新文案；复用现有空态/数量反馈逻辑，说明筛选及刷新结果。|
|B8|medium|patch|future.result首个网络/屏障异常中断证据遍历，丢剩余结果及存储；逐worker记录脱敏异常、收齐20项并写最终存储后判失败。|
|B9|medium|patch|释放后的共享日程只有独立API检查，未证明日程控件渲染；直接补真实页面房间日期查询及DOM无原预约断言。|
|B10|low|patch|20次快速真实退出不能在所有OS确定命中zombie-only分支；直接新增成功僵尸列表+PermissionError定向回归，保留活组/枚举失败拒绝。|
|E1|medium|patch|与B1相同ID绑定缺口，独立保留本条裁决后合并修补。|
|E2|medium|patch|与B3相同空/错误信封分类缺口，独立保留本条裁决后合并修补。|
|E3|medium|patch|与B2相同原值校验缺口，独立保留本条裁决后合并修补。|
|V1|medium|patch|预验证将取消后filter替换为空，34项history测试仍通过；补pending取消后带原filter查询、消失行与保留已取消详情。|
|V2|medium|patch|预验证仅移除后续GET的expired仍全过；补成功POST+GET401，断言清空/隐藏/登录说明及通用成功事实。|
|V3|medium|patch|其他发现经父流程原代码核对：模板化缺失人数绕过检查，和B2/E3同根，保留独立裁决。|

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs`，新增实际处理器关键错误恢复回归。
- 新功能真实浏览器1280x800及390x844正常/拒绝路径、登录退出和既有关键流程；精确DTO与纯文本，无页面横向溢出。
- 矩阵及Code Map中的并发、故障与持久化验证须实际执行；保存原始结果，不以计划替代结果。

## 本轮接受结果

121项唯一Python测试、86项JS及真实HTTP/双视口浏览器通过。Story2.4的16项评审已关闭，0defer；2.3验证器清理返工已闭环，单独保留完成后返工事件。最终[证据](../../docs/evidence/story-2.4-review-fixes/parent-final-qa.json)。AI技术接受，不是人类或教师验收。
