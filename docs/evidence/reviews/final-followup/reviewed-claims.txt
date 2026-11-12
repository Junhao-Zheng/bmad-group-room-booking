---
title: '管理页跨面板确认与结果一致性修补'
type: bugfix
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: abb72911742e59d3aa5d60c28e1f60ca384add13
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Epic 3 完成后修补

<frozen-after-approval reason="用户已授权完整实施与检查；本规格由AI拟定，不冒充人工验收">

## Intent

修复最终复盘证实的管理页确认/结果失真。涉及3.1、3.2、3.4，保持12条业务故事。无待人决定的新规则，无迁移或外部副作用。

## Boundaries & Constraints

只改管理页及必要验证；后端DTO/事务/业务规则不变。未知结果不得自动重试。原证据不得覆盖。不上Git、不修改其他文档或故事状态；父流程统一处理。安全整数以拒绝不安全操作/展示实现，不引入无损JSON协议。

## I/O & Edge-Case Matrix

|AC|Given / When|Then|
|---|---|---|
|R1|页面禁JS或rooms.js加载失败时尝试房间提交|写入字段/按钮初始禁用，有不可用提示，无原生GET；脚本完整绑定后可用|
|R2|房间保存网络失败/超时/坏响应|草稿保留、确认取消；提示先刷新核对再重新勾选；无自动重试|
|R3|停用已核对后同页房间保存成功|旧确认失效；明确要求刷新房间选项，刷新成功后才可再次确认。若停用已发出，不取消请求或掩盖其真实结果；刷新失败保持需刷新状态|
|R4|另一面板先报AUTH_REQUIRED/FORBIDDEN，随后房间保存/停用创建返回合法成功|保留成功事实及重新登录说明，列表仍清空、控件仍禁用；反向顺序也成立|
|R5|初始房间data-room或目录刷新含不安全ID，尝试编辑|拒绝发出舍入目标POST，安全编号仍正常；畸形初始数据不使其他保护失效|
|R6|审计事件或before/after快照含不安全整数|拒绝展示错误对象，有查询失败反馈，保留筛选；普通合法记录仍正常|
|R7|填写停用原因及核对摘要|清楚注明所有已登录成员可见，不新增权限或修改DTO|
|R8|停用创建结果未知后准备重试|明确先核对包含已撤销历史，重提交是新建而非原请求重放；仍需再次确认|

</frozen-after-approval>

## Code Map

- `booking_app/templates/admin.html`：房间缺fieldset保护；参照block-fields/script-unavailable。原因label补范围。
- `booking_app/static/rooms.js`：bindEdit初始JSON缺校验；roomShape/submit防线；savedMessage在blocked前设置但不得重新加载私密数据；保存成功广播目录变化。unknown分支清确认。
- `booking_app/static/blocks.js`：既有admin-auth-lost事件/identityError；创建已确认结果须保留；目录变更令选择标签过期并要求显式刷新，不能仅取消勾选又立即允许旧标签确认。refresh现已更新三个select；保留失效状态直至成功。summary含可见范围。
- `booking_app/static/audit.js`：snapshotShape/eventShape数字校验。
- `tests/test_rooms_js.cjs`、`tests/test_blocks_js.cjs`、`tests/test_audit_js.cjs`：真实脚本harness，补跨面板时序及不安全ID。现有Python页面断言随模板调整。
- `scripts/verify_audit_browser.py`、房间/停用现有browser runner可参考；独立新增最小真实浏览器验证也可。保持临时库、源指纹、失败先置INCOMPLETE、不泄漏临时凭证。

## Tasks & Acceptance

- [x] 上述4产品文件：完成R1—R8并覆盖相应测试。
- [x] `docs/evidence/epic-3-followup/`：保留实际定向测试输出和R1—R8对应说明。
- [x] 在真实Chrome桌面/窄屏运行正常编辑→停用确认失效→刷新重确认及禁JS/脚本失败，保存截图与前后源码SHA。父流程另跑全量与审计浏览器。

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

`node --test tests/test_rooms_js.cjs tests/test_blocks_js.cjs tests/test_audit_js.cjs`；相关Python模板测试。真实浏览器使用本机Chrome `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` 与 `work/browser-tools/node_modules`。不得将仅mock检查冒充浏览器执行。

## 初次实现核验

独立实现调用实际产出4个产品文件、定向测试及真实双视口浏览器证据；末尾报告阶段遭429/重试上限失败，不能冒充完整成功回合。父流程依据差异、实际输出与源码哈希自行核验，不据缺失的最终回复接受。定向与浏览器初始取证路径见 docs/evidence/epic-3-followup；前两次浏览器断言错误已保留INCOMPLETE，第三次PASS。

## 最终结果

技术矩阵R1—R8通过；208唯一Python/376 JS，双视口管理和审计PASS。独立三镜头均429失败；父流程复核无新阻断发现，独立复核留open item而非假通过。[记录](../../docs/evidence/reviews/epic-3-followup-review.md)。
