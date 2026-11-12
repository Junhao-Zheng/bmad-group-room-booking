---
title: '管理员说明原因干预未结束预约'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: 177dc64e5897a24850dcc79714cfcb87724c09d6
experiment_baseline_commit: b0ce58a9b66144db5a4b15f61376132fa3f210e4
story_key: 2-5-admin-cancel
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/docs/experiments/frozen-inputs/X/EXPERIMENT-INPUT.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-2-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/PRD.md
---

# Story 2.5 — 管理员说明原因干预未结束预约

<frozen-after-approval reason="用户授权完整实施；实验A的X组；不是人类逐项批准">

## Intent

**Problem:** 管理员需处理未结束预约并向预约人说明理由。
**Approach:** 独立管理取消命令，追踪FR-15/21/22、NFR-01/02/04、ADR-03/05/06/07、UX-DR8/9/10。

## Boundaries & Constraints

**Always:** 按上下文合同、单事务业务/槽/审计、新鲜身份与一次锁后时刻。
**Never:** 不实现撤销停用或通用管理转换命令，不读对照Y目录，不操作Git/远端，不冒充人类决策。

## I/O & Edge-Case Matrix

|验收|Given/When|Then|
|---|---|---|
|AC-2.5-1|管理员对待开始/进行中预约提交strip后1—500字原因|200 BookingFull；首次取消保存时刻/人/原因，释放全部槽，一次booking.cancelled_by_admin审计|
|AC-2.5-2|已取消记录含成员先取消；或首次t>=end；重复合法/非法原因|重复原结果/元数据/零审计，即使原end已过；首次结束409 TRANSITION_CLOSED；重复非法原因仍400|
|AC-2.5-3|成员、匿名、过期/退出、旧角色或非法参数|权限优先、拒绝且数据不变；正确kind；正64位ID/格式按合同|
|AC-2.5-4|成员与管理取消20轮真实HTTP竞争；审计失败|一转换保留首成功事实，双方结果一致；失败业务/槽/审计完整回滚|

</frozen-after-approval>

## Code Map

- 基线已有成员取消、房间/停用创建和管理列表，尚无两个实验目标。读取当前代码再接入；保留既有用户路径。
- services独立admin_cancel_booking(actor,id,reason)：BEGIN IMMEDIATE取得锁后一次Clock，重验有效会话及数据库admin；reason用normalized_text，校验对象kind=booking；已取消返回现有Full；首次t<end后更新cancelled_at/by/reason、只删对应槽、写完整before/after快照事件，COMMIT后返回。不得用传入Actor.role代替数据库，不能把校验放幂等分支之后。
- POST /api/admin/bookings/<ID>/cancel接受JSON reason，单层ok/data；所有POST沿用Origin/CSRF。详情取当前房间/显示名，但审计保留事件时操作者快照。不存在或对象kind不对404，普通成员先403，非法字段400。
- 在现有/admin预约列表提供取消确认及原因输入，等待禁用、失败保留、成功刷新；取消结果对预约人可见。textContent/模板转义，1280×800/390×844可用。
- 幂等分支不得调用writer；同事务注入writer前/后失败与COMMIT故障须回滚；复用已取消记录保留原操作者/原因（可能null）。测试权限/期限的精确等号，过期/退出/降权，非法reason含NUL/无效UTF8；不对测试用例继承重复计数。
- 初次实现只做本轮功能及验证，不自行另开代理评审/修复。父流程先封存初版代码和输出，再按实验统一标准评审；负面结果如实报告。

## Tasks & Acceptance

- [x] 交付独立命令、API、界面和矩阵测试。
- [x] 实际验证并保留原始输出；报告遗漏或风险，不写未跑成绩。

## Implementation Notes

本次是同基线、同模型配置、同主机的实验A完整上下文组。父流程记录调用时间；不自行修改上游规则。

## Spec Change Log

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

## Verification

- 全量Python及JS回归，无skip；API精确DTO和安全错误。
- 20轮真实独立HTTP成员/管理员取消竞争，最终DB完整槽、元数据、恰一次转换审计；真实文件库故障回滚。
- 桌面/手机真实浏览器操作管理取消、原因/确认/等待/拒绝/结果和成员详情；保留证据。


