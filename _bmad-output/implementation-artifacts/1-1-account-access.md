---
title: '使用预置账号安全登录和退出'
type: feature
created: '2026-11-12'
status: done
route: dispatch
baseline_commit: 837f30b48199ede90c4bfbb970080361db051070
story_key: 1-1-account-access
review_loop_iteration: 0
context:
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/implementation-artifacts/epic-1-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/project-context.md
  - /Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking/_bmad-output/planning-artifacts/architecture.md
---

# Story 1.1 — 使用预置账号安全登录和退出

<frozen-after-approval reason="用户已授权完整实施；业务细则由AI依上游基线拟定，非人工逐项批准">

## Intent

**Problem:** 课题组成员需要通过预置账号登录并退出，以便身份明确且退出后旧凭证立即失效。

**Approach:** 交付可运行的单个用户能力，涵盖页面、服务和验证。依赖：无；追踪：FR-01—04、FR-22；NFR-02；ADR-01/05/06/08；UX-DR1/2/3/9/10。

## Boundaries & Constraints

**Always:** 使用上述context固定契约；全部实现位于 `/Users/mima0000/Documents/Codex/2026-11-12/bmad-b/outputs/group-room-booking`。业务事实和时间/权限规则来自上游。仅使用合成演示数据；保留现有文件及用户改动。

**Never:** 不提前实现后续管理取消/撤销实验目标，不操作远端或提交Git；不得把AI测试记作人工/教师验收。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 输出/行为 | 错误处理 |
|---|---|---|---|
| AC-1.1-1 | 空数据目录；重复初始化2成员1管理员并登录 | 账号不重复且旧数据不覆盖；口令以scrypt保存，错误账号和密码同样401提示 | 保持一致错误协议及数据不变约束 |
| AC-1.1-2 | 取得预认证CSRF及cookie；提交正确登录并访问/me | token/CSRF轮换，显示本人及角色；8h绝对到期，刷新不续期 | 保持一致错误协议及数据不变约束 |
| AC-1.1-3 | 两独立登录会话；退出其中一个并重放旧cookie | 该会话401，另一仍有效；到期/匿名不能读业务；所有POST拒绝错误Origin/CSRF | 保持一致错误协议及数据不变约束 |
| AC-1.1-4 | 桌面或390px手机；键盘操作登录与退出 | 有label/焦点/明确反馈，无水平溢出；凭证不进入业务响应/日志；初始化及Waitress命令可复跑 | 保持一致错误协议及数据不变约束 |

</frozen-after-approval>

## Code Map

