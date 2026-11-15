---
title: 管理员配置导师与学生归属
type: feature
created: 2026-11-15
status: done
route: dispatch
baseline_commit: d585c190febd59ea3fd09ec2dd959052937e53c0
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="U-39批准完整变更方案；本卡编译其4.1，不增加人类决策">

## Intent

管理员统一创建学生和导师账号、预先绑定导师，供后续审批使用。保留本机Flask/SQLite结构及全部历史，显式升级旧库；学生无自注册/换导师入口。依据D-018/020/021及已批准变更方案。

## Boundaries & Constraints

保留member存储值表示学生，新增teacher，保留admin。新学生必须绑定teacher；旧库未知归属保留NULL，绝不猜测。初始化只添加、不覆盖已有密码/角色/绑定/业务。真实默认库不可修改，本故事仅临时库及副本验证。审批和学生直订拦截由紧随的4.2实现，本故事不宣称完整业务已切换。

## I/O & Edge-Case Matrix

|情形|结果|
|---|---|
|合法导师、学生、管理员配置|先建立导师，再绑定学生；teacher可登录；页面正确角色文字|
|学生绑定不存在/非teacher；teacher/admin绑定他人|拒绝，整批账号无部分写入|
|相同配置重复执行|无覆盖，已有数据不变；不偷偷修改错误绑定|
|schema1副本升级|ID/哈希/预约/槽/审计原样保留；旧学生未绑定；旧审计可读取|
|迁移失败、错版本、坏映射|原库不损坏；清晰失败；启动不自动升级|
|新绑定被客户端伪造|认证身份和归属从数据库读，HTTP无任意绑定写入口|

</frozen-after-approval>

## Code Map

- `booking_app/schema.sql`：users角色CHECK需重建，新增`supervisor_id`自引用；其余业务表不改变。
- `booking_app/db.py`：SCHEMA_VERSION/REQUIRED_COLUMNS、initialize/check；沿用显式事务、WAL与外键。
- `scripts/init_demo.py:seed_users`：现仅3账号，添加不覆盖；新配置学生使用`supervisor_username`。原3账号测试夹具可用显式旧库迁移夹具替代，不放宽新学生约束。
- `booking_app/auth.py`：Actor/read_session已从DB读角色；可保持CurrentUser精确字段不变，绑定在服务内查询，避免无必要DTO扩展。
- `booking_app/templates/base.html`、`static/auth.js`：角色显示/白名单；teacher不是admin，不开放管理端点。

## Tasks & Acceptance

- [x] `schema.sql`、`db.py`：schema2，支持可信导师FK；保持旧表ID与SQL约束。服务后续仍事务内刷新身份。
- [x] `scripts/migrate_db.py`（新增）：显式schema1→2；SQLite backup API备份至独立路径，拒绝覆盖；事务升级、完整性/外键检查；不自动绑定、不改旧审计、不删业务。可选受控首次绑定命令必须只允许NULL→有效teacher，禁止改已有归属；不必本故事增加此入口，新账号足够课程验收。
- [x] `scripts/init_demo.py`：合成两导师/两学生/admin，学生分别绑定；验证和哈希锁外，绑定与账号同事务。可对已初始化库添加单个账号，不再要求每次批次都有2学生/admin；空库演示主入口仍生成完整角色。
- [x] `auth.py`、`base.html`、`static/auth.js`：支持teacher身份，保持CSRF/Origin、8h会话及无凭证泄露。
- [x] `tests/test_supervisor_identity.py`（新增）及受影响认证夹具：覆盖矩阵，真实schema1数据库迁移、失败回滚、旧审计及历史槽保留；旧测试不通过删断言/skip修复。
- [x] `docs/evidence/human-review/identity-verification.md`、README账号/升级说明：准确记录命令、结果与阶段限制，不覆盖旧证据。所有改动留工作区，勿commit/push。

