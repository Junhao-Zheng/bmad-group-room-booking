# 需求与验收追踪矩阵

编号引用规划基线。功能是否完成以故事状态、实际测试输出和对应评审记录共同判断；12张故事均已完成技术验收；下列证据按其实际版本保存，未将历史测试数相加。

|需求|主要设计依据|故事|主要验证入口|
|---|---|---|---|
|FR-01 预置账号|ADR-05/08|1.1|test_auth 初始化/重复初始化、verify_auth_http；[用例](../tests/test_auth.py) / [证据](evidence/story-1.1-verification.md)|
|FR-02 登录|ADR-05|1.1|test_auth 凭证/会话旋转、test_auth_js、真实HTTP及浏览器；[用例](../tests/test_auth.py) / [证据](evidence/story-1.1-post-review-verification.md)|
|FR-03 会话退出|ADR-05|1.1；后续写入复核|过期/退出/旧cookie/独立会话、锁后时刻测试；[用例](../tests/test_auth.py) / [证据](evidence/story-1.1-post-review-verification.md)|
|FR-04 服务端授权|ADR-05/06|全部业务故事|每条API的匿名/失效/member A/B/admin权限矩阵；[用例](../tests/test_audit.py) / [证据](evidence/story-3.4-verification.md)|
|FR-05 目录|ADR-01/06|1.2|test_room_schedule 稳定排序/精确Room DTO/空目录；[用例](../tests/test_room_schedule.py) / [证据](evidence/story-1.2-verification.md)|
|FR-06 可用性|ADR-02/03|1.3|test_availability、verify_availability_performance；[用例](../tests/test_availability.py) / [证据](evidence/story-1.3-reviewed-verification.md)|
|FR-07 共享日程|ADR-02/06|1.2|test_room_schedule 半开区间/跨日/隐私及浏览器；[用例](../tests/test_room_schedule.py) / [证据](evidence/story-1.2-verification.md)|
|FR-08 创建|ADR-01/03/07|2.1|test_create_booking、verify_create_booking_http；[用例](../tests/test_create_booking.py) / [证据](evidence/story-2.1-verification.md)|
|FR-09 时间边界|ADR-02|1.3/2.1|严格时间、当前/30天/半小时/4小时/午夜边界；[用例](../tests/test_create_booking.py) / [证据](evidence/story-2.1-verification.md)|
|FR-10 人数|ADR-03|1.3/2.1|纯JSON整数/等容量/超容量/大整数拒绝；[用例](../tests/test_create_booking.py) / [证据](evidence/story-2.1-verification.md)|
|FR-11 互斥|ADR-03|2.1/2.4/3.2/3.3|不同意图20并发、完整槽、预约对停用竞争；[用例](../tests/test_create_booking.py) / [证据](evidence/story-3.2-verification.md)|
|FR-12 重放|ADR-04|2.2|相同意图20并发、取消/开始后重放、响应丢失；[用例](../tests/test_replay_intent.py) / [证据](evidence/story-2.2-verification.md)|
|FR-13 个人记录|ADR-02/06|2.3|四态/边界/排序/本人及管理员详情；[用例](../tests/test_personal_history.py) / [证据](evidence/story-2.3-verification.md)|
|FR-14 本人取消|ADR-07|2.4|所有权合并404/开始期限/重复/槽释放/回滚；[用例](../tests/test_member_cancel.py) / [证据](evidence/story-2.4-verification.md)|
|FR-15 管理干预|ADR-07|2.5 实验X|原因/权限/结束期限/幂等/成员对管理员取消竞争；[用例](../tests/test_admin_cancel.py) / [证据](evidence/story-2.5-verification.md)|
|FR-16 资源维护|ADR-01/07|3.1|字段/唯一组合/稳定ID/原子审计；[用例](../tests/test_room_management.py) / [证据](evidence/story-3.1-verification.md)|
|FR-17 容量保护|ADR-03/07|3.1|未结束含进行中保护、预约对降容量20轮；[用例](../tests/test_room_management.py) / [证据](evidence/story-3.1-verification.md)|
|FR-18 停用|ADR-03/07|3.2|跨日/窗口/冲突不覆盖、预约对停用20轮；[用例](../tests/test_maintenance_block.py) / [证据](evidence/story-3.2-verification.md)|
|FR-19 撤销|ADR-07|3.3 实验Y|原因/结束期限/幂等/槽释放/历史及回滚；[用例](../tests/test_block_revoke.py) / [证据](evidence/story-3.3-verification.md)|
|FR-20 管理查询|ADR-02/06|3.2|房间/日期/四态筛选与精确Full DTO；[用例](../tests/test_maintenance_block.py) / [证据](evidence/story-3.2-verification.md)|
|FR-21 操作记录|ADR-07/08|2.1起全部写入；3.4查询|每转换恰一次、完整事实快照、故障全回滚、管理员筛选；[用例](../tests/test_audit.py) / [证据](evidence/story-3.4-verification.md)|
|FR-22 失败恢复|ADR-01/04/06/07|全部交互故事|标准错误码/安全正文/保留输入/20秒超时/不自动重提；[用例](../tests/test_booking_js.cjs) / [证据](evidence/story-2.2-verification.md)|
|NFR-01 一致性|ADR-03/04/07|2.1/2.2/2.4/2.5/3.1/3.2|两组20请求、三种双请求竞争各20轮及最终数据库；[用例](../tests/test_create_booking.py) / [证据](evidence/story-3.4-verification.md)|
|NFR-02 认证安全隐私|ADR-05/06|1.1起全部业务|全路由身份矩阵、Origin/CSRF、XSS文本、哈希及敏感信息检查；[用例](../tests/test_audit.py) / [证据](evidence/story-3.4-verification.md)|
|NFR-03 查询性能|ADR-02/03/08|1.3|固定10房间1000记录、10客户端、20预热200实测、最近秩P95；[用例](../tests/test_availability_performance.py) / [证据](evidence/story-1.3-reviewed-verification.md)|
|NFR-04 持久追溯|ADR-04/07/08|3.4整体验收|实际停止/新PID重启、字段/数量/事件关联比对、旧意图及审计失败；[用例](../tests/test_audit.py) / [证据](evidence/story-3.4-verification.md)|

每行的用例是主要入口，跨故事矩阵和实际HTTP/浏览器补证见[验证索引](verification.md)。实验X/Y的冻结初稿表现与修复后的产品验收分开记录。最终通过结论仍需结合全量执行日志，不能仅由文件存在推断。
