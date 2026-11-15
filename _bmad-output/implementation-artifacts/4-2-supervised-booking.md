---
title: 学生申请与本人导师审批
type: feature
created: 2026-11-15
status: done
route: dispatch
baseline_commit: b6af1a1cc47e890cfdf59c7ad92f378bdd4235f9
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
- `schema.sql/db.py/scripts/migrate_db.py`：4.1已schema2；新schema版本及显式兼容升级须保留旧事实。迁移必须兼容1和2两种源：v1基线列/定义固定，不能从新增REQUIRED_COLUMNS倒推；v2已有teacher/绑定不得丢失。继承最新备份路径隔离、身份触发器校验与回滚保护。
- `domain.py:validate_booking_window`当前30天；停用校验独立保持30天。
- `dto.py`、`booking.js/history.js/schedule.js/audit.js`严格字段；所有调用者和fixture同步。
- `web.py`薄适配、`templates/home.html/my.html/base.html`；新增`applications.html/applications.js`提供本人记录及导师审批入口，admin可看全部不代批。

## Tasks & Acceptance

- [x] 新增`booking_app/applications.py`及schema：申请表保存owner/supervisor快照、room/title/purpose/attendees/start/end、intent_key/canonical payload、created/decision事实，状态awaiting_approval/approved/rejected/withdrawn。为后续周期预留weeks=1及occurrences关联，不提前启用多周。另用`booking_supervisors`关联生效预约与可信导师快照；历史无关联不补假事实。
- [x] 新增API：POST/GET `/api/applications`；GET `/api/applications/ID`；POST `/api/applications/ID/approve|reject|withdraw`。GET学生仅本人、teacher本人及绑定学生、admin全部；审批teacher且匹配归属，拒绝需reason1—500。写事务重新读取角色/关系；重放先授权，保持首个转换事实。过期状态派生，不自动写假拒绝。
- [x] `services.py`：直订teacher/admin；新学生请求403，旧意图重放保留。关联导师本人/管理员无导师字段。旧学生直接取消活跃预约先403；本人导师可读所属学生详情。统一7天窗口和共享导师白名单。
- [x] `schema.sql`、`audit.py/dto.py/static/audit.js`：application.created/approved/rejected/withdrawn新类型/严格快照；旧动作快照仍可读取。批准业务+槽+各真实转换审计同事务（允许多条不同转换，不能嵌套commit）。新增迁移及重启测试。
- [x] `web.py/templates/static`：页面提交给正确API；学生明确“申请已提交，尚未占用”；导师批准/拒绝及学生撤回可用，个人页能找到申请与获批记录、详情含审批事实、共享导师安全文本。处理等待、401、冲突、未知结果原意图重试、键盘焦点、窄屏；不得只做API无入口。
- [x] `tests/test_supervised_booking.py`、相关JS测试及旧fixtures：覆盖矩阵和并发/失败回滚；旧直订测试改用独立合成导师fixture，旧真实历史仍用schema1迁移fixture；不得把所有遗留member统一变teacher使认证/历史隐私用例失真。保留学生专属安全测试，禁止仅全局改角色以掩盖授权缺陷。同步当前contract-examples.json及前后端严格键。
- [x] `docs/evidence/human-review/booking-verification.md`：实际命令/输出；新增HTTP及真实浏览器runner支持学生→本人导师批准→共享日程→越权拒绝，截图是测试证据而非正式演示。代码留工作区，勿commit/push。

**Acceptance Criteria:**
- Given学生和两位导师，When提交/批准/跨导师访问，Then各自权限和不占用→占用规则成立，admin能查却不能代批。
- Given7天精确边界，When查询/新建/审批，Then合法边界通过、超限拒绝，停用30天不变。
- Given20个独立竞争批准，When同槽同时请求，Then恰1获批，其余冲突且保持待审；每申请幂等及审计回滚有存储断言。

## Implementation Notes

规划交接：4.1已接受，原完整Python225项通过。schema2身份测试对版本、表集合和历史快照有精确断言，新增业务表后应区分旧表保留与新增空表，而不是忽略验证；新增升级需覆盖schema1/2。此前legacy_fixture仅为旧历史而设计，不能当作新学生绕过审批的豁免。

## Spec Change Log

## Review Triage Log

复核输入：`/tmp/bmad-4-2-review.sb5QS2`，三路均在处理意见前完成。以下按原发现逐条记录，未合并或抹去不采纳项。

