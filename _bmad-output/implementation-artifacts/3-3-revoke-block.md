---
title: '撤销尚未结束的停用'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: 39436f328eaf2b85d5bf72629e903db00ccc842b
experiment_baseline_commit: b0ce58a9b66144db5a4b15f61376132fa3f210e4
story_key: 3-3-revoke-block
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-3-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 3.3 — 撤销尚未结束的停用

<frozen-after-approval reason="用户授权完整实施；实验A的Y组；不是人类逐项批准">

## Intent

**Problem:** 管理员需说明原因释放不再需要的维护时段，恢复房间可预约性并保留历史。
**Approach:** 独立停用撤销，追踪FR-19/21/22、NFR-01/02/04、ADR-03/05/06/07、UX-DR8/9/10。

## Boundaries & Constraints

**Always:** 管理权限、合法原因、期限、幂等和原子审计。
**Never:** 不恢复已取消预约、不硬删除历史，不冒充人工判断。

## I/O & Edge-Case Matrix

|验收|Given/When|Then|
|---|---|---|
|AC-3.3-1|管理员对未结束停用提交strip后1—500字原因|200 BlockFull；首次保存撤销时刻/人/原因，全部槽释放，同事务一次block.revoked审计|
|AC-3.3-2|已撤销记录或首次t>=end；重复合法/非法原因|重复保留原结果，即使end已过；首次结束409；重复非法原因仍400|
|AC-3.3-3|成员、失效/退出、降权或非法参数|权限优先、拒绝且数据不变；对象kind、正64位ID及原因格式正确|
|AC-3.3-4|同时重复撤销或审计失败|一次转换与首成功元数据；失败完整回滚，不恢复曾取消预约|

</frozen-after-approval>

## Code Map

- 本卡在首次实现前冻结于主仓库，但不向Y提供；Y只接收预登记口述TASK、共同运行说明及共同基线代码/测试。不得读本卡、规划、主仓库或X。初稿封存、统一首轮评审之后，修复阶段才揭示完整上下文；记录这一区别。
- services独立revoke_block：BEGIN IMMEDIATE后一次Clock、重验数据库有效admin；先验证strip后1—500字原因，再查kind=block。已撤销返回原Full且零writer；首次仅t<end，更新存储取消字段、只删目标槽、一次block.revoked审计，完整before/after同连接，提交后返回。
- POST /api/admin/blocks/<ID>/revoke接受JSON reason，单层ok/data；沿用Origin/CSRF、身份优先、严格ID和安全错误。原停用reason保持，输出revoked字段按BlockFull，不能泄露存储cancelled字段。
- /admin停用列表增加原因及明确确认，提交中禁用，失败保留输入，成功刷新。文本安全展示，手机/桌面可用，不影响已有预约/停用查询与创建。
- 两管理员独立HTTP会话20轮同时撤销，每轮两个200且元数据一致、仅一次转换/审计；验证首成功actor/time/reason、全部槽释放、其他记录不变。
- 验证待开始/进行中、首次结束等号、过期重复、重复非法原因、错误kind/严格ID、匿名/member/过期/退出/降权、writer前/后失败与提交失败，真正文件库事务回滚。

## Tasks & Acceptance

- [x] 首次实现按Y口述输入，封存后统一评审。
- [x] 修复后独立命令、API、界面与验收全部通过。
- [x] 实际保存验证，不重复计数测试，不写未跑成绩。

## Implementation Notes

本卡是主流程追踪和首稿之后评审修复的合同，不是Y的首次输入。全部实验差异须据首稿证据记录，不人为制造失败。

## Spec Change Log

## Review Triage Log

