---
title: '查看会议室和共享日程'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: 3f0349edf4cb0dedd85e269fdb1530cd67aa95d5
story_key: 1-2-room-schedule
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-1-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 1.2 — 查看会议室和共享日程

<frozen-after-approval reason="用户已授权完整实施；按已冻结上游基线执行，非人工逐项批准">

## Intent

**Problem:** 已登录课题组成员需要查看会议室与指定北京日期的占用，用于安排活动。

**Approach:** 在已完成1.1身份基础上交付可操作的目录与日程页面/API；追踪FR-05/07/22、NFR-02、ADR-02/03/06、UX-DR3/4/9/10。仓库为 `/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking`。

## Boundaries & Constraints

**Always:** 页面/API共用查询服务；身份在服务端确认；共享DTO只输出合同字段；数据为明确合成夹具。复用认证、事务、Clock及错误协议，保持正常登录退出。

**Never:** 不实现可用性/创建预约/管理写入/实验目标；不通过返回完整对象再隐藏字段保护隐私；不操作Git或远端。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 输出/行为 | 错误处理 |
|---|---|---|---|
| AC-1.2-1 | 已登录，目录有不同名称/地点房间 | GET /api/rooms精确Room列表、name/location/id升序；中文页面可选择房间 | 空目录200及空状态，匿名401 |
| AC-1.2-2 | 同日、跨日、已结束未撤销停用、取消预约/撤销停用夹具 | GET /api/schedule按date相交、start/id升序；排除取消/撤销，保留历史；ScheduleItem带kind及精确record | status随统一t派生；午夜端点半开，不能重复算相邻日 |
| AC-1.2-3 | 成员甲查看乙的预约，名称含HTML字符 | JSON及DOM没有用途/人数/账号/取消原因/预约ID/userID；显示名、活动名纯文本 | 私密字段不允许仅隐藏；XSS不执行 |
| AC-1.2-4 | 非法日期、资源ID越界/不存在、空结果 | 非法400、合法范围不存在404、空200；表单label/条件/空状态明确 | 未认证先401，2**63及超长数字不500 |

</frozen-after-approval>

## Code Map

- `booking_app/auth.py`：Actor、actor_for_token、read_session可复用；服务不要信任客户端user_id。`db.py`：连接和显式事务已实现，增加短只读事务助手及必要schema列检查。
- `schema.sql`：目前只有users/sessions。当前查询首次需要rooms/reservations/occupancy_slots，按架构完整kind/null/外键/索引约束增加；audit_events在2.1首个业务写时引入。初始化为非破坏性CREATE IF NOT EXISTS，重复不清库，user_version1保持此开发基线。
- 新建 `services.py` 与适度的DTO辅助文件，纯规则放domain；完整UTC/本地时间及状态合同已在architecture§5—7。ID转换先长度范围检查，不接受Unicode数字、前导零、bool/float；date严格YYYY-MM-DD且拒绝日期溢出。
- `web.py`：新增rooms/schedule接口，只适配服务，不写SQL。home.html替换临时欢迎内容为目录+日期日程；base/auth.js的退出反馈节点必须保留，脚本使用独立命名作用域防全局冲突。
- `scripts/init_demo.py`仍仅负责私有账号。可另建 `scripts/seed_demo_rooms.py` 添加标记清楚的合成房间（幂等，不覆盖数据），用于本故事独立展示；预约/停用由测试夹具直接准备，满足槽完整性，不提前提供业务写接口。
- `tests/test_auth.py`已33项，首初始化表集合断言需随当前schema增量调整而保留核心不覆盖/安全断言。新 `tests/test_room_schedule.py` 不继承包含test_方法的AuthTests，避免重复计数。浏览器runner依赖身份h1和Tab顺序；若页面改变，只改为稳定身份区域断言，不删登录/退出验证。

## Tasks & Acceptance

**Execution:**
- [x] schema/db — 仅增加本故事查询所需实体及只读一致快照。
- [x] domain/services/DTO — 目录和相交日程、准确状态/白名单、严格输入。
- [x] web/templates/static — 可操作中文目录/日程，label/等待/成功/空/错误、手机无页面溢出，所有输出安全。
- [x] tests/测试夹具 — 跑矩阵所有正常与拒绝边界，跨日和历史停用、字段不存在而非仅空值、同start稳定排序、身份过期/退出拒绝。
- [x] README/证据 — 演示房间初始化可复跑，不生成公开固定密码；保存真实测试及至少桌面/手机浏览器结果。

