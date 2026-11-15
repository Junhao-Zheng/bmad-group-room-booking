---
title: 学生申请与本人导师审批
type: feature
created: 2026-11-15
status: draft
route: dispatch
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="D-006/007/012/013/018与U-39批准方案">

## Intent

学生提交申请不占房；本人导师批准才占用。导师自己和管理员原有直接预约保留，学生无法旧API绕过。共享显示所属导师，详情学生本人/本人导师/admin可见。普通预约结束≤当前+7天、半点同日30分钟至4小时。

## Boundaries & Constraints

沿用分层单体、服务写锁后刷新身份与时钟、唯一占用槽、CSRF/Origin、持久幂等及保留历史。学生归属来自管理员绑定，不接收用户伪造归属。无通知、自注册、换导师及真实部署。待审≠旧pending（已生效待开始）。本卡单次，周期4.4、取消确认4.3紧随实现；本卡先阻止学生直接释放已获批预约，不伪造尚无审批入口已可取消。

## I/O & Edge-Case Matrix

|输入/状态|输出|
|---|---|
|已绑定学生合法申请|201申请编号、awaiting_approval，零reservations/slots|
|申请同意图重试/不同payload|同ID当前状态/409；不会重复申请或占用|
|本人导师批准|事务重新查关系/时间/容量/冲突，创建一条预约、完整槽及真实审计|
|其他导师/admin代批/伪造身份|拒绝，不泄露他人详情、不改数据|
|待审重叠申请/竞争批准|可并存待审；最多一个批准取得占用，冲突保留待审|
|导师拒绝/学生撤回|原因可见/本人撤回；零槽保留历史，越权拒绝|
|首次批准已开始、降容量、审计失败|拒绝或全回滚，无半成品；合法成功路径必须保留|
|旧学生直接创建/取消API|新操作403提示走审批；旧成功意图和已取消结果合法重放保留|
|旧历史无归属/管理员安排|不猜导师；明确显示历史未绑定/管理员安排|

</frozen-after-approval>

## Code Map

- `services.py:create_booking/_BOOKING_DETAIL_SELECT/booking_detail/schedule`现全部是生效预约；保留reservation语义。新`applications.py`服务可复用事务内助手，禁止嵌套调用公开事务命令。
- `schema.sql/db.py/scripts/migrate_db.py`：4.1已schema2；新schema版本及显式兼容升级须保留旧事实。
- `domain.py:validate_booking_window`当前30天；停用校验独立保持30天。
- `dto.py`、`booking.js/history.js/schedule.js/audit.js`严格字段；所有调用者和fixture同步。
- `web.py`薄适配、`templates/home.html/my.html/base.html`；新增`applications.html/applications.js`提供本人记录及导师审批入口，admin可看全部不代批。

## Tasks & Acceptance

- [ ] 新增`booking_app/applications.py`及schema：申请表保存owner/supervisor快照、room/title/purpose/attendees/start/end、intent_key/canonical payload、created/decision事实，状态awaiting_approval/approved/rejected/withdrawn。为后续周期预留weeks=1及occurrences关联，不提前启用多周。另用`booking_supervisors`关联生效预约与可信导师快照；历史无关联不补假事实。
- [ ] 新增API：POST/GET `/api/applications`；GET `/api/applications/ID`；POST `/api/applications/ID/approve|reject|withdraw`。GET学生仅本人、teacher本人及绑定学生、admin全部；审批teacher且匹配归属，拒绝需reason1—500。写事务重新读取角色/关系；重放先授权，保持首个转换事实。过期状态派生，不自动写假拒绝。
- [ ] `services.py`：直订teacher/admin；新学生请求403，旧意图重放保留。关联导师本人/管理员无导师字段。旧学生直接取消活跃预约先403；本人导师可读所属学生详情。统一7天窗口和共享导师白名单。
- [ ] `schema.sql`、`audit.py/dto.py/static/audit.js`：application.created/approved/rejected/withdrawn新类型/严格快照；旧动作快照仍可读取。批准业务+槽+各真实转换审计同事务（允许多条不同转换，不能嵌套commit）。新增迁移及重启测试。
- [ ] `web.py/templates/static`：页面提交给正确API；学生明确“申请已提交，尚未占用”；导师批准/拒绝及学生撤回可用，个人页能找到申请与获批记录、详情含审批事实、共享导师安全文本。处理等待、401、冲突、未知结果原意图重试、键盘焦点、窄屏；不得只做API无入口。
- [ ] `tests/test_supervised_booking.py`、相关JS测试及旧fixtures：覆盖矩阵和并发/失败回滚；旧直订测试改用合成导师，保留学生专属安全测试，禁止仅全局改角色以掩盖授权缺陷。同步当前contract-examples.json及前后端严格键。
- [ ] `docs/evidence/human-review/booking-verification.md`：实际命令/输出；新增HTTP及真实浏览器runner支持学生→本人导师批准→共享日程→越权拒绝，截图是测试证据而非正式演示。代码留工作区，勿commit/push。

**Acceptance Criteria:**
- Given学生和两位导师，When提交/批准/跨导师访问，Then各自权限和不占用→占用规则成立，admin能查却不能代批。
- Given7天精确边界，When查询/新建/审批，Then合法边界通过、超限拒绝，停用30天不变。
- Given20个独立竞争批准，When同槽同时请求，Then恰1获批，其余冲突且保持待审；每申请幂等及审计回滚有存储断言。

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

运行新增审批单测及全部受影响Python/JS测试；真实浏览器走通一场。测试用临时文件库与固定Clock，最终浏览器运行生产Clock；记录源码指纹，不把旧208/399通过数当新版结果。主流程最终全套回归。
