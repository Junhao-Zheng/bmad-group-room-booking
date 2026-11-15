---
title: 一次确认批量取消冲突预约并停用
type: feature
created: 2026-11-15
status: draft
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
|多个冲突预约预览→明确确认|一次原因取消所列预约并设置停用，逐条审计/同批关联|
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

- [ ] `booking_app/maintenance.py`（新增）及schema/显式迁移：服务器持久预览记录绑定actor、规范化房间时段原因、受影响预约事实、到期及成功block_id。token安全随机且存摘要；未消费预览10分钟有效，成功重放随历史保留。预览不是成功维护审计，不暴露口令/会话。选择其他等效服务端绑定设计须记录证据，不能信任客户端任意ID列表。
- [ ] POST `/api/admin/blocks/preview`返回受影响预约及确认凭据；POST `/api/admin/blocks/confirm`只接受凭据和显式确认。先admin/auth/CSRF，锁后刷新，未成功先再校验时间、冲突集合及事实。变化需重预览；已成功先重放，返回当前停用与原取消记录，不覆盖历史原因。
- [ ] 确认事务逐条取消有效冲突booking（含取消待审），终结对应待审取消请求；写block及完整槽、每条取消和停用审计，统一批次可从预览成功记录关联。任一故障全回滚；预约已结束不可被新维护悄悄取消。并发批准先后结果合法，后到审批遇block拒绝。
- [ ] 保留旧`create_block`无冲突创建API与旧单条admin取消；当前管理页面改用预览/确认，避免原拒绝冲突交互挡住新能力。无冲突也可预览后确认；旧API不自动静默取消。
- [ ] `blocks.js/admin.html`显示具体受影响预约、理由、一次确认；任何字段/房间变化使凭据失效，待网络结果不确定时保留同凭据重试；按钮锁/等待/401/冲突/焦点/窄屏明确。用户文本纯文本，admin以外不可读取列表或预览。
- [ ] `tests/test_batch_maintenance.py`及对应JS/HTTP浏览器测试：矩阵、20轮审批对确认竞争、writer中途失败、重复确认、预览后管理员取消/新获批、撤销不恢复、周期只取消一场。适配原维护runner，不以旧冲突拒绝证明新批量通过。
- [ ] `docs/evidence/human-review/maintenance-verification.md`实际输出，更新新维护指引；所有代码留工作区，勿commit/push。

**Acceptance Criteria:**
- Given两预约与一无关预约，When预览并一次原因确认停用，Then准确取消两条并创建一条block、无关保留；真实操作者/原因/关联可读。
- Given预览后新审批或首条取消后故障，When确认，Then要求重确认或整体回滚，不静默扩大取消。
- Given维护完成后重试及撤销，When操作，Then原批次不重复、已取消预约不恢复，历史全部保留。

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

新批量维护、原maintenance/block_revoke/admin_cancel及取消审批定向Python/JS测试；真实浏览器管理员预览确认、学生查取消原因、撤销不恢复。最终全套、独立评审、NFR/重启/全新副本由主流程收口。
