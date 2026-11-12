# Architecture Review — Rubric, Structure and Prose

## Gate verdict

核心架构可实现，建议在交接故事前直接修正两项共享协议歧义；没有严重或高优先级的架构阻塞问题。共 2 项 medium、1 项 low；这只是独立 AI 文档评审，不是代码测试结果或教师 M1/M2 批准。

审阅范围：`ARCHITECTURE-SPINE.md` 全文、执行附件 `architecture.md` 全文、`project-context.md`，并核对当前 `PRD.md`、`docs/course-scope.md`、`ux-designs/course/DESIGN.md` 与 `EXPERIENCE.md`。采用 good-spine checklist；另按配置的 bmad-review structure、prose 镜头顺序审阅表达。管理员取消预约与撤销停用保持两个独立命令，符合实验 A 的既定交接边界，本报告不建议合并。

## Critical / high

无。

## Medium / low findings

### AR-01 — 顺序协议重复指定取消审计写入

- **Severity:** medium
- **Location:** `architecture.md` §5.3 第 6、7 步（122—123 行）；spine AD-7；`project-context.md` 第 12 条。
- **Evidence:** 第 6 步明确要求“UPDATE cancelled_at/by/reason、DELETE 该 reservation_id 的槽、插一条审计”，紧接着第 7 步又要求“插入成功变更对应 audit_events”。其他约束要求每次真实状态转换恰好一条审计。
- **Consequence:** 将编号步骤直译为服务流程的实现者可能在取消/撤销分支插一次，再由公共收尾插一次，违反 FR-21 和 NFR-01 的单次转换审计要求；另一实现者则可能自行解释为复述。共享执行协议不应依赖这种判断。
- **Disposition:** autofix。
- **Fix:** 将审计唯一责任集中到一个步骤。建议第 6 步只修改取消元数据和释放槽，并产生待记审计事件；第 7 步仅对发生真实变更的命令写该事件一次再提交，重放、重复取消/撤销及无变化更新显式跳过。保留两个独立管理命令及各自测试，不改变业务边界。
- **Verification:** 对成员取消、管理员取消和撤销停用分别断言首次成功增加 1 条审计、重复请求增加 0 条；并发取消只增加 1 条。该建议是未来验收要求，本次未运行这些测试。

### AR-02 — 共享输出契约尚不足以供界面与管理查询独立实现

- **Severity:** medium
- **Location:** `architecture.md` §6.3（153—155 行）与 §7（178—190 行）；spine AD-6、Consistency Conventions 的 Contract authority；PRD FR-19—21。
- **Evidence:** `BookingFull` 将时间写成 `start/end`，同段又要求“所有时间始终同时提供 UTC `*_at` 及无歧义 `*_local`”；`BlockShared` 有字段集合，但“撤销完整信息仅管理查询”没有对应 `BlockFull` 字段契约；管理员停用和审计列表/撤销响应均没有明确所返回对象的完整字段与空值语义。
- **Consequence:** 页面与服务可分别选择 `start` 或 `start_at`、`cancelled_at` 或 `revoked_at`、直接返回存储的 `before_json` 字符串或已解析对象，最终同样自称遵守架构，却无法无歧义对接。尤其两个独立实验候选命令涉及取消/撤销结果，更需要固定输出协议，而非由故事各自补齐。
- **Disposition:** autofix。
- **Fix:** 在 §6.3 列出精确 `BookingFull`、`BlockFull`、`AuditEvent` 字段表及类型/可空性，统一所有时间字段名称；明确取消与撤销的外部字段命名以及审计 before/after 的 JSON 对象语义。在 §7 逐项引用 DTO，并说明首次取消/重复取消、首次撤销/重复撤销返回相同种类的完整对象。共享列表若混合两类对象，应明确列表元素如何区分类型，同时保留现有共享字段白名单，不借此增加敏感字段。
- **Verification:** 用固定样例列出创建预约、取消预约、创建停用、撤销停用、管理列表和操作记录的响应形状，使前后端故事可引用同一合同；相关契约断言留到实现阶段。

### AR-03 — 1,000 条性能夹具被表述为首版数据规模事实

- **Severity:** low
- **Location:** `architecture.md` §7 末段（192 行）；对照 PRD NFR-03、OQ-01/03。
- **Evidence:** “第一版数据规模仅1,000，固定返回全部匹配记录”将基准测试负载写成了产品实际规模或硬上限。PRD 明确 1,000 条预约只是验收设计值，并要求原型历史持续保留，未规定累计记录上限。
- **Consequence:** 下游可能误把 1,000 当成保留/拒绝新记录的阈值，或将该基准结果外推为实际规模保证。当前暂不分页的实现选择本身不需要推翻。
- **Disposition:** autofix。
- **Fix:** 改为“本版以 1,000 条预约作为性能验收负载；列表暂返回全部匹配记录，不设 1,000 条存储或保留上限。后续增加分页时保持稳定排序与隐私约束。”同步将 spine Deferred 中的“分页组件”限定为后续变更，不让当前故事误改已固定的 API 列表协议。

## Good-spine checklist judgments

