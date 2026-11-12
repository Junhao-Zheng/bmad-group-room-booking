---
title: '创建停用并查询完整管理记录'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: 4747ea2add89c06299246a1f60a06b2ecebad2a3
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

- [x] 完整实现本故事用户路径。
- [x] 验收矩阵逐项有执行断言；新测试不能通过继承已有test类重复计数。
- [x] 实际运行所列验证，保存原始证据。
- [x] 更新README当前能力和复跑命令、证据入口；使用独立临时库，凭证不进仓库。

## Implementation Notes

遵守上游合同，技术选择为AI实施。

- `normalize_block_payload/validate_block_window` 复用严格纯解析；`services.create_block` 独立写入口，在锁内认证管理员、取单次 Clock、检查预约/停用冲突，业务/完整槽/一次 block.created 审计共同提交。
- 新增精确 `BlockFull/BlockSnapshot` 白名单；独立 `admin_bookings/admin_blocks` 入口共享只读过滤，支持房间、北京相交日期与互斥四态，完整DTO按start/id升序返回。
- `/admin` 新增停用确认表单及两类只读管理列表；区分未查询/加载/空/冲突/失败/失效，保留输入、纯文本、跨表单焦点；没有取消/撤销按钮。
- 新增14个独立Python测试、35个真实JS处理器回归；全量153项Python、176项JS通过，无skip且无重复Python测试ID。20轮真实HTTP booking/block竞争每轮1×201+1×409，13轮预约胜、7轮停用胜；最终存储、故障回滚、重启及旧意图重放通过。
- 新功能及原房间管理、预约重放、本人取消共4套真实浏览器均通过1280×800与390×844。五份HTTP/浏览器报告源码指纹与当前文件一致，验证端口清理完成。
- README与[逐项证据](../../docs/evidence/story-3.2-verification.md)已更新，原始输出、网络、截图、逐轮存储、失败报告可追溯。默认浏览器启动失败保留INCOMPLETE，随后使用已安装Chrome完整通过。
- 未实现管理员取消或停用撤销、未开展实验A、无Git/远端操作。实现待父流程独立评审，未冒充人类/教师验收。

## Spec Change Log

## Review Triage Log

|来源|裁决|路线|验证与依据|
|---|---|---|---|
|B1|medium|patch|blocks.js Number(select.value)会把9007199254740993变为9007199254740992；若两ID均存在可写错房间。直接在创建前拒绝非安全整数，另对刷新目录中的不可安全表示ID拒绝接受，不改变后端正64位合同；不引入全站无损JSON系统。|
|B2|medium|patch|rooms.js与blocks.js各有独立blocked变量，前者失效不能清后者完整记录；新组合页面造成保护状态不同步。用页面内受控事件联动身份丢失，双方清数据/禁用，防止在途旧成功响应恢复显示。|
|B3|medium|patch|新block-form没有method/action且提交按钮默认可用；脚本未初始化时浏览器原生GET会带reason/start/end进URL且不创建。初始禁用提交，成功初始化才启用，保留静态不可用说明并验证JS禁用路径。|
|B4|low|patch|未知结果后原确认仍勾选，可能误点再次提交；同内容若已提交，占用互斥会拒绝重复，因此未证实双创建。最小修正为清除原确认并明确重新核对；既有主动查询入口保留，不擅自加入新硬性对账协议或幂等业务规则。|
|B5|medium|patch|查询完成后编辑筛选项不更新反馈或结果，旧结果仍位于新条件下，用户可能误解范围。用已执行条件说明或变更时清旧结果/标为待查解决；测试条件改变及重新查询。|
|B6|medium|patch|查询catch只显示message，丢弃fields.date等具体提示；HTML允许服务明确拒绝的9999-12-31。补字段错误、aria-invalid及恢复后焦点，日期最大值与现有合同一致。|
|B7|medium|patch|核查新JS与浏览器脚本：刷新按钮仅建stub，无事件调用。新房间到三选择框、原选择/草稿/确认以及失败恢复均缺覆盖，归入刷新验证缺口。|
|B8|medium|patch|丢响应后只断言未额外POST及草稿，未校验恢复查询含实际已提交ID。route.fetch已有真实响应可作已提交ID来源；须断言同一ID在查询和DOM出现并核对时段/原因。|
|B9|medium|patch|Python只比较after中幸存的原ID；原记录及槽一同丢失仍能通过。须完整比较所有原ID与行、原槽，另验证允许新增数据；增加删除原记录的负向证明。|
|B10|medium|patch|两类列表浏览器只检查响应精确键及无按钮/注入标签，删除render字段甚至整块仍可能通过。须真实DOM逐行比较标签/值，覆盖预约及停用四态与完整终态信息，不能只核对JSON。|
|V1|medium|patch|验证层已确认：没有成功预约渲染断言；render(bookings)清空后直接返回仍能通过现有检查。与B10同根因，扩展现有浏览器及处理器值绑定验证。|
|V2|medium|patch|验证层已确认：刷新未被实际执行；删掉append(option)仍不会影响已有测试。与B7同根因，加入新增房间、三选择框、草稿和确认的真实交互。|
|P1|medium|patch|父流程核查test_authorization_before_fields_direct_api_and_no_future_mutation_routes永久断言未来两个接口404/服务不存在，浏览器也永久断言管理列表没有按钮；这会把已计划的2.5/3.3正确实现判失败。将目标未实施的时间性证明保留为本阶段原始证据及实验冻结前检查，移除常规回归中禁止未来功能的断言，保留真实授权/不误写/纯文本断言。|

三层评审已全部返回后逐条裁决：Blind 10条，Edge明确空数组0条，Verification 2条；另含父流程发现1条，共13条。B7/V2及B10/V1分别同根因归并，共11项直接修补，0defer。每项均保持现有业务/API合同，无新增公共业务能力。

B1只保护本次新增停用创建的错房间风险；不以本故事宣称已解决所有旧页面的极大整数显示/编辑边界。B4直接清确认避免复用未知前确认，重试仍为主动操作；没有证据支持需要修改后端创建语义。P1是当前阶段假设误写成长期回归规则，不提前实现后续功能。

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs`，新增实际处理器关键错误恢复回归。
- 新功能真实浏览器1280x800及390x844正常/拒绝路径、登录退出和既有关键流程；精确DTO与纯文本，无页面横向溢出。
- 矩阵及Code Map中的并发、故障与持久化验证须实际执行；保存原始结果，不以计划替代结果。

## 本轮接受结果

156项唯一Python、208项JS及真实HTTP/浏览器验证通过，11项修补闭环，0defer。AI技术接受；[最终核验](../../docs/evidence/story-3.2-review-fixes/parent-final-qa.json)。

## Epic 3 复盘后修补

本卡完成后重新打开，8组共享修补按实际状态关闭。208 Python/376 JS和双视口管理/审计验证通过；最后独立复核受429限制未完成，按open item披露。[最终核验](../../docs/evidence/epic-3-followup/verification.md)。不改写本卡首次验收指标。
