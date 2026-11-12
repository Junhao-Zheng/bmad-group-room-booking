# Story 2.5 独立质量评审

实验两组原稿和统一A1—A9结果均已封存；本轮为额外产品质量检查，不倒改实验首轮结论。3个新上下文同能力代理：blind 10条，edge []，verification 1条。

## 原始输出

### review_2_5_blind

- Finding floor: 85,327 bytes ÷ 1,000 = 85.327 kB; N = min(floor(√85.327 + 1), 10) = 10.
- [blocks.js:126](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/booking_app/static/blocks.js:126): The selected booking and checked confirmation survive booking-filter changes and subsequent queries. I reproduced selecting booking 200, changing the room filter, receiving an empty list, and still submitting `/api/admin/bookings/200/cancel`. Invalidate the cancellation selection when the booking query context changes.
- [blocks.js:125](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/booking_app/static/blocks.js:125): Rejecting an unsafe booking ID leaves the previously selected booking and its confirmation armed. I reproduced clicking an unsupported ID and then submitting a cancellation for the previously selected booking 200. Clear or disable the old selection before reporting that the newly selected booking cannot be submitted.
- [blocks.js:125](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/booking_app/static/blocks.js:125): Valid booking IDs above JavaScript’s safe-integer limit cannot be cancelled through the new interface, although the API contract accepts positive 64-bit IDs. Preserve identifiers losslessly through response parsing and URL construction, and test a successful cancellation for an existing large ID rather than only testing rejection.
- [admin.html:79](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/booking_app/templates/admin.html:79): Opening the cancellation panel focuses the reason textarea, but neither that field nor the confirmation checkbox references the booking summary. A screen-reader user can reach destructive confirmation without hearing the selected booking’s title, room, or time. Associate the summary with the controls using `aria-describedby`, or focus and announce the summary first.
- [blocks.js:260](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/booking_app/static/blocks.js:260): The success summary replaces the booking’s room and scheduled interval with cancellation metadata. With a pending-only filter, the automatic refresh also removes the cancelled row, leaving no visible room or scheduled interval for the completed action. Retain those identifying details in the result summary.
- [blocks.js:267](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/booking_app/static/blocks.js:267): `TRANSITION_CLOSED` and `NOT_FOUND` receive the same “retry” guidance as recoverable errors, while the stale target and checked confirmation remain active. A booking that ends while its panel is open can therefore remain displayed as cancellable and repeatedly produce the same rejection. Refresh or invalidate the target for terminal errors while preserving the drafted reason.
- [test_admin_cancel.py:204](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/tests/test_admin_cancel.py:204): The lock-time tests modify state inside a monkeypatched transaction; they do not exercise an actual cancellation waiting behind another connection’s write lock. Add a real contention test covering a deadline or session change before lock acquisition, plus lock-timeout `503 STORE_BUSY` and unchanged storage.
- [verify_admin_cancel_http.py:107](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/scripts/verify_admin_cancel_http.py:107): The concurrency checks cover a member versus an administrator, but never two administrators submitting different valid reasons concurrently. Add that case and verify that both responses preserve the same winning administrator, reason, and timestamp with exactly one cancellation audit.
- [verify_admin_cancel_http.py:71](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/scripts/verify_admin_cancel_http.py:71): Verification fingerprints omit executable dependencies including `scripts/init_demo.py`, `scripts/verify_create_booking_http.py`, `tests/history_fixtures.py`, and `tests/schedule_fixtures.py`. Changes to seeding, the clock, or expected DTO keys can therefore alter the run without changing the recorded fingerprint set. Include these dependencies in the manifest and final comparison.
- [verify_admin_cancel_browser.py:74](/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/work/experiment-a-run-20261112/X/scripts/verify_admin_cancel_browser.py:74): Browser failures discard captured driver output and delete the temporary database before preserving final storage facts; storage assertions also run before `storage.json` is written. Consequently, the evidence needed to diagnose a failed invariant disappears. Save sanitized diagnostics and before/after storage snapshots before asserting, including on driver failure.

### review_2_5_edge

[]

### review_2_5_verification

### Late cancellation success after identity loss lacks verification

- **Changed surface:** The new cancellation handler suppresses protected details when a successful response arrives after another panel has detected identity loss — `booking_app/static/blocks.js:258`.
- **Impacted consumer or site:** The cancellation summary on `/admin`, rendered at `booking_app/static/blocks.js:260`, shares the page with room management, which broadcasts `admin-auth-lost` at `booking_app/static/rooms.js:89`.
- **Existing test evidence:**
  - **Regression gap:** Repository searches for `admin_cancel_booking`, `admin-cancel`, the cancellation route, and `blocks.js` identified the relevant service, JavaScript, and browser verification files.
  - `tests/test_blocks_js.cjs:168` tests delayed responses after another panel loses identity, but its cases cover room directory, block list, room write, and block write only.
  - Cancellation tests at `tests/test_blocks_js.cjs:243` cover rejection of the cancellation request itself; those at line 248 cover identity loss during the subsequent refresh. Neither delays a successful cancellation response until after another panel reports identity loss.
  - `scripts/verify_admin_cancel_browser.cjs:79` logs out before submitting cancellation, so it exercises rejection rather than a delayed success.