|来源/位置|裁定与核查依据|处置|
|---|---|---|
|blind-01 `applications.py:18`|low：直接修改学生导师绑定会使旧待审申请失去可审批者；当前用户明确首版不提供换导师，管理员CLI仅新增不改绑定，课程原型日常无法触发。|拒绝本故事增加改绑流程；真实部署前另议。|
|blind-02 `applications.py:71`|low：新增申请列表无分页会随保留记录增加而变慢；同项目现有历史/审计列表亦无分页，课程本机原型负载有限；本故事引入分页会改变公开合同和多处界面。|拒绝本故事分页，保留课程范围限制。|
|blind-03 `applications.py:54`|false：允许同一时段多个待审申请是本故事冻结矩阵的明确要求；申请不占槽，批准才在锁内查冲突，提交时已有占用也不应伪称已锁房。|不改提交语义。|
|blind-04 `applications.js:85`|medium：`TRANSITION_CLOSED`可由另一操作者先决定而发生，“记录保持原样”不真实，当前列表继续显示旧按钮。|patch：失败提示要求刷新，清理过时动作。|
|blind-05 `applications.js:51`|low：每次查看已生效详情都会追加段落，重复点击及后续取消可并列显示不同状态。|patch：单一详情区域替换。|
|blind-06 `applications.js:29`|medium：CSRF失败后旧令牌与按钮仍在，反复提交无法成功且提示不够明确。|patch：显示重新载入/登录引导并停止旧操作。|
|blind-07 `booking.js:80`、`home.html:53`|medium：学生申请的未知结果、新意图及表单文案仍多处称已预约，混淆“待审不占房”。|patch：按角色明确申请与生效预约。|
|blind-08 `db.py:159`|medium：schema3启动只查新表列，关键唯一约束/来源限制被删除后仍可能放行；由新增业务表暴露的实际数据风险。|patch：校验新表定义和关键索引，加入畸形库启动测试。|
|blind-09 `test_supervised_booking.py:221`|medium：schema2迁移测试没有旧审计行，不能发现重建审计表时静默丢失历史。|patch：加旧审计事实并校验备份/升级后的值。|
|blind-10 `test_supervised_booking.py:206`|medium：拒绝及撤回只有服务测试和模拟JS，未真实验证HTTP角色、CSRF、响应和重放。|patch：补HTTP调用路径测试。|
|blind-11 `contracts.js:13`|medium：完整预约严格合同允许导师来源和ID/审批申请编号矛盾，破坏页面对导师与审批事实的依赖。|patch：按来源校验字段关系。|
|edge-01 `schema.sql:136`|high：SQLite `CHECK`把NULL视为通过，`status='rejected'`且`decision_reason=NULL`的表达式结果为NULL；数据库可保存无理由拒绝。|patch：拒绝状态显式要求非NULL并测试SQL约束。|
|edge-02 `applications.js:89`|medium：处理成功后列表刷新失败会覆盖已确认成功提示并留下旧操作。|patch：保留确认结果并让列表提示需要手动刷新。|
|verification-01 `audit.js:12`|medium：现有管理员审计JS夹具无申请事件，新增动作白名单/快照渲染无界面验证。|patch：申请创建和处理事件实际经过审计处理器并核对文本。|
|verification-02 `applications.js:61`|medium：撤回按钮未点击；拒绝JS测试只检查payload不检查路径和结果，错误路由仍能通过。|patch：点击两个按钮并核对完整请求及显示结果。|

主流程另核查：旧浏览器脚本 `verify_auth_browser.cjs:125` 仍按旧共享日程字段断言，真实 Chrome 运行在该行失败；已同步新增的所属导师白名单键，待源码稳定后复跑。迁移 `migrate_db.py` 重建旧审计表前未校验自定义约束、索引、触发器，可能静默丢失旧保护；已交同一实现上下文补源库守卫与畸形库验证。

## Verification

运行新增审批单测及全部受影响Python/JS测试；真实浏览器走通一场。测试用临时文件库与固定Clock，最终浏览器运行生产Clock；记录源码指纹，不把旧208/399通过数当新版结果。主流程最终全套回归。

实际收口（2026-11-15）：复核前239项Python/405项JS通过；三路独立复核提出15项，逐条裁定为12项修补、2项低风险拒绝、1项与冻结矩阵相反的误报。修补后完整Python **243项**、JS **414项** 均通过；新增审批HTTP、桌面/390px Chrome、旧直订20请求HTTP及旧直订桌面/390px Chrome均实际通过。另修复旧浏览器runner的共享/完整字段与新导航断言；保留最初失败记录供溯源。当前复核没有转入延期事项。证据见 `../../docs/evidence/human-review/booking-verification.md` 与 `../../docs/evidence/story-4.2/`。最终产品全流程仍待4.3—4.5。