|发现|判定|路线|核验与理由|
|---|---|---|---|
|B1 重新查询不刷新选中停用|medium|patch|render只重建列表，selected仍旧快照。已有对象变为ended/revoked时确认表单可继续操作。主动查询清旧目标与确认，或按新结果更新并禁用终态；成功自动刷新保留已知撤销结果。|
|B2 改变筛选保留旧目标和已确认状态|high|patch|input/change只清列表，撤销form仍有selected。新筛选上下文可误操作旧对象；清既有选择/确认、清受保护摘要，保留原因草稿。|
|B3 不安全大ID无可操作提示|low|patch|Number.isSafeInteger失败不生成按钮也不解释；直接显示无法安全提交编号的文字，不引入无损数字协议，不接受对旧对象操作。极大ID限制继续披露。|
|B4 Node超时未回收浏览器后代|medium|patch|subprocess.run timeout仅处理直接进程，CJS finally被终止时Chromium可残留。复用已有browser_wrapper/run_driver与受管组清理，故障验证只操作本次所有PID。|
|B5 失败输出原始Playwright堆栈|medium|patch|CJS error.stack且Python print(stderr)，fill失败可能记录密码值。改为已存在的stage/type/source等安全白名单；不得归档原始私密stderr，测试故障输出不含哨兵。尚未观察到初稿凭据实际泄露，不伪称已泄露。|
|B6 浏览器/依赖源哈希不完整且仅事后采集|medium|patch|source_hashes缺browser.py/cjs和fixture等；浏览器仅末尾调用。覆盖实际依赖、环境、运行前后指纹一致；每次独立run_id。|
|B7 客户端屏障不足以宣称服务器必然锁争用|false|reject|实际报告声明独立HTTP双请求同步发出和最终一次转换，未声明两事务都已进锁等待；SQL写事务按设计串行。20轮barrier+两个HTTP客户端+trigger最终状态是预登记标准。强制服务端gate是额外实验条件，不是当前声称被证伪；保留“未强制观测服务器锁等待”的限制，不冒称确定重叠。|
|B8 浏览器目标完整行及rooms未核对|medium|patch|四个目标被排除完整前后比对，循环只检查幸存目标，删目标/改原reason或room元数据可漏检。完整ID集合、rooms/旧audit/未变记录及目标仅三取消字段变化、精确审计快照/原原因/槽均断言；先写事实再断言并加负面oracle。|
|B9 自定义输出与干净检出缺work父目录|medium|patch|两个TemporaryDirectory指定ROOT/work但仅mkdir output，自定义外部输出确实不存在父目录。改系统临时目录，不依赖仓库work存在。|
|E1 刷新后selected终态未同步|medium|patch|与B1相同真实路径。edge给出的guard_snippet是建议补丁而非当前源码；当前render不存在该重对齐代码。按B1修正。|
|V1 确认摘要区间绑定缺回归|medium|patch|验证层预验证：end_local改成start_local的内存突变仍过全部90个该JS文件测试。加两个不同区间的精确DOM值，真实浏览器也核对完整区间。|
|P1 PASS早于server清理且缺失败诊断隔离|medium|patch|main在try写PASS然后finally stop，stop失败仍留PASS；无run_id可覆盖旧图。复用现有INCOMPLETE→每次run→实际清理成功后PASS机制，异常保留阶段/类型与可得无凭据事实。|
|P2 浏览器尺寸未按完整故事对齐|low|patch|初稿脚本height=900，冻结实验仅桌面/手机故通过，但正式3.3规定1280×800/390×844。直接改两尺寸并真实跑，不倒改初稿实验分数。|
|P3 测试断言预约永远无按钮妨碍合法集成|medium|patch|新增只对block生成revoke的用例同时断言bookings完全无button；正确2.5集成将失败。改为预约无“撤销停用”动作，允许独立管理员取消预约。|
|P4 身份失效后迟到成功丢失已知结果|medium|patch|成功验证后if(blocked)return在revokedMessage赋值前，使已提交撤销仍只有失效提示。保留已确认撤销且要求重新登录，受保护摘要保持清空；覆盖AUTH_REQUIRED/FORBIDDEN先到再成功的两顺序。|
|P5 终态拒绝仍保留过期目标供反复确认|medium|patch|TRANSITION_CLOSED/NOT_FOUND只清confirm，selected/status不变，提示重新确认但目标不可操作。清已有目标并提示重新查询，保留原因；可恢复错误仍可人工重试。|

## Verification

- 全量Python及JS回归，无skip；精确DTO和安全错误。
- 20轮真实独立HTTP双管理员撤销，最终数据库一次转换/审计、原元数据和槽；文件库故障回滚。
- 1280×800和390×844实际管理撤销、原因/确认/等待/拒绝/结果及既有关键路径，保留证据。

## Quality Review Fixes — 首稿封存后的额外产品修补

本轮于初稿及统一 A1—A9 分数封存后，才完整读取本卡、Epic 3 context、project-context、architecture，以及 project-context 要求的 PRD/spine。此前初稿输入边界不变；上方逐条 Review Triage Log、初稿输出与原验证目录均保留，不回改初稿成绩。未读 X/主仓库，未操作 Git。新增证据全部放在 `work/quality-review-fixes/`。

### 修补结果