- **Missing verification:** Assert that a delayed successful cancellation cannot repopulate the cleared summary after room management reports `AUTH_REQUIRED` or `FORBIDDEN`, while preserving confirmed cancellation feedback.
- **Demonstration:** Removing only the guard at `booking_app/static/blocks.js:258` in memory left all 228 JavaScript tests passing. A separate probe using the existing combined-panel harness delayed cancellation, returned `AUTH_REQUIRED` from room management, then released the successful cancellation response. The original code kept the summary empty; the mutation restored the booking title, cancellation actor, and reason.
- **Consequence:** A regression could redisplay protected cancellation details after the page has already detected identity loss, without the checked verification failing.
- **Disposition:** `patch` — extend the existing combined-panel delayed-response test in `tests/test_blocks_js.cjs` with administrator cancellation, asserting an empty summary, disabled controls, retained draft, and confirmed-result/relogin feedback.

## Review Triage Log

|发现|判定|路线|核验与理由|
|---|---|---|---|
|B1 筛选/重查询后原取消目标仍 armed|high|patch|blocks.js 的 input/change 仅清 list，load 也未清 selectedBooking；改变房间至空列表仍可取消旧对象，用户可能误操作。清已有选择/确认及受保护摘要，保留原因草稿；自动成功刷新保留已知结果。|
|B2 无法安全选择新 ID 时仍保留旧目标|medium|patch|安全整数检查在 selectedBooking 赋值前 return，不撤销旧选择与确认。拒绝新目标时清旧目标/确认，避免对旧对象发送请求。|
|B3 浏览器无法操作超出安全整数的合法 64 位 ID|low|reject|限制属实，API 服务支持正64位且UI主动拒绝避免取整误取消；既有多页面使用数值JSON，统一无损解析需新增跨页面协议/解析复杂度。日常课程种子和递增规模不可能触及2^53，按低概率且非直接修正规则拒绝扩大本轮范围，README保留边界；不把安全拒绝计为权限/ADR冲突。|
|B4 取消控制未关联目标摘要|low|patch|模板 reason 仅关联字段错误，checkbox 不引用摘要。直接添加 aria-describedby 保留原错误引用，并用实际DOM属性检查。|
|B5 成功结果丢失房间和时段|medium|patch|成功摘要仅ID/title/取消元数据，pending筛选自动移除记录。保留房间与完整北京时间区间。|
|B6 终态错误仍提示重试且保留确认|medium|patch|TRANSITION_CLOSED/NOT_FOUND 走通用可重试文案，selectedBooking/confirm不清。仅对此两码清目标/确认、保留原因并明确重新查询；非终态错误维持恢复。|
|B7 真实写锁等待的期限与busy验证缺失|medium|patch|现有该方法替换write_transaction，真实20轮竞争不改变时钟；没有该命令等待真实另一连接至截止再取得锁、或超时503且数据不变的测试。复用真实文件库/连接加入定向断言，禁止以sleep推测已进入锁等待，使用可观测同步。|
|B8 两个管理员不同原因竞争缺少覆盖|medium|patch|HTTP仅member/admin；重复admin的顺序用例不覆盖两个有效不同原因同时首提交。追加独立admin/admin竞争与双方相同首actor/time/reason、恰1审计、目标槽释放及其他数据不变断言。|
|B9 HTTP源指纹未包括执行依赖|medium|patch|fingerprints仅app、当前脚本、performance/historybrowser，实际seed和FULL_KEYS来源未入。加init_demo、verify_create_booking_http、history/schedule_fixtures等直接/间接可执行依赖并前后比较。|
|B10 浏览器失败丢失数据库事实和安全诊断|medium|patch|run_driver失败立即raise，after事实和storage文件仅在断言后写出；TemporaryDirectory退出销毁库。使用现有安全结果机制，失败仍保存无凭据 before/after事实，先保存再断言，只保留诊断类型/阶段等白名单，不输出原始driver日志。|
|V1 跨面板身份失效后的迟到取消成功无断言|medium|patch|验证层预验证：移除blocked成功guard所有228JS仍过；真实combined harness证明摘要重现。补AUTH_REQUIRED/FORBIDDEN两种时序，摘要空/控件禁用/原因保留/已知成功和重新登录反馈；不要更改正确guard。|

逐条裁决后归并：B1/B2同为旧选择未失效，合并一次修补；其余不同根因不合并。10条patch发现→9项修补，1条low reject，0defer；没有变更产品需求或编造人工决定。

## 修补后的父流程发现 P1

medium / patch：新增 test_admin_cancel_browser_runner 调用 main 的真实 environment_metadata，后者读取仓库 work/browser-tools/node_modules/playwright/package.json；driver 已被测试替身替换，故这三项应是Python/真实本地服务测试，却在按README只装应用依赖的干净检出中因缺Playwright元数据而提早失败。测试内提供明确的受控环境元数据，并用sys.executable作为不会真正启动的wrapper目标，不能改弱生产runner的真实环境核验。保留真实SQLite/Waitress、故障留证和秘密哨兵断言。此为首轮修补引入的测试可移植性问题，另一次修补调用，非done后返工。

本次父流程在现有安装环境完整运行172项Python、241项JS通过，无skip；该成绩不宣称干净检出已过。最后统一集成后还要重新完整验证。

## 最终技术接受

全部接受修补经主仓库组合192 Python/282 JS及4套浏览器/2套HTTP检查，源哈希一致；[最终核验](../experiment-a-integration/parent-final-qa.json)。Y全量发现的既有2.3测试时限问题已单独返工闭环；无未处理阻塞项。