| Checklist dimension | Judgment | Evidence |
| --- | --- | --- |
| 固定下游真实分歧点 | adequate | 分层依赖、事务、时间单位、唯一占用、成功意图持久化、权限、部署都已固定；AR-02 指出少数输出 DTO 仍可分叉。 |
| 每条 Rule 可执行并阻止其 stated divergence | adequate | AD-2/3 用 1800 秒整槽与唯一主键防重叠，AD-3/7 将容量、业务和审计置于同一写锁序列；AR-01 是执行附件的一处重复写入表述，应与单次审计规则统一。 |
| Deferred 不把共享决定下放到故事 | adequate | 云部署、多机、真实资源和使用制度有明确条件，当前本机边界无需新的人类决定；列表当前不分页已经在附件固定，应按 AR-03 消除尾部措辞歧义。 |
| 命名技术有当前可核验依据 | strong | 栈版本可在官方页面核验；本机实际 Python/SQLite 与记录一致。Python 基线没有宣称最新。详见核验记录。 |
| 与现有实现相容 | n/a | 本次是未实施原型的架构基线；本报告没有声称对既有应用代码作兼容性验证。 |
| 覆盖来源需求和 UX | strong | FR-01—22、NFR-01—04 有能力映射；查询快照、未知响应重试、成员/管理取消权限、跨日停用、容量保护、共享字段、失败保留输入与 UX 一致。 |
| 不弱化继承约束 | strong | 用户取消开始前、管理员结束前、历史保留、30 天窗口、无原子改期等 PRD 约束均保留。未提供父级 spine，因此父级 AD 继承检查不适用。 |
| 环境与运维维度有决策或明确延期 | strong | 单 Waitress 进程/8 线程、loopback、独立连接、本地 WAL、版本门槛、配置、备份/恢复、测试/演示隔离、故障注入与 schema 版本检查均有边界；不承诺生产 SLA。 |
| 课程证据与交接 | strong | 8 条 ADR 均有备选与理由，16 条 project-context 规则可执行；实验 A 尚待故事定样，B 免做；不把 AI 技术备选否决或 review 当人工决定/教师门禁。 |

## Structure / prose lenses

本文帮助实现者和课程评审者把 PRD 转为一致的代码、接口与验收；spine 采用 Explanation（抽象到具体）结构，执行附件兼具 Reference/Database 结构。默认读者为 humans，采用配置中的 Microsoft Writing Style Guide；未规定缩减目标。

`word_metrics.py` 实跑：spine 2,223 words，执行附件 7,312 words；附件 §5.3 为 764、§6.3 为 421、§7 为 592 words。工具采用其自身计词口径，不能把这些英文式 word 计数当作中文字数。

结构镜头没有建议删除、移动或合并的段落。spine 的不变量摘要、附件的执行细节和 project-context 的实施规则服务不同读取场景，重复具有交接价值；图示、能力映射和独立实验命令应保留。

| Pass | Original Text | Revised Text | Changes |
| --- | --- | --- | --- |
| prose | §7：“第一版数据规模仅1,000，固定返回全部匹配记录” | “本版以 1,000 条预约作为性能验收负载；列表暂返回全部匹配记录，不设 1,000 条存储或保留上限。” | 澄清“测试值”与“产品规模”的区别；与 AR-03 为同一问题，不重复计数。 |

编辑结论：0 项结构删改建议，1 项文字澄清；预计删减 0 words（0%），无为压缩而损失上下文的取舍。AR-01/02 是协议内容澄清，未作为纯措辞问题掩盖。

## Verification record and limits

- 在项目 `.tools/bin/python` 下运行 `lint_spine.py --workspace .../architecture-group-room-booking-2026-11-12`，结果 `ok: true`、`total_findings: 0`。系统 PATH 中没有 `uv`，所以用项目已有解释器运行相同脚本；未安装依赖或改动配置。
- 同一解释器实测 Python `3.12.14`、SQLite `3.53.1`，与 spine 和 project-context 一致；没有运行应用、并发、性能、安全或恢复测试。
- 官方页面核验命名版本存在：[Flask 3.1.3](https://flask.palletsprojects.com/en/stable/changes/)、[Jinja 3.1.6](https://jinja.palletsprojects.com/en/stable/changes/)、[Werkzeug 3.1.9](https://werkzeug.palletsprojects.com/en/stable/changes/)、[Waitress 3.0.2](https://docs.pylonsproject.org/projects/waitress/en/stable/index.html)、[Python 3.12.14](https://www.python.org/downloads/release/python-31214/)、[SQLite 3.53.1](https://sqlite.org/releaselog/3_53_1.html)。这不等于已安装全部依赖或生成完整锁。
- SQLite 官方确认 WAL-reset 修复包含于 3.51.3 及以后；附件采取 3.51.3 门槛、固定 3.53.1 基线有依据。[SQLite WAL-reset 说明](https://sqlite.org/wal.html#walresetbug)
- `docs/course-scope.md` 的 C-02/C-03 仍是架构前状态；作者阶段收尾时应同步“架构已形成、待实际课程评审”的事实，不能将此机械更新写成 M2 已通过。
- 本评审仅写此文件，没有修改架构、PRD、项目上下文、代码或 Git；没有新增任何人工决定或教师批准。
