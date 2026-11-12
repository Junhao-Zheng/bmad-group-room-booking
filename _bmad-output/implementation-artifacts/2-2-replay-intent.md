---
title: '确认重复提交和网络重试结果'
type: feature
created: '2026-11-12'
status: ready-for-dev
route: dispatch
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
