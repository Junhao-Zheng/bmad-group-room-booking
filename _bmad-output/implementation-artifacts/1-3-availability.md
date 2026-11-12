---
title: '按时段和人数找到可用房间'
type: feature
created: '2026-11-12'
status: in-progress
route: dispatch
baseline_commit: ea3fba136e8b6c3cbd5bc373c167a8527376981f
story_key: 1-3-availability
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-1-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 1.3 — 按时段和人数找到可用房间

<frozen-after-approval reason="用户已授权完整实施；沿用上游基线，非额外人工批准">

## Intent

**Problem:** 成员需要按将来时段和人数找出可用房间，以便选择资源。
**Approach:** 在目录和日程基础上提供查询API与中文表单。追踪FR-06/09/10/11/22、NFR-03、ADR-02/03/06、UX-DR4/9/10。仓库 `/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking`。

## Boundaries & Constraints

**Always:** 服务端复核身份并使用同一t；时间人数规则与后续创建共用；半开相交包括booking/block；正确空结果和非法输入有区分。
**Never:** 不实施预约写入、管理取消或撤销停用；不将查询结果视为保留时段；不操作Git/远端。

## I/O & Edge-Case Matrix

|场景|输入/状态|输出/行为|错误|
|---|---|---|---|
|AC-1.3-1|未来同日30min—4h、正整数人数|GET /api/availability?start&end&attendees返回容量够、无未取消booking/block重叠的Room列表；name/location/id排序|匿名/到期401|
|AC-1.3-2|start=t、end<=start、超过t+30天、跨日、非半点、无效日期/格式|400及字段错误，严格北京YYYY-MM-DDTHH:MM；30min/4h/30天等号合法|午夜00:00跨到下一日也拒绝；禁止500|
|AC-1.3-3|0/负/小数/布尔/前导零/Unicode数字、合法>1000或上万位正整数|非法400；任意合法>1000是200空，不先转巨大int|不得绑定超SQLite范围人数|
|AC-1.3-4|10房间1000预约固定负载|10认证客户端20次预热200次测量；全部正确且零错误；nearest-rank P95<=1000ms|保存全部样本与环境；无测量不得宣称通过|

</frozen-after-approval>

## Code Map

- domain.py提供纯时间输入与预约窗口校验，输入时间严格固定长度、ASCII数字、:00/:30，无秒/时区后缀；UTC存储，Beijing同日判断，now<start<end<=now+30*86400，1800<=end-start<=14400。保留block后续可复用解析但不提前业务实现。
- 查询人数单独解析canonical ASCII正整数字符串；服务可接纯int但bool/float拒绝。超过1000先安全判断并返回空，不对超长字符串int()。JSON预约未来须用严格int解析，不能借此接受JSON数值字符串。
- services.availability(actor,start,end,attendees)：复用短只读事务、_require_actor，捕获同一个t。先验证时间/人数再查询Room；NOT EXISTS选择未取消预约与停用的半开重叠；容量与稳定排序精确合同。只返回Room，不附额外数据。
- web.py新增认证GET适配器；home.html提供start/end datetime-local(step1800)/attendees(min1 step1)有label表单，明确北京时间及查询不锁资源。现有目录/日程/登录退出保持。
- 新独立作用域availability.js，或抽取直接复用的通用查询助手，避免修改现有协议；等待/空/字段错误/失效重新登录/网络超时与条件保留清楚；textContent、20秒覆盖响应正文、finally恢复控件。
- 新tests/test_availability.py，复用合成夹具/固定Clock，不继承已有test类；测边界、容量相等、半开相邻、跨日停用、取消释放、精确DTO、超长人数与权限。
- 可复跑真实性能脚本和结果是本故事交付；准备资料在仓库外 `/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/performance_draft.py` 与 `verify_nfr_draft.py`，只借用需要的HTTP客户端/固定server/seed性能组件并核对，不能把未来尚未实现的一致性调用合入本故事脚本。固定10房间1000预约包含历史/将来/取消记录，槽必须一致；独立库独立账号，安全退出清理；200样本与20预热都保存，正确性对独立fixture预期，性能包含HTTP完整读取。

## Tasks & Acceptance

- [ ] domain/services/API完成正常及拒绝路径，复用身份/只读事务/错误封装。
- [ ] UI在1280x800与390x844可查询、空/错误/等待/失效清晰、无横向溢出。
- [ ] 运行Python全量与JS/浏览器关键回归；实际验证新表单与旧登录退出/日程。
- [ ] 运行固定负载真实HTTP性能采样并保存原始数据、环境、nearest-rank计算；README给复跑入口。

## Implementation Notes

1.2已交付精确日程DTO、半开日期与只读快照。维持业务无写接口，查询不泄漏预约私密字段。

## Spec Change Log

## Review Triage Log

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全部通过无skip。
- `node --test tests/test_*js.cjs` 已有与新查询超时回归。
- 真实浏览器桌面/手机运行新查询正常/空/错误、现有登录退出与日程。
- 独立真实HTTP性能脚本20预热+200测量，所有响应正确、零错误、P95<=1000ms，全部样本保存。