**Acceptance Criteria:**
- Given1.1已完成，When按新README初始化/启动，Then用户能登录选择房间和日期、看到空/有日程结果并退出，无需后续故事。
- Given相邻午夜与跨日停用夹具，When查询每个覆盖日期，Then与半开相交模型一致且没有私密字段。

## Implementation Notes

前一故事为b80e331：会话、Origin/CSRF、错误格式、凭证字节界限和浏览器runner已验证；保持这些能力，不为方便查询放松身份。暂无额外人类意图缺口，业务实际适用性仍标假设。

## Spec Change Log

## Review Triage Log

|编号|裁决|处置|核对证据与理由|
|---|---|---|---|
|B1|medium|patch|等待时room/date可编辑，旧错误确会标记新输入；固定本次查询期间禁用两输入，finally恢复即可，不增加业务协议。|
|B2|low|patch|home无noscript说明，脚本禁用可进入JSON；增加清晰的查询依赖JavaScript提示即可，不引入第二套HTML查询。|
|B3|low|reject|重新登录确会进入新页面；当前保留承诺是查询失败期间不清表单，不是跨登录持久状态。8h到期后的跨页面保存需要新增存储/回跳机制，对本地短时课程演示收益小，不增加复杂度。|
|B4|low|reject|手工直接SQL可植入超Python日期范围时间；当前CLI与所有合成夹具均在2026年，正常入口不生成该状态。对绕过服务的任意数据库内容新增边界分支非日常需求。|
|B5|low|reject|MultiDict.get稳定选择首值；重复键不改变身份/权限，所用首值仍严格验证。当前合同未要求拒绝重复标量，额外分支没有已证实用户损害。|
|B6|medium|patch|新增schedule.js未被认证JS测试执行；补响应头/正文超时、网络失败/坏JSON与恢复重试的定向测试。|
|B7|low|patch|原浏览器仅认证用键盘，日程用程序填充；给既有浏览器场景增加键盘提交与焦点次序断言，作为声明的直接补证。|
|B8|medium|patch|固定2026夹具与真实时钟会使状态随运行日期漂移；验证runner专用工厂注入fixture Clock并断言每项显示状态。生产工厂不接环境测试时钟。|
|B9|low|reject|空目录服务器测试已验证200及提示；HTML原生disabled条件明确且无房间不能提交，补一个独立空库浏览器生命周期收益小。非每个分支都需重复端到端覆盖。|
|B10|false|reject|服务端字段校验及聚焦已实现，novalidate用于统一中文错误并不等于缺失验证。要求另写客户端时间/编号规则会产生重复来源；网络往返是设计行为，无已证实错误结果。|
|E1|low|reject|年1附近手工epoch可能因时区表示下溢；仅在绕过服务直接造数据库行后出现。与B4同类，正常当前时间/未来窗口不会产生，新增防御超范围导入不属日常场景。|
|E2|medium|patch|与B1同一已复现可编辑条件导致旧错误覆盖，禁用本次输入并最终恢复。|
|V1|medium|patch|预验证mutation将end_local置start_local仍49测试过，缺端点值会误报时长；增加普通/跨日明确epoch、本地串及完整显示区间断言。|
|V2|medium|patch|预验证指出schedule自己的AbortSignal无回归，认证测试不能代替；与B6同根因，新增实际submit处理器超时恢复测试。|

归并：B1/E2条件竞态；B6/V2超时测试；其余B2、B7、B8、V1各自直接修补。无high/medium延期；低影响的非日常防御和重复验证拒绝。


## Verification

- `.venv/bin/python -m unittest discover -s tests -v` — 全量通过，无skip。
- `node --test tests/test_auth_js.cjs` — 认证超时回归通过。
- 实际运行浏览器目录/日期查询与登录退出；保存无凭证证据于`docs/evidence/story-1.2-*`；测试和演示库隔离。

实际实施验证（2026-11-12）：49 项 Python 测试、2 项认证 JS 回归、1280×800 与 390×844 真实浏览器全部通过。证据见 [Story 1.2 验证记录](../../docs/evidence/story-1.2-verification.md)；执行项完成，等待独立评审。


主代理最终核对：49项Python、7项JS全量通过（0 skip）；修订后桌面/手机浏览器通过，固定Clock三态、准确区间、无脚本说明与键盘提交均有证据；已查看修订截图。14条发现逐条裁决，所有保留修补项关闭，无high/medium延期。
