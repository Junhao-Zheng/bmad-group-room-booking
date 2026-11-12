# Architecture Adversarial Review

日期：2026-11-12。角色：独立架构对抗评审。依据 `bmad-architecture/references/reviewer-gate.md` 的跨单元一致性检查及配置中的 adversarial reviewer 指令。

完整审阅：本 run 的 `ARCHITECTURE-SPINE.md`、`../../architecture.md`、项目根 `project-context.md`。审阅时均为 draft。未改架构、代码或 Git；未执行应用测试；下列反例为契约推演，不冒充运行时缺陷。版本与外部技术核验由并行的技术核验评审负责，本评审不重复推断“最新版本”。

## Verdict

**建议收紧契约后交接实现。** 单文件数据库、统一占用槽、锁后判定、持久幂等、先授权后取消及历史保留已形成一致方向；没有发现需要推翻单体或 SQLite 选择的问题。仍有 **2 项 high、2 项 medium** 的单元交接缺口：不同实现分别满足当前 AD 的语义，组合时却可能重复写审计、无法解释 DTO、拒绝合法停用，或在测试/认证边界采用不同的时间与事务规则。

`admin_cancel_booking` 与 `revoke_block` 是已预登记实验 A 的独立命令，本评审不要求合并它们。以下补强只约束共享基础协议，不预写目标命令实现或泄漏对照组。

## ADV-01 [high] 审计“恰好一次”的结果已规定，调用和事务所有权没有闭合

**位置：** AD-3、AD-7、AD-8；详版 §4、§5.3 第 6/7 步、§5.4、§8.3；project-context 3/12/14。

**两个可独立成立的单元：**

- 状态转换单元 A 按 §5.3 第 6 步实现 `UPDATE→DELETE slots→插一条审计`；它调用 `audit_writer(connection, event)`，并在自己的命令测试中断言一次真实转换只有一条审计。
- 事务封装单元 B 按第 7 步把“插入成功变更对应 audit_events”作为统一提交钩子，命令返回变更事件后由钩子调用 `audit_writer(event)`；它在事务助手测试中也只写一条审计，假定命令尚未落审计。

两者都可以在各自测试中遵守“同事务、一条审计、异常回滚”，当前文字没有指定事件由谁交付、谁调用 writer、writer 的签名及其连接来源。集成后可能发生重复审计；若作者选择不同注入签名，则首次合法业务操作会因 TypeError 回滚为 500。如果 writer 自己通过 db helper 新建连接，外层正在持有写锁时还可能等待另一写入；“同事务”要求会在组合时才被破坏，而单个接口没有机械方式防止它。

**必要 tightening：**指定一个唯一协议，例如 `audit_writer(conn, event)`，其中 `conn` 必须是该命令当前事务连接，writer 不得打开连接、BEGIN、COMMIT 或 ROLLBACK；业务命令负责构造事件且只调用一次，db 事务助手只负责事务生命周期，不另加审计。§5.3 第 6 步改为“准备变更事件”，第 7 步明确一次写入；或反向选择命令内写入并删除公共尾步的重复含义。具体选择不限，但两处必须一致。保留两个管理命令的独立实现和测试。

**交接验证：**共享假 writer 接收同一个 conn 及事件，记录调用次数；每个真实转换为 1，重放/重复取消/撤销/无变化更新为 0；失败 writer 抛异常后业务、槽、审计均未提交。该 probe 验证接口，不替代实验目标故事。

## ADV-02 [high] 完整 DTO 和创建服务结果不是可直接对接的形状

**位置：** AD-1、AD-6、Consistency Conventions；详版 §4 服务表、§6.3、§7。

**两个可独立成立的单元：**

- `create_booking` 单元 A 按 §4 返回“BookingFull，含 replayed”，采用 `{id, room: 3, start_at, start_local, ..., replayed:false}`；`room` 是房间引用，所有时间仍为规定的 epoch/local 双字段，权限和白名单语义正确。
- web/页面单元 B 把 BookingFull 的 `room` 理解为完整 `Room` 对象，并把“含 replayed”理解为服务已经返回 `{booking: BookingFull, replayed:false}`；它按 §7 直接将该服务结果包装到 `data`，页面访问 `data.booking.room.name`。

当前 §6.3 对 Room、BookingShared、BlockShared 给了具体键，但 BookingFull 使用“room”“start/end”等语义列举，未固定 `room` 的类型、完整键集合和服务层的返回 wrapper。§4 与 §7 对 replayed 所在层级也未明确区分。上述单元都能展示同样信息并遵守授权，集成却产生缺字段或双层 wrapper。

同类缺口存在于管理员的完整停用结果：没有 `BlockFull` 契约。一个实现直接公开 `cancelled_at/cancel_reason`，另一个消费者用业务术语读取 `revoked_at/revoke_reason`；两者均使用 AD-2 规定的时间和 `revoked` 展示状态，却无法对接。共享日程还应明确它返回 BookingShared/BlockShared 的何种联合表示，不能要求下游自行发明 `kind` 或依靠未约定的键存在性判断类型。

**必要 tightening：**给出完整、可序列化的 BookingFull、BlockFull、CreateBookingResult 和 ScheduleItem 键/类型/可空字段，明确服务返回与 HTTP `data` 包装由哪一层负责。选择 flat 或 nested 均可；统一取消/撤销元数据映射，指定 schedule 的 discriminator 或确定的联合判别规则。任何新增共享字段须同步隐私白名单，不能直接暴露数据库行。

**交接验证：**为成功创建、重放、已取消本人记录、已撤销管理停用及混合日程各给一个精确 JSON 示例；以同一 DTO fixture 对接服务与 web/页面，断言无缺失/多余受限字段及正确 wrapper。

