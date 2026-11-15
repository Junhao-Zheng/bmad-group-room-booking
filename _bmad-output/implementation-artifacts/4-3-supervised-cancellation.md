---
title: 学生取消申请由本人导师确认
type: feature
created: 2026-11-15
status: done
route: dispatch
baseline_commit: 34443922ad2dd2df24e2a8f35cb01d8c83a7b59f
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="D-010/011/014，U-39批准方案">
## Intent

学生提出已获批预约的取消申请，自己的导师在预约开始前确认才释放房间。改期先取消后重新申请，无原子改期。管理员带原因结束前直接取消保留；导师自己的预约开始前直接取消。

## Boundaries & Constraints

待取消审核仍占用；确认时以写锁后的服务器时钟与可信导师关系判断。学生申请在开始前提出、导师确认也必须开始前；不因先申请而延长期限。当前单次预约和后续周期每场一致。保留终态、历史、幂等及原子审计；不自动发消息、不恢复旧预约。

## I/O & Edge-Case Matrix

|情形|结果|
|---|---|
|学生本人未开始预约申请取消|生成待确认请求，槽不变；重复请求返回现有待审|
|本人导师开始前确认|一次取消、全部释放、申请状态及审计同事务|
|其他导师/admin代确认、他人申请|拒绝且不泄详情、不改数据|
|申请后到start等号再确认|拒绝，预约仍有效；管理员特殊干预不受学生期限替代|
|导师拒绝取消|说明原因、预约仍占用；学生之后可重新申请，旧拒绝历史保留|
|管理员先直接取消/并发确认|单一终态、保留首次取消事实；旧待确认请求显示已被管理取消，不再次释放/记取消审计|
|审计故障/重试/重启|失败整体回滚，重放不重复转换，历史及当前请求状态持久化|

</frozen-after-approval>

## Code Map

`services.py:member_cancel_booking/admin_cancel_booking`已有事务取消与终态重放；4.2学生路径已拦截。`applications.py`已有导师授权、DTO及审批页可复用。`history.js/my.html`本人取消按钮、`applications.js`导师入口需可操作。`dto.py/audit.js`严格式兼容旧事件。

## Tasks & Acceptance

- [x] `booking_app/cancellations.py`及schema/显式迁移：取消请求id/booking_id/requester_id/supervisor_id/created_at、状态、decided_at/by/reason，单预约最多一个待审请求；拒绝后可重新申请，不覆盖旧记录。导师取预约可信归属且复核现绑定，不接受客户端指定审批人。
- [x] `web.py`新增POST `/api/bookings/ID/cancellation-requests`、GET `/api/cancellation-requests`、POST `/api/cancellation-requests/ID/approve|reject`。列表学生本人/导师本人学生/admin全部；admin仅可读，不代批。approve空对象，reject非空reason；id及角色验证沿用原协议。
- [x] 现有学生本人`/cancel`路径返回同一取消申请结果或明确拒绝改走新入口，绝不能直接释放。导师/admin自己的旧本人取消路径仍开始前直取消。UI按角色使用正确入口；管理员管理取消保持结束前原因必填。
- [x] `services.py`管理取消与新确认共用事务内取消原语（不嵌套公开事务命令）；管理取消原子终结未决请求为superseded，不能出现永久待批错误提示。确认请求再次请求返回首事实，拒绝后批准不得复活。
- [x] 审计新增cancellation_request.created/approved/rejected/superseded，目标cancellation_request；预约取消记录真实teacher执行者。不得写学生自己已取消假事实；旧booking.cancelled_by_member快照仍可读。业务/请求/槽/全部对应事件共同提交。
- [x] `templates/my.html/applications.html`、`history.js/applications.js/audit.js`：申请待确认仍占用文字，导师确认/拒绝，学生查看处理结果；待审/被拒/过期明确；个人详情仍能查取消操作者与时间。共享日程不暴露取消申请详情。
- [x] `tests/test_supervised_cancellation.py`及受影响契约/JS/HTTP测试：矩阵、时间等号、20轮导师确认对admin取消、writer中途失败、旧数据及幂等。浏览器覆盖学生→导师确认实际释放；拒绝/到期由定向测试覆盖。
- [x] `docs/evidence/human-review/cancellation-verification.md`保存实际证据。

**Acceptance Criteria:**
- Given已批准预约，When学生申请再由本人导师确认，Then待审占用、确认后释放一次，取消事实真实且按权限可读。
- Given开始边界、越权者及竞争管理取消，When操作，Then期限和权限成立，无覆盖首事实、重复审计或半释放。
- Given取消后另申请新时间且新时段冲突，When审批，Then新申请失败且不恢复旧预约。

## Implementation Notes

## Spec Change Log

2026-11-15：学生取消需本人导师开始前确认、管理员特殊干预及待审请求终结均按批准方案实现；完成状态对应提交597a091及后续整合回归。

## Review Triage Log

## Verification

运行新取消审批测试、test_member_cancel/test_admin_cancel/相关审计及JS测试。实际浏览器学生申请→导师确认，记录最终槽及审计。最终全套由主流程执行。

实际验收见`docs/evidence/human-review/cancellation-verification.md`；最终完整回归260项Python、414项JS及Epic4双视口浏览器通过。未取得教师评审，不把AI测试等同课堂验收。
