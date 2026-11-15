---
title: 一次确认批量取消冲突预约并停用
type: feature
created: 2026-11-15
status: done
route: dispatch
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="D-015/016/021，U-39批准完整方案">
## Intent

管理员一次填写原因，预览并明确确认受影响预约后，在一个事务取消与维修时段冲突的已批准预约并创建停用。保留每条取消事实和全部历史；撤销停用不恢复原预约。

## Boundaries & Constraints

仅管理员；停用维持未来30天、半点、可跨日。只取消同房间实际重叠场次；周期其他周不受影响。待审批申请不自动拒绝；与其他有效停用冲突仍失败。取消/槽/停用/审计全成全败；确认后新增的预约不能悄悄扩大取消范围。

## I/O & Edge-Case Matrix

|情形|结果|
|---|---|
|多个冲突预约预览→明确确认|一次原因取消所列预约并设置停用，各对象分别审计，预览凭据关联同次确认|
|相邻/不同房间/周期其他场|不取消、不修改|
|预览后新增/删除/状态改变或输入改变|409要求重新预览确认，无部分取消|
|已有有效停用重叠|拒绝，无论是否同时存在预约|
|确认网络重试、甚至已过预览期限|已成功操作重放同停用及原受影响集合，不重复审计|
|未消费预览到期或非本人admin/篡改|拒绝，不能凭客户端伪造受影响集合|
|第n条审计/停用写入失败|所有预约、槽、取消请求及停用审计回滚|
|撤销停用|仅释放停用，不恢复已取消预约；需要者重新申请|

</frozen-after-approval>

## Code Map

`services.py:create_block/admin_cancel_booking/revoke_block`及`cancellations.py`已有单事务操作；拆事务内原语复用，禁止循环调用公开命令各自commit。`blocks.js/admin.html`有跨表单锁、身份失效清空与草稿恢复。`dto.py/audit.js`严格协议；`db.py/migrate_db.py`显式升级须兼容原库。

## Tasks & Acceptance

- [x] `maintenance.py`和schema v6持久保存管理员绑定的预览摘要、10分钟到期时间、原受影响集合及成功block ID；v1—v5显式备份迁移。
- [x] 预览/确认API在写锁内重新核对身份、窗口、已有停用与实际预约集合；变化要求重新预览，成功凭据可重放。
- [x] 同事务取消目标预约、终结待审取消、释放槽、创建停用和审计；任一故障整体回滚。
- [x] 旧空闲停用和单条管理员取消API保留；管理页新增批量预览确认入口。
- [x] 页面列出具体受影响预约与一次原因；字段修改废止预览，响应丢失保留原凭据供明确重试。移动视口流程通过。
- [x] `test_batch_maintenance.py`覆盖20组审批/确认竞争、故障、漂移、到期、重放、撤销及v5迁移；真实Chrome双视口含周期其他周不受影响。
- [x] 验证事实见`docs/evidence/human-review/maintenance-verification.md`。

**Acceptance Criteria:**
- Given两预约与一无关预约，When预览并一次原因确认停用，Then准确取消两条并创建一条block、无关保留；真实操作者/原因/关联可读。
- Given预览后新审批或首条取消后故障，When确认，Then要求重确认或整体回滚，不静默扩大取消。
- Given维护完成后重试及撤销，When操作，Then原批次不重复、已取消预约不恢复，历史全部保留。

## Implementation Notes

## Spec Change Log

2026-11-15：按U-39获批方案完成schema v6、预览凭据、原子确认、页面和双视口验证。未扩大停用30天窗口，也未把待审申请当作占用。

## Review Triage Log

## Verification

新批量维护、原maintenance/block_revoke/admin_cancel及取消审批定向Python/JS测试；真实浏览器管理员预览确认、学生查取消原因、撤销不恢复。最终全套、独立评审、NFR/重启/全新副本由主流程收口。

2026-11-15：全套Python 260/260、既有JS 414/414；生产SystemClock的Chrome 1280/390均通过预览、两条取消、确认响应丢失后的同凭据重放、撤销不恢复及无横向溢出。没有额外独立LLM评审报告，不将原Epic3评审冒充此故事评审。