## ADV-03 [medium] reservations 的 kind 字段矩阵还允许 schema 与停用命令选择不同的空值语义

**位置：** AD-3、AD-6、AD-7；详版 §5.1 reservations 行及其 CHECK 段、§4 create_block。

**两个可独立成立的单元：**

- schema 单元 A 将 `user_id` 视为两种记录共同的创建人，设为 NOT NULL/FK users；`block` 仅把 title/purpose/attendees/intent_key/request_payload 设为 NULL。
- 停用单元 B 将 `user_id` 视为预约人，按“block 要 reason 非空，其余业务字段/key/payload NULL”把停用的 user_id 留空，创建管理员只写在 audit_events.actor_id；它仍满足管理员授权、完整占用槽、原因和同事务审计。

两种模型都与共表、占用主键及业务能力兼容，但组合时 B 的合法停用被 A 的 NOT NULL 拒绝，成为 500；宽松 schema 下还会使查询者不知道 user_id 对 block 是否可靠。同一表中多数公共列未显式写出 NOT NULL，取消列又用“三字段一致，成员取消 reason 可 NULL”的概括，进一步把需要共享的约束留给独立作者解释。

**必要 tightening：**列出 booking/block 的字段矩阵：每一列说明必须有值、必须为 NULL、可空，以及 user_id 对两种 kind 的语义。建议两种记录都保留创建 actor id；block 专属 reason 必填，booking 的 title/purpose/attendees/key/payload 必填，其他分支字段显式 NULL。取消元数据明确 `cancelled_at` 与 `cancelled_by` 同空/同有值，成员取消原因可空、管理员取消和停用撤销原因必填；明确相关 FK。该补强不需要提前实现完整 schema，但共享写入者不能自行选择。

**交接验证：**同一字段矩阵生成 booking/block 的有效初始与终态例子；schema 和命令输入适配使用相同例子，避免在业务故事开发时才发现 NOT NULL/CHECK 不兼容。

## ADV-04 [medium] 会话属于共享持久状态，但认证命令尚无与业务命令同等明确的 Clock/事务边界

**位置：** AD-2/3/5/8；详版 §5.3、§6.1、§8.3；project-context 5/7/8/14。

**两个可独立成立的单元：**

- auth 单元 A 依据 §6.1 实现临时会话及 8h 登录会话，以其自己的服务器时钟计算 created_at/expires_at；先在口令哈希前校验预认证会话，然后顺序执行旧会话删除与新会话插入。它遵守随机凭证、摘要存储、轮换、绝对期限及当前会话退出规则。
- 业务/测试单元 B 根据 §5.2/5.3 和 §8.3，在写锁内使用注入 `CLOCK.now_epoch()` 复核认证会话，并以固定基准时钟跑取消/到期边界。它假定 auth 的写入、预认证消费和时间也遵循同一 Clock/短事务助手。

AD-2 的 Binds 主要落在 FR-06—19，详版明确“服务从注入 Clock 取得 t”，而 §6.1 的登录 `t` 来源及会话写入没有单列协议；认证又被明确排除在 FR-21 业务审计之外，不能无条件套用要求已认证 actor/业务审计的整个 §5.3 流程。两种作者选择各自合理：单元测试中登录能成功，但集成的固定时间可能把会话立即判过期或延长其测试生命周期。

此外，两个并发登录可在哈希前都读到相同的预认证会话：如果最终写入不在短事务内重读并消费它，后一个请求即使旧会话已经不存在仍能创建另一登录会话。本文并未明确一次性消费的线性化点，也未规定删除成功但新插入失败时是否允许部分轮换；这不是要求禁用独立多会话，而是需要明确同一预认证凭证的使用边界。

**必要 tightening：**规定生产与测试下认证/查询/写入的全部时间均来自同一 Clock 接口，返回 int epoch 秒，`t >= expires_at` 即失效。认证专用短事务可共享 db helper，但不要求已认证 actor，也不生成业务审计：哈希验证在锁外；取得写锁后重新读取预认证会话、以该次 t 复核期限/状态，原子消费旧会话并插入新会话，只有消费成功才签发 cookie。退出删除与其成功响应的顺序同样固定，busy/失败不声称完成。若决定不采用一次性预认证消费，也应明确并发允许语义并写对应断言，而不是由两组代码自行猜测。

**交接验证：**固定 Clock 覆盖登录与服务，验证到期等号；同一预认证 token 的并发登录结果按选定语义断言；轮换插入失败不留下已声明成功的认证结果。不会新增 HTTP 设时钟或故障后门。

## 已闭合且不再制造发现的边界

- UTC 整数秒、30 分钟槽、半开区间、跨日停用、预约同日与 4h、取得写锁后捕获 t、状态优先 cancelled/revoked 已有明确规定；不建议在这些点增加重复 AD。
- 共表与 `(room_id,slot_start)` 主键阻止预约/停用互相绕开，容量降低检查未结束记录与创建处于同一写序列，方向可执行。
- 幂等 payload 的固定键、JSON 规范化、用户作用域、成功后先重放再检查当前时间/容量均已给出，不将该部分重复报缺口。
- 取消/撤销先授权与原因校验，再重复结果返回，保留首成功元数据；独立管理命令符合实验 A 边界。
- 本地盘、WAL、连接配置、备份恢复、生产禁止 HTTP 测试后门和真实 NFR 证据要求已经覆盖运维维度。

本报告只提出上述 4 个共享契约补强，没有要求增加支付、审批、周期预约、云基础设施或生产级账号管理。
