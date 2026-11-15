# 本人复核变更：只读代码调查

日期：2026-11-15。依据已读取的`bmad-build`步骤2，由两个独立调查上下文读取代码；二者未修改文件、未运行产品测试。主流程核对现行PRD、架构、史诗、UX、规则及用户决策后整理。此记录是调查摘要，不是独立验收报告。

调查上下文：`change_backend_map`、`change_frontend_map`。早先上下文摘要提及的调查者在本轮无可取得结果，不声称本文件是其产出。

## 代码地图

| 路径/符号 | 事实及实施注意 |
|---|---|
| booking_app/schema.sql | 角色CHECK仅member/admin；审计动作CHECK固定；新增导师及事件需升级；预约/停用共表并共享唯一槽 |
| booking_app/db.py | SCHEMA_VERSION=1；启动拒绝自动迁移；保留显式事务和每请求连接，新增显式升级副本验证 |
| booking_app/auth.py / services.py:_require_actor | 会话读取数据库身份，服务写锁后刷新；导师关系不能信任客户端或陈旧Actor |
| services.py:create_booking | 先规范化和幂等重放，再校验时间/容量/冲突；学生旧入口必须无法直接获得占用 |
| services.py:schedule/create_block/update_room/_admin_records | 多处将未取消reservation当占用；建议待审申请独立表，避免污染旧占用语义 |
| services.py:member_cancel_booking/admin_cancel_booking | 学生直接取消须改成申请；管理员结束前带理由干预保留；两流程需并发一致 |
| domain.py:validate_booking_window | 当前约束结束时间30天；普通/首场改7天，周期后续有显式例外；维护保持独立30天 |
| services.py:booking_detail/_BOOKING_DETAIL_SELECT | 旧详情仅本人/admin，新增本人导师权限和可信所属导师；其他导师仍不能读取私密详情 |
| dto.py / static/booking.js / blocks.js / audit.js | 严格字段集合和历史快照验证；新协议需前后端及夹具同步，旧审计不能被新字段要求拒读 |
| web.py / templates/base.html | 新导师页面与API需要服务层权限；所有写仍Origin+CSRF；不复用admin全局权限替代导师关系 |
| templates/home.html / static/availability.js / booking.js | 7天提示，周数/日期摘要，学生成功文字是申请已提交而非占用成功；周数进入幂等签名 |
| templates/my.html / static/history.js | 待审批与待开始分开；取消待确认时保持占用；详情含审批事实；`pending`不可重新解释为待审 |
| static/schedule.js / dto.schedule_item | 共享导师字段，保留白名单和安全文本；待审申请不显示成已占用 |
| templates/admin.html / static/blocks.js | 预览实际冲突后一次确认，房间/时段/原因变化或新增占用要求重确认；继承跨表单锁定与草稿策略 |
| scripts/init_demo.py:seed_users | 现有初始化仅添加不覆盖；扩展可信导师绑定及合成角色，不能修改未知真实账号密码/归属 |

## 验证入口与易漏问题

- `tests/test_auth.py`、`test_create_booking.py`、`test_member_cancel.py`、`test_replay_intent.py`等旧夹具按成员直订构造，需要有意识地区分导师直订、学生申请、旧历史记录；不得跳过新规则导致的失败。
- `tests/test_room_schedule.py`共享字段白名单、`test_*_js.cjs`严格DTO须和新协议同步；新增跨导师API权限及审批状态测试。
- `scripts/verify_auth_browser.py::verify_committed_response_loss`原断言提交立即产生槽和booking.created；新版学生流程应改证据场景，不能照抄旧PASS。
- 复用`verify_history_browser.py`等临时文件库、真实Waitress/Chromium、清理进程组、源码指纹和失败先作废报告机制。新报告单独目录；不覆盖历史版本。
- 新增审批竞争、取消开始等号、8周上限/冲突、周期意图重放、维护预览变化及事务中审计失败；断言最终数据库，不只看HTTP。
- 迁移保留旧预约和旧审计语义；旧member可能没有导师绑定，不能猜关系；旧意图取消/开始后仍须可重放。

## 未决业务与建议

两项核心选择为周期审批/冲突粒度、导师本人是否直订，见[完整方案](../../../_bmad-output/planning-artifacts/sprint-change-proposal-2026-11-15.md)。按场取消、未审批撤回/过期、管理员保留原直订且不代批等配套建议均明示为AI方案；未经回复不写成用户亲自决定。两调查者对管理员自身直订给出不同取舍，主方案选择保留现有能力并明确无导师归属，以减少无授权的功能删减。
