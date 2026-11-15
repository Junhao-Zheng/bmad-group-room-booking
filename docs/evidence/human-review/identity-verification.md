# 故事4.1：导师身份与学生归属验证

日期：2026-11-15。范围仅为本机 Flask/SQLite 身份基础，不代表4.2审批业务已启用。未修改或迁移 `instance/booking.sqlite3`，未提交或推送。所有数据库验证使用 `TemporaryDirectory` 下的合成库和备份；没有真实账号、凭证或旧默认库写入。

## 实现与保留边界

- schema 2：`member` 表示学生，新增 `teacher`，保留 `admin`；新增 `supervisor_id` 自引用外键、仅学生可绑定及有效导师触发器，并阻止被学生引用的导师降级。旧学生允许 `NULL`，不猜测归属。
- `scripts.init_demo`：隐藏输入默认两导师、两学生、管理员共五个账号；学生配置必须显式指定 `supervisor_username`。验证和 scrypt 在写锁外；有效角色/映射在写事务中复核，导师先插入，账号和绑定同事务。配置重复仅补缺失账号，不重置任何已有事实，错误映射不部分写入。空库CLI仍要求完整演示角色，已初始化库可单账号追加。
- `scripts.migrate_db`：只接受显式 `--source` 和 `--backup`，拒绝错误版本/未知用户表结构/自定义用户对象/坏外键，使用 SQLite backup API 保存独立私有快照，拒绝覆盖。写锁内重建用户表；历史ID、哈希、会话、房间、预约、槽、审计原样保留；提交前完整性和外键检查，异常回滚。启动和初始化均不自动升级schema 1。
- 页面角色显示“学生/导师/管理员”。现有 `auth.py` 从数据库读取角色，`static/auth.js` 不含角色白名单；两者无需修改，精确 CurrentUser DTO、8小时会话、CSRF/Origin与凭证保密契约保持不变。导师无管理员权限，HTTP无自注册或归属写入接口。
- `tests/fixtures/schema_v1.sql` 是变更前完整schema快照；`tests/legacy_fixture.py` 真实创建schema 1并迁移，用于原三账号/固定ID历史回归。旧业务测试及对应验证脚本显式使用此夹具；新身份测试使用生产初始化。没有通过删断言或skip规避新学生必须绑定约束。历史脚本的源码指纹列表加入迁移及夹具依赖。

## 实际运行

|命令或范围|结果|完整原始输出|
|---|---|---|
|`.venv/bin/python -m unittest tests.test_auth tests.test_backup -v`|39通过|[01](identity/01-auth-backup.log)|
|`.venv/bin/python -m unittest tests.test_supervisor_identity tests.test_auth tests.test_backup -v` 首轮|49项，2失败：新增测试对405转400的预期错误、手写旧审计快照不完整|[02](identity/02-focused.log)|
|`.venv/bin/python -m unittest discover -s tests -v` 首轮|218项，3失败4错误；包括上述两项及旧验证脚本缺导师配置|[03](identity/03-regression.log)|
|`node --test tests/test_auth_js.cjs`|4通过、0跳过|[04](identity/04-auth-js.log)|
|指定三模块修正复跑|49通过|[05](identity/05-focused.log)|
|完整Python回归第二轮|218项，1失败：真实HTTP脚本残留3账号计数预期|[06](identity/06-regression.log)|
|三指定模块 + `tests.test_browser_verification`|54通过，含真实HTTP隔离脚本修复验证|[07](identity/07-focused-and-runner.log)|
|最终 `.venv/bin/python -m unittest tests.test_supervisor_identity tests.test_auth tests.test_backup -v`|50通过、0跳过，退出码0；新增完整角色CLI/空文件初始化/单账号追加覆盖|[08](identity/08-final-focused.log)、[退出码](identity/08-final-focused.exit)|
|重复初始化角色保留测试 + `tests.test_admin_cancel_browser_runner tests.test_block_revoke_runner`|15通过、0跳过，退出码0；复核原学生改为管理员后仍不被重复配置覆盖，以及历史runner失败证据契约|[09](identity/09-repeat-and-runners.log)、[退出码](identity/09-repeat-and-runners.exit)|

02/03/06的失败原文没有覆盖。其早期工具调用以`tail`结束，shell整体状态为0，但日志明确记录了unittest失败；不能将工具shell状态当作测试通过。最终08使用subprocess记录真实测试退出码。修复最后一项后没有再次运行完整Python套件，不宣称最终全套通过。所有改动脚本通过Python编译检查；本轮未执行完整浏览器可视化/全部HTTP业务场景或性能测试。

