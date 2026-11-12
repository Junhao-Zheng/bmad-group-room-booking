---
project_name: group-room-booking
created: 2026-11-12
updated: 2026-11-12
status: final
source: _bmad-output/planning-artifacts/architecture.md
---

# 实现上下文与必须遵守的规则

读 [PRD](_bmad-output/planning-artifacts/PRD.md)、[架构](_bmad-output/planning-artifacts/architecture.md) 与 [spine](_bmad-output/planning-artifacts/architecture/architecture-group-room-booking-2026-11-12/ARCHITECTURE-SPINE.md) 后再实现。以下是具体规则，不替代上游协议。

1. 固定 Python 3.12.14、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2；当前 Python 链接 SQLite 3.53.1。生成真实依赖锁，运行证据记录实际版本；不把基线说成所有组件最新。（AD-1/8）
2. 依赖方向 web→services→db，services→domain；domain 不依赖 Flask。页面和API共用服务，路由不写业务 SQL/commit；不接入云服务。（AD-1）
3. 所有业务写 `BEGIN IMMEDIATE` 后读可变状态，业务、槽、审计同事务；任何异常回滚。每请求独立 SQLite 连接，foreign_keys=ON、busy_timeout=15000、synchronous=FULL；本地盘 WAL，不能用网络共享盘。（AD-3/8）
4. 预约/停用共用 reservations，两类user_id均为非空创建actor.id，分支及取消字段按架构§5.1空值矩阵；occupancy_slots 主键 `(room_id,slot_start)`；slot为半开区间内每1800秒一行。取消只删槽保留历史，禁止 OR REPLACE/IGNORE 吞冲突。（AD-2/3）
5. 时间存 UTC 整数秒；输入只接受北京时间 `YYYY-MM-DDTHH:MM`，分钟00/30。认证、查询、业务共用 Clock.now_epoch()->int，t>=expires_at失效；事务取锁后获取一次t；不得从客户端读取“当前时间”。预约同日≤4h，停用可跨日，均严格执行PRD 30天窗口。（AD-2）
6. `(user_id,intent_key)` 持久唯一，先按规范化 payload 重放成功记录再进行新建的时间/容量检查。失败不留key；取消或已开始的旧意图仍返回原ID当前状态；不同payload409。（AD-4）
7. actor 来自服务端会话；写事务内复核会话有效性。成员所有权和管理员角色在服务检查；本人路由对不存在/他人统一404。管理员取消自己通过成员路由仍按开始前期限。（AD-5/6/7）
8. 口令 scrypt；cookie使用32字节安全随机token，DB只存SHA-256摘要；会话绝对8h；登录锁外验密码、锁内复核/消费临时会话并原子插入新会话；相同临时token仅一成功，失败不改cookie；退出短事务删除。认证只在commit后签发/清cookie。所有POST包括登录退出都检查精确APP_ORIGIN与CSRF，cookie HttpOnly/SameSite=Lax；HTTPS加Secure。（AD-5）
9. 共享预约只返回白名单字段，禁止用途/人数/账号名/取消原因。所有模板自动转义，不使用 safe/innerHTML处理用户文本；不要直接JSON序列化数据库行。（AD-6）
10. 先验证权限及管理员原因，再幂等取消/撤销；重复不改原原因/操作者/时间、不加审计。首次成员取消 t<start，管理员取消/撤销 t<end。两个管理命令独立实现，实验A选定前不要预先实现它们。（AD-7）
11. 降容量在同写事务检查所有未取消且end>t预约（含进行中）；有任何超员则整次修改拒绝。停用冲突不得自动取消预约。（AD-3/7）
12. 命令独占审计调用点：audit_writer(conn,event)->None，只用当前事务conn执行一次INSERT，不新建连接或管理事务；事务助手不加审计。记录actor显示名快照和必要前后值；不写口令、cookie、CSRF、token摘要或完整请求头。重放/无变化操作不创造假审计。（AD-7）
13. API路径、精确DTO/空值、状态、错误码以架构§6—7为准；服务不包ok/data，web只包一层；创建返回{booking,replayed}，日程返回{kind,record}；所有ID限1至2**63-1，SQL前拒绝超范围400（鉴权优先）；JSON人数拒绝bool/float/字符串；字符串strip后按Unicode code point计数，不截断。500不泄露堆栈/SQL。（AD-1/6）
14. 测试使用可注入Clock与审计writer，但生产无HTTP测试后门。并发/重启用文件DB、独立连接与最终存储断言，不能只断言HTTP；保留全部性能样本；1000仅是验收负载，不能当作数据保留/创建上限；当前列表不分页。（AD-8，NFR-01—04）
15. Waitress默认只监听127.0.0.1:8000、8线程，关debug/reloader。备份用SQLite backup API，停服恢复后清会话；instance/真实凭证/备份不入Git。（AD-8）
16. 每个故事引用FR/NFR和ADR，记录真实状态变化与测试证据。AI技术备选否决不能冒充人类否决；实验B免做，实验A先登记隔离协议；AI review不能冒充教师M1/M2。（课程C-02—08）