### 初次实现验证记录（2026-11-12）

独立 `admin_cancel_booking`、管理取消 API、管理预约列表原因/确认界面已实现。取得写锁后一次取时，重验会话及数据库角色；原因校验先于幂等；首次取消、槽释放、完整审计快照在同一事务提交。成员入口保持原规则。未实施停用撤销，未自行发起独立代理评审。

- Python 全量：167 tests，PASS，无 skip。原始输出：`work/admin-cancel-python-final.log`。
- JavaScript 全量：228 tests，PASS，无 skip。原始输出：`work/admin-cancel-js-final.log`。新增 11 个独立 Python 测试方法与 20 个 JS 用例，无测试类继承重复计数。
- 20 轮真实 HTTP 成员/管理员取消竞争：40 个独立会话请求全部 200、每轮两个结果一致且仅一次转换审计。最终一轮验收成员先成功 13 轮、管理员 7 轮；不是固定胜者要求。审计写入前、写入后、SQLite 实际拒绝 COMMIT 均完整回滚；重启和原意图重放通过。`work/admin-cancel-http/http-result.json` 指向全部响应及各轮存储事实。
- Chrome / Playwright 1.58.2：1280×800、390×844 真实浏览器操作通过；原因/确认、等待禁用、实际拒绝、丢响应后人工重试、成员详情原因、可用性释放、会话退出、纯文本展示与无横向溢出均验证。`work/admin-cancel-browser/browser-results.json` 指向响应、存储和截图；最终桌面/手机取消面板截图已目视检查。
- 初次两个测试夹具错误（表单 CSRF 传法、种子少一个成员）的失败日志保留，修正后通过。完整交付清单、命令、源文件哈希、限制与隔离说明见 `work/admin-cancel-implementation-report.json`。

初次实现供父流程先封存再统一评审；本记录不代表独立评审或人类批准。UI 对超出 JS 安全整数范围的编号拒绝提交以防取整误取消；API/服务支持合同规定的正 64 位编号。首次从父工作目录执行的文件名清单检索曾列出 X/Y browser-tools 文件名与 spec 路径，但未打开 Y 或原始仓库文件内容；其后项目读写均限本 X 目录，未运行 Git/远端操作。


### 封存后质量修补：定向验证记录（2026-11-12）

保留上述逐条 Review Triage Log 与初稿验证记录；本轮修复 B1/B2/B4/B5/B6/B7/B8/B9/B10/V1，B3 维持 reject，不扩大 JS 安全整数 UI 能力或修改 JSON 合同。未实施另一实验目标，未执行 Git 操作。

- B1/B2/B6：预约筛选 input/change、主动查询、拒绝不安全编号、TRANSITION_CLOSED/NOT_FOUND 均清旧目标与确认、清受保护摘要、保留原因草稿；终态错误明确要求重新查询。成功自动刷新保留已有结果及可复核目标。
- B4/B5：原因与确认直接 aria-describedby 关联当前预约摘要，原因保留字段错误关联；成功摘要包含会议室编号/名称/地点与完整北京时间起止。真实 DOM 属性及 pending 筛选后显示值已验证。
- V1：combined rooms/blocks 实际处理器验证 AUTH_REQUIRED 与 FORBIDDEN 先到、取消成功后到；摘要仍空、控件禁用、草稿保留、反馈保留已确认取消并要求重新登录。删除原正确 blocked guard 的两个突变均被新增 oracle 检出，未修改该 guard。
- B7：真实文件库另一连接持有写锁，以实际 BEGIN IMMEDIATE 的 trace 回调同步；锁释放前将 Clock 推至 end，随后取得锁的命令拒绝，业务/槽/审计不变。真实 BEGIN 超时测试仅将连接 busy_timeout 缩至 50ms，返回 503 STORE_BUSY 且存储不变。
- B8/B9：保留原 20 轮 member/admin；新增不同管理员、不同原因、独立双会话同时首次取消，双方保存首 actor/time/reason 相同、恰一次取消审计、只释放目标槽且其他活动槽/记录/审计不变。直接/间接执行依赖加入运行前后 SHA 比较。
- B10：driver 结果解释及存储断言前保存无凭据 before/after；失败保存可取得的事实与阶段/异常类型/退出码白名单诊断。真实库上的 driver 非零、driver timeout、存储断言失败三个注入均证明旧 PASS 被替换为 INCOMPLETE，包含已发生的取消事实，未保存原始敏感 driver 日志。

