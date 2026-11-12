---
title: '查询操作证据并在重启后继续使用'
type: feature
created: '2026-11-12'
status: done
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

- [x] 上述服务/页面/CLI按依赖实现；复用`admin-auth-lost`身份失效事件。
- [x] `tests/test_audit*`、`test_backup*`：覆盖矩阵及权限/纯文本/过期响应。
- [x] `scripts/verify_audit*`：真实浏览器及重启，证据入`docs/evidence/story-3.4/`。
- [x] `README.md`：新增能力、复跑/备份恢复命令；独立临时库，凭证不进Git。

## Implementation Notes

- 已实现管理员审计只读查询/严格DTO/安全响应式界面、SQLite backup CLI和README停服恢复交接。
- 7种真实变更、重放零新增、损坏JSON安全500与跨组件身份失效均有实际回归。
- 真实Waitress停服新PID重启、旧会话/取消后旧意图、138项全路由权限矩阵及四项NFR联合复核通过。
- 全量201项Python、296项JavaScript无skip；新功能及6组既有浏览器流程均通过桌面/手机。
- 完整原始结果、失败保留、AC/NFR映射见 [Story 3.4验证](../../docs/evidence/story-3.4/verification.md)。实施交主流程独立评审；未执行Git操作或声称人工验收。



## Spec Change Log

## Review Triage Log

|来源|判定|处理|核对依据|
|---|---|---|---|
|B1|high|patch|已用隔离临时库复现：失败清理删除既有target-shm；独立评审也复现成功复制删旧WAL/journal。目标命名空间必须先拒绝已有辅助文件，包含源库恰位于目标sidecar路径，清理只处理本次创建物。|
|B2|low|reject|进程被强杀可留不完整目标，真实但只会发生在中断路径；没有成功退出或检查报告。现有恢复说明先检查完整性/schema，不能把文件存在当完成。原子发布需新增暂存/发布/清理状态，超出直接修正；本次不加，明确中断边界和新目标重试。|
|B3|low|reject|SQLite backup在外部独占锁下可持续等待。生产库WAL、短事务，正常热库已有成功证据；未约定备份完成时限。新增截止时间及策略不是直接校正，暂不加；说明可中断并解除占用后重试，不宣称有超时保证。|
|B4|low|patch|空SQLite源实测输出schema_version=0且结构检查ok；这确不能证明应用兼容。README明确CLI只证明SQLite结构一致，应用恢复必须检查schema=1并执行db.check_database，不把结构有效说成可用应用备份；不扩充通用复制工具为schema迁移器。|
|B5|medium|patch|主流程复现room.updated/before=null、target_id与after.id不同、capacity=-1仍返回DTO。增加对已证明矛盾的静态检查：action/type、创建/转换before、快照ID、正数容量等；不以当前预约窗口否定合法历史。|
|B6|medium|patch|eventShape仅检查snapshot键；嵌套对象或字符串容量可直接进入展示。补对应字段类型和可空类型检查，增加malformed值回归；没有据故障注入输入认定服务当前泄漏真实口令。|
|B7|low|reject|默认/仅日期查询需要扫描排序属实，但当前合同明确全量列表，NFR性能指标针对可用性。没有观测到此负载的失败；新增索引及schema更新是性能扩展而非直接校正，保留现有按类型日期索引和已披露无分页边界。|
|B8|medium|patch|正常查询后修改筛选时旧结果仍留在新条件下，无当前查询条件说明。按既有管理列表惯例在输入/change时使旧结果失效，提示重新查询；补真实处理器和浏览器断言。|
|B9|low|patch|新runner硬编码macOS Chrome，README又声称沿用已有runner安装方式。复用既有的显式路径优先、否则解析Playwright chromium.executablePath方式，不更改CLI公开参数；补无显式路径的解析回归。|
|B10|medium|patch|真实浏览器只核键/行数/展开文字，没有独立核实际actor/action/target/time/reason和before/after显示绑定。按API响应逐行逐单元格比较完整内容，并包含取消、撤销和更新记录。|
|E1|high|patch|与B1同根；已核源库可以恰占目标sidecar路径，因此清理有删除源库风险。保留独立发现，合并最小命名空间拒绝和不改已有文件测试。|
|E2|medium|patch|与B5中before缺失同根；当前dto允许任意action前值null，UI显示创建前。增加creation与before是否null的一致性断言。|
|V1|medium|patch|已预验证：将返回reason强制None，5项audit Python仍通过。补各实际动作原因与独立预期/存储事件一致及非null原因DOM断言；保留该mutation应被拒的证据。|
|V2|medium|patch|已预验证：before单元格改读after，14项JS仍通过。用值不同的更新/取消事件断言前后列完整值，并在真浏览器展开比较；保留mutation失败证据。|

## Verification

- `.venv/bin/python -m unittest discover -s tests -v` 全量通过，无skip。
- `node --test tests/test_*js.cjs`，新增实际处理器关键错误恢复回归。
- 新功能真实浏览器1280x800及390x844正常/拒绝路径、登录退出和既有关键流程；精确DTO与纯文本，无页面横向溢出。
- 执行所列真实并发/故障/重启验证并保存原始结果。

## 本轮接受结果

208项唯一Python、313项JS，真实双视口与停服重启、138项权限检查通过，8组修补闭环，0defer。[最终核验](../../docs/evidence/story-3.4-review-fixes/parent-final-qa.json)。初版201/296保留为历史记录。
