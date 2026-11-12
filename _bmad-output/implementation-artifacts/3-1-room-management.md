---
title: '维护房间资料并保护现有容量需求'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: 6644902c9e3880482d1edef75c42a1ee303ba6dd
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

- [x] 完整实现本故事用户路径。
- [x] 验收矩阵逐项有执行断言；新测试不能通过继承已有test类重复计数。
- [x] 实际运行所列验证，保存原始证据。
- [x] 更新README当前能力和复跑命令、证据入口；使用独立临时库，凭证不进仓库。

## Implementation Notes

遵守上游合同，技术选择为AI实施。

- `domain.normalize_room_payload` 校验完整文本/容量；`services.create_room/update_room` 在同一写锁内复核真实管理员、检查重复与未结束预约人数，并一次写审计。无变化不更新 timestamp、不调用 writer。
- `web.py` 提供管理页面和新增/修改 API；`admin.html/rooms.js` 提供目录、确认、编辑取消、完整错误恢复与跨表单焦点保护，顶栏仅管理员显示管理入口。
- 独立 `RoomManagementTests` 与真实 JS 处理器测试，不继承既有测试类。新增 HTTP/browser 验证器复用已验证的清理/INCOMPLETE/源码指纹；README 已更新。
- 实际验证：Python 133 项、JS 103 项全部通过无 skip；真实 HTTP 20 轮竞争、故障/重启/旧意图重放通过；1280×800 和 390×844 新管理、既有预约重放与本人取消浏览器通过。完整执行记录见 [Story 3.1 验证记录](../../docs/evidence/story-3.1-verification.md)。
- 未实现管理员取消或停用撤销；无 Git/远端操作。

## Spec Change Log

## Review Triage Log

|编号|裁决|处置|核对证据与理由|
|---|---|---|---|
|B1|low|reject|64位ID超过2^53的舍入确实存在；与已接受历史/取消页面边界同源。本地课题组正常自增不可能接近此规模，且无ID导入入口；跨JSON无损ID重构不属直接更正，按低频低影响规则拒绝，未缩小后端64位合同。|
|B2|medium|patch|服务接受内部CR/LF，text输入会删换行，纯容量修改可意外改名。改用可保留多行的现有字段编辑控件；对浏览器CR标准化后仍未编辑的字段保留原值，确保仅修改容量时原名称/地点逐字符往返，不改既有文本合同。|
|B3|low|reject|两个旧页面完整保存会后写覆盖前写的名称等字段，风险真实；当前是已确认三字段的完整替换而非局部补丁。低频房间资料编辑中影响是可审计、可重新修改的元数据，容量/历史安全仍被锁内保护。版本预条件会增加读写协议和冲突交互复杂度，按低频低影响规则拒绝；不声称提供乐观编辑并发控制。|
|B4|medium|patch|number控件允许1e2/10.0/01，但正十进制正则将其发成null。直接按数值解析再检查整数与1—1000范围，保持服务器严格JSON整数约束，补真实浏览器及处理器断言。|
|B5|medium|patch|两种刷新catch覆盖sessionError登录说明，且blocked已禁用刷新。保留身份错误专属说明；成功保存后的失效同时保留通用已保存事实，禁止指向已禁用操作。|
|B6|medium|patch|错误conflicts非数组或缺时间字符串会在catch内再次抛出。渲染前检查当前实际使用的错误fields/conflicts结构，不合法走未知响应且保留草稿/恢复控件，新增定向用例。|
|B7|low|reject|当前只保留当前页草稿，导航登录后不会恢复；8小时会话边界上的三字段管理草稿损失真实但影响小且少见。跨登录草稿存储、恢复、CSRF轮换和权限复核需要新状态/交互，不是直接修正，按低频低影响规则拒绝；说明不支持跨页面草稿恢复。|
|B8|medium|patch|勾选确认后修改任何字段仍可提交未重新核对的值。给现有字段input/change直接清确认，不改接口，不在未知响应时自动重提。|
|B9|low|patch|非零driver只保留通用RuntimeError，丢失失败定位。直接记录受控阶段名、错误类别和本脚本断言行号等白名单诊断；不保存原始可能含密码/cookie/CSRF的stderr或服务器异常正文，补失败仍INCOMPLETE及脱敏断言。|
|B10|medium|patch|room专属创建/修改路径没有STORE_BUSY的实际持锁拒绝及UI恢复验证。加独立连接持写锁使事务实际超时，验证503、零业务/审计改动、释放后成功；JS503草稿/控件/主动重试。|
|E1|low|reject|与B1相同已证实超大ID舍入边界，独立裁决后同样按低频低影响拒绝，避免为不可达自增规模加入无损JSON层。|
|E2|medium|patch|与B2相同已接受CR/LF被编辑器更改，独立裁决后合并直接修补与往返断言。|
|E3|medium|patch|与B6相同畸形冲突数据在catch内抛错，独立裁决后合并错误结构验证。|
|V1|medium|patch|预验证把显示end换为start，17项JS仍过，浏览器也只匹配标签。直接补不同起止的精确文本值，在真实DOM核对。|
|V2|medium|patch|其他发现经父流程读两刷新catch和blocked确认：覆盖专属登录说明，和B5同根，独立裁决后合并。|

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs`，新增实际处理器关键错误恢复回归。
- 新功能真实浏览器1280x800及390x844正常/拒绝路径、登录退出和既有关键流程；精确DTO与纯文本，无页面横向溢出。
- 矩阵及Code Map中的并发、故障与持久化验证须实际执行；保存原始结果，不以计划替代结果。

## 本轮接受结果

139项唯一Python、141项JS及真实HTTP/浏览器验证通过，8项修补闭环，4项low reject有理由，0defer。AI技术接受；[最终核验](../../docs/evidence/story-3.1-review-fixes/parent-final-qa.json)。

## Epic 3 复盘后修补

本卡完成后重新打开，8组共享修补按实际状态关闭。208 Python/376 JS和双视口管理/审计验证通过；最后独立复核受429限制未完成，按open item披露。[最终核验](../../docs/evidence/epic-3-followup/verification.md)。不改写本卡首次验收指标。
