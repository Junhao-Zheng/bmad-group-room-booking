# Story 1.1 账号登录与退出：实施验证

验证日期：2026-11-12。执行者：Codex AI。仅使用合成演示账号与独立测试数据库；以下属于自动化技术验证，不是人工成员验收、教师 M1/M2 批准或完整系统 NFR 验收。

追踪：FR-01—04、FR-22；NFR-02 的本故事认证范围；ADR-01/05/06/08；AC-1.1-1—4。

## 运行环境

- macOS 26.6 / arm64，Apple M1 Pro，8 个逻辑 CPU，内存 34,359,738,368 字节（32 GiB）。
- Python 3.12.14，链接 SQLite 3.53.1；Flask 3.1.3，Jinja2 3.1.6，Werkzeug 3.1.9，Waitress 3.0.2。
- 依赖完整锁定在 `uv.lock`；本次同步解析 9 个项目/包，8 个运行依赖。
- Waitress 单进程、8 线程、本机 127.0.0.1；文件 SQLite，WAL、FULL、foreign_keys=ON、busy_timeout=15000。
- 浏览器：本机 Chrome 157.0.8103.51；Playwright 1.58.2 仅作外部验证工具，未加入应用依赖。

## 可复跑命令与实际结果

在项目根目录执行：

```bash
.tools/bin/uv sync --python .tools/bin/python
.venv/bin/python -m unittest discover -s tests -v
.tools/bin/uv run python -m scripts.verify_auth_http
```

初次实施结果：依赖同步成功；24 项 unittest 全部通过，0 skip；真实 HTTP 冒烟通过。原始证据分别为 [依赖同步](story-1.1-uv-sync.txt)、[完整测试输出](story-1.1-tests.txt)、[HTTP 请求状态与版本](story-1.1-http.json)。这些文件保留初次结果；评审修订仅运行定向测试，结果另见本文末尾的修订记录。

HTTP 脚本调用以下真实初始化/启动路径，密码由脚本安全随机生成并写入权限 600 的临时文件；原始口令、cookie、CSRF 和摘要均不打印：

```bash
uv run python -m scripts.init_demo --credentials-file <临时私有文件>
uv run python -m scripts.init_demo --credentials-file <同一临时私有文件>
uv run waitress-serve --listen=127.0.0.1:8000 --threads=8 --call booking_app:create_app
```

脚本将 `BOOKING_DB_PATH` 指向独立临时数据库并配置匹配的 `APP_ORIGIN`，启动的是虚拟环境中的真实 `waitress-serve` 可执行文件；原始 JSON 保存其完整绝对命令。初始化新增数依次为 3、0；13 次 HTTP 请求的全部状态保留。两个独立会话均合法登录、访问 `/api/me` 和首页；缺少 Origin 的登录返回 403；退出返回 200，重放已退出 cookie 返回 401，另一个会话仍为 200。最终数据库有 3 个账号、1 个认证会话。服务日志凭证扫描通过，服务已停止，临时数据已清理。

首次编写 HTTP 验证脚本时，读取 urllib 请求方法的辅助代码使用不存在的 `Request.method` 属性而终止；改用 `Request.get_method()` 后重跑通过。该失败属于验证脚本，未修改业务契约或降低验收要求。

## 验收矩阵

| 场景 | 验证与结果 |
| --- | --- |
| AC-1.1-1 初始化与错误凭证 | 空目录创建 users/sessions；2 成员+1 管理员；重复初始化不覆写 hash、显示名、角色或已有会话；scrypt:32768:8:1 验证；未知账号/错误密码同一 401 文案；空字段 400。 |
| AC-1.1-2 轮换与期限 | 登录前 10 分钟临时会话刷新复用；正确登录消费旧临时会话并轮换 token/CSRF；CurrentUser 精确白名单；8 小时绝对期限及等号到期；刷新与重启不续期。 |
| AC-1.1-3 退出和请求保护 | 同账号独立会话互不影响；旧 cookie、匿名和到期身份被拒绝；所有 POST 对缺失/伪造 Origin、缺失/错值/Unicode CSRF 返回 403且不改数据；表单及 JSON 合法提交通过。 |
| 认证事务边界 | scrypt 期间可由另一连接获取写锁；同一临时 token 并发登录恰 1×200、1×401；同一认证 token 并发退出恰 1×200、1×401；失败响应无 Set-Cookie；轮换 INSERT 失败、提交前边界故障均完整回滚；锁内复核到期/hash/CSRF；真实写锁忙返回 503。 |
| AC-1.1-4 UI/隐私/运行 | 1280×800、390×844 浏览器键盘操作与无溢出检查；输入 label/可见焦点/错误聚焦；模板显示名 XSS 自动转义；响应和日志凭证扫描；no-store、CSP、HttpOnly、SameSite=Lax 与 HTTPS Secure 配置；启动 schema/SQLite/配置保护；真实初始化及 Waitress 命令通过。 |

认证流程没有调用或创建业务审计表。schema 在本故事仅含 `users` 与 `sessions`，`user_version=1`；后续故事增量加入其需要的业务表，当前版本启动检查要求本故事两表字段完整，不进行破坏性迁移。

## 浏览器证据

[浏览器检查结果](story-1.1-browser.json)保存尺寸、页面宽度和各操作结论。两种尺寸均通过 Tab→账号→密码→Enter 登录、首页身份展示、Tab→退出→Enter、退出成功反馈，以及空表单后账号聚焦和 alert。两种尺寸页面均未发生 JavaScript 异常。

- [桌面登录与键盘焦点](story-1.1-login-1280.png)
- [桌面身份首页](story-1.1-home-1280.png)
- [390px 登录与键盘焦点](story-1.1-login-390.png)
- [390px 身份首页](story-1.1-home-390.png)

截图已经视觉检查。390px 页面允许正常纵向滚动，登录及首页的 document.scrollWidth 均为 390；桌面相应值均为 1280。

## 范围与剩余边界

本故事执行项已完成，无已知未通过的本故事验收项。首页仅提供欢迎、身份与退出；会议室目录、预约、管理及实验 A 目标均未提前实现。测试未宣称后续业务权限矩阵、并发预约、查询性能或教师验收已经通过。部署仍限 README 所述本机演示边界，默认库留给部署者自行初始化，不交付含公开固定密码的运行数据库。

## 评审修订的定向验证

评审指出初次 `test_commit_failure_...` 实际在事务助手调用 COMMIT **之前**抛异常，因此上表改称“提交前边界故障”，测试已准确重命名为 `test_pre_commit_failure_...`。新用例另外拦截真实事务助手的 `connection.execute("COMMIT")` 调用并抛出 `sqlite3.OperationalError`，断言随后执行 `ROLLBACK`；临时会话创建、登录轮换及退出三条路径均返回 500、会话数据不变、没有 Set-Cookie，客户端原 cookie 不被签发或清除。这是 COMMIT 调用点故障注入，不是硬盘断电或真实介质损坏试验。

2026-11-12 修订后仅执行涉及编辑文件的定向检查：13 项 Python 用例、2 项 JavaScript 超时用例，以及交付的浏览器 runner，全部通过；未在修订代理侧重复全量测试、依赖安装或原 HTTP 冒烟。详见 [修订验证与命令](story-1.1-post-review-verification.md)、[Python 输出](story-1.1-post-review-tests.txt)、[JavaScript 输出](story-1.1-post-review-js-tests.txt)及[浏览器新结果](story-1.1-post-review-browser/browser-results.json)。初次原始证据未覆盖，修订后截图保存在单独目录。