**Acceptance Criteria:**
- Given三角色配置，When初始化并登录，Then学生绑定正确，teacher无管理权限，重复配置不覆盖。
- Given有历史schema1副本，When显式升级，Then旧事实及ID不变、版本2可启动，失败原库可恢复且错误不泄密。
- Given旧未绑定成员，When读取历史，Then仍可读取且不虚构导师；完整业务授权在4.2统一落地。

## Implementation Notes

- 已完成schema2、导师FK/角色约束、先导师后学生的原子追加初始化和显式迁移命令。旧学生NULL不补绑，既有账号与业务不覆盖。
- `auth.py`现有服务端DB身份读取、精确DTO及8小时会话已满足teacher；`static/auth.js`实际无角色白名单，无需修改；模板新增三角色中文标签，定向测试覆盖teacher无管理权限。
- 历史回归改用完整schema1快照与显式迁移夹具，保留原三账号ID和原业务断言；相关验证脚本同步夹具及源码指纹。生产初始化未放宽新学生绑定要求。
- README及独立验证报告已记录阶段限制、实际失败和复跑；真实默认库未修改，工作区未commit/push。

## Spec Change Log

## Review Triage Log

2026-11-15三层首轮全部返回后逐项裁决；B=blind、E=edge、V=verification。主流程用临时schema1/2库复现B1/B3/B4，见review-reproduction.json。

|项|裁决|证据与路由|
|---|---|---|
|B1|high|源-journal作为备份确实在迁移后消失；patch，拒绝源sidecar命名空间并测试备份保留|
|B2|low|失败前DELETE→WAL不改业务/版本，但文档需说清；patch文档并加对应失败检查，不宣称字节完全不变|
|B3|medium|rooms同名trigger使迁移漏建users触发器，实际允许学生绑admin；patch，提交前校验新身份对象定义并回滚冲突|
|B4|medium|缺失触发器库通过启动检查，破坏新增关系不变量；patch，兼容性检查校验三身份触发器|
|B5|low|旧浏览器runner没有新导师场景属覆盖建议；生产初始化已有真实HTTP、三角色render/API测试。拒绝本故事新增复杂浏览器runner，4.2完整浏览器流程按已批准任务覆盖导师；不冒充本故事有此证据|
|B6|medium|最终组合尚无全套通过证据属真实限制；主流程补本次修补后完整Python回归，不改阈值或旧失败|
|B7|medium|schema1回退指向schema2检查不可照抄执行；patch独立旧版本/新路径恢复说明|
|B8|low|五卡矩阵缺Markdown分隔符；按workflow不计产品修补，父流程独立修正文档排版，不改变冻结意图|
|B9|medium|新版PRD NFR04漏列新增事实；父流程patch需求文档，后续故事及最终重启覆盖|
|B10|low|FR22引用已改写FR14无合并404定义；父流程patch为FR04和明确一致错误|
|E1|high|与B1同一已复现缺陷；合并修补但保留独立裁决行|
|V1|medium|测试未覆盖自定义约束/index/trigger拒绝，删除保护会丢完整性规则；patch参数化拒绝及未变快照断言|

分组：B1/E1路径保护；B3/B4身份schema完整性；B2/B7文档；V1验证补强；B6父流程最终回归；B8—10父流程规划文档。无用户意图缺口，无新增公开接口，修改均局限已复现状态的直接保护/文档/验证。

## Verification

`.venv/bin/python -m unittest tests.test_supervisor_identity tests.test_auth tests.test_backup -v`；修改JS时运行对应`node --test tests/test_auth_js.cjs`。保存实际输出和非零失败，不假称全套通过。新迁移测试以旧schema快照构造真实含FK/审计数据；只造空users表不足。

实际结果：最终指定Python三模块50项通过、auth JS 4项通过；完整回归曾218项中1项HTTP计数失败，修复后包含该场景的54项定向测试通过，未冒称最终全套已重跑。完整输出与失败历史见 `docs/evidence/human-review/identity-verification.md`。

主流程收口：三层12条发现逐项处理，关键路径/身份约束修补及参数化测试通过；完整Python225项通过、源码稳定，证据parent-final-python.json。B5的整合浏览器场景在已批准4.2任务中执行，未冒称4.1已做。其余修补均已闭环。
