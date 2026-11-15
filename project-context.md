---
project_name: group-room-booking
created: 2026-11-12
updated: 2026-11-15
status: approved-implementation-in-progress
source: _bmad-output/planning-artifacts/architecture.md
---

# 实现上下文与必须遵守的规则

2026-11-15规则修订依据U-38/U-39批准方案，描述Epic4必须达到的目标；尚未通过的新增能力不视为完成。旧规则版本与原实验A保持Git历史。

读 [PRD](_bmad-output/planning-artifacts/PRD.md)、[架构](_bmad-output/planning-artifacts/architecture.md) 与 [spine](_bmad-output/planning-artifacts/architecture/architecture-group-room-booking-2026-11-12/ARCHITECTURE-SPINE.md) 后再实现。以下是具体规则，不替代上游协议。

1. 固定 Python 3.12.14、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.9、Waitress 3.0.2；当前 Python 链接 SQLite 3.53.1。生成真实依赖锁，运行证据记录实际版本；不把基线说成所有组件最新。（AD-1/8）
2. 依赖方向 web→services→db，services→domain；domain 不依赖 Flask。页面和API共用服务，路由不写业务 SQL/commit；不接入云服务。（AD-1）
3. 所有业务写 `BEGIN IMMEDIATE` 后读可变状态，业务、槽、审计同事务；任何异常回滚。每请求独立 SQLite 连接，foreign_keys=ON、busy_timeout=15000、synchronous=FULL；本地盘 WAL，不能用网络共享盘。（AD-3/8）
4. 已确认预约/停用共用 reservations，occupancy_slots 主键 `(room_id,slot_start)`，每1800秒一槽。待审申请独立存储、零槽；批准才创建预约/槽；周期全部场次同事务成功。取消只删对应槽、保留历史；禁止 OR REPLACE/IGNORE 吞冲突。（AD-2/3，D-006/017/022）
5. UTC整数秒存储、北京时间输入展示、统一Clock；写锁后一次取t。普通/周期首场满足 t<start<end<=t+7天，半点同日30分钟至4h；周期后续每7天同一时段最多8场，可超首场7天限制。停用独立保持30天，可跨日不限4h。不能从客户端取当前时间。（AD-2，D-007/008/009/017）
6. 用户作用域持久意图，先按规范化payload重放成功申请/预约再新建校验；周数省略=1，改变周数是新内容。失败提交不留key，已成功待审申请批准冲突仍保留原key/记录；取消、开始后旧成功意图仍可重放。跨入口不能导致重复占用或跨用户泄漏。（AD-4）
7. actor来自会话，写锁内复核身份及可信导师关系。学生申请/取消由本人导师处理，其他导师/admin不可代批；admin可全局查看与合法管理取消。完整详情学生本人、导师本人及自己学生、admin；共享日程仅白名单。导师本人/admin旧直订保留，学生不得旧API绕过。（AD-5/6/7，D-006/010/013/018/023）
8. 口令 scrypt；cookie使用32字节安全随机token，DB只存SHA-256摘要；会话绝对8h；登录锁外验密码、锁内复核/消费临时会话并原子插入新会话；相同临时token仅一成功，失败不改cookie；退出短事务删除。认证只在commit后签发/清cookie。所有POST包括登录退出都检查精确APP_ORIGIN与CSRF，cookie HttpOnly/SameSite=Lax；HTTPS加Secure。（AD-5）
9. 共享预约只返回房间、活动名、预约人显示名、所属导师显示名、起止及占用状态；不得发用途/人数/账号/审批取消原因后再隐藏。导师归属来自可信关系/历史快照，不猜历史未知值。模板转义、textContent，不用safe/innerHTML处理用户文本。（AD-6，D-012）
10. 学生获批预约取消先申请、占用不变，本人导师必须t<start确认才释放；拒绝后允许重新申请、旧处理保留。导师/admin自己的预约t<start直取消，admin管理取消/撤销停用t<end且必须原因。先授权/原因校验再幂等，重复不改首事实；管理取消须同步终结待确认请求。冻结实验A不能重写。（AD-7，D-010/014）
11. 降容量保护所有未结束有效预约含进行中，待审申请不阻挡、批准重验。维修先预览具体冲突、一次原因与显式确认；确认时集合或条件变化需重预览，不能静默扩大取消；与有效停用冲突仍拒绝。批量取消、终结取消请求、停用、槽及各审计全成全败，撤销不恢复旧预约。（AD-3/7，D-015/016）
12. 命令负责审计，writer(conn,event)只用当前事务conn INSERT，不开连接/管理事务/再次审计。每个真实对象转换一事件，一次批准/批量命令可多个事件但全原子；重放/无变化0事件。旧快照仍可读取、不重写历史；不写凭据/完整请求头。课程期间全部保留。（AD-7，D-021）
13. v2精确DTO/状态/API由各批准故事实施合同及对应夹具共同维护；旧架构v1键集合不覆盖新版合同。services只返回领域数据，web包装一层ok/data，不能直接序列化DB行。ID 1至2**63-1，鉴权优先，类型/范围错误400；人数拒bool/float/string，文本strip且安全，500无SQL/堆栈。历史DTO版本兼容须测试。（AD-1/6）
14. 测试使用可注入Clock与审计writer，但生产无HTTP测试后门。并发/重启用文件DB、独立连接与最终存储断言，不能只断言HTTP；保留全部性能样本；1000仅是验收负载，不能当作数据保留/创建上限；当前列表不分页。（AD-8，NFR-01—04）
15. Waitress默认只监听127.0.0.1:8000、8线程，关debug/reloader。备份用SQLite backup API，停服恢复后清会话；instance/真实凭证/备份不入Git。（AD-8）
16. 每个故事引用FR/NFR和ADR，记录真实状态变化与测试证据。AI技术备选否决不能冒充人类否决；实验B免做，实验A先登记隔离协议；AI review不能冒充教师M1/M2。（课程C-02—08）
