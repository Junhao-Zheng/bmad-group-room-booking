---
title: '确认重复提交和网络重试结果'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: 6ed26f50a70aa652df1796ff6d360240af70ca5c
story_key: 2-2-replay-intent
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-2-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 2.2 — 确认重复提交和网络重试结果

<frozen-after-approval reason="用户授权完整实施，沿用规划；非额外人工批准">

## Intent

**Problem:** 课题组成员需要用原提交意图确认是否成功，以便网络异常不会生成重复预约。
**Approach:** 在已完成依赖2.1基础上交付本故事可操作能力。追踪FR-12/22；NFR-01/04；ADR-04；UX-DR5/10。

## Boundaries & Constraints

**Always:** 服务端授权、严格输入、单事务业务/槽/审计、精确DTO、统一Clock；实际测试和可追踪证据。
**Never:** 不扩充范围外功能或虚构人类/课堂记录；不提前实施实验A目标；不操作Git/远端。

## I/O & Edge-Case Matrix

|验收编号|Given|When|Then|
|---|---|---|---|
|AC-2.2-1|同成员同key同规范化6字段已有成功记录|再次请求含首尾空格等价文本|200同id和当前状态，不新增业务/槽/审计|
|AC-2.2-2|原预约已取消/开始或房间容量已降低|使用相同原意图重试|重放先于新预约规则，仍返回原结果；换实质字段409；跨用户同key不泄漏|
|AC-2.2-3|失败请求或20并发同key请求|修正失败后重试或同时提交|失败不占key；并发全部同id，1条预约1条创建审计|
|AC-2.2-4|浏览器响应丢失|再次点击确认或实质编辑表单|相同内容保留key；编辑生成新key；提交中按钮禁用，未知结果不误称失败|

</frozen-after-approval>

## Code Map

- services.create_booking已保存成功的(user_id,key)和规范化六字段JSON。读取成功意图必须在纯格式规范化之后、当前时间窗口/房间容量/占用规则之前；same payload返回原记录当前BookingFull、replayed=true，200；不同payload409 IDEMPOTENCY_MISMATCH。失败请求无持久key记录；所有分支仍写锁后认证。
- 可复用1.3 beijing_datetime纯解析，但不能用booking_interval先施加当前窗口；保留原创建安全不变量与事务边界。重放之后不调用audit_writer，不能序列化历史时响应缓存；Room/显示名取查询时最新，取消字段取原事实。
- 首页预约提交生成crypto随机32字节键。相同规范化六字段保持key，实质编辑换key；网络结果未知与明确失败分别提示。失败后同内容原key重试；成功后重复点击仍能确认原记录，不自动清空导致重复；新预约需显式开始新意图。
- JS比较规则与后端相容，文本strip须与Python等价（含U+0085/U+001C—1F，不去U+FEFF），纯int人数/ID、固定时间格式。提交期间锁定相关控件避免旧响应标新输入；20秒同时覆盖头/JSON，超时不能声称失败或偷偷换key。
- 测试使用合规直接夹具模拟已取消/开始/降容量历史，不提前暴露取消/管理API。20并发相同用户key每请求独立HTTP客户端，同一登录凭证可复制但CookieJar不得线程共享；最终一id、一条创建审计，1x201+19x200。
- 真实浏览器截断首次成功响应后，原key重试仍原ID；再修改实质字段创建新意图。保留原始网络证据及安全的key哈希/相等性，不输出会话凭证。

## Tasks & Acceptance

- [x] 完整实现本故事用户路径。
- [x] 验收矩阵逐项有执行断言；新测试不能通过继承已有test类重复计数。
- [x] 实际运行所列验证，保存原始证据。
- [x] 更新README当前能力和复跑命令、证据入口；使用独立临时库，凭证不进仓库。

## Implementation Notes

遵守上游合同，技术选择为AI实施。

- `services.create_booking` 在取锁认证及纯格式规范化后读取本人成功意图；比较六字段，返回实时 Full DTO，重放不调用 writer。web 按 replayed 返回 200/201。
- 首页保持原提交意图，支持未知结果和已成功结果的主动确认；规范化实质编辑换键，显式新预约清空表单，提交期间锁控件，20 秒覆盖响应正文。
- 新增 9 项独立 Python 重放验收（未继承旧测试类）；更新实际 JS 处理器回归为 13 项。真实 HTTP 20 同意图并发及进程重启/故障验证、1280×800 和 390×844 浏览器响应截断/重试/新意图验证均已执行。
- 原始记录、命令、矩阵和范围见 [Story 2.2 验证记录](../../docs/evidence/story-2.2-verification.md)。取消、管理与实验 A 目标均未提前实现；历史状态仅通过直接测试夹具构造。