仅执行受改动覆盖的定向检查，未重跑全量：

|命令|实际结果|原始证据（均在 work/quality-review-fixes/）|
|---|---|---|
|`node --test tests/test_blocks_js.cjs`|100 PASS，0 skip|`blocks-js.log`|
|`.venv/bin/python -m unittest tests.test_admin_cancel -v`|13 PASS，0 skip|`admin-cancel-python.log`|
|`.venv/bin/python -m unittest tests.test_admin_cancel_browser_runner -v`|3 PASS，0 skip|`browser-runner-python.log`及三个独立失败证据目录|
|新 HTTP runner（显式新 output-dir）|20 轮 member/admin 共40个200；1轮 admin/admin 共2个200；存储/回滚/重启/指纹均 PASS|`http.log`、`http/http-result.json`及其 run 目录|
|新浏览器 runner（显式新 output-dir）|1280×800、390×844 PASS；实际 DOM 属性与完整结果摘要断言通过，面板截图目视检查|`browser.log`、`browser/browser-results.json`及其 run 目录|

完整命令、修改文件 SHA、运行目录见 `work/quality-review-fixes/report.json`。初稿输出未覆盖，统一全量验证留给父流程。

## 修补后的父流程发现 P1

medium / patch：新增 test_admin_cancel_browser_runner 调用 main 的真实 environment_metadata，后者读取仓库 work/browser-tools/node_modules/playwright/package.json；driver 已被测试替身替换，故这三项应是Python/真实本地服务测试，却在按README只装应用依赖的干净检出中因缺Playwright元数据而提早失败。测试内提供明确的受控环境元数据，并用sys.executable作为不会真正启动的wrapper目标，不能改弱生产runner的真实环境核验。保留真实SQLite/Waitress、故障留证和秘密哨兵断言。此为首轮修补引入的测试可移植性问题，另一次修补调用，非done后返工。

本次父流程在现有安装环境完整运行172项Python、241项JS通过，无skip；该成绩不宣称干净检出已过。最后统一集成后还要重新完整验证。

### P1 定向修补结果（2026-11-12）

仅修改 `tests/test_admin_cancel_browser_runner.py`：测试内注入明确标为 `stubbed-driver-real-waitress-sqlite` 的受控 `environment_metadata`；不会执行的浏览器 wrapper 目标改为 `sys.executable`。三种故障路径均传入本次输出目录下明确不存在的 `deliberately-absent-playwright-root`，在 metadata 替身、driver 替身的 `NODE_PATH` 以及结束后分别断言目录仍不存在，证明不读取 node_modules。生产 runner 的环境核验、应用、HTTP/浏览器实现与既有证据未修改。

实际仅运行 `.venv/bin/python -m unittest tests.test_admin_cancel_browser_runner -v`：3 tests PASS，0 skip，1.856s。真实 Waitress/SQLite、已变更 before/after 事实、旧 PASS 失效及全部秘密哨兵断言保留并通过。原始输出：`work/quality-review-fixes/portable-runner-tests.log`；本次新增失败证据目录分别为 `browser-timeout-jwq80xde`、`browser-driver-gftjcm85`、`browser-storage-hyhrylu2`（同属 `work/quality-review-fixes/`）。未重跑全量；父流程 P1 记录原样保留。

## 本轮接受结果

独立质量审查及修补完成，主流程最终合并后192个唯一Python、282项JS，4套真实浏览器及两套真实HTTP均PASS、无skip，源指纹已逐项复算。技术接受属于AI流程，不冒充人类/教师验收。[最终核验](../../docs/evidence/experiment-a-integration/parent-final-qa.json)。
