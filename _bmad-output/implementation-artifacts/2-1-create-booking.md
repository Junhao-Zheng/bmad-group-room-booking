---
title: '提交有效且不冲突的活动预约'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: 85263cf6526ea9dab8c359aa59ae04cccc060a9e
story_key: 2-1-create-booking
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-2-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 2.1 — 提交有效且不冲突的活动预约

<frozen-after-approval reason="用户授权完整实施，依规划推进；非人类逐项批准">

## Intent

**Problem:** 成员在找到可用房间后，需填写活动并获得确定的预约结果。
**Approach:** 创建预约与原子审计。追踪FR-08—11/21/22、NFR-01/02/04、ADR-01/02/03/06/07、UX-DR5/9/10。项目根为本故事文件所在仓库。

## Boundaries & Constraints

**Always:** 遵循架构事务、权限、DTO及安全错误合同。
**Never:** 不实现管理员取消/停用撤销、不删历史、不操作Git/远端。

## I/O & Edge-Case Matrix

|场景|输入/状态|行为|错误/验证|
|---|---|---|---|
|AC-2.1-1|合法room_id,title,purpose,attendees,start,end,intent_key|POST /api/bookings→201单层data={booking:BookingFull,replayed:false}；一组连续槽、一条booking.created审计|全部精确DTO键和null；活动文本纯文本|
|AC-2.1-2|strip空/超长title-purpose、非int/非正人数、JSON数字字符串ID、时间各边界、超容量|复用查询同时间规则；字段400，容量409 CAPACITY_CONFLICT，不存在房间404|不产生记录/槽/审计；超大ID、无法编码文本不能500；权限先于参数|
|AC-2.1-3|同室booking/block重叠；首尾相邻；不同房间|重叠409 OCCUPANCY_CONFLICT；相邻/异室成功；20独立成员同时同槽恰1x201+19x409|最终1条记录、完整槽、一条创建审计；共享conflicts不含ID/人数/用途/账号|
|AC-2.1-4|audit_writer注入异常或提交故障|500安全提示，整个业务和槽回滚；无成功响应|UI保留输入；所有POST有Origin/CSRF；真实失败不占意图key|

</frozen-after-approval>

## Code Map

- 复用auth Actor、db.write_transaction与1.3时间纯规则；JSON ID/人数须type(value) is int，不能用query_attendees截断人数。写锁内重新读真实会话/角色/显示名，统一取一次t。
- schema.sql加入架构audit_events及db必需列检查，初始化保留旧数据/user_version1。独立audit_writer(conn,event)只INSERT，按架构完整事实快照，测试可注入故障，生产无HTTP后门。
- services.create_booking：规范化→房间/窗口/容量/占用检查→业务和完整槽INSERT→一次审计→COMMIT；仅明确槽/意图唯一冲突映射409，其余异常安全500。成功后才响应。DTO/共享与admin冲突白名单严格遵守架构。
- 当前交付新建；2.2交付可靠重放。本次保存成功key与规范化六字段JSON，重复key暂受控409；README明确此增量未交付可靠重试，不提前实现2.2意图编辑/重放逻辑。
- 首页 `/` 从可用房间结果选择资源后填写title/purpose，沿用查询时段和人数。随机32字节新key；等待时禁输入/按钮，成功显示编号/时段，冲突保留输入，未知结果不得声称失败或自动重发。动态文字textContent。保留查询/日程/认证能力。
- 新tests/test_create_booking.py及隔离真实Waitress8线程HTTP验证器；20不同成员/key同槽竞争，检查完整最终DB及审计。可参考外部work/verify_nfr_draft.py的通用HTTP部分，不导入未来未实现调用。

## Tasks & Acceptance

- [x] 创建服务/schema/审计/DTO及首页表单可用；未提前实现实验目标。
- [x] 矩阵全部实际通过，原始证据已保存，README 已更新能力与复跑命令。

## Implementation Notes

无新增人类意图缺口；仅在隔离测试库写入，代码及schema增量可回退；涉及服务、DTO、审计、路由、前端和验证脚本。

## Spec Change Log

## Review Triage Log