- B1/B2/E1/P5：主动查询及筛选 input/change 立即清空旧目标、确认和保护摘要，保留撤销原因草稿；首次成功后的自动刷新保留已知结果。提交 guard 只接受 pending/in_progress。TRANSITION_CLOSED/NOT_FOUND 清旧目标并要求重新查询，可恢复失败及未知结果保留人工确认重试。
- B3/P3/P4：不安全整数编号显示明确不可安全提交提示；预约测试只禁止“撤销停用”动作，允许其他合法预约动作。AUTH_REQUIRED/FORBIDDEN 先到、撤销成功后到时保留“已撤销，请重新登录查看”提示，仍清空保护摘要、禁用管理控件并保留草稿。
- B4/B5/B6/B9/P1：浏览器复用 browser_wrapper/run_driver/stop_process_group，回收本次 Node/Chromium/Waitress 进程组；系统临时目录不依赖 ROOT/work。HTTP/浏览器每次独立 run_id，先写 INCOMPLETE；实际清理成功、开始/结束源哈希一致后才发布 PASS。指纹覆盖应用、浏览器 Python/CJS、直接/间接本地 helpers、fixtures 和依赖锁；记录环境版本及运行参数。失败保存可得 before/after 业务事实和受控 stage/type/source，不输出原始 driver stdout/stderr、异常消息或堆栈。
- B8/V1/P2：完整目标 ID 集合、全部原字段、rooms、其他记录、旧审计、目标三撤销字段、完整审计前后快照及全部槽均严格比对；先保存事实再断言。负面 oracle 明确拒绝删目标、改原原因/房间/区间等损坏。处理器和真实浏览器均核对两个不同区间的精确 start/end 摘要；浏览器改为 1280×800、390×844。

### 实际定向验证（非全量回归）

|命令/验证|实际结果|证据|
|---|---|---|
|`.venv/bin/python -m unittest tests.test_block_revoke_runner -v`|11 项通过，无 skip；含存储负面 oracle、发布门禁、源指纹、系统临时目录、失败事实留存。替身测试使用受控 metadata、不存在的 playwright-root 和 sys.executable，不要求 Node/浏览器安装。|[Python 定向日志](../../docs/evidence/story-3.3-review-fixes/isolated/revoke-runner-python.log)|
|`node --test tests/test_blocks_js.cjs tests/test_block_revoke_browser_runner_js.cjs`|104 项通过，无 skip；含真实处理器时序、两种身份失效后的迟到成功、终态 guard、摘要 end→start 内存突变被拒绝及诊断秘密哨兵。|[JavaScript 定向日志](../../docs/evidence/story-3.3-review-fixes/isolated/revoke-js.log)|
|`.venv/bin/python -m scripts.verify_block_revoke_http`|20 轮、两个独立管理员 HTTP 会话、40 个 200；每轮一次实际转换/一条撤销审计，首 actor/time/reason、原记录及释放槽校验通过；审计前后故障回滚及重启重试通过；源指纹前后一致。run_id=`38620960b6a0762b6f35d7a815bb0669`。|[新 HTTP 报告](../../docs/evidence/story-3.3-review-fixes/isolated/block-revoke-http/http-result.json)|
|`.venv/bin/python -m scripts.verify_block_revoke_browser`|本机 Chrome 157.0.8103.51；1280×800、390×844 均通过，完整存储 oracle、精确区间、原原因/首次撤销元数据、无页面横溢出与无 pageerror；截图已查看；清理完成且源指纹前后一致。run_id=`d5794912e8ad0d6e94b89c5623528a31`。|[新浏览器报告](../../docs/evidence/story-3.3-review-fixes/isolated/block-revoke-browser/browser-result.json)|
|真实 `--driver-fault secret-error` / `--driver-fault timeout --driver-timeout 6` 注入|两个失败运行均保持 INCOMPLETE，替换预置旧 PASS；已启动的 Chromium/服务进程组经 ps 确认无存活进程；before/after 事实保留；异常同时含哨兵及合成登录口令，公开输出/JSON 无哨兵；运行前后源指纹一致。|[故障检查结果](../../docs/evidence/story-3.3-review-fixes/isolated/lifecycle-injections-final/injection-results.json)|

### 剩余限制与交接

本轮未发现尚未修复的所列问题。仅跑覆盖本次改动的定向检查及新 HTTP/浏览器验证；全量回归由父流程另行运行，本卡不据定向通过宣称全量通过。浏览器实测限本机 macOS Chrome；受管进程工具支持 macOS/Linux POSIX，未宣称其他浏览器/平台通过。不安全整数 ID 继续保持 API JSON 整数合同并在页面明确拒绝，未引入无损数字协议。20 轮并发按预登记标准用客户端 barrier 同时派发；未强制服务端 gate，也未直接观测每轮写锁等待。仍只实现停用撤销，不在本目录实现 2.5 管理员取消预约。

## 本轮接受结果

独立质量审查及修补完成，主流程最终合并后192个唯一Python、282项JS，4套真实浏览器及两套真实HTTP均PASS、无skip，源指纹已逐项复算。技术接受属于AI流程，不冒充人类/教师验收。[最终核验](../../docs/evidence/experiment-a-integration/parent-final-qa.json)。
