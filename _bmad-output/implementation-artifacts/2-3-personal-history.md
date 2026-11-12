---
title: '查看自己的预约及状态'
type: feature
created: '2026-11-12'
status: done
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

- [x] 完整实现本故事用户路径。
- [x] 验收矩阵逐项有执行断言；新测试不能通过继承已有test类重复计数。
- [x] 实际运行所列验证，保存原始证据。
- [x] 更新README当前能力和复跑命令、证据入口；使用独立临时库，凭证不进仓库。

## Implementation Notes

遵守上游合同，技术选择为AI实施。

- 2026-11-12：新增 `my_bookings`、`booking_detail` 只读服务及精确 API；服务复核会话、当前角色，统一查询时刻，状态过滤与 start/id 倒序。新增 `/my`、顶栏导航及纯文本详情、错误/失效/空态和键盘流程，没有提前实现取消命令。
- 独立 `history_fixtures.py`、9 项直接继承 `unittest.TestCase` 的新增 Python 测试和 12 项真实 JS 处理器测试。新增隔离浏览器验证器，更新旧浏览器顶栏键盘顺序。
- 完整执行证据与 AC 映射：[Story 2.3 验证记录](../../docs/evidence/story-2.3-verification.md)。100 项 Python、44 项 JS 均通过，无 skip；1280×800/390×844 历史页面与原创建/重放浏览器均通过；真实 20 人创建竞争、20 次同意图重放、故障回滚及进程重启回归通过。状态为 review，交由父工作流评审；这不是人类或教师验收。

## Spec Change Log

## Review Triage Log

|编号|裁决|处置|核对证据与理由|
|---|---|---|---|
|B1|low|reject|正64位ID的JSON精度边界确可构造，但正常自增到2^53在本地课题组使用中不可达，项目没有导入/手填ID路径；增加无损JSON解析/多处类型分支不属于直接更正，按低频低影响规则拒绝，不把API范围改小。|
|B2|medium|patch|列表是上次读快照，详情重新取t；正常跨开始/结束时刻会显示不同状态却未说明。给列表和详情补充快照及主动刷新说明，沿用“查看预约”按钮，不增加轮询或新合同。|
|B3|medium|patch|详情401清空两面板但仅详情显示失效，列表保留旧成功数量。两面板都改为失效提示，焦点留在发起失败的区域。|
|B4|medium|patch|Chrome在禁用已聚焦提交按钮时把焦点移至BODY；成功后没有恢复。解锁后恢复到提交按钮或结果标题，并以真实键盘流程断言下一次Tab位置。|
|B5|medium|patch|第二个API请求时Clock已在会话到期时刻，不能进入被测服务边界；每次重设时刻并断言列表/详情各自命中注入边界。|
|B6|medium|patch|并发写发生在fetchall后，旧字段来自已物化行而非事务快照证据；将写插在会话SELECT完成后、业务SELECT之前，断言新旧快照分离。|
|B7|medium|patch|UI只断言行数，另发API取得正确ID不能证明页面显示正确行。直接断言渲染ID/顺序/状态并保存页面实际响应，和V1同根。|
|B8|medium|patch|列表与详情共用序列化器，相等和键集合不能独立验证值。用固定夹具事实明确写出代表性完整DTO，包括时间/人数/取消人等，而不复用被测DTO来算期望。|
|B9|medium|patch|父流程用真实Chrome复现只kill Node后1秒仍有4个本次浏览器进程；见独立探针。为验证器自己启动的进程创建独立进程组，异常/超时清理该组，Waitress终止超时强制回收；只处理本次PID/组并补失败路径验证。|
|B10|low|patch|历史验证器只有run_id，没有源码/夹具指纹；直接补实际app/driver/依赖脚本hash与运行版本，成功证据绑定本次版本。|
|E1|low|reject|与B1同一已证实精度边界，保留独立裁决；正常自增数据不可遇、无ID导入路径，额外无损解析增加维护复杂度，按低影响拒绝规则不扩展。|
|V1|medium|patch|预验证mutation把in_progress映射到ended仍通过现12项JS；浏览器只数一行也漏检。补真实渲染记录/状态/顺序，和B7合并修补但不合并本条裁决。|
|V2|medium|patch|预验证mutation将显示结束时间改为开始时间仍12项JS全过。以独立label-value映射逐字段断言已取消/未取消详情，使用不同起止时间。|
|P1（修补阶段）|medium|patch|元数据采集新增在INCOMPLETE之前，缺Playwright包会留下旧PASS；父流程定位后同轮修复，并以真实缺依赖回归验证先失效再安全失败。|


## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs`，新增实际处理器关键错误恢复回归。
- 新功能真实浏览器1280x800及390x844正常/拒绝路径、登录退出和既有关键流程；精确DTO与纯文本，无页面横向溢出。
- 矩阵及Code Map中的并发、故障与持久化验证须实际执行；保存原始结果，不以计划替代结果。

## 父流程最终验收

全量104项Python、49项JS通过且无skip；三条AC有独立值/边界/权限断言及真实1280/390浏览器证据。父流程核对本轮全部源码/辅助脚本SHA，并检查手机长文本截图。见[最终复验](../../docs/evidence/story-2.3-reviewed/verification.md)。实现调用2次（初次+同上下文修补），三层独立评审；初审13条，修补中另发现P1，共14条，12条已修复、2条低影响边界按规则拒绝，无高/中风险遗留。先由build置spec done/sprint review，再由父流程完成明确验收置done；不是人工/教师批准。

## 完成后返工 R2：验证器退出竞争

2.4验证期间复现原history浏览器清理helper在目标组仅剩Z状态时killpg(0)偶发PermissionError；100次快速退出探针有原始状态证据。作为真正的完成后返工重开2.3，限制修补在僵尸状态确认及活组权限错误拒绝；与2.4共用本次实现调用和评审，不额外算一次代理派发。证据见[2.4验证记录](../../docs/evidence/story-2.4-verification.md)。

## 本轮接受结果

121项唯一Python测试、86项JS及真实HTTP/双视口浏览器通过。Story2.4的16项评审已关闭，0defer；2.3验证器清理返工已闭环，单独保留完成后返工事件。最终[证据](../../docs/evidence/story-2.4-review-fixes/parent-final-qa.json)。AI技术接受，不是人类或教师验收。