|编号|裁决|处置|核对证据与理由|
|---|---|---|---|
|B1|medium|patch|查询未完成时仍可提交已选预约；两个finally独立恢复同一批控件，确可提前解锁或永远禁用。提交入口检查查询busy，覆盖两个操作顺序及结束后的控件状态。|
|B2|medium|patch|未知写入结果把只读查询也永久禁用，妨碍继续核对房间。恢复查询控件，仅保留创建与选房guard，输入仍保留。|
|B3|medium|patch|缺字段的2xx成功体能显示undefined并宣称成功；未知错误码也被当成明确失败。以现有API合同检查最小展示字段/包络和已知错误码，不合格走现有unknown分支。|
|B4|low|reject|JS确不能精确表示超2**53的整数；但创建流程自动分配房间ID，无ID导入入口，实际到达该值需约9千万亿次创建或库外改写。现有课程使用不遇到；无损数字协议会改变公共合同，拒绝增加复杂性并记录边界。|
|B5|low|patch|选择新房间只改feedback.textContent，确残留上一错误的alert/error。直接恢复status及无error样式。|
|B6|low|patch|多个选房按钮可访问名相同；直接加包含名称/地点的aria-label，不改业务。|
|B7|low|reject|原始SQL插入带空白空对象确可越过after_json!='{}'；唯一应用writer总是紧凑JSON并接收固定非空快照，正常调用不会到达。修改既有表约束需要迁移与新分支，对不受支持库外写入不增加此复杂性。|
|B8|medium|patch|现浏览器abort只覆盖未送达，缺已提交后响应丢失。增加fetch成功再丢弃响应、同页不重发、DB一记录/完整槽/一审计断言；可靠原key重放仍留2.2。|
|B9|medium|patch|单次clock计数不能证明在取得锁后采样；推进取锁前后时间并断言会话或开始边界拒绝、零业务变化。|
|B10|medium|patch|伪造admin Actor仅走成功路径，无法发现角色未刷新导致冲突白名单泄漏；加入真实member但Actor admin的冲突断言。|
|E1|medium|patch|独立边界层确认与B1相同的查询/预约控件恢复竞争，归并同根修补但保留本条裁决。|
|V1|medium|patch|预验证mutation把clock移到锁前仍12测试通过；信任评审证据，补会话到期/开始时刻跨锁边界，归并B9。|
|V2|medium|patch|预验证mutation沿用actor.role仍12测试通过；信任证据，补冲突路径精确成员白名单，归并B10。|
|V3|medium|patch|预验证mutation去cancelled过滤仍12测试通过；补已取消booking和已撤销block覆盖新建成功、历史保留、仅新增槽与审计。|

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs` 查询/认证与新增表单关键回归。
- 真实HTTP20成员竞争，1成功19冲突，最终存储完整且恰一次审计；故障注入全部回滚。
- 真实浏览器1280x800/390x844创建成功与冲突、普通Unicode/XSS文本及原查询登录退出验证。

### 实施验证记录（2026-11-12）

- 78 项 Python、18 项 JavaScript 全量通过，无 skip；真实 HTTP 20 个独立成员竞争得到 1×201 和 19×409，最终 1 预约 / 4 连续槽 / 1 创建审计。
- 审计写入前后失败、实际 COMMIT 执行故障、首槽后的槽主键失败均全部回滚；真实 HTTP 故障 key 重启后可用。
- 1280×800 / 390×844 真实浏览器完成创建、冲突输入保留、普通 Unicode/XSS 纯文本、未知网络结果，以及原登录/退出/查询回归。
- 细节、限制、命令与原始证据见 [Story 2.1 验证记录](../../docs/evidence/story-2.1-verification.md)。本增量仍不支持可靠重放，未实现后续实验目标。


主代理最终验收：81项Python、24项JavaScript全量通过，无skip；reviewed浏览器1280×800/390×844通过，已视检手机丢响应后的可读查询及保留输入。HTTP初版20成员竞争1成功19冲突及业务回滚证据有效，评审期间服务端业务代码未改；新浏览器直接验证提交后丢响应最终1预约/2槽/1审计。全部12条保留发现已关闭，无high/medium延期。最终记录见 [评审证据](../../docs/evidence/story-2.1-reviewed/)、[逐条裁决](../../docs/evidence/reviews/story-2.1-review.md)。