- `booking_app/` 尚不存在；创建 `__init__.py` 应用工厂、`db.py` 连接/初始化、`auth.py` 会话与CSRF、`domain.py` 安全错误、`web.py` 认证路由。
- `booking_app/schema.sql` 首故事仅需 users/sessions；后续查询故事再增加领域表，不提前实现预约/管理命令。
- `booking_app/templates/base.html`、`login.html`、`home.html` 与 `static/app.css`、`auth.js` 是新文件；本故事首页为清晰欢迎和登录身份，查询功能后续实现。
- `pyproject.toml`、`uv.lock`、`.python-version`、`scripts/init_demo.py`、`tests/test_auth.py` 均需创建；`.tools/bin/python` 为3.12.14，`.tools/bin/uv`已安装（本机工具目录不提交）。
- 可复用现有 `.gitignore` 并补 instance、.venv、缓存；README保留课程事实，添加本故事运行命令。不改上游PRD/ADR/实验协议，不执行Git或远端操作。

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml` / `uv.lock` / `.python-version` — 固定已核验版本并提供 uv sync / uv run 启动方式。
- [x] `booking_app` / `scripts/init_demo.py` — 完成账号、服务端会话、事务、CSRF、错误映射及初始化CLI；初始化本故事的两张表。
- [x] `templates` / `static` — 可操作的中文登录/退出及角色身份显示，响应式和可访问反馈。
- [x] `tests/test_auth.py` — 覆盖以下矩阵和架构修订后的认证事务边界，真实跑通合法/非法路径。
- [x] `README.md` / `.gitignore` — 增加可运行命令和明确合成账号说明，运行数据与私密配置不提交。

**Acceptance Criteria:**

- Given 上述每行初始状态，When 执行对应操作，Then 达到矩阵结果；测试需要显式成功路径和拒绝路径，不只检查页面能打开。
- Given 本次尚无程序代码，When 从README的初始化与Waitress命令启动，Then 可登录、查看身份、退出；不依赖未交付故事。

## Implementation Notes

- 认证服务位于 auth.py；web 仅适配 API/页面与 cookie，不含业务 SQL 或 commit。db 提供显式短写事务，启动检查 schema/SQLite/时区；首故事仅创建 users/sessions。
- scrypt 校验在写锁外；锁内重新读取并消费临时会话、复核 hash/期限/CSRF，提交后才签发 cookie。退出同样先提交再清 cookie，失败不覆盖凭证；认证无业务审计。
- 初始化通过隐藏交互或权限 600 私有文件，至少两成员一管理员；重复执行只补缺失。中文界面含 label、焦点与状态/错误反馈，输入保持纯文本。
- 新增 scripts/verify_auth_http.py 生成私有临时合成账号并实际启动 Waitress，自动保留无凭证的请求状态及环境信息。

## Spec Change Log

## Review Triage Log

| ID/镜头 | 发现 | 裁决及证据 | 路由 |
|---|---|---|---|
| B1 blind | 到期/放弃会话不清理，表长期增长 | low：到期读取正确拒绝，短期课程演示增长无实质功能影响；增加维护分支超过直接修正，不据此加后台任务 | reject-low |
| B2 blind | 孤立Unicode代理字符导致用户名SQL绑定/密码编码500 | medium：auth.py接受非空字符串后直接交给SQLite/scrypt；应当在编码边界拒绝非法Unicode | patch，和E1同因 |
| B3 blind | noscript声称表单仍可用，但成功后停在JSON | low：API按契约返回JSON，页面选择JS交互；真实缺陷是noscript误导，改为明确启用JS，不新增另一套HTML写协议 | patch文案 |
| B4 blind | APP_ORIGIN接受非法端口及显式默认端口 | medium：urlsplit未读取port，字符串原样比较与浏览器标准Origin不一致 | patch，和E4同因 |
| B5 blind | 手工伪造version=1且列名相同但无约束的DB可启动 | low：初始化始终生成约束，触发条件是外部修改/伪造schema；当前课堂常规路径不会遇到，复杂指纹校验不采纳 | reject-low |
| B6 blind | 17000字口令可初始化但超过16KiB请求上限 | medium：初始化与HTTP输入能力不一致，已定位MAX_CONTENT_LENGTH和seed校验；需同一兼容边界 | patch，和E2同因 |
| B7 blind | 私有JSON顶层array/null引发CLI TypeError回溯 | medium：直接json对象索引users；应先检查dict再交给现有受控错误 | patch，和E3同因 |
| B8 blind | getpass无TTY时可能回显而继续 | medium：getpass默认警告而不停止；已有私有文件方式，可将GetPassWarning转为受控失败 | patch |
| B9 blind | commit失败测试实际在COMMIT前抛异常 | medium：db事务yield之后测试抛错，证明普通回滚而非COMMIT异常；准确改名并另加SQL COMMIT处故障注入 | patch测试/证据 |
| B10 blind | 浏览器仅保存PASS/截图，没有可复跑入口 | medium：实际脚本在被忽略work/browser-check.cjs，未交付；保留为便携脚本并给出依赖/运行步骤 | patch，和V1同因 |
| E1 edge | JSON孤立代理字符500 | medium：同B2，不单独算新根因 | patch |
| E2 edge | 配置凭证超过HTTP请求长度 | medium：同B6，不单独算新根因 | patch |
| E3 edge | 顶层array/scalar/null文件回溯 | medium：同B7，不单独算新根因 | patch |
| E4 edge | 默认端口Origin与浏览器不一致 | medium：同B4，不单独算新根因 | patch |
| E5 edge | fetch永久挂起导致按钮一直禁用 | medium：auth.js无超时，网络不确定路径应恢复可操作并提示确认结果；20秒超时高于15秒存储等待 | patch |
| E6 edge | terminate后10秒仍未退出则可能留下验证服务 | maybe-false：当前仅启动默认Waitress且无忽略SIGTERM逻辑，实际退出通过；没有可达挂起证据，潜在影响仅外部故障下测试清理，属未证实low | reject，若今后复现再修 |
| V1 verification | 正常验证不执行浏览器JS，删除CSRF头仍会绿 | medium：服务器测试确实自行构造正确头，无法捕捉页面回归；“不存在忽略目录脚本”表述不准确，但未交付/不可复跑这一结论成立 | patch，和B10同因 |
| V2 verification | 权限644私有文件拒绝未被CLI负向测试覆盖 | medium：seed_users单测绕过main；HTTP脚本只有600合法输入，增加真实子进程拒绝与不改库/不泄漏断言 | patch |
| P1 主代理 | README工具Python3.11与应用精确3.12.14启动指令不衔接 | medium：新机器照抄.tools/python可能版本不符，缺少取得应用Python步骤；增加uv管理3.12.14、frozen同步和fresh环境复验 | patch |

## Verification

- `.tools/bin/uv sync --python .tools/bin/python` — 锁与环境安装成功。
- `.venv/bin/python -m unittest discover -s tests -v` — 本故事测试全通过，无skip。
- 实际启动Waitress并以HTTP登录/退出冒烟；保存命令与结果到 `docs/evidence/story-1.1-verification.md`，不打印凭证。
- 2026-11-12 实测：24 项 unittest 全通过、0 skip；同临时 token 并发登录和同认证 token 并发退出均恰好一成功；真实 HTTP 13 个请求与最终存储断言通过。
- 本机 Chrome 在 1280×800、390×844 通过键盘登录/退出、错误聚焦及无横向溢出验证；原始结果和截图见上述验证记录。所有验证均为 AI 自动化技术证据，不记作人工/教师验收。

主代理最终验收：33项全量Python、2项JS、真实HTTP与隔离环境安装/HTTP全通过；有效评审patch已关闭，详见`../../docs/evidence/reviews/story-1.1-review.md`。