## Spec Change Log

## Review Triage Log

|编号|裁决|处置|核对证据与理由|
|---|---|---|---|
|B1|medium|patch|未知首次结果之后收到500/503/401等只说明此次确认失败，不能据此清除原未知。保留unknown直到确认成功或显式换意图，错误反馈保留核对提示。|
|B2|medium|patch|换意图的首个按键提示原结果未知，下一次按键就覆盖，用户正常输入易漏看。保持已被替换但未确认的旧意图提示，不因继续编辑当前草稿消失；不扩展跨刷新持久化。|
|B3|medium|patch|已确认成功后再次确认断网，反馈退回“可能已成功”并丢编号，属信息倒退。保留当前意图最后确认编号，明确本次当前状态未刷新，不把已知创建写成未知。|
|B4|low|reject|可构造违反服务合同的错误对象被页面接受，但当前服务在同用户key和六字段相等后只取原记录，DB唯一约束及测试保证身份；无已证实正常路径会返回另一预约。新增前端六字段/ID镜像业务校验增加重复逻辑，不补不可达的错误服务响应。|
|B5|medium|patch|DTO刷新房间名称/地点，但成功确认仍显示选房时快照。直接用成功DTO刷新确认条件文字，同时保持规范化意图内容不变。|
|B6|low|reject|正常服务端规范化和schema已排除非法目的/标题NUL/容量，当前页面检查结构及必要展示类型即可。穷尽客户端重复域验证不修复已证实用户故障，增加维护分支，拒绝。|
|B7|medium|patch|现真实浏览器只覆盖提交后丢响应；补首请求未到达而后同key明确重试201及最终一次创建证据，防止只接受200重放的回归。|
|B8|low|reject|客户端实质编辑必换key，正常同时重试载荷相同；已有真实同key20并发、逐六字段mismatch及同一BEGIN IMMEDIATE覆盖核心风险。不同载荷并发是额外防御场景，未定位实际缺陷，不增加新的复合竞争harness。|
|B9|medium|patch|新增逐次网络证据可在browser-results仍是旧PASS时部分覆盖；开始先写带run_id的INCOMPLETE，失败保留安全失败状态，成功才发布PASS，防混用。|
|B10|low|patch|重放脚本确复用server/clock/writer/storage/fixture，当前只记自身和app哈希不足定位验证器；直接补所导入验证辅助源码哈希。|
|E1|medium|patch|边界层确认B1同根问题；保留逐条裁决并合并修补未知结果生命周期。|
|V1|medium|patch|预验证mutation删attendees签名仍27项通过，因为测试每步恢复默认值导致多字段同时变；逐字段独立fresh baseline并断言恰一个业务字段差异。|
|V2|medium|patch|预验证所有状态都显示待开始仍27项通过；四态分别断言完整对应中文状态，而不只确认前缀。|
|P1|low|patch|父代理检查取消后复用测试在固定NOW下写cancelled_at=NOW+1，随后仍用旧NOW创建；推进测试时钟到取消时刻，保证夹具没有未来取消事实。|

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs`，新增实际处理器关键错误恢复回归。
- 新功能真实浏览器1280x800及390x844正常/拒绝路径、登录退出和既有关键流程；精确DTO与纯文本，无页面横向溢出。
- 矩阵及Code Map中的并发、故障与持久化验证须实际执行；保存原始结果，不以计划替代结果。


主代理最终验收：91项Python、32项JavaScript全量通过，无skip；两视口真实浏览器覆盖提交后丢响应→200重放与未送达→201创建，两者最终均恰一次业务/审计。20同意图并发1×201+19×200，重启/回滚通过；应用及验证辅助源码hash已独立比对一致。全部11条保留发现关闭，无high/medium延期。修补期间发生1次传输中断，原代理恢复同一修补任务；逻辑修补1轮、实际实现/修补调用3次（含恢复调用），不把连接错误当产品缺陷。
