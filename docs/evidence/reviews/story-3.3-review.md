# Story 3.3 独立质量评审

在两组封存及统一评分后进行。blind9条、edge1条、verification1条，父流程另5条。不是原初稿统一评审的差异收益；完整上下文此时才揭示给Y修补。

## 原始输出

### review_3_3_blind

- Finding floor: 72,257 bytes ÷ 1,000 = 72.257 kB; N = min(⌊√72.257 + 1⌋, 10) = 9.

- [blocks.js:150](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/booking_app/static/blocks.js:150): Reconcile the selected record when refreshing the block list. A refreshed record can be `ended` or `revoked` while the selection panel still says “待开始” and keeps its confirmed, enabled submit button. I reproduced this with the supplied harness. Update the summary and disable obsolete actions.

- [blocks.js:173](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/booking_app/static/blocks.js:173): Changing room, date, or status filters clears the results but preserves the previously selected block and checked revocation confirmation. The user can therefore submit an action against a record outside the new results without confirming again. Clear the confirmation and explicitly retain or dismiss the selection when its query context changes.

- [blocks.js:122](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/booking_app/static/blocks.js:122): Valid database IDs above JavaScript’s safe integer range silently receive no revocation action. The API accepts these IDs, but the UI presents them like ordinary records without explaining the limitation. Preserve exact identifiers as strings or render an explicit unavailable-action explanation.

- [verify_block_revoke_browser.py:36](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/scripts/verify_block_revoke_browser.py:36): Browser-driver timeout cleanup only terminates the direct Node process. Its Chromium descendants can survive because forced termination bypasses the JavaScript `finally`. Reuse the repository’s existing process-group browser wrapper and `run_driver` cleanup, and verify cleanup on timeout.

- [verify_block_revoke_browser.cjs:66](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/scripts/verify_block_revoke_browser.cjs:66): Raw Playwright error stacks are printed and then forwarded by the Python wrapper. Failures during password filling can include the supplied value in Playwright call logs, contradicting the driver’s “never emit credentials” promise. Reuse the existing controlled stage/type/source diagnostics instead of emitting raw exceptions.

- [verify_block_revoke_http.py:50](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/scripts/verify_block_revoke_http.py:50): Verification provenance omits both new browser scripts and imported fixture/contract files. The browser wrapper also captures hashes only after execution. Consequently, a report cannot identify all code that produced it or detect edits made during the browser run. Fingerprint the complete verification dependency set before and after execution.

- [verify_block_revoke_http.py:90](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/scripts/verify_block_revoke_http.py:90): The client barrier synchronizes request dispatch but does not establish that the server transactions contend. All twenty rounds could execute serially while still reporting successful races. Add a deterministic server-side gate or held write lock that proves the second revocation arrives before the first commits.

- [verify_block_revoke_browser.py:42](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/scripts/verify_block_revoke_browser.py:42): Storage verification excludes the four revoked reservations from full before/after comparison, then checks only their cancellation actor/time and audit count. It also never compares the rooms table. A regression that rewrites an original block reason, room, interval, or room metadata could still produce `storage_verified: true`. Assert complete expected rows, allowing only the three revocation fields to change.

- [verify_block_revoke_browser.py:25](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/scripts/verify_block_revoke_browser.py:25): Both new verification runners place temporary databases under `ROOT/work`, but only create the requested output directory. With a custom output directory on a clean checkout, `ROOT/work` need not exist and verification fails before starting. Create the temporary parent explicitly or use the system temporary directory.

### review_3_3_edge

[{"location":"/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/booking_app/static/blocks.js:104-106","trigger_condition":"Refreshing the list returns the selected block as ended or revoked.","guard_snippet":"if (list.kind === \"blocks\" && selected) { selected = records.find(r => r.id === selected.id) ?? null; revokeForm.hidden = !selected || ![\"pending\",\"in_progress\"].includes(selected.status); revokeConfirm.checked = false; if (selected) showSelected(); }","potential_consequence":"Stale status and confirmation remain actionable, inviting rejected or redundant revocation requests."}]

### review_3_3_verification

### The revocation confirmation preview’s time interval is not verified

- **Changed surface:** `showSelected()` renders the selected block’s Beijing start and end times in [blocks.js:244](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/booking_app/static/blocks.js:244).
- **Impacted consumer or site:** The administrator reviews `#revoke-summary` before confirming revocation in [admin.html:79](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/booking_app/templates/admin.html:79).
- **Existing test evidence:** `Regression gap`: the “selected original facts” test checks the original reason and focus, then the successful revoker name and reason, but never the displayed interval ([test_blocks_js.cjs:211](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/tests/test_blocks_js.cjs:211)). The real-browser check likewise asserts the original reason, safe text, and revocation metadata without asserting the original interval ([verify_block_revoke_browser.cjs:25](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/Y/scripts/verify_block_revoke_browser.cjs:25)). Repository searches for `showSelected`, `revoke-summary`, and `blocks.js` found no additional preview assertions.
- **Missing verification:** Assert that the confirmation preview displays both the selected record’s actual start and end times.
- **Demonstration:** I applied an in-memory mutation changing the preview’s `row.end_local` to `row.start_local`. All 90 JavaScript tests still passed. The inspected browser assertions would also accept this incorrect interval; screenshots alone do not assert its correctness.
- **Consequence:** The administrator could confirm revocation while the dedicated confirmation panel displays the wrong time interval.
- **Disposition:** `patch` — extend the existing selected-record JavaScript test with exact expected start/end values, preferably across two records with distinct intervals.

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

先逐条裁决后归并：B1/B2/E1为同一旧选择未失效；B4/P1为同一验证生命周期管理未复用。15条patch发现归并12项修补，1条false reject，0defer。
