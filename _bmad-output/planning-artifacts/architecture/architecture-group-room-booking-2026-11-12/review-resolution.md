# 架构评审修复记录

日期：2026-11-12。作者：architecture_stage（AI）。三份独立原报告保持原样：`reviews/review-rubric.md`、`reviews/review-reality.md`、`reviews/review-adversarial.md`。原始发现合计2 high、5 medium、1 low；审计与DTO在两个镜头重复出现，共6个独立问题。以下全部采纳，没有把AI否决计作人类决定。

| 原发现 | 处理 | 最终证据位置与内容 |
| --- | --- | --- |
| AR-01 / ADV-01 | 已修复，同一问题合并落实 | architecture.md §5.3第6步只准备事件，第7步为唯一调用点；§5.4固定audit_writer(conn,event)->None、同一事务连接、writer只INSERT且禁止连接/事务管理、db助手禁止附加审计。spine AD-3/7及project-context 3/12/14同步。真实变更1次、重放/重复/无变化0次的实现验收已列§8.3。 |
| AR-02 / ADV-02 | 已修复，同一问题合并落实 | §4固定CreateBookingResult与服务/web分工；§6.3完整列出BookingFull、BlockFull、AuditEvent、ScheduleItem、nullable字段及Room嵌套类型，web只加一层ok/data；§7逐接口引用DTO。取消外部cancelled、撤销外部revoked，审计before/after为对象。contract-examples.json含12个完整JSON案例，contract-validation.json记录实际静态检查。 |
| AR-03 | 已修复 | §7明确1000仅为性能验收负载，无存储/保留/创建上限；spine Deferred将分页定为以后显式合同变更；project-context 14同步当前列表全部匹配。 |
| R-REALITY-01 | 已修复 | §5.2及§7统一所有路径/查询/JSON ID为1至9223372036854775807，SQL绑定前检查，超长文本先检查长度再转int；越界400、范围内不存在404，鉴权优先。spine IDs/project-context 13同步；边界验收列于§8.3。未把评审者的SQLite探针当成本应用测试。 |
| ADV-03 | 已修复 | §5.1定义所有非NULL标记列NOT NULL；reservations完整kind矩阵明确booking.user_id=所有者、block.user_id=创建管理员且都非空；专属字段必须NULL/有值，取消人/时刻成对，成员/管理员/撤销原因语义明确。cancelled_by FK users，服务承担无法用CHECK识别的路由语义。spine AD-3/context 4同步。 |
| ADV-04 | 已修复 | §5.2统一Clock接口涵盖auth/查询/业务/测试；§6.1规定锁外验hash、锁内重读有效临时会话并原子消费/创建；commit后签发cookie，同token并发最多一个200，其余401且不覆盖cookie；失败回滚保留旧临时行。退出短事务commit后清cookie，失败不声称成功。spine AD-2/5、context 5/8及§8.3同步。 |

附带交接澄清：实际SQLite链接版本与Asia/Shanghai数据在启动时检查；.python-version不能替代这些检查。课程C-03更新为8条ADR/16条具体规则已形成，教师M2未被声称通过。最终schema允许按故事逐步引入表，不要求首故事一次完成全部基础设施。两个实验候选命令继续独立，不合并、不提前实现。

## 实际验证及边界

- 本次作者重新运行官方lint_spine.py，结果见lint-result.json：0 findings。
- 实际解析12个JSON案例，检查HTTP只包装一层、BookingFull/BlockFull精确键、共享日程kind/record及隐私、AuditEvent对象快照；结果见contract-validation.json。此检查只验证文档夹具，不验证尚未实现的服务。
- 通过真实resolve_config.py、resolve_customization.py再次保存resolved-config.json/resolved-customization.json；memlog.py append保留每项取舍和最终事件，不覆写原始决策历史。
- 没有应用代码、数据库业务数据或Git变更；没有声称NFR通过，没有伪造人工评审。原独立报告未在修复后重新签发；本表是作者对明确发现的修复闭环，不能冒称独立再验收。

## 冻结结论

全部有效发现已落实，无剩余阻塞的架构问题。spine、architecture.md及project-context.md设为final，表示本次架构工作流完成，可供故事与实现使用；教师门禁、应用测试、运行度量和真实使用反馈仍按后续实际证据判断。非阻塞业务待验证项继续保留PRD OQ-01—03。
