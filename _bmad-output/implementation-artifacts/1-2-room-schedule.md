---
title: '查看会议室和共享日程'
type: feature
created: '2026-11-12'
status: ready-for-dev
route: dispatch
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
- [ ] schema/db — 仅增加本故事查询所需实体及只读一致快照。
- [ ] domain/services/DTO — 目录和相交日程、准确状态/白名单、严格输入。
- [ ] web/templates/static — 可操作中文目录/日程，label/等待/成功/空/错误、手机无页面溢出，所有输出安全。
- [ ] tests/测试夹具 — 跑矩阵所有正常与拒绝边界，跨日和历史停用、字段不存在而非仅空值、同start稳定排序、身份过期/退出拒绝。
- [ ] README/证据 — 演示房间初始化可复跑，不生成公开固定密码；保存真实测试及至少桌面/手机浏览器结果。

**Acceptance Criteria:**
- Given1.1已完成，When按新README初始化/启动，Then用户能登录选择房间和日期、看到空/有日程结果并退出，无需后续故事。
- Given相邻午夜与跨日停用夹具，When查询每个覆盖日期，Then与半开相交模型一致且没有私密字段。

## Implementation Notes

前一故事为b80e331：会话、Origin/CSRF、错误格式、凭证字节界限和浏览器runner已验证；保持这些能力，不为方便查询放松身份。暂无额外人类意图缺口，业务实际适用性仍标假设。

## Spec Change Log

## Review Triage Log

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` — 全量通过，无skip。
- `node --test tests/test_auth_js.cjs` — 认证超时回归通过。
- 实际运行浏览器目录/日期查询与登录退出；保存无凭证证据于`docs/evidence/story-1.2-*`；测试和演示库隔离。
