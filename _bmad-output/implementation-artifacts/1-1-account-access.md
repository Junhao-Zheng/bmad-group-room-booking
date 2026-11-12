---
title: '使用预置账号安全登录和退出'
type: feature
created: '2026-11-12'
status: ready-for-dev
route: dispatch
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
- [ ] `pyproject.toml` / `uv.lock` / `.python-version` — 固定已核验版本并提供 uv sync / uv run 启动方式。
- [ ] `booking_app` / `scripts/init_demo.py` — 完成账号、服务端会话、事务、CSRF、错误映射及初始化CLI；初始化本故事的两张表。
- [ ] `templates` / `static` — 可操作的中文登录/退出及角色身份显示，响应式和可访问反馈。
- [ ] `tests/test_auth.py` — 覆盖以下矩阵和架构修订后的认证事务边界，真实跑通合法/非法路径。
- [ ] `README.md` / `.gitignore` — 增加可运行命令和明确合成账号说明，运行数据与私密配置不提交。

**Acceptance Criteria:**

- Given 上述每行初始状态，When 执行对应操作，Then 达到矩阵结果；测试需要显式成功路径和拒绝路径，不只检查页面能打开。
- Given 本次尚无程序代码，When 从README的初始化与Waitress命令启动，Then 可登录、查看身份、退出；不依赖未交付故事。

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

- `.tools/bin/uv sync --python .tools/bin/python` — 锁与环境安装成功。
- `.venv/bin/python -m unittest discover -s tests -v` — 本故事测试全通过，无skip。
- 实际启动Waitress并以HTTP登录/退出冒烟；保存命令与结果到 `docs/evidence/story-1.1-verification.md`，不打印凭证。