## 验收证据与限制

新增11项身份测试覆盖三角色登录与页面文字、导师拒绝管理员接口、两个独立归属、非法映射/非学生绑定、整批失败回滚、重复配置不改角色/密码/归属、锁外哈希、伪造身份与绑定无效、数据库角色实时读取、真实schema 1历史迁移、备份独立性、迁移后旧审计与详情可读取、失败回滚、备份可再迁移恢复、错误版本/结构/外键/备份冲突拒绝、CLI错误不泄密。

原schema1中已有学生迁移后仍无导师；本故事未实现旧账号首次绑定入口，重复初始化不会自动补绑。需要课程验收的学生使用明确绑定的新账号。schema迁移要求停服，并对非标准用户表结构拒绝处理。迁移失败后的逻辑事实和版本回滚已测试；没有把真实默认库的停服恢复宣称为已演练。

**审批、7天窗口、学生直订拦截、完整业务授权、取消审批、周期申请与批量维修仍由后续故事实现。本轮仅是身份基础。**

关键源码摘要：[source-sha256.json](identity/source-sha256.json)。README提供五账号配置、追加、显式升级和恢复说明。


## 独立复核后的修补（2026-11-15）

复核复现已保留于 [review-reproduction.json](identity/review-reproduction.json)。复核指出源库sidecar作为备份可能被SQLite消费，以及同名但挂在rooms上的触发器会被`IF NOT EXISTS`误认已安装；初轮测试未覆盖这些情况。

- 备份和迁移共用路径预检，在打开SQLite前检查源/目标完整命名空间（含`-journal`、`-wal`、`-shm`和解析后的目录别名）。拒绝路径时不创建或删除文件；成功的独立备份仍能打开读取。
- schema 2兼容检查及迁移提交前，逐条检查三条身份触发器的原始定义和挂载表，并检查非空归属实际指向teacher。缺失、改写、错表的触发器和无效存量归属均拒绝；迁移异常回滚schema/数据/版本，保留已完成备份。相同语义但非本版本原始定义的自定义触发器也会保守拒绝。
- 补充schema 1自定义users索引、自定义users触发器和改变CHECK约束的拒绝测试，逐项比较schema、数据、版本，未放宽原结构检查。
- 纠正失败边界：路径隔离拒绝发生在任何SQLite打开前；版本1源库的DELETE→WAL设置发生在迁移事务外，完整schema验证或事务失败后，这项设置可以保留。测试实际证明此时数据/schema/user_version保持原样，但journal_mode为WAL，且若失败在备份之前，不会产生备份。不能将“回滚”描述为源文件逐字节不变。
- README新增独立的 [schema 1回退流程](../../../README.md#schema-1-独立回退验证)：归档兼容代码`d585c190febd59ea3fd09ec2dd959052937e53c0`，使用全新私有恢复目录与新数据库路径，核验版本1、完整性、外键和旧版启动兼容性，仅清理恢复副本会话，8001端口启动旧应用。原有schema 2恢复步骤明确只用于schema 2。此文档流程未对实际用户库执行，也未宣称已进行真实回退演练。

本次仅运行修改涉及的两个模块：

```bash
.venv/bin/python -m unittest tests.test_supervisor_identity tests.test_backup -v
```

结果：**23项通过、0跳过、退出码0**。[完整输出](identity/10-review-patch.log)、[真实退出码](identity/10-review-patch.exit)、[本次源码摘要](identity/10-review-patch-sha256.json)。未重跑完整套件或无关JS/浏览器测试；此前所有日志与摘要保留。

## 主流程修补后收口

独立三层首轮复核后，主流程已逐项裁决并复现路径/触发器问题；修补后完整Python套件 **225项通过、0跳过**，运行期间源码未变化。原始输出见[完整回归](identity/parent-final-python.log)，[退出码及源码指纹](identity/parent-final-python.json)。auth JS此前4项通过且JS未变。本故事的身份基础和迁移能力接受，未把审批等后续故事算作完成。

矩阵覆盖：合法身份/teacher权限→test_three_roles_bindings_login_and_teacher_denied_admin；非法映射→test_invalid_mappings_reject_entire_batch_and_single_account_add_supported；重复→test_repeat_is_add_only_and_never_repairs_old_binding；旧库→test_real_schema1_migration_preserves_all_facts_and_history_readability；失败→test_migration_failure_after_rebuild_rolls_back_and_backup_is_restorable及新增路径/自定义对象/触发器测试；伪造→test_client_cannot_set_role_or_supervisor_and_session_reads_database。上述均在完整回归真实运行并通过。
