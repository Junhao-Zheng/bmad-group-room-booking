---
title: '查询操作证据并在重启后继续使用'
type: feature
created: '2026-11-12'
status: in-progress
route: dispatch
baseline_commit: 795c65285aabb99d86d74a1b240deaa57ba9b1f8
story_key: 3-4-audit-and-restart
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-3-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 3.4 — 查询操作证据并在重启后继续使用

<frozen-after-approval reason="用户授权完整实施，沿用规划；非额外人工批准">

## Intent

**Problem:** 管理员和部署者需要按对象日期查看真实变更且重启不丢记录，以便能够追查预约和维护过程。
**Approach:** 追踪FR-21/22；NFR-02/04；ADR-07/08；UX-DR8/9/10。

## Boundaries & Constraints

**Always:** 服务端授权、严格输入、单事务业务/槽/审计、精确DTO、统一Clock；实际测试和可追踪证据。
**Never:** 不虚构记录；不操作Git/远端。

## I/O & Edge-Case Matrix

|验收编号|Given|When|Then|
|---|---|---|---|
|AC-3.4-1|管理员查看成功业务变更|按对象类型/日期过滤操作记录|occurred_at/id降序，actor快照/action/target/时间/前后值/原因完整，成员403|
|AC-3.4-2|重复提交/取消/无变化更新|统计审计|只统计真实转换，不含密码/token/CSRF/请求头|
|AC-3.4-3|执行房间修改及预约创建取消、停用创建撤销|真实停止重启Waitress|数量/关键字段/关联不变，旧成功意图返回同记录；保存重启前后证据|
|AC-3.4-4|准备本地运行交接|按文档检查schema版本、数据库路径和备份方式|配置可复现，默认仅loopback；备份使用SQLite backup API且不复制热库主文件；运行数据和凭证不进Git|

</frozen-after-approval>

## Code Map

- `booking_app/services.py`、`dto.py`、`web.py`：新增audit_events只读服务及GET /api/admin/audit：短事务内认证admin，同t；target_type可选room/booking/block、date按北京日事件时间半开过滤；occurred_at/id降序，精确AuditEvent白名单，before/after解析为JSON对象/null，不省略、不返回字符串。损坏JSON安全500，不能静默跳过；member403。
- `templates/admin.html`、`static/audit.js`、`app.css`：/admin操作记录界面支持对象/日期过滤、空/加载/错误/失效，安全展示actor快照/action/target/时间/前后值/原因；长内容可展开，表格局部横滚而不是页面横溢出。
- 重放/重复取消/撤销/无变化房间不增审计；所有7种实际动作完整对应业务最终状态，审计无口令、cookie、CSRF、摘要或完整请求头。
- 真实Waitress进程先运行房间修改、预约创建取消、停用创建撤销，采集业务/槽/审计数量与完整关键字段及关联hash；实际停止并新PID启动，同库内容不变、有效旧会话可用、原成功intent返回同一已取消记录、审计数不变。不能仅重新create_app或页面打开冒充重启。
- `scripts/backup_db.py`：备份CLI用SQLite Connection.backup，独立目标600权限、不覆盖源/已有目标，完成integrity/fk检查；README停服恢复、清会话、WAL/SHM处理与回退步骤，不伪称已灾难演练。默认runtime仅loopback，证据含Python/SQLite/依赖/OS/CPU/内存/启动命令。
- 完成全路由权限矩阵和四项NFR联合复核，保存真实结果。现有NFR03若查询代码没有变化可保留前次证据；如有相关变更需复跑并保留各次结果。人工材料与录屏由主代理整理。

## Tasks & Acceptance

- [ ] 上述服务/页面/CLI按依赖实现；复用`admin-auth-lost`身份失效事件。
- [ ] `tests/test_audit*`、`test_backup*`：覆盖矩阵及权限/纯文本/过期响应。
- [ ] `scripts/verify_audit*`：真实浏览器及重启，证据入`docs/evidence/story-3.4/`。
- [ ] `README.md`：新增能力、复跑/备份恢复命令；独立临时库，凭证不进Git。

## Implementation Notes



## Spec Change Log

## Review Triage Log

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs`，新增实际处理器关键错误恢复回归。
- 新功能真实浏览器1280x800及390x844正常/拒绝路径、登录退出和既有关键流程；精确DTO与纯文本，无页面横向溢出。
- 执行所列真实并发/故障/重启验证并保存原始结果。
